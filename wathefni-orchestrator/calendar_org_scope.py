"""Wathefni Calendar — organization scope adapter (C0 A1 / C1 kickoff §3).

Calendar ACL and projections depend only on this contract +
`calendar_event_org_scopes`. They must never query `manager_scopes` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OrgScopeRef:
    org_scope_id: str
    org_scope_kind: str
    label: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OrgScopeMembership:
    org_scope_id: str
    org_scope_kind: str
    label: str | None = None
    metadata: dict[str, Any] | None = None


@runtime_checkable
class OrgScopeAdapter(Protocol):
    def list_memberships(self, company_code: str, user_id: str) -> list[OrgScopeMembership]: ...

    def resolve_scopes(self, company_code: str, org_scope_ids: list[str]) -> list[OrgScopeRef]: ...

    def primary_scope_for_user(self, company_code: str, user_id: str) -> str | None: ...

    def actor_in_any(self, company_code: str, user_id: str, org_scope_ids: list[str]) -> bool: ...


class ManagerScopesOrgAdapter:
    """Current C1 adapter — reads manager_scopes / manager_scope_members only here."""

    def __init__(self, legacy: Any):
        self._legacy = legacy

    def list_memberships(self, company_code: str, user_id: str) -> list[OrgScopeMembership]:
        company = str(company_code or "").strip().upper()
        actor = str(user_id or "").strip()
        if not company or not actor:
            return []
        phone = ""
        try:
            with self._legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT phone FROM dashboard_users
                        WHERE company_code=%s AND user_id::text=%s
                        LIMIT 1
                        """,
                        (company, actor),
                    )
                    row = cur.fetchone()
                    if row and row.get("phone"):
                        phone = str(row["phone"]).strip()
                    cur.execute(
                        """
                        SELECT scope_id, scope_type, team_key, branch_key, manager_phone, dashboard_user_id
                        FROM manager_scopes
                        WHERE company_code=%s
                          AND is_active = true
                          AND (
                            dashboard_user_id = %s
                            OR (%s <> '' AND manager_phone = %s)
                          )
                        ORDER BY created_at ASC
                        """,
                        (company, actor, phone, phone),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        out: list[OrgScopeMembership] = []
        seen: set[str] = set()
        for row in rows:
            scope_id = str(row.get("scope_id") or "").strip()
            if not scope_id or scope_id in seen:
                continue
            seen.add(scope_id)
            kind = str(row.get("scope_type") or "team").strip() or "team"
            label = str(row.get("team_key") or row.get("branch_key") or kind).strip() or None
            out.append(
                OrgScopeMembership(
                    org_scope_id=scope_id,
                    org_scope_kind=kind,
                    label=label,
                    metadata={
                        "team_key": row.get("team_key"),
                        "branch_key": row.get("branch_key"),
                    },
                )
            )
        return out

    def resolve_scopes(self, company_code: str, org_scope_ids: list[str]) -> list[OrgScopeRef]:
        company = str(company_code or "").strip().upper()
        ids = [str(x).strip() for x in (org_scope_ids or []) if str(x).strip()]
        if not company or not ids:
            return []
        try:
            with self._legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT scope_id, scope_type, team_key, branch_key
                        FROM manager_scopes
                        WHERE company_code=%s AND scope_id::text = ANY(%s)
                        """,
                        (company, ids),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        by_id = {str(r.get("scope_id")): r for r in rows}
        refs: list[OrgScopeRef] = []
        for sid in ids:
            row = by_id.get(sid)
            if not row:
                refs.append(OrgScopeRef(org_scope_id=sid, org_scope_kind="unknown", label=None))
                continue
            kind = str(row.get("scope_type") or "team").strip() or "team"
            refs.append(
                OrgScopeRef(
                    org_scope_id=sid,
                    org_scope_kind=kind,
                    label=str(row.get("team_key") or row.get("branch_key") or kind).strip() or None,
                    metadata={"team_key": row.get("team_key"), "branch_key": row.get("branch_key")},
                )
            )
        return refs

    def primary_scope_for_user(self, company_code: str, user_id: str) -> str | None:
        memberships = self.list_memberships(company_code, user_id)
        return memberships[0].org_scope_id if memberships else None

    def actor_in_any(self, company_code: str, user_id: str, org_scope_ids: list[str]) -> bool:
        wanted = {str(x).strip() for x in (org_scope_ids or []) if str(x).strip()}
        if not wanted:
            return False
        member_ids = {m.org_scope_id for m in self.list_memberships(company_code, user_id)}
        return bool(member_ids & wanted)


def get_org_scope_adapter(legacy: Any | None = None) -> OrgScopeAdapter:
    """Factory — default ManagerScopesOrgAdapter; swap later without ACL changes."""
    if legacy is None:
        import app as legacy_app

        legacy = legacy_app
    return ManagerScopesOrgAdapter(legacy)
