"""Employees 360 Wave 5 — employee & manager self-service (request authority).

Local/staging only. Request-based: never directly edits canonical employment,
lifecycle, or payroll authority. Assignment mutations apply only through Wave 4
effective-dated authority after approval. Jurisdiction/lifecycle remain Wave 3.

Flags:
  WATHEFNI_EMPLOYEE_ESS_V5=on
  WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI (default)

Approval and canonical application are separate steps.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

SCHEMA_VERSION = "employees360-wave5-selfservice-v1"

REQUEST_STATES = frozenset({
    "draft",
    "submitted",
    "needs_information",
    "pending_manager",
    "pending_hr",
    "pending_payroll",
    "approved",
    "applied",
    "rejected",
    "withdrawn",
    "failed",
})

# Employee-originated types
EMPLOYEE_REQUEST_TYPES = frozenset({
    "personal_detail_change",
    "emergency_contact_change",
    "bank_detail_change",
    "document_change",
    "employment_letter",
    "service_certificate",
})

# Manager-originated types (assignment → Wave 4 on apply)
MANAGER_REQUEST_TYPES = frozenset({
    "transfer",
    "manager_change",
    "assignment_correction",
})

ALL_REQUEST_TYPES = EMPLOYEE_REQUEST_TYPES | MANAGER_REQUEST_TYPES

DECISION_ACTIONS = frozenset({"approve", "reject", "return_for_information"})

# Sensitive field keys masked unless actor has unmask permission
SENSITIVE_FIELDS = frozenset({
    "iban",
    "bank_account",
    "bank_name",
    "civil_id",
    "national_id",
    "passport_number",
    "salary",
    "account_holder",
})

# Employment eligibility for new requests
TERMINAL_BLOCKED = frozenset({"terminated", "left"})
SUSPENDED_ALLOWED_TYPES = frozenset({
    "personal_detail_change",
    "emergency_contact_change",
    "document_change",
    "employment_letter",
    "service_certificate",
})
FUTURE_START_BLOCKED_TYPES = frozenset({
    "transfer",
    "manager_change",
    "assignment_correction",
    "bank_detail_change",
})

WAVE5_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_ess_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_ess_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid,
  request_type text NOT NULL,
  state text NOT NULL DEFAULT 'draft',
  requester_kind text NOT NULL,
  requester_user_id uuid,
  requester_employee_key text,
  proposed_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  old_value_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  approval_route jsonb NOT NULL DEFAULT '[]'::jsonb,
  approval_cursor int NOT NULL DEFAULT 0,
  comments jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  concurrency_version bigint NOT NULL DEFAULT 1,
  expected_hub_updated_at timestamptz,
  expected_assignment_version bigint,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  designated_approver_user_id uuid,
  applied_authority_ref jsonb,
  applied_at timestamptz,
  applied_by_user_id uuid,
  fail_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (state IN (
    'draft','submitted','needs_information','pending_manager','pending_hr',
    'pending_payroll','approved','applied','rejected','withdrawn','failed'
  )),
  CHECK (requester_kind IN ('employee','manager','hr')),
  UNIQUE (company_code, idempotency_key)
);

CREATE INDEX IF NOT EXISTS employee_ess_requests_employee_idx
  ON employee_ess_requests (company_code, employee_key, created_at DESC);
CREATE INDEX IF NOT EXISTS employee_ess_requests_state_idx
  ON employee_ess_requests (company_code, state, updated_at DESC);
CREATE INDEX IF NOT EXISTS employee_ess_requests_requester_idx
  ON employee_ess_requests (company_code, requester_employee_key, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_ess_request_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  request_id uuid NOT NULL REFERENCES employee_ess_requests(request_id) ON DELETE CASCADE,
  actor_user_id uuid,
  actor_employee_key text,
  action text NOT NULL,
  from_state text,
  to_state text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS employee_ess_request_events_req_idx
  ON employee_ess_request_events (request_id, created_at);

CREATE TABLE IF NOT EXISTS employee_ess_personal_profiles (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  emergency_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_request_id uuid,
  PRIMARY KEY (company_code, employee_key)
);

CREATE TABLE IF NOT EXISTS employee_ess_bank_profiles (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  bank_ciphertext jsonb NOT NULL DEFAULT '{}'::jsonb,
  bank_fingerprint text,
  version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_request_id uuid,
  PRIMARY KEY (company_code, employee_key)
);

CREATE TABLE IF NOT EXISTS employee_ess_document_versions (
  document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  document_key text NOT NULL,
  version_number int NOT NULL,
  storage_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  replaced_version_id uuid,
  request_id uuid,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, employee_key, document_key, version_number)
);

CREATE TABLE IF NOT EXISTS employee_ess_letter_orders (
  letter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  letter_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  request_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_ess_audit_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'ok',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, action, idempotency_key)
);
"""


def _flag_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name) or default).strip().lower() in {"on", "1", "true", "yes"}


def ess_v5_enabled(company_code: str | None = None) -> bool:
    if not _flag_on("WATHEFNI_EMPLOYEE_ESS_V5"):
        return False
    allow = str(os.environ.get("WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES") or "WATHEFNI")
    companies = {c.strip().upper() for c in allow.split(",") if c.strip()}
    if company_code is None:
        return bool(companies)
    return str(company_code).upper() in companies


def ensure_ess_wave5_schema(cur: Any) -> None:
    cur.execute(WAVE5_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO employee_ess_schema_meta (schema_name, schema_version)
        VALUES ('employees360_wave5', %s)
        ON CONFLICT (schema_name) DO UPDATE
          SET schema_version=EXCLUDED.schema_version, updated_at=now()
        """,
        (SCHEMA_VERSION,),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(
    cur: Any,
    *,
    company: str,
    request_id: str,
    action: str,
    from_state: str | None,
    to_state: str | None,
    actor_user_id: str | None = None,
    actor_employee_key: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO employee_ess_request_events (
          company_code, request_id, actor_user_id, actor_employee_key,
          action, from_state, to_state, detail
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company,
            request_id,
            actor_user_id,
            actor_employee_key,
            action,
            from_state,
            to_state,
            json.dumps(_jsonable(detail or {})),
        ),
    )


def _journal(
    cur: Any,
    *,
    company: str,
    action: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    status: str = "ok",
) -> None:
    cur.execute(
        """
        INSERT INTO employee_ess_audit_journal (company_code, action, idempotency_key, payload, status)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (company_code, action, idempotency_key) DO NOTHING
        """,
        (company, action, idempotency_key, json.dumps(_jsonable(payload or {})), status),
    )


def mask_sensitive(payload: dict[str, Any] | None, *, can_unmask: bool) -> dict[str, Any]:
    """Field-level masking for sensitive keys."""
    data = dict(payload or {})
    if can_unmask:
        return data
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = str(k)
        if key.lower() in SENSITIVE_FIELDS or key.lower().endswith("_iban"):
            if v is None or v == "":
                out[key] = v
            else:
                s = str(v)
                out[key] = ("*" * max(0, len(s) - 4)) + s[-4:] if len(s) >= 4 else "****"
                out[f"{key}__masked"] = True
        elif isinstance(v, dict):
            out[key] = mask_sensitive(v, can_unmask=False)
        else:
            out[key] = v
    return out


def _approval_route_for(request_type: str) -> list[str]:
    """Ordered approval stages. Application happens only after all stages approve."""
    if request_type == "bank_detail_change":
        return ["hr", "payroll"]
    if request_type in MANAGER_REQUEST_TYPES:
        return ["hr"]
    if request_type in {"employment_letter", "service_certificate", "document_change"}:
        return ["hr"]
    # personal / emergency
    return ["hr"]


def _pending_state_for_stage(stage: str) -> str:
    return {
        "manager": "pending_manager",
        "hr": "pending_hr",
        "payroll": "pending_payroll",
    }.get(stage, "pending_hr")


def _actor_user_id(context: dict[str, Any]) -> str | None:
    return str(context.get("actor_user_id") or (context.get("actor") or {}).get("user_id") or "") or None


def _has_perm(legacy: Any, context: dict[str, Any], perm: str) -> bool:
    return bool(legacy.dashboard_context_has_permission(context, perm))


def _can_unmask(legacy: Any, context: dict[str, Any]) -> bool:
    return _has_perm(legacy, context, "employees.ess.unmask") or _has_perm(legacy, context, "employees.manage")


def _require_ess(legacy: Any, context: dict[str, Any]) -> str:
    company = str(context.get("company_code") or "").upper()
    if not ess_v5_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "ess_v5_disabled"})
    return company


def _load_employee(legacy: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, employee_key),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
            return dict(row)


def _employment_projection(legacy: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    """Wave 2/3 employment + lifecycle snapshot (read-only)."""
    out: dict[str, Any] = {
        "employment_id": None,
        "employment_status": None,
        "lifecycle_state": None,
        "start_date": None,
        "end_date": None,
        "jurisdiction_code": None,
        "worker_category": None,
        "policy_pack_status": None,
        "eligibility": "active",
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employment_id::text, employment_status, lifecycle_state,
                       start_date, end_date, jurisdiction_code, worker_category,
                       policy_pack_status, suspended_on
                FROM employee_employments
                WHERE company_code=%s AND legacy_employee_key=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                (company, employee_key),
            )
            row = cur.fetchone()
            if row:
                out.update({k: (v.isoformat() if isinstance(v, date) and not isinstance(v, datetime) else v)
                            for k, v in dict(row).items()})
                # normalize dates
                for dk in ("start_date", "end_date"):
                    if isinstance(out.get(dk), date):
                        out[dk] = out[dk].isoformat()
    # Eligibility classification
    life = str(out.get("lifecycle_state") or "").lower()
    emp_st = str(out.get("employment_status") or "").lower()
    start = out.get("start_date")
    today = date.today().isoformat()
    if emp_st in {"left"} or life in TERMINAL_BLOCKED:
        out["eligibility"] = "terminated"
    elif out.get("suspended_on") or life == "suspended":
        out["eligibility"] = "suspended"
    elif start and str(start)[:10] > today:
        out["eligibility"] = "future_start"
    else:
        out["eligibility"] = "active"
    return out


def _assert_request_eligibility(legacy: Any, *, eligibility: str, request_type: str) -> None:
    if eligibility == "terminated":
        if request_type not in {"employment_letter", "service_certificate"}:
            raise legacy.HTTPException(
                status_code=422,
                detail={
                    "error": "terminated_employee_request_blocked",
                    "message": "Terminated employees may only request letters/service certificates.",
                    "eligibility": eligibility,
                },
            )
    elif eligibility == "suspended":
        if request_type not in SUSPENDED_ALLOWED_TYPES:
            raise legacy.HTTPException(
                status_code=422,
                detail={"error": "suspended_employee_request_blocked", "eligibility": eligibility, "request_type": request_type},
            )
    elif eligibility == "future_start":
        if request_type in FUTURE_START_BLOCKED_TYPES:
            raise legacy.HTTPException(
                status_code=422,
                detail={"error": "future_start_request_blocked", "eligibility": eligibility, "request_type": request_type},
            )


def _old_snapshot(legacy: Any, *, company: str, employee_key: str, request_type: str) -> dict[str, Any]:
    snap: dict[str, Any] = {"employee_key": employee_key, "captured_at": _now().isoformat()}
    emp = _load_employee(legacy, company=company, employee_key=employee_key)
    snap["hub"] = {
        "name": emp.get("name"),
        "email": emp.get("email"),
        "phone": emp.get("phone"),
        "updated_at": str(emp.get("updated_at") or ""),
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT profile_json, emergency_json, version FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key=%s",
                (company, employee_key),
            )
            prow = cur.fetchone()
            if prow:
                pd = dict(prow)
                snap["personal"] = pd.get("profile_json") or {}
                snap["emergency"] = pd.get("emergency_json") or {}
                snap["personal_version"] = pd.get("version")
            cur.execute(
                "SELECT bank_fingerprint, version FROM employee_ess_bank_profiles WHERE company_code=%s AND employee_key=%s",
                (company, employee_key),
            )
            brow = cur.fetchone()
            if brow:
                bd = dict(brow)
                snap["bank_fingerprint"] = bd.get("bank_fingerprint")
                snap["bank_version"] = bd.get("version")
            if request_type in MANAGER_REQUEST_TYPES:
                try:
                    import employee_org_wave4 as w4

                    as_of = w4.get_assignment_as_of(legacy, company_code=company, employee_key=employee_key)
                    snap["assignment_as_of"] = as_of
                except Exception as exc:  # noqa: BLE001
                    snap["assignment_as_of_error"] = str(exc)
            conn.commit()
    snap["employment"] = _employment_projection(legacy, company=company, employee_key=employee_key)
    return snap


def _request_hash(**parts: Any) -> str:
    return hashlib.sha256(
        json.dumps(_jsonable(parts), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def get_own_view(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
) -> dict[str, Any]:
    """Employee view of own profile / employment / assignment / manager / history (masked)."""
    company = _require_ess(legacy, context)
    # Self or HR/manager with read
    actor_emp = str(context.get("actor_employee_key") or "")
    is_self = actor_emp and actor_emp == employee_key
    if not is_self:
        if not (_has_perm(legacy, context, "employees.read") or _has_perm(legacy, context, "employees.manage")):
            raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
        if hasattr(legacy, "require_employee_mutation_scope"):
            legacy.require_employee_mutation_scope(context, employee_key, company_code=company, action="ess_view")
    emp = _load_employee(legacy, company=company, employee_key=employee_key)
    employment = _employment_projection(legacy, company=company, employee_key=employee_key)
    can_unmask = _can_unmask(legacy, context) and not is_self  # employee self still masked for bank
    # Employees never unmask own bank in this surface unless HR unmask
    if is_self:
        can_unmask = False
    personal = {}
    emergency = {}
    bank_masked: dict[str, Any] = {}
    docs: list[dict[str, Any]] = []
    assignment = None
    history: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT profile_json, emergency_json FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key=%s",
                (company, employee_key),
            )
            prow = cur.fetchone()
            if prow:
                personal = dict(prow).get("profile_json") or {}
                emergency = dict(prow).get("emergency_json") or {}
            cur.execute(
                "SELECT bank_ciphertext, bank_fingerprint, version FROM employee_ess_bank_profiles WHERE company_code=%s AND employee_key=%s",
                (company, employee_key),
            )
            brow = cur.fetchone()
            if brow:
                bd = dict(brow)
                raw_bank = bd.get("bank_ciphertext") or {}
                if isinstance(raw_bank, str):
                    try:
                        raw_bank = json.loads(raw_bank)
                    except Exception:
                        raw_bank = {}
                # ciphertext blob is never returned; only fingerprint + masked placeholders
                bank_masked = {
                    "bank_fingerprint": bd.get("bank_fingerprint"),
                    "version": bd.get("version"),
                    "iban": "****" if bd.get("bank_fingerprint") else None,
                    "has_bank_on_file": bool(bd.get("bank_fingerprint")),
                }
                if can_unmask and isinstance(raw_bank, dict) and raw_bank.get("plaintext_dev_only"):
                    # staging/dev decrypt path — production should use encrypt_sensitive_text reverse
                    bank_masked = mask_sensitive(raw_bank.get("plaintext_dev_only") or {}, can_unmask=True)
                    bank_masked["version"] = bd.get("version")
            cur.execute(
                """
                SELECT document_version_id::text, document_key, version_number, storage_ref, metadata, status, created_at
                FROM employee_ess_document_versions
                WHERE company_code=%s AND employee_key=%s
                ORDER BY document_key, version_number DESC
                """,
                (company, employee_key),
            )
            docs = [_jsonable(dict(r)) for r in (cur.fetchall() or [])]
            conn.commit()
    try:
        import employee_org_wave4 as w4

        if w4.org_v4_enabled(company):
            assignment = w4.get_current_org_projection(legacy, company_code=company, employee_key=employee_key)
            history = w4.list_assignment_history(legacy, company_code=company, employee_key=employee_key)
    except Exception as exc:  # noqa: BLE001
        assignment = {"error": str(exc)}
    return {
        "ok": True,
        "employee_key": employee_key,
        "profile": {
            "name": emp.get("name"),
            "email": emp.get("email"),
            "phone": emp.get("phone"),
            "position_title": emp.get("position_title"),
            "department": emp.get("department"),
        },
        "personal": mask_sensitive(personal if isinstance(personal, dict) else {}, can_unmask=can_unmask or is_self),
        "emergency": mask_sensitive(emergency if isinstance(emergency, dict) else {}, can_unmask=can_unmask or is_self),
        "bank": bank_masked,
        "employment": employment,
        "assignment": assignment,
        "assignment_history": history,
        "documents": docs,
        "masking": {"bank_masked": not can_unmask, "sensitive_policy": "permission_gated"},
    }


def list_manager_reports(
    legacy: Any,
    context: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Effective in-scope reports for the acting manager."""
    company = _require_ess(legacy, context)
    if not (_has_perm(legacy, context, "employees.read") or _has_perm(legacy, context, "employees.manage") or context.get("actor_employee_key")):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
    manager_key = str(context.get("actor_employee_key") or context.get("manager_employee_key") or "")
    if not manager_key:
        raise legacy.HTTPException(status_code=422, detail={"error": "manager_employee_key_required"})
    as_of = as_of or date.today()
    reports: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            # Prefer Wave 4 as-of covering slice; fall back to Wave 2 assignments
            cur.execute(
                """
                SELECT DISTINCT h.employee_key
                FROM employee_org_assignment_history h
                WHERE h.company_code=%s
                  AND h.manager_employee_key=%s
                  AND h.effective_from <= %s
                  AND (h.effective_to IS NULL OR h.effective_to >= %s)
                """,
                (company, manager_key, as_of, as_of),
            )
            keys = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
            if not keys:
                cur.execute(
                    """
                    SELECT DISTINCT m.employee_key
                    FROM employee_assignments a
                    JOIN employee_key_authority_map m ON m.assignment_id=a.assignment_id AND m.company_code=a.company_code
                    WHERE a.company_code=%s AND a.manager_employee_key=%s
                      AND a.is_primary=true
                      AND (a.effective_to IS NULL OR a.effective_to >= CURRENT_DATE)
                    """,
                    (company, manager_key),
                )
                keys = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
            conn.commit()
    for key in keys:
        emp = None
        try:
            if hasattr(legacy, "require_employee_mutation_scope"):
                emp = legacy.require_employee_mutation_scope(context, key, company_code=company, action="ess_report_view")
            else:
                emp = _load_employee(legacy, company=company, employee_key=key)
        except Exception:
            continue  # out of dashboard manager_scopes
        reports.append(
            {
                "employee_key": key,
                "name": (emp or {}).get("name"),
                "employment": _employment_projection(legacy, company=company, employee_key=key),
            }
        )
    return {"ok": True, "manager_employee_key": manager_key, "as_of": as_of.isoformat(), "reports": reports}


def create_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    request_type: str,
    proposed_values: dict[str, Any],
    idempotency_key: str,
    requester_kind: str = "employee",
    comment: str | None = None,
    evidence: dict[str, Any] | None = None,
    expected_hub_updated_at: str | None = None,
    draft: bool = False,
) -> dict[str, Any]:
    company = _require_ess(legacy, context)
    request_type = str(request_type or "").strip().lower()
    if request_type not in ALL_REQUEST_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_request_type"})
    requester_kind = str(requester_kind or "employee").strip().lower()
    if requester_kind not in {"employee", "manager", "hr"}:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_requester_kind"})
    if request_type in MANAGER_REQUEST_TYPES and requester_kind == "employee":
        raise legacy.HTTPException(status_code=422, detail={"error": "manager_request_type_required"})
    if request_type in EMPLOYEE_REQUEST_TYPES and requester_kind == "manager":
        raise legacy.HTTPException(status_code=422, detail={"error": "employee_must_request_own_personal_data"})

    actor_emp = str(context.get("actor_employee_key") or "")
    actor_user = _actor_user_id(context)
    if requester_kind == "employee":
        if actor_emp and actor_emp != employee_key:
            raise legacy.HTTPException(status_code=403, detail={"error": "own_data_only"})
        if not actor_emp and not _has_perm(legacy, context, "employees.manage"):
            # dashboard HR creating on behalf blocked — ESS is self-service
            raise legacy.HTTPException(status_code=403, detail={"error": "employee_actor_required"})
    elif requester_kind == "manager":
        if hasattr(legacy, "require_employee_mutation_scope"):
            legacy.require_employee_mutation_scope(context, employee_key, company_code=company, action="ess_manager_request")
        # also require current reporting relationship
        reports = list_manager_reports(legacy, {**context, "actor_employee_key": actor_emp or context.get("manager_employee_key")}, as_of=date.today())
        report_keys = {r["employee_key"] for r in reports.get("reports") or []}
        if employee_key not in report_keys and not _has_perm(legacy, context, "employees.manage"):
            raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})

    employment = _employment_projection(legacy, company=company, employee_key=employee_key)
    _assert_request_eligibility(legacy, eligibility=str(employment.get("eligibility")), request_type=request_type)

    idem = str(idempotency_key or "").strip()
    if len(idem) < 8:
        raise legacy.HTTPException(status_code=422, detail={"error": "idempotency_key_required"})

    old_snap = _old_snapshot(legacy, company=company, employee_key=employee_key, request_type=request_type)
    route = _approval_route_for(request_type)
    initial_state = "draft" if draft else _pending_state_for_stage(route[0]) if route else "approved"
    if not draft and initial_state == "pending_hr" and request_type not in MANAGER_REQUEST_TYPES:
        # submitted then immediately routed
        initial_state = "pending_hr"

    rh = _request_hash(
        company=company,
        employee_key=employee_key,
        request_type=request_type,
        proposed=proposed_values,
        idempotency_key=idem,
        route=route,
    )

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND idempotency_key=%s",
                (company, idem),
            )
            existing = cur.fetchone()
            if existing:
                conn.commit()
                return {"ok": True, "idempotent": True, "request": _jsonable(dict(existing))}

            hub = _load_employee(legacy, company=company, employee_key=employee_key)
            hub_updated = expected_hub_updated_at or str(hub.get("updated_at") or "")
            comments = []
            if comment:
                comments.append({"at": _now().isoformat(), "by": actor_user or actor_emp, "text": comment})

            cur.execute(
                """
                INSERT INTO employee_ess_requests (
                  company_code, employee_key, employment_id, request_type, state,
                  requester_kind, requester_user_id, requester_employee_key,
                  proposed_values, old_value_snapshot, approval_route, approval_cursor,
                  comments, evidence, concurrency_version, expected_hub_updated_at,
                  idempotency_key, request_hash
                ) VALUES (
                  %s,%s,%s,%s,%s,
                  %s,%s,%s,
                  %s::jsonb,%s::jsonb,%s::jsonb,0,
                  %s::jsonb,%s::jsonb,1,%s,
                  %s,%s
                ) RETURNING *
                """,
                (
                    company,
                    employee_key,
                    employment.get("employment_id"),
                    request_type,
                    initial_state if not draft else "draft",
                    requester_kind,
                    actor_user,
                    actor_emp or None,
                    json.dumps(_jsonable(proposed_values or {})),
                    json.dumps(_jsonable(old_snap)),
                    json.dumps(route),
                    json.dumps(comments),
                    json.dumps(_jsonable(evidence or {})),
                    hub_updated or None,
                    idem,
                    rh,
                ),
            )
            row = dict(cur.fetchone())
            _event(
                cur,
                company=company,
                request_id=str(row["request_id"]),
                action="create_draft" if draft else "submit",
                from_state=None,
                to_state=row["state"],
                actor_user_id=actor_user,
                actor_employee_key=actor_emp or None,
                detail={"request_type": request_type, "route": route},
            )
            _journal(
                cur,
                company=company,
                action="ess_create_request",
                idempotency_key=idem,
                payload={"request_id": str(row["request_id"]), "state": row["state"]},
            )
            conn.commit()
    return {"ok": True, "request": _jsonable(row)}


def submit_request(legacy: Any, context: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    company = _require_ess(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(row)
            _assert_actor_owns_or_hr(legacy, context, req)
            if req["state"] not in {"draft", "needs_information"}:
                raise legacy.HTTPException(status_code=409, detail={"error": "invalid_state_for_submit", "state": req["state"]})
            route = req.get("approval_route") or []
            if isinstance(route, str):
                route = json.loads(route)
            next_state = _pending_state_for_stage(route[0]) if route else "approved"
            # Re-check eligibility
            employment = _employment_projection(legacy, company=company, employee_key=req["employee_key"])
            _assert_request_eligibility(legacy, eligibility=str(employment.get("eligibility")), request_type=req["request_type"])
            cur.execute(
                """
                UPDATE employee_ess_requests
                SET state=%s, approval_cursor=0, concurrency_version=concurrency_version+1, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (next_state, request_id),
            )
            updated = dict(cur.fetchone())
            _event(
                cur, company=company, request_id=request_id, action="submit",
                from_state=req["state"], to_state=next_state,
                actor_user_id=_actor_user_id(context),
                actor_employee_key=str(context.get("actor_employee_key") or "") or None,
            )
            conn.commit()
    return {"ok": True, "request": _jsonable(updated)}


def _assert_actor_owns_or_hr(legacy: Any, context: dict[str, Any], req: dict[str, Any]) -> None:
    actor_emp = str(context.get("actor_employee_key") or "")
    if actor_emp and actor_emp == str(req.get("employee_key") or ""):
        return
    if actor_emp and actor_emp == str(req.get("requester_employee_key") or ""):
        return
    if _has_perm(legacy, context, "employees.manage") or _has_perm(legacy, context, "employees.ess.approve.hr"):
        return
    raise legacy.HTTPException(status_code=403, detail={"error": "not_request_owner"})


def withdraw_request(legacy: Any, context: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    company = _require_ess(legacy, context)
    withdrawable = {"draft", "submitted", "needs_information", "pending_manager", "pending_hr", "pending_payroll"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(row)
            _assert_actor_owns_or_hr(legacy, context, req)
            if req["state"] not in withdrawable:
                raise legacy.HTTPException(status_code=409, detail={"error": "not_withdrawable", "state": req["state"]})
            cur.execute(
                """
                UPDATE employee_ess_requests
                SET state='withdrawn', concurrency_version=concurrency_version+1, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (request_id,),
            )
            updated = dict(cur.fetchone())
            _event(
                cur, company=company, request_id=request_id, action="withdraw",
                from_state=req["state"], to_state="withdrawn",
                actor_user_id=_actor_user_id(context),
                actor_employee_key=str(context.get("actor_employee_key") or "") or None,
            )
            conn.commit()
    return {"ok": True, "request": _jsonable(updated)}


def decide_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
    action: str,
    comment: str | None = None,
    expected_concurrency_version: int | None = None,
) -> dict[str, Any]:
    """Approve / reject / return_for_information. Does NOT apply canonical mutations."""
    company = _require_ess(legacy, context)
    action = str(action or "").strip().lower()
    if action not in DECISION_ACTIONS:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_decision_action"})
    actor_user = _actor_user_id(context)
    actor_emp = str(context.get("actor_employee_key") or "")

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(row)
            if expected_concurrency_version is not None and int(req.get("concurrency_version") or 0) != int(expected_concurrency_version):
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "stale_concurrency_version", "current": req.get("concurrency_version")},
                )

            state = req["state"]
            if state not in {"pending_manager", "pending_hr", "pending_payroll"}:
                raise legacy.HTTPException(status_code=409, detail={"error": "not_pending_decision", "state": state})

            # No self-approval
            if actor_user and str(req.get("requester_user_id") or "") == actor_user:
                raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
            if actor_emp and actor_emp == str(req.get("requester_employee_key") or ""):
                raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})
            if actor_emp and actor_emp == str(req.get("employee_key") or "") and req["request_type"] in EMPLOYEE_REQUEST_TYPES:
                raise legacy.HTTPException(status_code=403, detail={"error": "self_approval_forbidden"})

            # Stage permission + scope
            stage = {
                "pending_manager": "manager",
                "pending_hr": "hr",
                "pending_payroll": "payroll",
            }[state]
            _assert_stage_permission(legacy, context, stage=stage, req=req)

            comments = req.get("comments") or []
            if isinstance(comments, str):
                comments = json.loads(comments)
            if comment:
                comments = list(comments) + [{"at": _now().isoformat(), "by": actor_user or actor_emp, "text": comment, "action": action}]

            if action == "reject":
                new_state = "rejected"
                cursor = int(req.get("approval_cursor") or 0)
            elif action == "return_for_information":
                new_state = "needs_information"
                cursor = int(req.get("approval_cursor") or 0)
            else:
                # approve current stage
                route = req.get("approval_route") or []
                if isinstance(route, str):
                    route = json.loads(route)
                cursor = int(req.get("approval_cursor") or 0) + 1
                if cursor >= len(route):
                    new_state = "approved"
                else:
                    new_state = _pending_state_for_stage(route[cursor])

            cur.execute(
                """
                UPDATE employee_ess_requests
                SET state=%s, approval_cursor=%s, comments=%s::jsonb,
                    concurrency_version=concurrency_version+1, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (new_state, cursor if action == "approve" else req.get("approval_cursor") or 0, json.dumps(comments), request_id),
            )
            updated = dict(cur.fetchone())
            _event(
                cur, company=company, request_id=request_id, action=f"decide_{action}",
                from_state=state, to_state=new_state,
                actor_user_id=actor_user, actor_employee_key=actor_emp or None,
                detail={"stage": stage},
            )
            _journal(
                cur, company=company, action=f"ess_decide_{action}",
                idempotency_key=f"{request_id}:{state}:{action}:{updated['concurrency_version']}",
                payload={"request_id": request_id, "to": new_state},
            )
            conn.commit()
    return {"ok": True, "request": _jsonable(updated), "applied": False}


def _assert_stage_permission(legacy: Any, context: dict[str, Any], *, stage: str, req: dict[str, Any]) -> None:
    company = str(req.get("company_code") or context.get("company_code") or "").upper()
    if stage == "manager":
        if not (
            _has_perm(legacy, context, "employees.ess.approve.manager")
            or _has_perm(legacy, context, "employees.manage")
            or context.get("actor_employee_key")
        ):
            raise legacy.HTTPException(status_code=403, detail={"error": "manager_approve_denied"})
        # must be in reporting scope for the subject
        if hasattr(legacy, "require_employee_mutation_scope"):
            legacy.require_employee_mutation_scope(
                context, req["employee_key"], company_code=company, action="ess_manager_approve"
            )
    elif stage == "hr":
        if not (
            _has_perm(legacy, context, "employees.ess.approve.hr")
            or _has_perm(legacy, context, "employees.manage")
            or _has_perm(legacy, context, "employees.status.approve")
        ):
            raise legacy.HTTPException(status_code=403, detail={"error": "hr_approve_denied"})
    elif stage == "payroll":
        if not (
            _has_perm(legacy, context, "employees.ess.approve.payroll")
            or _has_perm(legacy, context, "employees.manage")
        ):
            raise legacy.HTTPException(status_code=403, detail={"error": "payroll_approve_denied"})


def apply_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Apply an approved request to ESS overlays / Wave 4. Idempotent."""
    company = _require_ess(legacy, context)
    if not (
        _has_perm(legacy, context, "employees.manage")
        or _has_perm(legacy, context, "employees.ess.apply")
        or _has_perm(legacy, context, "employees.ess.approve.hr")
    ):
        raise legacy.HTTPException(status_code=403, detail={"error": "apply_denied"})
    actor_user = _actor_user_id(context)
    apply_idem = str(idempotency_key or f"ess-apply:{request_id}").strip()

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(row)
            if req["state"] == "applied" and req.get("applied_authority_ref"):
                conn.commit()
                return {"ok": True, "idempotent": True, "request": _jsonable(req)}
            if req["state"] != "approved":
                raise legacy.HTTPException(status_code=409, detail={"error": "not_approved", "state": req["state"]})

            # Stale hub check (fail closed)
            hub = _load_employee(legacy, company=company, employee_key=req["employee_key"])
            expected = str(req.get("expected_hub_updated_at") or "")
            current = str(hub.get("updated_at") or "")
            if expected and current and expected != current:
                cur.execute(
                    """
                    UPDATE employee_ess_requests
                    SET state='failed', fail_reason=%s, concurrency_version=concurrency_version+1, updated_at=now()
                    WHERE request_id=%s RETURNING *
                    """,
                    ("stale_hub_updated_at", request_id),
                )
                failed = dict(cur.fetchone())
                _event(
                    cur, company=company, request_id=request_id, action="apply_failed_stale",
                    from_state="approved", to_state="failed",
                    actor_user_id=actor_user, detail={"expected": expected, "current": current},
                )
                conn.commit()
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "stale_data", "expected_hub_updated_at": expected, "current": current, "request": _jsonable(failed)},
                )

            proposed = req.get("proposed_values") or {}
            if isinstance(proposed, str):
                proposed = json.loads(proposed)
            rtype = req["request_type"]
            authority_ref: dict[str, Any] = {"request_id": request_id, "request_type": rtype}

            try:
                if rtype in {"personal_detail_change", "emergency_contact_change"}:
                    authority_ref.update(_apply_personal(cur, company=company, req=req, proposed=proposed))
                elif rtype == "bank_detail_change":
                    authority_ref.update(_apply_bank(legacy, cur, company=company, req=req, proposed=proposed))
                elif rtype == "document_change":
                    authority_ref.update(_apply_document(cur, company=company, req=req, proposed=proposed))
                elif rtype in {"employment_letter", "service_certificate"}:
                    authority_ref.update(_apply_letter(cur, company=company, req=req, proposed=proposed, letter_type=rtype))
                elif rtype in MANAGER_REQUEST_TYPES:
                    # Wave 4 apply outside this cursor — mark then call
                    authority_ref["wave4"] = "pending"
                else:
                    raise RuntimeError(f"unsupported_apply_type:{rtype}")
            except legacy.HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                cur.execute(
                    """
                    UPDATE employee_ess_requests
                    SET state='failed', fail_reason=%s, concurrency_version=concurrency_version+1, updated_at=now()
                    WHERE request_id=%s RETURNING *
                    """,
                    (str(exc)[:500], request_id),
                )
                failed = dict(cur.fetchone())
                _event(
                    cur, company=company, request_id=request_id, action="apply_failed",
                    from_state="approved", to_state="failed", actor_user_id=actor_user, detail={"error": str(exc)},
                )
                conn.commit()
                return {"ok": False, "request": _jsonable(failed), "error": str(exc)}

            if rtype not in MANAGER_REQUEST_TYPES:
                cur.execute(
                    """
                    UPDATE employee_ess_requests
                    SET state='applied', applied_at=now(), applied_by_user_id=%s,
                        applied_authority_ref=%s::jsonb,
                        concurrency_version=concurrency_version+1, updated_at=now()
                    WHERE request_id=%s RETURNING *
                    """,
                    (actor_user, json.dumps(_jsonable(authority_ref)), request_id),
                )
                updated = dict(cur.fetchone())
                _event(
                    cur, company=company, request_id=request_id, action="apply",
                    from_state="approved", to_state="applied", actor_user_id=actor_user, detail=authority_ref,
                )
                _journal(cur, company=company, action="ess_apply", idempotency_key=apply_idem, payload=authority_ref)
                conn.commit()
                return {"ok": True, "request": _jsonable(updated), "authority_ref": authority_ref}

            conn.commit()

    # Assignment types: Wave 4 outside ESS transaction (still after approval)
    import employee_org_wave4 as w4

    if not w4.org_v4_enabled(company):
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_ess_requests SET state='failed', fail_reason=%s, updated_at=now() WHERE request_id=%s RETURNING *",
                    ("org_v4_disabled", request_id),
                )
                failed = dict(cur.fetchone())
                conn.commit()
        return {"ok": False, "error": "org_v4_disabled", "request": _jsonable(failed)}

    proposed = req.get("proposed_values") or {}
    if isinstance(proposed, str):
        proposed = json.loads(proposed)
    eff = proposed.get("effective_from") or date.today().isoformat()
    if isinstance(eff, str):
        eff_d = date.fromisoformat(eff[:10])
    else:
        eff_d = eff
    change_type = {"transfer": "transfer", "manager_change": "manager_change", "assignment_correction": "department_change"}.get(rtype, "transfer")
    w4_out = w4.apply_assignment_change(
        legacy,
        context,
        employee_key=req["employee_key"],
        effective_from=eff_d,
        change_type=change_type,
        reason=str(proposed.get("reason") or f"ESS {rtype}"),
        department_unit_id=proposed.get("department_unit_id"),
        team_unit_id=proposed.get("team_unit_id"),
        location_unit_id=proposed.get("location_unit_id"),
        position_unit_id=proposed.get("position_unit_id"),
        manager_employee_key=proposed.get("manager_employee_key"),
        request_id=request_id,
        provenance={"source": "wave5_ess", "request_id": request_id},
    )
    authority_ref = {"request_id": request_id, "request_type": rtype, "wave4": w4_out}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                """
                UPDATE employee_ess_requests
                SET state='applied', applied_at=now(), applied_by_user_id=%s,
                    applied_authority_ref=%s::jsonb,
                    concurrency_version=concurrency_version+1, updated_at=now()
                WHERE request_id=%s AND state='approved'
                RETURNING *
                """,
                (actor_user, json.dumps(_jsonable(authority_ref)), request_id),
            )
            updated = cur.fetchone()
            if not updated:
                # already applied concurrently
                cur.execute("SELECT * FROM employee_ess_requests WHERE request_id=%s", (request_id,))
                updated = cur.fetchone()
                conn.commit()
                return {"ok": True, "idempotent": True, "request": _jsonable(dict(updated))}
            updated = dict(updated)
            _event(
                cur, company=company, request_id=request_id, action="apply",
                from_state="approved", to_state="applied", actor_user_id=actor_user, detail=authority_ref,
            )
            _journal(cur, company=company, action="ess_apply", idempotency_key=apply_idem, payload=authority_ref)
            conn.commit()
    return {"ok": True, "request": _jsonable(updated), "authority_ref": authority_ref}


def _apply_personal(cur: Any, *, company: str, req: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    key = req["employee_key"]
    cur.execute(
        "SELECT profile_json, emergency_json, version FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key=%s FOR UPDATE",
        (company, key),
    )
    existing = cur.fetchone()
    profile = dict((dict(existing).get("profile_json") if existing else {}) or {})
    emergency = dict((dict(existing).get("emergency_json") if existing else {}) or {})
    version = int(dict(existing).get("version") if existing else 0) + 1
    if req["request_type"] == "personal_detail_change":
        profile.update({k: v for k, v in proposed.items() if k not in {"reason"}})
    else:
        emergency.update({k: v for k, v in proposed.items() if k not in {"reason"}})
    cur.execute(
        """
        INSERT INTO employee_ess_personal_profiles (
          company_code, employee_key, profile_json, emergency_json, version, updated_by_request_id, updated_at
        ) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,now())
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          profile_json=EXCLUDED.profile_json,
          emergency_json=EXCLUDED.emergency_json,
          version=EXCLUDED.version,
          updated_by_request_id=EXCLUDED.updated_by_request_id,
          updated_at=now()
        """,
        (company, key, json.dumps(_jsonable(profile)), json.dumps(_jsonable(emergency)), version, req["request_id"]),
    )
    return {"personal_profile_version": version, "overlay": "employee_ess_personal_profiles"}


def _apply_bank(legacy: Any, cur: Any, *, company: str, req: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    key = req["employee_key"]
    iban = str(proposed.get("iban") or proposed.get("bank_account") or "").strip()
    if not iban:
        raise legacy.HTTPException(status_code=422, detail={"error": "iban_required"})
    # Prefer encrypt_sensitive_text when available
    cipher: dict[str, Any]
    if hasattr(legacy, "encrypt_sensitive_text"):
        try:
            cipher = {"enc": legacy.encrypt_sensitive_text(iban), "bank_name": proposed.get("bank_name"), "account_holder": proposed.get("account_holder")}
        except Exception:
            cipher = {"plaintext_dev_only": {"iban": iban, "bank_name": proposed.get("bank_name"), "account_holder": proposed.get("account_holder")}}
    else:
        cipher = {"plaintext_dev_only": {"iban": iban, "bank_name": proposed.get("bank_name"), "account_holder": proposed.get("account_holder")}}
    fp = hashlib.sha256(iban.encode("utf-8")).hexdigest()[:16]
    cur.execute(
        "SELECT version FROM employee_ess_bank_profiles WHERE company_code=%s AND employee_key=%s FOR UPDATE",
        (company, key),
    )
    existing = cur.fetchone()
    version = int(dict(existing).get("version") if existing else 0) + 1
    cur.execute(
        """
        INSERT INTO employee_ess_bank_profiles (
          company_code, employee_key, bank_ciphertext, bank_fingerprint, version, updated_by_request_id, updated_at
        ) VALUES (%s,%s,%s::jsonb,%s,%s,%s,now())
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          bank_ciphertext=EXCLUDED.bank_ciphertext,
          bank_fingerprint=EXCLUDED.bank_fingerprint,
          version=EXCLUDED.version,
          updated_by_request_id=EXCLUDED.updated_by_request_id,
          updated_at=now()
        """,
        (company, key, json.dumps(_jsonable(cipher)), fp, version, req["request_id"]),
    )
    return {"bank_profile_version": version, "bank_fingerprint": fp, "overlay": "employee_ess_bank_profiles"}


def _apply_document(cur: Any, *, company: str, req: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    key = req["employee_key"]
    doc_key = str(proposed.get("document_key") or proposed.get("document_type") or "document").strip()
    storage_ref = str(proposed.get("storage_ref") or proposed.get("object_key") or f"ess/{key}/{doc_key}/{uuid.uuid4().hex}")
    cur.execute(
        """
        SELECT document_version_id::text, version_number
        FROM employee_ess_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_key=%s
        ORDER BY version_number DESC LIMIT 1
        FOR UPDATE
        """,
        (company, key, doc_key),
    )
    prev = cur.fetchone()
    prev_d = dict(prev) if prev else None
    next_ver = int(prev_d["version_number"] if prev_d else 0) + 1
    if prev_d:
        cur.execute(
            "UPDATE employee_ess_document_versions SET status='replaced' WHERE document_version_id=%s",
            (prev_d["document_version_id"],),
        )
    cur.execute(
        """
        INSERT INTO employee_ess_document_versions (
          company_code, employee_key, document_key, version_number, storage_ref,
          metadata, replaced_version_id, request_id, status
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'active')
        RETURNING document_version_id::text, version_number
        """,
        (
            company,
            key,
            doc_key,
            next_ver,
            storage_ref,
            json.dumps(_jsonable(proposed.get("metadata") or {})),
            prev_d["document_version_id"] if prev_d else None,
            req["request_id"],
        ),
    )
    new_row = dict(cur.fetchone())
    return {
        "document_key": doc_key,
        "version_number": new_row["version_number"],
        "document_version_id": new_row["document_version_id"],
        "prior_version_id": prev_d["document_version_id"] if prev_d else None,
        "overlay": "employee_ess_document_versions",
    }


def _apply_letter(cur: Any, *, company: str, req: dict[str, Any], proposed: dict[str, Any], letter_type: str) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO employee_ess_letter_orders (
          company_code, employee_key, letter_type, status, request_id, payload
        ) VALUES (%s,%s,%s,'pending',%s,%s::jsonb)
        RETURNING letter_id::text
        """,
        (company, req["employee_key"], letter_type, req["request_id"], json.dumps(_jsonable(proposed))),
    )
    letter_id = dict(cur.fetchone())["letter_id"]
    return {"letter_id": letter_id, "letter_type": letter_type, "overlay": "employee_ess_letter_orders"}


def get_request(legacy: Any, context: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    company = _require_ess(legacy, context)
    can_unmask = _can_unmask(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            cur.execute(
                "SELECT * FROM employee_ess_requests WHERE company_code=%s AND request_id=%s",
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(row)
            cur.execute(
                "SELECT * FROM employee_ess_request_events WHERE request_id=%s ORDER BY created_at",
                (request_id,),
            )
            events = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    # Access: owner, manager in scope, or HR
    try:
        _assert_actor_owns_or_hr(legacy, context, req)
    except Exception:
        if hasattr(legacy, "require_employee_mutation_scope"):
            legacy.require_employee_mutation_scope(
                context, req["employee_key"], company_code=company, action="ess_request_view"
            )
        else:
            raise
    proposed = req.get("proposed_values") or {}
    if isinstance(proposed, str):
        proposed = json.loads(proposed)
    req["proposed_values"] = mask_sensitive(proposed if isinstance(proposed, dict) else {}, can_unmask=can_unmask)
    return {"ok": True, "request": _jsonable(req), "events": _jsonable(events)}


def list_requests(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str | None = None,
    state: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    company = _require_ess(legacy, context)
    actor_emp = str(context.get("actor_employee_key") or "")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_ess_wave5_schema(cur)
            clauses = ["company_code=%s"]
            args: list[Any] = [company]
            if employee_key:
                clauses.append("employee_key=%s")
                args.append(employee_key)
            elif actor_emp and not _has_perm(legacy, context, "employees.manage"):
                clauses.append("(employee_key=%s OR requester_employee_key=%s)")
                args.extend([actor_emp, actor_emp])
            if state:
                clauses.append("state=%s")
                args.append(state)
            args.append(max(1, min(int(limit), 200)))
            cur.execute(
                f"""
                SELECT request_id::text, employee_key, request_type, state, requester_kind,
                       approval_route, approval_cursor, concurrency_version, created_at, updated_at
                FROM employee_ess_requests
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(args),
            )
            rows = [_jsonable(dict(r)) for r in (cur.fetchall() or [])]
            conn.commit()
    return {"ok": True, "requests": rows}


def routing_permission_matrix() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "states": sorted(REQUEST_STATES),
        "request_types": {
            "employee": sorted(EMPLOYEE_REQUEST_TYPES),
            "manager": sorted(MANAGER_REQUEST_TYPES),
        },
        "routes": {t: _approval_route_for(t) for t in sorted(ALL_REQUEST_TYPES)},
        "permissions": {
            "employees.ess.request": "create/submit/withdraw own or in-scope manager requests",
            "employees.ess.approve.manager": "decide pending_manager",
            "employees.ess.approve.hr": "decide pending_hr",
            "employees.ess.approve.payroll": "decide pending_payroll (bank)",
            "employees.ess.apply": "apply approved → canonical ESS overlays / Wave 4",
            "employees.ess.unmask": "view unmasked sensitive proposed/bank fields",
            "employees.read / employees.manage": "compatible HR fallbacks",
        },
        "rules": [
            "approval and apply are separate",
            "no self-approval",
            "apply is idempotent",
            "stale hub updated_at fails closed",
            "assignment apply uses Wave 4 effective-dated authority",
            "lifecycle/jurisdiction remain Wave 3 governed",
            "bank requires payroll stage",
            "document replacement preserves prior versions",
            "managers cannot act outside reporting + dashboard scope",
            "sensitive fields masked by permission",
        ],
        "eligibility": {
            "terminated": "letters/service_certificate only",
            "suspended": sorted(SUSPENDED_ALLOWED_TYPES),
            "future_start": f"blocked types={sorted(FUTURE_START_BLOCKED_TYPES)}",
            "active": "all types per requester_kind",
        },
    }
