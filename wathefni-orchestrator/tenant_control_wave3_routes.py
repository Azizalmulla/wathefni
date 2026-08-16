"""Super Admin Wave 3 configuration / integration / readiness APIs.

Compatible with existing Setup Console; does not redesign the wizard UI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import tenant_control_config as tc_config
import tenant_control_decision as tc_decision
import tenant_control_integrations as tc_integrations
import tenant_control_lifecycle as tc_lifecycle
import tenant_control_readiness as tc_readiness
import tenant_control_roles as tc_roles
import tenant_control_service as tc_wave1


router = APIRouter(prefix="/dashboard/superadmin/setup", tags=["tenant-control-wave3"])


class ConfigDraftRequest(BaseModel):
    domain: str
    config: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ConfigPublishRequest(BaseModel):
    document_id: str


class ConfigRollbackRequest(BaseModel):
    domain: str
    target_version: int


class IntegrationUpsertRequest(BaseModel):
    provider_key: str
    state: str | None = None
    provider_account_ref: str | None = None
    secret_locator: str | None = None
    secret_purpose: str | None = None
    kill_switch: bool | None = None


class IntegrationTestRequest(BaseModel):
    provider_key: str
    test_kind: str = "health"


class ReadinessRunRequest(BaseModel):
    module_key: str | None = None
    domain: str | None = None


def register_wave3_routes(app: Any, *, superadmin_dependency: Any, db_connect: Any) -> None:
    """Attach Wave 3 routes to the FastAPI app using existing auth dependency."""

    def _actor(superadmin: dict[str, Any]) -> str:
        return str((superadmin or {}).get("email") or (superadmin or {}).get("user_id") or "superadmin")

    @router.get("/providers")
    def list_providers(superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        return {"ok": True, "providers": tc_integrations.provider_matrix()}

    @router.get("/companies/{company_code}/config/{domain}")
    def get_config(company_code: str, domain: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        company = company_code.upper()
        with db_connect() as conn:
            with conn.cursor() as cur:
                tc_config.ensure_schema(cur)
                published = tc_config.get_published(cur, company_code=company, domain=domain)
                drafts = tc_config.list_drafts(cur, company_code=company, domain=domain)
            conn.commit()
        return {"ok": True, "company_code": company, "domain": domain, "published": published, "drafts": drafts}

    @router.post("/companies/{company_code}/config/drafts")
    def create_config_draft(
        company_code: str,
        request: ConfigDraftRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        company = company_code.upper()
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_config.create_draft(
                    cur,
                    company_code=company,
                    domain=request.domain,
                    config_json=request.config,
                    actor=_actor(superadmin),
                    idempotency_key=request.idempotency_key,
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/config/drafts/{document_id}/validate")
    def validate_config_draft(
        company_code: str,
        document_id: str,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        _ = company_code
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_config.mark_validated(cur, document_id=document_id, actor=_actor(superadmin))
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/config/publish")
    def publish_config(
        company_code: str,
        request: ConfigPublishRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        _ = company_code
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_config.publish_document(
                    cur,
                    document_id=request.document_id,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/config/rollback")
    def rollback_config(
        company_code: str,
        request: ConfigRollbackRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_config.rollback_domain(
                    cur,
                    company_code=company_code.upper(),
                    domain=request.domain,
                    target_version=request.target_version,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.get("/companies/{company_code}/integrations")
    def list_integrations(company_code: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                tc_integrations.ensure_schema(cur)
                cur.execute(
                    """
                    SELECT integration_id::text AS integration_id, provider_key, channel_key, state,
                           support_tier, supported, kill_switch, last_tested_at, last_verified_at,
                           provider_account_ref IS NOT NULL AS has_account_ref,
                           secret_ref_id IS NOT NULL AS has_secret_ref
                    FROM tc_integrations
                    WHERE company_code=%s
                    ORDER BY provider_key
                    """,
                    (company_code.upper(),),
                )
                rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
        return {"ok": True, "integrations": rows, "providers": tc_integrations.provider_matrix()}

    @router.post("/companies/{company_code}/integrations")
    def upsert_integration(
        company_code: str,
        request: IntegrationUpsertRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                secret_ref_id = None
                if request.secret_locator and request.secret_purpose:
                    secret = tc_integrations.register_secret_ref(
                        cur,
                        company_code=company_code.upper(),
                        provider_key=request.provider_key,
                        purpose=request.secret_purpose,
                        secret_locator=request.secret_locator,
                        actor=_actor(superadmin),
                    )
                    secret_ref_id = secret.get("secret_ref_id")
                result = tc_integrations.upsert_integration(
                    cur,
                    company_code=company_code.upper(),
                    provider_key=request.provider_key,
                    state=request.state,
                    provider_account_ref=request.provider_account_ref,
                    secret_ref_id=secret_ref_id,
                    kill_switch=request.kill_switch,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/integrations/test")
    def test_integration(
        company_code: str,
        request: IntegrationTestRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_integrations.run_integration_test(
                    cur,
                    company_code=company_code.upper(),
                    provider_key=request.provider_key,
                    test_kind=request.test_kind,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok") and result.get("error") == "provider_unsupported":
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/integrations/{provider_key}/pause")
    def pause_integration(
        company_code: str,
        provider_key: str,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_integrations.set_integration_degraded(
                    cur,
                    company_code=company_code.upper(),
                    provider_key=provider_key,
                    actor=_actor(superadmin),
                    reason="operator_pause",
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/integrations/{provider_key}/reconnect")
    def reconnect_integration(
        company_code: str,
        provider_key: str,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_integrations.restore_integration(
                    cur,
                    company_code=company_code.upper(),
                    provider_key=provider_key,
                    actor=_actor(superadmin),
                    state="live",
                )
            conn.commit()
        return result

    @router.get("/companies/{company_code}/readiness")
    def get_readiness(company_code: str, module_key: str | None = None, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_readiness.evaluate_readiness(
                    cur,
                    company_code=company_code.upper(),
                    module_key=module_key,
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/readiness/run")
    def run_readiness(
        company_code: str,
        request: ReadinessRunRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_readiness.evaluate_readiness(
                    cur,
                    company_code=company_code.upper(),
                    module_key=request.module_key,
                    require_domain=request.domain,
                )
            conn.commit()
        return result

    @router.get("/companies/{company_code}/reconstruction")
    def reconstruction(company_code: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                snap = build_reconstruction(cur, company_code=company_code.upper())
            conn.commit()
        return snap

    app.include_router(router)


def build_reconstruction(cur: Any, *, company_code: str) -> dict[str, Any]:
    tc_config.ensure_schema(cur)
    company = company_code.upper()
    tenant = tc_decision.load_tenant_state(cur, company)
    gaps: list[str] = []
    if not tenant:
        gaps.append("tenant_not_imported")
        return {"ok": False, "gaps": gaps}

    cur.execute(
        "SELECT module_key, enabled, purchased, live, paused, activation_epoch FROM tc_tenant_module_instances WHERE tenant_id=%s ORDER BY module_key",
        (tenant["tenant_id"],),
    )
    modules = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT capability_key, granted, grant_mode FROM tc_tenant_capability_grants WHERE tenant_id=%s ORDER BY capability_key",
        (tenant["tenant_id"],),
    )
    caps = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT provider_key, state, support_tier, kill_switch FROM tc_integrations WHERE company_code=%s ORDER BY provider_key",
        (company,),
    )
    integ = [dict(r) for r in cur.fetchall()]
    domains = {}
    for domain in tc_config.DOMAIN_SCHEMAS:
        domains[domain] = tc_config.get_published(cur, company_code=company, domain=domain)
        if domains[domain] is None:
            gaps.append(f"missing_published:{domain}")
    cur.execute("SELECT count(*)::int AS n FROM tc_tenant_roles WHERE tenant_id=%s", (tenant["tenant_id"],))
    roles_n = int((cur.fetchone() or {}).get("n") or 0)
    if roles_n == 0:
        gaps.append("roles_not_seeded")

    import os

    flags = {
        k: os.environ.get(k)
        for k in (
            "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS",
            "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4",
            "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS",
            "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE",
            "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS",
            "WATHEFNI_EMPLOYEE_APP",
            "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS",
            "WATHEFNI_TENANT_CONTROL_PLANE",
        )
    }
    snapshot = {
        "company_code": company,
        "tenant": {
            "lifecycle_status": tenant.get("lifecycle_status"),
            "activation_epoch": tenant.get("activation_epoch"),
            "synthetic": tenant.get("synthetic"),
            "externally_usable": tenant.get("externally_usable"),
        },
        "modules": modules,
        "capabilities": caps,
        "integrations": integ,
        "published_configs": {k: (v.get("version_number") if v else None) for k, v in domains.items()},
        "roles_count": roles_n,
        "technical_flags": flags,
        "backend_only": {
            "candidate_knowledge": True,
            "talent_pool": True,
            "hr_visible_products": ["Candidates"],
        },
        "interviews_compatibility": any(c.get("capability_key") == "cap.interviews_compatibility" and c.get("granted") for c in caps),
        "workers": {
            "delivery_sweep_unit": "wathefni-delivery-sweep.service",
            "delivery_sweep_classification": "required_misconfigured_missing_application_environment",
        },
        "authority": {
            "global_canonical_authority": tc_decision.global_authoritative_enabled(),
            "wave1_authoritative": tc_wave1.authoritative_enabled(),
        },
    }
    score = max(0.0, 1.0 - (len(gaps) * 0.05))
    cur.execute(
        """
        INSERT INTO tc_reconstruction_snapshots (company_code, snapshot_json, completeness_score, gaps)
        VALUES (%s,%s::jsonb,%s,%s::jsonb)
        RETURNING snapshot_id::text AS snapshot_id
        """,
        (company, __import__("json").dumps(snapshot, default=str), score, __import__("json").dumps(gaps)),
    )
    snap_id = (cur.fetchone() or {}).get("snapshot_id")
    return {
        "ok": len(gaps) == 0,
        "snapshot_id": snap_id,
        "completeness_score": score,
        "gaps": gaps,
        "snapshot": snapshot,
    }
