#!/usr/bin/env python3
"""Surgically patch production app.py for Wave 1 tenant control foundation."""

from __future__ import annotations

import py_compile
from pathlib import Path

path = Path("/opt/wathefni/orchestrator/app.py")
text = path.read_text()
orig = text

old_import = """from module_catalog import (
    MODULE_BY_KEY,
    MODULE_DISPLAY_NAMES,
    POSTHIRE_MODULES,
    POSTHIRE_PEOPLE_MODULES,
    SETUP_CONSOLE_MODULES,
    app_surfaces_for_modules,
    apply_legacy_module_implications,
    expand_module_dependencies,
    missing_module_dependencies,
    module_bundles_payload,
    module_catalog_payload,
    normalize_module_key,
)"""
new_import = """from module_catalog import (
    MODULE_BY_KEY,
    MODULE_DISPLAY_NAMES,
    POSTHIRE_MODULES,
    POSTHIRE_PEOPLE_MODULES,
    SETUP_CONSOLE_MODULES,
    app_surfaces_for_modules,
    apply_legacy_module_implications,
    expand_module_dependencies,
    missing_module_dependencies,
    module_bundles_payload,
    module_catalog_payload,
    normalize_module_key,
    protect_setup_module_selection,
)
import tenant_control_service as _tenant_control  # noqa: E402
"""
if "protect_setup_module_selection" not in text:
    if old_import not in text:
        raise SystemExit("module_catalog import block not found")
    text = text.replace(old_import, new_import, 1)
elif "import tenant_control_service as _tenant_control" not in text:
    text = text.replace(
        "protect_setup_module_selection,\n)",
        "protect_setup_module_selection,\n)\nimport tenant_control_service as _tenant_control  # noqa: E402\n",
        1,
    )

old_ensure = """            _interviews.ensure_interview_schema(cur)
            import assessment_service as _assessment_service

            _assessment_service.freeze_current_content_version(
                cur,
                company_code="GLOBAL",
                battery_key=ASSESSMENT_BATTERY_KEY,
            )
        conn.commit()"""
new_ensure = """            _interviews.ensure_interview_schema(cur)
            import assessment_service as _assessment_service

            _assessment_service.freeze_current_content_version(
                cur,
                company_code="GLOBAL",
                battery_key=ASSESSMENT_BATTERY_KEY,
            )
            # Wave 1 additive tenant control-plane tables (shadow/dual-write only).
            if _tenant_control.plane_enabled():
                _tenant_control.ensure_schema(cur)
        conn.commit()"""
if "Wave 1 additive tenant control-plane" not in text:
    if old_ensure not in text:
        raise SystemExit("ensure_schema interview block not found")
    text = text.replace(old_ensure, new_ensure, 1)

old_setup_start = """    requested = sorted(set(requested))
    dependency_gaps = missing_module_dependencies(requested)
    if dependency_gaps:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_module_dependency",
                "message": " ".join(item["message"] for item in dependency_gaps),
                "missing_dependencies": dependency_gaps,
                "suggested_modules": expand_module_dependencies(requested),
            },
        )
"""
new_setup_start = """    requested = sorted(set(requested))
    currently_enabled = sorted(configured_company_modules(company))
    # Priority 0: never let Setup Console bulk-save strip protected live interviews.
    requested = protect_setup_module_selection(requested, currently_enabled)
    dual_write_validation = _tenant_control.validate_module_publish(
        requested,
        currently_enabled=currently_enabled,
    )
    if dual_write_validation.get("blocks_publish"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "commercial_dependency_blocks_publish",
                "message": " ".join(
                    item.get("message") or ""
                    for item in (dual_write_validation.get("commercial_gaps") or [])
                ) or "Commercial dependency missing.",
                "commercial_gaps": dual_write_validation.get("commercial_gaps") or [],
                "module_gaps": dual_write_validation.get("module_gaps") or [],
                "suggested_modules": expand_module_dependencies(requested),
            },
        )
    dependency_gaps = missing_module_dependencies(requested)
    if dependency_gaps:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_module_dependency",
                "message": " ".join(item["message"] for item in dependency_gaps),
                "missing_dependencies": dependency_gaps,
                "suggested_modules": expand_module_dependencies(requested),
            },
        )
"""
if "Priority 0: never let Setup Console" not in text:
    fn = text.find("def setup_console_set_modules")
    if fn < 0:
        raise SystemExit("setup_console_set_modules not found")
    idx = text.find(old_setup_start, fn)
    if idx < 0:
        raise SystemExit("setup start block not found in function")
    text = text[:idx] + new_setup_start + text[idx + len(old_setup_start) :]

old_commit_tail = """            if payroll_defaults is not None:
                cur.execute(
                    \"\"\"
                    INSERT INTO payroll_policies (company_code, settings, updated_at)
                    VALUES (%s,%s,now())
                    ON CONFLICT (company_code) DO NOTHING
                    \"\"\",
                    (company, Json(payroll_defaults)),
                )
        conn.commit()
    record_admin_audit(
        _setup_audit_context(superadmin, company),
        "setup_modules_updated",
        summary=f"Enabled modules for {company}: {', '.join(requested) or 'none'}.",
        target_type="company",
        target=company,
        details={"company_code": company, "modules": requested, **employee_app_invalidated},
    )
    return {
        "ok": True,
        "modules": requested,
        **employee_app_invalidated,
        "readiness": setup_console_company_readiness(company),
    }
"""

new_commit_tail = """            if payroll_defaults is not None:
                cur.execute(
                    \"\"\"
                    INSERT INTO payroll_policies (company_code, settings, updated_at)
                    VALUES (%s,%s,now())
                    ON CONFLICT (company_code) DO NOTHING
                    \"\"\",
                    (company, Json(payroll_defaults)),
                )
            # Additive dual-write into tenant control-plane (shadow; non-authoritative).
            try:
                dual_write_result = _tenant_control.dual_write_module_save(
                    cur,
                    company_code=company,
                    requested_modules=requested,
                    currently_enabled=currently_enabled,
                    actor=str((superadmin or {}).get("email") or (superadmin or {}).get("user_id") or "setup_console"),
                )
                if not dual_write_result.get("ok") and not dual_write_result.get("skipped"):
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "error": dual_write_result.get("error") or "dual_write_failed",
                            "validation": dual_write_result.get("validation") or {},
                        },
                    )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "tenant_control_dual_write_failed",
                        "message": "Module save could not persist control-plane audit state.",
                        "detail": str(exc)[:300],
                    },
                ) from exc
        conn.commit()
    record_admin_audit(
        _setup_audit_context(superadmin, company),
        "setup_modules_updated",
        summary=f"Enabled modules for {company}: {', '.join(requested) or 'none'}.",
        target_type="company",
        target=company,
        details={
            "company_code": company,
            "modules": requested,
            "protected_retained": dual_write_result.get("protected_retained") or dual_write_validation.get("protected_retained") or [],
            "control_plane_version": dual_write_result.get("version_number"),
            **employee_app_invalidated,
        },
    )
    return {
        "ok": True,
        "modules": requested,
        "protected_retained": dual_write_result.get("protected_retained") or dual_write_validation.get("protected_retained") or [],
        "control_plane": {
            "dual_write": (not dual_write_result.get("skipped")),
            "version_number": dual_write_result.get("version_number"),
            "rollback_target": dual_write_result.get("rollback_target"),
        },
        **employee_app_invalidated,
        "readiness": setup_console_company_readiness(company),
    }
"""

if "tenant_control_dual_write_failed" not in text:
    fn = text.find("def setup_console_set_modules")
    idx = text.find(old_commit_tail, fn)
    if idx < 0:
        raise SystemExit("commit tail block not found")
    text = text[:idx] + new_commit_tail + text[idx + len(old_commit_tail) :]
    init_old = """    employee_app_invalidated = {
        "revoked_employee_app_sessions": 0,
        "superseded_employee_app_invites": 0,
    }
    with db_connect() as conn:
"""
    init_new = """    employee_app_invalidated = {
        "revoked_employee_app_sessions": 0,
        "superseded_employee_app_invites": 0,
    }
    dual_write_result: dict[str, Any] = {"ok": True, "skipped": True}
    with db_connect() as conn:
"""
    fn = text.find("def setup_console_set_modules")
    idx = text.find(init_old, fn)
    if idx < 0:
        raise SystemExit("employee_app_invalidated init not found")
    if "dual_write_result: dict[str, Any]" not in text[fn : fn + 8000]:
        text = text[:idx] + init_new + text[idx + len(init_old) :]

if text == orig:
    raise SystemExit("no changes applied")

path.write_text(text)
print("patched_delta_chars", len(text) - len(orig))
print("has_protect", "protect_setup_module_selection" in text)
print("has_dual_write", "tenant_control_dual_write_failed" in text)
print("has_ensure_hook", "Wave 1 additive tenant control-plane" in text)
py_compile.compile(str(path), doraise=True)
print("syntax_ok")
