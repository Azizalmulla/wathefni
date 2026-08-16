"""Wave 3 adapter + scenario contract tests (offline)."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

import durable_email_ingress as dei
import inbound_cv_adapters as adapters
import inbound_cv_intake as ici
import inbound_cv_processing as icp


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ingress_config() -> dei.IngressConfig:
    return dei.IngressConfig(
        quarantine_root=Path(tempfile.gettempdir()) / "wathefni-wave3-quarantine",
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


class EnvCursor:
    def __init__(self) -> None:
        self.tables = {
            "intake_source_events": [],
            "intake_subjects": [],
            "intake_items": [],
            "intake_item_documents": [],
            "cv_versions": [],
            "cv_processing_stage_runs": [],
        }
        self._fetch = None
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        text = " ".join(sql.split())
        if text.startswith("CREATE TABLE") or text.startswith("ALTER TABLE") or "CREATE INDEX" in text:
            self._fetch = None
            return
        if "INSERT INTO intake_source_events" in text:
            event_id = str(params[0])
            company = params[1]
            channel = params[2]
            external = params[5]
            existing = next(
                (
                    r
                    for r in self.tables["intake_source_events"]
                    if r.get("external_event_id") == external
                    and r.get("channel") == channel
                    and r.get("company_code") == company
                ),
                None,
            )
            if existing is None:
                self.tables["intake_source_events"].append(
                    {
                        "event_id": event_id,
                        "company_code": company,
                        "channel": channel,
                        "external_event_id": external,
                    }
                )
            else:
                event_id = existing["event_id"]
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
                meta = params[9] if len(params) > 9 else {}
                self.tables["intake_items"].append({"item_id": iid, "metadata": meta})
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
        if "INSERT INTO cv_processing_stage_runs" in text:
            run_id = str(params[0])
            idem = params[7]
            if not any(r["idempotency_key"] == idem for r in self.tables["cv_processing_stage_runs"]):
                self.tables["cv_processing_stage_runs"].append(
                    {"run_id": run_id, "idempotency_key": idem, "stage": params[2], "status": params[4]}
                )
            self._fetch = {"run_id": run_id, "status": params[4]}
            return
        if "INSERT INTO cv_versions" in text:
            cv_id = str(params[0])
            if not any(r["cv_version_id"] == cv_id for r in self.tables["cv_versions"]):
                self.tables["cv_versions"].append({"cv_version_id": cv_id})
            self._fetch = {"cv_version_id": cv_id}
            return
        self._fetch = None

    def fetchone(self):
        return self._fetch


STAGING_ENV = {
    "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1",
    "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS": "1",
    "WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING": "1",
    "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1",
    "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE": "1",
    "WATHEFNI_CV_MISTRAL_OCR": "1",
    "WATHEFNI_CV_GPT_VISION_RESCUE": "1",
}


class AdapterContractTests(unittest.TestCase):
    def test_flags_default_off(self):
        self.assertFalse(adapters.adapters_enabled({}))
        self.assertFalse(adapters.shared_processing_enabled({}))

    def test_job_gate_blocks_unconfirmed_application(self):
        denied = adapters.assert_no_job_without_exact_confirmation(
            job_selected=False, human_confirmed=False, create_application=True
        )
        self.assertFalse(denied["allowed"])
        allowed = adapters.assert_no_job_without_exact_confirmation(
            job_selected=True, human_confirmed=True, create_application=True
        )
        self.assertTrue(allowed["allowed"])

    def test_manual_held_by_default(self):
        held = adapters.manual_held_by_default(auto_admit_enabled=False, explicit_role=True)
        self.assertTrue(held["held_by_default"])
        self.assertEqual(held["status"], "import_review")
        unset = adapters.manual_held_by_default(auto_admit_enabled=False, explicit_role=False)
        self.assertEqual(unset["status"], "needs_role")

    def test_unsolicited_talent_pool_non_actionable(self):
        vis = adapters.talent_pool_visibility_for_unsolicited()
        self.assertTrue(vis["hr_visible"])
        self.assertFalse(vis["actionable"])
        self.assertFalse(vis["job_ranking_allowed"])
        self.assertTrue(vis["requires_exact_job_confirmation"])


class AdapterDualWriteScenarioTests(unittest.TestCase):
    def test_cv_only_unsolicited_whatsapp(self):
        cur = EnvCursor()
        result = adapters.adapt_whatsapp_unsolicited(
            cur,
            company_code="WATHEFNI",
            provider_message_id="wa-msg-cv-only",
            phone="96550001111",
            account_id="acct-1",
            conversation_id="conv-1",
            pending_id=str(uuid.uuid4()),
            content_sha256="abc",
            filename="cv.pdf",
            needs_ocr=True,
            environ=STAGING_ENV,
        )
        self.assertFalse(result["creates_job_application"])
        self.assertTrue(result["talent_pool"]["hr_visible"])
        self.assertFalse(result["talent_pool"]["actionable"])
        self.assertEqual(len(cur.tables["intake_source_events"]), 1)
        # replay protection
        adapters.adapt_whatsapp_unsolicited(
            cur,
            company_code="WATHEFNI",
            provider_message_id="wa-msg-cv-only",
            phone="96550001111",
            account_id="acct-1",
            conversation_id="conv-1",
            pending_id=str(uuid.uuid4()),
            environ=STAGING_ENV,
        )
        self.assertEqual(len(cur.tables["intake_source_events"]), 1)

    def test_cv_then_apply_and_apply_then_cv_job_adapter(self):
        cur = EnvCursor()
        for msg_id, label in (("wa-cv-then-apply", "cv_then_apply"), ("wa-apply-then-cv", "apply_then_cv")):
            result = adapters.adapt_whatsapp_job(
                cur,
                company_code="WATHEFNI",
                provider_message_id=msg_id,
                phone="96550002222",
                account_id="acct-1",
                conversation_id="conv-2",
                document_id=str(uuid.uuid4()),
                content_sha256=hashlib.sha256(label.encode()).hexdigest(),
                app_key=f"app-{label}",
                apply_code="WELDER",
                human_confirmed=True,
                environ=STAGING_ENV,
            )
            self.assertFalse(result["creates_job_application"])
            self.assertTrue(result["links_existing_application"])
        self.assertEqual(len(cur.tables["intake_source_events"]), 2)

    def test_role_name_with_cv_manual_held(self):
        cur = EnvCursor()
        result = adapters.adapt_manual_import(
            cur,
            company_code="WATHEFNI",
            batch_id=str(uuid.uuid4()),
            content_sha256="deadbeef",
            filename="Ali_Welder.pdf",
            document_id=str(uuid.uuid4()),
            app_key="app-manual-1",
            held_status="import_review",
            mime_or_suffix=".pdf",
            environ=STAGING_ENV,
        )
        self.assertTrue(result["held_by_default"])
        self.assertFalse(result["creates_job_application"])

    def test_multiple_replacement_cvs_distinct_events(self):
        cur = EnvCursor()
        batch = str(uuid.uuid4())
        for i, sha in enumerate(("sha1", "sha2"), start=1):
            adapters.adapt_manual_import(
                cur,
                company_code="WATHEFNI",
                batch_id=batch,
                content_sha256=sha,
                filename=f"cv{i}.pdf",
                document_id=str(uuid.uuid4()),
                app_key=f"app-{i}",
                held_status="needs_role",
                environ=STAGING_ENV,
            )
        self.assertEqual(len(cur.tables["intake_source_events"]), 2)

    def test_cross_tenant_isolation_separate_events(self):
        cur = EnvCursor()
        for company in ("WATHEFNI", "OTHERCO"):
            adapters.adapt_whatsapp_unsolicited(
                cur,
                company_code=company,
                provider_message_id="shared-provider-msg",
                phone="96550003333",
                account_id="acct",
                conversation_id="conv",
                pending_id=str(uuid.uuid4()),
                environ=STAGING_ENV,
            )
        # Same provider message id but different company => separate events
        self.assertEqual(len(cur.tables["intake_source_events"]), 2)


class SafetyAndProviderMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _ingress_config()

    def test_image_scanned_docx_provider_plans(self):
        image = icp.plan_extraction_providers(
            mime_or_suffix="image/png", local_text_ok=False, needs_ocr=True, environ=STAGING_ENV
        )
        scanned = icp.plan_extraction_providers(
            mime_or_suffix="application/pdf", local_text_ok=False, needs_ocr=True, environ=STAGING_ENV
        )
        docx = icp.plan_extraction_providers(
            mime_or_suffix=".docx", local_text_ok=True, needs_ocr=False, environ=STAGING_ENV
        )
        self.assertTrue(image.mistral_ocr_eligible)
        self.assertTrue(scanned.mistral_ocr_eligible and not scanned.gpt_vision_rescue_eligible)
        self.assertFalse(docx.mistral_ocr_eligible)

    def test_corrupt_password_unsupported(self):
        corrupt, _, _ = dei.inspect_document_safety(
            data=_minimal_pdf(eof=False),
            original_filename="cv.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=self.config,
        )
        password, _, _ = dei.inspect_document_safety(
            data=_minimal_pdf(encrypt=True),
            original_filename="cv.pdf",
            claimed_mime="application/pdf",
            detected_mime="application/pdf",
            config=self.config,
        )
        unsupported, _, _ = dei.inspect_document_safety(
            data=b"x",
            original_filename="cv.doc",
            claimed_mime="application/msword",
            detected_mime="application/msword",
            config=self.config,
        )
        self.assertEqual(corrupt, "invalid_corrupt")
        self.assertEqual(password, "password_protected")
        self.assertEqual(unsupported, "unsupported_type")


class ZeroDownstreamMutationTests(unittest.TestCase):
    def test_adapters_do_not_create_jobs(self):
        src = _source(ROOT / "inbound_cv_adapters.py")
        self.assertIn("creates_job_application", src)
        self.assertIn("exact_job_confirmation_required", src)
        self.assertNotIn("INSERT INTO applications", src)
        self.assertNotIn("INSERT INTO candidates", src)

    def test_live_paths_remain_authoritative(self):
        app_src = _source(APP_PY)
        self.assertIn("adapt_manual_import", app_src)
        self.assertIn("adapt_whatsapp_unsolicited", app_src)
        self.assertIn("adapt_whatsapp_job", app_src)
        self.assertIn("def register_imported_cv", app_src)
        self.assertIn("def hold_candidate_pending_media", app_src)
        self.assertIn("def register_candidate_cv_file", app_src)
        self.assertIn("def process_durable_email_ingress_job", app_src)

    def test_zero_duplicate_proof_still_holds(self):
        proof = icp.parity_zero_duplicate_proof(
            {
                "live_submissions": 1,
                "envelope_events": 1,
                "live_documents": 1,
                "envelope_document_links": 1,
                "candidate_creates": 0,
                "application_creates": 0,
            }
        )
        self.assertTrue(proof["ok"])


if __name__ == "__main__":
    unittest.main()
