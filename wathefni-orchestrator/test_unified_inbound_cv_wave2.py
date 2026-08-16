"""Wave 2 shared security / CV-processing authority tests.

Covers stage catalog, kill switches, retries/dead letters, cv_version dual-write,
extraction provider planning, safety case matrix, and staging-style envelope
parity with zero-duplicate proof.

Does not cut over WhatsApp/manual. Does not enable production dual-write.
"""

from __future__ import annotations

import ast
import hashlib
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

import durable_email_ingress as dei
import inbound_cv_intake as ici
import inbound_cv_processing as icp


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"
WAVE2_VERSION = "unified-inbound-cv-wave2-v1"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ingress_config() -> dei.IngressConfig:
    return dei.IngressConfig(
        quarantine_root=Path(tempfile.gettempdir()) / "wathefni-wave2-quarantine",
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


def _png_1x1() -> bytes:
    # Minimal valid 1x1 PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []
        self._fetch: dict[str, Any] | None = None
        self.cv_versions: list[dict[str, Any]] = []
        self.stage_runs: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        params_t = tuple(params) if params is not None else None
        self.statements.append((sql, params_t))
        text = " ".join(sql.split())
        if text.startswith("CREATE TABLE") or text.startswith("ALTER TABLE") or "CREATE INDEX" in text:
            self._fetch = None
            return
        if "INSERT INTO cv_versions" in text:
            row = {
                "cv_version_id": str(params_t[0]),
                "company_code": params_t[1],
                "content_sha256": params_t[2],
                "legacy_document_id": params_t[8],
                "legacy_app_key": params_t[7],
            }
            existing = next(
                (
                    item
                    for item in self.cv_versions
                    if item["content_sha256"] == row["content_sha256"]
                    and item["legacy_document_id"] == row["legacy_document_id"]
                    and item["company_code"] == row["company_code"]
                ),
                None,
            )
            if existing is None:
                self.cv_versions.append(row)
            else:
                row = existing
            self._fetch = {"cv_version_id": row["cv_version_id"]}
            return
        if "INSERT INTO cv_processing_stage_runs" in text:
            row = {
                "run_id": str(params_t[0]),
                "company_code": params_t[1],
                "stage": params_t[2],
                "status": params_t[4],
                "idempotency_key": params_t[7],
            }
            existing = next(
                (
                    item
                    for item in self.stage_runs
                    if item["idempotency_key"] == row["idempotency_key"]
                    and item["company_code"] == row["company_code"]
                ),
                None,
            )
            if existing is None:
                self.stage_runs.append(row)
            else:
                existing["status"] = row["status"]
                row = existing
            self._fetch = {"run_id": row["run_id"], "status": row["status"]}
            return
        if "UPDATE candidate_cv_text_versions" in text or "UPDATE application_cv_" in text:
            self._fetch = None
            return
        self._fetch = None

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetch


class StageCatalogAndKillSwitchTests(unittest.TestCase):
    def test_shared_stages_cover_required_pipeline(self):
        required = {
            "document_acceptance",
            "mime_content_validation",
            "malware_scan",
            "local_extraction",
            "mistral_ocr",
            "gpt_vision_rescue",
            "structured_facts",
            "immutable_cv_version",
            "classification",
            "candidate_knowledge_indexing",
        }
        self.assertEqual(set(icp.STAGES), required)
        for stage in icp.STAGES:
            self.assertTrue(icp.STAGE_VERSIONS[stage].startswith(icp.PROCESSING_VERSION))

    def test_feature_flags_default_off(self):
        self.assertFalse(icp.processing_feature_enabled({}))
        self.assertFalse(icp.cv_version_dual_write_enabled({}))
        self.assertFalse(icp.stage_ledger_enabled({}))
        self.assertFalse(icp.envelope_dual_write_enabled({}))

    def test_kill_switches_independent(self):
        env = {
            "WATHEFNI_UNIFIED_STAGE_KILL_MALWARE_SCAN": "1",
            "WATHEFNI_CV_MISTRAL_OCR": "0",
            "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS": "off",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS": "off",
        }
        self.assertTrue(icp.stage_killed("malware_scan", env))
        self.assertTrue(icp.stage_killed("mistral_ocr", env))
        self.assertTrue(icp.stage_killed("classification", env))
        self.assertTrue(icp.stage_killed("candidate_knowledge_indexing", env))
        self.assertFalse(icp.stage_killed("local_extraction", env))

    def test_retry_then_dead_letter(self):
        self.assertEqual(icp.mark_stage_retry_or_dead_letter(attempt=1, max_attempts=5, error_code="x"), "retrying")
        self.assertEqual(icp.mark_stage_retry_or_dead_letter(attempt=5, max_attempts=5, error_code="x"), "dead_letter")


class CvVersionDualWriteTests(unittest.TestCase):
    def test_dual_write_skipped_when_flag_off(self):
        cur = RecordingCursor()
        result = icp.dual_write_cv_version(
            cur,
            company_code="WATHEFNI",
            content_sha256="abc",
            legacy_document_id="doc-1",
            environ={},
        )
        self.assertTrue(result["skipped"])
        self.assertEqual(cur.cv_versions, [])

    def test_dual_write_idempotent_stable_id(self):
        cur = RecordingCursor()
        env = {
            "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE": "1",
            "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1",
        }
        first = icp.dual_write_cv_version(
            cur,
            company_code="WATHEFNI",
            content_sha256="deadbeef",
            legacy_document_id="doc-1",
            legacy_app_key="app-1",
            extracted_text_hash="t1",
            extraction_method="pdftotext",
            evidence_id=str(uuid.uuid4()),
            facts_id=str(uuid.uuid4()),
            environ=env,
        )
        second = icp.dual_write_cv_version(
            cur,
            company_code="WATHEFNI",
            content_sha256="deadbeef",
            legacy_document_id="doc-1",
            legacy_app_key="app-1",
            environ=env,
        )
        self.assertFalse(first["skipped"])
        self.assertEqual(first["cv_version_id"], second["cv_version_id"])
        self.assertFalse(first["reader_cutover"])
        self.assertEqual(len(cur.cv_versions), 1)
        expected = icp.stable_cv_version_id(
            company_code="WATHEFNI",
            content_sha256="deadbeef",
            legacy_document_id="doc-1",
        )
        self.assertEqual(first["cv_version_id"], expected)

    def test_app_readers_not_cut_over_in_source(self):
        processing = _source(ROOT / "inbound_cv_processing.py")
        self.assertIn('"reader_cutover": False', processing)
        self.assertIn("Does not cut over app_key readers", processing)
        app_src = _source(APP_PY)
        self.assertIn("unified_cv_version_dual_write", app_src)
        self.assertIn("inbound_cv_processing", app_src)


class ExtractionProviderPlanTests(unittest.TestCase):
    def test_digital_pdf_local_only(self):
        plan = icp.plan_extraction_providers(
            mime_or_suffix="application/pdf",
            local_text_ok=True,
            needs_ocr=False,
            environ={"WATHEFNI_CV_MISTRAL_OCR": "1"},
        )
        self.assertTrue(plan.local_first)
        self.assertFalse(plan.mistral_ocr_eligible)
        self.assertFalse(plan.gpt_vision_rescue_eligible)

    def test_scanned_pdf_mistral_then_rescue(self):
        plan = icp.plan_extraction_providers(
            mime_or_suffix="application/pdf",
            local_text_ok=False,
            needs_ocr=True,
            environ={"WATHEFNI_CV_MISTRAL_OCR": "1", "WATHEFNI_CV_GPT_VISION_RESCUE": "1"},
        )
        self.assertTrue(plan.mistral_ocr_eligible)
        self.assertFalse(plan.gpt_vision_rescue_eligible)  # CV GPT rescue retired

    def test_scanned_pdf_ocr_kill_switch(self):
        plan = icp.plan_extraction_providers(
            mime_or_suffix="application/pdf",
            local_text_ok=False,
            needs_ocr=True,
            environ={"WATHEFNI_CV_MISTRAL_OCR": "0"},
        )
        self.assertFalse(plan.mistral_ocr_eligible)
        self.assertIn("mistral_ocr_disabled", plan.reason_codes)

    def test_image_cv_ocr_path(self):
        plan = icp.plan_extraction_providers(
            mime_or_suffix="image/png",
            local_text_ok=False,
            needs_ocr=True,
            environ={"WATHEFNI_CV_MISTRAL_OCR": "1"},
        )
        self.assertTrue(plan.mistral_ocr_eligible)

    def test_docx_local_xml_primary(self):
        plan = icp.plan_extraction_providers(
            mime_or_suffix=".docx",
            local_text_ok=True,
            needs_ocr=False,
            environ={"WATHEFNI_CV_MISTRAL_OCR": "1"},
        )
        self.assertTrue(plan.local_first)
        self.assertFalse(plan.mistral_ocr_eligible)
        self.assertIn("docx_local_xml_primary", plan.reason_codes)

    def test_arabic_english_do_not_force_ocr_when_local_ok(self):
        # Arabic/English/bilingual digital text stays local; OCR only when pages need it.
        for label in ("arabic", "english", "bilingual"):
            plan = icp.plan_extraction_providers(
                mime_or_suffix="application/pdf",
                local_text_ok=True,
                needs_ocr=False,
                environ={"WATHEFNI_CV_MISTRAL_OCR": "1"},
            )
            self.assertFalse(plan.mistral_ocr_eligible, label)


class SafetyCaseMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _ingress_config()

    def test_clean_pdf(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(),
            original_filename="cv.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=self.config,
        )
        self.assertEqual(state, "clean")
        self.assertIsNone(reason)

    def test_password_protected_pdf(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(encrypt=True),
            original_filename="cv.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=self.config,
        )
        self.assertEqual(state, "password_protected")
        self.assertEqual(reason, "pdf_encrypted")

    def test_corrupt_pdf_missing_eof(self):
        state, reason, _ = dei.inspect_document_safety(
            data=_minimal_pdf(eof=False),
            original_filename="cv.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=self.config,
        )
        self.assertEqual(state, "invalid_corrupt")
        self.assertEqual(reason, "pdf_eof_missing")

    def test_unsupported_extension(self):
        state, reason, _ = dei.inspect_document_safety(
            data=b"hello",
            original_filename="cv.doc",
            claimed_mime="application/msword",
            detected_mime="application/msword",
            config=self.config,
        )
        self.assertEqual(state, "unsupported_type")

    def test_image_png_clean(self):
        state, reason, meta = dei.inspect_document_safety(
            data=_png_1x1(),
            original_filename="cv.png",
            claimed_mime="image/png",
            detected_mime="image/png",
            config=self.config,
        )
        self.assertEqual(state, "clean")
        self.assertIsNone(reason)
        self.assertEqual(meta.get("image_width"), 1)

    def test_malware_fail_closed_contract(self):
        # Scanner unavailable / malware must not proceed to OCR on email path.
        ingress = _source(ROOT / "durable_email_ingress.py")
        self.assertIn("malware_suspicious", ingress)
        self.assertIn("scanner_unavailable", ingress)
        self.assertIn("scan_pending", ingress)
        authority = _source(ROOT / "inbound_cv_authority.py")
        self.assertIn("begin_scan", authority)
        self.assertIn("complete_scan", authority)


class StagingEnvelopeParityTests(unittest.TestCase):
    def test_staging_dual_write_one_exact_mapping_zero_duplicates(self):
        # Simulate staging-only envelope dual-write using Wave 1 helper + Wave 2 proof.
        class EnvCursor:
            def __init__(self) -> None:
                self.tables = {
                    "intake_source_events": [],
                    "intake_subjects": [],
                    "intake_items": [],
                    "intake_item_documents": [],
                }
                self._fetch = None
                self.statements = []

            def execute(self, sql, params=None):
                self.statements.append((sql, params))
                text = " ".join(sql.split())
                if "INSERT INTO intake_source_events" in text:
                    event_id = str(params[0])
                    if not self.tables["intake_source_events"]:
                        self.tables["intake_source_events"].append({"event_id": event_id})
                    self._fetch = {"event_id": event_id}
                    return
                if "INSERT INTO intake_subjects" in text:
                    sid = str(params[0])
                    if not any(r["subject_id"] == sid for r in self.tables["intake_subjects"]):
                        self.tables["intake_subjects"].append({"subject_id": sid})
                    return
                if "INSERT INTO intake_items" in text:
                    iid = str(params[0])
                    if not any(r["item_id"] == iid for r in self.tables["intake_items"]):
                        self.tables["intake_items"].append({"item_id": iid})
                    self._fetch = {"item_id": iid}
                    return
                if "INSERT INTO intake_item_documents" in text:
                    key = (params[0], str(params[1]), str(params[2]))
                    if not any(
                        (r["company_code"], r["item_id"], r["document_id"]) == key
                        for r in self.tables["intake_item_documents"]
                    ):
                        self.tables["intake_item_documents"].append(
                            {
                                "company_code": params[0],
                                "item_id": str(params[1]),
                                "document_id": str(params[2]),
                                "content_sha256": params[5],
                            }
                        )
                    return
                self._fetch = None

            def fetchone(self):
                return self._fetch

        cursor = EnvCursor()
        env = {"WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1"}
        inbound_id = str(uuid.uuid4())
        submission_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        digest = hashlib.sha256(b"%PDF-1.4 staging").hexdigest()
        docs = [
            {
                "document_id": document_id,
                "ordinal": 1,
                "filename": "cv.pdf",
                "storage_status": "stored",
                "safety_state": "scan_pending",
                "content_sha256": digest,
            }
        ]
        first = ici.dual_write_email_receipt(
            cursor,
            company_code="WATHEFNI",
            inbound_id=inbound_id,
            submission_id=submission_id,
            provider="postmark",
            provider_message_id="staging-msg-1",
            route_snapshot={"intake_id": "route-1", "company_code": "WATHEFNI"},
            source_provenance={"channel": "email_inbound", "provider": "postmark"},
            documents=docs,
            environ=env,
        )
        second = ici.dual_write_email_receipt(
            cursor,
            company_code="WATHEFNI",
            inbound_id=inbound_id,
            submission_id=submission_id,
            provider="postmark",
            provider_message_id="staging-msg-1",
            route_snapshot={"intake_id": "route-1", "company_code": "WATHEFNI"},
            source_provenance={"channel": "email_inbound", "provider": "postmark"},
            documents=docs,
            environ=env,
        )
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(len(cursor.tables["intake_source_events"]), 1)
        self.assertEqual(len(cursor.tables["intake_item_documents"]), 1)
        self.assertEqual(cursor.tables["intake_item_documents"][0]["content_sha256"], digest)

        proof = icp.parity_zero_duplicate_proof(
            {
                "live_submissions": 1,
                "envelope_events": 1,
                "live_documents": 1,
                "envelope_document_links": 1,
                "candidate_creates": 0,
                "application_creates": 0,
                "ocr_provider_calls": 0,
                "classification_writes": 0,
                "ck_writes": 0,
                "duplicate_candidate_creates": 0,
                "duplicate_application_creates": 0,
                "duplicate_ocr_writes": 0,
                "duplicate_classification_writes": 0,
                "duplicate_ck_writes": 0,
            }
        )
        self.assertTrue(proof["ok"], proof["errors"])

    def test_parity_fails_on_duplicate_candidate_create(self):
        proof = icp.parity_zero_duplicate_proof(
            {
                "live_submissions": 1,
                "envelope_events": 1,
                "live_documents": 1,
                "envelope_document_links": 1,
                "duplicate_candidate_creates": 1,
            }
        )
        self.assertFalse(proof["ok"])
        self.assertIn("duplicate_candidate_creates", proof["errors"])


class EmailPathAuthoritativeTests(unittest.TestCase):
    def test_email_wrappers_remain_dispatch_authority(self):
        app_src = _source(APP_PY)
        self.assertIn("def process_durable_email_ingress_job", app_src)
        self.assertIn("_durable_email_ingress.validate_submission", app_src)
        self.assertIn("_durable_email_ingress.scan_document", app_src)
        self.assertIn("process_candidate_cv_document", app_src)
        self.assertIn("observe_email_job_stage", app_src)
        # Observation must not replace handlers.
        self.assertIn("authoritative_path", _source(ROOT / "inbound_cv_processing.py"))

    def test_whatsapp_manual_not_cut_over(self):
        processing = _source(ROOT / "inbound_cv_processing.py")
        self.assertIn("does not cut over whatsapp or manual upload", processing.lower())
        self.assertNotIn("dual_write_whatsapp", processing)
        self.assertNotIn("dual_write_manual", processing)
        app_src = _source(APP_PY)
        self.assertIn("def hold_candidate_pending_media", app_src)
        self.assertIn("def register_imported_cv", app_src)

    def test_processing_module_has_no_candidate_create_authority(self):
        tree = ast.parse(_source(ROOT / "inbound_cv_processing.py"))
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        forbidden = {
            "register_imported_cv",
            "register_candidate_cv_file",
            "hold_candidate_pending_media",
        }
        self.assertTrue(forbidden.isdisjoint(names))
        src = _source(ROOT / "inbound_cv_processing.py")
        self.assertNotIn("INSERT INTO candidates", src)
        self.assertNotIn("INSERT INTO applications", src)


class StageLedgerIdempotencyTests(unittest.TestCase):
    def test_stage_run_idempotent(self):
        cur = RecordingCursor()
        env = {"WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1"}
        a = icp.record_stage_run(
            cur,
            company_code="WATHEFNI",
            stage="malware_scan",
            status="completed",
            subject_id="doc-1",
            content_sha256="abc",
            environ=env,
        )
        b = icp.record_stage_run(
            cur,
            company_code="WATHEFNI",
            stage="malware_scan",
            status="completed",
            subject_id="doc-1",
            content_sha256="abc",
            environ=env,
        )
        self.assertEqual(a["run_id"], b["run_id"])
        self.assertEqual(len(cur.stage_runs), 1)


class Wave2FingerprintTests(unittest.TestCase):
    def test_modules_hashable(self):
        for path in (
            ROOT / "inbound_cv_processing.py",
            ROOT / "inbound_cv_intake.py",
            ROOT / "durable_email_ingress.py",
            APP_PY,
        ):
            self.assertEqual(len(_sha256(path)), 64)
        self.assertEqual(WAVE2_VERSION, "unified-inbound-cv-wave2-v1")
        self.assertEqual(icp.PROCESSING_VERSION, "unified-inbound-cv-processing-v1")


if __name__ == "__main__":
    unittest.main()
