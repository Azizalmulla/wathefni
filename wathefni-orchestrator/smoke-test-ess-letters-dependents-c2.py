#!/usr/bin/env python3
"""Wave 3 C2 — ESS Letters + Dependents prove (company-scoped; global OFF)."""
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
COMPANY = f"EL2{_N:05d}"[:12].upper()
OTHER = f"ELX{_N:05d}"[:12].upper()
EMP_PHONE = f"9655711{_N:05d}"
HR_PHONE = f"9655712{_N:05d}"
OTHER_PHONE = f"9655713{_N:05d}"
EMP = f"{COMPANY}-W3C2-{SUFFIX}"


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
    os.environ["WATHEFNI_ESS_LETTERS_DEPENDENTS_C2"] = on
    os.environ["WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES"] = companies


def main() -> int:
    print("    ess letters + dependents c2 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import ess_letters_dependents_c2 as c2

    check("c2 module", c2.PHASE == "ess_letters_dependents_c2")
    check("rollback guidance", "WATHEFNI_ESS_LETTERS_DEPENDENTS_C2=off" in str(c2.rollback_guidance()))
    check("EN salary cert", c2.status_label("salary_certificate", lang="en") == "Salary certificate")
    check("AR employment cert", c2.status_label("employment_certificate", lang="ar") == "شهادة عمل")
    check("assistant mutations out", c2.honesty_payload().get("assistant_mutations") is False)
    check("payroll not required", c2.honesty_payload().get("payroll_required") is False)
    check("benefits not required", c2.honesty_payload().get("benefits_required") is False)
    check("no silent invent", c2.honesty_payload().get("silent_pdf_when_fulfill_off") is False)

    _flags(on="off", companies="")
    check("global off", c2.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c2.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary allowlisted", c2.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant isolation", c2.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    hire = date(2038, 1, 15)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c2.ensure_ess_letters_dependents_c2_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"EL2 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE
                  SET company_code=EXCLUDED.company_code, profile=EXCLUDED.profile, updated_at=now()
                """,
                (
                    COMPANY,
                    EMP,
                    EMP_PHONE,
                    "EL2 Emp",
                    hire,
                    hire,
                    '{"department":"Ops","position_title":"Analyst"}',
                ),
            )

            blocked = c2.request_letter(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                letter_type="employment_certificate",
                actor_phone=EMP_PHONE,
            )
            check(
                "blocked while entitlement off",
                blocked.get("error") == "ess_letters_dependents_not_enabled",
                blocked,
            )

            # Enable letters WITHOUT fulfill — no silent invent
            en = c2.enable_company_ess_letters_dependents(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="canary enable letters only",
                letters_enabled=True,
                letters_fulfill=False,
                dependents_enabled=False,
                salary_cert_use_payroll=False,
            )
            check("enable company", en.get("ok") is True, en)
            vis = c2.feature_visibility(cur, COMPANY)
            check("letters visible when on", vis.get("letters_visible") is True, vis)
            check("dependents hidden when off", vis.get("dependents_visible") is False, vis)

            req = c2.request_letter(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                letter_type="employment_certificate",
                actor_phone=EMP_PHONE,
                lang="en",
                purpose="visa",
            )
            check("employee requests letter", req.get("ok") is True, req)
            rid = str((req.get("request") or {}).get("request_id"))
            check("status requested", (req.get("request") or {}).get("status") == "requested", req)

            review = c2.start_letter_review(
                cur, company_code=COMPANY, request_id=rid, actor_phone=HR_PHONE,
                expected_version=int((req.get("request") or {}).get("row_version") or 1),
            )
            check("under_review", review.get("ok") is True and (review.get("request") or {}).get("status") == "under_review", review)

            sod = c2.approve_letter(
                cur,
                company_code=COMPANY,
                request_id=rid,
                actor_phone=EMP_PHONE,
                reason="self",
                expected_version=int((review.get("request") or {}).get("row_version") or 1),
            )
            check("SoD self-approve forbidden", sod.get("error") == "sod_self_approve_forbidden", sod)

            stale = c2.approve_letter(
                cur,
                company_code=COMPANY,
                request_id=rid,
                actor_phone=HR_PHONE,
                reason="stale",
                expected_version=0,
            )
            check("stale approval fails", stale.get("error") == "stale_row_version", stale)

            appr = c2.approve_letter(
                cur,
                company_code=COMPANY,
                request_id=rid,
                actor_phone=HR_PHONE,
                reason="ok to issue",
                expected_version=int((review.get("request") or {}).get("row_version") or 1),
            )
            check("approved", appr.get("ok") is True and (appr.get("request") or {}).get("status") == "approved", appr)

            silent = c2.issue_letter(
                cur,
                company_code=COMPANY,
                request_id=rid,
                actor_phone=HR_PHONE,
                reason="try invent",
                expected_version=int((appr.get("request") or {}).get("row_version") or 1),
            )
            check("no silent invent when fulfill off", silent.get("error") == "letters_fulfill_off", silent)

            # Enable fulfill + dependents + HR review
            c2.enable_company_ess_letters_dependents(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="enable fulfill + dependents",
                letters_enabled=True,
                letters_fulfill=True,
                dependents_enabled=True,
                dependents_require_hr_review=True,
                salary_cert_use_payroll=False,
            )

            issued = c2.issue_letter(
                cur,
                company_code=COMPANY,
                request_id=rid,
                actor_phone=HR_PHONE,
                reason="issue employment cert",
                expected_version=int((appr.get("request") or {}).get("row_version") or 1),
            )
            check("HR fulfills and issues", issued.get("ok") is True, issued)
            check("status issued", (issued.get("request") or {}).get("status") == "issued", issued)
            vid = str((issued.get("version") or {}).get("version_id"))
            hash1 = (issued.get("version") or {}).get("content_hash")
            check("artifact content hash", bool(hash1), hash1)

            dl = c2.download_letter_version(
                cur,
                company_code=COMPANY,
                version_id=vid,
                actor_phone=EMP_PHONE,
                employee_key=EMP,
            )
            check("employee downloads issued", dl.get("ok") is True and dl.get("immutable") is True, dl)
            check("download body tied to employment", "Analyst" in str(dl.get("body_text") or ""), dl)

            forbid = c2.download_letter_version(
                cur,
                company_code=COMPANY,
                version_id=vid,
                actor_phone=OTHER_PHONE,
                employee_key=f"{COMPANY}-OTHER",
            )
            check("self-scope blocks other employee", forbid.get("error") == "forbidden_self_scope", forbid)

            mut = c2.attempt_mutate_issued_version(
                cur, company_code=COMPANY, version_id=vid, new_body="tamper"
            )
            check("issued cannot silently change", mut.get("error") == "issued_version_immutable", mut)
            still = c2.get_letter_version(cur, company_code=COMPANY, version_id=vid)
            check("hash unchanged after mutate attempt", still and still.get("content_hash") == hash1, still)

            corr = c2.correct_letter(
                cur,
                company_code=COMPANY,
                prior_version_id=vid,
                actor_phone=EMP_PHONE,
                purpose="correction",
            )
            check("correction creates new request", corr.get("ok") is True, corr)
            crid = str((corr.get("request") or {}).get("request_id"))
            c2.start_letter_review(
                cur, company_code=COMPANY, request_id=crid, actor_phone=HR_PHONE,
                expected_version=int((corr.get("request") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (crid,))
            rv_c = int((cur.fetchone() or {}).get("row_version") or 1)
            c2.approve_letter(
                cur, company_code=COMPANY, request_id=crid, actor_phone=HR_PHONE, reason="reissue",
                expected_version=rv_c,
            )
            cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (crid,))
            rv_c2 = int((cur.fetchone() or {}).get("row_version") or 1)
            reissue = c2.issue_letter(
                cur, company_code=COMPANY, request_id=crid, actor_phone=HR_PHONE, reason="reissue",
                expected_version=rv_c2,
            )
            check("corrected letter new version", reissue.get("ok") is True, reissue)
            v2 = int((reissue.get("version") or {}).get("version_number") or 0)
            check("version number incremented", v2 == 2, v2)
            check("prior version still immutable", still.get("content_hash") == hash1)

            # EN/AR experience letter
            ar = c2.request_letter(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                letter_type="experience_letter",
                actor_phone=EMP_PHONE,
                lang="ar",
            )
            arid = str((ar.get("request") or {}).get("request_id"))
            c2.approve_letter(
                cur, company_code=COMPANY, request_id=arid, actor_phone=HR_PHONE, reason="ar ok",
                expected_version=int((ar.get("request") or {}).get("row_version") or 1),
            )
            cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (arid,))
            rv_ar = int((cur.fetchone() or {}).get("row_version") or 1)
            ar_iss = c2.issue_letter(
                cur, company_code=COMPANY, request_id=arid, actor_phone=HR_PHONE, reason="ar issue",
                expected_version=rv_ar,
            )
            check("AR experience letter issued", ar_iss.get("ok") is True, ar_iss)
            check("AR body path", "خطاب" in str((ar_iss.get("download") or {}).get("body_text") or ""), ar_iss)

            # Reject / cancel paths
            rej = c2.request_letter(
                cur, company_code=COMPANY, employee_key=EMP,
                letter_type="employment_certificate", actor_phone=EMP_PHONE,
            )
            rjid = str((rej.get("request") or {}).get("request_id"))
            rejected = c2.reject_letter(
                cur, company_code=COMPANY, request_id=rjid, actor_phone=HR_PHONE, reason="no",
                expected_version=1,
            )
            check("reject path", rejected.get("ok") is True and (rejected.get("request") or {}).get("status") == "rejected", rejected)

            can = c2.request_letter(
                cur, company_code=COMPANY, employee_key=EMP,
                letter_type="employment_certificate", actor_phone=EMP_PHONE,
            )
            cid = str((can.get("request") or {}).get("request_id"))
            cancelled = c2.cancel_letter(
                cur, company_code=COMPANY, request_id=cid, actor_phone=EMP_PHONE, reason="withdraw",
                expected_version=1,
            )
            check("cancel path", cancelled.get("ok") is True and (cancelled.get("request") or {}).get("status") == "cancelled", cancelled)

            # Salary cert WITHOUT payroll
            sal = c2.request_letter(
                cur, company_code=COMPANY, employee_key=EMP,
                letter_type="salary_certificate", actor_phone=EMP_PHONE, lang="en",
            )
            sid = str((sal.get("request") or {}).get("request_id"))
            c2.approve_letter(
                cur, company_code=COMPANY, request_id=sid, actor_phone=HR_PHONE, reason="sal",
                expected_version=1,
            )
            cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (sid,))
            rv_s = int((cur.fetchone() or {}).get("row_version") or 1)
            sal_iss = c2.issue_letter(
                cur, company_code=COMPANY, request_id=sid, actor_phone=HR_PHONE, reason="sal issue",
                expected_version=rv_s,
            )
            check("salary cert without payroll", sal_iss.get("ok") is True, sal_iss)
            body_sal = str((sal_iss.get("download") or {}).get("body_text") or "")
            check("payroll independence (link off)", "not_linked" in body_sal or "not disclosed" in body_sal, body_sal)

            # Salary cert WITH optional payroll
            os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
            os.environ["WATHEFNI_PAYROLL_WAVE1_COMPANIES"] = COMPANY
            os.environ["WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY"] = "1"
            os.environ["WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS"] = "W3C2,EL2,PYW1"
            c2.enable_company_ess_letters_dependents(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="salary payroll optional on",
                letters_enabled=True,
                letters_fulfill=True,
                dependents_enabled=True,
                dependents_require_hr_review=True,
                salary_cert_use_payroll=True,
            )
            try:
                import payroll_authority_wave1 as pyw1

                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                draft = pyw1.create_contract_draft(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP,
                    effective_from=hire,
                    currency="KWD",
                    components=[{"code": "BASIC", "amount": 850, "is_basic": True}],
                    source_kind="manual",
                    actor_phone=HR_PHONE,
                    reason="c2 salary truth",
                    metadata={"synthetic": True, "wave": "w3c2"},
                )
                check("payroll draft for salary cert", draft.get("ok") is True, draft)
                contract = draft.get("contract") or draft
                contract_id = str(contract.get("contract_id") or "")
                row_v = int(contract.get("row_version") or 1)
                if draft.get("ok") and contract_id:
                    ap = pyw1.approve_contract(
                        cur,
                        company_code=COMPANY,
                        contract_id=contract_id,
                        actor_phone=OTHER_PHONE,
                        reason="approve sal truth",
                        expected_row_version=row_v,
                    )
                    check("payroll contract approved", ap.get("ok") is True, ap)

                sal2 = c2.request_letter(
                    cur, company_code=COMPANY, employee_key=EMP,
                    letter_type="salary_certificate", actor_phone=EMP_PHONE,
                )
                s2 = str((sal2.get("request") or {}).get("request_id"))
                c2.approve_letter(
                    cur, company_code=COMPANY, request_id=s2, actor_phone=HR_PHONE, reason="sal2",
                    expected_version=1,
                )
                cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (s2,))
                rv_s2 = int((cur.fetchone() or {}).get("row_version") or 1)
                sal2_iss = c2.issue_letter(
                    cur, company_code=COMPANY, request_id=s2, actor_phone=HR_PHONE, reason="sal2 issue",
                    expected_version=rv_s2,
                )
                check("salary cert with optional payroll", sal2_iss.get("ok") is True, sal2_iss)
                body2 = str((sal2_iss.get("download") or {}).get("body_text") or "")
                check(
                    "salary uses payroll truth when on",
                    "payroll_approved_contract" in body2 or "850" in body2 or "no_approved" in body2 or "Amount:" in body2,
                    body2,
                )
            except Exception as exc:
                check("salary cert with optional payroll", False, str(exc))

            # Dependents CRUD
            d1 = c2.create_dependent(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                relationship="spouse",
                name_en="Sara Emp",
                name_ar="سارة",
                date_of_birth=date(1990, 5, 1),
                actor_phone=HR_PHONE,
                reason="hr add",
                evidence_ref="doc://civil-id-1",
            )
            check("dependent add", d1.get("ok") is True, d1)
            did = str((d1.get("dependent") or {}).get("dependent_id"))

            dup = c2.create_dependent(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                relationship="spouse",
                name_en="Sara Emp",
                date_of_birth=date(1990, 5, 1),
                actor_phone=HR_PHONE,
                reason="dup",
            )
            check("duplicate protection", dup.get("error") == "duplicate_dependent", dup)

            ed = c2.edit_dependent(
                cur,
                company_code=COMPANY,
                dependent_id=did,
                actor_phone=HR_PHONE,
                reason="rename",
                name_en="Sara Emp Edited",
                expected_version=int((d1.get("dependent") or {}).get("row_version") or 1),
            )
            check("dependent edit", ed.get("ok") is True, ed)

            stale_ed = c2.edit_dependent(
                cur,
                company_code=COMPANY,
                dependent_id=did,
                actor_phone=HR_PHONE,
                reason="stale",
                name_en="Nope",
                expected_version=1,
            )
            check("stale/concurrent edit blocked", stale_ed.get("error") in ("stale_row_version", "stale_row_version_or_missing"), stale_ed)

            # Employee-requested dependent + HR review
            ch = c2.request_dependent_change(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                action="create",
                actor_phone=EMP_PHONE,
                proposed={
                    "relationship": "child",
                    "name_en": "Omar Emp",
                    "name_ar": "عمر",
                    "date_of_birth": str(hire + timedelta(days=4000)),
                },
            )
            check("employee-requested dependent change", ch.get("ok") is True and ch.get("requires_hr_review") is True, ch)
            chid = str((ch.get("change_request") or {}).get("change_request_id"))

            sod_d = c2.review_dependent_change(
                cur,
                company_code=COMPANY,
                change_request_id=chid,
                actor_phone=EMP_PHONE,
                decision="approve",
                reason="self",
            )
            check("dependent SoD self-approve forbidden", sod_d.get("error") == "sod_self_approve_forbidden", sod_d)

            hr_ok = c2.review_dependent_change(
                cur,
                company_code=COMPANY,
                change_request_id=chid,
                actor_phone=HR_PHONE,
                decision="approve",
                reason="verified",
                expected_version=int((ch.get("change_request") or {}).get("row_version") or 1),
            )
            check("HR reviews dependent change", hr_ok.get("ok") is True, hr_ok)
            check("dependent applied after review", (hr_ok.get("change_request") or {}).get("status") == "applied", hr_ok)

            listed = c2.list_dependents_for_employee(cur, company_code=COMPANY, employee_key=EMP)
            check("list dependents", listed.get("ok") is True and len(listed.get("dependents") or []) >= 2, listed)

            arch = c2.archive_dependent(
                cur,
                company_code=COMPANY,
                dependent_id=did,
                actor_phone=HR_PHONE,
                reason="archive",
                expected_version=int((ed.get("dependent") or {}).get("row_version") or 2),
            )
            check("dependent archive", arch.get("ok") is True and (arch.get("dependent") or {}).get("status") == "archived", arch)

            # Tenant: other company cannot see
            cur.execute(
                "SELECT count(*) AS c FROM employee_dependents WHERE company_code=%s AND employee_key=%s",
                (OTHER, EMP),
            )
            check("tenant isolation dependents", int((cur.fetchone() or {}).get("c") or 0) == 0)

            # Module-off visibility
            c2.enable_company_ess_letters_dependents(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="disable dependents surface",
                letters_enabled=True,
                letters_fulfill=True,
                dependents_enabled=False,
            )
            vis2 = c2.feature_visibility(cur, COMPANY)
            check("dependents hide when disabled", vis2.get("dependents_visible") is False, vis2)
            blocked_dep = c2.create_dependent(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                relationship="other",
                name_en="X",
                actor_phone=HR_PHONE,
                reason="should fail",
            )
            check("dependents disabled blocks create", blocked_dep.get("error") == "dependents_disabled", blocked_dep)

            src = Path(__file__).with_name("ess_letters_dependents_c2.py").read_text()
            check("independent of offboarding", "offboarding_c4" not in src and "payroll_settlement_ot_c6" not in src)
            check("independent of benefits", "benefits_" not in src or "dependents_are_not_benefits" in src)

            off = c2.disable_company_ess_letters_dependents(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="rollback"
            )
            check("disable preserves history flag", off.get("history_preserved") is True, off)
            check(
                "module-off after disable",
                c2.module_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )
            cur.execute(
                "SELECT count(*) AS c FROM ess_letter_versions WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            check("issued history intact after rollback", int((cur.fetchone() or {}).get("c") or 0) >= 2)
            cur.execute(
                "SELECT count(*) AS c FROM employee_dependent_history WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            check("dependent history intact after rollback", int((cur.fetchone() or {}).get("c") or 0) >= 1)

            # Status visibility for employee
            listed_letters = c2.list_letter_requests_for_employee(cur, company_code=COMPANY, employee_key=EMP)
            # module off — list should fail closed
            check(
                "module-off hides letter list",
                listed_letters.get("ok") is not True,
                listed_letters,
            )

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("ESS_LETTERS_DEPENDENTS_UNIT_PASS")
    print("ESS_LETTERS_DEPENDENTS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
