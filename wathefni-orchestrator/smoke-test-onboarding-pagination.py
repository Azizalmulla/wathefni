"""Smoke test: Onboarding directory pagination + server-side search.

The onboarding page shows employees who are STILL ONBOARDING. It used to build
that list from the (formerly 1000-capped) full employee read and split in Python.
Now it pages the in-progress set in SQL with an accurate total_count/has_more and
a scope- and search-aware query, while the headline counts (total / completed)
stay workforce-wide.

Pins: only in-progress employees appear (completed excluded), paging reaches the
whole in-progress set with no gaps/duplicates, summary counts are correct,
server-side search filters the in-progress set (and matches department in profile
JSON), and tenant isolation holds.

Seeds throwaway synthetic companies; removed in a finally block. Safe to re-run.

Run against a DB (staging): python3 smoke-test-onboarding-pagination.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

N_IN = 250    # in-progress employees (> one page of 100)
N_DONE = 60   # completed employees (must be excluded from the in-progress list)
DEPTS = 6


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    onboarding pagination — in-progress paged + searchable (SQL), completed excluded, scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    tag = f"SMOKEONB{uuid.uuid4().hex[:8].upper()}"
    comp_a = f"{tag}A"
    comp_b = f"{tag}B"
    in_states = ("not_started", "in_progress", "pending")

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key LIKE %s", (f"{tag}%",))
                cur.execute("DELETE FROM company_modules WHERE company_code IN (%s,%s)", (comp_a, comp_b))
            conn.commit()

    cleanup()
    in_keys = {f"{tag}-IP-{i:05d}" for i in range(N_IN)}
    done_keys = {f"{tag}-DN-{i:05d}" for i in range(N_DONE)}
    exp_newhire7 = sum(1 for i in range(N_IN) if "newhire 7" in f"newhire {i}".lower())
    exp_dept3 = sum(1 for i in range(N_IN) if i % DEPTS == 3)

    try:
        rows = []
        for i in range(N_IN):
            rows.append((
                f"{tag}-IP-{i:05d}", comp_a, f"Newhire {i}", f"9651100{i:05d}",
                app.Json({"department": f"Dept{i % DEPTS}"}), in_states[i % len(in_states)], "active",
            ))
        for i in range(N_DONE):
            rows.append((
                f"{tag}-DN-{i:05d}", comp_a, f"Done {i}", f"9652200{i:05d}",
                app.Json({"department": "DoneDept"}), "complete", "active",
            ))
        b_keys = {f"{tag}-B{j:02d}" for j in range(3)}
        for k in sorted(b_keys):
            rows.append((k, comp_b, f"Newhire other {k}", "96500099999", app.Json({}), "not_started", "active"))

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

        # 1) paged in-progress read ------------------------------------------
        page1 = app.list_onboarding_page(comp_a, limit=100, offset=0)
        check("page 1 returns the page size", len(page1["rows"]) == 100)
        check("page 1 total_count == in-progress count", page1["total_count"] == N_IN)
        check("page 1 flags has_more", page1["has_more"] is True)

        seen: set[str] = set()
        off = 0
        guard = 0
        while True:
            guard += 1
            if guard > 40:
                break
            pg = app.list_onboarding_page(comp_a, limit=100, offset=off)
            seen.update(str(r.get("employee_key")) for r in pg["rows"])
            if not pg["has_more"]:
                break
            off += 100
        check("paging reaches every in-progress employee", seen == in_keys)
        check("completed employees never appear in the in-progress list", not (seen & done_keys))
        check("other company never appears", not (seen & b_keys))

        # 2) summary counts stay workforce-wide ------------------------------
        counts = app.onboarding_directory_counts(comp_a)
        check("summary total == all seeded for comp_a", counts["total"] == N_IN + N_DONE)
        check("summary completed_count correct", counts["completed_count"] == N_DONE)
        check("summary in_progress_count correct", counts["in_progress_count"] == N_IN)

        # 3) server-side search over the in-progress set ---------------------
        s = app.list_onboarding_page(comp_a, search="Newhire 7", limit=200, offset=0)
        check("search filters in-progress by name", s["total_count"] == exp_newhire7)
        check("search rows all match the term", all("newhire 7" in str(r.get("name")).lower() for r in s["rows"]))
        d = app.list_onboarding_page(comp_a, search="Dept3", limit=300, offset=0)
        check("search matches department in profile JSON", d["total_count"] == exp_dept3)
        done_search = app.list_onboarding_page(comp_a, search="Done", limit=100, offset=0)
        check("search does not surface completed employees", done_search["total_count"] == 0)
        none_search = app.list_onboarding_page(comp_a, search="zzz-nobody", limit=100, offset=0)
        check("no-match search is empty", none_search["total_count"] == 0 and none_search["rows"] == [])

        # 4) endpoint wiring -------------------------------------------------
        ctx = {
            "company_code": comp_a,
            "permissions": ["onboarding.read"],
            "access": {"role": "owner", "permissions": ["onboarding.read"]},
            "actor_user_id": "smoke-onb-page",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-onb-page",
            "permission_subject_company": comp_a,
            "actor_role": "owner",
            "hr_phone": "99900000079",
            "hr_user": {"role": "owner", "status": "active", "company_code": comp_a},
        }
        ep = app.dashboard_posthire_onboarding(offset=0, limit=100, context=ctx)
        check("endpoint returns a first page of 100", len(ep.get("in_progress") or []) == 100)
        check("endpoint exposes total_count", ep.get("total_count") == N_IN)
        check("endpoint flags has_more", ep.get("has_more") is True)
        check("endpoint completed_count workforce-wide", ep.get("completed_count") == N_DONE)
        check("endpoint total workforce-wide", ep.get("total") == N_IN + N_DONE)
        ep_search = app.dashboard_posthire_onboarding(offset=0, limit=100, search="Newhire 7", context=ctx)
        check("endpoint search filters in-progress", ep_search.get("total_count") == exp_newhire7)
        check("endpoint search keeps completed_count workforce-wide", ep_search.get("completed_count") == N_DONE)
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    ONBOARDING PAGINATION: FAILURES")
        return 1
    print("    ONBOARDING PAGINATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
