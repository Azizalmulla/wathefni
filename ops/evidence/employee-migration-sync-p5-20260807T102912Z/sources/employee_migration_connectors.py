"""Migration & Sync P5 — Connected Systems connectors + sync runs.

Connectors fetch external rows and feed the existing foundation
preview/commit pipeline. No parallel apply engine.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import schema_contract

CONTRACT = "employee_migration_sync_p5_connectors"
CONTRACT_VERSION = "5.0.0"

CONNECTOR_KINDS = frozenset(
    {"deterministic_canary", "scheduled_csv", "api_stub", "sftp_stub"}
)
CONNECTION_STATUSES = frozenset({"active", "paused", "disconnected", "error"})
SYNC_TRIGGERS = frozenset({"manual", "scheduled", "retry"})
SYNC_STATUSES = frozenset(
    {"running", "previewed", "committed", "failed", "cancelled", "partial"}
)

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
    'deterministic_canary','scheduled_csv','api_stub','sftp_stub'
  ])),
  CHECK (status = ANY (ARRAY['active','paused','disconnected','error']))
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_conn_company
  ON employee_migration_connections(company_code, status);

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
        "lifecycle_signals_captured_only": True,
        "secrets_never_in_api": True,
        "connector_kinds": sorted(CONNECTOR_KINDS),
        "canary_connector": "deterministic_canary",
    }


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
        ],
        module="employee_migration_connectors",
        lock_id=None,
    )
    _SCHEMA_READY = True


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
        "has_credentials": bool(has_secret),
        "cursor_present": bool(row.get("cursor_json")),
        "last_sync_at": _jsonable(row.get("last_sync_at")),
        "last_success_at": _jsonable(row.get("last_success_at")),
        "next_sync_at": _jsonable(row.get("next_sync_at")),
        "last_error_summary": row.get("last_error_summary"),
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


def _seal_secret(legacy: Any, plaintext: str) -> dict[str, str]:
    if hasattr(legacy, "encrypt_sensitive_text") and legacy.sensitive_encryption_available():
        return legacy.encrypt_sensitive_text(plaintext)
    # Dev/canary fallback when mailbox key unset — still not returned to API.
    token = plaintext.encode("utf-8").hex()
    return {"ciphertext": f"plainhex:{token}", "key_version": "dev_plainhex", "alg": "plainhex"}


def _open_secret(legacy: Any, ciphertext: str) -> str:
    text = str(ciphertext or "")
    if text.startswith("plainhex:"):
        return bytes.fromhex(text[len("plainhex:") :]).decode("utf-8")
    return legacy.decrypt_sensitive_text(text)


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
) -> dict[str, Any]:
    """Common connector contract → rows + cursor + lifecycle signals."""
    secrets = secrets or {}
    cursor = cursor or {}
    kind = str(connector_kind or "").strip()

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
                    "external_employee_id": f"CANARY-{config.get('fixture_tag') or 'p5canary'}-Z",
                    "note": "Captured only — P6 owns deactivation policy",
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
            )
        reader = csv.DictReader(io.StringIO(raw_csv))
        rows = [{k: (v or "") for k, v in dict(r).items()} for r in reader]
        return {
            "rows": rows,
            "cursor_after": {"content_sha": hashlib.sha256(raw_csv.encode()).hexdigest(), "mode": "full_snapshot"},
            "lifecycle_signals": [],
            "meta": {"kind": kind, "fetched": len(rows), "diff_mode": "full_snapshot"},
        }

    if kind in {"api_stub", "sftp_stub"}:
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
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    import employee_migration_foundation as emf

    emf.require_foundation(legacy, company)
    kind = str(connector_kind or "").strip()
    if kind not in CONNECTOR_KINDS:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_connector_kind"})
    name_s = str(name or "").strip()
    if not name_s:
        raise legacy.HTTPException(status_code=422, detail={"error": "name_required"})
    src = str(source_system or "").strip() or f"connector:{kind}"
    cfg = dict(config or {})
    actor = str(context.get("user_id") or context.get("email") or "") or None
    next_sync = None
    if schedule_enabled and schedule_cron:
        next_sync = _now() + timedelta(hours=1)

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_migration_connections (
                  company_code, name, connector_kind, source_system, status, config,
                  schedule_cron, schedule_enabled, next_sync_at, created_by
                ) VALUES (%s,%s,%s,%s,'active',%s::jsonb,%s,%s,%s,%s)
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
                    next_sync,
                    actor,
                ),
            )
            row = dict(cur.fetchone())
            cid = str(row["connection_id"])
            has_secret = False
            if credentials:
                sealed = _seal_secret(legacy, json.dumps(credentials))
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
                detail={"connector_kind": kind, "source_system": src},
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
    clear_cursor: bool = False,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    actor = str(context.get("user_id") or context.get("email") or "") or None
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
            if schedule_enabled is not None:
                sets.append("schedule_enabled=%s")
                params.append(bool(schedule_enabled))
                if schedule_enabled:
                    sets.append("next_sync_at=%s")
                    params.append(_now() + timedelta(hours=1))
            if clear_cursor:
                sets.append("cursor_json='{}'::jsonb")
            params.extend([connection_id, company])
            cur.execute(
                f"UPDATE employee_migration_connections SET {', '.join(sets)} WHERE connection_id=%s AND company_code=%s RETURNING *",
                params,
            )
            updated = dict(cur.fetchone())
            has_secret = False
            if credentials is not None:
                sealed = _seal_secret(legacy, json.dumps(credentials))
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
        "SELECT ciphertext FROM employee_migration_connection_secrets WHERE connection_id=%s",
        (connection_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    try:
        return json.loads(_open_secret(legacy, row["ciphertext"]))
    except Exception:
        return {}


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
    company = legacy.require_employee_roster_admin(context)
    import employee_migration_foundation as emf

    emf.require_foundation(legacy, company)
    trig = str(trigger or "manual").strip()
    if trig not in SYNC_TRIGGERS:
        trig = "manual"
    actor = str(context.get("user_id") or context.get("email") or "") or None

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
            cfg = crow.get("config") or {}
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            cursor = crow.get("cursor_json") or {}
            if isinstance(cursor, str):
                cursor = json.loads(cursor)
            if force_full:
                cfg = {**cfg, "sync_mode": "full"}
                cursor = {}
            secrets = _load_secrets(legacy, cur, connection_id)
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
                    json.dumps({"actor": actor, "auto_commit": auto_commit, "force_full": force_full}),
                ),
            )
            run = dict(cur.fetchone())
            run_id = str(run["sync_run_id"])
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
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET status='error', last_sync_at=now(), last_error_summary=%s, updated_at=now()
                    WHERE connection_id=%s
                    """,
                    (error_summary, connection_id),
                )
                _audit(
                    cur,
                    company=company,
                    connection_id=connection_id,
                    actor=actor,
                    action="sync_failed",
                    detail={"sync_run_id": run_id, "error_code": error_code},
                )
                conn.commit()
        return {"ok": False, "error": error_code, "message": error_summary, "run": _public_sync_run(run)}

    assert fetch_result is not None
    rows = fetch_result.get("rows") or []
    lifecycle = fetch_result.get("lifecycle_signals") or []
    cursor_after = fetch_result.get("cursor_after") or {}
    raw, _headers = _rows_to_csv(rows)
    filename = f"sync-{crow['source_system']}-{run_id[:8]}.csv"
    idem = f"sync:{connection_id}:{hashlib.sha256(raw).hexdigest()}"

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
                    (str(exc)[:180], len(rows), json.dumps(lifecycle), run_id),
                )
                run = dict(cur.fetchone())
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
                    len(rows),
                    int(totals.get("create") or 0),
                    int(totals.get("update") or 0),
                    int(totals.get("skip") or 0),
                    int(totals.get("review") or totals.get("conflict") or 0),
                    int(totals.get("invalid") or 0),
                    batch_id,
                    error_code,
                    error_summary,
                    json.dumps(lifecycle),
                    json.dumps({"fetch_meta": fetch_result.get("meta") or {}}),
                    run_id,
                ),
            )
            run = dict(cur.fetchone())
            # Advance cursor only on successful preview/commit (not failed fetch)
            if status in {"previewed", "committed", "partial"}:
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET cursor_json=%s::jsonb, last_sync_at=now(),
                        last_success_at=CASE WHEN %s IN ('previewed','committed') THEN now() ELSE last_success_at END,
                        last_error_summary=%s,
                        status='active',
                        updated_at=now(),
                        next_sync_at=CASE WHEN schedule_enabled THEN now() + interval '1 hour' ELSE next_sync_at END
                    WHERE connection_id=%s
                    """,
                    (
                        json.dumps(cursor_after),
                        status,
                        error_summary,
                        connection_id,
                    ),
                )
            _audit(
                cur,
                company=company,
                connection_id=connection_id,
                actor=actor,
                action="manual_sync" if trig == "manual" else f"sync_{trig}",
                detail={"sync_run_id": run_id, "status": status, "batch_id": batch_id},
            )
            conn.commit()

    return {
        "ok": True,
        "run": _public_sync_run(run),
        "batch_id": batch_id,
        "preview": preview,
        "commit": commit_result,
        "lifecycle_signals": lifecycle,
        "honesty": honesty_payload(),
    }


def tick_scheduled_syncs(legacy: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Run due scheduled connections for this company (manual tick / worker entry)."""
    company = legacy.require_employee_roster_admin(context)
    ran = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_connectors_schema(cur)
            cur.execute(
                """
                SELECT connection_id FROM employee_migration_connections
                WHERE company_code=%s AND status='active' AND schedule_enabled IS TRUE
                  AND (next_sync_at IS NULL OR next_sync_at <= now())
                """,
                (company,),
            )
            ids = [str(r["connection_id"]) for r in (cur.fetchall() or [])]
            conn.commit()
    for cid in ids:
        ran.append(run_sync(legacy, context, connection_id=cid, trigger="scheduled", auto_commit=False))
    return {"ok": True, "ran": len(ran), "results": ran}


def connector_kinds_catalog() -> dict[str, Any]:
    return {
        "ok": True,
        "kinds": [
            {
                "kind": "deterministic_canary",
                "label": "Wathefni canary (deterministic)",
                "supports_incremental": True,
                "supports_schedule": True,
                "credentials_required": False,
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
                "kind": "api_stub",
                "label": "API connector (coming soon)",
                "supports_incremental": True,
                "supports_schedule": True,
                "credentials_required": True,
                "available": False,
            },
            {
                "kind": "sftp_stub",
                "label": "SFTP connector (coming soon)",
                "supports_incremental": False,
                "supports_schedule": True,
                "credentials_required": True,
                "available": False,
            },
        ],
        "honesty": honesty_payload(),
    }
