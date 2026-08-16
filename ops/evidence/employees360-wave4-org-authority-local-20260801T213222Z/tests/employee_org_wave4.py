"""Employees 360 Wave 4 — organization authority, effective history, migration, bulk ops.

Local/staging only. Builds on Wave 2 person/employment/assignment authority.
Does not enable real-employee lifecycle use. Does not overwrite historical rows:
prior assignment slices are closed with effective_to, never mutated in place.

Flags:
  WATHEFNI_EMPLOYEE_ORG_V4=on
  WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI (default)
Requires Wave 2 authority for the same tenant.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from employee_authority_wave2 import (
    authority_v2_enabled,
    ensure_authority_schema,
    get_authority_projection,
    phone_digits,
)
from employee_hygiene_wave1c import _jsonable as _hygiene_jsonable

SCHEMA_VERSION = "employees360-wave4-org-authority-v1"

UNIT_TYPES = frozenset({
    "legal_employer",
    "branch",
    "department",
    "team",
    "location",
    "position",
    "cost_center",
})
CHANGE_TYPES = frozenset({
    "transfer",
    "manager_change",
    "job_change",
    "department_change",
    "location_change",
    "bulk_assign",
    "migration",
    "initial",
})
BATCH_STATUSES = frozenset({
    "draft",
    "mapped",
    "dry_run",
    "staged",
    "committing",
    "committed",
    "paused",
    "failed",
    "rolled_back",
})
ROW_STATUSES = frozenset({
    "pending",
    "valid",
    "invalid",
    "duplicate",
    "conflict",
    "needs_review",
    "committed",
    "skipped",
})
JOB_TYPES = frozenset({"bulk_assign", "export", "reconcile"})
POLICY_TIERS = frozenset({"small", "medium", "enterprise"})

DEFAULT_POLICY = {
    "tier": "small",
    "require_change_reason": True,
    "require_dual_approval": False,  # enterprise may enable
    "allow_future_dated_changes": True,
    "fail_on_overlap": True,
    "migration_auto_create_org_units": True,
    "migration_ambiguous_people": "needs_review",  # never auto-merge
    "bulk_max_rows": 500,
    "simple_org_types": ["department", "location", "position"],  # small-business subset
    "disclaimer": "Wave 4 org/migration policy. Not legal advice. No lifecycle monetary math.",
}

WAVE4_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_org_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_org_company_policies (
  company_code text PRIMARY KEY,
  tier text NOT NULL DEFAULT 'small',
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (tier IN ('small','medium','enterprise'))
);

CREATE TABLE IF NOT EXISTS employee_org_units (
  org_unit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  unit_type text NOT NULL,
  unit_key text NOT NULL,
  name text NOT NULL,
  parent_org_unit_id uuid,
  status text NOT NULL DEFAULT 'active',
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  version int NOT NULL DEFAULT 1,
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_to date,
  created_by_user_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (unit_type IN ('legal_employer','branch','department','team','location','position','cost_center')),
  CHECK (status IN ('active','archived')),
  UNIQUE (company_code, unit_type, unit_key)
);

CREATE INDEX IF NOT EXISTS employee_org_units_company_type_idx
  ON employee_org_units (company_code, unit_type, status);

CREATE TABLE IF NOT EXISTS employee_org_assignment_history (
  history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid,
  employment_id uuid,
  wave2_assignment_id uuid,
  legal_employer_unit_id uuid,
  branch_unit_id uuid,
  department_unit_id uuid,
  team_unit_id uuid,
  location_unit_id uuid,
  position_unit_id uuid,
  cost_center_unit_id uuid,
  manager_employee_key text,
  position_title text,
  effective_from date NOT NULL,
  effective_to date,
  change_type text NOT NULL DEFAULT 'transfer',
  reason text NOT NULL DEFAULT '',
  actor_user_id uuid,
  request_id uuid,
  bulk_job_id uuid,
  batch_id uuid,
  version int NOT NULL DEFAULT 1,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (change_type IN ('transfer','manager_change','job_change','department_change','location_change','bulk_assign','migration','initial')),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS employee_org_assignment_history_emp_idx
  ON employee_org_assignment_history (company_code, employee_key, effective_from DESC);

CREATE INDEX IF NOT EXISTS employee_org_assignment_history_open_idx
  ON employee_org_assignment_history (company_code, employee_key)
  WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS employee_org_change_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  change_type text NOT NULL,
  effective_on date NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  resulting_history_id uuid,
  expected_open_history_id uuid,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','executed','cancelled','scheduled')),
  CHECK (change_type IN ('transfer','manager_change','job_change','department_change','location_change','bulk_assign','migration','initial')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_migration_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  filename text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  tier text NOT NULL DEFAULT 'small',
  column_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  created_by_user_id uuid,
  paused_at timestamptz,
  committed_at timestamptz,
  rolled_back_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','mapped','dry_run','staged','committing','committed','paused','failed','rolled_back')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_migration_rows (
  row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES employee_migration_batches(batch_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  row_number int NOT NULL,
  raw jsonb NOT NULL DEFAULT '{}'::jsonb,
  normalized jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  conflict_reason text,
  employee_key text,
  person_id uuid,
  history_id uuid,
  review_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','valid','invalid','duplicate','conflict','needs_review','committed','skipped')),
  UNIQUE (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS employee_bulk_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  job_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  created_by_user_id uuid,
  reverse_of_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  CHECK (job_type IN ('bulk_assign','export','reconcile')),
  CHECK (status IN ('pending','running','succeeded','failed','reversed','cancelled')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_bulk_job_items (
  item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES employee_bulk_jobs(job_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  before_history_id uuid,
  after_history_id uuid,
  error_text text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','applied','skipped','failed','reversed'))
);

CREATE TABLE IF NOT EXISTS employee_org_migration_journal (
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
"""


def _jsonable(value: Any) -> Any:
    return _hygiene_jsonable(value)


def org_v4_enabled(company_code: str | None = None) -> bool:
    raw = str(os.environ.get("WATHEFNI_EMPLOYEE_ORG_V4") or "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    try:
        if not authority_v2_enabled(company_code):
            return False
    except TypeError:
        if not authority_v2_enabled():
            return False
    allow = str(os.environ.get("WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES") or "WATHEFNI")
    companies = {c.strip().upper() for c in allow.split(",") if c.strip()}
    if company_code is None:
        return bool(companies)
    return str(company_code or "").upper() in companies


def ensure_org_wave4_schema(cur: Any) -> None:
    cur.execute(WAVE4_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO employee_org_schema_meta (schema_name, schema_version)
        VALUES ('employees360_wave4', %s)
        ON CONFLICT (schema_name) DO UPDATE SET schema_version=EXCLUDED.schema_version, updated_at=now()
        """,
        (SCHEMA_VERSION,),
    )


def _require_manage(legacy: Any, context: dict[str, Any]) -> str:
    company = str(context.get("company_code") or "").upper()
    if not org_v4_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    if not legacy.dashboard_context_has_permission(context, "employees.manage"):
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied"})
    return company


def _require_scope(legacy: Any, context: dict[str, Any], employee_key: str) -> None:
    if hasattr(legacy, "require_employee_mutation_scope"):
        legacy.require_employee_mutation_scope(
            context, employee_key, company_code=str(context.get("company_code") or "").upper(), action="org_wave4"
        )


def _policy_defaults_for_tier(tier: str) -> dict[str, Any]:
    base = dict(DEFAULT_POLICY)
    base["tier"] = tier if tier in POLICY_TIERS else "small"
    if base["tier"] == "small":
        base["require_dual_approval"] = False
        base["simple_org_types"] = ["department", "location", "position"]
    elif base["tier"] == "medium":
        base["require_dual_approval"] = False
        base["simple_org_types"] = ["legal_employer", "branch", "department", "team", "location", "position"]
    else:
        base["require_dual_approval"] = True
        base["simple_org_types"] = list(UNIT_TYPES)
    return base


def get_or_create_org_policy(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute("SELECT * FROM employee_org_company_policies WHERE company_code=%s", (company,))
            row = cur.fetchone()
            if not row:
                defaults = _policy_defaults_for_tier("small")
                cur.execute(
                    """
                    INSERT INTO employee_org_company_policies (company_code, tier, policy_json)
                    VALUES (%s,%s,%s::jsonb) RETURNING *
                    """,
                    (company, defaults["tier"], json.dumps(defaults)),
                )
                row = cur.fetchone()
            conn.commit()
    policy = _jsonable(dict(row))
    pj = policy.get("policy_json") or {}
    if isinstance(pj, str):
        pj = json.loads(pj)
    merged = {**_policy_defaults_for_tier(str(policy.get("tier") or "small")), **(pj if isinstance(pj, dict) else {})}
    merged["tier"] = policy.get("tier") or merged["tier"]
    merged["company_code"] = company
    return merged


def upsert_org_policy(legacy: Any, context: dict[str, Any], *, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    patch = {k: v for k, v in (patch or {}).items() if v is not None}
    current = get_or_create_org_policy(legacy, company_code=company)
    prev_tier = str(current.get("tier") or "small")
    tier = str(patch.get("tier") or prev_tier)
    if tier not in POLICY_TIERS:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_tier"})
    defaults = _policy_defaults_for_tier(tier)
    merged = {**defaults}
    # Carry forward prior knobs, but refresh tier-derived fields when tier changes.
    for key, value in current.items():
        if key in {"company_code", "tier"}:
            continue
        if prev_tier != tier and key in {"simple_org_types", "require_dual_approval"} and key not in patch:
            continue
        merged[key] = value
    merged.update(patch)
    merged["tier"] = tier
    if prev_tier != tier:
        if "simple_org_types" not in patch:
            merged["simple_org_types"] = defaults["simple_org_types"]
        if "require_dual_approval" not in patch:
            merged["require_dual_approval"] = defaults["require_dual_approval"]
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            policy_keys = set(DEFAULT_POLICY.keys()) | set(merged.keys())
            policy_body = {k: merged[k] for k in policy_keys if k != "company_code" and k in merged}
            cur.execute(
                """
                UPDATE employee_org_company_policies
                SET tier=%s, policy_json=%s::jsonb, updated_by_user_id=%s, updated_at=now()
                WHERE company_code=%s RETURNING *
                """,
                (tier, json.dumps(_jsonable(policy_body)), context.get("actor_user_id"), company),
            )
            cur.fetchone()
            conn.commit()
    return get_or_create_org_policy(legacy, company_code=company)


def _slug_key(name: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(name or "").strip())
    while "--" in raw:
        raw = raw.replace("--", "-")
    return (raw.strip("-") or "unit")[:80]


def upsert_org_unit(
    legacy: Any,
    context: dict[str, Any],
    *,
    unit_type: str,
    name: str,
    unit_key: str | None = None,
    parent_org_unit_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    effective_from: date | None = None,
    status: str = "active",
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    unit_type = str(unit_type or "").strip().lower()
    if unit_type not in UNIT_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_unit_type"})
    policy = get_or_create_org_policy(legacy, company_code=company)
    allowed = {str(x) for x in (policy.get("simple_org_types") or list(UNIT_TYPES))}
    if unit_type not in allowed and policy.get("tier") == "small":
        raise legacy.HTTPException(
            status_code=422,
            detail={"error": "unit_type_not_enabled_for_tier", "tier": policy.get("tier"), "allowed": sorted(allowed)},
        )
    clean_name = str(name or "").strip()
    if not clean_name:
        raise legacy.HTTPException(status_code=422, detail={"error": "name_required"})
    key = str(unit_key or _slug_key(clean_name)).strip()
    eff = effective_from or date.today()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_org_units (
                  company_code, unit_type, unit_key, name, parent_org_unit_id, status,
                  attributes, effective_from, created_by_user_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                ON CONFLICT (company_code, unit_type, unit_key) DO UPDATE SET
                  name=EXCLUDED.name,
                  parent_org_unit_id=COALESCE(EXCLUDED.parent_org_unit_id, employee_org_units.parent_org_unit_id),
                  status=EXCLUDED.status,
                  attributes=employee_org_units.attributes || EXCLUDED.attributes,
                  version=employee_org_units.version + 1,
                  updated_at=now()
                RETURNING *
                """,
                (
                    company,
                    unit_type,
                    key,
                    clean_name,
                    parent_org_unit_id,
                    status if status in {"active", "archived"} else "active",
                    json.dumps(attributes or {}),
                    eff,
                    context.get("actor_user_id"),
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "unit": _jsonable(row)}


def list_org_units(legacy: Any, *, company_code: str, unit_type: str | None = None) -> list[dict[str, Any]]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            if unit_type:
                cur.execute(
                    "SELECT * FROM employee_org_units WHERE company_code=%s AND unit_type=%s ORDER BY name",
                    (company, unit_type),
                )
            else:
                cur.execute(
                    "SELECT * FROM employee_org_units WHERE company_code=%s ORDER BY unit_type, name",
                    (company,),
                )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return _jsonable(rows)


def _open_history(cur: Any, *, company: str, employee_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM employee_org_assignment_history
        WHERE company_code=%s AND employee_key=%s AND effective_to IS NULL
        ORDER BY effective_from DESC, created_at DESC
        LIMIT 1
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _assert_no_overlap(legacy: Any, cur: Any, *, company: str, employee_key: str, effective_from: date, fail_on_overlap: bool) -> None:
    cur.execute(
        """
        SELECT history_id::text, effective_from, effective_to
        FROM employee_org_assignment_history
        WHERE company_code=%s AND employee_key=%s
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
        ORDER BY effective_from
        """,
        (company, employee_key, effective_from, effective_from),
    )
    overlaps = [dict(r) for r in (cur.fetchall() or [])]
    # Open row that will be closed at effective_from-1 is OK if we close it in same txn.
    # Overlap fail-closed means: an existing CLOSED/OPEN row that already covers the date
    # besides the single open row we intend to close.
    open_rows = [r for r in overlaps if r.get("effective_to") is None]
    closed_covering = [r for r in overlaps if r.get("effective_to") is not None]
    if closed_covering and fail_on_overlap:
        raise legacy.HTTPException(
            status_code=409,
            detail={"error": "overlapping_assignment", "message": "Historical assignment already covers this effective date.", "overlaps": _jsonable(closed_covering)},
        )
    if len(open_rows) > 1 and fail_on_overlap:
        raise legacy.HTTPException(
            status_code=409,
            detail={"error": "overlapping_assignment", "message": "Multiple open assignment slices.", "overlaps": _jsonable(open_rows)},
        )


def _authority_ids(cur: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT person_id::text, employment_id::text, assignment_id::text
        FROM employee_key_authority_map
        WHERE company_code=%s AND employee_key=%s AND mapping_status='active'
        LIMIT 1
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else {}


def apply_assignment_change(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    effective_from: date,
    change_type: str,
    reason: str,
    department_unit_id: str | None = None,
    team_unit_id: str | None = None,
    location_unit_id: str | None = None,
    position_unit_id: str | None = None,
    branch_unit_id: str | None = None,
    cost_center_unit_id: str | None = None,
    legal_employer_unit_id: str | None = None,
    manager_employee_key: str | None = None,
    position_title: str | None = None,
    request_id: str | None = None,
    bulk_job_id: str | None = None,
    batch_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    allow_future: bool = True,
) -> dict[str, Any]:
    """Close open history (if any) and insert a new slice. Never overwrites prior rows."""
    company = _require_manage(legacy, context)
    _require_scope(legacy, context, employee_key)
    change_type = str(change_type or "").strip().lower()
    if change_type not in CHANGE_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_change_type"})
    reason_s = str(reason or "").strip()
    policy = get_or_create_org_policy(legacy, company_code=company)
    if policy.get("require_change_reason") and not reason_s:
        raise legacy.HTTPException(status_code=422, detail={"error": "reason_required"})
    if effective_from > date.today() and not (allow_future and policy.get("allow_future_dated_changes", True)):
        raise legacy.HTTPException(status_code=422, detail={"error": "future_dated_not_allowed"})

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            ensure_authority_schema(cur)
            cur.execute("SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s", (company, employee_key))
            if not cur.fetchone():
                raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})

            _assert_no_overlap(
                legacy,
                cur,
                company=company,
                employee_key=employee_key,
                effective_from=effective_from,
                fail_on_overlap=bool(policy.get("fail_on_overlap", True)),
            )
            open_row = _open_history(cur, company=company, employee_key=employee_key)
            closed = None
            if open_row:
                # If open row starts on/after new effective_from → hard overlap
                open_from = open_row["effective_from"]
                if isinstance(open_from, datetime):
                    open_from = open_from.date()
                if open_from >= effective_from:
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={
                            "error": "overlapping_assignment",
                            "message": "Open assignment starts on or after the new effective date.",
                            "open_history_id": str(open_row["history_id"]),
                        },
                    )
                close_to = effective_from - timedelta(days=1)
                cur.execute(
                    """
                    UPDATE employee_org_assignment_history
                    SET effective_to=%s, version=version+1
                    WHERE history_id=%s AND effective_to IS NULL
                    RETURNING *
                    """,
                    (close_to, open_row["history_id"]),
                )
                closed = dict(cur.fetchone())

            auth = _authority_ids(cur, company=company, employee_key=employee_key)
            # Inherit unspecified fields from prior open slice
            base = open_row or {}
            cur.execute(
                """
                INSERT INTO employee_org_assignment_history (
                  company_code, employee_key, person_id, employment_id, wave2_assignment_id,
                  legal_employer_unit_id, branch_unit_id, department_unit_id, team_unit_id,
                  location_unit_id, position_unit_id, cost_center_unit_id,
                  manager_employee_key, position_title,
                  effective_from, change_type, reason, actor_user_id,
                  request_id, bulk_job_id, batch_id, provenance
                ) VALUES (
                  %s,%s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,
                  %s,%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,%s::jsonb
                ) RETURNING *
                """,
                (
                    company,
                    employee_key,
                    auth.get("person_id") or base.get("person_id"),
                    auth.get("employment_id") or base.get("employment_id"),
                    auth.get("assignment_id") or base.get("wave2_assignment_id"),
                    legal_employer_unit_id or base.get("legal_employer_unit_id"),
                    branch_unit_id or base.get("branch_unit_id"),
                    department_unit_id if department_unit_id is not None else base.get("department_unit_id"),
                    team_unit_id if team_unit_id is not None else base.get("team_unit_id"),
                    location_unit_id if location_unit_id is not None else base.get("location_unit_id"),
                    position_unit_id if position_unit_id is not None else base.get("position_unit_id"),
                    cost_center_unit_id if cost_center_unit_id is not None else base.get("cost_center_unit_id"),
                    manager_employee_key if manager_employee_key is not None else base.get("manager_employee_key"),
                    position_title if position_title is not None else base.get("position_title"),
                    effective_from,
                    change_type,
                    reason_s,
                    context.get("actor_user_id"),
                    request_id,
                    bulk_job_id,
                    batch_id,
                    json.dumps(_jsonable(provenance or {"wave": "wave4"})),
                ),
            )
            created = dict(cur.fetchone())

            # Sync readable fields onto Wave 2 primary assignment when present (non-destructive extras)
            if auth.get("assignment_id"):
                # Resolve unit names for hub-ish projection fields
                def _unit_name(uid: Any) -> str | None:
                    if not uid:
                        return None
                    cur.execute("SELECT name FROM employee_org_units WHERE org_unit_id=%s", (uid,))
                    r = cur.fetchone()
                    return dict(r)["name"] if r else None

                dept_name = _unit_name(created.get("department_unit_id"))
                loc_name = _unit_name(created.get("location_unit_id"))
                cur.execute(
                    """
                    UPDATE employee_assignments SET
                      department=COALESCE(%s, department),
                      location=COALESCE(%s, location),
                      manager_employee_key=COALESCE(%s, manager_employee_key),
                      position_title=COALESCE(%s, position_title),
                      team_key=COALESCE(%s, team_key),
                      branch_key=COALESCE(%s, branch_key),
                      cost_center=COALESCE(%s, cost_center),
                      effective_from=COALESCE(%s, effective_from),
                      updated_at=now()
                    WHERE assignment_id=%s AND company_code=%s
                    """,
                    (
                        dept_name,
                        loc_name,
                        created.get("manager_employee_key"),
                        created.get("position_title"),
                        str(created.get("team_unit_id") or "") or None,
                        str(created.get("branch_unit_id") or "") or None,
                        str(created.get("cost_center_unit_id") or "") or None,
                        effective_from if effective_from <= date.today() else None,
                        auth["assignment_id"],
                        company,
                    ),
                )
            conn.commit()
    return {
        "ok": True,
        "closed_prior": _jsonable(closed) if closed else None,
        "history": _jsonable(created),
        "note": "Prior assignment preserved via effective_to close; new slice appended.",
    }


def create_org_change_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    change_type: str,
    effective_on: date,
    reason: str,
    payload: dict[str, Any],
    idempotency_key: str,
    designated_approver_user_id: str | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    _require_scope(legacy, context, employee_key)
    policy = get_or_create_org_policy(legacy, company_code=company)
    change_type = str(change_type or "").strip().lower()
    if change_type not in CHANGE_TYPES:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_change_type"})
    if policy.get("require_dual_approval"):
        if not designated_approver_user_id or str(designated_approver_user_id) == str(context.get("actor_user_id")):
            raise legacy.HTTPException(status_code=403, detail={"error": "dual_approval_required"})
    body = dict(payload or {})
    rhash = hashlib.sha256(
        json.dumps({"employee_key": employee_key, "change_type": change_type, "effective_on": effective_on.isoformat(), "payload": body, "reason": reason}, sort_keys=True, default=str).encode()
    ).hexdigest()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            open_row = _open_history(cur, company=company, employee_key=employee_key)
            cur.execute(
                """
                INSERT INTO employee_org_change_requests (
                  company_code, employee_key, change_type, effective_on, payload, reason, status,
                  requester_user_id, designated_approver_user_id, expected_open_history_id,
                  idempotency_key, request_hash
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, idempotency_key) DO UPDATE SET updated_at=now()
                RETURNING *
                """,
                (
                    company,
                    employee_key,
                    change_type,
                    effective_on,
                    json.dumps(_jsonable(body)),
                    reason,
                    "scheduled" if effective_on > date.today() else "pending",
                    context.get("actor_user_id"),
                    designated_approver_user_id,
                    open_row.get("history_id") if open_row else None,
                    idempotency_key.strip(),
                    rhash,
                ),
            )
            req = dict(cur.fetchone())
            # Idempotent payload conflict
            if req.get("request_hash") != rhash and req.get("idempotency_key") == idempotency_key.strip():
                conn.rollback()
                raise legacy.HTTPException(status_code=409, detail={"error": "idempotency_conflict"})
            conn.commit()

    # Small/medium: auto-execute when effective_on <= today and dual approval not required
    if (not policy.get("require_dual_approval")) and effective_on <= date.today():
        return execute_org_change_request(legacy, context, request_id=str(req["request_id"]))
    if (not policy.get("require_dual_approval")) and effective_on > date.today():
        return {"ok": True, "request": _jsonable(req), "status": "scheduled"}
    return {"ok": True, "request": _jsonable(req)}


def execute_org_change_request(legacy: Any, context: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                "SELECT * FROM employee_org_change_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                (company, request_id),
            )
            req = cur.fetchone()
            if not req:
                raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found"})
            req = dict(req)
            if req.get("status") not in {"pending", "scheduled", "approved"}:
                raise legacy.HTTPException(status_code=409, detail={"error": "request_not_executable", "status": req.get("status")})
            payload = req.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            conn.commit()

    applied = apply_assignment_change(
        legacy,
        context,
        employee_key=str(req["employee_key"]),
        effective_from=req["effective_on"] if not isinstance(req["effective_on"], datetime) else req["effective_on"].date(),
        change_type=str(req["change_type"]),
        reason=str(req.get("reason") or ""),
        department_unit_id=payload.get("department_unit_id"),
        team_unit_id=payload.get("team_unit_id"),
        location_unit_id=payload.get("location_unit_id"),
        position_unit_id=payload.get("position_unit_id"),
        branch_unit_id=payload.get("branch_unit_id"),
        cost_center_unit_id=payload.get("cost_center_unit_id"),
        legal_employer_unit_id=payload.get("legal_employer_unit_id"),
        manager_employee_key=payload.get("manager_employee_key"),
        position_title=payload.get("position_title"),
        request_id=str(req["request_id"]),
        provenance={"source": "org_change_request"},
    )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_org_change_requests
                SET status='executed', executed_at=now(), decided_at=now(),
                    decided_by_user_id=%s, resulting_history_id=%s, updated_at=now()
                WHERE request_id=%s RETURNING *
                """,
                (context.get("actor_user_id"), applied["history"]["history_id"], request_id),
            )
            updated = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "request": _jsonable(updated), "applied": applied}


def apply_due_org_change_requests(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    if not org_v4_enabled(company):
        return {"ok": False, "error": "org_v4_disabled"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                """
                SELECT request_id::text, requester_user_id::text
                FROM employee_org_change_requests
                WHERE company_code=%s AND status='scheduled' AND effective_on <= CURRENT_DATE
                ORDER BY effective_on, created_at
                """,
                (company,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    executed = []
    for row in rows:
        ctx = {
            "company_code": company,
            "actor_user_id": row.get("requester_user_id"),
            "permissions": ["employees.manage"],
            "role": "system",
        }
        # Bypass scope for system apply of already-authorized scheduled changes by loading manage context lightly
        try:
            # Use internal path: mark pending then execute via apply with elevated helper
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE employee_org_change_requests SET status='pending', updated_at=now() WHERE request_id=%s",
                        (row["request_id"],),
                    )
                conn.commit()
            out = execute_org_change_request(legacy, ctx, request_id=row["request_id"])
            executed.append(out)
        except Exception as exc:
            executed.append({"request_id": row["request_id"], "ok": False, "error": str(exc)})
    return {"ok": True, "executed": executed, "count": len(executed)}


def list_assignment_history(legacy: Any, *, company_code: str, employee_key: str) -> list[dict[str, Any]]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_org_assignment_history
                WHERE company_code=%s AND employee_key=%s
                ORDER BY effective_from DESC, created_at DESC
                """,
                (company, employee_key),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return _jsonable(rows)


# --- Migration batches ---

DEFAULT_COLUMN_ALIASES = {
    "name": "name",
    "full name": "name",
    "employee name": "name",
    "phone": "phone",
    "mobile": "phone",
    "whatsapp": "phone",
    "email": "email",
    "department": "department",
    "dept": "department",
    "team": "team",
    "location": "location",
    "branch": "branch",
    "position": "position_title",
    "position title": "position_title",
    "title": "position_title",
    "manager": "manager_phone",
    "manager phone": "manager_phone",
    "cost center": "cost_center",
    "start date": "start_date",
}


def _normalize_header(h: str) -> str:
    return " ".join(str(h or "").strip().lower().replace("_", " ").split())


def suggest_column_mapping(headers: list[str]) -> dict[str, str]:
    mapping = {}
    for h in headers:
        key = DEFAULT_COLUMN_ALIASES.get(_normalize_header(h))
        if key:
            mapping[h] = key
    return mapping


def create_migration_batch(
    legacy: Any,
    context: dict[str, Any],
    *,
    filename: str,
    rows: list[dict[str, Any]],
    idempotency_key: str,
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    if not rows:
        raise legacy.HTTPException(status_code=422, detail={"error": "empty_import"})
    policy = get_or_create_org_policy(legacy, company_code=company)
    if len(rows) > int(policy.get("bulk_max_rows") or 500):
        raise legacy.HTTPException(status_code=422, detail={"error": "too_many_rows"})
    headers = list(rows[0].keys()) if rows else []
    mapping = column_mapping or suggest_column_mapping(headers)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_migration_batches (
                  company_code, filename, status, tier, column_mapping, provenance,
                  idempotency_key, created_by_user_id
                ) VALUES (%s,%s,'mapped',%s,%s::jsonb,%s::jsonb,%s,%s)
                ON CONFLICT (company_code, idempotency_key) DO UPDATE SET updated_at=now()
                RETURNING *
                """,
                (
                    company,
                    filename,
                    policy.get("tier") or "small",
                    json.dumps(mapping),
                    json.dumps({"source": "wave4_migration", "row_count": len(rows)}),
                    idempotency_key.strip(),
                    context.get("actor_user_id"),
                ),
            )
            batch = dict(cur.fetchone())
            batch_id = batch["batch_id"]
            # Replace rows for idempotent retry only when still draft/mapped
            cur.execute("DELETE FROM employee_migration_rows WHERE batch_id=%s", (batch_id,))
            for i, raw in enumerate(rows, start=1):
                cur.execute(
                    """
                    INSERT INTO employee_migration_rows (batch_id, company_code, row_number, raw, status)
                    VALUES (%s,%s,%s,%s::jsonb,'pending')
                    """,
                    (batch_id, company, i, json.dumps(_jsonable(raw))),
                )
            conn.commit()
    return {"ok": True, "batch": _jsonable(batch), "column_mapping": mapping, "row_count": len(rows)}


def _map_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src, dest in mapping.items():
        if src in raw and raw[src] not in (None, ""):
            out[dest] = raw[src]
    return out


def dry_run_migration_batch(legacy: Any, context: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    policy = get_or_create_org_policy(legacy, company_code=company)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute("SELECT * FROM employee_migration_batches WHERE company_code=%s AND batch_id=%s FOR UPDATE", (company, batch_id))
            batch = cur.fetchone()
            if not batch:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch)
            mapping = batch.get("column_mapping") or {}
            if isinstance(mapping, str):
                mapping = json.loads(mapping)
            cur.execute("SELECT * FROM employee_migration_rows WHERE batch_id=%s ORDER BY row_number", (batch_id,))
            rows = [dict(r) for r in (cur.fetchall() or [])]
            summary = {"valid": 0, "invalid": 0, "duplicate": 0, "conflict": 0, "needs_review": 0}
            seen_phones: dict[str, int] = {}
            for row in rows:
                raw = row.get("raw") or {}
                if isinstance(raw, str):
                    raw = json.loads(raw)
                norm = _map_row(raw, mapping)
                status = "valid"
                reason = None
                phone = phone_digits(str(norm.get("phone") or ""))
                name = str(norm.get("name") or "").strip()
                if not phone or not name:
                    status, reason = "invalid", "name_and_phone_required"
                elif phone in seen_phones:
                    status, reason = "duplicate", f"duplicate_phone_in_batch_row_{seen_phones[phone]}"
                else:
                    seen_phones[phone] = int(row["row_number"])
                    # Existing hub collision
                    cur.execute(
                        "SELECT employee_key, name, phone FROM employees WHERE company_code=%s AND phone=%s LIMIT 1",
                        (company, phone),
                    )
                    hit = cur.fetchone()
                    if hit:
                        hit = dict(hit)
                        if str(hit.get("name") or "").strip().lower() != name.lower():
                            status, reason = "needs_review", "phone_exists_name_mismatch"
                            if policy.get("migration_ambiguous_people") == "needs_review":
                                pass
                        else:
                            status, reason = "conflict", "employee_already_exists"
                if status == "valid":
                    summary["valid"] += 1
                elif status == "invalid":
                    summary["invalid"] += 1
                elif status == "duplicate":
                    summary["duplicate"] += 1
                elif status == "conflict":
                    summary["conflict"] += 1
                else:
                    summary["needs_review"] += 1
                cur.execute(
                    """
                    UPDATE employee_migration_rows
                    SET normalized=%s::jsonb, status=%s, conflict_reason=%s, updated_at=now()
                    WHERE row_id=%s
                    """,
                    (json.dumps(_jsonable(norm)), status, reason, row["row_id"]),
                )
            cur.execute(
                """
                UPDATE employee_migration_batches
                SET status='dry_run', validation_summary=%s::jsonb, updated_at=now()
                WHERE batch_id=%s RETURNING *
                """,
                (json.dumps(summary), batch_id),
            )
            updated = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "batch": _jsonable(updated), "summary": summary, "partial_success": False}


def commit_migration_batch(
    legacy: Any,
    context: dict[str, Any],
    *,
    batch_id: str,
    resume: bool = False,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Commit only valid rows. Invalid/duplicate/conflict/needs_review stay in review — never silent partial invent."""
    company = _require_manage(legacy, context)
    policy = get_or_create_org_policy(legacy, company_code=company)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute("SELECT * FROM employee_migration_batches WHERE company_code=%s AND batch_id=%s FOR UPDATE", (company, batch_id))
            batch = cur.fetchone()
            if not batch:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch)
            if batch.get("status") not in {"dry_run", "staged", "paused", "committing"} and not resume:
                raise legacy.HTTPException(status_code=409, detail={"error": "batch_not_committable", "status": batch.get("status")})
            cur.execute(
                """
                UPDATE employee_migration_batches SET status='committing', paused_at=NULL, updated_at=now()
                WHERE batch_id=%s
                """,
                (batch_id,),
            )
            cur.execute(
                """
                SELECT * FROM employee_migration_rows
                WHERE batch_id=%s AND status='valid'
                ORDER BY row_number
                """,
                (batch_id,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    committed = []
    limit = max_rows if max_rows is not None else len(rows)
    for row in rows[:limit]:
        norm = row.get("normalized") or {}
        if isinstance(norm, str):
            norm = json.loads(norm)
        phone = phone_digits(str(norm.get("phone") or ""))
        name = str(norm.get("name") or "").strip()
        created = legacy.create_company_employee(
            company,
            name=name,
            phone=phone,
            email=str(norm.get("email") or "").strip() or None,
            position_title=str(norm.get("position_title") or "").strip() or None,
            department=str(norm.get("department") or "").strip() or None,
        )
        if created.get("status") not in {"created", "exists"}:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE employee_migration_rows SET status='needs_review', conflict_reason=%s, updated_at=now() WHERE row_id=%s",
                        (f"create_failed:{created.get('reason')}", row["row_id"]),
                    )
                conn.commit()
            continue
        key = str(created.get("employee_key") or (created.get("employee") or {}).get("employee_key"))
        # Ensure authority map for new creates
        try:
            from employee_authority_wave2 import sync_authority_from_hub_employee

            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, key),
                    )
                    hub = cur.fetchone()
                conn.commit()
            if hub:
                sync_authority_from_hub_employee(legacy, dict(hub), hire_source="wave4_migration")
        except Exception:
            pass

        # Optional org units from import
        unit_ids: dict[str, str] = {}
        if policy.get("migration_auto_create_org_units"):
            for field, utype in (("department", "department"), ("team", "team"), ("location", "location"), ("branch", "branch"), ("cost_center", "cost_center")):
                val = str(norm.get(field) or "").strip()
                if val:
                    u = upsert_org_unit(legacy, context, unit_type=utype, name=val)
                    unit_ids[f"{utype}_unit_id"] = str(u["unit"]["org_unit_id"])
            pos = str(norm.get("position_title") or "").strip()
            if pos:
                u = upsert_org_unit(legacy, context, unit_type="position", name=pos)
                unit_ids["position_unit_id"] = str(u["unit"]["org_unit_id"])

        hist = apply_assignment_change(
            legacy,
            context,
            employee_key=key,
            effective_from=date.today(),
            change_type="migration",
            reason=f"migration batch {batch_id}",
            department_unit_id=unit_ids.get("department_unit_id"),
            team_unit_id=unit_ids.get("team_unit_id"),
            location_unit_id=unit_ids.get("location_unit_id"),
            branch_unit_id=unit_ids.get("branch_unit_id"),
            cost_center_unit_id=unit_ids.get("cost_center_unit_id"),
            position_unit_id=unit_ids.get("position_unit_id"),
            position_title=str(norm.get("position_title") or "").strip() or None,
            batch_id=str(batch_id),
            provenance={"batch_id": str(batch_id), "row_number": row["row_number"]},
        )
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_rows
                    SET status='committed', employee_key=%s, history_id=%s, updated_at=now()
                    WHERE row_id=%s
                    """,
                    (key, hist["history"]["history_id"], row["row_id"]),
                )
            conn.commit()
        committed.append({"row_number": row["row_number"], "employee_key": key, "history_id": hist["history"]["history_id"]})

    paused = len(rows) > limit
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, count(*)::int n FROM employee_migration_rows WHERE batch_id=%s GROUP BY status
                """,
                (batch_id,),
            )
            counts = {dict(r)["status"]: int(dict(r)["n"]) for r in cur.fetchall()}
            new_status = "paused" if paused and counts.get("valid", 0) > 0 else ("committed" if counts.get("valid", 0) == 0 else "staged")
            if not paused and counts.get("valid", 0) == 0:
                new_status = "committed"
            cur.execute(
                """
                UPDATE employee_migration_batches
                SET status=%s, committed_at=CASE WHEN %s='committed' THEN now() ELSE committed_at END,
                    paused_at=CASE WHEN %s='paused' THEN now() ELSE paused_at END,
                    validation_summary=coalesce(validation_summary,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE batch_id=%s RETURNING *
                """,
                (new_status, new_status, new_status, json.dumps({"commit_counts": counts, "committed_now": len(committed)}), batch_id),
            )
            updated = dict(cur.fetchone())
            conn.commit()
    return {
        "ok": True,
        "batch": _jsonable(updated),
        "committed": committed,
        "paused": paused,
        "review_remaining": {
            "needs_review": counts.get("needs_review", 0),
            "conflict": counts.get("conflict", 0),
            "duplicate": counts.get("duplicate", 0),
            "invalid": counts.get("invalid", 0),
            "valid_remaining": counts.get("valid", 0),
        },
        "partial_success": False,
        "note": "Only explicitly valid rows commit. Review/conflict/duplicate rows never auto-create.",
    }


def pause_migration_batch(legacy: Any, context: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_migration_batches
                SET status='paused', paused_at=now(), updated_at=now()
                WHERE company_code=%s AND batch_id=%s AND status IN ('committing','staged','dry_run')
                RETURNING *
                """,
                (company, batch_id),
            )
            row = cur.fetchone()
            conn.commit()
    if not row:
        raise legacy.HTTPException(status_code=409, detail={"error": "batch_not_pausable"})
    return {"ok": True, "batch": _jsonable(dict(row))}


def rollback_migration_batch(legacy: Any, context: dict[str, Any], *, batch_id: str, idempotency_key: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute("SELECT * FROM employee_migration_batches WHERE company_code=%s AND batch_id=%s", (company, batch_id))
            batch = cur.fetchone()
            if not batch:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch)
            cur.execute(
                "SELECT * FROM employee_migration_rows WHERE batch_id=%s AND status='committed'",
                (batch_id,),
            )
            committed_rows = [dict(r) for r in (cur.fetchall() or [])]
            keys = [r["employee_key"] for r in committed_rows if r.get("employee_key")]
            history_ids = [str(r["history_id"]) for r in committed_rows if r.get("history_id")]
            before = {"keys": keys, "history_ids": history_ids, "batch_status": batch.get("status")}
            if history_ids:
                cur.execute(
                    "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND history_id = ANY(%s::uuid[])",
                    (company, history_ids),
                )
            # Soft-mark rows rolled back
            cur.execute(
                "UPDATE employee_migration_rows SET status='skipped', review_note='rolled_back', updated_at=now() WHERE batch_id=%s AND status='committed'",
                (batch_id,),
            )
            cur.execute(
                """
                UPDATE employee_migration_batches
                SET status='rolled_back', rolled_back_at=now(), updated_at=now()
                WHERE batch_id=%s RETURNING *
                """,
                (batch_id,),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_org_migration_journal (company_code, action, idempotency_key, before_json, after_json, status)
                VALUES (%s,'rollback_migration_batch',%s,%s::jsonb,%s::jsonb,'rolled_back')
                ON CONFLICT (company_code, idempotency_key) DO UPDATE SET after_json=EXCLUDED.after_json, rolled_back_at=now()
                RETURNING *
                """,
                (company, idempotency_key.strip(), json.dumps(before), json.dumps({"batch_id": str(batch_id)})),
            )
            journal = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "batch": _jsonable(updated), "journal": _jsonable(journal), "removed_history": history_ids, "note": "Hub employees created by migration are not auto-deleted; history slices removed."}


# --- Bulk assign ---

def create_bulk_assign_job(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_keys: list[str],
    effective_from: date,
    reason: str,
    idempotency_key: str,
    department_unit_id: str | None = None,
    team_unit_id: str | None = None,
    location_unit_id: str | None = None,
    manager_employee_key: str | None = None,
) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    keys = [str(k) for k in employee_keys if str(k).strip()]
    if not keys:
        raise legacy.HTTPException(status_code=422, detail={"error": "employee_keys_required"})
    policy = get_or_create_org_policy(legacy, company_code=company)
    if len(keys) > int(policy.get("bulk_max_rows") or 500):
        raise legacy.HTTPException(status_code=422, detail={"error": "too_many_rows"})
    payload = {
        "employee_keys": keys,
        "effective_from": effective_from.isoformat(),
        "reason": reason,
        "department_unit_id": department_unit_id,
        "team_unit_id": team_unit_id,
        "location_unit_id": location_unit_id,
        "manager_employee_key": manager_employee_key,
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_bulk_jobs (company_code, job_type, status, payload, idempotency_key, created_by_user_id)
                VALUES (%s,'bulk_assign','pending',%s::jsonb,%s,%s)
                ON CONFLICT (company_code, idempotency_key) DO UPDATE SET updated_at=now()
                RETURNING *
                """,
                (company, json.dumps(payload), idempotency_key.strip(), context.get("actor_user_id")),
            )
            job = dict(cur.fetchone())
            job_id = job["job_id"]
            cur.execute("DELETE FROM employee_bulk_job_items WHERE job_id=%s", (job_id,))
            for key in keys:
                cur.execute(
                    """
                    INSERT INTO employee_bulk_job_items (job_id, company_code, employee_key, status)
                    VALUES (%s,%s,%s,'pending')
                    """,
                    (job_id, company, key),
                )
            conn.commit()
    return run_bulk_assign_job(legacy, context, job_id=str(job_id))


def run_bulk_assign_job(legacy: Any, context: dict[str, Any], *, job_id: str) -> dict[str, Any]:
    company = _require_manage(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_bulk_jobs WHERE company_code=%s AND job_id=%s FOR UPDATE", (company, job_id))
            job = cur.fetchone()
            if not job:
                raise legacy.HTTPException(status_code=404, detail={"error": "job_not_found"})
            job = dict(job)
            if job.get("status") == "succeeded":
                conn.commit()
                return {"ok": True, "job": _jsonable(job), "idempotent": True}
            payload = job.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            cur.execute("UPDATE employee_bulk_jobs SET status='running', updated_at=now() WHERE job_id=%s", (job_id,))
            cur.execute("SELECT * FROM employee_bulk_job_items WHERE job_id=%s AND status='pending' ORDER BY employee_key", (job_id,))
            items = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    applied = []
    for item in items:
        key = item["employee_key"]
        try:
            _require_scope(legacy, context, key)
            open_before = None
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    open_before = _open_history(cur, company=company, employee_key=key)
                conn.commit()
            out = apply_assignment_change(
                legacy,
                context,
                employee_key=key,
                effective_from=date.fromisoformat(str(payload["effective_from"])),
                change_type="bulk_assign",
                reason=str(payload.get("reason") or "bulk_assign"),
                department_unit_id=payload.get("department_unit_id"),
                team_unit_id=payload.get("team_unit_id"),
                location_unit_id=payload.get("location_unit_id"),
                manager_employee_key=payload.get("manager_employee_key"),
                bulk_job_id=str(job_id),
                provenance={"bulk_job_id": str(job_id)},
            )
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE employee_bulk_job_items
                        SET status='applied', before_history_id=%s, after_history_id=%s
                        WHERE item_id=%s
                        """,
                        (
                            open_before.get("history_id") if open_before else None,
                            out["history"]["history_id"],
                            item["item_id"],
                        ),
                    )
                conn.commit()
            applied.append(key)
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            err = detail if detail else str(exc)
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE employee_bulk_job_items SET status='failed', error_text=%s WHERE item_id=%s",
                        (str(err)[:500], item["item_id"]),
                    )
                conn.commit()

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_bulk_jobs
                SET status='succeeded', finished_at=now(), result=%s::jsonb, updated_at=now()
                WHERE job_id=%s RETURNING *
                """,
                (json.dumps({"applied": applied, "applied_count": len(applied)}), job_id),
            )
            job = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "job": _jsonable(job), "applied": applied}


def reverse_bulk_assign_job(legacy: Any, context: dict[str, Any], *, job_id: str, idempotency_key: str) -> dict[str, Any]:
    """Reversible bulk: close slices created by the job and reopen prior open ends where possible."""
    company = _require_manage(legacy, context)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_bulk_jobs WHERE company_code=%s AND job_id=%s", (company, job_id))
            job = cur.fetchone()
            if not job:
                raise legacy.HTTPException(status_code=404, detail={"error": "job_not_found"})
            job = dict(job)
            cur.execute("SELECT * FROM employee_bulk_job_items WHERE job_id=%s AND status='applied'", (job_id,))
            items = [dict(r) for r in (cur.fetchall() or [])]
            for item in items:
                if item.get("after_history_id"):
                    cur.execute(
                        "DELETE FROM employee_org_assignment_history WHERE history_id=%s AND company_code=%s",
                        (item["after_history_id"], company),
                    )
                if item.get("before_history_id"):
                    cur.execute(
                        """
                        UPDATE employee_org_assignment_history
                        SET effective_to=NULL, version=version+1
                        WHERE history_id=%s AND company_code=%s
                        """,
                        (item["before_history_id"], company),
                    )
                cur.execute("UPDATE employee_bulk_job_items SET status='reversed' WHERE item_id=%s", (item["item_id"],))
            cur.execute(
                """
                INSERT INTO employee_bulk_jobs (company_code, job_type, status, payload, result, idempotency_key, created_by_user_id, reverse_of_job_id, finished_at)
                VALUES (%s,'bulk_assign','reversed',%s::jsonb,%s::jsonb,%s,%s,%s,now())
                RETURNING *
                """,
                (
                    company,
                    json.dumps({"reverse_of": str(job_id)}),
                    json.dumps({"reversed_items": len(items)}),
                    idempotency_key.strip(),
                    context.get("actor_user_id"),
                    job_id,
                ),
            )
            rev = dict(cur.fetchone())
            cur.execute("UPDATE employee_bulk_jobs SET status='reversed', updated_at=now() WHERE job_id=%s", (job_id,))
            conn.commit()
    return {"ok": True, "reverse_job": _jsonable(rev), "reversed_count": len(items)}


def export_org_reconciliation(legacy: Any, *, company_code: str) -> dict[str, Any]:
    company = str(company_code).upper()
    if not org_v4_enabled(company):
        raise RuntimeError("org_v4_disabled")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            ensure_authority_schema(cur)
            cur.execute(
                """
                SELECT e.employee_key, e.name, e.phone, e.employment_status,
                       m.person_id::text, m.employment_id::text, m.assignment_id::text,
                       a.department AS wave2_department, a.location AS wave2_location,
                       a.manager_employee_key AS wave2_manager,
                       h.history_id::text AS open_history_id,
                       h.department_unit_id::text, h.location_unit_id::text, h.manager_employee_key AS org_manager,
                       h.effective_from AS org_effective_from
                FROM employees e
                LEFT JOIN employee_key_authority_map m
                  ON m.company_code=e.company_code AND m.employee_key=e.employee_key AND m.mapping_status='active'
                LEFT JOIN employee_assignments a
                  ON a.assignment_id=m.assignment_id AND a.company_code=m.company_code
                LEFT JOIN employee_org_assignment_history h
                  ON h.company_code=e.company_code AND h.employee_key=e.employee_key AND h.effective_to IS NULL
                WHERE e.company_code=%s
                ORDER BY e.employee_key
                """,
                (company,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return {
        "ok": True,
        "company_code": company,
        "count": len(rows),
        "rows": _jsonable(rows),
        "note": "Export joins hub employee_key with Wave 2 authority and open Wave 4 org history.",
    }


def rollback_org_wave4(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    company = str(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_org_wave4_schema(cur)
            keys = list(employee_keys or [])
            before = {"employee_keys": keys}
            if keys:
                cur.execute(
                    "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_org_change_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_bulk_job_items WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
            cur.execute(
                """
                INSERT INTO employee_org_migration_journal (company_code, action, idempotency_key, before_json, status)
                VALUES (%s,'rollback_wave4_slices',%s,%s::jsonb,'rolled_back')
                ON CONFLICT (company_code, idempotency_key) DO UPDATE SET rolled_back_at=now()
                RETURNING *
                """,
                (company, idempotency_key.strip(), json.dumps(before)),
            )
            journal = dict(cur.fetchone())
            conn.commit()
    return {"ok": True, "journal": _jsonable(journal)}
