"""Setup Console Wave A — Launch Readiness authority.

Honest purchased / configured / blocked / live states for WATHEFNI.
Console toggles never override freezes, env gates, allowlists, or SYNTHETIC_ONLY.

Operator-facing copy is plain language. Technical gate keys stay in evidence only.
"""

from __future__ import annotations

import os
from typing import Any

import module_catalog as modules

WAVE_A_VERSION = "1.0.0"
WAVE_A_CONTRACT = "launch_readiness_authority_v1"
ALLOWED_COMPANY = "WATHEFNI"

HONEST_STATES = (
    "not_purchased",
    "setup_required",
    "blocked",
    "ready_for_canary",
    "live_controlled",
    "paused",
)

STAGES: tuple[dict[str, str], ...] = (
    {"key": "company_basics", "label_en": "Company basics", "label_ar": "أساسيات الشركة"},
    {"key": "modules", "label_en": "Modules", "label_ar": "الوحدات"},
    {"key": "people_roles", "label_en": "People and roles", "label_ar": "الأشخاص والأدوار"},
    {"key": "policies_payroll", "label_en": "Policies and payroll", "label_ar": "السياسات والرواتب"},
    {"key": "channels_integrations", "label_en": "Channels and integrations", "label_ar": "القنوات والتكاملات"},
    {"key": "launch_readiness", "label_en": "Launch readiness", "label_ar": "جاهزية الإطلاق"},
)


def _flag_on(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _flag_off(name: str, default: str = "off") -> bool:
    return os.environ.get(name, default).strip().lower() in {"0", "false", "no", "off", ""}


def _companies_allow(name: str) -> set[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def _company_allowed(env_name: str, company: str) -> bool:
    allowed = _companies_allow(env_name)
    if not allowed:
        # Empty company allowlist with feature on often means "all" for some modules,
        # but Wave A treats empty as not specifically opened for WATHEFNI commercial live.
        return False
    return company.upper() in allowed


def wave_a_enabled() -> bool:
    """Wave A is live when Setup Console is on and Wave A ACK flag is set (or legacy console-only)."""
    if not _flag_on("WATHEFNI_SETUP_CONSOLE_ENABLED"):
        return False
    # Explicit Wave A flag preferred after production ACK; console-only remains readable for staging.
    if _flag_on("WATHEFNI_SETUP_CONSOLE_WAVE_A"):
        return True
    return _flag_on("WATHEFNI_SETUP_CONSOLE_V2")


def wave_a_enabled_for_company(company_code: str) -> bool:
    if company_code.upper() != ALLOWED_COMPANY:
        return False
    allowed = _companies_allow("WATHEFNI_SETUP_CONSOLE_WAVE_A_COMPANIES")
    if allowed:
        return company_code.upper() in allowed
    # Empty Wave A company list: WATHEFNI-only hard rule still applies.
    return company_code.upper() == ALLOWED_COMPANY


def honesty_payload() -> dict[str, Any]:
    ingest_off = _flag_off("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
    return {
        "contract": WAVE_A_CONTRACT,
        "wave_a_version": WAVE_A_VERSION,
        "operator_only": True,
        "wathefni_only": True,
        "external_tenants": False,
        "payroll_money": False,
        "payment_processing": "disabled",
        "attendance_ingest": False,
        "capture_ingest": "off" if ingest_off else "on",
        "capture_ingest_must_remain_off": True,
        "entitlements_cannot_bypass_gates": True,
        "ai": False,
        "mobile_apps": False,
        "setup_wave_b": False,
        "rollout_widening": False,
        "frozen_module_contracts_unchanged": True,
        "read_only_evaluate": True,
    }


def _item(
    *,
    key: str,
    title_en: str,
    title_ar: str,
    state: str,
    purchased: bool,
    configured: bool,
    blocked: bool,
    live: bool,
    summary_en: str,
    summary_ar: str,
    next_action_en: str | None = None,
    next_action_ar: str | None = None,
    deep_link: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert state in HONEST_STATES, state
    return {
        "key": key,
        "title_en": title_en,
        "title_ar": title_ar,
        "state": state,
        "purchased": purchased,
        "configured": configured,
        "blocked": blocked,
        "live": live,
        "summary_en": summary_en,
        "summary_ar": summary_ar,
        "next_action_en": next_action_en,
        "next_action_ar": next_action_ar,
        "deep_link": deep_link,
        "evidence": evidence or {},
    }


def _load_company(cur: Any, company_code: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT company_code, name, country, status,
               COALESCE(disabled_at::text,'') AS disabled_at,
               COALESCE(archived_at::text,'') AS archived_at
        FROM companies
        WHERE upper(company_code)=%s
        LIMIT 1
        """,
        (company_code.upper(),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _enabled_modules(cur: Any, company_code: str) -> set[str]:
    cur.execute(
        """
        SELECT module_key
        FROM company_modules
        WHERE upper(company_code)=%s AND enabled IS TRUE
        """,
        (company_code.upper(),),
    )
    return {str(dict(r)["module_key"]) for r in cur.fetchall()}


def _owner_count(cur: Any, company_code: str) -> int:
    cur.execute(
        """
        SELECT count(*)::int AS n
        FROM dashboard_users
        WHERE upper(company_code)=%s
          AND lower(COALESCE(role,'')) IN ('owner','admin','hr_admin')
          AND lower(COALESCE(status,'')) NOT IN ('revoked','disabled','archived')
        """,
        (company_code.upper(),),
    )
    return int((cur.fetchone() or {}).get("n") or 0)


def _employee_count(cur: Any, company_code: str) -> int:
    try:
        cur.execute(
            """
            SELECT count(*)::int AS n
            FROM employees
            WHERE upper(company_code)=%s
            """,
            (company_code.upper(),),
        )
        return int((cur.fetchone() or {}).get("n") or 0)
    except Exception:
        return 0


def _settings_map(cur: Any, company_code: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT settings
        FROM company_settings
        WHERE upper(company_code)=%s
        LIMIT 1
        """,
        (company_code.upper(),),
    )
    row = cur.fetchone()
    if not row:
        return {}
    settings = dict(row).get("settings") or {}
    return dict(settings) if isinstance(settings, dict) else {}


def _module_pause_state(cur: Any, company_code: str, module_key: str) -> bool:
    try:
        cur.execute(
            """
            SELECT m.paused
            FROM tc_tenant_module_instances m
            JOIN tc_tenants t ON t.tenant_id = m.tenant_id
            WHERE upper(t.company_code)=%s AND m.module_key=%s
            LIMIT 1
            """,
            (company_code.upper(), module_key),
        )
        row = cur.fetchone()
        if not row:
            return False
        return bool(dict(row).get("paused"))
    except Exception:
        return False


def _evaluate_module(
    *,
    key: str,
    label: str,
    purchased: bool,
    paused: bool,
    company: str,
) -> dict[str, Any]:
    if not purchased:
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="not_purchased",
            purchased=False,
            configured=False,
            blocked=False,
            live=False,
            summary_en="Not included in this company’s purchased modules.",
            summary_ar="غير مضمّن في الوحدات المشتراة لهذه الشركة.",
            next_action_en="Add this module only if the commercial package includes it.",
            next_action_ar="أضف هذه الوحدة فقط إذا كانت ضمن الباقة التجارية.",
            deep_link="/setup-console",
            evidence={"module_key": key},
        )

    if paused:
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="paused",
            purchased=True,
            configured=True,
            blocked=False,
            live=False,
            summary_en="Purchased, but paused. Interactive use is held.",
            summary_ar="مشتراة لكنها متوقفة. الاستخدام التفاعلي معلّق.",
            next_action_en="Review pause impact, then resume only when operations are ready.",
            next_action_ar="راجع أثر الإيقاف، ثم استأنف فقط عندما تكون العمليات جاهزة.",
            deep_link="/setup-console",
            evidence={"module_key": key, "paused": True},
        )

    # Module-specific honest rollout gates (never overrideable by console toggles).
    if key == "attendance":
        ingest_on = _flag_on("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
        ingest_off = not ingest_on
        synthetic = _flag_on("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY", "on")
        auth_on = _flag_on("WATHEFNI_ATTENDANCE_AUTHORITY", "on")
        if not auth_on:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="blocked",
                purchased=True,
                configured=False,
                blocked=True,
                live=False,
                summary_en="Attendance review is not open for this company yet.",
                summary_ar="مراجعة الحضور غير مفتوحة لهذه الشركة بعد.",
                next_action_en="Keep Attendance closed until the controlled rollout opens it.",
                next_action_ar="أبقِ الحضور مغلقاً حتى يُفتح في الإطلاق المنضبط.",
                deep_link="/dashboard",
                evidence={"gate": "attendance_authority_off"},
            )
        if ingest_off:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="live_controlled",
                purchased=True,
                configured=True,
                blocked=True,
                live=True,
                summary_en="Attendance review is live in a controlled way. Real device punch intake stays off.",
                summary_ar="مراجعة الحضور تعمل بشكل منضبط. استقبال البصمات من الأجهزة ما زال مغلقاً.",
                next_action_en="Use the Attendance board for review. Do not connect devices yet.",
                next_action_ar="استخدم لوحة الحضور للمراجعة. لا تصل الأجهزة الآن.",
                deep_link="/dashboard",
                evidence={"gate": "capture_ingest_off", "synthetic_only": synthetic},
            )
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="blocked",
            purchased=True,
            configured=True,
            blocked=True,
            live=False,
            summary_en="Punch intake appears enabled outside the approved freeze. Treat as unsafe until ops confirms.",
            summary_ar="يبدو أن استقبال البصمات مفعّل خارج التجميد المعتمد. اعتبره غير آمن حتى يؤكد التشغيل.",
            next_action_en="Contact platform ops before using Attendance punches.",
            next_action_ar="تواصل مع تشغيل المنصة قبل استخدام بصمات الحضور.",
            deep_link="/dashboard",
            evidence={"gate": "capture_ingest_unexpected_on"},
        )

    if key == "payroll":
        synthetic = _flag_on("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "on") or _flag_on(
            "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "on"
        )
        wave_on = _flag_on("WATHEFNI_PAYROLL_WAVE1", "0") or _flag_on("WATHEFNI_PAYROLL_WAVE2A", "0")
        companies_ok = _company_allowed("WATHEFNI_PAYROLL_WAVE1_COMPANIES", company) or _company_allowed(
            "WATHEFNI_PAYROLL_WAVE2A_COMPANIES", company
        ) or company == "WATHEFNI"
        if not wave_on:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="setup_required",
                purchased=True,
                configured=False,
                blocked=False,
                live=False,
                summary_en="Payroll workspace is purchased but not opened for controlled use yet.",
                summary_ar="مساحة الرواتب مشتراة لكنها غير مفتوحة للاستخدام المنضبط بعد.",
                next_action_en="Open External payroll run after company basics and people are in place.",
                next_action_ar="افتح تشغيل الرواتب الخارجية بعد تجهيز الأساسيات والأشخاص.",
                deep_link="/dashboard",
                evidence={"gate": "payroll_wave_off"},
            )
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="live_controlled",
            purchased=True,
            configured=True,
            blocked=True,
            live=True,
            summary_en="External payroll run is available in a controlled way. Wathefni does not process pay money.",
            summary_ar="تشغيل الرواتب الخارجية متاح بشكل منضبط. وثفني لا يعالج أموال الرواتب.",
            next_action_en="Use External payroll run for setup and exports. Keep payment processing off.",
            next_action_ar="استخدم تشغيل الرواتب الخارجية للإعداد والتصدير. أبقِ معالجة الدفع مغلقة.",
            deep_link="/dashboard",
            evidence={"gate": "payroll_synthetic_or_money_disabled", "synthetic_only": synthetic, "companies_ok": companies_ok},
        )

    if key == "shifts":
        wave = _flag_on("WATHEFNI_SHIFTS_WAVE6C", "0") or _flag_on("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "0")
        hr_allow = os.environ.get("WATHEFNI_SHIFTS_HR_ALLOWLIST", "").strip()
        mgr_empty = not os.environ.get("WATHEFNI_SHIFTS_MANAGER_ALLOWLIST", "").strip()
        reminders_off = _flag_off("WATHEFNI_SHIFTS_REAL_REMINDERS", "0") or not _flag_on(
            "WATHEFNI_SHIFTS_REAL_REMINDERS", "0"
        )
        if not wave:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="setup_required",
                purchased=True,
                configured=False,
                blocked=False,
                live=False,
                summary_en="Shifts is purchased but the controlled schedule workspace is not open yet.",
                summary_ar="المناوبات مشتراة لكن مساحة الجدولة المنضبطة غير مفتوحة بعد.",
                next_action_en="Open Shifts in HR after people records exist.",
                next_action_ar="افتح المناوبات في الموارد البشرية بعد وجود سجلات الأشخاص.",
                deep_link="/dashboard",
                evidence={"gate": "shifts_wave_off"},
            )
        if not hr_allow:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="blocked",
                purchased=True,
                configured=False,
                blocked=True,
                live=False,
                summary_en="No approved schedule operator is assigned yet.",
                summary_ar="لا يوجد مشغّل جداول معتمد معيّن بعد.",
                next_action_en="Ask platform ops to confirm the approved HR operator before scheduling.",
                next_action_ar="اطلب من تشغيل المنصة تأكيد مشغّل الموارد البشرية المعتمد قبل الجدولة.",
                deep_link="/dashboard",
                evidence={"gate": "shifts_hr_allowlist_empty"},
            )
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="live_controlled",
            purchased=True,
            configured=True,
            blocked=False,
            live=True,
            summary_en="Shifts is live for the approved HR operator only. Manager scheduling and broad reminders stay closed.",
            summary_ar="المناوبات تعمل لمشغّل الموارد البشرية المعتمد فقط. جدولة المديرين والتذكيرات الواسعة مغلقة.",
            next_action_en="Publish schedules in Shifts. Do not widen manager access from Setup.",
            next_action_ar="انشر الجداول في المناوبات. لا توسّع صلاحية المديرين من الإعداد.",
            deep_link="/dashboard",
            evidence={"gate": "shifts_controlled", "manager_allowlist_empty": mgr_empty, "reminders_off": reminders_off},
        )

    if key == "leave":
        synthetic = _flag_on("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY", "on") or _flag_on(
            "WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY", "1"
        )
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="live_controlled" if purchased else "not_purchased",
            purchased=True,
            configured=True,
            blocked=False,
            live=True,
            summary_en="Leave is available in a controlled company posture. Policy details stay in Leave.",
            summary_ar="الإجازات متاحة بوضع شركة منضبط. تفاصيل السياسة تبقى في الإجازات.",
            next_action_en="Review leave policies inside Leave — not in Setup.",
            next_action_ar="راجع سياسات الإجازات داخل الإجازات — وليس من الإعداد.",
            deep_link="/dashboard",
            evidence={"synthetic_only": synthetic},
        )

    if key == "employee_app":
        flag = _flag_on("WATHEFNI_EMPLOYEE_APP", "off")
        if not flag:
            return _item(
                key=f"module:{key}",
                title_en=label,
                title_ar=label,
                state="blocked",
                purchased=True,
                configured=False,
                blocked=True,
                live=False,
                summary_en="Employee App is purchased but the platform channel is not open.",
                summary_ar="تطبيق الموظف مشترًى لكن قناة المنصة غير مفتوحة.",
                next_action_en="Leave Employee App closed until platform activation is approved.",
                next_action_ar="أبقِ تطبيق الموظف مغلقاً حتى يُعتمد تفعيل المنصة.",
                deep_link="/setup-console",
                evidence={"gate": "employee_app_master_flag_off"},
            )
        return _item(
            key=f"module:{key}",
            title_en=label,
            title_ar=label,
            state="live_controlled",
            purchased=True,
            configured=True,
            blocked=False,
            live=True,
            summary_en="Employee App channel is open in a controlled allowlist posture.",
            summary_ar="قناة تطبيق الموظف مفتوحة بوضع قائمة سماح منضبطة.",
            next_action_en="Manage employee access in the Employee App rollout — not via Setup toggles.",
            next_action_ar="أدِر وصول الموظفين من إطلاق تطبيق الموظف — وليس عبر مفاتيح الإعداد.",
            deep_link="/dashboard",
            evidence={"gate": "employee_app_on"},
        )

    # Default purchased post/pre-hire modules: controlled live if present in company_modules.
    return _item(
        key=f"module:{key}",
        title_en=label,
        title_ar=label,
        state="live_controlled",
        purchased=True,
        configured=True,
        blocked=False,
        live=True,
        summary_en=f"{label} is included and available in the current controlled company posture.",
        summary_ar=f"{label} مضمّنة ومتاحة في وضع الشركة المنضبط الحالي.",
        next_action_en=f"Configure {label} inside its own workspace when needed.",
        next_action_ar=f"اضبط {label} داخل مساحتها عند الحاجة.",
        deep_link="/dashboard",
        evidence={"module_key": key},
    )


def _overall_state(items: list[dict[str, Any]], company_paused: bool) -> str:
    if company_paused:
        return "paused"
    states = [str(i.get("state")) for i in items]
    if any(s == "blocked" for s in states):
        # Controlled live with intentional blockers (e.g. attendance ingest) still allows launch_readiness as live_controlled
        intentional = all(
            (i.get("state") != "blocked")
            or (i.get("live") is True)  # live_controlled with blocked side-path
            or str(i.get("key") or "").startswith("module:employee_app")
            for i in items
        )
        # Prefer live_controlled if we have live modules and only intentional safety blocks
        if any(i.get("live") for i in items) and intentional:
            return "live_controlled"
        if any(i.get("live") for i in items):
            return "live_controlled"
        return "blocked"
    if any(s == "setup_required" for s in states):
        return "setup_required"
    if any(s == "ready_for_canary" for s in states):
        return "ready_for_canary"
    if any(s == "live_controlled" for s in states):
        return "live_controlled"
    if all(s == "not_purchased" for s in states):
        return "setup_required"
    return "setup_required"


def evaluate_launch_readiness(cur: Any, *, company_code: str = ALLOWED_COMPANY) -> dict[str, Any]:
    company = (company_code or "").strip().upper()
    if company != ALLOWED_COMPANY:
        return {
            "ok": False,
            "error": "wave_a_wathefni_only",
            "message_en": "Launch Readiness Wave A is limited to WATHEFNI.",
            "message_ar": "جاهزية الإطلاق في الموجة A مقتصرة على وثفني.",
            "wave_a_version": WAVE_A_VERSION,
        }

    row = _load_company(cur, company)
    if not row:
        return {
            "ok": False,
            "error": "company_missing",
            "message_en": "WATHEFNI company record was not found.",
            "message_ar": "سجل شركة وثفني غير موجود.",
            "wave_a_version": WAVE_A_VERSION,
        }

    status = str(row.get("status") or "active").lower()
    company_paused = status in {"disabled", "archived"}
    enabled = _enabled_modules(cur, company)
    settings = _settings_map(cur, company)
    owners = _owner_count(cur, company)
    employees = _employee_count(cur, company)
    channel_reviewed = str(settings.get("channel_policy_reviewed") or "").lower() in {"1", "true", "yes", "on"}
    locale_default = str(settings.get("default_locale") or settings.get("locale") or "")
    country = str(row.get("country") or settings.get("country") or "")
    timezone = str(settings.get("timezone") or "")
    currency = str(settings.get("currency") or "")
    if not timezone and country.upper() == "KW":
        timezone = "Asia/Kuwait"
    if not currency and country.upper() == "KW":
        currency = "KWD"

    stages: list[dict[str, Any]] = []

    # --- Company basics ---
    basics_items: list[dict[str, Any]] = []
    profile_ok = bool(row.get("name") and country and timezone and currency)
    basics_items.append(
        _item(
            key="company_profile",
            title_en="Company profile",
            title_ar="ملف الشركة",
            state="paused" if company_paused else ("live_controlled" if profile_ok else "setup_required"),
            purchased=True,
            configured=profile_ok,
            blocked=False,
            live=profile_ok and not company_paused,
            summary_en=(
                "Company name, country, timezone, and currency are set."
                if profile_ok
                else "Company name, country, timezone, or currency still needs attention."
            ),
            summary_ar=(
                "اسم الشركة والدولة والمنطقة الزمنية والعملة مضبوطة."
                if profile_ok
                else "اسم الشركة أو الدولة أو المنطقة الزمنية أو العملة ما زال يحتاج انتباهاً."
            ),
            next_action_en=None if profile_ok else "Complete company basics in Classic setup.",
            next_action_ar=None if profile_ok else "أكمل أساسيات الشركة في الإعداد الكلاسيكي.",
            deep_link="/setup-console",
            evidence={"profile_ok": profile_ok},
        )
    )
    basics_items.append(
        _item(
            key="company_locale",
            title_en="Language default",
            title_ar="اللغة الافتراضية",
            state="live_controlled" if locale_default else "setup_required",
            purchased=True,
            configured=bool(locale_default),
            blocked=False,
            live=bool(locale_default),
            summary_en=(
                f"Default language is set ({locale_default})."
                if locale_default
                else "No company default language yet. Operators can still switch EN/AR in the console."
            ),
            summary_ar=(
                f"اللغة الافتراضية مضبوطة ({locale_default})."
                if locale_default
                else "لا توجد لغة افتراضية للشركة بعد. يمكن للمشغّلين التبديل بين العربية والإنجليزية في الواجهة."
            ),
            next_action_en=None if locale_default else "Set default language to English or Arabic when ready.",
            next_action_ar=None if locale_default else "اضبط اللغة الافتراضية إلى العربية أو الإنجليزية عند الجاهزية.",
            deep_link="/setup-console",
            evidence={"default_locale": locale_default or None},
        )
    )
    stages.append({"stage": STAGES[0], "items": basics_items})

    # --- Modules ---
    module_items: list[dict[str, Any]] = []
    for mod in modules.MODULE_CATALOG:
        paused = _module_pause_state(cur, company, mod.key)
        module_items.append(
            _evaluate_module(
                key=mod.key,
                label=mod.label,
                purchased=mod.key in enabled,
                paused=paused,
                company=company,
            )
        )
    stages.append({"stage": STAGES[1], "items": module_items})

    # --- People and roles ---
    people_items: list[dict[str, Any]] = []
    people_items.append(
        _item(
            key="owner_role",
            title_en="Owner or HR admin",
            title_ar="المالك أو مسؤول الموارد البشرية",
            state="live_controlled" if owners > 0 else "setup_required",
            purchased=True,
            configured=owners > 0,
            blocked=False,
            live=owners > 0,
            summary_en=(
                f"{owners} owner/HR admin account(s) present."
                if owners > 0
                else "No owner or HR admin account is ready yet."
            ),
            summary_ar=(
                f"يوجد {owners} حساب مالك/مسؤول موارد بشرية."
                if owners > 0
                else "لا يوجد حساب مالك أو مسؤول موارد بشرية جاهز بعد."
            ),
            next_action_en=None if owners > 0 else "Seed the Owner invite from Classic setup.",
            next_action_ar=None if owners > 0 else "أنشئ دعوة المالك من الإعداد الكلاسيكي.",
            deep_link="/setup-console",
            evidence={"owner_count": owners},
        )
    )
    people_items.append(
        _item(
            key="employee_records",
            title_en="People records",
            title_ar="سجلات الأشخاص",
            state="live_controlled" if employees > 0 else "setup_required",
            purchased=True,
            configured=employees > 0,
            blocked=False,
            live=employees > 0,
            summary_en=(
                f"{employees} employee record(s) on file."
                if employees > 0
                else "No employee records imported yet."
            ),
            summary_ar=(
                f"يوجد {employees} سجل موظف."
                if employees > 0
                else "لا توجد سجلات موظفين مستوردة بعد."
            ),
            next_action_en=None if employees > 0 else "Import or hire people from the HR workspace.",
            next_action_ar=None if employees > 0 else "استورد أو وظّف الأشخاص من مساحة الموارد البشرية.",
            deep_link="/dashboard",
            evidence={"employee_count": employees},
        )
    )
    people_items.append(
        _item(
            key="manager_scope",
            title_en="Manager access",
            title_ar="صلاحية المديرين",
            state="blocked",
            purchased=True,
            configured=False,
            blocked=True,
            live=False,
            summary_en="Scoped manager scheduling is not part of the current controlled launch.",
            summary_ar="جدولة المديرين ذات النطاق ليست جزءاً من الإطلاق المنضبط الحالي.",
            next_action_en="Keep manager scheduling closed. Use the approved HR operator for Shifts.",
            next_action_ar="أبقِ جدولة المديرين مغلقة. استخدم مشغّل الموارد البشرية المعتمد للمناوبات.",
            deep_link="/dashboard",
            evidence={"gate": "manager_scope_frozen"},
        )
    )
    stages.append({"stage": STAGES[2], "items": people_items})

    # --- Policies and payroll ---
    policy_items: list[dict[str, Any]] = []
    payroll_mod = next((i for i in module_items if i["key"] == "module:payroll"), None)
    leave_mod = next((i for i in module_items if i["key"] == "module:leave"), None)
    policy_items.append(
        _item(
            key="leave_policies",
            title_en="Leave policies",
            title_ar="سياسات الإجازات",
            state=(leave_mod or {}).get("state") or "not_purchased",
            purchased=bool((leave_mod or {}).get("purchased")),
            configured=bool((leave_mod or {}).get("configured")),
            blocked=False,
            live=bool((leave_mod or {}).get("live")),
            summary_en="Leave policy details stay inside Leave. Setup only shows whether Leave is included.",
            summary_ar="تفاصيل سياسة الإجازات تبقى داخل الإجازات. الإعداد يظهر فقط إن كانت الإجازات مضمّنة.",
            next_action_en="Open Leave to review policy packs — do not duplicate them here.",
            next_action_ar="افتح الإجازات لمراجعة حزم السياسات — ولا تكررها هنا.",
            deep_link="/dashboard",
            evidence={"owned_by": "leave_module"},
        )
    )
    policy_items.append(
        _item(
            key="payroll_mode",
            title_en="Payroll mode",
            title_ar="وضع الرواتب",
            state=(payroll_mod or {}).get("state") or "not_purchased",
            purchased=bool((payroll_mod or {}).get("purchased")),
            configured=bool((payroll_mod or {}).get("configured")),
            blocked=True,
            live=bool((payroll_mod or {}).get("live")),
            summary_en="External payroll remains the money authority. Payment processing stays disabled.",
            summary_ar="الرواتب الخارجية تبقى سلطة المال. معالجة الدفع تبقى معطّلة.",
            next_action_en="Open External payroll run for setup status and checklist.",
            next_action_ar="افتح تشغيل الرواتب الخارجية لحالة الإعداد وقائمة التحقق.",
            deep_link="/dashboard",
            evidence={"owned_by": "payroll_module", "payment_processing": "disabled"},
        )
    )
    stages.append({"stage": STAGES[3], "items": policy_items})

    # --- Channels and integrations ---
    channel_items: list[dict[str, Any]] = []
    channel_items.append(
        _item(
            key="channel_policy",
            title_en="Messaging policy",
            title_ar="سياسة المراسلة",
            state="live_controlled" if channel_reviewed else "setup_required",
            purchased=True,
            configured=channel_reviewed,
            blocked=False,
            live=channel_reviewed,
            summary_en=(
                "Messaging policy has been reviewed."
                if channel_reviewed
                else "Messaging policy still needs a review check."
            ),
            summary_ar=(
                "تمت مراجعة سياسة المراسلة."
                if channel_reviewed
                else "ما زالت سياسة المراسلة تحتاج مراجعة."
            ),
            next_action_en=None if channel_reviewed else "Mark messaging policy reviewed in Classic setup.",
            next_action_ar=None if channel_reviewed else "علّم سياسة المراسلة كمراجعة في الإعداد الكلاسيكي.",
            deep_link="/setup-console",
            evidence={"channel_policy_reviewed": channel_reviewed},
        )
    )
    company_wa = _flag_on("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", "off")
    channel_items.append(
        _item(
            key="whatsapp_channel",
            title_en="Company WhatsApp channel",
            title_ar="قناة واتساب الشركة",
            state="blocked" if not company_wa else "setup_required",
            purchased=True,
            configured=False,
            blocked=not company_wa,
            live=False,
            summary_en=(
                "Company-owned WhatsApp routing is not open. Shared platform messaging may still apply."
                if not company_wa
                else "Company WhatsApp routing can be configured when an account is verified."
            ),
            summary_ar=(
                "توجيه واتساب المملوك للشركة غير مفتوح. قد تبقى مراسلة المنصة المشتركة."
                if not company_wa
                else "يمكن ضبط واتساب الشركة عند التحقق من الحساب."
            ),
            next_action_en=(
                "Leave company WhatsApp closed unless platform ops opens company-owned routing."
                if not company_wa
                else "Add and verify the company WhatsApp account in Classic setup."
            ),
            next_action_ar=(
                "أبقِ واتساب الشركة مغلقاً ما لم يفتح تشغيل المنصة التوجيه المملوك للشركة."
                if not company_wa
                else "أضف حساب واتساب الشركة وتحقق منه في الإعداد الكلاسيكي."
            ),
            deep_link="/setup-console",
            evidence={"company_channel_accounts": company_wa},
        )
    )
    channel_items.append(
        _item(
            key="attendance_devices",
            title_en="Attendance devices",
            title_ar="أجهزة الحضور",
            state="blocked",
            purchased="attendance" in enabled,
            configured=False,
            blocked=True,
            live=False,
            summary_en="Real device punch intake stays off. Device setup is not part of this launch checklist.",
            summary_ar="استقبال بصمات الأجهزة يبقى مغلقاً. إعداد الأجهزة ليس جزءاً من قائمة الإطلاق هذه.",
            next_action_en="Do not connect biometric devices from Setup.",
            next_action_ar="لا تصل أجهزة البصمة من الإعداد.",
            deep_link="/dashboard",
            evidence={"gate": "capture_ingest_off"},
        )
    )
    stages.append({"stage": STAGES[4], "items": channel_items})

    # --- Launch readiness ---
    all_items = [i for s in stages for i in s["items"]]
    overall = _overall_state(all_items + people_items + policy_items + channel_items + basics_items, company_paused)
    # recompute cleanly
    flat = basics_items + module_items + people_items + policy_items + channel_items
    overall = _overall_state(flat, company_paused)

    important_blockers = [
        {
            "key": i["key"],
            "title_en": i["title_en"],
            "title_ar": i["title_ar"],
            "summary_en": i["summary_en"],
            "summary_ar": i["summary_ar"],
            "next_action_en": i.get("next_action_en"),
            "next_action_ar": i.get("next_action_ar"),
            "deep_link": i.get("deep_link"),
            "state": i["state"],
        }
        for i in flat
        if i.get("blocked") and i.get("state") in {"blocked", "live_controlled"}
        and i.get("next_action_en")
        and i["key"]
        in {
            "manager_scope",
            "module:employee_app",
            "whatsapp_channel",
            "attendance_devices",
            "payroll_mode",
            "module:attendance",
            "module:shifts",
        }
    ]
    # Deduplicate by key preserving order
    seen: set[str] = set()
    blockers_out: list[dict[str, Any]] = []
    for b in important_blockers:
        if b["key"] in seen:
            continue
        seen.add(b["key"])
        blockers_out.append(b)

    launch_items = [
        _item(
            key="overall_launch",
            title_en="Overall launch posture",
            title_ar="وضع الإطلاق العام",
            state=overall,
            purchased=True,
            configured=profile_ok and owners > 0,
            blocked=overall == "blocked",
            live=overall == "live_controlled",
            summary_en={
                "paused": "Company is paused. Interactive work is held.",
                "blocked": "Important launch blockers remain. See the list below.",
                "setup_required": "Basics still need work before calling this launch-ready.",
                "ready_for_canary": "Ready for a controlled canary, not a broad rollout.",
                "live_controlled": "WATHEFNI is operating in a controlled launch posture.",
                "not_purchased": "Nothing is purchased yet.",
            }.get(overall, "Review the checklist stages."),
            summary_ar={
                "paused": "الشركة متوقفة. العمل التفاعلي معلّق.",
                "blocked": "ما زالت هناك عوائق إطلاق مهمة. راجع القائمة أدناه.",
                "setup_required": "ما زالت الأساسيات تحتاج عملاً قبل اعتبار الإطلاق جاهزاً.",
                "ready_for_canary": "جاهز لتجربة منضبطة، وليس طرحاً واسعاً.",
                "live_controlled": "وثفني تعمل بوضع إطلاق منضبط.",
                "not_purchased": "لا شيء مشترًى بعد.",
            }.get(overall, "راجع مراحل قائمة التحقق."),
            next_action_en="Work the next action on each important blocker. Do not widen freezes from Setup.",
            next_action_ar="نفّذ الإجراء التالي لكل عائق مهم. لا توسّع التجميدات من الإعداد.",
            deep_link="/setup-console",
            evidence={"overall": overall},
        )
    ]
    stages.append({"stage": STAGES[5], "items": launch_items})

    pause_impact = {
        "title_en": "If you pause the company or a module",
        "title_ar": "إذا أوقفت الشركة أو وحدة",
        "bullets_en": [
            "Interactive Setup and HR sessions for that scope are held.",
            "Background jobs, timers, and device intake are not fully stopped by a Setup toggle alone.",
            "Payroll money and Attendance device intake stay off regardless of resume.",
            "Resuming never overrides safety freezes or allowlists.",
        ],
        "bullets_ar": [
            "جلسات الإعداد والموارد البشرية التفاعلية لهذا النطاق تُعلَّق.",
            "المهام الخلفية والمؤقتات واستقبال الأجهزة لا تتوقف بالكامل بمفتاح إعداد وحده.",
            "أموال الرواتب واستقبال أجهزة الحضور يبقيان مغلقين بغض النظر عن الاستئناف.",
            "الاستئناف لا يتجاوز تجميدات السلامة أو قوائم السماح.",
        ],
    }

    return {
        "ok": True,
        "wave_a_version": WAVE_A_VERSION,
        "company_code": company,
        "company_name": row.get("name"),
        "overall_state": overall,
        "overall_label_en": {
            "not_purchased": "Not purchased",
            "setup_required": "Setup required",
            "blocked": "Blocked",
            "ready_for_canary": "Ready for canary",
            "live_controlled": "Live · controlled",
            "paused": "Paused",
        }.get(overall, overall),
        "overall_label_ar": {
            "not_purchased": "غير مشترًى",
            "setup_required": "يلزم الإعداد",
            "blocked": "محظور",
            "ready_for_canary": "جاهز للتجربة",
            "live_controlled": "يعمل · منضبط",
            "paused": "متوقف",
        }.get(overall, overall),
        "stages": stages,
        "important_blockers": blockers_out,
        "pause_impact": pause_impact,
        "entitlements_cannot_bypass_gates": True,
        "external_tenants": False,
        "payroll_money": False,
        "attendance_ingest": False,
        "honesty": {
            "payment_processing": "disabled",
            "capture_ingest": "off",
            "operator_only": True,
            "wathefni_only": True,
        },
    }
