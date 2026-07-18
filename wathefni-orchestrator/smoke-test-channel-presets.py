"""Company notification presets — channel-policy contract + integration harness.

Presets are an operator-selected, per-company channel policy (frontline | office |
conservative) that can only make employee routing CALMER than each template's
employee_channel_intent ceiling, never louder. They compose delivery_urgency +
employee_channel_intent only — never failure_escalation.

This harness proves:
  1. EXACT resolved matrix: channel_plan_for(preset, intent, urgency) yields the
     approved (whatsapp / email / dashboard_only) verdict for all 12 templates ×
     3 presets.
  2. Hard invariants (anti-leak): payroll never WhatsApp, attendance stays
     dashboard-only, compliance never WhatsApp — under EVERY preset.
  3. Calmer-never-louder: WhatsApp availability is monotonic
     frontline >= office >= conservative for every template, and a preset never
     enables a channel above the template's intent ceiling.
  4. Resolver binding: resolve_channel_plan() reads the company's saved preset.
  5. Integration (stubbed providers): _attempt_ladder honours the plan — no
     WhatsApp attempt when the preset/intent forbid it; dashboard_only short-
     circuits with zero provider calls and a terminal STATUS_DASHBOARD_ONLY.
  6. Flag-OFF regression: with WATHEFNI_CHANNEL_PRESETS off the ladder behaves
     exactly as before (all channels allowed — WhatsApp attempted for payroll).

No real database or network: providers are stubbed and the preset is faked.

Run with the orchestrator venv, e.g.:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-channel-presets.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable

import app  # noqa: F401  (used for flag-default regression)
import outbound_delivery as od

# Approved resolved matrix. Per template: (preset -> verdict) where verdict is one
# of "WA" (WhatsApp-first, email fallback), "EM" (email only), "DASH" (dashboard
# only, no proactive send). This is the human-readable contract for the batch.
MATRIX = {
    "employee_onboarding_welcome": {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "onboarding_reminder":         {"frontline": "WA", "office": "EM", "conservative": "EM"},
    "compliance_document_required":{"frontline": "EM", "office": "EM", "conservative": "EM"},
    "compliance_document_expiring":{"frontline": "EM", "office": "EM", "conservative": "EM"},
    "shift_assigned":              {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "shift_rescheduled":           {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "shift_reminder":              {"frontline": "WA", "office": "EM", "conservative": "EM"},
    "shift_cancelled":             {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "attendance_missed_checkin":   {"frontline": "DASH", "office": "DASH", "conservative": "DASH"},
    "leave_request_approved":      {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "leave_request_rejected":      {"frontline": "WA", "office": "WA", "conservative": "EM"},
    "payroll_timesheet_ready":     {"frontline": "EM", "office": "EM", "conservative": "EM"},
    # Employee App activation code: critical action-now, whatsapp_ok intent —
    # same resolution as other critical WhatsApp-capable templates.
    "app_activation":              {"frontline": "WA", "office": "WA", "conservative": "EM"},
}

PRESETS = ("frontline", "office", "conservative")


def _verdict(plan: dict[str, Any]) -> str:
    if plan.get("dashboard_only"):
        return "DASH"
    if plan.get("whatsapp"):
        return "WA"
    if plan.get("email"):
        return "EM"
    return "NONE"


def _plan_for_key(preset: str, key: str) -> dict[str, Any]:
    entry = od.catalog_entry(key)
    return od.channel_plan_for(preset, entry.get("employee_channel_intent"), entry.get("delivery_urgency"))


# --- Stubs for the integration leg ------------------------------------------
class _FakeOctopus:
    calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def send_session(legacy, **kw):  # type: ignore[no-untyped-def]
        _FakeOctopus.calls.append(("session", kw))
        return {"ok": True}

    @staticmethod
    def send_template(legacy, **kw):  # type: ignore[no-untyped-def]
        _FakeOctopus.calls.append(("template", kw))
        return {"ok": False, "error": "template_unmapped"}


class _FakeEmail:
    calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def send(legacy, **kw):  # type: ignore[no-untyped-def]
        _FakeEmail.calls.append(("email", kw))
        return {"ok": True}


class _FakeLegacy:
    def __init__(self, preset: str, presets_on: bool = True, email_on: bool = True) -> None:
        self._preset = preset
        self._on = presets_on
        self._email = email_on

    def whatsapp_suppression_state(self, phone):  # type: ignore[no-untyped-def]
        return {"suppressed": False, "scope": None}

    def channel_presets_enabled(self) -> bool:
        return self._on

    # Push rung is flag-gated and OFF here: this harness proves preset/channel
    # policy for the WhatsApp/email ladder, independent of the employee app.
    def push_notifications_enabled(self) -> bool:
        return False

    def company_notification_preset(self, company_code):  # type: ignore[no-untyped-def]
        return self._preset

    def outbound_email_fallback_enabled(self) -> bool:
        return self._email


def _run_ladder(preset: str, key: str, *, presets_on: bool = True, phone: str | None = "96599999999") -> dict[str, Any]:
    _FakeOctopus.calls = []
    _FakeEmail.calls = []
    legacy = _FakeLegacy(preset, presets_on=presets_on)
    # The provider classes call legacy.* primitives; swap them for recorders so the
    # ladder exercises real routing decisions without any network/DB.
    real_octo, real_email = od.OctopusProvider, od.EmailProvider
    od.OctopusProvider, od.EmailProvider = _FakeOctopus, _FakeEmail
    try:
        return od._attempt_ladder(
            legacy,
            account_id="acct",
            phone=phone,
            email="emp@example.com",
            template_key=key,
            flow=key,
            locale="en",
            variables={},
            full_text="hello",
            email_subject="subject",
            subject_type="employee",
            subject_key="emp-1",
            company_code="DEMO",
        )
    finally:
        od.OctopusProvider, od.EmailProvider = real_octo, real_email


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


def run_checks(checks: Checks) -> None:
    catalog = od.TEMPLATE_CATALOG

    # --- 1. Exact resolved matrix --------------------------------------------
    checks.check("matrix covers every catalog template", lambda: set(MATRIX) == set(catalog))
    for key, by_preset in MATRIX.items():
        for preset, expected in by_preset.items():
            checks.check(
                f"{key} @ {preset} resolves to {expected}",
                (lambda k=key, p=preset, e=expected: _verdict(_plan_for_key(p, k)) == e),
            )

    # --- 2. Hard invariants under EVERY preset (anti-leak) -------------------
    for preset in PRESETS:
        checks.check(f"{preset}: payroll never WhatsApp", (lambda p=preset: _plan_for_key(p, "payroll_timesheet_ready")["whatsapp"] is False))
        checks.check(f"{preset}: attendance stays dashboard-only", (lambda p=preset: _plan_for_key(p, "attendance_missed_checkin")["dashboard_only"] is True))
        for key in ("compliance_document_required", "compliance_document_expiring"):
            checks.check(f"{preset}: {key} never WhatsApp", (lambda p=preset, k=key: _plan_for_key(p, k)["whatsapp"] is False))
    # conservative never uses WhatsApp for anything
    checks.check("conservative never uses WhatsApp for any template", lambda: all(_plan_for_key("conservative", k)["whatsapp"] is False for k in catalog))
    # office uses WhatsApp ONLY for action_now templates
    for key, entry in catalog.items():
        if entry.get("employee_channel_intent") == od.CHANNEL_WHATSAPP_OK:
            expect_wa = entry.get("delivery_urgency") == od.URGENCY_ACTION_NOW
            checks.check(f"office: {key} WhatsApp == action_now ({expect_wa})", (lambda k=key, e=expect_wa: _plan_for_key("office", k)["whatsapp"] is e))

    # --- 3. Calmer-never-louder ----------------------------------------------
    for key in catalog:
        wa_f = _plan_for_key("frontline", key)["whatsapp"]
        wa_o = _plan_for_key("office", key)["whatsapp"]
        wa_c = _plan_for_key("conservative", key)["whatsapp"]
        checks.check(f"{key}: WhatsApp monotonic frontline>=office>=conservative", (lambda a=wa_f, b=wa_o, c=wa_c: (a >= b) and (b >= c)))
        # A preset can never enable WhatsApp for a non-whatsapp_ok intent.
        intent = catalog[key].get("employee_channel_intent")
        if intent != od.CHANNEL_WHATSAPP_OK:
            checks.check(f"{key}: no preset can WhatsApp a {intent} template", (lambda k=key: all(_plan_for_key(p, k)["whatsapp"] is False for p in PRESETS)))

    # --- 4. Resolver binding reads the saved preset --------------------------
    for preset in PRESETS:
        legacy = _FakeLegacy(preset)
        plan = od.resolve_channel_plan(legacy, "DEMO", "shift_reminder")
        checks.check(f"resolve_channel_plan binds preset={preset}", (lambda p=plan, pr=preset: p.get("preset") == pr))
    # Unknown saved preset falls back to the default (frontline).
    checks.check("unknown preset falls back to frontline", lambda: od.channel_plan_for("bogus", od.CHANNEL_WHATSAPP_OK, od.URGENCY_REMINDER)["whatsapp"] is True)

    # --- 5. Integration with stubbed providers -------------------------------
    # frontline whatsapp_ok: WhatsApp session is attempted and lands.
    out = _run_ladder("frontline", "shift_assigned")
    checks.check("frontline shift_assigned -> WhatsApp session delivered", lambda: out.get("status") == od.STATUS_DELIVERED_WHATSAPP)
    checks.check("frontline shift_assigned -> a session call was made", lambda: any(c[0] == "session" for c in _FakeOctopus.calls))

    # office reminder: no WhatsApp attempt at all, email instead.
    out = _run_ladder("office", "shift_reminder")
    sess_calls = [c for c in _FakeOctopus.calls if c[0] in ("session", "template")]
    checks.check("office shift_reminder -> NO WhatsApp/template attempt", lambda: not sess_calls)
    checks.check("office shift_reminder -> email sent", lambda: out.get("status") == od.STATUS_SENT_EMAIL)

    # conservative whatsapp_ok action_now: still no WhatsApp.
    out = _run_ladder("conservative", "leave_request_approved")
    checks.check("conservative leave_approved -> NO WhatsApp attempt", lambda: not any(c[0] in ("session", "template") for c in _FakeOctopus.calls))
    checks.check("conservative leave_approved -> email sent", lambda: out.get("status") == od.STATUS_SENT_EMAIL)

    # payroll under frontline: email_only intent => never WhatsApp, even on the loud preset.
    out = _run_ladder("frontline", "payroll_timesheet_ready")
    checks.check("frontline payroll -> NO WhatsApp attempt (email_only intent)", lambda: not any(c[0] in ("session", "template") for c in _FakeOctopus.calls))
    checks.check("frontline payroll -> email sent", lambda: out.get("status") == od.STATUS_SENT_EMAIL)

    # attendance: dashboard_only short-circuits with zero provider calls.
    out = _run_ladder("frontline", "attendance_missed_checkin")
    checks.check("attendance -> dashboard_only outcome", lambda: out.get("dashboard_only") is True)
    checks.check("attendance -> zero provider calls", lambda: not _FakeOctopus.calls and not _FakeEmail.calls)
    checks.check("attendance -> not retryable, no terminal send status", lambda: out.get("retryable") is False and out.get("status") is None)

    # STATUS_DASHBOARD_ONLY is a terminal, non-failure status (finalize maps the
    # dashboard_only outcome to it; that DB write is exercised by staging deploy).
    checks.check("STATUS_DASHBOARD_ONLY is a terminal status", lambda: od.STATUS_DASHBOARD_ONLY in od._TERMINAL_STATUSES)
    checks.check("STATUS_DASHBOARD_ONLY is distinct from failed", lambda: od.STATUS_DASHBOARD_ONLY != od.STATUS_FAILED)

    # --- 6. Flag-OFF regression: behaves exactly as before -------------------
    # With presets OFF, the ladder allows all channels — payroll WOULD attempt WA.
    out = _run_ladder("conservative", "payroll_timesheet_ready", presets_on=False)
    checks.check("flag OFF -> WhatsApp session attempted (pre-preset behavior)", lambda: any(c[0] == "session" for c in _FakeOctopus.calls))
    checks.check("flag OFF -> WhatsApp delivered (no preset downgrade)", lambda: out.get("status") == od.STATUS_DELIVERED_WHATSAPP)
    # attendance with flag OFF is NOT short-circuited (no preset consumer).
    out = _run_ladder("frontline", "attendance_missed_checkin", presets_on=False)
    checks.check("flag OFF -> attendance NOT dashboard_only short-circuit", lambda: out.get("dashboard_only") is not True)

    # --- 7. App flag default is OFF ------------------------------------------
    prev = os.environ.pop("WATHEFNI_CHANNEL_PRESETS", None)
    try:
        checks.check("WATHEFNI_CHANNEL_PRESETS default OFF", lambda: app.channel_presets_enabled() is False)
    finally:
        if prev is not None:
            os.environ["WATHEFNI_CHANNEL_PRESETS"] = prev
    checks.check("default notification preset is frontline", lambda: od.DEFAULT_NOTIFICATION_PRESET == "frontline")


def main() -> None:
    print("company notification presets — channel-policy contract + integration harness")
    checks = Checks()
    run_checks(checks)
    code = checks.report()
    if code:
        print("\nCHANNEL PRESETS HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nCHANNEL PRESETS HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
