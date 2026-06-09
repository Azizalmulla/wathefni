#!/usr/bin/env python3
"""Monthly leave-accrual worker (P1, dark-launched).

Posts idempotent monthly accrual ledger entries for the current calendar year
and recomputes leave balances. No-op unless WATHEFNI_LEAVE_BALANCES is on, so it
is a harmless no-op in production until the flag is enabled. Observe-only:
touches only the leave ledger/balances, never approvals.

Scheduled via wathefni-leave-accrual.service/.timer; can also be run once.
"""

from __future__ import annotations

import argparse
import json
import time

import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Post monthly Wathefni leave accruals.")
    parser.add_argument("--company", type=str, default=None, help="Restrict to one company_code.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of one pass.")
    parser.add_argument("--sleep", type=int, default=86400, help="Seconds to sleep between loop passes.")
    args = parser.parse_args()

    while True:
        result = app.run_leave_accrual_sweep(company_code=args.company)
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(3600, args.sleep))


if __name__ == "__main__":
    main()
