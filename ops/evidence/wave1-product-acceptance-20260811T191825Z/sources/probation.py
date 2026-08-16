"""Wave 1 — Probation authority (30/60/90 + case SM).

Dark by default:
  WATHEFNI_PROBATION=on
  ∧ company in WATHEFNI_PROBATION_COMPANIES
  ∧ probation_settings.enabled (or company_modules.probation)

HARD: binds to canonical employment (employee_key / employment_id).
OPTIONAL: auto_plan_on_hire; offer probation_days sync (truth-sync canary).
NO UI in this wave — backend authority + staging qualify only.

Case SM (Wave 1):
  scheduled → active → under_review → confirmed | extended | failed
  (+ cancelled from non-terminal)
Milestone SM:
  pending → completed | skipped | overdue
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROBATION_SCHEMA_VERSION = "1.0.0"
DEFAULT_TEMPLATE_ID = "default_kuwait_30_60_90"
DEFAULT_TEMPLATE_VERSION = "1.0.0"
_ON_VALUES = {"1", "true", "yes", "on"}
_SCHEMA = Path(__file__).resolve().parent / "ops" / "sql" / "probation_wave1_v1.sql"

CASE_STATUSES = frozenset(
    {"scheduled", "active", "under_review", "confirmed", "extended", "failed", "cancelled"}
)
TERMINAL_CASE = frozenset({"confirmed", "failed", "cancelled"})
OPEN_CASE = frozenset({"scheduled", "active", "under_review", "extended"})
MILESTONE_STATUSES = frozenset({"pending", "completed", "skipped", "overdue"})

CASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "scheduled": frozenset({"active", "cancelled"}),
    "active": frozenset({"under_review", "cancelled"}),
    "under_review": frozenset({"confirmed", "extended", "failed", "active", "cancelled"}),
    "extended": frozenset({"under_review", "active", "cancelled"}),
    "confirmed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
MILESTONE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"completed", "skipped", "overdue"}),
    "overdue": frozenset({"completed", "skipped"}),
    "completed": frozenset(),
    "skipped": frozenset(),
}


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def probation_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_PROBATION", "off")


def probation_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PROBATION_COMPANIES", "") or "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def can_transition_case(from_status: str, to_status: str) -> bool:
    return to_status in CASE_TRANSITIONS.get(from_status, frozenset())


def can_transition_milestone(from_status: str, to_status: str) -> bool:
    return to_status in MILESTONE_TRANSITIONS.get(from_status, frozenset())


def ensure_probation_schema(cur: Any) -> None:
    cur.execute(_SCHEMA.read_text(encoding="utf-8"))


def default_kuwait_milestones() -> list[dict[str, Any]]:
    return [
        {
            "milestone_key": "day_30",
            "title_en": "30-day check-in",
            "title_ar": "متابعة يوم ٣٠",
            "offset_days": 30,
            "sort_order": 10,
        },
        {
            "milestone_key": "day_60",
            "title_en": "60-day check-in",
            "title_ar": "متابعة يوم ٦٠",
            "offset_days": 60,
            "sort_order": 20,
        },
        {
            "milestone_key": "day_90",
            "title_en": "90-day review",
            "title_ar": "مراجعة يوم ٩٠",
            "offset_days": 90,
            "sort_order": 30,
        },
    ]


def _insert_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    case_id: str | None = None,
    milestone_id: str | None = None,
    actor_user_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO probation_events (
          event_id, company_code, case_id, milestone_id, event_type, actor_user_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            str(uuid.uuid4()),
            company_code,
            case_id,
            milestone_id,
            event_type,
            actor_user_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _case_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in ("case_id",):
        if out.get(k) is not None:
            out[k] = str(out[k])
    for k in ("probation_start", "probation_end", "created_at", "updated_at", "decided_at"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    return out


def _milestone_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in ("milestone_id", "case_id"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    for k in ("due_on", "completed_at", "created_at", "updated_at"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    return out


def get_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM probation_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            INSERT INTO probation_settings (company_code, enabled, auto_plan_on_hire, start_mode)
            VALUES (%s, false, true, 'hire_date')
            ON CONFLICT (company_code) DO NOTHING
            RETURNING *
            """,
            (company,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT * FROM probation_settings WHERE company_code=%s", (company,))
            row = cur.fetchone()
    d = dict(row or {})
    return {
        "company_code": company,
        "enabled": bool(d.get("enabled")),
        "auto_plan_on_hire": bool(d.get("auto_plan_on_hire", True)),
        "start_mode": str(d.get("start_mode") or "hire_date"),
        "default_probation_days": int(d.get("default_probation_days") or 90),
    }


def set_settings(
    cur: Any,
    company_code: str,
    *,
    enabled: bool | None = None,
    auto_plan_on_hire: bool | None = None,
    start_mode: str | None = None,
    default_probation_days: int | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    current = get_settings(cur, company)
    nxt = {
        "enabled": current["enabled"] if enabled is None else bool(enabled),
        "auto_plan_on_hire": current["auto_plan_on_hire"] if auto_plan_on_hire is None else bool(auto_plan_on_hire),
        "start_mode": current["start_mode"] if start_mode is None else str(start_mode),
        "default_probation_days": current["default_probation_days"]
        if default_probation_days is None
        else int(default_probation_days),
    }
    if nxt["start_mode"] not in {"hire_date", "onboarding_complete"}:
        return {"ok": False, "error": "start_mode_invalid"}
    cur.execute(
        """
        INSERT INTO probation_settings (
          company_code, enabled, auto_plan_on_hire, start_mode, default_probation_days, updated_at
        ) VALUES (%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=EXCLUDED.enabled,
          auto_plan_on_hire=EXCLUDED.auto_plan_on_hire,
          start_mode=EXCLUDED.start_mode,
          default_probation_days=EXCLUDED.default_probation_days,
          updated_at=now()
        """,
        (
            company,
            nxt["enabled"],
            nxt["auto_plan_on_hire"],
            nxt["start_mode"],
            nxt["default_probation_days"],
        ),
    )
    return get_settings(cur, company)


def probation_enabled_for_company(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not probation_runtime_flag_on():
        return {"ok": False, "error": "probation_disabled", "gate": "runtime_flag"}
    allow = probation_company_allowlist()
    if allow and company not in allow:
        return {"ok": False, "error": "probation_company_not_allowlisted", "gate": "company_allowlist"}
    settings = get_settings(cur, company)
    module_on = False
    try:
        cur.execute(
            """
            SELECT enabled FROM company_modules
             WHERE company_code=%s AND module_key='probation' LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        module_on = bool(row and dict(row).get("enabled"))
    except Exception:
        module_on = False
    if not (settings.get("enabled") or module_on):
        return {"ok": False, "error": "probation_company_disabled", "gate": "company_enable"}
    return {"ok": True, "company_code": company, "settings": settings, "module_on": module_on}


def ensure_default_template(cur: Any, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO probation_plan_templates (
          template_id, company_code, version, title_en, title_ar, active
        ) VALUES (%s,%s,%s,%s,%s,true)
        ON CONFLICT (company_code, template_id) DO UPDATE
          SET updated_at=now()
        """,
        (
            DEFAULT_TEMPLATE_ID,
            company,
            DEFAULT_TEMPLATE_VERSION,
            "Kuwait 30/60/90 probation",
            "فترة التجربة ٣٠/٦٠/٩٠",
        ),
    )
    for m in default_kuwait_milestones():
        cur.execute(
            """
            INSERT INTO probation_plan_template_milestones (
              company_code, template_id, milestone_key, title_en, title_ar, offset_days, sort_order
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_code, template_id, milestone_key) DO UPDATE
              SET title_en=EXCLUDED.title_en,
                  title_ar=EXCLUDED.title_ar,
                  offset_days=EXCLUDED.offset_days,
                  sort_order=EXCLUDED.sort_order
            """,
            (
                company,
                DEFAULT_TEMPLATE_ID,
                m["milestone_key"],
                m["title_en"],
                m["title_ar"],
                m["offset_days"],
                m["sort_order"],
            ),
        )
    return {"ok": True, "template_id": DEFAULT_TEMPLATE_ID, "milestones": default_kuwait_milestones()}


def resolve_employment(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    if not company or not key:
        return {"ok": False, "error": "employee_required"}
    cur.execute(
        """
        SELECT employee_key, company_code, employment_status, start_date, name
          FROM employees
         WHERE company_code=%s AND employee_key=%s
         LIMIT 1
        """,
        (company, key),
    )
    hub = cur.fetchone()
    if not hub:
        return {"ok": False, "error": "employee_not_found"}
    hub_d = dict(hub)
    status = str(hub_d.get("employment_status") or "").strip().lower()
    if status in {"left", "terminated"}:
        return {"ok": False, "error": "employee_not_eligible", "hub_status": status}
    employment_id = None
    try:
        cur.execute(
            """
            SELECT employment_id, lifecycle_state, start_date
              FROM employee_employments
             WHERE company_code=%s AND legacy_employee_key=%s
               AND COALESCE(lifecycle_state,'') <> 'terminated'
             ORDER BY updated_at DESC NULLS LAST
             LIMIT 1
            """,
            (company, key),
        )
        emp = cur.fetchone()
        if emp:
            ed = dict(emp)
            employment_id = str(ed.get("employment_id") or "") or None
            if ed.get("start_date"):
                hub_d["start_date"] = ed.get("start_date")
    except Exception:
        pass
    return {
        "ok": True,
        "employee_key": key,
        "company_code": company,
        "employment_id": employment_id,
        "hub_status": status,
        "start_date": hub_d.get("start_date"),
        "name": hub_d.get("name"),
    }


def get_case(cur: Any, *, company_code: str, case_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM probation_cases WHERE company_code=%s AND case_id=%s",
        (company_code_norm(company_code), str(case_id)),
    )
    row = cur.fetchone()
    return _case_row(dict(row)) if row else None


def list_milestones(cur: Any, *, company_code: str, case_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM probation_milestones
         WHERE company_code=%s AND case_id=%s
         ORDER BY due_on ASC, milestone_key ASC
        """,
        (company_code_norm(company_code), str(case_id)),
    )
    return [_milestone_row(dict(r)) for r in (cur.fetchall() or [])]


def create_case(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    probation_start: date | None = None,
    probation_days: int | None = None,
    manager_user_id: str | None = None,
    actor_user_id: str | None = None,
    idempotency_key: str | None = None,
    initial_status: str = "active",
) -> dict[str, Any]:
    gate = probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_default_template(cur, company)
    resolved = resolve_employment(cur, company_code=company, employee_key=employee_key)
    if not resolved.get("ok"):
        return resolved

    idem = str(idempotency_key or "").strip() or None
    if idem:
        cur.execute(
            """
            SELECT * FROM probation_cases
             WHERE company_code=%s AND idempotency_key=%s
             LIMIT 1
            """,
            (company, idem),
        )
        existing = cur.fetchone()
        if existing:
            case = _case_row(dict(existing))
            return {
                "ok": True,
                "replayed": True,
                "case": case,
                "milestones": list_milestones(cur, company_code=company, case_id=case["case_id"]),
            }

    cur.execute(
        """
        SELECT case_id, status FROM probation_cases
         WHERE company_code=%s AND employee_key=%s
           AND status = ANY(%s)
         LIMIT 1
        """,
        (company, str(employee_key), list(OPEN_CASE)),
    )
    open_row = cur.fetchone()
    if open_row:
        return {
            "ok": False,
            "error": "open_case_exists",
            "case_id": str(dict(open_row)["case_id"]),
        }

    settings = gate["settings"]
    start = as_date(probation_start) or as_date(resolved.get("start_date")) or date.today()
    days = int(probation_days if probation_days is not None else settings["default_probation_days"])
    if days <= 0:
        return {"ok": False, "error": "probation_days_invalid"}
    end = start + timedelta(days=days)
    status = str(initial_status or "active").strip().lower()
    if status not in {"scheduled", "active"}:
        return {"ok": False, "error": "initial_status_invalid"}
    if status == "scheduled" and start <= date.today():
        status = "active"

    case_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO probation_cases (
          case_id, company_code, employee_key, employment_id, status,
          probation_start, probation_end, template_id, template_version,
          manager_user_id, idempotency_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            case_id,
            company,
            str(employee_key),
            resolved.get("employment_id"),
            status,
            start,
            end,
            DEFAULT_TEMPLATE_ID,
            DEFAULT_TEMPLATE_VERSION,
            str(manager_user_id or "").strip() or None,
            idem,
        ),
    )
    case = _case_row(dict(cur.fetchone()))
    _insert_event(
        cur,
        company_code=company,
        event_type="case_created",
        case_id=case_id,
        actor_user_id=actor_user_id,
        payload={"status": status, "probation_start": str(start), "probation_end": str(end)},
    )

    # Persist probation dates on employment SoT (best-effort).
    try:
        cur.execute(
            """
            UPDATE employee_employments
               SET probation_start_date=%s,
                   probation_end_date=%s,
                   updated_at=now()
             WHERE company_code=%s AND legacy_employee_key=%s
               AND COALESCE(lifecycle_state,'') <> 'terminated'
            """,
            (start, end, company, str(employee_key)),
        )
    except Exception:
        try:
            cur.execute(
                """
                UPDATE employees
                   SET probation_end_date=%s, updated_at=now()
                 WHERE company_code=%s AND employee_key=%s
                """,
                (end, company, str(employee_key)),
            )
        except Exception:
            pass

    milestones = _seed_milestones(cur, company=company, case=case, start=start)
    try:
        import workflow_task_sla as wts

        for m in milestones:
            wts.create_workflow_task(
                cur,
                company_code=company,
                task_type="probation_milestone",
                title=m.get("title_en") or m.get("milestone_key"),
                subject_type="probation_milestone",
                subject_id=str(m["milestone_id"]),
                employee_key=str(employee_key),
                source="probation",
                metadata={"milestone_key": m.get("milestone_key"), "due_on": m.get("due_on")},
                actor_user_id=actor_user_id,
                idempotency_key=f"probation_ms:{m['milestone_id']}",
            )
    except Exception:
        pass

    return {"ok": True, "replayed": False, "case": case, "milestones": milestones}


def _seed_milestones(
    cur: Any, *, company: str, case: dict[str, Any], start: date
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM probation_plan_template_milestones
         WHERE company_code=%s AND template_id=%s
         ORDER BY sort_order ASC, offset_days ASC
        """,
        (company, case.get("template_id") or DEFAULT_TEMPLATE_ID),
    )
    specs = [dict(r) for r in (cur.fetchall() or [])] or default_kuwait_milestones()
    end = as_date(case.get("probation_end")) or (start + timedelta(days=90))
    out: list[dict[str, Any]] = []
    for spec in specs:
        due = start + timedelta(days=int(spec.get("offset_days") or 0))
        if due > end:
            due = end
        mid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO probation_milestones (
              milestone_id, case_id, company_code, employee_key, milestone_key,
              title_en, title_ar, due_on, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            RETURNING *
            """,
            (
                mid,
                case["case_id"],
                company,
                case["employee_key"],
                spec["milestone_key"],
                spec["title_en"],
                spec.get("title_ar"),
                due,
            ),
        )
        out.append(_milestone_row(dict(cur.fetchone())))
    return out


def transition_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    to_status: str,
    actor_user_id: str | None = None,
    decision_reason: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    case = get_case(cur, company_code=company, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    dst = str(to_status or "").strip().lower()
    if dst not in CASE_STATUSES:
        return {"ok": False, "error": "status_invalid"}
    if not can_transition_case(case["status"], dst):
        return {"ok": False, "error": "invalid_transition", "from": case["status"], "to": dst}
    if expected_row_version is not None and int(case["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}

    # Decision terminals require reason.
    if dst in {"confirmed", "failed"} and not str(decision_reason or "").strip():
        return {"ok": False, "error": "decision_reason_required"}

    decided_at = datetime.now(timezone.utc) if dst in TERMINAL_CASE or dst == "extended" else None
    cur.execute(
        """
        UPDATE probation_cases
           SET status=%s,
               decision_reason=COALESCE(%s, decision_reason),
               decided_by_user_id=CASE WHEN %s THEN %s ELSE decided_by_user_id END,
               decided_at=COALESCE(%s, decided_at),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND case_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            dst,
            str(decision_reason or "").strip() or None,
            dst in {"confirmed", "failed", "extended"},
            actor_user_id,
            decided_at,
            company,
            str(case_id),
            int(case["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type=f"case_{dst}",
        case_id=str(case_id),
        actor_user_id=actor_user_id,
        payload={"from": case["status"], "to": dst, "decision_reason": decision_reason},
    )
    return {"ok": True, "case": _case_row(dict(updated))}


def extend_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    extend_days: int,
    actor_user_id: str | None = None,
    decision_reason: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Extend probation_end and move case to extended; seed extra review milestone."""
    if int(extend_days) <= 0:
        return {"ok": False, "error": "extend_days_invalid"}
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    # Must be under_review (or active) to extend via SM.
    if case["status"] not in {"under_review", "active"}:
        return {"ok": False, "error": "extend_requires_reviewable", "status": case["status"]}
    if case["status"] == "active":
        moved = transition_case(
            cur,
            company_code=company_code,
            case_id=case_id,
            to_status="under_review",
            actor_user_id=actor_user_id,
            decision_reason=decision_reason or "extension_review",
            expected_row_version=expected_row_version,
        )
        if not moved.get("ok"):
            return moved
        case = moved["case"]
        expected_row_version = int(case["row_version"])

    new_end = as_date(case["probation_end"]) + timedelta(days=int(extend_days))  # type: ignore[operator]
    company = company_code_norm(company_code)
    cur.execute(
        """
        UPDATE probation_cases
           SET status='extended',
               probation_end=%s,
               extension_count=extension_count+1,
               decision_reason=COALESCE(%s, decision_reason),
               decided_by_user_id=%s,
               decided_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND case_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            new_end,
            str(decision_reason or "extended").strip(),
            actor_user_id,
            company,
            str(case_id),
            int(case["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    case_out = _case_row(dict(updated))

    # Sync employment SoT end date.
    try:
        cur.execute(
            """
            UPDATE employee_employments
               SET probation_end_date=%s, updated_at=now()
             WHERE company_code=%s AND legacy_employee_key=%s
            """,
            (new_end, company, case["employee_key"]),
        )
    except Exception:
        pass

    # Add extension review milestone on new end.
    mid = str(uuid.uuid4())
    key = f"extension_{int(case_out.get('extension_count') or 1)}"
    cur.execute(
        """
        INSERT INTO probation_milestones (
          milestone_id, case_id, company_code, employee_key, milestone_key,
          title_en, title_ar, due_on, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending')
        ON CONFLICT (case_id, milestone_key) DO NOTHING
        RETURNING *
        """,
        (
            mid,
            str(case_id),
            company,
            case["employee_key"],
            key,
            f"Extension review (+{extend_days}d)",
            f"مراجعة التمديد (+{extend_days} يوم)",
            new_end,
        ),
    )
    ms = cur.fetchone()
    _insert_event(
        cur,
        company_code=company,
        event_type="case_extended",
        case_id=str(case_id),
        actor_user_id=actor_user_id,
        payload={"extend_days": extend_days, "probation_end": str(new_end)},
    )
    return {
        "ok": True,
        "case": case_out,
        "milestone": _milestone_row(dict(ms)) if ms else None,
        "milestones": list_milestones(cur, company_code=company, case_id=str(case_id)),
    }


def update_milestone(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    milestone_key: str,
    to_status: str,
    actor_user_id: str | None = None,
    notes: str | None = None,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    gate = probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    case = get_case(cur, company_code=company, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case["status"] in TERMINAL_CASE:
        return {"ok": False, "error": "case_terminal", "status": case["status"]}

    cur.execute(
        """
        SELECT * FROM probation_milestones
         WHERE company_code=%s AND case_id=%s AND milestone_key=%s
         LIMIT 1
        """,
        (company, str(case_id), str(milestone_key)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "milestone_not_found"}
    ms = _milestone_row(dict(row))
    dst = str(to_status or "").strip().lower()
    if dst not in MILESTONE_STATUSES:
        return {"ok": False, "error": "status_invalid"}
    if not can_transition_milestone(ms["status"], dst):
        return {"ok": False, "error": "invalid_transition", "from": ms["status"], "to": dst}
    if expected_row_version is not None and int(ms["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "concurrency_conflict"}

    completed_at = datetime.now(timezone.utc) if dst in {"completed", "skipped"} else None
    cur.execute(
        """
        UPDATE probation_milestones
           SET status=%s,
               notes=COALESCE(%s, notes),
               completed_at=COALESCE(%s, completed_at),
               completed_by_user_id=CASE WHEN %s THEN %s ELSE completed_by_user_id END,
               row_version=row_version+1,
               updated_at=now()
         WHERE milestone_id=%s AND row_version=%s
        RETURNING *
        """,
        (
            dst,
            notes,
            completed_at,
            dst in {"completed", "skipped"},
            actor_user_id,
            ms["milestone_id"],
            int(ms["row_version"]),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "concurrency_conflict"}
    _insert_event(
        cur,
        company_code=company,
        event_type=f"milestone_{dst}",
        case_id=str(case_id),
        milestone_id=str(ms["milestone_id"]),
        actor_user_id=actor_user_id,
        payload={"milestone_key": milestone_key, "from": ms["status"]},
    )
    return {"ok": True, "milestone": _milestone_row(dict(updated))}


def mark_overdue_milestones(
    cur: Any, *, company_code: str, today: date | None = None
) -> dict[str, Any]:
    gate = probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    day = today or date.today()
    cur.execute(
        """
        UPDATE probation_milestones
           SET status='overdue', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s
           AND status='pending'
           AND due_on < %s
        RETURNING milestone_id, case_id, milestone_key
        """,
        (company, day),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    for r in rows:
        _insert_event(
            cur,
            company_code=company,
            event_type="milestone_overdue",
            case_id=str(r.get("case_id")),
            milestone_id=str(r.get("milestone_id")),
            payload={"milestone_key": r.get("milestone_key"), "as_of": str(day)},
        )
    return {"ok": True, "marked": len(rows), "items": rows}


def maybe_create_case_on_hire(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    probation_start: date | None = None,
    probation_days: int | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """OPTIONAL: auto_plan_on_hire when contract + settings allow."""
    gate = probation_enabled_for_company(cur, company_code)
    if not gate.get("ok"):
        return {"ok": True, "skipped": True, "reason": gate.get("error")}
    settings = gate["settings"]
    if not settings.get("auto_plan_on_hire"):
        return {"ok": True, "skipped": True, "reason": "auto_plan_off"}
    if settings.get("start_mode") == "onboarding_complete":
        return {"ok": True, "skipped": True, "reason": "start_mode_onboarding_complete"}
    try:
        import capability_contracts as cc

        modules = {"probation"}
        try:
            cur.execute(
                "SELECT module_key FROM company_modules WHERE company_code=%s AND enabled=true",
                (company_code_norm(company_code),),
            )
            modules = {str(r["module_key"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])}
        except Exception:
            pass
        ev = cc.evaluate_contract(
            "probation.auto_plan_on_hire",
            enabled_modules=modules,
            company_settings={"probation.auto_plan_on_hire": True},
        )
        if not ev.get("active"):
            return {"ok": True, "skipped": True, "reason": "contract_inactive", "eval": ev}
    except Exception:
        pass
    return create_case(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        probation_start=probation_start,
        probation_days=probation_days,
        actor_user_id=actor_user_id,
        idempotency_key=f"hire:{employee_key}",
        initial_status="active",
    )


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_PROBATION=off",
            "Clear WATHEFNI_PROBATION_COMPANIES",
            "Disable company_modules.probation / probation_settings.enabled",
        ],
        "version": PROBATION_SCHEMA_VERSION,
        "note": "No Probation UI in Wave 1 backend freeze",
    }
