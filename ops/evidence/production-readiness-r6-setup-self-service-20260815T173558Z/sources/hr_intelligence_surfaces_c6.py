#!/usr/bin/env python3
"""Wave 5 C6 — governed HR Intelligence surfaces.

This module presents C1 Registry evaluations. It deliberately owns no KPI
formula and never reads domain facts to calculate a number.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_surfaces_c6"
CONTRACT_VERSION = "hr_intelligence_surfaces_c6_v1"
PASS_STAMP = "HR_INTELLIGENCE_SURFACES_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
_ON = {"1", "true", "yes", "on"}

HONESTY = {
    "no_frontend_formulas": True,
    "uses_c1_evaluator_only": True,
    "attention_is_not_intelligence": True,
    "scheduled_delivery_safe_debt": True,
    "employee_app_no_company_intelligence": True,
}

FAMILY_ORDER = (
    "workforce",
    "hiring",
    "time_leave",
    "pay",
    "performance",
    "talent",
    "hr_ops",
)
_FAMILY_PREFIXES = (
    ("workforce.", "workforce"),
    ("recruiting.", "hiring"),
    ("hire_ready.", "hiring"),
    ("time.", "time_leave"),
    ("leave.", "time_leave"),
    ("shifts.", "time_leave"),
    ("overtime.", "time_leave"),
    ("payroll.", "pay"),
    ("performance.", "performance"),
    ("talent.", "talent"),
    ("intelligence.", "hr_ops"),
)

_STATUS_LABELS = {
    "ok": {"en": "Available", "ar": "متاح"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
    "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
    "blocked": {"en": "Blocked", "ar": "محظور"},
    "stale": {"en": "May be stale", "ar": "قد يكون قديماً"},
    "refreshing": {"en": "Refreshing", "ar": "جارٍ التحديث"},
}
_NON_COMPARABLE = {
    "suppressed",
    "not_applicable",
    "insufficient_data",
    "unavailable",
    "blocked",
    "forbidden",
}
_PERSON_SENSITIVE = {"payroll_money", "talent_sensitive"}


def _ensure_handlers_loaded() -> None:
    """Load C2–C5 only so their C1 formula handlers register."""
    try:
        import hr_intelligence_workforce_c2  # noqa: F401
    except Exception:
        pass
    try:
        import hr_intelligence_recruiting_c3  # noqa: F401
    except Exception:
        pass
    try:
        import hr_intelligence_time_pay_c4  # noqa: F401
    except Exception:
        pass
    try:
        import hr_intelligence_perf_talent_c5  # noqa: F401
    except Exception:
        pass


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return value


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def family_for_semantic_key(key: str | None) -> str:
    semantic_key = str(key or "").strip().lower()
    for prefix, family in _FAMILY_PREFIXES:
        if semantic_key.startswith(prefix):
            return family
    return "hr_ops"


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    labels = _STATUS_LABELS.get(key) or {
        "en": key.replace("_", " ").title() or "Unknown",
        "ar": key or "غير معروف",
    }
    return labels["ar" if str(lang).lower().startswith("ar") else "en"]


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        **HONESTY,
        "company_code": c1.company_code_norm(company_code) if company_code else None,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = c1.company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    c1_gate = c1.runtime_gate_for_company(company)
    if not c1_gate.get("ok"):
        return {**c1_gate, "enabled": False, "error": "c1_registry_required", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"):
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_surfaces_c6_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    if not c1.slice_allowlist_admits(company, "WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"):
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_surfaces_company_not_allowlisted",
            "gate": "company_allowlist",
            "company_code": company,
            "phase": PHASE,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_surfaces_c6_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c6_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          manager_analytics_enabled boolean NOT NULL DEFAULT false,
          export_person_level_requires_permission boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_saved_views (
          view_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          owner_phone text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          mode text NOT NULL,
          query_config jsonb NOT NULL DEFAULT '{}'::jsonb,
          pinned_definition_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
          layout jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, owner_phone, name_en),
          CHECK (mode IN ('live','pinned'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_export_jobs (
          export_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          actor_phone text NOT NULL,
          semantic_key text NOT NULL,
          definition_id uuid,
          effective_version integer,
          time_window jsonb NOT NULL DEFAULT '{}'::jsonb,
          filters jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL,
          row_count integer NOT NULL DEFAULT 0,
          csv_sha256 text,
          csv_text text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('generated','failed'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c6_audit (
          audit_id bigserial PRIMARY KEY,
          company_code text,
          action text NOT NULL,
          actor_phone text,
          subject_type text,
          subject_id text,
          reason text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_intelligence_saved_views_owner "
        "ON hr_intelligence_saved_views (company_code, owner_phone, updated_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_intelligence_exports_company "
        "ON hr_intelligence_export_jobs (company_code, created_at DESC)"
    )


ensure_schema = ensure_hr_intelligence_surfaces_c6_schema


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO hr_intelligence_c6_audit (
          company_code, action, actor_phone, subject_type, subject_id, reason, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            c1.company_code_norm(company_code),
            action,
            _digits(actor_phone),
            subject_type,
            subject_id,
            reason,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_schema(cur)
    c1_entitlement = c1._entitled(cur, company)
    if not c1_entitlement.get("ok"):
        return {
            "ok": False,
            "enabled": False,
            "error": "c1_company_entitlement_required",
            "company_code": company,
        }
    cur.execute(
        "SELECT * FROM hr_intelligence_c6_company_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {
            "ok": False,
            "enabled": False,
            "error": "company_intelligence_surfaces_disabled",
            "company_code": company,
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company,
        "settings": dict(row),
        "c1_settings": c1_entitlement["settings"],
    }


def enable_company_hr_intelligence_surfaces(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    manager_analytics_enabled: bool = False,
    export_person_level_requires_permission: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_schema(cur)
    c1_entitlement = c1._entitled(cur, company)
    if not c1_entitlement.get("ok"):
        return {"ok": False, "error": "c1_company_entitlement_required", "detail": c1_entitlement}
    cur.execute(
        """
        INSERT INTO hr_intelligence_c6_company_settings (
          company_code, enabled, manager_analytics_enabled,
          export_person_level_requires_permission, enabled_by_phone,
          enabled_reason, enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          manager_analytics_enabled=EXCLUDED.manager_analytics_enabled,
          export_person_level_requires_permission=EXCLUDED.export_person_level_requires_permission,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(manager_analytics_enabled),
            bool(export_person_level_requires_permission),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    settings = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="company_enabled",
        actor_phone=actor_phone,
        reason=reason,
        payload={
            "manager_analytics_enabled": bool(manager_analytics_enabled),
            "requires_c1_company_entitlement": True,
        },
    )
    return {"ok": True, "enabled": True, "settings": settings}


def disable_company_hr_intelligence_surfaces(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = c1.company_code_norm(company_code)
    ensure_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c6_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s
        RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(
        cur,
        company_code=company,
        action="company_disabled",
        actor_phone=actor_phone,
        reason=reason,
        payload={"preserves_history": True},
    )
    return {
        "ok": True,
        "enabled": False,
        "settings": dict(row) if row else None,
        "preserves_history": True,
    }


enable_company = enable_company_hr_intelligence_surfaces
disable_company = disable_company_hr_intelligence_surfaces


def _published_definition(cur: Any, company_code: str, semantic_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT d.*, p.publication_id, p.published_at
          FROM hr_kpi_company_publications p
          JOIN hr_kpi_definitions d ON d.kpi_definition_id=p.kpi_definition_id
         WHERE p.company_code=%s AND p.semantic_key=%s AND p.published=true
        """,
        (c1.company_code_norm(company_code), str(semantic_key or "").strip()),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _definition_public(definition: dict[str, Any]) -> dict[str, Any]:
    key = str(definition["semantic_key"])
    return {
        "semantic_key": key,
        "definition_id": str(definition["kpi_definition_id"]),
        "effective_version": int(definition["effective_version"]),
        "family": family_for_semantic_key(key),
        "name_en": definition["name_en"],
        "name_ar": definition["name_ar"],
        "description_en": definition["description_en"],
        "description_ar": definition["description_ar"],
        "business_meaning": definition["business_meaning"],
        "numerator": _json(definition.get("numerator"), {}),
        "denominator": _json(definition.get("denominator"), None),
        "inclusion_rules": _json(definition.get("inclusion_rules"), {}),
        "exclusion_rules": _json(definition.get("exclusion_rules"), {}),
        "unit": definition["unit"],
        "time_semantics": definition["time_semantics"],
        "supported_dimensions": list(_json(definition.get("supported_dimensions"), [])),
        "permission_class": definition["permission_class"],
        "definition_status": definition["status"],
        "status_honesty": {
            key: {"en": status_label(key), "ar": status_label(key, lang="ar")}
            for key in _STATUS_LABELS
        },
    }


def list_published_kpis(cur: Any, company: str, actor: str) -> dict[str, Any]:
    _ = actor
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        """
        SELECT d.*, p.publication_id, p.published_at
          FROM hr_kpi_company_publications p
          JOIN hr_kpi_definitions d ON d.kpi_definition_id=p.kpi_definition_id
         WHERE p.company_code=%s AND p.published=true
         ORDER BY d.semantic_key
        """,
        (ent["company_code"],),
    )
    metrics = [_definition_public(dict(row)) for row in cur.fetchall()]
    rank = {family: index for index, family in enumerate(FAMILY_ORDER)}
    metrics.sort(key=lambda row: (rank.get(row["family"], 999), row["semantic_key"]))
    return {"ok": True, "company_code": ent["company_code"], "kpis": metrics, "count": len(metrics)}


def about_metric(cur: Any, semantic_key: str, company: str) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    definition = _published_definition(cur, ent["company_code"], semantic_key)
    if not definition:
        return {"ok": False, "error": "kpi_not_published_for_company", "status": "unavailable"}
    return {"ok": True, "about_metric": _definition_public(definition)}


def _safe_evaluation(result: dict[str, Any], *, lang: str = "en") -> dict[str, Any]:
    out = dict(result)
    status = str(out.get("status") or ("blocked" if not out.get("ok") else "ok")).lower()
    if status == "forbidden":
        status = "blocked"
    out["status"] = status
    out["status_label"] = status_label(status, lang=lang)
    if status == "suppressed":
        out["value"] = None
        out["numerator_value"] = None
        out["denominator_value"] = None
        out["population_ids"] = []
        out["population_count"] = None
        out["explain"] = {
            "suppressed": True,
            "reason": "minimum_cohort_policy",
            "numeric_details_withheld": True,
        }
    elif status in {"blocked", "unavailable"}:
        out["value"] = None
        out["population_ids"] = []
    return out


def evaluate_metric(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    time_window: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    actor_role: str = "hr",
    has_permission: bool = True,
    lang: str = "en",
    persist: bool = True,
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return _safe_evaluation({**ent, "status": "unavailable"}, lang=lang)
    if actor_role == "manager" and not bool(ent["settings"].get("manager_analytics_enabled")):
        return _safe_evaluation(
            {"ok": False, "status": "blocked", "error": "manager_analytics_disabled"},
            lang=lang,
        )
    _ensure_handlers_loaded()
    try:
        evaluated = c1.evaluate_kpi(
            cur,
            company_code=ent["company_code"],
            actor_phone=actor,
            semantic_key=semantic_key,
            actor_role=actor_role,
            filters=filters or {},
            time_window=time_window or {},
            has_permission=bool(has_permission),
            persist=persist,
        )
    except Exception as exc:  # surfaces fail closed — never crash Overview
        evaluated = {
            "ok": False,
            "status": "unavailable",
            "error": "evaluation_failed",
            "semantic_key": semantic_key,
            "message": str(exc)[:240],
            "value": None,
            "population_ids": [],
        }
    if evaluated.get("error") and not evaluated.get("status"):
        evaluated = {**evaluated, "status": "unavailable", "ok": False, "value": None, "population_ids": []}
    evaluated = _safe_evaluation(evaluated, lang=lang)
    about = about_metric(cur, semantic_key, ent["company_code"])
    evaluated["about_metric"] = about.get("about_metric")
    evaluated["family"] = family_for_semantic_key(semantic_key)
    evaluated["governed_by_c1"] = True
    return evaluated


def compose_overview(
    cur: Any,
    company: str,
    actor: str,
    time_window: dict[str, Any] | None,
    filters: dict[str, Any] | None,
    lang: str,
    *,
    actor_role: str = "hr",
    has_permission: bool = True,
) -> dict[str, Any]:
    published = list_published_kpis(cur, company, actor)
    if not published.get("ok"):
        return published
    groups = {family: [] for family in FAMILY_ORDER}
    omitted = []
    for metric in published["kpis"]:
        result = evaluate_metric(
            cur,
            company=company,
            actor=actor,
            semantic_key=metric["semantic_key"],
            time_window=time_window,
            filters=filters,
            actor_role=actor_role,
            has_permission=has_permission,
            lang=lang,
        )
        if result["status"] in {"unavailable", "blocked"}:
            omitted.append({"semantic_key": metric["semantic_key"], "status": result["status"]})
            continue
        groups[metric["family"]].append(result)
    families = [
        {"family": family, "metrics": groups[family]}
        for family in FAMILY_ORDER
        if groups[family]
    ]
    return {
        "ok": True,
        "company_code": c1.company_code_norm(company),
        "families": families,
        "omitted_count": len(omitted),
        "omitted": omitted,
        "honesty": honesty_payload(company_code=company),
    }


def allowed_trend_buckets(time_semantics: str | None) -> list[str]:
    semantics = str(time_semantics or "").strip().lower()
    if semantics == "cohort":
        return ["monthly", "quarterly", "yearly"]
    if semantics in {"point_in_time", "rolling_window"}:
        return ["weekly", "monthly", "quarterly", "yearly"]
    return ["daily", "weekly", "monthly", "quarterly", "yearly"]


def _next_month(day: date) -> date:
    return date(day.year + (1 if day.month == 12 else 0), 1 if day.month == 12 else day.month + 1, 1)


def _generated_buckets(time_window: dict[str, Any], bucket: str) -> list[dict[str, str]]:
    end = _date(time_window.get("period_end") or time_window.get("end") or time_window.get("as_of"))
    start = _date(time_window.get("period_start") or time_window.get("start"))
    end = end or date.today()
    start = start or (end - timedelta(days=365))
    if start > end:
        raise ValueError("invalid_time_window")
    result: list[dict[str, str]] = []
    cursor = start
    while cursor <= end and len(result) < 240:
        if bucket == "daily":
            bucket_end = cursor
            nxt = cursor + timedelta(days=1)
        elif bucket == "weekly":
            bucket_end = min(end, cursor + timedelta(days=6))
            nxt = bucket_end + timedelta(days=1)
        elif bucket == "monthly":
            nxt = _next_month(cursor.replace(day=1))
            bucket_end = min(end, nxt - timedelta(days=1))
        elif bucket == "quarterly":
            quarter_start_month = ((cursor.month - 1) // 3) * 3 + 1
            quarter_start = date(cursor.year, quarter_start_month, 1)
            month = quarter_start_month + 3
            nxt = date(cursor.year + (1 if month > 12 else 0), ((month - 1) % 12) + 1, 1)
            bucket_end = min(end, nxt - timedelta(days=1))
        elif bucket == "yearly":
            nxt = date(cursor.year + 1, 1, 1)
            bucket_end = min(end, nxt - timedelta(days=1))
        else:
            raise ValueError("invalid_trend_bucket")
        result.append(
            {
                "key": f"{cursor.isoformat()}:{bucket_end.isoformat()}",
                "period_start": cursor.isoformat(),
                "period_end": bucket_end.isoformat(),
                "as_of": bucket_end.isoformat(),
            }
        )
        cursor = nxt
    return result


def trend_metric(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    time_window: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    bucket: str = "monthly",
    time_buckets: list[dict[str, Any]] | None = None,
    actor_role: str = "hr",
    has_permission: bool = True,
    lang: str = "en",
) -> dict[str, Any]:
    about = about_metric(cur, semantic_key, company)
    if not about.get("ok"):
        return about
    semantics = about["about_metric"]["time_semantics"]
    allowed = allowed_trend_buckets(semantics)
    normalized_bucket = str(bucket or "monthly").lower()
    if normalized_bucket not in allowed:
        return {
            "ok": False,
            "error": "trend_bucket_not_allowed",
            "time_semantics": semantics,
            "allowed": allowed,
        }
    try:
        buckets = time_buckets or _generated_buckets(time_window or {}, normalized_bucket)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    series = []
    for item in buckets:
        period = {
            "period_start": _iso(item.get("period_start") or item.get("start")),
            "period_end": _iso(item.get("period_end") or item.get("end")),
            "as_of": _iso(item.get("as_of") or item.get("period_end") or item.get("end")),
        }
        result = evaluate_metric(
            cur,
            company=company,
            actor=actor,
            semantic_key=semantic_key,
            time_window=period,
            filters=filters,
            actor_role=actor_role,
            has_permission=has_permission,
            lang=lang,
        )
        series.append(
            {
                "bucket": item.get("key") or period["period_end"],
                "time_window": period,
                "status": result["status"],
                "status_label": result["status_label"],
                "value": result.get("value"),
                "unit": result.get("unit"),
            }
        )
    return {
        "ok": True,
        "semantic_key": semantic_key,
        "bucket": normalized_bucket,
        "time_semantics": semantics,
        "series": series,
        "about_metric": about["about_metric"],
    }


def _prior_window(current: dict[str, Any]) -> dict[str, str] | None:
    start = _date(current.get("period_start") or current.get("start"))
    end = _date(current.get("period_end") or current.get("end"))
    if not start or not end or start > end:
        return None
    days = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days - 1)
    return {"period_start": prior_start.isoformat(), "period_end": prior_end.isoformat(), "as_of": prior_end.isoformat()}


def compare_metric(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    current_time_window: dict[str, Any] | None = None,
    prior_time_window: dict[str, Any] | None = None,
    current_filters: dict[str, Any] | None = None,
    comparison_filters: dict[str, Any] | None = None,
    mode: str = "prior",
    actor_role: str = "hr",
    has_permission: bool = True,
    lang: str = "en",
) -> dict[str, Any]:
    current = evaluate_metric(
        cur,
        company=company,
        actor=actor,
        semantic_key=semantic_key,
        time_window=current_time_window,
        filters=current_filters,
        actor_role=actor_role,
        has_permission=has_permission,
        lang=lang,
    )
    if mode == "segment_vs_company":
        comparison_window = current_time_window
        compare_filters = comparison_filters or {}
    else:
        comparison_window = prior_time_window or _prior_window(current_time_window or {})
        if comparison_window is None:
            return {"ok": False, "error": "prior_time_window_required"}
        compare_filters = comparison_filters if comparison_filters is not None else current_filters
    comparison = evaluate_metric(
        cur,
        company=company,
        actor=actor,
        semantic_key=semantic_key,
        time_window=comparison_window,
        filters=compare_filters,
        actor_role=actor_role,
        has_permission=has_permission,
        lang=lang,
    )
    if current["status"] in _NON_COMPARABLE or comparison["status"] in _NON_COMPARABLE:
        return {
            "ok": False,
            "comparable": False,
            "error": "comparison_not_comparable",
            "current": current,
            "comparison": comparison,
        }
    if current.get("unit") != comparison.get("unit"):
        return {
            "ok": False,
            "comparable": False,
            "error": "comparison_unit_or_currency_mismatch",
            "current": current,
            "comparison": comparison,
        }
    current_currency = (current.get("explain") or {}).get("currency")
    comparison_currency = (comparison.get("explain") or {}).get("currency")
    if current_currency != comparison_currency:
        return {
            "ok": False,
            "comparable": False,
            "error": "comparison_unit_or_currency_mismatch",
            "current": current,
            "comparison": comparison,
        }
    return {
        "ok": True,
        "comparable": True,
        "mode": mode,
        "current": current,
        "comparison": comparison,
        "no_surface_recalculation": True,
    }


def segment_metric(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    dimension: str,
    dimension_value: Any,
    time_window: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    actor_role: str = "hr",
    has_permission: bool = True,
    lang: str = "en",
) -> dict[str, Any]:
    about = about_metric(cur, semantic_key, company)
    if not about.get("ok"):
        return about
    dimension_key = str(dimension or "").strip().lower()
    supported = {str(item).strip().lower() for item in about["about_metric"]["supported_dimensions"]}
    if dimension_key not in supported:
        return {"ok": False, "error": "dimension_not_supported", "supported_dimensions": sorted(supported)}
    if dimension_key == "gender":
        return {"ok": False, "error": "gender_dimension_forbidden"}
    if dimension_key == "nationality":
        ent = _entitled(cur, company)
        if not ent.get("ok") or not bool(ent["c1_settings"].get("nationality_dimension_enabled")):
            return {"ok": False, "error": "nationality_dimension_disabled"}
    segment_filters = dict(filters or {})
    segment_filters.update({"dimension": dimension_key, "dimension_value": dimension_value})
    result = evaluate_metric(
        cur,
        company=company,
        actor=actor,
        semantic_key=semantic_key,
        time_window=time_window,
        filters=segment_filters,
        actor_role=actor_role,
        has_permission=has_permission,
        lang=lang,
    )
    return {
        "ok": result.get("ok", False),
        "dimension": dimension_key,
        "dimension_value": dimension_value,
        "metric": result,
    }


def drill_population(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    time_window: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    actor_role: str = "hr",
    has_permission: bool = True,
    has_payroll_permission: bool = False,
    has_talent_permission: bool = False,
    offset: int = 0,
    limit: int = 50,
    lang: str = "en",
) -> dict[str, Any]:
    result = evaluate_metric(
        cur,
        company=company,
        actor=actor,
        semantic_key=semantic_key,
        time_window=time_window,
        filters=filters,
        actor_role=actor_role,
        has_permission=has_permission,
        lang=lang,
    )
    permission_class = str(result.get("permission_class") or "")
    if permission_class == "payroll_money" and not has_payroll_permission:
        return {"ok": False, "error": "payroll_drill_permission_required", "reauthorized": True}
    if permission_class == "talent_sensitive" and not has_talent_permission:
        return {"ok": False, "error": "talent_drill_permission_required", "reauthorized": True}
    if result["status"] == "suppressed":
        return {
            "ok": True,
            "status": "suppressed",
            "rows": [],
            "total": None,
            "reauthorized": True,
            "explain": "Drill was re-evaluated and reauthorized; suppressed populations are never returned.",
        }
    if result["status"] in _NON_COMPARABLE:
        return {
            "ok": False,
            "error": "drill_not_available",
            "status": result["status"],
            "rows": [],
            "reauthorized": True,
        }
    population = [str(item) for item in (result.get("population_ids") or [])]
    safe_offset = max(0, int(offset))
    safe_limit = min(200, max(1, int(limit)))
    page = population[safe_offset : safe_offset + safe_limit]
    return {
        "ok": True,
        "status": result["status"],
        "rows": [{"id": item, "label": item} for item in page],
        "total": len(population),
        "offset": safe_offset,
        "limit": safe_limit,
        "reauthorized": True,
        "aggregate_population_count": result.get("population_count"),
        "explain": "Drill was re-evaluated against current tenant, role, scope, and metric permissions.",
    }


def _saved_view_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "view_id": str(row["view_id"]),
        "query_config": _json(row.get("query_config"), {}),
        "pinned_definition_versions": _json(row.get("pinned_definition_versions"), {}),
        "layout": _json(row.get("layout"), {}),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def create_saved_view(
    cur: Any,
    *,
    company: str,
    owner_phone: str,
    name_en: str,
    name_ar: str | None = None,
    mode: str = "live",
    query_config: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
    actor_role: str = "hr",
    has_permission: bool = True,
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    if not str(name_en or "").strip():
        return {"ok": False, "error": "saved_view_name_required"}
    normalized_mode = str(mode or "live").strip().lower()
    if normalized_mode not in {"live", "pinned"}:
        return {"ok": False, "error": "invalid_saved_view_mode"}
    config = dict(query_config or {})
    pinned: dict[str, Any] = {}
    if normalized_mode == "pinned":
        semantic_key = str(config.get("semantic_key") or "").strip()
        if not semantic_key:
            return {"ok": False, "error": "semantic_key_required"}
        snapshot = evaluate_metric(
            cur,
            company=company,
            actor=owner_phone,
            semantic_key=semantic_key,
            time_window=config.get("time_window") or {},
            filters=config.get("filters") or {},
            actor_role=actor_role,
            has_permission=has_permission,
            persist=False,
        )
        if not snapshot.get("effective_version"):
            return {"ok": False, "error": snapshot.get("error") or "pinned_definition_unavailable"}
        pinned[semantic_key] = int(snapshot["effective_version"])
        config["_pinned_snapshot"] = {
            "is_snapshot": True,
            "re_evaluation_support": "current_definition_only",
            "explain": "C1 does not expose version-selective evaluation; this snapshot is historical metadata, not new truth.",
            "status": snapshot["status"],
            "value": snapshot.get("value"),
            "unit": snapshot.get("unit"),
            "effective_version": snapshot["effective_version"],
            "evaluated_at": _iso((snapshot.get("freshness") or {}).get("evaluated_at")),
        }
    view_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_intelligence_saved_views (
          view_id, company_code, owner_phone, name_en, name_ar, mode,
          query_config, pinned_definition_versions, layout
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
        RETURNING *
        """,
        (
            view_id,
            ent["company_code"],
            _digits(owner_phone),
            str(name_en).strip(),
            str(name_ar or "").strip() or None,
            normalized_mode,
            json.dumps(config, default=str),
            json.dumps(pinned, default=str),
            json.dumps(layout or {}, default=str),
        ),
    )
    row = _saved_view_public(dict(cur.fetchone()))
    _audit(
        cur,
        company_code=ent["company_code"],
        action="saved_view_created",
        actor_phone=owner_phone,
        subject_type="saved_view",
        subject_id=view_id,
        payload={"mode": normalized_mode},
    )
    return {"ok": True, "saved_view": row}


def list_saved_views(cur: Any, *, company: str, owner_phone: str) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        """
        SELECT * FROM hr_intelligence_saved_views
         WHERE company_code=%s AND owner_phone=%s
         ORDER BY updated_at DESC
        """,
        (ent["company_code"], _digits(owner_phone)),
    )
    return {"ok": True, "saved_views": [_saved_view_public(dict(row)) for row in cur.fetchall()]}


def get_saved_view(
    cur: Any,
    *,
    company: str,
    owner_phone: str,
    view_id: str,
    actor_role: str = "hr",
    has_permission: bool = True,
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        """
        SELECT * FROM hr_intelligence_saved_views
         WHERE view_id=%s AND company_code=%s AND owner_phone=%s
        """,
        (view_id, ent["company_code"], _digits(owner_phone)),
    )
    raw = cur.fetchone()
    if not raw:
        return {"ok": False, "error": "saved_view_not_found"}
    view = _saved_view_public(dict(raw))
    config = view["query_config"]
    semantic_key = str(config.get("semantic_key") or "").strip()
    if semantic_key:
        view["current_evaluation"] = evaluate_metric(
            cur,
            company=company,
            actor=owner_phone,
            semantic_key=semantic_key,
            time_window=config.get("time_window") or {},
            filters=config.get("filters") or {},
            actor_role=actor_role,
            has_permission=has_permission,
        )
        view["opened_by_re_evaluation"] = True
    return {"ok": True, "saved_view": view}


def delete_saved_view(cur: Any, *, company: str, owner_phone: str, view_id: str) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        """
        DELETE FROM hr_intelligence_saved_views
         WHERE view_id=%s AND company_code=%s AND owner_phone=%s
        RETURNING view_id
        """,
        (view_id, ent["company_code"], _digits(owner_phone)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "saved_view_not_found"}
    _audit(
        cur,
        company_code=ent["company_code"],
        action="saved_view_deleted",
        actor_phone=owner_phone,
        subject_type="saved_view",
        subject_id=view_id,
    )
    return {"ok": True, "deleted": True, "view_id": view_id}


def _csv_text(metadata: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> str:
    stream = io.StringIO(newline="")
    for key, value in metadata.items():
        stream.write(f"# {key}: {json.dumps(value, ensure_ascii=False, default=str)}\n")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()


def create_export_csv(
    cur: Any,
    *,
    company: str,
    actor: str,
    semantic_key: str,
    time_window: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    person_level: bool = False,
    actor_role: str = "hr",
    has_permission: bool = True,
    has_export_person_permission: bool = False,
    has_payroll_permission: bool = False,
    has_talent_permission: bool = False,
    lang: str = "en",
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    if (
        person_level
        and bool(ent["settings"].get("export_person_level_requires_permission", True))
        and not has_export_person_permission
    ):
        return {"ok": False, "error": "person_level_export_permission_required"}
    evaluated = evaluate_metric(
        cur,
        company=company,
        actor=actor,
        semantic_key=semantic_key,
        time_window=time_window,
        filters=filters,
        actor_role=actor_role,
        has_permission=has_permission,
        lang=lang,
    )
    permission_class = str(evaluated.get("permission_class") or "")
    if person_level and permission_class == "payroll_money" and not has_payroll_permission:
        return {"ok": False, "error": "payroll_drill_permission_required"}
    if person_level and permission_class == "talent_sensitive" and not has_talent_permission:
        return {"ok": False, "error": "talent_drill_permission_required"}
    metadata = {
        "semantic_key": semantic_key,
        "definition_id": evaluated.get("kpi_definition_id"),
        "effective_version": evaluated.get("effective_version"),
        "status": evaluated.get("status"),
        "unit": evaluated.get("unit"),
        "time_window": time_window or {},
        "filters": filters or {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_by": "hr_intelligence_registry_c1.evaluate_kpi",
        "suppressed_population_never_exported": True,
    }
    if person_level:
        people = [] if evaluated["status"] == "suppressed" else list(evaluated.get("population_ids") or [])
        rows = [[str(item), str(item)] for item in people]
        columns = ["id", "label"]
    else:
        rows = [[
            semantic_key,
            evaluated["status"],
            evaluated.get("value"),
            evaluated.get("unit"),
            evaluated.get("effective_version"),
        ]]
        columns = ["semantic_key", "status", "value", "unit", "effective_version"]
    text = _csv_text(metadata, columns, rows)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    export_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_intelligence_export_jobs (
          export_id, company_code, actor_phone, semantic_key, definition_id,
          effective_version, time_window, filters, status, row_count,
          csv_sha256, csv_text, metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,'generated',%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            export_id,
            ent["company_code"],
            _digits(actor),
            semantic_key,
            evaluated.get("kpi_definition_id"),
            evaluated.get("effective_version"),
            json.dumps(time_window or {}, default=str),
            json.dumps(filters or {}, default=str),
            len(rows),
            digest,
            text,
            json.dumps(metadata, default=str),
        ),
    )
    job = _export_public(dict(cur.fetchone()), include_csv=False)
    _audit(
        cur,
        company_code=ent["company_code"],
        action="export_generated",
        actor_phone=actor,
        subject_type="export",
        subject_id=export_id,
        payload={"person_level": bool(person_level), "status": evaluated["status"], "row_count": len(rows)},
    )
    return {"ok": True, "export": job}


def _export_public(row: dict[str, Any], *, include_csv: bool) -> dict[str, Any]:
    out = {
        **row,
        "export_id": str(row["export_id"]),
        "definition_id": str(row["definition_id"]) if row.get("definition_id") else None,
        "time_window": _json(row.get("time_window"), {}),
        "filters": _json(row.get("filters"), {}),
        "metadata": _json(row.get("metadata"), {}),
        "created_at": _iso(row.get("created_at")),
    }
    if not include_csv:
        out.pop("csv_text", None)
    return out


def get_export(
    cur: Any,
    *,
    company: str,
    actor: str,
    export_id: str,
    include_csv: bool = False,
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        """
        SELECT * FROM hr_intelligence_export_jobs
         WHERE export_id=%s AND company_code=%s AND actor_phone=%s
        """,
        (export_id, ent["company_code"], _digits(actor)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "export_not_found"}
    return {"ok": True, "export": _export_public(dict(row), include_csv=include_csv)}


def assistant_query_metric(
    cur: Any, *, company: str, actor: str, semantic_key: str
) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return ent
    _ensure_handlers_loaded()
    result = c1.assistant_resolve_metric(
        cur,
        company_code=ent["company_code"],
        actor_phone=actor,
        semantic_key=semantic_key,
    )
    result["invented"] = False
    result["governed_by_c1"] = True
    if isinstance(result.get("evaluation"), dict):
        result["evaluation"] = _safe_evaluation(result["evaluation"])
    return result


def bootstrap_payload(cur: Any, *, company: str, actor: str) -> dict[str, Any]:
    ent = _entitled(cur, company)
    if not ent.get("ok"):
        return {**ent, "c6_enabled": False, "honesty": honesty_payload(company_code=company)}
    published = list_published_kpis(cur, company, actor)
    return {
        "ok": True,
        "c6_enabled": True,
        "company_code": ent["company_code"],
        "honesty": honesty_payload(company_code=company),
        "overview": {"families": [], "evaluated": False},
        "published_kpis": published.get("kpis") or [],
        "settings": {
            "manager_analytics_enabled": bool(ent["settings"].get("manager_analytics_enabled")),
            "export_person_level_requires_permission": bool(
                ent["settings"].get("export_person_level_requires_permission", True)
            ),
        },
    }


_ensure_handlers_loaded()

