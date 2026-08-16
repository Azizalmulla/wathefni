"""Notification semantics — Phase 1 contract harness (behavior-frozen, no DB).

Phase 1 of the notification-semantics cleanup splits the overloaded `criticality`
label into three orthogonal, explicit fields on every TEMPLATE_CATALOG entry:

  * delivery_urgency        (action_now | reminder | informational)
  * failure_escalation      (hr_task | delivery_issue_only | audit_only)
  * employee_channel_intent (whatsapp_ok | email_first | email_only | dashboard_only)

Phase 1 is BEHAVIOR-FROZEN: `criticality` stays the runtime source of truth for
failure escalation + needs-follow-up sort; the new fields have NO consumer yet.
`failure_escalation` is a strict 1:1 alias of `criticality`.

This harness proves:
  1. Catalog contract: every key defines all three new fields with valid enum
     values (so a future template cannot be added without channel semantics).
  2. No behavior change: derived_criticality(failure_escalation) == legacy
     criticality for EVERY template key.
  3. Hard channel-intent assertions (the anti-leak guarantee): payroll = email_only,
     attendance = dashboard_only, compliance = email_first; and no payroll/admin/
     compliance/attendance template may ever be whatsapp_ok.
  4. Reminder caps + templates are untouched (caps map stable, templates OFF).

No database and no network: this reads TEMPLATE_CATALOG and the cap map directly.

Run with the orchestrator venv, e.g.:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-notification-semantics.py
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
import outbound_delivery as od

# What every employee-facing template is expected to declare in Phase 1.
# failure_escalation MUST mirror the listed criticality (1:1 alias).
EXPECTED = {
    "employee_onboarding_welcome": ("critical", od.URGENCY_ACTION_NOW, od.ESCALATION_HR_TASK, od.CHANNEL_WHATSAPP_OK),
    "onboarding_reminder": ("standard", od.URGENCY_REMINDER, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_WHATSAPP_OK),
    "compliance_document_required": ("critical", od.URGENCY_REMINDER, od.ESCALATION_HR_TASK, od.CHANNEL_EMAIL_FIRST),
    "compliance_document_expiring": ("critical", od.URGENCY_REMINDER, od.ESCALATION_HR_TASK, od.CHANNEL_EMAIL_FIRST),
    "shift_assigned": ("standard", od.URGENCY_ACTION_NOW, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_WHATSAPP_OK),
    "shift_rescheduled": ("standard", od.URGENCY_ACTION_NOW, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_WHATSAPP_OK),
    "shift_reminder": ("informational", od.URGENCY_REMINDER, od.ESCALATION_AUDIT_ONLY, od.CHANNEL_WHATSAPP_OK),
    "shift_cancelled": ("standard", od.URGENCY_ACTION_NOW, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_WHATSAPP_OK),
    "attendance_missed_checkin": ("standard", od.URGENCY_INFORMATIONAL, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_DASHBOARD_ONLY),
    "leave_request_approved": ("critical", od.URGENCY_ACTION_NOW, od.ESCALATION_HR_TASK, od.CHANNEL_WHATSAPP_OK),
    "leave_request_rejected": ("critical", od.URGENCY_ACTION_NOW, od.ESCALATION_HR_TASK, od.CHANNEL_WHATSAPP_OK),
    "payroll_timesheet_ready": ("standard", od.URGENCY_INFORMATIONAL, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_EMAIL_ONLY),
    "payslip_ready": ("standard", od.URGENCY_INFORMATIONAL, od.ESCALATION_AUDIT_ONLY, od.CHANNEL_DASHBOARD_ONLY),
    "bank_correction_required": ("standard", od.URGENCY_ACTION_NOW, od.ESCALATION_DELIVERY_ISSUE, od.CHANNEL_WHATSAPP_OK),
    # Employee App activation code (metadata-only sensitivity; code never persisted
    # in message bodies). Critical: HR must know if the code never reached the
    # employee, so failure escalates to an HR task.
    "app_activation": ("critical", od.URGENCY_ACTION_NOW, od.ESCALATION_HR_TASK, od.CHANNEL_WHATSAPP_OK),
}

# Expected reminder cap windows (must stay stable through this metadata-only batch).
EXPECTED_CAPS = {
    "onboarding_reminder": 24,
    "compliance_document_required": 24,
    "compliance_document_expiring": 24,
    "payroll_timesheet_ready": 72,
    "attendance_missed_checkin": 24,
}


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

    # --- 1. Catalog contract: every key has all 3 fields with valid enums -----
    checks.check("every catalog key is covered by the Phase-1 expectation set", lambda: set(catalog) == set(EXPECTED))
    for key, entry in catalog.items():
        checks.check(f"{key}: has delivery_urgency (valid enum)", (lambda e=entry: e.get("delivery_urgency") in od.DELIVERY_URGENCIES))
        checks.check(f"{key}: has failure_escalation (valid enum)", (lambda e=entry: e.get("failure_escalation") in od.FAILURE_ESCALATIONS))
        checks.check(f"{key}: has employee_channel_intent (valid enum)", (lambda e=entry: e.get("employee_channel_intent") in od.CHANNEL_INTENTS))
        checks.check(f"{key}: still has legacy criticality (runtime source of truth)", (lambda e=entry: e.get("criticality") in (od.CRITICALITY_CRITICAL, od.CRITICALITY_STANDARD, od.CRITICALITY_INFORMATIONAL)))

    # --- 2. No behavior change: derived criticality == legacy criticality -----
    for key, entry in catalog.items():
        checks.check(
            f"{key}: derived_criticality(failure_escalation) == legacy criticality",
            (lambda e=entry: od.derived_criticality(e.get("failure_escalation")) == e.get("criticality")),
        )

    # --- 2b. Values match the approved Phase-1 expectation exactly ------------
    for key, (crit, urg, esc, chan) in EXPECTED.items():
        entry = catalog.get(key, {})
        checks.check(
            f"{key}: matches approved Phase-1 semantics",
            (lambda e=entry, c=crit, u=urg, s=esc, ch=chan: e.get("criticality") == c and e.get("delivery_urgency") == u and e.get("failure_escalation") == s and e.get("employee_channel_intent") == ch),
        )

    # --- 3. Hard channel-intent assertions (anti-leak guarantee) --------------
    checks.check("payroll_timesheet_ready is email_only", lambda: catalog["payroll_timesheet_ready"]["employee_channel_intent"] == od.CHANNEL_EMAIL_ONLY)
    checks.check("attendance_missed_checkin is dashboard_only", lambda: catalog["attendance_missed_checkin"]["employee_channel_intent"] == od.CHANNEL_DASHBOARD_ONLY)
    checks.check("compliance_document_required is email_first", lambda: catalog["compliance_document_required"]["employee_channel_intent"] == od.CHANNEL_EMAIL_FIRST)
    checks.check("compliance_document_expiring is email_first", lambda: catalog["compliance_document_expiring"]["employee_channel_intent"] == od.CHANNEL_EMAIL_FIRST)

    # Forward-proof: ANY payroll/admin/compliance/attendance key (now or future)
    # may never be whatsapp_ok, so a preset can never push it down the shared WA
    # sender. payroll/admin must be email_only or dashboard_only.
    for key, entry in catalog.items():
        chan = entry.get("employee_channel_intent")
        if key.startswith("payroll") or key.startswith("admin"):
            checks.check(f"{key}: payroll/admin restricted to email_only/dashboard_only", (lambda c=chan: c in (od.CHANNEL_EMAIL_ONLY, od.CHANNEL_DASHBOARD_ONLY)))
        if key.startswith("compliance"):
            checks.check(f"{key}: compliance never whatsapp_ok", (lambda c=chan: c != od.CHANNEL_WHATSAPP_OK))
        if key.startswith("attendance"):
            checks.check(f"{key}: attendance is dashboard_only (HR-only, no employee push)", (lambda c=chan: c == od.CHANNEL_DASHBOARD_ONLY))

    # --- 4. Reminder caps stable + templates OFF ------------------------------
    checks.check("reminder cap windows unchanged", lambda: app.REMINDER_CAP_HOURS == EXPECTED_CAPS)
    checks.check("shift_reminder is NOT per-employee capped (per-shift unit)", lambda: app.reminder_cap_window_hours("shift_reminder") is None)
    checks.check("WATHEFNI_OUTBOUND_TEMPLATES stays off", lambda: app.outbound_templates_enabled() is False)


def main() -> None:
    print("notification semantics — Phase 1 contract harness (behavior-frozen, no DB)")
    checks = Checks()
    run_checks(checks)
    code = checks.report()
    if code:
        print("\nNOTIFICATION SEMANTICS HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nNOTIFICATION SEMANTICS HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
