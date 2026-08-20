#!/usr/bin/env python3
"""Oneshot worker: domain events → tenant-scoped HR Intelligence projections.

Does not rebuild from the frontend. Does not introduce a second SoT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="HR Intelligence projection freshness worker")
    parser.add_argument("--company", help="Limit to one company_code")
    parser.add_argument("--family", help="Limit rebuild/reconcile to one source family")
    parser.add_argument("--reconcile", action="store_true", help="Force periodic reconcile this pass")
    parser.add_argument("--rebuild", action="store_true", help="Controlled full rebuild/reconciliation")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import app
    import hr_intelligence_projection as proj

    company = str(args.company or os.environ.get("WATHEFNI_HR_INTELLIGENCE_PROJECTION_COMPANY") or "").strip().upper() or None
    family = str(args.family or "").strip().lower() or None
    if family and family not in proj.SOURCE_FAMILIES:
        print(json.dumps({"ok": False, "error": "invalid_family", "family": family}))
        return 2

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            result = proj.run_projection_pass(
                cur,
                company_code=company,
                force_reconcile=bool(args.reconcile),
                rebuild=bool(args.rebuild),
                family=family,
            )
        conn.commit()
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
