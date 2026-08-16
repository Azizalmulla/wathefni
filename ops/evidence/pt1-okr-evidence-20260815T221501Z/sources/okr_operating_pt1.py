#!/usr/bin/env python3
"""PT1 overlay — OKR operating depth on frozen Performance C1.

Adds first-class OKR cycles, alignment tree/history, visibility, and an
update thread. Does not replace C1 tables or compute_progress / objective_rollup.

OKR cycle ≠ C2 review cycle.
Alignment does not inherit scores.
Check-in / update ≠ progress authority.
Optional confidence ≠ progress.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Any

import performance_goals_c1 as c1

PHASE = "okr_operating_pt1"
CONTRACT_VERSION = "okr_operating_pt1_v1"
PASS_STAMP = "PT1_OKR_EVIDENCE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"

CYCLE_STATUSES = ("draft", "active", "closed")
VISIBILITIES = ("owner_manager", "org_unit", "company")
CONFIDENCE = ("high", "medium", "low")
UPDATE_SUBJECTS = ("objective", "key_result")
_ON = {"1", "true", "yes", "on"}

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "active": {"en": "Active", "ar": "نشط"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "okr_cycle": {"en": "OKR cycle", "ar": "دورة النتائج الرئيسية"},
    "review_cycle": {"en": "Review cycle", "ar": "دورة المراجعة"},
    "confidence": {"en": "Confidence", "ar": "الثقة"},
    "health": {"en": "Health", "ar": "الصحة"},
    "high": {"en": "High", "ar": "مرتفع"},
    "medium": {"en": "Medium", "ar": "متوسط"},
    "low": {"en": "Low", "ar": "منخفض"},
    "at_risk": {"en": "At risk", "ar": "معرّض للخطر"},
    "owner_manager": {"en": "Owner and manager", "ar": "المالك والمدير"},
    "org_unit": {"en": "Organization unit", "ar": "الوحدة التنظيمية"},
    "company": {"en": "Company", "ar": "الشركة"},
    "orphan": {"en": "Unaligned", "ar": "غير محاذٍ"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return c1.company_code_norm(company_code)


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "c1_remains_okr_sot": True,
        "okr_cycle_is_not_review_cycle": True,
        "alignment_does_not_inherit_score": True,
        "check_in_is_not_progress_authority": True,
        "confidence_is_not_progress": True,
        "no_second_goals_table": True,
        "no_frontend_progress_truth": True,
        "okr_not_stored_as_goal_kind": True,
        "trajectory_labels_not_computed": True,
        "assistant_talent_tools": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def _row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def _as_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def ensure_okr_operating_pt1_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_performance_goals_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS okr_operating_pt1_company_settings (
          company_code text PRIMARY KEY,
          confidence_enabled boolean NOT NULL DEFAULT false,
          default_visibility text NOT NULL DEFAULT 'owner_manager',
          company_objectives_broadly_visible boolean NOT NULL DEFAULT true,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT okr_pt1_vis_chk CHECK (default_visibility IN (
            'owner_manager','org_unit','company'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_okr_cycles (
          cycle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          period_start date NOT NULL,
          period_end date NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          scope text NOT NULL DEFAULT 'company',
          org_unit_id text,
          visibility_policy text NOT NULL DEFAULT 'owner_manager',
          scoring_policy_snapshot jsonb NOT NULL DEFAULT '{"rollup":"okr_rollup_v1","inherits_alignment_score":false}'::jsonb,
          version int NOT NULL DEFAULT 1,
          row_version int NOT NULL DEFAULT 1,
          closed_at timestamptz,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_okr_cycle_status_chk CHECK (status IN ('draft','active','closed')),
          CONSTRAINT perf_okr_cycle_scope_chk CHECK (scope IN (
            'individual','team','department','company'
          )),
          CONSTRAINT perf_okr_cycle_vis_chk CHECK (visibility_policy IN (
            'owner_manager','org_unit','company'
          )),
          CONSTRAINT perf_okr_cycle_not_review_chk CHECK (
            (metadata->>'review_cycle_id') IS NULL
          )
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_okr_cycle_objectives (
          membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES perf_okr_cycles(cycle_id),
          objective_id uuid NOT NULL,
          attached_at timestamptz NOT NULL DEFAULT now(),
          attached_by_phone text,
          UNIQUE (cycle_id, objective_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_okr_visibility (
          visibility_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          objective_id uuid NOT NULL,
          visibility text NOT NULL,
          version int NOT NULL DEFAULT 1,
          superseded_by uuid,
          actor_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_okr_obj_vis_chk CHECK (visibility IN (
            'owner_manager','org_unit','company'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_okr_alignment_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          link_id uuid,
          action text NOT NULL,
          from_type text NOT NULL,
          from_id uuid NOT NULL,
          to_type text NOT NULL,
          to_id uuid NOT NULL,
          link_kind text,
          actor_phone text,
          reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_okr_align_action_chk CHECK (action IN ('linked','withdrawn'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_okr_updates (
          update_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          subject_type text NOT NULL,
          subject_id uuid NOT NULL,
          cycle_id uuid,
          actor_phone text,
          actor_employee_key text,
          update_text text NOT NULL,
          observed_value numeric,
          confidence text,
          check_in_id uuid,
          mutates_progress boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_okr_upd_subject_chk CHECK (subject_type IN ('objective','key_result')),
          CONSTRAINT perf_okr_upd_conf_chk CHECK (
            confidence IS NULL OR confidence IN ('high','medium','low')
          ),
          CONSTRAINT perf_okr_upd_no_progress_chk CHECK (mutates_progress = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS okr_operating_pt1_audit (
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
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS perf_okr_cycles_co_idx ON perf_okr_cycles(company_code, status)",
        "CREATE INDEX IF NOT EXISTS perf_okr_cycle_obj_idx ON perf_okr_cycle_objectives(company_code, cycle_id)",
        "CREATE INDEX IF NOT EXISTS perf_okr_vis_obj_idx ON perf_okr_visibility(company_code, objective_id, version)",
        "CREATE INDEX IF NOT EXISTS perf_okr_align_ev_idx ON perf_okr_alignment_events(company_code, from_id, to_id)",
        "CREATE INDEX IF NOT EXISTS perf_okr_upd_idx ON perf_okr_updates(company_code, subject_id, created_at)",
    ):
        cur.execute(idx_sql)


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
        INSERT INTO okr_operating_pt1_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code,
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            str(subject_id) if subject_id else None,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any]:
    ensure_okr_operating_pt1_schema(cur)
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM okr_operating_pt1_company_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    if row:
        return _row(row)
    return {
        "company_code": company,
        "confidence_enabled": False,
        "default_visibility": "owner_manager",
        "company_objectives_broadly_visible": True,
    }


def upsert_company_settings(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    confidence_enabled: bool | None = None,
    default_visibility: str | None = None,
    company_objectives_broadly_visible: bool | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    current = get_company_settings(cur, company)
    vis = str(default_visibility or current.get("default_visibility") or "owner_manager").lower()
    if vis not in VISIBILITIES:
        return {"ok": False, "error": "invalid_visibility", "allowed": list(VISIBILITIES)}
    conf = current.get("confidence_enabled") if confidence_enabled is None else bool(confidence_enabled)
    broad = (
        current.get("company_objectives_broadly_visible")
        if company_objectives_broadly_visible is None
        else bool(company_objectives_broadly_visible)
    )
    cur.execute(
        """
        INSERT INTO okr_operating_pt1_company_settings (
          company_code, confidence_enabled, default_visibility,
          company_objectives_broadly_visible, updated_by_phone, updated_at
        ) VALUES (%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          confidence_enabled=EXCLUDED.confidence_enabled,
          default_visibility=EXCLUDED.default_visibility,
          company_objectives_broadly_visible=EXCLUDED.company_objectives_broadly_visible,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (company, bool(conf), vis, bool(broad), _digits(actor_phone)),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="settings_upserted",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"confidence_enabled": bool(conf), "default_visibility": vis},
    )
    return {"ok": True, "settings": row, **honesty_payload(company_code=company)}


def sync_from_setup(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    overlay: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if "confidence_enabled" in overlay:
        kwargs["confidence_enabled"] = bool(overlay.get("confidence_enabled"))
    if "default_visibility" in overlay:
        kwargs["default_visibility"] = overlay.get("default_visibility")
    if "company_objectives_broadly_visible" in overlay:
        kwargs["company_objectives_broadly_visible"] = bool(
            overlay.get("company_objectives_broadly_visible")
        )
    if not kwargs:
        return {"ok": True, "synced": False, **honesty_payload(company_code=company_code)}
    return upsert_company_settings(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason, **kwargs
    )


def create_okr_cycle(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    period_start: date | str,
    period_end: date | str,
    name_ar: str | None = None,
    scope: str = "company",
    org_unit_id: str | None = None,
    visibility_policy: str | None = None,
    reason: str = "create okr cycle",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not str(name_en or "").strip():
        return {"ok": False, "error": "name_required"}
    sc = str(scope or "company").strip().lower()
    if sc not in c1.SCOPES:
        return {"ok": False, "error": "invalid_scope", "allowed": list(c1.SCOPES)}
    settings = get_company_settings(cur, company_code)
    vis = str(visibility_policy or settings.get("default_visibility") or "owner_manager").lower()
    if vis not in VISIBILITIES:
        return {"ok": False, "error": "invalid_visibility"}
    start = _as_date(period_start)
    end = _as_date(period_end)
    if not start or not end:
        return {"ok": False, "error": "period_required"}
    if start > end:
        return {"ok": False, "error": "period_end_before_start"}
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    cur.execute(
        """
        INSERT INTO perf_okr_cycles (
          company_code, name_en, name_ar, period_start, period_end, status, scope,
          org_unit_id, visibility_policy, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:500],
            (str(name_ar).strip()[:500] if name_ar else None),
            start,
            end,
            sc,
            org_unit_id,
            vis,
            _digits(actor_phone),
        ),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="okr_cycle_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="okr_cycle",
        subject_id=str(row.get("cycle_id")),
        payload={"not_review_cycle": True},
    )
    return {
        "ok": True,
        "cycle": row,
        "is_review_cycle": False,
        "review_cycle_id": None,
        **honesty_payload(company_code=company),
    }


def _get_cycle(cur: Any, company: str, cycle_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM perf_okr_cycles WHERE company_code=%s AND cycle_id=%s",
        (company, cycle_id),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def set_okr_cycle_status(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    actor_phone: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    st = str(status or "").strip().lower()
    if st not in CYCLE_STATUSES:
        return {"ok": False, "error": "invalid_cycle_status", "allowed": list(CYCLE_STATUSES)}
    company = company_code_norm(company_code)
    cycle = _get_cycle(cur, company, cycle_id)
    if not cycle:
        return {"ok": False, "error": "okr_cycle_not_found"}
    current = str(cycle.get("status") or "")
    allowed = {
        "draft": {"active", "closed"},
        "active": {"closed"},
        "closed": set(),
    }
    if st != current and st not in allowed.get(current, set()):
        return {"ok": False, "error": "invalid_cycle_transition", "from": current, "to": st}
    cur.execute(
        """
        UPDATE perf_okr_cycles
           SET status=%s,
               closed_at=CASE WHEN %s='closed' THEN now() ELSE closed_at END,
               row_version=row_version+1,
               version=version+1,
               updated_at=now()
         WHERE company_code=%s AND cycle_id=%s
        RETURNING *
        """,
        (st, st, company, cycle_id),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="okr_cycle_status",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="okr_cycle",
        subject_id=str(cycle_id),
        payload={"status": st},
    )
    return {"ok": True, "cycle": row, "is_review_cycle": False, **honesty_payload(company_code=company)}


def list_okr_cycles(
    cur: Any, *, company_code: str, status: str | None = None
) -> dict[str, Any]:
    ensure_okr_operating_pt1_schema(cur)
    company = company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if status:
        where.append("status=%s")
        params.append(str(status).strip().lower())
    cur.execute(
        f"""
        SELECT * FROM perf_okr_cycles
         WHERE {' AND '.join(where)}
         ORDER BY period_start DESC, created_at DESC
        """,
        params,
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "cycles": rows,
        "is_review_cycle": False,
        **honesty_payload(company_code=company),
    }


def current_okr_cycle(cur: Any, *, company_code: str) -> dict[str, Any]:
    listed = list_okr_cycles(cur, company_code=company_code, status="active")
    cycles = listed.get("cycles") or []
    return {
        "ok": True,
        "cycle": cycles[0] if cycles else None,
        "is_review_cycle": False,
        **honesty_payload(company_code=company_code),
    }


def set_objective_visibility(
    cur: Any,
    *,
    company_code: str,
    objective_id: str,
    visibility: str,
    actor_phone: str,
    reason: str = "set visibility",
) -> dict[str, Any]:
    vis = str(visibility or "").strip().lower()
    if vis not in VISIBILITIES:
        return {"ok": False, "error": "invalid_visibility", "allowed": list(VISIBILITIES)}
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    cur.execute(
        """
        SELECT COALESCE(MAX(version), 0) AS v FROM perf_okr_visibility
         WHERE company_code=%s AND objective_id=%s AND superseded_by IS NULL
        """,
        (company, objective_id),
    )
    current_v = int((_row(cur.fetchone()).get("v") or 0))
    cur.execute(
        """
        UPDATE perf_okr_visibility SET superseded_by=visibility_id
         WHERE company_code=%s AND objective_id=%s AND superseded_by IS NULL
        """,
        (company, objective_id),
    )
    cur.execute(
        """
        INSERT INTO perf_okr_visibility (
          company_code, objective_id, visibility, version, actor_phone
        ) VALUES (%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (company, objective_id, vis, current_v + 1, _digits(actor_phone)),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="visibility_set",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="objective",
        subject_id=str(objective_id),
        payload={"visibility": vis},
    )
    return {"ok": True, "visibility": row, **honesty_payload(company_code=company)}


def current_visibility(cur: Any, *, company_code: str, objective_id: str) -> str:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT visibility FROM perf_okr_visibility
         WHERE company_code=%s AND objective_id=%s AND superseded_by IS NULL
         ORDER BY version DESC LIMIT 1
        """,
        (company, objective_id),
    )
    row = cur.fetchone()
    if row:
        return str(_row(row).get("visibility") or "owner_manager")
    settings = get_company_settings(cur, company)
    return str(settings.get("default_visibility") or "owner_manager")


def can_view_objective(
    *,
    actor_role: str,
    visibility: str,
    owner_employee_key: str | None,
    actor_employee_key: str | None,
    manager_scope_keys: list[str] | None,
    org_unit_id: str | None = None,
    actor_org_unit_id: str | None = None,
    company_objectives_broadly_visible: bool = True,
    objective_scope: str | None = None,
) -> bool:
    role = str(actor_role or "").strip().lower()
    if role in {"hr", "admin", "owner", "facilitator"}:
        return True
    owner = str(owner_employee_key or "")
    actor = str(actor_employee_key or "")
    if actor and owner and actor == owner:
        return True
    vis = str(visibility or "owner_manager")
    if vis == "company" or (
        objective_scope == "company" and company_objectives_broadly_visible
    ):
        return True
    if role == "manager":
        keys = {str(k) for k in (manager_scope_keys or [])}
        if owner and owner in keys:
            return True
        if vis == "org_unit" and org_unit_id and actor_org_unit_id and org_unit_id == actor_org_unit_id:
            return True
        return False
    if vis == "org_unit" and org_unit_id and actor_org_unit_id and org_unit_id == actor_org_unit_id:
        return True
    return False


def attach_objective_to_cycle(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    objective_id: str,
    actor_phone: str,
    visibility: str | None = None,
    reason: str = "attach objective",
) -> dict[str, Any]:
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = _get_cycle(cur, company, cycle_id)
    if not cycle:
        return {"ok": False, "error": "okr_cycle_not_found"}
    if str(cycle.get("status")) == "closed":
        return {"ok": False, "error": "okr_cycle_closed"}
    cur.execute(
        "SELECT * FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
        (company, objective_id),
    )
    obj = cur.fetchone()
    if not obj:
        return {"ok": False, "error": "objective_not_found"}
    obj = _row(obj)
    cur.execute(
        """
        INSERT INTO perf_okr_cycle_objectives (
          company_code, cycle_id, objective_id, attached_by_phone
        ) VALUES (%s,%s,%s,%s)
        ON CONFLICT (cycle_id, objective_id) DO NOTHING
        RETURNING *
        """,
        (company, cycle_id, objective_id, _digits(actor_phone)),
    )
    membership = cur.fetchone()
    settings = get_company_settings(cur, company)
    vis = visibility
    if not vis:
        if str(obj.get("scope")) == "company" and settings.get("company_objectives_broadly_visible"):
            vis = "company"
        else:
            vis = str(settings.get("default_visibility") or "owner_manager")
    set_objective_visibility(
        cur,
        company_code=company,
        objective_id=str(objective_id),
        visibility=str(vis),
        actor_phone=actor_phone,
        reason=reason,
    )
    _audit(
        cur,
        company_code=company,
        action="objective_attached_to_cycle",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="objective",
        subject_id=str(objective_id),
        payload={"cycle_id": str(cycle_id)},
    )
    return {
        "ok": True,
        "membership": _row(membership) if membership else {"cycle_id": cycle_id, "objective_id": objective_id},
        "cycle_id": str(cycle_id),
        "objective_id": str(objective_id),
        **honesty_payload(company_code=company),
    }


def create_objective_in_cycle(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    title_en: str,
    scope: str,
    owner_employee_key: str | None = None,
    org_unit_id: str | None = None,
    title_ar: str | None = None,
    visibility: str | None = None,
    reason: str = "create objective in cycle",
) -> dict[str, Any]:
    cycle = _get_cycle(cur, company_code_norm(company_code), cycle_id)
    if not cycle:
        return {"ok": False, "error": "okr_cycle_not_found"}
    created = c1.create_objective(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        title_en=title_en,
        scope=scope,
        owner_employee_key=owner_employee_key,
        org_unit_id=org_unit_id,
        title_ar=title_ar,
        period_start=cycle.get("period_start"),
        period_end=cycle.get("period_end"),
        reason=reason,
    )
    if not created.get("ok"):
        return created
    oid = str(created["objective"]["objective_id"])
    attached = attach_objective_to_cycle(
        cur,
        company_code=company_code,
        cycle_id=cycle_id,
        objective_id=oid,
        actor_phone=actor_phone,
        visibility=visibility,
        reason=reason,
    )
    if not attached.get("ok"):
        return attached
    return {
        **created,
        "cycle_id": str(cycle_id),
        "is_review_cycle": False,
        **honesty_payload(company_code=company_code),
    }


def create_alignment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    child_objective_id: str,
    parent_objective_id: str,
    link_kind: str = "contributes_to",
    reason: str = "align",
) -> dict[str, Any]:
    if str(child_objective_id) == str(parent_objective_id):
        return {"ok": False, "error": "alignment_self_forbidden"}
    linked = c1.create_alignment_link(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        from_type="objective",
        from_id=child_objective_id,
        to_type="objective",
        to_id=parent_objective_id,
        link_kind=link_kind,
        reason=reason,
    )
    if not linked.get("ok"):
        return linked
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    link = linked.get("link") or {}
    cur.execute(
        """
        INSERT INTO perf_okr_alignment_events (
          company_code, link_id, action, from_type, from_id, to_type, to_id, link_kind,
          actor_phone, reason
        ) VALUES (%s,%s,'linked','objective',%s,'objective',%s,%s,%s,%s)
        """,
        (
            company,
            link.get("link_id"),
            child_objective_id,
            parent_objective_id,
            str(link_kind or "contributes_to"),
            _digits(actor_phone),
            reason,
        ),
    )
    return {
        **linked,
        "inherits_score": False,
        "parent_progress_unchanged_by_alignment": True,
        **honesty_payload(company_code=company),
    }


def withdraw_alignment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    link_id: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_alignment_links WHERE company_code=%s AND link_id=%s",
        (company, link_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "alignment_link_not_found"}
    link = _row(row)
    cur.execute(
        "DELETE FROM perf_alignment_links WHERE company_code=%s AND link_id=%s",
        (company, link_id),
    )
    ensure_okr_operating_pt1_schema(cur)
    cur.execute(
        """
        INSERT INTO perf_okr_alignment_events (
          company_code, link_id, action, from_type, from_id, to_type, to_id, link_kind,
          actor_phone, reason
        ) VALUES (%s,%s,'withdrawn',%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            company,
            link_id,
            link.get("from_type"),
            link.get("from_id"),
            link.get("to_type"),
            link.get("to_id"),
            link.get("link_kind"),
            _digits(actor_phone),
            reason,
        ),
    )
    return {
        "ok": True,
        "withdrawn": True,
        "inherits_score": False,
        **honesty_payload(company_code=company),
    }


def alignment_history(cur: Any, *, company_code: str, objective_id: str | None = None) -> dict[str, Any]:
    ensure_okr_operating_pt1_schema(cur)
    company = company_code_norm(company_code)
    if objective_id:
        cur.execute(
            """
            SELECT * FROM perf_okr_alignment_events
             WHERE company_code=%s AND (from_id=%s OR to_id=%s)
             ORDER BY created_at
            """,
            (company, objective_id, objective_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM perf_okr_alignment_events
             WHERE company_code=%s ORDER BY created_at
            """,
            (company,),
        )
    return {
        "ok": True,
        "events": [_row(r) for r in (cur.fetchall() or [])],
        "inherits_score": False,
        **honesty_payload(company_code=company),
    }


def _visible_objectives(
    cur: Any,
    *,
    company: str,
    actor_role: str,
    actor_employee_key: str | None,
    manager_scope_keys: list[str] | None,
    actor_org_unit_id: str | None,
    cycle_id: str | None,
) -> list[dict[str, Any]]:
    settings = get_company_settings(cur, company)
    if cycle_id:
        cur.execute(
            """
            SELECT o.* FROM perf_objectives o
              JOIN perf_okr_cycle_objectives m
                ON m.objective_id=o.objective_id AND m.company_code=o.company_code
             WHERE o.company_code=%s AND m.cycle_id=%s
             ORDER BY o.scope, o.created_at
            """,
            (company, cycle_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM perf_objectives
             WHERE company_code=%s AND status NOT IN ('cancelled','archived')
             ORDER BY scope, created_at
            """,
            (company,),
        )
    out: list[dict[str, Any]] = []
    for raw in cur.fetchall() or []:
        obj = _row(raw)
        vis = current_visibility(cur, company_code=company, objective_id=str(obj["objective_id"]))
        if not can_view_objective(
            actor_role=actor_role,
            visibility=vis,
            owner_employee_key=str(obj.get("owner_employee_key") or ""),
            actor_employee_key=actor_employee_key,
            manager_scope_keys=manager_scope_keys,
            org_unit_id=str(obj.get("org_unit_id") or "") or None,
            actor_org_unit_id=actor_org_unit_id,
            company_objectives_broadly_visible=bool(settings.get("company_objectives_broadly_visible")),
            objective_scope=str(obj.get("scope") or ""),
        ):
            continue
        obj["visibility"] = vis
        out.append(obj)
    return out


def alignment_tree(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str | None = None,
    actor_role: str = "hr",
    actor_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    actor_org_unit_id: str | None = None,
) -> dict[str, Any]:
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    visible = _visible_objectives(
        cur,
        company=company,
        actor_role=actor_role,
        actor_employee_key=actor_employee_key,
        manager_scope_keys=manager_scope_keys,
        actor_org_unit_id=actor_org_unit_id,
        cycle_id=cycle_id,
    )
    visible_ids = {str(o["objective_id"]) for o in visible}
    cur.execute(
        """
        SELECT * FROM perf_alignment_links
         WHERE company_code=%s AND from_type='objective' AND to_type='objective'
        """,
        (company,),
    )
    links = [_row(r) for r in (cur.fetchall() or [])]
    children: dict[str, list[str]] = {}
    parents: dict[str, str] = {}
    for link in links:
        child = str(link.get("from_id"))
        parent = str(link.get("to_id"))
        if child not in visible_ids or parent not in visible_ids:
            continue
        children.setdefault(parent, []).append(child)
        parents[child] = parent

    def _node(oid: str) -> dict[str, Any]:
        obj = next(o for o in visible if str(o["objective_id"]) == oid)
        rollup = c1.objective_rollup(cur, company_code=company, objective_id=oid)
        return {
            "objective_id": oid,
            "title_en": obj.get("title_en"),
            "title_ar": obj.get("title_ar"),
            "scope": obj.get("scope"),
            "owner_employee_key": obj.get("owner_employee_key"),
            "visibility": obj.get("visibility"),
            "status": obj.get("status"),
            "rollup": {
                "progress_pct": rollup.get("progress_pct"),
                "formula_version": rollup.get("formula_version"),
                "inherited_from_alignment": False,
            },
            "children": [_node(cid) for cid in children.get(oid, [])],
        }

    roots = [o for o in visible if str(o["objective_id"]) not in parents]
    tree = [_node(str(o["objective_id"])) for o in roots]
    orphans = [n for n in tree if not n["children"] and n["scope"] != "company"]
    return {
        "ok": True,
        "tree": tree,
        "orphan_count": len(orphans),
        "inherits_score": False,
        "hidden_by_permission": True,
        "cycle_id": cycle_id,
        **honesty_payload(company_code=company),
    }


def record_update(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    subject_type: str,
    subject_id: str,
    update_text: str,
    actor_employee_key: str | None = None,
    observed_value: Any = None,
    confidence: str | None = None,
    cycle_id: str | None = None,
    reason: str = "okr update",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = c1.module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    st = str(subject_type or "").strip().lower()
    if st not in UPDATE_SUBJECTS:
        return {"ok": False, "error": "invalid_subject_type", "allowed": list(UPDATE_SUBJECTS)}
    if not str(update_text or "").strip():
        return {"ok": False, "error": "update_text_required"}
    settings = get_company_settings(cur, company_code)
    conf = str(confidence).strip().lower() if confidence else None
    if conf:
        if not settings.get("confidence_enabled"):
            return {"ok": False, "error": "confidence_disabled"}
        if conf not in CONFIDENCE:
            return {"ok": False, "error": "invalid_confidence", "allowed": list(CONFIDENCE)}
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    table = "perf_objectives" if st == "objective" else "perf_key_results"
    id_col = "objective_id" if st == "objective" else "key_result_id"
    cur.execute(
        f"SELECT * FROM {table} WHERE company_code=%s AND {id_col}=%s",
        (company, subject_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": f"{st}_not_found"}

    check_in_id = None
    try:
        import performance_feedback_c3 as c3

        c3.ensure_performance_feedback_c3_schema(cur)
        owner_key = actor_employee_key
        if st == "objective":
            cur.execute(
                "SELECT owner_employee_key FROM perf_objectives WHERE objective_id=%s",
                (subject_id,),
            )
            owner_key = str((_row(cur.fetchone()).get("owner_employee_key") or owner_key or ""))
        elif st == "key_result":
            cur.execute(
                """
                SELECT o.owner_employee_key
                  FROM perf_key_results kr
                  JOIN perf_objectives o ON o.objective_id=kr.objective_id
                 WHERE kr.key_result_id=%s
                """,
                (subject_id,),
            )
            owner_key = str((_row(cur.fetchone()).get("owner_employee_key") or owner_key or ""))
        if owner_key:
            ci = c3.create_check_in(
                cur,
                company_code=company,
                actor_phone=actor_phone,
                employee_key=owner_key,
                kind="ad_hoc",
                notes_shared=str(update_text).strip()[:4000],
                linked_subject_type=st,
                linked_subject_id=str(subject_id),
                progress_discussion=str(update_text).strip()[:2000],
                reason=reason,
            )
            if ci.get("ok"):
                check_in_id = str((ci.get("check_in") or {}).get("check_in_id") or "") or None
    except Exception:
        check_in_id = None

    observed = None
    if observed_value not in (None, ""):
        try:
            from decimal import Decimal

            observed = Decimal(str(observed_value))
        except Exception:
            return {"ok": False, "error": "invalid_observed_value"}

    cur.execute(
        """
        INSERT INTO perf_okr_updates (
          company_code, subject_type, subject_id, cycle_id, actor_phone, actor_employee_key,
          update_text, observed_value, confidence, check_in_id, mutates_progress
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
        RETURNING *
        """,
        (
            company,
            st,
            subject_id,
            cycle_id,
            _digits(actor_phone),
            actor_employee_key,
            str(update_text).strip()[:4000],
            observed,
            conf,
            check_in_id,
        ),
    )
    row = _row(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="okr_update_recorded",
        actor_phone=actor_phone,
        reason=reason,
        subject_type=st,
        subject_id=str(subject_id),
        payload={"mutates_progress": False, "confidence": conf, "check_in_id": check_in_id},
    )
    return {
        "ok": True,
        "update": row,
        "mutates_progress": False,
        "progress_authority": "performance_goals_c1.record_progress",
        "confidence_is_not_progress": True,
        **honesty_payload(company_code=company),
    }


def list_updates(
    cur: Any, *, company_code: str, subject_type: str, subject_id: str
) -> dict[str, Any]:
    ensure_okr_operating_pt1_schema(cur)
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM perf_okr_updates
         WHERE company_code=%s AND subject_type=%s AND subject_id=%s
         ORDER BY created_at
        """,
        (company, subject_type, subject_id),
    )
    return {
        "ok": True,
        "updates": [_row(r) for r in (cur.fetchall() or [])],
        "mutates_progress": False,
        **honesty_payload(company_code=company),
    }


def objective_operating_history(
    cur: Any, *, company_code: str, objective_id: str
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    cur.execute(
        """
        SELECT tv.*
          FROM perf_target_versions tv
          JOIN perf_key_results kr
            ON kr.company_code=tv.company_code
           AND kr.measure_id = tv.measure_id
         WHERE tv.company_code=%s
           AND kr.objective_id=%s
           AND tv.subject_type='measure'
         ORDER BY tv.created_at
        """,
        (company, objective_id),
    )
    targets = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT * FROM perf_progress_entries
         WHERE company_code=%s AND subject_id IN (
           SELECT key_result_id::text FROM perf_key_results WHERE objective_id=%s
           UNION SELECT %s
         )
         ORDER BY recorded_at
        """,
        (company, objective_id, objective_id),
    )
    progress = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT * FROM perf_okr_updates
         WHERE company_code=%s AND (
           (subject_type='objective' AND subject_id=%s)
           OR (subject_type='key_result' AND subject_id IN (
             SELECT key_result_id FROM perf_key_results WHERE objective_id=%s
           ))
         )
         ORDER BY created_at
        """,
        (company, objective_id, objective_id),
    )
    updates = [_row(r) for r in (cur.fetchall() or [])]
    align = alignment_history(cur, company_code=company, objective_id=objective_id)
    vis_hist: list[dict[str, Any]] = []
    cur.execute(
        """
        SELECT * FROM perf_okr_visibility
         WHERE company_code=%s AND objective_id=%s ORDER BY version
        """,
        (company, objective_id),
    )
    vis_hist = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "objective_id": str(objective_id),
        "target_versions": targets,
        "progress_entries": progress,
        "updates": updates,
        "alignment_events": align.get("events") or [],
        "visibility_history": vis_hist,
        "trajectory_ready": True,
        "trajectory_labels": None,
        "inherits_score": False,
        **honesty_payload(company_code=company),
    }


def list_cycle_objectives(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str | None = None,
    owner_employee_key: str | None = None,
    actor_role: str = "hr",
    actor_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    actor_org_unit_id: str | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_okr_operating_pt1_schema(cur)
    rows = _visible_objectives(
        cur,
        company=company,
        actor_role=actor_role,
        actor_employee_key=actor_employee_key,
        manager_scope_keys=manager_scope_keys,
        actor_org_unit_id=actor_org_unit_id,
        cycle_id=cycle_id,
    )
    if owner_employee_key:
        rows = [r for r in rows if str(r.get("owner_employee_key") or "") == str(owner_employee_key)]
    decorated = []
    for obj in rows:
        oid = str(obj["objective_id"])
        rollup = c1.objective_rollup(cur, company_code=company, objective_id=oid)
        membership = None
        cur.execute(
            """
            SELECT cycle_id FROM perf_okr_cycle_objectives
             WHERE company_code=%s AND objective_id=%s
             ORDER BY attached_at DESC LIMIT 1
            """,
            (company, oid),
        )
        mem = cur.fetchone()
        if mem:
            membership = str(_row(mem).get("cycle_id"))
        decorated.append(
            {
                **obj,
                "cycle_id": membership,
                "rollup": {
                    "progress_pct": rollup.get("progress_pct"),
                    "formula_version": rollup.get("formula_version"),
                    "inherited_from_alignment": False,
                },
            }
        )
    return {
        "ok": True,
        "objectives": decorated,
        "total": len(decorated),
        "inherits_score": False,
        **honesty_payload(company_code=company),
    }


def payload_integrity_marker(*, source_authority: str, source_id: str, version: Any, body: Any) -> str:
    raw = json.dumps(
        {"authority": source_authority, "id": str(source_id), "version": version, "body": body},
        default=str,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
