#!/usr/bin/env python3
"""Owner-UX evidence for Stage A share-surface remediation (staging only)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch
import prehire_jobs as jobs

COMPANY = "WATHEFNI"
ACTOR = "00000000-0000-4000-8000-000000000001"
MARKER = "OWNERUX-07210122"


def ensure_job(code: str, payload: dict) -> dict:
    try:
        return jobs.get_job(company=COMPANY, position_code=code, db_connect=orch.db_connect)
    except jobs.JobsError:
        draft = jobs.create_job(
            company=COMPANY,
            db_connect=orch.db_connect,
            actor_user_id=ACTOR,
            payload=payload,
            as_draft=True,
        )
        return jobs.transition_job(
            company=COMPANY,
            position_code=code,
            db_connect=orch.db_connect,
            actor_user_id=ACTOR,
            to_status="open",
            expected_version=draft.get("version"),
        )


def main() -> None:
    assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni_staging"
    assert os.environ.get("WATHEFNI_DELIVERY_MODE") == "dry_run"
    yesterday = (datetime.now(ZoneInfo("Asia/Kuwait")).date() - timedelta(days=1)).isoformat()

    expired = ensure_job(
        f"{MARKER}-EXPIRED",
        {
            "title_en": f"{MARKER} Expired Deadline",
            "position_code": f"{MARKER}-EXPIRED",
            "visibility": "public",
            "short_summary_en": "Expired deadline share-surface sample.",
            "requirements_en": ["Experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
            "application_deadline": yesterday,
        },
    )
    if expired.get("eligibility_reason") != "job_deadline_passed":
        jobs.update_job(
            company=COMPANY,
            position_code=f"{MARKER}-EXPIRED",
            db_connect=orch.db_connect,
            actor_user_id=ACTOR,
            payload={"application_deadline": yesterday},
            expected_version=expired.get("version"),
        )
        expired = jobs.get_job(company=COMPANY, position_code=f"{MARKER}-EXPIRED", db_connect=orch.db_connect)

    full_base = ensure_job(
        f"{MARKER}-FULL",
        {
            "title_en": f"{MARKER} Full Vacancies",
            "position_code": f"{MARKER}-FULL",
            "visibility": "public",
            "short_summary_en": "Full vacancies share-surface sample.",
            "requirements_en": ["Experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
    )
    full_snap = jobs.serialize_job(
        full_base,
        vacancy={"remaining_vacancies": 0, "vacancies": 1, "filled_vacancies": 1},
        include_salary=False,
    )

    targets = [
        f"{MARKER}-EN",
        f"{MARKER}-VIS-SHR",
        f"{MARKER}-VIS-INT",
        f"{MARKER}-PAUSED",
        f"{MARKER}-EXPIRED",
        f"{MARKER}-FULL",
        f"{MARKER}-INCOMPLETE",
        f"{MARKER}-ASST",
    ]
    cases = []
    for code in targets:
        try:
            job = jobs.get_job(company=COMPANY, position_code=code, db_connect=orch.db_connect)
        except jobs.JobsError as exc:
            cases.append({"position_code": code, "missing": True, "error": exc.code})
            continue
        if code.endswith("-FULL"):
            job = full_snap
        share = jobs.assistant_external_share_fields(job)
        cases.append(
            {
                "position_code": code,
                "title": job.get("title"),
                "status": job.get("status"),
                "visibility": job.get("visibility"),
                "accepts_applications": job.get("accepts_applications"),
                "eligibility_reason": job.get("eligibility_reason"),
                "shareable": job.get("shareable"),
                "apply_code_present": bool(job.get("apply_code")),
                "application_link": job.get("application_link"),
                "qr_value": job.get("qr_value"),
                "dashboard_share_controls_enabled": bool(job.get("shareable") and job.get("application_link")),
                "assistant_apply_link": share.get("apply_link"),
                "assistant_shareable": share.get("shareable"),
            }
        )

    internal_code = f"APPLY-{COMPANY}-{MARKER}-VIS-INT"
    resolved = orch.resolve_public_role_by_apply_code(internal_code)
    evidence = {
        "marker": MARKER,
        "commit": "62f13c997bb96f24f7625fe248ab7a7832a305cc",
        "staging_green": open("/opt/wathefni/staging/last-green.sha256", encoding="utf-8").read().strip(),
        "cases": cases,
        "candidate_denial": {
            "apply_code": internal_code,
            "ok": resolved.get("ok"),
            "error": resolved.get("error"),
            "unchanged_contract": resolved.get("error") == "job_visibility_denied",
        },
        "eligibility_labels": {
            "en": {
                "job_visibility_denied": "Internal only — not available on candidate WhatsApp",
                "job_paused": "Paused — not accepting applications",
                "job_deadline_passed": "Application deadline has passed",
                "job_vacancies_exhausted": "No remaining vacancies",
            },
            "ar": {
                "job_visibility_denied": "داخلية فقط — غير متاحة في واتساب المرشحين",
                "job_paused": "متوقفة مؤقتاً — لا تقبل الطلبات",
                "job_deadline_passed": "انتهى موعد التقديم",
                "job_vacancies_exhausted": "لا توجد شواغر متبقية",
            },
        },
        "owner_review": {
            "dashboard_search": MARKER,
            "page": "Staging dashboard → Pre-Hiring → Jobs → search OWNERUX-07210122",
            "expect": {
                "EN / share_only": "shareable=true, link+QR present, copy/QR enabled",
                "internal / paused / expired / full / draft": "shareable=false, link/QR null, controls disabled, eligibility reason EN+AR",
            },
        },
        "cleanup": {
            "no_validation_applications_created": True,
            "ownerux_jobs_retained": True,
            "note": "FULL vacancy proof uses remaining_vacancies=0 snapshot; no hired seed app left behind.",
        },
    }
    path = "/opt/wathefni/staging/orchestrator/ops/reports/jobs-phase2-stage-a-share-surface-ownerux.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, default=str)
    summary = [
        {
            "position_code": c.get("position_code"),
            "shareable": c.get("shareable"),
            "eligibility_reason": c.get("eligibility_reason"),
            "application_link": c.get("application_link"),
            "dashboard_share_controls_enabled": c.get("dashboard_share_controls_enabled"),
        }
        for c in cases
        if not c.get("missing")
    ]
    print(json.dumps({"report": path, "cases": summary, "candidate_denial": evidence["candidate_denial"]}, indent=2))


if __name__ == "__main__":
    main()
