#!/usr/bin/env python3
"""READ-ONLY schema discovery for the Wathefni audit. SELECTs only.
Reads WATHEFNI_DATABASE_URL from /root/.openclaw/secrets/postgres.env.
Prints: every public table, its row count, columns (name/type/nullable),
primary keys, and foreign keys. No writes, no DDL."""
import os, sys, json
from pathlib import Path

ENV = Path(os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env"))
if ENV.exists():
    for line in ENV.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

import psycopg2
from psycopg2.extras import RealDictCursor

dsn = os.environ["WATHEFNI_DATABASE_URL"]
conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()

cur.execute("""
  SELECT table_name FROM information_schema.tables
  WHERE table_schema='public' AND table_type='BASE TABLE'
  ORDER BY table_name;
""")
tables = [r["table_name"] for r in cur.fetchall()]

out = {"tables": {}, "foreign_keys": []}

for t in tables:
    cur.execute(f'SELECT count(*) AS n FROM "{t}";')
    n = cur.fetchone()["n"]
    cur.execute("""
      SELECT column_name, data_type, is_nullable, column_default
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name=%s
      ORDER BY ordinal_position;
    """, (t,))
    cols = cur.fetchall()
    out["tables"][t] = {"rows": n, "columns": [
        {"name": c["column_name"], "type": c["data_type"], "nullable": c["is_nullable"],
         "default": (c["column_default"] or "")[:40]} for c in cols]}

# foreign keys
cur.execute("""
  SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
  JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema
  WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'
  ORDER BY tc.table_name;
""")
out["foreign_keys"] = [dict(r) for r in cur.fetchall()]

print("=== TABLE ROW COUNTS (sorted) ===")
for t in sorted(out["tables"], key=lambda x: -out["tables"][x]["rows"]):
    print(f'{out["tables"][t]["rows"]:>10}  {t}')

print("\n=== COLUMNS PER TABLE ===")
for t in tables:
    info = out["tables"][t]
    print(f'\n## {t}  (rows={info["rows"]})')
    for c in info["columns"]:
        flag = "" if c["nullable"] == "YES" else " NOT NULL"
        print(f'   - {c["name"]} : {c["type"]}{flag}')

print("\n=== FOREIGN KEYS ===")
if not out["foreign_keys"]:
    print("(none declared)")
for fk in out["foreign_keys"]:
    print(f'   {fk["table_name"]}.{fk["column_name"]} -> {fk["ref_table"]}.{fk["ref_column"]}')

cur.close(); conn.close()
