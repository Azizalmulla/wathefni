#!/usr/bin/env python3
"""Attendance Wave 2B — ZKTeco BioTime REST pull adapter (event-only).

Pulls /iclock/api/transactions/ and maps to the canonical punch contract.
Never requests or retains biometric templates/images.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from attendance_capture_contract import (
    BIOTIME_TRANSACTION_ALLOWLIST,
    CONNECTOR_VERSION,
    CanonicalPunch,
    allowlisted_raw_ref,
    as_kuwait,
    biotime_punch_state_to_direction,
    biotime_source_event_id,
    normalize_capture_method,
    sanitize_vendor_payload,
)


class BioTimeAuthError(RuntimeError):
    pass


class BioTimeClient:
    """Minimal BioTime REST client (token or HTTP Basic)."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout_s: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.token = token
        self.timeout_s = timeout_s
        self._opener = opener or urlopen

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        elif self.username and self.password is not None:
            raw = f"{self.username}:{self.password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method=method.upper())
        try:
            with self._opener(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body_txt = ""
            try:
                body_txt = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            if exc.code in {401, 403}:
                raise BioTimeAuthError(f"auth_failed:{exc.code}:{body_txt[:200]}") from exc
            raise RuntimeError(f"biotime_http_{exc.code}:{body_txt[:200]}") from exc
        except URLError as exc:
            raise RuntimeError(f"biotime_unreachable:{exc.reason}") from exc

    def obtain_token(self) -> str:
        if not self.username or self.password is None:
            raise BioTimeAuthError("missing_username_password")
        # BioTime 8/9 commonly expose token via /api-token-auth/ or jwt-api-token-auth/
        for path in ("jwt-api-token-auth/", "api-token-auth/", "api/token/"):
            try:
                data = self.request("POST", path, body={"username": self.username, "password": self.password})
            except Exception:  # noqa: BLE001
                continue
            token = data.get("token") or data.get("access") or data.get("key")
            if token:
                self.token = str(token)
                return self.token
        raise BioTimeAuthError("token_endpoint_failed")

    def rotate_credentials(self, *, username: str | None = None, password: str | None = None, token: str | None = None) -> None:
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password
        if token is not None:
            self.token = token
        elif username is not None or password is not None:
            self.token = None

    def list_transactions(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        limit: int = 100,
        terminal_sn: str | None = None,
        emp_code: str | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "GET",
            "iclock/api/transactions/",
            params={
                "page": page,
                "limit": limit,
                "start_time": start_time,
                "end_time": end_time,
                "terminal_sn": terminal_sn,
                "emp_code": emp_code,
            },
        )


def extract_transaction_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("data"), list):
        return [r for r in payload["data"] if isinstance(r, dict)]
    if isinstance(payload.get("results"), list):
        return [r for r in payload["results"] if isinstance(r, dict)]
    if isinstance(payload.get("items"), list):
        return [r for r in payload["items"] if isinstance(r, dict)]
    return []


def transaction_to_canonical(
    row: dict[str, Any],
    *,
    company_code: str,
    connector_id: str,
    punch_state_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Sanitize + map one BioTime transaction. Returns ok/quarantine/reject."""
    san = sanitize_vendor_payload(row)
    if not san.ok:
        return {
            "ok": False,
            "error": san.reason,
            "forbidden_keys": san.forbidden_keys,
            "privacy_hard_fail": True,
        }
    clean = san.payload or {}
    emp_code = str(clean.get("emp_code") or "").strip()
    punch_time = as_kuwait(clean.get("punch_time"))
    direction = biotime_punch_state_to_direction(clean.get("punch_state"), mapping=punch_state_map)
    terminal_sn = str(clean.get("terminal_sn") or "").strip() or None
    tx_id = clean.get("id")
    source_event_id = biotime_source_event_id(
        tx_id,
        fallback_parts=(emp_code, clean.get("punch_time"), clean.get("punch_state"), terminal_sn),
    )
    if not emp_code:
        return {"ok": False, "error": "missing_emp_code", "source_event_id": source_event_id, "quarantine": True}
    if punch_time is None:
        return {"ok": False, "error": "invalid_punch_time", "source_event_id": source_event_id, "quarantine": True}
    if direction is None:
        return {
            "ok": False,
            "error": "unmapped_punch_state",
            "source_event_id": source_event_id,
            "quarantine": True,
            "device_user_id": emp_code,
            "device_id": terminal_sn,
        }

    capture_method = normalize_capture_method(clean.get("verify_type"))
    # GPS coordinates are allowed as event metadata scalars; capture_method may be gps if mobile punch.
    if clean.get("longitude") not in (None, "", 0, "0") and capture_method == "unknown":
        if clean.get("mobile"):
            capture_method = "gps"

    punch = CanonicalPunch(
        company_code=company_code.upper(),
        source="biotime",
        source_event_id=source_event_id,
        device_user_id=emp_code,
        punched_at=punch_time,
        direction=direction,
        capture_method=capture_method,
        device_id=terminal_sn,
        connector_id=connector_id,
        connector_version=CONNECTOR_VERSION,
        raw_ref=allowlisted_raw_ref(clean, BIOTIME_TRANSACTION_ALLOWLIST),
        metadata={
            "capture_method": capture_method,
            "vendor": "biotime",
            "verify_type_code": clean.get("verify_type"),
        },
    )
    return {"ok": True, "punch": punch}


def pull_transactions_paginated(
    client: BioTimeClient,
    *,
    company_code: str,
    connector_id: str,
    start_time: str | None = None,
    end_time: str | None = None,
    page_size: int = 50,
    max_pages: int = 100,
    after_checkpoint: str | None = None,
    punch_state_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Pull pages; optionally skip rows <= checkpoint (transaction id or punch_time)."""
    accepted: list[CanonicalPunch] = []
    quarantined: list[dict[str, Any]] = []
    privacy_fails: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    page = 1
    latest_checkpoint = after_checkpoint
    while page <= max_pages:
        payload = client.list_transactions(start_time=start_time, end_time=end_time, page=page, limit=page_size)
        rows = extract_transaction_rows(payload)
        if not rows:
            break
        for row in rows:
            mapped = transaction_to_canonical(
                row,
                company_code=company_code,
                connector_id=connector_id,
                punch_state_map=punch_state_map,
            )
            if mapped.get("privacy_hard_fail"):
                privacy_fails.append(mapped)
                continue
            if not mapped.get("ok"):
                quarantined.append(mapped)
                continue
            punch: CanonicalPunch = mapped["punch"]
            if punch.source_event_id in seen_ids:
                continue
            # Checkpoint resume: skip already-processed ids when checkpoint is biotime:ID
            if after_checkpoint:
                if punch.source_event_id == after_checkpoint:
                    continue
                # numeric id ordering when possible
                try:
                    cur_id = int(str(punch.raw_ref.get("id")))
                    cp = after_checkpoint.split(":")[-1]
                    if cp.isdigit() and cur_id <= int(cp):
                        continue
                except Exception:  # noqa: BLE001
                    pass
            seen_ids.add(punch.source_event_id)
            accepted.append(punch)
            latest_checkpoint = punch.source_event_id
        # stop if last page
        count = payload.get("count")
        if isinstance(count, int) and page * page_size >= count:
            break
        if len(rows) < page_size:
            break
        page += 1
    return {
        "ok": True,
        "punches": accepted,
        "quarantined": quarantined,
        "privacy_fails": privacy_fails,
        "pages": page,
        "checkpoint": latest_checkpoint,
        "pulled_at": datetime.now().isoformat(),
    }
