#!/usr/bin/env python3
"""Candidates C0/C1 guarded staging matrix.

Staging-only. Uses isolated company fixtures, dry_run delivery, deterministic cleanup.
Does not touch production.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT_PATH = Path(
    os.environ.get(
        "C01_STAGING_REPORT",
        "/opt/wathefni/staging/orchestrator/ops/reports/candidates-c01-staging-matrix.json",
    )
)

COMPANY = "C01STG"
OTHER = "C01XTO"
MARKER = "temporary_candidates_c01_staging"
ACTOR = "00000000-0000-4000-8000-c01c01c01c01"
PHONE = "965580010011"
PHONE_B = "965580010012"
PHONE_INTERVIEW = "965580010013"
PHONE_INTERVIEW_FAIL = "965580010014"
PHONE_HIRE_ROLLBACK = "965580010015"


class Matrix:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.fixtures: dict[str, Any] = {}

    def check(self, case: str, ok: bool, detail: Any = None) -> None:
        row = {"case": case, "result": "PASS" if ok else "FAIL", "detail": detail}
        self.rows.append(row)
        print(f"  {row['result']:4} {case}" + (f" :: {detail}" if (not ok and detail is not None) else ""))
        if not ok:
            raise AssertionError(f"{case}: {detail}")


def require_staging() -> None:
    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni_staging":
        raise SystemExit("refusing non-staging database")
    if (os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() not in {"dry_run", "dry-run", "dryrun"}:
        raise SystemExit("refusing non-dry_run delivery mode")


def cleanup(orch: Any, company: str = COMPANY) -> dict[str, int]:
    counts: dict[str, int] = {}
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            for table, sql in [
                ("hire_operations", "DELETE FROM hire_operations WHERE company_code=%s"),
                ("candidate_action_confirmations", "DELETE FROM candidate_action_confirmations WHERE company_code=%s"),
                ("application_lifecycle_events", "DELETE FROM application_lifecycle_events WHERE company_code=%s AND (metadata ? 'c01_marker' OR app_key LIKE 'c01-%%')"),
                ("candidate_interview_events", "DELETE FROM candidate_interview_events WHERE company_code=%s"),
                ("candidate_interviews", "DELETE FROM candidate_interviews WHERE company_code=%s"),
                ("hr_tasks", "DELETE FROM hr_tasks WHERE company_code=%s"),
                ("conversation_application_bindings", "DELETE FROM conversation_application_bindings WHERE company_code=%s"),
                ("pending_actions", "DELETE FROM pending_actions WHERE company_code=%s"),
                ("action_results", "DELETE FROM action_results WHERE company_code=%s"),
                ("outbound_delivery_events", "DELETE FROM outbound_delivery_events WHERE company_code=%s"),
                ("compliance_documents", "DELETE FROM compliance_documents WHERE company_code=%s"),
                ("employees", "DELETE FROM employees WHERE company_code=%s"),
                ("applications", "DELETE FROM applications WHERE company_code=%s"),
                ("positions", "DELETE FROM positions WHERE company_code=%s"),
                ("company_settings", "DELETE FROM company_settings WHERE company_code=%s"),
                ("company_modules", "DELETE FROM company_modules WHERE company_code=%s"),
                ("companies", "DELETE FROM companies WHERE company_code=%s AND metadata->>'c01_marker'=%s"),
                ("hr_admin_users", "DELETE FROM hr_admin_users WHERE company_code=%s") if False else ("noop", None),
            ]:
                if sql is None:
                    continue
                try:
                    cur.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",))
                    if not cur.fetchone()["t"] and table != "noop":
                        continue
                    if table == "noop":
                        continue
                    params = (company, MARKER) if table == "companies" else (company,)
                    cur.execute(sql, params)
                    counts[table] = cur.rowcount
                except Exception as exc:  # noqa: BLE001
                    counts[table] = -1
                    counts[f"{table}_error"] = str(exc)
            cur.execute("DELETE FROM candidate_documents WHERE app_key LIKE 'c01-%'")
            counts["candidate_documents"] = cur.rowcount
            cur.execute("DELETE FROM onboarding_items WHERE employee_key LIKE %s", (f"{company}-%",))
            counts["onboarding_items"] = cur.rowcount
            cur.execute(
                "DELETE FROM candidates WHERE phone = ANY(%s)",
                ([PHONE, PHONE_B, PHONE_INTERVIEW, PHONE_INTERVIEW_FAIL, PHONE_HIRE_ROLLBACK],),
            )
            counts["candidates"] = cur.rowcount
            # also other company probe
            cur.execute("DELETE FROM applications WHERE company_code=%s", (OTHER,))
            counts["other_apps"] = cur.rowcount
        conn.commit()
    return counts


def seed_companies(orch: Any) -> None:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s::jsonb,%s::jsonb,now(),now())
                    ON CONFLICT (company_code) DO UPDATE
                      SET metadata=companies.metadata || EXCLUDED.metadata,
                          raw_json=companies.raw_json || EXCLUDED.raw_json,
                          updated_at=now()
                    """,
                    (
                        company,
                        f"Candidates C0/C1 Staging {company}",
                        json.dumps({"c01_marker": MARKER, "smoke": True}),
                        json.dumps({"c01_marker": MARKER, "smoke": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules
                      (company_code, module_key, enabled, source, updated_at)
                    VALUES (%s,'pre_hiring',true,'c01_staging_matrix',now())
                    ON CONFLICT (company_code, module_key) DO UPDATE
                      SET enabled=true, source=EXCLUDED.source, updated_at=now()
                    """,
                    (company,),
                )
        conn.commit()


def seed_app(orch: Any, *, app_key: str, status: str, phone: str = PHONE, position: str = "C01_ROLE_A") -> dict[str, Any]:
    import recruiting_lifecycle as rl

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            rl.ensure_lifecycle_schema(cur)
            cur.execute(
                """
                INSERT INTO candidates (phone, name, email, current_status, active_company_code, data_source, raw_json)
                VALUES (%s,%s,%s,%s,%s,'c01_staging',%s::jsonb)
                ON CONFLICT (phone) DO UPDATE
                  SET name=EXCLUDED.name, active_company_code=EXCLUDED.active_company_code, updated_at=now()
                """,
                (phone, f"C01 Candidate {phone[-4:]}", f"{phone}@example.test", status, COMPANY, json.dumps({"c01_marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO positions (company_code, position_code, title, status, vacancies, raw_json)
                VALUES (%s,%s,%s,'open',3,%s::jsonb)
                ON CONFLICT (company_code, position_code) DO UPDATE SET title=EXCLUDED.title
                """,
                (COMPANY, position, f"C01 {position}", json.dumps({"c01_marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO applications (
                  app_key, company_code, phone, position_code, position_title, status, current_step,
                  cv_received, data_source, ingested_at, updated_at, raw_json, lifecycle_version
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,true,'c01_staging',now(),now(),%s::jsonb,0)
                ON CONFLICT (app_key) DO UPDATE
                  SET status=EXCLUDED.status, current_step=EXCLUDED.current_step,
                      position_code=EXCLUDED.position_code, lifecycle_version=0, updated_at=now()
                RETURNING *
                """,
                (
                    app_key,
                    COMPANY,
                    phone,
                    position,
                    f"C01 {position}",
                    status,
                    status,
                    json.dumps({"c01_marker": MARKER, "smoke": True}),
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return row


def main() -> int:
    require_staging()
    os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")
    import action_registry as registry
    import app as orch
    import hire_operations as hire
    import recruiting_lifecycle as rl

    orch.assert_runtime_environment_binding()
    matrix = Matrix()
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "marker": MARKER,
        "company": COMPANY,
    }

    # Identity
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_database() AS db, current_user AS db_user,
                       current_setting('wathefni.environment_marker', true) AS marker
                """
            )
            report["identity"] = dict(cur.fetchone())
    matrix.check("staging_db_identity", report["identity"]["db"] == "wathefni_staging", report["identity"])

    cleanup(orch)
    cleanup(orch, OTHER)
    seed_companies(orch)

    try:
        app_key = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=app_key, status="ready_for_review")
        matrix.fixtures["app_key"] = app_key

        # Tenant / confirmation
        missing = rl.transition_application(
            orch, app_key=app_key, company_code="", to_stage="shortlisted", trigger="dashboard_shortlist"
        )
        matrix.check("missing_tenant_fails_closed", missing.get("error") == "tenant_scope_required", missing)

        cross = rl.transition_application(
            orch,
            app_key=app_key,
            company_code=OTHER,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            human_confirmed=True,
            confirmation_id="x",
            confirmation_token="x",
            permissions={"candidate.manage"},
        )
        matrix.check("cross_tenant_denied", cross.get("error") in {"application_not_found", "tenant_mismatch"}, cross)

        omitted = rl.transition_application(
            orch,
            app_key=app_key,
            company_code=COMPANY,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            permissions={"candidate.manage"},
        )
        matrix.check("human_confirmed_omitted_denied", omitted.get("error") == "confirmation_required", omitted)

        ai = rl.transition_application(
            orch,
            app_key=app_key,
            company_code=COMPANY,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            actor_type="ai",
            human_confirmed=True,
            confirmation_id="made-up",
            confirmation_token="made-up",
            permissions={"candidate.manage"},
        )
        matrix.check("ai_cannot_manufacture_confirmation", ai.get("error") == "ai_cannot_mutate_stage", ai)

        mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=app_key,
            action="shortlist",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload={},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.manage"},
        )
        matrix.check("mint_confirmation", mint.get("ok") is True, mint)
        conf = mint["confirmation"]

        first = rl.transition_application(
            orch,
            app_key=app_key,
            company_code=COMPANY,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            expected_from_stage="ready_for_review",
            expected_version=0,
            actor_type="human",
            actor_user_id=ACTOR,
            channel="web",
            confirmation_id=conf["confirmation_id"],
            confirmation_token=conf["confirmation_token"],
            confirmation_action="shortlist",
            confirmation_payload={},
            human_confirmed=True,
            permissions={"candidate.manage"},
        )
        matrix.check("valid_confirmation_succeeds_once", first.get("ok") is True, first)

        second = rl.transition_application(
            orch,
            app_key=app_key,
            company_code=COMPANY,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            actor_type="human",
            actor_user_id=ACTOR,
            confirmation_id=conf["confirmation_id"],
            confirmation_token=conf["confirmation_token"],
            confirmation_action="shortlist",
            confirmation_payload={},
            human_confirmed=True,
            permissions={"candidate.manage"},
        )
        matrix.check("confirmation_single_use", second.get("error") == "confirmation_already_used", second)

        # Reset to ready for more confirmation negative tests
        reject_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=reject_app, status="ready_for_review", phone=PHONE_B, position="C01_ROLE_B")

        expired_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=reject_app,
            action="reject",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload={"reason_code": "not_selected", "note": "staging"},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        matrix.check("mint_reject_confirmation", expired_mint.get("ok") is True, expired_mint)
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE candidate_action_confirmations SET expires_at=%s WHERE confirmation_id=%s",
                    (datetime.now(timezone.utc) - timedelta(seconds=5), expired_mint["confirmation"]["confirmation_id"]),
                )
            conn.commit()
        expired = rl.transition_application(
            orch,
            app_key=reject_app,
            company_code=COMPANY,
            to_stage="rejected",
            trigger="dashboard_reject",
            expected_from_stage="ready_for_review",
            expected_version=0,
            actor_type="human",
            actor_user_id=ACTOR,
            confirmation_id=expired_mint["confirmation"]["confirmation_id"],
            confirmation_token=expired_mint["confirmation"]["confirmation_token"],
            confirmation_action="reject",
            confirmation_payload={"reason_code": "not_selected", "note": "staging"},
            human_confirmed=True,
            permissions={"candidate.decide"},
            metadata={"reason_code": "not_selected", "note": "staging"},
        )
        matrix.check("expired_confirmation_denied", expired.get("error") == "confirmation_expired", expired)

        changed_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=reject_app,
            action="reject",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload={"reason_code": "not_selected"},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        changed = rl.transition_application(
            orch,
            app_key=reject_app,
            company_code=COMPANY,
            to_stage="rejected",
            trigger="dashboard_reject",
            expected_from_stage="ready_for_review",
            expected_version=0,
            actor_type="human",
            actor_user_id=ACTOR,
            confirmation_id=changed_mint["confirmation"]["confirmation_id"],
            confirmation_token=changed_mint["confirmation"]["confirmation_token"],
            confirmation_action="reject",
            confirmation_payload={"reason_code": "not_selected", "note": "changed"},
            human_confirmed=True,
            permissions={"candidate.decide"},
            metadata={"reason_code": "not_selected", "note": "changed"},
        )
        matrix.check("changed_payload_denied", changed.get("error") == "confirmation_payload_changed", changed)

        stale_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=reject_app,
            action="reject",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload={"reason_code": "not_selected"},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        # Force version bump via canonical noop-safe path: shortlist first with new confirmation then try stale reject
        # Simpler: direct schema bump of lifecycle_version through canonical shortlist on a fresh app, then mutate reject_app version via SQL with authority marker
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('wathefni.lifecycle_authority', 'canonical', true)")
                cur.execute(
                    "UPDATE applications SET lifecycle_version=lifecycle_version+1 WHERE company_code=%s AND app_key=%s RETURNING lifecycle_version",
                    (COMPANY, reject_app),
                )
                ver = int(cur.fetchone()["lifecycle_version"])
            conn.commit()
        stale = rl.transition_application(
            orch,
            app_key=reject_app,
            company_code=COMPANY,
            to_stage="rejected",
            trigger="dashboard_reject",
            expected_from_stage="ready_for_review",
            expected_version=0,
            actor_type="human",
            actor_user_id=ACTOR,
            confirmation_id=stale_mint["confirmation"]["confirmation_id"],
            confirmation_token=stale_mint["confirmation"]["confirmation_token"],
            confirmation_action="reject",
            confirmation_payload={"reason_code": "not_selected"},
            human_confirmed=True,
            permissions={"candidate.decide"},
            metadata={"reason_code": "not_selected"},
        )
        matrix.check("stale_version_denied", stale.get("error") in {"stale_confirmation", "stale_state"}, {"result": stale, "ver": ver})

        revoked_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=reject_app,
            action="reject",
            observed_stage="ready_for_review",
            observed_version=ver,
            target_payload={"reason_code": "not_selected"},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        # Fix observed stage/version on confirmation vs app: re-read app status
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, lifecycle_version FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, reject_app))
                cur_app = dict(cur.fetchone())
        # Remint against actual state
        revoked_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=reject_app,
            action="reject",
            observed_stage=str(cur_app["status"]),
            observed_version=int(cur_app["lifecycle_version"]),
            target_payload={"reason_code": "not_selected"},
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        matrix.check("remint_after_version_bump", revoked_mint.get("ok") is True, revoked_mint)
        revoked = rl.transition_application(
            orch,
            app_key=reject_app,
            company_code=COMPANY,
            to_stage="rejected",
            trigger="dashboard_reject",
            expected_from_stage=str(cur_app["status"]),
            expected_version=int(cur_app["lifecycle_version"]),
            actor_type="human",
            actor_user_id=ACTOR,
            confirmation_id=revoked_mint["confirmation"]["confirmation_id"],
            confirmation_token=revoked_mint["confirmation"]["confirmation_token"],
            confirmation_action="reject",
            confirmation_payload={"reason_code": "not_selected"},
            human_confirmed=True,
            permissions=set(),
            metadata={"reason_code": "not_selected"},
        )
        matrix.check("permission_revoked_denied", revoked.get("error") == "permission_denied", revoked)

        # Direct write blocked
        blocked = False
        err = None
        try:
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE applications SET status='rejected' WHERE company_code=%s AND app_key=%s",
                        (COMPANY, reject_app),
                    )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            blocked = "application_lifecycle_direct_write_blocked" in str(exc)
            err = str(exc)
            with orch.db_connect() as conn:
                conn.rollback()
        matrix.check("direct_status_write_blocked", blocked, err)

        # Trigger present
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tgname FROM pg_trigger
                    WHERE tgname='applications_lifecycle_authority_guard' AND NOT tgisinternal
                    """
                )
                matrix.check("lifecycle_trigger_installed", cur.fetchone() is not None)

        # CV transitions
        cv_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=cv_app, status="awaiting_cv", phone=PHONE, position="C01_ROLE_CV")
        r1 = rl.mark_cv_received(orch, application={"app_key": cv_app, "company_code": COMPANY, "status": "awaiting_cv"})
        matrix.check("cv_awaiting_to_processing", r1.get("ok") is True and r1.get("to_stage") == "cv_processing", r1)
        r1b = rl.mark_cv_received(orch, application={"app_key": cv_app, "company_code": COMPANY, "status": "cv_processing"})
        matrix.check("cv_received_idempotent", r1b.get("ok") is True and (r1b.get("idempotent") or r1b.get("skipped")), r1b)
        r2 = rl.mark_cv_ready_for_review(
            orch,
            application={"app_key": cv_app, "company_code": COMPANY, "status": "cv_processing"},
            document_id="doc-c01-1",
        )
        matrix.check("cv_processing_to_ready", r2.get("ok") is True and r2.get("to_stage") == "ready_for_review", r2)
        fail = rl.transition_application(
            orch,
            app_key=cv_app,
            company_code=COMPANY,
            to_stage="awaiting_cv",
            trigger="cv_processing_failed",
            actor_type="system",
            channel="system",
            human_confirmed=False,
            idempotency_key="cv-failed:c01:force",
            expected_from_stage="ready_for_review",
        )
        # may fail transition_not_allowed from ready->awaiting; instead test from processing
        cv_fail_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=cv_fail_app, status="cv_processing", phone=PHONE, position="C01_ROLE_CVF")
        fail2 = rl.transition_application(
            orch,
            app_key=cv_fail_app,
            company_code=COMPANY,
            to_stage="awaiting_cv",
            trigger="cv_processing_failed",
            actor_type="system",
            channel="system",
            human_confirmed=False,
            idempotency_key=f"cv-failed:{COMPANY}:{cv_fail_app}:docx",
        )
        matrix.check("cv_failure_returns_awaiting", fail2.get("ok") is True and fail2.get("to_stage") == "awaiting_cv", fail2)

        # Interview preparation, calendar failure, successful scheduling,
        # rescheduling, and cancellation all preserve canonical lifecycle truth.
        interview_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(
            orch,
            app_key=interview_app,
            status="ready_for_review",
            phone=PHONE_INTERVIEW,
            position="C01_ROLE_INTERVIEW",
        )
        interview_payload = {"interview_time": "2026-08-10T10:00:00+03:00"}
        interview_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=interview_app,
            action="schedule_interview",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload=interview_payload,
            actor_user_id=ACTOR,
            actor_phone="96599338566",
            actor_type="human",
            channel="web",
            permissions={"interview.manage"},
        )
        matrix.check("interview_confirmation_minted", interview_mint.get("ok") is True, interview_mint)

        request = type(
            "C01Request",
            (),
            {
                "metadata": {
                    "company_code": COMPANY,
                    "dashboard": True,
                    "actor_user_id": ACTOR,
                    "permissions": ["interview.manage", "prehire.read"],
                },
                "sender_phone": "96599338566",
                "sender_role": "hr_admin",
                "account_id": COMPANY,
            },
        )()
        schedule_action = {
            "action_type": "schedule_interview",
            "app_key": interview_app,
            "interview_time": interview_payload["interview_time"],
            "human_confirmed": True,
            "actor_user_id": ACTOR,
            "expected_from_stage": "ready_for_review",
            "expected_version": 0,
            "confirmation_id": interview_mint["confirmation"]["confirmation_id"],
            "confirmation_token": interview_mint["confirmation"]["confirmation_token"],
            "confirmation_payload": interview_payload,
            "idempotency_key": f"c01-interview:{interview_app}",
        }
        original_run_gog = orch.run_gog
        company_token = orch.set_active_company_code(COMPANY)
        try:
            orch.run_gog = lambda *_args, **_kwargs: {
                "ok": True,
                "event": {
                    "id": f"c01-calendar-{interview_app}",
                    "conferenceData": {
                        "entryPoints": [
                            {"entryPointType": "video", "uri": "https://meet.google.com/c01-staging"}
                        ]
                    },
                },
            }
            scheduled = registry.execute(
                "schedule_interview",
                registry.ExecutionContext(
                    request=request,
                    action=schedule_action,
                    state={},
                    graph_state={},
                    intent={},
                    legacy=orch,
                ),
            )
        finally:
            orch.run_gog = original_run_gog
            orch.reset_active_company_code(company_token)
        matrix.check("confirmed_schedule_succeeds", scheduled.get("success") is True, scheduled)
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM applications WHERE company_code=%s AND app_key=%s",
                    (COMPANY, interview_app),
                )
                scheduled_stage = cur.fetchone()["status"]
                cur.execute(
                    "SELECT * FROM candidate_interviews WHERE company_code=%s AND app_key=%s ORDER BY created_at DESC LIMIT 1",
                    (COMPANY, interview_app),
                )
                interview_row = dict(cur.fetchone() or {})
        matrix.check(
            "successful_schedule_advances_canonical_stage",
            scheduled_stage == "interview" and interview_row.get("status") == "scheduled",
            {"stage": scheduled_stage, "interview": interview_row},
        )

        failed_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(
            orch,
            app_key=failed_app,
            status="ready_for_review",
            phone=PHONE_INTERVIEW_FAIL,
            position="C01_ROLE_INTERVIEW_FAIL",
        )
        plan_ctx = registry.ExecutionContext(
            request=request,
            action={
                "action_type": "execute_candidate_workflow",
                "app_key": failed_app,
                "workflow_goal": "schedule an interview",
                "interview_time": interview_payload["interview_time"],
            },
            state={},
            graph_state={},
            intent={},
            legacy=orch,
        )
        company_token = orch.set_active_company_code(COMPANY)
        try:
            plan = registry._candidate_workflow_plan(plan_ctx)
        finally:
            orch.reset_active_company_code(company_token)
        plan_app = orch.find_application_by_key(failed_app, company_code=COMPANY) or {}
        matrix.check(
            "interview_preparation_does_not_advance",
            plan.get("status") in {"ready", "needs_clarification"} and plan_app.get("status") == "ready_for_review",
            {"plan": plan, "stage": plan_app.get("status")},
        )
        failed_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=failed_app,
            action="schedule_interview",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload=interview_payload,
            actor_user_id=ACTOR,
            actor_phone="96599338566",
            actor_type="human",
            channel="web",
            permissions={"interview.manage"},
        )
        original_run_gog = orch.run_gog
        company_token = orch.set_active_company_code(COMPANY)
        try:
            orch.run_gog = lambda *_args, **_kwargs: {"ok": False, "error": "calendar_unavailable"}
            failed_schedule = registry.execute(
                "schedule_interview",
                registry.ExecutionContext(
                    request=request,
                    action={
                        "action_type": "schedule_interview",
                        "app_key": failed_app,
                        "interview_time": interview_payload["interview_time"],
                        "human_confirmed": True,
                        "actor_user_id": ACTOR,
                        "expected_from_stage": "ready_for_review",
                        "expected_version": 0,
                        "confirmation_id": failed_mint["confirmation"]["confirmation_id"],
                        "confirmation_token": failed_mint["confirmation"]["confirmation_token"],
                        "confirmation_payload": interview_payload,
                        "idempotency_key": f"c01-interview-fail:{failed_app}",
                    },
                    state={},
                    graph_state={},
                    intent={},
                    legacy=orch,
                ),
            )
        finally:
            orch.run_gog = original_run_gog
            orch.reset_active_company_code(company_token)
        failed_stage = orch.find_application_by_key(failed_app, company_code=COMPANY) or {}
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM candidate_interviews WHERE company_code=%s AND app_key=%s",
                    (COMPANY, failed_app),
                )
                failed_interviews = int(cur.fetchone()["n"])
        matrix.check(
            "calendar_failure_does_not_advance",
            failed_schedule.get("success") is False
            and failed_stage.get("status") == "ready_for_review"
            and failed_interviews == 0,
            {"result": failed_schedule, "stage": failed_stage.get("status"), "interviews": failed_interviews},
        )

        interview_context = {
            "company_code": COMPANY,
            "hr_phone": "96599338566",
            "hr_user": {"phone": "96599338566", "role": "owner"},
            "actor_user_id": ACTOR,
            "permissions": ["interview.manage", "prehire.read"],
        }
        rescheduled = orch.dashboard_prehire_interview_update(
            str(interview_row["interview_id"]),
            orch.DashboardInterviewStateRequest(status="rescheduled"),
            context=interview_context,
        )
        rescheduled_app = orch.find_application_by_key(interview_app, company_code=COMPANY) or {}
        matrix.check(
            "reschedule_remains_in_interview_stage",
            rescheduled["interview"]["status"] == "rescheduled"
            and rescheduled_app.get("status") == "interview",
            {"interview": rescheduled["interview"], "stage": rescheduled_app.get("status")},
        )
        cancelled = orch.dashboard_prehire_interview_update(
            str(interview_row["interview_id"]),
            orch.DashboardInterviewStateRequest(status="cancelled"),
            context=interview_context,
        )
        cancelled_app = orch.find_application_by_key(interview_app, company_code=COMPANY) or {}
        matrix.check(
            "cancellation_clears_false_interview_stage",
            cancelled["interview"]["status"] == "cancelled"
            and cancelled_app.get("status") == "shortlisted",
            {"interview": cancelled["interview"], "stage": cancelled_app.get("status")},
        )

        # Hiring atomicity
        hire_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=hire_app, status="shortlisted", phone=PHONE, position="C01_ROLE_HIRE")
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                hire.ensure_hire_schema(cur)
            conn.commit()
        prep = hire.prepare_hire_operation(
            orch,
            company_code=COMPANY,
            app_key=hire_app,
            idempotency_key=f"c01-hire:{hire_app}",
            expected_from_stage="shortlisted",
            expected_version=0,
            actor_user_id=ACTOR,
            actor_phone=None,
            channel="web",
            structured_reason={"hire_reference": f"c01-hire:{hire_app}"},
        )
        matrix.check("hire_prepare", prep.get("ok") is True, prep)
        # Mint hire confirmation
        hire_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=hire_app,
            action="hire",
            observed_stage="shortlisted",
            observed_version=0,
            target_payload={
                "hire_reference": f"c01-hire:{hire_app}",
                "hiring_reference": prep["operation"]["operation_id"],
                "operation_id": prep["operation"]["operation_id"],
            },
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        matrix.check("hire_mint", hire_mint.get("ok") is True, hire_mint)
        executed = hire.execute_hire_operation(
            orch,
            operation_id=prep["operation"]["operation_id"],
            confirmation_id=hire_mint["confirmation"]["confirmation_id"],
            confirmation_token=hire_mint["confirmation"]["confirmation_token"],
            permissions={"candidate.decide"},
        )
        matrix.check("hire_execute_atomic", executed.get("ok") is True, executed)
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, hire_app))
                st = cur.fetchone()["status"]
                cur.execute("SELECT count(*) AS n FROM employees WHERE company_code=%s AND app_key=%s", (COMPANY, hire_app))
                emp_n = int(cur.fetchone()["n"])
        matrix.check("hire_has_employee_link", st == "hired" and emp_n == 1, {"status": st, "employees": emp_n})
        replay = hire.execute_hire_operation(
            orch,
            operation_id=prep["operation"]["operation_id"],
            confirmation_id=hire_mint["confirmation"]["confirmation_id"],
            confirmation_token=hire_mint["confirmation"]["confirmation_token"],
            permissions={"candidate.decide"},
        )
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM employees WHERE company_code=%s AND app_key=%s", (COMPANY, hire_app))
                emp_n2 = int(cur.fetchone()["n"])
        matrix.check("hire_replay_no_duplicate_employee", emp_n2 == 1 and (replay.get("ok") or replay.get("error")), {"employees": emp_n2, "replay": replay})

        rollback_app = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(
            orch,
            app_key=rollback_app,
            status="shortlisted",
            phone=PHONE_HIRE_ROLLBACK,
            position="C01_ROLE_HIRE_ROLLBACK",
        )
        rollback_prep = hire.prepare_hire_operation(
            orch,
            company_code=COMPANY,
            app_key=rollback_app,
            idempotency_key=f"c01-hire-rollback:{rollback_app}",
            expected_from_stage="shortlisted",
            expected_version=0,
            actor_user_id=ACTOR,
            actor_phone=None,
            channel="web",
            structured_reason={"hire_reference": f"c01-hire-rollback:{rollback_app}"},
        )
        rollback_payload = {
            "hire_reference": f"c01-hire-rollback:{rollback_app}",
            "hiring_reference": rollback_prep["operation"]["operation_id"],
            "operation_id": rollback_prep["operation"]["operation_id"],
        }
        rollback_mint = rl.mint_candidate_action_confirmation(
            orch,
            company_code=COMPANY,
            app_key=rollback_app,
            action="hire",
            observed_stage="shortlisted",
            observed_version=0,
            target_payload=rollback_payload,
            actor_user_id=ACTOR,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        original_compliance_seed = orch._seed_employee_compliance_documents

        def _raise_before_commit(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("c01_forced_precommit_failure")

        try:
            orch._seed_employee_compliance_documents = _raise_before_commit
            rollback_result = hire.execute_hire_operation(
                orch,
                operation_id=rollback_prep["operation"]["operation_id"],
                confirmation_id=rollback_mint["confirmation"]["confirmation_id"],
                confirmation_token=rollback_mint["confirmation"]["confirmation_token"],
                permissions={"candidate.decide"},
            )
        finally:
            orch._seed_employee_compliance_documents = original_compliance_seed
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM applications WHERE company_code=%s AND app_key=%s",
                    (COMPANY, rollback_app),
                )
                rollback_stage = cur.fetchone()["status"]
                cur.execute(
                    "SELECT count(*) AS n FROM employees WHERE company_code=%s AND app_key=%s",
                    (COMPANY, rollback_app),
                )
                rollback_employees = int(cur.fetchone()["n"])
                cur.execute(
                    "SELECT count(*) AS n FROM application_lifecycle_events WHERE company_code=%s AND app_key=%s AND to_stage='hired'",
                    (COMPANY, rollback_app),
                )
                rollback_hire_events = int(cur.fetchone()["n"])
        matrix.check(
            "precommit_failure_leaves_no_half_hire",
            rollback_result.get("ok") is False
            and rollback_stage == "shortlisted"
            and rollback_employees == 0
            and rollback_hire_events == 0,
            {
                "result": rollback_result,
                "stage": rollback_stage,
                "employees": rollback_employees,
                "hire_events": rollback_hire_events,
            },
        )

        # Duplicate protection / collision gates
        collisions = rl.active_same_role_collisions(orch)
        matrix.check("active_same_role_collisions_clean", collisions == [], collisions)
        install = rl.install_active_same_role_constraint(orch)
        matrix.check("install_active_same_role_constraint", install.get("ok") is True, install)
        emp_install = hire.install_employee_link_constraint(orch)
        matrix.check("install_employee_link_constraint", emp_install.get("ok") is True, emp_install)

        # Same-role active duplicate blocked
        dup_a = f"c01-{uuid.uuid4().hex[:10]}"
        dup_b = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=dup_a, status="ready_for_review", phone=PHONE_B, position="C01_ROLE_DUP")
        blocked_dup = False
        dup_err = None
        try:
            seed_app(orch, app_key=dup_b, status="shortlisted", phone=PHONE_B, position="C01_ROLE_DUP")
        except Exception as exc:  # noqa: BLE001
            blocked_dup = "applications_one_active_same_role_uq" in str(exc) or "unique" in str(exc).lower()
            dup_err = str(exc)
            with orch.db_connect() as conn:
                conn.rollback()
        matrix.check("active_same_role_duplicate_blocked", blocked_dup, dup_err)

        # Different role allowed
        other_role = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=other_role, status="ready_for_review", phone=PHONE_B, position="C01_ROLE_OTHER")
        matrix.check("different_role_allowed", True)

        # Terminal then reapply allowed
        term = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=term, status="rejected", phone=PHONE_B, position="C01_ROLE_REAPP")
        reapp = f"c01-{uuid.uuid4().hex[:10]}"
        seed_app(orch, app_key=reapp, status="awaiting_cv", phone=PHONE_B, position="C01_ROLE_REAPP")
        matrix.check("terminal_then_reapply_allowed", True)

        # Half-hire inventory remains clean
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS n FROM applications a
                    LEFT JOIN employees e ON e.company_code=a.company_code AND e.app_key=a.app_key
                    WHERE lower(COALESCE(a.status,''))='hired' AND e.employee_key IS NULL
                    """
                )
                half = int(cur.fetchone()["n"])
        matrix.check("no_hired_without_employee", half == 0, half)

        # EN/AR confirmation copy present in the exact dashboard artifact on staging.
        dash = Path("/opt/wathefni/staging/dashboard-dist")
        text = "\n".join(
            asset.read_text(encoding="utf-8")
            for asset in sorted((dash / "assets").glob("*.js"))
        )
        matrix.check("bilingual_hire_copy", "Hire this candidate?" in text and "توظيف هذا المرشح؟" in text)
        matrix.check("bilingual_reject_copy", "Reject this candidate?" in text and "رفض هذا المرشح؟" in text)

        # Interview drift report callable
        drift = rl.interview_lifecycle_consistency_report(orch, company_code=COMPANY)
        matrix.check("interview_drift_report", drift.get("ok") is True, drift)

        report["actions"] = rl.allowed_actions_for_stage(
            "ready_for_review",
            {"candidate.manage", "candidate.decide", "interview.manage"},
        )
        matrix.check(
            "ready_for_review_actions_parity_basis",
            set(report["actions"]) >= {"shortlist", "reject", "schedule_interview"},
            report["actions"],
        )

    except Exception as exc:  # noqa: BLE001
        report["fatal"] = {"error": str(exc), "traceback": traceback.format_exc()}
        print("FATAL", exc)
    finally:
        report["cleanup"] = {
            COMPANY: cleanup(orch, COMPANY),
            OTHER: cleanup(orch, OTHER),
        }
        report["matrix"] = matrix.rows
        report["summary"] = {
            "passed": sum(1 for r in matrix.rows if r["result"] == "PASS"),
            "failed": sum(1 for r in matrix.rows if r["result"] == "FAIL"),
            "total": len(matrix.rows),
        }
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"summary": report["summary"], "report": str(REPORT_PATH)}, indent=2))
    return 0 if report["summary"]["failed"] == 0 and "fatal" not in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
