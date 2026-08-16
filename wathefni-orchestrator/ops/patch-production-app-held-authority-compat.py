#!/usr/bin/env python3
"""Reconcile older Unified Candidates route guards with shared authority.

The production Unified Candidates patch predates the qualified shared
communication authority and inserted status-only notify/assessment guards.
Replace those two guards with the qualified DB-backed authority call while
preserving every other production route and canary behavior.
"""
from __future__ import annotations

import ast
import pathlib
import sys

MARKER = "HELD_COMMUNICATION_AUTHORITY_PRODUCTION_COMPAT"

NOTIFY_OLD = """    application = dashboard_application_or_404(app_key, company)
    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_outreach_forbidden",
                "message": "Talent Pool held records cannot receive outreach until linked to a Job.",
            },
        )
    payload = request or DashboardCandidateMessage()
"""

NOTIFY_NEW = f"""    application = dashboard_application_or_404(app_key, company)
    require_live_candidate_communication(
        application,
        kind="notify",
        expected_company_code=company,
    )  # {MARKER}
    payload = request or DashboardCandidateMessage()
"""

ASSESSMENT_OLD = """    application = dashboard_application_or_404(app_key, company)
    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_assessment_forbidden",
                "message": "Talent Pool held records cannot receive assessments until linked to a Job.",
            },
        )
    payload = request or DashboardCandidateMessage()
    selected_battery_key = str(payload.battery_key or "").strip() or None
"""

ASSESSMENT_NEW = f"""    application = dashboard_application_or_404(app_key, company)
    require_live_candidate_communication(
        application,
        kind="assessment",
        expected_company_code=company,
    )  # {MARKER}
    payload = request or DashboardCandidateMessage()
    selected_battery_key = str(payload.battery_key or "").strip() or None
"""


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label} anchor matched {count} times")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if MARKER in source:
        return source
    source = replace_once(source, NOTIFY_OLD, NOTIFY_NEW, "notify")
    source = replace_once(source, ASSESSMENT_OLD, ASSESSMENT_NEW, "assessment")
    ast.parse(source)
    return source


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch-production-app-held-authority-compat.py <in> <out>", file=sys.stderr)
        return 2
    source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    output = pathlib.Path(sys.argv[2])
    output.write_text(patch(source), encoding="utf-8")
    print(f"patched {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
