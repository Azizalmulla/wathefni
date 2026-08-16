#!/usr/bin/env python3
"""Wave 2 C4 — Authoritative Payroll (company-scoped).

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).

Gates (fail-closed):
  1) WATHEFNI_PAYROLL_AUTHORITATIVE_C4 must be on (global kill; prod stays off)
  2) company must be in WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES
     (empty allowlist = nobody — never “all companies”)
  3) company must explicitly enable payroll.authoritative_finalize (DB + audit)
  4) optional Attendance/Leave/OT feeds only when company contracts enable them

Reuses Mode A P2→P3→P5 finalize SM + P6 entitlement. Does not rebuild payroll.
No payment movement / WPS / bank send. No invented statutory rates.
E360 remains inputs-only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

PHASE = "payroll_authoritative_c4"
CONTRACT_VERSION = "payroll_authoritative_c4_v1"
_ON = {"1", "true", "yes", "on"}

FEED_MANUAL = "manual"
FEED_IMPORTED = "imported"
FEED_ATTENDANCE = "attendance"
FEED_LEAVE = "leave"
FEED_OT = "ot"
FEED_ALL = "all"
FEED_MODES = (FEED_MANUAL, FEED_IMPORTED, FEED_ATTENDANCE, FEED_LEAVE, FEED_OT, FEED_ALL)

PERIOD_SM = (
    "open",
    "snapshotted",
    "calculated",
    "pending_approval",
    "approved",
    "finalized",
)

STATUS_LABELS = {
    "open": {"en": "Open", "ar": "مفتوح"},
    "snapshotted": {"en": "Snapshotted", "ar": "لقطة مدخلات"},
    "calculated": {"en": "Calculated", "ar": "محسوب"},
    "pending_approval": {"en": "Pending approval", "ar": "بانتظار الاعتماد"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "finalized": {"en": "Finalized", "ar": "مختوم"},
    "preview_non_authoritative": {"en": "Preview (non-authoritative)", "ar": "معاينة غير سلطوية"},
    "authoritative": {"en": "Authoritative", "ar": "سلطوي"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def payroll_authoritative_c4_runtime_on() -> bool:
    return _env_on("WATHEFNI_PAYROLL_AUTHORITATIVE_C4", "off")


def authoritative_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    gate = authoritative_finalize_enabled_for_company(None, company_code) if company_code else {
        "ok": False,
        "enabled": False,
    }
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "authoritative_finalize": bool(gate.get("ok")),
        "payment_processing": "disabled",
        "posts_payment": False,
        "wps_bank_send": False,
        "payslip_release_required": False,
        "e360_is_payroll_calculator": False,
        "attendance_required": False,
        "leave_required": False,
        "shifts_required": False,
        "invented_statutory_rates": False,
        "period_sm": list(PERIOD_SM),
        "synthetic_default_non_authoritative": True,
    }


def ensure_payroll_authoritative_c4_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c4_company_settings (
          company_code text PRIMARY KEY,
          authoritative_finalize boolean NOT NULL DEFAULT false,
          feed_attendance boolean NOT NULL DEFAULT false,
          feed_leave boolean NOT NULL DEFAULT false,
          feed_ot boolean NOT NULL DEFAULT false,
          feed_imported boolean NOT NULL DEFAULT false,
          allow_audited_reopen boolean NOT NULL DEFAULT false,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c4_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          action text NOT NULL,
          actor_phone text,
          reason text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    if force:
        pass


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None,
    reason: str | None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_c4_audit (company_code, action, actor_phone, reason, payload)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            _digits(actor_phone) or None,
            (str(reason).strip() if reason else None),
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any] | None:
    ensure_payroll_authoritative_c4_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_c4_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not payroll_authoritative_c4_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_authoritative_c4_off",
            "gate": "runtime_flag",
            "phase": PHASE,
            "message": "Global PAYROLL_AUTHORITATIVE_C4 is off (production default).",
        }
    allow = authoritative_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_authoritative_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Authoritative company allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_authoritative_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def authoritative_finalize_enabled_for_company(cur: Any | None, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if cur is None:
        return {**gate, "db_checked": False, "message": "Runtime allowlisted; DB enable not checked."}
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("authoritative_finalize"):
        return {
            "ok": False,
            "enabled": False,
            "error": "authoritative_finalize_not_enabled",
            "gate": "company_setting",
            "phase": PHASE,
            "company_code": company_code_norm(company_code),
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company_code_norm(company_code),
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "settings": settings,
        **honesty_payload(company_code=company_code),
    }


def enable_company_authoritative_finalize(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    feed_attendance: bool = False,
    feed_leave: bool = False,
    feed_ot: bool = False,
    feed_imported: bool = False,
    allow_audited_reopen: bool = False,
    entitle_p6: bool = True,
) -> dict[str, Any]:
    """Explicit company opt-in for payroll.authoritative_finalize."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not _digits(actor_phone):
        return {"ok": False, "error": "actor_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_payroll_authoritative_c4_schema(cur)
    cur.execute(
        """
        INSERT INTO payroll_c4_company_settings (
          company_code, authoritative_finalize,
          feed_attendance, feed_leave, feed_ot, feed_imported,
          allow_audited_reopen, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, metadata
        ) VALUES (
          %s,true,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),%s::jsonb
        )
        ON CONFLICT (company_code) DO UPDATE SET
          authoritative_finalize=true,
          feed_attendance=EXCLUDED.feed_attendance,
          feed_leave=EXCLUDED.feed_leave,
          feed_ot=EXCLUDED.feed_ot,
          feed_imported=EXCLUDED.feed_imported,
          allow_audited_reopen=EXCLUDED.allow_audited_reopen,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now(),
          metadata=EXCLUDED.metadata
        RETURNING *
        """,
        (
            company,
            bool(feed_attendance),
            bool(feed_leave),
            bool(feed_ot),
            bool(feed_imported),
            bool(allow_audited_reopen),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
            json.dumps({"phase": PHASE, "contract_version": CONTRACT_VERSION}),
        ),
    )
    row = dict(cur.fetchone())
    p6_result = None
    if entitle_p6:
        try:
            import payroll_authority_production_p6 as p6
            import payroll_authority_wave1 as pyw1

            pyw1.ensure_company_settings(cur, company_code=company)
            cur.execute(
                """
                UPDATE payroll_company_settings
                   SET payroll_mode='native', payment_processing='disabled', updated_at=now()
                 WHERE company_code=%s
                """,
                (company,),
            )
            p6.ensure_payroll_production_p6_schema(cur)
            p6_result = p6.set_company_mode_a_entitlement(
                cur,
                company_code=company,
                entitlement_state="authoritative_allowlisted",
                actor_phone=actor_phone,
                reason=f"c4 enable: {reason}",
                require_readiness=False,
            )
        except Exception as exc:  # noqa: BLE001
            p6_result = {"ok": False, "error": f"p6_entitle_failed:{type(exc).__name__}", "detail": str(exc)}
    _audit(
        cur,
        company_code=company,
        action="enable_authoritative_finalize",
        actor_phone=actor_phone,
        reason=reason,
        payload={"settings": row, "p6": p6_result},
    )
    return {
        "ok": True,
        "company": row,
        "p6": p6_result,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def disable_company_authoritative_finalize(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Rollback entitlement OFF without corrupting finalized sealed snapshots."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_payroll_authoritative_c4_schema(cur)
    cur.execute(
        """
        UPDATE payroll_c4_company_settings
           SET authoritative_finalize=false,
               disabled_at=now(),
               updated_by_phone=%s,
               updated_at=now()
         WHERE company_code=%s
         RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    try:
        import payroll_authority_production_p6 as p6

        p6.set_company_mode_a_entitlement(
            cur,
            company_code=company,
            entitlement_state="preview_only",
            actor_phone=actor_phone,
            reason=f"c4 disable: {reason}",
            require_readiness=False,
        )
    except Exception:
        pass
    _audit(
        cur,
        company_code=company,
        action="disable_authoritative_finalize",
        actor_phone=actor_phone,
        reason=reason,
        payload={"company": dict(row) if row else None},
    )
    return {"ok": True, "company": dict(row) if row else None, "phase": PHASE, "sealed_records_preserved": True}


def configure_input_feeds(
    cur: Any,
    *,
    company_code: str,
    mode: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Apply modularity matrix feed contracts for assemble/calc policy."""
    mode_n = str(mode or "").strip().lower()
    if mode_n not in FEED_MODES:
        return {"ok": False, "error": "invalid_feed_mode", "allowed": list(FEED_MODES)}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_payroll_authoritative_c4_schema(cur)
    import payroll_input_snapshot_p2 as p2

    feeds = {
        "attendance": mode_n in {FEED_ATTENDANCE, FEED_ALL},
        "leave": mode_n in {FEED_LEAVE, FEED_ALL},
        "ot": mode_n in {FEED_OT, FEED_ALL},
        "imported": mode_n in {FEED_IMPORTED, FEED_ALL},
        "manual": mode_n == FEED_MANUAL or mode_n == FEED_IMPORTED,
    }
    # Attendance feed on → informational (consume when present). "required" needs
    # complete approved snapshots and is an operator readiness choice, not default.
    att_mode = "informational" if feeds["attendance"] else "ignored"
    p2.set_attendance_payroll_mode(
        cur,
        company_code=company,
        mode=att_mode,
        actor_phone=actor_phone,
        reason=f"c4 feeds {mode_n}: {reason}",
    )
    existing = get_company_settings(cur, company) or {}
    cur.execute(
        """
        INSERT INTO payroll_c4_company_settings (
          company_code, authoritative_finalize,
          feed_attendance, feed_leave, feed_ot, feed_imported,
          updated_by_phone, updated_at, metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,now(),%s::jsonb)
        ON CONFLICT (company_code) DO UPDATE SET
          feed_attendance=EXCLUDED.feed_attendance,
          feed_leave=EXCLUDED.feed_leave,
          feed_ot=EXCLUDED.feed_ot,
          feed_imported=EXCLUDED.feed_imported,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now(),
          metadata=payroll_c4_company_settings.metadata || EXCLUDED.metadata
        RETURNING *
        """,
        (
            company,
            bool(existing.get("authoritative_finalize")),
            feeds["attendance"],
            feeds["leave"],
            feeds["ot"],
            feeds["imported"],
            _digits(actor_phone),
            json.dumps({"last_feed_mode": mode_n, "at": datetime.utcnow().isoformat() + "Z"}),
        ),
    )
    row = dict(cur.fetchone())
    # Money flags stay fail-closed without counsel/public baselines (no invented rates).
    # OT/sick feeds may still assemble facts; unpaid leave money is an existing approved path.
    policy_flags = {
        "attendance_payroll_mode": att_mode,
        "lateness_money_enabled": False,
        "absence_money_enabled": False,
        "unpaid_leave_money_enabled": feeds["leave"],
        "ot_money_enabled": False,
        "rest_day_money_enabled": False,
        "public_holiday_money_enabled": False,
        "sick_leave_money_enabled": False,
        "ot_facts_enabled": feeds["ot"],
        "attendance_facts_enabled": feeds["attendance"],
        "leave_facts_enabled": feeds["leave"],
    }
    _audit(
        cur,
        company_code=company,
        action="configure_input_feeds",
        actor_phone=actor_phone,
        reason=reason,
        payload={"mode": mode_n, "feeds": feeds, "policy_flags": policy_flags},
    )
    return {
        "ok": True,
        "mode": mode_n,
        "feeds": feeds,
        "policy_flags": policy_flags,
        "company": row,
        "phase": PHASE,
        "disabled_modules_do_not_break_payroll": True,
    }


def assert_input_fingerprint_fresh(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Stale protection: locked snapshot fingerprint must still match live reassemble."""
    import payroll_input_snapshot_p2 as p2

    company = company_code_norm(company_code)
    snap = p2.get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if not snap:
        return {"ok": False, "error": "input_snapshot_not_found"}
    if str(snap.get("status")) != "locked":
        return {"ok": False, "error": "input_snapshot_not_locked", "status": snap.get("status")}
    locked_fp = str(snap.get("content_fingerprint") or "")
    # Observe-only reassemble inside a savepoint so stale checks never mutate authority.
    cur.execute("SAVEPOINT c4_stale_fp_check")
    try:
        reassembled = p2.assemble_payroll_inputs(
            cur,
            company_code=company,
            period_start=snap.get("period_start"),
            period_end=snap.get("period_end"),
            employee_keys=employee_keys,
            actor_phone="c4-stale-check",
            reason="c4 stale fingerprint check (observe)",
        )
        live_fp = None
        if reassembled.get("ok"):
            live_snap = reassembled.get("input_snapshot") or {}
            live_fp = str(live_snap.get("content_fingerprint") or "")
            if str(live_snap.get("input_snapshot_id")) == str(input_snapshot_id):
                live_fp = locked_fp
        else:
            cur.execute("ROLLBACK TO SAVEPOINT c4_stale_fp_check")
            return {"ok": True, "fresh": True, "note": "reassemble_skipped", "detail": reassembled}
        if live_fp and live_fp != locked_fp:
            cur.execute("ROLLBACK TO SAVEPOINT c4_stale_fp_check")
            return {
                "ok": False,
                "error": "stale_input_fingerprint",
                "locked_fingerprint": locked_fp,
                "live_fingerprint": live_fp,
                "phase": PHASE,
            }
    finally:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT c4_stale_fp_check")
        except Exception:
            pass
    return {"ok": True, "fresh": True, "content_fingerprint": locked_fp, "phase": PHASE}


def approve_finalize_with_version(
    cur: Any,
    *,
    company_code: str,
    finalize_run_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """SoD approve with optional stale/concurrent row_version protection."""
    import payroll_authority_mode_a_p5 as p5

    run = p5._get_finalize(cur, company_code=company_code, finalize_run_id=finalize_run_id)  # noqa: SLF001
    if not run:
        return {"ok": False, "error": "finalize_run_not_found"}
    if expected_row_version is not None and int(run.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_finalize_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": run.get("row_version"),
            "phase": PHASE,
        }
    return p5.approve_finalize_run(
        cur,
        company_code=company_code,
        finalize_run_id=finalize_run_id,
        actor_phone=actor_phone,
        reason=reason,
    )


def forbid_period_reopen_if_authoritative(
    cur: Any,
    *,
    company_code: str,
    period_id: str | None = None,
    period_start: Any = None,
    period_end: Any = None,
    allow_audited_reopen: bool | None = None,
) -> dict[str, Any] | None:
    """Return denial dict when reopen would silently unseal an authoritative period."""
    company = company_code_norm(company_code)
    settings = get_company_settings(cur, company) or {}
    allow = bool(settings.get("allow_audited_reopen")) if allow_audited_reopen is None else bool(allow_audited_reopen)
    # Any wathefni sealed snapshot for the period blocks silent reopen
    cur.execute(
        """
        SELECT authority_snapshot_id::text
          FROM payroll_authority_snapshots
         WHERE company_code=%s AND money_authority='wathefni' AND status='sealed'
           AND (
             (%s::date IS NOT NULL AND period_start=%s::date AND period_end=%s::date)
             OR (%s::text IS NOT NULL AND provenance->>'period_id'=%s)
           )
         LIMIT 1
        """,
        (
            company,
            period_start,
            period_start,
            period_end,
            period_id,
            str(period_id) if period_id else None,
        ),
    )
    sealed = cur.fetchone()
    if sealed and not allow:
        return {
            "ok": False,
            "error": "authoritative_period_reopen_forbidden",
            "message": "Finalized authoritative payroll cannot be reopened without explicit audited reopen policy.",
            "phase": PHASE,
        }
    return None


def authoritative_finalize(
    cur: Any,
    *,
    company_code: str,
    finalize_run_id: str,
    actor_phone: str,
    reason: str,
    employee_keys: list[str] | None = None,
    check_stale_inputs: bool = True,
) -> dict[str, Any]:
    """Company-scoped authoritative finalize wrapper over Mode A P5."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = authoritative_finalize_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return {**gate, "error": gate.get("error") or "authoritative_finalize_not_enabled"}

    import payroll_authority_mode_a_p5 as p5

    run = p5._get_finalize(cur, company_code=company_code, finalize_run_id=finalize_run_id)  # noqa: SLF001
    if not run:
        return {"ok": False, "error": "finalize_run_not_found"}

    if check_stale_inputs:
        calc = None
        try:
            import payroll_components_policy_p3 as p3

            calc = p3.get_calc_run(cur, company_code=company_code, calc_run_id=str(run.get("calc_run_id")))
        except Exception:
            calc = None
        if calc and calc.get("input_snapshot_id"):
            fresh = assert_input_fingerprint_fresh(
                cur,
                company_code=company_code,
                input_snapshot_id=str(calc.get("input_snapshot_id")),
                employee_keys=employee_keys,
            )
            if not fresh.get("ok"):
                return fresh

    before = {
        "finalize_status": run.get("status"),
        "money_authority": run.get("money_authority"),
        "row_version": run.get("row_version"),
    }
    result = p5.finalize_mode_a(
        cur,
        company_code=company_code,
        finalize_run_id=finalize_run_id,
        actor_phone=actor_phone,
        reason=reason,
        employee_keys=employee_keys,
    )
    after = {
        "finalize_status": (result.get("finalize_run") or {}).get("status"),
        "money_authority": (result.get("finalize_run") or {}).get("money_authority"),
        "row_version": (result.get("finalize_run") or {}).get("row_version"),
        "sealed_count": len(result.get("authority_snapshots") or []),
    }
    _audit(
        cur,
        company_code=company_code,
        action="authoritative_finalize",
        actor_phone=actor_phone,
        reason=reason,
        payload={"before": before, "after": after, "ok": result.get("ok"), "idempotent": result.get("idempotent")},
    )
    if not result.get("ok"):
        return {**result, "phase": PHASE}
    return {
        **result,
        "authoritative": True,
        "period_state": "finalized",
        "phase": PHASE,
        "audit_before": before,
        "audit_after": after,
        **honesty_payload(company_code=company_code),
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "WATHEFNI_PAYROLL_AUTHORITATIVE_C4=off",
            "Clear WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES",
            "disable_company_authoritative_finalize(canary) → preview_only",
            "Sealed wathefni snapshots remain immutable (no silent unseal)",
            "payment_processing stays disabled",
        ],
    }
