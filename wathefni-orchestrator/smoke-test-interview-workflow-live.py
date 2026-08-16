from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg2.extras import Json

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    phone = f"9655599{suffix[:4]}"
    app_key = f"{phone}-WATHEFNI-INTERVIEW-SMOKE-{suffix}"
    event_id = f"interview-smoke-event-{suffix}"
    permissions = sorted(app.hr_role_permissions("owner"))
    context = {
        "company_code": company,
        "hr_phone": "96597453460",
        "hr_user": {
            "phone": "96597453460",
            "name": "smoke",
            "role": "owner",
            "status": "active",
            "company_code": company,
            "user_id": "interview-smoke-owner",
        },
        "access": {"role": "owner", "permissions": permissions},
        "permissions": permissions,
        "actor_user_id": "interview-smoke-owner",
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "interview-smoke-owner",
        "permission_subject_company": company,
        "scope": {"restricted": False},
    }

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, email, active_company_code, active_position_code, raw_json, data_source, data_source_detail)
                    VALUES (%s,%s,%s,%s,%s,%s,'production','temporary_interview_smoke')
                    """,
                    (phone, "Smoke Interview Candidate", "smoke-interview@example.com", company, "INTERVIEW_SMOKE", Json({"smoke": True})),
                )
                cur.execute(
                    """
                    INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, cv_received, raw_json, created_at, updated_at, data_source, data_source_detail)
                    VALUES (%s,%s,%s,'INTERVIEW_SMOKE','Interview Smoke','shortlisted','interview','complete',true,%s,CURRENT_DATE,CURRENT_DATE,'production','temporary_interview_smoke')
                    """,
                    (app_key, phone, company, Json({"smoke": True, "cv": {"filename": "smoke-interview.pdf"}})),
                )
            conn.commit()

        application = app.find_application_by_key(app_key, company_code=company)
        scheduled_start = datetime.now(timezone.utc) + timedelta(days=7)
        scheduled_end = scheduled_start + timedelta(minutes=30)
        interview = app.create_candidate_interview_from_schedule(
            application,
            {
                "start": scheduled_start.isoformat(),
                "end": scheduled_end.isoformat(),
                "result": {
                    "event": {
                        "id": event_id,
                        "conferenceData": {
                            "entryPoints": [{"entryPointType": "video", "uri": "https://meet.google.com/smk-test-live"}],
                        },
                    },
                },
            },
            created_by_phone="96597453460",
            source="live_smoke",
        )
        assert_true(
            bool(interview and interview["status"] == "scheduled"),
            f"scheduled interview should be created; result={interview!r}",
        )

        payload = app.dashboard_prehire_interviews(
            status=None,
            q=phone,
            role=None,
            date=None,
            interviewer=None,
            limit=100,
            offset=0,
            context=context,
        )
        assert_true(any(item["interview_id"] == interview["interview_id"] for item in payload["interviews"]), "dashboard should list smoke interview")

        updated = app.dashboard_prehire_interview_update(
            interview["interview_id"],
            app.DashboardInterviewStateRequest(status="no-show"),
            context=context,
        )
        assert_true(updated["interview"]["status"] == "no_show", "status update should normalize no-show")

        notes = app.dashboard_prehire_interview_notes(
            interview["interview_id"],
            app.DashboardInterviewNotesRequest(
                notes="Strong communication. Needs Excel follow-up.",
                status="completed",
                generate_summary=False,
                expected_updated_at=updated["interview"]["updated_at"],
            ),
            context=context,
        )
        assert_true(notes["interview"]["notes_status"] == "notes_present", "notes should be present")
        assert_true(
            notes["interview"]["human_feedback_status"] != "feedback_complete",
            "free-text notes must not fake completed human scorecard feedback",
        )

        refreshed = app.find_application_by_key(app_key, company_code=company)
        snapshot = (refreshed.get("raw_json") or {}).get("interview", {})
        assert_true(snapshot.get("status") == "completed" and bool(snapshot.get("updated_at")), "application interview snapshot should update")

        endpoint_payload = app.dashboard_prehire_interviews(
            status=None,
            q=phone,
            role=None,
            date=None,
            interviewer=None,
            limit=100,
            offset=0,
            context=context,
        )
        assert_true(endpoint_payload["company_code"] == company, "dashboard interviews endpoint should authorize and return company payload")

        print("live interview scenario passed")
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM candidate_interview_events WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidate_interviews WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM applications WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (phone,))
            conn.commit()


if __name__ == "__main__":
    main()
