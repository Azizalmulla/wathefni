"""Migration & Sync P5.2 — Connected Systems connectors + sync runs.

Connectors fetch external rows and feed the existing foundation
preview/commit pipeline. No parallel apply engine.

P5.1: production scheduler + real SFTP.
P5.2: connector secrets fail-closed (no plainhex / plaintext fallback).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import schema_contract

CONTRACT = "employee_migration_sync_p6_leavers"
CONTRACT_VERSION = "6.0.0"

CONNECTOR_KINDS = frozenset(
    {"deterministic_canary", "scheduled_csv", "api_stub", "sftp", "sftp_stub"}
)
CONNECTION_STATUSES = frozenset({"active", "paused", "disconnected", "error"})
SYNC_TRIGGERS = frozenset({"manual", "scheduled", "retry"})
SYNC_STATUSES = frozenset(
    {"running", "previewed", "committed", "failed", "cancelled", "partial"}
)
TRANSIENT_ERROR_CODES = frozenset({"timeout", "unavailable", "fetch_failed"})
DEFAULT_TIMEZONE = "Asia/Kuwait"
DEFAULT_INTERVAL_MINUTES = 60
LOCK_TTL_MINUTES = 15
MAX_BACKOFF_MINUTES = 60

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_migration_connections (
  connection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  connector_kind text NOT NULL,
  source_system text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  cursor_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  schedule_cron text,
  schedule_enabled boolean NOT NULL DEFAULT false,
  last_sync_at timestamptz,
  last_success_at timestamptz,
  next_sync_at timestamptz,
  last_error_summary text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (connector_kind = ANY (ARRAY[
    'deterministic_canary','scheduled_csv','api_stub','sftp','sftp_stub'
  ])),
  CHECK (status = ANY (ARRAY['active','paused','disconnected','error']))
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_conn_company
  ON employee_migration_connections(company_code, status);
CREATE INDEX IF NOT EXISTS idx_emp_mig_conn_due
  ON employee_migration_connections(schedule_enabled, status, next_sync_at)
  WHERE schedule_enabled IS TRUE;

CREATE TABLE IF NOT EXISTS employee_migration_connection_secrets (
  connection_id uuid PRIMARY KEY
    REFERENCES employee_migration_connections(connection_id) ON DELETE CASCADE,
  ciphertext text NOT NULL,
  key_version text,
  alg text NOT NULL DEFAULT 'fernet',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_migration_sync_runs (
  sync_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connection_id uuid NOT NULL
    REFERENCES employee_migration_connections(connection_id) ON DELETE CASCADE,
  trigger text NOT NULL,
  status text NOT NULL DEFAULT 'running',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  cursor_before jsonb NOT NULL DEFAULT '{}'::jsonb,
  cursor_after jsonb NOT NULL DEFAULT '{}'::jsonb,
  records_fetched integer NOT NULL DEFAULT 0,
  created_count integer NOT NULL DEFAULT 0,
  updated_count integer NOT NULL DEFAULT 0,
  unchanged_count integer NOT NULL DEFAULT 0,
  review_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  batch_id uuid,
  error_code text,
  error_summary text,
  lifecycle_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (trigger = ANY (ARRAY['manual','scheduled','retry'])),
  CHECK (status = ANY (ARRAY[
    'running','previewed','committed','failed','cancelled','partial'
  ]))
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_sync_runs_conn
  ON employee_migration_sync_runs(connection_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_emp_mig_sync_runs_company
  ON employee_migration_sync_runs(company_code, started_at DESC);

CREATE TABLE IF NOT EXISTS employee_migration_connector_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connection_id uuid,
  actor text,
  action text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_conn_audit_company
  ON employee_migration_connector_audit(company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_migration_processed_files (
  processed_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connection_id uuid NOT NULL
    REFERENCES employee_migration_connections(connection_id) ON DELETE CASCADE,
  content_sha256 text NOT NULL,
  remote_path text NOT NULL,
  remote_size bigint,
  remote_mtime text,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  sync_run_id uuid,
  UNIQUE (connection_id, content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_processed_files_conn
  ON employee_migration_processed_files(connection_id, processed_at DESC);
"""

SCHEMA_MIGRATE_SQL = """
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'Asia/Kuwait';
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS schedule_interval_minutes integer;
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS sync_lock_until timestamptz;
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS sync_lock_owner text;
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
ALTER TABLE employee_migration_connections
  ADD COLUMN IF NOT EXISTS retry_after timestamptz;

ALTER TABLE employee_migration_connections
  DROP CONSTRAINT IF EXISTS employee_migration_connections_connector_kind_check;
ALTER TABLE employee_migration_connections
  ADD CONSTRAINT employee_migration_connections_connector_kind_check
  CHECK (connector_kind = ANY (ARRAY[
    'deterministic_canary','scheduled_csv','api_stub','sftp','sftp_stub'
  ]));

CREATE TABLE IF NOT EXISTS employee_migration_processed_files (
  processed_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connection_id uuid NOT NULL
    REFERENCES employee_migration_connections(connection_id) ON DELETE CASCADE,
  content_sha256 text NOT NULL,
  remote_path text NOT NULL,
  remote_size bigint,
  remote_mtime text,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  sync_run_id uuid,
  UNIQUE (connection_id, content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_processed_files_conn
  ON employee_migration_processed_files(connection_id, processed_at DESC);
CREATE INDEX IF NOT EXISTS idx_emp_mig_conn_due
  ON employee_migration_connections(schedule_enabled, status, next_sync_at)
  WHERE schedule_enabled IS TRUE;
"""

_SCHEMA_READY = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "feeds_foundation_pipeline": True,
        "no_parallel_apply_engine": True,
        "no_invites": True,
        "no_auto_onboarding": True,
        "no_auto_deactivation": True,
        "lifecycle_signals_captured_only": False,
        "lifecycle_processed_with_policy": True,
        "secrets_never_in_api": True,
        "secrets_fail_closed": True,
        "plainhex_fallback_removed": True,
        "secret_hardening_p5_2": True,
        "lifecycle_sync_p6": True,
        "no_auto_deactivation_by_default": True,
        "connector_kinds": sorted(CONNECTOR_KINDS),
        "canary_connector": "deterministic_canary",
        "scheduler_production": True,
        "sftp_real_connector": True,
        "api_stub_only": True,
        "host_key_verification_required": True,
        "source_files_immutable_by_default": True,
    }


class ConnectorSecretError(Exception):
    """Fail-closed connector credential seal/unseal error (never includes secret material)."""

    def __init__(self, code: str, message: str):
        self.code = str(code or "connector_secret_error")
        self.message = str(message or "Connector credential encryption is unavailable.")
        super().__init__(self.message)


def _is_insecure_ciphertext(ciphertext: str | None, alg: str | None = None) -> bool:
    text = str(ciphertext or "")
    alg_s = str(alg or "").strip().lower()
    if alg_s in {"plainhex", "plaintext", "none", "clear"}:
        return True
    if text.startswith("plainhex:") or text.startswith("plaintext:"):
        return True
    return False


def _seal_secret(legacy: Any, plaintext: str) -> dict[str, str]:
    """Encrypt connector credentials at rest. Fail closed — never plainhex/plaintext."""
    if not hasattr(legacy, "encrypt_sensitive_text") or not hasattr(legacy, "sensitive_encryption_available"):
        raise ConnectorSecretError(
            "connector_encryption_unavailable",
            "Secure credential encryption is not configured. Set WATHEFNI_MAILBOX_SECRET_KEY and retry.",
        )
    try:
        available = bool(legacy.sensitive_encryption_available())
    except Exception as exc:
        raise ConnectorSecretError(
            "connector_encryption_unavailable",
            "Secure credential encryption is not configured. Set WATHEFNI_MAILBOX_SECRET_KEY and retry.",
        ) from exc
    if not available:
        raise ConnectorSecretError(
            "connector_encryption_unavailable",
            "Secure credential encryption is not configured. Set WATHEFNI_MAILBOX_SECRET_KEY and retry.",
        )
    try:
        sealed = legacy.encrypt_sensitive_text(plaintext)
    except Exception as exc:
        raise ConnectorSecretError(
            "connector_encryption_failed",
            "Could not encrypt connector credentials. Check the encryption key configuration.",
        ) from exc
    if not isinstance(sealed, dict):
        raise ConnectorSecretError(
            "connector_encryption_failed",
            "Could not encrypt connector credentials. Check the encryption key configuration.",
        )
    ciphertext = str(sealed.get("ciphertext") or "")
    alg = str(sealed.get("alg") or "fernet")
    if not ciphertext or _is_insecure_ciphertext(ciphertext, alg):
        raise ConnectorSecretError(
            "connector_encryption_rejected",
            "Encryption returned an insecure ciphertext and was rejected.",
        )
    return {
        "ciphertext": ciphertext,
        "key_version": str(sealed.get("key_version") or ""),
        "alg": alg if alg else "fernet",
    }


def _open_secret(legacy: Any, ciphertext: str, *, alg: str | None = None) -> str:
    """Decrypt connector credentials. Rejects insecure fallback storage."""
    text = str(ciphertext or "")
    if not text:
        raise ConnectorSecretError(
            "connector_secret_missing",
            "Connector credentials are missing. Re-enter credentials.",
        )
    if _is_insecure_ciphertext(text, alg):
        raise ConnectorSecretError(
            "insecure_secret_storage_rejected",
            "Stored credentials use insecure storage and must be re-entered.",
        )
    if not hasattr(legacy, "decrypt_sensitive_text") or not hasattr(legacy, "sensitive_encryption_available"):
        raise ConnectorSecretError(
            "connector_encryption_unavailable",
            "Secure credential encryption is not configured. Set WATHEFNI_MAILBOX_SECRET_KEY and retry.",
        )
    try:
        if not legacy.sensitive_encryption_available():
            raise ConnectorSecretError(
                "connector_encryption_unavailable",
                "Secure credential encryption is not configured. Set WATHEFNI_MAILBOX_SECRET_KEY and retry.",
            )
        return legacy.decrypt_sensitive_text(text)
    except ConnectorSecretError:
        raise
    except Exception as exc:
        raise ConnectorSecretError(
            "connector_secret_decrypt_failed",
            "Stored connector credentials could not be decrypted. Re-enter credentials.",
        ) from exc


def _read_plainhex_for_migration_only(ciphertext: str) -> str:
    """One-time migration helper. Never used by sync/apply paths."""
    text = str(ciphertext or "")
    if not text.startswith("plainhex:"):
        raise ConnectorSecretError(
            "not_plainhex",
            "Secret is not in the legacy plainhex format.",
        )
    try:
        return bytes.fromhex(text[len("plainhex:") :]).decode("utf-8")
    except Exception as exc:
        raise ConnectorSecretError(
            "plainhex_corrupt",
            "Legacy insecure secret could not be read for reseal.",
        ) from exc


def _http_secret_error(legacy: Any, exc: ConnectorSecretError) -> Any:
    return legacy.HTTPException(
        status_code=503,
        detail={
            "error": exc.code,
            "message": exc.message,
        },
    )


def ensure_connectors_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=[
            "employee_migration_connections",
            "employee_migration_connection_secrets",
            "employee_migration_sync_runs",
            "employee_migration_connector_audit",
            "employee_migration_processed_files",
        ],
        module="employee_migration_connectors",
        lock_id=None,
    )
    # Existing P5 installs need column/constraint upgrades.
    schema_contract.ensure_sql(
        cur,
        SCHEMA_MIGRATE_SQL,
        required_tables=[
            "employee_migration_connections",
            "employee_migration_processed_files",
        ],
        module="employee_migration_connectors_p51",
        lock_id=None,
    )
    _SCHEMA_READY = True


def _company_for_sync(legacy: Any, context: dict[str, Any]) -> str:
    """HR admin for interactive paths; scheduler worker uses sealed service context."""
    if context.get("_scheduler_worker") is True:
        company = str(context.get("company_code") or "").strip().upper()
        if not company:
            raise ValueError("scheduler_company_required")
        return company
    return legacy.require_employee_roster_admin(context)


def scheduler_service_context(company_code: str) -> dict[str, Any]:
    return {
        "company_code": str(company_code).strip().upper(),
        "user_id": "migration-scheduler",
        "email": "migration-scheduler@wathefni.internal",
        "permissions": ["employees.manage"],
        "_scheduler_worker": True,
    }


def _resolve_timezone(name: str | None) -> ZoneInfo:
    raw = str(name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(raw)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def parse_schedule_interval_minutes(
    *,
    schedule_interval_minutes: int | None,
    schedule_cron: str | None,
    config: dict[str, Any] | None = None,
) -> int:
    cfg = config or {}
    if schedule_interval_minutes is not None:
        try:
            mins = int(schedule_interval_minutes)
            if mins > 0:
                return max(1, min(mins, 60 * 24 * 7))
        except (TypeError, ValueError):
            pass
    cfg_mins = cfg.get("schedule_interval_minutes")
    if cfg_mins is not None:
        try:
            mins = int(cfg_mins)
            if mins > 0:
                return max(1, min(mins, 60 * 24 * 7))
        except (TypeError, ValueError):
            pass
    cron = str(schedule_cron or cfg.get("schedule_cron") or "").strip()
    if cron.startswith("*/"):
        # */N * * * *
        try:
            n = int(cron.split()[0][2:])
            if n > 0:
                return max(1, min(n, 60 * 24 * 7))
        except (TypeError, ValueError, IndexError):
            pass
    if cron in {"0 * * * *", "0 * * *"}:
        return 60
    if cron in {"0 0 * * *", "0 0 * *"}:
        return 60 * 24
    return DEFAULT_INTERVAL_MINUTES


def compute_next_sync_at(
    *,
    from_time: datetime | None = None,
    timezone_name: str | None = None,
    schedule_interval_minutes: int | None = None,
    schedule_cron: str | None = None,
    config: dict[str, Any] | None = None,
) -> datetime:
    """Deterministic next fire time: now + cadence (missed runs catch up once)."""
    base = from_time or _now()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    mins = parse_schedule_interval_minutes(
        schedule_interval_minutes=schedule_interval_minutes,
        schedule_cron=schedule_cron,
        config=config,
    )
    # Advance in UTC; timezone is recorded for display / daily boundary clarity.
    _ = _resolve_timezone(timezone_name)
    return base + timedelta(minutes=mins)


def compute_retry_after(*, retry_count: int, from_time: datetime | None = None) -> datetime:
    base = from_time or _now()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    # 1, 2, 4, 8, ... capped
    exp = min(MAX_BACKOFF_MINUTES, max(1, 2 ** max(0, int(retry_count))))
    return base + timedelta(minutes=exp)


def _audit(
    cur: Any,
    *,
    company: str,
    connection_id: str | None,
    actor: str | None,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO employee_migration_connector_audit
          (company_code, connection_id, actor, action, detail)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        """,
        (company, connection_id, actor, action, json.dumps(detail or {})),
    )


def _public_connection(row: dict[str, Any], *, has_secret: bool = False) -> dict[str, Any]:
    cfg = row.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    # Strip any accidental secret keys from config copies
    safe_cfg = {
        k: v
        for k, v in dict(cfg).items()
        if k.lower() not in {"password", "token", "api_key", "secret", "private_key"}
    }
    return {
        "connection_id": str(row.get("connection_id")),
        "company_code": row.get("company_code"),
        "name": row.get("name"),
        "connector_kind": row.get("connector_kind"),
        "source_system": row.get("source_system"),
        "status": row.get("status"),
        "config": safe_cfg,
        "schedule_cron": row.get("schedule_cron"),
        "schedule_enabled": bool(row.get("schedule_enabled")),
        "schedule_interval_minutes": row.get("schedule_interval_minutes"),
        "timezone": row.get("timezone") or DEFAULT_TIMEZONE,
        "has_credentials": bool(has_secret),
        "cursor_present": bool(row.get("cursor_json")),
        "last_sync_at": _jsonable(row.get("last_sync_at")),
        "last_success_at": _jsonable(row.get("last_success_at")),
        "next_sync_at": _jsonable(row.get("next_sync_at")),
        "last_error_summary": row.get("last_error_summary"),
        "credentials_reentry_required": bool(
            str(row.get("last_error_summary") or "").startswith("credentials_require_reentry")
            or str(row.get("last_error_summary") or "").startswith("insecure_secret_storage")
        ),
        "created_at": _jsonable(row.get("created_at")),
        "updated_at": _jsonable(row.get("updated_at")),
    }


def _public_sync_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sync_run_id": str(row.get("sync_run_id")),
        "connection_id": str(row.get("connection_id")),
        "company_code": row.get("company_code"),
        "trigger": row.get("trigger"),
        "status": row.get("status"),
        "started_at": _jsonable(row.get("started_at")),
        "finished_at": _jsonable(row.get("finished_at")),
        "cursor_before": row.get("cursor_before") or {},
        "cursor_after": row.get("cursor_after") or {},
        "records_fetched": int(row.get("records_fetched") or 0),
        "created_count": int(row.get("created_count") or 0),
        "updated_count": int(row.get("updated_count") or 0),
        "unchanged_count": int(row.get("unchanged_count") or 0),
        "review_count": int(row.get("review_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "batch_id": str(row["batch_id"]) if row.get("batch_id") else None,
        "error_code": row.get("error_code"),
        "error_summary": row.get("error_summary"),
        "lifecycle_signals_count": len(row.get("lifecycle_signals") or []),
    }


# --- Deterministic canary fixture -------------------------------------------------

def _canary_fixture(config: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic roster for WATHEFNI qualification. Phones stay in test ranges."""
    tag = str(config.get("fixture_tag") or "p5canary")[:12]
    base = int(hashlib.sha256(tag.encode()).hexdigest()[:6], 16) % 80000
    # Three employees; bump_version mutates #2 for incremental tests.
    version = int(config.get("fixture_version") or 1)
    rows = [
        {
            "name": f"P5 Canary Alpha {tag}",
            "phone": f"96557{(base + 1) % 100000:05d}1",
            "external_employee_id": f"CANARY-{tag}-A",
            "email": f"p5a-{tag}@example.invalid",
            "position_title": "Analyst",
            "department": "Ops",
            "updated_at": "2026-01-01T00:00:00Z",
            "source_version": "1",
        },
        {
            "name": f"P5 Canary Beta {tag}",
            "phone": f"96557{(base + 2) % 100000:05d}2",
            "external_employee_id": f"CANARY-{tag}-B",
            "email": f"p5b-{tag}@example.invalid",
            "position_title": "Coordinator" if version < 2 else "Senior Coordinator",
            "department": "Ops",
            "updated_at": "2026-01-01T00:00:00Z" if version < 2 else "2026-02-01T00:00:00Z",
            "source_version": str(version),
        },
        {
            "name": f"P5 Canary Gamma {tag}",
            "phone": f"96557{(base + 3) % 100000:05d}3",
            "external_employee_id": f"CANARY-{tag}-C",
            "email": f"p5c-{tag}@example.invalid",
            "position_title": "Specialist",
            "department": "Support",
            "updated_at": "2026-01-15T00:00:00Z",
            "source_version": "1",
            "custom_cost_center": "CC-900",
        },
    ]
    if config.get("include_conflict_name"):
        # Same phone as Alpha but materially different name → Needs review on update path
        rows.append(
            {
                "name": f"P5 Canary Alpha RENAMED {tag}",
                "phone": rows[0]["phone"],
                "external_employee_id": f"CANARY-{tag}-A",
                "email": rows[0]["email"],
                "position_title": "Analyst",
                "department": "Ops",
                "updated_at": "2026-03-01T00:00:00Z",
                "source_version": "99",
            }
        )
    return rows


def _rows_to_csv(rows: list[dict[str, str]]) -> tuple[bytes, list[str]]:
    if not rows:
        headers = ["name", "phone"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers)
        w.writeheader()
        return buf.getvalue().encode("utf-8"), headers
    # Stable union of keys; name+phone first
    keys: list[str] = []
    for preferred in ("name", "phone", "external_employee_id", "email", "position_title", "department"):
        if any(preferred in r for r in rows) and preferred not in keys:
            keys.append(preferred)
    for r in rows:
        for k in r:
            if k not in keys and k not in {"updated_at", "source_version"}:
                keys.append(k)
    # Keep updated_at for connector cursor logic but also include in CSV as source-only
    if any("updated_at" in r for r in rows):
        keys.append("updated_at")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in keys})
    return buf.getvalue().encode("utf-8"), keys


def fetch_connector_rows(
    *,
    connector_kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None,
    cursor: dict[str, Any] | None,
    company: str = "",
    connection_id: str | None = None,
    legacy: Any | None = None,
) -> dict[str, Any]:
    """Common connector contract → rows + cursor + lifecycle signals."""
    secrets = secrets or {}
    cursor = cursor or {}
    kind = str(connector_kind or "").strip()
    if kind == "sftp_stub":
        kind = "sftp"

    if config.get("force_auth_failure") or secrets.get("force_auth_failure"):
        raise PermissionError("connector_auth_failed")
    if config.get("force_unavailable"):
        raise ConnectionError("connector_unavailable")
    if config.get("force_timeout"):
        raise TimeoutError("connector_timeout")

    if kind == "deterministic_canary":
        all_rows = _canary_fixture(config)
        mode = str(config.get("sync_mode") or cursor.get("mode") or "incremental")
        watermark = str(cursor.get("updated_at") or "").strip()
        if mode == "full" or not watermark:
            selected = list(all_rows)
        else:
            selected = [r for r in all_rows if str(r.get("updated_at") or "") > watermark]
        # Simulate pagination metadata
        page_size = int(config.get("page_size") or 100)
        pages = max(1, (len(selected) + page_size - 1) // page_size) if selected else 1
        max_updated = max((str(r.get("updated_at") or "") for r in selected), default=watermark)
        lifecycle = []
        if config.get("emit_leaver_signal"):
            lifecycle.append(
                {
                    "signal": "source_deleted_or_inactive",
                    "source_status": str(config.get("leaver_source_status") or "inactive"),
                    "external_employee_id": str(
                        config.get("leaver_external_id")
                        or f"CANARY-{config.get('fixture_tag') or 'p5canary'}-Z"
                    ),
                    "effective_date": config.get("leaver_effective_date"),
                    "reason_code": config.get("leaver_reason_code"),
                    "note": "P6 lifecycle signal from canary connector",
                }
            )
        if config.get("emit_reactivation_signal"):
            lifecycle.append(
                {
                    "signal": "reactivated",
                    "source_status": str(config.get("reactivation_source_status") or "rehired"),
                    "external_employee_id": str(
                        config.get("reactivation_external_id")
                        or f"CANARY-{config.get('fixture_tag') or 'p5canary'}-A"
                    ),
                    "effective_date": config.get("reactivation_effective_date"),
                    "note": "P6 reactivation signal from canary connector",
                }
            )
        # Rows carrying employment_status also emit lifecycle signals (missing = not supplied)
        for r in selected:
            st = str(r.get("employment_status") or "").strip()
            if not st:
                continue
            lifecycle.append(
                {
                    "source_status": st,
                    "external_employee_id": r.get("external_employee_id"),
                    "effective_date": r.get("termination_date") or r.get("effective_date"),
                    "reason_code": r.get("termination_reason") or r.get("reason_code"),
                }
            )
        return {
            "rows": selected,
            "cursor_after": {
                "updated_at": max_updated or watermark or "2026-01-01T00:00:00Z",
                "mode": "incremental",
                "pages": pages,
            },
            "lifecycle_signals": lifecycle,
            "meta": {"kind": kind, "fetched": len(selected), "full_snapshot_size": len(all_rows)},
        }

    if kind == "scheduled_csv":
        # Inline fixture CSV text in config (no filesystem dependency on canary)
        raw_csv = str(config.get("inline_csv") or "").strip()
        if not raw_csv:
            # Fall back to canary fixture materialized as CSV rows
            return fetch_connector_rows(
                connector_kind="deterministic_canary",
                config={**config, "sync_mode": "full"},
                secrets=secrets,
                cursor={},
                company=company,
            )
        reader = csv.DictReader(io.StringIO(raw_csv))
        rows = [{k: (v or "") for k, v in dict(r).items()} for r in reader]
        return {
            "rows": rows,
            "cursor_after": {"content_sha": hashlib.sha256(raw_csv.encode()).hexdigest(), "mode": "full_snapshot"},
            "lifecycle_signals": [],
            "meta": {"kind": kind, "fetched": len(rows), "diff_mode": "full_snapshot"},
        }

    if kind == "sftp":
        import employee_migration_sftp as sftp_mod

        def _already(sha: str, meta: dict[str, Any]) -> bool:
            if not legacy or not connection_id:
                return False
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    ensure_connectors_schema(cur)
                    cur.execute(
                        """
                        SELECT 1 FROM employee_migration_processed_files
                        WHERE connection_id=%s AND content_sha256=%s
                        """,
                        (connection_id, sha),
                    )
                    hit = bool(cur.fetchone())
                    conn.commit()
            return hit

        return sftp_mod.fetch_sftp_rows(
            config=config,
            secrets=secrets,
            cursor=cursor,
            company=company,
            record_processed=_already if legacy and connection_id else None,
        )

    if kind == "api_stub":
        raise RuntimeError(f"connector_kind_not_configured:{kind}")

    raise ValueError(f"unknown_connector_kind:{kind}")


def create_connection(
    legacy: Any,
    context: dict[str, Any],
    *,
    name: str,
    connector_kind: str,
    source_system: str | None = None,
    config: dict[str, Any] | None = None,
    credentials: dict[str, Any] | None = None,
    schedule_cron: str | None = None,
    schedule_enabled: bool = False,
    schedule_interval_minutes: int | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    import employee_migration_foundation as emf

    emf.require_foundation(legacy, company)
    kind = str(connector_kind or "").strip()
    if kind == "sftp_stub":
        kind = "sftp"
    if kind not in CONNECTOR_KINDS:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_connector_kind"})
    import production_data_safety as _pds

    if kind in _pds.SYNTHETIC_CONNECTOR_KINDS and not _pds.synthetic_connectors_allowed(company):
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "synthetic_connector_forbidden",
                "message": "Synthetic fixture sources are not available in this workspace.",
            },
        )
    name_s = str(name or "").strip()
    if not name_s:
        raise legacy.HTTPException(status_code=422, detail={"error": "name_required"})
    src = str(source_system or "").strip() or f"connector:{kind}"
    cfg = dict(config or {})
    actor = str(context.get("user_id") or context.get("email") or "") or None
    tz = str(timezone_name or cfg.get("timezone") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    interval = parse_schedule_interval_minutes(
        schedule_interval_minutes=schedule_interval_minutes,
        schedule_cron=schedule_cron,
        config=cfg,
    )
    next_sync = None
    if schedule_enabled:
        next_sync = compute_next_sync_at(
            timezone_name=tz,
            schedule_interval_minutes=interval,
            schedule_cron=schedule_cron,
            config=cfg,
        )

    # Seal before any persistence so we never store a connection with failed encryption.
    sealed: dict[str, str] | None = None
    if credentials:
        try:
            sealed = _seal_secret(legacy, json.dumps(credentials))
        except ConnectorSecretError as exc:
            raise _http_secret_error(legacy, exc) from exc

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_migration_connections (
                  company_code, name, connector_kind, source_system, status, config,
                  schedule_cron, schedule_enabled, schedule_interval_minutes, timezone,
                  next_sync_at, created_by
                ) VALUES (%s,%s,%s,%s,'active',%s::jsonb,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    company,
                    name_s,
                    kind,
                    src,
                    json.dumps(cfg),
                    schedule_cron,
                    bool(schedule_enabled),
                    interval,
                    tz,
                    next_sync,
                    actor,
                ),
            )
            row = dict(cur.fetchone())
            cid = str(row["connection_id"])
            has_secret = False
            if sealed is not None:
                cur.execute(
                    """
                    INSERT INTO employee_migration_connection_secrets
                      (connection_id, ciphertext, key_version, alg)
                    VALUES (%s,%s,%s,%s)
                    """,
                    (cid, sealed["ciphertext"], sealed.get("key_version"), sealed.get("alg") or "fernet"),
                )
                has_secret = True
            _audit(
                cur,
                company=company,
                connection_id=cid,
                actor=actor,
                action="connect",
                detail={"connector_kind": kind, "source_system": src, "credentials_sealed": has_secret},
            )
            conn.commit()
    return {"ok": True, "connection": _public_connection(row, has_secret=has_secret), "honesty": honesty_payload()}


def list_connections(legacy: Any, context: dict[str, Any]) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                SELECT c.*, (s.connection_id IS NOT NULL) AS has_secret
                FROM employee_migration_connections c
                LEFT JOIN employee_migration_connection_secrets s ON s.connection_id=c.connection_id
                WHERE c.company_code=%s AND c.status <> 'disconnected'
                ORDER BY c.updated_at DESC
                """,
                (company,),
            )
            rows = cur.fetchall() or []
            conn.commit()
    return {
        "ok": True,
        "connections": [
            _public_connection(dict(r), has_secret=bool(r.get("has_secret"))) for r in rows
        ],
        "honesty": honesty_payload(),
    }


def update_connection(
    legacy: Any,
    context: dict[str, Any],
    *,
    connection_id: str,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    credentials: dict[str, Any] | None = None,
    schedule_cron: str | None = None,
    schedule_enabled: bool | None = None,
    schedule_interval_minutes: int | None = None,
    timezone_name: str | None = None,
    clear_cursor: bool = False,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    actor = str(context.get("user_id") or context.get("email") or "") or None
    sealed: dict[str, str] | None = None
    if credentials is not None:
        try:
            sealed = _seal_secret(legacy, json.dumps(credentials))
        except ConnectorSecretError as exc:
            raise _http_secret_error(legacy, exc) from exc
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_migration_connections
                WHERE company_code=%s AND connection_id=%s
                """,
                (company, connection_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "connection_not_found"})
            row = dict(row)
            new_cfg = dict(row.get("config") or {})
            if isinstance(new_cfg, str):
                new_cfg = json.loads(new_cfg)
            if config is not None:
                new_cfg.update(config)
            sets = ["config=%s::jsonb", "updated_at=now()"]
            params: list[Any] = [json.dumps(new_cfg)]
            if name is not None:
                sets.append("name=%s")
                params.append(str(name).strip())
            if schedule_cron is not None:
                sets.append("schedule_cron=%s")
                params.append(schedule_cron)
            if schedule_interval_minutes is not None:
                sets.append("schedule_interval_minutes=%s")
                params.append(int(schedule_interval_minutes))
            if timezone_name is not None:
                sets.append("timezone=%s")
                params.append(str(timezone_name).strip() or DEFAULT_TIMEZONE)
            if schedule_enabled is not None:
                sets.append("schedule_enabled=%s")
                params.append(bool(schedule_enabled))
                if schedule_enabled:
                    interval = parse_schedule_interval_minutes(
                        schedule_interval_minutes=schedule_interval_minutes
                        if schedule_interval_minutes is not None
                        else row.get("schedule_interval_minutes"),
                        schedule_cron=schedule_cron if schedule_cron is not None else row.get("schedule_cron"),
                        config=new_cfg,
                    )
                    sets.append("schedule_interval_minutes=%s")
                    params.append(interval)
                    next_sync = compute_next_sync_at(
                        timezone_name=timezone_name or row.get("timezone"),
                        schedule_interval_minutes=interval,
                        schedule_cron=schedule_cron if schedule_cron is not None else row.get("schedule_cron"),
                        config=new_cfg,
                    )
                    sets.append("next_sync_at=%s")
                    params.append(next_sync)
                    sets.append("retry_count=0")
                    sets.append("retry_after=NULL")
            if clear_cursor:
                sets.append("cursor_json='{}'::jsonb")
            if sealed is not None:
                # Clear prior insecure-storage / re-entry flags when credentials are resealed.
                sets.append("last_error_summary=NULL")
                sets.append("status=CASE WHEN status='error' THEN 'active' ELSE status END")
            params.extend([connection_id, company])
            cur.execute(
                f"UPDATE employee_migration_connections SET {', '.join(sets)} WHERE connection_id=%s AND company_code=%s RETURNING *",
                params,
            )
            updated = dict(cur.fetchone())
            has_secret = False
            if sealed is not None:
                cur.execute(
                    """
                    INSERT INTO employee_migration_connection_secrets
                      (connection_id, ciphertext, key_version, alg, updated_at)
                    VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (connection_id) DO UPDATE SET
                      ciphertext=EXCLUDED.ciphertext,
                      key_version=EXCLUDED.key_version,
                      alg=EXCLUDED.alg,
                      updated_at=now()
                    """,
                    (connection_id, sealed["ciphertext"], sealed.get("key_version"), sealed.get("alg") or "fernet"),
                )
                has_secret = True
                _audit(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    actor=actor,
                    action="credentials_updated",
                    detail={"alg": sealed.get("alg"), "key_version": sealed.get("key_version")},
                )
            else:
                cur.execute(
                    "SELECT 1 FROM employee_migration_connection_secrets WHERE connection_id=%s",
                    (connection_id,),
                )
                has_secret = bool(cur.fetchone())
            _audit(
                cur,
                company=company,
                connection_id=connection_id,
                actor=actor,
                action="configure",
                detail={"clear_cursor": clear_cursor},
            )
            conn.commit()
    return {"ok": True, "connection": _public_connection(updated, has_secret=has_secret)}


def set_connection_status(
    legacy: Any,
    context: dict[str, Any],
    *,
    connection_id: str,
    status: str,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    status_s = str(status or "").strip()
    if status_s not in CONNECTION_STATUSES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_status"})
    actor = str(context.get("user_id") or context.get("email") or "") or None
    action = {
        "paused": "pause",
        "active": "resume",
        "disconnected": "disconnect",
        "error": "mark_error",
    }.get(status_s, "status_change")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                UPDATE employee_migration_connections
                SET status=%s, updated_at=now(),
                    last_error_summary=CASE WHEN %s='active' THEN NULL ELSE last_error_summary END
                WHERE company_code=%s AND connection_id=%s
                RETURNING *
                """,
                (status_s, status_s, company, connection_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "connection_not_found"})
            _audit(cur, company=company, connection_id=connection_id, actor=actor, action=action, detail={"status": status_s})
            if status_s == "disconnected":
                cur.execute(
                    "DELETE FROM employee_migration_connection_secrets WHERE connection_id=%s",
                    (connection_id,),
                )
            conn.commit()
    return {"ok": True, "connection": _public_connection(dict(row), has_secret=False)}


def list_sync_runs(
    legacy: Any,
    context: dict[str, Any],
    *,
    connection_id: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    lim = max(1, min(int(limit or 25), 100))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            if connection_id:
                cur.execute(
                    """
                    SELECT * FROM employee_migration_sync_runs
                    WHERE company_code=%s AND connection_id=%s
                    ORDER BY started_at DESC LIMIT %s
                    """,
                    (company, connection_id, lim),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM employee_migration_sync_runs
                    WHERE company_code=%s
                    ORDER BY started_at DESC LIMIT %s
                    """,
                    (company, lim),
                )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return {"ok": True, "runs": [_public_sync_run(r) for r in rows]}


def _load_secrets(legacy: Any, cur: Any, connection_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT ciphertext, alg, key_version
        FROM employee_migration_connection_secrets
        WHERE connection_id=%s
        """,
        (connection_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    # Fail closed — never silently return empty and sync without auth when secrets exist.
    opened = _open_secret(legacy, row["ciphertext"], alg=row.get("alg"))
    try:
        parsed = json.loads(opened)
    except Exception as exc:
        raise ConnectorSecretError(
            "connector_secret_corrupt",
            "Stored connector credentials are corrupt and must be re-entered.",
        ) from exc
    if not isinstance(parsed, dict):
        raise ConnectorSecretError(
            "connector_secret_corrupt",
            "Stored connector credentials are corrupt and must be re-entered.",
        )
    return parsed


def mark_credentials_reentry_required(
    cur: Any,
    *,
    company: str,
    connection_id: str,
    actor: str | None,
    reason_code: str,
) -> None:
    """Delete insecure/unusable secret and flag connection for admin re-entry."""
    cur.execute(
        "DELETE FROM employee_migration_connection_secrets WHERE connection_id=%s",
        (connection_id,),
    )
    summary = f"credentials_require_reentry:{reason_code}"
    cur.execute(
        """
        UPDATE employee_migration_connections
        SET status='error',
            last_error_summary=%s,
            schedule_enabled=FALSE,
            sync_lock_until=NULL,
            sync_lock_owner=NULL,
            updated_at=now()
        WHERE connection_id=%s AND company_code=%s
        """,
        (summary, connection_id, company),
    )
    _audit(
        cur,
        company=company,
        connection_id=connection_id,
        actor=actor,
        action="credentials_require_reentry",
        detail={"reason_code": reason_code},
    )


def audit_and_remediate_insecure_secrets(
    legacy: Any,
    *,
    company_code: str | None = None,
    actor: str = "p5_2_secret_hardening",
) -> dict[str, Any]:
    """Find plainhex/plaintext connector secrets; reseal when possible, else require re-entry.

    Never prints or returns secret values.
    """
    results: list[dict[str, Any]] = []
    enc_ok = False
    try:
        enc_ok = bool(
            hasattr(legacy, "sensitive_encryption_available")
            and legacy.sensitive_encryption_available()
        )
    except Exception:
        enc_ok = False

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            params: list[Any] = []
            company_clause = ""
            if company_code:
                company_clause = "AND c.company_code=%s"
                params.append(str(company_code).strip().upper())
            cur.execute(
                f"""
                SELECT s.connection_id, s.ciphertext, s.alg, s.key_version,
                       c.company_code, c.name, c.status, c.connector_kind
                FROM employee_migration_connection_secrets s
                JOIN employee_migration_connections c ON c.connection_id = s.connection_id
                WHERE (
                  s.alg IN ('plainhex', 'plaintext', 'none', 'clear')
                  OR s.ciphertext LIKE 'plainhex:%%'
                  OR s.ciphertext LIKE 'plaintext:%%'
                  OR s.key_version = 'dev_plainhex'
                )
                {company_clause}
                ORDER BY c.company_code, s.connection_id
                """,
                params,
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            for row in rows:
                cid = str(row["connection_id"])
                company = str(row["company_code"])
                entry: dict[str, Any] = {
                    "connection_id": cid,
                    "company_code": company,
                    "connector_kind": row.get("connector_kind"),
                    "prior_alg": row.get("alg"),
                    "prior_key_version": row.get("key_version"),
                    "insecure": True,
                }
                if enc_ok and str(row.get("ciphertext") or "").startswith("plainhex:"):
                    try:
                        plaintext = _read_plainhex_for_migration_only(str(row["ciphertext"]))
                        sealed = _seal_secret(legacy, plaintext)
                        cur.execute(
                            """
                            UPDATE employee_migration_connection_secrets
                            SET ciphertext=%s, key_version=%s, alg=%s, updated_at=now()
                            WHERE connection_id=%s
                            """,
                            (
                                sealed["ciphertext"],
                                sealed.get("key_version"),
                                sealed.get("alg") or "fernet",
                                cid,
                            ),
                        )
                        cur.execute(
                            """
                            UPDATE employee_migration_connections
                            SET last_error_summary=NULL,
                                status=CASE WHEN status='error' THEN 'active' ELSE status END,
                                updated_at=now()
                            WHERE connection_id=%s
                            """,
                            (cid,),
                        )
                        _audit(
                            cur,
                            company=company,
                            connection_id=cid,
                            actor=actor,
                            action="credentials_resealed",
                            detail={
                                "from_alg": row.get("alg"),
                                "to_alg": sealed.get("alg"),
                                "to_key_version": sealed.get("key_version"),
                            },
                        )
                        entry["action"] = "resealed"
                        entry["alg"] = sealed.get("alg")
                        results.append(entry)
                        continue
                    except Exception:
                        pass
                mark_credentials_reentry_required(
                    cur,
                    company=company,
                    connection_id=cid,
                    actor=actor,
                    reason_code="insecure_secret_storage",
                )
                entry["action"] = "require_reentry"
                results.append(entry)
            conn.commit()

    return {
        "ok": True,
        "encryption_available": enc_ok,
        "scanned_insecure": len(results),
        "resealed": sum(1 for r in results if r.get("action") == "resealed"),
        "require_reentry": sum(1 for r in results if r.get("action") == "require_reentry"),
        "results": results,
        "honesty": honesty_payload(),
    }


def _try_acquire_sync_lock(cur: Any, *, connection_id: str, owner: str) -> bool:
    cur.execute(
        """
        UPDATE employee_migration_connections
        SET sync_lock_until = now() + (%s || ' minutes')::interval,
            sync_lock_owner = %s,
            updated_at = now()
        WHERE connection_id = %s
          AND (sync_lock_until IS NULL OR sync_lock_until < now())
        RETURNING connection_id
        """,
        (str(LOCK_TTL_MINUTES), owner, connection_id),
    )
    return bool(cur.fetchone())


def _release_sync_lock(cur: Any, *, connection_id: str, owner: str | None = None) -> None:
    if owner:
        cur.execute(
            """
            UPDATE employee_migration_connections
            SET sync_lock_until = NULL, sync_lock_owner = NULL, updated_at = now()
            WHERE connection_id = %s AND (sync_lock_owner = %s OR sync_lock_owner IS NULL)
            """,
            (connection_id, owner),
        )
    else:
        cur.execute(
            """
            UPDATE employee_migration_connections
            SET sync_lock_until = NULL, sync_lock_owner = NULL, updated_at = now()
            WHERE connection_id = %s
            """,
            (connection_id,),
        )


def _next_sync_for_row(crow: dict[str, Any], cfg: dict[str, Any]) -> datetime:
    return compute_next_sync_at(
        timezone_name=crow.get("timezone"),
        schedule_interval_minutes=crow.get("schedule_interval_minutes"),
        schedule_cron=crow.get("schedule_cron"),
        config=cfg,
    )


def _record_processed_files(
    cur: Any,
    *,
    company: str,
    connection_id: str,
    sync_run_id: str,
    fetch_meta: dict[str, Any],
) -> None:
    for f in fetch_meta.get("files_ok") or []:
        sha = str(f.get("content_sha256") or "").strip()
        if not sha:
            continue
        cur.execute(
            """
            INSERT INTO employee_migration_processed_files (
              company_code, connection_id, content_sha256, remote_path,
              remote_size, remote_mtime, processed_at, sync_run_id
            ) VALUES (%s,%s,%s,%s,%s,%s,now(),%s)
            ON CONFLICT (connection_id, content_sha256) DO UPDATE SET
              processed_at = now(),
              sync_run_id = EXCLUDED.sync_run_id,
              remote_path = EXCLUDED.remote_path
            """,
            (
                company,
                connection_id,
                sha,
                str(f.get("path") or f.get("name") or ""),
                f.get("size"),
                None,
                sync_run_id,
            ),
        )


def _apply_failure_schedule(
    cur: Any,
    *,
    crow: dict[str, Any],
    connection_id: str,
    error_code: str | None,
    error_summary: str | None,
    cfg: dict[str, Any],
) -> None:
    """Backoff for transient failures; keep schedule for next attempt without duplicate apply."""
    retry_count = int(crow.get("retry_count") or 0) + 1
    if error_code in TRANSIENT_ERROR_CODES:
        retry_after = compute_retry_after(retry_count=retry_count)
        next_sync = retry_after
        status = "active" if crow.get("schedule_enabled") else "error"
    else:
        retry_after = None
        next_sync = (
            _next_sync_for_row(crow, cfg)
            if crow.get("schedule_enabled")
            else crow.get("next_sync_at")
        )
        status = "error"
    cur.execute(
        """
        UPDATE employee_migration_connections
        SET status=%s, last_sync_at=now(), last_error_summary=%s, updated_at=now(),
            retry_count=%s, retry_after=%s, next_sync_at=%s,
            sync_lock_until=NULL, sync_lock_owner=NULL
        WHERE connection_id=%s
        """,
        (status, error_summary, retry_count, retry_after, next_sync, connection_id),
    )


def run_sync(
    legacy: Any,
    context: dict[str, Any],
    *,
    connection_id: str,
    trigger: str = "manual",
    auto_commit: bool = False,
    force_full: bool = False,
) -> dict[str, Any]:
    """Fetch via connector → foundation preview (optional commit). Never bypasses authority."""
    company = _company_for_sync(legacy, context)
    import employee_migration_foundation as emf

    emf.require_foundation(legacy, company)
    trig = str(trigger or "manual").strip()
    if trig not in SYNC_TRIGGERS:
        trig = "manual"
    actor = str(context.get("user_id") or context.get("email") or "") or None
    lock_owner = f"{actor or 'sync'}:{uuid.uuid4().hex[:8]}"

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            # Serialize concurrent workers on the same connection.
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"emp_mig_sync:{connection_id}",),
            )
            cur.execute(
                """
                SELECT * FROM employee_migration_connections
                WHERE company_code=%s AND connection_id=%s
                FOR UPDATE
                """,
                (company, connection_id),
            )
            crow = cur.fetchone()
            if not crow:
                raise legacy.HTTPException(status_code=404, detail={"error": "connection_not_found"})
            crow = dict(crow)
            if crow.get("status") == "paused":
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "connection_paused", "message": "Resume the connection before syncing."},
                )
            if crow.get("status") == "disconnected":
                raise legacy.HTTPException(status_code=409, detail={"error": "connection_disconnected"})
            preclaimed = context.get("_preclaimed_lock_owner")
            if (
                preclaimed
                and crow.get("sync_lock_owner")
                and str(crow.get("sync_lock_owner")) == str(preclaimed)
                and crow.get("sync_lock_until")
            ):
                lock_owner = str(preclaimed)
            elif not _try_acquire_sync_lock(cur, connection_id=connection_id, owner=lock_owner):
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "sync_in_progress", "message": "Another sync is already running for this connection."},
                )
            cfg = crow.get("config") or {}
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            cursor = crow.get("cursor_json") or {}
            if isinstance(cursor, str):
                cursor = json.loads(cursor)
            if force_full:
                cfg = {**cfg, "sync_mode": "full"}
                cursor = {}
            secret_error: ConnectorSecretError | None = None
            secrets: dict[str, Any] = {}
            try:
                secrets = _load_secrets(legacy, cur, connection_id)
            except ConnectorSecretError as exc:
                secret_error = exc
            cur.execute(
                """
                INSERT INTO employee_migration_sync_runs (
                  company_code, connection_id, trigger, status, cursor_before, metadata
                ) VALUES (%s,%s,%s,'running',%s::jsonb,%s::jsonb)
                RETURNING *
                """,
                (
                    company,
                    connection_id,
                    trig,
                    json.dumps(cursor),
                    json.dumps(
                        {
                            "actor": actor,
                            "auto_commit": auto_commit,
                            "force_full": force_full,
                            "lock_owner": lock_owner,
                        }
                    ),
                ),
            )
            run = dict(cur.fetchone())
            run_id = str(run["sync_run_id"])
            if secret_error is not None:
                cur.execute(
                    """
                    UPDATE employee_migration_sync_runs
                    SET status='failed', finished_at=now(), error_code=%s, error_summary=%s
                    WHERE sync_run_id=%s
                    RETURNING *
                    """,
                    (secret_error.code, secret_error.message, run_id),
                )
                run = dict(cur.fetchone())
                # Do not apply; flag connection for credential re-entry / config error.
                if secret_error.code in {
                    "insecure_secret_storage_rejected",
                    "connector_secret_decrypt_failed",
                    "connector_secret_corrupt",
                    "connector_secret_missing",
                }:
                    mark_credentials_reentry_required(
                        cur,
                        company=company,
                        connection_id=connection_id,
                        actor=actor,
                        reason_code=secret_error.code,
                    )
                else:
                    cur.execute(
                        """
                        UPDATE employee_migration_connections
                        SET status='error', last_sync_at=now(), last_error_summary=%s,
                            sync_lock_until=NULL, sync_lock_owner=NULL, updated_at=now()
                        WHERE connection_id=%s
                        """,
                        (secret_error.message, connection_id),
                    )
                _audit(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    actor=actor,
                    action="sync_failed",
                    detail={
                        "sync_run_id": run_id,
                        "error_code": secret_error.code,
                        "trigger": trig,
                        "secret_unreadable": True,
                    },
                )
                conn.commit()
                return {
                    "ok": False,
                    "error": secret_error.code,
                    "message": secret_error.message,
                    "run": _public_sync_run(run),
                }
            conn.commit()

    error_code = None
    error_summary = None
    fetch_result: dict[str, Any] | None = None
    try:
        fetch_result = fetch_connector_rows(
            connector_kind=str(crow["connector_kind"]),
            config=cfg,
            secrets=secrets,
            cursor=cursor,
            company=company,
            connection_id=connection_id,
            legacy=legacy,
        )
    except PermissionError:
        error_code, error_summary = "auth_failed", "Could not authenticate with the connected system."
    except TimeoutError:
        error_code, error_summary = "timeout", "The connected system timed out."
    except ConnectionError:
        error_code, error_summary = "unavailable", "The connected system is unavailable."
    except Exception as exc:
        error_code, error_summary = "fetch_failed", str(exc)[:180]

    if error_code:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_sync_runs
                    SET status='failed', finished_at=now(), error_code=%s, error_summary=%s
                    WHERE sync_run_id=%s
                    RETURNING *
                    """,
                    (error_code, error_summary, run_id),
                )
                run = dict(cur.fetchone())
                _apply_failure_schedule(
                    cur,
                    crow=crow,
                    connection_id=connection_id,
                    error_code=error_code,
                    error_summary=error_summary,
                    cfg=cfg,
                )
                _audit(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    actor=actor,
                    action="sync_failed",
                    detail={"sync_run_id": run_id, "error_code": error_code, "trigger": trig},
                )
                conn.commit()
        return {"ok": False, "error": error_code, "message": error_summary, "run": _public_sync_run(run)}

    assert fetch_result is not None
    rows = fetch_result.get("rows") or []
    lifecycle = fetch_result.get("lifecycle_signals") or []
    cursor_after = fetch_result.get("cursor_after") or {}
    fetch_meta = fetch_result.get("meta") or {}

    def _run_lifecycle(*, after_commit: bool) -> dict[str, Any]:
        del after_commit
        if not lifecycle:
            return {"ok": True, "counts": {}, "events": []}
        import employee_migration_lifecycle as p6

        # Policy (not sync auto_commit) gates whether termination/reactivation auto-applies.
        return p6.process_lifecycle_signals(
            legacy,
            context,
            connection=crow,
            sync_run_id=run_id,
            signals=list(lifecycle),
            auto_commit_apply=True,
        )
    # Strip internal provenance helpers from employee CSV when present
    clean_rows = []
    for r in rows:
        clean_rows.append({k: v for k, v in r.items() if not str(k).startswith("_source_file")})
    raw, _headers = _rows_to_csv(clean_rows)
    filename = f"sync-{crow['source_system']}-{run_id[:8]}.csv"
    idem = f"sync:{connection_id}:{hashlib.sha256(raw).hexdigest()}"

    # Empty new-file feed: still success — advance cursor/schedule, no foundation batch.
    if not clean_rows and fetch_meta.get("kind") == "sftp" and fetch_meta.get("status_hint") in {
        "no_new_files",
        "partial_files",
        "all_files_failed",
    }:
        status = "failed" if fetch_meta.get("status_hint") == "all_files_failed" else "previewed"
        if fetch_meta.get("status_hint") == "partial_files" and fetch_meta.get("files_failed"):
            status = "partial"
        if fetch_meta.get("status_hint") == "all_files_failed":
            error_code, error_summary = "malformed_files", "All remote files failed to parse."
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_sync_runs
                    SET status=%s, finished_at=now(), cursor_after=%s::jsonb,
                        records_fetched=0, error_code=%s, error_summary=%s,
                        metadata = metadata || %s::jsonb
                    WHERE sync_run_id=%s RETURNING *
                    """,
                    (
                        status,
                        json.dumps(cursor_after),
                        error_code,
                        error_summary,
                        json.dumps({"fetch_meta": fetch_meta}),
                        run_id,
                    ),
                )
                run = dict(cur.fetchone())
                if status == "failed":
                    _apply_failure_schedule(
                        cur,
                        crow=crow,
                        connection_id=connection_id,
                        error_code=error_code or "malformed_files",
                        error_summary=error_summary,
                        cfg=cfg,
                    )
                else:
                    next_sync = (
                        _next_sync_for_row(crow, cfg) if crow.get("schedule_enabled") else crow.get("next_sync_at")
                    )
                    cur.execute(
                        """
                        UPDATE employee_migration_connections
                        SET cursor_json=%s::jsonb, last_sync_at=now(), last_success_at=now(),
                            last_error_summary=NULL, status='active', updated_at=now(),
                            next_sync_at=%s, retry_count=0, retry_after=NULL,
                            sync_lock_until=NULL, sync_lock_owner=NULL
                        WHERE connection_id=%s
                        """,
                        (json.dumps(cursor_after), next_sync, connection_id),
                    )
                _audit(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    actor=actor,
                    action="manual_sync" if trig == "manual" else f"sync_{trig}",
                    detail={"sync_run_id": run_id, "status": status, "empty_feed": True},
                )
                conn.commit()
        lifecycle_result = _run_lifecycle(after_commit=True)
        return {
            "ok": status != "failed",
            "run": _public_sync_run(run),
            "batch_id": None,
            "preview": None,
            "commit": None,
            "lifecycle_signals": lifecycle,
            "lifecycle": lifecycle_result,
            "honesty": honesty_payload(),
        }

    # Foundation preview — same classification/authority as file import
    try:
        preview = emf.preview_or_replay_import(
            legacy,
            context,
            raw=raw,
            filename=filename,
            source_system=str(crow["source_system"]),
            idempotency_key=idem,
        )
    except Exception as exc:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_sync_runs
                    SET status='failed', finished_at=now(), error_code='preview_failed',
                        error_summary=%s, records_fetched=%s, lifecycle_signals=%s::jsonb
                    WHERE sync_run_id=%s RETURNING *
                    """,
                    (str(exc)[:180], len(clean_rows), json.dumps(lifecycle), run_id),
                )
                run = dict(cur.fetchone())
                _apply_failure_schedule(
                    cur,
                    crow=crow,
                    connection_id=connection_id,
                    error_code="preview_failed",
                    error_summary=str(exc)[:180],
                    cfg=cfg,
                )
                conn.commit()
        return {"ok": False, "error": "preview_failed", "message": str(exc)[:180], "run": _public_sync_run(run)}

    batch_id = preview.get("batch_id")
    totals = preview.get("totals") or {}
    # Stamp batch metadata with sync_run linkage
    if batch_id:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_import_batches
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb, updated_at=now()
                    WHERE batch_id=%s AND company_code=%s
                    """,
                    (
                        json.dumps(
                            {
                                "sync_run_id": run_id,
                                "connection_id": connection_id,
                                "connector_kind": crow["connector_kind"],
                                "contract": CONTRACT,
                            }
                        ),
                        batch_id,
                        company,
                    ),
                )
                conn.commit()

    commit_result = None
    status = "previewed"
    if auto_commit:
        try:
            commit_result = emf.commit_import_batch(
                legacy,
                context,
                batch_id=str(batch_id),
                raw=raw,
                filename=filename,
                source_system=str(crow["source_system"]),
                idempotency_key=f"{idem}:commit",
            )
            status = "committed" if commit_result.get("status") in {"committed", "partial", "replayed"} else "partial"
            if commit_result.get("status") == "partial":
                status = "partial"
        except Exception as exc:
            status = "partial"
            error_code = "commit_failed"
            error_summary = str(exc)[:180]

    # SFTP: one bad file among good → partial
    if fetch_meta.get("files_failed") and status in {"previewed", "committed"}:
        status = "partial"

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_migration_sync_runs
                SET status=%s, finished_at=now(), cursor_after=%s::jsonb,
                    records_fetched=%s,
                    created_count=%s, updated_count=%s, unchanged_count=%s,
                    review_count=%s, failed_count=%s,
                    batch_id=%s, error_code=%s, error_summary=%s,
                    lifecycle_signals=%s::jsonb,
                    metadata = metadata || %s::jsonb
                WHERE sync_run_id=%s
                RETURNING *
                """,
                (
                    status,
                    json.dumps(cursor_after),
                    len(clean_rows),
                    int(totals.get("create") or 0),
                    int(totals.get("update") or 0),
                    int(totals.get("skip") or 0),
                    int(totals.get("review") or totals.get("conflict") or 0),
                    int(totals.get("invalid") or 0) + len(fetch_meta.get("files_failed") or []),
                    batch_id,
                    error_code,
                    error_summary,
                    json.dumps(lifecycle),
                    json.dumps({"fetch_meta": fetch_meta}),
                    run_id,
                ),
            )
            run = dict(cur.fetchone())
            # Advance cursor only on successful preview/commit (not failed fetch)
            if status in {"previewed", "committed", "partial"}:
                next_sync = (
                    _next_sync_for_row(crow, cfg) if crow.get("schedule_enabled") else crow.get("next_sync_at")
                )
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET cursor_json=%s::jsonb, last_sync_at=now(),
                        last_success_at=CASE WHEN %s IN ('previewed','committed','partial') THEN now() ELSE last_success_at END,
                        last_error_summary=%s,
                        status='active',
                        updated_at=now(),
                        next_sync_at=%s,
                        retry_count=0,
                        retry_after=NULL,
                        sync_lock_until=NULL,
                        sync_lock_owner=NULL
                    WHERE connection_id=%s
                    """,
                    (
                        json.dumps(cursor_after),
                        status,
                        error_summary,
                        next_sync,
                        connection_id,
                    ),
                )
                _record_processed_files(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    sync_run_id=run_id,
                    fetch_meta=fetch_meta,
                )
            else:
                _release_sync_lock(cur, connection_id=connection_id, owner=lock_owner)
            _audit(
                cur,
                company=company,
                connection_id=connection_id,
                actor=actor,
                action="manual_sync" if trig == "manual" else f"sync_{trig}",
                detail={"sync_run_id": run_id, "status": status, "batch_id": batch_id},
            )
            conn.commit()

    # Lifecycle after roster apply so source mappings exist for same-run creates
    lifecycle_result = _run_lifecycle(after_commit=status in {"previewed", "committed", "partial"})
    if lifecycle_result.get("events"):
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_sync_runs
                    SET metadata = metadata || %s::jsonb
                    WHERE sync_run_id=%s
                    RETURNING *
                    """,
                    (
                        json.dumps(
                            {
                                "lifecycle": {
                                    "counts": lifecycle_result.get("counts") or {},
                                    "events": len(lifecycle_result.get("events") or []),
                                }
                            }
                        ),
                        run_id,
                    ),
                )
                run = dict(cur.fetchone())
                conn.commit()

    return {
        "ok": True,
        "run": _public_sync_run(run),
        "batch_id": batch_id,
        "preview": preview,
        "commit": commit_result,
        "lifecycle_signals": lifecycle,
        "lifecycle": lifecycle_result,
        "honesty": honesty_payload(),
    }


def claim_due_connections(
    legacy: Any,
    *,
    company_code: str | None = None,
    limit: int = 20,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    """Atomically claim due scheduled connections (SKIP LOCKED + row lock TTL)."""
    lim = max(1, min(int(limit or 20), 100))
    claim_owner = owner or f"scheduler:{uuid.uuid4().hex[:10]}"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            params: list[Any] = [str(LOCK_TTL_MINUTES), claim_owner]
            company_clause = ""
            if company_code:
                company_clause = "AND company_code=%s"
                params.append(str(company_code).strip().upper())
            params.append(lim)
            cur.execute(
                f"""
                UPDATE employee_migration_connections c
                SET sync_lock_until = now() + (%s || ' minutes')::interval,
                    sync_lock_owner = %s,
                    updated_at = now()
                WHERE c.connection_id IN (
                  SELECT connection_id FROM employee_migration_connections
                  WHERE status = 'active'
                    AND schedule_enabled IS TRUE
                    AND (retry_after IS NULL OR retry_after <= now())
                    AND (next_sync_at IS NULL OR next_sync_at <= now())
                    AND (sync_lock_until IS NULL OR sync_lock_until < now())
                    {company_clause}
                  ORDER BY next_sync_at NULLS FIRST, updated_at ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
                )
                RETURNING *
                """,
                params,
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return rows


def run_scheduler_tick(
    legacy: Any,
    *,
    company_code: str | None = None,
    limit: int = 20,
    auto_commit: bool = True,
) -> dict[str, Any]:
    """Production scheduler entry: claim due connections and invoke run_sync."""
    claimed = claim_due_connections(legacy, company_code=company_code, limit=limit)
    results = []
    for crow in claimed:
        cid = str(crow["connection_id"])
        company = str(crow["company_code"])
        ctx = scheduler_service_context(company)
        ctx["_preclaimed_lock_owner"] = crow.get("sync_lock_owner")
        try:
            cfg = crow.get("config") or {}
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            do_commit = bool(cfg.get("auto_commit_on_schedule", auto_commit))
            results.append(
                run_sync(
                    legacy,
                    ctx,
                    connection_id=cid,
                    trigger="scheduled",
                    auto_commit=do_commit,
                )
            )
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            err = detail if isinstance(detail, dict) else {"error": str(exc)[:180]}
            results.append({"ok": False, "connection_id": cid, "error": err})
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    _release_sync_lock(cur, connection_id=cid)
                    conn.commit()
    return {
        "ok": True,
        "claimed": len(claimed),
        "ran": len(results),
        "results": results,
        "honesty": honesty_payload(),
    }


def tick_scheduled_syncs(legacy: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Company-scoped tick (dashboard). Uses the same claim → run_sync pipeline."""
    company = legacy.require_employee_roster_admin(context)
    return run_scheduler_tick(legacy, company_code=company, limit=50, auto_commit=False)


def connector_kinds_catalog(company_code: str | None = None) -> dict[str, Any]:
    import production_data_safety as _pds

    canary_available = _pds.synthetic_connectors_allowed(company_code)
    return {
        "ok": True,
        "kinds": [
            {
                "kind": "deterministic_canary",
                "label": "Wathefni canary (deterministic)",
                "supports_incremental": True,
                "supports_schedule": True,
                "credentials_required": False,
                "available": canary_available,
                "synthetic": True,
            },
            {
                "kind": "scheduled_csv",
                "label": "Scheduled CSV / file feed",
                "supports_incremental": False,
                "supports_schedule": True,
                "credentials_required": False,
                "note": "Uses full snapshot diff when incremental is unavailable",
            },
            {
                "kind": "sftp",
                "label": "SFTP / file feed",
                "supports_incremental": True,
                "supports_schedule": True,
                "credentials_required": True,
                "available": True,
                "formats": ["csv", "xlsx"],
                "auth": ["password", "private_key"],
            },
            {
                "kind": "api_stub",
                "label": "API connector (coming soon)",
                "supports_incremental": True,
                "supports_schedule": True,
                "credentials_required": True,
                "available": False,
            },
        ],
        "honesty": honesty_payload(),
    }
