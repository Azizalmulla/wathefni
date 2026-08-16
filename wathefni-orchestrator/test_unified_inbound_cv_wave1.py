"""Wave 1 Unified Inbound CV Pipeline tests.

Covers:
- channel-neutral intake envelope schema/IDs
- production-dark email dual-write (flag default OFF; live path authoritative)
- three Phase 0 defect remediations
- no duplicate submission/candidate/application/OCR/classification/CK writes
  from the envelope module itself

Does not cut over WhatsApp or manual upload. Does not start Wave 2.
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

import candidate_knowledge_authority as cka
import candidate_record_state_policy as crsp
import durable_email_ingress as dei
import inbound_cv_intake as ici
from candidate_knowledge_authority import (
    CandidateKnowledgeAuthority,
    InMemoryCandidateKnowledgeStore,
    build_request_context,
)
from fixtures.unified_inbound_cv_phase0 import THREE_CURRENT_RISKS


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"
WAVE1_VERSION = "unified-inbound-cv-wave1-v1"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _count_sql_placeholders(sql: str) -> int:
    return len(re.findall(r"%s", sql))


def _extract_function_source(path: Path, name: str) -> str:
    tree = ast.parse(_source(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(_source(path), node) or ""
    raise AssertionError(f"function {name} not found in {path.name}")


class RecordingCursor:
    """Minimal cursor stub that records SQL and supports dual-write inserts."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []
        self._fetch: dict[str, Any] | None = None
        self.tables: dict[str, list[dict[str, Any]]] = {
            "intake_source_events": [],
            "intake_subjects": [],
            "intake_items": [],
            "intake_item_documents": [],
            "intake_submissions": [],
            "intake_documents": [],
        }

    def execute(self, sql: str, params: Any = None) -> None:
        params_t = tuple(params) if params is not None else None
        self.statements.append((sql, params_t))
        text = " ".join(sql.split())
        if "INSERT INTO intake_source_events" in text:
            row = {
                "event_id": str(params_t[0]),
                "company_code": params_t[1],
                "provider": params_t[2],
                "external_event_id": params_t[3],
                "legacy_inbound_id": str(params_t[6]),
                "legacy_submission_id": str(params_t[7]),
            }
            existing = next(
                (
                    item
                    for item in self.tables["intake_source_events"]
                    if item["external_event_id"] == row["external_event_id"]
                    and item["company_code"] == row["company_code"]
                ),
                None,
            )
            if existing is None:
                self.tables["intake_source_events"].append(row)
            self._fetch = {"event_id": row["event_id"]}
            return
        if "INSERT INTO intake_subjects" in text:
            row = {
                "subject_id": str(params_t[0]),
                "company_code": params_t[1],
                "originating_event_id": str(params_t[2]),
            }
            if not any(item["subject_id"] == row["subject_id"] for item in self.tables["intake_subjects"]):
                self.tables["intake_subjects"].append(row)
            self._fetch = None
            return
        if "INSERT INTO intake_items" in text:
            row = {
                "item_id": str(params_t[0]),
                "company_code": params_t[1],
                "event_id": str(params_t[2]),
                "subject_id": str(params_t[3]),
                "legacy_submission_id": str(params_t[4]),
                "primary_document_id": str(params_t[5]) if params_t[5] else None,
            }
            if not any(item["item_id"] == row["item_id"] for item in self.tables["intake_items"]):
                self.tables["intake_items"].append(row)
            self._fetch = {"item_id": row["item_id"]}
            return
        if "INSERT INTO intake_item_documents" in text:
            row = {
                "company_code": params_t[0],
                "item_id": str(params_t[1]),
                "document_id": str(params_t[2]),
            }
            key = (row["company_code"], row["item_id"], row["document_id"])
            if not any(
                (item["company_code"], item["item_id"], item["document_id"]) == key
                for item in self.tables["intake_item_documents"]
            ):
                self.tables["intake_item_documents"].append(row)
            self._fetch = None
            return
        if "UPDATE intake_subjects" in text or "UPDATE intake_documents" in text:
            self._fetch = None
            return
        if "UPDATE intake_submissions" in text and "envelope_event_id" in text:
            self._fetch = None
            return
        self._fetch = None

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetch


class EnvelopeSchemaAndIdTests(unittest.TestCase):
    def test_schema_defines_channel_neutral_tables(self):
        sql = ici.SCHEMA_SQL
        for table in (
            "intake_source_events",
            "intake_subjects",
            "intake_items",
            "intake_item_documents",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        self.assertIn("envelope_event_id", sql)
        self.assertIn("envelope_item_id", sql)
        self.assertIn("envelope_subject_id", sql)
        self.assertIn("email_inbound", " ".join(sorted(ici.CHANNELS)))
        self.assertIn("whatsapp", ici.CHANNELS)
        self.assertIn("manual_upload", ici.CHANNELS)

    def test_stable_ids_are_deterministic(self):
        a = ici.stable_event_id(
            company_code="WATHEFNI",
            channel="email_inbound",
            provider="postmark",
            provider_account_id="",
            external_event_id="msg-1",
        )
        b = ici.stable_event_id(
            company_code="WATHEFNI",
            channel="email_inbound",
            provider="postmark",
            provider_account_id="",
            external_event_id="msg-1",
        )
        c = ici.stable_event_id(
            company_code="WATHEFNI",
            channel="email_inbound",
            provider="postmark",
            provider_account_id="",
            external_event_id="msg-2",
        )
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        uuid.UUID(a)
        subject = ici.stable_subject_id(event_id=a, ordinal=1)
        item = ici.stable_item_id(event_id=a, document_id="doc-1", ordinal=1)
        self.assertNotEqual(subject, item)

    def test_dual_write_flag_defaults_off(self):
        self.assertFalse(ici.dual_write_enabled({}))
        self.assertFalse(ici.dual_write_enabled({"WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "0"}))
        self.assertTrue(ici.dual_write_enabled({"WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1"}))
        self.assertTrue(ici.dual_write_enabled({"WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "true"}))


class EmailDualWriteParityTests(unittest.TestCase):
    def test_dual_write_skipped_when_flag_off(self):
        cur = RecordingCursor()
        result = ici.dual_write_email_receipt(
            cur,
            company_code="WATHEFNI",
            inbound_id=str(uuid.uuid4()),
            submission_id=str(uuid.uuid4()),
            provider="postmark",
            provider_message_id="pm-1",
            route_snapshot={"intake_id": "route-1"},
            source_provenance={"sender": "a@b.com"},
            documents=[],
            environ={},
        )
        self.assertTrue(result["skipped"])
        self.assertEqual(cur.statements, [])

    def test_dual_write_idempotent_and_parity_mapped(self):
        cur = RecordingCursor()
        inbound_id = str(uuid.uuid4())
        submission_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        docs = [
            {
                "document_id": document_id,
                "ordinal": 1,
                "filename": "cv.pdf",
                "storage_status": "stored",
                "safety_state": "scan_pending",
                "content_sha256": "abc",
            }
        ]
        env = {"WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1"}
        first = ici.dual_write_email_receipt(
            cur,
            company_code="WATHEFNI",
            inbound_id=inbound_id,
            submission_id=submission_id,
            provider="postmark",
            provider_message_id="pm-parity-1",
            route_snapshot={"intake_id": "route-1", "company_code": "WATHEFNI"},
            source_provenance={"channel": "email_inbound"},
            documents=docs,
            environ=env,
        )
        second = ici.dual_write_email_receipt(
            cur,
            company_code="WATHEFNI",
            inbound_id=inbound_id,
            submission_id=submission_id,
            provider="postmark",
            provider_message_id="pm-parity-1",
            route_snapshot={"intake_id": "route-1", "company_code": "WATHEFNI"},
            source_provenance={"channel": "email_inbound"},
            documents=docs,
            environ=env,
        )
        self.assertFalse(first["skipped"])
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["subject_id"], second["subject_id"])
        self.assertEqual(len(cur.tables["intake_source_events"]), 1)
        self.assertEqual(len(cur.tables["intake_subjects"]), 1)
        self.assertEqual(len(cur.tables["intake_items"]), 1)
        self.assertEqual(len(cur.tables["intake_item_documents"]), 1)
        self.assertEqual(first["document_links"], 1)
        self.assertEqual(len(first["item_ids"]), 1)

    def test_dual_write_wired_before_commit_and_email_path_authoritative(self):
        ingress = _source(ROOT / "durable_email_ingress.py")
        self.assertIn("import inbound_cv_intake as _inbound_cv_intake", ingress)
        self.assertIn("_inbound_cv_intake.dual_write_email_receipt", ingress)
        self.assertIn("_inbound_cv_intake.ensure_schema(cur)", ingress)
        # Dual-write happens before before_commit failpoint / commit.
        receive = re.search(
            r"def durably_receive_postmark\([\s\S]*?_call_failpoint\(failpoint, \"before_commit\"\)",
            ingress,
        )
        self.assertIsNotNone(receive)
        self.assertIn("dual_write_email_receipt", receive.group(0))
        # Envelope module must not become candidate/application authority.
        envelope = _source(ROOT / "inbound_cv_intake.py")
        for forbidden in (
            "INSERT INTO candidates",
            "INSERT INTO applications",
            "register_imported_cv",
            "cv_extraction",
            "candidate_knowledge",
            "talent_pool_classification",
        ):
            self.assertNotIn(forbidden, envelope)

    def test_no_whatsapp_or_manual_cutover_in_wave1(self):
        envelope = _source(ROOT / "inbound_cv_intake.py")
        self.assertIn("Wave 1 does not cut over WhatsApp or manual upload", envelope)
        app_src = _source(APP_PY)
        # Manual path uses register_imported_cv; email requires identity_resolution.
        self.assertIn("def register_imported_cv", app_src)
        # Unsolicited WhatsApp still uses pending media authority.
        self.assertIn("hold_candidate_pending_media", app_src)


class DefectRemediationTests(unittest.TestCase):
    def test_risk_catalog_marks_wave1_remediation(self):
        by_id = {item["id"]: item for item in THREE_CURRENT_RISKS}
        self.assertEqual(by_id["single_item_promotion_sql"]["wave1_status"], "remediated")
        self.assertEqual(by_id["manual_auto_admit_default"]["wave1_status"], "remediated_fail_closed")
        self.assertEqual(by_id["ck_sibling_over_denial"]["wave1_status"], "remediated_anchor_scoped")

    def test_single_item_assign_sql_placeholder_and_tenant(self):
        src = _extract_function_source(APP_PY, "dashboard_prehire_import_assign")
        update_match = re.search(
            r'cur\.execute\(\s*"""\s*(UPDATE applications.*?WHERE app_key=%s AND company_code=%s)\s*"""\s*,\s*\((.*?)\),\s*\)',
            src,
            flags=re.S,
        )
        self.assertIsNotNone(update_match)
        sql = update_match.group(1)
        args_src = update_match.group(2)
        placeholders = _count_sql_placeholders(sql)
        arg_names = [part.strip() for part in args_src.split(",") if part.strip()]
        self.assertEqual(placeholders, len(arg_names))
        self.assertEqual(placeholders, 9)
        self.assertIn("company_code=%s", sql)

    def test_auto_admit_fail_closed_when_unset(self):
        src = _extract_function_source(APP_PY, "company_auto_admit_imports")
        self.assertIn("if val is None:\n        return False", src)
        self.assertNotIn("return True", src)

    def test_ck_live_anchor_not_over_denied_by_held_sibling(self):
        phone = "+96550001111"
        store = InMemoryCandidateKnowledgeStore(
            applications=[
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-live",
                    "phone": phone,
                    "status": "ready_for_review",
                    "candidate_name": "Live Candidate",
                    "position_code": "HR",
                    "data_source": "production",
                },
                {
                    "company_code": "WATHEFNI",
                    "app_key": "app-held",
                    "phone": phone,
                    "status": "needs_role",
                    "candidate_name": "Live Candidate",
                    "position_code": "",
                    "data_source": "production",
                },
            ]
        )
        authority = CandidateKnowledgeAuthority(
            store,
            module_enabled=lambda company, module: module == "pre_hiring" and company == "WATHEFNI",
        )
        ctx = build_request_context(
            company_code="WATHEFNI",
            actor_user_id="user-1",
            permission_authority="backend_current",
            permission_subject_user_id="user-1",
            permission_subject_company="WATHEFNI",
            permissions=["prehire.read"],
            modules_enabled=["pre_hiring"],
        )
        live = authority.resolve_exact(ctx, "app:app-live")
        held = authority.resolve_exact(ctx, "app:app-held")
        self.assertEqual(len(live.applications), 2)
        self.assertTrue(live.actionability.readable)
        self.assertTrue(live.actionability.contact_allowed)
        self.assertTrue(live.actionability.lifecycle_mutation_allowed)
        self.assertTrue(live.actionability.job_ranking_allowed)
        self.assertTrue(held.actionability.readable)
        self.assertFalse(held.actionability.job_ranking_allowed)
        self.assertEqual(held.actionability.held_state, "needs_role")

        # Contrast: legacy AND helper still denies when mixed.
        mixed = cka._strictest_actionability(
            [
                crsp.evaluate_candidate_record_state({"status": "ready_for_review"}),
                crsp.evaluate_candidate_record_state({"status": "needs_role"}),
            ]
        )
        self.assertFalse(mixed.job_ranking_allowed)


class NoDuplicateAuthorityWriteTests(unittest.TestCase):
    def test_envelope_module_has_no_downstream_write_symbols(self):
        tree = ast.parse(_source(ROOT / "inbound_cv_intake.py"))
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        forbidden = {
            "register_imported_cv",
            "register_candidate_cv_file",
            "extract_cv",
            "classify",
            "index_candidate",
            "write_candidate_knowledge",
        }
        self.assertTrue(forbidden.isdisjoint(names))

    def test_dual_write_does_not_enqueue_processing_jobs(self):
        envelope = _source(ROOT / "inbound_cv_intake.py")
        self.assertNotIn("enqueue_job", envelope)
        self.assertNotIn("intake_processing_jobs", envelope)

    def test_email_idempotency_contracts_preserved(self):
        ingress = _source(ROOT / "durable_email_ingress.py")
        self.assertIn("UNIQUE (company_code, provider, provider_message_id)", ingress)
        self.assertIn("stable_inbound_id", ingress)
        self.assertIn("stable_submission_id", ingress)
        self.assertIn("stable_document_id", ingress)


class Wave1FingerprintTests(unittest.TestCase):
    def test_wave1_modules_hashable(self):
        modules = [
            ROOT / "inbound_cv_intake.py",
            ROOT / "durable_email_ingress.py",
            ROOT / "candidate_knowledge_authority.py",
            APP_PY,
        ]
        for path in modules:
            digest = _sha256(path)
            self.assertEqual(len(digest), 64)
        self.assertEqual(WAVE1_VERSION, "unified-inbound-cv-wave1-v1")
        self.assertEqual(ici.ENVELOPE_VERSION, "unified-inbound-cv-envelope-v1")


if __name__ == "__main__":
    unittest.main()
