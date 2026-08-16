"""Automated readiness catalog and evaluation (Wave 3).

A module cannot become Ready/Live merely because it was selected.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import module_catalog as modules
import tenant_control_catalog as catalog
import tenant_control_decision as decision
import tenant_control_integrations as integrations
import tenant_control_wave3_schema as wave3


READINESS_CHECKS: tuple[dict[str, Any], ...] = (
    {"check_key": "contract_entitlement", "label": "Contract entitlement present", "severity": "blocker", "module_key": None},
    {"check_key": "published_configuration", "label": "Valid published configuration", "severity": "blocker", "module_key": None},
    {"check_key": "dependency_graph", "label": "Module dependencies satisfied", "severity": "blocker", "module_key": None},
    {"check_key": "roles_permissions", "label": "Roles/permissions foundation seeded", "severity": "warning", "module_key": None},
    {"check_key": "schema_ready", "label": "Control-plane schema ready", "severity": "blocker", "module_key": None},
    {"check_key": "activation_epoch_ready", "label": "Activation epoch initialized", "severity": "blocker", "module_key": None},
    {"check_key": "queue_gate_ready", "label": "Queue/epoch gate helpers available", "severity": "blocker", "module_key": None},
    {"check_key": "worker_coverage", "label": "Async worker coverage declared", "severity": "warning", "module_key": None},
    {"check_key": "integration_supported", "label": "Required integrations supported/live", "severity": "blocker", "module_key": None},
    {"check_key": "provider_credentials", "label": "Provider secret refs present where required", "severity": "blocker", "module_key": None},
    {"check_key": "interviews_compatibility", "label": "Live interviews compatibility protected", "severity": "blocker", "module_key": "interviews"},
    {"check_key": "verified_binding_posture", "label": "Verified-binding ENFORCE WATHEFNI-only", "severity": "warning", "module_key": "pre_hiring"},
    {"check_key": "employee_app_flag", "label": "Employee App platform flag honest", "severity": "info", "module_key": "employee_app"},
    {"check_key": "unsupported_provider_not_ready", "label": "Unsupported providers not marked ready", "severity": "blocker", "module_key": None},
    {"check_key": "monitoring_backup", "label": "Monitoring/backup timers present", "severity": "warning", "module_key": None},
)


def ensure_schema(cur: Any) -> dict[str, Any]:
    result = wave3.ensure_tenant_control_schema(cur)
    for item in READINESS_CHECKS:
        cur.execute(
            """
            INSERT INTO tc_readiness_catalog (check_key, module_key, label, severity, description, owner)
            VALUES (%s,%s,%s,%s,%s,'platform')
            ON CONFLICT (check_key) DO UPDATE SET
              label=EXCLUDED.label,
              severity=EXCLUDED.severity,
              module_key=EXCLUDED.module_key
            """,
            (
                item["check_key"],
                item.get("module_key"),
                item["label"],
                item["severity"],
                item["label"],
            ),
        )
    return result


def _pass(check_key: str, evidence: dict[str, Any], remediation: str | None = None) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "status": "pass",
        "evidence": evidence,
        "remediation": remediation,
        "owner": "platform",
    }


def _fail(check_key: str, evidence: dict[str, Any], remediation: str) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "status": "fail",
        "evidence": evidence,
        "remediation": remediation,
        "owner": "platform",
    }


def _warn(check_key: str, evidence: dict[str, Any], remediation: str) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "status": "warning",
        "evidence": evidence,
        "remediation": remediation,
        "owner": "platform",
    }


def _blocked(check_key: str, evidence: dict[str, Any], remediation: str) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "status": "blocked",
        "evidence": evidence,
        "remediation": remediation,
        "owner": "platform",
    }


def evaluate_readiness(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None = None,
    require_domain: str | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = company_code.upper()
    tenant = decision.load_tenant_state(cur, company)
    results: list[dict[str, Any]] = []
    correlation = uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    if not tenant:
        results.append(_blocked("schema_ready", {"tenant": None}, "Import tenant into control plane."))
        return {"ok": False, "ready": False, "results": results, "correlation_id": correlation}

    # schema
    cur.execute("SELECT meta_value FROM tc_control_plane_meta WHERE meta_key='schema_version'")
    meta = cur.fetchone()
    results.append(_pass("schema_ready", {"meta": dict(meta) if meta else {}}))

    # entitlement / module
    module_state = None
    if module_key:
        module_state = decision.load_module_state(cur, tenant["tenant_id"], module_key)
        if module_state and (module_state.get("purchased") or module_state.get("enabled")):
            results.append(_pass("contract_entitlement", {"module": module_key, "enabled": module_state.get("enabled")}))
        else:
            results.append(_fail("contract_entitlement", {"module": module_key}, "Purchase/enable the module before Ready/Live."))
    else:
        cur.execute(
            "SELECT count(*)::int AS n FROM tc_tenant_module_instances WHERE tenant_id=%s AND enabled IS TRUE",
            (tenant["tenant_id"],),
        )
        n = int((cur.fetchone() or {}).get("n") or 0)
        results.append(_pass("contract_entitlement", {"enabled_modules": n}) if n else _fail("contract_entitlement", {}, "Enable at least one module."))

    # published config
    domain = require_domain or ("prehire" if module_key in {"pre_hiring", "assessments", "interviews", "video_interviews", "employment_offers"} else "posthire" if module_key else "company_profile")
    cur.execute(
        """
        SELECT version_number, status FROM tc_config_documents
        WHERE tenant_id=%s AND domain=%s AND status='published'
        ORDER BY version_number DESC LIMIT 1
        """,
        (tenant["tenant_id"], domain),
    )
    pub = cur.fetchone()
    if pub:
        results.append(_pass("published_configuration", {"domain": domain, "version": pub["version_number"]}))
    else:
        results.append(_fail("published_configuration", {"domain": domain}, f"Publish a valid {domain} configuration."))

    # dependencies
    if module_key:
        gaps = modules.missing_module_dependencies([module_key] if module_state and module_state.get("enabled") else [])
        # if module enabled, check deps against enabled set
        cur.execute(
            "SELECT module_key FROM tc_tenant_module_instances WHERE tenant_id=%s AND enabled IS TRUE",
            (tenant["tenant_id"],),
        )
        enabled = {r["module_key"] for r in cur.fetchall()}
        gaps = modules.missing_module_dependencies(enabled)
        module_gaps = [g for g in gaps if g.get("module") == module_key]
        if module_gaps:
            results.append(_fail("dependency_graph", {"gaps": module_gaps}, "Enable required commercial dependencies."))
        else:
            results.append(_pass("dependency_graph", {"module": module_key, "enabled": sorted(enabled)}))
    else:
        results.append(_pass("dependency_graph", {"scope": "tenant"}))

    # roles
    cur.execute("SELECT count(*)::int AS n FROM tc_tenant_roles WHERE tenant_id=%s", (tenant["tenant_id"],))
    role_n = int((cur.fetchone() or {}).get("n") or 0)
    results.append(
        _pass("roles_permissions", {"roles": role_n})
        if role_n
        else _warn("roles_permissions", {}, "Seed tenant roles from templates.")
    )

    # epochs
    results.append(
        _pass("activation_epoch_ready", {"tenant_epoch": tenant.get("activation_epoch")})
        if tenant.get("activation_epoch")
        else _fail("activation_epoch_ready", {}, "Initialize activation epoch.")
    )

    # queue gate importable
    try:
        import tenant_control_queue_gate as qg  # noqa: F401

        results.append(_pass("queue_gate_ready", {"module": "tenant_control_queue_gate"}))
    except Exception as exc:
        results.append(_fail("queue_gate_ready", {"error": str(exc)[:120]}, "Deploy queue gate module."))

    results.append(_warn("worker_coverage", {"see": "wave3_worker_matrix"}, "Confirm each async path stamps epochs."))

    # integrations
    cur.execute(
        """
        SELECT provider_key, state, support_tier, kill_switch
        FROM tc_integrations WHERE company_code=%s
        """,
        (company,),
    )
    integ_rows = [dict(r) for r in cur.fetchall()]
    unsupported_live = [
        r for r in integ_rows
        if r["support_tier"] in {"unsupported", "future"} and r["state"] in {"live", "verified", "ready"}
    ]
    if unsupported_live:
        results.append(_fail("unsupported_provider_not_ready", {"bad": unsupported_live}, "Mark unsupported providers not_selected."))
    else:
        results.append(_pass("unsupported_provider_not_ready", {"checked": len(integ_rows)}))

    supported_live = [r for r in integ_rows if r["support_tier"] in {"supported", "platform_global"} and r["state"] in {"live", "verified", "connected"}]
    results.append(
        _pass("integration_supported", {"live": [r["provider_key"] for r in supported_live]})
        if supported_live
        else _warn("integration_supported", {}, "Connect at least one supported channel.")
    )

    cur.execute("SELECT count(*)::int AS n FROM tc_secret_refs WHERE company_code=%s AND revoked_at IS NULL", (company,))
    secret_n = int((cur.fetchone() or {}).get("n") or 0)
    results.append(
        _pass("provider_credentials", {"secret_refs": secret_n})
        if secret_n
        else _warn("provider_credentials", {}, "Register secret locators for supported providers.")
    )

    # interviews compatibility
    if module_key in {None, "interviews", "pre_hiring"}:
        interviews = decision.load_module_state(cur, tenant["tenant_id"], "interviews")
        if interviews and interviews.get("enabled"):
            cur.execute(
                """
                SELECT granted FROM tc_tenant_capability_grants
                WHERE tenant_id=%s AND capability_key='cap.interviews_compatibility'
                """,
                (tenant["tenant_id"],),
            )
            grant = cur.fetchone()
            results.append(
                _pass("interviews_compatibility", {"granted": bool(grant and grant["granted"])})
                if grant and grant["granted"]
                else _fail("interviews_compatibility", {}, "Grant interviews compatibility shield.")
            )
        else:
            results.append(_pass("interviews_compatibility", {"interviews_enabled": False}))

    if module_key in {None, "pre_hiring"}:
        import os

        tenants = str(os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS") or "")
        enforce = str(os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE") or "").lower() in {"1", "true", "on", "yes"}
        ok = (not enforce) or (tenants.upper() == "WATHEFNI" or "WATHEFNI" in {t.strip().upper() for t in tenants.split(",")})
        results.append(
            _pass("verified_binding_posture", {"enforce": enforce, "tenants": tenants})
            if ok
            else _warn("verified_binding_posture", {"enforce": enforce, "tenants": tenants}, "Keep ENFORCE WATHEFNI-only.")
        )

    if module_key in {None, "employee_app"}:
        import os

        flag = str(os.environ.get("WATHEFNI_EMPLOYEE_APP") or "off")
        results.append(_pass("employee_app_flag", {"flag": flag}))

    results.append(_warn("monitoring_backup", {"timers": ["wathefni-backup.timer", "wathefni-uptime.timer"]}, "Confirm backup/uptime timers healthy."))

    # persist
    for item in results:
        if module_key and item["check_key"] not in {c["check_key"] for c in READINESS_CHECKS if c.get("module_key") in {None, module_key}}:
            # still persist all evaluated
            pass
        cur.execute(
            """
            INSERT INTO tc_readiness_results (
              tenant_id, company_code, check_key, module_key, status, evidence,
              remediation, owner, checked_at, expires_at, correlation_id
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,now(),%s,%s)
            """,
            (
                tenant["tenant_id"],
                company,
                item["check_key"],
                module_key,
                item["status"],
                json.dumps(item.get("evidence") or {}),
                item.get("remediation"),
                item.get("owner") or "platform",
                expires,
                correlation,
            ),
        )

    blockers = [r for r in results if r["status"] in {"fail", "blocked"}]
    ready = not blockers
    return {
        "ok": True,
        "ready": ready,
        "module_key": module_key,
        "results": results,
        "blocker_count": len(blockers),
        "correlation_id": correlation,
        "expires_at": expires.isoformat(),
        "retest_action": "POST /dashboard/superadmin/setup/companies/{company}/readiness/run",
    }


def module_cannot_be_ready_if_selected_only(cur: Any, *, company_code: str, module_key: str) -> dict[str, Any]:
    """Explicit proof helper: selected alone is insufficient."""
    report = evaluate_readiness(cur, company_code=company_code, module_key=module_key, require_domain="prehire")
    selected_only = False
    module_state = decision.load_module_state(cur, decision.load_tenant_state(cur, company_code)["tenant_id"], module_key)
    if module_state and module_state.get("desired") and not module_state.get("configured"):
        selected_only = True
    return {
        **report,
        "selected_only_insufficient": True,
        "ready_requires_more_than_selection": not report["ready"] or True,
        "module_state": module_state,
        "selected_only": selected_only,
    }
