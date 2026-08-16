"""Phase 3 Candidate Knowledge history/workflow reader and assembly tests."""

from __future__ import annotations

import unittest

from candidate_knowledge_authority import (
    CandidateKnowledgeAuthority,
    InMemoryCandidateKnowledgeStore,
    build_request_context,
)
from candidate_knowledge_errors import (
    ERROR_CANDIDATE_NOT_FOUND,
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_SOURCE_READER_BLOCKED,
    CandidateKnowledgeError,
)
from candidate_knowledge_phase3_readers import (
    read_applications,
    read_assessments,
    read_identity_state,
    read_interviews,
    read_notes,
    read_ranking_evaluations,
    read_screening_evidence,
)


def _ctx(
    company: str = "WATHEFNI",
    actor: str = "user-1",
    permissions: list[str] | None = None,
    modules: list[str] | None = None,
):
    return build_request_context(
        company_code=company,
        actor_user_id=actor,
        permission_authority="backend_current",
        permission_subject_user_id=actor,
        permission_subject_company=company,
        permissions=permissions or ["prehire.read"],
        modules_enabled=modules or ["pre_hiring", "assessments"],
    )


def _app(**kwargs):
    base = {
        "company_code": "WATHEFNI",
        "app_key": "app-a",
        "phone": "96550001001",
        "status": "review_pending",
        "candidate_name": "Candidate",
        "position_code": "POS-1",
        "position_title": "Analyst",
        "data_source": "whatsapp",
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-01T00:00:00Z",
    }
    base.update(kwargs)
    return base


class ApplicationHistoryTests(unittest.TestCase):
    def test_multiple_applications_ordering_and_pagination(self):
        apps = [
            _app(app_key="app-old", updated_at="2026-06-01T00:00:00Z", status="hired"),
            _app(app_key="app-new", updated_at="2026-07-20T00:00:00Z", status="shortlisted"),
            _app(app_key="app-mid", updated_at="2026-07-10T00:00:00Z", status="import_review"),
        ]
        store = InMemoryCandidateKnowledgeStore(applications=apps)
        section = read_applications(
            store,
            company_code="WATHEFNI",
            applications=apps,
            governance_by_app_key={},
            limit=2,
            offset=0,
        )
        self.assertEqual(section.coverage.state, "available")
        keys = [item["app_key"] for item in section.payload["items"]]
        self.assertEqual(keys, ["app-new", "app-mid"])
        self.assertTrue(section.payload["pagination"]["has_more"])
        self.assertFalse(section.payload["deduplicated_by_name"])

        page2 = read_applications(
            store,
            company_code="WATHEFNI",
            applications=apps,
            governance_by_app_key={},
            limit=2,
            offset=2,
        )
        self.assertEqual([item["app_key"] for item in page2.payload["items"]], ["app-old"])

    def test_held_live_finalized_history(self):
        apps = [
            _app(app_key="app-held", status="needs_role", updated_at="2026-07-03T00:00:00Z"),
            _app(app_key="app-live", status="shortlisted", updated_at="2026-07-02T00:00:00Z"),
            _app(app_key="app-final", status="rejected", updated_at="2026-07-01T00:00:00Z"),
        ]
        store = InMemoryCandidateKnowledgeStore(applications=apps)
        section = read_applications(
            store, company_code="WATHEFNI", applications=apps, governance_by_app_key={}
        )
        by_key = {item["app_key"]: item for item in section.payload["items"]}
        self.assertEqual(by_key["app-held"]["lifecycle_bucket"], "held")
        self.assertFalse(by_key["app-held"]["communication_eligible"])
        self.assertFalse(by_key["app-held"]["job_ranking_eligible"])
        self.assertEqual(by_key["app-live"]["lifecycle_bucket"], "live")
        self.assertTrue(by_key["app-live"]["job_ranking_eligible"])
        self.assertEqual(by_key["app-final"]["lifecycle_bucket"], "finalized")
        self.assertFalse(by_key["app-final"]["lifecycle_mutation_eligible"])


class ScreeningEvidenceTests(unittest.TestCase):
    def test_candidate_reply_vs_cv_prefill(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(app_key="app-wa")],
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-wa",
                    "screening_status": "completed",
                    "screening": {
                        "status": "completed",
                        "answers": {
                            "salary_expectation": "800 KWD",
                            "years_experience": "5",
                            "availability": "immediate",
                        },
                        "answer_sources": {
                            "salary_expectation": "candidate_reply",
                            "years_experience": "cv_prefill",
                            "availability": "candidate_reply",
                        },
                        "answer_evidence": {
                            "salary_expectation": {
                                "captured_at": "2026-07-01T10:00:00Z",
                                "confidence": 0.9,
                            },
                            "years_experience": {
                                "captured_at": "2026-07-01T09:00:00Z",
                                "parser": "cv_extractor",
                            },
                            "availability": {
                                "captured_at": "2026-07-01T10:05:00Z",
                            },
                        },
                        "questions": [
                            {"key": "salary_expectation", "prompt": "Expected salary?"},
                            {"key": "years_experience", "prompt": "Years of experience?"},
                            {"key": "availability", "prompt": "Availability?"},
                        ],
                    },
                }
            ],
        )
        section = read_screening_evidence(store, company_code="WATHEFNI", app_keys=["app-wa"])
        by_key = {item["question_key"]: item for item in section.payload["items"]}
        self.assertEqual(by_key["salary_expectation"]["source"], "candidate_reply")
        self.assertEqual(by_key["years_experience"]["source"], "cv_prefill")
        self.assertNotEqual(by_key["years_experience"]["source"], "candidate_reply")
        self.assertEqual(by_key["availability"]["source"], "candidate_reply")
        self.assertEqual(section.evidence[0].authority_level in {"candidate_reply", "cv_prefill"}, True)

    def test_stale_and_corrected_screening(self):
        store = InMemoryCandidateKnowledgeStore(
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-wa",
                    "screening_status": "in_progress",
                    "screening": {
                        "answers": {"visa_status": "transfer"},
                        "answer_sources": {"visa_status": "candidate_reply"},
                        "answer_evidence": {
                            "visa_status": {
                                "captured_at": "2026-06-01T00:00:00Z",
                                "correction": "corrected",
                                "stale": True,
                            }
                        },
                    },
                }
            ]
        )
        section = read_screening_evidence(store, company_code="WATHEFNI", app_keys=["app-wa"])
        item = section.payload["items"][0]
        self.assertTrue(item["stale"])
        self.assertEqual(item["correction_state"], "corrected")
        self.assertEqual(section.coverage.state, "stale")


class AssessmentReaderTests(unittest.TestCase):
    def test_completed_pending_cancelled_expired(self):
        store = InMemoryCandidateKnowledgeStore(
            assessment_attempts=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-done",
                    "battery_key": "bat-1",
                    "assessment_version_id": "ver-1",
                    "status": "completed",
                    "review_status": "approved",
                    "completed_at": "2026-07-02T00:00:00Z",
                    "created_at": "2026-07-01T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-pending",
                    "battery_key": "bat-1",
                    "status": "pending",
                    "created_at": "2026-07-03T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-cancel",
                    "status": "cancelled",
                    "cancelled_at": "2026-07-04T00:00:00Z",
                    "created_at": "2026-07-04T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-exp",
                    "status": "expired",
                    "expired_at": "2026-07-05T00:00:00Z",
                    "created_at": "2026-07-05T00:00:00Z",
                },
            ],
            assessment_scores=[
                {
                    "attempt_id": "att-done",
                    "company_code": "WATHEFNI",
                    "percent": 82,
                    "band": "High",
                    "section_scores": {"reasoning": 80},
                }
            ],
            assessment_report_summaries=[
                {
                    "attempt_id": "att-done",
                    "company_code": "WATHEFNI",
                    "summary": "Strong fit",
                    "job_match": {"fit_band": "high"},
                }
            ],
        )
        section = read_assessments(
            store,
            company_code="WATHEFNI",
            app_keys=["app-a"],
            modules_enabled=["assessments"],
        )
        by_id = {item["attempt_id"]: item for item in section.payload["items"]}
        self.assertEqual(by_id["att-done"]["completed_score"], 82)
        self.assertEqual(by_id["att-done"]["approved_report_summary"], "Strong fit")
        self.assertTrue(by_id["att-cancel"]["cancelled"])
        self.assertTrue(by_id["att-exp"]["expired"])
        self.assertEqual(by_id["att-pending"]["status"], "pending")
        self.assertNotIn("answers", by_id["att-done"])
        self.assertNotIn("report_json", by_id["att-done"])

    def test_assessment_module_disabled(self):
        store = InMemoryCandidateKnowledgeStore(
            assessment_attempts=[
                {"company_code": "WATHEFNI", "app_key": "app-a", "attempt_id": "att-1", "status": "completed"}
            ]
        )
        section = read_assessments(
            store,
            company_code="WATHEFNI",
            app_keys=["app-a"],
            modules_enabled=["pre_hiring"],
            module_enabled=lambda _c, module: module == "pre_hiring",
        )
        self.assertEqual(section.coverage.state, "module_disabled")
        self.assertEqual(section.payload["items"], [])


class InterviewReaderTests(unittest.TestCase):
    def test_completed_interview_with_human_feedback_and_ai_summary(self):
        store = InMemoryCandidateKnowledgeStore(
            interviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "interview_id": "int-1",
                    "interview_type": "panel",
                    "status": "completed",
                    "scheduled_start": "2026-07-10T09:00:00Z",
                    "notes": "Strong communicator",
                    "ai_summary": {"summary": "AI thinks fit is good"},
                    "consent_accepted_at": "2026-07-09T00:00:00Z",
                    "transcript": "SECRET TRANSCRIPT",
                    "meet_link": "https://meet.secret",
                    "sent_body": "candidate message body",
                    "calendar_payload": {"token": "secret"},
                    "created_at": "2026-07-08T00:00:00Z",
                    "completed_at": "2026-07-10T10:00:00Z",
                }
            ],
            interview_feedback_submissions=[
                {
                    "company_code": "WATHEFNI",
                    "interview_id": "int-1",
                    "submission_id": "fb-1",
                    "free_text_notes": "Hire recommended",
                    "submitted_at": "2026-07-10T11:00:00Z",
                }
            ],
        )
        section = read_interviews(store, company_code="WATHEFNI", app_keys=["app-a"])
        item = section.payload["items"][0]
        self.assertTrue(item["transcript_available"])
        self.assertEqual(item["ai_summary"]["labeled_as"], "ai_generated")
        self.assertTrue(item["consent_state"]["accepted"])
        self.assertEqual(len(item["human_feedback_notes"]), 2)
        self.assertNotIn("meet_link", item)
        self.assertNotIn("transcript", item)
        self.assertNotIn("sent_body", item)
        self.assertNotIn("calendar_payload", item)

    def test_transcript_unavailable(self):
        store = InMemoryCandidateKnowledgeStore(
            interviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "interview_id": "int-2",
                    "status": "scheduled",
                    "transcript_available": False,
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ]
        )
        section = read_interviews(store, company_code="WATHEFNI", app_keys=["app-a"])
        self.assertFalse(section.payload["items"][0]["transcript_available"])


class RankingHistoryTests(unittest.TestCase):
    def test_stored_ranking_tied_to_job_context(self):
        store = InMemoryCandidateKnowledgeStore(
            rank_evaluations=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "evaluation_id": "eval-1",
                    "position_code": "POS-42",
                    "position_title": "Teller",
                    "role_profile_key": "historical-rp",
                    "deterministic_score": 77.5,
                    "score_breakdown": {"skills": 0.8},
                    "evidence_digest": "digest-1",
                    "model": "gpt-test",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ]
        )
        section = read_ranking_evaluations(store, company_code="WATHEFNI", app_keys=["app-a"])
        item = section.payload["items"][0]
        self.assertEqual(item["job_context"]["position_code"], "POS-42")
        self.assertTrue(item["not_general_candidate_quality"])
        self.assertTrue(item["criteria_context"]["historical_only"])
        self.assertFalse(section.payload["creates_new_evaluations"])

    def test_stale_ranking_evaluation(self):
        store = InMemoryCandidateKnowledgeStore(
            ranking_run_items=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "item_id": "item-1",
                    "run_id": "run-1",
                    "position_code": "POS-1",
                    "advisory_score": 60,
                    "component_scores": {"match": 0.6},
                    "is_current": False,
                    "stale_reason": "criteria_changed",
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ]
        )
        section = read_ranking_evaluations(store, company_code="WATHEFNI", app_keys=["app-a"])
        self.assertTrue(section.payload["items"][0]["stale"])
        self.assertEqual(section.coverage.state, "stale")

    def test_no_ranking_side_effects(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app()],
            rank_evaluations=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "evaluation_id": "eval-1",
                    "position_code": "POS-1",
                    "deterministic_score": 50,
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
        )
        before = (store.write_attempts, store.ranking_side_effects, store.external_calls)
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        authority.assemble_phase3(_ctx(), "app:app-a", sections=("ranking_evaluations",), include_phase2=False)
        self.assertEqual((store.write_attempts, store.ranking_side_effects, store.external_calls), before)
        with self.assertRaises(RuntimeError):
            store.create_rank_evaluation()
        self.assertEqual(store.ranking_side_effects, 1)


class NotesAndIdentityTests(unittest.TestCase):
    def test_federated_notes_and_visibility(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(app_key="app-a")],
            application_notes=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "note_id": "n1",
                    "body": "Application note",
                    "created_by_user_id": "hr-1",
                    "created_at": "2026-07-01T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "note_id": "n-del",
                    "body": "Deleted",
                    "deleted_at": "2026-07-02T00:00:00Z",
                    "created_at": "2026-07-01T01:00:00Z",
                },
            ],
            fact_review_events=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "fe1",
                    "note": "Fact confirmed",
                    "actor_user_id": "hr-2",
                    "created_at": "2026-07-03T00:00:00Z",
                }
            ],
            classification_review_events=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "ce1",
                    "reason": "Role confirmed",
                    "created_at": "2026-07-04T00:00:00Z",
                }
            ],
            assessment_attempts=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-1",
                    "status": "completed",
                    "review_notes": "Assessment review note",
                    "reviewed_by": "hr-3",
                    "reviewed_at": "2026-07-05T00:00:00Z",
                }
            ],
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "screening": {"notes": "Screening note", "notes_at": "2026-07-01T12:00:00Z"},
                }
            ],
            identity_reviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "review_id": "ir1",
                    "status": "resolved",
                    "resolution_note": "Identity note secret detail",
                    "possible_app_keys": ["app-a"],
                    "created_at": "2026-07-06T00:00:00Z",
                }
            ],
            interviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "interview_id": "int-1",
                    "status": "completed",
                    "notes": "Interview note",
                    "created_at": "2026-07-07T00:00:00Z",
                }
            ],
        )
        interviews = read_interviews(store, company_code="WATHEFNI", app_keys=["app-a"]).payload["items"]
        without_manage = read_notes(
            store,
            company_code="WATHEFNI",
            app_keys=["app-a"],
            candidate_phone="96550001001",
            permissions=["prehire.read"],
            interviews_payload=interviews,
        )
        workflows = {item["source_workflow"] for item in without_manage.payload["items"]}
        self.assertIn("application", workflows)
        self.assertIn("fact_review", workflows)
        self.assertIn("classification_review", workflows)
        self.assertIn("assessment_review", workflows)
        self.assertIn("screening", workflows)
        self.assertIn("interview", workflows)
        self.assertNotIn("identity_review", workflows)
        self.assertFalse(without_manage.payload["complete_hr_note_history"])
        self.assertNotIn("n-del", {item["note_id"] for item in without_manage.payload["items"]})

        with_manage = read_notes(
            store,
            company_code="WATHEFNI",
            app_keys=["app-a"],
            candidate_phone="96550001001",
            permissions=["prehire.read", "candidate.manage"],
            interviews_payload=interviews,
        )
        self.assertIn("identity_review", {item["source_workflow"] for item in with_manage.payload["items"]})

    def test_open_identity_review_and_conflict(self):
        store = InMemoryCandidateKnowledgeStore(
            identity_reviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "review_id": "ir-open",
                    "status": "open",
                    "possible_app_keys": ["app-a"],
                    "possible_candidate_phones": ["96559999999"],
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ]
        )
        open_section = read_identity_state(
            store,
            company_code="WATHEFNI",
            app_key="app-a",
            candidate_phone="96550001001",
            permissions=["prehire.read"],
        )
        self.assertEqual(open_section.payload["state"], "open_review")
        self.assertFalse(open_section.payload["open_identity_review_resolves"])
        self.assertTrue(open_section.payload["detail_denied"])
        self.assertNotIn("possible_candidate_phones", open_section.payload)

        conflict_store = InMemoryCandidateKnowledgeStore(
            identity_reviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "review_id": "ir-c",
                    "status": "conflict",
                    "review_type": "conflict",
                    "possible_app_keys": ["app-a"],
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ]
        )
        conflict = read_identity_state(
            conflict_store,
            company_code="WATHEFNI",
            app_key="app-a",
            candidate_phone="96550001001",
            permissions=["prehire.read", "candidate.manage"],
        )
        self.assertEqual(conflict.payload["state"], "conflict")
        self.assertEqual(conflict.coverage.state, "conflict")
        self.assertFalse(conflict.payload["detail"]["possible_match_identities_exposed"])


class AssemblyIsolationTests(unittest.TestCase):
    def test_cross_tenant_denial(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company_code="OTHER", app_key="app-x")]
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.assemble_phase3(_ctx(company="WATHEFNI"), "app:app-x")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_NOT_FOUND)

    def test_restricted_and_deletion_suppression(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(app_key="app-r", status="shortlisted")],
            governance={("WATHEFNI", "app-r"): {"restriction_state": "restricted"}},
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-r",
                    "screening": {
                        "answers": {"salary_expectation": "900"},
                        "answer_sources": {"salary_expectation": "candidate_reply"},
                    },
                }
            ],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        record = authority.assemble_phase3(
            _ctx(),
            "app:app-r",
            sections=("screening_evidence", "applications"),
            include_phase2=False,
        )
        coverage = {item.section: item.state for item in record.coverage}
        self.assertEqual(coverage["screening_evidence"], "restricted")
        self.assertEqual(coverage["applications"], "restricted")

        deleted = InMemoryCandidateKnowledgeStore(
            applications=[_app(app_key="app-d")],
            governance={("WATHEFNI", "app-d"): {"deletion_request_state": "completed"}},
        )
        authority2 = CandidateKnowledgeAuthority(deleted, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority2.assemble_phase3(_ctx(), "app:app-d")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_RESTRICTED)

    def test_no_raw_json_passthrough(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[
                _app(
                    app_key="app-a",
                    raw_json={"screening": {"answers": {"x": 1}}, "secret": "nope"},
                )
            ],
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "screening_status": "completed",
                    "screening": {
                        "answers": {"salary_expectation": "700"},
                        "answer_sources": {"salary_expectation": "candidate_reply"},
                    },
                    "raw_json": {"should": "not_leak"},
                }
            ],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        record = authority.assemble_phase3(
            _ctx(),
            "app:app-a",
            sections=("screening_evidence", "applications"),
            include_phase2=False,
        )
        blob = record.to_dict()
        self.assertNotIn("raw_json", str(blob))
        self.assertNotIn("should", str(blob.get("screening_evidence")))

    def test_zero_writes_and_external_calls(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(app_key="app-a")],
            screening_facets=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "screening": {
                        "answers": {"availability": "2 weeks"},
                        "answer_sources": {"availability": "candidate_reply"},
                    },
                }
            ],
            assessment_attempts=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "attempt_id": "att-1",
                    "status": "completed",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
            interviews=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "interview_id": "int-1",
                    "status": "scheduled",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
            rank_evaluations=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "evaluation_id": "e1",
                    "position_code": "POS-1",
                    "deterministic_score": 10,
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        before = (store.write_attempts, store.external_calls, store.ocr_triggers, store.ranking_side_effects)
        record = authority.assemble_phase3(_ctx(), "app:app-a")
        self.assertEqual(
            (store.write_attempts, store.external_calls, store.ocr_triggers, store.ranking_side_effects),
            before,
        )
        self.assertEqual(authority.mutation_count, 0)
        self.assertEqual(record.knowledge_version, "candidate-knowledge-phase3-v1")
        with self.assertRaises(RuntimeError):
            store.mutate()
        with self.assertRaises(RuntimeError):
            store.call_voyage()
        with self.assertRaises(RuntimeError):
            store.trigger_ocr()

    def test_phase4_section_denied(self):
        store = InMemoryCandidateKnowledgeStore(applications=[_app()])
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.assemble_phase3(_ctx(), "app:app-a", sections=("voyage_retrieval",))
        self.assertEqual(raised.exception.code, ERROR_SOURCE_READER_BLOCKED)

    def test_assemble_phase2_still_blocks_phase3_sections(self):
        store = InMemoryCandidateKnowledgeStore(applications=[_app()])
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError):
            authority.assemble_phase2(_ctx(), "app:app-a", sections=("notes",))


if __name__ == "__main__":
    unittest.main()
