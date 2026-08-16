"""Deadlock Remediation Wave 1-BR — schema apply vs runtime validate contract.

Long-term rule:
- Schema mutations (CREATE/ALTER/INDEX) run only through an explicit, serialized
  deployment migration step with WATHEFNI_SCHEMA_APPLY enabled.
- Runtime API/workers may validate required relations, never mutate schema.
- Missing schema fails closed with SchemaNotMigratedError.
- Deploy migrators take a PostgreSQL advisory lock so concurrent migrators cannot race.
"""

from __future__ import annotations

import os
from typing import Any

SCHEMA_CONTRACT_VERSION = "wave1br-runtime-ddl-ban-v1"
SCHEMA_APPLY_ENV = "WATHEFNI_SCHEMA_APPLY"
# Dedicated lock for Wave 1-BR deploy migrator (do not reuse payroll/shifts ids).
DEPLOY_ADVISORY_LOCK_ID = 770_911_001

# Process counters for staging proof (no DDL expected when apply is off).
_APPLY_CALLS = 0
_REQUIRE_CALLS = 0
_BLOCKED_APPLY_ATTEMPTS = 0


class SchemaNotMigratedError(RuntimeError):
    """Raised when runtime code finds required schema missing."""

    def __init__(self, module: str, missing: list[str]):
        self.module = module
        self.missing = list(missing)
        detail = ",".join(self.missing[:12])
        super().__init__(f"schema_not_migrated:{module}:missing={detail}")


def schema_apply_allowed(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(SCHEMA_APPLY_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def reset_counters() -> None:
    global _APPLY_CALLS, _REQUIRE_CALLS, _BLOCKED_APPLY_ATTEMPTS
    _APPLY_CALLS = 0
    _REQUIRE_CALLS = 0
    _BLOCKED_APPLY_ATTEMPTS = 0


def counters() -> dict[str, int]:
    return {
        "apply_calls": int(_APPLY_CALLS),
        "require_calls": int(_REQUIRE_CALLS),
        "blocked_apply_attempts": int(_BLOCKED_APPLY_ATTEMPTS),
    }


def require_relations(cur: Any, tables: list[str], *, module: str) -> None:
    """Fail closed if any required relation is missing. Never mutates schema."""

    global _REQUIRE_CALLS
    _REQUIRE_CALLS += 1
    needed = [str(t).strip() for t in tables if str(t).strip()]
    if not needed:
        return
    cur.execute(
        """
        SELECT c.relname::text AS name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
          AND c.relname = ANY(%s)
        """,
        (needed,),
    )
    found = {str(r["name"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
    missing = [t for t in needed if t not in found]
    if missing:
        raise SchemaNotMigratedError(module, missing)


def apply_sql(
    cur: Any,
    sql: str,
    *,
    module: str,
    lock_id: int | None = None,
    environ: dict[str, str] | None = None,
) -> None:
    """Execute DDL only when WATHEFNI_SCHEMA_APPLY is enabled."""

    global _APPLY_CALLS, _BLOCKED_APPLY_ATTEMPTS
    if not schema_apply_allowed(environ):
        _BLOCKED_APPLY_ATTEMPTS += 1
        raise RuntimeError(f"schema_apply_forbidden:{module}:set_{SCHEMA_APPLY_ENV}=1")
    text = str(sql or "").strip()
    if not text:
        return
    _APPLY_CALLS += 1
    held = False
    if lock_id is not None:
        cur.execute("SELECT pg_advisory_lock(%s)", (int(lock_id),))
        held = True
    try:
        cur.execute("SET LOCAL lock_timeout = '30s'")
        cur.execute(text)
        _record_ledger(cur, module=module, mode="apply")
    finally:
        if held:
            cur.execute("SELECT pg_advisory_unlock(%s)", (int(lock_id),))


def ensure_sql(
    cur: Any,
    sql: str,
    *,
    required_tables: list[str],
    module: str,
    lock_id: int | None = None,
    environ: dict[str, str] | None = None,
) -> None:
    """Apply DDL when allowed; otherwise validate required tables fail-closed."""

    if schema_apply_allowed(environ):
        apply_sql(cur, sql, module=module, lock_id=lock_id, environ=environ)
        return
    require_relations(cur, required_tables, module=module)


def with_deploy_advisory_lock(cur: Any, fn: Any) -> Any:
    """Serialize a deploy migration command under the Wave 1-BR advisory lock."""

    cur.execute("SELECT pg_advisory_lock(%s)", (DEPLOY_ADVISORY_LOCK_ID,))
    try:
        cur.execute("SET LOCAL lock_timeout = '60s'")
        return fn(cur)
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (DEPLOY_ADVISORY_LOCK_ID,))


def ensure_ledger_table(cur: Any) -> None:
    """Ledger itself is created only under apply mode (deploy migrator)."""

    if not schema_apply_allowed():
        # Validate ledger optionally; do not create.
        require_relations(cur, ["wathefni_schema_migrations"], module="schema_contract.ledger")
        return
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wathefni_schema_migrations (
          module text NOT NULL,
          contract_version text NOT NULL,
          mode text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (module, contract_version, mode, applied_at)
        )
        """
    )


def record_apply(cur: Any, *, module: str) -> None:
    _record_ledger(cur, module=module, mode="apply")


def _record_ledger(cur: Any, *, module: str, mode: str) -> None:
    try:
        ensure_ledger_table(cur)
        cur.execute(
            """
            INSERT INTO wathefni_schema_migrations (module, contract_version, mode)
            VALUES (%s, %s, %s)
            """,
            (module, SCHEMA_CONTRACT_VERSION, mode),
        )
    except Exception:
        # Ledger is best-effort evidence; never mask apply failures from missing SQL.
        pass


# Core relations that must exist before API/workers resume after deploy migration.
CORE_RUNTIME_TABLES = [
    "hr_turns",
    "candidates",
    "applications",
    "candidate_documents",
    "file_registry",
    "intake_processing_jobs",
    "inbound_messages",
    "intake_submissions",
    "intake_documents",
    "migration_batches",
    "migration_rows",
    "migration_chunk_jobs",
    "migration_events",
    "intake_source_events",
    "intake_subjects",
    "intake_items",
    "cv_versions",
]


def require_core_runtime_schema(cur: Any) -> None:
    require_relations(cur, CORE_RUNTIME_TABLES, module="core_runtime")
