#!/usr/bin/env python3
"""Staging-only: copy missing WATHEFNI IT_MANAGER position from prod inventory."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, RealDictCursor


def load_env(path: str) -> None:
    for line in Path(path).read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value.strip().strip('"').strip("'")


def adapt(value):
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def main() -> int:
    load_env("/root/.openclaw/secrets/postgres.env")
    prod = psycopg2.connect(os.environ["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)
    prod.set_session(readonly=True, autocommit=True)
    with prod.cursor() as cur:
        cur.execute(
            "SELECT * FROM positions WHERE company_code=%s AND position_code=%s",
            ("WATHEFNI", "IT_MANAGER"),
        )
        row = cur.fetchone()
    prod.close()
    if not row:
        print(json.dumps({"ok": False, "error": "IT_MANAGER missing in production"}))
        return 1
    row = dict(row)

    for key in [k for k in list(os.environ) if "DATABASE" in k or k.endswith("_URL") or "POSTGRES" in k]:
        os.environ.pop(key, None)
    load_env("/root/.openclaw/secrets/postgres.staging.env")
    stg = psycopg2.connect(os.environ["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)
    with stg.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM positions WHERE company_code=%s AND position_code=%s",
            ("WATHEFNI", "IT_MANAGER"),
        )
        if cur.fetchone():
            print(json.dumps({"ok": True, "skipped": "already_exists"}))
        else:
            cols = list(row.keys())
            values = [adapt(row[c]) for c in cols]
            placeholders = ",".join(["%s"] * len(cols))
            colnames = ",".join(cols)
            cur.execute(
                f"INSERT INTO positions ({colnames}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                values,
            )
            stg.commit()
            print(json.dumps({"ok": True, "inserted": "IT_MANAGER"}))
        cur.execute(
            "SELECT status, count(*) AS c FROM positions WHERE company_code=%s GROUP BY 1 ORDER BY 1",
            ("WATHEFNI",),
        )
        print("staging_counts", [dict(x) for x in cur.fetchall()])
    stg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
