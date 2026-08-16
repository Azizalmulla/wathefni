"""Contract: Candidates Stage filter accepts comma-separated display-bucket aliases."""

from __future__ import annotations

import unittest

import app as app_mod


class PrehireStageFilterContractTests(unittest.TestCase):
    def test_single_status_unchanged(self) -> None:
        where: list[str] = []
        params: list = []
        app_mod._append_prehire_application_status_filter(where, params, "shortlisted")
        self.assertEqual(where, ["a.status=%s"])
        self.assertEqual(params, ["shortlisted"])

    def test_comma_separated_uses_any(self) -> None:
        where: list[str] = []
        params: list = []
        app_mod._append_prehire_application_status_filter(
            where,
            params,
            "awaiting_cv,cv_processing,screening,cv_received,cv_request,cv_upload",
        )
        self.assertEqual(where, ["a.status = ANY(%s)"])
        self.assertEqual(
            params,
            [["awaiting_cv", "cv_processing", "screening", "cv_received", "cv_request", "cv_upload"]],
        )

    def test_empty_status_is_noop(self) -> None:
        where: list[str] = ["a.company_code=%s"]
        params: list = ["WATHEFNI"]
        app_mod._append_prehire_application_status_filter(where, params, "")
        self.assertEqual(where, ["a.company_code=%s"])
        self.assertEqual(params, ["WATHEFNI"])

    def test_shortlisted_expands_with_legacy_offer_aliases(self) -> None:
        where: list[str] = []
        params: list = []
        app_mod._append_prehire_application_status_filter(
            where,
            params,
            "shortlisted,offered,offer_sent",
        )
        self.assertEqual(where, ["a.status = ANY(%s)"])
        self.assertEqual(params, [["shortlisted", "offered", "offer_sent"]])


if __name__ == "__main__":
    unittest.main()
