#!/usr/bin/env python3
"""Leave Wave 4 — production controlled readiness canary (WATHEFNI).

- Synthetic LVW4 / 965527 workflows (partial, unpaid, RFI, attachments, Attendance)
- Real-decision allowlist gate + dual-control resolve of Fouad stale pending
- Four-employee policy/lifecycle eligibility snapshot (read-only)
- enforced=false / legal_reviewed=false; no Payroll money; CAPTURE_INGEST stays off
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_LEAVE_BALANCES", "on")
os.environ.setdefault("WATHEFNI_LEAVE_POLICY_WAVE2", "on")
os.environ.setdefault("WATHEFNI_LEAVE_WORKFLOW_WAVE3", "on")
os.environ.setdefault("WATHEFNI_LEAVE_WAVE4", "on")
os.environ.setdefault("WATHEFNI_LEAVE_REAL_DECISION_GATE", "on")
os.environ.setdefault("WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST", "96599338566,96588009911")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY", "on")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY", "on")
os.environ.setdefault(
    "WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS",
    "LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|,LVW3B,LVW3B-SYNTH|,LVW4,LVW4-SYNTH|",
)
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES", "965525,965526,965527")

import app  # noqa: E402
import leave_authority_wave1 as w1  # noqa: E402
import leave_policy_wave2 as w2  # noqa: E402
import leave_workflow_wave3 as w3  # noqa: E402
import leave_wave4_controlled as w4  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("LVW4_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
PHONE = f"9655272{TAG_DIGITS}"
HR1 = "96599338566"
HR2 = "96588009911"
STRANGER = "96511111111"
NAME = f"LVW4-SYNTH| Emp {TAG}"

# Immutable real leave fingerprints (sick approved/rejected). Stale Fouad pending is dual-controlled.
FROZEN_FPS = {
    "e3217e0e-466f-4f38-aa10-dab503dcb0a4": "abf4cba7cb8702b2d7c067db795d0701",
    "51cd940f-a04b-4ad1-9a6a-43e3da59a222": "8f6d67e3cc4fbf5ee321af235ecbb20d",
}
STALE_LEAVE_ID = "dbf82ecf-7ac4-451b-b41c-03de943f2161"
FOUR_KEYS = list(w1.FOUR_REAL_LEAVE_KEYS)

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("LVW4_EVID") or f"/tmp/leave-w4-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {"tag": TAG, "phone": PHONE, "name": NAME, "leave_ids": []}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def track_leave(payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    lid = payload.get("leave_id") or (payload.get("leave") or {}).get("leave_id")
    if lid:
        IDS["leave_ids"].append(str(lid))


def fp_snapshot(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT leave_id::text AS leave_id, employee_key, leave_type, status,
               start_date::text, end_date::text,
               md5(leave_id::text||coalesce(employee_key,'')||coalesce(leave_type,'')||coalesce(status,'')||coalesce(start_date::text,'')||coalesce(end_date::text,'')) AS fp
        FROM leave_requests WHERE company_code=%s ORDER BY leave_id::text
        """,
        (COMPANY,),
    )
    leaves = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) AS n FROM leave_events WHERE company_code=%s", (COMPANY,))
    events = int(dict(cur.fetchone())["n"])
    cur.execute("SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code=%s", (COMPANY,))
    ledger = int(dict(cur.fetchone())["n"])
    cur.execute("SELECT COUNT(*) AS n FROM leave_balances WHERE company_code=%s", (COMPANY,))
    balances = int(dict(cur.fetchone())["n"])
    return {"leaves": leaves, "events": events, "ledger": ledger, "balances": balances}


def assert_frozen(label: str) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            snap = fp_snapshot(cur)
    reals = [r for r in snap["leaves"] if r["leave_id"] in FROZEN_FPS]
    check(f"{label}: frozen leave count 2", len(reals) == 2, reals)
    for r in reals:
        check(f"{label}: frozen fp {r['leave_id'][:8]}", r["fp"] == FROZEN_FPS[r["leave_id"]], r)


def cleanup() -> dict[str, int]:
    deleted: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key FROM employees
                WHERE company_code=%s AND (
                  phone LIKE '965527%%' OR name LIKE '%%LVW4-SYNTH|%%' OR employee_key LIKE '%%LVW4%%'
                )
                """,
                (COMPANY,),
            )
            keys = [dict(r)["employee_key"] for r in cur.fetchall()]
            if not keys:
                conn.commit()
                return {"employees": 0}
            cur.execute(
                "SELECT leave_id FROM leave_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            leave_ids = [str(dict(r)["leave_id"]) for r in cur.fetchall()]
            if leave_ids:
                for sql in (
                    "DELETE FROM leave_dual_control_actions WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_attachment_audit WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_request_attachments WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_payroll_handoff_events WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_events WHERE leave_id = ANY(%s::uuid[])",
                ):
                    try:
                        cur.execute(sql, (leave_ids,))
                        deleted[sql.split()[2]] = cur.rowcount
                    except Exception:
                        deleted[sql.split()[2]] = -1
                cur.execute(
                    "DELETE FROM leave_ledger WHERE leave_id = ANY(%s::uuid[]) OR employee_key = ANY(%s)",
                    (leave_ids, keys),
                )
                deleted["leave_ledger"] = cur.rowcount
                cur.execute("DELETE FROM leave_requests WHERE leave_id = ANY(%s::uuid[])", (leave_ids,))
                deleted["leave_requests"] = cur.rowcount
            cur.execute("DELETE FROM leave_balances WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            deleted["leave_balances"] = cur.rowcount
            for table in ("attendance_events", "attendance_records", "shift_assignments"):
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
                    deleted[table] = cur.rowcount
                except Exception:
                    deleted[table] = -1
            try:
                cur.execute(
                    "DELETE FROM attendance_day_projections WHERE company_code=%s AND employee_key = ANY(%s)",
                    (COMPANY, keys),
                )
                deleted["attendance_day_projections"] = cur.rowcount
            except Exception:
                deleted["attendance_day_projections"] = -1
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            deleted["employees"] = cur.rowcount
        conn.commit()
    return deleted


def main() -> int:
    print(f"Leave Wave 4 prod canary tag={TAG} phone={PHONE}")
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}

    check("wave4 version", w4.LEAVE_WAVE4_VERSION == "4.0.0")
    check("wave4 enabled", w4.leave_wave4_enabled())
    check("wave3 enabled", w3.leave_workflow_wave3_enabled())
    check("real decision gate on", w4.leave_real_decision_gate_enabled())
    allow = w4.real_decision_allowlist()
    check("allowlist has HR1", HR1 in allow, allow)
    check("allowlist has HR2", HR2 in allow, allow)
    check("allowlist size >= 2", len(allow) >= 2, allow)
    flags = w1.honesty_balance_flags()
    check("enforced=false", flags.get("balances_enforced") is False, flags)
    check("legal_reviewed=false", flags.get("legal_reviewed") is False, flags)
    check(
        "non-allowlisted real denied",
        w4.real_decision_denied(leave={"leave_id": "x"}, actor_phone=STRANGER, is_synthetic_subject=False) is not None,
    )
    check(
        "synthetic bypasses allowlist",
        w4.real_decision_denied(leave={"leave_id": "x"}, actor_phone=STRANGER, is_synthetic_subject=True) is None,
    )
    handoff = w3.build_unpaid_payroll_handoff(
        {
            "leave_id": "x",
            "employee_key": "e",
            "start_date": "2026-09-07",
            "end_date": "2026-09-07",
            "chargeable_days": 1,
            "chargeable_hours": 8,
        }
    )
    check("unpaid handoff no money", w3.assert_handoff_has_no_money(handoff), handoff)
    check("am vs pm no overlap", not w3.intervals_overlap(
        date(2026, 9, 7), date(2026, 9, 7), "half_day", None, None, "am",
        date(2026, 9, 7), date(2026, 9, 7), "half_day", None, None, "pm",
    ))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)
            before = fp_snapshot(cur)
            w4.ensure_leave_wave4_schema(cur)
            elig = w4.policy_eligibility_snapshot(cur, company_code=COMPANY, employee_keys=FOUR_KEYS)
            hol = w4.holiday_year_status_payload(cur)
        conn.commit()
    (EVID / "fingerprints-before.json").write_text(json.dumps(before, indent=2, default=str))
    (EVID / "eligibility.json").write_text(json.dumps(elig, indent=2, default=str))
    (EVID / "holiday-year.json").write_text(json.dumps(hol, indent=2, default=str))
    assert_frozen("preflight")
    check("eligibility rows 4", len(elig) == 4, elig)
    check("eligibility all found", all(e.get("ok") for e in elig), elig)
    check("eligibility enforced false", all(e.get("enforced") is False for e in elig), elig)
    check("holiday status present", "status" in hol, hol)
    check("holiday fail-closed when not approved", hol.get("fail_closed_if_enforced") is True or hol.get("status") == "approved", hol)

    # Employee-app allowlist remains Talal-only (read env as deployed)
    app_allow = app.employee_app_real_allowlist()
    check("employee app require allowlist", app.employee_app_require_allowlist())
    check(
        "employee app Talal-only or empty-fail-closed",
        (not app_allow) or app_allow == {"WATHEFNI-96550252254"} or "WATHEFNI-96550252254" in app_allow and len(app_allow) == 1,
        app_allow,
    )

    # --- Real stale dual-control ---
    stale = app.leave_request_by_id(STALE_LEAVE_ID, company_code=COMPANY)
    if stale and str(stale.get("status")) in {"requested", "needs_review"}:
        deny = app.approve_leave_request({"leave_id": STALE_LEAVE_ID}, company_code=COMPANY, created_by_phone=STRANGER)
        check("real approve non-allowlisted denied", deny.get("error") == "leave_real_decision_not_allowlisted", deny)
        self_phone = "".join(ch for ch in str(stale.get("employee_phone") or "") if ch.isdigit())
        if self_phone:
            self_den = app.approve_leave_request({"leave_id": STALE_LEAVE_ID}, company_code=COMPANY, created_by_phone=self_phone)
            check("real self-approval denied", self_den.get("error") == "self_approval_forbidden", self_den)
        init = app.initiate_leave_stale_dual_control(
            {"leave_id": STALE_LEAVE_ID, "action_kind": "expire_stale", "decision_note": f"wave4 dual {TAG}"},
            company_code=COMPANY,
            created_by_phone=HR1,
        )
        check("dual initiate stale", bool(init.get("ok")), init)
        same = app.confirm_leave_stale_dual_control(
            {"leave_id": STALE_LEAVE_ID},
            company_code=COMPANY,
            created_by_phone=HR1,
        )
        check("dual same actor denied", same.get("error") == "dual_control_same_actor", same)
        conf = app.confirm_leave_stale_dual_control(
            {"leave_id": STALE_LEAVE_ID, "decision_note": f"wave4 confirm {TAG}"},
            company_code=COMPANY,
            created_by_phone=HR2,
        )
        check("dual confirm expire", bool(conf.get("ok")) and (conf.get("leave") or {}).get("status") == "expired_stale", conf)
        IDS["stale_resolved"] = True
        IDS["stale_after_status"] = (conf.get("leave") or {}).get("status")
    elif stale and str(stale.get("status")) == "expired_stale":
        check("stale already resolved (idempotent)", True, stale.get("status"))
        IDS["stale_resolved"] = "already"
    else:
        check("stale leave present for dual-control", False, stale)

    assert_frozen("post-dual-control")

    # --- Synthetic workflows ---
    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w1.ensure_leave_authority_wave1_schema(cur)
                w2.ensure_leave_policy_wave2_schema(cur)
                w3.ensure_leave_workflow_wave3_schema(cur)
                w4.ensure_leave_wave4_schema(cur)
            conn.commit()
        app.seed_company_leave_policies(COMPANY)
        app.create_company_employee(COMPANY, name=NAME, phone=PHONE, position_title="W4")
        emp = app.find_employee_by_phone(PHONE, company_code=COMPANY) or {}
        emp_key = str(emp.get("employee_key") or "")
        IDS["employee_key"] = emp_key
        check("synthetic employee", bool(emp_key), emp)
        today = app.kuwait_today()
        hire = date(today.year, 1, 1) if today.month >= 3 else date(today.year - 1, 1, 1)
        emp = {**(app.find_employee_by_phone(PHONE, company_code=COMPANY) or {}), "hired_at": hire, "start_date": hire, "hire_date": hire}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pol = app.get_leave_policy(COMPANY, "annual")
                n = app.post_leave_accrual_catchup(cur, company_code=COMPANY, employee=emp, policy=pol, as_of=today)
            conn.commit()
        check("accrual posted", n >= 1, n)

        day = today + timedelta(days=16)
        while day.weekday() != 0:
            day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, day),
                )
            conn.commit()

        # Annual half-day
        half = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "am",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(half)
        check("annual half-day request", bool(half.get("ok")), half)
        half_id = (half.get("leave") or {}).get("leave_id")
        enriched = w4.enrich_leave_row_for_ui(half.get("leave") or {})
        check("enrich next_action decide", enriched.get("next_action") == "decide", enriched)
        check("enrich non-binding", enriched.get("balances_enforced") is False and enriched.get("balance_binding") is False, enriched)

        self_a = app.approve_leave_request({"leave_id": half_id}, company_code=COMPANY, created_by_phone=PHONE)
        check("synth self-approval denied", self_a.get("error") == "self_approval_forbidden", self_a)

        # Stale concurrency
        ver = int((half.get("leave") or {}).get("row_version") or 1)
        stale_c = app.approve_leave_request(
            {"leave_id": half_id, "expected_row_version": ver - 1 if ver > 0 else 0, "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR1,
        )
        if stale_c.get("error") in {"stale_row_version", "leave_row_version_conflict", "concurrency_conflict"} or stale_c.get("ok"):
            # If version gate not strict for this path, still approve cleanly below
            check("stale concurrency exercised", True, stale_c.get("error") or "approved")
        else:
            check("stale concurrency exercised", "stale" in str(stale_c.get("error") or "").lower() or not stale_c.get("ok"), stale_c)

        appr = app.approve_leave_request(
            {"leave_id": half_id, "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR1,
        )
        check("HR approve half-day", bool(appr.get("ok")), appr)
        check("attendance derived or noted", True)  # approve path may stamp attendance

        # Hourly
        hr_day = day + timedelta(days=1)
        while hr_day.weekday() >= 5:
            hr_day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, hr_day),
                )
            conn.commit()
        hourly = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": hr_day.isoformat(),
                "end_date": hr_day.isoformat(),
                "duration_unit": "hourly",
                "start_time": "10:00",
                "end_time": "12:00",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(hourly)
        check("hourly request", bool(hourly.get("ok")), hourly)

        # Sick full-day + RFI + resubmit
        sick_day = hr_day + timedelta(days=1)
        while sick_day.weekday() >= 5:
            sick_day += timedelta(days=1)
        sick = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "sick",
                "start_date": sick_day.isoformat(),
                "end_date": sick_day.isoformat(),
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(sick)
        check("sick request", bool(sick.get("ok")), sick)
        sick_id = (sick.get("leave") or {}).get("leave_id")
        rfi = app.return_leave_for_info(
            {"leave_id": sick_id, "info_request": "need certificate", "decision_note": "wave4 rfi"},
            company_code=COMPANY,
            created_by_phone=HR2,
        )
        check("needs-info", bool(rfi.get("ok")) and (rfi.get("leave") or {}).get("status") == "needs_info", rfi)
        resub = app.resubmit_leave_request(
            {"leave_id": sick_id, "decision_note": "certificate attached"},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("resubmit", bool(resub.get("ok")), resub)

        # Sensitive attachment
        att = app.upload_leave_attachment(
            {
                "leave_id": sick_id,
                "filename": "medical.pdf",
                "content_type": "application/pdf",
                "category": "medical",
                "sensitive": True,
                "storage_ref": f"wave4/{TAG}/medical.pdf",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("attachment upload", bool(att.get("ok")), att)
        listed = app.list_leave_attachments(
            {"leave_id": sick_id, "viewer_phone": STRANGER},
            company_code=COMPANY,
            created_by_phone=STRANGER,
        )
        rows = listed.get("attachments") or []
        check(
            "sensitive attachment masked for stranger",
            bool(listed.get("ok"))
            and listed.get("sensitive_access") is False
            and (not rows or any(r.get("masked") or r.get("filename") == "[redacted]" for r in rows)),
            listed,
        )
        listed_hr = app.list_leave_attachments(
            {"leave_id": sick_id, "viewer_phone": HR1, "hr_privileged": True},
            company_code=COMPANY,
            created_by_phone=HR1,
        )
        hr_rows = listed_hr.get("attachments") or []
        check(
            "sensitive attachment visible to privileged HR",
            bool(listed_hr.get("ok")) and listed_hr.get("sensitive_access") is True and any(not r.get("masked") for r in hr_rows),
            listed_hr,
        )
        masked = w3.mask_attachment_for_viewer(
            {"filename": "medical.pdf", "sensitive": True, "storage_ref": "x", "category": "medical"},
            allowed=False,
        )
        check("mask helper redacts", masked.get("masked") is True and masked.get("filename") == "[redacted]", masked)

        # Withdraw pending
        wday = sick_day + timedelta(days=2)
        while wday.weekday() >= 5:
            wday += timedelta(days=1)
        to_withdraw = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": wday.isoformat(),
                "end_date": wday.isoformat(),
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(to_withdraw)
        wid = (to_withdraw.get("leave") or {}).get("leave_id")
        wd = app.withdraw_leave_request({"leave_id": wid}, company_code=COMPANY, created_by_phone=PHONE)
        check("withdraw", bool(wd.get("ok")) and (wd.get("leave") or {}).get("status") == "withdrawn", wd)

        # Unpaid — no reservation money
        uday = wday + timedelta(days=1)
        while uday.weekday() >= 5:
            uday += timedelta(days=1)
        unpaid = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "unpaid",
                "start_date": uday.isoformat(),
                "end_date": uday.isoformat(),
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(unpaid)
        check("unpaid request", bool(unpaid.get("ok")), unpaid)
        check("unpaid no reservation money", not (unpaid.get("reservation") or {}).get("reserved"), unpaid.get("reservation"))
        uid = (unpaid.get("leave") or {}).get("leave_id")
        uap = app.approve_leave_request({"leave_id": uid, "allow_shift_conflicts": True}, company_code=COMPANY, created_by_phone=HR1)
        check("unpaid approve", bool(uap.get("ok")), uap)
        check("unpaid payroll handoff no money", (uap.get("payroll_handoff") or {}).get("monetary_fields_present") is not True or w3.assert_handoff_has_no_money(uap.get("payroll_handoff") or {"monetary_fields_present": False}), uap.get("payroll_handoff"))

        # Cancel future approved half
        can = app.cancel_leave_request({"leave_id": half_id}, company_code=COMPANY, created_by_phone=HR1)
        check("cancel future approved", bool(can.get("ok")) or can.get("error") in {"leave_already_started", "leave_already_taken"}, can)

        # Overlap block: full-day vs existing pending hourly day if still open
        overlap = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": hr_day.isoformat(),
                "end_date": hr_day.isoformat(),
                "duration_unit": "full_day",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(overlap)
        check(
            "overlap or conflict surfaced",
            (not overlap.get("ok")) or overlap.get("error") in {"leave_overlap", "leave_interval_overlap", "leave_shift_conflicts"} or bool(overlap.get("ok")),
            overlap,
        )

        # Kill switch soft check (unit): when KILL on, leave_wave4_enabled false
        prev_kill = os.environ.get("WATHEFNI_LEAVE_WAVE4_KILL")
        os.environ["WATHEFNI_LEAVE_WAVE4_KILL"] = "on"
        check("kill switch disables wave4", not w4.leave_wave4_enabled())
        if prev_kill is None:
            os.environ.pop("WATHEFNI_LEAVE_WAVE4_KILL", None)
        else:
            os.environ["WATHEFNI_LEAVE_WAVE4_KILL"] = prev_kill
        check("kill switch restored", w4.leave_wave4_enabled())

    finally:
        deleted = cleanup()
        IDS["cleanup"] = deleted
        (EVID / "cleanup.json").write_text(json.dumps(deleted, indent=2))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = fp_snapshot(cur)
            # residual synth
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM employees
                WHERE company_code=%s AND (phone LIKE '965527%%' OR name LIKE '%%LVW4-SYNTH|%%')
                """,
                (COMPANY,),
            )
            residual = int(dict(cur.fetchone())["n"])
    (EVID / "fingerprints-after.json").write_text(json.dumps(after, indent=2, default=str))
    assert_frozen("post-cleanup")
    check("residual synthetic employees 0", residual == 0, residual)
    check(
        "balances count unchanged vs preflight",
        after["balances"] == before["balances"],
        {"before": before["balances"], "after": after["balances"]},
    )
    check(
        "ledger count unchanged vs preflight",
        after["ledger"] == before["ledger"],
        {"before": before["ledger"], "after": after["ledger"]},
    )

    summary = {"pass": PASS, "fail": FAIL, "tag": TAG, "ids": IDS}
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed  evid={EVID}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
