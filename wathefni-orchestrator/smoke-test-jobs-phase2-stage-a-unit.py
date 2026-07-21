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

    def test_share_surfaces_follow_backend_shareability(self) -> None:
        vacancy = {"remaining_vacancies": 1}
        public = jobs.serialize_job(self.row(visibility="public"), vacancy=vacancy, include_salary=False)
        self.assertTrue(public["shareable"])
        self.assertTrue(public["accepts_applications"])
        self.assertTrue(str(public["application_link"] or "").startswith("https://wa.me/"))
        self.assertEqual(public["qr_value"], public["application_link"])

        share_only = jobs.serialize_job(self.row(visibility="share_only"), vacancy=vacancy, include_salary=False)
        self.assertTrue(share_only["shareable"])
        self.assertTrue(str(share_only["application_link"] or "").startswith("https://wa.me/"))

        internal = jobs.serialize_job(self.row(visibility="internal"), vacancy=vacancy, include_salary=False)
        self.assertFalse(internal["shareable"])
        self.assertFalse(internal["accepts_applications"])
        self.assertEqual(internal["eligibility_reason"], "job_visibility_denied")
        self.assertIsNone(internal["application_link"])
        self.assertIsNone(internal["qr_value"])
        self.assertEqual(internal["apply_code"], "APPLY-WATHEFNI-IT-MANAGER")

        for status, reason in (
            ("draft", "job_not_accepting"),
            ("paused", "job_paused"),
            ("closed", "job_closed"),
        ):
            blocked = jobs.serialize_job(self.row(status=status), vacancy=vacancy, include_salary=False)
            self.assertFalse(blocked["shareable"], status)
            self.assertIsNone(blocked["application_link"], status)
            self.assertEqual(blocked["eligibility_reason"], reason, status)

        expired_share = jobs.job_shareability_snapshot(
            self.row(application_deadline="2026-07-20"),
            vacancy=vacancy,
            now=datetime(2026, 7, 21, 21, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(expired_share["shareable"])
        self.assertEqual(expired_share["reason"], "job_deadline_passed")
        expired_fields = jobs.assistant_external_share_fields(
            self.row(application_deadline="2026-07-20"),
            vacancy=vacancy,
            now=datetime(2026, 7, 21, 21, 1, tzinfo=timezone.utc),
        )
        self.assertIsNone(expired_fields["application_link"])

        full = jobs.serialize_job(self.row(), vacancy={"remaining_vacancies": 0}, include_salary=False)
        self.assertFalse(full["shareable"])
        self.assertEqual(full["eligibility_reason"], "job_vacancies_exhausted")
        self.assertIsNone(full["application_link"])

        incomplete = jobs.serialize_job(
            self.row(content_approved_en_at=None, short_summary_en=""),
            vacancy=vacancy,
            include_salary=False,
        )
        self.assertFalse(incomplete["shareable"])
        self.assertEqual(incomplete["eligibility_reason"], "job_content_incomplete")
        self.assertIsNone(incomplete["qr_value"])

    def test_assistant_cannot_share_blocked_cases(self) -> None:
        vacancy = {"remaining_vacancies": 1}
        for overrides in (
            {"visibility": "internal"},
            {"status": "draft"},
            {"status": "paused"},
            {"status": "closed"},
            {"application_deadline": "2020-01-01"},
        ):
            row = self.row(**overrides)
            share = jobs.assistant_external_share_fields(row, vacancy=vacancy)
            self.assertFalse(share["shareable"], overrides)
            self.assertIsNone(share["apply_link"], overrides)
            self.assertIsNone(share["application_link"], overrides)
            self.assertIsNone(share["qr_value"], overrides)
            self.assertIsNone(share["qr_image_url"], overrides)
            # Stable APPLY identity may remain for internal inspection.
            self.assertEqual(share["apply_code"], "APPLY-WATHEFNI-IT-MANAGER")

        open_share = jobs.assistant_external_share_fields(self.row(), vacancy=vacancy)
        self.assertTrue(open_share["shareable"])
        self.assertTrue(str(open_share["apply_link"] or "").startswith("https://wa.me/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
