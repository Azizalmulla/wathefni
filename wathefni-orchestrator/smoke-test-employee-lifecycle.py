"""Smoke test: Employee lifecycle — edit core fields + mark as left / reactivate.

A company must be able to correct employee details and remove leavers from active
rosters WITHOUT deleting history. This pins the NEW surface for the batch:

  - edit: update_company_employee changes name/title/department/email/start/phone
    in place; the employee_key (history anchor) never changes; a phone collision
    with another employee is rejected as 'duplicate'.
  - PATCH endpoint: gated on settings.manage (a role without it is denied), audited
    as 'employee_updated', company-scoped (cross-company edit is not_found).
  - mark as left: status endpoint sets employment_status='left' (no row delete,
    child history preserved), audited as 'employee_marked_left'; the directory still
    returns the row (searchable) carrying employment_status so rosters can exclude it.
  - reactivate: status='active' flips it back, audited as 'employee_reactivated'.

All writes use synthetic employee_keys removed in a finally block; safe to re-run.

Run against a DB (staging): python3 smoke-test-employee-lifecycle.py
"""

from __future__ import annotations

import sys
import uuid
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
    print("    employee lifecycle — edit + mark as left + reactivate, RBAC + scope + audit")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # --- locate a company with a post-hire people module enabled ---------
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next(
        (c for c in candidates if any(app.company_has_module(c, m) for m in app.POSTHIRE_PEOPLE_MODULES)),
        None,
    )
    if not company:
        print("    (no company has a post-hire people module enabled — skipping)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    print(f"    using company {company}")

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-lifecycle",
            "actor_role": role,
            "hr_phone": "99900000066",
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    owner = ctx(["settings.manage", "onboarding.read", "attendance.read"])

    audits: list[dict] = []
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k})

    phone_a = "96599000061"
    phone_b = "96599000062"
    phone_c = "96599000063"
    key_a = f"{company}-{app.canonical_employee_phone(phone_a)}"
    key_b = f"{company}-{app.canonical_employee_phone(phone_b)}"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_records WHERE employee_key IN (%s,%s)", (key_a, key_b))
                cur.execute("DELETE FROM employees WHERE employee_key IN (%s,%s)", (key_a, key_b))
            conn.commit()

    cleanup()
    try:
        app.create_company_employee(company, name="Lifecycle Alpha", phone=phone_a, position_title="Cashier", department="Front")
        app.create_company_employee(company, name="Lifecycle Beta", phone=phone_b, position_title="Stock")
        # Seed a child history row so we can prove deactivation preserves history.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO attendance_records (attendance_id, company_code, employee_key, employee_phone, employee_name, attendance_date, status, metadata) "
                    "VALUES (%s,%s,%s,%s,'Lifecycle Alpha', now()::date, 'present', %s)",
                    (str(uuid.uuid4()), company, key_a, app.digits(phone_a), app.Json({})),
                )
            conn.commit()

        # --- edit core fields in place -----------------------------------
        edited = app.update_company_employee(company, key_a, fields={
            "name": "Lifecycle Alpha Renamed", "position_title": "Senior Cashier",
            "department": "Operations", "email": "alpha@example.com",
        })
        check("edit returns updated", edited.get("status") == "updated")
        card = edited.get("employee") or {}
        check("edit applies name/title/department/email", card.get("name") == "Lifecycle Alpha Renamed"
              and card.get("position_title") == "Senior Cashier" and card.get("department") == "Operations"
              and card.get("email") == "alpha@example.com")
        check("edit keeps the employee_key (history anchor) stable", card.get("employee_key") == key_a)

        # phone change updates the column, NOT the key
        phone_changed = app.update_company_employee(company, key_a, fields={"phone": phone_c})
        check("edit can change the phone column", phone_changed.get("status") == "updated"
              and (phone_changed.get("employee") or {}).get("phone") == app.canonical_employee_phone(phone_c))
        check("phone change does not move the employee_key", (phone_changed.get("employee") or {}).get("employee_key") == key_a)

        # duplicate phone => rejected
        dup = app.update_company_employee(company, key_a, fields={"phone": phone_b})
        check("editing to another employee's phone is rejected as duplicate", dup.get("status") == "duplicate")

        # empty name => failed
        bad = app.update_company_employee(company, key_a, fields={"name": "   "})
        check("blank name is rejected", bad.get("status") == "failed")

        # cross-company edit => not_found
        other = app.update_company_employee("ZZZOTHERCO", key_a, fields={"name": "Hijack"})
        check("cross-company edit is not_found (tenant scoped)", other.get("status") == "not_found")

        # --- PATCH endpoint: audit + RBAC --------------------------------
        audits.clear()
        resp = app.dashboard_posthire_update_employee(employee_key=key_a, request=app.DashboardEmployeeUpdate(position_title="Lead"), context=owner)
        check("PATCH endpoint returns ok", bool(resp.get("ok")))
        check("edit recorded an 'employee_updated' audit", any(a["action_type"] == "employee_updated" for a in audits))
        try:
            app.dashboard_posthire_update_employee(employee_key=key_a, request=app.DashboardEmployeeUpdate(position_title="X"), context=ctx(["attendance.read"], role="viewer"))
            check("role without settings.manage cannot edit", False)
        except app.HTTPException as exc:
            check("role without settings.manage cannot edit", exc.status_code in (401, 403))

        # --- mark as left: no delete, history preserved ------------------
        audits.clear()
        left = app.dashboard_posthire_set_employee_status(employee_key=key_a, request=app.DashboardEmployeeStatus(status="left"), context=owner)
        check("mark-as-left returns left", left.get("employment_status") == "left")
        check("mark-as-left recorded an 'employee_marked_left' audit", any(a["action_type"] == "employee_marked_left" for a in audits))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key_a,))
                row = cur.fetchone()
                cur.execute("SELECT count(*) AS n FROM attendance_records WHERE employee_key=%s", (key_a,))
                hist = dict(cur.fetchone())
        check("employee row is NOT deleted", row is not None and str(dict(row).get("employment_status")) == "left")
        check("child history is preserved after offboard", int(hist.get("n") or 0) >= 1)

        # directory still returns the left employee (searchable), carrying status
        directory = app.dashboard_posthire_employees(context=owner)
        mine = next((e for e in directory.get("employees", []) if e.get("employee_key") == key_a), None)
        check("directory still lists the left employee (searchable)", mine is not None)
        check("directory card exposes employment_status for roster exclusion", (mine or {}).get("employment_status") == "left")

        # RBAC on status endpoint
        try:
            app.dashboard_posthire_set_employee_status(employee_key=key_a, request=app.DashboardEmployeeStatus(status="left"), context=ctx(["attendance.read"], role="viewer"))
            check("role without settings.manage cannot mark as left", False)
        except app.HTTPException as exc:
            check("role without settings.manage cannot mark as left", exc.status_code in (401, 403))

        # --- reactivate --------------------------------------------------
        audits.clear()
        back = app.dashboard_posthire_set_employee_status(employee_key=key_a, request=app.DashboardEmployeeStatus(status="active"), context=owner)
        check("reactivate returns active", back.get("employment_status") == "active")
        check("reactivate recorded an 'employee_reactivated' audit", any(a["action_type"] == "employee_reactivated" for a in audits))

        # cross-company status change => not_found
        scoped = app.set_employee_employment_status("ZZZOTHERCO", key_a, "left")
        check("cross-company status change is not_found (tenant scoped)", scoped.get("status") == "not_found")
    finally:
        app.record_admin_audit = real_audit
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    EMPLOYEE LIFECYCLE: FAILURES")
        return 1
    print("    EMPLOYEE LIFECYCLE: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
