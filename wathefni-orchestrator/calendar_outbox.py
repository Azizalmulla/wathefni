"""Wathefni Calendar C2 — durable calendar_link_outbox enqueue + worker.

Transactional-outbox guarantee (C2 durability amendment):
- Interview mutation + required outbox INSERT commit atomically in one DB transaction.
- Calendar *processing* is async (worker) and must never be required inside that TX.
- Worker failure must not undo Interview truth.
- Outbox INSERT failure must roll back the Interview mutation (never silently commit without intent).
- Duplicate idempotency_key is idempotent success.

Module-disabled policy (LOCKED): ``always_enqueue_defer_until_enabled``
- Always enqueue for live timed Interview ops that require Calendar sync.
- Worker defers processing until the calendar module is enabled.
- Backfill remains authoritative for pre-C2 / historical gaps when enabling Calendar later.
"""

from __future__ import annotations

import os
import socket
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

import calendar_interview_link as cil
import calendar_schema

SOURCE_WORKFLOW = "interview"
OPERATIONS = frozenset({"ensure", "cancel", "complete", "sync_attendees"})
MAX_ATTEMPTS = int(os.environ.get("CALENDAR_OUTBOX_MAX_ATTEMPTS", "8") or 8)
LEASE_SECONDS = int(os.environ.get("CALENDAR_OUTBOX_LEASE_SECONDS", "120") or 120)
MODULE_DISABLED_DELAY_SECONDS = int(os.environ.get("CALENDAR_OUTBOX_MODULE_DISABLED_DELAY", "1800") or 1800)
MODULE_DISABLED_POLICY = "always_enqueue_defer_until_enabled"


class CalendarOutboxError(Exception):
    """Required Calendar outbox intent could not be recorded — caller must roll back Interview TX."""

    def __init__(self, code: str, message: str, *, retryable: bool = True, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})

    def as_detail(self) -> dict[str, Any]:
        out = {
            "error": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "safe_next_action": "retry",
        }
        out.update(self.details)
        return out


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def idempotency_key(*, interview_id: str, operation: str, operation_token: str) -> str:
    return f"interview:{_text(interview_id)}:{_text(operation)}:{_text(operation_token)}"


def backoff_seconds(attempt_count: int) -> int:
    # 30s, 60s, 2m, 5m, 15m, 30m, 1h, 2h …
    ladder = [30, 60, 120, 300, 900, 1800, 3600, 7200]
    idx = max(0, min(int(attempt_count) - 1, len(ladder) - 1))
    return ladder[idx]


def enqueue_interview_calendar_intent(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    interview_id: str,
    operation: str,
    operation_token: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Insert outbox row in the caller's transaction. Duplicate key → idempotent success."""
    company = _text(company_code).upper()
    iid = _text(interview_id)
    op = _text(operation).lower()
    token = _text(operation_token) or str(uuid4())
    if op not in OPERATIONS:
        raise CalendarOutboxError(
            "invalid_operation",
            f"Unsupported calendar outbox operation: {op}",
            retryable=False,
            details={"operation": op},
        )
    if not company or not iid:
        raise CalendarOutboxError(
            "scope_required",
            "company_code and interview_id are required for calendar outbox.",
            retryable=False,
        )

    key = idempotency_key(interview_id=iid, operation=op, operation_token=token)
    body = dict(payload or {})
    body.setdefault("interview_id", iid)
    body.setdefault("company_code", company)
    body.setdefault("operation", op)
    body.setdefault("schedule_operation_id", token)
    body.setdefault("module_disabled_policy", MODULE_DISABLED_POLICY)

    cur.execute("SAVEPOINT calendar_outbox_enqueue")
    try:
        cur.execute(
            """
            INSERT INTO calendar_link_outbox (
              outbox_id, company_code, source_workflow, source_record_id, operation,
              idempotency_key, payload, status, attempt_count, next_attempt_at
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,'pending',0,now()
            )
            RETURNING *
            """,
            (
                str(uuid4()),
                company,
                SOURCE_WORKFLOW,
                iid,
                op,
                key,
                _json(legacy, body),
            ),
        )
        row = dict(cur.fetchone() or {})
        cur.execute("RELEASE SAVEPOINT calendar_outbox_enqueue")
        return {"ok": True, "enqueued": True, "outbox_id": str(row.get("outbox_id")), "idempotency_key": key}
    except Exception as exc:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT calendar_outbox_enqueue")
        except Exception:
            pass
        # Unique violation → already enqueued for this operation token (idempotent success).
        cur.execute(
            """
            SELECT * FROM calendar_link_outbox
            WHERE company_code=%s AND idempotency_key=%s
            LIMIT 1
            """,
            (company, key),
        )
        existing = cur.fetchone()
        if existing:
            row = dict(existing)
            return {
                "ok": True,
                "enqueued": False,
                "idempotent_replay": True,
                "outbox_id": str(row.get("outbox_id")),
                "idempotency_key": key,
                "status": row.get("status"),
            }
        raise CalendarOutboxError(
            "calendar_outbox_enqueue_failed",
            "Could not record the durable calendar sync intent. Retry the interview action.",
            retryable=True,
            details={"detail": str(exc)[:400], "idempotency_key": key},
        ) from exc


def enqueue_from_interview(
    cur: Any,
    legacy: Any,
    *,
    interview: Mapping[str, Any],
    assignments: list[Mapping[str, Any]] | None,
    operation: str,
    operation_token: str | None = None,
) -> dict[str, Any]:
    """Build projection payload + enqueue. Skips async video for timed ensure/sync_attendees."""
    interview = dict(interview or {})
    company = _text(interview.get("company_code")).upper()
    iid = _text(interview.get("interview_id"))
    op = _text(operation).lower()

    if op in {"ensure", "sync_attendees"} and not cil.is_live_timed_interview(interview):
        return {"ok": True, "skipped": True, "reason": "not_live_timed_interview"}

    person_key = None
    try:
        person_key = cil.resolve_person_key(cur, company_code=company, app_key=_text(interview.get("app_key")))
    except Exception:
        person_key = None

    payload = cil.build_interview_projection_payload(
        interview,
        assignments=assignments or [],
        person_key=person_key,
        operation=op,
    )
    token = _text(operation_token) or _text(interview.get("schedule_operation_id")) or str(uuid4())
    return enqueue_interview_calendar_intent(
        cur,
        legacy,
        company_code=company,
        interview_id=iid,
        operation=op,
        operation_token=token,
        payload=payload,
    )


def require_enqueue_from_interview(
    cur: Any,
    legacy: Any,
    *,
    interview: Mapping[str, Any],
    assignments: list[Mapping[str, Any]] | None,
    operation: str,
    operation_token: str | None = None,
) -> dict[str, Any]:
    """Required Calendar intent for Interview TX.

    Success: newly enqueued, idempotent duplicate, or explicitly skipped (async timed ops).
    Failure: raises CalendarOutboxError — caller must not commit Interview mutation.
    """
    result = enqueue_from_interview(
        cur,
        legacy,
        interview=interview,
        assignments=assignments,
        operation=operation,
        operation_token=operation_token,
    )
    if result.get("ok"):
        return result
    raise CalendarOutboxError(
        _text(result.get("error")) or "calendar_outbox_enqueue_failed",
        "Could not record the durable calendar sync intent. Retry the interview action.",
        retryable=True,
        details=result,
    )


def reclaim_expired_leases(cur: Any) -> int:
    cur.execute(
        """
        UPDATE calendar_link_outbox
        SET status='pending',
            lease_owner=NULL,
            lease_expires_at=NULL,
            last_error=COALESCE(last_error, 'lease_expired'),
            updated_at=now(),
            next_attempt_at=now()
        WHERE status='processing'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at < now()
        RETURNING outbox_id
        """
    )
    return len(cur.fetchall() or [])


def claim_next_outbox(
    cur: Any,
    *,
    worker_id: str,
    company_code: str | None = None,
    lease_seconds: int = LEASE_SECONDS,
) -> dict[str, Any] | None:
    reclaim_expired_leases(cur)
    params: list[Any] = []
    company_sql = ""
    if company_code:
        company_sql = "AND company_code=%s"
        params.append(_text(company_code).upper())
    cur.execute(
        f"""
        SELECT *
        FROM calendar_link_outbox
        WHERE status IN ('pending','failed')
          AND (next_attempt_at IS NULL OR next_attempt_at <= now())
          {company_sql}
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
        """,
        tuple(params),
    )
    row = cur.fetchone()
    if not row:
        return None
    item = dict(row)
    lease_expires = datetime.now(timezone.utc) + timedelta(seconds=max(30, int(lease_seconds)))
    cur.execute(
        """
        UPDATE calendar_link_outbox
        SET status='processing',
            attempt_count=attempt_count+1,
            lease_owner=%s,
            lease_expires_at=%s,
            updated_at=now()
        WHERE outbox_id=%s
        RETURNING *
        """,
        (worker_id, lease_expires, item["outbox_id"]),
    )
    claimed = cur.fetchone()
    return dict(claimed) if claimed else None


def _module_enabled(legacy: Any, company: str) -> bool:
    checker = getattr(legacy, "company_has_module", None)
    if callable(checker):
        try:
            return bool(checker(company, "calendar"))
        except Exception:
            return False
    return False


def _mark(
    cur: Any,
    *,
    outbox_id: str,
    status: str,
    last_error: str | None = None,
    next_attempt_at: datetime | None = None,
    clear_lease: bool = True,
) -> None:
    cur.execute(
        """
        UPDATE calendar_link_outbox
        SET status=%s,
            last_error=%s,
            next_attempt_at=%s,
            processed_at=CASE WHEN %s='processed' THEN now() ELSE processed_at END,
            lease_owner=CASE WHEN %s THEN NULL ELSE lease_owner END,
            lease_expires_at=CASE WHEN %s THEN NULL ELSE lease_expires_at END,
            updated_at=now()
        WHERE outbox_id=%s
        """,
        (
            status,
            last_error,
            next_attempt_at,
            status,
            clear_lease,
            clear_lease,
            outbox_id,
        ),
    )


def process_outbox_item(legacy: Any, cur: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    company = _text(item.get("company_code")).upper()
    operation = _text(item.get("operation")).lower()
    interview_id = _text(item.get("source_record_id"))
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    outbox_id = str(item.get("outbox_id"))
    attempts = int(item.get("attempt_count") or 1)

    if not _module_enabled(legacy, company):
        _mark(
            cur,
            outbox_id=outbox_id,
            status="pending",
            last_error="module_disabled",
            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=MODULE_DISABLED_DELAY_SECONDS),
        )
        # Undo attempt bump for module-disabled deferrals
        cur.execute(
            "UPDATE calendar_link_outbox SET attempt_count=GREATEST(attempt_count-1,0) WHERE outbox_id=%s",
            (outbox_id,),
        )
        return {"ok": True, "deferred": True, "reason": "module_disabled"}

    try:
        if operation == "ensure":
            result = cil.ensure_calendar_event(legacy, cur, company_code=company, interview_id=interview_id, payload=payload)
        elif operation == "sync_attendees":
            result = cil.sync_interview_attendees(legacy, cur, company_code=company, interview_id=interview_id, payload=payload)
        elif operation == "cancel":
            result = cil.cancel_interview_calendar_event(legacy, cur, company_code=company, interview_id=interview_id, payload=payload)
        elif operation == "complete":
            result = cil.complete_interview_calendar_event(legacy, cur, company_code=company, interview_id=interview_id, payload=payload)
        else:
            result = {"ok": False, "error": "unknown_operation"}

        if result.get("ok"):
            _mark(cur, outbox_id=outbox_id, status="processed", last_error=None)
            return {"ok": True, "result": result}

        error = _text(result.get("error")) or "process_failed"
        if attempts >= MAX_ATTEMPTS:
            _mark(cur, outbox_id=outbox_id, status="dead", last_error=error)
        else:
            _mark(
                cur,
                outbox_id=outbox_id,
                status="failed",
                last_error=error,
                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds(attempts)),
            )
        return {"ok": False, "error": error, "result": result}
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:500]
        if attempts >= MAX_ATTEMPTS:
            _mark(cur, outbox_id=outbox_id, status="dead", last_error=detail)
        else:
            _mark(
                cur,
                outbox_id=outbox_id,
                status="failed",
                last_error=detail,
                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds(attempts)),
            )
        return {"ok": False, "error": detail, "traceback": traceback.format_exc()[-800:]}


def run_outbox_once(
    legacy: Any,
    *,
    limit: int = 25,
    company_code: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    worker = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    processed = 0
    deferred = 0
    failed = 0
    results: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
        conn.commit()

    for _ in range(max(1, min(int(limit), 200))):
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                item = claim_next_outbox(cur, worker_id=worker, company_code=company_code)
                if not item:
                    conn.commit()
                    break
                outcome = process_outbox_item(legacy, cur, item)
            conn.commit()
        if outcome.get("deferred"):
            deferred += 1
        elif outcome.get("ok"):
            processed += 1
        else:
            failed += 1
        results.append({"outbox_id": str(item.get("outbox_id")), **outcome})

    return {
        "ok": True,
        "worker_id": worker,
        "processed": processed,
        "deferred": deferred,
        "failed": failed,
        "results": results,
    }


def replay_outbox(
    legacy: Any,
    *,
    outbox_id: str | None = None,
    idempotency_key: str | None = None,
    company_code: str | None = None,
) -> dict[str, Any]:
    """Manual replay for failed/dead rows — resets to pending without duplicating keys."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            if outbox_id:
                cur.execute(
                    """
                    UPDATE calendar_link_outbox
                    SET status='pending', next_attempt_at=now(), lease_owner=NULL, lease_expires_at=NULL,
                        last_error=NULL, updated_at=now()
                    WHERE outbox_id=%s AND status IN ('failed','dead','pending')
                    RETURNING *
                    """,
                    (outbox_id,),
                )
            elif idempotency_key:
                cur.execute(
                    """
                    UPDATE calendar_link_outbox
                    SET status='pending', next_attempt_at=now(), lease_owner=NULL, lease_expires_at=NULL,
                        last_error=NULL, updated_at=now()
                    WHERE company_code=COALESCE(%s, company_code) AND idempotency_key=%s
                      AND status IN ('failed','dead','pending')
                    RETURNING *
                    """,
                    (_text(company_code).upper() or None, idempotency_key),
                )
            else:
                return {"ok": False, "error": "outbox_id_or_idempotency_key_required"}
            row = cur.fetchone()
        conn.commit()
    if not row:
        return {"ok": False, "error": "outbox_not_found"}
    return {"ok": True, "outbox": dict(row)}
