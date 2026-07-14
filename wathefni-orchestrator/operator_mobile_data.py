"""HR-2A mobile-safe operator data adapters.

Thin DTO and confirmation adapters over the existing dashboard business logic.
No authority, tenant, scope, or mutation policy is implemented client-side.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any


MOBILE_CONFIRMATION_TTL = timedelta(minutes=10)
MOBILE_ACTIONS = {
    "approve_leave": "approve_leave_request",
    "reject_leave": "reject_leave_request",
    "shortlist": "shortlist_candidate",
    "reject": "reject_candidate",
    "hire": "hire_candidate",
}

MOBILE_DATA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_operator_mobile_confirmations (
  confirmation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES dashboard_users(user_id) ON DELETE CASCADE,
  session_id uuid REFERENCES dashboard_operator_mobile_sessions(session_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  action_type text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  expected_status text,
  safe_summary text NOT NULL,
  consequence text NOT NULL,
  args jsonb NOT NULL DEFAULT '{}'::jsonb,
  registry_action_hash text,
  registry_confirmation jsonb,
  status text NOT NULL DEFAULT 'preparing',
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  completed_at timestamptz,
  UNIQUE (company_code, user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_mobile_confirmations_lookup
  ON dashboard_operator_mobile_confirmations(company_code, user_id, confirmation_id);
"""


def ensure_operator_mobile_data_schema(app_mod: Any) -> None:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(MOBILE_DATA_SCHEMA_SQL)
        conn.commit()


def _stable_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _actions(feature: dict[str, Any] | None) -> list[str]:
    return [str(item) for item in ((feature or {}).get("actions") or [])]


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _employee_context(app_mod: Any, employee: dict[str, Any] | None) -> dict[str, Any]:
    row = employee if isinstance(employee, dict) else {}
    card = app_mod.posthire_employee_card(row) if row else {}
    return {
        "employee_key": card.get("employee_key"),
        "name": card.get("name") or "Employee",
        "position_title": card.get("position_title") or None,
        "department": card.get("department") or None,
        "employment_status": card.get("employment_status") or None,
    }


def _leave_duration(row: dict[str, Any]) -> float | None:
    explicit = row.get("duration_days") or row.get("days")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            pass
    start = row.get("start_date")
    end = row.get("end_date")
    if start and end:
        try:
            return float((end - start).days + 1)
        except Exception:
            return None
    return None


def leave_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    employee: dict[str, Any] | None = None,
    actions: list[str] | None = None,
    balance: Any = None,
) -> dict[str, Any]:
    status = str(row.get("status") or "")
    allowed = list(actions or []) if status == "requested" else []
    return {
        "leave_id": str(row.get("leave_id") or ""),
        "employee": _employee_context(app_mod, employee or row),
        "leave_type": row.get("leave_type") or row.get("type"),
        "start_date": _iso(row.get("start_date")),
        "end_date": _iso(row.get("end_date")),
        "duration_days": _leave_duration(row),
        "reason": row.get("reason") or row.get("request_reason"),
        "status": status,
        "decision_note": row.get("decision_note"),
        "requested_at": _iso(row.get("requested_at") or row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "shift_conflict_count": int(row.get("shift_conflict_count") or 0),
        "balance": app_mod.json_safe(balance) if balance is not None else None,
        "allowed_actions": allowed,
        "destination": f"/leave/{row.get('leave_id')}",
    }


def _load_leave(app_mod: Any, context: dict[str, Any], leave_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    company = context["company_code"]
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lr.*,
                  (
                    SELECT COUNT(*)
                    FROM shift_assignments s
                    WHERE s.company_code=lr.company_code
                      AND s.employee_key=lr.employee_key
                      AND s.shift_date BETWEEN lr.start_date AND lr.end_date
                      AND s.status='scheduled'
                  ) AS shift_conflict_count
                FROM leave_requests lr
                WHERE lr.company_code=%s AND lr.leave_id=%s
                LIMIT 1
                """,
                (company, str(leave_id)),
            )
            row = cur.fetchone()
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "leave_request_not_found", "message": "This leave request was not found."},
        )
    leave = dict(row)
    employee = app_mod.find_employee_by_key(leave.get("employee_key"), company_code=company)
    if not employee or not app_mod.context_manager_allows_employee(context, employee, company_code=company):
        # Cross-tenant and out-of-scope records are intentionally indistinguishable.
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "leave_request_not_found", "message": "This leave request was not found."},
        )
    return leave, employee


def mobile_leave_list(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str = "requested",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    app_mod.require_entitlement(context, "leave", "leave.read")
    feature = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context).get("leave_approvals")
    result = app_mod.list_leave_requests(
        {
            "company_code": context["company_code"],
            "status": status,
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": max(1, min(int(limit or 30), 100)),
            "offset": max(0, int(offset or 0)),
        },
        company_code=context["company_code"],
    )
    rows = result.get("leave_requests") or []
    employees = {
        str(row.get("employee_key")): app_mod.find_employee_by_key(
            row.get("employee_key"), company_code=context["company_code"]
        )
        for row in rows
        if row.get("employee_key")
    }
    actions = _actions(feature)
    return {
        "ok": True,
        "items": [
            leave_mobile_item(
                app_mod,
                row,
                employee=employees.get(str(row.get("employee_key"))),
                actions=actions,
            )
            for row in rows
        ],
        "total": int(result.get("total_count") or 0),
        "offset": int(result.get("offset") or 0),
        "limit": int(result.get("limit") or limit),
        "has_more": bool(result.get("has_more")),
        "status": status,
    }


def mobile_leave_detail(app_mod: Any, context: dict[str, Any], leave_id: str) -> dict[str, Any]:
    app_mod.require_entitlement(context, "leave", "leave.read")
    leave, employee = _load_leave(app_mod, context, leave_id)
    feature = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context).get("leave_approvals")
    balance = None
    if app_mod.leave_balances_enabled():
        balance = app_mod.leave_balances_for_employee(context["company_code"], str(leave.get("employee_key")))
    return {
        "ok": True,
        "request": leave_mobile_item(
            app_mod,
            leave,
            employee=employee,
            actions=_actions(feature),
            balance=balance,
        ),
    }


def _candidate_allowed_actions(context: dict[str, Any], status: str) -> list[str]:
    permissions = {str(value) for value in context.get("permissions") or []}
    if status in {"hired", "rejected"}:
        return []
    actions: list[str] = []
    if "candidate.manage" in permissions and status != "shortlisted":
        actions.append("shortlist")
    if "candidate.decide" in permissions:
        actions.extend(["reject", "hire"])
    return actions


def candidate_mobile_item(app_mod: Any, item: dict[str, Any]) -> dict[str, Any]:
    application = item.get("application") if isinstance(item.get("application"), dict) else {}
    candidate = application.get("candidate") if isinstance(application.get("candidate"), dict) else {}
    position = application.get("position") if isinstance(application.get("position"), dict) else {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    evaluation = item.get("gpt_evaluation") if isinstance(item.get("gpt_evaluation"), dict) else {}
    concerns = (
        evaluation.get("concerns")
        or evaluation.get("gaps")
        or evaluation.get("missing_evidence")
        or []
    )
    status = str(item.get("status") or application.get("status") or "")
    return {
        "app_key": str(item.get("app_key") or application.get("app_key") or ""),
        "candidate": {
            "name": item.get("name") or candidate.get("name") or "Candidate",
            "email": candidate.get("email"),
        },
        "position": {
            "code": item.get("position_code") or position.get("code"),
            "title": item.get("position_title") or position.get("title"),
        },
        "status": status,
        "score": item.get("score"),
        "confidence": item.get("confidence"),
        "evidence": app_mod.json_safe(evidence),
        "reasons": app_mod.json_safe(item.get("reasons") or evidence[:4]),
        "concerns": app_mod.json_safe(concerns),
        "missing_evidence": app_mod.json_safe(evaluation.get("missing_evidence") or []),
        "assessment": app_mod.json_safe(item.get("assessment_signal") or application.get("assessment")),
        "interview": app_mod.json_safe(item.get("interview_signal") or application.get("interview")),
        "cv": app_mod.json_safe(application.get("cv") or {}),
        "ai_advisory": True,
        "allowed_actions": _candidate_allowed_actions(
            {"permissions": item.get("_permissions") or []},
            status,
        ),
        "destination": f"/candidates/{item.get('app_key') or application.get('app_key')}",
    }


def mobile_candidate_rankings(
    app_mod: Any,
    context: dict[str, Any],
    *,
    query: str = "",
    position: str = "",
    status: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
    result = app_mod.rank_candidates(
        {
            "query": query,
            "position": position,
            "status": status,
            "top_n": max(1, min(int(limit or 20), 50)),
        },
        company_code=context["company_code"],
    )
    items = []
    for candidate in result.get("candidates") or []:
        items.append(candidate_mobile_item(app_mod, {**candidate, "_permissions": context.get("permissions") or []}))
    return {
        "ok": True,
        "items": items,
        "total": int(result.get("total_matching") or 0),
        "filters": app_mod.json_safe(result.get("filters") or {}),
        "ai_advisory": True,
    }


def mobile_candidate_detail(app_mod: Any, context: dict[str, Any], app_key: str) -> dict[str, Any]:
    app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
    application = app_mod.dashboard_application_or_404(app_key, context["company_code"])
    summary = app_mod.prehire_application_summary(
        application,
        include_raw=False,
        include_assessment=app_mod.company_has_module(context["company_code"], "assessments"),
    )
    evaluation = app_mod.latest_application_rank_evaluation(context["company_code"], app_key) or {}
    evidence = evaluation.get("evidence") or evaluation.get("reasons") or []
    concerns = evaluation.get("concerns") or evaluation.get("gaps") or evaluation.get("gaps_or_risks") or []
    cv = app_mod.dashboard_candidate_cv_metadata(application)
    status = str(summary.get("status") or application.get("status") or "")
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, feedback_status, notes, ai_summary, scheduled_start, updated_at
                FROM candidate_interviews
                WHERE company_code=%s AND app_key=%s
                ORDER BY scheduled_start DESC NULLS LAST, updated_at DESC
                LIMIT 1
                """,
                (context["company_code"], app_key),
            )
            interview = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT status, last_error, message_kind, sent_at, failed_at, updated_at
                FROM outbound_delivery_events
                WHERE account_id=%s AND subject_key=%s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (context["company_code"], app_key),
            )
            communications = [dict(row) for row in cur.fetchall()]
    return {
        "ok": True,
        "candidate": {
            "app_key": app_key,
            "overview": app_mod.json_safe(summary),
            "ranking": {
                "score": evaluation.get("score"),
                "confidence": evaluation.get("confidence"),
                "reasons": app_mod.json_safe(evaluation.get("reasons") or evidence[:4]),
                "evidence": app_mod.json_safe(evidence),
                "concerns": app_mod.json_safe(concerns),
                "missing_evidence": app_mod.json_safe(evaluation.get("missing_evidence") or []),
                "ai_advisory": True,
            },
            "cv": {
                "available": bool(cv),
                "filename": (cv or {}).get("original_filename"),
                "mime_type": (cv or {}).get("mime_type"),
                "size_bytes": (cv or {}).get("size_bytes"),
                "preview_path": f"/dashboard/mobile/candidates/{app_key}/cv/preview" if cv else None,
                "download_path": f"/dashboard/mobile/candidates/{app_key}/cv" if cv else None,
            },
            "interview": app_mod.json_safe(interview) if interview else None,
            "communication_status": [
                {
                    "status": row.get("status"),
                    "display_status": app_mod.dashboard_delivery_status(row),
                    "message_kind": row.get("message_kind"),
                    "sent_at": _iso(row.get("sent_at")),
                    "failed_at": _iso(row.get("failed_at")),
                    "updated_at": _iso(row.get("updated_at")),
                }
                for row in communications
            ],
            "allowed_actions": _candidate_allowed_actions(context, status),
        },
    }


def _confirmation_public(row: dict[str, Any], *, replay: bool = False) -> dict[str, Any]:
    registry = row.get("registry_confirmation") if isinstance(row.get("registry_confirmation"), dict) else {}
    return {
        "confirmation_id": str(row.get("confirmation_id") or ""),
        "confirmation_hash": row.get("request_hash"),
        "action": row.get("action_type"),
        "target": {"type": row.get("target_type"), "id": row.get("target_id")},
        "summary": row.get("safe_summary"),
        "consequence": row.get("consequence"),
        "current_state": row.get("expected_status"),
        "expires_at": _iso(row.get("expires_at")),
        "status": row.get("status"),
        "backend_confirmation": registry,
        "idempotent_replay": replay,
    }


def _confirmation_lookup(
    app_mod: Any,
    context: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    confirmation_id: str | None = None,
    for_update: bool = False,
) -> dict[str, Any] | None:
    where = "confirmation_id=%s" if confirmation_id else "idempotency_key=%s"
    value = confirmation_id or idempotency_key
    lock = " FOR UPDATE" if for_update else ""
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM dashboard_operator_mobile_confirmations
                WHERE company_code=%s AND user_id=%s AND {where}
                LIMIT 1{lock}
                """,
                (context["company_code"], context["actor_user_id"], value),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _execute_registry_action(
    app_mod: Any,
    context: dict[str, Any],
    action_type: str,
    args: dict[str, Any],
    target_type: str,
) -> dict[str, Any]:
    if target_type == "leave_request":
        result = app_mod.run_posthire_dashboard_action(context, action_type, args)
    else:
        conversation_id = app_mod.posthire_dashboard_conversation_id(context)
        scope = app_mod.posthire_dashboard_scope(context, conversation_id)
        result = app_mod.run_dashboard_registry_action(
            context,
            action_type,
            args,
            allowed_modules=app_mod.PREHIRE_DASHBOARD_REGISTRY_MODULES,
            conversation_id=conversation_id,
            scope=scope,
            audit_target_type="application",
        )
    return result


def prepare_mobile_confirmation(
    app_mod: Any,
    context: dict[str, Any],
    *,
    idempotency_key: str,
    action_type: str,
    target_type: str,
    target_id: str,
    expected_status: str,
    safe_summary: str,
    consequence: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    key = str(idempotency_key or "").strip()
    if len(key) < 12 or len(key) > 160:
        raise app_mod.HTTPException(
            status_code=422,
            detail={"error": "invalid_idempotency_key", "message": "A valid idempotency key is required."},
        )
    request_hash = _stable_hash(
        {
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "expected_status": expected_status,
            "args": args,
        }
    )
    existing = _confirmation_lookup(app_mod, context, idempotency_key=key)
    if existing:
        if existing.get("request_hash") != request_hash:
            raise app_mod.HTTPException(
                status_code=409,
                detail={"error": "idempotency_conflict", "message": "That action key was already used for another decision."},
            )
        return {
            "ok": str(existing.get("status")) == "completed",
            "status": existing.get("status"),
            "confirmation": _confirmation_public(existing, replay=True),
            "result": app_mod.json_safe(existing.get("result")),
        }

    expires_at = app_mod.now_utc() + MOBILE_CONFIRMATION_TTL
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_operator_mobile_confirmations
                  (user_id, session_id, company_code, idempotency_key, request_hash,
                   action_type, target_type, target_id, expected_status,
                   safe_summary, consequence, args, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    context["actor_user_id"],
                    context.get("mobile_session_id") or None,
                    context["company_code"],
                    key,
                    request_hash,
                    action_type,
                    target_type,
                    target_id,
                    expected_status,
                    safe_summary,
                    consequence,
                    app_mod.Json(app_mod.json_safe(args)),
                    expires_at,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()

    # Preflight through the authoritative registry. The mutation cannot execute
    # here because every exposed mobile action is registry-confirmed.
    preflight = _execute_registry_action(app_mod, context, action_type, args, target_type)
    if preflight.get("status") != "needs_confirmation":
        # Fail closed if registry policy unexpectedly stops requiring confirmation.
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='failed', result=%s, updated_at=now()
                    WHERE confirmation_id=%s
                    """,
                    (app_mod.Json(app_mod.json_safe(preflight)), row["confirmation_id"]),
                )
            conn.commit()
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "confirmation_unavailable", "message": "This decision could not be prepared safely."},
        )

    registry_confirmation = preflight.get("confirmation") or {}
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status='pending', registry_action_hash=%s,
                    registry_confirmation=%s, updated_at=now()
                WHERE confirmation_id=%s
                RETURNING *
                """,
                (
                    registry_confirmation.get("action_hash"),
                    app_mod.Json(app_mod.json_safe(registry_confirmation)),
                    row["confirmation_id"],
                ),
            )
            prepared = dict(cur.fetchone())
        conn.commit()
    return {
        "ok": False,
        "status": "needs_confirmation",
        "confirmation": _confirmation_public(prepared),
        "result": None,
    }


def _current_target_status(app_mod: Any, context: dict[str, Any], row: dict[str, Any]) -> str | None:
    if row.get("target_type") == "leave_request":
        leave, _ = _load_leave(app_mod, context, str(row.get("target_id") or ""))
        return str(leave.get("status") or "")
    application = app_mod.dashboard_application_or_404(str(row.get("target_id") or ""), context["company_code"])
    return str(application.get("status") or "")


def confirm_mobile_action(
    app_mod: Any,
    context: dict[str, Any],
    *,
    confirmation_id: str,
    confirmation_hash: str,
) -> dict[str, Any]:
    row = _confirmation_lookup(app_mod, context, confirmation_id=confirmation_id)
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "confirmation_not_found", "message": "This confirmation is no longer available."},
        )
    if not hmac.compare_digest(str(row.get("request_hash") or ""), str(confirmation_hash or "")):
        raise app_mod.HTTPException(
            status_code=403,
            detail={"error": "confirmation_mismatch", "message": "This confirmation does not match the decision."},
        )
    status = str(row.get("status") or "")
    if status in {"completed", "failed"}:
        return {
            "ok": status == "completed",
            "status": status,
            "confirmation": _confirmation_public(row, replay=True),
            "result": app_mod.json_safe(row.get("result")),
        }
    if status == "processing":
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "action_in_progress", "message": "This decision is already being processed."},
        )
    if row.get("expires_at") and row["expires_at"] <= app_mod.now_utc():
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "confirmation_expired", "message": "Review the current state and confirm again."},
        )
    current_status = _current_target_status(app_mod, context, row)
    if current_status != str(row.get("expected_status") or ""):
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='failed', result=%s, updated_at=now()
                    WHERE confirmation_id=%s
                    """,
                    (
                        app_mod.Json(
                            {
                                "error": "stale_decision",
                                "expected_status": row.get("expected_status"),
                                "current_status": current_status,
                            }
                        ),
                        row["confirmation_id"],
                    ),
                )
            conn.commit()
        raise app_mod.HTTPException(
            status_code=409,
            detail={
                "error": "stale_decision",
                "message": "This item changed since you reviewed it.",
                "current_status": current_status,
            },
        )

    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status='processing', updated_at=now()
                WHERE confirmation_id=%s AND status='pending'
                RETURNING confirmation_id
                """,
                (row["confirmation_id"],),
            )
            claimed = cur.fetchone()
        conn.commit()
    if not claimed:
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "action_in_progress", "message": "This decision is already being processed."},
        )

    try:
        result = _execute_registry_action(
            app_mod,
            context,
            str(row.get("action_type") or ""),
            dict(row.get("args") or {}),
            str(row.get("target_type") or ""),
        )
        # The prepare call created the registry pending action, so this should be
        # terminal. One extra invoke is allowed only after explicit mobile confirm
        # to tolerate a restarted pending-action store.
        if result.get("status") == "needs_confirmation":
            result = _execute_registry_action(
                app_mod,
                context,
                str(row.get("action_type") or ""),
                dict(row.get("args") or {}),
                str(row.get("target_type") or ""),
            )
        terminal = "completed" if result.get("ok") or result.get("status") == "completed" else "failed"
    except Exception:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='pending', updated_at=now()
                    WHERE confirmation_id=%s AND status='processing'
                    """,
                    (row["confirmation_id"],),
                )
            conn.commit()
        raise

    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status=%s, result=%s, completed_at=now(), updated_at=now()
                WHERE confirmation_id=%s
                RETURNING *
                """,
                (terminal, app_mod.Json(app_mod.json_safe(result)), row["confirmation_id"]),
            )
            completed = dict(cur.fetchone())
        conn.commit()
    return {
        "ok": terminal == "completed",
        "status": terminal,
        "confirmation": _confirmation_public(completed),
        "result": app_mod.json_safe(result),
    }


def build_mobile_priorities(app_mod: Any, context: dict[str, Any], *, limit: int = 12) -> dict[str, Any]:
    hr_features = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context)
    recruiting_features = app_mod._operator_mobile.build_recruiting_workspace_capabilities(app_mod, context)
    sections: list[dict[str, Any]] = []
    max_items = max(1, min(int(limit or 12), 30))

    if (hr_features.get("leave_approvals") or {}).get("enabled"):
        leave = mobile_leave_list(app_mod, context, status="requested", limit=max_items)
        sections.append(
            {
                "type": "leave_approvals",
                "title": "Leave approvals",
                "total": leave["total"],
                "items": [
                    {
                        "type": "leave_approval",
                        "target_id": item["leave_id"],
                        "summary": f"{item['employee']['name']} · {item.get('leave_type') or 'Leave request'}",
                        "status": item["status"],
                        "timestamp": item.get("requested_at") or item.get("updated_at"),
                        "due_context": {
                            "start_date": item.get("start_date"),
                            "end_date": item.get("end_date"),
                        },
                        "permitted_actions": item["allowed_actions"],
                        "destination": item["destination"],
                        "severity": "high" if item.get("shift_conflict_count") else None,
                    }
                    for item in leave["items"]
                ],
            }
        )

    if (hr_features.get("onboarding_review") or {}).get("enabled"):
        onboarding = app_mod.dashboard_posthire_onboarding(
            offset=0, limit=max_items, search="", context=context
        )
        sections.append(
            {
                "type": "onboarding_reviews",
                "title": "Onboarding reviews",
                "total": int(onboarding.get("total_count") or 0),
                "items": [
                    {
                        "type": "onboarding_review",
                        "target_id": item.get("employee_key"),
                        "summary": item.get("name") or "Employee onboarding",
                        "status": item.get("onboarding_status"),
                        "timestamp": _iso(item.get("updated_at")),
                        "due_context": None,
                        "permitted_actions": _actions(hr_features.get("onboarding_review")),
                        "destination": f"/onboarding/{item.get('employee_key')}",
                        "severity": None,
                    }
                    for item in onboarding.get("in_progress") or []
                ],
            }
        )

    if (hr_features.get("attendance_exceptions") or {}).get("enabled"):
        attendance = app_mod.dashboard_posthire_attendance(
            start_date=None,
            end_date=None,
            status="late",
            offset=0,
            limit=max_items,
            context=context,
        )
        sections.append(
            {
                "type": "attendance_exceptions",
                "title": "Attendance exceptions",
                "total": int(attendance.get("total_count") or attendance.get("count") or 0),
                "items": [
                    {
                        "type": "attendance_exception",
                        "target_id": item.get("attendance_id") or item.get("employee_key"),
                        "summary": item.get("employee_name") or "Attendance exception",
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("updated_at") or item.get("attendance_date")),
                        "due_context": {"date": _iso(item.get("attendance_date"))},
                        "permitted_actions": _actions(hr_features.get("attendance_exceptions")),
                        "destination": "/attendance",
                        "severity": None,
                    }
                    for item in attendance.get("attendance") or []
                ],
            }
        )

    if (hr_features.get("hr_tasks") or {}).get("enabled"):
        tasks = app_mod.dashboard_hr_tasks(status="open", limit=max_items, offset=0, context=context)
        sections.append(
            {
                "type": "hr_tasks",
                "title": "HR tasks",
                "total": int(tasks.get("total") or 0),
                "items": [
                    {
                        "type": str(item.get("task_type") or item.get("source") or "hr_task"),
                        "target_id": str(item.get("task_id") or ""),
                        "summary": item.get("summary") or item.get("title") or "HR task",
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("created_at") or item.get("updated_at")),
                        "due_context": app_mod.json_safe(item.get("due_context")),
                        "permitted_actions": _actions(hr_features.get("hr_tasks")),
                        "destination": f"/tasks/{item.get('task_id')}",
                        "severity": item.get("severity") or item.get("priority"),
                    }
                    for item in tasks.get("tasks") or []
                ],
            }
        )

    if (hr_features.get("delivery_alerts") or {}).get("enabled"):
        delivery = app_mod.dashboard_outbound_needs_follow_up(
            limit=max_items, offset=0, context=context
        )
        sections.append(
            {
                "type": "delivery_alerts",
                "title": "Delivery alerts",
                "total": int(delivery.get("total") or 0),
                "items": [
                    {
                        "type": "delivery_alert",
                        "target_id": item.get("message_id"),
                        "summary": item.get("reason"),
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("last_attempt_at")),
                        "due_context": {"suggested_action": item.get("suggested_action")},
                        "permitted_actions": _actions(hr_features.get("delivery_alerts")),
                        "destination": "/delivery-alerts",
                        "severity": item.get("criticality"),
                    }
                    for item in delivery.get("messages") or []
                    if item.get("kind") == "issue"
                ],
            }
        )

    if (recruiting_features.get("candidate_rankings") or {}).get("enabled"):
        candidates = mobile_candidate_rankings(app_mod, context, limit=max_items)
        decision_items = [
            item for item in candidates["items"] if item.get("allowed_actions")
        ]
        sections.append(
            {
                "type": "candidate_decisions",
                "title": "Candidate decisions",
                "total": len(decision_items),
                "items": [
                    {
                        "type": "candidate_decision",
                        "target_id": item["app_key"],
                        "summary": f"{item['candidate']['name']} · {item['position'].get('title') or 'Candidate'}",
                        "status": item.get("status"),
                        "timestamp": None,
                        "due_context": None,
                        "permitted_actions": item.get("allowed_actions") or [],
                        "destination": item["destination"],
                        "severity": None,
                    }
                    for item in decision_items
                ],
            }
        )

    return {
        "ok": True,
        "generated_at": app_mod.now_utc().isoformat(),
        "ranking_policy": "separated_authoritative_sections_no_invented_urgency",
        "sections": sections,
    }


def register_operator_mobile_data_routes(app_mod: Any) -> None:
    """Register HR-2A routes after HR-1 mobile auth routes."""
    from fastapi import Depends, Query
    from pydantic import BaseModel

    dependency = getattr(
        app_mod._operator_mobile.register_operator_mobile_routes,
        "operator_mobile_context",
        None,
    )
    if dependency is None:
        raise RuntimeError("operator mobile auth routes must register before HR-2A data routes")

    class LeaveDecisionRequest(BaseModel):
        action: str
        reason: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class CandidateActionRequest(BaseModel):
        action: str
        reason: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    # ``from __future__ import annotations`` makes FastAPI resolve these names
    # through module globals rather than this registration function's locals.
    globals()["LeaveDecisionRequest"] = LeaveDecisionRequest
    globals()["CandidateActionRequest"] = CandidateActionRequest

    @app_mod.app.get("/dashboard/mobile/priorities")
    def mobile_priorities(
        limit: int = Query(default=12, ge=1, le=30),
        context: dict[str, Any] = Depends(dependency),
    ):
        return build_mobile_priorities(app_mod, context, limit=limit)

    @app_mod.app.get("/dashboard/mobile/leave")
    def mobile_leave(
        status: str = Query(default="requested"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        normalized = str(status or "").strip().lower()
        if normalized not in {"requested", "approved", "rejected", "cancelled"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "invalid_leave_status", "message": "That leave status is not valid."},
            )
        return mobile_leave_list(
            app_mod, context, status=normalized, offset=offset, limit=limit
        )

    @app_mod.app.get("/dashboard/mobile/leave/{leave_id}")
    def mobile_leave_request(
        leave_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_leave_detail(app_mod, context, leave_id)

    @app_mod.app.post("/dashboard/mobile/leave/{leave_id}/decision")
    def mobile_leave_decision(
        leave_id: str,
        request: LeaveDecisionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "leave", "leave.decide")
        leave, employee = _load_leave(app_mod, context, leave_id)
        action = str(request.action or "").strip().lower()
        if action not in {"approve", "reject"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_leave_action", "message": "That leave decision is not supported."},
            )
        if action == "reject" and not str(request.reason or "").strip():
            raise app_mod.HTTPException(
                status_code=422,
                detail={"error": "rejection_reason_required", "message": "Add a reason before rejecting this request."},
            )
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
            )
        employee_name = _employee_context(app_mod, employee)["name"]
        consequence = (
            f"Approve {employee_name}'s leave and notify the employee."
            if action == "approve"
            else f"Reject {employee_name}'s leave and notify the employee."
        )
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS[f"{action}_leave"],
            target_type="leave_request",
            target_id=str(leave_id),
            expected_status=str(leave.get("status") or ""),
            safe_summary=f"{employee_name} · {leave.get('leave_type') or 'Leave request'}",
            consequence=consequence,
            args={
                "leave_id": str(leave_id),
                "decision_note": str(request.reason or "").strip() or None,
            },
        )

    @app_mod.app.get("/dashboard/mobile/candidates")
    def mobile_candidates(
        q: str = Query(default=""),
        position: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=50),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_candidate_rankings(
            app_mod,
            context,
            query=q,
            position=position,
            status=status,
            limit=limit,
        )

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}")
    def mobile_candidate(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_candidate_detail(app_mod, context, app_key)

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}/cv")
    def mobile_candidate_cv(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv(app_key, context=context)

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}/cv/preview")
    def mobile_candidate_cv_preview(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv_preview(app_key, context=context)

    @app_mod.app.post("/dashboard/mobile/candidates/{app_key}/decision")
    def mobile_candidate_decision(
        app_key: str,
        request: CandidateActionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        action = str(request.action or "").strip().lower()
        if action not in {"shortlist", "reject", "hire"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_candidate_action", "message": "That candidate action is not supported."},
            )
        permission = "candidate.manage" if action == "shortlist" else "candidate.decide"
        if not app_mod.dashboard_context_has_permission(context, permission):
            raise app_mod.HTTPException(
                status_code=403,
                detail={"error": "action_forbidden", "message": "You do not have access to do that."},
            )
        application = app_mod.dashboard_application_or_404(app_key, context["company_code"])
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
            )
        status = str(application.get("status") or "")
        if status in {"hired", "rejected"}:
            raise app_mod.HTTPException(
                status_code=409,
                detail={"error": "already_decided", "message": "This candidate already has a final decision."},
            )
        summary = app_mod.prehire_application_summary(application, include_raw=False)
        candidate = summary.get("candidate") if isinstance(summary.get("candidate"), dict) else {}
        position_data = summary.get("position") if isinstance(summary.get("position"), dict) else {}
        name = candidate.get("name") or "Candidate"
        position_title = position_data.get("title") or "this role"
        consequences = {
            "shortlist": f"Move {name} to the shortlist for {position_title}.",
            "reject": f"Reject {name} for {position_title}. This removes them from the active pipeline.",
            "hire": f"Hire {name} for {position_title}. This creates the employee and starts post-hire setup.",
        }
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS[action],
            target_type="application",
            target_id=app_key,
            expected_status=status,
            safe_summary=f"{name} · {position_title}",
            consequence=consequences[action],
            args={"app_key": app_key, "reason": str(request.reason or "").strip() or None},
        )

    # Additional V1 read adapters. They call the existing route functions with
    # the mobile context so entitlements and manager scope remain authoritative.
    @app_mod.app.get("/dashboard/mobile/onboarding")
    def mobile_onboarding(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        search: str = Query(default=""),
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_posthire_onboarding(
            offset=offset, limit=limit, search=search, context=context
        )

    @app_mod.app.get("/dashboard/mobile/onboarding/{employee_key}")
    def mobile_onboarding_detail(
        employee_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_posthire_onboarding_detail(employee_key, context=context)

    @app_mod.app.get("/dashboard/mobile/attendance")
    def mobile_attendance(
        start_date: str | None = Query(default=None),
        end_date: str | None = Query(default=None),
        status: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_posthire_attendance(
            start_date=start_date,
            end_date=end_date,
            status=status,
            offset=offset,
            limit=limit,
            context=context,
        )

    @app_mod.app.get("/dashboard/mobile/shifts")
    def mobile_shifts(
        week: int = Query(default=0, ge=-26, le=26),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_posthire_shifts(
            week=week, offset=offset, limit=limit, context=context
        )

    @app_mod.app.get("/dashboard/mobile/employees")
    def mobile_employees(
        search: str = Query(default=""),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_posthire_employees(
            offset=offset, limit=limit, search=search, context=context
        )

    @app_mod.app.get("/dashboard/mobile/employees/{employee_key}")
    def mobile_employee(
        employee_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_workspace_permission(context, "employees.read")
        profile = app_mod.dashboard_employee_profile(context, employee_key)
        return {
            "ok": True,
            "employee": profile.get("employee"),
            "sections": profile.get("sections"),
            "next_actions": profile.get("next_actions"),
        }

    @app_mod.app.get("/dashboard/mobile/delivery-alerts")
    def mobile_delivery_alerts(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        return app_mod.dashboard_outbound_needs_follow_up(
            limit=limit, offset=offset, context=context
        )
