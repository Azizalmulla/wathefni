"""Explicit Setup first-owner permission bootstrap.

Employee roster scopes are grant-only and are never inferred from role=owner.
A new company therefore cannot add its first employee unless Setup writes an
explicit, versioned grant bundle at first-owner creation.

This is not a second permission authority. It writes the existing
`dashboard_user_permission_grants` rows transactionally and idempotently.
It does not grant ER / Talent / Payroll-sensitive scopes.
"""
from __future__ import annotations

from typing import Any

BUNDLE_VERSION = "setup_owner_bootstrap_v1"
REVIEW_REFERENCE = BUNDLE_VERSION
GRANTED_REASON = (
    "Explicit Setup first-owner bootstrap so a new company can add and manage "
    "employees without CLI or SQL grants."
)
# Minimal self-service: roster read + create/manage. Setup itself uses
# settings.manage from the owner role (not grant-only).
OWNER_BOOTSTRAP_PERMISSIONS: tuple[str, ...] = (
    "employees.read",
    "employees.manage",
)
FORBIDDEN_BOOTSTRAP_PERMISSIONS = frozenset(
    {
        "payroll.export",
        "er.sensitive",
        "talent.sensitive",
        "performance.sensitive",
        "offer.hire_override",
        "assessment.publish",
        "employees.ess.unmask",
    }
)


def bootstrap_permissions() -> tuple[str, ...]:
    overlap = set(OWNER_BOOTSTRAP_PERMISSIONS) & FORBIDDEN_BOOTSTRAP_PERMISSIONS
    if overlap:
        raise RuntimeError(f"bootstrap bundle contains forbidden scopes: {sorted(overlap)}")
    return OWNER_BOOTSTRAP_PERMISSIONS


def apply_owner_bootstrap_grants(
    cur: Any,
    *,
    company_code: str,
    user_id: str,
    granted_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Insert the v1 owner bootstrap grants. Idempotent. Same transaction as caller.

    Existing rows (including later admin revokes) are left unchanged so a re-seed
    cannot undelete a deliberate revoke. Missing permissions are inserted.
    """
    company = str(company_code or "").strip().upper()
    target = str(user_id or "").strip()
    actor = str(granted_by_user_id or target).strip()
    if not company or not target or not actor:
        return {"ok": False, "error": "bootstrap_identity_required", "granted": []}

    granted: list[str] = []
    already: list[str] = []
    for permission in bootstrap_permissions():
        cur.execute(
            """
            INSERT INTO dashboard_user_permission_grants
              (company_code, user_id, permission, status, review_reference,
               granted_by_user_id, granted_reason, granted_at, updated_at)
            VALUES (%s,%s,%s,'active',%s,%s,%s,now(),now())
            ON CONFLICT (company_code, user_id, permission) DO NOTHING
            RETURNING permission
            """,
            (company, target, permission, REVIEW_REFERENCE, actor, GRANTED_REASON),
        )
        row = cur.fetchone()
        if row:
            granted.append(permission)
        else:
            already.append(permission)
    return {
        "ok": True,
        "bundle_version": BUNDLE_VERSION,
        "granted": granted,
        "already_present": already,
        "permissions": list(bootstrap_permissions()),
    }
