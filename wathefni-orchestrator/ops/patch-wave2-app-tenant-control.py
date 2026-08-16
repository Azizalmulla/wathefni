#!/usr/bin/env python3
"""Patch production app.py for Wave 2 decision hooks (idempotent)."""

from __future__ import annotations

import py_compile
from pathlib import Path

path = Path("/opt/wathefni/orchestrator/app.py")
text = path.read_text()
orig = text

# 1) Expand imports after tenant_control_service import
if "import tenant_control_decision as _tenant_decision" not in text:
    needle = "import tenant_control_service as _tenant_control  # noqa: E402\n"
    if needle not in text:
        raise SystemExit("tenant_control_service import missing — apply Wave 1 patch first")
    text = text.replace(
        needle,
        needle
        + "import tenant_control_decision as _tenant_decision  # noqa: E402\n"
        + "import tenant_control_surfaces as _tenant_surfaces  # noqa: E402\n"
        + "import tenant_control_lifecycle as _tenant_lifecycle  # noqa: E402\n",
        1,
    )

# 2) Replace company_has_module
old_has = '''def company_has_module(company_code: str | None, module_key: str) -> bool:
    module = normalize_module_key(module_key)
    modules = configured_company_modules(company_code)
    return module in modules
'''
new_has = '''def company_has_module(company_code: str | None, module_key: str) -> bool:
    module = normalize_module_key(module_key)
    modules = configured_company_modules(company_code)
    legacy_allow = module in modules
    company = (company_code or "WATHEFNI").upper()
    # Wave 2: shadow-observe; authoritative only for allowlisted canary capabilities.
    if _tenant_decision.decision_enabled():
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    result = _tenant_surfaces.observe_or_enforce(
                        cur,
                        company_code=company,
                        surface="module_check",
                        module_key=module,
                        legacy_allow=legacy_allow,
                        record_block=False,
                    )
                if result.mode == "authoritative":
                    conn.commit()
                    return bool(result.allow)
                conn.rollback()
        except Exception:
            pass
    return legacy_allow
'''
if "surface=\"module_check\"" not in text and "surface='module_check'" not in text:
    if old_has not in text:
        raise SystemExit("company_has_module block not found")
    text = text.replace(old_has, new_has, 1)

# 3) effective_company_modules
old_eff = '''def effective_company_modules(company_code: str | None) -> set[str]:
    """Configured tenant entitlements that are currently usable platform-wide."""
    return {
        module
        for module in configured_company_modules(company_code)
        if module in MODULE_BY_KEY and module_platform_available(module)
    }
'''
new_eff = '''def effective_company_modules(company_code: str | None) -> set[str]:
    """Configured tenant entitlements that are currently usable platform-wide."""
    company = (company_code or "WATHEFNI").upper()
    base = {
        module
        for module in configured_company_modules(company_code)
        if module in MODULE_BY_KEY and module_platform_available(module)
    }
    # Wave 2: drop modules that are authoritatively denied (canary pause etc.).
    if not _tenant_decision.decision_enabled():
        return base
    filtered: set[str] = set()
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                for module in sorted(base):
                    result = _tenant_decision.evaluate_decision(
                        cur,
                        company_code=company,
                        surface="navigation",
                        module_key=module,
                        legacy_allow=True,
                        persist=False,
                    )
                    if result.mode == "authoritative" and not result.detail.get("canonical_allow", True):
                        continue
                    if result.mode == "authoritative" and not result.allow:
                        continue
                    filtered.add(module)
            conn.rollback()
    except Exception:
        return base
    return filtered
'''
if "drop modules that are authoritatively denied" not in text:
    if old_eff not in text:
        raise SystemExit("effective_company_modules block not found")
    text = text.replace(old_eff, new_eff, 1)

# 4) set_company_setting orphan guard
old_set = '''def set_company_setting(company_code: str | None, key: str, value: Any) -> None:
    """Merge a single key into company_settings.settings (idempotent upsert)."""
    company = (company_code or "WATHEFNI").upper()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_settings (company_code, settings)
                VALUES (%s, %s)
                ON CONFLICT (company_code) DO UPDATE
                  SET settings = company_settings.settings || EXCLUDED.settings,
                      updated_at = now()
                """,
                (company, Json({key: value})),
            )
        conn.commit()
'''
new_set = '''def set_company_setting(company_code: str | None, key: str, value: Any) -> None:
    """Merge a single key into company_settings.settings (idempotent upsert).

    Wave 2 integrity: refuse creating settings rows for unknown companies so new
    orphan company_settings cannot be introduced. Existing orphans are retained.
    """
    company = (company_code or "WATHEFNI").upper()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM companies WHERE company_code=%s LIMIT 1", (company,))
            if not cur.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "company_not_found",
                        "message": "Cannot write company settings for an unknown company.",
                        "company_code": company,
                    },
                )
            cur.execute(
                """
                INSERT INTO company_settings (company_code, settings)
                VALUES (%s, %s)
                ON CONFLICT (company_code) DO UPDATE
                  SET settings = company_settings.settings || EXCLUDED.settings,
                      updated_at = now()
                """,
                (company, Json({key: value})),
            )
        conn.commit()
'''
if "Cannot write company settings for an unknown company." not in text:
    if old_set not in text:
        raise SystemExit("set_company_setting block not found")
    text = text.replace(old_set, new_set, 1)

# 5) require_entitlement wave2 observe — insert before permission check
marker = '''    if permission and permission not in context_permissions(context, role_key):
        raise entitlement_denied(
            status_code=403,
            error="permission_denied",
            message="You do not have permission to do this action.",
            company_code=company,
            module_key=module,
            permission=permission,
            role=role_key,
        )

    return {**context, "company_code": company, "actor_user_id": actor_user_id, "actor_role": role_key}
'''
insert = '''    # Wave 2 surface observation for APIs (shadow; canary may authoritative-deny).
    if module and _tenant_decision.decision_enabled():
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    result = _tenant_surfaces.observe_or_enforce(
                        cur,
                        company_code=company,
                        surface="apis",
                        module_key=module,
                        legacy_allow=True,
                        actor_permission_ok=True,
                        work_kind="api_entitlement",
                    )
                    conn.commit()
                    if result.mode == "authoritative" and not result.allow:
                        raise entitlement_denied(
                            status_code=403,
                            error=result.reason_code or "module_disabled",
                            message=result.remediation or "This capability is not available right now.",
                            company_code=company,
                            module_key=module,
                            permission=permission,
                            role=role_key,
                        )
        except HTTPException:
            raise
        except Exception:
            pass

    if permission and permission not in context_permissions(context, role_key):
        raise entitlement_denied(
            status_code=403,
            error="permission_denied",
            message="You do not have permission to do this action.",
            company_code=company,
            module_key=module,
            permission=permission,
            role=role_key,
        )

    return {**context, "company_code": company, "actor_user_id": actor_user_id, "actor_role": role_key}
'''
if "Wave 2 surface observation for APIs" not in text:
    # Only replace inside require_entitlement
    fn = text.find("def require_entitlement")
    if fn < 0:
        raise SystemExit("require_entitlement not found")
    idx = text.find(marker, fn)
    if idx < 0:
        raise SystemExit("require_entitlement permission marker not found")
    text = text[:idx] + insert + text[idx + len(marker) :]

# 6) require_active_company
old_active = '''def require_active_company(company_code: str | None) -> str:
    company = str(company_code or "").strip().upper()
    status = company_lifecycle_status(company)
    if status != "active":
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"company_{status}",
                "message": "This company workspace is not active. Contact the Wathefni platform operator.",
                "company_code": company,
                "company_status": status,
            },
        )
    return status
'''
new_active = '''def require_active_company(company_code: str | None) -> str:
    company = str(company_code or "").strip().upper()
    status = company_lifecycle_status(company)
    # Wave 2: also observe control-plane lifecycle (shadow unless canary tenant authority).
    if _tenant_decision.decision_enabled() and _tenant_decision.lifecycle_enforce_enabled():
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    result = _tenant_surfaces.observe_or_enforce(
                        cur,
                        company_code=company,
                        surface="navigation",
                        module_key=None,
                        legacy_allow=(status == "active"),
                        work_kind="company_lifecycle",
                    )
                    conn.commit()
                    if result.mode == "authoritative" and not result.allow:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": result.reason_code or f"company_{status}",
                                "message": result.remediation
                                or "This company workspace is not active. Contact the Wathefni platform operator.",
                                "company_code": company,
                                "company_status": status,
                                "correlation_id": result.audit_correlation_id,
                            },
                        )
        except HTTPException:
            raise
        except Exception:
            pass
    if status != "active":
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"company_{status}",
                "message": "This company workspace is not active. Contact the Wathefni platform operator.",
                "company_code": company,
                "company_status": status,
            },
        )
    return status
'''
if "observe control-plane lifecycle" not in text:
    if old_active not in text:
        raise SystemExit("require_active_company block not found")
    text = text.replace(old_active, new_active, 1)

if text == orig:
    print("no_changes_needed_or_already_patched")
else:
    path.write_text(text)
    print("patched_delta_chars", len(text) - len(orig))

py_compile.compile(str(path), doraise=True)
print("syntax_ok")
print("has_decision_import", "import tenant_control_decision as _tenant_decision" in path.read_text())
print("has_orphan_guard", "Cannot write company settings for an unknown company." in path.read_text())
