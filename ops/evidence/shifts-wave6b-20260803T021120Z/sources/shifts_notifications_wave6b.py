"""Shifts Wave 6B — channel-agnostic notification outbox (synthetic / mock only).

Canonical schedule + acknowledgement authority remains Wathefni.
One business event → many channel delivery attempts; no duplicate business notifications.
Real provider sends are NEVER performed in Wave 6B — mock adapters only.

Does NOT: send real WhatsApp/Teams/Telegram/email/SMS, enable real reminders/timers,
populate allowlists, PAM submit, or Payroll money.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SHIFTS_NOTIFICATIONS_WAVE6B_VERSION = "6.1.0"
JOB_LOCK_NOTIFY_BASE = 770_700_001

EVENT_TYPES = frozenset({
    "schedule_published",
    "shift_assigned",
    "shift_changed",
    "shift_cancelled",
    "upcoming_shift_reminder",
    "open_shift_available",
    "open_shift_claim_approved",
    "open_shift_claim_rejected",
    "swap_requested",
    "swap_approved",
    "swap_rejected",
    "acknowledgement_required",
})

CHANNELS = ("app", "push", "whatsapp", "teams", "telegram", "email", "sms", "web", "connector")

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "shifts_notifications_wave6b_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""

# In-process mock provider ledger (tests / canary). Never contacts external networks.
_MOCK_SENT: list[dict[str, Any]] = []
_MOCK_UNSUPPORTED: set[str] = set()
_MOCK_FAIL_ONCE: set[str] = set()  # "channel:dedupe" → fail first attempt then succeed


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name, default) or default
    return tuple(x.strip() for x in str(raw).split(",") if x.strip())


def _is_production() -> bool:
    return str(os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"


def shifts_notifications_wave6b_enabled() -> bool:
    return _env_bool("WATHEFNI_SHIFTS_NOTIFICATIONS_WAVE6B", default=not _is_production())


def shifts_notifications_wave6b_companies() -> set[str]:
    return {c.upper() for c in _env_csv("WATHEFNI_SHIFTS_NOTIFICATIONS_WAVE6B_COMPANIES", "WATHEFNI")}


def shifts_notifications_wave6b_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_notifications_wave6b_enabled():
        return False
    companies = shifts_notifications_wave6b_companies()
    if not companies:
        return True
    return (company_code or "").upper() in companies


def real_delivery_blocked() -> bool:
    """Wave 6B always blocks real provider sends unless explicitly overridden (never in canary)."""
    return _env_bool("WATHEFNI_SHIFTS_NOTIFICATIONS_REAL_DELIVERY", default=False) is False


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_notifications_wave6b_version": SHIFTS_NOTIFICATIONS_WAVE6B_VERSION,
        "multi_channel_outbox": True,
        "real_provider_delivery": False,
        "mock_adapters_only": True,
        "channels": list(CHANNELS),
        "event_types": sorted(EVENT_TYPES),
        "payroll_money": False,
        "pam_submission": False,
        "acknowledgement_authority": "wathefni",
        "drafts_do_not_notify": True,
    }


def reset_mock_ledger() -> None:
    _MOCK_SENT.clear()
    _MOCK_UNSUPPORTED.clear()
    _MOCK_FAIL_ONCE.clear()


def mock_mark_unsupported(channel: str) -> None:
    _MOCK_UNSUPPORTED.add(str(channel).strip().lower())


def mock_fail_once(channel: str, dedupe_key: str) -> None:
    _MOCK_FAIL_ONCE.add(f"{channel}:{dedupe_key}")


def mock_sent_ledger() -> list[dict[str, Any]]:
    return list(_MOCK_SENT)


def ensure_shifts_notifications_wave6b_schema(cur: Any) -> None:
    lock_id = JOB_LOCK_NOTIFY_BASE - 7
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        if SCHEMA_SQL.strip():
            cur.execute(SCHEMA_SQL)
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    fetched = cur.fetchall() or []
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in fetched]


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, (datetime, uuid.UUID)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    return obj


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def upsert_channel_preferences(
    cur: Any,
    *,
    company_code: str,
    scope_type: str = "company",
    scope_key: str = "*",
    channel_order: list[str] | None = None,
    enabled_channels: list[str] | None = None,
    fallback_enabled: bool = True,
) -> dict[str, Any]:
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    if not shifts_notifications_wave6b_enabled_for_company(company):
        return {"ok": False, "error": "shifts_notifications_wave6b_disabled", **honesty_payload()}
    order = [c for c in (channel_order or list(CHANNELS[:4])) if c in CHANNELS]
    enabled = [c for c in (enabled_channels or list(CHANNELS)) if c in CHANNELS]
    if not order:
        return {"ok": False, "error": "empty_channel_order"}
    cur.execute(
        """
        INSERT INTO shift_channel_preferences (
          company_code, scope_type, scope_key, channel_order, fallback_enabled, enabled_channels
        ) VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb)
        ON CONFLICT (company_code, scope_type, scope_key) DO UPDATE SET
          channel_order=EXCLUDED.channel_order,
          fallback_enabled=EXCLUDED.fallback_enabled,
          enabled_channels=EXCLUDED.enabled_channels,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            scope_type if scope_type in {"company", "employee"} else "company",
            scope_key or "*",
            json.dumps(order),
            bool(fallback_enabled),
            json.dumps(enabled),
        ),
    )
    return {"ok": True, "preference": _row(cur), **honesty_payload()}


def resolve_channel_plan(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
) -> dict[str, Any]:
    """Employee prefs override company prefs; defaults to app-first ladder."""
    company = (company_code or "").upper()
    ensure_shifts_notifications_wave6b_schema(cur)
    pref = None
    if employee_key:
        cur.execute(
            """
            SELECT * FROM shift_channel_preferences
            WHERE company_code=%s AND scope_type='employee' AND scope_key=%s
            """,
            (company, employee_key),
        )
        pref = _row(cur)
    if not pref:
        cur.execute(
            """
            SELECT * FROM shift_channel_preferences
            WHERE company_code=%s AND scope_type='company' AND scope_key='*'
            """,
            (company,),
        )
        pref = _row(cur)
    if not pref:
        return {
            "channel_order": ["app", "push", "whatsapp", "email"],
            "fallback_enabled": True,
            "enabled_channels": list(CHANNELS),
            "source": "default_app_first",
        }
    order = pref.get("channel_order") or []
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except Exception:
            order = ["app", "push", "whatsapp", "email"]
    enabled = pref.get("enabled_channels") or list(CHANNELS)
    if isinstance(enabled, str):
        try:
            enabled = json.loads(enabled)
        except Exception:
            enabled = list(CHANNELS)
    return {
        "channel_order": [c for c in order if c in CHANNELS],
        "fallback_enabled": bool(pref.get("fallback_enabled", True)),
        "enabled_channels": [c for c in enabled if c in CHANNELS],
        "source": f"{pref.get('scope_type')}:{pref.get('scope_key')}",
    }


def _mock_send(channel: str, *, dedupe_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    ch = str(channel).lower()
    correlation = f"mock|{ch}|{uuid.uuid4().hex[:12]}"
    if ch in _MOCK_UNSUPPORTED:
        return {
            "ok": False,
            "status": "unsupported",
            "error_code": "channel_unsupported",
            "error_detail": f"Mock adapter marks {ch} unavailable",
            "provider": "mock",
            "correlation_id": correlation,
            "real_sent": False,
        }
    fail_key = f"{ch}:{dedupe_key}"
    if fail_key in _MOCK_FAIL_ONCE:
        _MOCK_FAIL_ONCE.discard(fail_key)
        return {
            "ok": False,
            "status": "failed",
            "error_code": "mock_transient",
            "error_detail": "Mock transient failure (retry expected)",
            "provider": "mock",
            "correlation_id": correlation,
            "real_sent": False,
        }
    entry = {
        "channel": ch,
        "dedupe_key": dedupe_key,
        "correlation_id": correlation,
        "provider_message_id": f"mock-msg-{uuid.uuid4().hex[:10]}",
        "payload_fingerprint": hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16],
        "real_sent": False,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _MOCK_SENT.append(entry)
    return {
        "ok": True,
        "status": "delivered",
        "provider": "mock",
        "provider_message_id": entry["provider_message_id"],
        "correlation_id": correlation,
        "real_sent": False,
    }


def emit_notification_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    employee_key: str,
    payload: dict[str, Any] | None = None,
    employee_phone: str | None = None,
    employee_name: str | None = None,
    shift_id: Any = None,
    schedule_period_id: Any = None,
    schedule_version_id: Any = None,
    open_shift_id: Any = None,
    requires_ack: bool = False,
    dedupe_key: str | None = None,
    from_draft: bool = False,
) -> dict[str, Any]:
    """Create one canonical notification event (deduped). Drafts never notify."""
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    if not shifts_notifications_wave6b_enabled_for_company(company):
        return {"ok": False, "error": "shifts_notifications_wave6b_disabled", **honesty_payload()}
    if from_draft:
        return {"ok": False, "error": "drafts_do_not_notify", "suppressed": True, **honesty_payload()}
    et = str(event_type or "").strip()
    if et not in EVENT_TYPES:
        return {"ok": False, "error": "invalid_event_type", "event_type": et}
    ek = str(employee_key or "").strip()
    if not ek:
        return {"ok": False, "error": "employee_key_required"}
    # Tenant isolation: employee_key must belong to company when resolvable
    cur.execute(
        "SELECT company_code FROM employees WHERE employee_key=%s LIMIT 1",
        (ek,),
    )
    emp_row = _row(cur)
    if emp_row and str(emp_row.get("company_code") or "").upper() != company:
        return {"ok": False, "error": "tenant_isolation_violation", **honesty_payload()}

    body = payload or {}
    dedupe = dedupe_key or f"{et}|{company}|{ek}|{shift_id or ''}|{schedule_version_id or ''}|{body.get('occurrence_key') or ''}"
    cur.execute(
        """
        INSERT INTO shift_notification_events (
          company_code, event_type, employee_key, employee_phone, employee_name,
          shift_id, schedule_period_id, schedule_version_id, open_shift_id,
          dedupe_key, payload, status, requires_ack
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'pending',%s)
        ON CONFLICT (company_code, dedupe_key) DO NOTHING
        RETURNING *
        """,
        (
            company,
            et,
            ek,
            _digits(employee_phone) or None,
            employee_name,
            str(shift_id) if shift_id else None,
            str(schedule_period_id) if schedule_period_id else None,
            str(schedule_version_id) if schedule_version_id else None,
            str(open_shift_id) if open_shift_id else None,
            dedupe,
            json.dumps(_jsonable(body)),
            bool(requires_ack),
        ),
    )
    event = _row(cur)
    if not event:
        cur.execute(
            "SELECT * FROM shift_notification_events WHERE company_code=%s AND dedupe_key=%s",
            (company, dedupe),
        )
        event = _row(cur)
        return {
            "ok": True,
            "duplicate_suppressed": True,
            "event": event,
            **honesty_payload(),
        }
    return {"ok": True, "duplicate_suppressed": False, "event": event, **honesty_payload()}


def process_event_deliveries(
    cur: Any,
    *,
    company_code: str,
    event_id: Any,
    stop_on_first_success: bool | None = None,
) -> dict[str, Any]:
    """Attempt channel ladder with mock adapters. Never sends real provider traffic."""
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    if not real_delivery_blocked():
        # Safety: Wave 6B canary must keep real delivery blocked
        return {"ok": False, "error": "real_delivery_not_allowed_in_wave6b", **honesty_payload()}

    cur.execute(
        "SELECT * FROM shift_notification_events WHERE company_code=%s AND event_id=%s FOR UPDATE",
        (company, str(event_id)),
    )
    event = _row(cur)
    if not event:
        return {"ok": False, "error": "event_not_found"}
    if str(event.get("status")) in {"acked", "invalidated", "suppressed"}:
        return {"ok": True, "skipped": True, "event": event, "deliveries": [], **honesty_payload()}

    plan = resolve_channel_plan(cur, company_code=company, employee_key=event.get("employee_key"))
    order = [c for c in plan["channel_order"] if c in plan["enabled_channels"]]
    fallback = bool(plan.get("fallback_enabled", True))
    stop_first = fallback if stop_on_first_success is None else bool(stop_on_first_success)

    cur.execute(
        "UPDATE shift_notification_events SET status='delivering', updated_at=now() WHERE event_id=%s",
        (event["event_id"],),
    )

    deliveries: list[dict[str, Any]] = []
    any_delivered = False
    for channel in order:
        cur.execute(
            "SELECT coalesce(max(attempt_no),0) AS m FROM shift_notification_deliveries WHERE event_id=%s AND channel=%s",
            (event["event_id"], channel),
        )
        attempt = int((_row(cur) or {}).get("m") or 0) + 1
        result = _mock_send(channel, dedupe_key=str(event.get("dedupe_key")), payload=event.get("payload") or {})
        status = result.get("status") or ("delivered" if result.get("ok") else "failed")
        cur.execute(
            """
            INSERT INTO shift_notification_deliveries (
              company_code, event_id, channel, attempt_no, status, provider,
              provider_message_id, correlation_id, error_code, error_detail, delivered_at,
              next_retry_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                company,
                event["event_id"],
                channel,
                attempt,
                status,
                result.get("provider") or "mock",
                result.get("provider_message_id"),
                result.get("correlation_id"),
                result.get("error_code"),
                result.get("error_detail"),
                datetime.now(timezone.utc) if result.get("ok") else None,
                (datetime.now(timezone.utc) + timedelta(minutes=5)) if status == "failed" else None,
            ),
        )
        row = _row(cur)
        deliveries.append(row or {})
        if result.get("ok"):
            any_delivered = True
            if stop_first:
                break

    new_status = "delivered" if any_delivered else "failed"
    cur.execute(
        "UPDATE shift_notification_events SET status=%s, updated_at=now() WHERE event_id=%s RETURNING *",
        (new_status, event["event_id"]),
    )
    event = _row(cur)
    return {
        "ok": True,
        "event": event,
        "deliveries": deliveries,
        "any_delivered": any_delivered,
        "channel_plan": plan,
        "real_sent": False,
        **honesty_payload(),
    }


def retry_failed_deliveries(
    cur: Any,
    *,
    company_code: str,
    event_id: Any,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Retry failed channels; escalate to terminal_failed after max_attempts."""
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT * FROM shift_notification_deliveries
        WHERE company_code=%s AND event_id=%s AND status IN ('failed','queued')
        ORDER BY channel, attempt_no
        """,
        (company, str(event_id)),
    )
    failed = _rows(cur)
    if not failed:
        return {"ok": True, "retried": 0, "terminal": [], **honesty_payload()}

    cur.execute("SELECT * FROM shift_notification_events WHERE event_id=%s", (str(event_id),))
    event = _row(cur)
    if not event:
        return {"ok": False, "error": "event_not_found"}

    retried = 0
    terminal: list[dict[str, Any]] = []
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for d in failed:
        by_channel.setdefault(str(d.get("channel")), []).append(d)

    for channel, attempts in by_channel.items():
        last = max(attempts, key=lambda x: int(x.get("attempt_no") or 0))
        n = int(last.get("attempt_no") or 0)
        if n >= max_attempts:
            cur.execute(
                """
                UPDATE shift_notification_deliveries SET
                  status='terminal_failed', error_code=coalesce(error_code,'max_attempts'),
                  updated_at=now()
                WHERE delivery_id=%s
                RETURNING *
                """,
                (last["delivery_id"],),
            )
            terminal.append(_row(cur) or {})
            continue
        result = _mock_send(channel, dedupe_key=str(event.get("dedupe_key")), payload=event.get("payload") or {})
        status = result.get("status") or ("delivered" if result.get("ok") else "failed")
        if not result.get("ok") and (n + 1) >= max_attempts:
            status = "terminal_failed"
        cur.execute(
            """
            INSERT INTO shift_notification_deliveries (
              company_code, event_id, channel, attempt_no, status, provider,
              provider_message_id, correlation_id, error_code, error_detail, delivered_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                company,
                event["event_id"],
                channel,
                n + 1,
                status,
                "mock",
                result.get("provider_message_id"),
                result.get("correlation_id"),
                result.get("error_code"),
                result.get("error_detail"),
                datetime.now(timezone.utc) if result.get("ok") else None,
            ),
        )
        retried += 1
        if status == "terminal_failed":
            terminal.append(_row(cur) or {})
        elif result.get("ok"):
            cur.execute(
                "UPDATE shift_notification_events SET status='delivered', updated_at=now() WHERE event_id=%s",
                (event["event_id"],),
            )

    if terminal and not any(str(t.get("status")) == "delivered" for t in terminal):
        # Mark event failed if all channels terminal and none delivered overall
        cur.execute(
            """
            SELECT count(*) AS c FROM shift_notification_deliveries
            WHERE event_id=%s AND status IN ('delivered','sent')
            """,
            (event["event_id"],),
        )
        ok_count = int((_row(cur) or {}).get("c") or 0)
        if ok_count == 0:
            cur.execute(
                "UPDATE shift_notification_events SET status='failed', updated_at=now() WHERE event_id=%s",
                (event["event_id"],),
            )

    return {"ok": True, "retried": retried, "terminal": terminal, **honesty_payload()}


def acknowledge_event(
    cur: Any,
    *,
    company_code: str,
    event_id: Any,
    channel: str,
    actor_phone: str | None = None,
    actor_employee_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record acknowledgement once — subsequent acks from other channels are no-ops."""
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    ch = str(channel or "app").lower()
    if ch not in CHANNELS:
        return {"ok": False, "error": "invalid_channel"}
    cur.execute(
        "SELECT * FROM shift_notification_events WHERE company_code=%s AND event_id=%s FOR UPDATE",
        (company, str(event_id)),
    )
    event = _row(cur)
    if not event:
        return {"ok": False, "error": "event_not_found"}
    if str(event.get("status")) == "acked":
        cur.execute("SELECT * FROM shift_notification_acks WHERE event_id=%s", (event["event_id"],))
        return {"ok": True, "already_acked": True, "ack": _row(cur), "event": event, **honesty_payload()}

    cur.execute(
        """
        INSERT INTO shift_notification_acks (company_code, event_id, channel, actor_phone, actor_employee_key, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING *
        """,
        (
            company,
            event["event_id"],
            ch,
            _digits(actor_phone) or None,
            actor_employee_key,
            json.dumps(_jsonable(payload or {})),
        ),
    )
    ack = _row(cur)
    if not ack:
        cur.execute("SELECT * FROM shift_notification_acks WHERE event_id=%s", (event["event_id"],))
        ack = _row(cur)
        return {"ok": True, "already_acked": True, "ack": ack, **honesty_payload()}

    cur.execute(
        """
        UPDATE shift_notification_events SET
          status='acked', acked_at=now(), acked_via_channel=%s, updated_at=now()
        WHERE event_id=%s
        RETURNING *
        """,
        (ch, event["event_id"]),
    )
    event = _row(cur)
    return {"ok": True, "already_acked": False, "ack": ack, "event": event, **honesty_payload()}


def invalidate_notifications_for_shift(
    cur: Any,
    *,
    company_code: str,
    shift_id: Any,
    reason: str = "shift_cancelled_or_rescheduled",
) -> dict[str, Any]:
    """Invalidate pending reminders/notifications when a shift is cancelled/rescheduled."""
    ensure_shifts_notifications_wave6b_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE shift_notification_events SET
          status='invalidated', invalidated_at=now(), invalidate_reason=%s, updated_at=now()
        WHERE company_code=%s AND shift_id=%s
          AND status IN ('pending','delivering','delivered','failed')
          AND event_type IN ('upcoming_shift_reminder','shift_assigned','shift_changed','acknowledgement_required')
        RETURNING event_id
        """,
        (reason, company, str(shift_id)),
    )
    ids = [str(r.get("event_id")) for r in _rows(cur)]
    return {"ok": True, "invalidated": len(ids), "event_ids": ids, **honesty_payload()}


def list_events(cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    if employee_key:
        cur.execute(
            """
            SELECT * FROM shift_notification_events
            WHERE company_code=%s AND employee_key=%s
            ORDER BY created_at DESC LIMIT %s
            """,
            (company, employee_key, max(1, min(200, int(limit)))),
        )
    else:
        cur.execute(
            """
            SELECT * FROM shift_notification_events
            WHERE company_code=%s
            ORDER BY created_at DESC LIMIT %s
            """,
            (company, max(1, min(200, int(limit)))),
        )
    return _rows(cur)


def list_deliveries(cur: Any, *, company_code: str, event_id: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_notification_deliveries
        WHERE company_code=%s AND event_id=%s
        ORDER BY channel, attempt_no
        """,
        ((company_code or "").upper(), str(event_id)),
    )
    return _rows(cur)
