"""Multi-User Wave 4 — personal work queues (My work / Company work).

Shared company truth remains in compute_work_queue; this module applies
backend-authoritative assignment filtering and enriches every task with
owner, due_state, next_action, and source. Company scope is oversight-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

import prehire_overview as _overview
import prehire_visibility as _visibility

WORK_SCOPES = frozenset({"mine", "company"})
AUDIENCE_PERSONAL = "personal"
AUDIENCE_COMPANY = "company"

ACTION_INTERVIEW_FEEDBACK = "interview_feedback"
ACTION_OVERDUE_TASK = "overdue_task"
ACTION_APPROVAL = "approval_needed"
ACTION_JOB_OWNED = "job_owned_attention"

SOURCE_APPLICATION_OWNER = "application_owner"
SOURCE_JOB_RECRUITER = "job_recruiter"
SOURCE_JOB_HIRING_MANAGER = "job_hiring_manager"
SOURCE_INTERVIEW_ASSIGNMENT = "interview_assignment"
SOURCE_TASK_ASSIGNEE = "task_assignee"
SOURCE_APPROVAL_ASSIGNEE = "approval_assignee"
SOURCE_COMPANY_OPS = "company_ops"


class PersonalWorkScopeError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def as_detail(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _user_id(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return str(UUID(raw))
    except (TypeError, ValueError):
        return raw


def normalize_work_scope(value: Any) -> str:
    key = _text(value).lower().replace("-", "_")
    if key in {"my", "my_work", "personal", "assigned"}:
        return "mine"
    if key in {"company", "company_work", "all", "shared"}:
        return "company"
    if key in WORK_SCOPES:
        return key
    return ""


def resolve_work_scope(
    *,
    requested: Any,
    role: str | None,
    default_mine: bool = True,
) -> str:
    """Return mine|company. Company requires oversight; default is My work."""
    oversight = _visibility.actor_has_prehire_oversight(role)
    scope = normalize_work_scope(requested)
    if not scope:
        scope = "mine" if default_mine else ("company" if oversight else "mine")
    if scope == "company" and not oversight:
        raise PersonalWorkScopeError(
            "company_work_forbidden",
            "Company work is only available to HR leadership with company-wide oversight.",
            status_code=403,
        )
    return scope


def _due_state(*, age_hours: float, sla_hours: float | None = None, is_overdue: bool | None = None) -> str:
    if is_overdue is True:
        return "overdue"
    sla = float(sla_hours or 0)
    age = float(age_hours or 0)
    if sla > 0 and age >= sla:
        return "overdue"
    if sla > 0 and age >= max(1.0, sla * 0.7):
        return "due_soon"
    return "open"


def _next_action_label(action_type: str) -> str:
    key = _text(action_type).lower()
    mapping = {
        _overview.ACTION_FOLLOW_UP: "Follow up with candidate",
        _overview.ACTION_READY_FOR_REVIEW: "Review candidate",
        _overview.ACTION_ASSESSMENT_PENDING: "Act on assessment",
        _overview.ACTION_INTERVIEW_SCHEDULING: "Schedule interview",
        ACTION_INTERVIEW_FEEDBACK: "Submit interview feedback",
        ACTION_OVERDUE_TASK: "Complete overdue task",
        ACTION_APPROVAL: "Approve or reject",
        ACTION_JOB_OWNED: "Review owned role",
    }
    if key in mapping:
        return mapping[key]
    if "assessment" in key:
        return "Act on assessment"
    if "interview" in key:
        return "Open interview"
    if "follow" in key:
        return "Follow up with candidate"
    return "Open task"


def _sla_for_action(action_type: str, sla: dict[str, Any]) -> float:
    key = _text(action_type).lower()
    if "follow" in key:
        return float(sla.get("follow_up_hours") or 24)
    if "ready" in key or "review" in key:
        return float(sla.get("ready_for_review_hours") or 48)
    if "assessment" in key:
        return float(sla.get("assessment_pending_hours") or 72)
    if key == ACTION_OVERDUE_TASK:
        return 0.0
    if key == ACTION_INTERVIEW_FEEDBACK:
        return 24.0
    return 48.0


def load_user_labels(cur: Any, *, company: str, user_ids: set[str]) -> dict[str, str]:
    ids = sorted({uid for uid in user_ids if uid})
    if not ids:
        return {}
    cur.execute(
        """
        SELECT CAST(user_id AS text) AS user_id,
               COALESCE(NULLIF(name, ''), NULLIF(email, ''), CAST(user_id AS text)) AS label
        FROM dashboard_users
        WHERE company_code=%s AND CAST(user_id AS text) = ANY(%s)
        """,
        (company, ids),
    )
    return {_text(row.get("user_id")): _text(row.get("label")) for row in cur.fetchall()}


def load_app_responsibility(
    cur: Any,
    *,
    company: str,
    app_keys: list[str],
) -> dict[str, dict[str, Any]]:
    keys = sorted({_text(k) for k in app_keys if _text(k)})
    if not keys:
        return {}
    cur.execute(
        """
        SELECT
          a.app_key,
          CAST(a.owner_user_id AS text) AS owner_user_id,
          a.position_code,
          CAST(p.recruiter_user_id AS text) AS recruiter_user_id,
          CAST(p.hiring_manager_user_id AS text) AS hiring_manager_user_id,
          COALESCE(NULLIF(p.title, ''), NULLIF(a.position_title, ''), a.position_code) AS position_title
        FROM applications a
        LEFT JOIN positions p
          ON p.company_code=a.company_code AND p.position_code=a.position_code
        WHERE a.company_code=%s AND a.app_key = ANY(%s)
        """,
        (company, keys),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        out[_text(row.get("app_key"))] = {
            "owner_user_id": _text(row.get("owner_user_id")) or None,
            "recruiter_user_id": _text(row.get("recruiter_user_id")) or None,
            "hiring_manager_user_id": _text(row.get("hiring_manager_user_id")) or None,
            "position_code": _text(row.get("position_code")) or None,
            "position_title": _text(row.get("position_title")) or None,
        }
    return out


def responsibility_for_actor(
    meta: dict[str, Any] | None,
    *,
    actor_user_id: str,
    interview_app_keys: set[str] | None = None,
    app_key: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Return (is_mine, owner_user_id, source)."""
    actor = _text(actor_user_id)
    if not actor:
        return False, None, None
    data = meta or {}
    owner = _text(data.get("owner_user_id")) or None
    recruiter = _text(data.get("recruiter_user_id")) or None
    hm = _text(data.get("hiring_manager_user_id")) or None
    if owner and owner == actor:
        return True, owner, SOURCE_APPLICATION_OWNER
    if recruiter and recruiter == actor:
        return True, recruiter, SOURCE_JOB_RECRUITER
    if hm and hm == actor:
        return True, hm, SOURCE_JOB_HIRING_MANAGER
    if app_key and interview_app_keys and app_key in interview_app_keys:
        return True, actor, SOURCE_INTERVIEW_ASSIGNMENT
    return False, owner or recruiter or hm, None


def item_app_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    primary = _text(item.get("app_key") or item.get("primary_app_key"))
    if primary:
        keys.append(primary)
    for app in item.get("applications") or []:
        if isinstance(app, dict):
            key = _text(app.get("app_key"))
            if key:
                keys.append(key)
    for action in item.get("actions") or []:
        if isinstance(action, dict):
            key = _text(action.get("app_key"))
            if key:
                keys.append(key)
    # preserve order, unique
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def enrich_work_item(
    item: dict[str, Any],
    *,
    audience: str,
    owner_user_id: str | None,
    owner_label: str | None,
    source: str,
    due_state: str,
    entity_type: str,
    entity_id: str | None,
    next_action: str | None = None,
) -> dict[str, Any]:
    enriched = dict(item)
    action_type = _text(enriched.get("action_type"))
    enriched.update(
        {
            "audience": audience,
            "owner_user_id": owner_user_id,
            "owner": owner_label or owner_user_id or ("Unassigned" if audience == AUDIENCE_COMPANY else "You"),
            "due_state": due_state,
            "next_action": next_action or _next_action_label(action_type),
            "source": source,
            "entity_type": entity_type,
            "entity_id": entity_id or _text(enriched.get("app_key")) or _text(enriched.get("person_key")) or None,
            "work_scope": "mine" if audience == AUDIENCE_PERSONAL else "company",
        }
    )
    return enriched


def _actor_interview_app_keys(
    cur: Any,
    *,
    company: str,
    actor_user_id: str,
    actor_email: str | None = None,
    actor_phone: str | None = None,
) -> set[str]:
    clauses: list[str] = []
    params: list[Any] = [company]
    actor = _text(actor_user_id)
    if actor:
        clauses.append("LOWER(COALESCE(a.assignee_user_id, '')) = LOWER(%s)")
        params.append(actor)
    email = _text(actor_email).lower()
    if email:
        clauses.append("LOWER(COALESCE(a.assignee_email, '')) = LOWER(%s)")
        params.append(email)
    phone = "".join(ch for ch in _text(actor_phone) if ch.isdigit())
    if phone:
        clauses.append("regexp_replace(COALESCE(a.assignee_phone, ''), '\\D', '', 'g') = %s")
        params.append(phone)
    if not clauses:
        return set()
    cur.execute(
        f"""
        SELECT DISTINCT a.app_key
        FROM candidate_interview_assignments a
        WHERE a.company_code=%s AND ({' OR '.join(clauses)})
        """,
        params,
    )
    return {_text(row.get("app_key")) for row in cur.fetchall() if _text(row.get("app_key"))}


def _owned_position_codes(cur: Any, *, company: str, actor_user_id: str) -> set[str]:
    actor = _text(actor_user_id)
    if not actor:
        return set()
    cur.execute(
        """
        SELECT position_code
        FROM positions
        WHERE company_code=%s
          AND (
            CAST(recruiter_user_id AS text)=%s
            OR CAST(hiring_manager_user_id AS text)=%s
            OR CAST(created_by_user_id AS text)=%s
          )
        """,
        (company, actor, actor, actor),
    )
    return {_text(row.get("position_code")) for row in cur.fetchall() if _text(row.get("position_code"))}


def fetch_interview_feedback_items(
    cur: Any,
    *,
    company: str,
    actor_user_id: str,
    actor_email: str | None,
    actor_phone: str | None,
    now: datetime,
    user_labels: dict[str, str],
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = [company]
    actor = _text(actor_user_id)
    if actor:
        clauses.append("LOWER(COALESCE(cia.assignee_user_id, '')) = LOWER(%s)")
        params.append(actor)
    email = _text(actor_email).lower()
    if email:
        clauses.append("LOWER(COALESCE(cia.assignee_email, '')) = LOWER(%s)")
        params.append(email)
    phone = "".join(ch for ch in _text(actor_phone) if ch.isdigit())
    if phone:
        clauses.append("regexp_replace(COALESCE(cia.assignee_phone, ''), '\\D', '', 'g') = %s")
        params.append(phone)
    if not clauses:
        return []
    cur.execute(
        f"""
        SELECT
          ci.interview_id::text AS interview_id,
          ci.app_key,
          ci.status,
          ci.feedback_status,
          ci.human_feedback_status,
          ci.scheduled_start,
          COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
          COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
          a.position_code,
          EXTRACT(EPOCH FROM (NOW() - COALESCE(ci.updated_at, ci.created_at))) / 3600.0 AS age_hours
        FROM candidate_interview_assignments cia
        JOIN candidate_interviews ci ON ci.interview_id=cia.interview_id
        JOIN applications a ON a.app_key=ci.app_key AND a.company_code=ci.company_code
        LEFT JOIN candidates c ON c.phone=a.phone
        WHERE cia.company_code=%s
          AND ({' OR '.join(clauses)})
          AND COALESCE(NULLIF(ci.human_feedback_status, ''), NULLIF(ci.feedback_status, ''), 'notes_pending')
                <> 'feedback_complete'
          AND COALESCE(ci.status, '') NOT IN ('cancelled', 'canceled')
        ORDER BY ci.updated_at DESC NULLS LAST
        LIMIT 50
        """,
        params,
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        age = float(row.get("age_hours") or 0.0)
        interview_id = _text(row.get("interview_id"))
        app_key = _text(row.get("app_key"))
        base = {
            "unit": "actions",
            "person_key": app_key or interview_id,
            "action_type": ACTION_INTERVIEW_FEEDBACK,
            "app_key": app_key,
            "candidate_name": row.get("candidate_name"),
            "position_code": row.get("position_code"),
            "position_title": row.get("position_title"),
            "status": row.get("status"),
            "stage": row.get("status"),
            "job_label": row.get("position_title") or row.get("position_code"),
            "reason": "Interview feedback assigned to you",
            "priority": int(min(99, 65 + min(20, int(age // 12)))),
            "age_hours": round(age, 1),
            "action_count": 1,
            "application_count": 1 if app_key else 0,
            "destination": {
                "page": "interviews",
                "filters": {"interview_id": interview_id, "feedback": "needed"},
                "cohort_key": ACTION_INTERVIEW_FEEDBACK,
            },
            "authority_source": "prehire_personal_work.interview_feedback",
            "as_of": now.astimezone(timezone.utc).isoformat(),
            "interview_id": interview_id,
        }
        items.append(
            enrich_work_item(
                base,
                audience=AUDIENCE_PERSONAL,
                owner_user_id=actor,
                owner_label=user_labels.get(actor) or "You",
                source=SOURCE_INTERVIEW_ASSIGNMENT,
                due_state=_due_state(age_hours=age, sla_hours=24),
                entity_type="interview",
                entity_id=interview_id,
                next_action=_next_action_label(ACTION_INTERVIEW_FEEDBACK),
            )
        )
    return items


def fetch_overdue_task_items(
    cur: Any,
    *,
    company: str,
    actor_user_id: str,
    now: datetime,
    user_labels: dict[str, str],
    timezone_name: str = "Asia/Kuwait",
) -> list[dict[str, Any]]:
    actor = _text(actor_user_id)
    if not actor:
        return []
    cur.execute(
        """
        SELECT
          t.task_id::text AS task_id,
          t.app_key,
          t.title,
          t.priority AS task_priority,
          t.due_at,
          t.status,
          COALESCE(NULLIF(c.name, ''), a.raw_json->>'candidate_name', a.phone) AS candidate_name,
          COALESCE(NULLIF(a.position_title, ''), a.position_code) AS position_title,
          a.position_code,
          EXTRACT(EPOCH FROM (NOW() - COALESCE(t.due_at, t.updated_at, t.created_at))) / 3600.0 AS age_hours
        FROM application_recruiter_tasks t
        JOIN applications a ON a.app_key=t.app_key AND a.company_code=t.company_code
        LEFT JOIN candidates c ON c.phone=a.phone
        WHERE t.company_code=%s
          AND CAST(t.assigned_to_user_id AS text)=%s
          AND t.status='open'
          AND t.due_at IS NOT NULL
          AND t.due_at < NOW()
        ORDER BY t.due_at ASC
        LIMIT 50
        """,
        (company, actor),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        age = float(row.get("age_hours") or 0.0)
        task_id = _text(row.get("task_id"))
        app_key = _text(row.get("app_key"))
        title = _text(row.get("title")) or "Overdue task"
        base = {
            "unit": "actions",
            "person_key": app_key or task_id,
            "action_type": ACTION_OVERDUE_TASK,
            "app_key": app_key,
            "candidate_name": row.get("candidate_name"),
            "position_code": row.get("position_code"),
            "position_title": row.get("position_title"),
            "status": row.get("status"),
            "stage": row.get("status"),
            "job_label": row.get("position_title") or row.get("position_code"),
            "reason": title,
            "priority": int(min(99, 80 + min(15, int(age // 12)))),
            "age_hours": round(age, 1),
            "action_count": 1,
            "application_count": 1 if app_key else 0,
            "destination": {
                "page": "candidates",
                "filters": {"q": app_key, "task_id": task_id},
                "cohort_key": ACTION_OVERDUE_TASK,
            },
            "authority_source": "prehire_personal_work.overdue_task",
            "as_of": now.astimezone(timezone.utc).isoformat(),
            "task_id": task_id,
            "due_at": row.get("due_at").isoformat() if hasattr(row.get("due_at"), "isoformat") else row.get("due_at"),
        }
        items.append(
            enrich_work_item(
                base,
                audience=AUDIENCE_PERSONAL,
                owner_user_id=actor,
                owner_label=user_labels.get(actor) or "You",
                source=SOURCE_TASK_ASSIGNEE,
                due_state="overdue",
                entity_type="task",
                entity_id=task_id,
                next_action=_next_action_label(ACTION_OVERDUE_TASK),
            )
        )
    return items


def fetch_approval_items(
    cur: Any,
    *,
    company: str,
    actor_phone: str | None,
    actor_user_id: str,
    now: datetime,
    user_labels: dict[str, str],
    action_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    phone = "".join(ch for ch in _text(actor_phone) if ch.isdigit())
    if not phone:
        return []
    types = list(action_types or [])
    if not types:
        return []
    cur.execute(
        """
        SELECT action_id::text AS pending_action_id,
               action_type,
               subject_key,
               created_at,
               EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600.0 AS age_hours
        FROM pending_actions
        WHERE status='pending'
          AND expires_at > now()
          AND admin_phone=%s
          AND action_type = ANY(%s)
        ORDER BY created_at ASC
        LIMIT 25
        """,
        (phone, types),
    )
    actor = _text(actor_user_id)
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        age = float(row.get("age_hours") or 0.0)
        pending_id = _text(row.get("pending_action_id"))
        action_type = _text(row.get("action_type")) or "approval"
        base = {
            "unit": "actions",
            "person_key": pending_id,
            "action_type": ACTION_APPROVAL,
            "app_key": _text(row.get("subject_key")) or None,
            "candidate_name": None,
            "position_code": None,
            "position_title": None,
            "status": "pending",
            "stage": "pending",
            "job_label": action_type,
            "reason": f"Approval needed: {action_type}",
            "priority": int(min(99, 75 + min(15, int(age // 12)))),
            "age_hours": round(age, 1),
            "action_count": 1,
            "application_count": 0,
            "destination": {"page": "ai", "filters": {"pending_action_id": pending_id}, "cohort_key": ACTION_APPROVAL},
            "authority_source": "prehire_personal_work.approval",
            "as_of": now.astimezone(timezone.utc).isoformat(),
            "pending_action_id": pending_id,
        }
        items.append(
            enrich_work_item(
                base,
                audience=AUDIENCE_PERSONAL,
                owner_user_id=actor,
                owner_label=user_labels.get(actor) or "You",
                source=SOURCE_APPROVAL_ASSIGNEE,
                due_state=_due_state(age_hours=age, sla_hours=12),
                entity_type="approval",
                entity_id=pending_id,
                next_action=_next_action_label(ACTION_APPROVAL),
            )
        )
    return items


def fetch_owned_job_items(
    cur: Any,
    *,
    company: str,
    actor_user_id: str,
    now: datetime,
    user_labels: dict[str, str],
) -> list[dict[str, Any]]:
    actor = _text(actor_user_id)
    if not actor:
        return []
    cur.execute(
        """
        SELECT
          p.position_code,
          COALESCE(NULLIF(p.title, ''), p.position_code) AS position_title,
          CAST(p.recruiter_user_id AS text) AS recruiter_user_id,
          CAST(p.hiring_manager_user_id AS text) AS hiring_manager_user_id,
          COUNT(a.app_key) FILTER (
            WHERE a.status IS NOT NULL
              AND a.status NOT IN ('hired','rejected','withdrawn','archived')
          ) AS active_apps,
          EXTRACT(EPOCH FROM (NOW() - COALESCE(p.updated_at, p.created_at))) / 3600.0 AS age_hours
        FROM positions p
        LEFT JOIN applications a
          ON a.company_code=p.company_code AND a.position_code=p.position_code
        WHERE p.company_code=%s
          AND COALESCE(p.status, 'open') IN ('open', 'published', 'active')
          AND (
            CAST(p.recruiter_user_id AS text)=%s
            OR CAST(p.hiring_manager_user_id AS text)=%s
          )
        GROUP BY p.position_code, p.title, p.recruiter_user_id, p.hiring_manager_user_id, p.updated_at, p.created_at
        HAVING COUNT(a.app_key) FILTER (
          WHERE a.status IS NOT NULL
            AND a.status NOT IN ('hired','rejected','withdrawn','archived')
        ) > 0
        ORDER BY active_apps DESC
        LIMIT 20
        """,
        (company, actor, actor),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        age = float(row.get("age_hours") or 0.0)
        code = _text(row.get("position_code"))
        recruiter = _text(row.get("recruiter_user_id"))
        hm = _text(row.get("hiring_manager_user_id"))
        source = SOURCE_JOB_RECRUITER if recruiter == actor else SOURCE_JOB_HIRING_MANAGER
        active = int(row.get("active_apps") or 0)
        base = {
            "unit": "jobs",
            "person_key": f"job:{code}",
            "action_type": ACTION_JOB_OWNED,
            "app_key": None,
            "candidate_name": None,
            "position_code": code,
            "position_title": row.get("position_title"),
            "status": "open",
            "stage": "open",
            "job_label": row.get("position_title") or code,
            "reason": f"{active} active candidate{'s' if active != 1 else ''} on a role you own",
            "priority": int(min(99, 42 + min(20, active * 2))),
            "age_hours": round(age, 1),
            "action_count": active,
            "application_count": active,
            "destination": {
                "page": "candidates",
                "filters": {"position_code": code},
                "cohort_key": ACTION_JOB_OWNED,
            },
            "authority_source": "prehire_personal_work.job_owned",
            "as_of": now.astimezone(timezone.utc).isoformat(),
        }
        items.append(
            enrich_work_item(
                base,
                audience=AUDIENCE_PERSONAL,
                owner_user_id=actor,
                owner_label=user_labels.get(actor) or "You",
                source=source,
                due_state=_due_state(age_hours=age, sla_hours=72),
                entity_type="job",
                entity_id=code,
                next_action=_next_action_label(ACTION_JOB_OWNED),
            )
        )
    return items


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (
            _text(item.get("action_type")),
            _text(item.get("entity_id") or item.get("app_key") or item.get("person_key")),
        )
        prev = best.get(key)
        if prev is None or int(item.get("priority") or 0) > int(prev.get("priority") or 0):
            best[key] = item
    ordered = list(best.values())
    ordered.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            _text(item.get("due_state")) != "overdue",
            _text(item.get("candidate_name") or item.get("job_label") or ""),
            _text(item.get("entity_id") or ""),
        )
    )
    return ordered


def _count_breakdown(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "ready_for_review": 0,
        "follow_up": 0,
        "assessment": 0,
        "interview_feedback": 0,
        "interview_scheduling": 0,
        "overdue_tasks": 0,
        "approvals": 0,
        "jobs_owned": 0,
        "total": len(items),
    }
    for item in items:
        action = _text(item.get("action_type")).lower()
        if action == _overview.ACTION_READY_FOR_REVIEW or "ready_for_review" in action:
            counts["ready_for_review"] += 1
        elif "follow" in action:
            counts["follow_up"] += 1
        elif "assessment" in action:
            counts["assessment"] += 1
        elif action == ACTION_INTERVIEW_FEEDBACK:
            counts["interview_feedback"] += 1
        elif "interview" in action:
            counts["interview_scheduling"] += 1
        elif action == ACTION_OVERDUE_TASK:
            counts["overdue_tasks"] += 1
        elif action == ACTION_APPROVAL:
            counts["approvals"] += 1
        elif action == ACTION_JOB_OWNED:
            counts["jobs_owned"] += 1
    return counts


def build_scoped_work_queue(
    *,
    company: str,
    db_connect: Callable[[], Any],
    actor_user_id: str | None,
    actor_role: str | None,
    actor_email: str | None = None,
    actor_phone: str | None = None,
    scope: str,
    assessments_enabled: bool = True,
    interviews_enabled: bool = True,
    settings: dict[str, Any] | None = None,
    limit: int = 25,
    cursor: str | None = None,
    approval_action_types: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build My work or Company work from backend assignment authority."""
    now = now or datetime.now(timezone.utc)
    scope = resolve_work_scope(requested=scope, role=actor_role, default_mine=True)
    oversight = _visibility.actor_has_prehire_oversight(actor_role)
    actor = _text(actor_user_id)
    sla = _overview.resolve_sla_hours(settings)
    limit = max(1, min(int(limit or 25), 100))

    # Pull a wide company queue, then filter/enrich (backend-authoritative).
    company_payload = _overview.compute_work_queue(
        company=company,
        db_connect=db_connect,
        assessments_enabled=assessments_enabled,
        interviews_enabled=interviews_enabled,
        settings=settings,
        limit=100,
        cursor=None,
        now=now,
    )
    company_items = list(company_payload.get("items") or [])

    with db_connect() as conn:
        with conn.cursor() as cur:
            all_keys: list[str] = []
            for item in company_items:
                all_keys.extend(item_app_keys(item))
            responsibility = load_app_responsibility(cur, company=company, app_keys=all_keys)
            interview_apps = (
                _actor_interview_app_keys(
                    cur,
                    company=company,
                    actor_user_id=actor,
                    actor_email=actor_email,
                    actor_phone=actor_phone,
                )
                if actor
                else set()
            )
            owner_ids = {actor} if actor else set()
            for meta in responsibility.values():
                for field in ("owner_user_id", "recruiter_user_id", "hiring_manager_user_id"):
                    uid = _text(meta.get(field))
                    if uid:
                        owner_ids.add(uid)
            user_labels = load_user_labels(cur, company=company, user_ids=owner_ids)

            enriched_company: list[dict[str, Any]] = []
            mine_from_company: list[dict[str, Any]] = []
            for item in company_items:
                keys = item_app_keys(item)
                matched = False
                owner_id = None
                source = SOURCE_COMPANY_OPS
                for key in keys:
                    is_mine, owner_id, src = responsibility_for_actor(
                        responsibility.get(key),
                        actor_user_id=actor,
                        interview_app_keys=interview_apps,
                        app_key=key,
                    )
                    if is_mine and src:
                        matched = True
                        source = src
                        break
                    if owner_id is None:
                        owner_id = (responsibility.get(key) or {}).get("owner_user_id")
                action_type = _text(item.get("action_type"))
                due = _due_state(
                    age_hours=float(item.get("age_hours") or 0),
                    sla_hours=_sla_for_action(action_type, sla),
                )
                company_row = enrich_work_item(
                    item,
                    audience=AUDIENCE_COMPANY,
                    owner_user_id=owner_id,
                    owner_label=user_labels.get(_text(owner_id)) if owner_id else "Unassigned",
                    source=SOURCE_COMPANY_OPS,
                    due_state=due,
                    entity_type="person" if item.get("person_key") else "application",
                    entity_id=_text(item.get("person_key") or item.get("app_key")) or None,
                )
                enriched_company.append(company_row)
                if matched and actor:
                    mine_row = enrich_work_item(
                        item,
                        audience=AUDIENCE_PERSONAL,
                        owner_user_id=actor,
                        owner_label=user_labels.get(actor) or "You",
                        source=source,
                        due_state=due,
                        entity_type="person" if item.get("person_key") else "application",
                        entity_id=_text(item.get("person_key") or item.get("app_key")) or None,
                    )
                    mine_from_company.append(mine_row)

            personal_extras: list[dict[str, Any]] = []
            if actor and scope == "mine":
                if interviews_enabled:
                    personal_extras.extend(
                        fetch_interview_feedback_items(
                            cur,
                            company=company,
                            actor_user_id=actor,
                            actor_email=actor_email,
                            actor_phone=actor_phone,
                            now=now,
                            user_labels=user_labels,
                        )
                    )
                personal_extras.extend(
                    fetch_overdue_task_items(
                        cur,
                        company=company,
                        actor_user_id=actor,
                        now=now,
                        user_labels=user_labels,
                    )
                )
                personal_extras.extend(
                    fetch_approval_items(
                        cur,
                        company=company,
                        actor_phone=actor_phone,
                        actor_user_id=actor,
                        now=now,
                        user_labels=user_labels,
                        action_types=approval_action_types,
                    )
                )
                personal_extras.extend(
                    fetch_owned_job_items(
                        cur,
                        company=company,
                        actor_user_id=actor,
                        now=now,
                        user_labels=user_labels,
                    )
                )

    if scope == "company":
        ordered = _dedupe_items(enriched_company)
    else:
        ordered = _dedupe_items([*mine_from_company, *personal_extras])

    start = 0
    if cursor:
        for idx, item in enumerate(ordered):
            token = _overview._person_cursor_token(item)  # noqa: SLF001 — shared cursor format
            if token == cursor:
                start = idx + 1
                break
    page = ordered[start : start + limit]
    next_cursor = _overview._person_cursor_token(page[-1]) if start + limit < len(ordered) and page else None
    counts = _count_breakdown(ordered)
    next_action = None
    if page:
        top = page[0]
        next_action = {
            "action": top.get("action_type"),
            "priority": top.get("priority"),
            "unit": top.get("unit") or "people",
            "reason": top.get("reason"),
            "total_matching": 1,
            "people_count": 1 if top.get("person_key") else 0,
            "application_count": int(top.get("application_count") or (1 if top.get("app_key") else 0)),
            "destination": top.get("destination"),
            "authority_source": "prehire_personal_work.next_action",
            "owner": top.get("owner"),
            "due_state": top.get("due_state"),
            "source": top.get("source"),
            "next_action": top.get("next_action"),
            "entity_type": top.get("entity_type"),
            "entity_id": top.get("entity_id"),
        }

    return {
        "company_code": company,
        "ok": True,
        "as_of": now.astimezone(timezone.utc).isoformat(),
        "authority_source": "prehire_personal_work.work_queue",
        "unit": company_payload.get("unit") or "people",
        "scope": scope,
        "work_scope": scope,
        "can_view_company_work": oversight,
        "audience": AUDIENCE_COMPANY if scope == "company" else AUDIENCE_PERSONAL,
        "total": len(ordered),
        "total_count": len(ordered),
        "action_total": len(ordered),
        "limit": limit,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
        "items": page,
        "counts": counts,
        "next_action": next_action,
        "sla_hours": sla,
        "actor_user_id": actor or None,
    }


def actor_is_responsible_for_app(
    *,
    company: str,
    db_connect: Callable[[], Any],
    app_key: str,
    actor_user_id: str | None,
    actor_email: str | None = None,
    actor_phone: str | None = None,
) -> bool:
    actor = _text(actor_user_id)
    if not actor or not _text(app_key):
        return False
    with db_connect() as conn:
        with conn.cursor() as cur:
            meta = load_app_responsibility(cur, company=company, app_keys=[app_key]).get(app_key) or {}
            interview_apps = _actor_interview_app_keys(
                cur,
                company=company,
                actor_user_id=actor,
                actor_email=actor_email,
                actor_phone=actor_phone,
            )
            is_mine, _, _ = responsibility_for_actor(
                meta,
                actor_user_id=actor,
                interview_app_keys=interview_apps,
                app_key=app_key,
            )
            return is_mine


def resolve_notify_targets(
    *,
    company: str,
    db_connect: Callable[[], Any],
    assignee_user_ids: list[str] | None = None,
    assignee_phones: list[str] | None = None,
    fallback_company_broadcast: bool = False,
    company_users_loader: Callable[[str | None], list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Resolve personal assignee targets; optionally fall back to company broadcast."""
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    user_ids = [_text(uid) for uid in (assignee_user_ids or []) if _text(uid)]
    phones = ["".join(ch for ch in _text(p) if ch.isdigit()) for p in (assignee_phones or [])]
    phones = [p for p in phones if p]

    if user_ids:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT CAST(user_id AS text) AS user_id,
                           COALESCE(NULLIF(name, ''), '') AS name,
                           COALESCE(NULLIF(phone, ''), '') AS phone,
                           COALESCE(NULLIF(email, ''), '') AS email
                    FROM dashboard_users
                    WHERE company_code=%s
                      AND status='active'
                      AND CAST(user_id AS text) = ANY(%s)
                    """,
                    (company, user_ids),
                )
                for row in cur.fetchall():
                    phone = "".join(ch for ch in _text(row.get("phone")) if ch.isdigit())
                    if not phone or phone in seen:
                        continue
                    seen.add(phone)
                    targets.append(
                        {
                            "phone": phone,
                            "name": _text(row.get("name")),
                            "email": _text(row.get("email")),
                            "user_id": _text(row.get("user_id")),
                            "role": "assignee",
                            "company_code": company,
                        }
                    )

    for phone in phones:
        if phone in seen:
            continue
        seen.add(phone)
        targets.append({"phone": phone, "name": "", "email": "", "role": "assignee", "company_code": company})

    if targets:
        return targets, AUDIENCE_PERSONAL

    if fallback_company_broadcast and company_users_loader:
        broadcast = []
        for user in company_users_loader(company):
            phone = "".join(ch for ch in _text(user.get("phone")) if ch.isdigit())
            if not phone or phone in seen:
                continue
            seen.add(phone)
            broadcast.append({**user, "phone": phone})
        return broadcast, AUDIENCE_COMPANY

    # Assignees were requested but none were reachable — stay personal (never silent company broadcast).
    if user_ids or phones:
        return [], AUDIENCE_PERSONAL

    return [], AUDIENCE_COMPANY
