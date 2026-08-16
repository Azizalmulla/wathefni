#!/usr/bin/env python3
"""Attendance Wave 1B — PostgreSQL persistence adapter for authority engine.

Durable punches, versioned projections, corrections, payroll snapshots, audit
events, and compat-drift quarantine. Used when
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres (default when authority is on in
staging/local with a DB). Never silently overwrites conflicting legacy rows.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterator

from psycopg2.extras import Json

import attendance_authority_wave1 as core

AUTHORITY_VERSION = core.AUTHORITY_VERSION
KUWAIT_TZ = core.KUWAIT_TZ

WAVE1B_SCHEMA_DDL = """
-- Wave 1B additive tables / guards (base tables from WAVE1 SCHEMA_DDL).
CREATE TABLE IF NOT EXISTS attendance_authority_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  work_date date,
  shift_key text NOT NULL DEFAULT '',
  punch_id uuid,
  projection_id uuid,
  correction_id uuid,
  snapshot_id uuid,
  event_type text NOT NULL,
  source text,
  source_event_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_auth_events_company
  ON attendance_authority_events(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_att_auth_events_emp_day
  ON attendance_authority_events(company_code, employee_key, work_date);

CREATE TABLE IF NOT EXISTS attendance_compat_drift (
  drift_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  work_date date NOT NULL,
  shift_key text NOT NULL DEFAULT '',
  projection_id uuid,
  attendance_id uuid,
  drift_kind text NOT NULL,
  status text NOT NULL DEFAULT 'quarantined',
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by_phone text
);
CREATE INDEX IF NOT EXISTS idx_att_compat_drift_open
  ON attendance_compat_drift(company_code, status, created_at DESC);

CREATE OR REPLACE FUNCTION attendance_payroll_snapshots_forbid_mutation()
RETURNS trigger AS $$
BEGIN
  -- Synthetic/test cleanup may set wathefni.allow_authority_cleanup=1
  IF current_setting('wathefni.allow_authority_cleanup', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'attendance_payroll_snapshots are immutable (Wave 1B)';
  END IF;
  IF NEW.payload IS DISTINCT FROM OLD.payload
     OR NEW.projection_id IS DISTINCT FROM OLD.projection_id
     OR NEW.projection_version IS DISTINCT FROM OLD.projection_version
     OR NEW.worked_minutes_cache IS DISTINCT FROM OLD.worked_minutes_cache THEN
    RAISE EXCEPTION 'attendance_payroll_snapshots payload is immutable (Wave 1B)';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION attendance_punches_forbid_mutation()
RETURNS trigger AS $$
BEGIN
  IF current_setting('wathefni.allow_authority_cleanup', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'attendance_punches are append-only (Wave 1B)';
END;
$$ LANGUAGE plpgsql;

-- Optional cache column for reconcile (nullable additive).
ALTER TABLE attendance_payroll_snapshots
  ADD COLUMN IF NOT EXISTS worked_minutes_cache integer;

DROP TRIGGER IF EXISTS trg_attendance_punches_immutable ON attendance_punches;
CREATE TRIGGER trg_attendance_punches_immutable
  BEFORE UPDATE OR DELETE ON attendance_punches
  FOR EACH ROW EXECUTE FUNCTION attendance_punches_forbid_mutation();

DROP TRIGGER IF EXISTS trg_attendance_payroll_snapshots_immutable ON attendance_payroll_snapshots;
CREATE TRIGGER trg_attendance_payroll_snapshots_immutable
  BEFORE UPDATE OR DELETE ON attendance_payroll_snapshots
  FOR EACH ROW EXECUTE FUNCTION attendance_payroll_snapshots_forbid_mutation();
"""

# Rollback drops Wave 1B objects only when no non-synthetic residual exists
# (enforced by the rollback script, not blindly here).
WAVE1B_ROLLBACK_DDL = """
DROP TRIGGER IF EXISTS trg_attendance_payroll_snapshots_immutable ON attendance_payroll_snapshots;
DROP TRIGGER IF EXISTS trg_attendance_punches_immutable ON attendance_punches;
DROP FUNCTION IF EXISTS attendance_payroll_snapshots_forbid_mutation();
DROP FUNCTION IF EXISTS attendance_punches_forbid_mutation();
DROP TABLE IF EXISTS attendance_compat_drift;
DROP TABLE IF EXISTS attendance_authority_events;
-- Base Wave 1 tables retained unless ROLLBACK_DROP_BASE=1 is set by script.
"""


def authority_store_mode() -> str:
    """memory | postgres. Default postgres when authority enabled, else memory."""
    raw = (os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_STORE") or "").strip().lower()
    if raw in {"memory", "mem", "inmemory", "in-memory"}:
        return "memory"
    if raw in {"postgres", "pg", "postgresql", "db"}:
        return "postgres"
    if core.attendance_authority_enabled():
        return "postgres"
    return "memory"


def ensure_attendance_authority_postgres_schema(cur: Any) -> None:
    core.ensure_attendance_authority_schema(cur)
    cur.execute(WAVE1B_SCHEMA_DDL)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _as_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _advisory_keys(company: str, employee_key: str, work_date: date, shift_key: str) -> tuple[int, int]:
    digest = hashlib.sha256(f"{company}|{employee_key}|{work_date.isoformat()}|{shift_key}".encode()).digest()
    k1 = int.from_bytes(digest[:4], "big", signed=True)
    k2 = int.from_bytes(digest[4:8], "big", signed=True)
    return k1, k2


class PostgresAuthorityStore:
    """Durable store matching InMemoryAuthorityStore interface + day locking."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        self._local = threading.local()

    def _get_cur(self) -> Any | None:
        return getattr(self._local, "cur", None)

    @contextmanager
    def employee_day_transaction(
        self,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str = "",
    ) -> Iterator[Any]:
        existing = self._get_cur()
        if existing is not None:
            # Nested: already locked by outer transaction.
            yield existing
            return
        company = company_code.upper()
        skey = core.shift_key_of(shift_key)
        k1, k2 = _advisory_keys(company, employee_key, work_date, skey)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (k1, k2))
                self._local.cur = cur
                self._local.conn = conn
                try:
                    yield cur
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    self._local.cur = None
                    self._local.conn = None

    @contextmanager
    def _op(self) -> Iterator[Any]:
        existing = self._get_cur()
        if existing is not None:
            yield existing
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._local.cur = cur
                try:
                    yield cur
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    self._local.cur = None

    def record_event(
        self,
        *,
        company_code: str,
        event_type: str,
        employee_key: str | None = None,
        work_date: date | None = None,
        shift_key: str = "",
        punch_id: str | None = None,
        projection_id: str | None = None,
        correction_id: str | None = None,
        snapshot_id: str | None = None,
        source: str | None = None,
        source_event_id: str | None = None,
        payload: dict[str, Any] | None = None,
        created_by_phone: str | None = None,
    ) -> None:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_authority_events (
                  company_code, employee_key, work_date, shift_key,
                  punch_id, projection_id, correction_id, snapshot_id,
                  event_type, source, source_event_id, payload, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    company_code.upper(),
                    employee_key,
                    work_date,
                    core.shift_key_of(shift_key),
                    punch_id,
                    projection_id,
                    correction_id,
                    snapshot_id,
                    event_type,
                    source,
                    source_event_id,
                    Json(_json_safe(payload or {})),
                    core.digits(created_by_phone),
                ),
            )

    def append_punch(self, punch: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        company = str(punch["company_code"]).upper()
        source = str(punch["source"])
        source_event_id = str(punch["source_event_id"])
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_punches (
                  company_code, employee_key, employee_phone, employee_name,
                  punched_at, direction, source, source_event_id,
                  shift_id, shift_key, work_date, break_paid, metadata, created_by_phone
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (company_code, source, source_event_id) DO NOTHING
                RETURNING *
                """,
                (
                    company,
                    punch.get("employee_key"),
                    punch.get("employee_phone"),
                    punch.get("employee_name"),
                    punch["punched_at"],
                    punch["direction"],
                    source,
                    source_event_id,
                    punch.get("shift_id") or None,
                    core.shift_key_of(punch.get("shift_key")),
                    punch["work_date"],
                    punch.get("break_paid"),
                    Json(_json_safe(punch.get("metadata") or {})),
                    punch.get("created_by_phone"),
                ),
            )
            row = cur.fetchone()
            if row:
                created = True
                out = _as_dict(row)
            else:
                created = False
                cur.execute(
                    """
                    SELECT * FROM attendance_punches
                    WHERE company_code=%s AND source=%s AND source_event_id=%s
                    LIMIT 1
                    """,
                    (company, source, source_event_id),
                )
                out = _as_dict(cur.fetchone())
            assert out is not None
            cur.execute(
                """
                INSERT INTO attendance_authority_events (
                  company_code, employee_key, work_date, shift_key, punch_id,
                  event_type, source, source_event_id, payload, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    company,
                    out.get("employee_key"),
                    out.get("work_date"),
                    out.get("shift_key") or "",
                    out.get("punch_id"),
                    "punch_appended" if created else "punch_idempotent_hit",
                    source,
                    source_event_id,
                    Json(_json_safe({"created": created, "direction": out.get("direction")})),
                    out.get("created_by_phone"),
                ),
            )
            return out, created

    def list_punches(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str = "",
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_punches
                WHERE company_code=%s AND employee_key=%s AND work_date=%s AND shift_key=%s
                ORDER BY punched_at ASC, punch_id ASC
                """,
                (company_code.upper(), employee_key, work_date, core.shift_key_of(shift_key)),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_current_projection(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str = "",
        for_update: bool = False,
    ) -> dict[str, Any] | None:
        with self._op() as cur:
            lock = " FOR UPDATE" if for_update else ""
            cur.execute(
                f"""
                SELECT * FROM attendance_day_projections
                WHERE company_code=%s AND employee_key=%s AND work_date=%s AND shift_key=%s
                  AND is_current = true
                LIMIT 1
                {lock}
                """,
                (company_code.upper(), employee_key, work_date, core.shift_key_of(shift_key)),
            )
            return _as_dict(cur.fetchone())

    def insert_projection(self, proj: dict[str, Any]) -> dict[str, Any]:
        company = str(proj["company_code"]).upper()
        employee_key = proj["employee_key"]
        work_date = core.parse_date(proj["work_date"])
        skey = core.shift_key_of(proj.get("shift_key"))
        assert work_date is not None
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_day_projections
                WHERE company_code=%s AND employee_key=%s AND work_date=%s AND shift_key=%s
                  AND is_current = true
                FOR UPDATE
                """,
                (company, employee_key, work_date, skey),
            )
            current = _as_dict(cur.fetchone())
            version = int(current["version"]) + 1 if current else 1
            new_id = str(uuid.uuid4())
            if current:
                cur.execute(
                    """
                    UPDATE attendance_day_projections
                    SET is_current=false, superseded_by=%s, updated_at=now()
                    WHERE projection_id=%s
                    """,
                    (new_id, current["projection_id"]),
                )
            cur.execute(
                """
                INSERT INTO attendance_day_projections (
                  projection_id, company_code, employee_key, employee_phone, employee_name,
                  work_date, shift_id, shift_key, version, is_current, status, exception_state,
                  approval_status, payroll_eligible, check_in_at, check_out_at,
                  scheduled_start, scheduled_end, late_minutes, early_leave_minutes,
                  worked_minutes, unpaid_break_minutes, paid_break_minutes,
                  sessions, breaks, source_counts, authority, leave_id,
                  derived_from_leave, manual_correction, metadata, created_by_phone
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                  %s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                RETURNING *
                """,
                (
                    new_id,
                    company,
                    employee_key,
                    proj.get("employee_phone"),
                    proj.get("employee_name"),
                    work_date,
                    proj.get("shift_id") or None,
                    skey,
                    version,
                    proj.get("status"),
                    proj.get("exception_state") or "none",
                    proj.get("approval_status") or "unapproved",
                    bool(proj.get("payroll_eligible")),
                    proj.get("check_in_at"),
                    proj.get("check_out_at"),
                    proj.get("scheduled_start"),
                    proj.get("scheduled_end"),
                    int(proj.get("late_minutes") or 0),
                    int(proj.get("early_leave_minutes") or 0),
                    int(proj.get("worked_minutes") or 0),
                    int(proj.get("unpaid_break_minutes") or 0),
                    int(proj.get("paid_break_minutes") or 0),
                    Json(_json_safe(proj.get("sessions") or [])),
                    Json(_json_safe(proj.get("breaks") or [])),
                    Json(_json_safe(proj.get("source_counts") or {})),
                    proj.get("authority") or AUTHORITY_VERSION,
                    proj.get("leave_id"),
                    bool(proj.get("derived_from_leave")),
                    bool(proj.get("manual_correction")),
                    Json(_json_safe(proj.get("metadata") or {})),
                    proj.get("created_by_phone"),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            cur.execute(
                """
                INSERT INTO attendance_authority_events (
                  company_code, employee_key, work_date, shift_key, projection_id,
                  event_type, payload, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    company,
                    employee_key,
                    work_date,
                    skey,
                    saved["projection_id"],
                    "projection_versioned",
                    Json(_json_safe({"version": version, "status": saved.get("status"), "superseded": (current or {}).get("projection_id")})),
                    saved.get("created_by_phone"),
                ),
            )
            return saved

    def list_current_projections(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            params: list[Any] = [company_code.upper(), start_date, end_date]
            where = ["company_code=%s", "work_date BETWEEN %s AND %s", "is_current=true"]
            if employee_key:
                where.append("employee_key=%s")
                params.append(employee_key)
            if employee_keys is not None:
                where.append("employee_key = ANY(%s)")
                params.append(list(employee_keys))
            cur.execute(
                f"""
                SELECT * FROM attendance_day_projections
                WHERE {' AND '.join(where)}
                ORDER BY work_date, employee_name NULLS LAST, employee_key, shift_key
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def insert_correction(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_corrections (
                  company_code, employee_key, employee_phone, work_date, shift_key,
                  projection_id, status, requested_changes, requested_by_phone, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row.get("employee_key"),
                    row.get("employee_phone"),
                    row["work_date"],
                    core.shift_key_of(row.get("shift_key")),
                    row.get("projection_id"),
                    row.get("status") or "requested",
                    Json(_json_safe(row.get("requested_changes") or {})),
                    row.get("requested_by_phone"),
                    Json(_json_safe(row.get("metadata") or {})),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            cur.execute(
                """
                INSERT INTO attendance_authority_events (
                  company_code, employee_key, work_date, shift_key, correction_id,
                  event_type, payload, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    saved["company_code"],
                    saved.get("employee_key"),
                    saved.get("work_date"),
                    saved.get("shift_key") or "",
                    saved["correction_id"],
                    "correction_requested",
                    Json(_json_safe({"status": saved.get("status")})),
                    saved.get("requested_by_phone"),
                ),
            )
            return saved

    def get_correction(self, correction_id: str, company_code: str) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_corrections
                WHERE correction_id=%s AND company_code=%s
                LIMIT 1
                """,
                (correction_id, company_code.upper()),
            )
            return _as_dict(cur.fetchone())

    def update_correction(self, correction_id: str, company_code: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "decision_note",
            "decided_by_phone",
            "decided_at",
            "dispute_reason",
            "resulting_projection_id",
            "metadata",
        }
        sets = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "metadata":
                sets.append("metadata = metadata || %s")
                params.append(Json(_json_safe(value or {})))
            else:
                sets.append(f"{key}=%s")
                params.append(value)
        if not sets:
            return self.get_correction(correction_id, company_code)
        sets.append("updated_at=now()")
        params.extend([correction_id, company_code.upper()])
        with self._op() as cur:
            cur.execute(
                f"""
                UPDATE attendance_corrections
                SET {', '.join(sets)}
                WHERE correction_id=%s AND company_code=%s
                RETURNING *
                """,
                params,
            )
            saved = _as_dict(cur.fetchone())
            if saved:
                cur.execute(
                    """
                    INSERT INTO attendance_authority_events (
                      company_code, employee_key, work_date, shift_key, correction_id,
                      event_type, payload, created_by_phone
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        saved["company_code"],
                        saved.get("employee_key"),
                        saved.get("work_date"),
                        saved.get("shift_key") or "",
                        saved["correction_id"],
                        f"correction_{saved.get('status')}",
                        Json(_json_safe({"status": saved.get("status"), "decision_note": saved.get("decision_note")})),
                        saved.get("decided_by_phone"),
                    ),
                )
            return saved

    def upsert_payroll_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        company = str(snap["company_code"]).upper()
        skey = core.shift_key_of(snap.get("shift_key"))
        version = int(snap["projection_version"])
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_payroll_snapshots
                WHERE company_code=%s AND employee_key=%s AND work_date=%s
                  AND shift_key=%s AND projection_version=%s
                LIMIT 1
                """,
                (company, snap["employee_key"], snap["work_date"], skey, version),
            )
            existing = _as_dict(cur.fetchone())
            if existing:
                return existing
            payload = snap.get("payload") or {}
            worked = int(payload.get("worked_minutes") or 0)
            cur.execute(
                """
                INSERT INTO attendance_payroll_snapshots (
                  company_code, employee_key, employee_phone, employee_name,
                  work_date, shift_id, shift_key, projection_id, projection_version,
                  approved_by_phone, payload, worked_minutes_cache
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, employee_key, work_date, shift_key, projection_version)
                DO NOTHING
                RETURNING *
                """,
                (
                    company,
                    snap["employee_key"],
                    snap.get("employee_phone"),
                    snap.get("employee_name"),
                    snap["work_date"],
                    snap.get("shift_id") or None,
                    skey,
                    snap["projection_id"],
                    version,
                    snap.get("approved_by_phone"),
                    Json(_json_safe(payload)),
                    worked,
                ),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT * FROM attendance_payroll_snapshots
                    WHERE company_code=%s AND employee_key=%s AND work_date=%s
                      AND shift_key=%s AND projection_version=%s
                    LIMIT 1
                    """,
                    (company, snap["employee_key"], snap["work_date"], skey, version),
                )
                row = cur.fetchone()
            saved = _as_dict(row)
            assert saved is not None
            cur.execute(
                """
                INSERT INTO attendance_authority_events (
                  company_code, employee_key, work_date, shift_key,
                  projection_id, snapshot_id, event_type, payload, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    company,
                    saved.get("employee_key"),
                    saved.get("work_date"),
                    skey,
                    saved.get("projection_id"),
                    saved.get("snapshot_id"),
                    "payroll_snapshot_created",
                    Json(_json_safe({"projection_version": version, "worked_minutes": worked})),
                    saved.get("approved_by_phone"),
                ),
            )
            return saved

    def list_payroll_snapshots(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            params: list[Any] = [company_code.upper(), start_date, end_date]
            where = ["company_code=%s", "work_date BETWEEN %s AND %s"]
            if employee_key:
                where.append("employee_key=%s")
                params.append(employee_key)
            if employee_keys is not None:
                where.append("employee_key = ANY(%s)")
                params.append(list(employee_keys))
            cur.execute(
                f"""
                SELECT DISTINCT ON (employee_key, work_date, shift_key) *
                FROM attendance_payroll_snapshots
                WHERE {' AND '.join(where)}
                ORDER BY employee_key, work_date, shift_key, projection_version DESC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Rebuild + reconcile
# ---------------------------------------------------------------------------

def rebuild_projection_from_punches(
    service: core.AttendanceAuthorityService,
    *,
    company_code: str,
    employee: dict[str, Any],
    work_date: date,
    shift: dict[str, Any] | None = None,
    created_by_phone: str | None = None,
) -> dict[str, Any]:
    """Deterministic rebuild: read immutable punches → new projection version."""
    company = company_code.upper()
    skey = core.shift_key_of(shift.get("shift_id") if shift else None)
    store = service.store
    if hasattr(store, "employee_day_transaction"):
        ctx = store.employee_day_transaction(company, str(employee.get("employee_key")), work_date, skey)
    else:
        from contextlib import nullcontext

        ctx = nullcontext()
    with ctx:
        current = store.get_current_projection(
            company_code=company,
            employee_key=str(employee.get("employee_key")),
            work_date=work_date,
            shift_key=skey,
        )
        forced = None
        if current and current.get("status") in {"absent", "approved_leave"} and not store.list_punches(
            company_code=company,
            employee_key=str(employee.get("employee_key")),
            work_date=work_date,
            shift_key=skey,
        ):
            forced = current.get("status")
        result = service.reproject_day(
            company_code=company,
            employee=employee,
            work_date=work_date,
            shift=shift,
            forced_status=forced,
            created_by_phone=created_by_phone,
            leave_id=(current or {}).get("leave_id"),
            derived_from_leave=bool((current or {}).get("derived_from_leave")),
            manual_correction=bool((current or {}).get("manual_correction")),
            approval_status="unapproved",  # rebuild never auto-approves
            metadata={
                **((current or {}).get("metadata") or {}),
                "rebuilt_from_punches": True,
                "prior_projection_id": (current or {}).get("projection_id"),
            },
        )
        if hasattr(store, "record_event"):
            store.record_event(
                company_code=company,
                event_type="projection_rebuilt_from_punches",
                employee_key=str(employee.get("employee_key")),
                work_date=work_date,
                shift_key=skey,
                projection_id=(result.get("projection") or {}).get("projection_id"),
                payload={"prior": (current or {}).get("projection_id")},
                created_by_phone=created_by_phone,
            )
        return result


COMPAT_COMPARE_FIELDS = (
    "status",
    "check_in_at",
    "check_out_at",
    "late_minutes",
    "early_leave_minutes",
)


def _norm_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return core.as_kuwait(value).isoformat() if core.as_kuwait(value) else None
    text = str(value).replace("Z", "+00:00")
    try:
        return core.as_kuwait(datetime.fromisoformat(text)).isoformat()
    except Exception:
        return text


def _norm_field(name: str, value: Any) -> Any:
    if name in {"check_in_at", "check_out_at"}:
        return _norm_ts(value)
    if name in {"late_minutes", "early_leave_minutes"}:
        return int(value or 0)
    return str(value or "")


def reconcile_compat_mirror(
    cur: Any,
    *,
    company_code: str,
    start_date: date,
    end_date: date,
    employee_key: str | None = None,
    quarantine: bool = True,
) -> dict[str, Any]:
    """Compare current authority projections vs legacy attendance_records.

    Never silently overwrites conflicting legacy data — mismatches are quarantined
    into attendance_compat_drift.
    """
    company = company_code.upper()
    params: list[Any] = [company, start_date, end_date]
    emp_clause = ""
    if employee_key:
        emp_clause = " AND employee_key=%s"
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM attendance_day_projections
        WHERE company_code=%s AND work_date BETWEEN %s AND %s AND is_current=true
        {emp_clause}
        """,
        params,
    )
    projections = [dict(r) for r in cur.fetchall()]
    cur.execute(
        f"""
        SELECT * FROM attendance_records
        WHERE company_code=%s AND attendance_date BETWEEN %s AND %s
        {emp_clause}
        """,
        params,
    )
    legacy_rows = [dict(r) for r in cur.fetchall()]

    def legacy_key(row: dict[str, Any]) -> tuple[str, date | None, str]:
        return (
            str(row.get("employee_key") or ""),
            core.parse_date(row.get("attendance_date") or row.get("work_date")),
            core.shift_key_of(row.get("shift_id")),
        )

    legacy_by_key: dict[tuple[str, date | None, str], dict[str, Any]] = {}
    for row in legacy_rows:
        legacy_by_key[legacy_key(row)] = row

    matched = 0
    drifted: list[dict[str, Any]] = []
    orphan_authority: list[dict[str, Any]] = []
    seen_legacy: set[tuple[str, date | None, str]] = set()

    for proj in projections:
        key = (
            str(proj.get("employee_key") or ""),
            core.parse_date(proj.get("work_date")),
            core.shift_key_of(proj.get("shift_key") or proj.get("shift_id")),
        )
        legacy = legacy_by_key.get(key)
        if not legacy:
            # Only flag orphan authority when projection claims a mirror exists.
            meta = proj.get("metadata") if isinstance(proj.get("metadata"), dict) else {}
            if meta.get("compat_mirrored") or proj.get("approval_status") == "approved":
                orphan_authority.append({"projection": proj, "kind": "orphan_authority"})
            continue
        seen_legacy.add(key)
        mismatches = {}
        for field in COMPAT_COMPARE_FIELDS:
            pv = _norm_field(field, proj.get(field))
            lv = _norm_field(field, legacy.get(field))
            if pv != lv:
                mismatches[field] = {"authority": pv, "legacy": lv}
        # Also compare worked minutes if legacy metadata carries it.
        meta = legacy.get("metadata") if isinstance(legacy.get("metadata"), dict) else {}
        if "worked_minutes" in meta or proj.get("worked_minutes") is not None:
            if int(meta.get("worked_minutes") or -1) not in (-1, int(proj.get("worked_minutes") or 0)):
                # Only when legacy metadata claims authority mirror.
                if meta.get("authority") == AUTHORITY_VERSION:
                    mismatches["worked_minutes"] = {
                        "authority": int(proj.get("worked_minutes") or 0),
                        "legacy": int(meta.get("worked_minutes") or 0),
                    }
        if mismatches:
            drifted.append(
                {
                    "kind": "field_mismatch",
                    "projection_id": str(proj.get("projection_id")),
                    "attendance_id": str(legacy.get("attendance_id")),
                    "employee_key": key[0],
                    "work_date": key[1].isoformat() if key[1] else None,
                    "shift_key": key[2],
                    "mismatches": mismatches,
                }
            )
        else:
            matched += 1

    orphan_legacy = []
    for key, row in legacy_by_key.items():
        if key in seen_legacy:
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if meta.get("authority") == AUTHORITY_VERSION or meta.get("authority_mirror"):
            orphan_legacy.append(
                {
                    "kind": "orphan_legacy_authority_tagged",
                    "attendance_id": str(row.get("attendance_id")),
                    "employee_key": key[0],
                    "work_date": key[1].isoformat() if key[1] else None,
                    "shift_key": key[2],
                }
            )

    quarantined = 0
    if quarantine:
        for item in drifted + orphan_authority + orphan_legacy:
            if item.get("kind") == "orphan_authority":
                proj = item["projection"]
                cur.execute(
                    """
                    INSERT INTO attendance_compat_drift (
                      company_code, employee_key, work_date, shift_key,
                      projection_id, drift_kind, status, details
                    ) VALUES (%s,%s,%s,%s,%s,%s,'quarantined',%s)
                    """,
                    (
                        company,
                        proj.get("employee_key"),
                        proj.get("work_date"),
                        core.shift_key_of(proj.get("shift_key")),
                        proj.get("projection_id"),
                        "orphan_authority",
                        Json(_json_safe({"note": "authority projection without matching legacy row"})),
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO attendance_compat_drift (
                      company_code, employee_key, work_date, shift_key,
                      projection_id, attendance_id, drift_kind, status, details
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,'quarantined',%s)
                    """,
                    (
                        company,
                        item.get("employee_key"),
                        item.get("work_date"),
                        item.get("shift_key") or "",
                        item.get("projection_id"),
                        item.get("attendance_id"),
                        item.get("kind"),
                        Json(_json_safe(item)),
                    ),
                )
            quarantined += 1

    return {
        "ok": True,
        "company_code": company,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "projection_count": len(projections),
        "legacy_count": len(legacy_rows),
        "matched": matched,
        "drift_count": len(drifted),
        "orphan_authority_count": len(orphan_authority),
        "orphan_legacy_count": len(orphan_legacy),
        "quarantined": quarantined,
        "drifts": drifted,
        "orphan_authority": [{"projection_id": str(x["projection"].get("projection_id"))} for x in orphan_authority],
        "orphan_legacy": orphan_legacy,
        "silent_overwrite": False,
    }


def verify_snapshot_immutable(cur: Any, snapshot_id: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM attendance_payroll_snapshots WHERE snapshot_id=%s", (snapshot_id,))
    row = _as_dict(cur.fetchone())
    if not row:
        return {"ok": False, "error": "not_found"}
    try:
        cur.execute(
            "UPDATE attendance_payroll_snapshots SET payload = payload || %s WHERE snapshot_id=%s",
            (Json({"tamper": True}), snapshot_id),
        )
        return {"ok": False, "error": "mutation_allowed"}
    except Exception as exc:
        cur.connection.rollback()
        return {"ok": True, "immutable": True, "error": str(exc).split("\n")[0]}
