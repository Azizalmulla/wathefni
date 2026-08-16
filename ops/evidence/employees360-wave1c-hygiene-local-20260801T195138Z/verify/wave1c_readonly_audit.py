#!/usr/bin/env python3
"""Employees 360 Wave 1C — READ-ONLY production hygiene audit.

SELECT only. Never INSERT/UPDATE/DELETE/DDL.
Classifies known null employment_status rows and P0-DUP orphan messages,
rescans integrity after Wave 1, and emits a Wave 2 migration-readiness map.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

OUT = Path(os.environ.get("WAVE1C_OUT_DIR", "/tmp/employees360-wave1c-audit"))
OUT.mkdir(parents=True, exist_ok=True)

KNOWN_NULLS = ("WATHEFNI-96597727743", "WATHEFNI-96550252254")
KNOWN_ORPHAN_KEY = "WATHEFNI-P0-DUP-1"
COMPANY = "WATHEFNI"


def load_env() -> None:
    env_path = Path(os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env"))
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    url = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("missing WATHEFNI_DATABASE_URL")
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def q(cur, sql: str, params=None) -> list[dict[str, Any]]:
    cur.execute(sql, params or ())
    rows = cur.fetchall() or []
    return [dict(r) for r in rows]


def table_exists(cur, name: str) -> bool:
    return bool(
        q(
            cur,
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (name,),
        )
    )


def cols(cur, table: str) -> set[str]:
    return {
        r["column_name"]
        for r in q(
            cur,
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
    }


def redact_phone(p: Any) -> str:
    s = re.sub(r"\D", "", str(p or ""))
    if len(s) <= 4:
        return "***"
    return f"***{s[-4:]}"


def redact_email(e: Any) -> str:
    s = str(e or "").strip()
    if not s or "@" not in s:
        return ""
    local, _, domain = s.partition("@")
    return f"{local[:1]}***@{domain}"


def serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, memoryview):
        return bytes(obj).hex()
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).hex()
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, tuple):
        return [serialize(v) for v in obj]
    return obj


def dump_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(serialize(obj), indent=2, default=str) + "\n")


def integrity_orphan_scan(cur) -> dict[str, Any]:
    """Mirror Wave 1 INTEGRITY_SCAN_SPECS against live catalog."""
    specs = [
        ("attendance_records", "company_employee"),
        ("leave_requests", "company_employee"),
        ("shift_assignments", "company_employee"),
        ("payroll_timesheets", "company_employee"),
        ("employee_availability_requests", "company_employee"),
        ("compliance_documents", "company_employee"),
        ("employee_messages", "company_employee"),
        ("employee_sessions", "company_employee"),
        ("employee_app_invites", "company_employee"),
        ("employee_status_changes", "company_employee"),
        ("employee_org_assignments", "company_employee"),
        ("hr_tasks", "company_employee"),
        ("document_storage_operations", "company_employee"),
        ("file_registry", "company_employee"),
        ("onboarding_items", "employee_only"),
        ("employee_documents", "employee_only"),
    ]
    tables: dict[str, Any] = {}
    total = 0
    for table, mode in specs:
        if not table_exists(cur, table):
            tables[table] = {"present": False, "orphans": 0, "samples": [], "mode": mode}
            continue
        c = cols(cur, table)
        if mode == "company_employee" and {"company_code", "employee_key"} <= c:
            rows = q(
                cur,
                f"""
                SELECT t.company_code, t.employee_key, count(*)::bigint AS n
                FROM {table} t
                LEFT JOIN employees e
                  ON e.employee_key = t.employee_key AND e.company_code = t.company_code
                WHERE t.employee_key IS NOT NULL AND t.employee_key <> ''
                  AND e.employee_key IS NULL
                GROUP BY t.company_code, t.employee_key
                ORDER BY n DESC
                LIMIT 20
                """,
            )
        elif mode == "employee_only" and "employee_key" in c:
            rows = q(
                cur,
                f"""
                SELECT t.employee_key, count(*)::bigint AS n
                FROM {table} t
                LEFT JOIN employees e ON e.employee_key = t.employee_key
                WHERE t.employee_key IS NOT NULL AND t.employee_key <> ''
                  AND e.employee_key IS NULL
                GROUP BY t.employee_key
                ORDER BY n DESC
                LIMIT 20
                """,
            )
        else:
            tables[table] = {"present": True, "orphans": 0, "samples": [], "mode": mode, "skipped": "columns"}
            continue
        orphans = int(sum(int(r["n"]) for r in rows))
        total += orphans
        tables[table] = {"present": True, "orphans": orphans, "samples": rows, "mode": mode}
    return {"total_orphans": total, "ok": total == 0, "tables": tables}


def classify_null_employee(cur, employee_key: str) -> dict[str, Any]:
    emp_rows = q(cur, "SELECT * FROM employees WHERE employee_key=%s", (employee_key,))
    if not emp_rows:
        return {"employee_key": employee_key, "classification": "missing", "proposed_status": None, "confidence": "none", "evidence": {}}
    emp = emp_rows[0]
    phone = emp.get("phone")
    app_key = emp.get("app_key")
    evidence: dict[str, Any] = {
        "employee": {
            "employee_key": emp.get("employee_key"),
            "company_code": emp.get("company_code"),
            "phone_redacted": redact_phone(phone),
            "email_redacted": redact_email(emp.get("email")),
            "name": emp.get("name"),
            "position_title": emp.get("position_title"),
            "employment_status": emp.get("employment_status"),
            "onboarding_status": emp.get("onboarding_status"),
            "app_key": app_key,
            "hire_date": emp.get("hire_date"),
            "start_date": emp.get("start_date"),
            "created_at": emp.get("created_at"),
            "updated_at": emp.get("updated_at"),
            "documents_pending": emp.get("documents_pending"),
            "documents_complete": emp.get("documents_complete"),
            "compliance_status": emp.get("compliance_status"),
            "profile_keys": sorted((emp.get("profile") or {}).keys()) if isinstance(emp.get("profile"), dict) else [],
            "raw_json_keys": sorted((emp.get("raw_json") or {}).keys()) if isinstance(emp.get("raw_json"), dict) else [],
        }
    }

    # Application / hiring linkage
    if app_key and table_exists(cur, "applications"):
        acols = cols(cur, "applications")
        select = ["app_key"]
        for c in ("status", "stage", "company_code", "phone", "email", "full_name", "name", "created_at", "updated_at", "hired_at", "decision"):
            if c in acols:
                select.append(c)
        apps = q(cur, f"SELECT {', '.join(select)} FROM applications WHERE app_key=%s", (app_key,))
        evidence["applications"] = [
            {
                **{k: (redact_phone(v) if k == "phone" else redact_email(v) if k == "email" else v) for k, v in a.items()},
            }
            for a in apps
        ]
    else:
        evidence["applications"] = []

    if table_exists(cur, "candidates") and phone:
        # best-effort phone match
        cc = cols(cur, "candidates")
        if "phone" in cc:
            cands = q(
                cur,
                """
                SELECT candidate_id, phone, email, full_name, created_at
                FROM candidates
                WHERE regexp_replace(coalesce(phone,''), '\\D', '', 'g') = regexp_replace(%s, '\\D', '', 'g')
                LIMIT 5
                """,
                (str(phone),),
            ) if "candidate_id" in cc else q(
                cur,
                """
                SELECT phone, email, name, created_at
                FROM candidates
                WHERE regexp_replace(coalesce(phone,''), '\\D', '', 'g') = regexp_replace(%s, '\\D', '', 'g')
                LIMIT 5
                """,
                (str(phone),),
            )
            evidence["candidates_by_phone"] = [
                {k: (redact_phone(v) if k == "phone" else redact_email(v) if k == "email" else v) for k, v in c.items()}
                for c in cands
            ]

    # Child activity
    for table, label in [
        ("onboarding_items", "onboarding_items"),
        ("compliance_documents", "compliance_documents"),
        ("attendance_records", "attendance_records"),
        ("leave_requests", "leave_requests"),
        ("shift_assignments", "shift_assignments"),
        ("employee_messages", "employee_messages"),
        ("employee_status_changes", "employee_status_changes"),
        ("employee_documents", "employee_documents"),
        ("file_registry", "file_registry"),
        ("hr_tasks", "hr_tasks"),
    ]:
        if not table_exists(cur, table):
            evidence[label] = {"present": False, "count": 0, "samples": []}
            continue
        c = cols(cur, table)
        if "employee_key" not in c:
            evidence[label] = {"present": True, "count": 0, "samples": [], "note": "no employee_key"}
            continue
        if "company_code" in c:
            cnt = q(cur, f"SELECT count(*)::bigint AS n FROM {table} WHERE company_code=%s AND employee_key=%s", (COMPANY, employee_key))
            samples = q(cur, f"SELECT * FROM {table} WHERE company_code=%s AND employee_key=%s ORDER BY 1 DESC LIMIT 5", (COMPANY, employee_key))
        else:
            cnt = q(cur, f"SELECT count(*)::bigint AS n FROM {table} WHERE employee_key=%s", (employee_key,))
            samples = q(cur, f"SELECT * FROM {table} WHERE employee_key=%s ORDER BY 1 DESC LIMIT 5", (employee_key,))
        # redact sample phones/emails lightly by dropping bulky blobs
        slim = []
        for s in samples:
            slim.append({k: v for k, v in s.items() if k not in ("raw_json", "profile", "payload", "body", "content") or True})
            # keep but truncate large json
            for big in ("raw_json", "profile", "payload", "body", "content", "message_body"):
                if big in slim[-1] and slim[-1][big] is not None:
                    text = json.dumps(slim[-1][big], default=str)
                    if len(text) > 400:
                        slim[-1][big] = text[:400] + "…"
        evidence[label] = {"present": True, "count": int(cnt[0]["n"]), "samples": slim}

    # Admin audits mentioning this employee
    audit_hits = []
    for audit_table in ("admin_audit_events", "dashboard_audit_events", "audit_events"):
        if not table_exists(cur, audit_table):
            continue
        ac = cols(cur, audit_table)
        if "target" in ac:
            audit_hits.extend(
                q(
                    cur,
                    f"""
                    SELECT * FROM {audit_table}
                    WHERE target = %s OR target LIKE %s OR coalesce(details::text,'') LIKE %s
                    ORDER BY 1 DESC LIMIT 20
                    """,
                    (employee_key, f"%{employee_key}%", f"%{employee_key}%"),
                )
            )
        elif "details" in ac:
            audit_hits.extend(
                q(
                    cur,
                    f"""
                    SELECT * FROM {audit_table}
                    WHERE coalesce(details::text,'') LIKE %s
                    ORDER BY 1 DESC LIMIT 20
                    """,
                    (f"%{employee_key}%",),
                )
            )
    evidence["audit_hits_count"] = len(audit_hits)
    evidence["audit_hits"] = []
    for a in audit_hits[:15]:
        slim = {k: a.get(k) for k in a if k not in ("details",) or True}
        if "details" in slim and slim["details"] is not None:
            text = json.dumps(slim["details"], default=str)
            slim["details"] = text[:500] + ("…" if len(text) > 500 else "")
        evidence["audit_hits"].append(slim)

    # Classification rules — evidence-driven, no guessing
    status_raw = emp.get("employment_status")
    reasons: list[str] = []
    proposed = None
    confidence = "none"
    classification = "unresolved_null_status"

    if status_raw is not None and str(status_raw).strip() != "":
        classification = "already_set"
        proposed = str(status_raw).strip().lower()
        confidence = "high"
        reasons.append(f"employment_status already set to {proposed!r}")
    else:
        reasons.append("employment_status IS NULL")
        has_app = bool(app_key)
        onboarding = str(emp.get("onboarding_status") or "").strip().lower()
        att = evidence.get("attendance_records", {}).get("count", 0)
        shifts = evidence.get("shift_assignments", {}).get("count", 0)
        leave = evidence.get("leave_requests", {}).get("count", 0)
        msgs = evidence.get("employee_messages", {}).get("count", 0)
        status_changes = evidence.get("employee_status_changes", {}).get("count", 0)
        apps = evidence.get("applications") or []
        app_statuses = [str(a.get("status") or a.get("stage") or "").lower() for a in apps]

        if status_changes:
            reasons.append(f"found {status_changes} employee_status_changes — inspect before backfill")
            classification = "needs_manual_review"
            confidence = "low"
        elif any("left" in s or "reject" in s or "withdraw" in s for s in app_statuses):
            reasons.append(f"application statuses suggest possible non-active: {app_statuses}")
            classification = "needs_manual_review"
            confidence = "low"
        elif has_app or onboarding in ("in_progress", "pending", "complete", "completed") or att or shifts or leave or msgs:
            # Positive evidence of ongoing employment relationship; code already treats null as active.
            proposed = "active"
            confidence = "high" if (has_app and onboarding) or att or shifts else "medium"
            classification = "null_should_be_active"
            if has_app:
                reasons.append(f"hire-linked via app_key={app_key}")
            if onboarding:
                reasons.append(f"onboarding_status={onboarding!r}")
            if att:
                reasons.append(f"attendance_records={att}")
            if shifts:
                reasons.append(f"shift_assignments={shifts}")
            if leave:
                reasons.append(f"leave_requests={leave}")
            if msgs:
                reasons.append(f"employee_messages={msgs}")
            reasons.append("no employee_status_changes / left markers found")
            reasons.append("runtime already coerces null→active via coalesce/canonical helpers")
        else:
            classification = "needs_manual_review"
            confidence = "none"
            reasons.append("insufficient hiring/onboarding/activity evidence to set status without guessing")

    return {
        "employee_key": employee_key,
        "classification": classification,
        "proposed_status": proposed,
        "confidence": confidence,
        "reasons": reasons,
        "evidence": evidence,
    }


def classify_orphan_messages(cur) -> dict[str, Any]:
    rows = q(
        cur,
        """
        SELECT *
        FROM employee_messages
        WHERE company_code=%s AND employee_key=%s
        ORDER BY created_at NULLS LAST, updated_at NULLS LAST
        """,
        (COMPANY, KNOWN_ORPHAN_KEY),
    ) if table_exists(cur, "employee_messages") else []

    # Does any employee row exist for this key?
    emp = q(cur, "SELECT employee_key, phone, name, employment_status FROM employees WHERE employee_key=%s", (KNOWN_ORPHAN_KEY,))
    # Any applications / other refs?
    refs: dict[str, Any] = {"employees": emp, "other_tables": {}}
    for table in [
        "applications",
        "attendance_records",
        "onboarding_items",
        "compliance_documents",
        "leave_requests",
        "shift_assignments",
        "employee_documents",
        "file_registry",
        "employee_status_changes",
        "employee_sessions",
        "employee_app_invites",
    ]:
        if not table_exists(cur, table):
            continue
        c = cols(cur, table)
        if "employee_key" not in c:
            # applications may use different keys
            if table == "applications" and "app_key" in c:
                refs["other_tables"][table] = q(cur, "SELECT count(*)::bigint AS n FROM applications WHERE app_key=%s OR coalesce(raw_json::text,'') LIKE %s", (KNOWN_ORPHAN_KEY, f"%{KNOWN_ORPHAN_KEY}%"))
            continue
        if "company_code" in c:
            refs["other_tables"][table] = q(cur, f"SELECT count(*)::bigint AS n FROM {table} WHERE company_code=%s AND employee_key=%s", (COMPANY, KNOWN_ORPHAN_KEY))
        else:
            refs["other_tables"][table] = q(cur, f"SELECT count(*)::bigint AS n FROM {table} WHERE employee_key=%s", (KNOWN_ORPHAN_KEY,))

    # Look for P0 / synthetic markers in message content
    slim_rows = []
    synthetic_markers = []
    for r in rows:
        item = {k: r.get(k) for k in r}
        for big in ("raw_json", "payload", "body", "content", "message_body", "text"):
            if big in item and item[big] is not None:
                text = json.dumps(item[big], default=str)
                item[big] = text[:600] + ("…" if len(text) > 600 else "")
                low = text.lower()
                for marker in ("p0-dup", "synthetic", "smoke", "test", "duplicate", "harness"):
                    if marker in low or marker in KNOWN_ORPHAN_KEY.lower():
                        synthetic_markers.append(marker)
        slim_rows.append(item)

    key_is_synthetic = bool(re.search(r"P0-DUP|SYNTH|TEST|SMOKE", KNOWN_ORPHAN_KEY, re.I))
    no_employee = len(emp) == 0
    other_nonzero = {
        t: int(v[0]["n"]) for t, v in refs["other_tables"].items() if v and int(v[0]["n"]) > 0
    }

    if key_is_synthetic and no_employee and not other_nonzero:
        classification = "synthetic_orphan_quarantine"
        confidence = "high"
        reasons = [
            f"employee_key {KNOWN_ORPHAN_KEY!r} matches synthetic naming pattern",
            "no employees row exists for this key",
            "no valid application/attendance/onboarding/doc references found",
            f"{len(rows)} orphan employee_messages rows remain",
        ]
    elif key_is_synthetic and no_employee:
        classification = "synthetic_orphan_quarantine_with_extra_refs"
        confidence = "medium"
        reasons = [
            "synthetic key pattern + missing employee",
            f"extra refs present: {other_nonzero}",
        ]
    elif no_employee:
        classification = "orphan_needs_manual_review"
        confidence = "low"
        reasons = ["employee missing but key not clearly synthetic"]
    else:
        classification = "not_orphan"
        confidence = "high"
        reasons = ["employee row exists"]

    return {
        "employee_key": KNOWN_ORPHAN_KEY,
        "message_count": len(rows),
        "messages": slim_rows,
        "classification": classification,
        "confidence": confidence,
        "reasons": reasons,
        "synthetic_markers": sorted(set(synthetic_markers + (["key:P0-DUP"] if key_is_synthetic else []))),
        "references": serialize(refs),
        "proposed_remediation": "quarantine_archive" if classification.startswith("synthetic_orphan") else "manual_review",
    }


def migration_readiness_map(cur) -> dict[str, Any]:
    """Map every employee_key to future person/employment/assignment identifiers.

    Does NOT create schema. Emits deterministic UUIDv5-ready material + linkage facts
    so Wave 2 can cut over without guessing.
    """
    NS = uuid.UUID("6b1c0f3a-9d2e-4a7b-8c5d-1e2f3a4b5c6d")  # stable Wathefni employees360 namespace
    employees = q(cur, "SELECT * FROM employees WHERE company_code=%s ORDER BY employee_key", (COMPANY,))
    mapping = []
    for emp in employees:
        key = emp["employee_key"]
        phone_digits = re.sub(r"\D", "", str(emp.get("phone") or ""))
        email = str(emp.get("email") or "").strip().lower()
        # person identity preference: phone canonical within company, else email, else employee_key
        if phone_digits:
            person_seed = f"person:{COMPANY}:phone:{phone_digits}"
        elif email:
            person_seed = f"person:{COMPANY}:email:{email}"
        else:
            person_seed = f"person:{COMPANY}:employee_key:{key}"
        person_id = str(uuid.uuid5(NS, person_seed))
        employment_id = str(uuid.uuid5(NS, f"employment:{COMPANY}:{key}"))
        # default primary assignment = employment itself until org assignments exist
        assignment_id = str(uuid.uuid5(NS, f"assignment:{COMPANY}:{key}:primary"))

        org_assignments = []
        if table_exists(cur, "employee_org_assignments"):
            org_assignments = q(
                cur,
                "SELECT * FROM employee_org_assignments WHERE company_code=%s AND employee_key=%s",
                (COMPANY, key),
            )

        assignment_ids = [
            {
                "assignment_id": str(uuid.uuid5(NS, f"assignment:{COMPANY}:{key}:{a.get('assignment_id') or a.get('id') or idx}")),
                "source": "employee_org_assignments",
                "raw": {k: a.get(k) for k in a if k not in ("raw_json",)},
            }
            for idx, a in enumerate(org_assignments)
        ] or [
            {
                "assignment_id": assignment_id,
                "source": "synthetic_primary",
                "raw": {"role": "primary_employment"},
            }
        ]

        mapping.append(
            {
                "company_code": COMPANY,
                "employee_key": key,
                "phone_redacted": redact_phone(emp.get("phone")),
                "email_redacted": redact_email(emp.get("email")),
                "app_key": emp.get("app_key"),
                "employment_status": emp.get("employment_status"),
                "onboarding_status": emp.get("onboarding_status"),
                "person_id": person_id,
                "person_seed": person_seed,
                "employment_id": employment_id,
                "assignments": assignment_ids,
                "compatibility": {
                    "legacy_pk": "employee_key",
                    "future_person_pk": "person_id",
                    "future_employment_pk": "employment_id",
                    "future_assignment_pk": "assignment_id",
                    "join_strategy": "employee_key → employment_id (1:1 for current hub); person_id groups phone/email identity",
                },
            }
        )

    # Also map known orphan key (no employee) as quarantine-only — no person issuance
    orphan_map = {
        "employee_key": KNOWN_ORPHAN_KEY,
        "person_id": None,
        "employment_id": None,
        "assignments": [],
        "note": "synthetic orphan — do not mint person/employment IDs; quarantine messages only",
    }

    return {
        "namespace": str(NS),
        "company_code": COMPANY,
        "employee_count": len(mapping),
        "employees": mapping,
        "synthetic_orphans_excluded_from_person_mint": [orphan_map],
        "wave2_notes": [
            "Do not create person/employment/assignment tables in Wave 1C",
            "IDs are deterministic uuid5 from stable seeds — safe to recompute",
            "Phone-canonical person seed aligns with Wave 1 alias model",
            "Quarantined synthetic keys must not receive person_id",
        ],
    }


def main() -> int:
    load_env()
    report: dict[str, Any] = {
        "stamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "mode": "read_only",
        "company_code": COMPANY,
        "known_null_keys": list(KNOWN_NULLS),
        "known_orphan_key": KNOWN_ORPHAN_KEY,
    }
    with connect() as conn:
        with conn.cursor() as cur:
            # DB identity
            db = q(cur, "SELECT current_database() AS db, current_setting('transaction_read_only') AS txn_ro")
            report["database"] = db[0]
            # All employees snapshot
            emps = q(
                cur,
                """
                SELECT employee_key, phone, email, name, employment_status, onboarding_status,
                       app_key, hire_date, start_date, created_at, updated_at
                FROM employees WHERE company_code=%s ORDER BY employee_key
                """,
                (COMPANY,),
            )
            report["employees_snapshot"] = [
                {
                    **e,
                    "phone": redact_phone(e.get("phone")),
                    "email": redact_email(e.get("email")),
                }
                for e in emps
            ]
            report["null_status_classifications"] = [classify_null_employee(cur, k) for k in KNOWN_NULLS]
            # Also flag any additional nulls beyond known set
            extra_nulls = q(
                cur,
                """
                SELECT employee_key FROM employees
                WHERE company_code=%s AND (employment_status IS NULL OR btrim(employment_status)='')
                  AND employee_key <> ALL(%s)
                """,
                (COMPANY, list(KNOWN_NULLS)),
            )
            report["additional_null_statuses"] = [r["employee_key"] for r in extra_nulls]
            report["orphan_message_classification"] = classify_orphan_messages(cur)
            report["integrity_scan"] = integrity_orphan_scan(cur)
            report["migration_readiness_map"] = migration_readiness_map(cur)

    dump_json(OUT / "wave1c-audit.json", report)
    dump_json(OUT / "null-classifications.json", report["null_status_classifications"])
    dump_json(OUT / "orphan-classification.json", report["orphan_message_classification"])
    dump_json(OUT / "integrity-scan.json", report["integrity_scan"])
    dump_json(OUT / "migration-readiness-map.json", report["migration_readiness_map"])
    print(json.dumps({
        "out": str(OUT),
        "nulls": [
            {"key": n["employee_key"], "class": n["classification"], "proposed": n["proposed_status"], "confidence": n["confidence"]}
            for n in report["null_status_classifications"]
        ],
        "additional_nulls": report["additional_null_statuses"],
        "orphan": {
            "class": report["orphan_message_classification"]["classification"],
            "count": report["orphan_message_classification"]["message_count"],
            "remediation": report["orphan_message_classification"]["proposed_remediation"],
        },
        "integrity_total_orphans": report["integrity_scan"]["total_orphans"],
        "map_employees": report["migration_readiness_map"]["employee_count"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
