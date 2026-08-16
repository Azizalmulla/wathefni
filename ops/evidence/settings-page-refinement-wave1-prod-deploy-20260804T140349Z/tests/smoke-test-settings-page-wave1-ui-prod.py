#!/usr/bin/env python3
"""Safe production smoke for Settings Page Refinement Wave 1."""
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
    ok("settings_marker", "data-settings" in joined)
    ok("purpose_marker", "data-settings-purpose" in joined)
    ok("ownership_marker", "data-settings-ownership" in joined)
    ok("account_marker", "data-settings-account" in joined)
    ok("team_marker", "data-settings-team" in joined)
    ok("comms_marker", "data-settings-communications" in joined)
    ok("purpose_copy", "without changing role permissions" in joined.lower() or "دون تغيير صلاحيات" in joined)
    ok("no_platform_integrations_title", "Platform Integrations" not in joined)
    ok("company_connections", "Company connections" in joined or "اتصالات المنصة" in joined)
    ok("arabic_surface", "الحساب" in joined or "الفريق" in joined or "الإعدادات" in joined)
    ok("activity_still_present", "data-activity-timeline" in joined)
    ok("alerts_still_present", "data-alerts-delivery" in joined)

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

    print("SETTINGS_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("SETTINGS_PAGE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
