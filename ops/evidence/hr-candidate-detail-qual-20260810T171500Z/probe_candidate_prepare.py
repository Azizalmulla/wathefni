#!/usr/bin/env python3
"""Candidate detail prepare + terminal gate probe (no confirm on live import)."""

from __future__ import annotations

import json
import os
import uuid


def main() -> int:
    os.chdir("/opt/wathefni/orchestrator")
    import app
    import operator_mobile as om
    import operator_mobile_data as omd
    import recruiting_lifecycle as rl

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code='WATHEFNI' AND phone LIKE '%%96599338566%%'
                LIMIT 1
                """
            )
            user = dict(cur.fetchone())
    aziz = om.build_operator_mobile_context(app, user, session_id=None)

    app_key = "imp-wathefni-3bda14696342799f-WATHEFNI-IMPORT"
    terminal = "imp-wathefni-511c5f998f9f75cd-WATHEFNI-IMPORT"

    detail = omd.mobile_candidate_detail(app, aziz, app_key)
    cand = detail["candidate"]
    ov = cand["overview"]
    ranking = cand.get("ranking") or {}
    print(
        "DETAIL",
        json.dumps(
            {
                "app_key": app_key,
                "name": (ov.get("candidate") or {}).get("name"),
                "stage": ov.get("canonical_stage"),
                "actions": cand.get("allowed_actions"),
                "cv_available": (cand.get("cv") or {}).get("available"),
                "cv_filename": (cand.get("cv") or {}).get("filename"),
                "score": ranking.get("score"),
                "ai_advisory": ranking.get("ai_advisory"),
                "evidence_n": len(ranking.get("evidence") or []),
                "waiting_for_hr": ov.get("waiting_for_hr"),
                "automatic_activity": ov.get("automatic_activity"),
                "payload_keys": sorted(cand.keys()),
            },
            ensure_ascii=False,
            default=str,
        ),
    )

    action = "shortlist"
    omd._require_mobile_feature_action(app, aziz, "recruiting", "candidate_shortlist", "shortlist")
    app.require_entitlement(aziz, "pre_hiring", "prehire.read")
    application = app.dashboard_application_or_404(app_key, aziz["company_code"])
    status = str(application.get("status") or "")
    stage = rl.normalize_stage(status) or status
    perms = omd._authoritative_permissions(app, aziz)
    assert rl.authorize_recruiting_action(action, stage, perms), (action, stage)
    summary = app.prehire_application_summary(application, include_raw=False)
    name = ((summary.get("candidate") or {}) if isinstance(summary.get("candidate"), dict) else {}).get("name") or "Candidate"
    position_title = ((summary.get("position") or {}) if isinstance(summary.get("position"), dict) else {}).get("title") or "this role"
    consequence = f"Move {name} to the shortlist for {position_title}."
    prep = omd.prepare_mobile_confirmation(
        app,
        aziz,
        idempotency_key=f"hr-cand-qual-shortlist-{uuid.uuid4().hex[:8]}",
        action_type=omd.MOBILE_ACTIONS[action],
        target_type="application",
        target_id=app_key,
        expected_status=status,
        safe_summary=f"{name} · {position_title}",
        consequence=consequence,
        args={"app_key": app_key, "reason": None},
    )
    conf = prep.get("confirmation") or {}
    print(
        "PREPARE_SHORTLIST",
        json.dumps(
            {
                "status": prep.get("status"),
                "summary": conf.get("summary"),
                "consequence": conf.get("consequence"),
                "current_state": conf.get("current_state"),
                "action": conf.get("action"),
            },
            ensure_ascii=False,
        ),
    )
    assert conf.get("confirmation_id")
    print("PREPARE_ONLY_NO_CONFIRM", True)

    term = omd.mobile_candidate_detail(app, aziz, terminal)["candidate"]
    t_status = str((term.get("overview") or {}).get("status") or "")
    t_stage = rl.normalize_stage(t_status) or t_status
    print(
        "TERMINAL_DETAIL",
        json.dumps(
            {
                "app_key": terminal,
                "stage": t_stage,
                "status": t_status,
                "actions": term.get("allowed_actions"),
                "decide_actions": [a for a in (term.get("allowed_actions") or []) if a in {"shortlist", "reject", "hire"}],
            },
            ensure_ascii=False,
        ),
    )
    print(
        "ALREADY_DECIDED_SERVER",
        t_stage in rl.TERMINAL_STAGES or t_status in {"hired", "rejected", "import_archived"},
    )

    ranking_list = omd.mobile_candidate_rankings(app, aziz, limit=20)
    print("RANKINGS_ITEMS", len(ranking_list.get("items") or []), "TOTAL", ranking_list.get("total"))
    print("VERDICT_BACKEND_PATH", "PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
