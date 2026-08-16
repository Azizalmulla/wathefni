#!/usr/bin/env python3
"""Safe production smoke for Activity Page Refinement Wave 1."""
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
    assets = WWW / "assets"
    texts = [p.read_text(errors="ignore") for p in assets.glob("*.js")]
    joined = "\n".join(texts)
    post_bundles = list(assets.glob("PostHire-*.js"))
    ok("posthire_bundle_present", len(post_bundles) == 1, post_bundles[0].name if post_bundles else "missing")

    ok("timeline_marker", "data-activity-timeline" in joined)
    ok("list_marker", "data-activity-list" in joined)
    ok("filters_marker", "data-activity-filters" in joined)
    ok("export_marker", "data-activity-export" in joined or "Export CSV" in joined)
    ok("details_marker", "data-activity-details" in joined)
    ok("purpose_copy", "trustworthy, read-only timeline" in joined.lower() or "جدول زمني موثوق" in joined)
    ok("no_company_activity_card", "Company activity" not in joined)
    ok("no_decorative_category_meta", "CATEGORY_META" not in joined)
    ok("rbac_admins", "Owners and HR Admins" in joined)
    ok("no_hr_managers_copy", "Owners and HR Managers" not in joined)
    ok("arabic_surface", "المنفّذ" in joined or "النشاط" in joined or "تصدير CSV" in joined)
    ok("read_only_honesty", "Read-only audit record" in joined or "للقراءة فقط" in joined)
    ok("alerts_still_present", "data-alerts-delivery" in joined)
    ok("compliance_still_present", "data-compliance-findings" in joined)

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

    print("ACTIVITY_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("ACTIVITY_PAGE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
