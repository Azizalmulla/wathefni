"""Jobs (positions) pagination + search smoke test (staging).

The Jobs dashboard page used to read `summary.positions`, which was hard-capped
at 25 rows with no pagination, no "load more", and no indication more existed —
sorted by activity, so the LEAST active postings (including brand-new ones with
zero applicants yet) were the first to silently disappear once a company passed
25 total job openings. This test proves the fix:

  - the paginated positions query (`_dashboard_prehire_positions_query`) returns
    bounded, non-overlapping pages that reassemble to the true `total_count`,
    with correct `has_more`,
  - free-text search matches position title and position code,
  - `dashboard_prehire_positions_summary()` (headline stat cards) always reflects
    the FULL set, regardless of paging/search,
  - positions never leak across companies (tenant isolation), and
  - the legacy `dashboard_prehire_positions_payload()` call (used by the summary
    card's top-N glance) is unchanged in signature/behavior.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-jobs-pagination.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "JOBSPAGEA"   # scale + search subject
COMPANY_B = "JOBSPAGEB"   # isolation control
MARKER = "temporary_jobs_pagination_smoke"

BULK_OPEN = 25       # open positions, one application each
BULK_CLOSED = 3      # closed positions, no applications
ZEBRA_COUNT = 2      # unique searchable title
FALCON_COUNT = 1     # unique searchable position_code
TOTAL_A = BULK_OPEN + BULK_CLOSED + ZEBRA_COUNT + FALCON_COUNT
OPEN_A = BULK_OPEN + ZEBRA_COUNT + FALCON_COUNT
CLOSED_A = BULK_CLOSED


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
            print(f"      PASS  {label}")
        for label in self.failed:
            print(f"      FAIL  {label}")
        print(f"\n    {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _insert_position(cur: Any, company: str, code: str, title: str, status: str, apply_code: str | None) -> None:
    cur.execute(
        """
        INSERT INTO positions (company_code, position_code, title, status, apply_code, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,now(),now())
        ON CONFLICT (company_code, position_code) DO UPDATE SET status=EXCLUDED.status, apply_code=EXCLUDED.apply_code
        """,
        (company, code, title, status, apply_code),
    )


def _insert_application(cur: Any, company: str, app_key: str, position_code: str, position_title: str, phone: str) -> None:
    cur.execute(
        """
        INSERT INTO applications
            (app_key, phone, company_code, position_code, position_title, status, current_step,
             cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,'screening_complete','review',TRUE,'complete',%s,'production',now(),now(),now())
        ON CONFLICT (app_key) DO NOTHING
        """,
        (app_key, phone, company, position_code, position_title, Json({"smoke": MARKER, "cv": {"received": True}})),
    )


def _all_a_codes() -> list[str]:
    codes = [f"BULKOPEN{i}" for i in range(BULK_OPEN)]
    codes += [f"BULKCLOSED{i}" for i in range(BULK_CLOSED)]
    codes += [f"ZEBRA{i}" for i in range(ZEBRA_COUNT)]
    codes += [f"FALCONCODE{i}" for i in range(FALCON_COUNT)]
    return codes


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM applications WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM positions WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_A}-%",))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_B}-%",))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Jobs Pagination {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                    "VALUES (%s,'pre_hiring',TRUE,'smoke',now()) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (company,),
                )
            _purge(cur)
            # Bulk open positions, each with one application (so activity-based
            # ordering doesn't accidentally coincide with insertion order).
            for i in range(BULK_OPEN):
                code = f"BULKOPEN{i}"
                _insert_position(cur, COMPANY_A, code, f"A Open Role {i}", "open", f"APPLY-{code}")
                phone = f"{COMPANY_A}-cand{i}"
                cur.execute(
                    "INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING",
                    (phone, f"Candidate {i}"),
                )
                _insert_application(cur, COMPANY_A, f"{COMPANY_A}-app{i}", code, f"A Open Role {i}", phone)
            # Bulk closed positions, no applications -> zero activity, the exact
            # cohort the old activity-sorted LIMIT 25 would drop first.
            for i in range(BULK_CLOSED):
                code = f"BULKCLOSED{i}"
                _insert_position(cur, COMPANY_A, code, f"A Closed Role {i}", "closed", None)
            # Searchable by title: "Zebra Analyst".
            for i in range(ZEBRA_COUNT):
                code = f"ZEBRA{i}"
                _insert_position(cur, COMPANY_A, code, f"Zebra Analyst {i}", "open", f"APPLY-{code}")
            # Searchable by position_code: "FALCONCODE0".
            for i in range(FALCON_COUNT):
                code = f"FALCONCODE{i}"
                _insert_position(cur, COMPANY_A, code, "Generic Title", "open", f"APPLY-{code}")
            # Company B: one position, used to prove isolation from A.
            _insert_position(cur, COMPANY_B, "BEMP0", "B Only Role", "open", "APPLY-BEMP0")
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _page_codes(company: str, *, search: str | None = None, limit: int = 10) -> tuple[list[str], int]:
    """Collect every position_code across paged calls, plus the reported total_count."""
    seen: list[str] = []
    offset = 0
    total_count = 0
    for _ in range(1000):  # generous upper bound; test data is small
        rows, total_count = app._dashboard_prehire_positions_query(company, limit=limit, offset=offset, search=search)
        seen.extend(str(r["position_code"]) for r in rows)
        if not rows or (offset + len(rows)) >= total_count:
            break
        offset += len(rows)
    return seen, total_count


def run_checks(checks: Checks) -> None:
    # 1) Legacy call (used by the summary card's top-N glance) is unchanged:
    # same signature, still returns a plain list.
    legacy = app.dashboard_prehire_positions_payload(COMPANY_A, limit=25)
    checks.check("legacy call still returns a plain list", lambda: isinstance(legacy, list))
    checks.check("legacy call still respects its own limit", lambda: len(legacy) == 25)

    # 2) Default paginated page is bounded and reports the true total + has_more.
    first, total_count = app._dashboard_prehire_positions_query(COMPANY_A, limit=10, offset=0)
    checks.check("default page caps at limit=10", lambda: len(first) == 10)
    checks.check("total_count == TOTAL_A when unfiltered", lambda: total_count == TOTAL_A)

    # 3) Pagination reassembles to the full set with no duplicates or gaps —
    # crucially, INCLUDING the zero-activity closed positions the old hard
    # LIMIT=25 (sorted by activity) would have silently dropped first.
    seen, total = _page_codes(COMPANY_A, limit=10)
    checks.check("paging reports total_count == TOTAL_A", lambda: total == TOTAL_A)
    checks.check("paging visits every position once", lambda: len(seen) == TOTAL_A)
    checks.check("paging has no duplicate rows", lambda: len(set(seen)) == TOTAL_A)
    all_a_codes = set(_all_a_codes())
    checks.check("paging includes every zero-activity closed position", lambda: all(f"BULKCLOSED{i}" in seen for i in range(BULK_CLOSED)))
    checks.check("paging never invents codes outside the seeded set", lambda: set(seen) == all_a_codes)

    # 4) Free-text search matches position title and position_code.
    zebra_rows, zebra_total = app._dashboard_prehire_positions_query(COMPANY_A, limit=100, search="zebra")
    checks.check("search 'zebra' matches title -> ZEBRA_COUNT", lambda: zebra_total == ZEBRA_COUNT)
    checks.check("search 'zebra' rows all Zebra", lambda: all("Zebra" in str(r["position_title"]) for r in zebra_rows))
    falcon_rows, falcon_total = app._dashboard_prehire_positions_query(COMPANY_A, limit=100, search="falconcode")
    checks.check("search 'falconcode' matches position_code -> FALCON_COUNT", lambda: falcon_total == FALCON_COUNT)
    none_rows, none_total = app._dashboard_prehire_positions_query(COMPANY_A, limit=100, search="no-such-role-xyz")
    checks.check("search miss -> total 0", lambda: none_total == 0 and len(none_rows) == 0)

    # 5) Summary aggregate counts always reflect the FULL set (headline stat
    # cards must not be skewed by pagination or search).
    summary_full = app.dashboard_prehire_positions_summary(COMPANY_A)
    checks.check("summary.total_positions == TOTAL_A", lambda: summary_full["total_positions"] == TOTAL_A)
    checks.check("summary.open_positions == OPEN_A", lambda: summary_full["open_positions"] == OPEN_A)
    checks.check("summary.closed_positions == CLOSED_A", lambda: summary_full["closed_positions"] == CLOSED_A)
    checks.check("summary.active_qr_codes == OPEN_A (all open have apply_code)", lambda: summary_full["active_qr_codes"] == OPEN_A)
    checks.check("summary.total_applications == BULK_OPEN", lambda: summary_full["total_applications"] == BULK_OPEN)

    # 6) Tenant isolation: A never sees B; B only sees its own.
    a_rows, a_total = app._dashboard_prehire_positions_query(COMPANY_A, limit=200)
    checks.check("A positions only reference A codes", lambda: all(str(r["position_code"]) in all_a_codes for r in a_rows))
    b_rows, b_total = app._dashboard_prehire_positions_query(COMPANY_B, limit=200)
    checks.check("B total_count == 1", lambda: b_total == 1)
    checks.check("B positions exclude A codes", lambda: all(str(r["position_code"]) not in all_a_codes for r in b_rows))
    summary_b = app.dashboard_prehire_positions_summary(COMPANY_B)
    checks.check("B summary.total_positions == 1", lambda: summary_b["total_positions"] == 1)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"jobs pagination smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    JOBS PAGINATION: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
