#!/usr/bin/env python3
"""Safe production smoke for Shifts Wave 1 UI deploy (read-only + static checks)."""
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

    ok("surfaces_marker", "data-shifts-surfaces" in text)
    ok("schedule_default_marker", "data-shifts-queue" in text or "shifts-workspace" in text)
    ok("attention_strip", "data-shifts-attention" in text)
    ok("primary_schedule", "data-primary-action" in text and ("Schedule a shift" in text or "جدولة وردية" in text))
    ok("board_marker", "shifts-board" in text)
    ok("operations_collapsed", "data-shifts-operations" in text or "Show readiness" in text or "إظهار تفاصيل" in text)
    ok("no_inner_h1_pattern", "tracking-[0.18em]" not in text or text.count(">Shifts<") <= 2)
    ok("governed_filters", "All branches" in text or "كل الفروع" in text)
    ok("empty_cta", "No shifts in this period" in text or "لا ورديات في هذه الفترة" in text)
    ok("mutation_concurrency", "expected_updated_at" in text)
    ok("mutation_swaps", "approve_shift_swap" in text)
    ok("arabic_surface", "الجدول" in text or "الطلبات" in text)
    # Prior waves must remain
    ok("leave_still_present", "data-leave-queue" in text)
    ok("attendance_still_present", "attendance-board" in text)

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
            cur.execute(
                """
                SELECT status, count(*) AS c
                FROM shift_assignments
                WHERE company_code='WATHEFNI'
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 20
                """
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

    print("SHIFT_STATUS_COUNTS", json.dumps(rows, default=str)[:2000])
    ok("shifts_table_readable", True, f"statuses={len(rows)}")
    print("SHIFTS_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
