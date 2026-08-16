"""Payroll Authority P6 — Kuwait production readiness + controlled Mode A entitlement.

Company-level entitlement replaces blanket SYNTHETIC_ONLY as the production gate:
  disabled | preview_only | authoritative_allowlisted | authoritative

Never infers money authority from module enablement alone.
Payment/WPS remain disabled. No invented payment_date.
Does not globally unlock Mode A for all tenants.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import payroll_authority_mode_a_p5 as p5
import payroll_authority_snapshot_p1 as p1
import payroll_authority_wave1 as pyw1
import payroll_components_policy_p3 as p3
import payroll_input_snapshot_p2 as p2
import payroll_statutory_baseline_p4b as p4b

try:
    import payroll_authority_p6_oracle as oracle
except Exception:  # pragma: no cover
    oracle = None  # type: ignore

PAYROLL_AUTHORITY_P6_VERSION = "1.0.0"
ENTITLEMENT_SCHEMA = "wathefni.payroll_mode_a_entitlement.v1"
SETUP_SCHEMA_VERSION = "payroll_setup_console_contract_v1"

STATE_DISABLED = "disabled"
STATE_PREVIEW = "preview_only"
STATE_ALLOWLISTED = "authoritative_allowlisted"
STATE_AUTHORITATIVE = "authoritative"
AUTHORITATIVE_STATES = {STATE_ALLOWLISTED, STATE_AUTHORITATIVE}

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_authority_production_p6_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
SETUP_SCHEMA_PATH_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "ops" / "payroll_authority_p6_setup_console_schema_v1.json",
    Path(__file__).resolve().parent / "ops" / "payroll_authority_p6_setup_console_schema_v1.json",
]
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")
DEFAULT_MARKERS = (
    "PYW1", "PYP1", "PYP2", "PYP3", "PYP4A", "PYP4B", "PYP5", "PYP6",
    "PYAUTH", "PYSTAT", "PYINPUT", "PYCALC",
)


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p6_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P6", default=True)


def payroll_authority_p6_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p6_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P6_COMPANIES") or "WATHEFNI").strip()
    return (company_code or "").upper() in {p.strip().upper() for p in raw.split(",") if p.strip()}


def payroll_authority_p6_synthetic_qualification_allowed() -> bool:
    """Synthetic fixtures remain valid for qualification under any entitlement."""
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P6_ALLOW_SYNTHETIC_QUALIFICATION", default=True)


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P6_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_MARKERS


def is_p6_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    return any(m and m in key for m in synthetic_key_markers()) or p5.is_p5_synthetic_employee(employee_key=key)


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p6_version": PAYROLL_AUTHORITY_P6_VERSION,
        "entitlement_schema": ENTITLEMENT_SCHEMA,
        "production_entitlement_model": True,
        "global_synthetic_only_replaced_by_company_entitlement": True,
        "default_tenant_mode_a": STATE_DISABLED,
        "preview_remains_preview": True,
        "period_close_is_money_seal": False,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "mode_b_external_supported": True,
        "unrestricted_customer_rollout": False,
        "p1_p5_preserved": True,
    }


def remaining_gaps_before_unrestricted_rollout() -> list[str]:
    return [
        "Per-customer legal/ops onboarding checklist beyond WATHEFNI canary",
        "Broader multi-tenant residual-zero evidence packs",
        "Setup Console UX implementation of setup schema (contract only in P6)",
        "Payment/WPS program still separate — not required for Mode A authority",
        "Counsel acknowledgement workflow for company-specific statutory extensions",
        "Employee App payslip UX polish outside P0/P0.1 already frozen",
    ]


def ensure_payroll_production_p6_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    p5.ensure_payroll_mode_a_finalize_schema(cur)
    if SCHEMA_SQL.strip():
        lock_id = 770_900_017
        cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        try:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            cur.execute(SCHEMA_SQL)
        finally:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            except Exception:
                pass
    _SCHEMA_READY = True


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(zip([d[0] for d in cur.description], row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall() or []
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [dict(r) for r in rows]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def _json_safe(obj: Any) -> Any:
    return p1._json_safe(obj)  # noqa: SLF001


def _record_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_mode_a_entitlement_events (
          company_code, event_type, payload, created_by_phone
        ) VALUES (%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


# --------------------------------------------------------------------------- Setup Console schema contract


def setup_console_schema_contract() -> dict[str, Any]:
    for p in SETUP_SCHEMA_PATH_CANDIDATES:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    # Inline fallback if file not yet deployed
    return {
        "schema_version": SETUP_SCHEMA_VERSION,
        "required": [
            {"key": "payroll_mode", "label_en": "Payroll money authority mode", "values": ["native", "external", "parallel_shadow"]},
            {"key": "payroll_frequency", "label_en": "Payroll frequency", "values": ["monthly"]},
            {"key": "period_cutoff", "label_en": "Period cut-off settings"},
            {"key": "attendance_payroll_mode", "label_en": "Attendance payroll mode"},
            {"key": "salary_component_structure", "label_en": "Salary / component structure"},
            {"key": "approval_sod_chain", "label_en": "Approval / SOD chain"},
            {"key": "mode_a_entitlement_opt_in", "label_en": "Explicit Mode A opt-in"},
        ],
        "optional": [
            {"key": "working_calendar"},
            {"key": "lateness_absence_policies"},
            {"key": "ot_eligibility"},
            {"key": "employee_statutory_classifications"},
            {"key": "pifss_wage_bases"},
            {"key": "special_regime_flags"},
            {"key": "variance_thresholds"},
        ],
        "advanced": [
            {"key": "enterprise_sod_strict"},
            {"key": "employee_allowlist"},
            {"key": "controlled_policy_overrides"},
            {"key": "parallel_shadow_mode_b"},
        ],
        "wathefni_owned": [
            "kuwait_statutory_baseline_version",
            "calculation_engine",
            "authority_sealing_rules",
            "statutory_provenance",
        ],
        "sme_defaults": {
            "attendance_payroll_mode": "informational",
            "require_review_step": True,
            "allow_approver_as_finalizer": True,
            "hide_advanced_until_needed": True,
        },
    }


# --------------------------------------------------------------------------- Entitlement


def get_company_entitlement(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    cur.execute("SELECT * FROM payroll_company_mode_a_entitlement WHERE company_code=%s", (company,))
    row = _row(cur)
    if row:
        return row
    return {
        "company_code": company,
        "entitlement_state": STATE_DISABLED,
        "mode_a_opt_in": False,
        "payroll_mode": "native",
        "readiness_status": "incomplete",
        "readiness_payload": {},
        "metadata": {},
    }


def get_variance_policy(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    cur.execute("SELECT * FROM payroll_mode_a_variance_policy WHERE company_code=%s", (company,))
    row = _row(cur)
    if row:
        return row
    return {
        "company_code": company,
        "gross_delta_abs": Decimal("50"),
        "net_delta_abs": Decimal("50"),
        "gross_delta_pct": Decimal("0.10"),
        "net_delta_pct": Decimal("0.10"),
        "flag_component_add_remove": True,
        "flag_zero_or_negative_net": True,
    }


def upsert_variance_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str | None,
    gross_delta_abs: float | None = None,
    net_delta_abs: float | None = None,
    gross_delta_pct: float | None = None,
    net_delta_pct: float | None = None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    cur_pol = get_variance_policy(cur, company_code=company)
    cur.execute(
        """
        INSERT INTO payroll_mode_a_variance_policy (
          company_code, gross_delta_abs, net_delta_abs, gross_delta_pct, net_delta_pct, updated_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code) DO UPDATE SET
          gross_delta_abs=EXCLUDED.gross_delta_abs,
          net_delta_abs=EXCLUDED.net_delta_abs,
          gross_delta_pct=EXCLUDED.gross_delta_pct,
          net_delta_pct=EXCLUDED.net_delta_pct,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            float(gross_delta_abs if gross_delta_abs is not None else cur_pol.get("gross_delta_abs") or 50),
            float(net_delta_abs if net_delta_abs is not None else cur_pol.get("net_delta_abs") or 50),
            float(gross_delta_pct if gross_delta_pct is not None else cur_pol.get("gross_delta_pct") or 0.10),
            float(net_delta_pct if net_delta_pct is not None else cur_pol.get("net_delta_pct") or 0.10),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        company_code=company,
        event_type="variance_policy_upsert",
        payload={"reason": str(reason).strip(), "policy": _json_safe(row)},
        actor_phone=actor_phone,
    )
    return {"ok": True, "policy": _json_safe(row), **honesty_payload()}


def list_active_allowlist(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    ensure_payroll_production_p6_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_mode_a_employee_allowlist
        WHERE company_code=%s AND status='active'
        ORDER BY employee_key
        """,
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def add_employee_allowlist(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    key = str(employee_key or "").strip()
    if not key:
        return {"ok": False, "error": "employee_key_required"}
    cur.execute(
        """
        INSERT INTO payroll_mode_a_employee_allowlist (
          company_code, employee_key, status, reason, added_by_phone
        ) VALUES (%s,%s,'active',%s,%s)
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          status='active',
          reason=EXCLUDED.reason,
          added_by_phone=EXCLUDED.added_by_phone,
          added_at=now(),
          revoked_at=NULL,
          revoked_by_phone=NULL
        RETURNING *
        """,
        (company, key, str(reason).strip(), digits_phone(actor_phone)),
    )
    row = _row(cur)
    _record_event(
        cur,
        company_code=company,
        event_type="employee_allowlist_add",
        payload={"employee_key": key, "reason": str(reason).strip()},
        actor_phone=actor_phone,
    )
    return {"ok": True, "allowlist": _json_safe(row), **honesty_payload()}


def employee_on_allowlist(cur: Any, *, company_code: str, employee_key: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM payroll_mode_a_employee_allowlist
        WHERE company_code=%s AND employee_key=%s AND status='active'
        """,
        ((company_code or "").upper(), str(employee_key or "")),
    )
    return cur.fetchone() is not None


def employee_production_mutations_allowed(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> bool:
    """When True, layer SYNTHETIC_ONLY gates may admit this employee (entitlement path)."""
    key = str(employee_key or "")
    if is_p6_synthetic_employee(employee_key=key):
        return True
    if not payroll_authority_p6_enabled_for_company(company_code):
        return False
    ent = get_company_entitlement(cur, company_code=company_code)
    state = str(ent.get("entitlement_state") or STATE_DISABLED)
    if state == STATE_AUTHORITATIVE:
        return True
    if state == STATE_ALLOWLISTED:
        return employee_on_allowlist(cur, company_code=company_code, employee_key=key)
    return False


def employee_may_authoritative_seal(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    """Production gate replacing blanket SYNTHETIC_ONLY for Mode A seal."""
    company = (company_code or "").upper()
    key = str(employee_key or "")
    synthetic = is_p6_synthetic_employee(employee_key=key)

    if not payroll_authority_p6_enabled_for_company(company):
        # Fall back to P5 synthetic gate
        allowed = (not p5.payroll_authority_p5_synthetic_only()) or synthetic
        return {
            "ok": allowed,
            "gate": "p5_synthetic_fallback",
            "synthetic": synthetic,
            "reason": None if allowed else "nonsynthetic_employee_blocked",
        }

    ent = get_company_entitlement(cur, company_code=company)
    state = str(ent.get("entitlement_state") or STATE_DISABLED)
    if synthetic and payroll_authority_p6_synthetic_qualification_allowed():
        return {"ok": True, "gate": "synthetic_qualification", "synthetic": True, "entitlement_state": state}

    if state in (STATE_DISABLED, STATE_PREVIEW):
        return {
            "ok": False,
            "gate": "entitlement",
            "synthetic": synthetic,
            "entitlement_state": state,
            "reason": "company_not_authoritative_entitled",
            "message_en": "Company has not opted into OctoHR Mode A money authority.",
            "message_ar": "الشركة لم تُفعّل سلطة الرواتب في OctoHR.",
        }
    if state == STATE_ALLOWLISTED:
        on = employee_on_allowlist(cur, company_code=company, employee_key=key)
        return {
            "ok": on,
            "gate": "allowlist",
            "synthetic": synthetic,
            "entitlement_state": state,
            "reason": None if on else "employee_not_on_authoritative_allowlist",
            "message_en": None
            if on
            else "Employee is not on the Mode A authoritative allowlist for this company.",
        }
    if state == STATE_AUTHORITATIVE:
        return {"ok": True, "gate": "company_authoritative", "synthetic": synthetic, "entitlement_state": state}
    return {"ok": False, "gate": "unknown", "reason": "invalid_entitlement_state", "entitlement_state": state}


# --------------------------------------------------------------------------- Readiness validator


def _issue(
    *,
    code: str,
    severity: str,
    message_en: str,
    message_ar: str | None = None,
    field: str | None = None,
    how_to_fix: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "field": field,
        "message_en": message_en,
        "message_ar": message_ar or message_en,
        "how_to_fix": how_to_fix,
    }


def validate_payroll_readiness(cur: Any, *, company_code: str) -> dict[str, Any]:
    """Actionable readiness for Mode A activation — not technical exceptions."""
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    issues: list[dict[str, Any]] = []
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    mode = str(settings.get("payroll_mode") or "")
    if mode not in ("native", "parallel_shadow", "external"):
        issues.append(
            _issue(
                code="payroll_mode_missing",
                severity="blocked",
                field="payroll_mode",
            message_en="Choose payroll mode: OctoHR (native), external, or parallel shadow.",
            message_ar="اختر وضع الرواتب: OctoHR أو خارجي أو ظل موازي.",
                how_to_fix="Set payroll mode in company payroll settings.",
            )
        )

    att_mode = None
    try:
        att_mode = p2.resolve_attendance_payroll_mode(cur, company_code=company)
    except Exception:
        att_mode = settings.get("attendance_payroll_mode")
    if not att_mode:
        issues.append(
            _issue(
                code="attendance_payroll_mode_missing",
                severity="blocked",
                field="attendance_payroll_mode",
                message_en="Set how attendance affects payroll (informational or deduction modes).",
                message_ar="حدد كيف يؤثر الحضور على الرواتب.",
                how_to_fix="Configure attendance payroll mode.",
            )
        )

    # Approved company policy
    cur.execute(
        """
        SELECT policy_version_id::text, status, effective_from
        FROM payroll_company_policy_versions
        WHERE company_code=%s AND status='approved'
        ORDER BY effective_from DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (company,),
    )
    policy = _row(cur)
    if not policy:
        issues.append(
            _issue(
                code="approved_company_policy_missing",
                severity="blocked",
                field="company_payroll_policy",
                message_en="Approve a company payroll policy version before Mode A authority.",
                message_ar="يجب اعتماد سياسة رواتب للشركة قبل تفعيل السلطة.",
                how_to_fix="Create and approve a P3 company payroll policy.",
            )
        )

    # Component catalog presence (at least one company component or contracts exist)
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND status='approved'",
        (company,),
    )
    n_contracts = int((_row(cur) or {}).get("n") or 0)
    if n_contracts < 1:
        issues.append(
            _issue(
                code="compensation_structure_missing",
                severity="blocked",
                field="salary_component_structure",
                message_en="At least one approved employee compensation contract is required.",
                message_ar="يلزم وجود عقد تعويض معتمد لموظف واحد على الأقل.",
                how_to_fix="Approve compensation for employees included in payroll.",
            )
        )

    # Finalize / SOD policy
    fin = p5.get_company_finalize_policy(cur, company_code=company)
    if not fin:
        issues.append(
            _issue(
                code="finalize_sod_policy_missing",
                severity="blocked",
                field="approval_sod_chain",
                message_en="Configure payroll approval / segregation-of-duties policy.",
                message_ar="اضبط سلسلة اعتماد الرواتب وفصل الصلاحيات.",
                how_to_fix="Save Mode A finalize policy (SME defaults are fine).",
            )
        )

    # Statutory baseline package active
    try:
        rule = p4b.resolve_public_baseline_rule(cur, rule_family="ot_ordinary", as_of=date.today(), sector="private")
        if not rule:
            issues.append(
                _issue(
                    code="kuwait_statutory_baseline_missing",
                    severity="blocked",
                    field="kuwait_statutory_baseline",
                    message_en="Kuwait public statutory baseline is not available for this environment.",
                    message_ar="خط الأساس القانوني الكويتي غير متوفر.",
            how_to_fix="Ensure P4B KW_PUBLIC_BASELINE is activated (OctoHR-owned).",
                )
            )
    except Exception as exc:
        issues.append(
            _issue(
                code="kuwait_statutory_baseline_error",
                severity="blocked",
                field="kuwait_statutory_baseline",
                message_en=f"Could not resolve Kuwait statutory baseline: {exc}",
                how_to_fix="Activate P4B public baseline.",
            )
        )

    # Mode A opt-in is separate — missing opt-in is blocked for authoritative states only
    ent = get_company_entitlement(cur, company_code=company)
    if mode == "external" and str(ent.get("entitlement_state")) in AUTHORITATIVE_STATES:
        issues.append(
            _issue(
                code="external_mode_cannot_be_mode_a_authority",
                severity="blocked",
                field="payroll_mode",
                message_en="External payroll mode uses Mode B money authority; do not entitle Mode A seal.",
            message_ar="الوضع الخارجي يستخدم سلطة خارجية ولا يُختم كسلطة OctoHR.",
                how_to_fix="Keep Mode B for external, or switch payroll mode to native for Mode A.",
            )
        )

    # Phase 3A — working calendar required for native Mode A (Mode B unaffected).
    if mode in ("native", "parallel_shadow"):
        try:
            import setup_console_payroll_phase3a as p3a

            extras = p3a.parse_setup_extras(settings)
            if not extras.get("calendar_configured") or not extras.get("weekend_days"):
                issues.append(
                    _issue(
                        code="working_calendar_missing",
                        severity="blocked",
                        field="working_calendar",
                        message_en="Set the company working calendar (working days and weekly rest).",
                        message_ar="اضبط تقويم العمل للشركة (أيام العمل والراحة الأسبوعية).",
                        how_to_fix="Choose weekly rest days in Setup Console Payroll.",
                    )
                )
            # Statutory gaps block authoritative entitlement readiness only.
            if str(ent.get("entitlement_state") or "") in AUTHORITATIVE_STATES:
                gaps = p3a.statutory_gap_summary(cur, company_code=company, limit=3)
                if gaps.get("incomplete"):
                    issues.append(
                        _issue(
                            code="statutory_employee_inputs_incomplete",
                            severity="blocked",
                            field="employee_statutory_classifications",
                            message_en=str(gaps.get("message_en") or "Complete employee statutory classifications."),
                            message_ar=str(gaps.get("message_ar") or ""),
                            how_to_fix="Classify employees and set PIFSS wage bases where required.",
                        )
                    )
        except Exception:
            pass

    blocked = [i for i in issues if i["severity"] == "blocked"]
    status = "ready" if not blocked else "blocked"
    payload = {
        "issues": issues,
        "settings": {
            "payroll_mode": mode,
            "attendance_payroll_mode": att_mode,
            "payment_processing": "disabled",
        },
        "approved_policy_version_id": (policy or {}).get("policy_version_id"),
        "approved_compensation_contracts": n_contracts,
        "finalize_policy_present": bool(fin),
        "statutory_baseline": p4b.POLICY_VERSION if hasattr(p4b, "POLICY_VERSION") else "KW_PUBLIC_BASELINE_v1.0.0",
        "setup_schema_version": SETUP_SCHEMA_VERSION,
    }
    fp = fingerprint_payload(payload)
    # Persist snapshot on entitlement row if exists
    cur.execute(
        """
        INSERT INTO payroll_company_mode_a_entitlement (
          company_code, entitlement_state, mode_a_opt_in, payroll_mode,
          readiness_status, readiness_fingerprint, readiness_payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (company_code) DO UPDATE SET
          readiness_status=EXCLUDED.readiness_status,
          readiness_fingerprint=EXCLUDED.readiness_fingerprint,
          readiness_payload=EXCLUDED.readiness_payload,
          payroll_mode=EXCLUDED.payroll_mode,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            str(ent.get("entitlement_state") or STATE_DISABLED),
            bool(ent.get("mode_a_opt_in")),
            mode or "native",
            status if status == "ready" else ("incomplete" if not blocked else "blocked"),
            fp,
            json.dumps(_json_safe(payload)),
        ),
    )
    ent_row = _row(cur)
    return {
        "ok": status == "ready",
        "readiness_status": "ready" if status == "ready" else ("blocked" if blocked else "incomplete"),
        "issues": issues,
        "blockers": blocked,
        "fingerprint": fp,
        "entitlement": _json_safe(ent_row),
        "setup_contract": setup_console_schema_contract(),
        **honesty_payload(),
    }


def set_company_mode_a_entitlement(
    cur: Any,
    *,
    company_code: str,
    entitlement_state: str,
    actor_phone: str | None,
    reason: str | None,
    require_readiness: bool = True,
) -> dict[str, Any]:
    """Explicit company opt-in. Never inferred from module enablement."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not payroll_authority_p6_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p6_disabled_for_company"}
    state = str(entitlement_state or "").strip().lower()
    if state not in {STATE_DISABLED, STATE_PREVIEW, STATE_ALLOWLISTED, STATE_AUTHORITATIVE}:
        return {"ok": False, "error": "invalid_entitlement_state", "allowed": sorted({STATE_DISABLED, STATE_PREVIEW, STATE_ALLOWLISTED, STATE_AUTHORITATIVE})}

    readiness = validate_payroll_readiness(cur, company_code=company_code)
    if require_readiness and state in AUTHORITATIVE_STATES and not readiness.get("ok"):
        return {
            "ok": False,
            "error": "payroll_readiness_incomplete",
            "message_en": "Complete required payroll setup before Mode A authoritative entitlement.",
            "readiness": readiness,
            **honesty_payload(),
        }

    settings = pyw1.ensure_company_settings(cur, company_code=company_code)
    if state in AUTHORITATIVE_STATES and str(settings.get("payroll_mode")) == "external":
        return {
            "ok": False,
            "error": "external_mode_cannot_entitle_mode_a",
            "message_en": "External Mode B companies keep money_authority=external.",
            **honesty_payload(),
        }

    company = (company_code or "").upper()
    prev = get_company_entitlement(cur, company_code=company)
    opt_in = state in AUTHORITATIVE_STATES or state == STATE_PREVIEW
    cur.execute(
        """
        INSERT INTO payroll_company_mode_a_entitlement (
          company_code, entitlement_state, mode_a_opt_in, payroll_mode,
          readiness_status, readiness_fingerprint, readiness_payload,
          opted_in_at, opted_in_by_phone, opted_in_reason, updated_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s::jsonb,
          CASE WHEN %s THEN now() ELSE NULL END,
          %s,%s,%s
        )
        ON CONFLICT (company_code) DO UPDATE SET
          entitlement_state=EXCLUDED.entitlement_state,
          mode_a_opt_in=EXCLUDED.mode_a_opt_in,
          payroll_mode=EXCLUDED.payroll_mode,
          readiness_status=EXCLUDED.readiness_status,
          readiness_fingerprint=EXCLUDED.readiness_fingerprint,
          readiness_payload=EXCLUDED.readiness_payload,
          opted_in_at=CASE WHEN EXCLUDED.mode_a_opt_in THEN COALESCE(payroll_company_mode_a_entitlement.opted_in_at, now()) ELSE NULL END,
          opted_in_by_phone=EXCLUDED.opted_in_by_phone,
          opted_in_reason=EXCLUDED.opted_in_reason,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            state,
            opt_in,
            str(settings.get("payroll_mode") or "native"),
            readiness.get("readiness_status"),
            readiness.get("fingerprint"),
            json.dumps(_json_safe({"issues": readiness.get("issues")})),
            state in AUTHORITATIVE_STATES,
            digits_phone(actor_phone),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        company_code=company,
        event_type="entitlement_set",
        payload={
            "from": prev.get("entitlement_state"),
            "to": state,
            "reason": str(reason).strip(),
            "readiness_ok": readiness.get("ok"),
        },
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "entitlement": _json_safe(row),
        "previous_state": prev.get("entitlement_state"),
        "readiness": readiness,
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- Exception-first review + variance


def classify_run_exceptions(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str,
    persist: bool = True,
) -> dict[str, Any]:
    """Bucket employees: ready / needs_review / blocked / changed_since_previous."""
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    calc = p3.get_calc_run(cur, company_code=company, calc_run_id=calc_run_id)
    if not calc:
        return {"ok": False, "error": "calc_run_not_found"}
    emp_results = p3.list_calc_employee_results(cur, company_code=company, calc_run_id=calc_run_id)
    gates = p5.evaluate_finalize_gates(cur, company_code=company, calc_run_id=calc_run_id)
    gate_by_emp: dict[str, list[dict[str, Any]]] = {}
    for b in gates.get("blockers") or []:
        key = str(b.get("employee_key") or "")
        gate_by_emp.setdefault(key, []).append(b)

    variance = compute_period_variance(
        cur,
        company_code=company,
        calc_run_id=calc_run_id,
        period_start=calc.get("period_start"),
        period_end=calc.get("period_end"),
    )
    var_by_emp = {str(v["employee_key"]): v for v in (variance.get("employees") or [])}

    items: list[dict[str, Any]] = []
    summary = {"ready": 0, "needs_review": 0, "blocked": 0, "changed_since_previous": 0}

    for er in emp_results:
        key = str(er.get("employee_key") or "")
        blockers = list(gate_by_emp.get(key) or [])
        if str(er.get("status")) != "ok":
            blockers.append({"code": "employee_calc_blocked", "status": er.get("status")})
        v = var_by_emp.get(key) or {}
        unusual = bool(v.get("needs_review"))
        if blockers:
            bucket = "blocked"
            severity = "blocked"
            code = str(blockers[0].get("code") or "blocked")
            msg = str(blockers[0].get("message") or blockers[0].get("code") or "Blocked")
        elif unusual:
            bucket = "needs_review"
            severity = "warning"
            code = str(v.get("primary_code") or "unusual_variance")
            msg = str(v.get("message_en") or "Unusual change vs previous period — review advised.")
        elif v.get("changed"):
            bucket = "changed_since_previous"
            severity = "changed"
            code = "changed_since_previous"
            msg = "Result differs from previous authoritative period."
        else:
            bucket = "ready"
            severity = "ready"
            code = "ready"
            msg = "Ready for approval."
        summary[bucket] = summary.get(bucket, 0) + 1
        item = {
            "employee_key": key,
            "bucket": bucket,
            "severity": severity,
            "code": code,
            "message_en": msg,
            "message_ar": msg,
            "advisory": bucket != "blocked",
            "source_refs": {
                "calc_run_id": calc_run_id,
                "blockers": blockers,
                "variance": v,
                "totals": er.get("totals"),
            },
        }
        items.append(item)

    if persist:
        cur.execute(
            "DELETE FROM payroll_mode_a_run_review_items WHERE company_code=%s AND calc_run_id=%s",
            (company, calc_run_id),
        )
        for it in items:
            cur.execute(
                """
                INSERT INTO payroll_mode_a_run_review_items (
                  company_code, calc_run_id, period_start, period_end, employee_key,
                  severity, bucket, code, message_en, message_ar, source_refs, advisory
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (
                    company,
                    calc_run_id,
                    calc.get("period_start"),
                    calc.get("period_end"),
                    it["employee_key"],
                    it["severity"],
                    it["bucket"],
                    it["code"],
                    it["message_en"],
                    it.get("message_ar"),
                    json.dumps(_json_safe(it["source_refs"])),
                    bool(it["advisory"]),
                ),
            )

    return {
        "ok": True,
        "calc_run_id": calc_run_id,
        "summary": summary,
        "items": _json_safe(items),
        "gates_ok": gates.get("ok"),
        "variance": variance,
        **honesty_payload(),
    }


def compute_period_variance(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str,
    period_start: Any = None,
    period_end: Any = None,
) -> dict[str, Any]:
    """Advisory variance vs previous authoritative sealed period. Never rewrites money."""
    ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    pol = get_variance_policy(cur, company_code=company)
    emp_results = p3.list_calc_employee_results(cur, company_code=company, calc_run_id=calc_run_id)
    employees_out: list[dict[str, Any]] = []

    for er in emp_results:
        key = str(er.get("employee_key") or "")
        totals = er.get("totals") or {}
        if isinstance(totals, str):
            try:
                totals = json.loads(totals)
            except Exception:
                totals = {}
        gross = Decimal(str(totals.get("gross") or er.get("totals_gross") or 0))
        net = Decimal(str(totals.get("net") or er.get("totals_net") or 0))

        cur.execute(
            """
            SELECT authority_snapshot_id::text, totals_gross, totals_net, period_start, period_end
            FROM payroll_authority_snapshots
            WHERE company_code=%s AND employee_key=%s
              AND money_authority='wathefni' AND status='current'
            ORDER BY period_end DESC NULLS LAST, sealed_at DESC NULLS LAST
            LIMIT 1
            """,
            (company, key),
        )
        prev = _row(cur)
        if not prev:
            employees_out.append(
                {
                    "employee_key": key,
                    "changed": False,
                    "needs_review": False,
                    "message_en": "No previous authoritative period.",
                }
            )
            continue

        prev_gross = Decimal(str(prev.get("totals_gross") or 0))
        prev_net = Decimal(str(prev.get("totals_net") or 0))
        g_delta = gross - prev_gross
        n_delta = net - prev_net
        g_pct = (g_delta / prev_gross) if prev_gross != 0 else Decimal("0")
        n_pct = (n_delta / prev_net) if prev_net != 0 else Decimal("0")

        needs = False
        codes = []
        if abs(g_delta) >= Decimal(str(pol.get("gross_delta_abs") or 50)):
            needs = True
            codes.append("gross_delta_abs")
        if abs(n_delta) >= Decimal(str(pol.get("net_delta_abs") or 50)):
            needs = True
            codes.append("net_delta_abs")
        if abs(g_pct) >= Decimal(str(pol.get("gross_delta_pct") or 0.10)):
            needs = True
            codes.append("gross_delta_pct")
        if abs(n_pct) >= Decimal(str(pol.get("net_delta_pct") or 0.10)):
            needs = True
            codes.append("net_delta_pct")
        if pol.get("flag_zero_or_negative_net") and net <= 0:
            needs = True
            codes.append("zero_or_negative_net")

        employees_out.append(
            {
                "employee_key": key,
                "changed": g_delta != 0 or n_delta != 0,
                "needs_review": needs,
                "primary_code": codes[0] if codes else "changed_since_previous",
                "codes": codes,
                "gross": float(gross),
                "net": float(net),
                "prev_gross": float(prev_gross),
                "prev_net": float(prev_net),
                "gross_delta": float(g_delta),
                "net_delta": float(n_delta),
                "previous_authority_snapshot_id": prev.get("authority_snapshot_id"),
                "message_en": (
                    "Unusual variance vs previous authoritative period — review advised (no automatic rewrite)."
                    if needs
                    else "Changed since previous period."
                ),
                "advisory": True,
            }
        )

    return {
        "ok": True,
        "advisory_only": True,
        "never_rewrites_money": True,
        "policy": _json_safe(pol),
        "employees": employees_out,
    }


def record_controlled_override(
    cur: Any,
    *,
    company_code: str,
    override_kind: str,
    actor_phone: str | None,
    reason: str | None,
    employee_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Policy-decision overrides only — never for mandatory statutory uncertainty."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    kind = str(override_kind or "").strip()
    if kind not in ("company_policy_decision", "review_ack_unusual_variance", "component_exception_ack"):
        return {
            "ok": False,
            "error": "override_kind_not_allowed",
            "message_en": "Controlled overrides cannot clear mandatory statutory uncertainty.",
        }
    ensure_payroll_production_p6_schema(cur)
    cur.execute(
        """
        INSERT INTO payroll_mode_a_controlled_overrides (
          company_code, employee_key, override_kind, reason, actor_phone, allowed, payload
        ) VALUES (%s,%s,%s,%s,%s,true,%s::jsonb)
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            employee_key,
            kind,
            str(reason).strip(),
            digits_phone(actor_phone),
            json.dumps(_json_safe(payload or {})),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        company_code=company_code,
        event_type="controlled_override",
        payload={"override_id": str(row.get("override_id")), "kind": kind},
        actor_phone=actor_phone,
    )
    return {"ok": True, "override": _json_safe(row), **honesty_payload()}


# --------------------------------------------------------------------------- Scale benchmark helper


def measure_batch_timings(
    *,
    assemble_ms: float | None = None,
    calculate_ms: float | None = None,
    classify_ms: float | None = None,
    finalize_ms: float | None = None,
    payslip_ms: float | None = None,
    employee_count: int,
) -> dict[str, Any]:
    return {
        "employee_count": employee_count,
        "assemble_ms": assemble_ms,
        "calculate_ms": calculate_ms,
        "classify_ms": classify_ms,
        "finalize_ms": finalize_ms,
        "payslip_ms": payslip_ms,
        "per_employee_calc_ms": (calculate_ms / employee_count) if calculate_ms and employee_count else None,
        "batch_oriented": True,
        "n_plus_one_forbidden": True,
    }


def now_ms() -> float:
    return time.perf_counter() * 1000.0


# --------------------------------------------------------------------------- Workspace / oracle / blockers


def run_independent_oracle_pack() -> dict[str, Any]:
    if oracle is None:
        return {"ok": False, "error": "oracle_module_missing"}
    return oracle.compute_all()


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_production_p6_schema(cur)
    readiness = validate_payroll_readiness(cur, company_code=company_code)
    ent = get_company_entitlement(cur, company_code=company_code)
    return {
        "ok": True,
        "entitlement": _json_safe(ent),
        "readiness": readiness,
        "variance_policy": _json_safe(get_variance_policy(cur, company_code=company_code)),
        "allowlist": _json_safe(list_active_allowlist(cur, company_code=company_code)),
        "setup_contract": setup_console_schema_contract(),
        "remaining_gaps": remaining_gaps_before_unrestricted_rollout(),
        **honesty_payload(),
    }


def production_enablement_blockers() -> dict[str, Any]:
    return {
        "payment_processing": "disabled",
        "wps_bank_rails": "out_of_scope",
        "payment_date_invented": False,
        "global_mode_a_for_all_tenants": False,
        "unrestricted_customer_rollout": False,
        "remaining_gaps": remaining_gaps_before_unrestricted_rollout(),
        "employee_app_p1": "paused",
        "auth_wave2_phase6": "paused",
        "setup_console_redesign": "schema_contract_only",
    }
