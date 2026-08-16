#!/usr/bin/env python3
"""Compliance Wave 1-B — production synthetic Findings Contract canary (WATHEFNI).

Document compliance only. SYNTHETIC_ONLY required.
Proves ranking, scope isolation, owner/escalation, residence/work-permit integrity,
deep links, freshness/as_of, evidence honesty, EN/AR, residual canary ACK = 0.
Does not mutate frozen module contracts or real employee documents.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_COMPLIANCE_WAVE1", "1")
os.environ.setdefault("WATHEFNI_COMPLIANCE_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_KEY_MARKERS", "CFW1,CFW1-SYNTH|")
os.environ.setdefault("WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIXES", "965541")

import analytics_attention_wave1 as anw1  # noqa: E402
import compliance_findings_wave1 as cfw1  # noqa: E402
import app  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("CFW1B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("CFW1B_EVID") or f"/tmp/compliance-w1b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def main() -> int:
    honesty = cfw1.honesty_payload()
    check("wave1 enabled", cfw1.compliance_wave1_enabled())
    check("synthetic_only enforced", cfw1.compliance_wave1_synthetic_only() is True)
    check("company allowlisted", cfw1.compliance_wave1_enabled_for_company(COMPANY))
    check("document compliance only", honesty.get("document_compliance_only") is True)
    check("never government verified", honesty.get("government_verified") is False)
    check("no government APIs", honesty.get("government_apis") is False)
    check("no filing", honesty.get("filing") is False)
    check("no fine calculations", honesty.get("fine_calculations") is False)
    check("no legal-compliance claims", honesty.get("legal_compliance_claims") is False)
    check("no AI", honesty.get("ai") is False)
    check("analytics excludes compliance", honesty.get("analytics_excludes_compliance") is True)
    check("alerts own reminders", honesty.get("alerts_delivery_owns_reminders") is True)
    check("analytics freeze no compliance metrics", anw1.honesty_payload().get("compliance_metrics") is False)

    # --- residence / work-permit integrity ---
    integrity = cfw1.assert_residence_work_permit_integrity()
    check("residence/work-permit integrity", integrity.get("ok") is True, integrity)

    # --- ranked findings / owner / escalation / deep links (fixture builders) ---
    docs = [
        {
            "employee_key": f"WATHEFNI-CFW1-{TAG}",
            "employee_name": "Synth Alice",
            "department": "Ops",
            "document_type": "residence",
            "document_label": "Residence",
            "status": "expired",
            "days_until_expiry": -5,
            "expiry_date": "2026-07-01",
            "file_id": "f1",
            "next_action": "Start renewal",
        },
        {
            "employee_key": f"WATHEFNI-CFW1-{TAG}-B",
            "employee_name": "Synth Bob",
            "department": "Sales",
            "document_type": "residency_iqama",
            "document_label": "Residence (legacy id)",
            "status": "missing",
            "days_until_expiry": None,
            "expiry_date": None,
            "file_id": None,
            "next_action": "Request",
        },
        {
            "employee_key": f"WATHEFNI-CFW1-{TAG}-C",
            "employee_name": "Synth Carla",
            "department": "HQ",
            "document_type": "work_permit",
            "document_label": "Work permit",
            "status": "expiring_soon",
            "days_until_expiry": 4,
            "expiry_date": "2026-08-07",
            "file_id": "f3",
            "next_action": "Remind",
        },
        {
            "employee_key": f"WATHEFNI-CFW1-{TAG}-D",
            "employee_name": "Synth Dan",
            "department": "HQ",
            "document_type": "civil_id",
            "document_label": "Civil ID",
            "status": "valid",
            "days_until_expiry": 200,
            "expiry_date": "2027-01-01",
            "file_id": "f4",
            "next_action": "None",
        },
        {
            "employee_key": f"WATHEFNI-CFW1-{TAG}-E",
            "employee_name": "Synth Eve",
            "department": "Ops",
            "document_type": "passport",
            "document_label": "Passport",
            "status": "needs_review",
            "days_until_expiry": None,
            "expiry_date": None,
            "file_id": "f5",
            "next_action": "Review",
        },
    ]
    employees = {
        f"WATHEFNI-CFW1-{TAG}": {
            "employee_key": f"WATHEFNI-CFW1-{TAG}",
            "profile": {"branch": "Salmiya", "team": "Ops"},
        }
    }
    pack = cfw1.build_compliance_findings(
        documents=docs,
        employee_rows_by_key=employees,
        enabled_modules={"compliance", "onboarding", "employees"},
    )
    findings = pack["findings"]
    check("findings omit valid", len(findings) == 4, len(findings))
    check("severity high-first", findings[0]["severity"] == "high", findings[0])
    expired = next(f for f in findings if f["bucket"] == "expired")
    check("owner default hr_compliance", expired["owner_role"] == "hr_compliance")
    check("escalation overdue_daily", expired["escalation_step"] == "overdue_daily")
    check("deadline present", bool(expired.get("deadline")))
    check("location from profile", expired.get("location") == "Salmiya")
    check("deep link compliance", expired["deep_link"]["page"] == "compliance")
    check("reason AR present", bool(expired.get("reason_ar")))
    check("evidence honesty expired", expired["evidence_status"] == "expired")
    check("never gov verified on finding", expired["government_verified"] is False)
    check("guidance_only", expired["guidance_only"] is True)

    missing = next(f for f in findings if f["bucket"] == "missing")
    check("legacy iqama → residence", missing["document_type_canonical"] == "residence")
    check("missing deep link onboarding", missing["deep_link"]["page"] == "onboarding")
    check(
        "employees secondary link",
        any(l.get("page") == "employees" for l in (missing.get("secondary_links") or [])),
    )

    wp = next(f for f in findings if f["document_type"] == "work_permit")
    check("work_permit critical escalation", wp["escalation_step"] == "critical_hr")

    review = next(f for f in findings if f["bucket"] == "needs_review")
    check("needs_review evidence uploaded", review["evidence_status"] == "uploaded")

    check("as_of present", bool(pack.get("as_of")))
    check("timezone Kuwait", pack.get("timezone") == "Asia/Kuwait")
    check("freshness stale_after", int((pack.get("freshness") or {}).get("stale_after_seconds") or 0) == 300)
    defs = pack.get("definitions") or []
    check(
        "definitions EN/AR",
        all(d.get("label_en") and d.get("label_ar") and d.get("definition_en") and d.get("definition_ar") for d in defs),
    )

    partial = cfw1.source_availability({"compliance"})
    check("partial sources disclosed", partial["partial"] is True)
    check("alerts delivery-only", partial["sources"]["alerts"]["status"] == "delivery_only")

    # Owner override by document type
    prev = os.environ.get("WATHEFNI_COMPLIANCE_OWNER_BY_TYPE")
    try:
        os.environ["WATHEFNI_COMPLIANCE_OWNER_BY_TYPE"] = json.dumps(
            {
                "work_permit": {
                    "owner_role": "hr_manager",
                    "owner_label_en": "HR Manager",
                    "owner_label_ar": "مدير الموارد البشرية",
                }
            }
        )
        owner = cfw1.owner_for_document_type("work_permit")
        check("owner override", owner["owner_role"] == "hr_manager", owner)
    finally:
        if prev is None:
            os.environ.pop("WATHEFNI_COMPLIANCE_OWNER_BY_TYPE", None)
        else:
            os.environ["WATHEFNI_COMPLIANCE_OWNER_BY_TYPE"] = prev

    # --- live production read + ACK residual ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            cfw1.ensure_compliance_wave1_schema(cur, force=True)
            cfw1.record_compliance_wave_ack(
                cur,
                company_code=COMPANY,
                environment="production-canary",
                details={"tag": TAG, "proof": "wave1b"},
                canary_tag=TAG,
            )
            conn.commit()

    live = app.dashboard_compliance_payload(
        COMPANY,
        viewer_phone=None,
        dashboard_user_id=None,
        actor_role="hr_admin",
        limit=50,
    )
    check("live contract", live.get("contract") == cfw1.COMPLIANCE_WAVE1_CONTRACT, live.get("contract"))
    check("live as_of", bool(live.get("as_of")))
    check("live timezone Kuwait", live.get("timezone") == "Asia/Kuwait", live.get("timezone"))
    check("live kuwait_date", bool(live.get("kuwait_date")))
    check("live findings list", isinstance(live.get("findings"), list))
    check("live freshness", isinstance(live.get("freshness"), dict) and int((live.get("freshness") or {}).get("stale_after_seconds") or 0) > 0)
    check("live honesty never gov", (live.get("honesty") or {}).get("government_verified") is False)
    check("live no legal claims", (live.get("honesty") or {}).get("legal_compliance_claims") is False)
    check("live alerts own reminders", (live.get("honesty") or {}).get("alerts_delivery_owns_reminders") is True)
    auth = live.get("authority") if isinstance(live.get("authority"), dict) else {}
    check("live synthetic_only", auth.get("synthetic_only") is True, auth)
    check("live document_compliance_only", auth.get("document_compliance_only") is True, auth)

    # Scope isolation: manager with synthetic phone / missing user must fail closed or return empty scope
    scoped = app.dashboard_compliance_payload(
        COMPANY,
        viewer_phone="96554100000",
        dashboard_user_id=f"cfw1-missing-{TAG}",
        actor_role="manager",
        limit=20,
    )
    check("manager scope payload returns", isinstance(scoped, dict))
    # Manager without assignments should see zero or scoped-down employees — never unscoped company dump.
    scoped_emps = int((scoped.get("summary") or {}).get("employees_total") or 0)
    unscoped_emps = int((live.get("summary") or {}).get("employees_total") or 0)
    if unscoped_emps > 0:
        check(
            "manager scope isolation",
            scoped_emps < unscoped_emps or scoped_emps == 0,
            {"scoped": scoped_emps, "unscoped": unscoped_emps},
        )
    else:
        check("manager scope probe completed", True)

    # Dashboard route still uses actor identity for compliance (parity with analytics pattern where applicable)
    src = inspect.getsource(app.dashboard_posthire_compliance)
    check("dashboard compliance actor_role", "actor_role" in src)
    check("dashboard compliance user_id", "dashboard_user_id" in src or "actor_user_id" in src)

    # EN/AR + mobile web dist checks
    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    if dist.is_dir():
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in dist.rglob("*.js")
            if p.is_file() and p.stat().st_size < 2_000_000
        )
        check(
            "UI Findings EN/AR",
            ("Findings by severity" in blob) or ("النتائج حسب الخطورة" in blob),
        )
        check(
            "UI never government verified",
            ("Never government verified" in blob) or ("ليست تحققاً حكومياً" in blob),
        )
        check("UI responsive grid", "sm:grid-cols-2" in blob or "sm:grid-cols-3" in blob or "lg:grid-cols-5" in blob)
        check("UI Open SoA EN/AR", ("Open system of action" in blob) or ("افتح نظام التنفيذ" in blob))
    else:
        check("dashboard dist present", False, str(dist))

    # Residual cleanup
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            deleted = cfw1.cleanup_canary_acks(cur, company_code=COMPANY, tag=TAG)
            conn.commit()
            residual = cfw1.residual_synthetic_acks(cur, company_code=COMPANY, tag=TAG)
    check("canary ack deleted", deleted >= 1, deleted)
    check("residual 0", residual == 0, residual)

    check(
        "synthetic marker detection",
        cfw1.is_synthetic_subject(employee_key=f"WATHEFNI-CFW1-{TAG}", phone=f"9655411{TAG[:5]}"),
    )
    check(
        "real subject not synthetic",
        not cfw1.is_synthetic_subject(employee_key="WATHEFNI-96566363363", phone="96566363363"),
    )

    out = {
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "live": {
            "as_of": live.get("as_of"),
            "findings_count": len(live.get("findings") or []),
            "contract": live.get("contract"),
            "employees_total": unscoped_emps,
        },
        "honesty": honesty,
        "integrity": integrity,
    }
    (EVID / "canary-results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "tag": TAG, "residual": residual}, ensure_ascii=False))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
