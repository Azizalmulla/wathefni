"""P2 Assistant calendar + employee-app channel awareness helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def list_calendar_events(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    actor_role: str | None,
    permissions: set[str] | list[str] | None,
    scope: str = "mine",
    days: int = 14,
) -> dict[str, Any]:
    import calendar_projections as cal_proj

    company = str(company_code or "").strip().upper()
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=max(1, min(int(days or 14), 60)))
    result = cal_proj.project_events(
        legacy,
        company_code=company,
        actor_user_id=str(actor_user_id or ""),
        actor_role=str(actor_role or "hr_admin"),
        permissions=permissions or [],
        scope=str(scope or "mine"),
        start=start.isoformat(),
        end=end.isoformat(),
        org_scope_id=None,
        event_types=None,
        statuses=None,
        mine_only=False,
    )
    events = result.get("events") if isinstance(result, dict) and isinstance(result.get("events"), list) else []
    compact = []
    for row in events[:40]:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "event_id": row.get("event_id") or row.get("id"),
                "title": row.get("title") or row.get("summary"),
                "start": row.get("start") or row.get("starts_at"),
                "end": row.get("end") or row.get("ends_at"),
                "event_type": row.get("event_type") or row.get("type"),
                "status": row.get("status"),
            }
        )
    return {
        "ok": True,
        "company_code": company,
        "scope": scope,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "count": len(compact),
        "events": compact,
    }
