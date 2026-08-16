#!/usr/bin/env python3
"""Read-only production smoke for approved Shifts Visual Wave 3B."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WWW = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
if not (WWW / "assets").exists():
    WWW = Path("/var/www/wathefni-dashboard")


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> int:
    bundles = list((WWW / "assets").glob("PostHire-*.js"))
    ok("posthire_bundle_present", len(bundles) == 1, bundles[0].name if bundles else "missing")
    text = bundles[0].read_text(errors="ignore")
    joined = "\n".join(path.read_text(errors="ignore") for path in (WWW / "assets").glob("*.js"))

    ok("wave3b_marker", "data-shifts-visual-wave3b" in text)
    ok("roster_board", "data-shifts-roster-board" in text)
    ok("roster_rows", "data-shifts-roster-row" in text)
    ok("identity_once_component", "data-shifts-identity" in text)
    ok("overlap_layout", "data-shifts-overlap" in text)
    ok("overnight_continuation", "data-shift-continuation" in text)
    ok("mobile_day_strip", "data-shifts-day-strip" in text)
    ok("fixed_end_sheet", "data-shifts-aside-sheet" in text)
    ok("history_soft_keep", "data-shifts-history-soft-keep" in text)
    ok("client_filter_chrome", "data-shifts-active-filters" in text)

    # Frozen Wave 1 / IQ-12 interaction and authority markers.
    ok("iq_wave2_marker", "data-shifts-iq-wave2" in text)
    ok("updating_non_reflow", "data-shifts-updating" in text)
    ok("filters_preserved", "data-shifts-filters" in text)
    ok("surfaces_preserved", "data-shifts-surfaces" in text)
    ok("composer_org", "data-shifts-composer-org" in text)
    ok("edit_org", "data-shifts-edit-org" in text)
    ok("mutation_concurrency", "expected_updated_at" in text)
    ok("swap_actions", "approve_shift_swap" in text)
    ok("shared_priority_token", "wf-accent-priority" in text)
    ok("shared_review_token", "wf-accent-review" in text)
    ok("no_legacy_scheduled_hex", "bg-[#e9e4d9]" not in text)
    ok("no_legacy_conflict_hex", "bg-[#f3d85f]" not in text)
    ok("confirm_shell_present", "data-interaction-confirm" in joined or "data-interaction-shell-busy" in joined)

    sys.path.insert(0, "/opt/wathefni/orchestrator")
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
            database = dict(cur.fetchone())["db"]
        conn.commit()

    print("SHIFTS_WAVE3B_DB", json.dumps({"db": database, "bundle": bundles[0].name}))
    ok("db_readable", database == "wathefni", database)
    print("SHIFTS_WAVE3B_VISUAL_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

