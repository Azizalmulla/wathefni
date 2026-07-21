#!/usr/bin/env python3
"""Staging smoke: Jobs Phase 1 lifecycle, authority, vacancies, intake gate."""

from __future__ import annotations

import os
import sys
import time
import uuid

# Ensure orchestrator imports resolve when run from ops or repo root.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import prehire_jobs as jobs


def _ok(label: str) -> None:
    print(f"OK  {label}")


def _fail(label: str, detail: str = "") -> None:
    print(f"FAIL {label}: {detail}")
    raise SystemExit(1)


def main() -> None:
    # Import app after path setup so db_connect / schema helpers are available.
    import app as orch

    company = os.environ.get("SMOKE_COMPANY", "WATHEFNI").strip().upper()
    suffix = uuid.uuid4().hex[:8].upper()
    code = f"JP1_{suffix}"
    actor = "00000000-0000-4000-8000-000000000001"
    phone = f"9650000{suffix[:6]}"
    app_key = f"smoke-{suffix}"

    def _cleanup() -> None:
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key=%s", (company, app_key))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (phone,))
                cur.execute("DELETE FROM positions WHERE company_code=%s AND position_code=%s", (company, code))
            conn.commit()

    # Schema
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            jobs.ensure_jobs_schema(cur)
        conn.commit()
    _ok("schema ensure_jobs_schema")

    # Existing staging jobs survive (count before/after create must not drop legacy).
    before = orch.dashboard_prehire_positions_summary(company)
    before_total = int(before.get("total_positions") or 0)
    try:
        _run_jobs_phase1_body(orch, company, suffix, code, actor, phone, app_key, before_total)
    finally:
        _cleanup()
        _ok("cleanup smoke artifacts (finally)")

    print("PASS jobs-phase1")
    print(f"ts={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")


def _run_jobs_phase1_body(orch, company, suffix, code, actor, phone, app_key, before_total) -> None:

    # Create draft
    created = jobs.create_job(
        company=company,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        payload={
            "title": f"Phase1 Smoke {suffix}",
            "title_ar": f"اختبار {suffix}",
            "position_code": code,
            "description": "EN description",
            "description_ar": "وصف عربي",
            "short_summary_en": "A concise candidate-facing summary.",
            "requirements_en": ["Python"],
            "requirements_ar": ["بايثون"],
            "approve_content_en": True,
            "department": "Engineering",
            "location": "Kuwait",
            "employment_type": "full_time",
            "vacancies": 2,
            "salary_min": 500,
            "salary_max": 800,
            "currency": "KD",
            "salary_visibility": "hr_only",
        },
        as_draft=True,
    )
    if created.get("status") != "draft":
        _fail("create draft", str(created.get("status")))
    _ok("create draft")

    # Edit draft (no status change)
    edited = jobs.update_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        payload={"description": "EN description updated", "vacancies": 3},
        expected_version=created.get("version"),
    )
    if edited.get("status") != "draft":
        _fail("edit draft kept status", str(edited.get("status")))
    if int(edited.get("vacancies") or 0) != 3:
        _fail("edit vacancies", str(edited.get("vacancies")))
    _ok("edit draft")

    # Stale edit
    try:
        jobs.update_job(
            company=company,
            position_code=code,
            db_connect=orch.db_connect,
            actor_user_id=actor,
            payload={"description": "stale"},
            expected_version=1,
        )
        _fail("stale edit should conflict")
    except jobs.JobsError as exc:
        if exc.code != "stale_job_version":
            _fail("stale edit code", exc.code)
        _ok("stale edit rejected")

    # Publish
    published = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        to_status="open",
        expected_version=edited.get("version"),
    )
    if published.get("status") != "open" or published.get("transition_action") != "publish":
        _fail("publish", str(published))
    _ok("publish draft→open")

    # Intake accepts open
    role = orch.public_role_by_apply_code(created.get("apply_code") or f"APPLY-{company}-{code}")
    if not role:
        _fail("open intake accept")
    _ok("open accepts intake")

    # Pause / resume
    paused = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        to_status="paused",
        expected_version=published.get("version"),
    )
    if paused.get("transition_action") != "pause":
        _fail("pause", str(paused))
    if orch.public_role_by_apply_code(created.get("apply_code")):
        _fail("paused must reject intake")
    _ok("pause + intake rejected")

    resumed = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        to_status="open",
        expected_version=paused.get("version"),
    )
    if resumed.get("transition_action") != "resume":
        _fail("resume", str(resumed))
    _ok("resume paused→open")

    # Close / reopen
    closed = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        to_status="closed",
        expected_version=resumed.get("version"),
    )
    if closed.get("transition_action") != "close":
        _fail("close", str(closed))
    if orch.public_role_by_apply_code(created.get("apply_code")):
        _fail("closed must reject intake")
    _ok("close + intake rejected")

    # Generic create must not reopen
    try:
        jobs.create_job(
            company=company,
            db_connect=orch.db_connect,
            actor_user_id=actor,
            payload={"title": f"Phase1 Smoke {suffix}", "position_code": code, "salary_min": 1},
            as_draft=False,
        )
        _fail("duplicate create should conflict")
    except jobs.JobsError as exc:
        if exc.code != "position_code_conflict":
            _fail("duplicate code", exc.code)
        # Existing closed job must remain closed
        current = jobs.get_job(company=company, position_code=code, db_connect=orch.db_connect)
        if current.get("status") != "closed":
            _fail("create must not reopen closed", str(current.get("status")))
        _ok("duplicate code conflict; closed stays closed")

    reopened = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=actor,
        to_status="open",
        expected_version=closed.get("version"),
    )
    if reopened.get("transition_action") != "reopen":
        _fail("reopen", str(reopened))
    _ok("reopen closed→open")

    # Stale transition
    try:
        jobs.transition_job(
            company=company,
            position_code=code,
            db_connect=orch.db_connect,
            actor_user_id=actor,
            to_status="closed",
            expected_version=1,
        )
        _fail("stale transition should conflict")
    except jobs.JobsError as exc:
        if exc.code != "stale_job_version":
            _fail("stale transition code", exc.code)
        _ok("stale transition rejected")

    # Invalid transition
    try:
        jobs.transition_job(
            company=company,
            position_code=code,
            db_connect=orch.db_connect,
            actor_user_id=actor,
            to_status="draft",
            expected_version=reopened.get("version"),
        )
        _fail("open→draft should be invalid")
    except jobs.JobsError as exc:
        if exc.code != "invalid_job_transition":
            _fail("invalid transition code", exc.code)
        _ok("invalid transition rejected")

    # Vacancy math fixture: temporary hired row for count only; always cleaned in finally.
    # data_source must remain production so vacancy_counts includes it; mark via raw_json.
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates (phone, name, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name
                """,
                (phone, f"Smoke Hire {suffix}"),
            )
            cur.execute(
                "DELETE FROM applications WHERE company_code=%s AND app_key=%s",
                (company, app_key),
            )
            cur.execute(
                """
                INSERT INTO applications (
                  app_key, company_code, phone, position_code, position_title, status,
                  cv_received, data_source, ingested_at, updated_at, raw_json
                ) VALUES (%s,%s,%s,%s,%s,'hired', TRUE, 'production', now(), now(),
                          jsonb_build_object('smoke', true, 'jobs_phase1', true))
                """,
                (app_key, company, phone, code, created.get("title")),
            )
            vac = jobs.vacancy_counts(cur, company=company, position_code=code, approved_headcount=3)
        conn.commit()
    if vac.get("filled_vacancies") != 1 or vac.get("remaining_vacancies") != 2:
        _fail("vacancy math", str(vac))
    _ok("vacancy remaining = headcount - hired")

    # Applications remain attached after lifecycle churn
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM applications WHERE company_code=%s AND position_code=%s AND app_key=%s",
                (company, code, app_key),
            )
            n = int((cur.fetchone() or {}).get("n") or 0)
    if n != 1:
        _fail("application preserved", str(n))
    _ok("application remains attached")

    # WA link uses env config
    try:
        number = jobs.apply_whatsapp_number()
        link = jobs.apply_link(created.get("apply_code"))
        if not link or number not in (link or ""):
            _fail("apply link number", str(link))
        _ok(f"apply link uses configured number ({number})")
    except jobs.JobsError as exc:
        _fail("apply whatsapp configured", exc.message)

    # File-based inventory quarantined by default
    if jobs.file_based_positions_enabled():
        _fail("file positions should be disabled by default")
    _ok("file-based positions quarantined")

    after = orch.dashboard_prehire_positions_summary(company)
    after_total = int(after.get("total_positions") or 0)
    if after_total < before_total + 1:
        _fail("existing jobs survived", f"before={before_total} after={after_total}")
    _ok(f"inventory grew safely ({before_total} → {after_total})")


if __name__ == "__main__":
    main()
