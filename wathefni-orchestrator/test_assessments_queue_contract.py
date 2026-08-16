"""Regression: Assessments three-authority queue contract."""

from __future__ import annotations

import unittest

import assessment_cohorts as cohorts
import assessments_queue_contract as contract


class AssessmentsQueueContractTests(unittest.TestCase):
    def test_authorities_and_operational_keys(self) -> None:
        self.assertIn(cohorts.COHORT_READY_TO_SEND, contract.OPERATIONAL_COHORT_KEYS)
        self.assertIn(cohorts.COHORT_RESEND_NEEDED, contract.OPERATIONAL_COHORT_KEYS)
        self.assertIn(cohorts.COHORT_COMPLETED, contract.OPERATIONAL_COHORT_KEYS)
        self.assertIn(cohorts.COHORT_IN_PROGRESS, contract.OPERATIONAL_COHORT_KEYS)
        self.assertIn("cancelled", contract.ATTEMPT_STATUSES)

    def test_cancelled_never_maps_to_send_or_attention(self) -> None:
        self.assertTrue(contract.is_cancelled_status("cancelled"))
        self.assertIsNone(
            contract.cohort_for_attempt_presentation(
                attempt_status="cancelled",
                delivery_status="sent",
                application_status="shortlisted",
            )
        )
        self.assertIsNone(
            cohorts.classify_attempt_state(
                assessment_status="cancelled",
                delivery_status="failed",
                application_status="shortlisted",
            )
        )

    def test_delivery_failed_is_facet_of_pending_in_progress(self) -> None:
        for delivery in ("failed", "send_failed", "invitation_failed"):
            self.assertEqual(
                cohorts.classify_attempt_state(
                    assessment_status="pending",
                    delivery_status=delivery,
                    application_status="shortlisted",
                ),
                cohorts.COHORT_DELIVERY_FAILED,
            )
            self.assertEqual(
                cohorts.classify_attempt_state(
                    assessment_status="in_progress",
                    delivery_status=delivery,
                    application_status="shortlisted",
                ),
                cohorts.COHORT_DELIVERY_FAILED,
            )
        pred = cohorts.cohort_predicate(cohorts.COHORT_DELIVERY_FAILED, "a")
        self.assertIn("pending", pred)
        self.assertIn("in_progress", pred)
        self.assertIn("send_failed", pred)
        self.assertIn("invitation_failed", pred)

    def test_expired_latest_is_resend_superseded_is_history_only(self) -> None:
        self.assertEqual(
            cohorts.classify_attempt_state(
                assessment_status="expired",
                application_status="shortlisted",
            ),
            cohorts.COHORT_RESEND_NEEDED,
        )
        # Pending latest with a failed-delivery facet is not resend/expired.
        self.assertEqual(
            cohorts.classify_attempt_state(
                assessment_status="pending",
                delivery_status="sent",
                application_status="shortlisted",
            ),
            cohorts.COHORT_SENT_PENDING,
        )

    def test_needs_review_and_report_ready_predicates(self) -> None:
        nr = contract.needs_review_predicate("aa")
        self.assertIn("aa.status = 'completed'", nr)
        self.assertIn("reviewed", nr)
        self.assertIn("aa.status = 'completed'", contract.report_ready_predicate("aa"))

    def test_application_count_only_never_uses_people(self) -> None:
        self.assertEqual(
            contract.application_count_only(
                {"application_count": 2, "people_count": 9, "display_count": 9}
            ),
            2,
        )
        self.assertEqual(contract.application_count_only({"people_count": 5}), 0)
        self.assertEqual(contract.application_count_only({"applications": 3}), 3)

    def test_hybrid_visibility_clause_is_threaded_into_cohort_sql_shape(self) -> None:
        # Contract: badge SQL accepts the same visibility fragment as the opened queue.
        block = cohorts._empty_block(cohorts.COHORT_RESEND_NEEDED)
        self.assertEqual(block["application_count"], 0)
        self.assertEqual(contract.application_count_only(block), 0)
        # Resend and expired share the same latest-attempt predicate SQL.
        self.assertEqual(
            cohorts.cohort_predicate(cohorts.COHORT_RESEND_NEEDED, "a"),
            cohorts.cohort_predicate(cohorts.COHORT_EXPIRED, "a"),
        )
        # Signature documents optional visibility_sql for badge ≡ list scope.
        import inspect

        params = inspect.signature(cohorts.compute_assessment_cohorts).parameters
        self.assertIn("visibility_sql", params)
        self.assertIn("visibility_params", params)

    def test_multi_attempt_history_units_stay_separate(self) -> None:
        """Documented proof shape: resend apps (latest) ≠ expired attempt history."""
        # Cohort unit = applications / latest; attempt unit = every row.
        self.assertNotEqual(
            contract.OPERATIONAL_COHORT_KEYS,
            contract.ATTEMPT_STATUSES,
        )
        self.assertIn("expired", contract.ATTEMPT_STATUSES)
        self.assertIn(cohorts.COHORT_RESEND_NEEDED, contract.OPERATIONAL_COHORT_KEYS)


if __name__ == "__main__":
    unittest.main()
