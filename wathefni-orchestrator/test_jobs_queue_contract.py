"""Regression: Jobs applicant-count + status-alias contract."""

from __future__ import annotations

import unittest

import jobs_queue_contract as contract
import prehire_jobs as jobs
import prehire_overview as overview


class JobsQueueContractTests(unittest.TestCase):
    def test_status_aliases_normalize(self) -> None:
        self.assertEqual(contract.normalize_job_status("active"), "open")
        self.assertEqual(contract.normalize_job_status("published"), "open")
        self.assertEqual(contract.normalize_job_status("inactive"), "closed")
        self.assertEqual(contract.normalize_job_status("OPEN"), "open")
        self.assertEqual(contract.normalize_job_status("paused"), "paused")
        self.assertEqual(contract.normalize_job_status("draft"), "draft")
        self.assertEqual(contract.normalize_job_status("closed"), "closed")
        self.assertEqual(contract.normalize_job_status(""), "open")
        self.assertEqual(contract.normalize_job_status("mystery"), "closed")

    def test_prehire_jobs_normalize_delegates(self) -> None:
        self.assertEqual(jobs.normalize_status("published"), "open")
        self.assertEqual(jobs.normalize_status("inactive"), "closed")
        self.assertEqual(jobs.normalize_status("active"), "open")

    def test_status_filter_coercion(self) -> None:
        self.assertEqual(contract.coerce_job_status_filter("published"), "open")
        self.assertEqual(contract.coerce_job_status_filter("inactive"), "closed")
        self.assertEqual(contract.coerce_job_status_filter("all"), "")
        self.assertEqual(contract.coerce_job_status_filter("bogus"), "")

    def test_lifecycle_reopen_unchanged(self) -> None:
        self.assertEqual(jobs.assert_transition("closed", "open"), "reopen")
        self.assertEqual(jobs.assert_transition("open", "closed"), "close")
        self.assertEqual(jobs.assert_transition("paused", "open"), "resume")

    def test_active_pipeline_excludes_terminals(self) -> None:
        for status in ("hired", "rejected", "withdrawn", "archived"):
            self.assertFalse(contract.is_active_pipeline_status(status), status)
        for status in ("ready_for_review", "shortlisted", "interview", "screening"):
            self.assertTrue(contract.is_active_pipeline_status(status), status)

    def test_role_active_matches_active_pipeline(self) -> None:
        self.assertEqual(
            overview.role_active_predicate("a"),
            contract.active_pipeline_predicate("a"),
        )
        predicate = contract.active_pipeline_predicate("a")
        self.assertIn("'hired'", predicate)
        self.assertIn("'rejected'", predicate)
        self.assertIn("'withdrawn'", predicate)
        self.assertIn("'archived'", predicate)

    def test_active_pipeline_sql_fragment(self) -> None:
        sql = contract.active_pipeline_status_filter_sql("status")
        self.assertEqual(
            sql,
            "status NOT IN ('hired', 'rejected', 'withdrawn', 'archived')",
        )

    def test_effective_status_sql_covers_aliases(self) -> None:
        sql = contract.effective_job_status_sql("p.status")
        self.assertIn("'active'", sql)
        self.assertIn("'published'", sql)
        self.assertIn("'inactive'", sql)
        self.assertIn("'open'", sql)
        self.assertIn("'closed'", sql)

    def test_serialize_job_uses_normalized_aliases(self) -> None:
        for raw, expected in (
            ("published", "open"),
            ("active", "open"),
            ("inactive", "closed"),
            ("open", "open"),
        ):
            payload = jobs.serialize_job(
                {
                    "position_code": "ALIAS",
                    "title": "Alias Role",
                    "status": raw,
                    "application_count": 2,
                    "active_count": 0,
                }
            )
            self.assertEqual(payload["status"], expected, raw)
            self.assertEqual(payload["application_count"], 2)
            self.assertEqual(payload["active_count"], 0)

    def test_pipeline_count_semantics_hired_rejected_withdrawn_archived(self) -> None:
        """Badge / close confirm / View candidates share active_pipeline semantics."""
        rows = [
            {"status": "ready_for_review"},
            {"status": "hired"},
            {"status": "rejected"},
            {"status": "withdrawn"},
            {"status": "archived"},
            {"status": "shortlisted"},
        ]
        total = len(rows)
        active = sum(1 for row in rows if contract.is_active_pipeline_status(row["status"]))
        self.assertEqual(total, 6)
        self.assertEqual(active, 2)

        # Prove the three live-job shapes from the audit.
        it_maintenance = [{"status": "hired"}]
        marketing = [{"status": "rejected"}]
        social = [{"status": "withdrawn"}, {"status": "ready_for_review"}]
        self.assertEqual(
            sum(1 for r in it_maintenance if contract.is_active_pipeline_status(r["status"])),
            0,
        )
        self.assertEqual(
            sum(1 for r in marketing if contract.is_active_pipeline_status(r["status"])),
            0,
        )
        self.assertEqual(
            sum(1 for r in social if contract.is_active_pipeline_status(r["status"])),
            1,
        )


if __name__ == "__main__":
    unittest.main()
