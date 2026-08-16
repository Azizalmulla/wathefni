"""Multi-User Wave 2 — tenant pre-hiring visibility policy.

Policies (company_settings.settings.prehire_visibility_policy):
  - shared_company (default): company-wide among entitled roles
  - assigned_only: non-oversight operators see only owned/assigned work
  - hybrid: company-wide summary counts; detail/list/GET scoped to assignments

Leadership oversight (always company-wide): owner, hr_admin, hr_manager.
Interviewer remains assignment-scoped via Wave 1 helpers (not this module).
Viewer stays company-wide read (no ownership fields).
"""

from __future__ import annotations

from typing import Any

PREHIRE_VISIBILITY_POLICIES = frozenset({"shared_company", "assigned_only", "hybrid"})
PREHIRE_VISIBILITY_DEFAULT = "shared_company"
PREHIRE_OVERSIGHT_ROLES = frozenset({"owner", "hr_admin", "hr_manager"})
PREHIRE_SCOPED_ROLES = frozenset({"recruiter", "hiring_manager"})

SETTING_KEY = "prehire_visibility_policy"


def normalize_prehire_visibility_policy(value: Any) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in PREHIRE_VISIBILITY_POLICIES:
        return key
    return PREHIRE_VISIBILITY_DEFAULT


def prehire_visibility_policy_from_settings(settings: dict[str, Any] | None) -> str:
    data = settings if isinstance(settings, dict) else {}
    return normalize_prehire_visibility_policy(data.get(SETTING_KEY))


def actor_has_prehire_oversight(role: str | None) -> bool:
    key = str(role or "").strip().lower().replace("-", "_").replace(" ", "_")
    # Accept product aliases that normalize to oversight in ROLE_ALIASES.
    if key in {"company_admin", "admin", "super_admin"}:
        key = "owner"
    if key in {"hr admin"}:
        key = "hr_admin"
    return key in PREHIRE_OVERSIGHT_ROLES


def actor_needs_prehire_assignment_scope(role: str | None) -> bool:
    key = str(role or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key in PREHIRE_SCOPED_ROLES


def resolve_visibility_plan(
    *,
    policy: str,
    role: str | None,
    surface: str,
) -> dict[str, Any]:
    """Return how a surface should behave for this actor.

    surface:
      - summary: Overview/Reports headline counts, tab totals
      - detail: lists, work-queue rows, exports, GET-by-id, search hits
    """
    mode = normalize_prehire_visibility_policy(policy)
    role_key = str(role or "").strip().lower()
    oversight = actor_has_prehire_oversight(role_key)
    scoped_role = actor_needs_prehire_assignment_scope(role_key)
    kind = "summary" if str(surface or "").strip().lower() == "summary" else "detail"

    if oversight or mode == "shared_company" or not scoped_role:
        return {
            "policy": mode,
            "surface": kind,
            "apply_assignment_scope": False,
            "summary_company_wide": True,
            "role": role_key,
            "oversight": oversight,
        }

    if mode == "hybrid" and kind == "summary":
        return {
            "policy": mode,
            "surface": kind,
            "apply_assignment_scope": False,
            "summary_company_wide": True,
            "role": role_key,
            "oversight": False,
            "detail_scope": "assigned",
        }

    # assigned_only (any surface) or hybrid detail
    return {
        "policy": mode,
        "surface": kind,
        "apply_assignment_scope": True,
        "summary_company_wide": False,
        "role": role_key,
        "oversight": False,
    }


def jobs_assignment_sql(role: str | None, *, alias: str = "p") -> tuple[str, list[Any]]:
    """SQL predicate for positions visible to recruiter/HM. Caller binds actor_user_id once per %s."""
    role_key = str(role or "").strip().lower()
    prefix = f"{alias}." if alias else ""
    if role_key == "hiring_manager":
        return (
            f"(CAST({prefix}hiring_manager_user_id AS text) = %s)",
            ["__actor__"],
        )
    # recruiter (default scoped)
    return (
        f"(CAST({prefix}recruiter_user_id AS text) = %s OR CAST({prefix}created_by_user_id AS text) = %s)",
        ["__actor__", "__actor__"],
    )


def applications_assignment_sql(role: str | None, *, applications_alias: str = "a") -> tuple[str, list[Any]]:
    """SQL predicate for applications visible to recruiter/HM."""
    role_key = str(role or "").strip().lower()
    a = applications_alias
    if role_key == "hiring_manager":
        sql = (
            "("
            f"EXISTS ("
            f"  SELECT 1 FROM positions _pv "
            f"  WHERE _pv.company_code={a}.company_code "
            f"    AND _pv.position_code={a}.position_code "
            f"    AND CAST(_pv.hiring_manager_user_id AS text) = %s"
            f")"
            ")"
        )
        return sql, ["__actor__"]
    sql = (
        "("
        f"CAST({a}.owner_user_id AS text) = %s "
        f"OR EXISTS ("
        f"  SELECT 1 FROM candidate_record_governance _gov "
        f"  WHERE _gov.company_code={a}.company_code AND _gov.app_key={a}.app_key "
        f"    AND CAST(_gov.recruiter_owner_user_id AS text) = %s"
        f") "
        f"OR EXISTS ("
        f"  SELECT 1 FROM positions _pv "
        f"  WHERE _pv.company_code={a}.company_code "
        f"    AND _pv.position_code={a}.position_code "
        f"    AND (CAST(_pv.recruiter_user_id AS text) = %s OR CAST(_pv.created_by_user_id AS text) = %s)"
        f")"
        ")"
    )
    return sql, ["__actor__", "__actor__", "__actor__", "__actor__"]


def bind_actor_params(placeholders: list[Any], actor_user_id: str) -> list[Any]:
    actor = str(actor_user_id or "").strip()
    return [actor if p == "__actor__" else p for p in placeholders]


def application_visible_to_actor(
    *,
    application: dict[str, Any] | None,
    role: str | None,
    actor_user_id: str,
    cur: Any | None = None,
) -> bool:
    """Python-side check for GET-by-id (when SQL fragment is not handy)."""
    app = application if isinstance(application, dict) else {}
    actor = str(actor_user_id or "").strip()
    if not actor:
        return False
    role_key = str(role or "").strip().lower()
    company = str(app.get("company_code") or "").strip().upper()
    app_key = str(app.get("app_key") or "").strip()
    position_code = str(app.get("position_code") or "").strip()

    if role_key == "hiring_manager":
        if not company or not position_code or cur is None:
            return False
        cur.execute(
            """
            SELECT 1 FROM positions
            WHERE company_code=%s AND position_code=%s
              AND CAST(hiring_manager_user_id AS text)=%s
            LIMIT 1
            """,
            (company, position_code, actor),
        )
        return bool(cur.fetchone())

    if str(app.get("owner_user_id") or "") == actor:
        return True
    if cur is not None and company and app_key:
        cur.execute(
            """
            SELECT 1 FROM candidate_record_governance
            WHERE company_code=%s AND app_key=%s
              AND CAST(recruiter_owner_user_id AS text)=%s
            LIMIT 1
            """,
            (company, app_key, actor),
        )
        if cur.fetchone():
            return True
        if position_code:
            cur.execute(
                """
                SELECT 1 FROM positions
                WHERE company_code=%s AND position_code=%s
                  AND (CAST(recruiter_user_id AS text)=%s OR CAST(created_by_user_id AS text)=%s)
                LIMIT 1
                """,
                (company, position_code, actor, actor),
            )
            return bool(cur.fetchone())
    return False


def job_visible_to_actor(
    *,
    job: dict[str, Any] | None,
    role: str | None,
    actor_user_id: str,
) -> bool:
    row = job if isinstance(job, dict) else {}
    actor = str(actor_user_id or "").strip()
    if not actor:
        return False
    role_key = str(role or "").strip().lower()
    if role_key == "hiring_manager":
        return str(row.get("hiring_manager_user_id") or "") == actor
    return str(row.get("recruiter_user_id") or "") == actor or str(row.get("created_by_user_id") or "") == actor


def visibility_meta(plan: dict[str, Any]) -> dict[str, Any]:
    """Additive payload fields for list/summary responses."""
    return {
        "prehire_visibility_policy": plan.get("policy"),
        "prehire_visibility_scope": "assigned" if plan.get("apply_assignment_scope") else "company",
        "prehire_visibility_summary_company_wide": bool(plan.get("summary_company_wide")),
        "prehire_visibility_oversight": bool(plan.get("oversight")),
    }
