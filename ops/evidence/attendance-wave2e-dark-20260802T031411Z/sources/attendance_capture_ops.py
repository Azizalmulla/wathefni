#!/usr/bin/env python3
"""Attendance Wave 2E — dark capture-operations service (synthetic/lab only).

Process-local registry, remediation, and health for HR capture-ops UI/API.
Real device ingest and real punch import remain OFF. Replay into authority
only when synthetic-only gates admit the target.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable

from attendance_capture_compat import run_readonly_compat
from attendance_capture_contract import InMemoryMappingStore
from attendance_capture_health import HealthDashboard
from attendance_capture_pipeline import CapturePipeline
from attendance_capture_registry import ConnectorRegistry
from attendance_capture_remediation import RemediationQueue
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

_LOCK = threading.RLock()
_STATE: dict[str, Any] = {
    "registry": None,
    "mapping": None,
    "queue": None,
    "health": None,
    "pipeline": None,
}


def capture_ops_enabled() -> bool:
    return (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_OPS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def capture_ops_ingest_enabled() -> bool:
    """Hard off for Wave 2E dark — real/lab punch ingest into live device path stays false."""
    return (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def capture_ops_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES") or "WATHEFNI").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def capture_ops_enabled_for_company(company_code: str | None) -> bool:
    if not capture_ops_enabled():
        return False
    allowed = capture_ops_companies()
    if not allowed:
        return True
    return str(company_code or "").strip().upper() in allowed


def _manager_scope_default(company: str, actor: str, employee: str) -> bool:
    # Overridden by app wiring with real manager_scope_allows_employee.
    return True


def reset_capture_ops_for_tests() -> None:
    with _LOCK:
        _STATE["registry"] = ConnectorRegistry()
        _STATE["mapping"] = InMemoryMappingStore()
        _STATE["health"] = HealthDashboard()
        _STATE["pipeline"] = None
        _STATE["queue"] = RemediationQueue(
            mapping=_STATE["mapping"],
            pipeline=None,
            manager_scope_allows=_manager_scope_default,
        )


def _ensure(manager_scope_allows: Callable[[str, str, str], bool] | None = None) -> dict[str, Any]:
    with _LOCK:
        if _STATE["registry"] is None:
            reset_capture_ops_for_tests()
        if manager_scope_allows is not None:
            _STATE["queue"].manager_scope_allows = manager_scope_allows
        return _STATE


def get_registry(**kwargs: Any) -> ConnectorRegistry:
    return _ensure(**kwargs)["registry"]


def get_queue(**kwargs: Any) -> RemediationQueue:
    return _ensure(**kwargs)["queue"]


def get_health(**kwargs: Any) -> HealthDashboard:
    return _ensure(**kwargs)["health"]


def get_mapping(**kwargs: Any) -> InMemoryMappingStore:
    return _ensure(**kwargs)["mapping"]


def bind_pipeline(pipeline: CapturePipeline | None) -> None:
    with _LOCK:
        st = _ensure()
        st["pipeline"] = pipeline
        st["queue"].pipeline = pipeline


def list_connectors(company_code: str) -> list[dict[str, Any]]:
    reg = get_registry()
    company = company_code.upper()
    out = []
    for c in reg.connectors.values():
        if c.company_code != company:
            continue
        d = c.public_dict()
        d["secrets"] = REDACTED
        site = reg.sites.get(c.site_id)
        device = reg.devices.get(c.device_id) if c.device_id else None
        d["site_name"] = site.name if site else None
        d["terminal_sn"] = device.terminal_sn if device else None
        # merge health view if present
        views = {v["connector_id"]: v for v in get_health().list_company(company)}
        d["health"] = views.get(c.connector_id) or {
            "status": "offline" if c.status == "revoked" else "offline",
            "alerts": ["connector_offline"] if c.status != "revoked" else [],
        }
        if c.status == "revoked":
            d["health"] = {**(d["health"] or {}), "status": "revoked"}
        out.append(d)
    return out


def list_sites(company_code: str) -> list[dict[str, Any]]:
    reg = get_registry()
    company = company_code.upper()
    return [
        {
            "site_id": s.site_id,
            "company_code": s.company_code,
            "name": s.name,
            "timezone": s.timezone,
            "active": s.active,
        }
        for s in reg.sites.values()
        if s.company_code == company
    ]


def upsert_health_from_agent(
    *,
    connector_id: str,
    company_code: str,
    agent_health: dict[str, Any],
) -> dict[str, Any]:
    reg = get_registry()
    c = reg.connectors.get(connector_id)
    if not c or c.company_code != company_code.upper():
        return {"ok": False, "error": "connector_not_found"}
    q = get_queue()
    open_n = len([i for i in q.list_open(company_code) if i.get("connector_id") == connector_id])
    try:
        quarantined = len(get_mapping().list_open_quarantine(company_code))
    except Exception:  # noqa: BLE001
        quarantined = 0
    view = get_health().upsert_from_agent(
        connector_id=connector_id,
        company_code=company_code,
        site_id=c.site_id,
        agent_health=agent_health,
        quarantined_events=quarantined,
        open_remediation=open_n,
        revoked=c.status == "revoked",
    )
    # enqueue lag/offline alerts (idempotent)
    alerts = view.alerts
    if "connector_offline" in alerts:
        q.enqueue(
            company_code=company_code,
            kind="connector_offline",
            connector_id=connector_id,
            payload={"status": "offline", "last_error": view.last_error},
            idempotency_key=f"offline:{connector_id}",
        )
    if "connector_lag_critical" in alerts or "connector_lag_warning" in alerts:
        q.enqueue(
            company_code=company_code,
            kind="connector_lag",
            connector_id=connector_id,
            payload={"lag_seconds": view.lag_seconds},
            idempotency_key=f"lag:{connector_id}:{int(view.lag_seconds or 0)//300}",
        )
    return {"ok": True, "health": view.to_dict()}


def overview(company_code: str) -> dict[str, Any]:
    company = company_code.upper()
    connectors = list_connectors(company)
    queue = get_queue().list_open(company)
    excluded = get_queue().payroll_excluded_open(company)
    by_kind: dict[str, int] = {}
    for item in queue:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    health_rows = get_health().list_company(company)
    return {
        "ok": True,
        "company_code": company,
        "capture_ops_enabled": capture_ops_enabled_for_company(company),
        "ingest_enabled": capture_ops_ingest_enabled(),
        "sites": list_sites(company),
        "connectors": connectors,
        "health": health_rows,
        "health_schema": get_health().contract_schema(),
        "remediation_open": queue,
        "payroll_excluded": excluded,
        "counts": {
            "sites": len(list_sites(company)),
            "connectors": len(connectors),
            "open_remediation": len(queue),
            "payroll_excluded": len(excluded),
            "by_kind": by_kind,
            "online": sum(1 for h in health_rows if h.get("status") == "online"),
            "offline": sum(1 for h in health_rows if h.get("status") == "offline"),
            "degraded": sum(1 for h in health_rows if h.get("status") == "degraded"),
        },
        "flags": {
            "real_device_ingest": False,
            "qr_gps_kiosk": False,
            "synthetic_only_authority": (os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY") or "").lower()
            in {"1", "true", "yes", "on"},
            "import_enabled": (os.environ.get("WATHEFNI_ATTENDANCE_IMPORT") or "").lower()
            in {"1", "true", "yes", "on"},
        },
    }


def safe_public(result: dict[str, Any]) -> dict[str, Any]:
    try:
        return redact_mapping(result)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": safe_error(exc)}


def run_compat_probe(
    *,
    company_code: str,
    base_url: str,
    username: str | None = None,
    password: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    if capture_ops_ingest_enabled():
        return {"ok": False, "error": "compat_refuses_when_ingest_on"}
    report = run_readonly_compat(
        company_code=company_code,
        base_url=base_url,
        username=username,
        password=password,
        token=token,
        sample_limit=5,
        connector_id="compat-readonly",
    )
    report["ingest"] = False
    return safe_public(report)
