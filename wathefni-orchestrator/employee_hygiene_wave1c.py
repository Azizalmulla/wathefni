"""Employees 360 Wave 1C — data hygiene + Wave 2 migration readiness.

Local/staging-safe remediations:
  - evidence-backed null employment_status → active (journaled, reversible)
  - quarantine/archive synthetic orphan employee_messages (no silent delete)
  - deterministic employee_key → person_id / employment_id / assignment_id map

Does NOT:
  - add UNIQUE constraints
  - create Wave 2 person/employment schema tables
  - mutate production unless explicitly invoked with apply + approval gate
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

PERSON_NAMESPACE = uuid.UUID("6b1c0f3a-9d2e-4a7b-8c5d-1e2f3a4b5c6d")


def _psycopg2_json(value: Any):
    from psycopg2.extras import Json

    return Json(value)

HYGIENE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_hygiene_remediation_journal (
  remediation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  target_type text NOT NULL,
  target_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL,
  dry_run boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'applied',
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  rolled_back_at timestamptz,
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_messages_quarantine (
  quarantine_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quarantined_at timestamptz NOT NULL DEFAULT now(),
  quarantine_reason text NOT NULL,
  remediation_id uuid,
  message_id uuid NOT NULL UNIQUE,
  company_code text NOT NULL,
  employee_key text,
  message_row jsonb NOT NULL,
  restored_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_employee_messages_quarantine_company_key
  ON employee_messages_quarantine (company_code, employee_key);
"""


def ensure_hygiene_schema(cur) -> None:
    cur.execute(HYGIENE_SCHEMA_SQL)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def phone_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def is_synthetic_employee_key(employee_key: str) -> bool:
    return bool(re.search(r"(P0-DUP|SYNTH|TEST-ORPHAN|SMOKE-ORPHAN)", str(employee_key or ""), re.I))


def mint_person_id(*, company_code: str, phone: str | None = None, email: str | None = None, employee_key: str | None = None) -> tuple[str, str]:
    company = str(company_code or "").upper()
    digits = phone_digits(phone)
    mail = str(email or "").strip().lower()
    key = str(employee_key or "").strip()
    if digits:
        seed = f"person:{company}:phone:{digits}"
    elif mail:
        seed = f"person:{company}:email:{mail}"
    elif key:
        seed = f"person:{company}:employee_key:{key}"
    else:
        raise ValueError("cannot mint person_id without phone, email, or employee_key")
    return str(uuid.uuid5(PERSON_NAMESPACE, seed)), seed


def mint_employment_id(*, company_code: str, employee_key: str) -> str:
    return str(uuid.uuid5(PERSON_NAMESPACE, f"employment:{str(company_code or '').upper()}:{employee_key}"))


def mint_assignment_id(*, company_code: str, employee_key: str, slot: str = "primary") -> str:
    return str(uuid.uuid5(PERSON_NAMESPACE, f"assignment:{str(company_code or '').upper()}:{employee_key}:{slot}"))


def build_migration_readiness_row(employee: dict[str, Any]) -> dict[str, Any]:
    company = str(employee.get("company_code") or "").upper()
    key = str(employee.get("employee_key") or "")
    person_id, person_seed = mint_person_id(
        company_code=company,
        phone=employee.get("phone"),
        email=employee.get("email"),
        employee_key=key,
    )
    return {
        "company_code": company,
        "employee_key": key,
        "person_id": person_id,
        "person_seed": person_seed,
        "employment_id": mint_employment_id(company_code=company, employee_key=key),
        "assignments": [
            {
                "assignment_id": mint_assignment_id(company_code=company, employee_key=key, slot="primary"),
                "source": "synthetic_primary",
            }
        ],
        "employment_status": employee.get("employment_status"),
        "app_key": employee.get("app_key"),
    }


def build_migration_readiness_map(employees: list[dict[str, Any]], *, synthetic_orphan_keys: list[str] | None = None) -> dict[str, Any]:
    return {
        "namespace": str(PERSON_NAMESPACE),
        "employee_count": len(employees),
        "employees": [build_migration_readiness_row(e) for e in employees],
        "synthetic_orphans_excluded_from_person_mint": [
            {
                "employee_key": k,
                "person_id": None,
                "employment_id": None,
                "note": "synthetic orphan — quarantine only; do not mint person/employment IDs",
            }
            for k in (synthetic_orphan_keys or [])
        ],
        "wave2_notes": [
            "Wave 1C emits deterministic uuid5 IDs only; no Wave 2 schema migration",
            "Recompute safely from seeds; do not persist as authoritative until Wave 2",
        ],
    }


def classify_null_status_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Pure classifier used by audit + remediation gate. Never guesses left."""
    emp = evidence.get("employee") or {}
    status_raw = emp.get("employment_status")
    reasons: list[str] = []
    if status_raw is not None and str(status_raw).strip() != "":
        return {
            "classification": "already_set",
            "proposed_status": str(status_raw).strip().lower(),
            "confidence": "high",
            "reasons": [f"employment_status already set to {str(status_raw).strip().lower()!r}"],
        }
    reasons.append("employment_status IS NULL")
    if int(evidence.get("employee_status_changes", {}).get("count") or 0) > 0:
        return {
            "classification": "needs_manual_review",
            "proposed_status": None,
            "confidence": "low",
            "reasons": reasons + ["employee_status_changes present — inspect before backfill"],
        }
    apps = evidence.get("applications") or []
    app_statuses = [str(a.get("status") or "").lower() for a in apps]
    if any(s in ("left", "rejected", "withdrawn") for s in app_statuses):
        return {
            "classification": "needs_manual_review",
            "proposed_status": None,
            "confidence": "low",
            "reasons": reasons + [f"application statuses need review: {app_statuses}"],
        }
    has_app = bool(emp.get("app_key"))
    onboarding = str(emp.get("onboarding_status") or "").strip().lower()
    att = int(evidence.get("attendance_records", {}).get("count") or 0)
    shifts = int(evidence.get("shift_assignments", {}).get("count") or 0)
    leave = int(evidence.get("leave_requests", {}).get("count") or 0)
    msgs = int(evidence.get("employee_messages", {}).get("count") or 0)
    hired = any(s == "hired" for s in app_statuses)
    if hired or has_app or onboarding or att or shifts or leave or msgs:
        reasons_extra = []
        if hired:
            reasons_extra.append("application.status=hired")
        if has_app:
            reasons_extra.append(f"hire-linked app_key={emp.get('app_key')}")
        if onboarding:
            reasons_extra.append(f"onboarding_status={onboarding!r}")
        if att:
            reasons_extra.append(f"attendance_records={att}")
        if shifts:
            reasons_extra.append(f"shift_assignments={shifts}")
        if leave:
            reasons_extra.append(f"leave_requests={leave}")
        if msgs:
            reasons_extra.append(f"employee_messages={msgs}")
        confidence = "high" if hired or (has_app and (att or shifts or onboarding)) else "medium"
        return {
            "classification": "null_should_be_active",
            "proposed_status": "active",
            "confidence": confidence,
            "reasons": reasons + reasons_extra + ["no left markers found"],
        }
    return {
        "classification": "needs_manual_review",
        "proposed_status": None,
        "confidence": "none",
        "reasons": reasons + ["insufficient evidence — refuse to guess"],
    }


def _journal_lookup(cur, *, company_code: str, idempotency_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM employee_hygiene_remediation_journal
        WHERE company_code=%s AND idempotency_key=%s
        LIMIT 1
        """,
        (str(company_code).upper(), idempotency_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _insert_journal(
    cur,
    *,
    company_code: str,
    action: str,
    target_type: str,
    target_key: str,
    before_json: dict[str, Any],
    after_json: dict[str, Any],
    evidence: dict[str, Any],
    reason: str,
    dry_run: bool,
    status: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Insert or revive a journal row (supports restore-new after rollback)."""
    cur.execute(
        """
        INSERT INTO employee_hygiene_remediation_journal (
          company_code, action, target_type, target_key, before_json, after_json,
          evidence, reason, dry_run, status, idempotency_key
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
        ON CONFLICT (company_code, idempotency_key) DO UPDATE SET
          action = EXCLUDED.action,
          target_type = EXCLUDED.target_type,
          target_key = EXCLUDED.target_key,
          before_json = EXCLUDED.before_json,
          after_json = EXCLUDED.after_json,
          evidence = EXCLUDED.evidence,
          reason = EXCLUDED.reason,
          dry_run = EXCLUDED.dry_run,
          status = EXCLUDED.status,
          rolled_back_at = NULL,
          created_at = CASE
            WHEN employee_hygiene_remediation_journal.status = 'rolled_back' THEN now()
            ELSE employee_hygiene_remediation_journal.created_at
          END
        RETURNING *
        """,
        (
            str(company_code).upper(),
            action,
            target_type,
            target_key,
            json.dumps(_jsonable(before_json)),
            json.dumps(_jsonable(after_json)),
            json.dumps(_jsonable(evidence)),
            reason,
            dry_run,
            status,
            idempotency_key,
        ),
    )
    return dict(cur.fetchone())


def remediate_null_employment_status(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    evidence: dict[str, Any],
    reason: str,
    idempotency_key: str,
    dry_run: bool = True,
    allow_confidence: tuple[str, ...] = ("high",),
) -> dict[str, Any]:
    """Set null employment_status → active only when classifier agrees with evidence."""
    company = str(company_code or "").upper()
    key = str(employee_key or "").strip()
    decision = classify_null_status_from_evidence(evidence)
    if decision["classification"] != "null_should_be_active" or decision.get("proposed_status") != "active":
        return {
            "ok": False,
            "status": "refused",
            "error": "insufficient_or_conflicting_evidence",
            "decision": decision,
        }
    if decision.get("confidence") not in allow_confidence:
        return {
            "ok": False,
            "status": "refused",
            "error": "confidence_below_threshold",
            "decision": decision,
        }

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hygiene_schema(cur)
            existing = _journal_lookup(cur, company_code=company, idempotency_key=idempotency_key)
            if existing and existing.get("status") == "applied" and not existing.get("dry_run"):
                conn.commit()
                return {"ok": True, "status": "idempotent", "remediation": _jsonable(existing), "decision": decision}
            cur.execute(
                """
                SELECT employee_key, company_code, employment_status, updated_at, app_key, onboarding_status
                FROM employees WHERE company_code=%s AND employee_key=%s
                FOR UPDATE
                """,
                (company, key),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return {"ok": False, "status": "not_found", "error": "employee_not_found"}
            before = dict(row)
            if before.get("employment_status") is not None and str(before.get("employment_status")).strip() != "":
                journal = _insert_journal(
                    cur,
                    company_code=company,
                    action="set_employment_status",
                    target_type="employee",
                    target_key=key,
                    before_json=before,
                    after_json=before,
                    evidence={"decision": decision, "caller_evidence": evidence},
                    reason=reason + " | already_set_noop",
                    dry_run=dry_run,
                    status="idempotent_already_set",
                    idempotency_key=idempotency_key,
                )
                conn.commit()
                return {"ok": True, "status": "idempotent_already_set", "remediation": _jsonable(journal), "decision": decision}

            after = {**before, "employment_status": "active"}
            if dry_run:
                journal = _insert_journal(
                    cur,
                    company_code=company,
                    action="set_employment_status",
                    target_type="employee",
                    target_key=key,
                    before_json=before,
                    after_json=after,
                    evidence={"decision": decision, "caller_evidence": evidence},
                    reason=reason,
                    dry_run=True,
                    status="dry_run",
                    idempotency_key=idempotency_key,
                )
                conn.commit()
                return {"ok": True, "status": "dry_run", "remediation": _jsonable(journal), "decision": decision}

            cur.execute(
                """
                UPDATE employees
                SET employment_status='active', updated_at=clock_timestamp()
                WHERE company_code=%s AND employee_key=%s AND employment_status IS NULL
                RETURNING employee_key, company_code, employment_status, updated_at
                """,
                (company, key),
            )
            updated = cur.fetchone()
            if not updated:
                conn.rollback()
                return {"ok": False, "status": "conflict", "error": "status_changed_concurrently"}
            journal = _insert_journal(
                cur,
                company_code=company,
                action="set_employment_status",
                target_type="employee",
                target_key=key,
                before_json=before,
                after_json=dict(updated),
                evidence={"decision": decision, "caller_evidence": evidence, "reasons": decision.get("reasons")},
                reason=reason,
                dry_run=False,
                status="applied",
                idempotency_key=idempotency_key,
            )
            conn.commit()
            return {"ok": True, "status": "applied", "remediation": _jsonable(journal), "decision": decision}


def rollback_null_employment_status(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
) -> dict[str, Any]:
    company = str(company_code or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hygiene_schema(cur)
            journal = _journal_lookup(cur, company_code=company, idempotency_key=idempotency_key)
            if not journal:
                return {"ok": False, "status": "not_found"}
            if journal.get("status") == "rolled_back":
                return {"ok": True, "status": "idempotent_rolled_back", "remediation": _jsonable(journal)}
            if journal.get("status") != "applied" or journal.get("action") != "set_employment_status":
                return {"ok": False, "status": "not_reversible", "remediation": _jsonable(journal)}
            before = journal.get("before_json") or {}
            if isinstance(before, str):
                before = json.loads(before)
            key = journal["target_key"]
            prev = before.get("employment_status")
            cur.execute(
                """
                UPDATE employees
                SET employment_status=%s, updated_at=clock_timestamp()
                WHERE company_code=%s AND employee_key=%s
                RETURNING employee_key, employment_status, updated_at
                """,
                (prev, company, key),
            )
            after = dict(cur.fetchone() or {})
            cur.execute(
                """
                UPDATE employee_hygiene_remediation_journal
                SET status='rolled_back', rolled_back_at=now(), after_json=%s::jsonb
                WHERE remediation_id=%s
                RETURNING *
                """,
                (json.dumps(_jsonable({**before, "rollback_row": after})), journal["remediation_id"]),
            )
            updated = dict(cur.fetchone())
            conn.commit()
            return {"ok": True, "status": "rolled_back", "remediation": _jsonable(updated)}


def quarantine_orphan_employee_messages(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    reason: str,
    idempotency_key: str,
    dry_run: bool = True,
    require_synthetic_key: bool = True,
    require_no_employee_row: bool = True,
) -> dict[str, Any]:
    """Archive orphan messages into quarantine table, then remove from live table.

    Preserves full row JSON. Reversible via restore_quarantined_employee_messages.
    """
    company = str(company_code or "").upper()
    key = str(employee_key or "").strip()
    if require_synthetic_key and not is_synthetic_employee_key(key):
        return {"ok": False, "status": "refused", "error": "employee_key_not_synthetic"}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hygiene_schema(cur)
            existing = _journal_lookup(cur, company_code=company, idempotency_key=idempotency_key)
            if existing and existing.get("status") == "applied" and not existing.get("dry_run"):
                conn.commit()
                return {"ok": True, "status": "idempotent", "remediation": _jsonable(existing)}

            cur.execute(
                "SELECT employee_key FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
                (company, key),
            )
            emp = cur.fetchone()
            if require_no_employee_row and emp:
                return {"ok": False, "status": "refused", "error": "employee_row_exists", "employee": dict(emp)}

            cur.execute(
                """
                SELECT * FROM employee_messages
                WHERE company_code=%s AND employee_key=%s
                ORDER BY created_at
                FOR UPDATE
                """,
                (company, key),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            evidence = {
                "message_count": len(rows),
                "message_ids": [str(r.get("message_id")) for r in rows],
                "synthetic_key": is_synthetic_employee_key(key),
                "employee_row_present": bool(emp),
            }
            if dry_run:
                journal = _insert_journal(
                    cur,
                    company_code=company,
                    action="quarantine_employee_messages",
                    target_type="employee_messages",
                    target_key=key,
                    before_json={"messages": rows},
                    after_json={"quarantined": len(rows)},
                    evidence=evidence,
                    reason=reason,
                    dry_run=True,
                    status="dry_run",
                    idempotency_key=idempotency_key,
                )
                conn.commit()
                return {"ok": True, "status": "dry_run", "count": len(rows), "remediation": _jsonable(journal)}

            journal = _insert_journal(
                cur,
                company_code=company,
                action="quarantine_employee_messages",
                target_type="employee_messages",
                target_key=key,
                before_json={"messages": rows},
                after_json={"quarantined": len(rows)},
                evidence=evidence,
                reason=reason,
                dry_run=False,
                status="applied",
                idempotency_key=idempotency_key,
            )
            remediation_id = journal["remediation_id"]
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO employee_messages_quarantine (
                      quarantine_reason, remediation_id, message_id, company_code, employee_key, message_row
                    ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (message_id) DO UPDATE
                      SET quarantine_reason=EXCLUDED.quarantine_reason,
                          remediation_id=EXCLUDED.remediation_id,
                          message_row=EXCLUDED.message_row,
                          quarantined_at=now(),
                          restored_at=NULL
                    """,
                    (
                        reason,
                        remediation_id,
                        row["message_id"],
                        company,
                        key,
                        json.dumps(_jsonable(row)),
                    ),
                )
            cur.execute(
                "DELETE FROM employee_messages WHERE company_code=%s AND employee_key=%s",
                (company, key),
            )
            deleted = cur.rowcount
            conn.commit()
            return {
                "ok": True,
                "status": "applied",
                "count": len(rows),
                "deleted": deleted,
                "remediation": _jsonable(journal),
            }


def restore_quarantined_employee_messages(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
) -> dict[str, Any]:
    company = str(company_code or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hygiene_schema(cur)
            journal = _journal_lookup(cur, company_code=company, idempotency_key=idempotency_key)
            if not journal:
                return {"ok": False, "status": "not_found"}
            if journal.get("status") == "rolled_back":
                return {"ok": True, "status": "idempotent_rolled_back", "remediation": _jsonable(journal)}
            if journal.get("status") != "applied" or journal.get("action") != "quarantine_employee_messages":
                return {"ok": False, "status": "not_reversible", "remediation": _jsonable(journal)}

            cur.execute(
                """
                SELECT * FROM employee_messages_quarantine
                WHERE remediation_id=%s AND restored_at IS NULL
                ORDER BY quarantined_at
                """,
                (journal["remediation_id"],),
            )
            qrows = [dict(r) for r in (cur.fetchall() or [])]
            restored = 0
            for qrow in qrows:
                message = qrow.get("message_row") or {}
                if isinstance(message, str):
                    message = json.loads(message)
                cur.execute(
                    """
                    SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='employee_messages'
                    """
                )
                col_meta = {r["column_name"]: r for r in cur.fetchall()}
                live_cols = list(col_meta.keys())
                payload = {k: message.get(k) for k in live_cols if k in message}
                if not payload.get("message_id"):
                    continue
                cols = list(payload.keys())
                values = []
                for c in cols:
                    val = payload[c]
                    udt = str((col_meta.get(c) or {}).get("udt_name") or "")
                    dtype = str((col_meta.get(c) or {}).get("data_type") or "")
                    if udt == "jsonb" or dtype == "jsonb" or isinstance(val, (dict, list)):
                        values.append(_psycopg2_json(_jsonable(val)))
                    else:
                        values.append(val)
                cur.execute(
                    f"""
                    INSERT INTO employee_messages ({', '.join(cols)})
                    VALUES ({', '.join(['%s'] * len(cols))})
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    values,
                )
                cur.execute(
                    "UPDATE employee_messages_quarantine SET restored_at=now() WHERE quarantine_id=%s",
                    (qrow["quarantine_id"],),
                )
                restored += 1
            cur.execute(
                """
                UPDATE employee_hygiene_remediation_journal
                SET status='rolled_back', rolled_back_at=now()
                WHERE remediation_id=%s
                RETURNING *
                """,
                (journal["remediation_id"],),
            )
            updated = dict(cur.fetchone())
            conn.commit()
            return {"ok": True, "status": "rolled_back", "restored": restored, "remediation": _jsonable(updated)}


def proposed_production_plan(audit: dict[str, Any]) -> dict[str, Any]:
    """Build an approval-gated production remediation plan from Wave 1C audit JSON."""
    plan = {"actions": [], "non_actions": [
        "no uniqueness constraints",
        "no Wave 2 schema migration",
        "no frozen pre-hiring / Wave D changes",
        "no silent deletes",
    ]}
    for item in audit.get("null_status_classifications") or []:
        plan["actions"].append(
            {
                "action": "set_employment_status",
                "employee_key": item.get("employee_key"),
                "from": None,
                "to": item.get("proposed_status"),
                "classification": item.get("classification"),
                "confidence": item.get("confidence"),
                "reasons": item.get("reasons"),
                "idempotency_key": f"wave1c-null-status:{item.get('employee_key')}:active",
                "apply_when": "owner_approved_production",
            }
        )
    orphan = audit.get("orphan_message_classification") or {}
    plan["actions"].append(
        {
            "action": "quarantine_employee_messages",
            "employee_key": orphan.get("employee_key"),
            "count": orphan.get("message_count"),
            "classification": orphan.get("classification"),
            "confidence": orphan.get("confidence"),
            "reasons": orphan.get("reasons"),
            "idempotency_key": f"wave1c-quarantine:{orphan.get('employee_key')}",
            "apply_when": "owner_approved_production",
        }
    )
    plan["integrity_expectation_after"] = {
        "employee_messages_orphans": 0,
        "additional_null_statuses": 0,
    }
    plan["rollback"] = {
        "null_status": "rollback_null_employment_status(idempotency_key)",
        "orphan_messages": "restore_quarantined_employee_messages(idempotency_key)",
        "journal_table": "employee_hygiene_remediation_journal",
        "archive_table": "employee_messages_quarantine",
    }
    return plan
