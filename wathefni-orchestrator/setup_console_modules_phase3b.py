"""Setup Console Phase 3B — remaining module company policies.

Owns company-level policy for Leave, Attendance, Shifts, Documents/Compliance,
and Onboarding. Reuses canonical tables; does not invent parallel SoT.
Working calendar remains Phase 3A (payroll setup_extras + public_holidays).
"""
from __future__ import annotations

import json
from typing import Any

import payroll_authority_wave1 as pyw1

PHASE = "setup_console_phase3b"
CONTRACT_VERSION = "module_company_policies_v1"

WEEKDAY_TO_INT = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
INT_TO_WEEKDAY = {v: k for k, v in WEEKDAY_TO_INT.items()}

LEAVE_TYPES = ("annual", "sick", "unpaid")
MODULE_KEYS = ("leave", "attendance", "shifts", "compliance", "onboarding", "documents")


def _sp(cur: Any, name: str = "p3b") -> None:
    try:
        cur.execute(f"SAVEPOINT {name}")
    except Exception:
        pass


def _sp_release(cur: Any, name: str = "p3b") -> None:
    try:
        cur.execute(f"RELEASE SAVEPOINT {name}")
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        except Exception:
            pass


def _sp_rollback(cur: Any, name: str = "p3b") -> None:
    try:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
    except Exception:
        pass


def _isolate_policy(cur: Any, name: str, loader: Any) -> dict[str, Any]:
    """Run a policy GET without aborting the shared Setup Console transaction."""
    _sp(cur, name)
    try:
        payload = loader()
        _sp_release(cur, name)
        return payload if isinstance(payload, dict) else {"ok": False, "error": "policy_unavailable", "module_key": name}
    except Exception:
        _sp_rollback(cur, name)
        return {"ok": False, "error": "policy_unavailable", "module_key": name}


def _company(code: str) -> str:
    return str(code or "").upper()


def _module_row(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT enabled, settings FROM company_modules
        WHERE company_code=%s AND module_key=%s
        LIMIT 1
        """,
        (company, module_key),
    )
    row = cur.fetchone()
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


def _save_module_settings(cur: Any, company: str, module_key: str, settings: dict[str, Any], *, enabled: bool | None = None) -> None:
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
    next_enabled = current_enabled if enabled is None else bool(enabled)
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,%s,'setup_console',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          enabled=EXCLUDED.enabled,
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, module_key, next_enabled, json.dumps(merged)),
    )


def _calendar_weekend_days(cur: Any, company: str) -> list[str]:
    _sp(cur, "p3b_cal")
    try:
        import setup_console_payroll_phase3a as p3a

        settings = pyw1.ensure_company_settings(cur, company_code=company)
        extras = p3a.parse_setup_extras(settings)
        days = list(extras.get("weekend_days") or [])
        _sp_release(cur, "p3b_cal")
        return days
    except Exception:
        _sp_rollback(cur, "p3b_cal")
        return ["fri", "sat"]


def sync_calendar_consumers(cur: Any, company: str, weekend_days: list[str] | None = None) -> dict[str, Any]:
    """Push Phase 3A weekend days into Leave policies + Shifts rest_weekdays (no second calendar)."""
    company = _company(company)
    days = weekend_days if weekend_days is not None else _calendar_weekend_days(cur, company)
    if not days:
        days = ["fri", "sat"]
    # Leave policies
    cur.execute(
        """
        UPDATE leave_policies
        SET weekend_days=%s
        WHERE company_code=%s
        """,
        (list(days), company),
    )
    leave_n = cur.rowcount or 0
    # Shifts authority
    rest_ints = sorted({WEEKDAY_TO_INT[d] for d in days if d in WEEKDAY_TO_INT})
    try:
        import shifts_authority_wave1 as sh

        sh.ensure_shifts_authority_wave1_schema(cur)
        sh.seed_shift_authority_settings(cur, company)
        cur.execute(
            """
            UPDATE shift_authority_settings
            SET rest_weekdays=%s, updated_at=now()
            WHERE company_code=%s
            """,
            (rest_ints, company),
        )
        shifts_n = cur.rowcount or 0
    except Exception:
        shifts_n = 0
    return {"ok": True, "weekend_days": days, "leave_rows": leave_n, "shifts_updated": shifts_n > 0, "rest_weekdays": rest_ints}


def get_leave_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "leave")
    # Ensure seeded
    try:
        import sys

        legacy = sys.modules.get("app") or sys.modules.get("__main__")
        if legacy and hasattr(legacy, "seed_company_leave_policies"):
            legacy.seed_company_leave_policies(company)
    except Exception:
        pass
    cur.execute(
        """
        SELECT leave_type, days_per_year, accrual_method, eligibility_months,
               weekend_days, exclude_public_holidays, allow_negative, tiers,
               enforced, legal_reviewed, version
        FROM leave_policies
        WHERE company_code=%s
        ORDER BY leave_type
        """,
        (company,),
    )
    policies = []
    for r in cur.fetchall() or []:
        row = dict(r) if isinstance(r, dict) else {
            "leave_type": r[0],
            "days_per_year": r[1],
            "accrual_method": r[2],
            "eligibility_months": r[3],
            "weekend_days": r[4],
            "exclude_public_holidays": r[5],
            "allow_negative": r[6],
            "tiers": r[7],
            "enforced": r[8],
            "legal_reviewed": r[9],
            "version": r[10],
        }
        policies.append(row)
    calendar_days = _calendar_weekend_days(cur, company)
    overlay = mod["settings"].get("leave_setup") if isinstance(mod["settings"].get("leave_setup"), dict) else {}
    return {
        "ok": True,
        "module_key": "leave",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "policies": policies,
        "calendar_reference": {
            "weekend_days": calendar_days,
            "source": "setup_console_payroll_working_calendar",
            "setup_href": "/setup-console#classic-payroll-setup-calendar",
        },
        "required": {
            "leave_types_configured": len(policies) > 0,
            "eligibility_defaults_ok": all(p.get("eligibility_months") is not None for p in policies) if policies else False,
        },
        "optional": {
            "allow_negative_unpaid": bool(overlay.get("allow_negative_unpaid", False)),
            "require_attachment_for_sick": bool(overlay.get("require_attachment_for_sick", False)),
            "notice_days_default": int(overlay.get("notice_days_default") or 0),
        },
        "advanced": {
            "exclude_public_holidays": all(bool(p.get("exclude_public_holidays", True)) for p in policies) if policies else True,
            "lifecycle_gates_note": "Leave authority lifecycle gates remain platform-enforced.",
        },
        "ops_deep_link": "/dashboard?page=leave",
        "ownership": {"company_policy": "setup_console", "requests_balances": "leave_ops"},
        "setup_status": "ready" if policies and mod["enabled"] else ("inactive" if not mod["enabled"] else "needs_attention"),
        "summary_en": f"{len(policies)} leave type(s) · calendar from Payroll setup",
        "summary_ar": f"{len(policies)} نوع إجازة · التقويم من إعداد الرواتب",
    }


def patch_leave_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    policy_updates: list[dict[str, Any]] | None = None,
    optional: dict[str, Any] | None = None,
    sync_calendar: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    actions: list[dict[str, Any]] = []
    if sync_calendar:
        actions.append({"action": "sync_calendar", **sync_calendar_consumers(cur, company)})
    for upd in policy_updates or []:
        leave_type = str(upd.get("leave_type") or "").strip().lower()
        if leave_type not in LEAVE_TYPES:
            continue
        fields = []
        params: list[Any] = []
        for col, key, cast in (
            ("days_per_year", "days_per_year", float),
            ("eligibility_months", "eligibility_months", int),
            ("accrual_method", "accrual_method", str),
            ("allow_negative", "allow_negative", bool),
            ("exclude_public_holidays", "exclude_public_holidays", bool),
        ):
            if key in upd and upd.get(key) is not None:
                fields.append(f"{col}=%s")
                params.append(cast(upd.get(key)))
        if not fields:
            continue
        params.extend([company, leave_type, company, leave_type])
        cur.execute(
            f"""
            UPDATE leave_policies SET {', '.join(fields)}
            WHERE company_code=%s AND leave_type=%s
              AND version = (
                SELECT MAX(version) FROM leave_policies
                WHERE company_code=%s AND leave_type=%s
              )
            """,
            tuple(params),
        )
        actions.append({"action": "update_leave_policy", "leave_type": leave_type, "updated": cur.rowcount or 0})
    if optional is not None:
        overlay = {
            "allow_negative_unpaid": bool(optional.get("allow_negative_unpaid", False)),
            "require_attachment_for_sick": bool(optional.get("require_attachment_for_sick", False)),
            "notice_days_default": int(optional.get("notice_days_default") or 0),
            "updated_reason": str(reason).strip()[:200],
            "updated_by": actor_phone,
        }
        _save_module_settings(cur, company, "leave", {"leave_setup": overlay})
        actions.append({"action": "update_leave_overlay"})
    return {"ok": True, "actions": actions, "policy": get_leave_company_policy(cur, company)}


def get_attendance_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "attendance")
    overlay = mod["settings"].get("attendance_setup") if isinstance(mod["settings"].get("attendance_setup"), dict) else {}
    # Reference payroll attendance authority
    att_mode = None
    grace = overlay.get("lateness_grace_minutes")
    _sp(cur, "p3b_att_mode")
    try:
        import payroll_input_snapshot_p2 as p2

        att_mode = p2.resolve_attendance_payroll_mode(cur, company_code=company)
        _sp_release(cur, "p3b_att_mode")
    except Exception:
        _sp_rollback(cur, "p3b_att_mode")
    _sp(cur, "p3b_att_grace")
    try:
        cur.execute(
            """
            SELECT lateness_grace_minutes, attendance_payroll_mode
            FROM payroll_company_policy_versions
            WHERE company_code=%s AND status='approved'
            ORDER BY effective_from DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        if row:
            d = dict(row) if isinstance(row, dict) else {"lateness_grace_minutes": row[0], "attendance_payroll_mode": row[1]}
            if grace is None and d.get("lateness_grace_minutes") is not None:
                grace = d.get("lateness_grace_minutes")
            att_mode = att_mode or d.get("attendance_payroll_mode")
        _sp_release(cur, "p3b_att_grace")
    except Exception:
        _sp_rollback(cur, "p3b_att_grace")
    calendar_days = _calendar_weekend_days(cur, company)
    return {
        "ok": True,
        "module_key": "attendance",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "payroll_attendance_mode": att_mode,
            "payroll_setup_href": "/setup-console#classic-payroll-setup-attendance",
            "calendar_href": "/setup-console#classic-payroll-setup-calendar",
            "weekend_days": calendar_days,
        },
        "optional": {
            "lateness_grace_minutes": int(grace if grace is not None else 15),
            "require_clock_out": bool(overlay.get("require_clock_out", True)),
            "missing_punch_creates_exception": bool(overlay.get("missing_punch_creates_exception", True)),
            "correction_requires_approval": bool(overlay.get("correction_requires_approval", True)),
        },
        "advanced": {
            "location_restriction_note": "Device/site capture remains Capture Ops — not company Setup under freeze.",
        },
        "ops_deep_link": "/dashboard?page=attendance",
        "ownership": {
            "attendance_pay_mode": "setup_console_payroll",
            "attendance_ops_policy": "setup_console",
            "logs_corrections": "attendance_ops",
        },
        "setup_status": "ready" if mod["enabled"] and att_mode else ("inactive" if not mod["enabled"] else "needs_attention"),
        "summary_en": f"Pay impact via Payroll Setup · grace {int(grace if grace is not None else 15)} min",
        "summary_ar": f"أثر الأجر من إعداد الرواتب · سماحية {int(grace if grace is not None else 15)} د",
    }


def patch_attendance_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    optional: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    overlay = optional or {}
    saved = {
        "lateness_grace_minutes": max(0, min(120, int(overlay.get("lateness_grace_minutes") or 15))),
        "require_clock_out": bool(overlay.get("require_clock_out", True)),
        "missing_punch_creates_exception": bool(overlay.get("missing_punch_creates_exception", True)),
        "correction_requires_approval": bool(overlay.get("correction_requires_approval", True)),
        "updated_reason": str(reason).strip()[:200],
        "updated_by": actor_phone,
    }
    _save_module_settings(cur, company, "attendance", {"attendance_setup": saved})
    # Best-effort: stamp grace onto latest approved payroll policy metadata path if column exists
    try:
        cur.execute(
            """
            UPDATE payroll_company_policy_versions
            SET lateness_grace_minutes=%s
            WHERE company_code=%s AND status='approved'
              AND policy_version_id = (
                SELECT policy_version_id FROM payroll_company_policy_versions
                WHERE company_code=%s AND status='approved'
                ORDER BY effective_from DESC NULLS LAST, created_at DESC
                LIMIT 1
              )
            """,
            (saved["lateness_grace_minutes"], company, company),
        )
    except Exception:
        pass
    return {"ok": True, "actions": [{"action": "update_attendance_overlay"}], "policy": get_attendance_company_policy(cur, company)}


def get_shifts_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "shifts")
    overlay = mod["settings"].get("shifts_setup") if isinstance(mod["settings"].get("shifts_setup"), dict) else {}
    settings = {}
    _sp(cur, "p3b_sh")
    try:
        import shifts_authority_wave1 as sh

        settings = sh.get_shift_authority_settings(cur, company)
        _sp_release(cur, "p3b_sh")
    except Exception:
        _sp_rollback(cur, "p3b_sh")
        settings = {}
    calendar_days = _calendar_weekend_days(cur, company)
    rest_from_calendar = sorted({WEEKDAY_TO_INT[d] for d in calendar_days if d in WEEKDAY_TO_INT})
    return {
        "ok": True,
        "module_key": "shifts",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "shifts_enabled": bool(overlay.get("shifts_enabled", mod["enabled"])),
            "leave_conflict_mode": settings.get("leave_conflict_mode") or "require_ack",
            "calendar_rest_weekdays": rest_from_calendar,
            "calendar_href": "/setup-console#classic-payroll-setup-calendar",
            "rest_weekdays_source": "payroll_working_calendar",
        },
        "optional": {
            "allow_overnight": bool(settings.get("allow_overnight", True)),
            "publishing_requires_ack": bool(overlay.get("publishing_requires_ack", True)),
            "swap_requests_enabled": bool(overlay.get("swap_requests_enabled", False)),
        },
        "advanced": {
            "block_terminated": bool(settings.get("block_terminated", True)),
            "block_suspended": bool(settings.get("block_suspended", True)),
            "template_ownership": "shifts_ops",
            "template_note_en": "Shift templates and rosters stay in Shifts operations.",
        },
        "ops_deep_link": "/dashboard?page=shifts",
        "ownership": {
            "company_scheduling_policy": "setup_console",
            "templates_rosters_publish": "shifts_ops",
            "working_calendar": "setup_console_payroll",
        },
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"Leave conflict {settings.get('leave_conflict_mode') or 'require_ack'} · rest days from calendar",
        "summary_ar": f"تعارض الإجازة {settings.get('leave_conflict_mode') or 'require_ack'} · الراحة من التقويم",
    }


def patch_shifts_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
    optional: dict[str, Any] | None = None,
    sync_calendar: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    actions: list[dict[str, Any]] = []
    if sync_calendar:
        actions.append({"action": "sync_calendar", **sync_calendar_consumers(cur, company)})
    req = required or {}
    opt = optional or {}
    try:
        import shifts_authority_wave1 as sh

        sh.ensure_shifts_authority_wave1_schema(cur)
        sh.seed_shift_authority_settings(cur, company)
        mode = str(req.get("leave_conflict_mode") or "").strip().lower()
        if mode in {"block", "require_ack", "cancel_shift"}:
            cur.execute(
                "UPDATE shift_authority_settings SET leave_conflict_mode=%s, updated_at=now() WHERE company_code=%s",
                (mode, company),
            )
            actions.append({"action": "set_leave_conflict_mode", "mode": mode})
        if "allow_overnight" in opt:
            cur.execute(
                "UPDATE shift_authority_settings SET allow_overnight=%s, updated_at=now() WHERE company_code=%s",
                (bool(opt.get("allow_overnight")), company),
            )
            actions.append({"action": "set_allow_overnight"})
    except Exception as exc:
        return {"ok": False, "error": "shifts_settings_update_failed", "message": str(exc)[:200]}
    overlay = {
        "shifts_enabled": bool(req.get("shifts_enabled", True)),
        "publishing_requires_ack": bool(opt.get("publishing_requires_ack", True)),
        "swap_requests_enabled": bool(opt.get("swap_requests_enabled", False)),
        "updated_reason": str(reason).strip()[:200],
        "updated_by": actor_phone,
    }
    _save_module_settings(cur, company, "shifts", {"shifts_setup": overlay})
    actions.append({"action": "update_shifts_overlay"})
    return {"ok": True, "actions": actions, "policy": get_shifts_company_policy(cur, company)}


def get_documents_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    # Compliance module gates document requirements; documents is employee surface.
    mod = _module_row(cur, company, "compliance")
    overlay = mod["settings"].get("documents_setup") if isinstance(mod["settings"].get("documents_setup"), dict) else {}
    default_warnings = {
        "civil_id": 30,
        "passport": 60,
        "residence": 30,
        "work_permit": 30,
        "medical": 30,
    }
    warnings = dict(default_warnings)
    if isinstance(overlay.get("warning_days"), dict):
        for k, v in overlay["warning_days"].items():
            try:
                warnings[str(k)] = int(v)
            except Exception:
                pass
    required_types = overlay.get("required_document_types")
    if not isinstance(required_types, list) or not required_types:
        required_types = ["civil_id", "passport"]
    return {
        "ok": True,
        "module_key": "documents_compliance",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "required_document_types": required_types,
            "employee_surface": "documents",
            "no_separate_employee_compliance_module": True,
        },
        "optional": {
            "warning_days": warnings,
            "renewal_reminder_enabled": bool(overlay.get("renewal_reminder_enabled", True)),
        },
        "advanced": {
            "evidence_review_required": bool(overlay.get("evidence_review_required", True)),
            "ocr_owned_by_wathefni": True,
            "category_aware_seed": True,
        },
        "ops_deep_link": "/dashboard?page=compliance",
        "ownership": {
            "company_requirements": "setup_console",
            "uploads_reviews_renewals": "documents_compliance_ops",
            "extraction_ocr": "wathefni",
        },
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"{len(required_types)} required types · reminders {'on' if overlay.get('renewal_reminder_enabled', True) else 'off'}",
        "summary_ar": f"{len(required_types)} أنواع مطلوبة · التذكير {'تشغيل' if overlay.get('renewal_reminder_enabled', True) else 'إيقاف'}",
    }


def patch_documents_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
    optional: dict[str, Any] | None = None,
    advanced: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    opt = optional or {}
    adv = advanced or {}
    types = req.get("required_document_types")
    if isinstance(types, list):
        types = [str(t).strip().lower() for t in types if str(t).strip()]
    else:
        types = ["civil_id", "passport"]
    warnings = opt.get("warning_days") if isinstance(opt.get("warning_days"), dict) else {}
    clean_warnings = {}
    for k, v in warnings.items():
        try:
            clean_warnings[str(k)] = max(1, min(365, int(v)))
        except Exception:
            continue
    overlay = {
        "required_document_types": types,
        "warning_days": clean_warnings,
        "renewal_reminder_enabled": bool(opt.get("renewal_reminder_enabled", True)),
        "evidence_review_required": bool(adv.get("evidence_review_required", True)),
        "updated_reason": str(reason).strip()[:200],
        "updated_by": actor_phone,
    }
    _save_module_settings(cur, company, "compliance", {"documents_setup": overlay})
    return {"ok": True, "actions": [{"action": "update_documents_overlay"}], "policy": get_documents_company_policy(cur, company)}


def resolve_company_compliance_warning_days(cur: Any, company_code: str, document_type: str, row_warning: Any = None) -> int:
    """Company overlay → row → platform default."""
    if row_warning is not None:
        try:
            return int(row_warning)
        except Exception:
            pass
    pol = get_documents_company_policy(cur, company_code)
    warnings = ((pol.get("optional") or {}).get("warning_days") or {})
    if document_type in warnings:
        return int(warnings[document_type])
    # aliases
    if document_type in {"residency", "residency_iqama"} and "residence" in warnings:
        return int(warnings["residence"])
    return 30


def get_onboarding_company_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    mod = _module_row(cur, company, "onboarding")
    overlay = mod["settings"].get("onboarding_setup") if isinstance(mod["settings"].get("onboarding_setup"), dict) else {}
    template_id = "default_kuwait"
    try:
        cur.execute("SELECT metadata FROM companies WHERE company_code=%s LIMIT 1", (company,))
        row = cur.fetchone()
        meta = dict(row).get("metadata") if row else None
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if isinstance(meta, dict) and meta.get("onboarding_template"):
            template_id = str(meta.get("onboarding_template"))
    except Exception:
        pass
    if overlay.get("template_id"):
        template_id = str(overlay.get("template_id"))
    auto_start = bool(overlay.get("auto_seed_on_hire", True))
    try:
        import setup_console_policy_convergence as _conv

        auto_start = _conv.read_onboarding_auto_start(cur, company)
    except Exception:
        pass
    return {
        "ok": True,
        "module_key": "onboarding",
        "module_enabled": mod["enabled"],
        "inactive": not mod["enabled"],
        "required": {
            "template_id": template_id,
            "canonical_template_version": "2.0.0",
            "pins_historical_assignments": True,
            "note_en": "Changing template affects new assignments only — existing journeys stay pinned.",
            "note_ar": "تغيير القالب يؤثر على التعيينات الجديدة فقط — الرحلات الحالية تبقى مثبتة.",
        },
        "optional": {
            "default_due_offset_days": int(overlay.get("default_due_offset_days") or 7),
            "hr_owner_default": str(overlay.get("hr_owner_default") or "hr"),
            "employee_actions_enabled": bool(overlay.get("employee_actions_enabled", True)),
        },
        "advanced": {
            "department_specific_requirements": bool(overlay.get("department_specific_requirements", False)),
            "auto_seed_on_hire": auto_start,
        },
        "canonical_auto_start": {
            "source": "company_settings.onboarding.auto_start_on_hire",
            "auto_start_on_hire": auto_start,
        },
        "ops_deep_link": "/dashboard?page=onboarding",
        "ownership": {
            "company_template_policy": "setup_console",
            "active_journeys": "onboarding_ops",
            "lifecycle_projection": "platform_wave2a",
        },
        "setup_status": "ready" if mod["enabled"] else "inactive",
        "summary_en": f"Template {template_id} · new hires only when changed",
        "summary_ar": f"القالب {template_id} · الموظفون الجدد فقط عند التغيير",
    }


def patch_onboarding_company_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    required: dict[str, Any] | None = None,
    optional: dict[str, Any] | None = None,
    advanced: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    req = required or {}
    opt = optional or {}
    adv = advanced or {}
    template_id = str(req.get("template_id") or "default_kuwait").strip().lower() or "default_kuwait"
    overlay = {
        "template_id": template_id,
        "default_due_offset_days": max(0, min(90, int(opt.get("default_due_offset_days") or 7))),
        "hr_owner_default": str(opt.get("hr_owner_default") or "hr")[:40],
        "employee_actions_enabled": bool(opt.get("employee_actions_enabled", True)),
        "department_specific_requirements": bool(adv.get("department_specific_requirements", False)),
        "auto_seed_on_hire": bool(adv.get("auto_seed_on_hire", True)),
        "updated_reason": str(reason).strip()[:200],
        "updated_by": actor_phone,
    }
    _save_module_settings(cur, company, "onboarding", {"onboarding_setup": overlay})
    try:
        import setup_console_policy_convergence as _conv

        _conv.sync_onboarding_auto_start(
            cur,
            company,
            auto_start=bool(overlay.get("auto_seed_on_hire", True)),
            actor_phone=actor_phone,
            reason=reason,
        )
    except Exception:
        pass
    # Persist company metadata bind for resolve_onboarding_template (new seeds only).
    try:
        cur.execute("SELECT metadata FROM companies WHERE company_code=%s LIMIT 1 FOR UPDATE", (company,))
        row = cur.fetchone()
        meta = dict(row).get("metadata") if row else {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta["onboarding_template"] = template_id
        cur.execute(
            "UPDATE companies SET metadata=%s::jsonb WHERE company_code=%s",
            (json.dumps(meta), company),
        )
    except Exception:
        pass
    return {
        "ok": True,
        "actions": [{"action": "update_onboarding_overlay", "historical_rewritten": False}],
        "policy": get_onboarding_company_policy(cur, company),
    }


def get_all_module_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "company_code": company,
        "leave": _isolate_policy(cur, "p3b_leave", lambda: get_leave_company_policy(cur, company)),
        "attendance": _isolate_policy(cur, "p3b_att", lambda: get_attendance_company_policy(cur, company)),
        "shifts": _isolate_policy(cur, "p3b_shifts", lambda: get_shifts_company_policy(cur, company)),
        "documents": _isolate_policy(cur, "p3b_docs", lambda: get_documents_company_policy(cur, company)),
        "onboarding": _isolate_policy(cur, "p3b_onb", lambda: get_onboarding_company_policy(cur, company)),
        "cross_module": {
            "working_calendar": "/setup-console#classic-payroll-setup-calendar",
            "attendance_pay": "/setup-console#classic-payroll-setup-attendance",
            "documents_employee_surface": "documents",
            "onboarding_lifecycle": "wave2a_projection_unchanged",
        },
    }


def patch_module_policy(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor_phone: str | None,
    reason: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    key = str(module_key or "").strip().lower()
    if key == "leave":
        return patch_leave_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            policy_updates=payload.get("policy_updates"),
            optional=payload.get("optional"),
            sync_calendar=bool(payload.get("sync_calendar", True)),
        )
    if key == "attendance":
        return patch_attendance_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            optional=payload.get("optional"),
        )
    if key == "shifts":
        return patch_shifts_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
            optional=payload.get("optional"),
            sync_calendar=bool(payload.get("sync_calendar", True)),
        )
    if key in {"documents", "compliance", "documents_compliance"}:
        return patch_documents_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
            optional=payload.get("optional"),
            advanced=payload.get("advanced"),
        )
    if key == "onboarding":
        return patch_onboarding_company_policy(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            reason=reason,
            required=payload.get("required"),
            optional=payload.get("optional"),
            advanced=payload.get("advanced"),
        )
    return {"ok": False, "error": "unknown_module_key", "allowed": ["leave", "attendance", "shifts", "documents", "onboarding"]}
