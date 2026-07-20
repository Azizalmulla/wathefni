#!/usr/bin/env python3
"""Local/unit smoke for prehire_overview SQL predicates and scoring helpers."""

from __future__ import annotations

import prehire_overview as po


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    ready = po.ready_for_review_predicate("a")
    assert_true("ready_for_review" in ready, "ready predicate includes canonical status")
    assert_true("screening_complete" in ready, "ready predicate includes legacy status")

    assess = po.assessment_pending_predicate("a")
    assert_true("shortlisted" in assess, "assessment eligible includes shortlisted")
    assert_true("pending" in assess, "assessment pending includes pending")

    follow = po.follow_up_needed_exists("a")
    assert_true("outbound_delivery_events" in follow, "follow-up uses delivery events")
    assert_true("recovered_at IS NULL" in follow, "follow-up excludes recovered")

    sla = po.resolve_sla_hours({"prehire_overview_sla": {"follow_up_hours": 12}})
    assert_true(sla["follow_up_hours"] == 12, "tenant SLA override")
    assert_true(sla["ready_for_review_hours"] == 48, "default SLA retained")

    # Deterministic empty next-action shape (no DB).
    # Score ordering constants must stay stable.
    assert_true(po.ACTION_FOLLOW_UP == "follow_up_failed_delivery", "follow-up action key")
    assert_true(po.ACTION_READY_FOR_REVIEW == "ready_for_review", "ready action key")

    print("PASS: prehire_overview unit invariants")


if __name__ == "__main__":
    main()
