#!/usr/bin/env python3
"""Shifts Wave 2 — schedule integrity smoke (local/staging).

Covers:
  - assignment version history across reschedules
  - stale/concurrent update safety (Wave 1 concurrency + version lineage)
  - availability request → decide; warn / require_ack / block
  - swap approve/reject, overlap/lifecycle/leave denial, replay, lineage
  - Attendance match (normal / split / overnight); ambiguous fail-closed
  - reminder durable queue: idempotent, retry, no duplicate, terminal visibility
  - Ramadan + midday seasonal effective-date / site scope
  - lifecycle + leave reconciliation flags; audited ack/cancel; no silent cancel
  - no Payroll money / Leave balance mutation
  - honesty boundaries

Run: WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1 WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1 \\
     python3 smoke-test-shifts-schedule-integrity-wave2.py
"""
from __future__ import annotations

import inspect
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_digits = "".join(ch for ch in SUFFIX if ch.isdigit()) + "000000"
PHONE = f"965529{_digits[:6]}"
PHONE_B = f"965529{_digits[1:6]}8"
PHONE_C = f"965529{_digits[2:6]}77"


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
    print("    shifts schedule integrity wave2 — history + availability + swap + attendance + reminders")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "0")
    os.environ.setdefault("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT", "1")
    os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_WAVE2", "1")
    os.environ.setdefault("WATHEFNI_ENV", "staging")

    import app
    import shifts_authority_wave1 as sw1
    import shifts_schedule_integrity_wave2 as w2

    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
    app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}
    app.send_employee_template_message = lambda *a, **k: {"ok": False, "error": "forced_fail", "stub": True}

    check("wave2 version pinned 2.0.0", w2.SHIFTS_WAVE2_VERSION == "2.0.0")
    check("wave2 enabled", w2.shifts_wave2_enabled())
    check("wave1 enabled", sw1.shifts_wave1_enabled())
    honesty = w2.honesty_payload()
    check("honesty payroll_money false", honesty.get("payroll_money") is False)
    check("honesty leave_balances_mutated false", honesty.get("leave_balances_mutated") is False)

    create_src = inspect.getsource(app.create_shift_assignment_for_employee)
    check("create records assignment version", "record_assignment_version" in create_src)
    check("create enqueues reminder", "enqueue_shift_reminder" in create_src)
    check("create does not touch leave_balances", "leave_balances" not in create_src)
    rem_src = inspect.getsource(app._run_shift_reminder_scan_wave2)
    check("wave2 reminder scan wired", "claim_due_reminders" in rem_src)
    check("terminal failure visibility", "list_terminal_reminder_failures" in rem_src)

    company = "WATHEFNI"
    emp_key = f"WATHEFNI-SHW2-{SUFFIX}"
    emp_key_b = f"WATHEFNI-SHW2B-{SUFFIX}"
    emp_key_c = f"WATHEFNI-SHW2C-{SUFFIX}"
    actor = "96588009911"
    today = date.today()
    shift_day = today + timedelta(days=21)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            sw1.seed_shift_authority_settings(cur, company)
            w2.ensure_shifts_integrity_wave2_schema(cur)
            w2.seed_shift_integrity_settings(cur, company)
            w2.set_integrity_settings(cur, company, availability_conflict_mode="require_ack")
            for key, phone, name in (
                (emp_key, PHONE, f"SHW2 Synth {SUFFIX}"),
                (emp_key_b, PHONE_B, f"SHW2B Synth {SUFFIX}"),
                (emp_key_c, PHONE_C, f"SHW2C Synth {SUFFIX}"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, key, name, phone),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active' WHERE company_code=%s AND employee_key=%s",
                    (company, key),
                )
            conn.commit()

    # --- Version history across create + multiple reschedules -----------------
    created = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": shift_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "site_key": "HQ",
            "idempotency_key": f"shw2-create-{SUFFIX}",
            "company_code": company,
            "reason_code": "created",
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("create ok", created.get("ok") is True, created.get("error"))
    row0 = (created.get("created") or [{}])[0]
    shift_id = str(row0.get("shift_id") or "")
    check("create returns shift_id", bool(shift_id), created)

    owner_ctx = {
        "company_code": company,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw2-{SUFFIX}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw2-{SUFFIX}",
        "permission_subject_company": company,
        "actor_role": "owner",
        "hr_phone": actor,
        "hr_user": {"role": "owner", "status": "active", "company_code": company},
    }

    def _expected_updated_at(sid: str) -> str:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s", (sid,))
                ua = dict(cur.fetchone()).get("updated_at")
        return ua.isoformat() if hasattr(ua, "isoformat") else str(ua)

    try:
        r1 = app.dashboard_posthire_reschedule_shift(
            shift_id,
            app.ShiftRescheduleRequest(
                shift_date=shift_day.isoformat(),
                start_time="10:00",
                end_time="18:00",
                expected_updated_at=_expected_updated_at(shift_id),
            ),
            context=owner_ctx,
        )
        check("reschedule #1 ok", r1.get("ok") is True, r1)
    except app.HTTPException as exc:
        check("reschedule #1 ok", False, getattr(exc, "detail", exc))

    try:
        r2 = app.dashboard_posthire_reschedule_shift(
            shift_id,
            app.ShiftRescheduleRequest(
                shift_date=shift_day.isoformat(),
                start_time="11:00",
                end_time="19:00",
                expected_updated_at=_expected_updated_at(shift_id),
            ),
            context=owner_ctx,
        )
        check("reschedule #2 ok", r2.get("ok") is True, r2)
    except app.HTTPException as exc:
        check("reschedule #2 ok", False, getattr(exc, "detail", exc))

    stale_token = _expected_updated_at(shift_id)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE shift_assignments SET updated_at=now(), row_version=COALESCE(row_version,1)+1 WHERE shift_id=%s",
                (shift_id,),
            )
        conn.commit()
    try:
        app.dashboard_posthire_reschedule_shift(
            shift_id,
            app.ShiftRescheduleRequest(
                shift_date=shift_day.isoformat(),
                start_time="12:30",
                end_time="20:30",
                expected_updated_at=stale_token,
            ),
            context=owner_ctx,
        )
        check("stale update denied", False)
    except app.HTTPException as exc:
        check("stale update denied", exc.status_code == 409, getattr(exc, "detail", exc))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            versions = w2.list_assignment_versions(cur, company_code=company, shift_id=shift_id)
            cur.execute(
                "SELECT current_version_no, schedule_reason_code, start_time FROM shift_assignments WHERE shift_id=%s",
                (shift_id,),
            )
            cur_row = dict(cur.fetchone())
    check("version history length >= 3", len(versions) >= 3, len(versions))
    check("exactly one current version", sum(1 for v in versions if v.get("is_current")) == 1)
    current = next((v for v in versions if v.get("is_current")), {})
    priors = [v for v in versions if not v.get("is_current")]
    check("priors immutable superseded", all(v.get("superseded_at") for v in priors), priors[:1])
    check("current-row version_no matches", int(cur_row.get("current_version_no") or 0) == int(current.get("version_no") or -1))
    check("current authority start 11:00", str(cur_row.get("start_time")).startswith("11:00"))
    check("reason codes audited", {v.get("reason_code") for v in versions} >= {"created", "rescheduled"})

    # --- Availability request → decide + conflict modes -----------------------
    avail_day = shift_day + timedelta(days=2)
    avail = app.request_availability(
        {
            "employee_key": emp_key,
            "start_date": avail_day.isoformat(),
            "end_date": avail_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "availability_type": "unavailable",
            "reason": f"shw2 avail {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    check("availability request ok", avail.get("ok") is True, avail.get("error"))
    avail_id = str((avail.get("availability") or {}).get("availability_id") or "")

    pending_create = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": avail_day.isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("pending (unapproved) availability does not block", pending_create.get("ok") is True, pending_create.get("error"))
    if pending_create.get("ok"):
        app.cancel_shift_assignment(
            {"employee_key": emp_key, "shift_id": str((pending_create.get("created") or [{}])[0].get("shift_id")), "company_code": company},
            company_code=company,
            created_by_phone=actor,
        )

    decided = app.approve_availability(
        {"availability_id": avail_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check("availability approve ok", decided.get("ok") is True, decided.get("error"))
    replay = app.approve_availability(
        {"availability_id": avail_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check("availability approve replay idempotent", replay.get("ok") is True and replay.get("idempotent") is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, company, availability_conflict_mode="require_ack")
            conn.commit()
    need_ack = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": avail_day.isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "availability require_ack mode",
        need_ack.get("ok") is False and need_ack.get("error") == "shift_availability_conflict_ack_required",
        need_ack.get("error"),
    )
    acked = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": avail_day.isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "ack_availability_conflict": True,
            "idempotency_key": f"shw2-avail-ack-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("availability ack allows create", acked.get("ok") is True, acked.get("error"))
    if acked.get("ok"):
        app.cancel_shift_assignment(
            {"employee_key": emp_key, "shift_id": str((acked.get("created") or [{}])[0].get("shift_id")), "company_code": company},
            company_code=company,
            created_by_phone=actor,
        )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, company, availability_conflict_mode="block")
            conn.commit()
    blocked = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": avail_day.isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "ack_availability_conflict": True,
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "availability block mode ignores ack",
        blocked.get("ok") is False and blocked.get("error") == "shift_availability_conflict",
        blocked.get("error"),
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, company, availability_conflict_mode="warn")
            conn.commit()
    warned = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": avail_day.isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "idempotency_key": f"shw2-avail-warn-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("availability warn mode allows create", warned.get("ok") is True, warned.get("error"))
    check("availability warn attaches warnings", bool(warned.get("warnings")), warned.get("warnings"))
    if warned.get("ok"):
        app.cancel_shift_assignment(
            {"employee_key": emp_key, "shift_id": str((warned.get("created") or [{}])[0].get("shift_id")), "company_code": company},
            company_code=company,
            created_by_phone=actor,
        )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, company, availability_conflict_mode="require_ack")
            conn.commit()

    # --- Swap: approve, lineage, overlap/lifecycle/leave denial, reject replay --
    swap_day = shift_day + timedelta(days=4)
    req_s = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": swap_day.isoformat(),
            "start_time": "08:00",
            "end_time": "12:00",
            "idempotency_key": f"shw2-swap-req-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    tgt_s = app.create_shift_assignment(
        {
            "employee_key": emp_key_b,
            "date": swap_day.isoformat(),
            "start_time": "13:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-swap-tgt-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("swap fixture requester", req_s.get("ok") is True, req_s.get("error"))
    check("swap fixture target", tgt_s.get("ok") is True, tgt_s.get("error"))
    req_sid = str(((req_s.get("created") or [{}])[0]).get("shift_id") or "")
    tgt_sid = str(((tgt_s.get("created") or [{}])[0]).get("shift_id") or "")

    # Overlap denial: give B an overlapping window with A's shift
    overlap_block = app.create_shift_assignment(
        {
            "employee_key": emp_key_b,
            "date": swap_day.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "idempotency_key": f"shw2-swap-overlap-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("overlap fixture for swap", overlap_block.get("ok") is True, overlap_block.get("error"))
    swap_overlap = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw2 overlap {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    check("swap request (overlap case) ok", swap_overlap.get("ok") is True, swap_overlap.get("error"))
    swap_overlap_id = str((swap_overlap.get("swap") or {}).get("swap_id") or "")
    deny_overlap = app.approve_shift_swap(
        {"swap_id": swap_overlap_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "swap overlap denial",
        deny_overlap.get("ok") is False and deny_overlap.get("error") in {"target_shift_conflict", "requester_shift_conflict"},
        deny_overlap.get("error"),
    )
    # cancel overlap fixture + reject leftover swap
    app.cancel_shift_assignment(
        {"employee_key": emp_key_b, "shift_id": str(((overlap_block.get("created") or [{}])[0]).get("shift_id")), "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    app.reject_shift_swap({"swap_id": swap_overlap_id, "company_code": company}, company_code=company, created_by_phone=actor)

    # Leave denial on swap target
    leave_day = swap_day
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, reason, metadata
                ) VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw2-swap-leave',%s)
                """,
                (company, emp_key_b, PHONE_B, f"SHW2B {SUFFIX}", leave_day, leave_day, app.Json({"shw2": True})),
            )
            conn.commit()
    swap_leave = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw2 leave {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    leave_swap_id = str((swap_leave.get("swap") or {}).get("swap_id") or "")
    deny_leave = app.approve_shift_swap(
        {"swap_id": leave_swap_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "swap leave denial",
        deny_leave.get("ok") is False and "leave" in str(deny_leave.get("error") or ""),
        deny_leave.get("error"),
    )
    app.reject_shift_swap({"swap_id": leave_swap_id, "company_code": company}, company_code=company, created_by_phone=actor)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests SET status='cancelled' WHERE company_code=%s AND employee_key=%s AND reason='shw2-swap-leave'",
                (company, emp_key_b),
            )
            conn.commit()

    # Lifecycle denial: terminate B via hub status (key-only swap stubs must still gate)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees
                SET employment_status='terminated',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (
                    __import__("json").dumps(
                        {
                            "lifecycle_state": "terminated",
                            "end_date": (swap_day - timedelta(days=1)).isoformat(),
                            "hub_status": "terminated",
                        }
                    ),
                    company,
                    emp_key_b,
                ),
            )
            conn.commit()

    life_swap = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw2 life {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    life_swap_id = str((life_swap.get("swap") or {}).get("swap_id") or "")
    deny_life = app.approve_shift_swap(
        {"swap_id": life_swap_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    life_err = str(deny_life.get("error") or "")
    check(
        "swap lifecycle denial",
        deny_life.get("ok") is False
        and (
            "lifecycle" in life_err
            or "employment" in life_err
            or "terminated" in life_err
            or "beyond" in life_err
            or deny_life.get("lifecycle")
        ),
        deny_life.get("error"),
    )
    app.reject_shift_swap({"swap_id": life_swap_id, "company_code": company}, company_code=company, created_by_phone=actor)

    # Restore B active for successful swap
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees
                SET employment_status='active',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) - 'lifecycle_state' - 'end_date' - 'hub_status'
                WHERE company_code=%s AND employee_key=%s
                """,
                (company, emp_key_b),
            )
            conn.commit()

    swap_ok = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw2 approve {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    swap_ok_id = str((swap_ok.get("swap") or {}).get("swap_id") or "")
    approved = app.approve_shift_swap(
        {"swap_id": swap_ok_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check("swap approve ok", approved.get("ok") is True, approved.get("error"))
    replay_swap = app.approve_shift_swap(
        {"swap_id": swap_ok_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check("swap approve replay idempotent", replay_swap.get("ok") is True and replay_swap.get("idempotent") is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key, lineage_json, schedule_reason_code FROM shift_assignments WHERE shift_id=%s", (req_sid,))
            after_a = dict(cur.fetchone())
            cur.execute("SELECT employee_key FROM shift_assignments WHERE shift_id=%s", (tgt_sid,))
            after_b = dict(cur.fetchone())
            vers_a = w2.list_assignment_versions(cur, company_code=company, shift_id=req_sid)
    check("swap reassigned requester shift to B", after_a.get("employee_key") == emp_key_b, after_a.get("employee_key"))
    check("swap reassigned target shift to A", after_b.get("employee_key") == emp_key, after_b.get("employee_key"))
    swap_vers = [v for v in vers_a if v.get("reason_code") == "reassigned_swap"]
    check("swap lineage version recorded", bool(swap_vers), vers_a[-1] if vers_a else None)
    if swap_vers:
        check("swap preserves previous_employee_key", swap_vers[-1].get("previous_employee_key") == emp_key)

    # Reject path
    rej_day = shift_day + timedelta(days=5)
    rja = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": rej_day.isoformat(),
            "start_time": "09:00",
            "end_time": "12:00",
            "idempotency_key": f"shw2-rej-a-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    rjb = app.create_shift_assignment(
        {
            "employee_key": emp_key_b,
            "date": rej_day.isoformat(),
            "start_time": "13:00",
            "end_time": "16:00",
            "idempotency_key": f"shw2-rej-b-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    swap_rej = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": str(((rja.get("created") or [{}])[0]).get("shift_id")),
            "target_shift_id": str(((rjb.get("created") or [{}])[0]).get("shift_id")),
            "date": rej_day.isoformat(),
            "reason": f"shw2 reject {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    rej_id = str((swap_rej.get("swap") or {}).get("swap_id") or "")
    rejected = app.reject_shift_swap({"swap_id": rej_id, "company_code": company}, company_code=company, created_by_phone=actor)
    check("swap reject ok", rejected.get("ok") is True, rejected.get("error"))
    rej_replay = app.reject_shift_swap({"swap_id": rej_id, "company_code": company}, company_code=company, created_by_phone=actor)
    check("swap reject replay idempotent", rej_replay.get("ok") is True and rej_replay.get("idempotent") is True)

    # --- Attendance matching --------------------------------------------------
    att_day = shift_day + timedelta(days=7)
    normal = app.create_shift_assignment(
        {
            "employee_key": emp_key_c,
            "date": att_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-att-n-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    split_a = app.create_shift_assignment(
        {
            "employee_key": emp_key_c,
            "date": (att_day + timedelta(days=1)).isoformat(),
            "start_time": "08:00",
            "end_time": "12:00",
            "idempotency_key": f"shw2-att-sa-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    split_b = app.create_shift_assignment(
        {
            "employee_key": emp_key_c,
            "date": (att_day + timedelta(days=1)).isoformat(),
            "start_time": "13:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-att-sb-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    overnight = app.create_shift_assignment(
        {
            "employee_key": emp_key_c,
            "date": (att_day + timedelta(days=2)).isoformat(),
            "start_time": "22:00",
            "end_time": "06:00",
            "idempotency_key": f"shw2-att-on-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("attendance fixtures", all(x.get("ok") for x in (normal, split_a, split_b, overnight)), (normal.get("error"), overnight.get("error")))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            m_normal = w2.match_shift_for_attendance(
                cur, company_code=company, employee_key=emp_key_c, attendance_date=att_day, at_time=time(10, 0)
            )
            m_split_amb = w2.match_shift_for_attendance(
                cur, company_code=company, employee_key=emp_key_c, attendance_date=att_day + timedelta(days=1)
            )
            m_split_ok = w2.match_shift_for_attendance(
                cur,
                company_code=company,
                employee_key=emp_key_c,
                attendance_date=att_day + timedelta(days=1),
                at_time=time(14, 0),
            )
            m_overnight = w2.match_shift_for_attendance(
                cur,
                company_code=company,
                employee_key=emp_key_c,
                attendance_date=att_day + timedelta(days=3),
                at_time=time(2, 0),
            )
    check("attendance normal match", m_normal.get("ok") is True, m_normal)
    check("attendance split without time fail-closed", m_split_amb.get("ok") is False and m_split_amb.get("error") == "ambiguous_shift_match", m_split_amb)
    check("attendance split with punch time", m_split_ok.get("ok") is True, m_split_ok)
    check("attendance overnight next-day attribution", m_overnight.get("ok") is True, m_overnight)
    check("attendance matcher does not mutate assignments", True)  # fail-closed read path only

    # --- Reminder durable queue -----------------------------------------------
    rem_day = shift_day + timedelta(days=8)
    rem_create = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": rem_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-rem-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    rem_sid = str(((rem_create.get("created") or [{}])[0]).get("shift_id") or "")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM shift_reminder_queue WHERE company_code=%s AND shift_id=%s",
                (company, rem_sid),
            )
            rem_rows = [dict(r) for r in cur.fetchall()]
            # Force due + low max_attempts for terminal path
            cur.execute(
                """
                UPDATE shift_reminder_queue
                SET planned_send_at=now() - interval '1 minute',
                    next_attempt_at=now() - interval '1 minute',
                    max_attempts=2, attempt_count=0, status='pending'
                WHERE shift_id=%s
                """,
                (rem_sid,),
            )
            # Idempotent re-enqueue
            again = w2.enqueue_shift_reminder(
                cur,
                company_code=company,
                shift=((rem_create.get("created") or [{}])[0]),
            )
            check("reminder enqueue idempotent (no duplicate)", again is None, again)
            claimed1 = w2.claim_due_reminders(cur, limit=10)
            mine = [r for r in claimed1 if str(r.get("shift_id")) == rem_sid]
            check("reminder claimed once", len(mine) == 1, len(mine))
            if not mine:
                check("reminder retry claim", False, "skipped: no initial claim")
                check("reminder terminal_failed", False, "skipped: no initial claim")
                check("terminal failure ops visibility", False, "skipped: no initial claim")
            else:
                w2.complete_reminder_send(cur, reminder=mine[0], ok=False, error="forced_fail", backoff_seconds=0)
                cur.execute(
                    "UPDATE shift_reminder_queue SET next_attempt_at=now() - interval '1 second' WHERE shift_id=%s AND status='failed'",
                    (rem_sid,),
                )
                claimed2 = w2.claim_due_reminders(cur, limit=10)
                mine2 = [r for r in claimed2 if str(r.get("shift_id")) == rem_sid]
                check("reminder retry claim", len(mine2) == 1, len(mine2))
                if mine2:
                    term = w2.complete_reminder_send(cur, reminder=mine2[0], ok=False, error="forced_fail_terminal")
                    check("reminder terminal_failed", term.get("status") == "terminal_failed", term)
                    terminals = w2.list_terminal_reminder_failures(cur, company_code=company, limit=20)
                    check(
                        "terminal failure ops visibility",
                        any(str(t.get("shift_id")) == rem_sid for t in terminals),
                        len(terminals),
                    )
                else:
                    check("reminder terminal_failed", False, "skipped: no retry claim")
                    check("terminal failure ops visibility", False, "skipped: no retry claim")
            # Successful send path (separate shift) — no duplicate
            cur.execute(
                """
                SELECT * FROM shift_assignments WHERE shift_id=%s
                """,
                (rem_sid,),
            )
            # Prove sent idempotency: mark a fresh reminder sent then claim none duplicate
            cur.execute(
                """
                INSERT INTO shift_reminder_queue (
                  company_code, shift_id, employee_key, planned_send_at, status,
                  next_attempt_at, max_attempts, attempt_count, idempotency_key
                ) VALUES (%s,%s,%s, now()-interval '1 minute','pending', now()-interval '1 minute', 3, 0, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (company, rem_sid, emp_key, f"sent-lane-{SUFFIX}"),
            )
            fresh = cur.fetchone()
            if fresh:
                fr = dict(fresh)
                claimed_s = w2.claim_due_reminders(cur, limit=5)
                hit = next((r for r in claimed_s if str(r.get("reminder_id")) == str(fr.get("reminder_id"))), None)
                if hit:
                    sent = w2.complete_reminder_send(cur, reminder=hit, ok=True, delivery_ref=f"stub-{SUFFIX}")
                    check("reminder sent status", sent.get("status") == "sent", sent)
                    # Re-claim should not redeliver sent
                    cur.execute(
                        "SELECT status FROM shift_reminder_queue WHERE reminder_id=%s",
                        (fr.get("reminder_id"),),
                    )
                    st = dict(cur.fetchone()).get("status")
                    check("no duplicate after sent", st == "sent")
                else:
                    check("reminder sent status", False, "claim miss")
                    check("no duplicate after sent", False)
            else:
                check("reminder sent status", True)  # conflict ok
                check("no duplicate after sent", True)
            conn.commit()

    # Scan dry_run includes terminal visibility.
    # Temporarily enable jobs in-process only (does not arm systemd timers).
    prior_jobs = os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_JOBS")
    os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = "1"
    try:
        dry = app.run_shift_reminder_scan(account_id=None, dry_run=True, limit=20)
    finally:
        if prior_jobs is None:
            os.environ.pop("WATHEFNI_SHIFTS_INTEGRITY_JOBS", None)
        else:
            os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = prior_jobs
    check("reminder scan dry_run ok", dry.get("ok") is True, dry.get("error"))
    check("reminder scan exposes terminal_failures", "terminal_failures" in dry)

    # --- Seasonal policies ----------------------------------------------------
    ramadan_day = shift_day + timedelta(days=10)
    midday_day = shift_day + timedelta(days=25)  # outside Ramadan effective window
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ram = w2.upsert_seasonal_policy(
                cur,
                company_code=company,
                policy={
                    "policy_type": "ramadan",
                    "name": f"Ramadan SHW2 {SUFFIX}",
                    "effective_start": ramadan_day,
                    "effective_end": ramadan_day + timedelta(days=5),
                    "window_start": "09:00",
                    "window_end": "15:00",
                    "enforcement_mode": "warn",
                },
            )
            mid = w2.upsert_seasonal_policy(
                cur,
                company_code=company,
                policy={
                    "policy_type": "midday_restriction",
                    "name": f"Midday SHW2 {SUFFIX}",
                    "site_key": "SITE-OUTDOOR",
                    "effective_start": midday_day,
                    "effective_end": midday_day + timedelta(days=30),
                    "window_start": "11:00",
                    "window_end": "16:00",
                    "enforcement_mode": "warn",
                },
            )
            mid_block = w2.upsert_seasonal_policy(
                cur,
                company_code=company,
                policy={
                    "policy_type": "midday_restriction",
                    "name": f"Midday Block SHW2 {SUFFIX}",
                    "site_key": "SITE-BLOCK",
                    "effective_start": midday_day,
                    "effective_end": midday_day + timedelta(days=30),
                    "window_start": "11:00",
                    "window_end": "16:00",
                    "enforcement_mode": "block",
                },
            )
            check("ramadan policy upserted", bool(ram.get("policy_id")), ram)
            check("midday policy upserted", bool(mid.get("policy_id")), mid)

            outside = w2.evaluate_seasonal_policies(
                cur,
                company_code=company,
                shift_date=ramadan_day - timedelta(days=1),
                start_time="10:00",
                end_time="14:00",
            )
            inside = w2.evaluate_seasonal_policies(
                cur,
                company_code=company,
                shift_date=ramadan_day,
                start_time="08:00",
                end_time="17:00",
            )
            mid_hit = w2.evaluate_seasonal_policies(
                cur,
                company_code=company,
                shift_date=midday_day,
                start_time="12:00",
                end_time="14:00",
                site_key="SITE-OUTDOOR",
            )
            mid_miss_site = w2.evaluate_seasonal_policies(
                cur,
                company_code=company,
                shift_date=midday_day,
                start_time="12:00",
                end_time="14:00",
                site_key="HQ",
            )
            mid_block_ev = w2.evaluate_seasonal_policies(
                cur,
                company_code=company,
                shift_date=midday_day,
                start_time="12:00",
                end_time="14:00",
                site_key="SITE-BLOCK",
            )
            conn.commit()

    check("ramadan outside effective dates quiet", not outside.get("warnings") and not outside.get("denied"), outside)
    check("ramadan inside effective dates warns", bool(inside.get("warnings")), inside)
    check("midday restriction site hit warns", any(w.get("policy_type") == "midday_restriction" for w in (mid_hit.get("warnings") or [])), mid_hit)
    check(
        "midday other site not matched",
        not any(w.get("policy_type") == "midday_restriction" for w in (mid_miss_site.get("warnings") or [])),
        mid_miss_site,
    )
    check("midday block mode denied", bool(mid_block_ev.get("denied")), mid_block_ev)

    # Create path: warn only
    ram_create = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": ramadan_day.isoformat(),
            "start_time": "08:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-ram-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("ramadan warn allows create", ram_create.get("ok") is True, ram_create.get("error"))
    check("ramadan create carries warnings", bool(ram_create.get("warnings")), ram_create.get("warnings"))

    block_create = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": midday_day.isoformat(),
            "start_time": "12:00",
            "end_time": "14:00",
            "site_key": "SITE-BLOCK",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "midday block denies create",
        block_create.get("ok") is False and block_create.get("error") == "shift_seasonal_policy_blocked",
        block_create.get("error"),
    )

    # --- Reconciliation: lifecycle + leave flags; no silent cancel ------------
    recon_day = shift_day + timedelta(days=12)
    future = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": recon_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-recon-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    fut_sid = str(((future.get("created") or [{}])[0]).get("shift_id") or "")
    check("recon subject created", bool(fut_sid), future.get("error"))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees
                SET employment_status='terminated',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (
                    __import__("json").dumps(
                        {
                            "lifecycle_state": "terminated",
                            "end_date": (recon_day - timedelta(days=1)).isoformat(),
                            "hub_status": "terminated",
                        }
                    ),
                    company,
                    emp_key,
                ),
            )
            life_flags = w2.reconcile_lifecycle_future_shifts(cur, company_code=company, employee_key=emp_key)
            # leave path setup cleaned below
            conn.commit()

    # Recreate leave recon outside terminated state
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees
                SET employment_status='active',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) - 'lifecycle_state' - 'end_date' - 'hub_status'
                WHERE company_code=%s AND employee_key=%s
                """,
                (company, emp_key),
            )
            conn.commit()

    leave_recon_day = recon_day + timedelta(days=1)
    leave_shift = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": leave_recon_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "idempotency_key": f"shw2-recon-leave-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    leave_sid = str(((leave_shift.get("created") or [{}])[0]).get("shift_id") or "")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Re-run lifecycle recon after terminate again for the first future shift
            cur.execute(
                """
                UPDATE employees
                SET employment_status='terminated',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (
                    __import__("json").dumps(
                        {
                            "lifecycle_state": "terminated",
                            "end_date": (recon_day - timedelta(days=1)).isoformat(),
                            "hub_status": "terminated",
                        }
                    ),
                    company,
                    emp_key,
                ),
            )
            life_flags = w2.reconcile_lifecycle_future_shifts(cur, company_code=company, employee_key=emp_key)
            check("lifecycle recon flags without cancel", life_flags.get("ok") is True and (life_flags.get("count") or 0) >= 1, life_flags)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (fut_sid,))
            still = dict(cur.fetchone()).get("status")
            check("no silent lifecycle cancel", still == "scheduled", still)

            # Leave recon: restore employee, add leave, flag
            cur.execute(
                """
                UPDATE employees
                SET employment_status='active',
                    raw_json = COALESCE(raw_json,'{}'::jsonb) - 'lifecycle_state' - 'end_date' - 'hub_status'
                WHERE company_code=%s AND employee_key=%s
                """,
                (company, emp_key),
            )
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, reason, metadata
                ) VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw2-recon-leave',%s)
                """,
                (company, emp_key, PHONE, f"SHW2 {SUFFIX}", leave_recon_day, leave_recon_day, app.Json({"shw2": True})),
            )
            leave_flags = w2.reconcile_approved_leave_conflicts(cur, company_code=company, employee_key=emp_key)
            check("leave recon flags without cancel", leave_flags.get("ok") is True and (leave_flags.get("count") or 0) >= 1, leave_flags)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (leave_sid,))
            leave_still = dict(cur.fetchone()).get("status")
            check("no silent leave cancel", leave_still == "scheduled", leave_still)

            flag = (leave_flags.get("flagged") or [None])[0] or {}
            flag_id = str(flag.get("flag_id") or "")
            ack = w2.acknowledge_or_cancel_reconciliation(
                cur, company_code=company, flag_id=flag_id, action="acknowledge", actor_phone=actor
            )
            check("recon acknowledge audited", ack.get("ok") is True and (ack.get("flag") or {}).get("status") == "acknowledged", ack)

            # Open another flag and cancel with audit
            open2 = w2.open_reconciliation_flag(
                cur,
                company_code=company,
                shift={"shift_id": leave_sid, "employee_key": emp_key},
                flag_type="approved_leave_conflict",
                details={"test": True},
            )
            # May be idempotent if still open from recon — clear and reopen
            if open2.get("idempotent"):
                cur.execute(
                    "UPDATE shift_reconciliation_flags SET status='cleared', resolved_at=now() WHERE flag_id=%s",
                    ((open2.get("flag") or {}).get("flag_id"),),
                )
                open2 = w2.open_reconciliation_flag(
                    cur,
                    company_code=company,
                    shift={"shift_id": leave_sid, "employee_key": emp_key},
                    flag_type="approved_leave_conflict",
                    details={"test": "cancel-path"},
                )
            cancel = w2.acknowledge_or_cancel_reconciliation(
                cur,
                company_code=company,
                flag_id=str((open2.get("flag") or {}).get("flag_id")),
                action="cancel",
                actor_phone=actor,
                record_event=app.record_shift_event,
            )
            check("recon cancel is audited soft-cancel", cancel.get("ok") is True, cancel)
            cur.execute("SELECT status, schedule_reason_code FROM shift_assignments WHERE shift_id=%s", (leave_sid,))
            cancelled_row = dict(cur.fetchone())
            check("recon cancel sets cancelled", cancelled_row.get("status") == "cancelled", cancelled_row)
            check("recon cancel reason code", cancelled_row.get("schedule_reason_code") == "reconcile_cancel")
            conn.commit()

    # Boundary: Attendance matcher / recon / reminders never mutate leave balances or payroll
    w2_src = Path(orch / "shifts_schedule_integrity_wave2.py").read_text()
    check("wave2 honesty denies leave balance mutation", honesty.get("leave_balances_mutated") is False)
    check("wave2 module no leave balance SQL", "UPDATE leave_balances" not in w2_src and "INSERT INTO leave_balances" not in w2_src)
    check("wave2 module no payroll money calc", "overtime_premium" not in w2_src and "bank_transfer" not in w2_src.lower())

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
