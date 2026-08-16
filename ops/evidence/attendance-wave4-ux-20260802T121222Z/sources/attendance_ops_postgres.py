#!/usr/bin/env python3
"""Attendance Wave 3 — durable PostgreSQL store for exception ops (staging/local)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Iterator

from psycopg2.extras import Json, RealDictCursor

import attendance_authority_wave1 as authority
import attendance_ops_wave3 as ops

WAVE3_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS attendance_ops_exceptions (
  exception_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  work_date date NOT NULL,
  shift_key text NOT NULL DEFAULT '',
  projection_id uuid,
  kind text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  priority text NOT NULL DEFAULT 'normal',
  owner_phone text,
  due_at timestamptz,
  source text NOT NULL DEFAULT 'projection',
  source_ref text,
  before_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  payroll_excluded boolean NOT NULL DEFAULT true,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_ops_exc_company_status
  ON attendance_ops_exceptions(company_code, status, due_at);
CREATE INDEX IF NOT EXISTS idx_att_ops_exc_emp_day
  ON attendance_ops_exceptions(company_code, employee_key, work_date, kind);

CREATE TABLE IF NOT EXISTS attendance_ops_cases (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  exception_id uuid,
  correction_id uuid,
  employee_key text NOT NULL,
  employee_phone text,
  work_date date NOT NULL,
  shift_key text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'requested',
  kind text,
  high_risk boolean NOT NULL DEFAULT false,
  dual_approval_required boolean NOT NULL DEFAULT false,
  first_approver_phone text,
  second_approver_phone text,
  requested_by_phone text NOT NULL,
  requested_changes jsonb NOT NULL DEFAULT '{}'::jsonb,
  before_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  apply_idempotency_key text,
  applied_at timestamptz,
  resulting_projection_id uuid,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_att_ops_case_apply_idem
  ON attendance_ops_cases(company_code, apply_idempotency_key)
  WHERE apply_idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_att_ops_cases_company_status
  ON attendance_ops_cases(company_code, status, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_ops_disputes (
  dispute_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  exception_id uuid,
  case_id uuid,
  employee_key text NOT NULL,
  work_date date NOT NULL,
  shift_key text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'open',
  raised_by_phone text NOT NULL,
  reason text NOT NULL DEFAULT '',
  resolution_note text,
  resolved_by_phone text,
  resolved_at timestamptz,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_ops_disp_company_status
  ON attendance_ops_disputes(company_code, status, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_ops_comments (
  comment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  author_phone text,
  body text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_ops_comments_entity
  ON attendance_ops_comments(company_code, entity_type, entity_id, created_at);

CREATE TABLE IF NOT EXISTS attendance_ops_attachments (
  attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  filename text NOT NULL,
  content_type text NOT NULL DEFAULT 'application/octet-stream',
  storage_ref text NOT NULL,
  uploaded_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_ops_attach_entity
  ON attendance_ops_attachments(company_code, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS attendance_ops_audit_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_ops_audit_company
  ON attendance_ops_audit_events(company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_ops_idempotency (
  company_code text NOT NULL,
  idempotency_key text NOT NULL,
  action text NOT NULL,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, idempotency_key)
);

CREATE OR REPLACE FUNCTION attendance_ops_audit_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'attendance_ops_audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_att_ops_audit_immutable ON attendance_ops_audit_events;
CREATE TRIGGER trg_att_ops_audit_immutable
  BEFORE UPDATE OR DELETE ON attendance_ops_audit_events
  FOR EACH ROW EXECUTE FUNCTION attendance_ops_audit_immutable();
"""

WAVE3_ROLLBACK_DDL = """
DROP TRIGGER IF EXISTS trg_att_ops_audit_immutable ON attendance_ops_audit_events;
DROP FUNCTION IF EXISTS attendance_ops_audit_immutable();
DROP TABLE IF EXISTS attendance_ops_idempotency;
DROP TABLE IF EXISTS attendance_ops_audit_events;
DROP TABLE IF EXISTS attendance_ops_attachments;
DROP TABLE IF EXISTS attendance_ops_comments;
DROP TABLE IF EXISTS attendance_ops_disputes;
DROP TABLE IF EXISTS attendance_ops_cases;
DROP TABLE IF EXISTS attendance_ops_exceptions;
"""


def ensure_attendance_ops_postgres_schema(cur: Any) -> None:
    cur.execute(WAVE3_SCHEMA_DDL)


def rollback_attendance_ops_postgres_schema(cur: Any) -> None:
    cur.execute(WAVE3_ROLLBACK_DDL)


def _as_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _json_safe(value: Any) -> Any:
    return ops._json_safe(value)


class PostgresOpsStore:
    """Durable Wave 3 ops store. Uses app.db_connect when available."""

    def __init__(self, connect_fn: Any | None = None) -> None:
        self._connect_fn = connect_fn

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn()
        import app as orch_app

        return orch_app.db_connect()

    @contextmanager
    def _op(self) -> Iterator[Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
                conn.commit()

    def _audit(self, cur: Any, row: dict[str, Any]) -> None:
        cur.execute(
            """
            INSERT INTO attendance_ops_audit_events (
              company_code, entity_type, entity_id, event_type, payload, created_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                str(row["company_code"]).upper(),
                row["entity_type"],
                str(row["entity_id"]),
                row["event_type"],
                Json(_json_safe(row.get("payload") or {})),
                ops.digits(row.get("created_by_phone")),
            ),
        )

    def insert_exception(self, row: dict[str, Any]) -> dict[str, Any]:
        pri = row.get("priority") or ops.default_priority(row["kind"])
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_exceptions (
                  company_code, employee_key, employee_phone, employee_name, work_date, shift_key,
                  projection_id, kind, status, priority, owner_phone, due_at, source, source_ref,
                  before_values, after_values, payroll_excluded, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row["employee_key"],
                    ops.digits(row.get("employee_phone")),
                    row.get("employee_name"),
                    row["work_date"],
                    authority.shift_key_of(row.get("shift_key")),
                    row.get("projection_id"),
                    row["kind"],
                    row.get("status") or "open",
                    pri,
                    ops.digits(row.get("owner_phone")),
                    row.get("due_at") or ops.default_due_at(pri),
                    row.get("source") or "projection",
                    row.get("source_ref"),
                    Json(_json_safe(row.get("before_values") or {})),
                    Json(_json_safe(row.get("after_values") or {})),
                    bool(row.get("payroll_excluded", True)),
                    Json(_json_safe(row.get("metadata") or {})),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            self._audit(cur, {
                "company_code": saved["company_code"],
                "entity_type": "exception",
                "entity_id": saved["exception_id"],
                "event_type": "exception_opened",
                "payload": {"kind": saved["kind"], "status": saved["status"]},
                "created_by_phone": ops.digits((row.get("metadata") or {}).get("opened_by")),
            })
            return saved

    def get_exception(self, exception_id: str, company_code: str) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_exceptions WHERE exception_id=%s AND company_code=%s LIMIT 1",
                (exception_id, company_code.upper()),
            )
            return _as_dict(cur.fetchone())

    def update_exception(
        self,
        exception_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_exceptions WHERE exception_id=%s AND company_code=%s FOR UPDATE",
                (exception_id, company),
            )
            current = _as_dict(cur.fetchone())
            if not current:
                return None
            if expected_row_version is not None and int(current["row_version"]) != int(expected_row_version):
                return {"__conflict__": True, "current": current}
            sets = ["row_version = row_version + 1", "updated_at=now()"]
            params: list[Any] = []
            for key, value in fields.items():
                if key == "metadata":
                    sets.append("metadata = metadata || %s")
                    params.append(Json(_json_safe(value or {})))
                elif key in {
                    "status", "priority", "owner_phone", "due_at", "source_ref",
                    "payroll_excluded", "projection_id", "after_values", "before_values",
                }:
                    if key in {"before_values", "after_values"}:
                        sets.append(f"{key}=%s")
                        params.append(Json(_json_safe(value or {})))
                    elif key == "owner_phone":
                        sets.append("owner_phone=%s")
                        params.append(ops.digits(value))
                    else:
                        sets.append(f"{key}=%s")
                        params.append(value)
            params.extend([exception_id, company])
            cur.execute(
                f"UPDATE attendance_ops_exceptions SET {', '.join(sets)} WHERE exception_id=%s AND company_code=%s RETURNING *",
                params,
            )
            return _as_dict(cur.fetchone())

    def list_exceptions(
        self,
        *,
        company_code: str,
        status: str | None = None,
        kind: str | None = None,
        owner_phone: str | None = None,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            where = ["company_code=%s"]
            params: list[Any] = [company_code.upper()]
            if status:
                where.append("status=%s")
                params.append(status)
            if kind:
                where.append("kind=%s")
                params.append(kind)
            if owner_phone:
                where.append("owner_phone=%s")
                params.append(ops.digits(owner_phone))
            if employee_key:
                where.append("employee_key=%s")
                params.append(employee_key)
            if employee_keys is not None:
                where.append("employee_key = ANY(%s)")
                params.append(list(employee_keys))
            cur.execute(
                f"""
                SELECT * FROM attendance_ops_exceptions
                WHERE {' AND '.join(where)}
                ORDER BY due_at DESC NULLS LAST, created_at DESC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def find_open_exception(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str,
        kind: str,
    ) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_ops_exceptions
                WHERE company_code=%s AND employee_key=%s AND work_date=%s AND shift_key=%s AND kind=%s
                  AND status = ANY(%s)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    company_code.upper(),
                    employee_key,
                    work_date,
                    authority.shift_key_of(shift_key),
                    kind,
                    ["open", "assigned", "in_review", "pending_dual_approval", "reopened"],
                ),
            )
            return _as_dict(cur.fetchone())

    def insert_case(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_cases (
                  company_code, exception_id, correction_id, employee_key, employee_phone,
                  work_date, shift_key, status, kind, high_risk, dual_approval_required,
                  first_approver_phone, second_approver_phone, requested_by_phone,
                  requested_changes, before_snapshot, after_snapshot, decision_note, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row.get("exception_id"),
                    row.get("correction_id"),
                    row["employee_key"],
                    ops.digits(row.get("employee_phone")),
                    row["work_date"],
                    authority.shift_key_of(row.get("shift_key")),
                    row.get("status") or "requested",
                    row.get("kind"),
                    bool(row.get("high_risk")),
                    bool(row.get("dual_approval_required")),
                    ops.digits(row.get("first_approver_phone")),
                    ops.digits(row.get("second_approver_phone")),
                    ops.digits(row.get("requested_by_phone")),
                    Json(_json_safe(row.get("requested_changes") or {})),
                    Json(_json_safe(row.get("before_snapshot") or {})),
                    Json(_json_safe(row.get("after_snapshot") or {})),
                    row.get("decision_note"),
                    Json(_json_safe(row.get("metadata") or {})),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            self._audit(cur, {
                "company_code": saved["company_code"],
                "entity_type": "case",
                "entity_id": saved["case_id"],
                "event_type": "correction_requested",
                "payload": {"status": saved["status"], "correction_id": str(saved.get("correction_id") or "")},
                "created_by_phone": saved.get("requested_by_phone"),
            })
            return saved

    def get_case(self, case_id: str, company_code: str) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_cases WHERE case_id=%s AND company_code=%s LIMIT 1",
                (case_id, company_code.upper()),
            )
            return _as_dict(cur.fetchone())

    def list_cases_for_exception(self, exception_id: str, company_code: str) -> list[dict[str, Any]]:
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_cases WHERE exception_id=%s AND company_code=%s",
                (exception_id, company_code.upper()),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_cases(
        self,
        *,
        company_code: str,
        status: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            where = ["company_code=%s"]
            params: list[Any] = [company_code.upper()]
            if status:
                where.append("status=%s")
                params.append(status)
            if employee_keys is not None:
                where.append("employee_key = ANY(%s)")
                params.append(list(employee_keys))
            cur.execute(
                f"""
                SELECT * FROM attendance_ops_cases
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def list_disputes(
        self,
        *,
        company_code: str,
        status: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._op() as cur:
            where = ["company_code=%s"]
            params: list[Any] = [company_code.upper()]
            if status:
                where.append("status=%s")
                params.append(status)
            if employee_keys is not None:
                where.append("employee_key = ANY(%s)")
                params.append(list(employee_keys))
            cur.execute(
                f"""
                SELECT * FROM attendance_ops_disputes
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def update_case(
        self,
        case_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_cases WHERE case_id=%s AND company_code=%s FOR UPDATE",
                (case_id, company),
            )
            current = _as_dict(cur.fetchone())
            if not current:
                return None
            if expected_row_version is not None and int(current["row_version"]) != int(expected_row_version):
                return {"__conflict__": True, "current": current}
            sets = ["row_version = row_version + 1", "updated_at=now()"]
            params: list[Any] = []
            for key, value in fields.items():
                if key == "metadata":
                    sets.append("metadata = metadata || %s")
                    params.append(Json(_json_safe(value or {})))
                elif key in {
                    "status", "first_approver_phone", "second_approver_phone", "decision_note",
                    "apply_idempotency_key", "applied_at", "resulting_projection_id",
                    "before_snapshot", "after_snapshot", "correction_id", "high_risk",
                    "dual_approval_required",
                }:
                    if key in {"before_snapshot", "after_snapshot"}:
                        sets.append(f"{key}=%s")
                        params.append(Json(_json_safe(value or {})))
                    elif key.endswith("_phone"):
                        sets.append(f"{key}=%s")
                        params.append(ops.digits(value))
                    else:
                        sets.append(f"{key}=%s")
                        params.append(value)
            params.extend([case_id, company])
            cur.execute(
                f"UPDATE attendance_ops_cases SET {', '.join(sets)} WHERE case_id=%s AND company_code=%s RETURNING *",
                params,
            )
            return _as_dict(cur.fetchone())

    def insert_dispute(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_disputes (
                  company_code, exception_id, case_id, employee_key, work_date, shift_key,
                  status, raised_by_phone, reason, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row.get("exception_id"),
                    row.get("case_id"),
                    row["employee_key"],
                    row["work_date"],
                    authority.shift_key_of(row.get("shift_key")),
                    row.get("status") or "open",
                    ops.digits(row.get("raised_by_phone")),
                    row.get("reason") or "",
                    Json(_json_safe(row.get("metadata") or {})),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            self._audit(cur, {
                "company_code": saved["company_code"],
                "entity_type": "dispute",
                "entity_id": saved["dispute_id"],
                "event_type": "dispute_raised",
                "payload": {"reason": saved["reason"]},
                "created_by_phone": saved.get("raised_by_phone"),
            })
            return saved

    def get_dispute(self, dispute_id: str, company_code: str) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_disputes WHERE dispute_id=%s AND company_code=%s LIMIT 1",
                (dispute_id, company_code.upper()),
            )
            return _as_dict(cur.fetchone())

    def update_dispute(
        self,
        dispute_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_disputes WHERE dispute_id=%s AND company_code=%s FOR UPDATE",
                (dispute_id, company),
            )
            current = _as_dict(cur.fetchone())
            if not current:
                return None
            if expected_row_version is not None and int(current["row_version"]) != int(expected_row_version):
                return {"__conflict__": True, "current": current}
            sets = ["row_version = row_version + 1", "updated_at=now()"]
            params: list[Any] = []
            for key, value in fields.items():
                if key == "metadata":
                    sets.append("metadata = metadata || %s")
                    params.append(Json(_json_safe(value or {})))
                elif key in {
                    "status", "resolution_note", "resolved_by_phone", "resolved_at",
                    "case_id", "exception_id",
                }:
                    if key.endswith("_phone"):
                        sets.append(f"{key}=%s")
                        params.append(ops.digits(value))
                    else:
                        sets.append(f"{key}=%s")
                        params.append(value)
            params.extend([dispute_id, company])
            cur.execute(
                f"UPDATE attendance_ops_disputes SET {', '.join(sets)} WHERE dispute_id=%s AND company_code=%s RETURNING *",
                params,
            )
            return _as_dict(cur.fetchone())

    def add_comment(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_comments (
                  company_code, entity_type, entity_id, author_phone, body
                ) VALUES (%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row["entity_type"],
                    row["entity_id"],
                    ops.digits(row.get("author_phone")),
                    str(row.get("body") or ""),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            self._audit(cur, {
                "company_code": saved["company_code"],
                "entity_type": saved["entity_type"],
                "entity_id": saved["entity_id"],
                "event_type": "comment_added",
                "payload": {"comment_id": str(saved["comment_id"])},
                "created_by_phone": saved.get("author_phone"),
            })
            return saved

    def add_attachment(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_attachments (
                  company_code, entity_type, entity_id, filename, content_type, storage_ref, uploaded_by_phone
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    str(row["company_code"]).upper(),
                    row["entity_type"],
                    row["entity_id"],
                    row.get("filename") or "attachment",
                    row.get("content_type") or "application/octet-stream",
                    row.get("storage_ref") or "",
                    ops.digits(row.get("uploaded_by_phone")),
                ),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            self._audit(cur, {
                "company_code": saved["company_code"],
                "entity_type": saved["entity_type"],
                "entity_id": saved["entity_id"],
                "event_type": "attachment_added",
                "payload": {"attachment_id": str(saved["attachment_id"]), "filename": saved["filename"]},
                "created_by_phone": saved.get("uploaded_by_phone"),
            })
            return saved

    def list_comments(self, *, company_code: str, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_ops_comments
                WHERE company_code=%s AND entity_type=%s AND entity_id=%s
                ORDER BY created_at
                """,
                (company_code.upper(), entity_type, entity_id),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_attachments(self, *, company_code: str, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        with self._op() as cur:
            cur.execute(
                """
                SELECT * FROM attendance_ops_attachments
                WHERE company_code=%s AND entity_type=%s AND entity_id=%s
                ORDER BY created_at
                """,
                (company_code.upper(), entity_type, entity_id),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_audit(self, *, company_code: str, entity_type: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        with self._op() as cur:
            where = ["company_code=%s"]
            params: list[Any] = [company_code.upper()]
            if entity_type:
                where.append("entity_type=%s")
                params.append(entity_type)
            if entity_id:
                where.append("entity_id=%s")
                params.append(str(entity_id))
            cur.execute(
                f"SELECT * FROM attendance_ops_audit_events WHERE {' AND '.join(where)} ORDER BY created_at",
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def get_idempotency(self, company_code: str, key: str) -> dict[str, Any] | None:
        with self._op() as cur:
            cur.execute(
                "SELECT * FROM attendance_ops_idempotency WHERE company_code=%s AND idempotency_key=%s",
                (company_code.upper(), key),
            )
            return _as_dict(cur.fetchone())

    def put_idempotency(self, company_code: str, key: str, action: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._op() as cur:
            cur.execute(
                """
                INSERT INTO attendance_ops_idempotency (company_code, idempotency_key, action, result)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (company_code, idempotency_key) DO UPDATE
                  SET action=EXCLUDED.action, result=EXCLUDED.result
                RETURNING *
                """,
                (company_code.upper(), key, action, Json(_json_safe(result))),
            )
            saved = _as_dict(cur.fetchone())
            assert saved is not None
            return saved

    def audit_event(self, row: dict[str, Any]) -> None:
        with self._op() as cur:
            self._audit(cur, row)
