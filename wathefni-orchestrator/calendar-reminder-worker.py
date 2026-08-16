#!/usr/bin/env python3
"""Calendar C4 — reminder + delivery worker (oneshot).

Reminders notify only; they never create calendar blocks.
Delivery failures never mutate or delete Calendar event truth.
"""

from __future__ import annotations

import argparse
import json
import time

import app
import calendar_participation as cpart


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Process Wathefni Calendar reminders and delivery outbox.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep", type=int, default=30)
    args = parser.parse_args()

    while True:
        result = cpart.run_reminders_once(app, limit=args.limit)
        print(json.dumps({"ok": True, **{k: result[k] for k in ("reminders_processed",) if k in result}, "delivery_processed": (result.get("delivery") or {}).get("processed")}))
        if not args.loop:
            break
        time.sleep(max(5, args.sleep))


if __name__ == "__main__":
    main()
