#!/usr/bin/env python3
"""Payroll Authority P5 — Mode A authoritative finalize canary qualification.

Proves: P3 preview stays preview; locked inputs + approved policy + gates + SOD
finalize → sealed money_authority=wathefni; official PDF eligible; release isolation;
period_close / seal_from_native_preview still refused; P6 blockers listed.
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
    ROOT,
]
ORCH = next(
    (p for p in ORCH_CANDIDATES if (p / "payroll_authority_mode_a_p5.py").exists()),
    ORCH_CANDIDATES[0],
)
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
for flag in (
    "WATHEFNI_PAYROLL_WAVE1",
    "WATHEFNI_PAYROLL_WAVE3",
    "WATHEFNI_PAYROLL_AUTHORITY_P1",
    "WATHEFNI_PAYROLL_AUTHORITY_P2",
    "WATHEFNI_PAYROLL_AUTHORITY_P3",
    "WATHEFNI_PAYROLL_AUTHORITY_P4A",
    "WATHEFNI_PAYROLL_AUTHORITY_P4B",
    "WATHEFNI_PAYROLL_AUTHORITY_P5",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYW3,PYP1,PYP2,PYP3,PYP4A,PYP4B,PYP5,PYAUTH,PYSTAT,PYINPUT,PYCALC"
for mk in (
    "WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS",
):
    os.environ.setdefault(mk, MARKERS)

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP5_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
CREATOR = f"9655518{TAG_DIGITS}"
APPROVER = f"9655519{TAG_DIGITS}"
EMP = f"WATHEFNI-PYW1-PYP5-BASIC-{TAG}"
ALL_KEYS = [EMP]

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP5_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p5-{STAMP}"))
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


def upsert_employee(cur: Any, key: str, phone: str, *, hire: date | None = None) -> None:
    profile: dict[str, Any] = {}
    if hire:
        profile["employment_start"] = hire.isoformat()
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE
          SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, name=EXCLUDED.name,
              hire_date=EXCLUDED.hire_date, start_date=EXCLUDED.start_date,
              profile=EXCLUDED.profile, updated_at=now()
        """,
        (COMPANY, key, phone, f"P5 {key[-12:]}", hire, hire, json.dumps(profile)),
    )


def approve_contract(cur: Any, pyw1: Any, *, employee_key: str, effective_from: date, components: list[dict[str, Any]]) -> str:
    draft = pyw1.create_contract_draft(
        cur, company_code=COMPANY, employee_key=employee_key, effective_from=effective_from,
        components=components, actor_phone=CREATOR, reason=f"pap5_draft_{TAG}",
    )
    cid = str((draft.get("contract") or {}).get("contract_id"))
    pyw1.approve_contract(
        cur, company_code=COMPANY, contract_id=cid, actor_phone=APPROVER, reason=f"pap5_appr_{TAG}",
        expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
    )
    return cid


def cleanup(app: Any, keys: list[str], p_start: date, p_end: date) -> None:
    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_snapshot_p1 as p1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_wave3 as w3

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            p5.ensure_payroll_mode_a_finalize_schema(cur)
            p1.ensure_payroll_authority_snapshot_schema(cur)
            p3.ensure_payroll_components_policy_schema(cur)
            p2.ensure_payroll_input_snapshot_schema(cur)
            try:
                w3.ensure_payroll_wave3_schema(cur)
            except Exception:
                pass

            cur.execute(
                """
                SELECT finalize_run_id::text FROM payroll_mode_a_finalize_runs
                WHERE company_code=%s AND ((period_start=%s AND period_end=%s) OR decision_note LIKE %s)
                """,
                (COMPANY, p_start, p_end, f"%pap5_{TAG}%"),
            )
            fids = [dict(r)["finalize_run_id"] for r in (cur.fetchall() or [])]
            if fids:
                cur.execute("DELETE FROM payroll_mode_a_finalize_events WHERE finalize_run_id::text = ANY(%s)", (fids,))
                cur.execute("DELETE FROM payroll_mode_a_finalize_runs WHERE finalize_run_id::text = ANY(%s)", (fids,))

            cur.execute(
                "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            pids = [dict(r)["payslip_id"] for r in (cur.fetchall() or [])]
            if pids:
                for tbl in ("payroll_payslip_lines", "payroll_payslip_events"):
                    try:
                        cur.execute(f"DELETE FROM {tbl} WHERE payslip_id::text = ANY(%s)", (pids,))
                    except Exception:
                        pass
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))

            cur.execute(
                "SELECT authority_snapshot_id::text FROM payroll_authority_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            aids = [dict(r)["authority_snapshot_id"] for r in (cur.fetchall() or [])]
            if aids:
                cur.execute("DELETE FROM payroll_authority_snapshot_lines WHERE authority_snapshot_id::text = ANY(%s)", (aids,))
                cur.execute("DELETE FROM payroll_authority_snapshot_events WHERE authority_snapshot_id::text = ANY(%s)", (aids,))
                cur.execute("DELETE FROM payroll_authority_snapshots WHERE authority_snapshot_id::text = ANY(%s)", (aids,))

            cur.execute(
                "SELECT calc_run_id::text FROM payroll_calc_preview_runs WHERE company_code=%s AND period_start=%s AND period_end=%s",
                (COMPANY, p_start, p_end),
            )
            calc_ids = [dict(r)["calc_run_id"] for r in (cur.fetchall() or [])]
            if calc_ids:
                for tbl in (
                    "payroll_calc_preview_lines",
                    "payroll_calc_preview_employee_results",
                    "payroll_calc_preview_events",
                    "payroll_calc_preview_runs",
                ):
                    cur.execute(f"DELETE FROM {tbl} WHERE calc_run_id::text = ANY(%s)", (calc_ids,))

            cur.execute(
                "DELETE FROM payroll_company_policy_versions WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap5_{TAG}%"),
            )
            cur.execute(
                "SELECT input_snapshot_id::text FROM payroll_input_snapshots WHERE company_code=%s AND period_start=%s AND period_end=%s",
                (COMPANY, p_start, p_end),
            )
            ids = [dict(r)["input_snapshot_id"] for r in (cur.fetchall() or [])]
            if ids:
                for tbl in (
                    "payroll_input_snapshot_lines",
                    "payroll_input_snapshot_issues",
                    "payroll_input_snapshot_employees",
                    "payroll_input_snapshot_events",
                    "payroll_input_snapshots",
                ):
                    cur.execute(f"DELETE FROM {tbl} WHERE input_snapshot_id::text = ANY(%s)", (ids,))

            for key in keys:
                cur.execute(
                    "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cids = [dict(r)["contract_id"] for r in (cur.fetchall() or [])]
                if cids:
                    for tbl in (
                        "payroll_compensation_components",
                        "payroll_compensation_events",
                        "payroll_compensation_contracts",
                    ):
                        cur.execute(f"DELETE FROM {tbl} WHERE company_code=%s AND contract_id::text = ANY(%s)", (COMPANY, cids))
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            cur.execute("DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, f"%pap5_{TAG}%"))
        conn.commit()


def _write_evidence(p_start: date | None = None, p_end: date | None = None) -> None:
    summary = {
        "stamp": STAMP,
        "tag": TAG,
        "period_start": p_start.isoformat() if p_start else None,
        "period_end": p_end.isoformat() if p_end else None,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "honesty": {
            "mode_a_unlocked": True,
            "preview_remains_preview": True,
            "period_close_is_money_seal": False,
            "payment_processing": "disabled",
            "synthetic_only": True,
        },
    }
    (EVID / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (EVID / "RESULTS.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")


def main() -> int:
    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_official_pdf as opdf
    import payroll_payslip_wave3 as w3
    import payroll_statutory_baseline_p4b as p4b

    h = p5.honesty_payload()
    check("p5 version", p5.PAYROLL_AUTHORITY_P5_VERSION == "1.0.0")
    check("mode a unlocked via P5", h.get("mode_a_wathefni_seal_unlocked") is True)
    check("preview remains preview", h.get("preview_remains_preview") is True)
    check("period_close not money seal", h.get("period_close_is_money_seal") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("synthetic only", h.get("synthetic_only") is True)
    check("p6 company entitlement gate flagged", h.get("p6_company_entitlement_gate") is True)
    p6 = p5.p6_blockers()
    check(
        "p6 blockers listed",
        bool(p6.get("remaining_for_p6")) and p6.get("payment_processing_disabled") is True,
        p6,
    )
    check("period_close_grants_money_authority False", p1.period_close_grants_money_authority() is False)
    check("gcc gated code in GATED_BLOCKERS", "gcc_extension_review_required" in p4b.GATED_BLOCKERS)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            (EVID / "SUMMARY.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "skip": True}, indent=2))
            return 0
        raise

    p_start, p_end = unique_period()
    cleanup(app, ALL_KEYS, p_start, p_end)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
                p2.ensure_payroll_input_snapshot_schema(cur, force=True)
                p3.ensure_payroll_components_policy_schema(cur, force=True)
                p5.ensure_payroll_mode_a_finalize_schema(cur, force=True)
                w3.ensure_payroll_wave3_schema(cur)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                p2.set_attendance_payroll_mode(
                    cur, company_code=COMPANY, mode="informational",
                    actor_phone=APPROVER, reason=f"pap5_mode_info_{TAG}",
                )

                upsert_employee(cur, EMP, f"96557{TAG_DIGITS}01", hire=p_start - timedelta(days=60))
                approve_contract(
                    cur, pyw1, employee_key=EMP, effective_from=p_start - timedelta(days=60),
                    components=[{"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True}],
                )
                period = pyw1.create_period(
                    cur, company_code=COMPANY, period_start=p_start, period_end=p_end,
                    attendance_input_source="approved_snapshots", actor_phone=CREATOR, reason=f"pap5_{TAG}_period",
                )
                check("period", period.get("ok") is True, period)

                # p3 assemble/lock API names (assemble_payroll_inputs / lock_payroll_input_snapshot)
                assembled = p2.assemble_payroll_inputs(
                    cur, company_code=COMPANY, period_start=p_start, period_end=p_end,
                    employee_keys=ALL_KEYS, actor_phone=CREATOR, reason=f"pap5_{TAG}_assemble",
                )
                check("assemble inputs", assembled.get("ok") is True, assembled)
                snap = assembled.get("input_snapshot") or {}
                sid = str(snap.get("input_snapshot_id"))
                locked = p2.lock_payroll_input_snapshot(
                    cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                    reason=f"pap5_{TAG}_lock", force=str(snap.get("status")) == "needs_review",
                )
                if not locked.get("ok"):
                    locked = p2.lock_payroll_input_snapshot(
                        cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                        reason=f"pap5_{TAG}_lock_force", force=True,
                    )
                check("lock inputs", locked.get("ok") is True, locked)
                sid = str((locked.get("input_snapshot") or snap).get("input_snapshot_id") or sid)

                pol = p3.create_policy_version(
                    cur, company_code=COMPANY, effective_from=p_start, actor_phone=APPROVER,
                    reason=f"pap5_{TAG}_policy", attendance_payroll_mode="informational",
                    lateness_money_enabled=False, absence_money_enabled=False,
                    unpaid_leave_money_enabled=False, ot_money_enabled=False,
                    rest_day_money_enabled=False, public_holiday_money_enabled=False,
                    sick_leave_money_enabled=False, approve=True,
                )
                check("approved P3 policy", pol.get("ok") is True, pol)
                pol_id = str((pol.get("policy") or {}).get("policy_version_id"))

                calc = p3.calculate_mode_a_preview(
                    cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                    reason=f"pap5_{TAG}_calc", policy_version_id=pol_id, employee_keys=ALL_KEYS,
                )
                check("calc ok", calc.get("ok") is True, calc)
                run = calc.get("calc_run") or {}
                calc_id = str(run.get("calc_run_id"))
                check("calc status calculated", str(run.get("status")) == "calculated", run)
                check("calc money_authority still preview", run.get("money_authority") == "preview_non_authoritative", run)

                gates = p5.evaluate_finalize_gates(
                    cur, company_code=COMPANY, calc_run_id=calc_id, employee_keys=ALL_KEYS
                )
                check("evaluate_finalize_gates ok", gates.get("ok") is True, gates)
                check(
                    "normal employee gates no gcc",
                    not any(b.get("code") == "gcc_extension_review_required" for b in (gates.get("blockers") or [])),
                    gates.get("blockers"),
                )
                gcc = p4b.evaluate_pifss_with_baseline(
                    cur, as_of=p_start, employee_category="gcc_national", pifss_wage_by_fund={"basic": 1000},
                )
                check(
                    "p4b gcc blocker exists",
                    gcc.get("ok") is False and str((gcc.get("blocker") or {}).get("code")) == "gcc_extension_review_required",
                    gcc,
                )

                # Unlocked input blocks gates + create
                cur.execute(
                    "UPDATE payroll_input_snapshots SET status='ready' WHERE company_code=%s AND input_snapshot_id=%s",
                    (COMPANY, sid),
                )
                gates_u = p5.evaluate_finalize_gates(
                    cur, company_code=COMPANY, calc_run_id=calc_id, employee_keys=ALL_KEYS
                )
                check(
                    "unlocked input blocks gates",
                    gates_u.get("ok") is False
                    and any(b.get("code") == "input_snapshot_not_locked" for b in (gates_u.get("blockers") or [])),
                    gates_u,
                )
                create_u = p5.create_finalize_run_from_calc(
                    cur, company_code=COMPANY, calc_run_id=calc_id, actor_phone=CREATOR,
                    reason=f"pap5_{TAG}_unlocked_create", employee_keys=ALL_KEYS,
                )
                check(
                    "unlocked create finalize refused",
                    create_u.get("ok") is False and create_u.get("error") == "finalize_gates_failed",
                    create_u,
                )
                cur.execute(
                    "UPDATE payroll_input_snapshots SET status='locked' WHERE company_code=%s AND input_snapshot_id=%s",
                    (COMPANY, sid),
                )

                pol_f = p5.upsert_company_finalize_policy(
                    cur, company_code=COMPANY, actor_phone=APPROVER, reason=f"pap5_{TAG}_finalize_policy",
                    require_review_step=True, require_distinct_reviewer=True, require_distinct_approver=True,
                    require_distinct_finalizer=True, allow_approver_as_finalizer=True,
                )
                check("finalize policy upsert", pol_f.get("ok") is True, pol_f)

                created = p5.create_finalize_run_from_calc(
                    cur, company_code=COMPANY, calc_run_id=calc_id, actor_phone=CREATOR,
                    reason=f"pap5_{TAG}_create_finalize", employee_keys=ALL_KEYS,
                )
                check("create_finalize_run", created.get("ok") is True, created)
                fid = str((created.get("finalize_run") or {}).get("finalize_run_id"))

                submitted = p5.submit_finalize_for_review(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"pap5_{TAG}_submit",
                )
                check("submit_finalize_for_review", submitted.get("ok") is True, submitted)

                sod_fail = p5.approve_finalize_run(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR,
                    reason=f"pap5_{TAG}_sod_creator_approve",
                )
                check(
                    "SOD creator cannot approve",
                    sod_fail.get("ok") is False and sod_fail.get("error") == "sod_creator_cannot_approve",
                    sod_fail,
                )

                approved = p5.approve_finalize_run(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=APPROVER, reason=f"pap5_{TAG}_approve",
                )
                check("approve_finalize_run", approved.get("ok") is True, approved)

                finalized = p5.finalize_mode_a(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=APPROVER,
                    reason=f"pap5_{TAG}_finalize", employee_keys=ALL_KEYS,
                )
                check("finalize_mode_a", finalized.get("ok") is True, finalized)
                snaps = finalized.get("authority_snapshots") or []
                check("sealed snapshot present", len(snaps) >= 1, snaps)
                auth = snaps[0] if snaps else {}
                aid = str(auth.get("authority_snapshot_id") or "")
                check("money_authority=wathefni", auth.get("money_authority") == "wathefni", auth)
                check("source_kind=native_authoritative", auth.get("source_kind") == "native_authoritative", auth)

                calc_after = p3.get_calc_run(cur, company_code=COMPANY, calc_run_id=calc_id)
                check(
                    "calc still preview_non_authoritative after finalize",
                    (calc_after or {}).get("money_authority") == "preview_non_authoritative",
                    calc_after,
                )

                mutate = p1.refuse_mutate_sealed_snapshot(cur, company_code=COMPANY, authority_snapshot_id=aid)
                check(
                    "immutable refuse_mutate",
                    mutate.get("ok") is False and mutate.get("error") == "sealed_snapshot_immutable",
                    mutate,
                )

                again = p5.finalize_mode_a(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=APPROVER,
                    reason=f"pap5_{TAG}_finalize_again", employee_keys=ALL_KEYS,
                )
                check("repeat finalize idempotent", again.get("ok") is True and again.get("idempotent") is True, again)

                payslip_res = p5.generate_wathefni_payslip_from_sealed(
                    cur, company_code=COMPANY, authority_snapshot_id=aid,
                    actor_phone=APPROVER, reason=f"pap5_{TAG}_payslip",
                )
                check("generate payslip from sealed", payslip_res.get("ok") is True, payslip_res)
                payslip = payslip_res.get("payslip") or {}
                check("payslip money_authority=wathefni", payslip.get("money_authority") == "wathefni", payslip)
                check(
                    "official PDF eligible with sealed verification",
                    opdf.is_official_pdf_eligible(payslip, sealed_snapshot=auth, require_sealed_verification=True) is True,
                    payslip,
                )

                pid = str(payslip.get("payslip_id") or "")
                if hasattr(w3, "release_payslip_to_employee") and pid:
                    check(
                        "unreleased invisible",
                        w3.employee_can_view(payslip) is False and w3.employee_facing_state(payslip) == "not_released",
                        payslip,
                    )
                    released = w3.release_payslip_to_employee(
                        cur, company_code=COMPANY, payslip_id=pid, actor_phone=APPROVER, reason=f"pap5_{TAG}_release",
                    )
                    check("release_payslip_to_employee", released.get("ok") is True, released)
                    check("released visible", w3.employee_can_view(released.get("payslip") or {}) is True, released)

                refuse_preview = p1.seal_from_native_preview(
                    cur, company_code=COMPANY, preview_run_id=str(uuid.uuid4()), employee_key=EMP,
                    actor_phone=APPROVER, reason=f"pap5_{TAG}_refuse_preview_seal",
                )
                check(
                    "seal_from_native_preview still refused",
                    refuse_preview.get("ok") is False
                    and refuse_preview.get("error") == "mode_a_requires_p5_finalize_from_calc",
                    refuse_preview,
                )

            conn.commit()
    except Exception as exc:
        check("runtime", False, f"{type(exc).__name__}: {exc}")
        try:
            cleanup(app, ALL_KEYS, p_start, p_end)
        except Exception:
            pass
        _write_evidence(p_start, p_end)
        return 1

    cleanup(app, ALL_KEYS, p_start, p_end)
    _write_evidence(p_start, p_end)
    print(f"PASS={PASS} FAIL={FAIL} EVID={EVID}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
