"""Phase A slice 2 — unified task ontology + SLA/reminder policy.

Extends canonical `hr_tasks` (no second inbox SoT).
Dark by default: separate company-scoped flags for tasks and SLA.
Breach creates an `sla_breach` hr_task when tasks gate is also enabled.
Reminders emit audit events only in this slice (no live notification fan-out).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WORKFLOW_TASK_SLA_SCHEMA_VERSION = "1.0.0"

_ON_VALUES = {"1", "true", "yes", "on"}

TASK_STATUSES = frozenset({"open", "done", "dismissed"})
TASK_TERMINAL = frozenset({"done", "dismissed"})

CLOCK_STATUSES = frozenset({"running", "breached", "satisfied", "cancelled"})
CLOCK_TRANSITIONS: dict[str, frozenset[str]] = {
    "running": frozenset({"breached", "satisfied", "cancelled"}),
    # Post-breach closure is explicit/audited (deterministic; no silent reopen).
    "breached": frozenset({"satisfied", "cancelled"}),
    "satisfied": frozenset(),
    "cancelled": frozenset(),
}

_INVARIANTS_SQL_PATH = (
    Path(__file__).resolve().parent / "ops" / "sql" / "workflow_task_sla_phase_a_v1b_invariants.sql"
)

CANONICAL_TASK_TYPES: tuple[str, ...] = (
    "requisition_approval",
    "preboard_item",
    "preboard_readiness",
    "probation_milestone",
    "probation_decision",
    "sla_breach",
)

EVENT_TYPES = frozenset(
    {
        "task_created",
        "task_resolved",
        "task_gate_denied",
        "sla_policy_upserted",
        "sla_clock_started",
        "sla_reminder_due",
        "sla_breached",
        "sla_satisfied",
        "sla_cancelled",
        "sla_gate_denied",
        "sla_idempotent_replay",
        "sla_post_breach_closure",
        "concurrency_conflict",
    }
)

_SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "workflow_task_sla_phase_a_v1.sql"


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Store due_at / SLA timestamps canonically in UTC. Surfaces localize later."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def can_transition(machine: dict[str, frozenset[str]], from_status: str, to_status: str) -> bool:
    return to_status in machine.get(from_status, frozenset())


def workflow_tasks_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_WORKFLOW_TASKS", "off")


def workflow_sla_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_WORKFLOW_SLA", "off")


def _allowlist(env_name: str) -> set[str]:
    raw = str(os.environ.get(env_name, "") or "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def workflow_tasks_company_allowlist() -> set[str]:
    return _allowlist("WATHEFNI_WORKFLOW_TASKS_COMPANIES")


def workflow_sla_company_allowlist() -> set[str]:
    return _allowlist("WATHEFNI_WORKFLOW_SLA_COMPANIES")


def ensure_workflow_task_sla_schema(cur: Any) -> None:
    cur.execute(_SCHEMA_SQL_PATH.read_text(encoding="utf-8"))
    if _INVARIANTS_SQL_PATH.is_file():
        cur.execute(_INVARIANTS_SQL_PATH.read_text(encoding="utf-8"))


def seed_task_settings(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    if not company:
        return
    cur.execute(
        """
        INSERT INTO workflow_task_settings (company_code, enabled)
        VALUES (%s, false)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def seed_sla_settings(cur: Any, company_code: str) -> None:
    company = company_code_norm(company_code)
    if not company:
        return
    cur.execute(
        """
        INSERT INTO workflow_sla_settings (company_code, enabled, reminders_enabled)
        VALUES (%s, false, false)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def set_task_enabled(cur: Any, company_code: str, *, enabled: bool) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO workflow_task_settings (company_code, enabled, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (company_code) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now()
        RETURNING company_code, enabled, updated_at
        """,
        (company, bool(enabled)),
    )
    return dict(cur.fetchone())


def set_sla_enabled(
    cur: Any, company_code: str, *, enabled: bool, reminders_enabled: bool | None = None
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    seed_sla_settings(cur, company)
    if reminders_enabled is None:
        cur.execute(
            """
            UPDATE workflow_sla_settings
               SET enabled=%s, updated_at=now()
             WHERE company_code=%s
            RETURNING company_code, enabled, reminders_enabled, updated_at
            """,
            (bool(enabled), company),
        )
    else:
        cur.execute(
            """
            UPDATE workflow_sla_settings
               SET enabled=%s, reminders_enabled=%s, updated_at=now()
             WHERE company_code=%s
            RETURNING company_code, enabled, reminders_enabled, updated_at
            """,
            (bool(enabled), bool(reminders_enabled), company),
        )
    return dict(cur.fetchone())


def tasks_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required"}
    if not workflow_tasks_runtime_flag_on():
        return {"ok": False, "enabled": False, "error": "workflow_tasks_disabled", "gate": "runtime_flag"}
    allow = workflow_tasks_company_allowlist()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_tasks_company_not_allowlisted",
            "gate": "company_allowlist",
        }
    seed_task_settings(cur, company)
    cur.execute(
        "SELECT enabled FROM workflow_task_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    enabled = bool(dict(row).get("enabled")) if row else False
    if not enabled:
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_tasks_company_disabled",
            "gate": "company_setting",
        }
    return {"ok": True, "enabled": True, "company_code": company}


def sla_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required"}
    if not workflow_sla_runtime_flag_on():
        return {"ok": False, "enabled": False, "error": "workflow_sla_disabled", "gate": "runtime_flag"}
    allow = workflow_sla_company_allowlist()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_sla_company_not_allowlisted",
            "gate": "company_allowlist",
        }
    seed_sla_settings(cur, company)
    cur.execute(
        "SELECT enabled, reminders_enabled FROM workflow_sla_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    d = dict(row) if row else {"enabled": False, "reminders_enabled": False}
    if not d.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "workflow_sla_company_disabled",
            "gate": "company_setting",
            "reminders_enabled": bool(d.get("reminders_enabled")),
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company,
        "reminders_enabled": bool(d.get("reminders_enabled")),
    }


def _insert_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    task_id: str | None = None,
    clock_id: str | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_task_sla_events (
          event_id, company_code, task_id, clock_id, event_type,
          actor_user_id, actor_phone, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            event_id,
            company_code_norm(company_code),
            task_id,
            clock_id,
            event_type,
            actor_user_id,
            digits_phone(actor_phone) or None,
            json.dumps(payload or {}),
        ),
    )
    return event_id


def list_task_types(cur: Any, *, active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM workflow_task_type_catalogue"
    if active_only:
        sql += " WHERE active=true"
    sql += " ORDER BY task_type"
    cur.execute(sql)
    return [dict(r) for r in (cur.fetchall() or [])]


def is_canonical_task_type(task_type: str) -> bool:
    return str(task_type or "").strip() in CANONICAL_TASK_TYPES


def find_open_workflow_task(
    cur: Any,
    *,
    company_code: str,
    task_type: str,
    subject_type: str,
    subject_id: str,
) -> dict[str, Any] | None:
    """Canonical open task for a logical subject/action (tenant-scoped)."""
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT task_id, company_code, employee_key, task_type, source, title, detail,
               status, priority, subject_type, subject_id, due_at, sla_clock_id,
               metadata, row_version, created_at, updated_at
          FROM hr_tasks
         WHERE company_code=%s
           AND task_type=%s
           AND subject_type=%s
           AND subject_id=%s
           AND status='open'
         ORDER BY created_at ASC
         LIMIT 1
        """,
        (company, str(task_type).strip(), str(subject_type).strip(), str(subject_id).strip()),
    )
    row = cur.fetchone()
    return _task_row(dict(row)) if row else None


def create_workflow_task(
    cur: Any,
    *,
    company_code: str,
    task_type: str,
    title: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    detail: str | None = None,
    priority: str = "normal",
    employee_key: str | None = None,
    assigned_to_user_id: str | None = None,
    due_at: datetime | None = None,
    sla_clock_id: str | None = None,
    source: str = "workflow_task_sla",
    metadata: dict[str, Any] | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    gate = tasks_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        _insert_event(
            cur,
            company_code=company_code or "UNKNOWN",
            event_type="task_gate_denied",
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"op": "create_workflow_task", **{k: gate.get(k) for k in ("error", "gate")}},
        )
        return gate

    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "error": "company_required"}
    tt = str(task_type or "").strip()
    if not is_canonical_task_type(tt):
        return {"ok": False, "error": "task_type_unknown", "task_type": tt}
    title_n = str(title or "").strip()
    if not title_n:
        return {"ok": False, "error": "title_required"}

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            """
            SELECT task_id, company_code, task_type, status, subject_type, subject_id,
                   title, due_at, sla_clock_id, metadata, row_version, created_at, updated_at,
                   employee_key, source, detail, priority
              FROM hr_tasks
             WHERE company_code=%s
               AND metadata->>'idempotency_key'=%s
             LIMIT 1
            """,
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            row = dict(existing)
            return {"ok": True, "replayed": True, "task": _task_row(row)}

    meta = dict(metadata or {})
    if idem:
        meta["idempotency_key"] = idem
    meta["ontology"] = "workflow_task_sla_v1"
    meta["mutates_subject_on_resolve"] = False

    # hr_tasks.assigned_to_user_id is uuid; non-uuid actor keys live in metadata.
    assignee_uuid = None
    assignee_raw = str(assigned_to_user_id or "").strip() or None
    if assignee_raw:
        try:
            assignee_uuid = str(uuid.UUID(assignee_raw))
        except ValueError:
            meta["assigned_to_user_key"] = assignee_raw

    # Prefer catalogue subject_type when not provided
    if not subject_type:
        cur.execute(
            "SELECT subject_type FROM workflow_task_type_catalogue WHERE task_type=%s",
            (tt,),
        )
        crow = cur.fetchone()
        if crow and crow.get("subject_type"):
            subject_type = crow["subject_type"]

    subject_type_n = str(subject_type or "").strip() or None
    subject_id_n = str(subject_id or "").strip() or None
    # Ontology tasks are always tenant-scoped to a logical subject (fail closed).
    if not subject_type_n or not subject_id_n:
        return {
            "ok": False,
            "error": "subject_required",
            "message": "subject_type and subject_id are required for workflow tasks",
        }

    # One canonical open task per logical subject/action — retries must not duplicate.
    open_existing = find_open_workflow_task(
        cur,
        company_code=company,
        task_type=tt,
        subject_type=subject_type_n,
        subject_id=subject_id_n,
    )
    if open_existing:
        return {"ok": True, "replayed": True, "deduped_open": True, "task": open_existing}

    due_utc = ensure_utc(due_at)

    task_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_tasks (
          task_id, company_code, employee_key, task_type, source, title, detail,
          status, priority, assigned_to_user_id, subject_type, subject_id,
          due_at, sla_clock_id, metadata, row_version
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s,%s,%s,%s::jsonb,1
        )
        RETURNING task_id, company_code, employee_key, task_type, source, title, detail,
                  status, priority, subject_type, subject_id, due_at, sla_clock_id,
                  metadata, row_version, created_at, updated_at
        """,
        (
            task_id,
            company,
            employee_key,
            tt,
            source,
            title_n,
            detail,
            str(priority or "normal"),
            assignee_uuid,
            subject_type_n,
            subject_id_n,
            due_utc,
            sla_clock_id,
            json.dumps(meta),
        ),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="task_created",
        task_id=task_id,
        clock_id=sla_clock_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={
            "task_type": tt,
            "subject_type": subject_type_n,
            "subject_id": subject_id_n,
            "mutates_subject_on_resolve": False,
        },
    )
    return {"ok": True, "replayed": False, "task": _task_row(row)}


def create_task_from_approval(
    cur: Any,
    *,
    company_code: str,
    task_type: str,
    title: str,
    approval_instance_id: str,
    subject_type: str,
    subject_id: str,
    approval_step_id: str | None = None,
    due_at: datetime | None = None,
    priority: str = "normal",
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an inbox task linked to the originating approval instance/subject."""
    instance_id = str(approval_instance_id or "").strip()
    if not instance_id:
        return {"ok": False, "error": "approval_instance_id_required"}
    meta = dict(metadata or {})
    meta["approval_instance_id"] = instance_id
    if approval_step_id:
        meta["approval_step_id"] = str(approval_step_id).strip()
    meta["origin"] = "workflow_approvals"
    return create_workflow_task(
        cur,
        company_code=company_code,
        task_type=task_type,
        title=title,
        subject_type=subject_type,
        subject_id=subject_id,
        due_at=due_at,
        priority=priority,
        source="workflow_approvals",
        metadata=meta,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        idempotency_key=f"approval-task:{instance_id}:{task_type}:{subject_id}",
    )


def _task_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "task_id": str(row["task_id"]),
        "company_code": row["company_code"],
        "employee_key": row.get("employee_key"),
        "task_type": row["task_type"],
        "source": row.get("source"),
        "title": row.get("title"),
        "detail": row.get("detail"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "subject_type": row.get("subject_type"),
        "subject_id": row.get("subject_id"),
        "due_at": row.get("due_at"),
        "sla_clock_id": str(row["sla_clock_id"]) if row.get("sla_clock_id") else None,
        "metadata": meta or {},
        "row_version": int(row.get("row_version") or 1),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def resolve_workflow_task(
    cur: Any,
    *,
    company_code: str,
    task_id: str,
    status: str = "done",
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = tasks_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    status_n = str(status or "done").strip().lower()
    if status_n not in TASK_TERMINAL:
        return {"ok": False, "error": "invalid_status"}

    cur.execute(
        """
        SELECT task_id, company_code, status, row_version, task_type, subject_type, subject_id
          FROM hr_tasks
         WHERE company_code=%s AND task_id=%s
         LIMIT 1
        """,
        (company, str(task_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "task_not_found"}
    task = dict(row)
    if expected_row_version is not None and int(task.get("row_version") or 1) != int(expected_row_version):
        _insert_event(
            cur,
            company_code=company,
            event_type="concurrency_conflict",
            task_id=str(task_id),
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={
                "expected_row_version": expected_row_version,
                "actual_row_version": task.get("row_version"),
            },
        )
        return {"ok": False, "error": "concurrency_conflict"}
    if str(task.get("status")) in TASK_TERMINAL:
        return {"ok": False, "error": "task_terminal", "status": task.get("status")}

    cur.execute(
        """
        UPDATE hr_tasks
           SET status=%s,
               resolved_by_phone=%s,
               resolved_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE task_id=%s AND company_code=%s AND row_version=%s
        RETURNING task_id, company_code, employee_key, task_type, source, title, detail,
                  status, priority, subject_type, subject_id, due_at, sla_clock_id,
                  metadata, row_version, created_at, updated_at
        """,
        (
            status_n,
            digits_phone(actor_phone) or None,
            str(task_id),
            company,
            int(task.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type="task_resolved",
        task_id=str(task_id),
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={
            "status": status_n,
            # Resolve closes the inbox item only. Business-subject transitions
            # require an explicit owning workflow — never silently mutated here.
            "mutates_subject": False,
            "subject_type": task.get("subject_type"),
            "subject_id": task.get("subject_id"),
        },
    )
    return {"ok": True, "task": _task_row(dict(updated)), "mutates_subject": False}


def get_task_for_company(cur: Any, *, company_code: str, task_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT task_id, company_code, employee_key, task_type, source, title, detail,
               status, priority, subject_type, subject_id, due_at, sla_clock_id,
               metadata, row_version, created_at, updated_at
          FROM hr_tasks
         WHERE company_code=%s AND task_id=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), str(task_id)),
    )
    row = cur.fetchone()
    return _task_row(dict(row)) if row else None


# --- SLA ---------------------------------------------------------------------


def upsert_sla_policy(
    cur: Any,
    *,
    company_code: str,
    subject_type: str,
    name: str,
    due_in_seconds: int,
    priority: str = "normal",
    remind_before_seconds: int | None = None,
    escalate_to_role: str | None = None,
    escalate_to_user_id: str | None = None,
    escalate_task_type: str = "sla_breach",
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    gate = sla_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        _insert_event(
            cur,
            company_code=company_code or "UNKNOWN",
            event_type="sla_gate_denied",
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"op": "upsert_sla_policy", **{k: gate.get(k) for k in ("error", "gate")}},
        )
        return gate

    company = company_code_norm(company_code)
    subject = str(subject_type or "").strip()
    if not subject:
        return {"ok": False, "error": "subject_type_required"}
    if int(due_in_seconds) <= 0:
        return {"ok": False, "error": "due_in_seconds_invalid"}
    pri = str(priority or "normal").strip().lower()
    if pri not in {"low", "normal", "high", "urgent"}:
        return {"ok": False, "error": "priority_invalid"}
    if remind_before_seconds is not None and int(remind_before_seconds) >= int(due_in_seconds):
        return {"ok": False, "error": "remind_before_invalid"}
    esc_tt = str(escalate_task_type or "sla_breach").strip()
    if esc_tt not in CANONICAL_TASK_TYPES:
        return {"ok": False, "error": "escalate_task_type_unknown"}

    cur.execute(
        """
        UPDATE workflow_sla_policies
           SET active=false, updated_at=now()
         WHERE company_code=%s AND subject_type=%s AND priority=%s AND active=true
        """,
        (company, subject, pri),
    )
    policy_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_sla_policies (
          policy_id, company_code, subject_type, name, priority, due_in_seconds,
          remind_before_seconds, escalate_to_role, escalate_to_user_id,
          escalate_task_type, active, version
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,1)
        RETURNING *
        """,
        (
            policy_id,
            company,
            subject,
            str(name or subject).strip(),
            pri,
            int(due_in_seconds),
            int(remind_before_seconds) if remind_before_seconds is not None else None,
            escalate_to_role,
            escalate_to_user_id,
            esc_tt,
        ),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="sla_policy_upserted",
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"policy_id": policy_id, "subject_type": subject, "priority": pri},
    )
    return {"ok": True, "policy": row}


def get_active_sla_policy(
    cur: Any, *, company_code: str, subject_type: str, priority: str = "normal"
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM workflow_sla_policies
         WHERE company_code=%s AND subject_type=%s AND priority=%s AND active=true
         LIMIT 1
        """,
        (company_code_norm(company_code), str(subject_type).strip(), str(priority or "normal")),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def start_sla_clock(
    cur: Any,
    *,
    company_code: str,
    subject_type: str,
    subject_id: str,
    priority: str = "normal",
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = sla_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate

    company = company_code_norm(company_code)
    subject = str(subject_type or "").strip()
    sid = str(subject_id or "").strip()
    if not subject or not sid:
        return {"ok": False, "error": "subject_required"}

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            """
            SELECT * FROM workflow_sla_clocks
             WHERE company_code=%s AND idempotency_key=%s
             LIMIT 1
            """,
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            _insert_event(
                cur,
                company_code=company,
                event_type="sla_idempotent_replay",
                clock_id=str(dict(existing)["clock_id"]),
                actor_user_id=actor_user_id,
                actor_phone=actor_phone,
                payload={"op": "start_sla_clock", "idempotency_key": idem},
            )
            return {"ok": True, "replayed": True, "clock": _clock_row(dict(existing))}

    policy = get_active_sla_policy(
        cur, company_code=company, subject_type=subject, priority=priority
    )
    if not policy:
        return {"ok": False, "error": "sla_policy_not_found"}

    when = ensure_utc(now) or utc_now()
    due_at = ensure_utc(when + timedelta(seconds=int(policy["due_in_seconds"])))
    remind_at = None
    if policy.get("remind_before_seconds") is not None:
        remind_at = ensure_utc(due_at - timedelta(seconds=int(policy["remind_before_seconds"])))

    clock_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO workflow_sla_clocks (
          clock_id, company_code, policy_id, subject_type, subject_id, status,
          priority, due_at, remind_at, idempotency_key, metadata
        ) VALUES (%s,%s,%s,%s,%s,'running',%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            clock_id,
            company,
            str(policy["policy_id"]),
            subject,
            sid,
            str(policy.get("priority") or priority),
            due_at,
            remind_at,
            idem,
            json.dumps(metadata or {}),
        ),
    )
    row = dict(cur.fetchone())
    _insert_event(
        cur,
        company_code=company,
        event_type="sla_clock_started",
        clock_id=clock_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"subject_type": subject, "subject_id": sid, "due_at": due_at.isoformat()},
    )
    return {"ok": True, "replayed": False, "clock": _clock_row(row)}


def _clock_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "clock_id": str(row["clock_id"]),
        "company_code": row["company_code"],
        "policy_id": str(row["policy_id"]),
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
        "status": row["status"],
        "priority": row.get("priority"),
        "due_at": row.get("due_at"),
        "remind_at": row.get("remind_at"),
        "reminded_at": row.get("reminded_at"),
        "breached_at": row.get("breached_at"),
        "satisfied_at": row.get("satisfied_at"),
        "cancelled_at": row.get("cancelled_at"),
        "breach_task_id": str(row["breach_task_id"]) if row.get("breach_task_id") else None,
        "idempotency_key": row.get("idempotency_key"),
        "row_version": int(row.get("row_version") or 1),
        "metadata": meta or {},
    }


def _load_clock(cur: Any, *, company_code: str, clock_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM workflow_sla_clocks
         WHERE company_code=%s AND clock_id=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), str(clock_id)),
    )
    row = cur.fetchone()
    return _clock_row(dict(row)) if row else None


def satisfy_sla_clock(
    cur: Any,
    *,
    company_code: str,
    clock_id: str,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = sla_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    clock = _load_clock(cur, company_code=company, clock_id=clock_id)
    if not clock:
        return {"ok": False, "error": "clock_not_found"}
    if clock["status"] == "satisfied":
        return {"ok": True, "clock": clock, "replayed": True}
    if not can_transition(CLOCK_TRANSITIONS, clock["status"], "satisfied"):
        return {"ok": False, "error": "invalid_clock_transition", "status": clock["status"]}
    if expected_row_version is not None and int(clock["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}
    prior_status = clock["status"]
    cur.execute(
        """
        UPDATE workflow_sla_clocks
           SET status='satisfied', satisfied_at=now(),
               row_version=row_version+1, updated_at=now()
         WHERE clock_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (clock_id, company, int(clock["row_version"])),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type="sla_satisfied",
        clock_id=clock_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"from_status": prior_status},
    )
    if prior_status == "breached":
        _insert_event(
            cur,
            company_code=company,
            event_type="sla_post_breach_closure",
            clock_id=clock_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"closure": "satisfied"},
        )
    return {"ok": True, "clock": _clock_row(dict(row)), "from_status": prior_status}


def cancel_sla_clock(
    cur: Any,
    *,
    company_code: str,
    clock_id: str,
    actor_user_id: str | None = None,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = sla_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    clock = _load_clock(cur, company_code=company, clock_id=clock_id)
    if not clock:
        return {"ok": False, "error": "clock_not_found"}
    if clock["status"] == "cancelled":
        return {"ok": True, "clock": clock, "replayed": True}
    if not can_transition(CLOCK_TRANSITIONS, clock["status"], "cancelled"):
        return {"ok": False, "error": "invalid_clock_transition", "status": clock["status"]}
    if expected_row_version is not None and int(clock["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}
    prior_status = clock["status"]
    cur.execute(
        """
        UPDATE workflow_sla_clocks
           SET status='cancelled', cancelled_at=now(),
               row_version=row_version+1, updated_at=now()
         WHERE clock_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (clock_id, company, int(clock["row_version"])),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type="sla_cancelled",
        clock_id=clock_id,
        actor_user_id=actor_user_id,
        actor_phone=actor_phone,
        payload={"from_status": prior_status},
    )
    if prior_status == "breached":
        _insert_event(
            cur,
            company_code=company,
            event_type="sla_post_breach_closure",
            clock_id=clock_id,
            actor_user_id=actor_user_id,
            actor_phone=actor_phone,
            payload={"closure": "cancelled"},
        )
    return {"ok": True, "clock": _clock_row(dict(row)), "from_status": prior_status}


def tick_sla_clock(
    cur: Any,
    *,
    company_code: str,
    clock_id: str,
    now: datetime | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Advance reminder/breach for one clock. Reminder = audit only (no live push)."""
    gate = sla_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    clock = _load_clock(cur, company_code=company, clock_id=clock_id)
    if not clock:
        return {"ok": False, "error": "clock_not_found"}
    if clock["status"] != "running":
        # Repeated evaluation after breach/satisfy/cancel is a no-op (idempotent).
        return {
            "ok": True,
            "clock": clock,
            "actions": [],
            "action": "noop",
            "replayed": True,
        }

    when = ensure_utc(now) or utc_now()
    actions: list[str] = []

    # Reminder (audit-only in this slice)
    if (
        gate.get("reminders_enabled")
        and clock.get("remind_at")
        and not clock.get("reminded_at")
        and when >= clock["remind_at"]
        and when < clock["due_at"]
    ):
        cur.execute(
            """
            UPDATE workflow_sla_clocks
               SET reminded_at=%s, row_version=row_version+1, updated_at=now()
             WHERE clock_id=%s AND company_code=%s AND row_version=%s
            RETURNING *
            """,
            (when, clock_id, company, int(clock["row_version"])),
        )
        row = cur.fetchone()
        if row:
            clock = _clock_row(dict(row))
            _insert_event(
                cur,
                company_code=company,
                event_type="sla_reminder_due",
                clock_id=clock_id,
                actor_user_id=actor_user_id,
                payload={"remind_at": str(clock.get("remind_at")), "channel": "audit_only"},
            )
            actions.append("reminded")

    if when >= clock["due_at"] and clock["status"] == "running":
        # Reload policy for escalate task type
        cur.execute(
            "SELECT * FROM workflow_sla_policies WHERE policy_id=%s LIMIT 1",
            (clock["policy_id"],),
        )
        prow = cur.fetchone()
        policy = dict(prow) if prow else {}
        breach_task_id = None
        # OPTIONAL: breach task only when tasks module also enabled for company
        task_gate = tasks_enabled_for_company(cur, company)
        if task_gate.get("ok"):
            created = create_workflow_task(
                cur,
                company_code=company,
                task_type=str(policy.get("escalate_task_type") or "sla_breach"),
                title=f"SLA breach: {clock['subject_type']} {clock['subject_id']}",
                subject_type=clock["subject_type"],
                subject_id=clock["subject_id"],
                priority=str(clock.get("priority") or "high"),
                sla_clock_id=clock_id,
                assigned_to_user_id=policy.get("escalate_to_user_id"),
                metadata={
                    "sla_clock_id": clock_id,
                    "escalate_to_role": policy.get("escalate_to_role"),
                },
                actor_user_id=actor_user_id,
                idempotency_key=f"sla-breach:{clock_id}",
            )
            if created.get("ok"):
                breach_task_id = created["task"]["task_id"]

        cur.execute(
            """
            UPDATE workflow_sla_clocks
               SET status='breached', breached_at=%s, breach_task_id=%s,
                   row_version=row_version+1, updated_at=now()
             WHERE clock_id=%s AND company_code=%s AND status='running' AND row_version=%s
            RETURNING *
            """,
            (when, breach_task_id, clock_id, company, int(clock["row_version"])),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "concurrency_conflict"}
        clock = _clock_row(dict(row))
        _insert_event(
            cur,
            company_code=company,
            event_type="sla_breached",
            clock_id=clock_id,
            task_id=breach_task_id,
            actor_user_id=actor_user_id,
            payload={"breach_task_id": breach_task_id, "tasks_gate_ok": bool(task_gate.get("ok"))},
        )
        actions.append("breached")

    return {"ok": True, "clock": clock, "actions": actions}


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_WORKFLOW_TASKS=off and/or WATHEFNI_WORKFLOW_SLA=off",
            "Clear company from WATHEFNI_WORKFLOW_TASKS_COMPANIES / WATHEFNI_WORKFLOW_SLA_COMPANIES",
            "SET workflow_task_settings.enabled=false / workflow_sla_settings.enabled=false",
        ],
        "data": [
            "Retain hr_tasks rows and workflow_* tables; do not DROP",
            "Existing delivery_failed / activation hr_tasks remain on legacy paths",
            "Reminders are audit-only in slice 2 — no notification rollback required",
        ],
        "modularity": [
            "SLA works without tasks for clock accounting; breach task creation requires tasks gate",
            "Tasks work without SLA (due_at optional)",
            "Disabled Tasks/SLA leave legacy hr_tasks and domain workflows usable",
        ],
        "invariants": [
            "One open hr_task per (company, task_type, subject_type, subject_id)",
            "SLA breach task idempotent per clock_id; repeated tick does not duplicate",
            "due_at / SLA timestamps stored UTC; localize only at surfaces",
            "Task resolve never mutates business subject",
            "Reminders remain audit-only (no live push in Phase A)",
        ],
        "schema_version": WORKFLOW_TASK_SLA_SCHEMA_VERSION,
    }
