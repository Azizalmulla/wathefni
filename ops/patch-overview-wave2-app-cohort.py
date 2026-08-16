#!/usr/bin/env python3
"""Surgical Wave 2 overview_cohort patch for production app.py."""

from __future__ import annotations

from pathlib import Path
import sys

APP = Path("/opt/wathefni/orchestrator/app.py")


def main() -> int:
    text = APP.read_text()
    if "overview_cohort: str | None = None," in text and "cohort in {\"interview_scheduling_debt\"" in text:
        print("ALREADY_PATCHED")
        return 0

    old_sig = """    follow_up: str | None = None,
    review_status: str | None = None,
    activity_from: str | None = None,"""
    new_sig = """    follow_up: str | None = None,
    review_status: str | None = None,
    overview_cohort: str | None = None,
    activity_from: str | None = None,"""
    if text.count(old_sig) < 2:
        print(f"FAIL: expected >=2 signature anchors, found {text.count(old_sig)}", file=sys.stderr)
        return 1
    text = text.replace(old_sig, new_sig, 2)

    old_position = """    if status:
        where.append("a.status=%s")
        params.append(status)
    if position:
        where.append("(a.position_code ILIKE %s OR a.position_title ILIKE %s)")
        params.extend([f"%{position}%", f"%{position.replace('_', ' ')}%"])
    if search:"""
    new_position = """    if status:
        where.append("a.status=%s")
        params.append(status)
    cohort = str(overview_cohort or "").strip().lower()
    # role_active uses exact position_code so ACCOUNTING does not swallow ACCOUNTING_EXCEL.
    if position and cohort == "role_active":
        where.append("a.position_code=%s")
        params.append(position)
    elif position:
        where.append("(a.position_code ILIKE %s OR a.position_title ILIKE %s)")
        params.extend([f"%{position}%", f"%{position.replace('_', ' ')}%"])
    if search:"""
    if old_position not in text:
        print("FAIL: position filter anchor missing", file=sys.stderr)
        return 1
    text = text.replace(old_position, new_position, 1)

    old_review = """    if str(review_status or "").strip().lower() in {"ready", "ready_for_review", "needed"}:
        # Canonical with prehire_overview.ready_for_review / Overview review card.
        where.append(_prehire_overview.ready_for_review_predicate("a"))
    if activity_from:"""
    new_review = """    if str(review_status or "").strip().lower() in {"ready", "ready_for_review", "needed"}:
        # Canonical with prehire_overview.ready_for_review / Overview review card.
        where.append(_prehire_overview.ready_for_review_predicate("a"))
    if cohort in {"interview_scheduling_debt", "interview_debt"}:
        # Exact Overview interview scheduling debt (not Interviews tab status).
        where.append(
            _prehire_overview.interview_scheduling_debt_predicate(
                "a",
                interview_status_expr="latest_interview.interview_status",
            )
        )
    elif cohort in {"role_active", "active_role"}:
        where.append(_prehire_overview.role_active_predicate("a"))
    elif cohort in {"follow_up_needed", "follow_up"} and str(follow_up or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "needed",
    }:
        where.append(_prehire_overview.follow_up_needed_exists("a"))
    elif cohort in {"ready_for_review", "ready"} and str(review_status or "").strip().lower() not in {
        "ready",
        "ready_for_review",
        "needed",
    }:
        where.append(_prehire_overview.ready_for_review_predicate("a"))
    elif cohort in {"assessment_pending", "awaiting"} and str(assessment_status or "").strip().lower() != "awaiting":
        where.append(
            _prehire_overview.assessment_pending_predicate(
                "a",
                assessment_status_expr="COALESCE(latest_assessment.assessment_status, a.raw_json->'assessment'->>'status', '')",
                assessment_delivery_status_expr="COALESCE(latest_assessment.assessment_delivery_status, a.raw_json->'assessment'->>'delivery_status', '')",
            )
        )
    if activity_from:"""
    if old_review not in text:
        print("FAIL: review_status filter anchor missing", file=sys.stderr)
        return 1
    text = text.replace(old_review, new_review, 1)

    old_call = """            follow_up=(follow_up or "").strip() or None,
            review_status=(review_status or "").strip() or None,
            activity_from=(activity_from or "").strip() or None,"""
    new_call = """            follow_up=(follow_up or "").strip() or None,
            review_status=(review_status or "").strip() or None,
            overview_cohort=(overview_cohort or "").strip() or None,
            activity_from=(activity_from or "").strip() or None,"""
    if old_call not in text:
        print("FAIL: dashboard call anchor missing", file=sys.stderr)
        return 1
    text = text.replace(old_call, new_call, 1)

    APP.write_text(text)
    print("PATCHED_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
