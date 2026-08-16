"""Multi-User Wave 3 — canonical pre-hire ownership / assignment authority.

Contract:
  - Jobs: recruiter_user_id (primary recruiter owner), hiring_manager_user_id (explicit HM)
  - Applications: owner_user_id (primary); inherit from job.recruiter_user_id when present
  - Interviews: candidate_interview_assignments (Wave 1; explicit panel only)
  - Unassigned = NULL ownership fields; visible to HR leadership only under assigned/hybrid
  - Reassignment is audited (position_ownership_events + application_ownership_events)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

# Roles that auto-receive recruiter ownership on job create when not overridden.
AUTO_RECRUITER_ROLES = frozenset({"recruiter"})
# Roles that may leave jobs Unassigned and may override ownership.
OWNERSHIP_OVERSIGHT_ROLES = frozenset({"owner", "hr_admin", "hr_manager"})

POSITION_OWNERSHIP_EVENT_TYPES = frozenset(
    {"created", "recruiter_assigned", "recruiter_reassigned", "recruiter_unassigned", "hm_assigned", "hm_reassigned", "hm_unassigned"}
)


def _role_key(role: str | None) -> str:
    return str(role or "").strip().lower().replace("-", "_").replace(" ", "_")


def _user_id(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return str(UUID(raw))
    except (TypeError, ValueError):
        # Accept non-UUID dashboard ids used in some fixtures; still store as text cast later.
        return raw


def normalize_actor_role(role: str | None) -> str:
    key = _role_key(role)
    if key in {"company_admin", "admin", "super_admin"}:
        return "owner"
    if key in {"hr_admin", "hr admin"}:
        return "hr_admin"
    return key


def actor_is_ownership_oversight(role: str | None) -> bool:
    return normalize_actor_role(role) in OWNERSHIP_OVERSIGHT_ROLES


def resolve_job_recruiter_on_create(
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    payload: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """Return (recruiter_user_id, reason).

    reason: explicit | auto_recruiter | unassigned
    """
    data = payload if isinstance(payload, dict) else {}
    provided = data.get("recruiter_user_id")
    # Explicit non-empty override always wins (leadership or recruiter assigning someone else).
    if provided is not None and str(provided).strip():
        return _user_id(provided), "explicit"
    # Explicit empty clear by oversight → Unassigned.
    if "recruiter_user_id" in data and actor_is_ownership_oversight(actor_role):
        return None, "unassigned"
    role = normalize_actor_role(actor_role)
    actor = _user_id(actor_user_id)
    if role in AUTO_RECRUITER_ROLES and actor:
        return actor, "auto_recruiter"
    return None, "unassigned"


def resolve_job_hiring_manager_on_write(*, payload: dict[str, Any] | None, current: str | None = None, updating: bool = False) -> str | None:
    """HM is always explicit — never auto-assigned."""
    data = payload if isinstance(payload, dict) else {}
    if updating:
        if "hiring_manager_user_id" not in data:
            return _user_id(current)
        provided = data.get("hiring_manager_user_id")
        if provided is None or str(provided).strip() == "":
            return None
        return _user_id(provided)
    provided = data.get("hiring_manager_user_id")
    if provided is None or str(provided).strip() == "":
        return None
    return _user_id(provided)


def ownership_state(user_id: Any) -> str:
    return "assigned" if _user_id(user_id) else "unassigned"


def ensure_position_ownership_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS position_ownership_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          position_code text NOT NULL,
          event_type text NOT NULL,
          field text NOT NULL,
          from_user_id text,
          to_user_id text,
          actor_user_id text,
          reason text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (field IN ('recruiter', 'hiring_manager')),
          CHECK (event_type IN (
            'created','recruiter_assigned','recruiter_reassigned','recruiter_unassigned',
            'hm_assigned','hm_reassigned','hm_unassigned'
          ))
        );
        CREATE INDEX IF NOT EXISTS idx_position_ownership_events_company_pos
          ON position_ownership_events(company_code, position_code, created_at DESC);
        """
    )


def record_position_ownership_event(
    cur: Any,
    *,
    company_code: str,
    position_code: str,
    event_type: str,
    field: str,
    from_user_id: str | None,
    to_user_id: str | None,
    actor_user_id: str | None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_position_ownership_schema(cur)
    if event_type not in POSITION_OWNERSHIP_EVENT_TYPES:
        event_type = "created"
    cur.execute(
        """
        INSERT INTO position_ownership_events
          (company_code, position_code, event_type, field, from_user_id, to_user_id, actor_user_id, reason, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            str(company_code).strip().upper(),
            str(position_code).strip().upper(),
            event_type,
            field,
            from_user_id,
            to_user_id,
            actor_user_id,
            reason,
            __import__("json").dumps(metadata or {}),
        ),
    )


def recruiter_event_type(*, previous: str | None, new: str | None) -> str | None:
    prev = _user_id(previous)
    nxt = _user_id(new)
    if prev == nxt:
        return None
    if prev is None and nxt is not None:
        return "recruiter_assigned"
    if prev is not None and nxt is None:
        return "recruiter_unassigned"
    if prev is not None and nxt is not None:
        return "recruiter_reassigned"
    return "created"


def hm_event_type(*, previous: str | None, new: str | None) -> str | None:
    prev = _user_id(previous)
    nxt = _user_id(new)
    if prev == nxt:
        return None
    if prev is None and nxt is not None:
        return "hm_assigned"
    if prev is not None and nxt is None:
        return "hm_unassigned"
    if prev is not None and nxt is not None:
        return "hm_reassigned"
    return None


def lookup_job_recruiter(cur: Any, *, company_code: str, position_code: str) -> str | None:
    code = str(position_code or "").strip()
    if not code:
        return None
    cur.execute(
        """
        SELECT CAST(recruiter_user_id AS text) AS recruiter_user_id
        FROM positions
        WHERE company_code=%s AND position_code=%s
        LIMIT 1
        """,
        (str(company_code).strip().upper(), code.upper()),
    )
    row = cur.fetchone() or {}
    return _user_id(row.get("recruiter_user_id"))


def apply_application_owner_inherit(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    position_code: str | None,
    actor_user_id: str | None,
    reason: str = "inherit_from_job_recruiter",
    only_if_unassigned: bool = True,
) -> dict[str, Any]:
    """Set applications.owner_user_id from positions.recruiter_user_id when appropriate.

    Returns {changed, owner_user_id, ownership_state}.
    """
    company = str(company_code).strip().upper()
    key = str(app_key or "").strip()
    if not key:
        return {"changed": False, "owner_user_id": None, "ownership_state": "unassigned"}

    cur.execute(
        """
        SELECT CAST(owner_user_id AS text) AS owner_user_id,
               COALESCE(ownership_version, 0) AS ownership_version
        FROM applications
        WHERE company_code=%s AND app_key=%s
        LIMIT 1
        """,
        (company, key),
    )
    app = cur.fetchone() or {}
    current_owner = _user_id(app.get("owner_user_id"))
    if only_if_unassigned and current_owner:
        return {"changed": False, "owner_user_id": current_owner, "ownership_state": "assigned"}

    recruiter = lookup_job_recruiter(cur, company_code=company, position_code=str(position_code or ""))
    if not recruiter:
        return {"changed": False, "owner_user_id": current_owner, "ownership_state": ownership_state(current_owner)}

    if current_owner == recruiter:
        return {"changed": False, "owner_user_id": current_owner, "ownership_state": "assigned"}

    actor = _user_id(actor_user_id) or recruiter
    # Ensure collaboration schema columns/events exist when possible.
    try:
        cur.execute(
            """
            UPDATE applications
            SET owner_user_id=%s::uuid,
                ownership_version=COALESCE(ownership_version,0)+1,
                owner_assigned_at=now(),
                owner_assigned_by_user_id=%s::uuid,
                updated_at=CURRENT_DATE
            WHERE company_code=%s AND app_key=%s
            RETURNING ownership_version
            """,
            (recruiter, actor, company, key),
        )
    except Exception:
        # Fallback if uuid cast fails for non-uuid ids.
        cur.execute(
            """
            UPDATE applications
            SET owner_user_id=%s,
                ownership_version=COALESCE(ownership_version,0)+1,
                owner_assigned_at=now(),
                owner_assigned_by_user_id=%s,
                updated_at=CURRENT_DATE
            WHERE company_code=%s AND app_key=%s
            RETURNING ownership_version
            """,
            (recruiter, actor, company, key),
        )
    version_row = cur.fetchone() or {}
    version = int(version_row.get("ownership_version") or 1)
    try:
        cur.execute(
            """
            INSERT INTO application_ownership_events
              (company_code, app_key, event_type, from_owner_user_id, to_owner_user_id,
               ownership_version, actor_user_id, reason, metadata)
            VALUES (%s,%s,'assigned',%s::uuid,%s::uuid,%s,%s::uuid,%s,%s::jsonb)
            """,
            (
                company,
                key,
                current_owner,
                recruiter,
                version,
                actor,
                reason,
                __import__("json").dumps({"source": "wave3_inherit", "position_code": position_code}),
            ),
        )
    except Exception:
        # Soft-fail history if FK/uuid mismatch; ownership column still updated.
        pass
    return {"changed": True, "owner_user_id": recruiter, "ownership_state": "assigned"}


def job_ownership_payload(job: dict[str, Any] | None) -> dict[str, Any]:
    row = job if isinstance(job, dict) else {}
    recruiter = _user_id(row.get("recruiter_user_id"))
    hm = _user_id(row.get("hiring_manager_user_id"))
    return {
        "recruiter_user_id": recruiter,
        "hiring_manager_user_id": hm,
        "recruiter_ownership_state": ownership_state(recruiter),
        "hiring_manager_ownership_state": ownership_state(hm),
        "ownership_unassigned": recruiter is None,
    }
