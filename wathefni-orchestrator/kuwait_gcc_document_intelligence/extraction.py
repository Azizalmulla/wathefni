"""Shared channel-agnostic extraction — delegates identity; structures contracts/certs."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import cv_extraction as cv
import document_processing_foundation as dpf
import identity_document_extraction as ide
from kuwait_gcc_document_intelligence.jurisdiction_kw import (
    issuing_authority_for,
    jurisdiction_profile,
)
from kuwait_gcc_document_intelligence.schemas import (
    BANK_CERTIFICATE_ANNOTATION_PROMPT,
    COMPLIANCE_ANNOTATION_PROMPT,
    CONTRACT_ANNOTATION_PROMPT,
    GENERATED_ONLY_TYPES,
    IDENTITY_DELEGATE_TYPES,
    STORAGE_ONLY_TYPES,
    STRUCTURING_TYPES,
    bank_certificate_json_schema,
    compliance_certificate_json_schema,
    employment_contract_json_schema,
    normalize_document_type,
)
from kuwait_gcc_document_intelligence.validation import duplicate_keys, validate_common_fields

CONTRACT = "kuwait-gcc-document-intelligence-v1"
EXTRACTOR = "kuwait_gcc_mistral_document_ai"
MISTRAL_OCR_MODEL_PIN = cv.MISTRAL_OCR_MODEL

_RUNTIME_LOCK = threading.Lock()
_RUNTIME: dict[str, Any] = {
    "mistral_calls": 0,
    "identity_delegate_calls": 0,
    "gpt_calls": 0,  # must remain 0
    "needs_review": 0,
    "classify_calls": 0,
    "verify_calls": 0,
    "extract_calls": 0,
    "last_provider": None,
}


def runtime_counters() -> dict[str, Any]:
    with _RUNTIME_LOCK:
        return dict(_RUNTIME)


def reset_runtime_counters() -> None:
    with _RUNTIME_LOCK:
        for k, v in list(_RUNTIME.items()):
            _RUNTIME[k] = 0 if isinstance(v, int) else None


def _bump(counter: str, *, provider: str | None = None) -> None:
    with _RUNTIME_LOCK:
        _RUNTIME[counter] = int(_RUNTIME.get(counter) or 0) + 1
        if provider:
            _RUNTIME["last_provider"] = provider


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _null_if_blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    return text


def _field(value: Any, confidence: float | None, source: str) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": None if confidence is None else float(confidence),
        "provenance": {
            "source": source,
            "extractor": EXTRACTOR,
            "contract": CONTRACT,
            "authoritative": False,
            "hr_confirmed": False,
        },
    }


def _resolve_path(media: dict[str, Any] | None = None, path: Path | str | None = None) -> Path | None:
    if path:
        p = Path(path)
        return p if p.exists() and p.is_file() else None
    return ide.resolve_media_path(media)


def _sniff_mime(data: bytes, *, path: Path | None = None, mime_type: str | None = None) -> str:
    """Resolve a Mistral-safe MIME. Bank evidence paths often have no suffix."""
    hinted = str(mime_type or "").split(";")[0].strip().lower()
    if hinted in {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    }:
        return hinted
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    suffix = (path.suffix.lower() if path else "")
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(suffix, "application/octet-stream")


def _payload(path: Path, *, mime_type: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = _sniff_mime(data, path=path, mime_type=mime_type)
    return {"type": "document_url", "document_url": f"data:{mime};base64,{b64}"}


def _annotation_format(schema: dict[str, Any], name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "schema": schema, "strict": True},
    }


def _parse_annotation(parsed: dict[str, Any]) -> dict[str, Any]:
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


def _mistral_annotate(
    *,
    path: Path,
    schema: dict[str, Any],
    schema_name: str,
    prompt: str,
    mime_type: str | None = None,
) -> tuple[dict[str, Any], cv.EngineCallMeta, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    retries = max(1, int(os.environ.get("WATHEFNI_KUWAIT_GCC_MISTRAL_RETRIES") or os.environ.get("WATHEFNI_IDENTITY_MISTRAL_RETRIES") or "2"))
    api_key = cv.mistral_api_key()
    if not api_key:
        return {}, cv.EngineCallMeta(
            stage="kuwait_gcc_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="missing_mistral_api_key",
            retention="none_sent",
        ), attempts
    if ide._circuit_open():
        return {}, cv.EngineCallMeta(
            stage="kuwait_gcc_annotation",
            tier="mistral_document_ai",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL_PIN,
            error="circuit_open",
            retention="none_sent",
        ), attempts

    body = {
        "model": MISTRAL_OCR_MODEL_PIN,
        "document": _payload(path, mime_type=mime_type),
        "include_image_base64": False,
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
        "document_annotation_format": _annotation_format(schema, schema_name),
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
            with urllib_request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                request_id = (
                    cv._response_header(resp.headers, "x-request-id")
                    or cv._response_header(resp.headers, "x-mistral-request-id")
                )
                parsed = json.loads(raw) if raw else {}
            latency_ms = int((time.perf_counter() - started) * 1000)
            usage = parsed.get("usage_info") if isinstance(parsed.get("usage_info"), dict) else {}
            pages_processed = int(usage.get("pages_processed") or len(parsed.get("pages") or []) or 0)
            meta = cv.EngineCallMeta(
                stage="kuwait_gcc_annotation",
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
            ide._circuit_record_success()
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
                stage="kuwait_gcc_annotation",
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
            if "timeout" in str(exc).lower():
                err = f"timeout:{err}"
            last_meta = cv.EngineCallMeta(
                stage="kuwait_gcc_annotation",
                tier="mistral_document_ai",
                provider="mistral",
                actual_request_model=MISTRAL_OCR_MODEL_PIN,
                latency_ms=latency_ms,
                error=err,
                retention="base64_direct_no_files_api",
            )
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            time.sleep(min(2 ** (attempt - 1), 4))

    circuit = ide._circuit_record_failure()
    meta = last_meta or cv.EngineCallMeta(
        stage="kuwait_gcc_annotation",
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


def _delegate_identity(
    *,
    path: Path,
    document_type: str,
    company_code: str | None,
    subject_key: str | None,
    channel: str,
    mode: str,
    allowed_items: list[str] | None = None,
) -> dict[str, Any]:
    """Reuse live identity Mistral authority — do not reimplement."""

    _bump("identity_delegate_calls", provider="mistral")
    expected = document_type if document_type != "residence" else "residency"
    # Identity module uses residency in its schema enum.
    if mode == "classify":
        result = ide.classify_onboarding_media(
            media={"path": str(path), "mime_type": "application/octet-stream"},
            allowed_items=allowed_items or [expected, "civil_id", "passport", "medical", "work_permit", "education_cert"],
            company_code=company_code,
            subject_key=subject_key,
        )
        out = dict(result or {})
        out["delegated_to"] = "identity_document_extraction"
        out["gpt_used"] = False
        out["channel"] = channel
        return out
    if mode == "verify":
        result = ide.verify_onboarding_media(
            item_id=expected if expected != "residence" else "residency",
            media={"path": str(path)},
            company_code=company_code,
            subject_key=subject_key,
        )
        # Also accept residence canonical match
        if result and document_type == "residence":
            detected = str(result.get("detected_item") or "")
            if detected in {"residency", "residence"} and expected in {"residency", "residence"}:
                result = dict(result)
                result["matches_expected_item"] = detected in {"residency", "residence"}
                result["detected_item"] = "residence" if detected == "residency" else detected
        out = dict(result or {})
        out["delegated_to"] = "identity_document_extraction"
        out["gpt_used"] = False
        out["channel"] = channel
        return out

    extracted = ide.extract_compliance_via_mistral(
        document_type=expected if expected != "residence" else "residency",
        media={"path": str(path)},
        company_code=company_code,
        subject_key=subject_key,
    )
    out = dict(extracted or {})
    # Normalize residency → residence for shared channel records
    if out.get("document_type") == "residency":
        out["document_type"] = "residence"
    out["delegated_to"] = "identity_document_extraction"
    out["gpt_used"] = False
    out["channel"] = channel
    out["country_code"] = out.get("country_code") or "KW"
    out["jurisdiction"] = out.get("jurisdiction") or "kuwait_private_sector"
    if not out.get("issuing_authority"):
        out["issuing_authority"] = issuing_authority_for(
            "residence" if document_type in {"residence", "residency"} else document_type
        )
    return out


def _materialize_contract(annotation: dict[str, Any], *, country_code: str) -> dict[str, Any]:
    conf_map = annotation.get("field_confidence") if isinstance(annotation.get("field_confidence"), dict) else {}
    try:
        overall = float(annotation.get("overall_confidence")) if annotation.get("overall_confidence") is not None else None
    except Exception:
        overall = None

    def conf(key: str) -> float | None:
        if key in conf_map:
            try:
                return float(conf_map[key])
            except Exception:
                return overall
        return overall

    keys = [
        "document_type",
        "country_code",
        "jurisdiction",
        "issuing_authority",
        "document_number",
        "employee_name_ar",
        "employee_name_en",
        "employer_legal_name_ar",
        "employer_legal_name_en",
        "job_title",
        "contract_type",
        "contract_start_date",
        "contract_end_date",
        "probation_period",
        "salary_amount",
        "salary_currency",
        "allowances",
        "work_location",
        "working_hours",
        "weekly_rest_days",
        "annual_leave_entitlement",
        "notice_period",
        "renewal_terms",
        "termination_clauses",
        "signatories",
        "employee_signature_status",
        "employer_signature_status",
        "issue_date",
        "expiry_date",
        "renewal_required",
    ]
    fields = {
        k: _field(_null_if_blank(annotation.get(k)) if k != "salary_amount" and k != "renewal_required" else annotation.get(k), conf(k), "mistral_document_ai")
        for k in keys
    }
    if not fields["country_code"]["value"]:
        fields["country_code"] = _field(country_code, 0.4, "jurisdiction_profile")
    if not fields["jurisdiction"]["value"]:
        profile = jurisdiction_profile(country_code) or {}
        fields["jurisdiction"] = _field(profile.get("jurisdiction"), 0.4, "jurisdiction_profile")
    if not fields["issuing_authority"]["value"]:
        fields["issuing_authority"] = _field("EMPLOYER", 0.4, "jurisdiction_profile")
    # Compatibility aliases for receipt/compliance dual-write
    fields["full_name"] = _field(
        fields["employee_name_en"]["value"] or fields["employee_name_ar"]["value"],
        conf("employee_name_en"),
        "mistral_document_ai",
    )
    fields["employer_or_sponsor"] = _field(
        fields["employer_legal_name_en"]["value"] or fields["employer_legal_name_ar"]["value"],
        conf("employer_legal_name_en"),
        "mistral_document_ai",
    )
    fields["employee_or_holder"] = fields["full_name"]
    # Do NOT alias contract_start_date → issue_date (different semantics; invents false issue dates).
    # Expiry for renewal tracking may mirror contract_end_date only when end date is present.
    if fields["expiry_date"]["value"] is None and fields["contract_end_date"]["value"]:
        end = fields["contract_end_date"]
        fields["expiry_date"] = _field(end["value"], end.get("confidence"), "contract_end_date_alias")
    # Drop hallucinated issue_date when model copied start/end without a real issue line.
    issue_v = fields["issue_date"]["value"]
    start_v = fields["contract_start_date"]["value"]
    if issue_v and start_v and str(issue_v).strip() == str(start_v).strip():
        fields["issue_date"] = _field(None, None, "suppressed_start_alias")
    fields["clause_evidence"] = _field(annotation.get("clause_evidence") or [], conf("clause_evidence"), "mistral_document_ai")
    return fields


def _materialize_compliance(annotation: dict[str, Any], *, country_code: str, expected_type: str) -> dict[str, Any]:
    conf_map = annotation.get("field_confidence") if isinstance(annotation.get("field_confidence"), dict) else {}
    try:
        overall = float(annotation.get("overall_confidence")) if annotation.get("overall_confidence") is not None else None
    except Exception:
        overall = None

    def conf(key: str) -> float | None:
        if key in conf_map:
            try:
                return float(conf_map[key])
            except Exception:
                return overall
        return overall

    keys = [
        "document_type",
        "country_code",
        "jurisdiction",
        "issuing_authority",
        "document_number",
        "employee_or_holder_ar",
        "employee_or_holder_en",
        "employer_or_sponsor",
        "occupation_or_profession",
        "permit_or_residency_category",
        "qualification_or_category",
        "document_status",
        "issue_date",
        "expiry_date",
        "renewal_required",
    ]
    fields = {
        k: _field(
            annotation.get(k) if k == "renewal_required" else _null_if_blank(annotation.get(k)),
            conf(k),
            "mistral_document_ai",
        )
        for k in keys
    }
    if not fields["country_code"]["value"]:
        fields["country_code"] = _field(country_code, 0.4, "jurisdiction_profile")
    if not fields["jurisdiction"]["value"]:
        profile = jurisdiction_profile(country_code) or {}
        fields["jurisdiction"] = _field(profile.get("jurisdiction"), 0.4, "jurisdiction_profile")
    if not fields["issuing_authority"]["value"]:
        fields["issuing_authority"] = _field(
            issuing_authority_for(expected_type, country_code=country_code) or "UNKNOWN",
            0.4,
            "jurisdiction_profile",
        )
    fields["full_name"] = _field(
        fields["employee_or_holder_en"]["value"] or fields["employee_or_holder_ar"]["value"],
        conf("employee_or_holder_en"),
        "mistral_document_ai",
    )
    fields["employee_or_holder"] = fields["full_name"]
    return fields


def _normalize_iban_candidate(value: Any) -> str | None:
    text = _null_if_blank(value)
    if not text:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    return cleaned or None


def _materialize_bank_certificate(annotation: dict[str, Any], *, country_code: str) -> dict[str, Any]:
    conf_map = annotation.get("field_confidence") if isinstance(annotation.get("field_confidence"), dict) else {}
    try:
        overall = float(annotation.get("overall_confidence")) if annotation.get("overall_confidence") is not None else None
    except Exception:
        overall = None

    def conf(key: str) -> float | None:
        if key in conf_map:
            try:
                return float(conf_map[key])
            except Exception:
                return overall
        return overall

    iban = _normalize_iban_candidate(annotation.get("iban"))
    account_number = _null_if_blank(annotation.get("account_number"))
    if account_number:
        account_number = re.sub(r"\s+", "", str(account_number))
    fields = {
        "document_type": _field(
            _null_if_blank(annotation.get("document_type")) or "bank_certificate",
            conf("document_type"),
            "mistral_document_ai",
        ),
        "country_code": _field(
            _null_if_blank(annotation.get("country_code")) or country_code,
            conf("country_code"),
            "mistral_document_ai",
        ),
        "bank_name": _field(_null_if_blank(annotation.get("bank_name")), conf("bank_name"), "mistral_document_ai"),
        "account_holder": _field(
            _null_if_blank(annotation.get("account_holder")), conf("account_holder"), "mistral_document_ai"
        ),
        "iban": _field(iban, conf("iban"), "mistral_document_ai"),
        "account_number": _field(account_number, conf("account_number"), "mistral_document_ai"),
        "branch": _field(_null_if_blank(annotation.get("branch")), conf("branch"), "mistral_document_ai"),
        "swift": _field(
            (_null_if_blank(annotation.get("swift")) or "").upper() or None,
            conf("swift"),
            "mistral_document_ai",
        ),
        "currency": _field(_null_if_blank(annotation.get("currency")), conf("currency"), "mistral_document_ai"),
        "unreadable_reason": _field(
            _null_if_blank(annotation.get("unreadable_reason")), conf("unreadable_reason"), "mistral_document_ai"
        ),
        "warnings": _field(
            [str(w) for w in (annotation.get("warnings") or []) if str(w).strip()],
            overall,
            "mistral_document_ai",
        ),
    }
    return fields


def process_document(
    *,
    path: Path | str | None = None,
    media: dict[str, Any] | None = None,
    document_type: str | None = None,
    expected_item: str | None = None,
    allowed_items: list[str] | None = None,
    company_code: str | None = None,
    subject_key: str | None = None,
    country_code: str = "KW",
    channel: str = "shared",
    mode: str = "extract",  # classify | verify | extract
) -> dict[str, Any]:
    """Single shared entry for all channels. Never calls GPT. Never uses CV V2."""

    file_path = _resolve_path(media, path)
    if not file_path:
        _bump("needs_review")
        return {
            "ok": False,
            "extraction_status": "needs_review",
            "extraction_error": "missing_media_path",
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "provider": "mistral",
            "channel": channel,
        }

    doc_type = normalize_document_type(document_type or expected_item)
    if mode == "classify":
        _bump("classify_calls")
    elif mode == "verify":
        _bump("verify_calls")
    else:
        _bump("extract_calls")

    if doc_type in GENERATED_ONLY_TYPES:
        return {
            "ok": False,
            "extraction_status": "skipped_generated_only",
            "extraction_error": "generated_documents_never_ocr",
            "authoritative": False,
            "gpt_used": False,
            "channel": channel,
        }

    # Identity family — preserve live Mistral authority module.
    if doc_type in IDENTITY_DELEGATE_TYPES or (
        mode == "classify" and not doc_type
    ):
        if mode == "classify" and not doc_type:
            # Classify via identity classifier (includes education_cert sibling).
            return _delegate_identity(
                path=file_path,
                document_type="unknown",
                company_code=company_code,
                subject_key=subject_key,
                channel=channel,
                mode="classify",
                allowed_items=allowed_items,
            )
        return _delegate_identity(
            path=file_path,
            document_type=doc_type or "unknown",
            company_code=company_code,
            subject_key=subject_key,
            channel=channel,
            mode=mode if mode in {"classify", "verify", "extract"} else "extract",
            allowed_items=allowed_items,
        )

    if doc_type in STORAGE_ONLY_TYPES and doc_type not in STRUCTURING_TYPES:
        return {
            "ok": True,
            "extraction_status": "storage_only",
            "document_type": doc_type,
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "provider": None,
            "channel": channel,
            "fields": {},
        }

    if doc_type not in STRUCTURING_TYPES and doc_type not in {
        "education_cert",
        "employment_contract",
        "contract_amendment",
        "bank_certificate",
    }:
        _bump("needs_review")
        return {
            "ok": False,
            "extraction_status": "needs_review",
            "extraction_error": f"unsupported_or_mirror_only:{doc_type}",
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "channel": channel,
        }

    content_sha = _sha256(file_path)
    is_bank = doc_type in {"bank_certificate", "iban_letter"}
    is_contract = doc_type in {"employment_contract", "contract_amendment", "offer_letter"}
    if is_bank:
        schema = bank_certificate_json_schema()
        schema_name = "wathefni_kw_bank_certificate_v1"
        prompt = BANK_CERTIFICATE_ANNOTATION_PROMPT
        doc_class = "bank"
    elif is_contract:
        schema = employment_contract_json_schema()
        schema_name = "wathefni_kw_employment_contract_v1"
        prompt = CONTRACT_ANNOTATION_PROMPT
        doc_class = "contract"
    else:
        schema = compliance_certificate_json_schema()
        schema_name = "wathefni_kw_compliance_cert_v1"
        prompt = COMPLIANCE_ANNOTATION_PROMPT
        doc_class = "compliance"
    if expected_item:
        prompt += f" Expected document type: {expected_item}."

    envelope = dpf.build_document_envelope(
        company_code=company_code,
        subject_type="employee_bank" if is_bank else "employee_compliance",
        subject_key=subject_key or content_sha[:16],
        content_sha256=content_sha,
        source_channel=channel,
        document_class="compliance" if is_bank else doc_class,
        file_type=file_path.suffix.lower().lstrip(".") or "bin",
        authority_label="needs_hr_confirmation",
        processing={
            "status": "started",
            "extractor": EXTRACTOR,
            "contract": CONTRACT,
            "expected_type": doc_type,
            "gpt_auto_fallback": False,
            "cv_v2_forbidden": True,
            "country_code": country_code,
            "authoritative": False,
            "bank_ess_layer": "proposed_only" if is_bank else None,
        },
        retention_class="compliance_document",
    )

    media_mime = None
    if isinstance(media, dict):
        media_mime = media.get("mime_type") or media.get("content_type")
    parsed, meta, attempts = _mistral_annotate(
        path=file_path,
        schema=schema,
        schema_name=schema_name,
        prompt=prompt,
        mime_type=str(media_mime) if media_mime else None,
    )
    annotation = _parse_annotation(parsed)
    if not annotation:
        _bump("needs_review")
        envelope["processing"]["status"] = "needs_review"
        envelope["error"] = str(meta.error or "annotation_missing")
        return {
            "ok": False,
            "extraction_status": "needs_review",
            "extraction_error": str(meta.error or "annotation_missing"),
            "authoritative": False,
            "hr_confirmation_required": True,
            "gpt_used": False,
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
            "channel": channel,
            "envelope": envelope,
            "attempts": attempts,
            "cost_usd": float(meta.estimated_cost_usd or 0.0),
            "latency_ms": int(meta.latency_ms or 0),
            "content_sha256": content_sha,
        }

    fields = (
        _materialize_bank_certificate(annotation, country_code=country_code)
        if is_bank
        else (
            _materialize_contract(annotation, country_code=country_code)
            if is_contract
            else _materialize_compliance(annotation, country_code=country_code, expected_type=doc_type)
        )
    )
    if expected_item and mode == "verify":
        detected = _null_if_blank((fields.get("document_type") or {}).get("value")) or "unknown"
        matches = detected == normalize_document_type(expected_item) or (
            normalize_document_type(expected_item) == "education_cert" and detected == "education_cert"
        )
    else:
        detected = _null_if_blank((fields.get("document_type") or {}).get("value")) or doc_type
        matches = None

    validation = (
        {"ok": True, "issues": [], "bank_certificate": True}
        if is_bank
        else validate_common_fields(fields, expected_type=doc_type)
    )
    try:
        confidence = float(annotation.get("overall_confidence") or 0)
    except Exception:
        confidence = 0.0
    if is_bank:
        iban_v = (fields.get("iban") or {}).get("value")
        holder_v = (fields.get("account_holder") or {}).get("value")
        bank_v = (fields.get("bank_name") or {}).get("value")
        has_core = bool(iban_v) or bool((fields.get("account_number") or {}).get("value"))
        if has_core and confidence >= 0.45 and (holder_v or bank_v or iban_v):
            status = "extracted"
        elif has_core:
            status = "partial"
        else:
            status = "low_confidence" if confidence > 0 else "failed"
    else:
        status = "extracted" if confidence >= 0.55 else "low_confidence"
    if mode == "verify" and matches is False and confidence >= 0.65:
        status = "mismatch"
    if mode == "classify":
        return {
            "detected_item": detected,
            "confidence": confidence,
            "reason": status,
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
            "gpt_used": False,
            "channel": channel,
            "extraction_status": status,
        }
    if mode == "verify":
        return {
            "matches_expected_item": bool(matches),
            "detected_item": detected,
            "confidence": confidence,
            "reason": status,
            "provider": "mistral",
            "model": MISTRAL_OCR_MODEL_PIN,
            "gpt_used": False,
            "channel": channel,
            "extraction_status": status,
            "fields": fields,
        }

    envelope["processing"]["status"] = status
    envelope["processing"]["validation"] = validation
    envelope["processing"]["confidence"] = confidence

    legacy = {
        "document_type": (fields.get("document_type") or {}).get("value") or doc_type,
        "document_number": (fields.get("document_number") or {}).get("value"),
        "issued_date": (fields.get("issue_date") or {}).get("value"),
        "expiry_date": (fields.get("expiry_date") or {}).get("value"),
        "full_name": (fields.get("full_name") or {}).get("value"),
        "nationality": None,
        "date_of_birth": None,
        "confidence": confidence,
        "extraction_status": status,
        "provider": "mistral",
        "model": MISTRAL_OCR_MODEL_PIN,
        "gpt_used": False,
        "authoritative": False,
        "hr_confirmation_required": True,
        "country_code": (fields.get("country_code") or {}).get("value"),
        "issuing_authority": (fields.get("issuing_authority") or {}).get("value"),
        "jurisdiction": (fields.get("jurisdiction") or {}).get("value"),
        "employer_or_sponsor": (fields.get("employer_or_sponsor") or {}).get("value"),
        "renewal_required": (fields.get("renewal_required") or {}).get("value"),
        "fields": fields,
        "validation": validation,
        "envelope": envelope,
        "content_sha256": content_sha,
        "channel": channel,
        "duplicate_keys": duplicate_keys(
            content_sha256=content_sha,
            document_type=doc_type,
            document_number=(fields.get("document_number") or {}).get("value"),
            company_code=company_code,
        ),
        "cost_usd": float(meta.estimated_cost_usd or 0.0),
        "latency_ms": int(meta.latency_ms or 0),
    }
    # Parsed dates for receipt dual-write compatibility
    from identity_document_extraction import _parse_iso_date

    legacy["issued_date_parsed"] = _parse_iso_date(legacy.get("issued_date"))
    legacy["expiry_date_parsed"] = _parse_iso_date(legacy.get("expiry_date"))
    return legacy


def classify_document(**kwargs: Any) -> dict[str, Any]:
    return process_document(mode="classify", **kwargs)


def verify_document(**kwargs: Any) -> dict[str, Any]:
    return process_document(mode="verify", **kwargs)


def extract_document(**kwargs: Any) -> dict[str, Any]:
    return process_document(mode="extract", **kwargs)
