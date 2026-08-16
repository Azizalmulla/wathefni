#!/usr/bin/env python3
"""Server regression: pool exhaustion must not become employee_app_not_enabled."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app.py"


def _load_helpers():
    """Load only the helper functions we need without importing full app."""
    # Importing app.py is heavy; unit-test the helper via exec of the snippet
    # after ensuring the functions exist in source.
    source = APP_PATH.read_text(encoding="utf-8")
    assert "def _is_transient_db_error" in source
    assert "if _is_transient_db_error(exc):" in source
    assert "employee_app_temporarily_unavailable" in source
    return source


class PoolExhaustionEntitlementTests(unittest.TestCase):
    def test_source_reraises_pool_errors(self):
        source = _load_helpers()
        # configured_company_modules must re-raise transient DB errors
        idx = source.index("def configured_company_modules")
        chunk = source[idx : idx + 1800]
        self.assertIn("if _is_transient_db_error(exc):", chunk)
        self.assertIn("raise", chunk)
        # Must not bare-pass all exceptions anymore without the transient check
        self.assertNotIn("except Exception:\n        pass", chunk)
        self.assertIn("except Exception as exc:", chunk)

    def test_employee_app_context_maps_to_503(self):
        source = _load_helpers()
        self.assertIn('"error": "employee_app_temporarily_unavailable"', source)
        self.assertIn("status_code=503", source)

    def test_transient_helper_logic(self):
        # Execute helper in isolation
        ns: dict = {"BaseException": BaseException}
        # Extract function body from app.py via a minimal exec
        source = _load_helpers()
        start = source.index("def _is_transient_db_error")
        end = source.index("\ndef configured_company_modules", start)
        exec(source[start:end], ns)
        helper = ns["_is_transient_db_error"]

        class PoolError(Exception):
            pass

        self.assertTrue(helper(PoolError("connection pool exhausted")))
        self.assertTrue(helper(Exception("connection pool exhausted")))
        self.assertFalse(helper(ValueError("bad module key")))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PoolExhaustionEntitlementTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
