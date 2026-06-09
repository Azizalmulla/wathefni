"""Smoke test: Employee 360 profile (read-only, tenant + entitlement scoped).

The unified employee profile composes per-module reads around one person. It must
never leak across tenants and must only surface modules the company has and the
user can read. This test pins:

  - the profile resolves an employee within the session company and returns a
    structured, JSON-safe payload (employee + sections + next_actions)
  - tenant isolation: the same employee_key under a different company does not
    resolve (404)
  - entitlement gating: a section only appears when the user can read that module
  - an empty/unknown key is a clean 404

Run against a DB (staging): python3 smoke-test-employee-profile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    employee 360 — read-only profile, tenant + entitlement scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    def ctx(company: str, permissions: list[str]):
        return {
            "company_code": company,
            "permissions": permissions,
            "access": {"role": "owner", "permissions": permissions},
            "actor_user_id": "smoke-owner",
            "actor_role": "owner",
            "hr_user": {"role": "owner", "status": "active", "company_code": company},
        }

    owner_perms = sorted(app.hr_role_permissions("owner"))
    valid_section_keys = {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll"}
    # Composite sections are derived from one or more modules' read access rather
    # than being a module themselves (e.g. the Document Hub surfaces files when the
    # user can read onboarding OR compliance). They are not in available_modules.
    composite_sections = {"documents"}

    # locate a real employee to profile
    real_emp = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code, employee_key, name FROM employees WHERE employee_key <> '' LIMIT 1")
            row = cur.fetchone()
            if row:
                real_emp = dict(row)

    if not real_emp:
        print("    (no employees on this DB — running structural checks only)")
        # Empty key still 404s regardless of data.
        try:
            app.dashboard_employee_profile(ctx("WATHEFNI", owner_perms), "")
            check("empty key raises 404", False)
        except app.HTTPException as exc:
            check("empty key raises 404", exc.status_code == 404)
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 0 if FAIL == 0 else 1

    company = str(real_emp["company_code"])
    key = str(real_emp["employee_key"])

    # 1) resolves within the session company with a structured payload
    profile = app.dashboard_employee_profile(ctx(company, owner_perms), key)
    check("profile resolves the requested employee", (profile.get("employee") or {}).get("employee_key") == key)
    check("profile carries the session company", profile.get("company_code") == company)
    sections = profile.get("sections") or {}
    check("sections is a dict", isinstance(sections, dict))
    check("next_actions is a list", isinstance(profile.get("next_actions"), list))
    available = set(profile.get("available_modules") or [])
    check("available_modules is a subset of the post-hire modules", available <= valid_section_keys)
    check("every rendered section is an available module", (set(sections.keys()) - composite_sections) <= available)
    # The documents composite, when present, must be backed by an available module.
    check("documents section implies onboarding/compliance access", "documents" not in sections or bool(available & {"onboarding", "compliance"}))

    # 2) tenant isolation — same key under a different company does not resolve
    try:
        app.dashboard_employee_profile(ctx("ZZ_NOT_A_TENANT", owner_perms), key)
        check("cross-tenant lookup is blocked (404)", False)
    except app.HTTPException as exc:
        check("cross-tenant lookup is blocked (404)", exc.status_code == 404)

    # 3) entitlement gating — only onboarding.read present -> no payroll/attendance section
    limited = app.employee_profile_accessible_modules(ctx(company, ["onboarding.read"]), company)
    check("limited perms exclude payroll", "payroll" not in limited)
    check("limited perms exclude attendance", "attendance" not in limited)
    check("limited perms cannot exceed onboarding", set(limited) <= {"onboarding"})

    # 4) empty key -> clean 404
    try:
        app.dashboard_employee_profile(ctx(company, owner_perms), "")
        check("empty key raises 404", False)
    except app.HTTPException as exc:
        check("empty key raises 404", exc.status_code == 404)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    EMPLOYEE 360: FAILURES")
        return 1
    print("    EMPLOYEE 360: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
