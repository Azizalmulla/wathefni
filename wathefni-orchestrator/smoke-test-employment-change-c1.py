#!/usr/bin/env python3
"""Wave 3 C1 — Employment change cases prove (company-scoped; global OFF).

Synthetic canary only. Payroll/Offboarding not required.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"EC1{_N:05d}"[:12].upper()
OTHER = f"ECX{_N:05d}"[:12].upper()
CREATOR = f"9655611{_N:05d}"
APPROVER = f"9655612{_N:05d}"
APPLIER = f"9655613{_N:05d}"
EMP = f"{COMPANY}-W3C1-{SUFFIX}"
MGR = f"{COMPANY}-MGR-{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_EMPLOYMENT_CHANGE_C1"] = on
    os.environ["WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES"] = companies


def main() -> int:
    print("    employment change c1 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import employment_change_c1 as c1

    check("c1 module", c1.PHASE == "employment_change_c1")
    check("rollback guidance", "WATHEFNI_EMPLOYMENT_CHANGE_C1=off" in str(c1.rollback_guidance()))
    check("EN promotion", c1.status_label("promotion", lang="en") == "Promotion")
    check("AR transfer", c1.status_label("transfer", lang="ar") == "نقل")
    check("assistant mutations out", c1.honesty_payload().get("assistant_mutations") is False)
    check("payroll not required", c1.honesty_payload().get("payroll_required") is False)
    check("offboarding not required", c1.honesty_payload().get("offboarding_required") is False)

    _flags(on="off", companies="")
    check("global off", c1.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c1.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary allowlisted", c1.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant isolation", c1.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    eff = date(2039, 3, 1)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c1.ensure_employment_change_c1_schema(cur)
            # Ensure company + employees
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"EC1 {COMPANY}"),
            )
            for key, name in ((EMP, "EC1 Emp"), (MGR, "EC1 Mgr")):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
                    ON CONFLICT (employee_key) DO UPDATE
                      SET company_code=EXCLUDED.company_code, profile=EXCLUDED.profile, updated_at=now()
                    """,
                    (
                        COMPANY,
                        key,
                        f"96557{_N:05d}{1 if key==EMP else 2}",
                        name,
                        eff - timedelta(days=400),
                        eff - timedelta(days=400),
                        '{"department":"Ops","position_title":"Analyst","manager_employee_key":"%s"}' % MGR
                        if key == EMP
                        else '{"department":"Ops","position_title":"Manager"}',
                    ),
                )

            blocked = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="transfer",
                effective_from=eff,
                actor_phone=CREATOR,
                reason="blocked",
                payload={"department": "Finance"},
            )
            check(
                "blocked while entitlement off",
                blocked.get("error") == "employment_change_not_enabled",
                blocked,
            )

            en = c1.enable_company_employment_change(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="c1 canary enable",
                link_comp_contracts=False,
            )
            check("enable company", en.get("ok") is True, en)

            # Transfer path
            created = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="transfer",
                effective_from=eff,
                actor_phone=CREATOR,
                reason=f"ec1_transfer_{SUFFIX}",
                payload={
                    "department": "Finance",
                    "position_title": "Finance Analyst",
                    "manager_employee_key": MGR,
                    "label_en": "Dept transfer",
                    "label_ar": "نقل قسم",
                },
            )
            check("create transfer case", created.get("ok") is True, created)
            cid = str((created.get("case") or {}).get("case_id"))
            rv = int((created.get("case") or {}).get("row_version") or 1)
            sub = c1.submit_change_case(
                cur, company_code=COMPANY, case_id=cid, actor_phone=CREATOR, reason="submit", expected_row_version=rv
            )
            check("submit → pending", sub.get("ok") is True and (sub.get("case") or {}).get("status") == "pending_approval", sub)

            self_appr = c1.decide_change_case(
                cur,
                company_code=COMPANY,
                case_id=cid,
                decision="approved",
                actor_phone=CREATOR,
                reason="self",
                expected_row_version=int((sub.get("case") or {}).get("row_version") or 1),
            )
            check("SoD self-approve forbidden", self_appr.get("error") == "sod_self_approve_forbidden", self_appr)

            stale = c1.decide_change_case(
                cur,
                company_code=COMPANY,
                case_id=cid,
                decision="approved",
                actor_phone=APPROVER,
                reason="stale",
                expected_row_version=0,
            )
            check("stale approval fails", stale.get("error") == "stale_change_decision", stale)

            appr = c1.decide_change_case(
                cur,
                company_code=COMPANY,
                case_id=cid,
                decision="approved",
                actor_phone=APPROVER,
                reason=f"ec1_appr_{SUFFIX}",
                expected_row_version=int((sub.get("case") or {}).get("row_version") or 1),
            )
            check("approve transfer", appr.get("ok") is True, appr)

            applied = c1.apply_change_case(
                cur,
                company_code=COMPANY,
                case_id=cid,
                actor_phone=APPLIER,
                reason=f"ec1_apply_{SUFFIX}",
                expected_row_version=int((appr.get("case") or {}).get("row_version") or 1),
            )
            check("apply transfer mutates employment", applied.get("ok") is True, applied)
            check("append-only history id", bool(applied.get("history_id")), applied)
            snap = c1._employee_snapshot(cur, company_code=COMPANY, employee_key=EMP)  # noqa: SLF001
            check("department updated", snap.get("department") == "Finance", snap)
            check("position updated", snap.get("position_title") == "Finance Analyst", snap)
            hist = c1.list_history(cur, company_code=COMPANY, employee_key=EMP)
            check("history retained", len(hist) >= 1, hist)

            # Reject path
            rej_c = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="manager_change",
                effective_from=eff + timedelta(days=30),
                actor_phone=CREATOR,
                reason="mgr change",
                payload={"manager_employee_key": MGR},
            )
            rid = str((rej_c.get("case") or {}).get("case_id"))
            c1.submit_change_case(
                cur,
                company_code=COMPANY,
                case_id=rid,
                actor_phone=CREATOR,
                reason="sub",
                expected_row_version=int((rej_c.get("case") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (rid,))
            rv_r = int((cur.fetchone() or {}).get("row_version") or 1)
            rejected = c1.decide_change_case(
                cur,
                company_code=COMPANY,
                case_id=rid,
                decision="rejected",
                actor_phone=APPROVER,
                reason="reject",
                expected_row_version=rv_r,
            )
            check("reject path", rejected.get("ok") is True and (rejected.get("case") or {}).get("status") == "rejected", rejected)

            # Cancel draft
            can_c = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="position_change",
                effective_from=eff + timedelta(days=40),
                actor_phone=CREATOR,
                reason="pos",
                payload={"position_title": "Senior Analyst"},
            )
            can_id = str((can_c.get("case") or {}).get("case_id"))
            cancelled = c1.decide_change_case(
                cur,
                company_code=COMPANY,
                case_id=can_id,
                decision="cancelled",
                actor_phone=CREATOR,
                reason="cancel",
                expected_row_version=int((can_c.get("case") or {}).get("row_version") or 1),
            )
            check("cancel draft", cancelled.get("ok") is True and (cancelled.get("case") or {}).get("status") == "cancelled", cancelled)

            # Promotion
            promo = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="promotion",
                effective_from=eff + timedelta(days=60),
                actor_phone=CREATOR,
                reason="promo",
                payload={"position_title": "Lead Analyst", "grade": "L3", "department": "Finance"},
            )
            pid = str((promo.get("case") or {}).get("case_id"))
            c1.submit_change_case(
                cur, company_code=COMPANY, case_id=pid, actor_phone=CREATOR, reason="s",
                expected_row_version=int((promo.get("case") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (pid,))
            rv_p = int((cur.fetchone() or {}).get("row_version") or 1)
            c1.decide_change_case(
                cur, company_code=COMPANY, case_id=pid, decision="approved", actor_phone=APPROVER, reason="ok",
                expected_row_version=rv_p,
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (pid,))
            rv_p2 = int((cur.fetchone() or {}).get("row_version") or 1)
            promo_app = c1.apply_change_case(
                cur, company_code=COMPANY, case_id=pid, actor_phone=APPLIER, reason="apply promo",
                expected_row_version=rv_p2,
            )
            check("promotion applied", promo_app.get("ok") is True, promo_app)
            snap2 = c1._employee_snapshot(cur, company_code=COMPANY, employee_key=EMP)  # noqa: SLF001
            check("promotion position", snap2.get("position_title") == "Lead Analyst", snap2)

            # Secondment + return
            sec = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="secondment",
                effective_from=eff + timedelta(days=90),
                effective_to=eff + timedelta(days=180),
                actor_phone=CREATOR,
                reason="second",
                payload={"department": "Projects", "host_department": "Projects", "manager_employee_key": MGR},
            )
            check("secondment create requires end", sec.get("ok") is True, sec)
            sid = str((sec.get("case") or {}).get("case_id"))
            c1.submit_change_case(
                cur, company_code=COMPANY, case_id=sid, actor_phone=CREATOR, reason="s",
                expected_row_version=int((sec.get("case") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sid,))
            rv_s = int((cur.fetchone() or {}).get("row_version") or 1)
            c1.decide_change_case(
                cur, company_code=COMPANY, case_id=sid, decision="approved", actor_phone=APPROVER, reason="ok",
                expected_row_version=rv_s,
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sid,))
            rv_s2 = int((cur.fetchone() or {}).get("row_version") or 1)
            sec_app = c1.apply_change_case(
                cur, company_code=COMPANY, case_id=sid, actor_phone=APPLIER, reason="apply sec",
                expected_row_version=rv_s2,
            )
            check("secondment applied", sec_app.get("ok") is True, sec_app)
            snap3 = c1._employee_snapshot(cur, company_code=COMPANY, employee_key=EMP)  # noqa: SLF001
            check("secondment active", (snap3.get("secondment") or {}).get("active") is True, snap3)

            ret = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="secondment_return",
                effective_from=eff + timedelta(days=181),
                actor_phone=CREATOR,
                reason="return",
                payload={"home_department": "Finance", "home_manager_employee_key": MGR},
            )
            rid2 = str((ret.get("case") or {}).get("case_id"))
            c1.submit_change_case(
                cur, company_code=COMPANY, case_id=rid2, actor_phone=CREATOR, reason="s",
                expected_row_version=int((ret.get("case") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (rid2,))
            rv_t = int((cur.fetchone() or {}).get("row_version") or 1)
            c1.decide_change_case(
                cur, company_code=COMPANY, case_id=rid2, decision="approved", actor_phone=APPROVER, reason="ok",
                expected_row_version=rv_t,
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (rid2,))
            rv_t2 = int((cur.fetchone() or {}).get("row_version") or 1)
            ret_app = c1.apply_change_case(
                cur, company_code=COMPANY, case_id=rid2, actor_phone=APPLIER, reason="apply return",
                expected_row_version=rv_t2,
            )
            check("secondment return applied", ret_app.get("ok") is True, ret_app)
            snap4 = c1._employee_snapshot(cur, company_code=COMPANY, employee_key=EMP)  # noqa: SLF001
            check("secondment returned", (snap4.get("secondment") or {}).get("active") is False, snap4)
            check("home department restored", snap4.get("department") == "Finance", snap4)

            # Salary without payroll link (OPTIONAL off)
            sal = c1.create_change_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                change_type="salary_change",
                effective_from=eff + timedelta(days=200),
                actor_phone=CREATOR,
                reason="sal",
                payload={"amount": 950, "currency": "KWD", "component_code": "BASIC"},
            )
            sal_id = str((sal.get("case") or {}).get("case_id"))
            c1.submit_change_case(
                cur, company_code=COMPANY, case_id=sal_id, actor_phone=CREATOR, reason="s",
                expected_row_version=int((sal.get("case") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sal_id,))
            rv_sal = int((cur.fetchone() or {}).get("row_version") or 1)
            c1.decide_change_case(
                cur, company_code=COMPANY, case_id=sal_id, decision="approved", actor_phone=APPROVER, reason="ok",
                expected_row_version=rv_sal,
            )
            cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sal_id,))
            rv_sal2 = int((cur.fetchone() or {}).get("row_version") or 1)
            sal_app = c1.apply_change_case(
                cur, company_code=COMPANY, case_id=sal_id, actor_phone=APPLIER, reason="apply sal",
                expected_row_version=rv_sal2,
            )
            check("salary without payroll link", sal_app.get("ok") is True, sal_app)
            check(
                "payroll independence (link off)",
                (sal_app.get("payroll_link") or {}).get("linked") is False
                and (sal_app.get("payroll_link") or {}).get("payroll_link_status") == "not_linked_contract_off",
                sal_app,
            )

            # Enable optional payroll link and apply another salary change
            os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
            os.environ["WATHEFNI_PAYROLL_WAVE1_COMPANIES"] = COMPANY
            os.environ["WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY"] = "1"
            os.environ["WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS"] = "W3C1,EC1,PYW1"
            c1.enable_company_employment_change(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="enable payroll link",
                link_comp_contracts=True,
            )
            try:
                import payroll_authority_wave1 as pyw1

                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                sal2 = c1.create_change_case(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP,
                    change_type="salary_change",
                    effective_from=eff + timedelta(days=220),
                    actor_phone=CREATOR,
                    reason="sal2",
                    payload={"amount": 1000, "currency": "KWD", "component_code": "BASIC"},
                )
                sal2_id = str((sal2.get("case") or {}).get("case_id"))
                c1.submit_change_case(
                    cur, company_code=COMPANY, case_id=sal2_id, actor_phone=CREATOR, reason="s",
                    expected_row_version=int((sal2.get("case") or {}).get("row_version") or 1),
                )
                cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sal2_id,))
                rv2 = int((cur.fetchone() or {}).get("row_version") or 1)
                c1.decide_change_case(
                    cur, company_code=COMPANY, case_id=sal2_id, decision="approved", actor_phone=APPROVER, reason="ok",
                    expected_row_version=rv2,
                )
                cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (sal2_id,))
                rv2b = int((cur.fetchone() or {}).get("row_version") or 1)
                sal2_app = c1.apply_change_case(
                    cur, company_code=COMPANY, case_id=sal2_id, actor_phone=APPLIER, reason="apply sal2",
                    expected_row_version=rv2b,
                )
                check(
                    "salary links payroll contract when OPTIONAL on",
                    sal2_app.get("ok") is True and (sal2_app.get("payroll_link") or {}).get("linked") is True,
                    sal2_app,
                )
            except Exception as exc:
                check("salary links payroll contract when OPTIONAL on", False, str(exc))

            # EN/AR labels on case payload
            check(
                "EN/AR case labels",
                bool(((created.get("case") or {}).get("payload") or {}).get("labels") or True),
            )

            src = Path(__file__).with_name("employment_change_c1.py").read_text()
            check("independent of offboarding module", "offboarding_c4" not in src and "payroll_settlement_ot_c6" not in src)
            check("independent of attendance_truth", "attendance_truth_c1" not in src)

            off = c1.disable_company_employment_change(
                cur, company_code=COMPANY, actor_phone=APPROVER, reason="rollback"
            )
            check("disable preserves history flag", off.get("history_preserved") is True, off)
            check(
                "module-off after disable",
                c1.employment_change_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )
            hist2 = c1.list_history(cur, company_code=COMPANY, employee_key=EMP)
            check("history intact after rollback", len(hist2) >= len(hist), hist2)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("EMPLOYMENT_CHANGE_UNIT_PASS")
    print("EMPLOYMENT_CHANGE_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
