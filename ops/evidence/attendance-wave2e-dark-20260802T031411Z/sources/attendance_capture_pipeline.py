#!/usr/bin/env python3
"""Attendance Wave 2B — capture pipeline into Wave 1 Attendance Authority.

vendor event → privacy sanitizer → canonical punch → mapping → immutable ledger
→ projection → approval → payroll snapshot (via authority APIs).

Never auto-creates employees. Unknown device users quarantine for review.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

import attendance_authority_wave1 as authority
from attendance_capture_contract import (
    CONNECTOR_VERSION,
    CanonicalPunch,
    InMemoryMappingStore,
    as_kuwait,
    validate_canonical_punch,
)

EmployeeResolver = Callable[[str, str], dict[str, Any] | None]


class CapturePipeline:
    def __init__(
        self,
        *,
        authority_service: authority.AttendanceAuthorityService | None = None,
        mapping: InMemoryMappingStore | None = None,
        employee_resolver: EmployeeResolver | None = None,
        connector_id: str = "capture-default",
        require_mapping: bool = True,
    ) -> None:
        self.svc = authority_service or authority.AttendanceAuthorityService()
        self.mapping = mapping or InMemoryMappingStore()
        self.employee_resolver = employee_resolver
        self.connector_id = connector_id
        self.require_mapping = require_mapping
        self.version = CONNECTOR_VERSION

    def _employee_for(self, company_code: str, employee_key: str) -> dict[str, Any] | None:
        if self.employee_resolver:
            return self.employee_resolver(company_code, employee_key)
        # Synthetic default for local/staging tests — callers should inject resolver for real DBs.
        return {"employee_key": employee_key, "company_code": company_code.upper(), "phone": None, "name": employee_key}

    def ingest_canonical(
        self,
        punch: CanonicalPunch | dict[str, Any],
        *,
        shift: dict[str, Any] | None = None,
        work_date: date | None = None,
        reproject: bool = True,
    ) -> dict[str, Any]:
        validated = validate_canonical_punch(punch)
        if not validated.get("ok"):
            return {"ok": False, "error": "invalid_canonical", "detail": validated}

        data = validated["punch"]
        company = data["company_code"]
        device_user_id = data["device_user_id"]
        device_id = data.get("device_id")
        employee_key = data.get("employee_key")

        if not employee_key:
            mapped = self.mapping.resolve(company_code=company, device_user_id=device_user_id, device_id=device_id)
            if mapped:
                employee_key = mapped.employee_key
            elif self.require_mapping:
                q = self.mapping.quarantine(
                    company_code=company,
                    connector_id=str(data.get("connector_id") or self.connector_id),
                    reason="unknown_device_user",
                    source=data["source"],
                    source_event_id=data["source_event_id"],
                    payload=data,
                    device_user_id=device_user_id,
                    device_id=device_id,
                )
                return {
                    "ok": False,
                    "quarantined": True,
                    "reason": "unknown_device_user",
                    "quarantine_id": q.quarantine_id,
                    "source_event_id": data["source_event_id"],
                }

        assert employee_key
        employee = self._employee_for(company, employee_key)
        if employee is None:
            q = self.mapping.quarantine(
                company_code=company,
                connector_id=str(data.get("connector_id") or self.connector_id),
                reason="employee_not_found",
                source=data["source"],
                source_event_id=data["source_event_id"],
                payload=data,
                device_user_id=device_user_id,
                device_id=device_id,
            )
            return {
                "ok": False,
                "quarantined": True,
                "reason": "employee_not_found",
                "quarantine_id": q.quarantine_id,
            }

        punched_at = as_kuwait(data["punched_at"])
        assert punched_at is not None
        wd = work_date
        if wd is None and data.get("work_date_hint"):
            try:
                wd = date.fromisoformat(str(data["work_date_hint"]))
            except ValueError:
                wd = None

        meta = dict(data.get("metadata") or {})
        meta.update(
            {
                "capture_method": data.get("capture_method"),
                "device_id": device_id,
                "device_user_id": device_user_id,
                "connector_id": data.get("connector_id") or self.connector_id,
                "connector_version": data.get("connector_version") or self.version,
                "raw_ref": data.get("raw_ref") or {},
            }
        )

        result = self.svc.ingest_punch(
            company_code=company,
            employee=employee,
            punched_at=punched_at,
            direction=data["direction"],
            source=data["source"],
            source_event_id=data["source_event_id"],
            shift=shift,
            work_date=wd,
            metadata=meta,
            reproject=reproject,
        )
        result["canonical"] = data
        return result

    def ingest_many(
        self,
        punches: list[CanonicalPunch | dict[str, Any]],
        *,
        shift_for: Callable[[CanonicalPunch | dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        accepted = 0
        duplicates = 0
        quarantined = 0
        failed = 0
        details = []
        for p in punches:
            shift = shift_for(p) if shift_for else None
            res = self.ingest_canonical(p, shift=shift)
            details.append({"source_event_id": (p.source_event_id if isinstance(p, CanonicalPunch) else p.get("source_event_id")), "result": {"ok": res.get("ok"), "duplicate": res.get("duplicate"), "quarantined": res.get("quarantined"), "error": res.get("error") or res.get("reason")}})
            if res.get("quarantined"):
                quarantined += 1
            elif not res.get("ok"):
                failed += 1
            elif res.get("duplicate"):
                duplicates += 1
                accepted += 1
            else:
                accepted += 1
        return {
            "ok": failed == 0,
            "accepted": accepted,
            "duplicates": duplicates,
            "quarantined": quarantined,
            "failed": failed,
            "details": details,
        }

    def map_and_replay_quarantine(self, quarantine_id: str, *, employee_key: str, shift: dict[str, Any] | None = None) -> dict[str, Any]:
        q = self.mapping.resolve_quarantine(quarantine_id, employee_key=employee_key)
        if not q:
            return {"ok": False, "error": "quarantine_not_found"}
        payload = dict(q.payload)
        payload["employee_key"] = employee_key
        return self.ingest_canonical(payload, shift=shift)
