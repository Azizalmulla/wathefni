"""Assistant-layer policy helpers (Ranking replay, Reports boundary, correlation).

Does not modify Ranking / Reports computation authorities — only how the Assistant
invokes and describes them.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

ASSISTANT_RANKING_MODE_ENV = "WATHEFNI_ASSISTANT_RANKING_MODE"
DEFAULT_ASSISTANT_RANKING_MODE = "replay_only"

REPORTS_METRIC_QUESTIONS = re.compile(
    r"\b("
    r"time\s+to\s+hire|conversion\s+rate|funnel|hiring\s+speed|"
    r"source\s+perform|which\s+source|slowing\s+down\s+hiring|"
    r"report\s+stamp|reports?\s+v1|metrics?\s+for\s+hiring|"
    r"how\s+is\s+hiring\s+doing|hiring\s+performance|"
    r"follow[- ]?up\s+this\s+month|this\s+month.?s?\s+follow"
    r")\b"
    r"|"
    r"(معدل\s+التحول|سرعة\s+التوظيف|القمع|مصدر\s+الأداء|"
    r"ما\s+الذي\s+يبطئ|تقرير\s+التوظيف)",
    re.I | re.S,
)

OVERVIEW_OK_QUESTIONS = re.compile(
    r"\b("
    r"work\s*queue|what\s+should\s+i\s+(do|work\s+on)|"
    r"ready\s+for\s+review\s+now|who\s+needs\s+attention\s+now|"
    r"priorit(?:y|ies)\s+today|action\s+counts?"
    r")\b",
    re.I | re.S,
)


def assistant_ranking_mode() -> str:
    raw = (os.environ.get(ASSISTANT_RANKING_MODE_ENV) or DEFAULT_ASSISTANT_RANKING_MODE).strip().lower()
    if raw in {"replay_only", "allow_recalculate"}:
        return raw
    return DEFAULT_ASSISTANT_RANKING_MODE


def legacy_regex_inference_enabled() -> bool:
    return (os.environ.get("WATHEFNI_LEGACY_REGEX_INFERENCE_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def legacy_path_inactive_evidence() -> dict[str, Any]:
    """Startup/runtime evidence that Admin chat uses toolcall, not legacy regex."""
    return {
        "legacy_regex_inference_enabled": legacy_regex_inference_enabled(),
        "expected_disabled": True,
        "admin_chat_entry": "handle_toolcall_whatsapp_turn",
        "legacy_classify_gated": True,
        "inactive": not legacy_regex_inference_enabled(),
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def new_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex}"


def is_reports_metric_question(text: str | None) -> bool:
    return bool(REPORTS_METRIC_QUESTIONS.search(str(text or "")))


def is_overview_operational_question(text: str | None) -> bool:
    return bool(OVERVIEW_OK_QUESTIONS.search(str(text or "")))


def reports_parity_unavailable_message(*, locale_hint: str = "en") -> dict[str, Any]:
    ar = locale_hint == "ar"
    return {
        "action_type": "get_reports_metrics",
        "success": False,
        "status": "reports_tool_unavailable",
        "error": "reports_tool_unavailable",
        "reports_boundary": True,
        "message": (
            "هذا سؤال تقارير أداء التوظيف. افتح صفحة Reports في لوحة التحكم. "
            "أرقام Overview ليست Reports ولا يجوز اختراع المقاييس."
            if ar
            else "That is a hiring Reports question. Open the Reports page in the dashboard. "
            "Overview work-queue counts are not Reports — do not invent metrics."
        ),
        "authority": "reports-metrics-v1",
        "overview_is_not_reports": True,
        "navigation_hint": {"type": "page", "page": "reports", "label": "Open Reports" if not ar else "فتح التقارير"},
    }


def general_guidance_prefix(*, locale_hint: str = "en") -> str:
    if locale_hint == "ar":
        return "إرشاد عام (وليس من بيانات شركتك): "
    return "General guidance (not from your company records): "


def mint_outbound_confirmation_token(
    *,
    tool_name: str,
    company_code: str,
    app_key: str,
    action_hash: str,
    lifecycle_version: int,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    request_hash = hashlib.sha256(
        f"{company_code}|{app_key}|{tool_name}|{action_hash}|v{lifecycle_version}".encode()
    ).hexdigest()
    return {
        "confirmation_id": f"out_{uuid.uuid4().hex[:16]}",
        "confirmation_token": token,
        "request_hash": request_hash,
        "tool_name": tool_name,
        "app_key": app_key,
        "company_code": company_code,
        "observed_lifecycle_version": int(lifecycle_version),
        "outbound": True,
    }
