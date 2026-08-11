#!/usr/bin/env bash
# Pre-Customer Hardening Wave — orchestrator deploy.
#
# Ships: onboarding_items tenant column + scoped reads/writes, candidate tenant
# integrity (backfill + NOT NULL), real leave provenance, HR Web task
# stale-write guard, urgent task ordering, queue pagination contracts.
#
# Backs up every touched file and the two tables that change shape before
# anything is applied. Idempotent: safe to re-run.
set -euo pipefail

VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_ROOT="/opt/wathefni/orchestrator"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/opt/wathefni/backups/pre-customer-hardening-$STAMP"

FILES=(
  app.py
  operator_mobile_data.py
  outbound_delivery.py
  action_registry.py
  onboarding_wave2.py
  employee_migration_lifecycle.py
)

echo "== backup -> $BACKUP"
ssh -o BatchMode=yes "$VPS_HOST" "mkdir -p '$BACKUP/code'"
for f in "${FILES[@]}"; do
  ssh -o BatchMode=yes "$VPS_HOST" "cp '$REMOTE_ROOT/$f' '$BACKUP/code/$f'"
done
ssh -o BatchMode=yes "$VPS_HOST" "cd '$REMOTE_ROOT' && ORCH_PID=\$(systemctl show -p MainPID --value wathefni-orchestrator) BACKUP='$BACKUP' .venv/bin/python - " <<'ENDPY'
import csv, os, sys
pid = os.environ["ORCH_PID"]
with open("/proc/%s/environ" % pid, "rb") as fh:
    for item in fh.read().split(b"\0"):
        if item and b"=" in item:
            k, v = item.split(b"=", 1)
            os.environ[k.decode()] = v.decode()
os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app

backup = os.environ["BACKUP"]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        for table in ("candidates", "onboarding_items"):
            cur.execute("SELECT * FROM %s" % table)
            rows = cur.fetchall()
            path = os.path.join(backup, "%s.csv" % table)
            if rows:
                with open(path, "w", newline="") as out:
                    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(row)
            print("backed_up", table, len(rows))
ENDPY

echo "== ship code"
for f in "${FILES[@]}"; do
  rsync -az -e "ssh -o BatchMode=yes" "$SRC/$f" "$VPS_HOST:$REMOTE_ROOT/$f"
done

echo "== candidate tenant cleanup (audited)"
ssh -o BatchMode=yes "$VPS_HOST" "cd '$REMOTE_ROOT' && ORCH_PID=\$(systemctl show -p MainPID --value wathefni-orchestrator) .venv/bin/python - " <<'ENDPY'
import json, os, sys
pid = os.environ["ORCH_PID"]
with open("/proc/%s/environ" % pid, "rb") as fh:
    for item in fh.read().split(b"\0"):
        if item and b"=" in item:
            k, v = item.split(b"=", 1)
            os.environ[k.decode()] = v.decode()
os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app

with app.db_connect() as conn:
    with conn.cursor() as cur:
        # 1. Attribute every candidate whose applications name exactly one company.
        cur.execute(
            """
            UPDATE candidates c
            SET active_company_code = src.company_code, updated_at = now()
            FROM (
              SELECT phone, max(company_code) AS company_code
              FROM applications
              WHERE COALESCE(company_code,'') <> ''
              GROUP BY phone
              HAVING count(DISTINCT company_code) = 1
            ) src
            WHERE c.phone = src.phone AND COALESCE(c.active_company_code,'') = ''
            RETURNING c.phone, c.active_company_code
            """
        )
        attributed = cur.fetchall()
        print("attributed_from_applications", json.dumps(attributed, default=str))

        # 2. Anything still unowned has no application and no tenant. Only delete
        #    it when nothing anywhere references the phone.
        cur.execute("SELECT phone, name, data_source FROM candidates WHERE active_company_code IS NULL")
        orphans = cur.fetchall()
        cur.execute(
            """
            SELECT table_name FROM information_schema.columns
            WHERE table_schema='public' AND column_name='phone' AND table_name <> 'candidates'
            """
        )
        tables = [r["table_name"] for r in cur.fetchall()]
        deletable, retained = [], []
        for row in orphans:
            phone = row["phone"]
            refs = {}
            for table in tables:
                try:
                    cur.execute("SELECT count(*) AS n FROM %s WHERE phone = %%s" % table, (phone,))
                    n = cur.fetchone()["n"]
                    if n:
                        refs[table] = n
                except Exception:
                    conn.rollback()
            (retained if refs else deletable).append({**row, "refs": refs})

        print("orphans_retained", json.dumps(retained, default=str))
        print("orphans_deletable", json.dumps(deletable, default=str))
        if deletable:
            cur.execute(
                "DELETE FROM candidates WHERE phone = ANY(%s) AND active_company_code IS NULL",
                ([r["phone"] for r in deletable],),
            )
            print("orphans_deleted", cur.rowcount)
    conn.commit()

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM candidates WHERE active_company_code IS NULL")
        remaining = cur.fetchone()["n"]
print("candidates_null_company_remaining", remaining)
ENDPY

echo "== schema apply (advisory lock)"
ssh -o BatchMode=yes "$VPS_HOST" "cd '$REMOTE_ROOT' && ORCH_PID=\$(systemctl show -p MainPID --value wathefni-orchestrator) WATHEFNI_SCHEMA_APPLY=1 .venv/bin/python - " <<'ENDPY'
import os, sys
pid = os.environ["ORCH_PID"]
keep = os.environ.get("WATHEFNI_SCHEMA_APPLY")
with open("/proc/%s/environ" % pid, "rb") as fh:
    for item in fh.read().split(b"\0"):
        if item and b"=" in item:
            k, v = item.split(b"=", 1)
            os.environ[k.decode()] = v.decode()
os.environ["WATHEFNI_SCHEMA_APPLY"] = keep or "1"
os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app
import schema_contract as sc

assert sc.schema_apply_allowed(), "WATHEFNI_SCHEMA_APPLY must be on"
app.ensure_schema(force=True)
print("schema_applied", sc.counters())

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE company_code IS NULL) AS unstamped,
                   count(*) AS total
            FROM onboarding_items
            """
        )
        print("onboarding_items", dict(cur.fetchone()))
        cur.execute(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name='candidates' AND column_name='active_company_code'
            """
        )
        print("candidates_active_company_nullable", cur.fetchone()["is_nullable"])
ENDPY

# HR web bundle: the Caddyfile serves /opt/wathefni/dashboard-dist. The older
# /var/www/wathefni-dashboard path in legacy deploy scripts is no longer served.
if [[ -d "$ROOT/apps/wathefni-dashboard/dist" ]]; then
  echo "== ship HR web bundle"
  ssh -o BatchMode=yes "$VPS_HOST" "mkdir -p '$BACKUP/dashboard-dist' && rsync -a /opt/wathefni/dashboard-dist/ '$BACKUP/dashboard-dist/'"
  rsync -az -e "ssh -o BatchMode=yes" "$ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:/tmp/dash-live-$STAMP/"
  ssh -o BatchMode=yes "$VPS_HOST" "rsync -a --delete /tmp/dash-live-$STAMP/ /opt/wathefni/dashboard-dist/ && rm -rf /tmp/dash-live-$STAMP"
fi

echo "== restart + health"
ssh -o BatchMode=yes "$VPS_HOST" "systemctl restart wathefni-orchestrator.service && sleep 8 && curl -fsS localhost:8010/health && echo && curl -fsS localhost:8010/ready | head -c 400"
echo
echo "PRE_CUSTOMER_HARDENING_DEPLOY_OK backup=$BACKUP"
