#!/usr/bin/env python3
"""Guarded Jobs Phase 2 production qualification and deterministic cleanup.

Runs against the production database only after an explicit acknowledgement.
All candidate/application rows use a unique marker and are deleted in finally.
The dedicated J2P2_PROD_TEST position is retained for owner testing.
Outbound delivery is forced to dry_run inside this verifier; live WhatsApp health
is validated separately through the deployed service and OpenClaw route.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as orch
import jobs_phase2_stage_b as stage_b
import prehire_jobs as jobs

COMPANY = "WATHEFNI"
ACTOR = "00000000-0000-4000-8000-000000000001"
OWNER_JOB = "J2P2_PROD_TEST"
OWNER_APPLY = "APPLY-WATHEFNI-J2P2_PROD_TEST"
MARKER = f"J2P2PROD-{uuid.uuid4().hex[:8].upper()}"
ACCOUNT = "j2p2-production-qualification"
PHONES = ["96550971001", "96550971002", "96550971003"]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def require_production() -> None:
    if os.environ.get("WATHEFNI_JOBS_PHASE2_PRODUCTION_ACK") != "production:wathefni:jobs-phase2":
        raise SystemExit("REFUSE: missing production acknowledgement")
    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni":
        raise SystemExit("REFUSE: expected production database name wathefni")
    identity = orch.assert_runtime_environment_binding()
    if identity.application_environment != "production" or identity.database_environment != "production":
        raise SystemExit("REFUSE: runtime/database identity is not production")
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute("select current_database() as d")
        if cur.fetchone()["d"] != "wathefni":
            raise SystemExit("REFUSE: current_database is not wathefni")


def payload(code: str, *, title: str | None = None, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "position_code": code,
        "title": title or f"Jobs Phase 2 Production Test {MARKER}",
        "title_en": title or f"Jobs Phase 2 Production Test {MARKER}",
        "title_ar": f"اختبار وظائف المرحلة الثانية {MARKER}",
        "short_summary_en": f"{MARKER} controlled production qualification role.",
        "short_summary_ar": f"{MARKER} وظيفة تأهيل إنتاجية محكومة.",
        "description": f"{MARKER} controlled Jobs Phase 2 production verification role.",
        "requirements_en": ["Controlled Jobs Phase 2 production verification"],
        "requirements_ar": ["اختبار محكوم للمرحلة الثانية"],
        "approve_content_en": True,
        "approve_content_ar": True,
        "location": "Kuwait City",
        "work_arrangement": "onsite",
        "employment_type": "full_time",
        "vacancies": 10,
        "visibility": "public",
        "salary_visibility": "hr_only",
        "salary_min": 400,
        "salary_max": 600,
        "currency": "KD",
    }
    item.update(overrides)
    return item


def create_job(code: str, *, open_job: bool = True, **overrides: Any) -> dict[str, Any]:
    draft = jobs.create_job(
        company=COMPANY,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        payload=payload(code, **overrides),
        as_draft=True,
    )
    if not open_job:
        return draft
    return jobs.transition_job(
        company=COMPANY,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        to_status="open",
        expected_version=draft.get("version"),
    )


def ensure_owner_job() -> dict[str, Any]:
    try:
        existing = jobs.get_job(
            company=COMPANY,
            position_code=OWNER_JOB,
            db_connect=orch.db_connect,
        )
    except jobs.JobsError:
        existing = None
    if existing:
        if existing.get("status") != "open":
            existing = jobs.transition_job(
                company=COMPANY,
                position_code=OWNER_JOB,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="open",
                expected_version=existing.get("version"),
            )
        return existing
    return create_job(
        OWNER_JOB,
        title="Wathefni Jobs Phase 2 Production Test",
        vacancies=25,
    )


def request(
    *,
    phone: str,
    conversation: str,
    text: str,
    message_id: str,
    media: dict[str, Any] | None = None,
    source_ref_token: str | None = None,
) -> Any:
    return orch.WhatsAppTurnRequest(
        account_id=ACCOUNT,
        conversation_id=conversation,
        sender_phone=phone,
        sender_role="candidate",
        raw_text=text,
        media=media,
        metadata={
            "provider": "jobs-phase2-production-qualification",
            "provider_message_id": message_id,
            "message_id": message_id,
            "source_channel": "whatsapp",
            "source_ref_token": source_ref_token,
            "source_campaign": MARKER,
            "locale": "en",
        },
    )


def turn(**kwargs: Any) -> dict[str, Any]:
    raw = orch.handle_non_hr_conversational_turn(request(**kwargs)) or {}
    nested = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    return {**raw, **nested}


def app_count(phone: str, position: str | None = None) -> int:
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n
            FROM applications
            WHERE phone=%s
              AND (%s IS NULL OR position_code=%s)
            """,
            (phone, position, position),
        )
        return int(cur.fetchone()["n"])


def make_docx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Jobs Phase 2 Production Candidate",
        "Email: phase2-production@example.invalid",
        "Phone: +965 50971001",
        "Professional experience in operations, recruiting, reporting, and compliance.",
        "Skills: Excel, SQL, stakeholder communication.",
    ]
    paragraphs = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{line}</w:t></w:r></w:p>'
        for line in lines
    )
    document = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{paragraphs}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{PKG}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr("word/_rels/document.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="{PKG}"></Relationships>')
        archive.writestr("word/document.xml", document)
    return path


def cleanup(codes: list[str], app_keys: list[str], paths: list[str]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    with orch.db_connect() as conn, conn.cursor() as cur:
        if app_keys:
            for table, key in (
                ("hr_tasks", "metadata->>'app_key'"),
                ("application_lifecycle_events", "app_key"),
                ("candidate_documents", "app_key"),
                ("file_registry", "subject_key"),
            ):
                cur.execute(f"DELETE FROM {table} WHERE {key}=ANY(%s)", (app_keys,))
                deleted[table] = cur.rowcount
        cur.execute("DELETE FROM conversation_application_bindings WHERE phone=ANY(%s)", (PHONES,))
        deleted["bindings"] = cur.rowcount
        cur.execute("DELETE FROM candidate_pending_media WHERE phone=ANY(%s)", (PHONES,))
        deleted["pending_media"] = cur.rowcount
        cur.execute("DELETE FROM candidate_job_contexts WHERE phone=ANY(%s)", (PHONES,))
        deleted["contexts"] = cur.rowcount
        cur.execute("DELETE FROM whatsapp_inbound_messages WHERE provider='jobs-phase2-production-qualification'")
        deleted["inbound"] = cur.rowcount
        cur.execute("DELETE FROM applications WHERE phone=ANY(%s)", (PHONES,))
        deleted["applications"] = cur.rowcount
        cur.execute(
            "DELETE FROM candidates c WHERE phone=ANY(%s) AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.phone=c.phone)",
            (PHONES,),
        )
        deleted["candidates"] = cur.rowcount
        if codes:
            cur.execute(
                "DELETE FROM positions WHERE company_code=%s AND position_code=ANY(%s) AND position_code<>%s",
                (COMPANY, codes, OWNER_JOB),
            )
            deleted["positions"] = cur.rowcount
    for raw in paths:
        path = Path(raw)
        if path.exists() and str(path).startswith(str(orch.WORKSPACE)):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    return deleted


def main() -> int:
    require_production()
    # Qualification uses dry-run transport while exercising production DB logic.
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    os.environ["WATHEFNI_STAGE_B_ENABLED"] = "1"
    os.environ["WATHEFNI_STAGE_B_CANARY_ONLY"] = "0"
    os.environ["WATHEFNI_STAGE_B_STAMP_DRY_RUN"] = "1"
    os.environ["WATHEFNI_STAGE_B_PUBLIC_POSITIONS"] = OWNER_JOB
    os.environ["WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES"] = OWNER_APPLY
    os.environ["WATHEFNI_STAGE_B_RATE_LIMIT_PER_HOUR"] = "8"
    os.environ["WATHEFNI_APPLY_WHATSAPP_NUMBER"] = "96599338566"

    orch.ensure_schema(force=True)
    owner_job = ensure_owner_job()
    if owner_job.get("apply_code") != OWNER_APPLY:
        raise AssertionError(f"unexpected owner APPLY code: {owner_job.get('apply_code')}")

    suffix = MARKER[-8:]
    second_code = f"J2P2-R2-{suffix}"
    internal_code = f"J2P2-INT-{suffix}"
    draft_code = f"J2P2-DR-{suffix}"
    paused_code = f"J2P2-PAU-{suffix}"
    closed_code = f"J2P2-CLS-{suffix}"
    expired_code = f"J2P2-EXP-{suffix}"
    full_code = f"J2P2-FULL-{suffix}"
    unapproved_code = f"J2P2-UNAP-{suffix}"
    salary_code = f"J2P2-SAL-{suffix}"
    codes = [
        second_code,
        internal_code,
        draft_code,
        paused_code,
        closed_code,
        expired_code,
        full_code,
        unapproved_code,
        salary_code,
    ]
    app_keys: list[str] = []
    stored_paths: list[str] = []
    results: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "marker": MARKER,
        "database": "wathefni",
        "owner_test_job": {
            "position_code": OWNER_JOB,
            "apply_code": OWNER_APPLY,
            "application_link": owner_job.get("application_link"),
        },
    }

    def check(name: str, fn: Callable[[], Any]) -> None:
        try:
            value = fn()
            results.append({"name": name, "ok": True, "evidence": orch.json_safe(value)})
            print(f"PASS  {name}")
        except Exception as exc:
            results.append({"name": name, "ok": False, "error": str(exc), "trace": traceback.format_exc()})
            print(f"FAIL  {name}: {exc}")

    phone = PHONES[0]
    conv = f"{MARKER}-primary"
    source_token = f"SRC-{MARKER}"
    fixture = make_docx(Path(str(orch.WORKSPACE)) / "tmp" / MARKER / "candidate.docx")
    stored_paths.append(str(fixture.parent))

    try:
        def initial_apply() -> dict[str, Any]:
            response = turn(
                phone=phone,
                conversation=conv,
                text=OWNER_APPLY,
                message_id=f"{MARKER}-apply-1",
                source_ref_token=source_token,
            )
            context = response.get("job_context") or {}
            assert response.get("application_created") is False
            assert context.get("preview_sent_at")
            assert app_count(phone, OWNER_JOB) == 0
            assert context.get("source_ref_token") == source_token
            assert context.get("source_channel") == "whatsapp"
            return {"context_id": context.get("context_id"), "preview_sent_at": context.get("preview_sent_at")}

        check("apply_context_zero_applications", initial_apply)

        def webhook_idempotency() -> dict[str, Any]:
            req = request(
                phone=PHONES[2],
                conversation=f"{MARKER}-webhook",
                text=OWNER_APPLY,
                message_id=f"{MARKER}-webhook-1",
                source_ref_token=source_token,
            )
            first = orch.whatsapp_turn(req)
            second = orch.whatsapp_turn(req)
            first_json = first.model_dump() if hasattr(first, "model_dump") else dict(first)
            second_json = second.model_dump() if hasattr(second, "model_dump") else dict(second)
            assert (second_json.get("audit") or {}).get("ingress_dedupe", {}).get("duplicate") is True
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM candidate_job_contexts WHERE phone=%s AND conversation_id=%s",
                    (PHONES[2], f"{MARKER}-webhook"),
                )
                assert int(cur.fetchone()["n"]) == 1
            return {"first_intent": first_json.get("intent"), "replay": True}

        check("webhook_idempotency", webhook_idempotency)

        def confirm_one() -> dict[str, Any]:
            response = turn(
                phone=phone,
                conversation=conv,
                text="ready to apply",
                message_id=f"{MARKER}-confirm-1",
            )
            assert response.get("application_created") is True, response
            application = response.get("application") or {}
            assert application.get("status") == "awaiting_cv"
            assert app_count(phone, OWNER_JOB) == 1
            app_keys.append(str(application["app_key"]))
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM conversation_application_bindings WHERE app_key=%s",
                    (application["app_key"],),
                )
                binding = cur.fetchone()
                assert binding and binding["bound_reason"] == "explicit_apply"
                cur.execute(
                    "SELECT * FROM application_lifecycle_events WHERE app_key=%s AND trigger='explicit_apply'",
                    (application["app_key"],),
                )
                event = cur.fetchone()
                assert event and event["to_stage"] == "awaiting_cv"
                cur.execute("SELECT raw_json FROM applications WHERE app_key=%s", (application["app_key"],))
                raw = cur.fetchone()["raw_json"]
                assert raw.get("source_ref_token") == source_token
            return {"app_key": application["app_key"], "binding": "explicit_apply", "audit": "explicit_apply"}

        check("explicit_confirmation_exactly_one", confirm_one)

        def duplicate_apply_confirm() -> dict[str, Any]:
            repeated_apply = turn(
                phone=phone,
                conversation=conv,
                text=OWNER_APPLY,
                message_id=f"{MARKER}-apply-repeat",
            )
            assert repeated_apply.get("application_created") is False
            repeated_confirm = turn(
                phone=phone,
                conversation=conv,
                text="ready to apply",
                message_id=f"{MARKER}-confirm-repeat",
            )
            assert repeated_confirm.get("application_created") is not True
            assert app_count(phone, OWNER_JOB) == 1
            return {"applications": 1}

        check("duplicate_apply_and_confirmation", duplicate_apply_confirm)

        def cv_attach_processing() -> dict[str, Any]:
            response = turn(
                phone=phone,
                conversation=conv,
                text="",
                message_id=f"{MARKER}-cv-1",
                media={
                    "path": str(fixture),
                    "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
            )
            assert response.get("ok") is True, response
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT status, cv_received, raw_json FROM applications WHERE app_key=%s",
                    (app_keys[0],),
                )
                application = dict(cur.fetchone())
                assert application["status"] == "cv_processing"
                assert application["cv_received"] is True
                cur.execute(
                    "SELECT document_id::text, local_path FROM candidate_documents WHERE app_key=%s AND document_type='cv' ORDER BY updated_at DESC LIMIT 1",
                    (app_keys[0],),
                )
                document = dict(cur.fetchone())
            if document.get("local_path"):
                stored_paths.append(str(document["local_path"]))
            processed = orch.process_candidate_cv_document(document["document_id"], dry_run=True)
            assert processed.get("ok") is True, processed
            return {
                "status": application["status"],
                "cv_received": application["cv_received"],
                "document_id": document["document_id"],
                "dry_run_processing": processed,
            }

        check("cv_attachment_and_processing", cv_attach_processing)

        def different_role() -> dict[str, Any]:
            second = create_job(second_code)
            conv2 = f"{MARKER}-role2"
            bind = turn(
                phone=phone,
                conversation=conv2,
                text=second["apply_code"],
                message_id=f"{MARKER}-role2-apply",
            )
            assert bind.get("application_created") is False
            created = turn(
                phone=phone,
                conversation=conv2,
                text="ready to apply",
                message_id=f"{MARKER}-role2-confirm",
            )
            assert created.get("application_created") is True, created
            app_keys.append(str((created.get("application") or {})["app_key"]))
            assert app_count(phone) == 2
            return {"active_applications_for_phone": 2, "second_position": second_code}

        check("different_role_separate_application", different_role)

        def denials() -> dict[str, Any]:
            internal = create_job(internal_code, visibility="internal")
            draft = create_job(draft_code, open_job=False)
            paused = create_job(paused_code)
            paused = jobs.transition_job(
                company=COMPANY,
                position_code=paused_code,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="paused",
                expected_version=paused["version"],
            )
            closed = create_job(closed_code)
            closed = jobs.transition_job(
                company=COMPANY,
                position_code=closed_code,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="closed",
                expected_version=closed["version"],
            )
            expired = create_job(
                expired_code,
                application_deadline=(date.today() - timedelta(days=1)).isoformat(),
            )
            full = create_job(full_code, vacancies=1)
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO applications
                      (app_key,phone,company_code,position_code,status,current_step,raw_json,data_source,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,'hired','hired',%s,'production',CURRENT_DATE,CURRENT_DATE)
                    """,
                    (
                        f"{MARKER}-FULL-HIRED",
                        PHONES[0],
                        COMPANY,
                        full_code,
                        orch.Json({"marker": MARKER}),
                    ),
                )
                app_keys.append(f"{MARKER}-FULL-HIRED")
            unapproved = create_job(unapproved_code, open_job=False, approve_content_en=False, approve_content_ar=False)
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE positions SET status='open', published_at=now() WHERE company_code=%s AND position_code=%s",
                    (COMPANY, unapproved_code),
                )

            expected = {
                internal["apply_code"]: "job_visibility_denied",
                draft["apply_code"]: "job_not_accepting",
                paused["apply_code"]: "job_paused",
                closed["apply_code"]: "job_closed",
                expired["apply_code"]: "job_deadline_passed",
                full["apply_code"]: "job_vacancies_exhausted",
                unapproved["apply_code"]: "job_content_incomplete",
            }
            observed: dict[str, str] = {}
            for apply_code, reason in expected.items():
                resolved = orch.resolve_public_role_by_apply_code(apply_code)
                assert resolved.get("ok") is False, (apply_code, resolved)
                assert resolved.get("error") == reason, (apply_code, resolved, reason)
                observed[apply_code] = str(resolved.get("error"))
            return observed

        check("job_denial_matrix", denials)

        def salary_visibility() -> dict[str, Any]:
            hidden = orch.resolve_public_role_by_apply_code(OWNER_APPLY)
            assert hidden.get("ok") is True
            assert (hidden.get("role") or {}).get("salary_min") is None
            public = create_job(
                salary_code,
                salary_visibility="public",
                salary_min=700,
                salary_max=900,
            )
            visible = orch.resolve_public_role_by_apply_code(public["apply_code"])
            role = visible.get("role") or {}
            assert visible.get("ok") is True
            assert role.get("salary_min") == 700.0 and role.get("salary_max") == 900.0
            return {"hr_only_hidden": True, "public_range": [role["salary_min"], role["salary_max"]]}

        check("salary_visibility_enforced", salary_visibility)

        def tenant_isolation() -> dict[str, Any]:
            wrong = orch.resolve_public_role_by_apply_code(
                OWNER_APPLY,
                verified_company_code="NOT_WATHEFNI",
            )
            assert wrong.get("ok") is False and wrong.get("error") == "apply_code_not_found"
            with orch.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM candidate_job_contexts WHERE phone=ANY(%s) AND company_code<>%s",
                    (PHONES, COMPANY),
                )
                assert int(cur.fetchone()["n"]) == 0
            return {"wrong_tenant_result": wrong.get("error"), "cross_tenant_rows": 0}

        check("no_tenant_fallback_or_cross_tenant_access", tenant_isolation)
    finally:
        cleanup_result = cleanup(codes, app_keys, stored_paths)
        evidence["cleanup"] = cleanup_result

    passed = sum(1 for item in results if item["ok"])
    evidence["results"] = results
    evidence["summary"] = {"passed": passed, "failed": len(results) - passed, "total": len(results)}
    evidence["result"] = "PASS" if passed == len(results) else "FAIL"
    report_path = Path(
        os.environ.get("JOBS_PHASE2_PRODUCTION_REPORT")
        or "/opt/wathefni/orchestrator/ops/reports/jobs-phase2-production-green.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"result": evidence["result"], **evidence["summary"], "report": str(report_path)}, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
