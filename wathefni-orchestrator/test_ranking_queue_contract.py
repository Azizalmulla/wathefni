"""Regression: Ranking matching / rankable / eligible / top_n contract."""

from __future__ import annotations

import unittest

import ranking_queue_contract as contract
from candidate_ranking import (
    assessment_pool_lateral_sql,
    effective_assessment_mode,
    DEFAULT_EVIDENCE_POLICY,
)


class RankingQueueContractTests(unittest.TestCase):
    def test_matching_excludes_archived_and_terminals(self) -> None:
        sql = contract.matching_lifecycle_predicate("a")
        for status in ("hired", "rejected", "withdrawn", "archived"):
            self.assertIn(f"'{status}'", sql)

    def test_rankable_includes_not_applicable_not_hard_eligible(self) -> None:
        eligible = {"eligibility_bucket": "eligible", "required_evidence_complete": True}
        na = {"eligibility_bucket": "not_applicable", "required_evidence_complete": True}
        not_met = {"eligibility_bucket": "requirement_not_met", "required_evidence_complete": True}
        unknown = {"eligibility_bucket": "insufficient_information", "required_evidence_complete": False}
        self.assertTrue(contract.is_rankable_item(eligible))
        self.assertTrue(contract.is_rankable_item(na))
        self.assertFalse(contract.is_rankable_item(not_met))
        self.assertFalse(contract.is_rankable_item(unknown))
        self.assertEqual(contract.reconcile_pool_counters([eligible]).get("eligible_count"), 1)
        self.assertEqual(contract.reconcile_pool_counters([na]).get("eligible_count"), 0)
        self.assertEqual(contract.reconcile_pool_counters([na]).get("rankable_count"), 1)

    def test_counters_reconcile_including_not_applicable(self) -> None:
        items = [
            {"eligibility_bucket": "eligible", "required_evidence_complete": True},
            {"eligibility_bucket": "not_applicable", "required_evidence_complete": True},
            {"eligibility_bucket": "requirement_not_met", "required_evidence_complete": True},
            {"eligibility_bucket": "insufficient_information", "required_evidence_complete": False},
        ]
        counters = contract.reconcile_pool_counters(items)
        self.assertTrue(counters["reconciles"])
        self.assertEqual(counters["matching_count"], 4)
        self.assertEqual(counters["rankable_count"], 2)
        self.assertEqual(counters["eligible_count"], 1)
        self.assertEqual(counters["not_applicable_count"], 1)
        self.assertEqual(counters["not_met_count"], 1)
        self.assertEqual(counters["unknown_count"], 1)

    def test_restricted_held_not_rankable_but_counted(self) -> None:
        item = {
            "eligibility_bucket": "insufficient_information",
            "required_evidence_complete": False,
            "required_missing": ["ck_ranking_denied:held"],
            "ck_ranking_reader": {"active": True, "eligible": False, "denial_reason": "held"},
        }
        self.assertTrue(contract.is_restricted_held(item))
        self.assertFalse(contract.is_rankable_item(item))
        counters = contract.reconcile_pool_counters([item])
        self.assertEqual(counters["restricted_held_count"], 1)
        self.assertTrue(counters["reconciles"])

    def test_top_n_never_fills_with_unrankable(self) -> None:
        items = [
            {"eligibility_bucket": "requirement_not_met", "required_evidence_complete": True, "app_key": "bad1"},
            {"eligibility_bucket": "eligible", "required_evidence_complete": True, "app_key": "good1"},
            {"eligibility_bucket": "insufficient_information", "required_evidence_complete": False, "app_key": "bad2"},
            {"eligibility_bucket": "not_applicable", "required_evidence_complete": True, "app_key": "good2"},
        ]
        top = contract.top_n_rankable(items, 10)
        self.assertEqual([i["app_key"] for i in top], ["good1", "good2"])
        top1 = contract.top_n_rankable(items, 1)
        self.assertEqual([i["app_key"] for i in top1], ["good1"])

    def test_assessment_default_unused_and_lateral_null_without_selection(self) -> None:
        self.assertEqual(DEFAULT_EVIDENCE_POLICY["sources"]["assessment"], "unused")
        mode, selection = effective_assessment_mode(DEFAULT_EVIDENCE_POLICY, assessments_module_enabled=True)
        self.assertEqual(mode, "unused")
        self.assertIsNone(selection)
        sql = assessment_pool_lateral_sql(None)
        self.assertIn("NULL::text AS assessment_status", sql)
        self.assertNotIn("ORDER BY aa.updated_at DESC, aa.created_at DESC", sql)

    def test_assessment_lateral_uses_matching_selection_not_latest_any(self) -> None:
        selection = {
            "battery_key": "bat1",
            "assessment_version_id": "11111111-1111-1111-1111-111111111111",
            "norm_version": "n1",
            "attempt_selection_rule": "latest_matching_battery_version",
            "approved_by_user_id": "u1",
            "approved_at": "2026-01-01T00:00:00Z",
            "policy_version": "1",
        }
        sql = assessment_pool_lateral_sql(selection)
        self.assertIn("aa.battery_key=", sql)
        self.assertIn("aa.status='completed'", sql)
        self.assertIn("ORDER BY aa.completed_at DESC", sql)
        # Must not use unconstrained latest-any ordering alone.
        self.assertNotIn(
            "ORDER BY aa.updated_at DESC, aa.created_at DESC\n                  LIMIT 1\n                ) latest_assessment",
            sql,
        )

    def test_visibility_clause_signature_documented(self) -> None:
        import inspect
        import candidate_ranking as cr

        params = inspect.signature(cr.load_job_application_pool).parameters
        self.assertIn("visibility_sql", params)
        self.assertIn("assessment_selection", params)


if __name__ == "__main__":
    unittest.main()
