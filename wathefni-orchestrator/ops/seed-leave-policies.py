"""Seed leave-balance presets + per-company leave policies (P1).

Idempotent and INERT: it seeds the configurable Kuwait private-sector preset
catalog and clones it into per-company `leave_policies` for companies that have
the leave module enabled. Everything is seeded with `enforced=false` and
`legal_reviewed=false` — the figures are configurable presets that require legal
review before any enforcement is switched on. Nothing here blocks approvals.

Run (the host provides psycopg2 + the postgres env):
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env \
  WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni \
  /opt/wathefni/orchestrator/.venv/bin/python ops/seed-leave-policies.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(orchestrator_dir))
    import app

    presets = app.seed_leave_policy_presets()
    print(f"presets seeded (new rows): {presets}")

    companies: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code FROM companies ORDER BY company_code")
            companies = [str(dict(r)["company_code"]) for r in cur.fetchall()]

    total = 0
    for company in companies:
        if not app.company_has_module(company, "leave"):
            continue
        seeded = app.seed_company_leave_policies(company)
        if seeded:
            print(f"  {company}: seeded {seeded} leave policy row(s)")
        total += seeded
    print(f"company leave policies seeded (new rows): {total}")
    print("DONE — all seeded inert (enforced=false, legal_reviewed=false).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
