"""Platform Assistant Wave 1 — Spine Contract (staging foundation).

One shared assistant foundation for WATHEFNI, HR dashboard-first.
Kill switches, module registration, grounded envelopes, audit events,
EN/AR fallbacks, and read-only Action Inbox / Employees 360 / Setup readiness.

Does NOT: mutate records, embed AI in frozen module UIs, wire Candidate Knowledge,
widen WhatsApp, enable manager/employee assistants, Payroll money, or Attendance ingest.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

WAVE1_VERSION = "1.0.0"
WAVE1_CONTRACT = "platform_assistant_spine_wave1"
ALLOWED_COMPANY = "WATHEFNI"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")

# Read-only Wave 1 tools (no confirmation, no SoA mutation).
WAVE1_READ_TOOLS = frozenset(
    {
        "summarize_action_inbox",
        "summarize_employee_360",
        "get_launch_readiness_summary",
    }
)

AUTHORITY_LABELS = (
    "live",
    "synthetic",
    "preview_non_authoritative",
    "blocked",
    "missing",
    "stale",
    "partial",
    "unavailable",
    "read_only_compose",
)

FALLBACKS: dict[str, dict[str, str]] = {
    "missing": {
        "en": "That information is not available yet. I can help you open the right place to complete it.",
        "ar": "هذه المعلومات غير متوفرة بعد. يمكنني توجيهك إلى المكان المناسب لإكمالها.",
    },
    "stale": {
        "en": "This data may be stale. Refresh from the system of record before deciding.",
        "ar": "قد تكون هذه البيانات قديمة. حدّث من نظام السجل قبل اتخاذ قرار.",
    },
    "partial": {
        "en": "I only have a partial view. Some sources were unavailable or blocked.",
        "ar": "لديّ رؤية جزئية فقط. بعض المصادر غير متاحة أو محظورة.",
    },
    "unavailable": {
        "en": "I cannot answer that with grounded company data right now.",
        "ar": "لا أستطيع الإجابة ببيانات شركة موثوقة في الوقت الحالي.",
    },
    "blocked": {
        "en": "This is blocked by permissions, allowlists, or a safety freeze. I will not bypass it.",
        "ar": "هذا محظور بسبب الصلاحيات أو قوائم السماح أو تجميد السلامة. لن أتجاوزه.",
    },
    "unsupported": {
        "en": "That action is unsupported. Wathefni does not process pay money or turn on device attendance ingest from the assistant.",
        "ar": "هذا الإجراء غير مدعوم. وظفني لا يعالج أموال الرواتب ولا يفعّل استقبال أجهزة الحضور من المساعد.",
    },
    "killed": {
        "en": "The assistant is temporarily unavailable (kill switch).",
        "ar": "المساعد غير متاح مؤقتاً (مفتاح الإيقاف).",
    },
    "mutations_killed": {
        "en": "Mutations are disabled for this assistant session. I can summarize, explain, investigate, and prepare a deep link only.",
        "ar": "التعديلات معطّلة في هذه الجلسة. يمكنني التلخيص والشرح والتحقق وتجهيز رابط فقط.",
    },
    "tenant_denied": {
        "en": "This assistant spine is limited to the WATHEFNI company on the HR dashboard.",
        "ar": "عمود المساعد هذا مقتصر على شركة WATHEFNI ولوحة الموارد البشرية.",
    },
    "whatsapp_denied": {
        "en": "Wave 1 spine tools are HR dashboard only — not WhatsApp.",
        "ar": "أدوات الموجة 1 للوحة الموارد البشرية فقط — وليس واتساب.",
    },
}


def _flag_on(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _flag_off(name: str, default: str = "off") -> bool:
    return os.environ.get(name, default).strip().lower() in {"0", "false", "no", "off", ""}


def platform_assistant_wave1_enabled() -> bool:
    return _flag_on("WATHEFNI_PLATFORM_ASSISTANT_WAVE1")


def assistant_kill_engaged() -> bool:
    """Master AI kill — all LLM assistant turns stop."""
    return _flag_on("WATHEFNI_ASSISTANT_KILL")


def assistant_mutations_allowed() -> bool:
    """Separate mutation kill. Wave 1 default = mutations OFF when unset."""
    raw = os.environ.get("WATHEFNI_ASSISTANT_MUTATIONS")
    if raw is None or str(raw).strip() == "":
        # Spine Wave 1: prove no mutation path — default deny mutations when wave on.
        if platform_assistant_wave1_enabled():
            return False
        return True
    return _flag_on("WATHEFNI_ASSISTANT_MUTATIONS")


def wave1_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES") or ALLOWED_COMPANY).strip()
    return {part.strip().upper() for part in raw.split(",") if part.strip()} or {ALLOWED_COMPANY}


def wave1_enabled_for_company(company_code: str | None) -> bool:
    if not platform_assistant_wave1_enabled():
        return False
    company = str(company_code or "").strip().upper()
    if company != ALLOWED_COMPANY:
        return False
    allowed = wave1_companies()
    return company in allowed


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": WAVE1_CONTRACT,
        "wave1_version": WAVE1_VERSION,
        "wathefni_only": True,
        "hr_dashboard_only": True,
        "manager_assistant": False,
        "employee_assistant": False,
        "whatsapp_widening": False,
        "mobile_assistant": False,
        "candidate_knowledge_wired": False,
        "ai_embedded_in_frozen_module_uis": False,
        "new_mutation_tools": False,
        "mutates_records": False,
        "payroll_money": False,
        "attendance_ingest": False,
        "capture_ingest_must_remain_off": True,
        "legal_government_authority": False,
        "default_posthire_entry": "action_inbox",
        "may": ["summarize", "explain", "investigate", "prepare_deep_link_or_proposed_action"],
        "must_not": [
            "mutate_records",
            "bypass_confirmation_permissions_sod_allowlists_freezes",
            "payroll_money",
            "attendance_ingest",
            "claim_legal_or_government_authority",
        ],
    }


# --- Module registration contract -------------------------------------------------


ModuleRegistrar = Callable[[], dict[str, Any]]

_MODULE_CONTRACTS: dict[str, dict[str, Any]] = {}


def register_module_contract(contract: dict[str, Any]) -> dict[str, Any]:
    key = str(contract.get("module_key") or "").strip()
    if not key:
        raise ValueError("module_key required")
    _MODULE_CONTRACTS[key] = contract
    return contract


def list_module_contracts() -> list[dict[str, Any]]:
    return [dict(v) for _, v in sorted(_MODULE_CONTRACTS.items())]


def get_module_contract(module_key: str) -> dict[str, Any] | None:
    row = _MODULE_CONTRACTS.get(module_key)
    return dict(row) if row else None


def _base_contract(
    *,
    module_key: str,
    label_en: str,
    label_ar: str,
    tools: list[str],
    read_only: bool = True,
    mutates: bool = False,
    ai_in_product_ui: bool = False,
    deep_link: dict[str, Any] | None = None,
    kill_class: str = "platform_assistant_wave1",
) -> dict[str, Any]:
    return {
        "module_key": module_key,
        "version": WAVE1_VERSION,
        "label_en": label_en,
        "label_ar": label_ar,
        "honesty": {
            "read_only": read_only,
            "mutates_records": mutates,
            "ai_in_product_ui": ai_in_product_ui,
            "payroll_money": False,
            "attendance_ingest": False,
            "legal_government_authority": False,
        },
        "tools": list(tools),
        "read_capabilities": list(tools),
        "mutation_capabilities": [],
        "deep_links": deep_link or {},
        "fallbacks": {k: dict(v) for k, v in FALLBACKS.items()},
        "citation_kinds": ["module_record", "as_of", "authority_state", "deep_link"],
        "kill_class": kill_class,
    }


def ensure_default_module_contracts() -> None:
    if _MODULE_CONTRACTS:
        return
    register_module_contract(
        _base_contract(
            module_key="action_inbox",
            label_en="Unified Action Inbox",
            label_ar="صندوق الإجراءات الموحّد",
            tools=["summarize_action_inbox"],
            deep_link={"page": "action_inbox", "path": "/dashboard/posthire?tab=action-inbox"},
        )
    )
    register_module_contract(
        _base_contract(
            module_key="employees_360",
            label_en="Employees 360",
            label_ar="الموظفون 360",
            tools=["summarize_employee_360"],
            deep_link={"page": "employees", "path": "/dashboard/posthire?tab=employees"},
        )
    )
    register_module_contract(
        _base_contract(
            module_key="setup_console",
            label_en="Setup Console Launch Readiness",
            label_ar="جاهزية الإطلاق (إعداد الشركة)",
            tools=["get_launch_readiness_summary"],
            deep_link={"page": "setup_launch_readiness", "path": "/setup-console"},
        )
    )


ensure_default_module_contracts()


# --- Grounding envelope -----------------------------------------------------------


def kuwait_now_iso() -> str:
    return datetime.now(KUWAIT_TZ).isoformat()


def grounded_envelope(
    *,
    ok: bool,
    summary_en: str,
    summary_ar: str,
    citations: list[dict[str, Any]] | None = None,
    authority_state: str = "read_only_compose",
    data_freshness: str | None = None,
    confidence: str = "grounded",
    deep_links: list[dict[str, Any]] | None = None,
    proposed_actions: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    fallback_key: str | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    if authority_state not in AUTHORITY_LABELS and authority_state:
        # Allow module-specific labels but keep a canonical field.
        pass
    as_of = data_freshness or kuwait_now_iso()
    fb = FALLBACKS.get(fallback_key or "", {})
    message = summary_en if locale != "ar" else summary_ar
    if fallback_key and fb:
        message = fb.get("ar" if locale == "ar" else "en", message)
    return {
        "ok": bool(ok),
        "wave1_contract": WAVE1_CONTRACT,
        "summary_en": summary_en,
        "summary_ar": summary_ar,
        "message": message,
        "citations": citations or [],
        "data_freshness": as_of,
        "as_of_tz": "Asia/Kuwait",
        "authority_state": authority_state,
        "confidence": confidence,  # grounded | partial | unavailable
        "deep_links": deep_links or [],
        "proposed_actions": proposed_actions or [],  # prepare only — never executed here
        "payload": payload or {},
        "fallback_key": fallback_key,
        "honesty": honesty_payload(),
        "mutates_records": False,
    }


def fallback_envelope(key: str, *, locale: str = "en", **extra: Any) -> dict[str, Any]:
    fb = FALLBACKS.get(key) or FALLBACKS["unavailable"]
    return grounded_envelope(
        ok=False,
        summary_en=fb["en"],
        summary_ar=fb["ar"],
        authority_state="blocked" if key in {"blocked", "tenant_denied", "killed", "mutations_killed"} else "unavailable",
        confidence="unavailable",
        fallback_key=key,
        locale=locale,
        **extra,
    )


# --- Audit events -----------------------------------------------------------------


def ensure_assistant_spine_audit_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_spine_events (
            event_id UUID PRIMARY KEY,
            company_code TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'staging',
            event_type TEXT NOT NULL,
            channel TEXT,
            actor_ref TEXT,
            turn_id TEXT,
            tool_name TEXT,
            detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS assistant_spine_events_company_created_idx
        ON assistant_spine_events (company_code, created_at DESC)
        """
    )


def record_assistant_event(
    cur: Any | None,
    *,
    company_code: str,
    event_type: str,
    channel: str | None = None,
    actor_ref: str | None = None,
    turn_id: str | None = None,
    tool_name: str | None = None,
    detail: dict[str, Any] | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    env = environment or os.environ.get("WATHEFNI_ENV") or "staging"
    row = {
        "event_id": event_id,
        "company_code": str(company_code or "").upper(),
        "environment": env,
        "event_type": event_type,
        "channel": channel,
        "actor_ref": actor_ref,
        "turn_id": turn_id,
        "tool_name": tool_name,
        "detail": detail or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if cur is None:
        return row
    cur.execute(
        """
        INSERT INTO assistant_spine_events
            (event_id, company_code, environment, event_type, channel, actor_ref, turn_id, tool_name, detail)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            event_id,
            row["company_code"],
            env,
            event_type,
            channel,
            actor_ref,
            turn_id,
            tool_name,
            json.dumps(detail or {}, default=str),
        ),
    )
    return row


# --- Channel / actor helpers ------------------------------------------------------


def _locale_from_request(request: Any) -> str:
    metadata = getattr(request, "metadata", None) if isinstance(getattr(request, "metadata", None), dict) else {}
    if str(metadata.get("locale") or "").lower().startswith("ar"):
        return "ar"
    text = str(getattr(request, "raw_text", "") or "")
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        return "ar"
    return "en"


def _is_dashboard_channel(request: Any) -> bool:
    metadata = getattr(request, "metadata", None) if isinstance(getattr(request, "metadata", None), dict) else {}
    channel = str(metadata.get("channel") or "").strip()
    return channel == "web_dashboard" or bool(metadata.get("dashboard"))


def _actor_ref(request: Any, scope: dict[str, Any] | None = None) -> str:
    metadata = getattr(request, "metadata", None) if isinstance(getattr(request, "metadata", None), dict) else {}
    admin = metadata.get("admin_user") if isinstance(metadata.get("admin_user"), dict) else {}
    access = metadata.get("access") if isinstance(metadata.get("access"), dict) else {}
    for key in ("user_id", "id", "phone"):
        if admin.get(key):
            return str(admin.get(key))
    if access.get("actor_user_id"):
        return str(access.get("actor_user_id"))
    if scope and scope.get("admin_user_id"):
        return str(scope.get("admin_user_id"))
    return "unknown"


def _permissions_from_ctx(ctx: Any) -> set[str]:
    scope_perms = set()
    try:
        meta = getattr(ctx.request, "metadata", None)
        if isinstance(meta, dict):
            scope_perms |= {str(p) for p in (meta.get("permissions") or []) if str(p).strip()}
    except Exception:
        pass
    try:
        action = ctx.action if isinstance(ctx.action, dict) else {}
        scope_perms |= {str(p) for p in (action.get("permissions") or []) if str(p).strip()}
    except Exception:
        pass
    return scope_perms


def _perm_ok(perms: set[str], required: str) -> bool:
    if not perms:
        # Dashboard empty-state may omit perms; fail closed for spine tools when wave1 strict.
        return False
    if required in perms or "*:*" in perms:
        return True
    if required.endswith(".read") and required.replace(".read", ".manage") in perms:
        return True
    # Soft aliases
    if required == "employees.read" and ("employee.read" in perms or "employees.manage" in perms or "employee.manage" in perms):
        return True
    if required == "action_inbox.read" and (
        "analytics.read" in perms or "compliance.read" in perms or "employees.read" in perms or "employee.read" in perms
    ):
        return True
    return False


def spine_preflight(ctx: Any, *, required_permission: str) -> dict[str, Any] | None:
    """Return a denial envelope or None if the Wave 1 tool may run."""
    locale = _locale_from_request(ctx.request)
    company = str((ctx.action or {}).get("company_code") or "").upper()
    if assistant_kill_engaged():
        return fallback_envelope("killed", locale=locale)
    if not wave1_enabled_for_company(company):
        return fallback_envelope("tenant_denied", locale=locale)
    if not _is_dashboard_channel(ctx.request):
        return fallback_envelope("whatsapp_denied", locale=locale)
    perms = _permissions_from_ctx(ctx)
    if not _perm_ok(perms, required_permission):
        return fallback_envelope("blocked", locale=locale, payload={"required_permission": required_permission})
    return None


# --- Read-only tool executors -----------------------------------------------------


def execute_summarize_action_inbox(ctx: Any) -> dict[str, Any]:
    locale = _locale_from_request(ctx.request)
    denied = spine_preflight(ctx, required_permission="action_inbox.read")
    if denied:
        return _tool_result("summarize_action_inbox", denied)

    legacy = ctx.legacy
    company = str((ctx.action or {}).get("company_code") or ALLOWED_COMPANY).upper()
    try:
        import action_inbox_wave1 as inbox
    except Exception as exc:
        env = fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]})
        return _tool_result("summarize_action_inbox", env)

    if not inbox.action_inbox_wave1_enabled_for_company(company):
        env = fallback_envelope(
            "blocked",
            locale=locale,
            payload={"reason": "action_inbox_disabled_for_company"},
            deep_links=[{"page": "action_inbox", "label_en": "Open Action Inbox", "label_ar": "فتح صندوق الإجراءات"}],
        )
        return _tool_result("summarize_action_inbox", env)

    # Prefer live dashboard composer when actor context is available.
    pack: dict[str, Any] | None = None
    try:
        meta = getattr(ctx.request, "metadata", None) if isinstance(getattr(ctx.request, "metadata", None), dict) else {}
        context = {
            "company_code": company,
            "admin_user": meta.get("admin_user") or {},
            "access": meta.get("access") or {},
            "permissions": list(_permissions_from_ctx(ctx)),
            "hr_user": (meta.get("admin_user") or {}),
        }
        if hasattr(legacy, "dashboard_action_inbox_payload"):
            pack = legacy.dashboard_action_inbox_payload(context)
    except Exception as exc:
        # Soft-fail into empty compose with honesty — still grounded as partial/unavailable.
        pack = None
        compose_error = str(exc)[:240]
    else:
        compose_error = None

    if not isinstance(pack, dict):
        # Offline-safe empty compose (still proves contract / deep link prepare).
        pack = inbox.build_action_inbox(
            analytics_attention=[],
            compliance_findings=[],
            e360_next_actions=[],
            sources_meta={"assistant_wave1": True, "compose_error": compose_error},
            apply_phase0_filters=True,
        )
        authority = "partial" if compose_error else "missing"
        confidence = "partial" if compose_error else "unavailable"
        summary_en = FALLBACKS["partial"]["en"] if compose_error else (
            "Action Inbox is the default post-hire entry. No ranked items are available from live sources right now."
        )
        summary_ar = FALLBACKS["partial"]["ar"] if compose_error else (
            "صندوق الإجراءات هو مدخل ما بعد التوظيف الافتراضي. لا توجد عناصر مرتّبة من مصادر حية الآن."
        )
        env = grounded_envelope(
            ok=True,
            summary_en=summary_en,
            summary_ar=summary_ar,
            authority_state=authority,
            confidence=confidence,
            fallback_key="partial" if compose_error else "missing",
            locale=locale,
            citations=[
                {
                    "kind": "module_contract",
                    "module": "action_inbox",
                    "id": inbox.ACTION_INBOX_WAVE1_CONTRACT,
                    "label_en": "Unified Action Inbox",
                    "label_ar": "صندوق الإجراءات الموحّد",
                    "as_of": kuwait_now_iso(),
                }
            ],
            deep_links=[
                {
                    "page": "action_inbox",
                    "path": "/dashboard/posthire?tab=action-inbox",
                    "label_en": "Open Unified Action Inbox",
                    "label_ar": "فتح صندوق الإجراءات الموحّد",
                }
            ],
            proposed_actions=[
                {
                    "kind": "deep_link",
                    "module": "action_inbox",
                    "label_en": "Review what needs attention in Action Inbox",
                    "label_ar": "راجع ما يحتاج انتباهاً في صندوق الإجراءات",
                    "deep_link": {"page": "action_inbox"},
                    "executes": False,
                }
            ],
            payload={"summary": pack.get("summary"), "honesty": pack.get("honesty"), "compose_error": compose_error},
        )
        return _tool_result("summarize_action_inbox", env)

    items = pack.get("items") if isinstance(pack.get("items"), list) else []
    summary = pack.get("summary") if isinstance(pack.get("summary"), dict) else {}
    total = int(summary.get("total") or len(items))
    top = items[:5]
    citations = []
    deep_links = [
        {
            "page": "action_inbox",
            "path": "/dashboard/posthire?tab=action-inbox",
            "label_en": "Open Unified Action Inbox",
            "label_ar": "فتح صندوق الإجراءات الموحّد",
        }
    ]
    proposed = []
    for item in top:
        if not isinstance(item, dict):
            continue
        citations.append(
            {
                "kind": "inbox_item",
                "module": item.get("source_module") or item.get("source_stream") or "action_inbox",
                "id": item.get("id"),
                "label_en": item.get("what_en") or item.get("reason_en") or item.get("id"),
                "label_ar": item.get("what_ar") or item.get("reason_ar") or item.get("id"),
                "as_of": pack.get("as_of") or kuwait_now_iso(),
                "authority_state": "read_only_compose",
                "deep_link": item.get("deep_link"),
            }
        )
        if item.get("deep_link"):
            proposed.append(
                {
                    "kind": "deep_link",
                    "module": item.get("source_module") or "action_inbox",
                    "label_en": item.get("what_en") or "Open in system of action",
                    "label_ar": item.get("what_ar") or "افتح في نظام التنفيذ",
                    "deep_link": item.get("deep_link"),
                    "executes": False,
                }
            )
            deep_links.append(
                {
                    "page": (item.get("deep_link") or {}).get("page"),
                    "label_en": item.get("what_en"),
                    "label_ar": item.get("what_ar"),
                    **(item.get("deep_link") if isinstance(item.get("deep_link"), dict) else {}),
                }
            )

    sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
    unavailable_sources = [
        name for name, meta in sources.items() if isinstance(meta, dict) and meta.get("status") in {"unavailable", "blocked", "missing"}
    ]
    if total == 0 and unavailable_sources:
        confidence = "partial"
        authority = "partial"
        summary_en = (
            f"Action Inbox has no ranked items right now. Some sources look unavailable: {', '.join(unavailable_sources)}."
        )
        summary_ar = (
            f"صندوق الإجراءات بلا عناصر مرتّبة الآن. بعض المصادر غير متاحة: {'، '.join(unavailable_sources)}."
        )
    elif total == 0:
        confidence = "grounded"
        authority = "read_only_compose"
        summary_en = "Action Inbox is clear — no ranked attention items right now."
        summary_ar = "صندوق الإجراءات فارغ — لا توجد عناصر انتباه مرتّبة الآن."
    else:
        confidence = "partial" if unavailable_sources else "grounded"
        authority = "partial" if unavailable_sources else "read_only_compose"
        summary_en = f"Action Inbox shows {total} item(s) needing attention. Top items are prepared as deep links only — modules remain systems of action."
        summary_ar = f"صندوق الإجراءات يعرض {total} عنصراً يحتاج انتباهاً. العناصر الأعلى مُجهّزة كروابط فقط — الوحدات تبقى أنظمة التنفيذ."

    as_of = pack.get("as_of") or pack.get("window_end") or kuwait_now_iso()
    env = grounded_envelope(
        ok=True,
        summary_en=summary_en,
        summary_ar=summary_ar,
        citations=citations,
        authority_state=authority,
        data_freshness=str(as_of),
        confidence=confidence,
        deep_links=deep_links[:8],
        proposed_actions=proposed[:5],
        locale=locale,
        payload={
            "summary": summary,
            "top_item_ids": [c.get("id") for c in citations],
            "honesty": pack.get("honesty") or inbox.honesty_payload(),
            "default_posthire_entry": True,
        },
    )
    return _tool_result("summarize_action_inbox", env)


def execute_summarize_employee_360(ctx: Any) -> dict[str, Any]:
    locale = _locale_from_request(ctx.request)
    perms = _permissions_from_ctx(ctx)
    if not (
        _perm_ok(perms, "employees.read")
        or _perm_ok(perms, "employee.read")
        or _perm_ok(perms, "employees.manage")
        or _perm_ok(perms, "employee.manage")
    ):
        # Still run channel/tenant/kill checks via spine_preflight
        denied = spine_preflight(ctx, required_permission="employees.read")
        return _tool_result("summarize_employee_360", denied or fallback_envelope("blocked", locale=locale))

    denied = spine_preflight(ctx, required_permission="employees.read")
    # spine_preflight may block on permission even when employee.read alias holds — override only permission part
    if denied and denied.get("fallback_key") == "blocked" and (
        _perm_ok(perms, "employee.read") or _perm_ok(perms, "employees.read")
    ):
        # Re-check non-permission gates only
        if assistant_kill_engaged():
            return _tool_result("summarize_employee_360", fallback_envelope("killed", locale=locale))
        company_chk = str((ctx.action or {}).get("company_code") or "").upper()
        if not wave1_enabled_for_company(company_chk):
            return _tool_result("summarize_employee_360", fallback_envelope("tenant_denied", locale=locale))
        if not _is_dashboard_channel(ctx.request):
            return _tool_result("summarize_employee_360", fallback_envelope("whatsapp_denied", locale=locale))
        denied = None
    if denied:
        return _tool_result("summarize_employee_360", denied)

    legacy = ctx.legacy
    company = str((ctx.action or {}).get("company_code") or ALLOWED_COMPANY).upper()
    action = ctx.action if isinstance(ctx.action, dict) else {}
    employee_key = str(action.get("employee_key") or action.get("subject_key") or "").strip()
    query = str(action.get("query") or action.get("employee_name") or action.get("subject_name") or "").strip()

    if not employee_key and not query:
        env = grounded_envelope(
            ok=False,
            summary_en="Tell me which employee to investigate (name or employee key).",
            summary_ar="أخبرني أي موظف أتحقق منه (الاسم أو مفتاح الموظف).",
            authority_state="missing",
            confidence="unavailable",
            fallback_key="missing",
            locale=locale,
            deep_links=[{"page": "employees", "path": "/dashboard/posthire?tab=employees"}],
            proposed_actions=[
                {
                    "kind": "deep_link",
                    "module": "employees_360",
                    "label_en": "Open Employees 360",
                    "label_ar": "فتح الموظفون 360",
                    "deep_link": {"page": "employees"},
                    "executes": False,
                }
            ],
        )
        return _tool_result("summarize_employee_360", env)

    profile: dict[str, Any] | None = None
    meta = getattr(ctx.request, "metadata", None) if isinstance(getattr(ctx.request, "metadata", None), dict) else {}
    access = meta.get("access") if isinstance(meta.get("access"), dict) else {}
    admin = meta.get("admin_user") if isinstance(meta.get("admin_user"), dict) else {}
    try:
        if not employee_key and query and hasattr(legacy, "list_employees_page"):
            page = legacy.list_employees_page(
                company,
                viewer_phone=str(admin.get("phone") or access.get("phone") or "") or None,
                dashboard_user_id=str(admin.get("user_id") or admin.get("id") or "") or None,
                actor_role=str(access.get("role") or admin.get("role") or "") or None,
                search=query,
                limit=5,
                offset=0,
            )
            rows = (page or {}).get("rows") or []
            if len(rows) > 1:
                env = grounded_envelope(
                    ok=False,
                    summary_en="Multiple employees match. Ask which one, then I can summarize.",
                    summary_ar="عدة موظفين يطابقون. حدّد من تقصد ثم ألخّص.",
                    authority_state="partial",
                    confidence="partial",
                    fallback_key="partial",
                    locale=locale,
                    payload={
                        "matches": [
                            {
                                "employee_key": r.get("employee_key"),
                                "name": r.get("full_name") or r.get("name"),
                            }
                            for r in rows[:5]
                        ]
                    },
                )
                return _tool_result("summarize_employee_360", env)
            if len(rows) == 1:
                employee_key = str(rows[0].get("employee_key") or "")
            if not employee_key:
                env = fallback_envelope("missing", locale=locale, deep_links=[{"page": "employees"}])
                return _tool_result("summarize_employee_360", env)

        if employee_key and hasattr(legacy, "dashboard_employee_profile"):
            context = {
                "company_code": company,
                "admin_user": admin,
                "access": access,
                "permissions": list(_permissions_from_ctx(ctx)),
                "hr_user": admin,
            }
            profile = legacy.dashboard_employee_profile(context, employee_key)
    except Exception as exc:
        env = fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]})
        return _tool_result("summarize_employee_360", env)

    if not isinstance(profile, dict) or not profile:
        env = fallback_envelope(
            "missing",
            locale=locale,
            deep_links=[{"page": "employees", "employee_key": employee_key or None}],
        )
        return _tool_result("summarize_employee_360", env)

    employee = profile.get("employee") if isinstance(profile.get("employee"), dict) else {}
    name = employee.get("full_name") or employee.get("name") or employee_key
    status = employee.get("employment_status") or employee.get("status") or "unknown"
    next_actions = profile.get("next_actions") if isinstance(profile.get("next_actions"), list) else []
    proposed = []
    for act in next_actions[:5]:
        if not isinstance(act, dict):
            continue
        proposed.append(
            {
                "kind": "deep_link",
                "module": act.get("module") or "employees_360",
                "label_en": act.get("title_en") or act.get("label") or act.get("title"),
                "label_ar": act.get("title_ar") or act.get("label_ar"),
                "deep_link": act.get("deep_link") or {"page": "employees", "employee_key": employee_key},
                "executes": False,
            }
        )

    summary_en = f"Employees 360 summary for {name}: status {status}. Prepared next steps are deep links only — no mutations."
    summary_ar = f"ملخص الموظفون 360 لـ {name}: الحالة {status}. الخطوات التالية روابط فقط — بدون تعديلات."
    env = grounded_envelope(
        ok=True,
        summary_en=summary_en,
        summary_ar=summary_ar,
        citations=[
            {
                "kind": "employee_record",
                "module": "employees_360",
                "id": employee.get("employee_key") or employee_key,
                "label_en": name,
                "label_ar": name,
                "as_of": kuwait_now_iso(),
                "authority_state": "live",
                "deep_link": {"page": "employees", "employee_key": employee.get("employee_key") or employee_key},
            }
        ],
        authority_state="live",
        confidence="grounded",
        locale=locale,
        deep_links=[{"page": "employees", "employee_key": employee.get("employee_key") or employee_key}],
        proposed_actions=proposed,
        payload={
            "employee_key": employee.get("employee_key") or employee_key,
            "status": status,
            "next_actions_count": len(next_actions),
            "redacted": True,
            "hr_mutate_enabled_ignored_by_assistant": True,
        },
    )
    return _tool_result("summarize_employee_360", env)


def execute_get_launch_readiness_summary(ctx: Any) -> dict[str, Any]:
    locale = _locale_from_request(ctx.request)
    # HR may read readiness honesty; Setup mutations remain operator-only / never offered.
    denied = spine_preflight(ctx, required_permission="settings.read")
    if denied:
        # Allow hr_admin-style broad perms
        perms = _permissions_from_ctx(ctx)
        if not (
            _perm_ok(perms, "settings.read")
            or _perm_ok(perms, "settings.manage")
            or _perm_ok(perms, "users.manage")
            or "hr_admin" in str(perms)
        ):
            # Soften: owners/hr often have prehire + posthire without settings.read — allow if any posthire read
            if not any(_perm_ok(perms, p) for p in ("employees.read", "employee.read", "leave.read", "analytics.read", "action_inbox.read")):
                return _tool_result("get_launch_readiness_summary", denied)

    company = str((ctx.action or {}).get("company_code") or ALLOWED_COMPANY).upper()
    if company != ALLOWED_COMPANY:
        return _tool_result("get_launch_readiness_summary", fallback_envelope("tenant_denied", locale=locale))

    legacy = ctx.legacy
    try:
        import setup_console_wave_a_launch_readiness as wave_a
    except Exception as exc:
        return _tool_result(
            "get_launch_readiness_summary",
            fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]}),
        )

    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                result = wave_a.evaluate_launch_readiness(cur, company_code=company)
    except Exception as exc:
        return _tool_result(
            "get_launch_readiness_summary",
            fallback_envelope("unavailable", locale=locale, payload={"error": str(exc)[:200]}),
        )

    if not result.get("ok"):
        return _tool_result(
            "get_launch_readiness_summary",
            fallback_envelope("blocked", locale=locale, payload={"error": result.get("error")}),
        )

    blockers = result.get("important_blockers") or []
    overall = result.get("overall_state")
    proposed = []
    citations = [
        {
            "kind": "launch_readiness",
            "module": "setup_console",
            "id": f"overall:{overall}",
            "label_en": result.get("overall_label_en") or overall,
            "label_ar": result.get("overall_label_ar") or overall,
            "as_of": kuwait_now_iso(),
            "authority_state": "read_only_compose",
        }
    ]
    for b in blockers[:6]:
        if not isinstance(b, dict):
            continue
        citations.append(
            {
                "kind": "blocker",
                "module": "setup_console",
                "id": b.get("key"),
                "label_en": b.get("title_en") or b.get("summary_en"),
                "label_ar": b.get("title_ar") or b.get("summary_ar"),
                "as_of": kuwait_now_iso(),
                "deep_link": b.get("deep_link"),
                "authority_state": b.get("state") or "blocked",
            }
        )
        proposed.append(
            {
                "kind": "deep_link",
                "module": "setup_console",
                "label_en": b.get("next_action_en") or b.get("title_en"),
                "label_ar": b.get("next_action_ar") or b.get("title_ar"),
                "deep_link": b.get("deep_link"),
                "executes": False,
            }
        )

    summary_en = (
        f"Launch readiness for WATHEFNI is '{result.get('overall_label_en') or overall}'. "
        f"{len(blockers)} important blocker(s). Setup mutations stay operator-only; assistant prepares links only."
    )
    summary_ar = (
        f"جاهزية الإطلاق لـ WATHEFNI هي '{result.get('overall_label_ar') or overall}'. "
        f"{len(blockers)} عائق(عوائق) مهم. تعديلات الإعداد تبقى للمشغّل فقط؛ المساعد يجهّز الروابط فقط."
    )
    env = grounded_envelope(
        ok=True,
        summary_en=summary_en,
        summary_ar=summary_ar,
        citations=citations,
        authority_state="read_only_compose",
        confidence="grounded",
        locale=locale,
        deep_links=[{"page": "setup_launch_readiness", "path": "/setup-console"}],
        proposed_actions=proposed,
        payload={
            "overall_state": overall,
            "blockers": len(blockers),
            "entitlements_cannot_bypass_gates": result.get("entitlements_cannot_bypass_gates"),
            "payroll_money": result.get("payroll_money"),
            "attendance_ingest": result.get("attendance_ingest"),
            "pause_impact": result.get("pause_impact"),
        },
    )
    return _tool_result("get_launch_readiness_summary", env)


def _tool_result(action_type: str, envelope: dict[str, Any]) -> dict[str, Any]:
    ok = bool(envelope.get("ok"))
    return {
        "action_type": action_type,
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": envelope.get("message") or envelope.get("summary_en"),
        "grounding": envelope,
        "mutates_records": False,
        "reply": envelope.get("message") or envelope.get("summary_en"),
    }


def mutation_kill_denial(*, tool_name: str, locale: str = "en") -> dict[str, Any]:
    env = fallback_envelope("mutations_killed", locale=locale, payload={"tool": tool_name})
    return {
        "status": "mutations_disabled",
        "tool": tool_name,
        "message": env.get("message"),
        "result": env,
        "grounding": env,
        "mutates_records": False,
    }


def master_kill_turn_result(*, locale: str = "en") -> dict[str, Any]:
    env = fallback_envelope("killed", locale=locale)
    return {
        "authoritative": True,
        "reply_text": env.get("message"),
        "final_reply_source": "platform_assistant_spine_wave1",
        "intent": "assistant_killed",
        "turn_focus": "kill_switch",
        "pending_action": None,
        "grounding": env,
        "audit": {"event": "assistant.kill_engaged", "contract": WAVE1_CONTRACT},
    }


def is_wave1_read_tool(name: str | None) -> bool:
    return str(name or "") in WAVE1_READ_TOOLS


def is_spine_read_tool(name: str | None) -> bool:
    """Wave 1 + Wave 2 grounded read tools (HR dashboard spine)."""
    if is_wave1_read_tool(name):
        return True
    try:
        import platform_assistant_wave2_safe_ops_reads as wave2

        return wave2.is_wave2_read_tool(name)
    except Exception:
        return False


def tool_is_mutation(spec: Any) -> bool:
    if spec is None:
        return False
    name = getattr(spec, "name", None) or ""
    if is_spine_read_tool(name):
        return False
    if getattr(spec, "sensitive", False):
        return True
    rule = getattr(spec, "requires_confirmation", False)
    if callable(rule) or bool(rule):
        return True
    return False
