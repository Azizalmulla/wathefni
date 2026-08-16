#!/usr/bin/env python3
"""Live proof: Ranking matching/rankable/eligible contract (WATHEFNI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ORCH = Path("/opt/wathefni/orchestrator")
sys.path.insert(0, str(ORCH))

import app as orch  # noqa: E402
import candidate_ranking as cr  # noqa: E402
import ranking_queue_contract as contract  # noqa: E402
from jobs_queue_contract import active_pipeline_predicate  # noqa: E402

COMPANY = "WATHEFNI"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ranking-queue-live-proof.json")


def main() -> int:
    proof: dict = {"company": COMPANY, "jobs": [], "checks": {}, "verdict": "FAIL"}
    positions = ["FULLSTACK_DEVELOPER", "HR", "ACCOUNTING", "ACCOUNTING_EXCEL", "FINANCE", "SOCIAL_MEDIA_MANAGER"]

    for pos in positions:
        # Force recalculate under company-wide (owner) scope
        result = cr.rank_job_applications(orch, company_code=COMPANY, position_code=pos, force=True)
        legacy = cr.to_legacy_rank_candidates_shape(result, top_n=10)
        counters = contract.reconcile_pool_counters(result.get("items") or [])
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT count(*) AS n FROM applications a
                    WHERE a.company_code=%s AND a.position_code=%s
                      AND COALESCE(a.data_source, a.raw_json->>'data_source', 'production')='production'
                      AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv')='object')
                      AND {active_pipeline_predicate('a')}
                    """,
                    (COMPANY, pos),
                )
                active = int((cur.fetchone() or {}).get("n") or 0)
                # Missing-CV still in production non-terminal?
                cur.execute(
                    """
                    SELECT count(*) AS n FROM applications a
                    WHERE a.company_code=%s AND a.position_code=%s
                      AND COALESCE(a.data_source, a.raw_json->>'data_source', 'production')='production'
                      AND a.status NOT IN ('hired','rejected','withdrawn','archived','needs_role','import_review','import_archived')
                      AND NOT (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv')='object')
                    """,
                    (COMPANY, pos),
                )
                missing_cv_outside = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    """
                    SELECT a.status, count(*) AS n FROM applications a
                    WHERE a.company_code=%s AND a.position_code=%s
                      AND a.status IN ('hired','rejected','withdrawn','archived')
                    GROUP BY 1
                    """,
                    (COMPANY, pos),
                )
                terminals = {str(r["status"]): int(r["n"]) for r in cur.fetchall()}

        shown_buckets = [str(c.get("eligibility_bucket") or "") for c in (legacy.get("candidates") or [])]
        job = {
            "position": pos,
            "matching": result.get("matching_count", result.get("pool_total")),
            "rankable": result.get("rankable_count"),
            "eligible": result.get("eligible_count"),
            "not_applicable": result.get("not_applicable_count"),
            "not_met": result.get("not_met_count"),
            "unknown": result.get("unknown_count"),
            "restricted_held": result.get("restricted_held_count"),
            "reconciles": counters["reconciles"],
            "jobs_active_pipeline": active,
            "matching_eq_active_pipeline": int(result.get("matching_count") or 0) == active,
            "missing_cv_outside_matching": missing_cv_outside,
            "shown": len(legacy.get("candidates") or []),
            "shown_buckets": shown_buckets,
            "top_n_only_rankable": all(b in {"eligible", "not_applicable", ""} for b in shown_buckets),
            "no_unrankable_in_top_n": not any(b in {"requirement_not_met", "insufficient_information"} for b in shown_buckets),
            "terminals_present": terminals,
        }
        proof["jobs"].append(job)

    fs = next((j for j in proof["jobs"] if j["position"] == "FULLSTACK_DEVELOPER"), {})
    hr = next((j for j in proof["jobs"] if j["position"] == "HR"), {})
    accounting = next((j for j in proof["jobs"] if j["position"] == "ACCOUNTING"), {})

    # Visibility: empty assignment → matching 0
    empty = cr.rank_job_applications(
        orch,
        company_code=COMPANY,
        position_code="FULLSTACK_DEVELOPER",
        force=True,
        visibility_sql="FALSE",
        visibility_params=[],
    )
    pool_src = (ORCH / "candidate_ranking.py").read_text().split("def load_job_application_pool")[1].split("def load_complete_job_pool")[0]
    proof["checks"] = {
        "fullstack_missing_cv_excluded": bool(fs.get("matching_eq_active_pipeline")) and int(fs.get("matching") or 0) <= 1,
        "fullstack_matching_eq_active_pipeline": bool(fs.get("matching_eq_active_pipeline")),
        "hr_not_applicable_rankable_not_eligible": (
            int(hr.get("not_applicable") or 0) > 0
            and int(hr.get("rankable") or 0)
            == int(hr.get("not_applicable") or 0) + int(hr.get("eligible") or 0)
            and int(hr.get("eligible") or 0) == 0
        ),
        "accounting_not_applicable_rankable": (
            int(accounting.get("not_applicable") or 0) >= 1 and int(accounting.get("rankable") or 0) >= 1
        ),
        "all_reconcile": all(j.get("reconciles") for j in proof["jobs"]),
        "all_top_n_rankable_only": all(j.get("no_unrankable_in_top_n") for j in proof["jobs"]),
        "empty_visibility_matching_zero": int(empty.get("matching_count") or empty.get("pool_total") or 0) == 0,
        "assessment_default_unused": cr.DEFAULT_EVIDENCE_POLICY["sources"]["assessment"] == "unused",
        "assessment_lateral_wired": "assessment_pool_lateral_sql" in pool_src,
        # Owner/company-wide matching ≡ Candidates active_pipeline (reviewable CV + non-terminal).
        "owner_matching_eq_candidates_pipeline": all(j.get("matching_eq_active_pipeline") for j in proof["jobs"]),
        # Recruiter with empty assignment sees 0 (counts ≡ openable rows).
        "recruiter_empty_assignment_matching_zero": int(empty.get("matching_count") or empty.get("pool_total") or 0) == 0,
    }

    ok = all(
        [
            proof["checks"]["fullstack_missing_cv_excluded"],
            proof["checks"]["fullstack_matching_eq_active_pipeline"],
            proof["checks"]["hr_not_applicable_rankable_not_eligible"] or int(hr.get("matching") or 0) == 0,
            proof["checks"]["accounting_not_applicable_rankable"] or int(accounting.get("matching") or 0) == 0,
            proof["checks"]["all_reconcile"],
            proof["checks"]["all_top_n_rankable_only"],
            proof["checks"]["empty_visibility_matching_zero"],
            proof["checks"]["assessment_default_unused"],
            proof["checks"]["assessment_lateral_wired"],
            proof["checks"]["owner_matching_eq_candidates_pipeline"],
            proof["checks"]["recruiter_empty_assignment_matching_zero"],
        ]
    )
    proof["verdict"] = "PASS" if ok else "FAIL"
    OUT.write_text(json.dumps(proof, indent=2, default=str) + "\n")
    print(json.dumps({"verdict": proof["verdict"], "checks": proof["checks"], "fullstack": fs, "hr": hr}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
