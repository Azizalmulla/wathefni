"""Phase 2 Candidate Knowledge reader and assembly tests."""

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
from candidate_knowledge_readers import (
    read_canonical_cv,
    read_effective_classification,
    read_effective_facts,
)


def _ctx(company: str = "WATHEFNI", actor: str = "user-1"):
    return build_request_context(
        company_code=company,
        actor_user_id=actor,
        permission_authority="backend_current",
        permission_subject_user_id=actor,
        permission_subject_company=company,
        permissions=["prehire.read"],
        modules_enabled=["pre_hiring"],
    )


def _app(*, company: str, app_key: str, phone: str, status: str = "review_pending", name: str = "Candidate"):
    return {
        "company_code": company,
        "app_key": app_key,
        "phone": phone,
        "status": status,
        "candidate_name": name,
        "data_source": "production",
    }


class CanonicalCvReaderTests(unittest.TestCase):
    def test_valid_inbound_email_canonical_cv(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-email", phone="96550001001", name="Email Cand")],
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "version_id": "v-current",
                    "document_id": "doc-1",
                    "text_content": "HEADER skills kuwait arabic english TAIL",
                    "status": "ready",
                    "is_current": True,
                    "extraction_method": "mistral-ocr",
                    "extracted_text_hash": "hash-text",
                    "source_content_sha256": "hash-src",
                    "provenance": {"channel": "email"},
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
            documents=[
                {
                    "document_id": "doc-1",
                    "app_key": "app-email",
                    "company_code": "WATHEFNI",
                    "source": "email",
                }
            ],
        )
        section = read_canonical_cv(store, company_code="WATHEFNI", app_key="app-email")
        self.assertEqual(section.coverage.state, "available")
        self.assertEqual(section.payload["version_id"], "v-current")
        self.assertIn("HEADER", section.payload["text"])
        self.assertEqual(section.payload["channel"], "email")
        self.assertEqual(section.evidence[0].authority_level, "canonical")

    def test_multiple_versions_one_current(self):
        store = InMemoryCandidateKnowledgeStore(
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v-old",
                    "text_content": "old",
                    "status": "superseded",
                    "is_current": False,
                    "created_at": "2026-06-01T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v-new",
                    "text_content": "new current text",
                    "status": "ready",
                    "is_current": True,
                    "created_at": "2026-07-01T00:00:00Z",
                },
            ]
        )
        section = read_canonical_cv(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.payload["version_id"], "v-new")
        self.assertEqual(section.payload["text"], "new current text")

    def test_superseded_and_invalidated_excluded(self):
        store = InMemoryCandidateKnowledgeStore(
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v-super",
                    "text_content": "gone",
                    "status": "superseded",
                    "is_current": False,
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v-inv",
                    "text_content": "bad",
                    "status": "invalidated",
                    "is_current": True,
                },
            ]
        )
        section = read_canonical_cv(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.coverage.state, "invalidated")

    def test_conflicting_current_versions_fail_closed(self):
        store = InMemoryCandidateKnowledgeStore(
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v1",
                    "text_content": "one",
                    "status": "ready",
                    "is_current": True,
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "version_id": "v2",
                    "text_content": "two",
                    "status": "ready",
                    "is_current": True,
                },
            ]
        )
        section = read_canonical_cv(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.coverage.state, "conflict")
        self.assertNotIn("text", section.payload)

    def test_no_canonical_version_available(self):
        store = InMemoryCandidateKnowledgeStore(cv_text_versions=[])
        section = read_canonical_cv(store, company_code="WATHEFNI", app_key="app-missing")
        self.assertEqual(section.coverage.state, "not_recorded")


class EffectiveFactsReaderTests(unittest.TestCase):
    def test_current_snapshot_and_reviewed_override(self):
        store = InMemoryCandidateKnowledgeStore(
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "facts_id": "f1",
                    "is_current": True,
                    "status": "ready",
                    "contract_version": "application-cv-facts-v1",
                    "extractor_version": "cv-facts-deterministic-v1",
                    "facts_hash": "fh",
                    "facts": {"skills": ["Excel"], "languages": ["Arabic"]},
                    "materialized_at": "2026-07-01T00:00:00Z",
                }
            ],
            fact_review_events=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "e1",
                    "fact_path": "skills",
                    "action": "correct",
                    "new_value": ["Excel", "Recruitment"],
                    "created_at": "2026-07-02T00:00:00Z",
                }
            ],
        )
        section = read_effective_facts(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.coverage.state, "available")
        self.assertEqual(section.payload["effective"]["skills"], ["Excel", "Recruitment"])
        self.assertEqual(section.payload["extraction_snapshot"]["skills"], ["Excel"])
        self.assertEqual(section.payload["reviews_by_path"]["skills"]["display_state"], "hr_confirmed")

    def test_rejected_fact_path(self):
        store = InMemoryCandidateKnowledgeStore(
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "facts_id": "f1",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["Fake"]},
                }
            ],
            fact_review_events=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "e-reject",
                    "fact_path": "skills",
                    "action": "reject",
                    "created_at": "2026-07-02T00:00:00Z",
                }
            ],
        )
        section = read_effective_facts(store, company_code="WATHEFNI", app_key="app-a")
        self.assertIsNone(section.payload["effective"].get("skills"))
        self.assertEqual(section.payload["reviews_by_path"]["skills"]["display_state"], "rejected")

    def test_stale_invalidated_and_missing_unknown(self):
        stale = read_effective_facts(
            InMemoryCandidateKnowledgeStore(
                fact_snapshots=[
                    {
                        "company_code": "WATHEFNI",
                        "app_key": "app-a",
                        "facts_id": "f-old",
                        "is_current": False,
                        "status": "ready",
                        "facts": {"skills": ["x"]},
                    }
                ]
            ),
            company_code="WATHEFNI",
            app_key="app-a",
        )
        self.assertEqual(stale.coverage.state, "stale")

        invalidated = read_effective_facts(
            InMemoryCandidateKnowledgeStore(
                fact_snapshots=[
                    {
                        "company_code": "WATHEFNI",
                        "app_key": "app-a",
                        "facts_id": "f-bad",
                        "is_current": True,
                        "status": "invalidated",
                        "facts": {"skills": ["x"]},
                    }
                ]
            ),
            company_code="WATHEFNI",
            app_key="app-a",
        )
        self.assertEqual(invalidated.coverage.state, "invalidated")

        missing = read_effective_facts(
            InMemoryCandidateKnowledgeStore(),
            company_code="WATHEFNI",
            app_key="app-a",
        )
        self.assertEqual(missing.coverage.state, "not_recorded")
        self.assertIn("never a negative fact", missing.payload["missing_policy"])


class ClassificationReaderTests(unittest.TestCase):
    def test_ai_hr_rejected_and_invalidated_run(self):
        store = InMemoryCandidateKnowledgeStore(
            classification_runs=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-old",
                    "taxonomy_version": "tax-1",
                    "classifier_version": "clf-1",
                    "status": "classified",
                    "created_at": "2026-06-01T00:00:00Z",
                    "input_bundle_hash": "h0",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-new",
                    "taxonomy_version": "tax-1",
                    "classifier_version": "clf-1",
                    "status": "classified",
                    "created_at": "2026-07-01T00:00:00Z",
                    "input_bundle_hash": "h1",
                },
            ],
            classification_invalidations=[
                {"company_code": "WATHEFNI", "run_id": "run-old", "reason_code": "source_changed"}
            ],
            classification_suggestions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-new",
                    "suggestion_id": "s-role",
                    "node_id": "role.hr_assistant",
                    "node_type": "role",
                    "confidence_band": "High",
                    "state": "active",
                    "label_en": "HR Assistant",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-new",
                    "suggestion_id": "s-skill",
                    "node_id": "skill.excel",
                    "node_type": "skill",
                    "confidence_band": "High",
                    "state": "active",
                    "label_en": "Excel",
                },
            ],
            classification_review_events=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "ev-confirm",
                    "action": "confirm",
                    "node_id": "role.hr_assistant",
                    "node_type": "role",
                    "label_en": "HR Assistant",
                    "created_at": "2026-07-02T00:00:00Z",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "event_id": "ev-reject",
                    "action": "reject",
                    "node_id": "skill.excel",
                    "node_type": "skill",
                    "created_at": "2026-07-03T00:00:00Z",
                },
            ],
            taxonomy_releases=[{"taxonomy_version": "tax-1", "label_en": "GCC v1", "immutable": True}],
            taxonomy_nodes=[
                {
                    "taxonomy_version": "tax-1",
                    "node_id": "role.hr_assistant",
                    "node_type": "role",
                    "label_en": "HR Assistant",
                }
            ],
        )
        section = read_effective_classification(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.payload["run_id"], "run-new")
        self.assertEqual(section.payload["taxonomy_version"], "tax-1")
        self.assertEqual(len(section.payload["hr_confirmed"]), 1)
        self.assertEqual(section.payload["hr_confirmed"][0]["authority"], "hr_confirmed")
        self.assertEqual(section.payload["ai_suggested"], [])
        self.assertEqual(section.payload["rejected"][0]["node_id"], "skill.excel")
        self.assertIn("run-old", section.payload["invalidated_run_ids"])

    def test_active_ai_classification_only(self):
        store = InMemoryCandidateKnowledgeStore(
            classification_runs=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-1",
                    "taxonomy_version": "tax-1",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
            classification_suggestions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-a",
                    "run_id": "run-1",
                    "suggestion_id": "s1",
                    "node_id": "role.ops",
                    "node_type": "role",
                    "confidence_band": "High",
                    "state": "active",
                    "label_en": "Operations",
                }
            ],
        )
        section = read_effective_classification(store, company_code="WATHEFNI", app_key="app-a")
        self.assertEqual(section.payload["ai_suggested"][0]["authority"], "ai_suggested")
        self.assertEqual(section.payload["hr_confirmed"], [])


class CrossChannelAndAuthorityTests(unittest.TestCase):
    def test_whatsapp_partial_and_manual_incomplete(self):
        whatsapp_store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-wa", phone="96550002002", name="WA Cand")],
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-wa",
                    "facts_id": "f-wa",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["WhatsApp screening"]},
                }
            ],
            # no cv text versions, no classification
        )
        authority = CandidateKnowledgeAuthority(whatsapp_store, module_enabled=lambda *_: True)
        record = authority.assemble_phase2(_ctx(), "app:app-wa")
        by_section = {item.section: item.state for item in record.coverage if item.section in {"canonical_cv", "effective_facts", "classifications"}}
        self.assertEqual(by_section["canonical_cv"], "not_recorded")
        self.assertEqual(by_section["effective_facts"], "available")
        self.assertEqual(by_section["classifications"], "not_recorded")

        manual_store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-manual", phone="imp-1", name="Manual", status="import_review")],
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-manual",
                    "version_id": "v-m",
                    "text_content": "",
                    "status": "pending",
                    "is_current": True,
                    "provenance": {"channel": "manual_upload"},
                }
            ],
        )
        authority2 = CandidateKnowledgeAuthority(manual_store, module_enabled=lambda *_: True)
        manual = authority2.assemble_phase2(_ctx(), "app:app-manual")
        cv_cov = next(item for item in manual.coverage if item.section == "canonical_cv")
        self.assertEqual(cv_cov.state, "source_pipeline_incomplete")

    def test_cross_tenant_denial_on_assemble(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="OTHERCO", app_key="app-x", phone="96550003003")],
            cv_text_versions=[
                {
                    "company_code": "OTHERCO",
                    "app_key": "app-x",
                    "version_id": "v1",
                    "text_content": "secret",
                    "status": "ready",
                    "is_current": True,
                }
            ],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.assemble_phase2(_ctx(company="WATHEFNI"), "app:app-x")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_NOT_FOUND)
        self.assertNotIn("secret", str(raised.exception.to_dict()))

    def test_restricted_and_deletion_suppression(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-r", phone="96550004004", status="shortlisted")],
            governance={("WATHEFNI", "app-r"): {"restriction_state": "restricted"}},
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-r",
                    "version_id": "v1",
                    "text_content": "restricted body",
                    "status": "ready",
                    "is_current": True,
                }
            ],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        record = authority.assemble_phase2(_ctx(), "app:app-r")
        self.assertTrue(record.canonical_cv.get("suppressed"))
        self.assertIsNone(record.canonical_cv.get("text"))
        cv_cov = next(item for item in record.coverage if item.section == "canonical_cv")
        self.assertEqual(cv_cov.state, "restricted")

        deleted_store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-d", phone="96550004005", status="shortlisted")],
            governance={("WATHEFNI", "app-d"): {"deletion_request_state": "completed"}},
        )
        authority2 = CandidateKnowledgeAuthority(deleted_store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority2.assemble_phase2(_ctx(), "app:app-d")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_RESTRICTED)

    def test_no_profile_raw_json_semantic_fallback_and_no_side_effects(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[
                {
                    **_app(company="WATHEFNI", app_key="app-legacy", phone="96550005005"),
                    "raw_json": {"cv": {"text": "should-not-use"}},
                    "candidate_profile": {"skills": ["mirror"]},
                }
            ]
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        record = authority.assemble_phase2(_ctx(), "app:app-legacy")
        self.assertEqual(record.canonical_cv, {})
        self.assertNotIn("should-not-use", str(record.to_dict()))
        self.assertNotIn("mirror", str(record.effective_facts))
        with self.assertRaises(CandidateKnowledgeError):
            authority.assert_source_reader_blocked("candidates.profile")
        with self.assertRaises(CandidateKnowledgeError):
            authority.assert_source_reader_blocked("applications.raw_json")
        with self.assertRaises(CandidateKnowledgeError):
            authority.assert_source_reader_blocked("semantic_documents")
        self.assertEqual(store.write_attempts, 0)
        self.assertEqual(store.external_calls, 0)
        self.assertEqual(store.ocr_triggers, 0)
        self.assertEqual(authority.mutation_count, 0)
        with self.assertRaises(RuntimeError):
            store.trigger_ocr()
        with self.assertRaises(RuntimeError):
            store.call_voyage()
        with self.assertRaises(RuntimeError):
            store.mutate()
        self.assertEqual(store.ocr_triggers, 1)
        self.assertEqual(store.external_calls, 1)
        self.assertEqual(store.write_attempts, 1)

    def test_phase3_section_cannot_be_assembled(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-a", phone="96550006006")]
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.assemble_phase2(_ctx(), "app:app-a", sections=("notes",))
        self.assertEqual(raised.exception.code, ERROR_SOURCE_READER_BLOCKED)

    def test_inbound_email_full_assembly(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-email", phone="96550007007", name="Email Full")],
            cv_text_versions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "version_id": "v1",
                    "text_content": "Email CV body",
                    "status": "ready",
                    "is_current": True,
                    "provenance": {"channel": "email"},
                    "extracted_text_hash": "t1",
                }
            ],
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "facts_id": "f1",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["Recruitment"], "languages": ["English"]},
                    "contract_version": "application-cv-facts-v1",
                    "extractor_version": "cv-facts-deterministic-v1",
                }
            ],
            classification_runs=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "run_id": "run-1",
                    "taxonomy_version": "tax-1",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
            classification_suggestions=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "run_id": "run-1",
                    "suggestion_id": "s1",
                    "node_id": "role.hr",
                    "node_type": "role",
                    "confidence_band": "High",
                    "state": "active",
                    "label_en": "HR",
                }
            ],
            taxonomy_releases=[{"taxonomy_version": "tax-1", "label_en": "v1", "immutable": True}],
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        record = authority.assemble_phase2(_ctx(), "app:app-email")
        self.assertEqual(record.knowledge_version, "candidate-knowledge-phase2-v1")
        self.assertEqual(record.canonical_cv["text"], "Email CV body")
        self.assertEqual(record.effective_facts["effective"]["skills"], ["Recruitment"])
        self.assertEqual(record.classifications["ai_suggested"][0]["node_id"], "role.hr")
        self.assertTrue(record.evidence_manifest)
        self.assertEqual(set(authority.readers_executed), {"canonical_cv", "effective_facts", "classifications"})


if __name__ == "__main__":
    unittest.main()
