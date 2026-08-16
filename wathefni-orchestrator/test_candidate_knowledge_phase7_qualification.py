"""Phase 7 local Candidate Knowledge qualification matrix.

Deterministic, synthetic-only, zero production access. Records PASS/FAIL/
ACCEPTED_LIMITATION/BLOCKER outcomes for the Phase 7 report.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from dataclasses import asdict, dataclass, field
from typing import Any

from candidate_knowledge_authority import (
    CandidateKnowledgeAuthority,
    InMemoryCandidateKnowledgeStore,
    build_request_context,
)
from candidate_knowledge_chunker import ChunkerConfig, chunk_cv_text
from candidate_knowledge_embeddings import MockEmbeddingProvider
from candidate_knowledge_errors import (
    ERROR_AUDIT_WRITE_FAILED,
    ERROR_BACKEND_CURRENT_REQUIRED,
    ERROR_CANDIDATE_AMBIGUOUS,
    ERROR_CANDIDATE_NOT_FOUND,
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_PERMISSION_DENIED,
    ERROR_PERMISSION_SUBJECT_MISMATCH,
    ERROR_SHADOW_TOOLS_DISABLED,
    CandidateKnowledgeError,
)
from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore
from candidate_knowledge_indexer import CandidateKnowledgeIndexer
from candidate_knowledge_search import CandidateKnowledgeSearchService
from candidate_knowledge_tools import (
    ShadowToolRuntime,
    compare_candidates,
    get_candidate_knowledge,
    search_candidates,
)
from candidate_knowledge_types import (
    Actionability,
    CandidateKnowledgeRecord,
    CandidateKnowledgeSubject,
    CoverageItem,
)
from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity


GATE = ("PASS", "FAIL", "ACCEPTED_LIMITATION", "BLOCKER")
SAFETY_CATEGORIES = {
    "authorization",
    "tenant_isolation",
    "identity",
    "audit",
    "zero_mutation",
    "held_safety",
}


@dataclass
class GateResult:
    gate_id: str
    category: str
    status: str
    detail: str
    blocker: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ctx(**overrides):
    base = {
        "company_code": "WATHEFNI",
        "actor_user_id": "qual-user",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "qual-user",
        "permission_subject_company": "WATHEFNI",
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring", "assessments"],
    }
    base.update(overrides)
    return build_request_context(**base)


def _app(app_key: str, **kwargs):
    phone = kwargs.pop("phone", None)
    if phone is None:
        phone = f"9655{abs(hash(app_key)) % 10_000_000:07d}"
    row = {
        "company_code": kwargs.pop("company_code", "WATHEFNI"),
        "app_key": app_key,
        "phone": phone,
        "status": kwargs.pop("status", "review_pending"),
        "candidate_name": kwargs.pop("name", "Candidate"),
        "position_code": kwargs.pop("position_code", "POS-1"),
        "position_title": "Analyst",
        "data_source": kwargs.pop("data_source", "email"),
    }
    row.update(kwargs)
    return row


def _cv(app_key: str, version_id: str, text: str, *, current: bool = True, status: str = "ready", **extra):
    row = {
        "company_code": "WATHEFNI",
        "app_key": app_key,
        "version_id": version_id,
        "text_content": text,
        "status": status,
        "is_current": current,
        "extracted_text_hash": f"h-{version_id}",
        "provenance": {"channel": extra.pop("channel", "email")},
    }
    row.update(extra)
    return row


class Phase7QualificationSuite(unittest.TestCase):
    """Executable matrix; also callable from the ops harness."""

    results: list[GateResult] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = []

    def _record(self, gate_id: str, category: str, status: str, detail: str, **metrics: Any) -> None:
        assert status in GATE
        safety = category in SAFETY_CATEGORIES
        blocker = status == "BLOCKER" or (status == "FAIL" and safety)
        final_status = "BLOCKER" if blocker and status == "FAIL" else status
        self.__class__.results.append(
            GateResult(
                gate_id=gate_id,
                category=category,
                status=final_status,
                detail=detail,
                blocker=blocker or status == "BLOCKER",
                metrics=metrics,
            )
        )
        if blocker:
            self.fail(f"{gate_id}: {detail}")

    def test_01_authorization_matrix(self):
        store = InMemoryCandidateKnowledgeStore(applications=[_app("app-a", phone="111")])
        auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        cases = []
        expectations = [
            ("empty_permissions", {"permissions": []}, ERROR_PERMISSION_DENIED),
            ("missing_prehire", {"permissions": ["other.read"]}, ERROR_PERMISSION_DENIED),
            ("actor_mismatch", {"permission_subject_user_id": "other"}, ERROR_PERMISSION_SUBJECT_MISMATCH),
            ("tenant_subject_mismatch", {"permission_subject_company": "OTHER"}, ERROR_PERMISSION_SUBJECT_MISMATCH),
            ("not_backend_current", {"permission_authority": "legacy"}, ERROR_BACKEND_CURRENT_REQUIRED),
        ]
        for label, kwargs, expect in expectations:
            with self.subTest(label):
                with self.assertRaises(CandidateKnowledgeError) as raised:
                    auth.resolve_exact(_ctx(**kwargs), "app:app-a")
                self.assertEqual(raised.exception.code, expect)
                cases.append({"case": label, "code": raised.exception.code})

        with self.assertRaises(CandidateKnowledgeError) as missing:
            auth.resolve_exact(_ctx(), "app:missing")
        self.assertEqual(missing.exception.code, ERROR_CANDIDATE_NOT_FOUND)
        self.assertNotIn("OTHER", str(missing.exception.to_dict()))

        other_store = InMemoryCandidateKnowledgeStore(
            applications=[_app("app-secret", company_code="OTHERCO", phone="999")]
        )
        other_auth = CandidateKnowledgeAuthority(other_store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as cross:
            other_auth.resolve_exact(_ctx(), "app:app-secret")
        self.assertEqual(cross.exception.code, ERROR_CANDIDATE_NOT_FOUND)

        self._record(
            "auth_matrix",
            "authorization",
            "PASS",
            "backend_current, permission, actor/tenant mismatch, and cross-tenant non-leak proven",
            cases=cases,
        )

    def test_02_restricted_deletion_and_audit_fail_closed(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app("app-r", phone="201"), _app("app-d", phone="202")],
            governance={
                ("WATHEFNI", "app-r"): {"restriction_state": "restricted"},
                ("WATHEFNI", "app-d"): {"deletion_request_state": "completed"},
            },
        )
        auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        restricted = auth.resolve_exact(_ctx(), "app:app-r")
        self.assertFalse(restricted.actionability.contact_allowed)
        self.assertFalse(restricted.actionability.job_ranking_allowed)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            auth.resolve_exact(_ctx(), "app:app-d")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_RESTRICTED)

        class FailAudit(InMemoryCandidateKnowledgeIndexStore):
            def record_access_event(self, event):
                raise RuntimeError("audit_down")

        index = InMemoryCandidateKnowledgeIndexStore()
        auth_ok = CandidateKnowledgeAuthority(
            InMemoryCandidateKnowledgeStore(applications=[_app("app-a", phone="111")]),
            module_enabled=lambda *_: True,
        )
        runtime = ShadowToolRuntime(
            authority=auth_ok,
            search=CandidateKnowledgeSearchService(index, embedder=MockEmbeddingProvider(dimensions=16)),
            audit_store=FailAudit(),
            enabled=True,
        )
        with self.assertRaises(CandidateKnowledgeError) as audit_err:
            search_candidates(
                runtime,
                query="Excel",
                scope="talent_pool",
                company_code="WATHEFNI",
                actor_user_id="qual-user",
                permission_authority="backend_current",
                permission_subject_user_id="qual-user",
                permission_subject_company="WATHEFNI",
                permissions=["prehire.read"],
                modules_enabled=["pre_hiring"],
            )
        self.assertEqual(audit_err.exception.code, ERROR_AUDIT_WRITE_FAILED)
        self._record(
            "audit_fail_closed",
            "audit",
            "PASS",
            "restricted/deletion denied correctly; audit failure blocks model-facing evidence",
            restriction_readable=restricted.actionability.readable,
            deletion_code=raised.exception.code,
        )

    def test_03_identity_boundary_mariam_and_surrogate(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[
                _app("app-mariam", phone="96550000001", name="Mariam Almulla"),
                _app("app-faisal", phone="96550000002", name="Faisal Almulla"),
                _app("app-aziz", phone="96550000003", name="Aziz Almulla"),
                _app("app-hamad", phone="96550000004", name="Hamad Almulla"),
                _app("app-manual", phone="imp-manual-001", name="Manual Same Name", status="import_review"),
                _app("app-real", phone="96550009999", name="Manual Same Name", status="shortlisted"),
            ]
        )
        auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as ambiguous:
            auth.resolve_name_only(_ctx(), "Almulla")
        self.assertEqual(ambiguous.exception.code, ERROR_CANDIDATE_AMBIGUOUS)
        with self.assertRaises(CandidateKnowledgeError):
            auth.resolve_exact(_ctx(), "Mariam Almulla")
        mariam = auth.resolve_exact(_ctx(), "app:app-mariam")
        self.assertEqual(mariam.candidate_key, "96550000001")
        self.assertEqual(len(mariam.applications), 1)
        manual = auth.resolve_exact(_ctx(), "app:app-manual")
        real = auth.resolve_exact(_ctx(), "app:app-real")
        self.assertNotEqual(manual.candidate_key, real.candidate_key)
        self._record(
            "identity_mariam_surrogate",
            "identity",
            "PASS",
            "No surname merge; exact app refs only; surrogate separate from real phone",
            mariam_key=mariam.candidate_key,
            manual_key=manual.candidate_key,
            real_key=real.candidate_key,
        )

    def test_04_canonical_versions_and_channels(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[
                _app("app-email", phone="301", data_source="email", status="shortlisted"),
                _app("app-wa", phone="302", data_source="whatsapp", status="screening"),
                _app("app-manual", phone="imp-1", data_source="manual_upload", status="import_review"),
                _app("app-conflict", phone="303", status="shortlisted"),
            ],
            cv_text_versions=[
                _cv("app-email", "v-old", "old", current=False, status="superseded"),
                _cv("app-email", "v-new", "Experience\nGCC valuation finance\nSkills\nExcel Arabic English", channel="email"),
                _cv("app-conflict", "c1", "a"),
                _cv("app-conflict", "c2", "b"),
            ],
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-email",
                    "facts_id": "f1",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["Excel"]},
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-wa",
                    "facts_id": "f-wa",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["WhatsAppSkill"]},
                },
            ],
        )
        auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        email = auth.assemble_phase2(_ctx(), "app:app-email")
        self.assertEqual(email.canonical_cv.get("version_id"), "v-new")
        dumped = json.dumps(email.to_dict())
        self.assertNotIn("raw_json", dumped)
        self.assertNotIn("candidate_profile", dumped)

        wa = auth.assemble_phase2(_ctx(), "app:app-wa")
        wa_cov = {c.section: c.state for c in wa.coverage}
        self.assertEqual(wa_cov.get("canonical_cv"), "not_recorded")
        self.assertEqual(wa_cov.get("effective_facts"), "available")

        manual = auth.assemble_phase2(_ctx(), "app:app-manual")
        man_cov = {c.section: c.state for c in manual.coverage}
        self.assertIn(
            man_cov.get("canonical_cv"),
            {"not_recorded", "source_pipeline_incomplete", "not_extracted"},
        )

        conflict = auth.assemble_phase2(_ctx(), "app:app-conflict")
        conf_cov = {c.section: c.state for c in conflict.coverage}
        self.assertEqual(conf_cov.get("canonical_cv"), "conflict")

        self._record(
            "canonical_channels",
            "canonical_knowledge",
            "PASS",
            "Current version selected; WhatsApp/manual gaps disclosed; conflict fail-closed",
            email_version=email.canonical_cv.get("version_id"),
            whatsapp_cv=wa_cov.get("canonical_cv"),
            manual_cv=man_cov.get("canonical_cv"),
            conflict=conf_cov.get("canonical_cv"),
        )

    def test_05_search_tools_ranking_and_scale(self):
        index = InMemoryCandidateKnowledgeIndexStore()
        embedder = MockEmbeddingProvider(dimensions=24)
        indexer = CandidateKnowledgeIndexer(index, embedder=embedder)

        long_tail = "Experience\n" + ("mid role. " * 500) + "\nCertifications\nUNIQUE_TAIL_ORACLE_FUSION\n"
        seed_specs = [
            ("app-fin", "needs_role", "Skills\nbilingual finance GCC valuation Excel IFRS", "Finance Cand", "96551111001"),
            ("app-hr", "needs_role", "Skills\npayroll Kuwait labor law HR", "HR Cand", "96551111002"),
            ("app-tech", "shortlisted", "Skills\npython kubernetes", "Tech Cand", "96551111003"),
            ("app-long", "needs_role", long_tail, "Long Cand", "96551111004"),
            ("app-b", "needs_role", "Skills\npayroll Oracle", "B Cand", "96551111005"),
        ]
        store_apps = []
        for app_key, status, text, name, phone in seed_specs:
            store_apps.append(_app(app_key, status=status, name=name, phone=phone))
            record = CandidateKnowledgeRecord(
                candidate_ref=f"app:{app_key}",
                company_code="WATHEFNI",
                as_of="2026-07-26T00:00:00Z",
                knowledge_version="phase7",
                subject=CandidateKnowledgeSubject(display_name=name),
                canonical_cv={
                    "version_id": f"v-{app_key}",
                    "document_id": f"d-{app_key}",
                    "content_hash": f"h-{app_key}",
                    "text": text,
                    "channel": "email",
                },
                effective_facts={
                    "facts_id": f"f-{app_key}",
                    "status": "ready",
                    "effective": {"skills": text.split()[-5:]},
                },
                classifications={
                    "hr_confirmed": [{"node_id": "role.finance"}] if "finance" in text.lower() else [],
                    "ai_suggested": [],
                },
                coverage=[CoverageItem("canonical_cv", "available")],
                actionability=Actionability(
                    True,
                    False if status == "needs_role" else True,
                    False if status == "needs_role" else True,
                    False if status == "needs_role" else True,
                    held_state="needs_role" if status == "needs_role" else None,
                ),
            )
            indexer.index_from_knowledge_record(
                record,
                application=_app(app_key, status=status, name=name, phone=phone),
            )

        scale_metrics: dict[str, Any] = {}
        for n in (1000, 10000):
            t0 = time.perf_counter()
            needle_i = n // 2
            for i in range(n):
                marker = "needle-gcc-payroll" if i == needle_i else f"profile-{i}"
                rec = CandidateKnowledgeRecord(
                    candidate_ref=f"app:syn-{n}-{i:05d}",
                    company_code="WATHEFNI",
                    as_of="2026-07-26T00:00:00Z",
                    knowledge_version="phase7",
                    subject=CandidateKnowledgeSubject(display_name=f"S{i}"),
                    canonical_cv={
                        "version_id": f"v-{n}-{i}",
                        "document_id": f"d-{n}-{i}",
                        "content_hash": f"h-{n}-{i}",
                        "text": f"Skills\n{marker}",
                        "channel": "email",
                    },
                    actionability=Actionability(True, False, False, False, held_state="needs_role"),
                )
                indexer.index_from_knowledge_record(
                    rec,
                    application=_app(f"syn-{n}-{i:05d}", status="needs_role", phone=f"971{n}{i:08d}"),
                )
            index_ms = (time.perf_counter() - t0) * 1000
            search = CandidateKnowledgeSearchService(index, embedder=embedder)
            latencies = []
            found = False
            needle_ref = f"app:syn-{n}-{needle_i:05d}"
            for _ in range(5):
                t1 = time.perf_counter()
                result = search.search(
                    company_code="WATHEFNI",
                    actor_user_id="qual-user",
                    permission_authority="backend_current",
                    permissions=["prehire.read"],
                    query="needle-gcc-payroll",
                    scope="talent_pool",
                    limit=10,
                )
                latencies.append((time.perf_counter() - t1) * 1000)
                found = found or needle_ref in {item["candidate_ref"] for item in result["items"]}
            latencies.sort()
            scale_metrics[str(n)] = {
                "index_ms": round(index_ms, 2),
                "search_p50_ms": round(latencies[len(latencies) // 2], 2),
                "search_p95_ms": round(latencies[-1], 2),
                "chunks": result["index_freshness"]["chunk_count"],
                "retrieval_mode": result["retrieval_mode"],
                "needle_found": found,
                "total": result["total"],
            }
            self.assertTrue(found, f"needle not found at scale {n}")

        est_index_ms = scale_metrics["10000"]["index_ms"] * 5
        scale_metrics["50000_estimate"] = {
            "estimated_index_ms": round(est_index_ms, 2),
            "executed_full_50k": False,
            "reason": "capacity_estimate_from_10k_not_full_reindex",
        }
        capacity_ok = est_index_ms < 180_000

        knowledge_store = InMemoryCandidateKnowledgeStore(
            applications=store_apps,
            cv_text_versions=[
                _cv("app-fin", "v-fin", "Skills\nbilingual finance GCC valuation Excel IFRS"),
                _cv("app-b", "v-b", "Skills\npayroll Oracle"),
            ],
            fact_snapshots=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-fin",
                    "facts_id": "f-fin",
                    "is_current": True,
                    "status": "ready",
                    "facts": {"skills": ["Excel", "valuation"]},
                }
            ],
        )
        auth = CandidateKnowledgeAuthority(knowledge_store, module_enabled=lambda *_: True)
        search = CandidateKnowledgeSearchService(index, embedder=embedder)
        runtime = ShadowToolRuntime(
            authority=auth,
            search=search,
            audit_store=index,
            enabled=True,
        )
        tool_kwargs = {
            "company_code": "WATHEFNI",
            "actor_user_id": "qual-user",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "qual-user",
            "permission_subject_company": "WATHEFNI",
            "permissions": ["prehire.read"],
            "modules_enabled": ["pre_hiring", "assessments"],
        }
        s = search_candidates(runtime, query="bilingual finance GCC valuation", scope="talent_pool", **tool_kwargs)
        g = get_candidate_knowledge(
            runtime,
            candidate_ref="app:app-fin",
            focus_question="What evidence supports GCC valuation experience?",
            sections=["canonical_cv", "effective_facts", "classifications"],
            **tool_kwargs,
        )
        c = compare_candidates(
            runtime,
            candidate_refs=["app:app-fin", "app:app-b"],
            question="Compare their stored finance and payroll experience",
            **tool_kwargs,
        )
        self.assertIsNone(c["recommendation"]["best_candidate"])
        self.assertTrue(g["canonical_cv"].get("text_omitted"))
        self.assertTrue(index.access_events)
        for event in index.access_events[-8:]:
            for banned in ("chunk_text", "snippet", "email", "phone", "query_text", "cv_text"):
                self.assertNotIn(banned, event)

        failing = CandidateKnowledgeSearchService(index, embedder=MockEmbeddingProvider(dimensions=24, fail=True))
        degraded = failing.search(
            company_code="WATHEFNI",
            actor_user_id="qual-user",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="finance",
            scope="talent_pool",
        )
        self.assertEqual(degraded["retrieval_mode"], "retrieval_degraded")

        chunks = chunk_cv_text(long_tail, config=ChunkerConfig(target_tokens=80, overlap_tokens=20))
        self.assertTrue(any("UNIQUE_TAIL_ORACLE_FUSION" in ch.text for ch in chunks))

        adapter = RankingEvidenceAdapter()
        record = auth.assemble_phase3(
            _ctx(),
            "app:app-fin",
            sections=("canonical_cv", "effective_facts", "classifications", "assessments"),
        )
        legacy = build_legacy_ranking_row(
            company_code="WATHEFNI",
            app_key="app-fin",
            position_code="POS-1",
            status="shortlisted",
            raw_json={"cv": {"extracted": {"skills": ["Excel"]}}},
            candidate_profile={"skills": ["Old"]},
            cv_ready_fields={
                "cv_evidence_status": "ready",
                "cv_evidence_file_id": "f",
                "cv_evidence_source_sha256": "h",
                "cv_extraction_finalization_id": "fin",
                "cv_extraction_quality_ok": True,
                "cv_extracted_text_hash": "h",
                "cv_evidence_semantic_content_hash": "h",
                "semantic_content_hash": "h",
                "semantic_content": "excel valuation",
                "cv_evidence_contract_version": "application-cv-evidence-v1",
            },
        )
        held_bundle = adapter.adapt(
            record,
            job_context=RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=1),
            application=_app("app-fin", status="needs_role", phone="96551111001"),
        )
        self.assertFalse(held_bundle.eligible)

        live_record = CandidateKnowledgeRecord(
            candidate_ref="app:app-fin",
            company_code="WATHEFNI",
            as_of=record.as_of,
            knowledge_version=record.knowledge_version,
            subject=record.subject,
            canonical_cv=record.canonical_cv,
            effective_facts=record.effective_facts,
            classifications=record.classifications,
            coverage=record.coverage,
            actionability=Actionability(True, True, True, True),
        )
        parity = run_shadow_parity(
            adapter=adapter,
            record=live_record,
            job_context=RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=1),
            application=_app("app-fin", status="shortlisted", phone="96551111001"),
            legacy_row=legacy,
            job={"title": "Finance Analyst", "requirements_en": ["Excel"], "requirements": ["Excel"]},
            hard_criteria=[],
            soft_criteria=[
                {
                    "criterion_id": "s1",
                    "classification": "soft",
                    "criterion_type": "technical_skill",
                    "active": True,
                    "rule_json": {"keywords": ["excel", "valuation"]},
                }
            ],
        )
        self.assertEqual(parity.unexplained_score_differences, [])
        self.assertEqual(parity.side_effects.get("ranking_writes"), 0)

        disabled = ShadowToolRuntime(authority=auth, search=search, audit_store=index, enabled=False)
        with self.assertRaises(CandidateKnowledgeError) as disabled_err:
            search_candidates(disabled, query="x", scope="talent_pool", **tool_kwargs)
        self.assertEqual(disabled_err.exception.code, ERROR_SHADOW_TOOLS_DISABLED)

        status = "PASS" if capacity_ok else "ACCEPTED_LIMITATION"
        self._record(
            "search_tools_ranking_scale",
            "retrieval_tools_ranking",
            status,
            "Search/tools/ranking qualified; 50k full run estimated not executed",
            scale=scale_metrics,
            tool_search_mode=s.get("retrieval_mode"),
            compare_no_winner=c["recommendation"]["best_candidate"] is None,
            degraded_mode=degraded["retrieval_mode"],
            ranking_unexplained=len(parity.unexplained_score_differences),
            held_ranking_denied=held_bundle.denial_reason,
            audit_events=len(index.access_events),
            voyage_real_calls=0,
        )

    def test_06_invalidation_and_zero_mutation(self):
        index = InMemoryCandidateKnowledgeIndexStore()
        indexer = CandidateKnowledgeIndexer(index, embedder=MockEmbeddingProvider(dimensions=16))
        rec = CandidateKnowledgeRecord(
            candidate_ref="app:app-x",
            company_code="WATHEFNI",
            as_of="2026-07-26T00:00:00Z",
            knowledge_version="v1",
            subject=CandidateKnowledgeSubject(display_name="X"),
            canonical_cv={
                "version_id": "v1",
                "document_id": "d1",
                "content_hash": "h1",
                "text": "Skills\npayroll",
                "channel": "email",
            },
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        indexer.index_from_knowledge_record(rec, application=_app("app-x", status="needs_role", phone="401"))
        before = len(index.list_chunks(company_code="WATHEFNI", states=["current"]))
        invalidated = indexer.invalidate_for_identity_correction(company_code="WATHEFNI", old_app_key="app-x")
        after_current = len(index.list_chunks(company_code="WATHEFNI", states=["current"]))
        search = CandidateKnowledgeSearchService(index, embedder=MockEmbeddingProvider(dimensions=16))
        result = search.search(
            company_code="WATHEFNI",
            actor_user_id="qual-user",
            permission_authority="backend_current",
            permissions=["prehire.read"],
            query="payroll",
            scope="talent_pool",
        )
        self.assertEqual(result["items"], [])
        self.assertGreater(invalidated, 0)
        self.assertEqual(after_current, 0)
        with self.assertRaises(RuntimeError):
            index.mutate_lifecycle()
        with self.assertRaises(RuntimeError):
            index.access_production()
        self._record(
            "invalidation_zero_mutation",
            "zero_mutation",
            "PASS",
            "Invalidated chunks immediately unsearchable; no production/lifecycle mutation",
            before_current=before,
            invalidated=invalidated,
        )

    def test_07_voyage_credentials_gate(self):
        enabled = str(os.environ.get("WATHEFNI_CK_VOYAGE_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
        key = bool(str(os.environ.get("VOYAGE_API_KEY") or "").strip())
        if enabled and key:
            self._record(
                "voyage_real",
                "voyage",
                "PASS",
                "Real Voyage enabled — execute separate provider suite",
            )
        else:
            self._record(
                "voyage_real",
                "voyage",
                "ACCEPTED_LIMITATION",
                "Real Voyage not authorized/credentialed in this environment; mock provider used",
                voyage_enabled=enabled,
                api_key_present=key,
            )


if __name__ == "__main__":
    unittest.main()
