#!/usr/bin/env python3
"""Regression tests for the approved Interviews queue contract."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import interview_queue_contract as contract  # noqa: E402


def hamad_cancelled_video(**extra):
    row = {
        "interview_id": "06e4a65d-1a03-4dc9-9ad7-eba1c80717f9",
        "candidate_name": "Hamad Almulla",
        "status": "cancelled",
        "interview_type": "async_video",
        "source": "async_video",
        "feedback_status": "notes_pending",
        "human_feedback_status": "notes_pending",
        "async_status": "consented",
        "channel_send_status": "send_accepted",
    }
    row.update(extra)
    return row


def hamad_rows():
    return [
        hamad_cancelled_video(),
        hamad_cancelled_video(interview_id="8552e251-0cac-4a7a-9f8b-9ffbf351e2d1", async_status="link_sent"),
        {
            "interview_id": "669366ae-ee04-49c1-aca7-c1a9550ee405",
            "candidate_name": "Hamad Almulla",
            "status": "completed",
            "interview_type": "async_video",
            "source": "async_video",
            "feedback_status": "notes_pending",
            "human_feedback_status": "feedback_complete",
            "async_status": "completed",
        },
        {
            "interview_id": "369997d8-0ea5-429a-b5b5-40db0634c632",
            "candidate_name": "Hamad Almulla",
            "status": "completed",
            "interview_type": "live",
            "source": "schedule_interview",
            "feedback_status": "feedback_complete",
            "human_feedback_status": "notes_pending",
        },
    ]


class ContractMembershipTests(unittest.TestCase):
    def test_hamad_matrix(self):
        rows = hamad_rows()
        counts = {tab: sum(1 for r in rows if contract.tab_membership(r, tab)) for tab in contract.TAB_IDS}
        self.assertEqual(counts["upcoming"], 0)
        self.assertEqual(counts["needs_feedback"], 0)
        self.assertEqual(counts["video_interviews"], 1)
        self.assertEqual(counts["completed"], 2)
        self.assertEqual(counts["cancelled"], 2)
        self.assertEqual(counts["all"], 4)

    def test_cancelled_async_retains_fields_but_not_queues(self):
        row = hamad_cancelled_video()
        self.assertEqual(row["feedback_status"], "notes_pending")
        self.assertEqual(row["async_status"], "consented")
        self.assertEqual(row["channel_send_status"], "send_accepted")
        self.assertFalse(contract.tab_membership(row, "needs_feedback"))
        self.assertFalse(contract.tab_membership(row, "video_interviews"))
        self.assertFalse(contract.tab_membership(row, "upcoming"))
        self.assertTrue(contract.tab_membership(row, "cancelled"))
        self.assertTrue(contract.tab_membership(row, "all"))

    def test_no_show_async_excluded_from_video(self):
        row = hamad_cancelled_video(status="no_show")
        self.assertTrue(contract.tab_membership(row, "no_show"))
        self.assertFalse(contract.tab_membership(row, "video_interviews"))
        self.assertFalse(contract.tab_membership(row, "needs_feedback"))

    def test_legacy_aliases(self):
        self.assertEqual(contract.normalize_status("canceled"), "cancelled")
        self.assertEqual(contract.normalize_status("noshow"), "no_show")
        row = {"status": "canceled", "interview_type": "async_video", "source": "async_video"}
        self.assertTrue(contract.tab_membership(row, "cancelled"))
        self.assertFalse(contract.tab_membership(row, "video_interviews"))

    def test_structured_submission_submitted_wins(self):
        row = {
            "status": "completed",
            "feedback_status": "notes_pending",
            "human_feedback_status": "notes_pending",
            "feedback_submission": {"status": "submitted"},
        }
        self.assertTrue(contract.feedback_is_complete(row))
        self.assertFalse(contract.tab_membership(row, "needs_feedback"))

    def test_structured_submission_reopened_forces_pending(self):
        row = {
            "status": "completed",
            "feedback_status": "feedback_complete",
            "human_feedback_status": "feedback_complete",
            "feedback_submission": {"status": "reopened"},
        }
        self.assertFalse(contract.feedback_is_complete(row))
        self.assertTrue(contract.tab_membership(row, "needs_feedback"))

    def test_either_legacy_complete_clears_pending(self):
        row = {
            "status": "completed",
            "feedback_status": "feedback_complete",
            "human_feedback_status": "notes_pending",
        }
        self.assertTrue(contract.feedback_is_complete(row))
        self.assertFalse(contract.tab_membership(row, "needs_feedback"))

    def test_completed_video_remains_in_video(self):
        row = hamad_rows()[2]
        self.assertTrue(contract.tab_membership(row, "video_interviews"))
        self.assertTrue(contract.tab_membership(row, "completed"))


class SqlAndScopeParityTests(unittest.TestCase):
    def test_sql_video_excludes_terminals(self):
        sql = contract.sql_status_predicate("video_interviews")
        self.assertIn("NOT IN ('cancelled','no_show')", sql)
        self.assertIn("async_video", sql)

    def test_sql_needs_feedback_uses_canonical_expr(self):
        sql = contract.sql_status_predicate("needs_feedback")
        self.assertIn("interview_feedback_submissions", sql)
        self.assertIn("feedback_complete", sql)
        self.assertNotIn("COALESCE(ci.human_feedback_status, ci.feedback_status, 'notes_pending')", sql)

    def test_list_tab_predicate_aliases(self):
        sql, params = contract.list_tab_predicate("video")
        self.assertIn("NOT IN ('cancelled','no_show')", sql or "")
        self.assertEqual(params, [])
        sql, params = contract.list_tab_predicate("cancelled")
        self.assertEqual(sql, "ci.status=%s")
        self.assertEqual(params, ["cancelled"])

    def test_shared_scope_includes_assignment_and_visibility(self):
        where, params = contract.build_shared_scope(
            "WATHEFNI",
            assignment_sql="assign_scope=%s",
            assignment_params=["a1"],
            visibility_sql="vis_scope=%s",
            visibility_params=["v1"],
        )
        joined = " AND ".join(where)
        self.assertIn("ci.company_code=%s", joined)
        self.assertIn(contract.CV_EXISTS_SQL, joined)
        self.assertIn("assign_scope=%s", joined)
        self.assertIn("vis_scope=%s", joined)
        self.assertEqual(params, ["WATHEFNI", "a1", "v1"])

    def test_app_payload_uses_shared_scope_for_counts(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        start = src.find("def dashboard_interviews_payload")
        chunk = src[start : src.find("def deterministic_interview_summary", start)]
        self.assertIn("import interview_queue_contract as iqc", chunk)
        self.assertIn("build_shared_scope", chunk)
        self.assertIn("scope_sql", chunk)
        self.assertIn("WHERE {scope_sql}", chunk)
        self.assertIn("AND ({video_sql})", chunk)
        self.assertNotIn("counts_kind_sql", chunk)
        self.assertNotIn(
            "COALESCE(ci.human_feedback_status, ci.feedback_status, 'notes_pending')<>'feedback_complete'",
            chunk,
        )

    def test_no_divergence_flags(self):
        self.assertFalse(any(contract.current_diverges_from_contract().values()))


class CancelPreservesFieldsSourceTests(unittest.TestCase):
    def test_cancel_update_does_not_clear_feedback_or_video(self):
        src = (ROOT / "interview_service.py").read_text(encoding="utf-8")
        start = src.find("def cancel_interview")
        chunk = src[start : start + 2500]
        self.assertIn("SET status='cancelled'", chunk)
        self.assertNotIn("feedback_status=", chunk.split("SET status='cancelled'")[1].split("WHERE")[0])
        self.assertNotIn("async_status=", chunk.split("SET status='cancelled'")[1].split("WHERE")[0])


class FrontendInvalidationTests(unittest.TestCase):
    def test_after_interview_action_refetches_interviews_actively(self):
        dash = ROOT.parent / "apps/wathefni-dashboard/src/lib/query"
        inv_path = dash / "invalidation.ts"
        hooks_path = dash / "hooks.ts"
        if not inv_path.exists() or not hooks_path.exists():
            self.skipTest("dashboard source not present in this environment")
        inv = inv_path.read_text(encoding="utf-8")
        hooks = hooks_path.read_text(encoding="utf-8")
        self.assertIn("afterInterviewAction", inv)
        self.assertIn("refetchType: 'active'", inv)
        # Interviews query must not keep prior tab badges after mutation.
        interviews_hook = hooks[hooks.find("useInterviewsQuery") : hooks.find("useAssessmentsQuery")]
        self.assertIn("placeholderData: undefined", interviews_hook)
        self.assertNotIn("keepPreviousData", interviews_hook)


if __name__ == "__main__":
    unittest.main()
