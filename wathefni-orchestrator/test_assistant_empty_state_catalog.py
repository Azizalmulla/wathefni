"""Capability catalog empty-state matrix tests."""

from __future__ import annotations

import assistant_capability_catalog as caps


class _BaseLegacy:
    def configured_company_modules(self, company_code):
        return {"pre_hiring", "assessments", "interviews", "leave", "attendance", "onboarding", "payroll", "shifts", "compliance", "analytics"}

    def openclaw_env(self):
        return {"GOG_ACCOUNT": "hr@example.com"}

    def setup_console_channel_policy(self, company_code):
        return {"pre_hiring": {"company_whatsapp": {"configured": True}} }

    def db_connect(self):
        raise RuntimeError("no db in unit test")


def _tools(*names):
    return [{"function": {"name": name}} for name in names]


PREHIRE_TOOLS = _tools(
    "list_job_openings",
    "get_candidate_status",
    "rank_candidates",
    "get_prehire_work_queue",
    "get_reports_metrics",
    "schedule_interview",
    "send_assessment",
    "send_email",
    "notify_candidate",
)

POSTHIRE_TOOLS = _tools(
    "list_leave_requests",
    "list_attendance",
    "list_shifts",
    "list_onboarding_status",
    "list_compliance_documents",
    "list_payroll_hours",
    "workforce_analytics",
)


def _force_providers_off():
    import interview_lifecycle as life
    import interview_microsoft_calendar as mcal

    originals = {
        "google": life.google_calendar_configured,
        "ms_env": mcal.microsoft_env_configured,
        "ms_cal": caps._microsoft_calendar_configured,
        "email": caps._email_configured,
        "wa": caps._whatsapp_configured,
    }
    life.google_calendar_configured = lambda legacy: False
    mcal.microsoft_env_configured = lambda: False
    caps._microsoft_calendar_configured = lambda legacy, company: False
    caps._email_configured = lambda legacy, company=None: False
    caps._whatsapp_configured = lambda legacy, company: False
    return originals


def _restore_providers(originals):
    import interview_lifecycle as life
    import interview_microsoft_calendar as mcal

    life.google_calendar_configured = originals["google"]
    mcal.microsoft_env_configured = originals["ms_env"]
    caps._microsoft_calendar_configured = originals["ms_cal"]
    caps._email_configured = originals["email"]
    caps._whatsapp_configured = originals["wa"]


def test_hiring_only_empty_state():
    class HiringOnly(_BaseLegacy):
        def configured_company_modules(self, company_code):
            return {"pre_hiring"}

    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=HiringOnly(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "jobs.read"],
            visible_tools=PREHIRE_TOOLS,
        )
        empty = caps.empty_state_from_catalog(catalog, locale="en")
        assert empty["has_capabilities"] is True
        assert "payroll" not in " ".join(empty["modules"]).lower()
        assert "assessments" not in " ".join(empty["modules"]).lower()
        assert any("candidate" in m.lower() or "ranking" in m.lower() or "follow" in m.lower() for m in empty["modules"])
        assert all("payroll" not in c.lower() for c in empty["chips"])
        assert all("assessment" not in c.lower() for c in empty["chips"])
        ar = caps.empty_state_from_catalog(catalog, locale="ar")
        assert ar["headline"]
        assert ar["locale"] == "ar"
    finally:
        _restore_providers(originals)


def test_mixed_pre_post_hire_empty_state():
    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=_BaseLegacy(),
            company_code="WATHEFNI",
            permissions=[
                "prehire.read",
                "jobs.read",
                "leave.read",
                "attendance.read",
                "onboarding.read",
            ],
            visible_tools=PREHIRE_TOOLS + POSTHIRE_TOOLS,
        )
        empty = caps.empty_state_from_catalog(catalog, locale="en")
        joined = " ".join(empty["modules"]).lower()
        assert "candidates" in joined or "rankings" in joined
        assert "leave" in joined or "attendance" in joined or "onboarding" in joined
        assert "hiring or your team" in empty["headline"].lower()
        assert "payroll" not in joined  # no payroll.read
        assert all("payroll" not in c.lower() for c in empty["chips"])
    finally:
        _restore_providers(originals)


def test_disabled_payroll_never_advertised():
    class NoPayroll(_BaseLegacy):
        def configured_company_modules(self, company_code):
            return {"pre_hiring", "leave", "attendance"}

    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=NoPayroll(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "leave.read", "attendance.read", "payroll.read"],
            visible_tools=PREHIRE_TOOLS + POSTHIRE_TOOLS,
        )
        assert catalog["capabilities"]["posthire_payroll"]["offerable"] is False
        empty = caps.empty_state_from_catalog(catalog, locale="en")
        assert all("payroll" not in m.lower() for m in empty["modules"])
        assert all("payroll" not in c.lower() for c in empty["chips"])
        assert "payroll" not in empty["headline"].lower()
    finally:
        _restore_providers(originals)


def test_restricted_recruiter_hides_unauthorized():
    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=_BaseLegacy(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "jobs.read"],  # no interview/assessment/posthire
            visible_tools=PREHIRE_TOOLS + POSTHIRE_TOOLS,
        )
        empty = caps.empty_state_from_catalog(catalog, locale="en")
        text = (empty["headline"] + " " + " ".join(empty["modules"]) + " " + " ".join(empty["chips"])).lower()
        assert "interview" not in text
        assert "assessment" not in text
        assert "payroll" not in text
        assert "leave" not in text
        assert catalog["capabilities"]["interviews_schedule"]["status"] == caps.STATUS_DENIED
        assert catalog["capabilities"]["assessments"]["status"] in {
            caps.STATUS_DENIED,
            caps.STATUS_MODULE_OFF,
        }
    finally:
        _restore_providers(originals)


def test_enabled_but_unconfigured_providers_not_offerable():
    class InterviewsOn(_BaseLegacy):
        def configured_company_modules(self, company_code):
            return {"pre_hiring", "interviews"}

    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=InterviewsOn(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "interview.manage"],
            visible_tools=_tools("schedule_interview", "get_candidate_status"),
        )
        assert catalog["capabilities"]["google_meet"]["status"] == caps.STATUS_NOT_CONFIGURED
        assert catalog["capabilities"]["google_meet"]["offerable"] is False
        assert catalog["capabilities"]["teams_meet"]["offerable"] is False
        empty = caps.empty_state_from_catalog(catalog, locale="en")
        # interviews_schedule itself may still be offerable (tool+perm), but Teams/Meet provider chips
        # must not invent provider-specific prompts beyond schedule when only schedule is offerable.
        assert "teams" not in " ".join(empty["chips"]).lower()
        assert "google meet" not in " ".join(empty["chips"]).lower()
    finally:
        _restore_providers(originals)


def test_neutral_fallback_when_nothing_offerable():
    class EmptyTenant(_BaseLegacy):
        def configured_company_modules(self, company_code):
            return set()

    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=EmptyTenant(),
            company_code="WATHEFNI",
            permissions=[],
            visible_tools=[],
        )
        empty_en = caps.empty_state_from_catalog(catalog, locale="en")
        empty_ar = caps.empty_state_from_catalog(catalog, locale="ar")
        assert empty_en["has_capabilities"] is False
        assert empty_en["modules"] == []
        assert empty_en["headline"] == "What can you help me with?"
        assert empty_en["chips"] == []
        assert empty_ar["headline"] == "بماذا يمكنني المساعدة؟"
        assert empty_ar["chips"] == []
    finally:
        _restore_providers(originals)


def test_ar_en_parity_chip_counts():
    originals = _force_providers_off()
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=_BaseLegacy(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "jobs.read", "leave.read", "assessment.manage"],
            visible_tools=PREHIRE_TOOLS + POSTHIRE_TOOLS,
        )
        en = caps.empty_state_from_catalog(catalog, locale="en")
        ar = caps.empty_state_from_catalog(catalog, locale="ar")
        assert len(en["chips"]) == len(ar["chips"])
        assert len(en["modules"]) == len(ar["modules"])
        assert en["has_capabilities"] == ar["has_capabilities"]
    finally:
        _restore_providers(originals)


if __name__ == "__main__":
    test_hiring_only_empty_state()
    test_mixed_pre_post_hire_empty_state()
    test_disabled_payroll_never_advertised()
    test_restricted_recruiter_hides_unauthorized()
    test_enabled_but_unconfigured_providers_not_offerable()
    test_neutral_fallback_when_nothing_offerable()
    test_ar_en_parity_chip_counts()
    print("empty-state capability matrix PASS")
