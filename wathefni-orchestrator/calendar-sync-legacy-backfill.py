#!/usr/bin/env python3
"""C5 legacy Google → sync bindings backfill (dry-run by default, tenant-scoped, resumable)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--apply", action="store_true", help="Write bindings (default dry-run)")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--resume-after", default=None)
    args = parser.parse_args()
    import app as app_mod
    import calendar_sync as csync

    result = csync.backfill_legacy_google_bindings(
        app_mod,
        company_code=args.company,
        dry_run=not args.apply,
        limit=args.limit,
        resume_after_event_id=args.resume_after,
    )
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
