"""Wave D Phase 3 — enterprise-safe multi-tenant inbound hardening.

Design goals for large HR / high-volume hiring:
* generous configurable limits by tenant and plan
* soft warnings before any hard restriction
* burst capacity for campaigns / seasonal spikes
* queue legitimate mail (waiting_quota) — never reject for volume
* admin overrides to raise limits immediately
* hard block only malware, clear abuse, or extreme platform risk
* staging/production Postmark environment separation
* ClamAV/OCR outage retry + replay sweep
* retention execution with audit
* usage/health visibility, kill switches, concurrency-safe addresses

External tenants remain allowlist-gated (D2). No mailbox sync. No D4.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Enterprise plan catalog (generous defaults — safety without restrictiveness)
# ---------------------------------------------------------------------------

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    # High-volume enterprise hiring (default for allowlisted production tenants).
    "enterprise": {
        "label": "Enterprise hiring",
        "daily_message_quota": 10_000,
        "monthly_message_quota": 200_000,
        "daily_source_bytes_quota": 20 * 1024 * 1024 * 1024,  # 20 GiB/day
        "monthly_source_bytes_quota": 400 * 1024 * 1024 * 1024,
        "daily_processing_job_quota": 50_000,
        "per_tenant_concurrency": 8,
        "soft_warning_pct": 80,
        "burst_pct": 50,  # temporary headroom above plan hard cap
        "burst_hours": 72,
    },
    # Mid-market growth teams.
    "growth": {
        "label": "Growth hiring",
        "daily_message_quota": 2_000,
        "monthly_message_quota": 40_000,
        "daily_source_bytes_quota": 5 * 1024 * 1024 * 1024,
        "monthly_source_bytes_quota": 80 * 1024 * 1024 * 1024,
        "daily_processing_job_quota": 10_000,
        "per_tenant_concurrency": 4,
        "soft_warning_pct": 80,
        "burst_pct": 50,
        "burst_hours": 48,
    },
    # Smaller teams — still generous vs typical recruitment volume.
    "starter": {
        "label": "Starter hiring",
        "daily_message_quota": 500,
        "monthly_message_quota": 10_000,
        "daily_source_bytes_quota": 2 * 1024 * 1024 * 1024,
        "monthly_source_bytes_quota": 20 * 1024 * 1024 * 1024,
        "daily_processing_job_quota": 2_500,
        "per_tenant_concurrency": 2,
        "soft_warning_pct": 80,
        "burst_pct": 100,
        "burst_hours": 24,
    },
    # Internal / continuous freeze — effectively uncapped commercial quotas.
    "internal": {
        "label": "OctoHR internal",
        "daily_message_quota": 0,  # 0 = unlimited (queue never for volume)
        "monthly_message_quota": 0,
        "daily_source_bytes_quota": 0,
        "monthly_source_bytes_quota": 0,
        "daily_processing_job_quota": 0,
        "per_tenant_concurrency": 12,
        "soft_warning_pct": 90,
        "burst_pct": 0,
        "burst_hours": 0,
    },
}

QUOTA_KEYS = (
    "daily_message_quota",
    "monthly_message_quota",
    "daily_source_bytes_quota",
    "monthly_source_bytes_quota",
    "daily_processing_job_quota",
)

OUTAGE_DEAD_LETTER_CODES = frozenset(
    {
        "scanner_unavailable",
        "clamav_unavailable",
        "malware_scanner_unavailable",
        "cv_extraction_failed",
        "ocr_required_mistral_disabled",
        "identity_extraction_failed",
    }
)


def _norm_company(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(str(os.environ.get(name, default)).strip()))
    except (TypeError, ValueError):
        return max(0, default)


def default_plan_for_company(company_code: str | None) -> str:
    company = _norm_company(company_code)
    if company == "WATHEFNI" or company.startswith("INBOUND") or "TEST" in company:
        return "internal"
    raw = (os.environ.get("WATHEFNI_INBOUND_DEFAULT_PLAN") or "enterprise").strip().lower()
    return raw if raw in PLAN_CATALOG else "enterprise"


def tenant_plan_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    blob = settings if isinstance(settings, dict) else {}
    inbound = blob.get("inbound_enterprise") if isinstance(blob.get("inbound_enterprise"), dict) else {}
    plan = str(inbound.get("plan") or blob.get("inbound_plan") or "").strip().lower()
    if plan not in PLAN_CATALOG:
        plan = ""
    overrides = inbound.get("quota_overrides") if isinstance(inbound.get("quota_overrides"), dict) else {}
    admin_override = inbound.get("admin_override") if isinstance(inbound.get("admin_override"), dict) else {}
    return {
        "plan": plan,
        "quota_overrides": overrides,
        "admin_override": admin_override,
        "soft_warning_pct": inbound.get("soft_warning_pct"),
        "kill_switch": inbound.get("kill_switch"),
    }


def resolve_plan(company_code: str | None, settings: dict[str, Any] | None = None) -> str:
    configured = tenant_plan_settings(settings).get("plan") or ""
    if configured in PLAN_CATALOG:
        return configured
    return default_plan_for_company(company_code)


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def admin_override_active(admin_override: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any] | None:
    """Return active admin override payload, or None if expired/absent."""
    if not isinstance(admin_override, dict) or not admin_override:
        return None
    now = now or datetime.now(UTC)
    expires = _parse_iso(admin_override.get("expires_at"))
    if expires and expires <= now:
        return None
    return dict(admin_override)


def burst_multiplier(admin_override: dict[str, Any] | None, plan: dict[str, Any], *, now: datetime | None = None) -> float:
    """Campaign burst: admin can enable; otherwise plan default window is opt-in via override flag."""
    now = now or datetime.now(UTC)
    active = admin_override_active(admin_override, now=now)
    if not active:
        return 1.0
    if not bool(active.get("burst_enabled")):
        # Explicit raise without burst still applies quota_overrides below.
        return 1.0
    pct = active.get("burst_pct")
    if pct is None:
        pct = plan.get("burst_pct") or 0
    try:
        pct_i = max(0, int(pct))
    except (TypeError, ValueError):
        pct_i = int(plan.get("burst_pct") or 0)
    return 1.0 + (pct_i / 100.0)


def effective_limits(
    company_code: str | None,
    *,
    settings: dict[str, Any] | None = None,
    base_config: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve plan + tenant overrides + admin override + optional env base.

    0 means unlimited for that metric (never volume-reject).
    """
    now = now or datetime.now(UTC)
    plan_key = resolve_plan(company_code, settings)
    plan = dict(PLAN_CATALOG[plan_key])
    tenant = tenant_plan_settings(settings)
    overrides = dict(tenant.get("quota_overrides") or {})
    # Legacy D2 inbound_quotas still honored as tenant overrides.
    legacy = (settings or {}).get("inbound_quotas") if isinstance(settings, dict) else None
    if isinstance(legacy, dict):
        for key in QUOTA_KEYS:
            if key in legacy and key not in overrides:
                try:
                    overrides[key] = max(0, int(legacy.get(key)))
                except (TypeError, ValueError):
                    pass

    admin = admin_override_active(tenant.get("admin_override"), now=now)
    if admin and isinstance(admin.get("quota_overrides"), dict):
        for key, value in admin["quota_overrides"].items():
            if key in QUOTA_KEYS:
                try:
                    overrides[key] = max(0, int(value))
                except (TypeError, ValueError):
                    continue

    limits: dict[str, int] = {}
    for key in QUOTA_KEYS:
        # Prefer explicit tenant/admin override, else plan, else base config/env.
        if key in overrides:
            limits[key] = max(0, int(overrides[key]))
            continue
        plan_val = int(plan.get(key) or 0)
        if base_config is not None and hasattr(base_config, key):
            base_val = int(getattr(base_config, key) or 0)
            # Env base of 0 historically meant "disabled"; plan supplies enterprise defaults.
            limits[key] = plan_val if base_val == 0 else base_val
        else:
            limits[key] = plan_val

    mult = burst_multiplier(admin, plan, now=now)
    if mult > 1.0:
        for key in QUOTA_KEYS:
            if limits[key] > 0:
                limits[key] = int(limits[key] * mult)

    concurrency = int(plan.get("per_tenant_concurrency") or 2)
    if admin and admin.get("per_tenant_concurrency") is not None:
        try:
            concurrency = max(1, int(admin.get("per_tenant_concurrency")))
        except (TypeError, ValueError):
            pass
    elif overrides.get("per_tenant_concurrency") is not None:
        try:
            concurrency = max(1, int(overrides.get("per_tenant_concurrency")))
        except (TypeError, ValueError):
            pass

    soft_pct = tenant.get("soft_warning_pct")
    if soft_pct is None:
        soft_pct = plan.get("soft_warning_pct") or 80
    try:
        soft_pct_i = min(99, max(1, int(soft_pct)))
    except (TypeError, ValueError):
        soft_pct_i = 80

    return {
        "plan": plan_key,
        "plan_label": plan.get("label"),
        "limits": limits,
        "per_tenant_concurrency": concurrency,
        "soft_warning_pct": soft_pct_i,
        "burst_multiplier": mult,
        "admin_override_active": bool(admin),
        "admin_override": admin,
        "kill_switch": bool(tenant.get("kill_switch")),
    }


@dataclass(frozen=True)
class QuotaDecision:
    """Volume decision — never 'reject' for legitimate traffic."""

    status: str | None  # None | waiting_quota
    code: str | None
    soft_warnings: tuple[str, ...]
    effective_limits: dict[str, int]
    usage_snapshot: dict[str, dict[str, int]]


def evaluate_quota(
    usage: dict[str, dict[str, int]],
    *,
    company_code: str | None,
    settings: dict[str, Any] | None = None,
    base_config: Any | None = None,
    now: datetime | None = None,
) -> QuotaDecision:
    """Soft-warn at threshold; hard path only queues (waiting_quota), never rejects."""
    resolved = effective_limits(company_code, settings=settings, base_config=base_config, now=now)
    limits: dict[str, int] = dict(resolved["limits"])
    soft_pct = int(resolved["soft_warning_pct"])
    checks = (
        ("daily_message_quota", "day", "messages"),
        ("monthly_message_quota", "month", "messages"),
        ("daily_source_bytes_quota", "day", "source_bytes"),
        ("monthly_source_bytes_quota", "month", "source_bytes"),
    )
    warnings: list[str] = []
    hard_code: str | None = None
    for code, period, metric in checks:
        limit = int(limits.get(code) or 0)
        if limit <= 0:
            continue
        used = int(usage.get(period, {}).get(metric, 0) or 0)
        if used >= int(limit * soft_pct / 100):
            warnings.append(f"{code}_soft_warning")
        if used > limit and hard_code is None:
            hard_code = code
    return QuotaDecision(
        status="waiting_quota" if hard_code else None,
        code=hard_code,
        soft_warnings=tuple(warnings),
        effective_limits=limits,
        usage_snapshot={k: dict(v) for k, v in (usage or {}).items()},
    )


def build_admin_override(
    *,
    actor: str,
    quota_overrides: dict[str, int] | None = None,
    burst_enabled: bool = True,
    burst_pct: int | None = None,
    hours: int | None = None,
    reason: str | None = None,
    per_tenant_concurrency: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    window = hours if hours is not None else _env_int("WATHEFNI_INBOUND_ADMIN_OVERRIDE_HOURS", 72)
    expires = now + timedelta(hours=max(1, window))
    payload: dict[str, Any] = {
        "enabled": True,
        "burst_enabled": bool(burst_enabled),
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "actor": str(actor or "admin")[:120],
        "reason": str(reason or "hiring_campaign_capacity")[:240],
        "id": secrets.token_hex(8),
    }
    if burst_pct is not None:
        payload["burst_pct"] = max(0, int(burst_pct))
    if quota_overrides:
        clean: dict[str, int] = {}
        for key, value in quota_overrides.items():
            if key in QUOTA_KEYS or key == "per_tenant_concurrency":
                try:
                    clean[key] = max(0, int(value))
                except (TypeError, ValueError):
                    continue
        payload["quota_overrides"] = clean
    if per_tenant_concurrency is not None:
        payload["per_tenant_concurrency"] = max(1, int(per_tenant_concurrency))
    return payload


def merge_enterprise_settings(
    current: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Merge inbound_enterprise blob into company_settings-compatible patch result."""
    base = dict(current or {}) if isinstance(current, dict) else {}
    inbound = dict(base.get("inbound_enterprise") or {}) if isinstance(base.get("inbound_enterprise"), dict) else {}
    if "plan" in patch and str(patch.get("plan") or "").strip().lower() in PLAN_CATALOG:
        inbound["plan"] = str(patch.get("plan")).strip().lower()
    if "soft_warning_pct" in patch:
        try:
            inbound["soft_warning_pct"] = min(99, max(1, int(patch.get("soft_warning_pct"))))
        except (TypeError, ValueError):
            pass
    if "kill_switch" in patch:
        inbound["kill_switch"] = bool(patch.get("kill_switch"))
    if "quota_overrides" in patch and isinstance(patch.get("quota_overrides"), dict):
        inbound["quota_overrides"] = {
            k: max(0, int(v))
            for k, v in patch["quota_overrides"].items()
            if k in QUOTA_KEYS or k == "per_tenant_concurrency"
        }
    if "admin_override" in patch:
        if patch.get("admin_override") is None:
            inbound.pop("admin_override", None)
        elif isinstance(patch.get("admin_override"), dict):
            inbound["admin_override"] = dict(patch["admin_override"])
    base["inbound_enterprise"] = inbound
    return base


# ---------------------------------------------------------------------------
# Postmark staging / production isolation
# ---------------------------------------------------------------------------

def expected_inbound_postmark_env() -> str:
    explicit = (os.environ.get("WATHEFNI_POSTMARK_INBOUND_ENV") or "").strip().lower()
    if explicit:
        return explicit
    app_env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if app_env in {"production", "prod"}:
        return "production"
    if app_env in {"staging", "stage"}:
        return "staging"
    return ""  # local/test — isolation optional


def verify_postmark_inbound_environment(
    *,
    header_env: str | None = None,
    query_env: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Strict separation when an expected inbound env is configured.

    Staging and production must use distinct Postmark servers/secrets *and*
    present a matching environment marker (header, query, or payload tag).
    """
    expected = expected_inbound_postmark_env()
    if not expected:
        return True, None
    meta = (payload or {}).get("Metadata") if isinstance(payload, dict) else None
    meta_env = ""
    if isinstance(meta, dict):
        meta_env = str(meta.get("wathefni_inbound_env") or meta.get("WathefniInboundEnv") or "")
    payload_env = ""
    if isinstance(payload, dict):
        payload_env = str(payload.get("WathefniInboundEnv") or "")
    provided = (
        str(header_env or "").strip().lower()
        or str(query_env or "").strip().lower()
        or payload_env.strip().lower()
        or meta_env.strip().lower()
        or ""
    )
    # Also accept server-side pinned marker that ops injects into the webhook URL.
    pinned = (os.environ.get("WATHEFNI_POSTMARK_INBOUND_ENV_PIN") or "").strip().lower()
    if pinned and not provided:
        provided = pinned
    if not provided:
        return False, "inbound_env_marker_missing"
    if provided != expected:
        return False, "inbound_env_mismatch"
    return True, None


# ---------------------------------------------------------------------------
# Outage replay + retention helpers
# ---------------------------------------------------------------------------

def retention_execute_enabled() -> bool:
    """Opt-in destructive retention. Default dry-run unless explicitly enabled."""
    return (os.environ.get("WATHEFNI_INTAKE_RETENTION_EXECUTE") or "off").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def list_outage_dead_letters(
    cur: Any,
    *,
    company_code: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    company = _norm_company(company_code)
    params: list[Any] = []
    where = "status='dead_letter'"
    if company:
        where += " AND company_code=%s"
        params.append(company)
    params.append(max(1, min(int(limit), 500)))
    cur.execute(
        f"""
        SELECT job_id::text AS job_id, company_code, job_type, subject_id,
               last_error_code, last_error_detail, attempts, updated_at
        FROM intake_processing_jobs
        WHERE {where}
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params),
    )
    rows = [dict(r) for r in cur.fetchall()]
    out: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("last_error_code") or "").strip().lower()
        detail = str(row.get("last_error_detail") or "").strip().lower()
        if code in OUTAGE_DEAD_LETTER_CODES or any(x in detail for x in ("scanner_unavailable", "clamav", "mistral", "ocr")):
            out.append(row)
    return out


def usage_visibility(
    cur: Any,
    *,
    company_code: str,
    settings: dict[str, Any] | None = None,
    base_config: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    company = _norm_company(company_code)
    day = datetime(now.year, now.month, now.day, tzinfo=UTC)
    month = datetime(now.year, now.month, 1, tzinfo=UTC)
    usage: dict[str, dict[str, int]] = {"day": {}, "month": {}}
    for kind, start in (("day", day), ("month", month)):
        cur.execute(
            """
            SELECT messages, attachments, source_bytes, processed_jobs
            FROM intake_quota_usage
            WHERE company_code=%s AND period_kind=%s AND period_start=%s
            LIMIT 1
            """,
            (company, kind, start),
        )
        row = cur.fetchone() or {}
        usage[kind] = {
            "messages": int(row.get("messages") or 0),
            "attachments": int(row.get("attachments") or 0),
            "source_bytes": int(row.get("source_bytes") or 0),
            "processed_jobs": int(row.get("processed_jobs") or 0),
        }
    decision = evaluate_quota(usage, company_code=company, settings=settings, base_config=base_config, now=now)
    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE status IN ('pending','retrying','waiting_quota','waiting_budget','running'))::int AS active_jobs,
          count(*) FILTER (WHERE status='dead_letter')::int AS dead_letter_jobs,
          count(*) FILTER (WHERE status='waiting_quota')::int AS waiting_quota_jobs
        FROM intake_processing_jobs
        WHERE company_code=%s
        """,
        (company,),
    )
    queue = dict(cur.fetchone() or {})
    return {
        "company_code": company,
        "plan": resolve_plan(company, settings),
        "effective_limits": decision.effective_limits,
        "soft_warning_pct": effective_limits(company, settings=settings, base_config=base_config, now=now)["soft_warning_pct"],
        "soft_warnings": list(decision.soft_warnings),
        "queued_for_quota": decision.status == "waiting_quota",
        "quota_code": decision.code,
        "usage": usage,
        "queue": queue,
        "admin_override_active": effective_limits(company, settings=settings, base_config=base_config, now=now)["admin_override_active"],
        "never_reject_for_volume": True,
    }


ENTERPRISE_AUDIT_ACTIONS = (
    "inbound_admin_override_raised",
    "inbound_admin_override_cleared",
    "inbound_outage_replay",
    "inbound_retention_cleanup",
    "inbound_postmark_env_rejected",
    "inbound_tenant_kill_switch",
    "inbound_plan_updated",
)
