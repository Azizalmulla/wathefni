"""Payroll Authority P6 — independent expected-results oracle.

Deterministic Decimal calculator for qualification fixtures.
Does NOT import payroll_components_policy_p3 calculation internals.
Used only to assert residual-zero against engine outputs.
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ORACLE_VERSION = "1.0.0"
MONEY_Q = Decimal("0.001")
_HERE = Path(__file__).resolve().parent
_FIXTURE_CANDIDATES = [
    _HERE / "ops" / "payroll_authority_p6_oracle_fixtures_v1.json",
    _HERE.parent / "ops" / "payroll_authority_p6_oracle_fixtures_v1.json",
]
FIXTURE_PATH = next((p for p in _FIXTURE_CANDIDATES if p.exists()), _FIXTURE_CANDIDATES[0])


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _days_inclusive(start: str, end: str) -> int:
    from datetime import date

    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return (e - s).days + 1


def _prorate(amount: Decimal, days_worked: int, days_in_period: int) -> Decimal:
    if days_in_period <= 0:
        return money(0)
    return money(amount * Decimal(days_worked) / Decimal(days_in_period))


def compute_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Independent expected money for one fixture scenario."""
    period = scenario["period"]
    days_in_period = int(period.get("calendar_days") or _days_inclusive(period["start"], period["end"]))
    emp = scenario["employee"]
    days_worked = int(emp.get("days_worked_in_period") or days_in_period)
    basic = money(emp.get("basic_salary") or 0)
    if emp.get("mid_period_hire") or emp.get("mid_period_leaver") or emp.get("prorate"):
        basic_earn = _prorate(basic, days_worked, days_in_period)
    else:
        basic_earn = basic

    # Mid-period salary increase: weighted average of old/new
    if emp.get("salary_increase"):
        inc = emp["salary_increase"]
        days_before = int(inc["days_before"])
        days_after = int(inc["days_after"])
        basic_earn = money(
            _prorate(money(inc["old_basic"]), days_before, days_in_period)
            + _prorate(money(inc["new_basic"]), days_after, days_in_period)
        )

    earnings: list[dict[str, Any]] = [
        {
            "code": "BASIC",
            "category": "earning_basic",
            "amount": float(basic_earn),
        }
    ]
    earn_total = basic_earn
    for a in emp.get("allowances") or []:
        amt = money(a.get("amount") or 0)
        if a.get("prorate"):
            amt = _prorate(amt, days_worked, days_in_period)
        earnings.append(
            {
                "code": str(a["code"]),
                "category": str(a.get("category") or "earning_allowance_recurring"),
                "amount": float(amt),
            }
        )
        earn_total += amt
    for b in emp.get("bonuses") or []:
        amt = money(b.get("amount") or 0)
        earnings.append(
            {
                "code": str(b["code"]),
                "category": "earning_allowance_one_off",
                "amount": float(amt),
            }
        )
        earn_total += amt

    # OT / rest / PH using explicit multipliers from fixture (not engine)
    hourly = money(0)
    if emp.get("hourly_divisor_hours"):
        hourly = money(basic / Decimal(str(emp["hourly_divisor_hours"])))
    if emp.get("ot_ordinary_hours"):
        mult = Decimal(str(emp.get("ot_ordinary_multiplier") or "1.25"))
        amt = money(hourly * Decimal(str(emp["ot_ordinary_hours"])) * mult)
        earnings.append({"code": "OT_ORDINARY", "category": "earning_ot_ordinary", "amount": float(amt)})
        earn_total += amt
    if emp.get("rest_day_hours"):
        mult = Decimal(str(emp.get("rest_day_multiplier") or "1.5"))
        amt = money(hourly * Decimal(str(emp["rest_day_hours"])) * mult)
        earnings.append({"code": "REST_DAY", "category": "earning_rest_day", "amount": float(amt)})
        earn_total += amt
    if emp.get("public_holiday_hours"):
        mult = Decimal(str(emp.get("public_holiday_multiplier") or "2.0"))
        amt = money(hourly * Decimal(str(emp["public_holiday_hours"])) * mult)
        earnings.append({"code": "PH_WORK", "category": "earning_public_holiday", "amount": float(amt)})
        earn_total += amt

    deductions: list[dict[str, Any]] = []
    ded_total = money(0)
    for d in emp.get("deductions") or []:
        amt = money(d.get("amount") or 0)
        deductions.append(
            {
                "code": str(d["code"]),
                "category": str(d.get("category") or "deduction_recurring"),
                "amount": float(amt),
            }
        )
        ded_total += amt

    daily = money(basic / Decimal(days_in_period)) if days_in_period else money(0)
    unpaid_days = Decimal(str(emp.get("unpaid_leave_days") or 0))
    if unpaid_days > 0 and emp.get("unpaid_leave_money"):
        amt = money(daily * unpaid_days)
        deductions.append({"code": "UNPAID_LEAVE", "category": "deduction_unpaid_leave", "amount": float(amt)})
        ded_total += amt
    absence_days = Decimal(str(emp.get("absence_days") or 0))
    if absence_days > 0 and emp.get("absence_money"):
        amt = money(daily * absence_days)
        deductions.append({"code": "ABSENCE", "category": "deduction_absence", "amount": float(amt)})
        ded_total += amt
    if emp.get("lateness_deduction"):
        amt = money(emp["lateness_deduction"])
        deductions.append({"code": "LATENESS", "category": "deduction_lateness", "amount": float(amt)})
        ded_total += amt

    statutory_ee: list[dict[str, Any]] = []
    statutory_er: list[dict[str, Any]] = []
    if emp.get("pifss") and emp.get("pifss_resolvable"):
        wage = money(emp["pifss"]["contributory_wage"])
        ee_pct = Decimal(str(emp["pifss"].get("ee_pct") or "0.075"))
        er_pct = Decimal(str(emp["pifss"].get("er_pct") or "0.115"))
        ee_amt = money(wage * ee_pct)
        er_amt = money(wage * er_pct)
        statutory_ee.append({"code": "PIFSS_EE", "amount": float(ee_amt)})
        statutory_er.append({"code": "PIFSS_ER", "amount": float(er_amt)})
        ded_total += ee_amt

    blockers = list(scenario.get("expected_blockers") or [])
    if emp.get("statutory_gated"):
        code = str(emp["statutory_gated"])
        if code not in blockers:
            blockers.append(code)

    if scenario.get("money_authority") == "external":
        gross = money(emp.get("external_gross") or emp.get("basic_salary") or 0)
        net = money(emp.get("external_net") if emp.get("external_net") is not None else gross)
        earn_total = gross
        ded_total = money(gross - net)
        earnings = [{"code": "EXTERNAL_GROSS", "category": "external", "amount": float(gross)}]
        deductions = [{"code": "EXTERNAL_DEDUCTIONS", "category": "external", "amount": float(ded_total)}] if ded_total else []
        if "mode_b_external_authority" not in (scenario.get("expected_warnings") or []):
            warnings = list(scenario.get("expected_warnings") or []) + ["mode_b_external_authority"]
        else:
            warnings = list(scenario.get("expected_warnings") or [])
        return {
            "scenario_id": scenario["id"],
            "oracle_version": ORACLE_VERSION,
            "policy_versions": scenario.get("policy_versions") or {},
            "earnings": earnings,
            "deductions": deductions,
            "statutory_employee": [],
            "statutory_employer": [],
            "gross": float(gross),
            "net": float(net),
            "blockers": blockers,
            "warnings": warnings,
            "authoritative_eligible": False,
            "money_authority": "external",
        }

    gross = earn_total
    net = money(gross - ded_total)
    warnings = list(scenario.get("expected_warnings") or [])

    return {
        "scenario_id": scenario["id"],
        "oracle_version": ORACLE_VERSION,
        "policy_versions": scenario.get("policy_versions") or {},
        "earnings": earnings,
        "deductions": deductions,
        "statutory_employee": statutory_ee,
        "statutory_employer": statutory_er,
        "gross": float(gross),
        "net": float(net),
        "blockers": blockers,
        "warnings": warnings,
        "authoritative_eligible": not blockers and bool(scenario.get("authoritative_eligible", True)),
    }


def load_fixtures(path: Path | None = None) -> dict[str, Any]:
    p = path or FIXTURE_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def compute_all(path: Path | None = None) -> dict[str, Any]:
    pack = load_fixtures(path)
    results = []
    residual_issues = []
    for sc in pack.get("scenarios") or []:
        expected = compute_scenario(sc)
        # Fixture may embed expected_totals for self-consistency of the pack
        emb = sc.get("expected_totals")
        if emb:
            g = money(emb.get("gross"))
            n = money(emb.get("net"))
            if g != money(expected["gross"]) or n != money(expected["net"]):
                residual_issues.append(
                    {
                        "scenario_id": sc["id"],
                        "fixture_gross": float(g),
                        "oracle_gross": expected["gross"],
                        "fixture_net": float(n),
                        "oracle_net": expected["net"],
                    }
                )
        results.append(expected)
    return {
        "ok": len(residual_issues) == 0,
        "oracle_version": ORACLE_VERSION,
        "fixture_version": pack.get("fixture_version"),
        "statutory_policy_version": pack.get("statutory_policy_version"),
        "results": results,
        "fixture_self_consistency_residuals": residual_issues,
        "residual_count": len(residual_issues),
    }


def compare_engine_to_oracle(
    *,
    oracle: dict[str, Any],
    engine_lines: list[dict[str, Any]],
    engine_totals: dict[str, Any],
    tolerance: Decimal = Decimal("0.001"),
) -> dict[str, Any]:
    """Compare engine monetary totals/lines to oracle; residual must be ~0."""
    og = money(oracle.get("gross"))
    on = money(oracle.get("net"))
    eg = money(engine_totals.get("gross"))
    en = money(engine_totals.get("net"))
    gross_residual = abs(og - eg)
    net_residual = abs(on - en)

    # Code-level amounts where both sides declare codes
    oracle_by_code = {str(x["code"]): money(x["amount"]) for x in (oracle.get("earnings") or []) + (oracle.get("deductions") or [])}
    engine_by_code: dict[str, Decimal] = {}
    for ln in engine_lines or []:
        code = str(ln.get("code") or ln.get("component_code") or "")
        if not code:
            continue
        engine_by_code[code] = engine_by_code.get(code, money(0)) + money(ln.get("amount") or ln.get("amount_money") or 0)

    line_residuals = []
    for code, amt in oracle_by_code.items():
        eng = engine_by_code.get(code, money(0))
        delta = abs(amt - eng)
        if delta > tolerance:
            line_residuals.append({"code": code, "oracle": float(amt), "engine": float(eng), "delta": float(delta)})

    ok = gross_residual <= tolerance and net_residual <= tolerance and not line_residuals
    return {
        "ok": ok,
        "gross_residual": float(gross_residual),
        "net_residual": float(net_residual),
        "line_residuals": line_residuals,
        "unexplained_residual": float(gross_residual + net_residual),
    }
