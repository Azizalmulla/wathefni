#!/usr/bin/env python3
"""Retry worker for the shared outbound delivery layer.

Re-walks the channel ladder (WhatsApp session -> approved template -> email ->
HR task) for pending employee messages whose next_attempt_at has passed, so a
message that hit a transient failure (or a closed conversation that later got an
inbound) is retried and either delivered or escalated to an HR task.

Until a flow is wired through deliver_to_employee (Phase C+), there are no pending
rows and each pass is a harmless no-op. Scheduled via wathefni-delivery-sweep
.service/.timer; can also be run once for ops checks.
"""

from __future__ import annotations

import argparse
import json
import time

import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending Wathefni employee outbound deliveries.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum messages to process per pass.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of running one pass.")
    parser.add_argument("--sleep", type=int, default=120, help="Seconds to sleep between loop passes.")
    args = parser.parse_args()

    while True:
        result = app.run_delivery_sweep(limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(15, args.sleep))


if __name__ == "__main__":
    main()
