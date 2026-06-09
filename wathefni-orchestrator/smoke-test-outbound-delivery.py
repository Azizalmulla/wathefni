"""Shared outbound delivery layer harness (Phase A, staging).

Proves the resilient channel ladder in outbound_delivery.deliver_to_employee:
WhatsApp session -> approved template -> email fallback -> HR task, plus the
retry sweep, idempotency, sensitivity body-storage policy, and the feature-flag
gates. The channel primitives on `app` are stubbed so we can simulate a closed
WhatsApp conversation deterministically (no network); WATHEFNI_DELIVERY_MODE is
also pinned to dry_run as a safety net so any un-stubbed path simulates instead
of sending. A few checks exercise the REAL template/email/mapping helpers under
dry-run.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-outbound-delivery.py

NEVER point this at production: it writes and deletes a throwaway company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "OUTBOUNDTESTCO"
MARKER = "temporary_outbound_delivery_harness"

EMP = "outbound-emp-1"
PHONE = "96550000000801"
EMAIL = "outbound-emp-1@example.com"
EMPLOYEE = {"employee_key": EMP, "phone": PHONE, "email": EMAIL, "name": "Outbound Tester", "locale": "en"}
EMPLOYEE_NO_EMAIL = {"employee_key": EMP, "phone": PHONE, "name": "Outbound Tester"}

SMOKE_TEMPLATE_KEY = "leave_request_approved"  # critical / preview sensitivity in catalog

# Deterministic provider stubs. Each test sets these before calling deliver.
STUBS: dict[str, Any] = {
    "session": {"ok": False, "error": "conversation_closed"},
    "template": {"ok": False, "error": "template_unmapped"},
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
    _ORIG["session"] = app.send_octopus_whatsapp
    _ORIG["template"] = app.octopus_send_template
    _ORIG["email"] = app.send_outbound_email
    _ORIG["email_enabled"] = app.outbound_email_fallback_enabled
    app.send_octopus_whatsapp = lambda **k: dict(STUBS["session"])
    app.octopus_send_template = lambda **k: dict(STUBS["template"])
    app.send_outbound_email = lambda **k: dict(STUBS["email"])
    app.outbound_email_fallback_enabled = lambda: bool(STUBS["email_enabled"])


def _restore_stubs() -> None:
    if not _ORIG:
        return
    app.send_octopus_whatsapp = _ORIG["session"]
    app.octopus_send_template = _ORIG["template"]
    app.send_outbound_email = _ORIG["email"]
    app.outbound_email_fallback_enabled = _ORIG["email_enabled"]


def _set(session=None, template=None, email=None, email_enabled=None) -> None:
    if session is not None:
        STUBS["session"] = session
    if template is not None:
        STUBS["template"] = template
    if email is not None:
        STUBS["email"] = email
    if email_enabled is not None:
        STUBS["email_enabled"] = email_enabled


def _message_row(message_id: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_messages WHERE message_id=%s", (message_id,))
            return dict(cur.fetchone())


def _count(table: str, where: str, params: tuple) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM {table} WHERE {where}", params)
            return int(cur.fetchone()["n"])


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in ("employee_messages", "hr_tasks", "message_template_map", "outbound_delivery_events"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
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
                (COMPANY, "Outbound Delivery Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
        conn.commit()
    _install_stubs()


def teardown() -> None:
    _restore_stubs()
    _purge()
    app.os.environ.pop("WATHEFNI_OUTBOUND_LAYER", None)
    app.os.environ.pop("WATHEFNI_OUTBOUND_FLOWS", None)
    app.os.environ.pop("WATHEFNI_OUTBOUND_TEMPLATES", None)
    app.os.environ.pop("WATHEFNI_OUTBOUND_EMAIL_FALLBACK", None)


def _deliver(**over: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "company_code": COMPANY,
        "flow": "leave_decision",
        "template_key": SMOKE_TEMPLATE_KEY,
        "employee": EMPLOYEE,
        "variables": {"start_date": "2026-06-10", "end_date": "2026-06-12"},
    }
    kwargs.update(over)
    return app.deliver_to_employee(**kwargs)


def run_checks(checks: Checks) -> None:
    # --- Feature-flag gates ---------------------------------------------------
    app.os.environ.pop("WATHEFNI_OUTBOUND_LAYER", None)
    checks.check("layer flag OFF by default", lambda: app.outbound_layer_enabled() is False)
    checks.check("flow gate OFF when layer off", lambda: app.outbound_flow_enabled("leave_decision") is False)
    app.os.environ["WATHEFNI_OUTBOUND_LAYER"] = "on"
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "leave_decision"
    checks.check("layer flag ON", lambda: app.outbound_layer_enabled() is True)
    checks.check("named flow enabled", lambda: app.outbound_flow_enabled("leave_decision") is True)
    checks.check("other flow still gated", lambda: app.outbound_flow_enabled("shift_assigned") is False)
    app.os.environ["WATHEFNI_OUTBOUND_FLOWS"] = "all"
    checks.check("flows=all enables any flow", lambda: app.outbound_flow_enabled("shift_assigned") is True)
    checks.check("templates flag OFF by default", lambda: app.outbound_templates_enabled() is False)
    checks.check("email fallback ON by default", lambda: app.outbound_email_fallback_enabled() is True)

    # --- Ladder: rung 1 (WhatsApp session) ------------------------------------
    _set(session={"ok": True, "status": 200})
    r1 = _deliver(dedupe_key="ladder-session-ok")
    checks.check("session success -> delivered_whatsapp", lambda: r1["status"] == od.STATUS_DELIVERED_WHATSAPP)
    checks.check("session success -> channel whatsapp_session", lambda: r1["channel_used"] == "whatsapp_session")

    # --- Ladder: rung 2 (approved template) -----------------------------------
    _set(session={"ok": False, "error": "conversation_closed"}, template={"ok": True, "channel": "whatsapp_template"})
    r2 = _deliver(dedupe_key="ladder-template-ok")
    checks.check("closed session -> template delivers", lambda: r2["status"] == od.STATUS_DELIVERED_TEMPLATE)
    checks.check("template -> channel whatsapp_template", lambda: r2["channel_used"] == "whatsapp_template")

    # --- Ladder: rung 3 (email fallback) --------------------------------------
    _set(session={"ok": False, "error": "conversation_closed"}, template={"ok": False, "error": "template_unmapped"}, email={"ok": True})
    r3 = _deliver(dedupe_key="ladder-email-ok")
    checks.check("closed session + no template -> email fallback", lambda: r3["status"] == od.STATUS_SENT_EMAIL)
    checks.check("email fallback -> channel email", lambda: r3["channel_used"] == "email")

    # --- Ladder: rung 4 (critical -> HR task) ---------------------------------
    _set(session={"ok": False, "error": "conversation_closed"}, template={"ok": False, "error": "template_unmapped"}, email={"ok": False, "error": "no_employee_email"})
    r4 = _deliver(employee=EMPLOYEE_NO_EMAIL, dedupe_key="ladder-hr-task")
    checks.check("critical + all channels fail -> needs_hr_action", lambda: r4["status"] == od.STATUS_NEEDS_HR)
    checks.check("needs_hr_action creates an HR task", lambda: bool(r4.get("hr_task_id")))
    checks.check("HR task row exists, open & high priority", lambda: _count("hr_tasks", "task_id=%s AND status='open' AND priority='high'", (r4["hr_task_id"],)) == 1)
    checks.check("HR task records no message body (HR-safe)", lambda: _count("hr_tasks", "task_id=%s AND detail NOT LIKE %s", (r4["hr_task_id"], "%2026-06-1%")) == 1)

    # --- Standard (non-critical) terminal: failed, no HR task -----------------
    # Uses a metadata_only flow (payroll) so its needs-follow-up preview must be a
    # generic label, never the raw body — verified below.
    _set(session={"ok": False, "error": "conversation_closed"}, template={"ok": False, "error": "template_unmapped"}, email={"ok": False, "error": "email_failed"})
    r5 = _deliver(flow="payroll_timesheet_ready", template_key="payroll_timesheet_ready", variables={"period": "June 2026"}, employee=EMPLOYEE, dedupe_key="standard-failed")
    checks.check("standard + all fail (non-retryable) -> failed", lambda: r5["status"] == od.STATUS_FAILED)
    checks.check("standard failure raises NO HR task", lambda: r5.get("hr_task_id") is None)

    # --- Retry: transient session error -> pending, then sweep delivers -------
    _set(session={"ok": False, "error": "conversation_inactive"}, template={"ok": False, "error": "template_unmapped"}, email_enabled=False)
    r6 = _deliver(flow="shift_reminder", template_key="shift_reminder", employee={"employee_key": EMP, "phone": PHONE, "name": "T"}, dedupe_key="retry-pending")
    checks.check("transient + no fallback -> pending (retryable)", lambda: r6["status"] == od.STATUS_PENDING)
    checks.check("pending schedules a next attempt", lambda: bool(_message_row(r6["message_id"]).get("next_attempt_at")))

    # Make the pending message due, then let the sweep re-walk the ladder (now session OK).
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE employee_messages SET next_attempt_at = now() - interval '1 minute' WHERE message_id=%s", (r6["message_id"],))
        conn.commit()
    _set(session={"ok": True, "status": 200})
    sweep = app.run_delivery_sweep(limit=50)
    checks.check("sweep processes due pending messages", lambda: sweep["processed"] >= 1)
    checks.check("sweep delivers the recovered message", lambda: _message_row(r6["message_id"])["status"] == od.STATUS_DELIVERED_WHATSAPP)
    checks.check("recovered message attempts incremented", lambda: int(_message_row(r6["message_id"])["attempts"]) >= 2)

    # --- Idempotency: same dedupe_key does not create a duplicate -------------
    _set(session={"ok": True, "status": 200})
    a = _deliver(dedupe_key="idem-key")
    b = _deliver(dedupe_key="idem-key")
    checks.check("repeated dedupe_key returns same message", lambda: a["message_id"] == b["message_id"])
    checks.check("repeated dedupe_key marks deduped", lambda: b.get("deduped") is True)
    checks.check("dedupe creates exactly one row", lambda: _count("employee_messages", "company_code=%s AND dedupe_key=%s", (COMPANY, "idem-key")) == 1)

    # --- Sensitivity storage policy ------------------------------------------
    _set(session={"ok": True, "status": 200})
    meta = _deliver(flow="payroll_timesheet_ready", template_key="payroll_timesheet_ready", variables={"period": "June 2026"}, dedupe_key="sens-metadata")
    meta_row = _message_row(meta["message_id"])
    checks.check("metadata_only stores no raw body", lambda: not (meta_row.get("body_preview") or "").lower().startswith("hi "))
    checks.check("metadata_only stores a generic label preview", lambda: meta_row.get("body_preview") == "Payroll update")
    checks.check("metadata_only stores no ciphertext", lambda: meta_row.get("body_encrypted") is None)

    preview_row = _message_row(r1["message_id"])
    checks.check("preview sensitivity keeps a readable preview", lambda: "approved" in (preview_row.get("body_preview") or "").lower())

    if app.sensitive_encryption_available():
        enc = _deliver(template_key=SMOKE_TEMPLATE_KEY, sensitivity=od.SENS_ENCRYPTED, dedupe_key="sens-encrypted")
        enc_row = _message_row(enc["message_id"])
        checks.check("encrypted stores ciphertext", lambda: bool(enc_row.get("body_encrypted")))
        checks.check("encrypted preview is a generic label", lambda: enc_row.get("body_preview") == "Leave approved")
        checks.check("encrypted body round-trips", lambda: "approved" in app.decrypt_sensitive_text(enc_row["body_encrypted"]).lower())
    else:
        checks.check("encrypted degrades safely when no keyring", lambda: _message_row(_deliver(sensitivity=od.SENS_ENCRYPTED, dedupe_key="sens-enc-degrade")["message_id"]).get("body_encrypted") is None)

    # --- Real template path (mapping + flag) under dry-run --------------------
    # Restore the genuine channel primitives so the next checks exercise the real
    # code paths (dry-run keeps them from sending anything).
    _restore_stubs()
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"
    checks.check("real template send: disabled when flag off", lambda: app.octopus_send_template(account_id=None, phone=PHONE, template_key=SMOKE_TEMPLATE_KEY, company_code=COMPANY).get("error") == "template_disabled")
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "on"
    checks.check("real template send: unmapped key falls through", lambda: app.octopus_send_template(account_id=None, phone=PHONE, template_key=SMOKE_TEMPLATE_KEY, company_code=COMPANY).get("error") == "template_unmapped")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO message_template_map (template_key, locale, provider, provider_template_name, status, company_code) "
                "VALUES (%s,'en','octopus','wa_leave_approved','approved',%s)",
                (SMOKE_TEMPLATE_KEY, COMPANY),
            )
        conn.commit()
    checks.check("template mapping resolves approved name", lambda: app.lookup_template_mapping(SMOKE_TEMPLATE_KEY, company_code=COMPANY)["provider_template_name"] == "wa_leave_approved")
    checks.check("real template send: approved mapping + dry_run = ok", lambda: app.octopus_send_template(account_id=None, phone=PHONE, template_key=SMOKE_TEMPLATE_KEY, company_code=COMPANY, fallback_text="x").get("ok") is True)
    app.os.environ["WATHEFNI_OUTBOUND_TEMPLATES"] = "off"

    # --- Real email fallback under dry-run ------------------------------------
    checks.check("real email send (dry_run) reports ok", lambda: app.send_outbound_email(to=EMAIL, subject="s", body="b", company_code=COMPANY).get("ok") is True)
    checks.check("real email send rejects empty recipient", lambda: app.send_outbound_email(to="", subject="s", body="b", company_code=COMPANY).get("error") == "no_employee_email")

    # --- Audit: every terminal delivery wrote a consolidated layer event ------
    checks.check("layer writes consolidated audit events", lambda: _count("outbound_delivery_events", "company_code=%s AND channel='outbound_layer'", (COMPANY,)) >= 5)

    # --- Tenant safety: rows are company-scoped -------------------------------
    checks.check("all messages stay in our company", lambda: _count("employee_messages", "company_code=%s", (COMPANY,)) >= 6 and _count("employee_messages", "company_code <> %s AND dedupe_key LIKE %s", (COMPANY, "ladder-%")) == 0)

    # --- Phase B: HR tasks + needs-follow-up surface --------------------------
    open_tasks = od.list_hr_tasks(company_code=COMPANY, statuses=["open"], limit=200)
    checks.check("hr task list includes the delivery-failure task", lambda: any(t["task_id"] == r4["hr_task_id"] for t in open_tasks))
    checks.check("hr task open count >= 1", lambda: od.hr_task_open_count(company_code=COMPANY) >= 1)

    follow = od.list_needs_follow_up(company_code=COMPANY, limit=200)
    follow_status = {m["message_id"]: m["status"] for m in follow}
    follow_preview = {m["message_id"]: (m.get("body_preview") or "") for m in follow}
    checks.check("needs-follow-up includes needs_hr_action message", lambda: follow_status.get(r4["message_id"]) == od.STATUS_NEEDS_HR)
    checks.check("needs-follow-up includes failed message", lambda: follow_status.get(r5["message_id"]) == od.STATUS_FAILED)
    # The metadata_only (payroll) message must surface only its generic label.
    checks.check("needs-follow-up keeps metadata-only body generic", lambda: follow_preview.get(r5["message_id"]) == "Payroll update")
    checks.check("needs-follow-up exposes no raw/encrypted body field", lambda: all("body" not in m and "body_encrypted" not in m for m in follow))

    # Manager scope filters tasks/messages to the manager's own people.
    scope_emp = {"restricted": True, "company_code": COMPANY, "direct_employee_keys": [EMP], "branch_keys": [], "team_keys": []}
    scope_other = {"restricted": True, "company_code": COMPANY, "direct_employee_keys": ["someone-else"], "branch_keys": [], "team_keys": []}
    checks.check("manager scope sees tasks for its managed employee", lambda: any(t["task_id"] == r4["hr_task_id"] for t in od.list_hr_tasks(company_code=COMPANY, scope=scope_emp, statuses=["open"])))
    checks.check("manager scope hides tasks for non-managed employees", lambda: od.list_hr_tasks(company_code=COMPANY, scope=scope_other, statuses=["open"]) == [])
    checks.check("manager scope filters needs-follow-up too", lambda: od.list_needs_follow_up(company_code=COMPANY, scope=scope_other) == [])

    # Resolve closes the task, company-scoped.
    res = od.resolve_hr_task(company_code=COMPANY, task_id=r4["hr_task_id"], status="done", resolver_phone=PHONE)
    checks.check("resolve_hr_task succeeds", lambda: res.get("ok") is True)
    checks.check("resolved task drops out of the open list", lambda: all(t["task_id"] != r4["hr_task_id"] for t in od.list_hr_tasks(company_code=COMPANY, statuses=["open"])))
    checks.check("resolve is company-scoped (other company cannot touch)", lambda: od.resolve_hr_task(company_code="SOMEOTHERCO", task_id=r4["hr_task_id"], status="done").get("error") == "task_not_found")


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"outbound delivery harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nOUTBOUND DELIVERY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nOUTBOUND DELIVERY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
