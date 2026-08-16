"""Setup Console — Wave 1 Hire→Ready company policies.

Owns company-level configuration for requisitions (job gate), preboarding
(offer auto-create + readiness), probation (auto-plan + milestones), and
hire→onboarding auto-start. Reuses frozen module settings tables; does not
invent a parallel SoT.
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_wave1"
CONTRACT_VERSION = "wave1_hire_ready_policies_v1"
WAVE1_MODULE_KEYS = ("requisitions", "preboarding", "probation", "onboarding")


def _company(code: str) -> str:
    return str(code or "").upper()


def _sp(cur: Any, name: str = "w1p") -> None:
    try:
        cur.execute(f"SAVEPOINT {name}")
    except Exception:
        pass


def _sp_release(cur: Any, name: str = "w1p") -> None:
    try:
        cur.execute(f"RELEASE SAVEPOINT {name}")
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        except Exception:
            pass


def _sp_rollback(cur: Any, name: str = "w1p") -> None:
    try:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
    except Exception:
        pass


def _module_row(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    _sp(cur, "w1p_mod")
    try:
        cur.execute(
            """
            SELECT enabled, settings FROM company_modules
            WHERE company_code=%s AND module_key=%s
            LIMIT 1
            """,
            (company, module_key),
        )
        row = cur.fetchone()
        _sp_release(cur, "w1p_mod")
    except Exception:
        _sp_rollback(cur, "w1p_mod")
        return {"enabled": False, "settings": {}}
    if not row:
        return {"enabled": False, "settings": {}}
    d = dict(row) if isinstance(row, dict) else {"enabled": row[0], "settings": row[1]}
    settings = d.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    if not isinstance(settings, dict):
        settings = {}
    return {"enabled": bool(d.get("enabled")), "settings": settings}


def _save_module_settings(cur: Any, company: str, module_key: str, settings: dict[str, Any]) -> None:
    cur.execute(
        """
        SELECT enabled, settings FROM company_modules
        WHERE company_code=%s AND module_key=%s
        LIMIT 1 FOR UPDATE
        """,
        (company, module_key),
    )
    row = cur.fetchone()
    current_enabled = bool(dict(row).get("enabled")) if row else False
    current_settings = dict(dict(row).get("settings") or {}) if row and isinstance(dict(row).get("settings"), dict) else {}
    if row and isinstance(dict(row).get("settings"), str):
        try:
            current_settings = json.loads(dict(row).get("settings"))
        except Exception:
            current_settings = {}
    merged = {**current_settings, **settings}
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,%s,'setup_console',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, module_key, current_enabled, json.dumps(merged)),
    )


def _set_company_setting(cur: Any, company: str, key: str, value: Any) -> None:
    cur.execute(
        """
        INSERT INTO company_settings (company_code, settings, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (company_code) DO UPDATE
          SET settings = COALESCE(company_settings.settings, '{}'::jsonb) || EXCLUDED.settings,
              updated_at = now()
        """,
        (company, json.dumps({key: value})),
    )


def _get_company_setting(cur: Any, company: str, key: str, default: Any = None) -> Any:
    cur.execute("SELECT settings FROM company_settings WHERE company_code=%s LIMIT 1", (company,))
    row = cur.fetchone()
    if not row:
        return default
    settings = dict(row).get("settings") if isinstance(row, dict) else row[0]
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    if not isinstance(settings, dict):
        return default
    return settings.get(key, default)


def get_requisitions_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "requisitions")
    import requisitions as rq

    _sp(cur, "w1p_rq")
    try:
        rq.ensure_requisitions_schema(cur)
        settings = rq.get_settings(cur, company)
        _sp_release(cur, "w1p_rq")
    except Exception:
        _sp_rollback(cur, "w1p_rq")
        settings = {"enabled": mod["enabled"], "jobs_require_approved_requisition": True}
    pre_hiring = _module_row(cur, company, "pre_hiring")
    return {
        "ok": True,
        "module_key": "requisitions",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "jobs_require_approved_requisition": bool(settings.get("jobs_require_approved_requisition", True)),
            "approval_mode": "sod_single_step",
            "note_en": "Wave 1 uses creator SoD (creator cannot self-approve). Platform N-step available for later binding.",
            "note_ar": "الموجة ١ تستخدم فصل صلاحيات المنشئ. الموافقات متعددة الخطوات متاحة لاحقاً.",
        },
        "optional": {
            "pre_hiring_enabled": pre_hiring["enabled"],
            "gate_active_when_both_on": bool(
                mod["enabled"] and pre_hiring["enabled"] and settings.get("jobs_require_approved_requisition", True)
            ),
        },
        "advanced": {
            "delegation": "platform_workflow_approvals",
            "sla_task_type": "requisition_approval",
        },
        "ops_deep_link": "/dashboard?page=requisitions",
        "ownership": {"company_policy": "setup_console", "queue_ops": "hr_web_mobile"},
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": (
            "Job publish requires approved requisition"
            if settings.get("jobs_require_approved_requisition", True)
            else "Job publish gate off"
        ),
        "summary_ar": (
            "نشر الوظيفة يتطلب طلب توظيف معتمد"
            if settings.get("jobs_require_approved_requisition", True)
            else "بوابة نشر الوظيفة متوقفة"
        ),
    }


def patch_requisitions_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    import requisitions as rq

    rq.ensure_requisitions_schema(cur)
    gate = None
    if "jobs_require_approved_requisition" in req:
        gate = bool(req.get("jobs_require_approved_requisition"))
    settings = rq.set_settings(
        cur,
        company,
        enabled=True if _module_row(cur, company, "requisitions")["enabled"] else None,
        jobs_require_approved_requisition=gate,
    )
    _save_module_settings(
        cur,
        company,
        "requisitions",
        {
            "wave1_setup": {
                "jobs_require_approved_requisition": settings.get("jobs_require_approved_requisition"),
                "updated_reason": str(reason).strip()[:200],
                "updated_by": actor_phone,
            }
        },
    )
    return {"ok": True, "actions": [{"action": "update_requisition_gate"}], "policy": get_requisitions_company_policy(cur, company)}


def get_preboarding_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "preboarding")
    import preboarding as pb

    _sp(cur, "w1p_pb")
    try:
        pb.ensure_preboarding_schema(cur)
        settings = pb.get_settings(cur, company)
        pb.ensure_default_template(cur, company)
        items = pb.list_template_items(cur, company_code=company)
        _sp_release(cur, "w1p_pb")
    except Exception:
        _sp_rollback(cur, "w1p_pb")
        settings = {
            "enabled": mod["enabled"],
            "auto_create_on_offer_accept": True,
            "required_for_ready_mark": True,
            "handoff_onboarding_enabled": True,
        }
        items = []
    return {
        "ok": True,
        "module_key": "preboarding",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "auto_create_on_offer_accept": bool(settings.get("auto_create_on_offer_accept", True)),
            "required_for_ready_mark": bool(settings.get("required_for_ready_mark", True)),
            "template_id": getattr(pb, "DEFAULT_TEMPLATE_ID", "default_kuwait_preboard"),
            "template_item_count": len(items),
        },
        "optional": {
            "handoff_onboarding_enabled": bool(settings.get("handoff_onboarding_enabled", True)),
        },
        "advanced": {"sla_task_types": ["preboard_item", "preboard_readiness"]},
        "ops_deep_link": "/dashboard?page=preboarding",
        "ownership": {"company_policy": "setup_console", "assignments": "preboarding_ops"},
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"Template {getattr(pb, 'DEFAULT_TEMPLATE_ID', 'default')} · {len(items)} items · offer auto-create "
        f"{'on' if settings.get('auto_create_on_offer_accept', True) else 'off'}",
        "summary_ar": f"القالب الافتراضي · {len(items)} بنود · إنشاء تلقائي من العرض "
        f"{'مفعّل' if settings.get('auto_create_on_offer_accept', True) else 'متوقف'}",
    }


def patch_preboarding_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
    optional: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    opt = optional or {}
    import preboarding as pb

    pb.ensure_preboarding_schema(cur)
    pb.set_settings(
        cur,
        company,
        enabled=True if _module_row(cur, company, "preboarding")["enabled"] else None,
        auto_create_on_offer_accept=req.get("auto_create_on_offer_accept"),
        required_for_ready_mark=req.get("required_for_ready_mark"),
        handoff_onboarding_enabled=opt.get("handoff_onboarding_enabled"),
    )
    _save_module_settings(
        cur,
        company,
        "preboarding",
        {
            "wave1_setup": {
                "updated_reason": str(reason).strip()[:200],
                "updated_by": actor_phone,
            }
        },
    )
    return {"ok": True, "actions": [{"action": "update_preboarding_settings"}], "policy": get_preboarding_company_policy(cur, company)}


def get_probation_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "probation")
    import probation as pr

    _sp(cur, "w1p_pr")
    try:
        pr.ensure_probation_schema(cur)
        settings = pr.get_settings(cur, company)
        pr.ensure_default_template(cur, company)
        tid = getattr(pr, "DEFAULT_TEMPLATE_ID", "default_kuwait_30_60_90")
        cur.execute(
            "SELECT count(*) AS c FROM probation_plan_template_milestones WHERE company_code=%s AND template_id=%s",
            (company, tid),
        )
        ms_count = int(dict(cur.fetchone() or {"c": 0})["c"])
        if ms_count <= 0:
            ms_count = len(getattr(pr, "default_kuwait_milestones", lambda: [1, 2, 3])())
        _sp_release(cur, "w1p_pr")
    except Exception:
        _sp_rollback(cur, "w1p_pr")
        settings = {
            "enabled": mod["enabled"],
            "auto_plan_on_hire": True,
            "start_mode": "hire_date",
            "default_probation_days": 90,
        }
        ms_count = 3
        tid = "default_kuwait_30_60_90"
    return {
        "ok": True,
        "module_key": "probation",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "auto_plan_on_hire": bool(settings.get("auto_plan_on_hire", True)),
            "start_mode": str(settings.get("start_mode") or "hire_date"),
            "default_probation_days": int(settings.get("default_probation_days") or 90),
            "milestone_template": tid if "tid" in locals() else "default_kuwait_30_60_90",
            "milestone_count": ms_count,
        },
        "optional": {
            "manager_recommendation_is_final": False,
            "note_en": "Manager recommendation is not final HR authority unless company policy later elevates it.",
        },
        "advanced": {"sla_task_types": ["probation_milestone", "probation_decision"]},
        "ops_deep_link": "/dashboard?page=probation",
        "ownership": {"company_policy": "setup_console", "cases": "probation_ops"},
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"{settings.get('default_probation_days') or 90}d · auto-plan "
        f"{'on' if settings.get('auto_plan_on_hire', True) else 'off'} · {ms_count} milestones",
        "summary_ar": f"{settings.get('default_probation_days') or 90} يوماً · تخطيط تلقائي "
        f"{'مفعّل' if settings.get('auto_plan_on_hire', True) else 'متوقف'} · {ms_count} معالم",
    }


def patch_probation_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    import probation as pr

    pr.ensure_probation_schema(cur)
    result = pr.set_settings(
        cur,
        company,
        enabled=True if _module_row(cur, company, "probation")["enabled"] else None,
        auto_plan_on_hire=req.get("auto_plan_on_hire"),
        start_mode=req.get("start_mode"),
        default_probation_days=req.get("default_probation_days"),
    )
    if isinstance(result, dict) and result.get("error"):
        return {"ok": False, **result}
    _save_module_settings(
        cur,
        company,
        "probation",
        {
            "wave1_setup": {
                "updated_reason": str(reason).strip()[:200],
                "updated_by": actor_phone,
            }
        },
    )
    return {"ok": True, "actions": [{"action": "update_probation_settings"}], "policy": get_probation_company_policy(cur, company)}


def get_wave1_onboarding_auto_start_policy(cur: Any, company_code: str) -> dict[str, Any]:
    """Additive Wave 1 hire→onboarding auto-start (company_settings blob)."""
    company = _company(company_code)
    mod = _module_row(cur, company, "onboarding")
    auto = bool(_get_company_setting(cur, company, "onboarding.auto_start_on_hire", True))
    return {
        "ok": True,
        "module_key": "onboarding_auto_start",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {"auto_start_on_hire": auto},
        "optional": {},
        "advanced": {},
        "ops_deep_link": "/dashboard?page=onboarding",
        "ownership": {"company_policy": "setup_console"},
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"Auto-start on hire {'on' if auto else 'off'}",
        "summary_ar": f"البدء التلقائي عند التعيين {'مفعّل' if auto else 'متوقف'}",
    }


def patch_wave1_onboarding_auto_start(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    if "auto_start_on_hire" in req:
        _set_company_setting(cur, company, "onboarding.auto_start_on_hire", bool(req.get("auto_start_on_hire")))
    _save_module_settings(
        cur,
        company,
        "onboarding",
        {
            "wave1_auto_start": {
                "auto_start_on_hire": bool(req.get("auto_start_on_hire", True)),
                "updated_reason": str(reason).strip()[:200],
                "updated_by": actor_phone,
            }
        },
    )
    return {
        "ok": True,
        "actions": [{"action": "update_onboarding_auto_start"}],
        "policy": get_wave1_onboarding_auto_start_policy(cur, company),
    }


def get_all_wave1_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "company_code": company,
        "requisitions": get_requisitions_company_policy(cur, company),
        "preboarding": get_preboarding_company_policy(cur, company),
        "probation": get_probation_company_policy(cur, company),
        "onboarding_auto_start": get_wave1_onboarding_auto_start_policy(cur, company),
        "cross_module": {
            "ops_requisitions": "/dashboard?page=requisitions",
            "ops_preboarding": "/dashboard?page=preboarding",
            "ops_probation": "/dashboard?page=probation",
            "approval_mode_wave1": "sod_single_step",
            "platform_n_step": "workflow_approvals",
        },
    }


def patch_wave1_module_policy(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor_phone: str | None,
    reason: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    key = str(module_key or "").strip().lower()
    if key == "requisitions":
        return patch_requisitions_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
        )
    if key == "preboarding":
        return patch_preboarding_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
            optional=payload.get("optional"),
        )
    if key == "probation":
        return patch_probation_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
        )
    if key in {"onboarding_auto_start", "onboarding-auto-start"}:
        return patch_wave1_onboarding_auto_start(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
        )
    return {
        "ok": False,
        "error": "unknown_module_key",
        "allowed": ["requisitions", "preboarding", "probation", "onboarding_auto_start"],
    }
