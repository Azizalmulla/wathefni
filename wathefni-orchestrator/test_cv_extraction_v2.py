"""Unit tests for CV Extraction V2 schema + non-destructive validation."""

from __future__ import annotations

import unittest

import cv_extraction_v2 as cv2
import cv_extraction_v2_schema as schema


class CvExtractionV2Tests(unittest.TestCase):
    def test_schema_has_required_sections(self):
        body = schema.cv_extraction_v2_json_schema()
        for key in (
            "employment",
            "volunteer_work",
            "education",
            "skills",
            "languages",
            "publications",
            "training_courses",
            "memberships_activities",
            "awards_honors",
            "unmodeled_sections",
        ):
            self.assertIn(key, body["properties"])
            self.assertIn(key, body["required"])
        self.assertFalse(body.get("additionalProperties"))

    def test_validate_moves_contaminated_skills_to_unmodeled(self):
        raw = {
            "schema_version": "cv-extraction-v2",
            "skills": [
                {"name": "Python"},
                {"name": "Selected Publications & Reports"},
                {"name": "ref@example.com"},
            ],
            "languages": [],
            "employment": [],
            "volunteer_work": [],
            "education": [{"degree": "BSc", "institution": "KU"}],
            "projects": [],
            "publications": [],
            "certifications": [],
            "training_courses": [],
            "memberships_activities": [],
            "awards_honors": [],
            "references": [],
            "unmodeled_sections": [],
        }
        result = cv2.validate_v2_payload(raw)
        self.assertTrue(result["ok"])
        names = [i.get("name") for i in result["payload"]["skills"]]
        self.assertEqual(names, ["Python"])
        self.assertGreaterEqual(len(result["payload"]["unmodeled_sections"]), 2)

    def test_validate_recovers_languages_from_text(self):
        raw = cv2.empty_payload()
        raw["education"] = [{"degree": "BSc"}]
        text = "Additional Information\nLanguages: Arabic, English\n"
        result = cv2.validate_v2_payload(raw, source_text=text)
        langs = [i.get("language") for i in result["payload"]["languages"]]
        self.assertEqual(langs, ["Arabic", "English"])

    def test_project_profile_facts_v2_keeps_sections(self):
        payload = cv2.empty_payload()
        payload["employment"] = [
            {"title": "Analyst", "company": "A", "start_date": "2020", "end_date": "2021"},
            {"title": "Manager", "company": "B", "start_date": "2021", "end_date": "2023"},
        ]
        payload["volunteer_work"] = [{"role": "Tutor", "organization": "NGO"}]
        payload["languages"] = [{"language": "Arabic"}, {"language": "English"}]
        payload["publications"] = [{"title": "Report One"}]
        payload["training_courses"] = [{"name": "Bootcamp"}]
        payload["memberships_activities"] = [{"name": "IEEE"}]
        payload["awards_honors"] = [{"title": "Dean List", "issuing_organization": "KU"}]
        profile = cv2.project_profile_facts_v2(payload)
        self.assertEqual(profile["schema"], "candidate-profile-facts-v2")
        self.assertEqual(len(profile["employment"]), 2)
        self.assertEqual(len(profile["volunteer_work"]), 1)
        self.assertEqual(len(profile["languages"]), 2)
        self.assertEqual(len(profile["publications"]), 1)
        self.assertEqual(len(profile["training_courses"]), 1)
        self.assertEqual(len(profile["memberships_activities"]), 1)
        self.assertEqual(len(profile["awards_honors"]), 1)

    def test_empty_extraction_blocks_publication(self):
        result = cv2.validate_v2_payload(cv2.empty_payload())
        self.assertFalse(result["ok"])
        self.assertIn("empty_extraction", result["blocking"])


if __name__ == "__main__":
    unittest.main()
