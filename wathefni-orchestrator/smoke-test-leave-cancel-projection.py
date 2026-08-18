#!/usr/bin/env python3
"""Leave cancellation read-projection matrix (Kuwait-local, no database writes)."""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import date, timedelta

os.environ.setdefault("WATHEFNI_ENV", "test")
os.environ.setdefault("WATHEFNI_LEAVE_WORKFLOW_WAVE3", "on")
os.environ.setdefault("WATHEFNI_LEAVE_WAVE4", "on")
os.environ.setdefault("WATHEFNI_LEAVE_REAL_DECISION_GATE", "off")

import leave_wave4_controlled as wave4  # noqa: E402


TODAY = date(2026, 8, 18)


def project(status: str, start: date, end: date | None = None, *, enabled: bool = True):
    row = {
        "leave_id": "projection-only",
        "employee_key": "synthetic-projection",
        "status": status,
        "start_date": start,
        "end_date": end or start,
    }
    original = deepcopy(row)
    result = wave4.cancel_policy_projection(
        row,
        actor_phone="96500000000",
        is_self=True,
        is_synthetic_subject=True,
        action_enabled=enabled,
        as_of=TODAY,
    )
    assert row == original, "read projection mutated canonical Leave state"
    return result


def main() -> int:
    future = project("approved", TODAY + timedelta(days=1))
    assert future["temporal_state"] == "future"
    assert future["presentation_status"] == "approved"
    assert future["can_cancel"] is True and future["allowed_actions"] == ["cancel"]

    starts_today = project("approved", TODAY, TODAY + timedelta(days=1))
    assert starts_today["temporal_state"] == "in_progress"
    assert starts_today["can_cancel"] is False
    assert starts_today["cancel_block_reason"] == "leave_already_started"

    spanning_today = project("approved", TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    assert spanning_today["temporal_state"] == "in_progress"
    assert spanning_today["cancel_block_reason"] == "leave_already_started"

    ends_today = project("approved", TODAY - timedelta(days=1), TODAY)
    assert ends_today["temporal_state"] == "in_progress"
    assert ends_today["cancel_block_reason"] == "leave_already_started"

    completed = project("approved", TODAY - timedelta(days=2), TODAY - timedelta(days=1))
    assert completed["temporal_state"] == "completed"
    assert completed["presentation_status"] == "completed"
    assert completed["can_cancel"] is False and completed["allowed_actions"] == []
    assert completed["cancel_block_reason"] == "leave_already_taken"

    for terminal in ("cancelled", "canceled", "rejected", "denied", "completed"):
        result = project(terminal, TODAY + timedelta(days=1))
        assert result["can_cancel"] is False, terminal
        assert result["allowed_actions"] == [], terminal
        assert result["cancel_block_reason"] == "leave_not_cancellable", terminal

    requested = project("requested", TODAY + timedelta(days=1))
    assert requested["can_cancel"] is True and requested["allowed_actions"] == ["cancel"]

    disabled = project("approved", TODAY + timedelta(days=1), enabled=False)
    assert disabled["can_cancel"] is False and disabled["allowed_actions"] == []
    assert disabled["cancel_block_reason"] == "leave_cancel_not_available"

    print("PASS leave cancel read-projection matrix (Asia/Kuwait policy day 2026-08-18)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
