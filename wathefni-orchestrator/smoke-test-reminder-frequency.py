"""Reminder frequency caps + send idempotency harness (templates stay OFF).

Proves the behaviour added by the "reminder frequency / digest controls" batch,
with NO network and NO real sends (channel primitives are stubbed; delivery mode
pinned to dry_run):

  1. WATHEFNI_REMINDER_CAPS flag: default ON, kill-switch OFF restores old behaviour.
  2. Cap windows are keyed by template_key: onboarding_reminder/compliance_* = 24h,
     payroll = 72h; EVENT/critical templates (shift_assigned, leave decision,
     onboarding welcome) and shift_reminder are NOT per-employee capped.
  3. A repeated reminder within the window is THROTTLED (STATUS_THROTTLED), with NO
     provider call and NO HR task — it is not a delivery failure.
  4. Low-noise: many throttled attempts in one window collapse to ONE audit row
     per employee/template/window (dedupe), not one row per skipped reminder.
  5. Delivery Issues surfaces a throttled row as kind="info" with calm wording, and
     a real failure as kind="issue" — never mixed.
  6. Idempotency guardrail: an accidentally repeated CRITICAL event (same content,
     no caller dedupe) is deduped — the provider is NOT hit twice.
  7. shift_reminder is per-SHIFT, not per-employee: two DIFFERENT shifts in one
     window each still send (the cap does not wrongly collapse them).
  8. Compliance grouping: multiple due documents for one company collapse into ONE
     grouped reminder per company per run (observed in dry-run, no sends/writes).
  9. WATHEFNI_OUTBOUND_TEMPLATES stays OFF.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-reminder-frequency.py

NEVER point this at production: it writes and deletes throwaway companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "WREMINDERCAPCO"
COMPANY2 = "WREMINDERCAPCO2"
MARKER = "temporary_reminder_cap_harness"

EMP_A = "wcap-emp-a"   # onboarding throttle + delivery-issues visibility
EMP_B = "wcap-emp-b"   # critical idempotency + compliance grouping
EMP_C = "wcap-emp-c"   # shift per-shift (two shifts) + flag-off
PHONE_A = "96550000000911"
PHONE_B = "96550000000912"
PHONE_C = "96550000000913"
EMAIL_A = "wcap-a@example.com"
EMAIL_B = "wcap-b@example.com"
EMAIL_C = "wcap-c@example.com"

CALLS = {"session": 0, "template": 0, "email": 0}
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
    return {"ok": False, "error": "no_usable_conversation_id"}


def _template_stub(**_k: Any) -> dict[str, Any]:
    CALLS["template"] += 1
    return {"ok": False, "error": "template_disabled"}


def _email_stub(**_k: Any) -> dict[str, Any]:
    CALLS["email"] += 1
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
            for company in (COMPANY, COMPANY2):
                for table in ("employee_messages", "hr_tasks", "outbound_delivery_events", "compliance_documents", "employees", "company_modules"):
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
        conn.commit()


def setup() -> None:
    app.os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "shift,onboarding,leave_decision,compliance"
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"
    app.os.environ["WATHEFNI_REMINDER_CAPS"] = "on"
    app.os.environ.pop("WATHEFNI_OUTBOUND_EMAIL_FALLBACK", None)  # default on
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company, label in ((COMPANY, "Reminder Cap Harness"), (COMPANY2, "Reminder Cap Harness 2")):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET name=EXCLUDED.name, metadata=EXCLUDED.metadata",
                    (company, label, Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                # onboarding + compliance modules so the HR-tasks / needs-follow-up
                # surface and the compliance scan are enabled for this company.
                for module in ("onboarding", "compliance"):
                    cur.execute(
                        "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,%s,true) "
                        "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                        (company, module),
                    )
            emp_cols = _columns(cur, "employees")
            for emp_key, phone, name, email in (
                (EMP_A, PHONE_A, "Cap Emp A", EMAIL_A),
                (EMP_B, PHONE_B, "Cap Emp B", EMAIL_B),
                (EMP_C, PHONE_C, "Cap Emp C", EMAIL_C),
            ):
                _insert_filtered(cur, "employees", emp_cols, {
                    "company_code": COMPANY, "phone": phone, "name": name, "employee_key": emp_key,
                    "email": email, "status": "active", "employment_status": "active",
                    "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
                })
            # Two already-expired compliance documents in ONE company -> both "due".
            comp_cols = _columns(cur, "compliance_documents")
            for emp_key, doc_type in ((EMP_A, "civil_id"), (EMP_B, "passport")):
                _insert_filtered(cur, "compliance_documents", comp_cols, {
                    "company_code": COMPANY, "employee_key": emp_key, "document_type": doc_type,
                    "label": doc_type, "status": "received", "expiry_date": "2000-01-01",
                    "warning_days": 30,
                })
        conn.commit()
    _install_stubs()


def teardown() -> None:
    _restore_stubs()
    _purge()
    for key in ("WATHEFNI_OUTBOUND_LAYER", "WATHEFNI_OUTBOUND_FLOWS", "WATHEFNI_OUTBOUND_TEMPLATES", "WATHEFNI_DELIVERY_MODE", "WATHEFNI_REMINDER_CAPS"):
        app.os.environ.pop(key, None)


def _notify(emp_key: str, phone: str, email: str | None, *, flow: str, template_key: str, text: str, variables: dict[str, Any] | None = None, dedupe: str | None = None) -> dict[str, Any]:
    return app.deliver_employee_notification(
        {"employee_key": emp_key, "phone": phone, "email": email, "name": emp_key, "company_code": COMPANY},
        flow=flow, template_key=template_key, text=text, email_subject="Test",
        company_code=COMPANY, variables=variables, dedupe_key=dedupe,
    )


def _throttled_rows(emp_key: str, template_key: str) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM employee_messages WHERE company_code=%s AND employee_key=%s AND template_key=%s AND status=%s",
                (COMPANY, emp_key, template_key, od.STATUS_THROTTLED),
            )
            return int((cur.fetchone() or {}).get("n") or 0)


def run_checks(checks: Checks) -> None:
    # --- 1. Flag behaviour ---------------------------------------------------
    checks.check("caps enabled by default (flag=on)", lambda: app.reminder_caps_enabled() is True)
    app.os.environ["WATHEFNI_REMINDER_CAPS"] = "off"
    checks.check("kill switch off disables caps", lambda: app.reminder_caps_enabled() is False)
    app.os.environ["WATHEFNI_REMINDER_CAPS"] = "on"
    checks.check("caps re-enabled (flag=on)", lambda: app.reminder_caps_enabled() is True)

    # --- 2. Cap windows are keyed by template_key ----------------------------
    checks.check("window: onboarding_reminder = 24h", lambda: app.reminder_cap_window_hours("onboarding_reminder") == 24)
    checks.check("window: compliance_document_required = 24h", lambda: app.reminder_cap_window_hours("compliance_document_required") == 24)
    checks.check("window: compliance_document_expiring = 24h", lambda: app.reminder_cap_window_hours("compliance_document_expiring") == 24)
    checks.check("window: payroll_timesheet_ready = 72h", lambda: app.reminder_cap_window_hours("payroll_timesheet_ready") == 72)
    checks.check("shift_reminder is NOT per-employee capped", lambda: app.reminder_cap_window_hours("shift_reminder") is None)
    checks.check("shift_assigned (event) is NOT capped", lambda: app.reminder_cap_window_hours("shift_assigned") is None)
    checks.check("leave decision (critical) is NOT capped", lambda: app.reminder_cap_window_hours("leave_request_approved") is None)

    # --- 3. Repeated reminder within window is THROTTLED ---------------------
    CALLS.update(session=0, template=0, email=0)
    r1 = _notify(EMP_A, PHONE_A, EMAIL_A, flow="onboarding", template_key="onboarding_reminder", text="Finish onboarding")
    checks.check("1st onboarding reminder is delivered (email fallback)", lambda: r1.get("delivery_status") == od.STATUS_SENT_EMAIL)
    checks.check("1st reminder hit the provider ladder", lambda: CALLS["session"] == 1 and CALLS["email"] == 1)
    CALLS.update(session=0, template=0, email=0)
    r2 = _notify(EMP_A, PHONE_A, EMAIL_A, flow="onboarding", template_key="onboarding_reminder", text="Finish onboarding (again)")
    checks.check("2nd reminder within window is THROTTLED", lambda: r2.get("delivery_status") == od.STATUS_THROTTLED and r2.get("throttled") is True)
    checks.check("throttled: NO provider call", lambda: CALLS["session"] == 0 and CALLS["template"] == 0 and CALLS["email"] == 0)
    checks.check("throttled: NO HR task raised", lambda: r2.get("hr_task_id") is None)

    # --- 4. Low-noise: throttled rows collapse to ONE per window -------------
    _notify(EMP_A, PHONE_A, EMAIL_A, flow="onboarding", template_key="onboarding_reminder", text="x3")
    _notify(EMP_A, PHONE_A, EMAIL_A, flow="onboarding", template_key="onboarding_reminder", text="x4")
    checks.check("many throttled attempts -> exactly ONE audit row per employee/template/window", lambda: _throttled_rows(EMP_A, "onboarding_reminder") == 1)

    # --- 5. Delivery Issues: throttled=info (calm), real failure=issue -------
    # Seed a genuine failure (no email, all channels fail) for a separate employee.
    CALLS.update(session=0, template=0, email=0)
    fail = _notify(EMP_C, PHONE_C, None, flow="onboarding", template_key="onboarding_reminder", text="needs hr")
    follow = app.dashboard_outbound_needs_follow_up({"company_code": COMPANY, "scope": None})
    msgs = follow.get("messages") or []
    thr = next((m for m in msgs if m.get("status") == od.STATUS_THROTTLED), None)
    checks.check("throttled row present in Delivery Issues", lambda: thr is not None)
    checks.check("throttled row is kind=info (calm, not a failure)", lambda: (thr or {}).get("kind") == "info")
    checks.check("throttled wording is calm ('paused')", lambda: "paused" in str((thr or {}).get("reason", "")).lower())
    checks.check("throttled wording leaks no raw status code", lambda: "throttled" not in (str((thr or {}).get("reason", "")) + str((thr or {}).get("suggested_action", ""))).lower())
    issue = next((m for m in msgs if (m.get("status") in (od.STATUS_FAILED, od.STATUS_NEEDS_HR)) and not m.get("has_task")), None)
    if issue is not None:
        checks.check("real delivery failure is kind=issue", lambda: issue.get("kind") == "issue")

    # --- 6. Idempotency: repeated CRITICAL event is deduped ------------------
    CALLS.update(session=0, template=0, email=0)
    c1 = _notify(EMP_B, PHONE_B, EMAIL_B, flow="leave_decision", template_key="leave_request_approved", text="Leave approved for 2026-07-01")
    after_first = dict(CALLS)
    c2 = _notify(EMP_B, PHONE_B, EMAIL_B, flow="leave_decision", template_key="leave_request_approved", text="Leave approved for 2026-07-01")
    checks.check("critical event is NOT throttled (no frequency cap)", lambda: c1.get("delivery_status") != od.STATUS_THROTTLED and c2.get("delivery_status") != od.STATUS_THROTTLED)
    checks.check("repeated identical critical event is deduped (provider not hit twice)", lambda: CALLS["session"] == after_first["session"] and CALLS["email"] == after_first["email"])

    # --- 7. shift_reminder is per-SHIFT: two different shifts both send -------
    CALLS.update(session=0, template=0, email=0)
    s1 = _notify(EMP_C, PHONE_C, EMAIL_C, flow="shift", template_key="shift_reminder", text="Reminder: shift Mon 09:00")
    s2 = _notify(EMP_C, PHONE_C, EMAIL_C, flow="shift", template_key="shift_reminder", text="Reminder: shift Mon 17:00")
    checks.check("two different shift reminders are NOT collapsed by a per-employee cap", lambda: s1.get("delivery_status") == od.STATUS_SENT_EMAIL and s2.get("delivery_status") == od.STATUS_SENT_EMAIL and CALLS["email"] == 2)

    # --- 8. Compliance grouping: one company -> one grouped digest -----------
    scan = app.run_compliance_scan(account_id=None, dry_run=True)
    grouped = scan.get("grouped_documents") or {}
    checks.check("compliance: this company's due docs collapse into ONE group", lambda: COMPANY in grouped)
    checks.check("compliance: both due documents land in the single company group", lambda: grouped.get(COMPANY) == 2)

    # --- 9. Flag OFF restores pre-cap behaviour ------------------------------
    app.os.environ["WATHEFNI_REMINDER_CAPS"] = "off"
    CALLS.update(session=0, template=0, email=0)
    off = _notify(EMP_A, PHONE_A, EMAIL_A, flow="onboarding", template_key="onboarding_reminder", text="flag off send")
    checks.check("flag OFF: reminder is NOT throttled (attempts delivery again)", lambda: off.get("delivery_status") != od.STATUS_THROTTLED and CALLS["session"] == 1)
    app.os.environ["WATHEFNI_REMINDER_CAPS"] = "on"

    # --- 10. Kill switch + templates groundwork ------------------------------
    checks.check("STATUS_THROTTLED is a terminal status", lambda: od.STATUS_THROTTLED in od._TERMINAL_STATUSES)
    checks.check("WATHEFNI_OUTBOUND_TEMPLATES stays off", lambda: app.outbound_templates_enabled() is False)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"reminder frequency / caps harness — companies {COMPANY}/{COMPANY2} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nREMINDER FREQUENCY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nREMINDER FREQUENCY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
