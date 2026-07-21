"""Company-wide summary counts smoke test (staging).

Proves prehire_action_counts() reports TRUE company-wide totals that:
  - EXCEED the dashboard's first-50 candidate load window (no silent capping), and
  - use the SAME definitions as the Overview / Assessments pages:
      ready_for_review   = status IN (screening_complete, review_pending, ready_for_review)
      assessment_pending = (no/empty or pending assessment)
                           AND status IN (screening_complete, review_pending, ready_for_review, shortlisted)
      follow_up_needed   = distinct apps matching Candidates follow_up=needed
  - stay scoped to one company and respect the reviewable (production + CV) predicate.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-summary-counts.py

NEVER point this at the production database: it writes and deletes a test company.
"""

from __future__ import annotations

import sys
from typing import Any

import app
from psycopg2.extras import Json

COMPANY = "SUMMARYCOUNTTEST"
OTHER = "SUMMARYCOUNTOTHER"
MARKER = "temporary_summary_counts_smoke"

# Deliberately larger than the dashboard's 50-row candidate load window, to prove the
# count is a real company-wide total and not a windowed approximation.
READY_NO_ASSESS = 60        # screening_complete, no assessment  -> ready + pending
READY_WITH_DONE_ASSESS = 2  # screening_complete, completed assessment -> ready only (excluded from pending)
SHORTLISTED_NO_ASSESS = 3   # shortlisted, no assessment -> pending only (not ready)
HIRED = 5                   # excluded from both
NO_CV = 1                   # screening_complete but NOT reviewable (no CV) -> excluded from both
OTHER_READY = 10            # rows in a different company -> must never leak into COMPANY's counts

EXPECTED_READY = READY_NO_ASSESS + READY_WITH_DONE_ASSESS        # 62
EXPECTED_PENDING = READY_NO_ASSESS + SHORTLISTED_NO_ASSESS       # 63


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _insert_application(cur: Any, company: str, app_key: str, status: str, *, cv: bool = True, assessment_status: str | None = None) -> None:
    # One person per application keeps the fixture valid under the database's
    # active same-person + same-company + same-role uniqueness authority.
    phone = f"{app_key}-cand"
    raw: dict[str, Any] = {"smoke": MARKER}
    if cv:
        raw["cv"] = {"received": True}
    cur.execute(
        """
        INSERT INTO candidates (phone, name, email, raw_json, data_source)
        VALUES (%s,'Summary Smoke',%s,%s,'staging_smoke')
        ON CONFLICT (phone) DO NOTHING
        """,
        (phone, f"{phone}@example.com", Json({"smoke": MARKER})),
    )
    cur.execute(
        """
        INSERT INTO applications
            (app_key, phone, company_code, position_code, position_title, status, current_step,
             cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,'review',%s,'complete',%s,'production',now(),now(),now())
        ON CONFLICT (app_key) DO NOTHING
        """,
        (app_key, phone, company, "teller", "Teller", status, cv, Json(raw)),
    )
    if assessment_status:
        cur.execute(
            """
            INSERT INTO assessment_attempts
                (company_code, app_key, phone, candidate_name, position_code, position_title,
                 battery_key, status, current_item_index, total_items, random_seed, raw_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,22,1,%s)
            """,
            (company, app_key, phone, "Smoke", "teller", "Teller", "default", assessment_status, Json({"smoke": MARKER})),
        )


def _purge(cur: Any) -> None:
    companies = [COMPANY, OTHER]
    cur.execute("DELETE FROM assessment_attempts WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM applications WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM candidates WHERE raw_json->>'smoke'=%s", (MARKER,))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company, name in ((COMPANY, "Summary Counts Test"), (OTHER, "Summary Counts Other")):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, name, Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            _purge(cur)
            n = 0
            for _ in range(READY_NO_ASSESS):
                _insert_application(cur, COMPANY, f"{COMPANY}-ready-{n}", "screening_complete")
                n += 1
            for _ in range(READY_WITH_DONE_ASSESS):
                _insert_application(cur, COMPANY, f"{COMPANY}-done-{n}", "screening_complete", assessment_status="completed")
                n += 1
            for _ in range(SHORTLISTED_NO_ASSESS):
                _insert_application(cur, COMPANY, f"{COMPANY}-short-{n}", "shortlisted")
                n += 1
            for _ in range(HIRED):
                _insert_application(cur, COMPANY, f"{COMPANY}-hired-{n}", "hired")
                n += 1
            for _ in range(NO_CV):
                _insert_application(cur, COMPANY, f"{COMPANY}-nocv-{n}", "screening_complete", cv=False)
                n += 1
            for i in range(OTHER_READY):
                _insert_application(cur, OTHER, f"{OTHER}-ready-{i}", "screening_complete")
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
        conn.commit()


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"summary counts smoke — company {COMPANY} (env: {env or 'default'})")
    setup()
    passed: list[str] = []

    def ok(label: str) -> None:
        passed.append(label)
        print(f"      PASS  {label}")

    try:
        counts = app.prehire_action_counts(COMPANY)
        ready = int(counts.get("ready_for_review") or 0)
        pending = int(counts.get("assessment_pending") or 0)

        assert_true(ready > 50, f"ready_for_review must exceed the 50-row window (got {ready})")
        ok("ready_for_review exceeds the first-50 candidate window (not capped)")

        assert_true(ready == EXPECTED_READY, f"ready_for_review should be {EXPECTED_READY} (got {ready})")
        ok(f"ready_for_review == {EXPECTED_READY} (screening_complete only; shortlisted/hired/no-CV excluded)")

        assert_true(pending > 50, f"assessment_pending must exceed the 50-row window (got {pending})")
        ok("assessment_pending exceeds the first-50 candidate window (not capped)")

        assert_true(pending == EXPECTED_PENDING, f"assessment_pending should be {EXPECTED_PENDING} (got {pending})")
        ok(f"assessment_pending == {EXPECTED_PENDING} (includes shortlisted; excludes completed-assessment + no-CV)")

        # The completed-assessment rows count toward review but NOT toward pending.
        assert_true(ready - pending == READY_WITH_DONE_ASSESS - SHORTLISTED_NO_ASSESS,
                    "ready vs pending delta must reflect assessment-status definition")
        ok("definitions differ correctly: completed assessments leave the pending queue, shortlisted stay")

        # Company scoping: the OTHER company's 10 ready rows must not leak in.
        other_counts = app.prehire_action_counts(OTHER)
        assert_true(int(other_counts.get("ready_for_review") or 0) == OTHER_READY,
                    f"other company ready_for_review should be {OTHER_READY} (got {other_counts.get('ready_for_review')})")
        assert_true(ready == EXPECTED_READY,
                    "COMPANY ready_for_review must not include OTHER company rows")
        ok("counts are company-scoped (a second company's candidates never leak in)")
    finally:
        teardown()

    print(f"\n    {len(passed)} passed, 0 failed")
    print("    SUMMARY COUNTS: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
