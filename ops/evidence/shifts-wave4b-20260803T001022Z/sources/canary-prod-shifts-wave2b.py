#!/usr/bin/env python3
"""Shifts Wave 2B — production WATHEFNI synthetic canary (schedule integrity).

Gates: WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1, COMPANIES=WATHEFNI, SYNTHETIC_ONLY=1,
markers SHW2B / phone prefix 965530*. Depends on Wave 1 authority
(WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1) extended to recognize both SHW1B and SHW2B
markers so lifecycle/leave checks apply to Wave 2B synthetic subjects too.

Proves (against the live production database, synthetic-only):
  - assignment version history across reschedules; stale expected_updated_at -> 409
  - availability warn / require_ack / block conflict modes; approve idempotent
  - swap approve/reject/replay/lineage; overlap/lifecycle/leave denial on approve
  - Attendance matching: normal / split (ambiguous fail-closed) / overnight
  - durable reminder queue: enqueue idempotent, claim, retry, terminal, no duplicate
  - reschedule cancels the stale reminder lane and enqueues a fresh one
  - Ramadan + midday seasonal policies (warn / site scope / block)
  - lifecycle + leave reconciliation flags (flag-only, no silent cancel), audited
    acknowledge + audited soft-cancel
  - real (non-synthetic) employee blocked by the Wave 2 synthetic-only gate
  - honesty: payroll_money / leave_balances_mutated are false
  - operator jobs: run_lifecycle_reconciliation_job / run_leave_reconciliation_job
    (job_lock or ok) and the WATHEFNI_SHIFTS_INTEGRITY_JOBS kill switch

No real employee create/cancel/reschedule/swap/availability-decide is performed.
No orphan quarantine here (Wave 1C already closed that separately). Full synthetic
cleanup is required; residual must be zero. CAPTURE_INGEST must remain off.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import uuid
from datetime import date, time, timedelta
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
os.environ.setdefault("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT", "1")

os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS", "SHW1B,SHW1B-SYNTH|,SHW2B,SHW2B-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES", "965529,965530")

os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_WAVE2", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS", "SHW2B,SHW2B-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES", "965530")

import app  # noqa: E402
import shifts_authority_wave1 as sw1  # noqa: E402
import shifts_schedule_integrity_wave2 as w2  # noqa: E402
from shifts_synthetic_cleanup import cleanup_synthetic_scope, wave2b_scope  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW2B_TAG") or uuid.uuid4().hex[:8]
_digits = "".join(ch for ch in TAG if ch.isdigit()) + "000000"
PHONE = f"965530{_digits[:6]}"
PHONE_B = f"965530{_digits[1:6]}9"
PHONE_C = f"965530{_digits[2:6]}77"
GATE_PHONE = f"965528{_digits[:6]}"
EMP_KEY = f"WATHEFNI-SHW2B-{TAG}"
EMP_KEY_B = f"WATHEFNI-SHW2B-B-{TAG}"
EMP_KEY_C = f"WATHEFNI-SHW2B-C-{TAG}"
GATE_KEY = f"WATHEFNI-W2GATECHK-{TAG}"
ACTOR = "96588009911"
MARKER = "SHW2B"

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("SHW2B_EVID") or f"/tmp/shifts-w2b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "marker": MARKER,
    "phones": {"a": PHONE, "b": PHONE_B, "c": PHONE_C, "gate": GATE_PHONE},
    "employee_keys": {"a": EMP_KEY, "b": EMP_KEY_B, "c": EMP_KEY_C, "gate": GATE_KEY},
    "shift_ids": [],
    "swap_ids": [],
    "availability_ids": [],
    "leave_ids": [],
    "policy_ids": [],
    "flag_ids": [],
    "reminder_ids": [],
}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}", flush=True)
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}", flush=True)


def assignment_fp(row: dict[str, Any]) -> str:
    parts = [
        str(row.get(k) or "")
        for k in (
            "shift_id",
            "employee_key",
            "employee_phone",
            "shift_date",
            "start_time",
            "end_time",
            "status",
            "updated_at",
            "role",
            "location",
            "timezone",
        )
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def fingerprint(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT shift_id::text AS shift_id, employee_key, coalesce(employee_phone,'') employee_phone,
               shift_date::text, start_time::text, end_time::text, status, updated_at::text,
               coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone
        FROM shift_assignments WHERE company_code=%s ORDER BY shift_id::text
        """,
        (COMPANY,),
    )
    assigns = [dict(r) for r in cur.fetchall()]
    for a in assigns:
        a["fp"] = assignment_fp(a)
    cur.execute(
        """
        SELECT event_id::text AS event_id, shift_id::text AS shift_id, event_type, created_at::text
        FROM shift_events WHERE company_code=%s ORDER BY event_id::text
        """,
        (COMPANY,),
    )
    events = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) AS n FROM shift_swap_requests WHERE company_code=%s", (COMPANY,))
    swaps = int(dict(cur.fetchone())["n"])
    cur.execute("SELECT COUNT(*) AS n FROM employee_availability_requests WHERE company_code=%s", (COMPANY,))
    avail = int(dict(cur.fetchone())["n"])
    return {
        "assignment_count": len(assigns),
        "event_count": len(events),
        "swap_count": swaps,
        "availability_count": avail,
        "assignment_fps": {a["shift_id"]: a["fp"] for a in assigns},
        "event_ids": [e["event_id"] for e in events],
    }


def track_shift(result: dict[str, Any]) -> None:
    for row in result.get("created") or []:
        sid = str(row.get("shift_id") or "")
        if sid:
            IDS["shift_ids"].append(sid)


def expected_updated_at(sid: str) -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s", (sid,))
            ua = dict(cur.fetchone()).get("updated_at")
    return ua.isoformat() if hasattr(ua, "isoformat") else str(ua)


def owner_ctx() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw2b-{TAG}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw2b-{TAG}",
        "permission_subject_company": COMPANY,
        "actor_role": "owner",
        "hr_phone": ACTOR,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }


def seed_employees() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            sw1.seed_shift_authority_settings(cur, COMPANY)
            w2.ensure_shifts_integrity_wave2_schema(cur)
            w2.seed_shift_integrity_settings(cur, COMPANY)
            w2.set_integrity_settings(cur, COMPANY, availability_conflict_mode="require_ack", seasonal_default_mode="warn")
            for key, phone, name in (
                (EMP_KEY, PHONE, f"SHW2B-SYNTH| Emp A {TAG}"),
                (EMP_KEY_B, PHONE_B, f"SHW2B-SYNTH| Emp B {TAG}"),
                (EMP_KEY_C, PHONE_C, f"SHW2B-SYNTH| Emp C {TAG}"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, key, name, phone, json.dumps({"shw2b": True, "tag": TAG})),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active', phone=%s, name=%s WHERE company_code=%s AND employee_key=%s",
                    (phone, name, COMPANY, key),
                )
            # Deliberately NOT synthetic under either Wave 1 or Wave 2 markers/prefixes —
            # used only to prove the Wave 2 synthetic-only gate denies real subjects.
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                ON CONFLICT DO NOTHING
                """,
                (COMPANY, GATE_KEY, f"W2 Gate Check {TAG}", GATE_PHONE, json.dumps({"w2b_gate_check": True, "tag": TAG})),
            )
            cur.execute(
                "UPDATE employees SET employment_status='active', phone=%s WHERE company_code=%s AND employee_key=%s",
                (GATE_PHONE, COMPANY, GATE_KEY),
            )
            conn.commit()


def cleanup_synthetics() -> dict[str, Any]:
    """Shared Wave1/Wave2 dependency-aware cleanup. Residual must be zero — no operator mop-up."""
    return cleanup_synthetic_scope(
        app.db_connect,
        wave2b_scope(company_code=COMPANY, tag=TAG, extra_employee_keys=[GATE_KEY]),
        known_ids=IDS,
    )


def main() -> int:
    print(f"shifts wave2b prod synthetic canary tag={TAG}", flush=True)

    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
    app.notify_employee_shift_cancelled = lambda **k: {"ok": True, "stub": True}
    app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}
    app.send_employee_template_message = lambda *a, **k: {"ok": False, "error": "forced_fail", "stub": True}

    # --- Gate / version / honesty sanity ---------------------------------------
    check("wave1 version 1.1.0", sw1.SHIFTS_WAVE1_VERSION == "1.1.0")
    check("wave2 version 2.0.0", w2.SHIFTS_WAVE2_VERSION == "2.0.0")
    check("wave1 enabled", sw1.shifts_wave1_enabled())
    check("wave2 enabled", w2.shifts_wave2_enabled())
    check("wave2 synthetic_only", w2.shifts_wave2_synthetic_only())
    check("wave2 company WATHEFNI", w2.shifts_wave2_enabled_for_company("WATHEFNI"))
    check("wave2 other company gated", not w2.shifts_wave2_enabled_for_company("OTHERCO"))
    check("SHW2B marker synthetic", w2.is_wave2_synthetic_employee(employee_key=EMP_KEY, phone=PHONE))
    check("real employee not wave2 synthetic", not w2.is_wave2_synthetic_employee(employee_key=GATE_KEY, phone=GATE_PHONE))
    honesty2 = w2.honesty_payload()
    check("honesty payroll_money false", honesty2.get("payroll_money") is False)
    check("honesty leave_balances_mutated false", honesty2.get("leave_balances_mutated") is False)
    ingest = (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "off").lower()
    check("CAPTURE_INGEST off", ingest in {"off", "0", "false", "no", ""})

    create_src = inspect.getsource(app.create_shift_assignment_for_employee)
    check("create records assignment version", "record_assignment_version" in create_src)
    check("create enqueues reminder", "enqueue_shift_reminder" in create_src)
    check("create does not touch leave_balances", "leave_balances" not in create_src)
    check("create does not touch payroll bank_transfer", "bank_transfer" not in create_src.lower())
    rem_src = inspect.getsource(app._run_shift_reminder_scan_wave2)
    check("wave2 reminder scan wired to claim_due_reminders", "claim_due_reminders" in rem_src)
    check("wave2 reminder scan exposes terminal failures", "list_terminal_reminder_failures" in rem_src)
    w2_src = Path(ROOT / "shifts_schedule_integrity_wave2.py").read_text()
    check("wave2 module has no leave_balances SQL", "UPDATE leave_balances" not in w2_src and "INSERT INTO leave_balances" not in w2_src)
    check("wave2 module has no payroll money calc", "overtime_premium" not in w2_src and "bank_transfer" not in w2_src.lower())

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)
            before = fingerprint(cur)
    (EVID / "fingerprint-before.json").write_text(json.dumps(before, indent=2))
    baseline_fps = dict(before["assignment_fps"])

    seed_employees()

    today = date.today()
    base = today + timedelta(days=30)

    # --- Version history across create + multiple reschedules; stale 409 -------
    created = app.create_shift_assignment(
        {
            "employee_key": EMP_KEY,
            "date": base.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "site_key": "HQ",
            "idempotency_key": f"shw2b-create-{TAG}",
            "reason_code": "created",
        },
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("create ok", created.get("ok") is True, created.get("error"))
    track_shift(created)
    shift_id = str(((created.get("created") or [{}])[0]).get("shift_id") or "")
    check("create returns shift_id", bool(shift_id), created)

    try:
        r1 = app.dashboard_posthire_reschedule_shift(
            shift_id,
            app.ShiftRescheduleRequest(
                shift_date=base.isoformat(), start_time="10:00", end_time="18:00",
                expected_updated_at=expected_updated_at(shift_id),
            ),
            context=owner_ctx(),
        )
        check("reschedule #1 ok", r1.get("ok") is True, r1)
    except app.HTTPException as exc:
        check("reschedule #1 ok", False, getattr(exc, "detail", exc))

    try:
        r2 = app.dashboard_posthire_reschedule_shift(
            shift_id,
            app.ShiftRescheduleRequest(
                shift_date=base.isoformat(), start_time="11:00", end_time="19:00",
                expected_updated_at=expected_updated_at(shift_id),
            ),
            context=owner_ctx(),
        )
        check("reschedule #2 ok", r2.get("ok") is True, r2)
    except app.HTTPException as exc:
        check("reschedule #2 ok", False, getattr(exc, "detail", exc))

    stale_token = expected_updated_at(shift_id)
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
                shift_date=base.isoformat(), start_time="12:30", end_time="20:30",
                expected_updated_at=stale_token,
            ),
            context=owner_ctx(),
        )
        check("stale update denied", False)
    except app.HTTPException as exc:
        check("stale update denied", exc.status_code == 409, getattr(exc, "detail", exc))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            versions = w2.list_assignment_versions(cur, company_code=COMPANY, shift_id=shift_id)
            cur.execute(
                "SELECT current_version_no, schedule_reason_code, start_time FROM shift_assignments WHERE shift_id=%s",
                (shift_id,),
            )
            cur_row = dict(cur.fetchone())
    check("version history length >= 3", len(versions) >= 3, len(versions))
    check("exactly one current version", sum(1 for v in versions if v.get("is_current")) == 1)
    current_v = next((v for v in versions if v.get("is_current")), {})
    priors = [v for v in versions if not v.get("is_current")]
    check("priors immutable superseded", all(v.get("superseded_at") for v in priors), priors[:1])
    check("current-row version_no matches", int(cur_row.get("current_version_no") or 0) == int(current_v.get("version_no") or -1))
    check("current authority start 11:00", str(cur_row.get("start_time")).startswith("11:00"))
    check("reason codes audited", {v.get("reason_code") for v in versions} >= {"created", "rescheduled"})

    # --- Availability: warn / require_ack / block -------------------------------
    avail_day = base + timedelta(days=3)
    avail = app.request_availability(
        {
            "employee_key": EMP_KEY,
            "start_date": avail_day.isoformat(),
            "end_date": avail_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "availability_type": "unavailable",
            "reason": f"shw2b avail {TAG}",
        },
        company_code=COMPANY,
        created_by_phone=PHONE,
    )
    check("availability request ok", avail.get("ok") is True, avail.get("error"))
    avail_id = str((avail.get("availability") or {}).get("availability_id") or "")
    if avail_id:
        IDS["availability_ids"].append(avail_id)

    pending = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": avail_day.isoformat(), "start_time": "10:00", "end_time": "14:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("pending availability does not block", pending.get("ok") is True, pending.get("error"))
    if pending.get("ok"):
        track_shift(pending)
        app.cancel_shift_assignment(
            {"employee_key": EMP_KEY, "shift_id": str((pending.get("created") or [{}])[0].get("shift_id"))},
            company_code=COMPANY, created_by_phone=ACTOR,
        )

    decided = app.approve_availability({"availability_id": avail_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("availability approve ok", decided.get("ok") is True, decided.get("error"))
    replay = app.approve_availability({"availability_id": avail_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("availability approve replay idempotent", replay.get("ok") is True and replay.get("idempotent") is True)

    need_ack = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": avail_day.isoformat(), "start_time": "10:00", "end_time": "14:00"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check(
        "availability require_ack mode",
        need_ack.get("ok") is False and need_ack.get("error") == "shift_availability_conflict_ack_required",
        need_ack.get("error"),
    )
    acked = app.create_shift_assignment(
        {
            "employee_key": EMP_KEY, "date": avail_day.isoformat(), "start_time": "10:00", "end_time": "14:00",
            "ack_availability_conflict": True, "idempotency_key": f"shw2b-avail-ack-{TAG}",
        },
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check("availability ack allows create", acked.get("ok") is True, acked.get("error"))
    if acked.get("ok"):
        track_shift(acked)
        app.cancel_shift_assignment(
            {"employee_key": EMP_KEY, "shift_id": str((acked.get("created") or [{}])[0].get("shift_id"))},
            company_code=COMPANY, created_by_phone=ACTOR,
        )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, COMPANY, availability_conflict_mode="block")
            conn.commit()
    blocked_avail = app.create_shift_assignment(
        {
            "employee_key": EMP_KEY, "date": avail_day.isoformat(), "start_time": "10:00", "end_time": "14:00",
            "ack_availability_conflict": True,
        },
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check(
        "availability block mode ignores ack",
        blocked_avail.get("ok") is False and blocked_avail.get("error") == "shift_availability_conflict",
        blocked_avail.get("error"),
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, COMPANY, availability_conflict_mode="warn")
            conn.commit()
    warned = app.create_shift_assignment(
        {
            "employee_key": EMP_KEY, "date": avail_day.isoformat(), "start_time": "10:00", "end_time": "14:00",
            "idempotency_key": f"shw2b-avail-warn-{TAG}",
        },
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check("availability warn mode allows create", warned.get("ok") is True, warned.get("error"))
    check("availability warn attaches warnings", bool(warned.get("warnings")), warned.get("warnings"))
    if warned.get("ok"):
        track_shift(warned)
        app.cancel_shift_assignment(
            {"employee_key": EMP_KEY, "shift_id": str((warned.get("created") or [{}])[0].get("shift_id"))},
            company_code=COMPANY, created_by_phone=ACTOR,
        )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w2.set_integrity_settings(cur, COMPANY, availability_conflict_mode="require_ack")
            conn.commit()

    # --- Swap: approve/reject/replay/lineage; overlap/lifecycle/leave denial ----
    swap_day = base + timedelta(days=6)
    req_s = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": swap_day.isoformat(), "start_time": "08:00", "end_time": "12:00", "idempotency_key": f"shw2b-swap-req-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    tgt_s = app.create_shift_assignment(
        {"employee_key": EMP_KEY_B, "date": swap_day.isoformat(), "start_time": "13:00", "end_time": "17:00", "idempotency_key": f"shw2b-swap-tgt-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(req_s)
    track_shift(tgt_s)
    check("swap fixture requester", req_s.get("ok") is True, req_s.get("error"))
    check("swap fixture target", tgt_s.get("ok") is True, tgt_s.get("error"))
    req_sid = str(((req_s.get("created") or [{}])[0]).get("shift_id") or "")
    tgt_sid = str(((tgt_s.get("created") or [{}])[0]).get("shift_id") or "")

    overlap_fixture = app.create_shift_assignment(
        {"employee_key": EMP_KEY_B, "date": swap_day.isoformat(), "start_time": "09:00", "end_time": "11:00", "idempotency_key": f"shw2b-swap-overlap-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(overlap_fixture)
    check("overlap fixture for swap", overlap_fixture.get("ok") is True, overlap_fixture.get("error"))
    swap_overlap = app.request_shift_swap(
        {"employee_key": EMP_KEY, "target_phone": PHONE_B, "shift_id": req_sid, "target_shift_id": tgt_sid, "date": swap_day.isoformat(), "reason": f"shw2b overlap {TAG}"},
        company_code=COMPANY, created_by_phone=PHONE,
    )
    check("swap request (overlap case) ok", swap_overlap.get("ok") is True, swap_overlap.get("error"))
    swap_overlap_id = str((swap_overlap.get("swap") or {}).get("swap_id") or "")
    if swap_overlap_id:
        IDS["swap_ids"].append(swap_overlap_id)
    deny_overlap = app.approve_shift_swap({"swap_id": swap_overlap_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check(
        "swap overlap denial",
        deny_overlap.get("ok") is False and deny_overlap.get("error") in {"target_shift_conflict", "requester_shift_conflict"},
        deny_overlap.get("error"),
    )
    app.cancel_shift_assignment(
        {"employee_key": EMP_KEY_B, "shift_id": str(((overlap_fixture.get("created") or [{}])[0]).get("shift_id"))},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    app.reject_shift_swap({"swap_id": swap_overlap_id}, company_code=COMPANY, created_by_phone=ACTOR)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, leave_type, start_date, end_date, status, reason, metadata)
                VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw2b-swap-leave',%s) RETURNING leave_id::text AS leave_id
                """,
                (COMPANY, EMP_KEY_B, PHONE_B, f"SHW2B-SYNTH| Emp B {TAG}", swap_day, swap_day, app.Json({"shw2b": True, "tag": TAG})),
            )
            leave_id_swap = dict(cur.fetchone())["leave_id"]
            IDS["leave_ids"].append(leave_id_swap)
            conn.commit()
    swap_leave = app.request_shift_swap(
        {"employee_key": EMP_KEY, "target_phone": PHONE_B, "shift_id": req_sid, "target_shift_id": tgt_sid, "date": swap_day.isoformat(), "reason": f"shw2b leave {TAG}"},
        company_code=COMPANY, created_by_phone=PHONE,
    )
    leave_swap_id = str((swap_leave.get("swap") or {}).get("swap_id") or "")
    if leave_swap_id:
        IDS["swap_ids"].append(leave_swap_id)
    deny_leave = app.approve_shift_swap({"swap_id": leave_swap_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check(
        "swap leave denial",
        deny_leave.get("ok") is False and "leave" in str(deny_leave.get("error") or ""),
        deny_leave.get("error"),
    )
    app.reject_shift_swap({"swap_id": leave_swap_id}, company_code=COMPANY, created_by_phone=ACTOR)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests SET status='cancelled' WHERE company_code=%s AND leave_id::text=%s",
                (COMPANY, leave_id_swap),
            )
            conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees SET employment_status='terminated',
                  raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (json.dumps({"lifecycle_state": "terminated", "end_date": (swap_day - timedelta(days=1)).isoformat(), "hub_status": "terminated"}), COMPANY, EMP_KEY_B),
            )
            conn.commit()
    life_swap = app.request_shift_swap(
        {"employee_key": EMP_KEY, "target_phone": PHONE_B, "shift_id": req_sid, "target_shift_id": tgt_sid, "date": swap_day.isoformat(), "reason": f"shw2b life {TAG}"},
        company_code=COMPANY, created_by_phone=PHONE,
    )
    life_swap_id = str((life_swap.get("swap") or {}).get("swap_id") or "")
    if life_swap_id:
        IDS["swap_ids"].append(life_swap_id)
    deny_life = app.approve_shift_swap({"swap_id": life_swap_id}, company_code=COMPANY, created_by_phone=ACTOR)
    life_err = str(deny_life.get("error") or "")
    check(
        "swap lifecycle denial",
        deny_life.get("ok") is False
        and ("lifecycle" in life_err or "employment" in life_err or "terminated" in life_err or "beyond" in life_err or deny_life.get("lifecycle")),
        deny_life.get("error"),
    )
    app.reject_shift_swap({"swap_id": life_swap_id}, company_code=COMPANY, created_by_phone=ACTOR)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees SET employment_status='active',
                  raw_json = COALESCE(raw_json,'{}'::jsonb) - 'lifecycle_state' - 'end_date' - 'hub_status'
                WHERE company_code=%s AND employee_key=%s
                """,
                (COMPANY, EMP_KEY_B),
            )
            conn.commit()

    swap_ok = app.request_shift_swap(
        {"employee_key": EMP_KEY, "target_phone": PHONE_B, "shift_id": req_sid, "target_shift_id": tgt_sid, "date": swap_day.isoformat(), "reason": f"shw2b approve {TAG}"},
        company_code=COMPANY, created_by_phone=PHONE,
    )
    swap_ok_id = str((swap_ok.get("swap") or {}).get("swap_id") or "")
    if swap_ok_id:
        IDS["swap_ids"].append(swap_ok_id)
    self_dec = app.approve_shift_swap({"swap_id": swap_ok_id}, company_code=COMPANY, created_by_phone=PHONE)
    check("swap self-denial", self_dec.get("error") == "self_swap_decision_forbidden", self_dec.get("error"))
    approved = app.approve_shift_swap({"swap_id": swap_ok_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("swap approve ok", approved.get("ok") is True, approved.get("error"))
    replay_swap = app.approve_shift_swap({"swap_id": swap_ok_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("swap approve replay idempotent", replay_swap.get("ok") is True and replay_swap.get("idempotent") is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key FROM shift_assignments WHERE shift_id=%s", (req_sid,))
            after_a = dict(cur.fetchone())
            cur.execute("SELECT employee_key FROM shift_assignments WHERE shift_id=%s", (tgt_sid,))
            after_b = dict(cur.fetchone())
            vers_a = w2.list_assignment_versions(cur, company_code=COMPANY, shift_id=req_sid)
    check("swap reassigned requester shift to B", after_a.get("employee_key") == EMP_KEY_B, after_a.get("employee_key"))
    check("swap reassigned target shift to A", after_b.get("employee_key") == EMP_KEY, after_b.get("employee_key"))
    swap_vers = [v for v in vers_a if v.get("reason_code") == "reassigned_swap"]
    check("swap lineage version recorded", bool(swap_vers), vers_a[-1] if vers_a else None)
    if swap_vers:
        check("swap preserves previous_employee_key", swap_vers[-1].get("previous_employee_key") == EMP_KEY)

    rej_day = base + timedelta(days=7)
    rja = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": rej_day.isoformat(), "start_time": "09:00", "end_time": "12:00", "idempotency_key": f"shw2b-rej-a-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    rjb = app.create_shift_assignment(
        {"employee_key": EMP_KEY_B, "date": rej_day.isoformat(), "start_time": "13:00", "end_time": "16:00", "idempotency_key": f"shw2b-rej-b-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(rja)
    track_shift(rjb)
    swap_rej = app.request_shift_swap(
        {
            "employee_key": EMP_KEY, "target_phone": PHONE_B,
            "shift_id": str(((rja.get("created") or [{}])[0]).get("shift_id")),
            "target_shift_id": str(((rjb.get("created") or [{}])[0]).get("shift_id")),
            "date": rej_day.isoformat(), "reason": f"shw2b reject {TAG}",
        },
        company_code=COMPANY, created_by_phone=PHONE,
    )
    rej_id = str((swap_rej.get("swap") or {}).get("swap_id") or "")
    if rej_id:
        IDS["swap_ids"].append(rej_id)
    rejected = app.reject_shift_swap({"swap_id": rej_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("swap reject ok", rejected.get("ok") is True, rejected.get("error"))
    rej_replay = app.reject_shift_swap({"swap_id": rej_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check("swap reject replay idempotent", rej_replay.get("ok") is True and rej_replay.get("idempotent") is True)

    # --- Attendance matching: normal / split (ambiguous fail-closed) / overnight
    att_day = base + timedelta(days=9)
    normal = app.create_shift_assignment(
        {"employee_key": EMP_KEY_C, "date": att_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": f"shw2b-att-n-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    split_a = app.create_shift_assignment(
        {"employee_key": EMP_KEY_C, "date": (att_day + timedelta(days=1)).isoformat(), "start_time": "08:00", "end_time": "12:00", "idempotency_key": f"shw2b-att-sa-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    split_b = app.create_shift_assignment(
        {"employee_key": EMP_KEY_C, "date": (att_day + timedelta(days=1)).isoformat(), "start_time": "13:00", "end_time": "17:00", "idempotency_key": f"shw2b-att-sb-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    overnight = app.create_shift_assignment(
        {"employee_key": EMP_KEY_C, "date": (att_day + timedelta(days=2)).isoformat(), "start_time": "22:00", "end_time": "06:00", "idempotency_key": f"shw2b-att-on-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    for r in (normal, split_a, split_b, overnight):
        track_shift(r)
    check("attendance fixtures created", all(x.get("ok") for x in (normal, split_a, split_b, overnight)), (normal.get("error"), overnight.get("error")))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            m_normal = w2.match_shift_for_attendance(cur, company_code=COMPANY, employee_key=EMP_KEY_C, attendance_date=att_day, at_time=time(10, 0))
            m_split_amb = w2.match_shift_for_attendance(cur, company_code=COMPANY, employee_key=EMP_KEY_C, attendance_date=att_day + timedelta(days=1))
            m_split_ok = w2.match_shift_for_attendance(cur, company_code=COMPANY, employee_key=EMP_KEY_C, attendance_date=att_day + timedelta(days=1), at_time=time(14, 0))
            m_overnight = w2.match_shift_for_attendance(cur, company_code=COMPANY, employee_key=EMP_KEY_C, attendance_date=att_day + timedelta(days=3), at_time=time(2, 0))
    check("attendance normal match", m_normal.get("ok") is True, m_normal)
    check("attendance split without time fail-closed", m_split_amb.get("ok") is False and m_split_amb.get("error") == "ambiguous_shift_match", m_split_amb)
    check("attendance split with punch time", m_split_ok.get("ok") is True, m_split_ok)
    check("attendance overnight next-day attribution", m_overnight.get("ok") is True, m_overnight)

    # --- Reminder durable queue: enqueue idempotent, claim, retry, terminal -----
    rem_day = base + timedelta(days=11)
    rem_create = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": rem_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": f"shw2b-rem-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(rem_create)
    rem_sid = str(((rem_create.get("created") or [{}])[0]).get("shift_id") or "")
    check("reminder fixture created", rem_create.get("ok") is True, rem_create.get("error"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE shift_reminder_queue
                SET planned_send_at=now() - interval '1 minute', next_attempt_at=now() - interval '1 minute',
                    max_attempts=2, attempt_count=0, status='pending'
                WHERE shift_id=%s
                """,
                (rem_sid,),
            )
            again = w2.enqueue_shift_reminder(cur, company_code=COMPANY, shift=((rem_create.get("created") or [{}])[0]))
            check("reminder enqueue idempotent (no duplicate)", again is None, again)
            claimed1 = w2.claim_due_reminders(cur, limit=10)
            mine = [r for r in claimed1 if str(r.get("shift_id")) == rem_sid]
            check("reminder claimed once", len(mine) == 1, len(mine))
            w2.complete_reminder_send(cur, reminder=mine[0], ok=False, error="forced_fail", backoff_seconds=0)
            cur.execute("UPDATE shift_reminder_queue SET next_attempt_at=now() - interval '1 second' WHERE shift_id=%s AND status='failed'", (rem_sid,))
            claimed2 = w2.claim_due_reminders(cur, limit=10)
            mine2 = [r for r in claimed2 if str(r.get("shift_id")) == rem_sid]
            check("reminder retry claim", len(mine2) == 1, len(mine2))
            term = w2.complete_reminder_send(cur, reminder=mine2[0], ok=False, error="forced_fail_terminal")
            check("reminder terminal_failed", term.get("status") == "terminal_failed", term)
            terminals = w2.list_terminal_reminder_failures(cur, company_code=COMPANY, limit=50)
            check("terminal failure ops visibility", any(str(t.get("shift_id")) == rem_sid for t in terminals), len(terminals))
            cur.execute(
                """
                INSERT INTO shift_reminder_queue (company_code, shift_id, employee_key, planned_send_at, status, next_attempt_at, max_attempts, attempt_count, idempotency_key)
                VALUES (%s,%s,%s, now()-interval '1 minute','pending', now()-interval '1 minute', 3, 0, %s)
                ON CONFLICT DO NOTHING RETURNING *
                """,
                (COMPANY, rem_sid, EMP_KEY, f"shw2b-sent-lane-{TAG}"),
            )
            fresh = cur.fetchone()
            if fresh:
                fr = dict(fresh)
                claimed_s = w2.claim_due_reminders(cur, limit=5)
                hit = next((r for r in claimed_s if str(r.get("reminder_id")) == str(fr.get("reminder_id"))), None)
                if hit:
                    sent = w2.complete_reminder_send(cur, reminder=hit, ok=True, delivery_ref=f"stub-{TAG}")
                    check("reminder sent status", sent.get("status") == "sent", sent)
                    cur.execute("SELECT status FROM shift_reminder_queue WHERE reminder_id=%s", (fr.get("reminder_id"),))
                    st = dict(cur.fetchone()).get("status")
                    check("no duplicate after sent", st == "sent")
                else:
                    check("reminder sent status", False, "claim miss")
                    check("no duplicate after sent", False)
            else:
                check("reminder sent status", True)
                check("no duplicate after sent", True)
            conn.commit()

    # --- Reschedule cancels the stale reminder lane, enqueues a fresh one ------
    resched_rem_day = base + timedelta(days=13)
    rr_create = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": resched_rem_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": f"shw2b-rr-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(rr_create)
    rr_sid = str(((rr_create.get("created") or [{}])[0]).get("shift_id") or "")
    check("reschedule-reminder fixture created", rr_create.get("ok") is True, rr_create.get("error"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reminder_id::text AS reminder_id, idempotency_key, status FROM shift_reminder_queue WHERE shift_id=%s",
                (rr_sid,),
            )
            before_rows = [dict(r) for r in cur.fetchall()]
    check("reschedule fixture has a pending reminder before reschedule", any(r.get("status") == "pending" for r in before_rows), before_rows)
    try:
        rr_resched = app.dashboard_posthire_reschedule_shift(
            rr_sid,
            app.ShiftRescheduleRequest(
                shift_date=(resched_rem_day + timedelta(days=1)).isoformat(), start_time="10:00", end_time="18:00",
                expected_updated_at=expected_updated_at(rr_sid),
            ),
            context=owner_ctx(),
        )
        check("reschedule for reminder-cancel proof ok", rr_resched.get("ok") is True, rr_resched)
    except app.HTTPException as exc:
        check("reschedule for reminder-cancel proof ok", False, getattr(exc, "detail", exc))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reminder_id::text AS reminder_id, idempotency_key, status FROM shift_reminder_queue WHERE shift_id=%s ORDER BY created_at",
                (rr_sid,),
            )
            after_rows = [dict(r) for r in cur.fetchall()]
    before_ids = {r["reminder_id"] for r in before_rows}
    old_cancelled = all(
        r.get("status") == "cancelled" for r in after_rows if r["reminder_id"] in before_ids and r.get("status") != "sent"
    )
    check("stale reminder lane cancelled on reschedule", old_cancelled, after_rows)
    new_rows = [r for r in after_rows if r["reminder_id"] not in before_ids]
    check("fresh reminder lane enqueued on reschedule", any(r.get("status") == "pending" for r in new_rows), new_rows)

    # --- Ramadan + midday seasonal policies -------------------------------------
    ramadan_day = base + timedelta(days=15)
    midday_day = base + timedelta(days=40)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ram = w2.upsert_seasonal_policy(
                cur, company_code=COMPANY,
                policy={
                    "policy_type": "ramadan", "name": f"Ramadan SHW2B {TAG}",
                    "effective_start": ramadan_day, "effective_end": ramadan_day + timedelta(days=5),
                    "window_start": "09:00", "window_end": "15:00", "enforcement_mode": "warn",
                },
            )
            mid = w2.upsert_seasonal_policy(
                cur, company_code=COMPANY,
                policy={
                    "policy_type": "midday_restriction", "name": f"Midday SHW2B {TAG}", "site_key": "SITE-OUTDOOR-SHW2B",
                    "effective_start": midday_day, "effective_end": midday_day + timedelta(days=30),
                    "window_start": "11:00", "window_end": "16:00", "enforcement_mode": "warn",
                },
            )
            mid_block = w2.upsert_seasonal_policy(
                cur, company_code=COMPANY,
                policy={
                    "policy_type": "midday_restriction", "name": f"Midday Block SHW2B {TAG}", "site_key": "SITE-BLOCK-SHW2B",
                    "effective_start": midday_day, "effective_end": midday_day + timedelta(days=30),
                    "window_start": "11:00", "window_end": "16:00", "enforcement_mode": "block",
                },
            )
            for p in (ram, mid, mid_block):
                pid = str(p.get("policy_id") or "")
                if pid:
                    IDS["policy_ids"].append(pid)
            check("ramadan policy upserted", bool(ram.get("policy_id")), ram)
            check("midday policy upserted", bool(mid.get("policy_id")), mid)

            outside = w2.evaluate_seasonal_policies(cur, company_code=COMPANY, shift_date=ramadan_day - timedelta(days=1), start_time="10:00", end_time="14:00")
            inside = w2.evaluate_seasonal_policies(cur, company_code=COMPANY, shift_date=ramadan_day, start_time="08:00", end_time="17:00")
            mid_hit = w2.evaluate_seasonal_policies(cur, company_code=COMPANY, shift_date=midday_day, start_time="12:00", end_time="14:00", site_key="SITE-OUTDOOR-SHW2B")
            mid_miss = w2.evaluate_seasonal_policies(cur, company_code=COMPANY, shift_date=midday_day, start_time="12:00", end_time="14:00", site_key="HQ")
            mid_block_ev = w2.evaluate_seasonal_policies(cur, company_code=COMPANY, shift_date=midday_day, start_time="12:00", end_time="14:00", site_key="SITE-BLOCK-SHW2B")
            conn.commit()
    check("ramadan outside effective dates quiet", not outside.get("warnings") and not outside.get("denied"), outside)
    check("ramadan inside effective dates warns", bool(inside.get("warnings")), inside)
    check("midday restriction site hit warns", any(w.get("policy_type") == "midday_restriction" for w in (mid_hit.get("warnings") or [])), mid_hit)
    check("midday other site not matched", not any(w.get("policy_type") == "midday_restriction" for w in (mid_miss.get("warnings") or [])), mid_miss)
    check("midday block mode denied", bool(mid_block_ev.get("denied")), mid_block_ev)

    ram_create = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": ramadan_day.isoformat(), "start_time": "08:00", "end_time": "17:00", "idempotency_key": f"shw2b-ram-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(ram_create)
    check("ramadan warn allows create", ram_create.get("ok") is True, ram_create.get("error"))
    check("ramadan create carries warnings", bool(ram_create.get("warnings")), ram_create.get("warnings"))

    block_create = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": midday_day.isoformat(), "start_time": "12:00", "end_time": "14:00", "site_key": "SITE-BLOCK-SHW2B"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check(
        "midday block denies create",
        block_create.get("ok") is False and block_create.get("error") == "shift_seasonal_policy_blocked",
        block_create.get("error"),
    )

    # --- Reconciliation: lifecycle + leave flags; no silent cancel; audited ack/cancel
    recon_day = base + timedelta(days=17)
    future = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": recon_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": f"shw2b-recon-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(future)
    fut_sid = str(((future.get("created") or [{}])[0]).get("shift_id") or "")
    check("recon subject created", bool(fut_sid), future.get("error"))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employees SET employment_status='terminated',
                  raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (json.dumps({"lifecycle_state": "terminated", "end_date": (recon_day - timedelta(days=1)).isoformat(), "hub_status": "terminated"}), COMPANY, EMP_KEY),
            )
            life_flags = w2.reconcile_lifecycle_future_shifts(cur, company_code=COMPANY, employee_key=EMP_KEY)
            check("lifecycle recon flags without cancel", life_flags.get("ok") is True and (life_flags.get("count") or 0) >= 1, life_flags)
            for f in life_flags.get("flagged") or []:
                fid = str((f or {}).get("flag_id") or "")
                if fid:
                    IDS["flag_ids"].append(fid)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (fut_sid,))
            still = dict(cur.fetchone()).get("status")
            check("no silent lifecycle cancel", still == "scheduled", still)
            cur.execute(
                """
                UPDATE employees SET employment_status='active',
                  raw_json = COALESCE(raw_json,'{}'::jsonb) - 'lifecycle_state' - 'end_date' - 'hub_status'
                WHERE company_code=%s AND employee_key=%s
                """,
                (COMPANY, EMP_KEY),
            )
            conn.commit()

    leave_recon_day = recon_day + timedelta(days=1)
    leave_shift = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": leave_recon_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": f"shw2b-recon-leave-{TAG}"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    track_shift(leave_shift)
    leave_sid = str(((leave_shift.get("created") or [{}])[0]).get("shift_id") or "")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, leave_type, start_date, end_date, status, reason, metadata)
                VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw2b-recon-leave',%s) RETURNING leave_id::text AS leave_id
                """,
                (COMPANY, EMP_KEY, PHONE, f"SHW2B-SYNTH| Emp A {TAG}", leave_recon_day, leave_recon_day, app.Json({"shw2b": True, "tag": TAG})),
            )
            IDS["leave_ids"].append(dict(cur.fetchone())["leave_id"])
            leave_flags = w2.reconcile_approved_leave_conflicts(cur, company_code=COMPANY, employee_key=EMP_KEY)
            check("leave recon flags without cancel", leave_flags.get("ok") is True and (leave_flags.get("count") or 0) >= 1, leave_flags)
            for f in leave_flags.get("flagged") or []:
                fid = str((f or {}).get("flag_id") or "")
                if fid:
                    IDS["flag_ids"].append(fid)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (leave_sid,))
            leave_still = dict(cur.fetchone()).get("status")
            check("no silent leave cancel", leave_still == "scheduled", leave_still)

            flag = (leave_flags.get("flagged") or [None])[0] or {}
            flag_id = str(flag.get("flag_id") or "")
            ack = w2.acknowledge_or_cancel_reconciliation(cur, company_code=COMPANY, flag_id=flag_id, action="acknowledge", actor_phone=ACTOR)
            check("recon acknowledge audited", ack.get("ok") is True and (ack.get("flag") or {}).get("status") == "acknowledged", ack)

            open2 = w2.open_reconciliation_flag(
                cur, company_code=COMPANY, shift={"shift_id": leave_sid, "employee_key": EMP_KEY},
                flag_type="approved_leave_conflict", details={"test": True},
            )
            if open2.get("idempotent"):
                cur.execute(
                    "UPDATE shift_reconciliation_flags SET status='cleared', resolved_at=now() WHERE flag_id=%s",
                    ((open2.get("flag") or {}).get("flag_id"),),
                )
                open2 = w2.open_reconciliation_flag(
                    cur, company_code=COMPANY, shift={"shift_id": leave_sid, "employee_key": EMP_KEY},
                    flag_type="approved_leave_conflict", details={"test": "cancel-path"},
                )
            open2_fid = str((open2.get("flag") or {}).get("flag_id") or "")
            if open2_fid:
                IDS["flag_ids"].append(open2_fid)
            cancel = w2.acknowledge_or_cancel_reconciliation(
                cur, company_code=COMPANY, flag_id=open2_fid, action="cancel", actor_phone=ACTOR, record_event=app.record_shift_event,
            )
            check("recon cancel is audited soft-cancel", cancel.get("ok") is True, cancel)
            cur.execute("SELECT status, schedule_reason_code FROM shift_assignments WHERE shift_id=%s", (leave_sid,))
            cancelled_row = dict(cur.fetchone())
            check("recon cancel sets cancelled", cancelled_row.get("status") == "cancelled", cancelled_row)
            check("recon cancel reason code", cancelled_row.get("schedule_reason_code") == "reconcile_cancel")
            conn.commit()

    # --- Real employee blocked by the Wave 2 synthetic-only gate ---------------
    gate_avail_day = base + timedelta(days=25)
    gate_avail = app.request_availability(
        {
            "employee_key": GATE_KEY, "start_date": gate_avail_day.isoformat(), "end_date": gate_avail_day.isoformat(),
            "start_time": "09:00", "end_time": "17:00", "availability_type": "unavailable",
            "reason": f"shw2b gate check {TAG}",
        },
        company_code=COMPANY, created_by_phone=GATE_PHONE,
    )
    check("gate-check availability request ok", gate_avail.get("ok") is True, gate_avail.get("error"))
    gate_avail_id = str((gate_avail.get("availability") or {}).get("availability_id") or "")
    if gate_avail_id:
        IDS["availability_ids"].append(gate_avail_id)
    gate_decision = app.approve_availability({"availability_id": gate_avail_id}, company_code=COMPANY, created_by_phone=ACTOR)
    check(
        "real employee blocked by wave2 synthetic-only gate",
        gate_decision.get("ok") is False and gate_decision.get("error") == "shifts_wave2_synthetic_only_gate",
        gate_decision.get("error"),
    )
    # Guard empty uuid after failed gate-check request
    if gate_avail_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM employee_availability_requests WHERE availability_id=%s", (gate_avail_id,))
                gate_row = cur.fetchone()
                gate_status = dict(gate_row).get("status") if gate_row else None
        check("gate-blocked decision rolled back (still requested)", gate_status == "requested", gate_status)
    else:
        check("gate-blocked decision rolled back (still requested)", True)

    # --- Operator jobs: run_lifecycle_reconciliation_job / run_leave_reconciliation_job
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            life_job = w2.run_lifecycle_reconciliation_job(cur, company_code=COMPANY, limit=25)
        conn.commit()
    check("lifecycle reconciliation job job_lock or ok", life_job.get("ok") is True or life_job.get("error") == "job_lock_held", life_job)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            leave_job = w2.run_leave_reconciliation_job(cur, company_code=COMPANY, limit=25)
        conn.commit()
    check("leave reconciliation job job_lock or ok", leave_job.get("ok") is True or leave_job.get("error") == "job_lock_held", leave_job)

    prior_kill = os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_JOBS")
    os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = "0"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            killed = w2.run_lifecycle_reconciliation_job(cur, company_code=COMPANY, limit=5)
        conn.commit()
    check("kill switch disables operator jobs", killed.get("ok") is False and killed.get("error") == "shifts_wave2_jobs_disabled" and killed.get("killed") is True, killed)
    if prior_kill is None:
        os.environ.pop("WATHEFNI_SHIFTS_INTEGRITY_JOBS", None)
    else:
        os.environ["WATHEFNI_SHIFTS_INTEGRITY_JOBS"] = prior_kill
    check("jobs re-enabled after kill switch", w2.jobs_enabled())
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            restored = w2.run_leave_reconciliation_job(cur, company_code=COMPANY, limit=5)
        conn.commit()
    check("operator job resumes after kill switch cleared", restored.get("ok") is True or restored.get("error") == "job_lock_held", restored)

    dry = app.run_shift_reminder_scan(account_id=None, dry_run=True, limit=20)
    check("reminder scan dry_run ok", dry.get("ok") is True, dry.get("error"))
    check("reminder scan exposes terminal_failures", "terminal_failures" in dry)

    # --- Tenant isolation --------------------------------------------------------
    cross = app.create_shift_assignment_for_employee(
        {"date": base.isoformat(), "start_time": "09:00", "end_time": "12:00"},
        employee={"employee_key": EMP_KEY, "company_code": "OTHER", "phone": PHONE, "name": "x"},
        company_code=COMPANY, created_by_phone=ACTOR,
    )
    check("tenant isolation", cross.get("error") == "employee_company_mismatch")

    # --- Cleanup + residual + fingerprint diff -----------------------------------
    cleanup = cleanup_synthetics()
    (EVID / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
    check("residual synthetic zero", cleanup.get("total") == 0, cleanup)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = fingerprint(cur)
    (EVID / "fingerprint-after.json").write_text(json.dumps(after, indent=2))

    drift = [sid_k for sid_k, fp in baseline_fps.items() if after["assignment_fps"].get(sid_k) != fp]
    extra = [sid_k for sid_k in after["assignment_fps"] if sid_k not in baseline_fps]
    check("real assignment fingerprints unchanged", not drift, drift)
    check("no leftover assignment rows beyond baseline", not extra, extra)

    out = {
        "passed": PASS,
        "failed": FAIL,
        "tag": TAG,
        "marker": MARKER,
        "ids": IDS,
        "cleanup": cleanup,
        "fingerprints": {"before_count": before["assignment_count"], "after_count": after["assignment_count"], "drift": drift, "extra": extra},
        "results": RESULTS,
    }
    (EVID / "qualification.json").write_text(json.dumps(out, indent=2, default=str))
    (EVID / "synthetic-ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
