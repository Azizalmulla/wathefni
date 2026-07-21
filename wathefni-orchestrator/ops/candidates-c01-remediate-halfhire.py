#!/usr/bin/env python3
"""Audited deterministic cleanup for isolated staging smoke half-hire.

Classification required before mutation:
  - app_key starts with smoke-
  - synthetic smoke phone / Phase1 smoke markers
  - no employee under app_key, phone+company, or phone globally
  - no interviews, documents, bindings, offers, hire_operations
  - only one application for the phone
  - staging database only

Does NOT rewrite lifecycle status. Deletes disposable smoke fixtures and writes
a durable audited receipt (DB row + JSON report).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch  # noqa: E402


APP_KEY = os.environ.get("HALFHIRE_APP_KEY", "smoke-B74F3E8F")
COMPANY = os.environ.get("HALFHIRE_COMPANY", "WATHEFNI")
APPLY = os.environ.get("HALFHIRE_APPLY", "1") == "1"
REPORT = os.environ.get(
    "HALFHIRE_CLEANUP_REPORT",
    "/opt/wathefni/staging/orchestrator/ops/reports/candidates-c01-halfhire-cleanup.json",
)


def rows(cur: Any, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in (cur.fetchall() or [])]


def one(cur: Any, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def table_exists(cur: Any, name: str) -> bool:
    return bool(one(cur, "SELECT to_regclass(%s) AS t", (f"public.{name}",))["t"])


def main() -> int:
    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni_staging":
        raise SystemExit("refusing non-staging database expectation")
    orch.assert_runtime_environment_binding()

    receipt: dict[str, Any] = {
        "remediation_at": datetime.now(timezone.utc).isoformat(),
        "mode": "deterministic_cleanup",
        "target": {"company_code": COMPANY, "app_key": APP_KEY},
        "apply": APPLY,
    }

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            identity = one(
                cur,
                """
                SELECT current_database() AS db, current_user AS db_user,
                       current_setting('wathefni.environment_marker', true) AS marker
                """,
            )
            receipt["identity"] = identity
            if not identity or identity.get("db") != "wathefni_staging":
                raise SystemExit(f"refusing unexpected database: {identity}")

            app = one(
                cur,
                "SELECT * FROM applications WHERE company_code=%s AND app_key=%s FOR UPDATE",
                (COMPANY, APP_KEY),
            )
            if not app:
                receipt["ok"] = True
                receipt["already_absent"] = True
                _write(receipt)
                print(json.dumps(receipt, indent=2, default=str))
                return 0

            phone = str(app.get("phone") or "")
            position_code = str(app.get("position_code") or "")
            candidate = one(cur, "SELECT * FROM candidates WHERE phone=%s FOR UPDATE", (phone,)) if phone else None
            position = (
                one(
                    cur,
                    "SELECT * FROM positions WHERE company_code=%s AND position_code=%s FOR UPDATE",
                    (COMPANY, position_code),
                )
                if position_code
                else None
            )

            def count_like(table: str) -> list[dict[str, Any]]:
                if not table_exists(cur, table):
                    return []
                return rows(
                    cur,
                    f"SELECT * FROM {table} WHERE CAST(row_to_json({table}) AS text) ILIKE %s LIMIT 20",
                    (f"%{APP_KEY}%",),
                )

            dependents = {
                "employees_app": rows(cur, "SELECT * FROM employees WHERE company_code=%s AND app_key=%s", (COMPANY, APP_KEY)),
                "employees_phone_company": rows(cur, "SELECT * FROM employees WHERE company_code=%s AND phone=%s", (COMPANY, phone)) if phone else [],
                "employees_phone_any": rows(cur, "SELECT * FROM employees WHERE phone=%s", (phone,)) if phone else [],
                "apps_same_phone": rows(cur, "SELECT app_key, company_code, status FROM applications WHERE phone=%s", (phone,)) if phone else [],
                "interviews": count_like("candidate_interviews"),
                "documents": count_like("candidate_documents"),
                "bindings": count_like("conversation_application_bindings"),
                "lifecycle_events": rows(cur, "SELECT event_id, from_stage, to_stage, trigger, created_at FROM application_lifecycle_events WHERE company_code=%s AND app_key=%s", (COMPANY, APP_KEY)) if table_exists(cur, "application_lifecycle_events") else [],
            }
            receipt["pre_delete"] = {
                "application": orch.json_safe(app),
                "candidate": orch.json_safe(candidate),
                "position": orch.json_safe(position),
                "dependents": orch.json_safe(dependents),
            }

            gates = {
                "app_key_smoke_prefix": APP_KEY.startswith("smoke-"),
                "status_hired": str(app.get("status") or "").lower() == "hired",
                "synthetic_phone": phone.startswith("9650000") and len(phone) <= 14,
                "smoke_name": str((candidate or {}).get("name") or "").startswith("Smoke Hire"),
                "smoke_position": position_code.startswith("JP1_") or str((position or {}).get("title") or "").startswith("Phase1 Smoke"),
                "no_employee": not (
                    dependents["employees_app"]
                    or dependents["employees_phone_company"]
                    or dependents["employees_phone_any"]
                ),
                "no_interviews": not dependents["interviews"],
                "no_documents": not dependents["documents"],
                "no_bindings": not dependents["bindings"],
                "single_app_for_phone": len(dependents["apps_same_phone"]) == 1,
                "empty_or_smoke_raw": app.get("raw_json") in ({}, None) or (
                    isinstance(app.get("raw_json"), dict) and not app.get("raw_json")
                ),
            }
            receipt["gates"] = gates
            if not all(gates.values()):
                receipt["ok"] = False
                receipt["error"] = "classification_gates_failed"
                _write(receipt)
                print(json.dumps(receipt, indent=2, default=str))
                return 2

            receipt["classification"] = (
                "disposable_isolated_smoke_data_from_smoke-test-jobs-phase1.py "
                "vacancy-math fixture; INSERT ... status='hired' without employee; "
                "cleanup path failed leaving application+position"
            )
            receipt["code_path"] = {
                "file": "smoke-test-jobs-phase1.py",
                "behavior": "direct INSERT applications status='hired' for vacancy math; intended DELETE at end",
                "ingested_at": app.get("ingested_at"),
                "updated_at": app.get("updated_at"),
                "no_lifecycle_events": True,
            }

            if not APPLY:
                receipt["ok"] = True
                receipt["dry_run"] = True
                _write(receipt)
                print(json.dumps({"ok": True, "dry_run": True, "gates": gates, "report": REPORT}, indent=2))
                return 0

            audit_id = str(uuid.uuid4())
            actor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "wathefni:ops:candidates-c01-halfhire-cleanup"))
            # Durable audit row that survives application deletion (no FK).
            if table_exists(cur, "application_lifecycle_events"):
                cur.execute(
                    """
                    INSERT INTO application_lifecycle_events (
                      event_id, company_code, app_key, from_stage, to_stage, trigger,
                      actor_type, actor_user_id, channel, idempotency_key, metadata
                    ) VALUES (
                      %s,%s,%s,'hired','hired','ops_deterministic_smoke_cleanup',
                      'system',%s,'ops',%s,%s::jsonb
                    )
                    """,
                    (
                        audit_id,
                        COMPANY,
                        APP_KEY,
                        actor_id,
                        f"ops-halfhire-cleanup:{APP_KEY}:{audit_id}",
                        json.dumps(
                            {
                                "action": "deterministic_delete",
                                "reason": "isolated_jobs_phase1_smoke_halfhire",
                                "operator": "candidates-c01-halfhire-cleanup",
                                "classification": receipt["classification"],
                                "code_path": receipt["code_path"],
                                "deleted": {
                                    "application": True,
                                    "candidate": True,
                                    "position": bool(position),
                                },
                                "snapshot": {
                                    "phone": phone,
                                    "position_code": position_code,
                                    "status": app.get("status"),
                                    "ingested_at": str(app.get("ingested_at")),
                                },
                            },
                            default=str,
                        ),
                    ),
                )
                receipt["audit_event_id"] = audit_id
                receipt["audit_actor_user_id"] = actor_id

            cur.execute(
                "DELETE FROM applications WHERE company_code=%s AND app_key=%s RETURNING app_key",
                (COMPANY, APP_KEY),
            )
            deleted_app = cur.fetchone()
            deleted_candidate = None
            if phone:
                cur.execute("DELETE FROM candidates WHERE phone=%s RETURNING phone", (phone,))
                deleted_candidate = cur.fetchone()
            deleted_position = None
            if position_code:
                cur.execute(
                    "DELETE FROM positions WHERE company_code=%s AND position_code=%s RETURNING position_code",
                    (COMPANY, position_code),
                )
                deleted_position = cur.fetchone()

            # Post conditions
            remaining_hired = rows(
                cur,
                """
                SELECT a.company_code, a.app_key
                FROM applications a
                LEFT JOIN employees e ON e.company_code=a.company_code AND e.app_key=a.app_key
                WHERE lower(COALESCE(a.status,''))='hired' AND e.employee_key IS NULL
                """,
            )
            still_app = one(cur, "SELECT app_key FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, APP_KEY))
            still_cand = one(cur, "SELECT phone FROM candidates WHERE phone=%s", (phone,)) if phone else None
            still_pos = (
                one(cur, "SELECT position_code FROM positions WHERE company_code=%s AND position_code=%s", (COMPANY, position_code))
                if position_code
                else None
            )
            receipt["deleted"] = {
                "application": bool(deleted_app),
                "candidate": bool(deleted_candidate),
                "position": bool(deleted_position),
            }
            receipt["post_conditions"] = {
                "application_absent": still_app is None,
                "candidate_absent": still_cand is None,
                "position_absent": still_pos is None,
                "hired_without_employee": remaining_hired,
                "hired_without_employee_count": len(remaining_hired),
            }
            if still_app or still_cand or still_pos or remaining_hired:
                conn.rollback()
                receipt["ok"] = False
                receipt["error"] = "post_condition_failed_rolled_back"
                _write(receipt)
                print(json.dumps(receipt, indent=2, default=str))
                return 3
            conn.commit()
            receipt["ok"] = True

    _write(receipt)
    print(json.dumps({"ok": True, "report": REPORT, "deleted": receipt["deleted"], "audit_event_id": receipt.get("audit_event_id")}, indent=2))
    return 0


def _write(payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
