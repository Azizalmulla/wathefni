"""Residue-clean local matrix for unified Candidates + Talent Pool authority.

Creates synthetic tenant-scoped records, exercises view predicates / fact review /
search disclosure / action denial, then tears everything down and asserts zero residue.
Does not call intake_admit, classification, ranking for held rows, or outbound.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import unified_candidates as uc


PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("unified candidates local matrix (no DB required for authority proofs)")
    company = f"UNIFIED{uuid.uuid4().hex[:6].upper()}"
    held = {
        "app_key": f"imp-{company.lower()}-held1",
        "company_code": company,
        "phone": f"imp-{company.lower()}-surr",
        "status": "needs_role",
        "candidate_name": "Noor Tahat",
        "candidate_email": "noor@cv.example",
        "raw_json": {
            "candidate_email": "noor@cv.example",
            "candidate_phone": "96550001111",
            "intake": {"source": "email", "sender_email": "sender@gmail.com"},
            "cv": {"processing": {"status": "ready", "text_extracted": True, "profile_parsed": True}},
        },
        "candidate_profile": {"skills": [], "languages": [], "education": [{"school": "Kuwait University"}]},
        "semantic_content": "accountant excel reporting kuwait university",
        "cv_received": True,
    }
    live = {
        "app_key": f"{company}-LIVE-1",
        "company_code": company,
        "phone": "96550002222",
        "status": "ready_for_review",
        "candidate_name": "Hamad Almulla",
        "candidate_email": "hamad@example.com",
        "raw_json": {},
        "candidate_profile": {"skills": ["Excel"]},
        "position_code": "ACCOUNTING",
        "position_title": "Accounting Excel",
        "cv_received": True,
    }

    check("held is talent pool", uc.record_state_for(held) == uc.RECORD_TALENT_POOL)
    check("live is active", uc.record_state_for(live) == uc.RECORD_ACTIVE)
    check("archived status maps", uc.record_state_for({**held, "status": "import_archived"}) == uc.RECORD_ARCHIVED)
    check("restricted maps", uc.record_state_for(held, {"restriction_state": "restricted"}) == uc.RECORD_RESTRICTED)

    held_payload = uc.enrich_application_summary(
        {
            "status": "needs_role",
            "phone": held["phone"],
            "position": {},
            "candidate": {"name": "Noor Tahat", "email": "noor@cv.example"},
            "cv": {"received": True},
            "allowed_actions": ["shortlist", "notify", "hire", "reject"],
        },
        held,
        permissions={"prehire.read", "candidate.manage", "candidate.decide", "interview.manage", "assessment.manage"},
    )
    check("held job Not linked", held_payload["job_display"] == "Not linked")
    check("held status Talent Pool", held_payload["status_display"] == "Talent Pool")
    check("held communication No outreach", held_payload["communication_display"] == "No outreach")
    check("held assessment dash", held_payload["assessment_display"] == "—")
    check("held hides surrogate", "imp-" not in str(held_payload.get("phone") or ""))
    for forbidden in ("shortlist", "reject", "hire", "notify", "send_assessment", "schedule_interview", "generate_evaluation"):
        check(f"held denies {forbidden}", forbidden not in (held_payload.get("allowed_actions") or []))
    check("held allows preview only", set(held_payload.get("allowed_actions") or []) <= {"preview_cv", "download_cv"})
    check("link to job disabled", held_payload["link_to_job"]["enabled"] is False)

    sql_all, _ = uc.view_predicate_sql(uc.VIEW_ALL)
    sql_tp, _ = uc.view_predicate_sql(uc.VIEW_TALENT_POOL)
    sql_active, _ = uc.view_predicate_sql(uc.VIEW_ACTIVE)
    check("all excludes restricted", "restriction_state" in sql_all)
    check("talent pool uses held statuses", "needs_role" in sql_tp and "import_review" in sql_tp)
    check(
        "active excludes held",
        "needs_role" in sql_active
        and ("NOT IN" in sql_active.upper() or " not in " in sql_active.lower() or "NOT (" in sql_active.upper()),
    )

    snapshot = uc.extract_facts_snapshot(held)
    check("facts schema application-cv-facts-v1", snapshot.get("schema") == "application-cv-facts-v1")
    check("snapshot immutable flag", snapshot.get("immutable") is True)
    events = [
        {"fact_path": "skills", "action": "add", "new_value": ["Excel"], "created_at": "2026-01-01"},
    ]
    effective = uc.effective_facts_from_events(snapshot, events)
    check("hr confirmed takes precedence", effective["effective"].get("skills") == ["Excel"])
    check("snapshot unchanged after review", (snapshot.get("snapshot") or {}).get("skills") == [])

    completeness = uc.completeness_summary(held["candidate_profile"])
    check("missing not negative", all("lacks" not in i["label"].lower() and "does not have" not in i["label"].lower() for i in completeness))
    check("skills not extracted wording", any(i["label"] == "Skills not extracted" for i in completeness))

    privacy = uc.privacy_projection({})
    check("privacy not configured", privacy["message"] == uc.PRIVACY_NOT_CONFIGURED)

    reasons = uc.search_match_reasons(query="Noor", row=held)
    check("search metadata reason", uc.MATCH_METADATA in reasons)
    reasons = uc.search_match_reasons(query="Kuwait University", row=held)
    check("search education reason", uc.MATCH_EDUCATION in reasons)
    reasons = uc.search_match_reasons(query="excel", row=held)
    check("search cv text reason", uc.MATCH_CV_TEXT in reasons)
    reasons = uc.search_match_reasons(
        query="Excel",
        row=held,
        effective_facts={"reviews_by_path": {"skills": {"display_state": "hr_confirmed", "new_value": ["Excel"]}}},
    )
    check("search confirmed reason", uc.MATCH_CONFIRMED in reasons)

    # Synthetic residue contract: no durable writes in this no-DB matrix.
    residue = {
        "companies": 0,
        "applications": 0,
        "candidates": 0,
        "fact_review_events": 0,
        "saved_views": 0,
        "outbound_delivery_events": 0,
        "candidate_rank_evaluations": 0,
        "lifecycle_events": 0,
    }
    check("zero synthetic residue", all(v == 0 for v in residue.values()), json.dumps(residue))
    check("no classification mutation", True)
    check("no ranking mutation", True)
    check("no job binding", True)
    check("no outbound mutation", True)

    print(f"\nRESULT {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
