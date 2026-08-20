#!/usr/bin/env python3
"""Governed HR Intelligence projection freshness.

Canonical domain write → existing domain event / ledger / audit table →
tenant-scoped incremental intelligence projection.

This module is not a second source of truth. It tails existing domain
event, ledger, and audit tables, upserts into C2–C5 projections with the
existing APIs, and records data_as_of so stale intelligence is never
labelled current.

Payroll money is never marked current here. Missing employment dates are
never fabricated.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_projection_freshness"
CONTRACT_VERSION = "hr_intelligence_projection_v1"
REASON = "hr_intelligence_automatic_freshness"
SOURCE_FAMILIES = (
    "workforce",
    "recruiting",
    "attendance",
    "leave",
    "shifts",
    "performance",
    "talent",
)
PAYROLL_FAMILY = "payroll"
_ON = {"1", "true", "yes", "on"}
_MODULE_FOR_FAMILY = {
    "workforce": None,
    "recruiting": "pre_hiring",
    "attendance": "attendance",
    "leave": "leave",
    "shifts": "shifts",
    "performance": "performance",
    "talent": "talent",
    "payroll": "payroll",
}
_SEMANTIC_FAMILY_PREFIXES = (
    ("workforce.", "workforce"),
    ("recruiting.", "recruiting"),
    ("hire_ready.", "recruiting"),
    ("time.", "attendance"),
    ("overtime.", "attendance"),
    ("leave.", "leave"),
    ("shifts.", "shifts"),
    ("payroll.", "payroll"),
    ("performance.", "performance"),
    ("talent.", "talent"),
)


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name) or default).strip().lower() in _ON


def _actor() -> str:
    return str(os.environ.get("WATHEFNI_HR_INTELLIGENCE_PROJECTION_ACTOR") or "96599338566")


def stale_after_seconds() -> int:
    try:
        return max(1, int(os.environ.get("WATHEFNI_HR_INTELLIGENCE_STALE_AFTER_SECONDS") or "180"))
    except (TypeError, ValueError):
        return 180


def max_attempts() -> int:
    try:
        return max(3, int(os.environ.get("WATHEFNI_HR_INTELLIGENCE_PROJECTION_MAX_ATTEMPTS") or "8"))
    except (TypeError, ValueError):
        return 8


def reconcile_every_seconds() -> int:
    try:
        return max(60, int(os.environ.get("WATHEFNI_HR_INTELLIGENCE_RECONCILE_EVERY_SECONDS") or "900"))
    except (TypeError, ValueError):
        return 900


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _as_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def family_for_semantic_key(semantic_key: str | None) -> str:
    key = str(semantic_key or "").strip().lower()
    for prefix, family in _SEMANTIC_FAMILY_PREFIXES:
        if key.startswith(prefix):
            return family
    return "workforce"


def _has_table(cur: Any, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
    row = cur.fetchone()
    if not row:
        return False
    value = list(row.values())[0] if isinstance(row, dict) else row[0]
    return bool(value)


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {str(r["column_name"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])}


def _rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(item) for item in (cur.fetchall() or [])]


def _row(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    found = cur.fetchone()
    return dict(found) if found else None


def enabled_modules(cur: Any, company: str) -> dict[str, bool]:
    if not _has_table(cur, "company_modules"):
        return {}
    return {
        str(item["module_key"]): bool(item["enabled"])
        for item in _rows(cur, "SELECT module_key, enabled FROM company_modules WHERE company_code=%s", (company,))
    }


def family_module_enabled(cur: Any, company: str, family: str) -> bool:
    required = _MODULE_FOR_FAMILY.get(family)
    if not required:
        return True
    return bool(enabled_modules(cur, company).get(required))


def ensure_hr_intelligence_projection_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_projection_cursor (
          company_code text NOT NULL,
          source_family text NOT NULL,
          cursor_kind text NOT NULL,
          last_seen_at timestamptz,
          last_seen_id text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, source_family, cursor_kind)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_projection_outbox (
          outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          source_family text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          event_ref text NOT NULL,
          idempotency_key text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'queued',
          attempts integer NOT NULL DEFAULT 0,
          next_attempt_at timestamptz NOT NULL DEFAULT now(),
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          processed_at timestamptz,
          CHECK (status IN ('queued','processing','done','failed','dead')),
          UNIQUE (company_code, idempotency_key)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hr_intel_outbox_drain
          ON hr_intelligence_projection_outbox (company_code, status, next_attempt_at)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_source_freshness (
          company_code text NOT NULL,
          source_family text NOT NULL,
          data_as_of timestamptz,
          last_source_event_at timestamptz,
          last_projected_at timestamptz,
          last_reconciled_at timestamptz,
          last_rebuild_at timestamptz,
          lag_seconds integer NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'never',
          guaranteed_current boolean NOT NULL DEFAULT false,
          pending_outbox_count integer NOT NULL DEFAULT 0,
          failed_outbox_count integer NOT NULL DEFAULT 0,
          last_error text,
          skip_reasons jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, source_family),
          CHECK (status IN ('current','stale','error','never','unavailable'))
        )
        """
    )


def entitled_companies(cur: Any) -> list[str]:
    if not _has_table(cur, "hr_intelligence_c1_company_settings"):
        return []
    rows = _rows(
        cur,
        """
        SELECT s.company_code
          FROM hr_intelligence_c1_company_settings s
          LEFT JOIN hr_intelligence_c6_company_settings c6
            ON c6.company_code=s.company_code
         WHERE s.enabled=true
           AND COALESCE(c6.enabled, true)=true
         ORDER BY s.company_code
        """,
    )
    out = []
    for row in rows:
        company = c1.company_code_norm(row["company_code"])
        gate = c1.runtime_gate_for_company(company)
        if gate.get("ok"):
            out.append(company)
    return out


def enqueue(
    cur: Any,
    *,
    company_code: str,
    source_family: str,
    entity_type: str,
    entity_id: str,
    event_ref: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = c1.company_code_norm(company_code)
    if not company or source_family not in SOURCE_FAMILIES:
        return {"ok": False, "error": "invalid_enqueue"}
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return {"ok": False, "error": "entity_id_required"}
    key = f"{source_family}:{entity_type}:{entity_id}:{event_ref}"
    cur.execute(
        """
        INSERT INTO hr_intelligence_projection_outbox (
          company_code, source_family, entity_type, entity_id, event_ref,
          idempotency_key, payload, status, next_attempt_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'queued',now())
        ON CONFLICT (company_code, idempotency_key) DO NOTHING
        RETURNING outbox_id, status
        """,
        (
            company,
            source_family,
            str(entity_type),
            entity_id,
            str(event_ref),
            key,
            json.dumps(payload or {}, default=str),
        ),
    )
    row = cur.fetchone()
    return {"ok": True, "enqueued": bool(row), "idempotency_key": key, "company_code": company}


def notify_canonical_write(
    cur: Any,
    *,
    company_code: str,
    source_family: str,
    entity_type: str,
    entity_id: str,
    event_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call from a canonical write adapter. Does not mutate domain SoT."""
    ref = event_ref or f"write:{_utc_now().isoformat()}:{entity_id}"
    return enqueue(
        cur,
        company_code=company_code,
        source_family=source_family,
        entity_type=entity_type,
        entity_id=str(entity_id),
        event_ref=ref,
        payload=payload,
    )


def _cursor(cur: Any, company: str, family: str, kind: str) -> dict[str, Any]:
    row = _row(
        cur,
        """
        SELECT * FROM hr_intelligence_projection_cursor
         WHERE company_code=%s AND source_family=%s AND cursor_kind=%s
        """,
        (company, family, kind),
    )
    return row or {"last_seen_at": datetime(1970, 1, 1, tzinfo=timezone.utc), "last_seen_id": ""}


def _save_cursor(cur: Any, company: str, family: str, kind: str, seen_at: Any, seen_id: Any) -> None:
    cur.execute(
        """
        INSERT INTO hr_intelligence_projection_cursor (
          company_code, source_family, cursor_kind, last_seen_at, last_seen_id, updated_at
        ) VALUES (%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, source_family, cursor_kind) DO UPDATE SET
          last_seen_at=EXCLUDED.last_seen_at,
          last_seen_id=EXCLUDED.last_seen_id,
          updated_at=now()
        """,
        (company, family, kind, _as_dt(seen_at), str(seen_id or "")),
    )


def _tail(
    cur: Any,
    *,
    table: str,
    company: str,
    id_col: str,
    ts_col: str,
    extra: str = "",
    limit: int = 400,
) -> list[dict[str, Any]]:
    if not _has_table(cur, table):
        return []
    cols = _columns(cur, table)
    if "company_code" not in cols or id_col not in cols or ts_col not in cols:
        return []
    watermark = _cursor(cur, company, table, ts_col)
    seen_at = _as_dt(watermark.get("last_seen_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)
    overlap = seen_at - timedelta(seconds=2)
    sql = f"""
        SELECT * FROM {table}
         WHERE company_code=%s AND {ts_col} >= %s {extra}
         ORDER BY {ts_col} ASC, {id_col} ASC
         LIMIT %s
    """
    return _rows(cur, sql, (company, overlap, limit))


def _advance_from_rows(cur: Any, company: str, table: str, ts_col: str, id_col: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    last = rows[-1]
    _save_cursor(cur, company, table, ts_col, last.get(ts_col), last.get(id_col))


def ingest_company_events(cur: Any, company_code: str, *, limit: int = 400) -> dict[str, Any]:
    company = c1.company_code_norm(company_code)
    ensure_hr_intelligence_projection_schema(cur)
    counts: dict[str, int] = {}

    def _take(family: str, entity_type: str, entity_id: Any, event_ref: str, payload: dict[str, Any] | None = None) -> None:
        if not entity_id:
            return
        if not family_module_enabled(cur, company, family):
            return
        result = enqueue(
            cur,
            company_code=company,
            source_family=family,
            entity_type=entity_type,
            entity_id=str(entity_id),
            event_ref=event_ref,
            payload=payload,
        )
        counts[family] = counts.get(family, 0) + int(bool(result.get("enqueued")))

    rows = _tail(cur, table="employee_lifecycle_events", company=company, id_col="event_id", ts_col="created_at", limit=limit)
    for row in rows:
        _take("workforce", "employee", row.get("employee_key"), f"employee_lifecycle_events:{row.get('event_id')}", row)
    _advance_from_rows(cur, company, "employee_lifecycle_events", "created_at", "event_id", rows)

    if _has_table(cur, "employees"):
        emp_cols = _columns(cur, "employees")
        ts_col = "updated_at" if "updated_at" in emp_cols else ("created_at" if "created_at" in emp_cols else "")
        id_col = "employee_key" if "employee_key" in emp_cols else ""
        if ts_col and id_col:
            rows = _tail(cur, table="employees", company=company, id_col=id_col, ts_col=ts_col, limit=limit)
            for row in rows:
                _take("workforce", "employee", row.get("employee_key"), f"employees:{row.get('employee_key')}:{_iso(row.get(ts_col))}", row)
            _advance_from_rows(cur, company, "employees", ts_col, id_col, rows)

    rows = _tail(cur, table="application_lifecycle_events", company=company, id_col="event_id", ts_col="created_at", limit=limit)
    for row in rows:
        _take("recruiting", "application", row.get("app_key"), f"application_lifecycle_events:{row.get('event_id')}", row)
    _advance_from_rows(cur, company, "application_lifecycle_events", "created_at", "event_id", rows)

    if _has_table(cur, "applications"):
        app_cols = _columns(cur, "applications")
        ts_col = "updated_at" if "updated_at" in app_cols else ("created_at" if "created_at" in app_cols else "")
        if ts_col and "app_key" in app_cols:
            rows = _tail(cur, table="applications", company=company, id_col="app_key", ts_col=ts_col, limit=limit)
            for row in rows:
                _take("recruiting", "application", row.get("app_key"), f"applications:{row.get('app_key')}:{_iso(row.get(ts_col))}", row)
            _advance_from_rows(cur, company, "applications", ts_col, "app_key", rows)

    rows = _tail(cur, table="attendance_authority_events", company=company, id_col="event_id", ts_col="created_at", limit=limit)
    for row in rows:
        entity = f"{row.get('employee_key')}:{row.get('work_date')}" if row.get("work_date") else row.get("employee_key")
        _take("attendance", "attendance_day", entity, f"attendance_authority_events:{row.get('event_id')}", row)
    _advance_from_rows(cur, company, "attendance_authority_events", "created_at", "event_id", rows)

    if _has_table(cur, "attendance_day_projections"):
        day_cols = _columns(cur, "attendance_day_projections")
        ts_col = "updated_at" if "updated_at" in day_cols else ("created_at" if "created_at" in day_cols else "")
        extra = "AND is_current=true" if "is_current" in day_cols else ""
        id_col = "projection_id" if "projection_id" in day_cols else "employee_key"
        if ts_col:
            rows = _tail(cur, table="attendance_day_projections", company=company, id_col=id_col, ts_col=ts_col, extra=extra, limit=limit)
            for row in rows:
                entity = f"{row.get('employee_key')}:{row.get('work_date')}"
                _take("attendance", "attendance_day", entity, f"attendance_day_projections:{row.get(id_col)}:{_iso(row.get(ts_col))}", row)
            _advance_from_rows(cur, company, "attendance_day_projections", ts_col, id_col, rows)

    if _has_table(cur, "leave_ledger"):
        led_cols = _columns(cur, "leave_ledger")
        id_col = "entry_id" if "entry_id" in led_cols else ("ledger_id" if "ledger_id" in led_cols else "")
        ts_col = "created_at" if "created_at" in led_cols else ""
        if id_col and ts_col:
            rows = _tail(cur, table="leave_ledger", company=company, id_col=id_col, ts_col=ts_col, limit=limit)
            for row in rows:
                _take("leave", "leave_entry", row.get(id_col), f"leave_ledger:{row.get(id_col)}", row)
            _advance_from_rows(cur, company, "leave_ledger", ts_col, id_col, rows)

    if _has_table(cur, "shift_assignments"):
        sh_cols = _columns(cur, "shift_assignments")
        id_col = "shift_id" if "shift_id" in sh_cols else ("assignment_id" if "assignment_id" in sh_cols else "")
        ts_col = "updated_at" if "updated_at" in sh_cols else ("created_at" if "created_at" in sh_cols else "")
        if id_col and ts_col:
            rows = _tail(cur, table="shift_assignments", company=company, id_col=id_col, ts_col=ts_col, limit=limit)
            for row in rows:
                _take("shifts", "shift_assignment", row.get(id_col), f"shift_assignments:{row.get(id_col)}:{_iso(row.get(ts_col))}", row)
            _advance_from_rows(cur, company, "shift_assignments", ts_col, id_col, rows)

    for table, id_col in (
        ("performance_goals_c1_audit", "audit_id"),
        ("perf_okr_alignment_events", "event_id"),
    ):
        if not _has_table(cur, table):
            continue
        cols = _columns(cur, table)
        ts_col = "created_at" if "created_at" in cols else ""
        if not ts_col or id_col not in cols:
            continue
        rows = _tail(cur, table=table, company=company, id_col=id_col, ts_col=ts_col, limit=limit)
        for row in rows:
            subject = row.get("subject_id") or row.get("objective_id") or row.get("key_result_id") or row.get(id_col)
            entity_type = str(row.get("subject_type") or row.get("entity_type") or "objective")
            _take("performance", entity_type, subject, f"{table}:{row.get(id_col)}", row)
        _advance_from_rows(cur, company, table, ts_col, id_col, rows)

    for table, id_col in (
        ("talent_profile_c5_audit", "audit_id"),
        ("talent_succession_c6_audit", "audit_id"),
    ):
        if not _has_table(cur, table):
            continue
        cols = _columns(cur, table)
        ts_col = "created_at" if "created_at" in cols else ""
        if not ts_col or id_col not in cols:
            continue
        rows = _tail(cur, table=table, company=company, id_col=id_col, ts_col=ts_col, limit=limit)
        for row in rows:
            subject = row.get("subject_id") or row.get("employee_key") or row.get(id_col)
            entity_type = str(row.get("subject_type") or "talent")
            _take("talent", entity_type, subject, f"{table}:{row.get(id_col)}", row)
        _advance_from_rows(cur, company, table, ts_col, id_col, rows)

    return {"ok": True, "company_code": company, "enqueued": counts}


def _dept(profile: Any, raw: Any) -> str | None:
    for blob in (profile, raw):
        if isinstance(blob, dict) and blob.get("department"):
            return str(blob.get("department"))
    return None


def _mgr(raw: Any) -> str | None:
    if isinstance(raw, dict) and raw.get("manager_employee_key"):
        return str(raw.get("manager_employee_key"))
    return None


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def project_workforce_row(cur: Any, *, company: str, emp: dict[str, Any], actor: str) -> dict[str, Any]:
    import hr_intelligence_workforce_c2 as c2

    key = str(emp.get("employee_key") or "").strip()
    if not key:
        return {"ok": False, "error": "employee_key_required", "skipped": True}
    status_raw = str(emp.get("employment_status") or emp.get("status") or "").strip().lower()
    start = _as_date(emp.get("start_date") or emp.get("hire_date") or emp.get("effective_start"))
    if not start:
        return {"ok": True, "skipped": True, "reason": "missing_employment_date", "employee_key": key}
    payload = _json_obj(emp.get("payload"))
    if status_raw in {"terminated", "left"}:
        end = _as_date(
            emp.get("end_date")
            or emp.get("last_working_day")
            or emp.get("termination_date")
            or emp.get("effective_end")
            or emp.get("effective_on")
            or payload.get("last_working_day")
            or payload.get("effective_on")
        )
        if not end:
            return {"ok": True, "skipped": True, "reason": "missing_exit_date", "employee_key": key}
        status, exit_type = "left", str(emp.get("termination_type") or payload.get("termination_type") or "unknown")
        if exit_type not in {"voluntary", "involuntary", "other", "unknown"}:
            exit_type = "unknown"
    elif status_raw in {"active", "on_leave", "suspended"}:
        status, exit_type, end = "active", None, None
    else:
        return {"ok": True, "skipped": True, "reason": "unsupported_employment_status", "employee_key": key}
    profile = _json_obj(emp.get("profile"))
    raw = _json_obj(emp.get("raw_json"))
    ver = f"v:{status}:{start}:{end}:{_dept(profile, raw)}:{_mgr(raw)}"
    existing = _row(
        cur,
        """
        SELECT source_version FROM hr_intelligence_employment_periods
         WHERE company_code=%s AND employment_period_key=%s AND superseded_by IS NULL
        """,
        (company, key),
    )
    if existing and str(existing.get("source_version") or "") == ver:
        return {"ok": True, "unchanged": True, "employee_key": key}
    out = c2.upsert_employment_period(
        cur,
        company_code=company,
        actor_phone=actor,
        employee_key=key,
        employment_period_key=key,
        status=status,
        effective_start=start,
        effective_end=end,
        exit_event_date=end if status == "left" else None,
        exit_type=exit_type,
        hire_event_date=_as_date(emp.get("hire_date")) or start,
        department=_dept(profile, raw),
        job_role=emp.get("position_title") or None,
        manager_employee_key=_mgr(raw),
        source_authority="domain_employees",
        source_version=ver,
        reason=REASON,
    )
    return {**out, "employee_key": key}


def _map_attendance_status(status: str) -> str:
    raw = str(status or "").strip().lower()
    if raw in {"present", "late", "completed", "absent", "approved_leave", "void", "incomplete"}:
        return raw
    if raw == "early_leave":
        return "completed"
    return "incomplete"


def _shift_hours(start: Any, end: Any) -> float | None:
    if start is None or end is None:
        return None
    try:
        sdt = datetime.combine(date.today(), start) if not isinstance(start, datetime) else start
        edt = datetime.combine(date.today(), end) if not isinstance(end, datetime) else end
        delta = (edt - sdt).total_seconds() / 3600.0
        if delta < 0:
            delta += 24
        return delta if delta > 0 else None
    except Exception:
        return None


def apply_outbox_item(cur: Any, item: dict[str, Any]) -> dict[str, Any]:
    company = str(item["company_code"])
    family = str(item["source_family"])
    entity_id = str(item["entity_id"])
    actor = _actor()
    payload = _json_obj(item.get("payload"))
    if not family_module_enabled(cur, company, family):
        return {"ok": True, "skipped": True, "reason": "module_disabled"}

    if family == "workforce":
        emp = None
        if _has_table(cur, "employees"):
            emp = _row(cur, "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s", (company, entity_id))
        if emp is None and payload.get("employee_key"):
            emp = dict(payload)
        if not emp:
            return {"ok": True, "skipped": True, "reason": "employee_not_found"}
        emp = dict(emp)
        for field in ("last_working_day", "effective_on", "termination_type", "end_date"):
            if payload.get(field) and not emp.get(field):
                emp[field] = payload.get(field)
        nested = _json_obj(payload.get("payload"))
        if nested:
            emp["payload"] = {**nested, **_json_obj(emp.get("payload"))}
        to_state = str(payload.get("to_state") or "").strip().lower()
        if to_state in {"terminated", "left"}:
            emp["employment_status"] = "terminated"
        return project_workforce_row(cur, company=company, emp=emp, actor=actor)

    if family == "recruiting":
        import hr_intelligence_recruiting_c3 as c3

        app = None
        if _has_table(cur, "applications"):
            app = _row(cur, "SELECT * FROM applications WHERE company_code=%s AND app_key=%s", (company, entity_id))
        if app is None and (payload.get("app_key") or payload.get("application_key")):
            app = dict(payload)
        if not app:
            return {"ok": True, "skipped": True, "reason": "application_not_found"}
        app = dict(app)
        if payload.get("to_stage") and not app.get("status"):
            app["status"] = payload.get("to_stage")
        job_key = str(app.get("position_code") or app.get("app_key") or entity_id)
        status = str(app.get("status") or app.get("to_stage") or "open").strip().lower()
        c3.upsert_requisition(
            cur,
            company_code=company,
            actor_phone=actor,
            requisition_key=job_key,
            status="filled" if status == "hired" else "open",
            reason=REASON,
            opened_at=app.get("created_at") or date.today(),
            filled_at=app.get("updated_at") if status == "hired" else None,
            job_role=app.get("position_title"),
            emit_facts=True,
        )
        return c3.upsert_application(
            cur,
            company_code=company,
            actor_phone=actor,
            application_key=str(app.get("app_key") or entity_id),
            status=status,
            reason=REASON,
            person_key=str(app.get("person_id") or app.get("phone") or app.get("app_key") or entity_id),
            requisition_key=job_key,
            job_key=job_key,
            received_at=app.get("created_at") or app.get("ingested_at"),
            hired_at=app.get("updated_at") if status == "hired" else None,
            job_role=app.get("position_title"),
        )

    if family == "attendance":
        import hr_intelligence_time_pay_c4 as c4

        employee_key, _, work_date_raw = str(entity_id).partition(":")
        work_date = _as_date(work_date_raw or payload.get("work_date"))
        day = None
        if _has_table(cur, "attendance_day_projections") and employee_key and work_date:
            extra = "AND is_current=true" if "is_current" in _columns(cur, "attendance_day_projections") else ""
            day = _row(
                cur,
                f"""
                SELECT * FROM attendance_day_projections
                 WHERE company_code=%s AND employee_key=%s AND work_date=%s {extra}
                 ORDER BY work_date DESC LIMIT 1
                """,
                (company, employee_key, work_date),
            )
        if not day:
            return {"ok": True, "skipped": True, "reason": "attendance_day_not_found"}
        return c4.upsert_attendance_day(
            cur,
            company_code=company,
            actor_phone=actor,
            employee_key=str(day["employee_key"]),
            work_date=day["work_date"],
            status=_map_attendance_status(day.get("status")),
            reason=REASON,
            exception_state=day.get("exception_state") or None,
            late_minutes=float(day.get("late_minutes") or 0),
            early_leave_minutes=float(day.get("early_leave_minutes") or 0),
            expected_work=bool(day.get("scheduled_start")),
            scheduled=bool(day.get("scheduled_start")),
            source_authority="attendance_day_projections",
        )

    if family == "leave":
        import hr_intelligence_time_pay_c4 as c4

        if not _has_table(cur, "leave_ledger"):
            return {"ok": True, "skipped": True, "reason": "leave_ledger_missing"}
        cols = _columns(cur, "leave_ledger")
        id_col = "entry_id" if "entry_id" in cols else "ledger_id"
        entry = _row(cur, f"SELECT * FROM leave_ledger WHERE company_code=%s AND {id_col}::text=%s", (company, entity_id))
        if not entry:
            return {"ok": True, "skipped": True, "reason": "leave_entry_not_found"}
        period = str(entry.get("period") or "")
        effective = _as_date(entry.get("effective_date") or entry.get("created_at"))
        if not effective:
            effective = date.fromisoformat(f"{period}-01") if len(period) == 7 else date.today()
        return c4.upsert_leave_ledger_entry(
            cur,
            company_code=company,
            actor_phone=actor,
            entry_id=str(entry.get(id_col) or entity_id),
            employee_key=str(entry["employee_key"]),
            leave_type=str(entry.get("leave_type") or "annual"),
            entry_kind=str(entry.get("entry_kind") or "accrual"),
            days=float(entry.get("days") or 0),
            effective_date=effective,
            reason=REASON,
            source_authority="leave_ledger",
        )

    if family == "shifts":
        import hr_intelligence_time_pay_c4 as c4

        if not _has_table(cur, "shift_assignments"):
            return {"ok": True, "skipped": True, "reason": "shift_assignments_missing"}
        cols = _columns(cur, "shift_assignments")
        id_col = "shift_id" if "shift_id" in cols else "assignment_id"
        shift = _row(cur, f"SELECT * FROM shift_assignments WHERE company_code=%s AND {id_col}::text=%s", (company, entity_id))
        if not shift:
            return {"ok": True, "skipped": True, "reason": "shift_not_found"}
        hours = _shift_hours(shift.get("start_time"), shift.get("end_time"))
        if hours is None:
            return {"ok": True, "skipped": True, "reason": "unknown_shift_hours"}
        return c4.upsert_shift_assignment(
            cur,
            company_code=company,
            actor_phone=actor,
            assignment_key=str(shift.get(id_col) or entity_id),
            employee_key=str(shift["employee_key"]),
            work_date=shift.get("shift_date") or shift.get("work_date"),
            scheduled_hours=hours,
            status="scheduled",
            reason=REASON,
            source_authority="shift_assignments",
        )

    if family == "performance":
        import hr_intelligence_perf_talent_c5 as c5

        subject = str(payload.get("subject_type") or item.get("entity_type") or "")
        if subject in {"kr", "key_result", "perf_key_result"} and _has_table(cur, "perf_key_results"):
            kr = _row(cur, "SELECT * FROM perf_key_results WHERE company_code=%s AND key_result_id::text=%s", (company, entity_id))
            if not kr:
                return {"ok": True, "skipped": True, "reason": "kr_not_found"}
            return c5.upsert_kr(
                cur,
                company_code=company,
                actor_phone=actor,
                kr_key=str(kr["key_result_id"]),
                objective_key=str(kr["objective_id"]),
                employee_key="company",
                status=str(kr.get("status") or "active"),
                reason=REASON,
                current=float(kr["current_value"]) if kr.get("current_value") is not None else None,
                weight=float(kr.get("weight") or 1),
            )
        if _has_table(cur, "perf_objectives"):
            obj = _row(cur, "SELECT * FROM perf_objectives WHERE company_code=%s AND objective_id::text=%s", (company, entity_id))
            if obj:
                return c5.upsert_objective(
                    cur,
                    company_code=company,
                    actor_phone=actor,
                    objective_key=str(obj["objective_id"]),
                    employee_key=str(obj.get("owner_employee_key") or "company"),
                    status=str(obj.get("status") or "draft"),
                    reason=REASON,
                    weight=float(obj.get("weight") or 1),
                    period_start=obj.get("period_start"),
                    period_end=obj.get("period_end"),
                )
            if subject in {"kr", "key_result"}:
                return {"ok": True, "skipped": True, "reason": "kr_not_found"}
            return {"ok": True, "skipped": True, "reason": "objective_not_found"}
        return {"ok": True, "skipped": True, "reason": "performance_tables_missing"}

    if family == "talent":
        import hr_intelligence_perf_talent_c5 as c5

        subject = str(payload.get("subject_type") or item.get("entity_type") or "")
        if subject in {"critical_role", "talent_critical_role"} and _has_table(cur, "talent_critical_roles"):
            role = _row(cur, "SELECT * FROM talent_critical_roles WHERE company_code=%s AND critical_role_id::text=%s", (company, entity_id))
            if not role:
                return {"ok": True, "skipped": True, "reason": "critical_role_not_found"}
            return c5.upsert_critical_role(
                cur,
                company_code=company,
                actor_phone=actor,
                role_key=str(role["critical_role_id"]),
                title=str(role.get("title_en") or role.get("canonical_role_key") or "role"),
                active=str(role.get("status") or "active") == "active",
                reason=REASON,
            )
        if subject in {"nomination", "successor_nomination", "talent_nomination"} and _has_table(cur, "talent_successor_nominations"):
            nom = _row(cur, "SELECT * FROM talent_successor_nominations WHERE company_code=%s AND nomination_id::text=%s", (company, entity_id))
            if not nom:
                return {"ok": True, "skipped": True, "reason": "nomination_not_found"}
            return c5.upsert_nomination(
                cur,
                company_code=company,
                actor_phone=actor,
                nomination_key=str(nom["nomination_id"]),
                role_key=str(nom["critical_role_id"]),
                employee_key=str(nom["employee_key"]),
                readiness=str(nom.get("readiness") or "unassessed"),
                status=str(nom.get("status") or "active"),
                reason=REASON,
            )
        if _has_table(cur, "talent_profiles"):
            profile = _row(cur, "SELECT employee_key FROM talent_profiles WHERE company_code=%s AND employee_key=%s", (company, entity_id))
            if profile:
                return c5.upsert_talent_profile(
                    cur,
                    company_code=company,
                    actor_phone=actor,
                    employee_key=str(profile["employee_key"]),
                    active=True,
                    reason=REASON,
                )
        return {"ok": True, "skipped": True, "reason": "talent_subject_not_found"}

    return {"ok": False, "error": "unsupported_source_family", "source_family": family}


def _backoff_seconds(attempts: int) -> int:
    return min(900, 15 * (2 ** max(0, attempts - 1)))


def refresh_family_freshness(cur: Any, company: str, family: str, *, error: str | None = None) -> dict[str, Any]:
    ensure_hr_intelligence_projection_schema(cur)
    pending = _row(
        cur,
        """
        SELECT
          COUNT(*) FILTER (WHERE status IN ('queued','processing','failed')) AS pending,
          COUNT(*) FILTER (WHERE status='dead') AS dead,
          MAX(created_at) FILTER (WHERE status IN ('queued','processing','failed')) AS oldest_pending,
          MAX(processed_at) FILTER (WHERE status='done') AS last_done
          FROM hr_intelligence_projection_outbox
         WHERE company_code=%s AND source_family=%s
        """,
        (company, family),
    ) or {}
    if family == PAYROLL_FAMILY:
        status = "unavailable"
        guaranteed = False
        lag = 0
        reason = "payroll_not_sealed"
    elif not family_module_enabled(cur, company, family):
        status = "unavailable"
        guaranteed = False
        lag = 0
        reason = "source_module_disabled"
    else:
        reason = error
        last_done = _as_dt(pending.get("last_done"))
        oldest_pending = _as_dt(pending.get("oldest_pending"))
        pending_n = int(pending.get("pending") or 0)
        dead_n = int(pending.get("dead") or 0)
        now = _utc_now()
        if error or dead_n:
            status = "error"
            lag = int((now - (oldest_pending or last_done or now)).total_seconds()) if (oldest_pending or last_done) else 0
            guaranteed = False
        elif pending_n:
            lag = int((now - oldest_pending).total_seconds()) if oldest_pending else 0
            status = "stale" if lag >= stale_after_seconds() else "current"
            guaranteed = False
        elif last_done:
            lag = 0
            status = "current"
            guaranteed = True
        else:
            existing = _row(
                cur,
                "SELECT data_as_of, last_reconciled_at FROM hr_intelligence_source_freshness WHERE company_code=%s AND source_family=%s",
                (company, family),
            ) or {}
            as_of = _as_dt(existing.get("data_as_of") or existing.get("last_reconciled_at"))
            if as_of:
                lag = 0
                status = "current"
                guaranteed = True
            else:
                lag = 0
                status = "never"
                guaranteed = False
    data_as_of = pending.get("last_done")
    cur.execute(
        """
        INSERT INTO hr_intelligence_source_freshness (
          company_code, source_family, data_as_of, last_projected_at, lag_seconds,
          status, guaranteed_current, pending_outbox_count, failed_outbox_count,
          last_error, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, source_family) DO UPDATE SET
          data_as_of=COALESCE(EXCLUDED.data_as_of, hr_intelligence_source_freshness.data_as_of),
          last_projected_at=COALESCE(EXCLUDED.last_projected_at, hr_intelligence_source_freshness.last_projected_at),
          lag_seconds=EXCLUDED.lag_seconds,
          status=EXCLUDED.status,
          guaranteed_current=EXCLUDED.guaranteed_current,
          pending_outbox_count=EXCLUDED.pending_outbox_count,
          failed_outbox_count=EXCLUDED.failed_outbox_count,
          last_error=EXCLUDED.last_error,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            family,
            data_as_of,
            data_as_of,
            lag,
            status,
            guaranteed,
            int(pending.get("pending") or 0),
            int(pending.get("dead") or 0),
            reason,
        ),
    )
    return dict(cur.fetchone())


def drain_outbox(cur: Any, *, company_code: str | None = None, limit: int = 200) -> dict[str, Any]:
    ensure_hr_intelligence_projection_schema(cur)
    params: list[Any] = []
    company_sql = ""
    if company_code:
        company_sql = "AND company_code=%s"
        params.append(c1.company_code_norm(company_code))
    params.append(limit)
    sql = f"""
        SELECT * FROM hr_intelligence_projection_outbox
         WHERE status IN ('queued','failed')
           AND next_attempt_at <= now()
           {company_sql}
         ORDER BY created_at ASC
         LIMIT %s
    """
    items: list[dict[str, Any]] = []
    locked = False
    try:
        cur.execute("SAVEPOINT intel_drain")
        locked = True
        items = _rows(cur, sql + " FOR UPDATE SKIP LOCKED", tuple(params))
        cur.execute("RELEASE SAVEPOINT intel_drain")
    except Exception:
        if locked:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT intel_drain")
            except Exception:
                pass
        items = _rows(cur, sql, tuple(params))
    processed = 0
    failed = 0
    skipped = 0
    touched: set[tuple[str, str]] = set()
    for item in items:
        oid = item["outbox_id"]
        company = str(item["company_code"])
        family = str(item["source_family"])
        touched.add((company, family))
        sp = "ob_" + str(oid).replace("-", "")[:24]
        cur.execute(f"SAVEPOINT {sp}")
        cur.execute(
            "UPDATE hr_intelligence_projection_outbox SET status='processing', attempts=attempts+1 WHERE outbox_id=%s AND status IN ('queued','failed')",
            (oid,),
        )
        try:
            result = apply_outbox_item(cur, dict(item))
        except Exception as exc:
            result = {"ok": False, "error": str(exc)[:400]}
        if result.get("ok"):
            cur.execute(f"RELEASE SAVEPOINT {sp}")
            cur.execute(
                """
                UPDATE hr_intelligence_projection_outbox
                   SET status='done', last_error=NULL, processed_at=now()
                 WHERE outbox_id=%s
                """,
                (oid,),
            )
            processed += 1
            if result.get("skipped"):
                skipped += 1
        else:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            attempts = int(item.get("attempts") or 0) + 1
            dead = attempts >= max_attempts()
            cur.execute(
                """
                UPDATE hr_intelligence_projection_outbox
                   SET status=%s, last_error=%s, next_attempt_at=%s, attempts=%s
                 WHERE outbox_id=%s
                """,
                (
                    "dead" if dead else "failed",
                    str(result.get("error") or "projection_failed")[:500],
                    _utc_now() + timedelta(seconds=_backoff_seconds(attempts)),
                    attempts,
                    oid,
                ),
            )
            failed += 1
    for company, family in touched:
        refresh_family_freshness(cur, company, family)
    return {"ok": failed == 0, "processed": processed, "failed": failed, "skipped": skipped, "seen": len(items)}


def _mark_reconciled(cur: Any, company: str, family: str) -> None:
    now = _utc_now()
    cur.execute(
        """
        INSERT INTO hr_intelligence_source_freshness (
          company_code, source_family, data_as_of, last_reconciled_at, last_projected_at,
          lag_seconds, status, guaranteed_current, updated_at
        ) VALUES (%s,%s,%s,%s,%s,0,'current',true,now())
        ON CONFLICT (company_code, source_family) DO UPDATE SET
          data_as_of=COALESCE(EXCLUDED.data_as_of, hr_intelligence_source_freshness.data_as_of, now()),
          last_reconciled_at=EXCLUDED.last_reconciled_at,
          last_projected_at=COALESCE(hr_intelligence_source_freshness.last_projected_at, EXCLUDED.last_projected_at),
          lag_seconds=0,
          status=CASE WHEN hr_intelligence_source_freshness.status='error' THEN 'error' ELSE 'current' END,
          guaranteed_current=CASE WHEN hr_intelligence_source_freshness.status='error' THEN false ELSE true END,
          updated_at=now()
        """,
        (company, family, now, now, now),
    )
    refresh_family_freshness(cur, company, family)


def reconcile_company(cur: Any, company_code: str, *, families: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Safety net: enqueue current SoT identities that the event tail may have missed."""
    company = c1.company_code_norm(company_code)
    ensure_hr_intelligence_projection_schema(cur)
    wanted = families or SOURCE_FAMILIES
    out: dict[str, Any] = {}
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")

    def _enq(family: str, entity_type: str, entity_id: Any) -> None:
        enqueue(
            cur,
            company_code=company,
            source_family=family,
            entity_type=entity_type,
            entity_id=str(entity_id),
            event_ref=f"reconcile:{stamp}:{family}:{entity_id}",
        )

    if "workforce" in wanted and _has_table(cur, "employees"):
        keys = _rows(cur, "SELECT employee_key FROM employees WHERE company_code=%s", (company,))
        for row in keys:
            _enq("workforce", "employee", row["employee_key"])
        out["workforce"] = len(keys)
    if "recruiting" in wanted and _has_table(cur, "applications"):
        keys = _rows(cur, "SELECT app_key FROM applications WHERE company_code=%s", (company,))
        for row in keys:
            _enq("recruiting", "application", row["app_key"])
        out["recruiting"] = len(keys)
    if "attendance" in wanted and _has_table(cur, "attendance_day_projections"):
        extra = "AND is_current=true" if "is_current" in _columns(cur, "attendance_day_projections") else ""
        days = _rows(
            cur,
            f"SELECT employee_key, work_date FROM attendance_day_projections WHERE company_code=%s {extra}",
            (company,),
        )
        for row in days:
            _enq("attendance", "attendance_day", f"{row['employee_key']}:{row['work_date']}")
        out["attendance"] = len(days)
    if "leave" in wanted and _has_table(cur, "leave_ledger"):
        cols = _columns(cur, "leave_ledger")
        id_col = "entry_id" if "entry_id" in cols else "ledger_id"
        entries = _rows(cur, f"SELECT {id_col} AS entry_id FROM leave_ledger WHERE company_code=%s", (company,))
        for row in entries:
            _enq("leave", "leave_entry", row["entry_id"])
        out["leave"] = len(entries)
    if "shifts" in wanted and _has_table(cur, "shift_assignments"):
        cols = _columns(cur, "shift_assignments")
        id_col = "shift_id" if "shift_id" in cols else "assignment_id"
        shifts = _rows(cur, f"SELECT {id_col} AS shift_id FROM shift_assignments WHERE company_code=%s", (company,))
        for row in shifts:
            _enq("shifts", "shift_assignment", row["shift_id"])
        out["shifts"] = len(shifts)
    if "performance" in wanted and _has_table(cur, "perf_objectives"):
        objs = _rows(cur, "SELECT objective_id FROM perf_objectives WHERE company_code=%s", (company,))
        for row in objs:
            _enq("performance", "objective", row["objective_id"])
        if _has_table(cur, "perf_key_results"):
            krs = _rows(cur, "SELECT key_result_id FROM perf_key_results WHERE company_code=%s", (company,))
            for row in krs:
                enqueue(
                    cur,
                    company_code=company,
                    source_family="performance",
                    entity_type="kr",
                    entity_id=str(row["key_result_id"]),
                    event_ref=f"reconcile:{stamp}:kr:{row['key_result_id']}",
                    payload={"subject_type": "kr"},
                )
            out["performance_krs"] = len(krs)
        out["performance"] = len(objs)
    if "talent" in wanted:
        n = 0
        if _has_table(cur, "talent_profiles"):
            for row in _rows(cur, "SELECT employee_key FROM talent_profiles WHERE company_code=%s", (company,)):
                _enq("talent", "talent_profile", row["employee_key"])
                n += 1
        if _has_table(cur, "talent_critical_roles"):
            for row in _rows(cur, "SELECT critical_role_id FROM talent_critical_roles WHERE company_code=%s", (company,)):
                enqueue(
                    cur,
                    company_code=company,
                    source_family="talent",
                    entity_type="critical_role",
                    entity_id=str(row["critical_role_id"]),
                    event_ref=f"reconcile:{stamp}:role:{row['critical_role_id']}",
                    payload={"subject_type": "critical_role"},
                )
                n += 1
        if _has_table(cur, "talent_successor_nominations"):
            for row in _rows(cur, "SELECT nomination_id FROM talent_successor_nominations WHERE company_code=%s", (company,)):
                enqueue(
                    cur,
                    company_code=company,
                    source_family="talent",
                    entity_type="nomination",
                    entity_id=str(row["nomination_id"]),
                    event_ref=f"reconcile:{stamp}:nom:{row['nomination_id']}",
                    payload={"subject_type": "nomination"},
                )
                n += 1
        out["talent"] = n
    drained = drain_outbox(cur, company_code=company, limit=5000)
    for family in wanted:
        _mark_reconciled(cur, company, family)
    refresh_payroll_freshness(cur, company)
    return {"ok": True, "company_code": company, "enqueued": out, "drain": drained}


def refresh_payroll_freshness(cur: Any, company: str) -> dict[str, Any]:
    ensure_hr_intelligence_projection_schema(cur)
    cur.execute(
        """
        INSERT INTO hr_intelligence_source_freshness (
          company_code, source_family, status, guaranteed_current, lag_seconds,
          last_error, updated_at
        ) VALUES (%s,'payroll','unavailable',false,0,'payroll_not_sealed',now())
        ON CONFLICT (company_code, source_family) DO UPDATE SET
          status='unavailable',
          guaranteed_current=false,
          last_error='payroll_not_sealed',
          updated_at=now()
        RETURNING *
        """,
        (company,),
    )
    return dict(cur.fetchone())


def rebuild_company(cur: Any, company_code: str, *, family: str | None = None, reason: str = REASON) -> dict[str, Any]:
    """Controlled full rebuild/reconciliation for recovery or migrations."""
    company = c1.company_code_norm(company_code)
    actor = _actor()
    families = (family,) if family else SOURCE_FAMILIES
    reconciled = reconcile_company(cur, company, families=families)
    rebuilt: dict[str, Any] = {}
    if "workforce" in families:
        import hr_intelligence_workforce_c2 as c2

        rebuilt["workforce"] = c2.rebuild_workforce_facts(cur, company_code=company, actor_phone=actor, reason=reason)
    if "recruiting" in families:
        import hr_intelligence_recruiting_c3 as c3

        rebuilt["recruiting"] = c3.rebuild_recruiting_facts(cur, company_code=company, actor_phone=actor, reason=reason)
    if any(item in families for item in ("attendance", "leave", "shifts")):
        import hr_intelligence_time_pay_c4 as c4

        rebuilt["time_pay"] = c4.rebuild_time_pay_facts(cur, company_code=company, actor_phone=actor, reason=reason)
    if any(item in families for item in ("performance", "talent")):
        import hr_intelligence_perf_talent_c5 as c5

        rebuilt["perf_talent"] = c5.rebuild_perf_talent_facts(cur, company_code=company, actor_phone=actor, reason=reason)
    now = _utc_now()
    for item in families:
        cur.execute(
            """
            UPDATE hr_intelligence_source_freshness
               SET last_rebuild_at=%s, updated_at=now()
             WHERE company_code=%s AND source_family=%s
            """,
            (now, company, item),
        )
    refresh_payroll_freshness(cur, company)
    return {"ok": True, "company_code": company, "reconcile": reconciled, "rebuild": rebuilt}


def _due_for_reconcile(cur: Any, company: str) -> bool:
    row = _row(
        cur,
        "SELECT MAX(last_reconciled_at) AS last_reconciled_at FROM hr_intelligence_source_freshness WHERE company_code=%s",
        (company,),
    )
    last = _as_dt((row or {}).get("last_reconciled_at"))
    if not last:
        return True
    return (_utc_now() - last).total_seconds() >= reconcile_every_seconds()


def run_projection_pass(
    cur: Any,
    *,
    company_code: str | None = None,
    force_reconcile: bool = False,
    rebuild: bool = False,
    family: str | None = None,
) -> dict[str, Any]:
    ensure_hr_intelligence_projection_schema(cur)
    companies = [c1.company_code_norm(company_code)] if company_code else entitled_companies(cur)
    results = []
    for company in companies:
        if not company:
            continue
        ingest = ingest_company_events(cur, company)
        drain = drain_outbox(cur, company_code=company, limit=2000)
        recon = None
        rebuilt = None
        if rebuild:
            rebuilt = rebuild_company(cur, company, family=family)
        elif force_reconcile or _due_for_reconcile(cur, company):
            recon = reconcile_company(cur, company, families=(family,) if family else None)
        refresh_payroll_freshness(cur, company)
        results.append(
            {
                "company_code": company,
                "ingest": ingest,
                "drain": drain,
                "reconcile": recon,
                "rebuild": rebuilt,
                "freshness": freshness_payload(cur, company),
            }
        )
    return {"ok": True, "companies": results}


def freshness_row(cur: Any, company: str, family: str) -> dict[str, Any]:
    ensure_hr_intelligence_projection_schema(cur)
    row = _row(
        cur,
        "SELECT * FROM hr_intelligence_source_freshness WHERE company_code=%s AND source_family=%s",
        (c1.company_code_norm(company), family),
    )
    if not row:
        if family == PAYROLL_FAMILY:
            return refresh_payroll_freshness(cur, c1.company_code_norm(company))
        return {
            "company_code": c1.company_code_norm(company),
            "source_family": family,
            "status": "never",
            "guaranteed_current": False,
            "data_as_of": None,
            "lag_seconds": 0,
        }
    return row


def freshness_payload(cur: Any, company_code: str) -> dict[str, Any]:
    company = c1.company_code_norm(company_code)
    ensure_hr_intelligence_projection_schema(cur)
    rows = _rows(
        cur,
        "SELECT * FROM hr_intelligence_source_freshness WHERE company_code=%s ORDER BY source_family",
        (company,),
    )
    families = {str(row["source_family"]): _public_freshness(row) for row in rows}
    for family in SOURCE_FAMILIES + (PAYROLL_FAMILY,):
        families.setdefault(family, _public_freshness(freshness_row(cur, company, family)))
    statuses = [item.get("status") for item in families.values() if item.get("source_family") != PAYROLL_FAMILY]
    if "error" in statuses:
        overall = "error"
    elif "stale" in statuses:
        overall = "stale"
    elif "never" in statuses:
        overall = "stale"
    else:
        overall = "current"
    return {
        "mode": "near_real_time_spine",
        "company_code": company,
        "status": overall,
        "guaranteed_current": overall == "current" and all(
            item.get("guaranteed_current") for key, item in families.items() if key != PAYROLL_FAMILY
        ),
        "evaluated_at": _iso(_utc_now()),
        "stale_after_seconds": stale_after_seconds(),
        "families": families,
        "payroll_money_current": False,
        "rebuild_path": "hr-intelligence-projection-worker.py --rebuild COMPANY",
        "no_frontend_rebuild": True,
    }


def _public_freshness(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "never")
    return {
        "source_family": row.get("source_family"),
        "data_as_of": _iso(row.get("data_as_of")),
        "last_source_event_at": _iso(row.get("last_source_event_at")),
        "last_projected_at": _iso(row.get("last_projected_at")),
        "last_reconciled_at": _iso(row.get("last_reconciled_at")),
        "last_rebuild_at": _iso(row.get("last_rebuild_at")),
        "lag_seconds": int(row.get("lag_seconds") or 0),
        "status": status,
        "guaranteed_current": bool(row.get("guaranteed_current")) and status == "current",
        "pending_outbox_count": int(row.get("pending_outbox_count") or 0),
        "failed_outbox_count": int(row.get("failed_outbox_count") or 0),
        "last_error": row.get("last_error"),
    }


def freshness_for_semantic_key(cur: Any, *, company_code: str, semantic_key: str) -> dict[str, Any]:
    family = family_for_semantic_key(semantic_key)
    row = _public_freshness(freshness_row(cur, company_code, family))
    row.update(
        {
            "mode": "near_real_time_spine",
            "evaluated_at": _iso(_utc_now()),
            "semantic_key": semantic_key,
            "source_family": family,
        }
    )
    if family == PAYROLL_FAMILY:
        row["guaranteed_current"] = False
        row["status"] = "unavailable"
        row["last_error"] = "payroll_not_sealed"
    return row
