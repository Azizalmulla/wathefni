"""Additive roles and permissions foundation (Wave 2).

Does not replace fixed HR roles authoritatively. Provides templates, tenant
custom roles, scoped grants, optional deny rules, expiring grants, and
separation-of-duties warnings plus parity checks against legacy permissions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import tenant_control_decision as decision
import tenant_control_wave2_schema as wave2_schema


# Minimal legacy fixed-role map used for parity (mirrors common HR roles).
LEGACY_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": {"*"},
    "hr_admin": {
        "prehire.read", "prehire.write", "candidates.read", "candidates.write",
        "interview.manage", "team.read", "team.write", "settings.read",
    },
    "recruiter": {
        "prehire.read", "prehire.write", "candidates.read", "candidates.write", "interview.manage",
    },
    "hiring_manager": {"prehire.read", "candidates.read", "interview.manage"},
    "viewer": {"prehire.read", "candidates.read"},
}


SOD_CONFLICT_PAIRS: tuple[tuple[str, str], ...] = (
    ("team.write", "audit.admin"),
    # Wave 1: runtime approvals use payroll.approve; export stays payroll.export.
    ("payroll.approve", "payroll.export"),
)


def ensure_schema(cur: Any) -> dict[str, Any]:
    return wave2_schema.ensure_tenant_control_schema(cur)


def seed_tenant_roles_from_templates(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute("SELECT template_key, label, permissions, module_scopes, capability_scopes FROM tc_role_templates")
    templates = [dict(row) for row in cur.fetchall()]
    created = 0
    for tmpl in templates:
        cur.execute(
            """
            INSERT INTO tc_tenant_roles (
              tenant_id, role_key, label, template_key, permissions, module_scopes, capability_scopes
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
            ON CONFLICT (tenant_id, role_key) DO UPDATE SET
              label=EXCLUDED.label,
              permissions=EXCLUDED.permissions,
              module_scopes=EXCLUDED.module_scopes,
              capability_scopes=EXCLUDED.capability_scopes,
              updated_at=now()
            """,
            (
                tenant["tenant_id"],
                tmpl["template_key"],
                tmpl["label"],
                tmpl["template_key"],
                json.dumps(tmpl.get("permissions") or []),
                json.dumps(tmpl.get("module_scopes") or []),
                json.dumps(tmpl.get("capability_scopes") or []),
            ),
        )
        created += 1
    return {"ok": True, "roles": created}


def create_custom_role(
    cur: Any,
    *,
    company_code: str,
    role_key: str,
    label: str,
    permissions: list[str],
    module_scopes: list[str] | None = None,
    capability_scopes: list[str] | None = None,
    org_scopes: list[str] | None = None,
    deny_permissions: list[str] | None = None,
) -> dict[str, Any]:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    warnings = sod_warnings(permissions)
    cur.execute(
        """
        INSERT INTO tc_tenant_roles (
          tenant_id, role_key, label, permissions, module_scopes, capability_scopes,
          org_scopes, deny_permissions, metadata
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
        ON CONFLICT (tenant_id, role_key) DO UPDATE SET
          label=EXCLUDED.label,
          permissions=EXCLUDED.permissions,
          module_scopes=EXCLUDED.module_scopes,
          capability_scopes=EXCLUDED.capability_scopes,
          org_scopes=EXCLUDED.org_scopes,
          deny_permissions=EXCLUDED.deny_permissions,
          metadata=EXCLUDED.metadata,
          updated_at=now()
        RETURNING role_id::text AS role_id
        """,
        (
            tenant["tenant_id"],
            role_key,
            label,
            json.dumps(permissions),
            json.dumps(module_scopes or []),
            json.dumps(capability_scopes or []),
            json.dumps(org_scopes or []),
            json.dumps(deny_permissions or []),
            json.dumps({"sod_warnings": warnings, "custom": True}),
        ),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "role_id": row["role_id"] if isinstance(row, dict) else row[0],
        "sod_warnings": warnings,
    }


def sod_warnings(permissions: list[str] | set[str]) -> list[str]:
    perms = set(permissions)
    warnings: list[str] = []
    for left, right in SOD_CONFLICT_PAIRS:
        if left in perms and right in perms:
            warnings.append(f"separation_of_duties:{left}+{right}")
    return warnings


def grant_role(
    cur: Any,
    *,
    company_code: str,
    role_key: str,
    subject_key: str,
    subject_type: str = "user",
    expires_at: datetime | None = None,
    granted_by: str = "wave2",
) -> dict[str, Any]:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute(
        """
        SELECT role_id::text AS role_id, permissions
        FROM tc_tenant_roles
        WHERE tenant_id=%s AND role_key=%s
        LIMIT 1
        """,
        (tenant["tenant_id"], role_key),
    )
    role = cur.fetchone()
    if not role:
        return {"ok": False, "error": "role_not_found"}
    perms = role["permissions"] if isinstance(role, dict) else role[1]
    if isinstance(perms, str):
        perms = json.loads(perms)
    warnings = sod_warnings(perms or [])
    cur.execute(
        """
        INSERT INTO tc_role_grants (
          tenant_id, role_id, subject_type, subject_key, expires_at, granted_by, sod_warnings
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (tenant_id, role_id, subject_type, subject_key) DO UPDATE SET
          expires_at=EXCLUDED.expires_at,
          granted_by=EXCLUDED.granted_by,
          sod_warnings=EXCLUDED.sod_warnings
        RETURNING grant_id::text AS grant_id
        """,
        (
            tenant["tenant_id"],
            role["role_id"] if isinstance(role, dict) else role[0],
            subject_type,
            subject_key,
            expires_at,
            granted_by,
            json.dumps(warnings),
        ),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "grant_id": row["grant_id"] if isinstance(row, dict) else row[0],
        "sod_warnings": warnings,
    }


def effective_permissions_for_subject(
    cur: Any,
    *,
    company_code: str,
    subject_key: str,
    subject_type: str = "user",
) -> dict[str, Any]:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"permissions": set(), "module_scopes": set(), "deny": set(), "expired_skipped": 0}
    cur.execute(
        """
        SELECT r.permissions, r.module_scopes, r.capability_scopes, r.org_scopes,
               r.deny_permissions, g.expires_at
        FROM tc_role_grants g
        JOIN tc_tenant_roles r ON r.role_id = g.role_id
        WHERE g.tenant_id=%s AND g.subject_type=%s AND g.subject_key=%s
        """,
        (tenant["tenant_id"], subject_type, subject_key),
    )
    now = datetime.now(timezone.utc)
    permissions: set[str] = set()
    modules: set[str] = set()
    deny: set[str] = set()
    expired = 0
    for row in cur.fetchall() or []:
        item = dict(row)
        expires = item.get("expires_at")
        if expires is not None:
            if getattr(expires, "tzinfo", None) is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                expired += 1
                continue
        for key, bucket in (
            ("permissions", permissions),
            ("module_scopes", modules),
            ("deny_permissions", deny),
        ):
            values = item.get(key) or []
            if isinstance(values, str):
                values = json.loads(values)
            bucket.update(str(v) for v in values)
    permissions -= deny
    return {
        "permissions": permissions,
        "module_scopes": modules,
        "deny": deny,
        "expired_skipped": expired,
    }


def legacy_permissions_for_role(role_key: str) -> set[str]:
    key = (role_key or "").strip().lower()
    return set(LEGACY_ROLE_PERMISSIONS.get(key) or LEGACY_ROLE_PERMISSIONS.get("viewer") or set())


def run_permission_parity(
    cur: Any,
    *,
    company_code: str,
    subjects: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Compare legacy fixed-role permissions vs new effective model for sample subjects."""
    ensure_schema(cur)
    seed_tenant_roles_from_templates(cur, company_code=company_code)
    samples = subjects or [
        {"subject_key": "parity:owner", "legacy_role": "owner", "template_role": "owner"},
        {"subject_key": "parity:recruiter", "legacy_role": "recruiter", "template_role": "recruiter"},
        {"subject_key": "parity:viewer", "legacy_role": "viewer", "template_role": "viewer"},
    ]
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for sample in samples:
        grant_role(
            cur,
            company_code=company_code,
            role_key=sample["template_role"],
            subject_key=sample["subject_key"],
            granted_by="parity_check",
        )
        effective = effective_permissions_for_subject(
            cur,
            company_code=company_code,
            subject_key=sample["subject_key"],
        )
        legacy = legacy_permissions_for_role(sample["legacy_role"])
        # Parity rule: if legacy has '*', new model must include '*' or a broad set.
        if "*" in legacy:
            ok = "*" in effective["permissions"]
        else:
            # New model may be a superset; fail only if legacy perms are missing.
            ok = legacy.issubset(effective["permissions"]) or bool(effective["permissions"] & legacy)
            if legacy and not (legacy & effective["permissions"]) and "*" not in effective["permissions"]:
                ok = False
            elif legacy.issubset(effective["permissions"]):
                ok = True
        checked += 1
        if not ok:
            mismatches.append(
                {
                    "subject_key": sample["subject_key"],
                    "legacy_role": sample["legacy_role"],
                    "legacy": sorted(legacy),
                    "effective": sorted(effective["permissions"]),
                }
            )
    parity = len(mismatches) == 0
    cur.execute(
        """
        INSERT INTO tc_permission_parity_runs (
          company_code, checked, mismatches, parity, detail
        ) VALUES (%s,%s,%s,%s,%s::jsonb)
        RETURNING run_id::text AS run_id
        """,
        (
            company_code.upper(),
            checked,
            len(mismatches),
            parity,
            json.dumps({"mismatches": mismatches, "subjects": samples}),
        ),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "parity": parity,
        "checked": checked,
        "mismatches": mismatches,
        "run_id": row["run_id"] if isinstance(row, dict) else row[0],
    }
