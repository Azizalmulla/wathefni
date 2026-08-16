"""Per-turn Assistant capability catalog.

Builds what the HR copilot may offer from tenant modules, actor permissions,
provider/channel configuration, and the live tool registry — never invents
capabilities that are disabled, unconfigured, or unauthorized.
"""

from __future__ import annotations

from typing import Any

# Capability ids used in prompts, chips, and workflow previews.
CAPABILITY_IDS = (
    "jobs",
    "candidates",
    "ranking",
    "overview",
    "reports",
    "assessments",
    "interviews_schedule",
    "interviews_reschedule",
    "interviews_cancel",
    "google_meet",
    "teams_meet",
    "calendar_events",
    "email",
    "whatsapp",
    "video_interviews",
    "candidate_workflow",
    "posthire_action_inbox",
    "posthire_employees_360",
    "posthire_setup_readiness",
    "posthire_leave_queue",
    "posthire_attendance_exceptions",
    "posthire_leave",
    "posthire_attendance",
    "posthire_shifts",
    "posthire_onboarding",
    "posthire_compliance",
    "posthire_payroll",
    "posthire_analytics",
)

STATUS_AVAILABLE = "enabled_and_available"
STATUS_NOT_CONFIGURED = "enabled_but_not_configured"
STATUS_DENIED = "unavailable_by_permission"
STATUS_UNSUPPORTED = "unsupported"
STATUS_MODULE_OFF = "unavailable_module_off"


def _perm_ok(permissions: set[str] | list[str] | None, required: str | None) -> bool:
    if not required:
        return True
    perms = {str(p).strip() for p in (permissions or []) if str(p).strip()}
    if not perms:
        return False
    if required in perms or "*:*" in perms or "*." in perms:
        return True
    # Soft aliases used across the dashboard
    if required == "jobs.read" and ("prehire.read" in perms or "jobs.manage" in perms):
        return True
    if required.endswith(".read") and required.replace(".read", ".manage") in perms:
        return True
    return False


def _module_on(enabled: set[str], module: str) -> bool:
    if module == "pre_hiring":
        return True
    return module in enabled


def _email_env_transport_configured() -> bool:
    """Legacy/env transport probes (non-tenant). Includes Wathefni Postmark."""
    import os

    if os.environ.get("WATHEFNI_EMAIL_PROVIDER") or os.environ.get("SMTP_HOST"):
        return True
    if os.environ.get("RESEND_API_KEY") or os.environ.get("SENDGRID_API_KEY"):
        return True
    # Wathefni default outbound (Postmark) — same signals tenant_email_authority uses.
    token = (os.environ.get("WATHEFNI_POSTMARK_SERVER_TOKEN") or "").strip()
    from_addr = (os.environ.get("WATHEFNI_OUTBOUND_FROM") or "recruitment@wathefni.ai").strip()
    if token and from_addr:
        return True
    provider = (os.environ.get("WATHEFNI_OUTBOUND_EMAIL_PROVIDER") or "").strip().lower()
    return provider == "postmark" and bool(token and from_addr)


def _email_configured(legacy: Any, company_code: str | None = None) -> bool:
    """True when outbound email is ready for this tenant — aligned with Settings.

    Mirrors `GET /dashboard/prehire/integrations/email`:
      - wathefni + ready (Postmark) ⇒ configured
      - microsoft_mailbox / postmark_company_domain ⇒ only when status is ready
        (fail-closed when branded sender is selected but not activatable)
    """
    company = str(company_code or "").strip().upper()
    try:
        if company and hasattr(legacy, "db_connect"):
            import tenant_email_authority as tea

            view = tea.public_email_sending_view(legacy, company)
            status = str(view.get("status") or "").strip().lower()
            sender = str(view.get("current_sender") or "wathefni").strip().lower()
            if status == "ready":
                return True
            # Explicit branded mode that is not ready must stay fail-closed.
            if sender in {"microsoft_mailbox", "postmark_company_domain"}:
                return False
    except Exception:
        pass
    try:
        if legacy is not None and hasattr(legacy, "outbound_postmark_available"):
            if bool(legacy.outbound_postmark_available()):
                # Default Wathefni sender path without (or before) settings row.
                return True
    except Exception:
        pass
    try:
        return _email_env_transport_configured()
    except Exception:
        return False


def _whatsapp_configured(legacy: Any, company_code: str) -> bool:
    try:
        if hasattr(legacy, "setup_console_channel_policy"):
            policy = legacy.setup_console_channel_policy(company_code) or {}
            pre = policy.get("pre_hiring") if isinstance(policy.get("pre_hiring"), dict) else {}
            wa = pre.get("company_whatsapp") if isinstance(pre.get("company_whatsapp"), dict) else {}
            return bool(wa.get("configured"))
    except Exception:
        pass
    return False


def _google_calendar_configured(legacy: Any) -> bool:
    try:
        import interview_lifecycle as life

        return bool(life.google_calendar_configured(legacy))
    except Exception:
        return False


def _microsoft_calendar_configured(legacy: Any, company_code: str) -> bool:
    if not company_code or not hasattr(legacy, "db_connect"):
        return False
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM calendar_sync_connections
                    WHERE company_code=%s AND provider_key='microsoft' AND status='connected'
                    LIMIT 1
                    """,
                    (company_code.upper(),),
                )
                return bool(cur.fetchone())
    except Exception:
        return False


def _microsoft_cert_ready() -> bool:
    try:
        import interview_microsoft_calendar as mcal

        return bool(mcal.microsoft_env_configured())
    except Exception:
        return False


def _tool_names(visible_tools: list[dict[str, Any]] | None) -> set[str]:
    names: set[str] = set()
    for tool in visible_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str((fn or {}).get("name") or tool.get("name") or "").strip()
        if name:
            names.add(name)
    return names


def build_assistant_capability_catalog(
    *,
    legacy: Any,
    company_code: str,
    permissions: set[str] | list[str] | None,
    visible_tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return structured capability matrix for this actor/tenant/turn."""

    company = str(company_code or "").strip().upper()
    enabled: set[str] = set()
    try:
        if hasattr(legacy, "configured_company_modules"):
            enabled = {str(m) for m in (legacy.configured_company_modules(company) or set())}
    except Exception:
        enabled = set()

    tools = _tool_names(visible_tools)
    email_ok = _email_configured(legacy, company)
    wa_ok = _whatsapp_configured(legacy, company)
    google_ok = _google_calendar_configured(legacy)
    ms_ok = _microsoft_calendar_configured(legacy, company)
    live_interviews_on = _module_on(enabled, "interviews")
    # Aggregate flag for surfaces that treat either interview product as "interviews present".
    interviews_on = live_interviews_on or _module_on(enabled, "video_interviews")
    assessments_on = _module_on(enabled, "assessments")

    def entry(
        *,
        status: str,
        module: str | None = None,
        tools_needed: list[str] | None = None,
        provider: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "module": module,
            "tools": tools_needed or [],
            "provider": provider,
            "note": note,
            "offerable": status == STATUS_AVAILABLE,
        }

    def from_tool(
        tool_name: str,
        *,
        module: str,
        permission: str,
        provider_ok: bool | None = None,
        provider_label: str | None = None,
        unsupported_if_no_provider: bool = False,
    ) -> dict[str, Any]:
        if not _module_on(enabled, module) and module not in {"pre_hiring"}:
            return entry(status=STATUS_MODULE_OFF, module=module, tools_needed=[tool_name])
        if tool_name not in tools:
            # Tool absent from visible catalog — permission or module filter already applied
            if not _perm_ok(permissions, permission):
                return entry(status=STATUS_DENIED, module=module, tools_needed=[tool_name])
            return entry(status=STATUS_MODULE_OFF if module != "pre_hiring" else STATUS_DENIED, module=module, tools_needed=[tool_name])
        if not _perm_ok(permissions, permission):
            return entry(status=STATUS_DENIED, module=module, tools_needed=[tool_name])
        if provider_ok is False:
            if unsupported_if_no_provider:
                return entry(
                    status=STATUS_UNSUPPORTED,
                    module=module,
                    tools_needed=[tool_name],
                    provider=provider_label,
                    note=f"{provider_label or 'provider'} is not available for this company",
                )
            return entry(
                status=STATUS_NOT_CONFIGURED,
                module=module,
                tools_needed=[tool_name],
                provider=provider_label,
                note=f"{provider_label or 'provider'} is enabled in product but not configured",
            )
        return entry(status=STATUS_AVAILABLE, module=module, tools_needed=[tool_name], provider=provider_label)

    capabilities: dict[str, dict[str, Any]] = {
        "jobs": from_tool("list_job_openings", module="pre_hiring", permission="jobs.read"),
        "candidates": from_tool("get_candidate_status", module="pre_hiring", permission="prehire.read"),
        "ranking": from_tool("rank_candidates", module="pre_hiring", permission="prehire.read"),
        "overview": from_tool("get_prehire_work_queue", module="pre_hiring", permission="prehire.read"),
        "reports": from_tool("get_reports_metrics", module="pre_hiring", permission="prehire.read"),
        "assessments": from_tool("send_assessment", module="assessments", permission="assessment.manage"),
        # Live interview tools always require the interviews module (never fall back to pre_hiring).
        "interviews_schedule": from_tool("schedule_interview", module="interviews", permission="interview.manage"),
        "interviews_reschedule": from_tool("reschedule_interview", module="interviews", permission="interview.manage"),
        "interviews_cancel": from_tool("cancel_interview", module="interviews", permission="interview.manage"),
        "google_meet": from_tool(
            "schedule_interview",
            module="interviews",
            permission="interview.manage",
            provider_ok=google_ok,
            provider_label="google_calendar",
        ),
        "teams_meet": entry(
            status=(
                STATUS_AVAILABLE
                if (live_interviews_on and ms_ok and "schedule_interview" in tools and _microsoft_cert_ready())
                else (STATUS_MODULE_OFF if not live_interviews_on else STATUS_NOT_CONFIGURED)
            ),
            module="interviews",
            tools_needed=["schedule_interview"],
            provider="microsoft_teams",
            note=(
                None
                if (ms_ok and _microsoft_cert_ready())
                else "Microsoft 365 / Teams requires Exchange RBACfA Application Calendars.ReadWrite scoped to the calendar mailbox"
            ),
        ),
        "calendar_events": from_tool(
            "schedule_interview",
            module="interviews",
            permission="interview.manage",
            provider_ok=google_ok or ms_ok,
            provider_label="calendar",
        ),
        "email": from_tool(
            "send_email",
            module="pre_hiring",
            permission="candidate.manage",
            provider_ok=email_ok,
            provider_label="email",
        ),
        "whatsapp": from_tool(
            "notify_candidate",
            module="pre_hiring",
            permission="candidate.manage",
            provider_ok=wa_ok,
            provider_label="whatsapp",
        ),
        "video_interviews": from_tool("send_video_interview", module="video_interviews", permission="interview.manage"),
        "candidate_workflow": from_tool("execute_candidate_workflow", module="pre_hiring", permission="candidate.manage"),
        "posthire_action_inbox": from_tool(
            "summarize_action_inbox",
            module="analytics",  # inbox composes analytics/compliance/e360; gate on any posthire read
            permission="analytics.read",
        ),
        "posthire_employees_360": from_tool("summarize_employee_360", module="onboarding", permission="employees.read"),
        "posthire_setup_readiness": from_tool("get_launch_readiness_summary", module="pre_hiring", permission="settings.read"),
        "posthire_leave_queue": from_tool("summarize_leave_queue", module="leave", permission="leave.read"),
        "posthire_attendance_exceptions": from_tool(
            "summarize_attendance_exceptions", module="attendance", permission="attendance.read"
        ),
        "posthire_leave": from_tool("list_leave_requests", module="leave", permission="leave.read"),
        "posthire_attendance": from_tool("list_attendance", module="attendance", permission="attendance.read"),
        "posthire_shifts": from_tool("list_shifts", module="shifts", permission="shifts.read"),
        "posthire_onboarding": from_tool("list_onboarding_status", module="onboarding", permission="onboarding.read"),
        "posthire_compliance": from_tool("list_compliance_documents", module="compliance", permission="compliance.read"),
        "posthire_payroll": from_tool("list_payroll_hours", module="payroll", permission="payroll.read"),
        "posthire_analytics": from_tool("workforce_analytics", module="analytics", permission="analytics.read"),
    }

    # Wave 1: if spine tools are visible, force offerable flags with softer permission aliases.
    if "summarize_action_inbox" in tools:
        capabilities["posthire_action_inbox"] = entry(
            status=STATUS_AVAILABLE,
            module="action_inbox",
            tools_needed=["summarize_action_inbox"],
            note="default_posthire_entry",
        )
        capabilities["posthire_action_inbox"]["offerable"] = True
    if "summarize_employee_360" in tools:
        capabilities["posthire_employees_360"] = entry(
            status=STATUS_AVAILABLE,
            module="employees",
            tools_needed=["summarize_employee_360"],
        )
        capabilities["posthire_employees_360"]["offerable"] = True
    if "get_launch_readiness_summary" in tools:
        capabilities["posthire_setup_readiness"] = entry(
            status=STATUS_AVAILABLE,
            module="setup_console",
            tools_needed=["get_launch_readiness_summary"],
        )
        capabilities["posthire_setup_readiness"]["offerable"] = True
    # Wave 2 Safe Ops Queue Reads
    if "summarize_leave_queue" in tools:
        capabilities["posthire_leave_queue"] = entry(
            status=STATUS_AVAILABLE,
            module="leave",
            tools_needed=["summarize_leave_queue"],
            note="wave2_safe_ops_reads",
        )
        capabilities["posthire_leave_queue"]["offerable"] = True
    if "summarize_attendance_exceptions" in tools:
        capabilities["posthire_attendance_exceptions"] = entry(
            status=STATUS_AVAILABLE,
            module="attendance",
            tools_needed=["summarize_attendance_exceptions"],
            note="wave2_safe_ops_reads_ingest_off",
        )
        capabilities["posthire_attendance_exceptions"]["offerable"] = True

    # Fix teams_meet offerable flag
    if capabilities["teams_meet"]["status"] != STATUS_AVAILABLE:
        capabilities["teams_meet"]["offerable"] = False
    else:
        capabilities["teams_meet"]["offerable"] = True

    offerable = sorted(cid for cid, row in capabilities.items() if row.get("offerable"))
    return {
        "company_code": company,
        "enabled_modules": sorted(enabled),
        "visible_tools": sorted(tools),
        "providers": {
            "email": email_ok,
            "whatsapp": wa_ok,
            "google_calendar": google_ok,
            "microsoft_calendar": ms_ok,
        },
        "capabilities": capabilities,
        "offerable": offerable,
        "assessments_enabled": assessments_on,
        "interviews_enabled": interviews_on,
    }


def capability_prompt_block(catalog: dict[str, Any] | None) -> str:
    """Compact instruction block for the model — only offerable capabilities."""

    if not isinstance(catalog, dict):
        return ""
    caps = catalog.get("capabilities") if isinstance(catalog.get("capabilities"), dict) else {}
    lines = [
        "Capability authority for this turn (do not invent capabilities outside this list):",
    ]
    for cid in CAPABILITY_IDS:
        row = caps.get(cid) if isinstance(caps.get(cid), dict) else None
        if not row:
            continue
        status = row.get("status")
        if status == STATUS_AVAILABLE:
            lines.append(f"- {cid}: AVAILABLE via tools {row.get('tools')}")
        elif status == STATUS_NOT_CONFIGURED:
            lines.append(f"- {cid}: ENABLED BUT NOT CONFIGURED — tell HR it needs setup; do not claim it works")
        elif status == STATUS_DENIED:
            lines.append(f"- {cid}: UNAVAILABLE BY PERMISSION — do not offer")
        elif status == STATUS_MODULE_OFF:
            lines.append(f"- {cid}: MODULE OFF — do not offer")
        elif status == STATUS_UNSUPPORTED:
            lines.append(f"- {cid}: UNSUPPORTED — do not offer")
    return "\n".join(lines)


# Capability → empty-state module group (order preserved, de-duplicated).
# Action Inbox is the default post-hire entry (Wave 1 spine).
_EMPTY_MODULE_GROUPS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("action_inbox", ("posthire_action_inbox",), "Action Inbox", "صندوق الإجراءات"),
    ("leave_queue", ("posthire_leave_queue",), "Leave queue", "طابور الإجازات"),
    ("attendance_exceptions", ("posthire_attendance_exceptions",), "Attendance exceptions", "استثناءات الحضور"),
    ("employees", ("posthire_employees_360",), "Employees 360", "الموظفون 360"),
    ("setup", ("posthire_setup_readiness",), "Launch readiness", "جاهزية الإطلاق"),
    ("candidates", ("candidates",), "candidates", "المرشحين"),
    ("rankings", ("ranking",), "rankings", "الترتيب"),
    ("assessments", ("assessments",), "assessments", "التقييمات"),
    (
        "interviews",
        (
            "interviews_schedule",
            "interviews_reschedule",
            "interviews_cancel",
            "google_meet",
            "teams_meet",
            "video_interviews",
            "calendar_events",
        ),
        "interviews",
        "المقابلات",
    ),
    ("reports", ("reports",), "reports", "التقارير"),
    ("jobs", ("jobs",), "jobs", "الوظائف"),
    ("overview", ("overview",), "overview", "نظرة عامة"),
    ("follow-ups", ("email", "whatsapp", "candidate_workflow"), "follow-ups", "المتابعات"),
    ("onboarding", ("posthire_onboarding",), "onboarding", "التهيئة"),
    ("attendance", ("posthire_attendance",), "attendance", "الحضور"),
    ("leave", ("posthire_leave",), "leave", "الإجازات"),
    ("shifts", ("posthire_shifts",), "shifts", "الورديات"),
    ("payroll", ("posthire_payroll",), "payroll", "الرواتب"),
    ("compliance", ("posthire_compliance",), "compliance", "الامتثال"),
    ("analytics", ("posthire_analytics",), "workforce analytics", "تحليلات القوى العاملة"),
)

_POSTHIRE_MODULE_KEYS = {
    "action_inbox",
    "leave_queue",
    "attendance_exceptions",
    "employees",
    "setup",
    "onboarding",
    "attendance",
    "leave",
    "shifts",
    "payroll",
    "compliance",
    "analytics",
}


def empty_modules_from_catalog(catalog: dict[str, Any] | None, *, locale: str = "en") -> list[str]:
    """Human module labels for empty-state — only offerable capabilities."""

    ar = locale == "ar"
    if not isinstance(catalog, dict):
        return []
    offerable = set(catalog.get("offerable") or [])
    labels: list[str] = []
    seen: set[str] = set()
    for key, caps_needed, en, ar_text in _EMPTY_MODULE_GROUPS:
        if key in seen:
            continue
        if any(cid in offerable for cid in caps_needed):
            seen.add(key)
            labels.append(ar_text if ar else en)
    return labels


def empty_headline_from_catalog(catalog: dict[str, Any] | None, *, locale: str = "en") -> str:
    """Capability-driven empty-state headline. Neutral when nothing is offerable."""

    ar = locale == "ar"
    modules = empty_modules_from_catalog(catalog, locale=locale)
    if not modules:
        return "بماذا يمكنني المساعدة؟" if ar else "What can you help me with?"

    def join_list(items: list[str]) -> str:
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} {'أو' if ar else 'or'} {items[1]}"
        sep = "، " if ar else ", "
        conj = " أو " if ar else ", or "
        return sep.join(items[:-1]) + conj + items[-1]

    offerable = set((catalog or {}).get("offerable") or [])
    has_posthire = any(
        any(cid in offerable for cid in caps)
        for key, caps, _en, _ar in _EMPTY_MODULE_GROUPS
        if key in _POSTHIRE_MODULE_KEYS
    )
    has_hiring = any(
        any(cid in offerable for cid in caps)
        for key, caps, _en, _ar in _EMPTY_MODULE_GROUPS
        if key not in _POSTHIRE_MODULE_KEYS
    )

    joined = join_list(modules)
    # Keep headline short when many modules are offerable; chips carry the actionable prompts.
    if len(modules) > 4:
        if has_posthire and has_hiring:
            return "اسأل عن التوظيف أو فريقك." if ar else "Ask about hiring or your team."
        if has_posthire:
            return "اسأل عن فريقك." if ar else "Ask about your team."
        return "اسأل عن التوظيف." if ar else "Ask about hiring."
    if has_posthire and has_hiring:
        if ar:
            return f"اسأل عن التوظيف أو فريقك — {joined}."
        return f"Ask about hiring or your team — {joined}."
    if ar:
        return f"اسأل عن {joined}."
    return f"Ask about {joined}."


def empty_prompt_chips_from_catalog(catalog: dict[str, Any] | None, *, locale: str = "en") -> list[str]:
    """Grounded empty-state chips — only offerable capabilities."""

    ar = locale == "ar"
    if not isinstance(catalog, dict):
        return []
    offerable = set(catalog.get("offerable") or [])
    chips: list[str] = []

    def add(cid: str, en: str, ar_text: str) -> None:
        if cid in offerable and len(chips) < 6:
            chips.append(ar_text if ar else en)

    # Wave 1: Action Inbox is the default post-hire entry — surface first when offerable.
    add("posthire_action_inbox", "What needs attention in Action Inbox?", "ما الذي يحتاج انتباهاً في صندوق الإجراءات؟")
    # Wave 2: Safe Ops Queue Reads
    add("posthire_leave_queue", "Pending leave requests needing a decision", "طلبات إجازة معلّقة تحتاج قراراً")
    add("posthire_attendance_exceptions", "Attendance exceptions today", "استثناءات الحضور اليوم")
    add("posthire_employees_360", "Summarize an employee in Employees 360", "لخّص موظفاً في الموظفون 360")
    add("posthire_setup_readiness", "Launch readiness blockers", "عوائق جاهزية الإطلاق")
    # Prefer pre-hire operating surface next, then other post-hire when enabled.
    add("overview", "What should I work on today?", "بماذا أبدأ اليوم؟")
    add("jobs", "Create or update a job opening", "إنشاء أو تحديث وظيفة")
    add("candidates", "Review candidates", "مراجعة المرشحين")
    add("interviews_schedule", "Who needs an interview scheduled?", "من يحتاج جدولة مقابلة؟")
    add("calendar_events", "What's on the hiring calendar?", "ماذا في تقويم التوظيف؟")
    add("assessments", "Who needs an assessment?", "من يحتاج تقييمًا؟")
    add("ranking", "Show rankings", "عرض الترتيب")
    add("reports", "Hiring reports overview", "نظرة على تقارير التوظيف")
    add("posthire_onboarding", "Who is still onboarding?", "من ما زال في التهيئة؟")
    add("posthire_attendance", "Who was late today?", "من تأخر اليوم؟")
    add("posthire_leave", "Pending leave requests", "طلبات الإجازة المعلقة")
    add("posthire_shifts", "Open shifts this week", "الورديات المفتوحة هذا الأسبوع")
    add("posthire_payroll", "Payroll exceptions to review", "استثناءات الرواتب للمراجعة")
    add("posthire_compliance", "Documents expiring soon", "مستندات قاربت على الانتهاء")
    add("posthire_analytics", "Workforce attention summary", "ملخص ما يحتاج انتباهاً في القوى العاملة")
    return chips[:6]


def empty_state_from_catalog(catalog: dict[str, Any] | None, *, locale: str = "en") -> dict[str, Any]:
    """Single empty-state payload: headline, modules, chips from offerable capabilities only."""

    modules = empty_modules_from_catalog(catalog, locale=locale)
    chips = empty_prompt_chips_from_catalog(catalog, locale=locale)
    headline = empty_headline_from_catalog(catalog, locale=locale)
    has_capabilities = bool(modules) or bool(chips)
    return {
        "locale": "ar" if locale == "ar" else "en",
        "headline": headline,
        "modules": modules,
        "chips": chips,
        "has_capabilities": has_capabilities,
        "offerable": list((catalog or {}).get("offerable") or []) if isinstance(catalog, dict) else [],
    }
