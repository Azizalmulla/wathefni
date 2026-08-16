#!/usr/bin/env python3
"""Attendance Wave 2B — vendor-neutral canonical punch capture contract.

Privacy: Wathefni never stores fingerprint/face images or biometric templates.
BioTime (or other devices) remains the biometric verification authority.

Does not enable real clocking, QR/GPS/kiosk UI, or frozen-module changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

CONNECTOR_VERSION = "attendance_capture_wave2b_v1"
KUWAIT_TZ = timezone(timedelta(hours=3))

PUNCH_DIRECTIONS = frozenset({"in", "out", "break_start", "break_end"})
CAPTURE_METHODS = frozenset({
    "biometric",
    "face",
    "rfid",
    "card",
    "pin",
    "qr",
    "gps",
    "kiosk",
    "pos",
    "file_import",
    "manual_correction",
    "unknown",
})
CAPTURE_SOURCES = frozenset({
    "biotime",
    "csv",
    "sftp",
    "file_import",
    "capture",
    "hikcentral",
    "hik_isapi",
    "biostar",
    "anviz_cloud",
    "iba",
    "adms",
})

BIOMETRIC_FORBIDDEN_KEYS = frozenset({
    "fingerprint_image",
    "fingerprintimage",
    "face_image",
    "faceimage",
    "face_photo",
    "biometric_template",
    "biometrictemplate",
    "template",
    "template_data",
    "templatedata",
    "biodata",
    "bio_data",
    "picture",
    "pictureurl",
    "picture_url",
    "photo",
    "photo_url",
    "photourl",
    "face_template",
    "facetemplate",
    "fp_template",
    "fptemplate",
    "palm_template",
    "iris_template",
    "raw_image",
    "rawimage",
    "bmpimage",
    "bmp_image",
})

_BASE64_IMAGE_RE = re.compile(
    r"^(?:data:image/[a-zA-Z0-9.+-]+;base64,)?[A-Za-z0-9+/]{200,}={0,2}$"
)
# Templates are long hex; 64-char digests (sha256) are not biometric templates.
_HEX_TEMPLATE_RE = re.compile(r"^[0-9a-fA-F]{128,}$")
_HASH_KEY_HINTS = frozenset({"sha256", "sha1", "md5", "hash", "checksum", "etag", "filesha256", "rowsha256"})


@dataclass
class CanonicalPunch:
    company_code: str
    source: str
    source_event_id: str
    device_user_id: str
    punched_at: datetime
    direction: str
    capture_method: str = "unknown"
    employee_key: str | None = None
    device_id: str | None = None
    connector_id: str | None = None
    connector_version: str = CONNECTOR_VERSION
    work_date_hint: date | None = None
    raw_ref: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["punched_at"] = self.punched_at.isoformat()
        if self.work_date_hint is not None:
            d["work_date_hint"] = self.work_date_hint.isoformat()
        return d


@dataclass
class SanitizeResult:
    ok: bool
    reason: str | None = None
    forbidden_keys: list[str] = field(default_factory=list)
    payload: dict[str, Any] | None = None


def digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def as_kuwait(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
                try:
                    value = datetime.strptime(str(value).strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if value.tzinfo is None:
        return value.replace(tzinfo=KUWAIT_TZ)
    return value.astimezone(KUWAIT_TZ)


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _looks_like_biometric_blob(value: Any, *, key_hint: str = "") -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 64:
        return False
    nk = _norm_key(key_hint)
    if any(h in nk for h in _HASH_KEY_HINTS):
        return False
    if _BASE64_IMAGE_RE.match(s):
        return True
    if _HEX_TEMPLATE_RE.match(s):
        return True
    return False


def walk_forbidden(obj: Any, *, path: str = "", key_hint: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = _norm_key(str(k))
            p = f"{path}.{k}" if path else str(k)
            if nk in BIOMETRIC_FORBIDDEN_KEYS:
                hits.append(p)
                continue
            if isinstance(v, str) and _looks_like_biometric_blob(v, key_hint=str(k)):
                hits.append(p)
                continue
            hits.extend(walk_forbidden(v, path=p, key_hint=str(k)))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(walk_forbidden(item, path=f"{path}[{i}]", key_hint=key_hint))
    elif _looks_like_biometric_blob(obj, key_hint=key_hint):
        hits.append(path or "<value>")
    return hits


def sanitize_vendor_payload(payload: dict[str, Any] | None) -> SanitizeResult:
    if payload is None:
        return SanitizeResult(ok=True, payload={})
    if not isinstance(payload, dict):
        return SanitizeResult(ok=False, reason="payload_not_object")
    hits = walk_forbidden(payload)
    if hits:
        return SanitizeResult(ok=False, reason="biometric_payload_forbidden", forbidden_keys=hits)
    clean = json.loads(json.dumps(payload, default=str))
    return SanitizeResult(ok=True, payload=clean)


def allowlisted_raw_ref(payload: dict[str, Any], allowed_keys: Iterable[str]) -> dict[str, Any]:
    allow = {str(k) for k in allowed_keys}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k not in allow:
            continue
        if isinstance(v, (dict, list)):
            continue
        if _looks_like_biometric_blob(v, key_hint=str(k)):
            continue
        out[k] = v
    return out


def validate_canonical_punch(punch: CanonicalPunch | dict[str, Any]) -> dict[str, Any]:
    data = punch.to_dict() if isinstance(punch, CanonicalPunch) else dict(punch)
    company = str(data.get("company_code") or "").upper().strip()
    source = str(data.get("source") or "").lower().strip()
    direction = str(data.get("direction") or "").lower().strip()
    method = str(data.get("capture_method") or "unknown").lower().strip()
    if method == "rfid":
        method = "card"
    errors: list[str] = []
    if not company:
        errors.append("missing_company_code")
    if source not in CAPTURE_SOURCES:
        errors.append("invalid_source")
    if not data.get("source_event_id"):
        errors.append("missing_source_event_id")
    if not str(data.get("device_user_id") or "").strip():
        errors.append("missing_device_user_id")
    if direction not in PUNCH_DIRECTIONS:
        errors.append("invalid_direction")
    if method not in CAPTURE_METHODS:
        errors.append("invalid_capture_method")
    punched_dt = as_kuwait(data.get("punched_at"))
    if punched_dt is None:
        errors.append("invalid_punched_at")
    san = sanitize_vendor_payload({"raw_ref": data.get("raw_ref") or {}, "metadata": data.get("metadata") or {}})
    if not san.ok:
        errors.append(san.reason or "biometric_payload_forbidden")
    if errors:
        return {"ok": False, "errors": errors, "forbidden_keys": san.forbidden_keys}
    return {
        "ok": True,
        "punch": {
            **data,
            "company_code": company,
            "source": source,
            "direction": direction,
            "capture_method": method,
            "punched_at": punched_dt.isoformat(),
            "device_user_id": str(data.get("device_user_id")).strip(),
            "source_event_id": str(data.get("source_event_id")).strip(),
            "connector_version": data.get("connector_version") or CONNECTOR_VERSION,
        },
    }


def stable_hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def biotime_source_event_id(transaction_id: Any, *, fallback_parts: tuple[Any, ...] = ()) -> str:
    if transaction_id is not None and str(transaction_id).strip():
        return f"biotime:{transaction_id}"
    return f"biotime:hash:{stable_hash(*fallback_parts)[:32]}"


def csv_source_event_id(file_sha256: str, row_sha256: str) -> str:
    return f"csv:{file_sha256}:{row_sha256}"


def sftp_source_event_id(file_sha256: str, row_sha256: str) -> str:
    return f"sftp:{file_sha256}:{row_sha256}"


@dataclass
class MappingRecord:
    company_code: str
    device_user_id: str
    employee_key: str
    device_id: str | None = None
    active: bool = True


@dataclass
class QuarantineRecord:
    quarantine_id: str
    company_code: str
    connector_id: str
    reason: str
    device_user_id: str | None
    device_id: str | None
    source: str
    source_event_id: str
    payload: dict[str, Any]
    created_at: str
    resolved: bool = False
    resolved_employee_key: str | None = None


class InMemoryMappingStore:
    """Device/user → employee mapping with quarantine (never auto-creates employees)."""

    def __init__(self) -> None:
        self._maps: dict[tuple[str, str, str], MappingRecord] = {}
        self._quarantine: dict[str, QuarantineRecord] = {}

    def upsert_mapping(
        self,
        *,
        company_code: str,
        device_user_id: str,
        employee_key: str,
        device_id: str | None = None,
    ) -> MappingRecord:
        company = company_code.upper()
        rec = MappingRecord(
            company_code=company,
            device_user_id=str(device_user_id).strip(),
            employee_key=str(employee_key).strip(),
            device_id=device_id,
            active=True,
        )
        self._maps[(company, rec.device_user_id, device_id or "")] = rec
        self._maps[(company, rec.device_user_id, "")] = rec
        return rec

    def resolve(self, *, company_code: str, device_user_id: str, device_id: str | None = None) -> MappingRecord | None:
        company = company_code.upper()
        uid = str(device_user_id).strip()
        for key in ((company, uid, device_id or ""), (company, uid, "")):
            rec = self._maps.get(key)
            if rec and rec.active:
                return rec
        return None

    def quarantine(
        self,
        *,
        company_code: str,
        connector_id: str,
        reason: str,
        source: str,
        source_event_id: str,
        payload: dict[str, Any],
        device_user_id: str | None = None,
        device_id: str | None = None,
    ) -> QuarantineRecord:
        qid = str(uuid.uuid4())
        rec = QuarantineRecord(
            quarantine_id=qid,
            company_code=company_code.upper(),
            connector_id=connector_id,
            reason=reason,
            device_user_id=device_user_id,
            device_id=device_id,
            source=source,
            source_event_id=source_event_id,
            payload=payload,
            created_at=datetime.now(tz=KUWAIT_TZ).isoformat(),
        )
        self._quarantine[qid] = rec
        return rec

    def list_open_quarantine(self, company_code: str) -> list[QuarantineRecord]:
        company = company_code.upper()
        return [q for q in self._quarantine.values() if q.company_code == company and not q.resolved]

    def resolve_quarantine(self, quarantine_id: str, *, employee_key: str) -> QuarantineRecord | None:
        q = self._quarantine.get(quarantine_id)
        if not q or q.resolved or not q.device_user_id:
            return None
        self.upsert_mapping(
            company_code=q.company_code,
            device_user_id=q.device_user_id,
            employee_key=employee_key,
            device_id=q.device_id,
        )
        q.resolved = True
        q.resolved_employee_key = employee_key
        return q


@dataclass
class ConnectorHealth:
    connector_id: str
    connector_version: str
    company_code: str
    status: str
    last_sync_at: str | None = None
    last_success_at: str | None = None
    lag_seconds: float | None = None
    events_in_window: int = 0
    error_count: int = 0
    last_error: str | None = None
    checkpoint: str | None = None
    auth_expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BIOTIME_TRANSACTION_ALLOWLIST = frozenset({
    "id",
    "emp_code",
    "punch_time",
    "punch_state",
    "verify_type",
    "work_code",
    "terminal_sn",
    "terminal_alias",
    "area_alias",
    "longitude",
    "latitude",
    "gps_location",
    "mobile",
})

BIOTIME_VERIFY_TO_CAPTURE = {
    0: "pin",
    1: "biometric",
    2: "card",
    3: "pin",
    4: "card",
    15: "face",
    25: "biometric",
}

_VERIFY_ALIAS = {
    "password": "pin",
    "fingerprint": "biometric",
    "finger": "biometric",
    "fp": "biometric",
    "palm": "biometric",
    "rfid": "card",
    "badge": "card",
}


def normalize_capture_method(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, int):
        value = BIOTIME_VERIFY_TO_CAPTURE.get(value, "unknown")
    text = str(value).strip().lower()
    text = _VERIFY_ALIAS.get(text, text)
    if text == "rfid":
        text = "card"
    if text in CAPTURE_METHODS:
        return text
    return "unknown"


def biotime_punch_state_to_direction(punch_state: Any, *, mapping: dict[str, str] | None = None) -> str | None:
    table = {
        "0": "in",
        "1": "out",
        "2": "break_start",
        "3": "break_end",
        "4": "in",
        "5": "out",
        "check_in": "in",
        "check_out": "out",
        "in": "in",
        "out": "out",
        "break_start": "break_start",
        "break_end": "break_end",
    }
    if mapping:
        table.update({str(k).lower(): str(v).lower() for k, v in mapping.items()})
    key = str(punch_state if punch_state is not None else "").strip().lower()
    direction = table.get(key)
    if direction in PUNCH_DIRECTIONS:
        return direction
    return None
