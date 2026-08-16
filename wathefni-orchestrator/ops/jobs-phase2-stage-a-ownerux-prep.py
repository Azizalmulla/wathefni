#!/usr/bin/env python3
"""Contained staging owner-UX fixture prep for Jobs Phase 2 Stage A."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import action_registry as registry
import app as orch
import prehire_jobs as jobs

COMPANY = "WATHEFNI"
ACTOR = "00000000-0000-4000-8000-000000000001"


def main() -> None:
    assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni_staging"
    assert os.environ.get("WATHEFNI_DELIVERY_MODE") == "dry_run"
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database() as d")
            assert cur.fetchone()["d"] == "wathefni_staging"
            jobs.ensure_jobs_schema(cur)
        conn.commit()

    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M")
    marker = f"OWNERUX-{suffix}"
    fixtures: list[dict] = []

    def add(label: str, payload: dict, *, open_it: bool = False) -> dict:
        code = payload["position_code"]
        draft = jobs.create_job(
            company=COMPANY,
            db_connect=orch.db_connect,
            actor_user_id=ACTOR,
            payload=payload,
            as_draft=True,
        )
        result = draft
        publish_error = None
        if open_it:
            try:
                result = jobs.transition_job(
                    company=COMPANY,
                    position_code=code,
                    db_connect=orch.db_connect,
                    actor_user_id=ACTOR,
                    to_status="open",
                    expected_version=draft.get("version"),
                )
            except jobs.JobsError as exc:
                publish_error = {"code": exc.code, "details": exc.details, "message": exc.message}
                result = jobs.get_job(company=COMPANY, position_code=code, db_connect=orch.db_connect)
        fixtures.append(
            {
                "label": label,
                "position_code": code,
                "title": result.get("title"),
                "status": result.get("status"),
                "visibility": result.get("visibility"),
                "work_arrangement": result.get("work_arrangement"),
                "location": result.get("location"),
                "apply_code": result.get("apply_code"),
                "publish_ready": result.get("publish_ready"),
                "publish_blockers": result.get("publish_blockers"),
                "accepts_applications": result.get("accepts_applications"),
                "eligibility_reason": result.get("eligibility_reason"),
                "content_approved_en": result.get("content_approved_en"),
                "content_approved_ar": result.get("content_approved_ar"),
                "short_summary_en": result.get("short_summary_en"),
                "short_summary_ar": result.get("short_summary_ar"),
                "application_link_present": bool(result.get("application_link")),
                "publish_error": publish_error,
                "dashboard_search": marker,
            }
        )
        return result

    add(
        "incomplete_draft",
        {
            "title_en": f"{marker} Incomplete Draft",
            "position_code": f"{marker}-INCOMPLETE",
            "visibility": "public",
            "vacancies": 1,
            "salary_visibility": "hr_only",
        },
    )
    add(
        "publish_readiness_errors",
        {
            "title_en": f"{marker} Unready Publish",
            "position_code": f"{marker}-UNREADY",
            "visibility": "public",
            "short_summary_en": "",
            "requirements_en": [],
            "location": "",
            "work_arrangement": "hybrid",
            "employment_type": "full_time",
            "vacancies": 1,
            "salary_visibility": "hr_only",
        },
        open_it=True,
    )
    add(
        "approved_english_only",
        {
            "title_en": f"{marker} English Only",
            "position_code": f"{marker}-EN",
            "visibility": "public",
            "short_summary_en": "English-approved candidate summary for owner UX.",
            "requirements_en": ["English communication"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "work_arrangement": "onsite",
            "employment_type": "full_time",
            "vacancies": 1,
            "salary_visibility": "hr_only",
        },
        open_it=True,
    )
    add(
        "approved_arabic_only",
        {
            "title_ar": f"{marker} عربي فقط",
            "position_code": f"{marker}-AR",
            "visibility": "public",
            "short_summary_ar": "ملخص معتمد للمراجعة.",
            "requirements_ar": ["تواصل فعال"],
            "approve_content_ar": True,
            "location": "الكويت",
            "work_arrangement": "onsite",
            "employment_type": "full_time",
            "vacancies": 1,
            "salary_visibility": "hr_only",
        },
        open_it=True,
    )
    add(
        "fully_remote_no_location",
        {
            "title_en": f"{marker} Fully Remote",
            "position_code": f"{marker}-REMOTE",
            "visibility": "share_only",
            "short_summary_en": "Remote role with no physical location.",
            "requirements_en": ["Self-directed work"],
            "approve_content_en": True,
            "location": "",
            "work_arrangement": "fully_remote",
            "employment_type": "full_time",
            "vacancies": 1,
            "salary_visibility": "hr_only",
        },
        open_it=True,
    )
    add(
        "visibility_public",
        {
            "title_en": f"{marker} Visibility Public",
            "position_code": f"{marker}-VIS-PUB",
            "visibility": "public",
            "short_summary_en": "Public visibility sample.",
            "requirements_en": ["Relevant experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
        open_it=True,
    )
    add(
        "visibility_share_only",
        {
            "title_en": f"{marker} Visibility Share Only",
            "position_code": f"{marker}-VIS-SHR",
            "visibility": "share_only",
            "short_summary_en": "Share-only visibility sample.",
            "requirements_en": ["Relevant experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
        open_it=True,
    )
    add(
        "visibility_internal",
        {
            "title_en": f"{marker} Visibility Internal",
            "position_code": f"{marker}-VIS-INT",
            "visibility": "internal",
            "short_summary_en": "Internal visibility sample — external APPLY must fail.",
            "requirements_en": ["Relevant experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
        open_it=True,
    )
    add(
        "summaries_and_approvals_draft",
        {
            "title_en": f"{marker} Summaries Draft",
            "title_ar": f"{marker} مسودة الموافقات",
            "position_code": f"{marker}-SUM",
            "visibility": "public",
            "short_summary_en": "Short EN summary awaiting explicit approval stamp in UI.",
            "short_summary_ar": "ملخص عربي بانتظار الاعتماد.",
            "requirements_en": ["EN req"],
            "requirements_ar": ["متطلب عربي"],
            "approve_content_en": False,
            "approve_content_ar": False,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
    )
    paused = add(
        "unavailable_paused",
        {
            "title_en": f"{marker} Paused Unavailable",
            "position_code": f"{marker}-PAUSED",
            "visibility": "public",
            "short_summary_en": "Paused job — intake closed.",
            "requirements_en": ["Experience"],
            "approve_content_en": True,
            "location": "Kuwait City",
            "employment_type": "full_time",
            "vacancies": 1,
        },
        open_it=True,
    )
    jobs.transition_job(
        company=COMPANY,
        position_code=f"{marker}-PAUSED",
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        to_status="paused",
        expected_version=paused.get("version"),
    )
    paused_fresh = jobs.get_job(company=COMPANY, position_code=f"{marker}-PAUSED", db_connect=orch.db_connect)
    for item in fixtures:
        if item["position_code"] == f"{marker}-PAUSED":
            item.update(
                {
                    "status": paused_fresh.get("status"),
                    "accepts_applications": paused_fresh.get("accepts_applications"),
                    "eligibility_reason": paused_fresh.get("eligibility_reason"),
                    "application_link_present": bool(paused_fresh.get("application_link")),
                }
            )

    asst_code = f"{marker}-ASST"
    created = jobs.create_job(
        company=COMPANY,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        payload={
            "title": f"{marker} Assistant Draft",
            "position_code": asst_code,
            "requirements_en": ["Draft only"],
            "currency": "KD",
        },
        as_draft=True,
    )
    assert created.get("status") == "draft"
    assert registry.requires_confirmation("create_job_opening", {}) is True
    fixtures.append(
        {
            "label": "assistant_created_draft_only",
            "position_code": asst_code,
            "title": created.get("title"),
            "status": created.get("status"),
            "visibility": created.get("visibility"),
            "apply_code": created.get("apply_code"),
            "publish_ready": created.get("publish_ready"),
            "publish_blockers": created.get("publish_blockers"),
            "accepts_applications": created.get("accepts_applications"),
            "requires_confirmation": True,
            "qr_image_url": None,
            "dashboard_search": marker,
        }
    )

    phone = f"9656{int(uuid.uuid4().hex[:7], 16) % 10_000_000:07d}"
    en = next(item for item in fixtures if item["label"] == "approved_english_only")
    apply_result = orch.handle_public_candidate_apply_code_turn(
        orch.WhatsAppTurnRequest(
            account_id="ownerux-prep",
            conversation_id=f"ownerux-{suffix}",
            sender_phone=phone,
            sender_role="candidate",
            raw_text=en["apply_code"],
            metadata={"locale": "en"},
        )
    )
    cv_result = orch.handle_candidate_file_turn(
        orch.WhatsAppTurnRequest(
            account_id="ownerux-prep",
            conversation_id=f"ownerux-{suffix}",
            sender_phone=phone,
            sender_role="candidate",
            raw_text="",
            media={"path": f"/tmp/ownerux-{suffix}.pdf", "type": "application/pdf"},
            metadata={"locale": "en"},
        )
    )
    internal = next(item for item in fixtures if item["label"] == "visibility_internal")
    internal_resolved = orch.resolve_public_role_by_apply_code(internal["apply_code"])

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM applications WHERE phone=%s", (phone,))
            apps = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT COUNT(*) AS c FROM candidate_job_contexts WHERE phone=%s AND status=%s",
                (phone, "awaiting_apply_confirmation"),
            )
            ctxs = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT COUNT(*) AS c FROM candidate_pending_media WHERE phone=%s AND status=%s",
                (phone, "pending"),
            )
            media = int(cur.fetchone()["c"])
            cur.execute("DELETE FROM candidate_pending_media WHERE phone=%s", (phone,))
            cur.execute("DELETE FROM candidate_job_contexts WHERE phone=%s", (phone,))
            cur.execute("DELETE FROM applications WHERE phone=%s", (phone,))
            try:
                cur.execute("DELETE FROM public_candidate_sessions WHERE phone=%s", (phone,))
            except Exception:
                conn.rollback()
                cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM applications WHERE phone=%s", (phone,))
            apps_after = int(cur.fetchone()["c"])
            cur.execute("SELECT COUNT(*) AS c FROM candidate_job_contexts WHERE phone=%s", (phone,))
            ctx_after = int(cur.fetchone()["c"])
            cur.execute("SELECT COUNT(*) AS c FROM candidate_pending_media WHERE phone=%s", (phone,))
            media_after = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT COUNT(*) AS c FROM positions WHERE company_code=%s AND position_code LIKE %s",
                (COMPANY, f"{marker}-%"),
            )
            owner_jobs = int(cur.fetchone()["c"])
            # Also remove any leftover partial OWNERUX markers from failed earlier attempts in this hour window
            cur.execute(
                """
                SELECT position_code FROM positions
                WHERE company_code=%s AND position_code LIKE 'OWNERUX-%%'
                  AND position_code NOT LIKE %s
                """,
                (COMPANY, f"{marker}-%"),
            )
            stale = [row["position_code"] for row in cur.fetchall()]
            for code in stale:
                cur.execute("DELETE FROM applications WHERE company_code=%s AND position_code=%s", (COMPANY, code))
                cur.execute("DELETE FROM positions WHERE company_code=%s AND position_code=%s", (COMPANY, code))
        conn.commit()

    green = ""
    try:
        green = open("/opt/wathefni/staging/last-green.sha256", encoding="utf-8").read().strip()
    except OSError:
        pass

    handoff = {
        "marker": marker,
        "company": COMPANY,
        "commit": "674562231c40687029bdce1b37b094ce847890b2",
        "staging_green": green,
        "dashboard": {
            "page": "Jobs",
            "search": marker,
            "note": "Open staging dashboard as WATHEFNI owner → Pre-Hiring → Jobs → search the OWNERUX marker.",
        },
        "delivery_mode": os.environ.get("WATHEFNI_DELIVERY_MODE"),
        "fixtures": fixtures,
        "stale_ownerux_cleaned": stale,
        "candidate_proof": {
            "apply_application_created": apply_result.get("application_created"),
            "cv_application_created": (cv_result or {}).get("application_created"),
            "cv_counts_as_apply_intent": (cv_result or {}).get("cv_counts_as_apply_intent"),
            "applications_before_cleanup": apps,
            "contexts_before_cleanup": ctxs,
            "pending_media_before_cleanup": media,
            "residual_after_cleanup": {
                "applications": apps_after,
                "contexts": ctx_after,
                "pending_media": media_after,
            },
            "internal_apply_error": internal_resolved.get("error"),
            "owner_jobs_retained": owner_jobs,
        },
        "share_notes": {
            "internal_external_denied": internal_resolved.get("error") == "job_visibility_denied",
            "paused_accepts_applications": paused_fresh.get("accepts_applications") is False,
            "ui_ambiguity": (
                "serialize_job still emits application_link/qr_value for internal and non-accepting jobs; "
                "external eligibility denies internal APPLY. Confirm Jobs detail share controls against "
                "accepts_applications/eligibility_reason."
            ),
        },
    }
    path = f"/opt/wathefni/staging/orchestrator/ops/reports/jobs-phase2-stage-a-ownerux-{suffix}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(handoff, fh, indent=2, default=str)
    print(json.dumps({"report": path, "marker": marker, "fixture_count": len(fixtures), "candidate_proof": handoff["candidate_proof"]}, indent=2))


if __name__ == "__main__":
    main()
