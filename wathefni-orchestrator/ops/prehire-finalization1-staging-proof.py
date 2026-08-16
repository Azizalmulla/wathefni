#!/usr/bin/env python3
"""Controlled EN/AR staging proof for Pre-Hiring Finalization-1.

Synthetic company only. Delivery must be dry-run. Production is refused.
The harness exercises current behavior without changing product architecture.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMPANY = "PHF1"
MARKER = "prehire_finalization1_staging_proof"
OUT = Path(os.environ.get("PHF1_EVIDENCE_DIR", "/opt/wathefni/staging/evidence/prehire-finalization1"))
ACTORS = {
    "recruiter": "00000000-0000-4000-8000-000000000101",
    "offer_creator": "00000000-0000-4000-8000-000000000102",
    "offer_approver": "00000000-0000-4000-8000-000000000103",
    "offer_sender": "00000000-0000-4000-8000-000000000104",
    "owner": "00000000-0000-4000-8000-000000000105",
}


class Proof:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.journeys: list[dict[str, Any]] = []
        self.negative: list[dict[str, Any]] = []

    def check(self, label: str, condition: bool, detail: Any = None) -> None:
        self.checks.append({"label": label, "ok": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{label}: {detail}")

    def expect_error(self, label: str, fn: Callable[[], Any], codes: set[str]) -> str:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            code = str(getattr(exc, "code", "") or "")
            self.negative.append({"label": label, "ok": code in codes, "code": code, "detail": str(exc)})
            if code not in codes:
                raise
            return code
        self.negative.append({"label": label, "ok": False, "code": None, "detail": "no error"})
        raise AssertionError(f"{label}: expected {codes}")


def _json(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _app_row(app: Any, app_key: str) -> dict[str, Any]:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.*, c.name AS candidate_name, c.email AS candidate_email
            FROM applications a LEFT JOIN candidates c ON c.phone=a.phone
            WHERE a.app_key=%s AND a.company_code=%s
            """,
            (app_key, COMPANY),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError(f"application_missing:{app_key}")
    return dict(row)


def _counts(app: Any) -> dict[str, int]:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*)::int FROM applications WHERE company_code=%s) applications,
              (SELECT count(*)::int FROM assessment_attempts WHERE company_code=%s) attempts,
              (SELECT count(*)::int FROM candidate_interviews WHERE company_code=%s) interviews,
              (SELECT count(*)::int FROM employment_offers WHERE company_code=%s) offers,
              (SELECT count(*)::int FROM application_lifecycle_events WHERE company_code=%s) lifecycle_events,
              (SELECT count(*)::int FROM outbound_delivery_events WHERE company_code=%s) outbound_events
            """,
            (COMPANY, COMPANY, COMPANY, COMPANY, COMPANY, COMPANY),
        )
        row = dict(cur.fetchone())
        conn.commit()
    return row


def _cleanup(app: Any) -> None:
    """Delete only PHF1 synthetic rows, retrying tables to satisfy FK order."""
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema='public' AND column_name='company_code'
            ORDER BY table_name
            """
        )
        tables = [str(r["table_name"]) for r in cur.fetchall()]
        conn.rollback()
    remaining = set(tables)
    for _ in range(8):
        progressed = False
        for table in list(remaining):
            if table == "companies":
                continue
            with app.db_connect() as conn, conn.cursor() as cur:
                try:
                    cur.execute(f'DELETE FROM "{table}" WHERE company_code=%s', (COMPANY,))
                    conn.commit()
                    remaining.discard(table)
                    progressed = True
                except Exception:
                    conn.rollback()
        if not progressed:
            break
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM candidates WHERE active_company_code=%s", (COMPANY,))
        cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()
    proof_root = Path(str(app.WORKSPACE)) / "companies" / COMPANY
    if proof_root.exists():
        shutil.rmtree(proof_root)


def _seed(app: Any, offer_service: Any) -> None:
    app.ensure_schema(force=True)
    offer_service.ensure_schema(app)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO companies (company_code,name,status,metadata,raw_json,created_at,updated_at)
            VALUES (%s,'PHF1 Synthetic','active',%s,%s,now(),now())
            ON CONFLICT (company_code) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
            """,
            (COMPANY, app.Json({"marker": MARKER}), app.Json({"marker": MARKER})),
        )
        for module in ("pre_hiring", "assessments", "video_interviews", "employment_offers"):
            cur.execute(
                """
                INSERT INTO company_modules (company_code,module_key,enabled,source,updated_at)
                VALUES (%s,%s,true,%s,now())
                ON CONFLICT (company_code,module_key) DO UPDATE SET enabled=true,source=EXCLUDED.source,updated_at=now()
                """,
                (COMPANY, module, MARKER),
            )
        cur.execute(
            """
            INSERT INTO company_settings (company_code,settings)
            VALUES (%s,%s)
            ON CONFLICT (company_code) DO UPDATE SET settings=company_settings.settings || EXCLUDED.settings,updated_at=now()
            """,
            (COMPANY, app.Json({"offer_allow_self_approval": False})),
        )
        conn.commit()


def _seed_candidate(app: Any, locale: str, index: int) -> tuple[str, str, str]:
    phone = f"96550177{index:04d}"
    app_key = f"PHF1-{locale.upper()}-{index}"
    conversation = f"phf1-{locale}-conversation-{index}"
    name = "English Synthetic Candidate" if locale == "en" else "مرشح تجريبي عربي"
    email = f"phf1-{locale}-{index}@example.invalid"
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidates
              (phone,name,email,current_status,active_company_code,active_position_code,profile,raw_json,data_source)
            VALUES (%s,%s,%s,'awaiting_cv',%s,'GENERAL',%s,%s,'production')
            ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name,email=EXCLUDED.email,
              active_company_code=EXCLUDED.active_company_code,raw_json=EXCLUDED.raw_json,updated_at=now()
            """,
            (
                phone,
                name,
                email,
                COMPANY,
                app.Json({"locale": locale, "marker": MARKER}),
                app.Json({"locale": locale, "marker": MARKER, "synthetic": True}),
            ),
        )
        cur.execute(
            """
            INSERT INTO applications
              (app_key,phone,company_code,position_code,position_title,status,current_step,
               cv_received,screening_status,raw_json,data_source,created_at,updated_at)
            VALUES (%s,%s,%s,'GENERAL','General Role','awaiting_cv','cv_request',
                    false,'awaiting_cv',%s,'production',CURRENT_DATE,CURRENT_DATE)
            ON CONFLICT (app_key) DO UPDATE SET status='awaiting_cv',current_step='cv_request',
              cv_received=false,screening_status='awaiting_cv',raw_json=EXCLUDED.raw_json,updated_at=CURRENT_DATE
            """,
            (app_key, phone, COMPANY, app.Json({"locale": locale, "marker": MARKER, "synthetic": True})),
        )
        conn.commit()
    return phone, app_key, conversation


def _cv_file(locale: str, index: int, *, updated: bool = False, blank: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"phf1-{locale}-{index}{'-updated' if updated else ''}{'-blank' if blank else ''}.txt"
    if blank:
        path.write_text("", encoding="utf-8")
    elif locale == "ar":
        path.write_text(
            "السيرة الذاتية\nالاسم: مرشح تجريبي عربي\nالبريد الإلكتروني: phf1-ar@example.invalid\n"
            "الهاتف: 965501770002\nالخبرة: خمس سنوات في خدمة العملاء والعمليات المصرفية.\n"
            "المهارات: التواصل، الدقة، حل المشكلات، اللغة العربية والإنجليزية.\n"
            + ("تحديث: خبرة إضافية في الموارد البشرية.\n" if updated else "")
            + ("وصف مهني تجريبي. " * 18),
            encoding="utf-8",
        )
    else:
        path.write_text(
            "CURRICULUM VITAE\nName: English Synthetic Candidate\nEmail: phf1-en@example.invalid\n"
            "Phone: 965501770001\nExperience: Five years in customer service and banking operations.\n"
            "Skills: communication, accuracy, problem solving, English and Arabic.\n"
            + ("Update: additional human-resources experience.\n" if updated else "")
            + ("Synthetic professional profile for controlled staging proof. " * 18),
            encoding="utf-8",
        )
    return path


def _complete_assessment(app: Any, service: Any, attempt: dict[str, Any], token: str) -> dict[str, Any]:
    with app.db_connect() as conn, conn.cursor() as cur:
        version = service.content_version_by_id(
            cur, str(attempt["assessment_version_id"]), company_code=COMPANY
        )
        conn.commit()
    items = service.version_items(version)
    result: dict[str, Any] = {}
    for item in items:
        state = app.public_assessment_state(str(attempt["attempt_id"]), token, start=True)
        result = app.record_assessment_response(
            attempt_id=str(attempt["attempt_id"]),
            company_code=COMPANY,
            raw_token=token,
            item_id=str(item["item_id"]),
            response_text=str(item.get("answer_key") or "A"),
            selected_key=str(item.get("answer_key") or "A"),
            progress_version=int(state["attempt"]["progress_version"]),
        )
    return result


def _journey(
    proof: Proof,
    app: Any,
    lifecycle: Any,
    assessment_service: Any,
    offer_service: Any,
    offer_lifecycle: Any,
    *,
    locale: str,
    index: int,
) -> None:
    phone, app_key, conversation = _seed_candidate(app, locale, index)
    initial = _app_row(app, app_key)
    cv_path = _cv_file(locale, index)
    request = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id=conversation,
        sender_phone=phone,
        sender_role="candidate",
        raw_text="My CV" if locale == "en" else "سيرتي الذاتية",
        media={"path": str(cv_path), "type": "text/plain", "current": True},
        metadata={"locale": locale, "marker": MARKER},
    )
    upload = app.handle_candidate_file_turn(request)
    proof.check(f"{locale}: WhatsApp CV stored", bool(upload and upload.get("ok")), upload)
    upload_reply = str((upload or {}).get("reply") or "")

    # Exact duplicate webhook/file submission is storage-idempotent by filename.
    duplicate = app.handle_candidate_file_turn(request)
    proof.check(f"{locale}: repeated CV turn safe", bool(duplicate and duplicate.get("ok")), duplicate)

    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT document_id::text FROM candidate_documents WHERE app_key=%s ORDER BY updated_at DESC LIMIT 1",
            (app_key,),
        )
        document_id = str(cur.fetchone()["document_id"])
        conn.commit()

    original_llm = app.extract_structured_candidate_profile_from_cv_text
    app.extract_structured_candidate_profile_from_cv_text = lambda *_a, **_k: {}
    try:
        processing = app.process_candidate_cv_document(document_id, dry_run=False, send_screening=False)
    finally:
        app.extract_structured_candidate_profile_from_cv_text = original_llm
    proof.check(f"{locale}: CV processing successful", bool(processing.get("ok")), processing)
    reviewed = _app_row(app, app_key)
    proof.check(f"{locale}: ready for HR review", reviewed["status"] == "ready_for_review", reviewed["status"])

    # Status and receipt replies must reflect backend truth.
    status_turn = app.handle_candidate_application_status_turn(
        app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id=conversation,
            sender_phone=phone,
            sender_role="candidate",
            raw_text="application status" if locale == "en" else "حالة الطلب",
        )
    )
    truth_turn = app.handle_candidate_truth_turn(
        app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id=conversation,
            sender_phone=phone,
            sender_role="candidate",
            raw_text="was my CV received?" if locale == "en" else "هل استلمتم السيرة الذاتية؟",
        )
    )

    # Assessment delivery and deterministic completion.
    sent_assessment = app.send_assessment(
        reviewed, "default", note=f"PHF1 {locale} synthetic", requested_by="phf1-hr"
    )
    proof.check(f"{locale}: assessment dry-run delivery", bool(sent_assessment.get("ok")), sent_assessment)
    attempt = dict(sent_assessment["attempt"])
    proof.check(
        f"{locale}: assessment delivery controlled",
        str(attempt.get("delivery_status")) == "intentionally_skipped",
        attempt.get("delivery_status"),
    )
    token = str(sent_assessment["assessment_link"]).split("token=", 1)[1]
    completed = _complete_assessment(app, assessment_service, attempt, token)
    proof.check(f"{locale}: deterministic assessment complete", bool(completed.get("completed")), completed)

    # Human-confirmed canonical shortlist and interview transitions.
    shortlist = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code=COMPANY,
        to_stage="shortlisted",
        trigger="dashboard_shortlist",
        expected_from_stage="ready_for_review",
        actor_type="human",
        actor_user_id=ACTORS["recruiter"],
        human_confirmed=True,
        confirmation_token=f"phf1:{locale}:shortlist",
        idempotency_key=f"phf1:{locale}:shortlist",
        permissions={"candidate.manage"},
    )
    proof.check(f"{locale}: human-confirmed shortlist", bool(shortlist.get("ok")), shortlist)
    shortlist_replay = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code=COMPANY,
        to_stage="shortlisted",
        trigger="dashboard_shortlist",
        actor_type="human",
        human_confirmed=True,
        idempotency_key=f"phf1:{locale}:shortlist",
        permissions={"candidate.manage"},
    )
    proof.check(f"{locale}: shortlist replay idempotent", bool(shortlist_replay.get("idempotent")), shortlist_replay)
    interview_transition = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code=COMPANY,
        to_stage="interview",
        trigger="dashboard_schedule",
        expected_from_stage="shortlisted",
        actor_type="human",
        actor_user_id=ACTORS["recruiter"],
        human_confirmed=True,
        confirmation_token=f"phf1:{locale}:interview",
        idempotency_key=f"phf1:{locale}:interview",
        permissions={"interview.manage"},
    )
    proof.check(f"{locale}: interview transition", bool(interview_transition.get("ok")), interview_transition)
    interviewed = _app_row(app, app_key)
    interview_req = app.DashboardVideoInterviewRequest(
        send_invite=False, link_ttl_days=7, response_mode="single_video"
    )
    created_interview = app.create_or_resume_async_video_interview(
        interviewed,
        interview_req,
        actor_context={"actor_type": "human", "actor_user_id": ACTORS["recruiter"], "actor_phone": "96550000001"},
    )
    interview_delivery = app.send_async_video_interview_invite(
        interviewed,
        created_interview["interview"],
        created_interview["public_link"],
        account_id="default",
        preferred_channel="whatsapp",
        actor_context={"actor_type": "human", "actor_user_id": ACTORS["recruiter"], "actor_phone": "96550000001"},
        note=f"PHF1 {locale} synthetic",
    )
    proof.check(f"{locale}: interview dry-run delivery", bool(interview_delivery.get("ok")), interview_delivery)

    # Offer: distinct creator/approver, version-pinned token, candidate acceptance.
    perms = {
        "offer.manage",
        "offer.approve",
        "offer.send",
        "offer.withdraw",
        "offer.record_response",
        "candidate.decide",
    }
    draft = offer_service.create_draft(
        app,
        company_code=COMPANY,
        app_key=app_key,
        actor_user_id=ACTORS["offer_creator"],
        permissions=perms,
        position_title="General Role",
        base_salary=800,
        currency="KWD",
        wording_en="Controlled synthetic staging offer.",
        wording_ar="عرض تجريبي مضبوط لبيئة الاختبار.",
        idempotency_key=f"phf1:{locale}:offer",
    )
    submitted = offer_service.submit_for_approval(
        legacy=app,
        company_code=COMPANY,
        offer_id=str(draft["offer_id"]),
        actor_user_id=ACTORS["offer_creator"],
        permissions=perms,
    )
    approved = offer_service.approve_offer(
        legacy=app,
        company_code=COMPANY,
        offer_id=str(draft["offer_id"]),
        actor_user_id=ACTORS["offer_approver"],
        permissions=perms,
    )
    proof.check(f"{locale}: offer approved", approved.get("status") == "approved", approved)
    sent_offer = offer_service.send_offer(
        app,
        company_code=COMPANY,
        offer_id=str(draft["offer_id"]),
        actor_user_id=ACTORS["offer_sender"],
        permissions=perms,
    )
    delivery = sent_offer.get("delivery") or {}
    proof.check(
        f"{locale}: offer version pinned",
        int(delivery.get("offer_version") or 0) == int(sent_offer.get("current_version") or 0),
        delivery,
    )
    raw_offer_token = str(sent_offer["raw_token"])

    # Expired and revoked token fail closed; restore only this synthetic token.
    token_hash = offer_lifecycle.hash_offer_token(raw_offer_token)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE employment_offer_tokens SET expires_at=now()-interval '1 minute' WHERE token_hash=%s",
            (token_hash,),
        )
        conn.commit()
    proof.expect_error(
        f"{locale}: expired offer link",
        lambda: offer_service.respond_via_token(app, raw_token=raw_offer_token, decision="accepted"),
        {"token_expired"},
    )
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE employment_offer_tokens SET expires_at=now()+interval '1 day',revoked_at=now() WHERE token_hash=%s",
            (token_hash,),
        )
        conn.commit()
    proof.expect_error(
        f"{locale}: revoked offer link",
        lambda: offer_service.public_offer_preview(app, raw_token=raw_offer_token),
        {"token_revoked"},
    )
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE employment_offer_tokens SET revoked_at=NULL WHERE token_hash=%s", (token_hash,))
        conn.commit()
    accepted = offer_service.respond_via_token(app, raw_token=raw_offer_token, decision="accepted")
    proof.check(f"{locale}: candidate accepted offer", accepted.get("status") == "accepted", accepted)
    gate = offer_service.enforce_hire_gate(
        app,
        company_code=COMPANY,
        app_key=app_key,
        permissions={"candidate.decide"},
        actor_user_id=ACTORS["owner"],
        actor_type="human",
        expected_from_stage="interview",
    )
    proof.check(f"{locale}: accepted-offer hire gate", bool(gate.get("ok")), gate)
    hired = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code=COMPANY,
        to_stage="hired",
        trigger="dashboard_hire",
        expected_from_stage="interview",
        actor_type="human",
        actor_user_id=ACTORS["owner"],
        human_confirmed=True,
        confirmation_token=f"phf1:{locale}:hire",
        idempotency_key=f"phf1:{locale}:hire",
        permissions={"candidate.decide"},
        run_hire_side_effects=False,
    )
    proof.check(f"{locale}: human-confirmed hire", bool(hired.get("ok")), hired)

    # Secure pages reveal current localization behavior without inventing parity.
    assessment_html = app.public_assessment_html()
    offer_html = app.public_offer_html() if hasattr(app, "public_offer_html") else ""
    journey = {
        "locale": locale,
        "app_key": app_key,
        "messages": {
            "upload_reply": upload_reply,
            "status_reply": (status_turn or {}).get("reply"),
            "receipt_reply": (truth_turn or {}).get("reply"),
            "assessment_invite": sent_assessment.get("message"),
            "interview_invite": interview_delivery.get("sent_body"),
        },
        "delivery": {
            "assessment": attempt.get("delivery_status"),
            "interview": (interview_delivery.get("delivery") or {}).get("status")
            or (interview_delivery.get("delivery") or {}).get("delivery_status"),
            "offer": delivery.get("status"),
        },
        "entities": {
            "assessment_version_id": str(attempt.get("assessment_version_id")),
            "interview_id": str(created_interview["interview"]["interview_id"]),
            "offer_id": str(draft["offer_id"]),
            "offer_version": int(sent_offer.get("current_version") or 0),
            "final_application_stage": _app_row(app, app_key).get("status"),
        },
        "secure_page_localization": {
            "assessment_has_arabic": any("\u0600" <= c <= "\u06ff" for c in assessment_html),
            "offer_has_arabic": any("\u0600" <= c <= "\u06ff" for c in offer_html),
        },
    }
    proof.journeys.append(journey)


def _negative_paths(proof: Proof, app: Any, lifecycle: Any, offer_service: Any) -> None:
    # Unsupported file is not accepted by the CV handler.
    phone, app_key, conversation = _seed_candidate(app, "neg", 90)
    unsupported = OUT / "unsupported.exe"
    unsupported.write_bytes(b"MZ synthetic")
    unsupported_result = app.handle_candidate_file_turn(
        app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id=conversation,
            sender_phone=phone,
            sender_role="candidate",
            raw_text="CV",
            media={"path": str(unsupported), "type": "application/octet-stream", "current": True},
        )
    )
    proof.negative.append(
        {"label": "unsupported CV", "ok": unsupported_result is None, "detail": _json(unsupported_result)}
    )

    # Blank file stores, then deterministic extraction fails.
    blank = _cv_file("neg", 90, blank=True)
    blank_upload = app.handle_candidate_file_turn(
        app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id=conversation,
            sender_phone=phone,
            sender_role="candidate",
            raw_text="CV",
            media={"path": str(blank), "type": "text/plain", "current": True},
        )
    )
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT document_id::text FROM candidate_documents WHERE app_key=%s ORDER BY updated_at DESC LIMIT 1",
            (app_key,),
        )
        blank_document = str(cur.fetchone()["document_id"])
        conn.commit()
    blank_processed = app.process_candidate_cv_document(
        blank_document, dry_run=False, send_screening=False
    )
    proof.negative.append(
        {
            "label": "blank/unreadable CV",
            "ok": not bool(blank_processed.get("ok")),
            "detail": _json(blank_processed),
            "receipt_claimed_processing": bool(blank_upload and blank_upload.get("ok")),
        }
    )

    wrong_tenant = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code="WRONGTENANT",
        to_stage="shortlisted",
        trigger="dashboard_shortlist",
        actor_type="human",
        human_confirmed=True,
        permissions={"candidate.manage"},
    )
    proof.negative.append(
        {
            "label": "wrong tenant",
            "ok": not bool(wrong_tenant.get("ok")),
            "detail": _json(wrong_tenant),
        }
    )

    # Two open apps on an unbound conversation must not attach a CV.
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO applications
              (app_key,phone,company_code,position_code,position_title,status,current_step,
               cv_received,screening_status,raw_json,data_source,created_at,updated_at)
            VALUES (%s,%s,%s,'SECOND','Second Role','awaiting_cv','cv_request',false,'awaiting_cv',%s,'production',CURRENT_DATE,CURRENT_DATE)
            """,
            (f"{app_key}-SECOND", phone, COMPANY, app.Json({"marker": MARKER})),
        )
        conn.commit()
    ambiguous = app.handle_candidate_file_turn(
        app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="phf1-unbound-ambiguous",
            sender_phone=phone,
            sender_role="candidate",
            raw_text="CV",
            media={"path": str(blank), "type": "text/plain", "current": True},
        )
    )
    proof.negative.append(
        {
            "label": "ambiguous application",
            "ok": bool(ambiguous and ambiguous.get("error") == "ambiguous_applications"),
            "detail": _json(ambiguous),
        }
    )

    failed_delivery = app.candidate_communication_router(
        {"app_key": "missing-contact", "company_code": COMPANY, "phone": None},
        account_id="default",
        kind="status",
        message="Synthetic",
        action={"purpose": "proof"},
    )
    proof.negative.append(
        {
            "label": "failed delivery not success",
            "ok": not bool(failed_delivery.get("ok")),
            "detail": _json(failed_delivery),
        }
    )

    withdrawal_handler = getattr(app, "handle_candidate_withdrawal_turn", None)
    handoff_handler = getattr(app, "handle_candidate_hr_handoff_turn", None)
    proof.negative.extend(
        [
            {
                "label": "candidate withdrawal handler exists",
                "ok": callable(withdrawal_handler),
                "detail": None,
            },
            {
                "label": "candidate human handoff handler exists",
                "ok": callable(handoff_handler),
                "detail": None,
            },
        ]
    )

    stale = lifecycle.transition_application(
        app,
        app_key=app_key,
        company_code=COMPANY,
        to_stage="shortlisted",
        trigger="dashboard_shortlist",
        expected_from_stage="ready_for_review",
        actor_type="human",
        human_confirmed=True,
        permissions={"candidate.manage"},
    )
    proof.negative.append(
        {
            "label": "stale expected stage",
            "ok": not bool(stale.get("ok")),
            "detail": _json(stale),
        }
    )


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
    os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")

    import app
    import assessment_service
    import offer_lifecycle
    import offer_service
    import recruiting_lifecycle

    binding = app.assert_runtime_environment_binding()
    if binding.application_environment != "staging" or binding.database_environment != "staging":
        raise RuntimeError("prehire_finalization1_refuses_non_staging")
    if not app.delivery_is_dry_run():
        raise RuntimeError("prehire_finalization1_requires_dry_run_delivery")

    OUT.mkdir(parents=True, exist_ok=True)
    proof = Proof()
    _cleanup(app)
    _seed(app, offer_service)
    before = _counts(app)
    try:
        _journey(
            proof,
            app,
            recruiting_lifecycle,
            assessment_service,
            offer_service,
            offer_lifecycle,
            locale="en",
            index=1,
        )
        _journey(
            proof,
            app,
            recruiting_lifecycle,
            assessment_service,
            offer_service,
            offer_lifecycle,
            locale="ar",
            index=2,
        )
        _negative_paths(proof, app, recruiting_lifecycle, offer_service)
        during = _counts(app)
    finally:
        _cleanup(app)
    after = _counts(app)
    result = {
        "suite": "prehire_finalization1_staging",
        "completed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "environment": binding.public(),
        "delivery_mode": app.delivery_mode(),
        "production_touched": False,
        "real_external_messages": False,
        "company_code": COMPANY,
        "counts": {"before": before, "during": during, "after_cleanup": after},
        "journeys": proof.journeys,
        "negative_paths": proof.negative,
        "checks": proof.checks,
        "totals": {
            "checks_passed": sum(1 for c in proof.checks if c["ok"]),
            "checks_failed": sum(1 for c in proof.checks if not c["ok"]),
            "negative_passed": sum(1 for c in proof.negative if c["ok"]),
            "negative_failed": sum(1 for c in proof.negative if not c["ok"]),
        },
        "cleanup_ok": all(v == 0 for v in after.values()),
    }
    result["artifact_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    (OUT / "STAGING_PROOF.json").write_text(
        json.dumps(_json(result), indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(_json(result), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
