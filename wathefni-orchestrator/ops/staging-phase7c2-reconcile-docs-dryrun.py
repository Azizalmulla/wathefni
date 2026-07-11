#!/usr/bin/env python3
"""Phase 7C.2 — company-scoped dry-run document reconciliation planner.

Plans W1–W4 writes only. Never applies. Apply mode is hard-disabled.

Usage:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
    python3 ops/staging-phase7c2-reconcile-docs-dryrun.py \\
      --company P7C2STG01 \\
      --jsonl-out /tmp/p7c2-plan.jsonl \\
      --summary-out /tmp/p7c2-summary.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

OPS_ROOT = Path(__file__).resolve().parent
if str(OPS_ROOT) not in sys.path:
    sys.path.insert(0, str(OPS_ROOT))

from lib import doc_type_map as tm  # noqa: E402

ACTOR = "phase7c2-reconcile-dryrun"
SCHEMA_VERSION = 1


def sample_id(employee_key: str) -> str:
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


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def connect_readonly(*, allow_production_dsn: bool = False):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.environ.get("WATHEFNI_DATABASE_URL")
    if not dsn:
        raise SystemExit("WATHEFNI_DATABASE_URL missing — set WATHEFNI_POSTGRES_ENV")
    dsn_l = dsn.lower()
    looks_staging = "staging" in dsn_l or "wathefni_staging" in dsn_l
    # Bare production DB name is typically .../wathefni (not wathefni_staging).
    looks_prod = (not looks_staging) and (
        dsn_l.rstrip("/").endswith("/wathefni") or "/wathefni?" in dsn_l
    )
    if looks_prod and not allow_production_dsn:
        raise SystemExit(
            "refusing production-looking DSN without --allow-production-dsn "
            "(Phase 7C.2: no production runs)"
        )

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
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


def new_event(**kwargs: Any) -> dict[str, Any]:
    base = {
        "event_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "schema_version": SCHEMA_VERSION,
        "mode": "dry-run",
        "actor": ACTOR,
        "skip_reason": None,
        "guards": {"expiry_rule": None, "no_delete": True, "alias_merge": False},
        "evidence": {},
        "before": None,
        "after": None,
        "op": None,
        "table": None,
    }
    base.update(kwargs)
    return json_safe(base)


def prove_write_blocked(conn) -> dict[str, Any]:
    """Attempt UPDATE on planner connection; must fail."""
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE companies SET name=name WHERE false")
        return {"blocked": False, "error": None}
    except Exception as exc:  # noqa: BLE001 — proof probe
        return {"blocked": True, "error": type(exc).__name__, "detail": str(exc).splitlines()[0][:200]}


def plan_company(cur, company: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company = company.upper()
    events: list[dict[str, Any]] = []

    employees = fetchall(
        cur,
        "SELECT employee_key, company_code FROM employees WHERE company_code=%s",
        (company,),
    )
    emp_keys = {str(e["employee_key"]) for e in employees}

    onboarding = fetchall(
        cur,
        """
        SELECT oi.employee_key, oi.item_id, oi.document_type, oi.status, oi.item_type
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
               expiry_date, content_sha256, storage_status
        FROM employee_documents
        WHERE company_code=%s OR employee_key = ANY(%s)
        """,
        (company, list(emp_keys) or [""]),
    )
    compliance = fetchall(
        cur,
        """
        SELECT employee_key, company_code, document_type, status, expiry_date,
               days_until_expiry, renewal_status
        FROM compliance_documents
        WHERE company_code=%s OR employee_key = ANY(%s)
        """,
        (company, list(emp_keys) or [""]),
    )
    files = fetchall(
        cur,
        """
        SELECT file_id, company_code, subject_key, file_kind, document_type,
               content_sha256, storage_status, metadata
        FROM file_registry
        WHERE company_code=%s
          AND subject_type='employee'
          AND file_kind = ANY(%s)
        """,
        (company, list(tm.EMPLOYEE_FILE_KINDS)),
    )

    onboard_by_emp_item: dict[tuple[str, str], dict] = {}
    for row in onboarding:
        onboard_by_emp_item[(str(row["employee_key"]), str(row.get("item_id") or ""))] = row

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

    files_by_subject_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in files:
        sk = str(row.get("subject_key") or "")
        dt = str(row.get("document_type") or "").strip()
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        item = str(meta.get("item_id") or "").strip()
        if dt:
            files_by_subject_type[(sk, dt)].append(row)
        if item and item != dt:
            files_by_subject_type[(sk, item)].append(row)

    compliance_by_emp_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in compliance:
        dt = str(row.get("document_type") or "").strip()
        if dt:
            compliance_by_emp_type[(str(row["employee_key"]), dt)].append(row)

    # --- tenant / orphan flags (manual only) ---------------------------------
    for row in employee_docs + compliance:
        ek = str(row.get("employee_key") or "")
        cc = str(row.get("company_code") or "").upper()
        dt = str(row.get("document_type") or "")
        sid = sample_id(ek) if ek else "emp_unknown"
        if ek and ek not in emp_keys:
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="orphan_employee_keys",
                    action="report_orphan_employee_key",
                    decision="manual_only",
                    skip_reason=tm.SKIP_ORPHAN_EMPLOYEE,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={"store": "documents"},
                )
            )
        if ek in emp_keys and cc and cc != company:
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="company_mismatch",
                    action="report_tenant_mismatch",
                    decision="manual_only",
                    skip_reason=tm.SKIP_TENANT_MISMATCH,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={"row_company": cc},
                )
            )

    # --- ambiguous aliases ---------------------------------------------------
    for ek in emp_keys:
        sid = sample_id(ek)
        for group_name, aliases in tm.AMBIGUOUS_TYPE_GROUPS.items():
            present = [
                a
                for a in aliases
                if ed_by_emp_type.get((ek, a))
                or compliance_by_emp_type.get((ek, a))
                or onboard_by_emp_item.get((ek, a))
            ]
            if len(set(present)) >= 2:
                events.append(
                    new_event(
                        company_code=company,
                        sample_id=sid,
                        drift_class="ambiguous_type_mappings",
                        action="report_needs_operator_map",
                        decision="manual_only",
                        skip_reason=tm.SKIP_NEEDS_OPERATOR_MAP,
                        natural_key={"sample_id": sid, "group": group_name},
                        evidence={"aliases": present},
                        guards={"expiry_rule": None, "no_delete": True, "alias_merge": False},
                    )
                )

    # --- duplicates ----------------------------------------------------------
    for (ek, dt), rows in ed_by_emp_type.items():
        if len(rows) > 1:
            sid = sample_id(ek)
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="duplicate_employee_docs",
                    action="report_duplicates",
                    decision="manual_only",
                    skip_reason=tm.SKIP_DUPLICATE_ROWS,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={"duplicates": len(rows)},
                )
            )
    for (ek, dt), rows in compliance_by_emp_type.items():
        if len(rows) > 1:
            sid = sample_id(ek)
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="duplicate_compliance_docs",
                    action="report_duplicates",
                    decision="manual_only",
                    skip_reason=tm.SKIP_DUPLICATE_ROWS,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={"duplicates": len(rows)},
                )
            )

    # --- W1: ED present, onboarding pending ----------------------------------
    for row in employee_docs:
        ek = str(row["employee_key"])
        if ek not in emp_keys:
            continue
        cc = str(row.get("company_code") or "").upper()
        if cc and cc != company:
            continue
        item_id = str(row.get("item_id") or "").strip()
        dt = str(row.get("document_type") or "").strip()
        sid = sample_id(ek)
        keys = [k for k in (item_id, dt) if k]
        matched = None
        matched_item = None
        for k in keys:
            matched = onboard_by_emp_item.get((ek, k))
            if matched:
                matched_item = k
                break
        if not matched:
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="employee_doc_without_received_item",
                    action="skip_onboarding_item_missing",
                    decision="skip",
                    skip_reason=tm.SKIP_ONBOARDING_MISSING,
                    natural_key={"sample_id": sid, "document_type": dt or item_id},
                    evidence={"has_employee_document": True},
                )
            )
            continue
        status = str(matched.get("status") or "").lower()
        if status in tm.RECEIVED_LIKE:
            # Already consistent — no event (idempotent empty plan for this key).
            continue
        if status in tm.PENDING_LIKE or status not in tm.RECEIVED_LIKE:
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="employee_doc_without_received_item",
                    action="mark_onboarding_received",
                    decision="plan",
                    table="onboarding_items",
                    op="UPDATE",
                    natural_key={"sample_id": sid, "item_id": matched_item},
                    before={"status": status or "empty"},
                    after={"status": "received"},
                    evidence={
                        "has_employee_document": True,
                        "onboarding_status": status or "empty",
                    },
                )
            )

    # --- W2 / skips: compliance without ED -----------------------------------
    for row in compliance:
        ek = str(row["employee_key"])
        if ek not in emp_keys:
            continue
        cc = str(row.get("company_code") or "").upper()
        if cc and cc != company:
            continue
        dt = str(row.get("document_type") or "").strip()
        status = str(row.get("status") or "").lower()
        sid = sample_id(ek)
        if not dt:
            continue
        if status in {"missing"} and as_date(row.get("expiry_date")) is None:
            continue
        if status not in tm.COMPLIANCE_ACTIVE_LIKE and as_date(row.get("expiry_date")) is None:
            continue
        if ed_by_emp_type.get((ek, dt)):
            continue
        # Ambiguous alias with ED under another key → operator map only
        aliases = []
        for group in tm.AMBIGUOUS_TYPE_GROUPS.values():
            if dt in group:
                aliases = [a for a in group if a != dt]
        if any(ed_by_emp_type.get((ek, a)) for a in aliases):
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="ambiguous_type_mappings",
                    action="report_needs_operator_map",
                    decision="manual_only",
                    skip_reason=tm.SKIP_NEEDS_OPERATOR_MAP,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={"aliases": aliases, "via": "compliance_vs_employee_doc"},
                )
            )
            continue

        file_rows = files_by_subject_type.get((ek, dt)) or []
        supported = [f for f in file_rows if str(f.get("file_kind") or "") in tm.EMPLOYEE_FILE_KINDS]
        if supported:
            fr = supported[0]
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="compliance_without_employee_doc",
                    action="insert_employee_document_from_file",
                    decision="plan",
                    table="employee_documents",
                    op="INSERT",
                    natural_key={"sample_id": sid, "document_type": dt},
                    before=None,
                    after={
                        "document_type": dt,
                        "item_id": dt if dt in tm.ONBOARDING_DOCUMENT_ITEMS else None,
                        "status": "received",
                        "content_sha256": (str(fr.get("content_sha256") or "")[:16] + "…")
                        if fr.get("content_sha256")
                        else None,
                        "storage_status": fr.get("storage_status"),
                        "expiry_date": as_date(row.get("expiry_date")).isoformat()
                        if as_date(row.get("expiry_date"))
                        else None,
                    },
                    evidence={
                        "has_employee_document": False,
                        "has_file_registry": True,
                        "file_kind": fr.get("file_kind"),
                        "compliance_status": status,
                    },
                )
            )
        else:
            reason = tm.SKIP_COMPLIANCE_ORPHAN_NO_FILE if not file_rows else tm.SKIP_NO_SUPPORTED_FILE
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="compliance_without_employee_doc",
                    action="skip_compliance_orphan_no_file",
                    decision="skip",
                    skip_reason=reason,
                    natural_key={"sample_id": sid, "document_type": dt},
                    evidence={
                        "has_employee_document": False,
                        "has_file_registry": bool(file_rows),
                        "compliance_status": status,
                    },
                )
            )

    # --- W3 / W4: expiry sync + null fill ------------------------------------
    seen_pairs: set[tuple[str, str]] = set()
    for (ek, dt), ed_rows in list(ed_by_emp_type.items()) + [
        (k, []) for k in compliance_by_emp_type.keys() if k not in ed_by_emp_type
    ]:
        if (ek, dt) in seen_pairs or ek not in emp_keys:
            continue
        seen_pairs.add((ek, dt))
        sid = sample_id(ek)
        ed = (ed_by_emp_type.get((ek, dt)) or [None])[0]
        cd = (compliance_by_emp_type.get((ek, dt)) or [None])[0]
        if not ed or not cd:
            # W4 only needs both for fill-from-ed; null compliance without ED handled above
            if cd and not ed:
                continue
            if ed and not cd:
                continue
            continue

        ed_exp = as_date(ed.get("expiry_date"))
        cd_exp = as_date(cd.get("expiry_date"))
        cd_status = str(cd.get("status") or "").lower()

        # W4: received-like compliance with null expiry
        if cd_exp is None and (cd_status in tm.COMPLIANCE_ACTIVE_LIKE or cd_status in tm.RECEIVED_LIKE):
            if ed_exp is not None:
                days = (ed_exp - date.today()).days
                events.append(
                    new_event(
                        company_code=company,
                        sample_id=sid,
                        drift_class="null_expiry_on_received_compliance",
                        action="fill_compliance_expiry_from_ed",
                        decision="plan",
                        table="compliance_documents",
                        op="UPDATE",
                        natural_key={"sample_id": sid, "document_type": dt},
                        before={"expiry_date": None, "status": cd_status},
                        after={"expiry_date": ed_exp.isoformat(), "days_until_expiry": days},
                        evidence={"has_employee_document": True, "source": "employee_documents"},
                        guards={"expiry_rule": "fill_from_ed_non_null", "no_delete": True, "alias_merge": False},
                    )
                )
            else:
                events.append(
                    new_event(
                        company_code=company,
                        sample_id=sid,
                        drift_class="null_expiry_on_received_compliance",
                        action="skip_null_expiry_no_source",
                        decision="skip",
                        skip_reason=tm.SKIP_NULL_EXPIRY_NO_SOURCE,
                        natural_key={"sample_id": sid, "document_type": dt},
                        evidence={"has_employee_document": True, "compliance_status": cd_status},
                    )
                )

        # W3: both non-null and differ
        if ed_exp is not None and cd_exp is not None and ed_exp != cd_exp:
            winner = ed_exp if ed_exp >= cd_exp else cd_exp
            winner_source = "employee_documents" if ed_exp >= cd_exp else "compliance_documents"
            # Plan updates for lagging store(s)
            if ed_exp < winner:
                events.append(
                    new_event(
                        company_code=company,
                        sample_id=sid,
                        drift_class="expiry_status_conflicts",
                        action="sync_expiry",
                        decision="plan",
                        table="employee_documents",
                        op="UPDATE",
                        natural_key={"sample_id": sid, "document_type": dt},
                        before={"expiry_date": ed_exp.isoformat()},
                        after={"expiry_date": winner.isoformat()},
                        evidence={"winner_source": winner_source},
                        guards={"expiry_rule": "newer_non_null_wins", "no_delete": True, "alias_merge": False},
                    )
                )
            if cd_exp < winner:
                days = (winner - date.today()).days
                events.append(
                    new_event(
                        company_code=company,
                        sample_id=sid,
                        drift_class="expiry_status_conflicts",
                        action="sync_expiry",
                        decision="plan",
                        table="compliance_documents",
                        op="UPDATE",
                        natural_key={"sample_id": sid, "document_type": dt},
                        before={"expiry_date": cd_exp.isoformat()},
                        after={"expiry_date": winner.isoformat(), "days_until_expiry": days},
                        evidence={"winner_source": winner_source},
                        guards={"expiry_rule": "newer_non_null_wins", "no_delete": True, "alias_merge": False},
                    )
                )
            # Explicit skip for older→newer direction
            older_source = "compliance_documents" if winner_source == "employee_documents" else "employee_documents"
            older_date = cd_exp if older_source == "compliance_documents" else ed_exp
            events.append(
                new_event(
                    company_code=company,
                    sample_id=sid,
                    drift_class="expiry_status_conflicts",
                    action="skip_expiry_older_than_existing",
                    decision="skip",
                    skip_reason=tm.SKIP_EXPIRY_OLDER,
                    natural_key={"sample_id": sid, "document_type": dt},
                    before={"candidate_expiry": older_date.isoformat(), "existing_expiry": winner.isoformat()},
                    after=None,
                    evidence={"rejected_source": older_source, "winner_source": winner_source},
                    guards={"expiry_rule": "newer_non_null_wins", "no_delete": True, "alias_merge": False},
                )
            )

    # Deduplicate already_consistent noise: keep only when no plan for same key
    # (already emitted per ED; fine for verifier case 11 filtering by sample)

    summary = build_summary(company, events)
    return events, summary


def build_summary(company: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    by_action: Counter[str] = Counter()
    by_drift: Counter[str] = Counter()
    by_skip: Counter[str] = Counter()
    planned = skips = manual = 0
    for ev in events:
        decision = ev.get("decision")
        action = str(ev.get("action") or "")
        drift = str(ev.get("drift_class") or "")
        by_action[action] += 1
        by_drift[drift] += 1
        if decision == "plan":
            planned += 1
        elif decision == "skip":
            skips += 1
            if ev.get("skip_reason"):
                by_skip[str(ev["skip_reason"])] += 1
        elif decision == "manual_only":
            manual += 1
            if ev.get("skip_reason"):
                by_skip[str(ev["skip_reason"])] += 1
    return {
        "company_code": company,
        "mode": "dry-run",
        "read_only": True,
        "no_writes": True,
        "apply_enabled": False,
        "planned_writes": planned,
        "skips": skips,
        "manual_only": manual,
        "event_count": len(events),
        "by_action": dict(by_action),
        "by_drift_class": dict(by_drift),
        "by_skip_reason": dict(by_skip),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7C.2 dry-run reconcile planner")
    parser.add_argument("--company", required=True, help="Required company_code scope")
    parser.add_argument(
        "--mode",
        default="dry-run",
        choices=["dry-run", "apply"],
        help="dry-run (default). apply is hard-disabled in Phase 7C.2",
    )
    parser.add_argument(
        "--postgres-env",
        default=os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"),
    )
    parser.add_argument("--jsonl-out", default="")
    parser.add_argument("--summary-out", default="")
    parser.add_argument("--confirm-company", default="")
    parser.add_argument("--i-understand-writes", action="store_true")
    parser.add_argument("--allow-production-dsn", action="store_true")
    parser.add_argument("--prove-write-probe", action="store_true", help="Attempt UPDATE; expect block")
    args = parser.parse_args()

    company = str(args.company or "").strip().upper()
    if not company:
        raise SystemExit("--company is required")
    if company in {"ALL", "*", "ANY"}:
        raise SystemExit("refusing broad ALL-company run (Phase 7C.2 company-scoped only)")

    if args.mode == "apply":
        # Confirm flags must NOT unlock writes in 7C.2.
        raise SystemExit(
            "apply mode disabled until Phase 7C.3 approval "
            "(dry-run planner only in Phase 7C.2); "
            f"confirm_company={bool(args.confirm_company)} "
            f"i_understand_writes={bool(args.i_understand_writes)}"
        )

    load_env(Path(args.postgres_env))
    conn = connect_readonly(allow_production_dsn=bool(args.allow_production_dsn))
    write_probe: dict[str, Any] | None = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok FROM companies WHERE company_code=%s LIMIT 1", (company,))
            if not cur.fetchone():
                raise SystemExit(f"company not found: {company}")
            cur.execute("SELECT current_setting('transaction_read_only') AS tro")
            tro = str((cur.fetchone() or {}).get("tro") or "")
            events, summary = plan_company(cur, company)
            summary["transaction_read_only"] = tro
            summary["postgres_env"] = str(args.postgres_env)
        if args.prove_write_probe:
            write_probe = prove_write_blocked(conn)
            summary["write_probe"] = write_probe
            if not write_probe.get("blocked"):
                raise SystemExit("write probe unexpectedly succeeded on readonly connection")
    finally:
        conn.close()

    jsonl_text = "\n".join(json.dumps(ev, sort_keys=True) for ev in events)
    if events:
        jsonl_text += "\n"
    summary_text = json.dumps(summary, indent=2, sort_keys=True)

    if args.jsonl_out:
        Path(args.jsonl_out).write_text(jsonl_text)
    if args.summary_out:
        Path(args.summary_out).write_text(summary_text + "\n")

    print(summary_text)
    print("NO_WRITES=true")
    print("READ_ONLY_TRANSACTION=true")
    print("APPLY_ENABLED=false")
    if write_probe is not None:
        print(f"WRITE_PROBE_BLOCKED={str(write_probe.get('blocked')).lower()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
