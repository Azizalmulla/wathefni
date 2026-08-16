#!/usr/bin/env python3
"""Smoke tests for AnyDoc Office Shadow Canary Wave 1 (observation only)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import anydoc_office_shadow as shadow  # noqa: E402


class AnyDocOfficeShadowWave1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_flag_modes(self) -> None:
        self.assertEqual(shadow.shadow_mode({"WATHEFNI_ANYDOC_OFFICE_SHADOW": "off"}), "off")
        self.assertFalse(shadow.shadow_enabled({"WATHEFNI_ANYDOC_OFFICE_SHADOW": "off"}))
        self.assertEqual(
            shadow.shadow_mode({"WATHEFNI_ANYDOC_OFFICE_SHADOW": "staging_shadow"}),
            "staging_shadow",
        )
        self.assertTrue(shadow.shadow_enabled({"WATHEFNI_ANYDOC_OFFICE_SHADOW": "staging_shadow"}))
        self.assertEqual(
            shadow.shadow_mode({"WATHEFNI_ANYDOC_OFFICE_SHADOW": "production_shadow"}),
            "production_shadow",
        )

    def test_denies_pdf_and_identity(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\n")
            path = Path(tmp.name)
        try:
            out = shadow.run_anydoc_office_shadow(path, authoritative_text="x")
            self.assertEqual(out.get("skipped"), "denied_extension_or_mime")
            self.assertFalse(out.get("influences_routing"))
        finally:
            path.unlink(missing_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"PK\x03\x04")
            path = Path(tmp.name)
        try:
            out = shadow.run_anydoc_office_shadow(
                path,
                authoritative_text="x",
                document_class="civil_id",
            )
            self.assertEqual(out.get("skipped"), "identity_document_denied")
        finally:
            path.unlink(missing_ok=True)

    def test_flag_off_skips(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "off"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(b"a,b\n1,2\n")
            path = Path(tmp.name)
        try:
            out = shadow.run_anydoc_office_shadow(path, authoritative_text="a b")
            self.assertEqual(out.get("skipped"), "flag_off")
            self.assertFalse(out.get("ok"))
        finally:
            path.unlink(missing_ok=True)

    def test_fail_open_on_parser_exception(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"not-a-real-docx")
            path = Path(tmp.name)
        try:
            out = shadow.run_anydoc_office_shadow(path, authoritative_text="hello world " * 10)
            self.assertTrue(out.get("fail_open") or out.get("ok") is False)
            self.assertFalse(out.get("influences_routing"))
            self.assertFalse(out.get("influences_admission"))
        finally:
            path.unlink(missing_ok=True)

    def test_csv_shadow_observes_without_mutating_auth(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
        auth = "Name Role Hours\nAli Engineer 40"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(b"Name,Role,Hours\nAli,Engineer,40\n")
            path = Path(tmp.name)
        try:
            out = shadow.run_anydoc_office_shadow(path, authoritative_text=auth)
            self.assertTrue(out.get("ok"), out)
            self.assertEqual(out.get("pinned_version"), "0.1.2")
            self.assertFalse(out.get("hosted_firecrawl_parse"))
            self.assertTrue(out.get("local_bytes_only"))
            self.assertIsNotNone(out.get("output_sha256"))
            self.assertIsNotNone(out.get("latency_ms"))
            self.assertIn("quality", out)
            # Authoritative text is comparison input only — not replaced.
            self.assertEqual(out["comparison"]["authoritative"]["chars"], len(auth))
        finally:
            path.unlink(missing_ok=True)

    def test_timeout_fail_open(self) -> None:
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
        os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS"] = "1"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(b"a,b\n1,2\n")
            path = Path(tmp.name)

        def slow(*_a, **_k):
            import time

            time.sleep(0.05)
            return {"ok": True, "wall_ms": 50, "markdown": "x", "format_detected": "csv", "quality": shadow._quality_metrics("x")}

        try:
            with mock.patch.object(shadow, "_call_anydoc", side_effect=slow):
                out = shadow.run_anydoc_office_shadow(path, authoritative_text="x")
            self.assertTrue(out.get("fail_open"))
            self.assertEqual(out.get("error"), "timeout")
        finally:
            path.unlink(missing_ok=True)
            os.environ.pop("WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS", None)


if __name__ == "__main__":
    print("ANYDOC_OFFICE_SHADOW_SMOKE_START")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AnyDocOfficeShadowWave1Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("ANYDOC_OFFICE_SHADOW_SMOKE_OK")
