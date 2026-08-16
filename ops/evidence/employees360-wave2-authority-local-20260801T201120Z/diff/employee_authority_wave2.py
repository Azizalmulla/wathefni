"""Employees 360 Wave 2 — canonical person / employment / assignment authority.

Shadow authority model (no hard cutover):
  Person      = identity + contacts (+ tenant employee_number)
  Employment  = legal service period + employment state
  Assignment  = role / org / working pattern

Compatibility:
  employees.employee_key remains the live hub alias used by Onboarding,
  Compliance, Shifts, Attendance, Leave, Payroll and Employees 360 APIs.
  Authority rows are projected alongside the hub; writes sync both ways when
  WATHEFNI_EMPLOYEE_AUTHORITY_V2 is enabled.

Deterministic IDs reuse the Wave 1C approved UUIDv5 namespace/seeds.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from employee_hygiene_wave1c import (
    PERSON_NAMESPACE,
    mint_assignment_id,
    mint_employment_id,
    mint_person_id,
    phone_digits,
)

# Approved Wave 1C readiness map (WATHEFNI production truth at map time).
# Statuses may have been remediated later; IDs are phone-seed stable.
APPROVED_WATHEFNI_MAP: dict[str, dict[str, str]] = {
    "WATHEFNI-96550252254": {
        "person_id": "a0b0d348-addd-5da3-87d7-e0f94a5a466c",
        "employment_id": "e25da3b1-13a3-558d-a147-42dd8445edf7",
        "assignment_id": "112ac62d-bfe5-5f5e-bb33-2f36fb32e2f3",
        "person_seed": "person:WATHEFNI:phone:96550252254",
    },
    "WATHEFNI-96566363363": {
        "person_id": "c24a9068-62a7-5a8e-9b60-d1004dd3c265",
        "employment_id": "fe3359c9-2b14-53a6-88ac-4662e6c04902",
        "assignment_id": "e46040d8-c069-5b9d-aef8-bf507acc73cd",
        "person_seed": "person:WATHEFNI:phone:96566363363",
    },
    "WATHEFNI-96597727743": {
        "person_id": "9bf69b24-2ee3-5d36-9c4a-ed5756afbc50",
        "employment_id": "8fe3358b-18c5-581c-84ea-94f120fd597f",
        "assignment_id": "def8f1c7-9c2a-55ee-a5c9-7a7b92b30d7f",
        "person_seed": "person:WATHEFNI:phone:96597727743",
    },
    "WATHEFNI-96599411617": {
        "person_id": "12966424-7e65-556a-9678-cc3f264836d0",
        "employment_id": "7e51c028-f1db-5b3b-942a-da0f005ac2f1",
        "assignment_id": "fdf5845d-3e96-5f34-b78b-0194f61f438d",
        "person_seed": "person:WATHEFNI:phone:96599411617",
    },
}

WAVE2_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_persons (
  person_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  display_name text,
  primary_phone text,
  primary_email text,
  employee_number text,
  status text NOT NULL DEFAULT 'active',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('active','merged','archived')),
  UNIQUE (company_code, person_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS employee_persons_number_uq
  ON employee_persons (company_code, employee_number)
  WHERE employee_number IS NOT NULL AND employee_number <> '';

CREATE TABLE IF NOT EXISTS employee_person_contact_aliases (
  alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  alias_type text NOT NULL,
  alias_value text NOT NULL,
  alias_value_raw text,
  is_primary boolean NOT NULL DEFAULT false,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (alias_type IN ('phone','email')),
  UNIQUE (company_code, alias_type, alias_value)
);

CREATE INDEX IF NOT EXISTS employee_person_contact_aliases_person_idx
  ON employee_person_contact_aliases (company_code, person_id);

CREATE TABLE IF NOT EXISTS employee_employments (
  employment_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  employment_status text NOT NULL DEFAULT 'active',
  start_date date,
  end_date date,
  hire_source text,
  app_key text,
  legacy_employee_key text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (employment_status IN ('active','left')),
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  UNIQUE (company_code, employment_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS employee_employments_legacy_key_uq
  ON employee_employments (company_code, legacy_employee_key)
  WHERE legacy_employee_key IS NOT NULL AND legacy_employee_key <> '';

CREATE INDEX IF NOT EXISTS employee_employments_person_idx
  ON employee_employments (company_code, person_id, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_assignments (
  assignment_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  employment_id uuid NOT NULL REFERENCES employee_employments(employment_id),
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  is_primary boolean NOT NULL DEFAULT true,
  position_title text,
  department text,
  location text,
  manager_employee_key text,
  team_key text,
  branch_key text,
  cost_center text,
  working_pattern jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from date,
  effective_to date,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, assignment_id)
);

CREATE INDEX IF NOT EXISTS employee_assignments_employment_idx
  ON employee_assignments (company_code, employment_id, is_primary);

CREATE TABLE IF NOT EXISTS employee_key_authority_map (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  employment_id uuid NOT NULL REFERENCES employee_employments(employment_id),
  assignment_id uuid NOT NULL REFERENCES employee_assignments(assignment_id),
  mapping_status text NOT NULL DEFAULT 'active',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, employee_key),
  CHECK (mapping_status IN ('active','superseded','rolled_back')),
  UNIQUE (company_code, employment_id)
);

CREATE TABLE IF NOT EXISTS employee_authority_migration_journal (
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

ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS person_id uuid;
ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS employment_id uuid;
ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS assignment_id uuid;
"""


def authority_v2_enabled() -> bool:
    return str(os.environ.get("WATHEFNI_EMPLOYEE_AUTHORITY_V2") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def ensure_authority_schema(cur) -> None:
    cur.execute(WAVE2_SCHEMA_SQL)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _psycopg2_json(value: Any):
    from psycopg2.extras import Json

    return Json(_jsonable(value))


def canonical_email(value: Any) -> str:
    return str(value or "").strip().lower()


def resolve_ids_for_employee(employee: dict[str, Any]) -> dict[str, str]:
    """Deterministic IDs: prefer approved map, else mint from phone/email/key."""
    company = str(employee.get("company_code") or "").upper()
    key = str(employee.get("employee_key") or "")
    if company == "WATHEFNI" and key in APPROVED_WATHEFNI_MAP:
        approved = APPROVED_WATHEFNI_MAP[key]
        # Verify seed still matches live phone when present
        phone = phone_digits(employee.get("phone"))
        if phone:
            expected_seed = f"person:{company}:phone:{phone}"
            if approved["person_seed"] != expected_seed:
                raise ValueError(
                    f"approved map seed mismatch for {key}: map={approved['person_seed']} live={expected_seed}"
                )
            person_id, _ = mint_person_id(company_code=company, phone=phone)
            if person_id != approved["person_id"]:
                raise ValueError(f"approved person_id mismatch for {key}")
        return {
            "person_id": approved["person_id"],
            "employment_id": approved["employment_id"],
            "assignment_id": approved["assignment_id"],
            "person_seed": approved["person_seed"],
        }
    person_id, person_seed = mint_person_id(
        company_code=company,
        phone=employee.get("phone"),
        email=employee.get("email"),
        employee_key=key,
    )
    return {
        "person_id": person_id,
        "employment_id": mint_employment_id(company_code=company, employee_key=key),
        "assignment_id": mint_assignment_id(company_code=company, employee_key=key, slot="primary"),
        "person_seed": person_seed,
    }


def _next_employee_number(cur, company_code: str) -> str:
    company = str(company_code).upper()
    cur.execute(
        """
        SELECT employee_number FROM employee_persons
        WHERE company_code=%s AND employee_number ~ '^EMP-[0-9]+$'
        ORDER BY employee_number DESC LIMIT 1
        """,
        (company,),
    )
    row = cur.fetchone()
    if not row:
        return "EMP-0001"
    raw = str(dict(row).get("employee_number") or "EMP-0000")
    try:
        n = int(raw.split("-", 1)[1])
    except Exception:
        n = 0
    return f"EMP-{n + 1:04d}"


def _journal_upsert(
    cur,
    *,
    company_code: str,
    action: str,
    idempotency_key: str,
    before_json: dict[str, Any],
    after_json: dict[str, Any],
    evidence: dict[str, Any],
    status: str = "applied",
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO employee_authority_migration_journal (
          company_code, action, idempotency_key, before_json, after_json, evidence, status
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)
        ON CONFLICT (company_code, idempotency_key) DO UPDATE SET
          action=EXCLUDED.action,
          before_json=EXCLUDED.before_json,
          after_json=EXCLUDED.after_json,
          evidence=EXCLUDED.evidence,
          status=EXCLUDED.status,
          rolled_back_at=NULL,
          created_at=CASE
            WHEN employee_authority_migration_journal.status='rolled_back' THEN now()
            ELSE employee_authority_migration_journal.created_at
          END
        RETURNING *
        """,
        (
            str(company_code).upper(),
            action,
            idempotency_key,
            json.dumps(_jsonable(before_json)),
            json.dumps(_jsonable(after_json)),
            json.dumps(_jsonable(evidence)),
            status,
        ),
    )
    return dict(cur.fetchone())


def _assert_tenant_person(cur, *, company_code: str, person_id: str) -> None:
    cur.execute(
        "SELECT 1 FROM employee_persons WHERE company_code=%s AND person_id=%s",
        (str(company_code).upper(), person_id),
    )
    if not cur.fetchone():
        raise PermissionError("cross_tenant_or_missing_person")


def upsert_person_employment_assignment(
    cur,
    *,
    employee: dict[str, Any],
    hire_source: str = "backfill",
    employee_number: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or refresh authority rows for one hub employee (idempotent)."""
    company = str(employee.get("company_code") or "").upper()
    key = str(employee.get("employee_key") or "")
    if not company or not key:
        raise ValueError("company_code and employee_key required")
    ids = resolve_ids_for_employee(employee)
    person_id = ids["person_id"]
    employment_id = ids["employment_id"]
    assignment_id = ids["assignment_id"]
    phone = phone_digits(employee.get("phone")) or None
    email = canonical_email(employee.get("email")) or None
    status = str(employee.get("employment_status") or "active").strip().lower()
    if status != "left":
        status = "active"
    prov = {
        "source": hire_source,
        "legacy_employee_key": key,
        "person_seed": ids["person_seed"],
        "namespace": str(PERSON_NAMESPACE),
        **(provenance or {}),
    }

    cur.execute(
        "SELECT employee_number FROM employee_persons WHERE company_code=%s AND person_id=%s",
        (company, person_id),
    )
    existing_person = cur.fetchone()
    number = employee_number
    if existing_person and dict(existing_person).get("employee_number"):
        number = dict(existing_person)["employee_number"]
    elif not number:
        number = _next_employee_number(cur, company)

    cur.execute(
        """
        INSERT INTO employee_persons (
          person_id, company_code, display_name, primary_phone, primary_email,
          employee_number, status, provenance
        ) VALUES (%s,%s,%s,%s,%s,%s,'active',%s::jsonb)
        ON CONFLICT (person_id) DO UPDATE SET
          display_name=COALESCE(EXCLUDED.display_name, employee_persons.display_name),
          primary_phone=COALESCE(EXCLUDED.primary_phone, employee_persons.primary_phone),
          primary_email=COALESCE(EXCLUDED.primary_email, employee_persons.primary_email),
          employee_number=COALESCE(employee_persons.employee_number, EXCLUDED.employee_number),
          updated_at=now(),
          provenance=employee_persons.provenance || EXCLUDED.provenance
        WHERE employee_persons.company_code = EXCLUDED.company_code
        RETURNING *
        """,
        (
            person_id,
            company,
            employee.get("name"),
            phone,
            email,
            number,
            json.dumps(_jsonable(prov)),
        ),
    )
    person = dict(cur.fetchone())
    if str(person.get("company_code") or "").upper() != company:
        raise PermissionError("cross_tenant_person_write_denied")

    if phone:
        cur.execute(
            """
            INSERT INTO employee_person_contact_aliases (
              company_code, person_id, alias_type, alias_value, alias_value_raw, is_primary, provenance
            ) VALUES (%s,%s,'phone',%s,%s,true,%s::jsonb)
            ON CONFLICT (company_code, alias_type, alias_value) DO UPDATE SET
              person_id=EXCLUDED.person_id,
              is_primary=EXCLUDED.is_primary,
              alias_value_raw=COALESCE(EXCLUDED.alias_value_raw, employee_person_contact_aliases.alias_value_raw)
            """,
            (company, person_id, phone, str(employee.get("phone") or ""), json.dumps(_jsonable(prov))),
        )
    if email:
        cur.execute(
            """
            INSERT INTO employee_person_contact_aliases (
              company_code, person_id, alias_type, alias_value, alias_value_raw, is_primary, provenance
            ) VALUES (%s,%s,'email',%s,%s,true,%s::jsonb)
            ON CONFLICT (company_code, alias_type, alias_value) DO UPDATE SET
              person_id=EXCLUDED.person_id,
              is_primary=EXCLUDED.is_primary,
              alias_value_raw=COALESCE(EXCLUDED.alias_value_raw, employee_person_contact_aliases.alias_value_raw)
            """,
            (company, person_id, email, str(employee.get("email") or ""), json.dumps(_jsonable(prov))),
        )

    cur.execute(
        """
        INSERT INTO employee_employments (
          employment_id, company_code, person_id, employment_status, start_date, end_date,
          hire_source, app_key, legacy_employee_key, provenance
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (employment_id) DO UPDATE SET
          employment_status=EXCLUDED.employment_status,
          start_date=COALESCE(EXCLUDED.start_date, employee_employments.start_date),
          end_date=EXCLUDED.end_date,
          app_key=COALESCE(EXCLUDED.app_key, employee_employments.app_key),
          legacy_employee_key=COALESCE(EXCLUDED.legacy_employee_key, employee_employments.legacy_employee_key),
          updated_at=now(),
          provenance=employee_employments.provenance || EXCLUDED.provenance
        WHERE employee_employments.company_code = EXCLUDED.company_code
        RETURNING *
        """,
        (
            employment_id,
            company,
            person_id,
            status,
            employee.get("start_date") or employee.get("hire_date"),
            None if status == "active" else employee.get("updated_at"),
            hire_source,
            employee.get("app_key"),
            key,
            json.dumps(_jsonable(prov)),
        ),
    )
    employment = dict(cur.fetchone())

    cur.execute(
        """
        INSERT INTO employee_assignments (
          assignment_id, company_code, employment_id, person_id, is_primary,
          position_title, department, provenance
        ) VALUES (%s,%s,%s,%s,true,%s,%s,%s::jsonb)
        ON CONFLICT (assignment_id) DO UPDATE SET
          position_title=COALESCE(EXCLUDED.position_title, employee_assignments.position_title),
          department=COALESCE(EXCLUDED.department, employee_assignments.department),
          updated_at=now(),
          provenance=employee_assignments.provenance || EXCLUDED.provenance
        WHERE employee_assignments.company_code = EXCLUDED.company_code
        RETURNING *
        """,
        (
            assignment_id,
            company,
            employment_id,
            person_id,
            employee.get("position_title"),
            employee.get("department"),
            json.dumps(_jsonable(prov)),
        ),
    )
    assignment = dict(cur.fetchone())

    cur.execute(
        """
        INSERT INTO employee_key_authority_map (
          company_code, employee_key, person_id, employment_id, assignment_id,
          mapping_status, provenance
        ) VALUES (%s,%s,%s,%s,%s,'active',%s::jsonb)
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          person_id=EXCLUDED.person_id,
          employment_id=EXCLUDED.employment_id,
          assignment_id=EXCLUDED.assignment_id,
          mapping_status='active',
          updated_at=now(),
          provenance=employee_key_authority_map.provenance || EXCLUDED.provenance
        RETURNING *
        """,
        (company, key, person_id, employment_id, assignment_id, json.dumps(_jsonable(prov))),
    )
    mapping = dict(cur.fetchone())

    # Additive denormalized pointers on hub (nullable; non-destructive)
    cur.execute(
        """
        UPDATE employees
        SET person_id=%s, employment_id=%s, assignment_id=%s
        WHERE company_code=%s AND employee_key=%s
        """,
        (person_id, employment_id, assignment_id, company, key),
    )

    return {
        "person": _jsonable(person),
        "employment": _jsonable(employment),
        "assignment": _jsonable(assignment),
        "mapping": _jsonable(mapping),
        "ids": ids,
    }


def backfill_company_authority(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str | None = None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic backfill for a tenant. Idempotent on rerun."""
    company = str(company_code or "").upper()
    key = idempotency_key or f"wave2-backfill:{company}"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_authority_migration_journal
                WHERE company_code=%s AND idempotency_key=%s AND status='applied'
                LIMIT 1
                """,
                (company, key),
            )
            existing = cur.fetchone()
            # Always allow refresh upserts; journal marks idempotent when counts unchanged after
            if employee_keys:
                cur.execute(
                    """
                    SELECT * FROM employees
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    ORDER BY created_at NULLS LAST, employee_key
                    """,
                    (company, list(employee_keys)),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM employees
                    WHERE company_code=%s
                    ORDER BY created_at NULLS LAST, employee_key
                    """,
                    (company,),
                )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            before = {
                "employee_count": len(rows),
                "employee_keys": [r["employee_key"] for r in rows],
            }
            results = []
            for emp in rows:
                results.append(upsert_person_employment_assignment(cur, employee=emp, hire_source="wave2_backfill"))
            after = {
                "person_count": _count(cur, "employee_persons", company),
                "employment_count": _count(cur, "employee_employments", company),
                "assignment_count": _count(cur, "employee_assignments", company),
                "mapping_count": _count(cur, "employee_key_authority_map", company),
                "results": results,
            }
            # Duplicate guards
            cur.execute(
                """
                SELECT person_id, count(*) AS n FROM employee_persons
                WHERE company_code=%s GROUP BY person_id HAVING count(*) > 1
                """,
                (company,),
            )
            dup_persons = [dict(r) for r in (cur.fetchall() or [])]
            journal = _journal_upsert(
                cur,
                company_code=company,
                action="backfill_authority",
                idempotency_key=key,
                before_json=before,
                after_json={"person_count": after["person_count"], "employment_count": after["employment_count"], "assignment_count": after["assignment_count"], "mapping_count": after["mapping_count"]},
                evidence={
                    "approved_map_keys": list(APPROVED_WATHEFNI_MAP) if company == "WATHEFNI" else [],
                    "duplicate_persons": dup_persons,
                    "idempotent_replay": bool(existing),
                },
                status="applied",
            )
            conn.commit()
            return {
                "ok": True,
                "status": "idempotent" if existing else "applied",
                "journal_id": str(journal.get("journal_id")),
                "before": before,
                "after": {
                    "person_count": after["person_count"],
                    "employment_count": after["employment_count"],
                    "assignment_count": after["assignment_count"],
                    "mapping_count": after["mapping_count"],
                },
                "ids": [r["ids"] for r in results],
                "duplicate_persons": dup_persons,
            }


def _count(cur, table: str, company: str) -> int:
    cur.execute(f"SELECT count(*)::bigint AS n FROM {table} WHERE company_code=%s", (company,))
    return int(dict(cur.fetchone())["n"])


def rollback_company_authority(
    legacy: Any,
    *,
    company_code: str,
    idempotency_key: str | None = None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Remove Wave 2 authority rows; restore hub nullable pointers to NULL.

    When employee_keys is provided, only those mappings/related rows are removed.
    Does not delete or rewrite employees hub business columns.
    """
    company = str(company_code or "").upper()
    key = idempotency_key or f"wave2-backfill:{company}"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            if employee_keys:
                keys = list(employee_keys)
                cur.execute(
                    """
                    SELECT person_id::text AS person_id, employment_id::text AS employment_id,
                           assignment_id::text AS assignment_id, employee_key
                    FROM employee_key_authority_map
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
                maps = [dict(r) for r in (cur.fetchall() or [])]
                person_ids = sorted({m["person_id"] for m in maps})
                employment_ids = sorted({m["employment_id"] for m in maps})
                assignment_ids = sorted({m["assignment_id"] for m in maps})
                before = {
                    "scoped_keys": keys,
                    "mappings": len(maps),
                    "persons": len(person_ids),
                    "employments": len(employment_ids),
                    "assignments": len(assignment_ids),
                }
                cur.execute(
                    "UPDATE employees SET person_id=NULL, employment_id=NULL, assignment_id=NULL WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                if assignment_ids:
                    cur.execute(
                        "DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])",
                        (company, assignment_ids),
                    )
                if employment_ids:
                    cur.execute(
                        "DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])",
                        (company, employment_ids),
                    )
                # Drop persons only when no remaining employments reference them
                for pid in person_ids:
                    cur.execute(
                        "SELECT 1 FROM employee_employments WHERE company_code=%s AND person_id=%s LIMIT 1",
                        (company, pid),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        "DELETE FROM employee_person_contact_aliases WHERE company_code=%s AND person_id=%s",
                        (company, pid),
                    )
                    cur.execute(
                        "DELETE FROM employee_persons WHERE company_code=%s AND person_id=%s",
                        (company, pid),
                    )
                after = {
                    "mappings": _count_keys(cur, company, keys),
                }
            else:
                before = {
                    "persons": _count(cur, "employee_persons", company),
                    "employments": _count(cur, "employee_employments", company),
                    "assignments": _count(cur, "employee_assignments", company),
                    "mappings": _count(cur, "employee_key_authority_map", company),
                }
                cur.execute(
                    "UPDATE employees SET person_id=NULL, employment_id=NULL, assignment_id=NULL WHERE company_code=%s",
                    (company,),
                )
                cur.execute("DELETE FROM employee_key_authority_map WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_assignments WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_employments WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_person_contact_aliases WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employee_persons WHERE company_code=%s", (company,))
                after = {
                    "persons": _count(cur, "employee_persons", company),
                    "employments": _count(cur, "employee_employments", company),
                    "assignments": _count(cur, "employee_assignments", company),
                    "mappings": _count(cur, "employee_key_authority_map", company),
                }
            cur.execute(
                """
                UPDATE employee_authority_migration_journal
                SET status='rolled_back', rolled_back_at=now()
                WHERE company_code=%s AND idempotency_key=%s
                RETURNING *
                """,
                (company, key),
            )
            journal = dict(cur.fetchone() or {})
            conn.commit()
            return {"ok": True, "status": "rolled_back", "before": before, "after": after, "journal": _jsonable(journal)}


def _count_keys(cur, company: str, keys: list[str]) -> int:
    cur.execute(
        "SELECT count(*)::bigint AS n FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
        (company, keys),
    )
    return int(dict(cur.fetchone())["n"])


def sync_authority_from_hub_employee(legacy: Any, employee: dict[str, Any], *, hire_source: str = "hub_sync") -> dict[str, Any] | None:
    """Best-effort shadow sync used by create/update/hire when V2 enabled."""
    if not authority_v2_enabled():
        return None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            out = upsert_person_employment_assignment(cur, employee=employee, hire_source=hire_source)
            conn.commit()
            return out


def get_authority_projection(legacy: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    company = str(company_code or "").upper()
    key = str(employee_key or "")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            cur.execute(
                """
                SELECT m.*, p.employee_number, p.display_name AS person_name,
                       e.employment_status AS authority_employment_status,
                       e.start_date AS employment_start_date, e.end_date AS employment_end_date,
                       a.position_title AS assignment_position_title, a.department AS assignment_department
                FROM employee_key_authority_map m
                JOIN employee_persons p ON p.person_id=m.person_id AND p.company_code=m.company_code
                JOIN employee_employments e ON e.employment_id=m.employment_id AND e.company_code=m.company_code
                JOIN employee_assignments a ON a.assignment_id=m.assignment_id AND a.company_code=m.company_code
                WHERE m.company_code=%s AND m.employee_key=%s AND m.mapping_status='active'
                LIMIT 1
                """,
                (company, key),
            )
            row = cur.fetchone()
            return _jsonable(dict(row)) if row else None


def open_rehire_employment(
    legacy: Any,
    *,
    company_code: str,
    person_id: str,
    new_employee_key: str,
    phone: str,
    name: str,
    position_title: str | None = None,
    app_key: str | None = None,
) -> dict[str, Any]:
    """Reuse person; create new employment + assignment + hub compatibility row.

    Prior employments remain as service history (typically status=left).
    """
    company = str(company_code or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            _assert_tenant_person(cur, company_code=company, person_id=person_id)
            # Mark current active employments left (history preserved)
            cur.execute(
                """
                UPDATE employee_employments
                SET employment_status='left', end_date=COALESCE(end_date, CURRENT_DATE), updated_at=now()
                WHERE company_code=%s AND person_id=%s AND employment_status='active'
                """,
                (company, person_id),
            )
            employment_id = mint_employment_id(company_code=company, employee_key=new_employee_key)
            assignment_id = mint_assignment_id(company_code=company, employee_key=new_employee_key, slot="primary")
            # Hub row for compatibility
            cur.execute(
                """
                INSERT INTO employees (employee_key, phone, company_code, name, position_title, app_key, employment_status, onboarding_status)
                VALUES (%s,%s,%s,%s,%s,%s,'active','not_started')
                ON CONFLICT (employee_key) DO UPDATE SET
                  phone=EXCLUDED.phone,
                  name=COALESCE(EXCLUDED.name, employees.name),
                  position_title=COALESCE(EXCLUDED.position_title, employees.position_title),
                  employment_status='active',
                  updated_at=now()
                RETURNING *
                """,
                (new_employee_key, phone_digits(phone) or phone, company, name, position_title, app_key),
            )
            emp = dict(cur.fetchone())
            emp["person_id"] = person_id  # force reuse
            # Override resolve_ids by writing directly
            prov = {"source": "rehire", "reused_person_id": person_id}
            cur.execute(
                """
                INSERT INTO employee_employments (
                  employment_id, company_code, person_id, employment_status, start_date,
                  hire_source, app_key, legacy_employee_key, provenance
                ) VALUES (%s,%s,%s,'active',CURRENT_DATE,'rehire',%s,%s,%s::jsonb)
                ON CONFLICT (employment_id) DO UPDATE SET
                  employment_status='active', end_date=NULL, updated_at=now()
                RETURNING *
                """,
                (employment_id, company, person_id, app_key, new_employee_key, json.dumps(prov)),
            )
            employment = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_assignments (
                  assignment_id, company_code, employment_id, person_id, is_primary, position_title, provenance
                ) VALUES (%s,%s,%s,%s,true,%s,%s::jsonb)
                ON CONFLICT (assignment_id) DO UPDATE SET position_title=COALESCE(EXCLUDED.position_title, employee_assignments.position_title), updated_at=now()
                RETURNING *
                """,
                (assignment_id, company, employment_id, person_id, position_title, json.dumps(prov)),
            )
            assignment = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_key_authority_map (
                  company_code, employee_key, person_id, employment_id, assignment_id, mapping_status, provenance
                ) VALUES (%s,%s,%s,%s,%s,'active',%s::jsonb)
                ON CONFLICT (company_code, employee_key) DO UPDATE SET
                  person_id=EXCLUDED.person_id, employment_id=EXCLUDED.employment_id,
                  assignment_id=EXCLUDED.assignment_id, mapping_status='active', updated_at=now()
                """,
                (company, new_employee_key, person_id, employment_id, assignment_id, json.dumps(prov)),
            )
            cur.execute(
                "UPDATE employees SET person_id=%s, employment_id=%s, assignment_id=%s WHERE employee_key=%s AND company_code=%s",
                (person_id, employment_id, assignment_id, new_employee_key, company),
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
                "person_id": person_id,
                "employment": _jsonable(employment),
                "assignment": _jsonable(assignment),
                "employee": _jsonable(emp),
                "employment_history_count": history_n,
            }


def assert_no_cross_tenant_access(legacy: Any, *, actor_company: str, person_id: str) -> bool:
    """Fail-closed: person must belong to actor company."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            try:
                _assert_tenant_person(cur, company_code=actor_company, person_id=person_id)
                return True
            except PermissionError:
                return False


def verify_approved_map_ids(legacy: Any, *, company_code: str = "WATHEFNI") -> dict[str, Any]:
    company = str(company_code).upper()
    mismatches = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_authority_schema(cur)
            for key, approved in APPROVED_WATHEFNI_MAP.items():
                cur.execute(
                    """
                    SELECT person_id::text, employment_id::text, assignment_id::text
                    FROM employee_key_authority_map
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (company, key),
                )
                row = cur.fetchone()
                if not row:
                    mismatches.append({"employee_key": key, "error": "missing_mapping"})
                    continue
                got = dict(row)
                for field in ("person_id", "employment_id", "assignment_id"):
                    if str(got.get(field)) != approved[field]:
                        mismatches.append({"employee_key": key, "field": field, "expected": approved[field], "got": got.get(field)})
    return {"ok": not mismatches, "mismatches": mismatches}
