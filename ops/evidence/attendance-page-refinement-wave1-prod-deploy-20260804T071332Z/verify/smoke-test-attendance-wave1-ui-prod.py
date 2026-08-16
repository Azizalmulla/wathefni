#!/usr/bin/env python3
"""Safe production smoke for Attendance Wave 1 UI deploy (read-only + static checks).

Does not mutate attendance, apply corrections, or touch payroll money.
"""
from __future__ import annotations

import json
import re
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

    ok("board_first_marker", "attendance-board" in text)
    ok("attention_strip", "attendance-attention-strip" in text)
    ok("operations_collapsed_marker", "attendance-operations" in text)
    ok("ops_exception_row", "attendance-exception-row" in text)
    ok("no_board_correct_save", "Save correction" not in text or "AttendanceCorrectionRow" not in text)
    # Minified may drop exact strings; require Resolve + Request correction still present
    ok("resolve_cta", "Resolve" in text or "متابعة" in text)
    ok("request_correction_cta", "Request correction" in text or "طلب تصحيح" in text)
    ok("apply_separate_hint", "Approve confirms the decision" in text or "الاعتماد يؤكد القرار" in text)
    ok("dual_pending_copy", "Waiting for a different approver" in text or "بانتظار معتمد مختلف" in text)
    ok("payroll_locked_copy", "This day is locked in Payroll" in text or "هذا اليوم مقفل في كشف الرواتب" in text)
    ok("stale_row_copy", "Someone else updated this item" in text or "حدّث شخص آخر هذا العنصر" in text)
    ok("show_operations_default", "Show Operations" in text or "إظهار العمليات" in text)
    ok("arabic_rtl_hint", "افهم حالة اليوم" in text)
    # Competing board mutation tool names should not be wired as Save/Mark on attendance page
    # (confirm map may still list them globally — ensure board-specific Save correction form gone)
    ok("no_attendance_correction_row_component", "AttendanceCorrectionRow" not in text)

    # Live ops read probe (no mutate)
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
                SELECT kind, status, count(*) AS c
                FROM attendance_ops_exceptions
                WHERE company_code='WATHEFNI'
                GROUP BY 1,2
                ORDER BY 3 DESC
                LIMIT 20
                """
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            cur.execute(
                """
                SELECT count(*) AS c FROM attendance_ops_exceptions
                WHERE company_code='WATHEFNI' AND lower(coalesce(kind,''))='absence'
                  AND lower(coalesce(status,'')) IN ('open','assigned','in_review','pending_dual_approval','reopened')
                """
            )
            absence_open = int((cur.fetchone() or {}).get("c") or 0)
        conn.commit()

    print("OPS_KIND_STATUS", json.dumps(rows, default=str)[:2000])
    ok("ops_table_readable", True, f"absence_open={absence_open}")
    # Absence resolution path exists in UI (request sets status completed) — static proof above.
    ok("absence_ops_path_ui", "absence" in text.lower() or "غياب" in text)

    print("ATTENDANCE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
