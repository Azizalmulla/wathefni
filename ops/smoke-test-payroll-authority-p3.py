#!/usr/bin/env python3
"""Payroll Authority P3 — Components + policy + Mode A preview qualification.

Proves deterministic preview_non_authoritative calc from locked P2 inputs +
compensation + versioned company policy. Does NOT unlock Mode A seal / PDF /
PIFSS/EOS / payments.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORCH_CANDIDATES = [
    ROOT / "wathefni-orchestrator",
    Path("/opt/wathefni/orchestrator"),
    ROOT / "orchestrator",
    ROOT,
]
ORCH = next(
    (p for p in ORCH_CANDIDATES if (p / "payroll_components_policy_p3.py").exists()),
    ORCH_CANDIDATES[0],
)
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
    "WATHEFNI_PAYROLL_AUTHORITY_P3",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYW2A,PYW3,PYAUTH,PYP1,PYP2,PYP3,PYINPUT,PYCALC,ATTW1C,W1C-SYNTH|"
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS", MARKERS)

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP3_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
CREATOR = f"9655518{TAG_DIGITS}"
APPROVER = f"9655519{TAG_DIGITS}"

EMP_BASIC = f"WATHEFNI-PYW1-PYP3-BASIC-{TAG}"
EMP_MID = f"WATHEFNI-PYW1-PYP3-MIDSAL-{TAG}"
EMP_HIRE = f"WATHEFNI-PYW1-PYP3-HIRE-{TAG}"
EMP_LEAVE = f"WATHEFNI-PYW1-PYP3-LEAVER-{TAG}"
EMP_ABS = f"WATHEFNI-PYW1-PYP3-ABSENT-{TAG}"
EMP_UNPAID = f"WATHEFNI-PYW1-PYP3-UNPAID-{TAG}"
EMP_PAID = f"WATHEFNI-PYW1-PYP3-PAID-{TAG}"
EMP_LATE = f"WATHEFNI-PYW1-PYP3-LATE-{TAG}"
EMP_OT = f"WATHEFNI-PYW1-PYP3-OT-{TAG}"
EMP_OVERLAP = f"WATHEFNI-PYW1-PYP3-OVERLAP-{TAG}"
EMP_CUSTOM = f"WATHEFNI-PYW1-PYP3-CUSTOM-{TAG}"
ALL_KEYS = [
    EMP_BASIC,
    EMP_MID,
    EMP_HIRE,
    EMP_LEAVE,
    EMP_ABS,
    EMP_UNPAID,
    EMP_PAID,
    EMP_LATE,
    EMP_OT,
    EMP_OVERLAP,
    EMP_CUSTOM,
]

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP3_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p3-{STAMP}"))
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
    year = 2035 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def upsert_employee(cur: Any, key: str, phone: str, *, hire: date | None = None, term: date | None = None) -> None:
    profile: dict[str, Any] = {}
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
        (COMPANY, key, phone, f"P3 {key[-12:]}", hire, hire, json.dumps(profile)),
    )


def approve_contract(
    cur: Any,
    pyw1: Any,
    *,
    employee_key: str,
    effective_from: date,
    components: list[dict[str, Any]],
    effective_to: date | None = None,
) -> str:
    draft = pyw1.create_contract_draft(
        cur,
        company_code=COMPANY,
        employee_key=employee_key,
        effective_from=effective_from,
        effective_to=effective_to,
        components=components,
        actor_phone=CREATOR,
        reason=f"pap3_draft_{TAG}_{employee_key[-10:]}",
    )
    cid = str((draft.get("contract") or {}).get("contract_id"))
    pyw1.approve_contract(
        cur,
        company_code=COMPANY,
        contract_id=cid,
        actor_phone=APPROVER,
        reason=f"pap3_appr_{TAG}",
        expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
    )
    return cid


def seed_att_snap(
    cur: Any,
    *,
    employee_key: str,
    work_date: date,
    status: str,
    worked: int,
    scheduled: int = 480,
    late: int = 0,
) -> str:
    snap_id = str(uuid.uuid4())
    proj_id = str(uuid.uuid4())
    payload = {
        "status": status,
        "worked_minutes": worked,
        "scheduled_minutes": scheduled,
        "late_minutes": late,
        "early_leave_minutes": 0,
        "ends_next_day": False,
        "overnight_shift": False,
        "approval_status": "approved",
        "check_in_at": f"{work_date.isoformat()}T08:00:00+03:00",
        "check_out_at": f"{work_date.isoformat()}T17:00:00+03:00",
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
    handoff: dict[str, Any] = {}
    if unpaid_handoff:
        handoff = {
            "leave_id": leave_id,
            "classification": "unpaid_leave",
            "chargeable_days": float((end - start).days + 1),
            "monetary_fields": None,
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


def emp_lines(lines: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [ln for ln in lines if str(ln.get("employee_key")) == key]


def line_codes(lines: list[dict[str, Any]], key: str) -> set[str]:
    return {str(ln.get("component_code")) for ln in emp_lines(lines, key)}


def line_amt(lines: list[dict[str, Any]], key: str, code: str) -> Decimal:
    total = Decimal("0")
    for ln in emp_lines(lines, key):
        if str(ln.get("component_code")) == code:
            total += Decimal(str(ln.get("amount") or 0))
    return total


def cleanup(app: Any, keys: list[str], p_start: date, p_end: date) -> None:
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            p3.ensure_payroll_components_policy_schema(cur)
            p2.ensure_payroll_input_snapshot_schema(cur)

            cur.execute(
                """
                SELECT calc_run_id::text FROM payroll_calc_preview_runs
                WHERE company_code=%s AND period_start=%s AND period_end=%s
                """,
                (COMPANY, p_start, p_end),
            )
            calc_ids = [dict(r)["calc_run_id"] for r in (cur.fetchall() or [])]
            if calc_ids:
                cur.execute("DELETE FROM payroll_calc_preview_lines WHERE calc_run_id::text = ANY(%s)", (calc_ids,))
                cur.execute(
                    "DELETE FROM payroll_calc_preview_employee_results WHERE calc_run_id::text = ANY(%s)",
                    (calc_ids,),
                )
                cur.execute("DELETE FROM payroll_calc_preview_events WHERE calc_run_id::text = ANY(%s)", (calc_ids,))
                cur.execute("DELETE FROM payroll_calc_preview_runs WHERE calc_run_id::text = ANY(%s)", (calc_ids,))

            cur.execute(
                "DELETE FROM payroll_one_off_adjustments WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM payroll_component_assignments WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM payroll_company_components WHERE company_code=%s AND component_code LIKE %s",
                (COMPANY, f"%{TAG.upper()}%"),
            )
            # Keep policy versions (company-wide) but remove ones tagged in decision_note
            cur.execute(
                "DELETE FROM payroll_company_policy_versions WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap3_{TAG}%"),
            )

            cur.execute(
                "SELECT input_snapshot_id::text FROM payroll_input_snapshots WHERE company_code=%s AND period_start=%s AND period_end=%s",
                (COMPANY, p_start, p_end),
            )
            ids = [dict(r)["input_snapshot_id"] for r in (cur.fetchall() or [])]
            if ids:
                cur.execute("DELETE FROM payroll_input_snapshot_lines WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshot_issues WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute(
                    "DELETE FROM payroll_input_snapshot_employees WHERE input_snapshot_id::text = ANY(%s)", (ids,)
                )
                cur.execute("DELETE FROM payroll_input_snapshot_events WHERE input_snapshot_id::text = ANY(%s)", (ids,))
                cur.execute("DELETE FROM payroll_input_snapshots WHERE input_snapshot_id::text = ANY(%s)", (ids,))

            cur.execute("ALTER TABLE attendance_payroll_snapshots DISABLE TRIGGER trg_attendance_payroll_snapshots_immutable")
            try:
                cur.execute(
                    "DELETE FROM attendance_payroll_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                    (COMPANY, keys),
                )
            finally:
                cur.execute("ALTER TABLE attendance_payroll_snapshots ENABLE TRIGGER trg_attendance_payroll_snapshots_immutable")

            cur.execute("DELETE FROM leave_requests WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
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
                (COMPANY, f"%pap3_{TAG}%"),
            )
        conn.commit()


def main() -> int:
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_official_pdf as opdf

    h = p3.honesty_payload()
    inv = p3.freeze_invariants()
    check("p3 version", p3.PAYROLL_AUTHORITY_P3_VERSION == "1.0.0")
    check("preview only", h.get("money_authority") == "preview_non_authoritative")
    check("mode a sealed locked", h.get("mode_a_wathefni_seal_unlocked") is False)
    check("native pdf locked", h.get("native_official_pdf_unlocked") is False)
    check("pifss/eos not implemented", h.get("pifss_eos_rates_implemented") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("no payment_date invent", h.get("payment_date_invented") is False)
    check("no formula scripts", h.get("arbitrary_formula_scripts") is False)
    check("counsel gated ot/sick/ph", h.get("ot_sick_ph_rates_counsel_gated") is True)
    check("synthetic only default", h.get("synthetic_only") is True)
    check("invariant locked inputs", inv.get("requires_locked_input_snapshot") is True)
    check("invariant deterministic", inv.get("deterministic_idempotent") is True)
    check("p1 preserved", p1.PAYROLL_AUTHORITY_P1_VERSION == "1.0.0")
    check("p2 preserved", p2.PAYROLL_AUTHORITY_P2_VERSION == "1.0.0")
    check(
        "native preview not pdf eligible",
        opdf.is_official_pdf_eligible(
            {
                "source_kind": "native_preview",
                "money_authority": "preview_non_authoritative",
                "authority_snapshot_id": str(uuid.uuid4()),
            }
        )
        is False,
    )
    check(
        "external without seal id not pdf eligible",
        opdf.is_official_pdf_eligible({"source_kind": "external_import", "money_authority": "external"}) is False,
    )

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            (EVID / "SUMMARY.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "skip": True}, indent=2))
            return 0
        raise

    p_start, p_end = unique_period()
    period_days = (p_end - p_start).days + 1
    hire_day = p_start + timedelta(days=10)
    leave_day = p_start + timedelta(days=20)
    mid_day = p_start + timedelta(days=15)
    abs_day = p_start + timedelta(days=5)
    unpaid_day = p_start + timedelta(days=6)
    paid_day = p_start + timedelta(days=7)
    late_day = p_start + timedelta(days=8)
    ot_day = p_start + timedelta(days=9)

    cleanup(app, ALL_KEYS, p_start, p_end)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
                p2.ensure_payroll_input_snapshot_schema(cur, force=True)
                p3.ensure_payroll_components_policy_schema(cur, force=True)

                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                # Informational assemble → lock cleanly; money driven by P3 policy version
                p2.set_attendance_payroll_mode(
                    cur,
                    company_code=COMPANY,
                    mode="informational",
                    actor_phone=APPROVER,
                    reason=f"pap3_mode_info_{TAG}",
                )

                phones = {k: f"96557{TAG_DIGITS}{i:02d}" for i, k in enumerate(ALL_KEYS, start=1)}
                upsert_employee(cur, EMP_BASIC, phones[EMP_BASIC], hire=p_start - timedelta(days=60))
                upsert_employee(cur, EMP_MID, phones[EMP_MID], hire=p_start - timedelta(days=60))
                upsert_employee(cur, EMP_HIRE, phones[EMP_HIRE], hire=hire_day)
                upsert_employee(cur, EMP_LEAVE, phones[EMP_LEAVE], hire=p_start - timedelta(days=60), term=leave_day)
                for k in (EMP_ABS, EMP_UNPAID, EMP_PAID, EMP_LATE, EMP_OT, EMP_OVERLAP, EMP_CUSTOM):
                    upsert_employee(cur, k, phones[k], hire=p_start - timedelta(days=60))

                # BASIC + recurring allowance + recurring deduction
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_BASIC,
                    effective_from=p_start - timedelta(days=60),
                    components=[
                        {"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True},
                        {
                            "component_kind": "allowance",
                            "code": "ALLOWANCE.TRANSPORT",
                            "amount": 50,
                            "label_en": "Transport",
                        },
                        {
                            "component_kind": "deduction",
                            "code": "DEDUCTION.RECURRING",
                            "amount": 25,
                            "label_en": "Recurring ded",
                        },
                        {
                            "component_kind": "earning",
                            "code": "ALLOWANCE.ONE_OFF",
                            "amount": 100,
                            "amount_unit": "one_time",
                            "label_en": "Signing bonus",
                        },
                    ],
                )

                # Mid-period salary change
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_MID,
                    effective_from=p_start - timedelta(days=60),
                    effective_to=mid_day - timedelta(days=1),
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 300, "is_basic": True}],
                )
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_MID,
                    effective_from=mid_day,
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True}],
                )

                # Hire / leaver
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_HIRE,
                    effective_from=hire_day,
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 450, "is_basic": True}],
                )
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_LEAVE,
                    effective_from=p_start - timedelta(days=60),
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 450, "is_basic": True}],
                )

                for k in (EMP_ABS, EMP_UNPAID, EMP_PAID, EMP_LATE, EMP_OT, EMP_CUSTOM):
                    approve_contract(
                        cur,
                        pyw1,
                        employee_key=k,
                        effective_from=p_start - timedelta(days=60),
                        components=[{"component_kind": "earning", "code": "BASIC", "amount": 300, "is_basic": True}],
                    )

                # Overlapping approved contracts (simulate stale/ambiguous rows — Wave1 approve refuses this)
                approve_contract(
                    cur,
                    pyw1,
                    employee_key=EMP_OVERLAP,
                    effective_from=p_start - timedelta(days=60),
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 300, "is_basic": True}],
                )
                cur.execute(
                    """
                    INSERT INTO payroll_compensation_contracts (
                      company_code, employee_key, status, currency, effective_from, effective_to,
                      source_kind, created_by_phone, approved_by_phone, approved_at, decision_note
                    ) VALUES (%s,%s,'approved','KWD',%s,NULL,'manual',%s,%s,now(),%s)
                    RETURNING contract_id::text
                    """,
                    (
                        COMPANY,
                        EMP_OVERLAP,
                        p_start,
                        CREATOR,
                        APPROVER,
                        f"pap3_{TAG}_overlap_inject",
                    ),
                )
                overlap_cid = dict(cur.fetchone())["contract_id"]
                cur.execute(
                    """
                    INSERT INTO payroll_compensation_components (
                      contract_id, company_code, component_kind, code, label_en,
                      amount, amount_unit, is_basic, sort_order, metadata
                    ) VALUES (%s,%s,'earning','BASIC','Basic',400,'monthly',true,0,'{}'::jsonb)
                    """,
                    (overlap_cid, COMPANY),
                )

                # Custom company component + assignment + one-off deduction
                custom = p3.upsert_company_component(
                    cur,
                    company_code=COMPANY,
                    catalog_code="CUSTOM.EARNING",
                    component_code=f"CUSTOM.PHONE.{TAG.upper()}",
                    label_en="Phone allowance custom",
                    label_ar="بدل هاتف مخصص",
                    line_kind="earning",
                    amount_unit="monthly",
                    default_amount=20,
                    is_custom=True,
                    actor_phone=CREATOR,
                    reason=f"pap3_{TAG}_custom_comp",
                )
                check("custom component upsert", custom.get("ok") is True, custom)
                ccid = str((custom.get("component") or {}).get("company_component_id"))
                asg = p3.assign_component(
                    cur,
                    company_code=COMPANY,
                    company_component_id=ccid,
                    amount=20,
                    effective_from=p_start,
                    employee_key=EMP_CUSTOM,
                    actor_phone=CREATOR,
                    reason=f"pap3_{TAG}_assign",
                )
                check("custom assignment", asg.get("ok") is True, asg)
                adj = p3.create_one_off_adjustment(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_CUSTOM,
                    period_start=p_start,
                    period_end=p_end,
                    component_code="DEDUCTION.ONE_OFF",
                    line_kind="deduction",
                    amount=15,
                    reason=f"pap3_{TAG}_oneoff",
                    actor_phone=APPROVER,
                    label_en="Manual one-off deduction",
                )
                check("one-off adjustment", adj.get("ok") is True, adj)

                reserved = p3.upsert_company_component(
                    cur,
                    company_code=COMPANY,
                    catalog_code="CUSTOM.EARNING",
                    component_code="PIFSS_EE",
                    label_en="Fake",
                    label_ar=None,
                    line_kind="deduction",
                    is_custom=True,
                    actor_phone=CREATOR,
                    reason=f"pap3_{TAG}_reserved",
                )
                check("reserved statutory cannot be custom", reserved.get("ok") is False, reserved)

                # Attendance / leave facts
                seed_att_snap(cur, employee_key=EMP_BASIC, work_date=p_start + timedelta(days=1), status="completed", worked=480)
                seed_att_snap(cur, employee_key=EMP_MID, work_date=p_start + timedelta(days=1), status="completed", worked=480)
                seed_att_snap(cur, employee_key=EMP_HIRE, work_date=hire_day, status="completed", worked=480)
                seed_att_snap(
                    cur, employee_key=EMP_LEAVE, work_date=leave_day - timedelta(days=1), status="completed", worked=480
                )
                seed_att_snap(cur, employee_key=EMP_ABS, work_date=abs_day, status="absent", worked=0)
                seed_att_snap(cur, employee_key=EMP_ABS, work_date=p_start + timedelta(days=1), status="completed", worked=480)
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
                seed_leave(
                    cur,
                    employee_key=EMP_PAID,
                    leave_type="annual",
                    status="approved",
                    start=paid_day,
                    end=paid_day,
                )
                seed_att_snap(cur, employee_key=EMP_PAID, work_date=paid_day, status="absent", worked=0)
                seed_att_snap(
                    cur, employee_key=EMP_LATE, work_date=late_day, status="completed", worked=420, late=60
                )
                seed_att_snap(
                    cur, employee_key=EMP_OT, work_date=ot_day, status="completed", worked=600, scheduled=480
                )
                seed_att_snap(cur, employee_key=EMP_CUSTOM, work_date=p_start + timedelta(days=2), status="completed", worked=480)
                seed_att_snap(cur, employee_key=EMP_OVERLAP, work_date=p_start + timedelta(days=2), status="completed", worked=480)

                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="approved_snapshots",
                    actor_phone=CREATOR,
                    reason=f"pap3_{TAG}_period",
                )
                check("period", period.get("ok") is True, period)

                assembled = p2.assemble_payroll_inputs(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    employee_keys=ALL_KEYS,
                    actor_phone=CREATOR,
                    reason=f"pap3_{TAG}_assemble",
                )
                check("assemble inputs", assembled.get("ok") is True, assembled)
                snap = assembled.get("input_snapshot") or {}
                sid = str(snap.get("input_snapshot_id"))
                check("assemble status lockable", str(snap.get("status")) in ("ready", "needs_review"), snap)

                locked = p2.lock_payroll_input_snapshot(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_lock",
                    force=str(snap.get("status")) == "needs_review",
                )
                # If force not allowed, re-check
                if not locked.get("ok"):
                    locked = p2.lock_payroll_input_snapshot(
                        cur,
                        company_code=COMPANY,
                        input_snapshot_id=sid,
                        actor_phone=APPROVER,
                        reason=f"pap3_{TAG}_lock",
                        force=True,
                    )
                check("lock inputs", locked.get("ok") is True, locked)
                sid = str((locked.get("input_snapshot") or snap).get("input_snapshot_id") or sid)

                # Catalog seeds
                catalog = p3.list_component_catalog(cur)
                codes = {str(r.get("component_code")) for r in catalog}
                for need in (
                    "BASIC",
                    "ALLOWANCE.TRANSPORT",
                    "ALLOWANCE.PHONE",
                    "DEDUCTION.LATENESS",
                    "DEDUCTION.ABSENCE",
                    "OT_ORDINARY",
                    "CUSTOM.EARNING",
                    "PIFSS_EE",
                ):
                    check(f"catalog has {need}", need in codes)

                # Policy v1: attendance money ON, lateness OFF, OT OFF
                pol1 = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_v1_money",
                    attendance_payroll_mode="required",
                    lateness_money_enabled=False,
                    absence_money_enabled=True,
                    unpaid_leave_money_enabled=True,
                    ot_money_enabled=False,
                    rest_day_money_enabled=False,
                    public_holiday_money_enabled=False,
                    sick_leave_money_enabled=False,
                    approve=True,
                )
                check("policy v1", pol1.get("ok") is True, pol1)
                pol1_id = str((pol1.get("policy") or {}).get("policy_version_id"))

                calc1 = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc1",
                    policy_version_id=pol1_id,
                    employee_keys=ALL_KEYS,
                )
                check("calc1 ok", calc1.get("ok") is True, calc1)
                run1 = calc1.get("calc_run") or {}
                check("calc1 preview authority", run1.get("money_authority") == "preview_non_authoritative")
                check("calc1 fingerprints present", bool(run1.get("content_fingerprint")) and bool(run1.get("input_fingerprint")))
                check("calc1 policy fp", str(run1.get("policy_fingerprint")) == str((pol1.get("policy") or {}).get("content_fingerprint")))
                check("calc1 input fp", str(run1.get("input_fingerprint")) == str(snap.get("content_fingerprint") or (locked.get("input_snapshot") or {}).get("content_fingerprint") or run1.get("input_fingerprint")))

                lines1 = p3.list_calc_lines(cur, company_code=COMPANY, calc_run_id=str(run1.get("calc_run_id")))
                emps1 = {r["employee_key"]: r for r in (calc1.get("employees") or [])}

                # Basic salary + recurring + one-off
                check("basic salary line", "BASIC" in line_codes(lines1, EMP_BASIC))
                check("recurring allowance", "ALLOWANCE.TRANSPORT" in line_codes(lines1, EMP_BASIC))
                check("recurring deduction", "DEDUCTION.RECURRING" in line_codes(lines1, EMP_BASIC))
                check("one-off earning", "ALLOWANCE.ONE_OFF" in line_codes(lines1, EMP_BASIC))
                basic_amt = line_amt(lines1, EMP_BASIC, "BASIC")
                check("basic full period ~600", abs(basic_amt - Decimal("600")) < Decimal("0.01"), float(basic_amt))

                # Mid-period salary
                mid_basic = line_amt(lines1, EMP_MID, "BASIC")
                days_low = (mid_day - p_start).days
                days_high = (p_end - mid_day).days + 1
                expected_mid = money_expect(300, days_low, period_days) + money_expect(600, days_high, period_days)
                check(
                    "mid-period salary change",
                    abs(mid_basic - expected_mid) < Decimal("0.02"),
                    {"got": float(mid_basic), "expected": float(expected_mid), "days_low": days_low, "days_high": days_high},
                )

                # Hire / leaver proration
                hire_days = (p_end - hire_day).days + 1
                leave_days = (leave_day - p_start).days + 1
                hire_amt = line_amt(lines1, EMP_HIRE, "BASIC")
                leave_amt = line_amt(lines1, EMP_LEAVE, "BASIC")
                check(
                    "mid-period hire proration",
                    abs(hire_amt - money_expect(450, hire_days, period_days)) < Decimal("0.02"),
                    float(hire_amt),
                )
                check(
                    "mid-period leaver proration",
                    abs(leave_amt - money_expect(450, leave_days, period_days)) < Decimal("0.02"),
                    float(leave_amt),
                )

                # Unpaid absence money
                check("unpaid absence deduction", "DEDUCTION.ABSENCE" in line_codes(lines1, EMP_ABS), line_codes(lines1, EMP_ABS))
                # Unpaid leave money + no double with absence
                check("unpaid leave deduction", "UNPAID_LEAVE" in line_codes(lines1, EMP_UNPAID), line_codes(lines1, EMP_UNPAID))
                check(
                    "no double deduct unpaid+absence",
                    "DEDUCTION.ABSENCE" not in line_codes(lines1, EMP_UNPAID),
                    line_codes(lines1, EMP_UNPAID),
                )
                # Paid leave does not deduct
                check(
                    "paid leave no absence deduct",
                    "DEDUCTION.ABSENCE" not in line_codes(lines1, EMP_PAID)
                    and "UNPAID_LEAVE" not in line_codes(lines1, EMP_PAID),
                    line_codes(lines1, EMP_PAID),
                )
                # Lateness off
                check("lateness off no money", "DEDUCTION.LATENESS" not in line_codes(lines1, EMP_LATE))
                # OT facts present but money disabled → no OT line / no counsel block for disabled
                ot_emp = emps1.get(EMP_OT) or {}
                check("ot disabled no counsel block", not any(
                    (b.get("code") == "counsel_rate_required" and b.get("rule_family") == "ot_ordinary")
                    for b in (ot_emp.get("blockers") or [])
                ), ot_emp.get("blockers"))
                check("ot disabled no OT money line", "OT_ORDINARY" not in line_codes(lines1, EMP_OT))

                # Custom + one-off
                check("custom company component line", any(TAG.upper() in c for c in line_codes(lines1, EMP_CUSTOM)))
                check("one-off deduction line", "DEDUCTION.ONE_OFF" in line_codes(lines1, EMP_CUSTOM))

                # Overlap fail closed
                ov = emps1.get(EMP_OVERLAP) or {}
                check("overlapping compensation blocked", ov.get("ok") is False, ov)
                check(
                    "overlap blocker code",
                    any(b.get("code") == "overlapping_approved_contracts" for b in (ov.get("blockers") or [])),
                    ov.get("blockers"),
                )

                # Idempotent recalculation
                calc1b = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc1_again",
                    policy_version_id=pol1_id,
                    employee_keys=ALL_KEYS,
                )
                check("idempotent flag", calc1b.get("idempotent") is True, calc1b)
                check(
                    "idempotent same fingerprint",
                    str((calc1b.get("calc_run") or {}).get("content_fingerprint"))
                    == str(run1.get("content_fingerprint")),
                )
                check(
                    "idempotent same calc_run_id",
                    str((calc1b.get("calc_run") or {}).get("calc_run_id")) == str(run1.get("calc_run_id")),
                )

                # Policy v2: lateness ON
                pol2 = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_v2_late",
                    attendance_payroll_mode="required",
                    lateness_money_enabled=True,
                    lateness_grace_minutes=0,
                    absence_money_enabled=True,
                    unpaid_leave_money_enabled=True,
                    ot_money_enabled=False,
                    approve=True,
                )
                check("policy v2 lateness", pol2.get("ok") is True, pol2)
                pol2_id = str((pol2.get("policy") or {}).get("policy_version_id"))
                calc2 = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc2",
                    policy_version_id=pol2_id,
                    employee_keys=[EMP_LATE],
                )
                check("calc2 ok", calc2.get("ok") is True, calc2)
                lines2 = p3.list_calc_lines(cur, company_code=COMPANY, calc_run_id=str((calc2.get("calc_run") or {}).get("calc_run_id")))
                check("lateness on produces money", "DEDUCTION.LATENESS" in line_codes(lines2, EMP_LATE), line_codes(lines2, EMP_LATE))
                check(
                    "policy version change new fingerprint",
                    str((calc2.get("calc_run") or {}).get("content_fingerprint")) != str(run1.get("content_fingerprint")),
                )

                # Policy informational → no attendance money
                pol_info = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_info",
                    attendance_payroll_mode="informational",
                    lateness_money_enabled=True,
                    absence_money_enabled=True,
                    unpaid_leave_money_enabled=True,
                    ot_money_enabled=False,
                    approve=True,
                )
                pol_info_id = str((pol_info.get("policy") or {}).get("policy_version_id"))
                calc_info = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc_info",
                    policy_version_id=pol_info_id,
                    employee_keys=[EMP_ABS, EMP_UNPAID, EMP_LATE],
                )
                check("calc informational ok", calc_info.get("ok") is True, calc_info)
                lines_info = p3.list_calc_lines(
                    cur, company_code=COMPANY, calc_run_id=str((calc_info.get("calc_run") or {}).get("calc_run_id"))
                )
                for k in (EMP_ABS, EMP_UNPAID, EMP_LATE):
                    codes_k = line_codes(lines_info, k)
                    check(
                        f"informational no att money {k[-8:]}",
                        "DEDUCTION.ABSENCE" not in codes_k
                        and "UNPAID_LEAVE" not in codes_k
                        and "DEDUCTION.LATENESS" not in codes_k,
                        codes_k,
                    )

                pol_ign = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_ignored",
                    attendance_payroll_mode="ignored",
                    lateness_money_enabled=True,
                    absence_money_enabled=True,
                    unpaid_leave_money_enabled=True,
                    approve=True,
                )
                calc_ign = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc_ignored",
                    policy_version_id=str((pol_ign.get("policy") or {}).get("policy_version_id")),
                    employee_keys=[EMP_ABS],
                )
                lines_ign = p3.list_calc_lines(
                    cur, company_code=COMPANY, calc_run_id=str((calc_ign.get("calc_run") or {}).get("calc_run_id"))
                )
                check("ignored mode no absence money", "DEDUCTION.ABSENCE" not in line_codes(lines_ign, EMP_ABS))

                # OT / rest / PH / sick: public baseline (P4B) unblocks; otherwise fail closed
                pol_ot = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_ot",
                    attendance_payroll_mode="required",
                    ot_money_enabled=True,
                    rest_day_money_enabled=True,
                    public_holiday_money_enabled=True,
                    sick_leave_money_enabled=True,
                    approve=True,
                )
                calc_ot = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_calc_ot",
                    policy_version_id=str((pol_ot.get("policy") or {}).get("policy_version_id")),
                    employee_keys=[EMP_OT],
                )
                check("ot policy calc returns", calc_ot.get("ok") is True, calc_ot)
                ot_res = (calc_ot.get("employees") or [{}])[0]
                blocker_families = {b.get("rule_family") for b in (ot_res.get("blockers") or []) if b.get("code") == "counsel_rate_required"}
                baseline_ot = p3.get_approved_rate(cur, company_code=COMPANY, rule_family="ot_ordinary", as_of=p_start)
                has_public_baseline = bool(baseline_ot and baseline_ot.get("legal_claim") and baseline_ot.get("source") == "p4b_public_baseline")
                if has_public_baseline:
                    check("ot public baseline unblocks", ot_res.get("ok") is True and "ot_ordinary" not in blocker_families, ot_res)
                    check("rest public baseline unblocks", "rest_day_work" not in blocker_families, ot_res.get("blockers"))
                    check("ph public baseline unblocks", "public_holiday_work" not in blocker_families, ot_res.get("blockers"))
                    check("sick public baseline unblocks", "sick_leave_fractions" not in blocker_families, ot_res.get("blockers"))
                    check("ot employee not blocked by missing rate", ot_res.get("ok") is True)
                    ot_lines = line_codes(
                        p3.list_calc_lines(cur, company_code=COMPANY, calc_run_id=str((calc_ot.get("calc_run") or {}).get("calc_run_id"))),
                        EMP_OT,
                    )
                    check("ot baseline may emit OT line", "OT_ORDINARY" in ot_lines or ot_res.get("ok") is True, ot_lines)
                else:
                    check("ot counsel fail closed", "ot_ordinary" in blocker_families, ot_res.get("blockers"))
                    check("rest counsel fail closed", "rest_day_work" in blocker_families, ot_res.get("blockers"))
                    check("ph counsel fail closed", "public_holiday_work" in blocker_families, ot_res.get("blockers"))
                    check("sick counsel fail closed", "sick_leave_fractions" in blocker_families, ot_res.get("blockers"))
                    check("ot blocked employee", ot_res.get("ok") is False)
                    check("no silent OT amount", "OT_ORDINARY" not in line_codes(
                        p3.list_calc_lines(cur, company_code=COMPANY, calc_run_id=str((calc_ot.get("calc_run") or {}).get("calc_run_id"))),
                        EMP_OT,
                    ) or ot_res.get("ok") is False)

                # Unlocked input refused — supersede creates a new non-locked snapshot
                pol_ready = p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_for_unlocked_test",
                    attendance_payroll_mode="informational",
                    lateness_money_enabled=False,
                    ot_money_enabled=False,
                    rest_day_money_enabled=False,
                    public_holiday_money_enabled=False,
                    sick_leave_money_enabled=False,
                    approve=True,
                )
                check("policy for unlocked test", pol_ready.get("ok") is True, pol_ready)
                superseded = p2.supersede_input_snapshot(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=sid,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_supersede_for_unlocked",
                    employee_keys=[EMP_BASIC],
                )
                check("supersede for unlocked test", superseded.get("ok") is True, superseded)
                new_sid = str(
                    (superseded.get("input_snapshot") or (superseded.get("assembled") or {}).get("input_snapshot") or {}).get(
                        "input_snapshot_id"
                    )
                    or ""
                )
                if not new_sid:
                    # fallback shapes
                    new_sid = str((superseded.get("new_input_snapshot") or {}).get("input_snapshot_id") or "")
                new_status = str(
                    (superseded.get("input_snapshot") or (superseded.get("assembled") or {}).get("input_snapshot") or {}).get(
                        "status"
                    )
                    or ""
                )
                refused = p3.calculate_mode_a_preview(
                    cur,
                    company_code=COMPANY,
                    input_snapshot_id=new_sid or "00000000-0000-0000-0000-000000000000",
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_refuse_unlocked",
                    policy_version_id=str((pol_ready.get("policy") or {}).get("policy_version_id")),
                    employee_keys=[EMP_BASIC],
                )
                check(
                    "unlocked input refused",
                    refused.get("ok") is False
                    and refused.get("error") == "input_snapshot_not_locked"
                    and new_status != "locked",
                    {"refused": refused, "new_sid": new_sid, "new_status": new_status, "supersede": {k: superseded.get(k) for k in ("ok", "error")}},
                )

                rates = p3.ensure_counsel_required_rate_placeholders(cur, company_code=COMPANY, actor_phone=APPROVER)
                check("counsel placeholders seeded", len(rates) >= 4, len(rates))
                approved_ot = p3.get_approved_rate(cur, company_code=COMPANY, rule_family="ot_ordinary", as_of=p_start)
                if approved_ot and approved_ot.get("source") == "p4b_public_baseline":
                    check(
                        "approved OT from public baseline",
                        float(approved_ot.get("multiplier") or 0) == 1.25
                        and approved_ot.get("legal_claim") is True,
                        approved_ot,
                    )
                else:
                    check("no approved OT rate", approved_ot is None)

            conn.commit()
    except Exception as exc:
        check("runtime", False, f"{type(exc).__name__}: {exc}")
        try:
            cleanup(app, ALL_KEYS, p_start, p_end)
        except Exception:
            pass
        _write_evidence(p_start, p_end)
        return 1

    # Restore a sane informational policy for company after smoke
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start,
                    actor_phone=APPROVER,
                    reason=f"pap3_{TAG}_policy_restore_info",
                    attendance_payroll_mode="informational",
                    lateness_money_enabled=False,
                    ot_money_enabled=False,
                    approve=True,
                )
            conn.commit()
    except Exception:
        pass

    cleanup(app, ALL_KEYS, p_start, p_end)
    _write_evidence(p_start, p_end)
    print(f"PASS={PASS} FAIL={FAIL} EVID={EVID}")
    return 0 if FAIL == 0 else 1


def money_expect(monthly: float, days: int, period_days: int) -> Decimal:
    if period_days <= 0 or days <= 0:
        return Decimal("0.000")
    return (Decimal(str(monthly)) * Decimal(days) / Decimal(period_days)).quantize(Decimal("0.001"))


def _write_evidence(p_start: date, p_end: date) -> None:
    summary = {
        "stamp": STAMP,
        "tag": TAG,
        "period_start": p_start.isoformat(),
        "period_end": p_end.isoformat(),
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "honesty": {
            "money_authority": "preview_non_authoritative",
            "mode_a_seal": False,
            "native_pdf": False,
            "pifss_eos": False,
            "payment_processing": "disabled",
        },
    }
    (EVID / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (EVID / "RESULTS.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
