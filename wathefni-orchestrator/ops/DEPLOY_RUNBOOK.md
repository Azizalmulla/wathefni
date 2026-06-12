# Wathefni Deploy Runbook (staging → production)

Lightweight, single-VPS release process. No CI, no containers. Deploy from the repo
on an operator machine; the script drives the VPS over ssh/rsync.

## Environments

| | Production | Staging |
|---|---|---|
| Service | `wathefni-orchestrator.service` | `wathefni-orchestrator-staging.service` |
| Port (localhost) | `8010` | `8011` |
| Database | `wathefni` | `wathefni_staging` (restored from latest backup) |
| Workspace | `/root/.openclaw/workspaces/company-wathefni` | `/opt/wathefni/staging/workspace` |
| Delivery | `live` (real email/WhatsApp) | `dry_run` (simulated; never sends) |
| Access | `https://api.wathefni.ai` (Caddy) | localhost only — **SSH tunnel** |
| Dashboard token | prod token | separate staging token (`postgres.staging.env`) |

Staging is internal-only. Reach it with an SSH tunnel:
```
ssh -N -L 8011:127.0.0.1:8011 root@<vps>
# then open http://127.0.0.1:8011/dashboard  (use the STAGING dashboard token from
#   /root/.openclaw/secrets/postgres.staging.env, with an HR phone e.g. 96599338566)
```

## Delivery safety
`WATHEFNI_DELIVERY_MODE` gates the two real send paths (`send_email`, `send_octopus_whatsapp[_image]`):
- `live` (default / production): real sends.
- `dry_run` (staging): returns a simulated success and records a `dry_run` outbound event — **no Gmail call, no Octopus HTTP call**. Proven by `smoke-test-delivery-mode.py`.

## Deploy workflow

Always staging first, then production.

```
# 1) Deploy + test on staging
ops/deploy.sh staging
#    - builds dashboard, runs local source smokes
#    - syncs code to /opt/wathefni/staging, migrates staging DB, restarts :8011
#    - runs the staging smoke suite (ops/staging-smoke.sh)
#    - on success records the app.py sha256 as the "staging-green" artifact

# 2) Promote the SAME artifact to production
ops/deploy.sh production
#    - REFUSES unless local app.py matches the staging-green sha256
#    - takes a full backup + snapshots current prod app/dashboard (rollback point)
#    - syncs code, migrates, restarts :8010, republishes dashboard, health-checks
#    - auto-rolls back if the health check fails
```

### Production gate
`deploy.sh production` compares `sha256(app.py)` to `/opt/wathefni/staging/last-green.sha256`
(written by the staging run). If they differ, it refuses — so only a staging-tested build
can reach production.

## Rollback
```
ops/deploy.sh rollback
```
Restores the most recent `/opt/wathefni/backups/predeploy-<stamp>/` snapshot (orchestrator
files + dashboard), restarts the service, reloads Caddy, health-checks. For a DB rollback
(only if a release made a destructive schema change), use `RESTORE_RUNBOOK.md` §4 with the
pre-deploy `db.dump`.

## Staging smoke suite (gate before production)
`ops/staging-smoke.sh` runs:
- `GET /health`, `/dashboard/auth/me`, `/dashboard/prehire/summary`, `/dashboard/team` → 200
- tenant isolation (cross-company fail-closed) against the staging DB
- tenant-read hardening (source)
- dry-run delivery sends nothing real
- entitlement hardening (runtime: viewer read-only, owner can manage)

## Refresh staging from production data
Staging DB is a restored copy. To refresh it from the latest backup:
```
run=$(ls -1dt /opt/wathefni/backups/daily/*/ | head -1); run=${run%/}
tmp=$(mktemp /tmp/staging-XXXX.dump); cp "$run/db.dump" "$tmp"; chown postgres:postgres "$tmp"
sudo -u postgres psql -c "DROP DATABASE IF EXISTS wathefni_staging;"
sudo -u postgres psql -c "CREATE DATABASE wathefni_staging OWNER wathefni_app;"
sudo -u postgres pg_restore --no-owner --no-privileges -d wathefni_staging "$tmp"
sudo -u postgres psql -d wathefni_staging -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO wathefni_app; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO wathefni_app;"
rm -f "$tmp"; systemctl restart wathefni-orchestrator-staging.service
```
(Optionally also `rsync -a --delete /root/.openclaw/workspaces/company-wathefni/ /opt/wathefni/staging/workspace/`.)

## Health after deploy
```
systemctl is-active wathefni-orchestrator.service wathefni-orchestrator-staging.service caddy
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/health     # prod
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8011/health     # staging (or via tunnel)
curl -s -o /dev/null -w '%{http_code}\n' https://api.wathefni.ai/dashboard
```

## Uptime monitoring (dead-man's switch)
- **Destination:** Healthchecks.io (5-min period / 10-min grace). The ping URL is a
  capability secret stored ONLY in `/root/.openclaw/secrets/healthcheck.env`
  (`WATHEFNI_HEALTHCHECK_URL=`, chmod 600) — never in git.
- **What is monitored:** every 5 min, `wathefni-uptime.timer` runs
  `/usr/local/bin/wathefni-healthcheck-ping`, which probes `http://127.0.0.1:8010/health`
  and pings Healthchecks **only** when it returns `200 {"status":"ok"}`. If `/health`
  fails — or the whole VPS is down — no ping is sent, and Healthchecks alerts after the
  grace window. The alert signal is the ABSENCE of a ping.
- **Check status / logs:**
  ```
  systemctl list-timers wathefni-uptime.timer
  tail -n 20 /var/log/wathefni-uptime.log     # "health=200 ping=OK" each run
  ```
- **Test:** force the fail path without touching prod (must log "no ping"):
  ```
  WATHEFNI_HEALTH_URL=http://127.0.0.1:9/health /usr/local/bin/wathefni-healthcheck-ping
  /usr/local/bin/wathefni-healthcheck-ping     # re-ping to leave the check green
  ```
  To see a real downtime alert, let pings stop for >15 min (period + grace).
- **Silence / disable:** `systemctl disable --now wathefni-uptime.timer` (and pause the
  check in the Healthchecks.io UI so it doesn't alert on the silence).

## Notes / limits (by design)
- Single VPS: staging shares CPU/Postgres with prod. Fine at current scale; revisit under load.
- No public staging domain; access is SSH-tunnel only.
- Backups: see `RESTORE_RUNBOOK.md` (daily, encrypted, offsite to B2, restore-drilled).
- Uptime: Healthchecks.io dead-man's switch (above); pings only when `/health` is healthy.
