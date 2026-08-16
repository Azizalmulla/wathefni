#!/usr/bin/env python3
"""Safe production smoke for Payroll Page Refinement Wave 1 (read-only + static checks)."""
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

    ok("surfaces_marker", "data-payroll-surfaces" in text)
    ok("queue_marker", "data-payroll-queue" in text)
    ok("records_panels", "data-payroll-records-panels" in text)
    ok("run_default_tab", "payroll-tab-external-run" in text)
    ok("hours_tab", "payroll-tab-hours-review" in text)
    ok("records_tab", "payroll-tab-records" in text)
    ok("payslips_tab", "payroll-tab-payslips" in text)
    ok("close_tab", "payroll-tab-close-export" in text)
    ok("statutory_tab", "payroll-tab-statutory" in text)
    ok("honesty_toggle", "data-payroll-honesty-toggle" in text)
    ok("hours_export_soft", "data-payroll-hours-export" in text)
    ok("external_workspace", "external-payroll-workspace" in text)
    ok("money_honesty_copy", "does not pay" in text.lower() or "لا يدفع" in text)
    ok("mutation_row_version", "expected_row_version" in text)
    ok("arabic_surface", "التشغيل" in text or "الساعات" in text or "السجلات" in text)
    # Prior waves must remain
    ok("shifts_still_present", "data-shifts-surfaces" in text or "data-shifts-composer-org" in text)
    ok("leave_still_present", "data-leave-queue" in text)
    ok("attendance_still_present", "attendance-board" in text)

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

    print("PAYROLL_WAVE1_DB", json.dumps({"db": db}))
    ok("db_readable", db == "wathefni", db)
    print("PAYROLL_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
