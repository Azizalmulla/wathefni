"""Assessments pagination + true-count smoke test (staging).

The Assessments dashboard page (`dashboard_assessments_payload` /
`/dashboard/prehire/assessments`) used to have a hard `LIMIT 100` with no
offset, and worse than most other truncation bugs we've fixed: it also
computed `total`, `status_counts` (the "In progress" / "Completed" headline
numbers), and `average_percent` (the "Average score" headline number) by
counting/averaging over that same truncated page in Python — instead of
real company-wide aggregate queries. So once a company passed the page size,
the headline metrics on the page silently went wrong, not just the list.

This test proves the fix:
  - `dashboard_assessments_payload()` now supports `offset`, and paging
    through it reassembles the full, non-overlapping set of attempts,
  - `total` and `status_counts` reflect ALL matching attempts company-wide,
    regardless of which page is requested,
  - `average_percent` is the true average across ALL completed attempts,
    not just whichever ones happen to land on the requested page,
  - the new `assessment_status=awaiting` filter on
    `prehire_applications_query()` returns exactly the same cohort/count as
    `prehire_action_counts()["assessment_pending"]` (the number HR sees on
    the Assessments page headline card and the Overview page), so "Open all
    in Candidates" actually lands on the full, matching set, and
  - attempts never leak across companies (tenant isolation).

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-assessments-pagination.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "ASSESSPAGEA"  # scale subject
COMPANY_B = "ASSESSPAGEB"  # isolation control
MARKER = "temporary_assessments_pagination_smoke"

COMPLETED_COUNT = 60      # completed attempts with scores -> forces >1 page
PENDING_ATTEMPT_COUNT = 4  # attempt row exists with status='pending'
NO_ATTEMPT_COUNT = 3      # reviewable app, no attempt row at all
OUT_OF_STAGE_PENDING = 2  # pending-eligible stage-wise but NOT a reviewable stage
AWAITING_TOTAL_A = PENDING_ATTEMPT_COUNT + NO_ATTEMPT_COUNT


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


def _insert_application(cur: Any, company: str, app_key: str, phone: str, status: str) -> None:
    cur.execute(
        """
        INSERT INTO applications
            (app_key, phone, company_code, position_code, position_title, status, current_step,
             cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
        VALUES (%s,%s,%s,'ROLE1','Test Role',%s,'review',TRUE,'complete',%s,'production',now(),now(),now())
        ON CONFLICT (app_key) DO NOTHING
        """,
        (app_key, phone, company, status, Json({"smoke": MARKER, "cv": {"received": True}})),
    )


def _insert_attempt(cur: Any, company: str, app_key: str, phone: str, status: str, *, percent: float | None = None) -> None:
    completed_at_sql = "now()" if status == "completed" else "NULL"
    cur.execute(
        f"""
        INSERT INTO assessment_attempts
            (company_code, app_key, phone, battery_key, status, total_items, started_at, completed_at, created_at, updated_at)
        VALUES (%s,%s,%s,'general',%s,22,now(),{completed_at_sql},now(),now())
        RETURNING attempt_id
        """,
        (company, app_key, phone, status),
    )
    attempt_id = cur.fetchone()["attempt_id"]
    if percent is not None:
        cur.execute(
            """
            INSERT INTO assessment_scores (attempt_id, raw_score, max_score, percent, band, norm_version)
            VALUES (%s,%s,22,%s,'meets_bar','v1')
            """,
            (attempt_id, percent * 22 / 100.0, percent),
        )


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute(
        "DELETE FROM assessment_scores WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
        (companies,),
    )
    cur.execute("DELETE FROM assessment_attempts WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM applications WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_A}-%",))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_B}-%",))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> list[float]:
    completed_percents: list[float] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Assessments Pagination {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                for module in ("pre_hiring", "assessments"):
                    cur.execute(
                        "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                        "VALUES (%s,%s,TRUE,'smoke',now()) "
                        "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                        (company, module),
                    )
            _purge(cur)

            # Completed attempts with varied scores, spread so page 1 (most
            # recently updated) does NOT average out to the same value as the
            # full set -- otherwise a truncation bug would go unnoticed.
            for i in range(COMPLETED_COUNT):
                phone = f"{COMPANY_A}-completed{i}"
                app_key = f"{COMPANY_A}-app-completed{i}"
                cur.execute("INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING", (phone, f"Completed {i}"))
                _insert_application(cur, COMPANY_A, app_key, phone, "shortlisted")
                percent = 30.0 if i < 20 else 90.0  # first 20 (by insertion) score low, rest score high
                _insert_attempt(cur, COMPANY_A, app_key, phone, "completed", percent=percent)
                completed_percents.append(percent)

            # Pending attempts (attempt row exists, status='pending'), reviewable
            # stage -> counted in "assessment_pending" / "awaiting" bucket.
            for i in range(PENDING_ATTEMPT_COUNT):
                phone = f"{COMPANY_A}-pending{i}"
                app_key = f"{COMPANY_A}-app-pending{i}"
                cur.execute("INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING", (phone, f"Pending {i}"))
                _insert_application(cur, COMPANY_A, app_key, phone, "review_pending")
                _insert_attempt(cur, COMPANY_A, app_key, phone, "pending")

            # No assessment attempt at all, reviewable stage -> also counted in
            # "assessment_pending" / "awaiting" (COALESCE(...,'') = '').
            for i in range(NO_ATTEMPT_COUNT):
                phone = f"{COMPANY_A}-none{i}"
                app_key = f"{COMPANY_A}-app-none{i}"
                cur.execute("INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING", (phone, f"NoAttempt {i}"))
                _insert_application(cur, COMPANY_A, app_key, phone, "screening_complete")

            # No assessment attempt, but NOT a reviewable stage (e.g. still
            # mid-screening) -> must be EXCLUDED from "awaiting"/pending counts.
            for i in range(OUT_OF_STAGE_PENDING):
                phone = f"{COMPANY_A}-early{i}"
                app_key = f"{COMPANY_A}-app-early{i}"
                cur.execute("INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING", (phone, f"Early {i}"))
                _insert_application(cur, COMPANY_A, app_key, phone, "applied")

            # Company B: one completed attempt, used to prove isolation from A.
            phone_b = f"{COMPANY_B}-only"
            cur.execute("INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING", (phone_b, "B Only"))
            _insert_application(cur, COMPANY_B, f"{COMPANY_B}-app-only", phone_b, "shortlisted")
            _insert_attempt(cur, COMPANY_B, f"{COMPANY_B}-app-only", phone_b, "completed", percent=50.0)
        conn.commit()
    return completed_percents


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _page_attempt_ids(company: str, *, limit: int) -> tuple[list[str], int]:
    seen: list[str] = []
    offset = 0
    total = 0
    for _ in range(1000):
        payload = app.dashboard_assessments_payload(company, limit=limit, offset=offset)
        total = payload["total"]
        rows = payload["attempts"]
        seen.extend(str(a["attempt_id"]) for a in rows)
        if not rows or (offset + len(rows)) >= total:
            break
        offset += len(rows)
    return seen, total


def run_checks(checks: Checks, completed_percents: list[float]) -> None:
    total_attempts_a = COMPLETED_COUNT + PENDING_ATTEMPT_COUNT

    # 1) A single page is bounded, and the reported total is the TRUE
    # company-wide total, not len(attempts) of the truncated page.
    page1 = app.dashboard_assessments_payload(COMPANY_A, limit=20, offset=0)
    checks.check("page 1 caps at limit=20", lambda: len(page1["attempts"]) == 20)
    checks.check("total == full company-wide attempt count (not page size)", lambda: page1["total"] == total_attempts_a)
    checks.check("total != len(attempts) on a truncated page (proves the old bug is gone)", lambda: page1["total"] != len(page1["attempts"]))

    # 2) Paging reassembles to the full set with no duplicates or gaps.
    seen, total = _page_attempt_ids(COMPANY_A, limit=17)
    checks.check("paging reports total == full attempt count", lambda: total == total_attempts_a)
    checks.check("paging visits every attempt once", lambda: len(seen) == total_attempts_a)
    checks.check("paging has no duplicate rows", lambda: len(set(seen)) == total_attempts_a)

    # 3) status_counts reflect the FULL set regardless of the requested page.
    small_page = app.dashboard_assessments_payload(COMPANY_A, limit=5, offset=0)
    status_map = {row["status"]: row["count"] for row in small_page["status_counts"]}
    checks.check("status_counts unaffected by small page size (completed)", lambda: status_map.get("completed") == COMPLETED_COUNT)
    checks.check("status_counts unaffected by small page size (pending)", lambda: status_map.get("pending") == PENDING_ATTEMPT_COUNT)
    big_page_status = {row["status"]: row["count"] for row in page1["status_counts"]}
    checks.check("status_counts identical across different page sizes", lambda: big_page_status == status_map)

    # 4) average_percent is the TRUE average across ALL completed attempts,
    # not just whichever land on the requested page (first 20 are all 30.0,
    # so an average computed only from page 1 would wrongly read 30.0).
    true_average = round(sum(completed_percents) / len(completed_percents), 1)
    checks.check("average_percent == true company-wide average", lambda: page1["average_percent"] == true_average)
    checks.check("average_percent is not just page 1's average (30.0)", lambda: page1["average_percent"] != 30.0)

    # 5) The new assessment_status="awaiting" filter matches the exact
    # "assessment_pending" headline definition used by prehire_action_counts.
    action_counts = app.prehire_action_counts(COMPANY_A)
    checks.check("action_counts.assessment_pending == expected", lambda: action_counts["assessment_pending"] == AWAITING_TOTAL_A)
    awaiting = app.prehire_applications_query(company_code=COMPANY_A, status=None, position=None, search=None, limit=100, offset=0, assessment_status="awaiting")
    checks.check("awaiting filter total matches action_counts.assessment_pending", lambda: awaiting["total"] == action_counts["assessment_pending"])
    checks.check("awaiting filter excludes out-of-stage pending applicants", lambda: awaiting["total"] == AWAITING_TOTAL_A)

    # 6) Tenant isolation: A never sees B's attempts.
    payload_b = app.dashboard_assessments_payload(COMPANY_B, limit=50, offset=0)
    checks.check("B total == 1", lambda: payload_b["total"] == 1)
    a_ids = {str(a["attempt_id"]) for a in app.dashboard_assessments_payload(COMPANY_A, limit=200, offset=0)["attempts"]}
    b_ids = {str(a["attempt_id"]) for a in payload_b["attempts"]}
    checks.check("A and B attempts never overlap", lambda: a_ids.isdisjoint(b_ids))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"assessments pagination smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup_result = setup()
    checks = Checks()
    try:
        run_checks(checks, setup_result)
    finally:
        teardown()
    code = checks.report()
    print("    ASSESSMENTS PAGINATION: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
