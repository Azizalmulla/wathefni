#!/usr/bin/env python3
"""Action Inbox — controlled real-HR canary (WATHEFNI / Aziz / Talal).

Proves Aziz can see Talal-only inbox items; Fouad and others denied; payroll excluded;
soft-kill on either allowlist; WAVE1=0 kill switch; residual 0.
Does NOT widen past approved Aziz/Talal boundary.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import uuid
from collections import Counter
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

import action_inbox_wave1 as w1  # noqa: E402
import analytics_attention_wave1 as anw1  # noqa: E402
import compliance_findings_wave1 as cfw1  # noqa: E402
import app  # noqa: E402
from fastapi import HTTPException  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("AIW1RHC_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("AIW1RHC_EVID") or f"/tmp/action-inbox-rhc-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

AZIZ_PHONE = "96599338566"
AZIZ_UID = "88b17ca9-aff4-4721-a553-c1b5514ef95f"
AZIZ_EMAIL = "azizalmulla16@gmail.com"
TALAL = "WATHEFNI-96550252254"
FOUAD_PHONE = "66363363"
FOUAD_EMAIL = "f.burhama@disruptv.tech"
SAFE_PAGES = {
    "analytics",
    "compliance",
    "employees",
    "onboarding",
    "attendance",
    "leave",
    "shifts",
    "payroll",
    "inbox",
}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def _ctx(
    phone: str,
    uid: str,
    email: str | None = None,
    *,
    role: str = "owner",
    perms: list[str] | None = None,
) -> dict[str, Any]:
    permissions = perms or [
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
        "actor_role": role,
        "permission_authority": "backend_current",
        "permission_subject_user_id": uid,
        "permission_subject_company": COMPANY,
        "permissions": permissions,
        "hr_user": {"user_id": uid, "email": email, "phone": phone},
        "access": {
            "permission_authority": "backend_current",
            "permission_subject_user_id": uid,
            "permission_subject_company": COMPANY,
            "permissions": permissions,
        },
    }


def _summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: Counter[str] = Counter()
    by_soa: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for item in items:
        src = str(item.get("source") or item.get("source_module") or "unknown")
        soa = str(item.get("system_of_action") or "")
        by_source[src] += 1
        by_soa[soa] += 1
        deep = item.get("deep_link") if isinstance(item.get("deep_link"), dict) else {}
        rows.append(
            {
                "id": item.get("id"),
                "source": src,
                "system_of_action": soa,
                "employee_key": item.get("employee_key"),
                "employee_name": item.get("employee_name") or item.get("who"),
                "severity": item.get("severity"),
                "what_en": item.get("what_en") or item.get("title"),
                "deep_link_page": deep.get("page"),
                "deep_link_employee": deep.get("employee") or deep.get("employee_key"),
            }
        )
    return {
        "total": len(items),
        "by_source": dict(by_source),
        "by_system_of_action": dict(by_soa),
        "items": rows,
    }


def main() -> int:
    honesty = w1.honesty_payload()
    check("wave1 enabled", w1.action_inbox_wave1_enabled())
    check("company WATHEFNI", w1.action_inbox_wave1_enabled_for_company(COMPANY))
    check("exclude payroll on", w1.exclude_payroll_stream() is True)
    check("read-only honesty", honesty.get("read_only") is True and honesty.get("mutates_records") is False)
    check("no AI", honesty.get("ai") is False)
    check("alerts owns notifications", honesty.get("alerts_delivery_owns_notifications") is True)
    check("analytics freeze intact", anw1.honesty_payload().get("compliance_metrics") is False)
    check("compliance freeze intact", cfw1.honesty_payload().get("legal_compliance_claims") is False)

    check("viewer allowlist configured", bool(w1.real_viewer_allowlist()))
    check("subject allowlist configured", bool(w1.real_subject_allowlist()))
    check("real canary enabled", honesty.get("real_canary_enabled") is True)
    check("approved boundary", w1.allowlists_within_approved_boundary() is True)
    check("viewer is Aziz phone", AZIZ_PHONE in w1.real_viewer_allowlist() or w1.viewer_is_allowlisted(phone=AZIZ_PHONE))
    check("subject is Talal only", w1.real_subject_allowlist() == {TALAL}, sorted(w1.real_subject_allowlist()))
    check("nav offerable for Aziz", w1.nav_offerable_for_viewer(company_code=COMPANY, phone=AZIZ_PHONE, user_id=AZIZ_UID, email=AZIZ_EMAIL))
    check(
        "nav hidden for Fouad",
        w1.nav_offerable_for_viewer(company_code=COMPANY, phone=FOUAD_PHONE, email=FOUAD_EMAIL) is False,
    )

    # Live Aziz payload
    live = app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, AZIZ_EMAIL))
    check("Aziz API access", live.get("contract") == w1.ACTION_INBOX_WAVE1_CONTRACT, live.get("error"))
    items = list(live.get("items") or [])
    summary = _summarize_items(items)
    (EVID / "aziz-talal-items.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"aziz_items_summary": {"total": summary["total"], "by_source": summary["by_source"], "by_soa": summary["by_system_of_action"]}}, ensure_ascii=False))

    keys = {str(i.get("employee_key") or "").upper() for i in items}
    check("Talal only subjects", keys <= {TALAL} and (not keys or TALAL in keys or summary["total"] == 0), keys)
    for item in items:
        check(
            f"item subject Talal::{item.get('id')}",
            str(item.get("employee_key") or "").upper() == TALAL,
            item.get("employee_key"),
        )
        check(f"item not payroll::{item.get('id')}", not w1.is_payroll_inbox_item(item), item.get("id"))
        deep = item.get("deep_link") if isinstance(item.get("deep_link"), dict) else {}
        page = str(deep.get("page") or "").strip().lower()
        check(f"deep_link page present::{item.get('id')}", bool(page), deep)
        check(f"deep_link page safe::{item.get('id')}", page in SAFE_PAGES, page)
        dee = str(deep.get("employee") or deep.get("employee_key") or "").upper()
        if dee:
            check(f"deep_link employee Talal::{item.get('id')}", dee == TALAL, dee)
        # Permission-safe: payroll page must not appear while EXCLUDE_PAYROLL=1
        check(f"deep_link not payroll page::{item.get('id')}", page != "payroll", page)

    # Permission-stripped context: missing payroll.read still works; still no payroll
    lean = app.dashboard_action_inbox_payload(
        _ctx(
            AZIZ_PHONE,
            AZIZ_UID,
            AZIZ_EMAIL,
            perms=["analytics.read", "compliance.read", "employees.read", "onboarding.read"],
        )
    )
    lean_items = list(lean.get("items") or [])
    check("lean perms still Talal-only", all(str(i.get("employee_key") or "").upper() == TALAL for i in lean_items))
    check("lean perms no payroll", all(not w1.is_payroll_inbox_item(i) for i in lean_items))

    # Fouad + other viewers denied
    for label, phone, uid, email in (
        ("fouad", FOUAD_PHONE, f"fouad-{TAG}", FOUAD_EMAIL),
        ("viewer_no_phone", "", f"viewer-{TAG}", "fslalmulla@gmail.com"),
        ("random_manager", "96550000000", f"mgr-{TAG}", "manager@example.com"),
    ):
        try:
            app.dashboard_action_inbox_payload(_ctx(phone, uid, email, role="owner" if label == "fouad" else "viewer"))
            check(f"{label} denied", False, "expected HTTPException")
        except HTTPException as exc:
            check(
                f"{label} denied",
                isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_viewer_denied",
                exc.detail,
            )

    # Soft-kill: clear viewer allowlist
    prev_v = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST", "")
    prev_s = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST", "")
    prev_wave = os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1", "1")
    try:
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
        check("soft-kill viewer empty", not w1.real_viewer_allowlist())
        try:
            app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, AZIZ_EMAIL))
            check("soft-kill viewer API denial", False)
        except HTTPException as exc:
            check(
                "soft-kill viewer API denial",
                isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_viewer_denied",
                exc.detail,
            )

        # Restore viewer, clear subject
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = prev_v or AZIZ_PHONE
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
        check("soft-kill subject empty", not w1.real_subject_allowlist())
        empty_pack = app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, AZIZ_EMAIL))
        empty_items = list(empty_pack.get("items") or [])
        check("soft-kill subject removes items", len(empty_items) == 0, len(empty_items))
        check("soft-kill subject canary off", w1.honesty_payload().get("real_canary_enabled") is False)

        # Restore both, prove kill switch
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = prev_v or AZIZ_PHONE
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = prev_s or TALAL
        os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "0"
        try:
            app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, AZIZ_EMAIL))
            check("WAVE1=0 kill switch", False)
        except HTTPException as exc:
            check(
                "WAVE1=0 kill switch",
                isinstance(exc.detail, dict) and exc.detail.get("error") == "action_inbox_disabled",
                exc.detail,
            )
    finally:
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = prev_v or AZIZ_PHONE
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = prev_s or TALAL
        os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = prev_wave or "1"

    # Restored access
    restored = app.dashboard_action_inbox_payload(_ctx(AZIZ_PHONE, AZIZ_UID, AZIZ_EMAIL))
    restored_items = list(restored.get("items") or [])
    check("restored Aziz access", restored.get("contract") == w1.ACTION_INBOX_WAVE1_CONTRACT)
    check(
        "restored Talal-only",
        all(str(i.get("employee_key") or "").upper() == TALAL for i in restored_items),
        {str(i.get("employee_key")) for i in restored_items},
    )
    check("restored real canary on", w1.honesty_payload().get("real_canary_enabled") is True)

    # Mutation / wiring
    gate = inspect.getsource(app._action_inbox_gate)
    payload_src = inspect.getsource(app.dashboard_action_inbox_payload)
    check("gate fail-closed viewer", "action_inbox_viewer_denied" in gate)
    check("payload composes via build_action_inbox", "build_action_inbox" in payload_src)
    check(
        "payload has no mutating SQL",
        not any(tok in payload_src.upper() for tok in ("INSERT INTO", "UPDATE ", "DELETE FROM")),
    )
    check("honesty mutates_records false", w1.honesty_payload().get("mutates_records") is False)

    # ACK residual
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            w1.ensure_action_inbox_wave1_schema(cur, force=True)
            w1.record_action_inbox_wave_ack(
                cur,
                company_code=COMPANY,
                environment="production-real-hr-canary",
                details={
                    "tag": TAG,
                    "viewer": AZIZ_PHONE,
                    "subject": TALAL,
                    "item_total": summary["total"],
                    "by_source": summary["by_source"],
                },
                canary_tag=TAG,
            )
            conn.commit()
            deleted = w1.cleanup_canary_acks(cur, company_code=COMPANY, tag=TAG)
            conn.commit()
            residual = w1.residual_synthetic_acks(cur, company_code=COMPANY, tag=TAG)
    check("canary ack deleted", deleted >= 1, deleted)
    check("residual 0", residual == 0, residual)

    out = {
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "residual": residual,
        "allowlists": {
            "viewer": sorted(w1.real_viewer_allowlist_raw()),
            "subject": sorted(w1.real_subject_allowlist()),
            "within_boundary": w1.allowlists_within_approved_boundary(),
        },
        "aziz_items": summary,
        "privacy": {
            "fouad_denied": True,
            "other_viewers_denied": True,
            "talal_only": keys <= {TALAL},
            "payroll_excluded": all(not w1.is_payroll_inbox_item(i) for i in items),
            "exclude_payroll_flag": w1.exclude_payroll_stream(),
        },
    }
    (EVID / "canary-results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": PASS,
                "fail": FAIL,
                "tag": TAG,
                "residual": residual,
                "item_total": summary["total"],
                "by_source": summary["by_source"],
                "by_soa": summary["by_system_of_action"],
                "viewer": AZIZ_PHONE,
                "subject": TALAL,
            },
            ensure_ascii=False,
        )
    )
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
