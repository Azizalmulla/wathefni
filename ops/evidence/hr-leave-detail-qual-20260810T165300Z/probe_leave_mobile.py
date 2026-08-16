#!/usr/bin/env python3
"""Canary probe: HR mobile leave detail payload + prepare semantics (no confirm by default)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def main() -> int:
    os.chdir("/opt/wathefni/orchestrator")
    import app
    import operator_mobile_data as omd

    company = "WATHEFNI"
    confirm = "--confirm" in sys.argv
    action = "approve"
    if "--reject" in sys.argv:
        action = "reject"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT leave_id::text AS leave_id, employee_key, leave_type, status,
                       start_date::text AS start_date, end_date::text AS end_date,
                       left(coalesce(reason, ''), 120) AS reason,
                       left(coalesce(decision_note, ''), 80) AS decision_note,
                       requested_at::text AS requested_at,
                       updated_at::text AS updated_at
                FROM leave_requests
                WHERE company_code=%s
                ORDER BY CASE WHEN status='requested' THEN 0 ELSE 1 END,
                         updated_at DESC NULLS LAST
                LIMIT 20
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]

    print("BALANCES_ENABLED", app.leave_balances_enabled())
    print("LEAVE_ROWS", len(rows))
    for row in rows:
        print("ROW", json.dumps(row, ensure_ascii=False))

    requested = [r for r in rows if r.get("status") == "requested"]
    decided = [r for r in rows if r.get("status") != "requested"]
    target = requested[0] if requested else (decided[0] if decided else None)
    if not target:
        print("NO_LEAVE_FOUND")
        return 1

    # Build Aziz-like owner context from live operator if possible.
    context = _aziz_context(app, company)
    print("ACTOR", json.dumps({k: context.get(k) for k in ("company_code", "actor_user_id", "actor_role", "hr_phone")}, ensure_ascii=False))

    detail = omd.mobile_leave_detail(app, context, str(target["leave_id"]))
    req = detail.get("request") or {}
    print("DETAIL_KEYS", sorted(req.keys()))
    print(
        "DETAIL_SUMMARY",
        json.dumps(
            {
                "leave_id": req.get("leave_id"),
                "status": req.get("status"),
                "leave_type": req.get("leave_type"),
                "start_date": req.get("start_date"),
                "end_date": req.get("end_date"),
                "duration_days": req.get("duration_days"),
                "reason": req.get("reason"),
                "shift_conflict_count": req.get("shift_conflict_count"),
                "allowed_actions": req.get("allowed_actions"),
                "employee": req.get("employee"),
                "balance_type": type(req.get("balance")).__name__,
                "balance_len": len(req.get("balance") or []) if isinstance(req.get("balance"), list) else None,
                "balance_sample": (req.get("balance") or [None])[0] if isinstance(req.get("balance"), list) and req.get("balance") else req.get("balance"),
            },
            ensure_ascii=False,
            default=str,
        ),
    )

    # Already-decided: actions must be empty
    if req.get("status") != "requested":
        print("ALREADY_DECIDED_ACTIONS", req.get("allowed_actions"))
        print("PREPARE_SKIPPED_already_decided")
        return 0

    # Prepare only by default
    from pydantic import BaseModel

    class LeaveDecisionRequest(BaseModel):
        action: str
        reason: str | None = None
        idempotency_key: str | None = None
        confirm: bool = False
        confirmation_id: str | None = None
        confirmation_hash: str | None = None

    reason = "HR mobile leave qualification reject reason" if action == "reject" else None
    idem = f"hr-leave-qual-{target['leave_id'][:8]}-{action}"
    # Call the same helpers the route uses
    feature_action = "approve" if action == "approve" else "reject"
    omd._require_mobile_feature_action(app, context, "hr", "leave_approvals", feature_action)
    app.require_entitlement(context, "leave", "leave.decide")
    leave, employee = omd._load_leave(app, context, str(target["leave_id"]))
    employee_name = omd._employee_context(app, employee)["name"]
    consequence = (
        f"Approve {employee_name}'s leave and notify the employee."
        if action == "approve"
        else f"Reject {employee_name}'s leave and notify the employee."
    )
    prepared = omd.prepare_mobile_confirmation(
        app,
        context,
        idempotency_key=idem,
        action_type=omd.MOBILE_ACTIONS[f"{action}_leave"],
        target_type="leave_request",
        target_id=str(target["leave_id"]),
        expected_status=str(leave.get("status") or ""),
        safe_summary=f"{employee_name} · {leave.get('leave_type') or 'Leave request'}",
        consequence=consequence,
        args={
            "leave_id": str(target["leave_id"]),
            "decision_note": reason,
        },
    )
    print("PREPARE", json.dumps(prepared, ensure_ascii=False, default=str)[:2000])

    if not confirm:
        print("CONFIRM_SKIPPED (pass --confirm to execute)")
        return 0

    confirmed = omd.confirm_mobile_action(
        app,
        context,
        confirmation_id=str(prepared["confirmation"]["confirmation_id"]),
        confirmation_hash=str(prepared["confirmation"]["confirmation_hash"]),
        expected_target_type="leave_request",
        expected_target_id=str(target["leave_id"]),
        expected_action_types={omd.MOBILE_ACTIONS[f"{action}_leave"]},
    )
    print("CONFIRM", json.dumps(confirmed, ensure_ascii=False, default=str)[:2000])

    # Priorities should drop this leave
    pri = omd.build_mobile_priorities(app, context, limit=20)
    leave_section = next((s for s in (pri.get("sections") or []) if s.get("type") == "leave_approvals"), None)
    ids = [i.get("id") or i.get("destination") for i in ((leave_section or {}).get("items") or [])]
    print("PRIORITIES_LEAVE_IDS", ids)
    print("STILL_IN_PRIORITIES", any(str(target["leave_id"]) in str(x) for x in ids))
    return 0


def _aziz_context(app: Any, company: str) -> dict[str, Any]:
    """Prefer Aziz operator via the same builder as live mobile auth."""
    import operator_mobile as om

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM dashboard_users
                WHERE company_code=%s
                  AND phone LIKE '%%96599338566%%'
                LIMIT 1
                """,
                (company,),
            )
            user = cur.fetchone()
            if not user:
                cur.execute(
                    """
                    SELECT *
                    FROM dashboard_users
                    WHERE company_code=%s AND role IN ('owner','hr_manager','hr') AND status='active'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (company,),
                )
                user = cur.fetchone()
    if not user:
        raise SystemExit("no dashboard user for context")
    row = dict(user)
    safe = {k: ("***" if any(x in k.lower() for x in ("pass", "hash", "secret", "token")) else v) for k, v in row.items()}
    print(
        "USER",
        json.dumps(
            {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in safe.items() if k in {"user_id", "phone", "email", "role", "name", "status", "company_code"}},
            ensure_ascii=False,
            default=str,
        ),
    )
    return om.build_operator_mobile_context(app, row, session_id="hr-leave-qual-probe")



if __name__ == "__main__":
    raise SystemExit(main())
