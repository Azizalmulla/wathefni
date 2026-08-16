#!/usr/bin/env python3
"""Wave 2 C5 — Payslips release + Payment files (company-scoped).

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).

Payslips: reuse Wave 3 / P5 sealed generate → release|void (revoked).
Payment files: new SM draft → generated → acknowledged|failed|cancelled.

Gates (fail-closed):
  1) WATHEFNI_PAYROLL_PAYMENT_C5 must be on (global kill for C5 runtime; prod stays off)
  2) company must be in WATHEFNI_PAYROLL_PAYMENT_COMPANIES (empty = nobody)
  3) payslip release uses existing Wave 3 release (sealed/finalized only for Mode A path)
  4) payment-file generate requires company payment_processing entitlement in C5 settings
  5) WATHEFNI_PAYROLL_PAYMENT_KILL=on immediately blocks new payment-file generation

Semantic contract:
  acknowledged = Wathefni recorded configured operational acknowledgement.
  It does NOT mean employees were paid or bank settlement succeeded.

Does NOT: transfer funds, initiate bank payments, invent WPS/bank requirements,
auto-mark payroll paid from file generation. Does not require Attendance/Leave/Shifts.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Any

PHASE = "payroll_payslip_payment_c5"
CONTRACT_VERSION = "payroll_payslip_payment_c5_v1"
_ON = {"1", "true", "yes", "on"}

# Versioned synthetic format pack — never claims real WPS/bank compliance.
FORMAT_PACK_KW_WPS_STUB_V1 = "kw_wps_stub_v1"
FORMAT_PACKS = {
    FORMAT_PACK_KW_WPS_STUB_V1: {
        "id": FORMAT_PACK_KW_WPS_STUB_V1,
        "version": "1.0.0",
        "real_bank_format": False,
        "real_wps_format": False,
        "description_en": "Synthetic Kuwait WPS-shaped stub for canary qualification only",
        "description_ar": "حزمة تجريبية لشكل WPS الكويتي للتأهيل فقط",
    }
}

PF_DRAFT = "draft"
PF_GENERATED = "generated"
PF_ACKNOWLEDGED = "acknowledged"
PF_FAILED = "failed"
PF_CANCELLED = "cancelled"
PF_STATUSES = (PF_DRAFT, PF_GENERATED, PF_ACKNOWLEDGED, PF_FAILED, PF_CANCELLED)

STATUS_LABELS = {
    "generated": {"en": "Generated", "ar": "تم الإنشاء"},
    "released": {"en": "Released", "ar": "تم الإصدار"},
    "voided": {"en": "Voided", "ar": "ملغى"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "acknowledged": {"en": "Acknowledged (ops)", "ar": "إقرار تشغيلي"},
    "failed": {"en": "Failed", "ar": "فشل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "not_released": {"en": "Not released", "ar": "غير صادر"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def payroll_payment_c5_runtime_on() -> bool:
    return _env_on("WATHEFNI_PAYROLL_PAYMENT_C5", "off")


def payment_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_PAYMENT_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def payment_kill_switch_active() -> bool:
    """Immediate block on new payment-file generation."""
    return _env_on("WATHEFNI_PAYROLL_PAYMENT_KILL", "off")


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "posts_payment": False,
        "transfers_funds": False,
        "initiates_bank_payment": False,
        "claims_bank_settlement": False,
        "acknowledged_is_not_paid": True,
        "auto_mark_payroll_paid_from_file": False,
        "real_bank_format": False,
        "real_wps_format": False,
        "invented_wps_requirements": False,
        "payment_kill_switch": payment_kill_switch_active(),
        "attendance_required": False,
        "leave_required": False,
        "shifts_required": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not payroll_payment_c5_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_payment_c5_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = payment_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_payment_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Payment company allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_payment_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_payroll_payslip_payment_c5_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c5_company_settings (
          company_code text PRIMARY KEY,
          payslip_release_enabled boolean NOT NULL DEFAULT true,
          payment_processing_enabled boolean NOT NULL DEFAULT false,
          default_format_pack_id text NOT NULL DEFAULT 'kw_wps_stub_v1',
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
        CREATE TABLE IF NOT EXISTS payroll_payment_files (
          payment_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          finalize_run_id text,
          period_start date NOT NULL,
          period_end date NOT NULL,
          authority_snapshot_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          authority_fingerprint text NOT NULL,
          format_pack_id text NOT NULL,
          format_pack_version text NOT NULL DEFAULT '1.0.0',
          status text NOT NULL DEFAULT 'draft',
          content_fingerprint text,
          file_payload text,
          file_bytes_sha256 text,
          row_version int NOT NULL DEFAULT 1,
          posts_payment boolean NOT NULL DEFAULT false,
          acknowledged_is_not_paid boolean NOT NULL DEFAULT true,
          real_bank_format boolean NOT NULL DEFAULT false,
          real_wps_format boolean NOT NULL DEFAULT false,
          decision_note text,
          created_by_phone text,
          generated_by_phone text,
          generated_at timestamptz,
          acknowledged_by_phone text,
          acknowledged_at timestamptz,
          failed_by_phone text,
          failed_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT payroll_payment_files_status_chk
            CHECK (status IN ('draft','generated','acknowledged','failed','cancelled')),
          CONSTRAINT payroll_payment_files_no_money_chk
            CHECK (posts_payment = false AND acknowledged_is_not_paid = true),
          CONSTRAINT payroll_payment_files_no_real_format_chk
            CHECK (real_bank_format = false AND real_wps_format = false)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_payroll_payment_files_idempotent
          ON payroll_payment_files (company_code, authority_fingerprint, format_pack_id)
          WHERE status IN ('draft','generated','acknowledged')
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c5_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None,
    reason: str | None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_c5_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            _digits(actor_phone) or None,
            (str(reason).strip() if reason else None),
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any] | None:
    ensure_payroll_payslip_payment_c5_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_c5_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_payment_processing(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    format_pack_id: str = FORMAT_PACK_KW_WPS_STUB_V1,
) -> dict[str, Any]:
    """Company-scoped payment_processing entitlement (C5 settings — not wave1 money rails)."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    pack = FORMAT_PACKS.get(str(format_pack_id or "").strip())
    if not pack:
        return {"ok": False, "error": "unknown_format_pack", "allowed": sorted(FORMAT_PACKS)}
    company = company_code_norm(company_code)
    ensure_payroll_payslip_payment_c5_schema(cur)
    cur.execute(
        """
        INSERT INTO payroll_c5_company_settings (
          company_code, payslip_release_enabled, payment_processing_enabled,
          default_format_pack_id, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, metadata
        ) VALUES (%s,true,true,%s,%s,%s,now(),%s,now(),%s::jsonb)
        ON CONFLICT (company_code) DO UPDATE SET
          payment_processing_enabled=true,
          default_format_pack_id=EXCLUDED.default_format_pack_id,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            pack["id"],
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
            json.dumps({"phase": PHASE, "format_pack": pack}),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_payment_processing",
        actor_phone=actor_phone,
        reason=reason,
        payload={"settings": row},
    )
    return {"ok": True, "company": row, "format_pack": pack, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_payment_processing(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_payroll_payslip_payment_c5_schema(cur)
    cur.execute(
        """
        UPDATE payroll_c5_company_settings
           SET payment_processing_enabled=false,
               disabled_at=now(),
               updated_by_phone=%s,
               updated_at=now()
         WHERE company_code=%s
         RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    _audit(
        cur,
        company_code=company,
        action="disable_payment_processing",
        actor_phone=actor_phone,
        reason=reason,
        payload={"company": dict(row) if row else None},
    )
    return {"ok": True, "company": dict(row) if row else None, "phase": PHASE}


def payment_processing_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("payment_processing_enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "payment_processing_not_enabled",
            "gate": "company_entitlement",
            "phase": PHASE,
            "company_code": company_code_norm(company_code),
        }
    if payment_kill_switch_active():
        return {
            "ok": False,
            "enabled": False,
            "error": "payment_kill_switch_active",
            "gate": "kill_switch",
            "phase": PHASE,
            "company_code": company_code_norm(company_code),
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company_code_norm(company_code),
        "settings": settings,
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


# --------------------------------------------------------------------------- Payslips


def charter_payslip_state(doc: dict[str, Any] | None) -> str:
    """Map Wave 3 status/visibility onto charter generated → released | voided."""
    import payroll_payslip_wave3 as w3

    if not doc:
        return "unknown"
    if str(doc.get("status") or "") == w3.STATUS_REVOKED:
        return "voided"
    if w3.employee_can_view(doc):
        return "released"
    return "generated"


def generate_payslip_from_sealed(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Generate payslip from sealed/finalized payroll authority snapshot only."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_snapshot_p1 as p1

    snap = p1.get_sealed_snapshot_by_id(
        cur, company_code=company_code, authority_snapshot_id=authority_snapshot_id
    )
    if not snap or str(snap.get("status")) != "sealed":
        return {"ok": False, "error": "requires_sealed_finalized_payroll"}
    if str(snap.get("money_authority")) not in {"wathefni", "external"}:
        return {"ok": False, "error": "requires_authoritative_money_authority", "money_authority": snap.get("money_authority")}

    result = p5.generate_wathefni_payslip_from_sealed(
        cur,
        company_code=company_code,
        authority_snapshot_id=authority_snapshot_id,
        actor_phone=actor_phone,
        reason=reason,
    )
    if result.get("ok"):
        payslip = result.get("payslip") or {}
        _audit(
            cur,
            company_code=company_code,
            action="payslip_generated_from_sealed",
            actor_phone=actor_phone,
            reason=reason,
            subject_type="payslip",
            subject_id=str(payslip.get("payslip_id") or ""),
            payload={"authority_snapshot_id": authority_snapshot_id, "charter_state": charter_payslip_state(payslip)},
        )
        result = {
            **result,
            "charter_state": charter_payslip_state(payslip),
            "phase": PHASE,
            **honesty_payload(company_code=company_code),
        }
    return result


def release_payslip(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str,
    reason: str,
    notify: bool = True,
) -> dict[str, Any]:
    """HR release control — employee cannot see before this."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    import payroll_payslip_wave3 as w3

    before = w3.get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
    result = w3.release_payslip_to_employee(
        cur,
        company_code=company_code,
        payslip_id=payslip_id,
        actor_phone=actor_phone,
        reason=reason,
    )
    if not result.get("ok"):
        return {**result, "phase": PHASE}
    payslip = result.get("payslip") or {}
    _audit(
        cur,
        company_code=company_code,
        action="payslip_released",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="payslip",
        subject_id=payslip_id,
        payload={
            "before_state": charter_payslip_state(before),
            "after_state": charter_payslip_state(payslip),
            "employee_key": payslip.get("employee_key"),
            "notify": bool(notify),
        },
    )
    notification = None
    if notify and not result.get("idempotent"):
        notification = {
            "ok": True,
            "channel": "canonical_audit_event",
            "event": "payslip_released",
            "employee_key": payslip.get("employee_key"),
            "message_en": "Your payslip is ready.",
            "message_ar": "كشف راتبك جاهز.",
        }
    return {
        **result,
        "charter_state": "released",
        "employee_visible": True,
        "notification": notification,
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


def void_payslip(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Audited void path (Wave 3 revoke)."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    import payroll_payslip_wave3 as w3

    result = w3.revoke_payslip(
        cur,
        company_code=company_code,
        payslip_id=payslip_id,
        actor_phone=actor_phone,
        reason=reason,
    )
    if result.get("ok"):
        _audit(
            cur,
            company_code=company_code,
            action="payslip_voided",
            actor_phone=actor_phone,
            reason=reason,
            subject_type="payslip",
            subject_id=payslip_id,
            payload={"charter_state": "voided"},
        )
    return {**result, "charter_state": "voided" if result.get("ok") else None, "phase": PHASE}


def employee_payslip_visible(doc: dict[str, Any] | None) -> bool:
    import payroll_payslip_wave3 as w3

    return bool(w3.employee_can_view(doc))


def assert_payslip_bound_to_sealed(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
) -> dict[str, Any]:
    import payroll_payslip_wave3 as w3
    import payroll_authority_snapshot_p1 as p1

    doc = w3.get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    payload = doc.get("statement_payload") or doc.get("document_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    aid = str(
        doc.get("authority_snapshot_id")
        or doc.get("source_run_id")
        or (payload or {}).get("authority_snapshot_id")
        or (doc.get("provenance") or {}).get("authority_snapshot_id")
        or ""
    )
    if not aid:
        return {"ok": False, "error": "payslip_missing_authority_binding", "payslip_id": payslip_id}
    snap = p1.get_sealed_snapshot_by_id(cur, company_code=company_code, authority_snapshot_id=aid)
    if not snap or str(snap.get("status")) != "sealed":
        return {"ok": False, "error": "payslip_not_tied_to_sealed_payroll", "authority_snapshot_id": aid}
    return {
        "ok": True,
        "payslip_id": payslip_id,
        "authority_snapshot_id": aid,
        "money_authority": snap.get("money_authority"),
        "immutable_relative_to_seal": True,
        "phase": PHASE,
    }


# --------------------------------------------------------------------------- Payment files


def _authority_fingerprint(
    *,
    company_code: str,
    period_start: Any,
    period_end: Any,
    finalize_run_id: str | None,
    snapshot_ids: list[str],
) -> str:
    raw = json.dumps(
        {
            "company": company_code_norm(company_code),
            "period_start": str(period_start)[:10],
            "period_end": str(period_end)[:10],
            "finalize_run_id": finalize_run_id or "",
            "authority_snapshot_ids": sorted(snapshot_ids),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _render_format_pack(
    *,
    pack_id: str,
    company_code: str,
    period_start: Any,
    period_end: Any,
    finalize_run_id: str | None,
    lines: list[dict[str, Any]],
    authority_fingerprint: str,
) -> dict[str, Any]:
    pack = FORMAT_PACKS.get(pack_id)
    if not pack:
        return {"ok": False, "error": "unknown_format_pack"}
    # Stub only — structured text with provenance. Never invent real WPS field requirements.
    body_lines = [
        f"# format_pack={pack['id']} version={pack['version']}",
        f"# real_bank_format=false real_wps_format=false",
        f"# company={company_code_norm(company_code)}",
        f"# period={str(period_start)[:10]}..{str(period_end)[:10]}",
        f"# finalize_run_id={finalize_run_id or ''}",
        f"# authority_fingerprint={authority_fingerprint}",
        f"# posts_payment=false acknowledged_is_not_paid=true",
        "employee_key,net_amount,currency",
    ]
    for ln in lines:
        body_lines.append(
            f"{ln.get('employee_key')},{ln.get('net_amount')},{ln.get('currency') or 'KWD'}"
        )
    payload = "\n".join(body_lines) + "\n"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "ok": True,
        "format_pack": pack,
        "file_payload": payload,
        "file_bytes_sha256": digest,
        "content_fingerprint": digest,
    }


def create_payment_file_draft(
    cur: Any,
    *,
    company_code: str,
    period_start: Any,
    period_end: Any,
    actor_phone: str,
    reason: str,
    finalize_run_id: str | None = None,
    authority_snapshot_ids: list[str] | None = None,
    format_pack_id: str | None = None,
) -> dict[str, Any]:
    """Create payment-file draft bound to exact finalized payroll provenance."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = payment_processing_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    import payroll_authority_snapshot_p1 as p1

    company = company_code_norm(company_code)
    ensure_payroll_payslip_payment_c5_schema(cur)
    settings = ent.get("settings") or {}
    pack_id = str(format_pack_id or settings.get("default_format_pack_id") or FORMAT_PACK_KW_WPS_STUB_V1)
    if pack_id not in FORMAT_PACKS:
        return {"ok": False, "error": "unknown_format_pack", "allowed": sorted(FORMAT_PACKS)}

    ids = [str(x) for x in (authority_snapshot_ids or []) if str(x).strip()]
    if not ids and finalize_run_id:
        cur.execute(
            """
            SELECT authority_snapshot_id::text
              FROM payroll_authority_snapshots
             WHERE company_code=%s AND money_authority='wathefni' AND status='sealed'
               AND provenance->>'finalize_run_id'=%s
             ORDER BY employee_key
            """,
            (company, str(finalize_run_id)),
        )
        ids = [str(r["authority_snapshot_id"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])]
    if not ids:
        cur.execute(
            """
            SELECT authority_snapshot_id::text
              FROM payroll_authority_snapshots
             WHERE company_code=%s AND money_authority IN ('wathefni','external') AND status='sealed'
               AND period_start=%s AND period_end=%s
             ORDER BY employee_key
            """,
            (company, str(period_start)[:10], str(period_end)[:10]),
        )
        ids = [str(r["authority_snapshot_id"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])]
    if not ids:
        return {"ok": False, "error": "no_sealed_finalized_payroll_for_period"}

    lines = []
    for aid in ids:
        snap = p1.get_sealed_snapshot_by_id(cur, company_code=company, authority_snapshot_id=aid)
        if not snap:
            return {"ok": False, "error": "authority_snapshot_not_found", "authority_snapshot_id": aid}
        totals = snap.get("totals") or {}
        if isinstance(snap.get("snapshot_payload"), dict):
            totals = (snap.get("snapshot_payload") or {}).get("totals") or totals
        lines.append(
            {
                "employee_key": snap.get("employee_key"),
                "net_amount": float(
                    totals.get("net")
                    or snap.get("totals_net")
                    or 0
                ),
                "currency": "KWD",
                "authority_snapshot_id": aid,
            }
        )

    fp = _authority_fingerprint(
        company_code=company,
        period_start=period_start,
        period_end=period_end,
        finalize_run_id=finalize_run_id,
        snapshot_ids=ids,
    )
    # Idempotent draft/generated for same provenance+pack
    cur.execute(
        """
        SELECT * FROM payroll_payment_files
         WHERE company_code=%s AND authority_fingerprint=%s AND format_pack_id=%s
           AND status IN ('draft','generated','acknowledged')
         ORDER BY created_at DESC LIMIT 1
        """,
        (company, fp, pack_id),
    )
    existing = cur.fetchone()
    if existing:
        row = dict(existing)
        return {
            "ok": True,
            "idempotent": True,
            "payment_file": row,
            "phase": PHASE,
            **honesty_payload(company_code=company),
        }

    cur.execute(
        """
        INSERT INTO payroll_payment_files (
          company_code, finalize_run_id, period_start, period_end,
          authority_snapshot_ids, authority_fingerprint, format_pack_id, format_pack_version,
          status, decision_note, created_by_phone, metadata
        ) VALUES (
          %s,%s,%s,%s,%s::jsonb,%s,%s,%s,'draft',%s,%s,%s::jsonb
        )
        RETURNING *
        """,
        (
            company,
            str(finalize_run_id) if finalize_run_id else None,
            str(period_start)[:10],
            str(period_end)[:10],
            json.dumps(ids),
            fp,
            pack_id,
            FORMAT_PACKS[pack_id]["version"],
            str(reason).strip()[:500],
            _digits(actor_phone),
            json.dumps({"lines": lines, "phase": PHASE}, default=str),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="payment_file_draft_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="payment_file",
        subject_id=str(row.get("payment_file_id")),
        payload={"authority_fingerprint": fp, "format_pack_id": pack_id},
    )
    return {"ok": True, "payment_file": row, "lines": lines, "phase": PHASE, **honesty_payload(company_code=company)}


def generate_payment_file(
    cur: Any,
    *,
    company_code: str,
    payment_file_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Generate payment file bytes from draft. Kill switch + entitlement enforced."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = payment_processing_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_payroll_payslip_payment_c5_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_payment_files WHERE company_code=%s AND payment_file_id=%s FOR UPDATE",
        (company, str(payment_file_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "payment_file_not_found"}
    pf = dict(row)
    if expected_row_version is not None and int(pf.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_payment_file_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": pf.get("row_version"),
            "phase": PHASE,
        }
    if str(pf.get("status")) == PF_GENERATED:
        return {"ok": True, "idempotent": True, "payment_file": pf, "phase": PHASE, **honesty_payload(company_code=company)}
    if str(pf.get("status")) != PF_DRAFT:
        return {"ok": False, "error": "payment_file_not_draft", "status": pf.get("status")}

    meta = pf.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    lines = list(meta.get("lines") or [])
    rendered = _render_format_pack(
        pack_id=str(pf.get("format_pack_id")),
        company_code=company,
        period_start=pf.get("period_start"),
        period_end=pf.get("period_end"),
        finalize_run_id=pf.get("finalize_run_id"),
        lines=lines,
        authority_fingerprint=str(pf.get("authority_fingerprint")),
    )
    if not rendered.get("ok"):
        return rendered

    cur.execute(
        """
        UPDATE payroll_payment_files
           SET status='generated',
               file_payload=%s,
               file_bytes_sha256=%s,
               content_fingerprint=%s,
               generated_by_phone=%s,
               generated_at=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND payment_file_id=%s AND status='draft' AND row_version=%s
         RETURNING *
        """,
        (
            rendered["file_payload"],
            rendered["file_bytes_sha256"],
            rendered["content_fingerprint"],
            _digits(actor_phone),
            str(reason).strip()[:500],
            company,
            str(payment_file_id),
            int(pf.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "generate_race_or_stale", "phase": PHASE}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="payment_file_generated",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="payment_file",
        subject_id=str(payment_file_id),
        payload={
            "content_fingerprint": out.get("content_fingerprint"),
            "authority_fingerprint": out.get("authority_fingerprint"),
            "format_pack_id": out.get("format_pack_id"),
        },
    )
    return {
        "ok": True,
        "payment_file": out,
        "format_pack": FORMAT_PACKS.get(str(out.get("format_pack_id"))),
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def transition_payment_file(
    cur: Any,
    *,
    company_code: str,
    payment_file_id: str,
    decision: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Acknowledge / fail / cancel. Acknowledge ≠ paid."""
    decision_n = str(decision or "").strip().lower()
    if decision_n not in {PF_ACKNOWLEDGED, PF_FAILED, PF_CANCELLED}:
        return {"ok": False, "error": "invalid_payment_file_decision", "allowed": [PF_ACKNOWLEDGED, PF_FAILED, PF_CANCELLED]}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_payroll_payslip_payment_c5_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_payment_files WHERE company_code=%s AND payment_file_id=%s FOR UPDATE",
        (company, str(payment_file_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "payment_file_not_found"}
    pf = dict(row)
    if expected_row_version is not None and int(pf.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_payment_file_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": pf.get("row_version"),
            "phase": PHASE,
        }
    status = str(pf.get("status"))
    if decision_n == PF_ACKNOWLEDGED and status != PF_GENERATED:
        return {"ok": False, "error": "acknowledge_requires_generated", "status": status}
    if decision_n == PF_FAILED and status not in {PF_DRAFT, PF_GENERATED}:
        return {"ok": False, "error": "invalid_fail_transition", "status": status}
    if decision_n == PF_CANCELLED and status in {PF_ACKNOWLEDGED}:
        return {"ok": False, "error": "cannot_cancel_acknowledged", "status": status}
    if status == decision_n:
        return {"ok": True, "idempotent": True, "payment_file": pf, "phase": PHASE, **honesty_payload(company_code=company)}

    fields = {
        PF_ACKNOWLEDGED: ("acknowledged_by_phone", "acknowledged_at"),
        PF_FAILED: ("failed_by_phone", "failed_at"),
        PF_CANCELLED: ("cancelled_by_phone", "cancelled_at"),
    }
    phone_col, at_col = fields[decision_n]
    cur.execute(
        f"""
        UPDATE payroll_payment_files
           SET status=%s,
               {phone_col}=%s,
               {at_col}=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND payment_file_id=%s AND row_version=%s
         RETURNING *
        """,
        (
            decision_n,
            _digits(actor_phone),
            str(reason).strip()[:500],
            company,
            str(payment_file_id),
            int(pf.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "transition_race_or_stale", "phase": PHASE}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action=f"payment_file_{decision_n}",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="payment_file",
        subject_id=str(payment_file_id),
        payload={
            "status": decision_n,
            "acknowledged_is_not_paid": True,
            "posts_payment": False,
        },
    )
    return {
        "ok": True,
        "payment_file": out,
        "acknowledged_means": "operational_ack_only" if decision_n == PF_ACKNOWLEDGED else None,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "WATHEFNI_PAYROLL_PAYMENT_KILL=on (immediate block)",
            "WATHEFNI_PAYROLL_PAYMENT_C5=off",
            "Clear WATHEFNI_PAYROLL_PAYMENT_COMPANIES",
            "disable_company_payment_processing(canary)",
            "Existing sealed payslips / payment-file rows remain; no silent money claim",
        ],
    }
