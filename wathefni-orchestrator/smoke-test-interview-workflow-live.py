from __future__ import annotations

import uuid

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
    context = {
        "company_code": company,
        "hr_phone": "96597453460",
        "hr_user": {"phone": "96597453460", "name": "smoke"},
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
                    INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, raw_json, created_at, updated_at, data_source, data_source_detail)
                    VALUES (%s,%s,%s,'INTERVIEW_SMOKE','Interview Smoke','shortlisted','interview','complete',%s,CURRENT_DATE,CURRENT_DATE,'production','temporary_interview_smoke')
                    """,
                    (app_key, phone, company, Json({"smoke": True})),
                )
            conn.commit()

        application = app.find_application_by_key(app_key)
        interview = app.create_candidate_interview_from_schedule(
            application,
            {
                "start": "2026-05-18T21:00:00+03:00",
                "end": "2026-05-18T21:30:00+03:00",
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
        assert_true(bool(interview and interview["status"] == "scheduled"), "scheduled interview should be created")

        payload = app.dashboard_prehire_interviews(context=context)
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
            ),
            context=context,
        )
        assert_true(notes["interview"]["feedback_status"] == "feedback_complete", "notes should mark feedback complete")

        refreshed = app.find_application_by_key(app_key)
        assert_true(
            (refreshed.get("raw_json") or {}).get("interview", {}).get("feedback_status") == "feedback_complete",
            "application interview snapshot should update",
        )

        token = app.dashboard_configured_token()
        dashboard_context = app.prehire_dashboard_context(
            app.dashboard_context(authorization=f"Bearer {token}", x_company_code=company, x_hr_phone="")
        )
        endpoint_payload = app.dashboard_prehire_interviews(context=dashboard_context)
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
