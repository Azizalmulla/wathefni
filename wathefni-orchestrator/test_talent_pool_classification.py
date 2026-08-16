"""Unit tests for Talent Pool Classification authority (no DB required)."""

from __future__ import annotations

import json
import os
import unittest

import talent_pool_classification as tpc


SOFTWARE_CV = """
Senior Software Engineer with 6 years experience.
Python, SQL, FastAPI, AWS certified. Computer Science degree.
Built backend services for a banking technology team in Kuwait.
"""

HR_CV = """
HR Generalist and recruiter with talent acquisition experience.
Managed hiring pipelines and employee relations for a retail group.
Fluent Arabic and English.
"""

FINANCE_CV = """
Accountant with strong Excel and financial reporting skills.
Bachelor in Accounting. Experience in audit and treasury support.
"""

ENGINEERING_CV = """
Mechanical Engineer experienced with AutoCAD and SolidWorks.
Oil & Gas projects. B.Eng Mechanical.
"""

SALES_CV = """
Sales Executive and digital marketing specialist.
Business development and social media campaigns for retail brands.
"""

LOW_INFO_CV = "Name: Sam Example\nPhone: 000\n"

COMMON_SOFTWARE_TOOLS_CV = """
Office Administrator coordinating calendars and preparing Word documents,
Excel trackers, email updates, and other common business software.
"""

FINANCE_ERP_CV = """
Senior Accountant managing financial reporting, treasury, and audit using
SAP ERP software and Excel.
"""

HR_SYSTEMS_CV = """
HR Generalist managing recruitment, employee relations, payroll coordination,
and HR information systems.
"""

MULTIDISCIPLINARY_CV = """
Operations Manager who led warehouse teams and built Python automation with
SQL dashboards for logistics planning.
"""

CAREER_CHANGE_CV = """
Former Mechanical Engineer. Completed a software developer bootcamp, built
Python and FastAPI projects, and completed a backend internship.
"""

LONG_UNCLEAR_CV = """
Professional with experience in many areas and various responsibilities across
teams over time. Supported initiatives, communicated with stakeholders, used
standard tools, and contributed to different projects without specific role
titles, domain outcomes, education, or sustained specialist skills.
"""


class TalentPoolClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = tpc.load_taxonomy_pack()
        self.env = {
            tpc.FEATURE_MASTER: "off",
            tpc.FEATURE_TENANTS: "LOCALTPC",
            tpc.FEATURE_SCHEMA: "on",
            tpc.FEATURE_MANUAL: "on",
            tpc.FEATURE_WORKERS: "off",
            tpc.FEATURE_UI: "on",
        }

    def test_taxonomy_pack_is_versioned_and_bilingual(self) -> None:
        self.assertTrue(self.pack["taxonomy_version"].startswith("taxonomy_v"))
        nodes = self.pack["nodes"]
        self.assertGreater(len(nodes), 20)
        types = {n["node_type"] for n in nodes}
        for required in (
            "career_function",
            "likely_role",
            "skill",
            "industry",
            "seniority",
            "experience_band",
            "education_field",
            "certification",
            "language",
        ):
            self.assertIn(required, types)
        for node in nodes:
            self.assertTrue(node["label_en"])
            self.assertTrue(node["label_ar"])
            self.assertTrue(node["node_id"])

    def test_feature_flags_decoupled_and_workers_off(self) -> None:
        status = tpc.feature_status("LOCALTPC", self.env)
        self.assertFalse(status["master_enabled"])
        self.assertTrue(status["enabled_for_company"])
        self.assertFalse(status["workers_enabled"])
        self.assertFalse(status["coupled_to_unified_candidates"])
        self.assertFalse(tpc.feature_enabled_for_company("OTHER", self.env))
        with self.assertRaises(RuntimeError):
            tpc.assert_workers_disabled_for_local({tpc.FEATURE_WORKERS: "on"})

    def test_software_multilabel_with_evidence(self) -> None:
        bundle = tpc.build_input_bundle(
            cv_text=SOFTWARE_CV,
            facts={"skills": []},  # weak structured facts
            hr_confirmed_facts={},
            document_version_id="doc-1",
            extraction_version_id="ext-1",
        )
        result = tpc.classify_bundle(bundle, pack=self.pack)
        self.assertEqual(result["status"], "classified")
        self.assertFalse(result["ocr_triggered"])
        ids = {s["node_id"] for s in result["suggestions"]}
        self.assertIn("fn.technology", ids)
        self.assertIn("role.software_engineer", ids)
        self.assertIn("skill.python", ids)
        for suggestion in result["suggestions"]:
            self.assertTrue(suggestion["evidence"])
            self.assertIn(suggestion["confidence_band"], {tpc.BAND_HIGH, tpc.BAND_MEDIUM, tpc.BAND_NEEDS_REVIEW})
            self.assertNotEqual(suggestion["confidence_band"], "")

    def test_hr_finance_engineering_sales(self) -> None:
        cases = [
            (HR_CV, "fn.hr", "role.hr_generalist"),
            (FINANCE_CV, "fn.finance", "role.accountant"),
            (ENGINEERING_CV, "fn.engineering", "role.mechanical_engineer"),
            (SALES_CV, "fn.sales_marketing", "role.sales_executive"),
        ]
        for text, fn, role in cases:
            result = tpc.classify_bundle(
                tpc.build_input_bundle(
                    cv_text=text,
                    facts={},
                    hr_confirmed_facts={},
                    document_version_id="d",
                    extraction_version_id="e",
                ),
                pack=self.pack,
            )
            ids = {s["node_id"] for s in result["suggestions"]}
            self.assertIn(fn, ids, msg=text[:40])
            self.assertIn(role, ids, msg=text[:40])

    def test_low_information_unclassified(self) -> None:
        result = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text=LOW_INFO_CV,
                facts={},
                hr_confirmed_facts={},
                document_version_id="d",
                extraction_version_id="e",
            ),
            pack=self.pack,
        )
        self.assertEqual(result["status"], tpc.STATE_UNCLASSIFIED)
        self.assertEqual(result["suggestions"], [])
        self.assertTrue(result["refusal_reason"])

    def test_technology_requires_meaningful_evidence(self) -> None:
        for text, expected_function in (
            (COMMON_SOFTWARE_TOOLS_CV, None),
            (FINANCE_ERP_CV, "fn.finance"),
            (HR_SYSTEMS_CV, "fn.hr"),
        ):
            result = tpc.classify_bundle(
                tpc.build_input_bundle(
                    cv_text=text,
                    facts={},
                    hr_confirmed_facts={},
                    document_version_id="quality",
                    extraction_version_id="quality",
                ),
                pack=self.pack,
            )
            ids = {s["node_id"] for s in result["suggestions"]}
            self.assertNotIn("fn.technology", ids, msg=text)
            if expected_function:
                self.assertIn(expected_function, ids, msg=text)

    def test_multidisciplinary_technology_remains_supported_secondary(self) -> None:
        result = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text=MULTIDISCIPLINARY_CV,
                facts={},
                hr_confirmed_facts={},
                document_version_id="quality",
                extraction_version_id="quality",
            ),
            pack=self.pack,
        )
        by_id = {s["node_id"]: s for s in result["suggestions"]}
        self.assertIn("fn.operations", by_id)
        self.assertIn("fn.technology", by_id)
        self.assertEqual(by_id["fn.technology"]["confidence_band"], tpc.BAND_MEDIUM)
        self.assertTrue(by_id["fn.technology"]["evidence"])

    def test_clear_short_career_change_and_raw_text_stay_useful(self) -> None:
        cases = (
            ("CS graduate. Python projects. Software Engineering intern.", {}),
            (CAREER_CHANGE_CV, {}),
            ("Backend developer using Python and SQL daily; built APIs for banking operations.", {"skills": []}),
        )
        for text, facts in cases:
            result = tpc.classify_bundle(
                tpc.build_input_bundle(
                    cv_text=text,
                    facts=facts,
                    hr_confirmed_facts={},
                    document_version_id="quality",
                    extraction_version_id="quality",
                ),
                pack=self.pack,
            )
            technology = next((s for s in result["suggestions"] if s["node_id"] == "fn.technology"), None)
            self.assertIsNotNone(technology, msg=text)
            self.assertIn(technology["confidence_band"], {tpc.BAND_HIGH, tpc.BAND_MEDIUM})
            self.assertTrue(any(e["evidence_kind"] == "cv_text" for e in technology["evidence"]))

    def test_long_unclear_is_not_forced_into_technology(self) -> None:
        result = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text=LONG_UNCLEAR_CV,
                facts={},
                hr_confirmed_facts={},
                document_version_id="quality",
                extraction_version_id="quality",
            ),
            pack=self.pack,
        )
        self.assertIn(result["status"], {tpc.STATE_UNCLASSIFIED, tpc.STATE_NEEDS_REVIEW})
        self.assertNotIn("fn.technology", {s["node_id"] for s in result["suggestions"]})
        self.assertFalse(any(s["confidence_band"] == tpc.BAND_HIGH for s in result["suggestions"]))

    def test_arabic_and_bilingual(self) -> None:
        arabic = "مهندس برمجيات بخبرة في بايثون وقواعد البيانات إس كيو إل. تقنية المعلومات."
        result = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text=arabic,
                facts={},
                hr_confirmed_facts={},
                document_version_id="d",
                extraction_version_id="e",
            ),
            pack=self.pack,
        )
        ids = {s["node_id"] for s in result["suggestions"]}
        self.assertTrue(ids.intersection({"fn.technology", "role.software_engineer", "skill.python", "skill.sql"}))

    def test_skills_from_text_when_facts_empty(self) -> None:
        result = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text="Backend developer using Python and SQL daily.",
                facts={"skills": []},
                hr_confirmed_facts={},
                document_version_id="d",
                extraction_version_id="e",
            ),
            pack=self.pack,
        )
        skill_ids = {s["node_id"] for s in result["suggestions"] if s["node_type"] == "skill"}
        self.assertTrue({"skill.python", "skill.sql"} & skill_ids)
        for suggestion in result["suggestions"]:
            if suggestion["node_id"] in {"skill.python", "skill.sql"}:
                self.assertTrue(any(e["evidence_kind"] == "cv_text" for e in suggestion["evidence"]))

    def test_hr_confirm_survives_reclassify_projection(self) -> None:
        suggestions = [
            {
                "node_id": "fn.technology",
                "node_type": "career_function",
                "label_en": "Technology",
                "confidence_band": tpc.BAND_HIGH,
                "evidence": [{"quote": "software"}],
                "state": tpc.STATE_ACTIVE,
            },
            {
                "node_id": "role.software_engineer",
                "node_type": "likely_role",
                "label_en": "Software Engineering",
                "confidence_band": tpc.BAND_HIGH,
                "evidence": [{"quote": "engineer"}],
                "state": tpc.STATE_ACTIVE,
            },
        ]
        events = [
            tpc.append_review_event(
                action="confirm",
                node_id="fn.technology",
                actor_user_id="hr1",
                node_type="career_function",
                label_en="Technology",
                label_ar="التكنولوجيا",
            ),
            tpc.append_review_event(
                action="reject",
                node_id="role.software_engineer",
                actor_user_id="hr1",
            ),
        ]
        # Simulate new run suggestions that would try to re-add rejected role
        new_suggestions = [
            {**suggestions[0], "state": tpc.STATE_ACTIVE},
            {**suggestions[1], "state": tpc.STATE_ACTIVE},
            {
                "node_id": "skill.python",
                "node_type": "skill",
                "label_en": "Python",
                "confidence_band": tpc.BAND_HIGH,
                "evidence": [{"quote": "Python"}],
                "state": tpc.STATE_ACTIVE,
            },
        ]
        effective = tpc.effective_classification(suggestions=new_suggestions, review_events=events)
        confirmed_ids = {c["node_id"] for c in effective["confirmed"]}
        ai_ids = {s["node_id"] for s in effective["ai_suggested"]}
        self.assertIn("fn.technology", confirmed_ids)
        self.assertNotIn("role.software_engineer", ai_ids)
        self.assertIn("role.software_engineer", set(effective["rejected_node_ids"]))
        self.assertIn("skill.python", ai_ids)
        chip = effective["chip"]
        self.assertTrue(chip and "Technology" in chip)

    def test_graduated_outcomes_not_judgmental(self) -> None:
        short_clear = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text="CS graduate. Python projects. Software Engineering intern.",
                facts={},
                hr_confirmed_facts={},
                document_version_id="d",
                extraction_version_id="e",
            ),
            pack=self.pack,
        )
        self.assertIn(short_clear["status"], {tpc.STATE_CLASSIFIED, tpc.STATE_CLASSIFIED_MULTI, tpc.STATE_CAUTIOUS})
        self.assertIn(short_clear["outcome_label"], {tpc.OUTCOME_CLEAR, tpc.OUTCOME_MULTI, tpc.OUTCOME_PARTIAL})
        self.assertNotIn("weak", json.dumps(short_clear).lower())
        self.assertNotIn("poor candidate", json.dumps(short_clear).lower())

        unclear = tpc.classify_bundle(
            tpc.build_input_bundle(
                cv_text="Professional with experience in many areas and various responsibilities across teams over time without specific titles.",
                facts={},
                hr_confirmed_facts={},
                document_version_id="d",
                extraction_version_id="e",
            ),
            pack=self.pack,
        )
        self.assertIn(unclear["status"], {tpc.STATE_UNCLASSIFIED, tpc.STATE_NEEDS_REVIEW, tpc.STATE_CAUTIOUS})
        self.assertIn(unclear["outcome_label"], {tpc.OUTCOME_INSUFFICIENT, tpc.OUTCOME_NEEDS_HR, tpc.OUTCOME_PARTIAL})

    def test_medium_requires_opt_in_for_default_filters(self) -> None:
        suggestions = [
            {
                "node_id": "fn.finance",
                "node_type": "career_function",
                "label_en": "Finance",
                "confidence_band": tpc.BAND_MEDIUM,
                "evidence": [{"quote": "accountant"}],
                "state": tpc.STATE_ACTIVE,
            }
        ]
        default_eff = tpc.effective_classification(suggestions=suggestions, review_events=[], include_medium_ai=False)
        opt_in = tpc.effective_classification(suggestions=suggestions, review_events=[], include_medium_ai=True)
        self.assertEqual(default_eff["ai_suggested"], [])
        self.assertEqual(len(opt_in["ai_suggested"]), 1)
        self.assertIsNone(default_eff["chip"])

    def test_idempotency_key_stable(self) -> None:
        bundle = tpc.build_input_bundle(
            cv_text=SOFTWARE_CV,
            facts={},
            hr_confirmed_facts={},
            document_version_id="doc-1",
            extraction_version_id="ext-1",
        )
        h = tpc.input_bundle_hash(bundle)
        k1 = tpc.idempotency_key(
            company_code="A",
            app_key="X",
            document_version_id="doc-1",
            extraction_version_id="ext-1",
            taxonomy_version="taxonomy_v1.0.0",
            classifier_version=tpc.CLASSIFIER_VERSION,
            bundle_hash=h,
        )
        k2 = tpc.idempotency_key(
            company_code="A",
            app_key="X",
            document_version_id="doc-1",
            extraction_version_id="ext-1",
            taxonomy_version="taxonomy_v1.0.0",
            classifier_version=tpc.CLASSIFIER_VERSION,
            bundle_hash=h,
        )
        k3 = tpc.idempotency_key(
            company_code="A",
            app_key="X",
            document_version_id="doc-2",
            extraction_version_id="ext-1",
            taxonomy_version="taxonomy_v1.0.0",
            classifier_version=tpc.CLASSIFIER_VERSION,
            bundle_hash=h,
        )
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)

    def test_search_reasons_do_not_blend_authority(self) -> None:
        effective = {
            "confirmed": [{"node_id": "fn.hr", "label_en": "Human Resources"}],
            "ai_suggested": [{"node_id": "skill.python", "label_en": "Python", "confidence_band": "High"}],
        }
        reasons = tpc.search_match_reasons_for_classification(
            query="human resources",
            effective=effective,
            suggestions=[{"evidence": [{"quote": "python fastapi"}]}],
        )
        self.assertIn(tpc.MATCH_CONFIRMED_CLASSIFICATION, reasons)
        reasons2 = tpc.search_match_reasons_for_classification(
            query="python",
            effective=effective,
            suggestions=[{"evidence": [{"quote": "python fastapi"}]}],
        )
        self.assertIn(tpc.MATCH_AI_SUGGESTED_CLASSIFICATION, reasons2)
        self.assertIn(tpc.MATCH_CLASSIFICATION_EVIDENCE, reasons2)

    def test_no_hiring_score_in_profile_section(self) -> None:
        section = tpc.profile_classification_section(
            run={"status": "classified", "taxonomy_version": "taxonomy_v1.0.0"},
            suggestions=[],
            review_events=[],
            pack=self.pack,
        )
        self.assertIsNone(section["hiring_score"])
        self.assertIsNone(section["role_profile_score"])
        self.assertIsNone(section["job_assignment"])

    def test_tenant_node_namespace_enforced(self) -> None:
        class _Cur:
            def execute(self, *args, **kwargs):
                return None

        with self.assertRaises(ValueError):
            tpc.upsert_tenant_node(
                _Cur(),
                company_code="ACME",
                node_id="role.custom",
                node_type="likely_role",
                label_en="Custom",
                label_ar="مخصص",
            )


if __name__ == "__main__":
    unittest.main()
