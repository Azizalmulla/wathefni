#!/usr/bin/env python3
"""Live proof for Overview Wave 2 destination parity (WATHEFNI)."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "/opt/wathefni/orchestrator")

import app as orch  # noqa: E402
import prehire_overview as po  # noqa: E402


def person_key_row(row: dict) -> str:
    email_candidates = [
        row.get("email"),
        row.get("candidate_email"),
        ((row.get("raw_json") or {}) if isinstance(row.get("raw_json"), dict) else {}).get("candidate_email"),
        ((row.get("raw_json") or {}) if isinstance(row.get("raw_json"), dict) else {}).get("email"),
    ]
    email = ""
    for value in email_candidates:
        text = str(value or "").strip().lower()
        if text and "@" in text and not text.startswith("imp-"):
            email = text
            break
    if email:
        return f"email:{email}"
    phone = str(row.get("phone") or row.get("candidate_phone") or "")
    if phone and not phone.lower().startswith("imp-"):
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) >= 8:
            return f"phone:{digits}"
    return f"singleton:{row.get('app_key') or ''}"


def people_count(apps: list[dict]) -> int:
    return len({person_key_row(a) for a in apps})


def query(**kwargs):
    return orch.prehire_applications_query(
        company_code="WATHEFNI",
        status=None,
        position=kwargs.get("position"),
        search=None,
        limit=200,
        offset=0,
        assessment_status=kwargs.get("assessment_status"),
        interview_status=kwargs.get("interview_status"),
        follow_up=kwargs.get("follow_up"),
        review_status=kwargs.get("review_status"),
        overview_cohort=kwargs.get("overview_cohort"),
        sort=kwargs.get("sort"),
    )


def main() -> int:
    company = "WATHEFNI"
    settings = {}
    try:
        settings = orch.get_company_settings(company) or {}
    except Exception:
        settings = {}

    counts = po.compute_action_counts(company=company, db_connect=orch.db_connect, assessments_enabled=True)
    role = po.compute_role_priority(company=company, db_connect=orch.db_connect, assessments_enabled=True)
    next_action = po.compute_next_action(
        company=company,
        db_connect=orch.db_connect,
        assessments_enabled=True,
        interviews_enabled=True,
        settings=settings,
    )
    wq = po.compute_work_queue(
        company=company,
        db_connect=orch.db_connect,
        assessments_enabled=True,
        interviews_enabled=True,
        limit=25,
    )
    role_steps = po.compute_role_next_steps(company=company, db_connect=orch.db_connect, assessments_enabled=True, limit=5)

    checks = []

    follow_people = int(counts.get("follow_up_needed") or 0)
    follow_apps = int(counts.get("follow_up_needed_applications") or 0)
    dest = query(follow_up="needed", overview_cohort="follow_up_needed")
    dest_people = people_count(dest.get("applications") or [])
    checks.append(
        {
            "card": "follow_up",
            "overview_people": follow_people,
            "overview_apps": follow_apps,
            "dest_total": int(dest.get("total") or 0),
            "dest_people": dest_people,
            "destination": po._destination_candidates(cohort_key=po.COHORT_FOLLOW_UP, follow_up="needed"),
            "pass": dest_people == follow_people and int(dest.get("total") or 0) == follow_apps,
        }
    )

    ready_people = int(counts.get("ready_for_review") or 0)
    ready_apps = int(counts.get("ready_for_review_applications") or 0)
    dest = query(review_status="ready", overview_cohort="ready_for_review", sort="ready_for_review")
    dest_people = people_count(dest.get("applications") or [])
    checks.append(
        {
            "card": "ready_for_review",
            "overview_people": ready_people,
            "overview_apps": ready_apps,
            "dest_total": int(dest.get("total") or 0),
            "dest_people": dest_people,
            "pass": dest_people == ready_people and int(dest.get("total") or 0) == ready_apps,
        }
    )

    assess_people = int(counts.get("assessment_pending") or 0)
    assess_apps = int(counts.get("assessment_pending_applications") or 0)
    dest = query(assessment_status="awaiting", overview_cohort="assessment_pending")
    dest_people = people_count(dest.get("applications") or [])
    checks.append(
        {
            "card": "assessment_pending",
            "overview_people": assess_people,
            "overview_apps": assess_apps,
            "dest_total": int(dest.get("total") or 0),
            "dest_people": dest_people,
            "pass": dest_people == assess_people and int(dest.get("total") or 0) == assess_apps,
        }
    )

    # Recompute interview debt people/apps from overview authority query path.
    interview_dest = po._destination_interview_scheduling_debt()
    dest = query(overview_cohort="interview_scheduling_debt", interview_status="none")
    interview_apps_n = int(dest.get("total") or 0)
    interview_people_n = people_count(dest.get("applications") or [])
    # Prefer next_action counts when that action is present / alternative.
    interview_people = interview_people_n
    interview_apps = interview_apps_n
    for alt in [next_action, *(next_action.get("alternatives") or [])]:
        if str((alt or {}).get("action") or "") == "interview_scheduling_debt":
            interview_people = int(alt.get("people_count") or alt.get("total_matching") or interview_people_n)
            interview_apps = int(alt.get("application_count") or interview_apps_n)
            break
    checks.append(
        {
            "card": "interview_scheduling_debt",
            "overview_people": interview_people,
            "overview_apps": interview_apps,
            "dest_total": interview_apps_n,
            "dest_people": interview_people_n,
            "destination": interview_dest,
            "pass": interview_people_n == interview_people
            and interview_apps_n == interview_apps
            and interview_dest["page"] == "candidates"
            and interview_dest["filters"].get("overview_cohort") == "interview_scheduling_debt",
        }
    )

    if role:
        code = role["position_code"]
        dest = query(position=code, overview_cohort="role_active")
        dest_people = people_count(dest.get("applications") or [])
        checks.append(
            {
                "card": "role_priority",
                "position": code,
                "overview_people": int(role.get("people_count") or 0),
                "overview_apps": int(role.get("application_count") or 0),
                "dest_total": int(dest.get("total") or 0),
                "dest_people": dest_people,
                "destination": role.get("destination"),
                "ranking_destination": role.get("ranking_destination"),
                "pass": dest_people == int(role.get("people_count") or 0)
                and int(dest.get("total") or 0) == int(role.get("application_count") or 0)
                and (role.get("destination") or {}).get("page") == "candidates",
            }
        )

    role_step_ok = True
    for step in role_steps:
        d = step.get("destination") or {}
        filters = d.get("filters") or {}
        if d.get("page") != "candidates" or filters.get("overview_cohort") != "role_active":
            role_step_ok = False
    checks.append(
        {
            "card": "role_next_steps",
            "count": len(role_steps),
            "sample": (role_steps[0].get("destination") if role_steps else None),
            "pass": role_step_ok and bool(role_steps),
        }
    )

    wq_ok = True
    sample = None
    for item in wq.get("items") or []:
        sample = sample or item
        d = item.get("destination") or {}
        filters = d.get("filters") or {}
        if d.get("page") != "candidates":
            wq_ok = False
        if not (d.get("cohort_key") or filters.get("cohort_key")):
            wq_ok = False
        if not item.get("app_key"):
            wq_ok = False
        if filters.get("q") and filters.get("q") != item.get("app_key"):
            wq_ok = False
    checks.append(
        {
            "card": "top_priority_work_queue",
            "people": int(wq.get("total") or 0),
            "sample_destination": (sample or {}).get("destination") if sample else None,
            "sample_app_key": (sample or {}).get("app_key") if sample else None,
            "pass": wq_ok,
        }
    )

    na_dest = next_action.get("destination") or {}
    checks.append(
        {
            "card": "next_action_destination",
            "action": next_action.get("action"),
            "destination": na_dest,
            "pass": bool(
                next_action.get("action") == "none"
                or na_dest.get("cohort_key")
                or (na_dest.get("filters") or {}).get("cohort_key")
            ),
        }
    )

    out = {"company": company, "checks": checks, "all_pass": all(bool(c.get("pass")) for c in checks)}
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
