"""Route authority/error contracts for Talent Pool Classification."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

import talent_pool_classification_routes as routes


class FakeApp:
    def __init__(self) -> None:
        self.routes = {}

    def _register(self, method: str, path: str):
        def decorator(fn):
            self.routes[(method, path)] = fn
            return fn

        return decorator

    def get(self, path: str):
        return self._register("GET", path)

    def post(self, path: str):
        return self._register("POST", path)


class FakeCursor:
    def __init__(self, application_exists: bool) -> None:
        self.application_exists = application_exists

    def execute(self, _sql, _params=()):
        return None

    def fetchone(self):
        return {"exists": 1} if self.application_exists else None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeConnection:
    def __init__(self, application_exists: bool) -> None:
        self.application_exists = application_exists

    def cursor(self):
        return FakeCursor(self.application_exists)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeModule:
    def __init__(self, *, allowed: bool, application_exists: bool = False) -> None:
        self.app = FakeApp()
        self.allowed = allowed
        self.application_exists = application_exists
        self.permission_calls = []
        self.audit_calls = []

    def prehire_dashboard_context(self):
        return {}

    def require_entitlement(self, context, module, permission):
        self.permission_calls.append((context, module, permission))
        if not self.allowed:
            raise HTTPException(
                status_code=403,
                detail={"error": "permission_denied", "message": "You do not have access to do that."},
            )

    def db_connect(self):
        return FakeConnection(self.application_exists)

    def record_admin_audit(self, *args, **kwargs):
        self.audit_calls.append((args, kwargs))


REVIEW_PATH = "/dashboard/prehire/applications/{app_key}/classification/review"


class ClassificationRouteContractTests(unittest.TestCase):
    def mounted_review(self, module: FakeModule):
        routes.mount_talent_pool_classification_routes(module)
        return module.app.routes[("POST", REVIEW_PATH)]

    @patch("talent_pool_classification_routes.tpc.feature_enabled_for_company", return_value=True)
    def test_restricted_viewer_is_denied_before_review_processing(self, _enabled) -> None:
        module = FakeModule(allowed=False)
        review = self.mounted_review(module)

        with self.assertRaises(HTTPException) as caught:
            review(
                "APP-1",
                {"action": "add", "node_id": "fn.hr", "preview": True},
                {"actor_role": "viewer"},
            )

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(module.permission_calls[0][1:], ("pre_hiring", "candidate.manage"))

    @patch("talent_pool_classification_routes.tpc.feature_manual_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_ui_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_enabled_for_company", return_value=True)
    def test_invalid_action_returns_calm_422_not_500(self, _enabled, _ui, _manual) -> None:
        review = self.mounted_review(FakeModule(allowed=True))

        with self.assertRaises(HTTPException) as caught:
            review("APP-1", {}, {"actor_role": "owner"})

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail["error"], "invalid_classification_review_action")
        self.assertTrue(caught.exception.detail["message"])

    @patch("talent_pool_classification_routes.tpc.feature_manual_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_ui_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_enabled_for_company", return_value=True)
    def test_preview_requires_a_real_tenant_application(self, _enabled, _ui, _manual) -> None:
        review = self.mounted_review(FakeModule(allowed=True, application_exists=False))

        with self.assertRaises(HTTPException) as caught:
            review(
                "MISSING",
                {"action": "add", "node_id": "fn.hr", "preview": True},
                {"actor_role": "owner"},
            )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail["error"], "application_not_found")
        self.assertTrue(caught.exception.detail["message"])

    @patch("talent_pool_classification_routes.tpc.ensure_classification_schema")
    @patch("talent_pool_classification_routes.tpc.append_review_event")
    @patch("talent_pool_classification_routes.tpc.taxonomy_index", return_value={"fn.hr": {}})
    @patch("talent_pool_classification_routes.tpc.load_taxonomy_pack", return_value={})
    @patch("talent_pool_classification_routes.tpc.feature_manual_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_ui_enabled", return_value=True)
    @patch("talent_pool_classification_routes.tpc.feature_enabled_for_company", return_value=True)
    def test_confirmed_review_records_admin_audit(
        self,
        _enabled,
        _ui,
        _manual,
        _pack,
        _index,
        append_review,
        _ensure,
    ) -> None:
        append_review.return_value = {
            "event_id": "EVT-1",
            "action": "add",
            "node_id": "fn.hr",
            "previous_node_id": None,
            "actor_user_id": "USR-1",
            "actor_email": "hr@wathefni.test",
        }
        module = FakeModule(allowed=True, application_exists=True)
        review = self.mounted_review(module)

        result = review(
            "APP-1",
            {"action": "add", "node_id": "fn.hr", "confirm": True},
            {"company_code": "WATHEFNI", "actor_user_id": "USR-1"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(module.audit_calls), 1)
        self.assertEqual(module.audit_calls[0][0][1], "candidate_classification_reviewed")


if __name__ == "__main__":
    unittest.main()
