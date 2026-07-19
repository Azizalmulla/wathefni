#!/usr/bin/env python3
"""Contained EN/AR candidate WhatsApp cleanup proof.

Refuses non-staging and non-dry-run environments. All candidates, positions,
files, events, tasks, and bindings are synthetic and removed after evidence is
captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MARKER = "candidate_whatsapp_cleanup1"
COMPANY = "WATHEFNI"
WRONG_COMPANY = "WAC1WRONG"
OUT = Path(os.environ.get("WAC1_EVIDENCE_DIR", "/opt/wathefni/staging/evidence/candidate-whatsapp-cleanup1"))
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
PHONE_LOCALE: dict[str, str] = {}
APP_KEYS: set[str] = set()
PHONES: set[str] = set()
POSITION_CODES = {"WACEN1", "WACEN2", "WACAR1", "WACAR2", "WACAMB1", "WACAMB2"}


class Proof:
    def __init__(self) -> None:
        self.positive: list[dict[str, Any]] = []
        self.negative: list[dict[str, Any]] = []

    def check(self, label: str, condition: bool, detail: Any = None, *, negative: bool = False) -> bool:
        row = {"label": label, "ok": bool(condition), "detail": _json(detail)}
        (self.negative if negative else self.positive).append(row)
        return bool(condition)


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(v) for v in value]
    return value


def _response(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value or {})


def _turn(
    app: Any,
    *,
    phone: str,
    conversation: str,
    message_id: str,
    text: str = "",
    locale: str = "en",
    media: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _response(
        app.whatsapp_turn(
            app.WhatsAppTurnRequest(
                account_id="cleanup-proof",
                conversation_id=conversation,
                sender_phone=phone,
                raw_text=text,
                media=media,
                metadata={
                    "provider": "cleanup-proof",
                    "provider_message_id": message_id,
                    "locale": locale,
                    "synthetic": True,
                    "marker": MARKER,
                },
            )
        )
    )


def _app_row(app: Any, app_key: str) -> dict[str, Any]:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, app_key))
        row = cur.fetchone()
    return dict(row or {})


def _latest_document(app: Any, app_key: str) -> dict[str, Any]:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM candidate_documents
            WHERE app_key=%s AND document_type='cv'
            ORDER BY created_at DESC, updated_at DESC
            LIMIT 1
            """,
            (app_key,),
        )
        row = cur.fetchone()
    return dict(row or {})


def _count(app: Any, table: str, predicate: str, args: tuple[Any, ...]) -> int:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT count(*)::int AS count FROM "{table}" WHERE {predicate}', args)
        return int((cur.fetchone() or {}).get("count") or 0)


def _docx(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    paragraphs = []
    for line in text.splitlines():
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>')
    document = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{"".join(paragraphs)}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{PKG}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr("word/_rels/document.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="{PKG}"></Relationships>')
        zf.writestr("word/document.xml", document)
    return path


def _pdf(path: Path, text: str, *, encrypted: bool = False) -> Path:
    from reportlab.pdfgen import canvas

    raw = path.with_suffix(".raw.pdf") if encrypted else path
    c = canvas.Canvas(str(raw))
    y = 800
    for line in text.splitlines() or [""]:
        c.drawString(72, y, line)
        y -= 18
    c.save()
    if encrypted:
        import pikepdf

        with pikepdf.open(raw) as doc:
            doc.save(path, encryption=pikepdf.Encryption(owner="owner-proof", user="candidate-proof", R=6))
        raw.unlink(missing_ok=True)
    return path


def _image(path: Path, text: str) -> Path:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text((80, 80), text, fill="black", spacing=18)
    image.save(path)
    return path


def _seed(app: Any) -> None:
    app.ensure_schema(force=True)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO companies (company_code,name,status,metadata,raw_json,created_at,updated_at)
            VALUES (%s,'Cleanup Wrong Tenant','active',%s,%s,now(),now())
            ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata,updated_at=now()
            """,
            (WRONG_COMPANY, app.Json({"marker": MARKER}), app.Json({"marker": MARKER})),
        )
        roles = {
            "WACEN1": "Helios Compliance Archivist",
            "WACEN2": "Quantum Marine Linguist",
            "WACAR1": "محلل الامتثال التجريبي",
            "WACAR2": "مهندس الروبوتات البحرية",
            "WACAMB1": "Synthetic Ambiguous One",
            "WACAMB2": "Synthetic Ambiguous Two",
        }
        for code, title in roles.items():
            cur.execute(
                """
                INSERT INTO positions (company_code,position_code,title,status,created_at,updated_at)
                VALUES (%s,%s,%s,'open',now(),now())
                ON CONFLICT (company_code,position_code) DO UPDATE
                SET title=EXCLUDED.title,status='open',updated_at=now()
                """,
                (COMPANY, code, title),
            )
            cur.execute(
                "UPDATE positions SET apply_code=%s,metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE company_code=%s AND position_code=%s",
                (f"APPLY-{COMPANY}-{code}", app.Json({"marker": MARKER}), COMPANY, code),
            )
        conn.commit()


def _fake_workspace_start(app: Any, args: list[str], timeout: int = 60) -> dict[str, Any]:
    del timeout
    if "start-application" not in args:
        return {"ok": True, "synthetic": True}
    phone = args[args.index("--phone") + 1]
    company = args[args.index("--company") + 1]
    position = args[args.index("--position") + 1]
    locale = PHONE_LOCALE.get(phone, "en")
    app_key = f"{phone}-{company}-{position}"
    APP_KEYS.add(app_key)
    PHONES.add(phone)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT title,apply_code FROM positions WHERE company_code=%s AND position_code=%s", (company, position))
        role = dict(cur.fetchone() or {})
        cur.execute(
            """
            INSERT INTO candidates
              (phone,name,email,current_status,active_company_code,active_position_code,profile,raw_json,data_source)
            VALUES (%s,NULL,%s,'awaiting_cv',%s,%s,%s,%s,'production')
            ON CONFLICT (phone) DO UPDATE SET active_company_code=EXCLUDED.active_company_code,
              active_position_code=EXCLUDED.active_position_code,raw_json=EXCLUDED.raw_json,updated_at=now()
            """,
            (
                phone,
                f"{MARKER}-{phone}@example.invalid",
                company,
                position,
                app.Json({"marker": MARKER, "locale": locale}),
                app.Json({"marker": MARKER, "candidate_locale": locale, "synthetic": True}),
            ),
        )
        cur.execute(
            """
            INSERT INTO applications
              (app_key,phone,company_code,position_code,apply_code,position_title,status,current_step,
               cv_received,screening_status,raw_json,data_source,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,'awaiting_cv','cv_request',false,'not_started',%s,'production',CURRENT_DATE,CURRENT_DATE)
            ON CONFLICT (app_key) DO UPDATE SET status='awaiting_cv',current_step='cv_request',
              cv_received=false,screening_status='not_started',raw_json=EXCLUDED.raw_json,updated_at=CURRENT_DATE
            """,
            (
                app_key,
                phone,
                company,
                position,
                role.get("apply_code"),
                role.get("title"),
                app.Json({"marker": MARKER, "candidate_locale": locale, "synthetic": True}),
            ),
        )
        conn.commit()
    return {"ok": True, "synthetic": True, "app_key": app_key}


def _seed_direct_app(app: Any, *, phone: str, code: str, locale: str, company: str = COMPANY) -> str:
    app_key = f"{phone}-{company}-{code}"
    PHONES.add(phone)
    APP_KEYS.add(app_key)
    PHONE_LOCALE[phone] = locale
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidates
              (phone,name,email,current_status,active_company_code,active_position_code,profile,raw_json,data_source)
            VALUES (%s,NULL,%s,'awaiting_cv',%s,%s,%s,%s,'production')
            ON CONFLICT (phone) DO UPDATE SET active_company_code=EXCLUDED.active_company_code,
              active_position_code=EXCLUDED.active_position_code,raw_json=EXCLUDED.raw_json,updated_at=now()
            """,
            (
                phone,
                f"{MARKER}-{phone}@example.invalid",
                company,
                code,
                app.Json({"marker": MARKER, "locale": locale}),
                app.Json({"marker": MARKER, "candidate_locale": locale, "synthetic": True}),
            ),
        )
        cur.execute(
            """
            INSERT INTO applications
              (app_key,phone,company_code,position_code,position_title,status,current_step,
               cv_received,screening_status,raw_json,data_source,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,'awaiting_cv','cv_request',false,'not_started',%s,'production',CURRENT_DATE,CURRENT_DATE)
            ON CONFLICT (app_key) DO UPDATE SET status='awaiting_cv',current_step='cv_request',
              cv_received=false,raw_json=EXCLUDED.raw_json,updated_at=CURRENT_DATE
            """,
            (
                app_key,
                phone,
                company,
                code,
                f"Synthetic {code}",
                app.Json({"marker": MARKER, "candidate_locale": locale, "synthetic": True}),
            ),
        )
        conn.commit()
    return app_key


def _link_proof(app: Any, proof: Proof, application: dict[str, Any], locale: str) -> list[dict[str, Any]]:
    links = {
        "assessment_invitation": f"https://staging.invalid/assessment/{application['app_key']}?version=1",
        "interview_invitation": f"https://staging.invalid/interview/{application['app_key']}?version=1",
        "offer_invitation": f"https://staging.invalid/offer/{application['app_key']}?version=1",
    }
    rows = []
    for key, link in links.items():
        values = {"role": application.get("position_title") or "the role", "link": link}
        if key == "interview_invitation":
            values["details"] = "Synthetic staging interview."
        template = app.candidate_message_payload(key, application=application, locale=locale, **values)
        send = app.send_octopus_whatsapp(
            account_id="cleanup-proof",
            phone=application.get("phone"),
            text=template["text"],
            subject_type="candidate",
            subject_key=application.get("app_key"),
            message_kind=key,
            company_code=application.get("company_code"),
            audience="candidate",
        )
        proof.check(f"{locale} {key} dry-run", send.get("ok") and send.get("dry_run"), send)
        rows.append({"template": template, "send": _json(send), "entity": application.get("app_key"), "link": link})
    return rows


def _journey(app: Any, proof: Proof, *, locale: str, mode: str, index: int, files: dict[str, Path]) -> dict[str, Any]:
    phone = f"9655098{index:04d}"
    conversation = f"{MARKER}-{locale}-{mode}-{index}"
    code = f"WAC{locale.upper()}{'1' if mode == 'code' else '2'}"
    PHONE_LOCALE[phone] = locale
    apply_text = f"APPLY-{COMPANY}-{code}" if mode == "code" else (
        "I want to apply for Quantum Marine Linguist" if locale == "en" else "أريد التقديم على مهندس الروبوتات البحرية"
    )
    apply_response = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-{mode}-apply",
        text=apply_text,
        locale=locale,
    )
    app_key = f"{phone}-{COMPANY}-{code}"
    APP_KEYS.add(app_key)
    PHONES.add(phone)
    proof.check(f"{locale} apply by {mode}", _app_row(app, app_key).get("status") == "awaiting_cv", apply_response)
    proof.check(
        f"{locale} role resolved asks CV",
        app.candidate_message_payload("role_resolved_cv_request", locale=locale, role="x")["text"].split()[0]
        in str(apply_response.get("reply_text") or ""),
        apply_response.get("reply_text"),
    )
    if mode != "code":
        return {"locale": locale, "mode": mode, "apply": apply_response, "app_key": app_key}

    valid = files[f"valid_{locale}"]
    upload_request = {
        "phone": phone,
        "conversation": conversation,
        "message_id": f"{MARKER}-{locale}-valid-upload",
        "text": "CV" if locale == "en" else "السيرة الذاتية",
        "locale": locale,
        "media": {
            "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "path": str(valid),
        },
    }
    received = _turn(app, **upload_request)
    docs_after_first = _count(app, "candidate_documents", "app_key=%s", (app_key,))
    replay = _turn(app, **upload_request)
    docs_after_replay = _count(app, "candidate_documents", "app_key=%s", (app_key,))
    proof.check(f"{locale} checking message", "checking" in str(received.get("reply_text") or "").lower() or "نتحقق" in str(received.get("reply_text") or ""), received)
    proof.check(f"{locale} provider dedupe replay", replay.get("final_reply_source") == received.get("final_reply_source"), replay)
    proof.check(f"{locale} provider dedupe no second document", docs_after_first == docs_after_replay == 1, {"first": docs_after_first, "replay": docs_after_replay}, negative=True)

    document = _latest_document(app, app_key)
    processed = app.process_candidate_cv_document(str(document["document_id"]), dry_run=False)
    current = _app_row(app, app_key)
    proof.check(f"{locale} valid CV accepted", processed.get("ok") and current.get("status") == "ready_for_review", processed)
    proof.check(
        f"{locale} acceptance sent after validation",
        (processed.get("candidate_notification") or {}).get("template", {}).get("template_key") == "cv_accepted",
        processed.get("candidate_notification"),
    )

    duplicate_content = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-duplicate-content",
        text="same CV",
        locale=locale,
        media=upload_request["media"],
    )
    proof.check(
        f"{locale} duplicate content idempotent",
        _count(app, "candidate_documents", "app_key=%s", (app_key,)) == 1,
        duplicate_content,
        negative=True,
    )

    status = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-status",
        text="What is my application status?" if locale == "en" else "وين وصل طلبي؟",
        locale=locale,
    )
    proof.check(f"{locale} status response", status.get("intent") == "candidate_application_status", status)

    replace = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-replace",
        text="I want to replace my CV" if locale == "en" else "أبي أستبدل سيرتي الذاتية",
        locale=locale,
    )
    proof.check(f"{locale} replace request", replace.get("intent") == "candidate_cv_update_request", replace)
    accepted_sha = ((_app_row(app, app_key).get("raw_json") or {}).get("cv") or {}).get("storage", {}).get("sha256")

    invalid_upload = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-invalid-replacement",
        text="replacement",
        locale=locale,
        media={
            "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "path": str(files["corrupt_docx"]),
        },
    )
    invalid_doc = _latest_document(app, app_key)
    invalid_processed = app.process_candidate_cv_document(str(invalid_doc["document_id"]), dry_run=False)
    after_invalid = _app_row(app, app_key)
    after_invalid_sha = ((after_invalid.get("raw_json") or {}).get("cv") or {}).get("storage", {}).get("sha256")
    proof.check(f"{locale} invalid replacement rejected", not invalid_processed.get("ok"), invalid_processed, negative=True)
    proof.check(f"{locale} invalid replacement preserves accepted CV", accepted_sha == after_invalid_sha, {"before": accepted_sha, "after": after_invalid_sha}, negative=True)
    proof.check(
        f"{locale} invalid CV notification",
        (invalid_processed.get("candidate_notification") or {}).get("template", {}).get("template_key") == "cv_invalid",
        invalid_processed,
        negative=True,
    )
    proof.check(f"{locale} invalid file first acknowledged", bool(invalid_upload.get("reply_text")), invalid_upload)

    updated_upload = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-updated",
        text="updated CV",
        locale=locale,
        media={
            "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "path": str(files[f"updated_{locale}"]),
        },
    )
    updated_doc = _latest_document(app, app_key)
    updated_processed = app.process_candidate_cv_document(str(updated_doc["document_id"]), dry_run=False)
    proof.check(f"{locale} updated CV checked first", bool(updated_upload.get("reply_text")), updated_upload)
    proof.check(
        f"{locale} updated CV accepted",
        updated_processed.get("ok")
        and (updated_processed.get("candidate_notification") or {}).get("template", {}).get("template_key") == "cv_updated_accepted",
        updated_processed,
    )

    handoff = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-handoff",
        text="I want to speak to HR" if locale == "en" else "أبي أتكلم مع الموارد البشرية",
        locale=locale,
    )
    proof.check(f"{locale} HR handoff confirmation", handoff.get("intent") == "candidate_hr_handoff", handoff)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM hr_tasks
            WHERE company_code=%s AND task_type='candidate_handoff'
              AND metadata->>'app_key'=%s AND status='open'
            ORDER BY created_at DESC LIMIT 1
            """,
            (COMPANY, app_key),
        )
        task = dict(cur.fetchone() or {})
        cur.execute(
            "SELECT * FROM conversation_application_bindings WHERE company_code=%s AND conversation_id=%s",
            (COMPANY, conversation),
        )
        binding = dict(cur.fetchone() or {})
    proof.check(
        f"{locale} handoff pauses automation",
        bool(task) and (binding.get("metadata") or {}).get("automation_paused") is True,
        {"task": task, "binding": binding},
    )
    import recruiting_lifecycle as rl

    resume = rl.resume_candidate_handoff(
        app,
        company_code=COMPANY,
        task=task,
        resumed_by="cleanup-proof",
    )
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE hr_tasks SET status='done',resolved_at=now() WHERE task_id=%s", (task.get("task_id"),))
        conn.commit()
    proof.check(f"{locale} handoff resume", resume.get("ok"), resume)

    links = _link_proof(app, proof, _app_row(app, app_key), locale)

    withdraw_prompt = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-withdraw-prompt",
        text="Withdraw my application" if locale == "en" else "أريد سحب طلبي",
        locale=locale,
    )
    withdraw_confirm = _turn(
        app,
        phone=phone,
        conversation=conversation,
        message_id=f"{MARKER}-{locale}-withdraw-confirm",
        text="CONFIRM" if locale == "en" else "تأكيد",
        locale=locale,
    )
    withdrawn = _app_row(app, app_key)
    proof.check(f"{locale} withdrawal asks confirmation", withdraw_prompt.get("intent") == "candidate_withdrawal_confirmation_required", withdraw_prompt)
    proof.check(f"{locale} withdrawal confirmed", withdraw_confirm.get("intent") == "candidate_withdrawal_confirmed" and withdrawn.get("status") == "withdrawn", withdraw_confirm)
    proof.check(
        f"{locale} withdrawal audit",
        _count(app, "application_lifecycle_events", "company_code=%s AND app_key=%s AND trigger='candidate_withdrawal_confirmed'", (COMPANY, app_key)) == 1,
        negative=False,
    )
    return {
        "locale": locale,
        "mode": mode,
        "app_key": app_key,
        "apply": apply_response,
        "received": received,
        "processed": processed,
        "duplicate_replay": replay,
        "duplicate_content": duplicate_content,
        "status": status,
        "replace": replace,
        "invalid_processed": invalid_processed,
        "updated_processed": updated_processed,
        "handoff": handoff,
        "resume": resume,
        "links": links,
        "withdraw_prompt": withdraw_prompt,
        "withdraw_confirm": withdraw_confirm,
    }


def _negative_paths(app: Any, proof: Proof, files: dict[str, Path]) -> dict[str, Any]:
    phone = "96550989991"
    app_key = _seed_direct_app(app, phone=phone, code="WACAMB1", locale="en")
    second_key = _seed_direct_app(app, phone=phone, code="WACAMB2", locale="en")
    ambiguous = _turn(
        app,
        phone=phone,
        conversation=f"{MARKER}-ambiguous",
        message_id=f"{MARKER}-ambiguous-status",
        text="What is my application status?",
    )
    proof.check("ambiguous application fails closed", ambiguous.get("final_reply_source") != "llm_fallback" and "more than one" in str(ambiguous.get("reply_text") or ""), ambiguous, negative=True)
    proof.check("ambiguous status mutates neither app", _app_row(app, app_key).get("status") == _app_row(app, second_key).get("status") == "awaiting_cv", negative=True)

    empty = app.send_octopus_whatsapp(
        account_id="cleanup-proof",
        phone="",
        text="must fail",
        subject_type="candidate",
        subject_key=app_key,
        company_code=COMPANY,
    )
    proof.check("empty recipient fails dry-run", empty.get("ok") is False and empty.get("error") == "invalid_recipient", empty, negative=True)

    wrong_phone = "96550989992"
    wrong_key = _seed_direct_app(app, phone=wrong_phone, code="WRONG", locale="en", company=WRONG_COMPANY)
    import recruiting_lifecycle as rl

    wrong_binding = rl.bind_conversation_application(
        app,
        company_code=COMPANY,
        conversation_id=f"{MARKER}-wrong",
        phone=wrong_phone,
        app_key=wrong_key,
    )
    proof.check("wrong tenant binding rejected", wrong_binding.get("error") == "application_binding_mismatch", wrong_binding, negative=True)

    no_id = _response(
        app.whatsapp_turn(
            app.WhatsAppTurnRequest(
                account_id="cleanup-proof",
                conversation_id=f"{MARKER}-no-id",
                sender_phone="96550989993",
                raw_text="hello",
                metadata={"provider": "cleanup-proof", "locale": "en"},
            )
        )
    )
    proof.check("provider ID required", no_id.get("final_reply_source") == "provider_message_id_required", no_id, negative=True)

    first = _turn(
        app,
        phone="96550989994",
        conversation=f"{MARKER}-identity",
        message_id=f"{MARKER}-identity-reuse",
        text="hello",
    )
    mismatch = _turn(
        app,
        phone="96550989995",
        conversation=f"{MARKER}-identity",
        message_id=f"{MARKER}-identity-reuse",
        text="hello",
    )
    proof.check("provider ID identity mismatch rejected", mismatch.get("final_reply_source") == "whatsapp_duplicate_identity_mismatch", {"first": first, "mismatch": mismatch}, negative=True)

    unsupported = _turn(
        app,
        phone=phone,
        conversation=f"{MARKER}-unsupported",
        message_id=f"{MARKER}-unsupported",
        text="file",
        media={"type": "text/plain", "path": str(files["unsupported"])},
    )
    proof.check("unsupported attachment rejected", unsupported.get("intent") == "handle_candidate_file" and bool(unsupported.get("reply_text")), unsupported, negative=True)
    return {
        "ambiguous": ambiguous,
        "empty_recipient": empty,
        "wrong_binding": wrong_binding,
        "provider_id_required": no_id,
        "identity_mismatch": mismatch,
        "unsupported": unsupported,
    }


def _validation_matrix(app: Any, proof: Proof, files: dict[str, Path]) -> dict[str, Any]:
    cases = {
        "pdf": (files["valid_pdf"], "application/pdf", True),
        "docx_en": (files["valid_en"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", True),
        "docx_ar": (files["valid_ar"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", True),
        "docx_mixed": (files["mixed"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", True),
        "blank_docx": (files["blank_docx"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", False),
        "corrupt_docx": (files["corrupt_docx"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", False),
        "blank_pdf": (files["blank_pdf"], "application/pdf", False),
        "corrupt_pdf": (files["corrupt_pdf"], "application/pdf", False),
        "password_pdf": (files["password_pdf"], "application/pdf", False),
        "image": (files["image"], "image/png", True),
    }
    rows: dict[str, Any] = {}
    for label, (path, mime, expected) in cases.items():
        result = app.extract_candidate_cv_document(path, mime)
        accepted = bool(result.text and result.quality_ok)
        proof.check(
            f"CV validation {label}",
            accepted is expected,
            {"accepted": accepted, "expected": expected, "method": result.method, "error": result.error, "chars": len(result.text)},
            negative=not expected,
        )
        rows[label] = {
            "accepted": accepted,
            "expected": expected,
            "method": result.method,
            "error": result.error,
            "chars": len(result.text),
            "quality_ok": result.quality_ok,
        }
    return rows


def _cleanup(app: Any) -> dict[str, Any]:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT app_key,phone FROM applications WHERE raw_json->>'marker'=%s", (MARKER,))
        for row in cur.fetchall():
            APP_KEYS.add(str(row["app_key"]))
            PHONES.add(str(row["phone"]))
        cur.execute("SELECT phone FROM candidates WHERE raw_json->>'marker'=%s", (MARKER,))
        for row in cur.fetchall():
            PHONES.add(str(row["phone"]))
    app_keys = sorted(APP_KEYS)
    phones = sorted(PHONES)
    before = {"applications": 0, "documents": 0, "inbound": 0, "tasks": 0}
    if app_keys:
        before["applications"] = _count(app, "applications", "app_key=ANY(%s)", (app_keys,))
        before["documents"] = _count(app, "candidate_documents", "app_key=ANY(%s)", (app_keys,))
        before["tasks"] = _count(app, "hr_tasks", "metadata->>'app_key'=ANY(%s)", (app_keys,))
    before["inbound"] = _count(app, "whatsapp_inbound_messages", "provider=%s AND provider_message_id LIKE %s", ("cleanup-proof", f"{MARKER}%"))
    with app.db_connect() as conn, conn.cursor() as cur:
        if app_keys:
            cur.execute("SELECT document_id::text FROM candidate_documents WHERE app_key=ANY(%s)", (app_keys,))
            document_ids = [str(row["document_id"]) for row in cur.fetchall()]
            cur.execute("DELETE FROM cv_extraction_runs WHERE app_key=ANY(%s)", (app_keys,))
            if document_ids:
                cur.execute("DELETE FROM cv_extraction_leases WHERE document_id=ANY(%s)", (document_ids,))
            cur.execute("DELETE FROM outbound_delivery_events WHERE subject_type='candidate' AND subject_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM semantic_documents WHERE entity_type='application' AND app_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM hr_tasks WHERE metadata->>'app_key'=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM conversation_application_bindings WHERE app_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM application_lifecycle_events WHERE app_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM candidate_documents WHERE app_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM file_registry WHERE subject_type='application' AND subject_key=ANY(%s)", (app_keys,))
            cur.execute("DELETE FROM applications WHERE app_key=ANY(%s)", (app_keys,))
        if phones:
            cur.execute("DELETE FROM public_candidate_sessions WHERE phone=ANY(%s)", (phones,))
            cur.execute("DELETE FROM candidates WHERE phone=ANY(%s)", (phones,))
        cur.execute(
            "DELETE FROM whatsapp_inbound_messages WHERE provider=%s AND provider_message_id LIKE %s",
            ("cleanup-proof", f"{MARKER}%"),
        )
        cur.execute("DELETE FROM positions WHERE company_code=%s AND position_code=ANY(%s)", (COMPANY, sorted(POSITION_CODES)))
        cur.execute("DELETE FROM companies WHERE company_code=%s AND metadata->>'marker'=%s", (WRONG_COMPANY, MARKER))
        conn.commit()
    for phone in phones:
        path = Path(str(app.WORKSPACE)) / "data" / "candidates" / phone
        if path.exists():
            shutil.rmtree(path)
    after = {
        "applications": _count(app, "applications", "app_key=ANY(%s)", (app_keys,)) if app_keys else 0,
        "documents": _count(app, "candidate_documents", "app_key=ANY(%s)", (app_keys,)) if app_keys else 0,
        "inbound": _count(app, "whatsapp_inbound_messages", "provider=%s AND provider_message_id LIKE %s", ("cleanup-proof", f"{MARKER}%")),
        "tasks": _count(app, "hr_tasks", "metadata->>'app_key'=ANY(%s)", (app_keys,)) if app_keys else 0,
    }
    return {"before": before, "after": after}


def _artifact_sha() -> tuple[str, dict[str, str]]:
    paths = [
        ROOT / "app.py",
        ROOT / "recruiting_lifecycle.py",
        ROOT / "action_registry.py",
        ROOT / "offer_service.py",
        ROOT / "candidate_messages.py",
        ROOT / "smoke-test-candidate-whatsapp-cleanup.py",
        Path(__file__).resolve(),
    ]
    members: dict[str, str] = {}
    bundle = hashlib.sha256()
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        members[str(path.relative_to(ROOT))] = digest
        bundle.update(str(path.relative_to(ROOT)).encode())
        bundle.update(b"\0")
        bundle.update(bytes.fromhex(digest))
    return bundle.hexdigest(), members


def main() -> int:
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() != "staging":
        raise SystemExit("REFUSE: WATHEFNI_ENV must be staging")
    if str(os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() not in {"dry_run", "dry-run", "simulate", "simulated"}:
        raise SystemExit("REFUSE: delivery mode must be dry_run")
    if str(os.environ.get("WATHEFNI_CANONICAL_LIFECYCLE") or "").lower() not in {"1", "true", "yes", "on", "enabled"}:
        raise SystemExit("REFUSE: canonical lifecycle must be explicitly enabled")

    import app
    import candidate_messages

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise SystemExit("REFUSE: runtime/database identity is not staging")
    OUT.mkdir(parents=True, exist_ok=True)
    fixture_dir = OUT / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "valid_en": _docx(fixture_dir / "valid-en.docx", "Aisha Al Salem\nEmail: aisha@example.com\nPhone: +965 50000000\nProfessional experience in operations and compliance for eight years.\nSkills: Excel, reporting, stakeholder communication."),
        "updated_en": _docx(fixture_dir / "updated-en.docx", "Aisha Al Salem\nEmail: aisha@example.com\nPhone: +965 50000000\nUpdated professional experience in operations, compliance, reporting, and project delivery.\nSkills: Excel, SQL, stakeholder communication."),
        "valid_ar": _docx(fixture_dir / "valid-ar.docx", "مريم السالم\nالبريد: mariam@example.com\nالهاتف: +965 51111111\nخبرة مهنية في العمليات والامتثال وإدارة المشاريع لمدة ثماني سنوات.\nالمهارات: التقارير والتحليل والتواصل."),
        "updated_ar": _docx(fixture_dir / "updated-ar.docx", "مريم السالم\nالبريد: mariam@example.com\nالهاتف: +965 51111111\nخبرة محدثة في العمليات والامتثال وإدارة المشاريع والتحليل.\nالمهارات: التقارير والتحليل والتواصل وإكسل."),
        "mixed": _docx(fixture_dir / "mixed.docx", "Noor Al Sabah نور الصباح\nEmail: noor@example.com\nPhone: +965 52222222\nخبرة في إدارة العمليات وتحليل البيانات. Experience in operations and data analysis.\nSkills المهارات: Excel, SQL, reporting."),
        "blank_docx": _docx(fixture_dir / "blank.docx", ""),
        "corrupt_docx": fixture_dir / "corrupt.docx",
        "valid_pdf": _pdf(fixture_dir / "valid.pdf", "Khalid Al Ahmad\nEmail khalid@example.com\nPhone +965 53333333\nOperations and finance professional with ten years of experience in reporting, controls, planning, and stakeholder management."),
        "blank_pdf": _pdf(fixture_dir / "blank.pdf", ""),
        "corrupt_pdf": fixture_dir / "corrupt.pdf",
        "password_pdf": _pdf(fixture_dir / "password.pdf", "Protected candidate resume with professional experience and contact details.", encrypted=True),
        "image": _image(fixture_dir / "image.png", "Dana Al Ali\nEmail dana@example.com\nPhone +965 54444444\nProfessional operations experience reporting analysis compliance projects"),
        "unsupported": fixture_dir / "unsupported.txt",
    }
    files["corrupt_docx"].write_bytes(b"not-a-docx")
    files["corrupt_pdf"].write_bytes(b"%PDF-1.4 corrupt")
    files["unsupported"].write_text("text-only CV ingestion is intentionally unsupported", encoding="utf-8")

    proof = Proof()
    original_workspace_tool = app.run_workspace_tool
    original_profile_extractor = app.extract_structured_candidate_profile_from_cv_text
    app.run_workspace_tool = lambda args, timeout=60: _fake_workspace_start(app, args, timeout)
    app.extract_structured_candidate_profile_from_cv_text = lambda text, application: None
    journeys: list[dict[str, Any]] = []
    negatives: dict[str, Any] = {}
    matrix: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        _cleanup(app)
        _seed(app)
        matrix = _validation_matrix(app, proof, files)
        journeys.append(_journey(app, proof, locale="en", mode="code", index=1, files=files))
        journeys.append(_journey(app, proof, locale="en", mode="role", index=2, files=files))
        journeys.append(_journey(app, proof, locale="ar", mode="code", index=3, files=files))
        journeys.append(_journey(app, proof, locale="ar", mode="role", index=4, files=files))
        negatives = _negative_paths(app, proof, files)
    finally:
        app.run_workspace_tool = original_workspace_tool
        app.extract_structured_candidate_profile_from_cv_text = original_profile_extractor
        cleanup = _cleanup(app)

    artifact_sha, member_hashes = _artifact_sha()
    positive_passed = sum(1 for row in proof.positive if row["ok"])
    negative_passed = sum(1 for row in proof.negative if row["ok"])
    all_ok = positive_passed == len(proof.positive) and negative_passed == len(proof.negative) and all(v == 0 for v in cleanup["after"].values())
    evidence = {
        "proof": MARKER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "staging",
        "database_identity": identity.public(),
        "delivery_mode": "dry_run",
        "real_external_messages_sent": 0,
        "canonical_lifecycle_enabled": app.canonical_lifecycle_enabled(),
        "artifact_sha256": artifact_sha,
        "artifact_members": member_hashes,
        "template_version": candidate_messages.CATALOG_VERSION,
        "message_inventory": candidate_messages.inventory(),
        "positive": {"passed": positive_passed, "total": len(proof.positive), "checks": proof.positive},
        "negative": {"passed": negative_passed, "total": len(proof.negative), "checks": proof.negative},
        "cv_validation": matrix,
        "journeys": journeys,
        "negative_paths": negatives,
        "cleanup": cleanup,
        "quarantine": {"legacy_ai_recruiter_listener_present": False, "verified_separately": True},
        "all_ok": all_ok,
    }
    evidence_path = OUT / "STAGING_PROOF.json"
    evidence_path.write_text(json.dumps(_json(evidence), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "MESSAGE_INVENTORY.json").write_text(
        json.dumps(candidate_messages.inventory(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "all_ok": all_ok,
                "artifact_sha256": artifact_sha,
                "positive": f"{positive_passed}/{len(proof.positive)}",
                "negative": f"{negative_passed}/{len(proof.negative)}",
                "cleanup": cleanup["after"],
                "evidence": str(evidence_path),
            },
            sort_keys=True,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
