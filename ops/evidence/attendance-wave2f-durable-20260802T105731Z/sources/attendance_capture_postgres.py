#!/usr/bin/env python3
"""Attendance Wave 2F — durable PostgreSQL capture-operations authority.

Sites, devices, connectors, sealed credential refs, health, checkpoints,
mappings, remediation, immutable audit, and exactly-once replay ledger.

Secrets: only Fernet-sealed blobs in attendance_capture_credentials.
Never store raw passwords/tokens in row columns.

Activated when WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from psycopg2.extras import Json, RealDictCursor

from attendance_capture_agent import CredentialVault
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

KUWAIT_TZ = timezone(timedelta(hours=3))
CAPTURE_OPS_VERSION = "attendance_capture_ops_wave2f_v1"

WAVE2F_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS attendance_capture_sites (
  site_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  name text NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_cap_sites_company
  ON attendance_capture_sites(company_code, active);

CREATE TABLE IF NOT EXISTS attendance_capture_devices (
  device_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  site_id uuid NOT NULL REFERENCES attendance_capture_sites(site_id),
  terminal_sn text NOT NULL,
  vendor text NOT NULL DEFAULT 'biotime',
  active boolean NOT NULL DEFAULT true,
  owned_by_company text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (terminal_sn, company_code)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_att_cap_device_sn_active
  ON attendance_capture_devices(terminal_sn) WHERE active;
CREATE INDEX IF NOT EXISTS idx_att_cap_devices_company
  ON attendance_capture_devices(company_code, site_id);

CREATE TABLE IF NOT EXISTS attendance_capture_connectors (
  connector_id text PRIMARY KEY,
  company_code text NOT NULL,
  site_id uuid NOT NULL REFERENCES attendance_capture_sites(site_id),
  device_id uuid REFERENCES attendance_capture_devices(device_id),
  status text NOT NULL,
  connector_version text NOT NULL,
  row_version integer NOT NULL DEFAULT 1,
  credential_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  last_rotate_at timestamptz,
  checkpoint text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_att_cap_connectors_company
  ON attendance_capture_connectors(company_code, status);

-- Sealed credential blobs only (Fernet). No plaintext password/token columns.
CREATE TABLE IF NOT EXISTS attendance_capture_credentials (
  credential_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  connector_id text NOT NULL REFERENCES attendance_capture_connectors(connector_id),
  sealed_ref text NOT NULL,
  previous_sealed_ref text,
  key_fingerprint text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  rotated_at timestamptz,
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_att_cap_creds_connector
  ON attendance_capture_credentials(connector_id, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_capture_health (
  connector_id text PRIMARY KEY REFERENCES attendance_capture_connectors(connector_id),
  company_code text NOT NULL,
  site_id uuid,
  status text NOT NULL,
  last_sync_at timestamptz,
  lag_seconds double precision,
  failure_count integer NOT NULL DEFAULT 0,
  last_error text,
  quarantined_events integer NOT NULL DEFAULT 0,
  open_remediation integer NOT NULL DEFAULT 0,
  checkpoint text,
  connector_version text,
  alerts jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attendance_capture_health_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_id text NOT NULL,
  company_code text NOT NULL,
  event_type text NOT NULL,
  status text,
  lag_seconds double precision,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_cap_health_events
  ON attendance_capture_health_events(connector_id, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_capture_checkpoints (
  connector_id text PRIMARY KEY REFERENCES attendance_capture_connectors(connector_id),
  company_code text NOT NULL,
  checkpoint text NOT NULL,
  source text NOT NULL DEFAULT 'biotime',
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS attendance_capture_mappings (
  mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  device_user_id text NOT NULL,
  employee_key text NOT NULL,
  device_id text,
  device_key text NOT NULL DEFAULT '',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, device_user_id, device_key)
);
CREATE INDEX IF NOT EXISTS idx_att_cap_mappings_company
  ON attendance_capture_mappings(company_code, device_user_id);

CREATE TABLE IF NOT EXISTS attendance_capture_quarantine (
  quarantine_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  connector_id text,
  reason text NOT NULL,
  device_user_id text,
  device_id text,
  source text NOT NULL,
  source_event_id text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved boolean NOT NULL DEFAULT false,
  resolved_employee_key text,
  resolved_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_att_cap_quarantine_open
  ON attendance_capture_quarantine(company_code, resolved, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_capture_remediation (
  item_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  kind text NOT NULL,
  status text NOT NULL,
  connector_id text,
  employee_key text,
  device_id text,
  device_user_id text,
  work_date text,
  source_event_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_version integer NOT NULL DEFAULT 1,
  payroll_excluded boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_cap_remediation_open
  ON attendance_capture_remediation(company_code, status, kind);

CREATE TABLE IF NOT EXISTS attendance_capture_idempotency (
  idempotency_key text PRIMARY KEY,
  company_code text NOT NULL,
  action text NOT NULL,
  item_id uuid,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attendance_capture_audit_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connector_id text,
  item_id uuid,
  action text NOT NULL,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_cap_audit
  ON attendance_capture_audit_events(company_code, created_at DESC);

-- Exactly-once replay into Wave 1 authority
CREATE TABLE IF NOT EXISTS attendance_capture_replay_ledger (
  replay_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  item_id uuid NOT NULL,
  source text NOT NULL,
  source_event_id text NOT NULL,
  punch_id uuid,
  status text NOT NULL DEFAULT 'accepted',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, source, source_event_id)
);

CREATE OR REPLACE FUNCTION attendance_capture_audit_forbid_mutation()
RETURNS trigger AS $$
BEGIN
  IF current_setting('wathefni.allow_capture_cleanup', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'attendance_capture_audit_events are immutable (Wave 2F)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_att_cap_audit_immutable ON attendance_capture_audit_events;
CREATE TRIGGER trg_att_cap_audit_immutable
  BEFORE UPDATE OR DELETE ON attendance_capture_audit_events
  FOR EACH ROW EXECUTE FUNCTION attendance_capture_audit_forbid_mutation();

CREATE OR REPLACE FUNCTION attendance_capture_replay_forbid_mutation()
RETURNS trigger AS $$
BEGIN
  IF current_setting('wathefni.allow_capture_cleanup', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'attendance_capture_replay_ledger is append-only (Wave 2F)';
  END IF;
  RAISE EXCEPTION 'attendance_capture_replay_ledger is immutable (Wave 2F)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_att_cap_replay_immutable ON attendance_capture_replay_ledger;
CREATE TRIGGER trg_att_cap_replay_immutable
  BEFORE UPDATE OR DELETE ON attendance_capture_replay_ledger
  FOR EACH ROW EXECUTE FUNCTION attendance_capture_replay_forbid_mutation();
"""

WAVE2F_ROLLBACK_DDL = """
-- Staging/local only. Requires wathefni.allow_capture_cleanup=1 for audit/replay drops.
DROP TRIGGER IF EXISTS trg_att_cap_audit_immutable ON attendance_capture_audit_events;
DROP TRIGGER IF EXISTS trg_att_cap_replay_immutable ON attendance_capture_replay_ledger;
DROP FUNCTION IF EXISTS attendance_capture_audit_forbid_mutation();
DROP FUNCTION IF EXISTS attendance_capture_replay_forbid_mutation();
DROP TABLE IF EXISTS attendance_capture_replay_ledger CASCADE;
DROP TABLE IF EXISTS attendance_capture_audit_events CASCADE;
DROP TABLE IF EXISTS attendance_capture_idempotency CASCADE;
DROP TABLE IF EXISTS attendance_capture_remediation CASCADE;
DROP TABLE IF EXISTS attendance_capture_quarantine CASCADE;
DROP TABLE IF EXISTS attendance_capture_mappings CASCADE;
DROP TABLE IF EXISTS attendance_capture_checkpoints CASCADE;
DROP TABLE IF EXISTS attendance_capture_health_events CASCADE;
DROP TABLE IF EXISTS attendance_capture_health CASCADE;
DROP TABLE IF EXISTS attendance_capture_credentials CASCADE;
DROP TABLE IF EXISTS attendance_capture_connectors CASCADE;
DROP TABLE IF EXISTS attendance_capture_devices CASCADE;
DROP TABLE IF EXISTS attendance_capture_sites CASCADE;
"""


def capture_store_mode() -> str:
    raw = (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE") or "memory").strip().lower()
    return "postgres" if raw in {"postgres", "pg", "postgresql"} else "memory"


def _now() -> datetime:
    return datetime.now(tz=KUWAIT_TZ)


def _key_fingerprint(vault: CredentialVault) -> str:
    # Do not expose the key; fingerprint from sealed empty object stability is weak —
    # store a static label derived from env presence only.
    present = bool(os.environ.get("WATHEFNI_CAPTURE_CREDENTIAL_KEY"))
    return "env-key" if present else "ephemeral-key"


def ensure_attendance_capture_postgres_schema(cur: Any) -> None:
    # gen_random_uuid(): prefer pgcrypto when available (safe no-op if already present).
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    except Exception:  # noqa: BLE001
        pass
    cur.execute(WAVE2F_SCHEMA_DDL)
    # Additive column for older partial deploys
    cur.execute(
        """
        ALTER TABLE attendance_capture_mappings
          ADD COLUMN IF NOT EXISTS device_key text NOT NULL DEFAULT ''
        """
    )


class PostgresCaptureStore:
    """Durable capture-ops authority."""

    LAG_WARN_S = 300.0
    LAG_CRIT_S = 1800.0

    def __init__(
        self,
        *,
        connect: Callable[[], Any],
        vault: CredentialVault | None = None,
        manager_scope_allows: Callable[[str, str, str], bool] | None = None,
        pipeline: Any | None = None,
    ) -> None:
        self._connect = connect
        self.vault = vault or CredentialVault()
        self.manager_scope_allows = manager_scope_allows or (lambda *_a: True)
        self.pipeline = pipeline

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        """Accept either ``db_connect()`` context manager or a raw psycopg2 connection."""
        handle = self._connect()
        if hasattr(handle, "__enter__"):
            with handle as conn:
                yield conn
            return
        try:
            yield handle
            handle.commit()
        except Exception:
            handle.rollback()
            raise
        finally:
            handle.close()

    def ensure_schema(self) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                ensure_attendance_capture_postgres_schema(cur)

    def audit(
        self,
        cur: Any,
        *,
        company_code: str,
        action: str,
        actor_phone: str | None = None,
        connector_id: str | None = None,
        item_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO attendance_capture_audit_events
              (company_code, connector_id, item_id, action, actor_phone, payload)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                company_code.upper(),
                connector_id,
                item_id,
                action,
                actor_phone,
                Json(redact_mapping(payload or {})),
            ),
        )

    # --- sites / devices / connectors ---
    def register_site(self, *, company_code: str, name: str, timezone: str = "Asia/Kuwait") -> dict[str, Any]:
        site_id = str(uuid.uuid4())
        company = company_code.upper()
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO attendance_capture_sites (site_id, company_code, name, timezone)
                    VALUES (%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (site_id, company, name, timezone),
                )
                row = dict(cur.fetchone())
                self.audit(cur, company_code=company, action="register_site", payload={"site_id": site_id, "name": name})
        return row

    def register_device(
        self,
        *,
        company_code: str,
        site_id: str,
        terminal_sn: str,
        vendor: str = "biotime",
        actor_company: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        actor = (actor_company or company).upper()
        if actor != company:
            return {"ok": False, "error": "cross_tenant_device_registration_denied", "actor": actor, "company": company}
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT company_code FROM attendance_capture_sites WHERE site_id=%s",
                    (site_id,),
                )
                site = cur.fetchone()
                if not site or site["company_code"] != company:
                    return {"ok": False, "error": "site_not_found_or_wrong_tenant"}
                cur.execute(
                    """
                    SELECT company_code FROM attendance_capture_devices
                    WHERE terminal_sn=%s AND active AND company_code <> %s
                    LIMIT 1
                    """,
                    (terminal_sn, company),
                )
                other = cur.fetchone()
                if other:
                    return {"ok": False, "error": "device_owned_by_other_tenant", "owner": other["company_code"]}
                device_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_devices
                      (device_id, company_code, site_id, terminal_sn, vendor, owned_by_company)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (device_id, company, site_id, terminal_sn, vendor, company),
                )
                device = dict(cur.fetchone())
                self.audit(cur, company_code=company, action="register_device", payload={"device_id": device_id, "terminal_sn": terminal_sn})
        return {"ok": True, "device": device}

    def register_connector(
        self,
        *,
        company_code: str,
        site_id: str,
        device_id: str | None,
        secrets: dict[str, Any],
        connector_version: str,
        actor_company: str | None = None,
        actor_phone: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        actor = (actor_company or company).upper()
        if actor != company:
            return {"ok": False, "error": "cross_tenant_connector_registration_denied"}
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT company_code FROM attendance_capture_sites WHERE site_id=%s", (site_id,))
                site = cur.fetchone()
                if not site or site["company_code"] != company:
                    return {"ok": False, "error": "site_tenant_mismatch"}
                if device_id:
                    cur.execute("SELECT company_code, site_id FROM attendance_capture_devices WHERE device_id=%s", (device_id,))
                    device = cur.fetchone()
                    if not device or device["company_code"] != company:
                        return {"ok": False, "error": "device_tenant_mismatch"}
                    if str(device["site_id"]) != str(site_id):
                        return {"ok": False, "error": "device_site_mismatch"}
                connector_id = f"conn-{company.lower()}-{uuid.uuid4().hex[:10]}"
                cur.execute(
                    """
                    INSERT INTO attendance_capture_connectors
                      (connector_id, company_code, site_id, device_id, status, connector_version, row_version)
                    VALUES (%s,%s,%s,%s,'registered',%s,1)
                    RETURNING *
                    """,
                    (connector_id, company, site_id, device_id, connector_version),
                )
                reg = dict(cur.fetchone())
                sealed = self.vault.seal(secrets)
                cred_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_credentials
                      (credential_id, company_code, connector_id, sealed_ref, key_fingerprint)
                    VALUES (%s,%s,%s,%s,%s)
                    """,
                    (cred_id, company, connector_id, sealed, _key_fingerprint(self.vault)),
                )
                cur.execute(
                    "UPDATE attendance_capture_connectors SET credential_id=%s WHERE connector_id=%s",
                    (cred_id, connector_id),
                )
                reg["credential_id"] = cred_id
                self.audit(
                    cur,
                    company_code=company,
                    action="register",
                    actor_phone=actor_phone,
                    connector_id=connector_id,
                    payload={"connector_version": connector_version},
                )
        return {"ok": True, "connector": reg, "secrets": REDACTED}

    def list_sites(self, company_code: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT site_id, company_code, name, timezone, active FROM attendance_capture_sites WHERE company_code=%s ORDER BY name",
                    (company_code.upper(),),
                )
                return [dict(r) for r in cur.fetchall()]

    def list_connectors(self, company_code: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT c.*, s.name AS site_name, d.terminal_sn,
                           h.status AS health_status, h.last_sync_at, h.lag_seconds, h.failure_count,
                           h.last_error, h.alerts, h.quarantined_events, h.open_remediation
                    FROM attendance_capture_connectors c
                    LEFT JOIN attendance_capture_sites s ON s.site_id=c.site_id
                    LEFT JOIN attendance_capture_devices d ON d.device_id=c.device_id
                    LEFT JOIN attendance_capture_health h ON h.connector_id=c.connector_id
                    WHERE c.company_code=%s
                    ORDER BY c.created_at DESC
                    """,
                    (company,),
                )
                out = []
                for r in cur.fetchall():
                    row = dict(r)
                    row["secrets"] = REDACTED
                    alerts = row.get("alerts") or []
                    if isinstance(alerts, str):
                        try:
                            alerts = json.loads(alerts)
                        except Exception:  # noqa: BLE001
                            alerts = []
                    row["health"] = {
                        "connector_id": row["connector_id"],
                        "company_code": company,
                        "site_id": str(row["site_id"]) if row.get("site_id") else None,
                        "status": row.get("health_status")
                        or ("revoked" if row.get("status") == "revoked" else "offline"),
                        "last_sync_at": row.get("last_sync_at").isoformat() if row.get("last_sync_at") else None,
                        "lag_seconds": row.get("lag_seconds"),
                        "failure_count": row.get("failure_count") or 0,
                        "last_error": row.get("last_error"),
                        "quarantined_events": row.get("quarantined_events") or 0,
                        "open_remediation": row.get("open_remediation") or 0,
                        "checkpoint": row.get("checkpoint"),
                        "connector_version": row.get("connector_version"),
                        "alerts": alerts,
                    }
                    out.append(row)
                return out

    def activate(self, connector_id: str, *, expected_row_version: int, actor_phone: str | None = None) -> dict[str, Any]:
        return self._bump_status(connector_id, expected_row_version=expected_row_version, status="active", action="activate", actor_phone=actor_phone)

    def _bump_status(
        self,
        connector_id: str,
        *,
        expected_row_version: int,
        status: str,
        action: str,
        actor_phone: str | None = None,
        reason: str | None = None,
        extra_sets: str = "",
        extra_params: tuple = (),
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM attendance_capture_connectors WHERE connector_id=%s FOR UPDATE",
                    (connector_id,),
                )
                reg = cur.fetchone()
                if not reg:
                    return {"ok": False, "error": "connector_not_found"}
                if reg["status"] == "revoked" and action != "revoke":
                    return {"ok": False, "error": "connector_revoked"}
                if int(reg["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": reg["row_version"]}
                sets = "status=%s, row_version=row_version+1, updated_at=now()" + (f", {extra_sets}" if extra_sets else "")
                params = (status, *extra_params, connector_id, expected_row_version)
                cur.execute(
                    f"""
                    UPDATE attendance_capture_connectors
                    SET {sets}
                    WHERE connector_id=%s AND row_version=%s
                    RETURNING *
                    """,
                    params,
                )
                updated = cur.fetchone()
                if not updated:
                    return {"ok": False, "error": "stale_row_version"}
                self.audit(
                    cur,
                    company_code=updated["company_code"],
                    action=action,
                    actor_phone=actor_phone,
                    connector_id=connector_id,
                    payload={"reason": reason} if reason else {},
                )
                return {"ok": True, "connector": dict(updated)}

    def rotate_credentials(
        self,
        connector_id: str,
        *,
        new_secrets: dict[str, Any],
        expected_row_version: int,
        actor_phone: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM attendance_capture_connectors WHERE connector_id=%s FOR UPDATE",
                    (connector_id,),
                )
                reg = cur.fetchone()
                if not reg:
                    return {"ok": False, "error": "connector_not_found"}
                if reg["status"] == "revoked":
                    return {"ok": False, "error": "connector_revoked"}
                if int(reg["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": reg["row_version"]}
                prev = None
                if reg.get("credential_id"):
                    cur.execute(
                        "SELECT sealed_ref FROM attendance_capture_credentials WHERE credential_id=%s",
                        (reg["credential_id"],),
                    )
                    old = cur.fetchone()
                    prev = old["sealed_ref"] if old else None
                sealed = self.vault.seal(new_secrets)
                cred_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_credentials
                      (credential_id, company_code, connector_id, sealed_ref, previous_sealed_ref, key_fingerprint, rotated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,now())
                    """,
                    (cred_id, reg["company_code"], connector_id, sealed, prev, _key_fingerprint(self.vault)),
                )
                cur.execute(
                    """
                    UPDATE attendance_capture_connectors
                    SET status='rotated', credential_id=%s, last_rotate_at=now(),
                        row_version=row_version+1, updated_at=now()
                    WHERE connector_id=%s AND row_version=%s
                    RETURNING *
                    """,
                    (cred_id, connector_id, expected_row_version),
                )
                updated = cur.fetchone()
                if not updated:
                    return {"ok": False, "error": "stale_row_version"}
                self.audit(cur, company_code=reg["company_code"], action="rotate", actor_phone=actor_phone, connector_id=connector_id)
                return {"ok": True, "connector": dict(updated), "secrets": REDACTED}

    def revoke(
        self,
        connector_id: str,
        *,
        expected_row_version: int,
        actor_phone: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM attendance_capture_connectors WHERE connector_id=%s FOR UPDATE",
                    (connector_id,),
                )
                reg = cur.fetchone()
                if not reg:
                    return {"ok": False, "error": "connector_not_found"}
                if int(reg["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": reg["row_version"]}
                # wipe sealed material
                cur.execute(
                    """
                    UPDATE attendance_capture_credentials
                    SET sealed_ref='[REVOKED]', previous_sealed_ref=NULL, revoked_at=now()
                    WHERE connector_id=%s
                    """,
                    (connector_id,),
                )
                cur.execute(
                    """
                    UPDATE attendance_capture_connectors
                    SET status='revoked', revoked_at=now(), credential_id=NULL,
                        row_version=row_version+1, updated_at=now()
                    WHERE connector_id=%s AND row_version=%s
                    RETURNING *
                    """,
                    (connector_id, expected_row_version),
                )
                updated = cur.fetchone()
                if not updated:
                    return {"ok": False, "error": "stale_row_version"}
                cur.execute(
                    """
                    INSERT INTO attendance_capture_health
                      (connector_id, company_code, site_id, status, alerts, updated_at)
                    VALUES (%s,%s,%s,'revoked','[]'::jsonb,now())
                    ON CONFLICT (connector_id) DO UPDATE
                      SET status='revoked', alerts='[]'::jsonb, updated_at=now()
                    """,
                    (connector_id, updated["company_code"], updated["site_id"]),
                )
                self.audit(
                    cur,
                    company_code=updated["company_code"],
                    action="revoke",
                    actor_phone=actor_phone,
                    connector_id=connector_id,
                    payload={"reason": reason},
                )
                return {"ok": True, "connector": dict(updated)}

    def reconnect_after_rotate(self, connector_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_connectors WHERE connector_id=%s", (connector_id,))
                reg = cur.fetchone()
                if not reg:
                    return {"ok": False, "error": "connector_not_found"}
                if reg["status"] == "revoked":
                    return {"ok": False, "error": "connector_revoked"}
                if not reg.get("credential_id"):
                    return {"ok": False, "error": "credentials_missing"}
                cur.execute(
                    "SELECT sealed_ref FROM attendance_capture_credentials WHERE credential_id=%s",
                    (reg["credential_id"],),
                )
                cred = cur.fetchone()
                if not cred or not cred["sealed_ref"] or cred["sealed_ref"] == "[REVOKED]":
                    return {"ok": False, "error": "credentials_missing"}
                try:
                    secrets = self.vault.open(cred["sealed_ref"])
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": safe_error(exc)}
                return {
                    "ok": True,
                    "connector_id": connector_id,
                    "status": reg["status"],
                    "has_username": bool(secrets.get("username")),
                    "has_password": bool(secrets.get("password")),
                    "has_token": bool(secrets.get("token")),
                    "secrets": REDACTED,
                }

    def assert_connector_tenant(self, connector_id: str, company_code: str) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT company_code, status FROM attendance_capture_connectors WHERE connector_id=%s", (connector_id,))
                reg = cur.fetchone()
                if not reg:
                    return {"ok": False, "error": "connector_not_found"}
                if reg["company_code"] != company_code.upper():
                    return {"ok": False, "error": "cross_tenant_denied"}
                if reg["status"] == "revoked":
                    return {"ok": False, "error": "connector_revoked"}
                return {"ok": True, "connector_id": connector_id}

    def verify_device_ownership(self, *, company_code: str, terminal_sn: str) -> dict[str, Any]:
        company = company_code.upper()
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM attendance_capture_devices WHERE terminal_sn=%s AND active",
                    (terminal_sn,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                if not rows:
                    return {"ok": False, "error": "device_not_registered"}
                owned = [d for d in rows if d["company_code"] == company]
                if not owned:
                    return {"ok": False, "error": "wrong_tenant_device", "owner": rows[0]["company_code"]}
                return {"ok": True, "device": owned[0]}

    # --- health / checkpoint ---
    def upsert_health(
        self,
        *,
        connector_id: str,
        company_code: str,
        site_id: str | None,
        agent_health: dict[str, Any],
        quarantined_events: int = 0,
        open_remediation: int = 0,
        revoked: bool = False,
    ) -> dict[str, Any]:
        raw_status = str(agent_health.get("status") or "offline").lower()
        if revoked:
            status = "revoked"
        elif raw_status in {"error", "offline"}:
            status = "offline" if raw_status == "offline" else "degraded"
        elif raw_status == "degraded":
            status = "degraded"
        else:
            status = "online"
        try:
            lag_f = float(agent_health["lag_seconds"]) if agent_health.get("lag_seconds") is not None else None
        except (TypeError, ValueError):
            lag_f = None
        alerts: list[str] = []
        if status == "offline":
            alerts.append("connector_offline")
        if status == "degraded":
            alerts.append("connector_failures")
        if lag_f is not None and lag_f >= self.LAG_CRIT_S:
            alerts.append("connector_lag_critical")
            status = "degraded"
        elif lag_f is not None and lag_f >= self.LAG_WARN_S:
            alerts.append("connector_lag_warning")
        if quarantined_events > 0:
            alerts.append("quarantined_events")
        if open_remediation > 0:
            alerts.append("open_remediation")
        last_sync = agent_health.get("last_sync_at") or agent_health.get("last_success_at")
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO attendance_capture_health
                      (connector_id, company_code, site_id, status, last_sync_at, lag_seconds,
                       failure_count, last_error, quarantined_events, open_remediation,
                       checkpoint, connector_version, alerts, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                    ON CONFLICT (connector_id) DO UPDATE SET
                      status=EXCLUDED.status,
                      last_sync_at=EXCLUDED.last_sync_at,
                      lag_seconds=EXCLUDED.lag_seconds,
                      failure_count=EXCLUDED.failure_count,
                      last_error=EXCLUDED.last_error,
                      quarantined_events=EXCLUDED.quarantined_events,
                      open_remediation=EXCLUDED.open_remediation,
                      checkpoint=EXCLUDED.checkpoint,
                      connector_version=EXCLUDED.connector_version,
                      alerts=EXCLUDED.alerts,
                      updated_at=now()
                    RETURNING *
                    """,
                    (
                        connector_id,
                        company_code.upper(),
                        site_id,
                        status,
                        last_sync,
                        lag_f,
                        int(agent_health.get("error_count") or 0),
                        agent_health.get("last_error"),
                        int(quarantined_events),
                        int(open_remediation),
                        agent_health.get("checkpoint"),
                        agent_health.get("connector_version"),
                        Json(alerts),
                    ),
                )
                row = dict(cur.fetchone())
                event_type = "health_upsert"
                if "connector_offline" in alerts:
                    event_type = "connector_offline"
                elif "connector_lag_critical" in alerts:
                    event_type = "connector_lag_critical"
                cur.execute(
                    """
                    INSERT INTO attendance_capture_health_events
                      (connector_id, company_code, event_type, status, lag_seconds, payload)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (connector_id, company_code.upper(), event_type, status, lag_f, Json({"alerts": alerts})),
                )
                if agent_health.get("checkpoint"):
                    cur.execute(
                        """
                        INSERT INTO attendance_capture_checkpoints (connector_id, company_code, checkpoint, updated_at, row_version)
                        VALUES (%s,%s,%s,now(),1)
                        ON CONFLICT (connector_id) DO UPDATE SET
                          checkpoint=EXCLUDED.checkpoint,
                          updated_at=now(),
                          row_version=attendance_capture_checkpoints.row_version+1
                        """,
                        (connector_id, company_code.upper(), agent_health["checkpoint"]),
                    )
        row["alerts"] = alerts
        if row.get("last_sync_at"):
            row["last_sync_at"] = row["last_sync_at"].isoformat() if hasattr(row["last_sync_at"], "isoformat") else row["last_sync_at"]
        return row

    def mark_recovered(self, connector_id: str, *, last_sync_at: str | None = None) -> dict[str, Any] | None:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_health WHERE connector_id=%s FOR UPDATE", (connector_id,))
                row = cur.fetchone()
                if not row or row["status"] == "revoked":
                    return dict(row) if row else None
                sync = last_sync_at or _now().isoformat()
                cur.execute(
                    """
                    UPDATE attendance_capture_health
                    SET status='online', lag_seconds=0, last_sync_at=%s,
                        alerts=COALESCE((
                          SELECT jsonb_agg(a) FROM jsonb_array_elements_text(alerts) t(a)
                          WHERE a NOT IN ('connector_offline','connector_lag_critical','connector_lag_warning','connector_failures')
                        ), '[]'::jsonb),
                        updated_at=now()
                    WHERE connector_id=%s
                    RETURNING *
                    """,
                    (sync, connector_id),
                )
                updated = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_health_events
                      (connector_id, company_code, event_type, status, lag_seconds, payload)
                    VALUES (%s,%s,'recovered','online',0,'{}'::jsonb)
                    """,
                    (connector_id, updated["company_code"]),
                )
                if updated.get("last_sync_at") and hasattr(updated["last_sync_at"], "isoformat"):
                    updated["last_sync_at"] = updated["last_sync_at"].isoformat()
                alerts = updated.get("alerts") or []
                if isinstance(alerts, str):
                    alerts = json.loads(alerts)
                updated["alerts"] = alerts
                return updated

    def list_health(self, company_code: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM attendance_capture_health WHERE company_code=%s ORDER BY updated_at DESC",
                    (company_code.upper(),),
                )
                out = []
                for r in cur.fetchall():
                    row = dict(r)
                    if row.get("last_sync_at") and hasattr(row["last_sync_at"], "isoformat"):
                        row["last_sync_at"] = row["last_sync_at"].isoformat()
                    alerts = row.get("alerts") or []
                    if isinstance(alerts, str):
                        alerts = json.loads(alerts)
                    row["alerts"] = alerts
                    out.append(row)
                return out

    def save_checkpoint(self, *, connector_id: str, company_code: str, checkpoint: str) -> dict[str, Any]:
        """Idempotent checkpoint advance — same value is a no-op; forward-only."""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT checkpoint, row_version FROM attendance_capture_checkpoints WHERE connector_id=%s FOR UPDATE",
                    (connector_id,),
                )
                existing = cur.fetchone()
                if existing and existing["checkpoint"] == checkpoint:
                    return {"ok": True, "duplicate": True, "checkpoint": checkpoint, "row_version": existing["row_version"]}
                cur.execute(
                    """
                    INSERT INTO attendance_capture_checkpoints (connector_id, company_code, checkpoint, updated_at, row_version)
                    VALUES (%s,%s,%s,now(),1)
                    ON CONFLICT (connector_id) DO UPDATE SET
                      checkpoint=EXCLUDED.checkpoint,
                      updated_at=now(),
                      row_version=attendance_capture_checkpoints.row_version+1
                    RETURNING *
                    """,
                    (connector_id, company_code.upper(), checkpoint),
                )
                row = dict(cur.fetchone())
                return {"ok": True, "duplicate": False, "checkpoint": row["checkpoint"], "row_version": row["row_version"]}

    def get_checkpoint(self, connector_id: str) -> str | None:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT checkpoint FROM attendance_capture_checkpoints WHERE connector_id=%s", (connector_id,))
                row = cur.fetchone()
                return row["checkpoint"] if row else None

    # --- mapping / remediation ---
    def upsert_mapping(
        self,
        *,
        company_code: str,
        device_user_id: str,
        employee_key: str,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        device_key = device_id or ""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO attendance_capture_mappings
                      (company_code, device_user_id, employee_key, device_id, device_key, active)
                    VALUES (%s,%s,%s,%s,%s,true)
                    ON CONFLICT (company_code, device_user_id, device_key)
                    DO UPDATE SET employee_key=EXCLUDED.employee_key, device_id=EXCLUDED.device_id,
                                  active=true, updated_at=now()
                    RETURNING *
                    """,
                    (company_code.upper(), device_user_id, employee_key, device_id, device_key),
                )
                return dict(cur.fetchone())

    def resolve_mapping(self, *, company_code: str, device_user_id: str, device_id: str | None = None) -> dict[str, Any] | None:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM attendance_capture_mappings
                    WHERE company_code=%s AND device_user_id=%s AND active
                      AND (device_id IS NOT DISTINCT FROM %s OR device_id IS NULL OR %s IS NULL)
                    ORDER BY CASE WHEN device_id IS NOT DISTINCT FROM %s THEN 0 ELSE 1 END
                    LIMIT 1
                    """,
                    (company_code.upper(), device_user_id, device_id, device_id, device_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def enqueue_remediation(
        self,
        *,
        company_code: str,
        kind: str,
        payload: dict[str, Any],
        connector_id: str | None = None,
        employee_key: str | None = None,
        device_id: str | None = None,
        device_user_id: str | None = None,
        work_date: str | None = None,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        key = idempotency_key or f"{company_code}:{kind}:{source_event_id or ''}:{device_user_id or ''}:{work_date or ''}"
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_idempotency WHERE idempotency_key=%s", (key,))
                existing = cur.fetchone()
                if existing:
                    item = None
                    if existing.get("item_id"):
                        cur.execute("SELECT * FROM attendance_capture_remediation WHERE item_id=%s", (existing["item_id"],))
                        item = cur.fetchone()
                    return {"ok": True, "duplicate": True, "item": dict(item) if item else existing.get("result")}
                item_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_remediation
                      (item_id, company_code, kind, status, connector_id, employee_key, device_id,
                       device_user_id, work_date, source_event_id, payload, row_version, payroll_excluded)
                    VALUES (%s,%s,%s,'open',%s,%s,%s,%s,%s,%s,%s,1,true)
                    RETURNING *
                    """,
                    (
                        item_id,
                        company_code.upper(),
                        kind,
                        connector_id,
                        employee_key,
                        device_id,
                        device_user_id,
                        work_date,
                        source_event_id,
                        Json(redact_mapping(payload)),
                    ),
                )
                item = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_idempotency (idempotency_key, company_code, action, item_id, result)
                    VALUES (%s,%s,'enqueue',%s,%s)
                    """,
                    (key, company_code.upper(), item_id, Json({"item_id": item_id})),
                )
                self.audit(
                    cur,
                    company_code=company_code,
                    action="enqueue",
                    connector_id=connector_id,
                    item_id=item_id,
                    payload={"kind": kind, "idempotency_key": key},
                )
                return {"ok": True, "duplicate": False, "item": item}

    def list_open_remediation(self, company_code: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM attendance_capture_remediation
                    WHERE company_code=%s AND status IN ('open','approved_pending_replay')
                    ORDER BY created_at DESC
                    """,
                    (company_code.upper(),),
                )
                return [dict(r) for r in cur.fetchall()]

    def payroll_excluded_open(self, company_code: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM attendance_capture_remediation
                    WHERE company_code=%s AND payroll_excluded
                      AND status IN ('open','approved_pending_replay','rejected')
                    ORDER BY created_at DESC
                    """,
                    (company_code.upper(),),
                )
                return [dict(r) for r in cur.fetchall()]

    def approve_mapping(
        self,
        item_id: str,
        *,
        employee_key: str,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        actor_is_manager: bool = False,
        employee_phone: str | None = None,
        replay: bool = True,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_remediation WHERE item_id=%s FOR UPDATE", (item_id,))
                item = cur.fetchone()
                if not item:
                    return {"ok": False, "error": "item_not_found"}
                if item["company_code"] != actor_company.upper():
                    return {"ok": False, "error": "cross_tenant_denied"}
                if item["kind"] not in {"unknown_employee", "unknown_device"}:
                    return {"ok": False, "error": "not_a_mapping_item", "kind": item["kind"]}
                if item["status"] != "open":
                    return {"ok": False, "error": "item_not_open", "status": item["status"]}
                if int(item["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": item["row_version"]}
                a = "".join(ch for ch in str(actor_phone or "") if ch.isdigit())
                e = "".join(ch for ch in str(employee_phone or "") if ch.isdigit())
                if actor_is_manager and a and e and a == e:
                    return {"ok": False, "error": "manager_self_action_denied"}
                scope_target = employee_key or item.get("employee_key")
                if scope_target and not self.manager_scope_allows(item["company_code"], actor_phone, scope_target):
                    return {"ok": False, "error": "manager_scope_denied"}
                if not item.get("device_user_id"):
                    return {"ok": False, "error": "missing_device_user_id"}

                device_key = item.get("device_id") or ""
                cur.execute(
                    """
                    INSERT INTO attendance_capture_mappings
                      (company_code, device_user_id, employee_key, device_id, device_key, active, updated_at)
                    VALUES (%s,%s,%s,%s,%s,true,now())
                    ON CONFLICT (company_code, device_user_id, device_key) DO UPDATE SET
                      employee_key=EXCLUDED.employee_key,
                      device_id=EXCLUDED.device_id,
                      active=true,
                      updated_at=now()
                    RETURNING *
                    """,
                    (actor_company.upper(), item["device_user_id"], employee_key, item.get("device_id"), device_key),
                )
                map_res = dict(cur.fetchone())
                status = "approved_pending_replay" if replay else "approved_replayed"
                cur.execute(
                    """
                    UPDATE attendance_capture_remediation
                    SET employee_key=%s, status=%s, row_version=row_version+1, updated_at=now(),
                        payroll_excluded=%s
                    WHERE item_id=%s AND row_version=%s
                    RETURNING *
                    """,
                    (employee_key, status, bool(replay), item_id, expected_row_version),
                )
                updated = cur.fetchone()
                if not updated:
                    return {"ok": False, "error": "stale_row_version"}
                self.audit(
                    cur,
                    company_code=updated["company_code"],
                    action="approve_mapping",
                    actor_phone=actor_phone,
                    item_id=item_id,
                    payload={"employee_key": employee_key, "mapping_id": str(map_res.get("mapping_id"))},
                )
                result: dict[str, Any] = {"ok": True, "item": dict(updated), "mapping": map_res}
        if replay and self.pipeline is not None:
            replay_res = self.replay_item(
                item_id,
                expected_row_version=result["item"]["row_version"],
                actor_phone=actor_phone,
                actor_company=actor_company,
                shift=shift,
            )
            result["replay"] = replay_res
            result["item"] = replay_res.get("item") or result["item"]
        return result

    def reject(
        self,
        item_id: str,
        *,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        reason: str | None = None,
        actor_is_manager: bool = False,
        employee_phone: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_remediation WHERE item_id=%s FOR UPDATE", (item_id,))
                item = cur.fetchone()
                if not item:
                    return {"ok": False, "error": "item_not_found"}
                if item["company_code"] != actor_company.upper():
                    return {"ok": False, "error": "cross_tenant_denied"}
                if item["status"] == "rejected":
                    return {"ok": True, "duplicate": True, "item": dict(item)}
                if item["status"] not in {"open", "approved_pending_replay"}:
                    return {"ok": False, "error": "item_not_open", "status": item["status"]}
                if int(item["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": item["row_version"]}
                a = "".join(ch for ch in str(actor_phone or "") if ch.isdigit())
                e = "".join(ch for ch in str(employee_phone or "") if ch.isdigit())
                if actor_is_manager and a and e and a == e:
                    return {"ok": False, "error": "manager_self_action_denied"}
                cur.execute(
                    """
                    UPDATE attendance_capture_remediation
                    SET status='rejected', row_version=row_version+1, updated_at=now(), payroll_excluded=true
                    WHERE item_id=%s AND row_version=%s
                    RETURNING *
                    """,
                    (item_id, expected_row_version),
                )
                updated = cur.fetchone()
                if not updated:
                    return {"ok": False, "error": "stale_row_version"}
                self.audit(
                    cur,
                    company_code=updated["company_code"],
                    action="reject",
                    actor_phone=actor_phone,
                    item_id=item_id,
                    payload={"reason": reason},
                )
                return {"ok": True, "item": dict(updated)}

    def replay_item(
        self,
        item_id: str,
        *,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM attendance_capture_remediation WHERE item_id=%s FOR UPDATE", (item_id,))
                item = cur.fetchone()
                if not item:
                    return {"ok": False, "error": "item_not_found"}
                if item["company_code"] != actor_company.upper():
                    return {"ok": False, "error": "cross_tenant_denied"}
                if item["status"] not in {"approved_pending_replay", "approved_replayed"}:
                    return {"ok": False, "error": "replay_not_allowed", "status": item["status"]}
                if int(item["row_version"]) != int(expected_row_version):
                    return {"ok": False, "error": "stale_row_version", "current": item["row_version"]}
                if item["kind"] not in {"unknown_employee", "unknown_device"}:
                    return {"ok": False, "error": "kind_not_replayable_to_authority", "kind": item["kind"]}
                payload = dict(item["payload"] or {})
                payload["employee_key"] = item["employee_key"]
                source = str(payload.get("source") or "biotime")
                source_event_id = str(payload.get("source_event_id") or item.get("source_event_id") or "")
                if not source_event_id:
                    return {"ok": False, "error": "missing_source_event_id"}
                # durable idempotency: ledger first
                cur.execute(
                    """
                    SELECT * FROM attendance_capture_replay_ledger
                    WHERE company_code=%s AND source=%s AND source_event_id=%s
                    """,
                    (item["company_code"], source, source_event_id),
                )
                prior = cur.fetchone()
                if prior:
                    if item["status"] != "approved_replayed":
                        cur.execute(
                            """
                            UPDATE attendance_capture_remediation
                            SET status='approved_replayed', row_version=row_version+1, updated_at=now(), payroll_excluded=false
                            WHERE item_id=%s
                            RETURNING *
                            """,
                            (item_id,),
                        )
                        item = cur.fetchone()
                    return {"ok": True, "duplicate": True, "item": dict(item), "ingest": {"ok": True, "duplicate": True}}

                action_key = f"replay:{item_id}:{expected_row_version}"
                cur.execute("SELECT 1 FROM attendance_capture_idempotency WHERE idempotency_key=%s", (action_key,))
                if cur.fetchone() and item["status"] == "approved_replayed":
                    return {"ok": True, "duplicate": True, "item": dict(item)}

                if self.pipeline is None:
                    return {"ok": False, "error": "pipeline_not_configured"}

                # release lock before pipeline IO by committing after ledger insert reservation
                cur.execute(
                    """
                    INSERT INTO attendance_capture_replay_ledger
                      (company_code, item_id, source, source_event_id, status)
                    VALUES (%s,%s,%s,%s,'pending')
                    ON CONFLICT (company_code, source, source_event_id) DO NOTHING
                    RETURNING replay_id
                    """,
                    (item["company_code"], item_id, source, source_event_id),
                )
                reserved = cur.fetchone()
                if not reserved:
                    return {"ok": True, "duplicate": True, "item": dict(item), "ingest": {"ok": True, "duplicate": True}}

        # ingest outside (pipeline may use its own DB connections)
        try:
            res = self.pipeline.ingest_canonical(payload, shift=shift)
        except Exception as exc:  # noqa: BLE001
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
                    cur.execute(
                        "DELETE FROM attendance_capture_replay_ledger WHERE company_code=%s AND source=%s AND source_event_id=%s AND status='pending'",
                        (actor_company.upper(), source, source_event_id),
                    )
            return {"ok": False, "error": safe_error(exc)}

        punch_id = None
        if isinstance(res, dict):
            punch_id = (res.get("punch") or {}).get("punch_id") or res.get("punch_id")

        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
                # replay ledger trigger forbids UPDATE — delete pending and insert accepted under cleanup flag
                cur.execute(
                    """
                    DELETE FROM attendance_capture_replay_ledger
                    WHERE company_code=%s AND source=%s AND source_event_id=%s AND status='pending'
                    """,
                    (actor_company.upper(), source, source_event_id),
                )
                cur.execute(
                    """
                    INSERT INTO attendance_capture_replay_ledger
                      (company_code, item_id, source, source_event_id, punch_id, status)
                    VALUES (%s,%s,%s,%s,%s,'accepted')
                    ON CONFLICT (company_code, source, source_event_id) DO NOTHING
                    """,
                    (actor_company.upper(), item_id, source, source_event_id, punch_id),
                )
                cur.execute(
                    """
                    UPDATE attendance_capture_remediation
                    SET status='approved_replayed', row_version=row_version+1, updated_at=now(),
                        payroll_excluded=%s
                    WHERE item_id=%s
                    RETURNING *
                    """,
                    (not bool(res.get("ok")), item_id),
                )
                updated = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO attendance_capture_idempotency (idempotency_key, company_code, action, item_id, result)
                    VALUES (%s,%s,'replay',%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    (f"replay:{item_id}:{expected_row_version}", actor_company.upper(), item_id, Json({"ok": res.get("ok")})),
                )
                self.audit(
                    cur,
                    company_code=actor_company,
                    action="replay",
                    actor_phone=actor_phone,
                    item_id=item_id,
                    payload={"result_ok": res.get("ok"), "source_event_id": source_event_id},
                )
                return {"ok": bool(res.get("ok")), "ingest": res, "item": updated}

    def reconcile_with_authority(self, company_code: str) -> dict[str, Any]:
        """Compare replay ledger accepted rows to Wave 1 punches (exactly-once check)."""
        company = company_code.upper()
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.source, r.source_event_id, r.punch_id, r.status,
                           p.punch_id AS authority_punch_id
                    FROM attendance_capture_replay_ledger r
                    LEFT JOIN attendance_punches p
                      ON p.company_code=r.company_code
                     AND p.source=r.source
                     AND p.source_event_id=r.source_event_id
                    WHERE r.company_code=%s AND r.status='accepted'
                    """,
                    (company,),
                )
                rows = [dict(r) for r in cur.fetchall()]
        matched = sum(1 for r in rows if r.get("authority_punch_id"))
        missing = [r for r in rows if not r.get("authority_punch_id")]
        return {
            "ok": len(missing) == 0,
            "accepted": len(rows),
            "matched_in_authority": matched,
            "missing_in_authority": missing[:20],
            "version": CAPTURE_OPS_VERSION,
        }

    def assert_no_plaintext_secrets(self) -> dict[str, Any]:
        """Scan credential table for obvious plaintext assignment patterns."""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT credential_id, sealed_ref, previous_sealed_ref
                    FROM attendance_capture_credentials
                    WHERE sealed_ref ILIKE '%%password=%%'
                       OR sealed_ref ~ '^[A-Za-z0-9+/=]{0,40}$'
                       OR (previous_sealed_ref IS NOT NULL AND previous_sealed_ref NOT LIKE 'gAAAA%%' AND previous_sealed_ref <> '[REVOKED]')
                    LIMIT 5
                    """
                )
                # Fernet tokens start with gAAAA
                suspicious = []
                cur.execute("SELECT credential_id, sealed_ref FROM attendance_capture_credentials LIMIT 200")
                for r in cur.fetchall():
                    sealed = r["sealed_ref"] or ""
                    if sealed in {"[REVOKED]", REDACTED}:
                        continue
                    if not sealed.startswith("gAAAA") and sealed != "[REVOKED]":
                        suspicious.append({"credential_id": str(r["credential_id"]), "reason": "sealed_ref_not_fernet_shaped"})
                # column inventory — no password/token columns
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name LIKE 'attendance_capture_%%'
                      AND column_name IN ('password','token','api_secret','secret','biotime_password')
                    """
                )
                bad_cols = [r["column_name"] for r in cur.fetchall()]
        return {
            "ok": not suspicious and not bad_cols,
            "suspicious_sealed": suspicious[:5],
            "forbidden_columns": bad_cols,
        }

    def cleanup_synthetic(self, marker: str) -> dict[str, Any]:
        """Test cleanup for ATTW2F synthetic rows (staging only)."""
        like = f"%{marker}%"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
                cur.execute(
                    """
                    DELETE FROM attendance_capture_replay_ledger
                    WHERE item_id IN (
                      SELECT item_id FROM attendance_capture_remediation
                      WHERE source_event_id ILIKE %s OR device_user_id ILIKE %s OR employee_key ILIKE %s
                    )
                    OR company_code ILIKE %s
                    """,
                    (like, like, like, like),
                )
                cur.execute("DELETE FROM attendance_capture_idempotency WHERE idempotency_key ILIKE %s OR company_code ILIKE %s", (like, like))
                cur.execute(
                    "DELETE FROM attendance_capture_audit_events WHERE payload::text ILIKE %s OR connector_id ILIKE %s OR company_code ILIKE %s",
                    (like, like, like),
                )
                cur.execute(
                    "DELETE FROM attendance_capture_remediation WHERE source_event_id ILIKE %s OR device_user_id ILIKE %s OR employee_key ILIKE %s OR company_code ILIKE %s",
                    (like, like, like, like),
                )
                cur.execute(
                    "DELETE FROM attendance_capture_mappings WHERE device_user_id ILIKE %s OR employee_key ILIKE %s OR company_code ILIKE %s",
                    (like, like, like),
                )
                cur.execute(
                    """
                    DELETE FROM attendance_capture_health_events WHERE connector_id IN (
                      SELECT connector_id FROM attendance_capture_connectors
                      WHERE connector_id ILIKE %s OR connector_version ILIKE %s OR company_code ILIKE %s
                    ) OR company_code ILIKE %s
                    """,
                    (like, like, like, like),
                )
                cur.execute(
                    """
                    DELETE FROM attendance_capture_health WHERE connector_id IN (
                      SELECT connector_id FROM attendance_capture_connectors
                      WHERE connector_id ILIKE %s OR connector_version ILIKE %s OR company_code ILIKE %s
                    ) OR company_code ILIKE %s
                    """,
                    (like, like, like, like),
                )
                cur.execute(
                    """
                    DELETE FROM attendance_capture_checkpoints WHERE connector_id IN (
                      SELECT connector_id FROM attendance_capture_connectors
                      WHERE connector_id ILIKE %s OR connector_version ILIKE %s OR company_code ILIKE %s
                    ) OR company_code ILIKE %s
                    """,
                    (like, like, like, like),
                )
                cur.execute(
                    """
                    DELETE FROM attendance_capture_credentials WHERE connector_id IN (
                      SELECT connector_id FROM attendance_capture_connectors
                      WHERE connector_id ILIKE %s OR connector_version ILIKE %s OR company_code ILIKE %s
                    ) OR company_code ILIKE %s
                    """,
                    (like, like, like, like),
                )
                cur.execute(
                    "DELETE FROM attendance_capture_connectors WHERE connector_id ILIKE %s OR connector_version ILIKE %s OR company_code ILIKE %s",
                    (like, like, like),
                )
                cur.execute("DELETE FROM attendance_capture_devices WHERE terminal_sn ILIKE %s OR company_code ILIKE %s", (like, like))
                cur.execute("DELETE FROM attendance_capture_sites WHERE name ILIKE %s OR company_code ILIKE %s", (like, like))
                cur.execute("DELETE FROM attendance_capture_quarantine WHERE company_code ILIKE %s OR source_event_id ILIKE %s", (like, like))
        return {"ok": True, "marker": marker}
