#!/usr/bin/env python3
"""Shifts Wave 1B — production WATHEFNI synthetic canary.

Gates: WAVE1=1, COMPANIES=WATHEFNI, SYNTHETIC_ONLY=1, markers SHW1B / 965529*.
No real employee create/cancel/reschedule/swap. Orphan quarantine is allowlisted only.
Full synthetic cleanup required. CAPTURE_INGEST must remain off.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import uuid
from datetime import date, timedelta
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
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS", "SHW1B,SHW1B-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES", "965529")
os.environ.setdefault("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT", "1")

import app  # noqa: E402
import attendance_authority_wave1 as att  # noqa: E402
import shifts_authority_wave1 as sw1  # noqa: E402
import shifts_controlled_wave6c as _shifts_w6c  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    PRODUCTION_ORPHAN_ALLOWLIST,
    cleanup_synthetic_scope,
    wave1b_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW1B_TAG") or uuid.uuid4().hex[:8]
_digits = "".join(ch for ch in TAG if ch.isdigit()) + "000000"
PHONE = f"965529{_digits[:6]}"
PHONE_B = f"965529{_digits[1:6]}9"
EMP_KEY = f"WATHEFNI-SHW1B-{TAG}"
EMP_KEY_B = f"WATHEFNI-SHW1B-B-{TAG}"
ACTOR = "96588009911"
MARKER = "SHW1B"

ORPHAN_ALLOWLIST = set(PRODUCTION_ORPHAN_ALLOWLIST)

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("SHW1B_EVID") or f"/tmp/shifts-w1b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "marker": MARKER,
    "phones": {"a": PHONE, "b": PHONE_B},
    "employee_keys": {"a": EMP_KEY, "b": EMP_KEY_B},
    "shift_ids": [],
    "swap_ids": [],
    "leave_ids": [],
    "quarantine_ids": [],
    "orphan_shift_ids": [],
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
    avail = 0
    for tbl in ("employee_availability_requests", "employee_availability"):
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM {tbl} WHERE company_code=%s", (COMPANY,))
            avail = int(dict(cur.fetchone())["n"])
            break
        except Exception:
            pass
    return {
        "assignment_count": len(assigns),
        "event_count": len(events),
        "swap_count": swaps,
        "availability_count": avail,
        "assignment_fps": {a["shift_id"]: a["fp"] for a in assigns},
        "event_ids": [e["event_id"] for e in events],
        "assigns": assigns,
        "events": events,
    }


def track_shift(result: dict[str, Any]) -> None:
    for row in result.get("created") or []:
        sid = str(row.get("shift_id") or "")
        if sid:
            IDS["shift_ids"].append(sid)


def seed_employees() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            sw1.seed_shift_authority_settings(cur, COMPANY)
            for key, phone, name in (
                (EMP_KEY, PHONE, f"SHW1B-SYNTH| Emp A {TAG}"),
                (EMP_KEY_B, PHONE_B, f"SHW1B-SYNTH| Emp B {TAG}"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, key, name, phone, json.dumps({"shw1b": True, "tag": TAG})),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active', phone=%s, name=%s WHERE company_code=%s AND employee_key=%s",
                    (phone, name, COMPANY, key),
                )
            conn.commit()


def quarantine_known_orphans() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            for sid in sorted(ORPHAN_ALLOWLIST):
                cur.execute(
                    "SELECT * FROM shift_assignments WHERE company_code=%s AND shift_id=%s",
                    (COMPANY, sid),
                )
                row = cur.fetchone()
                if not row:
                    check(f"orphan {sid} present", False, "missing")
                    continue
                shift = dict(row)
                # Never quarantine a valid employee assignment
                cur.execute(
                    "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, shift.get("employee_key")),
                )
                if cur.fetchone():
                    check(f"orphan {sid} not a valid employee", False, "employee_exists")
                    continue
                if str(shift.get("status")) == "cancelled":
                    check(f"orphan {sid} already cancelled", True)
                    IDS["orphan_shift_ids"].append(sid)
                    continue
                q = sw1.quarantine_orphan_shift(
                    cur,
                    company_code=COMPANY,
                    shift=shift,
                    actor_phone=ACTOR,
                    reason="orphan_employee_key",
                    record_event=app.record_shift_event,
                )
                ok = q.get("ok") is True
                check(f"orphan quarantine {sid}", ok, q)
                if ok:
                    IDS["orphan_shift_ids"].append(sid)
                    qid = str((q.get("quarantine") or {}).get("quarantine_id") or "")
                    if qid:
                        IDS["quarantine_ids"].append(qid)
                    cur.execute(
                        "SELECT count(*) AS c FROM shift_events WHERE shift_id=%s AND event_type='orphan_quarantined'",
                        (sid,),
                    )
                    check(f"orphan audit event {sid}", int(dict(cur.fetchone())["c"]) >= 1)
                    cur.execute(
                        """
                        SELECT status FROM shift_lifecycle_flags
                        WHERE shift_id=%s AND flag_type='orphan_employee_key'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (sid,),
                    )
                    fr = cur.fetchone()
                    check(f"orphan lifecycle flag {sid}", fr and dict(fr).get("status") == "open")
            # Confirm no valid employee assignment changed among non-allowlist scheduled
            cur.execute(
                """
                SELECT shift_id::text FROM shift_assignments
                WHERE company_code=%s AND status='scheduled'
                  AND employee_key IN (SELECT employee_key FROM employees WHERE company_code=%s)
                """,
                (COMPANY, COMPANY),
            )
            valid_scheduled = {dict(r)["shift_id"] for r in cur.fetchall()}
            check("no allowlist collision with valid employees", not (valid_scheduled & ORPHAN_ALLOWLIST))
            conn.commit()


def cleanup_synthetics() -> dict[str, Any]:
    """Shared Wave1/Wave2 dependency-aware cleanup. Residual must be zero — no operator mop-up."""
    return cleanup_synthetic_scope(
        app.db_connect,
        wave1b_scope(company_code=COMPANY, tag=TAG),
        known_ids=IDS,
    )


def main() -> int:
    print(f"shifts wave1b prod synthetic canary tag={TAG}", flush=True)
    # Stub WhatsApp
    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
    app.notify_employee_shift_cancelled = lambda **k: {"ok": True, "stub": True}
    app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}

    check("version 1.1.0", sw1.SHIFTS_WAVE1_VERSION == "1.1.0")
    check("wave1 enabled", sw1.shifts_wave1_enabled())
    check("authority_scope_within_approved_boundary", _shifts_w6c.authority_scope_within_approved_boundary())
    check("company WATHEFNI", sw1.shifts_authority_enabled_for_company("WATHEFNI"))
    check("other company gated", not sw1.shifts_authority_enabled_for_company("OTHERCO"))
    check("SHW1B marker synthetic", sw1.is_shift_synthetic_employee(employee_key=EMP_KEY, phone=PHONE))
    check("real employee not synthetic", not sw1.is_shift_synthetic_employee(employee_key="WATHEFNI-96550252254", phone="96550252254"))
    ingest = (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "off").lower()
    check("CAPTURE_INGEST off", ingest in {"off", "0", "false", "no", ""})

    # Unit lifecycle matrix
    base = {
        "block_terminated": True,
        "block_suspended": True,
        "block_future_start": True,
        "block_notice_period": False,
        "garden_leave_during_notice": False,
        "beyond_end_mode": "require_ack",
    }
    start_d = date(2026, 9, 1)
    end_d = date(2026, 9, 30)
    before = sw1.shift_window(date(2026, 8, 31), "09:00", "17:00")
    on_start = sw1.shift_window(start_d, "09:00", "17:00")
    mid_notice = sw1.shift_window(date(2026, 9, 15), "09:00", "17:00")
    in_sus = sw1.shift_window(date(2026, 9, 11), "09:00", "17:00")
    overnight_past = sw1.shift_window(end_d, "22:00", "06:00")
    assert before and on_start and mid_notice and in_sus and overnight_past
    facts_future = {"lifecycle_state": "pending_start", "start_date": start_d, "hub_status": "active"}
    check(
        "future_start blocks before",
        (sw1.evaluate_shift_lifecycle(facts=facts_future, shift_start=before[0], shift_end=before[1], settings=base) or {}).get("lifecycle")
        == "future_start",
    )
    check(
        "future_start allows on start",
        sw1.evaluate_shift_lifecycle(facts=facts_future, shift_start=on_start[0], shift_end=on_start[1], settings=base) is None,
    )
    facts_notice = {
        "lifecycle_state": "notice_period",
        "start_date": date(2026, 1, 1),
        "notice_starts_on": date(2026, 9, 1),
        "last_working_day": end_d,
        "end_date": end_d,
        "hub_status": "active",
    }
    check(
        "notice allows through end",
        sw1.evaluate_shift_lifecycle(facts=facts_notice, shift_start=mid_notice[0], shift_end=mid_notice[1], settings=base) is None,
    )
    garden = dict(base, garden_leave_during_notice=True)
    check(
        "garden leave blocks notice",
        (sw1.evaluate_shift_lifecycle(facts=facts_notice, shift_start=mid_notice[0], shift_end=mid_notice[1], settings=garden) or {}).get("lifecycle")
        == "notice_period",
    )
    facts_sus = {
        "lifecycle_state": "suspended",
        "start_date": date(2026, 1, 1),
        "suspended_on": date(2026, 9, 10),
        "suspension_ends_on": date(2026, 9, 12),
        "hub_status": "suspended",
    }
    check(
        "suspended overlap blocks",
        (sw1.evaluate_shift_lifecycle(facts=facts_sus, shift_start=in_sus[0], shift_end=in_sus[1], settings=base) or {}).get("lifecycle")
        == "suspended",
    )
    facts_term = {"lifecycle_state": "terminated", "start_date": date(2026, 1, 1), "end_date": end_d, "hub_status": "terminated"}
    check(
        "overnight past employment end fails closed",
        (sw1.evaluate_shift_lifecycle(facts=facts_term, shift_start=overnight_past[0], shift_end=overnight_past[1], settings=base) or {}).get("lifecycle")
        == "beyond_employment_end",
    )
    a_win = att.shift_window(end_d, "22:00", "06:00")
    check("Attendance overnight parity", a_win == overnight_past)

    create_src = inspect.getsource(app.create_shift_assignment_for_employee)
    check("no leave_balances mutation", "leave_balances" not in create_src)
    check("no payroll money calc", "bank_transfer" not in create_src.lower())
    check("honesty payroll_money false", sw1.honesty_payload().get("payroll_money") is False)

    dist_root = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    token_hit = False
    if dist_root.is_dir():
        for asset in dist_root.glob("assets/*.js"):
            if "expected_updated_at" in asset.read_text(errors="ignore"):
                token_hit = True
                break
    check("dashboard dist expected_updated_at", token_hit)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)
            before = fingerprint(cur)
    (EVID / "fingerprint-before.json").write_text(json.dumps({k: before[k] for k in before if k not in {"assigns", "events"}}, indent=2))
    baseline_fps = dict(before["assignment_fps"])

    quarantine_known_orphans()
    seed_employees()

    # Prove real employee create is not Wave1-gated overnight (legacy reject) while synth works
    today = date.today()
    shift_day = today + timedelta(days=21)

    unknown = app.create_shift_assignment(
        {"employee_key": f"WATHEFNI-MISSING-{TAG}", "date": shift_day.isoformat(), "start_time": "09:00", "end_time": "17:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("unknown employee fail-closed", unknown.get("ok") is False, unknown.get("error"))

    idem = f"shw1b-create-{TAG}"
    created = app.create_shift_assignment(
        {
            "employee_key": EMP_KEY,
            "date": shift_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "break_minutes": 45,
            "site_key": "HQ",
            "branch_key": "KUWAIT",
            "team_key": "OPS",
            "idempotency_key": idem,
        },
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("same-day create", created.get("ok") is True, created.get("error"))
    track_shift(created)
    row = (created.get("created") or [{}])[0]
    sid = str(row.get("shift_id") or "")
    check("break_minutes", row.get("break_minutes") == 45)
    check("site_key", row.get("site_key") == "HQ")

    dup = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": shift_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "idempotency_key": idem},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("idempotent create", dup.get("ok") is True and dup.get("idempotent") is True)

    split_a = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=1)).isoformat(), "start_time": "09:00", "end_time": "13:00", "idempotency_key": f"shw1b-sa-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    split_b = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=1)).isoformat(), "start_time": "14:00", "end_time": "18:00", "idempotency_key": f"shw1b-sb-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(split_a)
    track_shift(split_b)
    check("split morning", split_a.get("ok") is True, split_a.get("error"))
    check("split afternoon", split_b.get("ok") is True, split_b.get("error"))
    overlap = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=1)).isoformat(), "start_time": "12:00", "end_time": "15:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(overlap)
    check("split overlap detected", overlap.get("ok") is False or bool(overlap.get("conflicts")))

    overnight = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=2)).isoformat(), "start_time": "22:00", "end_time": "06:00", "idempotency_key": f"shw1b-on-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(overnight)
    on_row = (overnight.get("created") or [{}])[0]
    on_id = str(on_row.get("shift_id") or "")
    check("overnight create", overnight.get("ok") is True, overnight.get("error"))
    check("overnight ends_next_day", on_row.get("ends_next_day") is True)
    next_morn = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=3)).isoformat(), "start_time": "05:00", "end_time": "09:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(next_morn)
    check("cross-midnight overlap", next_morn.get("ok") is False or bool(next_morn.get("conflicts")))

    # Dashboard overnight reschedule + concurrency
    owner_ctx = {
        "company_code": COMPANY,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw1b-{TAG}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw1b-{TAG}",
        "permission_subject_company": COMPANY,
        "actor_role": "owner",
        "hr_phone": ACTOR,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }
    if on_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM shift_assignments WHERE shift_id=%s", (on_id,))
                cur_row = dict(cur.fetchone())
        expected_iso = cur_row["updated_at"].isoformat() if hasattr(cur_row["updated_at"], "isoformat") else str(cur_row["updated_at"])
        try:
            resched = app.dashboard_posthire_reschedule_shift(
                on_id,
                app.ShiftRescheduleRequest(
                    shift_date=str(cur_row["shift_date"]),
                    start_time="21:00",
                    end_time="05:00",
                    expected_updated_at=expected_iso,
                ),
                context=owner_ctx,
            )
            check("dashboard overnight reschedule", resched.get("ok") is True, resched)
        except app.HTTPException as exc:
            check("dashboard overnight reschedule", False, getattr(exc, "detail", exc))
        try:
            app.dashboard_posthire_reschedule_shift(
                on_id,
                app.ShiftRescheduleRequest(
                    shift_date=str(cur_row["shift_date"]),
                    start_time="20:00",
                    end_time="04:00",
                    expected_updated_at=expected_iso,
                ),
                context=owner_ctx,
            )
            check("stale reschedule denied", False)
        except app.HTTPException as exc:
            check("stale reschedule denied", exc.status_code == 409)

    # Concurrent winner
    r_create = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": (shift_day + timedelta(days=6)).isoformat(), "start_time": "10:00", "end_time": "18:00", "idempotency_key": f"shw1b-race-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(r_create)
    r_shift = (r_create.get("created") or [{}])[0]
    r_id = str(r_shift.get("shift_id") or "")
    updated_at = r_shift.get("updated_at")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE shift_assignments SET start_time='11:00', end_time='19:00', updated_at=now(), row_version=COALESCE(row_version,1)+1
                WHERE shift_id=%s AND company_code=%s AND status='scheduled' AND updated_at=%s RETURNING shift_id
                """,
                (r_id, COMPANY, updated_at),
            )
            winner = cur.fetchone()
            cur.execute(
                """
                UPDATE shift_assignments SET start_time='12:00', end_time='20:00', updated_at=now(), row_version=COALESCE(row_version,1)+1
                WHERE shift_id=%s AND company_code=%s AND status='scheduled' AND updated_at=%s RETURNING shift_id
                """,
                (r_id, COMPANY, updated_at),
            )
            loser = cur.fetchone()
            conn.commit()
    check("concurrent reschedule one winner", bool(winner) and not loser)

    # Leave conflict modes
    leave_day = shift_day + timedelta(days=5)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, reason, metadata
                ) VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw1b',%s)
                RETURNING leave_id::text AS leave_id
                """,
                (COMPANY, EMP_KEY, PHONE, f"SHW1B-SYNTH| Emp A {TAG}", leave_day, leave_day, app.Json({"shw1b": True, "tag": TAG})),
            )
            leave_id = dict(cur.fetchone())["leave_id"]
            IDS["leave_ids"].append(leave_id)
            cur.execute("UPDATE shift_authority_settings SET leave_conflict_mode='require_ack' WHERE company_code=%s", (COMPANY,))
            conn.commit()
    blocked = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": leave_day.isoformat(), "start_time": "09:00", "end_time": "17:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("leave require_ack", blocked.get("error") in {"shift_leave_conflict_ack_required", "shift_leave_conflict"}, blocked.get("error"))
    acked = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": leave_day.isoformat(), "start_time": "09:00", "end_time": "17:00", "ack_leave_conflict": True, "idempotency_key": f"shw1b-leave-ack-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(acked)
    check("leave ack allows", acked.get("ok") is True, acked.get("error"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE shift_authority_settings SET leave_conflict_mode='block' WHERE company_code=%s", (COMPANY,))
            conn.commit()
    blocked2 = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": leave_day.isoformat(), "start_time": "10:00", "end_time": "12:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("leave block mode", blocked2.get("error") == "shift_leave_conflict", blocked2.get("error"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE shift_authority_settings SET leave_conflict_mode='cancel_shift' WHERE company_code=%s", (COMPANY,))
            conn.commit()
    cancel_mode = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": leave_day.isoformat(), "start_time": "13:00", "end_time": "15:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("leave cancel_shift mode requires ack", cancel_mode.get("error") == "shift_leave_conflict_ack_required", cancel_mode.get("error"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE shift_authority_settings SET leave_conflict_mode='require_ack' WHERE company_code=%s", (COMPANY,))
            conn.commit()

    # Cancel idempotent
    c1 = app.cancel_shift_assignment({"employee_key": EMP_KEY, "shift_id": sid}, company_code=COMPANY, created_by_phone=ACTOR)
    c2 = app.cancel_shift_assignment({"employee_key": EMP_KEY, "shift_id": sid}, company_code=COMPANY, created_by_phone=ACTOR)
    check("cancel ok", c1.get("ok") is True, c1)
    check("cancel idempotent", c2.get("ok") is True and c2.get("idempotent") is True)

    # Swap E2E
    swap_day = shift_day + timedelta(days=9)
    req = app.create_shift_assignment(
        {"employee_key": EMP_KEY, "date": swap_day.isoformat(), "start_time": "08:00", "end_time": "12:00", "idempotency_key": f"shw1b-swap-a-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    tgt = app.create_shift_assignment(
        {"employee_key": EMP_KEY_B, "date": swap_day.isoformat(), "start_time": "13:00", "end_time": "17:00", "idempotency_key": f"shw1b-swap-b-{TAG}"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    track_shift(req)
    track_shift(tgt)
    req_sid = str(((req.get("created") or [{}])[0]).get("shift_id") or "")
    tgt_sid = str(((tgt.get("created") or [{}])[0]).get("shift_id") or "")
    swap_req = app.request_shift_swap(
        {
            "employee_key": EMP_KEY,
            "employee_phone": PHONE,
            "target_phone": PHONE_B,
            "target_employee_key": EMP_KEY_B,
            "target_employee_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"SHW1B swap {TAG}",
            "company_code": COMPANY,
        },
        company_code=COMPANY,
        created_by_phone=PHONE,
    )
    check("swap request", swap_req.get("ok") is True, swap_req.get("error"))
    swap_id = str((swap_req.get("swap") or {}).get("swap_id") or "")
    if swap_id:
        IDS["swap_ids"].append(swap_id)
    self_dec = app.approve_shift_swap({"swap_id": swap_id, "company_code": COMPANY}, company_code=COMPANY, created_by_phone=PHONE)
    check("swap self-denial", self_dec.get("error") == "self_swap_decision_forbidden", self_dec.get("error"))
    scoped = app.reject_shift_swap({"swap_id": swap_id, "company_code": COMPANY}, company_code=COMPANY, created_by_phone=ACTOR, account_id=None)
    check("swap scoped decision", scoped.get("ok") is True, scoped.get("error"))
    replay = app.reject_shift_swap({"swap_id": swap_id, "company_code": COMPANY}, company_code=COMPANY, created_by_phone=ACTOR, account_id=None)
    check("swap idempotent replay", replay.get("ok") is True and replay.get("idempotent") is True, replay)
    swap2 = app.request_shift_swap(
        {
            "employee_key": EMP_KEY_B,
            "employee_phone": PHONE_B,
            "target_employee_key": EMP_KEY,
            "target_phone": PHONE,
            "target_employee_phone": PHONE,
            "shift_id": tgt_sid,
            "target_shift_id": req_sid,
            "date": swap_day.isoformat(),
            "reason": f"SHW1B swap2 {TAG}",
            "company_code": COMPANY,
        },
        company_code=COMPANY,
        created_by_phone=PHONE_B,
    )
    swap2_id = str((swap2.get("swap") or {}).get("swap_id") or "")
    if swap2_id:
        IDS["swap_ids"].append(swap2_id)
    first = app.approve_shift_swap({"swap_id": swap2_id, "company_code": COMPANY}, company_code=COMPANY, created_by_phone=ACTOR, account_id=None)
    check("swap first wins", first.get("ok") is True, first.get("error"))
    second = app.reject_shift_swap({"swap_id": swap2_id, "company_code": COMPANY}, company_code=COMPANY, created_by_phone=ACTOR, account_id=None)
    check(
        "swap stale second",
        second.get("ok") is False or second.get("idempotent") is True or second.get("error") in {"stale_swap_decision", "shift_swap_not_found"},
        second,
    )

    # Tenant isolation
    cross = app.create_shift_assignment_for_employee(
        {"date": shift_day.isoformat(), "start_time": "09:00", "end_time": "12:00"},
        employee={"employee_key": EMP_KEY, "company_code": "OTHER", "phone": PHONE, "name": "x"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("tenant isolation", cross.get("error") == "employee_company_mismatch")

    # Terminated lifecycle (synthetic)
    term_key = f"WATHEFNI-SHW1B-TERM-{TAG}"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb, now(), now()) ON CONFLICT DO NOTHING
                """,
                (COMPANY, term_key, f"SHW1B-SYNTH| Term {TAG}", f"965529{_digits[:5]}8", json.dumps({"shw1b": True, "tag": TAG})),
            )
            cur.execute("UPDATE employees SET employment_status='terminated' WHERE company_code=%s AND employee_key=%s", (COMPANY, term_key))
            conn.commit()
    term = app.create_shift_assignment(
        {"employee_key": term_key, "date": (shift_day + timedelta(days=8)).isoformat(), "start_time": "09:00", "end_time": "17:00"},
        company_code=COMPANY,
        created_by_phone=ACTOR,
    )
    check("lifecycle terminated blocks", term.get("ok") is False, term.get("error"))

    cleanup = cleanup_synthetics()
    (EVID / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
    check("residual synthetic zero", cleanup.get("residual_total") == 0, cleanup)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = fingerprint(cur)
    (EVID / "fingerprint-after.json").write_text(json.dumps({k: after[k] for k in after if k not in {"assigns", "events"}}, indent=2))

    # Real fingerprints unchanged except allowlisted orphans (status/updated_at may change) + their new audit events
    drift = []
    for sid_k, fp in baseline_fps.items():
        if sid_k in ORPHAN_ALLOWLIST:
            continue
        if after["assignment_fps"].get(sid_k) != fp:
            drift.append(sid_k)
    check("real assignment fingerprints unchanged except orphans", not drift, drift)

    for sid_k in ORPHAN_ALLOWLIST:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (sid_k,))
                row = cur.fetchone()
                st = dict(row).get("status") if row else None
        check(f"orphan {sid_k} soft-cancelled", st == "cancelled", st)

    out = {
        "passed": PASS,
        "failed": FAIL,
        "tag": TAG,
        "ids": IDS,
        "cleanup": cleanup,
        "results": RESULTS,
        "orphan_allowlist": sorted(ORPHAN_ALLOWLIST),
    }
    (EVID / "qualification.json").write_text(json.dumps(out, indent=2, default=str))
    (EVID / "synthetic-ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
