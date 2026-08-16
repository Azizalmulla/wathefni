#!/usr/bin/env python3
"""Wathefni Local Hybrid PDF Engine Wave 0 — experimental / offline / staging-only.

Native-first page routing via pdf-inspector, OCR fallback via Wathefni Mistral.
Never wired into production CV extraction in this wave.
No document-type-specific parsing (CV/identity/contract stay elsewhere).

Pinned dependency (do not silently upgrade production):
  pdf-inspector==0.2.6  (Python PyO3 binding)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("wathefni.local_hybrid_pdf_engine")

ENGINE_ID = "local_hybrid_pdf_engine_wave0"
ENGINE_VERSION = "0.1.0"
CONTRACT_ENVELOPE = "document_envelope@1"
PINNED_INSPECTOR = "0.2.6"
PINNED_OCR_MODEL = "mistral-ocr-4-0"
COST_USD_PER_PAGE = 0.004

_MOJIBAKE_RE = re.compile(r"(Ã.|Â.|Ù.|Ø.|ð.|�|\ufffd|ÃÑ|Ùn|Â\x9d)")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")


@dataclass
class HybridEngineLimits:
    max_pages: int = 10
    max_bytes: int = 20 * 1024 * 1024
    timeout_s: float = 60.0
    max_retries: int = 2
    max_projected_cost_usd: float = 0.12  # 30 pages @ $0.004
    allow_paid_ocr: bool = False
    cache_dir: Path | None = None


@dataclass
class PageDecision:
    page_number: int  # 1-indexed
    page_index: int  # 0-indexed
    method: str  # native | ocr | failed | skipped
    reason: str
    text: str = ""
    native_markdown: str = ""
    inspector_needs_ocr: bool = False
    quality_forced_ocr: bool = False
    error: str | None = None
    latency_ms: int = 0
    billable: bool = False


@dataclass
class HybridEngineResult:
    ok: bool
    envelope: dict[str, Any]
    pages: list[PageDecision] = field(default_factory=list)
    merged_markdown: str = ""
    error: str | None = None
    simulated_ocr: bool = True
    cache_hit: bool = False
    inspector_version: str = PINNED_INSPECTOR
    ocr_model: str = PINNED_OCR_MODEL
    wall_ms: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inspector_version() -> str:
    try:
        from importlib.metadata import version

        return version("pdf-inspector")
    except Exception:
        return PINNED_INSPECTOR


def inspector_extension_digest() -> str | None:
    try:
        import pdf_inspector

        so = Path(pdf_inspector.__file__).resolve().parent / "pdf_inspector.abi3.so"
        if so.exists():
            return sha256_bytes(so.read_bytes())
    except Exception:
        return None
    return None


def word_count(text: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF0-9+#.'\-]{1,}",
            text or "",
        )
    )


def native_page_usable(markdown: str | None) -> tuple[bool, str]:
    """Arabic-aware usability + broken-encoding force-OCR gates."""
    raw = str(markdown or "").strip()
    if not raw:
        return False, "empty"
    mojibake_hits = len(_MOJIBAKE_RE.findall(raw))
    replacement = raw.count("\ufffd") + raw.count("�")
    arabic_chars = len(_ARABIC_RE.findall(raw))
    presentation = len(_ARABIC_PRESENTATION_RE.findall(raw))
    words = word_count(raw)
    alpha = sum(1 for ch in raw if ch.isalpha())
    printable = sum(1 for ch in raw if ch.isprintable() and not ch.isspace())
    alpha_ratio = (alpha / printable) if printable else 0.0

    # Broken / unusable native text → OCR (required for Wave 2 broken-encoding).
    if mojibake_hits >= 1:
        return False, "mojibake_native_text"
    if replacement >= 3:
        return False, "replacement_chars"
    if presentation >= 8 and arabic_chars == 0:
        return False, "corrupted_arabic_presentation"
    if printable and alpha_ratio < 0.35 and arabic_chars == 0 and words >= 6:
        return False, "suspicious_printable_but_meaningless"

    # Usable Arabic digital: preserve locally even when whitespace word_count is low.
    if arabic_chars >= 40 and mojibake_hits == 0 and len(raw) >= 80:
        return True, "accepted_native_arabic"
    if arabic_chars >= 20 and words >= 4 and mojibake_hits == 0:
        return True, "accepted_native_arabic_sparse"

    if len(raw) < 40:
        return False, "too_short"
    if words < 6:
        return False, "too_few_words"
    if printable and alpha_ratio < 0.35:
        return False, "quality_gate_failed"
    return True, "accepted_native"


def build_cache_key(
    *,
    content_sha256: str,
    inspector_ver: str,
    ocr_model: str,
    engine_version: str,
    allow_paid_ocr: bool,
) -> str:
    payload = {
        "engine": ENGINE_ID,
        "engine_version": engine_version,
        "content_sha256": content_sha256,
        "inspector_version": inspector_ver,
        "ocr_model": ocr_model,
        "allow_paid_ocr": allow_paid_ocr,
        "routing": "inspector_native_plus_quality_gate_ocr",
    }
    return sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _normalize_ocr_pages(pages: list[Any], *, page_count: int) -> list[int]:
    vals = sorted({int(p) for p in (pages or []) if str(p).lstrip("-").isdigit()})
    if not vals:
        return []
    if any(v == 0 for v in vals):
        return [v + 1 for v in vals if 0 <= v < max(page_count, 1)]
    return [v for v in vals if 1 <= v <= max(page_count, 1)]


def _load_pages_markdown(path: Path) -> tuple[list[Any], dict[str, Any]]:
    import pdf_inspector as pi

    result = pi.extract_pages_markdown(str(path))
    pages = list(getattr(result, "pages", []) or [])
    meta = {
        "pages_needing_ocr_raw": list(getattr(result, "pages_needing_ocr", []) or []),
        "pages_with_tables": list(getattr(result, "pages_with_tables", []) or []),
        "pages_with_columns": list(getattr(result, "pages_with_columns", []) or []),
        "is_complex": bool(getattr(result, "is_complex", False)),
        "ocr_reasons_by_page": list(getattr(result, "ocr_reasons_by_page", []) or []),
    }
    return pages, meta


def _decide_pages(pages: list[Any]) -> list[PageDecision]:
    decisions: list[PageDecision] = []
    for pg in pages:
        # PageMarkdown.page is 0-indexed.
        idx = int(getattr(pg, "page", 0) or 0)
        page_number = idx + 1
        md = str(getattr(pg, "markdown", "") or "")
        inspector_needs = bool(getattr(pg, "needs_ocr", False))
        inspector_reason = str(getattr(pg, "ocr_reason", "") or "") or (
            "inspector_needs_ocr" if inspector_needs else "inspector_native"
        )
        usable, gate_reason = native_page_usable(md)
        quality_forced = (not inspector_needs) and (not usable)
        if inspector_needs or not usable:
            decisions.append(
                PageDecision(
                    page_number=page_number,
                    page_index=idx,
                    method="ocr",
                    reason=inspector_reason if inspector_needs else gate_reason,
                    native_markdown=md,
                    inspector_needs_ocr=inspector_needs,
                    quality_forced_ocr=quality_forced,
                )
            )
        else:
            decisions.append(
                PageDecision(
                    page_number=page_number,
                    page_index=idx,
                    method="native",
                    reason=gate_reason,
                    text=md,
                    native_markdown=md,
                    inspector_needs_ocr=False,
                    quality_forced_ocr=False,
                )
            )
    return decisions


def _ocr_pages(
    path: Path,
    page_indexes_0: list[int],
    *,
    limits: HybridEngineLimits,
) -> tuple[dict[int, str], dict[str, Any]]:
    """OCR 0-based page indexes via existing Wathefni Mistral adapter."""
    import cv_extraction as cv

    meta_out: dict[str, Any] = {
        "provider": "mistral",
        "model": PINNED_OCR_MODEL,
        "retries": 0,
        "error": None,
        "request_id": None,
        "latency_ms": 0,
        "billable_pages": 0,
        "estimated_cost_usd": 0.0,
    }
    if not page_indexes_0:
        return {}, meta_out
    if not limits.allow_paid_ocr:
        meta_out["error"] = "paid_ocr_disabled"
        return {}, meta_out

    last_err = None
    for attempt in range(limits.max_retries + 1):
        meta_out["retries"] = attempt
        t0 = time.perf_counter()
        try:
            by_page, _blocks, meta = cv.extract_pdf_pages_with_mistral(path, page_indexes_0)
            meta_out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            meta_out["request_id"] = getattr(meta, "provider_request_id", None)
            meta_out["billable_pages"] = int(getattr(meta, "billable_pages", 0) or len(page_indexes_0))
            meta_out["estimated_cost_usd"] = float(
                getattr(meta, "estimated_cost_usd", None)
                or round(meta_out["billable_pages"] * COST_USD_PER_PAGE, 6)
            )
            meta_out["error"] = getattr(meta, "error", None)
            if by_page and not meta_out["error"]:
                return by_page, meta_out
            last_err = meta_out["error"] or "empty_ocr_response"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}:{exc}"
            meta_out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            meta_out["error"] = last_err
            logger.warning("hybrid_ocr_attempt_failed attempt=%s err=%s", attempt, last_err)
        time.sleep(min(0.5 * (attempt + 1), 2.0))
    meta_out["error"] = last_err or "ocr_failed"
    return {}, meta_out


def _build_envelope(
    *,
    path: Path,
    content_sha256: str,
    decisions: list[PageDecision],
    inspector_meta: dict[str, Any],
    ocr_meta: dict[str, Any],
    simulated: bool,
    cache_hit: bool,
    wall_ms: int,
    limits: HybridEngineLimits,
    error: str | None,
    company_code: str | None,
    document_class: str,
    subject_type: str,
    subject_key: str | None,
    source_channel: str,
) -> dict[str, Any]:
    pages_native = [d.page_number for d in decisions if d.method == "native"]
    pages_ocr = [d.page_number for d in decisions if d.method == "ocr"]
    pages_failed = [d.page_number for d in decisions if d.method == "failed"]
    billable = sum(1 for d in decisions if d.billable)
    projected = round(len(pages_ocr) * COST_USD_PER_PAGE, 6)
    actual_cost = float(ocr_meta.get("estimated_cost_usd") or 0.0)
    quality_ok = bool(decisions) and not pages_failed and error is None
    # Partial success still quality-flagged when any page succeeded.
    if any(d.method in {"native", "ocr"} and d.text for d in decisions):
        if pages_failed:
            quality_ok = False
        elif error in {None, "ocr_required_simulated", "paid_ocr_disabled"}:
            quality_ok = True if pages_native or (simulated and pages_ocr) or (
                not simulated and any(d.method == "ocr" and d.text for d in decisions)
            ) else quality_ok

    route = "local_hybrid_pdf_engine"
    return {
        "contract": CONTRACT_ENVELOPE,
        "company_code": company_code,
        "subject_type": subject_type,
        "subject_key": subject_key,
        "file_id": None,
        "content_sha256": content_sha256,
        "source_channel": source_channel,
        "migration_batch_id": None,
        "document_class": document_class,
        "authority_label": "machine_extracted",
        "filename": path.name,
        "processing": {
            "route": route,
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "provider": "mistral" if pages_ocr and not simulated else "local",
            "model": PINNED_OCR_MODEL if pages_ocr else None,
            "inspector_version": inspector_version(),
            "inspector_extension_sha256": inspector_extension_digest(),
            "request_id": ocr_meta.get("request_id"),
            "pages_local": pages_native,
            "pages_ocr": pages_ocr,
            "pages_failed": pages_failed,
            "page_methods": [
                {
                    "page": d.page_number,
                    "method": d.method,
                    "reason": d.reason,
                    "inspector_needs_ocr": d.inspector_needs_ocr,
                    "quality_forced_ocr": d.quality_forced_ocr,
                    "error": d.error,
                    "text_sha256": sha256_text(d.text) if d.text else None,
                    "char_count": len(d.text or ""),
                }
                for d in decisions
            ],
            "quality_ok": quality_ok,
            "confidence": None,
            "estimated_cost_usd": actual_cost if not simulated else 0.0,
            "projected_cost_usd_if_ocr_executed": projected,
            "billable_pages": billable if not simulated else 0,
            "simulated_ocr": simulated,
            "cache_hit": cache_hit,
            "wall_ms": wall_ms,
            "limits": asdict(limits) | {"cache_dir": str(limits.cache_dir) if limits.cache_dir else None},
            "inspector": inspector_meta,
            "ocr": ocr_meta,
            "job_id": None,
            "shadow": None,
        },
        "text_ref": "inline:merged_markdown",
        "structured_ref": None,
        "retention_class": "ephemeral_synthetic",
        "merged_markdown": None,  # filled by caller optionally; keep envelope lean when dumping
        "error": error,
        "created_at": utc_now(),
    }


def extract_pdf_hybrid(
    path: Path | str,
    *,
    limits: HybridEngineLimits | None = None,
    company_code: str | None = "WATHEFNI",
    document_class: str = "other",
    subject_type: str = "other",
    subject_key: str | None = None,
    source_channel: str = "offline_eval",
    include_merged_in_envelope: bool = False,
) -> HybridEngineResult:
    """Run local hybrid extraction. Default: paid OCR disabled (simulate)."""
    limits = limits or HybridEngineLimits()
    started = time.perf_counter()
    pdf_path = Path(path)
    if not pdf_path.is_file():
        env = {
            "contract": CONTRACT_ENVELOPE,
            "error": "file_not_found",
            "content_sha256": None,
        }
        return HybridEngineResult(ok=False, envelope=env, error="file_not_found")

    data = pdf_path.read_bytes()
    if len(data) > limits.max_bytes:
        return HybridEngineResult(
            ok=False,
            envelope={"contract": CONTRACT_ENVELOPE, "error": "max_bytes_exceeded"},
            error="max_bytes_exceeded",
        )
    content_sha = sha256_bytes(data)
    insp_ver = inspector_version()
    cache_key = build_cache_key(
        content_sha256=content_sha,
        inspector_ver=insp_ver,
        ocr_model=PINNED_OCR_MODEL,
        engine_version=ENGINE_VERSION,
        allow_paid_ocr=limits.allow_paid_ocr,
    )

    if limits.cache_dir:
        limits.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = limits.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                pages = [PageDecision(**p) for p in cached.get("pages", [])]
                return HybridEngineResult(
                    ok=bool(cached.get("ok")),
                    envelope=cached.get("envelope") or {},
                    pages=pages,
                    merged_markdown=cached.get("merged_markdown") or "",
                    error=cached.get("error"),
                    simulated_ocr=bool(cached.get("simulated_ocr", True)),
                    cache_hit=True,
                    inspector_version=insp_ver,
                    wall_ms=int((time.perf_counter() - started) * 1000),
                )
            except Exception:
                logger.warning("hybrid_cache_read_failed key=%s", cache_key)

    try:
        page_objs, inspector_meta = _load_pages_markdown(pdf_path)
    except Exception as exc:  # noqa: BLE001
        return HybridEngineResult(
            ok=False,
            envelope={"contract": CONTRACT_ENVELOPE, "error": f"inspector_failed:{exc}"},
            error=f"inspector_failed:{exc}",
            wall_ms=int((time.perf_counter() - started) * 1000),
        )

    if len(page_objs) > limits.max_pages:
        return HybridEngineResult(
            ok=False,
            envelope={"contract": CONTRACT_ENVELOPE, "error": "max_pages_exceeded", "pages": len(page_objs)},
            error="max_pages_exceeded",
            wall_ms=int((time.perf_counter() - started) * 1000),
        )

    decisions = _decide_pages(page_objs)
    ocr_needed = [d for d in decisions if d.method == "ocr"]
    projected = len(ocr_needed) * COST_USD_PER_PAGE
    error: str | None = None
    ocr_meta: dict[str, Any] = {
        "provider": "mistral",
        "model": PINNED_OCR_MODEL,
        "simulated": not limits.allow_paid_ocr,
        "pages_requested_1idx": [d.page_number for d in ocr_needed],
        "pages_requested_0idx": [d.page_index for d in ocr_needed],
        "projected_cost_usd": round(projected, 6),
    }

    if projected > limits.max_projected_cost_usd + 1e-9:
        error = "projected_cost_cap_exceeded"
        for d in ocr_needed:
            d.method = "failed"
            d.error = error
        ocr_meta["error"] = error
    elif ocr_needed and not limits.allow_paid_ocr:
        # Simulate exact pages that would be sent to Mistral.
        error = "ocr_required_simulated"
        for d in ocr_needed:
            d.text = f"[OCR_SIMULATED page={d.page_number} reason={d.reason}]"
            d.billable = False
        ocr_meta["error"] = "paid_ocr_disabled"
        ocr_meta["simulated_page_markers"] = True
    elif ocr_needed:
        if time.perf_counter() - started > limits.timeout_s:
            error = "timeout_before_ocr"
            for d in ocr_needed:
                d.method = "failed"
                d.error = error
        else:
            by_page, ocr_meta_live = _ocr_pages(
                pdf_path,
                [d.page_index for d in ocr_needed],
                limits=limits,
            )
            ocr_meta.update(ocr_meta_live)
            ocr_meta["simulated"] = False
            for d in ocr_needed:
                text = by_page.get(d.page_number) or by_page.get(d.page_index + 1) or ""
                if text:
                    d.text = text
                    d.billable = True
                    d.latency_ms = int(ocr_meta_live.get("latency_ms") or 0)
                else:
                    # One failed page must not discard successful pages.
                    d.method = "failed"
                    d.error = ocr_meta_live.get("error") or "ocr_page_empty"
                    error = error or d.error

    # Preserve native pages even when some OCR pages fail.
    merged_parts = []
    for d in sorted(decisions, key=lambda x: x.page_number):
        if d.method in {"native", "ocr"} and d.text:
            merged_parts.append(d.text)
        elif d.method == "failed":
            merged_parts.append(f"[PAGE_{d.page_number}_FAILED:{d.error}]")
    merged = "\n\n".join(merged_parts).strip()

    wall_ms = int((time.perf_counter() - started) * 1000)
    if wall_ms > int(limits.timeout_s * 1000) and error is None:
        error = "timeout_soft"

    envelope = _build_envelope(
        path=pdf_path,
        content_sha256=content_sha,
        decisions=decisions,
        inspector_meta=inspector_meta,
        ocr_meta=ocr_meta,
        simulated=not limits.allow_paid_ocr,
        cache_hit=False,
        wall_ms=wall_ms,
        limits=limits,
        error=error,
        company_code=company_code,
        document_class=document_class,
        subject_type=subject_type,
        subject_key=subject_key or pdf_path.stem,
        source_channel=source_channel,
    )
    if include_merged_in_envelope:
        envelope["merged_markdown"] = merged

    ok = bool(merged) and not (
        error in {"max_pages_exceeded", "max_bytes_exceeded", "inspector_failed", "projected_cost_cap_exceeded"}
    )
    # Simulated OCR still counts as ok for offline routing qualification.
    if error == "ocr_required_simulated":
        ok = True

    result = HybridEngineResult(
        ok=ok,
        envelope=envelope,
        pages=decisions,
        merged_markdown=merged,
        error=error,
        simulated_ocr=not limits.allow_paid_ocr,
        cache_hit=False,
        inspector_version=insp_ver,
        wall_ms=wall_ms,
    )

    if limits.cache_dir:
        try:
            cache_file = limits.cache_dir / f"{cache_key}.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "ok": result.ok,
                        "error": result.error,
                        "simulated_ocr": result.simulated_ocr,
                        "merged_markdown": result.merged_markdown,
                        "envelope": envelope,
                        "pages": [asdict(p) for p in decisions],
                        "cache_key": cache_key,
                        "created_at": utc_now(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception:
            logger.warning("hybrid_cache_write_failed key=%s", cache_key)

    return result
