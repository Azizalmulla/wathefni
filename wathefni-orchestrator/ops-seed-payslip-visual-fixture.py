#!/usr/bin/env python3
"""Seed disposable multi-year payslip fixtures for Employee App visual QA.

Target: WATHEFNI-96550010001 (Noura) — already on the employee-app allowlist.
Aziz/Talal are never touched. Rows are tagged in document_payload.fixture for cleanup.

Does not enable PAYROLL_WAVE3 mutations for real employees; inserts released
external_import documents the employee list already knows how to read.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
import payroll_payslip_wave3 as w3  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
KEY = f"{COMPANY}-96550010001"
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
TAG = "payslip-visual-fixture"
STAMP = os.environ.get("PAYSLIP_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _guard() -> None:
    if KEY in PROTECTED:
        raise SystemExit(f"refusing protected canary key {KEY}")


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _periods() -> list[tuple[date, date, float, float]]:
    """(start, end, earnings, deductions) — enough for year groups + has_more."""
    rows: list[tuple[date, date, float, float]] = []
    # Current year months through August 2026
    for m in range(1, 9):
        end = _month_end(2026, m)
        earn = 820.0 + m * 7.5
        ded = 45.0 + (m % 3) * 4.0
        rows.append((date(2026, m, 1), end, earn, ded))
    # Full prior year
    for m in range(1, 13):
        end = _month_end(2025, m)
        earn = 790.0 + m * 6.0
        ded = 40.0 + (m % 4) * 3.5
        rows.append((date(2025, m, 1), end, earn, ded))
    # Older year sample (10 months) so Load earlier appears with limit=24
    for m in range(3, 13):
        end = _month_end(2024, m)
        earn = 760.0 + m * 5.0
        ded = 38.0 + (m % 5) * 2.5
        rows.append((date(2024, m, 1), end, earn, ded))
    return rows


def cleanup() -> dict[str, Any]:
    _guard()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM payroll_payslip_lines
                WHERE company_code=%s AND employee_key=%s
                  AND payslip_id IN (
                    SELECT payslip_id FROM payroll_payslip_documents
                    WHERE company_code=%s AND employee_key=%s
                      AND COALESCE(document_payload->>'fixture','') = %s
                  )
                """,
                (COMPANY, KEY, COMPANY, KEY, TAG),
            )
            lines = cur.rowcount
            cur.execute(
                """
                DELETE FROM payroll_payslip_documents
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(document_payload->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            docs = cur.rowcount
        conn.commit()
    return {"employee_key": KEY, "deleted_docs": docs, "deleted_lines": lines, "stamp": STAMP}


def seed() -> dict[str, Any]:
    _guard()
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or {}
    if not emp:
        raise SystemExit(f"missing synthetic employee {KEY}")

    cleanup()  # replace prior fixture family

    periods = _periods()
    created: list[str] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            w3.ensure_payroll_wave3_schema(cur)
            for i, (start, end, earn, ded) in enumerate(periods):
                pid = str(uuid.uuid4())
                run = str(uuid.uuid4())
                net = round(earn - ded, 3)
                released = datetime(end.year, end.month, min(end.day, 28), 9, 0, tzinfo=timezone(timedelta(hours=3)))
                payload = Json(
                    {
                        "fixture": TAG,
                        "stamp": STAMP,
                        "purpose": "payslip_visual_qa",
                        "seq": i,
                    }
                )
                cur.execute(
                    """
                    INSERT INTO payroll_payslip_documents (
                      payslip_id, company_code, employee_key, source_kind, source_run_id,
                      period_start, period_end, version_number, status,
                      content_fingerprint, money_authority, authoritative_label,
                      employee_visibility, employee_released_at,
                      currency, totals_earnings, totals_deductions, totals_net,
                      document_payload, created_at
                    ) VALUES (
                      %s::uuid, %s, %s, 'external_import', %s::uuid,
                      %s, %s, 1, 'active',
                      %s, 'external', %s,
                      'released', %s,
                      'KWD', %s, %s, %s,
                      %s, %s
                    )
                    """,
                    (
                        pid,
                        COMPANY,
                        KEY,
                        run,
                        start,
                        end,
                        f"{TAG}-{STAMP}-{i}",
                        f"{TAG}:{STAMP}",
                        released,
                        earn,
                        ded,
                        net,
                        payload,
                        released + timedelta(hours=1),
                    ),
                )
                lines = [
                    ("basic", "BASIC", "Basic salary", "الراتب الأساسي", earn * 0.7, 10),
                    ("allowance", "HOUSING", "Housing allowance", "بدل السكن", earn * 0.2, 20),
                    ("earning", "TRANSPORT", "Transport allowance", "بدل مواصلات", earn * 0.1, 30),
                    ("deduction", "PIFSS", "Social insurance", "التأمينات", -ded, 40),
                ]
                for kind, code, en, ar, amount, sort in lines:
                    cur.execute(
                        """
                        INSERT INTO payroll_payslip_lines (
                          payslip_id, company_code, employee_key, line_kind, code,
                          label_en, label_ar, amount, currency, sort_order
                        ) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, 'KWD', %s)
                        """,
                        (pid, COMPANY, KEY, kind, code, en, ar, round(amount, 3), sort),
                    )
                created.append(pid)
        conn.commit()

    # Ensure app access + fresh activation for physical login
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": "payslip-visual-fixture",
                "actor_user_id": "payslip-visual-fixture",
                "email": "payslip-visual-fixture@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=KEY,
            enabled=True,
            reason="payslip-visual-fixture",
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp

    invite, code = legacy.create_employee_app_invite(
        COMPANY, emp, created_by_user_id="payslip-visual-fixture"
    )

    phone = legacy.digits(emp.get("phone"))
    ctx = {
        "company_code": COMPANY,
        "employee_key": KEY,
        "employee": emp,
        "phone": phone,
        "session_id": f"payslip-visual-{STAMP}",
        "actor_employee_key": KEY,
        "actor_user_id": f"employee_app:{KEY}",
        "actor_phone": phone,
        "actor_email": emp.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {"role": "employee", "company_code": COMPANY, "phone": phone, "name": emp.get("name") or ""},
    }
    page = legacy.app_payslips(locale="en", limit=24, cursor=None, context=ctx)
    years = sorted(
        {
            str(p.get("period_end"))[:4]
            for p in (page.get("payslips") or [])
            if p.get("period_end")
        },
        reverse=True,
    )
    ok = (
        int(page.get("count") or 0) == 24
        and bool(page.get("has_more"))
        and bool(page.get("next_cursor"))
        and len(created) == len(periods)
        and "2026" in years
    )
    return {
        "ok": ok,
        "stamp": STAMP,
        "employee_key": KEY,
        "name": emp.get("name"),
        "phone": phone,
        "activation_code": code,
        "invite_expires_at": str(invite.get("expires_at") or ""),
        "seeded_count": len(created),
        "first_page_count": page.get("count"),
        "has_more": page.get("has_more"),
        "years_on_first_page": years,
        "protected_untouched": sorted(PROTECTED),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        print(json.dumps(cleanup(), indent=2))
        return 0
    result = seed()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
