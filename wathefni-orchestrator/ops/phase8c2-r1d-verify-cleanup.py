#!/usr/bin/env python3
"""Staging-only R1D fixture cleanup / schema / production-hash verification."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

COMPANY = "WATHEFNI"
FIXTURE_EMPLOYEE = "WATHEFNI-96550000008401"
EVIDENCE = Path(os.environ.get("R1D_EVIDENCE_DIR", "/opt/wathefni/staging/evidence"))
PROD_APP = Path("/opt/wathefni/orchestrator/app.py")
STAGING_APP = Path("/opt/wathefni/staging/orchestrator/app.py")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if "staging" not in str(os.environ.get("WATHEFNI_POSTGRES_ENV") or "").lower():
        raise SystemExit("refusing to run without staging postgres env")

    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM employees WHERE employee_key=%s", (FIXTURE_EMPLOYEE,))
        employees = int(cur.fetchone()["c"])
        cur.execute("SELECT count(*) AS c FROM employee_app_invites WHERE employee_key=%s", (FIXTURE_EMPLOYEE,))
        invites = int(cur.fetchone()["c"])
        cur.execute(
            "SELECT count(*) AS c FROM employee_status_changes WHERE employee_key=%s",
            (FIXTURE_EMPLOYEE,),
        )
        status_changes = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT count(*) AS c
            FROM hr_tasks
            WHERE company_code=%s
              AND employee_key=%s
            """,
            (COMPANY, FIXTURE_EMPLOYEE),
        )
        hr_tasks = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT enabled
            FROM company_modules
            WHERE company_code=%s AND module_key=%s
            """,
            (COMPANY, "employee_app"),
        )
        row = cur.fetchone()
        module_enabled = None if row is None else bool(row["enabled"])
        cur.execute(
            """
            SELECT count(*) AS c
            FROM dashboard_user_sessions ds
            JOIN dashboard_users du ON du.user_id = ds.user_id
            WHERE du.company_code=%s
              AND COALESCE(du.metadata->>'source','') = 'legacy_hr_phone_bootstrap'
              AND ds.status = 'active'
              AND ds.expires_at > NOW()
            """,
            (COMPANY,),
        )
        recovery = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name IN ('dashboard_user_permission_grants', 'employee_status_changes')
            ORDER BY 1
            """
        )
        tables = [r["table_name"] for r in cur.fetchall()]
        cur.execute(
            """
            SELECT permission, count(*) AS c
            FROM dashboard_user_permission_grants
            WHERE company_code=%s AND status='active'
              AND permission IN ('employees.read','employees.manage','employees.status.approve')
            GROUP BY 1
            ORDER BY 1
            """,
            (COMPANY,),
        )
        grant_counts = {r["permission"]: int(r["c"]) for r in cur.fetchall()}

    # Bundle hash of the accepted staging orchestrator tree (tracked evidence files).
    tracked = []
    for path in sorted(STAGING_APP.parent.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(STAGING_APP.parent).as_posix()
        if rel.startswith((".", "__pycache__", "ops/__pycache__")):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        tracked.append(rel)
    digest = hashlib.sha256()
    for rel in tracked:
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update((STAGING_APP.parent / rel).read_bytes())
        digest.update(b"\0")
    artifact_hash = digest.hexdigest()

    payload = {
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "postgres_env": os.environ.get("WATHEFNI_POSTGRES_ENV"),
        "schema_tables": tables,
        "schema_ok": tables == ["dashboard_user_permission_grants", "employee_status_changes"],
        "fixture_cleanup": {
            "employees": employees,
            "employee_app_invites": invites,
            "employee_status_changes": status_changes,
            "hr_tasks_like_fixture": hr_tasks,
            "employee_app_module_enabled": module_enabled,
            "ok": employees == 0 and invites == 0 and hr_tasks == 0 and module_enabled is False,
        },
        "active_recovery_sessions": recovery,
        "employee_grant_counts": grant_counts,
        "staging_app_sha256": sha256_file(STAGING_APP),
        "artifact_hash": artifact_hash,
        "artifact_file_count": len(tracked),
        "production_app_sha256": sha256_file(PROD_APP),
        "production_unchanged_vs_predeploy": sha256_file(PROD_APP)
        == (EVIDENCE / "r1d-prod-app.sha256").read_text().split()[0],
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "r1d-cleanup-and-artifact.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["fixture_cleanup"]["ok"] and payload["schema_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
