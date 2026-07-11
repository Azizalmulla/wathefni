#!/usr/bin/env python3
"""Phase 7C — company-scoped READ-ONLY compliance/document reconciliation audit.

Measures document truth gaps across:
  onboarding_items, employee_documents, file_registry, compliance_documents

Hard rules:
  - SELECT only (readonly transaction)
  - --company is required
  - refuses multi-company / all-tenant unless --allow-unsafe-all-companies
  - never prints phones, emails, names, tokens, or storage URLs
  - never writes / backfills / mutates

Usage (staging):
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
    python3 ops/staging-phase7c-compliance-docs-audit.py --company WATHEFNI
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ---- type map (audit authority; mirrors current app behavior) ---------------

# Default Kuwait onboarding document item_ids (workflow keys).
ONBOARDING_DOCUMENT_ITEMS = {
    "civil_id",
    "passport",
    "personal_photo",
    "residency_iqama",
    "work_permit",
    "employment_contract",
    "offer_letter",
}

# Upload path currently dual-writes compliance for this allowlist only
# (see app.record_employee_document_receipt).
UPLOAD_SYNCED_COMPLIANCE_TYPES = {"civil_id", "passport", "medical", "education_cert"}

# Types that compliance UI / seed treat as first-class compliance docs.
COMPLIANCE_CANONICAL_TYPES = {
    "civil_id",
    "passport",
    "residency",
    "work_permit",
    "medical",
    "education_cert",
}

# Ambiguous / legacy aliases the audit should flag (not auto-merge).
AMBIGUOUS_TYPE_GROUPS = {
    "medical_family": ("medical", "medical_check"),
    "residency_family": ("residency", "residency_iqama"),
    "education_family": ("education_cert", "education", "certificate"),
}

# Soft onboarding expiry tasks that are NOT the compliance expiry store.
ONBOARDING_SOFT_EXPIRY_TASKS = {
    "civil_id_expiry",
    "passport_expiry",
    "residency_expiry",
    "work_permit_expiry",
}

EMPLOYEE_FILE_KINDS = ("onboarding_document", "compliance_document", "employee_document")

RECEIVED_LIKE = {"received", "submitted", "complete", "completed", "done", "uploaded"}
PENDING_LIKE = {"pending", "missing", "requested", "awaiting", ""}


def sample_id(employee_key: str) -> str:
    """Stable non-PII sample token (employee_key often embeds phone)."""
    digest = hashlib.sha256(str(employee_key).encode("utf-8")).hexdigest()[:12]
    return f"emp_{digest}"


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect_readonly():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.environ.get("WATHEFNI_DATABASE_URL")
    if not dsn:
        raise SystemExit("WATHEFNI_DATABASE_URL missing — set WATHEFNI_POSTGRES_ENV to staging env")
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    # Defense in depth: abort if anything tries to write.
    with conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        row = cur.fetchone() or {}
        flag = str(row.get("transaction_read_only") or next(iter(row.values()), "")).lower()
        if flag not in {"on", "true", "1"}:
            conn.close()
            raise SystemExit(f"refusing to continue: transaction_read_only={flag!r}")
    return conn


def fetchall(cur, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def add_sample(bucket: dict[str, Any], *, employee_key: str, document_type: str | None = None, extra: dict | None = None, limit: int = 5) -> None:
    samples = bucket.setdefault("samples", [])
    if len(samples) >= limit:
        return
    row = {"sample_id": sample_id(employee_key)}
    if document_type:
        row["document_type"] = document_type
    if extra:
        row.update(extra)
    samples.append(row)


def audit_company(cur, company: str, *, sample_limit: int = 5) -> dict[str, Any]:
    company = company.upper()

    employees = fetchall(
        cur,
        "SELECT employee_key, company_code FROM employees WHERE company_code=%s",
        (company,),
    )
    emp_keys = {str(e["employee_key"]) for e in employees}

    onboarding = fetchall(
        cur,
        """
        SELECT oi.employee_key, oi.item_id, oi.document_type, oi.status, oi.required,
               oi.item_type, oi.category, oi.owner
        FROM onboarding_items oi
        JOIN employees e ON e.employee_key = oi.employee_key
        WHERE e.company_code=%s
        """,
        (company,),
    )

    employee_docs = fetchall(
        cur,
        """
        SELECT document_id, employee_key, company_code, item_id, document_type, status,
               expiry_date, content_sha256, storage_status, storage_provider, external_file_id
        FROM employee_documents
        WHERE company_code=%s
           OR employee_key = ANY(%s)
        """,
        (company, list(emp_keys) or [""]),
    )
    # Prefer company_code match; still capture orphans keyed to this company's employees.
    employee_docs = [
        d
        for d in employee_docs
        if str(d.get("company_code") or "").upper() == company or str(d.get("employee_key")) in emp_keys
    ]

    compliance = fetchall(
        cur,
        """
        SELECT employee_key, company_code, document_type, status, expiry_date,
               days_until_expiry, renewal_status, label
        FROM compliance_documents
        WHERE company_code=%s
           OR employee_key = ANY(%s)
        """,
        (company, list(emp_keys) or [""]),
    )
    compliance = [
        d
        for d in compliance
        if str(d.get("company_code") or "").upper() == company or str(d.get("employee_key")) in emp_keys
    ]

    files = fetchall(
        cur,
        """
        SELECT file_id, company_code, subject_type, subject_key, file_kind, document_type,
               content_sha256, storage_status, metadata
        FROM file_registry
        WHERE company_code=%s
          AND subject_type='employee'
          AND file_kind = ANY(%s)
        """,
        (company, list(EMPLOYEE_FILE_KINDS)),
    )

    buckets: dict[str, dict[str, Any]] = {
        name: {"count": 0, "samples": []}
        for name in (
            "received_without_employee_doc",
            "employee_doc_without_received_item",
            "employee_doc_without_file",
            "orphan_employee_files",
            "compliance_missing_for_synced_received",
            "compliance_without_employee_doc",
            "expiry_status_conflicts",
            "null_expiry_on_received_compliance",
            "duplicate_employee_docs",
            "duplicate_compliance_docs",
            "ambiguous_type_mappings",
            "orphan_employee_keys",
            "company_mismatch",
        )
    }

    # Indexes
    onboard_by_emp_item: dict[tuple[str, str], dict] = {}
    for row in onboarding:
        key = (str(row["employee_key"]), str(row.get("item_id") or ""))
        onboard_by_emp_item[key] = row

    ed_by_emp_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    ed_by_emp_item: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in employee_docs:
        ek = str(row["employee_key"])
        dt = str(row.get("document_type") or "").strip()
        item = str(row.get("item_id") or "").strip()
        if dt:
            ed_by_emp_type[(ek, dt)].append(row)
        if item:
            ed_by_emp_item[(ek, item)].append(row)

    files_by_subject: dict[str, list[dict]] = defaultdict(list)
    files_by_subject_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in files:
        sk = str(row.get("subject_key") or "")
        files_by_subject[sk].append(row)
        dt = str(row.get("document_type") or "").strip()
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        item = str(meta.get("item_id") or "").strip()
        if dt:
            files_by_subject_type[(sk, dt)].append(row)
        if item:
            files_by_subject_type[(sk, item)].append(row)

    compliance_by_emp_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in compliance:
        ek = str(row["employee_key"])
        dt = str(row.get("document_type") or "").strip()
        if dt:
            compliance_by_emp_type[(ek, dt)].append(row)

    def bump(name: str, employee_key: str, document_type: str | None = None, **extra: Any) -> None:
        buckets[name]["count"] += 1
        add_sample(buckets[name], employee_key=employee_key, document_type=document_type, extra=extra or None, limit=sample_limit)

    # A. onboarding received without employee_documents
    for (ek, item_id), row in onboard_by_emp_item.items():
        status = str(row.get("status") or "").lower()
        item_type = str(row.get("item_type") or "").lower()
        if item_type and item_type not in {"document", "text"} and item_id not in ONBOARDING_DOCUMENT_ITEMS:
            continue
        if status not in RECEIVED_LIKE:
            continue
        # Only flag document-like / known document items
        if item_id not in ONBOARDING_DOCUMENT_ITEMS and item_type != "document":
            continue
        has_ed = bool(ed_by_emp_item.get((ek, item_id)) or ed_by_emp_type.get((ek, item_id)))
        if not has_ed:
            bump("received_without_employee_doc", ek, item_id, onboarding_status=status)

    # B. employee_documents without received/matching onboarding item
    for row in employee_docs:
        ek = str(row["employee_key"])
        item_id = str(row.get("item_id") or "").strip()
        dt = str(row.get("document_type") or "").strip()
        keys = [k for k in (item_id, dt) if k]
        matched = None
        for k in keys:
            matched = onboard_by_emp_item.get((ek, k))
            if matched:
                break
        if not matched:
            bump("employee_doc_without_received_item", ek, dt or item_id, reason="no_onboarding_item")
            continue
        status = str(matched.get("status") or "").lower()
        if status in PENDING_LIKE or status not in RECEIVED_LIKE:
            bump(
                "employee_doc_without_received_item",
                ek,
                dt or item_id,
                reason="onboarding_not_received",
                onboarding_status=status or "empty",
            )

    # C. employee_documents without file_registry
    for row in employee_docs:
        ek = str(row["employee_key"])
        dt = str(row.get("document_type") or "").strip()
        item_id = str(row.get("item_id") or "").strip()
        sha = str(row.get("content_sha256") or "").strip()
        candidates = files_by_subject.get(ek) or []
        linked = False
        for fr in candidates:
            fr_dt = str(fr.get("document_type") or "").strip()
            meta = fr.get("metadata") if isinstance(fr.get("metadata"), dict) else {}
            fr_item = str(meta.get("item_id") or "").strip()
            fr_sha = str(fr.get("content_sha256") or "").strip()
            if dt and fr_dt == dt:
                linked = True
                break
            if item_id and (fr_item == item_id or fr_dt == item_id):
                linked = True
                break
            if sha and fr_sha and sha == fr_sha:
                linked = True
                break
        if not linked:
            bump("employee_doc_without_file", ek, dt or item_id, storage_status=row.get("storage_status"))

    # D. orphan employee files (no employee_documents and no onboarding link)
    for fr in files:
        ek = str(fr.get("subject_key") or "")
        dt = str(fr.get("document_type") or "").strip()
        meta = fr.get("metadata") if isinstance(fr.get("metadata"), dict) else {}
        item_id = str(meta.get("item_id") or "").strip()
        has_ed = bool(
            (dt and ed_by_emp_type.get((ek, dt)))
            or (item_id and ed_by_emp_item.get((ek, item_id)))
            or (item_id and ed_by_emp_type.get((ek, item_id)))
        )
        has_oi = bool(
            (item_id and onboard_by_emp_item.get((ek, item_id)))
            or (dt and onboard_by_emp_item.get((ek, dt)))
        )
        if not has_ed and not has_oi:
            bump("orphan_employee_files", ek, dt or item_id or None, file_kind=fr.get("file_kind"))

    # E. compliance missing for upload-synced received docs
    for row in employee_docs:
        ek = str(row["employee_key"])
        dt = str(row.get("document_type") or "").strip()
        status = str(row.get("status") or "").lower()
        if dt not in UPLOAD_SYNCED_COMPLIANCE_TYPES:
            continue
        if status not in RECEIVED_LIKE and status not in {"", "stored"}:
            # still treat presence of employee_doc as receipt
            pass
        if not compliance_by_emp_type.get((ek, dt)):
            bump("compliance_missing_for_synced_received", ek, dt, employee_doc_status=status or "unknown")

    # F. compliance without employee_documents (excluding pure missing placeholders optional)
    for row in compliance:
        ek = str(row["employee_key"])
        dt = str(row.get("document_type") or "").strip()
        status = str(row.get("status") or "").lower()
        if status in {"missing"} and not ed_by_emp_type.get((ek, dt)):
            # seeded missing placeholder without receipt is expected; still countable separately via samples lightly
            continue
        if status in RECEIVED_LIKE or row.get("expiry_date") is not None:
            if not ed_by_emp_type.get((ek, dt)):
                # residency vs residency_iqama ambiguity
                aliases = []
                for group in AMBIGUOUS_TYPE_GROUPS.values():
                    if dt in group:
                        aliases = [a for a in group if a != dt]
                if any(ed_by_emp_type.get((ek, a)) for a in aliases):
                    bump("ambiguous_type_mappings", ek, dt, aliases=aliases, via="compliance_vs_employee_doc")
                else:
                    bump("compliance_without_employee_doc", ek, dt, compliance_status=status)

    # G. expiry/status conflicts between employee_documents and compliance
    for (ek, dt), ed_rows in ed_by_emp_type.items():
        cd_rows = compliance_by_emp_type.get((ek, dt)) or []
        if not cd_rows:
            continue
        ed = ed_rows[0]
        cd = cd_rows[0]
        ed_exp = ed.get("expiry_date")
        cd_exp = cd.get("expiry_date")
        if ed_exp and cd_exp and str(ed_exp) != str(cd_exp):
            bump("expiry_status_conflicts", ek, dt, kind="expiry_date_mismatch")
        ed_status = str(ed.get("status") or "").lower()
        cd_status = str(cd.get("status") or "").lower()
        if ed_status in RECEIVED_LIKE and cd_status in {"missing"}:
            bump("expiry_status_conflicts", ek, dt, kind="received_vs_missing")

    # Soft expiry task done vs compliance expiry null
    for (ek, item_id), row in onboard_by_emp_item.items():
        if item_id not in ONBOARDING_SOFT_EXPIRY_TASKS:
            continue
        if str(row.get("status") or "").lower() not in RECEIVED_LIKE | {"done", "complete", "completed"}:
            continue
        base = item_id.replace("_expiry", "")
        # residency_expiry -> residency / residency_iqama
        candidates = [base]
        if base == "residency":
            candidates.append("residency_iqama")
        for dt in candidates:
            for cd in compliance_by_emp_type.get((ek, dt)) or []:
                if cd.get("expiry_date") is None:
                    bump("expiry_status_conflicts", ek, dt, kind="soft_task_done_compliance_expiry_null")

    # H. null expiry on received compliance
    for row in compliance:
        status = str(row.get("status") or "").lower()
        if status in RECEIVED_LIKE or status in {"valid", "expiring_soon", "needs_review"}:
            if row.get("expiry_date") is None:
                bump(
                    "null_expiry_on_received_compliance",
                    str(row["employee_key"]),
                    str(row.get("document_type") or ""),
                    compliance_status=status,
                )

    # I. duplicates
    for (ek, dt), rows in ed_by_emp_type.items():
        if len(rows) > 1:
            bump("duplicate_employee_docs", ek, dt, duplicates=len(rows))
    for (ek, dt), rows in compliance_by_emp_type.items():
        if len(rows) > 1:
            bump("duplicate_compliance_docs", ek, dt, duplicates=len(rows))

    # J. ambiguous mappings present in same employee
    for ek in emp_keys:
        for group_name, aliases in AMBIGUOUS_TYPE_GROUPS.items():
            present = [a for a in aliases if ed_by_emp_type.get((ek, a)) or compliance_by_emp_type.get((ek, a)) or onboard_by_emp_item.get((ek, a))]
            if len(set(present)) >= 2:
                bump("ambiguous_type_mappings", ek, group_name, aliases=present, via="coexisting_aliases")

    # K. orphan employee keys
    for row in employee_docs + compliance:
        ek = str(row.get("employee_key") or "")
        if ek and ek not in emp_keys:
            bump("orphan_employee_keys", ek, str(row.get("document_type") or ""), store="documents")
    for fr in files:
        ek = str(fr.get("subject_key") or "")
        if ek and ek not in emp_keys:
            bump("orphan_employee_keys", ek, str(fr.get("document_type") or ""), store="file_registry")

    # L. company mismatch / cross-tenant
    for row in employee_docs:
        cc = str(row.get("company_code") or "").upper()
        ek = str(row["employee_key"])
        if cc and cc != company:
            bump("company_mismatch", ek, str(row.get("document_type") or ""), store="employee_documents", row_company=cc)
        if ek in emp_keys:
            # employee belongs to company but row company_code null/other
            if not cc:
                bump("company_mismatch", ek, str(row.get("document_type") or ""), store="employee_documents", row_company="NULL")
    for row in compliance:
        cc = str(row.get("company_code") or "").upper()
        ek = str(row["employee_key"])
        if cc and cc != company:
            bump("company_mismatch", ek, str(row.get("document_type") or ""), store="compliance_documents", row_company=cc)
        if ek in emp_keys and not cc:
            bump("company_mismatch", ek, str(row.get("document_type") or ""), store="compliance_documents", row_company="NULL")
    for fr in files:
        cc = str(fr.get("company_code") or "").upper()
        if cc and cc != company:
            bump("company_mismatch", str(fr.get("subject_key") or ""), str(fr.get("document_type") or ""), store="file_registry", row_company=cc)

    type_map = {
        "onboarding_document_item_ids": sorted(ONBOARDING_DOCUMENT_ITEMS),
        "upload_synced_compliance_types": sorted(UPLOAD_SYNCED_COMPLIANCE_TYPES),
        "compliance_canonical_types": sorted(COMPLIANCE_CANONICAL_TYPES),
        "ambiguous_groups": {k: list(v) for k, v in AMBIGUOUS_TYPE_GROUPS.items()},
        "soft_expiry_tasks": sorted(ONBOARDING_SOFT_EXPIRY_TASKS),
        "notes": [
            "Upload dual-write to compliance currently only for civil_id/passport/medical/education_cert.",
            "Default Kuwait uses residency_iqama while compliance seed/UI often uses residency.",
            "medical_check is an onboarding task; medical is a compliance/upload document type.",
            "personal_photo/employment_contract/bank_details are employee receipts but not compliance-synced.",
        ],
    }

    store_counts = {
        "employees": len(employees),
        "onboarding_items": len(onboarding),
        "onboarding_document_like": sum(
            1
            for r in onboarding
            if str(r.get("item_id")) in ONBOARDING_DOCUMENT_ITEMS or str(r.get("item_type") or "") == "document"
        ),
        "employee_documents": len(employee_docs),
        "compliance_documents": len(compliance),
        "file_registry_employee_docs": len(files),
    }

    return {
        "company_code": company,
        "read_only": True,
        "no_writes": True,
        "store_counts": store_counts,
        "type_map": type_map,
        "mismatches": {name: {"count": data["count"], "samples": data["samples"]} for name, data in buckets.items()},
        "mismatch_totals": {name: data["count"] for name, data in buckets.items()},
        "total_mismatch_events": sum(data["count"] for data in buckets.values()),
    }


WRITE_RULES = [
    "file_registry is the authority for binary/file identity (file_id, sha256, storage).",
    "onboarding_items remains workflow authority (pending/received/waived) and must not invent files.",
    "employee_documents is the durable receipt/metadata spine linking item_id/document_type to storage/extraction.",
    "compliance_documents is the expiry/renewal alert surface; derive from employee_documents for compliance-relevant types only.",
    "Never create compliance rows without a receipt or explicit HR action.",
    "Never overwrite a newer expiry with null/older extraction values.",
    "Never delete historical rows in reconciliation v1 — upsert/link only.",
    "Maintain an explicit item_id ↔ document_type ↔ compliance_type map; do not silently alias residency_iqama↔residency or medical_check↔medical without operator-visible migration.",
    "Keep onboarding soft expiry tasks as HR UX until a later sync from compliance_documents.",
    "All future write paths must be company-scoped, idempotent, and dry-run first.",
]


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Phase 7C compliance docs audit — {report['company_code']}",
        "",
        f"- read_only: `{report['read_only']}`",
        f"- no_writes: `{report['no_writes']}`",
        f"- total_mismatch_events: **{report['total_mismatch_events']}**",
        "",
        "## Store counts",
        "",
    ]
    for key, value in report["store_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Mismatch counts", ""])
    for key, value in report["mismatch_totals"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Samples (redacted)", ""])
    for key, payload in report["mismatches"].items():
        if not payload["samples"]:
            continue
        lines.append(f"### {key}")
        for sample in payload["samples"]:
            lines.append(f"- `{json.dumps(sample, sort_keys=True)}`")
        lines.append("")
    lines.extend(["## Proposed write rules (not implemented)", ""])
    for rule in WRITE_RULES:
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## Employee-app upload readiness recommendation",
            "",
            _recommendation(report),
            "",
        ]
    )
    return "\n".join(lines)


def _recommendation(report: dict[str, Any]) -> str:
    totals = report["mismatch_totals"]
    risky = (
        totals.get("employee_doc_without_file", 0)
        + totals.get("orphan_employee_files", 0)
        + totals.get("company_mismatch", 0)
        + totals.get("orphan_employee_keys", 0)
    )
    sync_gap = totals.get("compliance_missing_for_synced_received", 0) + totals.get("ambiguous_type_mappings", 0)
    if risky > 0:
        return (
            "**Not yet safe to expand employee-app document upload broadly.** "
            "Fix or contain file-link / tenant mismatch gaps first; otherwise uploads will widen orphan and cross-store drift."
        )
    if sync_gap > 0 or report["total_mismatch_events"] > 0:
        return (
            "**Conditionally safe for a closed pilot** if uploads stay on the existing receipt pipeline "
            "(file_registry + employee_documents + onboarding item update) and compliance dual-write gaps are accepted as known. "
            "Do not enable broad production employee-app upload until a write-path reconciliation plan is approved."
        )
    return (
        "**Low measured drift on this company.** Employee-app upload can be considered later for a controlled pilot, "
        "still behind `WATHEFNI_EMPLOYEE_APP` and after an explicit activation approval."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7C read-only compliance/document audit")
    parser.add_argument("--company", required=True, help="Required company_code scope (e.g. WATHEFNI)")
    parser.add_argument(
        "--postgres-env",
        default=os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"),
        help="Env file with WATHEFNI_DATABASE_URL (defaults to staging)",
    )
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--md-out", default="")
    parser.add_argument(
        "--allow-unsafe-all-companies",
        action="store_true",
        help="Unsafe: allow company=ALL (explicit opt-in only)",
    )
    args = parser.parse_args()

    company = str(args.company or "").strip().upper()
    if not company:
        raise SystemExit("--company is required")
    if company in {"ALL", "*", "ANY"} and not args.allow_unsafe_all_companies:
        raise SystemExit("refusing broad ALL-company audit without --allow-unsafe-all-companies")
    if company in {"ALL", "*", "ANY"}:
        raise SystemExit("ALL-company mode is intentionally unimplemented in Phase 7C; pass one company_code")

    load_env(Path(args.postgres_env))
    # Prefer staging path if caller did not override and staging env exists.
    staging_env = Path("/root/.openclaw/secrets/postgres.staging.env")
    if args.postgres_env.endswith("postgres.env") and staging_env.exists() and "staging" not in args.postgres_env:
        # Keep explicit prod env if user passed it; only nudge default messaging.
        pass

    conn = connect_readonly()
    try:
        with conn.cursor() as cur:
            # Prove company exists (read-only).
            cur.execute("SELECT 1 FROM companies WHERE company_code=%s LIMIT 1", (company,))
            if not cur.fetchone():
                raise SystemExit(f"company not found: {company}")
            cur.execute("SELECT current_setting('transaction_read_only') AS tro")
            tro = str((cur.fetchone() or {}).get("tro") or "")
            report = audit_company(cur, company, sample_limit=max(1, args.sample_limit))
            report["transaction_read_only"] = tro
            report["postgres_env"] = str(args.postgres_env)
            report["proposed_write_rules"] = WRITE_RULES
            report["employee_app_upload_recommendation"] = _recommendation(report)
    finally:
        conn.close()

    text_json = json.dumps(json_safe(report), indent=2, sort_keys=True)
    text_md = render_markdown(report)
    print(text_md)
    print("\n=== MACHINE REPORT (summary) ===")
    print(json.dumps({
        "company_code": report["company_code"],
        "store_counts": report["store_counts"],
        "mismatch_totals": report["mismatch_totals"],
        "total_mismatch_events": report["total_mismatch_events"],
        "read_only": report["read_only"],
        "no_writes": report["no_writes"],
        "transaction_read_only": report.get("transaction_read_only"),
    }, indent=2, sort_keys=True))

    if args.json_out:
        Path(args.json_out).write_text(text_json + "\n")
    if args.md_out:
        Path(args.md_out).write_text(text_md + "\n")

    print("NO_WRITES=true")
    print("READ_ONLY_TRANSACTION=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
