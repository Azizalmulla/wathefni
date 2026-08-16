#!/usr/bin/env python3
"""Action Inbox Phase 0-B — production safety-gate canary (WATHEFNI).

Proves fail-closed empty allowlists, payroll exclusion, soft-kill restore,
and WAVE1=0 kill switch. Does NOT leave real viewer/subject allowlists populated.
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

import action_inbox_wave1 as w1  # noqa: E402
import analytics_attention_wave1 as anw1  # noqa: E402
import compliance_findings_wave1 as cfw1  # noqa: E402
import app  # noqa: E402
from fastapi import HTTPException  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("AIW1P0B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("AIW1P0B_EVID") or f"/tmp/action-inbox-p0b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

AZIZ_PHONE = "96599338566"
AZIZ_UID = "88b17ca9-aff4-4721-a553-c1b5514ef95f"
TALAL = "WATHEFNI-96550252254"


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def _ctx(phone: str, uid: str, email: str | None = None) -> dict[str, Any]:
    perms = [
        "analytics.read",
        "compliance.read",
        "employees.read",
        "onboarding.read",
        "leave.read",
        "attendance.read",
        "shifts.read",
        "payroll.read",
    ]
    return {
        "company_code": COMPANY,
        "hr_phone": phone,
        "actor_phone": phone,
        "actor_user_id": uid,
        "actor_email": email,
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": uid,
        "permission_subject_company": COMPANY,
        "permissions": perms,
        "hr_user": {"user_id": uid, "email": email, "phone": phone},
        "access": {
            "permission_authority": "backend_current",
            "permission_subject_user_id": uid,
            "permission_subject_company": COMPANY,
            "permissions": perms,
        },
    }


def main() -> int:
    honesty = w1.honesty_payload()
    check("wave1 enabled", w1.action_inbox_wave1_enabled())
    check("company allowlisted", w1.action_inbox_wave1_enabled_for_company(COMPANY))
    check("phase0 viewer fail-closed flag", honesty.get("phase0_viewer_allowlist_fail_closed") is True)
    check("phase0 subject fail-closed flag", honesty.get("phase0_subject_allowlist_fail_closed") is True)
    check("exclude payroll default/on", w1.exclude_payroll_stream() is True)
    check("no AI", honesty.get("ai") is False)
    check("no mutations", honesty.get("mutates_records") is False)
    check("analytics freeze intact", anw1.honesty_payload().get("compliance_metrics") is False)
    check("compliance freeze intact", cfw1.honesty_payload().get("legal_compliance_claims") is False)

    # Production must end (and start) with empty allowlists
    check("viewer allowlist empty (live env)", not w1.real_viewer_allowlist_raw() and not w1.real_viewer_allowlist())
    check("subject allowlist empty (live env)", not w1.real_subject_allowlist_raw() and not w1.real_subject_allowlist())
    check("real canary not enabled", honesty.get("real_canary_enabled") is False)
    check("nav hidden for Aziz when empty", w1.nav_offerable_for_viewer(company_code=COMPANY, phone=AZIZ_PHONE, user_id=AZIZ_UID) is False)

    # API denial with empty allowlists
    try:
        app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, "azizalmulla16@gmail.com"))
        check("API denial empty allowlist", False, "expected HTTPException")
    except HTTPException as exc:
        check(
            "API denial empty allowlist",
            isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_viewer_denied",
            exc.detail,
        )

    # Payroll exclusion even when temporarily scoped to Talal (in-process only)
    prev_v = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST")
    prev_s = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST")
    prev_wave = os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1")
    try:
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = AZIZ_PHONE
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = TALAL
        pack = w1.build_action_inbox(
            compliance_findings=[
                {
                    "id": "talal",
                    "severity": "high",
                    "reason_en": "Talal doc",
                    "employee_key": TALAL,
                    "document_type": "residence",
                    "document_type_canonical": "residence",
                    "deep_link": {"page": "compliance", "employee": TALAL},
                    "evidence_status": "expired",
                },
                {
                    "id": "other",
                    "severity": "high",
                    "reason_en": "Other doc",
                    "employee_key": "WATHEFNI-96566363363",
                    "document_type": "residence",
                    "document_type_canonical": "residence",
                    "deep_link": {"page": "compliance"},
                    "evidence_status": "expired",
                },
            ],
            e360_next_actions=[
                w1.normalize_e360_next_action(
                    {
                        "id": "payroll:timesheet",
                        "severity": "high",
                        "module": "payroll",
                        "title": "Timesheet awaiting approval",
                        "reason": "open",
                        "target": {"page": "payroll"},
                    },
                    employee_key=TALAL,
                    employee_name="Talal",
                ),
                w1.normalize_e360_next_action(
                    {
                        "id": "onboarding:incomplete",
                        "severity": "medium",
                        "module": "onboarding",
                        "title": "Onboarding incomplete",
                        "reason": "open",
                        "target": {"page": "onboarding"},
                    },
                    employee_key=TALAL,
                    employee_name="Talal",
                ),
            ],
            apply_phase0_filters=True,
        )
        keys = {str(i.get("employee_key") or "").upper() for i in pack["items"]}
        check("temp probe Talal-only subjects", keys <= {TALAL}, keys)
        check("temp probe no payroll rows", all(not w1.is_payroll_inbox_item(i) for i in pack["items"]))
        check("approved boundary", w1.allowlists_within_approved_boundary() is True)

        live = app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, "azizalmulla16@gmail.com"))
        check("temp live payload ok", live.get("contract") == w1.ACTION_INBOX_WAVE1_CONTRACT)
        for item in live.get("items") or []:
            check("temp live Talal-only", str(item.get("employee_key") or "").upper() == TALAL, item.get("employee_key"))
            check("temp live no payroll", not w1.is_payroll_inbox_item(item), item.get("id"))

        try:
            app.dashboard_action_inbox_payload(_ctx("66363363", f"fouad-{TAG}", "f.burhama@disruptv.tech"))
            check("fouad denied during temp probe", False)
        except HTTPException as exc:
            check(
                "fouad denied during temp probe",
                isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_viewer_denied",
                exc.detail,
            )
    finally:
        # Soft-kill restore — must clear before any kill-switch test ends
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
        if prev_v is None:
            os.environ.pop("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST", None)
            os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
        else:
            os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = prev_v
        if prev_s is None:
            os.environ.pop("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST", None)
            os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
        else:
            os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = prev_s

    # Force empty for soft-kill proof regardless of prior env inheritance
    os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
    os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
    check("soft-kill viewers empty after clear", not w1.real_viewer_allowlist())
    check("soft-kill subjects empty after clear", not w1.real_subject_allowlist())
    try:
        app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID))
        check("soft-kill API denial after clear", False)
    except HTTPException as exc:
        check(
            "soft-kill API denial after clear",
            isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_viewer_denied",
            exc.detail,
        )

    # WAVE1=0 kill switch (process-local), then restore
    os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "0"
    try:
        app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID))
        check("WAVE1=0 kill switch", False)
    except HTTPException as exc:
        check(
            "WAVE1=0 kill switch",
            isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_disabled",
            exc.detail,
        )
    if prev_wave is None:
        os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "1"
    else:
        os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = prev_wave

    # Wiring
    gate = inspect.getsource(app._action_inbox_gate)
    check("gate viewer denied code", "action_inbox_viewer_denied" in gate)
    check("gate disabled code", "action_inbox_disabled" in gate)
    boot = inspect.getsource(app.dashboard_workspace_bootstrap)
    check("bootstrap action_inbox nav", "action_inbox" in boot and "nav_offerable_for_viewer" in boot)

    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    if dist.is_dir():
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in dist.rglob("*.js")
            if p.is_file() and p.stat().st_size < 2_000_000
        )
        check("UI Action Inbox EN/AR present", ("Action Inbox" in blob) or ("صندوق الإجراءات" in blob))
    else:
        check("dashboard dist present", False, str(dist))

    # ACK residual for phase0b audit row
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            w1.ensure_action_inbox_wave1_schema(cur, force=True)
            w1.record_action_inbox_wave_ack(
                cur,
                company_code=COMPANY,
                environment="production-phase0b",
                details={"tag": TAG, "proof": "phase0b", "allowlists_empty": True},
                canary_tag=TAG,
            )
            conn.commit()
            deleted = w1.cleanup_canary_acks(cur, company_code=COMPANY, tag=TAG)
            conn.commit()
            residual = w1.residual_synthetic_acks(cur, company_code=COMPANY, tag=TAG)
    check("canary ack deleted", deleted >= 1, deleted)
    check("residual 0", residual == 0, residual)

    # Final posture: empty allowlists, wave on
    os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
    os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
    if str(os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1") or "") == "0":
        os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "1"
    check("final real canary disabled", w1.honesty_payload().get("real_canary_enabled") is False)

    out = {"tag": TAG, "pass": PASS, "fail": FAIL, "results": RESULTS, "residual": residual}
    (EVID / "canary-results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "tag": TAG, "residual": residual, "allowlists_populated": False}, ensure_ascii=False))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
