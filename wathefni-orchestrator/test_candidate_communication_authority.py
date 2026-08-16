#!/usr/bin/env python3
"""Unit tests for held-record candidate communication authority."""

from __future__ import annotations

import unittest
from unittest import mock

import candidate_communication_authority as auth


def _app(**overrides):
    row = {
        "app_key": "LIVE-APP-001",
        "company_code": "WATHEFNI",
        "status": "ready_for_review",
        "phone": "96550001111",
        "data_source": "production",
        "candidate_name": "Live Candidate",
        "raw_json": {},
    }
    row.update(overrides)
    return row


class CandidateCommunicationAuthorityTests(unittest.TestCase):
    def test_live_application_allowed(self):
        decision = auth.evaluate_candidate_communication_authority(_app())
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["reason"], "live_application")

    def test_held_statuses_denied(self):
        for status in auth.HELD_IMPORT_STATUSES:
            with self.subTest(status=status):
                decision = auth.evaluate_candidate_communication_authority(_app(status=status))
                self.assertFalse(decision["allowed"])
                self.assertEqual(decision["code"], auth.ERROR_HELD)
                with self.assertRaises(auth.CandidateCommunicationAuthorityError) as ctx:
                    auth.assert_candidate_communication_allowed(_app(status=status), kind="notify")
                self.assertEqual(ctx.exception.status_code, 409)
                self.assertEqual(ctx.exception.code, auth.ERROR_HELD)

    def test_restricted_and_deletion_pending_denied(self):
        for gov in (
            {"restriction_state": "restricted"},
            {"deletion_request_state": "pending"},
            {"deletion_request_state": "requested"},
            {"archive_state": "archived"},
        ):
            with self.subTest(gov=gov):
                decision = auth.evaluate_candidate_communication_authority(_app(), governance=gov)
                self.assertFalse(decision["allowed"])
                self.assertEqual(decision["code"], auth.ERROR_RESTRICTED)

    def test_tenant_mismatch_denied(self):
        decision = auth.evaluate_candidate_communication_authority(
            _app(),
            expected_company_code="OTHER",
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["code"], auth.ERROR_TENANT)

    def test_non_production_and_test_identity_denied(self):
        self.assertFalse(
            auth.evaluate_candidate_communication_authority(_app(data_source="smoke_test"))["allowed"]
        )
        self.assertFalse(
            auth.evaluate_candidate_communication_authority(_app(app_key="APP-TEST-001"))["allowed"]
        )
        self.assertFalse(
            auth.evaluate_candidate_communication_authority(_app(candidate_name="Test Person"))["allowed"]
        )

    def test_missing_application_denied(self):
        decision = auth.evaluate_candidate_communication_authority(None)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["code"], auth.ERROR_MISSING)

    def test_filter_live_applications_for_bulk(self):
        apps = [
            _app(app_key="LIVE-1", status="ready_for_review"),
            _app(app_key="HELD-1", status="needs_role"),
            _app(app_key="HELD-2", status="import_review"),
        ]
        split = auth.filter_live_applications_for_communication(apps, kind="notify")
        self.assertEqual(split["allowed_count"], 1)
        self.assertEqual(split["denied_count"], 2)
        self.assertEqual(split["allowed"][0]["app_key"], "LIVE-1")

    def test_error_payload_has_no_side_effect_hints(self):
        try:
            auth.assert_candidate_communication_allowed(_app(status="needs_role"), kind="whatsapp")
        except auth.CandidateCommunicationAuthorityError as exc:
            detail = exc.as_detail()
            result = exc.as_result()
            self.assertEqual(detail["error"], auth.ERROR_HELD)
            self.assertFalse(result["ok"])
            self.assertIn("Talent Pool held", result["message"])


class CommunicationHelperGateTests(unittest.TestCase):
    """Gate notify/email/router helpers without provider or DB side effects."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as app_mod
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"app import unavailable locally: {exc}") from exc
        cls.app_mod = app_mod

    def setUp(self):
        self.app = self.app_mod
        self.held = _app(status="needs_role", app_key="HELD-LOCAL-001")
        self.live = _app(status="ready_for_review", app_key="LIVE-LOCAL-001")

    def test_notify_candidate_held_returns_authority_error_without_provider(self):
        with mock.patch.object(self.app, "send_octopus_whatsapp") as send:
            with mock.patch.object(self.app, "load_candidate_communication_governance", return_value=None):
                result = self.app.notify_candidate(self.held, "default", "hello")
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("error"), auth.ERROR_HELD)
        send.assert_not_called()

    def test_send_email_held_returns_authority_error_without_provider(self):
        with mock.patch.object(self.app, "dispatch_outbound_email") as send:
            with mock.patch.object(self.app, "record_outbound_delivery_event") as record:
                with mock.patch.object(self.app, "load_candidate_communication_governance", return_value=None):
                    result = self.app.send_email(self.held, {"purpose": "notification", "account_id": "default"})
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("error"), auth.ERROR_HELD)
        send.assert_not_called()
        record.assert_not_called()

    def test_router_held_returns_authority_error_without_channels(self):
        with mock.patch.object(self.app, "send_email") as email:
            with mock.patch.object(self.app, "notify_candidate") as notify:
                with mock.patch.object(self.app, "load_candidate_communication_governance", return_value=None):
                    result = self.app.candidate_communication_router(
                        self.held,
                        account_id="default",
                        kind="notification",
                        message="hi",
                    )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("error"), auth.ERROR_HELD)
        self.assertEqual(result.get("attempts"), [])
        email.assert_not_called()
        notify.assert_not_called()

    def test_live_notify_still_calls_provider(self):
        with mock.patch.object(self.app, "send_octopus_whatsapp", return_value={"ok": True, "dry_run": True}) as send:
            with mock.patch.object(self.app, "load_candidate_communication_governance", return_value=None):
                with mock.patch.object(
                    self.app,
                    "candidate_contact",
                    return_value={"name": "Live", "phone": "96550001111", "email": "a@b.com"},
                ):
                    result = self.app.notify_candidate(self.live, "default", "hello")
        self.assertTrue(result.get("ok"))
        send.assert_called_once()

    def test_require_live_raises_http_for_held(self):
        with mock.patch.object(self.app, "load_candidate_communication_governance", return_value=None):
            with self.assertRaises(self.app.HTTPException) as ctx:
                self.app.require_live_candidate_communication(
                    self.held,
                    kind="notify",
                    expected_company_code="WATHEFNI",
                )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["error"], auth.ERROR_HELD)


class RegistryCommunicationGateTests(unittest.TestCase):
    def test_notify_executor_denies_held(self):
        import action_registry as registry

        legacy = mock.Mock(
            spec=[
                "resolve_application_for_action",
                "assert_application_communication_allowed",
                "json_safe",
                "candidate_communication_router",
            ]
        )
        legacy.resolve_application_for_action.return_value = _app(status="import_archived", app_key="HELD-AR")
        legacy.assert_application_communication_allowed.side_effect = auth.CandidateCommunicationAuthorityError(
            auth.ERROR_HELD,
            "held",
            status_code=409,
            reason="held_status:import_archived",
        )
        legacy.json_safe.side_effect = lambda value: value
        ctx = registry.ExecutionContext(
            request=mock.Mock(account_id="default"),
            action={"action_type": "notify_candidate", "app_key": "HELD-AR"},
            state={},
            graph_state={},
            intent={},
            legacy=legacy,
        )
        result = registry._notify_candidate_executor(ctx)
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error"), auth.ERROR_HELD)
        legacy.candidate_communication_router.assert_not_called()


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
