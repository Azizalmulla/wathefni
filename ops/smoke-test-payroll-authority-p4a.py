#!/usr/bin/env python3
"""Payroll Authority P4A — Kuwait statutory architecture qualification.

Proves versioned counsel-gated packaging, A/B/C/D boundaries, fail-closed legal path,
architecture fixtures (legal_claim=false), EOS settlement snapshots, P3 bridge.
Does NOT invent Kuwait legal rates or unlock Mode A / PDF / payments.
"""
from __future__ import annotations

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
    (p for p in ORCH_CANDIDATES if (p / "payroll_statutory_architecture_p4a.py").exists()),
    ORCH_CANDIDATES[0],
)
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
for flag in (
    "WATHEFNI_PAYROLL_WAVE1",
    "WATHEFNI_PAYROLL_AUTHORITY_P1",
    "WATHEFNI_PAYROLL_AUTHORITY_P2",
    "WATHEFNI_PAYROLL_AUTHORITY_P3",
    "WATHEFNI_PAYROLL_AUTHORITY_P4A",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYP1,PYP2,PYP3,PYP4A,PYSTAT,PYINPUT,PYCALC"
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P4A_SYNTHETIC_KEY_MARKERS", MARKERS)

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP4A_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
ACTOR = f"9655618{TAG_DIGITS}"
EMP_EOS = f"WATHEFNI-PYW1-PYP4A-EOS-{TAG}"
EMP_SICK = f"WATHEFNI-PYW1-PYP4A-SICK-{TAG}"

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP4A_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p4a-{STAMP}"))
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


def cleanup(app: Any, package_ids: list[str], keys: list[str]) -> None:
    import payroll_statutory_architecture_p4a as p4a

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            p4a.ensure_payroll_statutory_architecture_schema(cur)
            cur.execute(
                "DELETE FROM payroll_eos_settlement_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                """
                DELETE FROM payroll_statutory_eval_lines
                WHERE company_code=%s
                  AND eval_run_id IN (
                    SELECT eval_run_id FROM payroll_statutory_eval_runs
                    WHERE company_code=%s AND decision_note LIKE %s
                  )
                """,
                (COMPANY, COMPANY, f"%pap4a_{TAG}%"),
            )
            cur.execute(
                "DELETE FROM payroll_statutory_eval_runs WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap4a_{TAG}%"),
            )
            if package_ids:
                cur.execute(
                    """
                    DELETE FROM payroll_pifss_contribution_specs
                    WHERE rule_version_id IN (
                      SELECT rule_version_id FROM payroll_statutory_rule_versions
                      WHERE package_id::text = ANY(%s)
                    )
                    """,
                    (package_ids,),
                )
                cur.execute(
                    "DELETE FROM payroll_statutory_rule_versions WHERE package_id::text = ANY(%s)",
                    (package_ids,),
                )
                cur.execute(
                    "DELETE FROM payroll_statutory_packages WHERE package_id::text = ANY(%s)",
                    (package_ids,),
                )
            cur.execute(
                """
                DELETE FROM payroll_rate_tables
                WHERE company_code=%s
                  AND counsel_signed=false
                  AND version_label LIKE %s
                """,
                (COMPANY, "p4a_architecture_%"),
            )
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            cur.execute(
                "DELETE FROM payroll_statutory_events WHERE company_code=%s AND payload::text LIKE %s",
                (COMPANY, f"%{TAG}%"),
            )
        conn.commit()


def main() -> int:
    import payroll_authority_snapshot_p1 as p1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_statutory_architecture_p4a as p4a

    h = p4a.honesty_payload()
    inv = p4a.freeze_invariants()
    boundary = p4a.output_class_boundary()
    p4b = p4a.p4b_required_legal_inputs()

    check("p4a version", p4a.PAYROLL_AUTHORITY_P4A_VERSION == "1.0.0")
    check("preview only", h.get("money_authority") == "preview_non_authoritative")
    check("no invented rates", h.get("kuwait_statutory_rates_invented") is False)
    check("no legal claim", h.get("kuwait_legal_claim") is False)
    check("mode a locked", h.get("mode_a_wathefni_seal_unlocked") is False)
    check("native pdf locked", h.get("native_official_pdf_unlocked") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("remittance not payment", h.get("remittance_is_not_payment") is True)
    check("eos not auto payable", h.get("eos_auto_payable") is False)
    check("no speculative gcc", h.get("speculative_gcc_rules_implemented") is False)
    check("invariant no invented", inv.get("no_invented_kuwait_rates") is True)
    check("invariant pifss distinct", inv.get("pifss_ee_er_remittance_distinct") is True)
    check("invariant eos settlement", inv.get("eos_is_settlement_not_monthly_line") is True)
    check("boundary A exists", "A_employee_net" in boundary)
    check("boundary D remittance", "D_remittance_reporting" in boundary)
    check("p4b inputs listed", len(p4b.get("required") or []) >= 6)
    check("p1 preserved", p1.PAYROLL_AUTHORITY_P1_VERSION == "1.0.0")
    check("p2 preserved", p2.PAYROLL_AUTHORITY_P2_VERSION == "1.0.0")
    check("p3 preserved", p3.PAYROLL_AUTHORITY_P3_VERSION == "1.0.0")

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            (EVID / "SUMMARY.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "skip": True}, indent=2))
            return 0
        raise

    package_ids: list[str] = []
    as_of = date(2036, 3, 1)
    as_of_early = date(2035, 1, 1)
    keys = [EMP_EOS, EMP_SICK]
    cleanup(app, [], keys)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                p4a.ensure_payroll_statutory_architecture_schema(cur, force=True)
                p3.ensure_payroll_components_policy_schema(cur)

                # Legal approve refused
                refused = p4a.refuse_legal_approve_package(
                    cur, package_id=str(uuid.uuid4()), actor_phone=ACTOR, reason=f"pap4a_{TAG}_refuse"
                )
                check("legal approve refused", refused.get("ok") is False and refused.get("error") == "legal_approval_reserved_for_p4b")

                # Non-fixture numeric rate refused
                pkg_draft = p4a.create_statutory_package(
                    cur,
                    company_code=COMPANY,
                    package_code=f"KW_CORE_{TAG}",
                    effective_from=as_of_early,
                    title_en="Kuwait core architecture",
                    title_ar="هيكل الكويت",
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_pkg_draft",
                    is_architecture_fixture=False,
                    approval_status="draft",
                )
                check("draft package", pkg_draft.get("ok") is True, pkg_draft)
                pid_draft = str((pkg_draft.get("package") or {}).get("package_id"))
                package_ids.append(pid_draft)
                bad_rate = p4a.create_rule_version(
                    cur,
                    package_id=pid_draft,
                    rule_family="ot_ordinary",
                    output_class="A_employee_net",
                    version_label="illegal-rate-attempt",
                    effective_from=as_of,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_bad_rate",
                    multiplier=1.25,
                    is_architecture_fixture=False,
                )
                check("invented rate refused", bad_rate.get("ok") is False, bad_rate)

                submitted = p4a.submit_package_for_legal_validation(
                    cur, package_id=pid_draft, actor_phone=ACTOR, reason=f"pap4a_{TAG}_await"
                )
                check("awaiting legal validation", submitted.get("ok") is True and (submitted.get("package") or {}).get("approval_status") == "awaiting_legal_validation")

                # Architecture fixture package with versioned rules
                pkg = p4a.create_statutory_package(
                    cur,
                    company_code=COMPANY,
                    package_code=f"KW_ARCH_{TAG}",
                    effective_from=as_of_early,
                    title_en="Architecture fixture package",
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_pkg_arch",
                    is_architecture_fixture=True,
                    approval_status="approved",
                )
                check("architecture package", pkg.get("ok") is True, pkg)
                check("architecture never legal_claim", (pkg.get("package") or {}).get("legal_claim") is False)
                pid = str((pkg.get("package") or {}).get("package_id"))
                package_ids.append(pid)

                # v1 OT effective early
                ot_v1 = p4a.create_rule_version(
                    cur,
                    package_id=pid,
                    rule_family="ot_ordinary",
                    output_class="A_employee_net",
                    version_label="arch-ot-v1",
                    effective_from=as_of_early,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_ot_v1",
                    multiplier=1.11,
                    is_architecture_fixture=True,
                    approval_status="approved",
                    company_code=COMPANY,
                )
                check("ot v1 fixture", ot_v1.get("ok") is True, ot_v1)
                ot_v1_id = str((ot_v1.get("rule_version") or {}).get("rule_version_id"))

                # v2 OT effective later — version selection
                ot_v2 = p4a.create_rule_version(
                    cur,
                    package_id=pid,
                    rule_family="ot_ordinary",
                    output_class="A_employee_net",
                    version_label="arch-ot-v2",
                    effective_from=as_of,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_ot_v2",
                    multiplier=1.22,
                    is_architecture_fixture=True,
                    approval_status="approved",
                    company_code=COMPANY,
                )
                check("ot v2 fixture", ot_v2.get("ok") is True, ot_v2)
                ot_v2_id = str((ot_v2.get("rule_version") or {}).get("rule_version_id"))

                sel_early = p4a.resolve_rule_version(
                    cur,
                    company_code=COMPANY,
                    rule_family="ot_ordinary",
                    as_of=as_of_early + timedelta(days=10),
                    require_legal_claim=False,
                    allow_architecture_fixture=True,
                )
                check("effective-date selects v1", str((sel_early or {}).get("rule_version_id")) == ot_v1_id, sel_early)
                sel_late = p4a.resolve_rule_version(
                    cur,
                    company_code=COMPANY,
                    rule_family="ot_ordinary",
                    as_of=as_of,
                    require_legal_claim=False,
                    allow_architecture_fixture=True,
                )
                check("effective-date selects v2", str((sel_late or {}).get("rule_version_id")) == ot_v2_id, sel_late)

                # Legal path: P4B public baseline may resolve; architecture fixtures never qualify as legal_claim alone
                legal_miss = p4a.require_rule_or_blocker(
                    cur,
                    company_code=COMPANY,
                    rule_family="ot_ordinary",
                    as_of=as_of,
                    require_legal_claim=True,
                    allow_architecture_fixture=False,
                )
                p3_legal = p3.get_approved_rate(cur, company_code=COMPANY, rule_family="ot_ordinary", as_of=as_of)
                if legal_miss.get("ok") and (legal_miss.get("rule_version") or {}).get("authority_kind") == "wathefni_public_baseline":
                    check("public baseline legal resolve", legal_miss.get("ok") is True, legal_miss)
                    check(
                        "p3 legal rate from public baseline",
                        p3_legal is not None
                        and p3_legal.get("source") == "p4b_public_baseline"
                        and float(p3_legal.get("multiplier") or 0) == 1.25,
                        p3_legal,
                    )
                else:
                    check("missing legal approved fails closed", legal_miss.get("ok") is False, legal_miss)
                    check("p3 legal rate still none", p3_legal is None)

                # Distinct families
                for fam, out_cls, mult, frac in (
                    ("rest_day_work", "A_employee_net", 1.33, None),
                    ("public_holiday_work", "A_employee_net", 1.44, None),
                    ("sick_leave_fractions", "A_employee_net", None, {"default_fraction": 0.75, "day_1_to_15": 0.75}),
                    ("eos_indemnity", "C_settlement", 0.5, None),
                    ("pifss", "mixed_pifss_pack", None, None),
                ):
                    rv = p4a.create_rule_version(
                        cur,
                        package_id=pid,
                        rule_family=fam,
                        output_class=out_cls,
                        version_label=f"arch-{fam}",
                        effective_from=as_of,
                        actor_phone=ACTOR,
                        reason=f"pap4a_{TAG}_{fam}",
                        multiplier=mult,
                        fraction_payload=frac,
                        rate_payload={"architecture_factor": mult} if fam == "eos_indemnity" else {"architecture_only": True},
                        is_architecture_fixture=True,
                        approval_status="approved",
                        company_code=COMPANY,
                    )
                    check(f"family {fam}", rv.get("ok") is True, rv)

                # Collapse refused
                collapse = p4a.create_rule_version(
                    cur,
                    package_id=pid,
                    rule_family="ot_ordinary",
                    output_class="B_employer_liability",
                    version_label="bad-collapse",
                    effective_from=as_of,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_collapse",
                    multiplier=1.0,
                    is_architecture_fixture=True,
                    approval_status="approved",
                )
                check("ot not collapsible to B", collapse.get("ok") is False, collapse)

                # PIFSS EE/ER/remittance distinct
                pifss_rule = p4a.resolve_rule_version(
                    cur,
                    company_code=COMPANY,
                    rule_family="pifss",
                    as_of=as_of,
                    require_legal_claim=False,
                    allow_architecture_fixture=True,
                )
                check("pifss rule resolved", pifss_rule is not None)
                pifss_id = str((pifss_rule or {}).get("rule_version_id"))
                sides = []
                for side, pct in (
                    ("employee_deduction", 5.0),
                    ("employer_contribution", 10.0),
                    ("remittance_obligation", 15.0),
                ):
                    spec = p4a.add_pifss_contribution_spec(
                        cur,
                        rule_version_id=pifss_id,
                        employee_category="kuwaiti_national",
                        contribution_side=side,
                        actor_phone=ACTOR,
                        reason=f"pap4a_{TAG}_{side}",
                        rate_percent=pct,
                        rate_is_architecture_fixture=True,
                    )
                    check(f"pifss {side}", spec.get("ok") is True, spec)
                    sides.append((side, (spec.get("spec") or {}).get("output_class")))
                check("pifss EE is A", sides[0][1] == "A_employee_net")
                check("pifss ER is B", sides[1][1] == "B_employer_liability")
                check("pifss remit is D", sides[2][1] == "D_remittance_reporting")

                # Supersede v2 — cannot be used for new period selection among approved
                sup = p4a.supersede_rule_version(
                    cur, rule_version_id=ot_v2_id, actor_phone=ACTOR, reason=f"pap4a_{TAG}_supersede_ot_v2"
                )
                check("supersede ot v2", sup.get("ok") is True, sup)
                after_sup = p4a.resolve_rule_version(
                    cur,
                    company_code=COMPANY,
                    rule_family="ot_ordinary",
                    as_of=as_of,
                    require_legal_claim=False,
                    allow_architecture_fixture=True,
                )
                check(
                    "superseded not selected",
                    str((after_sup or {}).get("rule_version_id")) == ot_v1_id,
                    after_sup,
                )

                # Recreate v3 for remaining eval after supersede
                ot_v3 = p4a.create_rule_version(
                    cur,
                    package_id=pid,
                    rule_family="ot_ordinary",
                    output_class="A_employee_net",
                    version_label="arch-ot-v3",
                    effective_from=as_of,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_ot_v3",
                    multiplier=1.22,
                    is_architecture_fixture=True,
                    approval_status="approved",
                    company_code=COMPANY,
                )
                check("ot v3 after supersede", ot_v3.get("ok") is True, ot_v3)

                # Statutory evaluate with architecture fixtures
                ev = p4a.evaluate_statutory_period(
                    cur,
                    company_code=COMPANY,
                    period_start=as_of,
                    period_end=as_of + timedelta(days=30),
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_eval",
                    allow_architecture_fixture=True,
                )
                check("eval ok", ev.get("ok") is True, ev)
                families = set(ev.get("resolved_families") or [])
                check("eval has ot", "ot_ordinary" in families)
                check("eval has rest", "rest_day_work" in families)
                check("eval has ph", "public_holiday_work" in families)
                check("eval has sick", "sick_leave_fractions" in families)
                check("eval has pifss", "pifss" in families)
                line_classes = {str(ln.get("output_class")) for ln in (ev.get("lines") or [])}
                check("eval has A", "A_employee_net" in line_classes)
                check("eval has B", "B_employer_liability" in line_classes)
                check("eval has D", "D_remittance_reporting" in line_classes)
                check("eval never legal_claim", (ev.get("eval_run") or {}).get("legal_claim") is False)
                ot_lines = [ln for ln in (ev.get("lines") or []) if ln.get("rule_family") == "ot_ordinary"]
                rest_lines = [ln for ln in (ev.get("lines") or []) if ln.get("rule_family") == "rest_day_work"]
                ph_lines = [ln for ln in (ev.get("lines") or []) if ln.get("rule_family") == "public_holiday_work"]
                check("ot/rest/ph remain separate", len(ot_lines) == 1 and len(rest_lines) == 1 and len(ph_lines) == 1)

                # Legal evaluate: public baseline may satisfy families; still preview_non_authoritative
                ev_legal = p4a.evaluate_statutory_period(
                    cur,
                    company_code=COMPANY,
                    period_start=as_of,
                    period_end=as_of + timedelta(days=30),
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_eval_legal",
                    allow_architecture_fixture=False,
                    require_families=["ot_ordinary", "pifss"],
                )
                if (ev_legal.get("resolved_families") or []) and not ev_legal.get("blockers"):
                    check(
                        "legal eval via public baseline",
                        ev_legal.get("ok") is True
                        and (ev_legal.get("eval_run") or {}).get("money_authority") == "preview_non_authoritative"
                        and (ev_legal.get("eval_run") or {}).get("legal_claim") is False,
                        ev_legal,
                    )
                else:
                    check("legal eval blocked", bool(ev_legal.get("blockers")), ev_legal)

                # Sick leave fraction engine on synthetic P2-like facts
                sick_facts = [
                    {
                        "line_kind": "leave_interval",
                        "classification": "sick_leave",
                        "fact_date": as_of.isoformat(),
                        "fact_end_date": (as_of + timedelta(days=2)).isoformat(),
                        "chargeable_days": 3,
                        "line_id": str(uuid.uuid4()),
                        "leave_id": str(uuid.uuid4()),
                        "employee_key": EMP_SICK,
                    }
                ]
                sick_rule = p4a.resolve_rule_version(
                    cur,
                    company_code=COMPANY,
                    rule_family="sick_leave_fractions",
                    as_of=as_of,
                    require_legal_claim=False,
                    allow_architecture_fixture=True,
                )
                sick_out = p4a.evaluate_sick_leave_from_p2_facts(
                    input_lines=sick_facts,
                    rule_version=sick_rule or {},
                    daily_rate=p4a.money(10),
                )
                check("sick engine lines", len(sick_out.get("lines") or []) == 1, sick_out)
                check(
                    "sick provenance rule",
                    str(((sick_out.get("lines") or [{}])[0].get("provenance") or {}).get("rule_version_id"))
                    == str((sick_rule or {}).get("rule_version_id")),
                )

                # EOS settlement snapshot
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, employment_status)
                    VALUES (%s,%s,%s,%s,%s,%s,'active')
                    ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code
                    """,
                    (COMPANY, EMP_EOS, f"9655620{TAG_DIGITS}", f"P4A EOS {TAG}", as_of_early, as_of_early),
                )
                eos = p4a.create_eos_settlement_snapshot(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_EOS,
                    service_start=as_of_early,
                    service_end=as_of,
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_eos",
                    termination_reason="resignation",
                    compensation_basis={"monthly_basic": 500},
                    allow_architecture_fixture=True,
                )
                check("eos settlement created", eos.get("ok") is True, eos)
                settle = eos.get("settlement") or {}
                check("eos output class C", (settle.get("provenance") or {}).get("not_monthly_g2n") is True or settle.get("approval_status") == "architecture_qualified")
                check("eos not auto pay", settle.get("auto_payable") is False)
                check("eos preview authority", settle.get("money_authority") == "preview_non_authoritative")
                check("eos never legal_claim", settle.get("legal_claim") is False)
                check("eos has rule provenance", bool(settle.get("rule_version_id")))
                check("eos provisional architecture amount", settle.get("provisional_amount") is not None)

                eos_legal = p4a.create_eos_settlement_snapshot(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_EOS,
                    service_start=as_of_early,
                    service_end=as_of + timedelta(days=1),
                    actor_phone=ACTOR,
                    reason=f"pap4a_{TAG}_eos_legal",
                    compensation_basis={"monthly_basic": 500},
                    allow_architecture_fixture=False,
                )
                check("eos legal path blocked/awaiting", bool((eos_legal.get("settlement") or {}).get("blockers")), eos_legal)

                ws = p4a.workspace_bootstrap(cur, company_code=COMPANY)
                check("workspace ok", ws.get("ok") is True)
                check("workspace p4b inputs", len((ws.get("p4b_required_inputs") or {}).get("required") or []) >= 6)

            conn.commit()
    except Exception as exc:
        check("runtime", False, f"{type(exc).__name__}: {exc}")
        try:
            cleanup(app, package_ids, keys)
        except Exception:
            pass
        _write()
        return 1

    cleanup(app, package_ids, keys)
    _write()
    print(f"PASS={PASS} FAIL={FAIL} EVID={EVID}")
    return 0 if FAIL == 0 else 1


def _write() -> None:
    summary = {
        "stamp": STAMP,
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "honesty": {
            "money_authority": "preview_non_authoritative",
            "legal_claim": False,
            "rates_invented": False,
            "mode_a_seal": False,
            "payment_processing": "disabled",
        },
    }
    (EVID / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (EVID / "RESULTS.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
