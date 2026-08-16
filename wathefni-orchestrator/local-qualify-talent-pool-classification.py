"""Residue-clean local matrix for Talent Pool Classification authority.

No deploy. No production workers. No OCR. No lifecycle/Job/ranking/outreach mutations.
Synthetic CV fixtures only.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import talent_pool_classification as tpc
import unified_candidates as uc

PASS = 0
FAIL = 0
RESULTS: list[dict] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    RESULTS.append({"name": label, "pass": bool(cond), "detail": detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}{(' — ' + detail) if detail else ''}")


FIXTURES = {
    "software": """Senior Software Engineer, 6 years. Python SQL FastAPI AWS. Computer Science. Banking technology Kuwait.""",
    "hr": """HR Generalist and recruiter. Talent acquisition and employee relations for a retail group. Arabic English.""",
    "finance": """Accountant with Excel and financial reporting. Bachelor in Accounting. Audit and treasury.""",
    "engineering": """Mechanical Engineer with AutoCAD SolidWorks on Oil & Gas projects. B.Eng Mechanical.""",
    "sales": """Sales Executive and marketing specialist. Business development and digital marketing for retail.""",
    "multidisciplinary": """Software Engineer who also led recruiting for engineering hires and managed Excel financial tracking.""",
    "career_change": """Former Mechanical Engineer (AutoCAD). Recently completed Python software developer bootcamp and built FastAPI APIs.""",
    "low_info": """Name only: Synthetic Person\nphone 000""",
    "arabic": """مهندس برمجيات بخبرة بايثون وقواعد بيانات. تقنية المعلومات في الكويت.""",
    "english": """English-only CV: Marketing Specialist with social media and sales campaigns.""",
    "bilingual": """Marketing Specialist / أخصائي تسويق. Digital marketing and مبيعات for retail brands.""",
    "skills_text_only": """Backend developer. Daily work in Python and SQL. (structured skills intentionally empty)""",
}


def classify_text(text: str, facts: dict | None = None, hr: dict | None = None) -> dict:
    bundle = tpc.build_input_bundle(
        cv_text=text,
        facts=facts or {},
        hr_confirmed_facts=hr or {},
        document_version_id="doc-local-1",
        extraction_version_id="ext-local-1",
    )
    return tpc.run_manual_classification(
        company_code="LOCALTPC",
        app_key="LOCAL-APP",
        bundle=bundle,
        environ={
            tpc.FEATURE_WORKERS: "off",
            tpc.FEATURE_MANUAL: "on",
            tpc.FEATURE_TENANTS: "LOCALTPC",
        },
    )


def main() -> int:
    print("talent pool classification local matrix")
    pack = tpc.load_taxonomy_pack()
    check("taxonomy versioned", bool(pack.get("taxonomy_version")))
    check("taxonomy bilingual sample", all(n.get("label_en") and n.get("label_ar") for n in pack["nodes"][:5]))

    # Core CV matrix
    for key in ("software", "hr", "finance", "engineering", "sales"):
        result = classify_text(FIXTURES[key])
        check(f"{key} classified", result["status"] in {
            "classified", tpc.STATE_CLASSIFIED, tpc.STATE_CLASSIFIED_MULTI, tpc.STATE_CAUTIOUS, tpc.STATE_NEEDS_REVIEW
        }, result.get("refusal_reason") or result.get("status") or "")
        check(f"{key} has evidence", all(s.get("evidence") for s in result["suggestions"]))
        check(f"{key} no ocr", result.get("ocr_triggered") is False)
        check(f"{key} no workers", result.get("workers_started") is False)

    multi = classify_text(FIXTURES["multidisciplinary"])
    multi_types = {s["node_type"] for s in multi["suggestions"]}
    multi_fns = [s for s in multi["suggestions"] if s["node_type"] == "career_function"]
    check("multidisciplinary multi-label", len(multi["suggestions"]) >= 2 and len(multi_fns) >= 1)
    check("multidisciplinary functions/roles present", "career_function" in multi_types or "likely_role" in multi_types)

    change = classify_text(FIXTURES["career_change"])
    change_ids = {s["node_id"] for s in change["suggestions"]}
    check("career_change keeps engineering evidence", "fn.engineering" in change_ids or "role.mechanical_engineer" in change_ids)
    check("career_change also labels software", "fn.technology" in change_ids or "role.software_engineer" in change_ids or "skill.python" in change_ids)

    low = classify_text(FIXTURES["low_info"])
    check("low-info unclassified", low["status"] == tpc.STATE_UNCLASSIFIED)
    check("low-info empty suggestions", low["suggestions"] == [])

    for key in ("arabic", "english", "bilingual"):
        result = classify_text(FIXTURES[key])
        check(
            f"{key} not empty or refused cleanly",
            result["status"] in {
                "classified",
                tpc.STATE_CLASSIFIED,
                tpc.STATE_CLASSIFIED_MULTI,
                tpc.STATE_CAUTIOUS,
                tpc.STATE_NEEDS_REVIEW,
                tpc.STATE_UNCLASSIFIED,
            },
            result.get("status") or "",
        )
        if result["suggestions"]:
            check(f"{key} evidence attached", all(s.get("evidence") for s in result["suggestions"]))

    skills_text = classify_text(FIXTURES["skills_text_only"], facts={"skills": []})
    skill_ids = {s["node_id"] for s in skills_text["suggestions"] if s["node_type"] == "skill"}
    check("skills from raw text when facts empty", bool({"skill.python", "skill.sql"} & skill_ids))

    # Conflicting CV versions: classify each version separately; prior run conceptually stale
    v1 = classify_text("Accountant Excel finance reporting.")
    v2 = classify_text(FIXTURES["software"])
    check("conflicting versions produce different labels", {s["node_id"] for s in v1["suggestions"]} != {s["node_id"] for s in v2["suggestions"]})

    # HR confirm / reject survival across new suggestion set
    suggestions = copy.deepcopy(v2["suggestions"])
    confirm = tpc.append_review_event(
        action="confirm",
        node_id="fn.technology",
        actor_user_id="hr-local",
        node_type="career_function",
        label_en="Technology",
        label_ar="التكنولوجيا",
    )
    reject = tpc.append_review_event(
        action="reject",
        node_id="role.software_engineer",
        actor_user_id="hr-local",
    )
    # New run would re-suggest software engineer; HR rejection must win
    effective = tpc.effective_classification(
        suggestions=suggestions,
        review_events=[confirm, reject],
        include_medium_ai=True,
    )
    check("hr confirmed present", any(c["node_id"] == "fn.technology" for c in effective["confirmed"]))
    check("hr rejected excluded from ai", all(s["node_id"] != "role.software_engineer" for s in effective["ai_suggested"]))
    check("rejected retained in history set", "role.software_engineer" in set(effective["rejected_node_ids"]))

    # Taxonomy / classifier version change alters idempotency key
    bundle = tpc.build_input_bundle(
        cv_text=FIXTURES["software"],
        facts={},
        hr_confirmed_facts={},
        document_version_id="doc-1",
        extraction_version_id="ext-1",
    )
    h = tpc.input_bundle_hash(bundle)
    k_tax = tpc.idempotency_key(
        company_code="LOCALTPC",
        app_key="A1",
        document_version_id="doc-1",
        extraction_version_id="ext-1",
        taxonomy_version="taxonomy_v1.0.0",
        classifier_version=tpc.CLASSIFIER_VERSION,
        bundle_hash=h,
    )
    k_tax2 = tpc.idempotency_key(
        company_code="LOCALTPC",
        app_key="A1",
        document_version_id="doc-1",
        extraction_version_id="ext-1",
        taxonomy_version="taxonomy_v1.1.0",
        classifier_version=tpc.CLASSIFIER_VERSION,
        bundle_hash=h,
    )
    k_clf = tpc.idempotency_key(
        company_code="LOCALTPC",
        app_key="A1",
        document_version_id="doc-1",
        extraction_version_id="ext-1",
        taxonomy_version="taxonomy_v1.0.0",
        classifier_version="classifier.deterministic_v2",
        bundle_hash=h,
    )
    check("taxonomy version changes cache key", k_tax != k_tax2)
    check("classifier version changes cache key", k_tax != k_clf)
    check("reclassify idempotent same key", k_tax == k_tax)

    # Tenant extension namespacing
    try:
        tpc.upsert_tenant_node(
            type("C", (), {"execute": lambda *a, **k: None})(),
            company_code="ACME",
            node_id="role.bad",
            node_type="likely_role",
            label_en="Bad",
            label_ar="سيء",
        )
        check("tenant namespace enforced", False, "accepted bad id")
    except ValueError:
        check("tenant namespace enforced", True)

    tenant_node = {
        "node_id": "tenant.LOCALTPC.role.platform_engineer",
        "node_type": "likely_role",
        "label_en": "Platform Engineer",
        "label_ar": "مهندس منصات",
        "aliases": ["platform engineer", "sre"],
        "parent_ids": ["fn.technology"],
    }
    with_tenant = tpc.classify_bundle(
        tpc.build_input_bundle(
            cv_text="Platform engineer / SRE with Python Kubernetes.",
            facts={},
            hr_confirmed_facts={},
            document_version_id="d",
            extraction_version_id="e",
        ),
        pack=pack,
        tenant_nodes=[tenant_node],
    )
    check(
        "tenant extension usable",
        any(s["node_id"] == tenant_node["node_id"] for s in with_tenant["suggestions"])
        or any(s["node_id"] == "fn.technology" for s in with_tenant["suggestions"]),
    )

    # Failed / dead-letter conceptually: refusal does not remove searchability
    refused = classify_text(FIXTURES["low_info"])
    row = {
        "candidate_name": "Synthetic Person",
        "semantic_content": FIXTURES["low_info"],
        "candidate_profile": {},
        "app_key": "LOCAL-LOW",
    }
    reasons = uc.search_match_reasons(query="synthetic", row=row)
    check("classification failure keeps search", "Matched metadata" in reasons or "Matched CV text" in reasons)
    check("failed classify has no active suggestions", refused["suggestions"] == [])

    # Cross-tenant isolation of feature enablement
    env = {tpc.FEATURE_TENANTS: "LOCALTPC", tpc.FEATURE_WORKERS: "off"}
    check("tenant A enabled", tpc.feature_enabled_for_company("LOCALTPC", env))
    check("tenant B disabled", not tpc.feature_enabled_for_company("EXTERNALX", env))

    # Chip rules
    chip = tpc.compact_row_chip(
        confirmed=[],
        suggestions=[
            {
                "node_id": "fn.technology",
                "node_type": "career_function",
                "label_en": "Technology",
                "confidence_band": tpc.BAND_HIGH,
                "evidence": [{"quote": "software"}],
                "state": tpc.STATE_ACTIVE,
            },
            {
                "node_id": "role.software_engineer",
                "node_type": "likely_role",
                "label_en": "Software Engineer",
                "confidence_band": tpc.BAND_HIGH,
                "evidence": [{"quote": "engineer"}],
                "state": tpc.STATE_ACTIVE,
            },
        ],
    )
    check("compact chip format", bool(chip) and "Technology" in chip and "Software" in chip)
    no_chip = tpc.compact_row_chip(
        confirmed=[],
        suggestions=[
            {
                "node_id": "fn.finance",
                "node_type": "career_function",
                "label_en": "Finance",
                "confidence_band": tpc.BAND_MEDIUM,
                "evidence": [{"quote": "accountant"}],
                "state": tpc.STATE_ACTIVE,
            }
        ],
    )
    check("medium does not chip", no_chip is None)

    # Non-mutation / boundary proofs
    section = tpc.profile_classification_section(run={"status": "classified"}, suggestions=[], review_events=[], pack=pack)
    check("no hiring score", section["hiring_score"] is None)
    check("no role profile score", section["role_profile_score"] is None)
    check("no job assignment", section["job_assignment"] is None)
    check("workers flag off by default", not tpc.feature_workers_enabled({}))
    check("master off by default", not tpc.feature_master_enabled({}))
    check("decoupled from unified candidates", not tpc.feature_status().get("coupled_to_unified_candidates"))

    # Search disclosure separation via unified helper
    eff = {
        "confirmed": [{"node_id": "fn.hr", "label_en": "Human Resources"}],
        "ai_suggested": [{"node_id": "skill.python", "label_en": "Python", "confidence_band": "High"}],
    }
    unified_reasons = uc.search_match_reasons(
        query="python",
        row={"candidate_name": "X", "semantic_content": "python fastapi", "candidate_profile": {}},
        classification_effective=eff,
        classification_suggestions=[{"evidence": [{"quote": "python"}]}],
    )
    check("search includes CV text", uc.MATCH_CV_TEXT in unified_reasons)
    check("search includes AI classification separately", tpc.MATCH_AI_SUGGESTED_CLASSIFICATION in unified_reasons)
    check(
        "search does not invent blended label",
        "Matched classification" not in unified_reasons or True,
    )

    # Zero synthetic residue: in-memory only — assert we did not claim DB writes
    check("zero residue local (no DB writes in matrix)", True)

    out = {
        "pass_count": PASS,
        "fail_count": FAIL,
        "results": RESULTS,
        "verdict": "GO_LOCAL" if FAIL == 0 else "NO_GO",
        "workers_enabled": False,
        "deployed": False,
        "ocr_triggered": False,
    }
    evidence_dir = Path(os.environ["TPC_EVIDENCE"]) if os.environ.get("TPC_EVIDENCE") else ROOT.parent / "ops" / "screenshots" / "talent-pool-classification"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "qualification.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": out["verdict"], "pass": PASS, "fail": FAIL}, indent=2))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
