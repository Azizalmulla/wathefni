#!/usr/bin/env python3
"""Controlled channel-authority cutover for WA unsolicited, manual, and email.

Default OFF. Tenant allowlist required. Does not cut over Job Stage B.
Does not enable verified-job-binding ENFORCE.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import inbound_cv_adapters as adapters
import inbound_cv_intake as intake
import inbound_cv_processing as processing
import inbound_cv_wave4 as wave4
import candidate_knowledge_wave4 as ck_w4
from intake_malware_scanner import build_malware_scanner_from_env

CUTOVER_VERSION = "unified-inbound-cv-wa-manual-email-cutover-v1"
FEATURE_WA_UNSOLICITED = "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED"
FEATURE_MANUAL = "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL"
FEATURE_EMAIL = "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL"
FEATURE_TENANTS = "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS"
DURABLE_ROOT_ENV = "WATHEFNI_UNIFIED_INTAKE_DURABLE_ROOT"

ALLOWED_SUFFIXES = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_company(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum() or ch in {"_", "-"})


def tenant_allowed(company_code: str, environ: dict[str, str] | None = None) -> bool:
    company = _safe_company(company_code)
    raw = str(_env(environ).get(FEATURE_TENANTS) or "").strip()
    if not raw:
        return False
    allowed = {_safe_company(part) for part in raw.replace(";", ",").split(",") if part.strip()}
    return company in allowed


def wa_unsolicited_authority_enabled(
    company_code: str, environ: dict[str, str] | None = None
) -> bool:
    return _truthy(_env(environ).get(FEATURE_WA_UNSOLICITED)) and tenant_allowed(
        company_code, environ
    )


def manual_authority_enabled(company_code: str, environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_MANUAL)) and tenant_allowed(company_code, environ)


def email_authority_enabled(company_code: str, environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_EMAIL)) and tenant_allowed(company_code, environ)


def durable_root(environ: dict[str, str] | None = None) -> Path:
    raw = str(_env(environ).get(DURABLE_ROOT_ENV) or "/opt/wathefni/var/intake-durable").strip()
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _guess_suffix(filename: str | None, mime: str | None) -> str:
    name = str(filename or "").strip().lower()
    if "." in name:
        suf = "." + name.rsplit(".", 1)[-1]
        if suf in ALLOWED_SUFFIXES:
            return suf
    mime_n = str(mime or "").strip().lower()
    if "pdf" in mime_n:
        return ".pdf"
    if "wordprocessingml" in mime_n or mime_n.endswith("docx"):
        return ".docx"
    if "png" in mime_n:
        return ".png"
    if "jpeg" in mime_n or "jpg" in mime_n:
        return ".jpg"
    if "webp" in mime_n:
        return ".webp"
    return ""


def validate_media_type(*, filename: str | None, mime: str | None) -> dict[str, Any]:
    suf = _guess_suffix(filename, mime)
    mime_n = str(mime or "").strip().lower()
    if suf not in ALLOWED_SUFFIXES and not (
        mime_n.startswith("image/") or mime_n in ALLOWED_MIMES
    ):
        return {"ok": False, "error": "unsupported_file_type", "suffix": suf, "mime": mime_n}
    return {"ok": True, "suffix": suf or ".bin", "mime": mime_n}


def store_durable_bytes(
    *,
    company_code: str,
    channel: str,
    document_id: str,
    data: bytes,
    suffix: str,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    company = _safe_company(company_code)
    dest_dir = durable_root(environ) / channel / company
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{document_id}{suffix}"
    dest.write_bytes(data)
    dest.chmod(0o640)
    digest = hashlib.sha256(data).hexdigest()
    return {
        "ok": True,
        "path": str(dest),
        "content_sha256": digest,
        "size_bytes": len(data),
        "document_id": document_id,
    }


def store_durable_path(
    *,
    company_code: str,
    channel: str,
    document_id: str,
    source_path: str | Path,
    suffix: str,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    src = Path(source_path)
    if not src.is_file():
        return {"ok": False, "error": "source_missing", "path": str(src)}
    data = src.read_bytes()
    if not data:
        return {"ok": False, "error": "empty_file"}
    return store_durable_bytes(
        company_code=company_code,
        channel=channel,
        document_id=document_id,
        data=data,
        suffix=suffix,
        environ=environ,
    )


def scan_file(path: str | Path) -> dict[str, Any]:
    scanner = build_malware_scanner_from_env()
    result = scanner.scan_path(Path(path))
    record = result.to_record() if hasattr(result, "to_record") else {
        "state": getattr(result, "state", "unavailable"),
        "reason_code": getattr(result, "reason_code", None),
        "engine": getattr(result, "engine", "unknown"),
    }
    state = str(record.get("state") or "").lower()
    if state == "malware":
        return {"ok": False, "error": "malware_rejected", "scan": record}
    if state != "clean":
        return {"ok": False, "error": "scanner_unavailable_fail_closed", "scan": record}
    return {"ok": True, "scan": record}


def needs_ocr_for(*, mime: str | None, suffix: str, filename: str | None = None) -> bool:
    mime_n = str(mime or "").lower()
    name = str(filename or "").lower()
    if mime_n.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return True
    if "scan" in name:
        return True
    return False


def enqueue_ck_index_job(
    cur: Any,
    *,
    company_code: str,
    candidate_ref: str,
    cv_version_id: str | None,
    content_sha256: str | None,
    reason: str,
) -> dict[str, Any]:
    """Enqueue searchable non-actionable CK index job for person:/subject: refs."""

    company = _safe_company(company_code)
    ref = str(candidate_ref or "").strip()
    if not ref:
        return {"ok": False, "error": "candidate_ref_required"}
    digest = str(content_sha256 or cv_version_id or ref)
    idem = f"cutover:{company}:{ref}:{digest}:{reason}"
    source_key = f"src_{hashlib.sha256(idem.encode()).hexdigest()[:40]}"
    app_key_sentinel = f"tp:{ref}"
    cur.execute(
        """
        INSERT INTO candidate_knowledge_index_jobs (
          job_id, company_code, app_key, candidate_ref, document_version_id,
          source_key, reason, idempotency_key, status, attempts, dead_letter
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,'pending',0,false
        )
        ON CONFLICT (company_code, idempotency_key) DO UPDATE
          SET updated_at=now()
        RETURNING job_id::text AS job_id, status, candidate_ref
        """,
        (
            str(uuid.uuid4()),
            company,
            app_key_sentinel[:200],
            ref,
            cv_version_id,
            source_key,
            reason,
            idem[:300],
        ),
    )
    row = cur.fetchone() or {}
    meta = ck_w4.index_meta_for_ref(
        candidate_ref=ref, actionable=False, provisional=ref.startswith("subject:")
    )
    return {"ok": True, "job": dict(row), "index_meta": meta}


def _cutover_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(_env(environ))
    for key in (
        "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE",
        "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE",
        "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER",
        "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS",
        "WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING",
        "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4",
        "WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE",
        "WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES",
        "WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS",
    ):
        env.setdefault(key, "1")
    return env


def accept_whatsapp_unsolicited(
    cur: Any,
    *,
    company_code: str,
    phone: str | None,
    provider_message_id: str,
    account_id: str | None,
    conversation_id: str | None,
    pending_id: str | None,
    media_path: str | None,
    mime_or_suffix: str | None,
    filename: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Authoritative unsolicited WhatsApp CV accept → durable Talent Pool (no Job app)."""

    company = _safe_company(company_code) or "WATHEFNI"
    if not wa_unsolicited_authority_enabled(company, environ):
        return {"ok": True, "skipped": True, "reason": "wa_unsolicited_authority_disabled"}

    env = _cutover_env(environ)
    type_check = validate_media_type(filename=filename or media_path, mime=mime_or_suffix)
    if not type_check.get("ok"):
        return {
            "ok": False,
            "rejected": True,
            "error": type_check.get("error"),
            "confirmation_key": "cv_invalid",
            "creates_job_application": False,
        }

    document_id = str(pending_id or uuid.uuid4())
    stored = store_durable_path(
        company_code=company,
        channel="whatsapp_unsolicited",
        document_id=document_id,
        source_path=str(media_path or ""),
        suffix=str(type_check.get("suffix") or ".bin"),
        environ=env,
    )
    if not stored.get("ok"):
        return {
            "ok": False,
            "rejected": True,
            "error": stored.get("error") or "durable_store_failed",
            "confirmation_key": "cv_invalid",
            "creates_job_application": False,
        }

    scanned = scan_file(stored["path"])
    if not scanned.get("ok"):
        return {
            "ok": False,
            "rejected": True,
            "error": scanned.get("error"),
            "scan": scanned.get("scan"),
            "confirmation_key": "cv_invalid",
            "creates_job_application": False,
            "durable_path": stored["path"],
        }

    ocr = needs_ocr_for(
        mime=mime_or_suffix,
        suffix=str(type_check.get("suffix") or ""),
        filename=filename or media_path,
    )
    receipt = intake.dual_write_whatsapp_receipt(
        cur,
        company_code=company,
        provider_message_id=provider_message_id,
        phone=phone,
        account_id=account_id,
        conversation_id=conversation_id,
        pending_id=pending_id,
        document_id=document_id,
        content_sha256=stored["content_sha256"],
        filename=filename or Path(str(media_path or "whatsapp-cv")).name,
        job_bound=False,
        environ=env,
    )
    subject_id = str(receipt.get("subject_id") or "")
    item_ids = list(receipt.get("item_ids") or [])
    stages: dict[str, Any] = {"skipped": True}
    if item_ids:
        stages = adapters.observe_shared_stages_for_document(
            cur,
            company_code=company,
            subject_id=str(item_ids[0]),
            content_sha256=stored["content_sha256"],
            mime_or_suffix=mime_or_suffix or str(type_check.get("suffix") or "application/pdf"),
            local_text_ok=not ocr,
            needs_ocr=ocr,
            channel="whatsapp_unsolicited",
            environ=env,
        )
        processing.record_stage_run(
            cur,
            company_code=company,
            stage="malware_scan",
            status="completed",
            subject_id=str(item_ids[0]),
            content_sha256=stored["content_sha256"],
            metadata={
                "cutover_version": CUTOVER_VERSION,
                "scan": scanned.get("scan"),
                "authoritative": True,
            },
            environ=env,
        )

    wave = wave4.after_intake_receipt(
        cur,
        company_code=company,
        subject_id=subject_id or (item_ids[0] if item_ids else None),
        phone=phone if phone and str(phone).startswith("+") else (f"+{phone}" if phone else None),
        content_sha256=stored["content_sha256"],
        document_id=document_id,
        actionable=False,
        channel="whatsapp_unsolicited",
        environ=env,
    )
    person = wave.get("person") or {}
    tp = wave.get("talent_pool") or {}
    cv = wave.get("cv_version") or {}
    ck: dict[str, Any] = {"skipped": True}
    ref = None
    if person.get("person_id"):
        ref = ck_w4.candidate_ref_from_person_id(str(person["person_id"]))
    elif subject_id:
        ref = ck_w4.candidate_ref_from_subject_id(subject_id)
    if ref:
        ck = enqueue_ck_index_job(
            cur,
            company_code=company,
            candidate_ref=ref,
            cv_version_id=str(cv.get("cv_version_id") or "") or None,
            content_sha256=stored["content_sha256"],
            reason="whatsapp_unsolicited_cutover",
        )

    return {
        "ok": True,
        "skipped": False,
        "rejected": False,
        "authoritative": True,
        "cutover_version": CUTOVER_VERSION,
        "confirmation_key": "cv_received_talent_pool",
        "creates_job_application": False,
        "requires_apply_code": False,
        "durable_path": stored["path"],
        "content_sha256": stored["content_sha256"],
        "document_id": document_id,
        "scan": scanned.get("scan"),
        "receipt": receipt,
        "shared_processing": stages,
        "wave4": wave,
        "talent_pool": {
            **(adapters.talent_pool_visibility_for_unsolicited()),
            "entry_id": tp.get("entry_id"),
            "actionable": False,
        },
        "cv_version_id": cv.get("cv_version_id"),
        "person_id": person.get("person_id"),
        "subject_id": subject_id,
        "ck_index": ck,
        "accepted_at": _now(),
    }


def accept_manual_upload(
    cur: Any,
    *,
    company_code: str,
    batch_id: str,
    content_sha256: str,
    filename: str | None,
    document_id: str | None,
    source_path: str | Path | None,
    mime_or_suffix: str | None,
    app_key: str | None,
    held_status: str | None,
    uploader_user_id: str | None = None,
    source: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Authoritative manual upload security/envelope/Talent Pool projection."""

    company = _safe_company(company_code) or "WATHEFNI"
    if not manual_authority_enabled(company, environ):
        return {"ok": True, "skipped": True, "reason": "manual_authority_disabled"}

    env = _cutover_env(environ)
    type_check = validate_media_type(filename=filename, mime=mime_or_suffix)
    if not type_check.get("ok"):
        return {"ok": False, "rejected": True, "error": type_check.get("error")}

    doc_id = str(document_id or uuid.uuid4())
    durable = None
    if source_path:
        durable = store_durable_path(
            company_code=company,
            channel="manual_upload",
            document_id=doc_id,
            source_path=source_path,
            suffix=str(type_check.get("suffix") or ".bin"),
            environ=env,
        )
        if not durable.get("ok"):
            return {"ok": False, "rejected": True, "error": durable.get("error")}
        scanned = scan_file(durable["path"])
        if not scanned.get("ok"):
            return {
                "ok": False,
                "rejected": True,
                "error": scanned.get("error"),
                "scan": scanned.get("scan"),
            }
        sha = durable["content_sha256"]
    else:
        sha = str(content_sha256 or "").strip().lower()
        if not sha:
            return {"ok": False, "rejected": True, "error": "checksum_required"}
        scanned = {"ok": True, "scan": {"state": "clean", "engine": "pre_registered"}}

    held = adapters.manual_held_by_default(auto_admit_enabled=False, explicit_role=False)
    result = adapters.adapt_manual_import(
        cur,
        company_code=company,
        batch_id=batch_id,
        content_sha256=sha,
        filename=filename,
        document_id=doc_id,
        app_key=app_key,
        held_status=held_status or held.get("status") or "needs_role",
        mime_or_suffix=mime_or_suffix or str(type_check.get("suffix") or ""),
        environ=env,
    )
    wave = result.get("wave4") or {}
    person = wave.get("person") or {}
    cv = wave.get("cv_version") or {}
    subject_id = str((result.get("receipt") or {}).get("subject_id") or "")
    ck: dict[str, Any] = {"skipped": True}
    ref = None
    if person.get("person_id"):
        ref = ck_w4.candidate_ref_from_person_id(str(person["person_id"]))
    elif subject_id:
        ref = ck_w4.candidate_ref_from_subject_id(subject_id)
    if ref:
        ck = enqueue_ck_index_job(
            cur,
            company_code=company,
            candidate_ref=ref,
            cv_version_id=str(cv.get("cv_version_id") or "") or None,
            content_sha256=sha,
            reason="manual_upload_cutover",
        )

    return {
        "ok": bool(result.get("ok")),
        "skipped": False,
        "rejected": False,
        "authoritative": True,
        "cutover_version": CUTOVER_VERSION,
        "creates_job_application": False,
        "auto_admit": False,
        "held_by_default": True,
        "held_status": held.get("status"),
        "scan": scanned.get("scan"),
        "durable": durable,
        "adapter": result,
        "ck_index": ck,
        "provenance": {
            "batch_id": batch_id,
            "uploader_user_id": uploader_user_id,
            "source": source or "manual_upload",
            "cutover_version": CUTOVER_VERSION,
        },
        "accepted_at": _now(),
    }


def pre_scan_manual_bytes(
    *,
    company_code: str,
    batch_id: str,
    filename: str,
    data: bytes,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fail-closed scan before register_imported_cv when manual authority is ON."""

    company = _safe_company(company_code) or "WATHEFNI"
    if not manual_authority_enabled(company, environ):
        return {"ok": True, "skipped": True, "reason": "manual_authority_disabled"}
    type_check = validate_media_type(filename=filename, mime=None)
    if not type_check.get("ok"):
        return {"ok": False, "rejected": True, "error": type_check.get("error")}
    if not data:
        return {"ok": False, "rejected": True, "error": "empty_file"}
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"manual-prescan:{company}:{batch_id}:{filename}"))
    stored = store_durable_bytes(
        company_code=company,
        channel="manual_upload",
        document_id=doc_id,
        data=data,
        suffix=str(type_check.get("suffix") or ".bin"),
        environ=environ,
    )
    scanned = scan_file(stored["path"])
    if not scanned.get("ok"):
        return {
            "ok": False,
            "rejected": True,
            "error": scanned.get("error"),
            "scan": scanned.get("scan"),
            "durable_path": stored["path"],
        }
    return {
        "ok": True,
        "skipped": False,
        "content_sha256": stored["content_sha256"],
        "durable_path": stored["path"],
        "document_id": doc_id,
        "scan": scanned.get("scan"),
    }


def accept_email_inbound(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    submission_id: str,
    provider_message_id: str,
    documents: list[dict[str, Any]],
    route_snapshot: dict[str, Any] | None = None,
    source_provenance: dict[str, Any] | None = None,
    sender_email: str | None = None,
    extracted_phone: str | None = None,
    extracted_email: str | None = None,
    display_name: str | None = None,
    position_code: str | None = None,
    legacy_app_key: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Authoritative unified processing for an accepted inbound email receipt.

    Preserves Postmark/provider IDs. Sender is provenance only — candidate
    identity uses extracted contacts when present, never auto-binds sender.
    """

    company = _safe_company(company_code) or "WATHEFNI"
    if not email_authority_enabled(company, environ):
        return {"ok": True, "skipped": True, "reason": "email_authority_disabled"}

    env = _cutover_env(environ)
    env.setdefault("WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE", "1")
    docs = list(documents or [])
    if not docs:
        return {"ok": False, "rejected": True, "error": "documents_required"}

    provenance = {
        **(source_provenance or {}),
        "channel": "email_inbound",
        "sender_email_provenance_only": True,
        "sender_email": sender_email,
        "cutover_version": CUTOVER_VERSION,
        "authoritative": True,
    }
    receipt = intake.dual_write_email_receipt(
        cur,
        company_code=company,
        inbound_id=inbound_id,
        submission_id=submission_id,
        provider="postmark",
        provider_message_id=provider_message_id,
        route_snapshot=route_snapshot or {},
        source_provenance=provenance,
        documents=docs,
        environ=env,
    )
    subject_id = str(receipt.get("subject_id") or "")
    item_ids = list(receipt.get("item_ids") or [])
    per_doc: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        doc_id = str(doc.get("document_id") or "")
        sha = str(doc.get("content_sha256") or "").strip().lower()
        filename = str(doc.get("filename") or doc.get("original_filename") or f"email-{idx}.pdf")
        mime = str(doc.get("mime") or doc.get("detected_mime") or doc.get("claimed_mime") or "")
        item_id = item_ids[idx] if idx < len(item_ids) else (item_ids[0] if item_ids else subject_id)
        ocr = needs_ocr_for(mime=mime, suffix=_guess_suffix(filename, mime), filename=filename)
        stages = adapters.observe_shared_stages_for_document(
            cur,
            company_code=company,
            subject_id=str(item_id),
            content_sha256=sha or None,
            mime_or_suffix=mime or filename,
            local_text_ok=not ocr,
            needs_ocr=ocr,
            channel="email_inbound",
            environ=env,
        )
        if sha:
            processing.record_stage_run(
                cur,
                company_code=company,
                stage="malware_scan",
                status="completed",
                subject_id=str(item_id),
                content_sha256=sha,
                metadata={
                    "cutover_version": CUTOVER_VERSION,
                    "scan_before_extraction": True,
                    "authoritative": True,
                    "email_inbound_id": inbound_id,
                },
                environ=env,
            )
        # Identity: extracted contacts only — never treat sender as candidate identity.
        wave = wave4.after_intake_receipt(
            cur,
            company_code=company,
            subject_id=subject_id or str(item_id),
            phone=extracted_phone,
            email=extracted_email,  # CV-derived, not envelope sender
            display_name=display_name,
            content_sha256=sha or None,
            document_id=doc_id or None,
            legacy_app_key=legacy_app_key,
            actionable=False,
            channel="email_inbound",
            environ=env,
        )
        person = wave.get("person") or {}
        tp = wave.get("talent_pool") or {}
        cv = wave.get("cv_version") or {}
        ck: dict[str, Any] = {"skipped": True}
        ref = None
        if person.get("person_id"):
            ref = ck_w4.candidate_ref_from_person_id(str(person["person_id"]))
        elif subject_id:
            ref = ck_w4.candidate_ref_from_subject_id(subject_id)
        if ref:
            ck = enqueue_ck_index_job(
                cur,
                company_code=company,
                candidate_ref=ref,
                cv_version_id=str(cv.get("cv_version_id") or "") or None,
                content_sha256=sha or None,
                reason="email_inbound_cutover",
            )
        per_doc.append(
            {
                "document_id": doc_id,
                "content_sha256": sha,
                "stages": stages,
                "wave4": wave,
                "cv_version_id": cv.get("cv_version_id"),
                "talent_pool_entry_id": tp.get("entry_id"),
                "person_id": person.get("person_id"),
                "ck_index": ck,
                "job_bound": bool(position_code),
            }
        )

    return {
        "ok": True,
        "skipped": False,
        "authoritative": True,
        "cutover_version": CUTOVER_VERSION,
        "creates_job_application": False,
        "sender_is_provenance_only": True,
        "receipt": receipt,
        "subject_id": subject_id,
        "documents": per_doc,
        "document_count": len(per_doc),
        "accepted_at": _now(),
    }


def after_email_extraction(
    cur: Any,
    *,
    company_code: str,
    content_sha256: str,
    legacy_document_id: str,
    legacy_app_key: str | None = None,
    extracted_text_hash: str | None = None,
    extraction_method: str | None = None,
    evidence_id: str | None = None,
    facts_id: str | None = None,
    person_id: str | None = None,
    subject_id: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Promote extraction into owned cv_version + TP/CK when email authority ON."""

    company = _safe_company(company_code) or "WATHEFNI"
    if not email_authority_enabled(company, environ):
        return {"ok": True, "skipped": True, "reason": "email_authority_disabled"}
    env = _cutover_env(environ)
    cv = processing.dual_write_cv_version(
        cur,
        company_code=company,
        content_sha256=content_sha256,
        legacy_document_id=legacy_document_id,
        legacy_app_key=legacy_app_key,
        extracted_text_hash=extracted_text_hash,
        extraction_method=extraction_method,
        evidence_id=evidence_id,
        facts_id=facts_id,
        person_id=person_id,
        subject_id=subject_id,
        provenance={
            "source": "email_inbound_cutover_extraction",
            "cutover_version": CUTOVER_VERSION,
            "authoritative": True,
        },
        environ=env,
    )
    wave = {"skipped": True}
    if subject_id or person_id or phone or email:
        wave = wave4.after_intake_receipt(
            cur,
            company_code=company,
            subject_id=subject_id,
            phone=phone,
            email=email,
            content_sha256=content_sha256,
            document_id=legacy_document_id,
            legacy_app_key=legacy_app_key,
            actionable=False,
            channel="email_inbound",
            environ=env,
        )
    return {
        "ok": True,
        "skipped": False,
        "authoritative": True,
        "cv_version": cv,
        "wave4": wave,
        "cutover_version": CUTOVER_VERSION,
    }


__all__ = [
    "CUTOVER_VERSION",
    "FEATURE_WA_UNSOLICITED",
    "FEATURE_MANUAL",
    "FEATURE_EMAIL",
    "FEATURE_TENANTS",
    "wa_unsolicited_authority_enabled",
    "manual_authority_enabled",
    "email_authority_enabled",
    "tenant_allowed",
    "accept_whatsapp_unsolicited",
    "accept_manual_upload",
    "accept_email_inbound",
    "after_email_extraction",
    "pre_scan_manual_bytes",
    "scan_file",
    "store_durable_path",
    "validate_media_type",
]
