#!/usr/bin/env python3
"""Local Hybrid PDF Engine Wave 1 — CV staging alternate-path canary.

Flag (default off):
  WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary

When enabled for eligible CV PDFs:
  1) Poppler/Mistral extraction remains authoritative (caller already ran it)
  2) Hybrid engine emits document_envelope@1 (non-authoritative)
  3) Hybrid merged text is fed into the same CV Extraction V2 pipeline
     (Document AI annotation still runs on the PDF bytes — not bypassed)
  4) Structured outputs are compared; hybrid is never materialized as current

Rollback: unset the flag. Fail-open on any canary error.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("wathefni.local_hybrid_pdf_engine_canary")

FLAG_NAME = "WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"
FLAG_VALUE = "staging_canary"
CONTRACT = "local_hybrid_pdf_engine_cv_staging_canary_wave1"
CANARY_STAGE = "local_hybrid_pdf_engine_canary"

DbExecute = Callable[..., Any]


def canary_enabled() -> bool:
    raw = (os.environ.get(FLAG_NAME) or "").strip().lower()
    return raw == FLAG_VALUE


def _arabic_chars(text: str) -> int:
    return sum(1 for ch in (text or "") if "\u0600" <= ch <= "\u06FF")


def _normalize_contact(payload: dict[str, Any]) -> dict[str, str]:
    c = payload.get("contact_details") if isinstance(payload.get("contact_details"), dict) else {}
    return {
        "full_name": str(c.get("full_name") or "").strip().lower(),
        "email": str(c.get("email") or "").strip().lower(),
        "phone": re.sub(r"\D+", "", str(c.get("phone") or "")),
        "location": str(c.get("location") or "").strip().lower(),
    }


def _employment_fingerprint(payload: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for item in payload.get("employment") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": str(item.get("title") or "").strip().lower(),
                "company": str(item.get("company") or "").strip().lower(),
                "start_date": str(item.get("start_date") or "").strip().lower(),
                "end_date": str(item.get("end_date") or "").strip().lower(),
            }
        )
    return out


def _education_fingerprint(payload: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for item in payload.get("education") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "degree": str(item.get("degree") or "").strip().lower(),
                "institution": str(item.get("institution") or "").strip().lower(),
                "start_date": str(item.get("start_date") or "").strip().lower(),
                "end_date": str(item.get("end_date") or "").strip().lower(),
            }
        )
    return out


def _skill_names(payload: dict[str, Any]) -> list[str]:
    names = []
    for item in payload.get("skills") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip().lower()
        else:
            name = str(item or "").strip().lower()
        if name:
            names.append(name)
    return sorted(set(names))


def _count_source_evidence(payload: dict[str, Any]) -> dict[str, int]:
    """Count items that carry source_evidence (Ranking/evidence provenance)."""
    counts = {"with_evidence": 0, "without_evidence": 0, "fields_checked": 0}
    for key in (
        "employment",
        "education",
        "skills",
        "languages",
        "projects",
        "certifications",
        "training_courses",
        "volunteer_work",
    ):
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            counts["fields_checked"] += 1
            if item.get("source_evidence"):
                counts["with_evidence"] += 1
            else:
                counts["without_evidence"] += 1
    return counts


def _ranking_inputs_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Lightweight Ranking-facing inputs derived from V2 payload (no Ranking rewrite)."""
    try:
        import cv_extraction_v2 as cv2

        projected = cv2.project_profile_facts_v2(payload)
    except Exception as exc:  # noqa: BLE001
        projected = {"error": f"{type(exc).__name__}:{exc}"}
    return {
        "contact": _normalize_contact(payload),
        "employment_n": len(payload.get("employment") or []),
        "education_n": len(payload.get("education") or []),
        "skills_n": len(payload.get("skills") or []),
        "languages_n": len(payload.get("languages") or []),
        "source_evidence": _count_source_evidence(payload),
        "profile_facts_projection_keys": sorted(projected.keys()) if isinstance(projected, dict) else [],
        "projected_skill_count": len((projected or {}).get("skills") or [])
        if isinstance(projected, dict)
        else 0,
        "projected_employment_count": len((projected or {}).get("employment") or [])
        if isinstance(projected, dict)
        else 0,
    }


def compare_v2_structured(
    *,
    auth_payload: dict[str, Any],
    hybrid_payload: dict[str, Any],
    auth_ok: bool,
    hybrid_ok: bool,
) -> dict[str, Any]:
    auth_c = _normalize_contact(auth_payload)
    hyb_c = _normalize_contact(hybrid_payload)
    auth_emp = _employment_fingerprint(auth_payload)
    hyb_emp = _employment_fingerprint(hybrid_payload)
    auth_edu = _education_fingerprint(auth_payload)
    hyb_edu = _education_fingerprint(hybrid_payload)
    auth_skills = _skill_names(auth_payload)
    hyb_skills = _skill_names(hybrid_payload)
    auth_ev = _count_source_evidence(auth_payload)
    hyb_ev = _count_source_evidence(hybrid_payload)
    auth_rank = _ranking_inputs_snapshot(auth_payload)
    hyb_rank = _ranking_inputs_snapshot(hybrid_payload)

    # Field accuracy relative to authoritative: hybrid must not lose required fields.
    contact_regression = any(
        auth_c[k] and auth_c[k] != hyb_c[k] for k in ("full_name", "email", "phone")
    )
    # Missing employment/education/skills that auth had.
    emp_missing = max(0, len(auth_emp) - len(hyb_emp))
    edu_missing = max(0, len(auth_edu) - len(hyb_edu))
    skills_missing = sorted(set(auth_skills) - set(hyb_skills))
    evidence_regression = hyb_ev["with_evidence"] < auth_ev["with_evidence"]
    ranking_regression = (
        hyb_rank.get("projected_skill_count", 0) < auth_rank.get("projected_skill_count", 0)
        or hyb_rank.get("projected_employment_count", 0) < auth_rank.get("projected_employment_count", 0)
    )
    v2_completion_regression = bool(auth_ok) and (not hybrid_ok)

    auth_ar = _arabic_chars(
        " ".join(
            [
                str((auth_payload.get("contact_details") or {}).get("full_name") or ""),
                str(auth_payload.get("professional_summary") or ""),
            ]
        )
    )
    hyb_ar = _arabic_chars(
        " ".join(
            [
                str((hybrid_payload.get("contact_details") or {}).get("full_name") or ""),
                str(hybrid_payload.get("professional_summary") or ""),
            ]
        )
    )

    return {
        "contact_match": auth_c == hyb_c,
        "contact_auth": auth_c,
        "contact_hybrid": hyb_c,
        "contact_regression": contact_regression,
        "employment_match": auth_emp == hyb_emp,
        "employment_auth_n": len(auth_emp),
        "employment_hybrid_n": len(hyb_emp),
        "employment_missing_vs_auth": emp_missing,
        "education_match": auth_edu == hyb_edu,
        "education_auth_n": len(auth_edu),
        "education_hybrid_n": len(hyb_edu),
        "education_missing_vs_auth": edu_missing,
        "skills_match": auth_skills == hyb_skills,
        "skills_auth_n": len(auth_skills),
        "skills_hybrid_n": len(hyb_skills),
        "skills_missing_vs_auth": skills_missing[:20],
        "skills_missing_count": len(skills_missing),
        "evidence_auth": auth_ev,
        "evidence_hybrid": hyb_ev,
        "evidence_regression": evidence_regression,
        "ranking_auth": auth_rank,
        "ranking_hybrid": hyb_rank,
        "ranking_regression": ranking_regression,
        "v2_auth_ok": bool(auth_ok),
        "v2_hybrid_ok": bool(hybrid_ok),
        "v2_completion_regression": v2_completion_regression,
        "arabic_chars_auth_summary": auth_ar,
        "arabic_chars_hybrid_summary": hyb_ar,
        "structured_field_accuracy_reduction": bool(
            contact_regression
            or emp_missing > 0
            or edu_missing > 0
            or skills_missing
            or evidence_regression
            or ranking_regression
        ),
    }


def _poppler_ocr_pages(extraction: Any) -> list[int]:
    pages = []
    for a in getattr(extraction, "page_assessments", None) or []:
        if str(getattr(a, "disposition", "")) == "needs_ocr":
            pages.append(int(getattr(a, "page_number")))
    return sorted(set(pages))


def _engine_cost_and_latency(extraction: Any) -> dict[str, Any]:
    calls = list(getattr(extraction, "engine_calls", None) or [])
    cost = 0.0
    latency = 0
    billable = 0
    mistral_calls = 0
    for c in calls:
        cost += float(getattr(c, "estimated_cost_usd", 0) or 0)
        latency += int(getattr(c, "latency_ms", 0) or 0)
        billable += int(getattr(c, "billable_pages", 0) or 0)
        if str(getattr(c, "provider", "") or "") == "mistral":
            mistral_calls += 1
    return {
        "engine_calls": len(calls),
        "mistral_engine_calls": mistral_calls,
        "billable_pages": billable,
        "estimated_cost_usd": round(cost, 6),
        "latency_ms_sum": latency,
    }


def run_cv_hybrid_alternate_canary(
    *,
    path: Path | str,
    mime_type: str | None,
    company_code: str,
    authoritative_extraction: Any,
    authoritative_v2: dict[str, Any] | None,
    document_id: str | None = None,
    app_key: str | None = None,
    db_execute: DbExecute | None = None,
    allow_paid_ocr: bool | None = None,
) -> dict[str, Any]:
    """Run hybrid alternate path + V2 compare. Never authoritative. Fail-open friendly."""
    started = time.perf_counter()
    base: dict[str, Any] = {
        "contract": CONTRACT,
        "enabled": canary_enabled(),
        "authoritative_path": "poppler_mistral_cv_extraction",
        "hybrid_authoritative": False,
        "influences_routing": False,
        "materializes_current_v2": False,
        "publishes_profile_facts": False,
    }
    if not canary_enabled():
        base["skipped"] = "flag_off"
        return base

    pdf_path = Path(path)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        base["skipped"] = "not_eligible_pdf"
        return base

    try:
        import cv_extraction as cv
        import cv_extraction_v2 as cv2
        from local_hybrid_pdf_engine import HybridEngineLimits, extract_pdf_hybrid

        if allow_paid_ocr is None:
            allow_paid_ocr = bool(cv.mistral_ocr_enabled())

        t_hybrid = time.perf_counter()
        hybrid = extract_pdf_hybrid(
            pdf_path,
            limits=HybridEngineLimits(
                max_pages=15,
                allow_paid_ocr=allow_paid_ocr,
                max_retries=2,
                max_projected_cost_usd=0.12,
                timeout_s=120.0,
                cache_dir=None,
            ),
            company_code=company_code,
            document_class="cv",
            subject_type="application",
            subject_key=app_key or pdf_path.stem,
            source_channel="staging_canary",
            include_merged_in_envelope=True,
        )
        hybrid_ms = int((time.perf_counter() - t_hybrid) * 1000)

        # False OCR skip check vs Poppler true-need reasons.
        poppler_ocr = _poppler_ocr_pages(authoritative_extraction)
        hybrid_ocr = [p.page_number for p in hybrid.pages if p.method == "ocr"]
        hybrid_native = [p.page_number for p in hybrid.pages if p.method == "native"]
        false_skip_pages: list[int] = []
        assessments = list(getattr(authoritative_extraction, "page_assessments", None) or [])
        for a in assessments:
            if str(getattr(a, "disposition", "")) != "needs_ocr":
                continue
            reason = str(getattr(a, "reason", "") or "")
            page = int(getattr(a, "page_number"))
            if reason in {
                "image_only_page",
                "scanned_or_empty",
                "corrupt_or_unusable_text",
                "image_dominant_sparse_text",
            } and page in hybrid_native:
                false_skip_pages.append(page)
        # Broken native pages hybrid marked OCR via quality gate are fine.
        false_skip_pages = sorted(set(false_skip_pages))

        t_v2 = time.perf_counter()
        hybrid_v2 = cv2.run_v2_extraction(
            local_path=pdf_path,
            mime_type=mime_type or "application/pdf",
            extracted_text=hybrid.merged_markdown or "",
            blocks=[],
            prefer_reuse_text=False,
        )
        hybrid_v2_ms = int((time.perf_counter() - t_v2) * 1000)

        auth_v2 = authoritative_v2 or {}
        auth_payload = (auth_v2.get("payload") if isinstance(auth_v2, dict) else None) or {}
        hyb_payload = (hybrid_v2.get("payload") if isinstance(hybrid_v2, dict) else None) or {}
        structured = compare_v2_structured(
            auth_payload=auth_payload if isinstance(auth_payload, dict) else {},
            hybrid_payload=hyb_payload if isinstance(hyb_payload, dict) else {},
            auth_ok=bool(auth_v2.get("ok")) if isinstance(auth_v2, dict) else False,
            hybrid_ok=bool(hybrid_v2.get("ok")),
        )

        auth_metrics = _engine_cost_and_latency(authoritative_extraction)
        hybrid_proc = (hybrid.envelope or {}).get("processing") or {}
        hybrid_ocr_meta = hybrid_proc.get("ocr") or {}
        v2_auth_meta = (auth_v2.get("meta") if isinstance(auth_v2, dict) else None) or {}
        v2_hyb_meta = hybrid_v2.get("meta") or {}

        result = {
            **base,
            "ok": True,
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "hybrid_extract_ms": hybrid_ms,
            "hybrid_v2_ms": hybrid_v2_ms,
            "document_envelope": {
                k: hybrid.envelope.get(k)
                for k in (
                    "contract",
                    "content_sha256",
                    "document_class",
                    "processing",
                    "error",
                )
            },
            "hybrid_error": hybrid.error,
            "hybrid_simulated_ocr": hybrid.simulated_ocr,
            "page_order_hybrid": [p.page_number for p in hybrid.pages],
            "page_methods": [
                {
                    "page": p.page_number,
                    "method": p.method,
                    "reason": p.reason,
                    "quality_forced_ocr": p.quality_forced_ocr,
                }
                for p in hybrid.pages
            ],
            "ocr_pages": {
                "poppler": poppler_ocr,
                "hybrid": hybrid_ocr,
                "false_skip_pages": false_skip_pages,
                "zero_false_ocr_skips": len(false_skip_pages) == 0,
            },
            "latency_ms": {
                "authoritative_extract_sum": auth_metrics["latency_ms_sum"],
                "hybrid_extract": hybrid_ms,
                "hybrid_v2": hybrid_v2_ms,
                "v2_auth_meta": v2_auth_meta.get("latency_ms"),
                "v2_hybrid_meta": v2_hyb_meta.get("latency_ms"),
            },
            "mistral_calls_and_cost": {
                "authoritative_extract": auth_metrics,
                "hybrid_ocr": {
                    "billable_pages": hybrid_proc.get("billable_pages"),
                    "estimated_cost_usd": hybrid_proc.get("estimated_cost_usd"),
                    "projected_cost_usd": hybrid_proc.get("projected_cost_usd_if_ocr_executed"),
                    "request_id": hybrid_proc.get("request_id"),
                    "error": hybrid_ocr_meta.get("error"),
                },
                "v2_document_ai_auth": {
                    "billable_pages": v2_auth_meta.get("billable_pages"),
                    "estimated_cost_usd": v2_auth_meta.get("estimated_cost_usd"),
                    "model": v2_auth_meta.get("actual_request_model") or v2_auth_meta.get("model"),
                    "error": v2_auth_meta.get("error"),
                    "path": auth_v2.get("path") if isinstance(auth_v2, dict) else None,
                },
                "v2_document_ai_hybrid": {
                    "billable_pages": v2_hyb_meta.get("billable_pages"),
                    "estimated_cost_usd": v2_hyb_meta.get("estimated_cost_usd"),
                    "model": v2_hyb_meta.get("actual_request_model") or v2_hyb_meta.get("model"),
                    "error": v2_hyb_meta.get("error"),
                    "path": hybrid_v2.get("path"),
                },
            },
            "layout": {
                "hybrid_inspector": hybrid_proc.get("inspector"),
                "auth_method": getattr(authoritative_extraction, "method", None),
                "auth_text_chars": len(getattr(authoritative_extraction, "text", "") or ""),
                "hybrid_text_chars": len(hybrid.merged_markdown or ""),
                "auth_arabic_chars": _arabic_chars(getattr(authoritative_extraction, "text", "") or ""),
                "hybrid_arabic_chars": _arabic_chars(hybrid.merged_markdown or ""),
            },
            "v2_compare": {
                "auth_ok": bool(auth_v2.get("ok")) if isinstance(auth_v2, dict) else False,
                "hybrid_ok": bool(hybrid_v2.get("ok")),
                "auth_path": auth_v2.get("path") if isinstance(auth_v2, dict) else None,
                "hybrid_path": hybrid_v2.get("path"),
                "auth_extractor_version": auth_v2.get("extractor_version") if isinstance(auth_v2, dict) else None,
                "hybrid_extractor_version": hybrid_v2.get("extractor_version"),
                "structured": structured,
            },
            "acceptance": {
                "zero_structured_field_accuracy_reduction": not structured["structured_field_accuracy_reduction"],
                "zero_missing_ranking_evidence": not structured["evidence_regression"]
                and not structured["ranking_regression"],
                "zero_false_ocr_skips": len(false_skip_pages) == 0,
                "v2_completion_same_or_better": (not structured["v2_completion_regression"]),
            },
        }
        result["acceptance"]["all_pass"] = all(result["acceptance"].values())

        if db_execute is not None:
            try:
                from cv_extraction import record_extraction_run

                record_extraction_run(
                    db_execute,
                    company_code=company_code,
                    document_id=document_id,
                    app_key=app_key,
                    content_sha256=getattr(authoritative_extraction, "content_sha256", None)
                    or (hybrid.envelope or {}).get("content_sha256"),
                    stage=CANARY_STAGE,
                    tier="local_hybrid_alternate",
                    provider="local+mistral",
                    actual_request_model="pdf-inspector+mistral-ocr-4-0+document_ai",
                    provider_response_model=None,
                    pages_requested=hybrid_ocr,
                    pages_processed=len(hybrid.pages),
                    billable_pages=int(hybrid_proc.get("billable_pages") or 0),
                    estimated_cost_usd=float(hybrid_proc.get("estimated_cost_usd") or 0),
                    latency_ms=result["wall_ms"],
                    provider_request_id=hybrid_proc.get("request_id"),
                    quality_ok=bool(result["acceptance"]["all_pass"]),
                    cache_hit=False,
                    error=None if result["ok"] else hybrid.error,
                    metadata={
                        "contract": CONTRACT,
                        "hybrid_authoritative": False,
                        "acceptance": result["acceptance"],
                        "ocr_pages": result["ocr_pages"],
                        "v2_compare_summary": {
                            "auth_ok": result["v2_compare"]["auth_ok"],
                            "hybrid_ok": result["v2_compare"]["hybrid_ok"],
                            "structured_field_accuracy_reduction": structured[
                                "structured_field_accuracy_reduction"
                            ],
                        },
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("hybrid_canary_record_failed")

        return result
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.exception("hybrid_canary_fail_open")
        return {
            **base,
            "ok": False,
            "fail_open": True,
            "error": f"{type(exc).__name__}:{exc}",
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "hybrid_authoritative": False,
        }
