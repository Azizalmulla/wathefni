#!/usr/bin/env python3
"""Assessments Cleanup-1 controlled production proof + cleanup.

Uses synthetic companies only. Delivery forced to dry_run / intentionally_skipped.
Removes every synthetic fixture before exit. Does not enable authoring.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

MARKER = "temporary_assessments_cleanup1_prod_proof_v1"
COMPANY_A = "ASSESSP1A"
COMPANY_B = "ASSESSP1B"
REAL_COMPANY = "WATHEFNI"
REPORT: dict[str, Any] = {"checks": [], "migration": {}, "before": {}, "after": {}, "cleanup": {}, "hashes": {}}
PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL
    ok = bool(cond)
    if ok:
        PASS += 1
        print(f"  PASS  {label}" + (f" — {detail}" if detail not in (None, "") else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))
    REPORT["checks"].append({"label": label, "ok": ok, "detail": None if ok else detail})


def http_code(exc: BaseException) -> str:
    detail = getattr(exc, "detail", {})
    return str(detail.get("error") if isinstance(detail, dict) else detail)


def main() -> int:
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    # Production keep-off: never enable authoring for this proof.
    os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "false"

    prod_orch = os.environ.get("WATHEFNI_PROD_ORCH", "/opt/wathefni/orchestrator")
    sys.path = [p for p in sys.path if p not in {prod_orch, "/opt/wathefni/staging/orchestrator"}]
    sys.path.insert(0, prod_orch)

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    import app
    import assessment_lifecycle as lifecycle
    import operator_mobile as omobile

    if not str(getattr(app, "__file__", "")).startswith(prod_orch):
        raise RuntimeError(f"must import production app.py, got {app.__file__}")

    print("Assessments Cleanup-1 PRODUCTION controlled proof — synthetic tenants only")
    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "production" or identity.database_environment != "production":
        raise RuntimeError("assessments_cleanup1_prod_proof_refuses_non_production")
    REPORT["environment"] = identity.public()
    REPORT["authoring_env"] = os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING")
    check("authoring flag off for proof process", os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING") == "false")

    def snapshot_real() -> dict[str, int]:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM applications WHERE company_code=%s", (REAL_COMPANY,))
            apps = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM candidate_interviews WHERE company_code=%s", (REAL_COMPANY,))
            interviews = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employment_offers WHERE company_code=%s", (REAL_COMPANY,))
            offers = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employees WHERE company_code=%s", (REAL_COMPANY,))
            employees = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n FROM assessment_scores s
                JOIN assessment_attempts a ON a.attempt_id=s.attempt_id
                WHERE a.company_code=%s AND a.company_code NOT IN (%s,%s)
                """,
                (REAL_COMPANY, COMPANY_A, COMPANY_B),
            )
            # real company only
            cur.execute(
                """
                SELECT count(*) AS n FROM assessment_scores s
                JOIN assessment_attempts a ON a.attempt_id=s.attempt_id
                WHERE a.company_code=%s
                """,
                (REAL_COMPANY,),
            )
            scores = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM outbound_delivery_events WHERE account_id=%s",
                (REAL_COMPANY,),
            )
            outbound = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n FROM assessment_attempts
                WHERE company_code=%s
                """,
                (REAL_COMPANY,),
            )
            attempts = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n FROM assessment_attempts
                WHERE company_code=%s AND assessment_version_id IS NOT NULL
                """,
                (REAL_COMPANY,),
            )
            pinned = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n FROM assessment_attempts
                WHERE company_code=%s AND status='expired'
                """,
                (REAL_COMPANY,),
            )
            expired = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM assessment_items WHERE battery_key=%s", (app.ASSESSMENT_BATTERY_KEY,))
            items = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT coalesce(md5(string_agg(item_id::text || coalesce(prompt_text,'') || coalesce(answer_key,'')
                       , '|' ORDER BY item_order, item_id)), '') AS digest
                FROM assessment_items WHERE battery_key=%s
                """,
                (app.ASSESSMENT_BATTERY_KEY,),
            )
            item_digest = str((cur.fetchone() or {}).get("digest") or "")
            cur.execute(
                """
                SELECT coalesce(md5(string_agg(battery_key || coalesce(scoring_rules_json::text,'')
                       , '|' ORDER BY battery_key)), '') AS digest
                FROM assessment_batteries WHERE battery_key=%s
                """,
                (app.ASSESSMENT_BATTERY_KEY,),
            )
            rules_digest = str((cur.fetchone() or {}).get("digest") or "")
            cur.execute(
                """
                SELECT coalesce(md5(string_agg(norm_key || coalesce(percentiles::text,'')
                       , '|' ORDER BY norm_key)), '') AS digest
                FROM assessment_norm_groups WHERE battery_key=%s
                """,
                (app.ASSESSMENT_BATTERY_KEY,),
            )
            norms_digest = str((cur.fetchone() or {}).get("digest") or "")
        return {
            "applications": apps,
            "interviews": interviews,
            "offers": offers,
            "employees": employees,
            "assessment_scores": scores,
            "outbound": outbound,
            "assessment_attempts": attempts,
            "assessment_attempts_pinned": pinned,
            "assessment_attempts_expired": expired,
            "assessment_items": items,
            "item_content_digest": item_digest,
            "scoring_rules_digest": rules_digest,
            "norms_digest": norms_digest,
        }

    before = snapshot_real()
    REPORT["before"] = before

    # Migration inventory (all companies, post-migrate expected)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM assessment_attempts")
        seen = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("SELECT count(*) AS n FROM assessment_attempts WHERE assessment_version_id IS NOT NULL")
        pinned_all = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("SELECT count(*) AS n FROM assessment_attempts WHERE status='expired'")
        expired_all = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT count(*) AS n FROM assessment_responses
            WHERE assessment_version_id IS NOT NULL AND company_code IS NOT NULL
            """
        )
        responses = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("SELECT count(*) AS n FROM assessment_scores WHERE immutable IS TRUE")
        scores_frozen = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("SELECT count(*) AS n FROM assessment_reports WHERE immutable IS TRUE")
        reports_frozen = int((cur.fetchone() or {}).get("n") or 0)
    REPORT["migration"] = {
        "attempts_seen": seen,
        "attempts_pinned": pinned_all,
        "attempts_expired": expired_all,
        "responses_versioned": responses,
        "scores_frozen": scores_frozen,
        "reports_frozen": reports_frozen,
    }
    check("existing attempts are pinned", pinned_all == seen and seen > 0, f"pinned={pinned_all}/{seen}")

    def purge(cur: Any) -> None:
        companies = [COMPANY_A, COMPANY_B]
        cur.execute("DELETE FROM assessment_item_drafts WHERE company_code=ANY(%s)", (companies,))
        cur.execute("DELETE FROM assessment_attempts WHERE company_code=ANY(%s)", (companies,))
        cur.execute("DELETE FROM applications WHERE company_code=ANY(%s)", (companies,))
        cur.execute("DELETE FROM candidates WHERE phone LIKE '96571001%' OR phone LIKE '96571002%'")
        cur.execute("DELETE FROM company_modules WHERE company_code=ANY(%s)", (companies,))
        cur.execute("DELETE FROM companies WHERE company_code=ANY(%s)", (companies,))

    def cleanup_counts() -> dict[str, int]:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM assessment_attempts WHERE company_code IN (%s,%s)) AS attempts,
                  (SELECT COUNT(*) FROM assessment_item_drafts WHERE company_code IN (%s,%s)) AS drafts,
                  (SELECT COUNT(*) FROM applications WHERE company_code IN (%s,%s)) AS applications,
                  (SELECT COUNT(*) FROM company_modules WHERE company_code IN (%s,%s)) AS modules,
                  (SELECT COUNT(*) FROM companies WHERE company_code IN (%s,%s)) AS companies,
                  (SELECT COUNT(*) FROM candidates WHERE phone LIKE '96571001%%' OR phone LIKE '96571002%%') AS candidates
                """,
                (COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B, COMPANY_A, COMPANY_B),
            )
            return {key: int(value or 0) for key, value in dict(cur.fetchone()).items()}

    def insert_application(cur: Any, company: str, suffix: str, status: str = "ready_for_review") -> dict[str, Any]:
        company_digit = "1" if company == COMPANY_A else "2"
        phone = f"9657100{company_digit}{int(suffix):03d}"
        app_key = f"{company.lower()}-{suffix}"
        cur.execute(
            "INSERT INTO candidates (phone,name,email) VALUES (%s,%s,%s) ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name,email=EXCLUDED.email",
            (phone, f"Prod Cleanup Candidate {suffix}", f"prod-cleanup-{company.lower()}-{suffix}@example.invalid"),
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
            VALUES (%s,%s,%s,'ROLE1','Cleanup Prod Role',%s,'review',TRUE,'complete',%s,'production',now(),now(),now())
            RETURNING *
            """,
            (app_key, phone, company, status, app.Json(raw)),
        )
        return dict(cur.fetchone())

    apps: dict[str, dict[str, Any]] = {}
    with app.db_connect() as conn, conn.cursor() as cur:
        purge(cur)
        for company in (COMPANY_A, COMPANY_B):
            cur.execute(
                """
                INSERT INTO companies (company_code,name,metadata,raw_json,created_at,updated_at)
                VALUES (%s,%s,%s,%s,now(),now())
                """,
                (company, f"Assess Prod Cleanup {company[-1]}", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
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

    def create_attempt(application: dict[str, Any]) -> dict[str, Any]:
        result = app.create_or_resume_assessment_attempt(application, source=MARKER, requested_by="prod-proof-owner")
        assert result.get("ok"), result
        return dict(result["attempt"])

    def issue(attempt: dict[str, Any]) -> str:
        with app.db_connect() as conn, conn.cursor() as cur:
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

    try:
        attempt = create_attempt(apps["001"])
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
        check("duplicate answer is idempotent", duplicate.get("idempotent") is True)
        check(
            "duplicate answer does not advance",
            duplicate["attempt"]["current_item_index"] == first["attempt"]["current_item_index"] == 1,
        )

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
        check("concurrent duplicate inserts one response", sum(not bool(row.get("idempotent")) for row in concurrent_results) == 1)
        check("concurrent duplicate advances once", attempt_row(str(attempt["attempt_id"]))["current_item_index"] == 2)

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
        check("wrong tenant cannot answer attempt", wrong_tenant == "invalid_assessment_token")

        before_whatsapp = attempt_row(str(attempt["attempt_id"]))["current_item_index"]
        scope = app.set_active_company_code(COMPANY_A)
        try:
            whatsapp = app.handle_candidate_assessment_turn(
                app.WhatsAppTurnRequest(
                    account_id="prod-proof",
                    conversation_id="prod-proof-conversation",
                    sender_phone=apps["001"]["phone"],
                    raw_text="A",
                )
            )
        finally:
            app.reset_active_company_code(scope)
        after_whatsapp = attempt_row(str(attempt["attempt_id"]))["current_item_index"]
        check("WhatsApp returns browser link", bool(whatsapp and "/assessment/" in str(whatsapp.get("reply"))))
        check("WhatsApp cannot advance answers", before_whatsapp == after_whatsapp)

        cancel_attempt = create_attempt(apps["002"])
        cancel_token = issue(cancel_attempt)
        cancelled = app.cancel_assessment_attempt(
            cancel_attempt,
            reason="prod_proof_hr_cancel",
            actor_type="human",
            actor_user_id="prod-proof-owner",
        )
        check("HR cancel terminalizes attempt", cancelled.get("status") == "cancelled")
        try:
            app.public_assessment_state(str(cancel_attempt["attempt_id"]), cancel_token, start=True)
            cancel_error = ""
        except Exception as exc:
            cancel_error = http_code(exc)
        check("cancelled link rejected", cancel_error == "attempt_cancelled")

        expiry_attempt = create_attempt(apps["003"])
        expiry_token = issue(expiry_attempt)
        with app.db_connect() as conn, conn.cursor() as cur:
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
        check("durable attempt expiry enforced", expiry_error == "attempt_expired")
        check("expired status persisted", attempt_row(str(expiry_attempt["attempt_id"]))["status"] == "expired")

        resend_attempt = create_attempt(apps["004"])
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
                apps["004"],
                resend_attempt,
                "prod-proof",
                requested_by="prod-proof-owner",
            )
        finally:
            app.candidate_communication_router = original_router
        new_token = urllib.parse.parse_qs(urllib.parse.urlsplit(resent["assessment_link"]).query)["token"][0]
        try:
            app.public_assessment_state(str(resend_attempt["attempt_id"]), old_token, start=True)
            old_token_error = ""
        except Exception as exc:
            old_token_error = http_code(exc)
        check("resend revokes prior token", old_token_error == "token_revoked")
        check("resend new token is active", app.public_assessment_state(str(resend_attempt["attempt_id"]), new_token, start=False)["ok"])
        check("dry-run delivery is intentionally skipped", resent.get("delivery_status") == "intentionally_skipped")

        completed = complete(resend_attempt, new_token)
        check("last answer completes from frozen version", completed.get("completed") is True)
        try:
            answer_current(attempt_row(str(resend_attempt["attempt_id"])), new_token)
            completed_error = ""
        except Exception as exc:
            completed_error = http_code(exc)
        check("answer after completion rejected", completed_error == "attempt_completed")

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT immutable, assessment_version_id FROM assessment_scores WHERE attempt_id=%s",
                (resend_attempt["attempt_id"],),
            )
            score = dict(cur.fetchone())
            cur.execute(
                "SELECT immutable, assessment_version_id, report_json FROM assessment_reports WHERE attempt_id=%s",
                (resend_attempt["attempt_id"],),
            )
            report = dict(cur.fetchone())
            cur.execute(
                "SELECT raw_json, screening_status FROM applications WHERE app_key=%s AND company_code=%s",
                (apps["004"]["app_key"], COMPANY_A),
            )
            app_row = dict(cur.fetchone())
            application_raw = app_row.get("raw_json") or {}
            cur.execute(
                "SELECT COUNT(*) AS count FROM employment_offers WHERE app_key=%s AND company_code=%s",
                (apps["004"]["app_key"], COMPANY_A),
            )
            offer_count = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute(
                "SELECT COUNT(*) AS count FROM employees WHERE company_code=%s AND phone=%s",
                (COMPANY_A, apps["004"]["phone"]),
            )
            employee_count = int((cur.fetchone() or {}).get("count") or 0)

        check("score and report immutable", bool(score["immutable"] and report["immutable"]))
        check(
            "score and report pinned to same version",
            score["assessment_version_id"] == report["assessment_version_id"] == resend_attempt["assessment_version_id"],
        )
        check(
            "completion does not rewrite screening facet",
            application_raw.get("screening", {}).get("status") == "manual_complete"
            and app_row.get("screening_status") == "complete",
        )
        check("assessment completion creates no offer", offer_count == 0)
        check(
            "assessment completion cannot hire",
            employee_count == 0 and apps["004"]["status"] == "ready_for_review",
        )
        exact = app.fetch_dashboard_assessment_report_payload(COMPANY_A, str(resend_attempt["attempt_id"]))
        check(
            "exact attempt report opens",
            exact["attempt"]["attempt_id"] == str(resend_attempt["attempt_id"]) and exact["report"] == report["report_json"],
        )

        check(
            "incomplete assessment earns zero ranking points",
            app.row_assessment_signal({"assessment_status": "in_progress", "assessment_percent": 99})["score"] == 0,
        )
        check(
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
        check("ready_for_review included in assessment queue", apps["005"]["app_key"] in awaiting_keys)
        check("queue and action count are identical", awaiting["total"] == counts["assessment_pending"])

        # Mobile parity: capability surface ships for assessments module; authoritative
        # attempt state is proved via the same prehire projection mobile detail uses.
        caps = omobile.build_recruiting_workspace_capabilities(
            app,
            {
                "company_code": COMPANY_A,
                "permissions": ["prehire.read"],
            },
        )
        assess_cap = caps.get("assessments") or {}
        module_on = bool(app.company_has_module(COMPANY_A, "assessments"))
        check(
            "mobile assessments capability present",
            module_on
            and "assessments" in caps
            and assess_cap.get("advisory") is True
            and assess_cap.get("reason") != "module_disabled",
            assess_cap,
        )
        prehire = app.prehire_applications_query(
            company_code=COMPANY_A,
            status=None,
            position=None,
            search=apps["004"]["app_key"],
            limit=5,
            offset=0,
        )
        items = prehire.get("applications") or prehire.get("items") or []
        match = next((row for row in items if row.get("app_key") == apps["004"]["app_key"]), None)
        assess = (match or {}).get("assessment") or {}
        check(
            "mobile assessment state parity",
            assess.get("status") == "completed"
            and str(assess.get("attempt_id")) == str(resend_attempt["attempt_id"])
            and str(assess.get("assessment_version_id") or "") == str(resend_attempt["assessment_version_id"]),
        )

        # AI / authoring blocked with flag off
        context = authority_context(COMPANY_A)
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM assessment_items WHERE battery_key=%s", (app.ASSESSMENT_BATTERY_KEY,))
            live_before = int(cur.fetchone()["count"])
        try:
            app.dashboard_assessment_item_draft_create(
                app.AssessmentItemDraftRequest(
                    battery_key=app.ASSESSMENT_BATTERY_KEY,
                    section="logical_reasoning",
                    competency_tags=["analytical_thinking"],
                    difficulty="medium",
                    locale="en",
                    prompt_text="Prod proof must not publish this item.",
                    choices=[
                        {"key": "A", "text": "A"},
                        {"key": "B", "text": "B"},
                        {"key": "C", "text": "C"},
                        {"key": "D", "text": "D"},
                    ],
                    proposed_answer_key="B",
                    proposed_scoring={"type": "answer_key", "correct": 1, "incorrect": 0, "max_score": 1},
                    rationale="must stay blocked",
                    source_blueprint_id="blocked",
                    ai_model="none",
                    original_content_attested=True,
                ),
                context,
            )
            authoring_error = ""
        except Exception as exc:
            authoring_error = http_code(exc) or type(exc).__name__
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM assessment_items WHERE battery_key=%s", (app.ASSESSMENT_BATTERY_KEY,))
            live_after = int(cur.fetchone()["count"])
        check("AI authoring blocked when flag off", bool(authoring_error), authoring_error)
        check("live item bank count unchanged by AI attempt", live_before == live_after)

    except Exception as exc:
        check("suite_exception", False, f"{type(exc).__name__}: {exc}")
    finally:
        with app.db_connect() as conn, conn.cursor() as cur:
            purge(cur)
            conn.commit()

    cleanup = cleanup_counts()
    REPORT["cleanup"] = cleanup
    check("synthetic fixtures removed", all(v == 0 for v in cleanup.values()), cleanup)

    after = snapshot_real()
    REPORT["after"] = after
    for key in (
        "applications",
        "interviews",
        "offers",
        "employees",
        "assessment_scores",
        "outbound",
        "assessment_items",
        "item_content_digest",
        "scoring_rules_digest",
        "norms_digest",
    ):
        check(f"real {key} unchanged", before.get(key) == after.get(key), f"{before.get(key)} -> {after.get(key)}")

    # Attempt migration may have changed pin/expired counts vs pre-migrate before;
    # after proof, real attempt pin/expire should equal post-migrate before snapshot
    # captured at start of this script (post-migrate).
    check(
        "real assessment attempt pin inventory stable after proof",
        before["assessment_attempts"] == after["assessment_attempts"]
        and before["assessment_attempts_pinned"] == after["assessment_attempts_pinned"]
        and before["assessment_attempts_expired"] == after["assessment_attempts_expired"],
    )

    REPORT["passed"] = PASS
    REPORT["failed"] = FAIL
    REPORT["total"] = PASS + FAIL
    REPORT["real_delivery_sent"] = False
    REPORT["production_touched"] = True
    REPORT["synthetic_only"] = True
    print(json.dumps(REPORT, ensure_ascii=False, sort_keys=True, default=str))
    return 1 if FAIL or any(cleanup.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
