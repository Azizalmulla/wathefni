"""Unit tests for unified Candidates + Talent Pool authority (no DB required)."""

from __future__ import annotations

import unittest

import unified_candidates as uc


class UnifiedCandidatesAuthorityTests(unittest.TestCase):
    def test_surrogate_phone_hidden(self):
        self.assertTrue(uc.is_surrogate_phone("imp-wathefni-abc123"))
        self.assertFalse(uc.is_surrogate_phone("96550001111"))
        row = {
            "phone": "imp-wathefni-abc123",
            "raw_json": {"candidate_phone": "96550009999", "candidate_email": "noor@example.com"},
            "candidate_profile": {},
            "status": "needs_role",
        }
        self.assertEqual(uc.grounded_contact_phone(row), "96550009999")
        self.assertEqual(uc.grounded_contact_email(row), "noor@example.com")

    def test_record_states(self):
        self.assertEqual(uc.record_state_for({"status": "needs_role"}), uc.RECORD_TALENT_POOL)
        self.assertEqual(uc.record_state_for({"status": "import_review"}), uc.RECORD_TALENT_POOL)
        self.assertEqual(uc.record_state_for({"status": "import_archived"}), uc.RECORD_ARCHIVED)
        self.assertEqual(uc.record_state_for({"status": "hired"}), uc.RECORD_HIRED)
        self.assertEqual(uc.record_state_for({"status": "ready_for_review"}), uc.RECORD_ACTIVE)
        self.assertEqual(
            uc.record_state_for({"status": "needs_role"}, {"restriction_state": "restricted"}),
            uc.RECORD_RESTRICTED,
        )

    def test_held_allowed_actions_forbid_lifecycle(self):
        actions = uc.held_allowed_actions(
            {"prehire.read", "candidate.manage", "candidate.decide", "interview.manage", "assessment.manage"},
            cv_received=True,
        )
        self.assertEqual(actions, ["preview_cv", "download_cv"])
        for forbidden in (
            "shortlist",
            "reject",
            "hire",
            "notify",
            "send_assessment",
            "send_video_interview",
            "schedule_interview",
            "generate_evaluation",
        ):
            self.assertNotIn(forbidden, actions)

    def test_missing_facts_are_not_negative(self):
        summary = uc.completeness_summary({"skills": [], "languages": [], "education": []})
        labels = {item["label"] for item in summary}
        self.assertIn("Skills not extracted", labels)
        self.assertIn("Languages not extracted", labels)
        self.assertTrue(all("lacks" not in item["label"].lower() for item in summary))
        self.assertTrue(all("does not have" not in item["label"].lower() for item in summary))

    def test_privacy_not_configured_message(self):
        privacy = uc.privacy_projection({})
        self.assertFalse(privacy["configured"])
        self.assertEqual(privacy["message"], uc.PRIVACY_NOT_CONFIGURED)

    def test_fact_review_effective_precedence(self):
        snapshot = {
            "schema": "application-cv-facts-v1",
            "immutable": True,
            "snapshot": {"skills": ["Python"], "languages": []},
        }
        events = [
            {
                "fact_path": "skills",
                "action": "correct",
                "new_value": ["Python", "SQL"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "fact_path": "languages",
                "action": "add",
                "new_value": ["English", "Arabic"],
                "created_at": "2026-01-02T00:00:00Z",
            },
        ]
        effective = uc.effective_facts_from_events(snapshot, events)
        self.assertEqual(effective["effective"]["skills"], ["Python", "SQL"])
        self.assertEqual(effective["effective"]["languages"], ["English", "Arabic"])
        self.assertEqual(snapshot["snapshot"]["skills"], ["Python"])  # immutable

    def test_search_match_reasons_disclose(self):
        row = {
            "candidate_name": "Noor Tahat",
            "candidate_email": "noor@example.com",
            "phone": "imp-hidden",
            "raw_json": {"candidate_phone": "96550001111"},
            "candidate_profile": {
                "skills": ["Excel"],
                "education": [{"school": "Kuwait University"}],
            },
            "semantic_content": "experienced accountant with excel and reporting",
        }
        reasons = uc.search_match_reasons(query="Noor", row=row)
        self.assertIn(uc.MATCH_METADATA, reasons)
        reasons = uc.search_match_reasons(query="excel", row=row)
        self.assertTrue({uc.MATCH_CV_TEXT, uc.MATCH_EXTRACTED} & set(reasons))
        reasons = uc.search_match_reasons(query="Kuwait University", row=row)
        self.assertIn(uc.MATCH_EDUCATION, reasons)
        confirmed = {
            "reviews_by_path": {
                "skills": {"display_state": "hr_confirmed", "new_value": ["Confirmed Skill"]}
            }
        }
        reasons = uc.search_match_reasons(query="Confirmed Skill", row=row, effective_facts=confirmed)
        self.assertIn(uc.MATCH_CONFIRMED, reasons)

    def test_enrich_held_row_display(self):
        row = {
            "status": "needs_role",
            "phone": "imp-wathefni-xyz",
            "candidate_name": "Noor Tahat",
            "candidate_email": "noor@cv.example",
            "raw_json": {"candidate_email": "noor@cv.example", "cv": {"processing": {"status": "ready", "text_extracted": True, "profile_parsed": True}}},
            "candidate_profile": {"skills": ["Excel"]},
            "cv_received": True,
        }
        payload = {
            "status": "needs_role",
            "phone": "imp-wathefni-xyz",
            "position": {},
            "candidate": {"name": "Noor Tahat", "email": "noor@cv.example"},
            "cv": {"received": True},
            "status_label": "Talent Pool",
            "allowed_actions": ["shortlist", "notify"],
        }
        enriched = uc.enrich_application_summary(
            payload,
            row,
            permissions={"prehire.read", "candidate.manage", "candidate.decide"},
        )
        self.assertEqual(enriched["job_display"], "Not linked")
        self.assertEqual(enriched["status_display"], "Talent Pool")
        self.assertEqual(enriched["communication_display"], "No outreach")
        self.assertEqual(enriched["assessment_display"], "—")
        self.assertEqual(enriched["recruiter_owner"]["label"], "Unassigned")
        self.assertNotIn("shortlist", enriched["allowed_actions"])
        self.assertNotIn("notify", enriched["allowed_actions"])
        self.assertTrue(enriched["identity"]["compatibility_key_hidden"])
        self.assertFalse(enriched["link_to_job"]["enabled"])
        self.assertNotIn("imp-", enriched.get("phone") or "")

    def test_view_predicates_exclude_restricted_from_all(self):
        sql, _ = uc.view_predicate_sql(uc.VIEW_ALL)
        self.assertIn("needs_role", sql)
        self.assertIn("restriction_state", sql)
        sql_tp, _ = uc.view_predicate_sql(uc.VIEW_TALENT_POOL)
        self.assertIn("import_review", sql_tp)
        self.assertNotIn("hired", sql_tp.lower().split("in")[0] if False else sql_tp)


if __name__ == "__main__":
    unittest.main()
