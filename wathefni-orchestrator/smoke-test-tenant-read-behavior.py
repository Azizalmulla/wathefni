"""Live behaviour test for tenant read hardening.

Creates two temporary companies with the same candidate name and verifies that
AI/WhatsApp resolution helpers only ever read within the active company and fail
closed when no company scope is set. Cleans up all temporary rows on exit.

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-tenant-read-behavior.py
"""

from __future__ import annotations

import app
from psycopg2.extras import Json

COMPANY_A = "TENANTREADTESTA"
COMPANY_B = "TENANTREADTESTB"
PHONE_A = "96550000000901"
PHONE_B = "96550000000902"
APP_A = f"{PHONE_A}-{COMPANY_A}-WELDER"
APP_B = f"{PHONE_B}-{COMPANY_B}-DIVER"
SHARED_NAME = "Zaynab Tenantread"
MARKER = "temporary_tenant_read_behavior_smoke"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Tenant Read Smoke {company}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            for phone in (PHONE_A, PHONE_B):
                cur.execute(
                    "INSERT INTO candidates (phone, name, email, raw_json) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name",
                    (phone, SHARED_NAME, f"{phone}@example.com", Json({"smoke": MARKER})),
                )
            cur.execute(
                "INSERT INTO positions (company_code, position_code, title, status, updated_at) "
                "VALUES (%s,'WELDER','Tenantread Welder','open',now()) "
                "ON CONFLICT (company_code, position_code) DO UPDATE SET title=EXCLUDED.title, status='open'",
                (COMPANY_A,),
            )
            cur.execute(
                "INSERT INTO positions (company_code, position_code, title, status, updated_at) "
                "VALUES (%s,'DIVER','Tenantread Diver','open',now()) "
                "ON CONFLICT (company_code, position_code) DO UPDATE SET title=EXCLUDED.title, status='open'",
                (COMPANY_B,),
            )
            cur.execute(
                "INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, raw_json, data_source, data_source_detail, created_at, updated_at) "
                "VALUES (%s,%s,%s,'WELDER','Tenantread Welder','screening_complete','screening','complete',%s,'production',%s,CURRENT_DATE,CURRENT_DATE) "
                "ON CONFLICT (app_key) DO UPDATE SET company_code=EXCLUDED.company_code",
                (APP_A, PHONE_A, COMPANY_A, Json({"smoke": MARKER, "candidate_name": SHARED_NAME}), MARKER),
            )
            cur.execute(
                "INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, raw_json, data_source, data_source_detail, created_at, updated_at) "
                "VALUES (%s,%s,%s,'DIVER','Tenantread Diver','screening_complete','screening','complete',%s,'production',%s,CURRENT_DATE,CURRENT_DATE) "
                "ON CONFLICT (app_key) DO UPDATE SET company_code=EXCLUDED.company_code",
                (APP_B, PHONE_B, COMPANY_B, Json({"smoke": MARKER, "candidate_name": SHARED_NAME}), MARKER),
            )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", ([APP_A, APP_B],))
            cur.execute("DELETE FROM positions WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", ([PHONE_A, PHONE_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def run_checks() -> None:
    # 1. Company A active: application name match returns only A's record.
    token = app.set_active_company_code(COMPANY_A)
    try:
        match = app.application_mentioned_in_text(f"what about {SHARED_NAME}")
        assert_true(match is not None, "same-company application lookup should resolve")
        assert_true(match.get("company_code") == COMPANY_A, "application match must belong to active company A")
        assert_true(match.get("app_key") == APP_A, "application match must be company A's application")

        # 2. Position inference is company-scoped: A sees welder, never B's diver.
        assert_true(app.infer_position_filter_from_text("welder role") == "WELDER", "company A must infer its own position")
        assert_true(app.infer_position_filter_from_text("diver role") is None, "company A must not infer company B position")

        # 3. Candidate fuzzy lookup only returns A's candidate phone.
        fuzzy = app._fuzzy_candidate_phones_by_name("Zaynab Tenantread", threshold=0.2, limit=10)
        phones = {row.get("phone") for row in fuzzy}
        assert_true(PHONE_A in phones, "fuzzy candidate lookup should find company A candidate")
        assert_true(PHONE_B not in phones, "fuzzy candidate lookup must not leak company B candidate")
    finally:
        app.reset_active_company_code(token)

    # 4. Company B active: position inference flips, and A's welder is invisible.
    token = app.set_active_company_code(COMPANY_B)
    try:
        assert_true(app.infer_position_filter_from_text("diver role") == "DIVER", "company B must infer its own position")
        assert_true(app.infer_position_filter_from_text("welder role") is None, "company B must not infer company A position")
        match_b = app.application_mentioned_in_text(f"what about {SHARED_NAME}")
        assert_true(match_b is not None and match_b.get("company_code") == COMPANY_B, "company B must resolve its own application")
    finally:
        app.reset_active_company_code(token)

    # 5. Explicit company_code argument also scopes correctly and cross-company is blocked.
    assert_true(app.find_application_by_candidate_name(SHARED_NAME, COMPANY_A).get("company_code") == COMPANY_A, "explicit company A scope works")
    assert_true(app.find_application_by_candidate_name(SHARED_NAME, COMPANY_B).get("company_code") == COMPANY_B, "explicit company B scope works")

    # 6. Fail closed: no active company and no explicit company -> no global search.
    assert_true(app.active_company_code() is None, "no active company should be set here")
    assert_true(app.application_mentioned_in_text(f"what about {SHARED_NAME}") is None, "must fail closed without company scope")
    assert_true(app.infer_position_filter_from_text("welder role") is None, "position inference must fail closed without company scope")
    assert_true(app._fuzzy_candidate_phones_by_name("Zaynab Tenantread", threshold=0.2, limit=10) == [], "fuzzy lookup must fail closed without company scope")
    assert_true(app.candidate_matches_from_text(SHARED_NAME) == [], "candidate matches must fail closed without company scope")
    assert_true(app.find_application_by_candidate_name(SHARED_NAME) is None, "application-by-name must fail closed without company scope")

    # 7. ensure_schema remains idempotent under force.
    app.ensure_schema(force=True)
    app.ensure_schema(force=True)


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("tenant read behaviour smoke tests passed")


if __name__ == "__main__":
    main()
