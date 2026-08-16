#!/usr/bin/env python3
"""Read-only Reports page correctness proof for WATHEFNI (audit only)."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/opt/wathefni/orchestrator")

import app as orch  # noqa: E402
import jobs_queue_contract as jqc  # noqa: E402
import prehire_overview as po  # noqa: E402
import reports_metrics as rm  # noqa: E402
import reports_v1 as rv  # noqa: E402

COMPANY = "WATHEFNI"


def count_export(report_type: str) -> int:
    return sum(
        1
        for _ in rv.iter_export_rows(
            orch,
            company_code=COMPANY,
            report_type=report_type,
            filters={"date_from": None, "date_to": None, "position_code": None},
            assessments_enabled=True,
            interviews_enabled=True,
        )
    )


def main() -> None:
    payload = rv.build_reports_v1_payload(
        orch,
        company_code=COMPANY,
        assessments_enabled=True,
        interviews_enabled=True,
        offers_enabled=True,
    )
    action_counts = po.compute_action_counts(
        company=COMPANY,
        db_connect=orch.db_connect,
        assessments_enabled=True,
    )
    metrics = rm.build_reports_metrics(
        company=COMPANY,
        db_connect=orch.db_connect,
        reviewable_predicate=orch.reviewable_application_predicate,
        action_counts=action_counts,
        assessments_enabled=True,
        interviews_enabled=True,
    )

    summary = payload.get("summary") or {}
    interview_total = (
        (summary.get("interview_scheduled") or 0)
        + (summary.get("interview_completed") or 0)
        + (summary.get("interview_no_show") or 0)
    )
    stage = (metrics.get("breakdowns") or {}).get("applications_by_stage") or []
    active = sum(
        int(r.get("count") or 0)
        for r in stage
        if str(r.get("label") or "").lower() not in {"hired", "rejected", "withdrawn", "closed"}
    )
    metric_map = {m["key"]: m["value"] for m in metrics.get("metrics") or []}
    pending = int(metric_map.get("assessment_pending") or 0)
    completed = int(metric_map.get("assessment_completed") or 0)

    counts = {
        t: count_export(t)
        for t in [
            "candidates",
            "roles",
            "assessments",
            "interviews",
            "followups",
            "followup_delivery_history",
        ]
    }

    rev = orch.reviewable_application_predicate("a")
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s
                  AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object')
                """,
                (COMPANY,),
            )
            stage_scope_all = int(cur.fetchone()["n"])
            cur.execute(
                f"SELECT COUNT(*) AS n FROM applications a WHERE a.company_code=%s AND {rev}",
                (COMPANY,),
            )
            stage_scope_rev = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s AND {rev} AND {jqc.active_pipeline_predicate("a")}
                """,
                (COMPANY,),
            )
            active_pipeline = int(cur.fetchone()["n"])
            debt = po.interview_scheduling_debt_predicate(
                "a", interview_status_expr="li.interview_status"
            )
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM applications a
                LEFT JOIN LATERAL (
                  SELECT ci.status AS interview_status
                  FROM candidate_interviews ci
                  WHERE ci.company_code=a.company_code AND ci.app_key=a.app_key
                  ORDER BY ci.scheduled_start DESC NULLS LAST
                  LIMIT 1
                ) li ON TRUE
                WHERE a.company_code=%s AND {rev} AND {debt}
                """,
                (COMPANY,),
            )
            interview_debt = int(cur.fetchone()["n"])
            # test leak probe in stage-scope query (no production predicate)
            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM applications a
                WHERE a.company_code=%s
                  AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object')
                  AND (
                    COALESCE(a.data_source, a.raw_json->>'data_source', 'production') <> 'production'
                    OR COALESCE(a.app_key, '') ILIKE '%%TEST%%'
                    OR COALESCE(a.raw_json->>'candidate_name', a.raw_json->>'name', '') ILIKE 'test %%'
                    OR COALESCE(a.status, '') IN ('needs_role','import_review','import_archived')
                  )
                """,
                (COMPANY,),
            )
            non_production_in_stage_scope = int(cur.fetchone()["n"])

    out = {
        "company": COMPANY,
        "ui_simulated": {
            "open_roles": metric_map.get("open_roles"),
            "active_applications_from_stage_labels": active,
            "ready_for_review": metric_map.get("ready_for_review"),
            "interviews_needing_action_from_summary_fields": interview_total,
            "interviews_metric_value": metric_map.get("interviews"),
            "assessments_needing_action_pending_plus_completed": pending + completed,
            "assessment_pending_only": pending,
            "followups_current": metric_map.get("followups_current"),
        },
        "exports_displayed_vs_download": {
            "exports_candidate_rows_payload": (payload.get("exports") or {}).get("candidate_rows"),
            "exports_assessment_rows_payload": (payload.get("exports") or {}).get("assessment_rows"),
            "exports_interview_rows_payload": (payload.get("exports") or {}).get("interview_rows"),
            "exports_followup_rows_payload": (payload.get("exports") or {}).get("followup_rows"),
            "exports_role_rows_payload": (payload.get("exports") or {}).get("role_rows"),
            "actual_export_row_counts": counts,
            "ui_followups_card_count": metric_map.get("followups_current"),
            "ui_roles_card_count": (payload.get("exports") or {}).get("role_rows") or metric_map.get("open_roles"),
            "role_export_total_metric": metrics.get("role_export_total"),
            "delivery_history_metric": metric_map.get("delivery_failure_history"),
        },
        "scope": {
            "stage_breakdown_apps_no_reviewable": stage_scope_all,
            "reviewable_apps": stage_scope_rev,
            "active_pipeline_apps": active_pipeline,
            "interview_scheduling_debt_apps": interview_debt,
            "non_production_or_held_in_stage_scope": non_production_in_stage_scope,
        },
        "raw_assessment_labels": (metrics.get("breakdowns") or {}).get("assessment_status") or [],
        "raw_interview_labels": (metrics.get("breakdowns") or {}).get("interview_status") or [],
        "stage_labels": stage,
        "summary_keys": sorted(summary.keys()),
        "action_counts": {
            "ready_for_review": action_counts.get("ready_for_review"),
            "follow_up_needed": action_counts.get("follow_up_needed"),
            "assessment_pending": action_counts.get("assessment_pending"),
        },
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
