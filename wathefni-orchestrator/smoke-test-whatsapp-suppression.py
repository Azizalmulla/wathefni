"""WhatsApp opt-out / suppression harness (templates stay OFF).

Proves the behaviour added by the "global WhatsApp sender readiness — opt-out /
suppression + template-map groundwork" batch, with NO network and NO real sends
(channel primitives are stubbed; WATHEFNI_DELIVERY_MODE is pinned to dry_run):

  1. detect_whatsapp_opt_out only fires on CLEAR opt-out wording (STOP /
     unsubscribe / cancel messages / إلغاء الاشتراك / إيقاف / توقف) and never on a
     bare "no" / "لا".
  2. An inbound opt-out from an EMPLOYEE phone records a global suppression and is
     ignored for a phone that belongs to no employee.
  3. Pre-send: a suppressed phone skips the WhatsApp session + template rungs
     entirely (no provider call) but still falls back to email (scope='whatsapp').
  4. scope='all' blocks the email rung too -> STATUS_SUPPRESSED, even for a
     CRITICAL flow, and raises NO HR task (opt-out is a choice, not a failure).
  5. A non-suppressed employee follows the normal session/template/email ladder.
  6. Delivery Issues surfaces the suppressed message with calm opt-out wording and
     stays company-scoped (no cross-tenant leak).
  7. Operator unsuppress re-enables proactive WhatsApp.
  8. Template map: a company-specific row overrides the global (company_code NULL)
     default; the global default is used when there is no company-specific row.
  9. WATHEFNI_OUTBOUND_TEMPLATES stays OFF.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-whatsapp-suppression.py

NEVER point this at production: it writes and deletes throwaway companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od
from psycopg2.extras import Json

COMPANY = "WASUPPRESSIONCO"
COMPANY2 = "WASUPPRESSIONCO2"
MARKER = "temporary_whatsapp_suppression_harness"

EMP_A = "wasup-emp-a"      # has email — email fallback / unsuppress
EMP_B = "wasup-emp-b"      # no email — scope=whatsapp suppressed terminal (critical)
EMP_C = "wasup-emp-c"      # has email — control (not suppressed)
EMP_ALL = "wasup-emp-all"  # has email — scope=all suppression
PHONE_A = "96550000000811"
PHONE_B = "96550000000812"
PHONE_C = "96550000000813"
PHONE_ALL = "96550000000814"
PHONE_STRANGER = "96550000000899"  # belongs to no employee
EMAIL_A = "wasup-a@example.com"
EMAIL_C = "wasup-c@example.com"
EMAIL_ALL = "wasup-all@example.com"

ALL_PHONES = [PHONE_A, PHONE_B, PHONE_C, PHONE_ALL, PHONE_STRANGER]

CALLS = {"session": 0, "template": 0, "email": 0}
STUBS: dict[str, Any] = {"session_ok": False}
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
    if STUBS["session_ok"]:
        return {"ok": True, "channel": "whatsapp_session"}
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


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, phone: str, name: str, email: str | None) -> None:
    desired: dict[str, Any] = {
        "company_code": company, "phone": phone, "name": name, "employee_key": emp_key,
        "email": email, "status": "active", "employment_status": "active",
        "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _canon_phones() -> list[str]:
    return [app.canonical_employee_phone(p) for p in ALL_PHONES]


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM whatsapp_suppressions WHERE phone = ANY(%s)", (_canon_phones(),))
            for company in (COMPANY, COMPANY2):
                for table in ("employee_messages", "hr_tasks", "message_template_map", "outbound_delivery_events", "employees", "company_modules"):
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
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
            for company, label in ((COMPANY, "WhatsApp Suppression Harness"), (COMPANY2, "WhatsApp Suppression Harness 2")):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET name=EXCLUDED.name, metadata=EXCLUDED.metadata",
                    (company, label, Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            emp_cols = _columns(cur, "employees")
            _insert_employee(cur, emp_cols, COMPANY, EMP_A, PHONE_A, "Emp A", EMAIL_A)
            _insert_employee(cur, emp_cols, COMPANY, EMP_B, PHONE_B, "Emp B", None)
            _insert_employee(cur, emp_cols, COMPANY, EMP_C, PHONE_C, "Emp C", EMAIL_C)
            _insert_employee(cur, emp_cols, COMPANY, EMP_ALL, PHONE_ALL, "Emp All", EMAIL_ALL)
        conn.commit()
    _install_stubs()


def teardown() -> None:
    _restore_stubs()
    _purge()
    for key in ("WATHEFNI_OUTBOUND_LAYER", "WATHEFNI_OUTBOUND_FLOWS", "WATHEFNI_OUTBOUND_TEMPLATES", "WATHEFNI_DELIVERY_MODE"):
        app.os.environ.pop(key, None)


def _deliver(emp_key: str, phone: str, email: str | None, *, flow: str, template_key: str, dedupe: str) -> dict[str, Any]:
    return app.deliver_to_employee(
        company_code=COMPANY, flow=flow, template_key=template_key,
        employee={"employee_key": emp_key, "phone": phone, "email": email, "name": emp_key},
        dedupe_key=dedupe,
    )


def run_checks(checks: Checks) -> None:
    # --- 1. Opt-out detection ------------------------------------------------
    for word in ["STOP", "stop", "  Stop ", "unsubscribe", "cancel messages", "إلغاء الاشتراك", "الغاء الاشتراك", "إيقاف", "توقف"]:
        checks.check(f"detect opt-out: {word!r}", (lambda w=word: app.detect_whatsapp_opt_out(w)))
    for word in ["لا", "no", "no thanks", "hello", "", "what about my shift", "stop the shift please"]:
        checks.check(f"NOT opt-out: {word!r}", (lambda w=word: not app.detect_whatsapp_opt_out(w)))

    # --- 2. Inbound opt-out suppresses an employee phone (not a stranger) -----
    req = app.WhatsAppTurnRequest(sender_phone=PHONE_B, raw_text="STOP")
    res = app.maybe_handle_employee_opt_out(req)
    checks.check("inbound STOP from employee returns a confirmation", lambda: bool(res) and "unsubscrib" in (res or {}).get("reply", "").lower())
    checks.check("inbound STOP records a suppression", lambda: app.whatsapp_suppression_state(PHONE_B)["suppressed"] is True)
    checks.check("suppression scope defaults to whatsapp", lambda: app.whatsapp_suppression_state(PHONE_B)["scope"] == "whatsapp")
    stranger = app.maybe_handle_employee_opt_out(app.WhatsAppTurnRequest(sender_phone=PHONE_STRANGER, raw_text="STOP"))
    checks.check("inbound STOP from non-employee phone is ignored", lambda: stranger is None and app.whatsapp_suppression_state(PHONE_STRANGER)["suppressed"] is False)
    non_optout = app.maybe_handle_employee_opt_out(app.WhatsAppTurnRequest(sender_phone=PHONE_A, raw_text="hello there"))
    checks.check("inbound non-opt-out text does not suppress", lambda: non_optout is None and app.whatsapp_suppression_state(PHONE_A)["suppressed"] is False)

    # --- 3. Pre-send: suppressed phone skips WA, falls back to email ----------
    CALLS["session"] = 0
    CALLS["template"] = 0
    CALLS["email"] = 0
    app.suppress_whatsapp(PHONE_A, scope="whatsapp", reason="test", source="operator", created_by="smoke")
    r_a = _deliver(EMP_A, PHONE_A, EMAIL_A, flow="shift", template_key="shift_reminder", dedupe="wa-supp-email")
    checks.check("suppressed (whatsapp) + email -> sent via email", lambda: r_a["status"] == od.STATUS_SENT_EMAIL)
    checks.check("suppressed: WhatsApp session provider NOT called", lambda: CALLS["session"] == 0)
    checks.check("suppressed: WhatsApp template provider NOT called", lambda: CALLS["template"] == 0)
    checks.check("suppressed: email provider WAS called", lambda: CALLS["email"] == 1)
    checks.check("suppressed: reasons show opt-out for session + template", lambda: any("session:suppressed_opt_out" in x for x in r_a.get("attempt_reasons", [])) and any("template:suppressed_opt_out" in x for x in r_a.get("attempt_reasons", [])))

    # --- 4. scope=all blocks email too; critical flow -> suppressed, no task --
    CALLS["email"] = 0
    app.suppress_whatsapp(PHONE_B, scope="all", reason="test-all", source="operator", created_by="smoke")
    r_b = _deliver(EMP_B, PHONE_B, None, flow="leave_decision", template_key="leave_request_approved", dedupe="wa-supp-all")
    checks.check("scope=all -> STATUS_SUPPRESSED (terminal)", lambda: r_b["status"] == od.STATUS_SUPPRESSED)
    checks.check("scope=all: critical flow raises NO HR task", lambda: r_b.get("hr_task_id") is None)
    checks.check("scope=all: email provider NOT called", lambda: CALLS["email"] == 0)
    checks.check("scope=all: reasons include email opt-out", lambda: any("email:suppressed_opt_out" in x for x in r_b.get("attempt_reasons", [])))

    # --- 5. Non-suppressed employee follows the normal ladder -----------------
    CALLS["session"] = 0
    CALLS["template"] = 0
    CALLS["email"] = 0
    r_c = _deliver(EMP_C, PHONE_C, EMAIL_C, flow="shift", template_key="shift_reminder", dedupe="wa-normal")
    checks.check("non-suppressed: session + template attempted, email lands", lambda: CALLS["session"] == 1 and CALLS["template"] == 1 and r_c["status"] == od.STATUS_SENT_EMAIL)

    # --- 6. Delivery Issues: calm wording + company-scoped --------------------
    follow = od.list_needs_follow_up(company_code=COMPANY, limit=200)
    supp_item = next((m for m in follow if str(m.get("message_id")) == str(r_b["message_id"])), None)
    checks.check("suppressed message appears in needs-follow-up", lambda: supp_item is not None)
    reason, action = app._humanize_delivery_failure(last_error="session:suppressed_opt_out; template:suppressed_opt_out; email:suppressed_opt_out", employee_name="Emp B", has_email=False)
    checks.check("humanize: opt-out wording is calm (opted out)", lambda: "opted out" in reason.lower())
    checks.check("humanize: opt-out leaks no raw codes", lambda: "suppressed_opt_out" not in (reason + action))
    follow2 = od.list_needs_follow_up(company_code=COMPANY2, limit=200)
    checks.check("no cross-tenant leak: company 2 cannot see company 1's suppressed message", lambda: not any(str(m.get("message_id")) == str(r_b["message_id"]) for m in follow2))

    # --- 7. Operator unsuppress re-enables proactive WhatsApp -----------------
    app.unsuppress_whatsapp(PHONE_A, by="smoke-operator")
    checks.check("unsuppress clears suppression state", lambda: app.whatsapp_suppression_state(PHONE_A)["suppressed"] is False)
    STUBS["session_ok"] = True
    r_a2 = _deliver(EMP_A, PHONE_A, EMAIL_A, flow="shift", template_key="shift_reminder", dedupe="wa-after-unsuppress")
    STUBS["session_ok"] = False
    checks.check("after unsuppress: WhatsApp session delivers again", lambda: r_a2["status"] == od.STATUS_DELIVERED_WHATSAPP)

    # --- 8. Template map: company override vs global default ------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO message_template_map (template_key, locale, provider, provider_template_name, status, company_code) "
                "VALUES (%s,'en','octopus',%s,'approved',NULL)",
                ("leave_request_approved", "wa_global_leave"),
            )
            cur.execute(
                "INSERT INTO message_template_map (template_key, locale, provider, provider_template_name, status, company_code) "
                "VALUES (%s,'en','octopus',%s,'approved',%s)",
                ("leave_request_approved", "wa_company_leave", COMPANY),
            )
        conn.commit()
    checks.check("template map: company-specific override wins for its company", lambda: app.lookup_template_mapping("leave_request_approved", company_code=COMPANY)["provider_template_name"] == "wa_company_leave")
    checks.check("template map: global default used for other company", lambda: app.lookup_template_mapping("leave_request_approved", company_code=COMPANY2)["provider_template_name"] == "wa_global_leave")
    checks.check("template map: global default used when no company given", lambda: app.lookup_template_mapping("leave_request_approved")["provider_template_name"] == "wa_global_leave")

    # --- 9. Kill switch stays off + catalog groundwork ------------------------
    checks.check("WATHEFNI_OUTBOUND_TEMPLATES stays off", lambda: app.outbound_templates_enabled() is False)
    checks.check("catalog includes shift_rescheduled", lambda: "shift_rescheduled" in od.TEMPLATE_CATALOG)
    checks.check("company_name is injectable in onboarding welcome body", lambda: "Suppression" in od.render_body("employee_onboarding_welcome", {"employee_name": "X", "company_name": app.company_display_name(COMPANY)}, "en"))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"whatsapp suppression harness — companies {COMPANY}/{COMPANY2} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nWHATSAPP SUPPRESSION HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nWHATSAPP SUPPRESSION HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
