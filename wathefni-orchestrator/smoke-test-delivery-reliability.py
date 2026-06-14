"""Post-hire delivery reliability harness (before WhatsApp templates).

Proves the behaviour added by the "delivery reliability" batch, with NO network
and NO real sends (channel primitives are stubbed; WATHEFNI_DELIVERY_MODE is
pinned to dry_run as a safety net):

  1. Email fallback succeeds when the WhatsApp session is closed and approved
     templates are OFF, as long as the employee has an email on file (the core
     "templates unavailable" requirement).
  2. With no email + templates off, the message terminates honestly (failed /
     needs_hr_action) and surfaces in needs-follow-up — never a fake success.
  3. list_needs_follow_up exposes target_email so the endpoint can compute
     whether an email is on file (no raw body / encrypted body leaks).
  4. _humanize_delivery_failure turns internal reason codes into calm HR copy
     and never leaks raw provider/error codes.
  5. messaging_readiness reports templates-off + email coverage honestly.
  6. The shift reminder scan stamps reminder_sent_at on EVERY attempt (success
     or failure) so a failed reminder does not re-fire every hour, passes the
     employee email through for fallback, and records the outcome.
  7. The onboarding reminder scan throttles a FAILED reminder with last_reminded_at
     so it does not re-fire hourly.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-delivery-reliability.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "DELIVERYRELIABILITYCO"
MARKER = "temporary_delivery_reliability_harness"

EMP_EMAIL = "deliv-emp-email"
EMP_NOEMAIL = "deliv-emp-noemail"
PHONE_EMAIL = "96550000000901"
PHONE_NOEMAIL = "96550000000902"
EMAIL_ADDR = "deliv-emp-email@example.com"

STUBS: dict[str, Any] = {
    "session": {"ok": False, "error": "no_usable_conversation_id"},
    "email": {"ok": True, "channel": "email"},
    "email_enabled": True,
}
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


def _install_stubs() -> None:
    # Session + email are stubbed; the template rung is left REAL so it returns
    # template_disabled while WATHEFNI_OUTBOUND_TEMPLATES is off — matching prod.
    _ORIG["session"] = app.send_octopus_whatsapp
    _ORIG["email"] = app.send_outbound_email
    _ORIG["email_enabled"] = app.outbound_email_fallback_enabled
    app.send_octopus_whatsapp = lambda **k: dict(STUBS["session"])
    app.send_outbound_email = lambda **k: dict(STUBS["email"])
    app.outbound_email_fallback_enabled = lambda: bool(STUBS["email_enabled"])


def _restore_stubs() -> None:
    if not _ORIG:
        return
    app.send_octopus_whatsapp = _ORIG["session"]
    app.send_outbound_email = _ORIG["email"]
    app.outbound_email_fallback_enabled = _ORIG["email_enabled"]


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], emp_key: str, phone: str, name: str, email: str | None) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "phone": phone, "name": name, "employee_key": emp_key,
        "email": email, "status": "active", "employment_status": "active",
        "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _insert_module(cur: Any, columns: set[str], module_key: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "module_key": module_key, "enabled": True,
        "source": "delivery_reliability_smoke", "settings": Json({"automation_enabled": True}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(
        f"INSERT INTO company_modules ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))}) "
        f"ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, settings=EXCLUDED.settings",
        [desired[c] for c in cols],
    )


def _insert_shift(cur: Any, columns: set[str], emp_key: str, phone: str, name: str) -> str:
    now_local = app.datetime.now(app.KUWAIT_TZ).replace(tzinfo=None)
    target = now_local + timedelta(minutes=30)
    desired: dict[str, Any] = {
        "company_code": COMPANY, "employee_key": emp_key, "employee_phone": phone, "employee_name": name,
        "shift_date": target.date(), "start_time": target.time().replace(microsecond=0),
        "end_time": (target + timedelta(hours=8)).time().replace(microsecond=0),
        "timezone": "Asia/Kuwait", "status": "scheduled", "metadata": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(
        f"INSERT INTO shift_assignments ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))}) RETURNING shift_id",
        [desired[c] for c in cols],
    )
    return str(cur.fetchone()["shift_id"])


def _insert_onboarding_item(cur: Any, columns: set[str], emp_key: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "employee_key": emp_key, "item_id": "civil_id",
        "label": "Civil ID", "item_type": "document", "document_type": "civil_id",
        "required": True, "status": "pending", "raw_json": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO onboarding_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


SHIFT_IDS: dict[str, str] = {}


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # onboarding_items is keyed by employee_key (no company_code column).
            cur.execute("DELETE FROM onboarding_items WHERE employee_key IN (%s,%s)", (EMP_EMAIL, EMP_NOEMAIL))
            for table in ("employee_messages", "hr_tasks", "message_template_map", "outbound_delivery_events", "shift_events", "shift_assignments", "employees", "company_modules"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "shift,onboarding,leave_decision,compliance"
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"
    app.os.environ.pop("WATHEFNI_OUTBOUND_EMAIL_FALLBACK", None)  # default on
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                (COMPANY, "Delivery Reliability Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            mod_cols = _columns(cur, "company_modules")
            for module in ("shifts", "onboarding"):
                _insert_module(cur, mod_cols, module)
            emp_cols = _columns(cur, "employees")
            _insert_employee(cur, emp_cols, EMP_EMAIL, PHONE_EMAIL, "Has Email", EMAIL_ADDR)
            _insert_employee(cur, emp_cols, EMP_NOEMAIL, PHONE_NOEMAIL, "No Email", None)
            shift_cols = _columns(cur, "shift_assignments")
            SHIFT_IDS["email"] = _insert_shift(cur, shift_cols, EMP_EMAIL, PHONE_EMAIL, "Has Email")
            SHIFT_IDS["noemail"] = _insert_shift(cur, shift_cols, EMP_NOEMAIL, PHONE_NOEMAIL, "No Email")
            item_cols = _columns(cur, "onboarding_items")
            _insert_onboarding_item(cur, item_cols, EMP_NOEMAIL)
        conn.commit()
    _install_stubs()


def teardown() -> None:
    _restore_stubs()
    _purge()
    for key in ("WATHEFNI_OUTBOUND_LAYER", "WATHEFNI_OUTBOUND_FLOWS", "WATHEFNI_OUTBOUND_TEMPLATES", "WATHEFNI_DELIVERY_MODE"):
        app.os.environ.pop(key, None)


def _message_row(message_id: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_messages WHERE message_id=%s", (message_id,))
            return dict(cur.fetchone())


def _shift_reminder_sent_at(shift_id: str) -> Any:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT reminder_sent_at FROM shift_assignments WHERE shift_id=%s", (shift_id,))
            row = cur.fetchone()
            return row["reminder_sent_at"] if row else None


def _onboarding_last_reminded(emp_key: str) -> Any:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max(last_reminded_at) AS m FROM onboarding_items WHERE employee_key=%s", (emp_key,))
            return (cur.fetchone() or {}).get("m")


def run_checks(checks: Checks) -> None:
    # --- 4. Humanizer: plain copy, no raw codes ------------------------------
    reason, action = app._humanize_delivery_failure(
        last_error="session:no_usable_conversation_id; template:template_disabled; email:no_employee_email",
        employee_name="Ahmad", has_email=False,
    )
    checks.check("humanize: mentions WhatsApp + email, not codes", lambda: "WhatsApp" in reason and "email" in reason.lower())
    checks.check("humanize: suggested action mentions adding email", lambda: "email" in action.lower())
    checks.check("humanize: no raw reason codes leak", lambda: not any(tok in (reason + action) for tok in ["session:", "template:", "no_usable_conversation_id", "template_disabled", "no_employee_email"]))
    checks.check("flow label humanizes shift", lambda: app._delivery_flow_label("shift") == "Shift")
    checks.check("flow label humanizes leave_decision", lambda: app._delivery_flow_label("leave_decision") == "Leave")

    # --- 5. Messaging readiness ----------------------------------------------
    mr = app.messaging_readiness(COMPANY)
    checks.check("readiness: templates not configured", lambda: mr["templates_configured"] is False)
    checks.check("readiness: email fallback available", lambda: mr["email_fallback"] is True)
    checks.check("readiness: 2 employees total", lambda: mr["employees_total"] == 2)
    checks.check("readiness: 1 with email, 1 missing", lambda: mr["employees_with_email"] == 1 and mr["employees_missing_email"] == 1)
    checks.check("readiness: summary says templates not configured yet", lambda: "not configured yet" in mr["summary"])

    # --- 1. Email fallback when session closed + templates off ----------------
    r_email = app.deliver_to_employee(
        company_code=COMPANY, flow="shift", template_key="shift_reminder",
        employee={"employee_key": EMP_EMAIL, "phone": PHONE_EMAIL, "email": EMAIL_ADDR, "name": "Has Email"},
        text="Shift reminder", email_subject="Shift reminder", dedupe_key="email-fallback-ok",
    )
    checks.check("closed session + templates off + email -> sent via email", lambda: r_email["status"] == od.STATUS_SENT_EMAIL)
    checks.check("email fallback reports channel email", lambda: r_email["channel_used"] == "email")
    checks.check("email fallback reports ok", lambda: r_email["ok"] is True)

    # --- 2. No email -> honest failure (informational, no HR task) ------------
    r_fail = app.deliver_to_employee(
        company_code=COMPANY, flow="shift", template_key="shift_reminder",
        employee={"employee_key": EMP_NOEMAIL, "phone": PHONE_NOEMAIL, "name": "No Email"},
        text="Shift reminder", email_subject="Shift reminder", dedupe_key="no-email-fails",
    )
    checks.check("no email + templates off -> failed (no fake success)", lambda: r_fail["status"] == od.STATUS_FAILED)
    checks.check("informational failure raises NO HR task", lambda: r_fail.get("hr_task_id") is None)

    # --- 3. needs-follow-up exposes target_email, no raw body -----------------
    follow = od.list_needs_follow_up(company_code=COMPANY, limit=200)
    checks.check("needs-follow-up includes target_email field", lambda: all("target_email" in m for m in follow))
    checks.check("needs-follow-up has the failed no-email message", lambda: any(m["message_id"] == r_fail["message_id"] and not m.get("target_email") for m in follow))
    checks.check("needs-follow-up exposes no raw/encrypted body", lambda: all("body_encrypted" not in m for m in follow))

    # --- 6. Shift reminder scan: stamp every attempt + pass email -------------
    scan1 = app.run_shift_reminder_scan(account_id="default", dry_run=False, limit=200, hours_ahead=2)
    ours = {str(e.get("shift_id")): e for e in scan1.get("results", []) if str(e.get("shift_id")) in SHIFT_IDS.values()}
    checks.check("scan attempts both seeded shifts", lambda: len(ours) == 2)
    checks.check("scan stamps reminder_sent_at on the email shift", lambda: _shift_reminder_sent_at(SHIFT_IDS["email"]) is not None)
    checks.check("scan stamps reminder_sent_at on the FAILED no-email shift", lambda: _shift_reminder_sent_at(SHIFT_IDS["noemail"]) is not None)

    scan2 = app.run_shift_reminder_scan(account_id="default", dry_run=False, limit=200, hours_ahead=2)
    again = {str(e.get("shift_id")) for e in scan2.get("results", [])}
    checks.check("failed shift reminder does NOT re-fire on the next scan", lambda: SHIFT_IDS["noemail"] not in again and SHIFT_IDS["email"] not in again)

    # The email shift's message carried the employee email (fallback path used).
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, target_email FROM employee_messages WHERE company_code=%s AND employee_key=%s AND flow='shift' ORDER BY created_at DESC LIMIT 1", (COMPANY, EMP_EMAIL))
            email_msg = dict(cur.fetchone() or {})
            cur.execute("SELECT status FROM employee_messages WHERE company_code=%s AND employee_key=%s AND flow='shift' ORDER BY created_at DESC LIMIT 1", (COMPANY, EMP_NOEMAIL))
            noemail_msg = dict(cur.fetchone() or {})
    checks.check("scan delivered the email shift via email (email passed through)", lambda: email_msg.get("status") == od.STATUS_SENT_EMAIL and bool(email_msg.get("target_email")))
    checks.check("scan recorded the no-email shift as failed", lambda: noemail_msg.get("status") == od.STATUS_FAILED)

    # --- 7. Onboarding reminder scan: failed reminder is throttled ------------
    _orig_candidates = app.pending_onboarding_reminder_candidates
    _orig_send = app.send_onboarding_reminder
    try:
        emp_row = {"employee_key": EMP_NOEMAIL, "phone": PHONE_NOEMAIL, "name": "No Email", "company_code": COMPANY}
        app.pending_onboarding_reminder_candidates = lambda **k: [dict(emp_row)]
        app.send_onboarding_reminder = lambda employee, account_id: {"ok": False, "send": {"error": "no_usable_conversation_id"}, "employee": employee}
        app.run_onboarding_reminder_scan(account_id="default", dry_run=False, limit=5, min_hours_since_last=24)
    finally:
        app.pending_onboarding_reminder_candidates = _orig_candidates
        app.send_onboarding_reminder = _orig_send
    checks.check("failed onboarding reminder stamps last_reminded_at (throttled)", lambda: _onboarding_last_reminded(EMP_NOEMAIL) is not None)
    # With the real candidate query and the freshly-stamped cooldown, it is excluded.
    checks.check("throttled onboarding reminder is excluded within cooldown", lambda: not any(c.get("employee_key") == EMP_NOEMAIL for c in app.pending_onboarding_reminder_candidates(min_hours_since_last=24)))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"delivery reliability harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nDELIVERY RELIABILITY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nDELIVERY RELIABILITY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
