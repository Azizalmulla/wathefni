from __future__ import annotations

import unittest

import candidate_cv_facts as facts


HAMAD_HR_CV = """Hamad Almulla
Professional Summary
Motivated Human Resources professional supporting recruitment and employee relations.
Skills
- Recruitment and Talent Acquisition- Employee Relations- HR Administration- Communication
Experience
HR Assistant- Supported recruitment processes including CV screening- Assisted in onboarding new employees
Education
Bachelor's Degree
Languages
Arabic (Native), English (Fluent)
"""

AZIZ_HR_CV = """Aziz Almulla
Skills
- Recruitment and Talent Screening- Employee Relations- Data Handling
Experience
HR Assistant (Simulated/Academic Projects)- Assisted in screening candidates- Supported onboarding documentation
Education
Bachelor's Degree in Sport and Exercise Psychology
Projects
Recruitment Simulation Project- Practiced candidate evaluation and shortlisting
"""


class CandidateCvFactsTests(unittest.TestCase):
    def test_extracts_hr_skills_and_professional_experience_from_docx_style_text(self):
        result = facts.extract_application_cv_facts(HAMAD_HR_CV)
        skills = [item["value"] for item in result["skills"]]
        self.assertEqual(result["status"], "ready")
        self.assertIn("Recruitment and Talent Acquisition", skills)
        self.assertIn("Employee Relations", skills)
        self.assertEqual(result["employment"][0]["role"], "HR Assistant")
        self.assertEqual(result["employment"][0]["experience_type"], "professional_or_unspecified")
        self.assertIn("Assisted in onboarding", " ".join(result["employment"][0]["responsibilities"]))

    def test_preserves_academic_or_simulated_experience_distinction(self):
        result = facts.extract_application_cv_facts(AZIZ_HR_CV)
        self.assertEqual(result["employment"][0]["experience_type"], "academic_or_simulated")
        self.assertIn("Simulated/Academic", result["employment"][0]["role"])
        self.assertTrue(result["projects"])

    def test_parses_arabic_indic_experience_years(self):
        result = facts.extract_application_cv_facts(
            "المهارات\nالتوظيف\nالخبرة\nأخصائي موارد بشرية ولديه ٥ سنوات خبرة\nالتعليم\nبكالوريوس"
        )
        self.assertEqual(result["experience_years"]["value"], 5.0)
        self.assertEqual(result["experience_years"]["method"], "explicit_text")

    def test_not_found_is_not_claimed_as_absent(self):
        result = facts.extract_application_cv_facts("Education\nBachelor's Degree")
        self.assertIn("skills", result["not_found"])
        self.assertIn("employment", result["not_found"])
        self.assertNotIn("absent", str(result).lower())

    def test_ranking_fields_keep_application_facts_separate(self):
        hr = facts.ranking_fields(facts.extract_application_cv_facts(HAMAD_HR_CV))
        accounting = facts.ranking_fields(
            facts.extract_application_cv_facts("Skills\nBookkeeping\nExperience\nAccounts Assistant")
        )
        self.assertIn("Recruitment and Talent Acquisition", hr["skills"])
        self.assertNotIn("Bookkeeping", hr["skills"])
        self.assertIn("Bookkeeping", accounting["skills"])


if __name__ == "__main__":
    unittest.main()
