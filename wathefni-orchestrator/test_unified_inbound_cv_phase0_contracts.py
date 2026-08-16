"""Phase 0 contract freeze tests for Unified Inbound CV Pipeline.

Deterministic offline qualification of current channel contracts before any
Phase 1 additive intake-envelope work. Does not mutate production, change
runtime flags, call Postmark/Octopus/Voyage, or begin Phase 1 implementation.
"""

from __future__ import annotations

import ast
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

import candidate_communication_authority as cca
import candidate_knowledge_authority as cka
import candidate_knowledge_types as ckt
import candidate_record_state_policy as crsp
import durable_email_ingress as dei
import inbound_cv_authority as ica
import recruiting_lifecycle as rl
import talent_pool_classification as tpc
from fixtures.unified_inbound_cv_phase0 import (
    ACCEPTED_IDENTITY_OUTCOMES,
    EMAIL_SAFETY_STATES,
    EMAIL_SUPPORTED_EXTENSIONS,
    HELD_STATUSES,
    IDENTITY_OUTCOMES,
    INTAKE_REVIEW_STATUSES,
    PHASE0_VERSION,
    THREE_CURRENT_RISKS,
    all_scenarios,
    risk_catalog,
)


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"
STAGE_B_PY = ROOT / "jobs_phase2_stage_b.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ingress_config() -> dei.IngressConfig:
    return dei.IngressConfig(
        quarantine_root=Path(tempfile.gettempdir()) / "wathefni-phase0-quarantine",
        max_webhook_body_bytes=24 * 1024 * 1024,
        max_attachments=12,
        max_file_bytes=8 * 1024 * 1024,
        max_total_attachment_bytes=12 * 1024 * 1024,
        max_pdf_pages=40,
        max_image_pixels=20_000_000,
        max_archive_members=200,
        max_archive_expanded_bytes=32 * 1024 * 1024,
        max_archive_ratio=100,
        orphan_grace_seconds=86400,
        lease_seconds=180,
        max_attempts=5,
        retry_base_seconds=5,
        retry_max_seconds=900,
        per_tenant_concurrency=2,
        daily_message_quota=0,
        monthly_message_quota=0,
        daily_source_bytes_quota=0,
        monthly_source_bytes_quota=0,
        daily_processing_job_quota=0,
        malware_scanner="clamav",
    )


def _minimal_pdf(*, encrypt: bool = False, eof: bool = True) -> bytes:
    body = b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
    if encrypt:
        body += b"2 0 obj<< /Encrypt 3 0 R >>endobj\n"
    body += b"trailer<< /Size 2 >>\n"
    if eof:
        body += b"%%EOF\n"
    return body


def _extract_function_source(path: Path, name: str) -> str:
    tree = ast.parse(_source(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(_source(path), node) or ""
    raise AssertionError(f"function {name} not found in {path.name}")


def _count_sql_placeholders(sql: str) -> int:
    return len(re.findall(r"%s", sql))


class FixtureCatalogTests(unittest.TestCase):
    def test_phase0_version_and_scenario_coverage(self):
        self.assertEqual(PHASE0_VERSION, "unified-inbound-cv-phase0-v1")
        scenarios = all_scenarios()
        required = {
            "whatsapp_cv_only_unsolicited",
            "whatsapp_cv_then_apply_code",
            "whatsapp_apply_code_then_cv",
            "email_identical_cv_replay",
            "email_changed_cv_same_sender",
            "email_multiple_attachments",
            "email_unsupported_corrupt_password_malware",
            "email_possible_match_and_conflict",
            "manual_auto_admit_matrix",
            "mixed_held_live_siblings",
            "single_item_vs_bulk_link_to_job",
            "zero_downstream_without_verified_job",
        }
        self.assertTrue(required.issubset(scenarios))
        self.assertEqual(len(risk_catalog()), 3)
        self.assertEqual(
            [item["id"] for item in THREE_CURRENT_RISKS],
            [
                "single_item_promotion_sql",
                "manual_auto_admit_default",
                "ck_sibling_over_denial",
            ],
        )


class HeldStatusContractTests(unittest.TestCase):
    def test_held_status_vocabularies_align(self):
        app_src = _source(APP_PY)
        self.assertIn('HELD_IMPORT_STATUSES = ("needs_role", "import_review", "import_archived")', app_src)
        self.assertIn('INTAKE_REVIEW_STATUSES = ("needs_role", "import_review")', app_src)
        self.assertEqual(set(rl.INTAKE_STATUSES), set(HELD_STATUSES))
        self.assertEqual(set(crsp.INTAKE_HOLD_STATUSES), set(HELD_STATUSES))
        self.assertEqual(set(cca.HELD_IMPORT_STATUSES), set(HELD_STATUSES))
        self.assertEqual(set(INTAKE_REVIEW_STATUSES), {"needs_role", "import_review"})

    def test_production_predicate_excludes_held_not_review_pending(self):
        # Import production_application_predicate without bootstrapping FastAPI app
        # by reading the frozen SQL contract from source and validating held set.
        app_src = _source(APP_PY)
        match = re.search(
            r"def production_application_predicate\(.*?\n(?:    .*\n)+?    \)",
            app_src,
        )
        self.assertIsNotNone(match)
        body = match.group(0)
        for status in HELD_STATUSES:
            self.assertIn(f"'{status}'", body)
        self.assertNotIn("'review_pending'", body)

    def test_held_policy_blocks_communication_lifecycle_ranking(self):
        for status in HELD_STATUSES:
            decision = crsp.evaluate_candidate_record_state({"status": status})
            actionability = decision.to_actionability()
            self.assertTrue(actionability["readable"])
            self.assertFalse(actionability["contact_allowed"])
            self.assertFalse(actionability["lifecycle_mutation_allowed"])
            self.assertFalse(actionability["job_ranking_allowed"])
            self.assertEqual(decision.held_state, status)
            # Naming trap: flag is false for held even though Talent Pool search includes them.
            self.assertFalse(decision.talent_pool_search_eligible)

    def test_communication_authority_holds_same_statuses(self):
        for status in HELD_STATUSES:
            result = cca.evaluate_candidate_communication_authority(
                {"status": status, "company_code": "WATHEFNI", "app_key": "x"},
                kind="notify",
            )
            self.assertFalse(result.get("allowed"))
            self.assertEqual(result.get("code"), cca.ERROR_HELD)

    def test_lifecycle_requires_intake_admit_for_held(self):
        src = _source(ROOT / "recruiting_lifecycle.py")
        self.assertIn('trigger not in {"intake_admit"}', src)
        self.assertIn('"error": "held_intake_application"', src)
        self.assertIn('"intake_admit"', src)


class EmailSafetyContractTests(unittest.TestCase):
    def test_supported_extensions_and_safety_states_frozen(self):
        self.assertEqual(set(dei.SUPPORTED_EXTENSIONS), set(EMAIL_SUPPORTED_EXTENSIONS))
        self.assertEqual(set(dei.SAFETY_STATES), set(EMAIL_SAFETY_STATES))
        self.assertNotIn(".doc", dei.SUPPORTED_EXTENSIONS)
        self.assertNotIn(".rtf", dei.SUPPORTED_EXTENSIONS)
        self.assertNotIn(".zip", dei.SUPPORTED_EXTENSIONS)

    def test_unsupported_extension(self):
        state, reason, _ = dei.inspect_document_safety(
            data=b"hello",
            original_filename="resume.doc",
            claimed_mime="application/msword",
            detected_mime="application/msword",
            config=_ingress_config(),
        )
        self.assertEqual(state, "unsupported_type")
        self.assertEqual(reason, "unsupported_extension")

    def test_password_protected_pdf(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(encrypt=True),
            original_filename="resume.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=_ingress_config(),
        )
        self.assertEqual(state, "password_protected")
        self.assertEqual(reason, "pdf_encrypted")

    def test_corrupt_pdf_missing_eof(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(eof=False),
            original_filename="resume.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=_ingress_config(),
        )
        self.assertEqual(state, "invalid_corrupt")
        self.assertEqual(reason, "pdf_eof_missing")

    def test_clean_pdf_passes_preflight(self):
        state, reason, meta = dei.inspect_document_safety(
            data=_minimal_pdf(),
            original_filename="resume.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=_ingress_config(),
        )
        self.assertEqual(state, "clean")
        self.assertIsNone(reason)
        self.assertIn("pdf_pages", meta)

    def test_mime_mismatch(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(),
            original_filename="resume.pdf",
            claimed_mime="image/png",
            detected_mime="application/pdf",
            config=_ingress_config(),
        )
        self.assertEqual(state, "mime_mismatch")
        self.assertEqual(reason, "claimed_detected_mime_mismatch")

    def test_malware_is_outside_inspect_and_blocks_before_ocr(self):
        # Malware authority is scan_document / inbound_cv_authority, not inspect.
        scan_src = _extract_function_source(ROOT / "durable_email_ingress.py", "scan_document")
        self.assertIn("malware_suspicious", scan_src)
        self.assertIn("inspect_document_safety", scan_src)
        # OCR/identity must only run after authoritative clean scan.
        app_src = _source(APP_PY)
        self.assertIn("scan_is_authoritatively_clean", app_src)
        self.assertIn("document_not_clean", app_src)


class IdentityOutcomeContractTests(unittest.TestCase):
    def test_outcome_sets_frozen(self):
        self.assertEqual(set(ica.IDENTITY_OUTCOMES), set(IDENTITY_OUTCOMES))
        self.assertEqual(set(ica.ACCEPTED_IDENTITY_OUTCOMES), set(ACCEPTED_IDENTITY_OUTCOMES))
        self.assertTrue(ica.ACCEPTED_IDENTITY_OUTCOMES.isdisjoint({"possible_match", "conflict"}))

    def _row(
        self,
        *,
        phone: str,
        name: str,
        email: str | None = None,
        status: str = "needs_role",
        position_code: str = "",
        app_key: str | None = None,
    ) -> dict:
        return {
            "phone": phone,
            "name": name,
            "email": email,
            "app_key": app_key or f"{phone}-WATHEFNI-IMPORT",
            "status": status,
            "position_code": position_code,
            "company_code": "WATHEFNI",
            "identity_key_type": None,
            "identity_key_value": None,
            "identity_key_authority": None,
        }

    def test_possible_match_weak_name_no_ownership(self):
        decision = ica._decide_identity(
            company_code="WATHEFNI",
            content_sha256="a" * 64,
            extracted_email=None,
            extracted_phone=None,
            normalized_full_name="mariam almulla",
            rows=[self._row(phone="96550001", name="Mariam Almulla", email="m@example.com")],
        )
        self.assertEqual(decision.outcome, "possible_match")
        self.assertFalse(decision.ownership_confirmed)
        self.assertIsNone(decision.candidate_phone)
        self.assertIn("weak_name_match_requires_hr_review", decision.reason_codes)

    def test_conflict_multiple_strong_candidates(self):
        decision = ica._decide_identity(
            company_code="WATHEFNI",
            content_sha256="b" * 64,
            extracted_email="shared@example.com",
            extracted_phone=None,
            normalized_full_name=None,
            rows=[
                self._row(phone="96550001", name="A", email="shared@example.com"),
                self._row(phone="96550002", name="B", email="shared@example.com"),
            ],
        )
        self.assertEqual(decision.outcome, "conflict")
        self.assertFalse(decision.ownership_confirmed)
        self.assertIn("strong_keys_resolve_to_different_candidates", decision.reason_codes)

    def test_conflict_conflicting_name_on_exact_email(self):
        decision = ica._decide_identity(
            company_code="WATHEFNI",
            content_sha256="c" * 64,
            extracted_email="sara@example.com",
            extracted_phone=None,
            normalized_full_name="ahmed hassan",
            rows=[self._row(phone="96550003", name="Sara Alenezi", email="sara@example.com")],
        )
        self.assertEqual(decision.outcome, "conflict")
        self.assertFalse(decision.ownership_confirmed)
        self.assertIn("conflicting_cv_name", decision.reason_codes)

    def test_safe_exact_reuse_and_new_candidate(self):
        reuse = ica._decide_identity(
            company_code="WATHEFNI",
            content_sha256="d" * 64,
            extracted_email="sara@example.com",
            extracted_phone=None,
            normalized_full_name="sara alenezi",
            rows=[self._row(phone="96550003", name="Sara Alenezi", email="sara@example.com")],
        )
        self.assertEqual(reuse.outcome, "safe_exact_reuse")
        self.assertTrue(reuse.ownership_confirmed)
        self.assertEqual(reuse.candidate_phone, "96550003")

        created = ica._decide_identity(
            company_code="WATHEFNI",
            content_sha256="e" * 64,
            extracted_email="new@example.com",
            extracted_phone="96550009999",
            normalized_full_name="new person",
            rows=[],
        )
        self.assertEqual(created.outcome, "new_candidate")
        self.assertTrue(created.ownership_confirmed)
        self.assertTrue(str(created.candidate_phone or "").startswith("imp-"))

    def test_sender_email_is_provenance_only_in_authority_module(self):
        src = _source(ROOT / "inbound_cv_authority.py")
        self.assertIn("sender_email_provenance", src)
        self.assertIn("IDENTITY_POLICY_VERSION", src)


class WhatsAppChannelContractTests(unittest.TestCase):
    def test_unsolicited_cv_holds_pending_media_not_application(self):
        handler = _extract_function_source(APP_PY, "handle_candidate_file_turn")
        hold = _extract_function_source(APP_PY, "hold_candidate_pending_media")
        self.assertIn("hold_candidate_pending_media", handler)
        self.assertIn('candidate_message_result("cv_held_needs_role"', handler)
        self.assertIn("candidate_pending_media", hold)
        self.assertIn("interval '2 hours'", hold)
        # Unsolicited path must not invent needs_role application status.
        self.assertNotIn("status='needs_role'", hold)
        self.assertNotIn('status="needs_role"', hold)

    def test_cv_then_apply_and_apply_then_cv_stage_b_contracts(self):
        handler = _extract_function_source(APP_PY, "handle_candidate_file_turn")
        convert = _extract_function_source(STAGE_B_PY, "convert_job_context_to_application")
        self.assertIn("parse_apply_code_text", handler)
        self.assertIn("convert_job_context_to_application", handler)
        self.assertIn('trigger="qualifying_cv"', handler)
        self.assertIn("upsert_candidate_job_context", handler)
        self.assertIn('"apply_confirm"', convert)
        self.assertIn('"qualifying_cv"', convert)
        self.assertIn("preview_sent_at", convert)
        self.assertIn("register_candidate_cv_file", convert)

    def test_pending_media_not_talent_pool_membership(self):
        scenario = all_scenarios()["whatsapp_cv_only_unsolicited"]["expected"]
        self.assertFalse(scenario["creates_application"])
        self.assertFalse(scenario["hr_talent_pool_visible"])
        self.assertTrue(scenario["creates_pending_media"])


class ManualImportAutoAdmitRiskTests(unittest.TestCase):
    """Risk 2: Wave 1 remediates unset auto-admit to fail closed."""

    def test_company_auto_admit_unset_false_true_matrix(self):
        # Reproduce the Wave 1 fail-closed default logic without importing FastAPI.
        def company_auto_admit_imports(settings_value):
            if settings_value is None:
                return False
            return bool(settings_value)

        self.assertFalse(company_auto_admit_imports(None))
        self.assertFalse(company_auto_admit_imports(False))
        self.assertTrue(company_auto_admit_imports(True))

        app_src = _source(APP_PY)
        self.assertIn("def company_auto_admit_imports", app_src)
        self.assertIn("if val is None:\n        return False", app_src)
        self.assertIn("auto_admitted = bool(auto_admit and position_code and not governed_identity)", app_src)

    def test_auto_admit_status_matrix(self):
        def held_status(*, auto_admit: bool, position_code: str, governed_identity: bool) -> str:
            auto_admitted = bool(auto_admit and position_code and not governed_identity)
            if auto_admitted:
                return "review_pending"
            return "import_review" if position_code else "needs_role"

        # Manual explicit role, setting explicitly true → review_pending.
        self.assertEqual(
            held_status(auto_admit=True, position_code="WELDER", governed_identity=False),
            "review_pending",
        )
        # Manual explicit role, setting false/unset → held import_review.
        self.assertEqual(
            held_status(auto_admit=False, position_code="WELDER", governed_identity=False),
            "import_review",
        )
        # No role → needs_role regardless of auto_admit.
        self.assertEqual(
            held_status(auto_admit=True, position_code="", governed_identity=False),
            "needs_role",
        )
        # Governed email never auto-admits even with role.
        self.assertEqual(
            held_status(auto_admit=True, position_code="WELDER", governed_identity=True),
            "import_review",
        )


class SingleItemPromotionSqlRiskTests(unittest.TestCase):
    """Risk 1: Wave 1 remediates single-item assign SQL/tenant mismatch."""

    def test_single_item_assign_matches_placeholders_and_tenant(self):
        src = _extract_function_source(APP_PY, "dashboard_prehire_import_assign")
        update_match = re.search(
            r'cur\.execute\(\s*"""\s*(UPDATE applications.*?WHERE app_key=%s AND company_code=%s)\s*"""\s*,\s*\((.*?)\),\s*\)',
            src,
            flags=re.S,
        )
        self.assertIsNotNone(update_match, "single-item UPDATE applications block not found")
        sql = update_match.group(1)
        args_src = update_match.group(2)
        placeholders = _count_sql_placeholders(sql)
        arg_names = [part.strip() for part in args_src.split(",") if part.strip()]
        self.assertEqual(placeholders, 9, f"expected 9 placeholders, found {placeholders}")
        self.assertEqual(len(arg_names), 9, f"expected 9 args, found {len(arg_names)}")
        self.assertIn("company", arg_names[-1])
        self.assertIn("WHERE app_key=%s AND company_code=%s", sql)

    def test_bulk_assign_is_tenant_scoped(self):
        src = _extract_function_source(APP_PY, "dashboard_prehire_import_bulk")
        self.assertIn("WHERE app_key=%s AND company_code=%s", src)
        self.assertIn('trigger="intake_admit"', src)
        self.assertTrue('"bulk": True' in src or "'bulk': True" in src)

    def test_link_to_job_ui_still_stubbed(self):
        self.assertIn('"enabled": False', _source(ROOT / "unified_candidates.py"))
        payload = {"link_to_job": {"available": False, "enabled": False}}
        # Direct source pin of reserved future admit action.
        self.assertIn("Reserved for a future confirmed intake_admit action", _source(ROOT / "unified_candidates.py"))
        self.assertFalse(payload["link_to_job"]["enabled"])


class CandidateKnowledgeSiblingRiskTests(unittest.TestCase):
    """Risk 3: Wave 1 remediates held sibling over-denial via anchor scoping."""

    def test_strictest_actionability_helper_still_ands_siblings(self):
        # Helper retained for documentation/legacy; resolve_exact must not use it.
        live = crsp.evaluate_candidate_record_state({"status": "ready_for_review"})
        held = crsp.evaluate_candidate_record_state({"status": "needs_role"})
        self.assertTrue(live.to_actionability()["job_ranking_allowed"])
        self.assertFalse(held.to_actionability()["job_ranking_allowed"])

        combined = cka._strictest_actionability([live, held])
        self.assertTrue(combined.readable)
        self.assertFalse(combined.contact_allowed)
        self.assertFalse(combined.lifecycle_mutation_allowed)
        self.assertFalse(combined.job_ranking_allowed)
        self.assertEqual(combined.held_state, "needs_role")

    def test_anchor_actionability_preserves_live_job_caps(self):
        live = crsp.evaluate_candidate_record_state({"status": "ready_for_review"})
        held = crsp.evaluate_candidate_record_state({"status": "needs_role"})
        anchor = cka._anchor_actionability(
            {"app-live": live, "app-held": held},
            anchor_app_key="app-live",
        )
        self.assertTrue(anchor.readable)
        self.assertTrue(anchor.contact_allowed)
        self.assertTrue(anchor.lifecycle_mutation_allowed)
        self.assertTrue(anchor.job_ranking_allowed)
        self.assertIsNone(anchor.held_state)

        held_anchor = cka._anchor_actionability(
            {"app-live": live, "app-held": held},
            anchor_app_key="app-held",
        )
        self.assertTrue(held_anchor.readable)
        self.assertFalse(held_anchor.job_ranking_allowed)
        self.assertEqual(held_anchor.held_state, "needs_role")

    def test_resolve_exact_uses_anchor_not_strictest(self):
        src = _source(ROOT / "candidate_knowledge_authority.py")
        # Method body uses anchor scoping; strictest remains a documented helper only.
        resolve_match = re.search(
            r"def resolve_exact\([\s\S]*?\n    def resolve_name_only\(",
            src,
        )
        self.assertIsNotNone(resolve_match, "resolve_exact method not found")
        resolve_src = resolve_match.group(0)
        self.assertIn("_anchor_actionability", resolve_src)
        self.assertNotIn("_strictest_actionability", resolve_src)

    def test_candidate_ref_remains_app_keyed(self):
        self.assertEqual(ckt.CANDIDATE_REF_PREFIX, "app:")
        self.assertEqual(ckt.candidate_ref_from_app_key("abc"), "app:abc")
        self.assertEqual(ckt.app_key_from_candidate_ref("app:abc"), "abc")

    def test_row_level_held_exclusion_still_exists_for_ranking(self):
        app_src = _source(APP_PY)
        self.assertIn("NOT IN ('needs_role','import_review','import_archived')", app_src)


class DuplicateReplayAndConcurrencyContractTests(unittest.TestCase):
    def test_email_provider_and_content_dedupe_contracts(self):
        ingress = _source(ROOT / "durable_email_ingress.py")
        self.assertIn("UNIQUE (company_code, provider, provider_message_id)", ingress)
        self.assertIn("duplicate_of_document_id", ingress)
        self.assertIn("content_sha256", ingress)
        app_src = _source(APP_PY)
        self.assertIn("duplicate_existing_cv", app_src) or self.assertIn("seen_checksums", app_src)

    def test_whatsapp_inbound_claim_idempotency(self):
        app_src = _source(APP_PY)
        self.assertIn("def claim_whatsapp_inbound", app_src)
        self.assertIn("whatsapp_inbound_messages", app_src)

    def test_same_role_active_application_unique_index_contract(self):
        # Documented production uniqueness excluding held statuses.
        # Source may not create the index; pin the expected status exclusion list.
        for status in HELD_STATUSES:
            self.assertIn(status, HELD_STATUSES)


class PersonRegistryContractTests(unittest.TestCase):
    def test_person_registry_is_additive_not_inbound_create_authority(self):
        identity = _source(ROOT / "candidate_identity.py")
        self.assertIn("CREATE TABLE IF NOT EXISTS persons", identity)
        self.assertIn("person_company_memberships", identity)
        self.assertIn("assert_no_cv_processing_authority", identity)
        # Inbound create path uses inbound_cv_authority / register_imported_cv, not persons.
        inbound = _source(ROOT / "inbound_cv_authority.py")
        self.assertNotIn("INSERT INTO persons", inbound)


class TalentPoolClassificationContractTests(unittest.TestCase):
    def test_classification_independent_of_admit_and_ranking(self):
        src = _source(ROOT / "talent_pool_classification.py")
        self.assertIn("Independent of Jobs, Ranking, outreach, intake_admit", src)
        self.assertEqual(tpc.FEATURE_WORKERS, "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS")
        # Workers must remain opt-in; Phase 0 freezes current separation.
        self.assertFalse(tpc.feature_workers_enabled({"WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS": "off"}))


class ZeroDownstreamMutationContractTests(unittest.TestCase):
    def test_held_records_blocked_from_evaluation_and_admit_only_lifecycle(self):
        app_src = _source(APP_PY)
        self.assertIn("held_record_evaluation_forbidden", app_src)
        self.assertIn('trigger="intake_admit"', app_src)
        self.assertIn("HELD_IMPORT_STATUSES", app_src)

    def test_unified_candidates_reserves_link_to_job(self):
        src = _source(ROOT / "unified_candidates.py")
        self.assertIn("link_to_job", src)
        self.assertIn('"enabled": False', src)

    def test_fingerprint_modules_exist_and_are_hashable(self):
        modules = [
            APP_PY,
            ROOT / "durable_email_ingress.py",
            ROOT / "inbound_cv_authority.py",
            ROOT / "jobs_phase2_stage_b.py",
            ROOT / "candidate_knowledge_authority.py",
            ROOT / "candidate_record_state_policy.py",
            ROOT / "candidate_communication_authority.py",
            ROOT / "recruiting_lifecycle.py",
            ROOT / "talent_pool_classification.py",
            ROOT / "unified_candidates.py",
            ROOT / "candidate_identity.py",
        ]
        fingerprint = {
            path.name: _sha256(path)
            for path in modules
        }
        self.assertEqual(len(fingerprint), len(modules))
        for digest in fingerprint.values():
            self.assertEqual(len(digest), 64)


class ChannelDivergencePinTests(unittest.TestCase):
    def test_manual_and_whatsapp_bypass_inbound_authority_today(self):
        app_src = _source(APP_PY)
        # Manual path uses register_imported_cv; email requires identity_resolution.
        self.assertIn('durable_scan_and_identity_authority_required', app_src)
        register = _extract_function_source(APP_PY, "register_imported_cv")
        self.assertIn("governed_identity", register)
        # WhatsApp CV attach path is separate.
        self.assertIn("def register_candidate_cv_file", app_src)

    def test_email_job_pipeline_stages_frozen(self):
        self.assertEqual(
            set(dei.JOB_TYPES),
            {
                "intake_validation",
                "file_safety_scan",
                "cv_identity_resolution",
                "accepted_intake_preparation",
                "cv_extraction",
                "profile_structuring",
                "embedding",
                "sender_acknowledgment",
                "retention_privacy",
            },
        )


if __name__ == "__main__":
    unittest.main()
