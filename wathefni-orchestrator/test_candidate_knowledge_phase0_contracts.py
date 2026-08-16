"""Phase 0 frozen contract tests for Candidate Knowledge.

Updated during runtime/source reconciliation (2026-07-26):
- Historical drift pins remain asserted against the Phase 0 / reconciliation
  evidence packs (preimage local copies).
- Live checkout assertions now expect the reconciled production contracts.

Does not implement CandidateKnowledgeAuthority, mutate production, call Voyage,
or index.
"""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path

import action_registry as ar
import candidate_cv_evidence as cve
import candidate_cv_facts as cvf
import candidate_knowledge_types as ckt
import candidate_ranking as cr
import cv_extraction
import inbound_retention_policy as irp
import tool_call_orchestrator as tc
from fixtures.candidate_knowledge_phase0 import (
    HELD_STATES,
    LONG_CV_BEYOND_12000,
    MANUAL_SURROGATE,
    MARIAM_ALMULLA,
    MULTIPLE_APPLICATIONS_ONE_CANDIDATE,
    PERMISSION_FIXTURES,
    REAL_PHONE_CONTROL,
    REVIEW_PENDING_POLICY_MATRIX,
    TENANT_ISOLATION,
    UNRELATED_ALMULLA_FAMILY,
    all_fixtures,
    long_cv_text,
)


ROOT = Path(__file__).resolve().parent
EVIDENCE_DIR = ROOT.parent / "ops" / "evidence" / "candidate-knowledge-phase0"
RECON_DIR = ROOT.parent / "ops" / "evidence" / "candidate-knowledge-runtime-reconciliation"
SCHEMA_PATH = ROOT / "schemas" / "candidate_knowledge_v1.json"

# SHA-256 of deployed production modules captured 2026-07-26 (read-only).
DEPLOYED_MODULE_SHA256 = {
    "candidate_cv_facts.py": "4c01145e0379554cf3f61a1d06d7d4d1d35859f270549934c1588b142276153d",
    "candidate_cv_evidence.py": "06de2da2fba4638161edcfca64b6a55c2b75f5f63cf5332abee400dd8d5a26f4",
    "candidate_ranking.py": "9b8a54f19d10da7ddd8c1ef8b5207833cde4aa1cfc71e3b72d47bae1f3efd8c8",
}

# Production runtime authority SHAs captured during reconciliation.
PRODUCTION_RUNTIME_SHA256 = {
    "cv_extraction.py": "2859dc7e5e9598fc26e4561aaf5ecda8bcc26b0f62a30e04121ab18a4e18a229",
    "action_registry.py": "b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb",
    "app.py": "b4a9a4b032abee27e75ec6b4fc382b0797889a935af4d6529af29bf6574a7dd5",
}

# Preimage local SHAs from Phase 0 NO-GO (preserved as historical evidence).
PHASE0_PREIMAGE_LOCAL_SHA256 = {
    "cv_extraction.py": "4dace00f5ab197b79d638acb1c44b108d261ae34c85132f8da008549d633c0d9",
    "action_registry.py": "92ea89bcfcab973bd4270bc6c5a56ba7dcb4bed8e23162afa974e06be844fc1a",
    "app.py": "d7a9f7ec25f85a272076102366ad7ce4f6aaa6e3e67b81047c37f1bc7e32192c",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class RestoredModuleInventoryTests(unittest.TestCase):
    def test_restored_modules_match_deployed_sha256(self):
        for name, expected in DEPLOYED_MODULE_SHA256.items():
            path = ROOT / name
            self.assertTrue(path.is_file(), f"missing restored module {name}")
            self.assertEqual(_sha256(path), expected, f"SHA drift for {name}")
            evidence_copy = EVIDENCE_DIR / name
            self.assertTrue(evidence_copy.is_file(), f"missing evidence pack copy {name}")
            self.assertEqual(_sha256(evidence_copy), expected, f"evidence pack drift for {name}")

    def test_module_contract_versions_frozen(self):
        self.assertEqual(cvf.CV_FACTS_CONTRACT_VERSION, "application-cv-facts-v1")
        self.assertEqual(cvf.CV_FACTS_EXTRACTOR_VERSION, "cv-facts-deterministic-v1")
        self.assertEqual(cve.CV_EVIDENCE_CONTRACT_VERSION, "application-cv-evidence-v1")
        self.assertEqual(cr.SCORING_CONFIG_VERSION, "ranking-soft-v2")
        self.assertEqual(cr.CANONICAL_EMBEDDING_MODEL, "voyage-4-large")


class HistoricalDriftEvidenceTests(unittest.TestCase):
    """Preserve Phase 0 NO-GO evidence: preimage local disagreed with production."""

    def test_preimage_local_copies_retain_phase0_drift_hashes(self):
        for name, expected in PHASE0_PREIMAGE_LOCAL_SHA256.items():
            path = RECON_DIR / "local" / name
            self.assertTrue(path.is_file(), f"missing preimage {name}")
            self.assertEqual(_sha256(path), expected, f"preimage hash changed for {name}")

    def test_preimage_lacked_finalization_and_facts_wiring(self):
        pre_cv = _source(RECON_DIR / "local" / "cv_extraction.py")
        pre_app = _source(RECON_DIR / "local" / "app.py")
        self.assertNotIn("def record_extraction_finalization", pre_cv)
        self.assertNotIn("import candidate_cv_facts", pre_app)
        self.assertNotIn("rank_candidates_compat", pre_app)
        self.assertNotIn("materialize_extracted_cv", pre_app)

    def test_preimage_registry_had_obsolete_semantic_rank_defects(self):
        pre_ar = _source(RECON_DIR / "local" / "action_registry.py")
        self.assertIn("RANK_CANDIDATES_POOL_LIMIT", pre_ar)
        self.assertIn("legacy.rank_candidate_row(", pre_ar)
        self.assertIn('screening.get("status")', pre_ar)
        # Production registry no longer uses that obsolete scorer path.
        prod_ar = _source(RECON_DIR / "production" / "action_registry.py")
        self.assertNotIn("legacy.rank_candidate_row(", prod_ar)
        self.assertIn("import candidate_ranking as _candidate_ranking", prod_ar)


class ReconciledRuntimeContractTests(unittest.TestCase):
    def test_cv_extraction_matches_production_and_exposes_finalization(self):
        self.assertEqual(_sha256(ROOT / "cv_extraction.py"), PRODUCTION_RUNTIME_SHA256["cv_extraction.py"])
        self.assertTrue(hasattr(cv_extraction, "record_extraction_finalization"))
        self.assertIn("cv_extraction_finalizations", _source(ROOT / "cv_extraction.py"))

    def test_action_registry_matches_production(self):
        self.assertEqual(_sha256(ROOT / "action_registry.py"), PRODUCTION_RUNTIME_SHA256["action_registry.py"])
        self.assertEqual(len(ar.REGISTRY), 75)
        self.assertTrue(ar.is_registered("rank_candidates"))
        self.assertTrue(ar.is_registered("candidate_cv_evaluation"))
        self.assertFalse(ar.is_registered("compare_candidates"))

    def test_app_wires_facts_evidence_ranking_compat(self):
        app_source = _source(ROOT / "app.py")
        self.assertIn("import candidate_cv_facts", app_source)
        self.assertIn("import candidate_cv_evidence", app_source)
        self.assertIn("import candidate_ranking", app_source)
        self.assertIn("rank_candidates_compat", app_source)
        self.assertIn("materialize_extracted_cv", app_source)
        self.assertIn("extract_application_cv_facts", app_source)
        self.assertIn("talent_pool_auto_email", app_source)
        # Reconciled app is production + local-only additive graft, so SHA differs.
        self.assertNotEqual(_sha256(ROOT / "app.py"), PRODUCTION_RUNTIME_SHA256["app.py"])
        self.assertIn("LOCAL-ONLY ADDITIVE SURFACE", app_source)
        self.assertIn("def _unified_candidate_profile_payload", app_source)
        self.assertIn("def internal_intake_worker_run", app_source)


class RecruiterLimitsAndExclusionsTests(unittest.TestCase):
    def test_cv_evaluation_text_cap_is_6000(self):
        self.assertEqual(ar.CV_TEXT_MAX_CHARS, 6000)

    def test_rank_pool_and_top_n_defaults_pinned_in_app_source(self):
        app_source = _source(ROOT / "app.py")
        self.assertIn("RANK_CANDIDATES_DEFAULT_TOP_N = 5", app_source)
        self.assertIn("RANK_CANDIDATES_MAX_TOP_N = 10", app_source)
        self.assertIn("RANK_CANDIDATES_POOL_LIMIT = 500", app_source)

    def test_production_registry_rank_is_job_scoped_canonical(self):
        source = _source(ROOT / "action_registry.py")
        self.assertIn("job-scoped canonical Ranking authority", source)
        self.assertIn('getattr(legacy, "RANK_CANDIDATES_MAX_TOP_N", 10)', source)
        self.assertIn('getattr(legacy, "RANK_CANDIDATES_DEFAULT_TOP_N", 5)', source)
        # Obsolete local pool-limit semantic scorer path must not return.
        self.assertNotIn('getattr(legacy, "RANK_CANDIDATES_POOL_LIMIT", 200)', source)

    def test_production_predicate_excludes_held_intake_statuses(self):
        app_source = _source(ROOT / "app.py")
        self.assertIn("NOT IN ('needs_role','import_review','import_archived')", app_source)
        for held in HELD_STATES:
            self.assertIn(held["status"], ("needs_role", "import_review", "import_archived"))

    def test_voyage_document_embed_truncates_at_12000_in_app_source(self):
        app_source = _source(ROOT / "app.py")
        self.assertIn("content[:12000]", app_source)
        self.assertIn('"cv_text": text[:12000]', app_source)

    def test_long_cv_fixture_exceeds_embed_and_eval_windows(self):
        text = long_cv_text()
        self.assertGreaterEqual(len(text), LONG_CV_BEYOND_12000["expected"]["char_count_min"])
        self.assertIn(LONG_CV_BEYOND_12000["expected"]["head_token"], text[:6000])
        self.assertNotIn(LONG_CV_BEYOND_12000["expected"]["tail_token"], text[:6000])
        self.assertNotIn(LONG_CV_BEYOND_12000["expected"]["tail_token"], text[:12000])
        self.assertIn(LONG_CV_BEYOND_12000["expected"]["tail_token"], text[12000:])


class ProductionBehaviorPinTests(unittest.TestCase):
    """Re-verified against production source after reconciliation — not old local assumptions."""

    def test_compare_candidates_not_registry_registered_in_production(self):
        self.assertTrue(ar.is_registered("rank_candidates"))
        self.assertTrue(ar.is_registered("candidate_cv_evaluation"))
        self.assertFalse(ar.is_registered("compare_candidates"))
        self.assertIn("def compare_candidates(", _source(ROOT / "app.py"))

    def test_production_rank_executor_does_not_call_rank_candidate_row(self):
        registry_source = _source(ROOT / "action_registry.py")
        self.assertNotIn("legacy.rank_candidate_row(", registry_source)
        self.assertIn("to_legacy_rank_candidates_shape", registry_source)
        # Historical local defect evidence retained in preimage pack.
        preimage = _source(RECON_DIR / "local" / "action_registry.py")
        self.assertIn("legacy.rank_candidate_row(", preimage)

    def test_production_rank_executor_has_no_screening_before_assignment_defect(self):
        registry_source = _source(ROOT / "action_registry.py")
        self.assertNotIn(
            'row_screening_status = str(row.get("screening_status") or screening.get("status") or "").lower()',
            registry_source,
        )
        preimage = _source(RECON_DIR / "local" / "action_registry.py")
        self.assertIn(
            'row_screening_status = str(row.get("screening_status") or screening.get("status") or "").lower()',
            preimage,
        )

    def test_empty_permissions_still_admit_read_tools_when_strict_flag_off(self):
        scope = {"permissions": [], "company_id": "WATHEFNI"}
        previous = os.environ.pop("WATHEFNI_STRICT_WHATSAPP_PERMS", None)
        try:
            allowed_rank, required_rank = tc._tool_allowed("rank_candidates", scope)
            allowed_eval, required_eval = tc._tool_allowed("candidate_cv_evaluation", scope)
        finally:
            if previous is not None:
                os.environ["WATHEFNI_STRICT_WHATSAPP_PERMS"] = previous
        self.assertTrue(allowed_rank)
        self.assertTrue(allowed_eval)
        self.assertEqual(required_rank, "prehire.read")
        self.assertEqual(required_eval, "prehire.read")
        self.assertEqual(
            PERMISSION_FIXTURES["empty_permissions"]["expected_current_tool_admission"]["rank_candidates"],
            True,
        )


class RankingPathParityBoundaryTests(unittest.TestCase):
    def test_both_paths_use_candidate_ranking_compat_surface(self):
        self.assertTrue(callable(ar._rank_candidates_executor))
        self.assertTrue(callable(cr.rank_candidates_compat))
        app_source = _source(ROOT / "app.py")
        self.assertIn("def rank_candidates(", app_source)
        self.assertIn("rank_candidates_compat", app_source)
        registry_source = _source(ROOT / "action_registry.py")
        self.assertIn("import candidate_ranking as _candidate_ranking", registry_source)

    def test_parity_boundary_documented_in_evidence_pack(self):
        notes_path = EVIDENCE_DIR / "ranking-path-notes.json"
        self.assertTrue(notes_path.is_file())
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
        self.assertEqual(notes["paths"]["registry_rank"], "action_registry._rank_candidates_executor")
        self.assertIn("parity_boundary", notes)
        self.assertFalse(notes["parity_boundary"]["scores_must_match"])
        self.assertTrue(notes["parity_boundary"]["tenant_and_held_exclusions_must_agree"])


class FixtureCoverageTests(unittest.TestCase):
    def test_fixture_pack_includes_required_cases(self):
        pack = all_fixtures()
        required = {
            "mariam_almulla",
            "unrelated_almulla_family",
            "open_identity_review",
            "held_states",
            "review_pending_policy_matrix",
            "long_cv_beyond_12000",
            "multiple_applications_one_candidate",
            "manual_surrogate",
            "real_phone_control",
            "permission_fixtures",
            "tenant_isolation",
        }
        self.assertEqual(required, set(pack))

    def test_gcc_shared_surname_identities_remain_distinct(self):
        family_keys = {item["app_key"] for item in UNRELATED_ALMULLA_FAMILY}
        self.assertNotIn(MARIAM_ALMULLA["app_key"], family_keys)
        for item in UNRELATED_ALMULLA_FAMILY:
            self.assertEqual(item["identity"]["shared_surname"], "Almulla")
            self.assertIn(MARIAM_ALMULLA["app_key"], item["identity"]["must_not_match_app_keys"])
            self.assertNotEqual(item["email"], MARIAM_ALMULLA["email"])
            self.assertNotEqual(item["phone"], MARIAM_ALMULLA["phone"])

    def test_manual_surrogate_is_not_real_phone(self):
        self.assertTrue(str(MANUAL_SURROGATE["phone"]).startswith("imp-"))
        self.assertNotEqual(MANUAL_SURROGATE["phone"], REAL_PHONE_CONTROL["phone"])
        self.assertEqual(
            MANUAL_SURROGATE["provenance"]["must_not_merge_to_real_phone"],
            REAL_PHONE_CONTROL["phone"],
        )

    def test_multiple_applications_bound_by_phone(self):
        apps = MULTIPLE_APPLICATIONS_ONE_CANDIDATE["applications"]
        self.assertEqual(len(apps), 3)
        self.assertEqual(len({item["app_key"] for item in apps}), 3)
        self.assertEqual(MULTIPLE_APPLICATIONS_ONE_CANDIDATE["expected"]["bound_by"], "phone")

    def test_tenant_isolation_fixture_uses_distinct_company_codes(self):
        a = TENANT_ISOLATION["tenant_a"]
        b = TENANT_ISOLATION["tenant_b"]
        self.assertNotEqual(a["company_code"], b["company_code"])
        self.assertNotEqual(a["app_key"], b["app_key"])
        self.assertNotEqual(a["phone"], b["phone"])

    def test_review_pending_domain_matrix_pins_intentional_divergence(self):
        domains = REVIEW_PENDING_POLICY_MATRIX["domains"]
        self.assertFalse(domains["production_search_predicate"]["excluded"])
        self.assertTrue(domains["inbound_identity_retention"]["treated_as_held"])
        self.assertIn("review_pending", irp.HELD_APPLICATION_STATUSES)
        app_source = _source(ROOT / "app.py")
        import re

        predicate_match = re.search(
            r"def production_application_predicate\([\s\S]*?NOT IN \(([^)]+)\)",
            app_source,
        )
        self.assertIsNotNone(predicate_match)
        self.assertNotIn("review_pending", predicate_match.group(1))


class CandidateKnowledgeV1ContractTests(unittest.TestCase):
    def test_schema_const_and_ref_helpers(self):
        self.assertEqual(ckt.CANDIDATE_KNOWLEDGE_SCHEMA, "candidate-knowledge-v1")
        self.assertEqual(ckt.candidate_ref_from_app_key("abc"), "app:abc")
        self.assertEqual(ckt.app_key_from_candidate_ref("app:abc"), "abc")
        with self.assertRaises(ValueError):
            ckt.app_key_from_candidate_ref("abc")

    def test_dto_to_dict_matches_required_schema_keys(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        record = ckt.CandidateKnowledgeRecord(
            candidate_ref="app:app-mariam-almulla-hr",
            company_code="WATHEFNI",
            as_of="2026-07-26T17:22:49Z",
            knowledge_version="phase0-contract",
            subject=ckt.CandidateKnowledgeSubject(display_name="Mariam Almulla"),
            coverage=[
                ckt.CoverageItem(
                    section="canonical_cv",
                    state="not_extracted",
                    reason_codes=("phase0_contract_only",),
                )
            ],
            evidence_manifest=[
                ckt.EvidenceRef(
                    evidence_id="ev-1",
                    source_kind="fixture",
                    source_record_id="app-mariam-almulla-hr",
                    company_code="WATHEFNI",
                )
            ],
            actionability=ckt.Actionability(
                readable=False,
                contact_allowed=False,
                lifecycle_mutation_allowed=False,
                job_ranking_allowed=False,
                reason_codes=("phase0_contract_only",),
            ),
        )
        payload = record.to_dict()
        for key in schema["required"]:
            self.assertIn(key, payload)
        self.assertEqual(payload["schema"], "candidate-knowledge-v1")
        self.assertEqual(payload["candidate_ref"], "app:app-mariam-almulla-hr")

    def test_no_authority_implementation_in_phase0(self):
        # Historical Phase 0 pin: types-only existed then. Phase 1 later added the
        # authority shell; preserve the Phase 0 evidence pack expectation and the
        # types module contract.
        self.assertTrue((ROOT / "candidate_knowledge_types.py").is_file())
        self.assertEqual(ckt.CANDIDATE_KNOWLEDGE_SCHEMA, "candidate-knowledge-v1")
        # Phase 0 evidence: authority file was absent at Phase 0 capture time.
        # After Phase 1 it may exist; do not treat current presence as Phase 0 failure.
        phase0_report = ROOT.parent / "ops" / "PREHIRING_CANDIDATE_KNOWLEDGE_PHASE_0_CONTRACT_CAPTURE.md"
        self.assertTrue(phase0_report.is_file())
        report = phase0_report.read_text(encoding="utf-8")
        self.assertIn("no `candidate_knowledge_authority.py`", report)


if __name__ == "__main__":
    unittest.main()
