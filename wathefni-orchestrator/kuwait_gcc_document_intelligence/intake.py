"""Shared omnichannel intake adapter — one processor for all channels.

Channels call this instead of empty extraction={} or channel-specific OCR.
Identity classes delegate to identity_document_extraction; contracts/education
use the qualified Kuwait/GCC Mistral path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kuwait_gcc_document_intelligence.authority import kuwait_gcc_authority_enabled
from kuwait_gcc_document_intelligence.schemas import (
    GENERATED_ONLY_TYPES,
    IDENTITY_DELEGATE_TYPES,
    STORAGE_ONLY_TYPES,
    STRUCTURING_TYPES,
    normalize_document_type,
)

# Types that run through the shared processor (identity delegate + structuring).
SHARED_INTAKE_TYPES = frozenset(
    {
        "civil_id",
        "passport",
        "residence",
        "residency",
        "residency_iqama",
        "work_permit",
        "medical",
        "medical_check",
        "medical_fitness",
        "education_cert",
        "employment_contract",
        "contract_amendment",
        "bank_certificate",
        "iban_letter",
        "bank_letter",
        "salary_transfer_letter",
    }
)

# Backward-compatible aliases → canonical storage/processing type.
CANONICAL_TYPE_MAP: dict[str, str] = {
    "residency": "residence",
    "residency_iqama": "residence",
    "residence": "residence",
    "medical_check": "medical",
    "medical_fitness": "medical",
    "medical": "medical",
    "education_certificate": "education_cert",
    "education": "education_cert",
    "edu_cert": "education_cert",
    "education_cert": "education_cert",
    "employment_agreement": "employment_contract",
    "contract": "employment_contract",
    "employment_contract": "employment_contract",
    "contract_amendment": "contract_amendment",
    "amendment": "contract_amendment",
    "bank_certificate": "bank_certificate",
    "iban_letter": "bank_certificate",
    "bank_letter": "bank_certificate",
    "salary_transfer_letter": "bank_certificate",
    "bank_cert": "bank_certificate",
    "kw_iban_letter": "bank_certificate",
}

PRESERVED_ALIASES = frozenset(CANONICAL_TYPE_MAP.keys()) - frozenset(CANONICAL_TYPE_MAP.values())


def canonical_document_type(document_type: str | None) -> str:
    raw = normalize_document_type(document_type)
    return CANONICAL_TYPE_MAP.get(raw, raw)


def is_shared_intake_type(document_type: str | None) -> bool:
    raw = str(document_type or "").strip().lower()
    canon = canonical_document_type(raw)
    return raw in SHARED_INTAKE_TYPES or canon in SHARED_INTAKE_TYPES or canon in STRUCTURING_TYPES


def _media_with_path(media: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(media, dict):
        return media
    out = dict(media)
    if not out.get("path") and out.get("local_path"):
        out["path"] = out["local_path"]
    return out


def _needs_review_stub(
    *,
    channel: str,
    document_type: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "extraction_status": "needs_review",
        "extraction_error": reason,
        "document_type": document_type,
        "authoritative": False,
        "hr_confirmation_required": True,
        "gpt_used": False,
        "provider": None,
        "channel": channel,
        "confidence": 0.0,
    }


def shared_channel_extraction(
    *,
    document_type: str | None,
    media: dict[str, Any] | None,
    company_code: str | None = None,
    subject_key: str | None = None,
    channel: str = "shared",
    expected_item: str | None = None,
    mode: str = "extract",
    country_code: str = "KW",
    text: str | None = None,
    allowed_items: list[str] | None = None,
) -> dict[str, Any]:
    """Single entry used by WhatsApp, ESS, Hub, email, and backfill."""

    del text  # reserved for future plaintext hints; never sent to GPT
    canon = canonical_document_type(document_type or expected_item)
    if mode == "classify" and not canon:
        from kuwait_gcc_document_intelligence.extraction import process_document

        media_n = _media_with_path(media)
        allowed = [canonical_document_type(x) for x in (allowed_items or [])]
        # Prefer identity classifier for identity-heavy allowlists; shared process_document
        # routes empty-type classify through identity classify with allowed_items.
        result = process_document(
            media=media_n,
            document_type=None,
            allowed_items=allowed or None,
            company_code=company_code,
            subject_key=subject_key,
            country_code=country_code,
            channel=channel,
            mode="classify",
        )
        out = dict(result or {})
        if out.get("detected_item"):
            out["detected_item"] = canonical_document_type(out.get("detected_item"))
        out["gpt_used"] = False
        out["channel"] = channel
        return out

    if not canon:
        return _needs_review_stub(channel=channel, document_type="unknown", reason="missing_document_type")

    if canon in GENERATED_ONLY_TYPES:
        return {
            "ok": True,
            "extraction_status": "skipped_generated_only",
            "document_type": canon,
            "authoritative": False,
            "gpt_used": False,
            "channel": channel,
        }

    if canon in STORAGE_ONLY_TYPES and canon not in STRUCTURING_TYPES:
        return {
            "ok": True,
            "extraction_status": "storage_only",
            "document_type": canon,
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "channel": channel,
            "fields": {},
        }

    if not is_shared_intake_type(canon):
        return _needs_review_stub(
            channel=channel,
            document_type=canon,
            reason=f"unsupported_intake_type:{canon}",
        )

    # Identity always uses live identity authority (separate kill switch).
    # Structuring types require Kuwait/GCC authority.
    from kuwait_gcc_document_intelligence.schemas import IDENTITY_DELEGATE_TYPES as _ID

    if canon not in _ID and not kuwait_gcc_authority_enabled(company_code=company_code):
        return _needs_review_stub(
            channel=channel,
            document_type=canon,
            reason="kuwait_gcc_authority_disabled",
        )

    # For identity delegate when identity authority is off, still needs_review (no GPT).
    if canon in IDENTITY_DELEGATE_TYPES:
        import identity_document_extraction as ide

        if not ide.identity_mistral_authority_enabled(company_code=company_code):
            return _needs_review_stub(
                channel=channel,
                document_type=canon,
                reason="identity_authority_disabled",
            )

    from kuwait_gcc_document_intelligence.extraction import process_document

    media_n = _media_with_path(media)
    # Processing type for identity module: residency alias retained for identity schema enum.
    process_type = "residency" if canon == "residence" else canon
    result = process_document(
        media=media_n,
        document_type=process_type,
        expected_item=canonical_document_type(expected_item) if expected_item else None,
        allowed_items=[canonical_document_type(x) for x in (allowed_items or [])] or None,
        company_code=company_code,
        subject_key=subject_key,
        country_code=country_code,
        channel=channel,
        mode=mode,
    )
    out = dict(result or {})
    out["document_type"] = canon if out.get("document_type") in {None, "residency", "residence"} or canon == "residence" else (
        canonical_document_type(out.get("document_type")) or canon
    )
    if canon == "residence":
        out["document_type"] = "residence"
    out["canonical_document_type"] = canon
    out["gpt_used"] = False
    out["authoritative"] = False
    out["hr_confirmation_required"] = True
    out["channel"] = channel
    return out


def extraction_for_receipt(result: dict[str, Any] | None) -> dict[str, Any]:
    """Shape shared processor output for record_employee_document_receipt.

    Empty dict means 'skip extract' historically. We never return {} for
    shared intake types when the processor ran — use needs_review stub instead.
    """

    if not isinstance(result, dict):
        return {
            "extraction_status": "needs_review",
            "extraction_error": "missing_extraction",
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "confidence": 0.0,
        }
    if result.get("extraction_status") in {"storage_only", "skipped_generated_only"}:
        return dict(result)
    out = dict(result)
    out.setdefault("authoritative", False)
    out.setdefault("hr_confirmation_required", True)
    out.setdefault("gpt_used", False)
    # Ensure parsed dates keys exist for receipt dual-write compatibility.
    if "issued_date_parsed" not in out and out.get("issued_date"):
        try:
            from identity_document_extraction import _parse_iso_date

            out["issued_date_parsed"] = _parse_iso_date(out.get("issued_date"))
        except Exception:
            out["issued_date_parsed"] = None
    if "expiry_date_parsed" not in out and out.get("expiry_date"):
        try:
            from identity_document_extraction import _parse_iso_date

            out["expiry_date_parsed"] = _parse_iso_date(out.get("expiry_date"))
        except Exception:
            out["expiry_date_parsed"] = None
    return out


def resolve_path_from_media(media: dict[str, Any] | None) -> Path | None:
    media_n = _media_with_path(media)
    if not media_n:
        return None
    p = Path(str(media_n.get("path") or ""))
    return p if p.exists() and p.is_file() else None
