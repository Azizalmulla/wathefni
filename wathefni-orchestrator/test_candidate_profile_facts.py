"""Unit tests for candidate-profile-facts-v1 normalization."""

from __future__ import annotations

import unittest

import candidate_profile_facts as cpf


class CanonicalProfileFactsTests(unittest.TestCase):
    def test_unwraps_value_objects_to_strings(self):
        raw = {
            "skills": [
                {"value": "Python", "source": {"quote": "Python"}, "confidence": 0.9},
                {"value": "React", "confidence": 0.9},
            ],
            "education": [{"value": "BSc Computer Science, Kuwait"}],
            "employment": [{"role": "Intern · Acme", "confidence": 0.8}],
            "languages": [],
            "experience_years": {"value": 2, "method": "explicit_text"},
        }
        profile = cpf.build_canonical_profile_facts(raw_facts=raw)
        self.assertEqual(profile["schema"], "candidate-profile-facts-v1")
        self.assertEqual(profile["skills"][0], "Python")
        self.assertTrue(all(isinstance(s, str) for s in profile["skills"]))
        self.assertEqual(profile["education"][0], "BSc Computer Science, Kuwait")
        self.assertTrue(profile["employment"][0].startswith("Intern"))
        self.assertEqual(profile["experience_years"], 2.0)
        self.assertNotIn("{", str(profile["skills"]))

    def test_derives_summary_location_expertise_when_missing(self):
        raw = {
            "skills": [{"value": "Programming: Python, Java"}],
            "education": [{"value": "Bachelor in Computer Science Candidate, Gulf University, Kuwait"}],
            "employment": [],
            "languages": [],
        }
        text = (
            "Yasser Al Dossary\n\n"
            "Results-oriented Computer Science undergraduate with strong academic performance "
            "and practical experience in full-stack development.\n\n"
            "Skills\nPython\n"
        )
        profile = cpf.build_canonical_profile_facts(raw_facts=raw, cv_text=text)
        self.assertTrue(profile["professional_summary"])
        self.assertIn("Computer Science", profile["professional_summary"])
        self.assertEqual(profile["location"], "Kuwait")
        self.assertTrue(profile["primary_expertise"])
        self.assertEqual(profile["field_sources"]["professional_summary"]["origin"], "derived")
        self.assertEqual(profile["field_sources"]["skills"]["origin"], "extracted")

    def test_hr_confirmed_beats_extracted(self):
        raw = {"skills": [{"value": "Python"}], "education": [], "employment": [], "languages": []}
        reviews = {
            "skills": {
                "display_state": "hr_confirmed",
                "new_value": ["TypeScript", "Go"],
            }
        }
        profile = cpf.build_canonical_profile_facts(raw_facts=raw, reviews_by_path=reviews)
        self.assertEqual(profile["skills"], ["TypeScript", "Go"])
        self.assertEqual(profile["field_sources"]["skills"]["origin"], "hr_confirmed")


if __name__ == "__main__":
    unittest.main()
