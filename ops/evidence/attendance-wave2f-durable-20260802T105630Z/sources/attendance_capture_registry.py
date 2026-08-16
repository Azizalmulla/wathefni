#!/usr/bin/env python3
"""Attendance Wave 2D — customer/site/device connector registry.

Tenant ownership verification, credential rotate/revoke, registration lifecycle.
Does not connect real devices or ingest punches by itself.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from attendance_capture_agent import CredentialVault
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

KUWAIT_TZ = timezone(timedelta(hours=3))


def _now() -> str:
    return datetime.now(tz=KUWAIT_TZ).isoformat()


@dataclass
class SiteRecord:
    site_id: str
    company_code: str
    name: str
    timezone: str = "Asia/Kuwait"
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceRecord:
    device_id: str
    company_code: str
    site_id: str
    terminal_sn: str
    vendor: str = "biotime"
    active: bool = True
    owned_by_company: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorRegistration:
    connector_id: str
    company_code: str
    site_id: str
    device_id: str | None
    status: str  # registered|active|rotated|revoked|suspended
    connector_version: str
    row_version: int = 1
    created_at: str = ""
    updated_at: str = ""
    revoked_at: str | None = None
    last_rotate_at: str | None = None
    health: dict[str, Any] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # never expose sealed secrets here
        return d


class ConnectorRegistry:
    """In-memory registry suitable for local/staging qualification."""

    def __init__(self, *, vault: CredentialVault | None = None) -> None:
        self.vault = vault or CredentialVault()
        self.sites: dict[str, SiteRecord] = {}
        self.devices: dict[str, DeviceRecord] = {}
        self.connectors: dict[str, ConnectorRegistration] = {}
        self._sealed: dict[str, str] = {}
        self._previous_sealed: dict[str, str | None] = {}

    def register_site(self, *, company_code: str, name: str, timezone: str = "Asia/Kuwait") -> SiteRecord:
        site = SiteRecord(
            site_id=str(uuid.uuid4()),
            company_code=company_code.upper(),
            name=name,
            timezone=timezone,
        )
        self.sites[site.site_id] = site
        return site

    def register_device(
        self,
        *,
        company_code: str,
        site_id: str,
        terminal_sn: str,
        vendor: str = "biotime",
        actor_company: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        actor = (actor_company or company).upper()
        site = self.sites.get(site_id)
        if not site or site.company_code != company:
            return {"ok": False, "error": "site_not_found_or_wrong_tenant"}
        if actor != company:
            return {"ok": False, "error": "cross_tenant_device_registration_denied", "actor": actor, "company": company}
        # reject registering a device already owned by another tenant
        for d in self.devices.values():
            if d.terminal_sn == terminal_sn and d.company_code != company and d.active:
                return {"ok": False, "error": "device_owned_by_other_tenant", "owner": d.company_code}
        rec = DeviceRecord(
            device_id=str(uuid.uuid4()),
            company_code=company,
            site_id=site_id,
            terminal_sn=terminal_sn,
            vendor=vendor,
            owned_by_company=company,
        )
        self.devices[rec.device_id] = rec
        return {"ok": True, "device": asdict(rec)}

    def register_connector(
        self,
        *,
        company_code: str,
        site_id: str,
        device_id: str | None,
        secrets: dict[str, Any],
        connector_version: str,
        actor_company: str | None = None,
        actor_phone: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        actor = (actor_company or company).upper()
        if actor != company:
            return {"ok": False, "error": "cross_tenant_connector_registration_denied"}
        site = self.sites.get(site_id)
        if not site or site.company_code != company:
            return {"ok": False, "error": "site_tenant_mismatch"}
        if device_id:
            device = self.devices.get(device_id)
            if not device or device.company_code != company:
                return {"ok": False, "error": "device_tenant_mismatch"}
            if device.site_id != site_id:
                return {"ok": False, "error": "device_site_mismatch"}
        connector_id = f"conn-{company.lower()}-{uuid.uuid4().hex[:10]}"
        sealed = self.vault.seal(secrets)
        now = _now()
        reg = ConnectorRegistration(
            connector_id=connector_id,
            company_code=company,
            site_id=site_id,
            device_id=device_id,
            status="registered",
            connector_version=connector_version,
            created_at=now,
            updated_at=now,
            audit=[{"at": now, "action": "register", "actor_phone": actor_phone}],
        )
        self.connectors[connector_id] = reg
        self._sealed[connector_id] = sealed
        self._previous_sealed[connector_id] = None
        return {"ok": True, "connector": reg.public_dict(), "secrets": REDACTED}

    def verify_device_ownership(self, *, company_code: str, terminal_sn: str) -> dict[str, Any]:
        company = company_code.upper()
        matches = [d for d in self.devices.values() if d.terminal_sn == terminal_sn and d.active]
        if not matches:
            return {"ok": False, "error": "device_not_registered"}
        owned = [d for d in matches if d.company_code == company]
        if not owned:
            return {"ok": False, "error": "wrong_tenant_device", "owner": matches[0].company_code}
        return {"ok": True, "device": asdict(owned[0])}

    def activate(self, connector_id: str, *, expected_row_version: int, actor_phone: str | None = None) -> dict[str, Any]:
        reg = self.connectors.get(connector_id)
        if not reg:
            return {"ok": False, "error": "connector_not_found"}
        if reg.status == "revoked":
            return {"ok": False, "error": "connector_revoked"}
        if reg.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": reg.row_version}
        reg.status = "active"
        reg.row_version += 1
        reg.updated_at = _now()
        reg.audit.append({"at": reg.updated_at, "action": "activate", "actor_phone": actor_phone})
        return {"ok": True, "connector": reg.public_dict()}

    def rotate_credentials(
        self,
        connector_id: str,
        *,
        new_secrets: dict[str, Any],
        expected_row_version: int,
        actor_phone: str | None = None,
    ) -> dict[str, Any]:
        reg = self.connectors.get(connector_id)
        if not reg:
            return {"ok": False, "error": "connector_not_found"}
        if reg.status == "revoked":
            return {"ok": False, "error": "connector_revoked"}
        if reg.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": reg.row_version}
        self._previous_sealed[connector_id] = self._sealed.get(connector_id)
        self._sealed[connector_id] = self.vault.seal(new_secrets)
        reg.status = "rotated"
        reg.last_rotate_at = _now()
        reg.updated_at = reg.last_rotate_at
        reg.row_version += 1
        reg.audit.append({"at": reg.updated_at, "action": "rotate", "actor_phone": actor_phone})
        return {"ok": True, "connector": reg.public_dict(), "secrets": REDACTED}

    def revoke(
        self,
        connector_id: str,
        *,
        expected_row_version: int,
        actor_phone: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        reg = self.connectors.get(connector_id)
        if not reg:
            return {"ok": False, "error": "connector_not_found"}
        if reg.row_version != expected_row_version:
            return {"ok": False, "error": "stale_row_version", "current": reg.row_version}
        reg.status = "revoked"
        reg.revoked_at = _now()
        reg.updated_at = reg.revoked_at
        reg.row_version += 1
        reg.audit.append({"at": reg.updated_at, "action": "revoke", "actor_phone": actor_phone, "reason": reason})
        # wipe sealed material
        self._sealed.pop(connector_id, None)
        self._previous_sealed.pop(connector_id, None)
        return {"ok": True, "connector": reg.public_dict()}

    def reconnect_after_rotate(self, connector_id: str) -> dict[str, Any]:
        """Load current sealed secrets for agent reconnect (values not returned)."""
        reg = self.connectors.get(connector_id)
        if not reg:
            return {"ok": False, "error": "connector_not_found"}
        if reg.status == "revoked":
            return {"ok": False, "error": "connector_revoked"}
        sealed = self._sealed.get(connector_id)
        if not sealed:
            return {"ok": False, "error": "credentials_missing"}
        try:
            secrets = self.vault.open(sealed)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": safe_error(exc)}
        # Return only non-secret metadata + presence flags
        return {
            "ok": True,
            "connector_id": connector_id,
            "status": reg.status,
            "has_username": bool(secrets.get("username")),
            "has_password": bool(secrets.get("password")),
            "has_token": bool(secrets.get("token")),
            "secrets": REDACTED,
        }

    def assert_connector_tenant(self, connector_id: str, company_code: str) -> dict[str, Any]:
        reg = self.connectors.get(connector_id)
        if not reg:
            return {"ok": False, "error": "connector_not_found"}
        if reg.company_code != company_code.upper():
            return {"ok": False, "error": "cross_tenant_denied"}
        if reg.status == "revoked":
            return {"ok": False, "error": "connector_revoked"}
        return {"ok": True, "connector_id": connector_id}
