#!/usr/bin/env python3
"""Attendance Wave 2D — connector health dashboard contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

KUWAIT_TZ = timezone(timedelta(hours=3))


@dataclass
class ConnectorHealthView:
    connector_id: str
    company_code: str
    site_id: str | None
    status: str  # online|offline|degraded|revoked
    last_sync_at: str | None = None
    lag_seconds: float | None = None
    failure_count: int = 0
    last_error: str | None = None
    quarantined_events: int = 0
    open_remediation: int = 0
    checkpoint: str | None = None
    connector_version: str | None = None
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HealthDashboard:
    """Aggregates agent health + remediation counts into a UI/API contract."""

    LAG_WARN_S = 300.0
    LAG_CRIT_S = 1800.0

    def __init__(self) -> None:
        self._views: dict[str, ConnectorHealthView] = {}

    def upsert_from_agent(
        self,
        *,
        connector_id: str,
        company_code: str,
        site_id: str | None,
        agent_health: dict[str, Any],
        quarantined_events: int = 0,
        open_remediation: int = 0,
        revoked: bool = False,
    ) -> ConnectorHealthView:
        raw_status = str(agent_health.get("status") or "offline").lower()
        if revoked:
            status = "revoked"
        elif raw_status in {"error", "offline"}:
            status = "offline" if raw_status == "offline" else "degraded"
        elif raw_status == "degraded":
            status = "degraded"
        else:
            status = "online"

        lag = agent_health.get("lag_seconds")
        try:
            lag_f = float(lag) if lag is not None else None
        except (TypeError, ValueError):
            lag_f = None

        alerts: list[str] = []
        if status == "offline":
            alerts.append("connector_offline")
        if status == "degraded":
            alerts.append("connector_failures")
        if lag_f is not None and lag_f >= self.LAG_CRIT_S:
            alerts.append("connector_lag_critical")
            status = "degraded"
        elif lag_f is not None and lag_f >= self.LAG_WARN_S:
            alerts.append("connector_lag_warning")
        if quarantined_events > 0:
            alerts.append("quarantined_events")
        if open_remediation > 0:
            alerts.append("open_remediation")

        view = ConnectorHealthView(
            connector_id=connector_id,
            company_code=company_code.upper(),
            site_id=site_id,
            status=status,
            last_sync_at=agent_health.get("last_sync_at") or agent_health.get("last_success_at"),
            lag_seconds=lag_f,
            failure_count=int(agent_health.get("error_count") or 0),
            last_error=agent_health.get("last_error"),
            quarantined_events=int(quarantined_events),
            open_remediation=int(open_remediation),
            checkpoint=agent_health.get("checkpoint"),
            connector_version=agent_health.get("connector_version"),
            alerts=alerts,
        )
        self._views[connector_id] = view
        return view

    def mark_recovered(
        self, connector_id: str, *, last_sync_at: str | None = None
    ) -> ConnectorHealthView | None:
        view = self._views.get(connector_id)
        if not view or view.status == "revoked":
            return view
        view.status = "online"
        view.lag_seconds = 0.0
        view.last_sync_at = last_sync_at or datetime.now(tz=KUWAIT_TZ).isoformat()
        view.alerts = [
            a
            for a in view.alerts
            if a
            not in {
                "connector_offline",
                "connector_lag_critical",
                "connector_lag_warning",
                "connector_failures",
            }
        ]
        return view

    def list_company(self, company_code: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        return [v.to_dict() for v in self._views.values() if v.company_code == company]

    def contract_schema(self) -> dict[str, Any]:
        return {
            "version": "attendance_connector_health_wave2d_v1",
            "fields": [
                "connector_id",
                "company_code",
                "site_id",
                "status",
                "last_sync_at",
                "lag_seconds",
                "failure_count",
                "last_error",
                "quarantined_events",
                "open_remediation",
                "checkpoint",
                "connector_version",
                "alerts",
            ],
            "status_enum": ["online", "offline", "degraded", "revoked"],
            "alert_enum": [
                "connector_offline",
                "connector_failures",
                "connector_lag_warning",
                "connector_lag_critical",
                "quarantined_events",
                "open_remediation",
            ],
        }
