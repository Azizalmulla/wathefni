from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import candidate_cv_evidence as cve


class ScriptedCursor:
    def __init__(self, file_row: dict | None = None) -> None:
        self.file_row = file_row
        self.current = None
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.calls.append((str(sql), tuple(params or ())))
        if "SELECT file_id, content_sha256" in sql:
            self.current = self.file_row
        elif "INSERT INTO cv_extraction_finalizations" in sql:
            self.current = {
                "finalization_id": "00000000-0000-0000-0000-000000000001",
                "status": "completed",
                "quality_ok": True,
                "extracted_text_hash": params[4],
            }
        elif "INSERT INTO application_cv_evidence_materializations" in sql:
            self.current = {
                "evidence_id": "00000000-0000-0000-0000-000000000002",
                "company_code": params[1],
                "app_key": params[2],
                "status": "ready",
                "embedding_status": params[11],
                "contract_version": cve.CV_EVIDENCE_CONTRACT_VERSION,
            }
        else:
            self.current = None

    def fetchone(self):
        return self.current

    def fetchall(self):
        return []


def execute_adapter(cur: ScriptedCursor):
    def execute(sql, params=None, *, fetchone=False):
        cur.execute(sql, params or ())
        return cur.fetchone() if fetchone else None

    return execute


class CanonicalCvEvidenceTests(unittest.TestCase):
    def test_health_counts_can_exclude_non_production_fixture_rows(self):
        cur = ScriptedCursor()
        result = cve.health_counts(
            cur,
            company_code="TENANT_A",
            position_code="ACCOUNTING",
            production_only=True,
        )
        application_queries = [sql for sql, _ in cur.calls if "FROM applications a" in sql]
        self.assertEqual(result["total"], 0)
        self.assertEqual(len(application_queries), 2)
        self.assertTrue(all("a.data_source" in sql for sql in application_queries))
        self.assertTrue(all("smoke_test" not in sql for sql in application_queries))

    def ready_row(self, **overrides):
        row = {
            "cv_evidence_status": "ready",
            "cv_evidence_file_id": "file-1",
            "cv_evidence_source_sha256": "source-hash",
            "cv_extraction_finalization_id": "final-1",
            "cv_extraction_quality_ok": True,
            "cv_extracted_text_hash": "text-hash",
            "cv_evidence_semantic_content_hash": "text-hash",
            "semantic_content_hash": "text-hash",
            "semantic_content": "A sufficiently useful CV body.",
            "cv_evidence_contract_version": cve.CV_EVIDENCE_CONTRACT_VERSION,
            "cv_evidence_embedding_status": "missing",
        }
        row.update(overrides)
        return row

    def test_file_only_is_not_ready(self):
        state = cve.readiness_from_row({"cv_evidence_file_id": "file-1"})
        self.assertFalse(state["ready"])
        self.assertEqual(state["reason"], "cv_file_missing")

    def test_final_success_is_ready_without_embedding(self):
        state = cve.readiness_from_row(self.ready_row())
        self.assertTrue(state["ready"])
        self.assertEqual(state["embedding_status"], "missing")

    def test_superseded_or_hash_mismatched_evidence_fails_closed(self):
        superseded = cve.readiness_from_row(self.ready_row(cv_evidence_status="superseded"))
        mismatch = cve.readiness_from_row(self.ready_row(semantic_content_hash="other"))
        self.assertFalse(superseded["ready"])
        self.assertFalse(mismatch["ready"])
        self.assertEqual(mismatch["reason"], "cv_semantic_projection_stale")

    def test_materialization_is_tenant_scoped_idempotent_and_side_effect_free(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cv.txt"
            text = (
                "Experienced Python engineer with a bachelor degree and five years of relevant "
                "professional software delivery experience across reliable production systems."
            )
            path.write_text(text)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            cur = ScriptedCursor(
                {
                    "file_id": "file-1",
                    "content_sha256": digest,
                    "local_path": str(path),
                    "storage_object_key": "tenant/ACME/cv.txt",
                    "storage_status": "stored",
                    "metadata": {"latest": True},
                }
            )
            semantic_calls = []

            def semantic_upsert(cursor, *, application, content, metadata):
                semantic_calls.append((application["company_code"], application["app_key"], metadata))
                return {
                    "ok": True,
                    "semantic_id": "application:app-1:cv",
                    "content_hash": cve.sha256_text(content),
                    "embedded": False,
                }

            args = {
                "cur": cur,
                "db_execute": execute_adapter(cur),
                "application": {"company_code": "acme", "app_key": "app-1"},
                "document_id": "doc-1",
                "local_path": str(path),
                "source_content_sha256": digest,
                "extracted_text": text,
                "extraction_method": "text",
                "extraction_metadata": {"source": "test"},
                "semantic_upsert": semantic_upsert,
                "actor": "migration-test",
            }
            first = cve.materialize_extracted_cv(**args)
            second = cve.materialize_extracted_cv(**args)

        self.assertEqual(first["evidence"]["evidence_id"], second["evidence"]["evidence_id"])
        self.assertEqual(first["evidence"]["embedding_status"], "missing")
        self.assertEqual([call[:2] for call in semantic_calls], [("acme", "app-1"), ("acme", "app-1")])
        file_select = next(call for call in cur.calls if "SELECT file_id, content_sha256" in call[0])
        self.assertEqual(file_select[1][0], "ACME")
        self.assertTrue(any("status='superseded'" in sql for sql, _ in cur.calls))
        self.assertFalse(any(token in sql.lower() for sql, _ in cur.calls for token in ("outbound", "lifecycle", "notification")))

    def test_managed_file_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cv.txt"
            path.write_text("Actual file bytes differ from the registry.")
            cur = ScriptedCursor(
                {
                    "file_id": "file-1",
                    "content_sha256": "0" * 64,
                    "local_path": str(path),
                    "storage_object_key": "tenant/ACME/cv.txt",
                    "storage_status": "stored",
                    "metadata": {"latest": True},
                }
            )
            with self.assertRaisesRegex(ValueError, "managed_cv_file_hash_mismatch"):
                cve.materialize_extracted_cv(
                    cur,
                    db_execute=execute_adapter(cur),
                    application={"company_code": "ACME", "app_key": "app-1"},
                    document_id="doc-1",
                    local_path=str(path),
                    source_content_sha256=None,
                    extracted_text=(
                        "Experienced engineer with several years of relevant professional work "
                        "building reliable software systems for multiple business teams and customers."
                    ),
                    extraction_method="text",
                    extraction_metadata={},
                    semantic_upsert=lambda *args, **kwargs: {},
                    actor="test",
                )


if __name__ == "__main__":
    unittest.main()
