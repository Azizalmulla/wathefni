"""R8 — structured, redacted observability.

Preserves the R2 `safe_detail` secrets contract. Adds phone/email redaction
for log lines and client crash ingest. Does not invent a second audit system.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import security_rate_limit as _rl

logger = logging.getLogger("wathefni.observability")

CONTRACT_VERSION = "r8-delivery-safety-v1"
ERROR_TABLE = "wathefni_error_events"

_PHONE_RE = re.compile(r"\+\d[\d\s-]{6,16}\d|(?<![\w-])\d{8,15}(?![\w-])")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_SKIP_TEXT_REDACT_KEYS = {"event_id", "contract", "surface", "severity"}
_ALLOWED_SURFACES = {
    "backend",
    "hr_web",
    "setup_console",
    "hr_mobile",
    "employee_mobile",
}


def redact_text(value: str, *, limit: int = 500) -> str:
    text = str(value or "")
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _PHONE_RE.sub("[redacted-phone]", text)
    return text[:limit]


def redact_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    """R2 secret redaction, then phone/email scrub of remaining strings."""
    clean = _rl.safe_detail(detail)
    out: dict[str, Any] = {}
    for key, value in clean.items():
        if key in _SKIP_TEXT_REDACT_KEYS:
            out[key] = value
        elif isinstance(value, str):
            out[key] = redact_text(value, limit=800)
        elif isinstance(value, dict):
            out[key] = redact_detail(value)
        else:
            out[key] = value
    return out


def structured_log(level: str, event: str, **fields: Any) -> None:
    fields.pop("level", None)
    fields.pop("event", None)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "contract": CONTRACT_VERSION,
        "severity": level if level in {"debug", "info", "warning", "error"} else "info",
        **redact_detail(fields),
    }
    line = json.dumps(payload, default=str, separators=(",", ":"))
    log = getattr(logger, level if level in {"debug", "info", "warning", "error"} else "info")
    log(line)


def normalize_surface(value: str) -> str:
    surface = str(value or "").strip().lower().replace("-", "_")
    return surface if surface in _ALLOWED_SURFACES else "backend"


def record_error_event(
    app_mod: Any,
    *,
    surface: str,
    message: str,
    detail: dict[str, Any] | None = None,
    level: str = "error",
) -> dict[str, Any]:
    event = {
        "event_id": str(uuid.uuid4()),
        "surface": normalize_surface(surface),
        "level": "error" if level not in {"error", "warning"} else level,
        "message": redact_text(message, limit=400),
        "detail": redact_detail(detail),
    }
    structured_log(event["level"], "client_or_server_error", **{key: value for key, value in event.items() if key != "level"})
    stored = False
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {ERROR_TABLE} (event_id, surface, level, message, detail)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        event["event_id"],
                        event["surface"],
                        event["level"],
                        event["message"],
                        json.dumps(event["detail"], default=str),
                    ),
                )
            conn.commit()
            stored = True
    except Exception:
        structured_log("warning", "error_event_persist_failed", surface=event["surface"])
    event["stored"] = stored
    return event


def recent_error_count(app_mod: Any, *, hours: int = 24) -> int:
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM {ERROR_TABLE}
                    WHERE created_at >= now() - (%s || ' hours')::interval
                    """,
                    (str(int(hours)),),
                )
                row = cur.fetchone() or {}
                return int(row["n"] if isinstance(row, dict) else row[0] or 0)
    except Exception:
        return 0


def failed_job_visibility(app_mod: Any) -> dict[str, Any]:
    """Counts known failed-job tables. Missing tables are omitted, not invented."""
    queries = (
        (
            "intake_processing_jobs",
            "SELECT COUNT(*) FROM intake_processing_jobs WHERE status IN ('failed', 'terminal_failed', 'storage_failed')",
        ),
        (
            "migration_chunk_jobs",
            "SELECT COUNT(*) FROM migration_chunk_jobs WHERE status IN ('failed', 'error')",
        ),
    )
    sources: dict[str, int] = {}
    for name, sql in queries:
        try:
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    row = cur.fetchone() or {}
                    if isinstance(row, dict):
                        sources[name] = int(row.get("count") or row.get("n") or next(iter(row.values()), 0) or 0)
                    else:
                        sources[name] = int(row[0] or 0)
        except Exception:
            continue
    return {"sources": sources, "total": sum(sources.values())}


def delivery_snapshot(app_mod: Any) -> dict[str, Any]:
    import migration_framework as migrations

    return {
        "contract": CONTRACT_VERSION,
        "recent_error_events_24h": recent_error_count(app_mod),
        "failed_jobs": failed_job_visibility(app_mod),
        "migrations": migrations.readiness_snapshot(app_mod),
    }
