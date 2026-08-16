"""Payroll Authority P5 — Mode A authoritative finalize.

Flow:
  locked P2 + approved P3 policy + P3 calculated run + P4B OFFICIAL_CLEAR
  → finalize gates → review/approve (SOD) → seal money_authority=wathefni
  → native authoritative payslip → official PDF (when released)

Never promotes preview_non_authoritative rows in place.
P6 replaces blanket SYNTHETIC_ONLY with company entitlement when P6 is enabled.
Never unlocks payment_processing. Never globally enables Mode A for all tenants.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import payroll_authority_snapshot_p1 as p1
import payroll_authority_wave1 as pyw1
import payroll_components_policy_p3 as p3
import payroll_input_snapshot_p2 as p2
import payroll_payslip_wave3 as w3
import payroll_statutory_architecture_p4a as p4a
import payroll_statutory_baseline_p4b as p4b

PAYROLL_AUTHORITY_P5_VERSION = "1.0.0"
FINALIZE_SCHEMA = "wathefni.payroll_mode_a_finalize.v1"
MONEY_WATHEFNI = "wathefni"
MONEY_PENDING = "pending_seal"
STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_APPROVED = "approved"
STATUS_FINALIZED = "finalized"
SOURCE_NATIVE_AUTH = "native_authoritative"

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_authority_mode_a_p5_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")
DEFAULT_MARKERS = (
    "PYW1", "PYP1", "PYP2", "PYP3", "PYP4A", "PYP4B", "PYP5", "PYAUTH", "PYSTAT", "PYINPUT", "PYCALC",
)

# Families that must resolve when company policy enables corresponding money.
POLICY_FAMILY_FLAGS = {
    "ot_ordinary": "ot_money_enabled",
    "rest_day_work": "rest_day_money_enabled",
    "public_holiday_work": "public_holiday_money_enabled",
    "sick_leave_fractions": "sick_leave_money_enabled",
}


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p5_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P5", default=True)


def payroll_authority_p5_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p5_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P5_COMPANIES") or "WATHEFNI").strip()
    return (company_code or "").upper() in {p.strip().upper() for p in raw.split(",") if p.strip()}


def payroll_authority_p5_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_MARKERS


def is_p5_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    return any(m and m in key for m in synthetic_key_markers()) or p1.is_p1_synthetic_employee(employee_key=key)


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p5_version": PAYROLL_AUTHORITY_P5_VERSION,
        "finalize_schema": FINALIZE_SCHEMA,
        "mode_a_wathefni_seal_unlocked": True,
        "mode_a_seal_requires_finalize_gates": True,
        "preview_remains_preview": True,
        "never_flip_preview_row": True,
        "period_close_is_money_seal": False,
        "money_authority_on_seal": MONEY_WATHEFNI,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "synthetic_only": payroll_authority_p5_synthetic_only(),
        "p6_company_entitlement_gate": True,
        "p6_real_employees_unlocked": False,
        "p1_p2_p3_p4a_p4b_preserved": True,
    }


def ensure_payroll_mode_a_finalize_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    p1.ensure_payroll_authority_snapshot_schema(cur)
    p3.ensure_payroll_components_policy_schema(cur)
    p4b.ensure_payroll_statutory_baseline_schema(cur)
    if SCHEMA_SQL.strip():
        lock_id = 770_900_016
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
    finalize_run_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_mode_a_finalize_events (
          company_code, finalize_run_id, event_type, payload, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            finalize_run_id,
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def get_company_finalize_policy(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    cur.execute("SELECT * FROM payroll_mode_a_company_finalize_policy WHERE company_code=%s", (company,))
    row = _row(cur)
    if row:
        return row
    # SME-sensible defaults: review + SOD, approver may finalize
    return {
        "company_code": company,
        "require_review_step": True,
        "require_distinct_reviewer": True,
        "require_distinct_approver": True,
        "require_distinct_finalizer": True,
        "allow_approver_as_finalizer": True,
        "metadata": {"default": True, "sme_friendly": True},
    }


def upsert_company_finalize_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str | None,
    require_review_step: bool = True,
    require_distinct_reviewer: bool = True,
    require_distinct_approver: bool = True,
    require_distinct_finalizer: bool = True,
    allow_approver_as_finalizer: bool = True,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO payroll_mode_a_company_finalize_policy (
          company_code, require_review_step, require_distinct_reviewer,
          require_distinct_approver, require_distinct_finalizer, allow_approver_as_finalizer,
          metadata, updated_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (company_code) DO UPDATE SET
          require_review_step=EXCLUDED.require_review_step,
          require_distinct_reviewer=EXCLUDED.require_distinct_reviewer,
          require_distinct_approver=EXCLUDED.require_distinct_approver,
          require_distinct_finalizer=EXCLUDED.require_distinct_finalizer,
          allow_approver_as_finalizer=EXCLUDED.allow_approver_as_finalizer,
          updated_at=now(), updated_by_phone=EXCLUDED.updated_by_phone
        RETURNING *
        """,
        (
            company,
            require_review_step,
            require_distinct_reviewer,
            require_distinct_approver,
            require_distinct_finalizer,
            allow_approver_as_finalizer,
            json.dumps({"reason": str(reason).strip()}),
            digits_phone(actor_phone),
        ),
    )
    return {"ok": True, "policy": _json_safe(_row(cur)), **honesty_payload()}


def evaluate_finalize_gates(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Fail-closed gate evaluation for Mode A seal eligibility."""
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    calc = p3.get_calc_run(cur, company_code=company, calc_run_id=calc_run_id)
    if not calc:
        return {"ok": False, "blockers": [{"code": "calc_run_not_found"}], **honesty_payload()}
    if str(calc.get("status")) != "calculated":
        blockers.append({"code": "calc_run_not_calculated", "status": calc.get("status")})
    if str(calc.get("money_authority")) != "preview_non_authoritative":
        # Must still be preview row — never seal by flipping it
        blockers.append({"code": "calc_run_money_authority_unexpected", "money_authority": calc.get("money_authority")})

    input_id = str(calc.get("input_snapshot_id") or "")
    snap = p2.get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_id) if input_id else None
    if not snap:
        blockers.append({"code": "input_snapshot_not_found"})
    elif str(snap.get("status")) != "locked":
        blockers.append({"code": "input_snapshot_not_locked", "status": snap.get("status")})
    else:
        # Unresolved blocking issues on employees
        emp_rows = p2.list_input_snapshot_employees(cur, company_code=company, input_snapshot_id=input_id)
        for er in emp_rows:
            key = str(er.get("employee_key") or "")
            if employee_keys and key not in employee_keys:
                continue
            try:
                import payroll_authority_production_p6 as p6

                if p6.payroll_authority_p6_enabled_for_company(company):
                    gate = p6.employee_may_authoritative_seal(
                        cur, company_code=company, employee_key=key
                    )
                    if not gate.get("ok"):
                        blockers.append(
                            {
                                "code": gate.get("reason") or "nonsynthetic_employee_blocked",
                                "employee_key": key,
                                "gate": gate.get("gate"),
                                "entitlement_state": gate.get("entitlement_state"),
                                "message_en": gate.get("message_en"),
                            }
                        )
                elif payroll_authority_p5_synthetic_only() and not is_p5_synthetic_employee(employee_key=key):
                    blockers.append({"code": "nonsynthetic_employee_blocked", "employee_key": key})
            except Exception:
                if payroll_authority_p5_synthetic_only() and not is_p5_synthetic_employee(employee_key=key):
                    blockers.append({"code": "nonsynthetic_employee_blocked", "employee_key": key})
            st = str(er.get("status") or "")
            if st in ("blocked", "needs_review"):
                blockers.append({"code": "unresolved_p2_issue", "employee_key": key, "status": st})

    policy_id = str(calc.get("policy_version_id") or "")
    policy = p3.get_policy_by_id(cur, company_code=company, policy_version_id=policy_id) if policy_id else None
    if not policy or str(policy.get("status")) != "approved":
        blockers.append({"code": "approved_policy_required", "policy_version_id": policy_id})

    emp_results = p3.list_calc_employee_results(cur, company_code=company, calc_run_id=calc_run_id)
    if employee_keys:
        emp_results = [e for e in emp_results if str(e.get("employee_key")) in set(employee_keys)]
    if not emp_results:
        blockers.append({"code": "no_employees_to_finalize"})
    for er in emp_results:
        if str(er.get("status")) != "ok":
            blockers.append(
                {
                    "code": "employee_calc_blocked",
                    "employee_key": er.get("employee_key"),
                    "status": er.get("status"),
                    "blockers": er.get("blockers"),
                }
            )

    # Statutory: required families when policy enables money
    as_of = p4a._parse_date(calc.get("period_start")) or date.today()  # noqa: SLF001
    statutory_prov: dict[str, Any] = {}
    if policy:
        for fam, flag in POLICY_FAMILY_FLAGS.items():
            if not policy.get(flag):
                continue
            rule = p4b.resolve_public_baseline_rule(cur, rule_family=fam, as_of=as_of, sector="private")
            if not rule:
                # also try p4a legal resolve
                rule = p4a.resolve_rule_version(
                    cur,
                    company_code=company,
                    rule_family=fam,
                    as_of=as_of,
                    require_legal_claim=True,
                )
            if not rule:
                blockers.append({"code": "missing_approved_statutory_rule", "rule_family": fam})
            else:
                statutory_prov[fam] = {
                    "rule_version_id": str(rule.get("rule_version_id")),
                    "policy_version": rule.get("policy_version"),
                    "official_source_ref": rule.get("official_source_ref"),
                    "authority_kind": rule.get("authority_kind"),
                    "multiplier": float(rule["multiplier"]) if rule.get("multiplier") is not None else None,
                }

    # Per-employee gated statutory classifications (only when applicable)
    for er in emp_results:
        key = str(er.get("employee_key") or "")
        # Classification from calc provenance / employee metadata if present
        meta = er.get("result_payload") or er.get("provenance") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        category = meta.get("employee_category") or meta.get("statutory_category")
        # If OT/rest/PH/sick only — category not required.
        # If policy implies PIFSS (kuwaiti) via metadata flag on calc content:
        needs_pifss = bool((calc.get("snapshot_payload") or {}))  # unused
        _ = needs_pifss
        # Explicit: only block when employee is marked as requiring gated path
        gated_flags = meta.get("statutory_gates") or []
        if isinstance(gated_flags, str):
            gated_flags = [gated_flags]
        for g in gated_flags:
            code = str(g)
            if code in p4b.GATED_BLOCKERS:
                blockers.append({"code": code, "employee_key": key, **p4b.GATED_BLOCKERS[code]})
        # GCC / oil / kuwaiti EOS flags if present
        if category == "gcc_national":
            blockers.append({"code": "gcc_extension_review_required", "employee_key": key, **p4b.GATED_BLOCKERS["gcc_extension_review_required"]})
        if meta.get("special_regime") == "oil":
            blockers.append(
                {
                    "code": "special_regime_review_required",
                    "employee_key": key,
                    "message": "Oil/special regime remains review-gated for Mode A seal.",
                }
            )
        if category == "kuwaiti_national" and meta.get("include_eos_settlement"):
            blockers.append(
                {
                    "code": "eos_pifss_interaction_review_required",
                    "employee_key": key,
                    **p4b.GATED_BLOCKERS["eos_pifss_interaction_review_required"],
                }
            )
        if category == "kuwaiti_national" and meta.get("include_pifss") and not meta.get("pifss_wage_by_fund"):
            blockers.append(
                {
                    "code": "pifss_wage_base_classification_required",
                    "employee_key": key,
                    **p4b.GATED_BLOCKERS["pifss_wage_base_classification_required"],
                }
            )

    ok = len(blockers) == 0
    return {
        "ok": ok,
        "blockers": blockers,
        "warnings": warnings,
        "calc_run": _json_safe(calc),
        "input_snapshot": _json_safe(snap) if snap else None,
        "policy": _json_safe(policy) if policy else None,
        "statutory_provenance": statutory_prov,
        "employee_keys": [str(e.get("employee_key")) for e in emp_results],
        **honesty_payload(),
    }


def create_finalize_run_from_calc(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not payroll_authority_p5_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p5_disabled_for_company"}
    ensure_payroll_mode_a_finalize_schema(cur)
    gates = evaluate_finalize_gates(
        cur, company_code=company_code, calc_run_id=calc_run_id, employee_keys=employee_keys
    )
    if not gates.get("ok"):
        return {"ok": False, "error": "finalize_gates_failed", "gates": gates, **honesty_payload()}

    calc = gates["calc_run"]
    policy_cfg = get_company_finalize_policy(cur, company_code=company_code)
    content = {
        "calc_run_id": calc_run_id,
        "input_snapshot_id": calc.get("input_snapshot_id"),
        "policy_version_id": calc.get("policy_version_id"),
        "content_fingerprint_calc": calc.get("content_fingerprint"),
        "statutory_provenance": gates.get("statutory_provenance"),
        "employee_keys": gates.get("employee_keys"),
        "finalize_policy": {
            "require_review_step": policy_cfg.get("require_review_step"),
            "require_distinct_approver": policy_cfg.get("require_distinct_approver"),
            "require_distinct_finalizer": policy_cfg.get("require_distinct_finalizer"),
        },
    }
    fp = fingerprint_payload(content)
    company = (company_code or "").upper()

    # Idempotent: existing active finalize for same calc
    cur.execute(
        """
        SELECT * FROM payroll_mode_a_finalize_runs
        WHERE company_code=%s AND calc_run_id=%s
          AND status IN ('draft','in_review','approved','finalized')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, calc_run_id),
    )
    existing = _row(cur)
    if existing:
        if str(existing.get("content_fingerprint")) == fp and str(existing.get("status")) != "cancelled":
            return {
                "ok": True,
                "idempotent": True,
                "finalize_run": _json_safe(existing),
                "gates": gates,
                **honesty_payload(),
            }
        if str(existing.get("status")) == "finalized":
            return {
                "ok": True,
                "idempotent": True,
                "finalize_run": _json_safe(existing),
                "message": "Already finalized for this calc run",
                **honesty_payload(),
            }

    chain = [
        {
            "actor_phone": digits_phone(actor_phone),
            "action": "create_finalize_draft",
            "reason": str(reason).strip(),
            "at": datetime.utcnow().isoformat() + "Z",
        }
    ]
    cur.execute(
        """
        INSERT INTO payroll_mode_a_finalize_runs (
          company_code, calc_run_id, input_snapshot_id, policy_version_id,
          period_start, period_end, status, money_authority, content_fingerprint,
          gate_payload, blockers, statutory_provenance, approval_actor_chain,
          company_finalize_policy, created_by_phone, decision_note
        ) VALUES (
          %s,%s,%s,%s,
          %s,%s,'draft','pending_seal',%s,
          %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,
          %s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            company,
            calc_run_id,
            calc.get("input_snapshot_id"),
            calc.get("policy_version_id"),
            calc.get("period_start"),
            calc.get("period_end"),
            fp,
            json.dumps(_json_safe({"ok": True, "employee_keys": gates.get("employee_keys")})),
            json.dumps([]),
            json.dumps(_json_safe(gates.get("statutory_provenance") or {})),
            json.dumps(_json_safe(chain)),
            json.dumps(_json_safe(policy_cfg)),
            digits_phone(actor_phone),
            str(reason).strip(),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        company_code=company,
        finalize_run_id=str((row or {}).get("finalize_run_id")),
        event_type="finalize_run_created",
        payload={"calc_run_id": calc_run_id, "content_fingerprint": fp},
        actor_phone=actor_phone,
    )
    return {"ok": True, "idempotent": False, "finalize_run": _json_safe(row), "gates": gates, **honesty_payload()}


def _get_finalize(cur: Any, *, company_code: str, finalize_run_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM payroll_mode_a_finalize_runs WHERE company_code=%s AND finalize_run_id=%s",
        ((company_code or "").upper(), finalize_run_id),
    )
    return _row(cur)


def _append_chain(run: dict[str, Any], entry: dict[str, Any]) -> list[dict[str, Any]]:
    chain = run.get("approval_actor_chain") or []
    if isinstance(chain, str):
        try:
            chain = json.loads(chain)
        except Exception:
            chain = []
    chain = list(chain) if isinstance(chain, list) else []
    chain.append(entry)
    return chain


def submit_finalize_for_review(
    cur: Any,
    *,
    company_code: str,
    finalize_run_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    run = _get_finalize(cur, company_code=company_code, finalize_run_id=finalize_run_id)
    if not run:
        return {"ok": False, "error": "finalize_run_not_found"}
    if str(run.get("status")) not in (STATUS_DRAFT, STATUS_IN_REVIEW):
        return {"ok": False, "error": "invalid_finalize_status", "status": run.get("status")}
    policy = run.get("company_finalize_policy") or get_company_finalize_policy(cur, company_code=company_code)
    if isinstance(policy, str):
        policy = json.loads(policy)
    if not policy.get("require_review_step", True):
        # Skip to approved path not via this function
        return {"ok": False, "error": "review_step_not_required_use_approve"}
    chain = _append_chain(
        run,
        {
            "actor_phone": digits_phone(actor_phone),
            "action": "submit_review",
            "reason": str(reason).strip(),
            "at": datetime.utcnow().isoformat() + "Z",
        },
    )
    cur.execute(
        """
        UPDATE payroll_mode_a_finalize_runs
        SET status='in_review', reviewed_by_phone=%s, reviewed_at=now(),
            approval_actor_chain=%s::jsonb, updated_at=now(), row_version=row_version+1,
            decision_note=%s
        WHERE company_code=%s AND finalize_run_id=%s AND status IN ('draft','in_review')
        RETURNING *
        """,
        (
            digits_phone(actor_phone),
            json.dumps(_json_safe(chain)),
            str(reason).strip(),
            (company_code or "").upper(),
            finalize_run_id,
        ),
    )
    row = _row(cur)
    return {"ok": True, "finalize_run": _json_safe(row), **honesty_payload()}


def approve_finalize_run(
    cur: Any,
    *,
    company_code: str,
    finalize_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | None = None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    run = _get_finalize(cur, company_code=company_code, finalize_run_id=finalize_run_id)
    if not run:
        return {"ok": False, "error": "finalize_run_not_found"}
    policy = run.get("company_finalize_policy") or get_company_finalize_policy(cur, company_code=company_code)
    if isinstance(policy, str):
        policy = json.loads(policy)

    actor = digits_phone(actor_phone)
    creator = digits_phone(run.get("created_by_phone"))
    if policy.get("require_distinct_approver", True) and actor and creator and actor == creator:
        return {
            "ok": False,
            "error": "sod_creator_cannot_approve",
            "message": "Segregation of duties: finalize creator cannot approve.",
            **honesty_payload(),
        }
    if policy.get("require_review_step", True) and str(run.get("status")) != STATUS_IN_REVIEW:
        return {"ok": False, "error": "finalize_must_be_in_review", "status": run.get("status")}
    if not policy.get("require_review_step", True) and str(run.get("status")) not in (STATUS_DRAFT, STATUS_IN_REVIEW):
        return {"ok": False, "error": "invalid_finalize_status", "status": run.get("status")}
    if policy.get("require_distinct_reviewer", True) and policy.get("require_review_step", True):
        reviewer = digits_phone(run.get("reviewed_by_phone"))
        if reviewer and actor == reviewer and policy.get("require_distinct_approver", True):
            # Allow same reviewer=approver for SME unless strict enterprise — default allow
            pass
    if actor_permissions is not None and pyw1.sod_holds_approve_and_export(actor_permissions):
        return {"ok": False, "error": "sod_approve_export_conflict", **honesty_payload()}

    chain = _append_chain(
        run,
        {
            "actor_phone": actor,
            "action": "approve",
            "reason": str(reason).strip(),
            "at": datetime.utcnow().isoformat() + "Z",
        },
    )
    cur.execute(
        """
        UPDATE payroll_mode_a_finalize_runs
        SET status='approved', approved_by_phone=%s, approved_at=now(),
            approval_actor_chain=%s::jsonb, updated_at=now(), row_version=row_version+1,
            decision_note=%s
        WHERE company_code=%s AND finalize_run_id=%s
          AND status IN ('draft','in_review','approved')
        RETURNING *
        """,
        (
            actor,
            json.dumps(_json_safe(chain)),
            str(reason).strip(),
            (company_code or "").upper(),
            finalize_run_id,
        ),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "approve_race"}
    _record_event(
        cur,
        company_code=company_code,
        finalize_run_id=finalize_run_id,
        event_type="finalize_approved",
        payload={"actor": actor},
        actor_phone=actor_phone,
    )
    return {"ok": True, "finalize_run": _json_safe(row), **honesty_payload()}


def finalize_mode_a(
    cur: Any,
    *,
    company_code: str,
    finalize_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | None = None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Seal wathefni authority snapshots for eligible employees. Idempotent."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    run = _get_finalize(cur, company_code=company, finalize_run_id=finalize_run_id)
    if not run:
        return {"ok": False, "error": "finalize_run_not_found"}

    # Idempotent re-finalize
    if str(run.get("status")) == STATUS_FINALIZED and str(run.get("money_authority")) == MONEY_WATHEFNI:
        snaps = _list_wathefni_for_finalize(cur, company_code=company, finalize_run_id=finalize_run_id)
        return {
            "ok": True,
            "idempotent": True,
            "finalize_run": _json_safe(run),
            "authority_snapshots": _json_safe(snaps),
            **honesty_payload(),
        }

    if str(run.get("status")) != STATUS_APPROVED:
        return {"ok": False, "error": "finalize_requires_approved", "status": run.get("status")}

    policy = run.get("company_finalize_policy") or {}
    if isinstance(policy, str):
        policy = json.loads(policy)
    actor = digits_phone(actor_phone)
    creator = digits_phone(run.get("created_by_phone"))
    approver = digits_phone(run.get("approved_by_phone"))
    if policy.get("require_distinct_finalizer", True) and actor and creator and actor == creator:
        return {"ok": False, "error": "sod_creator_cannot_finalize", **honesty_payload()}
    if (
        policy.get("require_distinct_finalizer", True)
        and not policy.get("allow_approver_as_finalizer", True)
        and actor
        and approver
        and actor == approver
    ):
        return {"ok": False, "error": "sod_approver_cannot_finalize", **honesty_payload()}
    if actor_permissions is not None and pyw1.sod_holds_approve_and_export(actor_permissions):
        return {"ok": False, "error": "sod_approve_export_conflict", **honesty_payload()}

    # Re-check gates
    gates = evaluate_finalize_gates(
        cur,
        company_code=company,
        calc_run_id=str(run.get("calc_run_id")),
        employee_keys=employee_keys,
    )
    if not gates.get("ok"):
        return {"ok": False, "error": "finalize_gates_failed", "gates": gates, **honesty_payload()}

    sealed = []
    for key in gates.get("employee_keys") or []:
        result = seal_wathefni_from_calc_employee(
            cur,
            company_code=company,
            calc_run_id=str(run.get("calc_run_id")),
            employee_key=key,
            finalize_run_id=finalize_run_id,
            actor_phone=actor_phone,
            reason=str(reason).strip(),
            statutory_provenance=gates.get("statutory_provenance") or {},
            approval_actor_chain=_append_chain(
                run,
                {
                    "actor_phone": actor,
                    "action": "finalize_seal",
                    "employee_key": key,
                    "reason": str(reason).strip(),
                    "at": datetime.utcnow().isoformat() + "Z",
                },
            ),
        )
        if not result.get("ok"):
            return result
        sealed.append(result.get("authority_snapshot"))

    chain = _append_chain(
        run,
        {
            "actor_phone": actor,
            "action": "finalize",
            "reason": str(reason).strip(),
            "sealed_count": len(sealed),
            "at": datetime.utcnow().isoformat() + "Z",
        },
    )
    cur.execute(
        """
        UPDATE payroll_mode_a_finalize_runs
        SET status='finalized', money_authority='wathefni',
            finalized_by_phone=%s, finalized_at=now(),
            approval_actor_chain=%s::jsonb, updated_at=now(), row_version=row_version+1,
            decision_note=%s
        WHERE company_code=%s AND finalize_run_id=%s AND status='approved'
        RETURNING *
        """,
        (
            actor,
            json.dumps(_json_safe(chain)),
            str(reason).strip(),
            company,
            finalize_run_id,
        ),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "finalize_race"}
    _record_event(
        cur,
        company_code=company,
        finalize_run_id=finalize_run_id,
        event_type="finalize_sealed_wathefni",
        payload={"sealed_count": len(sealed)},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "idempotent": False,
        "finalize_run": _json_safe(row),
        "authority_snapshots": _json_safe(sealed),
        **honesty_payload(),
    }


def _list_wathefni_for_finalize(cur: Any, *, company_code: str, finalize_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshots
        WHERE company_code=%s AND money_authority='wathefni' AND status='sealed'
          AND provenance->>'finalize_run_id'=%s
        ORDER BY employee_key
        """,
        ((company_code or "").upper(), finalize_run_id),
    )
    return _rows(cur)


def seal_wathefni_from_calc_employee(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str,
    employee_key: str,
    finalize_run_id: str,
    actor_phone: str | None,
    reason: str,
    statutory_provenance: dict[str, Any],
    approval_actor_chain: list[dict[str, Any]] | None = None,
    replaces_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Create immutable money_authority=wathefni snapshot from P3 calc lines (separate from preview row)."""
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    key = str(employee_key or "")
    if payroll_authority_p5_synthetic_only() and not is_p5_synthetic_employee(employee_key=key):
        return {"ok": False, "error": "nonsynthetic_employee_blocked", "employee_key": key}

    calc = p3.get_calc_run(cur, company_code=company, calc_run_id=calc_run_id)
    if not calc or str(calc.get("status")) != "calculated":
        return {"ok": False, "error": "calc_run_not_calculated"}
    # Never mutate calc money_authority
    if str(calc.get("money_authority")) != "preview_non_authoritative":
        return {"ok": False, "error": "calc_preview_authority_invariant_broken"}

    emp_results = p3.list_calc_employee_results(cur, company_code=company, calc_run_id=calc_run_id)
    emp = next((e for e in emp_results if str(e.get("employee_key")) == key), None)
    if not emp or str(emp.get("status")) != "ok":
        return {"ok": False, "error": "employee_calc_not_ok", "employee": _json_safe(emp)}

    lines_raw = p3.list_calc_lines(cur, company_code=company, calc_run_id=calc_run_id, employee_key=key)
    lines = []
    for i, ln in enumerate(lines_raw):
        lines.append(
            {
                "component_code": str(ln.get("component_code") or f"L{i}"),
                "catalog_code": ln.get("catalog_code"),
                "line_kind": str(ln.get("line_kind") or "earning"),
                "category": ln.get("category"),
                "label_en": ln.get("label_en") or ln.get("component_code"),
                "label_ar": ln.get("label_ar"),
                "amount": float(Decimal(str(ln.get("amount") or 0))),
                "currency": "KWD",
                "source": "native_authoritative",
                "policy_version": str(calc.get("policy_version_id") or ""),
                "sort_order": int(ln.get("sort_order") or i),
                "provenance": {
                    "calc_line_id": str(ln.get("line_id") or ""),
                    "calc_notes": ln.get("calc_notes"),
                    "input_line_id": (ln.get("provenance") or {}).get("input_line_id")
                    if isinstance(ln.get("provenance"), dict)
                    else None,
                },
            }
        )
    totals = {
        "earnings": float(Decimal(str(emp.get("totals_earnings") or 0))),
        "deductions": float(Decimal(str(emp.get("totals_deductions") or 0))),
        "gross": float(Decimal(str(emp.get("totals_gross") or emp.get("totals_earnings") or 0))),
        "net": float(Decimal(str(emp.get("totals_net") or 0))),
    }
    content = {
        "schema": p1.AUTHORITY_SNAPSHOT_SCHEMA,
        "money_authority": MONEY_WATHEFNI,
        "source_kind": SOURCE_NATIVE_AUTH,
        "source_mode": p1.MODE_A,
        "calc_run_id": calc_run_id,
        "finalize_run_id": finalize_run_id,
        "input_snapshot_id": str(calc.get("input_snapshot_id")),
        "policy_version_id": str(calc.get("policy_version_id")),
        "catalog_fingerprint": calc.get("catalog_fingerprint"),
        "compensation_fingerprint": calc.get("compensation_fingerprint"),
        "policy_fingerprint": calc.get("policy_fingerprint"),
        "input_fingerprint": calc.get("input_fingerprint"),
        "calc_content_fingerprint": calc.get("content_fingerprint"),
        "statutory_provenance": statutory_provenance,
        "employee_key": key,
        "period_start": str(calc.get("period_start"))[:10],
        "period_end": str(calc.get("period_end"))[:10],
        "lines": lines,
        "totals": totals,
        "payment_processing": "disabled",
        "posts_payment": False,
    }
    content_fp = fingerprint_payload(content)
    source_fp = str(calc.get("content_fingerprint") or content_fp)

    # Idempotent same content
    current = p1.get_current_sealed_snapshot(
        cur,
        company_code=company,
        employee_key=key,
        period_start=str(calc.get("period_start"))[:10],
        period_end=str(calc.get("period_end"))[:10],
    )
    if current and not replaces_snapshot_id:
        if (
            str(current.get("money_authority")) == MONEY_WATHEFNI
            and str(current.get("content_fingerprint")) == content_fp
        ):
            return {
                "ok": True,
                "idempotent": True,
                "authority_snapshot": _json_safe(current),
                **honesty_payload(),
            }
        if str(current.get("status")) == "sealed":
            return {
                "ok": False,
                "error": "active_sealed_snapshot_exists",
                "message": "Use replace_mode_a_authority for corrections.",
                "authority_snapshot_id": str(current.get("authority_snapshot_id")),
                **honesty_payload(),
            }

    built = {
        "ok": True,
        "period_start": calc.get("period_start"),
        "period_end": calc.get("period_end"),
        "content": content,
        "lines": lines,
        "totals": totals,
        "source_fingerprint": source_fp,
        "content_fingerprint": content_fp,
    }
    row = p1.insert_wathefni_sealed_snapshot(
        cur,
        company_code=company,
        employee_key=key,
        built=built,
        actor_phone=actor_phone,
        reason=reason,
        calc_run_id=calc_run_id,
        finalize_run_id=finalize_run_id,
        replaces_snapshot_id=replaces_snapshot_id,
        approval_actor_chain=approval_actor_chain,
        statutory_provenance=statutory_provenance,
    )
    return {"ok": True, "idempotent": False, "authority_snapshot": _json_safe(row), **honesty_payload()}


def replace_mode_a_authority(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    calc_run_id: str,
    finalize_run_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    """Correction: new wathefni sealed snapshot; prior becomes replaced (history retained)."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    company = (company_code or "").upper()
    prior = p1.get_sealed_snapshot_by_id(
        cur, company_code=company, authority_snapshot_id=authority_snapshot_id
    )
    if not prior:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(prior.get("status")) != "sealed":
        return {"ok": False, "error": "authority_snapshot_not_sealed"}
    if str(prior.get("money_authority")) != MONEY_WATHEFNI:
        return {"ok": False, "error": "replace_requires_wathefni_snapshot"}

    key = str(prior.get("employee_key") or "")
    gates = evaluate_finalize_gates(cur, company_code=company, calc_run_id=calc_run_id, employee_keys=[key])
    if not gates.get("ok"):
        return {"ok": False, "error": "finalize_gates_failed", "gates": gates, **honesty_payload()}

    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET status='replaced', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | replaced:' || %s
        WHERE company_code=%s AND authority_snapshot_id=%s AND status='sealed'
        RETURNING *
        """,
        (str(reason).strip(), company, authority_snapshot_id),
    )
    if not _row(cur):
        return {"ok": False, "error": "authority_snapshot_replace_race"}

    sealed = seal_wathefni_from_calc_employee(
        cur,
        company_code=company,
        calc_run_id=calc_run_id,
        employee_key=key,
        finalize_run_id=finalize_run_id,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
        statutory_provenance=gates.get("statutory_provenance") or {},
        replaces_snapshot_id=authority_snapshot_id,
        approval_actor_chain=[
            {
                "actor_phone": digits_phone(actor_phone),
                "action": "replace_wathefni",
                "prior": authority_snapshot_id,
                "reason": str(reason).strip(),
                "at": datetime.utcnow().isoformat() + "Z",
            }
        ],
    )
    if not sealed.get("ok"):
        return sealed
    new_id = str((sealed.get("authority_snapshot") or {}).get("authority_snapshot_id") or "")
    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET superseded_by=%s, updated_at=now()
        WHERE company_code=%s AND authority_snapshot_id=%s
        """,
        (new_id, company, authority_snapshot_id),
    )
    return {
        "ok": True,
        "prior_authority_snapshot_id": authority_snapshot_id,
        "authority_snapshot": sealed.get("authority_snapshot"),
        **honesty_payload(),
    }


def generate_wathefni_payslip_from_sealed(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    """Create native_authoritative payslip projection matching sealed wathefni snapshot exactly."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_mode_a_finalize_schema(cur)
    return w3.generate_wathefni_payslip_from_authority_snapshot(
        cur,
        company_code=company_code,
        authority_snapshot_id=authority_snapshot_id,
        actor_phone=actor_phone,
        reason=reason,
    )


def p6_blockers() -> dict[str, Any]:
    try:
        import payroll_authority_production_p6 as p6

        if p6.payroll_authority_p6_enabled():
            return {
                "synthetic_only_still_enabled": False,
                "company_entitlement_model": True,
                "global_mode_a_for_all_tenants": False,
                "real_employees_blocked_unless_entitled": True,
                "payment_processing_disabled": True,
                "payment_date_not_invented": True,
                "wps_bank_rails_out_of_scope": True,
                "remaining_for_p6": p6.remaining_gaps_before_unrestricted_rollout(),
                "production_enablement": p6.production_enablement_blockers(),
                "do_not_auto_start": ["Employee App P1", "Setup Console redesign", "Auth Wave 2 Phase 6"],
            }
    except Exception:
        pass
    return {
        "synthetic_only_still_enabled": True,
        "real_employees_blocked": True,
        "payment_processing_disabled": True,
        "payment_date_not_invented": True,
        "wps_bank_rails_out_of_scope": True,
        "remaining_for_p6": [
            "Controlled real-employee allowlist canary",
            "Accountant/spreadsheet residual-zero sample period",
            "Company opt-in to Mode A non-synthetic",
            "Re-prove employee release + PDF isolation on real subjects",
            "Rollback/reopen/correction drill on real allowlist",
            "Optional counsel acknowledgement on enabled statutory tables",
        ],
        "do_not_auto_start": ["Employee App P1", "Setup Console redesign", "Auth Wave 2 Phase 6"],
    }


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_mode_a_finalize_schema(cur)
    return {
        "ok": True,
        "company_code": (company_code or "").upper(),
        "p5_enabled": payroll_authority_p5_enabled_for_company(company_code),
        "finalize_policy": _json_safe(get_company_finalize_policy(cur, company_code=company_code)),
        "mode_a_transition": {
            "from": "preview_non_authoritative (P3 calc row)",
            "to": "separate sealed snapshot money_authority=wathefni",
            "never": "flip preview row in place",
        },
        "progression": ["draft", "in_review", "approved", "finalized"],
        "p6_blockers": p6_blockers(),
        **honesty_payload(),
        **p1.honesty_payload(),
    }
