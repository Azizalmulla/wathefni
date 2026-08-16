# Wathefni Backup & Restore Runbook

Operational guide for backing up and restoring Wathefni. Keep this current; it is the
source of truth during an incident.

## 1. What is backed up

Each run (`/usr/local/bin/backup-wathefni`) produces, under `/opt/wathefni/backups`:

| Artifact | Contents |
|---|---|
| `db.dump` | PostgreSQL `pg_dump -Fc` (custom format) of the `wathefni` database |
| `files.tar.zst` | Candidate CVs, async video interview files, transcripts/evidence on disk, OpenClaw media, public media, dashboard bundle, orchestrator app snapshot, `openclaw.json` |
| `secrets.tar.gz.gpg` | `/root/.openclaw/secrets` (DB password, dashboard token, service account, etc.), **AES256-encrypted** |
| `MANIFEST.txt`, `SHA256SUMS` | Run metadata + integrity checksums |
| `offsite/offsite-<mode>-<stamp>.tar.zst.gpg` | A single AES256-encrypted bundle of all of the above, for offsite copy |

Excluded: `orchestrator/.venv`, `__pycache__`, `*.pyc`, and the backup passphrase file itself.

## 2. Where backups live

- On-VPS, fast restore: `/opt/wathefni/backups/daily/<stamp>/` and `/opt/wathefni/backups/weekly/<stamp>/`
- Encrypted offsite bundles: `/opt/wathefni/backups/offsite/`
- Backup log: `/var/log/wathefni-backup.log`
- Encryption passphrase: `/root/.openclaw/secrets/backup-passphrase` (**also store in a password manager** — offsite restores are impossible without it)

> Backups on the same disk are not disaster-safe on their own. The encrypted offsite
> bundle must be shipped off the VPS (see §7).

## 3. Schedule & retention

- Daily backup: systemd `wathefni-backup.timer` at 02:30 UTC (`Persistent=true`, runs after missed boots).
- Weekly: a copy is auto-promoted on Sundays into `weekly/`.
- Retention: 7 daily + 4 weekly (configurable via `WATHEFNI_BACKUP_DAILY_KEEP` / `WATHEFNI_BACKUP_WEEKLY_KEEP`).

Check status:
```
systemctl list-timers wathefni-backup.timer
journalctl -u wathefni-backup.service --since '2 days ago'
tail -n 40 /var/log/wathefni-backup.log
```

Run a backup on demand:
```
/usr/local/bin/backup-wathefni daily      # or: weekly
```

## 4. Restore the database

```
set -a; . /root/.openclaw/secrets/postgres.env; set +a
RUN=/opt/wathefni/backups/daily/<stamp>          # pick the run to restore

# Option A — restore over the live database (DESTRUCTIVE; stop the app first):
systemctl stop wathefni-orchestrator.service wathefni-video-interview-worker.service
# The dump dir is root-only (700); stage a copy postgres can read:
TMP=$(mktemp /tmp/wathefni-restore-XXXXXX.dump); cp "$RUN/db.dump" "$TMP"; chown postgres:postgres "$TMP"
sudo -u postgres psql -c "DROP DATABASE wathefni;"
sudo -u postgres psql -c "CREATE DATABASE wathefni OWNER wathefni_app;"
sudo -u postgres pg_restore --no-owner --no-privileges -d wathefni "$TMP"
# Grant + make wathefni_app own the restored objects (so it can run schema migrations):
sudo -u postgres psql -d wathefni <<'SQL'
GRANT ALL ON SCHEMA public TO wathefni_app;
GRANT ALL ON ALL TABLES IN SCHEMA public TO wathefni_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO wathefni_app;
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO wathefni_app', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname='public' LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO wathefni_app', r.sequencename);
  END LOOP;
  FOR r IN SELECT table_name FROM information_schema.views WHERE table_schema='public' LOOP
    EXECUTE format('ALTER VIEW public.%I OWNER TO wathefni_app', r.table_name);
  END LOOP;
END$$;
SQL
rm -f "$TMP"
systemctl start wathefni-orchestrator.service wathefni-video-interview-worker.service

# Option B — restore into a separate database for inspection:
sudo -u postgres psql -c "CREATE DATABASE wathefni_restore OWNER wathefni_app;"
sudo -u postgres pg_restore --no-owner --no-privileges -d wathefni_restore "$RUN/db.dump"
```

## 4b. R8 forward migrations — no in-place down path

R8 numbered SQL under `wathefni-orchestrator/migrations/` is **forward-only**.
The ledger is `wathefni_forward_migrations`. Runtime never applies DDL
(`WATHEFNI_SCHEMA_APPLY` is deploy-only).

To roll back a bad schema change: restore `db.dump` from this runbook. Do **not**
invent down-SQL for domain tables. After restore, start services and confirm
`GET /ready` returns HTTP 200.

## 5. Restore files / media / app / config

```
RUN=/opt/wathefni/backups/daily/<stamp>
# Inspect first:
tar --zstd -tf "$RUN/files.tar.zst" | less
# Restore in place (paths are stored relative to /):
tar --zstd -C / -xf "$RUN/files.tar.zst"
# Re-publish the dashboard if needed:
cp -a /opt/wathefni/apps/wathefni-dashboard/dist/. /var/www/wathefni-dashboard/
systemctl reload caddy
```

Restore secrets (only if lost — handle carefully, never place in a public path):
```
gpg --batch --decrypt --passphrase-file /root/.openclaw/secrets/backup-passphrase \
  "$RUN/secrets.tar.gz.gpg" | tar -C /root/.openclaw/secrets -xzf -
chmod 700 /root/.openclaw/secrets && chmod 600 /root/.openclaw/secrets/*
```

## 6. Restore from a remote / offsite encrypted bundle

This is the full disaster path: the VPS is gone and you only have the offsite bundle.

### 6.1 Download the bundle from the remote (rclone)

```
# List what is offsite (newest last):
rclone lsl "$WATHEFNI_BACKUP_RCLONE_REMOTE"          # or: rclone lsl wathefni-offsite:wathefni-backups

# Download the chosen bundle:
mkdir -p /tmp/wathefni-restore && cd /tmp/wathefni-restore
rclone copy "$WATHEFNI_BACKUP_RCLONE_REMOTE/offsite-daily-<stamp>.tar.zst.gpg" .
```

On a brand-new machine, first install + configure rclone with the same B2 application key
(`apt-get install -y rclone` then `rclone config`, remote type `b2`).

### 6.2 Decrypt and unpack

```
cd /tmp/wathefni-restore
BUNDLE=offsite-daily-<stamp>.tar.zst.gpg
# Passphrase comes from your password manager (see §11); write it to a temp file or use --passphrase.
gpg --batch --decrypt --passphrase-file /path/to/backup-passphrase "$BUNDLE" | tar --zstd -xf -
sha256sum -c SHA256SUMS          # must report: db.dump OK, files.tar.zst OK, secrets.tar.gz.gpg OK
pg_restore --list db.dump >/dev/null && echo "db.dump is restorable"
```

### 6.3 Restore the database

Use `/tmp/wathefni-restore` as the run dir and follow §4 Option A (it stages a
postgres-readable copy, restores, and reassigns ownership to `wathefni_app`).

### 6.4 Restore files / media / app / config

```
tar --zstd -C / -xf /tmp/wathefni-restore/files.tar.zst
cp -a /opt/wathefni/apps/wathefni-dashboard/dist/. /var/www/wathefni-dashboard/
systemctl reload caddy
```

### 6.5 Restore secrets (only if lost)

```
gpg --batch --decrypt --passphrase-file /path/to/backup-passphrase \
  /tmp/wathefni-restore/secrets.tar.gz.gpg | tar -C /root/.openclaw/secrets -xzf -
chmod 700 /root/.openclaw/secrets && chmod 600 /root/.openclaw/secrets/*
```

### 6.6 Verify health (see §8), then remove the temp dir

```
rm -rf /tmp/wathefni-restore
```

## 7. Enabling automated offsite

Offsite push is built in but disabled until a destination is configured. Pick one:

- **rclone to Backblaze B2 (recommended — cheap, simple; rclone is already installed):**
  ```
  # Non-interactive remote creation (B2):
  rclone config create wathefni-offsite b2 account <B2_KEY_ID> key <B2_APPLICATION_KEY>
  # Wire it into the scheduled backup:
  install -d -m 700 /etc/systemd/system/wathefni-backup.service.d
  cat >/etc/systemd/system/wathefni-backup.service.d/offsite.conf <<'EOF'
  [Service]
  Environment=WATHEFNI_BACKUP_RCLONE_REMOTE=wathefni-offsite:<BUCKET_NAME>/offsite
  EOF
  systemctl daemon-reload
  ```
- **rsync to a second server:**
  ```
  systemctl edit wathefni-backup.service
  #   Environment=WATHEFNI_BACKUP_RSYNC_TARGET=backup@host:/srv/wathefni-backups
  ```

The encrypted bundle (`offsite-*.tar.zst.gpg`) is what ships offsite; the passphrase is
NOT included in it and must be kept separately.

Interim offsite (until a remote is wired): pull the latest encrypted bundle to a trusted
machine, e.g. from an operator laptop:
```
rsync -az root@<vps>:/opt/wathefni/backups/offsite/ ~/wathefni-offsite/
```

## 8. Health checks after restore

```
systemctl is-active wathefni-orchestrator.service caddy
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/health
curl -s -o /dev/null -w '%{http_code}\n' https://api.wathefni.ai/dashboard
# Authenticated read (use the live dashboard token + an HR phone):
#   GET /dashboard/auth/me, /dashboard/prehire/summary, /dashboard/team  -> 200
```

## 9. Restore drill (do this regularly)

```
/opt/wathefni/orchestrator/ops/restore-drill.sh
```
Restores the latest dump into a throwaway DB, verifies record counts and video-file
linkage, runs an app smoke against the restored DB, then drops the test DB. It never
touches the live database.

## 10. Verify backups any time

```
/opt/wathefni/orchestrator/.venv/bin/python /opt/wathefni/orchestrator/smoke-test-backup-restore.py
```

## 11. Passphrase safety (CRITICAL)

- The backup encryption passphrase lives at: `/root/.openclaw/secrets/backup-passphrase` (root-only, `600`).
- It is **deliberately excluded** from every backup/offsite bundle. Without it, offsite bundles cannot be decrypted.
- Copy its contents into your password manager now (store as e.g. "Wathefni backup passphrase"):
  ```
  cat /root/.openclaw/secrets/backup-passphrase
  ```
- Keep at least one copy of the passphrase somewhere other than the VPS and other than the
  offsite bucket. If both the VPS and your password manager are lost, the encrypted offsite
  backups are unrecoverable by design.
- The B2 application key is what lets the VPS upload offsite; the passphrase is what lets you
  decrypt. Keep them in separate places.
