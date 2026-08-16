#!/usr/bin/env python3
"""Safe production smoke for Alerts & Delivery Page Refinement Wave 1."""
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
    post = bundles[0].read_text(errors="ignore")
    # Notifications may be in dashboard chunk or its own lazy chunk
    assets = WWW / "assets"
    texts = [p.read_text(errors="ignore") for p in assets.glob("*.js")]
    joined = "\n".join(texts)

    ok("alerts_marker", "data-alerts-delivery" in joined)
    ok("issues_marker", "data-alerts-issues" in joined)
    ok("filters_marker", "data-alerts-filters" in joined)
    ok("summary_marker", "data-alerts-summary" in joined)
    ok("details_marker", "data-alerts-issue-detail" in joined or "Hide details" in joined)
    ok("purpose_copy", "safest next action" in joined.lower() or "أأمن إجراء" in joined)
    ok("scoped_rows_rendered", "delivery_id" in joined or "Open Assessments" in joined)
    ok("no_void_issues", "void issues" not in joined)
    ok("no_urgent_nested_card", "Urgent HR alerts" not in joined)
    ok("mark_done_path", "Marked as done" in joined or "وُسم كمكتمل" in joined or "Mark done" in joined)
    ok("status_cta_path", "data-alerts-status-cta" in joined or "No action needed" in joined)
    ok("arabic_surface", "يحتاج متابعة" in joined or "التنبيهات والتسليم" in joined)
    ok("no_specialist_strip_mount", "<DeliveryStatusStrip" not in post and "employee messages need" not in post.lower())
    ok("compliance_still_present", "data-compliance-findings" in post)
    ok("analytics_still_present", "data-analytics-insights" in post)

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import os

    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

    from app import db_connect

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
        conn.commit()

    print("ALERTS_DELIVERY_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("ALERTS_DELIVERY_PAGE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
