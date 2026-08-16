"""Unit tests for person-aware candidate identity resolution."""

from __future__ import annotations

import unittest
from unittest import mock

import unified_person_profile as upp


class ConfirmedIdentityTests(unittest.TestCase):
    def test_email_beats_phone_and_never_uses_name(self):
        row = {
            "app_key": "a1",
            "phone": "96550001111",
            "candidate_email": "hr@example.com",
            "candidate_name": "Same Name",
            "candidate_profile": {"contacts": {"email": "hr@example.com"}},
        }
        identity = upp.confirmed_identity_from_row(row)
        self.assertEqual(identity["identity_key"], "email:hr@example.com")
        self.assertEqual(identity["resolution_method"], "grounded_email")

    def test_candidates_table_email_alone_does_not_merge(self):
        row = {
            "app_key": "imp-noor",
            "phone": "imp-noor",
            "candidate_email": "shared@example.com",
            "candidate_name": "Noor",
            "raw_json": {},
            "candidate_profile": {},
        }
        identity = upp.confirmed_identity_from_row(row)
        self.assertEqual(identity["resolution_method"], "singleton")
        self.assertEqual(identity["identity_key"], "singleton:imp-noor")

    def test_surrogate_phone_without_grounded_contact_is_singleton(self):
        row = {
            "app_key": "imp-abc-WATHEFNI-IMPORT",
            "phone": "imp-abc-WATHEFNI-IMPORT",
            "candidate_name": "Noor Tahat",
        }
        identity = upp.confirmed_identity_from_row(row)
        self.assertEqual(identity["identity_key"], "singleton:imp-abc-WATHEFNI-IMPORT")
        self.assertEqual(identity["resolution_method"], "singleton")

    def test_person_id_beats_polluted_email(self):
        row = {
            "app_key": "a1",
            "phone": "imp-x",
            "person_id": "11111111-1111-1111-1111-111111111111",
            "candidate_name": "Ignored",
            "candidate_profile": {"email": "shared@example.com"},
        }
        identity = upp.confirmed_identity_from_row(row)
        self.assertEqual(identity["identity_key"], "person:11111111-1111-1111-1111-111111111111")
        self.assertEqual(identity["resolution_method"], "person_id")
        self.assertEqual(identity["email"], "shared@example.com")

    def test_person_id_used_when_no_grounded_contact(self):
        row = {
            "app_key": "a1",
            "phone": "imp-x",
            "person_id": "11111111-1111-1111-1111-111111111111",
            "candidate_name": "Ignored",
        }
        identity = upp.confirmed_identity_from_row(row)
        self.assertEqual(identity["identity_key"], "person:11111111-1111-1111-1111-111111111111")
        self.assertEqual(identity["resolution_method"], "person_id")


class ResolveKeysTests(unittest.TestCase):
    def test_singleton_does_not_merge_same_name_rows(self):
        anchor = {
            "app_key": "imp-one",
            "phone": "imp-one",
            "candidate_name": "Alex Same",
        }
        cur = mock.MagicMock()
        # person_id / email / phone queries unused for singleton
        cur.fetchall.return_value = []
        result = upp.resolve_person_application_keys(cur, company="WATHEFNI", anchor_row=anchor)
        self.assertEqual(result["app_keys"], ["imp-one"])
        self.assertEqual(result["resolution_method"], "singleton")

    def test_add_to_job_preflight_blocks_duplicate_position(self):
        profile = {
            "add_to_job": {
                "enabled": True,
                "held_app_key": "held-1",
                "blocked_position_codes": ["HR", "FINANCE"],
            }
        }
        denied = upp.person_add_to_job_preflight(profile, position_code="HR")
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["error"], "duplicate_active_application")
        ok = upp.person_add_to_job_preflight(profile, position_code="DRIVER")
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["held_app_key"], "held-1")

    def test_duplicate_wins_even_when_no_held_general(self):
        profile = {
            "add_to_job": {
                "enabled": False,
                "reason": "no_general_candidate_application",
                "held_app_key": None,
                "blocked_position_codes": ["J2P2_PROD_TEST"],
            }
        }
        denied = upp.person_add_to_job_preflight(profile, position_code="J2P2_PROD_TEST")
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["error"], "duplicate_active_application")
        self.assertEqual(denied.get("http_status"), 409)


if __name__ == "__main__":
    unittest.main()
