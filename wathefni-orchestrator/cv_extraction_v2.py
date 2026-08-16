"""CV Extraction V2 — Mistral Document AI structured extraction.

Runs inside the existing shared durable CV pipeline after text/OCR evidence is
available. Does not create a second intake path.

Primary path (all formats):
  PDF / scanned PDF / image / DOCX → mistral-ocr-4-0 (+ document_annotation)

Fallback:
  Wathefni internal extractor (same cv-extraction-v2 contract) on Mistral
  outage / timeout / rate-limit / exhausted retries / explicit local policy.

Native DOCX/PDF text is preserved as evidence and used by the internal fallback.
Pinned chat models are never production DOCX authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import cv_extraction as cv
from cv_extraction_v2_internal import INTERNAL_EXTRACTOR_VERSION, extract_internal_v2
from cv_extraction_v2_schema import (
    CV_EXTRACTION_V2_CONTRACT,
    CV_EXTRACTION_V2_EXTRACTOR,
    CV_PROFILE_FACTS_V2_SCHEMA,
    DOCUMENT_ANNOTATION_PROMPT,
    cv_extraction_v2_json_schema,
    document_annotation_format,
)

# Pinned OCR model (never mistral-ocr-latest).
MISTRAL_OCR_MODEL_PIN = cv.MISTRAL_OCR_MODEL  # mistral-ocr-4-0
# Optional Mistral chat fallback only — version-pinned, never *-latest.
MISTRAL_ANNOTATION_CHAT_MODEL = (
    (os.environ.get("WATHEFNI_CV_V2_CHAT_FALLBACK_MODEL") or "").strip()
    or "mistral-small-2506"
)
MISTRAL_CHAT_MAX_TOKENS = 8192
MISTRAL_CHAT_COST_USD_PER_1K_INPUT = 0.0001
MISTRAL_CHAT_COST_USD_PER_1K_OUTPUT = 0.0003
MISTRAL_MAX_RETRIES = max(1, int(os.environ.get("WATHEFNI_CV_V2_MISTRAL_RETRIES") or "2"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_cv_extraction_v2 (
  extraction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_id text NOT NULL,
  evidence_id uuid,
  source_content_sha256 text NOT NULL,
  extracted_text_hash text NOT NULL,
  extraction_hash text NOT NULL,
  contract_version text NOT NULL DEFAULT 'cv-extraction-v2',
  extractor_version text NOT NULL,
  status text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_provider_response jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  estimated_cost_usd numeric(12,6),
  is_current boolean NOT NULL DEFAULT true,
  published_to_profile boolean NOT NULL DEFAULT false,
  materialized_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, app_key, document_id, source_content_sha256, contract_version, extractor_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_extraction_v2_current
  ON application_cv_extraction_v2(company_code, app_key)
  WHERE is_current=true;

CREATE INDEX IF NOT EXISTS idx_cv_extraction_v2_doc
  ON application_cv_extraction_v2(company_code, document_id, updated_at DESC);
"""

_EMPTY_LIST_FIELDS = (
    "employment",
    "volunteer_work",
    "education",
    "skills",
    "languages",
    "projects",
    "publications",
    "certifications",
    "training_courses",
    "memberships_activities",
    "awards_honors",
    "references",
    "unmodeled_sections",
)


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def v2_enabled() -> bool:
    return cv.env_flag("WATHEFNI_CV_EXTRACTION_V2", default=True)


def profile_facts_v2_published() -> bool:
    """When true, person-profile prefers V2 canonical projection."""
    return cv.env_flag("WATHEFNI_CV_PROFILE_FACTS_V2", default=False)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def extraction_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def empty_payload() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": CV_EXTRACTION_V2_CONTRACT,
        "professional_summary": None,
        "contact_details": {},
        "availability": None,
    }
    for key in _EMPTY_LIST_FIELDS:
        body[key] = []
    return body


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("name", "title", "language", "value", "label", "role", "degree"):
            found = value.get(key)
            if isinstance(found, (str, int, float)) and str(found).strip():
                return str(found).strip()
    return ""


def normalize_payload(raw: Any) -> dict[str, Any]:
    """Coerce provider output into a complete V2 payload without dropping lists."""
    src = raw if isinstance(raw, dict) else {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                src = parsed
        except Exception:
            src = {}
    out = empty_payload()
    out["professional_summary"] = _text(src.get("professional_summary")) or None
    out["availability"] = _text(src.get("availability")) or None
    contacts = _as_dict(src.get("contact_details"))
    out["contact_details"] = {
        "full_name": _text(contacts.get("full_name")) or None,
        "email": _text(contacts.get("email")) or None,
        "phone": _text(contacts.get("phone")) or None,
        "location": _text(contacts.get("location")) or None,
        "links": [str(x).strip() for x in _as_list(contacts.get("links")) if str(x).strip()],
    }
    for key in _EMPTY_LIST_FIELDS:
        items = []
        for item in _as_list(src.get(key)):
            if isinstance(item, dict):
                items.append(item)
            elif str(item or "").strip():
                items.append({"name": str(item).strip()} if key != "unmodeled_sections" else {"content": str(item).strip()})
        out[key] = items
    out["schema_version"] = CV_EXTRACTION_V2_CONTRACT
    return out


def validate_v2_payload(
    payload: dict[str, Any],
    *,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Non-destructive validation. Never deletes content; may move uncertain items."""
    warnings: list[dict[str, Any]] = []
    body = normalize_payload(payload)
    text = str(source_text or "")

    # Detect skills contamination and move to unmodeled.
    clean_skills: list[dict[str, Any]] = []
    for item in body.get("skills") or []:
        name = _text(item.get("name") if isinstance(item, dict) else item)
        if not name:
            continue
        if re.search(
            r"publication|report|reference|@|online course|languages?\s*:|selected publications|dr\.|http",
            name,
            re.I,
        ):
            body["unmodeled_sections"].append(
                {
                    "original_heading": "skills_contamination",
                    "items": [name],
                    "content": name,
                    "language": None,
                    "document_order": None,
                    "reason": "likely_misclassified_skill",
                    "source_evidence": (item.get("source_evidence") if isinstance(item, dict) else None),
                }
            )
            warnings.append({"code": "skill_contamination_moved", "value": name[:180]})
            continue
        clean_skills.append(item if isinstance(item, dict) else {"name": name})
    body["skills"] = clean_skills

    # Languages present in text but missing from extraction.
    if text and not body.get("languages"):
        match = re.search(r"languages?\s*:\s*([^\n]+)", text, re.I)
        if match:
            langs = [p.strip(" .;") for p in re.split(r"[,/|]| and ", match.group(1)) if p.strip(" .;")]
            if langs:
                body["languages"] = [{"language": lang, "proficiency": None} for lang in langs]
                warnings.append({"code": "languages_recovered_from_text", "count": len(langs)})

    # Move course/bootcamp rows out of education into training_courses (non-destructive).
    clean_education: list[dict[str, Any]] = []
    for item in body.get("education") or []:
        if not isinstance(item, dict):
            continue
        degree = _text(item.get("degree"))
        institution = _text(item.get("institution"))
        blob = f"{degree} {institution}"
        if re.search(r"\b(bootcamp|online course|short course|workshop|training program)\b", blob, re.I):
            body.setdefault("training_courses", []).append(
                {
                    "name": degree or institution,
                    "provider": institution if degree else None,
                    "date": _text(item.get("end_date") or item.get("start_date")) or None,
                    "status": None,
                    "description": None,
                    "location": _text(item.get("location")) or None,
                    "source_evidence": item.get("source_evidence"),
                }
            )
            warnings.append({"code": "education_course_moved_to_training", "value": degree[:180]})
            continue
        clean_education.append(item)
    body["education"] = clean_education

    # Integrity: empty extraction is a hard failure for publication.
    non_empty = any(
        body.get(key)
        for key in (
            "professional_summary",
            "employment",
            "education",
            "skills",
            "languages",
            "projects",
            "publications",
            "certifications",
            "training_courses",
            "memberships_activities",
            "awards_honors",
            "volunteer_work",
            "unmodeled_sections",
        )
    )
    blocking: list[str] = []
    if not non_empty:
        blocking.append("empty_extraction")

    return {
        "ok": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "payload": body,
        "stats": {
            "employment": len(body.get("employment") or []),
            "volunteer_work": len(body.get("volunteer_work") or []),
            "education": len(body.get("education") or []),
            "skills": len(body.get("skills") or []),
            "languages": len(body.get("languages") or []),
            "projects": len(body.get("projects") or []),
            "publications": len(body.get("publications") or []),
            "certifications": len(body.get("certifications") or []),
            "training_courses": len(body.get("training_courses") or []),
            "memberships_activities": len(body.get("memberships_activities") or []),
            "awards_honors": len(body.get("awards_honors") or []),
            "unmodeled_sections": len(body.get("unmodeled_sections") or []),
        },
    }


def force_internal_policy() -> bool:
    return cv.env_flag("WATHEFNI_CV_V2_FORCE_INTERNAL", default=False)


def chat_fallback_enabled() -> bool:
    """Optional pinned-chat intermediate; default OFF. Never DOCX authority."""
    return cv.env_flag("WATHEFNI_CV_V2_CHAT_FALLBACK", default=False)


def _is_mistral_unavailable_error(error: str | None) -> bool:
    if not error:
        return False
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "missing_mistral_api_key",
            "http_429",
            "http_500",
            "http_502",
            "http_503",
            "http_504",
            "timeout",
            "timed out",
            "urlerror",
            "connection",
            "temporarily",
            "rate",
        )
    )


def mistral_ocr_with_annotation(
    *,
    document_payload: dict[str, Any],
    pages: list[int] | None = None,
) -> tuple[dict[str, Any], cv.EngineCallMeta]:
    """OCR + Document AI structured annotation in one mistral-ocr-4-0 call."""
    api_key = cv.mistral_api_key()
    if not api_key:
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="missing_mistral_api_key",
            retention="none_sent",
        )
        return {}, meta

    body: dict[str, Any] = {
        "model": MISTRAL_OCR_MODEL_PIN,
        "document": document_payload,
        "include_image_base64": False,
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
        "document_annotation_format": document_annotation_format(),
        "document_annotation_prompt": DOCUMENT_ANNOTATION_PROMPT,
    }
    # DOCX/PPTX: Mistral requires image_limit=0 when not returning image base64.
    doc_url = ""
    if isinstance(document_payload, dict):
        doc_url = str(document_payload.get("document_url") or "")
    if "wordprocessingml" in doc_url or "msword" in doc_url or doc_url.lower().endswith(".docx"):
        body["image_limit"] = 0
    if pages is not None:
        body["pages"] = pages

    started = time.perf_counter()
    req = urllib_request.Request(
        "https://api.mistral.ai/v1/ocr",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            request_id = (
                cv._response_header(resp.headers, "x-request-id")
                or cv._response_header(resp.headers, "x-mistral-request-id")
            )
            parsed = json.loads(raw) if raw else {}
    except urllib_error.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(exc)
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            latency_ms=latency_ms,
            pages=list(pages or []),
            error=f"http_{getattr(exc, 'code', 'error')}:{detail[:200]}",
            retention="base64_direct_no_files_api",
        )
        return {}, meta
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        err = type(exc).__name__
        if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
            err = f"timeout:{err}"
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            latency_ms=latency_ms,
            pages=list(pages or []),
            error=err,
            retention="base64_direct_no_files_api",
        )
        return {}, meta

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = parsed.get("usage_info") if isinstance(parsed.get("usage_info"), dict) else {}
    pages_processed = int(usage.get("pages_processed") or len(parsed.get("pages") or []) or 0)
    meta = cv.EngineCallMeta(
        stage="document_annotation",
        tier="mistral_document_ai",
        provider="mistral",
        actual_request_model=MISTRAL_OCR_MODEL_PIN,
        provider_response_model=str(parsed.get("model") or MISTRAL_OCR_MODEL_PIN),
        provider_request_id=request_id,
        latency_ms=latency_ms,
        billable_pages=pages_processed,
        estimated_cost_usd=cv.estimate_mistral_cost(pages_processed),
        pages=list(pages or []),
        retention="base64_direct_no_files_api",
    )
    return parsed if isinstance(parsed, dict) else {}, meta


def mistral_chat_structured_extraction(
    *,
    document_text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], cv.EngineCallMeta]:
    """Text/DOCX path: same V2 contract via Mistral chat JSON schema."""
    api_key = cv.mistral_api_key()
    if not api_key:
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai_chat",
            provider="mistral",
            actual_request_model=MISTRAL_ANNOTATION_CHAT_MODEL,
            error="missing_mistral_api_key",
            retention="none_sent",
        )
        return {}, meta

    # Cap prompt size for cost/latency while preserving reading order.
    text = str(document_text or "")[:24000]
    block_hint = ""
    if blocks:
        sample = []
        for item in blocks[:40]:
            if not isinstance(item, dict):
                continue
            sample.append(
                {
                    "type": item.get("type") or item.get("label"),
                    "page": item.get("page"),
                    "text": str(item.get("text") or item.get("content") or "")[:180],
                }
            )
        if sample:
            block_hint = "\n\nReading-order blocks (partial):\n" + json.dumps(sample, ensure_ascii=False)

    body = {
        "model": MISTRAL_ANNOTATION_CHAT_MODEL,
        "temperature": 0,
        "max_tokens": MISTRAL_CHAT_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": DOCUMENT_ANNOTATION_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extract this CV into cv-extraction-v2 JSON.\n\n"
                    f"CV TEXT:\n{text}{block_hint}"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "cv-extraction-v2",
                "schema": cv_extraction_v2_json_schema(),
                "strict": True,
            },
        },
    }
    started = time.perf_counter()
    req = urllib_request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            request_id = cv._response_header(resp.headers, "x-request-id")
            parsed = json.loads(raw) if raw else {}
    except urllib_error.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(exc)
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai_chat",
            provider="mistral",
            actual_request_model=MISTRAL_ANNOTATION_CHAT_MODEL,
            latency_ms=latency_ms,
            error=f"http_{getattr(exc, 'code', 'error')}:{detail[:200]}",
            retention="prompt_text_only",
        )
        return {}, meta
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        meta = cv.EngineCallMeta(
            stage="document_annotation",
            tier="mistral_document_ai_chat",
            provider="mistral",
            actual_request_model=MISTRAL_ANNOTATION_CHAT_MODEL,
            latency_ms=latency_ms,
            error=type(exc).__name__,
            retention="prompt_text_only",
        )
        return {}, meta

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cost = round(
        (prompt_tokens / 1000.0) * MISTRAL_CHAT_COST_USD_PER_1K_INPUT
        + (completion_tokens / 1000.0) * MISTRAL_CHAT_COST_USD_PER_1K_OUTPUT,
        6,
    )
    content = ""
    try:
        content = parsed["choices"][0]["message"]["content"]
    except Exception:
        content = ""
    annotation: dict[str, Any] = {}
    if isinstance(content, str) and content.strip():
        annotation = _try_parse_json_object(content)
    elif isinstance(content, dict):
        annotation = content

    meta = cv.EngineCallMeta(
        stage="document_annotation",
        tier="mistral_document_ai_chat",
        provider="mistral",
        actual_request_model=MISTRAL_ANNOTATION_CHAT_MODEL,
        provider_response_model=str(parsed.get("model") or MISTRAL_ANNOTATION_CHAT_MODEL),
        provider_request_id=request_id,
        latency_ms=latency_ms,
        estimated_cost_usd=cost,
        retention="prompt_text_only",
    )
    return {"document_annotation": annotation, "usage": usage, "raw_chat": parsed}, meta


def _is_docx(mime_type: str | None, suffix: str) -> bool:
    mime = (mime_type or "").lower()
    return suffix in {".docx", ".doc"} or "wordprocessingml" in mime or mime in {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


def _is_pdf_or_image(mime_type: str | None, suffix: str) -> bool:
    mime = (mime_type or "").lower()
    if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}:
        return True
    if mime == "application/pdf" or suffix == ".pdf":
        return True
    return False


def _supports_document_ai(mime_type: str | None, suffix: str) -> bool:
    return _is_pdf_or_image(mime_type, suffix) or _is_docx(mime_type, suffix)


def _file_document_payload(path: Path, mime_type: str | None) -> dict[str, Any] | None:
    try:
        data = path.read_bytes()
    except Exception:
        return None
    import base64

    b64 = base64.b64encode(data).decode("ascii")
    mime = (mime_type or "").lower()
    suffix = path.suffix.lower()
    if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return {"type": "image_url", "image_url": f"data:{mime or 'image/png'};base64,{b64}"}
    if mime == "application/pdf" or suffix == ".pdf":
        return {"type": "document_url", "document_url": f"data:application/pdf;base64,{b64}"}
    # DOCX / DOC — Mistral Document AI accepts document_url for docx.
    if _is_docx(mime_type, suffix):
        doc_mime = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if suffix != ".doc"
            else "application/msword"
        )
        if "wordprocessingml" in mime or mime == "application/msword":
            doc_mime = mime
        return {"type": "document_url", "document_url": f"data:{doc_mime};base64,{b64}"}
    return None


def _try_parse_json_object(raw: str) -> dict[str, Any]:
    """Parse JSON object; best-effort repair for truncated provider output."""
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    # Truncation repair: cut to last complete top-level object boundary if possible.
    start = text.find("{")
    if start < 0:
        return {"raw_content": text[:8000], "parse_error": "no_object"}
    snippet = text[start:]
    # Drop trailing whitespace/noise then close open braces/brackets.
    snippet = snippet.rstrip()
    # Remove trailing incomplete string fragment after last quote pair when obvious.
    if snippet.count('"') % 2 == 1:
        snippet = snippet.rsplit('"', 1)[0]
    open_curly = snippet.count("{") - snippet.count("}")
    open_square = snippet.count("[") - snippet.count("]")
    # Trim to last comma or closing value to reduce mid-token garbage.
    for stop in (snippet.rfind("}"), snippet.rfind("]"), snippet.rfind('"')):
        if stop > 0:
            candidate = snippet[: stop + 1]
            break
    else:
        candidate = snippet
    open_curly = candidate.count("{") - candidate.count("}")
    open_square = candidate.count("[") - candidate.count("]")
    candidate = candidate + ("]" * max(0, open_square)) + ("}" * max(0, open_curly))
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            parsed["_repaired_truncated_json"] = True
            return parsed
    except Exception:
        pass
    return {"raw_content": text[:8000], "parse_error": "truncated_json"}


def extract_annotation_object(provider_response: dict[str, Any]) -> Any:
    if not isinstance(provider_response, dict):
        return {}
    annotation = provider_response.get("document_annotation")
    if isinstance(annotation, str):
        return _try_parse_json_object(annotation)
    if isinstance(annotation, dict):
        if annotation.get("parse_error") or annotation.get("raw_content"):
            # Prefer full chat message content when annotation wrapper only kept a stub.
            try:
                content = (
                    provider_response.get("raw_chat", {})
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content")
                )
                if isinstance(content, str) and len(content) > len(str(annotation.get("raw_content") or "")):
                    repaired = _try_parse_json_object(content)
                    if repaired and not repaired.get("parse_error"):
                        return repaired
            except Exception:
                pass
        return annotation
    # Chat responses sometimes only keep raw_chat.
    try:
        content = (
            provider_response.get("raw_chat", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if isinstance(content, str) and content.strip():
            return _try_parse_json_object(content)
        if isinstance(content, dict):
            return content
    except Exception:
        pass
    return {}


def _meta_dict(meta: Any) -> dict[str, Any]:
    if hasattr(meta, "to_dict"):
        return meta.to_dict()
    return {
        "error": getattr(meta, "error", None),
        "actual_request_model": getattr(meta, "actual_request_model", None),
        "estimated_cost_usd": getattr(meta, "estimated_cost_usd", None),
        "latency_ms": getattr(meta, "latency_ms", None),
        "billable_pages": getattr(meta, "billable_pages", None),
        "tier": getattr(meta, "tier", None),
        "provider": getattr(meta, "provider", None),
    }


def _ocr_pages_text(provider_response: dict[str, Any]) -> str:
    pages = provider_response.get("pages") if isinstance(provider_response, dict) else None
    if not isinstance(pages, list):
        return ""
    chunks = []
    for page in pages:
        if isinstance(page, dict) and page.get("markdown"):
            chunks.append(str(page.get("markdown")))
    return "\n\n".join(chunks).strip()


def _run_internal_fallback(
    *,
    extracted_text: str,
    blocks: list[dict[str, Any]] | None,
    reason: str,
    prior_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    annotation = extract_internal_v2(extracted_text=extracted_text, blocks=blocks)
    validated = validate_v2_payload(annotation, source_text=extracted_text)
    return {
        "ok": bool(validated.get("ok")),
        "path": "wathefni_internal_fallback",
        "payload": validated.get("payload") or empty_payload(),
        "validation": validated,
        "raw_provider_response": {
            "provider": "wathefni_internal",
            "extractor_version": INTERNAL_EXTRACTOR_VERSION,
            "fallback_reason": reason,
            "document_annotation": annotation,
        },
        "meta": {
            "provider": "wathefni_internal",
            "tier": "internal_v2",
            "actual_request_model": INTERNAL_EXTRACTOR_VERSION,
            "estimated_cost_usd": 0.0,
            "error": None,
            "fallback_reason": reason,
        },
        "extractor_version": INTERNAL_EXTRACTOR_VERSION,
        "attempts": prior_attempts
        + [
            {
                "provider": "wathefni_internal",
                "path": "wathefni_internal_fallback",
                "reason": reason,
                "ok": bool(validated.get("ok")),
            }
        ],
        "ocr_text_chars": 0,
    }


def run_v2_extraction(
    *,
    local_path: str | Path | None,
    mime_type: str | None,
    extracted_text: str,
    blocks: list[dict[str, Any]] | None = None,
    force_ocr_annotation: bool = False,
    prefer_reuse_text: bool = False,
    force_internal: bool | None = None,
) -> dict[str, Any]:
    """Primary: Mistral OCR 4 + Document AI for PDF/image/DOCX. Fallback: internal V2.

    prefer_reuse_text is retained for evidence comparison only — it does not make
    chat/native text the DOCX authority.
    force_ocr_annotation kept for explicit OCR re-runs.
    Never uses GPT Vision.
    """
    _ = prefer_reuse_text  # native text remains evidence / internal input only
    path = Path(local_path) if local_path else None
    suffix = path.suffix.lower() if path else ""
    text_ok = bool(extracted_text and cv.cv_text_quality_ok(extracted_text) and len(extracted_text) >= 80)
    attempts: list[dict[str, Any]] = []

    if force_internal is None:
        force_internal = force_internal_policy()

    if force_internal:
        return _run_internal_fallback(
            extracted_text=extracted_text,
            blocks=blocks,
            reason="explicit_local_processing_policy",
            prior_attempts=attempts,
        )

    document_payload = None
    if path and path.is_file() and _supports_document_ai(mime_type, suffix):
        document_payload = _file_document_payload(path, mime_type)

    provider_response: dict[str, Any] = {}
    meta: cv.EngineCallMeta | None = None
    path_used = "ocr_document_annotation"
    mistral_error: str | None = None

    if document_payload:
        last_meta = None
        for attempt_idx in range(MISTRAL_MAX_RETRIES):
            provider_response, meta = mistral_ocr_with_annotation(document_payload=document_payload)
            last_meta = meta
            err = getattr(meta, "error", None)
            attempts.append(
                {
                    "provider": "mistral",
                    "path": "ocr_document_annotation",
                    "attempt": attempt_idx + 1,
                    "model": MISTRAL_OCR_MODEL_PIN,
                    "error": err,
                    "ok": not err,
                }
            )
            if not err:
                mistral_error = None
                break
            mistral_error = str(err)
            if not _is_mistral_unavailable_error(err) and attempt_idx + 1 >= MISTRAL_MAX_RETRIES:
                break
            if attempt_idx + 1 < MISTRAL_MAX_RETRIES and _is_mistral_unavailable_error(err):
                time.sleep(min(2 ** attempt_idx, 4))
                continue
            break
        meta = last_meta
        path_used = "ocr_document_annotation"
    else:
        # No file bytes — cannot call Document AI; use internal on text evidence.
        return _run_internal_fallback(
            extracted_text=extracted_text,
            blocks=blocks,
            reason="no_document_bytes_for_mistral_ocr",
            prior_attempts=attempts,
        )

    # Optional pinned-chat intermediate (never DOCX authority; default OFF).
    if getattr(meta, "error", None) and chat_fallback_enabled() and text_ok:
        provider_response, meta = mistral_chat_structured_extraction(
            document_text=extracted_text, blocks=blocks
        )
        path_used = "pinned_chat_after_ocr_error"
        attempts.append(
            {
                "provider": "mistral",
                "path": path_used,
                "model": MISTRAL_ANNOTATION_CHAT_MODEL,
                "error": getattr(meta, "error", None),
                "ok": not getattr(meta, "error", None),
            }
        )
        mistral_error = getattr(meta, "error", None)

    # Route to internal when Mistral unavailable / retries exhausted / rate-limited.
    if getattr(meta, "error", None) and (
        _is_mistral_unavailable_error(getattr(meta, "error", None))
        or mistral_error
    ):
        internal = _run_internal_fallback(
            extracted_text=extracted_text,
            blocks=blocks,
            reason=f"mistral_unavailable:{getattr(meta, 'error', None)}",
            prior_attempts=attempts,
        )
        # Preserve failed Mistral response alongside internal authority.
        internal["raw_provider_response"] = {
            **(internal.get("raw_provider_response") or {}),
            "mistral_attempt": provider_response,
            "mistral_meta": _meta_dict(meta),
        }
        internal["secondary_result"] = {
            "provider": "mistral",
            "path": path_used,
            "error": getattr(meta, "error", None),
            "raw_provider_response": provider_response,
            "meta": _meta_dict(meta),
            "extractor_version": CV_EXTRACTION_V2_EXTRACTOR,
        }
        return internal

    ocr_text = _ocr_pages_text(provider_response)
    source_for_validation = ocr_text or extracted_text
    annotation = extract_annotation_object(provider_response)
    validated = validate_v2_payload(annotation, source_text=source_for_validation)
    meta_dict = _meta_dict(meta)
    if path_used.startswith("ocr_document_annotation") and meta_dict.get("billable_pages"):
        pages_n = int(meta_dict["billable_pages"] or 0)
        meta_dict["estimated_cost_usd"] = round(pages_n * 0.005, 6)

    # Weak annotation with usable native text → keep Mistral OCR text but do not
    # silently invent; validation may recover languages. Internal is not used to
    # overwrite stronger Mistral facts when OCR succeeded.
    return {
        "ok": bool(validated.get("ok")) and not meta_dict.get("error"),
        "path": path_used,
        "payload": validated.get("payload") or empty_payload(),
        "validation": validated,
        "raw_provider_response": provider_response,
        "meta": meta_dict,
        "extractor_version": CV_EXTRACTION_V2_EXTRACTOR,
        "attempts": attempts,
        "ocr_text_chars": len(ocr_text),
        "native_text_preserved": bool(extracted_text),
        "force_ocr_annotation": bool(force_ocr_annotation),
    }


def project_profile_facts_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Project V2 structured extraction into candidate-profile-facts-v2 clean contract."""
    body = normalize_payload(payload)

    def skill_names() -> list[str]:
        out = []
        for item in body.get("skills") or []:
            name = _text(item.get("name") if isinstance(item, dict) else item)
            if name:
                out.append(name)
        return out

    def language_names() -> list[str]:
        out = []
        for item in body.get("languages") or []:
            if isinstance(item, dict):
                lang = _text(item.get("language"))
                prof = _text(item.get("proficiency"))
                out.append(f"{lang} ({prof})" if lang and prof else lang)
            else:
                text = _text(item)
                if text:
                    out.append(text)
        return [x for x in out if x]

    def employment_lines() -> list[str]:
        out = []
        for item in body.get("employment") or []:
            if not isinstance(item, dict):
                continue
            title = _text(item.get("title"))
            company = _text(item.get("company"))
            when = " – ".join(p for p in (_text(item.get("start_date")), _text(item.get("end_date"))) if p)
            line = " · ".join(p for p in (title, company, when) if p)
            if line:
                out.append(line)
        return out

    def education_lines() -> list[str]:
        out = []
        for item in body.get("education") or []:
            if not isinstance(item, dict):
                continue
            degree = _text(item.get("degree"))
            institution = _text(item.get("institution"))
            loc = _text(item.get("location"))
            gpa = _text(item.get("gpa"))
            honors = _text(item.get("honors"))
            when = " – ".join(p for p in (_text(item.get("start_date")), _text(item.get("end_date"))) if p)
            parts = [p for p in (degree, institution, loc, when, f"GPA: {gpa}" if gpa else "", honors) if p]
            if parts:
                out.append(" · ".join(parts))
        return out

    contacts = body.get("contact_details") or {}
    expertise = None
    for item in body.get("education") or []:
        if isinstance(item, dict) and _text(item.get("degree")):
            expertise = _text(item.get("degree"))
            break
    if not expertise and skill_names():
        expertise = skill_names()[0]

    return {
        "schema": CV_PROFILE_FACTS_V2_SCHEMA,
        "skills": skill_names(),
        "education": education_lines(),
        "employment": employment_lines(),
        "languages": language_names(),
        "certifications": [
            " · ".join(
                p
                for p in (
                    _text(i.get("name")),
                    _text(i.get("issuer")),
                    _text(i.get("date")),
                )
                if p
            )
            for i in body.get("certifications") or []
            if isinstance(i, dict)
        ],
        "projects": [
            " · ".join(p for p in (_text(i.get("name")), _text(i.get("description"))[:120]) if p)
            for i in body.get("projects") or []
            if isinstance(i, dict)
        ],
        "publications": [
            " · ".join(p for p in (_text(i.get("title")), _text(i.get("venue")), _text(i.get("date"))) if p)
            for i in body.get("publications") or []
            if isinstance(i, dict)
        ],
        "training_courses": [
            " · ".join(p for p in (_text(i.get("name")), _text(i.get("provider")), _text(i.get("date"))) if p)
            for i in body.get("training_courses") or []
            if isinstance(i, dict)
        ],
        "memberships_activities": [
            " · ".join(p for p in (_text(i.get("name")), _text(i.get("organization")), _text(i.get("role"))) if p)
            for i in body.get("memberships_activities") or []
            if isinstance(i, dict)
        ],
        "awards_honors": [
            " · ".join(
                p
                for p in (
                    _text(i.get("title")),
                    _text(i.get("issuing_organization")),
                    _text(i.get("date")),
                )
                if p
            )
            for i in body.get("awards_honors") or []
            if isinstance(i, dict)
        ],
        "volunteer_work": [
            " · ".join(p for p in (_text(i.get("role")), _text(i.get("organization"))) if p)
            for i in body.get("volunteer_work") or []
            if isinstance(i, dict)
        ],
        "references": [
            " · ".join(p for p in (_text(i.get("name")), _text(i.get("organization")), _text(i.get("email"))) if p)
            for i in body.get("references") or []
            if isinstance(i, dict)
        ],
        "location": _text(contacts.get("location")) or None,
        "professional_summary": body.get("professional_summary"),
        "primary_expertise": expertise,
        "experience_years": None,
        "availability": body.get("availability"),
        "unmodeled_sections": body.get("unmodeled_sections") or [],
        "structured": {
            "employment": body.get("employment") or [],
            "volunteer_work": body.get("volunteer_work") or [],
            "education": body.get("education") or [],
            "skills": body.get("skills") or [],
            "languages": body.get("languages") or [],
            "projects": body.get("projects") or [],
            "publications": body.get("publications") or [],
            "certifications": body.get("certifications") or [],
            "training_courses": body.get("training_courses") or [],
            "memberships_activities": body.get("memberships_activities") or [],
            "awards_honors": body.get("awards_honors") or [],
            "references": body.get("references") or [],
            "contact_details": contacts,
        },
        "field_sources": {
            "skills": {"origin": "extracted_v2"},
            "education": {"origin": "extracted_v2"},
            "employment": {"origin": "extracted_v2"},
            "languages": {"origin": "extracted_v2"},
            "professional_summary": {"origin": "extracted_v2"},
            "primary_expertise": {"origin": "derived" if expertise else "missing"},
            "location": {"origin": "extracted_v2" if contacts.get("location") else "missing"},
        },
    }


def materialize_v2(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str,
    evidence_id: str | None,
    source_content_sha256: str,
    extracted_text_hash: str,
    run_result: dict[str, Any],
    publish_to_profile: bool = False,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    document = str(document_id or "").strip()
    source_hash = str(source_content_sha256 or "").strip().lower() or "unknown"
    text_hash = str(extracted_text_hash or "").strip().lower() or "unknown"
    payload = run_result.get("payload") if isinstance(run_result.get("payload"), dict) else empty_payload()
    validation = run_result.get("validation") if isinstance(run_result.get("validation"), dict) else {}
    raw = run_result.get("raw_provider_response") if isinstance(run_result.get("raw_provider_response"), dict) else {}
    meta = run_result.get("meta") if isinstance(run_result.get("meta"), dict) else {}
    extractor_version = str(
        run_result.get("extractor_version") or CV_EXTRACTION_V2_EXTRACTOR
    ).strip() or CV_EXTRACTION_V2_EXTRACTOR
    digest = extraction_hash(payload)
    status = "ready" if validation.get("ok") else "review"
    if validation.get("blocking"):
        status = "failed"

    provenance = {
        "path": run_result.get("path"),
        "meta": meta,
        "attempts": run_result.get("attempts") or [],
        "native_text_preserved": run_result.get("native_text_preserved"),
        "authority": extractor_version,
    }

    # Never silently overwrite a stronger Mistral current row with internal fallback
    # unless this run is explicitly the authority (Mistral failed) or force policy.
    if extractor_version == INTERNAL_EXTRACTOR_VERSION:
        cur.execute(
            """
            SELECT extractor_version, status FROM application_cv_extraction_v2
            WHERE company_code=%s AND app_key=%s AND is_current=true
            LIMIT 1
            """,
            (company, application),
        )
        current = cur.fetchone()
        if (
            current
            and str(current.get("extractor_version") or "") == CV_EXTRACTION_V2_EXTRACTOR
            and str(current.get("status") or "") == "ready"
            and not force_internal_policy()
        ):
            # Preserve internal as non-current evidence only.
            cur.execute(
                """
                INSERT INTO application_cv_extraction_v2(
                  extraction_id, company_code, app_key, document_id, evidence_id,
                  source_content_sha256, extracted_text_hash, extraction_hash,
                  contract_version, extractor_version, status, payload,
                  raw_provider_response, validation, provenance, estimated_cost_usd,
                  is_current, published_to_profile, materialized_at, created_at, updated_at
                ) VALUES (
                  %s::uuid,%s,%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,
                  false,false,now(),now(),now()
                )
                ON CONFLICT (
                  company_code, app_key, document_id, source_content_sha256,
                  contract_version, extractor_version
                ) DO UPDATE SET
                  payload=EXCLUDED.payload,
                  raw_provider_response=EXCLUDED.raw_provider_response,
                  validation=EXCLUDED.validation,
                  provenance=EXCLUDED.provenance,
                  status=EXCLUDED.status,
                  estimated_cost_usd=EXCLUDED.estimated_cost_usd,
                  is_current=false,
                  updated_at=now()
                RETURNING *
                """,
                (
                    str(uuid.uuid4()),
                    company,
                    application,
                    document,
                    evidence_id,
                    source_hash,
                    text_hash,
                    digest,
                    CV_EXTRACTION_V2_CONTRACT,
                    extractor_version,
                    status,
                    _stable_json(payload),
                    _stable_json(raw),
                    _stable_json(validation),
                    _stable_json({**provenance, "not_promoted": "stronger_mistral_current"}),
                    meta.get("estimated_cost_usd"),
                ),
            )
            return dict(cur.fetchone() or {})

    cur.execute(
        """
        UPDATE application_cv_extraction_v2
        SET is_current=false, superseded_at=now(), updated_at=now()
        WHERE company_code=%s AND app_key=%s AND is_current=true
          AND NOT (
            document_id=%s AND source_content_sha256=%s
            AND contract_version=%s AND extractor_version=%s
          )
        """,
        (company, application, document, source_hash, CV_EXTRACTION_V2_CONTRACT, extractor_version),
    )
    extraction_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO application_cv_extraction_v2(
          extraction_id, company_code, app_key, document_id, evidence_id,
          source_content_sha256, extracted_text_hash, extraction_hash,
          contract_version, extractor_version, status, payload,
          raw_provider_response, validation, provenance, estimated_cost_usd,
          is_current, published_to_profile, materialized_at, created_at, updated_at
        ) VALUES (
          %s::uuid,%s,%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,
          true,%s,now(),now(),now()
        )
        ON CONFLICT (
          company_code, app_key, document_id, source_content_sha256,
          contract_version, extractor_version
        ) DO UPDATE SET
          evidence_id=EXCLUDED.evidence_id,
          extracted_text_hash=EXCLUDED.extracted_text_hash,
          extraction_hash=EXCLUDED.extraction_hash,
          status=EXCLUDED.status,
          payload=EXCLUDED.payload,
          raw_provider_response=EXCLUDED.raw_provider_response,
          validation=EXCLUDED.validation,
          provenance=EXCLUDED.provenance,
          estimated_cost_usd=EXCLUDED.estimated_cost_usd,
          is_current=true,
          published_to_profile=EXCLUDED.published_to_profile,
          materialized_at=now(),
          superseded_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            extraction_id,
            company,
            application,
            document,
            evidence_id,
            source_hash,
            text_hash,
            digest,
            CV_EXTRACTION_V2_CONTRACT,
            extractor_version,
            status,
            _stable_json(payload),
            _stable_json(raw),
            _stable_json(validation),
            _stable_json(provenance),
            meta.get("estimated_cost_usd"),
            bool(publish_to_profile and status == "ready"),
        ),
    )
    row = dict(cur.fetchone() or {})

    # Persist secondary provider attempt without making it current.
    secondary = run_result.get("secondary_result") if isinstance(run_result.get("secondary_result"), dict) else None
    if secondary and secondary.get("extractor_version"):
        sec_payload = secondary.get("payload") if isinstance(secondary.get("payload"), dict) else empty_payload()
        sec_raw = secondary.get("raw_provider_response") if isinstance(secondary.get("raw_provider_response"), dict) else {}
        sec_meta = secondary.get("meta") if isinstance(secondary.get("meta"), dict) else {}
        sec_version = str(secondary.get("extractor_version"))
        cur.execute(
            """
            INSERT INTO application_cv_extraction_v2(
              extraction_id, company_code, app_key, document_id, evidence_id,
              source_content_sha256, extracted_text_hash, extraction_hash,
              contract_version, extractor_version, status, payload,
              raw_provider_response, validation, provenance, estimated_cost_usd,
              is_current, published_to_profile, materialized_at, created_at, updated_at
            ) VALUES (
              %s::uuid,%s,%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,
              false,false,now(),now(),now()
            )
            ON CONFLICT (
              company_code, app_key, document_id, source_content_sha256,
              contract_version, extractor_version
            ) DO UPDATE SET
              raw_provider_response=EXCLUDED.raw_provider_response,
              provenance=EXCLUDED.provenance,
              status=EXCLUDED.status,
              is_current=false,
              updated_at=now()
            """,
            (
                str(uuid.uuid4()),
                company,
                application,
                document,
                evidence_id,
                source_hash,
                text_hash,
                extraction_hash(sec_payload) if sec_payload else digest,
                CV_EXTRACTION_V2_CONTRACT,
                sec_version,
                "failed" if sec_meta.get("error") else "review",
                _stable_json(sec_payload),
                _stable_json(sec_raw),
                _stable_json({"ok": False, "warnings": [{"code": "secondary_provider_attempt"}]}),
                _stable_json({"path": secondary.get("path"), "meta": sec_meta, "role": "secondary"}),
                sec_meta.get("estimated_cost_usd"),
            ),
        )

    # Project into candidate_profile_facts when publishing.
    if publish_to_profile and status == "ready":
        try:
            import candidate_profile_facts as cpf

            profile = project_profile_facts_v2(payload)
            cur.execute(
                """
                SELECT facts_id, facts_hash FROM application_cv_fact_snapshots
                WHERE company_code=%s AND app_key=%s AND is_current=true
                LIMIT 1
                """,
                (company, application),
            )
            snap = cur.fetchone()
            facts_id = str((snap or {}).get("facts_id") or extraction_id)
            profile["source_contract_version"] = CV_EXTRACTION_V2_CONTRACT
            profile["source_facts_id"] = facts_id
            profile["source_extraction_id"] = str(row.get("extraction_id") or extraction_id)
            profile["profile_hash"] = cpf.profile_hash(profile)
            cpf.materialize_profile_facts(
                cur,
                facts_id=facts_id,
                company_code=company,
                app_key=application,
                profile=profile,
                source_facts_hash=str((snap or {}).get("facts_hash") or digest),
            )
        except Exception:
            pass
    return row


def load_current_v2(cur: Any, *, company_code: str, app_key: str) -> dict[str, Any] | None:
    ensure_schema(cur)
    cur.execute(
        """
        SELECT * FROM application_cv_extraction_v2
        WHERE company_code=%s AND app_key=%s AND is_current=true
        LIMIT 1
        """,
        (str(company_code).upper(), str(app_key)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


__all__ = [
    "CV_EXTRACTION_V2_CONTRACT",
    "CV_EXTRACTION_V2_EXTRACTOR",
    "CV_PROFILE_FACTS_V2_SCHEMA",
    "INTERNAL_EXTRACTOR_VERSION",
    "MISTRAL_ANNOTATION_CHAT_MODEL",
    "MISTRAL_OCR_MODEL_PIN",
    "ensure_schema",
    "empty_payload",
    "extract_annotation_object",
    "force_internal_policy",
    "load_current_v2",
    "materialize_v2",
    "mistral_chat_structured_extraction",
    "mistral_ocr_with_annotation",
    "normalize_payload",
    "profile_facts_v2_published",
    "project_profile_facts_v2",
    "run_v2_extraction",
    "v2_enabled",
    "validate_v2_payload",
]
