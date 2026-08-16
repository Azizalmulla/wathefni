#!/usr/bin/env python3
"""Onboarding completion — single canonical authority.

Every surface (employee app, HR dashboard, employee profile, checklist, tasks,
reminders, notifications, reporting, downstream access decisions) must derive
completion from this module. Do not re-implement "complete" sets in SQL or UI.

Employee-level canonical states
-------------------------------
  not_started          no required progress yet, nothing ever submitted
  in_progress          progress exists, nothing actionable by employee or HR
  waiting_on_employee  at least one open required item needs employee action
  waiting_on_hr        open required items are all awaiting HR/verifier action
  blocked              every open required item is blocked by dependencies
  completed            all required items satisfied (accepted / waived / N/A)
  reopened             was completed before, now has open required work again

Item-level classification (derived, never a new stored status)
--------------------------------------------------------------
  satisfied_accepted | satisfied_waived | satisfied_not_applicable
  waiting_employee | waiting_hr | waiting_other | blocked

Design rules
------------
* Completion is calculated, never a decorative toggle.
* Submitted != verified. Only HR-verified (accepted) or explicitly
  waived / not-applicable required items satisfy completion.
* Historical completion evidence is append-only and is never removed when
  checklist definitions change.
* Transitions are atomic and idempotent (single upsert, COALESCE first stamp).
* Requirement changes after start re-open completion instead of rewriting history.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "onboarding_completion_v1"

# ---------------------------------------------------------------------------
# Employee-level states
# ---------------------------------------------------------------------------
STATE_NOT_STARTED = "not_started"
STATE_IN_PROGRESS = "in_progress"
STATE_WAITING_ON_EMPLOYEE = "waiting_on_employee"
STATE_WAITING_ON_HR = "waiting_on_hr"
STATE_BLOCKED = "blocked"
STATE_COMPLETED = "completed"
STATE_REOPENED = "reopened"

COMPLETION_STATES = (
    STATE_NOT_STARTED,
    STATE_IN_PROGRESS,
    STATE_WAITING_ON_EMPLOYEE,
    STATE_WAITING_ON_HR,
    STATE_BLOCKED,
    STATE_COMPLETED,
    STATE_REOPENED,
)

# Terminal employment/assignment states that suspend completion expectations.
ASSIGNMENT_TERMINAL = frozenset({"cancelled", "abandoned"})

# Assignment states meaning HR has launched onboarding. Once launched, the
# employee is no longer `not_started` even with zero submissions — the process is
# underway and someone owes the first action.
ASSIGNMENT_STARTED = frozenset({"in_progress", "started", "active", "delayed"})

# ---------------------------------------------------------------------------
# Item classification
# ---------------------------------------------------------------------------
ITEM_SATISFIED_ACCEPTED = "satisfied_accepted"
ITEM_SATISFIED_WAIVED = "satisfied_waived"
ITEM_SATISFIED_NOT_APPLICABLE = "satisfied_not_applicable"
ITEM_WAITING_EMPLOYEE = "waiting_employee"
ITEM_WAITING_HR = "waiting_hr"
ITEM_WAITING_OTHER = "waiting_other"
ITEM_BLOCKED = "blocked"

SATISFIED_CLASSES = frozenset(
    {ITEM_SATISFIED_ACCEPTED, ITEM_SATISFIED_WAIVED, ITEM_SATISFIED_NOT_APPLICABLE}
)

# ---------------------------------------------------------------------------
# Canonical status vocabulary (single source for Python AND SQL)
#
# Wave 2A canonical states plus every legacy spelling still present in data.
# `received` is deliberately NOT satisfying: it means "file arrived", not
# "HR verified". Legacy rows are treated as awaiting HR review.
# ---------------------------------------------------------------------------
ACCEPTED_STATUSES = (
    "accepted",
    "complete",
    "completed",
    "verified",
    "approved",
    "reviewed",
)
WAIVED_STATUSES = (
    "waived",
    "cancelled_onboarding",
    "retired_legacy",
)
NOT_APPLICABLE_STATUSES = ("not_applicable", "n/a", "na")
BLOCKED_STATUSES = ("blocked", "abandoned_employment_ended")
EMPLOYEE_ACTION_STATUSES = (
    "pending",
    "missing",
    "requested",
    "in_progress",
    "rejected",
    "replacement_required",
    "reupload_required",
)
HR_REVIEW_STATUSES = (
    "submitted",
    "processing",
    "received",
    "needs_review",
)

SATISFIED_STATUSES = ACCEPTED_STATUSES + WAIVED_STATUSES + NOT_APPLICABLE_STATUSES

# Statuses that mean "no further onboarding work expected on this row".
CLOSED_STATUSES = SATISFIED_STATUSES + BLOCKED_STATUSES

# Progress signal: employee/HR has done something beyond initial seed.
PROGRESS_STATUSES = (
    ACCEPTED_STATUSES
    + WAIVED_STATUSES
    + NOT_APPLICABLE_STATUSES
    + HR_REVIEW_STATUSES
    + ("in_progress", "rejected", "replacement_required", "reupload_required")
)


def _sql_list(values: Iterable[str]) -> str:
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def sql_satisfied_list() -> str:
    """SQL literal list of satisfying statuses — use everywhere instead of ad-hoc sets."""
    return _sql_list(SATISFIED_STATUSES)


def sql_closed_list() -> str:
    return _sql_list(CLOSED_STATUSES)


def sql_employee_action_list() -> str:
    """Statuses where the employee owes an action — includes correction states.

    Reminder queries historically used only pending/missing/requested, so a
    rejected document never produced a follow-up.
    """
    return _sql_list(EMPLOYEE_ACTION_STATUSES)


def sql_satisfied_predicate(column: str = "status") -> str:
    return f"lower(coalesce({column},'')) IN ({sql_satisfied_list()})"


def sql_open_predicate(column: str = "status") -> str:
    """Open = required work still outstanding (not satisfied, not blocked-terminal)."""
    return f"lower(coalesce({column},'')) NOT IN ({sql_closed_list()})"


# ---------------------------------------------------------------------------
# Item-level helpers
# ---------------------------------------------------------------------------
def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _meta(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get("lifecycle_meta")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def item_is_not_applicable(item: Mapping[str, Any]) -> bool:
    if _norm(item.get("status")) in NOT_APPLICABLE_STATUSES:
        return True
    meta = _meta(item)
    return bool(meta.get("not_applicable")) or _norm(meta.get("applicability")) == "not_applicable"


def item_is_satisfied(status: str | None) -> bool:
    """Canonical satisfaction test. Replaces divergent per-module sets.

    NOTE: `received` is not satisfying — it is awaiting HR verification.
    """
    return _norm(status) in SATISFIED_STATUSES


def item_is_blocked(item: Mapping[str, Any]) -> bool:
    if _norm(item.get("status")) in BLOCKED_STATUSES:
        return True
    blockers = item.get("blocked_by")
    return bool(blockers) if isinstance(blockers, (list, tuple)) else False


def item_is_required(item: Mapping[str, Any]) -> bool:
    if item_is_not_applicable(item):
        return False
    return item.get("required") is True


def classify_item(item: Mapping[str, Any]) -> str:
    """Single classification used by every surface."""
    status = _norm(item.get("status"))
    if item_is_not_applicable(item):
        return ITEM_SATISFIED_NOT_APPLICABLE
    if status in ACCEPTED_STATUSES:
        return ITEM_SATISFIED_ACCEPTED
    if status in WAIVED_STATUSES:
        return ITEM_SATISFIED_WAIVED
    if item_is_blocked(item):
        return ITEM_BLOCKED
    if status in HR_REVIEW_STATUSES:
        return ITEM_WAITING_HR
    if status in EMPLOYEE_ACTION_STATUSES:
        # Ownership decides: HR-owned pending work is not the employee's ask.
        owner = _norm(item.get("owner"))
        responsible = _norm(item.get("responsible_party") or item.get("waiting_on"))
        if responsible == "employee":
            return ITEM_WAITING_EMPLOYEE
        if responsible in {"hr", "compliance"}:
            return ITEM_WAITING_HR
        if responsible in {"system", "payroll"}:
            return ITEM_WAITING_OTHER
        if owner == "employee":
            return ITEM_WAITING_EMPLOYEE
        if owner == "hr":
            return ITEM_WAITING_HR
        return ITEM_WAITING_OTHER
    return ITEM_WAITING_OTHER


def item_has_progress(item: Mapping[str, Any]) -> bool:
    return _norm(item.get("status")) in PROGRESS_STATUSES


# ---------------------------------------------------------------------------
# Employee-level computation
# ---------------------------------------------------------------------------
def compute_completion(
    items: Iterable[Mapping[str, Any]],
    *,
    previously_completed: bool = False,
    assignment_status: str | None = None,
) -> dict[str, Any]:
    """Derive the canonical completion snapshot from checklist rows.

    Pure function: no DB, no flags. Same inputs → same outputs on every surface.
    """
    rows = [dict(i) for i in items or []]
    required = [i for i in rows if item_is_required(i)]

    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in required:
        buckets.setdefault(classify_item(item), []).append(item)

    satisfied = [i for cls in SATISFIED_CLASSES for i in buckets.get(cls, [])]
    waiting_employee = buckets.get(ITEM_WAITING_EMPLOYEE, [])
    waiting_hr = buckets.get(ITEM_WAITING_HR, [])
    waiting_other = buckets.get(ITEM_WAITING_OTHER, [])
    blocked = buckets.get(ITEM_BLOCKED, [])

    open_required = waiting_employee + waiting_hr + waiting_other + blocked
    assignment_launched = _norm(assignment_status) in ASSIGNMENT_STARTED
    any_progress = assignment_launched or any(item_has_progress(i) for i in rows)

    def _ids(seq: list[dict[str, Any]]) -> list[str]:
        return [str(i.get("item_id") or i.get("document_type") or "") for i in seq]

    if _norm(assignment_status) in ASSIGNMENT_TERMINAL:
        state = STATE_BLOCKED
        reason = f"assignment_{_norm(assignment_status)}"
    elif required and not open_required:
        state = STATE_COMPLETED
        reason = "all_required_satisfied"
    elif not required:
        # No required work defined: not a completion claim.
        state = STATE_NOT_STARTED if not any_progress else STATE_IN_PROGRESS
        reason = "no_required_items"
    elif previously_completed:
        state = STATE_REOPENED
        reason = "required_work_after_completion"
    elif open_required and blocked and len(blocked) == len(open_required):
        state = STATE_BLOCKED
        reason = "all_open_required_blocked"
    elif not any_progress:
        # Onboarding not launched and nothing submitted, reviewed, waived or
        # corrected yet: distinct from waiting_on_*, which implies work is
        # already underway.
        state = STATE_NOT_STARTED
        reason = "no_progress_yet"
    elif waiting_employee:
        state = STATE_WAITING_ON_EMPLOYEE
        reason = "employee_action_required"
    elif waiting_hr:
        state = STATE_WAITING_ON_HR
        reason = "hr_action_required"
    else:
        state = STATE_IN_PROGRESS
        reason = "progress_without_actor_ask"

    return {
        "contract_version": CONTRACT_VERSION,
        "state": state,
        "reason": reason,
        "is_complete": state == STATE_COMPLETED,
        "required_total": len(required),
        "satisfied_count": len(satisfied),
        "open_count": len(open_required),
        "counts": {
            "satisfied_accepted": len(buckets.get(ITEM_SATISFIED_ACCEPTED, [])),
            "satisfied_waived": len(buckets.get(ITEM_SATISFIED_WAIVED, [])),
            "satisfied_not_applicable": len(buckets.get(ITEM_SATISFIED_NOT_APPLICABLE, [])),
            "waiting_employee": len(waiting_employee),
            "waiting_hr": len(waiting_hr),
            "waiting_other": len(waiting_other),
            "blocked": len(blocked),
            "optional_total": len([i for i in rows if not item_is_required(i)]),
        },
        "waiting_on_employee_items": _ids(waiting_employee),
        "waiting_on_hr_items": _ids(waiting_hr),
        "blocked_items": _ids(blocked),
        "satisfied_items": _ids(satisfied),
        # Legacy mirrors so older clients keep working during rollout.
        "legacy_onboarding_status": "completed" if state == STATE_COMPLETED else (
            "not_started" if state == STATE_NOT_STARTED else "in_progress"
        ),
        "documents_pending": len(open_required),
        "documents_complete": len(satisfied),
    }


# Order in which an open item becomes "the next action". Mirrors the state
# precedence in compute_completion, so the named item always explains the state.
NEXT_ITEM_CLASS_PRIORITY = (
    ITEM_WAITING_EMPLOYEE,
    ITEM_WAITING_HR,
    ITEM_WAITING_OTHER,
    ITEM_BLOCKED,
)


def _next_item_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    """Deterministic order inside one class: actionable, then soonest due."""
    due = item.get("due_date")
    due_key = str(due)[:10] if due is not None else "9999-12-31"
    try:
        order = int(item.get("sort_order") or 0)
    except Exception:
        order = 0
    return (1 if item_is_blocked(item) else 0, due_key, order, str(item.get("item_id") or ""))


def select_next_item(items: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The one open item every surface must name as "what happens next".

    Selection has to be derived from the same rows and the same filter as
    `compute_completion`, or the queue names one item while the drawer and the
    app name another. Required-only, because an optional item cannot be what a
    required-item state such as `waiting_on_hr` is waiting for.
    """
    rows = [dict(i) for i in items or []]
    _enrich_responsible_party(rows)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        if not item_is_required(item):
            continue
        cls = classify_item(item)
        if cls in SATISFIED_CLASSES:
            continue
        buckets.setdefault(cls, []).append(item)
    for cls in NEXT_ITEM_CLASS_PRIORITY:
        bucket = buckets.get(cls) or []
        if bucket:
            return sorted(bucket, key=_next_item_sort_key)[0]
    return None


def current_actor(snapshot: Mapping[str, Any]) -> str:
    """Who holds the open work, in the same priority `select_next_item` uses.

    Derived from the snapshot's own buckets so the owner named by `next_action`
    and the owner of the named next item can never disagree.
    """
    counts = snapshot.get("counts") or {}

    def _n(name: str) -> int:
        try:
            return int(counts.get(name) or 0)
        except Exception:
            return 0

    if _n("waiting_employee"):
        return "employee"
    if _n("waiting_hr"):
        return "hr"
    if _n("waiting_other"):
        return "system"
    if _n("blocked"):
        return "hr"
    return "none"


# What each actor is expected to do, reused wherever a state does not by itself
# name an owner (`reopened` is a history fact, not an ownership fact).
_ACTOR_ASK = {
    "employee": (
        "Complete the remaining items assigned to you.",
        "أكمل البنود المتبقية المطلوبة منك.",
    ),
    "hr": (
        "HR needs to review what has been submitted.",
        "الموارد البشرية بحاجة لمراجعة ما تم إرساله.",
    ),
    "system": (
        "Payroll or HR is finishing the remaining items — nothing is needed from you.",
        "الرواتب أو الموارد البشرية تُكمل البنود المتبقية — لا يلزم إجراء منك.",
    ),
    "none": (
        "Nothing further is required.",
        "لا يلزم شيء إضافي.",
    ),
}


def next_action(snapshot: Mapping[str, Any], *, locale: str = "en") -> dict[str, Any]:
    """One unambiguous "what happens next" for every surface. No dead ends."""
    state = _norm(snapshot.get("state")) or STATE_NOT_STARTED
    is_ar = str(locale).lower().startswith("ar")
    if state == STATE_REOPENED:
        # Reopened says when the work appeared, not who owns it: ask the buckets.
        actor = current_actor(snapshot)
        ask_en, ask_ar = _ACTOR_ASK.get(actor, _ACTOR_ASK["none"])
        return {
            "owner": actor,
            "message": (f"تم إعادة فتح الالتحاق — {ask_ar}" if is_ar else f"Onboarding reopened — {ask_en}"),
            "message_en": f"Onboarding reopened — {ask_en}",
            "message_ar": f"تم إعادة فتح الالتحاق — {ask_ar}",
        }
    table = {
        STATE_NOT_STARTED: (
            "employee",
            "Start your onboarding checklist.",
            "ابدأ قائمة الالتحاق الخاصة بك.",
        ),
        STATE_IN_PROGRESS: (
            "system",
            "Onboarding is in progress — no action needed from you right now.",
            "الالتحاق قيد التقدم — لا يلزم إجراء منك الآن.",
        ),
        STATE_WAITING_ON_EMPLOYEE: (
            "employee",
            "Complete the remaining items assigned to you.",
            "أكمل البنود المتبقية المطلوبة منك.",
        ),
        STATE_WAITING_ON_HR: (
            "hr",
            "HR needs to review what has been submitted.",
            "الموارد البشرية بحاجة لمراجعة ما تم إرساله.",
        ),
        STATE_BLOCKED: (
            "hr",
            "Blocked by prerequisites — HR must resolve the blocking item.",
            "متوقف بسبب متطلبات سابقة — يجب على الموارد البشرية معالجتها.",
        ),
        STATE_COMPLETED: (
            "none",
            "Onboarding is complete. Nothing further is required.",
            "تم إكمال الالتحاق. لا يلزم شيء إضافي.",
        ),
    }
    owner, en, ar = table.get(state, table[STATE_IN_PROGRESS])
    return {"owner": owner, "message": ar if is_ar else en, "message_en": en, "message_ar": ar}


# ---------------------------------------------------------------------------
# Checklist loading — tolerant of schema drift between environments
# ---------------------------------------------------------------------------
CHECKLIST_COLUMNS_WANTED = (
    "item_id",
    "label",
    "status",
    "required",
    "owner",
    "authority",
    "category",
    "item_type",
    "collection_mode",
    "document_type",
    "depends_on",
    "lifecycle_meta",
    "rejection_reason",
    "due_date",
    "updated_at",
)
_CHECKLIST_COLUMNS_CACHE: list[str] | None = None


def reset_checklist_column_cache() -> None:
    global _CHECKLIST_COLUMNS_CACHE
    _CHECKLIST_COLUMNS_CACHE = None


def _checklist_columns(cur: Any) -> list[str]:
    """Only select columns this deployment actually has."""
    global _CHECKLIST_COLUMNS_CACHE
    if _CHECKLIST_COLUMNS_CACHE is not None:
        return list(_CHECKLIST_COLUMNS_CACHE)
    present: set[str] = set()
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='onboarding_items'"
        )
        for row in cur.fetchall() or []:
            try:
                present.add(str(row["column_name"]))
            except Exception:
                present.add(str(row[0]))
    except Exception:
        present = set()
    cols = [c for c in CHECKLIST_COLUMNS_WANTED if c in present] or [
        "item_id",
        "status",
        "required",
    ]
    _CHECKLIST_COLUMNS_CACHE = cols
    return list(cols)


def _enrich_responsible_party(rows: list[dict[str, Any]]) -> None:
    """Reuse the lifecycle module's ownership rule when it is importable."""
    resolver = None
    try:
        import onboarding_lifecycle_wave2a as _lifecycle

        resolver = getattr(_lifecycle, "responsible_party", None)
    except Exception:
        resolver = None
    for row in rows:
        if row.get("responsible_party"):
            continue
        if callable(resolver):
            try:
                row["responsible_party"] = resolver(row)
                continue
            except Exception:
                pass
        row["responsible_party"] = _norm(row.get("owner")) or "hr"


# ---------------------------------------------------------------------------
# Persistence — append-only evidence, atomic idempotent transition
# ---------------------------------------------------------------------------
def ensure_completion_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_onboarding_completion (
          company_code text NOT NULL,
          employee_key text NOT NULL,
          state text NOT NULL,
          reason text,
          contract_version text NOT NULL,
          required_total int NOT NULL DEFAULT 0,
          satisfied_count int NOT NULL DEFAULT 0,
          open_count int NOT NULL DEFAULT 0,
          waiting_employee_count int NOT NULL DEFAULT 0,
          waiting_hr_count int NOT NULL DEFAULT 0,
          blocked_count int NOT NULL DEFAULT 0,
          first_completed_at timestamptz,
          last_completed_at timestamptz,
          reopened_at timestamptz,
          reopen_count int NOT NULL DEFAULT 0,
          snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          completion_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
          row_version bigint NOT NULL DEFAULT 1,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_onboarding_completion_events (
          event_id bigserial PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          from_state text,
          to_state text NOT NULL,
          reason text,
          actor text,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employee_onboarding_completion_events_key_idx
        ON employee_onboarding_completion_events (company_code, employee_key, created_at DESC)
        """
    )
    _ensure_employee_cascade(cur)


# A completion snapshot for a deleted employee is unreachable state that still
# counts in reporting aggregates. Cascade ties its lifetime to the employee row
# regardless of which code path performs the delete.
_CASCADE_TABLES = (
    "employee_onboarding_completion",
    "employee_onboarding_completion_events",
)


def _ensure_employee_cascade(cur: Any) -> None:
    for table in _CASCADE_TABLES:
        constraint = f"{table}_employee_fk"
        try:
            cur.execute("SAVEPOINT completion_fk_step")
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conname=%s AND conrelid=%s::regclass",
                (constraint, table),
            )
            if cur.fetchone():
                cur.execute("RELEASE SAVEPOINT completion_fk_step")
                continue
            cur.execute(
                f"DELETE FROM {table} WHERE employee_key NOT IN (SELECT employee_key FROM employees)"
            )
            cur.execute(
                f"""
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint}
                FOREIGN KEY (employee_key) REFERENCES employees (employee_key)
                ON DELETE CASCADE
                """
            )
            cur.execute("RELEASE SAVEPOINT completion_fk_step")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT completion_fk_step")


def load_completion_row(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM employee_onboarding_completion
        WHERE company_code=%s AND employee_key=%s
        """,
        (str(company_code).upper(), employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def seed_legacy_completion_history(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    completed_at: Any,
    source: str,
) -> bool:
    """Record that an employee was already complete before this contract existed.

    Without this, a legacy-completed employee has no `first_completed_at`, so a
    later requirement change reads as `waiting_on_*` instead of `reopened`. The
    stamp is immutable once set and the evidence entry is append-only.
    """
    ensure_completion_schema(cur)
    cur.execute(
        """
        INSERT INTO employee_onboarding_completion (
          company_code, employee_key, state, reason, contract_version,
          first_completed_at, last_completed_at, completion_evidence, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s, jsonb_build_array(%s::jsonb), now())
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          first_completed_at=COALESCE(
            employee_onboarding_completion.first_completed_at, EXCLUDED.first_completed_at
          ),
          last_completed_at=COALESCE(
            employee_onboarding_completion.last_completed_at, EXCLUDED.last_completed_at
          ),
          completion_evidence=employee_onboarding_completion.completion_evidence
            || CASE WHEN employee_onboarding_completion.first_completed_at IS NULL
                    THEN EXCLUDED.completion_evidence ELSE '[]'::jsonb END,
          updated_at=now()
        WHERE employee_onboarding_completion.first_completed_at IS NULL
        RETURNING employee_key
        """,
        (
            str(company_code).upper(),
            employee_key,
            STATE_COMPLETED,
            "legacy_completion_backfill",
            CONTRACT_VERSION,
            completed_at,
            completed_at,
            json.dumps(
                {
                    "at": str(completed_at),
                    "source": source,
                    "note": "completion predates the completion contract",
                },
                default=str,
            ),
        ),
    )
    return bool(cur.fetchone())


def previously_completed_flag(cur: Any, *, company_code: str, employee_key: str) -> bool:
    """Read-only history probe for projections. Never raises, never writes."""
    try:
        row = load_completion_row(cur, company_code=company_code, employee_key=employee_key)
    except Exception:
        return False
    return bool((row or {}).get("first_completed_at"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_completion(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    snapshot: Mapping[str, Any],
    actor: str | None = None,
) -> dict[str, Any]:
    """Atomic + idempotent completion transition.

    Re-running with an unchanged snapshot produces no new event and keeps
    `first_completed_at` stable. Completion evidence is append-only.
    """
    ensure_completion_schema(cur)
    company = str(company_code).upper()
    prior = load_completion_row(cur, company_code=company, employee_key=employee_key)
    prior_state = str((prior or {}).get("state") or "") or None
    state = str(snapshot.get("state"))
    counts = dict(snapshot.get("counts") or {})

    is_complete = state == STATE_COMPLETED
    became_complete = is_complete and prior_state != STATE_COMPLETED
    reopened_now = (
        prior_state == STATE_COMPLETED and state != STATE_COMPLETED
    )

    evidence_entry = None
    if became_complete:
        evidence_entry = {
            "completed_at": _now(),
            "contract_version": snapshot.get("contract_version"),
            "required_total": snapshot.get("required_total"),
            "satisfied_items": list(snapshot.get("satisfied_items") or []),
            "actor": actor,
        }

    cur.execute(
        """
        INSERT INTO employee_onboarding_completion (
          company_code, employee_key, state, reason, contract_version,
          required_total, satisfied_count, open_count,
          waiting_employee_count, waiting_hr_count, blocked_count,
          first_completed_at, last_completed_at, reopened_at, reopen_count,
          snapshot, completion_evidence, row_version, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,
          %s,%s,%s,
          %s,%s,%s,
          CASE WHEN %s THEN now() ELSE NULL END,
          CASE WHEN %s THEN now() ELSE NULL END,
          CASE WHEN %s THEN now() ELSE NULL END,
          CASE WHEN %s THEN 1 ELSE 0 END,
          %s::jsonb,
          CASE WHEN %s::jsonb IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(%s::jsonb) END,
          1, now()
        )
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          state=EXCLUDED.state,
          reason=EXCLUDED.reason,
          contract_version=EXCLUDED.contract_version,
          required_total=EXCLUDED.required_total,
          satisfied_count=EXCLUDED.satisfied_count,
          open_count=EXCLUDED.open_count,
          waiting_employee_count=EXCLUDED.waiting_employee_count,
          waiting_hr_count=EXCLUDED.waiting_hr_count,
          blocked_count=EXCLUDED.blocked_count,
          -- first completion stamp is immutable
          first_completed_at=COALESCE(employee_onboarding_completion.first_completed_at, EXCLUDED.first_completed_at),
          last_completed_at=COALESCE(EXCLUDED.last_completed_at, employee_onboarding_completion.last_completed_at),
          reopened_at=COALESCE(EXCLUDED.reopened_at, employee_onboarding_completion.reopened_at),
          reopen_count=employee_onboarding_completion.reopen_count + EXCLUDED.reopen_count,
          snapshot=EXCLUDED.snapshot,
          -- append-only: never drop historical completion evidence
          completion_evidence=employee_onboarding_completion.completion_evidence
            || CASE WHEN jsonb_array_length(EXCLUDED.completion_evidence) > 0
                    THEN EXCLUDED.completion_evidence ELSE '[]'::jsonb END,
          row_version=employee_onboarding_completion.row_version + 1,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            employee_key,
            state,
            str(snapshot.get("reason") or ""),
            str(snapshot.get("contract_version") or CONTRACT_VERSION),
            int(snapshot.get("required_total") or 0),
            int(snapshot.get("satisfied_count") or 0),
            int(snapshot.get("open_count") or 0),
            int(counts.get("waiting_employee") or 0),
            int(counts.get("waiting_hr") or 0),
            int(counts.get("blocked") or 0),
            became_complete,
            became_complete,
            reopened_now,
            reopened_now,
            json.dumps(dict(snapshot), default=str),
            json.dumps(evidence_entry, default=str) if evidence_entry else None,
            json.dumps(evidence_entry, default=str) if evidence_entry else None,
        ),
    )
    saved = dict(cur.fetchone() or {})

    if prior_state != state:
        cur.execute(
            """
            INSERT INTO employee_onboarding_completion_events (
              company_code, employee_key, from_state, to_state, reason, actor, detail
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                company,
                employee_key,
                prior_state,
                state,
                str(snapshot.get("reason") or ""),
                actor,
                json.dumps(
                    {
                        "required_total": snapshot.get("required_total"),
                        "open_count": snapshot.get("open_count"),
                        "waiting_on_employee_items": snapshot.get("waiting_on_employee_items"),
                        "waiting_on_hr_items": snapshot.get("waiting_on_hr_items"),
                        "blocked_items": snapshot.get("blocked_items"),
                    },
                    default=str,
                ),
            ),
        )
    return saved


def recompute(
    cur: Any,
    *,
    employee_key: str,
    company_code: str | None = None,
    actor: str | None = None,
    mirror_legacy_columns: bool = True,
) -> dict[str, Any]:
    """Load checklist rows, derive canonical completion, persist, mirror legacy.

    This is the ONLY function that should write employees.onboarding_status.
    """
    ensure_completion_schema(cur)
    cur.execute(
        "SELECT company_code FROM employees WHERE employee_key=%s LIMIT 1",
        (employee_key,),
    )
    emp = dict(cur.fetchone() or {})
    company = str(company_code or emp.get("company_code") or "WATHEFNI").upper()

    cols = _checklist_columns(cur)
    cur.execute(
        f"SELECT {', '.join(cols)} FROM onboarding_items WHERE employee_key=%s",
        (employee_key,),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]

    # Ownership must match what the HR/employee projections render, otherwise
    # one surface can say "waiting on HR" while another says "waiting on you".
    _enrich_responsible_party(rows)

    # Dependency blocking uses the canonical satisfaction test.
    by_id = {str(r.get("item_id") or ""): r for r in rows}
    for row in rows:
        raw = row.get("depends_on") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        blockers: list[str] = []
        for dep in raw or []:
            dep_row = by_id.get(str(dep))
            if not dep_row or not item_is_satisfied(dep_row.get("status")):
                blockers.append(str(dep))
        row["blocked_by"] = blockers

    assignment_status = None
    try:
        cur.execute(
            "SELECT status FROM employee_onboarding_assignments WHERE employee_key=%s LIMIT 1",
            (employee_key,),
        )
        assignment_status = (dict(cur.fetchone() or {}) or {}).get("status")
    except Exception:
        assignment_status = None

    prior = load_completion_row(cur, company_code=company, employee_key=employee_key)
    previously_completed = bool((prior or {}).get("first_completed_at"))

    snapshot = compute_completion(
        rows,
        previously_completed=previously_completed,
        assignment_status=assignment_status,
    )
    saved = persist_completion(
        cur,
        company_code=company,
        employee_key=employee_key,
        snapshot=snapshot,
        actor=actor,
    )

    if mirror_legacy_columns:
        # Legacy columns stay in sync so older readers cannot disagree.
        #
        # employees.updated_at is deliberately NOT touched here. ESS uses it as
        # the hub optimistic-concurrency token, so bumping it for derived
        # counters would make unrelated in-flight employee requests fail stale
        # whenever any checklist item moved. Completion has its own timestamps
        # in employee_onboarding_completion.
        cur.execute(
            """
            UPDATE employees
            SET documents_pending=%s,
                documents_complete=%s,
                onboarding_status=%s
            WHERE employee_key=%s
              AND (documents_pending, documents_complete, coalesce(onboarding_status,''))
                  IS DISTINCT FROM (%s, %s, %s)
            """,
            (
                int(snapshot["documents_pending"]),
                int(snapshot["documents_complete"]),
                snapshot["legacy_onboarding_status"],
                employee_key,
                int(snapshot["documents_pending"]),
                int(snapshot["documents_complete"]),
                snapshot["legacy_onboarding_status"],
            ),
        )
        # Assignment completed_at reflects canonical completion only.
        try:
            if snapshot["is_complete"]:
                cur.execute(
                    """
                    UPDATE employee_onboarding_assignments
                    SET status='completed',
                        completed_at=COALESCE(completed_at, now()),
                        updated_at=now()
                    WHERE employee_key=%s AND status NOT IN ('cancelled','abandoned')
                    """,
                    (employee_key,),
                )
            else:
                cur.execute(
                    """
                    UPDATE employee_onboarding_assignments
                    SET status=CASE WHEN status='completed' THEN 'in_progress' ELSE status END,
                        updated_at=now()
                    WHERE employee_key=%s AND status NOT IN ('cancelled','abandoned')
                    """,
                    (employee_key,),
                )
        except Exception:
            pass

    snapshot["persisted"] = {
        "state": saved.get("state"),
        "first_completed_at": saved.get("first_completed_at"),
        "last_completed_at": saved.get("last_completed_at"),
        "reopened_at": saved.get("reopened_at"),
        "reopen_count": saved.get("reopen_count"),
        "row_version": saved.get("row_version"),
        "completion_evidence_count": len(saved.get("completion_evidence") or []),
    }
    return snapshot


def completion_view(
    cur: Any,
    *,
    employee_key: str,
    company_code: str | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Read-only canonical view for any surface. Never mutates."""
    company = str(company_code or "WATHEFNI").upper()
    row = load_completion_row(cur, company_code=company, employee_key=employee_key)
    if not row:
        return {
            "contract_version": CONTRACT_VERSION,
            "state": STATE_NOT_STARTED,
            "is_complete": False,
            "required_total": 0,
            "satisfied_count": 0,
            "open_count": 0,
            "next_action": next_action({"state": STATE_NOT_STARTED}, locale=locale),
            "computed": False,
        }
    snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
    out = dict(snapshot)
    out.update(
        {
            "state": row.get("state"),
            "is_complete": row.get("state") == STATE_COMPLETED,
            "first_completed_at": row.get("first_completed_at"),
            "last_completed_at": row.get("last_completed_at"),
            "reopened_at": row.get("reopened_at"),
            "reopen_count": row.get("reopen_count"),
            "computed": True,
        }
    )
    out["next_action"] = next_action(out, locale=locale)
    return out


def completion_history(
    cur: Any, *, employee_key: str, company_code: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    company = str(company_code or "WATHEFNI").upper()
    cur.execute(
        """
        SELECT from_state, to_state, reason, actor, detail, created_at
        FROM employee_onboarding_completion_events
        WHERE company_code=%s AND employee_key=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (company, employee_key, int(limit)),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


# ---------------------------------------------------------------------------
# Reminder eligibility — channel-agnostic and deduplicated at the contract level
# ---------------------------------------------------------------------------
def reminder_targets(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Which party should be reminded, and for which items.

    Channel-agnostic: callers pick WhatsApp/email/push. Dedup key is stable so
    the same pending set never produces two reminders.
    """
    state = _norm(snapshot.get("state"))
    if state in {STATE_COMPLETED, STATE_NOT_STARTED} and state == STATE_COMPLETED:
        return {"party": "none", "items": [], "dedup_key": None}
    if state in {STATE_WAITING_ON_EMPLOYEE, STATE_REOPENED, STATE_NOT_STARTED}:
        items = list(snapshot.get("waiting_on_employee_items") or [])
        party = "employee"
    elif state == STATE_WAITING_ON_HR:
        items = list(snapshot.get("waiting_on_hr_items") or [])
        party = "hr"
    elif state == STATE_BLOCKED:
        items = list(snapshot.get("blocked_items") or [])
        party = "hr"
    else:
        return {"party": "none", "items": [], "dedup_key": None}
    if not items:
        return {"party": "none", "items": [], "dedup_key": None}
    key = f"onboarding:{state}:{party}:" + ",".join(sorted(items))
    return {"party": party, "items": items, "dedup_key": key}


def contract_flag_enabled(*, company_code: str | None = None) -> bool:
    """Canonical-contract rollout flag. Legacy mirrors stay written either way."""
    raw = (os.environ.get("WATHEFNI_ONBOARDING_COMPLETION_CONTRACT") or "").strip().lower()
    if raw not in {"1", "true", "yes", "on", "enabled"}:
        return False
    companies = {
        c.strip().upper()
        for c in (os.environ.get("WATHEFNI_ONBOARDING_COMPLETION_CONTRACT_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    }
    if company_code and str(company_code).upper() not in companies:
        return False
    return True
