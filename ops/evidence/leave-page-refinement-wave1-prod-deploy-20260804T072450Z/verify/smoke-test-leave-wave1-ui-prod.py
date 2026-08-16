#!/usr/bin/env python3
"""Safe production smoke for Leave Wave 1 UI deploy (read-only + static checks).

Does not approve/decline leave, initiate dual-control, or touch payroll money.
"""
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

    ok("leave_queue_marker", "data-leave-queue" in text or "leave-workspace" in text)
    ok("leave_attention", "data-leave-attention" in text or "leave request" in text.lower())
    ok("primary_action_marker", "data-primary-action" in text)
    ok("open_in_leave", "Open in Leave" in text)
    ok("approve_action", "approve_leave_request" in text)
    ok("dual_initiate", "initiate_leave_stale_dual_control" in text)
    ok("dual_confirm_separate", "confirm_leave_stale_dual_control" in text)
    ok("row_version", "expected_row_version" in text)
    ok("approve_separate_honesty", "Approval is a separate authority" in text or "الاعتماد قرار منفصل" in text)
    ok("balances_nonbinding", "enforced=false" in text or "non-binding" in text.lower() or "غير ملزم" in text)
    ok("unpaid_honesty", "Payroll calculates" in text or "الرواتب تحسب" in text)
    ok("stale_conflict_copy", "Stale version" in text or "تعارض إصدار" in text)
    ok("arabic_rtl_hint", "طلبات بانتظار القرار" in text or "اعتماد" in text)

    # Live leave read probe (no mutate)
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
                FROM leave_requests
                WHERE company_code='WATHEFNI'
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 20
                """
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            cur.execute(
                """
                SELECT count(*) AS c FROM leave_requests
                WHERE company_code='WATHEFNI' AND lower(coalesce(status,''))='requested'
                """
            )
            pending = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute(
                """
                SELECT count(*) AS c FROM leave_dual_control_actions
                WHERE company_code='WATHEFNI' AND status='pending_second'
                """
            )
            dual_pending = int((cur.fetchone() or {}).get("c") or 0)
        conn.commit()

    print("LEAVE_STATUS_COUNTS", json.dumps(rows, default=str)[:2000])
    ok("leave_table_readable", True, f"requested={pending} dual_pending={dual_pending}")
    ok("dual_path_ui", "Start dual-control" in text or "بدء اعتماد مزدوج" in text)
    ok("confirm_path_ui", "Confirm dual-control" in text or "تأكيد الاعتماد المزدوج" in text)

    print("LEAVE_WAVE1_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
