"""Employees 360 Wave 3H — jurisdiction policy-pack architecture.

Reusable, versioned packs. Only KW_PRIVATE_SECTOR is verified/enabled.
Reserved pack IDs exist for future countries/categories but have no legal rules yet.
Generic lifecycle services must resolve packs — never hard-code country law.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import date, datetime, timezone
from typing import Any

SCHEMA_VERSION = "employees360-wave3h-jurisdiction-packs-v1"

# ---------------------------------------------------------------------------
# Pack identifiers
# ---------------------------------------------------------------------------

VERIFIED_PACKS = frozenset({"KW_PRIVATE_SECTOR"})

RESERVED_PACKS = frozenset({
    "KW_GOVERNMENT",
    "KW_DOMESTIC_WORKERS",
    "KW_OIL_SECTOR",
    "KW_MARITIME",
    "SA_PRIVATE_SECTOR",
    "UAE_PRIVATE_SECTOR",
    "QA_PRIVATE_SECTOR",
    "BH_PRIVATE_SECTOR",
    "OM_PRIVATE_SECTOR",
})

ALL_PACK_CODES = VERIFIED_PACKS | RESERVED_PACKS

# Jurisdiction + worker_category → pack code (only verified mappings implemented).
JURISDICTION_ALIASES = {
    "KW": "KW",
    "KWT": "KW",
    "KUWAIT": "KW",
    "KUWAIT_PRIVATE_SECTOR": "KW",
}

WORKER_CATEGORY_ALIASES = {
    "private_sector": "private_sector",
    "private": "private_sector",
    "kw_private_sector": "private_sector",
    "government": "government",
    "gov": "government",
    "domestic": "domestic_workers",
    "domestic_workers": "domestic_workers",
    "oil": "oil_sector",
    "oil_sector": "oil_sector",
    "maritime": "maritime",
    "marine": "maritime",
}

# Only this mapping is verified/enabled today.
ENABLED_RESOLUTION = {
    ("KW", "private_sector"): "KW_PRIVATE_SECTOR",
}

# Reserved mappings (fail closed — pack not implemented).
RESERVED_RESOLUTION = {
    ("KW", "government"): "KW_GOVERNMENT",
    ("KW", "domestic_workers"): "KW_DOMESTIC_WORKERS",
    ("KW", "oil_sector"): "KW_OIL_SECTOR",
    ("KW", "maritime"): "KW_MARITIME",
    ("SA", "private_sector"): "SA_PRIVATE_SECTOR",
    ("UAE", "private_sector"): "UAE_PRIVATE_SECTOR",
    ("QA", "private_sector"): "QA_PRIVATE_SECTOR",
    ("BH", "private_sector"): "BH_PRIVATE_SECTOR",
    ("OM", "private_sector"): "OM_PRIVATE_SECTOR",
}

# Keys tenants may tighten (never weaken below pack mandatory floors).
TIGHTENABLE_BOOL_TRUE_ONLY = frozenset({
    "require_last_working_day",
    "require_employment_classification",
    "require_termination_case_class",
    "require_impact_ack",
    "exceptional_cases_manual_only",
    "service_certificate_default",
})
TIGHTENABLE_BOOL_FALSE_ONLY = frozenset({
    "show_notice_hints",
    "allow_reinstate_after_effective",
    "auto_cancel_shifts",
    "auto_decline_leave",
    "allow_self_approval",
})
TIGHTENABLE_INT_RAISE_ONLY = frozenset({
    "document_retention_floor_days",
    "lag_alert_seconds",
})
IMMUTABLE_STATUTORY_KEYS = frozenset({
    "monetary_calculations_owner",
    "settlement_packet_mode",
    "jurisdiction_code",
    "worker_category",
    "pack_code",
    "pack_version",
    "mandatory_rules",
    "exceptional_case_classes",
    "contract_types",
    "pay_frequencies",
    "allowed_lifecycle_actions",
    "disabled_fallbacks",
    "source_refs",
})


def _pack_hash(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _kw_private_sector_v1() -> dict[str, Any]:
    """Canonical verified pack — preserves Wave 3F Kuwait private-sector behaviour exactly."""
    pack = {
        "pack_code": "KW_PRIVATE_SECTOR",
        "jurisdiction_code": "KW",
        "worker_category": "private_sector",
        "policy_version": "1.0.0",
        "effective_from": "2010-02-21",  # Gazette Issue 963 publication date (Law 6/2010)
        "effective_to": None,
        "status": "verified",
        "enabled": True,
        "timezone_default": "Asia/Kuwait",
        "source_refs": [
            {
                "role": "primary_arabic",
                "title": "Kuwait Labour Law No. 6 of 2010 (e.gov / MOJ PDF)",
                "sha256": "20eac58834489098d86271cfc6df9926adfe3fcc9607c47531247e6a56d3f326",
                "evidence": "ops/evidence/employees360-wave3f-public-law-closure-20260801T214550Z/sources/",
            },
            {
                "role": "english_gazette_reading_aid",
                "title": "Official Gazette Issue 963 extract (21 Feb 2010)",
                "sha256": "aaed5c6e02a03df4bfdcf035ba1befb9ece3c96d635c5a947f0c5ae929a70fe0",
            },
            {
                "role": "wave3f_closure",
                "title": "Employees 360 Wave 3F public-law closure pack",
                "evidence": "ops/evidence/employees360-wave3f-public-law-closure-20260801T214550Z/",
            },
        ],
        "required_employment_fields": [
            "contract_type",
            "pay_frequency",
            "probation_status",
            "termination_case_class",
            "termination_effective_on",
            "last_working_day",
        ],
        "contract_types": ["unlimited", "fixed_term"],
        "pay_frequencies": ["monthly", "other"],
        "probation_statuses": ["none", "active", "completed"],
        "probation_rules": {
            "max_working_days": 100,
            "terminate_without_notice_during_probation": True,
            "hide_notice_hints_when_active": True,
            "require_dates_when_active": True,
            "once_per_employer": True,
            "article_refs": ["32"],
        },
        "notice_rules": {
            "applies_to_contract_types": ["unlimited"],
            "blocked_when_probation_active": True,
            "blocked_for_exceptional_cases": True,
            "show_hints_default": False,
            "monthly_hint_days": 90,
            "other_hint_days": 30,
            "article_refs": ["44"],
            "label": (
                "Optional labeled guidance only — not a legal determination. "
                "Shown only when contract_type=unlimited, probation is not active, pay_frequency is known, "
                "and the case is not an exceptional/summary path. Mirrors Law No. 6/2010 Art. 44 "
                "(Official Gazette Issue 963, 21 Feb 2010): 3 months (monthly) / 1 month (other). "
                "HR must still enter effective date and last working day."
            ),
        },
        "fixed_term_rules": {
            "notice_hints_apply": False,
            "damages_owned_by": "payroll",
            "article_refs": ["30", "31", "47"],
        },
        "termination_case_classes": [
            "resignation",
            "dismissal_ordinary",
            "summary_dismissal_41a",
            "summary_dismissal_41b",
            "end_of_fixed_term",
            "mutual",
            "abandonment_42",
            "worker_summary_exit_48",
            "death_disability_49",
            "employer_status_50",
            "other_exceptional",
        ],
        "exceptional_case_classes": [
            "summary_dismissal_41a",
            "summary_dismissal_41b",
            "abandonment_42",
            "worker_summary_exit_48",
            "death_disability_49",
            "employer_status_50",
            "other_exceptional",
        ],
        "exceptional_case_escalation": {
            "manual_only": True,
            "require_escalation_note": True,
            "software_decides_lawfulness": False,
        },
        "settlement_ownership": {
            "owner": "payroll",
            "mode": "inputs_only",
            "forbidden_in_employees360": [
                "eosb",
                "notice_pay",
                "garden_leave_pay",
                "damages",
                "leave_encashment",
            ],
        },
        "service_certificate": {
            "required_default": True,
            "article_refs": ["54"],
            "fields": ["duration", "position", "last_remuneration"],
            "forbid_harmful_expressions": True,
        },
        "retention": {
            "mode": "retain",
            "floor_days": 365,
            "auto_purge": False,
            "article_refs": ["80", "144"],
        },
        "allowed_lifecycle_actions": [
            "termination",
            "cancel_scheduled",
            "rehire",
            "notice",
            "suspension",
            "unsuspend",
            "activate_start",
            "downstream_action",
            # reinstate allowed only if tenant explicitly tightens... no: reinstate is disabled by default
            # included as action type but gated by allow_reinstate_after_effective=false
            "reinstate",
        ],
        "disabled_fallbacks": {
            "allow_reinstate_after_effective": False,
            "show_notice_hints": False,
            "auto_cancel_shifts": False,
            "auto_decline_leave": False,
            "allow_self_approval": False,
            "unsupported_jurisdiction": "fail_closed",
            "missing_worker_category": "fail_closed",
            "missing_classification": "manual_review_missing_classification",
        },
        "mandatory_rules": {
            "require_last_working_day": True,
            "require_employment_classification": True,
            "require_termination_case_class": True,
            "require_impact_ack": True,
            "exceptional_cases_manual_only": True,
            "monetary_calculations_owner": "payroll",
            "settlement_packet_mode": "inputs_only",
            "service_certificate_default": True,
            "document_retention_mode": "retain",
            "document_retention_floor_days": 365,
            "allow_self_approval": False,
        },
        "ui_copy": {
            "termination_banner": (
                "Enter contract type, pay frequency, probation status, case classification, "
                "effective date and last working day. Missing or conflicting fields go to manual review."
            ),
            "notice_hint_hidden": (
                "Notice-period guidance is hidden until unlimited contract, non-probation status "
                "and pay frequency are complete, and the case is not exceptional."
            ),
            "exceptional_case_banner": (
                "Exceptional / high-risk case. Wathefni will not decide lawfulness. "
                "Complete evidence, escalate for human legal judgment, and keep dates/approvals manual."
            ),
            "settlement_handoff": (
                "Settlement packet is inputs-only. Payroll calculates EOSB, notice compensation, "
                "garden-leave pay and leave encashment outside Employees 360."
            ),
            "service_certificate": (
                "On end of service the worker is entitled to a service certificate (Art. 54) stating "
                "duration, position and last remuneration, without harmful expressions. Track issuance in Wathefni."
            ),
            "rehire_vs_reinstate": (
                "Post-effective reinstatement is disabled by default. Use true rehire (new employment) "
                "unless policy explicitly enables reinstate."
            ),
            "retention": (
                "Personnel file contents (Art. 80) are retained. No automatic purge. "
                "Conservative floor aligns with the one-year lawsuit horizon (Art. 144)."
            ),
            "unsupported_pack": (
                "This employment jurisdiction/worker category has no verified Employees 360 policy pack. "
                "Lifecycle actions are blocked until a verified pack exists or the record is remediated."
            ),
            "remediation_required": (
                "Jurisdiction or worker category is uncertain. Complete remediation before lifecycle actions."
            ),
        },
        "disclaimer": (
            "Configurable policy only. Not legal advice. Wathefni records, validates and orchestrates HR decisions. "
            "Wathefni does not determine whether a specific termination is legally justified. "
            "Employees 360 never calculates EOSB, notice pay, garden leave, damages or leave encashment — "
            "Payroll owns monetary calculations from an inputs-only settlement packet."
        ),
        "wave": "wave3h",
        "wave3f_compatible": True,
    }
    pack["content_hash"] = _pack_hash({k: v for k, v in pack.items() if k != "content_hash"})
    return pack


def _reserved_stub(pack_code: str, jurisdiction_code: str, worker_category: str) -> dict[str, Any]:
    stub = {
        "pack_code": pack_code,
        "jurisdiction_code": jurisdiction_code,
        "worker_category": worker_category,
        "policy_version": "0.0.0-reserved",
        "effective_from": None,
        "effective_to": None,
        "status": "reserved",
        "enabled": False,
        "source_refs": [],
        "required_employment_fields": [],
        "mandatory_rules": {},
        "disabled_fallbacks": {"reason": "pack_not_implemented"},
        "disclaimer": "Reserved pack identifier only. No legal rules implemented.",
        "wave": "wave3h",
    }
    stub["content_hash"] = _pack_hash({k: v for k, v in stub.items() if k != "content_hash"})
    return stub


def build_pack_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {
        "KW_PRIVATE_SECTOR": _kw_private_sector_v1(),
    }
    reserved_meta = [
        ("KW_GOVERNMENT", "KW", "government"),
        ("KW_DOMESTIC_WORKERS", "KW", "domestic_workers"),
        ("KW_OIL_SECTOR", "KW", "oil_sector"),
        ("KW_MARITIME", "KW", "maritime"),
        ("SA_PRIVATE_SECTOR", "SA", "private_sector"),
        ("UAE_PRIVATE_SECTOR", "UAE", "private_sector"),
        ("QA_PRIVATE_SECTOR", "QA", "private_sector"),
        ("BH_PRIVATE_SECTOR", "BH", "private_sector"),
        ("OM_PRIVATE_SECTOR", "OM", "private_sector"),
    ]
    for code, jur, cat in reserved_meta:
        catalog[code] = _reserved_stub(code, jur, cat)
    return catalog


PACK_CATALOG = build_pack_catalog()


def get_pack(pack_code: str, *, version: str | None = None) -> dict[str, Any] | None:
    pack = PACK_CATALOG.get(str(pack_code or "").upper())
    if not pack:
        return None
    if version and str(pack.get("policy_version")) != str(version):
        # Future: load historical immutable versions from DB. v1 only in-process today.
        return None
    return copy.deepcopy(pack)


def normalize_jurisdiction(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    return JURISDICTION_ALIASES.get(s, s)


def normalize_worker_category(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        return None
    return WORKER_CATEGORY_ALIASES.get(s, s)


def resolve_pack_code(*, jurisdiction_code: str | None, worker_category: str | None) -> dict[str, Any]:
    """Fail closed: missing/unsupported/conflicting → not resolvable."""
    jur = normalize_jurisdiction(jurisdiction_code)
    cat = normalize_worker_category(worker_category)
    if not jur:
        return {
            "ok": False,
            "error": "missing_jurisdiction",
            "message": "Employment jurisdiction is required to resolve a policy pack.",
            "remediation": True,
        }
    if not cat:
        return {
            "ok": False,
            "error": "missing_worker_category",
            "message": "Worker category is required to resolve a policy pack.",
            "remediation": True,
        }
    key = (jur, cat)
    if key in ENABLED_RESOLUTION:
        code = ENABLED_RESOLUTION[key]
        pack = get_pack(code)
        assert pack and pack.get("enabled")
        return {
            "ok": True,
            "pack_code": code,
            "policy_version": pack["policy_version"],
            "content_hash": pack["content_hash"],
            "pack": pack,
            "jurisdiction_code": jur,
            "worker_category": cat,
        }
    if key in RESERVED_RESOLUTION:
        code = RESERVED_RESOLUTION[key]
        return {
            "ok": False,
            "error": "pack_not_implemented",
            "message": f"Policy pack {code} is reserved but not implemented.",
            "pack_code": code,
            "jurisdiction_code": jur,
            "worker_category": cat,
            "remediation": False,
            "ui_copy": PACK_CATALOG[code].get("disclaimer"),
        }
    return {
        "ok": False,
        "error": "unsupported_jurisdiction",
        "message": "No verified or reserved policy pack matches this jurisdiction/worker category.",
        "jurisdiction_code": jur,
        "worker_category": cat,
        "remediation": True,
    }


def merge_tenant_override(pack: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Tenant may only tighten controls; never weaken mandatory statutory rules."""
    if not override:
        return copy.deepcopy(pack)
    merged = copy.deepcopy(pack)
    rules = dict(merged.get("mandatory_rules") or {})
    disabled = dict(merged.get("disabled_fallbacks") or {})
    notice = dict(merged.get("notice_rules") or {})
    rejected: list[dict[str, Any]] = []

    for key, value in override.items():
        if key in IMMUTABLE_STATUTORY_KEYS or key in {"pack_code", "policy_version", "content_hash", "source_refs"}:
            rejected.append({"key": key, "reason": "immutable_statutory"})
            continue
        if key in TIGHTENABLE_BOOL_TRUE_ONLY:
            if value is True:
                rules[key] = True
            elif value is False and rules.get(key) is True:
                rejected.append({"key": key, "reason": "cannot_weaken_mandatory_true"})
            continue
        if key in TIGHTENABLE_BOOL_FALSE_ONLY:
            # Tightening means keeping false (or forcing false). True weakens safety defaults.
            if value is False:
                disabled[key] = False
                if key == "show_notice_hints":
                    notice["show_hints_default"] = False
                if key == "allow_reinstate_after_effective":
                    disabled["allow_reinstate_after_effective"] = False
            elif value is True:
                # Only allow enabling reinstate/hints if pack default permits opt-in AND not statutory forbidden.
                # Wave 3H: allow_reinstate and show_notice_hints are configurable opt-ins (not mandatory statutory).
                # Enabling them is a company policy choice, not weakening a statutory floor.
                if key in {"show_notice_hints", "allow_reinstate_after_effective"}:
                    disabled[key] = True
                    if key == "show_notice_hints":
                        notice["show_hints_default"] = True
                    if key == "allow_reinstate_after_effective":
                        disabled["allow_reinstate_after_effective"] = True
                else:
                    rejected.append({"key": key, "reason": "cannot_enable_unsafe_default"})
            continue
        if key in TIGHTENABLE_INT_RAISE_ONLY:
            try:
                new_v = int(value)
                old_v = int(rules.get(key) or disabled.get(key) or notice.get(key) or 0)
                if key == "document_retention_floor_days":
                    floor = int(rules.get("document_retention_floor_days") or merged.get("retention", {}).get("floor_days") or 365)
                    if new_v >= floor:
                        rules["document_retention_floor_days"] = new_v
                        ret = dict(merged.get("retention") or {})
                        ret["floor_days"] = new_v
                        merged["retention"] = ret
                    else:
                        rejected.append({"key": key, "reason": "cannot_lower_retention_floor", "floor": floor})
                elif new_v >= old_v:
                    rules[key] = new_v
                else:
                    rejected.append({"key": key, "reason": "cannot_lower_int_floor"})
            except Exception:
                rejected.append({"key": key, "reason": "invalid_int"})
            continue
        if key == "timezone":
            # Company timezone operational — allow if non-empty.
            if str(value or "").strip():
                merged["timezone_default"] = str(value).strip()
            continue
        rejected.append({"key": key, "reason": "override_not_allowed"})

    merged["mandatory_rules"] = rules
    merged["disabled_fallbacks"] = disabled
    merged["notice_rules"] = notice
    merged["tenant_override_rejected"] = rejected
    # Recompute effective hash of applied rules (pack content_hash stays immutable identity).
    merged["effective_hash"] = _pack_hash(
        {
            "pack_code": merged.get("pack_code"),
            "policy_version": merged.get("policy_version"),
            "content_hash": merged.get("content_hash"),
            "mandatory_rules": rules,
            "disabled_fallbacks": disabled,
            "notice_rules": notice,
            "retention": merged.get("retention"),
        }
    )
    return merged


def pack_as_company_policy_overlay(pack: dict[str, Any]) -> dict[str, Any]:
    """Project pack mandatory/disabled rules onto Wave 3C/3F company-policy shape."""
    rules = pack.get("mandatory_rules") or {}
    disabled = pack.get("disabled_fallbacks") or {}
    notice = pack.get("notice_rules") or {}
    retention = pack.get("retention") or {}
    settlement = pack.get("settlement_ownership") or {}
    service = pack.get("service_certificate") or {}
    return {
        "timezone": pack.get("timezone_default") or "Asia/Kuwait",
        "show_notice_hints": bool(notice.get("show_hints_default", disabled.get("show_notice_hints", False))),
        "notice_hint_monthly_days": int(notice.get("monthly_hint_days") or 90),
        "notice_hint_other_days": int(notice.get("other_hint_days") or 30),
        "notice_hint_label": notice.get("label"),
        "require_last_working_day": bool(rules.get("require_last_working_day", True)),
        "require_employment_classification": bool(rules.get("require_employment_classification", True)),
        "require_termination_case_class": bool(rules.get("require_termination_case_class", True)),
        "allow_reinstate_after_effective": bool(disabled.get("allow_reinstate_after_effective", False)),
        "document_retention_mode": retention.get("mode") or rules.get("document_retention_mode") or "retain",
        "document_retention_floor_days": int(
            rules.get("document_retention_floor_days") or retention.get("floor_days") or 365
        ),
        "auto_cancel_shifts": bool(disabled.get("auto_cancel_shifts", False)),
        "auto_decline_leave": bool(disabled.get("auto_decline_leave", False)),
        "monetary_calculations_owner": settlement.get("owner") or rules.get("monetary_calculations_owner") or "payroll",
        "settlement_packet_mode": settlement.get("mode") or rules.get("settlement_packet_mode") or "inputs_only",
        "service_certificate_default": bool(
            service.get("required_default", rules.get("service_certificate_default", True))
        ),
        "exceptional_cases_manual_only": bool(rules.get("exceptional_cases_manual_only", True)),
        "require_impact_ack": bool(rules.get("require_impact_ack", True)),
        "allow_self_approval": bool(rules.get("allow_self_approval", False)),
        "disclaimer": pack.get("disclaimer"),
        "ui_copy": pack.get("ui_copy") or {},
        "jurisdiction_mode": "policy_pack",
        "policy_pack_code": pack.get("pack_code"),
        "policy_pack_version": pack.get("policy_version"),
        "policy_pack_hash": pack.get("content_hash"),
        "wave": "wave3h",
    }


def notice_guidance_from_pack(
    *,
    pack: dict[str, Any],
    company_show_notice_hints: bool,
    contract_type: str | None,
    pay_frequency: str | None,
    probation_status: str | None,
    termination_case_class: str | None,
    exceptional_case: bool = False,
) -> dict[str, Any]:
    notice = pack.get("notice_rules") or {}
    reasons: list[str] = []
    show = bool(company_show_notice_hints and notice.get("show_hints_default") is not False)
    # company_show_notice_hints is the explicit UI enable; pack default is still fail-closed false.
    if not company_show_notice_hints:
        reasons.append("policy_show_notice_hints_false")
    applies = set(notice.get("applies_to_contract_types") or ["unlimited"])
    if str(contract_type or "") not in applies:
        reasons.append("contract_not_in_notice_scope")
    if notice.get("blocked_when_probation_active") and str(probation_status or "") == "active":
        reasons.append("probation_active")
    pay_ok = set(pack.get("pay_frequencies") or ["monthly", "other"])
    if str(pay_frequency or "") not in pay_ok:
        reasons.append("pay_frequency_unknown")
    exceptional = set(pack.get("exceptional_case_classes") or [])
    if notice.get("blocked_for_exceptional_cases") and (
        exceptional_case or str(termination_case_class or "") in exceptional
    ):
        reasons.append("exceptional_or_summary_case")
    eligible = len(reasons) == 0
    hint_days = None
    if eligible:
        hint_days = (
            int(notice.get("monthly_hint_days") or 90)
            if str(pay_frequency) == "monthly"
            else int(notice.get("other_hint_days") or 30)
        )
    return {
        "eligible": eligible,
        "show": eligible,
        "hint_days": hint_days,
        "block_reasons": reasons,
        "label": notice.get("label"),
        "pack_code": pack.get("pack_code"),
        "policy_version": pack.get("policy_version"),
    }


WAVE3H_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_policy_pack_registry (
  pack_code text NOT NULL,
  policy_version text NOT NULL,
  jurisdiction_code text NOT NULL,
  worker_category text NOT NULL,
  status text NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  effective_from date,
  effective_to date,
  content_hash text NOT NULL,
  pack_json jsonb NOT NULL,
  immutable boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (pack_code, policy_version),
  CHECK (status IN ('verified','reserved','deprecated','draft'))
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_tenant_overrides (
  company_code text NOT NULL,
  pack_code text NOT NULL,
  override_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, pack_code)
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_remediation (
  remediation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  employment_id uuid,
  person_id uuid,
  status text NOT NULL DEFAULT 'open',
  reason_code text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by_user_id uuid,
  CHECK (status IN ('open','resolved','cancelled'))
);

CREATE INDEX IF NOT EXISTS employee_policy_pack_remediation_open_idx
  ON employee_policy_pack_remediation (company_code, status)
  WHERE status = 'open';

ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS jurisdiction_code text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS worker_category text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_code text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_version text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_hash text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_status text;
-- policy_pack_status: resolved | remediation | unsupported | reserved

ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_code text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_version text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_hash text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_frozen_at timestamptz;

CREATE TABLE IF NOT EXISTS employee_lifecycle_policy_freezes (
  freeze_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  request_id uuid NOT NULL,
  case_id uuid,
  employee_key text NOT NULL,
  employment_id uuid,
  pack_code text NOT NULL,
  policy_version text NOT NULL,
  content_hash text NOT NULL,
  pack_snapshot jsonb NOT NULL,
  frozen_at timestamptz NOT NULL DEFAULT now(),
  frozen_by_user_id uuid,
  UNIQUE (company_code, request_id)
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_migration_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'applied',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
"""


def ensure_wave3h_schema(cur) -> None:
    cur.execute(WAVE3H_SCHEMA_SQL)
    # Seed registry from in-process catalog (immutable insert-once per version).
    for code, pack in PACK_CATALOG.items():
        cur.execute(
            """
            INSERT INTO employee_policy_pack_registry (
              pack_code, policy_version, jurisdiction_code, worker_category,
              status, enabled, effective_from, effective_to, content_hash, pack_json, immutable
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,true)
            ON CONFLICT (pack_code, policy_version) DO NOTHING
            """,
            (
                pack["pack_code"],
                pack["policy_version"],
                pack["jurisdiction_code"],
                pack["worker_category"],
                pack["status"],
                bool(pack.get("enabled")),
                pack.get("effective_from"),
                pack.get("effective_to"),
                pack["content_hash"],
                json.dumps(pack, default=str),
            ),
        )
    cur.execute(
        """
        INSERT INTO employee_policy_pack_schema_meta (schema_name, schema_version)
        VALUES ('employees360_wave3h', %s)
        ON CONFLICT (schema_name) DO UPDATE
          SET schema_version=EXCLUDED.schema_version, applied_at=now()
        """,
        (SCHEMA_VERSION,),
    )


def load_tenant_override(cur, *, company_code: str, pack_code: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT override_json FROM employee_policy_pack_tenant_overrides
        WHERE company_code=%s AND pack_code=%s
        """,
        (str(company_code).upper(), str(pack_code).upper()),
    )
    row = cur.fetchone()
    if not row:
        return {}
    raw = row["override_json"] if isinstance(row, dict) else row[0]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return dict(raw or {})


def resolve_employment_pack(
    legacy: Any,
    *,
    company_code: str,
    employment: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    require_resolved: bool = True,
) -> dict[str, Any]:
    """Resolve exactly one active pack for an employment. Fail closed if uncertain."""
    company = str(company_code).upper()
    payload = payload or {}
    employment = employment or {}
    if "jurisdiction_code" in payload or "work_country" in payload or "jurisdiction" in payload or "employment_country" in payload or "country_code" in payload:
        jur = (
            payload.get("jurisdiction_code")
            or payload.get("work_country")
            or payload.get("jurisdiction")
            or payload.get("employment_country")
            or payload.get("country_code")
        )
    else:
        jur = employment.get("jurisdiction_code")
    if "worker_category" in payload:
        cat = payload.get("worker_category")
    else:
        cat = employment.get("worker_category")
    # Explicit empty strings are missing (fail closed) — never silently inherit conflicting blanks.
    if isinstance(jur, str) and not jur.strip():
        jur = None
    if isinstance(cat, str) and not cat.strip():
        cat = None
    # If employment already resolved to a verified pack, trust stored binding unless payload conflicts.
    stored_code = employment.get("policy_pack_code")
    stored_ver = employment.get("policy_pack_version")
    stored_status = str(employment.get("policy_pack_status") or "")
    if stored_code and stored_status == "resolved" and not (payload.get("jurisdiction_code") or payload.get("worker_category") or payload.get("work_country")):
        pack = get_pack(str(stored_code), version=str(stored_ver) if stored_ver else None)
        if not pack or not pack.get("enabled"):
            return {
                "ok": False,
                "error": "stored_pack_unavailable",
                "message": "Stored policy pack is no longer available.",
                "pack_code": stored_code,
                "policy_version": stored_ver,
            }
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_wave3h_schema(cur)
                override = load_tenant_override(cur, company_code=company, pack_code=str(stored_code))
            conn.commit()
        effective = merge_tenant_override(pack, override)
        return {
            "ok": True,
            "pack_code": stored_code,
            "policy_version": stored_ver or pack["policy_version"],
            "content_hash": pack["content_hash"],
            "pack": effective,
            "base_pack": pack,
            "jurisdiction_code": pack.get("jurisdiction_code"),
            "worker_category": pack.get("worker_category"),
            "from_stored": True,
        }

    resolved = resolve_pack_code(jurisdiction_code=jur, worker_category=cat)
    if not resolved.get("ok"):
        if require_resolved:
            return resolved
        return resolved
    pack = resolved["pack"]
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3h_schema(cur)
            override = load_tenant_override(cur, company_code=company, pack_code=pack["pack_code"])
        conn.commit()
    effective = merge_tenant_override(pack, override)
    return {
        **resolved,
        "pack": effective,
        "base_pack": pack,
        "from_stored": False,
    }


def assert_pack_resolved(legacy: Any, resolution: dict[str, Any]) -> dict[str, Any]:
    if resolution.get("ok"):
        return resolution
    err = resolution.get("error") or "policy_pack_unresolved"
    raise legacy.HTTPException(
        status_code=422,
        detail={
            "error": err,
            "message": resolution.get("message") or "Policy pack could not be resolved.",
            "jurisdiction_code": resolution.get("jurisdiction_code"),
            "worker_category": resolution.get("worker_category"),
            "pack_code": resolution.get("pack_code"),
            "remediation": bool(resolution.get("remediation")),
            "ui_copy": (get_pack("KW_PRIVATE_SECTOR") or {}).get("ui_copy", {}).get(
                "unsupported_pack" if err == "pack_not_implemented" else "remediation_required"
            ),
        },
    )


def freeze_pack_on_request(
    cur,
    *,
    company_code: str,
    request_id: str,
    case_id: str | None,
    employee_key: str,
    employment_id: str | None,
    pack: dict[str, Any],
    frozen_by_user_id: str | None,
) -> dict[str, Any]:
    """Immutable freeze of pack code+version+hash on an approved lifecycle request."""
    company = str(company_code).upper()
    # Base identity from catalog hash — historical events keep this even if catalog later gains v2.
    base = get_pack(str(pack.get("pack_code")), version=str(pack.get("policy_version"))) or pack
    snapshot = {
        "pack_code": base.get("pack_code"),
        "policy_version": base.get("policy_version"),
        "content_hash": base.get("content_hash"),
        "jurisdiction_code": base.get("jurisdiction_code"),
        "worker_category": base.get("worker_category"),
        "mandatory_rules": pack.get("mandatory_rules"),
        "notice_rules": pack.get("notice_rules"),
        "exceptional_case_classes": pack.get("exceptional_case_classes"),
        "settlement_ownership": pack.get("settlement_ownership"),
        "retention": pack.get("retention"),
        "service_certificate": pack.get("service_certificate"),
        "disabled_fallbacks": pack.get("disabled_fallbacks"),
        "source_refs": base.get("source_refs"),
        "frozen_wave": SCHEMA_VERSION,
    }
    cur.execute(
        """
        INSERT INTO employee_lifecycle_policy_freezes (
          company_code, request_id, case_id, employee_key, employment_id,
          pack_code, policy_version, content_hash, pack_snapshot, frozen_by_user_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (company_code, request_id) DO NOTHING
        RETURNING *
        """,
        (
            company,
            request_id,
            case_id,
            employee_key,
            employment_id,
            snapshot["pack_code"],
            snapshot["policy_version"],
            snapshot["content_hash"],
            json.dumps(snapshot, default=str),
            frozen_by_user_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            SELECT * FROM employee_lifecycle_policy_freezes
            WHERE company_code=%s AND request_id=%s
            """,
            (company, request_id),
        )
        row = cur.fetchone()
    cur.execute(
        """
        UPDATE employee_lifecycle_requests SET
          policy_pack_code=%s,
          policy_pack_version=%s,
          policy_pack_hash=%s,
          policy_pack_frozen_at=COALESCE(policy_pack_frozen_at, now()),
          updated_at=now()
        WHERE company_code=%s AND request_id=%s
        """,
        (
            snapshot["pack_code"],
            snapshot["policy_version"],
            snapshot["content_hash"],
            company,
            request_id,
        ),
    )
    return dict(row) if row else snapshot


def bind_employment_pack(
    cur,
    *,
    company_code: str,
    employment_id: str,
    resolution: dict[str, Any],
) -> None:
    if not resolution.get("ok"):
        status = "remediation" if resolution.get("remediation") else "unsupported"
        if resolution.get("error") == "pack_not_implemented":
            status = "reserved"
        cur.execute(
            """
            UPDATE employee_employments SET
              jurisdiction_code=%s,
              worker_category=%s,
              policy_pack_code=%s,
              policy_pack_version=NULL,
              policy_pack_hash=NULL,
              policy_pack_status=%s,
              updated_at=now()
            WHERE company_code=%s AND employment_id=%s
            """,
            (
                resolution.get("jurisdiction_code"),
                resolution.get("worker_category"),
                resolution.get("pack_code"),
                status,
                str(company_code).upper(),
                employment_id,
            ),
        )
        return
    pack = resolution["pack"]
    base = resolution.get("base_pack") or pack
    cur.execute(
        """
        UPDATE employee_employments SET
          jurisdiction_code=%s,
          worker_category=%s,
          policy_pack_code=%s,
          policy_pack_version=%s,
          policy_pack_hash=%s,
          policy_pack_status='resolved',
          updated_at=now()
        WHERE company_code=%s AND employment_id=%s
        """,
        (
            resolution.get("jurisdiction_code") or base.get("jurisdiction_code"),
            resolution.get("worker_category") or base.get("worker_category"),
            base.get("pack_code"),
            base.get("policy_version"),
            base.get("content_hash"),
            str(company_code).upper(),
            employment_id,
        ),
    )


def open_remediation(
    cur,
    *,
    company_code: str,
    employee_key: str | None,
    employment_id: str | None,
    person_id: str | None,
    reason_code: str,
    detail: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO employee_policy_pack_remediation (
          company_code, employee_key, employment_id, person_id, reason_code, detail
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            str(company_code).upper(),
            employee_key,
            employment_id,
            person_id,
            reason_code,
            json.dumps(detail, default=str),
        ),
    )


def migrate_company_to_kw_private_sector(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
    eligible_only: bool = True,
) -> dict[str, Any]:
    """Map eligible employments to KW_PRIVATE_SECTOR. Uncertain → remediation (never silent)."""
    company = str(company_code).upper()
    pack = get_pack("KW_PRIVATE_SECTOR")
    assert pack
    stats = {
        "resolved": 0,
        "already_resolved": 0,
        "remediation": 0,
        "skipped": 0,
        "total": 0,
    }
    details: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3h_schema(cur)
            cur.execute(
                """
                SELECT journal_id FROM employee_policy_pack_migration_journal
                WHERE company_code=%s AND idempotency_key=%s
                """,
                (company, idempotency_key),
            )
            if cur.fetchone():
                conn.commit()
                return {"ok": True, "idempotent": True, "stats": stats}

            cur.execute(
                """
                SELECT e.*, m.employee_key
                FROM employee_employments e
                LEFT JOIN employee_key_authority_map m
                  ON m.company_code=e.company_code AND m.employment_id=e.employment_id
                 AND m.mapping_status='active'
                WHERE e.company_code=%s
                ORDER BY e.created_at ASC NULLS LAST
                """,
                (company,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            stats["total"] = len(rows)
            for row in rows:
                emp_id = str(row["employment_id"])
                if row.get("policy_pack_status") == "resolved" and row.get("policy_pack_code") == "KW_PRIVATE_SECTOR":
                    stats["already_resolved"] += 1
                    continue
                jur = normalize_jurisdiction(row.get("jurisdiction_code"))
                cat = normalize_worker_category(row.get("worker_category"))
                # Eligible WATHEFNI private-sector default: missing fields on known KW tenant may be
                # proposed only when company is WATHEFNI and no conflicting jurisdiction is present.
                if not jur and not cat and company == "WATHEFNI" and eligible_only:
                    # Still do NOT silently classify — open remediation proposing KW_PRIVATE_SECTOR.
                    open_remediation(
                        cur,
                        company_code=company,
                        employee_key=row.get("employee_key"),
                        employment_id=emp_id,
                        person_id=str(row["person_id"]) if row.get("person_id") else None,
                        reason_code="uncertain_jurisdiction_or_category",
                        detail={
                            "proposed_pack": "KW_PRIVATE_SECTOR",
                            "message": (
                                "Missing jurisdiction_code/worker_category. "
                                "HR must confirm KW private sector before binding."
                            ),
                        },
                    )
                    cur.execute(
                        """
                        UPDATE employee_employments SET
                          policy_pack_status='remediation',
                          updated_at=now()
                        WHERE company_code=%s AND employment_id=%s
                        """,
                        (company, emp_id),
                    )
                    stats["remediation"] += 1
                    details.append({"employment_id": emp_id, "status": "remediation"})
                    continue
                if jur == "KW" and cat == "private_sector":
                    bind_employment_pack(
                        cur,
                        company_code=company,
                        employment_id=emp_id,
                        resolution={
                            "ok": True,
                            "pack": pack,
                            "base_pack": pack,
                            "jurisdiction_code": "KW",
                            "worker_category": "private_sector",
                        },
                    )
                    stats["resolved"] += 1
                    details.append({"employment_id": emp_id, "status": "resolved"})
                    continue
                if jur and cat:
                    resolution = resolve_pack_code(jurisdiction_code=jur, worker_category=cat)
                    if resolution.get("ok"):
                        bind_employment_pack(
                            cur,
                            company_code=company,
                            employment_id=emp_id,
                            resolution={**resolution, "base_pack": resolution["pack"]},
                        )
                        stats["resolved"] += 1
                    else:
                        bind_employment_pack(cur, company_code=company, employment_id=emp_id, resolution=resolution)
                        open_remediation(
                            cur,
                            company_code=company,
                            employee_key=row.get("employee_key"),
                            employment_id=emp_id,
                            person_id=str(row["person_id"]) if row.get("person_id") else None,
                            reason_code=str(resolution.get("error") or "unresolved"),
                            detail=resolution,
                        )
                        stats["remediation"] += 1
                    details.append({"employment_id": emp_id, "status": resolution.get("error") or "ok"})
                    continue
                open_remediation(
                    cur,
                    company_code=company,
                    employee_key=row.get("employee_key"),
                    employment_id=emp_id,
                    person_id=str(row["person_id"]) if row.get("person_id") else None,
                    reason_code="uncertain_jurisdiction_or_category",
                    detail={"jurisdiction_code": jur, "worker_category": cat},
                )
                cur.execute(
                    """
                    UPDATE employee_employments SET
                      jurisdiction_code=COALESCE(%s, jurisdiction_code),
                      worker_category=COALESCE(%s, worker_category),
                      policy_pack_status='remediation',
                      updated_at=now()
                    WHERE company_code=%s AND employment_id=%s
                    """,
                    (jur, cat, company, emp_id),
                )
                stats["remediation"] += 1
                details.append({"employment_id": emp_id, "status": "remediation"})

            cur.execute(
                """
                INSERT INTO employee_policy_pack_migration_journal (
                  company_code, action, idempotency_key, before_json, after_json, evidence
                ) VALUES (%s,'migrate_kw_private_sector',%s,'{}'::jsonb,%s::jsonb,%s::jsonb)
                """,
                (
                    company,
                    idempotency_key,
                    json.dumps({"stats": stats}, default=str),
                    json.dumps({"details_sample": details[:50], "pack_hash": pack["content_hash"]}, default=str),
                ),
            )
            conn.commit()
    return {"ok": True, "idempotent": False, "stats": stats, "pack_code": "KW_PRIVATE_SECTOR", "policy_version": pack["policy_version"]}


def confirm_employment_kw_private_sector(
    legacy: Any,
    *,
    company_code: str,
    employment_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """HR confirmation path: bind KW_PRIVATE_SECTOR after explicit confirmation (not silent)."""
    company = str(company_code).upper()
    pack = get_pack("KW_PRIVATE_SECTOR")
    assert pack
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3h_schema(cur)
            bind_employment_pack(
                cur,
                company_code=company,
                employment_id=employment_id,
                resolution={
                    "ok": True,
                    "pack": pack,
                    "base_pack": pack,
                    "jurisdiction_code": "KW",
                    "worker_category": "private_sector",
                },
            )
            cur.execute(
                """
                UPDATE employee_policy_pack_remediation SET
                  status='resolved', resolved_at=now(), resolved_by_user_id=%s
                WHERE company_code=%s AND employment_id=%s AND status='open'
                """,
                (actor_user_id, company, employment_id),
            )
            conn.commit()
    return {
        "ok": True,
        "employment_id": employment_id,
        "pack_code": "KW_PRIVATE_SECTOR",
        "policy_version": pack["policy_version"],
        "content_hash": pack["content_hash"],
    }


def wave3h_enabled(company_code: str | None = None) -> bool:
    raw = str(os.environ.get("WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H") or "on").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    allow = str(os.environ.get("WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H_COMPANIES") or "WATHEFNI").strip()
    if allow in {"*", "ALL", "all"}:
        return True
    if not company_code:
        return True
    allowed = {c.strip().upper() for c in allow.split(",") if c.strip()}
    return str(company_code).upper() in allowed
