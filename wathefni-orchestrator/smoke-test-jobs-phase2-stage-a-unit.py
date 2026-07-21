#!/usr/bin/env python3
"""Fast, database-free checks for Jobs Phase 2 Stage A authority contracts."""

from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timezone

try:
    from psycopg2.extras import Json as _Json  # noqa: F401
except ModuleNotFoundError:
    psycopg2 = types.ModuleType("psycopg2")
    extras = types.ModuleType("psycopg2.extras")
    extras.Json = lambda value: value
    psycopg2.extras = extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = extras

import prehire_jobs as jobs


class JobsPhase2StageAUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_number = os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER")
        os.environ["WATHEFNI_APPLY_WHATSAPP_NUMBER"] = "96599338566"

    def tearDown(self) -> None:
        if self._old_number is None:
            os.environ.pop("WATHEFNI_APPLY_WHATSAPP_NUMBER", None)
        else:
            os.environ["WATHEFNI_APPLY_WHATSAPP_NUMBER"] = self._old_number

    def row(self, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "company_code": "WATHEFNI",
            "company_display_name": "Wathefni",
            "position_code": "IT-MANAGER",
            "apply_code": "APPLY-WATHEFNI-IT-MANAGER",
            "status": "open",
            "visibility": "public",
            "title": "IT Manager",
            "title_en": "IT Manager",
            "short_summary_en": "Lead the company technology function.",
            "requirements_en": ["Technology leadership experience"],
            "content_approved_en_at": datetime(2026, 7, 21, tzinfo=timezone.utc),
            "location": "Kuwait City",
            "employment_type": "full_time",
            "work_arrangement": "onsite",
            "vacancies": 1,
            "salary_visibility": "hr_only",
            "application_deadline": None,
        }
        row.update(overrides)
        return row

    def test_hyphenated_apply_code_is_captured_whole(self) -> None:
        self.assertEqual(
            jobs.extract_apply_code("Please send APPLY-WATHEFNI-IT-MANAGER"),
            "APPLY-WATHEFNI-IT-MANAGER",
        )
        self.assertEqual(
            jobs.extract_apply_code("APPLY\u2013WATHEFNI\u2013IT\u2013MANAGER"),
            "APPLY-WATHEFNI-IT-MANAGER",
        )

    def test_publish_requires_location_or_fully_remote(self) -> None:
        row = self.row(location="", work_arrangement="hybrid")
        self.assertIn("location_or_fully_remote", jobs.publish_blockers(row))
        remote = self.row(location="", work_arrangement="fully_remote")
        self.assertNotIn("location_or_fully_remote", jobs.publish_blockers(remote))

    def test_publish_requires_approved_language_pack(self) -> None:
        row = self.row(content_approved_en_at=None)
        self.assertIn("approved_language_pack", jobs.publish_blockers(row))
        with self.assertRaises(jobs.JobsError) as caught:
            jobs.assert_job_publishable(row)
        self.assertEqual(caught.exception.code, "job_not_publishable")

    def test_eligibility_is_fail_closed(self) -> None:
        vacancy = {"remaining_vacancies": 1}
        self.assertTrue(jobs.job_eligibility_snapshot(self.row(), vacancy=vacancy)["eligible"])
        self.assertEqual(
            jobs.job_eligibility_snapshot(self.row(status=None), vacancy=vacancy)["reason"],
            "job_not_accepting",
        )
        self.assertEqual(
            jobs.job_eligibility_snapshot(self.row(visibility="share_only"), vacancy=vacancy, access_mode="discovery")["reason"],
            "job_visibility_denied",
        )
        self.assertTrue(
            jobs.job_eligibility_snapshot(self.row(visibility="share_only"), vacancy=vacancy, access_mode="exact_token")["eligible"]
        )
        self.assertEqual(
            jobs.job_eligibility_snapshot(self.row(), vacancy={"remaining_vacancies": 0})["reason"],
            "job_vacancies_exhausted",
        )

    def test_deadline_is_inclusive_in_tenant_timezone(self) -> None:
        row = self.row(application_deadline="2026-07-21")
        before_midnight = datetime(2026, 7, 21, 20, 59, tzinfo=timezone.utc)
        after_midnight = datetime(2026, 7, 21, 21, 1, tzinfo=timezone.utc)
        self.assertTrue(
            jobs.job_eligibility_snapshot(row, vacancy={"remaining_vacancies": 1}, now=before_midnight)["eligible"]
        )
        self.assertEqual(
            jobs.job_eligibility_snapshot(row, vacancy={"remaining_vacancies": 1}, now=after_midnight)["reason"],
            "job_deadline_passed",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
