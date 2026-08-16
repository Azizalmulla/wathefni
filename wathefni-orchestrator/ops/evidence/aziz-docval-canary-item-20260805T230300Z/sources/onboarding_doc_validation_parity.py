#!/usr/bin/env python3
"""Onboarding Document Validation Parity — employee-app upload gate.

Reuses the shared WhatsApp classify/verify/identity stack (Mistral for identity;
Kuwait/GCC structuring for contracts/certs). No GPT fallback.

Soft-gate (default canary):
  * Clear mismatches → block before store with a correction message
  * Uncertain / low-confidence → allow submit → processing + HR-review flags
Hard-gate (separate flag, default off):
  * Also blocks WhatsApp-equivalent needs_review / identity_unverified / low conf

Does **not** change Wave 2A lifecycle transitions when allowing a submit.
Governed versions remain append-only; HR retains final approval authority.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

_ON = frozenset({"1", "true", "yes", "on", "enabled"})

FLAG_SOFT = "WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT"
FLAG_HARD = "WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD"
FLAG_COMPANIES = "WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES"
FLAG_ALLOWLIST = "WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST"

MEDIA_ITEMS = frozenset(
    {
        "civil_id",
        "passport",
        "personal_photo",
        "medical",
        "medical_check",
        "education_cert",
        "employment_contract",
        "residence",
        "residency",
        "work_permit",
    }
)
IDENTITY_ITEMS = frozenset({"civil_id", "passport"})
# Disposable canary checklist ids that must run Civil ID / identity soft-gate
# without sharing the real document_type / governed version lane.
CANARY_VALIDATION_ALIASES: dict[str, str] = {
    "civil_id_canary_test": "civil_id",
}
OFFICE_EXTENSIONS = frozenset({".docx", ".pptx", ".odt", ".xlsx", ".csv"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"})
PDF_EXTENSIONS = frozenset({".pdf"})

CLEAR_BLOCK_REASONS = frozenset(
    {
        "wrong_media_item",
        "instruction_screenshot",
        "identity_mismatch",
        "unreadable",
        "wrong_format",
        "looks_like_id_not_photo",
        "looks_like_photo_not_document",
        "missing_media",
        "file_too_small",
        "expired_document",
    }
)

HARD_BLOCK_REASONS = frozenset(
    {
        "needs_review",
        "identity_unverified",
        "media_unverified",
        "missing_side",
        "required_fields_missing",
    }
)

VERIFY_CONFIDENCE_FLOOR = 0.65
IDENTITY_CONFIDENCE_FLOOR = 0.55
MIN_IMAGE_BYTES = 8 * 1024
MIN_DOC_BYTES = 2 * 1024

logger = logging.getLogger("wathefni.onboarding_doc_validation_parity")

CORRECTION_COPY: dict[str, dict[str, str]] = {
    "wrong_media_item": {
        "en": "This file doesn't look like the document we asked for. Please upload the correct document and try again.",
        "ar": "هذا الملف لا يبدو كالمستند المطلوب. يرجى رفع المستند الصحيح والمحاولة مرة أخرى.",
    },
    "instruction_screenshot": {
        "en": "That looks like a screenshot of instructions, not the document itself. Please upload the actual document.",
        "ar": "يبدو أن هذه لقطة شاشة للتعليمات وليست المستند نفسه. يرجى رفع المستند الفعلي.",
    },
    "identity_mismatch": {
        "en": "The name on this ID doesn't match your employee record. Please upload your own Civil ID or passport, or contact HR.",
        "ar": "الاسم على هذه الهوية لا يطابق سجلك الوظيفي. يرجى رفع بطاقتك المدنية أو جوازك، أو تواصل مع الموارد البشرية.",
    },
    "identity_unverified": {
        "en": "We couldn't confirm the name on this ID. Please upload a clearer photo of the document, or contact HR.",
        "ar": "تعذّر تأكيد الاسم على هذه الهوية. يرجى رفع صورة أوضح للمستند، أو تواصل مع الموارد البشرية.",
    },
    "needs_review": {
        "en": "We couldn't read this document clearly. Please upload a sharper photo or a clearer PDF and try again.",
        "ar": "تعذّر قراءة هذا المستند بوضوح. يرجى رفع صورة أوضح أو ملف PDF أوضح والمحاولة مرة أخرى.",
    },
    "unreadable": {
        "en": "This file is too unclear to read. Please retake a well-lit photo or upload a clearer scan.",
        "ar": "هذا الملف غير واضح للقراءة. يرجى إعادة التقاط صورة بإضاءة جيدة أو رفع مسح أوضح.",
    },
    "wrong_format": {
        "en": "This file type isn't accepted for this checklist item. Please upload a PDF or image as requested.",
        "ar": "نوع الملف غير مقبول لهذا البند. يرجى رفع PDF أو صورة كما هو مطلوب.",
    },
    "looks_like_id_not_photo": {
        "en": "That looks like an ID document. Please upload a clear personal photo of yourself instead.",
        "ar": "يبدو أن هذا مستند هوية. يرجى رفع صورة شخصية واضحة لك بدلاً منه.",
    },
    "looks_like_photo_not_document": {
        "en": "That looks like a personal photo, not the requested document. Please upload the correct document.",
        "ar": "يبدو أن هذه صورة شخصية وليست المستند المطلوب. يرجى رفع المستند الصحيح.",
    },
    "missing_side": {
        "en": "Please include both sides of your Civil ID (front and back) in a clear upload.",
        "ar": "يرجى إرفاق وجهي البطاقة المدنية (الأمام والخلف) بوضوح.",
    },
    "expired_document": {
        "en": "This document appears expired. Please upload a valid document, or contact HR if you need help.",
        "ar": "يبدو أن هذا المستند منتهٍ. يرجى رفع مستند ساري، أو تواصل مع الموارد البشرية للمساعدة.",
    },
    "required_fields_missing": {
        "en": "We couldn't find required details on this document. Please upload a clearer, complete copy.",
        "ar": "تعذّر العثور على التفاصيل المطلوبة في هذا المستند. يرجى رفع نسخة أوضح وكاملة.",
    },
    "media_unverified": {
        "en": "We couldn't verify this file matches the checklist item. Please try another clearer upload.",
        "ar": "تعذّر التحقق من أن هذا الملف يطابق بند القائمة. يرجى المحاولة برفع أوضح.",
    },
    "file_too_small": {
        "en": "This file is too small or incomplete. Please upload a fuller photo or PDF.",
        "ar": "هذا الملف صغير جداً أو غير مكتمل. يرجى رفع صورة أو ملف PDF أوضح وأكمل.",
    },
    "missing_media": {
        "en": "Please attach a file before submitting.",
        "ar": "يرجى إرفاق ملف قبل الإرسال.",
    },
}


def _env_on(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _ON


def soft_enabled() -> bool:
    return _env_on(FLAG_SOFT)


def hard_enabled() -> bool:
    return _env_on(FLAG_HARD)


def allowed_companies() -> set[str]:
    raw = (os.environ.get(FLAG_COMPANIES) or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def employee_allowlist() -> set[str]:
    raw = (os.environ.get(FLAG_ALLOWLIST) or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def validation_enabled(*, company_code: str | None, employee_key: str | None) -> bool:
    if not soft_enabled() and not hard_enabled():
        return False
    company = (company_code or "").strip().upper()
    companies = allowed_companies()
    if companies and company not in companies:
        return False
    allow = employee_allowlist()
    if allow and str(employee_key or "").strip() not in allow:
        return False
    return True


def gate_mode() -> str:
    if hard_enabled():
        return "hard"
    if soft_enabled():
        return "soft"
    return "off"


def canonical_validation_item(item_id: str) -> str:
    raw = str(item_id or "").strip().lower()
    return CANARY_VALIDATION_ALIASES.get(raw, raw)


def correction_message(reason: str | None, *, locale: str = "en") -> str:
    lang = "ar" if str(locale or "").lower().startswith("ar") else "en"
    pack = CORRECTION_COPY.get(str(reason or ""), CORRECTION_COPY["needs_review"])
    return pack[lang]


def document_class_for_item(item_id: str) -> str:
    item = canonical_validation_item(item_id)
    if item in IDENTITY_ITEMS or item in {"residence", "residency", "work_permit", "medical", "medical_check"}:
        return "identity"
    if item in {"employment_contract", "contract_amendment"}:
        return "contract"
    if item == "education_cert":
        return "education"
    if item == "personal_photo":
        return "personal_photo"
    return "onboarding_document"


def resolve_reading_route(*, item_id: str, extension: str, mime_type: str | None = None) -> dict[str, Any]:
    ext = (extension or "").lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    file_type = ext.lstrip(".") or (mimetypes.guess_extension(mime_type or "") or "").lstrip(".")
    doc_class = document_class_for_item(item_id)
    route: dict[str, Any] = {
        "document_class": doc_class,
        "file_type": file_type,
        "extension": ext,
        "reading_route": "mistral_or_shared",
        "gpt_auto_ocr_fallback": False,
    }
    try:
        import document_processing_foundation as foundation

        mapped_class = {
            "identity": "identity",
            "contract": "contracts",
            "education": "education",
            "personal_photo": "identity",
        }.get(doc_class, "contracts")
        found = foundation.resolve_route(document_class=mapped_class, file_type=file_type or "pdf")
        if found:
            route.update(found)
        route["gpt_auto_ocr_fallback"] = False
        if foundation.gpt_auto_ocr_fallback_forbidden():
            route["gpt_fallback_forbidden"] = True
        if ext in PDF_EXTENSIONS and doc_class in {"contract", "education"}:
            route["hybrid_mode"] = foundation.hybrid_mode()
            route["hybrid_applicable"] = bool(foundation.hybrid_mode())
    except Exception:
        logger.exception("resolve_reading_route foundation failed item=%s", item_id)
        route["hybrid_applicable"] = False
    if ext in OFFICE_EXTENSIONS:
        route["anydoc_applicable"] = True
        try:
            import anydoc_office_authority as anydoc

            route["anydoc_mode"] = anydoc.authority_mode()
            route["anydoc_role"] = anydoc.role_for_extension(ext)
        except Exception:
            route["anydoc_mode"] = "off"
    return route


def _quality_issues(*, item_id: str, extension: str, size_bytes: int, media: dict[str, Any] | None) -> list[str]:
    issues: list[str] = []
    ext = (extension or "").lower()
    item = canonical_validation_item(item_id)
    min_bytes = MIN_IMAGE_BYTES if ext in IMAGE_EXTENSIONS or item == "personal_photo" else MIN_DOC_BYTES
    if size_bytes < min_bytes:
        issues.append("file_too_small")
    if item == "personal_photo" and ext in PDF_EXTENSIONS | OFFICE_EXTENSIONS:
        issues.append("wrong_format")
    if isinstance(media, dict) and str(media.get("unreadable_reason") or "").strip():
        issues.append("unreadable")
    return issues


def _side_issue(item_id: str, extraction: dict[str, Any] | None) -> str | None:
    if canonical_validation_item(item_id) != "civil_id":
        return None
    if not isinstance(extraction, dict):
        return None
    side = str(extraction.get("side") or "").lower()
    fields = extraction.get("fields") if isinstance(extraction.get("fields"), dict) else {}
    if not side and isinstance(fields.get("side"), dict):
        side = str(fields["side"].get("value") or "").lower()
    if side == "back":
        return "missing_side"
    return None


def _expiry_issue(extraction: dict[str, Any] | None) -> str | None:
    if not isinstance(extraction, dict):
        return None
    from datetime import date, datetime

    raw = extraction.get("expiry_date") or extraction.get("expiry_date_parsed")
    fields = extraction.get("fields") if isinstance(extraction.get("fields"), dict) else {}
    cell = fields.get("expiry_date")
    if isinstance(cell, dict) and cell.get("value"):
        raw = cell.get("value")
    if not raw:
        issues = extraction.get("validation_issues") or extraction.get("issues") or []
        if isinstance(issues, list) and any("expiry_before_issue" in str(i) for i in issues):
            return "expired_document"
        return None
    try:
        if isinstance(raw, date) and not isinstance(raw, datetime):
            expiry = raw
        else:
            expiry = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    if expiry < date.today():
        return "expired_document"
    return None


def _required_fields_issue(item_id: str, extraction: dict[str, Any] | None) -> str | None:
    if not isinstance(extraction, dict):
        return None
    if str(item_id or "").lower() not in IDENTITY_ITEMS:
        return None
    if str(extraction.get("extraction_status") or "") == "needs_review":
        return None
    name = extraction.get("full_name") or extraction.get("full_name_en") or extraction.get("full_name_ar")
    number = extraction.get("document_number")
    try:
        conf = float(extraction.get("confidence") or 0)
    except Exception:
        conf = 0.0
    if not name and not number and conf >= IDENTITY_CONFIDENCE_FLOOR:
        return "required_fields_missing"
    return None


def _run_anydoc_assist(path: str, extension: str) -> dict[str, Any] | None:
    if (extension or "").lower() not in OFFICE_EXTENSIONS:
        return None
    try:
        import anydoc_office_authority as anydoc

        if anydoc.authority_enabled():
            return anydoc.maybe_run_and_attach(path, extension=extension)
        import anydoc_office_shadow as shadow

        if hasattr(shadow, "run_anydoc_office_shadow"):
            return shadow.run_anydoc_office_shadow(path)
    except Exception:
        logger.exception("anydoc assist failed")
    return None


def _run_hybrid_pdf_assist(path: str) -> dict[str, Any] | None:
    try:
        import document_processing_foundation as foundation

        if not foundation.hybrid_mode():
            return None
        import local_hybrid_pdf_engine as hybrid

        result = hybrid.extract_pdf_hybrid(path)
        if isinstance(result, dict):
            result["gpt_used"] = False
            return result
        # Some engine versions return a dataclass / HybridEngineResult.
        return {
            "ok": bool(getattr(result, "ok", True)),
            "engine": str(getattr(result, "engine", None) or "local_hybrid_pdf_engine"),
            "gpt_used": False,
        }
    except Exception:
        logger.exception("hybrid pdf assist failed")
        return None


def evaluate_employee_upload(
    *,
    employee: dict[str, Any],
    item_id: str,
    media: dict[str, Any],
    filename: str | None = None,
    size_bytes: int = 0,
    extension: str = "",
    locale: str = "en",
    verify_fn: Any | None = None,
    classify_fn: Any | None = None,
    identity_fn: Any | None = None,
) -> dict[str, Any]:
    company = str(employee.get("company_code") or "").upper()
    key = str(employee.get("employee_key") or "")
    item_raw = str(item_id or "").strip()
    item = canonical_validation_item(item_raw)
    ext = (extension or Path(str(filename or "")).suffix or "").lower()
    mode = gate_mode()
    out: dict[str, Any] = {
        "ok": True,
        "decision": "allow",
        "reason": None,
        "gate": mode,
        "item_id": item_raw,
        "validation_item_id": item,
        "gpt_used": False,
        "authoritative": False,
        "hr_confirmation_required": True,
        "quality_issues": [],
        "route": resolve_reading_route(item_id=item, extension=ext, mime_type=str(media.get("type") or "")),
        "message": None,
        "message_en": None,
        "message_ar": None,
        "verification": None,
        "extraction": None,
        "identity_check": None,
        "assists": {},
    }
    if mode == "off" or not validation_enabled(company_code=company, employee_key=key):
        out["gate"] = "off"
        return out

    quality = _quality_issues(item_id=item, extension=ext, size_bytes=size_bytes, media=media)
    out["quality_issues"] = quality
    if "file_too_small" in quality:
        return _block(out, "file_too_small", locale=locale)
    if "wrong_format" in quality:
        return _block(out, "wrong_format", locale=locale)
    if "unreadable" in quality:
        return _block(out, "unreadable", locale=locale)

    assists: dict[str, Any] = {}
    path = str(media.get("path") or "")
    if path and ext in PDF_EXTENSIONS and out["route"].get("hybrid_applicable"):
        hybrid = _run_hybrid_pdf_assist(path)
        if isinstance(hybrid, dict):
            assists["hybrid_pdf"] = {
                "ok": bool(hybrid.get("ok", True)),
                "engine": hybrid.get("engine") or "local_hybrid_pdf_engine",
                "gpt_used": False,
            }
    if path and ext in OFFICE_EXTENSIONS:
        anydoc = _run_anydoc_assist(path, ext)
        if anydoc:
            assists["anydoc"] = {"attached": True, "gpt_used": False}
    out["assists"] = assists

    verify = verify_fn
    classify = classify_fn
    identity = identity_fn

    def _ensure_app_helpers() -> None:
        nonlocal verify, classify, identity
        if verify is not None and classify is not None and identity is not None:
            return
        import app as _app

        if verify is None:
            verify = _app.verify_onboarding_media_item
        if classify is None:
            classify = _app.classify_onboarding_media_upload
        if identity is None:
            identity = _app.validate_onboarding_document_identity

    if item == "personal_photo":
        if ext not in IMAGE_EXTENSIONS:
            return _block(out, "wrong_format", locale=locale)
        if classify is None:
            _ensure_app_helpers()
        try:
            classified = classify(
                str(filename or ""),
                media,
                ["civil_id", "passport", "personal_photo"],
                company_code=company,
                subject_key=key,
            )
            out["verification"] = classified
            detected = str((classified or {}).get("detected_item") or "").strip()
            conf = float((classified or {}).get("confidence") or 0)
            if detected in IDENTITY_ITEMS and conf >= VERIFY_CONFIDENCE_FLOOR:
                return _block(out, "looks_like_id_not_photo", locale=locale)
        except Exception:
            logger.exception("personal_photo classify failed; fail-open soft")
            if mode == "hard":
                return _uncertain(out, "media_unverified", locale=locale)
        return _allow(out)

    if item not in MEDIA_ITEMS:
        return _allow(out)

    if verify is None or identity is None:
        _ensure_app_helpers()
    try:
        verification = verify(
            item,
            str(filename or ""),
            media,
            company_code=company,
            subject_key=key,
        )
    except Exception:
        logger.exception("verify failed item=%s; fail-open soft", item)
        verification = None

    out["verification"] = verification
    if not verification:
        if mode == "hard":
            return _block(out, "media_unverified", locale=locale)
        return _uncertain(out, "media_unverified", locale=locale)

    try:
        confidence = float(verification.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    detected = str(verification.get("detected_item") or "").strip()
    status = str(verification.get("extraction_status") or "").strip()
    matches = verification.get("matches_expected_item") is True

    if detected == "instruction_screenshot":
        return _block(out, "instruction_screenshot", locale=locale)
    if (
        detected == "personal_photo"
        and item in IDENTITY_ITEMS | {"employment_contract", "education_cert"}
        and confidence >= VERIFY_CONFIDENCE_FLOOR
    ):
        return _block(out, "looks_like_photo_not_document", locale=locale)

    if detected and detected != item and confidence >= VERIFY_CONFIDENCE_FLOOR and not matches:
        return _block(out, "wrong_media_item", locale=locale)

    if status == "needs_review" and confidence < VERIFY_CONFIDENCE_FLOOR:
        if mode == "hard":
            return _block(out, "needs_review", locale=locale)
        return _uncertain(out, "needs_review", locale=locale)

    if not matches or confidence < VERIFY_CONFIDENCE_FLOOR:
        if mode == "hard":
            reason = "wrong_media_item" if detected and detected != item else "needs_review"
            return _block(out, reason, locale=locale)
        return _uncertain(out, "needs_review", locale=locale)

    extraction = None
    if item in IDENTITY_ITEMS or item in {"education_cert", "employment_contract", "medical", "residence", "work_permit"}:
        try:
            ok_id, identity_reason, extraction = identity(
                employee=employee,
                item_id=item,
                text=str(filename or ""),
                media=media,
            )
        except Exception:
            logger.exception("identity validation failed item=%s", item)
            ok_id, identity_reason, extraction = False, "needs_review", None
        out["extraction"] = extraction
        if isinstance(extraction, dict):
            out["identity_check"] = extraction.get("identity_check")
            if extraction.get("gpt_used"):
                logger.error("gpt_used unexpectedly true on onboarding validation; forcing false")
            out["gpt_used"] = False

        side = _side_issue(item, extraction if isinstance(extraction, dict) else verification)
        if side:
            out["quality_issues"] = list(out.get("quality_issues") or []) + [side]
            if mode == "hard":
                return _block(out, side, locale=locale)
            out["advisory_reason"] = side

        expiry = _expiry_issue(extraction if isinstance(extraction, dict) else None)
        if expiry:
            return _block(out, expiry, locale=locale)

        req = _required_fields_issue(item, extraction if isinstance(extraction, dict) else None)
        if req:
            if mode == "hard":
                return _block(out, req, locale=locale)
            return _uncertain(out, req, locale=locale)

        if item in IDENTITY_ITEMS:
            if identity_reason == "identity_mismatch":
                return _block(out, "identity_mismatch", locale=locale)
            if not ok_id:
                if mode == "hard":
                    return _block(out, identity_reason or "identity_unverified", locale=locale)
                return _uncertain(out, identity_reason or "identity_unverified", locale=locale)

    if out.get("advisory_reason"):
        return _uncertain(out, str(out["advisory_reason"]), locale=locale)
    return _allow(out)


def _with_messages(out: dict[str, Any], reason: str, *, locale: str) -> dict[str, Any]:
    out["reason"] = reason
    out["message_en"] = correction_message(reason, locale="en")
    out["message_ar"] = correction_message(reason, locale="ar")
    out["message"] = correction_message(reason, locale=locale)
    return out


def _allow(out: dict[str, Any]) -> dict[str, Any]:
    out["ok"] = True
    out["decision"] = "allow"
    out["reason"] = None
    return out


def _uncertain(out: dict[str, Any], reason: str, *, locale: str) -> dict[str, Any]:
    out["ok"] = True
    out["decision"] = "allow_uncertain"
    out["hr_review_recommended"] = True
    return _with_messages(out, reason, locale=locale)


def _block(out: dict[str, Any], reason: str, *, locale: str) -> dict[str, Any]:
    out["ok"] = False
    out["decision"] = "block"
    return _with_messages(out, reason, locale=locale)


def should_block(result: dict[str, Any]) -> bool:
    return str(result.get("decision") or "") == "block"


def http_error_detail(result: dict[str, Any], *, locale: str = "en") -> dict[str, Any]:
    reason = str(result.get("reason") or "needs_review")
    return {
        "error": f"document_validation_{reason}",
        "message": result.get("message") or correction_message(reason, locale=locale),
        "message_en": result.get("message_en") or correction_message(reason, locale="en"),
        "message_ar": result.get("message_ar") or correction_message(reason, locale="ar"),
        "reason": reason,
        "gate": result.get("gate"),
        "detected_item": (result.get("verification") or {}).get("detected_item"),
        "validation": {
            "decision": result.get("decision"),
            "confidence": (result.get("verification") or {}).get("confidence"),
            "route": result.get("route"),
            "gpt_used": False,
        },
    }


def attach_lifecycle_meta(existing_meta: dict[str, Any] | None, result: dict[str, Any]) -> dict[str, Any]:
    meta = dict(existing_meta or {})
    meta["doc_validation"] = {
        "gate": result.get("gate"),
        "decision": result.get("decision"),
        "reason": result.get("reason"),
        "hr_review_recommended": bool(
            result.get("hr_review_recommended") or result.get("decision") == "allow_uncertain"
        ),
        "detected_item": (result.get("verification") or {}).get("detected_item"),
        "confidence": (result.get("verification") or {}).get("confidence"),
        "identity_check": result.get("identity_check"),
        "quality_issues": result.get("quality_issues") or [],
        "route": result.get("route"),
        "assists": result.get("assists") or {},
        "gpt_used": False,
    }
    return meta
