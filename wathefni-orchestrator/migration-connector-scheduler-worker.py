#!/usr/bin/env python3
"""Production scheduler for Migration Sync Connected Systems (P5.1).

Claims due schedule_enabled connections and invokes the same run_sync pipeline
as manual Sync now. Safe for concurrent workers via FOR UPDATE SKIP LOCKED +
per-connection sync_lock_until.

Scheduled via wathefni-migration-connector-scheduler.service/.timer.
"""

from __future__ import annotations

import argparse
import json
import time

import app


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Run due employee migration connector syncs.")
    parser.add_argument("--company", type=str, default=None, help="Restrict to one company_code.")
    parser.add_argument("--limit", type=int, default=20, help="Max connections per pass.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of one pass.")
    parser.add_argument("--sleep", type=int, default=60, help="Seconds between loop passes.")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Force auto_commit=false for this pass (ops diagnostics).",
    )
    args = parser.parse_args()

    import employee_migration_connectors as p5

    while True:
        result = p5.run_scheduler_tick(
            app,
            company_code=args.company,
            limit=args.limit,
            auto_commit=not args.preview_only,
        )
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(15, args.sleep))


if __name__ == "__main__":
    main()
