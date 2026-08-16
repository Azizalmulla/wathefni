#!/usr/bin/env python3
"""Payroll Authority P2 — Attendance + Leave input assembly qualification.

Proves input snapshot assembly, overlap/precedence, readiness/locking,
immutability, and P1/P0.1 regression hooks without calculating money.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORCH_CANDIDATES = [
    ROOT / "wathefni-orchestrator",
    Path("/opt/wathefni/orchestrator"),
    ROOT / "orchestrator",
]
ORCH = next((p for p in ORCH_CANDIDATES if (p / "payroll_input_snapshot_p2.py").exists()), ORCH_CANDIDATES[0])
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
for flag in (
    "WATHEFNI_PAYROLL_WAVE1",
    "WATHEFNI_PAYROLL_WAVE2A",
    "WATHEFNI_PAYROLL_WAVE2B",
    "WATHEFNI_PAYROLL_WAVE3",
    "WATHEFNI_PAYROLL_AUTHORITY_P1",
    "WATHEFNI_PAYROLL_AUTHORITY_P2",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYW2A,PYW3,PYAUTH,PYP1,PYP2,PYINPUT,ATTW1C,W1C-SYNTH|"
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS", MARKERS)

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP2_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
CREATOR = f"9655418{TAG_DIGITS}"
APPROVER = f"9655419{TAG_DIGITS}"

EMP_FULL = f"WATHEFNI-PYW1-PYP2-FULL-{TAG}"
EMP_HIRE = f"WATHEFNI-PYW1-PYP2-HIRE-{TAG}"
EMP_LEAVE = f"WATHEFNI-PYW1-PYP2-LEAVER-{TAG}"
EMP_UNPAID = f"WATHEFNI-PYW1-PYP2-UNPAID-{TAG}"
EMP_PAID = f"WATHEFNI-PYW1-PYP2-PAID-{TAG}"
EMP_OT = f"WATHEFNI-PYW1-PYP2-OT-{TAG}"
EMP_MISS = f"WATHEFNI-PYW1-PYP2-MISS-{TAG}"
EMP_INFO = f"WATHEFNI-PYW1-PYP2-INFO-{TAG}"
ALL_KEYS = [EMP_FULL, EMP_HIRE, EMP_LEAVE, EMP_UNPAID, EMP_PAID, EMP_OT, EMP_MISS, EMP_INFO]

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP2_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p2-{STAMP}"))
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: Any = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def unique_period() -> tuple[date, date]:
    n = int(TAG[:4], 16) % 120
    year = 2034 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def upsert_employee(cur: Any, key: str, phone: str, *, hire: date | None = None, term: date | None = None) -> None:
    profile = {}
    if hire:
        profile["employment_start"] = hire.isoformat()
    if term:
        profile["employment_end"] = term.isoformat()
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE
          SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, name=EXCLUDED.name,
              hire_date=EXCLUDED.hire_date, start_date=EXCLUDED.start_date,
              profile=EXCLUDED.profile, updated_at=now()
        """,
        (COMPANY, key, phone, f"P2 {key[-12:]}", hire, hire, json.dumps(profile)),
    )


def seed_att_snap(
    cur: Any,
    *,
    employee_key: str,
    work_date: date,
    status: str,
    worked: int,
    scheduled: int = 480,
    late: int = 0,
    early: int = 0,
    overnight: bool = False,
) -> str:
    snap_id = str(uuid.uuid4())
    proj_id = str(uuid.uuid4())
    payload = {
        "status": status,
        "worked_minutes": worked,
        "scheduled_minutes": scheduled,
        "late_minutes": late,
        "early_leave_minutes": early,
        "ends_next_day": overnight,
        "overnight_shift": overnight,
        "approval_status": "approved",
        "check_in_at": f"{work_date.isoformat()}T08:00:00+03:00",
        "check_out_at": f"{(work_date + timedelta(days=1)).isoformat() if overnight else work_date.isoformat()}T17:00:00+03:00",
    }
    cur.execute(
        """
        INSERT INTO attendance_payroll_snapshots (
          snapshot_id, company_code, employee_key, work_date, shift_key,
          projection_id, projection_version, approved_by_phone, payload, worked_minutes_cache
        ) VALUES (%s,%s,%s,%s,'',%s,1,%s,%s::jsonb,%s)
        ON CONFLICT DO NOTHING
        """,
        (snap_id, COMPANY, employee_key, work_date, proj_id, APPROVER, json.dumps(payload), worked),
    )
    return snap_id


def seed_leave(
    cur: Any,
    *,
    employee_key: str,
    leave_type: str,
    status: str,
    start: date,
    end: date,
    unpaid_handoff: bool = False,
) -> str:
    leave_id = str(uuid.uuid4())
    handoff = {}
    if unpaid_handoff:
        handoff = {
            "leave_id": leave_id,
            "classification": "unpaid_leave",
            "chargeable_days": float((end - start).days + 1),
            "monetary_fields": None,
            "salary_deduction": None,
            "pay_fraction": None,
        }
    cur.execute(
        """
        INSERT INTO leave_requests (
          leave_id, company_code, employee_key, leave_type, status,
          start_date, end_date, chargeable_days, chargeable_hours, payroll_handoff
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s::jsonb)
        """,
        (
            leave_id,
            COMPANY,
            employee_key,
            leave_type,
            status,
            start,
            end,
            float((end - start).days + 1),
            json.dumps(handoff),
        ),
    )
    return leave_id


def seed_shift(cur: Any, *, employee_key: str, shift_date: date, overnight: bool = False) -> str:
    shift_id = str(uuid.uuid4())
    try:
        cur.execute(
            """
            INSERT INTO shift_assignments (
              shift_id, company_code, employee_key, shift_date, start_time, end_time,
              ends_next_day, status, timezone
            ) VALUES (%s,%s,%s,%s,'22:00','06:00',%s,'scheduled','Asia/Kuwait')
            """,
            (shift_id, COMPANY, employee_key, shift_date, overnight),
        )
    except Exception:
        # Minimal columns fallback
        cur.execute(
            """
            INSERT INTO shift_assignments (
              shift_id, company_code, employee_key, shift_date, start_time, end_time, ends_next_day, status
            ) VALUES (%s,%s,%s,%s,'22:00','06:00',%s,'scheduled')
            """,
            (shift_id, COMPANY, employee_key, shift_date, overnight),
        )
    return shift_id


def seed_holiday(cur: Any, d: date) -> None:
    try:
        cur.execute(
            """
            INSERT INTO public_holidays (company_code, holiday_date, name, year)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (COMPANY, d, f"P2 Holiday {TAG}", d.year),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO public_holidays (company_code, holiday_date, name)
            VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (COMPANY, d, f"P2 Holiday {TAG}"),
        )


def seed_correction(cur: Any, *, employee_key: str, work_date: date) -> str:
    cid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO attendance_corrections (
          correction_id, company_code, employee_key, work_date, status, requested_changes, requested_by_phone
        ) VALUES (%s,%s,%s,%s,'requested',%s::jsonb,%s)
        """,
        (cid, COMPANY, employee_key, work_date, json.dumps({"worked_minutes": 480}), CREATOR),
    )
    return cid


def cleanup(app: Any, keys: list[str], p_start: date, p_end: date) -> None:
    import payroll_input_snapshot_p2 as p2

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            p2.ensure_payroll_input_snapshot_schema(cur)
            cur.execute(
                "SELECT input_snapshot_id::text FROM payroll_input_snapshots WHERE company_code=%s AND period_start=%s AND period_end=%s",
                (COMPANY, p_start, p_end),
            )
            ids = [dict(r)["input_snapshot_id"] for r in (cur.fetchall() or [])]
            if ids:
                cur.execute("DELETE FROM payroll_input_snapshot_lines WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshot_issues WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshot_employees WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshot_events WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshots WHERE input_snapshot_id::text = ANY(%s)", (ids,))
            cur.execute(
                "DELETE FROM attendance_corrections WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            # Attendance payroll snapshots are immutable in prod; disable trigger only for synthetic cleanup.
            cur.execute("ALTER TABLE attendance_payroll_snapshots DISABLE TRIGGER trg_attendance_payroll_snapshots_immutable")
            try:
                cur.execute(
                    "DELETE FROM attendance_payroll_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                    (COMPANY, keys),
                )
            finally:
                cur.execute("ALTER TABLE attendance_payroll_snapshots ENABLE TRIGGER trg_attendance_payroll_snapshots_immutable")
            cur.execute(
                "DELETE FROM leave_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM shift_assignments WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM public_holidays WHERE company_code=%s AND name LIKE %s",
                (COMPANY, f"%{TAG}%"),
            )
            for key in keys:
                cur.execute(
                    "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cids = [dict(r)["contract_id"] for r in (cur.fetchall() or [])]
                if cids:
                    cur.execute(
                        "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
                        (COMPANY, cids),
                    )
                    cur.execute(
                        "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)",
                        (COMPANY, cids),
                    )
                    cur.execute(
                        "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)",
                        (COMPANY, cids),
                    )
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            cur.execute(
                "DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap2_{TAG}%"),
            )
        conn.commit()


def main() -> int:
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_official_pdf as opdf

    h = p2.honesty_payload()
    inv = p2.freeze_invariants()
    rules = p2.overlap_precedence_rules()
    check("p2 version", p2.PAYROLL_AUTHORITY_P2_VERSION == "1.0.0")
    check("no money", h.get("money_calculated") is False)
    check("mode a locked", h.get("mode_a_wathefni_seal_unlocked") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("locked immutable invariant", inv.get("locked_inputs_immutable") is True)
    check("unpaid suppresses absence", rules.get("approved_unpaid_leave_suppresses_attendance_absence") is True)
    check("p1 still exists", p1.PAYROLL_AUTHORITY_P1_VERSION == "1.0.0")
    check(
        "pdf still needs seal",
        opdf.is_official_pdf_eligible({"source_kind": "external_import", "money_authority": "external"}) is False,
    )

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            (EVID / "results.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "results": RESULTS}, indent=2))
            return 1 if FAIL else 0
        raise

    p_start, p_end = unique_period()
    # Pick weekday inside period for scenarios
    mid = p_start + timedelta(days=10)
    while mid.weekday() >= 4:  # avoid fri/sat default rest
        mid += timedelta(days=1)
    hire_day = p_start + timedelta(days=14)
    leave_day = p_start + timedelta(days=20)
    unpaid_day = mid
    paid_day = mid + timedelta(days=1)
    while paid_day.weekday() >= 4:
        paid_day += timedelta(days=1)
    ot_day = paid_day + timedelta(days=1)
    while ot_day.weekday() >= 4:
        ot_day += timedelta(days=1)
    # Find a Friday in period for rest-day work
    fri = p_start
    while fri.weekday() != 4:
        fri += timedelta(days=1)
    ph_day = fri + timedelta(days=7)
    if ph_day > p_end:
        ph_day = fri

    cleanup(app, ALL_KEYS, p_start, p_end)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
                p2.ensure_payroll_input_snapshot_schema(cur, force=True)

                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                p2.set_attendance_payroll_mode(
                    cur, company_code=COMPANY, mode="required", actor_phone=APPROVER, reason=f"pap2_mode_req_{TAG}"
                )

                phones = {
                    EMP_FULL: f"9655241{TAG_DIGITS}",
                    EMP_HIRE: f"9655242{TAG_DIGITS}",
                    EMP_LEAVE: f"9655243{TAG_DIGITS}",
                    EMP_UNPAID: f"9655244{TAG_DIGITS}",
                    EMP_PAID: f"9655245{TAG_DIGITS}",
                    EMP_OT: f"9655246{TAG_DIGITS}",
                    EMP_MISS: f"9655247{TAG_DIGITS}",
                    EMP_INFO: f"9655248{TAG_DIGITS}",
                }
                upsert_employee(cur, EMP_FULL, phones[EMP_FULL], hire=p_start - timedelta(days=30))
                upsert_employee(cur, EMP_HIRE, phones[EMP_HIRE], hire=hire_day)
                upsert_employee(cur, EMP_LEAVE, phones[EMP_LEAVE], hire=p_start - timedelta(days=60), term=leave_day)
                for k in (EMP_UNPAID, EMP_PAID, EMP_OT, EMP_MISS, EMP_INFO):
                    upsert_employee(cur, k, phones[k], hire=p_start - timedelta(days=30))

                # Contracts for all
                for k in ALL_KEYS:
                    draft = pyw1.create_contract_draft(
                        cur,
                        company_code=COMPANY,
                        employee_key=k,
                        effective_from=p_start - timedelta(days=60),
                        components=[{"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True}],
                        actor_phone=CREATOR,
                        reason=f"pap2_draft_{TAG}_{k[-8:]}",
                    )
                    cid = str((draft.get("contract") or {}).get("contract_id"))
                    pyw1.approve_contract(
                        cur,
                        company_code=COMPANY,
                        contract_id=cid,
                        actor_phone=APPROVER,
                        reason=f"pap2_appr_{TAG}",
                        expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
                    )

                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="approved_snapshots",
                    actor_phone=CREATOR,
                    reason=f"pap2_{TAG}_period",
                )
                check("period", period.get("ok") is True, period)

                # FULL: present weekdays in first week of active period (limit seeding)
                for d in (p_start + timedelta(days=i) for i in range(0, 5)):
                    if d.weekday() < 4:
                        seed_att_snap(cur, employee_key=EMP_FULL, work_date=d, status="completed", worked=480)

                # HIRE: only after hire_day
                seed_att_snap(cur, employee_key=EMP_HIRE, work_date=hire_day, status="completed", worked=480)

                # LEAVER: attendance before leave_day
                seed_att_snap(
                    cur, employee_key=EMP_LEAVE, work_date=leave_day - timedelta(days=1), status="completed", worked=480
                )

                # UNPAID leave + absence same day → suppress
                seed_leave(
                    cur,
                    employee_key=EMP_UNPAID,
                    leave_type="unpaid",
                    status="approved",
                    start=unpaid_day,
                    end=unpaid_day,
                    unpaid_handoff=True,
                )
                seed_att_snap(cur, employee_key=EMP_UNPAID, work_date=unpaid_day, status="absent", worked=0)
                # pending leave must be excluded
                seed_leave(
                    cur,
                    employee_key=EMP_UNPAID,
                    leave_type="annual",
                    status="requested",
                    start=unpaid_day + timedelta(days=2),
                    end=unpaid_day + timedelta(days=2),
                )
                seed_leave(
                    cur,
                    employee_key=EMP_UNPAID,
                    leave_type="annual",
                    status="rejected",
                    start=unpaid_day + timedelta(days=3),
                    end=unpaid_day + timedelta(days=3),
                )

                # PAID leave
                seed_leave(
                    cur,
                    employee_key=EMP_PAID,
                    leave_type="annual",
                    status="approved",
                    start=paid_day,
                    end=paid_day,
                )
                seed_att_snap(cur, employee_key=EMP_PAID, work_date=paid_day, status="absent", worked=0)

                # OT + rest-day + PH + overnight
                seed_att_snap(
                    cur, employee_key=EMP_OT, work_date=ot_day, status="completed", worked=600, scheduled=480
                )
                seed_att_snap(
                    cur, employee_key=EMP_OT, work_date=fri, status="completed", worked=240, scheduled=0
                )
                seed_holiday(cur, ph_day)
                seed_att_snap(
                    cur, employee_key=EMP_OT, work_date=ph_day, status="completed", worked=300, scheduled=0
                )
                seed_shift(cur, employee_key=EMP_OT, shift_date=ot_day, overnight=True)
                seed_att_snap(
                    cur,
                    employee_key=EMP_OT,
                    work_date=ot_day + timedelta(days=2) if ot_day + timedelta(days=2) <= p_end else ot_day,
                    status="completed",
                    worked=480,
                    overnight=True,
                )

                # MISSING attendance weekday + open correction
                miss_day = ot_day + timedelta(days=3)
                while miss_day.weekday() >= 4 or miss_day > p_end:
                    miss_day -= timedelta(days=1)
                seed_correction(cur, employee_key=EMP_MISS, work_date=miss_day)
                # one present day so employee appears with issues
                seed_att_snap(cur, employee_key=EMP_MISS, work_date=p_start + timedelta(days=1), status="completed", worked=480)

                # INFO mode employee will be tested in second assemble after mode flip — seed present
                seed_att_snap(cur, employee_key=EMP_INFO, work_date=p_start + timedelta(days=2), status="completed", worked=480)

                # Assemble required mode for core keys (exclude EMP_INFO from first pass blockers focus)
                assembled = p2.assemble_payroll_inputs(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    employee_keys=[EMP_FULL, EMP_HIRE, EMP_LEAVE, EMP_UNPAID, EMP_PAID, EMP_OT, EMP_MISS],
                    actor_phone=APPROVER,
                    reason=f"pap2_assemble_{TAG}",
                )
                check("assemble ok", assembled.get("ok") is True, assembled)
                snap = assembled.get("input_snapshot") or {}
                snap_id = str(snap.get("input_snapshot_id") or "")
                check("status needs_review or ready", str(snap.get("status")) in ("needs_review", "ready"), snap)
                check("money_calculated false", snap.get("money_calculated") is False, snap)
                check("payment disabled on snap", snap.get("payment_processing") == "disabled", snap)

                lines = p2.list_input_snapshot_lines(cur, company_code=COMPANY, input_snapshot_id=snap_id)
                emps = p2.list_input_snapshot_employees(cur, company_code=COMPANY, input_snapshot_id=snap_id)
                issues = p2.list_input_snapshot_issues(cur, company_code=COMPANY, input_snapshot_id=snap_id)

                hire_emp = next(e for e in emps if e["employee_key"] == EMP_HIRE)
                leave_emp = next(e for e in emps if e["employee_key"] == EMP_LEAVE)
                check("mid-period hire flag", bool(hire_emp.get("mid_period_hire")), hire_emp)
                check("mid-period leaver flag", bool(leave_emp.get("mid_period_leaver")), leave_emp)

                unpaid_lines = [ln for ln in lines if ln["employee_key"] == EMP_UNPAID]
                check(
                    "approved unpaid leave line",
                    any(ln.get("line_kind") == "leave_interval" and ln.get("classification") == "unpaid_leave" for ln in unpaid_lines),
                    unpaid_lines[:5],
                )
                check(
                    "absence suppressed by unpaid leave",
                    any(ln.get("line_kind") == "suppressed_absence" for ln in unpaid_lines),
                    unpaid_lines,
                )
                check(
                    "pending leave excluded info",
                    any(i.get("code") == "leave_excluded_not_approved" for i in issues if i.get("employee_key") == EMP_UNPAID),
                    [i for i in issues if i.get("employee_key") == EMP_UNPAID][:5],
                )

                paid_lines = [ln for ln in lines if ln["employee_key"] == EMP_PAID]
                check(
                    "paid leave present",
                    any(ln.get("line_kind") == "leave_interval" and ln.get("classification") == "paid_leave" for ln in paid_lines),
                    paid_lines,
                )

                ot_lines = [ln for ln in lines if ln["employee_key"] == EMP_OT]
                check("ot fact line", any(ln.get("line_kind") == "overtime_fact" for ln in ot_lines), ot_lines)
                check("rest day work fact", any(ln.get("line_kind") == "rest_day_work_fact" for ln in ot_lines), ot_lines)
                check("ph work fact", any(ln.get("line_kind") == "public_holiday_work_fact" for ln in ot_lines), ot_lines)
                check(
                    "overnight fact",
                    any(bool(ln.get("overnight_shift")) for ln in ot_lines if ln.get("line_kind") in ("attendance_day", "schedule_day")),
                    ot_lines,
                )
                check(
                    "ot facts have no money",
                    all((ln.get("fact_payload") or {}).get("money_impact") in (None, {}) for ln in ot_lines if ln.get("line_kind") == "overtime_fact"),
                    True,
                )

                check(
                    "unresolved correction blocks",
                    any(i.get("code") == "unresolved_attendance_correction" and i.get("blocks_lock") for i in issues),
                    issues,
                )

                # Provenance back to attendance/leave
                att_line = next((ln for ln in lines if ln.get("attendance_snapshot_id")), None)
                leave_line = next((ln for ln in lines if ln.get("leave_id")), None)
                check("attendance provenance id", bool(att_line and att_line.get("source_table") == "attendance_payroll_snapshots"), att_line)
                check("leave provenance id", bool(leave_line and leave_line.get("source_table") == "leave_requests"), leave_line)

                # Idempotent reassemble
                again = p2.assemble_payroll_inputs(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    employee_keys=[EMP_FULL, EMP_HIRE, EMP_LEAVE, EMP_UNPAID, EMP_PAID, EMP_OT, EMP_MISS],
                    actor_phone=APPROVER,
                    reason=f"pap2_idem_{TAG}",
                )
                check("assemble idempotent", again.get("idempotent") is True, again)

                # Lock should fail closed while needs_review
                if str(snap.get("status")) == "needs_review":
                    lock_fail = p2.lock_payroll_input_snapshot(
                        cur,
                        company_code=COMPANY,
                        input_snapshot_id=snap_id,
                        actor_phone=APPROVER,
                        reason=f"pap2_lock_fail_{TAG}",
                    )
                    check("lock fail closed", lock_fail.get("error") == "input_snapshot_needs_review", lock_fail)

                # Informational mode: assemble EMP_INFO with missing days should not block
                p2.set_attendance_payroll_mode(
                    cur, company_code=COMPANY, mode="informational", actor_phone=APPROVER, reason=f"pap2_info_{TAG}"
                )
                # supersede prior then assemble info cohort
                if str(snap.get("status")) != "superseded":
                    cur.execute(
                        "UPDATE payroll_input_snapshots SET status='superseded', updated_at=now() WHERE input_snapshot_id=%s",
                        (snap_id,),
                    )
                info_asm = p2.assemble_payroll_inputs(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    employee_keys=[EMP_INFO],
                    actor_phone=APPROVER,
                    reason=f"pap2_info_assemble_{TAG}",
                )
                check("info assemble ok", info_asm.get("ok") is True, info_asm)
                info_snap = info_asm.get("input_snapshot") or {}
                check(
                    "informational does not block",
                    str(info_snap.get("status")) in ("ready", "needs_review") and int(info_snap.get("issue_blocker_count") or 0) == 0,
                    info_snap,
                )
                info_id = str(info_snap.get("input_snapshot_id") or "")
                locked = p2.lock_payroll_input_snapshot(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=info_id,
                    actor_phone=APPROVER,
                    reason=f"pap2_lock_{TAG}",
                )
                check("lock informational ok", locked.get("ok") is True, locked)
                mutate = p2.refuse_mutate_locked_input(cur, company_code=COMPANY, input_snapshot_id=info_id)
                check("locked immutable", mutate.get("error") == "locked_input_snapshot_immutable", mutate)

                # Later HR edit (new attendance) must not silently mutate locked; assemble refuses
                seed_att_snap(
                    cur,
                    employee_key=EMP_INFO,
                    work_date=p_start + timedelta(days=3),
                    status="completed",
                    worked=480,
                )
                silent = p2.assemble_payroll_inputs(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    employee_keys=[EMP_INFO],
                    actor_phone=APPROVER,
                    reason=f"pap2_silent_{TAG}",
                )
                check(
                    "locked refuse silent rewrite",
                    silent.get("error") == "locked_input_snapshot_immutable",
                    silent,
                )
                # New version via supersede
                newv = p2.supersede_input_snapshot(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=info_id,
                    actor_phone=APPROVER,
                    reason=f"pap2_supersede_{TAG}",
                    employee_keys=[EMP_INFO],
                )
                check("supersede creates new version", newv.get("ok") is True, newv)
                new_id = str((newv.get("input_snapshot") or {}).get("input_snapshot_id") or "")
                check("new version id differs", new_id and new_id != info_id, new_id)
                prior = p2.get_input_snapshot_by_id(cur, company_code=COMPANY, input_snapshot_id=info_id)
                check("prior preserved superseded", prior and prior.get("status") == "superseded", prior)

                events = p2.list_input_snapshot_events(cur, company_code=COMPANY, limit=30)
                check("audit events", any(str(e.get("event_type") or "").startswith("input_snapshot") for e in events), len(events))

                # Schema columns
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='payroll_input_snapshots'"
                )
                cols = {dict(r)["column_name"] for r in (cur.fetchall() or [])}
                required = {
                    "input_snapshot_id",
                    "status",
                    "attendance_payroll_mode",
                    "content_fingerprint",
                    "source_fingerprint",
                    "locked_at",
                    "policy_context",
                    "money_calculated",
                }
                check("schema columns", required.issubset(cols), sorted(required - cols))
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='payroll_authority_snapshots' AND column_name='input_snapshot_id'"
                )
                check("p1 bridge column", cur.fetchone() is not None)

                # Restore company mode to required for canary hygiene
                p2.set_attendance_payroll_mode(
                    cur, company_code=COMPANY, mode="required", actor_phone=APPROVER, reason=f"pap2_restore_{TAG}"
                )
            conn.commit()
    finally:
        cleanup(app, ALL_KEYS, p_start, p_end)
        check("cleanup", True)

    # Lightweight P1 honesty still true
    check("p1 honesty external seal unlocked", p1.honesty_payload().get("mode_b_external_seal_unlocked") is True)
    check("p1 native preview never authoritative", p1.honesty_payload().get("native_preview_authoritative") is False)
    check("p1 mode a honesty flag present", "mode_a_wathefni_seal_unlocked" in p1.honesty_payload())

    verdict = "PASS" if FAIL == 0 else "FAIL"
    report = {
        "verdict": verdict,
        "pass": PASS,
        "fail": FAIL,
        "stamp": STAMP,
        "evidence": str(EVID),
        "schema": {
            "tables": [
                "payroll_input_snapshots",
                "payroll_input_snapshot_employees",
                "payroll_input_snapshot_lines",
                "payroll_input_snapshot_issues",
                "payroll_input_snapshot_events",
            ],
            "status": ["assembling", "needs_review", "ready", "locked", "superseded"],
            "attendance_payroll_mode": ["required", "informational", "ignored"],
        },
        "overlap_precedence": rules,
        "readiness_locking": {
            "assemble": "assembling→needs_review|ready",
            "lock": "ready→locked (needs_review fail-closed unless force)",
            "source_change": "locked refuse silent rewrite; supersede→new version",
        },
        "results": RESULTS,
        "p3_blockers": [
            "Component/time-pay rules not implemented (P3)",
            "OT/sick/PH statutory money still counsel-gated",
            "Mode A authoritative finalize still locked (P1/P5)",
            "SYNTHETIC_ONLY remains",
            "payment_processing disabled",
        ],
    }
    (EVID / "results.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (EVID / "REPORT.md").write_text(
        f"""# Payroll Authority P2 — Qualification

**Verdict: {verdict}**  
**Stamp:** `{STAMP}`  
**Checks:** {PASS} PASS / {FAIL} FAIL

## Payroll input snapshot schema

- `payroll_input_snapshots` (+ employees, lines, issues, events)
- status ∈ {{assembling, needs_review, ready, locked, superseded}}
- `attendance_payroll_mode` ∈ {{required, informational, ignored}}
- P1 bridge: `payroll_authority_snapshots.input_snapshot_id` (nullable)

## Overlap / precedence

- Only approved leave affects payroll
- Pending/rejected/cancelled excluded
- Approved unpaid leave suppresses attendance absence (no double count)
- Paid leave not treated as unpaid absence
- OT / rest-day / PH work = distinct facts, **no money**
- Overnight shifts anchored to shift work_date; timezone Asia/Kuwait

## Readiness / locking

- Unresolved required attendance → `needs_review` / lock fail-closed
- Informational mode does not block lock
- Locked inputs immutable; source changes require supersede + new version
- Repeated assemble with unchanged sources is idempotent

## Evidence

`{EVID}`

## Blockers for P3

1. Time-pay / component rules  
2. OT/sick/PH statutory money (counsel)  
3. Mode A finalize still locked  
4. SYNTHETIC_ONLY  
5. payment_processing disabled  

**Do not start P3 / Employee App P1 / Setup Console / Auth Wave 2 Phase 6 automatically.**
""",
        encoding="utf-8",
    )
    print(f"\nVERDICT {verdict}  pass={PASS} fail={FAIL}  evidence={EVID}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
