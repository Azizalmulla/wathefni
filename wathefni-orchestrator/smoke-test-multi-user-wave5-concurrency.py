#!/usr/bin/env python3
"""Wave 5: concurrency / collaboration safety."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import concurrency_safety as cs  # noqa: E402
import app  # noqa: E402
import prehire_jobs as jobs  # noqa: E402
import interview_service as iv  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    check("human conflict message present", "another user" in cs.CONFLICT_MESSAGE_EN.lower())
    check("arabic conflict message present", bool(cs.CONFLICT_MESSAGE_AR.strip()))

    try:
        cs.assert_fresh(current_version=3, expected_version=2, require_token=True, code_version="stale_settings_version")
        check("stale version raises", False)
    except cs.ConcurrencyError as exc:
        detail = exc.as_detail()
        check("stale returns 409 code", exc.http_status == 409)
        check("conflict flag", detail.get("conflict") is True)
        check("includes current_version", detail.get("current_version") == 3)
        check("includes safe_next_action", detail.get("safe_next_action") == "reload_latest")
        check("human message", "another user" in str(detail.get("message") or "").lower())

    try:
        cs.assert_fresh(require_token=True)
        check("missing token raises", False)
    except cs.ConcurrencyError as exc:
        check("missing token code", exc.code == "missing_expected_version")
        check("missing token status 422", exc.http_status == 422)

    # Matching tokens pass
    cs.assert_fresh(
        current_version=5,
        expected_version=5,
        current_updated_at="2026-07-28T12:00:00+00:00",
        expected_updated_at="2026-07-28T12:00:00+00:00",
        require_token=True,
    )
    check("matching tokens pass", True)

    # Jobs require expected token
    try:
        jobs._assert_fresh({"version": 1, "updated_at": None, "position_code": "X"}, expected_updated_at=None, expected_version=None)
        check("jobs require token", False)
    except jobs.JobsError as exc:
        check("jobs missing token", exc.code == "missing_expected_version")

    try:
        jobs._assert_fresh({"version": 2, "updated_at": None, "position_code": "X"}, expected_updated_at=None, expected_version=1)
        check("jobs stale raises", False)
    except jobs.JobsError as exc:
        check("jobs stale code", exc.code == "stale_job_version")

    # set_company_setting accepts concurrency kwargs
    sig = inspect.signature(app.set_company_setting)
    check("settings require_expected param", "require_expected" in sig.parameters)
    check("settings expected_version param", "expected_version" in sig.parameters)

    notes_sig = inspect.signature(iv.save_notes_only)
    check("interview notes expected_updated_at", "expected_updated_at" in notes_sig.parameters)

    # Request models include expected tokens
    check("interview notes request has expected_updated_at", "expected_updated_at" in app.DashboardInterviewNotesRequest.model_fields)
    check("assessment review request has expected_updated_at", "expected_updated_at" in app.DashboardAssessmentReviewRequest.model_fields)

    # Waves preserved
    check("wave1 interviewer scoped", app.interview_role_is_assignment_scoped("interviewer"))
    import prehire_visibility as pv

    check("wave2 default shared", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    import prehire_ownership as own

    check("wave3 ownership present", hasattr(own, "resolve_job_recruiter_on_create"))
    import prehire_personal_work as ppw

    check("wave4 personal work present", ppw.resolve_work_scope(requested="mine", role="recruiter") == "mine")
    check("calendar routes present for C1", "/dashboard/calendar/events" in {getattr(r, "path", "") for r in app.app.routes})
    check("interview routes unchanged", "/dashboard/prehire/interviews" in {getattr(r, "path", "") for r in app.app.routes})

    print("ALL WAVE5 CONCURRENCY CHECKS PASSED")


if __name__ == "__main__":
    main()
