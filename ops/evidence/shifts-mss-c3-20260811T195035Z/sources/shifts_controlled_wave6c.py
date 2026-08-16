"""Shifts Wave 6C — controlled real rollout: named allowlists, real delivery, freeze posture.

Wave 6B proved the canonical notification outbox with mock adapters only. Wave 6C binds
that outbox to the production sender for a single approved recipient on a single approved
external channel, and adds the controlled-rollout guards the freeze depends on.

Layered fail-closed guards, all of which must pass before one real message leaves:
  1. Wave 6C enabled for the company
  2. global notification kill switch not engaged
  3. real delivery explicitly enabled
  4. recipient employee_key on the real-notify allowlist
  5. subject not on the controlled exclusion list (ORPHAN / probe residue)
  6. channel on the approved real-channel list
  7. recorded consent for that employee + channel

Does NOT: enable broad employee-app rollout, grant Talal HR/manager capability, submit to
PAM, mutate Payroll money, mutate Leave balances, mutate Attendance authority, or enable
scoped-manager real scheduling (no manager identity/scope exists in production).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

SHIFTS_WAVE6C_VERSION = "6.2.0"
CLEANUP_CONTRACT_MIN = "1.5.0"
JOB_LOCK_CONTROLLED_BASE = 770_800_001

_ON = {"1", "true", "yes", "on"}

# Wave 6C production controlled canary markers (synthetic subjects for the non-real paths).
DEFAULT_W6C_SYNTHETIC_KEY_MARKERS = ("SHW6C", "SHW6C-SYNTH|")
DEFAULT_W6C_SYNTHETIC_PHONE_PREFIXES = ("965538",)

# Channels permitted to carry a real Wave 6C message. `app` is the canonical in-product
# delivery; exactly one external channel is approved for the first canary (email).
DEFAULT_REAL_CHANNELS = ("app", "email")

# In-product channels do not leave the platform and therefore do not require an external
# consent record; every other channel does.
IN_PRODUCT_CHANNELS = frozenset({"app", "web"})

# Subjects that the synthetic detectors do not catch but which are NOT real people:
# Wave 1 orphan-quarantine residue and the deliberate real-denial probe employee.
DEFAULT_EXCLUDED_SUBJECT_PATTERNS = ("WATHEFNI-ORPHAN-", "-REALBLOCK-")

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "shifts_controlled_wave6c_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        raw = default
    return tuple(x.strip() for x in str(raw).split(",") if x.strip())


def _is_production() -> bool:
    return str(os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


# --------------------------------------------------------------------------- flags


def shifts_wave6c_enabled() -> bool:
    return _env_bool("WATHEFNI_SHIFTS_WAVE6C", default=not _is_production())


def shifts_wave6c_companies() -> set[str]:
    return {c.upper() for c in _env_csv("WATHEFNI_SHIFTS_WAVE6C_COMPANIES", "WATHEFNI")}


def shifts_wave6c_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave6c_enabled():
        return False
    companies = shifts_wave6c_companies()
    if not companies:
        return False
    return (company_code or "").upper() in companies


def notify_kill_switch_active() -> bool:
    """Operator kill switch — stops every Wave 6C delivery attempt immediately."""
    return _env_bool("WATHEFNI_SHIFTS_NOTIFY_KILL", default=False)


def real_delivery_enabled() -> bool:
    """Real provider sends. Fail-closed: must be explicitly turned on."""
    if notify_kill_switch_active():
        return False
    return _env_bool("WATHEFNI_SHIFTS_NOTIFY_REAL_DELIVERY", default=False)


def real_notify_allowlist() -> set[str]:
    """Employee keys approved to receive a real Shifts notification. Empty ⇒ nobody."""
    return {k for k in _env_csv("WATHEFNI_SHIFTS_NOTIFY_REAL_ALLOWLIST", "") if k}


def real_notify_channels() -> tuple[str, ...]:
    configured = _env_csv("WATHEFNI_SHIFTS_NOTIFY_REAL_CHANNELS", ",".join(DEFAULT_REAL_CHANNELS))
    return tuple(c.lower() for c in configured if c)


def excluded_subject_patterns() -> tuple[str, ...]:
    configured = _env_csv(
        "WATHEFNI_SHIFTS_EXCLUDED_SUBJECTS", ",".join(DEFAULT_EXCLUDED_SUBJECT_PATTERNS)
    )
    return configured or DEFAULT_EXCLUDED_SUBJECT_PATTERNS


def subject_excluded(employee_key: Any) -> bool:
    key = str(employee_key or "")
    if not key:
        return True
    return any(pattern and pattern in key for pattern in excluded_subject_patterns())


def manager_real_rollout_enabled() -> bool:
    """Scoped-manager real scheduling via the global Wave-3 MANAGER_ALLOWLIST.

    Hard NO-GO for the Wave 6C global boundary — keep returning False.
    Company-scoped MSS unlock is gated by `shifts_mss_c3` (Wave 2 C3), not this flag.
    """
    return False


def operator_timers_enabled() -> bool:
    """Systemd timers for reminder/reconciliation jobs. Off unless explicitly enabled."""
    return _env_bool("WATHEFNI_SHIFTS_OPERATOR_TIMERS", default=False)


# The only real-mutation actors any Wave may run under. Widening this set requires a new
# owner-approved wave, not an environment variable.
APPROVED_HR_OPERATORS = frozenset({"96599338566"})


def allowlists_within_approved_boundary() -> bool:
    """True while the real-mutation allowlists stay inside the approved rollout boundary.

    Legal postures:
      * pre-Wave-6C synthetic-only (both global allowlists empty)
      * Wave 6C controlled (HR ⊆ APPROVED_HR_OPERATORS, global manager allowlist empty)
      * Wave 2 C3 company-scoped MSS via WATHEFNI_SHIFTS_MSS_* (does not populate
        WATHEFNI_SHIFTS_MANAGER_ALLOWLIST)

    Any global manager phone, or an HR phone nobody approved, is out of boundary.
    """
    import shifts_wave3_controlled as _w3

    if _w3.manager_mutation_allowlist():
        return False
    return set(_w3.hr_mutation_allowlist()) <= set(APPROVED_HR_OPERATORS)


def authority_scope_within_approved_boundary() -> bool:
    """Wave 1 authority may leave synthetic-only mode only under the controlled posture."""
    import shifts_authority_wave1 as _w1

    if _w1.shifts_authority_synthetic_only():
        return True
    return shifts_wave6c_enabled_for_company("WATHEFNI") and allowlists_within_approved_boundary()


def controlled_jobs_enabled() -> bool:
    return _env_bool("WATHEFNI_SHIFTS_CONTROLLED_JOBS", default=False)


def wave6c_synthetic_key_markers() -> tuple[str, ...]:
    configured = _env_csv(
        "WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_KEY_MARKERS", ",".join(DEFAULT_W6C_SYNTHETIC_KEY_MARKERS)
    )
    return configured or DEFAULT_W6C_SYNTHETIC_KEY_MARKERS


def wave6c_synthetic_phone_prefixes() -> tuple[str, ...]:
    configured = _env_csv(
        "WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_PHONE_PREFIXES",
        ",".join(DEFAULT_W6C_SYNTHETIC_PHONE_PREFIXES),
    )
    return configured or DEFAULT_W6C_SYNTHETIC_PHONE_PREFIXES


def is_wave6c_synthetic_employee(
    *,
    employee_key: Any = None,
    phone: Any = None,
    employee: dict[str, Any] | None = None,
) -> bool:
    key = str(employee_key or (employee or {}).get("employee_key") or "")
    phone_digits = _digits(phone or (employee or {}).get("phone") or (employee or {}).get("employee_phone"))
    for marker in wave6c_synthetic_key_markers():
        if marker and marker in key:
            return True
    for prefix in wave6c_synthetic_phone_prefixes():
        if prefix and phone_digits.startswith(prefix):
            return True
    raw = (employee or {}).get("raw_json") if isinstance(employee, dict) else None
    if isinstance(raw, dict) and (raw.get("shw6c") is True or str(raw.get("shw6c") or "").lower() in _ON):
        return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave6c_version": SHIFTS_WAVE6C_VERSION,
        "controlled_real_rollout": True,
        "real_delivery_enabled": real_delivery_enabled(),
        "notify_kill_switch": notify_kill_switch_active(),
        "real_notify_recipients": sorted(real_notify_allowlist()),
        "real_notify_channels": list(real_notify_channels()),
        "excluded_subject_patterns": list(excluded_subject_patterns()),
        "manager_real_rollout": manager_real_rollout_enabled(),
        "broad_employee_app": False,
        "talal_read_and_ack_only": True,
        "operator_timers": operator_timers_enabled(),
        "pam_submission": False,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "acknowledgement_authority": "wathefni",
    }


# --------------------------------------------------------------------------- schema


_SCHEMA_READY = False


def ensure_shifts_wave6c_schema(cur: Any, *, force: bool = False) -> None:
    """Apply the Wave 6C schema pack once per process.

    The pack contains `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, which takes an
    AccessExclusiveLock even when it is a no-op. Re-running it on every call deadlocked
    against readers holding row locks, so the result is cached for the process and the
    DDL waits are bounded.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = JOB_LOCK_CONTROLLED_BASE - 7
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
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


# --------------------------------------------------------------------------- consent


def record_consent(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    channel: str,
    destination_ref: str | None = None,
    granted_by: str | None = None,
    evidence_ref: str | None = None,
    policy_version: str = "shifts-notify@1.0.0",
    status: str = "granted",
) -> dict[str, Any]:
    ensure_shifts_wave6c_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6c_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6c_disabled", **honesty_payload()}
    if subject_excluded(employee_key):
        return {"ok": False, "error": "subject_excluded", "employee_key": employee_key}
    if status not in {"granted", "withdrawn", "pending"}:
        return {"ok": False, "error": "invalid_consent_status"}
    cur.execute(
        """
        INSERT INTO shift_notification_consent (
          company_code, employee_key, channel, status, policy_version,
          destination_ref, granted_by, evidence_ref
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, employee_key, channel) DO UPDATE SET
          status=EXCLUDED.status,
          policy_version=EXCLUDED.policy_version,
          destination_ref=EXCLUDED.destination_ref,
          granted_by=EXCLUDED.granted_by,
          evidence_ref=EXCLUDED.evidence_ref,
          withdrawn_at=CASE WHEN EXCLUDED.status='withdrawn' THEN now() ELSE NULL END,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            str(employee_key),
            str(channel).lower(),
            status,
            policy_version,
            destination_ref,
            granted_by,
            evidence_ref,
        ),
    )
    return {"ok": True, "consent": _row(cur), **honesty_payload()}


def consent_granted(cur: Any, *, company_code: str, employee_key: str, channel: str) -> dict[str, Any] | None:
    ch = str(channel).lower()
    if ch in IN_PRODUCT_CHANNELS:
        return {"channel": ch, "status": "in_product", "destination_ref": None}
    cur.execute(
        """
        SELECT * FROM shift_notification_consent
        WHERE company_code=%s AND employee_key=%s AND channel=%s AND status='granted'
        """,
        ((company_code or "").upper(), str(employee_key), ch),
    )
    return _row(cur)


# ----------------------------------------------------------------- delivery guards


def delivery_precheck(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    channel: str,
) -> dict[str, Any] | None:
    """Return a denial dict when a real send must not happen, else None."""
    company = (company_code or "").upper()
    if not shifts_wave6c_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6c_disabled"}
    if notify_kill_switch_active():
        return {"ok": False, "error": "notify_kill_switch_active"}
    if not real_delivery_enabled():
        return {"ok": False, "error": "real_delivery_disabled"}
    if subject_excluded(employee_key):
        return {"ok": False, "error": "subject_excluded"}
    allow = real_notify_allowlist()
    if not allow:
        return {"ok": False, "error": "real_notify_allowlist_empty"}
    if str(employee_key) not in allow:
        return {"ok": False, "error": "recipient_not_allowlisted"}
    ch = str(channel).lower()
    if ch not in real_notify_channels():
        return {"ok": False, "error": "channel_not_approved", "channel": ch}
    if consent_granted(cur, company_code=company, employee_key=employee_key, channel=ch) is None:
        return {"ok": False, "error": "consent_missing", "channel": ch}
    return None


def _blocked_sender(**_: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "skipped",
        "error_code": "no_sender_bound",
        "error_detail": "No production sender was bound to Wave 6C delivery.",
        "provider": "none",
        "real_sent": False,
    }


def deliver_event_controlled(
    cur: Any,
    *,
    company_code: str,
    event_id: Any,
    sender: Callable[..., dict[str, Any]] | None = None,
    stop_on_first_success: bool = True,
    channel_order: list[str] | None = None,
) -> dict[str, Any]:
    """Deliver one canonical event through the approved real channels.

    `sender` is injected so the canary and production bind the same code path to the same
    production transport. Every attempt is recorded with provider receipt / correlation id
    and an explicit `real_sent` flag, whether it succeeded, was skipped or was denied.
    """
    ensure_shifts_wave6c_schema(cur)
    company = (company_code or "").upper()
    send = sender or _blocked_sender

    cur.execute(
        "SELECT * FROM shift_notification_events WHERE company_code=%s AND event_id=%s FOR UPDATE",
        (company, str(event_id)),
    )
    event = _row(cur)
    if not event:
        return {"ok": False, "error": "event_not_found", **honesty_payload()}
    if str(event.get("status")) in {"acked", "invalidated", "suppressed"}:
        return {"ok": True, "skipped": True, "event": event, "deliveries": [], **honesty_payload()}

    employee_key = str(event.get("employee_key") or "")
    order = [c.lower() for c in (channel_order or list(real_notify_channels()))]

    deliveries: list[dict[str, Any]] = []
    any_delivered = False
    any_real = False

    for channel in order:
        denial = delivery_precheck(
            cur, company_code=company, employee_key=employee_key, channel=channel
        )
        if denial is not None:
            deliveries.append(
                _record_delivery(
                    cur,
                    company=company,
                    event=event,
                    channel=channel,
                    status="skipped",
                    result={
                        "provider": "none",
                        "error_code": denial.get("error"),
                        "error_detail": f"Blocked before send: {denial.get('error')}",
                        "real_sent": False,
                    },
                )
            )
            continue

        consent = consent_granted(cur, company_code=company, employee_key=employee_key, channel=channel)
        recipient_ref = (consent or {}).get("destination_ref")
        try:
            result = send(
                channel=channel,
                company_code=company,
                employee_key=employee_key,
                event=dict(event),
                recipient_ref=recipient_ref,
            )
        except Exception as exc:  # noqa: BLE001 - transport failures must be recorded, not raised
            result = {
                "ok": False,
                "status": "failed",
                "error_code": "sender_exception",
                "error_detail": str(exc)[:500],
                "provider": "unknown",
                "real_sent": False,
            }

        status = result.get("status") or ("delivered" if result.get("ok") else "failed")
        row = _record_delivery(
            cur, company=company, event=event, channel=channel, status=status, result=result,
            recipient_ref=recipient_ref,
        )
        deliveries.append(row)
        if result.get("real_sent"):
            any_real = True
        if result.get("ok"):
            any_delivered = True
            if stop_on_first_success:
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
        "real_sent": any_real,
        **honesty_payload(),
    }


def _record_delivery(
    cur: Any,
    *,
    company: str,
    event: dict[str, Any],
    channel: str,
    status: str,
    result: dict[str, Any],
    recipient_ref: str | None = None,
) -> dict[str, Any]:
    cur.execute(
        "SELECT coalesce(max(attempt_no),0) AS m FROM shift_notification_deliveries WHERE event_id=%s AND channel=%s",
        (event["event_id"], channel),
    )
    attempt = int((_row(cur) or {}).get("m") or 0) + 1
    backoff = timedelta(minutes=5 * (2 ** max(0, attempt - 1)))
    cur.execute(
        """
        INSERT INTO shift_notification_deliveries (
          company_code, event_id, channel, attempt_no, status, provider,
          provider_message_id, correlation_id, error_code, error_detail,
          delivered_at, next_retry_at, real_sent, recipient_ref, provider_receipt
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            event["event_id"],
            channel,
            attempt,
            status,
            result.get("provider") or "none",
            result.get("provider_message_id"),
            result.get("correlation_id"),
            result.get("error_code"),
            result.get("error_detail"),
            datetime.now(timezone.utc) if result.get("ok") else None,
            (datetime.now(timezone.utc) + backoff) if status == "failed" else None,
            bool(result.get("real_sent")),
            recipient_ref,
            json.dumps(_jsonable(result.get("receipt") or {})),
        ),
    )
    return _row(cur) or {}


def list_terminal_failures(cur: Any, *, company_code: str, limit: int = 50) -> list[dict[str, Any]]:
    """HR-visible terminal failures — a real message that will never arrive must be seen."""
    cur.execute(
        """
        SELECT d.*, e.event_type, e.employee_key, e.employee_name
        FROM shift_notification_deliveries d
        JOIN shift_notification_events e ON e.event_id = d.event_id
        WHERE d.company_code=%s AND d.status IN ('terminal_failed','failed')
        ORDER BY d.created_at DESC LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(200, int(limit)))),
    )
    return _rows(cur)


# ------------------------------------------------------------------- operator jobs


def run_controlled_job(
    cur: Any,
    *,
    company_code: str,
    job_key: str,
    handler: Callable[[int], dict[str, Any]],
    batch_size: int = 25,
    lock_offset: int = 1,
) -> dict[str, Any]:
    """Run one bounded operator batch under an advisory lock, recording the run.

    Overlapping execution is impossible: a second caller fails to take the advisory lock
    and records `skipped_locked` instead of processing anything.
    """
    ensure_shifts_wave6c_schema(cur)
    company = (company_code or "").upper()
    lock_id = JOB_LOCK_CONTROLLED_BASE + int(lock_offset)
    size = max(1, min(500, int(batch_size)))

    if not controlled_jobs_enabled():
        cur.execute(
            """
            INSERT INTO shift_controlled_job_runs (
              company_code, job_key, lock_id, batch_size, status, skipped_reason, finished_at
            ) VALUES (%s,%s,%s,%s,'skipped_disabled','controlled_jobs_disabled', now())
            RETURNING *
            """,
            (company, job_key, lock_id, size),
        )
        return {"ok": True, "skipped": True, "reason": "controlled_jobs_disabled", "run": _row(cur)}

    cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (lock_id,))
    got = bool((_row(cur) or {}).get("got"))
    if not got:
        cur.execute(
            """
            INSERT INTO shift_controlled_job_runs (
              company_code, job_key, lock_id, batch_size, status, skipped_reason, finished_at
            ) VALUES (%s,%s,%s,%s,'skipped_locked','advisory_lock_held', now())
            RETURNING *
            """,
            (company, job_key, lock_id, size),
        )
        return {"ok": True, "skipped": True, "reason": "advisory_lock_held", "run": _row(cur)}

    cur.execute(
        """
        INSERT INTO shift_controlled_job_runs (company_code, job_key, lock_id, batch_size, status)
        VALUES (%s,%s,%s,%s,'running') RETURNING *
        """,
        (company, job_key, lock_id, size),
    )
    run = _row(cur) or {}
    try:
        outcome = handler(size) or {}
        cur.execute(
            """
            UPDATE shift_controlled_job_runs SET
              status='completed', claimed=%s, processed=%s, failed=%s, finished_at=now()
            WHERE run_id=%s RETURNING *
            """,
            (
                int(outcome.get("claimed") or 0),
                int(outcome.get("processed") or 0),
                int(outcome.get("failed") or 0),
                run.get("run_id"),
            ),
        )
        return {"ok": True, "skipped": False, "run": _row(cur), "outcome": outcome}
    except Exception as exc:  # noqa: BLE001 - a failed batch must stay visible, not vanish
        cur.execute(
            """
            UPDATE shift_controlled_job_runs SET status='failed', error_detail=%s, finished_at=now()
            WHERE run_id=%s RETURNING *
            """,
            (str(exc)[:500], run.get("run_id")),
        )
        return {"ok": False, "error": "job_failed", "detail": str(exc)[:500], "run": _row(cur)}
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


# ------------------------------------------------------------------ freeze posture


def permission_matrix() -> dict[str, Any]:
    return {
        "hr_allowlisted_real": {
            "create": True,
            "reschedule": True,
            "soft_cancel": True,
            "template_create": True,
            "recurrence_preview": True,
            "draft_review_approve_publish": True,
            "open_shift_create_decide": True,
            "requires_audit_reason": True,
            "requires_concurrency_token": True,
            "future_dates_only": True,
        },
        "manager_scoped": {
            "real_rollout": False,
            "reason": "no manager identity, scope, branch or team exists in production",
            "synthetic_qualification": "in_scope_only",
            "self_decision": False,
            "publish": "only_if_approval_matrix_grants",
        },
        "talal_employee_app": {
            "read_own": True,
            "acknowledge": True,
            "mutate": False,
            "open_shift_claim": False,
            "swap_request": False,
        },
        "broad_employee_app": {"read": False, "mutate": False},
        "operator_timers": "disabled_unless_WATHEFNI_SHIFTS_OPERATOR_TIMERS=on",
        "pam": "export_only_manual_submission_required",
    }


def freeze_invariants() -> tuple[str, ...]:
    """Invariants the freeze regression suite asserts must never be weakened."""
    return (
        "canonical_l0_authority",
        "published_version_immutability",
        "lifecycle_and_leave_gates",
        "self_decision_ban",
        "manager_scope_enforcement",
        "concurrency_and_idempotency",
        "overnight_and_split_semantics",
        "template_regeneration_safety",
        "notification_deduplication",
        "notification_tenant_isolation",
        "real_notify_allowlist_fail_closed",
        "notify_kill_switch",
        "controlled_subject_exclusions",
        "no_payroll_money",
        "no_leave_balance_mutation",
        "no_attendance_authority_mutation",
        "pam_export_only",
        "frozen_employees360_onboarding_attendance_leave",
    )
