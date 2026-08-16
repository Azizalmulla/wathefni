#!/usr/bin/env python3
"""Wave 3 C4 — Offboarding + Clearance (synthetic; commercial module key: offboarding).

Owner-approved under WAVE3_EMPLOYEE_LIFECYCLE_CHARTER.
C3 RESIGNATION_TERMINATION_FULL_PASS ACCEPTED/frozen before this slice.

Case SM:
  not_started → in_progress → blocked | ready_to_close → completed
  (+ cancelled)

Clearance is a sub-workflow inside Offboarding (not a separate commercial module).

C4 does NOT: invent Asset Management product; treat revoke-requested as revoked;
equate completion with settlement/paid/access-revoked/exit-interview;
silently mark employment left; invent legal formulas; Assistant mutations;
unlock real non-synthetic termination.

Gates (fail-closed):
  1) WATHEFNI_OFFBOARDING_C4 must be on
  2) company in WATHEFNI_OFFBOARDING_COMPANIES (empty = nobody)
  3) company entitlement in offboarding_c4_company_settings
  4) WATHEFNI_OFFBOARDING_KILL blocks mutations when on
  5) WATHEFNI_REAL_TERMINATION_CANARY remains off (dark)
  6) synthetic markers required for subjects
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "offboarding_c4"
CONTRACT_VERSION = "offboarding_c4_v1"
PASS_STAMP = "OFFBOARDING_FULL_PASS"
COMMERCIAL_MODULE_KEY = "offboarding"
_ON = {"1", "true", "yes", "on"}

ST_NOT_STARTED = "not_started"
ST_IN_PROGRESS = "in_progress"
ST_BLOCKED = "blocked"
ST_READY = "ready_to_close"
ST_COMPLETED = "completed"
ST_CANCELLED = "cancelled"

CASE_STATUSES = (
    ST_NOT_STARTED,
    ST_IN_PROGRESS,
    ST_BLOCKED,
    ST_READY,
    ST_COMPLETED,
    ST_CANCELLED,
)

ITEM_PENDING = "pending"
ITEM_IN_PROGRESS = "in_progress"
ITEM_COMPLETED = "completed"
ITEM_REJECTED = "rejected"
ITEM_RETURNED = "returned"
ITEM_WAIVED = "waived"
ITEM_CANCELLED = "cancelled"

ITEM_STATUSES = (
    ITEM_PENDING,
    ITEM_IN_PROGRESS,
    ITEM_COMPLETED,
    ITEM_REJECTED,
    ITEM_RETURNED,
    ITEM_WAIVED,
    ITEM_CANCELLED,
)

ITEM_SATISFIED = {ITEM_COMPLETED, ITEM_WAIVED}
ITEM_OPEN = {ITEM_PENDING, ITEM_IN_PROGRESS, ITEM_REJECTED, ITEM_RETURNED}

OWNERS = ("employee", "manager", "hr", "it", "finance", "department", "custom")

ITEM_CLASSES = (
    "handover",
    "asset_return",
    "keys_cards",
    "it_access",
    "dept_clearance",
    "manager_clearance",
    "hr_docs",
    "custom",
)

# Setup-owned default template — company may replace via settings. Not one customer's checklist.
DEFAULT_TEMPLATE_ITEMS = [
    {
        "item_key": "handover",
        "item_class": "handover",
        "required": True,
        "owner_role": "manager",
        "title_en": "Knowledge / work handover",
        "title_ar": "تسليم العمل / المعرفة",
        "depends_on": [],
        "due_offset_days": 7,
    },
    {
        "item_key": "assets",
        "item_class": "asset_return",
        "required": True,
        "owner_role": "it",
        "title_en": "Company assets return",
        "title_ar": "إرجاع أصول الشركة",
        "depends_on": [],
        "due_offset_days": 7,
    },
    {
        "item_key": "keys_cards",
        "item_class": "keys_cards",
        "required": False,
        "owner_role": "hr",
        "title_en": "Keys / cards / equipment",
        "title_ar": "مفاتيح / بطاقات / معدات",
        "depends_on": [],
        "due_offset_days": 5,
    },
    {
        "item_key": "it_access",
        "item_class": "it_access",
        "required": True,
        "owner_role": "it",
        "title_en": "IT / access actions",
        "title_ar": "إجراءات تقنية المعلومات / الصلاحيات",
        "depends_on": ["assets"],
        "due_offset_days": 10,
    },
    {
        "item_key": "dept_clearance",
        "item_class": "dept_clearance",
        "required": True,
        "owner_role": "department",
        "title_en": "Departmental clearance",
        "title_ar": "إخلاء طرف القسم",
        "depends_on": ["handover"],
        "due_offset_days": 7,
    },
    {
        "item_key": "hr_docs",
        "item_class": "hr_docs",
        "required": True,
        "owner_role": "hr",
        "title_en": "HR documentation",
        "title_ar": "وثائق الموارد البشرية",
        "depends_on": [],
        "due_offset_days": 10,
    },
]

STATUS_LABELS = {
    "not_started": {"en": "Not started", "ar": "لم يبدأ"},
    "in_progress": {"en": "In progress", "ar": "قيد التنفيذ"},
    "blocked": {"en": "Blocked", "ar": "موقوف"},
    "ready_to_close": {"en": "Ready to close", "ar": "جاهز للإغلاق"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "pending": {"en": "Pending", "ar": "معلّق"},
    "completed_item": {"en": "Completed", "ar": "مكتمل"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "returned": {"en": "Returned", "ar": "مُعاد"},
    "waived": {"en": "Waived", "ar": "مُعفى"},
    "handover": {"en": "Handover", "ar": "تسليم"},
    "asset_return": {"en": "Asset return", "ar": "إرجاع أصل"},
    "it_access": {"en": "IT / access", "ar": "تقنية / صلاحيات"},
    "revoke_requested": {"en": "Revoke requested", "ar": "طُلب الإلغاء"},
    "revoke_acked": {"en": "Revoke acknowledged", "ar": "أُكِّد الإلغاء"},
    "manual_confirmed": {"en": "Manually confirmed", "ar": "تأكيد يدوي"},
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


def offboarding_c4_runtime_on() -> bool:
    return _env_on("WATHEFNI_OFFBOARDING_C4", "off")


def offboarding_kill_on() -> bool:
    return _env_on("WATHEFNI_OFFBOARDING_KILL", "off")


def real_termination_canary_on() -> bool:
    return _env_on("WATHEFNI_REAL_TERMINATION_CANARY", "off")


def idp_adapter_enabled() -> bool:
    return _env_on("WATHEFNI_OFFBOARDING_IDP_ADAPTER", "off")


def offboarding_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_OFFBOARDING_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def synthetic_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_OFFBOARDING_SYNTHETIC_MARKERS") or "W3C4,OB4,EX3,W3C3").strip()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "clearance_is_subworkflow": True,
        "assistant_mutations": False,
        "payroll_required": False,
        "identity_adapter_required": False,
        "asset_management_required": False,
        "settlement_finalized_implied": False,
        "payment_completed_implied": False,
        "access_revoked_implied": False,
        "exit_interview_implied": False,
        "employment_left_on_complete": False,
        "revoke_requested_is_not_revoked": True,
        "real_termination_canary": real_termination_canary_on(),
        "real_termination_dark": not real_termination_canary_on(),
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "steps": [
            "WATHEFNI_OFFBOARDING_C4=off",
            "Clear WATHEFNI_OFFBOARDING_COMPANIES",
            "WATHEFNI_OFFBOARDING_KILL=on (optional immediate block)",
            "WATHEFNI_REAL_TERMINATION_CANARY remains off",
            "disable_company_offboarding(canary)",
            "Offboarding/clearance history retained",
        ],
        "history_intact": True,
    }


def assert_real_termination_dark() -> dict[str, Any]:
    if real_termination_canary_on():
        return {
            "ok": False,
            "error": "real_termination_canary_must_remain_off_in_c4",
            "gate": "real_termination_canary",
            "phase": PHASE,
        }
    return {"ok": True, "real_termination_dark": True}


def assert_not_killed() -> dict[str, Any]:
    if offboarding_kill_on():
        return {
            "ok": False,
            "error": "offboarding_kill_switch_on",
            "gate": "offboarding_kill",
            "phase": PHASE,
        }
    return {"ok": True}


def assert_synthetic_employee_key(employee_key: str) -> dict[str, Any]:
    key = str(employee_key or "")
    markers = synthetic_markers()
    if any(m and m in key for m in markers):
        return {"ok": True, "synthetic": True, "markers": list(markers)}
    return {
        "ok": False,
        "error": "non_synthetic_employee_blocked",
        "gate": "synthetic_only",
        "markers": list(markers),
        "phase": PHASE,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not offboarding_c4_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "offboarding_c4_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = offboarding_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "offboarding_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Offboarding allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "offboarding_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_offboarding_c4_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_c4_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          template jsonb NOT NULL DEFAULT '[]'::jsonb,
          waiver_roles jsonb NOT NULL DEFAULT '["hr"]'::jsonb,
          require_settlement_ack boolean NOT NULL DEFAULT false,
          idp_revoke_policy text NOT NULL DEFAULT 'manual_ok',
          asset_mode text NOT NULL DEFAULT 'clearance_reference',
          sla_escalation_enabled boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT offboarding_c4_idp_policy_chk
            CHECK (idp_revoke_policy IN ('manual_ok','adapter_required','adapter_optional')),
          CONSTRAINT offboarding_c4_asset_mode_chk
            CHECK (asset_mode IN ('clearance_reference','external_asset_authority'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_cases (
          case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          exit_intent_case_id uuid NOT NULL,
          status text NOT NULL DEFAULT 'not_started',
          row_version int NOT NULL DEFAULT 1,
          blocked_reason text,
          exit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          settlement_ack_status text NOT NULL DEFAULT 'not_required',
          access_revoked boolean NOT NULL DEFAULT false,
          settlement_finalized boolean NOT NULL DEFAULT false,
          payment_completed boolean NOT NULL DEFAULT false,
          exit_interview_completed boolean NOT NULL DEFAULT false,
          employment_left boolean NOT NULL DEFAULT false,
          created_by_phone text NOT NULL,
          started_at timestamptz,
          ready_at timestamptz,
          completed_at timestamptz,
          cancelled_at timestamptz,
          cancelled_by_phone text,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT offboarding_cases_status_chk
            CHECK (status IN (
              'not_started','in_progress','blocked','ready_to_close','completed','cancelled'
            )),
          CONSTRAINT offboarding_cases_exit_uq UNIQUE (company_code, exit_intent_case_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_clearance_items (
          item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          case_id uuid NOT NULL,
          item_key text NOT NULL,
          item_class text NOT NULL,
          required boolean NOT NULL DEFAULT true,
          owner_role text NOT NULL,
          owner_actor_phone text,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          status text NOT NULL DEFAULT 'pending',
          row_version int NOT NULL DEFAULT 1,
          depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
          due_on date,
          evidence_ref text,
          notes text,
          waiver_reason text,
          waived_by_phone text,
          waived_at timestamptz,
          completed_by_phone text,
          completed_at timestamptz,
          rejected_by_phone text,
          rejected_at timestamptz,
          returned_by_phone text,
          returned_at timestamptz,
          hr_task_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT offboarding_items_class_chk
            CHECK (item_class IN (
              'handover','asset_return','keys_cards','it_access','dept_clearance',
              'manager_clearance','hr_docs','custom'
            )),
          CONSTRAINT offboarding_items_owner_chk
            CHECK (owner_role IN (
              'employee','manager','hr','it','finance','department','custom'
            )),
          CONSTRAINT offboarding_items_status_chk
            CHECK (status IN (
              'pending','in_progress','completed','rejected','returned','waived','cancelled'
            )),
          UNIQUE (case_id, item_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_asset_refs (
          asset_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          case_id uuid NOT NULL,
          item_id uuid,
          external_asset_id text,
          label text NOT NULL,
          status text NOT NULL DEFAULT 'pending_return',
          notes text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT offboarding_asset_refs_status_chk
            CHECK (status IN ('pending_return','returned','waived','missing'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_access_actions (
          action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          case_id uuid NOT NULL,
          item_id uuid,
          channel text NOT NULL,
          status text NOT NULL DEFAULT 'not_started',
          requested_by_phone text,
          requested_at timestamptz,
          acked_by_phone text,
          acked_at timestamptz,
          adapter_ref text,
          notes text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT offboarding_access_channel_chk
            CHECK (channel IN ('manual','idp_adapter')),
          CONSTRAINT offboarding_access_status_chk
            CHECK (status IN (
              'not_started','revoke_requested','revoke_acked','manual_confirmed','failed','cancelled'
            ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_c4_audit (
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
    reason: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO offboarding_c4_audit (
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
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        "SELECT * FROM offboarding_c4_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_offboarding(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    template: list[dict[str, Any]] | None = None,
    waiver_roles: list[str] | None = None,
    require_settlement_ack: bool = False,
    idp_revoke_policy: str = "manual_ok",
    asset_mode: str = "clearance_reference",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    dark = assert_real_termination_dark()
    if not dark.get("ok"):
        return dark
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if idp_revoke_policy not in ("manual_ok", "adapter_required", "adapter_optional"):
        return {"ok": False, "error": "invalid_idp_revoke_policy"}
    company = company_code_norm(company_code)
    ensure_offboarding_c4_schema(cur)
    tpl = template if template is not None else DEFAULT_TEMPLATE_ITEMS
    roles = waiver_roles if waiver_roles is not None else ["hr"]
    cur.execute(
        """
        INSERT INTO offboarding_c4_company_settings (
          company_code, enabled, template, waiver_roles, require_settlement_ack,
          idp_revoke_policy, asset_mode, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          template=EXCLUDED.template,
          waiver_roles=EXCLUDED.waiver_roles,
          require_settlement_ack=EXCLUDED.require_settlement_ack,
          idp_revoke_policy=EXCLUDED.idp_revoke_policy,
          asset_mode=EXCLUDED.asset_mode,
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
            json.dumps(tpl, default=str),
            json.dumps(roles),
            bool(require_settlement_ack),
            idp_revoke_policy,
            asset_mode,
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_offboarding",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"require_settlement_ack": require_settlement_ack, "idp_revoke_policy": idp_revoke_policy},
    )
    return {"ok": True, "company": row, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_offboarding(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        """
        UPDATE offboarding_c4_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
         WHERE company_code=%s
         RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    _audit(
        cur,
        company_code=company,
        action="disable_offboarding",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
    )
    return {
        "ok": True,
        "company": dict(row) if row else None,
        "history_preserved": True,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def module_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    dark = assert_real_termination_dark()
    if not dark.get("ok"):
        return dark
    killed = assert_not_killed()
    if not killed.get("ok"):
        return killed
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "offboarding_not_enabled",
            "gate": "company_entitlement",
            "phase": PHASE,
        }
    return {
        "ok": True,
        "enabled": True,
        "settings": settings,
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


def _decorate_case(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label_en"] = status_label(out.get("status"), lang="en")
    out["status_label_ar"] = status_label(out.get("status"), lang="ar")
    out["labels"] = {
        "status_en": out["status_label_en"],
        "status_ar": out["status_label_ar"],
    }
    # Honesty flags always explicit on case reads
    out["implies"] = {
        "settlement_finalized": bool(out.get("settlement_finalized")),
        "payment_completed": bool(out.get("payment_completed")),
        "access_revoked": bool(out.get("access_revoked")),
        "exit_interview_completed": bool(out.get("exit_interview_completed")),
        "employment_left": bool(out.get("employment_left")),
    }
    return out


def _decorate_item(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label_en"] = status_label(out.get("status"), lang="en")
    out["status_label_ar"] = status_label(out.get("status"), lang="ar")
    out["item_class_label_en"] = status_label(out.get("item_class"), lang="en")
    out["item_class_label_ar"] = status_label(out.get("item_class"), lang="ar")
    return out


def get_case(cur: Any, *, company_code: str, case_id: str) -> dict[str, Any] | None:
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        "SELECT * FROM offboarding_cases WHERE company_code=%s AND case_id=%s",
        (company_code_norm(company_code), str(case_id)),
    )
    row = cur.fetchone()
    return _decorate_case(dict(row)) if row else None


def get_case_by_exit_intent(
    cur: Any, *, company_code: str, exit_intent_case_id: str
) -> dict[str, Any] | None:
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        """
        SELECT * FROM offboarding_cases
         WHERE company_code=%s AND exit_intent_case_id=%s
        """,
        (company_code_norm(company_code), str(exit_intent_case_id)),
    )
    row = cur.fetchone()
    return _decorate_case(dict(row)) if row else None


def list_items(cur: Any, *, case_id: str) -> list[dict[str, Any]]:
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        "SELECT * FROM offboarding_clearance_items WHERE case_id=%s ORDER BY created_at",
        (str(case_id),),
    )
    return [_decorate_item(dict(r)) for r in (cur.fetchall() or [])]


def get_item(cur: Any, *, company_code: str, item_id: str) -> dict[str, Any] | None:
    ensure_offboarding_c4_schema(cur)
    cur.execute(
        "SELECT * FROM offboarding_clearance_items WHERE company_code=%s AND item_id=%s",
        (company_code_norm(company_code), str(item_id)),
    )
    row = cur.fetchone()
    return _decorate_item(dict(row)) if row else None


def _load_exit_intent(cur: Any, *, company_code: str, exit_intent_case_id: str) -> dict[str, Any] | None:
    cur.execute("SELECT to_regclass('public.exit_intent_cases') AS t")
    if not dict(cur.fetchone()).get("t"):
        return None
    cur.execute(
        """
        SELECT * FROM exit_intent_cases
         WHERE company_code=%s AND case_id=%s
        """,
        (company_code_norm(company_code), str(exit_intent_case_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _best_effort_hr_task(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    item: dict[str, Any],
) -> str | None:
    """Reuse Phase A hr_tasks when table exists — do not fork inbox SoT."""
    sp = f"ob4_task_{uuid.uuid4().hex[:10]}"
    try:
        cur.execute(f"SAVEPOINT {sp}")
        cur.execute("SELECT to_regclass('public.hr_tasks') AS t")
        if not dict(cur.fetchone()).get("t"):
            cur.execute(f"RELEASE SAVEPOINT {sp}")
            return None
        task_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO hr_tasks (
              task_id, company_code, employee_key, task_type, status, title, metadata, created_at
            ) VALUES (%s,%s,%s,'clearance_item_pending','open',%s,%s::jsonb,now())
            """,
            (
                task_id,
                company,
                employee_key,
                str(item.get("title_en") or item.get("item_key")),
                json.dumps(
                    {
                        "sot": PHASE,
                        "item_id": str(item.get("item_id")),
                        "item_key": item.get("item_key"),
                        "owner_role": item.get("owner_role"),
                    },
                    default=str,
                ),
            ),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return task_id
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            pass
        return None


def start_offboarding_from_exit_intent(
    cur: Any,
    *,
    company_code: str,
    exit_intent_case_id: str,
    actor_phone: str,
    reason: str = "start offboarding from exit intent",
) -> dict[str, Any]:
    """One canonical offboarding case per exit intent — duplicate handoff is idempotent."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    company = company_code_norm(company_code)

    existing = get_case_by_exit_intent(
        cur, company_code=company, exit_intent_case_id=exit_intent_case_id
    )
    if existing:
        return {
            "ok": True,
            "case": existing,
            "duplicate_handoff": True,
            "created": False,
            "message": "Duplicate handoff did not create a second case.",
        }

    exit_case = _load_exit_intent(cur, company_code=company, exit_intent_case_id=exit_intent_case_id)
    if not exit_case:
        return {"ok": False, "error": "exit_intent_case_not_found"}
    if str(exit_case.get("status")) != "ready_for_offboarding":
        return {
            "ok": False,
            "error": "exit_intent_not_ready",
            "status": exit_case.get("status"),
            "message": "Offboarding starts only from ready_for_offboarding exit intent.",
        }
    employee_key = str(exit_case.get("employee_key"))
    synth = assert_synthetic_employee_key(employee_key)
    if not synth.get("ok"):
        return synth

    settlement_ack = "required" if settings.get("require_settlement_ack") else "not_required"
    cur.execute(
        """
        INSERT INTO offboarding_cases (
          company_code, employee_key, exit_intent_case_id, status, exit_snapshot,
          settlement_ack_status, created_by_phone, started_at
        ) VALUES (%s,%s,%s,'not_started',%s::jsonb,%s,%s,now())
        RETURNING *
        """,
        (
            company,
            employee_key,
            exit_intent_case_id,
            json.dumps(
                {
                    "exit_type": exit_case.get("exit_type"),
                    "notice_starts_on": str(exit_case.get("notice_starts_on") or ""),
                    "notice_ends_on": str(exit_case.get("notice_ends_on") or ""),
                    "last_working_day": str(exit_case.get("effective_last_working_day") or ""),
                    "exit_intent_status": exit_case.get("status"),
                },
                default=str,
            ),
            settlement_ack,
            _digits(actor_phone),
        ),
    )
    case = dict(cur.fetchone())
    case_id = str(case["case_id"])

    template = settings.get("template") or DEFAULT_TEMPLATE_ITEMS
    if isinstance(template, str):
        template = json.loads(template)
    for tpl in template:
        item_key = str(tpl.get("item_key") or "").strip()
        if not item_key:
            continue
        item_class = str(tpl.get("item_class") or "custom")
        if item_class not in ITEM_CLASSES:
            item_class = "custom"
        owner_role = str(tpl.get("owner_role") or "hr")
        if owner_role not in OWNERS:
            owner_role = "custom"
        due_offset = int(tpl.get("due_offset_days") or 7)
        due_on = date.today() + timedelta(days=due_offset)
        depends_on = tpl.get("depends_on") or []
        cur.execute(
            """
            INSERT INTO offboarding_clearance_items (
              company_code, case_id, item_key, item_class, required, owner_role,
              title_en, title_ar, status, depends_on, due_on
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s::jsonb,%s)
            RETURNING *
            """,
            (
                company,
                case_id,
                item_key,
                item_class,
                bool(tpl.get("required", True)),
                owner_role,
                str(tpl.get("title_en") or item_key),
                str(tpl.get("title_ar") or item_key),
                json.dumps(depends_on, default=str),
                due_on,
            ),
        )
        item = dict(cur.fetchone())
        task_id = _best_effort_hr_task(cur, company=company, employee_key=employee_key, item=item)
        if task_id:
            cur.execute(
                "UPDATE offboarding_clearance_items SET hr_task_id=%s WHERE item_id=%s",
                (task_id, item["item_id"]),
            )

    # Move to in_progress immediately after materializing items
    cur.execute(
        """
        UPDATE offboarding_cases
           SET status='in_progress', row_version=row_version+1, updated_at=now()
         WHERE case_id=%s
        RETURNING *
        """,
        (case_id,),
    )
    case = dict(cur.fetchone())
    _reevaluate_case_status(cur, company_code=company, case_id=case_id)
    case = get_case(cur, company_code=company, case_id=case_id) or _decorate_case(case)

    _audit(
        cur,
        company_code=company,
        action="offboarding_started",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="offboarding_case",
        subject_id=case_id,
        payload={"exit_intent_case_id": str(exit_intent_case_id)},
    )
    return {
        "ok": True,
        "case": case,
        "items": list_items(cur, case_id=case_id),
        "duplicate_handoff": False,
        "created": True,
        **honesty_payload(company_code=company),
    }


def _deps_satisfied(cur: Any, *, case_id: str, depends_on: list[str]) -> bool:
    if not depends_on:
        return True
    items = {i["item_key"]: i for i in list_items(cur, case_id=case_id)}
    for key in depends_on:
        dep = items.get(key)
        if not dep or dep.get("status") not in ITEM_SATISFIED:
            return False
    return True


def _item_dependency_blocked(cur: Any, item: dict[str, Any]) -> bool:
    deps = item.get("depends_on") or []
    if isinstance(deps, str):
        deps = json.loads(deps)
    return not _deps_satisfied(cur, case_id=str(item["case_id"]), depends_on=list(deps))


def required_clearance_satisfied(cur: Any, *, case_id: str) -> dict[str, Any]:
    items = list_items(cur, case_id=case_id)
    required = [i for i in items if i.get("required")]
    unsatisfied = [i for i in required if i.get("status") not in ITEM_SATISFIED]
    optional_open = [i for i in items if not i.get("required") and i.get("status") in ITEM_OPEN]
    return {
        "ok": len(unsatisfied) == 0,
        "required_total": len(required),
        "required_satisfied": len(required) - len(unsatisfied),
        "unsatisfied": [
            {"item_key": i.get("item_key"), "status": i.get("status")} for i in unsatisfied
        ],
        "optional_open_count": len(optional_open),
    }


def _reevaluate_case_status(cur: Any, *, company_code: str, case_id: str) -> dict[str, Any]:
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("status") in (ST_COMPLETED, ST_CANCELLED):
        return {"ok": True, "case": case, "unchanged": True}

    items = list_items(cur, case_id=case_id)
    # Blocked if any required item is rejected/returned OR dependency deadlocks required open items
    blocked_reasons: list[str] = []
    for i in items:
        if i.get("required") and i.get("status") in (ITEM_REJECTED, ITEM_RETURNED):
            blocked_reasons.append(f"{i.get('item_key')}:{i.get('status')}")
        if i.get("required") and i.get("status") in (ITEM_PENDING, ITEM_IN_PROGRESS) and _item_dependency_blocked(cur, i):
            # dependency not yet satisfied is normal in_progress, not blocked unless cycle — skip
            pass

    sat = required_clearance_satisfied(cur, case_id=case_id)
    new_status = ST_IN_PROGRESS
    if blocked_reasons:
        new_status = ST_BLOCKED
    elif sat.get("ok"):
        new_status = ST_READY
    elif any(i.get("status") in ITEM_OPEN or i.get("status") == ITEM_IN_PROGRESS for i in items):
        new_status = ST_IN_PROGRESS

    # Never cosmetic: ready only when required satisfied
    if new_status == ST_READY and not sat.get("ok"):
        new_status = ST_BLOCKED if blocked_reasons else ST_IN_PROGRESS

    extra = ""
    params: list[Any] = [new_status]
    if new_status == ST_READY:
        extra = ", ready_at=COALESCE(ready_at, now()), blocked_reason=NULL"
    elif new_status == ST_BLOCKED:
        extra = ", blocked_reason=%s"
        params.append(",".join(blocked_reasons)[:500])
    else:
        extra = ", blocked_reason=NULL"
    params.extend([company_code_norm(company_code), str(case_id)])
    cur.execute(
        f"""
        UPDATE offboarding_cases
           SET status=%s,
               row_version = row_version + 1,
               updated_at=now()
               {extra}
         WHERE company_code=%s AND case_id=%s
           AND status NOT IN ('completed','cancelled')
        RETURNING *
        """,
        tuple(params),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "case": _decorate_case(dict(row)) if row else case,
        "required_clearance": sat,
    }


def _actor_may_act_on_item(
    *,
    item: dict[str, Any],
    actor_role: str,
    actor_phone: str,
) -> bool:
    role = str(actor_role or "").strip().lower()
    owner = str(item.get("owner_role") or "").strip().lower()
    if role == "hr":
        return True  # HR can complete/oversee
    if role == owner:
        return True
    if owner == "custom" and _digits(item.get("owner_actor_phone")) == _digits(actor_phone):
        return True
    return False


def complete_clearance_item(
    cur: Any,
    *,
    company_code: str,
    item_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
    evidence_ref: str | None = None,
    notes: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    item = get_item(cur, company_code=company_code, item_id=item_id)
    if not item:
        return {"ok": False, "error": "item_not_found"}
    if expected_version is not None and int(item.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version", "row_version": item.get("row_version")}
    if not _actor_may_act_on_item(item=item, actor_role=actor_role, actor_phone=actor_phone):
        return {"ok": False, "error": "rbac_owner_scope_denied", "owner_role": item.get("owner_role")}
    if _item_dependency_blocked(cur, item):
        return {"ok": False, "error": "dependency_blocked", "depends_on": item.get("depends_on")}
    if item.get("status") in ITEM_SATISFIED:
        return {"ok": False, "error": "item_already_satisfied", "status": item.get("status")}

    cur.execute(
        """
        UPDATE offboarding_clearance_items
           SET status='completed',
               evidence_ref=COALESCE(%s, evidence_ref),
               notes=COALESCE(%s, notes),
               completed_by_phone=%s,
               completed_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            evidence_ref,
            notes,
            _digits(actor_phone),
            company_code_norm(company_code),
            item_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="clearance_item_completed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="clearance_item",
        subject_id=str(item_id),
        payload={"item_key": d.get("item_key"), "actor_role": actor_role},
    )
    case_state = _reevaluate_case_status(cur, company_code=company_code, case_id=str(d["case_id"]))
    return {"ok": True, "item": _decorate_item(d), "case": case_state.get("case")}


def reject_clearance_item(
    cur: Any,
    *,
    company_code: str,
    item_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    item = get_item(cur, company_code=company_code, item_id=item_id)
    if not item:
        return {"ok": False, "error": "item_not_found"}
    if not _actor_may_act_on_item(item=item, actor_role=actor_role, actor_phone=actor_phone):
        return {"ok": False, "error": "rbac_owner_scope_denied"}
    if expected_version is not None and int(item.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version"}
    cur.execute(
        """
        UPDATE offboarding_clearance_items
           SET status='rejected',
               notes=%s,
               rejected_by_phone=%s,
               rejected_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            str(reason).strip()[:1000],
            _digits(actor_phone),
            company_code_norm(company_code),
            item_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="clearance_item_rejected",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="clearance_item",
        subject_id=str(item_id),
    )
    case_state = _reevaluate_case_status(cur, company_code=company_code, case_id=str(d["case_id"]))
    return {"ok": True, "item": _decorate_item(d), "case": case_state.get("case")}


def return_clearance_item(
    cur: Any,
    *,
    company_code: str,
    item_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    item = get_item(cur, company_code=company_code, item_id=item_id)
    if not item:
        return {"ok": False, "error": "item_not_found"}
    if not _actor_may_act_on_item(item=item, actor_role=actor_role, actor_phone=actor_phone):
        return {"ok": False, "error": "rbac_owner_scope_denied"}
    cur.execute(
        """
        UPDATE offboarding_clearance_items
           SET status='returned',
               notes=%s,
               returned_by_phone=%s,
               returned_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            str(reason).strip()[:1000],
            _digits(actor_phone),
            company_code_norm(company_code),
            item_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="clearance_item_returned",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="clearance_item",
        subject_id=str(item_id),
    )
    case_state = _reevaluate_case_status(cur, company_code=company_code, case_id=str(d["case_id"]))
    return {"ok": True, "item": _decorate_item(d), "case": case_state.get("case")}


def waive_clearance_item(
    cur: Any,
    *,
    company_code: str,
    item_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    waiver_roles = settings.get("waiver_roles") or ["hr"]
    if isinstance(waiver_roles, str):
        waiver_roles = json.loads(waiver_roles)
    role = str(actor_role or "").strip().lower()
    if role not in {str(r).lower() for r in waiver_roles}:
        return {
            "ok": False,
            "error": "unauthorized_waiver",
            "allowed_roles": list(waiver_roles),
            "actor_role": role,
        }
    item = get_item(cur, company_code=company_code, item_id=item_id)
    if not item:
        return {"ok": False, "error": "item_not_found"}
    if expected_version is not None and int(item.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version"}
    cur.execute(
        """
        UPDATE offboarding_clearance_items
           SET status='waived',
               waiver_reason=%s,
               waived_by_phone=%s,
               waived_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND item_id=%s
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            str(reason).strip()[:1000],
            _digits(actor_phone),
            company_code_norm(company_code),
            item_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="clearance_item_waived",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="clearance_item",
        subject_id=str(item_id),
        payload={"actor_role": role},
    )
    case_state = _reevaluate_case_status(cur, company_code=company_code, case_id=str(d["case_id"]))
    return {"ok": True, "item": _decorate_item(d), "case": case_state.get("case")}


def add_asset_clearance_ref(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    label: str,
    actor_phone: str,
    item_id: str | None = None,
    external_asset_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Clearance reference only — not a full Asset Management product."""
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not str(label or "").strip():
        return {"ok": False, "error": "label_required"}
    cur.execute(
        """
        INSERT INTO offboarding_asset_refs (
          company_code, case_id, item_id, external_asset_id, label, status, notes
        ) VALUES (%s,%s,%s,%s,%s,'pending_return',%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            item_id,
            external_asset_id,
            str(label).strip()[:200],
            notes,
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="asset_clearance_ref_added",
        actor_phone=actor_phone,
        subject_type="asset_ref",
        subject_id=str(row["asset_ref_id"]),
        payload={"mode": enabled["settings"].get("asset_mode"), "not_full_am_product": True},
    )
    return {"ok": True, "asset_ref": row, "full_asset_management": False}


def mark_asset_ref_returned(
    cur: Any,
    *,
    company_code: str,
    asset_ref_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    cur.execute(
        """
        UPDATE offboarding_asset_refs
           SET status='returned', notes=%s, updated_at=now()
         WHERE company_code=%s AND asset_ref_id=%s
        RETURNING *
        """,
        (str(reason).strip()[:500], company_code_norm(company_code), asset_ref_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "asset_ref_not_found"}
    _audit(
        cur,
        company_code=company_code,
        action="asset_ref_returned",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="asset_ref",
        subject_id=str(asset_ref_id),
    )
    return {"ok": True, "asset_ref": dict(row)}


def confirm_it_access_manual(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    item_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Manual IT confirmation path when identity adapter is absent."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if settings.get("idp_revoke_policy") == "adapter_required" and not idp_adapter_enabled():
        return {"ok": False, "error": "idp_adapter_required"}
    cur.execute(
        """
        INSERT INTO offboarding_access_actions (
          company_code, case_id, item_id, channel, status,
          requested_by_phone, requested_at, acked_by_phone, acked_at, notes
        ) VALUES (%s,%s,%s,'manual','manual_confirmed',%s,now(),%s,now(),%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            item_id,
            _digits(actor_phone),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    action = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="it_access_manual_confirmed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="access_action",
        subject_id=str(action["action_id"]),
        payload={"access_revoked_case_flag_unchanged": True},
    )
    # Honesty: manual confirm of clearance IT item ≠ case.access_revoked unless explicitly acked revoke
    return {
        "ok": True,
        "access_action": action,
        "case_access_revoked": False,
        "revoke_requested_is_not_revoked": True,
    }


def request_idp_revoke(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    item_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not idp_adapter_enabled():
        return {"ok": False, "error": "idp_adapter_disabled"}
    cur.execute(
        """
        INSERT INTO offboarding_access_actions (
          company_code, case_id, item_id, channel, status,
          requested_by_phone, requested_at, adapter_ref, notes
        ) VALUES (%s,%s,%s,'idp_adapter','revoke_requested',%s,now(),%s,%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            item_id,
            _digits(actor_phone),
            f"idp-req-{uuid.uuid4().hex[:12]}",
            str(reason).strip()[:500],
        ),
    )
    action = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="idp_revoke_requested",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="access_action",
        subject_id=str(action["action_id"]),
    )
    # Never set case.access_revoked on request alone
    return {
        "ok": True,
        "access_action": action,
        "case_access_revoked": False,
        "revoke_requested_is_not_revoked": True,
    }


def ack_idp_revoke(
    cur: Any,
    *,
    company_code: str,
    action_id: str,
    actor_phone: str,
    reason: str,
    mark_case_access_revoked: bool = True,
) -> dict[str, Any]:
    """Authoritative acknowledgement — only then may access_revoked become true."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not idp_adapter_enabled():
        return {"ok": False, "error": "idp_adapter_disabled"}
    cur.execute(
        """
        UPDATE offboarding_access_actions
           SET status='revoke_acked',
               acked_by_phone=%s,
               acked_at=now(),
               notes=%s,
               updated_at=now()
         WHERE company_code=%s AND action_id=%s AND status='revoke_requested'
        RETURNING *
        """,
        (
            _digits(actor_phone),
            str(reason).strip()[:500],
            company_code_norm(company_code),
            action_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "access_action_not_found_or_not_requested"}
    action = dict(row)
    case_revoked = False
    if mark_case_access_revoked:
        cur.execute(
            """
            UPDATE offboarding_cases
               SET access_revoked=true, row_version=row_version+1, updated_at=now()
             WHERE company_code=%s AND case_id=%s
            RETURNING access_revoked
            """,
            (company_code_norm(company_code), action["case_id"]),
        )
        case_revoked = bool((cur.fetchone() or {}).get("access_revoked"))
    _audit(
        cur,
        company_code=company_code,
        action="idp_revoke_acked",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="access_action",
        subject_id=str(action_id),
        payload={"case_access_revoked": case_revoked},
    )
    return {
        "ok": True,
        "access_action": action,
        "case_access_revoked": case_revoked,
        "revoke_requested_is_not_revoked": False if case_revoked else True,
    }


def complete_offboarding_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Complete only from ready_to_close — derived from required clearance, not cosmetic."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if expected_version is not None and int(case.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version"}
    if case.get("status") == ST_BLOCKED:
        return {"ok": False, "error": "blocked_case_cannot_complete", "status": ST_BLOCKED}
    if case.get("status") != ST_READY:
        # Re-evaluate once in case items just satisfied
        _reevaluate_case_status(cur, company_code=company_code, case_id=case_id)
        case = get_case(cur, company_code=company_code, case_id=case_id) or case
    if case.get("status") != ST_READY:
        return {
            "ok": False,
            "error": "not_ready_to_close",
            "status": case.get("status"),
            "required_clearance": required_clearance_satisfied(cur, case_id=case_id),
        }
    sat = required_clearance_satisfied(cur, case_id=case_id)
    if not sat.get("ok"):
        return {"ok": False, "error": "required_clearance_unsatisfied", "required_clearance": sat}

    cur.execute(
        """
        UPDATE offboarding_cases
           SET status='completed',
               completed_at=now(),
               decision_note=%s,
               row_version=row_version+1,
               updated_at=now(),
               -- Honesty: completion does not imply these truths
               settlement_finalized=false,
               payment_completed=false,
               exit_interview_completed=false,
               employment_left=false
         WHERE company_code=%s AND case_id=%s AND status='ready_to_close'
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            str(reason).strip()[:500],
            company_code_norm(company_code),
            case_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_or_not_ready"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="offboarding_completed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="offboarding_case",
        subject_id=str(case_id),
        payload={
            "employment_left": False,
            "settlement_finalized": False,
            "payment_completed": False,
            "access_revoked": d.get("access_revoked"),
        },
    )
    return {
        "ok": True,
        "case": _decorate_case(d),
        "employment_left": False,
        "settlement_finalized": False,
        "payment_completed": False,
        "exit_interview_completed": False,
        **honesty_payload(company_code=company_code),
    }


def cancel_offboarding_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    cur.execute(
        """
        UPDATE offboarding_cases
           SET status='cancelled',
               cancelled_at=now(),
               cancelled_by_phone=%s,
               decision_note=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND case_id=%s
           AND status NOT IN ('completed','cancelled')
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            _digits(actor_phone),
            str(reason).strip()[:500],
            company_code_norm(company_code),
            case_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_or_terminal"}
    _audit(
        cur,
        company_code=company_code,
        action="offboarding_cancelled",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="offboarding_case",
        subject_id=str(case_id),
    )
    return {"ok": True, "case": _decorate_case(dict(row))}


def attempt_force_ready_to_close(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
) -> dict[str, Any]:
    """Honesty prove — cosmetic ready toggle is refused when required unsatisfied."""
    sat = required_clearance_satisfied(cur, case_id=case_id)
    if not sat.get("ok"):
        return {
            "ok": False,
            "error": "cannot_cosmetic_ready_to_close",
            "required_clearance": sat,
        }
    return _reevaluate_case_status(cur, company_code=company_code, case_id=case_id)
