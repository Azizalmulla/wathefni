from __future__ import annotations

import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import recruiting_lifecycle as lifecycle


class FakeCursor:
    def __init__(self, db: "FakeDatabase") -> None:
        self.db = db
        self.result: Any = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def fetchone(self) -> Any:
        return self.result

    def fetchall(self) -> list[Any]:
        return self.result if isinstance(self.result, list) else []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        normalized = " ".join(sql.lower().split())
        values = params or ()
        self.result = None
        if normalized.startswith(("create ", "alter ", "comment ", "do $$")) or "create trigger" in normalized:
            for app in self.db.applications.values():
                app.setdefault("lifecycle_version", 0)
            return
        if "set_config('wathefni.lifecycle_authority'" in normalized:
            self.result = {"set_config": "canonical"}
            return
        if normalized.startswith("select * from applications where app_key=%s and company_code=%s"):
            self.result = self.db.applications.get((str(values[1]), str(values[0])))
            return
        if normalized.startswith("select * from candidate_action_confirmations where company_code=%s and idempotency_key=%s"):
            self.result = next(
                (
                    row
                    for row in self.db.confirmations.values()
                    if row["company_code"] == values[0] and row.get("idempotency_key") == values[1]
                ),
                None,
            )
            return
        if normalized.startswith("insert into candidate_action_confirmations"):
            confirmation_id = f"confirmation-{len(self.db.confirmations) + 1}"
            row = {
                "confirmation_id": confirmation_id,
                "company_code": values[0],
                "app_key": values[1],
                "action": values[2],
                "observed_stage": values[3],
                "observed_version": values[4],
                "target_payload": values[5],
                "request_hash": values[6],
                "token_hash": values[7],
                "actor_user_id": values[8],
                "actor_phone": values[9],
                "actor_type": values[10],
                "channel": values[11],
                "idempotency_key": values[12],
                "expires_at": values[13],
                "status": "pending",
            }
            self.db.confirmations[confirmation_id] = row
            self.result = row
            return
        if normalized.startswith("select * from candidate_action_confirmations where confirmation_id=%s"):
            row = self.db.confirmations.get(str(values[0]))
            self.result = (
                row
                if row and row["company_code"] == values[1] and row["app_key"] == values[2]
                else None
            )
            return
        if normalized.startswith("update candidate_action_confirmations set status='processing'"):
            self.db.confirmations[str(values[0])]["status"] = "processing"
            return
        if normalized.startswith("update candidate_action_confirmations set status='expired'"):
            self.db.confirmations[str(values[0])]["status"] = "expired"
            return
        if normalized.startswith("update candidate_action_confirmations set status='consumed'"):
            confirmation_id = str(values[-1])
            self.db.confirmations[confirmation_id]["status"] = "consumed"
            self.db.confirmations[confirmation_id]["result"] = values[0]
            return
        if normalized.startswith("select * from application_lifecycle_events"):
            company, idem = values
            self.result = next(
                (event for event in self.db.events if event["company_code"] == company and event.get("idempotency_key") == idem),
                None,
            )
            return
        if normalized.startswith("update applications set status=%s"):
            target, current_step, app_key, company = values
            app = self.db.applications[(str(company), str(app_key))]
            app.update(
                {
                    "status": target,
                    "current_step": current_step,
                    "lifecycle_version": int(app.get("lifecycle_version") or 0) + 1,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self.result = app
            return
        if normalized.startswith("update candidates set current_status=%s"):
            self.db.candidate_status[str(values[2])] = str(values[0])
            return
        if normalized.startswith("insert into application_lifecycle_events"):
            row = {
                "event_id": values[0],
                "company_code": values[1],
                "app_key": values[2],
                "from_stage": values[3],
                "to_stage": values[4],
                "trigger": values[5],
                "actor_type": values[6],
                "actor_user_id": values[7],
                "actor_phone": values[8],
                "channel": values[9],
                "confirmation_token": values[10],
                "idempotency_key": values[11],
                "expected_from_stage": values[12],
                "metadata": values[13],
            }
            self.db.events.append(row)
            self.result = row
            return
        raise AssertionError(f"Unhandled SQL in fake integration test: {normalized}")


class FakeConnection:
    def __init__(self, db: "FakeDatabase") -> None:
        self.db = db

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.db)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakeDatabase:
    def __init__(self) -> None:
        self.applications: dict[tuple[str, str], dict[str, Any]] = {}
        self.confirmations: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.candidate_status: dict[str, str] = {}


class FakeLegacy:
    def __init__(self) -> None:
        self.db = FakeDatabase()

    def db_connect(self) -> FakeConnection:
        return FakeConnection(self.db)

    @staticmethod
    def digits(value: Any) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def json_safe(value: Any) -> Any:
        return value

    @staticmethod
    def Json(value: Any) -> Any:
        return value


class CandidateAuthorityIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.legacy = FakeLegacy()
        self.company = "TENANT_A"
        self.app_key = "APP-1"
        self.phone = "96550000001"
        self.actor = "operator-1"
        self.legacy.db.applications[(self.company, self.app_key)] = {
            "app_key": self.app_key,
            "company_code": self.company,
            "phone": self.phone,
            "status": "ready_for_review",
            "current_step": "ready_for_review",
            "lifecycle_version": 0,
            "raw_json": {},
        }

    def mint(self, action: str, payload: dict[str, Any], permissions: set[str]) -> dict[str, Any]:
        result = lifecycle.mint_candidate_action_confirmation(
            self.legacy,
            company_code=self.company,
            app_key=self.app_key,
            action=action,
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload=payload,
            actor_user_id=self.actor,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions=permissions,
        )
        self.assertTrue(result["ok"], result)
        return result["confirmation"]

    def transition(
        self,
        confirmation: dict[str, Any],
        *,
        target: str,
        action: str,
        payload: dict[str, Any],
        permissions: set[str],
        expected_stage: str = "ready_for_review",
        expected_version: int = 0,
    ) -> dict[str, Any]:
        return lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code=self.company,
            to_stage=target,
            trigger=f"dashboard_{action}",
            expected_from_stage=expected_stage,
            expected_version=expected_version,
            actor_type="human",
            actor_user_id=self.actor,
            channel="web",
            confirmation_id=confirmation["confirmation_id"],
            confirmation_token=confirmation["confirmation_token"],
            confirmation_action=action,
            confirmation_payload=payload,
            human_confirmed=True,
            permissions=permissions,
            metadata=payload,
        )

    def test_missing_and_cross_tenant_fail_closed(self) -> None:
        missing = lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code="",
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
        )
        cross = lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code="TENANT_B",
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            human_confirmed=True,
            confirmation_id="x",
            confirmation_token="x",
            permissions={"candidate.manage"},
        )
        self.assertEqual(missing["error"], "tenant_scope_required")
        self.assertEqual(cross["error"], "application_not_found")

    def test_confirmation_is_required_and_ai_cannot_manufacture_it(self) -> None:
        omitted = lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code=self.company,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            permissions={"candidate.manage"},
        )
        ai = lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code=self.company,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            actor_type="ai",
            human_confirmed=True,
            confirmation_id="made-up",
            confirmation_token="made-up",
            permissions={"candidate.manage"},
        )
        self.assertEqual(omitted["error"], "confirmation_required")
        self.assertEqual(ai["error"], "ai_cannot_mutate_stage")

    def test_valid_confirmation_succeeds_once_and_audits(self) -> None:
        confirmation = self.mint("shortlist", {}, {"candidate.manage"})
        first = self.transition(
            confirmation,
            target="shortlisted",
            action="shortlist",
            payload={},
            permissions={"candidate.manage"},
        )
        second = lifecycle.transition_application(
            self.legacy,
            app_key=self.app_key,
            company_code=self.company,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            actor_type="human",
            actor_user_id=self.actor,
            confirmation_id=confirmation["confirmation_id"],
            confirmation_token=confirmation["confirmation_token"],
            confirmation_action="shortlist",
            confirmation_payload={},
            human_confirmed=True,
            permissions={"candidate.manage"},
        )
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["application"]["lifecycle_version"], 1)
        self.assertEqual(self.legacy.db.candidate_status[self.phone], "shortlisted")
        self.assertEqual(len(self.legacy.db.events), 1)
        self.assertEqual(second["error"], "confirmation_already_used")

    def test_expired_stale_and_changed_payload_are_denied(self) -> None:
        expired_confirmation = self.mint("reject", {"reason_code": "not_selected"}, {"candidate.decide"})
        self.legacy.db.confirmations[expired_confirmation["confirmation_id"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        expired = self.transition(
            expired_confirmation,
            target="rejected",
            action="reject",
            payload={"reason_code": "not_selected"},
            permissions={"candidate.decide"},
        )
        self.assertEqual(expired["error"], "confirmation_expired")

        changed_confirmation = self.mint("reject", {"reason_code": "not_selected"}, {"candidate.decide"})
        changed = self.transition(
            changed_confirmation,
            target="rejected",
            action="reject",
            payload={"reason_code": "not_selected", "note": "changed"},
            permissions={"candidate.decide"},
        )
        self.assertEqual(changed["error"], "confirmation_payload_changed")

        stale_confirmation = self.mint("reject", {"reason_code": "not_selected"}, {"candidate.decide"})
        app = self.legacy.db.applications[(self.company, self.app_key)]
        app["status"] = "shortlisted"
        app["lifecycle_version"] = 1
        stale = self.transition(
            stale_confirmation,
            target="rejected",
            action="reject",
            payload={"reason_code": "not_selected"},
            permissions={"candidate.decide"},
            expected_stage="shortlisted",
            expected_version=1,
        )
        self.assertEqual(stale["error"], "stale_confirmation")

    def test_permission_revocation_and_structured_reason(self) -> None:
        confirmation = self.mint("reject", {"reason_code": "not_selected"}, {"candidate.decide"})
        revoked = self.transition(
            confirmation,
            target="rejected",
            action="reject",
            payload={"reason_code": "not_selected"},
            permissions=set(),
        )
        self.assertEqual(revoked["error"], "permission_denied")
        no_reason = lifecycle.mint_candidate_action_confirmation(
            self.legacy,
            company_code=self.company,
            app_key=self.app_key,
            action="reject",
            observed_stage="ready_for_review",
            observed_version=0,
            target_payload={},
            actor_user_id=self.actor,
            actor_phone=None,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
        )
        self.assertEqual(no_reason["error"], "rejection_reason_required")


class CandidateAuthoritySourceContractTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent

    def source(self, name: str) -> str:
        return (self.ROOT / name).read_text(encoding="utf-8")

    def test_registry_defaults_human_confirmation_false(self) -> None:
        source = self.source("action_registry.py")
        self.assertNotIn('get("human_confirmed", True)', source)
        self.assertIn('get("human_confirmed", False)', source)

    def test_cv_worker_uses_canonical_transitions(self) -> None:
        source = self.source("app.py")
        self.assertIn("_rl.mark_cv_ready_for_review(", source)
        self.assertIn('idempotency_key=f"cv-failed:', source)
        cv_success_window = source[source.index("def process_candidate_cv_document"):source.index("def run_candidate_cv_processing_worker")]
        self.assertNotRegex(cv_success_window, re.compile(r"status\s*=\s*CASE", re.IGNORECASE))

    def test_database_guard_and_hire_atomicity_are_present(self) -> None:
        lifecycle_source = self.source("recruiting_lifecycle.py")
        hire_source = self.source("hire_operations.py")
        self.assertIn("applications_lifecycle_authority_guard", lifecycle_source)
        self.assertIn("application_lifecycle_direct_write_blocked", lifecycle_source)
        self.assertIn("transactional_side_effect=_employee_transaction", hire_source)
        self.assertIn("SET app_key=%s", hire_source)
        self.assertIn("status='completed'", hire_source)

    def test_transitional_duplicate_constraint_is_active_only(self) -> None:
        source = self.source("recruiting_lifecycle.py")
        self.assertIn("applications_one_active_same_role_uq", source)
        for terminal in ("rejected", "withdrawn", "hired"):
            self.assertIn(f"'{terminal}'", source)

    def test_no_candidate_runtime_wathefni_fallbacks_in_authorities(self) -> None:
        for name in (
            "recruiting_lifecycle.py",
            "hire_operations.py",
            "cv_extraction.py",
            "cv_docx.py",
        ):
            source = self.source(name)
            self.assertNotIn('or "WATHEFNI"', source, name)
        registry = self.source("action_registry.py")
        self.assertNotIn('app.get("company_code") or "WATHEFNI"', registry)
        app = self.source("app.py")
        self.assertIn(
            "def request_company_code(request: WhatsAppTurnRequest, default: str | None = None)",
            app,
        )
        self.assertIn(
            "def rank_candidates(action: dict[str, Any], *, company_code: str | None = None)",
            app,
        )
        self.assertIn(
            "def candidate_cv_evaluation(action: dict[str, Any], *, company_code: str | None = None)",
            app,
        )
        self.assertIn(
            "def compare_candidates(action: dict[str, Any], *, company_code: str | None = None)",
            app,
        )
        self.assertNotIn('application.get("company_code") or "WATHEFNI"', app)
        self.assertNotIn('interview.get("company_code") or "WATHEFNI"', app)

    def test_interview_and_hire_contracts_are_explicit(self) -> None:
        registry = self.source("action_registry.py")
        lifecycle_source = self.source("recruiting_lifecycle.py")
        hire = self.source("hire_operations.py")
        self.assertIn("create_candidate_interview_from_schedule", registry)
        self.assertIn("calendar_event_id", registry)
        self.assertIn("interview_lifecycle_consistency_report", lifecycle_source)
        self.assertIn("status IN ('prepared','processing')", hire)
        self.assertIn("hire_operation_in_progress", hire)
        self.assertIn("employees_company_app_key_uq", hire)
        self.assertIn("transactional_side_effect=_employee_transaction", hire)

    def test_dashboard_has_bilingual_consequence_copy(self) -> None:
        source_path = self.ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "App.tsx"
        if source_path.exists():
            source = source_path.read_text(encoding="utf-8")
        else:
            dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST", "/opt/wathefni/staging/dashboard-dist"))
            source = "\n".join(
                asset.read_text(encoding="utf-8")
                for asset in sorted((dist / "assets").glob("*.js"))
            )
        self.assertIn("Hire this candidate?", source)
        self.assertIn("توظيف هذا المرشح؟", source)
        self.assertIn("Reject this candidate?", source)
        self.assertIn("رفض هذا المرشح؟", source)


if __name__ == "__main__":
    unittest.main()
