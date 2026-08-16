"""Setup Console Phase 2A — company payroll setup experience.

Composes existing Wave1 / P2 / P3 / P5 / P6 mutators. Does not change
calculation, sealing, or money-authority semantics.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import payroll_authority_mode_a_p5 as p5
import payroll_authority_production_p6 as p6
import payroll_authority_wave1 as pyw1
import payroll_components_policy_p3 as p3
import payroll_input_snapshot_p2 as p2

PHASE = "setup_console_phase2a"
PHASE_3A = "setup_console_phase3a"
CONTRACT_VERSION = "payroll_setup_console_contract_v1"

# Product-facing attendance choices → canonical runtime enums.
ATTENDANCE_UX = {
    "informational": {
        "runtime": "informational",
        "label_en": "Informational only (no pay impact)",
        "label_ar": "للمعلومة فقط (بدون أثر على الأجر)",
    },
    "attendance_affects_pay": {
        "runtime": "required",
        "label_en": "Attendance can affect pay",
        "label_ar": "الحضور قد يؤثر على الأجر",
    },
    "ignored": {
        "runtime": "ignored",
        "label_en": "Ignore attendance for pay",
        "label_ar": "تجاهل الحضور في الأجر",
    },
}

RUNTIME_TO_UX = {
    "informational": "informational",
    "required": "attendance_affects_pay",
    "ignored": "ignored",
}

FIELD_DEEP_LINKS = {
    "payroll_mode": "/setup-console#classic-payroll-setup-mode",
    "attendance_payroll_mode": "/setup-console#classic-payroll-setup-attendance",
    "company_payroll_policy": "/setup-console#classic-payroll-setup-policy",
    "salary_component_structure": "/dashboard?page=employees",
    "approval_sod_chain": "/setup-console#classic-payroll-setup-approval",
    "kuwait_statutory_baseline": "/setup-console#classic-payroll-setup-statutory",
    "mode_a_entitlement": "/setup-console#classic-payroll-setup-authority",
    "working_calendar": "/setup-console#classic-payroll-setup-calendar",
    "employee_statutory_classifications": "/setup-console#classic-payroll-setup-statutory-inputs",
    "pifss_wage_bases": "/setup-console#classic-payroll-setup-statutory-inputs",
    "variance_thresholds": "/setup-console#classic-payroll-setup-variance",
    "employee_allowlist": "/setup-console#classic-payroll-setup-allowlist",
}


def _statutory_baseline_label() -> str:
    try:
        import payroll_statutory_baseline_p4b as p4b

        return str(getattr(p4b, "POLICY_VERSION", None) or "KW_PUBLIC_BASELINE_v1.0.0")
    except Exception:
        return "KW_PUBLIC_BASELINE_v1.0.0"


def ensure_payroll_setup_extras_schema(cur: Any) -> None:
    """Additive company setup extras (frequency / cut-off) — not calc fields."""
    pyw1.ensure_payroll_wave1_schema(cur)
    cur.execute(
        """
        ALTER TABLE payroll_company_settings
          ADD COLUMN IF NOT EXISTS setup_extras jsonb NOT NULL DEFAULT '{}'::jsonb
        """
    )


def _json_safe(value: Any) -> Any:
    return pyw1._json_safe(value) if hasattr(pyw1, "_json_safe") else value


def _payroll_module_enabled(cur: Any, company: str) -> bool:
    cur.execute(
        """
        SELECT enabled FROM company_modules
        WHERE company_code=%s AND module_key='payroll'
        LIMIT 1
        """,
        (company,),
    )
    row = cur.fetchone()
    if not row:
        return False
    if isinstance(row, dict):
        return bool(row.get("enabled"))
    return bool(row[0])


def _setup_extras(settings: dict[str, Any]) -> dict[str, Any]:
    try:
        import setup_console_payroll_phase3a as p3a

        return p3a.parse_setup_extras(settings)
    except Exception:
        raw = settings.get("setup_extras") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "payroll_frequency": str(raw.get("payroll_frequency") or "monthly"),
            "cutoff_day": raw.get("cutoff_day"),
            "period_end_rule": str(raw.get("period_end_rule") or "calendar_month"),
            "working_calendar_note": str(raw.get("working_calendar_note") or ""),
        }


def _human_readiness_state(*, readiness: dict[str, Any], entitlement_state: str, payroll_mode: str) -> dict[str, Any]:
    """Customer-facing readiness — no Wave/P6 jargon."""
    blockers = list(readiness.get("blockers") or readiness.get("issues") or [])
    blocked = [i for i in blockers if str(i.get("severity") or "") == "blocked"]
    ok = bool(readiness.get("ok"))
    ent = str(entitlement_state or p6.STATE_DISABLED).lower()
    mode = str(payroll_mode or "").lower()

    if mode == "external":
        # Mode B: "ready" means company chose external and module can operate externally.
        if not blocked:
            state = "ready_external"
            label_en = "Ready for external payroll"
            label_ar = "جاهز للرواتب الخارجية"
        else:
            state = "needs_attention"
            label_en = "Needs attention"
            label_ar = "يحتاج انتباهاً"
    elif not ok or blocked:
        # Distinguish empty/incomplete vs has blockers
        if not settings_configured_enough(readiness):
            state = "setup_incomplete"
            label_en = "Setup incomplete"
            label_ar = "الإعداد غير مكتمل"
        else:
            state = "needs_attention"
            label_en = "Needs attention"
            label_ar = "يحتاج انتباهاً"
    elif ent in p6.AUTHORITATIVE_STATES:
        state = "ready_authoritative"
        label_en = "Ready for authoritative payroll"
        label_ar = "جاهز للرواتب السلطوية"
    elif ent == p6.STATE_PREVIEW:
        state = "ready_preview"
        label_en = "Ready for preview"
        label_ar = "جاهز للمعاينة"
    else:
        state = "ready_preview"
        label_en = "Ready for preview"
        label_ar = "جاهز للمعاينة"

    return {
        "state": state,
        "label_en": label_en,
        "label_ar": label_ar,
        "ok": ok and not blocked,
    }


def settings_configured_enough(readiness: dict[str, Any]) -> bool:
    settings = readiness.get("settings") or {}
    return bool(settings.get("payroll_mode") and settings.get("attendance_payroll_mode"))


def enrich_issues(issues: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in issues or []:
        field = str(issue.get("field") or "")
        item = dict(issue)
        # Never surface raw codes as primary label — keep for tests only.
        item["fix_href"] = FIELD_DEEP_LINKS.get(field) or "/setup-console#classic-payroll-setup"
        # Soften internal how_to_fix wording for customers when present.
        how = str(item.get("how_to_fix") or "")
        how = how.replace("P3 ", "").replace("P4B ", "").replace("Mode A ", "").replace("Mode B ", "")
        item["how_to_fix"] = how
        out.append(item)
    return out


def get_payroll_setup(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_setup_extras_schema(cur)
    company = (company_code or "").upper()
    module_on = _payroll_module_enabled(cur, company)
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    extras = _setup_extras(settings)
    att_runtime = None
    try:
        att_runtime = p2.resolve_attendance_payroll_mode(cur, company_code=company)
    except Exception:
        att_runtime = settings.get("attendance_payroll_mode")
    att_ux = RUNTIME_TO_UX.get(str(att_runtime or "").lower(), "informational")

    finalize = p5.get_company_finalize_policy(cur, company_code=company)
    finalize_persisted = not bool((finalize.get("metadata") or {}).get("default"))

    entitlement = p6.get_company_entitlement(cur, company_code=company)
    readiness = p6.validate_payroll_readiness(cur, company_code=company)
    human = _human_readiness_state(
        readiness=readiness,
        entitlement_state=str(entitlement.get("entitlement_state") or p6.STATE_DISABLED),
        payroll_mode=str(settings.get("payroll_mode") or ""),
    )

    # Active approved policy summary
    cur.execute(
        """
        SELECT policy_version_id::text AS policy_version_id,
               version_number, status, effective_from::text AS effective_from,
               attendance_payroll_mode, lateness_money_enabled, absence_money_enabled,
               unpaid_leave_money_enabled, ot_money_enabled
        FROM payroll_company_policy_versions
        WHERE company_code=%s AND status='approved'
        ORDER BY effective_from DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (company,),
    )
    policy_row = cur.fetchone()
    policy_d: dict[str, Any] | None
    if policy_row is None:
        policy_d = None
    elif isinstance(policy_row, dict):
        policy_d = dict(policy_row)
    else:
        cols = [d[0] for d in (cur.description or [])]
        policy_d = dict(zip(cols, policy_row))

    mode = str(settings.get("payroll_mode") or "native")
    contracts_n = readiness.get("approved_compensation_contracts")
    # readiness payload nests contracts under top-level from validate_payroll_readiness return
    if contracts_n is None:
        # validate_payroll_readiness returns approved_compensation_contracts at top level via **payload? 
        # Looking at return: it does NOT spread payload settings contracts — check again.
        contracts_n = 0
    # Actually validate returns fingerprint/entitlement/setup_contract and issues — contracts are inside
    # the persisted payload only. Re-query:
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND status='approved'",
        (company,),
    )
    crow = cur.fetchone()
    if crow is None:
        contracts_n = 0
    elif isinstance(crow, dict):
        contracts_n = int(crow.get("n") or 0)
    else:
        contracts_n = int(crow[0] or 0)

    return_payload = {
        "ok": True,
        "phase": PHASE_3A,
        "company_code": company,
        "module_enabled": module_on,
        "payroll_mode": mode,
        "product_mode": "wathefni" if mode in ("native", "parallel_shadow") else "external",
        "attendance_payroll_mode": att_runtime,
        "attendance_ux": att_ux,
        "attendance_choices": [
            {"key": k, "label_en": v["label_en"], "label_ar": v["label_ar"]} for k, v in ATTENDANCE_UX.items()
        ],
        "setup_extras": extras,
        "finalize_policy": {
            "persisted": finalize_persisted,
            "require_review_step": bool(finalize.get("require_review_step", True)),
            "require_distinct_approver": bool(finalize.get("require_distinct_approver", True)),
            "allow_approver_as_finalizer": bool(finalize.get("allow_approver_as_finalizer", True)),
            "enterprise_sod_strict": bool(finalize.get("require_distinct_finalizer", True))
            and not bool(finalize.get("allow_approver_as_finalizer", True)),
        },
        "entitlement": {
            "state": str(entitlement.get("entitlement_state") or p6.STATE_DISABLED),
            "mode_a_opt_in": bool(entitlement.get("mode_a_opt_in")),
        },
        "approved_policy": policy_d,
        "approved_compensation_contracts": contracts_n,
        "readiness": {
            **human,
            "fingerprint": readiness.get("fingerprint"),
            "issues": enrich_issues(readiness.get("issues") or readiness.get("blockers")),
            "blockers": enrich_issues(readiness.get("blockers") or []),
            "raw_status": readiness.get("readiness_status"),
        },
        "wathefni_owned": {
            "kuwait_statutory_baseline_version": _statutory_baseline_label(),
            "calculation_engine": "wathefni",
            "authority_sealing_rules": "wathefni",
            "statutory_provenance": "wathefni",
            "payment_processing": "disabled",
            "company_editable": False,
        },
        "setup_contract": p6.setup_console_schema_contract(),
        "ops_deep_link": "/dashboard?page=payroll",
        "ownership": {
            "company_payroll_setup": "setup_console",
            "payroll_runs": "operational_payroll",
        },
    }
    try:
        import setup_console_payroll_phase3a as p3a

        return_payload = p3a.enrich_payroll_setup_phase3a(cur, company_code=company, base=return_payload)
        # Refresh human readiness labels after Phase 3A blockers merge.
        return_payload["readiness"] = {
            **_human_readiness_state(
                readiness={
                    "ok": return_payload["readiness"].get("ok"),
                    "blockers": return_payload["readiness"].get("blockers") or [],
                    "issues": return_payload["readiness"].get("issues") or [],
                    "settings": {"payroll_mode": mode, "attendance_payroll_mode": att_runtime},
                },
                entitlement_state=str(entitlement.get("entitlement_state") or p6.STATE_DISABLED),
                payroll_mode=mode,
            ),
            **{k: v for k, v in (return_payload.get("readiness") or {}).items() if k not in {"state", "label_en", "label_ar", "ok"}},
            "ok": (return_payload.get("readiness") or {}).get("ok"),
            "issues": enrich_issues((return_payload.get("readiness") or {}).get("issues")),
            "blockers": enrich_issues((return_payload.get("readiness") or {}).get("blockers")),
            "attention": enrich_issues((return_payload.get("readiness") or {}).get("attention")),
        }
    except Exception:
        pass
    return return_payload


def _update_setup_extras(
    cur: Any,
    *,
    company: str,
    extras_patch: dict[str, Any],
    actor_phone: str | None,
) -> dict[str, Any]:
    ensure_payroll_setup_extras_schema(cur)
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    current = _setup_extras(settings)
    if "payroll_frequency" in extras_patch and extras_patch["payroll_frequency"] is not None:
        current["payroll_frequency"] = str(extras_patch["payroll_frequency"]).strip().lower() or "monthly"
    if "cutoff_day" in extras_patch:
        day = extras_patch["cutoff_day"]
        if day is None or day == "":
            current["cutoff_day"] = None
        else:
            day_i = int(day)
            if day_i < 1 or day_i > 28:
                return {"ok": False, "error": "invalid_cutoff_day", "message_en": "Cut-off day must be between 1 and 28."}
            current["cutoff_day"] = day_i
    if "period_end_rule" in extras_patch and extras_patch["period_end_rule"] is not None:
        current["period_end_rule"] = str(extras_patch["period_end_rule"]).strip() or "calendar_month"
    if "working_calendar_note" in extras_patch and extras_patch["working_calendar_note"] is not None:
        current["working_calendar_note"] = str(extras_patch["working_calendar_note"])[:500]
    if "weekend_days" in extras_patch and extras_patch["weekend_days"] is not None:
        try:
            import setup_console_payroll_phase3a as p3a

            weekend = p3a.normalize_weekend_days(extras_patch["weekend_days"])
            current["weekend_days"] = weekend
            current["working_days"] = p3a.working_days_from_weekend(weekend)
            current["calendar_configured"] = bool(weekend)
        except Exception:
            current["weekend_days"] = extras_patch["weekend_days"]
            current["calendar_configured"] = True
    if extras_patch.get("calendar_configured") is True:
        current["calendar_configured"] = True
    if "use_wathefni_public_holiday_pack" in extras_patch:
        current["use_wathefni_public_holiday_pack"] = bool(extras_patch.get("use_wathefni_public_holiday_pack"))
    cur.execute(
        """
        UPDATE payroll_company_settings
        SET setup_extras=%s::jsonb, updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s
        RETURNING setup_extras
        """,
        (json.dumps(current), pyw1.digits_phone(actor_phone), company),
    )
    return {"ok": True, "setup_extras": current}


def patch_payroll_setup(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    reason: str,
    payroll_mode: str | None = None,
    attendance_ux: str | None = None,
    apply_sme_policy: bool = False,
    lateness_money_enabled: bool | None = None,
    absence_money_enabled: bool | None = None,
    unpaid_leave_money_enabled: bool | None = None,
    ot_money_enabled: bool | None = None,
    require_review_step: bool | None = None,
    require_distinct_approver: bool | None = None,
    allow_approver_as_finalizer: bool | None = None,
    enterprise_sod_strict: bool | None = None,
    entitlement_state: str | None = None,
    setup_extras: dict[str, Any] | None = None,
    apply_sme_defaults: bool = False,
    # Phase 3A
    weekend_days: list[str] | None = None,
    seed_kuwait_holidays: bool = False,
    holiday_upsert: dict[str, Any] | None = None,
    holiday_delete_date: str | None = None,
    variance_policy: dict[str, Any] | None = None,
    allowlist_add: list[str] | None = None,
    allowlist_revoke: list[str] | None = None,
    statutory_upsert: dict[str, Any] | None = None,
    confirm_authoritative: bool = False,
) -> dict[str, Any]:
    """Apply company payroll setup changes. Audited. Never rewrites sealed history."""
    if not reason or not str(reason).strip():
        return {
            "ok": False,
            "error": "audit_reason_required",
            "message_en": "A reason is required for payroll setup changes.",
            "message_ar": "يلزم ذكر سبب لتغيير إعداد الرواتب.",
        }
    ensure_payroll_setup_extras_schema(cur)
    company = (company_code or "").upper()
    module_on = _payroll_module_enabled(cur, company)
    actions: list[dict[str, Any]] = []
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    previous_mode = str(settings.get("payroll_mode") or "")

    if apply_sme_defaults:
        payroll_mode = payroll_mode or "native"
        attendance_ux = attendance_ux or "informational"
        apply_sme_policy = True
        require_review_step = True if require_review_step is None else require_review_step
        require_distinct_approver = True if require_distinct_approver is None else require_distinct_approver
        allow_approver_as_finalizer = True if allow_approver_as_finalizer is None else allow_approver_as_finalizer
        if entitlement_state is None and module_on:
            entitlement_state = p6.STATE_PREVIEW
        setup_extras = {
            **(setup_extras or {}),
            "payroll_frequency": (setup_extras or {}).get("payroll_frequency") or "monthly",
            "period_end_rule": (setup_extras or {}).get("period_end_rule") or "calendar_month",
            "weekend_days": (setup_extras or {}).get("weekend_days") or weekend_days or ["fri", "sat"],
            "calendar_configured": True,
        }
        weekend_days = weekend_days or ["fri", "sat"]
        seed_kuwait_holidays = True

    # --- Mode switch (guarded) ---
    if payroll_mode is not None:
        mode_n = str(payroll_mode).strip().lower()
        if mode_n not in pyw1.PAYROLL_MODES:
            return {"ok": False, "error": "invalid_payroll_mode", "allowed": list(pyw1.PAYROLL_MODES)}
        ent = p6.get_company_entitlement(cur, company_code=company)
        ent_state = str(ent.get("entitlement_state") or p6.STATE_DISABLED)
        if previous_mode and previous_mode != mode_n:
            if ent_state in p6.AUTHORITATIVE_STATES and mode_n == "external":
                return {
                    "ok": False,
                    "error": "mode_switch_blocked_authoritative",
                    "message_en": "Turn off Wathefni authoritative payroll before switching to external payroll. Existing sealed runs stay unchanged.",
                    "message_ar": "أوقف سلطة وظفني السلطوية قبل التحويل إلى الرواتب الخارجية. التشغيلات المختومة سابقاً تبقى كما هي.",
                }
            if mode_n == "external" and ent_state == p6.STATE_PREVIEW:
                # Auto-disable Mode A entitlement when moving to external (audited).
                dis = p6.set_company_mode_a_entitlement(
                    cur,
                    company_code=company,
                    entitlement_state=p6.STATE_DISABLED,
                    actor_phone=actor_phone,
                    reason=f"{reason.strip()} · auto-disable on external mode switch",
                    require_readiness=False,
                )
                actions.append({"action": "entitlement_disabled_on_mode_switch", "result_ok": bool(dis.get("ok"))})
        mode_res = pyw1.set_payroll_mode(
            cur,
            company_code=company,
            mode=mode_n,
            actor_phone=actor_phone,
            reason=reason,
        )
        if not mode_res.get("ok"):
            return mode_res
        actions.append(
            {
                "action": "set_payroll_mode",
                "from": previous_mode,
                "to": mode_n,
                "audited": True,
            }
        )

    # --- Attendance ---
    runtime_att = None
    if attendance_ux is not None:
        ux = str(attendance_ux).strip().lower()
        if ux not in ATTENDANCE_UX:
            return {"ok": False, "error": "invalid_attendance_ux", "allowed": sorted(ATTENDANCE_UX.keys())}
        runtime_att = ATTENDANCE_UX[ux]["runtime"]
        att_res = p2.set_attendance_payroll_mode(
            cur,
            company_code=company,
            mode=runtime_att,
            actor_phone=actor_phone,
            reason=reason,
        )
        if not att_res.get("ok"):
            return att_res
        actions.append({"action": "set_attendance_payroll_mode", "mode": runtime_att})

    # --- Company policy version (P3) ---
    if apply_sme_policy or any(
        v is not None
        for v in (
            lateness_money_enabled,
            absence_money_enabled,
            unpaid_leave_money_enabled,
            ot_money_enabled,
            attendance_ux,
        )
    ):
        if runtime_att is None:
            try:
                runtime_att = p2.resolve_attendance_payroll_mode(cur, company_code=company) or "informational"
            except Exception:
                runtime_att = "informational"
        # Defaults for informational SME: no money flags
        lateness = False if lateness_money_enabled is None else bool(lateness_money_enabled)
        absence = False if absence_money_enabled is None else bool(absence_money_enabled)
        unpaid = False if unpaid_leave_money_enabled is None else bool(unpaid_leave_money_enabled)
        ot = False if ot_money_enabled is None else bool(ot_money_enabled)
        if runtime_att == "informational" and (apply_sme_policy or attendance_ux is not None):
            if lateness_money_enabled is None:
                lateness = False
            if absence_money_enabled is None:
                absence = False
            if unpaid_leave_money_enabled is None:
                unpaid = False
            if ot_money_enabled is None:
                ot = False
        elif runtime_att == "required" and apply_sme_policy:
            # Attendance-driven: allow unpaid/absence money; OT stays off (Wathefni rates).
            absence = True if absence_money_enabled is None else bool(absence_money_enabled)
            unpaid = True if unpaid_leave_money_enabled is None else bool(unpaid_leave_money_enabled)
            lateness = False if lateness_money_enabled is None else bool(lateness_money_enabled)
            ot = False
        pol = p3.create_policy_version(
            cur,
            company_code=company,
            effective_from=date.today(),
            actor_phone=actor_phone,
            reason=reason,
            attendance_payroll_mode=str(runtime_att),
            lateness_money_enabled=lateness,
            absence_money_enabled=absence,
            unpaid_leave_money_enabled=unpaid,
            ot_money_enabled=ot,
            approve=True,
        )
        if not pol.get("ok"):
            return pol
        actions.append(
            {
                "action": "create_approved_company_policy",
                "policy_version_id": (pol.get("policy") or {}).get("policy_version_id"),
            }
        )

    # --- Finalize / SOD ---
    if any(
        v is not None
        for v in (require_review_step, require_distinct_approver, allow_approver_as_finalizer, enterprise_sod_strict, apply_sme_defaults)
    ):
        current = p5.get_company_finalize_policy(cur, company_code=company)
        rev = bool(current.get("require_review_step", True)) if require_review_step is None else bool(require_review_step)
        dist_appr = (
            bool(current.get("require_distinct_approver", True))
            if require_distinct_approver is None
            else bool(require_distinct_approver)
        )
        allow_fin = (
            bool(current.get("allow_approver_as_finalizer", True))
            if allow_approver_as_finalizer is None
            else bool(allow_approver_as_finalizer)
        )
        if enterprise_sod_strict is True:
            # Approver ≠ finalizer
            allow_fin = False
            dist_appr = True
            rev = True
        elif enterprise_sod_strict is False and allow_approver_as_finalizer is None and not apply_sme_defaults:
            allow_fin = True
        fin = p5.upsert_company_finalize_policy(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            reason=reason,
            require_review_step=rev,
            require_distinct_reviewer=True,
            require_distinct_approver=dist_appr,
            require_distinct_finalizer=True,
            allow_approver_as_finalizer=allow_fin,
        )
        if not fin.get("ok"):
            return fin
        actions.append({"action": "upsert_finalize_policy", "enterprise_sod_strict": enterprise_sod_strict is True})

    # --- Setup extras (frequency / cut-off) ---
    if setup_extras is not None:
        ex = _update_setup_extras(cur, company=company, extras_patch=setup_extras, actor_phone=actor_phone)
        if not ex.get("ok"):
            return ex
        actions.append({"action": "update_setup_extras", "setup_extras": ex.get("setup_extras")})

    # --- Phase 3A: working calendar / holidays / variance / allowlist / statutory ---
    try:
        import setup_console_payroll_phase3a as p3a

        if weekend_days is not None or seed_kuwait_holidays:
            cal = p3a.apply_working_calendar(
                cur,
                company_code=company,
                actor_phone=actor_phone,
                weekend_days=weekend_days,
                working_calendar_note=(setup_extras or {}).get("working_calendar_note") if setup_extras else None,
                seed_kuwait_holidays=bool(seed_kuwait_holidays),
            )
            if not cal.get("ok"):
                return cal
            actions.append({"action": "apply_working_calendar", "weekend_days": cal.get("setup_extras", {}).get("weekend_days")})
        if holiday_upsert and holiday_upsert.get("holiday_date"):
            hol = p3a.upsert_company_holiday(
                cur,
                company_code=company,
                holiday_date=str(holiday_upsert.get("holiday_date")),
                name=str(holiday_upsert.get("name") or "Company holiday"),
                actor_phone=actor_phone,
            )
            actions.append({"action": "upsert_holiday", "ok": hol.get("ok")})
        if holiday_delete_date:
            p3a.delete_company_holiday(cur, company_code=company, holiday_date=holiday_delete_date)
            actions.append({"action": "delete_holiday", "holiday_date": holiday_delete_date})
        if variance_policy is not None:
            var = p6.upsert_variance_policy(
                cur,
                company_code=company,
                actor_phone=actor_phone,
                reason=reason,
                gross_delta_abs=variance_policy.get("gross_delta_abs"),
                net_delta_abs=variance_policy.get("net_delta_abs"),
                gross_delta_pct=variance_policy.get("gross_delta_pct"),
                net_delta_pct=variance_policy.get("net_delta_pct"),
            )
            if not var.get("ok"):
                return var
            actions.append({"action": "upsert_variance_policy", "advisory_only": True})
        for key in allowlist_add or []:
            add = p6.add_employee_allowlist(
                cur,
                company_code=company,
                employee_key=str(key),
                actor_phone=actor_phone,
                reason=reason,
            )
            actions.append({"action": "allowlist_add", "employee_key": key, "ok": add.get("ok")})
        for key in allowlist_revoke or []:
            rev = p3a.revoke_employee_allowlist(
                cur,
                company_code=company,
                employee_key=str(key),
                actor_phone=actor_phone,
                reason=reason,
            )
            actions.append({"action": "allowlist_revoke", "employee_key": key, "ok": rev.get("ok")})
        if statutory_upsert and statutory_upsert.get("employee_key"):
            st = p3a.upsert_employee_statutory_inputs(
                cur,
                company_code=company,
                employee_key=str(statutory_upsert.get("employee_key")),
                actor_phone=actor_phone,
                employee_category=statutory_upsert.get("employee_category"),
                pifss_wage_by_fund=statutory_upsert.get("pifss_wage_by_fund"),
                reason=reason,
            )
            if not st.get("ok"):
                return st
            actions.append({"action": "statutory_upsert", "employee_key": statutory_upsert.get("employee_key")})
    except Exception as exc:
        return {"ok": False, "error": "phase3a_apply_failed", "message": str(exc)[:300]}

    # --- Entitlement / authority opt-in ---
    if entitlement_state is not None:
        target_ent = str(entitlement_state).strip().lower()
        prev_ent = str((p6.get_company_entitlement(cur, company_code=company) or {}).get("entitlement_state") or p6.STATE_DISABLED)
        if target_ent == p6.STATE_AUTHORITATIVE and prev_ent != p6.STATE_AUTHORITATIVE and not confirm_authoritative:
            return {
                "ok": False,
                "error": "confirm_authoritative_required",
                "message_en": "Confirm full authoritative payroll carefully. Existing finalized payroll history will not be rewritten.",
                "message_ar": "أكد تفعيل الرواتب السلطوية بالكامل بحذر. السجلات المختومة سابقاً لن تُعاد كتابتها.",
                "requires_confirm_authoritative": True,
            }
        if not module_on and target_ent in (p6.STATE_PREVIEW, *p6.AUTHORITATIVE_STATES):
            return {
                "ok": False,
                "error": "payroll_module_disabled",
                "message_en": "Enable the Payroll module before activating Wathefni payroll authority.",
                "message_ar": "فعّل وحدة الرواتب قبل تفعيل سلطة رواتب وظفني.",
                "fix_href": "/setup-console#classic-modules",
            }
        settings_now = pyw1.ensure_company_settings(cur, company_code=company)
        if str(settings_now.get("payroll_mode")) == "external" and target_ent in p6.AUTHORITATIVE_STATES | {p6.STATE_PREVIEW}:
            return {
                "ok": False,
                "error": "external_mode_no_wathefni_authority",
                "message_en": "External payroll companies keep money authority outside Wathefni. Switch to Wathefni Payroll to enable preview or authoritative runs.",
                "message_ar": "شركات الرواتب الخارجية تبقي سلطة المال خارج وظفني. انتقل إلى رواتب وظفني لتفعيل المعاينة أو السلطة.",
            }
        # Authoritative transitions require Phase 3A calendar (+ statutory when already authoritative path).
        ent_res = p6.set_company_mode_a_entitlement(
            cur,
            company_code=company,
            entitlement_state=target_ent,
            actor_phone=actor_phone,
            reason=reason,
            require_readiness=True,
        )
        if not ent_res.get("ok"):
            # Surface readiness blockers in customer form
            readiness = ent_res.get("readiness") or p6.validate_payroll_readiness(cur, company_code=company)
            return {
                **ent_res,
                "readiness": {
                    **_human_readiness_state(
                        readiness=readiness,
                        entitlement_state=str(entitlement_state),
                        payroll_mode=str(settings_now.get("payroll_mode") or ""),
                    ),
                    "issues": enrich_issues(readiness.get("issues") or []),
                    "blockers": enrich_issues(readiness.get("blockers") or []),
                },
            }
        actions.append(
            {
                "action": "set_entitlement",
                "state": entitlement_state,
                "from": prev_ent,
                "history_rewritten": False,
                "audited": True,
            }
        )

    snapshot = get_payroll_setup(cur, company_code=company)
    return {
        "ok": True,
        "actions": actions,
        "setup": snapshot,
        "mode_switch_audited": any(a.get("action") == "set_payroll_mode" and a.get("from") != a.get("to") for a in actions),
    }
