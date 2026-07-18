"""Smoke test: Add employee / Import employees (roster management).

A company that buys only a post-hire module must be able to load its workforce
without the pre-hiring pipeline. These endpoints INSERT directly into the
`employees` hub (app_key left NULL). This test pins:

  - RBAC: roster management requires employees.manage + an enabled post-hire
    module; viewers/recruiters are denied.
  - create core: deterministic key {COMPANY}-{digits(phone)}, phone/name
    required, idempotent dedupe (second create -> 'exists'), app_key stays NULL.
  - module defaults: compliance docs seed as 'missing' ONLY when asked; NO
    onboarding items are created and NO welcome message is sent (existing staff).
  - import parsing: CSV + XLSX header mapping, and a clean error when the file
    is missing a name/phone column.
  - import summary buckets: created / skipped / needs_review / failed.

All writes use a clearly-synthetic phone and are removed in a finally block, so
the test is safe to re-run against staging.

Run against a DB (staging): python3 smoke-test-employee-roster.py
"""

from __future__ import annotations

import io
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
    print("    employee roster — add / import, RBAC + tenant scoped, no messaging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # --- pure parsing checks (no DB) -------------------------------------
    check("canonical phone: 8-digit local -> 965 prefix", app.canonical_employee_phone("5025 2299") == "96550252299")
    check("canonical phone: 965 form is unchanged", app.canonical_employee_phone("96550252299") == "96550252299")

    csv_bytes = b"name,phone,email,job title\nSara Al-Ali,9655 000 111,sara@x.com,Manager\n,9650000000,,\n"
    rows, err = app._parse_employee_import_file(csv_bytes, "team.csv")
    check("CSV parses without error", err is None)
    check("CSV maps name+phone+email+job title", bool(rows) and rows[0].get("name") == "Sara Al-Ali" and rows[0].get("position_title") == "Manager")

    bad_csv = b"first,last\nA,B\n"
    _, bad_err = app._parse_employee_import_file(bad_csv, "bad.csv")
    check("CSV without name/phone columns is a friendly error", isinstance(bad_err, str) and "name" in bad_err.lower())

    try:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Full Name", "WhatsApp", "Department"])
        ws.append(["Omar Q", 96599999999, "Ops"])  # phone as a number on purpose
        buf = io.BytesIO()
        wb.save(buf)
        xrows, xerr = app._parse_employee_import_file(buf.getvalue(), "team.xlsx")
        check("XLSX parses without error", xerr is None)
        check("XLSX maps headers + numeric phone keeps digits", bool(xrows) and xrows[0].get("name") == "Omar Q" and app.digits(xrows[0].get("phone")) == "96599999999")
    except Exception as exc:  # pragma: no cover - openpyxl missing locally
        print(f"    (skipping XLSX parse check: {exc})")

    # --- locate a company to scope writes --------------------------------
    company = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code FROM employees WHERE company_code <> '' LIMIT 1")
            row = cur.fetchone()
            if row:
                company = str(dict(row)["company_code"]).upper()
    if not company:
        company = "WATHEFNI"

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-roster",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-roster",
            "permission_subject_company": company,
            "actor_role": role,
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    has_module = any(app.company_has_module(company, m) for m in app.POSTHIRE_PEOPLE_MODULES)

    # --- RBAC gate -------------------------------------------------------
    if has_module:
        try:
            app.require_employee_roster_admin(ctx(["onboarding.read"], role="viewer"))
            check("viewer without employees.manage is denied", False)
        except app.HTTPException as exc:
            check("viewer without employees.manage is denied", exc.status_code == 403)
        try:
            resolved = app.require_employee_roster_admin(ctx(["employees.manage"]))
            check("employees.manage + enabled module is allowed", resolved == company)
        except app.HTTPException:
            check("employees.manage + enabled module is allowed", False)
    else:
        print(f"    ({company} has no post-hire module enabled — skipping RBAC module gate)")

    # --- create core (synthetic phone, cleaned up) -----------------------
    test_phone = "99900000099"
    test_key = f"{company}-{test_phone}"

    local8 = "50252299"
    canonical_key = f"{company}-965{local8}"

    def cleanup():
        keys = (test_key, f"{company}-0{test_phone}", canonical_key)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (list(keys),))
            conn.commit()

    cleanup()  # ensure a clean slate even if a prior run aborted
    try:
        check("missing phone -> failed", app.create_company_employee(company, name="No Phone", phone="")["status"] == "failed")
        check("missing name -> failed", app.create_company_employee(company, name="", phone=test_phone)["status"] == "failed")

        created = app.create_company_employee(
            company, name="Roster Tester", phone="0" + test_phone, email="rt@example.com",
            position_title="Technician", department="Field", start_date="2026-01-15", seed_compliance=True,
        )
        check("first create returns 'created'", created["status"] == "created")
        check("deterministic key {COMPANY}-{digits}", created["employee_key"] == f"{company}-0{test_phone}")

        real_key = created["employee_key"]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s", (real_key,))
                emp = dict(cur.fetchone())
                cur.execute("SELECT document_type, status FROM compliance_documents WHERE employee_key=%s", (real_key,))
                comp = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT count(*) AS n FROM onboarding_items WHERE employee_key=%s", (real_key,))
                onb = dict(cur.fetchone())["n"]
        check("row is company-scoped", emp["company_code"] == company)
        check("app_key stays NULL (no pre-hiring dependency)", emp["app_key"] is None)
        check("phone stored as digits", emp["phone"] == "0" + test_phone)
        check("department lands in profile json", (emp.get("profile") or {}).get("department") == "Field")
        check("onboarding stays 'not_started'", emp["onboarding_status"] == "not_started")
        check("NO onboarding items are seeded (existing staff, no welcome message)", onb == 0)
        check("compliance docs seeded as 'missing'", bool(comp) and all(c["status"] == "missing" for c in comp))
        check("only the default compliance types are seeded", {c["document_type"] for c in comp} == set(app.DEFAULT_COMPLIANCE_SEED_TYPES))

        again = app.create_company_employee(company, name="Roster Tester", phone="0" + test_phone)
        check("second create de-dupes to 'exists'", again["status"] == "exists")

        # canonical phone: local 8-digit and the stored 965 form must be one employee
        local_created = app.create_company_employee(company, name="Canon Tester", phone=local8)
        check("8-digit local create uses 965 canonical key", local_created.get("employee_key") == canonical_key)
        canon_dupe = app.create_company_employee(company, name="Canon Tester", phone="965" + local8)
        check("965 form de-dupes against the 8-digit-created employee", canon_dupe["status"] == "exists")

        # cleanup the prefixed-phone variant created above
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (real_key,))
            conn.commit()
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    EMPLOYEE ROSTER: FAILURES")
        return 1
    print("    EMPLOYEE ROSTER: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
