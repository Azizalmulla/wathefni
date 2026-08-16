#!/usr/bin/env python3
"""Attendance Wave 2E — FastAPI route registration for capture-operations (dark)."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import Body, HTTPException
from pydantic import BaseModel, Field

import attendance_capture_ops as capture_ops
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

# Mutable hooks for in-process canary (TestClient). Production routes leave these None.
CANARY_SKIP_ENTITLEMENT = False


class CaptureSiteCreate(BaseModel):
    name: str
    timezone: str = "Asia/Kuwait"


class CaptureDeviceCreate(BaseModel):
    site_id: str
    terminal_sn: str
    vendor: str = "biotime"


class CaptureConnectorCreate(BaseModel):
    site_id: str
    device_id: str | None = None
    connector_version: str = "wave2e"
    username: str | None = None
    password: str | None = None
    token: str | None = None


class CaptureRotateRequest(BaseModel):
    expected_row_version: int
    username: str | None = None
    password: str | None = None
    token: str | None = None


class CaptureRowVersionRequest(BaseModel):
    expected_row_version: int
    reason: str | None = None


class CaptureHealthUpdate(BaseModel):
    status: str = "ok"
    lag_seconds: float | None = None
    error_count: int = 0
    last_error: str | None = None
    last_sync_at: str | None = None
    checkpoint: str | None = None
    connector_version: str | None = None


class CaptureApproveMapping(BaseModel):
    employee_key: str
    expected_row_version: int
    replay: bool = True
    employee_phone: str | None = None


class CaptureRejectItem(BaseModel):
    expected_row_version: int
    reason: str | None = None
    employee_phone: str | None = None


class CaptureReplayItem(BaseModel):
    expected_row_version: int


class CaptureCompatRequest(BaseModel):
    base_url: str
    username: str | None = None
    password: str | None = None
    token: str | None = None


class CaptureSeedSynthetic(BaseModel):
    tag: str | None = None


def register_attendance_capture_ops_routes(
    app: Any,
    *,
    Depends: Any,
    dashboard_context: Callable,
    require_entitlement: Callable,
    manager_scope_allows_employee: Callable,
    context_manager_allows_employee: Callable | None = None,
    record_admin_audit: Callable,
    digits: Callable,
    json_safe: Callable,
    get_employee: Callable | None = None,
) -> None:
    """Wire dark capture-ops endpoints. Invisible (404) when flag off."""

    def _guard(context: dict[str, Any], *, write: bool) -> str:
        company = str(context.get("company_code") or "").upper()
        if not capture_ops.capture_ops_enabled_for_company(company):
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Not found."})
        if not CANARY_SKIP_ENTITLEMENT:
            require_entitlement(context, "attendance", "attendance.manage" if write else "attendance.read")
        return company

    def _actor_phone(context: dict[str, Any]) -> str:
        return digits(context.get("actor_phone") or context.get("hr_phone") or "") or ""

    def _scope_allows(company: str, actor: str, employee_key: str) -> bool:
        if CANARY_SKIP_ENTITLEMENT:
            return True
        # Remediaton queue passes (company, actor_phone, employee_key).
        # App manager_scope_allows_employee(employee, *, company_code, viewer_phone, ...).
        emp: dict[str, Any] | None
        if get_employee is not None:
            try:
                emp = get_employee(company, employee_key)
            except Exception:  # noqa: BLE001
                emp = None
        else:
            emp = {"employee_key": employee_key, "company_code": company}
        if emp is None:
            return False
        try:
            return bool(
                manager_scope_allows_employee(
                    emp,
                    company_code=company,
                    viewer_phone=actor,
                )
            )
        except TypeError:
            # Fallback if a test double uses the (company, actor, employee_key) shape
            return bool(manager_scope_allows_employee(company, actor, employee_key))

    def _bind_scope() -> None:
        capture_ops.get_queue(manager_scope_allows=_scope_allows)

    @app.get("/dashboard/posthire/attendance/capture-ops")
    def capture_ops_overview(context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=False)
        _bind_scope()
        return json_safe(capture_ops.overview(company))

    @app.get("/dashboard/posthire/attendance/capture-ops/connectors")
    def capture_ops_connectors(context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=False)
        return {"company_code": company, "connectors": json_safe(capture_ops.list_connectors(company))}

    @app.get("/dashboard/posthire/attendance/capture-ops/remediation")
    def capture_ops_remediation(
        kind: str | None = None,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _guard(context, write=False)
        _bind_scope()
        items = capture_ops.get_queue().list_open(company)
        if kind:
            items = [i for i in items if i.get("kind") == kind]
        excluded = capture_ops.get_queue().payroll_excluded_open(company)
        return {
            "company_code": company,
            "items": json_safe(items),
            "payroll_excluded": json_safe(excluded),
        }

    @app.post("/dashboard/posthire/attendance/capture-ops/sites")
    def capture_ops_create_site(body: CaptureSiteCreate, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        site = capture_ops.get_registry().register_site(
            company_code=company, name=body.name.strip(), timezone=body.timezone or "Asia/Kuwait"
        )
        record_admin_audit(
            context,
            "attendance_capture_site_registered",
            summary=f"Registered capture site {site.name}.",
            target_type="company",
            target=company,
            details={"site_id": site.site_id},
        )
        return {"ok": True, "site": json_safe(site.__dict__)}

    @app.post("/dashboard/posthire/attendance/capture-ops/devices")
    def capture_ops_create_device(body: CaptureDeviceCreate, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        result = capture_ops.get_registry().register_device(
            company_code=company,
            site_id=body.site_id,
            terminal_sn=body.terminal_sn.strip(),
            vendor=body.vendor,
            actor_company=company,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=403 if "tenant" in str(result.get("error")) else 422, detail=result)
        record_admin_audit(
            context,
            "attendance_capture_device_registered",
            summary=f"Registered capture device {body.terminal_sn}.",
            target_type="company",
            target=company,
            details={"device_id": (result.get("device") or {}).get("device_id")},
        )
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/connectors")
    def capture_ops_create_connector(body: CaptureConnectorCreate, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        secrets = {}
        if body.username:
            secrets["username"] = body.username
        if body.password:
            secrets["password"] = body.password
        if body.token:
            secrets["token"] = body.token
        result = capture_ops.get_registry().register_connector(
            company_code=company,
            site_id=body.site_id,
            device_id=body.device_id,
            secrets=secrets,
            connector_version=body.connector_version,
            actor_company=company,
            actor_phone=_actor_phone(context),
        )
        if not result.get("ok"):
            raise HTTPException(status_code=403 if "tenant" in str(result.get("error")) else 422, detail=redact_mapping(result))
        result["secrets"] = REDACTED
        record_admin_audit(
            context,
            "attendance_capture_connector_registered",
            summary="Registered attendance connector.",
            target_type="company",
            target=company,
            details={"connector_id": (result.get("connector") or {}).get("connector_id")},
        )
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/connectors/{connector_id}/activate")
    def capture_ops_activate(connector_id: str, body: CaptureRowVersionRequest, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        tenant = capture_ops.get_registry().assert_connector_tenant(connector_id, company)
        if not tenant.get("ok"):
            raise HTTPException(status_code=403, detail=tenant)
        result = capture_ops.get_registry().activate(
            connector_id, expected_row_version=body.expected_row_version, actor_phone=_actor_phone(context)
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 422
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/connectors/{connector_id}/rotate")
    def capture_ops_rotate(connector_id: str, body: CaptureRotateRequest, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        tenant = capture_ops.get_registry().assert_connector_tenant(connector_id, company)
        if not tenant.get("ok"):
            raise HTTPException(status_code=403, detail=tenant)
        secrets = {}
        if body.username:
            secrets["username"] = body.username
        if body.password:
            secrets["password"] = body.password
        if body.token:
            secrets["token"] = body.token
        result = capture_ops.get_registry().rotate_credentials(
            connector_id,
            new_secrets=secrets,
            expected_row_version=body.expected_row_version,
            actor_phone=_actor_phone(context),
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 422
            raise HTTPException(status_code=code, detail=redact_mapping(result))
        result["secrets"] = REDACTED
        recon = capture_ops.get_registry().reconnect_after_rotate(connector_id)
        record_admin_audit(context, "attendance_capture_connector_rotated", summary="Rotated connector credentials.", target_type="connector", target=connector_id, details={})
        return json_safe({"ok": True, "rotate": result, "reconnect": recon})

    @app.post("/dashboard/posthire/attendance/capture-ops/connectors/{connector_id}/revoke")
    def capture_ops_revoke(connector_id: str, body: CaptureRowVersionRequest, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        tenant = capture_ops.get_registry().assert_connector_tenant(connector_id, company)
        if not tenant.get("ok"):
            raise HTTPException(status_code=403, detail=tenant)
        result = capture_ops.get_registry().revoke(
            connector_id,
            expected_row_version=body.expected_row_version,
            actor_phone=_actor_phone(context),
            reason=body.reason,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 422
            raise HTTPException(status_code=code, detail=result)
        capture_ops.get_health().upsert_from_agent(
            connector_id=connector_id,
            company_code=company,
            site_id=(result.get("connector") or {}).get("site_id"),
            agent_health={"status": "offline"},
            revoked=True,
        )
        record_admin_audit(context, "attendance_capture_connector_revoked", summary="Revoked attendance connector.", target_type="connector", target=connector_id, details={"reason": body.reason})
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/connectors/{connector_id}/health")
    def capture_ops_health_update(connector_id: str, body: CaptureHealthUpdate, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        tenant = capture_ops.get_registry().assert_connector_tenant(connector_id, company)
        if not tenant.get("ok"):
            raise HTTPException(status_code=403, detail=tenant)
        result = capture_ops.upsert_health_from_agent(
            connector_id=connector_id,
            company_code=company,
            agent_health={
                "status": body.status,
                "lag_seconds": body.lag_seconds,
                "error_count": body.error_count,
                "last_error": body.last_error,
                "last_sync_at": body.last_sync_at,
                "checkpoint": body.checkpoint,
                "connector_version": body.connector_version,
            },
        )
        if body.status in {"ok", "online"} and (body.lag_seconds or 0) < 60:
            capture_ops.get_health().mark_recovered(connector_id, last_sync_at=body.last_sync_at)
            result = {"ok": True, "health": next((h for h in capture_ops.get_health().list_company(company) if h["connector_id"] == connector_id), None)}
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/remediation/{item_id}/approve-mapping")
    def capture_ops_approve_mapping(item_id: str, body: CaptureApproveMapping, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        _bind_scope()
        # Dark wave: refuse replay when ingest flag off — approve mapping only
        replay = bool(body.replay) and capture_ops.capture_ops_ingest_enabled()
        actor = _actor_phone(context)
        result = capture_ops.get_queue().approve_mapping(
            item_id,
            employee_key=body.employee_key,
            expected_row_version=body.expected_row_version,
            actor_phone=actor,
            actor_company=company,
            actor_is_manager=True,
            employee_phone=body.employee_phone,
            replay=replay,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 403 if "denied" in str(result.get("error")) else 422
            raise HTTPException(status_code=code, detail=result)
        record_admin_audit(
            context,
            "attendance_capture_mapping_approved",
            summary=f"Approved capture mapping to {body.employee_key}.",
            target_type="remediation",
            target=item_id,
            details={"employee_key": body.employee_key, "replay": replay},
        )
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/remediation/{item_id}/reject")
    def capture_ops_reject(item_id: str, body: CaptureRejectItem, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        _bind_scope()
        result = capture_ops.get_queue().reject(
            item_id,
            expected_row_version=body.expected_row_version,
            actor_phone=_actor_phone(context),
            actor_company=company,
            reason=body.reason,
            actor_is_manager=True,
            employee_phone=body.employee_phone,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 403 if "denied" in str(result.get("error")) else 422
            raise HTTPException(status_code=code, detail=result)
        record_admin_audit(context, "attendance_capture_remediation_rejected", summary="Rejected capture remediation item.", target_type="remediation", target=item_id, details={"reason": body.reason})
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/remediation/{item_id}/replay")
    def capture_ops_replay(item_id: str, body: CaptureReplayItem, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        if not capture_ops.capture_ops_ingest_enabled():
            raise HTTPException(
                status_code=403,
                detail={"ok": False, "error": "capture_ingest_off", "message": "Punch ingest remains off in Wave 2E dark mode."},
            )
        _bind_scope()
        result = capture_ops.get_queue().replay_item(
            item_id,
            expected_row_version=body.expected_row_version,
            actor_phone=_actor_phone(context),
            actor_company=company,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 422
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/posthire/attendance/capture-ops/compat")
    def capture_ops_compat(body: CaptureCompatRequest, context: dict[str, Any] = Depends(dashboard_context)):
        company = _guard(context, write=True)
        report = capture_ops.run_compat_probe(
            company_code=company,
            base_url=body.base_url,
            username=body.username,
            password=body.password,
            token=body.token,
        )
        # never echo secrets
        report["secrets"] = REDACTED
        return json_safe(report)

    @app.post("/dashboard/posthire/attendance/capture-ops/seed-synthetic")
    def capture_ops_seed_synthetic(body: CaptureSeedSynthetic = Body(default=CaptureSeedSynthetic()), context: dict[str, Any] = Depends(dashboard_context)):
        """Lab/synthetic seed for dark canary UI — never touches real devices."""
        company = _guard(context, write=True)
        import uuid

        tag = (body.tag or uuid.uuid4().hex[:8]).strip()
        reg = capture_ops.get_registry()
        site = reg.register_site(company_code=company, name=f"Lab Site {tag}")
        dev = reg.register_device(company_code=company, site_id=site.site_id, terminal_sn=f"LAB-SN-{tag}")
        if not dev.get("ok"):
            return json_safe(dev)
        device_id = dev["device"]["device_id"]
        conn = reg.register_connector(
            company_code=company,
            site_id=site.site_id,
            device_id=device_id,
            secrets={"username": "lab", "password": f"lab-{tag}", "token": f"tok-{tag}"},
            connector_version="wave2e-lab",
            actor_phone=_actor_phone(context),
        )
        connector_id = conn["connector"]["connector_id"]
        row_v = conn["connector"]["row_version"]
        act = reg.activate(connector_id, expected_row_version=row_v, actor_phone=_actor_phone(context))
        capture_ops.upsert_health_from_agent(
            connector_id=connector_id,
            company_code=company,
            agent_health={"status": "ok", "lag_seconds": 12, "last_sync_at": None, "error_count": 0},
        )
        q = capture_ops.get_queue()
        unknown = q.enqueue(
            company_code=company,
            kind="unknown_employee",
            connector_id=connector_id,
            device_user_id=f"LABDU-{tag}",
            device_id=f"LAB-SN-{tag}",
            source_event_id=f"biotime:lab-{tag}-1",
            payload={
                "company_code": company,
                "source": "biotime",
                "source_event_id": f"biotime:lab-{tag}-1",
                "device_user_id": f"LABDU-{tag}",
                "punched_at": "2026-08-25T09:05:00+03:00",
                "direction": "in",
                "capture_method": "card",
                "device_id": f"LAB-SN-{tag}",
                "connector_id": connector_id,
            },
            idempotency_key=f"lab-unk-{tag}",
        )
        missing = q.mark_projection_exception(
            company_code=company,
            kind="missing_check_out",
            employee_key=f"{company}-ATTW2E-{tag}",
            work_date="2026-08-25",
            projection={"status": "incomplete", "exception_state": "missing_check_out"},
            connector_id=connector_id,
        )
        amb = q.mark_projection_exception(
            company_code=company,
            kind="ambiguous_punch_order",
            employee_key=f"{company}-ATTW2E-{tag}",
            work_date="2026-08-25",
            projection={"status": "ambiguous", "exception_state": "ambiguous_punch_order"},
            connector_id=connector_id,
        )
        conflict = q.enqueue(
            company_code=company,
            kind="duplicate_conflict",
            connector_id=connector_id,
            payload={"a": 1, "b": 2},
            source_event_id=f"dup-lab-{tag}",
            idempotency_key=f"lab-dup-{tag}",
        )
        record_admin_audit(context, "attendance_capture_synthetic_seeded", summary="Seeded synthetic capture-ops lab data.", target_type="company", target=company, details={"tag": tag})
        return json_safe(
            {
                "ok": True,
                "tag": tag,
                "site": site.__dict__,
                "device": dev.get("device"),
                "connector": act.get("connector") or conn.get("connector"),
                "secrets": REDACTED,
                "remediation": {
                    "unknown": unknown,
                    "missing_check_out": missing,
                    "ambiguous": amb,
                    "conflict": conflict,
                },
                "ingest_enabled": capture_ops.capture_ops_ingest_enabled(),
            }
        )
