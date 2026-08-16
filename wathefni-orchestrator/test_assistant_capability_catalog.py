"""Capability catalog + assistant policy wiring tests."""

from __future__ import annotations

import assistant_capability_catalog as caps
import assistant_policy as policy


class _Legacy:
    def configured_company_modules(self, company_code):
        return {"pre_hiring", "assessments", "interviews", "leave"}

    def openclaw_env(self):
        return {"GOG_ACCOUNT": "hr@example.com"}

    def setup_console_channel_policy(self, company_code):
        return {"pre_hiring": {"company_whatsapp": {"configured": True}}}

    def db_connect(self):
        raise RuntimeError("no db in unit test")

    def outbound_postmark_available(self):
        return False


def _tools(*names):
    return [{"function": {"name": name}} for name in names]


def test_capability_matrix_hides_denied_and_unconfigured():
    catalog = caps.build_assistant_capability_catalog(
        legacy=_Legacy(),
        company_code="WATHEFNI",
        permissions=["prehire.read", "jobs.read"],  # no interview.manage / candidate.manage
        visible_tools=_tools(
            "list_job_openings",
            "get_candidate_status",
            "rank_candidates",
            "get_prehire_work_queue",
            "get_reports_metrics",
            "schedule_interview",
            "send_email",
            "notify_candidate",
        ),
    )
    assert catalog["capabilities"]["reports"]["status"] == caps.STATUS_AVAILABLE
    assert catalog["capabilities"]["interviews_schedule"]["status"] == caps.STATUS_DENIED
    assert catalog["capabilities"]["email"]["status"] in {
        caps.STATUS_DENIED,
        caps.STATUS_NOT_CONFIGURED,
    }
    assert "interviews_schedule" not in catalog["offerable"]
    chips = caps.empty_prompt_chips_from_catalog(catalog)
    assert all("interview" not in c.lower() for c in chips)


def test_capability_matrix_marks_provider_not_configured(monkeypatch=None):
    class NoProviders(_Legacy):
        def openclaw_env(self):
            return {}

        def setup_console_channel_policy(self, company_code):
            return {"pre_hiring": {"company_whatsapp": {"configured": False}}}

    # Force provider probes off regardless of developer machine env.
    import interview_lifecycle as life

    original = life.google_calendar_configured
    life.google_calendar_configured = lambda legacy: False
    original_email = caps._email_configured
    caps._email_configured = lambda legacy, company=None: False
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=NoProviders(),
            company_code="WATHEFNI",
            permissions=["prehire.read", "candidate.manage", "interview.manage"],
            visible_tools=_tools("schedule_interview", "send_email", "notify_candidate"),
        )
        assert catalog["providers"]["google_calendar"] is False
        assert catalog["providers"]["whatsapp"] is False
        assert catalog["capabilities"]["google_meet"]["status"] == caps.STATUS_NOT_CONFIGURED
        assert catalog["capabilities"]["whatsapp"]["status"] == caps.STATUS_NOT_CONFIGURED
        assert catalog["capabilities"]["google_meet"]["offerable"] is False
    finally:
        life.google_calendar_configured = original
        caps._email_configured = original_email


def test_module_off_hides_assessments():
    class NoAssessments(_Legacy):
        def configured_company_modules(self, company_code):
            return {"pre_hiring"}

    catalog = caps.build_assistant_capability_catalog(
        legacy=NoAssessments(),
        company_code="WATHEFNI",
        permissions=["assessment.manage", "prehire.read"],
        visible_tools=_tools("send_assessment"),
    )
    # Tool may still be in list but module off should win when module gated
    assert catalog["capabilities"]["assessments"]["status"] in {
        caps.STATUS_MODULE_OFF,
        caps.STATUS_DENIED,
    }


def test_live_interview_caps_require_interviews_module_not_pre_hiring():
    class PreHiringOnly(_Legacy):
        def configured_company_modules(self, company_code):
            return {"pre_hiring", "video_interviews"}

    catalog = caps.build_assistant_capability_catalog(
        legacy=PreHiringOnly(),
        company_code="WATHEFNI",
        permissions=["interview.manage", "prehire.read", "candidate.manage"],
        visible_tools=_tools(
            "schedule_interview",
            "reschedule_interview",
            "cancel_interview",
            "send_video_interview",
        ),
    )
    for key in ("interviews_schedule", "interviews_reschedule", "interviews_cancel", "google_meet", "teams_meet", "calendar_events"):
        assert catalog["capabilities"][key]["status"] == caps.STATUS_MODULE_OFF, key
        assert catalog["capabilities"][key]["module"] == "interviews", key
        assert key not in catalog["offerable"]
    assert catalog["capabilities"]["video_interviews"]["status"] in {
        caps.STATUS_AVAILABLE,
        caps.STATUS_DENIED,
        caps.STATUS_NOT_CONFIGURED,
        caps.STATUS_MODULE_OFF,
    }


def test_live_interview_caps_available_when_interviews_on():
    catalog = caps.build_assistant_capability_catalog(
        legacy=_Legacy(),
        company_code="WATHEFNI",
        permissions=["interview.manage", "prehire.read", "candidate.manage", "jobs.read"],
        visible_tools=_tools("schedule_interview", "reschedule_interview", "cancel_interview"),
    )
    assert catalog["capabilities"]["interviews_schedule"]["status"] == caps.STATUS_AVAILABLE
    assert catalog["capabilities"]["interviews_schedule"]["module"] == "interviews"
    assert "interviews_schedule" in catalog["offerable"]


def test_reports_policy_classifiers():
    assert policy.is_reports_metric_question("What is our time to hire?")
    assert not policy.is_overview_operational_question("What is our time to hire?")
    assert policy.is_overview_operational_question("What should I work on today?")
    msg = policy.reports_parity_unavailable_message(locale_hint="en")
    assert msg["overview_is_not_reports"] is True
    assert "Reports" in msg["message"]


def test_capability_prompt_block_lists_statuses():
    catalog = caps.build_assistant_capability_catalog(
        legacy=_Legacy(),
        company_code="WATHEFNI",
        permissions=["prehire.read", "interview.manage", "candidate.manage", "jobs.read"],
        visible_tools=_tools(
            "list_job_openings",
            "schedule_interview",
            "send_email",
            "notify_candidate",
            "get_reports_metrics",
        ),
    )
    block = caps.capability_prompt_block(catalog)
    assert "AVAILABLE" in block
    assert "reports:" in block


def test_email_configured_recognizes_postmark_env(monkeypatch=None):
    """Wave B/C: Postmark Wathefni transport must count as configured."""
    import os

    saved = {k: os.environ.get(k) for k in (
        "WATHEFNI_POSTMARK_SERVER_TOKEN",
        "WATHEFNI_OUTBOUND_FROM",
        "WATHEFNI_EMAIL_PROVIDER",
        "SMTP_HOST",
        "RESEND_API_KEY",
        "SENDGRID_API_KEY",
        "WATHEFNI_OUTBOUND_EMAIL_PROVIDER",
    )}
    for k in saved:
        os.environ.pop(k, None)
    try:
        assert caps._email_configured(_Legacy(), "WATHEFNI") is False
        os.environ["WATHEFNI_POSTMARK_SERVER_TOKEN"] = "pm-test-token"
        os.environ["WATHEFNI_OUTBOUND_FROM"] = "hr@wathefni.ai"
        assert caps._email_env_transport_configured() is True
        assert caps._email_configured(_Legacy(), "WATHEFNI") is True
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_email_configured_via_outbound_postmark_available():
    class WithPostmark(_Legacy):
        def outbound_postmark_available(self):
            return True

    assert caps._email_configured(WithPostmark(), "WATHEFNI") is True


def test_email_configured_aligns_with_integrations_wathefni_ready():
    """When Settings reports wathefni/ready, Assistant email must be offerable-ready."""
    import tenant_email_authority as tea

    original = tea.public_email_sending_view

    def fake_view(legacy, company, *, intake_addresses=None):
        return {
            "company_code": company,
            "current_sender": "wathefni",
            "status": "ready",
            "visible_from": "hr@wathefni.ai",
        }

    class DbLegacy(_Legacy):
        def db_connect(self):
            raise AssertionError("view stub should not hit db")

        def outbound_postmark_available(self):
            return False

    tea.public_email_sending_view = fake_view
    original_env = caps._email_env_transport_configured
    caps._email_env_transport_configured = lambda: False
    try:
        assert caps._email_configured(DbLegacy(), "WATHEFNI") is True
        catalog = caps.build_assistant_capability_catalog(
            legacy=DbLegacy(),
            company_code="WATHEFNI",
            permissions=["candidate.manage", "prehire.read"],
            visible_tools=_tools("send_email"),
        )
        assert catalog["providers"]["email"] is True
        assert catalog["capabilities"]["email"]["status"] == caps.STATUS_AVAILABLE
        assert catalog["capabilities"]["email"]["offerable"] is True
    finally:
        tea.public_email_sending_view = original
        caps._email_env_transport_configured = original_env


def test_email_configured_microsoft_fail_closed_when_not_ready():
    """Branded Microsoft sender that is not ready must not look configured."""
    import tenant_email_authority as tea

    original = tea.public_email_sending_view

    def fake_view(legacy, company, *, intake_addresses=None):
        return {
            "company_code": company,
            "current_sender": "microsoft_mailbox",
            "status": "setup_required",
            "visible_from": None,
        }

    class DbLegacy(_Legacy):
        def outbound_postmark_available(self):
            return True  # Postmark exists globally — must NOT override branded fail-closed

    tea.public_email_sending_view = fake_view
    try:
        assert caps._email_configured(DbLegacy(), "WATHEFNI") is False
        catalog = caps.build_assistant_capability_catalog(
            legacy=DbLegacy(),
            company_code="WATHEFNI",
            permissions=["candidate.manage", "prehire.read"],
            visible_tools=_tools("send_email"),
        )
        assert catalog["providers"]["email"] is False
        assert catalog["capabilities"]["email"]["status"] == caps.STATUS_NOT_CONFIGURED
        assert catalog["capabilities"]["email"]["offerable"] is False
    finally:
        tea.public_email_sending_view = original


def test_email_configured_microsoft_ready_is_configured():
    import tenant_email_authority as tea

    original = tea.public_email_sending_view

    def fake_view(legacy, company, *, intake_addresses=None):
        return {
            "company_code": company,
            "current_sender": "microsoft_mailbox",
            "status": "ready",
            "visible_from": "hr@contoso.invalid",
        }

    tea.public_email_sending_view = fake_view
    try:
        assert caps._email_configured(_Legacy(), "ACME") is True
    finally:
        tea.public_email_sending_view = original


if __name__ == "__main__":
    test_capability_matrix_hides_denied_and_unconfigured()
    test_capability_matrix_marks_provider_not_configured()
    test_module_off_hides_assessments()
    test_live_interview_caps_require_interviews_module_not_pre_hiring()
    test_live_interview_caps_available_when_interviews_on()
    test_reports_policy_classifiers()
    test_capability_prompt_block_lists_statuses()
    test_email_configured_recognizes_postmark_env()
    test_email_configured_via_outbound_postmark_available()
    test_email_configured_aligns_with_integrations_wathefni_ready()
    test_email_configured_microsoft_fail_closed_when_not_ready()
    test_email_configured_microsoft_ready_is_configured()
    print("capability unit PASS")
