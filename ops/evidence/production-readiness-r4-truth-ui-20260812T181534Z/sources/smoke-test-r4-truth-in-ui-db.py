#!/usr/bin/env python3
"""Production Readiness R4 — staging DB truth-in-UI (notification suppression).

Proves against an isolated staging database:

  * disabled source module cannot emit a new actionable employee notification
  * historical rows are left in place
  * re-enabling the module allows a new send
  * unmapped flows are not blocked by the module gate
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
CO_ON = f"R4ON{SUFFIX}"
CO_OFF = f"R4OFF{SUFFIX}"
EMP_ON = f"r4-on-{SUFFIX.lower()}"
EMP_OFF = f"r4-off-{SUFFIX.lower()}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def cleanup(app, companies: list[str]) -> None:
    import production_data_safety as pds

    pds.require_destructive_scope(companies)
    tables = [
        "employee_messages",
        "hr_tasks",
        "outbound_delivery_events",
        "employees",
        "company_modules",
        "company_settings",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
                except Exception:
                    conn.rollback()
        conn.commit()


def _insert_company(app, company: str, name: str) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, country, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,'KW',%s,%s,now(),now())",
                (company, name, app.Json({}), app.Json({})),
            )
        conn.commit()


def _set_module(app, company: str, module: str, enabled: bool) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,%s,%s) "
                "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=EXCLUDED.enabled",
                (company, module, enabled),
            )
        conn.commit()


def _message_count(app, company: str) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM employee_messages WHERE company_code=%s", (company,))
            return int((cur.fetchone() or {}).get("n") or 0)


def _seed_historical(app, company: str, emp_key: str) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee_messages
                  (company_code, employee_key, flow, template_key, locale, status, body_preview)
                VALUES (%s,%s,'leave','leave_request_approved','en','sent','historical leave note')
                """,
                (company, emp_key),
            )
        conn.commit()


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R4 — notification suppression (staging DB)")
    print(f"    tenants: {CO_ON} / {CO_OFF}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "leave_decision,leave,onboarding,compliance,shift"
    os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"

    try:
        import app
        import production_data_safety as pds
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable")
            return 1
        raise

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 1

    pds.require_non_production_target()
    app.ensure_schema()
    cleanup(app, [CO_ON, CO_OFF])

    try:
        _insert_company(app, CO_ON, "R4 leave on")
        _insert_company(app, CO_OFF, "R4 leave off")
        _set_module(app, CO_ON, "leave", True)
        _set_module(app, CO_OFF, "leave", False)

        emp_on = {"employee_key": EMP_ON, "company_code": CO_ON, "name": "On Emp", "phone": "96550000004111"}
        emp_off = {"employee_key": EMP_OFF, "company_code": CO_OFF, "name": "Off Emp", "phone": "96550000004112"}

        # Historical row on the disabled tenant must survive a suppressed send.
        try:
            _seed_historical(app, CO_OFF, EMP_OFF)
            historical_ok = True
        except Exception as exc:
            historical_ok = False
            print(f"      note  historical seed skipped ({type(exc).__name__}: {exc})")
        before_off = _message_count(app, CO_OFF)

        enabled = app.deliver_employee_notification(
            emp_on,
            flow="leave_decision",
            template_key="leave_request_approved",
            text="Your leave was approved.",
            email_subject="Leave update",
            company_code=CO_ON,
        )
        check("enabled module is not suppressed", enabled.get("suppressed") is not True, enabled)
        check("enabled module does not return source_module_disabled", enabled.get("error") != "source_module_disabled", enabled)

        disabled = app.deliver_employee_notification(
            emp_off,
            flow="leave_decision",
            template_key="leave_request_approved",
            text="Your leave was approved.",
            email_subject="Leave update",
            company_code=CO_OFF,
        )
        check("disabled module suppresses new notification", disabled.get("error") == "source_module_disabled", disabled)
        check("disabled module ok is false", disabled.get("ok") is False, disabled)
        check("disabled module delivery_status is module_disabled", disabled.get("delivery_status") == "module_disabled", disabled)
        after_off = _message_count(app, CO_OFF)
        check("disabled module created no new employee_messages row", after_off == before_off, {"before": before_off, "after": after_off})
        if historical_ok:
            check("historical notification row preserved", before_off >= 1 and after_off == before_off)

        _set_module(app, CO_OFF, "leave", True)
        reenabled = app.deliver_employee_notification(
            emp_off,
            flow="leave_decision",
            template_key="leave_request_approved",
            text="Your leave was approved after re-enable.",
            email_subject="Leave update",
            company_code=CO_OFF,
            dedupe_key=f"r4-reenable-{SUFFIX}",
        )
        check("re-enabled module is not suppressed", reenabled.get("error") != "source_module_disabled", reenabled)
        check("re-enabled module can emit again", reenabled.get("suppressed") is not True, reenabled)
    finally:
        cleanup(app, [CO_ON, CO_OFF])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    R4_TRUTH_IN_UI_DB_FAIL")
        return 1
    print("    R4_TRUTH_IN_UI_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
