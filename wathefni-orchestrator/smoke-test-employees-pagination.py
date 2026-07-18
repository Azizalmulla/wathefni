"""Smoke test: Employees directory pagination + uncapped employee hub.

Pins two things that used to silently lose data past a hardcoded LIMIT 1000:

  1. company_employees() (the shared hub used by "message all staff",
     onboarding cards, analytics roll-ups) is now UNCAPPED — a company with
     >1000 people returns all of them, not the first 1000.

  2. The dashboard directory (/dashboard/posthire/employees) pages via
     limit/offset with an accurate total_count/has_more, and the stat-card
     counts (active / left / onboarding / departments) are computed in SQL over
     the WHOLE workforce so they stay correct no matter how many pages are
     loaded in the UI.

Also pins: stable paging (no gaps/duplicates across pages) and tenant isolation.

Everything is seeded into throwaway synthetic companies and removed in a finally
block, so this is safe to re-run. Seeds 1200 rows via one batched insert.

Run against a DB (staging): python3 smoke-test-employees-pagination.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

N = 1200          # > the old 1000 cap so truncation would show
LEFT = 50         # first LEFT rows are employment_status='left'
DEPTS = 8         # distinct departments among active rows


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    employees pagination — hub uncapped + directory paged (stats in SQL), stable + tenant-scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    tag = f"SMOKEEMP{uuid.uuid4().hex[:8].upper()}"
    comp_a = f"{tag}A"
    comp_b = f"{tag}B"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key LIKE %s", (f"{tag}%",))
                cur.execute("DELETE FROM company_modules WHERE company_code IN (%s,%s)", (comp_a, comp_b))
            conn.commit()

    # Expected stats for comp_a (see seeding below).
    exp_active = N - LEFT
    exp_left = LEFT
    exp_complete = sum(1 for i in range(N) if i >= LEFT and i % 5 == 0)
    exp_onboarding = exp_active - exp_complete
    exp_depts = DEPTS

    cleanup()
    try:
        # --- seed 1200 employees for comp_a in one batched insert -----------
        # `department` is not a column — it lives in the profile JSON, matching how
        # real employees store it (posthire_employee_card reads profile.department).
        rows = []
        for i in range(N):
            key = f"{tag}-{i:05d}"
            if i < LEFT:
                rows.append((key, comp_a, f"Emp {i}", f"9650000{i:05d}", app.Json({}), "not_started", "left"))
            else:
                dept = f"Dept{i % DEPTS}"
                status = "complete" if i % 5 == 0 else "not_started"
                rows.append((key, comp_a, f"Emp {i}", f"9650000{i:05d}", app.Json({"department": dept}), status, "active"))
        # A few in comp_b to prove isolation.
        b_keys = {f"{tag}-B{j:02d}" for j in range(3)}
        for k in sorted(b_keys):
            rows.append((k, comp_b, f"Other {k}", "96500099999", app.Json({"department": "OtherDept"}), "not_started", "active"))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO employees
                      (employee_key, company_code, name, phone, profile, onboarding_status, employment_status, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s, now())
                    ON CONFLICT (employee_key) DO NOTHING
                    """,
                    rows,
                )
                # Enable a people module so the dashboard endpoint is reachable.
                for comp in (comp_a, comp_b):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                        VALUES (%s,'onboarding',true,'smoke','{}'::jsonb, now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
                        """,
                        (comp,),
                    )
            conn.commit()

        seeded_keys = {f"{tag}-{i:05d}" for i in range(N)}

        # 1) hub is uncapped -------------------------------------------------
        hub = app.company_employees(comp_a)
        hub_keys = {str(r.get("employee_key")) for r in hub}
        check("company_employees returns ALL seeded rows (no silent 1000 cap)", len(hub) == N)
        check("company_employees includes rows beyond the old 1000 cap", f"{tag}-01100" in hub_keys and f"{tag}-01199" in hub_keys)

        # 2) list_employees_page pages the directory -------------------------
        page1 = app.list_employees_page(comp_a, limit=100, offset=0)
        check("page 1 returns exactly the page size", len(page1["rows"]) == 100)
        check("page 1 reports the true total_count", page1["total_count"] == N)
        check("page 1 flags has_more", page1["has_more"] is True)

        collected: list[str] = []
        offset = 0
        guard = 0
        while True:
            guard += 1
            if guard > 40:
                break
            page = app.list_employees_page(comp_a, limit=100, offset=offset)
            collected.extend(str(r.get("employee_key")) for r in page["rows"])
            if not page["has_more"]:
                break
            offset += 100
        check("paging reaches every seeded employee", set(collected) == seeded_keys)
        check("paging returns no duplicate rows", len(collected) == len(set(collected)))
        check("other company's employees never appear when paging comp_a", not (b_keys & set(collected)))

        # 3) SQL stat cards are correct over the WHOLE workforce -------------
        stats = app.employee_directory_stats(comp_a)
        check("stats total_count correct", stats["total_count"] == N)
        check("stats active_count correct", stats["active_count"] == exp_active)
        check("stats left_count correct", stats["left_count"] == exp_left)
        check("stats onboarding_count correct", stats["onboarding_count"] == exp_onboarding)
        check("stats department_count correct", stats["department_count"] == exp_depts)

        # 4) dashboard endpoint wiring (limit/offset + exposed pagination) ---
        ctx = {
            "company_code": comp_a,
            "permissions": ["employees.read", "onboarding.read"],
            "access": {"role": "owner", "permissions": ["employees.read", "onboarding.read"]},
            "actor_user_id": "smoke-emp-page",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-emp-page",
            "permission_subject_company": comp_a,
            "actor_role": "owner",
            "hr_phone": "99900000078",
            "hr_user": {"role": "owner", "status": "active", "company_code": comp_a},
        }
        first = app.dashboard_posthire_employees(offset=0, limit=100, context=ctx)
        check("endpoint returns a first page of 100", len(first.get("employees") or []) == 100)
        check("endpoint exposes total_count", first.get("total_count") == N)
        check("endpoint flags has_more on page 1", first.get("has_more") is True)
        check("endpoint surfaces SQL active_count", first.get("active_count") == exp_active)
        check("endpoint surfaces SQL onboarding_count", first.get("onboarding_count") == exp_onboarding)
        last = app.dashboard_posthire_employees(offset=N - 100, limit=100, context=ctx)
        check("endpoint deep page returns the tail", len(last.get("employees") or []) == 100)
        check("endpoint deep page clears has_more", last.get("has_more") is False)

        # 5) server-side search reaches the WHOLE workforce ------------------
        # "Emp 7" matches Emp 7, 70-79, 700-799, 7xx... — a spread across pages.
        # Prove list_employees_page filters in SQL and total_count reflects it.
        expected_emp7 = sum(1 for i in range(N) if "emp 7" in f"emp {i}".lower())
        s_page = app.list_employees_page(comp_a, search="Emp 7", limit=100, offset=0)
        check("search reports a filtered total_count", s_page["total_count"] == expected_emp7)
        check("search matches only rows containing the term", all("emp 7" in str(r.get("name")).lower() for r in s_page["rows"]))
        # Page the search result and confirm we reach exactly the matched set.
        s_keys: set[str] = set()
        s_off = 0
        s_guard = 0
        while True:
            s_guard += 1
            if s_guard > 40:
                break
            pg = app.list_employees_page(comp_a, search="Emp 7", limit=100, offset=s_off)
            s_keys.update(str(r.get("employee_key")) for r in pg["rows"])
            if not pg["has_more"]:
                break
            s_off += 100
        check("search result pages to exactly the matched count", len(s_keys) == expected_emp7)

        # Search by department (stored in profile JSON) works too.
        dept_page = app.list_employees_page(comp_a, search="Dept3", limit=100, offset=0)
        check("search matches department in profile JSON", dept_page["total_count"] > 0 and dept_page["total_count"] == sum(1 for i in range(N) if i >= LEFT and i % DEPTS == 3))

        # A term that matches nobody returns an empty, honest result.
        none_page = app.list_employees_page(comp_a, search="zzz-no-such-person", limit=100, offset=0)
        check("no-match search returns empty with zero total", none_page["total_count"] == 0 and none_page["rows"] == [])

        # Wildcards are treated literally (not as SQL wildcards).
        pct_page = app.list_employees_page(comp_a, search="%", limit=100, offset=0)
        check("literal '%' does not match everything", pct_page["total_count"] == 0)

        # Search stays tenant-scoped: comp_b rows never leak into comp_a search.
        b_search = app.list_employees_page(comp_a, search="Other", limit=100, offset=0)
        check("search does not cross company boundaries", b_search["total_count"] == 0)

        # Endpoint surfaces search too; stats stay workforce-wide (not filtered).
        ep = app.dashboard_posthire_employees(search="Emp 7", limit=100, offset=0, context=ctx)
        check("endpoint search filters rows", ep.get("total_count") == expected_emp7)
        check("endpoint stats stay workforce-wide during search", ep.get("active_count") == exp_active)
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    EMPLOYEES PAGINATION: FAILURES")
        return 1
    print("    EMPLOYEES PAGINATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
