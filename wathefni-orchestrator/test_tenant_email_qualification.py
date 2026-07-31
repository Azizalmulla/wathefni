"""Expanded Phase 1 email qualification: authority, isolation, API auth, dual-send, Graph semantics."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import microsoft_mail_send as mms
import tenant_email_authority as tea

ROOT = Path(__file__).resolve().parent


class _FakeCursor:
    def __init__(self, store: dict):
        self.store = store
        self._result = None
        self.rowcount = 0

    def execute(self, sql: str, params=None):
        sql_n = " ".join(sql.split()).lower()
        params = params or ()
        if sql_n.startswith("create table") or sql_n.startswith("alter table"):
            self._result = None
            return
        if "from company_email_settings where company_code" in sql_n and "insert" not in sql_n:
            company = params[0]
            row = self.store["settings"].get(company)
            self._result = dict(row) if row else None
            return
        if "insert into company_email_settings" in sql_n:
            company = params[0]
            self.store["settings"][company] = {
                "company_code": company,
                "outbound_mode": params[1],
                "display_name": params[2],
                "from_address": params[3],
                "reply_to": params[4],
                "company_name_en": params[5],
                "company_name_ar": params[6],
                "logo_url": params[7],
                "outbound_mailbox_id": params[8],
                "interview_email_when_calendar_sent": params[9],
                "allow_wathefni_emergency_fallback": params[10],
                "public_forward_address": params[11],
                "updated_by_user_id": params[12],
            }
            self._result = None
            return
        if "from company_operational_mailboxes where company_code=%s and mailbox_id" in sql_n:
            company, mailbox_id = params
            for row in self.store["mailboxes"].get(company, []):
                if str(row.get("mailbox_id")) == str(mailbox_id):
                    self._result = dict(row)
                    return
            self._result = None
            return
        if "from company_operational_mailboxes where company_code" in sql_n:
            company = params[0]
            rows = list(self.store["mailboxes"].get(company, []))
            if "status <> 'disabled'" in sql_n:
                rows = [r for r in rows if r.get("status") != "disabled"]
            self._result = rows
            return
        if "from company_email_domains where company_code" in sql_n:
            company = params[0]
            self._result = list(self.store["domains"].get(company, []))
            return
        if "insert into company_operational_mailboxes" in sql_n:
            company = params[1]
            row = {
                "mailbox_id": params[0],
                "company_code": company,
                "address": params[2],
                "display_name": params[3],
                "provider": params[4],
                "allow_send": params[5],
                "status": params[6],
                "entra_user_id": params[7],
                "exchange_scope_ref": params[8],
                "last_error": params[9],
                "last_probe_ok": None,
            }
            self.store["mailboxes"].setdefault(company, [])
            # upsert by address
            existing = [r for r in self.store["mailboxes"][company] if r["address"] == row["address"]]
            if existing:
                existing[0].update(row)
                self._result = dict(existing[0])
            else:
                self.store["mailboxes"][company].append(row)
                self._result = dict(row)
            return
        if "update company_operational_mailboxes" in sql_n and "last_probe" in sql_n:
            ok, err, _ok2, company, mailbox_id = params
            for row in self.store["mailboxes"].get(company, []):
                if str(row.get("mailbox_id")) == str(mailbox_id):
                    row["last_probe_ok"] = ok
                    row["last_error"] = err
                    if not ok:
                        row["status"] = "error"
                    self._result = dict(row)
                    return
            self._result = None
            return
        if "update company_operational_mailboxes" in sql_n:
            status, allow_send, last_error, scope, entra, company, mailbox_id = params
            for row in self.store["mailboxes"].get(company, []):
                if str(row.get("mailbox_id")) == str(mailbox_id):
                    row["status"] = status
                    if allow_send is not None:
                        row["allow_send"] = allow_send
                    row["last_error"] = last_error
                    if scope:
                        row["exchange_scope_ref"] = scope
                    if entra:
                        row["entra_user_id"] = entra
                    self._result = dict(row)
                    return
            self._result = None
            return
        self._result = None

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return self._result
        return [self._result] if self._result else []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeConn:
    def __init__(self, store: dict):
        self.store = store

    def cursor(self):
        return _FakeCursor(self.store)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeLegacy:
    def __init__(self):
        self.store = {"settings": {}, "mailboxes": {}, "domains": {}}

    def db_connect(self):
        return _FakeConn(self.store)

    def outbound_postmark_config(self):
        return {"from_address": "hr@wathefni.ai", "reply_to": "", "server_token": "tok", "message_stream": "outbound"}

    def outbound_postmark_available(self):
        return True


class AuthoritySemanticsTests(unittest.TestCase):
    def test_legacy_defaults_to_wathefni(self):
        resolved = tea.resolve_outbound_sender_pure(settings=None, global_from="hr@wathefni.ai")
        self.assertEqual(resolved["mode"], "wathefni")
        self.assertEqual(resolved["from_address"], "hr@wathefni.ai")
        self.assertFalse(resolved.get("emergency_fallback_used"))

    def test_unverified_company_from_rejected(self):
        resolved = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "postmark_company_domain", "from_address": "hr@acme.com"},
            global_from="hr@wathefni.ai",
            verified_domain_names=[],
            for_send=True,
        )
        self.assertFalse(resolved["activatable"])
        self.assertEqual(resolved["block_reason"], "company_domain_not_verified")
        self.assertFalse(resolved.get("emergency_fallback_used"))

    def test_no_silent_wathefni_fallback_when_branded_unavailable(self):
        resolved = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox", "allow_wathefni_emergency_fallback": False},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[],
            microsoft_configured=True,
            for_send=True,
        )
        self.assertEqual(resolved["mode"], "microsoft_mailbox")
        self.assertFalse(resolved["activatable"])
        self.assertNotEqual(resolved.get("from_address"), "hr@wathefni.ai")

    def test_emergency_fallback_explicit_and_auditable(self):
        resolved = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox", "allow_wathefni_emergency_fallback": True},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[],
            microsoft_configured=True,
            for_send=True,
        )
        self.assertTrue(resolved["emergency_fallback_used"])
        self.assertEqual(resolved["mode"], "wathefni")
        self.assertEqual(resolved["from_address"], "hr@wathefni.ai")
        self.assertEqual(resolved["intended_mode"], "microsoft_mailbox")
        self.assertIn("emergency fallback", (resolved.get("hr_notice") or "").lower())

    def test_microsoft_requires_approved_probed_mailbox_and_mail_sp(self):
        no_probe = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox"},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[{"address": "hr@a.com", "status": "approved", "allow_send": True, "last_probe_ok": False}],
            microsoft_configured=True,
        )
        self.assertFalse(no_probe["activatable"])

        no_sp = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox"},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[{"address": "hr@a.com", "status": "approved", "allow_send": True, "last_probe_ok": True}],
            microsoft_configured=False,
        )
        self.assertFalse(no_sp["activatable"])

        ready = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox"},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[{"address": "hr@a.com", "status": "approved", "allow_send": True, "last_probe_ok": True}],
            microsoft_configured=True,
        )
        self.assertTrue(ready["activatable"])
        self.assertEqual(ready["provider"], "microsoft_graph")

    def test_dual_send_requires_successful_calendar_attendee_invite(self):
        self.assertTrue(
            tea.should_skip_interview_email_pure(
                calendar_invite_sent=True,
                candidate_email="a@b.com",
                interview_email_when_calendar_sent=False,
            )
        )
        self.assertFalse(
            tea.should_skip_interview_email_pure(
                calendar_invite_sent=False,
                candidate_email="a@b.com",
                interview_email_when_calendar_sent=False,
            )
        )
        self.assertFalse(
            tea.should_skip_interview_email_pure(
                calendar_invite_sent=True,
                candidate_email="a@b.com",
                interview_email_when_calendar_sent=False,
                calendar_invite_failed=True,
            )
        )
        self.assertFalse(
            tea.should_skip_interview_email_pure(
                calendar_invite_sent=True,
                candidate_email="a@b.com",
                interview_email_when_calendar_sent=False,
                provider_sync_ok=False,
            )
        )
        self.assertFalse(
            tea.should_skip_interview_email_pure(
                calendar_invite_sent=True,
                candidate_email="a@b.com",
                interview_email_when_calendar_sent=False,
                explicit=True,
            )
        )


class TenantIsolationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = FakeLegacy()
        tea.upsert_operational_mailbox(
            self.legacy, "TENANT_A", address="hr@a.com", display_name="A", allow_send=True, status="approved"
        )
        tea.upsert_operational_mailbox(
            self.legacy, "TENANT_B", address="hr@b.com", display_name="B", allow_send=True, status="approved"
        )
        # mark probed
        a = tea.list_operational_mailboxes(self.legacy, "TENANT_A")[0]
        b = tea.list_operational_mailboxes(self.legacy, "TENANT_B")[0]
        tea.record_mailbox_probe(self.legacy, "TENANT_A", a["mailbox_id"], ok=True)
        tea.record_mailbox_probe(self.legacy, "TENANT_B", b["mailbox_id"], ok=True)
        self.legacy.store["domains"]["TENANT_A"] = [
            {"domain_id": "d1", "company_code": "TENANT_A", "domain": "a.com", "verification_status": "verified"}
        ]
        self.legacy.store["domains"]["TENANT_B"] = [
            {"domain_id": "d2", "company_code": "TENANT_B", "domain": "b.com", "verification_status": "verified"}
        ]

    def test_tenant_a_cannot_see_tenant_b_mailboxes_or_domains(self):
        a_boxes = tea.list_operational_mailboxes(self.legacy, "TENANT_A")
        b_boxes = tea.list_operational_mailboxes(self.legacy, "TENANT_B")
        self.assertTrue(all(r["address"].endswith("@a.com") for r in a_boxes))
        self.assertTrue(all(r["address"].endswith("@b.com") for r in b_boxes))
        self.assertEqual([d["domain"] for d in tea.list_email_domains(self.legacy, "TENANT_A")], ["a.com"])
        self.assertEqual([d["domain"] for d in tea.list_email_domains(self.legacy, "TENANT_B")], ["b.com"])

    def test_tenant_a_cannot_get_tenant_b_mailbox_by_id(self):
        b = tea.list_operational_mailboxes(self.legacy, "TENANT_B")[0]
        cross = tea.get_mailbox(self.legacy, "TENANT_A", b["mailbox_id"])
        self.assertIsNone(cross)

    def test_settings_scoped_per_company(self):
        tea.upsert_email_settings(self.legacy, "TENANT_A", {"display_name": "A Team"}, allow_unready_mode=True)
        tea.upsert_email_settings(self.legacy, "TENANT_B", {"display_name": "B Team"}, allow_unready_mode=True)
        self.assertEqual(tea.get_email_settings(self.legacy, "TENANT_A")["display_name"], "A Team")
        self.assertEqual(tea.get_email_settings(self.legacy, "TENANT_B")["display_name"], "B Team")


class MailSpSeparationTests(unittest.TestCase):
    def test_calendar_client_cannot_be_reused(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as fh:
            fh.write(b"dummy")
            fh.flush()
            with mock.patch.dict(
                os.environ,
                {
                    "WATHEFNI_M365_CLIENT_ID": "calendar-client",
                    "WATHEFNI_M365_MAIL_CLIENT_ID": "calendar-client",
                    "WATHEFNI_M365_MAIL_TENANT_ID": "tenant",
                    "WATHEFNI_M365_MAIL_CERT_BUNDLE_PATH": fh.name,
                },
                clear=False,
            ):
                self.assertTrue(mms.mail_send_configured())
                with self.assertRaises(RuntimeError) as ctx:
                    mms.mint_mail_graph_token()
                self.assertIn("must_differ", str(ctx.exception))

    def test_graph_accept_status_constant(self):
        src = (ROOT / "microsoft_mail_send.py").read_text(encoding="utf-8")
        self.assertIn("accepted_by_provider", src)
        self.assertNotIn('"provider_accept_status": "accepted"', src)
        self.assertNotIn("confirmed delivery", src.lower().replace("not confirmed", "NOT"))


class ApiAuthorizationSourceTests(unittest.TestCase):
    def test_company_email_routes_require_settings_manage(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # Extract email settings handlers and assert entitlement gate
        for marker in (
            "def dashboard_email_settings_get",
            "def dashboard_email_settings_put",
            "def dashboard_email_settings_action",
        ):
            idx = src.index(marker)
            chunk = src[idx : idx + 400]
            self.assertIn('require_entitlement(context, "pre_hiring", "settings.manage")', chunk)

    def test_superadmin_email_routes_use_superadmin_context(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for marker in (
            "def setup_console_email_admin_get",
            "def setup_console_email_seed_mailboxes",
            "def setup_console_email_mailbox_patch",
            "def setup_console_email_force_wathefni",
        ):
            idx = src.index(marker)
            chunk = src[idx : idx + 350]
            self.assertIn("Depends(superadmin_context)", chunk)

    def test_public_projection_has_no_internal_jargon(self):
        view_src = (ROOT / "tenant_email_authority.py").read_text(encoding="utf-8")
        # public_email_sending_view body should not expose these strings as UX copy
        public_fn = view_src[view_src.index("def public_email_sending_view") : view_src.index("def admin_email_snapshot")]
        for banned in ("service principal", "RBAC", "Mail.Send", "capability", "postmark_domain_id"):
            self.assertNotIn(banned, public_fn)


class InboundRegressionSourceTests(unittest.TestCase):
    def test_durable_ingress_untouched_by_email_authority(self):
        auth = (ROOT / "tenant_email_authority.py").read_text(encoding="utf-8")
        self.assertNotIn("durable_email_ingress", auth)
        ingress = ROOT / "durable_email_ingress.py"
        self.assertTrue(ingress.exists())
        ingress_src = ingress.read_text(encoding="utf-8")
        self.assertNotIn("tenant_email_authority", ingress_src)
        self.assertNotIn("microsoft_mail_send", ingress_src)
        # Local wave tests remain when present (not required on production hosts).
        for name in (
            "test_unified_inbound_cv_wave1.py",
            "test_unified_inbound_cv_phase0_contracts.py",
        ):
            path = ROOT / name
            if path.exists():
                self.assertNotIn("tenant_email_authority", path.read_text(encoding="utf-8"))


class IntegrationDispatchSemanticsTests(unittest.TestCase):
    def test_dispatch_source_fails_closed_without_emergency_fallback(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # Resolve must be called for_send=True and non-activatable path must return failed.
        self.assertIn("for_send=True", src)
        self.assertIn('if not resolved.get("activatable"):', src)
        self.assertIn('"provider_accept_status": "failed"', src)
        self.assertIn("emergency_fallback_used", src)
        self.assertIn("accepted_by_provider", src)

    def test_resolve_fail_closed_matches_dispatch_contract(self):
        resolved = tea.resolve_outbound_sender_pure(
            settings={"outbound_mode": "microsoft_mailbox", "allow_wathefni_emergency_fallback": False},
            global_from="hr@wathefni.ai",
            approved_mailboxes=[],
            microsoft_configured=True,
            for_send=True,
        )
        self.assertFalse(resolved["activatable"])
        self.assertEqual(resolved["block_reason"], "microsoft_mailbox_not_approved")
        self.assertFalse(resolved.get("emergency_fallback_used"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
