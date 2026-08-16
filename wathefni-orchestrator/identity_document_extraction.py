"""Identity Document Processing — Mistral Document AI authority module.

Wave 1 qualified the path; Wave 2 makes Mistral the authority for identity
classification, verification, and structured extraction.

Constraints honored by this module:
- Does NOT use CV Extraction V2 / Ranking / Candidate Knowledge
- Does NOT use GPT vision as automatic extraction, shadow, or fallback
- Machine fields remain non-authoritative until HR confirms
- Does NOT mutate document_processing_foundation route matrix in this module

Document types: civil_id, passport, residency, work_permit, medical
Also classifies onboarding media siblings: personal_photo, education_cert
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import cv_extraction as cv
import document_processing_foundation as dpf

IDENTITY_CONTRACT = "identity-document-extraction-v1"
IDENTITY_EXTRACTOR = "identity_mistral_document_ai"
MISTRAL_OCR_MODEL_PIN = cv.MISTRAL_OCR_MODEL  # mistral-ocr-4-0
DOCUMENT_TYPES = frozenset(
    {"civil_id", "passport", "residency", "work_permit", "medical", "unknown"}
)
IDENTITY_DOC_TYPES = frozenset(
    {"civil_id", "passport", "residency", "work_permit", "medical"}
)
ONBOARDING_MEDIA_TYPES = frozenset(
    {
        "civil_id",
        "passport",
        "medical",
        "residency",
        "work_permit",
        "personal_photo",
        "education_cert",
        "instruction_screenshot",
        "unknown",
    }
)
SIDES = frozenset({"front", "back", "single", "unknown"})

# Civil ID in Kuwait is typically 12 digits.
CIVIL_ID_RE = re.compile(r"^\d{12}$")
PASSPORT_RE = re.compile(r"^[A-Z0-9]{6,12}$", re.I)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CIRCUIT_LOCK = threading.Lock()
_CIRCUIT: dict[str, Any] = {
    "failures": 0,
    "opened_at": None,
    "open_until": 0.0,
}
_RUNTIME_LOCK = threading.Lock()
_RUNTIME: dict[str, Any] = {
    "mistral_calls": 0,
    "gpt_identity_calls": 0,  # must remain 0 under Wave 2 authority
    "needs_review": 0,
    "classify_calls": 0,
    "verify_calls": 0,
    "extract_calls": 0,
    "last_provider": None,
    "cache_hits": 0,
}
_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_S = 120.0


def identity_mistral_enabled(environ: dict[str, str] | None = None) -> bool:
    """Legacy Wave 1 qualify flag — still honored as an authority alias."""

    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_IDENTITY_MISTRAL_EXTRACT") or "off").strip().lower()
    return raw in {"1", "true", "on", "yes", "shadow", "canary", "qualify"} or identity_mistral_authority_enabled(
        environ=env
    )


def identity_mistral_authority_enabled(
    *,
    company_code: str | None = None,
    environ: dict[str, str] | None = None,
) -> bool:
    """Global identity Mistral authority contract.

    Default: ON for all tenants (current and future).
    Emergency kill switch: WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=off|kill|disabled
    Optional per-tenant disable: WATHEFNI_IDENTITY_MISTRAL_DISABLE_COMPANIES=A,B
    Legacy canary allowlist mode retained only when AUTHORITY=canary explicitly.
    Never enables a GPT fallback path.
    """

    env = environ if environ is not None else os.environ
    # Default-on when unset.
    mode = str(env.get("WATHEFNI_IDENTITY_MISTRAL_AUTHORITY") or "on").strip().lower()
    legacy = str(env.get("WATHEFNI_IDENTITY_MISTRAL_EXTRACT") or "").strip().lower()
    if mode in {"", "default"}:
        mode = "on"
    if mode in {"off", "0", "false", "no", "kill", "disabled", "emergency_stop"}:
        return False
    if mode not in {"1", "true", "on", "yes", "staging", "canary", "production", "authority", "global"}:
        if legacy in {"1", "true", "on", "yes", "canary", "qualify", "shadow"}:
            mode = "canary" if legacy == "canary" else "on"
        elif legacy in {"off", "0", "false"}:
            return False
        else:
            # Unknown value → fail closed to kill? Prefer default-on for production contract.
            mode = "on"

    company = str(company_code or "").strip().upper()
    disable_raw = str(env.get("WATHEFNI_IDENTITY_MISTRAL_DISABLE_COMPANIES") or "")
    disabled = {c.strip().upper() for c in disable_raw.split(",") if c.strip()}
    if company and company in disabled:
        return False

    # Explicit legacy canary allowlist (not the default production contract).
    if mode == "canary":
        allow_raw = str(env.get("WATHEFNI_IDENTITY_MISTRAL_COMPANIES") or "WATHEFNI")
        allow = {c.strip().upper() for c in allow_raw.split(",") if c.strip()}
        return bool(company and company in allow)

    # Global default-on / staging / production / authority / global
    return True


def gpt_auto_fallback_forbidden() -> bool:
    """Identity processing never falls back to GPT automatically."""

    return True


def runtime_counters() -> dict[str, Any]:
    with _RUNTIME_LOCK:
        return dict(_RUNTIME)


def reset_runtime_counters() -> None:
    with _RUNTIME_LOCK:
        for key in list(_RUNTIME.keys()):
            if isinstance(_RUNTIME[key], int):
                _RUNTIME[key] = 0
            else:
                _RUNTIME[key] = None
    _RESULT_CACHE.clear()


def _bump(counter: str, *, provider: str | None = None) -> None:
    with _RUNTIME_LOCK:
        _RUNTIME[counter] = int(_RUNTIME.get(counter) or 0) + 1
        if provider:
            _RUNTIME["last_provider"] = provider


def record_forbidden_gpt_identity_call(reason: str = "unexpected") -> None:
    """If any caller still invokes GPT for identity, stamp a hard counter."""

    _bump("gpt_identity_calls")
    with _RUNTIME_LOCK:
        _RUNTIME["last_gpt_reason"] = reason


def resolve_media_path(media: dict[str, Any] | None) -> Path | None:
    if not isinstance(media, dict):
        return None
    for key in ("path", "local_path", "source_path"):
        raw = str(media.get(key) or "").strip()
        if not raw or raw.startswith(("http://", "https://", "data:")):
            continue
        path = Path(raw)
        try:
            if path.exists() and path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
                return path
        except Exception:
            continue
    return None


def _circuit_max_failures() -> int:
    return max(1, int(os.environ.get("WATHEFNI_IDENTITY_MISTRAL_CIRCUIT_FAILURES") or "3"))


def _circuit_cooldown_s() -> float:
    return float(os.environ.get("WATHEFNI_IDENTITY_MISTRAL_CIRCUIT_COOLDOWN_S") or "60")


def _circuit_open() -> bool:
    with _CIRCUIT_LOCK:
        until = float(_CIRCUIT.get("open_until") or 0.0)
        return time.time() < until


def _circuit_record_success() -> None:
    with _CIRCUIT_LOCK:
        _CIRCUIT["failures"] = 0
        _CIRCUIT["opened_at"] = None
        _CIRCUIT["open_until"] = 0.0


def _circuit_record_failure() -> dict[str, Any]:
    with _CIRCUIT_LOCK:
        _CIRCUIT["failures"] = int(_CIRCUIT.get("failures") or 0) + 1
        opened = False
        if _CIRCUIT["failures"] >= _circuit_max_failures():
            _CIRCUIT["opened_at"] = time.time()
            _CIRCUIT["open_until"] = time.time() + _circuit_cooldown_s()
            opened = True
        return {
            "failures": _CIRCUIT["failures"],
            "opened": opened,
            "open_until": _CIRCUIT["open_until"],
        }


def reset_circuit_for_tests() -> None:
    with _CIRCUIT_LOCK:
        _CIRCUIT["failures"] = 0
        _CIRCUIT["opened_at"] = None
        _CIRCUIT["open_until"] = 0.0


def identity_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_type": {
                "type": "string",
                "enum": sorted(DOCUMENT_TYPES),
            },
            "side": {"type": "string", "enum": sorted(SIDES)},
            "document_relationship": {
                "type": ["string", "null"],
                "description": "e.g. civil_id_front_of, pair_with_back, standalone",
            },
            "full_name_ar": {"type": ["string", "null"]},
            "full_name_en": {"type": ["string", "null"]},
            "document_number": {"type": ["string", "null"]},
            "nationality": {"type": ["string", "null"]},
            "date_of_birth": {"type": ["string", "null"]},
            "issue_date": {"type": ["string", "null"]},
            "expiry_date": {"type": ["string", "null"]},
            "employer_or_sponsor": {"type": ["string", "null"]},
            "field_confidence": {
                "type": "object",
                "additionalProperties": {"type": "number"},
            },
            "overall_confidence": {"type": "number"},
            "unreadable_reason": {"type": ["string", "null"]},
        },
        "required": [
            "document_type",
            "side",
            "document_number",
            "full_name_ar",
            "full_name_en",
            "nationality",
            "date_of_birth",
            "issue_date",
            "expiry_date",
            "employer_or_sponsor",
            "overall_confidence",
        ],
    }


def document_annotation_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "wathefni_identity_document_v1",
            "schema": identity_json_schema(),
            "strict": True,
        },
    }


IDENTITY_ANNOTATION_PROMPT = (
    "Extract identity/compliance document fields for Kuwait HR onboarding. "
    "Supported types: civil_id, passport, residency, work_permit, medical. "
    "Return ONLY values visibly present on the document image/PDF. "
    "If a field is not clearly visible, return null — never invent values. "
    "Prefer ISO dates YYYY-MM-DD. Preserve Arabic text without transliteration loss. "
    "For Kuwait Civil ID (PACI): front is the portrait face (photo + name + civil ID number + nationality + DOB); "
    "back is the reverse (address and/or barcode/serial and/or blood type/occupation). "
    "Set side to front/back/single/unknown. If front vs back is unclear, set side=unknown — never default to front. "
    "Set document_relationship to civil_id_front_of, pair_with_front, standalone, or unknown accordingly. "
    "Include per-field confidence in field_confidence when possible."
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_iso_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw or not ISO_DATE_RE.match(raw):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _null_if_blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    return text


def _field(
    *,
    value: Any,
    confidence: float | None,
    source: str,
    page: int | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": None if confidence is None else float(confidence),
        "provenance": {
            "source": source,
            "extractor": IDENTITY_EXTRACTOR,
            "contract": IDENTITY_CONTRACT,
            "page": page,
            "authoritative": False,
            "hr_confirmed": False,
        },
    }


def validate_identity_fields(
    fields: dict[str, Any],
    *,
    expected_type: str | None = None,
) -> dict[str, Any]:
    """Deterministic safety validation only — does not invent values."""

    issues: list[str] = []
    doc_type = _null_if_blank((fields.get("document_type") or {}).get("value"))
    number = _null_if_blank((fields.get("document_number") or {}).get("value"))
    issue = _parse_iso_date((fields.get("issue_date") or {}).get("value"))
    expiry = _parse_iso_date((fields.get("expiry_date") or {}).get("value"))
    dob = _parse_iso_date((fields.get("date_of_birth") or {}).get("value"))

    for key in ("issue_date", "expiry_date", "date_of_birth"):
        raw = (fields.get(key) or {}).get("value")
        if raw is not None and _parse_iso_date(raw) is None:
            issues.append(f"invalid_date_format:{key}")

    if issue and expiry and expiry < issue:
        issues.append("expiry_before_issue")

    if dob and issue and dob > issue:
        issues.append("dob_after_issue")

    if expected_type and doc_type and doc_type not in {expected_type, "unknown"}:
        issues.append(f"type_mismatch:expected_{expected_type}_got_{doc_type}")

    if doc_type == "civil_id" and number and not CIVIL_ID_RE.match(number):
        issues.append("civil_id_format_unexpected")
    if doc_type == "passport" and number and not PASSPORT_RE.match(re.sub(r"\s+", "", number)):
        issues.append("passport_format_unexpected")

    name_ar = _null_if_blank((fields.get("full_name_ar") or {}).get("value"))
    name_en = _null_if_blank((fields.get("full_name_en") or {}).get("value"))
    if not name_ar and not name_en and doc_type in {"civil_id", "passport"}:
        issues.append("missing_name")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "has_issue_date": issue is not None,
        "has_expiry_date": expiry is not None,
        "has_dob": dob is not None,
    }


def _document_payload_for_path(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        mime = "application/pdf"
    elif suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"
    else:
        mime = "application/octet-stream"
    return {
        "type": "document_url",
        "document_url": f"data:{mime};base64,{b64}",
    }


def mistral_identity_annotation(
    *,
    path: Path,
    max_retries: int | None = None,
) -> tuple[dict[str, Any], cv.EngineCallMeta, list[dict[str, Any]]]:
    """OCR + Document AI annotation for identity docs. Never calls GPT."""

    attempts: list[dict[str, Any]] = []
    retries = max_retries if max_retries is not None else max(
        1, int(os.environ.get("WATHEFNI_IDENTITY_MISTRAL_RETRIES") or "2")
    )
    api_key = cv.mistral_api_key()
    if not api_key:
        meta = cv.EngineCallMeta(
            stage="identity_document_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="missing_mistral_api_key",
            retention="none_sent",
        )
        return {}, meta, attempts

    if _circuit_open():
        meta = cv.EngineCallMeta(
            stage="identity_document_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="circuit_open",
            retention="none_sent",
        )
        return {}, meta, attempts

    payload = _document_payload_for_path(path)
    body: dict[str, Any] = {
        "model": MISTRAL_OCR_MODEL_PIN,
        "document": payload,
        "include_image_base64": False,
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
        "document_annotation_format": document_annotation_format(),
        "document_annotation_prompt": IDENTITY_ANNOTATION_PROMPT,
    }

    last_meta: cv.EngineCallMeta | None = None
    for attempt in range(1, retries + 1):
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
            with urllib_request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                request_id = (
                    cv._response_header(resp.headers, "x-request-id")
                    or cv._response_header(resp.headers, "x-mistral-request-id")
                )
                parsed = json.loads(raw) if raw else {}
            latency_ms = int((time.perf_counter() - started) * 1000)
            usage = parsed.get("usage_info") if isinstance(parsed.get("usage_info"), dict) else {}
            pages_processed = int(
                usage.get("pages_processed") or len(parsed.get("pages") or []) or 0
            )
            meta = cv.EngineCallMeta(
                stage="identity_document_annotation",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                provider_response_model=str(parsed.get("model") or MISTRAL_OCR_MODEL_PIN),
                provider_request_id=request_id,
                latency_ms=latency_ms,
                billable_pages=pages_processed,
                estimated_cost_usd=cv.estimate_mistral_cost(pages_processed),
                pages=list(range(pages_processed)),
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": True, "latency_ms": latency_ms})
            _circuit_record_success()
            dpf.record_spend(ocr_usd=float(meta.estimated_cost_usd or 0.0), sampled=True)
            return parsed if isinstance(parsed, dict) else {}, meta, attempts
        except urllib_error.HTTPError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                detail = str(exc)
            err = f"http_{getattr(exc, 'code', 'error')}:{detail[:200]}"
            last_meta = cv.EngineCallMeta(
                stage="identity_document_annotation",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                latency_ms=latency_ms,
                error=err,
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            transient = getattr(exc, "code", 0) in {408, 429, 500, 502, 503, 504}
            if not transient:
                break
            time.sleep(min(2 ** (attempt - 1), 4))
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            err = type(exc).__name__
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                err = f"timeout:{err}"
            last_meta = cv.EngineCallMeta(
                stage="identity_document_annotation",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                latency_ms=latency_ms,
                error=err,
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            time.sleep(min(2 ** (attempt - 1), 4))

    circuit = _circuit_record_failure()
    meta = last_meta or cv.EngineCallMeta(
        stage="identity_document_annotation",
        tier="mistral_document_ai",
        provider="mistral",
        actual_request_model=MISTRAL_OCR_MODEL_PIN,
        error="mistral_failed",
        retention="base64_direct_no_files_api",
    )
    if circuit.get("opened"):
        meta.error = f"{meta.error}|circuit_opened"
    return {}, meta, attempts


def _annotation_dict(parsed: dict[str, Any]) -> dict[str, Any]:
    ann = parsed.get("document_annotation")
    if isinstance(ann, dict):
        return ann
    if isinstance(ann, str):
        try:
            obj = json.loads(ann)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def materialize_fields(annotation: dict[str, Any], *, source: str) -> dict[str, Any]:
    conf_map = annotation.get("field_confidence") if isinstance(annotation.get("field_confidence"), dict) else {}
    overall = annotation.get("overall_confidence")
    try:
        overall_f = float(overall) if overall is not None else None
    except Exception:
        overall_f = None

    def conf(key: str) -> float | None:
        if key in conf_map:
            try:
                return float(conf_map[key])
            except Exception:
                return overall_f
        return overall_f

    keys = [
        "document_type",
        "side",
        "document_relationship",
        "full_name_ar",
        "full_name_en",
        "document_number",
        "nationality",
        "date_of_birth",
        "issue_date",
        "expiry_date",
        "employer_or_sponsor",
    ]
    fields = {
        k: _field(value=_null_if_blank(annotation.get(k)), confidence=conf(k), source=source)
        for k in keys
    }
    # Compatibility alias for legacy GPT shape
    legacy_name = fields["full_name_en"]["value"] or fields["full_name_ar"]["value"]
    fields["full_name"] = _field(value=legacy_name, confidence=conf("full_name_en"), source=source)
    fields["issued_date"] = fields["issue_date"]
    return fields


def extract_identity_document(
    *,
    path: Path | str,
    expected_type: str | None = None,
    company_code: str = "WATHEFNI",
    subject_key: str | None = None,
    source_channel: str = "identity_wave1_qualify",
) -> dict[str, Any]:
    """Envelope → Mistral Document AI → field provenance → deterministic validation.

    Never calls GPT. On unusable extraction returns durable needs_review.
    """

    file_path = Path(path)
    content_sha = sha256_file(file_path)
    file_type = file_path.suffix.lower().lstrip(".") or "bin"
    route = dpf.resolve_route(document_class="identity", file_type=file_type) or {}

    envelope = dpf.build_document_envelope(
        company_code=company_code,
        subject_type="employee_identity",
        subject_key=subject_key or content_sha[:16],
        content_sha256=content_sha,
        source_channel=source_channel,
        document_class="identity",
        file_type=file_type,
        authority_label="needs_hr_confirmation",
        processing={
            "status": "started",
            "extractor": IDENTITY_EXTRACTOR,
            "contract": IDENTITY_CONTRACT,
            "expected_type": expected_type,
            "route": route,
            "gpt_auto_fallback": False,
            "cv_v2_forbidden": True,
        },
        retention_class="identity_document",
    )

    if _circuit_open():
        envelope["processing"]["status"] = "needs_review"
        envelope["error"] = "mistral_circuit_open"
        return {
            "ok": False,
            "extraction_status": "needs_review",
            "extraction_error": "mistral_circuit_open",
            "authoritative": False,
            "envelope": envelope,
            "fields": {},
            "validation": {"ok": False, "issues": ["mistral_circuit_open"]},
            "cost_usd": 0.0,
            "latency_ms": 0,
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
        }

    parsed, meta, attempts = mistral_identity_annotation(path=file_path)
    annotation = _annotation_dict(parsed)
    if not annotation:
        envelope["processing"]["status"] = "needs_review"
        envelope["error"] = str(meta.error or "annotation_missing")
        return {
            "ok": False,
            "extraction_status": "needs_review",
            "extraction_error": str(meta.error or "annotation_missing"),
            "authoritative": False,
            "envelope": envelope,
            "fields": {},
            "validation": {"ok": False, "issues": ["extraction_unusable"]},
            "attempts": attempts,
            "engine": meta.__dict__ if hasattr(meta, "__dict__") else {},
            "cost_usd": float(meta.estimated_cost_usd or 0.0),
            "latency_ms": int(meta.latency_ms or 0),
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
            "pages_markdown": [
                str((p or {}).get("markdown") or "")[:500]
                for p in (parsed.get("pages") or [])
                if isinstance(p, dict)
            ][:3],
        }

    fields = materialize_fields(annotation, source="mistral_document_ai")
    if expected_type and not fields["document_type"]["value"]:
        fields["document_type"] = _field(
            value=expected_type, confidence=0.4, source="expected_type_hint"
        )
    validation = validate_identity_fields(fields, expected_type=expected_type)
    overall = annotation.get("overall_confidence")
    try:
        confidence = float(overall) if overall is not None else 0.0
    except Exception:
        confidence = 0.0

    status = "extracted"
    if confidence < 0.55:
        status = "low_confidence"
    if not validation["ok"] and "type_mismatch" in ",".join(validation["issues"]):
        status = "mismatch"
    if not any(
        (fields[k]["value"] for k in ("document_number", "full_name_en", "full_name_ar", "expiry_date"))
    ):
        status = "needs_review"

    envelope["processing"]["status"] = status
    envelope["processing"]["validation"] = validation
    envelope["processing"]["confidence"] = confidence

    return {
        "ok": status in {"extracted", "low_confidence"},
        "extraction_status": status,
        "authoritative": False,
        "hr_confirmation_required": True,
        "confidence": confidence,
        "fields": fields,
        "validation": validation,
        "envelope": envelope,
        "attempts": attempts,
        "engine": {
            "provider": meta.provider,
            "model": meta.actual_request_model,
            "latency_ms": meta.latency_ms,
            "billable_pages": meta.billable_pages,
            "estimated_cost_usd": meta.estimated_cost_usd,
            "request_id": meta.provider_request_id,
            "error": meta.error,
        },
        "cost_usd": float(meta.estimated_cost_usd or 0.0),
        "latency_ms": int(meta.latency_ms or 0),
        "provider": "mistral",
        "model": MISTRAL_OCR_MODEL_PIN,
        "content_sha256": content_sha,
        "legacy_compat": {
            "document_type": fields["document_type"]["value"],
            "document_number": fields["document_number"]["value"],
            "issued_date": fields["issue_date"]["value"],
            "expiry_date": fields["expiry_date"]["value"],
            "nationality": fields["nationality"]["value"],
            "full_name": fields["full_name"]["value"],
            "date_of_birth": fields["date_of_birth"]["value"],
            "confidence": confidence,
            "extraction_status": status,
            "issued_date_parsed": _parse_iso_date(fields["issue_date"]["value"]),
            "expiry_date_parsed": _parse_iso_date(fields["expiry_date"]["value"]),
            "date_of_birth_parsed": _parse_iso_date(fields["date_of_birth"]["value"]),
        },
    }


def duplicate_keys(result: dict[str, Any]) -> dict[str, str]:
    """Keys used for duplicate detection (content hash + identifiers)."""

    fields = result.get("fields") or {}
    number = _null_if_blank((fields.get("document_number") or {}).get("value"))
    doc_type = _null_if_blank((fields.get("document_type") or {}).get("value"))
    return {
        "content_sha256": str(result.get("content_sha256") or ""),
        "identifier_key": f"{doc_type or 'unknown'}:{number or ''}".lower(),
    }


def _cache_get(key: str) -> dict[str, Any] | None:
    row = _RESULT_CACHE.get(key)
    if not row:
        return None
    ts, payload = row
    if time.time() - ts > _CACHE_TTL_S:
        _RESULT_CACHE.pop(key, None)
        return None
    _bump("cache_hits")
    return dict(payload)


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    _RESULT_CACHE[key] = (time.time(), dict(payload))


def classification_json_schema() -> dict[str, Any]:
    base = identity_json_schema()
    props = dict(base["properties"])
    props["detected_item"] = {
        "type": "string",
        "enum": sorted(ONBOARDING_MEDIA_TYPES),
    }
    props["matches_expected_item"] = {"type": ["boolean", "null"]}
    props["reason"] = {"type": ["string", "null"]}
    required = list(base["required"]) + ["detected_item"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": required,
    }


def classification_annotation_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "wathefni_identity_onboarding_classify_v1",
            "schema": classification_json_schema(),
            "strict": True,
        },
    }


CLASSIFY_ANNOTATION_PROMPT = (
    "Classify this employee onboarding upload for Kuwait HR. "
    "detected_item must be one of: civil_id, passport, residency, work_permit, medical, "
    "personal_photo, education_cert, instruction_screenshot, unknown. "
    "A personal_photo must be a clear portrait/headshot. "
    "WhatsApp screenshots, checklists, or instruction images are instruction_screenshot. "
    "If it is an identity/compliance document, also extract visible fields; otherwise leave fields null. "
    "For Kuwait Civil ID: portrait/photo face is side=front (document_relationship=civil_id_front_of); "
    "reverse with address/barcode/blood type is side=back (document_relationship=pair_with_front). "
    "If side is unclear, use side=unknown — do not guess front. "
    "Never invent values. Prefer ISO dates YYYY-MM-DD. Preserve Arabic text."
)


def mistral_classify_annotation(
    *,
    path: Path,
    expected_item: str | None = None,
    allowed_items: list[str] | None = None,
    max_retries: int | None = None,
) -> tuple[dict[str, Any], cv.EngineCallMeta, list[dict[str, Any]]]:
    """OCR + classification annotation. Never calls GPT."""

    attempts: list[dict[str, Any]] = []
    retries = max_retries if max_retries is not None else max(
        1, int(os.environ.get("WATHEFNI_IDENTITY_MISTRAL_RETRIES") or "2")
    )
    api_key = cv.mistral_api_key()
    if not api_key:
        meta = cv.EngineCallMeta(
            stage="identity_document_classify",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="missing_mistral_api_key",
            retention="none_sent",
        )
        return {}, meta, attempts
    if _circuit_open():
        meta = cv.EngineCallMeta(
            stage="identity_document_classify",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="circuit_open",
            retention="none_sent",
        )
        return {}, meta, attempts

    prompt = CLASSIFY_ANNOTATION_PROMPT
    if expected_item:
        prompt += f" Expected item: {expected_item}."
    if allowed_items:
        prompt += " Allowed pending items: " + ", ".join(allowed_items) + "."

    body: dict[str, Any] = {
        "model": MISTRAL_OCR_MODEL_PIN,
        "document": _document_payload_for_path(path),
        "include_image_base64": False,
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
        "document_annotation_format": classification_annotation_format(),
        "document_annotation_prompt": prompt,
    }

    last_meta: cv.EngineCallMeta | None = None
    for attempt in range(1, retries + 1):
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
            with urllib_request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                request_id = (
                    cv._response_header(resp.headers, "x-request-id")
                    or cv._response_header(resp.headers, "x-mistral-request-id")
                )
                parsed = json.loads(raw) if raw else {}
            latency_ms = int((time.perf_counter() - started) * 1000)
            usage = parsed.get("usage_info") if isinstance(parsed.get("usage_info"), dict) else {}
            pages_processed = int(
                usage.get("pages_processed") or len(parsed.get("pages") or []) or 0
            )
            meta = cv.EngineCallMeta(
                stage="identity_document_classify",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                provider_response_model=str(parsed.get("model") or MISTRAL_OCR_MODEL_PIN),
                provider_request_id=request_id,
                latency_ms=latency_ms,
                billable_pages=pages_processed,
                estimated_cost_usd=cv.estimate_mistral_cost(pages_processed),
                pages=list(range(pages_processed)),
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": True, "latency_ms": latency_ms})
            _circuit_record_success()
            dpf.record_spend(ocr_usd=float(meta.estimated_cost_usd or 0.0), sampled=True)
            _bump("mistral_calls", provider="mistral")
            return parsed if isinstance(parsed, dict) else {}, meta, attempts
        except urllib_error.HTTPError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                detail = str(exc)
            err = f"http_{getattr(exc, 'code', 'error')}:{detail[:200]}"
            last_meta = cv.EngineCallMeta(
                stage="identity_document_classify",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                latency_ms=latency_ms,
                error=err,
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            if getattr(exc, "code", 0) not in {408, 429, 500, 502, 503, 504}:
                break
            time.sleep(min(2 ** (attempt - 1), 4))
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            err = type(exc).__name__
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                err = f"timeout:{err}"
            last_meta = cv.EngineCallMeta(
                stage="identity_document_classify",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                latency_ms=latency_ms,
                error=err,
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            time.sleep(min(2 ** (attempt - 1), 4))

    circuit = _circuit_record_failure()
    meta = last_meta or cv.EngineCallMeta(
        stage="identity_document_classify",
        tier="mistral_document_ai",
        provider="mistral",
        actual_request_model=MISTRAL_OCR_MODEL_PIN,
        error="mistral_failed",
        retention="base64_direct_no_files_api",
    )
    if circuit.get("opened"):
        meta.error = f"{meta.error}|circuit_opened"
    _bump("mistral_calls", provider="mistral")
    return {}, meta, attempts


def _needs_review_payload(*, error: str, company_code: str | None = None) -> dict[str, Any]:
    _bump("needs_review", provider="mistral")
    return {
        "ok": False,
        "extraction_status": "needs_review",
        "extraction_error": error,
        "authoritative": False,
        "hr_confirmation_required": True,
        "confidence": 0.0,
        "provider": "mistral",
        "model": MISTRAL_OCR_MODEL_PIN,
        "gpt_used": False,
        "company_code": company_code,
        "fields": {},
    }


def process_onboarding_media(
    *,
    path: Path | str,
    company_code: str | None = None,
    subject_key: str | None = None,
    expected_item: str | None = None,
    allowed_items: list[str] | None = None,
    source_channel: str = "identity_wave2_authority",
) -> dict[str, Any]:
    """Single Mistral Document AI pass for classify + optional identity fields."""

    file_path = Path(path)
    content_sha = sha256_file(file_path)
    cache_key = f"{content_sha}:{expected_item or ''}:{','.join(allowed_items or [])}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not identity_mistral_authority_enabled(company_code=company_code):
        out = _needs_review_payload(
            error="identity_mistral_authority_disabled",
            company_code=company_code,
        )
        out["detected_item"] = "unknown"
        out["matches_expected_item"] = False
        out["reason"] = "identity_authority_not_enabled_for_company"
        return out

    parsed, meta, attempts = mistral_classify_annotation(
        path=file_path,
        expected_item=expected_item,
        allowed_items=allowed_items,
    )
    annotation = _annotation_dict(parsed)
    if not annotation:
        out = _needs_review_payload(
            error=str(meta.error or "annotation_missing"),
            company_code=company_code,
        )
        out["detected_item"] = "unknown"
        out["matches_expected_item"] = False
        out["attempts"] = attempts
        out["engine"] = meta.__dict__ if hasattr(meta, "__dict__") else {}
        return out

    fields = materialize_fields(annotation, source="mistral_document_ai")
    detected = _null_if_blank(annotation.get("detected_item")) or _null_if_blank(
        annotation.get("document_type")
    ) or "unknown"
    if detected not in ONBOARDING_MEDIA_TYPES:
        detected = "unknown"
    # Align document_type for identity docs
    if detected in IDENTITY_DOC_TYPES and not fields["document_type"]["value"]:
        fields["document_type"] = _field(value=detected, confidence=0.7, source="detected_item")

    validation = validate_identity_fields(
        fields,
        expected_type=expected_item if expected_item in IDENTITY_DOC_TYPES else None,
    )
    try:
        confidence = float(annotation.get("overall_confidence"))
    except Exception:
        confidence = 0.0
    if confidence <= 0:
        try:
            confidence = float(annotation.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0

    matches = False
    if expected_item:
        matches = detected == expected_item
        if annotation.get("matches_expected_item") is True and detected == expected_item:
            matches = True
        if annotation.get("matches_expected_item") is False:
            matches = False

    status = "extracted"
    if confidence < 0.55:
        status = "low_confidence"
    if detected == "unknown":
        status = "needs_review"
    if expected_item and not matches and confidence >= 0.65:
        status = "mismatch"
    if detected in IDENTITY_DOC_TYPES and not any(
        fields[k]["value"] for k in ("document_number", "full_name_en", "full_name_ar", "expiry_date")
    ):
        # Classification can still succeed without full fields (e.g. personal_photo path)
        if expected_item in IDENTITY_DOC_TYPES:
            status = "low_confidence" if status == "extracted" else status

    envelope = dpf.build_document_envelope(
        company_code=company_code,
        subject_type="employee_identity",
        subject_key=subject_key or content_sha[:16],
        content_sha256=content_sha,
        source_channel=source_channel,
        document_class="identity",
        file_type=file_path.suffix.lower().lstrip(".") or "bin",
        authority_label="needs_hr_confirmation",
        processing={
            "status": status,
            "extractor": IDENTITY_EXTRACTOR,
            "contract": IDENTITY_CONTRACT,
            "expected_item": expected_item,
            "detected_item": detected,
            "gpt_auto_fallback": False,
            "cv_v2_forbidden": True,
            "validation": validation,
            "confidence": confidence,
        },
        retention_class="identity_document",
    )

    out = {
        "ok": status in {"extracted", "low_confidence"} or (matches and confidence >= 0.55),
        "extraction_status": status,
        "authoritative": False,
        "hr_confirmation_required": True,
        "confidence": confidence,
        "detected_item": detected,
        "matches_expected_item": matches if expected_item else None,
        "reason": _null_if_blank(annotation.get("reason")) or status,
        "side": fields.get("side", {}).get("value"),
        "fields": fields,
        "validation": validation,
        "envelope": envelope,
        "attempts": attempts,
        "engine": {
            "provider": meta.provider,
            "model": meta.actual_request_model,
            "latency_ms": meta.latency_ms,
            "billable_pages": meta.billable_pages,
            "estimated_cost_usd": meta.estimated_cost_usd,
            "request_id": meta.provider_request_id,
            "error": meta.error,
        },
        "cost_usd": float(meta.estimated_cost_usd or 0.0),
        "latency_ms": int(meta.latency_ms or 0),
        "provider": "mistral",
        "model": MISTRAL_OCR_MODEL_PIN,
        "content_sha256": content_sha,
        "gpt_used": False,
        "company_code": company_code,
        "duplicate_keys": {
            "content_sha256": content_sha,
            "identifier_key": f"{detected}:{_null_if_blank(fields.get('document_number', {}).get('value')) or ''}".lower(),
        },
        "legacy_compat": {
            "document_type": fields["document_type"]["value"] or (detected if detected in IDENTITY_DOC_TYPES else None),
            "document_number": fields["document_number"]["value"],
            "issued_date": fields["issue_date"]["value"],
            "expiry_date": fields["expiry_date"]["value"],
            "nationality": fields["nationality"]["value"],
            "full_name": fields["full_name"]["value"],
            "full_name_ar": fields["full_name_ar"]["value"],
            "full_name_en": fields["full_name_en"]["value"],
            "date_of_birth": fields["date_of_birth"]["value"],
            "employer_or_sponsor": fields["employer_or_sponsor"]["value"],
            "side": fields["side"]["value"],
            "confidence": confidence,
            "extraction_status": status,
            "extraction_error": None if status != "needs_review" else "extraction_unusable",
            "issued_date_parsed": _parse_iso_date(fields["issue_date"]["value"]),
            "expiry_date_parsed": _parse_iso_date(fields["expiry_date"]["value"]),
            "date_of_birth_parsed": _parse_iso_date(fields["date_of_birth"]["value"]),
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "fields": fields,
            "envelope": envelope,
            "validation": validation,
        },
    }
    _cache_put(cache_key, out)
    return out


def classify_onboarding_media(
    *,
    media: dict[str, Any] | None,
    allowed_items: list[str],
    company_code: str | None = None,
    subject_key: str | None = None,
    text: str = "",
) -> dict[str, Any] | None:
    _bump("classify_calls")
    path = resolve_media_path(media)
    if not path or not allowed_items:
        return None
    result = process_onboarding_media(
        path=path,
        company_code=company_code,
        subject_key=subject_key,
        allowed_items=list(allowed_items),
        source_channel="identity_wave2_classify",
    )
    if result.get("extraction_status") == "needs_review" and result.get("extraction_error") in {
        "identity_mistral_authority_disabled",
        "mistral_circuit_open",
        "missing_mistral_api_key",
    }:
        return {
            "detected_item": "unknown",
            "confidence": 0.0,
            "reason": result.get("extraction_error") or "needs_review",
            "provider": "mistral",
            "gpt_used": False,
            "extraction_status": "needs_review",
        }
    return {
        "detected_item": result.get("detected_item") or "unknown",
        "confidence": float(result.get("confidence") or 0.0),
        "reason": result.get("reason") or result.get("extraction_status"),
        "provider": "mistral",
        "model": result.get("model"),
        "gpt_used": False,
        "side": result.get("side"),
        "extraction_status": result.get("extraction_status"),
        "content_sha256": result.get("content_sha256"),
        "identity_result": result,
    }


def verify_onboarding_media(
    *,
    item_id: str,
    media: dict[str, Any] | None,
    company_code: str | None = None,
    subject_key: str | None = None,
    text: str = "",
) -> dict[str, Any] | None:
    _bump("verify_calls")
    path = resolve_media_path(media)
    if not path or not item_id:
        return None
    result = process_onboarding_media(
        path=path,
        company_code=company_code,
        subject_key=subject_key,
        expected_item=item_id,
        allowed_items=[item_id],
        source_channel="identity_wave2_verify",
    )
    detected = str(result.get("detected_item") or "unknown")
    confidence = float(result.get("confidence") or 0.0)
    matches = bool(result.get("matches_expected_item"))
    if result.get("extraction_status") == "needs_review" and not matches:
        return {
            "matches_expected_item": False,
            "detected_item": detected,
            "confidence": confidence,
            "reason": result.get("extraction_error") or "needs_review",
            "provider": "mistral",
            "gpt_used": False,
            "extraction_status": "needs_review",
            "unreadable_reason": result.get("unreadable_reason")
            or (result.get("legacy_compat") or {}).get("unreadable_reason"),
            "side": result.get("side"),
        }
    return {
        "matches_expected_item": matches,
        "detected_item": detected,
        "confidence": confidence,
        "reason": result.get("reason") or result.get("extraction_status"),
        "provider": "mistral",
        "model": result.get("model"),
        "gpt_used": False,
        "side": result.get("side"),
        "unreadable_reason": result.get("unreadable_reason")
        or (result.get("legacy_compat") or {}).get("unreadable_reason"),
        "extraction_status": result.get("extraction_status"),
        "content_sha256": result.get("content_sha256"),
        "identity_result": result,
    }


def extract_compliance_via_mistral(
    *,
    document_type: str,
    media: dict[str, Any] | None,
    company_code: str | None = None,
    subject_key: str | None = None,
    text: str = "",
) -> dict[str, Any] | None:
    """Legacy-compatible extraction payload. Never calls GPT."""

    _bump("extract_calls")
    if document_type not in IDENTITY_DOC_TYPES:
        return None
    path = resolve_media_path(media)
    if not path:
        return {
            "extraction_status": "needs_review",
            "extraction_error": "missing_media_path",
            "confidence": 0.0,
            "provider": "mistral",
            "gpt_used": False,
            "authoritative": False,
            "hr_confirmation_required": True,
        }
    # Prefer dedicated extract for identity field quality; fall back to process cache.
    if identity_mistral_authority_enabled(company_code=company_code):
        extracted = extract_identity_document(
            path=path,
            expected_type=document_type,
            company_code=company_code or "WATHEFNI",
            subject_key=subject_key,
            source_channel="identity_wave2_extract",
        )
        _bump("mistral_calls", provider="mistral")
        legacy = dict(extracted.get("legacy_compat") or {})
        legacy.update(
            {
                "provider": "mistral",
                "model": extracted.get("model"),
                "gpt_used": False,
                "authoritative": False,
                "hr_confirmation_required": True,
                "fields": extracted.get("fields") or {},
                "envelope": extracted.get("envelope"),
                "validation": extracted.get("validation"),
                "content_sha256": extracted.get("content_sha256"),
                "side": ((extracted.get("fields") or {}).get("side") or {}).get("value"),
                "full_name_ar": ((extracted.get("fields") or {}).get("full_name_ar") or {}).get("value"),
                "full_name_en": ((extracted.get("fields") or {}).get("full_name_en") or {}).get("value"),
                "employer_or_sponsor": (
                    (extracted.get("fields") or {}).get("employer_or_sponsor") or {}
                ).get("value"),
                "cost_usd": extracted.get("cost_usd"),
                "latency_ms": extracted.get("latency_ms"),
            }
        )
        if extracted.get("extraction_status") == "needs_review":
            legacy["extraction_status"] = "needs_review"
            legacy["extraction_error"] = extracted.get("extraction_error") or "extraction_unusable"
        return legacy

    return {
        "extraction_status": "needs_review",
        "extraction_error": "identity_mistral_authority_disabled",
        "confidence": 0.0,
        "provider": "mistral",
        "gpt_used": False,
        "authoritative": False,
        "hr_confirmation_required": True,
    }
