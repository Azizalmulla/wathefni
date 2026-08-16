"""AnyDoc Office Authority Closure — format-specific authority models.

Local bytes only. Pinned firecrawl-anydoc. Automatic fallback to existing readers.
No GPT. Never PDF / images / identity / hosted Firecrawl /parse.

Authority models
----------------
DOCX:
  AnyDoc may become primary local text normalization when quality gates pass.
  Existing DOCX parser remains immediate fallback; blocks/provenance preserved.

PPTX / ODT / ODS:
  Document-text normalization authority only (search / understanding).
  Preserve original structure evidence; fallback on disagreement or low confidence.

XLSX / CSV:
  Structured spreadsheet parsers remain authoritative for rows/cells/formulas/
  imports/payroll/migration. AnyDoc attaches Markdown normalization only —
  never replaces structured authority text used by those paths.

Shadow-only (unchanged observation):
  RTF, ODP, DOC, XLS, PPT, other legacy Office formats.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import anydoc_office_shadow as shadow

logger = logging.getLogger("wathefni.anydoc_office_authority")

CONTRACT = "anydoc_office_authority_closure_wave1"
PINNED_PACKAGE = shadow.PINNED_PACKAGE
PINNED_VERSION = shadow.PINNED_VERSION

MODE_OFF = "off"
MODE_STAGING = "staging"
MODE_PRODUCTION = "production"
_VALID_MODES = frozenset({MODE_OFF, MODE_STAGING, MODE_PRODUCTION, ""})

# Format → authority role when the closure flag is on.
ROLE_PRIMARY_NORMALIZE = "primary_local_normalization"
ROLE_DOC_TEXT_NORMALIZE = "document_text_normalization"
ROLE_MARKDOWN_ONLY = "markdown_normalization_only"
ROLE_SHADOW_ONLY = "shadow_only"
ROLE_DENIED = "denied"

AUTHORITY_ROLES: dict[str, str] = {
    ".docx": ROLE_PRIMARY_NORMALIZE,
    ".pptx": ROLE_DOC_TEXT_NORMALIZE,
    ".odt": ROLE_DOC_TEXT_NORMALIZE,
    ".ods": ROLE_DOC_TEXT_NORMALIZE,
    ".xlsx": ROLE_MARKDOWN_ONLY,
    ".csv": ROLE_MARKDOWN_ONLY,
    # Explicit shadow-only (also covered by default).
    ".rtf": ROLE_SHADOW_ONLY,
    ".odp": ROLE_SHADOW_ONLY,
    ".doc": ROLE_SHADOW_ONLY,
    ".xls": ROLE_SHADOW_ONLY,
    ".ppt": ROLE_SHADOW_ONLY,
}


def authority_mode(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_ANYDOC_OFFICE_AUTHORITY") or MODE_OFF).strip().lower()
    if raw in {"1", "true", "on", "yes", "enabled"}:
        return MODE_PRODUCTION
    if raw not in _VALID_MODES:
        return MODE_OFF
    return raw or MODE_OFF


def authority_enabled(environ: dict[str, str] | None = None) -> bool:
    return authority_mode(environ) in {MODE_STAGING, MODE_PRODUCTION}


def role_for_extension(ext: str) -> str:
    e = (ext or "").lower()
    if e in shadow.DENIED_EXTENSIONS or e == ".pdf":
        return ROLE_DENIED
    return AUTHORITY_ROLES.get(e, ROLE_SHADOW_ONLY)


def _auth_weak(text: str | None) -> bool:
    sample = str(text or "").strip()
    if not sample:
        return True
    q = shadow._quality_metrics(sample)
    return not q.get("ok")


def _should_promote_docx(*, anydoc_ok: bool, quality_ok: bool, comparison: dict[str, Any], auth_text: str | None) -> tuple[bool, str | None]:
    if not anydoc_ok:
        return False, "anydoc_failed"
    if not quality_ok:
        return False, "quality_gate_failed"
    if comparison.get("material_disagreement") and not _auth_weak(auth_text):
        # Prefer existing DOCX parser when both look strong but disagree.
        return False, "material_disagreement_with_existing_docx"
    # Promote when quality OK and (agree or existing weak/empty).
    return True, None


def _should_promote_doc_text(*, anydoc_ok: bool, quality_ok: bool, comparison: dict[str, Any], auth_text: str | None) -> tuple[bool, str | None]:
    if not anydoc_ok:
        return False, "anydoc_failed"
    if not quality_ok:
        return False, "quality_gate_failed"
    if _auth_weak(auth_text):
        # Current handling has little/no usable text — normalize with AnyDoc.
        return True, None
    if comparison.get("material_disagreement"):
        return False, "material_disagreement_keep_existing"
    # Soft agree with existing text — keep existing as authority, attach AnyDoc as alt.
    return False, "existing_text_retained_anydoc_attached"


def apply_office_authority(
    result: Any,
    path: Path | str,
    *,
    document_class: str | None = None,
    mime_type: str | None = None,
    company_code: str | None = None,
    environ: dict[str, str] | None = None,
) -> Any:
    """Apply format-specific AnyDoc authority. Never raises. No GPT."""
    try:
        return _apply_office_authority_inner(
            result,
            path,
            document_class=document_class,
            mime_type=mime_type,
            company_code=company_code,
            environ=environ,
        )
    except Exception:  # noqa: BLE001
        logger.exception("anydoc_office_authority_outer_fail_open")
        return result


def _apply_office_authority_inner(
    result: Any,
    path: Path | str,
    *,
    document_class: str | None,
    mime_type: str | None,
    company_code: str | None,
    environ: dict[str, str] | None,
) -> Any:
    mode = authority_mode(environ)
    file_path = Path(path)
    ext = file_path.suffix.lower()
    role = role_for_extension(ext)

    # Always keep shadow observation for allowlisted formats when shadow flag on,
    # including legacy. Authority layer is separate.
    if not authority_enabled(environ):
        if shadow.shadow_enabled(environ):
            return shadow.maybe_run_and_attach(
                result,
                path,
                document_class=document_class,
                mime_type=mime_type,
                company_code=company_code,
            )
        return result

    # Denied classes — never call AnyDoc for identity/PDF/images.
    doc_class = str(document_class or "").strip().lower()
    if doc_class in shadow.IDENTITY_CLASSES or "identity" in doc_class:
        return _attach_decision(
            result,
            {
                "contract": CONTRACT,
                "mode": mode,
                "role": ROLE_DENIED,
                "selected_engine": "existing",
                "fallback_reason": "identity_document_denied",
                "influences_structured_spreadsheet": False,
                "influences_payroll": False,
                "influences_migration": False,
                "influences_admission": False,
                "influences_cv_v2": False,
                "hosted_firecrawl_parse": False,
                "local_bytes_only": True,
                "pinned_version": PINNED_VERSION,
            },
        )

    mime = str(mime_type or "").lower()
    if ext in shadow.DENIED_EXTENSIONS or "pdf" in mime or mime.startswith("image/") or role == ROLE_DENIED:
        return _attach_decision(
            result,
            {
                "contract": CONTRACT,
                "mode": mode,
                "role": ROLE_DENIED,
                "extension": ext,
                "selected_engine": "existing",
                "fallback_reason": "denied_extension_or_mime",
                "hosted_firecrawl_parse": False,
                "local_bytes_only": True,
                "pinned_version": PINNED_VERSION,
            },
        )

    auth_text = getattr(result, "text", None) if result is not None else None
    content_sha = getattr(result, "content_sha256", None) if result is not None else None

    # Shadow-only formats: observation blob only; never promote text.
    if role == ROLE_SHADOW_ONLY:
        obs = shadow.run_anydoc_office_shadow(
            file_path,
            authoritative_text=auth_text,
            content_sha256=content_sha,
            document_class=document_class,
            mime_type=mime_type,
            company_code=company_code,
            environ={**(environ or os.environ), "WATHEFNI_ANYDOC_OFFICE_SHADOW": "production_shadow"},
        )
        decision = {
            "contract": CONTRACT,
            "mode": mode,
            "role": ROLE_SHADOW_ONLY,
            "extension": ext,
            "selected_engine": "existing",
            "fallback_reason": "format_shadow_only",
            "engine_version": obs.get("engine_version"),
            "pinned_version": PINNED_VERSION,
            "comparison_outcome": (obs.get("comparison") or {}).get("disagreement_reasons"),
            "material_disagreement": (obs.get("comparison") or {}).get("material_disagreement"),
            "shadow": {k: obs.get(k) for k in ("ok", "fail_open", "latency_ms", "output_sha256", "character_count", "error", "quality")},
            "influences_structured_spreadsheet": False,
            "influences_payroll": False,
            "influences_migration": False,
            "influences_admission": False,
            "hosted_firecrawl_parse": False,
            "local_bytes_only": True,
        }
        return _attach_decision(result, decision, shadow_blob=obs)

    # Run AnyDoc observation for authority candidates.
    # Force shadow-enabled environ so the converter runs even if shadow flag is off.
    forced = {**(environ or dict(os.environ)), "WATHEFNI_ANYDOC_OFFICE_SHADOW": "production_shadow"}
    obs = shadow.run_anydoc_office_shadow(
        file_path,
        authoritative_text=auth_text,
        content_sha256=content_sha,
        document_class=document_class,
        mime_type=mime_type,
        company_code=company_code,
        environ=forced,
    )
    quality = obs.get("quality") or {}
    comparison = obs.get("comparison") or {}
    markdown = None
    # Re-fetch markdown only when we may promote — shadow drops full text from blob.
    # Call converter again only on promote path via internal helper.
    anydoc_ok = bool(obs.get("ok"))
    quality_ok = bool(quality.get("ok"))

    base_decision: dict[str, Any] = {
        "contract": CONTRACT,
        "mode": mode,
        "role": role,
        "extension": ext,
        "engine": "anydoc",
        "package": PINNED_PACKAGE,
        "pinned_version": PINNED_VERSION,
        "engine_version": obs.get("engine_version") or shadow._package_version(),
        "latency_ms": obs.get("latency_ms"),
        "output_sha256": obs.get("output_sha256"),
        "character_count": obs.get("character_count"),
        "quality": quality,
        "comparison_outcome": comparison.get("disagreement_reasons"),
        "material_disagreement": comparison.get("material_disagreement"),
        "completeness_ratio": comparison.get("completeness_ratio"),
        "content_sha256": obs.get("content_sha256") or content_sha,
        "hosted_firecrawl_parse": False,
        "local_bytes_only": True,
        "no_gpt_fallback": True,
        "influences_structured_spreadsheet": False,
        "influences_payroll": False,
        "influences_migration": False,
        "influences_admission": False,
        "influences_cv_v2": False,
        "influences_workflows": False,
        "company_code": (company_code or "").strip().upper() or None,
    }

    if role == ROLE_MARKDOWN_ONLY:
        # Never mutate authoritative structured/raw text.
        md = _recover_markdown(file_path, ext) if anydoc_ok and quality_ok else None
        decision = {
            **base_decision,
            "selected_engine": "existing_structured",
            "fallback_reason": None if (anydoc_ok and quality_ok) else (
                obs.get("error") or "anydoc_unavailable_for_markdown_normalize"
            ),
            "normalized_markdown_attached": bool(md),
            "normalized_markdown_sha256": quality.get("output_sha256") if md else None,
            "normalized_markdown_chars": quality.get("chars") if md else None,
            # Store markdown for understanding consumers only — not as result.text.
            "normalized_markdown": md,
            "structured_authority_unchanged": True,
        }
        return _attach_decision(result, decision, shadow_blob=obs)

    if role == ROLE_PRIMARY_NORMALIZE:
        promote, reason = _should_promote_docx(
            anydoc_ok=anydoc_ok,
            quality_ok=quality_ok,
            comparison=comparison,
            auth_text=auth_text,
        )
        if promote:
            md = _recover_markdown(file_path, ext)
            if not md:
                promote = False
                reason = "markdown_recover_failed"
        if promote and md is not None:
            decision = {
                **base_decision,
                "selected_engine": "anydoc",
                "fallback_reason": None,
                "promoted": True,
                "existing_method": getattr(result, "method", None),
                "existing_text_chars": len(str(auth_text or "")),
                "existing_text_sha256": comparison.get("authoritative", {}).get("sha256"),
            }
            result = _promote_text(
                result,
                text=md,
                method="anydoc_docx",
                preserve_blocks=True,
            )
            return _attach_decision(result, decision, shadow_blob=obs)
        decision = {
            **base_decision,
            "selected_engine": "existing_docx",
            "fallback_reason": reason or obs.get("error") or "fallback_existing",
            "promoted": False,
        }
        return _attach_decision(result, decision, shadow_blob=obs)

    if role == ROLE_DOC_TEXT_NORMALIZE:
        promote, reason = _should_promote_doc_text(
            anydoc_ok=anydoc_ok,
            quality_ok=quality_ok,
            comparison=comparison,
            auth_text=auth_text,
        )
        if promote:
            md = _recover_markdown(file_path, ext)
            if not md:
                promote = False
                reason = "markdown_recover_failed"
        if promote and md is not None:
            method_map = {".pptx": "anydoc_pptx", ".odt": "anydoc_odt", ".ods": "anydoc_ods"}
            decision = {
                **base_decision,
                "selected_engine": "anydoc",
                "fallback_reason": None,
                "promoted": True,
                "existing_method": getattr(result, "method", None),
                "existing_text_chars": len(str(auth_text or "")),
                "structure_evidence_preserved": True,
            }
            result = _promote_text(
                result,
                text=md,
                method=method_map.get(ext, "anydoc_office"),
                preserve_blocks=True,
            )
            return _attach_decision(result, decision, shadow_blob=obs)
        decision = {
            **base_decision,
            "selected_engine": "existing",
            "fallback_reason": reason or obs.get("error") or "fallback_existing",
            "promoted": False,
            "normalized_markdown_attached": False,
        }
        # If existing retained but AnyDoc OK, still attach MD for understanding.
        if anydoc_ok and quality_ok and reason == "existing_text_retained_anydoc_attached":
            md = _recover_markdown(file_path, ext)
            if md:
                decision["normalized_markdown_attached"] = True
                decision["normalized_markdown"] = md
                decision["normalized_markdown_sha256"] = quality.get("output_sha256")
        return _attach_decision(result, decision, shadow_blob=obs)

    # Default: shadow attach only.
    return _attach_decision(
        result,
        {
            **base_decision,
            "selected_engine": "existing",
            "fallback_reason": "unknown_role",
            "promoted": False,
        },
        shadow_blob=obs,
    )


def _recover_markdown(path: Path, ext: str) -> str | None:
    """Re-run AnyDoc to obtain markdown for promotion (shadow blob omits full text)."""
    try:
        data = path.read_bytes()
        parsed = shadow._call_anydoc(path, data, ext)
        md = str(parsed.get("markdown") or "")
        return md if md.strip() else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("anydoc_office_authority_recover_failed path=%s err=%s", path, exc)
        return None


def _promote_text(result: Any, *, text: str, method: str, preserve_blocks: bool) -> Any:
    if result is None:
        return result
    try:
        # Preserve prior text as evidence for audit.
        meta = dict(getattr(result, "metadata", None) or {})
        meta["anydoc_prior_text_chars"] = len(str(getattr(result, "text", "") or ""))
        meta["anydoc_prior_method"] = getattr(result, "method", None)
        result.metadata = meta
        result.text = text
        result.method = method
        # Quality for promoted Markdown
        try:
            import cv_extraction as cv

            result.quality_ok = bool(cv.cv_text_quality_ok(text))
        except Exception:
            result.quality_ok = bool(text and len(text.strip()) >= 40)
        result.error = None if text.strip() else (getattr(result, "error", None) or "no_text_extracted")
        if not preserve_blocks:
            result.blocks = []
        # blocks/provenance left intact for DOCX structure evidence.
    except Exception:  # noqa: BLE001
        logger.exception("anydoc_office_authority_promote_failed")
    return result


def _attach_decision(result: Any, decision: dict[str, Any], shadow_blob: dict[str, Any] | None = None) -> Any:
    if result is None:
        return result
    try:
        meta = dict(getattr(result, "metadata", None) or {})
        # Do not persist full markdown into long-lived dumps when huge — keep under authority key.
        meta["anydoc_office_authority"] = decision
        if shadow_blob is not None:
            # Observation companion (metrics only; shadow already strips markdown).
            meta["anydoc_office_shadow"] = {
                k: shadow_blob.get(k)
                for k in (
                    "contract",
                    "mode",
                    "ok",
                    "fail_open",
                    "latency_ms",
                    "output_sha256",
                    "character_count",
                    "quality",
                    "comparison",
                    "error",
                    "engine_version",
                    "pinned_version",
                    "influences_routing",
                    "local_bytes_only",
                    "hosted_firecrawl_parse",
                    "extension",
                    "content_sha256",
                )
            }
        result.metadata = meta
    except Exception:  # noqa: BLE001
        logger.exception("anydoc_office_authority_attach_failed")
    return result


def maybe_run_and_attach(
    result: Any,
    path: Path | str,
    *,
    document_class: str | None = None,
    mime_type: str | None = None,
    company_code: str | None = None,
) -> Any:
    """Entry used by extract façades — authority if enabled, else shadow."""
    return apply_office_authority(
        result,
        path,
        document_class=document_class,
        mime_type=mime_type,
        company_code=company_code,
    )
