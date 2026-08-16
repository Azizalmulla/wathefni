#!/usr/bin/env python3
"""Wave 3C lifecycle scheduler worker (oneshot).

Runs due terminations + access revokes for allowlisted companies.
Idempotent. No legal/payroll calculations.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    companies = [
        c.strip().upper()
        for c in str(os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    ]
    import app
    import employee_lifecycle_wave3c as lifecycle

    results = []
    failed = False
    for company in companies:
        out = lifecycle.run_lifecycle_scheduler(
            app,
            company_code=company,
            environment=str(os.environ.get("WATHEFNI_ENV") or "staging"),
        )
        results.append(out)
        if not out.get("ok"):
            failed = True
        lag = out.get("lag") or {}
        if lag.get("alert"):
            print(f"LIFECYCLE_LAG_ALERT company={company} lag_seconds={lag.get('lag_seconds')}", flush=True)
    print(json.dumps({"ok": not failed, "results": results}, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
