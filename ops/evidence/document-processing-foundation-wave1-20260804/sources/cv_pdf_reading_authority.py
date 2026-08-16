#!/usr/bin/env python3
"""CV PDF reading authority — hybrid primary with automatic Poppler fallback.

Used only when document_processing_foundation.cv_pdf_authority_enabled().
Never materializes V2 / Ranking / Candidate Knowledge by itself.
GPT is not used as automatic OCR fallback.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("wathefni.cv_pdf_reading_authority")

AUTHORITY_CONTRACT = "cv_pdf_reading_authority_wave1"


def _hybrid_result_acceptable(hybrid: Any) -> tuple[bool, str]:
    if hybrid is None:
        return False, "hybrid_none"
    if not getattr(hybrid, "ok", False):
        return False, f"hybrid_not_ok:{getattr(hybrid, 'error', None)}"
    err = getattr(hybrid, "error", None)
    # Simulated OCR is not acceptable as production authority text for scanned pages.
    if getattr(hybrid, "simulated_ocr", False):
        pages = list(getattr(hybrid, "pages", []) or [])
        if any(getattr(p, "method", None) == "ocr" for p in pages):
            return False, "hybrid_simulated_ocr_not_authoritative"
    text = str(getattr(hybrid, "merged_markdown", "") or "").strip()
    if not text:
        return False, "empty_merged_markdown"
    # Reject marker-only / failed-page-only merges.
    if text.startswith("[OCR_SIMULATED") or "[PAGE_" in text and "FAILED" in text and len(text) < 80:
        return False, "unusable_merged_markers"
    envelope = getattr(hybrid, "envelope", None)
    try:
        from document_processing_foundation import envelope_complete

        ok, reason = envelope_complete(envelope if isinstance(envelope, dict) else None)
        if not ok:
            return False, f"incomplete_envelope:{reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"envelope_check_failed:{exc}"
    pages = list(getattr(hybrid, "pages", []) or [])
    if not pages:
        return False, "missing_page_provenance"
    for p in pages:
        if getattr(p, "page_number", None) is None or not getattr(p, "method", None):
            return False, "incomplete_page_provenance"
    # Quality gate on merged text (Arabic-aware leniency via cv_extraction helpers).
    try:
        import cv_extraction as cv

        arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
        if arabic >= 40 and len(text) >= 80:
            return True, "accepted_hybrid_arabic"
        if not cv.cv_text_quality_ok(text, min_chars=40, min_words=6):
            return False, "low_quality_hybrid_text"
    except Exception:
        if len(text) < 40:
            return False, "low_quality_hybrid_text"
    return True, "accepted_hybrid"


def hybrid_to_extraction_result(
    *,
    path: Path,
    hybrid: Any,
    content_sha256: str,
    accept_reason: str,
) -> Any:
    import cv_extraction as cv
    from document_processing_foundation import build_document_envelope, FOUNDATION_ID

    pages = list(getattr(hybrid, "pages", []) or [])
    assessments = []
    for p in pages:
        method = getattr(p, "method", "")
        disposition = "accepted_local" if method == "native" else (
            "needs_ocr" if method == "ocr" else "empty"
        )
        # After successful hybrid OCR, page text is already merged — treat OCR pages as accepted.
        if method == "ocr" and getattr(p, "text", ""):
            disposition = "accepted_local"
        local = str(getattr(p, "text", "") or getattr(p, "native_markdown", "") or "")
        assessments.append(
            cv.PageAssessment(
                page_number=int(getattr(p, "page_number")),
                page_index=int(getattr(p, "page_index")),
                local_text=local,
                page_hash=cv.sha256_text(local or f"empty:{getattr(p, 'page_number')}"),
                disposition=disposition,
                reason=str(getattr(p, "reason", "") or method),
                char_count=len(local),
                word_count=cv.word_count(local),
                arabic_ratio=cv.arabic_ratio(local),
            )
        )

    text = str(getattr(hybrid, "merged_markdown", "") or "")
    ok = True
    try:
        arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
        if arabic < 40:
            ok = cv.cv_text_quality_ok(text)
    except Exception:
        ok = bool(text)

    proc = (getattr(hybrid, "envelope", None) or {}).get("processing") or {}
    envelope = build_document_envelope(
        company_code=(getattr(hybrid, "envelope", None) or {}).get("company_code"),
        subject_type="application",
        subject_key=(getattr(hybrid, "envelope", None) or {}).get("subject_key"),
        content_sha256=content_sha256,
        source_channel="cv_pdf_reading_authority",
        document_class="cv",
        file_type="pdf",
        authority_label="machine_extracted",
        processing={
            **proc,
            "route": "local_hybrid_pdf_engine",
            "provider": proc.get("provider") or "local",
            "foundation_id": FOUNDATION_ID,
            "accept_reason": accept_reason,
            "fallback_used": False,
            "gpt_auto_ocr_fallback": False,
            "text_ref": "inline:merged_markdown",
        },
        retention_class="inbound_cv",
    )

    engine_calls = [
        cv.EngineCallMeta(
            stage="local_hybrid_authority",
            tier="local_hybrid_pdf_engine",
            provider="local+mistral",
            actual_request_model="pdf-inspector+mistral-ocr-4-0",
            provider_response_model=None,
            latency_ms=int(getattr(hybrid, "wall_ms", 0) or 0),
            billable_pages=int(proc.get("billable_pages") or 0),
            estimated_cost_usd=float(proc.get("estimated_cost_usd") or 0),
            pages=[p.page_index for p in pages if getattr(p, "method", None) == "ocr"],
            quality_ok=ok,
            retention="local_hybrid_authority",
        )
    ]

    return cv.ExtractionResult(
        text=text,
        method="local_hybrid_pdf_engine",
        error=None if ok else "low_quality_text",
        quality_ok=ok,
        page_assessments=assessments,
        engine_calls=engine_calls,
        content_sha256=content_sha256,
        metadata={
            "stage": "local_hybrid_authority",
            "tier": "local_hybrid_pdf_engine",
            "authority_contract": AUTHORITY_CONTRACT,
            "document_envelope": envelope,
            "fallback_used": False,
            "gpt_vision_invoked": False,
            "accept_reason": accept_reason,
        },
    )


def try_hybrid_cv_pdf_authority(
    path: Path,
    *,
    company_code: str,
    document_id: str | None = None,
    app_key: str | None = None,
    allow_paid_ocr: bool = True,
) -> tuple[Any | None, dict[str, Any]]:
    """Attempt hybrid authority. Returns (ExtractionResult|None, diagnostics)."""
    diag: dict[str, Any] = {
        "contract": AUTHORITY_CONTRACT,
        "attempted": True,
        "accepted": False,
        "fallback_required": True,
        "reason": None,
        "gpt_vision_invoked": False,
    }
    started = time.perf_counter()
    try:
        from document_processing_foundation import (
            cv_pdf_authority_enabled,
            record_spend,
            stop_requested,
        )
        from local_hybrid_pdf_engine import HybridEngineLimits, extract_pdf_hybrid
        import cv_extraction as cv

        if not cv_pdf_authority_enabled():
            diag.update({"attempted": False, "reason": "authority_flag_off", "fallback_required": True})
            return None, diag
        if stop_requested():
            diag["reason"] = "emergency_stop"
            return None, diag

        hybrid = extract_pdf_hybrid(
            path,
            limits=HybridEngineLimits(
                max_pages=15,
                allow_paid_ocr=allow_paid_ocr and cv.mistral_ocr_enabled(),
                max_retries=2,
                max_projected_cost_usd=0.12,
                timeout_s=90.0,
                cache_dir=None,
            ),
            company_code=company_code,
            document_class="cv",
            subject_type="application",
            subject_key=app_key or path.stem,
            source_channel="cv_pdf_reading_authority",
            include_merged_in_envelope=True,
        )
        ok, reason = _hybrid_result_acceptable(hybrid)
        diag["hybrid_error"] = getattr(hybrid, "error", None)
        diag["hybrid_wall_ms"] = getattr(hybrid, "wall_ms", None)
        diag["accept_check"] = reason
        if not ok:
            diag["reason"] = reason
            return None, diag

        content_sha = cv.sha256_bytes(path.read_bytes())
        result = hybrid_to_extraction_result(
            path=path,
            hybrid=hybrid,
            content_sha256=content_sha,
            accept_reason=reason,
        )
        proc = (result.metadata or {}).get("document_envelope", {}).get("processing") or {}
        record_spend(
            ocr_usd=float(proc.get("estimated_cost_usd") or 0),
            sampled=False,
        )
        diag.update(
            {
                "accepted": True,
                "fallback_required": False,
                "reason": reason,
                "wall_ms": int((time.perf_counter() - started) * 1000),
            }
        )
        return result, diag
    except Exception as exc:  # noqa: BLE001
        logger.exception("hybrid_cv_pdf_authority_failed")
        diag["reason"] = f"exception:{type(exc).__name__}:{exc}"
        diag["wall_ms"] = int((time.perf_counter() - started) * 1000)
        return None, diag
