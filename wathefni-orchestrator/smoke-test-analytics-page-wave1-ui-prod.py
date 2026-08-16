#!/usr/bin/env python3
"""Safe production smoke for Analytics Page Refinement Wave 1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

WWW = Path("/var/www/wathefni-dashboard")


def ok(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        raise SystemExit(1)


def main() -> int:
    bundles = list((WWW / "assets").glob("PostHire-*.js"))
    ok("posthire_bundle_present", len(bundles) == 1, bundles[0].name if bundles else "missing")
    text = bundles[0].read_text(errors="ignore")

    ok("insights_marker", "data-analytics-insights" in text)
    ok("snapshot_marker", "data-analytics-snapshot" in text)
    ok("narrative_marker", "data-analytics-narrative" in text)
    ok("patterns_marker", "data-analytics-patterns" in text)
    ok("period_marker", "data-analytics-period" in text)
    ok("comparison_marker", "data-analytics-comparison" in text)
    ok("methodology_marker", "data-analytics-methodology" in text)
    ok("triage_deeplink", "data-analytics-triage-link" in text or "Open Needs Attention" in text)
    # Analytics no longer hosts a ranked attention inbox card titled for triage
    ok("no_analytics_attention_card", "Ranked by severity. Open the system of action" not in text)
    ok("purpose_copy", "not the daily task queue" in text.lower() or "لا قائمة المهام" in text)
    ok("arabic_surface", "ملخص الفترة" in text or "اتجاهات" in text or "التحليلات" in text)
    ok("payroll_still_present", "data-payroll-surfaces" in text)
    ok("shifts_still_present", "data-shifts-surfaces" in text or "data-shifts-planning" in text)
    ok("inbox_still_present", "data-leave-queue" in text or "Needs Attention" in text)

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_explicit_environment()
    import os

    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")

    from app import db_connect

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
        conn.commit()

    print("ANALYTICS_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("ANALYTICS_PAGE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
