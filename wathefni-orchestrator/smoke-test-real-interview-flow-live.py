from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import urllib.error
import uuid
from pathlib import Path

from psycopg2.extras import Json

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def model_dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def latest_interviews(app_key: str) -> list[dict]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_interviews
                WHERE app_key=%s
                ORDER BY created_at ASC
                """,
                (app_key,),
            )
            return [dict(row) for row in cur.fetchall()]


def cleanup_calendar_events(event_ids: list[str]) -> list[dict]:
    load_gog_keyring_env()
    results = []
    for event_id in event_ids:
        if not event_id:
            continue
        try:
            result = app.run_gog(["calendar", "delete", "primary", event_id, "--force", "--no-input"], timeout=30)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        results.append({"event_id": event_id, "delete": result})
    return results


def load_gog_keyring_env() -> None:
    path = Path("/root/.openclaw/secrets/gog-keyring.env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def http_json(path: str, payload: dict | None = None, *, method: str = "POST", headers: dict[str, str] | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:8010{path}",
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"HTTP {exc.code} for {path}: {body[:800]}") from exc
    return json.loads(body) if body else {}


def live_dashboard_token() -> str | None:
    try:
        out = subprocess.check_output(["systemctl", "show", "wathefni-orchestrator.service", "-p", "MainPID", "--value"], text=True).strip()
        pid = out if out and out != "0" else ""
        if pid:
            for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
                if item.startswith(b"WATHEFNI_DASHBOARD_TOKEN="):
                    return item.split(b"=", 1)[1].decode(errors="replace")
    except Exception:
        pass
    return app.dashboard_configured_token()


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    phone = f"9655588{suffix[:4]}"
    email = f"wathefni-smoke-{suffix}@example.com"
    app_key = f"{phone}-WATHEFNI-INTERVIEW-FLOW-SMOKE-{suffix}"
    whatsapp_conversation = f"smoke-wa-interview-{suffix}"
    dashboard_conversation = f"smoke-dashboard-interview-{suffix}"
    whatsapp_admin = f"9656600{suffix[:4]}"
    cleanup_event_ids: list[str] = []

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, email, active_company_code, active_position_code, raw_json, data_source, data_source_detail)
                    VALUES (%s,%s,%s,%s,%s,%s,'production','temporary_real_interview_flow_smoke')
                    """,
                    (
                        phone,
                        f"Smoke Interview Flow {suffix}",
                        email,
                        company,
                        "INTERVIEW_FLOW_SMOKE",
                        Json({"smoke": True, "suffix": suffix}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications (app_key, phone, company_code, position_code, position_title, status, current_step, screening_status, raw_json, created_at, updated_at, data_source, data_source_detail)
                    VALUES (%s,%s,%s,'INTERVIEW_FLOW_SMOKE','Interview Flow Smoke','shortlisted','interview','complete',%s,CURRENT_DATE,CURRENT_DATE,'production','temporary_real_interview_flow_smoke')
                    """,
                    (app_key, phone, company, Json({"smoke": True, "suffix": suffix, "candidate_name": f"Smoke Interview Flow {suffix}"})),
                )
            conn.commit()

        # WhatsApp path through the running service, so it uses the same systemd env as production.
        wa_first = http_json(
            "/orchestrator/whatsapp-turn",
            {
                "account_id": "default",
                "conversation_id": whatsapp_conversation,
                "sender_phone": whatsapp_admin,
                "sender_role": "hr_admin",
                "raw_text": f"Schedule a Google Meet interview for candidate_app_key {app_key} on 2026-05-18T21:00:00+03:00",
                "metadata": {"company_code": company, "smoke": True},
            },
        )
        assert_true(wa_first.get("pending_action_id") or "confirm" in str(wa_first.get("reply_text", "")).lower(), f"WhatsApp first turn should request confirmation: {wa_first}")
        wa_second = http_json(
            "/orchestrator/whatsapp-turn",
            {
                "account_id": "default",
                "conversation_id": whatsapp_conversation,
                "sender_phone": whatsapp_admin,
                "sender_role": "hr_admin",
                "raw_text": "yes",
                "metadata": {"company_code": company, "smoke": True},
            },
        )
        assert_true(wa_second.get("intent") == "execute_candidate_workflow", f"WhatsApp confirm should execute workflow: {wa_second}")
        assert_true("scheduled" in str(wa_second.get("reply_text", "")).lower(), f"WhatsApp reply should confirm scheduling: {wa_second}")

        interviews = latest_interviews(app_key)
        assert_true(len(interviews) == 1, f"WhatsApp scheduling should create one interview, got {len(interviews)}")
        first_interview = interviews[0]
        cleanup_event_ids.append(str(first_interview.get("calendar_event_id") or ""))
        assert_true(first_interview.get("meet_link"), "WhatsApp schedule should store Google Meet link")
        assert_true(first_interview.get("calendar_event_id"), "WhatsApp schedule should store calendar event id")
        assert_true(email in str(first_interview.get("calendar_payload")), "Calendar payload should include candidate attendee email")

        # Dashboard path: dashboard AI uses the same orchestrator/channel and confirmation policy.
        token = live_dashboard_token()
        assert_true(bool(token), "Live dashboard token should be readable for HTTP dashboard smoke")
        dashboard_headers = {"Authorization": f"Bearer {token}", "X-Company-Code": company}
        dash_first_payload = http_json(
            "/dashboard/prehire/chat",
            {
                "message": f"Schedule a Google Meet interview for candidate_app_key {app_key} on 2026-05-18T22:00:00+03:00",
                "conversation_id": dashboard_conversation,
                "page": "interviews",
                "selected_app_key": app_key,
            },
            headers=dashboard_headers,
        )
        assert_true("confirm" in str(dash_first_payload.get("reply_text", "")).lower() or dash_first_payload.get("confirmation"), f"Dashboard first turn should request confirmation: {dash_first_payload}")
        dash_second_payload = http_json(
            "/dashboard/prehire/chat",
            {
                "message": "yes",
                "conversation_id": dashboard_conversation,
                "page": "interviews",
                "selected_app_key": app_key,
            },
            headers=dashboard_headers,
        )
        assert_true("scheduled" in str(dash_second_payload.get("reply_text", "")).lower(), f"Dashboard confirm should schedule: {dash_second_payload}")

        interviews = latest_interviews(app_key)
        cleanup_event_ids.extend(str(item.get("calendar_event_id") or "") for item in interviews)
        assert_true(len(interviews) == 2, f"Dashboard scheduling should create second interview, got {len(interviews)}")
        assert_true(interviews[0].get("status") == "rescheduled", f"First interview should become rescheduled, got {interviews[0].get('status')}")
        active = interviews[-1]
        assert_true(active.get("status") == "scheduled", "Latest dashboard-created interview should be scheduled")
        assert_true(active.get("meet_link"), "Dashboard schedule should store Google Meet link")

        # State changes.
        no_show = http_json(
            f"/dashboard/prehire/interviews/{active['interview_id']}",
            {"status": "no-show"},
            method="PATCH",
            headers=dashboard_headers,
        )
        assert_true(no_show["interview"]["status"] == "no_show", "No-show state should persist")
        cancel = http_json(
            f"/dashboard/prehire/interviews/{active['interview_id']}",
            {"status": "cancelled"},
            method="PATCH",
            headers=dashboard_headers,
        )
        assert_true(cancel["interview"]["status"] == "cancelled", "Cancel state should persist")

        # Notes + AI summary + feedback complete.
        notes = http_json(
            f"/dashboard/prehire/interviews/{active['interview_id']}/notes",
            {
                "notes": "Candidate communicated clearly, understood the role, and needs a follow-up Excel validation question.",
                "transcript": "HR asked about availability and Excel experience. Candidate gave structured answers and asked about next steps.",
                "status": "completed",
                "generate_summary": True,
            },
            headers=dashboard_headers,
        )
        assert_true(notes["interview"]["feedback_status"] == "feedback_complete", "Notes should mark feedback complete")
        assert_true(notes["interview"]["ai_summary"].get("summary"), "AI summary should be generated")
        assert_true("HR remains" in notes["interview"]["ai_summary"].get("decision_policy", ""), "Summary must keep HR as decision-maker")

        # Candidate drawer/application reflection.
        detail = http_json(
            f"/dashboard/prehire/applications/{app_key}",
            payload=None,
            method="GET",
            headers=dashboard_headers,
        )
        reflected = (detail.get("application") or {}).get("interview") or {}
        assert_true(reflected.get("feedback_status") == "feedback_complete", "Candidate detail should reflect feedback complete")
        assert_true(reflected.get("summary"), "Candidate detail should reflect interview AI summary")

        print("real interview flow live smoke passed")
        print("app_key=", app_key)
        print("email=", email)
        print("whatsapp_reply=", wa_second.get("reply_text"))
        print("dashboard_reply=", dash_second_payload.get("reply_text"))
        print("calendar_event_ids=", sorted({event_id for event_id in cleanup_event_ids if event_id}))
        print("calendar_cleanup_attempts=", app.json_safe(cleanup_calendar_events(list({event_id for event_id in cleanup_event_ids if event_id}))))
    finally:
        cleanup_calendar_events(list({event_id for event_id in cleanup_event_ids if event_id}))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM action_results WHERE turn_id IN (SELECT turn_id FROM hr_turns WHERE conversation_id IN (%s,%s))", (whatsapp_conversation, dashboard_conversation))
                cur.execute("DELETE FROM pending_actions WHERE conversation_id IN (%s,%s)", (whatsapp_conversation, dashboard_conversation))
                cur.execute("DELETE FROM hr_turns WHERE conversation_id IN (%s,%s)", (whatsapp_conversation, dashboard_conversation))
                cur.execute("DELETE FROM candidate_interview_events WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidate_interviews WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM applications WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (phone,))
            conn.commit()


if __name__ == "__main__":
    main()
