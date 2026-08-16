#!/usr/bin/env python3
"""Smoke tests for AnyDoc Office Authority Closure Wave."""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import anydoc_office_authority as auth  # noqa: E402
import anydoc_office_shadow as shadow  # noqa: E402


class _FakeResult:
    def __init__(self, text: str, method: str = "existing"):
        self.text = text
        self.method = method
        self.error = None
        self.quality_ok = bool(text)
        self.blocks = [{"t": "x"}]
        self.provenance = [{"p": 1}]
        self.content_sha256 = "abc"
        self.metadata: dict = {}


class AnyDocOfficeAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_roles(self) -> None:
        self.assertEqual(auth.role_for_extension(".docx"), auth.ROLE_PRIMARY_NORMALIZE)
        self.assertEqual(auth.role_for_extension(".pptx"), auth.ROLE_DOC_TEXT_NORMALIZE)
        self.assertEqual(auth.role_for_extension(".xlsx"), auth.ROLE_MARKDOWN_ONLY)
        self.assertEqual(auth.role_for_extension(".csv"), auth.ROLE_MARKDOWN_ONLY)
        self.assertEqual(auth.role_for_extension(".rtf"), auth.ROLE_SHADOW_ONLY)
        self.assertEqual(auth.role_for_extension(".pdf"), auth.ROLE_DENIED)

    def test_flag_off_uses_shadow_when_enabled(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "off"
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "production_shadow"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(b"a,b\n1,2\n")
            path = Path(tmp.name)
        try:
            result = _FakeResult("a,b\n1,2")
            out = auth.maybe_run_and_attach(result, path, company_code="WATHEFNI")
            self.assertIn("anydoc_office_shadow", out.metadata)
            self.assertNotIn("anydoc_office_authority", out.metadata)
            self.assertEqual(out.text, "a,b\n1,2")
        finally:
            path.unlink(missing_ok=True)

    def test_csv_markdown_only_never_replaces_text(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "production"
        auth_text = "Name,Role,Hours\nAli,Engineer,40\n"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(auth_text.encode())
            path = Path(tmp.name)
        try:
            result = _FakeResult(auth_text, method="text")
            out = auth.maybe_run_and_attach(result, path, company_code="WATHEFNI")
            self.assertEqual(out.text, auth_text)
            self.assertEqual(out.method, "text")
            decision = out.metadata["anydoc_office_authority"]
            self.assertEqual(decision["role"], auth.ROLE_MARKDOWN_ONLY)
            self.assertTrue(decision["structured_authority_unchanged"])
            self.assertFalse(decision["influences_payroll"])
            self.assertFalse(decision["influences_migration"])
            # Structured parse still works on original bytes
            rows = list(csv.DictReader(io.StringIO(path.read_text())))
            self.assertEqual(rows[0]["Name"], "Ali")
            self.assertEqual(rows[0]["Hours"], "40")
        finally:
            path.unlink(missing_ok=True)

    def test_pdf_and_identity_denied(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "production"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\n")
            path = Path(tmp.name)
        try:
            out = auth.maybe_run_and_attach(_FakeResult("x"), path, company_code="WATHEFNI")
            self.assertEqual(out.metadata["anydoc_office_authority"]["fallback_reason"], "denied_extension_or_mime")
        finally:
            path.unlink(missing_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"PK\x03\x04")
            path = Path(tmp.name)
        try:
            out = auth.maybe_run_and_attach(
                _FakeResult("x"), path, document_class="civil_id", company_code="WATHEFNI"
            )
            self.assertEqual(out.metadata["anydoc_office_authority"]["fallback_reason"], "identity_document_denied")
            self.assertEqual(out.text, "x")
        finally:
            path.unlink(missing_ok=True)

    def test_docx_fallback_on_quality_fail(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "production"
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"not-a-docx")
            path = Path(tmp.name)
        try:
            existing = "Existing DOCX text from cv_docx parser with enough characters for quality."
            result = _FakeResult(existing, method="docx-local")
            out = auth.maybe_run_and_attach(result, path, company_code="WATHEFNI")
            self.assertEqual(out.text, existing)
            self.assertEqual(out.method, "docx-local")
            decision = out.metadata["anydoc_office_authority"]
            self.assertEqual(decision["selected_engine"], "existing_docx")
            self.assertFalse(decision.get("promoted"))
            self.assertEqual(out.blocks, [{"t": "x"}])  # structure preserved
        finally:
            path.unlink(missing_ok=True)

    def test_docx_promote_when_quality_ok(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "production"
        md = "# CV\n\n" + ("Senior engineer experience bilingual علي محمد. " * 8)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"PK fake")
            path = Path(tmp.name)
        fake_obs = {
            "ok": True,
            "fail_open": False,
            "latency_ms": 1,
            "output_sha256": "deadbeef",
            "character_count": len(md),
            "engine_version": "0.1.2",
            "content_sha256": "abc",
            "quality": shadow._quality_metrics(md),
            "comparison": {
                "disagreement_reasons": [],
                "material_disagreement": False,
                "completeness_ratio": 1.0,
                "authoritative": {"sha256": "a"},
            },
            "error": None,
        }
        try:
            with mock.patch.object(shadow, "run_anydoc_office_shadow", return_value=fake_obs):
                with mock.patch.object(auth, "_recover_markdown", return_value=md):
                    result = _FakeResult("short", method="docx-local")
                    out = auth.maybe_run_and_attach(result, path, company_code="WATHEFNI")
            self.assertEqual(out.text, md)
            self.assertEqual(out.method, "anydoc_docx")
            self.assertTrue(out.metadata["anydoc_office_authority"]["promoted"])
            self.assertEqual(out.blocks, [{"t": "x"}])
        finally:
            path.unlink(missing_ok=True)

    def test_legacy_rtf_shadow_only(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "production"
        with tempfile.NamedTemporaryFile(suffix=".rtf", delete=False) as tmp:
            tmp.write(b"{\\rtf1 hello world content enough chars here forever}")
            path = Path(tmp.name)
        try:
            result = _FakeResult("existing rtf")
            out = auth.maybe_run_and_attach(result, path, company_code="WATHEFNI")
            self.assertEqual(out.text, "existing rtf")
            decision = out.metadata["anydoc_office_authority"]
            self.assertEqual(decision["role"], auth.ROLE_SHADOW_ONLY)
            self.assertEqual(decision["fallback_reason"], "format_shadow_only")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    print("ANYDOC_OFFICE_AUTHORITY_SMOKE_START")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AnyDocOfficeAuthorityTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("ANYDOC_OFFICE_AUTHORITY_SMOKE_OK")
