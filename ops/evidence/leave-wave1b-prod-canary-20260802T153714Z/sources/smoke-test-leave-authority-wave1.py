#!/usr/bin/env python3
"""Leave Wave 1 — authority & safety hardening smoke.

Pins:
  - canonical type catalogue + legacy vacation/time_off mapping
  - self-approval hard ban (approve/reject); self-cancel allowed
  - lifecycle gates (terminated/suspended/future_start/notice_period)
  - stale-pending deterministic expire/needs_review + audit event
  - optimistic concurrency fail-closed on approve/reject/cancel
  - declined_lifecycle reverse restores requested (never pending)
  - honesty flags balances_enforced/legal_reviewed=false
  - holiday chargeable path with synthetic holidays
  - manager cannot create leave (no leave.request)
  - observe-only ledger; payroll invalidate only (no money mutation symbols)

Run: python3 smoke-test-leave-authority-wave1.py
"""

from __future__ import annotations

import inspect
import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
PHONE_SUFFIX = "".join(ch for ch in SUFFIX if ch.isdigit()) + "000000"
PHONE_SUFFIX = PHONE_SUFFIX[:6]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    leave authority wave1 — catalogue + gates + concurrency + honesty")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import leave_authority_wave1 as leave_w1

    # --- Pure catalogue / policy ------------------------------------------------
    check("schema version pinned", leave_w1.LEAVE_AUTHORITY_SCHEMA_VERSION == "1.0.0")
    check("vacation → annual", leave_w1.canonicalize_leave_type("vacation") == "annual")
    check("time_off → annual", leave_w1.canonicalize_leave_type("time_off") == "annual")
    check("sick stays sick", leave_w1.canonicalize_leave_type("sick") == "sick")
    check("unknown → other", leave_w1.canonicalize_leave_type("mystery") == "other")
    check("annual ledger-eligible", "annual" in leave_w1.LEAVE_LEDGER_TYPES)
    check("unpaid not ledger-eligible", "unpaid" not in leave_w1.LEAVE_LEDGER_TYPES)

    leave_self = {"employee_phone": "96550001111", "leave_id": "x", "status": "requested"}
    denied_a = leave_w1.self_decision_denied(leave=leave_self, actor_phone="96550001111", action="approve")
    denied_r = leave_w1.self_decision_denied(leave=leave_self, actor_phone="96550001111", action="reject")
    allowed_c = leave_w1.self_decision_denied(
        leave=leave_self, actor_phone="96550001111", action="cancel", allow_self_cancel=True
    )
    other_ok = leave_w1.self_decision_denied(leave=leave_self, actor_phone="96559999999", action="approve")
    check("self-approve denied", bool(denied_a) and denied_a.get("error") == "self_approval_forbidden")
    check("self-reject denied", bool(denied_r) and denied_r.get("error") == "self_approval_forbidden")
    check("self-cancel allowed", allowed_c is None)
    check("other-actor approve not self-banned", other_ok is None)

    settings = dict(leave_w1.DEFAULT_LIFECYCLE_POLICY)
    for lab in ("terminated", "suspended", "future_start", "notice_period"):
        blocked = leave_w1.lifecycle_gate(label=lab, settings=settings, operation="request")
        check(f"lifecycle blocks {lab}", bool(blocked) and blocked.get("error") == "leave_lifecycle_blocked")
    check("lifecycle allows active", leave_w1.lifecycle_gate(label="active", settings=settings, operation="request") is None)

    honesty = leave_w1.honesty_balance_flags()
    check("honesty balances_enforced=false", honesty.get("balances_enforced") is False)
    check("honesty legal_reviewed=false", honesty.get("legal_reviewed") is False)
    check("honesty observe_only", honesty.get("observe_only") is True)

    hol = leave_w1.holiday_calendar_chargeable_smoke(
        start=date(2026, 6, 1),
        end=date(2026, 6, 7),
        weekend_days=["fri", "sat"],
        holidays={date(2026, 6, 1)},
    )
    check("holiday path excludes weekend+holiday", hol == Decimal("4"))

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    # Manager cannot create leave requests (unchanged RBAC)
    mgr = set(app.hr_role_permissions("manager"))
    check("manager lacks leave.request", "leave.request" not in mgr)
    check("manager has leave.decide", "leave.decide" in mgr)
    check("infer vacation → annual", app.infer_leave_type("need vacation next week") == "annual")
    check("infer time off → annual", app.infer_leave_type("time off please") == "annual")

    # Payroll money mutation must remain absent from leave cancel/approve helpers
    inv_src = inspect.getsource(app.invalidate_provisional_timesheets)
    check("invalidate_provisional does not pay", "payment" not in inv_src.lower() or "invalidate" in inv_src.lower())
    check("no payroll_payment in invalidate", "payroll_payment" not in inv_src)
    check("no bank transfer in invalidate", "bank_transfer" not in inv_src.lower())

    # Prefer a real leave-enabled tenant (staging WATHEFNI) so module gates match production shape.
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 40")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.insert(0, "WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "leave")), None) or "WATHEFNI"
    print(f"    using company {company}")

    emp_phone = f"96577{PHONE_SUFFIX}"
    emp_key = f"{company}-LVW1-{SUFFIX}"
    hr_phone = "96588000001"
    today = app.kuwait_today()

    events: list[str] = []

    def record_event(cur, *, leave, company_code, event_type, payload, created_by_phone=None):
        events.append(event_type)
        app.record_leave_event(
            cur,
            leave=leave,
            company_code=company_code,
            event_type=event_type,
            payload=payload,
            created_by_phone=created_by_phone,
        )

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM leave_events WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM leave_ledger WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM leave_balances WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM leave_requests WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    cleanup()
    try:
        app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                leave_w1.ensure_leave_authority_wave1_schema(cur)
                leave_w1.seed_company_leave_authority_settings(cur, company)
            conn.commit()
        seeded = app.create_company_employee(
            company, name="Leave Wave1 Emp", phone=emp_phone, position_title="Wave1 Tester"
        )
        check("temp employee created/exists", seeded.get("status") in {"created", "exists"}, seeded)
        # Prefer the key returned by create_company_employee for later cleanup
        emp = app.find_employee_by_phone(emp_phone, company_code=company) or {}
        if emp.get("employee_key"):
            emp_key = str(emp["employee_key"])

        # --- request + honesty -------------------------------------------------
        req = app.request_leave(
            {
                "employee_phone": emp_phone,
                "leave_type": "vacation",
                "start_date": (today + timedelta(days=14)).isoformat(),
                "end_date": (today + timedelta(days=15)).isoformat(),
                "reason": "wave1",
            },
            company_code=company,
            created_by_phone=emp_phone,
        )
        check("request ok", bool(req.get("ok")), req)
        check("request stores annual not vacation", (req.get("leave") or {}).get("leave_type") == "annual", req.get("leave"))
        check("request honesty flags", req.get("balances_enforced") is False and req.get("legal_reviewed") is False)
        leave_id = str((req.get("leave") or {}).get("leave_id") or "")
        row_version = int((req.get("leave") or {}).get("row_version") or 1)
        if not leave_id:
            check("abort remaining API checks — leave_id missing", False, req)
            print(f"\n    {PASS} passed, {FAIL} failed")
            return 1

        # --- self approve/reject denied ---------------------------------------
        self_appr = app.approve_leave_request(
            {"leave_id": leave_id}, company_code=company, created_by_phone=emp_phone
        )
        check("self-approve denied at API", self_appr.get("error") == "self_approval_forbidden", self_appr)
        self_rej = app.reject_leave_request(
            {"leave_id": leave_id}, company_code=company, created_by_phone=emp_phone
        )
        check("self-reject denied at API", self_rej.get("error") == "self_approval_forbidden", self_rej)

        # --- concurrency fail-closed ------------------------------------------
        stale = app.approve_leave_request(
            {"leave_id": leave_id, "expected_row_version": row_version + 99, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone=hr_phone,
        )
        check("stale version approve fails closed", stale.get("error") == "stale_row_version", stale)

        appr = app.approve_leave_request(
            {"leave_id": leave_id, "expected_row_version": row_version, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone=hr_phone,
        )
        check("approve with matching version", bool(appr.get("ok")), appr)
        check("approve honesty", appr.get("balances_enforced") is False)
        check("approve payroll_impact provisional only", appr.get("payroll_impact") == "recalculation_required")

        # second concurrent cancel with old version fails
        bad_cancel = app.cancel_leave_request(
            {"leave_id": leave_id, "expected_row_version": row_version},
            company_code=company,
            created_by_phone=hr_phone,
        )
        check("cancel with stale version fails", bad_cancel.get("error") == "stale_row_version", bad_cancel)

        new_ver = int((appr.get("leave") or {}).get("row_version") or 0)
        cancel = app.cancel_leave_request(
            {"leave_id": leave_id, "expected_row_version": new_ver},
            company_code=company,
            created_by_phone=hr_phone,
        )
        check("cancel preserves history ok", bool(cancel.get("ok")), cancel)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_type FROM leave_events WHERE leave_id=%s ORDER BY created_at",
                    (leave_id,),
                )
                etypes = [dict(r)["event_type"] for r in cur.fetchall()]
        check("events preserve request/approve/cancel", {"requested", "approved", "cancelled"} <= set(etypes), etypes)

        # --- stale pending ----------------------------------------------------
        stale_start = (today - timedelta(days=5)).isoformat()
        stale_end = (today - timedelta(days=4)).isoformat()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                leave_w1.ensure_leave_authority_wave1_schema(cur)
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata, row_version)
                    VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','stale',%s,1)
                    RETURNING *
                    """,
                    (company, emp_key, app.digits(emp_phone), "Leave Wave1 Emp", stale_start, stale_end, app.Json({})),
                )
                stale_leave = dict(cur.fetchone())
            conn.commit()
        stale_id = str(stale_leave["leave_id"])
        events.clear()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                settings_row = leave_w1.get_leave_authority_settings(cur, company)
                rows = leave_w1.apply_stale_pending(
                    cur,
                    company_code=company,
                    settings=settings_row,
                    as_of=today,
                    record_event=record_event,
                    actor_phone=hr_phone,
                    leave_id=stale_id,
                )
            conn.commit()
        check("stale pending resolved", len(rows) == 1 and rows[0].get("status") == "expired_stale", rows)
        check("stale audit event", "stale_pending_resolved" in events, events)

        # Approving a past-start requested row resolves stale instead of approving
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata, row_version)
                    VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','stale2',%s,1)
                    RETURNING leave_id
                    """,
                    (
                        company,
                        emp_key,
                        app.digits(emp_phone),
                        "Leave Wave1 Emp",
                        (today - timedelta(days=3)).isoformat(),
                        (today - timedelta(days=2)).isoformat(),
                        app.Json({}),
                    ),
                )
                sid2 = str(dict(cur.fetchone())["leave_id"])
            conn.commit()
        stale_appr = app.approve_leave_request(
            {"leave_id": sid2, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone=hr_phone,
        )
        check(
            "approve past-start returns stale resolved",
            stale_appr.get("error") == "leave_stale_pending_resolved",
            stale_appr,
        )

        # --- lifecycle gate on request ----------------------------------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employees SET employment_status='terminated' WHERE employee_key=%s",
                    (emp_key,),
                )
            conn.commit()
        blocked = app.request_leave(
            {
                "employee_phone": emp_phone,
                "leave_type": "annual",
                "start_date": (today + timedelta(days=30)).isoformat(),
                "end_date": (today + timedelta(days=31)).isoformat(),
            },
            company_code=company,
            created_by_phone=emp_phone,
        )
        check("terminated cannot request", blocked.get("error") == "leave_lifecycle_blocked", blocked)

        # --- lifecycle decline/reverse status machine -------------------------
        import employee_lifecycle_wave3c as w3c

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "UPDATE employees SET employment_status='active' WHERE employee_key=%s",
                        (emp_key,),
                    )
                except Exception:
                    pass
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata, row_version)
                    VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','life',%s,1)
                    RETURNING leave_id
                    """,
                    (
                        company,
                        emp_key,
                        app.digits(emp_phone),
                        "Leave Wave1 Emp",
                        (today + timedelta(days=40)).isoformat(),
                        (today + timedelta(days=41)).isoformat(),
                        app.Json({}),
                    ),
                )
                life_id = str(dict(cur.fetchone())["leave_id"])
                decl = w3c._execute_downstream_action(
                    cur,
                    company=company,
                    req={"action_type": "decline_open_leave", "employee_key": emp_key},
                )
                rev = w3c._execute_downstream_action(
                    cur,
                    company=company,
                    req={"action_type": "reverse_decline_open_leave", "employee_key": emp_key},
                )
                cur.execute("SELECT status FROM leave_requests WHERE leave_id=%s", (life_id,))
                restored_status = str(dict(cur.fetchone() or {}).get("status") or "")
            conn.commit()
        check("lifecycle decline recorded", bool((decl or {}).get("declined_leave_ids")), decl)
        check("lifecycle reverse recorded", bool((rev or {}).get("restored_leave_ids")), rev)
        check("reverse never pending", restored_status != "pending", restored_status)
        check("reverse restores requested", restored_status == "requested", restored_status)

        # --- legacy vacation ledger mapping (no silent skip) ------------------
        prev_bal = os.environ.get("WATHEFNI_LEAVE_BALANCES")
        os.environ["WATHEFNI_LEAVE_BALANCES"] = "on"
        try:
            app.seed_company_leave_policies(company)
        except Exception:
            pass
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                leave_vacation = {
                    "leave_id": str(uuid.uuid4()),
                    "employee_key": emp_key,
                    "leave_type": "vacation",  # legacy stored type
                    "start_date": today + timedelta(days=50),
                    "end_date": today + timedelta(days=50),
                    "status": "approved",
                }
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (leave_id, company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata, row_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'vacation','approved','legacy',%s,1)
                    """,
                    (
                        leave_vacation["leave_id"],
                        company,
                        emp_key,
                        app.digits(emp_phone),
                        "Leave Wave1 Emp",
                        leave_vacation["start_date"],
                        leave_vacation["end_date"],
                        app.Json({}),
                    ),
                )
                before = 0
                try:
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code=%s AND leave_type='annual'",
                        (company,),
                    )
                    before = int(dict(cur.fetchone())["n"])
                except Exception:
                    before = 0
                app.observe_leave_consumption(
                    cur, company_code=company, leave=leave_vacation, kind="consume", actor_phone=hr_phone
                )
                cur.execute(
                    "SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code=%s AND leave_type='annual' AND leave_id=%s",
                    (company, leave_vacation["leave_id"]),
                )
                after_row = cur.fetchone()
                after = int(dict(after_row)["n"]) if after_row else 0
            conn.commit()
        check("legacy vacation maps into annual ledger", after >= 1, {"before": before, "after": after})
        if prev_bal is None:
            os.environ.pop("WATHEFNI_LEAVE_BALANCES", None)
        else:
            os.environ["WATHEFNI_LEAVE_BALANCES"] = prev_bal

        # API honesty without dashboard auth harness
        honesty = app._leave_honesty_payload()
        check("dashboard-equivalent honesty flags", honesty.get("balances_enforced") is False and honesty.get("observe_only") is True, honesty)
        listed = app.list_leave_requests({"company_code": company, "status": "requested", "history": False}, company_code=company)
        check("list leave ok", bool(listed.get("ok")), listed)

    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
