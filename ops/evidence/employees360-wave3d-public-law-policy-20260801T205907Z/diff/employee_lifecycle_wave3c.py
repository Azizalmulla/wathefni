"""Employees 360 Wave 3C/3D — production-safety + conservative KW public-law policy.

Wave 3C: P0-1..P0-10 safety. Wave 3D: official-source verification + conservative defaults.
No legal/payroll math. Requires Wave 3 + Wave 2 flags. WATHEFNI allowlist by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from employee_authority_wave2 import ensure_authority_schema, phone_digits
from employee_hygiene_wave1c import mint_assignment_id, mint_employment_id
from employee_lifecycle_wave3 import (
    CASE_TYPES as WAVE3_CASE_TYPES,
    _apply_transition,
    _jsonable,
    _load_employment,
    _require_manage,
    _require_scope,
    _request_hash,
    _ts_equal,
    cancel_lifecycle_request,
    create_lifecycle_request as wave3_create_lifecycle_request,
    decide_lifecycle_request as wave3_decide_lifecycle_request,
    ensure_lifecycle_schema as wave3_ensure_lifecycle_schema,
    execute_due_scheduled_terminations as wave3_execute_due,
    get_lifecycle_projection,
    lifecycle_v3_enabled,
    list_pending_lifecycle_for_actor,
    preview_downstream_impact,
    rollback_lifecycle_wave3,
)

SCHEMA_VERSION = "employees360-wave3d-public-law-policy-v1"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")

CASE_TYPES = frozenset(set(WAVE3_CASE_TYPES) | {"cancel_scheduled", "reinstate", "downstream_action"})

DOWNSTREAM_ACTION_TYPES = frozenset({
    "cancel_future_shifts",
    "decline_open_leave",
    "resolve_attendance_hold",
    "abandon_onboarding",
    "revoke_app_access",
    "restore_app_access",
    "reverse_cancel_future_shifts",
    "reverse_decline_open_leave",
    "reverse_abandon_onboarding",
})

# Conservative Wave 3D defaults. Numeric notice values are stored for optional labeled
# guidance only; UI exposure is off unless show_notice_hints is explicitly enabled.
DEFAULT_POLICY = {
    "tier": "small",
    "timezone": "Asia/Kuwait",
    "notice_hint_monthly_days": 90,
    "notice_hint_other_days": 30,
    "show_notice_hints": False,
    "notice_hint_label": (
        "Configurable policy guidance only (not a legal determination). "
        "When enabled, monthly/other day hints mirror Law No. 6 of 2010 Art. 44 "
        "for unlimited contracts (3 months / 1 month) as published in Official Gazette "
        "Issue 963 (21 Feb 2010). Fixed-term, probation, and summary-dismissal cases "
        "are not covered by these hints. HR must enter effective date and last working day."
    ),
    "require_last_working_day": True,
    "allow_reinstate_after_effective": False,
    "jurisdiction_mode": "kuwait_private_sector_only",
    "document_retention_mode": "retain",
    "auto_cancel_shifts": False,
    "auto_decline_leave": False,
    "monetary_calculations_owner": "payroll",
    "settlement_packet_mode": "inputs_only",
    "revoke_mode": "end_of_last_working_day",
    "effective_time_mode": "start_of_effective_date",
    "downstream_mode": "warn_first",
    "require_impact_ack": True,
    "require_counsel_gate": True,
    "allow_self_approval": False,
    "rehire_same_employee_key": True,
    "scheduler_cadence": "hourly",
    "lag_alert_seconds": 7200,
    "disclaimer": (
        "Configurable policy only. Not legal advice. Employees 360 never calculates "
        "EOSB, notice pay, garden leave, or leave encashment — Payroll owns monetary calculations."
    ),
}

WAVE3D_POLICY_JSON_KEYS = (
    "show_notice_hints",
    "notice_hint_label",
    "require_last_working_day",
    "allow_reinstate_after_effective",
    "jurisdiction_mode",
    "document_retention_mode",
    "auto_cancel_shifts",
    "auto_decline_leave",
    "monetary_calculations_owner",
    "settlement_packet_mode",
    "disclaimer",
    "wave",
)

COUNSEL_QUESTIONS = [
    {"id": "CQ1", "text": "Confirm KW notice floors for Wathefni contract types (monthly/other, fixed/unlimited, probation)."},
    {"id": "CQ2", "text": "Does a UI notice suggestion create representation risk if shorter dates are approved?"},
    {"id": "CQ3", "text": "Confirm Employees 360 must never compute pay-in-lieu or garden-leave amounts."},
    {"id": "CQ4", "text": "Confirm EOSB / leave encashment formulas live only in Payroll."},
    {"id": "CQ5", "text": "Summary dismissal without notice — evidence standard."},
    {"id": "CQ6", "text": "Reinstate-after-effective: continuous vs broken service for indemnity/visa."},
    {"id": "CQ7", "text": "Job-search day during employer notice — track vs entitlement."},
    {"id": "CQ8", "text": "Document retention / legal hold after termination."},
    {"id": "CQ9", "text": "Cross-border workers — which notice regime."},
    {"id": "CQ10", "text": "Auto-decline leave / auto-cancel shifts on effective date — local practice."},
]

WAVE3C_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_lifecycle_company_policies (
  company_code text PRIMARY KEY,
  tier text NOT NULL DEFAULT 'small',
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  notice_hint_monthly_days int NOT NULL DEFAULT 90,
  notice_hint_other_days int NOT NULL DEFAULT 30,
  revoke_mode text NOT NULL DEFAULT 'end_of_last_working_day',
  effective_time_mode text NOT NULL DEFAULT 'start_of_effective_date',
  downstream_mode text NOT NULL DEFAULT 'warn_first',
  require_impact_ack boolean NOT NULL DEFAULT true,
  require_counsel_gate boolean NOT NULL DEFAULT true,
  allow_self_approval boolean NOT NULL DEFAULT false,
  rehire_same_employee_key boolean NOT NULL DEFAULT true,
  scheduler_cadence text NOT NULL DEFAULT 'hourly',
  lag_alert_seconds int NOT NULL DEFAULT 7200,
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (tier IN ('small','medium','enterprise')),
  CHECK (revoke_mode IN ('end_of_last_working_day','start_of_effective_date','immediate_on_summary')),
  CHECK (downstream_mode IN ('warn_first','block_submitted_payroll','enterprise_configurable')),
  CHECK (allow_self_approval = false)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_counsel_reviews (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  checklist_version text NOT NULL,
  answers jsonb NOT NULL DEFAULT '{}'::jsonb,
  signed_by_name text NOT NULL,
  signed_by_role text NOT NULL,
  signed_reference text NOT NULL,
  signed_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'signed',
  notes text,
  UNIQUE (company_code, checklist_version),
  CHECK (status IN ('signed','revoked','expired'))
);

ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_snapshot_id uuid;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_snapshot_hash text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_at timestamptz;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_by_user_id uuid;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_text text;

ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoke_at timestamptz;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoked_at timestamptz;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoke_status text;

CREATE TABLE IF NOT EXISTS employee_lifecycle_settlement_packets (
  packet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_id uuid,
  request_id uuid,
  status text NOT NULL DEFAULT 'draft',
  packet jsonb NOT NULL DEFAULT '{}'::jsonb,
  handed_off_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','handed_to_payroll','closed','cancelled'))
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_downstream_actions (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid NOT NULL,
  case_id uuid,
  request_id uuid,
  action_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  reverse_of_action_id uuid,
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid NOT NULL,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','cancelled','executed','reversed')),
  CHECK (requester_user_id <> designated_approver_user_id),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_scheduler_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  environment text NOT NULL DEFAULT 'staging',
  status text NOT NULL DEFAULT 'started',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  terminations_executed int NOT NULL DEFAULT 0,
  revokes_executed int NOT NULL DEFAULT 0,
  lag_seconds int,
  error_text text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (status IN ('started','succeeded','failed','partial'))
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_schema_meta_3c (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- Expand Wave 3 case_type CHECKs for cancel_scheduled / reinstate / downstream_action.
ALTER TABLE employee_lifecycle_cases DROP CONSTRAINT IF EXISTS employee_lifecycle_cases_case_type_check;
ALTER TABLE employee_lifecycle_cases
  ADD CONSTRAINT employee_lifecycle_cases_case_type_check
  CHECK (case_type IN (
    'termination','reversal','rehire','notice','suspension','unsuspend','activate_start',
    'cancel_scheduled','reinstate','downstream_action'
  ));
ALTER TABLE employee_lifecycle_requests DROP CONSTRAINT IF EXISTS employee_lifecycle_requests_case_type_check;
-- requests table may not have named case_type check; ignore if absent.
"""


def ensure_wave3c_schema(cur) -> None:
    wave3_ensure_lifecycle_schema(cur)
    cur.execute(WAVE3C_SCHEMA_SQL)
    # Best-effort expand request case_type if a check exists under unknown name
    cur.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'employee_lifecycle_requests'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) ILIKE '%case_type%'
          LOOP
            EXECUTE format('ALTER TABLE employee_lifecycle_requests DROP CONSTRAINT %I', r.conname);
          END LOOP;
        EXCEPTION WHEN undefined_table THEN
          NULL;
        END $$;
        """
    )
    cur.execute(
        """
        INSERT INTO employee_lifecycle_schema_meta_3c (schema_name, schema_version)
        VALUES ('employees360_wave3c', %s)
        ON CONFLICT (schema_name) DO UPDATE
          SET schema_version=EXCLUDED.schema_version, applied_at=now()
        """,
        (SCHEMA_VERSION,),
    )


def _company_tz(policy: dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo(str(policy.get("timezone") or "Asia/Kuwait"))
    except Exception:
        return KUWAIT_TZ


def _default_policy_json() -> dict[str, Any]:
    return {k: DEFAULT_POLICY[k] for k in WAVE3D_POLICY_JSON_KEYS if k in DEFAULT_POLICY} | {"wave": "wave3d"}


def _normalize_policy(row: dict[str, Any]) -> dict[str, Any]:
    """Merge Wave 3D conservative defaults; hide numeric notice hints unless explicitly enabled."""
    policy = _jsonable(dict(row))
    pj = policy.get("policy_json") or {}
    if isinstance(pj, str):
        try:
            pj = json.loads(pj)
        except Exception:
            pj = {}
    if not isinstance(pj, dict):
        pj = {}
    defaults = _default_policy_json()
    merged_json = {**defaults, **pj}
    for key in WAVE3D_POLICY_JSON_KEYS:
        if key == "wave":
            continue
        if key in merged_json:
            policy[key] = merged_json[key]
        elif key in DEFAULT_POLICY:
            policy[key] = DEFAULT_POLICY[key]
    policy["policy_json"] = merged_json
    policy["disclaimer"] = str(merged_json.get("disclaimer") or DEFAULT_POLICY["disclaimer"])
    show = bool(policy.get("show_notice_hints"))
    policy["show_notice_hints"] = show
    if show:
        policy["notice_hints_ui"] = {
            "monthly_days": int(policy.get("notice_hint_monthly_days") or 90),
            "other_days": int(policy.get("notice_hint_other_days") or 30),
            "label": policy.get("notice_hint_label") or DEFAULT_POLICY["notice_hint_label"],
            "scope": "unlimited_contract_guidance_only",
        }
    else:
        # Hide numeric values from product surfaces unless explicitly enabled.
        policy["notice_hints_ui"] = None
        policy["notice_hint_monthly_days_exposed"] = None
        policy["notice_hint_other_days_exposed"] = None
    policy["allow_reinstate_after_effective"] = bool(policy.get("allow_reinstate_after_effective"))
    policy["require_last_working_day"] = bool(policy.get("require_last_working_day", True))
    policy["auto_cancel_shifts"] = bool(policy.get("auto_cancel_shifts"))
    policy["auto_decline_leave"] = bool(policy.get("auto_decline_leave"))
    return policy


def _assert_kuwait_jurisdiction(legacy: Any, *, policy: dict[str, Any], payload: dict[str, Any]) -> None:
    if str(policy.get("jurisdiction_mode") or "") != "kuwait_private_sector_only":
        return
    raw = (
        payload.get("work_country")
        or payload.get("jurisdiction")
        or payload.get("employment_country")
        or payload.get("country_code")
        or ""
    )
    code = str(raw).strip().upper()
    if not code:
        return
    if code in {"KW", "KWT", "KUWAIT", "KUWAIT_PRIVATE_SECTOR"}:
        return
    raise legacy.HTTPException(
        status_code=422,
        detail={
            "error": "jurisdiction_excluded",
            "message": "Wave 3D supports Kuwait private-sector policy only. Non-Kuwait cases are excluded.",
            "work_country": code,
        },
    )


def get_or_create_company_policy(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute("SELECT * FROM employee_lifecycle_company_policies WHERE company_code=%s", (company,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    INSERT INTO employee_lifecycle_company_policies (
                      company_code, tier, timezone, notice_hint_monthly_days, notice_hint_other_days,
                      revoke_mode, effective_time_mode, downstream_mode, require_impact_ack,
                      require_counsel_gate, allow_self_approval, rehire_same_employee_key,
                      scheduler_cadence, lag_alert_seconds, policy_json
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s,%s,%s::jsonb)
                    RETURNING *
                    """,
                    (
                        company,
                        DEFAULT_POLICY["tier"],
                        DEFAULT_POLICY["timezone"],
                        DEFAULT_POLICY["notice_hint_monthly_days"],
                        DEFAULT_POLICY["notice_hint_other_days"],
                        DEFAULT_POLICY["revoke_mode"],
                        DEFAULT_POLICY["effective_time_mode"],
                        DEFAULT_POLICY["downstream_mode"],
                        DEFAULT_POLICY["require_impact_ack"],
                        DEFAULT_POLICY["require_counsel_gate"],
                        DEFAULT_POLICY["rehire_same_employee_key"],
                        DEFAULT_POLICY["scheduler_cadence"],
                        DEFAULT_POLICY["lag_alert_seconds"],
                        json.dumps(_default_policy_json()),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return _normalize_policy(dict(row))


def upsert_company_policy(legacy: Any, context: dict[str, Any], *, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    patch = patch or {}
    if patch.get("allow_self_approval") is True:
        raise legacy.HTTPException(status_code=422, detail={"error": "self_approval_forbidden_by_policy"})
    current = get_or_create_company_policy(legacy, company_code=company)
    merged = {**current, **{k: v for k, v in patch.items() if v is not None}}
    pj = dict(merged.get("policy_json") or _default_policy_json())
    if isinstance(pj, str):
        pj = json.loads(pj)
    for key in WAVE3D_POLICY_JSON_KEYS:
        if key in patch and patch[key] is not None:
            pj[key] = patch[key]
        elif key in merged and key not in {"policy_json"}:
            pj[key] = merged[key]
    pj["wave"] = "wave3d"
    pj["disclaimer"] = merged.get("disclaimer") or DEFAULT_POLICY["disclaimer"]
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                UPDATE employee_lifecycle_company_policies SET
                  tier=%s, timezone=%s, notice_hint_monthly_days=%s, notice_hint_other_days=%s,
                  revoke_mode=%s, effective_time_mode=%s, downstream_mode=%s,
                  require_impact_ack=%s, require_counsel_gate=%s, allow_self_approval=false,
                  rehire_same_employee_key=%s, scheduler_cadence=%s, lag_alert_seconds=%s,
                  policy_json=%s::jsonb, updated_by_user_id=%s, updated_at=now()
                WHERE company_code=%s RETURNING *
                """,
                (
                    merged.get("tier") or "small",
                    merged.get("timezone") or "Asia/Kuwait",
                    int(merged.get("notice_hint_monthly_days") or 90),
                    int(merged.get("notice_hint_other_days") or 30),
                    merged.get("revoke_mode") or "end_of_last_working_day",
                    merged.get("effective_time_mode") or "start_of_effective_date",
                    merged.get("downstream_mode") or "warn_first",
                    bool(merged.get("require_impact_ack", True)),
                    bool(merged.get("require_counsel_gate", True)),
                    bool(merged.get("rehire_same_employee_key", True)),
                    merged.get("scheduler_cadence") or "hourly",
                    int(merged.get("lag_alert_seconds") or 7200),
                    json.dumps(_jsonable(pj)),
                    context.get("actor_user_id"),
                    company,
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return _normalize_policy(row)


def counsel_gate_status(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_lifecycle_counsel_reviews
                WHERE company_code=%s AND checklist_version=%s AND status='signed'
                ORDER BY signed_at DESC LIMIT 1
                """,
                (company, SCHEMA_VERSION),
            )
            row = cur.fetchone()
            conn.commit()
    signed = dict(row) if row else None
    return {
        "company_code": company,
        "checklist_version": SCHEMA_VERSION,
        "required_questions": COUNSEL_QUESTIONS,
        "signed": bool(signed),
        "review": _jsonable(signed) if signed else None,
        "production_gate": "blocked_until_signed" if not signed else "counsel_recorded",
        "note": "Recording a checklist is an operational gate, not a legal determination by the system.",
    }


def sign_counsel_checklist(
    legacy: Any,
    context: dict[str, Any],
    *,
    answers: dict[str, Any],
    signed_by_name: str,
    signed_by_role: str,
    signed_reference: str,
    notes: str | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    missing = [q["id"] for q in COUNSEL_QUESTIONS if q["id"] not in (answers or {})]
    if missing:
        raise legacy.HTTPException(status_code=422, detail={"error": "counsel_checklist_incomplete", "missing": missing})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_lifecycle_counsel_reviews (
                  company_code, checklist_version, answers, signed_by_name, signed_by_role,
                  signed_reference, notes, status
                ) VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,'signed')
                ON CONFLICT (company_code, checklist_version) DO UPDATE SET
                  answers=EXCLUDED.answers, signed_by_name=EXCLUDED.signed_by_name,
                  signed_by_role=EXCLUDED.signed_by_role, signed_reference=EXCLUDED.signed_reference,
                  notes=EXCLUDED.notes, signed_at=now(), status='signed'
                RETURNING *
                """,
                (
                    company,
                    SCHEMA_VERSION,
                    json.dumps(_jsonable(answers)),
                    signed_by_name.strip(),
                    signed_by_role.strip(),
                    signed_reference.strip(),
                    notes,
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "review": _jsonable(row), "production_gate": "counsel_recorded"}


def assert_counsel_gate(legacy: Any, *, company_code: str) -> None:
    policy = get_or_create_company_policy(legacy, company_code=company_code)
    if not policy.get("require_counsel_gate"):
        return
    gate_env = str(os.environ.get("WATHEFNI_LIFECYCLE_COUNSEL_GATE") or "on").strip().lower()
    if gate_env in {"0", "false", "no", "off"}:
        return
    status = counsel_gate_status(legacy, company_code=company_code)
    if not status.get("signed"):
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "counsel_gate_unsigned",
                "message": "Counsel checklist must be recorded before irreversible lifecycle mutations.",
                "checklist_version": SCHEMA_VERSION,
            },
        )


def compute_access_revoke_at(*, policy: dict[str, Any], termination_effective_on: date, last_working_day: date | None) -> datetime:
    tz = _company_tz(policy)
    mode = str(policy.get("revoke_mode") or "end_of_last_working_day")
    lwd = last_working_day or (termination_effective_on - timedelta(days=1))
    if mode == "start_of_effective_date":
        return datetime.combine(termination_effective_on, time(0, 0, 0), tzinfo=tz)
    if mode == "immediate_on_summary":
        return datetime.now(tz=tz)
    return datetime.combine(lwd, time(23, 59, 59), tzinfo=tz)


def _impact_hash(preview: dict[str, Any]) -> str:
    body = {
        "as_of_date": preview.get("as_of_date"),
        "employee_key": preview.get("employee_key"),
        "domains": preview.get("domains"),
        "snapshot_id": preview.get("snapshot_id"),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
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
    impact_ack: bool = False,
    impact_ack_text: str | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    if not lifecycle_v3_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "lifecycle_disabled"})
    policy = get_or_create_company_policy(legacy, company_code=company)
    case_type = str(case_type or "").strip().lower()
    if case_type == "reversal":
        raise legacy.HTTPException(
            status_code=422,
            detail={"error": "use_cancel_scheduled_or_reinstate", "message": "Use cancel_scheduled or reinstate."},
        )
    if case_type not in CASE_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_case_type"})
    irreversible = case_type in {"termination", "cancel_scheduled", "reinstate", "rehire", "suspension", "downstream_action"}
    if irreversible:
        assert_counsel_gate(legacy, company_code=company)
    if policy.get("require_impact_ack") and case_type in {"termination", "cancel_scheduled", "reinstate", "rehire", "downstream_action"}:
        if not impact_ack:
            raise legacy.HTTPException(status_code=422, detail={"error": "impact_ack_required"})
        if not str(impact_ack_text or "").strip():
            raise legacy.HTTPException(status_code=422, detail={"error": "impact_ack_text_required"})

    body = dict(payload or {})
    _assert_kuwait_jurisdiction(legacy, policy=policy, payload=body)
    if case_type == "termination":
        eff = body.get("termination_effective_on") or body.get("effective_on")
        if not eff:
            raise legacy.HTTPException(status_code=422, detail={"error": "effective_date_required"})
        if policy.get("require_last_working_day") and not body.get("last_working_day"):
            raise legacy.HTTPException(
                status_code=422,
                detail={
                    "error": "last_working_day_required",
                    "message": "HR must enter both effective date and last working day.",
                },
            )
    body["policy_snapshot"] = {
        "tier": policy.get("tier"),
        "timezone": policy.get("timezone"),
        "revoke_mode": policy.get("revoke_mode"),
        "downstream_mode": policy.get("downstream_mode"),
        "show_notice_hints": bool(policy.get("show_notice_hints")),
        "allow_reinstate_after_effective": bool(policy.get("allow_reinstate_after_effective")),
        "jurisdiction_mode": policy.get("jurisdiction_mode"),
        "document_retention_mode": policy.get("document_retention_mode"),
        "monetary_calculations_owner": policy.get("monetary_calculations_owner") or "payroll",
        "disclaimer": policy.get("disclaimer") or DEFAULT_POLICY["disclaimer"],
        "wave": "wave3d",
    }
    wave3_case = case_type
    if case_type == "cancel_scheduled":
        wave3_case = "reversal"
        body.setdefault("restore_state", "active")
        body["wave3c_case"] = "cancel_scheduled"
    elif case_type == "reinstate":
        if not policy.get("allow_reinstate_after_effective"):
            raise legacy.HTTPException(
                status_code=422,
                detail={
                    "error": "reinstate_disabled_by_policy",
                    "message": (
                        "Post-effective reinstatement is disabled by default. "
                        "Use true rehire unless allow_reinstate_after_effective is explicitly enabled."
                    ),
                },
            )
        wave3_case = "reversal"
        body.setdefault("restore_state", "active")
        body["wave3c_case"] = "reinstate"
        if not str(approval_reference or "").strip():
            raise legacy.HTTPException(status_code=422, detail={"error": "reinstate_requires_approval_reference"})

    as_of = date.today()
    if case_type == "termination":
        as_of = date.fromisoformat(str(body.get("termination_effective_on") or body.get("effective_on")))
    impact = preview_downstream_impact(legacy, company_code=company, employee_key=employee_key, as_of_date=as_of)
    snap_hash = _impact_hash(impact)
    result = wave3_create_lifecycle_request(
        legacy,
        context,
        employee_key=employee_key,
        case_type=wave3_case,
        reason=reason,
        approval_reference=approval_reference,
        designated_approver_user_id=designated_approver_user_id,
        idempotency_key=idempotency_key,
        expected_lifecycle_state=expected_lifecycle_state,
        expected_lifecycle_version=expected_lifecycle_version,
        expected_hub_updated_at=expected_hub_updated_at,
        payload=body,
    )
    if result.get("idempotent"):
        return {**result, "impact_snapshot_hash": snap_hash, "wave3c": True}
    req = result.get("request") or {}
    request_id = req.get("request_id")
    actor = str(context.get("actor_user_id") or "")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            if case_type in {"cancel_scheduled", "reinstate"}:
                cur.execute("UPDATE employee_lifecycle_cases SET case_type=%s, updated_at=now() WHERE case_id=%s", (case_type, req.get("case_id")))
                cur.execute("UPDATE employee_lifecycle_requests SET case_type=%s, updated_at=now() WHERE request_id=%s", (case_type, request_id))
            cur.execute(
                """
                UPDATE employee_lifecycle_requests SET
                  impact_snapshot_id=%s, impact_snapshot_hash=%s, impact_ack_at=now(),
                  impact_ack_by_user_id=%s, impact_ack_text=%s, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (impact.get("snapshot_id"), snap_hash, actor, str(impact_ack_text or "").strip()[:500], request_id),
            )
            updated = dict(cur.fetchone())
            conn.commit()
    result["request"] = _jsonable(updated)
    result["impact"] = impact
    result["impact_snapshot_hash"] = snap_hash
    result["wave3c"] = True
    result["case_type"] = case_type
    return result
def decide_lifecycle_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
    action: str,
    decision_reason: str | None = None,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                "SELECT * FROM employee_lifecycle_requests WHERE company_code=%s AND request_id=%s",
                (company, request_id),
            )
            req = cur.fetchone()
            conn.commit()
    if not req:
        raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
    req = dict(req)
    case_type = str(req.get("case_type") or "")
    payload = req.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    if action == "approve" and case_type in {"cancel_scheduled", "reinstate"}:
        return _decide_cancel_or_reinstate(
            legacy, context, req=req, action=action, decision_reason=decision_reason, payload=payload
        )
    if action == "approve" and case_type == "rehire":
        return _decide_rehire_same_key(legacy, context, req=req, decision_reason=decision_reason, payload=payload)
    if action == "approve" and case_type == "termination":
        out = wave3_decide_lifecycle_request(
            legacy, context, request_id=request_id, action=action, decision_reason=decision_reason
        )
        if out.get("committed"):
            _post_termination_hooks(legacy, context, req=req, decide_result=out, payload=payload)
        return {**out, "wave3c": True}
    out = wave3_decide_lifecycle_request(
        legacy, context, request_id=request_id, action=action, decision_reason=decision_reason
    )
    return {**out, "wave3c": True}


def _decide_cancel_or_reinstate(
    legacy: Any,
    context: dict[str, Any],
    *,
    req: dict[str, Any],
    action: str,
    decision_reason: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    actor = str(context.get("actor_user_id") or "").strip()
    if not legacy.dashboard_context_has_permission(context, "employees.status.approve"):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
    if str(req.get("designated_approver_user_id")) != actor:
        raise legacy.HTTPException(status_code=403, detail={"error": "not_designated_approver"})
    if str(req.get("requester_user_id")) == actor:
        raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
    if req.get("status") != "pending":
        raise legacy.HTTPException(status_code=409, detail={"error": "request_not_pending"})
    case_type = str(req.get("case_type"))
    if case_type == "reinstate":
        policy = get_or_create_company_policy(legacy, company_code=company)
        if not policy.get("allow_reinstate_after_effective"):
            raise legacy.HTTPException(
                status_code=422,
                detail={
                    "error": "reinstate_disabled_by_policy",
                    "message": (
                        "Post-effective reinstatement is disabled by default. "
                        "Use true rehire unless allow_reinstate_after_effective is explicitly enabled."
                    ),
                },
            )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            employment = _load_employment(cur, company=company, employee_key=req["employee_key"])
            if not _ts_equal(employment.get("hub_updated_at"), req.get("expected_hub_updated_at")):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})
            if int(employment.get("lifecycle_version") or 1) != int(req.get("expected_lifecycle_version") or 0):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})
            state = str(employment.get("lifecycle_state") or "active")
            if case_type == "cancel_scheduled":
                if state != "notice_period":
                    raise legacy.HTTPException(status_code=409, detail={"error": "cancel_scheduled_requires_notice_period"})
                event_type = "termination_cancelled_before_effective"
            else:
                if state != "terminated":
                    raise legacy.HTTPException(status_code=409, detail={"error": "reinstate_requires_terminated"})
                event_type = "employment_reinstated_after_effective"
            applied = _apply_transition(
                cur,
                company=company,
                employment=employment,
                to_state=str(payload.get("restore_state") or "active"),
                event_type=event_type,
                actor_user_id=actor,
                case_id=req["case_id"],
                request_id=req["request_id"],
                effective_on=date.today(),
                last_working_day=None,
                termination_type=None,
                reason=str(req.get("reason") or ""),
                payload={**payload, "wave3c_case": case_type, "silent_downstream_restore": False},
            )
            if case_type == "reinstate":
                cur.execute(
                    """
                    UPDATE employee_employments SET
                      access_revoke_status=COALESCE(access_revoke_status, 'revoked'), updated_at=now()
                    WHERE employment_id=%s
                    """,
                    (employment["employment_id"],),
                )
            else:
                cur.execute(
                    """
                    UPDATE employee_employments SET
                      access_revoke_at=NULL, access_revoked_at=NULL, access_revoke_status=NULL, updated_at=now()
                    WHERE employment_id=%s
                    """,
                    (employment["employment_id"],),
                )
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='executed', decided_by_user_id=%s, decided_at=now(), executed_at=now(),
                    decision_reason=%s, resulting_event_id=%s, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (actor, decision_reason or "approved", applied["event"]["event_id"], req["request_id"]),
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
        "case_type": case_type,
        "request": _jsonable(updated),
        "event": _jsonable(applied["event"]),
        "employment": _jsonable(applied["employment"]),
        "hub": _jsonable(applied["hub"]),
        "note": (
            "Reinstate does not silently restore sessions, shifts, leave, or onboarding."
            if case_type == "reinstate"
            else "Scheduled termination cancelled; same employment preserved."
        ),
        "wave3c": True,
    }


def _post_termination_hooks(legacy: Any, context: dict[str, Any], *, req: dict[str, Any], decide_result: dict[str, Any], payload: dict[str, Any]) -> None:
    company = str(context.get("company_code") or "").upper()
    policy = get_or_create_company_policy(legacy, company_code=company)
    eff = payload.get("termination_effective_on") or payload.get("effective_on")
    lwd = payload.get("last_working_day")
    if not eff:
        return
    eff_d = date.fromisoformat(str(eff))
    lwd_d = date.fromisoformat(str(lwd)) if lwd else None
    revoke_at = compute_access_revoke_at(policy=policy, termination_effective_on=eff_d, last_working_day=lwd_d)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                UPDATE employee_employments SET
                  access_revoke_at=%s, access_revoke_status='scheduled', updated_at=now()
                WHERE company_code=%s AND employment_id=%s
                """,
                (revoke_at, company, req["employment_id"]),
            )
            packet = {
                "company_code": company,
                "employee_key": req["employee_key"],
                "person_id": str(req["person_id"]),
                "employment_id": str(req["employment_id"]),
                "termination_effective_on": eff_d.isoformat(),
                "last_working_day": (lwd_d.isoformat() if lwd_d else None),
                "termination_type": payload.get("termination_type"),
                "termination_reason": req.get("reason"),
                "impact_snapshot_id": str(req.get("impact_snapshot_id") or ""),
                "impact_snapshot_hash": req.get("impact_snapshot_hash"),
                "inputs": {
                    "leave_balance_refs": "see_impact_snapshot",
                    "open_timesheet_refs": "see_impact_snapshot",
                    "attendance_exception_refs": "see_impact_snapshot",
                },
                "document_retention_mode": policy.get("document_retention_mode") or "retain",
                "monetary_calculations_owner": policy.get("monetary_calculations_owner") or "payroll",
                "disclaimer": (
                    "Inputs only. No EOSB, notice pay, garden leave, or leave encashment "
                    "calculated in Employees 360. Payroll owns monetary calculations."
                ),
            }
            if "amounts" in packet:
                raise RuntimeError("settlement_packet_must_not_contain_amounts")
            cur.execute(
                """
                INSERT INTO employee_lifecycle_settlement_packets (
                  company_code, employee_key, person_id, employment_id, case_id, request_id,
                  status, packet, handed_off_at
                ) VALUES (%s,%s,%s,%s,%s,%s,'handed_to_payroll',%s::jsonb,now())
                """,
                (
                    company,
                    req["employee_key"],
                    req["person_id"],
                    req["employment_id"],
                    req["case_id"],
                    req["request_id"],
                    json.dumps(_jsonable(packet)),
                ),
            )
            conn.commit()
def open_same_key_rehire(
    legacy: Any,
    *,
    company_code: str,
    person_id: str,
    employee_key: str,
    prior_employment_id: str,
    phone: str,
    name: str,
    position_title: str | None = None,
    app_key: str | None = None,
) -> dict[str, Any]:
    company = str(company_code).upper()
    key = str(employee_key)
    digits = phone_digits(phone) or phone
    rehire_token = uuid.uuid4().hex[:10]
    employment_id = mint_employment_id(company_code=company, employee_key=f"{key}:rehire:{rehire_token}")
    assignment_id = mint_assignment_id(company_code=company, employee_key=key, slot=f"rehire-{rehire_token}")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                UPDATE employee_employments
                SET lifecycle_state='terminated', employment_status='left',
                    end_date=COALESCE(end_date, CURRENT_DATE),
                    legacy_employee_key=NULL,
                    provenance = coalesce(provenance,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE company_code=%s AND employment_id=%s RETURNING *
                """,
                (
                    json.dumps(
                        {
                            "superseded_by_rehire": True,
                            "released_legacy_employee_key": key,
                        }
                    ),
                    company,
                    prior_employment_id,
                ),
            )
            if not cur.fetchone():
                raise KeyError("prior_employment_not_found")
            cur.execute(
                """
                INSERT INTO employee_employments (
                  employment_id, company_code, person_id, employment_status, lifecycle_state,
                  start_date, hire_source, app_key, legacy_employee_key, provenance, lifecycle_version
                ) VALUES (%s,%s,%s,'active','active',CURRENT_DATE,'rehire',%s,%s,%s::jsonb,1)
                RETURNING *
                """,
                (
                    employment_id,
                    company,
                    person_id,
                    app_key,
                    key,
                    json.dumps({"source": "wave3c_same_key_rehire", "prior_employment_id": str(prior_employment_id), "rehire_token": rehire_token}),
                ),
            )
            employment = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_assignments (
                  assignment_id, company_code, employment_id, person_id, is_primary, position_title, provenance
                ) VALUES (%s,%s,%s,%s,true,%s,%s::jsonb) RETURNING *
                """,
                (assignment_id, company, employment_id, person_id, position_title, json.dumps({"source": "wave3c_same_key_rehire", "rehire_token": rehire_token})),
            )
            assignment = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE employee_key_authority_map SET
                  employment_id=%s, assignment_id=%s, mapping_status='active',
                  provenance = coalesce(provenance,'{}'::jsonb) || %s::jsonb, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                """,
                (employment_id, assignment_id, json.dumps({"rehire": True, "prior_employment_id": str(prior_employment_id)}), company, key),
            )
            cur.execute(
                """
                UPDATE employees SET
                  person_id=%s, employment_id=%s, assignment_id=%s, employment_status='active',
                  name=COALESCE(%s, name), phone=COALESCE(%s, phone),
                  position_title=COALESCE(%s, position_title), updated_at=clock_timestamp()
                WHERE company_code=%s AND employee_key=%s RETURNING *
                """,
                (person_id, employment_id, assignment_id, name, digits, position_title, company, key),
            )
            hub = dict(cur.fetchone())
            cur.execute(
                "SELECT count(*)::bigint AS n FROM employee_employments WHERE company_code=%s AND person_id=%s",
                (company, person_id),
            )
            history_n = int(dict(cur.fetchone())["n"])
            conn.commit()
    return {
        "ok": True,
        "same_employee_key": True,
        "employee_key": key,
        "person_id": person_id,
        "prior_employment_id": str(prior_employment_id),
        "employment": _jsonable(employment),
        "assignment": _jsonable(assignment),
        "employee": _jsonable(hub),
        "employment_history_count": history_n,
    }


def _decide_rehire_same_key(legacy: Any, context: dict[str, Any], *, req: dict[str, Any], decision_reason: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    actor = str(context.get("actor_user_id") or "").strip()
    policy = get_or_create_company_policy(legacy, company_code=company)
    if not legacy.dashboard_context_has_permission(context, "employees.status.approve"):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
    if str(req.get("designated_approver_user_id")) != actor:
        raise legacy.HTTPException(status_code=403, detail={"error": "not_designated_approver"})
    if str(req.get("requester_user_id")) == actor:
        raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
    if req.get("status") != "pending":
        raise legacy.HTTPException(status_code=409, detail={"error": "request_not_pending"})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            employment = _load_employment(cur, company=company, employee_key=req["employee_key"])
            if str(employment.get("lifecycle_state")) != "terminated":
                raise legacy.HTTPException(status_code=409, detail={"error": "rehire_requires_terminated_employment"})
            if not _ts_equal(employment.get("hub_updated_at"), req.get("expected_hub_updated_at")):
                raise legacy.HTTPException(status_code=409, detail={"error": "employee_version_conflict"})
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='approved', decided_by_user_id=%s, decided_at=now(), decision_reason=%s, updated_at=now()
                WHERE request_id=%s AND status='pending'
                """,
                (actor, decision_reason or "approved", req["request_id"]),
            )
            conn.commit()
    phone = str(payload.get("phone") or "")
    if not phone:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (req["employee_key"],))
                phone = str(dict(cur.fetchone() or {}).get("phone") or "")
            conn.commit()
    if not phone:
        raise legacy.HTTPException(status_code=422, detail={"error": "rehire_phone_required"})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (req["employee_key"],))
            hub_phone = phone_digits(dict(cur.fetchone() or {}).get("phone"))
        conn.commit()
    payload_digits = phone_digits(phone)
    # Prefer hub phone when payload phone omitted or matches identity; same-key when digits equal.
    if not payload.get("phone"):
        phone = hub_phone or phone
        payload_digits = phone_digits(phone)
    same_identity = bool(policy.get("rehire_same_employee_key", True)) and bool(payload_digits) and payload_digits == hub_phone
    if same_identity and not payload.get("force_new_employee_key") and not payload.get("new_employee_key"):
        result = open_same_key_rehire(
            legacy,
            company_code=company,
            person_id=str(req["person_id"]),
            employee_key=str(req["employee_key"]),
            prior_employment_id=str(req["employment_id"]),
            phone=phone,
            name=str(payload.get("name") or "Rehired employee"),
            position_title=payload.get("position_title"),
            app_key=payload.get("app_key"),
        )
        new_employment_id = result["employment"]["employment_id"]
        new_assignment_id = result["assignment"]["assignment_id"]
        new_key = str(req["employee_key"])
    else:
        from employee_lifecycle_wave3 import _execute_rehire_after_approval
        return _execute_rehire_after_approval(legacy, context, req=req, actor=actor, payload=payload)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_lifecycle_events (
                  company_code, case_id, request_id, employee_key, person_id, employment_id,
                  from_state, to_state, event_type, effective_on, reason, actor_user_id, payload
                ) VALUES (%s,%s,%s,%s,%s,%s,'terminated','active','rehired_same_key',CURRENT_DATE,%s,%s,%s::jsonb)
                RETURNING *
                """,
                (
                    company,
                    req["case_id"],
                    req["request_id"],
                    new_key,
                    req["person_id"],
                    new_employment_id,
                    str(req.get("reason") or ""),
                    actor,
                    json.dumps(_jsonable({"prior_employment_id": str(req["employment_id"]), "same_employee_key": True, "new_assignment_id": new_assignment_id})),
                ),
            )
            event = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE employee_lifecycle_requests
                SET status='executed', decided_by_user_id=%s, decided_at=COALESCE(decided_at, now()),
                    executed_at=now(), resulting_event_id=%s, updated_at=now()
                WHERE request_id=%s AND status IN ('pending','approved') RETURNING *
                """,
                (actor, event["event_id"], req["request_id"]),
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
        "rehire": True,
        "same_employee_key": True,
        "request": _jsonable(updated),
        "event": _jsonable(event),
        "person_id": str(req["person_id"]),
        "prior_employment_id": str(req["employment_id"]),
        "new_employment_id": str(new_employment_id),
        "new_assignment_id": str(new_assignment_id),
        "employee_key": new_key,
        "employment_history_count": result.get("employment_history_count"),
        "wave3c": True,
    }
def revoke_due_app_access(legacy: Any, *, company_code: str, now: datetime | None = None) -> dict[str, Any]:
    company = str(company_code).upper()
    policy = get_or_create_company_policy(legacy, company_code=company)
    tz = _company_tz(policy)
    now_local = now or datetime.now(tz=tz)
    revoked = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                SELECT e.employment_id, m.employee_key, e.access_revoke_at
                FROM employee_employments e
                JOIN employee_key_authority_map m
                  ON m.employment_id=e.employment_id AND m.company_code=e.company_code
                WHERE e.company_code=%s
                  AND e.access_revoke_status='scheduled'
                  AND e.access_revoke_at IS NOT NULL
                  AND e.access_revoke_at <= %s
                FOR UPDATE OF e
                """,
                (company, now_local),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            for row in rows:
                key = row["employee_key"]
                cur.execute(
                    """
                    UPDATE employee_sessions
                    SET status='revoked', refresh_hash=NULL, revoked_at=now(),
                        revoked_reason='lifecycle_access_revoke',
                        expires_at=LEAST(expires_at, now()),
                        refresh_expires_at=LEAST(refresh_expires_at, now())
                    WHERE company_code=%s AND employee_key=%s AND status='active'
                    """,
                    (company, key),
                )
                sessions_n = int(cur.rowcount or 0)
                cur.execute(
                    """
                    UPDATE employee_app_invites
                    SET status='superseded', updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                      AND lower(coalesce(status,'')) IN ('pending','sent','active')
                    """,
                    (company, key),
                )
                invites_n = int(cur.rowcount or 0)
                cur.execute(
                    """
                    UPDATE employee_employments SET
                      access_revoke_status='revoked', access_revoked_at=now(), updated_at=now()
                    WHERE employment_id=%s
                    """,
                    (row["employment_id"],),
                )
                cur.execute(
                    """
                    INSERT INTO employee_lifecycle_events (
                      company_code, employee_key, person_id, employment_id,
                      from_state, to_state, event_type, reason, payload
                    )
                    SELECT %s, %s, e.person_id, e.employment_id,
                           e.lifecycle_state, e.lifecycle_state, 'access_revoked',
                           'scheduled_access_revoke', %s::jsonb
                    FROM employee_employments e WHERE e.employment_id=%s
                    """,
                    (company, key, json.dumps({"sessions": sessions_n, "invites": invites_n, "at": now_local.isoformat()}), row["employment_id"]),
                )
                revoked.append({"employee_key": key, "sessions": sessions_n, "invites": invites_n})
            conn.commit()
    return {"ok": True, "revoked": revoked, "count": len(revoked), "as_of": now_local.isoformat()}


def create_downstream_action_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    action_type: str,
    reason: str,
    designated_approver_user_id: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    impact_ack: bool = False,
    impact_ack_text: str | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    _require_scope(legacy, context, employee_key)
    assert_counsel_gate(legacy, company_code=company)
    action_type = str(action_type or "").strip().lower()
    if action_type not in DOWNSTREAM_ACTION_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_downstream_action"})
    if not impact_ack or not str(impact_ack_text or "").strip():
        raise legacy.HTTPException(status_code=422, detail={"error": "impact_ack_required"})
    requester = str(context.get("actor_user_id") or "")
    approver = str(designated_approver_user_id or "")
    if not requester or requester == approver:
        raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
    proj = get_lifecycle_projection(legacy, company_code=company, employee_key=employee_key)
    if not proj:
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    body = payload or {}
    hash_payload = {
        "company_code": company,
        "employee_key": employee_key,
        "action_type": action_type,
        "reason": reason.strip(),
        "idempotency_key": idempotency_key.strip(),
        "payload": body,
        "requester_user_id": requester,
        "designated_approver_user_id": approver,
    }
    rhash = _request_hash(hash_payload)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            import employee_status_approval as status_approval
            status_approval.ensure_employee_status_approval_schema(cur)
            eligible = status_approval.list_eligible_status_approvers(legacy, cur, company_code=company, exclude_user_id=requester)
            if not any(str(a.get("user_id")) == approver for a in eligible):
                raise legacy.HTTPException(status_code=403, detail={"error": "approver_not_eligible"})
            cur.execute(
                "SELECT * FROM employee_lifecycle_downstream_actions WHERE company_code=%s AND idempotency_key=%s",
                (company, idempotency_key.strip()),
            )
            existing = cur.fetchone()
            if existing:
                ex = dict(existing)
                if str(ex.get("request_hash")) != rhash:
                    raise legacy.HTTPException(status_code=409, detail={"error": "idempotency_conflict"})
                conn.commit()
                return {"ok": True, "idempotent": True, "action": _jsonable(ex)}
            cur.execute(
                """
                INSERT INTO employee_lifecycle_downstream_actions (
                  company_code, employee_key, employment_id, action_type, status,
                  idempotency_key, request_hash, payload, requester_user_id, designated_approver_user_id
                ) VALUES (%s,%s,%s,%s,'pending',%s,%s,%s::jsonb,%s,%s) RETURNING *
                """,
                (
                    company,
                    employee_key,
                    proj["employment_id"],
                    action_type,
                    idempotency_key.strip(),
                    rhash,
                    json.dumps(_jsonable({**body, "reason": reason, "impact_ack_text": impact_ack_text})),
                    requester,
                    approver,
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "idempotent": False, "action": _jsonable(row)}


def _execute_downstream_action(cur, *, company: str, req: dict[str, Any]) -> dict[str, Any]:
    action_type = str(req.get("action_type"))
    key = req["employee_key"]
    today = date.today()
    if action_type == "cancel_future_shifts":
        cur.execute(
            """
            UPDATE shift_assignments
            SET status='cancelled_lifecycle', updated_at=now(),
                notes=COALESCE(notes,'') || ' [lifecycle cancel]'
            WHERE company_code=%s AND employee_key=%s AND shift_date >= %s
              AND lower(coalesce(status,'')) NOT IN ('cancelled','cancelled_lifecycle')
            RETURNING shift_id
            """,
            (company, key, today),
        )
        return {"cancelled_shift_ids": [str(dict(r)["shift_id"]) for r in (cur.fetchall() or [])], "reversible": True}
    if action_type == "reverse_cancel_future_shifts":
        cur.execute(
            """
            UPDATE shift_assignments SET status='scheduled', updated_at=now()
            WHERE company_code=%s AND employee_key=%s AND status='cancelled_lifecycle' RETURNING shift_id
            """,
            (company, key),
        )
        return {"restored_shift_ids": [str(dict(r)["shift_id"]) for r in (cur.fetchall() or [])]}
    if action_type == "decline_open_leave":
        cur.execute(
            """
            UPDATE leave_requests
            SET status='declined_lifecycle', decision_note='lifecycle downstream action', decided_at=now(), updated_at=now()
            WHERE company_code=%s AND employee_key=%s
              AND lower(coalesce(status,'')) IN ('pending','requested','open','approved')
              AND coalesce(end_date, start_date) >= %s
            RETURNING leave_id
            """,
            (company, key, today),
        )
        return {"declined_leave_ids": [str(dict(r)["leave_id"]) for r in (cur.fetchall() or [])], "reversible": True}
    if action_type == "reverse_decline_open_leave":
        cur.execute(
            """
            UPDATE leave_requests SET status='pending', decision_note='lifecycle reverse', updated_at=now()
            WHERE company_code=%s AND employee_key=%s AND status='declined_lifecycle' RETURNING leave_id
            """,
            (company, key),
        )
        return {"restored_leave_ids": [str(dict(r)["leave_id"]) for r in (cur.fetchall() or [])]}
    if action_type == "abandon_onboarding":
        try:
            cur.execute(
                """
                UPDATE onboarding_items SET status='abandoned_employment_ended', updated_at=now()
                WHERE employee_key=%s AND lower(coalesce(status,'')) IN ('pending','in_progress','open')
                RETURNING item_id
                """,
                (key,),
            )
            ids = [str(dict(r).get("item_id") or dict(r).get("id")) for r in (cur.fetchall() or [])]
        except Exception:
            ids = []
        return {"abandoned_onboarding_ids": ids, "reversible": True}
    if action_type == "reverse_abandon_onboarding":
        try:
            cur.execute(
                """
                UPDATE onboarding_items SET status='pending', updated_at=now()
                WHERE employee_key=%s AND status='abandoned_employment_ended' RETURNING item_id
                """,
                (key,),
            )
            ids = [str(dict(r).get("item_id") or dict(r).get("id")) for r in (cur.fetchall() or [])]
        except Exception:
            ids = []
        return {"restored_onboarding_ids": ids}
    if action_type == "revoke_app_access":
        cur.execute(
            """
            UPDATE employee_sessions
            SET status='revoked', refresh_hash=NULL, revoked_at=now(),
                revoked_reason='lifecycle_downstream_revoke',
                expires_at=LEAST(expires_at, now()), refresh_expires_at=LEAST(refresh_expires_at, now())
            WHERE company_code=%s AND employee_key=%s AND status='active'
            """,
            (company, key),
        )
        return {"sessions_revoked": int(cur.rowcount or 0), "reversible_via": "restore_app_access"}
    if action_type == "restore_app_access":
        cur.execute(
            """
            UPDATE employee_employments SET
              access_revoke_status='restored_eligible', access_revoked_at=NULL, updated_at=now()
            WHERE company_code=%s AND employment_id=%s
            """,
            (company, req["employment_id"]),
        )
        return {"restored_eligible": True, "note": "Prior sessions stay revoked; new invite/session required."}
    if action_type == "resolve_attendance_hold":
        return {"note": "Attendance exceptions remain for human resolution; no auto payroll decision.", "automatic": False}
    raise ValueError(f"unsupported_action:{action_type}")


def decide_downstream_action(
    legacy: Any,
    context: dict[str, Any],
    *,
    action_id: str,
    action: str,
    decision_reason: str | None = None,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    actor = str(context.get("actor_user_id") or "").strip()
    decision = str(action or "").lower()
    if decision not in {"approve", "reject"}:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_action"})
    if not legacy.dashboard_context_has_permission(context, "employees.status.approve"):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                "SELECT * FROM employee_lifecycle_downstream_actions WHERE company_code=%s AND action_id=%s FOR UPDATE",
                (company, action_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "action_not_found"})
            req = dict(row)
            if str(req.get("designated_approver_user_id")) != actor:
                raise legacy.HTTPException(status_code=403, detail={"error": "not_designated_approver"})
            if str(req.get("requester_user_id")) == actor:
                raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
            if req.get("status") != "pending":
                raise legacy.HTTPException(status_code=409, detail={"error": "action_not_pending"})
            if decision == "reject":
                cur.execute(
                    """
                    UPDATE employee_lifecycle_downstream_actions
                    SET status='rejected', decided_by_user_id=%s, decided_at=now(), updated_at=now()
                    WHERE action_id=%s RETURNING *
                    """,
                    (actor, action_id),
                )
                updated = dict(cur.fetchone())
                conn.commit()
                return {"ok": True, "decision": "reject", "action": _jsonable(updated)}
            result = _execute_downstream_action(cur, company=company, req=req)
            cur.execute(
                """
                UPDATE employee_lifecycle_downstream_actions
                SET status='executed', decided_by_user_id=%s, decided_at=now(), executed_at=now(),
                    result=%s::jsonb, updated_at=now()
                WHERE action_id=%s RETURNING *
                """,
                (actor, json.dumps(_jsonable(result)), action_id),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_lifecycle_events (
                  company_code, employee_key, person_id, employment_id,
                  from_state, to_state, event_type, reason, actor_user_id, payload
                )
                SELECT %s, %s, e.person_id, e.employment_id, e.lifecycle_state, e.lifecycle_state,
                       %s, %s, %s, %s::jsonb
                FROM employee_employments e WHERE e.employment_id=%s
                """,
                (
                    company,
                    req["employee_key"],
                    f"downstream_{req['action_type']}",
                    decision_reason or "approved_downstream_action",
                    actor,
                    json.dumps(_jsonable({"action_id": action_id, "result": result})),
                    req["employment_id"],
                ),
            )
            conn.commit()
    return {"ok": True, "decision": "approve", "committed": True, "action": _jsonable(updated), "result": result}


def compute_scheduler_lag(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    policy = get_or_create_company_policy(legacy, company_code=company)
    tz = _company_tz(policy)
    now_local = datetime.now(tz=tz)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                SELECT termination_effective_on FROM employee_employments
                WHERE company_code=%s AND lifecycle_state='notice_period'
                  AND termination_effective_on IS NOT NULL AND termination_effective_on <= %s
                """,
                (company, now_local.date()),
            )
            due = [dict(r) for r in (cur.fetchall() or [])]
            lag = 0
            for row in due:
                eff = row["termination_effective_on"]
                eff_d = eff.date() if isinstance(eff, datetime) else eff
                seconds = int((now_local - datetime.combine(eff_d, time(0, 0), tzinfo=tz)).total_seconds())
                lag = max(lag, max(0, seconds))
            conn.commit()
    return {
        "company_code": company,
        "due_count": len(due),
        "lag_seconds": lag,
        "alert": lag >= int(policy.get("lag_alert_seconds") or 7200),
        "as_of": now_local.isoformat(),
    }


def run_lifecycle_scheduler(
    legacy: Any,
    *,
    company_code: str,
    environment: str | None = None,
    now: datetime | None = None,
    fail_before_commit: bool = False,
) -> dict[str, Any]:
    company = str(company_code).upper()
    if not lifecycle_v3_enabled(company):
        return {"ok": False, "error": "lifecycle_disabled"}
    env = environment or str(os.environ.get("WATHEFNI_ENV") or "staging")
    run_id = None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_lifecycle_scheduler_runs (company_code, environment, status)
                VALUES (%s,%s,'started') RETURNING run_id
                """,
                (company, env),
            )
            run_id = str(dict(cur.fetchone())["run_id"])
            conn.commit()
    try:
        if fail_before_commit:
            raise RuntimeError("injected_scheduler_failure")
        term = wave3_execute_due(legacy, company_code=company)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_wave3c_schema(cur)
                cur.execute(
                    """
                    UPDATE employee_lifecycle_events
                    SET payload = coalesce(payload,'{}'::jsonb) || %s::jsonb
                    WHERE company_code=%s AND event_type='termination_effective'
                      AND created_at >= now() - interval '15 minutes'
                      AND coalesce(payload->>'run_id','') = ''
                    """,
                    (json.dumps({"scheduler": True, "run_id": run_id}), company),
                )
                conn.commit()
        revoke = revoke_due_app_access(legacy, company_code=company, now=now)
        lag = compute_scheduler_lag(legacy, company_code=company)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_lifecycle_scheduler_runs SET
                      status='succeeded', finished_at=now(),
                      terminations_executed=%s, revokes_executed=%s, lag_seconds=%s,
                      evidence=%s::jsonb
                    WHERE run_id=%s RETURNING *
                    """,
                    (
                        int(term.get("count") or 0),
                        int(revoke.get("count") or 0),
                        int(lag.get("lag_seconds") or 0),
                        json.dumps(_jsonable({"term": term, "revoke": revoke, "lag": lag}), default=str),
                        run_id,
                    ),
                )
                run = dict(cur.fetchone())
                conn.commit()
        return {"ok": True, "run": _jsonable(run), "terminations": term, "revokes": revoke, "lag": lag}
    except Exception as exc:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_wave3c_schema(cur)
                cur.execute(
                    """
                    UPDATE employee_lifecycle_scheduler_runs SET
                      status='failed', finished_at=now(), error_text=%s WHERE run_id=%s
                    """,
                    (str(exc)[:500], run_id),
                )
                conn.commit()
        return {"ok": False, "run_id": run_id, "error": str(exc)}


def rollback_lifecycle_wave3c(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_wave3c_schema(cur)
            if employee_keys:
                keys = list(employee_keys)
                cur.execute(
                    "DELETE FROM employee_lifecycle_downstream_actions WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_lifecycle_settlement_packets WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    """
                    UPDATE employee_employments e SET
                      access_revoke_at=NULL, access_revoked_at=NULL, access_revoke_status=NULL
                    FROM employee_key_authority_map m
                    WHERE m.employment_id=e.employment_id AND m.company_code=e.company_code
                      AND m.company_code=%s AND m.employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
            conn.commit()
    base = rollback_lifecycle_wave3(
        legacy, company_code=company, idempotency_key=idempotency_key, employee_keys=employee_keys
    )
    return {**base, "wave3c": True}
