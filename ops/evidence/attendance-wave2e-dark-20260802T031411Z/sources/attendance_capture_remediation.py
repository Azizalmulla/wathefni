#!/usr/bin/env python3
"""Attendance Wave 2D — HR remediation queue and mapping approve/reject/replay.

Exception kinds: unknown employee/device, missing check-in/out, ambiguous punch
order, duplicate/conflicting events, connector lag/offline.
Optimistic concurrency via row_version. Audit trail on every decision.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from attendance_capture_contract import CanonicalPunch, InMemoryMappingStore
from attendance_capture_pipeline import CapturePipeline
from attendance_capture_secrets import redact_mapping

KUWAIT_TZ = timezone(timedelta(hours=3))

EXCEPTION_KINDS = frozenset({
    "unknown_employee",
    "unknown_device",
    "missing_check_in",
    "missing_check_out",
    "ambiguous_punch_order",
    "duplicate_conflict",
    "connector_lag",
    "connector_offline",
})

OPEN_STATES = frozenset({"open", "approved_pending_replay"})
TERMINAL_STATES = frozenset({"approved_replayed", "rejected", "superseded"})


def _now() -> str:
    return datetime.now(tz=KUWAIT_TZ).isoformat()


@dataclass
class RemediationItem:
    item_id: str
    company_code: str
    kind: str
    status: str
    connector_id: str | None
    employee_key: str | None
    device_id: str | None
    device_user_id: str | None
    work_date: str | None
    source_event_id: str | None
    payload: dict[str, Any]
    row_version: int = 1
    payroll_excluded: bool = True
    created_at: str = ""
    updated_at: str = ""
    audit: list[dict[str, Any]] = field(default_factory=list)


class RemediationQueue:
    def __init__(
        self,
        *,
        mapping: InMemoryMappingStore | None = None,
        pipeline: CapturePipeline | None = None,
        manager_scope_allows: Callable[[str, str, str], bool] | None = None,
    ) -> None:
        self.mapping = mapping or InMemoryMappingStore()
        self.pipeline = pipeline
        self.manager_scope_allows = manager_scope_allows or (lambda _company, _actor, _employee: True)
        self.items: dict[str, RemediationItem] = {}
        # idempotency for repeated remediation actions
        self._action_keys: set[str] = set()

    def enqueue(
        self,
        *,
        company_code: str,
        kind: str,
        payload: dict[str, Any],
        connector_id: str | None = None,
        employee_key: str | None = None,
        device_id: str | None = None,
        device_user_id: str | None = None,
        work_date: str | None = None,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if kind not in EXCEPTION_KINDS:
            return {"ok": False, "error": "invalid_kind", "kind": kind}
        key = idempotency_key or f"{company_code}:{kind}:{source_event_id or ''}:{device_user_id or ''}:{work_date or ''}"
        if key in self._action_keys:
            existing = next((i for i in self.items.values() if any(a.get("idempotency_key") == key for a in i.audit)), None)
            return {"ok": True, "duplicate": True, "item": asdict(existing) if existing else None}
        now = _now()
        item = RemediationItem(
            item_id=str(uuid.uuid4()),
            company_code=company_code.upper(),
            kind=kind,
            status="open",
            connector_id=connector_id,
            employee_key=employee_key,
            device_id=device_id,
            device_user_id=device_user_id,
            work_date=work_date,
            source_event_id=source_event_id,
            payload=redact_mapping(payload),
            created_at=now,
            updated_at=now,
            payroll_excluded=True,
            audit=[{"at": now, "action": "enqueue", "idempotency_key": key}],
        )
        self.items[item.item_id] = item
        self._action_keys.add(key)
        return {"ok": True, "duplicate": False, "item": asdict(item)}

    def list_open(self, company_code: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        return [asdict(i) for i in self.items.values() if i.company_code == company and i.status in OPEN_STATES]

    def _get(self, item_id: str) -> RemediationItem | None:
        return self.items.get(item_id)

    def _deny_self(self, *, actor_phone: str | None, employee_phone: str | None, actor_is_manager: bool) -> bool:
        if not actor_is_manager:
            return False
        a = "".join(ch for ch in str(actor_phone or "") if ch.isdigit())
        e = "".join(ch for ch in str(employee_phone or "") if ch.isdigit())
        return bool(a and e and a == e)

    def approve_mapping(
        self,
        item_id: str,
        *,
        employee_key: str,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        actor_is_manager: bool = False,
        employee_phone: str | None = None,
        replay: bool = True,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = self._get(item_id)
        if not item:
            return {"ok": False, "error": "item_not_found"}
        if item.company_code != actor_company.upper():
            return {"ok": False, "error": "cross_tenant_denied"}
        if item.kind not in {"unknown_employee", "unknown_device"}:
            return {"ok": False, "error": "not_a_mapping_item", "kind": item.kind}
        if item.status not in {"open"}:
            return {"ok": False, "error": "item_not_open", "status": item.status}
        if item.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": item.row_version}
        if self._deny_self(actor_phone=actor_phone, employee_phone=employee_phone, actor_is_manager=actor_is_manager):
            return {"ok": False, "error": "manager_self_action_denied"}
        scope_target = employee_key or item.employee_key
        if scope_target and not self.manager_scope_allows(item.company_code, actor_phone, scope_target):
            return {"ok": False, "error": "manager_scope_denied"}
        if not item.device_user_id:
            return {"ok": False, "error": "missing_device_user_id"}

        self.mapping.upsert_mapping(
            company_code=item.company_code,
            device_user_id=item.device_user_id,
            employee_key=employee_key,
            device_id=item.device_id,
        )
        item.employee_key = employee_key
        item.status = "approved_pending_replay" if replay else "approved_replayed"
        item.row_version += 1
        item.updated_at = _now()
        item.audit.append(
            {
                "at": item.updated_at,
                "action": "approve_mapping",
                "actor_phone": actor_phone,
                "employee_key": employee_key,
                "row_version": item.row_version,
            }
        )
        result: dict[str, Any] = {"ok": True, "item": asdict(item)}
        if replay and self.pipeline is not None:
            replay_res = self.replay_item(item_id, expected_row_version=item.row_version, actor_phone=actor_phone, actor_company=actor_company, shift=shift)
            result["replay"] = replay_res
            # refresh item
            result["item"] = asdict(self.items[item_id])
        return result

    def reject(
        self,
        item_id: str,
        *,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        reason: str | None = None,
        actor_is_manager: bool = False,
        employee_phone: str | None = None,
    ) -> dict[str, Any]:
        item = self._get(item_id)
        if not item:
            return {"ok": False, "error": "item_not_found"}
        if item.company_code != actor_company.upper():
            return {"ok": False, "error": "cross_tenant_denied"}
        if item.status not in OPEN_STATES:
            # idempotent reject of already rejected
            if item.status == "rejected":
                return {"ok": True, "duplicate": True, "item": asdict(item)}
            return {"ok": False, "error": "item_not_open", "status": item.status}
        if item.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": item.row_version}
        if self._deny_self(actor_phone=actor_phone, employee_phone=employee_phone, actor_is_manager=actor_is_manager):
            return {"ok": False, "error": "manager_self_action_denied"}
        item.status = "rejected"
        item.row_version += 1
        item.updated_at = _now()
        item.payroll_excluded = True
        item.audit.append({"at": item.updated_at, "action": "reject", "actor_phone": actor_phone, "reason": reason})
        return {"ok": True, "item": asdict(item)}

    def replay_item(
        self,
        item_id: str,
        *,
        expected_row_version: int,
        actor_phone: str,
        actor_company: str,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = self._get(item_id)
        if not item:
            return {"ok": False, "error": "item_not_found"}
        if item.company_code != actor_company.upper():
            return {"ok": False, "error": "cross_tenant_denied"}
        if item.status not in {"approved_pending_replay", "approved_replayed"}:
            return {"ok": False, "error": "replay_not_allowed", "status": item.status}
        if item.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": item.row_version}
        if self.pipeline is None:
            return {"ok": False, "error": "pipeline_not_configured"}
        payload = dict(item.payload)
        payload["employee_key"] = item.employee_key
        # Only mapping-driven unknown punches may replay into authority
        if item.kind not in {"unknown_employee", "unknown_device"}:
            return {"ok": False, "error": "kind_not_replayable_to_authority", "kind": item.kind}
        action_key = f"replay:{item_id}:{item.row_version}"
        if action_key in self._action_keys and item.status == "approved_replayed":
            return {"ok": True, "duplicate": True, "item": asdict(item)}
        res = self.pipeline.ingest_canonical(payload, shift=shift)
        item.status = "approved_replayed"
        item.row_version += 1
        item.updated_at = _now()
        item.payroll_excluded = False if res.get("ok") else True
        item.audit.append({"at": item.updated_at, "action": "replay", "actor_phone": actor_phone, "result_ok": res.get("ok")})
        self._action_keys.add(action_key)
        return {"ok": bool(res.get("ok")), "ingest": res, "item": asdict(item)}

    def mark_projection_exception(
        self,
        *,
        company_code: str,
        kind: str,
        employee_key: str,
        work_date: str,
        projection: dict[str, Any],
        connector_id: str | None = None,
    ) -> dict[str, Any]:
        """Enqueue missing/ambiguous exceptions — always payroll_excluded until resolved."""
        if kind not in {"missing_check_in", "missing_check_out", "ambiguous_punch_order"}:
            return {"ok": False, "error": "invalid_projection_exception"}
        return self.enqueue(
            company_code=company_code,
            kind=kind,
            connector_id=connector_id,
            employee_key=employee_key,
            work_date=work_date,
            payload={"projection": projection, "exception_state": projection.get("exception_state"), "status": projection.get("status")},
            idempotency_key=f"{company_code}:{kind}:{employee_key}:{work_date}",
        )

    def payroll_excluded_open(self, company_code: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        return [
            asdict(i)
            for i in self.items.values()
            if i.company_code == company and i.payroll_excluded and i.status in OPEN_STATES.union({"rejected", "approved_pending_replay"})
        ]
