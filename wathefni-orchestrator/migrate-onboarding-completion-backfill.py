#!/usr/bin/env python3
"""Backfill the canonical onboarding completion snapshot for existing employees.

Two things happen per employee, in this order:

1. If the employee reads as complete under the legacy `employees.onboarding_status`
   but has no completion snapshot, stamp `first_completed_at` from the best
   available historical timestamp. Completion that predates the contract is
   preserved as evidence rather than being silently forgotten.
2. Recompute the canonical snapshot. A legacy-complete employee who now has open
   required work therefore lands on `reopened`, not `waiting_on_*`.

Idempotent: re-running changes nothing once an employee is stamped and current.

Usage:
  ./.venv/bin/python migrate-onboarding-completion-backfill.py            # dry run
  ./.venv/bin/python migrate-onboarding-completion-backfill.py --apply
  ./.venv/bin/python migrate-onboarding-completion-backfill.py --apply --company WATHEFNI
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

LEGACY_COMPLETE_STATUSES = {"completed", "complete", "done"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default is dry run)")
    parser.add_argument("--company", default=None, help="limit to one company code")
    parser.add_argument("--limit", type=int, default=0, help="cap employees processed")
    args = parser.parse_args()

    import app
    import onboarding_completion_contract as C

    where = ["coalesce(employment_status,'active') <> 'left'"]
    params: list[Any] = []
    if args.company:
        where.append("company_code=%s")
        params.append(args.company.upper())

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            C.ensure_completion_schema(cur)
            cur.execute(
                f"""
                SELECT e.employee_key, e.company_code, e.onboarding_status, e.updated_at,
                       e.created_at, c.first_completed_at
                FROM employees e
                LEFT JOIN employee_onboarding_completion c
                  ON c.company_code=e.company_code AND c.employee_key=e.employee_key
                WHERE {' AND '.join(where)}
                ORDER BY e.created_at
                """,
                tuple(params),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()

    if args.limit:
        rows = rows[: args.limit]

    states = Counter()
    stamped = 0
    failures: list[dict[str, Any]] = []
    print(f"employees to process: {len(rows)} (apply={args.apply})")

    for row in rows:
        key = str(row["employee_key"])
        company = str(row["company_code"] or "WATHEFNI").upper()
        legacy_complete = str(row.get("onboarding_status") or "").strip().lower() in LEGACY_COMPLETE_STATUSES
        needs_stamp = legacy_complete and not row.get("first_completed_at")

        if not args.apply:
            if needs_stamp:
                stamped += 1
            states["(dry-run)"] += 1
            continue

        try:
            # Each employee in its own transaction: one bad row cannot abort the run.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    if needs_stamp:
                        when = row.get("updated_at") or row.get("created_at")
                        if C.seed_legacy_completion_history(
                            cur,
                            company_code=company,
                            employee_key=key,
                            completed_at=when,
                            source="legacy_onboarding_status",
                        ):
                            stamped += 1
                    snap = C.recompute(
                        cur, employee_key=key, company_code=company, actor="completion_backfill"
                    )
                    states[str(snap.get("state"))] += 1
                conn.commit()
        except Exception as exc:
            failures.append({"employee_key": key, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})

    print(f"legacy completion stamps written: {stamped}")
    print("resulting states: " + json.dumps(dict(states), sort_keys=True))
    if failures:
        print(f"failures: {len(failures)}")
        for f in failures[:20]:
            print("  !", f["employee_key"], f["error"])
        return 1
    if not args.apply:
        print("dry run only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
