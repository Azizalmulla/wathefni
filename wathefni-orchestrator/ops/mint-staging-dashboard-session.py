#!/usr/bin/env python3
"""Mint a backend-current dashboard session for staging HTTP smokes.

Server-side only. Does not print secrets other than a short-lived session token
to stdout for the calling smoke harness. Prefer an active normal owner; never
falls back to legacy_untrusted shared-token auth.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default="WATHEFNI")
    parser.add_argument("--role", default="owner")
    args = parser.parse_args()

    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

    import app

    company = str(args.company or "WATHEFNI").strip().upper()
    role = str(args.role or "owner").strip().lower()
    app.ensure_schema()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM dashboard_users
                WHERE company_code=%s
                  AND status='active'
                  AND role=%s
                  AND COALESCE(metadata->>'source','') <> 'legacy_hr_phone_bootstrap'
                  AND lower(email) NOT LIKE '%%.wathefni.local'
                ORDER BY accepted_at NULLS LAST, updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company, role),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT *
                    FROM dashboard_users
                    WHERE company_code=%s AND status='active' AND role=%s
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company, role),
                )
                row = cur.fetchone()
    if not row:
        print(f"no active {role} for {company}", file=sys.stderr)
        return 1
    user = dict(row)
    token, _expires = app.create_dashboard_session(user)
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
