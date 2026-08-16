#!/usr/bin/env python3
"""Wathefni Calendar C5 sync outbox worker (oneshot)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    import app as app_mod
    import calendar_sync as csync

    result = csync.run_sync_once(app_mod, limit=args.limit, worker_id=f"calendar-sync:{os.getpid()}")
    try:
        import platform_connection_c6 as c6

        expiry = c6.scan_expiring_credentials(app_mod, within_days=14)
        result = {**result, "expiry_scan": {"expiring": expiry.get("expiring"), "newly_notified": expiry.get("newly_notified")}}
    except Exception as exc:
        result = {**result, "expiry_scan_error": str(exc)[:160]}
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
