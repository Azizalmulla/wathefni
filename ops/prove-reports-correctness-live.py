#!/usr/bin/env python3
"""Production proof for Reports correctness contract (WATHEFNI)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wathefni/orchestrator")

import app as orch  # noqa: E402
import jobs_queue_contract as jqc  # noqa: E402
import prehire_visibility as pv  # noqa: E402
import reports_metrics as rm  # noqa: E402
import reports_v1 as rv  # noqa: E402

COMPANY = "WATHEFNI"


def count_export(report_type: str, vis_sql: str = "", vis_params: list | None = None, jobs_sql: str = "", jobs_params: list | None = None) -> int:
    return sum(
        1
        for _ in rv.iter_export_rows(
            orch,
            company_code=COMPANY,
            report_type=report_type,
            filters={"date_from": None, "date_to": None, "position_code": None},
            assessments_enabled=True,
            interviews_enabled=True,
            visibility_sql=vis_sql or None,
            visibility_params=vis_params or None,
            jobs_visibility_sql=jobs_sql or None,
            jobs_visibility_params=jobs_params or None,
        )
    )


def payload_for(role: str, actor: str = "proof-actor") -> dict:
    plan = pv.resolve_visibility_plan(policy=pv.PREHIRE_VISIBILITY_DEFAULT, role=role, surface="detail")
    vis_sql, vis_params = "", []
    jobs_sql, jobs_params = "", []
    if plan.get("apply_assignment_scope"):
        app_sql, placeholders = pv.applications_assignment_sql(role, applications_alias="a")
        vis_sql = app_sql
        vis_params = pv.bind_actor_params(placeholders, actor)
        job_sql, job_ph = pv.jobs_assignment_sql(role, alias="")
        jobs_sql = job_sql
        jobs_params = pv.bind_actor_params(job_ph, actor)
    body = rm.build_canonical_reports_payload(
        company=COMPANY,
        db_connect=orch.db_connect,
        reviewable_predicate=orch.reviewable_application_predicate,
        assessments_enabled=True,
        interviews_enabled=True,
        locale="en",
        visibility_sql=vis_sql or None,
        visibility_params=vis_params or None,
        jobs_visibility_sql=jobs_sql or None,
        jobs_visibility_params=jobs_params or None,
        visibility_meta=pv.visibility_meta(plan),
    )
    exports = body.get("exports") or {}
    actual = {
        t: count_export(t, vis_sql, vis_params, jobs_sql, jobs_params)
        for t in ("candidates", "roles", "assessments", "interviews", "followups", "followup_delivery_history")
    }
    displayed = {
        "candidates": exports.get("candidate_rows"),
        "roles": exports.get("role_rows"),
        "assessments": exports.get("assessment_rows"),
        "interviews": exports.get("interview_rows"),
        "followups": exports.get("followup_rows"),
        "followup_delivery_history": exports.get("followup_delivery_history_rows"),
    }
    parity = {k: displayed[k] == actual[k] for k in actual}
    return {
        "role": role,
        "apply_assignment_scope": bool(plan.get("apply_assignment_scope")),
        "overview": body.get("overview"),
        "stage_labels": [r.get("label") for r in (body.get("breakdowns") or {}).get("applications_by_stage") or []],
        "assessment_labels": [r.get("label") for r in (body.get("breakdowns") or {}).get("assessment_status") or []],
        "interview_labels": [r.get("label") for r in (body.get("breakdowns") or {}).get("interview_status") or []],
        "export_displayed": displayed,
        "export_actual": actual,
        "export_parity": parity,
        "metric_version": body.get("metric_version"),
        "partial": body.get("partial"),
        "ok": body.get("ok"),
    }


def main() -> None:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/reports-live-proof.json")
    owner = payload_for("owner")
    manager = payload_for("hr_manager")
    # Recruiter with empty assignment should be fail-closed / scoped (often zero)
    recruiter = payload_for("recruiter", actor="unassigned-recruiter-proof")

    rev = orch.reviewable_application_predicate("a")
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {rev} AND {jqc.active_pipeline_predicate("a")}
                """,
                (COMPANY,),
            )
            active_pipeline = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s
                  AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object')
                  AND (
                    COALESCE(a.data_source, a.raw_json->>'data_source', 'production') <> 'production'
                    OR COALESCE(a.status, '') IN ('needs_role','import_review','import_archived')
                    OR COALESCE(a.app_key, '') ILIKE '%%TEST%%'
                  )
                """,
                (COMPANY,),
            )
            held_outside_reviewable = int(cur.fetchone()["n"])

    overview = owner["overview"] or {}
    checks = {
        "active_applications_equals_pipeline": overview.get("active_applications") == active_pipeline,
        "active_applications_value": overview.get("active_applications"),
        "active_pipeline_truth": active_pipeline,
        "interview_debt_equals_4": overview.get("interview_scheduling_debt") == 4,
        "interview_debt_value": overview.get("interview_scheduling_debt"),
        "assessment_pending_excludes_completed": "Completed" not in str(overview.get("assessment_pending")),
        "assessment_pending_value": overview.get("assessment_pending"),
        "no_needs_role_in_stage": "Needs role" not in owner["stage_labels"] and "Needs Role" not in owner["stage_labels"],
        "stage_labels": owner["stage_labels"],
        "assessment_labels_human": all(
            label not in {"pending", "completed", "expired", "cancelled", "in_progress"}
            for label in owner["assessment_labels"]
        ),
        "interview_labels_human": all(
            label not in {"scheduled", "completed", "cancelled", "no_show", "rescheduled"}
            for label in owner["interview_labels"]
        ),
        "owner_export_parity": all(owner["export_parity"].values()),
        "manager_export_parity": all(manager["export_parity"].values()),
        "recruiter_export_parity": all(recruiter["export_parity"].values()),
        "owner_roles_not_open_only": (owner["export_displayed"].get("roles") or 0) >= (overview.get("open_roles") or 0),
        "interviews_export_visible_count": (owner["export_displayed"].get("interviews") or 0)
        == (owner["export_actual"].get("interviews") or -1),
        "metric_version": owner.get("metric_version") == "reports-contract-v2",
        "held_still_exist_outside_reviewable": held_outside_reviewable,
    }
    fail_keys = [k for k, v in checks.items() if isinstance(v, bool) and v is False]
    verdict = "PASS" if not fail_keys else "FAIL"
    result = {
        "company": COMPANY,
        "verdict": verdict,
        "fail_keys": fail_keys,
        "checks": checks,
        "owner": owner,
        "manager": manager,
        "recruiter": recruiter,
    }
    out_path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps({"verdict": verdict, "fail_keys": fail_keys, "checks": {k: checks[k] for k in checks if isinstance(checks[k], (bool, int, str))}}, indent=2))
    if verdict != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
