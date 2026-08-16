"""Multi-User Wave 6 — team directory privacy + people pickers.

Collaboration directory exposes only name + role (+ status) for assignment.
Effective permission matrices and peer contact details are admin-gated.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Purposes for searchable company people pickers.
PURPOSE_RECRUITER = "recruiter"
PURPOSE_HIRING_MANAGER = "hiring_manager"
PURPOSE_INTERVIEWER = "interviewer"
PURPOSE_TASK_OWNER = "task_owner"
PURPOSE_APPROVER = "approver"
PURPOSE_DIRECTORY = "directory"

PICKER_PURPOSES = frozenset(
    {
        PURPOSE_RECRUITER,
        PURPOSE_HIRING_MANAGER,
        PURPOSE_INTERVIEWER,
        PURPOSE_TASK_OWNER,
        PURPOSE_APPROVER,
        PURPOSE_DIRECTORY,
    }
)

# Eligible active roles per assignment purpose (backend-authoritative).
PURPOSE_ELIGIBLE_ROLES: dict[str, frozenset[str]] = {
    PURPOSE_RECRUITER: frozenset({"owner", "hr_admin", "hr_manager", "recruiter"}),
    PURPOSE_HIRING_MANAGER: frozenset({"owner", "hr_admin", "hr_manager", "hiring_manager", "manager"}),
    PURPOSE_INTERVIEWER: frozenset(
        {"owner", "hr_admin", "hr_manager", "recruiter", "hiring_manager", "interviewer"}
    ),
    PURPOSE_TASK_OWNER: frozenset({"owner", "hr_admin", "hr_manager", "recruiter", "hiring_manager"}),
    PURPOSE_APPROVER: frozenset({"owner", "hr_admin", "hr_manager", "hiring_manager", "manager"}),
    PURPOSE_DIRECTORY: frozenset(
        {
            "owner",
            "hr_admin",
            "hr_manager",
            "recruiter",
            "hiring_manager",
            "interviewer",
            "manager",
            "payroll_operator",
            "viewer",
        }
    ),
}

# Recruiting assignment roles (owner / tasks) — includes HR Admin.
RECRUITING_ASSIGNMENT_ROLES = frozenset({"owner", "hr_admin", "hr_manager", "recruiter", "hiring_manager"})

VIEW_ADMIN = "admin"
VIEW_COLLABORATION = "collaboration"
DIRECTORY_VIEWS = frozenset({VIEW_ADMIN, VIEW_COLLABORATION})

SAFE_NEXT_UNASSIGNED = "unassigned"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _role_key(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def normalize_picker_purpose(value: Any) -> str:
    key = _role_key(value) or PURPOSE_DIRECTORY
    if key in {"hm", "hiring-manager"}:
        return PURPOSE_HIRING_MANAGER
    if key in {"panel", "interview_panel"}:
        return PURPOSE_INTERVIEWER
    if key in {"task", "assignee", "task_assignee"}:
        return PURPOSE_TASK_OWNER
    if key not in PICKER_PURPOSES:
        raise ValueError("invalid_picker_purpose")
    return key


def eligible_roles_for_purpose(purpose: Any) -> frozenset[str]:
    return PURPOSE_ELIGIBLE_ROLES.get(normalize_picker_purpose(purpose), frozenset())


def role_eligible_for_purpose(role: Any, purpose: Any) -> bool:
    return _role_key(role) in eligible_roles_for_purpose(purpose)


def resolve_directory_view(
    *,
    can_manage_users: bool,
    can_manage_settings: bool = False,
    actor_role: str | None = None,
) -> str:
    """Admin view: Company Admin (users.manage) or authorized HR Admin (settings.manage).

    Collaboration view: everyone else — no peer emails/phones/permission matrices.
    """
    if can_manage_users:
        return VIEW_ADMIN
    role = _role_key(actor_role)
    if can_manage_settings and role in {"owner", "hr_admin"}:
        return VIEW_ADMIN
    return VIEW_COLLABORATION


def project_team_member(
    user: Mapping[str, Any] | None,
    *,
    view: str,
    actor_user_id: str | None = None,
    include_permissions: bool = False,
    role_label_resolver: Any = None,
) -> dict[str, Any]:
    """Project a dashboard user for team list / pickers under privacy rules."""
    data = dict(user or {})
    user_id = _text(data.get("user_id"))
    role = _role_key(data.get("role")) or "viewer"
    status = _text(data.get("status")).lower() or "invited"
    name = _text(data.get("name")) or None
    role_label = None
    if callable(role_label_resolver):
        role_label = role_label_resolver(role)
    elif data.get("role_label"):
        role_label = _text(data.get("role_label"))
    is_self = bool(actor_user_id and user_id and user_id == _text(actor_user_id))
    admin = _role_key(view) == VIEW_ADMIN

    payload: dict[str, Any] = {
        "user_id": user_id,
        "name": name or (f"User {user_id[:8]}" if user_id else "Team member"),
        "role": role,
        "role_label": role_label or role.replace("_", " ").title(),
        "status": status,
        "directory_view": VIEW_ADMIN if admin else VIEW_COLLABORATION,
        "is_self": is_self,
    }
    if admin or is_self:
        email = _text(data.get("email"))
        phone = _text(data.get("phone"))
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone
        if data.get("last_active_at") is not None:
            payload["last_active_at"] = data.get("last_active_at")
        if "whatsapp_linked" in data:
            payload["whatsapp_linked"] = bool(data.get("whatsapp_linked"))
        if "company_code" in data:
            payload["company_code"] = _text(data.get("company_code")).upper() or None
    # Effective permission details — admin manage only, never collaboration peers.
    if include_permissions and admin and ("permissions" in data or data.get("_effective_permissions") is not None):
        perms = data.get("_effective_permissions") if data.get("_effective_permissions") is not None else data.get("permissions")
        if isinstance(perms, (list, set, tuple)):
            payload["permissions"] = sorted({_text(p) for p in perms if _text(p)})
    return payload


def project_picker_person(
    user: Mapping[str, Any] | None,
    *,
    purpose: Any,
    role_label_resolver: Any = None,
) -> dict[str, Any] | None:
    """Privacy-safe picker row: name + role only (plus user_id for mutation). Never show raw IDs in UI labels."""
    data = dict(user or {})
    if _text(data.get("status")).lower() != "active":
        return None
    role = _role_key(data.get("role"))
    if not role_eligible_for_purpose(role, purpose):
        return None
    projected = project_team_member(
        data,
        view=VIEW_COLLABORATION,
        include_permissions=False,
        role_label_resolver=role_label_resolver,
    )
    # Picker never exposes peer email/phone even for self.
    projected.pop("email", None)
    projected.pop("phone", None)
    projected.pop("last_active_at", None)
    projected.pop("whatsapp_linked", None)
    projected["purpose"] = normalize_picker_purpose(purpose)
    projected["label"] = f"{projected['name']} · {projected['role_label']}"
    return projected


def filter_users_for_picker(
    users: Iterable[Mapping[str, Any]],
    *,
    purpose: Any,
    query: str | None = None,
    role_label_resolver: Any = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = _text(query).casefold()
    out: list[dict[str, Any]] = []
    for user in users:
        person = project_picker_person(user, purpose=purpose, role_label_resolver=role_label_resolver)
        if not person:
            continue
        if q:
            hay = f"{person.get('name') or ''} {person.get('role_label') or ''} {person.get('role') or ''}".casefold()
            # Allow searching by email only against internal filter if present on source row,
            # but never return email in the projected person.
            source_email = _text(user.get("email")).casefold()
            if q not in hay and q not in source_email and q not in _text(user.get("user_id")).casefold():
                continue
        out.append(person)
        if len(out) >= max(1, min(int(limit or 50), 100)):
            break
    return out


def notification_audit_fields(
    *,
    audience: str,
    source: str | None = None,
    kind: str | None = None,
    notification_scope: str | None = None,
) -> dict[str, Any]:
    resolved_audience = "personal" if _text(audience).lower() == "personal" else "company"
    scope = _text(notification_scope).lower() or resolved_audience
    if scope not in {"personal", "company"}:
        scope = resolved_audience
    return {
        "audience": resolved_audience,
        "notification_scope": scope,
        "source": _text(source) or ("personal_assignee" if resolved_audience == "personal" else "company_ops"),
        "kind": _text(kind) or None,
    }


def validate_active_assignee(
    cur: Any,
    *,
    company: str,
    user_id: Any,
    purpose: str,
) -> dict[str, Any]:
    """Backend authority: assignee must be active + role-eligible for the purpose."""
    target = _text(user_id)
    if not target:
        raise ValueError("assignee_required")
    purpose_key = normalize_picker_purpose(purpose)
    cur.execute(
        """
        SELECT user_id, company_code, role, status, name, email
        FROM dashboard_users
        WHERE company_code=%s AND CAST(user_id AS text)=%s
        LIMIT 1
        """,
        (_text(company).upper(), target),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("assignee_not_found")
    data = dict(row)
    if _text(data.get("status")).lower() != "active":
        raise ValueError("assignee_not_active")
    if not role_eligible_for_purpose(data.get("role"), purpose_key):
        raise ValueError("assignee_not_eligible")
    return data


def ownership_display_names(
    cur: Any,
    *,
    company: str,
    user_ids: Iterable[Any],
) -> dict[str, str]:
    ids = sorted({_text(uid) for uid in user_ids if _text(uid)})
    if not ids:
        return {}
    cur.execute(
        """
        SELECT CAST(user_id AS text) AS user_id,
               COALESCE(NULLIF(name, ''), NULLIF(email, ''), CAST(user_id AS text)) AS label
        FROM dashboard_users
        WHERE company_code=%s AND CAST(user_id AS text) = ANY(%s)
        """,
        (_text(company).upper(), ids),
    )
    return {_text(row.get("user_id")): _text(row.get("label")) for row in cur.fetchall()}
