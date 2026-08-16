"""Unit tests for Reports correctness contract (reports-contract-v2)."""

from __future__ import annotations

import unittest

import candidates_stage_contract as stages
import reports_metrics as rm


class ReportsMetricsContractTests(unittest.TestCase):
    def test_stage_buckets_drop_held_and_merge_legacy_offer(self):
        rows = [
            {"status": "needs_role", "count": 2},
            {"status": "import_review", "count": 1},
            {"status": "offered", "count": 2},
            {"status": "offer_sent", "count": 1},
            {"status": "shortlisted", "count": 1},
            {"status": "ready_for_review", "count": 2},
            {"status": "screening_complete", "count": 1},
        ]
        merged = rm.merge_stage_breakdown(rows, locale="en")
        labels = {row["label"]: row["count"] for row in merged}
        self.assertNotIn("Needs role", labels)
        self.assertEqual(labels.get("Shortlisted"), 4)
        self.assertEqual(labels.get("Ready for review"), 3)
        self.assertTrue(all(row.get("key") != stages.STAGE_BUCKET_NONE for row in merged))

    def test_stage_ar_labels(self):
        rows = [{"status": "hired", "count": 1}]
        merged = rm.merge_stage_breakdown(rows, locale="ar")
        self.assertEqual(merged[0]["label"], "تم التعيين")

    def test_assessment_labels_never_raw(self):
        labeled = rm.label_assessment_status("pending", locale="en")
        self.assertEqual(labeled["label"], "Sent pending")
        self.assertNotEqual(labeled["label"], "pending")
        labeled_ar = rm.label_assessment_status("completed", locale="ar")
        self.assertEqual(labeled_ar["label"], "مكتمل")

    def test_interview_alias_normalization(self):
        labeled = rm.label_interview_status("noshow", locale="en")
        self.assertEqual(labeled["key"], "no_show")
        self.assertEqual(labeled["label"], "No-show")
        canceled = rm.label_interview_status("canceled", locale="en")
        self.assertEqual(canceled["key"], "cancelled")

    def test_talent_pool_record_state_omitted(self):
        self.assertIsNone(rm.stage_bucket_for_row("screening", "talent_pool"))
        self.assertEqual(rm.stage_bucket_for_row("shortlisted", None), stages.STAGE_BUCKET_SHORTLISTED)


if __name__ == "__main__":
    unittest.main()
