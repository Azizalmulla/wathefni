"""Phase C: leave decision -> shared outbound delivery layer (staging).

Proves that approving / rejecting a leave request routes the employee
notification through deliver_to_employee when WATHEFNI_OUTBOUND_FLOWS includes
leave_decision — recording an employee_messages row and (under dry-run) marking
it delivered — while with the flow OFF the legacy direct-send path is used and
no employee_messages row is created. Also checks dedupe idempotency.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_DELIVERY_MODE=dry_run \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-outbound-leave.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "OUTBOUNDLEAVECO"
MARKER = "temporary_outbound_leave_harness"
TODAY = app.kuwait_today()

EMP = "outbound-leave-emp"
PHONE = "96550000000701"
EMAIL = "outbound-leave-emp@example.com"


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


def _flow(on: bool) -> None:
    if on:
        app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
        app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "leave_decision"
    else:
        app.os.environ.pop("WATHEFNI_OUTBOUND_LAYER", None)
        app.os.environ.pop("WATHEFNI_OUTBOUND_FLOWS", None)


def _new_leave() -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, "
                "start_date, end_date, leave_type, status, metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,'time_off','requested',%s) RETURNING leave_id",
                (COMPANY, EMP, PHONE, "Layla Leave", TODAY, TODAY, Json({"smoke": MARKER})),
            )
            return str(cur.fetchone()["leave_id"])


def _messages_for(leave_id: str, decision: str) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employee_messages WHERE company_code=%s AND dedupe_key=%s",
                (COMPANY, f"leave_decision:{leave_id}:{decision}"),
            )
            return [dict(r) for r in cur.fetchall()]


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in ("employee_messages", "hr_tasks", "leave_requests", "employees"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM outbound_delivery_events WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Outbound Leave Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
            columns = {row["column_name"] for row in cur.fetchall()}
            desired: dict[str, Any] = {
                "company_code": COMPANY, "phone": PHONE, "name": "Layla Leave", "email": EMAIL,
                "employee_key": EMP, "status": "active", "onboarding_status": "complete",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            }
            cols = [c for c in desired if c in columns]
            cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})", [desired[c] for c in cols])
        conn.commit()


def teardown() -> None:
    _purge()
    _flow(False)


def run_checks(checks: Checks) -> None:
    token = app.set_active_company_code(COMPANY)
    try:
        # --- Flow ON: approve routes through the delivery layer ---------------
        _flow(True)
        leave_a = _new_leave()
        approved = app.approve_leave_request({"company_code": COMPANY, "leave_id": leave_a}, company_code=COMPANY, created_by_phone="96599999999")
        note_a = approved.get("employee_notification") if isinstance(approved.get("employee_notification"), dict) else {}
        checks.check("approve succeeds", lambda: approved.get("ok") is True)
        checks.check("approve notification went via outbound layer", lambda: note_a.get("via") == "outbound_layer")
        checks.check("approve delivered under dry-run", lambda: note_a.get("delivery_status") == "delivered_whatsapp")
        msgs_a = _messages_for(leave_a, "approved")
        checks.check("approve created exactly one employee_message", lambda: len(msgs_a) == 1)
        checks.check("approve message uses leave_request_approved template", lambda: msgs_a and msgs_a[0]["template_key"] == "leave_request_approved")
        checks.check("approve message flow is leave_decision", lambda: msgs_a and msgs_a[0]["flow"] == "leave_decision")
        checks.check("approve message is terminal-delivered", lambda: msgs_a and msgs_a[0]["status"] == "delivered_whatsapp")

        # --- Flow ON: reject uses the rejection template ----------------------
        leave_r = _new_leave()
        rejected = app.reject_leave_request({"company_code": COMPANY, "leave_id": leave_r}, company_code=COMPANY, created_by_phone="96599999999")
        note_r = rejected.get("employee_notification") if isinstance(rejected.get("employee_notification"), dict) else {}
        checks.check("reject succeeds", lambda: rejected.get("ok") is True)
        checks.check("reject notification went via outbound layer", lambda: note_r.get("via") == "outbound_layer")
        msgs_r = _messages_for(leave_r, "rejected")
        checks.check("reject message uses leave_request_rejected template", lambda: msgs_r and msgs_r[0]["template_key"] == "leave_request_rejected")

        # --- Dedupe: re-notifying the same decision does not duplicate --------
        employee = app.find_employee_by_phone(PHONE)
        leave_row = app.leave_request_by_id(leave_a)
        app.notify_employee_leave_decision(employee, leave_row, "approved", account_id=None)
        checks.check("re-notify is idempotent on dedupe_key", lambda: len(_messages_for(leave_a, "approved")) == 1)

        # --- HR-readable status text -----------------------------------------
        checks.check("status text maps delivered -> notified", lambda: app.notification_status_text({"delivery_status": "delivered_whatsapp"}) == "notified on WhatsApp")
        checks.check("status text maps needs_hr_action -> follow-up", lambda: "follow-up" in app.notification_status_text({"delivery_status": "needs_hr_action"}))

        # --- Flow OFF: legacy direct-send path, no employee_messages row ------
        _flow(False)
        leave_off = _new_leave()
        approved_off = app.approve_leave_request({"company_code": COMPANY, "leave_id": leave_off}, company_code=COMPANY, created_by_phone="96599999999")
        note_off = approved_off.get("employee_notification") if isinstance(approved_off.get("employee_notification"), dict) else {}
        checks.check("flag OFF: approve still succeeds", lambda: approved_off.get("ok") is True)
        checks.check("flag OFF: notification is NOT via outbound layer", lambda: note_off.get("via") != "outbound_layer")
        checks.check("flag OFF: no employee_message row created", lambda: len(_messages_for(leave_off, "approved")) == 0)
    finally:
        app.reset_active_company_code(token)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"outbound leave harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nOUTBOUND LEAVE HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nOUTBOUND LEAVE HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
