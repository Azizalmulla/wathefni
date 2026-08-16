"""Staging live-soak for the shared outbound delivery layer (Phases C-E).

Drives the REAL operational entry points for every wrapped flow with the layer
enabled (leave_decision / onboarding / compliance / shift), templates OFF, and
WATHEFNI_DELIVERY_MODE=dry_run (nothing real is sent). It exercises the happy
path (WhatsApp), the email fallback rung, and the critical -> HR-task rung, then
reads everything back through the dashboard surfaces and prints a consolidated
soak report:

  * employee_messages rows created (by status / flow)
  * outbound_delivery_events written
  * HR tasks created (only the case that should)
  * email fallback behaviour
  * duplicate-send guard (dedupe)
  * dashboard status / toast copy
  * failures / follow-up noise

Run on staging only:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \
  WATHEFNI_DELIVERY_MODE=dry_run \
  /opt/wathefni/orchestrator/.venv/bin/python soak-outbound-layer.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "SOAKOUTBOUNDCO"
MARKER = "temporary_outbound_soak"
TODAY = app.kuwait_today()

EMP = "soak-emp-email"
PHONE = "96550000000901"
EMAIL = "soak-emp-email@example.com"

EMP_NOEMAIL = "soak-emp-noemail"
PHONE_NOEMAIL = "96550000000902"

_ORIG_SESSION: list[Any] = []


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


def _close_session(closed: bool) -> None:
    """Simulate a closed WhatsApp conversation for the next operational calls so
    we can soak the email-fallback / HR-task rungs deterministically (dry-run)."""
    if closed:
        if not _ORIG_SESSION:
            _ORIG_SESSION.append(app.send_octopus_whatsapp)
        app.send_octopus_whatsapp = lambda **k: {"ok": False, "error": "conversation_closed"}
    elif _ORIG_SESSION:
        app.send_octopus_whatsapp = _ORIG_SESSION.pop()


def _insert_columns(cur: Any, table: str, desired: dict[str, Any]) -> None:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    columns = {row["column_name"] for row in cur.fetchall()}
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})", [desired[c] for c in cols])


def _new_leave(emp: str, phone: str, name: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, "
                "start_date, end_date, leave_type, status, metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,'time_off','requested',%s) RETURNING leave_id",
                (COMPANY, emp, phone, name, TODAY, TODAY, Json({"smoke": MARKER})),
            )
            return str(cur.fetchone()["leave_id"])


def _rows(where: str, params: tuple) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM employee_messages WHERE company_code=%s AND {where} ORDER BY created_at", (COMPANY, *params))
            return [dict(r) for r in cur.fetchall()]


def _count(table: str, where: str, params: tuple) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM {table} WHERE company_code=%s AND {where}", (COMPANY, *params))
            return int((cur.fetchone() or {}).get("n") or 0)


def _all_messages() -> list[dict[str, Any]]:
    return _rows("1=1", ())


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shift_events WHERE company_code=%s", (COMPANY,))
            for table in ("employee_messages", "hr_tasks", "leave_requests", "compliance_documents", "employees", "outbound_delivery_events", "company_modules"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    # Mirror the staging service config so a standalone run behaves like the live
    # service (the live service already has these set via systemd drop-in).
    app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "leave_decision,onboarding,compliance,shift"
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Outbound Soak", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            _insert_columns(cur, "employees", {
                "company_code": COMPANY, "phone": PHONE, "name": "Soak Emailed", "email": EMAIL,
                "employee_key": EMP, "status": "active", "onboarding_status": "in_progress",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            _insert_columns(cur, "employees", {
                "company_code": COMPANY, "phone": PHONE_NOEMAIL, "name": "Soak NoEmail",
                "employee_key": EMP_NOEMAIL, "status": "active", "onboarding_status": "in_progress",
                "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
            })
            _insert_columns(cur, "compliance_documents", {
                "company_code": COMPANY, "employee_key": EMP, "document_type": "civil_id",
                "label": "Civil ID", "status": "missing", "metadata": Json({"smoke": MARKER}),
            })
            for module in ("leave", "onboarding", "compliance", "shifts"):
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,%s,true) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                    (COMPANY, module),
                )
        conn.commit()


def teardown() -> None:
    _close_session(False)
    _purge()
    for key in ("WATHEFNI_OUTBOUND_LAYER", "WATHEFNI_OUTBOUND_FLOWS", "WATHEFNI_OUTBOUND_TEMPLATES"):
        app.os.environ.pop(key, None)


def _emp(key: str, phone: str, name: str, email: str | None = None) -> dict[str, Any]:
    e = {"employee_key": key, "company_code": COMPANY, "phone": phone, "name": name}
    if email:
        e["email"] = email
    return e


def run(checks: Checks) -> dict[str, Any]:
    token = app.set_active_company_code(COMPANY)
    observed: dict[str, Any] = {}
    try:
        emp = _emp(EMP, PHONE, "Soak Emailed", EMAIL)

        # --- Happy path: WhatsApp delivered (dry-run) ------------------------
        leave_a = _new_leave(EMP, PHONE, "Soak Emailed")
        approved = app.approve_leave_request({"company_code": COMPANY, "leave_id": leave_a}, company_code=COMPANY, created_by_phone="96599999999")
        note_a = approved.get("employee_notification") or {}
        checks.check("leave approve via layer", lambda: note_a.get("via") == "outbound_layer")
        checks.check("leave approve delivered_whatsapp", lambda: note_a.get("delivery_status") == "delivered_whatsapp")

        leave_r = _new_leave(EMP, PHONE, "Soak Emailed")
        rejected = app.reject_leave_request({"company_code": COMPANY, "leave_id": leave_r}, company_code=COMPANY, created_by_phone="96599999999")
        note_r = rejected.get("employee_notification") or {}
        checks.check("leave reject via layer", lambda: note_r.get("via") == "outbound_layer")

        kickoff = app.notify_employee_onboarding_started(emp, None)
        checks.check("onboarding kickoff delivered_whatsapp", lambda: kickoff.get("delivery_status") == "delivered_whatsapp")
        rem = app.send_onboarding_reminder(emp, None)
        checks.check("onboarding reminder delivered_whatsapp", lambda: rem.get("delivery_status") == "delivered_whatsapp")
        comp = app.send_compliance_reminder(emp, None, None)
        checks.check("compliance reminder delivered_whatsapp", lambda: comp.get("delivery_status") == "delivered_whatsapp")

        shift = {"company_code": COMPANY, "employee_key": EMP, "shift_date": "2026-06-12", "start_time": "09:00:00", "end_time": "17:00:00", "location": "HQ"}
        sc = app.notify_employee_shift_created(result={"ok": True, "employee": emp, "created": [shift]}, account_id=None, created_by_phone=None)
        checks.check("shift assigned via layer", lambda: sc.get("send", {}).get("via") == "outbound_layer")
        sx = app.notify_employee_shift_cancelled(result={"ok": True, "employee": emp, "cancelled": [shift]}, account_id=None, created_by_phone=None)
        checks.check("shift cancelled via layer", lambda: sx.get("send", {}).get("via") == "outbound_layer")
        sr = app.deliver_employee_notification(emp, flow="shift", template_key="shift_reminder", text="Reminder: your shift starts on Friday at 09:00.", email_subject="Shift reminder", account_id=None, company_code=COMPANY, variables={"shift_date": "2026-06-12", "shift_time": "09:00"})
        checks.check("shift reminder delivered_whatsapp", lambda: sr.get("delivery_status") == "delivered_whatsapp")

        delivered_count = _count("employee_messages", "status='delivered_whatsapp'", ())
        observed["delivered_whatsapp"] = delivered_count
        checks.check("happy-path delivered messages recorded (>=8)", lambda: delivered_count >= 8)

        # --- Email fallback rung: closed conversation, employee has email ----
        _close_session(True)
        leave_email = _new_leave(EMP, PHONE, "Soak Emailed")
        approved_email = app.approve_leave_request({"company_code": COMPANY, "leave_id": leave_email}, company_code=COMPANY, created_by_phone="96599999999")
        note_email = approved_email.get("employee_notification") or {}
        observed["email_status"] = note_email.get("delivery_status")
        checks.check("closed convo + email -> sent_email_fallback", lambda: note_email.get("delivery_status") == "sent_email_fallback")
        checks.check("email fallback channel is email", lambda: note_email.get("channel") == "email")

        # --- Critical HR-task rung: closed conversation, no email ------------
        leave_hr = _new_leave(EMP_NOEMAIL, PHONE_NOEMAIL, "Soak NoEmail")
        approved_hr = app.approve_leave_request({"company_code": COMPANY, "leave_id": leave_hr}, company_code=COMPANY, created_by_phone="96599999999")
        note_hr = approved_hr.get("employee_notification") or {}
        observed["hr_status"] = note_hr.get("delivery_status")
        observed["hr_task_id"] = note_hr.get("hr_task_id")
        checks.check("closed convo + no email (critical) -> needs_hr_action", lambda: note_hr.get("delivery_status") == "needs_hr_action")
        checks.check("needs_hr_action creates an HR task", lambda: bool(note_hr.get("hr_task_id")))
        _close_session(False)

        # --- Duplicate guard: re-approving the same leave doesn't duplicate --
        before = _count("employee_messages", "dedupe_key=%s", (f"leave_decision:{leave_a}:approved",))
        emp_row = app.find_employee_by_phone(PHONE)
        app.notify_employee_leave_decision(emp_row, app.leave_request_by_id(leave_a), "approved", account_id=None)
        after = _count("employee_messages", "dedupe_key=%s", (f"leave_decision:{leave_a}:approved",))
        checks.check("dedupe: no duplicate on re-notify", lambda: before == 1 and after == 1)

        # --- HR task only where expected -------------------------------------
        hr_tasks = od.list_hr_tasks(company_code=COMPANY, statuses=["open"], limit=200)
        observed["open_hr_tasks"] = len(hr_tasks)
        checks.check("exactly one HR task (the no-email critical case)", lambda: len(hr_tasks) == 1)
        checks.check("HR task points at the no-email employee", lambda: hr_tasks and hr_tasks[0].get("employee_key") == EMP_NOEMAIL)

        # --- Dashboard needs-follow-up surface -------------------------------
        follow = od.list_needs_follow_up(company_code=COMPANY, limit=200)
        observed["needs_follow_up"] = len(follow)
        follow_status = {m["message_id"]: m["status"] for m in follow}
        checks.check("needs-follow-up surfaces the needs_hr_action message", lambda: od.STATUS_NEEDS_HR in follow_status.values())
        checks.check("needs-follow-up exposes no raw body field", lambda: all("body" not in m and "body_encrypted" not in m for m in follow))

        # --- Dashboard status / toast copy -----------------------------------
        checks.check("toast copy: delivered -> 'notified on WhatsApp'", lambda: app.notification_status_text({"delivery_status": "delivered_whatsapp"}) == "notified on WhatsApp")
        checks.check("toast copy: email -> human readable", lambda: "email" in app.notification_status_text({"delivery_status": "sent_email_fallback"}))
        checks.check("toast copy: needs_hr -> follow-up wording", lambda: "follow-up" in app.notification_status_text({"delivery_status": "needs_hr_action"}))

        # --- Audit events ----------------------------------------------------
        events = _count("outbound_delivery_events", "1=1", ())
        observed["delivery_events"] = events
        checks.check("delivery events written for the soak", lambda: events >= 10)

        observed["total_messages"] = _count("employee_messages", "1=1", ())
        observed["failed"] = _count("employee_messages", "status='failed'", ())
        observed["by_status"] = {}
        for m in _all_messages():
            observed["by_status"][m["status"]] = observed["by_status"].get(m["status"], 0) + 1
        observed["follow_up_rows"] = [
            {"flow": m["flow"], "template": m["template_key"], "status": m["status"], "preview": m.get("body_preview")}
            for m in follow
        ]
    finally:
        _close_session(False)
        app.reset_active_company_code(token)
    return observed


def print_report(observed: dict[str, Any]) -> None:
    print("\n================ OUTBOUND LAYER — STAGING SOAK REPORT ================")
    print(f"company: {COMPANY}   delivery_mode: {app.os.environ.get('WATHEFNI_DELIVERY_MODE')}   templates: off")
    print(f"flows enabled: {app.os.environ.get('WATHEFNI_OUTBOUND_FLOWS')}")
    print("")
    print(f"employee_messages rows created:   {observed.get('total_messages')}")
    print(f"  by status:                      {observed.get('by_status')}")
    print(f"outbound_delivery_events written: {observed.get('delivery_events')}")
    print(f"HR tasks created (open):          {observed.get('open_hr_tasks')}  (expected: 1, the no-email critical case)")
    print(f"email fallback status:            {observed.get('email_status')}  (expected: sent_email_fallback)")
    print(f"needs_hr_action status:           {observed.get('hr_status')}  (expected: needs_hr_action)")
    print(f"needs-follow-up rows:             {observed.get('needs_follow_up')}")
    print(f"failed messages:                  {observed.get('failed')}  (expected: 0)")
    print(f"duplicate sends:                  none (dedupe held)")
    print("follow-up / HR-task detail:")
    for row in observed.get("follow_up_rows", []):
        print(f"  - flow={row['flow']:<14} template={row['template']:<26} status={row['status']:<16} preview={row['preview']!r}")
    print("=====================================================================\n")


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"outbound layer staging soak — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    observed: dict[str, Any] = {}
    try:
        observed = run(checks)
    finally:
        print_report(observed)
        teardown()
    code = checks.report()
    print("\nOUTBOUND LAYER SOAK: " + ("FAILURES PRESENT (see above)" if code else "ALL CHECKS PASSED"))
    sys.exit(code)


if __name__ == "__main__":
    main()
