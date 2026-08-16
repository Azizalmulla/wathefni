#!/usr/bin/env python3
"""Unit/contract smoke for Employee App push tray policy (no DB / no network)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import employee_push_tray as tray  # noqa: E402
import outbound_delivery as od  # noqa: E402


def main() -> int:
    failed: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        print(("PASS" if ok else "FAIL"), f"{label}{suffix}")
        if not ok:
            failed.append(label)

    check("activation never push-allowed", not tray.push_allowed(flow="app_activation", template_key="app_activation"))
    check("leave push-allowed", tray.push_allowed(flow="leave_decision", template_key="leave_request_approved"))
    check("bank template in catalog", "bank_correction_required" in od.TEMPLATE_CATALOG)

    # Freeze "today" expectations via ISO inputs in current year — format omits year.
    # Use explicit year-bearing examples for payslip / cross-year.
    examples = [
        (
            "leave_request_approved",
            {"start_date": "2026-08-23", "end_date": "2026-08-25"},
            "Leave approved",
            "Your leave from 23–25 Aug has been approved.",
        ),
        (
            "leave_request_rejected",
            {"start_date": "2026-08-23", "end_date": "2026-08-25"},
            "Leave rejected",
            "Your leave request for 23–25 Aug was not approved.",
        ),
        (
            "shift_rescheduled",
            {"shift_date": "2026-08-12", "shift_time": "09:00-17:00"},
            "Shift updated",
            "Your shift on 12 Aug is now 9:00 AM–5:00 PM.",
        ),
        (
            "shift_assigned",
            {"shift_date": "2026-08-12", "shift_time": "09:00-17:00"},
            "New shift",
            "Your shift on 12 Aug is 9:00 AM–5:00 PM.",
        ),
        (
            "shift_reminder",
            {"shift_date": date.today().isoformat(), "shift_time": "09:00"},
            "Shift reminder",
            "Your shift starts at 9:00 AM today.",
        ),
        (
            "shift_cancelled",
            {"shift_date": "2026-08-12"},
            "Shift cancelled",
            "Your shift on 12 Aug was cancelled.",
        ),
        (
            "compliance_document_expiring",
            {"document_type": "Civil ID", "expiry_date": "2026-08-27"},
            "Document expiring",
            "Your Civil ID expires on 27 Aug.",
        ),
        (
            "compliance_document_required",
            {"document_type": "Civil ID"},
            "Document action needed",
            "Please update your Civil ID.",
        ),
        (
            "payslip_ready",
            {"period": "2026-08"},
            "Payslip ready",
            "Your August 2026 payslip is ready.",
        ),
        (
            "onboarding_reminder",
            {},
            "Onboarding action needed",
            "You have an onboarding item waiting for you.",
        ),
        (
            "employee_onboarding_welcome",
            {},
            "Onboarding started",
            "You have onboarding steps waiting for you.",
        ),
        (
            "bank_correction_required",
            {},
            "Bank details need attention",
            "Please update your bank details.",
        ),
    ]

    print("\n=== EN tray examples ===")
    for key, variables, want_title, want_body in examples:
        title, body = tray.tray_copy(key, locale="en", variables=variables)
        print(f"{key}: {title} — {body}")
        check(f"en:{key}:title", title == want_title, f"got={title!r}")
        check(f"en:{key}:body", body == want_body, f"got={body!r}")
        check(f"en:{key}:no-iso", "2026-08" not in body or key == "payslip_ready")
        # payslip uses August 2026 not ISO; the check above is weak for payslip — strengthen:
        if key != "payslip_ready":
            check(f"en:{key}:no-iso-date", not re_has_iso(body))

    print("\n=== AR tray examples ===")
    ar_cases = [
        ("leave_request_approved", {"start_date": "2026-08-23", "end_date": "2026-08-25"}),
        ("leave_request_rejected", {"start_date": "2026-08-23", "end_date": "2026-08-25"}),
        ("shift_rescheduled", {"shift_date": "2026-08-12", "shift_time": "09:00-17:00"}),
        ("shift_reminder", {"shift_time": "09:00"}),
        ("compliance_document_expiring", {"document_type": "البطاقة المدنية", "expiry_date": "2026-08-27"}),
        ("compliance_document_required", {"document_type": "البطاقة المدنية"}),
        ("payslip_ready", {"period": "2026-08"}),
        ("onboarding_reminder", {}),
        ("bank_correction_required", {}),
        ("shift_cancelled", {"shift_date": "2026-08-12"}),
        ("shift_assigned", {"shift_date": "2026-08-12", "shift_time": "09:00"}),
        ("employee_onboarding_welcome", {}),
    ]
    for key, variables in ar_cases:
        title, body = tray.tray_copy(key, locale="ar", variables=variables)
        print(f"{key}: {title} — {body}")
        check(f"ar:{key}:present", bool(title) and bool(body))
        check(f"ar:{key}:no-iso-date", not re_has_iso(body))
        check(f"ar:{key}:no-open-cta", "افتح" not in body and "Open " not in body)

    # ISO date_text input still humanized
    title, body = tray.tray_copy(
        "leave_request_approved",
        locale="en",
        variables={"date_text": "2026-08-23 to 2026-08-25"},
    )
    check("iso date_text humanized", body == "Your leave from 23–25 Aug has been approved.", body)

    title_ar, body_ar = tray.tray_copy("payslip_ready", locale="ar", variables={"period": "June 2026"})
    check("tray ar present", bool(title_ar) and bool(body_ar))

    cid = tray.collapse_id(
        company_code="WATHEFNI",
        flow="payroll",
        template_key="payslip_ready",
        subject_key="E1",
        dedupe_key="payslip_ready:abc",
    )
    check("collapse stable", cid == "WATHEFNI:payslip_ready:abc")

    check("reminder time-sensitive", tray.interruption_level("shift_reminder") == "timeSensitive")
    check(
        "future cancel not time-sensitive",
        tray.interruption_level("shift_cancelled", variables={"shift_date": "2099-01-01"}) is None,
    )
    check(
        "same-day cancel time-sensitive",
        tray.interruption_level("shift_cancelled", variables={"shift_date": date.today().isoformat()})
        == "timeSensitive",
    )

    src = Path(od.__file__).read_text()
    check("ladder skips inbox-only push", "push_inbox_only_policy" in src or "inbox_only_policy" in src)
    check("ladder uses tray_copy", "tray_copy" in src)

    print(f"\n{len(failed)} failed")
    return 1 if failed else 0


def re_has_iso(text: str) -> bool:
    import re

    return bool(re.search(r"\d{4}-\d{2}-\d{2}", text))


if __name__ == "__main__":
    raise SystemExit(main())
