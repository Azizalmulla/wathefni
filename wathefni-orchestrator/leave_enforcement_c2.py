#!/usr/bin/env python3
"""Wave 2 C2 — Leave Enforcement + optional N-step / delegation.

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).
Amends leave freeze for company-scoped canary only — global enforcement stays OFF.

Gates (all required for enforcement):
  1) WATHEFNI_LEAVE_ENFORCEMENT=on (global kill; prod default off)
  2) company in WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES (empty = nobody)
  3) versioned company leave-policy pack bound
  4) pack counsel/legal attestation recorded for that company+pack version
  5) company enforcement row enabled

Ledger remains append-only balance authority.
Unpaid skips balance (no fake balance).
Optional workflow_approvals bind; single-step remains default when unbound/off.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

PHASE = "leave_enforcement_c2"
CONTRACT_VERSION = "leave_enforcement_c2_v1"
_ON = {"1", "true", "yes", "on"}
SUBJECT_LEAVE = "leave_request"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leave_enforcement_company (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  pack_code text NOT NULL,
  pack_version text NOT NULL,
  legal_reviewed boolean NOT NULL DEFAULT false,
  reviewed_by text,
  reviewed_at timestamptz,
  attestation_ref text,
  attestation_reason text,
  approval_policy_id uuid,
  require_balance boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS leave_enforcement_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  actor_phone text,
  reason text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def leave_enforcement_runtime_on() -> bool:
    return _env_on("WATHEFNI_LEAVE_ENFORCEMENT", "off")


def leave_enforcement_company_allowlist() -> set[str]:
    raw = str(
        os.environ.get("WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES")
        or os.environ.get("WATHEFNI_LEAVE_TRUTH_COMPANIES")
        or ""
    ).strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def ensure_leave_enforcement_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO leave_enforcement_audit (company_code, action, actor_phone, reason, payload)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            actor_phone,
            (reason or "")[:500] or None,
            json.dumps(payload or {}),
        ),
    )


def get_company_enforcement_row(cur: Any, company_code: str) -> dict[str, Any] | None:
    company = company_code_norm(company_code)
    ensure_leave_enforcement_schema(cur)
    cur.execute("SELECT * FROM leave_enforcement_company WHERE company_code=%s LIMIT 1", (company,))
    row = cur.fetchone()
    return dict(row) if row else None


def attest_company_policy_pack(
    cur: Any,
    *,
    company_code: str,
    pack_code: str,
    pack_version: str,
    reviewed_by: str,
    attestation_reason: str,
    attestation_ref: str | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Record counsel/legal review for a bound pack version. Required before enable."""
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "error": "company_required"}
    if not str(reviewed_by or "").strip():
        return {"ok": False, "error": "reviewed_by_required"}
    if not str(attestation_reason or "").strip():
        return {"ok": False, "error": "attestation_reason_required"}
    ensure_leave_enforcement_schema(cur)
    # Pack must exist
    cur.execute(
        "SELECT pack_code, version FROM leave_policy_packs WHERE pack_code=%s AND version=%s LIMIT 1",
        (pack_code, pack_version),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "policy_pack_not_found", "pack_code": pack_code, "pack_version": pack_version}
    # Bind company to pack
    import leave_policy_wave2 as lp

    lp.bind_company_policy_pack(cur, company, pack_code=pack_code, pack_version=pack_version)
    cur.execute(
        """
        INSERT INTO leave_enforcement_company (
          company_code, enabled, pack_code, pack_version, legal_reviewed,
          reviewed_by, reviewed_at, attestation_ref, attestation_reason, updated_at
        ) VALUES (%s,false,%s,%s,true,%s,now(),%s,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          pack_code=EXCLUDED.pack_code,
          pack_version=EXCLUDED.pack_version,
          legal_reviewed=true,
          reviewed_by=EXCLUDED.reviewed_by,
          reviewed_at=now(),
          attestation_ref=EXCLUDED.attestation_ref,
          attestation_reason=EXCLUDED.attestation_reason,
          enabled=false,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            pack_code,
            pack_version,
            str(reviewed_by).strip()[:120],
            (attestation_ref or "")[:200] or None,
            str(attestation_reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="policy_pack_attested",
        actor_phone=actor_phone or reviewed_by,
        reason=attestation_reason,
        payload={"pack_code": pack_code, "pack_version": pack_version, "ref": attestation_ref},
    )
    return {"ok": True, "company": row, "phase": PHASE}


def enable_company_enforcement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    approval_policy_id: str | None = None,
) -> dict[str, Any]:
    """Enable leave.enforced for company only after pack attestation."""
    company = company_code_norm(company_code)
    if not leave_enforcement_runtime_on():
        return {"ok": False, "error": "leave_enforcement_runtime_off", "gate": "runtime_flag"}
    allow = leave_enforcement_company_allowlist()
    if not allow or company not in allow:
        return {"ok": False, "error": "leave_enforcement_company_not_allowlisted", "gate": "company_allowlist"}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    row = get_company_enforcement_row(cur, company)
    if not row or not row.get("legal_reviewed"):
        return {"ok": False, "error": "policy_pack_attestation_required"}
    if not row.get("pack_code") or not row.get("pack_version"):
        return {"ok": False, "error": "policy_pack_binding_required"}
    cur.execute(
        """
        UPDATE leave_enforcement_company
           SET enabled=true,
               approval_policy_id=COALESCE(%s::uuid, approval_policy_id),
               updated_at=now()
         WHERE company_code=%s
        RETURNING *
        """,
        (approval_policy_id, company),
    )
    updated = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enforcement_enabled",
        actor_phone=actor_phone,
        reason=reason,
        payload={"pack_code": updated.get("pack_code"), "pack_version": updated.get("pack_version")},
    )
    return {"ok": True, "company": updated, "phase": PHASE}


def disable_company_enforcement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None = None,
    reason: str = "disable",
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_leave_enforcement_schema(cur)
    cur.execute(
        "UPDATE leave_enforcement_company SET enabled=false, updated_at=now() WHERE company_code=%s RETURNING *",
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="enforcement_disabled", actor_phone=actor_phone, reason=reason)
    return {"ok": True, "company": dict(row) if row else None}


def leave_enforcement_enabled_for_company(cur: Any | None, company_code: str | None) -> dict[str, Any]:
    """Fail-closed company enforcement gate."""
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not leave_enforcement_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "leave_enforcement_runtime_off",
            "gate": "runtime_flag",
            "phase": PHASE,
            "observe_only": True,
        }
    allow = leave_enforcement_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "leave_enforcement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "observe_only": True,
            "message": "Enforcement allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "leave_enforcement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "observe_only": True,
            "company_code": company,
        }
    if cur is None:
        return {
            "ok": False,
            "enabled": False,
            "error": "policy_pack_attestation_required",
            "gate": "db_required",
            "phase": PHASE,
            "observe_only": True,
        }
    row = get_company_enforcement_row(cur, company)
    if not row or not row.get("legal_reviewed"):
        return {
            "ok": False,
            "enabled": False,
            "error": "policy_pack_attestation_required",
            "gate": "policy_pack",
            "phase": PHASE,
            "observe_only": True,
        }
    if not row.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "leave_enforcement_company_disabled",
            "gate": "company_setting",
            "phase": PHASE,
            "observe_only": True,
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company,
        "pack_code": row.get("pack_code"),
        "pack_version": row.get("pack_version"),
        "legal_reviewed": True,
        "balances_enforced": True,
        "balances_binding": True,
        "observe_only": False,
        "approval_policy_id": str(row.get("approval_policy_id") or "") or None,
        "require_balance": bool(row.get("require_balance", True)),
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
    }


def honesty_flags_for_company(cur: Any | None, company_code: str | None) -> dict[str, Any]:
    gate = leave_enforcement_enabled_for_company(cur, company_code)
    if gate.get("ok"):
        return {
            "balances_enforced": True,
            "legal_reviewed": True,
            "balances_binding": True,
            "observe_only": False,
            "phase": PHASE,
        }
    return {
        "balances_enforced": False,
        "legal_reviewed": False,
        "balances_binding": False,
        "observe_only": True,
        "phase": PHASE,
        "gate": gate.get("gate") or gate.get("error"),
    }


def reserve_with_enforcement(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any],
    actor_phone: str | None = None,
    override: bool = False,
    override_reason: str | None = None,
    override_actor_phone: str | None = None,
) -> dict[str, Any]:
    """Wrap leave_policy.reserve_leave_balance with fail-closed enforcement."""
    import leave_policy_wave2 as lp

    gate = leave_enforcement_enabled_for_company(cur, company_code)
    leave_type = str(leave.get("leave_type") or "")
    if leave_type == "unpaid" or policy.get("payroll_boundary"):
        return {
            "ok": True,
            "skipped": True,
            "reason": "unpaid_payroll_boundary",
            "balances_enforced": bool(gate.get("ok")),
            "legal_reviewed": bool(gate.get("ok")),
        }

    result = lp.reserve_leave_balance(
        cur,
        company_code=company_code,
        leave=leave,
        policy=policy,
        actor_phone=actor_phone,
    )
    if not gate.get("ok"):
        # Observe-only path unchanged
        return {**result, **honesty_flags_for_company(cur, company_code)}

    insufficient = bool(result.get("insufficient_balance_observe")) or (
        result.get("ok") is False and result.get("error") == "insufficient_balance"
    )
    if insufficient:
        if override:
            if not str(override_reason or "").strip():
                return {"ok": False, "error": "override_reason_required", "balances_enforced": True}
            if not str(override_actor_phone or actor_phone or "").strip():
                return {"ok": False, "error": "override_actor_required", "balances_enforced": True}
            # Force reservation with allow_negative policy copy
            forced_policy = {**policy, "allow_negative": True}
            forced = lp.reserve_leave_balance(
                cur,
                company_code=company_code,
                leave=leave,
                policy=forced_policy,
                actor_phone=override_actor_phone or actor_phone,
            )
            _audit(
                cur,
                company_code=company_code,
                action="balance_override_reserve",
                actor_phone=override_actor_phone or actor_phone,
                reason=override_reason,
                payload={
                    "leave_id": leave.get("leave_id"),
                    "days": forced.get("days") or result.get("days"),
                    "available_before": result.get("available_before"),
                },
            )
            return {
                **forced,
                "ok": True if forced.get("ok", True) else False,
                "override": True,
                "balances_enforced": True,
                "legal_reviewed": True,
                "insufficient_balance_observe": False,
            }
        return {
            "ok": False,
            "error": "insufficient_balance",
            "days": result.get("days"),
            "available_before": result.get("available_before"),
            "balances_enforced": True,
            "legal_reviewed": True,
            "observe_only": False,
        }

    return {
        **result,
        "ok": True if result.get("ok", True) else False,
        "balances_enforced": True,
        "legal_reviewed": True,
        "insufficient_balance_observe": False,
        "observe_only": False,
    }


def post_balance_adjustment(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    leave_type: str,
    days: Decimal | float | int | str,
    actor_phone: str,
    reason: str,
    period_year: int | None = None,
) -> dict[str, Any]:
    """Privileged append-only ledger adjustment + recompute."""
    company = company_code_norm(company_code)
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not str(actor_phone or "").strip():
        return {"ok": False, "error": "actor_required"}
    amt = Decimal(str(days))
    if amt == 0:
        return {"ok": False, "error": "adjustment_days_required"}
    year = int(period_year or date.today().year)
    period = f"{year}-01"
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period, leave_id,
          observe_only, actor_phone, reason
        ) VALUES (%s,%s,%s,'adjustment',%s,%s,NULL,false,%s,%s)
        RETURNING days, entry_kind, leave_type, created_at
        """,
        (company, employee_key, leave_type, amt, period, actor_phone, str(reason).strip()[:500]),
    )
    row = dict(cur.fetchone())
    import leave_policy_wave2 as lp

    ent = Decimal("30")
    bal = lp.recompute_balance_with_reservations(
        cur,
        company_code=company,
        employee_key=employee_key,
        leave_type=leave_type,
        period_year=year,
        entitlement_days=ent,
    )
    _audit(
        cur,
        company_code=company,
        action="balance_adjustment",
        actor_phone=actor_phone,
        reason=reason,
        payload={"days": float(amt), "leave_type": leave_type},
    )
    return {"ok": True, "ledger": row, "balance": bal, "phase": PHASE}


def bind_leave_approval_policy(
    cur: Any,
    *,
    company_code: str,
    name: str,
    steps: list[dict[str, Any]],
    forbid_self_approval: bool = True,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Create/activate workflow_approvals policy for leave_request (optional integration)."""
    import workflow_approvals as wa

    company = company_code_norm(company_code)
    gate = wa.workflow_approvals_enabled_for_company(cur, company)
    if not gate.get("ok"):
        return {"ok": False, "error": "workflow_approvals_disabled", "gate": gate}
    created = wa.upsert_policy(
        cur,
        company_code=company,
        subject_type=SUBJECT_LEAVE,
        name=name,
        steps=steps,
        forbid_self_approval=forbid_self_approval,
        activate=True,
        actor_user_id=actor_user_id,
    )
    if not created.get("ok"):
        return created
    policy = created.get("policy") or {}
    policy_id = policy.get("policy_id")
    ensure_leave_enforcement_schema(cur)
    cur.execute(
        """
        UPDATE leave_enforcement_company
           SET approval_policy_id=%s::uuid, updated_at=now()
         WHERE company_code=%s
        """,
        (policy_id, company),
    )
    _audit(
        cur,
        company_code=company,
        action="approval_policy_bound",
        actor_phone=actor_user_id,
        reason="bind_leave_n_step",
        payload={"policy_id": str(policy_id)},
    )
    return {"ok": True, "policy_id": policy_id, "subject_type": SUBJECT_LEAVE, **created}


def start_leave_approval_if_bound(
    cur: Any,
    *,
    company_code: str,
    leave_id: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """OPTIONAL: start N-step instance when policy bound; else skipped for single-step."""
    gate = leave_enforcement_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return {"ok": True, "skipped": True, "reason": "enforcement_off"}
    policy_id = gate.get("approval_policy_id")
    if not policy_id:
        return {"ok": True, "skipped": True, "reason": "single_step_fallback"}
    import workflow_approvals as wa

    wa_gate = wa.workflow_approvals_enabled_for_company(cur, company_code)
    if not wa_gate.get("ok"):
        return {"ok": True, "skipped": True, "reason": "workflow_approvals_off", "fallback": "single_step"}
    return wa.create_instance(
        cur,
        company_code=company_code,
        subject_type=SUBJECT_LEAVE,
        subject_id=str(leave_id),
        created_by_user_id=created_by_user_id,
        submit=True,
    )


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "Set WATHEFNI_LEAVE_ENFORCEMENT=off",
            "Clear WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES",
            "disable_company_enforcement for canary company",
            "Do not DROP leave_ledger / leave_enforcement_* tables",
            "Leave single-step path remains available",
        ],
    }
