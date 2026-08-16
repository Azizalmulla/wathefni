"""Wave D Phase 2 — productized forwarded inbound CV email (tenant-flagged).

Architecture (approved):
  company recruitment email → forwarding → tenant Wathefni intake address
  → Postmark → durable ingress (quarantine / malware / identity / explicit admit)

This module owns allowlist + tenant flags, setup copy (EN/AR), address health,
and quota presentation. Wave D3 (`inbound_enterprise_hardening`) adds plan
catalogs, soft warnings, burst overrides, and never-reject volume semantics.
"""

from __future__ import annotations

import os
import re
import secrets
from typing import Any


DEFAULT_INBOUND_DOMAIN = "inbound.wathefni.ai"

# Fail-closed default when WATHEFNI_INBOUND_ALLOWED_COMPANIES is unset:
# WATHEFNI continuous freeze + obvious test tenants only.
_DEFAULT_ALLOWLIST = frozenset({"WATHEFNI"})


def inbound_domain() -> str:
    return (os.environ.get("WATHEFNI_INBOUND_DOMAIN") or DEFAULT_INBOUND_DOMAIN).strip().lower() or DEFAULT_INBOUND_DOMAIN


def _norm_company(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def parse_inbound_allowlist() -> frozenset[str]:
    """Explicit allowlist from env. Empty env → default WATHEFNI-only set.

    Comma-separated company codes. Use `*` only in WATHEFNI_ENV=test to permit
    any company (local/smoke). Never default to open allowlist in production.
    """
    raw = (os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES") or "").strip()
    if not raw:
        return _DEFAULT_ALLOWLIST
    parts = {_norm_company(p) for p in raw.split(",") if _norm_company(p)}
    return frozenset(parts) if parts else _DEFAULT_ALLOWLIST


def company_looks_like_test_tenant(company_code: str | None) -> bool:
    company = _norm_company(company_code)
    if not company:
        return False
    if company.startswith("TEST") or company.endswith("TEST"):
        return True
    if "_TEST_" in company or company.startswith("INBOUND"):
        return True
    return False


def company_on_inbound_allowlist(company_code: str | None) -> bool:
    company = _norm_company(company_code)
    if not company:
        return False
    allow = parse_inbound_allowlist()
    if "*" in allow:
        # Wildcard only honored in test/local environments.
        env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
        return env in {"test", "local", "dev"}
    if company in allow:
        return True
    # When using the default WATHEFNI-only allowlist, also permit clear test tenants
    # so local smoke and QA companies can opt in via the tenant flag without
    # opening external production customers.
    if allow == _DEFAULT_ALLOWLIST and company_looks_like_test_tenant(company):
        return True
    return False


def company_inbound_flag(settings: dict[str, Any] | None) -> bool | None:
    """Return explicit tenant flag if set; None means 'unset' (default on for allowlisted)."""
    if not isinstance(settings, dict):
        return None
    if "inbound_forwarding_enabled" not in settings:
        return None
    return bool(settings.get("inbound_forwarding_enabled"))


def company_inbound_email_enabled(
    *,
    global_enabled: bool,
    company_code: str | None,
    company_settings: dict[str, Any] | None = None,
) -> bool:
    """Global kill-switch AND allowlist AND tenant flag (default on when allowlisted)."""
    if not global_enabled:
        return False
    if not company_on_inbound_allowlist(company_code):
        return False
    flag = company_inbound_flag(company_settings)
    if flag is None:
        return True
    return flag


def tenant_inbound_quotas(settings: dict[str, Any] | None) -> dict[str, int]:
    """Optional per-tenant quota caps stored under company_settings.inbound_quotas."""
    raw = (settings or {}).get("inbound_quotas") if isinstance(settings, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key in (
        "daily_message_quota",
        "monthly_message_quota",
        "daily_source_bytes_quota",
        "monthly_source_bytes_quota",
        "daily_processing_job_quota",
    ):
        if key not in raw:
            continue
        try:
            out[key] = max(0, int(raw.get(key)))
        except (TypeError, ValueError):
            continue
    return out


def merge_ingress_quotas(base: dict[str, int], overrides: dict[str, int]) -> dict[str, int]:
    """Apply tenant overrides; 0 means disabled (same semantics as IngressConfig)."""
    merged = dict(base)
    for key, value in overrides.items():
        if key in merged:
            merged[key] = value
    return merged


def quotas_public(config: Any, *, tenant_overrides: dict[str, int] | None = None) -> dict[str, Any]:
    base = {
        "daily_message_quota": int(getattr(config, "daily_message_quota", 0) or 0),
        "monthly_message_quota": int(getattr(config, "monthly_message_quota", 0) or 0),
        "daily_source_bytes_quota": int(getattr(config, "daily_source_bytes_quota", 0) or 0),
        "monthly_source_bytes_quota": int(getattr(config, "monthly_source_bytes_quota", 0) or 0),
        "daily_processing_job_quota": int(getattr(config, "daily_processing_job_quota", 0) or 0),
    }
    effective = merge_ingress_quotas(base, tenant_overrides or {})
    commercial = any(int(v or 0) > 0 for v in effective.values())
    return {
        **effective,
        "commercial_enforced": commercial,
        "tenant_overrides": dict(tenant_overrides or {}),
    }


def suggest_local_part(company_code: str | None, *, suffix: str | None = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm_company(company_code).lower()).strip("-") or "company"
    base = base[:24]
    token = (suffix or secrets.token_hex(3)).lower()
    return f"{base}-cv-{token}"


def setup_instructions(*, primary_address: str | None = None) -> dict[str, Any]:
    """Customer-facing EN/AR forwarding checklist (Outlook / Gmail / M365)."""
    addr = (primary_address or "").strip() or f"your-company@{inbound_domain()}"
    steps_en = [
        f"Create or choose the recruitment mailbox your company already uses (for example careers@yourcompany.com).",
        f"Add a forward (or inbox rule) so every message with a CV attachment is copied to {addr}.",
        "In Microsoft 365 / Outlook: Settings → Mail → Forwarding, or create a rule “if has attachment → redirect/forward to Wathefni”.",
        "In Gmail: Settings → Forwarding and POP/IMAP → Add a forwarding address, then confirm; optionally filter “Has attachment” to that address.",
        "Send one test CV from an external address and confirm Wathefni shows a recent received time on this page.",
        "Optional: create a job-specific Wathefni alias for a single open role. Without a role alias, CVs are held as needs role until HR assigns one.",
        "Wathefni does not open or sync your Microsoft/Google inbox in this phase — forwarding is the only intake path.",
    ]
    steps_ar = [
        f"أنشئ أو اختر صندوق بريد التوظيف الذي تستخدمه الشركة بالفعل (مثل careers@yourcompany.com).",
        f"أضف تحويلاً (أو قاعدة وارد) بحيث تُنسخ كل رسالة تحتوي مرفق سيرة ذاتية إلى {addr}.",
        "في Microsoft 365 / Outlook: الإعدادات ← البريد ← التحويل، أو أنشئ قاعدة «إذا وُجد مرفق ← إعادة توجيه إلى وظفني».",
        "في Gmail: الإعدادات ← التحويل وPOP/IMAP ← أضف عنوان تحويل ثم أكّده؛ ويمكنك تصفية «يحتوي مرفقاً» إلى ذلك العنوان.",
        "أرسل سيرة ذاتية تجريبية من عنوان خارجي وتأكد أن وظفني يعرض وقت استلام حديث في هذه الصفحة.",
        "اختياري: أنشئ اسماً مستعاراً خاصاً بوظيفة مفتوحة. بدون تعيين وظيفة تُحفظ السير كـ «تحتاج دوراً» حتى يعيّنها الموارد البشرية.",
        "وظفني لا يفتح ولا يزامن صندوق بريد مايكروسوفت/جوجل في هذه المرحلة — التحويل هو مسار الاستقبال الوحيد.",
    ]
    summary_en = (
        f"Forward CVs from your company recruitment email to {addr}. "
        "Wathefni receives a copy via secure inbound mail, scans attachments, "
        "and holds candidates until HR reviews identity and admits them to a role."
    )
    summary_ar = (
        f"حوّل السير الذاتية من بريد التوظيف في شركتك إلى {addr}. "
        "يستلم وظفني نسخة عبر بريد وارد آمن، يفحص المرفقات، "
        "ويُبقي المرشحين معلّقين حتى تراجع الموارد البشرية الهوية وتضيفهم إلى وظيفة."
    )
    return {
        "primary_address": addr,
        "forward_instructions_en": summary_en,
        "forward_instructions_ar": summary_ar,
        "setup_steps_en": steps_en,
        "setup_steps_ar": steps_ar,
    }


def intake_health_from_row(stats: dict[str, Any] | None) -> dict[str, Any]:
    stats = stats or {}
    return {
        "last_received_at": stats.get("last_received_at"),
        "received_count": int(stats.get("received_count") or 0),
        "received_7d": int(stats.get("received_7d") or 0),
        "last_status": stats.get("last_status"),
    }


def fetch_intake_health(cur: Any, *, company_code: str, intake_id: str | None = None) -> dict[str, Any]:
    """Aggregate last-received health for one address or the whole company."""
    company = _norm_company(company_code)
    if intake_id:
        cur.execute(
            """
            SELECT max(received_at) AS last_received_at,
                   count(*)::int AS received_count,
                   count(*) FILTER (WHERE received_at >= now() - interval '7 days')::int AS received_7d,
                   (
                     SELECT status FROM inbound_messages
                     WHERE company_code=%s AND intake_id=%s::uuid
                     ORDER BY coalesce(received_at, created_at) DESC NULLS LAST
                     LIMIT 1
                   ) AS last_status
            FROM inbound_messages
            WHERE company_code=%s AND intake_id=%s::uuid
            """,
            (company, intake_id, company, intake_id),
        )
    else:
        cur.execute(
            """
            SELECT max(received_at) AS last_received_at,
                   count(*)::int AS received_count,
                   count(*) FILTER (WHERE received_at >= now() - interval '7 days')::int AS received_7d,
                   (
                     SELECT status FROM inbound_messages
                     WHERE company_code=%s
                     ORDER BY coalesce(received_at, created_at) DESC NULLS LAST
                     LIMIT 1
                   ) AS last_status
            FROM inbound_messages
            WHERE company_code=%s
            """,
            (company, company),
        )
    row = cur.fetchone() or {}
    return intake_health_from_row(dict(row) if not isinstance(row, dict) else row)


def feature_status_public(
    *,
    global_enabled: bool,
    company_code: str | None,
    company_settings: dict[str, Any] | None,
    config: Any,
    health: dict[str, Any] | None = None,
    enterprise: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowlisted = company_on_inbound_allowlist(company_code)
    tenant_on = company_inbound_email_enabled(
        global_enabled=global_enabled,
        company_code=company_code,
        company_settings=company_settings,
    )
    overrides = tenant_inbound_quotas(company_settings)
    payload: dict[str, Any] = {
        "enabled": bool(tenant_on),
        "global_enabled": bool(global_enabled),
        "allowlisted": bool(allowlisted),
        "tenant_flag": company_inbound_flag(company_settings),
        "domain": inbound_domain(),
        "architecture": "forward_to_wathefni_intake",
        # Premium D5 connectors stay off in the forwarding product payload.
        # When WATHEFNI_MAILBOX_SYNC is enabled, mailbox_feature_status() owns UX.
        "mailbox_sync_enabled": False,
        "mailbox_connectors_premium": True,
        "default_intake_product": "forwarding",
        "quotas": quotas_public(config, tenant_overrides=overrides),
        "health": health or intake_health_from_row({}),
        "never_reject_for_volume": True,
        "hard_block_only": ["malware", "clear_abuse", "extreme_platform_risk"],
    }
    if enterprise:
        payload["enterprise"] = enterprise
    return payload
