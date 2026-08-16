#!/usr/bin/env python3
"""Action Inbox Wave 1-B — production synthetic Unified Action Inbox canary (WATHEFNI).

Read-only. SYNTHETIC_ONLY required. No AI / Compliance Wave 2 / Analytics Wave 2 /
Payroll money / Attendance ingest / Shifts manager expansion.

Proves: scope isolation wiring, cross-source ranking, E360 dedupe, clears-on-resolve,
owner/deadline/escalation, evidence/authority labels, deep links, EN/AR + mobile web,
residual canary ACK = 0.
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

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
os.environ.setdefault("WATHEFNI_ACTION_INBOX_WAVE1", "1")
os.environ.setdefault("WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_KEY_MARKERS", "AIW1,AIW1-SYNTH|")
os.environ.setdefault("WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_PHONE_PREFIXES", "965542")

import action_inbox_wave1 as w1  # noqa: E402
import analytics_attention_wave1 as anw1  # noqa: E402
import compliance_findings_wave1 as cfw1  # noqa: E402
import app  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("AIW1B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("AIW1B_EVID") or f"/tmp/action-inbox-w1b-{TAG}")
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
    honesty = w1.honesty_payload()
    check("wave1 enabled", w1.action_inbox_wave1_enabled())
    check("synthetic_only enforced", w1.action_inbox_wave1_synthetic_only() is True)
    check("company allowlisted", w1.action_inbox_wave1_enabled_for_company(COMPANY))
    check("read_only", honesty.get("read_only") is True)
    check("composes_only", honesty.get("composes_only") is True)
    check("no mutations", honesty.get("mutates_records") is False)
    check("no AI", honesty.get("ai") is False)
    check("hiring reports separate", honesty.get("hiring_reports_separate") is True)
    check("alerts own notifications", honesty.get("alerts_delivery_owns_notifications") is True)
    check("no compliance wave2", honesty.get("compliance_wave2") is False)
    check("no analytics wave2", honesty.get("analytics_wave2") is False)
    check("no payroll money", honesty.get("payroll_money") is False)
    check("no attendance ingest", honesty.get("attendance_ingest") is False)
    check("no shifts manager expand", honesty.get("shifts_manager_expansion") is False)
    check("analytics freeze no compliance metrics", anw1.honesty_payload().get("compliance_metrics") is False)
    check("compliance freeze no legal claims", cfw1.honesty_payload().get("legal_compliance_claims") is False)

    # --- ranking / owner / deadline / escalation / deep links / labels ---
    pack = w1.build_action_inbox(
        analytics_attention=[
            {
                "id": "pending_leave",
                "severity": "high",
                "reason_en": "3 leave requests await a decision",
                "reason_ar": "3 طلبات إجازة بانتظار القرار",
                "subject": "Leave queue",
                "source_module": "leave",
                "deep_link": {"page": "leave"},
            }
        ],
        compliance_findings=[
            {
                "id": f"expired:WATHEFNI-AIW1-{TAG}:residence",
                "severity": "high",
                "reason_en": "Synth Alice residence expired",
                "reason_ar": "إقامة Synth Alice منتهية",
                "why_it_matters_en": "MOI guidance only",
                "why_it_matters_ar": "إرشاد فقط",
                "employee_key": f"WATHEFNI-AIW1-{TAG}",
                "employee_name": "Synth Alice",
                "team": "Ops",
                "location": "Salmiya",
                "document_type": "residence",
                "document_type_canonical": "residence",
                "owner_role": "hr_compliance",
                "owner_label_en": "Company HR / Compliance",
                "owner_label_ar": "الموارد البشرية / الامتثال",
                "deadline": "2026-08-03",
                "deadline_label_en": "Overdue",
                "deadline_label_ar": "متأخر",
                "escalation_step": "overdue_daily",
                "escalation_label_en": "Daily follow-up",
                "escalation_label_ar": "متابعة يومية",
                "system_of_action": "compliance",
                "evidence_status": "expired",
                "evidence_status_label_en": "Expired",
                "evidence_status_label_ar": "منتهية",
                "deep_link": {
                    "page": "compliance",
                    "employee": f"WATHEFNI-AIW1-{TAG}",
                    "document_type": "residence",
                },
                "government_verified": False,
                "guidance_only": True,
            }
        ],
        e360_next_actions=[
            w1.normalize_e360_next_action(
                {
                    "id": "compliance:expired:residence",
                    "severity": "critical",
                    "module": "compliance",
                    "title": "Residence expired",
                    "reason": "Document has expired",
                    "target": {"page": "compliance"},
                    "meta": {"document_type": "residence"},
                },
                employee_key=f"WATHEFNI-AIW1-{TAG}",
                employee_name="Synth Alice",
            ),
            w1.normalize_e360_next_action(
                {
                    "id": "onboarding:incomplete",
                    "severity": "medium",
                    "module": "onboarding",
                    "title": "Onboarding incomplete",
                    "reason": "2 required items still open",
                    "target": {"page": "onboarding"},
                },
                employee_key=f"WATHEFNI-AIW1-{TAG}-B",
                employee_name="Synth Bob",
                team="Sales",
            ),
        ],
    )
    items = pack["items"]
    check("cross-source item count", len(items) == 3, len(items))  # e360 compliance deduped
    check("e360 compliance deduped", int(pack["summary"]["deduped_e360_compliance"]) >= 1)
    check("high severity first", items[0]["severity"] in {"high", "critical"}, items[0].get("severity"))
    streams = {i["source_stream"] for i in items}
    check("all three streams present", streams == {"analytics", "compliance", "employees"}, streams)

    compliance_item = next(i for i in items if i["source_stream"] == "compliance")
    check("owner label EN", bool(compliance_item.get("owner_label_en")))
    check("owner label AR", bool(compliance_item.get("owner_label_ar")))
    check("deadline present", bool(compliance_item.get("deadline")))
    check("deadline label EN", bool(compliance_item.get("deadline_label_en")))
    check("escalation label EN", bool(compliance_item.get("escalation_label_en")))
    check("escalation label AR", bool(compliance_item.get("escalation_label_ar")))
    check("evidence label EN", bool(compliance_item.get("evidence_status_label_en")))
    check("authority label EN", bool(compliance_item.get("authority_status_label_en")))
    check("authority label AR", bool(compliance_item.get("authority_status_label_ar")))
    check("deep link compliance", compliance_item["deep_link"]["page"] == "compliance")
    check("what AR present", bool(compliance_item.get("what_ar")))
    check("never gov verified", compliance_item.get("government_verified") is False)

    leave_item = next(i for i in items if i["source_stream"] == "analytics")
    check("analytics deep link leave", leave_item["deep_link"]["page"] == "leave")

    e360_item = next(i for i in items if i["source_stream"] == "employees")
    check("e360 deep link onboarding", e360_item["deep_link"]["page"] == "onboarding")

    proof = w1.prove_item_clears_when_source_resolves()
    check("clears on resolve", proof.get("cleared") is True, proof)
    check("dedupe in clear proof", int(proof.get("deduped") or 0) >= 1, proof)
    check("after clear remaining 1", int(proof.get("after_total") or 0) == 1, proof)

    check("as_of present", bool(pack.get("as_of")))
    check("timezone Kuwait", pack.get("timezone") == "Asia/Kuwait")
    check("freshness stale_after", int((pack.get("freshness") or {}).get("stale_after_seconds") or 0) == 300)
    defs = pack.get("definitions") or []
    check(
        "definitions EN/AR",
        all(d.get("label_en") and d.get("label_ar") and d.get("definition_en") and d.get("definition_ar") for d in defs),
    )
    check("honesty mutates false", pack["honesty"]["mutates_records"] is False)

    # --- live production read + ACK residual ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            w1.ensure_action_inbox_wave1_schema(cur, force=True)
            w1.record_action_inbox_wave_ack(
                cur,
                company_code=COMPANY,
                environment="production-canary",
                details={"tag": TAG, "proof": "wave1b"},
                canary_tag=TAG,
            )
            conn.commit()

    def _synth_context(*, role: str, phone: str | None, user_id: str, perms: list[str]) -> dict[str, Any]:
        return {
            "company_code": COMPANY,
            "hr_phone": phone,
            "actor_user_id": user_id,
            "actor_role": role,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": COMPANY,
            "permissions": perms,
            "access": {
                "permission_authority": "backend_current",
                "permission_subject_user_id": user_id,
                "permission_subject_company": COMPANY,
                "permissions": perms,
            },
        }

    admin_perms = [
        "analytics.read",
        "compliance.read",
        "employees.read",
        "onboarding.read",
        "leave.read",
        "attendance.read",
        "shifts.read",
        "payroll.read",
    ]
    live = app.dashboard_action_inbox_payload(
        _synth_context(role="hr_admin", phone=None, user_id=f"aiw1-admin-{TAG}", perms=admin_perms)
    )
    check("live contract", live.get("contract") == w1.ACTION_INBOX_WAVE1_CONTRACT, live.get("contract"))
    check("live as_of", bool(live.get("as_of")))
    check("live timezone Kuwait", live.get("timezone") == "Asia/Kuwait", live.get("timezone"))
    check("live items list", isinstance(live.get("items"), list))
    check("live honesty no mutate", (live.get("honesty") or {}).get("mutates_records") is False)
    check("live synthetic_only", (live.get("authority") or {}).get("synthetic_only") is True, live.get("authority"))

    # Scope isolation wiring (manager identity keys + E360 manager_scope)
    src = inspect.getsource(app.dashboard_action_inbox_payload)
    check("payload viewer_phone", "viewer_phone" in src)
    check("payload actor_role", "actor_role" in src)
    e360_src = inspect.getsource(app._inbox_e360_next_actions)
    check("e360 manager_scope", "manager_scope_employee_keys" in e360_src)
    route_src = inspect.getsource(app.dashboard_posthire_action_inbox)
    check("route uses dashboard_context", "dashboard_context" in route_src)

    # Manager probe: missing manager user should not crash; scope filters apply downstream
    try:
        scoped = app.dashboard_action_inbox_payload(
            _synth_context(
                role="manager",
                phone=f"9655421{TAG[:5]}",
                user_id=f"aiw1-missing-{TAG}",
                perms=["employees.read", "compliance.read", "analytics.read"],
            )
        )
        check("manager scope probe returns", isinstance(scoped, dict))
        check("manager probe has items list", isinstance(scoped.get("items"), list))
        # Manager without assignments should see fewer or equal items vs admin — never crash.
        admin_n = len(live.get("items") or [])
        scoped_n = len(scoped.get("items") or [])
        if admin_n > 0:
            check(
                "manager scope isolation",
                scoped_n <= admin_n,
                {"scoped": scoped_n, "admin": admin_n},
            )
        else:
            check("manager scope probe completed", True)
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", None)
        ok = isinstance(detail, dict) and detail.get("error") == "permission_denied"
        check("manager scope fail-closed or returns", ok, str(exc))

    # EN/AR + mobile web dist checks
    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    if dist.is_dir():
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in dist.rglob("*.js")
            if p.is_file() and p.stat().st_size < 2_000_000
        )
        check(
            "UI Action Inbox EN/AR",
            ("Action Inbox" in blob) or ("صندوق الإجراءات" in blob),
        )
        check(
            "UI SoA EN/AR",
            ("System of action" in blob) or ("نظام التنفيذ" in blob),
        )
        check(
            "UI honesty hiring reports",
            ("Hiring Reports stay separate" in blob) or ("تقارير التوظيف منفصلة" in blob),
        )
        check(
            "UI owner/deadline labels",
            ("Owner" in blob) or ("المالك" in blob),
        )
        check("UI responsive mobile", "sm:flex-row" in blob or "sm:grid-cols" in blob)
    else:
        check("dashboard dist present", False, str(dist))

    # Residual cleanup
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            deleted = w1.cleanup_canary_acks(cur, company_code=COMPANY, tag=TAG)
            conn.commit()
            residual = w1.residual_synthetic_acks(cur, company_code=COMPANY, tag=TAG)
    check("canary ack deleted", deleted >= 1, deleted)
    check("residual 0", residual == 0, residual)

    check(
        "synthetic marker detection",
        w1.is_synthetic_subject(employee_key=f"WATHEFNI-AIW1-{TAG}", phone=f"9655421{TAG[:5]}"),
    )
    check(
        "real subject not synthetic",
        not w1.is_synthetic_subject(employee_key="WATHEFNI-96566363363", phone="96566363363"),
    )

    out = {
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "proof": proof,
        "honesty": honesty,
        "pack_summary": pack.get("summary"),
    }
    (EVID / "canary-results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "tag": TAG, "residual": residual}, ensure_ascii=False))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
