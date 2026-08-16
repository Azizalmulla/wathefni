#!/usr/bin/env python3
"""Payroll Wave 2B-B — production synthetic native-preview canary.

Synthetic subjects only (PYW1/PYW2B/W2BB · 965541*).
Proves: full-month, join/exit proration, unpaid leave, fixed components,
missing/overlap denial, idempotency, recalculation, KWD 3dp,
counsel-gated blocked, rollback, residual cleanup.

Does NOT: payslips, bank/WPS, PIFSS remittance, EOS, journals, payments, AI.
Previews non-authoritative; payment_processing=disabled.
Does NOT mutate frozen Wave 2A external adapter flows beyond mode toggle restore.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY", "1")
os.environ.setdefault(
    "WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS",
    "PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,W2BB",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES", "965541,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402
import payroll_native_preview_wave2b as w2b  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW2BB_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-PYW2B-W2BB-{TAG}"
REAL_KEY = "WATHEFNI-96566363363"
CREATOR = f"9655415{TAG_DIGITS}"
APPROVER = f"9655416{TAG_DIGITS}"

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW2BB_EVID") or f"/tmp/payroll-w2bb-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER},
    "preview_run_ids": [],
    "period_ids": [],
    "contract_ids": [],
    "prior_mode": None,
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


def unique_period() -> tuple[date, date]:
    n = int(TAG[:4], 16) % 120
    year = 2028 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def cleanup(cur) -> dict[str, int]:
    deleted: dict[str, int] = {}
    cur.execute(
        """
        SELECT preview_run_id::text FROM payroll_preview_runs
        WHERE company_code=%s AND (
          decision_note LIKE %s OR created_by_phone = ANY(%s)
          OR inputs::text LIKE %s OR result_summary::text LIKE %s
        )
        """,
        (COMPANY, f"%{TAG}%", [CREATOR, APPROVER], f"%{EMP_KEY}%", f"%{EMP_KEY}%"),
    )
    rids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
    if rids:
        cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (rids,))
        deleted["preview_lines"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)",
            (rids,),
        )
        deleted["preview_employees"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (rids,))
        deleted["preview_events"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (rids,))
        deleted["preview_runs"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_preview_events WHERE company_code=%s AND payload::text LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    deleted["orphan_events"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_preview_adjustments WHERE company_code=%s AND (decision_note LIKE %s OR employee_key=%s)",
        (COMPANY, f"%{TAG}%", EMP_KEY),
    )
    deleted["adjustments"] = cur.rowcount or 0

    cur.execute(
        "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    cids = [dict(r)["contract_id"] for r in cur.fetchall()]
    if cids:
        cur.execute(
            "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        cur.execute(
            "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        cur.execute(
            "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contracts"] = cur.rowcount or 0

    cur.execute(
        """
        SELECT period_id::text FROM payroll_periods
        WHERE company_code=%s AND (decision_note LIKE %s OR created_by_phone = ANY(%s))
        """,
        (COMPANY, f"%{TAG}%", [CREATOR, APPROVER]),
    )
    pids = [dict(r)["period_id"] for r in cur.fetchall()]
    if pids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, pids),
        )
        cur.execute("DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)", (COMPANY, pids))
        deleted["periods"] = cur.rowcount or 0
    return deleted


def residual(cur) -> int:
    n = 0
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM payroll_preview_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR inputs::text LIKE %s)
        """,
        (COMPANY, f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_preview_adjustments WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave2bb prod synthetic canary tag={TAG}")
    h = w2b.honesty_payload()
    check("wave2b enabled", w2b.payroll_wave2b_enabled())
    check("synthetic only", w2b.payroll_wave2b_synthetic_only())
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("not authoritative", h.get("authoritative") is False)
    check("preview only", h.get("preview_only") is True)
    check("no AI", h.get("ai_calculations") is False)
    check("external flows unchanged", h.get("external_flows_unchanged") is True)
    check("wave1 enabled", pyw1.payroll_wave1_enabled())
    check("wave2a enabled synthetic", w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only())
    check("money round half up", w2b.money("1.2345") == Decimal("1.235"))
    check("money 3dp", w2b.money("100") == Decimal("100.000"))

    # Pure unit proofs (no DB) — full-month / join / exit / unpaid / fixed / deny / counsel
    p_unit_start, p_unit_end = date(2026, 8, 1), date(2026, 8, 31)
    contract_u = {
        "contract_id": "c1",
        "employee_key": EMP_KEY,
        "status": "approved",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "components": [
            {"component_kind": "earning", "code": "BASIC", "amount": 500, "amount_unit": "monthly", "is_basic": True},
            {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50, "amount_unit": "monthly"},
            {"component_kind": "deduction", "code": "LOAN", "amount": 20, "amount_unit": "monthly"},
        ],
    }
    full = w2b.calculate_employee_preview(
        period_start=p_unit_start, period_end=p_unit_end, employee={"employee_key": EMP_KEY}, contracts=[contract_u]
    )
    check("full-month ok", full.get("ok") is True, full)
    check("full-month earnings 550", abs(float(full.get("totals_earnings") or 0) - 550.0) < 0.001, full)
    check("full-month deductions 20", abs(float(full.get("totals_deductions") or 0) - 20.0) < 0.001, full)
    check("full-month net 530", abs(float(full.get("totals_net_preview") or 0) - 530.0) < 0.001, full)

    join = w2b.calculate_employee_preview(
        period_start=p_unit_start,
        period_end=p_unit_end,
        employee={"employee_key": EMP_KEY, "employment_start": "2026-08-16"},
        contracts=[contract_u],
    )
    expected_join = w2b.money(Decimal("550") * 16 / 31)
    check("mid join ok", join.get("ok") is True, join)
    check("mid join active 16", join.get("active_days") == 16, join)
    check("mid join earnings prorated", abs(float(join.get("totals_earnings") or 0) - float(expected_join)) < 0.001, join)

    exit_r = w2b.calculate_employee_preview(
        period_start=p_unit_start,
        period_end=p_unit_end,
        employee={"employee_key": EMP_KEY, "employment_end": "2026-08-15"},
        contracts=[contract_u],
    )
    expected_exit = w2b.money(Decimal("550") * 15 / 31)
    check("mid exit ok", exit_r.get("ok") is True, exit_r)
    check("mid exit active 15", exit_r.get("active_days") == 15, exit_r)
    check("mid exit earnings prorated", abs(float(exit_r.get("totals_earnings") or 0) - float(expected_exit)) < 0.001, exit_r)

    unpaid = w2b.calculate_employee_preview(
        period_start=p_unit_start,
        period_end=p_unit_end,
        employee={"employee_key": EMP_KEY},
        contracts=[contract_u],
        unpaid_leaves=[{"employee_key": EMP_KEY, "classification": "unpaid_leave", "chargeable_days": 2}],
    )
    unpaid_ded = w2b.money(Decimal("550") * 2 / 31)
    check("unpaid ok", unpaid.get("ok") is True, unpaid)
    check(
        "unpaid deduction applied",
        abs(float(unpaid.get("totals_deductions") or 0) - float(w2b.money(20) + unpaid_ded)) < 0.001,
        unpaid,
    )

    adj = w2b.calculate_employee_preview(
        period_start=p_unit_start,
        period_end=p_unit_end,
        employee={"employee_key": EMP_KEY},
        contracts=[contract_u],
        adjustments=[
            {"employee_key": EMP_KEY, "component_kind": "earning", "code": "BONUS", "amount": 100},
            {"employee_key": EMP_KEY, "component_kind": "deduction", "code": "FINE", "amount": 5.555},
        ],
    )
    check("fixed adjustment ok", adj.get("ok") is True, adj)
    check("bonus included", abs(float(adj.get("totals_earnings") or 0) - 650.0) < 0.001, adj)
    check("fine rounded 3dp", abs(float(adj.get("totals_deductions") or 0) - 25.555) < 0.001, adj)

    missing = w2b.calculate_employee_preview(
        period_start=p_unit_start, period_end=p_unit_end, employee={"employee_key": EMP_KEY}, contracts=[]
    )
    check("missing contract blocked", missing.get("ok") is False, missing)
    check(
        "missing contract code",
        any(b.get("code") == "missing_approved_contract" for b in (missing.get("blockers") or [])),
        missing,
    )

    c2 = {
        **contract_u,
        "contract_id": "c2",
        "effective_from": "2026-08-01",
        "components": [
            {"component_kind": "earning", "code": "BASIC", "amount": 600, "amount_unit": "monthly", "is_basic": True}
        ],
    }
    overlap = w2b.calculate_employee_preview(
        period_start=p_unit_start,
        period_end=p_unit_end,
        employee={"employee_key": EMP_KEY},
        contracts=[contract_u, c2],
    )
    check("overlap blocked", overlap.get("ok") is False, overlap)
    check(
        "overlap code",
        any(b.get("code") == "overlapping_approved_contracts" for b in (overlap.get("blockers") or [])),
        overlap,
    )

    for rule in ("pifss", "overtime_premiums", "sick_leave_pay_fractions", "eos", "public_holiday_rest_day_pay"):
        blocked = w2b.calculate_employee_preview(
            period_start=p_unit_start,
            period_end=p_unit_end,
            employee={"employee_key": EMP_KEY},
            contracts=[contract_u],
            requested_unsupported=[rule],
        )
        check(f"counsel {rule} blocked", blocked.get("ok") is False, blocked)
        check(
            f"counsel {rule} review_only",
            any(b.get("posture") == "review_only" for b in (blocked.get("blockers") or [])),
            blocked,
        )

    p_start, p_end = unique_period()
    IDS["period"] = {"start": str(p_start), "end": str(p_end)}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            check("production db", db == "wathefni", db)

            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            IDS["prior_mode"] = str(settings.get("payroll_mode") or "native")
            check("payment_processing disabled in settings", settings.get("payment_processing") == "disabled")

            mode_set = pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"w2bb_mode_native_{TAG}"
            )
            check("set native mode", mode_set.get("ok") is True, mode_set)

            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50},
                    {"component_kind": "deduction", "code": "LOAN", "amount": 20},
                ],
                actor_phone=CREATOR,
                reason=f"w2bb_draft_{TAG}",
            )
            check("db draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id") or "")
            IDS["contract_ids"].append(cid)
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2bb_approve_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("db approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

            # Period get-or-create (avoid unique-constraint abort)
            cur.execute(
                """
                SELECT * FROM payroll_periods
                WHERE company_code=%s AND period_start=%s AND period_end=%s
                ORDER BY created_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY, p_start, p_end),
            )
            existing = cur.fetchone()
            if existing:
                period = {"ok": True, "period": dict(existing), "reused": True}
            else:
                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"w2bb_period_{TAG}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")
            if pid:
                IDS["period_ids"].append(pid)

            run1 = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                period_id=pid or None,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2bb_calc1_{TAG}",
            )
            check("preview run ok", run1.get("ok") is True, run1)
            check("preview not authoritative", run1.get("authoritative") is False)
            check("preview payment disabled", run1.get("payment_processing") == "disabled")
            rid1 = str((run1.get("preview_run") or {}).get("preview_run_id") or "")
            IDS["preview_run_ids"].append(rid1)
            fp1 = run1.get("input_fingerprint")
            emp_results = run1.get("employee_results") or []
            check("employee result present", len(emp_results) == 1, emp_results)
            if emp_results:
                er = emp_results[0]
                check("db full-month earnings", abs(float(er.get("totals_earnings") or 0) - 550.0) < 0.001, er)
                check("db full-month net", abs(float(er.get("totals_net_preview") or 0) - 530.0) < 0.001, er)

            run_idem = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2bb_calc_idem_{TAG}",
            )
            check("idempotent replay", run_idem.get("idempotent") is True, run_idem)

            run2 = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                unpaid_leaves=[
                    {
                        "employee_key": EMP_KEY,
                        "classification": "unpaid",
                        "chargeable_days": 1,
                        "leave_id": f"L-{TAG}",
                    }
                ],
                actor_phone=CREATOR,
                reason=f"w2bb_calc2_{TAG}",
            )
            check("recalc after input change", run2.get("ok") is True and not run2.get("idempotent"), run2)
            check("fingerprint changed", run2.get("input_fingerprint") != fp1, run2)
            check("prior superseded", bool(run2.get("superseded_run_ids")), run2)
            rid2 = str((run2.get("preview_run") or {}).get("preview_run_id") or "")
            IDS["preview_run_ids"].append(rid2)

            run_bad = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                requested_unsupported=["eos", "pifss", "overtime_premiums"],
                actor_phone=CREATOR,
                reason=f"w2bb_unsupported_{TAG}",
            )
            check("unsupported run failed closed", run_bad.get("ok") is False, run_bad)
            # Failed run must not supersede successful calculated preview
            cur.execute(
                "SELECT status FROM payroll_preview_runs WHERE preview_run_id=%s",
                (rid2,),
            )
            st2 = dict(cur.fetchone() or {}).get("status")
            check("failed run did not supersede success", st2 == "calculated", st2)

            blocked_mode = None
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w2bb_ext_{TAG}"
            )
            blocked_mode = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2bb_mode_block_{TAG}",
            )
            check("external mode blocks preview", blocked_mode.get("error") == "mode_not_native_preview", blocked_mode)
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"w2bb_restore_native_{TAG}"
            )

            rb = w2b.rollback_preview_run(
                cur,
                company_code=COMPANY,
                preview_run_id=rid2,
                actor_phone=APPROVER,
                reason=f"w2bb_rollback_{TAG}",
            )
            check("rollback ok", rb.get("ok") is True, rb)
            check("rollback status", (rb.get("preview_run") or {}).get("status") == "rolled_back", rb)

            events = w2b.list_preview_events(cur, company_code=COMPANY, limit=40)
            check("audit events present", len(events) >= 1, len(events))

            real = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": REAL_KEY}],
                contracts=[],
                actor_phone=CREATOR,
                reason=f"w2bb_real_{TAG}",
            )
            check("real employee refused", real.get("error") == "payroll_wave2b_synthetic_only", real)

            # Restore prior payroll_mode (Wave 2A may have left external)
            restore_mode = IDS["prior_mode"] if IDS["prior_mode"] in ("native", "external", "parallel_shadow") else "external"
            restored = pyw1.set_payroll_mode(
                cur,
                company_code=COMPANY,
                mode=restore_mode,
                actor_phone=APPROVER,
                reason=f"w2bb_restore_prior_{TAG}",
            )
            check("restore prior mode", restored.get("ok") is True, restored)

            deleted = cleanup(cur)
            res = residual(cur)
            check("residual zero", res == 0, {"residual": res, "deleted": deleted})
            IDS["cleanup"] = {"deleted": deleted, "residual_total": res}

            conn.commit()

    qual = {
        "tag": TAG,
        "passed": PASS,
        "failed": FAIL,
        "ids": IDS,
        "results": RESULTS,
        "honesty": h,
        "cleanup": IDS.get("cleanup") or {},
        "wave": "2B-B",
        "authoritative": False,
        "payment_processing": "disabled",
        "ai_calculations": False,
        "payslips": False,
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("QUALIFICATION_JSON", EVID / "qualification.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
