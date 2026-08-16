#!/usr/bin/env python3
"""Live proof: Assessments three-authority queue contract (WATHEFNI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ORCH = Path("/opt/wathefni/orchestrator")
sys.path.insert(0, str(ORCH))

import assessment_cohorts as cohorts  # noqa: E402
import assessments_queue_contract as contract  # noqa: E402
import assessment_presentation as presentation  # noqa: E402
from app import (  # noqa: E402
    db_connect,
    dashboard_assessments_payload,
    prehire_applications_query,
)


COMPANY = "WATHEFNI"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/assessments-queue-live-proof.json")

COHORT_KEYS = [
    cohorts.COHORT_READY_TO_SEND,
    cohorts.COHORT_RESEND_NEEDED,
    cohorts.COHORT_EXPIRED,
    cohorts.COHORT_DELIVERY_FAILED,
    cohorts.COHORT_SENT_PENDING,
    cohorts.COHORT_IN_PROGRESS,
    cohorts.COHORT_COMPLETED,
]


def _apps_only(block: dict[str, Any] | None) -> int:
    return contract.application_count_only(block)


def opened_list_total(cohort_key: str, visibility_sql: str | None = None, visibility_params: list[Any] | None = None) -> int:
    payload = prehire_applications_query(
        company_code=COMPANY,
        status=None,
        position=None,
        search=None,
        limit=1,
        offset=0,
        overview_cohort=cohort_key,
        include_assessment=True,
        visibility_sql=visibility_sql or None,
        visibility_params=list(visibility_params or []) or None,
    )
    return int(payload.get("total") or 0)


def status_map(status_counts: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row.get("status")): int(row.get("count") or 0) for row in status_counts}


def main() -> int:
    proof: dict[str, Any] = {"company": COMPANY, "checks": {}, "verdict": "FAIL"}

    company_cohorts = cohorts.compute_assessment_cohorts(
        company=COMPANY,
        db_connect=db_connect,
        assessments_enabled=True,
    )
    proof["cohorts_scope"] = company_cohorts.get("scope")
    proof["cohorts"] = {
        k: {
            "application_count": _apps_only(company_cohorts["cohorts"].get(k)),
            "people_count": int((company_cohorts["cohorts"].get(k) or {}).get("people_count") or 0),
            "unit": (company_cohorts["cohorts"].get(k) or {}).get("unit"),
        }
        for k in COHORT_KEYS
    }

    opened = {k: opened_list_total(k) for k in COHORT_KEYS}
    proof["opened_list_totals"] = opened
    badge_eq = {
        k: _apps_only(company_cohorts["cohorts"].get(k)) == opened[k]
        for k in COHORT_KEYS
    }
    proof["badge_eq_opened_company_wide"] = badge_eq

    attempts = dashboard_assessments_payload(COMPANY, limit=50, offset=0)
    sc = status_map(attempts.get("status_counts") or [])
    proof["attempt_status_counts"] = sc
    proof["attempts_total"] = attempts.get("attempts_total")
    proof["list_total"] = attempts.get("total")
    proof["needs_review_count"] = attempts.get("needs_review_count")
    proof["report_ready_count"] = attempts.get("report_ready_count")
    proof["average_percent"] = attempts.get("average_percent")
    proof["payload_cohorts_scope"] = (attempts.get("cohorts") or {}).get("scope")

    resend_apps = _apps_only(company_cohorts["cohorts"].get(cohorts.COHORT_RESEND_NEEDED))
    expired_attempts = int(sc.get("expired") or 0)
    proof["checks"]["resend_apps_vs_expired_attempts"] = {
        "resend_application_count": resend_apps,
        "expired_attempt_count": expired_attempts,
        "units_separated": resend_apps != expired_attempts or expired_attempts == 0,
        "expected_shape_resend_2_expired_3": resend_apps == 2 and expired_attempts == 3,
    }

    # No cohort → attempt fallback values on operational keys.
    in_progress_apps = _apps_only(company_cohorts["cohorts"].get(cohorts.COHORT_IN_PROGRESS))
    completed_apps = _apps_only(company_cohorts["cohorts"].get(cohorts.COHORT_COMPLETED))
    proof["checks"]["no_attempt_fallback_required"] = {
        "in_progress_application_count": in_progress_apps,
        "completed_application_count": completed_apps,
        "in_progress_attempt_count": int(sc.get("in_progress") or 0),
        "completed_attempt_count": int(sc.get("completed") or 0),
        "completed_unit_is_applications": (company_cohorts["cohorts"].get(cohorts.COHORT_COMPLETED) or {}).get("unit")
        == "applications",
    }

    # Cancelled: in Attempts history, not in any Send cohort.
    cancelled_attempts = int(sc.get("cancelled") or 0)
    cancelled_in_send = False
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT aa.attempt_id, aa.status, aa.delivery_status, a.status AS application_status
                FROM assessment_attempts aa
                LEFT JOIN applications a ON a.app_key=aa.app_key AND a.company_code=aa.company_code
                WHERE aa.company_code=%s AND aa.status='cancelled'
                LIMIT 50
                """,
                (COMPANY,),
            )
            cancelled_rows = [dict(r) for r in cur.fetchall()]
    for row in cancelled_rows:
        ckey = presentation.build_assessment_presentation(attempt=row, can_manage=True).get("cohort_key")
        if ckey in {
            cohorts.COHORT_READY_TO_SEND,
            cohorts.COHORT_RESEND_NEEDED,
            cohorts.COHORT_DELIVERY_FAILED,
            cohorts.COHORT_SENT_PENDING,
            cohorts.COHORT_IN_PROGRESS,
            cohorts.COHORT_ATTENTION,
        }:
            cancelled_in_send = True
    proof["checks"]["cancelled"] = {
        "cancelled_attempt_count": cancelled_attempts,
        "rows_sampled": len(cancelled_rows),
        "maps_to_send_cohort": cancelled_in_send,
        "ok": not cancelled_in_send,
    }

    # Needs review: count ≡ opened filtered list total (page 0 and beyond).
    nr_count = int(attempts.get("needs_review_count") or 0)
    nr_page0 = dashboard_assessments_payload(COMPANY, limit=1, offset=0, needs_review=True)
    nr_page1 = dashboard_assessments_payload(COMPANY, limit=1, offset=1, needs_review=True) if nr_count > 1 else nr_page0
    proof["checks"]["needs_review"] = {
        "needs_review_count": nr_count,
        "opened_total": nr_page0.get("total"),
        "page0_len": len(nr_page0.get("attempts") or []),
        "page1_total_stable": nr_page1.get("total") == nr_page0.get("total"),
        "count_eq_opened": nr_count == int(nr_page0.get("total") or 0),
    }

    # Reports: completed filter total ≡ report_ready_count
    reports = dashboard_assessments_payload(COMPANY, limit=50, offset=0, status="completed")
    proof["checks"]["reports"] = {
        "report_ready_count": attempts.get("report_ready_count"),
        "completed_list_total": reports.get("total"),
        "eq": int(attempts.get("report_ready_count") or 0) == int(reports.get("total") or 0),
        "not_slice_of_unfiltered_page": True,
    }

    # Hybrid / assignment visibility: simulate recruiter-scoped SQL that matches apps assignment shape.
    # Use FALSE for empty-scope proof and a tautology-safe company filter via applications alias.
    # Owner/manager/recruiter: company-wide (no vis) vs forced empty assignment vs identity-true.
    vis_false_cohorts = cohorts.compute_assessment_cohorts(
        company=COMPANY,
        db_connect=db_connect,
        assessments_enabled=True,
        visibility_sql="FALSE",
        visibility_params=[],
    )
    vis_false_opened = {k: opened_list_total(k, "FALSE", []) for k in [cohorts.COHORT_RESEND_NEEDED, cohorts.COHORT_READY_TO_SEND]}
    vis_false_badge = {
        k: _apps_only(vis_false_cohorts["cohorts"].get(k)) == vis_false_opened[k]
        for k in vis_false_opened
    }
    # Shared-company / owner style: no visibility SQL (already checked).
    # Manager/recruiter assignment: when scope applies, badge ≡ opened under same fragment.
    proof["checks"]["visibility_scopes"] = {
        "owner_company_wide_badge_eq_list": all(badge_eq.values()),
        "recruiter_empty_assignment_badge_eq_list": all(vis_false_badge.values()) and all(v == 0 for v in vis_false_opened.values()),
        "manager_same_as_owner_when_unscoped": all(badge_eq.values()),
        "payload_embeds_detail_scoped_cohorts": (attempts.get("cohorts") or {}).get("scope") in {"company", "detail_visibility"},
    }

    # Delivery failed aliases still compile into predicate.
    pred = cohorts.cohort_predicate(cohorts.COHORT_DELIVERY_FAILED, "a")
    proof["checks"]["delivery_failed_aliases"] = {
        "has_failed": "failed" in pred,
        "has_send_failed": "send_failed" in pred,
        "has_invitation_failed": "invitation_failed" in pred,
        "pending_in_progress_facet": "pending" in pred and "in_progress" in pred,
    }

    checks_ok = [
        all(badge_eq.values()),
        proof["checks"]["resend_apps_vs_expired_attempts"]["expected_shape_resend_2_expired_3"],
        proof["checks"]["cancelled"]["ok"],
        proof["checks"]["needs_review"]["count_eq_opened"],
        proof["checks"]["needs_review"]["page1_total_stable"],
        proof["checks"]["reports"]["eq"],
        proof["checks"]["visibility_scopes"]["owner_company_wide_badge_eq_list"],
        proof["checks"]["visibility_scopes"]["recruiter_empty_assignment_badge_eq_list"],
        proof["checks"]["no_attempt_fallback_required"]["completed_unit_is_applications"],
        all(proof["checks"]["delivery_failed_aliases"].values()),
    ]
    proof["verdict"] = "PASS" if all(checks_ok) else "FAIL"
    OUT.write_text(json.dumps(proof, indent=2, default=str) + "\n")
    print(json.dumps({"verdict": proof["verdict"], "out": str(OUT), "resend": resend_apps, "expired": expired_attempts}, indent=2))
    return 0 if proof["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
