"""Phase E: shift flows -> shared outbound delivery layer (staging).

Proves that the shift assignment, shift cancellation, and shift reminder messages
route through deliver_to_employee when the `shift` flow is enabled
(WATHEFNI_OUTBOUND_FLOWS includes shift) — recording an employee_messages row with
the right template and flow, keeping the shift_events bookkeeping intact, and
(under dry-run) marking delivered — while with the flow OFF the legacy
direct-send path is used and no employee_messages row is created.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_DELIVERY_MODE=dry_run \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-outbound-shift.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "OUTBOUNDSHIFTCO"
MARKER = "temporary_outbound_shift_harness"

EMP = "outbound-shift-emp"
PHONE = "96550000000701"
EMAIL = "outbound-shift-emp@example.com"


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


def _flows(value: str | None) -> None:
    if value:
        app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
        app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = value
    else:
        app.os.environ.pop("WATHEFNI_OUTBOUND_LAYER", None)
        app.os.environ.pop("WATHEFNI_OUTBOUND_FLOWS", None)


def _employee() -> dict[str, Any]:
    return {"employee_key": EMP, "company_code": COMPANY, "phone": PHONE, "email": EMAIL, "name": "Sara Shift"}


def _shift() -> dict[str, Any]:
    # No shift_id -> shift_events.shift_id is nullable, so we avoid an FK to a real
    # shift_assignments row while still exercising the event bookkeeping.
    return {"company_code": COMPANY, "employee_key": EMP, "shift_date": "2026-06-12",
            "start_time": "09:00:00", "end_time": "17:00:00", "location": "HQ"}


def _messages(template_key: str) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employee_messages WHERE company_code=%s AND template_key=%s ORDER BY created_at",
                (COMPANY, template_key),
            )
            return [dict(r) for r in cur.fetchall()]


def _shift_events(event_type: str) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM shift_events WHERE company_code=%s AND event_type=%s",
                (COMPANY, event_type),
            )
            return int((cur.fetchone() or {}).get("n") or 0)


def _clear_messages() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employee_messages WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM hr_tasks WHERE company_code=%s", (COMPANY,))
        conn.commit()


def _insert_columns(cur: Any, table: str, desired: dict[str, Any]) -> None:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    columns = {row["column_name"] for row in cur.fetchall()}
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})", [desired[c] for c in cols])


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shift_events WHERE company_code=%s", (COMPANY,))
            for table in ("employee_messages", "hr_tasks", "employees", "company_modules"):
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
                (COMPANY, "Outbound Shift Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            _insert_columns(cur, "employees", {
                "company_code": COMPANY, "phone": PHONE, "name": "Sara Shift", "email": EMAIL,
                "employee_key": EMP, "status": "active",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            cur.execute(
                "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,%s,true) "
                "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                (COMPANY, "shifts"),
            )
        conn.commit()


def teardown() -> None:
    _purge()
    _flows(None)


def run_checks(checks: Checks) -> None:
    token = app.set_active_company_code(COMPANY)
    try:
        emp = _employee()

        # --- Flow ON ---------------------------------------------------------
        _flows("shift")

        created = app.notify_employee_shift_created(
            result={"ok": True, "employee": emp, "created": [_shift()]},
            account_id=None,
            created_by_phone=None,
        )
        checks.check("shift created via layer", lambda: created.get("send", {}).get("via") == "outbound_layer")
        checks.check("shift created delivered under dry-run", lambda: created.get("send", {}).get("delivery_status") == "delivered_whatsapp")
        assigned = _messages("shift_assigned")
        checks.check("shift created one shift_assigned message", lambda: len(assigned) == 1)
        checks.check("shift_assigned message flow is shift", lambda: assigned and assigned[0]["flow"] == "shift")
        checks.check("shift created wrote employee_notified event", lambda: _shift_events("employee_notified") == 1)

        cancelled = app.notify_employee_shift_cancelled(
            result={"ok": True, "employee": emp, "cancelled": [_shift()]},
            account_id=None,
            created_by_phone=None,
        )
        checks.check("shift cancelled via layer", lambda: cancelled.get("send", {}).get("via") == "outbound_layer")
        cxl = _messages("shift_cancelled")
        checks.check("shift cancelled one shift_cancelled message", lambda: len(cxl) == 1)
        checks.check("shift cancelled wrote cancellation event", lambda: _shift_events("employee_cancellation_notified") == 1)

        # Shift reminder uses the same helper + the shift_reminder template; prove
        # it routes without depending on the time-windowed reminder scan.
        reminder = app.deliver_employee_notification(
            emp,
            flow="shift",
            template_key="shift_reminder",
            text="Reminder: your shift starts on Friday at 09:00.",
            email_subject="Shift reminder",
            account_id=None,
            company_code=COMPANY,
            variables={"shift_date": "2026-06-12", "shift_time": "09:00"},
        )
        checks.check("shift reminder via layer", lambda: reminder.get("via") == "outbound_layer")
        checks.check("shift reminder created one shift_reminder message", lambda: len(_messages("shift_reminder")) == 1)

        # --- Flow OFF: legacy direct send, no employee_messages rows --------
        _clear_messages()
        _flows(None)
        created_off = app.notify_employee_shift_created(
            result={"ok": True, "employee": emp, "created": [_shift()]},
            account_id=None,
            created_by_phone=None,
        )
        checks.check("flag OFF: shift created not via layer", lambda: created_off.get("send", {}).get("via") != "outbound_layer")
        checks.check("flag OFF: shift created still succeeds (legacy)", lambda: created_off.get("ok") is True)
        checks.check("flag OFF: no shift_assigned employee_message rows", lambda: len(_messages("shift_assigned")) == 0)
    finally:
        app.reset_active_company_code(token)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"outbound shift harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nOUTBOUND SHIFT HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nOUTBOUND SHIFT HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
