#!/usr/bin/env python3
"""Reconfirm leave decision spine + prepare consequence templates for mobile i18n."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from typing import Any


def j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def main() -> int:
    import os

    os.chdir("/opt/wathefni/orchestrator")
    import app
    import operator_mobile as om
    import operator_mobile_data as omd

    company = "WATHEFNI"
    subject_key = "WATHEFNI-96550252254"
    aziz = _aziz_context(app, om, company)

    open_items = omd.mobile_leave_list(app, aziz, status="requested", limit=20)
    fouad_id = "033e8a56-480c-4188-ad68-93d73003fc01"
    fouad = next((i for i in (open_items.get("items") or []) if i.get("leave_id") == fouad_id), None)
    if fouad:
        detail = omd.mobile_leave_detail(app, aziz, fouad_id)["request"]
        bal = detail.get("balance") or []
        print("FOUAD_STATUS", detail.get("status"))
        print("FOUAD_CONFLICTS", detail.get("shift_conflict_count"))
        print("FOUAD_BALANCE_ROWS", len(bal))
        if bal:
            row = bal[0]
            print(
                "FOUAD_BALANCE",
                j(
                    {
                        "available": row.get("available"),
                        "current_balance": row.get("current_balance"),
                        "entitlement_days": row.get("entitlement_days"),
                        "observe_only": row.get("observe_only"),
                        "enforced": row.get("enforced"),
                    }
                ),
            )
            assert row.get("available") is not None or row.get("current_balance") is not None
            assert row.get("observe_only") is True or row.get("enforced") is False

    leave_id = str(uuid.uuid4())
    start = date(2026, 8, 22)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  leave_id, company_code, employee_key, leave_type, status,
                  start_date, end_date, reason, requested_at, updated_at
                ) VALUES (
                  %s, %s, %s, 'annual', 'requested',
                  %s, %s, %s, now(), now()
                )
                """,
                (leave_id, company, subject_key, start, start, "HR leave cream EN/AR physical (disposable)"),
            )
            conn.commit()
    print("CREATED", leave_id)

    detail = omd.mobile_leave_detail(app, aziz, leave_id)["request"]
    assert detail["status"] == "requested"
    assert "approve" in detail["allowed_actions"]

    prep = _prepare(app, omd, aziz, leave_id, "approve", None)
    consequence = (prep.get("confirmation") or {}).get("consequence") or ""
    print("PREPARE_CONSEQUENCE", consequence)
    assert re.match(r"^Approve .+\'s leave and notify the employee\.?$", consequence), consequence

    conf = prep["confirmation"]
    done = omd.confirm_mobile_action(
        app,
        aziz,
        confirmation_id=str(conf["confirmation_id"]),
        confirmation_hash=str(conf["confirmation_hash"]),
        expected_target_type="leave_request",
        expected_target_id=leave_id,
        expected_action_types={omd.MOBILE_ACTIONS["approve_leave"]},
    )
    print("CONFIRM_OK", done.get("ok"), done.get("status"))
    after = omd.mobile_leave_detail(app, aziz, leave_id)["request"]
    print("AFTER_STATUS", after.get("status"), "ACTIONS", after.get("allowed_actions"))
    assert after.get("status") == "approved"
    assert after.get("allowed_actions") == []

    print("SPINE_REENFORCE: PASS")
    return 0


def _prepare(app: Any, omd: Any, context: dict[str, Any], leave_id: str, action: str, reason: str | None) -> dict[str, Any]:
    omd._require_mobile_feature_action(app, context, "hr", "leave_approvals", action)
    app.require_entitlement(context, "leave", "leave.decide")
    leave, employee = omd._load_leave(app, context, leave_id)
    employee_name = omd._employee_context(app, employee)["name"]
    consequence = (
        f"Approve {employee_name}'s leave and notify the employee."
        if action == "approve"
        else f"Reject {employee_name}'s leave and notify the employee."
    )
    return omd.prepare_mobile_confirmation(
        app,
        context,
        idempotency_key=f"hr-leave-cream-{leave_id[:8]}-{action}-{uuid.uuid4().hex[:8]}",
        action_type=omd.MOBILE_ACTIONS[f"{action}_leave"],
        target_type="leave_request",
        target_id=str(leave_id),
        expected_status=str(leave.get("status") or ""),
        safe_summary=f"{employee_name} · {leave.get('leave_type') or 'Leave request'}",
        consequence=consequence,
        args={"leave_id": str(leave_id), "decision_note": reason} if reason else {"leave_id": str(leave_id)},
    )


def _aziz_context(app: Any, om: Any, company: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND phone LIKE '%%96599338566%%'
                LIMIT 1
                """,
                (company,),
            )
            user = cur.fetchone()
    if not user:
        raise SystemExit("aziz missing")
    return om.build_operator_mobile_context(app, dict(user), session_id=None)


if __name__ == "__main__":
    raise SystemExit(main())
