"""Durable, idempotent hiring operation authority.

The canonical application transition, employee link, onboarding seed, and
operation completion commit in one Postgres transaction. External delivery and
sheet mirrors are explicitly outside the committed hiring result.
"""

from __future__ import annotations

import uuid
from typing import Any

import recruiting_lifecycle as lifecycle


def ensure_hire_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hire_operations (
          operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          employee_key text,
          status text NOT NULL DEFAULT 'prepared',
          idempotency_key text NOT NULL,
          confirmation_id uuid,
          actor_user_id text,
          actor_phone text,
          channel text,
          expected_from_stage text NOT NULL,
          expected_version bigint NOT NULL,
          structured_reason jsonb NOT NULL DEFAULT '{}'::jsonb,
          result jsonb NOT NULL DEFAULT '{}'::jsonb,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          CHECK (status IN ('prepared','processing','completed','failed','manual_review')),
          UNIQUE (company_code, idempotency_key)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS hire_operations_open_app_uq
          ON hire_operations (company_code, app_key)
          WHERE status IN ('prepared','processing')
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS hire_operations_reconcile_idx
          ON hire_operations (status, updated_at)
          WHERE status IN ('prepared','processing','failed')
        """
    )


def employee_link_collisions(legacy: Any) -> list[dict[str, Any]]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_code, app_key, count(*) AS employee_count,
                       array_agg(employee_key ORDER BY employee_key) AS employee_keys
                FROM employees
                WHERE app_key IS NOT NULL AND app_key <> ''
                GROUP BY company_code, app_key
                HAVING count(*) > 1
                ORDER BY company_code, app_key
                """
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def install_employee_link_constraint(legacy: Any) -> dict[str, Any]:
    collisions = employee_link_collisions(legacy)
    if collisions:
        return {"ok": False, "error": "employee_link_collisions", "collisions": legacy.json_safe(collisions)}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS employees_company_app_key_uq
                  ON employees (company_code, app_key)
                  WHERE app_key IS NOT NULL AND app_key <> ''
                """
            )
        conn.commit()
    return {"ok": True}


def prepare_hire_operation(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    idempotency_key: str,
    expected_from_stage: str,
    expected_version: int,
    actor_user_id: str | None,
    actor_phone: str | None,
    channel: str,
    structured_reason: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    key = str(app_key or "").strip()
    idem = str(idempotency_key or "").strip()
    if not company or not key:
        return {"ok": False, "error": "tenant_scope_required"}
    if not idem:
        return {"ok": False, "error": "idempotency_key_required"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hire_schema(cur)
            lifecycle.ensure_lifecycle_schema(cur)
            cur.execute(
                """
                SELECT * FROM applications
                WHERE company_code=%s AND app_key=%s
                FOR UPDATE
                """,
                (company, key),
            )
            application = cur.fetchone()
            if not application:
                return {"ok": False, "error": "application_not_found"}
            cur.execute(
                """
                SELECT * FROM hire_operations
                WHERE company_code=%s AND app_key=%s AND status IN ('prepared','processing')
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (company, key),
            )
            open_operation = cur.fetchone()
            if open_operation:
                operation = dict(open_operation)
                same_actor = (
                    str(operation.get("actor_user_id") or "") == str(actor_user_id or "")
                    and str(operation.get("actor_phone") or "") == str(legacy.digits(actor_phone) or "")
                )
                same_observation = (
                    str(operation.get("expected_from_stage") or "") == str(expected_from_stage or "")
                    and int(operation.get("expected_version") or 0) == int(expected_version)
                )
                if same_actor and same_observation:
                    return {"ok": True, "idempotent": True, "operation": legacy.json_safe(operation)}
                return {"ok": False, "error": "hire_operation_in_progress"}
            cur.execute(
                """
                INSERT INTO hire_operations (
                  company_code, app_key, idempotency_key, actor_user_id, actor_phone,
                  channel, expected_from_stage, expected_version, structured_reason
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    company,
                    key,
                    idem,
                    str(actor_user_id or "") or None,
                    legacy.digits(actor_phone) or None,
                    str(channel or "unknown"),
                    str(expected_from_stage or ""),
                    int(expected_version),
                    legacy.Json(legacy.json_safe(structured_reason or {})),
                ),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "SELECT * FROM hire_operations WHERE company_code=%s AND idempotency_key=%s",
                    (company, idem),
                )
                row = cur.fetchone()
            operation = dict(row)
        conn.commit()
    return {"ok": True, "operation": legacy.json_safe(operation)}


def _employee_transaction(
    legacy: Any,
    operation_id: str,
    confirmation_id: str,
) -> Any:
    def apply(cur: Any, before: dict[str, Any], hired: dict[str, Any]) -> dict[str, Any]:
        ensure_hire_schema(cur)
        cur.execute("SELECT * FROM hire_operations WHERE operation_id=%s FOR UPDATE", (operation_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "hire_operation_not_found"}
        operation = dict(row)
        if operation.get("status") == "completed":
            return {
                "ok": True,
                "idempotent": True,
                "operation_id": operation_id,
                "employee_key": operation.get("employee_key"),
            }
        company = str(hired.get("company_code") or "").upper()
        phone = legacy.digits(hired.get("phone"))
        if not company or not phone:
            return {"ok": False, "error": "candidate_identity_incomplete"}
        cur.execute("SELECT * FROM candidates WHERE phone=%s LIMIT 1", (phone,))
        candidate_row = cur.fetchone()
        candidate = dict(candidate_row) if candidate_row else {}
        employee_key = f"{company}-{phone}"
        cur.execute(
            """
            SELECT * FROM employees
            WHERE company_code=%s AND (app_key=%s OR employee_key=%s)
            ORDER BY CASE WHEN app_key=%s THEN 0 ELSE 1 END
            FOR UPDATE
            """,
            (company, hired["app_key"], employee_key, hired["app_key"]),
        )
        matches = [dict(item) for item in (cur.fetchall() or [])]
        linked = [item for item in matches if str(item.get("app_key") or "") == str(hired["app_key"])]
        if len(linked) > 1:
            cur.execute(
                "UPDATE hire_operations SET status='manual_review', last_error='duplicate_employee_link', updated_at=now() WHERE operation_id=%s",
                (operation_id,),
            )
            return {"ok": False, "error": "duplicate_employee_link"}
        employee = linked[0] if linked else (matches[0] if matches else None)
        name = str(hired.get("candidate_name") or candidate.get("name") or phone)
        email = str(hired.get("candidate_email") or candidate.get("email") or "").strip() or None
        position = str(hired.get("position_title") or hired.get("position_code") or "").strip() or None
        if employee:
            if employee.get("app_key") and str(employee.get("app_key")) != str(hired["app_key"]):
                return {"ok": False, "error": "employee_already_linked_to_other_application"}
            cur.execute(
                """
                UPDATE employees
                SET app_key=%s, name=COALESCE(NULLIF(name,''),%s),
                    email=COALESCE(email,%s), position_title=COALESCE(position_title,%s),
                    updated_at=now()
                WHERE employee_key=%s AND company_code=%s
                RETURNING *
                """,
                (hired["app_key"], name, email, position, employee["employee_key"], company),
            )
            employee = dict(cur.fetchone())
        else:
            cur.execute(
                """
                INSERT INTO employees (
                  employee_key, phone, company_code, app_key, name, email,
                  position_title, profile, raw_json, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb,%s,now())
                RETURNING *
                """,
                (
                    employee_key,
                    phone,
                    company,
                    hired["app_key"],
                    name,
                    email,
                    position,
                    legacy.Json({"source": "canonical_hire", "operation_id": operation_id}),
                ),
            )
            employee = dict(cur.fetchone())
        # Kuwait first-client foundation: one immutable employment-applicability
        # snapshot in the same TX as the employee row (no duplicate on replay).
        try:
            import kuwait_first_client_foundation as _kw_foundation

            _kw_foundation.ensure_foundation_schema(cur)
            snap = _kw_foundation.create_applicability_snapshot_on_cur(
                legacy,
                cur,
                company_code=company,
                employee_key=str(employee["employee_key"]),
                app_key=str(hired["app_key"]),
                hire_operation_id=str(operation_id),
                hire_operation=operation,
                actor_user_id=str(operation.get("actor_user_id") or "") or None,
            )
            result_snapshot_id = str((snap.get("snapshot") or {}).get("snapshot_id") or "")
        except Exception as exc:
            return {"ok": False, "error": "employment_applicability_snapshot_failed", "detail": f"{type(exc).__name__}:{exc}"}
        # Compliance seed respects employee category when already known; otherwise
        # nationals-safe defaults (no residence/work_permit required yet).
        category = "unspecified"
        try:
            cur.execute(
                "SELECT employee_category FROM employee_identity WHERE company_code=%s AND employee_key=%s",
                (company, employee["employee_key"]),
            )
            idrow = cur.fetchone()
            if idrow:
                category = str(idrow.get("employee_category") or "unspecified")
        except Exception:
            category = "unspecified"
        if hasattr(legacy, "_seed_employee_compliance_documents"):
            legacy._seed_employee_compliance_documents(
                cur, company, employee["employee_key"], employee_category=category
            )
        if hasattr(legacy, "onboarding_seed_enabled") and legacy.onboarding_seed_enabled() and hasattr(legacy, "seed_onboarding_items"):
            legacy.seed_onboarding_items(cur, employee)
        cur.execute(
            """
            UPDATE applications
            SET raw_json=COALESCE(raw_json,'{}'::jsonb) ||
                jsonb_build_object('hiring', jsonb_build_object(
                  'operation_id', %s, 'employee_key', %s, 'committed', true
                ))
            WHERE company_code=%s AND app_key=%s
            """,
            (operation_id, employee["employee_key"], company, hired["app_key"]),
        )
        result = {
            "ok": True,
            "operation_id": operation_id,
            "employee_key": employee["employee_key"],
            "application_app_key": hired["app_key"],
            "employment_applicability_snapshot_id": locals().get("result_snapshot_id") or "",
        }
        cur.execute(
            """
            UPDATE hire_operations
            SET status='completed', employee_key=%s, confirmation_id=%s, result=%s,
                completed_at=now(), updated_at=now(), last_error=NULL
            WHERE operation_id=%s
            """,
            (employee["employee_key"], confirmation_id, legacy.Json(result), operation_id),
        )
        return result

    return apply


def execute_hire_operation(
    legacy: Any,
    *,
    operation_id: str,
    confirmation_id: str,
    confirmation_token: str,
    permissions: set[str] | list[str],
) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hire_schema(cur)
            cur.execute("SELECT * FROM hire_operations WHERE operation_id=%s", (operation_id,))
            row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "hire_operation_not_found"}
    operation = dict(row)
    if operation.get("status") == "completed":
        return {"ok": True, "idempotent": True, "operation": legacy.json_safe(operation)}
    payload = {
        **(operation.get("structured_reason") if isinstance(operation.get("structured_reason"), dict) else {}),
        "hiring_reference": str(operation_id),
        "operation_id": str(operation_id),
    }
    result = lifecycle.transition_application(
        legacy,
        app_key=str(operation["app_key"]),
        company_code=str(operation["company_code"]),
        to_stage="hired",
        trigger="hire_candidate",
        expected_from_stage=str(operation["expected_from_stage"]),
        expected_version=int(operation["expected_version"]),
        actor_type="human",
        actor_user_id=str(operation.get("actor_user_id") or "") or None,
        actor_phone=operation.get("actor_phone"),
        channel=str(operation.get("channel") or "unknown"),
        confirmation_id=confirmation_id,
        confirmation_token=confirmation_token,
        confirmation_action="hire",
        confirmation_payload=payload,
        human_confirmed=True,
        idempotency_key=f"hire-operation:{operation_id}",
        permissions=permissions,
        metadata=payload,
        run_hire_side_effects=False,
        transactional_side_effect=_employee_transaction(legacy, str(operation_id), confirmation_id),
    )
    return {"ok": bool(result.get("ok")), "operation_id": operation_id, "transition": legacy.json_safe(result)}


def reconcile_hire_operations(legacy: Any, *, limit: int = 100) -> dict[str, Any]:
    """Report recoverable work. Execution still requires the original confirmation."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_hire_schema(cur)
            cur.execute(
                """
                SELECT * FROM hire_operations
                WHERE status IN ('prepared','processing','failed')
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 500)),),
            )
            operations = [dict(row) for row in (cur.fetchall() or [])]
            cur.execute(
                """
                SELECT a.company_code, a.app_key
                FROM applications a
                LEFT JOIN employees e
                  ON e.company_code=a.company_code AND e.app_key=a.app_key
                WHERE lower(a.status)='hired' AND e.employee_key IS NULL
                ORDER BY a.updated_at ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 500)),),
            )
            half_hires = [dict(row) for row in (cur.fetchall() or [])]
    return {
        "ok": not half_hires,
        "operations": legacy.json_safe(operations),
        "hired_without_employee": legacy.json_safe(half_hires),
    }
