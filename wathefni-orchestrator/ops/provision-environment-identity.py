#!/usr/bin/env python3
"""Provision one immutable database environment marker.

This is an explicit operator migration. Application startup never creates or
updates the marker because doing so could bless an incorrectly selected DB.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_environment import fingerprint, read_env_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--environment", choices=("staging", "production"), required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--expected-port", type=int, required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if not args.apply:
        raise SystemExit("refusing: --apply is required")
    if args.confirm != f"{args.environment}:{args.expected_database}:{args.marker}":
        raise SystemExit("refusing: confirmation does not match environment/database/marker")
    if args.environment == "production" and not args.allow_production:
        raise SystemExit("refusing: production requires --allow-production")
    if args.environment == "staging" and args.expected_database == "wathefni":
        raise SystemExit("refusing: staging cannot provision production database")
    if args.environment == "production" and args.expected_database == "wathefni_staging":
        raise SystemExit("refusing: production cannot provision staging database")

    values = read_env_file(Path(args.env_file))
    dsn = values.get("WATHEFNI_DATABASE_URL", "")
    parsed = urlparse(dsn)
    configured_host = str(parsed.hostname or "").lower()
    configured_port = int(parsed.port or 5432)
    configured_database = unquote(str(parsed.path or "").lstrip("/"))
    if (configured_host, configured_port, configured_database) != (
        args.expected_host.lower(),
        args.expected_port,
        args.expected_database,
    ):
        raise SystemExit("refusing: env-file host/port/database does not match explicit identity")

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor, application_name="wathefni_identity_provision")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS database_name")
            if str((cur.fetchone() or {}).get("database_name") or "") != args.expected_database:
                raise SystemExit("refusing: connected database does not match expected database")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS wathefni_environment_identity (
                  identity_key text PRIMARY KEY CHECK (identity_key='primary'),
                  environment text NOT NULL CHECK (environment IN ('staging','production')),
                  marker text NOT NULL UNIQUE,
                  created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                SELECT environment, marker
                FROM wathefni_environment_identity
                WHERE identity_key='primary'
                FOR UPDATE
                """
            )
            existing = cur.fetchone()
            if existing:
                if (
                    str(existing.get("environment") or "") != args.environment
                    or str(existing.get("marker") or "") != args.marker
                ):
                    raise SystemExit("refusing: existing database identity does not match")
            else:
                cur.execute(
                    """
                    INSERT INTO wathefni_environment_identity (identity_key, environment, marker)
                    VALUES ('primary', %s, %s)
                    """,
                    (args.environment, args.marker),
                )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        "environment identity provisioned:",
        {
            "environment": args.environment,
            "database_fingerprint": fingerprint(args.expected_database),
            "host_fingerprint": fingerprint(args.expected_host),
            "marker_fingerprint": fingerprint(args.marker),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
