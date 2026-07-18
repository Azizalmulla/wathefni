"""Employee-hub integrity scan (cron-able).

Reports post-hire child rows (attendance, leave, shifts, payroll, availability,
compliance) whose (company_code, employee_key) no longer resolves to a live
employee. Read-only: counts and a few sample keys only, never mutates data.

Exit code is non-zero when orphans are found, so it can be wired to a nightly
systemd timer / cron and alert on drift:

    # /etc/cron.d/wathefni-integrity  (example)
    30 3 * * *  root  cd /opt/wathefni/orchestrator && \
        WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env \
        .venv/bin/python integrity-scan.py >> /var/log/wathefni-integrity.log 2>&1

Usage:
    python3 integrity-scan.py [--company CODE] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

import app


def main() -> int:
    parser = argparse.ArgumentParser(description="Employee-hub orphan integrity scan")
    parser.add_argument("--company", default=None, help="Limit the scan to one company_code")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    report = app.workspace_integrity_scan(args.company)

    if args.json:
        print(json.dumps(report, default=str))
        return 0 if report.get("ok") else 1

    scope = report.get("company_code") or "ALL COMPANIES"
    print(f"Employee-hub integrity scan — {scope}  ({report.get('scanned_at')})")
    tables = report.get("tables") or {}
    for table, info in tables.items():
        if not info.get("present"):
            print(f"  {table:<32} (table not present)")
            continue
        orphans = info.get("orphans") or 0
        marker = "OK " if orphans == 0 else "!! "
        print(f"  {marker}{table:<30} orphans={orphans}")
        for sample in info.get("samples") or []:
            print(f"       - company={sample.get('company_code')} employee_key={sample.get('employee_key')}")

    total = report.get("total_orphans") or 0
    if total == 0:
        print("\nResult: clean — every post-hire row resolves to a live employee.")
        return 0
    print(f"\nResult: {total} orphaned row(s) found — investigate the keys above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
