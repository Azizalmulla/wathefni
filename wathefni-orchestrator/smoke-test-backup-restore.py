"""Backup verification smoke checks (run on the VPS).

Verifies the latest backup is present, non-empty, internally consistent, restorable
in form (pg_restore --list), the offsite encrypted bundle exists, the file archive
contains company-scoped paths, and the backup log shows a recent success.

Run:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-backup-restore.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKUP_ROOT = Path("/opt/wathefni/backups")
LOG_FILE = Path("/var/log/wathefni-backup.log")


def fail(message: str) -> None:
    print(f"FAILED: {message}")
    sys.exit(1)


def latest_daily_run() -> Path:
    daily = BACKUP_ROOT / "daily"
    runs = sorted([p for p in daily.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True) if daily.exists() else []
    if not runs:
        fail("no daily backup run found")
    return runs[0]


def main() -> None:
    run = latest_daily_run()
    print(f"latest daily run: {run.name}")

    # 1) Core artifacts exist and are non-empty.
    for name in ("db.dump", "files.tar.zst", "secrets.tar.gz.gpg", "MANIFEST.txt", "SHA256SUMS"):
        artifact = run / name
        if not artifact.exists() or artifact.stat().st_size == 0:
            fail(f"missing or empty artifact: {artifact}")
    print("core artifacts present and non-empty")

    # 2) Checksums match.
    res = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=run, text=True, capture_output=True)
    if res.returncode != 0:
        fail(f"checksum verification failed:\n{res.stdout}\n{res.stderr}")
    print("sha256 checksums verified")

    # 3) DB dump is a readable custom-format archive with data.
    res = subprocess.run(["pg_restore", "--list", str(run / "db.dump")], text=True, capture_output=True)
    if res.returncode != 0:
        fail(f"pg_restore --list failed: {res.stderr}")
    table_data = sum(1 for line in res.stdout.splitlines() if "TABLE DATA" in line)
    if table_data <= 0:
        fail("db.dump has no TABLE DATA entries")
    print(f"pg_restore --list OK ({table_data} table-data entries)")

    # 4) Encrypted offsite bundle exists for this run.
    offsite = BACKUP_ROOT / "offsite"
    bundles = list(offsite.glob(f"offsite-*-{run.name}.tar.zst.gpg")) if offsite.exists() else []
    if not bundles or bundles[0].stat().st_size == 0:
        fail("no non-empty offsite encrypted bundle for latest run")
    print(f"offsite bundle present: {bundles[0].name}")

    # 5) File archive contains company-scoped candidate/workspace paths.
    res = subprocess.run(["tar", "--zstd", "-tf", str(run / "files.tar.zst")], text=True, capture_output=True)
    if res.returncode != 0:
        fail(f"cannot list files.tar.zst: {res.stderr}")
    listing = res.stdout
    if "workspaces/company-wathefni" not in listing:
        fail("file archive missing company-scoped workspace path")
    print("file archive contains company-scoped workspace paths")

    # 6) Backup log shows a recent SUCCESS.
    if not LOG_FILE.exists():
        fail("backup log missing")
    tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
    if not any("SUCCESS" in line for line in tail):
        fail("no SUCCESS line in recent backup log")
    print("backup log shows recent SUCCESS")

    print("backup verification smoke checks passed")


if __name__ == "__main__":
    main()
