"""Regression: Jobs lifecycle status request must keep OCC tokens on the model.

Bug: DashboardPositionStatus only declared `status`, so Pydantic dropped
`expected_version` / `expected_updated_at`. The handler then raised
AttributeError and `_jobs_http_error` returned generic 400 jobs_error —
every pause/resume/reopen/close failed.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

import app as app_mod
import concurrency_safety as cs
import prehire_jobs as jobs
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"


def _dashboard_position_status_ast_fields() -> set[str]:
    tree = ast.parse(APP_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "DashboardPositionStatus":
            fields: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.add(item.target.id)
            return fields
    raise AssertionError("DashboardPositionStatus class not found in app.py")


class JobsPositionStatusContractTests(unittest.TestCase):
    def test_model_declares_occ_fields_in_source(self) -> None:
        fields = _dashboard_position_status_ast_fields()
        self.assertIn("status", fields)
        self.assertIn("expected_version", fields)
        self.assertIn("expected_updated_at", fields)

    def test_model_preserves_occ_tokens(self) -> None:
        req = app_mod.DashboardPositionStatus.model_validate(
            {
                "status": "paused",
                "expected_version": 7,
                "expected_updated_at": "2026-07-30T04:00:00+00:00",
            }
        )
        # Exact handler access pattern — must not AttributeError.
        self.assertEqual(req.status, "paused")
        self.assertEqual(req.expected_version, 7)
        self.assertEqual(req.expected_updated_at, "2026-07-30T04:00:00+00:00")

    def test_malformed_expected_version_is_validation_error(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            app_mod.DashboardPositionStatus.model_validate(
                {"status": "open", "expected_version": "not-an-int"}
            )
        errors = ctx.exception.errors()
        self.assertTrue(any(err.get("loc") == ("expected_version",) for err in errors))

    def test_missing_token_still_enforced_by_occ(self) -> None:
        row = {
            "position_code": "CONTRACT",
            "version": 3,
            "updated_at": "2026-07-30T04:00:00+00:00",
            "updated_by_user_id": "u1",
        }
        with self.assertRaises(jobs.JobsError) as ctx:
            jobs._assert_fresh(row, expected_updated_at=None, expected_version=None)
        self.assertEqual(ctx.exception.code, "missing_expected_version")
        self.assertEqual(ctx.exception.http_status, 422)

    def test_stale_version_returns_conflict_code(self) -> None:
        row = {
            "position_code": "CONTRACT",
            "version": 3,
            "updated_at": "2026-07-30T04:00:00+00:00",
            "updated_by_user_id": "u1",
        }
        with self.assertRaises(jobs.JobsError) as ctx:
            jobs._assert_fresh(row, expected_updated_at=None, expected_version=1)
        self.assertEqual(ctx.exception.code, "stale_job_version")
        self.assertEqual(ctx.exception.http_status, 409)
        detail = ctx.exception.details
        self.assertEqual(detail.get("current_version"), 3)
        self.assertEqual(detail.get("expected_version"), 1)

    def test_lifecycle_transition_matrix_unchanged(self) -> None:
        self.assertEqual(jobs.assert_transition("open", "paused"), "pause")
        self.assertEqual(jobs.assert_transition("paused", "open"), "resume")
        self.assertEqual(jobs.assert_transition("open", "closed"), "close")
        self.assertEqual(jobs.assert_transition("closed", "open"), "reopen")
        with self.assertRaises(jobs.JobsError):
            jobs.assert_transition("closed", "paused")

    def test_status_http_forwards_occ_and_rejects_malformed(self) -> None:
        captured: dict[str, object] = {}

        def fake_context() -> dict:
            return {
                "company_code": "WATHEFNI",
                "actor_user_id": "test-actor",
                "actor_role": "owner",
                "access": {"role": "owner", "permissions": ["jobs.publish", "jobs.close", "jobs.edit", "jobs.read"]},
                "entitlements": {"pre_hiring": True},
            }

        current = {
            "position_code": "OCCFIX",
            "status": "open",
            "version": 4,
            "updated_at": "2026-07-30T05:00:00+00:00",
            "title": "OCC Fix",
        }

        def fake_get_job(*, company, position_code, db_connect):  # noqa: ANN001
            self.assertEqual(company, "WATHEFNI")
            self.assertEqual(position_code, "OCCFIX")
            return dict(current)

        def fake_set_status(company, position_code, status, **kwargs):  # noqa: ANN001
            captured["company"] = company
            captured["position_code"] = position_code
            captured["status"] = status
            captured["expected_version"] = kwargs.get("expected_version")
            captured["expected_updated_at"] = kwargs.get("expected_updated_at")
            return {
                **current,
                "status": status,
                "version": int(current["version"]) + 1,
                "transition_action": "pause",
            }

        app = app_mod.app
        app.dependency_overrides[app_mod.prehire_dashboard_context] = fake_context
        client = TestClient(app)
        try:
            with (
                mock.patch.object(app_mod._prehire_jobs, "get_job", side_effect=fake_get_job),
                mock.patch.object(app_mod, "dashboard_set_position_status", side_effect=fake_set_status),
                mock.patch.object(app_mod, "require_jobs_permission", return_value="WATHEFNI"),
                mock.patch.object(app_mod, "record_admin_audit", return_value=None),
            ):
                # Valid OCC payload reaches transition with tokens intact.
                resp = client.post(
                    "/dashboard/prehire/positions/OCCFIX/status",
                    json={
                        "status": "paused",
                        "expected_version": 4,
                        "expected_updated_at": "2026-07-30T05:00:00+00:00",
                    },
                )
                self.assertEqual(resp.status_code, 200, resp.text)
                self.assertEqual(captured.get("expected_version"), 4)
                self.assertEqual(captured.get("expected_updated_at"), "2026-07-30T05:00:00+00:00")
                self.assertEqual(captured.get("status"), "paused")

                # Malformed token → FastAPI/Pydantic 422, not generic jobs_error 400.
                bad = client.post(
                    "/dashboard/prehire/positions/OCCFIX/status",
                    json={"status": "paused", "expected_version": "nope"},
                )
                self.assertEqual(bad.status_code, 422, bad.text)
                body = bad.json()
                detail = body.get("detail")
                # Never the AttributeError / jobs_error envelope.
                if isinstance(detail, dict):
                    self.assertNotEqual(detail.get("error"), "jobs_error")
                else:
                    self.assertIsInstance(detail, list)
        finally:
            app.dependency_overrides.pop(app_mod.prehire_dashboard_context, None)

    def test_concurrency_safe_next_action_preserved(self) -> None:
        err = cs.ConcurrencyError(
            "stale_job_version",
            details={
                "current_version": 2,
                "expected_version": 1,
                "entity_type": "job",
                "entity_id": "X",
            },
        )
        detail = err.as_detail()
        self.assertEqual(detail.get("error"), "stale_job_version")
        self.assertEqual(detail.get("safe_next_action"), cs.SAFE_NEXT_ACTION)


if __name__ == "__main__":
    unittest.main()
