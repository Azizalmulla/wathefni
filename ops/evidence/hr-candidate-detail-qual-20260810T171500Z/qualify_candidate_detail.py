#!/usr/bin/env python3
"""HR Candidate detail qualification against production mobile helpers (read + prepare)."""

from __future__ import annotations

import json
import uuid
from typing import Any


def j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def main() -> int:
    import os

    os.chdir("/opt/wathefni/orchestrator")
    import app
    import operator_mobile as om
    import operator_mobile_data as omd
    import recruiting_lifecycle as rl

    company = "WATHEFNI"
    aziz = _aziz_context(app, om, company)
    print("ACTOR", j({k: aziz.get(k) for k in ("company_code", "actor_user_id", "actor_role")}))

    ranking = omd.mobile_candidate_rankings(app, aziz, limit=10)
    items = ranking.get("items") or []
    print("LIST_COUNT", ranking.get("total"), "items", len(items))
    actionable = None
    for item in items[:12]:
        overview = item.get("overview") if isinstance(item.get("overview"), dict) else {}
        candidate = overview.get("candidate") if isinstance(overview.get("candidate"), dict) else {}
        brief = {
            "app_key": item.get("app_key"),
            "name": candidate.get("name"),
            "stage": overview.get("canonical_stage") or overview.get("status") or item.get("status"),
            "actions": item.get("allowed_actions") or [],
            "destination": item.get("destination"),
        }
        print("LIST_ITEM", j(brief))
        if not actionable and brief["actions"]:
            actionable = brief["app_key"]

    pri = omd.build_mobile_priorities(app, aziz, limit=40)
    cand_section = next((s for s in (pri.get("sections") or []) if s.get("type") == "candidate_decisions"), None)
    homeish = [s.get("type") for s in (pri.get("sections") or []) if s.get("type") in {"candidate_decisions", "prehire_priorities"}]
    print(
        "PRIORITY_CANDIDATE",
        j(
            {
                "hiring_sections": homeish,
                "count": len((cand_section or {}).get("items") or []),
                "destinations": [i.get("destination") for i in ((cand_section or {}).get("items") or [])[:8]],
            }
        ),
    )
    if not actionable and cand_section:
        for i in cand_section.get("items") or []:
            dest = str(i.get("destination") or "")
            if "/candidates/" in dest:
                actionable = dest.rsplit("/", 1)[-1]
                break
    if not actionable and items:
        actionable = items[0].get("app_key")
    if not actionable:
        print("NO_CANDIDATE_FOR_DETAIL")
        print("VERDICT_BACKEND_PATH", "PARTIAL")
        return 0

    detail = omd.mobile_candidate_detail(app, aziz, actionable)
    cand = detail.get("candidate") or detail
    overview = cand.get("overview") or {}
    print(
        "DETAIL",
        j(
            {
                "app_key": cand.get("app_key"),
                "name": (overview.get("candidate") or {}).get("name"),
                "stage": overview.get("canonical_stage") or overview.get("status"),
                "status": overview.get("status"),
                "actions": cand.get("allowed_actions"),
                "cv_available": (cand.get("cv") or {}).get("available"),
                "score": (cand.get("ranking") or {}).get("score"),
                "ai_advisory": (cand.get("ranking") or {}).get("ai_advisory"),
                "has_offer": "offer" in cand and cand.get("offer") is not None,
                "has_assessment": "assessment" in cand and cand.get("assessment") is not None,
                "interview": cand.get("interview"),
                "waiting_for_hr": overview.get("waiting_for_hr"),
                "automatic_activity": overview.get("automatic_activity"),
            }
        ),
    )

    actions = [str(a) for a in (cand.get("allowed_actions") or [])]
    action = next((a for a in ("shortlist", "reject", "hire") if a in actions), None)
    if not action:
        print("DETAIL_TERMINAL_NO_ACTIONS")
        # Exercise already_decided prepare gate if terminal
        stage = rl.normalize_stage(str(overview.get("status") or "")) or str(overview.get("status") or "")
        print("STAGE", stage, "TERMINAL", stage in rl.TERMINAL_STAGES)
        print("VERDICT_BACKEND_PATH", "PASS_READ_ONLY")
        return 0

    prep = _prepare(app, omd, rl, aziz, actionable, action)
    conf = prep.get("confirmation") or {}
    print(
        "PREPARE",
        j(
            {
                "status": prep.get("status"),
                "action": conf.get("action"),
                "summary": conf.get("summary"),
                "consequence": conf.get("consequence"),
                "current_state": conf.get("current_state"),
            }
        ),
    )
    assert conf.get("confirmation_id")
    print("PREPARE_ONLY_NO_CONFIRM", True)
    print("SAFE_BACK_PARENT", "/hr/hiring or /hr/candidates (hrCanonicalParent)")
    print("VERDICT_BACKEND_PATH", "PASS")
    return 0


def _prepare(app: Any, omd: Any, rl: Any, context: dict[str, Any], app_key: str, action: str) -> dict[str, Any]:
    feature_for_action = {
        "shortlist": ("candidate_shortlist", "shortlist"),
        "reject": ("candidate_reject", "reject"),
        "hire": ("candidate_hire", "hire"),
    }[action]
    omd._require_mobile_feature_action(app, context, "recruiting", feature_for_action[0], feature_for_action[1])
    app.require_entitlement(context, "pre_hiring", "prehire.read")
    application = app.dashboard_application_or_404(app_key, context["company_code"])
    status = str(application.get("status") or "")
    stage = rl.normalize_stage(status) or status
    if stage in rl.TERMINAL_STAGES or status in {"hired", "rejected"}:
        raise RuntimeError("already_decided")
    permissions = omd._authoritative_permissions(app, context)
    if not rl.authorize_recruiting_action(action, stage, permissions):
        raise RuntimeError("action_forbidden")
    summary = app.prehire_application_summary(application, include_raw=False)
    candidate = summary.get("candidate") if isinstance(summary.get("candidate"), dict) else {}
    position_data = summary.get("position") if isinstance(summary.get("position"), dict) else {}
    name = candidate.get("name") or "Candidate"
    position_title = position_data.get("title") or "this role"
    consequences = {
        "shortlist": f"Move {name} to the shortlist for {position_title}.",
        "reject": f"Reject {name} for {position_title}. This removes them from the active pipeline.",
        "hire": f"Hire {name} for {position_title}. This creates the employee and starts post-hire setup.",
    }
    return omd.prepare_mobile_confirmation(
        app,
        context,
        idempotency_key=f"hr-cand-qual-{action}-{uuid.uuid4().hex[:8]}",
        action_type=omd.MOBILE_ACTIONS[action],
        target_type="application",
        target_id=app_key,
        expected_status=status,
        safe_summary=f"{name} · {position_title}",
        consequence=consequences[action],
        args={"app_key": app_key, "reason": None},
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
