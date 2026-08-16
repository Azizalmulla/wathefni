#!/usr/bin/env python3
"""Calendar C2 outbox worker — claim/process calendar_link_outbox rows.

Interview truth is already committed; this worker projects to Wathefni Calendar.
Safe to run when the calendar module is disabled (rows defer). Scheduled via
wathefni-calendar-outbox.service/.timer.
"""

from __future__ import annotations

import argparse
import json
import time

import app
import calendar_outbox


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Process Wathefni Calendar interview link outbox.")
    parser.add_argument("--limit", type=int, default=50, help="Max outbox rows per pass.")
    parser.add_argument("--company", default=None, help="Optional tenant filter.")
    parser.add_argument("--loop", action="store_true", help="Keep polling.")
    parser.add_argument("--sleep", type=int, default=30, help="Seconds between loop passes.")
    args = parser.parse_args()

    while True:
        result = calendar_outbox.run_outbox_once(
            app,
            limit=args.limit,
            company_code=args.company,
        )
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(5, args.sleep))


if __name__ == "__main__":
    main()
