"""R8 — versioned forward migrations over the Wave 1-BR schema contract.

Runtime still never mutates schema. Apply only when WATHEFNI_SCHEMA_APPLY=1.
Rollback is restore-from-backup, not invented down SQL.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import schema_contract

CONTRACT_VERSION = "r8-forward-migrations-v1"
LEDGER_TABLE = "wathefni_forward_migrations"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
ROLLBACK_RUNBOOK = "wathefni-orchestrator/ops/RESTORE_RUNBOOK.md"

REQUIRED_RELATIONS = [
    LEDGER_TABLE,
    "wathefni_error_events",
]


def list_migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    files = [path for path in MIGRATIONS_DIR.iterdir() if path.suffix == ".sql" and path.name[:4].isdigit()]
    return sorted(files, key=lambda path: path.name)


def checksum_for(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_version(path: Path) -> int:
    return int(path.name[:4])


def file_sequence_errors(files: list[Path] | None = None) -> list[str]:
    paths = files if files is not None else list_migration_files()
    versions = [parse_version(path) for path in paths]
    errors: list[str] = []
    if versions and versions[0] != 1:
        errors.append(f"expected_1_got_{versions[0]}")
    for index in range(1, len(versions)):
        expected = versions[index - 1] + 1
        if versions[index] != expected:
            errors.append(f"expected_{expected}_got_{versions[index]}")
    return errors


def ensure_ledger(cur: Any) -> None:
    schema_contract.apply_sql(
        cur,
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
          version integer PRIMARY KEY,
          name text NOT NULL,
          checksum text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        module="r8.forward_migrations.ledger",
    )


def applied_rows(cur: Any) -> list[dict[str, Any]]:
    try:
        cur.execute(
            f"SELECT version, name, checksum, applied_at FROM {LEDGER_TABLE} ORDER BY version"
        )
    except Exception:
        return []
    rows = []
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            rows.append(dict(row))
        else:
            rows.append(
                {
                    "version": int(row[0]),
                    "name": str(row[1]),
                    "checksum": str(row[2]),
                    "applied_at": row[3],
                }
            )
    return rows


def history(cur: Any) -> list[dict[str, Any]]:
    return applied_rows(cur)


def pending(cur: Any) -> list[dict[str, Any]]:
    applied = {int(row["version"]) for row in applied_rows(cur)}
    out = []
    for path in list_migration_files():
        version = parse_version(path)
        if version not in applied:
            out.append({"version": version, "name": path.name, "checksum": checksum_for(path)})
    return out


def detect_drift(cur: Any) -> dict[str, Any]:
    applied = {int(row["version"]): row for row in applied_rows(cur)}
    files = {parse_version(path): path for path in list_migration_files()}
    checksum_mismatch = []
    for version, path in files.items():
        row = applied.get(version)
        if row and str(row.get("checksum") or "") != checksum_for(path):
            checksum_mismatch.append(version)
    missing_files = sorted(set(applied) - set(files))
    missing_applied = sorted(set(files) - set(applied))
    sequence_errors = file_sequence_errors()
    missing_relations: list[str] = []
    try:
        schema_contract.require_relations(cur, REQUIRED_RELATIONS, module="r8.drift")
    except schema_contract.SchemaNotMigratedError as exc:
        missing_relations = list(exc.missing)
    drifted = bool(checksum_mismatch or missing_files or missing_relations or sequence_errors)
    return {
        "ok": not drifted and not missing_applied,
        "drifted": drifted,
        "pending": missing_applied,
        "checksum_mismatch": checksum_mismatch,
        "applied_without_file": missing_files,
        "missing_relations": missing_relations,
        "sequence_errors": sequence_errors,
    }


def apply_pending(cur: Any) -> list[dict[str, Any]]:
    if not schema_contract.schema_apply_allowed():
        raise RuntimeError("schema_apply_forbidden:r8.forward_migrations")
    gaps = file_sequence_errors()
    if gaps:
        raise RuntimeError(f"migration_order_gap:{','.join(gaps)}")
    ensure_ledger(cur)
    applied = applied_rows(cur)
    last = int(applied[-1]["version"]) if applied else 0
    done: list[dict[str, Any]] = []
    for path in list_migration_files():
        version = parse_version(path)
        row = next((item for item in applied if int(item["version"]) == version), None)
        if row:
            if str(row.get("checksum") or "") != checksum_for(path):
                raise RuntimeError(f"migration_checksum_changed:{path.name}")
            last = max(last, version)
            continue
        if version != last + 1:
            raise RuntimeError(f"migration_order_gap:expected_{last + 1}_got_{version}")
        schema_contract.apply_sql(
            cur,
            path.read_text(encoding="utf-8"),
            module=f"r8.migration.{path.stem}",
        )
        cur.execute(
            f"""
            INSERT INTO {LEDGER_TABLE} (version, name, checksum)
            VALUES (%s, %s, %s)
            """,
            (version, path.name, checksum_for(path)),
        )
        last = version
        done.append({"version": version, "name": path.name})
    return done


def apply_with_connection(app_mod: Any) -> list[dict[str, Any]]:
    if not schema_contract.schema_apply_allowed():
        raise RuntimeError("schema_apply_forbidden:r8.forward_migrations")
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            done = schema_contract.with_deploy_advisory_lock(cur, apply_pending)
        conn.commit()
    return done


def readiness_snapshot(app_mod: Any) -> dict[str, Any]:
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                drift = detect_drift(cur)
                applied = applied_rows(cur)
                waiting = pending(cur)
    except Exception as exc:
        return {
            "ok": False,
            "error": "migration_status_unavailable",
            "rollback_runbook": ROLLBACK_RUNBOOK,
            "detail": str(exc.__class__.__name__),
        }
    return {
        "ok": bool(drift.get("ok")),
        "applied": [row["version"] for row in applied],
        "pending": [row["version"] for row in waiting],
        "drift": {
            key: drift[key]
            for key in (
                "drifted",
                "checksum_mismatch",
                "missing_relations",
                "applied_without_file",
                "sequence_errors",
            )
        },
        "forward_only": True,
        "rollback_runbook": ROLLBACK_RUNBOOK,
        "contract": CONTRACT_VERSION,
    }


def rollback_procedure() -> dict[str, Any]:
    return {
        "mode": "restore_from_backup",
        "forward_migrations_are_not_reversed_in_place": True,
        "runbook": ROLLBACK_RUNBOOK,
        "steps": [
            "Stop orchestrator and workers.",
            "Select a backup stamp from /opt/wathefni/backups/daily or weekly.",
            "Restore db.dump with pg_restore as documented in RESTORE_RUNBOOK.md.",
            "Restore files.tar.zst if object storage is required.",
            "Start services and hit /ready.",
            "Do not invent down-SQL for domain tables.",
        ],
    }


def main() -> int:
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "rollback-procedure":
        print(json.dumps(rollback_procedure(), indent=2))
        return 0
    if command == "files":
        print(json.dumps([path.name for path in list_migration_files()]))
        return 0
    if command == "apply":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import app  # noqa: WPS433

        done = apply_with_connection(app)
        print(json.dumps({"applied": done}, indent=2))
        return 0
    print(json.dumps({"error": "db_required_for_status_or_apply", "hint": command}, indent=2))
    return 0 if command in {"files", "rollback-procedure"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
