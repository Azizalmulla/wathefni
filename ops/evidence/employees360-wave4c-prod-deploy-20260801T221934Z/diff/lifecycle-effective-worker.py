#!/usr/bin/env python3
"""Wave 3C/3E lifecycle + Wave 4C org activate-due scheduler worker (oneshot).

Runs due terminations + access revokes for allowlisted companies.
When ORG_V4 is enabled and activate-due is not killed, also syncs due
assignment slices (shared timer — no separate org timer required).
Idempotent. No legal/payroll calculations.
Supports optional one-shot failure inject via FAIL_ONCE_FILE for retry drills.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def _flag_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name) or default).strip().lower() in {"on", "1", "true", "yes"}


def main() -> int:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    companies = [
        c.strip().upper()
        for c in str(os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    ]
    org_companies = [
        c.strip().upper()
        for c in str(os.environ.get("WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    ]
    fail_file = Path(
        str(os.environ.get("WATHEFNI_LIFECYCLE_SCHEDULER_FAIL_ONCE_FILE") or "/tmp/wathefni-lifecycle-fail-once")
    )
    inject_fail = fail_file.exists()
    if inject_fail:
        try:
            fail_file.unlink()
        except FileNotFoundError:
            pass
        print(f"LIFECYCLE_INJECT_FAIL consumed={fail_file}", flush=True)

    import app
    import employee_lifecycle_wave3c as lifecycle

    results = []
    org_results = []
    failed = False
    for company in companies:
        out = lifecycle.run_lifecycle_scheduler(
            app,
            company_code=company,
            environment=str(os.environ.get("WATHEFNI_ENV") or "staging"),
            fail_before_commit=inject_fail,
        )
        results.append(out)
        if not out.get("ok"):
            failed = True
        lag = out.get("lag") or {}
        if lag.get("alert"):
            print(f"LIFECYCLE_LAG_ALERT company={company} lag_seconds={lag.get('lag_seconds')}", flush=True)

    # Wave 4C: share this timer for unattended future-assignment activation.
    # Kill switch: WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE=off (or ORG_V4 off).
    activate_due_enabled = _flag_on("WATHEFNI_EMPLOYEE_ORG_V4") and _flag_on(
        "WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE", "on"
    )
    if activate_due_enabled:
        import employee_org_wave4 as org_w4

        today = date.today()
        lookback = int(str(os.environ.get("WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_LOOKBACK_DAYS") or "7"))
        lookback = max(0, min(lookback, 30))
        for company in org_companies:
            if not org_w4.org_v4_enabled(company):
                org_results.append({"company": company, "ok": False, "error": "org_v4_disabled"})
                continue
            day_outs = []
            for delta in range(lookback, -1, -1):
                as_of = today - timedelta(days=delta)
                out = org_w4.activate_due_assignment_slices(app, company_code=company, as_of=as_of)
                day_outs.append(out)
                if not out.get("ok"):
                    failed = True
            # Lag: covering slices whose effective_from is in the past but Wave 2 manager differs.
            lag_rows = []
            try:
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        org_w4.ensure_org_wave4_schema(cur)
                        cur.execute(
                            """
                            SELECT h.employee_key, h.effective_from, h.manager_employee_key AS hist_mgr,
                                   a.manager_employee_key AS wave2_mgr
                            FROM employee_org_assignment_history h
                            JOIN employee_key_authority_map m
                              ON m.company_code=h.company_code AND m.employee_key=h.employee_key
                            JOIN employee_assignments a
                              ON a.assignment_id=m.assignment_id AND a.company_code=h.company_code
                            WHERE h.company_code=%s
                              AND h.effective_from <= %s
                              AND (h.effective_to IS NULL OR h.effective_to >= %s)
                              AND coalesce(h.manager_employee_key,'') IS DISTINCT FROM coalesce(a.manager_employee_key,'')
                            LIMIT 50
                            """,
                            (company, today, today),
                        )
                        lag_rows = [dict(r) for r in (cur.fetchall() or [])]
                    conn.commit()
            except Exception as exc:  # noqa: BLE001 — lag probe must not crash worker
                lag_rows = [{"error": str(exc)}]
            if lag_rows and not any(r.get("error") for r in lag_rows):
                print(
                    f"ORG_ACTIVATE_LAG_ALERT company={company} count={len(lag_rows)}",
                    flush=True,
                )
            org_results.append(
                {
                    "company": company,
                    "ok": all(d.get("ok") for d in day_outs),
                    "days": day_outs,
                    "lag_count": len(lag_rows) if not any(r.get("error") for r in lag_rows) else -1,
                    "lag_sample": lag_rows[:5],
                }
            )
    else:
        print("ORG_ACTIVATE_DUE skipped (kill switch or ORG_V4 off)", flush=True)

    print(
        json.dumps(
            {
                "ok": not failed,
                "inject_fail": inject_fail,
                "results": results,
                "org_activate_due": {
                    "enabled": activate_due_enabled,
                    "results": org_results,
                },
            },
            default=str,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
