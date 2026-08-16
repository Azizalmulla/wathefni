"""Regression: Candidates stage-bucket contract."""

from __future__ import annotations

import unittest

import candidates_stage_contract as contract


class CandidatesStageContractTests(unittest.TestCase):
    def test_new_excludes_talent_pool_intake(self) -> None:
        statuses = contract.expand_stage_filter_statuses("awaiting_cv")
        self.assertEqual(
            statuses,
            [
                "awaiting_cv",
                "cv_processing",
                "cv_received",
                "screening",
                "cv_request",
                "cv_upload",
            ],
        )
        self.assertNotIn("needs_role", statuses)
        self.assertNotIn("import_review", statuses)

    def test_shortlisted_includes_legacy_offer(self) -> None:
        statuses = contract.expand_stage_filter_statuses("shortlisted")
        self.assertEqual(statuses, ["shortlisted", "offered", "offer_sent"])
        self.assertEqual(contract.expand_stage_filter_statuses("offer_sent"), statuses)
        self.assertEqual(contract.expand_stage_filter_statuses("offered"), statuses)

    def test_talent_pool_display_is_none_not_new(self) -> None:
        for status in ("needs_role", "import_review"):
            row = {"status": status, "record_state": "talent_pool", "canonical_stage": status}
            self.assertEqual(contract.display_stage_bucket(row), contract.STAGE_BUCKET_NONE)
            self.assertNotEqual(contract.display_stage_bucket(row), contract.STAGE_BUCKET_NEW)

    def test_offer_display_is_shortlisted(self) -> None:
        self.assertEqual(
            contract.display_stage_bucket({"status": "offer_sent", "canonical_stage": None}),
            contract.STAGE_BUCKET_SHORTLISTED,
        )
        self.assertEqual(
            contract.display_stage_bucket({"status": "offered", "canonical_stage": "shortlisted"}),
            contract.STAGE_BUCKET_SHORTLISTED,
        )

    def test_unknown_not_silently_new(self) -> None:
        self.assertEqual(
            contract.display_stage_bucket({"status": "mystery_legacy", "canonical_stage": None}),
            contract.STAGE_BUCKET_UNKNOWN,
        )

    def test_lifecycle_buckets_unchanged(self) -> None:
        self.assertEqual(contract.lifecycle_bucket_for_status("screening"), contract.STAGE_BUCKET_NEW)
        self.assertEqual(
            contract.lifecycle_bucket_for_status("screening_complete"),
            contract.STAGE_BUCKET_READY,
        )
        self.assertEqual(contract.lifecycle_bucket_for_status("scheduled"), contract.STAGE_BUCKET_INTERVIEW)
        self.assertEqual(contract.lifecycle_bucket_for_status("hired"), contract.STAGE_BUCKET_HIRED)


if __name__ == "__main__":
    unittest.main()
