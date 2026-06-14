"""Shift reminder email-fallback regression harness (templates stay OFF).

Locks in the behaviour proven by the investigation: run_shift_reminder_scan loads
the employee email and passes it through deliver_employee_notification ->
deliver_to_employee -> the channel ladder, so a shift reminder uses the email
fallback when WhatsApp is unavailable. (The earlier 27 failed rows predated the
fix; this guards against a silent regression — shift_reminder is informational, so
a regression would NOT raise an HR task and could go unnoticed.)

No network, no real sends: the channel primitives are stubbed (WhatsApp session
fails with a closed-conversation error, templates are disabled, email is a
recorder) and delivery mode is pinned to dry_run.

Cases:
  A. Employee WITH email + no open WhatsApp session + templates OFF
     -> the email provider is called with THAT employee's email
     -> result status is sent_email_fallback
     -> reasons do NOT include email:no_employee_email
     -> no HR task (informational).
  B. Employee WITHOUT email
     -> calm TERMINAL result (failed, not a pending retry)
     -> reasons include email:no_employee_email
     -> no HR task (shift_reminder is informational, not critical).

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-shift-reminder-email.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "WSHIFTEMAILCO"
MARKER = "temporary_shift_reminder_email_harness"

EMP_WITH = "wshift-emp-with-email"
EMP_WITHOUT = "wshift-emp-no-email"
PHONE_WITH = "96550000000811"
PHONE_WITHOUT = "96550000000812"
EMAIL_WITH = "wshift-with@example.com"

CALLS: dict[str, Any] = {"session": 0, "template": 0, "email": 0, "email_to": []}
_ORIG: dict[str, Any] = {}


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _session_stub(**_k: Any) -> dict[str, Any]:
    CALLS["session"] += 1
    # Non-retryable closed-conversation: forces the ladder past WhatsApp deterministically.
    return {"ok": False, "error": "no_usable_conversation_id"}


def _template_stub(**_k: Any) -> dict[str, Any]:
    CALLS["template"] += 1
    return {"ok": False, "error": "template_disabled"}


def _email_stub(*, to: Any = None, **_k: Any) -> dict[str, Any]:
    CALLS["email"] += 1
    CALLS["email_to"].append(to)
    return {"ok": True, "channel": "email"}


def _install_stubs() -> None:
    _ORIG["session"] = app.send_octopus_whatsapp
    _ORIG["template"] = app.octopus_send_template
    _ORIG["email"] = app.send_outbound_email
    _ORIG["email_enabled"] = app.outbound_email_fallback_enabled
    app.send_octopus_whatsapp = _session_stub
    app.octopus_send_template = _template_stub
    app.send_outbound_email = _email_stub
    app.outbound_email_fallback_enabled = lambda: True


def _restore_stubs() -> None:
    if not _ORIG:
        return
    app.send_octopus_whatsapp = _ORIG["session"]
    app.octopus_send_template = _ORIG["template"]
    app.send_outbound_email = _ORIG["email"]
    app.outbound_email_fallback_enabled = _ORIG["email_enabled"]


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _insert_filtered(cur: Any, table: str, columns: set[str], desired: dict[str, Any]) -> None:
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in ("employee_messages", "hr_tasks", "outbound_delivery_events", "shift_events", "shift_assignments", "employees", "company_modules"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "shift"
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"
    app.os.environ.pop("WATHEFNI_OUTBOUND_EMAIL_FALLBACK", None)  # default on
    _purge()
    # A shift starting ~30 min from now (in Kuwait local time), well inside the
    # scan's look-ahead window. Date is derived from the same instant so a near-
    # midnight run still lands on the right day.
    now_local = app.datetime.now(app.KUWAIT_TZ).replace(tzinfo=None)
    start_dt = now_local + timedelta(minutes=30)
    end_dt = start_dt + timedelta(hours=1)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET name=EXCLUDED.name",
                (COMPANY, "Shift Reminder Email Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            cur.execute(
                "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,'shifts',true) "
                "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                (COMPANY,),
            )
            emp_cols = _columns(cur, "employees")
            _insert_filtered(cur, "employees", emp_cols, {
                "company_code": COMPANY, "phone": PHONE_WITH, "name": "Shift Emp With Email", "employee_key": EMP_WITH,
                "email": EMAIL_WITH, "status": "active", "employment_status": "active",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            _insert_filtered(cur, "employees", emp_cols, {
                "company_code": COMPANY, "phone": PHONE_WITHOUT, "name": "Shift Emp No Email", "employee_key": EMP_WITHOUT,
                "email": "", "status": "active", "employment_status": "active",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            shift_cols = _columns(cur, "shift_assignments")
            for emp_key, phone in ((EMP_WITH, PHONE_WITH), (EMP_WITHOUT, PHONE_WITHOUT)):
                _insert_filtered(cur, "shift_assignments", shift_cols, {
                    "company_code": COMPANY, "employee_key": emp_key, "employee_phone": phone,
                    "shift_date": start_dt.date(), "start_time": start_dt.time().replace(microsecond=0),
                    "end_time": end_dt.time().replace(microsecond=0), "status": "scheduled",
                    "metadata": Json({"smoke": MARKER}),
                })
        conn.commit()
    _install_stubs()


def teardown() -> None:
    _restore_stubs()
    _purge()
    for key in ("WATHEFNI_OUTBOUND_LAYER", "WATHEFNI_OUTBOUND_FLOWS", "WATHEFNI_OUTBOUND_TEMPLATES", "WATHEFNI_DELIVERY_MODE"):
        app.os.environ.pop(key, None)


def _message_row(emp_key: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, last_error, hr_task_id, target_email FROM employee_messages "
                "WHERE company_code=%s AND employee_key=%s AND template_key='shift_reminder' "
                "ORDER BY created_at DESC LIMIT 1",
                (COMPANY, emp_key),
            )
            return dict(cur.fetchone() or {})


def run_checks(checks: Checks) -> None:
    # shift_reminder must be informational so a delivery miss never raises an HR task.
    checks.check("shift_reminder is informational (no HR task on miss)", lambda: od.TEMPLATE_CATALOG["shift_reminder"]["criticality"] == od.CRITICALITY_INFORMATIONAL)

    # Drive the REAL scan once. dry_run=False so it walks the ladder (stubbed),
    # but WATHEFNI_DELIVERY_MODE=dry_run guarantees no real provider I/O.
    CALLS.update(session=0, template=0, email=0, email_to=[])
    result = app.run_shift_reminder_scan(account_id=None, dry_run=False, hours_ahead=2, limit=50)
    checks.check("scan processed both seeded shifts", lambda: int(result.get("count") or 0) >= 2)

    # --- Case A: employee WITH email -> email fallback used ------------------
    a = _message_row(EMP_WITH)
    checks.check("A: shift reminder status is sent_email_fallback", lambda: a.get("status") == od.STATUS_SENT_EMAIL)
    checks.check("A: email provider was called with the employee's email", lambda: EMAIL_WITH in CALLS["email_to"])
    checks.check("A: reasons do NOT include email:no_employee_email", lambda: "no_employee_email" not in str(a.get("last_error") or ""))
    checks.check("A: WhatsApp was tried before email (session attempted)", lambda: CALLS["session"] >= 1)
    checks.check("A: no HR task raised for a delivered reminder", lambda: not a.get("hr_task_id"))
    checks.check("A: target_email recorded on the message", lambda: (a.get("target_email") or "") == EMAIL_WITH)

    # --- Case B: employee WITHOUT email -> calm terminal, no HR task ---------
    b = _message_row(EMP_WITHOUT)
    checks.check("B: result is TERMINAL failed (not a pending retry)", lambda: b.get("status") == od.STATUS_FAILED)
    checks.check("B: reasons include email:no_employee_email", lambda: "no_employee_email" in str(b.get("last_error") or ""))
    checks.check("B: NO HR task (shift_reminder is informational)", lambda: not b.get("hr_task_id"))

    # --- Posture guards ------------------------------------------------------
    checks.check("templates stayed OFF", lambda: app.outbound_templates_enabled() is False)
    checks.check("email recorder saw exactly one send (only the with-email employee)", lambda: CALLS["email"] == 1)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"shift reminder email-fallback regression harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nSHIFT REMINDER EMAIL HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nSHIFT REMINDER EMAIL HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
