"""Candidate WhatsApp natural-language intent router (GPT-5.6 Luna).

Deterministic handlers remain first for APPLY codes, attachments, pending
confirmations, and secure tokens. This module is called only after those
paths do not resolve the message. It never mutates application state.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

MODEL_ID = "gpt-5.6-luna"
PROMPT_VERSION = "candidate_intent_prompt_v1"
SCHEMA_VERSION = "candidate_intent_v1"
CATALOG_VERSION = "candidate_flow_v1"
CONFIDENCE_THRESHOLD = 0.80

# USD per 1M tokens (OpenAI GPT-5.6 Luna list pricing, July 2026).
INPUT_USD_PER_1M = 1.0
OUTPUT_USD_PER_1M = 6.0

INTENTS = frozenset(
    {
        "apply_role",
        "replace_cv",
        "cv_received",
        "status",
        "withdraw",
        "confirm_withdraw",
        "cancel_withdraw",
        "hr_handoff",
        "assessment",
        "interview",
        "offer",
        "unknown",
    }
)

SYSTEM_PROMPT = """You are Wathefni's candidate WhatsApp intent router.
Classify the candidate message only. Do not invent roles, applications, scores, or decisions.
Do not mutate state. Do not claim a CV was accepted or a message was delivered.
Return JSON only that matches the schema.

Supported intents:
- apply_role: wants to apply for a named role (not a full APPLY code)
- replace_cv: wants to replace/update/resend CV
- cv_received: asking whether CV was received
- status: asking about application status
- withdraw: wants to withdraw application
- confirm_withdraw: confirming a pending withdrawal
- cancel_withdraw: cancelling a pending withdrawal
- hr_handoff: wants to speak to HR/human/recruiter
- assessment: asking about assessment/test/link
- interview: asking about interview
- offer: asking about employment offer
- unknown: ambiguous, multi-intent conflict, or unclear

Languages: English, Modern Standard Arabic, Kuwaiti/Gulf Arabic, Arabizi, mixed Arabic/English.
Tolerate spelling mistakes and short messages.
If multiple intents compete or confidence is low, set intent=unknown and needs_clarification=true.
Never invent an APPLY code or role title that is not evidenced in the message.
"""

JSON_SCHEMA: dict[str, Any] = {
    "name": "candidate_intent_v1",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "enum": sorted(INTENTS),
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "language": {"type": "string", "enum": ["en", "ar"]},
            "apply_code": {"type": ["string", "null"]},
            "role_text": {"type": ["string", "null"]},
            "confirmation": {"type": "string", "enum": ["confirm", "cancel", "none"]},
            "needs_clarification": {"type": "boolean"},
            "clarification_reason": {"type": ["string", "null"]},
            "secondary_intents": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(INTENTS)},
            },
        },
        "required": [
            "intent",
            "confidence",
            "language",
            "apply_code",
            "role_text",
            "confirmation",
            "needs_clarification",
            "clarification_reason",
            "secondary_intents",
        ],
    },
}


def estimate_cost_usd(*, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    inp = float(input_tokens or 0)
    out = float(output_tokens or 0)
    return round((inp * INPUT_USD_PER_1M + out * OUTPUT_USD_PER_1M) / 1_000_000.0, 8)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_model_text(parsed: dict[str, Any]) -> str:
    if not isinstance(parsed, dict):
        return ""
    output_text = parsed.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for item in parsed.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
        if item.get("type") == "output_text" and isinstance(item.get("text"), str):
            return item["text"]
    choices = parsed.get("choices") if isinstance(parsed.get("choices"), list) else []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _usage(parsed: dict[str, Any] | None) -> dict[str, Any]:
    usage = (parsed or {}).get("usage") if isinstance((parsed or {}).get("usage"), dict) else {}
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    return {
        "response_id": (parsed or {}).get("id") or (parsed or {}).get("response_id"),
        "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
        "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
        "cached_tokens": input_details.get("cached_tokens") or input_details.get("cache_read_input_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    intent = str(raw.get("intent") or "unknown").strip().lower()
    if intent not in INTENTS:
        intent = "unknown"
    try:
        confidence = float(raw.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    language = "ar" if str(raw.get("language") or "").strip().lower().startswith("ar") else "en"
    confirmation = str(raw.get("confirmation") or "none").strip().lower()
    if confirmation not in {"confirm", "cancel", "none"}:
        confirmation = "none"
    secondary = [
        str(item).strip().lower()
        for item in (raw.get("secondary_intents") or [])
        if str(item).strip().lower() in INTENTS and str(item).strip().lower() != intent
    ]
    needs_clarification = bool(raw.get("needs_clarification")) or confidence < CONFIDENCE_THRESHOLD or intent == "unknown" or len(secondary) > 0
    apply_code = str(raw.get("apply_code") or "").strip().upper() or None
    role_text = str(raw.get("role_text") or "").strip() or None
    clarification_reason = str(raw.get("clarification_reason") or "").strip() or None
    if needs_clarification and not clarification_reason:
        if confidence < CONFIDENCE_THRESHOLD:
            clarification_reason = "low_confidence"
        elif len(secondary) > 0:
            clarification_reason = "multi_intent"
        else:
            clarification_reason = "unknown_or_ambiguous"
    return {
        "intent": intent if not needs_clarification else ("unknown" if intent == "unknown" else intent),
        "accepted_intent": None if needs_clarification else intent,
        "confidence": confidence,
        "language": language,
        "apply_code": apply_code,
        "role_text": role_text,
        "confirmation": confirmation,
        "needs_clarification": needs_clarification,
        "clarification_reason": clarification_reason,
        "secondary_intents": secondary,
        "threshold": CONFIDENCE_THRESHOLD,
        "model": MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def classify_candidate_intent(
    text: str,
    *,
    provider: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    timeout: int = 12,
) -> dict[str, Any]:
    """Classify natural-language candidate intent. Never mutates state."""
    raw_text = str(text or "").strip()
    if not raw_text:
        return {
            "ok": False,
            "error": "empty_text",
            "needs_clarification": True,
            "accepted_intent": None,
            "intent": "unknown",
            "confidence": 0.0,
            "language": "en",
            "model": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "threshold": CONFIDENCE_THRESHOLD,
        }
    if not provider or not provider.get("api_key") or not provider.get("url"):
        return {
            "ok": False,
            "error": "provider_unavailable",
            "needs_clarification": True,
            "accepted_intent": None,
            "intent": "unknown",
            "confidence": 0.0,
            "language": "en",
            "model": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "threshold": CONFIDENCE_THRESHOLD,
        }

    user_payload = {
        "candidate_message": raw_text,
        "context": context or {},
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
    model = MODEL_ID
    api_kind = str(provider.get("api") or "openai-responses")
    if api_kind == "openai-responses":
        body: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": JSON_SCHEMA["name"],
                    "strict": True,
                    "schema": JSON_SCHEMA["schema"],
                }
            },
        }
    else:
        body = {
            "model": model,
            "response_format": {
                "type": "json_schema",
                "json_schema": JSON_SCHEMA,
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

    req = urllib.request.Request(
        provider["url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=max(5, int(timeout))) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
        latency_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "error": f"llm_error:{exc}",
            "needs_clarification": True,
            "accepted_intent": None,
            "intent": "unknown",
            "confidence": 0.0,
            "language": "en",
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "threshold": CONFIDENCE_THRESHOLD,
            "latency_ms": latency_ms,
            "provider": provider.get("provider"),
            "api": provider.get("api"),
        }

    usage = _usage(parsed if isinstance(parsed, dict) else {})
    content = _extract_model_text(parsed if isinstance(parsed, dict) else {})
    extracted = _extract_json_object(content) or {}
    # Some Responses payloads nest parsed JSON under content.parsed.
    if not extracted and isinstance(parsed, dict):
        for item in parsed.get("output") or []:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict) and isinstance(part.get("parsed"), dict):
                    extracted = part["parsed"]
                    break

    normalized = _normalize_result(extracted if isinstance(extracted, dict) else {})
    cost = estimate_cost_usd(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
    return {
        "ok": True,
        "error": None,
        **normalized,
        "latency_ms": latency_ms,
        "response_id": usage.get("response_id"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cached_tokens": usage.get("cached_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "estimated_cost_usd": cost,
        "provider": provider.get("provider"),
        "api": provider.get("api"),
        "raw": extracted,
    }


def clarification_template_key() -> str:
    return "intent_clarification"


def should_accept(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return False
    if result.get("needs_clarification"):
        return False
    try:
        confidence = float(result.get("confidence") or 0)
    except Exception:
        return False
    intent = str(result.get("accepted_intent") or "")
    return confidence >= CONFIDENCE_THRESHOLD and intent in INTENTS and intent != "unknown"
