#!/usr/bin/env python3
"""Safe production smoke for Interaction Quality & Loading Integrity Wave 1."""
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
    joined = "\n".join(p.read_text(errors="ignore") for p in assets.glob("*.js"))
    ok("confirm_marker", "data-interaction-confirm" in joined)
    ok("shell_busy_marker", "data-interaction-shell-busy" in joined)
    ok("activity_refreshing", "data-activity-refreshing" in joined)
    ok("working_copy", "Working…" in joined or "جاري العمل" in joined)
    ok("no_always_refreshing_banner_only", "Refreshing hiring data..." not in joined or "Working…" in joined)
    ok("activity_timeline", "data-activity-timeline" in joined)
    ok("settings_ia", "data-settings-ia-closure" in joined)
    ok("alerts_preserved", "data-alerts-delivery" in joined)

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

    print("IQ_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("INTERACTION_QUALITY_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
