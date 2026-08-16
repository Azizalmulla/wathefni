"""AnyDoc Office Shadow Canary Wave 1 — observation only.

Local bytes only. Never influences routing, classification, CV V2, validation,
admission, or workflows. Fail-open on any error/timeout/import failure.

Allowlist: doc/docx, ppt/pptx, xls/xlsx, odt/ods/odp, rtf, csv.
Deny: PDF, images, identity document classes, hosted Firecrawl /parse.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

logger = logging.getLogger("wathefni.anydoc_office_shadow")

CONTRACT = "anydoc_office_shadow_wave1"
PINNED_PACKAGE = "firecrawl-anydoc"
PINNED_VERSION = "0.1.2"
DEFAULT_TIMEOUT_MS = 2000
# Align with email/CV per-file honesty; never shadow huge archives.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024

MODE_OFF = "off"
MODE_STAGING = "staging_shadow"
MODE_PRODUCTION = "production_shadow"
_VALID_MODES = frozenset({MODE_OFF, MODE_STAGING, MODE_PRODUCTION, ""})

ALLOWED_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
        ".csv",
    }
)
DENIED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".heic",
        ".gif",
        ".bmp",
    }
)
IDENTITY_CLASSES = frozenset(
    {
        "identity",
        "civil_id",
        "passport",
        "residency",
        "residence",
        "work_permit",
        "medical",
        "identity_document",
    }
)

_MOJIBAKE_RE = re.compile(r"(Ã.|Â.|Ù.|Ø.|ð.|�|\ufffd|ÃÑ|Ùn|Â\x9d)")
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")
_MIN_CHARS_DEFAULT = 40
_MIN_WORDS_DEFAULT = 6


def shadow_mode(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_ANYDOC_OFFICE_SHADOW") or MODE_OFF).strip().lower()
    if raw in {"1", "true", "on", "yes", "enabled"}:
        # Treat boolean-on as production_shadow for operability, but prefer explicit modes.
        return MODE_PRODUCTION
    if raw not in _VALID_MODES:
        return MODE_OFF
    return raw or MODE_OFF


def shadow_enabled(environ: dict[str, str] | None = None) -> bool:
    return shadow_mode(environ) in {MODE_STAGING, MODE_PRODUCTION}


def shadow_timeout_ms(environ: dict[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS") or "").strip()
    try:
        value = int(raw) if raw else DEFAULT_TIMEOUT_MS
    except ValueError:
        value = DEFAULT_TIMEOUT_MS
    return max(50, min(value, 15_000))


def shadow_max_bytes(environ: dict[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_ANYDOC_OFFICE_SHADOW_MAX_BYTES") or "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_BYTES
    except ValueError:
        value = DEFAULT_MAX_BYTES
    return max(64 * 1024, min(value, 64 * 1024 * 1024))


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return str(version(PINNED_PACKAGE))
    except Exception:
        try:
            import anydoc  # noqa: F401

            return str(getattr(anydoc, "__version__", PINNED_VERSION) or PINNED_VERSION)
        except Exception:
            return PINNED_VERSION


def _quality_metrics(markdown: str | None) -> dict[str, Any]:
    text = str(markdown or "")
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    arabic_chars = len(_ARABIC_LETTER_RE.findall(text))
    printable = sum(1 for ch in text if ch.isprintable() and not ch.isspace())
    alpha = sum(1 for ch in text if ch.isalpha())
    replacement = text.count("\ufffd") + text.count("�")
    mojibake_hits = len(_MOJIBAKE_RE.findall(text))
    presentation = len(_ARABIC_PRESENTATION_RE.findall(text))
    alpha_ratio = round(alpha / max(printable, 1), 4) if printable else 0.0
    empty = chars == 0 or not text.strip()
    below_min = (not empty) and (chars < _MIN_CHARS_DEFAULT or words < _MIN_WORDS_DEFAULT)
    suspicious_printable = bool(
        chars >= _MIN_CHARS_DEFAULT
        and words >= _MIN_WORDS_DEFAULT
        and alpha_ratio < 0.35
        and arabic_chars == 0
    )
    reversed_or_corrupted_arabic = bool(
        (presentation >= 8 and arabic_chars == 0)
        or (arabic_chars >= 20 and mojibake_hits >= 3)
        or (replacement >= 8 and arabic_chars > 0)
    )
    reasons: list[str] = []
    if empty:
        reasons.append("empty_text")
    if below_min:
        reasons.append("below_min_chars_or_words")
    if mojibake_hits > 0 or replacement >= 3:
        reasons.append("mojibake")
    if reversed_or_corrupted_arabic:
        reasons.append("arabic_corruption")
    if suspicious_printable:
        reasons.append("suspicious_printable")
    ok = not reasons
    return {
        "ok": ok,
        "reasons": reasons,
        "chars": chars,
        "words": words,
        "arabic_chars": arabic_chars,
        "alpha_ratio": alpha_ratio,
        "replacement_chars": replacement,
        "mojibake_hits": mojibake_hits,
        "arabic_presentation_forms": presentation,
        "has_heading_md": bool(re.search(r"(?m)^#{1,6}\s", text)),
        "has_table_md": "|" in text and "---" in text,
        "has_list_md": bool(re.search(r"(?m)^(\s*[-*]|\s*\d+\.)\s", text)),
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "suspicious_printable_but_meaningless": suspicious_printable,
        "reversed_or_corrupted_arabic": reversed_or_corrupted_arabic,
    }


def _structure_signals(text: str | None) -> dict[str, Any]:
    sample = str(text or "")
    return {
        "chars": len(sample),
        "words": len(re.findall(r"\S+", sample)),
        "arabic_chars": len(_ARABIC_LETTER_RE.findall(sample)),
        "has_heading_md": bool(re.search(r"(?m)^#{1,6}\s", sample)),
        "has_table_md": "|" in sample and "---" in sample,
        "has_list_md": bool(re.search(r"(?m)^(\s*[-*]|\s*\d+\.)\s", sample)),
        "has_blockquote": bool(re.search(r"(?m)^>", sample)),
        "sha256": hashlib.sha256(sample.encode("utf-8")).hexdigest() if sample else None,
    }


def compare_to_authoritative(
    *,
    anydoc_markdown: str | None,
    authoritative_text: str | None,
    anydoc_quality: dict[str, Any],
) -> dict[str, Any]:
    auth = _structure_signals(authoritative_text)
    shadow = _structure_signals(anydoc_markdown)
    auth_chars = int(auth.get("chars") or 0)
    shadow_chars = int(shadow.get("chars") or 0)
    completeness_ratio = round(shadow_chars / max(auth_chars, 1), 4) if auth_chars else None
    disagreement_reasons: list[str] = []
    if auth_chars > 0 and shadow_chars == 0:
        disagreement_reasons.append("anydoc_empty_while_auth_has_text")
    if auth_chars == 0 and shadow_chars > 0:
        # No Wathefni Markdown authority for this format yet — informational only.
        disagreement_reasons.append("anydoc_only_no_auth_baseline")
    if completeness_ratio is not None and completeness_ratio < 0.5 and auth_chars >= 80:
        disagreement_reasons.append("completeness_below_50pct")
    if completeness_ratio is not None and completeness_ratio > 2.0 and shadow_chars >= 80 and auth_chars >= 80:
        disagreement_reasons.append("anydoc_much_longer_than_auth")
    if auth.get("has_table_md") and not shadow.get("has_table_md") and auth_chars >= 40:
        disagreement_reasons.append("auth_table_missing_in_anydoc")
    if auth.get("has_list_md") and not shadow.get("has_list_md") and auth_chars >= 40:
        disagreement_reasons.append("auth_list_missing_in_anydoc")
    if int(auth.get("arabic_chars") or 0) >= 20 and int(shadow.get("arabic_chars") or 0) < max(
        5, int(auth["arabic_chars"]) // 4
    ):
        disagreement_reasons.append("arabic_loss")
    if anydoc_quality and not anydoc_quality.get("ok"):
        disagreement_reasons.append("anydoc_quality_gate_failed")
    # Material disagreements exclude "anydoc_only_no_auth_baseline".
    material = [r for r in disagreement_reasons if r != "anydoc_only_no_auth_baseline"]
    return {
        "authoritative": auth,
        "anydoc": shadow,
        "completeness_ratio": completeness_ratio,
        "disagreement": bool(material),
        "disagreement_reasons": disagreement_reasons,
        "material_disagreement": bool(material),
        "influences_routing": False,
        "authoritative_parser_unchanged": True,
    }


def _call_anydoc(path: Path, data: bytes, ext: str) -> dict[str, Any]:
    import anydoc

    fmt_name = ext.lstrip(".").lower()
    # Python binding named formats omit some aliases (e.g. xls); prefer content/path fallback.
    t0 = time.perf_counter()
    markdown = None
    fmt_used: str | None = None
    last_err: Exception | None = None
    for attempt in (
        ("named", fmt_name),
        ("detect", None),
        ("path", "path"),
    ):
        try:
            if attempt[0] == "named":
                markdown = anydoc.to_markdown_bytes(data, fmt_name)
                fmt_used = fmt_name
            elif attempt[0] == "detect":
                markdown = anydoc.to_markdown_bytes(data)
                fmt_used = "content_detect"
            else:
                markdown = anydoc.to_markdown(str(path))
                fmt_used = "path"
            break
        except Exception as exc:  # noqa: BLE001 — try next strategy
            last_err = exc
            continue
    if markdown is None:
        assert last_err is not None
        raise last_err
    wall_ms = int((time.perf_counter() - t0) * 1000)
    quality = _quality_metrics(markdown)
    return {
        "ok": True,
        "wall_ms": wall_ms,
        "markdown": markdown,
        "format_detected": fmt_used,
        "quality": quality,
    }


def run_anydoc_office_shadow(
    path: Path | str,
    *,
    authoritative_text: str | None = None,
    content_sha256: str | None = None,
    document_class: str | None = None,
    mime_type: str | None = None,
    company_code: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Observe AnyDoc beside the authoritative office parser. Always fail-open."""
    mode = shadow_mode(environ)
    enabled = mode in {MODE_STAGING, MODE_PRODUCTION}
    base: dict[str, Any] = {
        "contract": CONTRACT,
        "mode": mode,
        "enabled": enabled,
        "influences_routing": False,
        "influences_classification": False,
        "influences_cv_v2": False,
        "influences_validation": False,
        "influences_admission": False,
        "influences_workflows": False,
        "hosted_firecrawl_parse": False,
        "local_bytes_only": True,
        "engine": "anydoc",
        "package": PINNED_PACKAGE,
        "pinned_version": PINNED_VERSION,
        "engine_version": _package_version(),
        "ok": False,
        "company_code": (company_code or "").strip().upper() or None,
    }
    if not enabled:
        base["skipped"] = "flag_off"
        return base

    doc_class = str(document_class or "").strip().lower()
    if doc_class in IDENTITY_CLASSES or "identity" in doc_class:
        base["skipped"] = "identity_document_denied"
        base["deny_reason"] = "never_send_identity_through_anydoc"
        return base

    file_path = Path(path)
    ext = file_path.suffix.lower()
    mime = str(mime_type or "").lower()
    if ext in DENIED_EXTENSIONS or "pdf" in mime or mime.startswith("image/"):
        base["skipped"] = "denied_extension_or_mime"
        base["extension"] = ext
        return base
    if ext == ".pdf":
        base["skipped"] = "pdf_denied"
        return base
    if ext not in ALLOWED_EXTENSIONS:
        base["skipped"] = "extension_not_in_allowlist"
        base["extension"] = ext
        return base

    if not file_path.exists() or not file_path.is_file():
        base["skipped"] = "missing_file"
        return base

    max_bytes = shadow_max_bytes(environ)
    try:
        size = int(file_path.stat().st_size)
    except OSError as exc:
        base["skipped"] = "stat_failed"
        base["error"] = str(exc)
        base["fail_open"] = True
        return base
    base["bytes"] = size
    if size > max_bytes:
        base["skipped"] = "file_too_large"
        base["max_bytes"] = max_bytes
        return base

    try:
        data = file_path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"read_failed:{exc}"
        base["fail_open"] = True
        return base

    digest = content_sha256 or hashlib.sha256(data).hexdigest()
    base["content_sha256"] = digest
    # Malware scanning is an upstream intake gate; shadow never bypasses it and
    # never uploads bytes. Record that we rely on prior gates.
    base["malware_gate"] = "upstream_intake_required"
    base["file_size_gate"] = {"max_bytes": max_bytes, "passed": True}

    timeout_ms = shadow_timeout_ms(environ)
    base["timeout_ms"] = timeout_ms
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_call_anydoc, file_path, data, ext)
            parsed = fut.result(timeout=timeout_ms / 1000.0)
        wall_ms = int((time.perf_counter() - started) * 1000)
        quality = parsed.get("quality") or _quality_metrics(parsed.get("markdown"))
        comparison = compare_to_authoritative(
            anydoc_markdown=parsed.get("markdown"),
            authoritative_text=authoritative_text,
            anydoc_quality=quality,
        )
        # Drop full markdown from persisted blob — keep hash/metrics only.
        return {
            **base,
            "ok": True,
            "fail_open": False,
            "extension": ext,
            "latency_ms": wall_ms,
            "library_wall_ms": parsed.get("wall_ms"),
            "format_detected": parsed.get("format_detected"),
            "character_count": quality.get("chars"),
            "output_sha256": quality.get("output_sha256"),
            "quality": quality,
            "comparison": comparison,
            "error": None if quality.get("ok") else ",".join(quality.get("reasons") or []) or "quality_failed",
        }
    except FuturesTimeout:
        wall_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("anydoc_office_shadow_timeout path=%s timeout_ms=%s", file_path, timeout_ms)
        return {
            **base,
            "ok": False,
            "fail_open": True,
            "extension": ext,
            "latency_ms": wall_ms,
            "error": "timeout",
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        wall_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("anydoc_office_shadow_fail_open path=%s error=%s", file_path, exc)
        return {
            **base,
            "ok": False,
            "fail_open": True,
            "extension": ext,
            "latency_ms": wall_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


def attach_shadow_to_result(result: Any, shadow: dict[str, Any] | None) -> Any:
    """Attach observation blob onto ExtractionResult.metadata without altering text/method."""
    if result is None or shadow is None:
        return result
    try:
        meta = dict(getattr(result, "metadata", None) or {})
        meta["anydoc_office_shadow"] = shadow
        result.metadata = meta
    except Exception:  # noqa: BLE001
        logger.exception("anydoc_office_shadow_attach_failed")
    return result


def maybe_run_and_attach(
    result: Any,
    path: Path | str,
    *,
    document_class: str | None = None,
    mime_type: str | None = None,
    company_code: str | None = None,
) -> Any:
    """Convenience for extract façades — never raises."""
    try:
        if not shadow_enabled():
            return result
        auth_text = getattr(result, "text", None) if result is not None else None
        content_sha = getattr(result, "content_sha256", None) if result is not None else None
        shadow = run_anydoc_office_shadow(
            path,
            authoritative_text=auth_text,
            content_sha256=content_sha,
            document_class=document_class,
            mime_type=mime_type,
            company_code=company_code,
        )
        return attach_shadow_to_result(result, shadow)
    except Exception:  # noqa: BLE001
        logger.exception("anydoc_office_shadow_maybe_outer_fail_open")
        return result
