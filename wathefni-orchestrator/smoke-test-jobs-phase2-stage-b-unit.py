#!/usr/bin/env python3
"""Database-free Stage B contract checks (confirm parse, public canary gate)."""

from __future__ import annotations

import os
import unittest

import jobs_phase2_stage_b as stage_b


class JobsPhase2StageBUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {
            key: os.environ.get(key)
            for key in (
                "WATHEFNI_STAGE_B_ENABLED",
                "WATHEFNI_STAGE_B_CANARY_ONLY",
                "WATHEFNI_STAGE_B_PUBLIC_POSITIONS",
                "WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES",
                "WATHEFNI_STAGE_B_LIVE_WHATSAPP",
                "WATHEFNI_STAGE_B_STAMP_DRY_RUN",
                "WATHEFNI_STAGE_B_CANDIDATE_ALLOWLIST",
            )
        }

    def tearDown(self) -> None:
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_confirm_phrases(self) -> None:
        self.assertTrue(stage_b.parse_apply_confirm("ready to apply"))
        self.assertTrue(stage_b.parse_apply_confirm("Yes, apply"))
        self.assertTrue(stage_b.parse_apply_confirm("I want to apply now"))
        self.assertTrue(stage_b.parse_apply_confirm("جاهز للتقديم"))
        self.assertTrue(stage_b.parse_apply_confirm("أريد التقديم"))
        self.assertFalse(stage_b.parse_apply_confirm("what is the salary?"))
        self.assertFalse(stage_b.parse_apply_confirm("APPLY-WATHEFNI-FOO"))

    def test_public_canary_job_gate(self) -> None:
        os.environ["WATHEFNI_STAGE_B_ENABLED"] = "1"
        os.environ["WATHEFNI_STAGE_B_CANARY_ONLY"] = "1"
        os.environ["WATHEFNI_STAGE_B_PUBLIC_POSITIONS"] = "STAGEB_07210227"
        os.environ["WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES"] = "APPLY-WATHEFNI-STAGEB_07210227"
        self.assertTrue(
            stage_b.stage_b_convert_allowed_for_job(
                position_code="STAGEB_07210227",
                apply_code="APPLY-WATHEFNI-STAGEB_07210227",
            )
        )
        self.assertTrue(
            stage_b.stage_b_convert_allowed_for_job(
                position_code="stageb_07210227",
                apply_code=None,
            )
        )
        self.assertFalse(
            stage_b.stage_b_convert_allowed_for_job(
                position_code="OTHER_ROLE",
                apply_code="APPLY-WATHEFNI-OTHER_ROLE",
            )
        )
        # Phone allowlist is removed / unused.
        self.assertFalse(stage_b.stage_b_convert_allowed("96599338566", digits_fn=lambda p: "96599338566"))

    def test_convert_gate_requires_enable(self) -> None:
        os.environ["WATHEFNI_STAGE_B_ENABLED"] = "0"
        os.environ["WATHEFNI_STAGE_B_CANARY_ONLY"] = "1"
        os.environ["WATHEFNI_STAGE_B_PUBLIC_POSITIONS"] = "STAGEB_07210227"
        self.assertFalse(
            stage_b.stage_b_convert_allowed_for_job(position_code="STAGEB_07210227")
        )


if __name__ == "__main__":
    unittest.main()
