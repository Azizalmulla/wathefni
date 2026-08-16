#!/usr/bin/env python3
"""Safe production smoke for Shifts Wave 1 UX Closure (read-only + static checks)."""
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
    ok("planning_marker", "data-shifts-planning" in text)
    ok("planning_hr", "data-shifts-planning-hr" in text)
    ok("advanced_ops", "data-shifts-advanced" in text)
    ok("composer_org", "data-shifts-composer-org" in text or "Unmapped" in text)
    ok("advanced_ops_copy", "Show advanced operations" in text or "إظهار العمليات المتقدمة" in text)
    ok("shared_reason_modal", "minReasonLength" in text or "withReason" in text)
    ok("hr_cancel_impact", "removed from the live schedule" in text or "ستُلغى هذه الوردية" in text)
    ok("hr_copy_no_real_mutation", "Audit reason required for real mutations" not in text)
    ok("hr_copy_no_allowlist_jargon", "named allowlist" not in text.lower())
    ok("hr_copy_no_concurrency_token", "concurrency token" not in text.lower())
    ok("mutation_concurrency", "expected_updated_at" in text)
    ok("primary_schedule", "Schedule a shift" in text or "جدولة وردية" in text)
    ok("arabic_surface", "الجدول" in text or "التخطيط" in text)
    ok("payroll_still_present", "data-payroll-surfaces" in text)
    ok("leave_still_present", "data-leave-queue" in text)

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
    print("SHIFTS_WAVE1_UX_CLOSURE_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
