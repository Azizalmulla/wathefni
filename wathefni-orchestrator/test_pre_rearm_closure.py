from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import inbound_retention_policy as retention
import talent_pool_classification as classification


ROOT = Path(__file__).resolve().parent


class RetentionPolicyTests(unittest.TestCase):
    def test_owner_defaults_are_explicit_and_versioned(self) -> None:
        env = {
            "WATHEFNI_INTAKE_RETENTION_POLICY_VERSION": "inbound-retention-ops-v1",
            "WATHEFNI_INTAKE_RETENTION_CLEAN_DAYS": "30",
            "WATHEFNI_INTAKE_RETENTION_NONCLEAN_DAYS": "90",
            "WATHEFNI_INTAKE_RETENTION_RESOLVED_REVIEW_DAYS": "90",
            "WATHEFNI_INTAKE_RETENTION_WITHDRAWN_HELD_DAYS": "90",
            "WATHEFNI_INTAKE_RETENTION_AUDIT_YEARS": "7",
            "WATHEFNI_INTAKE_RETENTION_CORRECTION_AUDIT_YEARS": "7",
            "WATHEFNI_INTAKE_SCAN_REUSE_HOURS": "168",
            "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS": "86400",
        }
        policy = retention.policy_from_env("WATHEFNI", env)
        self.assertEqual(policy.policy_version, "inbound-retention-ops-v1")
        self.assertEqual(policy.clean_quarantine_days, 30)
        self.assertEqual(policy.nonclean_quarantine_days, 90)
        self.assertEqual(policy.audit_years, 7)
        self.assertEqual(policy.clean_scan_reuse_hours, 168)
        self.assertEqual(policy.orphan_grace_seconds, 86400)

    def test_unset_or_invalid_policy_fails_closed(self) -> None:
        with self.assertRaises(retention.RetentionPolicyError):
            retention.policy_from_env("WATHEFNI", {})
        env = {
            name: "1" for name in retention.POLICY_ENV.values()
        }
        env["WATHEFNI_INTAKE_RETENTION_POLICY_VERSION"] = "invalid version"
        env["WATHEFNI_INTAKE_SCAN_REUSE_HOURS"] = "168"
        env["WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS"] = "86400"
        with self.assertRaises(retention.RetentionPolicyError):
            retention.policy_from_env("WATHEFNI", env)

    def test_cleanup_is_dry_run_by_default(self) -> None:
        self.assertTrue(
            retention.execute_cleanup.__kwdefaults__["dry_run"]  # type: ignore[index]
        )
        policy = retention.RetentionPolicy(
            "WATHEFNI", "v1", 30, 90, 90, 90, 7, 7, 168, 86400
        )
        now = datetime.now(timezone.utc)
        self.assertEqual(
            retention._eligibility({"legal_hold": True}, policy, now)[1],
            "legal_hold",
        )
        self.assertEqual(
            retention._eligibility(
                {"review_status": "open"}, policy, now
            )[1],
            "identity_review_open",
        )
        withdrawn = (now - timedelta(days=91)).isoformat()
        self.assertEqual(
            retention._eligibility(
                {
                    "metadata": {"withdrawn_at": withdrawn},
                    "app_status": "needs_role",
                    "position_code": None,
                },
                policy,
                now,
            )[:2],
            (True, "withdrawn_or_deleted_held_source"),
        )
        self.assertEqual(
            retention._eligibility(
                {
                    "metadata": {"withdrawn_at": withdrawn},
                    "app_status": "shortlisted",
                    "position_code": "JOB-1",
                },
                policy,
                now,
            )[1],
            "withdrawn_source_not_held",
        )


class NativeInvalidationTests(unittest.TestCase):
    def test_profile_excludes_invalidated_run_but_keeps_audit(self) -> None:
        run_id = "00000000-0000-0000-0000-000000000001"
        invalidation = {
            "invalidation_id": "00000000-0000-0000-0000-000000000002",
            "run_id": run_id,
            "reason_code": "identity_misbinding",
            "invalidated_by": "test-authority",
            "created_at": "2026-07-26T00:00:00+00:00",
        }
        section = classification.profile_classification_section(
            run={"run_id": run_id, "status": "classified"},
            suggestions=[
                {
                    "run_id": run_id,
                    "node_id": "fn.technology",
                    "node_type": "career_function",
                    "confidence_band": "High",
                    "state": "active",
                    "evidence": [{"quote": "test"}],
                }
            ],
            review_events=[],
            runs=[{"run_id": run_id, "status": "classified"}],
            invalidations=[invalidation],
        )
        self.assertEqual(section["ai_suggested"], [])
        self.assertIsNone(section["chip"])
        self.assertIsNone(section["current_run"])
        self.assertEqual(section["currency"], "unclassified")
        self.assertEqual(section["runs"][0]["currency"], "invalidated")
        self.assertEqual(
            section["runs"][0]["invalidations"][0]["reason_code"],
            "identity_misbinding",
        )

    def test_filter_sql_excludes_invalidated_runs(self) -> None:
        sql, _ = classification.classification_filter_sql(
            company_code="WATHEFNI",
            filters={"classification_confidence": "High"},
        )
        self.assertIn("candidate_classification_run_invalidations", sql)

    def test_dashboard_shows_invalidation_audit(self) -> None:
        source = (
            ROOT.parent
            / "apps"
            / "wathefni-dashboard"
            / "src"
            / "components"
            / "candidates"
            / "CandidateClassificationSection.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("Invalidated:", source)
        self.assertIn("invalidation.invalidated_by", source)
        self.assertIn("invalidation.created_at", source)


class ExistingCvTimerAuthorityTests(unittest.TestCase):
    def test_inbound_candidate_document_requires_all_authority_provenance(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        start = source.index("def process_candidate_cv_document")
        end = source.index("def run_candidate_cv_processing_worker")
        worker = source[start:end]
        self.assertIn("authority_intake_document_id", worker)
        self.assertIn("inbound_email_authority_provenance_missing", worker)
        self.assertIn("_inbound_cv_authority.binding_is_authorized", worker)
        self.assertLess(
            worker.index("_inbound_cv_authority.binding_is_authorized"),
            worker.index("extract_candidate_cv_document"),
        )


if __name__ == "__main__":
    unittest.main()
