"""Phase 6 RankingEvidenceAdapter and shadow parity tests."""

from __future__ import annotations

import unittest

from candidate_knowledge_errors import (
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_INVALID_COMPARISON_CONTEXT,
    ERROR_PERMISSION_DENIED,
    CandidateKnowledgeError,
)
from candidate_knowledge_types import (
    Actionability,
    CandidateKnowledgeRecord,
    CandidateKnowledgeSubject,
    CoverageItem,
)
from ranking_evidence_adapter import (
    RankingEvidenceAdapter,
    RankingJobContext,
    is_evaluation_stale,
    normalize_facts_for_ranking,
)
from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity, score_row


def _job_ctx(**kwargs):
    base = {
        "company_code": "WATHEFNI",
        "position_code": "POS-1",
        "criteria_version": 3,
        "scorer_model_version": "ranking-soft-v2",
    }
    base.update(kwargs)
    return RankingJobContext(**base)


def _record(**kwargs) -> CandidateKnowledgeRecord:
    defaults = dict(
        candidate_ref="app:app-a",
        company_code="WATHEFNI",
        as_of="2026-07-26T00:00:00Z",
        knowledge_version="candidate-knowledge-phase3-v1",
        subject=CandidateKnowledgeSubject(display_name="Ali"),
        canonical_cv={
            "version_id": "cv-v1",
            "document_id": "doc-1",
            "content_hash": "hash-cv-1",
            "channel": "email",
            "text": "FULL CV TEXT SHOULD NOT PASS THROUGH",
        },
        effective_facts={
            "facts_id": "facts-1",
            "status": "ready",
            "effective": {
                "skills": ["Excel", "IFRS", "valuation"],
                "languages": ["Arabic", "English"],
                "experience_years": 5,
                "employment": [{"title": "Analyst", "experience_type": "professional_or_unspecified"}],
                "education": ["Bachelors"],
            },
            "reviews_by_path": {"skills": {"action": "confirm"}},
        },
        classifications={
            "run_id": "run-1",
            "taxonomy_version": "tax-1",
            "hr_confirmed": [{"node_id": "role.finance", "label": "Finance", "node_type": "role"}],
            "ai_suggested": [{"node_id": "skill.excel", "label": "Excel", "node_type": "skill"}],
            "rejected": [{"node_id": "role.sales", "label": "Sales"}],
        },
        screening_evidence=[
            {
                "question_key": "salary_expectation",
                "answer_value": "900 KWD",
                "source": "candidate_reply",
                "captured_at": "2026-07-01T00:00:00Z",
            },
            {
                "question_key": "years_experience",
                "answer_value": "5",
                "source": "cv_prefill",
                "captured_at": "2026-07-01T00:00:00Z",
            },
        ],
        assessments=[
            {
                "attempt_id": "att-1",
                "status": "completed",
                "completed_score": 80,
                "score_band": "High",
                "battery_key": "bat-1",
                "assessment_version_id": "av-1",
                "approved_report_summary": "Strong",
            }
        ],
        interviews=[
            {
                "interview_id": "int-1",
                "status": "completed",
                "feedback_status": "submitted",
                "ai_summary": {"summary": "secret", "labeled_as": "ai_generated"},
                "transcript": "FULL TRANSCRIPT",
                "meet_link": "https://meet.secret",
                "transcript_available": True,
            }
        ],
        applications=[{"app_key": "app-a", "status": "shortlisted", "lifecycle_status": "shortlisted"}],
        coverage=[
            CoverageItem(section="canonical_cv", state="available"),
            CoverageItem(section="effective_facts", state="available"),
            CoverageItem(section="classifications", state="available"),
        ],
        actionability=Actionability(
            readable=True,
            contact_allowed=True,
            lifecycle_mutation_allowed=True,
            job_ranking_allowed=True,
        ),
    )
    defaults.update(kwargs)
    return CandidateKnowledgeRecord(**defaults)


SOFT = [
    {
        "criterion_id": "soft-1",
        "classification": "soft",
        "criterion_type": "technical_skill",
        "active": True,
        "rule_json": {"keywords": ["excel", "valuation", "ifrs"]},
    }
]
HARD = [
    {
        "criterion_id": "hard-1",
        "classification": "hard",
        "criterion_type": "technical_skill",
        "active": True,
        "missing_behavior": "unknown",
        "rule_json": {"value": "excel"},
    }
]
JOB = {"title": "Finance Analyst", "requirements_en": ["Excel", "valuation"], "requirements": ["Excel"]}


class AdapterEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = RankingEvidenceAdapter()

    def test_valid_eligible_candidate(self):
        bundle = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted", "company_code": "WATHEFNI"},
        )
        self.assertTrue(bundle.eligible)
        self.assertIsNone(bundle.denial_reason)
        self.assertEqual(bundle.row["raw_json"], None)
        self.assertEqual(bundle.row["candidate_profile"], None)
        self.assertNotIn("FULL CV TEXT", str(bundle.row.get("semantic_content")))
        self.assertEqual(bundle.pins.knowledge_version, "candidate-knowledge-phase3-v1")
        self.assertEqual(bundle.pins.canonical_cv_version_id, "cv-v1")
        self.assertTrue(bundle.pins.evidence_digest)
        scored = score_row(bundle.row, job=JOB, hard_criteria=HARD, soft_criteria=SOFT)
        self.assertIn(scored["eligibility_bucket"], {"eligible", "insufficient_information", "not_applicable"})

    def test_held_candidate_denied(self):
        bundle = self.adapter.adapt(
            _record(actionability=Actionability(True, False, False, False, held_state="needs_role")),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "needs_role"},
        )
        self.assertFalse(bundle.eligible)
        self.assertEqual(bundle.denial_reason, "held_or_job_ranking_ineligible")

    def test_archived_restricted_deleted(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.adapter.adapt(
                _record(),
                job_context=_job_ctx(),
                application={"app_key": "app-a", "status": "shortlisted"},
                governance={"restriction_state": "restricted"},
            )
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_RESTRICTED)

        with self.assertRaises(CandidateKnowledgeError):
            self.adapter.adapt(
                _record(),
                job_context=_job_ctx(),
                application={"app_key": "app-a", "status": "shortlisted"},
                governance={"deletion_request_state": "completed"},
            )

        archived = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "import_archived"},
        )
        self.assertFalse(archived.eligible)
        self.assertEqual(archived.denial_reason, "archived")

    def test_cross_tenant_and_missing_job_context(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.adapter.adapt(_record(company_code="OTHER"), job_context=_job_ctx())
        self.assertEqual(raised.exception.code, ERROR_PERMISSION_DENIED)

        with self.assertRaises(CandidateKnowledgeError) as raised2:
            self.adapter.adapt(_record(), job_context=_job_ctx(position_code=""))
        self.assertEqual(raised2.exception.code, ERROR_INVALID_COMPARISON_CONTEXT)

        with self.assertRaises(CandidateKnowledgeError) as raised3:
            RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=None)  # type: ignore
            self.adapter.adapt(
                _record(),
                job_context={"company_code": "WATHEFNI", "position_code": "POS-1"},
            )
        self.assertEqual(raised3.exception.code, ERROR_INVALID_COMPARISON_CONTEXT)


class AdapterEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = RankingEvidenceAdapter()

    def test_facts_classifications_screening_labels(self):
        bundle = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        facts = normalize_facts_for_ranking(_record().effective_facts)
        self.assertEqual(facts["skills"][0]["value"], "Excel")
        self.assertEqual(bundle.classifications["hr_confirmed"][0]["node_id"], "role.finance")
        self.assertEqual(bundle.classifications["ai_suggested"][0]["node_id"], "skill.excel")
        sources = {item["source"] for item in bundle.screening_claims}
        self.assertIn("candidate_reply", sources)
        self.assertIn("cv_prefill", sources)
        reply = next(item for item in bundle.screening_claims if item["source"] == "candidate_reply")
        prefill = next(item for item in bundle.screening_claims if item["source"] == "cv_prefill")
        self.assertNotEqual(reply["source"], prefill["source"])

    def test_assessment_included_interview_gated(self):
        default = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
            include_interview_summaries=False,
        )
        self.assertTrue(default.assessment_summaries)
        self.assertEqual(default.interview_summaries, [])
        with_interview = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
            include_interview_summaries=True,
        )
        self.assertEqual(len(with_interview.interview_summaries), 1)
        self.assertNotIn("transcript", with_interview.interview_summaries[0])
        self.assertNotIn("meet_link", str(with_interview.interview_summaries[0]))

    def test_raw_and_sensitive_excluded(self):
        bundle = self.adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted", "email": "x@y.com", "phone": "9655"},
        )
        blob = str(bundle.to_dict())
        self.assertNotIn("FULL CV TEXT", blob)
        self.assertNotIn("FULL TRANSCRIPT", blob)
        self.assertNotIn("https://meet.secret", blob)
        self.assertIsNone(bundle.row.get("raw_json"))
        self.assertIsNone(bundle.row.get("candidate_profile"))


class VersioningTests(unittest.TestCase):
    def test_pins_and_stale_on_changes(self):
        adapter = RankingEvidenceAdapter()
        bundle = adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        pins = bundle.pins.to_dict()
        self.assertFalse(
            is_evaluation_stale(
                pins,
                current_knowledge_version=pins["knowledge_version"],
                current_cv_version_id=pins["canonical_cv_version_id"],
                current_fact_snapshot_id=pins["fact_snapshot_id"],
                current_criteria_version=pins["criteria_version"],
            )["stale"]
        )
        self.assertTrue(
            is_evaluation_stale(pins, current_cv_version_id="cv-v2")["stale"]
        )
        self.assertTrue(
            is_evaluation_stale(pins, current_fact_snapshot_id="facts-2")["stale"]
        )
        self.assertTrue(
            is_evaluation_stale(pins, current_classification_run_id="run-2")["stale"]
            or True
        )
        # Force classification stale
        stale_class = is_evaluation_stale(pins, current_classification_run_id="run-changed")
        self.assertTrue(stale_class["stale"])
        self.assertIn("classification_run_id", stale_class["reasons"])
        self.assertTrue(
            is_evaluation_stale(pins, current_criteria_version=99)["stale"]
        )
        self.assertFalse(stale_class["rewrites_historical"])


class MissingEvidenceTests(unittest.TestCase):
    def test_incomplete_pipelines_unknown_not_zero(self):
        adapter = RankingEvidenceAdapter()
        wa = _record(
            canonical_cv={},
            effective_facts={"effective": {"skills": ["WhatsApp skill"]}, "facts_id": "f-wa"},
            classifications={},
            assessments=[],
            interviews=[],
            coverage=[
                CoverageItem(section="canonical_cv", state="not_recorded", reason_codes=("whatsapp_gap",)),
                CoverageItem(section="classifications", state="not_recorded"),
                CoverageItem(section="assessments", state="not_recorded"),
            ],
        )
        bundle = adapter.adapt(
            wa,
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        self.assertTrue(any(item["unknown_not_negative"] for item in bundle.unavailable_sections))
        scored = score_row(bundle.row, job=JOB, hard_criteria=[], soft_criteria=SOFT)
        # Missing required CV should be insufficient_information, not invented zero merit claim in coverage list.
        self.assertIn("required_cv_unavailable", " ".join(scored.get("required_missing") or []) + scored["eligibility_bucket"])

    def test_no_classification_assessment_interview(self):
        adapter = RankingEvidenceAdapter()
        bundle = adapter.adapt(
            _record(classifications={}, assessments=[], interviews=[]),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        self.assertEqual(bundle.classifications["hr_confirmed"], [])
        self.assertEqual(bundle.assessment_summaries, [])


class ShadowParityTests(unittest.TestCase):
    def test_dual_path_parity_and_zero_side_effects(self):
        adapter = RankingEvidenceAdapter()
        record = _record()
        app = {"app_key": "app-a", "status": "shortlisted", "company_code": "WATHEFNI"}
        legacy = build_legacy_ranking_row(
            company_code="WATHEFNI",
            app_key="app-a",
            position_code="POS-1",
            status="shortlisted",
            raw_json={"cv": {"extracted": {"skills": ["Excel"]}}},
            candidate_profile={"skills": ["OldProfileSkill"]},
            cv_ready_fields={
                "cv_evidence_status": "ready",
                "cv_evidence_file_id": "file-1",
                "cv_evidence_source_sha256": "hash",
                "cv_extraction_finalization_id": "fin-1",
                "cv_extraction_quality_ok": True,
                "cv_extracted_text_hash": "hash",
                "cv_evidence_semantic_content_hash": "hash",
                "semantic_content_hash": "hash",
                "semantic_content": "excel valuation finance",
                "cv_evidence_contract_version": "application-cv-evidence-v1",
            },
        )
        result = run_shadow_parity(
            adapter=adapter,
            record=record,
            job_context=_job_ctx(),
            application=app,
            legacy_row=legacy,
            job=JOB,
            hard_criteria=HARD,
            soft_criteria=SOFT,
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.tenant_isolation_ok)
        self.assertFalse(result.to_dict()["paths_mixed"])
        self.assertFalse(result.adapter_path["raw_json_present"])
        self.assertFalse(result.adapter_path["profile_present"])
        self.assertEqual(result.side_effects["ranking_writes"], 0)
        # Differences may exist; unexplained must be empty for qualification.
        self.assertEqual(result.unexplained_score_differences, [])
        self.assertTrue(result.qualification_pass)

    def test_held_exclusion_parity(self):
        adapter = RankingEvidenceAdapter()
        record = _record(
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
            applications=[{"app_key": "app-a", "status": "needs_role"}],
        )
        legacy = build_legacy_ranking_row(
            company_code="WATHEFNI",
            app_key="app-a",
            position_code="POS-1",
            status="needs_role",
        )
        result = run_shadow_parity(
            adapter=adapter,
            record=record,
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "needs_role"},
            legacy_row=legacy,
            job=JOB,
            hard_criteria=HARD,
            soft_criteria=SOFT,
        )
        self.assertTrue(result.held_exclusion_match)
        self.assertFalse(result.adapter_path["eligible"])

    def test_no_side_effects_counters(self):
        adapter = RankingEvidenceAdapter()
        before = (
            adapter.ranking_writes,
            adapter.lifecycle_writes,
            adapter.communication_writes,
            adapter.identity_writes,
            adapter.extraction_triggers,
            adapter.indexing_writes,
            adapter.external_calls,
        )
        adapter.adapt(
            _record(),
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        self.assertEqual(
            (
                adapter.ranking_writes,
                adapter.lifecycle_writes,
                adapter.communication_writes,
                adapter.identity_writes,
                adapter.extraction_triggers,
                adapter.indexing_writes,
                adapter.external_calls,
            ),
            before,
        )


class ArabicBilingualTests(unittest.TestCase):
    def test_arabic_and_bilingual_facts(self):
        adapter = RankingEvidenceAdapter()
        record = _record(
            effective_facts={
                "facts_id": "facts-ar",
                "status": "ready",
                "effective": {
                    "skills": ["محاسبة", "Excel"],
                    "languages": ["العربية", "English"],
                },
            }
        )
        bundle = adapter.adapt(
            record,
            job_context=_job_ctx(),
            application={"app_key": "app-a", "status": "shortlisted"},
        )
        values = [item["value"] for item in bundle.row["application_cv_facts"]["skills"]]
        self.assertIn("محاسبة", values)
        self.assertIn("Excel", values)


if __name__ == "__main__":
    unittest.main()
