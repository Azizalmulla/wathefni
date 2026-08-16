"""Employee App access eligibility — company + employee gates for invite triggers.

Canonical rule:
  Invite only when Employee 360 employee exists
  AND company Employee App module is ON
  AND that employee is eligible for app access.

Never invite on mere create / migration / onboarding start.
Enabling access triggers existing invitation+delivery (employee_app_invitation).
Disabling access clears eligibility and reuses Auth Wave 2 revoke for sessions.

Auth Wave 2 Phase 6 is out of scope.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger("wathefni.employee_app_access")

MODULE_KEY = "employee_app"

# Company policy modes (stored on company_modules.settings for employee_app).
MODE_ALL = "all"
MODE_SELECTED = "selected"
ACCESS_MODES = {MODE_ALL, MODE_SELECTED}

TRIGGER_ACCESS_ENABLED = "app_access_enabled"
TRIGGER_ACCESS_BULK = "app_access_bulk"
TRIGGER_ACCESS_POLICY = "app_access_policy"

CONTRACT_VERSION = "employee_app_access_eligibility_v1"
PHASE_2B = "setup_console_phase2b"
PHASE_2C = "setup_console_phase2c"

# Product-facing who-can-use choice (maps onto access_mode + selection_scope).
UX_EVERYONE = "everyone"
UX_DEPARTMENTS = "departments"
UX_EMPLOYEES = "employees"
UX_MODES = {UX_EVERYONE, UX_DEPARTMENTS, UX_EMPLOYEES}

# selection_scope stored when access_mode=selected
SCOPE_DEPARTMENTS = "departments"
SCOPE_EMPLOYEES = "employees"

# Confirm when removing access from this many (or more) employees.
LARGE_REMOVAL_THRESHOLD = 10

# Phase 2C — canonical org-unit IDs (additive settings keys).
SETTINGS_ORG_UNIT_IDS = "selected_department_org_unit_ids"
SETTINGS_ORG_UNIT_LABELS = "selected_department_org_unit_labels"  # id → historical display name
SETTINGS_ATTENTION = "policy_attention"
SETTINGS_LEGACY_DEPT_NAMES = "selected_departments"  # retained for audit / pre-2C backfill


def ensure_access_schema(cur: Any) -> None:
    """Additive employee-level access flag (default OFF — migration-safe)."""
    cur.execute(
        """
        ALTER TABLE employees
          ADD COLUMN IF NOT EXISTS app_access_enabled boolean NOT NULL DEFAULT false
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employees_app_access_enabled
          ON employees(company_code, app_access_enabled)
          WHERE app_access_enabled IS TRUE
        """
    )


def reconcile_access_flag_for_live_sessions(cur: Any) -> list[dict[str, str]]:
    """Deploy-time repair: enable the flag for employees holding a live session.

    ``app_access_enabled`` was added after the first canary activations, so pre-flag
    employees default to false. Runtime access is now fail-closed on the flag, and only
    an HR grant can produce an active session (HR disable revokes them), so an employee
    holding a live session was granted access before the column existed. Enabling those
    rows — and only those — keeps the fail-closed repair from signing them out.

    Idempotent: a second run reconciles nothing. Deploy-only; never call at runtime.
    """
    cur.execute(
        """
        UPDATE employees e
           SET app_access_enabled = TRUE, updated_at = now()
         WHERE e.app_access_enabled IS NOT TRUE
           AND EXISTS (
                 SELECT 1 FROM employee_sessions s
                  WHERE s.company_code = e.company_code
                    AND s.employee_key = e.employee_key
                    AND s.status = 'active'
                    AND s.expires_at > now()
               )
        RETURNING company_code, employee_key
        """
    )
    return [
        {"company_code": str(row["company_code"]), "employee_key": str(row["employee_key"])}
        for row in (dict(r) for r in cur.fetchall())
    ]


def _company(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def _norm_dept(value: Any) -> str:
    return str(value or "").strip().lower()


def get_company_app_access_policy(
    legacy: Any,
    company_code: str,
    *,
    migrate_names: bool = True,
    persist_migration: bool = True,
) -> dict[str, Any]:
    """Company Employee App access policy.

    - module_enabled False → company OFF (no invites)
    - access_mode ``all`` / ux ``everyone`` → every active employee should have access
    - access_mode ``selected`` + selection_scope ``departments`` → active employees in selected org-unit IDs
    - access_mode ``selected`` + selection_scope ``employees`` → only explicitly listed employee keys
    Runtime invite truth remains: module ON + employment active + ``app_access_enabled``.

    Phase 2C: department scope prefers canonical ``selected_department_org_unit_ids``.
    Historical name-only policies are migrated safely (never guess on ambiguous names).
    """
    company = _company(company_code)
    settings = legacy.company_module_settings(company, MODULE_KEY) or {}
    module_enabled = bool(settings.get("enabled"))
    raw_mode = str(settings.get("access_mode") or MODE_SELECTED).strip().lower()
    mode = raw_mode if raw_mode in ACCESS_MODES else MODE_SELECTED
    depts_raw = settings.get("selected_departments") or settings.get("departments") or []
    if not isinstance(depts_raw, list):
        depts_raw = []
    departments = sorted({str(d).strip() for d in depts_raw if str(d).strip()})
    keys_raw = settings.get("selected_employee_keys") or []
    if not isinstance(keys_raw, list):
        keys_raw = []
    selected_keys = sorted({str(k).strip() for k in keys_raw if str(k).strip()})
    ids_raw = settings.get(SETTINGS_ORG_UNIT_IDS) or []
    if not isinstance(ids_raw, list):
        ids_raw = []
    org_unit_ids = sorted({str(i).strip() for i in ids_raw if str(i).strip()})
    labels_raw = settings.get(SETTINGS_ORG_UNIT_LABELS) or {}
    if not isinstance(labels_raw, dict):
        labels_raw = {}
    org_unit_labels = {str(k): str(v) for k, v in labels_raw.items() if str(k).strip() and str(v).strip()}
    attention_raw = settings.get(SETTINGS_ATTENTION) if isinstance(settings.get(SETTINGS_ATTENTION), dict) else {}
    scope_raw = str(settings.get("selection_scope") or "").strip().lower()
    if mode == MODE_ALL:
        ux_mode = UX_EVERYONE
        selection_scope = None
    elif scope_raw == SCOPE_EMPLOYEES or (not departments and not org_unit_ids and selected_keys):
        ux_mode = UX_EMPLOYEES
        selection_scope = SCOPE_EMPLOYEES
    elif departments or org_unit_ids or scope_raw == SCOPE_DEPARTMENTS:
        ux_mode = UX_DEPARTMENTS
        selection_scope = SCOPE_DEPARTMENTS
    else:
        # Legacy selected with empty depts/keys — treat as employees (explicit flags only).
        ux_mode = UX_EMPLOYEES
        selection_scope = SCOPE_EMPLOYEES

    migration: dict[str, Any] = {"ran": False}
    if migrate_names and ux_mode == UX_DEPARTMENTS and departments and not org_unit_ids:
        migration = migrate_selected_department_names_to_ids(
            legacy,
            company,
            names=departments,
            existing_ids=org_unit_ids,
            existing_labels=org_unit_labels,
            persist=persist_migration,
        )
        org_unit_ids = list(migration.get("selected_department_org_unit_ids") or org_unit_ids)
        org_unit_labels = dict(migration.get("selected_department_org_unit_labels") or org_unit_labels)
        attention_raw = dict(migration.get("policy_attention") or attention_raw)
        if migration.get("persisted"):
            # Refresh settings after persist
            settings = legacy.company_module_settings(company, MODULE_KEY) or {}
            departments = sorted(
                {
                    str(d).strip()
                    for d in (settings.get("selected_departments") or departments)
                    if str(d).strip()
                }
            )

    # Refresh lifecycle attention (archived/missing units) without remapping by name.
    attention = evaluate_department_policy_attention(
        legacy,
        company,
        org_unit_ids=org_unit_ids,
        org_unit_labels=org_unit_labels,
        prior_attention=attention_raw,
    )
    if persist_migration and attention.get("changed") and ux_mode == UX_DEPARTMENTS:
        _persist_policy_attention(legacy, company, attention)

    # Display names for selected IDs (live name preferred; historical label fallback).
    unit_meta = _org_units_meta(legacy, company, org_unit_ids)
    selected_departments_display = []
    for uid in org_unit_ids:
        meta = unit_meta.get(uid) or {}
        label = str(meta.get("name") or org_unit_labels.get(uid) or uid).strip()
        selected_departments_display.append(label)

    return {
        "ok": True,
        "company_code": company,
        "contract_version": CONTRACT_VERSION,
        "phase": PHASE_2C,
        "module_enabled": module_enabled,
        "access_mode": mode,
        "selection_scope": selection_scope,
        "ux_mode": ux_mode,
        # Legacy name field: display labels for selected IDs (or unresolved historical names).
        "selected_departments": selected_departments_display or departments,
        "selected_department_org_unit_ids": org_unit_ids,
        "selected_department_org_unit_labels": org_unit_labels,
        "selected_employee_keys": selected_keys,
        "policy_attention": {
            "needs_attention": bool(attention.get("needs_attention")),
            "reasons": list(attention.get("reasons") or []),
            "ambiguous_names": list(attention.get("ambiguous_names") or []),
            "unresolved_names": list(attention.get("unresolved_names") or []),
            "archived_org_unit_ids": list(attention.get("archived_org_unit_ids") or []),
            "missing_org_unit_ids": list(attention.get("missing_org_unit_ids") or []),
            "message_en": attention.get("message_en"),
            "message_ar": attention.get("message_ar"),
        },
        "name_migration": {
            "ran": bool(migration.get("ran")),
            "migrated_names": list(migration.get("migrated_names") or []),
            "ambiguous_names": list(migration.get("ambiguous_names") or []),
            "unresolved_names": list(migration.get("unresolved_names") or []),
            "persisted": bool(migration.get("persisted")),
        },
        "company_app_status": "on" if module_enabled else "off",
        "future_hire": {
            UX_EVERYONE: "auto_eligible_when_active",
            UX_DEPARTMENTS: "auto_eligible_when_active_in_selected_department",
            UX_EMPLOYEES: "no_automatic_access",
        }.get(ux_mode),
        "large_removal_threshold": LARGE_REMOVAL_THRESHOLD,
    }


def set_company_app_access_policy(
    legacy: Any,
    context: dict[str, Any],
    *,
    module_enabled: bool | None = None,
    access_mode: str | None = None,
    selected_departments: list[str] | None = None,
    selected_department_org_unit_ids: list[str] | None = None,
    selected_employee_keys: list[str] | None = None,
    selection_scope: str | None = None,
    ux_mode: str | None = None,
    sync_invites: bool = False,
    source: str = "dashboard",
    allow_module_toggle: bool = True,
    clear_attention: bool = False,
) -> dict[str, Any]:
    """Update company Employee App access policy on the existing company_modules row.

    Prefer ``apply_access_policy`` from Setup Console for durable reconcile + preview.
    Phase 1 ownership: module on/off is Setup Console-owned.
    Phase 2C: department mode stores canonical org-unit IDs.
    """
    company = _company(context.get("company_code"))
    if module_enabled is not None and not allow_module_toggle:
        raise legacy.HTTPException(
            status_code=422,
            detail={
                "error": "module_enable_owned_by_setup_console",
                "message": (
                    "Turning the Employee App on or off is configured in Setup Console. "
                    "Here you can only change who is eligible once the app is on."
                ),
            },
        )

    # Normalize product UX → storage fields.
    try:
        resolved = _resolve_ux_to_storage(
            ux_mode=ux_mode,
            access_mode=access_mode,
            selection_scope=selection_scope,
            selected_departments=selected_departments,
            selected_department_org_unit_ids=selected_department_org_unit_ids,
            selected_employee_keys=selected_employee_keys,
        )
    except ValueError as exc:
        raise legacy.HTTPException(
            status_code=422,
            detail={"error": str(exc), "message": "Invalid Employee App access mode."},
        ) from exc
    mode = resolved.get("access_mode")
    scope = resolved.get("selection_scope")
    depts = resolved.get("selected_departments")
    org_ids = resolved.get("selected_department_org_unit_ids")
    keys = resolved.get("selected_employee_keys")

    source_n = str(source or "dashboard").strip() or "dashboard"
    org_labels: dict[str, str] = {}
    if org_ids is not None:
        meta = _org_units_meta(legacy, company, org_ids)
        for uid in org_ids:
            name = str((meta.get(uid) or {}).get("name") or "").strip()
            if name:
                org_labels[uid] = name
            elif uid:
                # Preserve prior historical label if unit missing/archived without name join.
                org_labels[uid] = uid

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            cur.execute(
                """
                SELECT enabled, settings FROM company_modules
                WHERE company_code=%s AND module_key=%s
                LIMIT 1 FOR UPDATE
                """,
                (company, MODULE_KEY),
            )
            row = cur.fetchone()
            current_settings: dict[str, Any] = {}
            current_enabled = False
            if row:
                current_enabled = bool(dict(row).get("enabled"))
                raw = dict(row).get("settings")
                current_settings = dict(raw) if isinstance(raw, dict) else {}

            next_enabled = current_enabled if module_enabled is None else bool(module_enabled)
            if mode is not None:
                current_settings["access_mode"] = mode
            if scope is not None:
                if scope:
                    current_settings["selection_scope"] = scope
                else:
                    current_settings.pop("selection_scope", None)
            if depts is not None:
                current_settings["selected_departments"] = depts
            if org_ids is not None:
                current_settings[SETTINGS_ORG_UNIT_IDS] = org_ids
                # Merge labels: keep historical names for removed IDs only in attention audit elsewhere;
                # for current IDs store live labels.
                prior_labels = current_settings.get(SETTINGS_ORG_UNIT_LABELS)
                merged_labels = dict(prior_labels) if isinstance(prior_labels, dict) else {}
                for uid, label in org_labels.items():
                    merged_labels[uid] = label
                # Drop labels for IDs no longer selected (historical audit is in admin_audit).
                current_settings[SETTINGS_ORG_UNIT_LABELS] = {
                    k: v for k, v in merged_labels.items() if k in set(org_ids)
                }
            if keys is not None:
                current_settings["selected_employee_keys"] = keys
            if clear_attention or (org_ids is not None and scope == SCOPE_DEPARTMENTS):
                # Fresh explicit ID selection clears name-migration ambiguity; lifecycle re-eval on next get.
                current_settings[SETTINGS_ATTENTION] = {
                    "needs_attention": False,
                    "reasons": [],
                    "ambiguous_names": [],
                    "unresolved_names": [],
                    "archived_org_unit_ids": [],
                    "missing_org_unit_ids": [],
                    "cleared_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                }
            # Default mode when enabling module without explicit mode.
            if next_enabled and not current_settings.get("access_mode"):
                current_settings["access_mode"] = MODE_SELECTED
                current_settings["selection_scope"] = SCOPE_EMPLOYEES

            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE
                  SET enabled=EXCLUDED.enabled,
                      settings=EXCLUDED.settings,
                      source=EXCLUDED.source,
                      updated_at=now()
                """,
                (company, MODULE_KEY, next_enabled, source_n, json.dumps(current_settings)),
            )
            conn.commit()

    policy = get_company_app_access_policy(legacy, company, migrate_names=False, persist_migration=False)
    invite_summary: dict[str, Any] | None = None
    if sync_invites and policy.get("module_enabled"):
        ux = policy.get("ux_mode")
        if ux == UX_EVERYONE:
            invite_summary = enable_app_access_bulk(
                legacy, context, enable_all_active=True, reason="company_policy_mode_all"
            )
        elif ux == UX_DEPARTMENTS and (policy.get("selected_department_org_unit_ids") or policy.get("selected_departments") or []):
            invite_summary = enable_app_access_bulk(
                legacy,
                context,
                department_org_unit_ids=list(policy.get("selected_department_org_unit_ids") or []),
                departments=list(policy.get("selected_departments") or []),
                reason="company_policy_departments",
            )
        elif ux == UX_EMPLOYEES and (policy.get("selected_employee_keys") or []):
            invite_summary = enable_app_access_bulk(
                legacy,
                context,
                employee_keys=list(policy.get("selected_employee_keys") or []),
                reason="company_policy_employees",
            )
        else:
            invite_summary = sync_invites_for_eligible_employees(
                legacy,
                company_code=company,
                actor_user_id=str(context.get("actor_user_id") or context.get("user_id") or "") or None,
                trigger_source=TRIGGER_ACCESS_POLICY,
            )
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_access_policy_updated",
            summary="Updated Employee App company access policy.",
            target_type="company",
            target=company,
            details={"policy": policy, "invite_summary": invite_summary, "source": source_n},
        )
    except Exception:
        logger.warning("app access policy audit failed", exc_info=True)
    return {"ok": True, "policy": policy, "invite_summary": invite_summary, "source": source_n}


def _resolve_ux_to_storage(
    *,
    ux_mode: str | None,
    access_mode: str | None,
    selection_scope: str | None,
    selected_departments: list[str] | None,
    selected_employee_keys: list[str] | None,
    selected_department_org_unit_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Map product UX choice onto storage fields. Unspecified fields stay None (no overwrite)."""
    out: dict[str, Any] = {
        "access_mode": None,
        "selection_scope": None,
        "selected_departments": None,
        "selected_department_org_unit_ids": None,
        "selected_employee_keys": None,
    }
    ux = str(ux_mode or "").strip().lower() or None
    if ux:
        if ux not in UX_MODES:
            raise ValueError("invalid_ux_mode")
        if ux == UX_EVERYONE:
            out["access_mode"] = MODE_ALL
            out["selection_scope"] = ""  # clear
            out["selected_departments"] = []
            out["selected_department_org_unit_ids"] = []
            out["selected_employee_keys"] = []
        elif ux == UX_DEPARTMENTS:
            out["access_mode"] = MODE_SELECTED
            out["selection_scope"] = SCOPE_DEPARTMENTS
            out["selected_employee_keys"] = []
            if selected_department_org_unit_ids is not None:
                out["selected_department_org_unit_ids"] = sorted(
                    {str(i).strip() for i in selected_department_org_unit_ids if str(i).strip()}
                )
                # Keep display names optional; IDs are source of truth.
                if selected_departments is not None:
                    out["selected_departments"] = sorted(
                        {str(d).strip() for d in selected_departments if str(d).strip()}
                    )
                else:
                    out["selected_departments"] = []
            elif selected_departments is not None:
                # Legacy name-only write — store names; migration on next get converts if unambiguous.
                out["selected_departments"] = sorted({str(d).strip() for d in selected_departments if str(d).strip()})
                out["selected_department_org_unit_ids"] = None
            else:
                out["selected_departments"] = None
                out["selected_department_org_unit_ids"] = None
        else:
            out["access_mode"] = MODE_SELECTED
            out["selection_scope"] = SCOPE_EMPLOYEES
            out["selected_departments"] = []
            out["selected_department_org_unit_ids"] = []
            if selected_employee_keys is not None:
                out["selected_employee_keys"] = sorted({str(k).strip() for k in selected_employee_keys if str(k).strip()})
        return out

    if access_mode is not None:
        mode = str(access_mode).strip().lower()
        if mode not in ACCESS_MODES:
            raise ValueError("invalid_access_mode")
        out["access_mode"] = mode
        if mode == MODE_ALL:
            out["selection_scope"] = ""
            out["selected_departments"] = [] if selected_departments is None else sorted({str(d).strip() for d in selected_departments if str(d).strip()})
            out["selected_department_org_unit_ids"] = [] if selected_department_org_unit_ids is None else sorted({str(i).strip() for i in selected_department_org_unit_ids if str(i).strip()})
            out["selected_employee_keys"] = [] if selected_employee_keys is None else sorted({str(k).strip() for k in selected_employee_keys if str(k).strip()})
    if selection_scope is not None:
        scope = str(selection_scope).strip().lower()
        out["selection_scope"] = scope if scope in {SCOPE_DEPARTMENTS, SCOPE_EMPLOYEES} else ""
    if selected_departments is not None and out["selected_departments"] is None:
        out["selected_departments"] = sorted({str(d).strip() for d in selected_departments if str(d).strip()})
    if selected_department_org_unit_ids is not None and out["selected_department_org_unit_ids"] is None:
        out["selected_department_org_unit_ids"] = sorted(
            {str(i).strip() for i in selected_department_org_unit_ids if str(i).strip()}
        )
    if selected_employee_keys is not None and out["selected_employee_keys"] is None:
        out["selected_employee_keys"] = sorted({str(k).strip() for k in selected_employee_keys if str(k).strip()})
    return out


def _employee_department(employee: dict[str, Any] | None) -> str:
    emp = employee or {}
    profile = emp.get("profile") if isinstance(emp.get("profile"), dict) else {}
    raw = emp.get("raw_json") if isinstance(emp.get("raw_json"), dict) else {}
    return str(
        emp.get("department")
        or profile.get("department")
        or raw.get("department")
        or ""
    ).strip()


def employment_eligible(employee: dict[str, Any] | None) -> bool:
    if not employee:
        return False
    status = str(employee.get("employment_status") or "active").strip().lower()
    return status in {"", "active"}


def is_employee_app_access_eligible(
    legacy: Any,
    *,
    company_code: str,
    employee: dict[str, Any] | None,
    policy: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Return (eligible, reason_code).

    Invite requires an explicit employee-level enable flag. Company mode
    (all/selected) controls bulk enable UX; it does not silently invite on create.
    """
    company = _company(company_code)
    if not legacy.employee_app_enabled():
        return False, "platform_employee_app_disabled"
    pol = policy or get_company_app_access_policy(legacy, company)
    if not pol.get("module_enabled"):
        return False, "company_app_off"
    if not employment_eligible(employee):
        return False, "employee_not_employment_eligible"
    if bool((employee or {}).get("app_access_enabled")):
        return True, "employee_enabled"
    # Department group membership counts as eligible when company is in selected mode
    # with departments configured (HR enabled a group without flipping each row yet).
    # Prefer explicit flags from enable_app_access_bulk(departments=...) which sets flags.
    # Group policy without flags does NOT auto-invite — bulk enable must run.
    return False, "employee_access_disabled"


def get_employee_app_access_state(legacy: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    company = _company(company_code)
    employee = legacy.find_employee_by_key(employee_key, company_code=company)
    if not employee:
        return {"ok": False, "error": "employee_not_found"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            cur.execute(
                """
                SELECT app_access_enabled FROM employees
                WHERE company_code=%s AND employee_key=%s
                LIMIT 1
                """,
                (company, str(employee_key)),
            )
            row = cur.fetchone()
            conn.commit()
    if row:
        employee["app_access_enabled"] = bool(dict(row).get("app_access_enabled"))
    policy = get_company_app_access_policy(legacy, company)
    eligible, reason = is_employee_app_access_eligible(
        legacy, company_code=company, employee=employee, policy=policy
    )
    return {
        "ok": True,
        "employee_key": str(employee_key),
        "app_access_enabled": bool(employee.get("app_access_enabled")),
        "eligible": eligible,
        "eligibility_reason": reason,
        "policy": {
            "module_enabled": policy.get("module_enabled"),
            "access_mode": policy.get("access_mode"),
            "selected_departments": policy.get("selected_departments"),
            "company_app_status": policy.get("company_app_status"),
        },
    }


def _set_employee_flag(legacy: Any, *, company: str, employee_key: str, enabled: bool) -> bool:
    """Set flag; return True if value changed."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            cur.execute(
                """
                UPDATE employees
                SET app_access_enabled=%s, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                  AND app_access_enabled IS DISTINCT FROM %s
                RETURNING employee_key
                """,
                (bool(enabled), company, str(employee_key), bool(enabled)),
            )
            changed = bool(cur.fetchone())
            if not changed:
                # Ensure row exists / flag is correct even if unchanged.
                cur.execute(
                    """
                    UPDATE employees SET app_access_enabled=%s, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (bool(enabled), company, str(employee_key)),
                )
            conn.commit()
    return changed


def set_employee_app_access(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    enabled: bool,
    reason: str,
    deliver_invite: bool = True,
) -> dict[str, Any]:
    """Enable or disable Employee App access for one Employee 360 employee.

    Enable → set flag → existing auto invite+delivery (idempotent).
    Disable → clear flag → existing revoke/session semantics (no new invite path).
    """
    company = _company(context.get("company_code"))
    employee = legacy.find_employee_by_key(employee_key, company_code=company)
    if not employee:
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    if not legacy.context_manager_allows_employee(context, employee, company_code=company):
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})

    policy = get_company_app_access_policy(legacy, company)
    if enabled and not policy.get("module_enabled"):
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "company_app_off",
                "message": "Turn on the Employee App for this company before enabling employee access.",
            },
        )
    if enabled and not employment_eligible(employee):
        raise legacy.HTTPException(
            status_code=422,
            detail={"error": "employee_not_eligible", "message": "Only active employees can receive app access."},
        )

    changed = _set_employee_flag(legacy, company=company, employee_key=employee_key, enabled=bool(enabled))
    invitation: dict[str, Any] | None = None
    revoke_result: dict[str, Any] | None = None

    if enabled and deliver_invite:
        import employee_app_invitation as _inv

        employee = legacy.find_employee_by_key(employee_key, company_code=company) or employee
        employee["app_access_enabled"] = True
        invitation = _inv.maybe_auto_invite_employee(
            legacy,
            company_code=company,
            employee=employee,
            trigger_source=TRIGGER_ACCESS_ENABLED,
            idempotency_key=f"access_enabled:{employee_key}",
        )
    elif not enabled:
        # Prevent new invites + reuse existing revoke for active sessions / pending codes.
        # The cleared flag already blocks runtime access fail-closed on every /app request,
        # refresh and activation, so a revoke failure cannot leave access usable — but it
        # must never be reported as a clean revoke either.
        revoked = 0
        revoke_error: str | None = None
        for attempt in (1, 2):
            try:
                revoked = int(
                    legacy.revoke_employee_app_access(company, str(employee_key), reason="app_access_disabled") or 0
                )
                revoke_error = None
                break
            except Exception as exc:  # noqa: BLE001 — reported, never swallowed
                revoke_error = f"{type(exc).__name__}: {exc}"[:300]
                logger.exception(
                    "revoke on disable failed employee=%s attempt=%s", employee_key, attempt
                )
        # Also supersede pending invites (revoke_employee_app_access may already do sessions;
        # mirror dashboard revoke invite supersede for consistency).
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_app_invites
                    SET status='superseded', idempotency_key=NULL, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s AND status='pending'
                    """,
                    (company, str(employee_key)),
                )
                superseded = int(cur.rowcount or 0)
                cur.execute(
                    """
                    SELECT count(*) AS n FROM employee_sessions
                    WHERE company_code=%s AND employee_key=%s AND status='active'
                    """,
                    (company, str(employee_key)),
                )
                sessions_still_active = int(dict(cur.fetchone() or {}).get("n") or 0)
                conn.commit()
        revoke_result = {
            "sessions_revoked": revoked,
            "pending_invites_superseded": superseded,
            "sessions_still_active": sessions_still_active,
            # Access is blocked by the flag regardless; this reports cleanup health only.
            "revoke_clean": revoke_error is None and sessions_still_active == 0,
        }
        if revoke_error:
            revoke_result["revoke_error"] = revoke_error

    state = get_employee_app_access_state(legacy, company_code=company, employee_key=employee_key)
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_access_enabled" if enabled else "employee_app_access_disabled",
            summary=("Enabled" if enabled else "Disabled") + " employee app access.",
            target_type="employee",
            target=str(employee_key),
            details={
                "reason": reason,
                "changed": changed,
                "invitation": {
                    k: invitation.get(k)
                    for k in ("ok", "skipped", "reason", "invite_id", "delivered", "skipped_duplicate", "delivery_status", "error")
                    if invitation and k in invitation
                }
                if invitation
                else None,
                "revoke": revoke_result,
            },
        )
    except Exception:
        logger.warning("employee app access audit failed", exc_info=True)

    return {
        "ok": True,
        "changed": changed,
        "enabled": bool(enabled),
        "state": state,
        "invitation": invitation,
        "revoke": revoke_result,
    }


def enable_app_access_bulk(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_keys: list[str] | None = None,
    departments: list[str] | None = None,
    department_org_unit_ids: list[str] | None = None,
    enable_all_active: bool = False,
    reason: str,
) -> dict[str, Any]:
    """Enable access for selected keys, departments, or all active employees. Idempotent invites."""
    company = _company(context.get("company_code"))
    policy = get_company_app_access_policy(legacy, company, migrate_names=False, persist_migration=False)
    if not policy.get("module_enabled"):
        raise legacy.HTTPException(
            status_code=403,
            detail={"error": "company_app_off", "message": "Turn on the Employee App for this company first."},
        )

    targets: list[str] = []
    org_ids = {str(i).strip() for i in (department_org_unit_ids or []) if str(i).strip()}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            if enable_all_active:
                cur.execute(
                    """
                    SELECT employee_key FROM employees
                    WHERE company_code=%s
                      AND COALESCE(NULLIF(lower(employment_status), ''), 'active') = 'active'
                    """,
                    (company,),
                )
                targets.extend(str(dict(r).get("employee_key") or "") for r in cur.fetchall())
            if org_ids:
                rows = _list_active_employees(legacy, company)
                for emp in rows:
                    if str(emp.get("department_org_unit_id") or "").strip() in org_ids:
                        targets.append(str(emp.get("employee_key") or ""))
            elif departments:
                dept_norms = {_norm_dept(d) for d in departments if str(d).strip()}
                cur.execute(
                    """
                    SELECT employee_key, profile, raw_json FROM employees
                    WHERE company_code=%s
                      AND COALESCE(NULLIF(lower(employment_status), ''), 'active') = 'active'
                    """,
                    (company,),
                )
                for r in cur.fetchall():
                    row = dict(r)
                    emp = {
                        "employee_key": row.get("employee_key"),
                        "profile": row.get("profile"),
                        "raw_json": row.get("raw_json"),
                    }
                    if _norm_dept(_employee_department(emp)) in dept_norms:
                        targets.append(str(row.get("employee_key") or ""))
            if employee_keys:
                targets.extend(str(k).strip() for k in employee_keys if str(k).strip())
            conn.commit()

    # Dedupe while preserving order.
    seen: set[str] = set()
    unique_keys: list[str] = []
    for key in targets:
        if key and key not in seen:
            seen.add(key)
            unique_keys.append(key)

    results = []
    invited = 0
    skipped = 0
    errors = 0
    for key in unique_keys:
        try:
            out = set_employee_app_access(
                legacy,
                context,
                employee_key=key,
                enabled=True,
                reason=reason,
                deliver_invite=True,
            )
            inv = out.get("invitation") or {}
            if inv.get("skipped_duplicate") or inv.get("skipped"):
                skipped += 1
            elif inv.get("ok") or out.get("changed"):
                invited += 1
            results.append({"employee_key": key, "ok": True, "invitation": inv.get("delivery_status") or inv.get("reason")})
        except Exception as exc:
            errors += 1
            results.append({"employee_key": key, "ok": False, "error": str(exc)[:200]})
            logger.exception("bulk enable failed employee=%s", key)

    return {
        "ok": errors == 0,
        "requested": len(unique_keys),
        "invited_or_enabled": invited,
        "skipped_duplicate": skipped,
        "errors": errors,
        "results": results[:50],
        "results_truncated": len(results) > 50,
        "reason": reason,
    }


def sync_invites_for_eligible_employees(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str | None = None,
    trigger_source: str = TRIGGER_ACCESS_POLICY,
) -> dict[str, Any]:
    """Issue invites for employees who are currently eligible (idempotent, no spam)."""
    import employee_app_invitation as _inv

    company = _company(company_code)
    policy = get_company_app_access_policy(legacy, company)
    if not policy.get("module_enabled"):
        return {"ok": True, "skipped": True, "reason": "company_app_off", "count": 0}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            cur.execute(
                """
                SELECT * FROM employees
                WHERE company_code=%s
                  AND COALESCE(NULLIF(lower(employment_status), ''), 'active') = 'active'
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()

    issued = 0
    skipped = 0
    for emp in rows:
        eligible, _reason = is_employee_app_access_eligible(
            legacy, company_code=company, employee=emp, policy=policy
        )
        if not eligible:
            continue
        key = str(emp.get("employee_key") or "")
        result = _inv.maybe_auto_invite_employee(
            legacy,
            company_code=company,
            employee=emp,
            trigger_source=trigger_source,
            idempotency_key=f"{trigger_source}:{key}",
        )
        if result.get("skipped_duplicate") or result.get("skipped"):
            skipped += 1
        elif result.get("ok"):
            issued += 1
    return {"ok": True, "issued": issued, "skipped_duplicate": skipped, "actor_user_id": actor_user_id}


def assert_invite_allowed(legacy: Any, *, company_code: str, employee: dict[str, Any]) -> None:
    """Raise EmployeeAppInviteDenied-compatible error if invite must not be issued."""
    eligible, reason = is_employee_app_access_eligible(
        legacy, company_code=company_code, employee=employee
    )
    if eligible:
        return
    # Map to existing deny vocabulary where possible.
    if reason == "company_app_off":
        raise legacy.EmployeeAppInviteDenied("employee_app_not_enabled_for_company")
    if reason == "platform_employee_app_disabled":
        raise legacy.EmployeeAppInviteDenied("employee_app_disabled")
    raise legacy.EmployeeAppInviteDenied("employee_app_access_not_enabled")


# ---------------------------------------------------------------------------
# Phase 2B — durable policy desired-state, preview, apply, reconcile
# ---------------------------------------------------------------------------


def employee_desired_by_policy(policy: dict[str, Any], employee: dict[str, Any] | None) -> bool:
    """Whether durable company policy says this active employee should have access.

    Distinct from runtime eligibility (which also requires the flag to already be set
    for invites). Used for reconcile / preview.

    Phase 2C: department mode matches canonical ``department_org_unit_id`` against
    ``selected_department_org_unit_ids``. Name matching is not used when IDs exist.
    Ambiguous name-only policies (needs_attention without IDs) fail closed.
    """
    if not policy.get("module_enabled"):
        return False
    if not employment_eligible(employee):
        return False
    ux = str(policy.get("ux_mode") or "").strip().lower()
    if ux == UX_EVERYONE or policy.get("access_mode") == MODE_ALL:
        return True
    if ux == UX_DEPARTMENTS:
        ids = {
            str(i).strip()
            for i in (policy.get("selected_department_org_unit_ids") or [])
            if str(i).strip()
        }
        if ids:
            emp_id = str((employee or {}).get("department_org_unit_id") or "").strip()
            return bool(emp_id and emp_id in ids)
        attention = policy.get("policy_attention") if isinstance(policy.get("policy_attention"), dict) else {}
        if attention.get("needs_attention") or attention.get("ambiguous_names") or attention.get("unresolved_names"):
            # Fail closed until HR resolves ambiguous/historical name migration.
            return False
        # Pre-2C name-only policy (unambiguous path not yet migrated in this in-memory proposal).
        depts = {_norm_dept(d) for d in (policy.get("selected_departments") or [])}
        if not depts:
            return False
        return _norm_dept(_employee_department(employee)) in depts
    # employees scope (explicit list)
    keys = {str(k).strip() for k in (policy.get("selected_employee_keys") or []) if str(k).strip()}
    if not keys:
        return False
    return str((employee or {}).get("employee_key") or "").strip() in keys


def _inclusion_reason(policy: dict[str, Any], employee: dict[str, Any], *, desired: bool, current: bool) -> str:
    """Human-readable reason for preview drill-down."""
    ux = str(policy.get("ux_mode") or "").strip().lower()
    if desired and not current:
        if ux == UX_EVERYONE:
            return "everyone_policy"
        if ux == UX_DEPARTMENTS:
            return "selected_department"
        return "selected_employee"
    if current and not desired:
        if ux == UX_EVERYONE:
            return "not_active_or_module"
        if ux == UX_DEPARTMENTS:
            return "no_longer_in_selected_department"
        return "no_longer_explicitly_selected"
    if desired and current:
        return "unchanged_in_scope"
    return "unchanged_out_of_scope"


def _list_active_employees(legacy: Any, company: str) -> list[dict[str, Any]]:
    """Active employees with current department_org_unit_id attached (batch, not N+1)."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            try:
                cur.execute(
                    """
                    SELECT e.employee_key, e.name, e.phone, e.email, e.employment_status, e.profile, e.raw_json,
                           e.app_access_enabled,
                           a.department_unit_id::text AS department_org_unit_id,
                           d.name AS department_unit_name,
                           d.status AS department_unit_status
                    FROM employees e
                    LEFT JOIN LATERAL (
                      SELECT h.department_unit_id
                      FROM employee_org_assignment_history h
                      WHERE h.company_code = e.company_code
                        AND h.employee_key = e.employee_key
                        AND h.effective_from <= CURRENT_DATE
                        AND (h.effective_to IS NULL OR h.effective_to >= CURRENT_DATE)
                      ORDER BY h.effective_from DESC, h.created_at DESC
                      LIMIT 1
                    ) a ON TRUE
                    LEFT JOIN employee_org_units d ON d.org_unit_id = a.department_unit_id
                    WHERE e.company_code=%s
                      AND COALESCE(NULLIF(lower(e.employment_status), ''), 'active') = 'active'
                    ORDER BY e.name NULLS LAST, e.employee_key
                    """,
                    (company,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
                for emp in rows:
                    # Prefer live org-unit name for display; keep profile department as fallback.
                    if emp.get("department_unit_name"):
                        emp["department"] = emp.get("department_unit_name")
                    else:
                        emp["department"] = _employee_department(emp)
                return rows
            except Exception:
                conn.rollback()
                logger.warning("org-joined employee list failed; falling back", exc_info=True)
                cur.execute(
                    """
                    SELECT employee_key, name, phone, email, employment_status, profile, raw_json,
                           app_access_enabled
                    FROM employees
                    WHERE company_code=%s
                      AND COALESCE(NULLIF(lower(employment_status), ''), 'active') = 'active'
                    ORDER BY name NULLS LAST, employee_key
                    """,
                    (company,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
                for emp in rows:
                    emp["department"] = _employee_department(emp)
                    emp["department_org_unit_id"] = None
                return rows


def _active_session_count(legacy: Any, company: str, employee_keys: list[str]) -> int:
    if not employee_keys:
        return 0
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM employee_app_sessions
                    WHERE company_code=%s AND employee_key = ANY(%s) AND revoked_at IS NULL
                    """,
                    (company, employee_keys),
                )
                row = cur.fetchone()
                conn.commit()
        if not row:
            return 0
        return int(dict(row).get("n") if isinstance(row, dict) else row[0] or 0)
    except Exception:
        return 0


def _pending_invite_count(legacy: Any, company: str, employee_keys: list[str]) -> int:
    if not employee_keys:
        return 0
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM employee_app_invites
                    WHERE company_code=%s AND employee_key = ANY(%s) AND status='pending'
                    """,
                    (company, employee_keys),
                )
                row = cur.fetchone()
                conn.commit()
        if not row:
            return 0
        return int(dict(row).get("n") if isinstance(row, dict) else row[0] or 0)
    except Exception:
        return 0


def build_proposed_policy(
    legacy: Any,
    company_code: str,
    *,
    ux_mode: str,
    selected_departments: list[str] | None = None,
    selected_department_org_unit_ids: list[str] | None = None,
    selected_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Build a proposed policy dict (not persisted) for preview."""
    company = _company(company_code)
    current = get_company_app_access_policy(legacy, company, migrate_names=False, persist_migration=False)
    try:
        resolved = _resolve_ux_to_storage(
            ux_mode=ux_mode,
            access_mode=None,
            selection_scope=None,
            selected_departments=selected_departments,
            selected_department_org_unit_ids=selected_department_org_unit_ids,
            selected_employee_keys=selected_employee_keys,
        )
    except ValueError as exc:
        raise legacy.HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    # Fill unspecified from current when needed (e.g. departments mode without new list)
    depts = resolved["selected_departments"]
    if depts is None:
        depts = list(current.get("selected_departments") or [])
    org_ids = resolved["selected_department_org_unit_ids"]
    if org_ids is None:
        org_ids = list(current.get("selected_department_org_unit_ids") or [])
    keys = resolved["selected_employee_keys"]
    if keys is None:
        keys = list(current.get("selected_employee_keys") or [])
    mode = resolved["access_mode"] or current.get("access_mode")
    scope = resolved["selection_scope"]
    if scope == "":
        scope = None
    elif scope is None:
        scope = current.get("selection_scope")
    ux = str(ux_mode).strip().lower()
    proposed = {
        **current,
        "access_mode": mode,
        "selection_scope": scope,
        "ux_mode": ux,
        "selected_departments": depts if ux == UX_DEPARTMENTS else [],
        "selected_department_org_unit_ids": org_ids if ux == UX_DEPARTMENTS else [],
        "selected_employee_keys": keys if ux == UX_EMPLOYEES else [],
        "module_enabled": current.get("module_enabled"),
    }
    if ux == UX_DEPARTMENTS:
        # Explicit ID proposal is authoritative — clear migration fail-closed for preview.
        proposed["policy_attention"] = {
            **(current.get("policy_attention") or {}),
            "needs_attention": False,
            "ambiguous_names": [],
            "unresolved_names": [],
        } if org_ids is not None else current.get("policy_attention")
    return proposed


def preview_access_policy_impact(
    legacy: Any,
    company_code: str,
    *,
    ux_mode: str,
    selected_departments: list[str] | None = None,
    selected_department_org_unit_ids: list[str] | None = None,
    selected_employee_keys: list[str] | None = None,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Count who would gain / lose / stay unchanged under a proposed policy."""
    company = _company(company_code)
    proposed = build_proposed_policy(
        legacy,
        company,
        ux_mode=ux_mode,
        selected_departments=selected_departments,
        selected_department_org_unit_ids=selected_department_org_unit_ids,
        selected_employee_keys=selected_employee_keys,
    )
    if not proposed.get("module_enabled"):
        return {
            "ok": True,
            "module_enabled": False,
            "will_gain_access": 0,
            "will_lose_access": 0,
            "unchanged": 0,
            "active_sessions_affected": 0,
            "pending_invites_affected": 0,
            "requires_large_removal_confirm": False,
            "message_en": "Employee App is off for this company — turn it on under Modules first.",
            "message_ar": "تطبيق الموظف متوقف لهذه الشركة — فعّله من الوحدات أولاً.",
            "proposed": proposed,
        }

    rows = _list_active_employees(legacy, company)
    gain: list[str] = []
    lose: list[str] = []
    unchanged = 0
    for emp in rows:
        key = str(emp.get("employee_key") or "")
        current = bool(emp.get("app_access_enabled"))
        desired = employee_desired_by_policy(proposed, emp)
        if desired and not current:
            gain.append(key)
        elif current and not desired:
            lose.append(key)
        else:
            unchanged += 1

    sessions = _active_session_count(legacy, company, lose)
    pending = _pending_invite_count(legacy, company, lose)
    requires = len(lose) >= LARGE_REMOVAL_THRESHOLD
    return {
        "ok": True,
        "module_enabled": True,
        "will_gain_access": len(gain),
        "will_lose_access": len(lose),
        "unchanged": unchanged,
        "active_sessions_affected": sessions,
        "pending_invites_affected": pending,
        "requires_large_removal_confirm": requires,
        "large_removal_threshold": LARGE_REMOVAL_THRESHOLD,
        "sample_gain": gain[:sample_limit],
        "sample_lose": lose[:sample_limit],
        "samples_truncated": len(gain) > sample_limit or len(lose) > sample_limit,
        "drilldown_available": True,
        "proposed": {
            "ux_mode": proposed.get("ux_mode"),
            "selected_departments": proposed.get("selected_departments"),
            "selected_department_org_unit_ids": proposed.get("selected_department_org_unit_ids"),
            "selected_employee_keys_count": len(proposed.get("selected_employee_keys") or []),
        },
        "message_en": (
            f"{len(gain)} will gain access, {len(lose)} will lose access"
            + (f" ({sessions} active sessions signed out)" if sessions else "")
            + "."
        ),
        "message_ar": (
            f"{len(gain)} سيحصلون على الوصول، و{len(lose)} سيفقدونه"
            + (f" (تسجيل خروج من {sessions} جلسة نشطة)" if sessions else "")
            + "."
        ),
    }


def _batch_set_flags(legacy: Any, *, company: str, employee_keys: list[str], enabled: bool) -> list[str]:
    """Set flags in one SQL statement; return keys that actually changed."""
    if not employee_keys:
        return []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            cur.execute(
                """
                UPDATE employees
                SET app_access_enabled=%s, updated_at=now()
                WHERE company_code=%s
                  AND employee_key = ANY(%s)
                  AND app_access_enabled IS DISTINCT FROM %s
                RETURNING employee_key
                """,
                (bool(enabled), company, employee_keys, bool(enabled)),
            )
            changed = [str(dict(r).get("employee_key") or "") for r in cur.fetchall()]
            conn.commit()
    return [k for k in changed if k]


def apply_access_policy(
    legacy: Any,
    context: dict[str, Any],
    *,
    ux_mode: str,
    selected_departments: list[str] | None = None,
    selected_department_org_unit_ids: list[str] | None = None,
    selected_employee_keys: list[str] | None = None,
    confirm_large_impact: bool = False,
    reason: str,
) -> dict[str, Any]:
    """Persist durable policy and reconcile all active employees (batch flags + existing invite/revoke)."""
    company = _company(context.get("company_code"))
    if not str(reason or "").strip():
        raise legacy.HTTPException(
            status_code=422,
            detail={
                "error": "audit_reason_required",
                "message": "A reason is required for Employee App access policy changes.",
            },
        )
    preview = preview_access_policy_impact(
        legacy,
        company,
        ux_mode=ux_mode,
        selected_departments=selected_departments,
        selected_department_org_unit_ids=selected_department_org_unit_ids,
        selected_employee_keys=selected_employee_keys,
    )
    if not preview.get("module_enabled"):
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "company_app_off",
                "message": preview.get("message_en"),
                "message_ar": preview.get("message_ar"),
            },
        )
    if preview.get("requires_large_removal_confirm") and not confirm_large_impact:
        raise legacy.HTTPException(
            status_code=409,
            detail={
                "error": "large_removal_confirmation_required",
                "message": (
                    f"This will remove Employee App access from {preview['will_lose_access']} employees"
                    f" and sign out active sessions ({preview['active_sessions_affected']})."
                ),
                "message_ar": (
                    f"سيُزال وصول تطبيق الموظف عن {preview['will_lose_access']} موظفاً"
                    f" مع تسجيل الخروج من الجلسات النشطة ({preview['active_sessions_affected']})."
                ),
                "preview": preview,
            },
        )

    # No-op short circuit
    if preview["will_gain_access"] == 0 and preview["will_lose_access"] == 0:
        # Still persist policy text (e.g. department list change with zero active employees).
        saved = set_company_app_access_policy(
            legacy,
            context,
            ux_mode=ux_mode,
            selected_departments=selected_departments,
            selected_department_org_unit_ids=selected_department_org_unit_ids,
            selected_employee_keys=selected_employee_keys,
            sync_invites=False,
            source="setup_console",
            allow_module_toggle=False,
            clear_attention=True,
        )
        return {
            "ok": True,
            "noop": True,
            "policy": saved.get("policy"),
            "preview": preview,
            "reconcile": {"gained": 0, "lost": 0, "invites": 0, "revokes": 0},
        }

    saved = set_company_app_access_policy(
        legacy,
        context,
        ux_mode=ux_mode,
        selected_departments=selected_departments,
        selected_department_org_unit_ids=selected_department_org_unit_ids,
        selected_employee_keys=selected_employee_keys,
        sync_invites=False,
        source="setup_console",
        allow_module_toggle=False,
        clear_attention=True,
    )
    policy = saved.get("policy") or get_company_app_access_policy(
        legacy, company, migrate_names=False, persist_migration=False
    )

    rows = _list_active_employees(legacy, company)
    gain_keys: list[str] = []
    lose_keys: list[str] = []
    for emp in rows:
        key = str(emp.get("employee_key") or "")
        current = bool(emp.get("app_access_enabled"))
        desired = employee_desired_by_policy(policy, emp)
        if desired and not current:
            gain_keys.append(key)
        elif current and not desired:
            lose_keys.append(key)

    changed_gain = _batch_set_flags(legacy, company=company, employee_keys=gain_keys, enabled=True)
    changed_lose = _batch_set_flags(legacy, company=company, employee_keys=lose_keys, enabled=False)

    import employee_app_invitation as _inv

    invites_ok = 0
    invites_skipped = 0
    for key in changed_gain:
        emp = legacy.find_employee_by_key(key, company_code=company) or {"employee_key": key, "app_access_enabled": True}
        emp["app_access_enabled"] = True
        result = _inv.maybe_auto_invite_employee(
            legacy,
            company_code=company,
            employee=emp,
            trigger_source=TRIGGER_ACCESS_POLICY,
            idempotency_key=f"policy_gain:{key}",
        )
        if result.get("skipped_duplicate") or result.get("skipped"):
            invites_skipped += 1
        elif result.get("ok"):
            invites_ok += 1

    session_touches = 0
    revoke_failures: list[str] = []
    for key in changed_lose:
        try:
            revoked = int(legacy.revoke_employee_app_access(company, key, reason="app_access_policy_removed") or 0)
            if revoked:
                session_touches += 1
        except Exception:
            # The flag is already cleared, so runtime access is blocked fail-closed.
            # Record the cleanup failure instead of reporting a clean reconcile.
            revoke_failures.append(key)
            logger.exception("policy revoke failed employee=%s", key)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_app_invites
                    SET status='superseded', idempotency_key=NULL, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s AND status='pending'
                    """,
                    (company, key),
                )
                conn.commit()

    reconcile = {
        "gained": len(changed_gain),
        "lost": len(changed_lose),
        "invites_issued": invites_ok,
        "invites_skipped": invites_skipped,
        "revokes": len(changed_lose),
        "sessions_touch_attempts": session_touches,
        "revoke_failures": len(revoke_failures),
        "revoke_clean": not revoke_failures,
    }
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_access_policy_applied",
            summary="Applied Employee App access policy with reconcile.",
            target_type="company",
            target=company,
            details={
                "reason": reason,
                "preview": preview,
                "reconcile": reconcile,
                "ux_mode": ux_mode,
                "selected_department_org_unit_ids": selected_department_org_unit_ids,
            },
        )
    except Exception:
        logger.warning("policy apply audit failed", exc_info=True)

    return {
        "ok": True,
        "noop": False,
        "policy": policy,
        "preview": preview,
        "reconcile": reconcile,
    }


def reconcile_employee_app_access(
    legacy: Any,
    context: dict[str, Any] | None,
    *,
    employee_key: str,
    allow_invite: bool = True,
    trigger: str = "reconcile",
) -> dict[str, Any]:
    """Re-evaluate one employee against durable company policy (idempotent).

    ``allow_invite=False`` for migration/import paths (flag may still change when
    policy requires disable; enables without inviting).
    """
    company = _company((context or {}).get("company_code"))
    if not company:
        # Infer from employee row
        emp0 = legacy.find_employee_by_key(employee_key)
        company = _company((emp0 or {}).get("company_code"))
    if not company:
        return {"ok": False, "error": "company_required"}
    ctx = dict(context or {})
    ctx.setdefault("company_code", company)
    ctx.setdefault("actor_user_id", f"system:{trigger}")
    ctx.setdefault("user_id", ctx["actor_user_id"])

    policy = get_company_app_access_policy(legacy, company, migrate_names=False, persist_migration=False)
    state = get_employee_app_access_state(legacy, company_code=company, employee_key=employee_key)
    if not state.get("ok"):
        return state
    employee = legacy.find_employee_by_key(employee_key, company_code=company) or {}
    employee["app_access_enabled"] = bool(state.get("app_access_enabled"))
    # Attach canonical department_org_unit_id for Phase 2C matching.
    try:
        import employee_org_wave4 as w4

        asg = w4.get_assignment_as_of(legacy, company_code=company, employee_key=employee_key)
        if asg and asg.get("department_unit_id"):
            employee["department_org_unit_id"] = str(asg.get("department_unit_id"))
            if asg.get("department_name"):
                employee["department"] = asg.get("department_name")
    except Exception:
        logger.warning("reconcile org attach failed employee=%s", employee_key, exc_info=True)
    desired = employee_desired_by_policy(policy, employee)
    current = bool(employee.get("app_access_enabled"))
    if desired == current:
        return {"ok": True, "changed": False, "desired": desired, "trigger": trigger}

    if desired and not allow_invite:
        # Migration/import: set flag only, never invite from this path.
        changed = _set_employee_flag(legacy, company=company, employee_key=employee_key, enabled=True)
        return {"ok": True, "changed": changed, "desired": True, "invite_skipped": True, "trigger": trigger}

    out = set_employee_app_access(
        legacy,
        ctx,
        employee_key=employee_key,
        enabled=desired,
        reason=f"policy_reconcile:{trigger}",
        deliver_invite=bool(desired and allow_invite),
    )
    return {"ok": True, "changed": bool(out.get("changed")), "desired": desired, "result": out, "trigger": trigger}


def list_company_departments_for_access(legacy: Any, company_code: str) -> dict[str, Any]:
    """Canonical org-unit departments for Setup picker (IDs + names + counts + status)."""
    company = _company(company_code)
    units: list[dict[str, Any]] = []
    try:
        import employee_org_wave4 as w4

        for u in w4.list_org_units(legacy, company_code=company, unit_type="department") or []:
            uid = str((u or {}).get("org_unit_id") or "").strip()
            name = str((u or {}).get("name") or "").strip()
            if not uid or not name:
                continue
            units.append(
                {
                    "org_unit_id": uid,
                    "name": name,
                    "unit_key": (u or {}).get("unit_key"),
                    "status": str((u or {}).get("status") or "active"),
                }
            )
    except Exception:
        logger.warning("org units list failed for access picker", exc_info=True)

    # Active employee counts by department_unit_id (canonical) + name fallback for unassigned.
    counts_by_id: dict[str, int] = {}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT a.department_unit_id::text AS uid, COUNT(*) AS n
                    FROM employees e
                    JOIN LATERAL (
                      SELECT h.department_unit_id
                      FROM employee_org_assignment_history h
                      WHERE h.company_code = e.company_code
                        AND h.employee_key = e.employee_key
                        AND h.effective_from <= CURRENT_DATE
                        AND (h.effective_to IS NULL OR h.effective_to >= CURRENT_DATE)
                      ORDER BY h.effective_from DESC, h.created_at DESC
                      LIMIT 1
                    ) a ON TRUE
                    WHERE e.company_code=%s
                      AND COALESCE(NULLIF(lower(e.employment_status), ''), 'active') = 'active'
                      AND a.department_unit_id IS NOT NULL
                    GROUP BY 1
                    """,
                    (company,),
                )
                for r in cur.fetchall():
                    row = dict(r)
                    uid = str(row.get("uid") or "").strip()
                    if uid:
                        counts_by_id[uid] = int(row.get("n") or 0)
                conn.commit()
            except Exception:
                conn.rollback()
                logger.warning("department count by org unit failed", exc_info=True)

    departments = []
    for u in sorted(units, key=lambda x: str(x.get("name") or "").lower()):
        departments.append(
            {
                "org_unit_id": u["org_unit_id"],
                "name": u["name"],
                "unit_key": u.get("unit_key"),
                "status": u.get("status") or "active",
                "active_employee_count": counts_by_id.get(u["org_unit_id"], 0),
                # Backward-compatible alias used by Phase 2B UI during transition.
                "id": u["org_unit_id"],
            }
        )
    return {"ok": True, "departments": departments, "identity": "org_unit_id"}


def search_employees_for_access(
    legacy: Any,
    company_code: str,
    *,
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    department_org_unit_id: str | None = None,
    employment_status: str | None = "active",
    selected_only: bool = False,
    selected_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Paged roster search for Setup selected-employees mode (never returns full 10k roster)."""
    company = _company(company_code)
    limit_n = max(1, min(int(limit or 50), 100))
    offset_n = max(0, int(offset or 0))
    query = str(q or "").strip()
    like = f"%{query}%"
    dept_id = str(department_org_unit_id or "").strip() or None
    status_filter = str(employment_status or "active").strip().lower()
    if status_filter not in {"active", "all", "inactive", "terminated"}:
        status_filter = "active"
    keys_filter = [str(k).strip() for k in (selected_employee_keys or []) if str(k).strip()]
    if selected_only and not keys_filter:
        return {
            "ok": True,
            "employees": [],
            "total_count": 0,
            "has_more": False,
            "limit": limit_n,
            "offset": offset_n,
            "next_offset": None,
            "page_size_max": 100,
        }

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_access_schema(cur)
            params: list[Any] = [company]
            filters = ["e.company_code=%s"]
            if status_filter == "active":
                filters.append("COALESCE(NULLIF(lower(e.employment_status), ''), 'active') = 'active'")
            elif status_filter != "all":
                filters.append("lower(COALESCE(e.employment_status,'')) = %s")
                params.append(status_filter)

            if keys_filter:
                filters.append("e.employee_key = ANY(%s)")
                params.append(keys_filter)
            if query:
                filters.append(
                    """(
                      e.name ILIKE %s OR e.phone ILIKE %s OR COALESCE(e.email,'') ILIKE %s
                      OR e.employee_key ILIKE %s
                      OR COALESCE(e.profile->>'department','') ILIKE %s
                      OR COALESCE(d.name,'') ILIKE %s
                    )"""
                )
                params.extend([like, like, like, like, like, like])
            if dept_id:
                filters.append("a.department_unit_id::text = %s")
                params.append(dept_id)

            where = " AND ".join(filters)
            sql = f"""
                SELECT e.employee_key, e.name, e.phone, e.email, e.employment_status,
                       COALESCE(d.name, NULLIF(e.profile->>'department',''), NULLIF(e.raw_json->>'department','')) AS department,
                       a.department_unit_id::text AS department_org_unit_id,
                       e.app_access_enabled,
                       COUNT(*) OVER() AS total_count
                FROM employees e
                LEFT JOIN LATERAL (
                  SELECT h.department_unit_id
                  FROM employee_org_assignment_history h
                  WHERE h.company_code = e.company_code
                    AND h.employee_key = e.employee_key
                    AND h.effective_from <= CURRENT_DATE
                    AND (h.effective_to IS NULL OR h.effective_to >= CURRENT_DATE)
                  ORDER BY h.effective_from DESC, h.created_at DESC
                  LIMIT 1
                ) a ON TRUE
                LEFT JOIN employee_org_units d ON d.org_unit_id = a.department_unit_id
                WHERE {where}
                ORDER BY e.name NULLS LAST, e.employee_key
                LIMIT %s OFFSET %s
            """
            params.extend([limit_n, offset_n])
            try:
                cur.execute(sql, tuple(params))
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
            except Exception:
                conn.rollback()
                # Fallback without org joins
                cur.execute(
                    """
                    SELECT employee_key, name, phone, email, employment_status,
                           COALESCE(NULLIF(profile->>'department',''), NULLIF(raw_json->>'department','')) AS department,
                           app_access_enabled,
                           COUNT(*) OVER() AS total_count
                    FROM employees
                    WHERE company_code=%s
                      AND COALESCE(NULLIF(lower(employment_status), ''), 'active') = 'active'
                      AND (%s = '' OR name ILIKE %s OR phone ILIKE %s OR employee_key ILIKE %s)
                    ORDER BY name NULLS LAST, employee_key
                    LIMIT %s OFFSET %s
                    """,
                    (company, query, like, like, like, limit_n, offset_n),
                )
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()

    total = int(rows[0].get("total_count") or 0) if rows else 0
    employees = [
        {
            "employee_key": str(r.get("employee_key") or ""),
            "name": r.get("name"),
            "phone": r.get("phone"),
            "email": r.get("email"),
            "department": r.get("department"),
            "department_org_unit_id": r.get("department_org_unit_id"),
            "employment_status": r.get("employment_status") or "active",
            "app_access_enabled": bool(r.get("app_access_enabled")),
        }
        for r in rows
    ]
    next_offset = offset_n + len(employees) if offset_n + len(employees) < total else None
    return {
        "ok": True,
        "employees": employees,
        "total_count": total,
        "has_more": next_offset is not None,
        "limit": limit_n,
        "offset": offset_n,
        "next_offset": next_offset,
        "page_size_max": 100,
        "filters": {
            "q": query,
            "department_org_unit_id": dept_id,
            "employment_status": status_filter,
            "selected_only": bool(selected_only),
        },
    }


# ---------------------------------------------------------------------------
# Phase 2C — org-unit identity, migration, attention, drill-down, resolve
# ---------------------------------------------------------------------------


def _org_units_meta(legacy: Any, company: str, org_unit_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(i).strip() for i in org_unit_ids if str(i).strip()]
    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        import employee_org_wave4 as w4

        for u in w4.list_org_units(legacy, company_code=company, unit_type="department") or []:
            uid = str((u or {}).get("org_unit_id") or "").strip()
            if uid in set(ids):
                out[uid] = {
                    "org_unit_id": uid,
                    "name": (u or {}).get("name"),
                    "unit_key": (u or {}).get("unit_key"),
                    "status": (u or {}).get("status") or "active",
                }
    except Exception:
        logger.warning("org unit meta lookup failed", exc_info=True)
    # Fill missing via direct SQL (covers archived still in table)
    missing = [i for i in ids if i not in out]
    if missing:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT org_unit_id::text AS org_unit_id, name, unit_key, status
                        FROM employee_org_units
                        WHERE company_code=%s AND org_unit_id::text = ANY(%s)
                        """,
                        (company, missing),
                    )
                    for r in cur.fetchall():
                        row = dict(r)
                        uid = str(row.get("org_unit_id") or "")
                        out[uid] = row
                    conn.commit()
                except Exception:
                    conn.rollback()
    return out


def migrate_selected_department_names_to_ids(
    legacy: Any,
    company_code: str,
    *,
    names: list[str],
    existing_ids: list[str] | None = None,
    existing_labels: dict[str, str] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Map historical department name strings → org-unit IDs.

    Unique name match → migrate. Duplicate/ambiguous names → Needs Attention (never guess).
    Unmatched names → unresolved Needs Attention.
    """
    company = _company(company_code)
    ids = list(existing_ids or [])
    labels = dict(existing_labels or {})
    migrated: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    unresolved: list[str] = []

    # Index units by normalized name
    by_name: dict[str, list[dict[str, Any]]] = {}
    try:
        import employee_org_wave4 as w4

        for u in w4.list_org_units(legacy, company_code=company, unit_type="department") or []:
            name = str((u or {}).get("name") or "").strip()
            if not name:
                continue
            by_name.setdefault(_norm_dept(name), []).append(
                {
                    "org_unit_id": str((u or {}).get("org_unit_id") or ""),
                    "name": name,
                    "status": (u or {}).get("status") or "active",
                    "unit_key": (u or {}).get("unit_key"),
                }
            )
    except Exception:
        logger.warning("migrate name→id: list_org_units failed", exc_info=True)

    for name in names:
        key = _norm_dept(name)
        if not key:
            continue
        matches = by_name.get(key) or []
        # Prefer active units when multiple; still ambiguous if >1 active OR >1 total with no unique active
        active = [m for m in matches if str(m.get("status") or "") == "active"]
        candidates = active if len(active) == 1 else matches
        if len(candidates) == 1:
            uid = str(candidates[0].get("org_unit_id") or "")
            if uid and uid not in ids:
                ids.append(uid)
            if uid:
                labels[uid] = str(candidates[0].get("name") or name)
                migrated.append(name)
        elif len(candidates) > 1:
            ambiguous.append(
                {
                    "name": name,
                    "matches": [
                        {"org_unit_id": m.get("org_unit_id"), "name": m.get("name"), "status": m.get("status")}
                        for m in candidates
                    ],
                }
            )
        else:
            unresolved.append(name)

    ids = sorted({str(i).strip() for i in ids if str(i).strip()})
    needs = bool(ambiguous or unresolved)
    attention = {
        "needs_attention": needs,
        "reasons": (["ambiguous_name_migration"] if ambiguous else [])
        + (["unresolved_name_migration"] if unresolved else []),
        "ambiguous_names": ambiguous,
        "unresolved_names": unresolved,
        "archived_org_unit_ids": [],
        "missing_org_unit_ids": [],
        "message_en": (
            "Some department names could not be mapped to a unique org unit. Choose the correct departments by ID."
            if needs
            else None
        ),
        "message_ar": (
            "تعذر ربط بعض أسماء الأقسام بوحدة تنظيمية فريدة. اختر الأقسام الصحيحة بالمعرّف."
            if needs
            else None
        ),
    }

    persisted = False
    if persist and (migrated or needs):
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT settings FROM company_modules
                    WHERE company_code=%s AND module_key=%s
                    LIMIT 1 FOR UPDATE
                    """,
                    (company, MODULE_KEY),
                )
                row = cur.fetchone()
                settings = dict(dict(row).get("settings") or {}) if row else {}
                if not isinstance(settings, dict):
                    settings = {}
                settings[SETTINGS_ORG_UNIT_IDS] = ids
                settings[SETTINGS_ORG_UNIT_LABELS] = labels
                # Keep original names for audit until HR clears attention.
                settings[SETTINGS_LEGACY_DEPT_NAMES] = sorted({str(n).strip() for n in names if str(n).strip()})
                settings[SETTINGS_ATTENTION] = attention
                if ids and not needs:
                    # Successful full migrate: display names from labels
                    settings[SETTINGS_LEGACY_DEPT_NAMES] = sorted({labels[i] for i in ids if labels.get(i)})
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (
                      %s, %s,
                      COALESCE((SELECT enabled FROM company_modules WHERE company_code=%s AND module_key=%s), false),
                      'setup_console_phase2c_migration',
                      %s::jsonb, now()
                    )
                    ON CONFLICT (company_code, module_key) DO UPDATE
                      SET settings=EXCLUDED.settings, source=EXCLUDED.source, updated_at=now()
                    """,
                    (company, MODULE_KEY, company, MODULE_KEY, json.dumps(settings)),
                )
                conn.commit()
                persisted = True

    return {
        "ran": True,
        "selected_department_org_unit_ids": ids,
        "selected_department_org_unit_labels": labels,
        "policy_attention": attention,
        "migrated_names": migrated,
        "ambiguous_names": ambiguous,
        "unresolved_names": unresolved,
        "persisted": persisted,
    }


def evaluate_department_policy_attention(
    legacy: Any,
    company_code: str,
    *,
    org_unit_ids: list[str],
    org_unit_labels: dict[str, str] | None = None,
    prior_attention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Flag archived/missing org units referenced by policy — never remap by name."""
    prior = dict(prior_attention or {})
    meta = _org_units_meta(legacy, company_code, org_unit_ids)
    archived: list[str] = []
    missing: list[str] = []
    for uid in org_unit_ids:
        info = meta.get(uid)
        if not info:
            missing.append(uid)
        elif str(info.get("status") or "").lower() == "archived":
            archived.append(uid)
    reasons = list(prior.get("reasons") or [])
    # Keep migration reasons until cleared by explicit apply.
    for r in ("ambiguous_name_migration", "unresolved_name_migration"):
        if r in reasons:
            continue
    if archived and "archived_org_unit" not in reasons:
        reasons.append("archived_org_unit")
    if missing and "missing_org_unit" not in reasons:
        reasons.append("missing_org_unit")
    # Drop archived/missing reasons if no longer applicable
    if not archived:
        reasons = [r for r in reasons if r != "archived_org_unit"]
    if not missing:
        reasons = [r for r in reasons if r != "missing_org_unit"]

    needs = bool(
        reasons
        or prior.get("ambiguous_names")
        or prior.get("unresolved_names")
        or archived
        or missing
    )
    message_en = None
    message_ar = None
    if needs:
        parts_en = []
        parts_ar = []
        if prior.get("ambiguous_names") or "ambiguous_name_migration" in reasons:
            parts_en.append("ambiguous department names need an explicit choice")
            parts_ar.append("أسماء أقسام غامضة تحتاج اختياراً صريحاً")
        if archived:
            parts_en.append(f"{len(archived)} selected department(s) are archived")
            parts_ar.append(f"{len(archived)} قسماً مختاراً مؤرشفاً")
        if missing:
            parts_en.append(f"{len(missing)} selected department reference(s) are missing")
            parts_ar.append(f"{len(missing)} مرجعاً قسماً مفقوداً")
        message_en = "Access policy needs attention: " + "; ".join(parts_en) + "."
        message_ar = "سياسة الوصول تحتاج مراجعة: " + "؛ ".join(parts_ar) + "."

    out = {
        "needs_attention": needs,
        "reasons": reasons,
        "ambiguous_names": list(prior.get("ambiguous_names") or []),
        "unresolved_names": list(prior.get("unresolved_names") or []),
        "archived_org_unit_ids": archived,
        "missing_org_unit_ids": missing,
        "org_unit_labels": org_unit_labels or {},
        "message_en": message_en,
        "message_ar": message_ar,
        "changed": (
            archived != list(prior.get("archived_org_unit_ids") or [])
            or missing != list(prior.get("missing_org_unit_ids") or [])
            or bool(needs) != bool(prior.get("needs_attention"))
        ),
    }
    return out


def _persist_policy_attention(legacy: Any, company: str, attention: dict[str, Any]) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT settings FROM company_modules
                WHERE company_code=%s AND module_key=%s
                LIMIT 1 FOR UPDATE
                """,
                (company, MODULE_KEY),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return
            settings = dict(dict(row).get("settings") or {})
            if not isinstance(settings, dict):
                settings = {}
            settings[SETTINGS_ATTENTION] = {
                "needs_attention": bool(attention.get("needs_attention")),
                "reasons": list(attention.get("reasons") or []),
                "ambiguous_names": list(attention.get("ambiguous_names") or []),
                "unresolved_names": list(attention.get("unresolved_names") or []),
                "archived_org_unit_ids": list(attention.get("archived_org_unit_ids") or []),
                "missing_org_unit_ids": list(attention.get("missing_org_unit_ids") or []),
                "message_en": attention.get("message_en"),
                "message_ar": attention.get("message_ar"),
            }
            cur.execute(
                """
                UPDATE company_modules SET settings=%s::jsonb, updated_at=now()
                WHERE company_code=%s AND module_key=%s
                """,
                (json.dumps(settings), company, MODULE_KEY),
            )
            conn.commit()


def resolve_department_policy_attention(
    legacy: Any,
    context: dict[str, Any],
    *,
    remove_org_unit_ids: list[str] | None = None,
    replace_org_unit_ids: list[dict[str, str]] | None = None,
    reason: str,
) -> dict[str, Any]:
    """HR resolves archived/ambiguous department references without silent name remap."""
    company = _company(context.get("company_code"))
    if not str(reason or "").strip():
        raise legacy.HTTPException(status_code=422, detail={"error": "audit_reason_required"})
    policy = get_company_app_access_policy(legacy, company, migrate_names=False, persist_migration=False)
    current_ids = list(policy.get("selected_department_org_unit_ids") or [])
    labels = dict(policy.get("selected_department_org_unit_labels") or {})
    remove = {str(i).strip() for i in (remove_org_unit_ids or []) if str(i).strip()}
    replacements = replace_org_unit_ids or []
    for item in replacements:
        src = str((item or {}).get("from") or (item or {}).get("from_org_unit_id") or "").strip()
        dst = str((item or {}).get("to") or (item or {}).get("to_org_unit_id") or "").strip()
        if src and dst:
            current_ids = [dst if i == src else i for i in current_ids]
            if src in labels and dst not in labels:
                labels[dst] = labels.get(src) or dst
            remove.add(src)
    next_ids = sorted({i for i in current_ids if i not in remove})
    # Preserve historical labels for removed IDs in audit only.
    historical = {k: v for k, v in labels.items() if k in remove}
    saved = set_company_app_access_policy(
        legacy,
        context,
        ux_mode=UX_DEPARTMENTS,
        selected_department_org_unit_ids=next_ids,
        sync_invites=False,
        source="setup_console",
        allow_module_toggle=False,
        clear_attention=True,
    )
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_access_policy_attention_resolved",
            summary="Resolved Employee App department policy attention.",
            target_type="company",
            target=company,
            details={
                "reason": reason,
                "removed": sorted(remove),
                "replacements": replacements,
                "historical_labels": historical,
                "next_ids": next_ids,
            },
        )
    except Exception:
        logger.warning("attention resolve audit failed", exc_info=True)
    return {"ok": True, "policy": saved.get("policy"), "removed": sorted(remove), "historical_labels": historical}


def preview_access_policy_drilldown(
    legacy: Any,
    company_code: str,
    *,
    ux_mode: str,
    bucket: str,
    selected_departments: list[str] | None = None,
    selected_department_org_unit_ids: list[str] | None = None,
    selected_employee_keys: list[str] | None = None,
    q: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paged drill-down for preview buckets (gain/lose/unchanged). Counts stay in preview."""
    company = _company(company_code)
    bucket_n = str(bucket or "gain").strip().lower()
    if bucket_n not in {"gain", "lose", "unchanged"}:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_bucket"})
    limit_n = max(1, min(int(limit or 50), 100))
    offset_n = max(0, int(offset or 0))
    query = str(q or "").strip().lower()

    proposed = build_proposed_policy(
        legacy,
        company,
        ux_mode=ux_mode,
        selected_departments=selected_departments,
        selected_department_org_unit_ids=selected_department_org_unit_ids,
        selected_employee_keys=selected_employee_keys,
    )
    rows = _list_active_employees(legacy, company)
    matched: list[dict[str, Any]] = []
    for emp in rows:
        current = bool(emp.get("app_access_enabled"))
        desired = employee_desired_by_policy(proposed, emp)
        if desired and not current:
            b = "gain"
        elif current and not desired:
            b = "lose"
        else:
            b = "unchanged"
        if b != bucket_n:
            continue
        if query:
            blob = " ".join(
                [
                    str(emp.get("name") or ""),
                    str(emp.get("employee_key") or ""),
                    str(emp.get("department") or ""),
                    str(emp.get("phone") or ""),
                ]
            ).lower()
            if query not in blob:
                continue
        matched.append(
            {
                "employee_key": emp.get("employee_key"),
                "name": emp.get("name"),
                "department": emp.get("department"),
                "department_org_unit_id": emp.get("department_org_unit_id"),
                "app_access_enabled": current,
                "desired": desired,
                "reason": _inclusion_reason(proposed, emp, desired=desired, current=current),
            }
        )
    total = len(matched)
    page = matched[offset_n : offset_n + limit_n]
    return {
        "ok": True,
        "bucket": bucket_n,
        "total_count": total,
        "employees": page,
        "limit": limit_n,
        "offset": offset_n,
        "has_more": offset_n + len(page) < total,
        "next_offset": offset_n + len(page) if offset_n + len(page) < total else None,
    }


def measure_access_scale(
    legacy: Any,
    company_code: str,
    *,
    synthetic_sizes: list[int] | None = None,
) -> dict[str, Any]:
    """Measure picker/preview/matcher costs for qualification (synthetic + live)."""
    import time

    company = _company(company_code)
    sizes = synthetic_sizes or [100, 1000, 10000]
    live: dict[str, Any] = {}
    t0 = time.perf_counter()
    search = search_employees_for_access(legacy, company, q="", limit=50, offset=0)
    live["search_page_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    live["search_page_rows"] = len(search.get("employees") or [])
    live["search_total_count"] = search.get("total_count")
    t1 = time.perf_counter()
    preview = preview_access_policy_impact(legacy, company, ux_mode=UX_EVERYONE)
    live["preview_everyone_ms"] = round((time.perf_counter() - t1) * 1000, 2)
    live["preview_active_employees"] = (
        int(preview.get("will_gain_access") or 0)
        + int(preview.get("will_lose_access") or 0)
        + int(preview.get("unchanged") or 0)
    )

    synthetic: list[dict[str, Any]] = []
    policy = {
        "module_enabled": True,
        "ux_mode": UX_DEPARTMENTS,
        "access_mode": MODE_SELECTED,
        "selected_department_org_unit_ids": ["unit-a", "unit-b"],
        "selected_departments": [],
        "selected_employee_keys": [],
        "policy_attention": {"needs_attention": False},
    }
    for n in sizes:
        emps = [
            {
                "employee_key": f"P2C-{i}",
                "employment_status": "active",
                "app_access_enabled": i % 3 == 0,
                "department_org_unit_id": "unit-a" if i % 2 == 0 else "unit-c",
                "profile": {"department": "Sales"},
            }
            for i in range(n)
        ]
        t2 = time.perf_counter()
        gain = lose = unchanged = 0
        for emp in emps:
            desired = employee_desired_by_policy(policy, emp)
            current = bool(emp.get("app_access_enabled"))
            if desired and not current:
                gain += 1
            elif current and not desired:
                lose += 1
            else:
                unchanged += 1
        ms = round((time.perf_counter() - t2) * 1000, 2)
        synthetic.append(
            {
                "n": n,
                "matcher_ms": ms,
                "gain": gain,
                "lose": lose,
                "unchanged": unchanged,
                "loads_full_roster_client_side": False,
            }
        )

    return {
        "ok": True,
        "phase": PHASE_2C,
        "live": live,
        "synthetic_matcher": synthetic,
        "notes": [
            "Employee picker is server-paged (max 100/page) — UI never loads full roster.",
            "Preview uses one batch SQL join for org-unit IDs (no per-employee assignment fetches).",
            "Apply uses batch UPDATE for flags.",
        ],
    }
