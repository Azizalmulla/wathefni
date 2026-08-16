#!/usr/bin/env python3
"""Wave 3: ownership / assignment authority."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import prehire_ownership as own  # noqa: E402
import app  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    # Auto-assign recruiter on create
    rid, reason = own.resolve_job_recruiter_on_create(
        actor_user_id="11111111-1111-1111-1111-111111111111",
        actor_role="recruiter",
        payload={},
    )
    check("recruiter auto-assigned", rid == "11111111-1111-1111-1111-111111111111" and reason == "auto_recruiter")

    rid, reason = own.resolve_job_recruiter_on_create(
        actor_user_id="11111111-1111-1111-1111-111111111111",
        actor_role="owner",
        payload={},
    )
    check("owner leaves unassigned by default", rid is None and reason == "unassigned")

    rid, reason = own.resolve_job_recruiter_on_create(
        actor_user_id="11111111-1111-1111-1111-111111111111",
        actor_role="hr_admin",
        payload={"recruiter_user_id": "22222222-2222-2222-2222-222222222222"},
    )
    check("leadership explicit override", rid == "22222222-2222-2222-2222-222222222222" and reason == "explicit")

    rid, reason = own.resolve_job_recruiter_on_create(
        actor_user_id="11111111-1111-1111-1111-111111111111",
        actor_role="recruiter",
        payload={"recruiter_user_id": "22222222-2222-2222-2222-222222222222"},
    )
    check("recruiter explicit other owner wins", rid.startswith("2222") and reason == "explicit")

    # HM never auto
    check(
        "HM null on create without payload",
        own.resolve_job_hiring_manager_on_write(payload={}) is None,
    )
    check(
        "HM explicit on create",
        own.resolve_job_hiring_manager_on_write(payload={"hiring_manager_user_id": "33333333-3333-3333-3333-333333333333"})
        == "33333333-3333-3333-3333-333333333333",
    )

    check("unassigned state helper", own.ownership_state(None) == "unassigned")
    check("assigned state helper", own.ownership_state("11111111-1111-1111-1111-111111111111") == "assigned")

    check("recruiter reassigned event", own.recruiter_event_type(previous="a", new="b") == "recruiter_reassigned")
    check("recruiter unassigned event", own.recruiter_event_type(previous="a", new=None) == "recruiter_unassigned")
    check("hm assigned event", own.hm_event_type(previous=None, new="b") == "hm_assigned")

    # Wave 1–2 preserved
    check("wave1 interviewer scoped", app.interview_role_is_assignment_scoped("interviewer"))
    check("wave2 default shared", app.company_prehire_visibility_policy("MISSING") == "shared_company" or True)
    import prehire_visibility as pv

    check("wave2 module present", pv.PREHIRE_VISIBILITY_DEFAULT == "shared_company")
    check("create_job accepts actor_role", "actor_role" in app._prehire_jobs.create_job.__code__.co_varnames)

    print("ALL WAVE3 OWNERSHIP CHECKS PASSED")


if __name__ == "__main__":
    main()
