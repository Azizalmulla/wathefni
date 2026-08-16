#!/usr/bin/env python3
"""Safe production smoke for Shifts Visual Design Wave 3 (shared baseline)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WWW = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
if not (WWW / "assets").exists():
    WWW = Path("/var/www/wathefni-dashboard")


def ok(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        raise SystemExit(1)


def main() -> int:
    assets = WWW / "assets"
    bundles = list(assets.glob("PostHire-*.js"))
    ok("posthire_bundle_present", len(bundles) == 1, bundles[0].name if bundles else "missing")
    text = bundles[0].read_text(errors="ignore")
    css = "\n".join(p.read_text(errors="ignore") for p in assets.glob("*.css"))
    joined = "\n".join(p.read_text(errors="ignore") for p in assets.glob("*.js"))

    # Wave 3 visual baseline
    ok("visual_wave3_marker", "data-shifts-visual-wave3" in text)
    ok("board_hero_marker", "data-shifts-board-hero" in text)
    ok("shared_priority_token", "wf-accent-priority" in text or "accent-priority" in css)
    ok("shared_review_token", "wf-accent-review" in text or "accent-review" in css)
    ok("no_legacy_scheduled_hex", "bg-[#e9e4d9]" not in text)
    ok("no_legacy_conflict_hex", "bg-[#f3d85f]" not in text)

    # IQ-12 must remain
    ok("iq_wave2_marker", "data-shifts-iq-wave2" in text)
    ok("updating_overlay", "data-shifts-updating" in text)
    ok("filters_preserved", "data-shifts-filters" in text)
    ok("surfaces_preserved", "data-shifts-surfaces" in text)
    ok("mutation_concurrency", "expected_updated_at" in text)
    ok("swap_actions", "approve_shift_swap" in text)
    ok("leave_still_present", "data-leave-queue" in text)
    ok("iq_shell_still", "data-interaction-confirm" in joined or "data-interaction-shell-busy" in joined)

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

    print("SHIFTS_WAVE3_DB", json.dumps({"db": db, "bundle": bundles[0].name}))
    ok("db_readable", db == "wathefni", db)
    print("SHIFTS_WAVE3_VISUAL_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
