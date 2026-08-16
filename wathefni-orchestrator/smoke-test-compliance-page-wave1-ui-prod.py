#!/usr/bin/env python3
"""Safe production smoke for Compliance Page Refinement Wave 1."""
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

    ok("findings_marker", "data-compliance-findings" in text)
    ok("findings_list_marker", "data-compliance-findings-list" in text)
    ok("register_marker", "data-compliance-register" in text)
    ok("surfaces_marker", "data-compliance-surfaces" in text)
    ok("filters_marker", "data-compliance-filters" in text)
    ok("summary_marker", "data-compliance-summary" in text)
    ok("methodology_marker", "data-compliance-methodology" in text)
    ok("remind_marker", "data-compliance-remind" in text)
    ok("purpose_copy", "one clear workflow" in text.lower() or "مسار واحد واضح" in text)
    ok("all_documents_label", "All documents" in text or "كل المستندات" in text)
    ok("open_in_findings", "Open in Findings" in text or "فتح في النتائج" in text)
    ok("no_remind_all", "Remind all" not in text and "تذكير الجميع" not in text)
    ok("governed_dates_modal", "Correct dates" in text or "تصحيح التواريخ" in text)
    ok("hr_reviewed_honesty", "not government verified" in text.lower() or "ليست تحققاً حكومياً" in text)
    ok("arabic_surface", "تحتاج مراجعة" in text or "كل المستندات" in text)
    # Prior waves still present
    ok("analytics_still_present", "data-analytics-insights" in text)
    ok("payroll_still_present", "data-payroll-surfaces" in text)
    ok("shifts_still_present", "data-shifts-surfaces" in text or "data-shifts-planning" in text)

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

    print("COMPLIANCE_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("COMPLIANCE_PAGE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
