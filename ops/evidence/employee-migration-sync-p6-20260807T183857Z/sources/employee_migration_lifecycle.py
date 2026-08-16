"""Migration & Sync P6 — Leavers + lifecycle sync.

External lifecycle data is a signal, not automatic authority. Events flow through
the Connected Systems sync_run ledger and policy dispositions (review / auto /
ignore). Apply reuses hub employment_status + Auth Wave 2 session revoke.
No hard-delete. No separate lifecycle engine.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import schema_contract

CONTRACT = "employee_migration_sync_p6_leavers"
CONTRACT_VERSION = "6.0.0"

# Hub employment_status values (canonical Wathefni)
HUB_ACTIVE = "active"
HUB_LEFT = "left"

# Normalized proposed lifecycle states
NORM_TERMINATED = "terminated"
NORM_INACTIVE = "inactive"
NORM_SUSPENDED = "suspended"
NORM_RESIGNED = "resigned"
NORM_EMPLOYMENT_ENDED = "employment_ended"
NORM_REACTIVATED = "reactivated"
NORM_REHIRED = "rehired"
NORM_ACTIVE = "active"
NORM_UNKNOWN = "unknown"

TERMINATION_LIKE = frozenset(
    {
        NORM_TERMINATED,
        NORM_INACTIVE,
        NORM_SUSPENDED,
        NORM_RESIGNED,
        NORM_EMPLOYMENT_ENDED,
    }
)
REACTIVATION_LIKE = frozenset({NORM_REACTIVATED, NORM_REHIRED, NORM_ACTIVE})

POLICY_REVIEW = "review_required"
POLICY_AUTO = "auto_apply"
POLICY_IGNORE = "ignore"
POLICY_VALUES = frozenset({POLICY_REVIEW, POLICY_AUTO, POLICY_IGNORE})

DISPOSITION_TERMINATION_PROPOSED = "termination_proposed"
DISPOSITION_REACTIVATION_PROPOSED = "reactivation_proposed"
DISPOSITION_WILL_APPLY = "will_apply"
DISPOSITION_NEEDS_REVIEW = "needs_review"
DISPOSITION_IGNORED = "ignored_by_policy"
DISPOSITION_UNCHANGED = "unchanged"
DISPOSITION_APPLIED = "applied"
DISPOSITION_BLOCKED = "blocked_authority"

EVENT_STATUSES = frozenset(
    {
        "proposed",
        "needs_review",
        "applied",
        "ignored",
        "unchanged",
        "rejected",
        "blocked",
    }
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_migration_lifecycle_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  connection_id uuid,
  sync_run_id uuid,
  batch_id uuid,
  source_system text NOT NULL,
  external_employee_id text,
  employee_key text,
  source_status text,
  normalized_state text NOT NULL,
  proposed_hub_status text,
  effective_date date,
  reason_code text,
  reason_text text,
  policy text NOT NULL,
  disposition text NOT NULL,
  status text NOT NULL DEFAULT 'proposed',
  event_fingerprint text NOT NULL,
  authority_note text,
  review_reason text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  applied_at timestamptz,
  applied_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, source_system, event_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_lifecycle_company
  ON employee_migration_lifecycle_events(company_code, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_emp_mig_lifecycle_sync
  ON employee_migration_lifecycle_events(sync_run_id);
CREATE INDEX IF NOT EXISTS idx_emp_mig_lifecycle_employee
  ON employee_migration_lifecycle_events(company_code, employee_key)
  WHERE employee_key IS NOT NULL;
"""

_SCHEMA_READY = False

# Source status → normalized state
_STATUS_MAP = {
    "terminated": NORM_TERMINATED,
    "terminate": NORM_TERMINATED,
    "termination": NORM_TERMINATED,
    "dismissed": NORM_TERMINATED,
    "fired": NORM_TERMINATED,
    "ended": NORM_EMPLOYMENT_ENDED,
    "employment_ended": NORM_EMPLOYMENT_ENDED,
    "end of employment": NORM_EMPLOYMENT_ENDED,
    "end_of_employment": NORM_EMPLOYMENT_ENDED,
    "resigned": NORM_RESIGNED,
    "resignation": NORM_RESIGNED,
    "quit": NORM_RESIGNED,
    "inactive": NORM_INACTIVE,
    "in_active": NORM_INACTIVE,
    "not_active": NORM_INACTIVE,
    "suspended": NORM_SUSPENDED,
    "suspension": NORM_SUSPENDED,
    "leave_without_pay": NORM_SUSPENDED,
    "source_deleted_or_inactive": NORM_INACTIVE,
    "deleted": NORM_INACTIVE,
    "removed": NORM_INACTIVE,
    "reactivated": NORM_REACTIVATED,
    "reactivate": NORM_REACTIVATED,
    "rehired": NORM_REHIRED,
    "rehire": NORM_REHIRED,
    "re_hired": NORM_REHIRED,
    "active": NORM_ACTIVE,
    "employed": NORM_ACTIVE,
    "current": NORM_ACTIVE,
}


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "no_hard_delete": True,
        "lifecycle_signal_not_automatic_authority": True,
        "default_termination_policy": POLICY_REVIEW,
        "policies": sorted(POLICY_VALUES),
        "reuses_auth_wave2_revoke": True,
        "revoked_reason_offboarded": True,
        "revoked_reason_reactivated_via_invite": True,
        "no_auto_invite_on_rehire": True,
        "preserves_history": True,
        "no_auth_wave2_phase6": True,
        "feeds_connected_systems_sync_runs": True,
        "no_parallel_lifecycle_engine": True,
    }


def ensure_lifecycle_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=["employee_migration_lifecycle_events"],
        module="employee_migration_lifecycle",
        lock_id=None,
    )
    _SCHEMA_READY = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    # date (not datetime)
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def normalize_source_status(raw: str | None) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return NORM_UNKNOWN
    if text in _STATUS_MAP:
        return _STATUS_MAP[text]
    for key, norm in _STATUS_MAP.items():
        if key in text or text in key:
            return norm
    return NORM_UNKNOWN


def proposed_hub_status(normalized: str) -> str | None:
    if normalized in TERMINATION_LIKE:
        return HUB_LEFT
    if normalized in REACTIVATION_LIKE:
        return HUB_ACTIVE
    return None


def resolve_lifecycle_policy(
    config: dict[str, Any] | None,
    *,
    normalized_state: str,
) -> str:
    """Per-connection policy. Default: review_required for material lifecycle changes."""
    cfg = dict(config or {})
    policy_block = cfg.get("lifecycle_policy") if isinstance(cfg.get("lifecycle_policy"), dict) else {}
    default = str(policy_block.get("default") or POLICY_REVIEW).strip().lower()
    if default not in POLICY_VALUES:
        default = POLICY_REVIEW

    if normalized_state in TERMINATION_LIKE:
        raw = str(policy_block.get("termination") or default).strip().lower()
    elif normalized_state in REACTIVATION_LIKE:
        raw = str(policy_block.get("reactivation") or default).strip().lower()
    else:
        raw = str(policy_block.get("unknown") or POLICY_IGNORE).strip().lower()

    if raw not in POLICY_VALUES:
        return POLICY_REVIEW
    # Safety: never default auto for termination unless explicitly set
    if normalized_state in TERMINATION_LIKE and "termination" not in policy_block and raw == POLICY_AUTO:
        return POLICY_REVIEW
    return raw


def event_fingerprint(
    *,
    external_employee_id: str | None,
    normalized_state: str,
    effective_date: str | None,
    source_status: str | None,
) -> str:
    material = "|".join(
        [
            str(external_employee_id or "").strip(),
            str(normalized_state or "").strip(),
            str(effective_date or "").strip(),
            str(source_status or "").strip().lower(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _parse_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()[:32]
    if not text:
        return None
    # Accept YYYY-MM-DD prefix
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text[:10] if text else None


def _lookup_employee_key(
    cur: Any,
    *,
    company: str,
    source_system: str,
    external_employee_id: str | None,
) -> str | None:
    ext = str(external_employee_id or "").strip()
    if not ext:
        return None
    cur.execute(
        """
        SELECT employee_key FROM employee_source_mappings
        WHERE company_code=%s AND source_system=%s AND external_employee_id=%s AND active IS TRUE
        LIMIT 1
        """,
        (company, source_system, ext),
    )
    row = cur.fetchone()
    return str(row["employee_key"]) if row else None


def _load_employee(cur: Any, *, company: str, employee_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT employee_key, employment_status, updated_at, raw_json, name, phone
        FROM employees
        WHERE company_code=%s AND employee_key=%s
        LIMIT 1
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _hub_status(emp: dict[str, Any] | None) -> str:
    raw = str((emp or {}).get("employment_status") or HUB_ACTIVE).strip().lower()
    return HUB_LEFT if raw == HUB_LEFT else HUB_ACTIVE


def _newer_native_blocks_termination(emp: dict[str, Any], effective_date: str | None) -> tuple[bool, str | None]:
    """Block stale/lower-authority termination when Wathefni shows newer accepted lifecycle state.

    Do not treat ordinary import `updated_at` alone as native authority — freshly synced
    employees would otherwise always block historical effective dates.
    """
    del effective_date
    hub = _hub_status(emp)
    if hub != HUB_ACTIVE:
        return False, None
    raw = emp.get("raw_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if raw.get("lifecycle_native_authority") is True:
        return True, "native_wathefni_lifecycle_authority"
    prior = raw.get("employee_migration_lifecycle") if isinstance(raw.get("employee_migration_lifecycle"), dict) else {}
    # If we previously applied a reactivation/rehire and hub is active, block stale termination auto/review-apply path.
    if prior.get("normalized_state") in REACTIVATION_LIKE and hub == HUB_ACTIVE:
        return True, "source_termination_stale_vs_newer_wathefni_activity"
    rehire = raw.get("lifecycle_rehire") if isinstance(raw.get("lifecycle_rehire"), dict) else {}
    if rehire.get("requires_fresh_activation") and hub == HUB_ACTIVE:
        return True, "source_termination_stale_vs_newer_wathefni_activity"
    return False, None


def _stamp_lifecycle_provenance(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    event: dict[str, Any],
) -> None:
    patch = {
        "employee_migration_lifecycle": {
            "contract": CONTRACT,
            "version": CONTRACT_VERSION,
            "event_id": str(event.get("event_id")),
            "normalized_state": event.get("normalized_state"),
            "source_status": event.get("source_status"),
            "source_system": event.get("source_system"),
            "effective_date": _jsonable(event.get("effective_date")),
            "policy": event.get("policy"),
            "applied_at": _now().isoformat(),
            "sync_run_id": str(event.get("sync_run_id")) if event.get("sync_run_id") else None,
        }
    }
    cur.execute(
        """
        UPDATE employees
        SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb, updated_at=now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (json.dumps(_jsonable(patch)), company, employee_key),
    )


def apply_hub_lifecycle(
    legacy: Any,
    *,
    company: str,
    employee_key: str,
    target_hub: str,
    event: dict[str, Any],
    actor: str | None,
) -> dict[str, Any]:
    """Apply hub employment_status + Auth Wave 2 revoke. Never hard-deletes."""
    target = HUB_LEFT if target_hub == HUB_LEFT else HUB_ACTIVE
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            emp = _load_employee(cur, company=company, employee_key=employee_key)
            if not emp:
                return {"ok": False, "error": "employee_not_found"}
            previous = _hub_status(emp)
            if previous == target:
                _stamp_lifecycle_provenance(cur, company=company, employee_key=employee_key, event=event)
                conn.commit()
                return {"ok": True, "status": "unchanged", "employment_status": target, "sessions_revoked": 0}

            cur.execute(
                """
                UPDATE employees
                SET employment_status=%s, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                RETURNING employee_key, employment_status
                """,
                (target, company, employee_key),
            )
            updated = dict(cur.fetchone())
            _stamp_lifecycle_provenance(cur, company=company, employee_key=employee_key, event=event)

            sessions_revoked = 0
            if target == HUB_LEFT:
                # Reuse Auth Wave 2 revoke — offboarded → account_inactive UX
                cur.execute(
                    """
                    UPDATE employee_sessions
                    SET status='revoked', refresh_hash=NULL, revoked_at=now(),
                        revoked_reason='offboarded',
                        expires_at=LEAST(expires_at, now()),
                        refresh_expires_at=LEAST(refresh_expires_at, now())
                    WHERE company_code=%s AND employee_key=%s AND status='active'
                    """,
                    (company, employee_key),
                )
                sessions_revoked = int(cur.rowcount or 0)
                cur.execute(
                    """
                    UPDATE employee_push_tokens
                    SET active=false, last_error=%s, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s AND active IS TRUE
                    """,
                    ("offboarded", company, employee_key),
                )
                # Best-effort: abandon open onboarding without failing lifecycle apply
                try:
                    cur.execute("SAVEPOINT p6_onboarding_abandon")
                    cur.execute(
                        """
                        UPDATE onboarding_items
                        SET status='abandoned_employment_ended', updated_at=now()
                        WHERE company_code=%s AND employee_key=%s
                          AND status NOT IN ('completed', 'abandoned_employment_ended', 'cancelled')
                        """,
                        (company, employee_key),
                    )
                    cur.execute("RELEASE SAVEPOINT p6_onboarding_abandon")
                except Exception:
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT p6_onboarding_abandon")
                    except Exception:
                        pass

            elif target == HUB_ACTIVE and previous == HUB_LEFT:
                # Rehire/reactivation: kill stale sessions; require fresh activation (no auto-invite)
                cur.execute(
                    """
                    UPDATE employee_sessions
                    SET status='revoked', refresh_hash=NULL, revoked_at=now(),
                        revoked_reason='reactivated_via_invite',
                        expires_at=LEAST(expires_at, now()),
                        refresh_expires_at=LEAST(refresh_expires_at, now())
                    WHERE company_code=%s AND employee_key=%s AND status='active'
                    """,
                    (company, employee_key),
                )
                sessions_revoked = int(cur.rowcount or 0)
                cur.execute(
                    """
                    UPDATE employee_push_tokens
                    SET active=false, last_error=%s, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s AND active IS TRUE
                    """,
                    ("reactivated_via_invite", company, employee_key),
                )
                cur.execute(
                    """
                    UPDATE employees
                    SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (
                        json.dumps(
                            {
                                "lifecycle_rehire": {
                                    "at": _now().isoformat(),
                                    "requires_fresh_activation": True,
                                    "prior_status": previous,
                                }
                            }
                        ),
                        company,
                        employee_key,
                    ),
                )

            cur.execute(
                """
                UPDATE employee_migration_lifecycle_events
                SET status='applied', disposition=%s, applied_at=now(), applied_by=%s, updated_at=now()
                WHERE event_id=%s
                """,
                (DISPOSITION_APPLIED, actor, event.get("event_id")),
            )
            conn.commit()
    return {
        "ok": True,
        "status": "applied",
        "employment_status": updated.get("employment_status"),
        "previous_status": previous,
        "sessions_revoked": sessions_revoked,
        "employee_key": employee_key,
    }


def _public_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(row.get("event_id")),
        "company_code": row.get("company_code"),
        "connection_id": str(row["connection_id"]) if row.get("connection_id") else None,
        "sync_run_id": str(row["sync_run_id"]) if row.get("sync_run_id") else None,
        "source_system": row.get("source_system"),
        "external_employee_id": row.get("external_employee_id"),
        "employee_key": row.get("employee_key"),
        "source_status": row.get("source_status"),
        "normalized_state": row.get("normalized_state"),
        "proposed_hub_status": row.get("proposed_hub_status"),
        "effective_date": _jsonable(row.get("effective_date")),
        "reason_code": row.get("reason_code"),
        "reason_text": row.get("reason_text"),
        "policy": row.get("policy"),
        "disposition": row.get("disposition"),
        "status": row.get("status"),
        "review_reason": row.get("review_reason"),
        "authority_note": row.get("authority_note"),
        "applied_at": _jsonable(row.get("applied_at")),
        "created_at": _jsonable(row.get("created_at")),
    }


def process_lifecycle_signals(
    legacy: Any,
    context: dict[str, Any],
    *,
    connection: dict[str, Any],
    sync_run_id: str,
    signals: list[dict[str, Any]],
    auto_commit_apply: bool = True,
) -> dict[str, Any]:
    """Normalize + policy-route lifecycle signals for one sync run. Idempotent."""
    company = str(context.get("company_code") or connection.get("company_code") or "").upper()
    if not company:
        raise ValueError("company_required")
    # Paused/disconnected must never apply — caller should already block sync
    conn_status = str(connection.get("status") or "").strip().lower()
    if conn_status in {"paused", "disconnected"}:
        return {
            "ok": True,
            "skipped": True,
            "reason": f"connection_{conn_status}",
            "counts": {},
            "events": [],
            "honesty": honesty_payload(),
        }

    actor = str(context.get("user_id") or context.get("email") or "") or None
    source_system = str(connection.get("source_system") or "")
    connection_id = str(connection.get("connection_id") or "") or None
    cfg = connection.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)

    counts: dict[str, int] = {
        DISPOSITION_TERMINATION_PROPOSED: 0,
        DISPOSITION_REACTIVATION_PROPOSED: 0,
        DISPOSITION_WILL_APPLY: 0,
        DISPOSITION_NEEDS_REVIEW: 0,
        DISPOSITION_IGNORED: 0,
        DISPOSITION_UNCHANGED: 0,
        DISPOSITION_APPLIED: 0,
        DISPOSITION_BLOCKED: 0,
        "replayed": 0,
    }
    events_out: list[dict[str, Any]] = []

    for raw_sig in signals or []:
        if not isinstance(raw_sig, dict):
            continue
        source_status = str(
            raw_sig.get("source_status")
            or raw_sig.get("status")
            or raw_sig.get("signal")
            or raw_sig.get("employment_status")
            or ""
        ).strip() or None
        # Missing status = not supplied — ignore, never assume termination
        if not source_status:
            counts[DISPOSITION_IGNORED] += 1
            continue

        normalized = normalize_source_status(source_status)
        if normalized == NORM_UNKNOWN and not raw_sig.get("force_unknown_review"):
            counts[DISPOSITION_IGNORED] += 1
            continue

        ext_id = str(
            raw_sig.get("external_employee_id")
            or raw_sig.get("external_id")
            or raw_sig.get("employee_id")
            or ""
        ).strip() or None
        effective_date = _parse_date(raw_sig.get("effective_date") or raw_sig.get("termination_date"))
        reason_code = str(raw_sig.get("reason_code") or raw_sig.get("reason") or "").strip() or None
        reason_text = str(raw_sig.get("reason_text") or raw_sig.get("note") or "").strip() or None
        hub = proposed_hub_status(normalized)
        policy = resolve_lifecycle_policy(cfg, normalized_state=normalized)
        fp = event_fingerprint(
            external_employee_id=ext_id,
            normalized_state=normalized,
            effective_date=effective_date,
            source_status=source_status,
        )

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_lifecycle_schema(cur)
                # Idempotent replay
                cur.execute(
                    """
                    SELECT * FROM employee_migration_lifecycle_events
                    WHERE company_code=%s AND source_system=%s AND event_fingerprint=%s
                    """,
                    (company, source_system, fp),
                )
                existing = cur.fetchone()
                if existing:
                    existing = dict(existing)
                    counts["replayed"] += 1
                    if existing.get("status") == "applied":
                        counts[DISPOSITION_UNCHANGED] += 1
                    else:
                        counts[str(existing.get("disposition") or DISPOSITION_UNCHANGED)] = (
                            counts.get(str(existing.get("disposition") or DISPOSITION_UNCHANGED), 0) + 1
                        )
                    events_out.append(_public_event(existing))
                    conn.commit()
                    continue

                employee_key = _lookup_employee_key(
                    cur,
                    company=company,
                    source_system=source_system,
                    external_employee_id=ext_id,
                )
                emp = _load_employee(cur, company=company, employee_key=employee_key) if employee_key else None

                disposition = DISPOSITION_NEEDS_REVIEW
                status = "needs_review"
                review_reason = None
                authority_note = None

                if policy == POLICY_IGNORE:
                    disposition = DISPOSITION_IGNORED
                    status = "ignored"
                elif not employee_key:
                    disposition = DISPOSITION_NEEDS_REVIEW
                    status = "needs_review"
                    review_reason = "identity_unmatched"
                elif hub is None:
                    disposition = DISPOSITION_IGNORED
                    status = "ignored"
                    review_reason = "unknown_lifecycle_state"
                elif hub == _hub_status(emp):
                    disposition = DISPOSITION_UNCHANGED
                    status = "unchanged"
                elif hub == HUB_LEFT:
                    blocked, why = _newer_native_blocks_termination(emp, effective_date)
                    if blocked:
                        disposition = DISPOSITION_BLOCKED
                        status = "blocked"
                        review_reason = why
                        authority_note = "Newer Wathefni activity / native authority blocks source termination."
                    elif policy == POLICY_AUTO:
                        disposition = DISPOSITION_WILL_APPLY
                        status = "proposed"
                    else:
                        disposition = DISPOSITION_TERMINATION_PROPOSED
                        status = "needs_review"
                        review_reason = "termination_requires_review"
                elif hub == HUB_ACTIVE:
                    if policy == POLICY_AUTO:
                        disposition = DISPOSITION_WILL_APPLY
                        status = "proposed"
                    else:
                        disposition = DISPOSITION_REACTIVATION_PROPOSED
                        status = "needs_review"
                        review_reason = "reactivation_requires_review"

                # Multi-source disagreement: if another connection applied opposite recently
                if employee_key and hub and disposition in {
                    DISPOSITION_WILL_APPLY,
                    DISPOSITION_TERMINATION_PROPOSED,
                    DISPOSITION_REACTIVATION_PROPOSED,
                }:
                    cur.execute(
                        """
                        SELECT source_system, normalized_state, status, created_at
                        FROM employee_migration_lifecycle_events
                        WHERE company_code=%s AND employee_key=%s
                          AND status IN ('applied', 'needs_review', 'proposed')
                          AND source_system <> %s
                          AND proposed_hub_status IS NOT NULL
                          AND proposed_hub_status <> %s
                          AND created_at > now() - interval '30 days'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (company, employee_key, source_system, hub),
                    )
                    conflict = cur.fetchone()
                    if conflict:
                        disposition = DISPOSITION_NEEDS_REVIEW
                        status = "needs_review"
                        review_reason = "conflicting_connected_systems"
                        authority_note = f"Disagrees with {conflict['source_system']} ({conflict['normalized_state']})"

                cur.execute(
                    """
                    INSERT INTO employee_migration_lifecycle_events (
                      company_code, connection_id, sync_run_id, source_system,
                      external_employee_id, employee_key, source_status, normalized_state,
                      proposed_hub_status, effective_date, reason_code, reason_text,
                      policy, disposition, status, event_fingerprint,
                      authority_note, review_reason, payload
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
                    )
                    RETURNING *
                    """,
                    (
                        company,
                        connection_id,
                        sync_run_id,
                        source_system,
                        ext_id,
                        employee_key,
                        source_status,
                        normalized,
                        hub,
                        effective_date,
                        reason_code,
                        reason_text,
                        policy,
                        disposition,
                        status,
                        fp,
                        authority_note,
                        review_reason,
                        json.dumps({"signal": raw_sig, "contract": CONTRACT}),
                    ),
                )
                event = dict(cur.fetchone())
                conn.commit()

        counts[disposition] = counts.get(disposition, 0) + 1

        # Auto-apply when policy allows and disposition is will_apply
        if (
            auto_commit_apply
            and disposition == DISPOSITION_WILL_APPLY
            and hub
            and employee_key
            and status == "proposed"
        ):
            applied = apply_hub_lifecycle(
                legacy,
                company=company,
                employee_key=employee_key,
                target_hub=hub,
                event=event,
                actor=actor or "lifecycle-auto-apply",
            )
            if applied.get("ok"):
                if applied.get("status") == "unchanged":
                    counts[DISPOSITION_UNCHANGED] += 1
                    counts[DISPOSITION_WILL_APPLY] = max(0, counts[DISPOSITION_WILL_APPLY] - 1)
                else:
                    counts[DISPOSITION_APPLIED] += 1
                    counts[DISPOSITION_WILL_APPLY] = max(0, counts[DISPOSITION_WILL_APPLY] - 1)
                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM employee_migration_lifecycle_events WHERE event_id=%s",
                            (event["event_id"],),
                        )
                        event = dict(cur.fetchone())
                        conn.commit()
            else:
                # Fall back to needs review if apply failed
                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE employee_migration_lifecycle_events
                            SET status='needs_review', disposition=%s,
                                review_reason=%s, updated_at=now()
                            WHERE event_id=%s
                            RETURNING *
                            """,
                            (
                                DISPOSITION_NEEDS_REVIEW,
                                f"auto_apply_failed:{applied.get('error')}",
                                event["event_id"],
                            ),
                        )
                        event = dict(cur.fetchone())
                        conn.commit()
                counts[DISPOSITION_NEEDS_REVIEW] += 1
                counts[DISPOSITION_WILL_APPLY] = max(0, counts[DISPOSITION_WILL_APPLY] - 1)

        events_out.append(_public_event(event))

    return {
        "ok": True,
        "counts": counts,
        "events": events_out,
        "honesty": honesty_payload(),
    }


def list_lifecycle_events(
    legacy: Any,
    context: dict[str, Any],
    *,
    status: str | None = None,
    sync_run_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    lim = max(1, min(int(limit or 50), 200))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            clauses = ["company_code=%s"]
            params: list[Any] = [company]
            if status:
                clauses.append("status=%s")
                params.append(str(status))
            if sync_run_id:
                clauses.append("sync_run_id=%s")
                params.append(sync_run_id)
            params.append(lim)
            cur.execute(
                f"""
                SELECT * FROM employee_migration_lifecycle_events
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return {"ok": True, "events": [_public_event(r) for r in rows], "honesty": honesty_payload()}


def list_lifecycle_review(
    legacy: Any,
    context: dict[str, Any],
    *,
    limit: int = 50,
) -> dict[str, Any]:
    return list_lifecycle_events(legacy, context, status="needs_review", limit=limit)


def approve_lifecycle_event(
    legacy: Any,
    context: dict[str, Any],
    *,
    event_id: str,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    actor = str(context.get("user_id") or context.get("email") or "") or None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_migration_lifecycle_events
                WHERE company_code=%s AND event_id=%s
                FOR UPDATE
                """,
                (company, event_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "lifecycle_event_not_found"})
            event = dict(row)
            if event.get("status") == "applied":
                conn.commit()
                return {"ok": True, "event": _public_event(event), "status": "already_applied"}
            if event.get("status") not in {"needs_review", "proposed", "blocked"}:
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "lifecycle_event_not_reviewable", "status": event.get("status")},
                )
            if not event.get("employee_key") or not event.get("proposed_hub_status"):
                raise legacy.HTTPException(
                    status_code=422,
                    detail={"error": "lifecycle_event_incomplete", "message": "Match employee before applying."},
                )
            # Clear blocked → allow explicit HR override
            cur.execute(
                """
                UPDATE employee_migration_lifecycle_events
                SET status='proposed', disposition=%s, review_reason=NULL,
                    authority_note=COALESCE(authority_note,'') || ' | hr_approved_override',
                    updated_at=now()
                WHERE event_id=%s
                RETURNING *
                """,
                (DISPOSITION_WILL_APPLY, event_id),
            )
            event = dict(cur.fetchone())
            conn.commit()

    applied = apply_hub_lifecycle(
        legacy,
        company=company,
        employee_key=str(event["employee_key"]),
        target_hub=str(event["proposed_hub_status"]),
        event=event,
        actor=actor,
    )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employee_migration_lifecycle_events WHERE event_id=%s",
                (event_id,),
            )
            event = dict(cur.fetchone())
            conn.commit()
    return {"ok": bool(applied.get("ok")), "event": _public_event(event), "apply": applied}


def reject_lifecycle_event(
    legacy: Any,
    context: dict[str, Any],
    *,
    event_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    actor = str(context.get("user_id") or context.get("email") or "") or None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                UPDATE employee_migration_lifecycle_events
                SET status='rejected', disposition=%s,
                    review_reason=%s, applied_by=%s, updated_at=now()
                WHERE company_code=%s AND event_id=%s
                  AND status IN ('needs_review', 'proposed', 'blocked')
                RETURNING *
                """,
                (
                    DISPOSITION_IGNORED,
                    (reason or "rejected_by_hr")[:180],
                    actor,
                    company,
                    event_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "lifecycle_event_not_found"})
            conn.commit()
    return {"ok": True, "event": _public_event(dict(row))}
