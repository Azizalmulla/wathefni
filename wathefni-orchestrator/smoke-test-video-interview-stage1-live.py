from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from psycopg2.extras import Json

import app


BASE_URL = "http://127.0.0.1:8010"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def http_json(
    path_or_url: str,
    payload: dict | None = None,
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> tuple[int, dict]:
    if path_or_url.startswith("http"):
        parsed = urllib.parse.urlparse(path_or_url)
        url = f"{BASE_URL}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")
    else:
        url = f"{BASE_URL}{path_or_url}"
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    if status != expected_status:
        raise AssertionError(f"HTTP {status} for {url}; expected {expected_status}: {body[:1200]}")
    try:
        return status, json.loads(body) if body else {}
    except Exception:
        return status, {"raw": body}


def http_text(path_or_url: str, *, expected_status: int = 200) -> tuple[int, str]:
    if path_or_url.startswith("http"):
        parsed = urllib.parse.urlparse(path_or_url)
        url = f"{BASE_URL}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")
    else:
        url = f"{BASE_URL}{path_or_url}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    if status != expected_status:
        raise AssertionError(f"HTTP {status} for {url}; expected {expected_status}: {body[:1200]}")
    return status, body


def http_multipart(
    path_or_url: str,
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    expected_status: int = 200,
) -> tuple[int, dict]:
    if path_or_url.startswith("http"):
        parsed = urllib.parse.urlparse(path_or_url)
        url = f"{BASE_URL}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")
    else:
        url = f"{BASE_URL}{path_or_url}"
    boundary = f"----wathefni-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
        .encode()
    )
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    if status != expected_status:
        raise AssertionError(f"HTTP {status} for {url}; expected {expected_status}: {body[:1200]}")
    return status, json.loads(body) if body else {}


def live_dashboard_token() -> str | None:
    try:
        pid = subprocess.check_output(
            ["systemctl", "show", "wathefni-orchestrator.service", "-p", "MainPID", "--value"],
            text=True,
        ).strip()
        if pid and pid != "0":
            for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
                if item.startswith(b"WATHEFNI_DASHBOARD_TOKEN="):
                    return item.split(b"=", 1)[1].decode(errors="replace")
    except Exception:
        pass
    return app.dashboard_configured_token()


def upsert_smoke_hr_users(company: str, owner_phone: str, viewer_phone: str) -> tuple[Path, str | None]:
    path = app.WORKSPACE / "data" / "companies" / company / "hr-users.json"
    original = path.read_text() if path.exists() else None
    payload = app.read_json(path, {"company_code": company, "users": []})
    users = [item for item in payload.get("users") or [] if app.digits((item or {}).get("phone") if isinstance(item, dict) else str(item)) not in {owner_phone, viewer_phone}]
    users.extend(
        [
            {"phone": owner_phone, "name": "Video Smoke Owner", "role": "owner"},
            {"phone": viewer_phone, "name": "Video Smoke Viewer", "role": "viewer"},
        ]
    )
    payload["company_code"] = company
    payload["users"] = users
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path, original


def restore_file(path: Path, original: str | None) -> None:
    if original is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        path.write_text(original)


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    numeric_suffix = f"{int(suffix[:6], 16) % 10000:04d}"
    company = "WATHEFNI"
    owner_phone = f"9657700{numeric_suffix}"
    viewer_phone = f"9657701{numeric_suffix}"
    candidate_phone = f"9657711{numeric_suffix}"
    app_key = f"{candidate_phone}-WATHEFNI-VIDEO-SMOKE-{suffix}"
    email = f"video-smoke-{suffix}@example.com"
    hr_users_path: Path | None = None
    hr_users_original: str | None = None
    original_module_rows: list[dict] = []
    stored_paths: list[Path] = []
    interview_id = ""

    try:
        token = live_dashboard_token()
        assert_true(bool(token), "Live dashboard token should be readable")
        hr_users_path, hr_users_original = upsert_smoke_hr_users(company, owner_phone, viewer_phone)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT module_key, enabled, settings FROM company_modules WHERE company_code=%s AND module_key='pre_hiring'",
                    (company,),
                )
                original_module_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'pre_hiring',true,'video_interview_stage1_smoke',%s,now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET enabled=true, settings=company_modules.settings || EXCLUDED.settings, updated_at=now()
                    """,
                    (company, Json({"video_interview_stage1_smoke": True})),
                )
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, email, active_company_code, active_position_code, raw_json, data_source, data_source_detail)
                    VALUES (%s,%s,%s,%s,'VIDEO_SMOKE',%s,'production','temporary_video_interview_stage1_smoke')
                    """,
                    (candidate_phone, f"Video Smoke Candidate {suffix}", email, company, Json({"smoke": True, "suffix": suffix})),
                )
                cur.execute(
                    """
                    INSERT INTO applications (
                      app_key, phone, company_code, position_code, position_title, status, current_step,
                      screening_status, raw_json, created_at, updated_at, data_source, data_source_detail
                    )
                    VALUES (%s,%s,%s,'VIDEO_SMOKE','Video Interview Smoke','shortlisted','interview','complete',%s,CURRENT_DATE,CURRENT_DATE,'production','temporary_video_interview_stage1_smoke')
                    """,
                    (app_key, candidate_phone, company, Json({"smoke": True, "suffix": suffix})),
                )
            conn.commit()

        owner_headers = {"Authorization": f"Bearer {token}", "X-Company-Code": company, "X-HR-Phone": owner_phone}
        viewer_headers = {"Authorization": f"Bearer {token}", "X-Company-Code": company, "X-HR-Phone": viewer_phone}

        _, denied = http_json(
            f"/dashboard/prehire/applications/{app_key}/video-interview",
            {"send_invite": False, "questions": [{"prompt_text": "Viewer should not create this.", "max_duration_seconds": 60}]},
            headers=viewer_headers,
            expected_status=403,
        )
        detail = denied.get("detail") if isinstance(denied.get("detail"), dict) else {}
        assert_true(detail.get("error") == "permission_denied", f"Viewer should be denied: {denied}")
        assert_true(detail.get("required_permission") == "interview.manage", f"Denied response should name interview.manage: {denied}")

        _, created = http_json(
            f"/dashboard/prehire/applications/{app_key}/video-interview",
            {
                "send_invite": False,
                "retake_enabled": True,
                "max_retakes": 1,
                "link_ttl_days": 7,
                "questions": [
                    {
                        "prompt_text": "Please summarize your most relevant experience for this role.",
                        "competency": "role_fit",
                        "max_duration_seconds": 90,
                        "required": True,
                    }
                ],
            },
            headers=owner_headers,
        )
        assert_true(created.get("ok") is True, f"HR create should succeed: {created}")
        result = created.get("result") if isinstance(created.get("result"), dict) else {}
        public_link = str(result.get("public_link") or "")
        created_interview = result.get("interview") if isinstance(result.get("interview"), dict) else {}
        interview_id = str(created_interview.get("interview_id") or "")
        assert_true(bool(public_link and interview_id), f"Create should return interview_id and public_link: {created}")

        _, html = http_text(public_link)
        assert_true("Wathefni Video Interview" in html, "Signed candidate link should open HTML")

        parsed = urllib.parse.urlparse(public_link)
        state_path = f"{parsed.path}/state?{parsed.query}"
        _, state = http_json(state_path, payload=None, method="GET")
        questions = state.get("questions") if isinstance(state.get("questions"), list) else []
        assert_true(len(questions) == 1, f"State should return one smoke question: {state}")
        question_id = questions[0]["question_id"]
        assert_true(state["interview"]["async_status"] in {"opened", "pending", "link_sent"}, f"State should open interview: {state}")

        _, consented = http_json(
            f"{parsed.path}/consent?{parsed.query}",
            {"consent": True, "candidate_name": f"Video Smoke Candidate {suffix}", "privacy_notice_version": "v1", "device_info": {"smoke": True}},
        )
        assert_true(consented["interview"]["consent_required"] is False, f"Consent should persist: {consented}")

        _, answered = http_multipart(
            f"{parsed.path}/responses?{parsed.query}",
            fields={
                "question_id": question_id,
                "response_text": "I have relevant experience and can explain it clearly.",
                "transcript_text": "Candidate described relevant role experience clearly.",
                "video_filename": "stage1-smoke.webm",
                "mime_type": "video/webm",
                "duration_seconds": "12",
                "metadata": json.dumps({"smoke": True}),
            },
            file_field="video",
            filename="stage1-smoke.webm",
            content_type="video/webm",
            file_bytes=b"wathefni-video-smoke-webm",
        )
        assert_true(answered["interview"]["response_count"] == 1, f"Response should persist: {answered}")

        _, completed = http_json(f"{parsed.path}/complete?{parsed.query}", {})
        assert_true(completed["interview"]["async_status"] == "completed", f"Complete should mark async_status completed: {completed}")
        assert_true(completed.get("completed") is True, f"Complete endpoint should report completed: {completed}")

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM candidate_interviews WHERE interview_id=%s", (interview_id,))
                interview = dict(cur.fetchone() or {})
                assert_true(interview.get("company_code") == company and interview.get("company_id") == company, f"Interview company scope wrong: {interview}")
                assert_true(interview.get("app_key") == app_key, f"Interview app scope wrong: {interview}")
                assert_true(interview.get("interview_type") == "async_video", f"Interview type wrong: {interview}")
                assert_true(interview.get("async_status") == "completed", f"Interview completion not stored: {interview}")
                ai_summary = interview.get("ai_summary") if isinstance(interview.get("ai_summary"), dict) else {}
                for key in ("summary", "strengths", "concerns", "communication_notes", "role_fit_evidence", "missing_evidence", "follow_up_questions", "recommended_next_step", "hr_decision_note"):
                    assert_true(key in ai_summary, f"ai_summary missing {key}: {ai_summary}")
                assert_true("decision-maker" in str(ai_summary.get("hr_decision_note")), f"HR decision note missing: {ai_summary}")

                cur.execute("SELECT * FROM candidate_video_interview_questions WHERE interview_id=%s", (interview_id,))
                question_rows = [dict(row) for row in cur.fetchall()]
                assert_true(len(question_rows) == 1, f"Question row missing: {question_rows}")
                assert_true(question_rows[0].get("company_code") == company and question_rows[0].get("company_id") == company, f"Question scope wrong: {question_rows}")

                cur.execute("SELECT * FROM candidate_video_interview_responses WHERE interview_id=%s", (interview_id,))
                response_rows = [dict(row) for row in cur.fetchall()]
                assert_true(len(response_rows) == 1, f"Response row missing: {response_rows}")
                response = response_rows[0]
                assert_true(response.get("company_code") == company and response.get("company_id") == company, f"Response scope wrong: {response}")
                assert_true(bool(response.get("video_file_id")), f"Response should link file_registry: {response}")
                if response.get("local_path"):
                    stored_paths.append(Path(str(response["local_path"])))
                    assert_true(Path(str(response["local_path"])).exists(), f"Stored video file missing: {response['local_path']}")

                cur.execute("SELECT * FROM file_registry WHERE file_id=%s", (response.get("video_file_id"),))
                file_row = dict(cur.fetchone() or {})
                assert_true(file_row.get("company_code") == company, f"File registry company wrong: {file_row}")
                assert_true(file_row.get("subject_type") == "candidate_interview" and file_row.get("subject_key") == interview_id, f"File registry subject wrong: {file_row}")

                cur.execute("SELECT * FROM candidate_interview_events WHERE app_key=%s ORDER BY created_at", (app_key,))
                events = [dict(row) for row in cur.fetchall()]
                event_types = {row.get("event_type") for row in events}
                for event_type in {"video_created", "video_link_opened", "video_consent_accepted", "video_response_submitted", "video_completed"}:
                    assert_true(event_type in event_types, f"Missing event {event_type}: {event_types}")
                for row in events:
                    assert_true(row.get("company_code") == company and row.get("company_id") == company, f"Event company scope wrong: {row}")
                    assert_true(row.get("app_key") == app_key and str(row.get("interview_id")) == interview_id, f"Event app/interview scope wrong: {row}")
                    assert_true(row.get("action") and row.get("target"), f"Event action/target missing: {row}")
                    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                    audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
                    assert_true(audit.get("company_code") == company and audit.get("company_id") == company, f"Event audit company wrong: {row}")
                    assert_true(audit.get("app_key") == app_key and audit.get("interview_id") == interview_id, f"Event audit target wrong: {row}")
                    assert_true(bool(audit.get("timestamp")), f"Event audit timestamp missing: {row}")

                create_event = next(row for row in events if row.get("event_type") == "video_created")
                assert_true(create_event.get("actor_user_id") == owner_phone, f"Create actor_user_id wrong: {create_event}")
                assert_true(create_event.get("actor_role") == "owner", f"Create actor_role wrong: {create_event}")
                response_event = next(row for row in events if row.get("event_type") == "video_response_submitted")
                assert_true(response_event.get("actor_role") == "candidate", f"Candidate actor role wrong: {response_event}")

                cur.execute(
                    """
                    SELECT *
                    FROM action_results
                    WHERE action_type='send_video_interview' AND result::text ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (f"%{app_key}%",),
                )
                action_result = dict(cur.fetchone() or {})
                assert_true(action_result.get("company_code") == company, f"ActionResult company wrong: {action_result}")
                assert_true(action_result.get("actor_user_id") == owner_phone, f"ActionResult actor wrong: {action_result}")
                assert_true(action_result.get("actor_role") == "owner", f"ActionResult role wrong: {action_result}")

        print("video interview stage1 live smoke passed")
        print("app_key=", app_key)
        print("interview_id=", interview_id)
        print("question_id=", question_id)
        print("public_link_path=", parsed.path)
    finally:
        if hr_users_path is not None:
            restore_file(hr_users_path, hr_users_original)
        for path in stored_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                if interview_id:
                    cur.execute("DELETE FROM file_registry WHERE subject_type='candidate_interview' AND subject_key=%s", (interview_id,))
                cur.execute("DELETE FROM action_results WHERE action_type='send_video_interview' AND result::text ILIKE %s", (f"%{app_key}%",))
                cur.execute("DELETE FROM candidate_interview_events WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidate_interviews WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM applications WHERE app_key=%s", (app_key,))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (candidate_phone,))
                if original_module_rows:
                    original = original_module_rows[0]
                    cur.execute(
                        """
                        UPDATE company_modules
                        SET enabled=%s, settings=%s, updated_at=now()
                        WHERE company_code=%s AND module_key='pre_hiring'
                        """,
                        (original.get("enabled"), Json(original.get("settings") or {}), company),
                    )
                else:
                    cur.execute("DELETE FROM company_modules WHERE company_code=%s AND module_key='pre_hiring'", (company,))
            conn.commit()


if __name__ == "__main__":
    main()
