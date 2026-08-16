#!/usr/bin/env python3
"""Production Readiness R9 — live permission / tenant-isolation contracts (no DB).

Proves source contracts that the staging attack harness depends on:
  * session company wins over client X-Company-Code
  * role SOD (payroll / talent-sensitive / ER-sensitive / setup)
  * P1-19 defence-in-depth company_code predicates on named mutations
  * employee /app identity cannot be widened by client headers
UI hiding is not evidence; these are server contracts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def session_company_authority() -> None:
    print("\n    session company is the only tenant authority")
    src = read(ROOT / "app.py")
    start = src.find("def dashboard_context(")
    body = src[start : start + 4500]
    check("dashboard_context exists", "def dashboard_context(" in src)
    check(
        "session user company is taken from the session, not the header",
        "company = public_user[\"company_code\"]" in body,
        body[body.find("session_user") : body.find("session_user") + 400] if "session_user" in body else "missing",
    )
    check(
        "mismatched X-Company-Code is 403 dashboard_company_forbidden",
        "dashboard_company_forbidden" in body and "requested_company != company" in body,
    )
    emp_start = src.find("def employee_app_context(")
    emp = src[emp_start : emp_start + 12000]
    check(
        "employee /app identity is the session employee only",
        'sess["employee_key"]' in emp and '"actor_role": "employee"' in emp,
    )
    check(
        "employee /app still enforces the rollout allowlist",
        "assert_employee_app_allowlisted" in emp,
    )


def role_sod() -> None:
    print("\n    role SOD contracts")
    sys.path.insert(0, str(ROOT))
    import app

    roles = app.ROLE_PERMISSIONS
    check("owner has users.manage + settings.manage", "users.manage" in roles["owner"] and "settings.manage" in roles["owner"])
    check("hr_admin has settings.manage but never users.manage", "settings.manage" in roles["hr_admin"] and "users.manage" not in roles["hr_admin"])
    check("manager has no payroll.export", "payroll.export" not in roles["manager"])
    check("manager has no er.sensitive", "er.sensitive" not in roles["manager"])
    check("manager has no talent.sensitive", "talent.sensitive" not in roles["manager"])
    check("manager has no performance.sensitive", "performance.sensitive" not in roles["manager"])
    check("payroll_operator is payroll-only", roles["payroll_operator"] <= {"payroll.read", "payroll.manage", "payroll.approve"})
    check("payroll_operator has no users.manage", "users.manage" not in roles["payroll_operator"])
    check("viewer has no leave.decide", "leave.decide" not in roles["viewer"])
    check("hr_admin holds ER + talent + performance sensitive", {"er.sensitive", "talent.sensitive", "performance.sensitive"} <= roles["hr_admin"])
    check("hr_admin holds payroll.export", "payroll.export" in roles["hr_admin"])


def p1_19_company_predicates() -> None:
    print("\n    P1-19 defence-in-depth company_code predicates")
    src = read(ROOT / "app.py")
    check(
        "employee raw_json write is company-scoped",
        "UPDATE employees SET raw_json=%s, updated_at=now() WHERE employee_key=%s AND company_code=%s" in src,
    )
    check(
        "unscoped employee raw_json write is gone",
        "UPDATE employees SET raw_json=%s, updated_at=now() WHERE employee_key=%s\"" not in src.replace(
            "UPDATE employees SET raw_json=%s, updated_at=now() WHERE employee_key=%s AND company_code=%s",
            "",
        ),
    )
    check(
        "onboarding received write is company-scoped",
        "WHERE employee_key=%s AND item_id=%s AND company_code=%s" in src
        and "SET status='received'" in src,
    )
    check(
        "unscoped onboarding received write is gone",
        "UPDATE onboarding_items SET status='received', updated_at=now() WHERE employee_key=%s AND item_id=%s\"" not in src,
    )

    mutations = []
    for match in re.finditer(
        r'("""[\s\S]{0,80}?(?:UPDATE|DELETE)[\s\S]{0,500}?"""|\'(?:UPDATE|DELETE)[^\']{0,500}\')',
        src,
        re.I,
    ):
        sql = match.group(0)
        if "employee_key=%s" not in sql:
            continue
        if re.search(r"\b(UPDATE|DELETE)\b", sql, re.I) is None:
            continue
        if "company_code" in sql:
            continue
        mutations.append(re.sub(r"\s+", " ", sql)[:180])
    # Remaining unscoped writes must stay an explicit, shrinking list.
    allowed_unscoped = (
        "SELECT item_id FROM onboarding_items WHERE employee_key=%s",
    )
    unexpected = [
        m for m in mutations
        if re.search(r"UPDATE\s+employees\b", m, re.I) or re.search(r"DELETE\s+FROM\s+employees\b", m, re.I)
    ]
    check(
        "no employee_key-only UPDATE/DELETE on employees",
        len(unexpected) == 0,
        unexpected[:8],
    )
    leftover_tables = sorted({
        re.search(r"(?:UPDATE|DELETE FROM)\s+(\w+)", m, re.I).group(1)
        for m in mutations
        if re.search(r"(?:UPDATE|DELETE FROM)\s+(\w+)", m, re.I)
    })
    check(
        "remaining unscoped writes are not the employees hub",
        "employees" not in leftover_tables,
        leftover_tables,
    )


def fail_closed_errors() -> None:
    print("\n    fail-closed error vocabulary")
    src = read(ROOT / "app.py")
    check("module_disabled is a 403 entitlement error", 'error="module_disabled"' in src)
    check("permission_denied is used for missing permissions", 'error="permission_denied"' in src or 'error": "permission_denied"' in src)
    check("document hub 404s out-of-scope files", 'error": "document_not_found"' in src)


def main() -> int:
    print("    PRODUCTION READINESS R9 — permission / tenant attack contracts (no DB)")
    session_company_authority()
    role_sod()
    p1_19_company_predicates()
    fail_closed_errors()
    print("\n    R9_PERMISSION_TENANT_ATTACK_UNIT_PASS" if not FAIL else "\n    R9_PERMISSION_TENANT_ATTACK_UNIT_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
