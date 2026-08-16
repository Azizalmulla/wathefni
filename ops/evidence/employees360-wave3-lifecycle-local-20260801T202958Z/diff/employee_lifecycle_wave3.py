"""Employees 360 Wave 3 — employment lifecycle, termination, reversal, true rehire.

Builds on Wave 2 person/employment/assignment authority.

Compatibility:
  - Hub `employees.employment_status` remains active|left for existing modules.
  - Rich lifecycle lives on `employee_employments.lifecycle_state`.
  - terminated ⇒ hub left; all other live states ⇒ hub active.

WATHEFNI-only when flag + company allowlist enabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from employee_authority_wave2 import (
    authority_v2_enabled,
    ensure_authority_schema,
    get_authority_projection,
    mint_assignment_id,
    mint_employment_id,
    open_rehire_employment,
    phone_digits,
)
from employee_hygiene_wave1c import _jsonable as _hygiene_jsonable

SCHEMA_VERSION = "employees360-wave3-lifecycle-v1"

LIFECYCLE_STATES = frozenset({
    "pending_start",
    "active",
    "notice_period",
    "suspended",
    "terminated",
})
TERMINATION_TYPES = frozenset({
    "resignation",
    "dismissal",
    "end_of_contract",
    "mutual",
    "other",
})
CASE_TYPES = frozenset({
    "termination",
    "reversal",
    "rehire",
    "notice",
    "suspension",
    "unsuspend",
    "activate_start",
})
REQUEST_STATUSES = frozenset({"pending", "approved", "rejected", "cancelled", "executed", "expired"})


def lifecycle_v3_enabled(company_code: str | None = None) -> bool:
    raw = str(os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3") or "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    # Wave 3 requires Wave 2 authority for the tenant.
    try:
        if not authority_v2_enabled(company_code):
            return False
    except TypeError:
        # Older Wave 2 builds exposed a zero-arg flag only.
        if not authority_v2_enabled():
            return False
        if company_code is not None:
            allow_v2 = str(os.environ.get("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES") or "WATHEFNI")
            if str(company_code).upper() not in {c.strip().upper() for c in allow_v2.split(",") if c.strip()}:
                return False
    allow = str(os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES") or "WATHEFNI")
    companies = {c.strip().upper() for c in allow.split(",") if c.strip()}
    if company_code is None:
        return bool(companies)
    return str(company_code or "").upper() in companies


def _jsonable(value: Any) -> Any:
    return _hygiene_jsonable(value)


def _ts_equal(left: Any, right: Any) -> bool:
    """Compare hub updated_at tokens across datetime/ISO string forms."""
    if left is None or right is None:
        return left is None and right is None
    if left == right:
        return True
    try:
        l = left if isinstance(left, datetime) else datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        r = right if isinstance(right, datetime) else datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        return l == r
    except Exception:
        return str(left) == str(right)


WAVE3_SCHEMA_SQL = """
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS lifecycle_state text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS notice_starts_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS last_working_day date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_effective_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_type text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_reason text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS suspended_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS suspension_reason text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS lifecycle_version bigint NOT NULL DEFAULT 1;

UPDATE employee_employments
SET lifecycle_state = CASE
  WHEN lower(coalesce(employment_status,'active')) = 'left' THEN 'terminated'
  ELSE 'active'
END
WHERE lifecycle_state IS NULL;

CREATE TABLE IF NOT EXISTS employee_lifecycle_cases (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_type text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  summary text,
  impact_snapshot_id uuid,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_user_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  CHECK (case_type IN ('termination','reversal','rehire','notice','suspension','unsuspend','activate_start')),
  CHECK (status IN ('open','pending_approval','executed','cancelled','rejected'))
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_cases_employee
  ON employee_lifecycle_cases (company_code, employee_key, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_lifecycle_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  case_id uuid NOT NULL REFERENCES employee_lifecycle_cases(case_id),
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_type text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_lifecycle_state text NOT NULL,
  expected_lifecycle_version bigint NOT NULL,
  expected_hub_updated_at timestamptz NOT NULL,
  reason text NOT NULL,
  approval_reference text NOT NULL,
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  decision_reason text,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  resulting_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','cancelled','executed','expired')),
  CHECK (requester_user_id <> designated_approver_user_id),
  UNIQUE (company_code, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_requests_pending
  ON employee_lifecycle_requests (company_code, designated_approver_user_id, status, created_at DESC)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS employee_lifecycle_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  case_id uuid,
  request_id uuid,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  from_state text,
  to_state text NOT NULL,
  event_type text NOT NULL,
  effective_on date,
  last_working_day date,
  termination_type text,
  reason text,
  actor_user_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_events_employment
  ON employee_lifecycle_events (company_code, employment_id, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_lifecycle_impact_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid NOT NULL,
  as_of_date date NOT NULL,
  preview jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_migration_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'applied',
  created_at timestamptz NOT NULL DEFAULT now(),
  rolled_back_at timestamptz,
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def ensure_lifecycle_schema(cur) -> None:
    ensure_authority_schema(cur)
    cur.execute(WAVE3_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO employee_lifecycle_schema_meta (schema_name, schema_version)
        VALUES ('employees360_wave3', %s)
        ON CONFLICT (schema_name) DO UPDATE
          SET schema_version=EXCLUDED.schema_version, applied_at=now()
        """,
        (SCHEMA_VERSION,),
    )


def hub_status_for_lifecycle(lifecycle_state: str) -> str:
    return "left" if str(lifecycle_state) == "terminated" else "active"


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _require_manage(legacy: Any, context: dict[str, Any]) -> str:
    company = str(context.get("company_code") or "").upper()
    if not lifecycle_v3_enabled(company):
        raise legacy.HTTPException(
            status_code=403,
            detail={"error": "lifecycle_disabled", "message": "Employment lifecycle is not enabled for this company."},
        )
    if not legacy.dashboard_context_has_permission(context, "employees.manage"):
        raise legacy.HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "message": "You do not have access to do that."},
        )
    return company


def _require_scope(legacy: Any, context: dict[str, Any], employee_key: str) -> None:
    # Preserve Wave 1 manager-scope fail-closed when available.
    company = str(context.get("company_code") or "").upper() or None
    if hasattr(legacy, "require_employee_mutation_scope"):
        legacy.require_employee_mutation_scope(
            context, employee_key, company_code=company, action="lifecycle"
        )
        return
    # Fallback: restricted managers without helper cannot mutate.
    scope = legacy.manager_scope_context(context) if hasattr(legacy, "manager_scope_context") else {"restricted": False}
    if scope.get("restricted"):
        allowed = set(scope.get("direct_employee_keys") or [])
        if employee_key not in allowed:
            raise legacy.HTTPException(
                status_code=404,
                detail={"error": "employee_not_found", "message": "We couldn't find that employee."},
            )


def preview_downstream_impact(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Read-only downstream impact preview. No legal/payroll decisions."""
    company = str(company_code).upper()
    as_of = as_of_date or date.today()
    preview: dict[str, Any] = {
        "as_of_date": as_of.isoformat(),
        "employee_key": employee_key,
        "company_code": company,
        "disclaimer": "Preview only. No automatic legal or payroll decisions are made.",
        "domains": {},
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)

            def count_sql(sql: str, params: tuple) -> int:
                try:
                    cur.execute(sql, params)
                    return int(dict(cur.fetchone() or {}).get("n") or 0)
                except Exception:
                    conn.rollback()
                    ensure_lifecycle_schema(cur)
                    return 0

            future_shifts = count_sql(
                """
                SELECT count(*)::bigint AS n FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND shift_date >= %s
                """,
                (company, employee_key, as_of),
            )
            open_leave = count_sql(
                """
                SELECT count(*)::bigint AS n FROM leave_requests
                WHERE company_code=%s AND employee_key=%s
                  AND lower(coalesce(status,'')) IN ('pending','approved','open','requested')
                  AND coalesce(end_date, start_date) >= %s
                """,
                (company, employee_key, as_of),
            )
            leave_balances = 0
            try:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='leave_balances'"
                )
                if cur.fetchone():
                    cur.execute(
                        "SELECT count(*)::bigint AS n FROM leave_balances WHERE company_code=%s AND employee_key=%s",
                        (company, employee_key),
                    )
                    leave_balances = int(dict(cur.fetchone())["n"])
            except Exception:
                leave_balances = 0

            # Prefer leave_ledger periods if balances table absent
            if leave_balances == 0:
                try:
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='leave_ledger'"
                    )
                    if cur.fetchone():
                        cur.execute(
                            "SELECT count(*)::bigint AS n FROM leave_ledger WHERE company_code=%s AND employee_key=%s",
                            (company, employee_key),
                        )
                        leave_balances = int(dict(cur.fetchone())["n"])
                except Exception:
                    leave_balances = 0

            attendance_exceptions = count_sql(
                """
                SELECT count(*)::bigint AS n FROM attendance_records
                WHERE company_code=%s AND employee_key=%s
                  AND attendance_date >= %s
                  AND (
                    lower(coalesce(status,'')) IN ('exception','missing','open','pending')
                    OR coalesce(late_minutes,0) > 0
                    OR coalesce(early_leave_minutes,0) > 0
                  )
                """,
                (company, employee_key, as_of - timedelta(days=30)),
            )
            payroll_open = count_sql(
                """
                SELECT count(*)::bigint AS n FROM payroll_timesheets
                WHERE company_code=%s AND employee_key=%s
                  AND lower(coalesce(status,'')) IN ('draft','open','pending','submitted')
                """,
                (company, employee_key),
            )
            onboarding_open = count_sql(
                """
                SELECT count(*)::bigint AS n FROM onboarding_items
                WHERE employee_key=%s
                  AND lower(coalesce(status,'')) IN ('pending','in_progress','open')
                """,
                (employee_key,),
            )
            compliance_open = count_sql(
                """
                SELECT count(*)::bigint AS n FROM compliance_documents
                WHERE company_code=%s AND employee_key=%s
                  AND lower(coalesce(status,'')) IN ('missing','pending','expired','rejected')
                """,
                (company, employee_key),
            )
            documents = count_sql(
                """
                SELECT count(*)::bigint AS n FROM employee_documents
                WHERE employee_key=%s
                """,
                (employee_key,),
            )
            sessions = count_sql(
                """
                SELECT count(*)::bigint AS n FROM employee_sessions
                WHERE company_code=%s AND employee_key=%s
                  AND revoked_at IS NULL
                  AND lower(coalesce(status,'active')) = 'active'
                  AND expires_at > now()
                """,
                (company, employee_key),
            )
            invites = count_sql(
                """
                SELECT count(*)::bigint AS n FROM employee_app_invites
                WHERE company_code=%s AND employee_key=%s
                  AND lower(coalesce(status,'')) IN ('pending','sent','active')
                """,
                (company, employee_key),
            )

            preview["domains"] = {
                "future_shifts": {
                    "count": future_shifts,
                    "recommended_action": "review_and_cancel_or_reassign" if future_shifts else "none",
                    "automatic": False,
                },
                "open_leave_requests": {
                    "count": open_leave,
                    "recommended_action": "review_pending_leave" if open_leave else "none",
                    "automatic": False,
                },
                "leave_balances": {
                    "count": leave_balances,
                    "recommended_action": "manual_final_settlement_input" if leave_balances else "none",
                    "automatic": False,
                    "note": "Balances are inputs only; no settlement is computed here.",
                },
                "attendance_exceptions": {
                    "count": attendance_exceptions,
                    "recommended_action": "resolve_exceptions" if attendance_exceptions else "none",
                    "automatic": False,
                },
                "payroll_timesheets": {
                    "count": payroll_open,
                    "recommended_action": "finalize_or_hold_timesheets" if payroll_open else "none",
                    "automatic": False,
                    "note": "No payroll decision is automated.",
                },
                "onboarding_obligations": {
                    "count": onboarding_open,
                    "recommended_action": "close_or_waive_open_items" if onboarding_open else "none",
                    "automatic": False,
                },
                "compliance_obligations": {
                    "count": compliance_open,
                    "recommended_action": "review_missing_or_expired_docs" if compliance_open else "none",
                    "automatic": False,
                },
                "documents": {
                    "count": documents,
                    "recommended_action": "retain_per_policy",
                    "automatic": False,
                },
                "employee_app_access": {
                    "active_sessions": sessions,
                    "open_invites": invites,
                    "recommended_action": "revoke_sessions_and_invites_on_effective_termination"
                    if (sessions or invites)
                    else "none",
                    "automatic": False,
                },
            }
            # Persist snapshot
            cur.execute(
                """
                INSERT INTO employee_lifecycle_impact_snapshots (
                  company_code, employee_key, employment_id, as_of_date, preview
                )
                SELECT %s, %s, m.employment_id, %s, %s::jsonb
                FROM employee_key_authority_map m
                WHERE m.company_code=%s AND m.employee_key=%s
                RETURNING snapshot_id
                """,
                (
                    company,
                    employee_key,
                    as_of,
                    json.dumps(_jsonable(preview)),
                    company,
                    employee_key,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            if row:
                preview["snapshot_id"] = str(dict(row)["snapshot_id"])
    return preview


def _load_employment(cur, *, company: str, employee_key: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT e.*, m.employee_key, m.assignment_id, m.person_id AS map_person_id,
               emp.updated_at AS hub_updated_at, emp.employment_status AS hub_employment_status
        FROM employee_key_authority_map m
        JOIN employee_employments e
          ON e.employment_id = m.employment_id AND e.company_code = m.company_code
        JOIN employees emp
          ON emp.employee_key = m.employee_key AND emp.company_code = m.company_code
        WHERE m.company_code=%s AND m.employee_key=%s AND m.mapping_status='active'
        LIMIT 1
        FOR UPDATE OF e, emp
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    if not row:
        raise KeyError("employment_not_found")
    return dict(row)


def create_lifecycle_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    case_type: str,
    reason: str,
    approval_reference: str,
    designated_approver_user_id: str,
    idempotency_key: str,
    expected_lifecycle_state: str,
    expected_lifecycle_version: int,
    expected_hub_updated_at: datetime,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    _require_scope(legacy, context, employee_key)
    case_type = str(case_type or "").strip().lower()
    if case_type not in CASE_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_case_type"})
    requester = str(context.get("actor_user_id") or "").strip()
    approver = str(designated_approver_user_id or "").strip()
    if not requester or not approver or requester == approver or approver == "self":
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "self_approval_forbidden",
                "message": "A separate approver is required. You cannot approve your own lifecycle request.",
            },
        )
    body = payload or {}
    if case_type == "termination":
        eff = body.get("termination_effective_on") or body.get("effective_on")
        if not eff:
            raise legacy.HTTPException(status_code=422, detail={"error": "effective_date_required"})
        ttype = str(body.get("termination_type") or "other").lower()
        if ttype not in TERMINATION_TYPES:
            raise legacy.HTTPException(status_code=422, detail={"error": "invalid_termination_type"})

    # Impact preview outside the write TX (own connection)
    as_of = date.today()
    if case_type == "termination":
        as_of = date.fromisoformat(str(body.get("termination_effective_on") or body.get("effective_on")))
    impact = preview_downstream_impact(
        legacy, company_code=company, employee_key=employee_key, as_of_date=as_of
    )

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            # approver must hold approve permission
            import employee_status_approval as status_approval

            status_approval.ensure_employee_status_approval_schema(cur)
            eligible = status_approval.list_eligible_status_approvers(
                legacy, cur, company_code=company, exclude_user_id=requester
            )
            if not any(str(a.get("user_id")) == approver for a in eligible):
                raise legacy.HTTPException(
                    status_code=403,
                    detail={"error": "approver_not_eligible", "message": "Designated approver is not eligible."},
                )

            try:
                employment = _load_employment(cur, company=company, employee_key=employee_key)
            except KeyError:
                raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})

            current_state = str(employment.get("lifecycle_state") or "active")
            current_version = int(employment.get("lifecycle_version") or 1)
            hub_updated = employment.get("hub_updated_at")
            if current_state != expected_lifecycle_state or current_version != int(expected_lifecycle_version):
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "employee_version_conflict", "message": "Lifecycle state changed. Refresh and retry."},
                )
            if not _ts_equal(hub_updated, expected_hub_updated_at):
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "employee_version_conflict", "message": "Employee changed. Refresh and retry."},
                )

            hash_payload = {
                "company_code": company,
                "employee_key": employee_key,
                "case_type": case_type,
                "expected_lifecycle_state": expected_lifecycle_state,
                "expected_lifecycle_version": int(expected_lifecycle_version),
                "expected_hub_updated_at": (
                    expected_hub_updated_at.isoformat()
                    if isinstance(expected_hub_updated_at, datetime)
                    else str(expected_hub_updated_at)
                ),
                "reason": reason.strip(),
                "approval_reference": approval_reference.strip(),
                "requester_user_id": requester,
                "designated_approver_user_id": approver,
                "idempotency_key": idempotency_key.strip(),
                "payload": body,
            }
            rhash = _request_hash(hash_payload)

            cur.execute(
                """
                SELECT * FROM employee_lifecycle_requests
                WHERE company_code=%s AND idempotency_key=%s
                LIMIT 1
                """,
                (company, idempotency_key.strip()),
            )
            existing = cur.fetchone()
            if existing:
                ex = dict(existing)
                if str(ex.get("request_hash")) != rhash:
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={"error": "idempotency_conflict", "message": "Idempotency key reused with different payload."},
                    )
                conn.commit()
                return {"ok": True, "idempotent": True, "request": _jsonable(ex), "impact": impact}

            cur.execute(
                """
                INSERT INTO employee_lifecycle_cases (
                  company_code, employee_key, person_id, employment_id, case_type, status,
                  summary, impact_snapshot_id, created_by_user_id, provenance
                ) VALUES (%s,%s,%s,%s,%s,'pending_approval',%s,%s,%s,%s::jsonb)
                RETURNING *
                """,
                (
                    company,
                    employee_key,
                    employment["person_id"],
                    employment["employment_id"],
                    case_type,
                    reason.strip()[:500],
                    impact.get("snapshot_id"),
                    requester,
                    json.dumps({"wave": "wave3", "impact": {"snapshot_id": impact.get("snapshot_id")}}),
                ),
            )
            case = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_lifecycle_requests (
                  company_code, case_id, employee_key, person_id, employment_id, case_type,
                  idempotency_key, request_hash, payload, expected_lifecycle_state,
                  expected_lifecycle_version, expected_hub_updated_at, reason, approval_reference,
                  requester_user_id, designated_approver_user_id, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,'pending')
                RETURNING *
                """,
                (
                    company,
                    case["case_id"],
                    employee_key,
                    employment["person_id"],
                    employment["employment_id"],
                    case_type,
                    idempotency_key.strip(),
                    rhash,
                    json.dumps(_jsonable(body)),
                    expected_lifecycle_state,
                    int(expected_lifecycle_version),
                    expected_hub_updated_at,
                    reason.strip(),
                    approval_reference.strip(),
                    requester,
                    approver,
                ),
            )
            req = dict(cur.fetchone())
            conn.commit()
            return {"ok": True, "idempotent": False, "case": _jsonable(case), "request": _jsonable(req), "impact": impact}


def cancel_lifecycle_request(legacy: Any, context: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    actor = str(context.get("actor_user_id") or "").strip()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_lifecycle_requests
                WHERE company_code=%s AND request_id=%s FOR UPDATE
                """,
                (company, request_id),
            )
            req = cur.fetchone()
            if not req:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(req)
            if str(req.get("requester_user_id")) != actor:
                raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
            if req.get("status") != "pending":
                raise legacy.HTTPException(status_code=409, detail={"error": "request_not_pending"})
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='cancelled', updated_at=now(), decided_at=now(), decided_by_user_id=%s, decision_reason='cancelled_by_requester'
                WHERE request_id=%s RETURNING *
                """,
                (actor, request_id),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                "UPDATE employee_lifecycle_cases SET status='cancelled', updated_at=now(), closed_at=now() WHERE case_id=%s",
                (req["case_id"],),
            )
            conn.commit()
            return {"ok": True, "request": _jsonable(updated)}


def _apply_transition(
    cur,
    *,
    company: str,
    employment: dict[str, Any],
    to_state: str,
    event_type: str,
    actor_user_id: str,
    case_id: Any,
    request_id: Any,
    effective_on: date | None,
    last_working_day: date | None,
    termination_type: str | None,
    reason: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from_state = str(employment.get("lifecycle_state") or "active")
    hub_status = hub_status_for_lifecycle(to_state)
    version = int(employment.get("lifecycle_version") or 1) + 1

    notice_starts_on = employment.get("notice_starts_on")
    suspended_on = employment.get("suspended_on")
    suspension_reason = employment.get("suspension_reason")
    term_eff = employment.get("termination_effective_on")
    lwd = employment.get("last_working_day")
    term_type = employment.get("termination_type")
    term_reason = employment.get("termination_reason")
    end_date = employment.get("end_date")

    if to_state == "notice_period":
        notice_starts_on = effective_on or date.today()
    if to_state == "suspended":
        suspended_on = effective_on or date.today()
        suspension_reason = reason
    if to_state == "active" and from_state == "suspended":
        suspended_on = None
        suspension_reason = None
    if to_state == "terminated":
        term_eff = effective_on
        lwd = last_working_day or effective_on
        term_type = termination_type or "other"
        term_reason = reason
        end_date = effective_on
    if to_state == "active" and from_state in {"terminated", "notice_period"}:
        # Reversal / cancel-before-effective on the same employment.
        term_eff = None
        lwd = None
        term_type = None
        term_reason = None
        end_date = None
        notice_starts_on = None

    cur.execute(
        """
        UPDATE employee_employments SET
          lifecycle_state=%s,
          employment_status=%s,
          lifecycle_version=%s,
          notice_starts_on=%s,
          suspended_on=%s,
          suspension_reason=%s,
          termination_effective_on=%s,
          last_working_day=%s,
          termination_type=%s,
          termination_reason=%s,
          end_date=%s,
          updated_at=now()
        WHERE company_code=%s AND employment_id=%s
        RETURNING *
        """,
        (
            to_state,
            hub_status,
            version,
            notice_starts_on,
            suspended_on,
            suspension_reason,
            term_eff,
            lwd,
            term_type,
            term_reason,
            end_date,
            company,
            employment["employment_id"],
        ),
    )
    updated = dict(cur.fetchone())
    # Hub compatibility projection
    cur.execute(
        """
        UPDATE employees
        SET employment_status=%s, updated_at=clock_timestamp()
        WHERE company_code=%s AND employee_key=%s
        RETURNING employee_key, employment_status, updated_at
        """,
        (hub_status, company, employment["employee_key"]),
    )
    hub = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO employee_lifecycle_events (
          company_code, case_id, request_id, employee_key, person_id, employment_id,
          from_state, to_state, event_type, effective_on, last_working_day, termination_type,
          reason, actor_user_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            case_id,
            request_id,
            employment["employee_key"],
            employment["person_id"],
            employment["employment_id"],
            from_state,
            to_state,
            event_type,
            effective_on,
            last_working_day,
            termination_type,
            reason,
            actor_user_id,
            json.dumps(_jsonable(payload)),
        ),
    )
    event = dict(cur.fetchone())
    return {"employment": updated, "hub": hub, "event": event}


def decide_lifecycle_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
    action: str,
    decision_reason: str | None = None,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    if not lifecycle_v3_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "lifecycle_disabled"})
    actor = str(context.get("actor_user_id") or "").strip()
    action = str(action or "").strip().lower()
    if action not in {"approve", "reject"}:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_action"})
    if not legacy.dashboard_context_has_permission(context, "employees.status.approve"):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_lifecycle_requests
                WHERE company_code=%s AND request_id=%s FOR UPDATE
                """,
                (company, request_id),
            )
            req = cur.fetchone()
            if not req:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(req)
            if str(req.get("designated_approver_user_id")) != actor:
                raise legacy.HTTPException(
                    status_code=403,
                    detail={"error": "not_designated_approver", "message": "Only the designated approver can decide."},
                )
            if str(req.get("requester_user_id")) == actor:
                raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
            if req.get("status") != "pending":
                # Idempotent rehire replay after approved→executed race window.
                if action == "approve" and req.get("status") == "executed" and req.get("resulting_event_id"):
                    conn.commit()
                    return {
                        "ok": True,
                        "idempotent": True,
                        "decision": "approve",
                        "committed": True,
                        "request": _jsonable(req),
                    }
                raise legacy.HTTPException(status_code=409, detail={"error": "request_not_pending"})

            if action == "reject":
                cur.execute(
                    """
                    UPDATE employee_lifecycle_requests
                    SET status='rejected', decision_reason=%s, decided_by_user_id=%s, decided_at=now(), updated_at=now()
                    WHERE request_id=%s RETURNING *
                    """,
                    (decision_reason or "rejected", actor, request_id),
                )
                updated = dict(cur.fetchone())
                cur.execute(
                    "UPDATE employee_lifecycle_cases SET status='rejected', updated_at=now(), closed_at=now() WHERE case_id=%s",
                    (req["case_id"],),
                )
                conn.commit()
                return {"ok": True, "decision": "reject", "committed": False, "request": _jsonable(updated)}

            # approve path — stale checks
            employment = _load_employment(cur, company=company, employee_key=req["employee_key"])
            if str(employment.get("lifecycle_state") or "active") != str(req.get("expected_lifecycle_state")):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})
            if int(employment.get("lifecycle_version") or 1) != int(req.get("expected_lifecycle_version") or 0):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})
            if not _ts_equal(employment.get("hub_updated_at"), req.get("expected_hub_updated_at")):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})

            payload = req.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            case_type = str(req.get("case_type"))

            if case_type == "termination":
                eff = date.fromisoformat(str(payload.get("termination_effective_on") or payload.get("effective_on")))
                lwd = payload.get("last_working_day")
                lwd_d = date.fromisoformat(str(lwd)) if lwd else eff
                # Future-dated: move to notice_period until effective; if effective today/past → terminated now.
                today = date.today()
                if eff > today:
                    applied = _apply_transition(
                        cur,
                        company=company,
                        employment=employment,
                        to_state="notice_period",
                        event_type="termination_scheduled",
                        actor_user_id=actor,
                        case_id=req["case_id"],
                        request_id=req["request_id"],
                        effective_on=eff,
                        last_working_day=lwd_d,
                        termination_type=str(payload.get("termination_type") or "other"),
                        reason=str(req.get("reason") or ""),
                        payload={**payload, "scheduled": True},
                    )
                    # store scheduled fields even while in notice
                    cur.execute(
                        """
                        UPDATE employee_employments SET
                          termination_effective_on=%s,
                          last_working_day=%s,
                          termination_type=%s,
                          termination_reason=%s,
                          updated_at=now()
                        WHERE employment_id=%s
                        """,
                        (
                            eff,
                            lwd_d,
                            str(payload.get("termination_type") or "other"),
                            str(req.get("reason") or ""),
                            employment["employment_id"],
                        ),
                    )
                else:
                    applied = _apply_transition(
                        cur,
                        company=company,
                        employment=employment,
                        to_state="terminated",
                        event_type="termination_effective",
                        actor_user_id=actor,
                        case_id=req["case_id"],
                        request_id=req["request_id"],
                        effective_on=eff,
                        last_working_day=lwd_d,
                        termination_type=str(payload.get("termination_type") or "other"),
                        reason=str(req.get("reason") or ""),
                        payload=payload,
                    )
            elif case_type == "reversal":
                if str(employment.get("lifecycle_state")) not in {"terminated", "notice_period"}:
                    raise legacy.HTTPException(status_code=409, detail={"error": "reversal_not_applicable"})
                # Reversal restores same employment — never invents a new one.
                target = str(payload.get("restore_state") or "active")
                if target not in {"active", "notice_period", "suspended"}:
                    target = "active"
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state=target,
                    event_type="termination_reversed",
                    actor_user_id=actor,
                    case_id=req["case_id"],
                    request_id=req["request_id"],
                    effective_on=date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason=str(req.get("reason") or ""),
                    payload=payload,
                )
            elif case_type == "notice":
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state="notice_period",
                    event_type="notice_started",
                    actor_user_id=actor,
                    case_id=req["case_id"],
                    request_id=req["request_id"],
                    effective_on=date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason=str(req.get("reason") or ""),
                    payload=payload,
                )
            elif case_type == "suspension":
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state="suspended",
                    event_type="suspended",
                    actor_user_id=actor,
                    case_id=req["case_id"],
                    request_id=req["request_id"],
                    effective_on=date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason=str(req.get("reason") or ""),
                    payload=payload,
                )
            elif case_type == "unsuspend":
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state="active",
                    event_type="unsuspended",
                    actor_user_id=actor,
                    case_id=req["case_id"],
                    request_id=req["request_id"],
                    effective_on=date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason=str(req.get("reason") or ""),
                    payload=payload,
                )
            elif case_type == "activate_start":
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state="active",
                    event_type="started",
                    actor_user_id=actor,
                    case_id=req["case_id"],
                    request_id=req["request_id"],
                    effective_on=date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason=str(req.get("reason") or ""),
                    payload=payload,
                )
            elif case_type == "rehire":
                # True rehire: must not flip old employment active. Create new employment/assignment.
                if str(employment.get("lifecycle_state")) != "terminated":
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={
                            "error": "rehire_requires_terminated_employment",
                            "message": "Rehire requires a terminated prior employment.",
                        },
                    )
                # Mark approved before releasing the row lock so concurrent decide fails closed.
                cur.execute(
                    """
                    UPDATE employee_lifecycle_requests
                    SET status='approved', decided_by_user_id=%s, decided_at=now(),
                        decision_reason=%s, updated_at=now()
                    WHERE request_id=%s AND status='pending'
                    RETURNING *
                    """,
                    (actor, decision_reason or "approved", request_id),
                )
                if not cur.fetchone():
                    raise legacy.HTTPException(status_code=409, detail={"error": "request_not_pending"})
                conn.commit()
                return _execute_rehire_after_approval(legacy, context, req=req, actor=actor, payload=payload)
            else:
                raise legacy.HTTPException(status_code=422, detail={"error": "unsupported_case_type"})

            event_id = applied["event"]["event_id"]
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='executed', decided_by_user_id=%s, decided_at=now(), executed_at=now(),
                    decision_reason=%s, resulting_event_id=%s, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (actor, decision_reason or "approved", event_id, request_id),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                "UPDATE employee_lifecycle_cases SET status='executed', updated_at=now(), closed_at=now() WHERE case_id=%s",
                (req["case_id"],),
            )
            conn.commit()
            return {
                "ok": True,
                "decision": "approve",
                "committed": True,
                "request": _jsonable(updated),
                "event": _jsonable(applied["event"]),
                "employment": _jsonable(applied["employment"]),
                "hub": _jsonable(applied["hub"]),
            }


def _execute_rehire_after_approval(
    legacy: Any,
    context: dict[str, Any],
    *,
    req: dict[str, Any],
    actor: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    person_id = str(req.get("person_id"))
    old_key = str(req.get("employee_key"))
    phone = str(payload.get("phone") or "")
    name = str(payload.get("name") or "Rehired employee")
    position = payload.get("position_title")
    if not phone:
        # fall back to person primary phone / old hub phone
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (old_key,))
                phone = str(dict(cur.fetchone() or {}).get("phone") or "")
    if not phone:
        raise legacy.HTTPException(status_code=422, detail={"error": "rehire_phone_required"})

    # New hub key from canonical phone — if same phone, reuse key string but NEW employment ids
    # Wave 2 open_rehire creates new employee_key; for same phone PK conflict, mint suffix key.
    digits = phone_digits(phone)
    new_key = str(payload.get("new_employee_key") or f"{company}-{digits}-R{uuid.uuid4().hex[:4].upper()}")
    result = open_rehire_employment(
        legacy,
        company_code=company,
        person_id=person_id,
        new_employee_key=new_key,
        phone=digits or phone,
        name=name,
        position_title=position,
        app_key=payload.get("app_key"),
    )
    # Ensure prior employment remains terminated (immutable history)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                UPDATE employee_employments
                SET lifecycle_state='terminated',
                    employment_status='left',
                    updated_at=now()
                WHERE company_code=%s AND employment_id=%s
                """,
                (company, req["employment_id"]),
            )
            # New employment lifecycle active
            new_employment_id = result["employment"]["employment_id"]
            cur.execute(
                """
                UPDATE employee_employments
                SET lifecycle_state='active', employment_status='active', lifecycle_version=1, updated_at=now()
                WHERE company_code=%s AND employment_id=%s
                """,
                (company, new_employment_id),
            )
            cur.execute(
                """
                INSERT INTO employee_lifecycle_events (
                  company_code, case_id, request_id, employee_key, person_id, employment_id,
                  from_state, to_state, event_type, effective_on, reason, actor_user_id, payload
                ) VALUES (%s,%s,%s,%s,%s,%s,'terminated','active','rehired',CURRENT_DATE,%s,%s,%s::jsonb)
                RETURNING *
                """,
                (
                    company,
                    req["case_id"],
                    req["request_id"],
                    new_key,
                    person_id,
                    new_employment_id,
                    str(req.get("reason") or ""),
                    actor,
                    json.dumps(
                        _jsonable(
                            {
                                "prior_employment_id": str(req["employment_id"]),
                                "prior_employee_key": old_key,
                                "new_assignment_id": result["assignment"]["assignment_id"],
                            }
                        )
                    ),
                ),
            )
            event = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='executed', decided_by_user_id=%s, decided_at=COALESCE(decided_at, now()),
                    executed_at=now(), resulting_event_id=%s, updated_at=now()
                WHERE request_id=%s AND status IN ('pending','approved')
                RETURNING *
                """,
                (actor, event["event_id"], req["request_id"]),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                "UPDATE employee_lifecycle_cases SET status='executed', updated_at=now(), closed_at=now() WHERE case_id=%s",
                (req["case_id"],),
            )
            # history count
            cur.execute(
                "SELECT count(*)::bigint AS n FROM employee_employments WHERE company_code=%s AND person_id=%s",
                (company, person_id),
            )
            history_n = int(dict(cur.fetchone())["n"])
            conn.commit()
    return {
        "ok": True,
        "decision": "approve",
        "committed": True,
        "rehire": True,
        "request": _jsonable(updated),
        "event": _jsonable(event),
        "person_id": person_id,
        "prior_employment_id": str(req["employment_id"]),
        "new_employment_id": str(new_employment_id),
        "new_assignment_id": str(result["assignment"]["assignment_id"]),
        "new_employee_key": new_key,
        "employment_history_count": history_n,
        "note": "Prior employment remains terminated; rehire created a new employment and assignment.",
    }


def execute_due_scheduled_terminations(legacy: Any, *, company_code: str) -> dict[str, Any]:
    """Move notice_period employments to terminated when effective date is due."""
    company = str(company_code).upper()
    if not lifecycle_v3_enabled(company):
        return {"ok": False, "error": "lifecycle_disabled"}
    executed = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT e.*, m.employee_key
                FROM employee_employments e
                JOIN employee_key_authority_map m
                  ON m.employment_id=e.employment_id AND m.company_code=e.company_code
                WHERE e.company_code=%s
                  AND e.lifecycle_state='notice_period'
                  AND e.termination_effective_on IS NOT NULL
                  AND e.termination_effective_on <= CURRENT_DATE
                FOR UPDATE OF e
                """,
                (company,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            for employment in rows:
                applied = _apply_transition(
                    cur,
                    company=company,
                    employment=employment,
                    to_state="terminated",
                    event_type="termination_effective",
                    actor_user_id=None,
                    case_id=None,
                    request_id=None,
                    effective_on=employment.get("termination_effective_on"),
                    last_working_day=employment.get("last_working_day"),
                    termination_type=employment.get("termination_type"),
                    reason=employment.get("termination_reason") or "scheduled_effective",
                    payload={"scheduler": True},
                )
                executed.append(_jsonable(applied["event"]))
            conn.commit()
    return {"ok": True, "executed": executed, "count": len(executed)}


def get_lifecycle_projection(legacy: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    company = str(company_code or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT e.employment_id, e.person_id, e.lifecycle_state, e.lifecycle_version,
                       e.employment_status AS authority_employment_status,
                       e.notice_starts_on, e.last_working_day, e.termination_effective_on,
                       e.termination_type, e.termination_reason, e.suspended_on, e.suspension_reason,
                       e.start_date, e.end_date, m.employee_key, m.assignment_id,
                       emp.employment_status AS hub_employment_status, emp.updated_at AS hub_updated_at
                FROM employee_key_authority_map m
                JOIN employee_employments e
                  ON e.employment_id=m.employment_id AND e.company_code=m.company_code
                JOIN employees emp
                  ON emp.employee_key=m.employee_key AND emp.company_code=m.company_code
                WHERE m.company_code=%s AND m.employee_key=%s AND m.mapping_status='active'
                LIMIT 1
                """,
                (company, employee_key),
            )
            row = cur.fetchone()
            conn.commit()
            return _jsonable(dict(row)) if row else None


def list_pending_lifecycle_for_actor(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    employee_key: str | None = None,
) -> list[dict[str, Any]]:
    company = str(company_code or "").upper()
    actor = str(actor_user_id or "").strip()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            if employee_key:
                cur.execute(
                    """
                    SELECT *
                    FROM employee_lifecycle_requests
                    WHERE company_code=%s AND status='pending' AND employee_key=%s
                      AND (designated_approver_user_id=%s OR requester_user_id=%s)
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (company, employee_key, actor, actor),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM employee_lifecycle_requests
                    WHERE company_code=%s AND status='pending'
                      AND (designated_approver_user_id=%s OR requester_user_id=%s)
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (company, actor, actor),
                )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return _jsonable(rows)


def rollback_lifecycle_wave3(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Remove Wave 3 lifecycle rows for a tenant/keys; does not destroy Wave 2 authority or hub history."""
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_lifecycle_schema(cur)
            before = {}
            if employee_keys:
                keys = list(employee_keys)
                cur.execute(
                    "SELECT count(*)::bigint n FROM employee_lifecycle_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                before["requests"] = int(dict(cur.fetchone())["n"])
                cur.execute("DELETE FROM employee_lifecycle_events WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                cur.execute("DELETE FROM employee_lifecycle_requests WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                cur.execute("DELETE FROM employee_lifecycle_cases WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                cur.execute("DELETE FROM employee_lifecycle_impact_snapshots WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                # Reset lifecycle fields on employments for those keys to Wave2-compatible active/left
                cur.execute(
                    """
                    UPDATE employee_employments e SET
                      lifecycle_state = CASE WHEN e.employment_status='left' THEN 'terminated' ELSE 'active' END,
                      notice_starts_on=NULL, suspended_on=NULL, suspension_reason=NULL,
                      termination_effective_on=NULL, last_working_day=NULL,
                      termination_type=NULL, termination_reason=NULL,
                      lifecycle_version=1, updated_at=now()
                    FROM employee_key_authority_map m
                    WHERE m.employment_id=e.employment_id AND m.company_code=e.company_code
                      AND m.company_code=%s AND m.employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
            else:
                cur.execute("DELETE FROM employee_lifecycle_events WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_lifecycle_requests WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_lifecycle_cases WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_lifecycle_impact_snapshots WHERE company_code=%s", (company,))
            cur.execute(
                """
                INSERT INTO employee_lifecycle_migration_journal (
                  company_code, action, idempotency_key, before_json, after_json, evidence, status
                ) VALUES (%s,'rollback_wave3',%s,%s::jsonb,'{}'::jsonb,'{}'::jsonb,'rolled_back')
                ON CONFLICT (company_code, idempotency_key) DO UPDATE
                  SET status='rolled_back', rolled_back_at=now(), before_json=EXCLUDED.before_json
                RETURNING *
                """,
                (company, idempotency_key, json.dumps(_jsonable(before))),
            )
            journal = dict(cur.fetchone())
            conn.commit()
            return {"ok": True, "status": "rolled_back", "journal": _jsonable(journal)}
