#!/usr/bin/env python3
"""Analytics Wave 1 — Attention Contract smoke tests (no DB required for builders)."""

from __future__ import annotations

import analytics_attention_wave1 as w1
import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_partial_sources() -> None:
    pack = w1.analytics_source_availability({"analytics", "leave"})
    assert_true(pack["partial"] is True, "partial modules must disclose unavailable sources")
    assert_true(pack["sources"]["leave"]["available"] is True, "leave must be available when enabled")
    assert_true(pack["sources"]["attendance"]["available"] is False, "attendance must be unavailable when disabled")
    assert_true("attendance" in pack["unavailable_source_keys"], "attendance must be listed as unavailable")
    assert_true(pack["sources"]["hours_summary"]["authority"] == "non_payroll_hours_projection", "hours authority must be non-payroll")


def test_attention_ranking_and_deep_links() -> None:
    sources = w1.analytics_source_availability(
        {"analytics", "attendance", "leave", "shifts", "payroll", "onboarding"}
    )
    counts = {
        "pending_leave": 3,
        "pending_swaps": 2,
        "pending_availability": 1,
        "absent_records": 4,
        "late_records": 6,
        "late_minutes": 90,
        "scheduled_shifts": 40,
    }
    summaries = [
        {
            "employee_key": "WATHEFNI-E1",
            "employee_name": "Alice",
            "late_minutes": 40,
            "absent_minutes": 0,
            "overtime_minutes": 120,
            "attendance_count": 3,
        },
        {
            "employee_key": "WATHEFNI-E2",
            "employee_name": "Bob",
            "late_minutes": 0,
            "absent_minutes": 180,
            "overtime_minutes": 0,
            "attendance_count": 2,
        },
    ]
    branch_rows = [{"branch_name": "Salmiya", "absent_count": 3}]
    attention = w1.build_analytics_attention(
        counts=counts,
        summaries=summaries,
        branch_rows=branch_rows,
        sources=sources,
    )
    assert_true(len(attention) >= 4, "attention must include queue and pattern items")
    assert_true(attention[0]["severity"] == "high", "highest severity must rank first")
    ids = [item["id"] for item in attention]
    assert_true("pending_leave" in ids, "pending leave must appear")
    assert_true("pending_swaps" in ids, "pending swaps must appear")
    leave_item = next(item for item in attention if item["id"] == "pending_leave")
    assert_true(leave_item["deep_link"]["page"] == "leave", "leave attention must deep-link to leave")
    alice = next(item for item in attention if item["id"].startswith("top_lateness:"))
    assert_true(alice["deep_link"]["page"] == "employees", "person lateness must deep-link to employees")
    assert_true(alice["deep_link"].get("employee") == "WATHEFNI-E1", "person deep-link must carry employee key")
    hours_items = [item for item in attention if item["id"].startswith("hours_above_schedule:")]
    assert_true(hours_items, "hours-above-schedule must appear when hours source available")
    assert_true("non-payroll" in hours_items[0]["reason_en"].lower(), "hours signal must say non-payroll")
    assert_true(all(item["id"] != "scheduled_shifts" for item in attention), "scheduled shifts must not be attention")
    assert_true(
        all("best attendance" not in (item.get("reason_en") or "").lower() for item in attention),
        "best attendance must not be attention",
    )


def test_demoted_vanity_and_honest_wording() -> None:
    sources = w1.analytics_source_availability({"analytics", "attendance", "shifts", "payroll"})
    insights = w1.build_analytics_pattern_insights(
        counts={"scheduled_shifts": 10, "absent_records": 1, "late_records": 2, "late_minutes": 5},
        summaries=[
            {
                "employee_name": "Fouad",
                "employee_key": "E1",
                "late_minutes": 25,
                "absent_minutes": 0,
                "overtime_minutes": 30,
                "attendance_count": 2,
                "shift_count": 5,
                "early_leave_minutes": 0,
            }
        ],
        branch_rows=[{"branch_name": "Salmiya", "absent_count": 1}],
        sources=sources,
        decimal_hours_fn=app.decimal_hours,
    )
    metrics = [row["metric"] for row in insights]
    assert_true("Best attendance" not in metrics, "best attendance must be removed")
    scheduled = [row for row in insights if row["metric"] == "Scheduled shifts"]
    assert_true(scheduled and scheduled[0].get("demoted") is True, "scheduled shifts must be demoted")
    assert_true("Overtime risk" not in metrics, "overtime risk label must be gone")
    assert_true(w1.HOURS_ABOVE_SCHEDULE_METRIC in metrics, "honest hours-above-schedule label required")
    hours = next(row for row in insights if row["metric"] == w1.HOURS_ABOVE_SCHEDULE_METRIC)
    assert_true("non-payroll" in str(hours.get("detail") or "").lower(), "hours detail must deny money authority")


def test_headlines_exclude_scheduled() -> None:
    sources = w1.analytics_source_availability({"analytics", "attendance", "leave"})
    headlines = w1.attention_headline_stats(
        {"scheduled_shifts": 99, "absent_records": 2, "late_records": 1, "late_minutes": 10, "pending_leave": 1},
        sources,
    )
    keys = [h["key"] for h in headlines]
    assert_true("scheduled_shifts" not in keys, "scheduled shifts must not be a headline")
    assert_true("absences" in keys, "absences headline required")


def test_definitions_and_reply_contract() -> None:
    defs = w1.analytics_metric_definitions()
    assert_true(any(d["key"] == "authority" for d in defs), "authority definition required")
    assert_true(any(d["key"] == "hours_above_schedule" for d in defs), "hours definition required")
    reply = app.format_workforce_analytics_reply(
        {
            "ok": True,
            "start_date": "2026-08-01",
            "end_date": "2026-08-03",
            "metric": "review",
            "counts": {"absent_records": 1, "late_records": 2, "pending_leave": 1, "pending_availability": 0, "pending_swaps": 0},
            "attention": [
                {
                    "severity": "high",
                    "reason": "1 leave request awaits a decision",
                    "reason_en": "1 leave request awaits a decision",
                }
            ],
            "insights": [
                {"metric": "Top lateness", "subject": "Fouad Burhamad", "value": 25, "detail": "2 attendance record(s)."},
                {"metric": "Scheduled shifts", "subject": "All employees", "value": 10, "detail": "Context only", "demoted": True},
            ],
            "sources": {"unavailable_source_keys": ["payroll"], "partial": True},
        }
    )
    assert_true("Needs attention:" in reply, "reply must surface attention block")
    assert_true("Fouad Burhamad" in reply, "reply must keep insight subjects")
    assert_true("Scheduled shifts:" not in reply.split("Needs attention:")[0], "vanity scheduled headline removed from summary line")
    assert_true("Unavailable sources: payroll" in reply, "partial sources must be disclosed")


def test_dashboard_action_identity_keys() -> None:
    # Contract: dashboard path must pass full actor identity into workforce_analytics.
    from pathlib import Path

    text = Path(app.__file__).read_text(encoding="utf-8")
    start = text.find("def dashboard_posthire_analytics")
    assert_true(start > 0, "dashboard analytics route must exist")
    chunk = text[start : start + 900]
    assert_true("viewer_user_id" in chunk, "dashboard analytics must pass viewer_user_id")
    assert_true("actor_role" in chunk, "dashboard analytics must pass actor_role")
    assert_true("viewer_phone" in chunk, "dashboard analytics must still pass viewer_phone")
    assert_true("workforce_analytics(" in chunk, "dashboard analytics must call workforce_analytics")


def test_assistant_chip_not_headcount() -> None:
    from assistant_capability_catalog import empty_prompt_chips_from_catalog

    chips = empty_prompt_chips_from_catalog(
        {"offerable": ["posthire_analytics"]},
        locale="en",
    )
    texts = " ".join(chips).lower()
    assert_true(chips, "analytics chip must be offerable")
    assert_true("headcount" not in texts, "assistant chip must not say Headcount summary")
    assert_true("attention" in texts, "assistant chip must say attention")


def main() -> None:
    test_partial_sources()
    test_attention_ranking_and_deep_links()
    test_demoted_vanity_and_honest_wording()
    test_headlines_exclude_scheduled()
    test_definitions_and_reply_contract()
    test_dashboard_action_identity_keys()
    try:
        test_assistant_chip_not_headcount()
    except Exception as exc:
        # Chip helper signature may vary; still fail closed with message.
        raise AssertionError(f"assistant chip check failed: {exc}") from exc
    print("analytics-attention-wave1 smoke tests passed")


if __name__ == "__main__":
    main()
