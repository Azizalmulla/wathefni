#!/usr/bin/env python3
"""Reconcile employee-app document objects not finalized canonically."""

from __future__ import annotations

import argparse
import json
import time

import app


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Reconcile pending employee document storage operations.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum operations to process per pass.")
    parser.add_argument("--company", help="Optional company scope.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of running one pass.")
    parser.add_argument("--sleep", type=int, default=300, help="Seconds between loop passes.")
    args = parser.parse_args()
    while True:
        result = app.run_document_storage_reconciliation(limit=args.limit, company_code=args.company)
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(30, args.sleep))


if __name__ == "__main__":
    main()
