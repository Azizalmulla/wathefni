"""Staging-only authority proof for Assessments Cleanup-1.

Writes synthetic tenants and deletes every fixture before exit. Delivery is
mocked and no real candidate communication is sent.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import app
import assessment_lifecycle as lifecycle


COMPANY_A = "ASSESSC1A"
COMPANY_B = "ASSESSC1B"
MARKER = "temporary_assessments_cleanup1_smoke"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, value: bool | Callable[[], bool]) -> None:
        try:
            ok = bool(value() if callable(value) else value)
        except Exception as exc:
            self.failed.append(f"{label}: {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        payload = {
            "suite": "assessments_cleanup1",
            "passed": len(self.passed),
            "failed": len(self.failed),
            "checks": {"passed": self.passed, "failed": self.failed},
            "synthetic_cleanup": cleanup_counts(),
            "real_delivery_sent": False,
            "production_touched": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1 if self.failed or any(payload["synthetic_cleanup"].values()) else 0


def http_code(exc: BaseException) -> str:
    detail = getattr(exc, "detail", {})
    return str(detail.get("error") if isinstance(detail, dict) else detail)


def purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM assessment_item_drafts WHERE company_code=ANY(%s)", (companies,))
    cur.execute("DELETE FROM assessment_attempts WHERE company_code=ANY(%s)", (companies,))
    cur.execute("DELETE FROM applications WHERE company_code=ANY(%s)", (companies,))
    cur.execute("DELETE FROM candidates WHERE phone LIKE '96570001%' OR phone LIKE '96570002%'")
    cur.execute("DELETE FROM company_modules WHERE company_code=ANY(%s)", (companies,))
    cur.execute("DELETE FROM companies WHERE company_code=ANY(%s)", (companies,))


def cleanup_counts() -> dict[str, int]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM assessment_attempts WHERE company_code IN (%s,%s)) AS attempts,
                  (SELECT COUNT(*) FROM assessment_item_drafts WHERE company_code IN (%s,%s)) AS drafts,
                  (SELECT COUNT(*) FROM applications WHERE company_code IN (%s,%s)) AS applications,
                  (SELECT COUNT(*) FROM company_modules WHERE company_code IN (%s,%s)) AS modules,
                  (SELECT COUNT(*) FROM companies WHERE company_code IN (%s,%s)) AS companies
                """,
                (COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B),
            )
            return {key: int(value or 0) for key, value in dict(cur.fetchone()).items()}


def insert_application(cur: Any, company: str, suffix: str, status: str = "ready_for_review") -> dict[str, Any]:
    company_digit = "1" if company == COMPANY_A else "2"
    phone = f"9657000{company_digit}{int(suffix):03d}"
    app_key = f"{company.lower()}-{suffix}"
    cur.execute(
        "INSERT INTO candidates (phone,name,email) VALUES (%s,%s,%s) ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name,email=EXCLUDED.email",
        (phone, f"Cleanup Candidate {suffix}", f"cleanup-{company.lower()}-{suffix}@example.invalid"),
    )
    raw = {
        "smoke": MARKER,
        "cv": {"received": True},
        "screening": {"status": "manual_complete", "source": "pre_assessment"},
    }
    cur.execute(
        """
        INSERT INTO applications
          (app_key, phone, company_code, position_code, position_title, status,
           current_step, cv_received, screening_status, raw_json, data_source,
           ingested_at, created_at, updated_at)
        VALUES (%s,%s,%s,'ROLE1','Cleanup Test Role',%s,'review',TRUE,'complete',%s,'production',now(),now(),now())
        RETURNING *
        """,
        (app_key, phone, company, status, app.Json(raw)),
    )
    return dict(cur.fetchone())


def setup() -> dict[str, dict[str, Any]]:
    apps: dict[str, dict[str, Any]] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            purge(cur)
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    """
                    INSERT INTO companies (company_code,name,metadata,raw_json,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    """,
                    (company, f"Assess Cleanup {company[-1]}", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
                )
                for module in ("pre_hiring", "assessments"):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code,module_key,enabled,source,updated_at)
                        VALUES (%s,%s,TRUE,'smoke',now())
                        """,
                        (company, module),
                    )
            for suffix in ("001", "002", "003", "004", "005"):
                apps[suffix] = insert_application(cur, COMPANY_A, suffix)
            apps["b001"] = insert_application(cur, COMPANY_B, "001")
        conn.commit()
    return apps


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            purge(cur)
        conn.commit()


def create_attempt(application: dict[str, Any]) -> dict[str, Any]:
    result = app.create_or_resume_assessment_attempt(application, source=MARKER, requested_by="smoke-owner")
    assert result.get("ok"), result
    return dict(result["attempt"])


def issue(attempt: dict[str, Any]) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            raw, _row = lifecycle.issue_token(
                cur,
                attempt_id=str(attempt["attempt_id"]),
                company_code=str(attempt["company_code"]),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        conn.commit()
    return raw


def attempt_row(attempt_id: str, company: str = COMPANY_A) -> dict[str, Any]:
    row = app.assessment_attempt_by_id(attempt_id, company)
    assert row
    return row


def answer_current(attempt: dict[str, Any], token: str) -> dict[str, Any]:
    state = app.public_assessment_state(str(attempt["attempt_id"]), token, start=True)
    item = state["item"]
    selected = str(item["choices"][0]["key"])
    return app.record_assessment_response(
        attempt_id=str(attempt["attempt_id"]),
        company_code=str(attempt["company_code"]),
        raw_token=token,
        item_id=str(item["item_id"]),
        response_text=selected,
        selected_key=selected,
        progress_version=int(state["attempt"]["progress_version"]),
    )


def complete(attempt: dict[str, Any], token: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    while not result.get("completed"):
        current = attempt_row(str(attempt["attempt_id"]), str(attempt["company_code"]))
        result = answer_current(current, token)
    return result


def authority_context(company: str) -> dict[str, Any]:
    actor = f"{company.lower()}-owner"
    return {
        "company_code": company,
        "actor_user_id": actor,
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": actor,
        "permission_subject_company": company,
        "permissions": ["prehire.read", "assessment.manage"],
        "hr_user": {
            "user_id": actor,
            "phone": "96599999999",
            "email": f"{actor}@example.invalid",
            "role": "owner",
            "status": "active",
        },
    }


def run(checks: Checks, applications: dict[str, dict[str, Any]]) -> None:
    attempt = create_attempt(applications["001"])
    token = issue(attempt)
    state = app.public_assessment_state(str(attempt["attempt_id"]), token, start=True)
    first_item = state["item"]
    selected = first_item["choices"][0]["key"]
    first = app.record_assessment_response(
        attempt_id=str(attempt["attempt_id"]),
        company_code=COMPANY_A,
        raw_token=token,
        item_id=first_item["item_id"],
        response_text=selected,
        selected_key=selected,
        progress_version=state["attempt"]["progress_version"],
    )
    duplicate = app.record_assessment_response(
        attempt_id=str(attempt["attempt_id"]),
        company_code=COMPANY_A,
        raw_token=token,
        item_id=first_item["item_id"],
        response_text=selected,
        selected_key=selected,
        progress_version=state["attempt"]["progress_version"],
    )
    checks.check("duplicate answer is idempotent", duplicate.get("idempotent") is True)
    checks.check("duplicate answer does not advance", duplicate["attempt"]["current_item_index"] == first["attempt"]["current_item_index"] == 1)

    concurrent_state = app.public_assessment_state(str(attempt["attempt_id"]), token, start=False)
    concurrent_item = concurrent_state["item"]
    concurrent_selected = concurrent_item["choices"][0]["key"]

    def submit_concurrent() -> dict[str, Any]:
        return app.record_assessment_response(
            attempt_id=str(attempt["attempt_id"]),
            company_code=COMPANY_A,
            raw_token=token,
            item_id=concurrent_item["item_id"],
            response_text=concurrent_selected,
            selected_key=concurrent_selected,
            progress_version=concurrent_state["attempt"]["progress_version"],
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        concurrent_results = [future.result() for future in [pool.submit(submit_concurrent), pool.submit(submit_concurrent)]]
    checks.check("concurrent duplicate inserts one response", sum(not bool(row.get("idempotent")) for row in concurrent_results) == 1)
    checks.check("concurrent duplicate advances once", attempt_row(str(attempt["attempt_id"]))["current_item_index"] == 2)

    try:
        app.record_assessment_response(
            attempt_id=str(attempt["attempt_id"]),
            company_code=COMPANY_B,
            raw_token=token,
            item_id=concurrent_item["item_id"],
            response_text=concurrent_selected,
            selected_key=concurrent_selected,
        )
        wrong_tenant = ""
    except Exception as exc:
        wrong_tenant = http_code(exc)
    checks.check("wrong tenant cannot answer attempt", wrong_tenant == "invalid_assessment_token")

    before_whatsapp = attempt_row(str(attempt["attempt_id"]))["current_item_index"]
    scope = app.set_active_company_code(COMPANY_A)
    try:
        whatsapp = app.handle_candidate_assessment_turn(
            app.WhatsAppTurnRequest(
                account_id="smoke",
                conversation_id="smoke-conversation",
                sender_phone=applications["001"]["phone"],
                raw_text="A",
            )
        )
    finally:
        app.reset_active_company_code(scope)
    after_whatsapp = attempt_row(str(attempt["attempt_id"]))["current_item_index"]
    checks.check("WhatsApp returns browser link", bool(whatsapp and "/assessment/" in str(whatsapp.get("reply"))))
    checks.check("WhatsApp cannot advance answers", before_whatsapp == after_whatsapp)

    cancel_attempt = create_attempt(applications["002"])
    cancel_token = issue(cancel_attempt)
    cancelled = app.cancel_assessment_attempt(
        cancel_attempt,
        reason="smoke_hr_cancel",
        actor_type="human",
        actor_user_id="smoke-owner",
    )
    checks.check("HR cancel terminalizes attempt", cancelled.get("status") == "cancelled")
    try:
        app.public_assessment_state(str(cancel_attempt["attempt_id"]), cancel_token, start=True)
        cancel_error = ""
    except Exception as exc:
        cancel_error = http_code(exc)
    checks.check("cancelled link rejected", cancel_error == "attempt_cancelled")

    expiry_attempt = create_attempt(applications["003"])
    expiry_token = issue(expiry_attempt)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE assessment_attempts SET expires_at=now()-interval '1 minute' WHERE attempt_id=%s",
                (expiry_attempt["attempt_id"],),
            )
        conn.commit()
    try:
        app.public_assessment_state(str(expiry_attempt["attempt_id"]), expiry_token, start=True)
        expiry_error = ""
    except Exception as exc:
        expiry_error = http_code(exc)
    checks.check("durable attempt expiry enforced", expiry_error == "attempt_expired")
    checks.check("expired status persisted", attempt_row(str(expiry_attempt["attempt_id"]))["status"] == "expired")

    resend_attempt = create_attempt(applications["004"])
    old_token = issue(resend_attempt)
    original_router = app.candidate_communication_router
    app.candidate_communication_router = lambda *_args, **_kwargs: {
        "ok": True,
        "attempts": [
            {"channel": "email", "ok": True, "result": {"intentionally_skipped": True}},
            {"channel": "whatsapp", "ok": True, "result": {"intentionally_skipped": True}},
        ],
        "successful_channels": ["email", "whatsapp"],
        "failed_channels": [],
    }
    try:
        resent = app.resend_assessment(
            applications["004"],
            resend_attempt,
            "smoke",
            requested_by="smoke-owner",
        )
    finally:
        app.candidate_communication_router = original_router
    new_token = urllib.parse.parse_qs(urllib.parse.urlsplit(resent["assessment_link"]).query)["token"][0]
    try:
        app.public_assessment_state(str(resend_attempt["attempt_id"]), old_token, start=True)
        old_token_error = ""
    except Exception as exc:
        old_token_error = http_code(exc)
    checks.check("resend revokes prior token", old_token_error == "token_revoked")
    checks.check("resend new token is active", app.public_assessment_state(str(resend_attempt["attempt_id"]), new_token, start=False)["ok"])
    checks.check("dry-run delivery is intentionally skipped", resent.get("delivery_status") == "intentionally_skipped")

    completed = complete(resend_attempt, new_token)
    checks.check("last answer completes from frozen version", completed.get("completed") is True)
    try:
        answer_current(attempt_row(str(resend_attempt["attempt_id"])), new_token)
        completed_error = ""
    except Exception as exc:
        completed_error = http_code(exc)
    checks.check("answer after completion rejected", completed_error == "attempt_completed")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT immutable, assessment_version_id FROM assessment_scores WHERE attempt_id=%s", (resend_attempt["attempt_id"],))
            score = dict(cur.fetchone())
            cur.execute("SELECT immutable, assessment_version_id, report_json FROM assessment_reports WHERE attempt_id=%s", (resend_attempt["attempt_id"],))
            report = dict(cur.fetchone())
            cur.execute("SELECT raw_json FROM applications WHERE app_key=%s AND company_code=%s", (applications["004"]["app_key"], COMPANY_A))
            application_raw = (cur.fetchone() or {}).get("raw_json") or {}
            cur.execute("SELECT COUNT(*) AS count FROM employment_offers WHERE app_key=%s AND company_code=%s", (applications["004"]["app_key"], COMPANY_A))
            offer_count = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute("SELECT COUNT(*) AS count FROM employees WHERE company_code=%s AND phone=%s", (COMPANY_A, applications["004"]["phone"]))
            employee_count = int((cur.fetchone() or {}).get("count") or 0)
    checks.check("score and report immutable", bool(score["immutable"] and report["immutable"]))
    checks.check("score and report pinned to same version", score["assessment_version_id"] == report["assessment_version_id"] == resend_attempt["assessment_version_id"])
    checks.check("completion does not rewrite screening facet", application_raw.get("screening", {}).get("status") == "manual_complete")
    checks.check("assessment completion creates no offer", offer_count == 0)
    checks.check("assessment completion cannot hire", employee_count == 0 and applications["004"]["status"] == "ready_for_review")
    exact = app.fetch_dashboard_assessment_report_payload(COMPANY_A, str(resend_attempt["attempt_id"]))
    checks.check("exact attempt report opens", exact["attempt"]["attempt_id"] == str(resend_attempt["attempt_id"]) and exact["report"] == report["report_json"])

    checks.check(
        "incomplete assessment earns zero ranking points",
        app.row_assessment_signal({"assessment_status": "in_progress", "assessment_percent": 99})["score"] == 0,
    )
    checks.check(
        "completed assessment without percent earns zero",
        app.row_assessment_signal({"assessment_status": "completed"})["score"] == 0,
    )
    counts = app.prehire_action_counts(COMPANY_A)
    awaiting = app.prehire_applications_query(
        company_code=COMPANY_A,
        status=None,
        position=None,
        search=None,
        limit=100,
        offset=0,
        assessment_status="awaiting",
    )
    awaiting_keys = {row["app_key"] for row in awaiting["applications"]}
    checks.check("ready_for_review included in assessment queue", applications["005"]["app_key"] in awaiting_keys)
    checks.check("queue and action count are identical", awaiting["total"] == counts["assessment_pending"])

    os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "true"
    context = authority_context(COMPANY_A)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM assessment_items WHERE battery_key=%s", (app.ASSESSMENT_BATTERY_KEY,))
            live_before = int(cur.fetchone()["count"])
    draft_result = app.dashboard_assessment_item_draft_create(
        app.AssessmentItemDraftRequest(
            battery_key=app.ASSESSMENT_BATTERY_KEY,
            section="logical_reasoning",
            competency_tags=["analytical_thinking"],
            difficulty="medium",
            locale="en",
            prompt_text="A verified process has four ordered controls. Which option preserves all four controls in sequence?",
            choices=[
                {"key": "A", "text": "Skip the second control"},
                {"key": "B", "text": "Perform controls one through four in order"},
                {"key": "C", "text": "Perform only the final control"},
                {"key": "D", "text": "Replace controls with an estimate"},
            ],
            proposed_answer_key="B",
            proposed_scoring={"type": "answer_key", "correct": 1, "incorrect": 0, "max_score": 1},
            rationale="Original deterministic sequencing item.",
            source_blueprint_id="approved-blueprint-smoke",
            ai_model="smoke-no-model-call",
            original_content_attested=True,
        ),
        context,
    )
    draft_id = draft_result["draft"]["draft_id"]
    automated = app.dashboard_assessment_item_draft_automated_review(draft_id, context)
    checks.check("authoring automated review passes deterministic checks", automated["findings"]["passed"] is True)
    for to_status in ("human_review", "pilot", "approved"):
        transitioned = app.dashboard_assessment_item_draft_transition(
            draft_id,
            app.AssessmentItemTransitionRequest(to_status=to_status, notes=f"smoke {to_status}"),
            context,
        )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM assessment_items WHERE battery_key=%s", (app.ASSESSMENT_BATTERY_KEY,))
            live_after = int(cur.fetchone()["count"])
            cur.execute("SELECT lifecycle_status FROM assessment_item_drafts WHERE draft_id=%s", (draft_id,))
            final_status = cur.fetchone()["lifecycle_status"]
    checks.check("human-gated authoring lifecycle reaches approved", final_status == "approved")
    checks.check("approved draft is not published to live bank", live_before == live_after and transitioned["published"] is False)


def main() -> int:
    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("assessments_cleanup1_smoke_refuses_non_staging")
    applications = setup()
    checks = Checks()
    try:
        run(checks, applications)
    except Exception as exc:
        checks.failed.append(f"suite_exception: {type(exc).__name__}: {exc}")
    finally:
        teardown()
    return checks.report()


if __name__ == "__main__":
    raise SystemExit(main())
