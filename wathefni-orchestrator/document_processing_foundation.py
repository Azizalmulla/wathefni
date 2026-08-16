#!/usr/bin/env python3
"""Wathefni Unified Document Processing Foundation — cloud-portable domain contract.

No AWS- or GCP-specific imports. Designed for local/systemd now and container
workers later. Owns routing policy and document_envelope@1 helpers only —
document-class processors (CV V2, identity, contracts, payroll) stay separate.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_ENVELOPE = "document_envelope@1"
FOUNDATION_VERSION = "1.0.0"
FOUNDATION_ID = "wathefni_document_processing_foundation_wave1"

# Hybrid engine flag values
FLAG_HYBRID = "WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"
HYBRID_OFF = ""
HYBRID_STAGING_CANARY = "staging_canary"
HYBRID_PRODUCTION_SHADOW = "production_shadow"
HYBRID_PRODUCTION_AUTHORITY = "production_authority"

# Kill / cap controls (files or env)
ENV_DAILY_OCR_COST_CAP = "WATHEFNI_DOC_FOUNDATION_DAILY_OCR_COST_CAP_USD"
ENV_DAILY_DOC_AI_COST_CAP = "WATHEFNI_DOC_FOUNDATION_DAILY_DOC_AI_COST_CAP_USD"
ENV_MAX_SHADOW_PDFS = "WATHEFNI_DOC_FOUNDATION_MAX_SAMPLED_PDFS"
ENV_AUTHORITY_ENABLED = "WATHEFNI_DOC_FOUNDATION_CV_PDF_AUTHORITY"
ENV_GPT_AUTO_OCR_FALLBACK = "WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"  # must stay off
ENV_STOP_FILE = "WATHEFNI_DOC_FOUNDATION_STOP_FILE"

DEFAULT_DAILY_OCR_CAP = 2.0
DEFAULT_DAILY_DOC_AI_CAP = 5.0
DEFAULT_MAX_SAMPLED = 50

_lock = threading.Lock()
_spend: dict[str, float] = {"ocr": 0.0, "doc_ai": 0.0, "sampled_pdfs": 0.0}
_spend_day: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hybrid_mode() -> str:
    return (os.environ.get(FLAG_HYBRID) or "").strip().lower()


def cv_pdf_authority_enabled() -> bool:
    """Hybrid is authoritative for CV PDFs only when explicitly enabled."""
    mode = hybrid_mode()
    if mode == HYBRID_PRODUCTION_AUTHORITY:
        return True
    return (os.environ.get(ENV_AUTHORITY_ENABLED) or "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
        "enabled",
    }


def production_shadow_enabled() -> bool:
    return hybrid_mode() == HYBRID_PRODUCTION_SHADOW


def staging_canary_enabled() -> bool:
    return hybrid_mode() == HYBRID_STAGING_CANARY


def gpt_auto_ocr_fallback_forbidden() -> bool:
    """Foundation wave: GPT must not be automatic OCR fallback."""
    raw = (os.environ.get(ENV_GPT_AUTO_OCR_FALLBACK) or "off").strip().lower()
    return raw not in {"force", "force_on", "1_force"}


def stop_requested() -> bool:
    path = (os.environ.get(ENV_STOP_FILE) or "").strip()
    if path and Path(path).exists():
        return True
    return (os.environ.get("WATHEFNI_DOC_FOUNDATION_EMERGENCY_STOP") or "").strip().lower() in {
        "1",
        "true",
        "on",
        "stop",
    }


def _roll_spend_day() -> None:
    global _spend_day, _spend
    day = utc_day()
    if _spend_day != day:
        _spend_day = day
        _spend = {"ocr": 0.0, "doc_ai": 0.0, "sampled_pdfs": 0.0}


def daily_caps() -> dict[str, float]:
    def _f(name: str, default: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        try:
            return float(raw) if raw else default
        except ValueError:
            return default

    return {
        "ocr_usd": _f(ENV_DAILY_OCR_COST_CAP, DEFAULT_DAILY_OCR_CAP),
        "doc_ai_usd": _f(ENV_DAILY_DOC_AI_COST_CAP, DEFAULT_DAILY_DOC_AI_CAP),
        "max_sampled_pdfs": _f(ENV_MAX_SHADOW_PDFS, float(DEFAULT_MAX_SAMPLED)),
    }


def record_spend(*, ocr_usd: float = 0.0, doc_ai_usd: float = 0.0, sampled: bool = False) -> dict[str, Any]:
    with _lock:
        _roll_spend_day()
        _spend["ocr"] += max(0.0, float(ocr_usd or 0))
        _spend["doc_ai"] += max(0.0, float(doc_ai_usd or 0))
        if sampled:
            _spend["sampled_pdfs"] += 1
        caps = daily_caps()
        return {
            "day": _spend_day,
            "spent": dict(_spend),
            "caps": caps,
            "ocr_cap_breached": _spend["ocr"] > caps["ocr_usd"],
            "doc_ai_cap_breached": _spend["doc_ai"] > caps["doc_ai_usd"],
            "sample_cap_breached": _spend["sampled_pdfs"] > caps["max_sampled_pdfs"],
        }


def allow_sample() -> tuple[bool, str]:
    if stop_requested():
        return False, "emergency_stop"
    with _lock:
        _roll_spend_day()
        caps = daily_caps()
        if _spend["sampled_pdfs"] >= caps["max_sampled_pdfs"]:
            return False, "max_sampled_pdfs"
        if _spend["ocr"] >= caps["ocr_usd"]:
            return False, "ocr_cost_cap"
        if _spend["doc_ai"] >= caps["doc_ai_usd"]:
            return False, "doc_ai_cost_cap"
    return True, "ok"


# ---------------------------------------------------------------------------
# Route matrix (domain contract — cloud portable)
# ---------------------------------------------------------------------------

ROUTE_MATRIX: list[dict[str, Any]] = [
    {
        "document_class": "cv",
        "file_types": ["pdf"],
        "reading_route": "local_hybrid_pdf_engine",
        "fallback_reading": "poppler_mistral",
        "structuring": "cv_extraction_v2",
        "ocr_policy": "page_level_mistral_only_when_needed",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "hybrid_with_poppler_fallback",
    },
    {
        "document_class": "cv",
        "file_types": ["docx"],
        "reading_route": "native_docx_plus_selective_image_ocr",
        "fallback_reading": None,
        "structuring": "cv_extraction_v2",
        "ocr_policy": "embedded_text_candidate_images_only",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "existing_docx_authority",
    },
    {
        "document_class": "cv",
        "file_types": ["jpg", "jpeg", "png", "tif", "tiff", "webp"],
        "reading_route": "mistral_ocr",
        "fallback_reading": "needs_review_or_extraction_failed",
        "structuring": "cv_extraction_v2",
        "ocr_policy": "full_image_mistral",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "mistral_image_authority_no_gpt",
    },
    {
        "document_class": "generic_pdf",
        "file_types": ["pdf"],
        "reading_route": "local_hybrid_native_first",
        "fallback_reading": "needs_review",
        "structuring": "document_specific_processor",
        "ocr_policy": "mistral_only_scanned_corrupt_unusable",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "shared_reading_legacy_structuring",
    },
    {
        "document_class": "identity",
        "file_types": ["jpg", "jpeg", "png", "pdf", "tif", "tiff", "webp"],
        "reading_route": "shared_envelope_intake",
        "fallback_reading": "needs_review",
        "structuring": "identity_document_extraction_mistral",
        "ocr_policy": "mistral_document_ai_no_cv_v2_no_gpt",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "mistral_identity_authority_hr_confirmation_required",
        "notes": "Live identity authority via identity_document_extraction; GPT document fallback retired.",
    },
    {
        "document_class": "contract",
        "file_types": ["pdf", "jpg", "jpeg", "png", "tif", "tiff", "docx"],
        "reading_route": "shared_hybrid_or_native_docx",
        "fallback_reading": "needs_review",
        "structuring": "kuwait_gcc_document_intelligence",
        "ocr_policy": "mistral_when_needed_images_full_docx_native_selective",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "shared_contract_compliance_processor_hr_confirmation_required",
        "notes": "Shared omnichannel processor; identity classes still delegate to identity_document_extraction.",
    },
    {
        "document_class": "compliance",
        "file_types": ["pdf", "jpg", "jpeg", "png", "tif", "tiff", "docx"],
        "reading_route": "shared_hybrid_or_native_docx",
        "fallback_reading": "needs_review",
        "structuring": "kuwait_gcc_document_intelligence",
        "ocr_policy": "mistral_when_needed_images_full_docx_native_selective",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "shared_contract_compliance_processor_hr_confirmation_required",
        "notes": "Education cert and related compliance structuring; identity types delegate.",
    },
    {
        "document_class": "spreadsheet",
        "file_types": ["csv", "xlsx", "xls"],
        "reading_route": "structured_parser",
        "fallback_reading": None,
        "structuring": "schema_validation",
        "ocr_policy": "never_ocr",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "structured_import",
    },
    {
        "document_class": "generated_offer",
        "file_types": ["pdf"],
        "reading_route": "generated",
        "fallback_reading": None,
        "structuring": "none",
        "ocr_policy": "never_ocr",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "generated",
    },
    {
        "document_class": "payslip",
        "file_types": ["pdf", "json"],
        "reading_route": "generated_or_mirror_only",
        "fallback_reading": None,
        "structuring": "none",
        "ocr_policy": "never_ocr",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "mirror_or_generated",
    },
    {
        "document_class": "payroll_mirror",
        "file_types": ["json", "csv"],
        "reading_route": "mirror_only",
        "fallback_reading": None,
        "structuring": "none",
        "ocr_policy": "never_ocr",
        "gpt_auto_ocr_fallback": False,
        "authority_in_this_wave": "mirror_only",
    },
]


def resolve_route(*, document_class: str, file_type: str) -> dict[str, Any] | None:
    ft = (file_type or "").lower().lstrip(".")
    dc = (document_class or "").lower()
    for row in ROUTE_MATRIX:
        if row["document_class"] == dc and ft in row["file_types"]:
            return dict(row)
    return None


def must_never_ocr(document_class: str) -> bool:
    route = None
    for row in ROUTE_MATRIX:
        if row["document_class"] == (document_class or "").lower():
            if row.get("ocr_policy") == "never_ocr":
                return True
            route = row
    return False


def build_document_envelope(
    *,
    company_code: str | None,
    subject_type: str,
    subject_key: str | None,
    content_sha256: str,
    source_channel: str,
    document_class: str,
    file_type: str,
    authority_label: str,
    processing: dict[str, Any],
    retention_class: str = "inbound_cv",
    migration_batch_id: str | None = None,
    file_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    route = resolve_route(document_class=document_class, file_type=file_type) or {}
    return {
        "contract": CONTRACT_ENVELOPE,
        "foundation_id": FOUNDATION_ID,
        "foundation_version": FOUNDATION_VERSION,
        "company_code": company_code,
        "subject_type": subject_type,
        "subject_key": subject_key,
        "file_id": file_id,
        "content_sha256": content_sha256,
        "source_channel": source_channel,
        "migration_batch_id": migration_batch_id,
        "document_class": document_class,
        "file_type": file_type,
        "authority_label": authority_label,
        "route_policy": {
            "reading_route": route.get("reading_route"),
            "structuring": route.get("structuring"),
            "ocr_policy": route.get("ocr_policy"),
            "gpt_auto_ocr_fallback": False,
        },
        "processing": processing,
        "text_ref": processing.get("text_ref"),
        "structured_ref": processing.get("structured_ref"),
        "retention_class": retention_class,
        "error": error,
        "created_at": utc_now(),
        "cloud_portability": {
            "domain_contract_cloud_agnostic": True,
            "aws_specific_deps": False,
            "gcp_specific_deps": False,
            "worker_shape": "container_ready_async",
        },
    }


@dataclass
class WorkerJobContract:
    """Async worker job shape — portable to containers later."""

    job_id: str
    company_code: str
    workload_class: str  # live_cv | migration_bulk | backfill | shadow
    priority: int
    document_class: str
    file_type: str
    content_sha256: str
    storage_ref: str
    source_channel: str
    max_attempts: int = 5
    timeout_s: float = 120.0
    cost_budget_usd: float = 0.25
    idempotency_key: str = ""
    cancel_requested: bool = False
    envelope_contract: str = CONTRACT_ENVELOPE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def envelope_complete(envelope: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(envelope, dict):
        return False, "missing_envelope"
    if envelope.get("contract") != CONTRACT_ENVELOPE:
        return False, "bad_contract"
    if not envelope.get("content_sha256"):
        return False, "missing_content_sha256"
    proc = envelope.get("processing") if isinstance(envelope.get("processing"), dict) else {}
    page_methods = proc.get("page_methods")
    if page_methods is not None and not isinstance(page_methods, list):
        return False, "bad_page_methods"
    if page_methods is not None:
        for pm in page_methods:
            if not isinstance(pm, dict) or "page" not in pm or "method" not in pm:
                return False, "incomplete_page_provenance"
    return True, "ok"
