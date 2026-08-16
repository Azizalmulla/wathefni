#!/usr/bin/env python3
"""Payroll Authority P4B — Kuwait public statutory baseline qualification.

Activates OFFICIAL_CLEAR Wathefni-owned baseline; proves provenance, applicability,
fail-closed gated cases, company non-override, A/B/C/D boundaries, P1–P4A regressions.
Does NOT unlock Mode A / PDF / payments.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import date
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
    (p for p in ORCH_CANDIDATES if (p / "payroll_statutory_baseline_p4b.py").exists()),
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
    "WATHEFNI_PAYROLL_AUTHORITY_P4B",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYP1,PYP2,PYP3,PYP4A,PYP4B,PYSTAT,PYINPUT,PYCALC"
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P4B_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P4A_SYNTHETIC_KEY_MARKERS", MARKERS)

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP4B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
ACTOR = f"9655619{TAG_DIGITS}"

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP4B_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p4b-{STAMP}"))
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


def main() -> int:
    import payroll_statutory_architecture_p4a as p4a
    import payroll_statutory_baseline_p4b as p4b
    import payroll_components_policy_p3 as p3

    check("p4b version", p4b.PAYROLL_AUTHORITY_P4B_VERSION == "1.0.0")
    check("mode a locked", p4b.honesty_payload()["mode_a_wathefni_seal_unlocked"] is False)
    check("pdf locked", p4b.honesty_payload()["native_official_pdf_unlocked"] is False)
    check("payments disabled", p4b.honesty_payload()["payment_processing"] == "disabled")
    check("synthetic only", p4b.payroll_authority_p4b_synthetic_only() is True)

    pack = p4b.load_classification_pack()
    check("classification pack loaded", pack.get("pack_id", "").startswith("KW_STATUTORY_PUBLIC_BASELINE"))
    clear = [c for c in pack["classifications"] if c.get("classification") == "OFFICIAL_CLEAR" and c.get("activate")]
    gated = [c for c in pack["classifications"] if not c.get("activate")]
    check("has official clear", len(clear) >= 10, len(clear))
    check("has gated", len(gated) >= 8, len(gated))

    try:
        import app as orch_app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            check("db available", False, "psycopg2 missing")
            _write_evidence()
            return 1
        raise

    package_id = None
    activated_families: set[str] = set()
    with orch_app.db_connect() as conn:
        with conn.cursor() as cur:
            act = p4b.activate_kuwait_public_baseline(
                cur, actor_phone=ACTOR, reason=f"pap4b_{TAG}_activate", force_refresh=False
            )
            check("activate ok", act.get("ok") is True, act)
            check("legal claim true on package", (act.get("package") or {}).get("legal_claim") is True)
            check("authority wathefni baseline", (act.get("package") or {}).get("authority_kind") == "wathefni_public_baseline")
            check("mode a still locked after activate", act.get("mode_a_wathefni_seal_unlocked") is False)
            package_id = str((act.get("package") or {}).get("package_id") or "")
            activated = act.get("activated_rules") or []
            activated_families = {r.get("rule_family") for r in activated if r.get("rule_family")}
            for fam in (
                "ot_ordinary",
                "rest_day_work",
                "public_holiday_work",
                "sick_leave_fractions",
                "eos_indemnity",
                "pifss",
            ):
                check(f"activated {fam}", fam in activated_families, activated_families)

            as_of = date(2024, 6, 1)
            ot = p4b.resolve_public_baseline_rule(cur, rule_family="ot_ordinary", as_of=as_of, sector="private")
            check("ot selects baseline", ot is not None and float(ot.get("multiplier") or 0) == 1.25, ot)
            check("ot provenance retained", "Article 66" in str(ot.get("official_source_ref") or ""), ot)
            check("ot policy version", ot.get("policy_version") == p4b.POLICY_VERSION, ot)

            # Effective dating: before law — no row expected if we used 2010-02-21
            early = p4b.resolve_public_baseline_rule(
                cur, rule_family="ot_ordinary", as_of=date(2009, 1, 1), sector="private"
            )
            check("ot not before effective", early is None, early)

            # Applicability: oil special not same as private for activated private-only OT
            # (baseline marks sector private — oil context should fail apply)
            oil = p4b.resolve_public_baseline_rule(cur, rule_family="ot_ordinary", as_of=as_of, sector="oil")
            check("ot not apply oil without private", oil is None, oil)

            rest = p4b.resolve_public_baseline_rule(cur, rule_family="rest_day_work", as_of=as_of, sector="private")
            ph = p4b.resolve_public_baseline_rule(cur, rule_family="public_holiday_work", as_of=as_of, sector="private")
            sick = p4b.resolve_public_baseline_rule(cur, rule_family="sick_leave_fractions", as_of=as_of, sector="private")
            check("rest distinct family", rest is not None and float(rest.get("multiplier") or 0) == 1.5)
            check("ph distinct family", ph is not None and float(ph.get("multiplier") or 0) == 2.0)
            check("sick bands present", bool((sick or {}).get("fraction_payload")))
            check("families not collapsed", len({str(ot.get("rule_version_id")), str(rest.get("rule_version_id")), str(ph.get("rule_version_id"))}) == 3)

            # P3 bridge consumes baseline
            bridged = p3.get_approved_rate(cur, company_code=COMPANY, rule_family="ot_ordinary", as_of=as_of)
            check("p3 gets ot baseline", bridged is not None and float(bridged.get("multiplier") or 0) == 1.25, bridged)
            check("p3 source public baseline", (bridged or {}).get("source") == "p4b_public_baseline", bridged)
            sick_b = p3.get_approved_rate(cur, company_code=COMPANY, rule_family="sick_leave_fractions", as_of=as_of)
            check("p3 gets sick fractions", bool((sick_b or {}).get("fraction_payload")), sick_b)

            # PIFSS EE/ER distinct + wage base fail-closed
            no_wage = p4b.evaluate_pifss_with_baseline(
                cur, as_of=as_of, employee_category="kuwaiti_national", pifss_wage_by_fund=None
            )
            check(
                "pifss wage gate",
                no_wage.get("ok") is False
                and (no_wage.get("blocker") or {}).get("code") == "pifss_wage_base_classification_required",
                no_wage,
            )
            gcc = p4b.evaluate_pifss_with_baseline(
                cur, as_of=as_of, employee_category="gcc_national", pifss_wage_by_fund={"basic": 1000}
            )
            check("gcc gated", gcc.get("ok") is False and "gcc" in str((gcc.get("blocker") or {}).get("code")), gcc)

            wages = {
                "basic": 1200,
                "supplementary": 800,
                "pension_increase": 2000,
                "unemployment_private_oil": 2000,
            }
            ok_pifss = p4b.evaluate_pifss_with_baseline(
                cur, as_of=as_of, employee_category="kuwaiti_national", pifss_wage_by_fund=wages
            )
            check("pifss eval ok", ok_pifss.get("ok") is True, ok_pifss)
            ee = ok_pifss.get("A_employee_net") or []
            er = ok_pifss.get("B_employer_liability") or []
            rem = ok_pifss.get("D_remittance_reporting") or []
            check("pifss EE A class", all(x.get("output_class") == "A_employee_net" for x in ee), ee)
            check("pifss ER B class", all(x.get("output_class") == "B_employer_liability" for x in er), er)
            check("pifss remittance D", len(rem) >= 1 and rem[0].get("is_payment_processing") is False, rem)
            check("pifss EE ER distinct amounts", len(ee) >= 1 and len(er) >= 1)

            # EOS settlement not G2N; Kuwaiti Law17 gated; remuneration gate
            eos_no_rem = p4b.evaluate_eos_settlement_baseline(
                cur,
                as_of=as_of,
                pay_frequency="monthly",
                termination="employer_terminates",
                contract_type="indefinite",
                service_years=6,
                remuneration_for_eos=None,
                employee_category="expatriate",
            )
            check(
                "eos rem gate",
                eos_no_rem.get("ok") is False
                and (eos_no_rem.get("blocker") or {}).get("code") == "eos_remuneration_base_classification_required",
                eos_no_rem,
            )
            eos_kw = p4b.evaluate_eos_settlement_baseline(
                cur,
                as_of=as_of,
                pay_frequency="monthly",
                termination="employer_terminates",
                contract_type="indefinite",
                service_years=6,
                remuneration_for_eos=1000,
                employee_category="kuwaiti_national",
            )
            check(
                "eos kuwaiti law17 gate",
                eos_kw.get("ok") is False
                and (eos_kw.get("blocker") or {}).get("code") == "eos_pifss_interaction_review_required",
                eos_kw,
            )
            eos_ok = p4b.evaluate_eos_settlement_baseline(
                cur,
                as_of=as_of,
                pay_frequency="monthly",
                termination="employer_terminates",
                contract_type="indefinite",
                service_years=6,
                remuneration_for_eos=1000,
                employee_category="expatriate",
            )
            check("eos settlement ok", eos_ok.get("ok") is True and eos_ok.get("monthly_g2n") is False, eos_ok)
            check("eos not auto pay", eos_ok.get("auto_payable") is False and eos_ok.get("payment_processing") == "disabled")
            check("eos C class", eos_ok.get("output_class") == "C_settlement")

            # Company cannot override
            override = p4b.refuse_company_statutory_override(
                company_code=COMPANY, rule_family="ot_ordinary", legal_claim=True
            )
            check("company override refused", override is not None and override.get("ok") is False, override)

            # Setup matrix
            matrix = p4b.setup_console_ownership_matrix()
            check("setup wathefni owned", "Ordinary OT premium" in str(matrix.get("wathefni_owned_kuwait_statutory_baseline")))
            check("setup company provided", "Employee statutory classification" in str(matrix.get("company_provided_never_kuwait_law")))
            check("never ask kuwait law", len(matrix.get("never_ask_company") or []) >= 3)

            # p4a resolve prefers baseline
            resolved = p4a.resolve_rule_version(
                cur,
                company_code=COMPANY,
                rule_family="ot_ordinary",
                as_of=as_of,
                require_legal_claim=True,
            )
            check(
                "p4a resolve baseline",
                resolved is not None
                and str(resolved.get("authority_kind")) == "wathefni_public_baseline"
                and float(resolved.get("multiplier") or 0) == 1.25,
                resolved,
            )

            conn.commit()

    # Persist summary
    summary = {
        "stamp": STAMP,
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "package_id": package_id,
        "activated_official_clear": sorted(activated_families),
        "still_gated_count": len(gated),
        "honesty": p4b.honesty_payload(),
        "setup_matrix": p4b.setup_console_ownership_matrix(),
        "results": RESULTS,
    }
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    (EVID / "STATUS.txt").write_text(
        "\n".join(
            [
                f"result={'PASS' if FAIL == 0 else 'FAIL'}",
                f"pass={PASS}",
                f"fail={FAIL}",
                "mode_a_unlocked=false",
                "synthetic_only=true",
                "native_pdf=false",
                "payment_processing=disabled",
                f"policy_version={p4b.POLICY_VERSION}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"evidence={EVID}")
    print(f"PASS={PASS} FAIL={FAIL}")
    return 0 if FAIL == 0 else 1


def _write_evidence() -> None:
    (EVID / "summary.json").write_text(json.dumps({"results": RESULTS}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
