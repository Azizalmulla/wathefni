"""Production-safe employee employment-status approval (Wave 1B).

Model:
  - Production / non-canary: two-person pending request → decide (approve|reject).
    Requester cannot approve their own request even with dual grants.
  - Allowlisted internal non-prod: optional self_approved_internal_canary
    single-step commit (existing path).
  - Never invent an approver or silently auto-approve.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


REQUEST_STATUSES = frozenset({"pending", "approved", "rejected", "cancelled", "expired"})
DECISION_ACTIONS = frozenset({"approve", "reject"})


def ensure_employee_status_approval_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_status_change_requests (
          request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          idempotency_key text NOT NULL,
          request_hash text NOT NULL,
          requested_status text NOT NULL,
          expected_status text NOT NULL,
          expected_updated_at timestamptz NOT NULL,
          reason text NOT NULL,
          approval_reference text NOT NULL,
          requester_user_id uuid NOT NULL REFERENCES dashboard_users(user_id),
          designated_approver_user_id uuid NOT NULL REFERENCES dashboard_users(user_id),
          status text NOT NULL DEFAULT 'pending',
          decision_reason text,
          decided_by_user_id uuid REFERENCES dashboard_users(user_id),
          decided_at timestamptz,
          resulting_change_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('pending','approved','rejected','cancelled','expired')),
          CHECK (requested_status IN ('active','left')),
          CHECK (expected_status IN ('active','left')),
          CHECK (requester_user_id <> designated_approver_user_id),
          UNIQUE (company_code, idempotency_key)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_status_change_requests_pending
          ON employee_status_change_requests(company_code, designated_approver_user_id, status, created_at DESC)
          WHERE status = 'pending'
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_status_change_requests_employee
          ON employee_status_change_requests(company_code, employee_key, status, created_at DESC)
        """
    )


def request_hash_payload(
    *,
    company_code: str,
    employee_key: str,
    requested_status: str,
    expected_status: str,
    expected_updated_at: datetime,
    reason: str,
    approval_reference: str,
    requester_user_id: str,
    designated_approver_user_id: str,
    idempotency_key: str,
) -> str:
    payload = {
        "company_code": str(company_code or "").upper(),
        "employee_key": str(employee_key),
        "requested_status": requested_status,
        "expected_status": expected_status,
        "expected_updated_at": expected_updated_at.isoformat(),
        "reason": reason.strip(),
        "approval_reference": approval_reference.strip(),
        "requester_user_id": requester_user_id,
        "designated_approver_user_id": designated_approver_user_id,
        "idempotency_key": idempotency_key.strip(),
        "approval_mode": "separate_approval",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def list_eligible_status_approvers(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    exclude_user_id: str | None = None,
) -> list[dict[str, Any]]:
    company = str(company_code or "").upper()
    exclude = str(exclude_user_id or "").strip()
    cur.execute(
        """
        SELECT *
        FROM dashboard_users
        WHERE company_code=%s
        ORDER BY name NULLS LAST, email NULLS LAST, user_id
        """,
        (company,),
    )
    out: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        user = dict(row)
        user_id = str(user.get("user_id") or "")
        if not user_id or (exclude and user_id == exclude):
            continue
        if not legacy._normal_dashboard_operator(user):
            continue
        perms = legacy.dashboard_effective_permissions_for_user(user, cur=cur)
        if "employees.status.approve" not in perms:
            continue
        out.append(
            {
                "user_id": user_id,
                "name": user.get("name") or "",
                "email": user.get("email") or "",
                "role": user.get("role") or "",
                "phone": legacy.digits(user.get("phone")) or "",
            }
        )
    return out


def approval_policy(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
) -> dict[str, Any]:
    company = str(company_code or "").upper()
    actor = str(actor_user_id or "").strip()
    canary_allowed = bool(legacy.employee_status_canary_allowed(company))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_employee_status_approval_schema(cur)
            eligible = list_eligible_status_approvers(
                legacy, cur, company_code=company, exclude_user_id=actor
            )
            cur.execute(
                "SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s LIMIT 1",
                (company, actor),
            )
            me = dict(cur.fetchone() or {})
            my_perms = legacy.dashboard_effective_permissions_for_user(me, cur=cur) if me else []
            conn.commit()
    dual_grant = "employees.manage" in my_perms and "employees.status.approve" in my_perms
    production_safe_required = not canary_allowed
    return {
        "company_code": company,
        "environment": legacy.employee_status_runtime_env(),
        "canary_allowed": canary_allowed,
        "production_safe_required": production_safe_required,
        "self_approval_allowed": canary_allowed,
        "requester_has_approve_permission": "employees.status.approve" in my_perms,
        "requester_dual_grant": dual_grant,
        "eligible_approver_count": len(eligible),
        "eligible_approvers": eligible,
        "status_change_available": bool(eligible) or canary_allowed,
        "blocked_reason": (
            None
            if (eligible or canary_allowed)
            else "no_eligible_approver"
        ),
        "rules": {
            "dual_grant_cannot_self_approve_outside_canary": True,
            "fake_approver_forbidden": True,
            "silent_auto_approve_forbidden": True,
            "rejected_leaves_employee_unchanged": True,
            "cancelled_leaves_employee_unchanged": True,
            "stale_expected_version_conflict": "employee_version_conflict",
            "replay_same_hash": "idempotent",
            "replay_different_hash": "idempotency_conflict",
        },
    }


def create_status_change_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    requested_status: str,
    expected_status: str,
    expected_updated_at: datetime,
    reason: str,
    approval_reference: str,
    designated_approver_user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    requester_user_id = str(context.get("actor_user_id") or "").strip()
    approver_id = str(designated_approver_user_id or "").strip()
    key = str(idempotency_key or "").strip()
    if not requester_user_id:
        raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied", "message": "You do not have access to do that."})
    if approver_id == requester_user_id or approver_id == "self":
        raise legacy.HTTPException(
            status_code=403,
            detail={
                "error": "self_approval_forbidden",
                "message": "A separate approver is required. You cannot approve your own status change.",
            },
        )
    req_hash = request_hash_payload(
        company_code=company,
        employee_key=employee_key,
        requested_status=requested_status,
        expected_status=expected_status,
        expected_updated_at=expected_updated_at,
        reason=reason,
        approval_reference=approval_reference,
        requester_user_id=requester_user_id,
        designated_approver_user_id=approver_id,
        idempotency_key=key,
    )
    with legacy.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                ensure_employee_status_approval_schema(cur)
                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s FOR SHARE",
                    (company, requester_user_id),
                )
                requester = dict(cur.fetchone() or {})
                requester_permissions = legacy.dashboard_effective_permissions_for_user(requester, cur=cur) if requester else []
                if not legacy._normal_dashboard_operator(requester) or "employees.manage" not in requester_permissions:
                    raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied", "message": "You do not have access to do that."})

                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s FOR SHARE",
                    (company, approver_id),
                )
                approver = dict(cur.fetchone() or {})
                approver_permissions = legacy.dashboard_effective_permissions_for_user(approver, cur=cur) if approver else []
                if not legacy._normal_dashboard_operator(approver) or "employees.status.approve" not in approver_permissions:
                    raise legacy.HTTPException(
                        status_code=403,
                        detail={"error": "approver_permission_denied", "message": "The designated approver is not authorized for employee status changes."},
                    )

                eligible_ids = {
                    str(item["user_id"])
                    for item in list_eligible_status_approvers(
                        legacy, cur, company_code=company, exclude_user_id=requester_user_id
                    )
                }
                if approver_id not in eligible_ids:
                    raise legacy.HTTPException(
                        status_code=422,
                        detail={"error": "approver_not_eligible", "message": "Choose an eligible separate approver."},
                    )

                cur.execute(
                    "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s FOR SHARE",
                    (company, str(employee_key)),
                )
                employee = dict(cur.fetchone() or {})
                if not employee:
                    raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found", "message": "We couldn't find that employee."})
                current_status = legacy._canonical_employee_status(employee.get("employment_status"))
                if current_status != expected_status or employee.get("updated_at") != expected_updated_at:
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={"error": "employee_version_conflict", "message": "This employee changed after the status form was opened."},
                    )
                if current_status == requested_status and str(employee.get("employment_status") or "").strip().lower() == requested_status:
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={"error": "employee_status_unchanged", "message": "This employee already has that status."},
                    )

                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"employee-status-request:{company}:{key}",),
                )
                cur.execute(
                    "SELECT * FROM employee_status_change_requests WHERE company_code=%s AND idempotency_key=%s FOR UPDATE",
                    (company, key),
                )
                existing = cur.fetchone()
                if existing:
                    row = dict(existing)
                    if row["request_hash"] != req_hash:
                        raise legacy.HTTPException(
                            status_code=409,
                            detail={"error": "idempotency_conflict", "message": "This request key was already used for a different status approval request."},
                        )
                    conn.commit()
                    return {"ok": True, "idempotent": True, "request": legacy.json_safe(row)}

                cur.execute(
                    """
                    INSERT INTO employee_status_change_requests (
                      company_code, employee_key, idempotency_key, request_hash,
                      requested_status, expected_status, expected_updated_at,
                      reason, approval_reference, requester_user_id,
                      designated_approver_user_id, status
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
                    RETURNING *
                    """,
                    (
                        company,
                        str(employee_key),
                        key,
                        req_hash,
                        requested_status,
                        expected_status,
                        expected_updated_at,
                        reason.strip(),
                        approval_reference.strip(),
                        requester_user_id,
                        approver_id,
                    ),
                )
                row = dict(cur.fetchone())
                legacy.write_admin_audit(
                    cur,
                    legacy._permission_operator_context(requester, requester_permissions),
                    "employee_status_approval_requested",
                    summary="Requested a two-person employment status change.",
                    target_type="employee",
                    target=str(employee_key),
                    details={
                        "request_id": str(row["request_id"]),
                        "requested_status": requested_status,
                        "designated_approver_user_id": approver_id,
                        "idempotency_key": key,
                    },
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"ok": True, "idempotent": False, "request": legacy.json_safe(row)}


def cancel_status_change_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    actor = str(context.get("actor_user_id") or "").strip()
    with legacy.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                ensure_employee_status_approval_schema(cur)
                cur.execute(
                    "SELECT * FROM employee_status_change_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                    (company, str(request_id)),
                )
                row = cur.fetchone()
                if not row:
                    raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found", "message": "We couldn't find that approval request."})
                req = dict(row)
                if str(req.get("requester_user_id")) != actor:
                    raise legacy.HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Only the requester can cancel this approval request."})
                if req.get("status") != "pending":
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={"error": "request_not_pending", "message": f"This request is already {req.get('status')}."},
                    )
                cur.execute(
                    """
                    UPDATE employee_status_change_requests
                    SET status='cancelled', decided_by_user_id=%s, decided_at=now(),
                        decision_reason='cancelled_by_requester', updated_at=now()
                    WHERE request_id=%s
                    RETURNING *
                    """,
                    (actor, str(request_id)),
                )
                updated = dict(cur.fetchone())
                legacy.record_admin_audit(
                    context,
                    "employee_status_approval_cancelled",
                    summary="Cancelled a pending employment status approval request.",
                    target_type="employee",
                    target=str(updated.get("employee_key") or ""),
                    details={"request_id": str(request_id)},
                    status="completed",
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"ok": True, "request": legacy.json_safe(updated)}


def decide_status_change_request(
    legacy: Any,
    context: dict[str, Any],
    *,
    request_id: str,
    action: str,
    decision_reason: str | None = None,
) -> dict[str, Any]:
    company = str(context.get("company_code") or "").upper()
    actor = str(context.get("actor_user_id") or "").strip()
    decision = str(action or "").strip().lower()
    if decision not in DECISION_ACTIONS:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_decision", "message": "Choose approve or reject."})

    with legacy.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                ensure_employee_status_approval_schema(cur)
                cur.execute(
                    "SELECT * FROM employee_status_change_requests WHERE company_code=%s AND request_id=%s FOR UPDATE",
                    (company, str(request_id)),
                )
                row = cur.fetchone()
                if not row:
                    raise legacy.HTTPException(status_code=404, detail={"error": "request_not_found", "message": "We couldn't find that approval request."})
                req = dict(row)
                if req.get("status") != "pending":
                    # Idempotent approve replay if already approved with resulting change.
                    if decision == "approve" and req.get("status") == "approved" and req.get("resulting_change_id"):
                        conn.commit()
                        return {
                            "ok": True,
                            "idempotent": True,
                            "decision": "approve",
                            "request": legacy.json_safe(req),
                            "committed": True,
                        }
                    raise legacy.HTTPException(
                        status_code=409,
                        detail={"error": "request_not_pending", "message": f"This request is already {req.get('status')}."},
                    )
                if str(req.get("designated_approver_user_id")) != actor:
                    raise legacy.HTTPException(
                        status_code=403,
                        detail={"error": "approver_mismatch", "message": "Only the designated approver can decide this request."},
                    )
                if str(req.get("requester_user_id")) == actor:
                    raise legacy.HTTPException(
                        status_code=403,
                        detail={"error": "self_approval_forbidden", "message": "You cannot approve or reject your own status change request."},
                    )

                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s FOR SHARE",
                    (company, actor),
                )
                approver = dict(cur.fetchone() or {})
                approver_permissions = legacy.dashboard_effective_permissions_for_user(approver, cur=cur) if approver else []
                if not legacy._normal_dashboard_operator(approver) or "employees.status.approve" not in approver_permissions:
                    raise legacy.HTTPException(
                        status_code=403,
                        detail={"error": "approver_permission_denied", "message": "The approver is not authorized for employee status changes."},
                    )

                if decision == "reject":
                    reason_text = str(decision_reason or "").strip() or "rejected_by_approver"
                    cur.execute(
                        """
                        UPDATE employee_status_change_requests
                        SET status='rejected', decided_by_user_id=%s, decided_at=now(),
                            decision_reason=%s, updated_at=now()
                        WHERE request_id=%s
                        RETURNING *
                        """,
                        (actor, reason_text, str(request_id)),
                    )
                    updated = dict(cur.fetchone())
                    legacy.write_admin_audit(
                        cur,
                        legacy._permission_operator_context(approver, approver_permissions),
                        "employee_status_approval_rejected",
                        summary="Rejected a pending employment status change. Employee status was not changed.",
                        target_type="employee",
                        target=str(updated.get("employee_key") or ""),
                        details={"request_id": str(request_id), "decision_reason": reason_text},
                    )
                    conn.commit()
                    return {"ok": True, "decision": "reject", "committed": False, "request": legacy.json_safe(updated)}
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # Approve path: commit via existing atomic transition helper (separate connection
    # keeps the proven status-change transaction/idempotency path intact).
    status_body = legacy.DashboardEmployeeStatus(
        status=str(req["requested_status"]),
        reason=str(req["reason"]),
        idempotency_key=str(req["idempotency_key"]),
        expected_status=str(req["expected_status"]),
        expected_updated_at=req["expected_updated_at"],
        approver_user_id=actor,
        approval_reference=str(req["approval_reference"]),
        approval_mode="separate_approval",
    )
    # Use requester context identity for the transition hash requester, but
    # execute with a context that carries company + the original requester id.
    transition_context = {
        **context,
        "actor_user_id": str(req["requester_user_id"]),
        "company_code": company,
    }
    # Approver must remain `actor` via request.approver_user_id (not self).
    result = legacy.transition_employee_employment_status(
        transition_context,
        str(req["employee_key"]),
        status_body,
    )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_employee_status_approval_schema(cur)
            cur.execute(
                """
                UPDATE employee_status_change_requests
                SET status='approved', decided_by_user_id=%s, decided_at=now(),
                    decision_reason=%s, resulting_change_id=%s, updated_at=now()
                WHERE company_code=%s AND request_id=%s AND status='pending'
                RETURNING *
                """,
                (
                    actor,
                    str(decision_reason or "").strip() or "approved_by_designated_approver",
                    result.get("change_id") or None,
                    company,
                    str(request_id),
                ),
            )
            updated = cur.fetchone()
            if not updated:
                # Race: already decided; reload.
                cur.execute(
                    "SELECT * FROM employee_status_change_requests WHERE company_code=%s AND request_id=%s",
                    (company, str(request_id)),
                )
                updated = cur.fetchone()
            conn.commit()
    return {
        "ok": True,
        "decision": "approve",
        "committed": True,
        "request": legacy.json_safe(dict(updated or req)),
        "status_change": result,
    }


def list_pending_for_actor(
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
            ensure_employee_status_approval_schema(cur)
            if employee_key:
                cur.execute(
                    """
                    SELECT *
                    FROM employee_status_change_requests
                    WHERE company_code=%s
                      AND status='pending'
                      AND employee_key=%s
                      AND (designated_approver_user_id=%s OR requester_user_id=%s)
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (company, str(employee_key), actor, actor),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM employee_status_change_requests
                    WHERE company_code=%s
                      AND status='pending'
                      AND (designated_approver_user_id=%s OR requester_user_id=%s)
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (company, actor, actor),
                )
            rows = [dict(r) for r in cur.fetchall() or []]
            conn.commit()
    return legacy.json_safe(rows)
