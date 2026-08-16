"""Phase 4 Candidate Knowledge indexing and hybrid retrieval tests."""

from __future__ import annotations

import time
import unittest

from candidate_knowledge_chunker import (
    ChunkerConfig,
    approximate_tokens,
    benchmark_chunk_configs,
    chunk_cv_text,
    detect_language,
)
from candidate_knowledge_embeddings import (
    MockEmbeddingProvider,
    QueryEmbeddingCache,
    deterministic_mock_embedding,
)
from candidate_knowledge_errors import (
    ERROR_INDEX_NOT_READY,
    CandidateKnowledgeError,
)
from candidate_knowledge_index_schema import PHASE4_LOCAL_SCHEMA_DDL
from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore
from candidate_knowledge_indexer import CandidateKnowledgeIndexer, redact_pii_for_index
from candidate_knowledge_search import CandidateKnowledgeSearchService, reciprocal_rank_fusion
from candidate_knowledge_types import (
    Actionability,
    CandidateKnowledgeRecord,
    CandidateKnowledgeSubject,
)


def _record(
    *,
    app_key: str,
    company: str = "WATHEFNI",
    text: str = "",
    version_id: str = "v1",
    facts: dict | None = None,
    classifications: dict | None = None,
    name: str | None = "Candidate",
) -> CandidateKnowledgeRecord:
    return CandidateKnowledgeRecord(
        candidate_ref=f"app:{app_key}",
        company_code=company,
        as_of="2026-07-26T00:00:00Z",
        knowledge_version="candidate-knowledge-phase4-v1",
        subject=CandidateKnowledgeSubject(display_name=name),
        canonical_cv={
            "version_id": version_id,
            "text": text,
            "channel": "email",
            "content_hash": "hash-" + version_id,
        }
        if text
        else {},
        effective_facts={"effective": facts or {}},
        classifications=classifications or {},
        actionability=Actionability(
            readable=True,
            contact_allowed=False,
            lifecycle_mutation_allowed=True,
            job_ranking_allowed=True,
        ),
    )


def _app(app_key: str, status: str = "needs_role", **kwargs):
    row = {
        "company_code": "WATHEFNI",
        "app_key": app_key,
        "phone": kwargs.pop("phone", f"9655{app_key[-4:].rjust(7, '0')}"),
        "status": status,
        "position_code": kwargs.pop("position_code", "POS-1"),
        "position_title": "Analyst",
        "data_source": "email",
    }
    row.update(kwargs)
    return row


class ChunkerTests(unittest.TestCase):
    def test_deterministic_section_chunking_and_stable_ids(self):
        text = (
            "Summary\nExperienced payroll specialist in Kuwait.\n\n"
            "Experience\n" + ("Payroll operations for NBK. " * 80) + "\n\n"
            "Skills\nExcel, bilingual Arabic English, Oracle.\n\n"
            "Education\nBachelors in Accounting.\n"
        )
        a = chunk_cv_text(text, config=ChunkerConfig(target_tokens=50, overlap_tokens=10))
        b = chunk_cv_text(text, config=ChunkerConfig(target_tokens=50, overlap_tokens=10))
        self.assertEqual([c.text_hash for c in a], [c.text_hash for c in b])
        self.assertTrue(any(c.section_type == "employment" for c in a))
        self.assertTrue(any(c.section_type == "skills" for c in a))
        self.assertTrue(all(c.char_end >= c.char_start for c in a))

    def test_long_cv_tail_retrievable(self):
        head = "Summary\nIntro\n\nExperience\n"
        mid = ("Mid career role with detailed responsibilities across GCC banks. " * 400)
        tail_marker = "UNIQUE_TAIL_CERTIFICATION_ORACLE_FUSION_2024"
        text = head + mid + f"\n\nCertifications\n{tail_marker}\n"
        self.assertGreater(len(text), 12000)
        chunks = chunk_cv_text(text, config=ChunkerConfig(target_tokens=100, overlap_tokens=20))
        joined = "\n".join(c.text for c in chunks)
        self.assertIn(tail_marker, joined)
        self.assertGreater(max(c.char_start for c in chunks), 6000)

    def test_arabic_and_bilingual_language_detection(self):
        ar = chunk_cv_text("الملخص\nمحاسب ذو خبرة في الرواتب\n\nالمهارات\nإكسل، محاسبة")
        self.assertTrue(any(c.language == "ar" for c in ar))
        bi = chunk_cv_text("Summary\nBilingual payroll\n\nSkills\nArabic English Excel والرواتب")
        self.assertTrue(any(c.language in {"ar_en", "en", "ar"} for c in bi))
        self.assertEqual(detect_language("Hello والعربية"), "ar_en")

    def test_chunk_size_benchmark_configs(self):
        text = "Experience\n" + ("GCC banking experience. " * 500)
        result = benchmark_chunk_configs(text)
        self.assertEqual(len(result["configs"]), 3)
        counts = [item["chunk_count"] for item in result["configs"]]
        self.assertTrue(counts[0] >= counts[1] >= counts[2])


class IndexerSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = InMemoryCandidateKnowledgeIndexStore()
        self.embedder = MockEmbeddingProvider(dimensions=32)
        self.indexer = CandidateKnowledgeIndexer(self.index, embedder=self.embedder)
        self.search = CandidateKnowledgeSearchService(self.index, embedder=self.embedder)

    def test_schema_ddl_present(self):
        self.assertIn("candidate_knowledge_chunks", PHASE4_LOCAL_SCHEMA_DDL)
        self.assertIn("candidate_knowledge_index_jobs", PHASE4_LOCAL_SCHEMA_DDL)
        self.assertIn("candidate_knowledge_access_events", PHASE4_LOCAL_SCHEMA_DDL)
        self.assertNotIn("candidate_knowledge_records", PHASE4_LOCAL_SCHEMA_DDL)

    def test_current_version_only_default_search(self):
        rec_old = _record(app_key="app-1", text="Experience\nOld payroll text", version_id="v-old")
        self.indexer.index_from_knowledge_record(rec_old, application=_app("app-1"), force_state="current")
        for chunk in self.index.list_chunks(company_code="WATHEFNI", app_key="app-1"):
            chunk["state"] = "superseded"
        rec_new = _record(app_key="app-1", text="Experience\nNew oracle fusion payroll", version_id="v-new")
        self.indexer.index_from_knowledge_record(rec_new, application=_app("app-1"), force_state="current")
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="oracle fusion",
            scope="talent_pool",
        )
        self.assertEqual(result["retrieval_mode"] in {"hybrid", "lexical_only"}, True)
        self.assertTrue(result["items"])
        versions = {item["index_version"]["document_version_id"] for item in result["items"]}
        self.assertEqual(versions, {"v-new"})

    def test_invalidated_and_restricted_excluded(self):
        rec = _record(app_key="app-x", text="Skills\nExcel payroll")
        self.indexer.index_from_knowledge_record(rec, application=_app("app-x"))
        self.index.invalidate_chunks(company_code="WATHEFNI", app_key="app-x")
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(result["items"], [])

        rec2 = _record(app_key="app-r", text="Skills\nExcel")
        self.indexer.index_from_knowledge_record(
            rec2,
            application=_app("app-r"),
            governance={"restriction_state": "restricted"},
        )
        result2 = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="Excel",
            scope="talent_pool",
        )
        self.assertEqual(result2["items"], [])

    def test_identity_ownership_correction_order(self):
        old = _record(app_key="app-old", text="Skills\nOwnership old phone candidate")
        self.indexer.index_from_knowledge_record(old, application=_app("app-old", phone="111"))
        new = _record(app_key="app-new", text="Skills\nOwnership corrected candidate")
        outcome = self.indexer.process_identity_correction(
            company_code="WATHEFNI",
            old_app_key="app-old",
            new_record=new,
            new_application=_app("app-new", phone="222"),
        )
        self.assertGreater(outcome["invalidated"], 0)
        old_states = {c["state"] for c in self.index.list_chunks(company_code="WATHEFNI", app_key="app-old")}
        self.assertEqual(old_states, {"invalidated"})
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="Ownership corrected",
            scope="talent_pool",
        )
        refs = {item["candidate_ref"] for item in result["items"]}
        self.assertIn("app:app-new", refs)
        self.assertNotIn("app:app-old", refs)

    def test_many_chunks_do_not_dominate_and_surname_no_merge(self):
        long_text = "Experience\n" + ("Kuwait payroll role. " * 300)
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-long", text=long_text, name="Ali Almutairi"),
            application=_app("app-long", phone="96550000001", status="needs_role"),
        )
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-short", text="Skills\nKuwait payroll specialist Excel", name="Sara Almutairi"),
            application=_app("app-short", phone="96550000002", status="needs_role"),
        )
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="Kuwait payroll",
            scope="talent_pool",
            limit=10,
        )
        refs = [item["candidate_ref"] for item in result["items"]]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertIn("app:app-short", refs)
        self.assertIn("app:app-long", refs)
        # Same surname must not merge.
        self.assertEqual(len(refs), 2)

    def test_lexical_semantic_hybrid_and_structured_filters(self):
        self.indexer.index_from_knowledge_record(
            _record(
                app_key="app-a",
                text="Skills\nbilingual payroll Excel Oracle",
                facts={"skills": ["payroll", "Excel"]},
                classifications={
                    "hr_confirmed": [{"node_id": "role.payroll", "label": "Payroll", "node_type": "role"}],
                    "ai_suggested": [{"node_id": "skill.excel", "label": "Excel", "node_type": "skill"}],
                },
            ),
            application=_app("app-a", status="needs_role"),
        )
        hybrid = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="bilingual payroll Excel",
            scope="talent_pool",
            filters={"classification_node_ids": ["role.payroll"]},
        )
        self.assertIn(hybrid["retrieval_mode"], {"hybrid", "lexical_only"})
        self.assertTrue(hybrid["items"])
        self.assertIn("hr_confirmed", hybrid["items"][0]["classifications"])
        self.assertIn("ai_suggested", hybrid["items"][0]["classifications"])
        self.assertNotEqual(
            hybrid["items"][0]["classifications"]["hr_confirmed"],
            None,
        )

        lexical = CandidateKnowledgeSearchService(
            self.index, embedder=self.embedder, force_lexical_only=True
        ).search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(lexical["retrieval_mode"], "lexical_only")

        structured = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="",
            scope="talent_pool",
            filters={"classification_node_ids": ["role.payroll"]},
        )
        self.assertEqual(structured["retrieval_mode"], "structured_only")

    def test_voyage_failure_disclosed(self):
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-a", text="Skills\npayroll"),
            application=_app("app-a"),
        )
        failing = MockEmbeddingProvider(dimensions=32, fail=True)
        service = CandidateKnowledgeSearchService(self.index, embedder=failing)
        # Indexed embeddings exist; query embedding fails → degraded/lexical fallback.
        # Re-use existing chunk embeddings but fail query embed.
        result = service.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(result["retrieval_mode"], "retrieval_degraded")
        self.assertIsNotNone(result["embedding"]["error"])

    def test_stable_pagination(self):
        for i in range(25):
            self.indexer.index_from_knowledge_record(
                _record(app_key=f"app-{i:03d}", text=f"Skills\npayroll specialist variant {i}"),
                application=_app(f"app-{i:03d}", phone=f"9655001{i:04d}"),
            )
        page1 = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
            limit=10,
        )
        page2 = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
            limit=10,
            cursor=page1["next_cursor"],
        )
        refs1 = [item["candidate_ref"] for item in page1["items"]]
        refs2 = [item["candidate_ref"] for item in page2["items"]]
        self.assertEqual(len(refs1), 10)
        self.assertTrue(refs2)
        self.assertEqual(set(refs1) & set(refs2), set())

    def test_thousands_candidate_synthetic_search(self):
        start = time.perf_counter()
        for i in range(1200):
            marker = "needle-gcc-payroll" if i == 777 else f"general-profile-{i}"
            self.indexer.index_from_knowledge_record(
                _record(app_key=f"syn-{i:04d}", text=f"Skills\n{marker}"),
                application=_app(f"syn-{i:04d}", phone=f"971500{i:06d}"),
            )
        indexed_ms = (time.perf_counter() - start) * 1000
        search_start = time.perf_counter()
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="needle-gcc-payroll",
            scope="talent_pool",
            limit=5,
        )
        search_ms = (time.perf_counter() - search_start) * 1000
        self.assertGreaterEqual(result["total"], 1)
        self.assertIn("app:syn-0777", {item["candidate_ref"] for item in result["items"]})
        self.assertLess(search_ms, 5000)
        self._synthetic_metrics = {
            "candidates": 1200,
            "index_ms": round(indexed_ms, 2),
            "search_ms": round(search_ms, 2),
            "chunk_count": result["index_freshness"]["chunk_count"],
        }

    def test_cross_tenant_denial(self):
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-a", company="OTHER", text="Skills\npayroll"),
            application=_app("app-a", company_code="OTHER"),
        )
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(result["items"], [])

    def test_held_talent_pool_searchable_not_actionable(self):
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-held", text="Skills\npayroll excel"),
            application=_app("app-held", status="needs_role"),
        )
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertTrue(result["items"])
        action = result["items"][0]["actionability"]
        self.assertFalse(action["contact_allowed"])
        self.assertFalse(action["lifecycle_mutation_allowed"])
        self.assertFalse(action["job_ranking_allowed"])

    def test_no_pii_notes_private_evidence(self):
        dirty = "Contact me at person@example.com or +96550001111. Skills payroll."
        cleaned = redact_pii_for_index(dirty)
        self.assertNotIn("person@example.com", cleaned)
        self.assertIn("[REDACTED_EMAIL]", cleaned)
        rec = _record(app_key="app-pii", text=f"Skills\n{dirty}")
        self.indexer.index_from_knowledge_record(rec, application=_app("app-pii"))
        for chunk in self.index.list_chunks(company_code="WATHEFNI", app_key="app-pii"):
            self.assertNotIn("person@example.com", chunk["chunk_text"])
            self.assertNotIn("private note", chunk["chunk_text"].lower())

        # Notes must not be indexed even if mistakenly present on record.
        rec2 = _record(app_key="app-notes", text="Skills\nExcel")
        rec2.notes = [{"body": "private HR note should never embed"}]
        self.indexer.index_from_knowledge_record(rec2, application=_app("app-notes"))
        joined = "\n".join(c["chunk_text"] for c in self.index.list_chunks(company_code="WATHEFNI", app_key="app-notes"))
        self.assertNotIn("private HR note", joined)

    def test_zero_mutations_and_no_production_access(self):
        before = (
            self.index.lifecycle_mutations,
            self.index.communication_mutations,
            self.index.ranking_mutations,
            self.index.identity_mutations,
            self.index.production_access_attempts,
        )
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-z", text="Skills\npayroll"),
            application=_app("app-z"),
        )
        self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(
            (
                self.index.lifecycle_mutations,
                self.index.communication_mutations,
                self.index.ranking_mutations,
                self.index.identity_mutations,
                self.index.production_access_attempts,
            ),
            before,
        )
        with self.assertRaises(RuntimeError):
            self.index.mutate_lifecycle()
        with self.assertRaises(RuntimeError):
            self.index.mutate_communication()
        with self.assertRaises(RuntimeError):
            self.index.mutate_ranking()
        with self.assertRaises(RuntimeError):
            self.index.mutate_identity()
        with self.assertRaises(RuntimeError):
            self.index.access_production()
        self.assertTrue(self.index.access_events)
        for event in self.index.access_events:
            self.assertNotIn("chunk_text", event)
            self.assertNotIn("snippet", event)

    def test_index_not_ready_and_rrf(self):
        empty = CandidateKnowledgeSearchService(InMemoryCandidateKnowledgeIndexStore(), embedder=self.embedder)
        result = empty.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(result["retrieval_mode"], "index_not_ready")
        fused = reciprocal_rank_fusion({"lexical": ["a", "b"], "semantic": ["b", "c"]})
        self.assertGreater(fused["b"], fused["a"])

    def test_active_applications_scope(self):
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-held", text="Skills\npayroll"),
            application=_app("app-held", status="needs_role"),
        )
        self.indexer.index_from_knowledge_record(
            _record(app_key="app-live", text="Skills\npayroll"),
            application=_app("app-live", status="shortlisted"),
        )
        result = self.search.search(
            company_code="WATHEFNI",
            actor_user_id="u1",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="active_applications",
        )
        refs = {item["candidate_ref"] for item in result["items"]}
        self.assertIn("app:app-live", refs)
        self.assertNotIn("app:app-held", refs)

    def test_query_cache_and_mock_embeddings_deterministic(self):
        a = deterministic_mock_embedding("payroll", dimensions=16)
        b = deterministic_mock_embedding("payroll", dimensions=16)
        self.assertEqual(a, b)
        cache = QueryEmbeddingCache(ttl_seconds=60)
        cache.put(company_code="WATHEFNI", model="mock", query="payroll", policy_scope="talent_pool", vector=a)
        self.assertEqual(
            cache.get(company_code="WATHEFNI", model="mock", query="payroll", policy_scope="talent_pool"),
            a,
        )
        self.assertEqual(cache.hits, 1)


if __name__ == "__main__":
    unittest.main()
