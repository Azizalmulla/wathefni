#!/usr/bin/env python3
"""Employee App payslip list keyset pagination contract.

Proves released-payslip paging via ``has_more`` / ``next_cursor`` without a
raised silent hard cap. Synthetic documents only; Aziz/Talal untouched.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
import payroll_payslip_wave3 as w3  # noqa: E402
from fastapi import HTTPException  # noqa: E402

COMPANY = "WATHEFNI"
TAG = uuid.uuid4().hex[:8]
EMP = f"PAYPAGE-{TAG}"
FAILS: list[str] = []
DOC_IDS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def seed(n: int = 5) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            w3.ensure_payroll_wave3_schema(cur)
            for i in range(n):
                end = date(2024, 1, 31) + timedelta(days=31 * i)
                start = end.replace(day=1)
                pid = str(uuid.uuid4())
                run = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO payroll_payslip_documents (
                      payslip_id, company_code, employee_key, source_kind, source_run_id,
                      period_start, period_end, version_number, status,
                      content_fingerprint, money_authority, authoritative_label,
                      employee_visibility, employee_released_at,
                      currency, totals_earnings, totals_deductions, totals_net,
                      created_at
                    ) VALUES (
                      %s::uuid, %s, %s, 'external_import', %s::uuid,
                      %s, %s, 1, 'active',
                      %s, 'external', 'smoke-page',
                      'released', NOW(),
                      'KWD', 100, 0, 100,
                      NOW() - (%s || ' hours')::interval
                    )
                    """,
                    (
                        pid,
                        COMPANY,
                        EMP,
                        run,
                        start,
                        end,
                        f"fp-{TAG}-{i}",
                        str((n - i) * 3),
                    ),
                )
                DOC_IDS.append(pid)
        conn.commit()


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
        conn.commit()


def main() -> int:
    sample = {
        "period_end": "2024-06-30",
        "created_at": "2024-07-01T12:00:00+00:00",
        "payslip_id": "abc",
    }
    token = w3.encode_employee_payslip_list_cursor(sample)
    decoded = w3.decode_employee_payslip_list_cursor(token)
    check(
        "cursor round-trips",
        decoded == {"pe": "2024-06-30", "ca": "2024-07-01T12:00:00+00:00", "id": "abc"},
    )
    try:
        w3.decode_employee_payslip_list_cursor("!!!")
        check("malformed cursor raises", False)
    except ValueError:
        check("malformed cursor raises", True)

    seed(5)
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                p1 = w3.list_employee_released_payslips_page(
                    cur, company_code=COMPANY, employee_key=EMP, limit=2
                )
                check("page1 has_more", p1["has_more"] is True)
                check("page1 size", len(p1["payslips"]) == 2)
                check("page1 next_cursor", bool(p1.get("next_cursor")))
                p2 = w3.list_employee_released_payslips_page(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP,
                    limit=2,
                    cursor=p1["next_cursor"],
                )
                ids1 = {str(r["payslip_id"]) for r in p1["payslips"]}
                ids2 = {str(r["payslip_id"]) for r in p2["payslips"]}
                check("pages do not overlap", ids1.isdisjoint(ids2))
                p3 = w3.list_employee_released_payslips_page(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP,
                    limit=2,
                    cursor=p2["next_cursor"],
                )
                check(
                    "final page drains",
                    p3["has_more"] is False and len(p3["payslips"]) == 1,
                    f"has_more={p3['has_more']} n={len(p3['payslips'])}",
                )
                all_ids = ids1 | ids2 | {str(r["payslip_id"]) for r in p3["payslips"]}
                check("all five rows reachable", len(all_ids) == 5, str(len(all_ids)))
                # Wrapper still returns a plain list for Home callers.
                listed = w3.list_employee_released_payslips(
                    cur, company_code=COMPANY, employee_key=EMP, limit=3
                )
                check("compat wrapper returns list", isinstance(listed, list) and len(listed) == 3)

        # Route-level invalid cursor
        ctx = {
            "company_code": COMPANY,
            "employee_key": EMP,
            "employee": {"phone": "96570000000", "email": "", "name": "page"},
            "phone": "96570000000",
            "session_id": f"page-{TAG}",
            "actor_employee_key": EMP,
            "actor_user_id": f"employee_app:{EMP}",
            "actor_phone": "96570000000",
            "actor_email": "",
            "actor_role": "employee",
            "hr_phone": "",
            "hr_user": {"role": "employee", "company_code": COMPANY, "phone": "96570000000", "name": "page"},
        }

        real_require = legacy.require_employee_app_feature
        real_enabled = w3.payroll_wave3_enabled_for_company

        def fake_require(_ctx: Any, feature: str, action: str | None = None) -> dict[str, Any]:
            return {"enabled": True, "actions": ["download"]}

        legacy.require_employee_app_feature = fake_require  # type: ignore[assignment]
        w3.payroll_wave3_enabled_for_company = lambda _c: True  # type: ignore[assignment]
        try:
            try:
                legacy.app_payslips(locale="en", limit=2, cursor="not-a-cursor", context=ctx)
                check("invalid cursor → HTTP 400", False)
            except HTTPException as exc:
                err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
                check("invalid cursor → HTTP 400", exc.status_code == 400 and err == "invalid_cursor")
            page = legacy.app_payslips(locale="en", limit=2, cursor=None, context=ctx)
            check(
                "HTTP page exposes has_more + next_cursor",
                page.get("has_more") is True and bool(page.get("next_cursor")),
                str({k: page.get(k) for k in ("has_more", "next_cursor", "count")}),
            )
        finally:
            legacy.require_employee_app_feature = real_require  # type: ignore[assignment]
            w3.payroll_wave3_enabled_for_company = real_enabled  # type: ignore[assignment]
    finally:
        cleanup()

    print("---")
    if FAILS:
        print(f"FAIL employee payslip pagination contract ({len(FAILS)})")
        return 1
    print("PASS employee payslip pagination contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
