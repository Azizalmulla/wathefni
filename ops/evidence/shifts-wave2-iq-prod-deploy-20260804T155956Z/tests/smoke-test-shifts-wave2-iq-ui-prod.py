#!/usr/bin/env python3
"""Safe production smoke for Shifts Visual & UX Wave 2 (IQ-12)."""
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
    bundles = list(assets.glob("PostHire-*.js"))
    ok("posthire_bundle_present", len(bundles) == 1, bundles[0].name if bundles else "missing")
    text = bundles[0].read_text(errors="ignore")
    joined = "\n".join(p.read_text(errors="ignore") for p in assets.glob("*.js"))

    ok("iq_wave2_marker", "data-shifts-iq-wave2" in text)
    ok("updating_overlay", "data-shifts-updating" in text)
    ok("updating_copy", "Updating…" in text or "جارٍ التحديث" in text)
    ok("surfaces_preserved", "data-shifts-surfaces" in text)
    ok("board_preserved", "shifts-board" in text)
    ok("filters_preserved", "data-shifts-filters" in text)
    ok("mutation_concurrency", "expected_updated_at" in text)
    ok("swap_actions", "approve_shift_swap" in text)
    ok("confirm_continue", "Continue" in text or "متابعة" in text)
    ok("wave1_primary", "data-primary-action" in text)
    ok("leave_still_present", "data-leave-queue" in text)
    ok("iq_shell_still", "data-interaction-confirm" in joined or "data-interaction-shell-busy" in joined)

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

    print("SHIFTS_WAVE2_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("SHIFTS_WAVE2_IQ_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
