#!/usr/bin/env python3
"""Read-only staging investigation for hired applications missing employee links.

Refuses production databases. Writes a JSON evidence report.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch  # noqa: E402


APP_KEY = os.environ.get("HALFHIRE_APP_KEY", "smoke-B74F3E8F")
COMPANY = os.environ.get("HALFHIRE_COMPANY", "WATHEFNI")
REPORT = os.environ.get(
    "HALFHIRE_REPORT",
    "/opt/wathefni/staging/orchestrator/ops/reports/candidates-c01-halfhire-evidence.json",
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


def columns(cur: Any, table: str) -> set[str]:
    return {
        r["column_name"]
        for r in rows(
            cur,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table,),
        )
    }


def select_by_app(cur: Any, table: str, company: str, app_key: str) -> list[dict[str, Any]]:
    cols = columns(cur, table)
    if "company_code" in cols and "app_key" in cols:
        return rows(cur, f"SELECT * FROM {table} WHERE company_code=%s AND app_key=%s", (company, app_key))
    if "app_key" in cols:
        return rows(cur, f"SELECT * FROM {table} WHERE app_key=%s", (app_key,))
    return rows(
        cur,
        f"SELECT * FROM {table} WHERE CAST(row_to_json({table}) AS text) ILIKE %s LIMIT 50",
        (f"%{app_key}%",),
    )


def main() -> int:
    expected_db = os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
    if expected_db != "wathefni_staging":
        raise SystemExit(f"refusing non-staging expected database: {expected_db!r}")
    orch.assert_runtime_environment_binding()

    out: dict[str, Any] = {
        "investigation_at": datetime.now(timezone.utc).isoformat(),
        "target": {"company_code": COMPANY, "app_key": APP_KEY},
    }

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            identity = one(
                cur,
                """
                SELECT current_database() AS db,
                       current_user AS db_user,
                       current_setting('wathefni.environment_marker', true) AS marker
                """,
            )
            out["identity"] = identity
            if identity and identity.get("db") != "wathefni_staging":
                raise SystemExit(f"refusing unexpected database: {identity}")

            app = one(
                cur,
                "SELECT * FROM applications WHERE company_code=%s AND app_key=%s",
                (COMPANY, APP_KEY),
            )
            out["application"] = app
            phone = str((app or {}).get("phone") or "")

            out["candidate"] = one(cur, "SELECT * FROM candidates WHERE phone=%s", (phone,)) if phone else None
            out["lifecycle_events"] = (
                rows(
                    cur,
                    """
                    SELECT *
                    FROM application_lifecycle_events
                    WHERE company_code=%s AND app_key=%s
                    ORDER BY created_at
                    """,
                    (COMPANY, APP_KEY),
                )
                if table_exists(cur, "application_lifecycle_events")
                else []
            )

            out["employees_columns"] = sorted(columns(cur, "employees")) if table_exists(cur, "employees") else []
            out["employees_by_app_key"] = (
                rows(cur, "SELECT * FROM employees WHERE company_code=%s AND app_key=%s", (COMPANY, APP_KEY))
                if table_exists(cur, "employees")
                else []
            )
            out["employees_by_phone_company"] = (
                rows(cur, "SELECT * FROM employees WHERE company_code=%s AND phone=%s", (COMPANY, phone))
                if phone and table_exists(cur, "employees")
                else []
            )
            out["employees_by_phone_any_company"] = (
                rows(cur, "SELECT * FROM employees WHERE phone=%s", (phone,))
                if phone and table_exists(cur, "employees")
                else []
            )

            for table in (
                "hire_operations",
                "offers",
                "candidate_offers",
                "offer_events",
                "candidate_interviews",
                "candidate_documents",
                "conversation_application_bindings",
                "file_registry",
                "outbound_delivery_events",
                "action_result_history",
                "dashboard_audit_events",
                "audit_events",
                "candidate_action_confirmations",
            ):
                if not table_exists(cur, table):
                    out[table] = "missing_table"
                    continue
                if table == "file_registry":
                    out[table] = rows(
                        cur,
                        """
                        SELECT file_id, company_code, subject_type, subject_key, file_kind,
                               document_type, original_filename, created_at, metadata
                        FROM file_registry
                        WHERE company_code=%s AND subject_key=%s
                        """,
                        (COMPANY, APP_KEY),
                    )
                else:
                    out[table] = select_by_app(cur, table, COMPANY, APP_KEY)

            # onboarding / compliance by employee keys if any
            emp_keys = [
                str(e.get("employee_key"))
                for e in (out["employees_by_phone_any_company"] or [])
                if e.get("employee_key")
            ]
            for table in ("employee_onboarding", "onboarding_tasks", "compliance_documents", "employee_compliance"):
                if not table_exists(cur, table):
                    out[table] = "missing_table"
                    continue
                cols = columns(cur, table)
                if "app_key" in cols:
                    out[table] = select_by_app(cur, table, COMPANY, APP_KEY)
                elif emp_keys and "employee_key" in cols:
                    out[table] = rows(cur, f"SELECT * FROM {table} WHERE employee_key = ANY(%s)", (emp_keys,))
                else:
                    out[table] = []

            out["all_hired_without_employee"] = rows(
                cur,
                """
                SELECT a.company_code, a.app_key, a.phone, a.status, a.position_code,
                       a.updated_at, a.ingested_at, left(COALESCE(a.raw_json::text,''), 400) AS raw_preview
                FROM applications a
                LEFT JOIN employees e
                  ON e.company_code=a.company_code AND e.app_key=a.app_key
                WHERE lower(COALESCE(a.status,''))='hired'
                  AND e.employee_key IS NULL
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 100
                """,
            )

            # same-role / employee-link collisions for later gates
            out["active_same_role_collisions"] = rows(
                cur,
                """
                SELECT phone, company_code, position_code, count(*) AS active_count,
                       array_agg(app_key ORDER BY updated_at DESC NULLS LAST) AS app_keys,
                       array_agg(status ORDER BY updated_at DESC NULLS LAST) AS statuses
                FROM applications
                WHERE phone IS NOT NULL AND phone <> ''
                  AND company_code IS NOT NULL AND company_code <> ''
                  AND position_code IS NOT NULL AND position_code <> ''
                  AND lower(COALESCE(status,'')) NOT IN
                    ('rejected','withdrawn','hired','needs_role','import_review','import_archived')
                GROUP BY phone, company_code, position_code
                HAVING count(*) > 1
                """,
            )
            out["duplicate_employee_links"] = rows(
                cur,
                """
                SELECT company_code, app_key, count(*) AS n,
                       array_agg(employee_key) AS employee_keys
                FROM employees
                WHERE app_key IS NOT NULL AND app_key <> ''
                GROUP BY company_code, app_key
                HAVING count(*) > 1
                """,
            )

            # other applications for same phone (context)
            if phone:
                out["other_applications_same_phone"] = rows(
                    cur,
                    """
                    SELECT company_code, app_key, status, position_code, updated_at
                    FROM applications
                    WHERE phone=%s
                    ORDER BY updated_at DESC NULLS LAST
                    """,
                    (phone,),
                )

    # Classification hints (no mutation)
    app = out.get("application") or {}
    raw = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
    classification = {
        "app_key_prefix_smoke": str(APP_KEY).startswith("smoke-"),
        "raw_smoke_markers": {
            k: raw.get(k)
            for k in raw
            if any(token in str(k).lower() for token in ("smoke", "test", "canary", "fixture", "proof"))
        },
        "has_employee_any_identifier": bool(
            out.get("employees_by_app_key")
            or out.get("employees_by_phone_company")
            or out.get("employees_by_phone_any_company")
        ),
        "lifecycle_event_count": len(out.get("lifecycle_events") or []),
        "hired_without_employee_count": len(out.get("all_hired_without_employee") or []),
    }
    out["classification_hints"] = classification

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"ok": True, "report": REPORT, "classification_hints": classification, "identity": out["identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
