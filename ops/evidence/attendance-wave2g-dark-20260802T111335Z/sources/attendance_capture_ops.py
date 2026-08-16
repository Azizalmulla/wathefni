#!/usr/bin/env python3
"""Attendance capture-operations service (Wave 2E/2F).

Store mode:
  WATHEFNI_ATTENDANCE_CAPTURE_STORE=memory   (default; process-local)
  WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres (Wave 2F durable authority)

Real device ingest remains gated by WATHEFNI_ATTENDANCE_CAPTURE_INGEST.
"""

from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from typing import Any, Callable

from attendance_capture_compat import run_readonly_compat
from attendance_capture_contract import InMemoryMappingStore
from attendance_capture_health import HealthDashboard
from attendance_capture_pipeline import CapturePipeline
from attendance_capture_registry import ConnectorRegistry, SiteRecord
from attendance_capture_remediation import RemediationQueue
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

_LOCK = threading.RLock()
_STATE: dict[str, Any] = {
    "mode": None,
    "registry": None,
    "mapping": None,
    "queue": None,
    "health": None,
    "pipeline": None,
    "pg": None,
}


def capture_ops_enabled() -> bool:
    return (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_OPS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def capture_ops_ingest_enabled() -> bool:
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


def capture_store_mode() -> str:
    raw = (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE") or "memory").strip().lower()
    return "postgres" if raw in {"postgres", "pg", "postgresql"} else "memory"


def _manager_scope_default(company: str, actor: str, employee: str) -> bool:
    return True


class _PgRegistryAdapter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def register_site(self, *, company_code: str, name: str, timezone: str = "Asia/Kuwait") -> SiteRecord:
        row = self.store.register_site(company_code=company_code, name=name, timezone=timezone)
        return SiteRecord(
            site_id=str(row["site_id"]),
            company_code=row["company_code"],
            name=row["name"],
            timezone=row.get("timezone") or "Asia/Kuwait",
            active=bool(row.get("active", True)),
            metadata=row.get("metadata") or {},
        )

    def register_device(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.register_device(**kwargs)

    def register_connector(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.register_connector(**kwargs)

    def activate(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.activate(*a, **k)

    def rotate_credentials(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.rotate_credentials(*a, **k)

    def revoke(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.revoke(*a, **k)

    def reconnect_after_rotate(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.reconnect_after_rotate(*a, **k)

    def assert_connector_tenant(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.assert_connector_tenant(*a, **k)

    def verify_device_ownership(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.verify_device_ownership(**kwargs)

    @property
    def connectors(self) -> dict[str, Any]:
        # sparse view for legacy callers
        rows = {}
        for company in capture_ops_companies() or {"WATHEFNI"}:
            for c in self.store.list_connectors(company):
                rows[c["connector_id"]] = SimpleNamespace(
                    connector_id=c["connector_id"],
                    company_code=c["company_code"],
                    site_id=str(c["site_id"]),
                    device_id=str(c["device_id"]) if c.get("device_id") else None,
                    status=c["status"],
                    row_version=c["row_version"],
                    public_dict=lambda _c=c: {**_c, "secrets": REDACTED},
                )
        return rows

    @property
    def sites(self) -> dict[str, Any]:
        out = {}
        for company in capture_ops_companies() or {"WATHEFNI"}:
            for s in self.store.list_sites(company):
                out[str(s["site_id"])] = SimpleNamespace(**{**s, "site_id": str(s["site_id"])})
        return out

    @property
    def devices(self) -> dict[str, Any]:
        return {}


class _PgQueueAdapter:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.pipeline = None
        self.manager_scope_allows = _manager_scope_default

    def enqueue(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.enqueue_remediation(**kwargs)

    def list_open(self, company_code: str) -> list[dict[str, Any]]:
        return self.store.list_open_remediation(company_code)

    def payroll_excluded_open(self, company_code: str) -> list[dict[str, Any]]:
        return self.store.payroll_excluded_open(company_code)

    def approve_mapping(self, *a: Any, **k: Any) -> dict[str, Any]:
        self.store.manager_scope_allows = self.manager_scope_allows
        self.store.pipeline = self.pipeline
        return self.store.approve_mapping(*a, **k)

    def reject(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self.store.reject(*a, **k)

    def replay_item(self, *a: Any, **k: Any) -> dict[str, Any]:
        self.store.pipeline = self.pipeline
        return self.store.replay_item(*a, **k)

    def mark_projection_exception(self, **kwargs: Any) -> dict[str, Any]:
        kind = kwargs["kind"]
        return self.store.enqueue_remediation(
            company_code=kwargs["company_code"],
            kind=kind,
            connector_id=kwargs.get("connector_id"),
            employee_key=kwargs.get("employee_key"),
            work_date=kwargs.get("work_date"),
            payload={"projection": kwargs.get("projection") or {}},
            idempotency_key=f"{kwargs['company_code']}:{kind}:{kwargs.get('employee_key')}:{kwargs.get('work_date')}",
        )

    @property
    def items(self) -> dict[str, Any]:
        # lazy view for tests that poke .items[id]
        out = {}
        for company in capture_ops_companies() or {"WATHEFNI"}:
            for i in self.store.list_open_remediation(company) + self.store.payroll_excluded_open(company):
                out[str(i["item_id"])] = SimpleNamespace(**{**i, "item_id": str(i["item_id"])})
        return out


class _PgHealthAdapter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def upsert_from_agent(self, **kwargs: Any) -> Any:
        row = self.store.upsert_health(
            connector_id=kwargs["connector_id"],
            company_code=kwargs["company_code"],
            site_id=kwargs.get("site_id"),
            agent_health=kwargs["agent_health"],
            quarantined_events=kwargs.get("quarantined_events") or 0,
            open_remediation=kwargs.get("open_remediation") or 0,
            revoked=kwargs.get("revoked") or False,
        )
        return SimpleNamespace(**row, to_dict=lambda _r=row: _r)

    def mark_recovered(self, connector_id: str, *, last_sync_at: str | None = None) -> Any:
        row = self.store.mark_recovered(connector_id, last_sync_at=last_sync_at)
        return SimpleNamespace(**row, to_dict=lambda _r=row: _r) if row else None

    def list_company(self, company_code: str) -> list[dict[str, Any]]:
        return self.store.list_health(company_code)

    def contract_schema(self) -> dict[str, Any]:
        return HealthDashboard().contract_schema()


class _PgMappingAdapter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def upsert_mapping(self, **kwargs: Any) -> Any:
        return SimpleNamespace(**self.store.upsert_mapping(**kwargs))

    def resolve(self, **kwargs: Any) -> Any:
        row = self.store.resolve_mapping(**kwargs)
        return SimpleNamespace(**row) if row else None

    def list_open_quarantine(self, company_code: str) -> list[Any]:
        return []


def _pg_connect_factory() -> Callable[[], Any]:
    import app as app_mod

    # Returns a callable that yields app.db_connect() context managers (pooled).
    return app_mod.db_connect


def reset_capture_ops_for_tests(*, force_memory: bool = False) -> None:
    with _LOCK:
        mode = "memory" if force_memory else capture_store_mode()
        _STATE["mode"] = mode
        _STATE["pipeline"] = None
        if mode == "postgres":
            from attendance_capture_postgres import PostgresCaptureStore

            try:
                connect = _pg_connect_factory()
                store = PostgresCaptureStore(
                    connect=connect,
                    manager_scope_allows=_manager_scope_default,
                )
                store.ensure_schema()
            except Exception:  # noqa: BLE001
                _STATE["mode"] = "memory"
                mode = "memory"
            else:
                _STATE["pg"] = store
                _STATE["registry"] = _PgRegistryAdapter(store)
                _STATE["queue"] = _PgQueueAdapter(store)
                _STATE["health"] = _PgHealthAdapter(store)
                _STATE["mapping"] = _PgMappingAdapter(store)
                return
        _STATE["pg"] = None
        _STATE["registry"] = ConnectorRegistry()
        _STATE["mapping"] = InMemoryMappingStore()
        _STATE["health"] = HealthDashboard()
        _STATE["queue"] = RemediationQueue(
            mapping=_STATE["mapping"],
            pipeline=None,
            manager_scope_allows=_manager_scope_default,
        )


def _ensure(manager_scope_allows: Callable[[str, str, str], bool] | None = None) -> dict[str, Any]:
    with _LOCK:
        desired = capture_store_mode()
        if _STATE["registry"] is None or _STATE.get("mode") != desired:
            reset_capture_ops_for_tests()
        if manager_scope_allows is not None:
            _STATE["queue"].manager_scope_allows = manager_scope_allows
            if _STATE.get("pg") is not None:
                _STATE["pg"].manager_scope_allows = manager_scope_allows
        return _STATE


def get_registry(**kwargs: Any) -> Any:
    return _ensure(**kwargs)["registry"]


def get_queue(**kwargs: Any) -> Any:
    return _ensure(**kwargs)["queue"]


def get_health(**kwargs: Any) -> Any:
    return _ensure(**kwargs)["health"]


def get_mapping(**kwargs: Any) -> Any:
    return _ensure(**kwargs)["mapping"]


def get_pg_store() -> Any | None:
    return _ensure().get("pg")


def bind_pipeline(pipeline: CapturePipeline | None) -> None:
    with _LOCK:
        st = _ensure()
        st["pipeline"] = pipeline
        st["queue"].pipeline = pipeline
        if st.get("pg") is not None:
            st["pg"].pipeline = pipeline


def list_connectors(company_code: str) -> list[dict[str, Any]]:
    st = _ensure()
    if st.get("mode") == "postgres" and st.get("pg") is not None:
        return st["pg"].list_connectors(company_code)
    reg = st["registry"]
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
    st = _ensure()
    if st.get("mode") == "postgres" and st.get("pg") is not None:
        return st["pg"].list_sites(company_code)
    reg = st["registry"]
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
    st = _ensure()
    company = company_code.upper()
    if st.get("mode") == "postgres" and st.get("pg") is not None:
        tenant = st["pg"].assert_connector_tenant(connector_id, company)
        if not tenant.get("ok"):
            return {"ok": False, "error": tenant.get("error") or "connector_not_found"}
        # load site_id
        connectors = st["pg"].list_connectors(company)
        match = next((c for c in connectors if c["connector_id"] == connector_id), None)
        site_id = str(match["site_id"]) if match else None
        revoked = bool(match and match.get("status") == "revoked")
        q = get_queue()
        open_n = len([i for i in q.list_open(company) if i.get("connector_id") == connector_id])
        view = st["pg"].upsert_health(
            connector_id=connector_id,
            company_code=company,
            site_id=site_id,
            agent_health=agent_health,
            quarantined_events=0,
            open_remediation=open_n,
            revoked=revoked,
        )
        alerts = view.get("alerts") or []
        if "connector_offline" in alerts:
            q.enqueue(
                company_code=company,
                kind="connector_offline",
                connector_id=connector_id,
                payload={"status": "offline", "last_error": view.get("last_error")},
                idempotency_key=f"offline:{connector_id}",
            )
        if "connector_lag_critical" in alerts or "connector_lag_warning" in alerts:
            q.enqueue(
                company_code=company,
                kind="connector_lag",
                connector_id=connector_id,
                payload={"lag_seconds": view.get("lag_seconds")},
                idempotency_key=f"lag:{connector_id}:{int(view.get('lag_seconds') or 0)//300}",
            )
        return {"ok": True, "health": view}

    reg = get_registry()
    c = reg.connectors.get(connector_id)
    if not c or c.company_code != company:
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
        "store_mode": capture_store_mode(),
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
            "capture_store": capture_store_mode(),
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
