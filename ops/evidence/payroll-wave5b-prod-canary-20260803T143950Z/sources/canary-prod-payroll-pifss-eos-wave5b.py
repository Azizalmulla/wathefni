#!/usr/bin/env python3
"""Payroll Wave 5-B — production synthetic PIFSS + EOS review worksheet canary.

Synthetic subjects only (PYW5/PYW1/W5B · 965541*).
Proves: honesty, category separation, counsel-required / unsupported blocking,
effective-dated rule versioning, dual-approval override + evidence,
recalculation after source changes, immutable approved history, residual = 0,
SYNTHETIC_ONLY refusal for non-synthetic keys.

Does NOT: remittance, statutory filing, bank/WPS/AS'HAL, payments, or
auto-compliance claims. EOS never auto-payable. Native non-authoritative;
external remains money authority. payment_processing=disabled.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from datetime import date
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
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE5", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE5_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY", "1")
os.environ.setdefault(
    "WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_KEY_MARKERS",
    "PYW5,PYW5-SYNTH|,PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,"
    "PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4B,W4,W5B,W5",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_pifss_eos_wave5 as w5  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW5B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-PYW5-W5B-{TAG}"
CREATOR = f"9655411{TAG_DIGITS}"
APPROVER = f"9655412{TAG_DIGITS}"
OVERRIDE2 = f"9655413{TAG_DIGITS}"
REAL_EMP = "WATHEFNI-REAL-EMPLOYEE-NOT-SYNTH"

PERMS_APPROVE = ["payroll.read", "payroll.manage", "payroll.approve"]

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW5B_EVID") or f"/tmp/payroll-w5b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER, "override2": OVERRIDE2},
    "worksheet_ids": [],
    "rule_table_ids": [],
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


def cleanup(cur) -> dict[str, int]:
    deleted: dict[str, int] = {}
    tag_like = f"%{TAG}%"
    emp = EMP_KEY

    cur.execute(
        """
        DELETE FROM payroll_statutory_dual_control
        WHERE company_code=%s AND worksheet_id IN (
          SELECT worksheet_id FROM payroll_pifss_worksheets WHERE employee_key=%s
          UNION
          SELECT worksheet_id FROM payroll_eos_worksheets WHERE employee_key=%s
        )
        """,
        (COMPANY, emp, emp),
    )
    deleted["dual_control"] = cur.rowcount or 0

    cur.execute(
        """
        DELETE FROM payroll_statutory_worksheet_events
        WHERE company_code=%s AND (
          worksheet_id IN (
            SELECT worksheet_id FROM payroll_pifss_worksheets WHERE employee_key=%s
            UNION
            SELECT worksheet_id FROM payroll_eos_worksheets WHERE employee_key=%s
            UNION
            SELECT rule_table_id FROM payroll_statutory_rule_tables
              WHERE company_code=%s AND decision_note LIKE %s
          )
          OR payload::text LIKE %s
          OR payload::text LIKE %s
        )
        """,
        (COMPANY, emp, emp, COMPANY, tag_like, tag_like, f"%{TAG}%"),
    )
    deleted["events"] = cur.rowcount or 0

    cur.execute(
        "DELETE FROM payroll_pifss_worksheets WHERE company_code=%s AND employee_key=%s",
        (COMPANY, emp),
    )
    deleted["pifss"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_eos_worksheets WHERE company_code=%s AND employee_key=%s",
        (COMPANY, emp),
    )
    deleted["eos"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_statutory_rule_tables WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["rules"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_statutory_worksheet_events WHERE company_code=%s AND payload::text LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["events_sweep"] = cur.rowcount or 0
    return deleted


def residual(cur) -> int:
    total = 0
    tag_like = f"%{TAG}%"
    for sql, params in (
        (
            "SELECT count(*) AS c FROM payroll_pifss_worksheets WHERE employee_key=%s OR decision_note LIKE %s",
            (EMP_KEY, tag_like),
        ),
        (
            "SELECT count(*) AS c FROM payroll_eos_worksheets WHERE employee_key=%s OR decision_note LIKE %s",
            (EMP_KEY, tag_like),
        ),
        (
            "SELECT count(*) AS c FROM payroll_statutory_rule_tables WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT count(*) AS c FROM payroll_statutory_worksheet_events WHERE company_code=%s AND payload::text LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT count(*) AS c FROM payroll_statutory_dual_control WHERE company_code=%s AND payload::text LIKE %s",
            (COMPANY, tag_like),
        ),
    ):
        cur.execute(sql, params)
        total += int(dict(cur.fetchone())["c"])
    return total


def main() -> int:
    print("payroll pifss eos wave5b production synthetic canary")
    print("tag", TAG, "employee", EMP_KEY)

    h = w5.honesty_payload()
    check("version", w5.PAYROLL_WAVE5_VERSION == "1.0.0")
    check("wave5 enabled", w5.payroll_wave5_enabled() is True)
    check("synthetic_only", w5.payroll_wave5_synthetic_only() is True)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("no posts payment", h.get("posts_payment") is False)
    check("remittance false", h.get("remittance") is False)
    check("statutory filing false", h.get("statutory_filing") is False)
    check("pifss remittance false", h.get("pifss_remittance") is False)
    check("eos_auto_payable false", h.get("eos_auto_payable") is False)
    check("no auto compliance claim", h.get("automatic_legal_compliance_claim") is False)
    check("pifss worksheets", h.get("pifss_worksheets") is True)
    check("eos worksheets", h.get("eos_worksheets") is True)
    check("bank false", h.get("bank_files") is False)
    check("wps false", h.get("wps") is False)
    check("ashal false", h.get("ashal") is False)
    check("ai false", h.get("ai_calculations") is False)
    check("native non-auth", h.get("native_results_authoritative") is False)
    check("external authority", h.get("external_payroll_authority") == "external")

    inv = w5.freeze_invariants()
    check("freeze category separation", inv.get("category_separation") is True)
    check("freeze missing rule fail closed", inv.get("missing_rule_fail_closed") is True)
    check("freeze effective dated", inv.get("effective_dated_rules") is True)
    check("freeze dual override", inv.get("dual_approval_override") is True)
    check("freeze approved immutable", inv.get("approved_history_immutable") is True)
    check("freeze no remittance", inv.get("no_remittance") is True)
    check("freeze no auto payable", inv.get("no_auto_payable") is True)

    p_start = date(2034, 5, 1)
    p_end = date(2034, 5, 31)
    term_date = date(2034, 5, 15)
    salary = 1000
    salary_new = 1250
    rule_code_pifss = f"W5B_PIFSS_KUWAITI_{TAG}"
    rule_code_eos = f"W5B_EOS_ART51_{TAG}"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            check("production db", db == "wathefni", db)
            if db != "wathefni":
                print("REFUSE: not production database")
                return 2

            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            w5.ensure_payroll_wave5_schema(cur, force=True)

            # SYNTHETIC_ONLY refusal
            refused = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=REAL_EMP,
                employee_category="kuwaiti_national",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=salary,
                actor_phone=CREATOR,
                reason=f"w5b_refuse_{TAG}",
            )
            check(
                "nonsynthetic refused",
                refused.get("error") == "payroll_wave5_synthetic_only",
                refused,
            )

            # Category separation
            expat = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="expatriate",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=salary,
                actor_phone=CREATOR,
                reason=f"w5b_expat_{TAG}",
            )
            check("expat ok True", expat.get("ok") is True, expat)
            check(
                "expat status unsupported",
                (expat.get("worksheet") or {}).get("status") == "unsupported",
                expat,
            )
            check("expat error", expat.get("error") == "expatriate_no_pifss", expat)
            wid = str((expat.get("worksheet") or {}).get("worksheet_id") or "")
            if wid:
                IDS["worksheet_ids"].append(wid)
            cur.execute(
                "UPDATE payroll_pifss_worksheets SET status='superseded', updated_at=now() "
                "WHERE company_code=%s AND employee_key=%s AND status = ANY(%s)",
                (COMPANY, EMP_KEY, list(w5.ACTIVE_WS_STATUSES)),
            )

            gcc = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="gcc_national",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=salary,
                actor_phone=CREATOR,
                reason=f"w5b_gcc_{TAG}",
            )
            check("gcc ok False", gcc.get("ok") is False, gcc)
            check("gcc error counsel", gcc.get("error") == "counsel_required_rule", gcc)
            check(
                "gcc status counsel_required",
                (gcc.get("worksheet") or {}).get("status") == "counsel_required",
                gcc,
            )
            cur.execute(
                "UPDATE payroll_pifss_worksheets SET status='superseded', updated_at=now() "
                "WHERE company_code=%s AND employee_key=%s AND status = ANY(%s)",
                (COMPANY, EMP_KEY, list(w5.ACTIVE_WS_STATUSES)),
            )

            kuwaiti = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="kuwaiti_national",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=salary,
                actor_phone=CREATOR,
                reason=f"w5b_kuwaiti_{TAG}",
            )
            check("kuwaiti ok False", kuwaiti.get("ok") is False, kuwaiti)
            check("kuwaiti error counsel", kuwaiti.get("error") == "counsel_required_rule", kuwaiti)
            check(
                "kuwaiti status counsel_required",
                (kuwaiti.get("worksheet") or {}).get("status") == "counsel_required",
                kuwaiti,
            )
            kuwaiti_ws_id = str((kuwaiti.get("worksheet") or {}).get("worksheet_id") or "")
            check("kuwaiti worksheet id", bool(kuwaiti_ws_id), kuwaiti)
            if kuwaiti_ws_id:
                IDS["worksheet_ids"].append(kuwaiti_ws_id)

            # Effective-dated rule versioning
            upsert_v1 = w5.upsert_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                rule_code=rule_code_pifss,
                employee_category="kuwaiti_national",
                version_label="v1",
                effective_from=date(2026, 1, 1),
                counsel_status="pending",
                source_citation="w5b counsel KW PIFSS v1",
                rule_payload=dict(w5.SMOKE_PIFSS_KUWAITI_PAYLOAD),
                actor_phone=CREATOR,
                reason=f"w5b_upsert_pifss_v1_{TAG}",
            )
            check("upsert pifss v1", upsert_v1.get("ok") is True, upsert_v1)
            v1_id = str((upsert_v1.get("rule_table") or {}).get("rule_table_id") or "")
            if v1_id:
                IDS["rule_table_ids"].append(v1_id)

            pending_resolve = w5.resolve_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                employee_category="kuwaiti_national",
                as_of_date=date(2026, 6, 1),
                rule_code=rule_code_pifss,
            )
            check("resolve pending None", pending_resolve is None, pending_resolve)

            approve_v1 = w5.counsel_approve_rule_table(
                cur,
                company_code=COMPANY,
                rule_table_id=v1_id,
                actor_phone=APPROVER,
                reason=f"w5b_counsel_v1_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("counsel approve v1", approve_v1.get("ok") is True, approve_v1)

            resolved_v1 = w5.resolve_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                employee_category="kuwaiti_national",
                as_of_date=date(2026, 6, 1),
                rule_code=rule_code_pifss,
            )
            check("resolve returns v1", (resolved_v1 or {}).get("version_label") == "v1", resolved_v1)

            payload_v2 = copy.deepcopy(w5.SMOKE_PIFSS_KUWAITI_PAYLOAD)
            payload_v2["ceiling_kwd"] = 3000
            upsert_v2 = w5.upsert_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                rule_code=rule_code_pifss,
                employee_category="kuwaiti_national",
                version_label="v2",
                effective_from=date(2030, 1, 1),
                counsel_status="pending",
                source_citation="w5b counsel KW PIFSS v2",
                rule_payload=payload_v2,
                actor_phone=CREATOR,
                reason=f"w5b_upsert_pifss_v2_{TAG}",
            )
            check("upsert pifss v2", upsert_v2.get("ok") is True, upsert_v2)
            v2_id = str((upsert_v2.get("rule_table") or {}).get("rule_table_id") or "")
            if v2_id:
                IDS["rule_table_ids"].append(v2_id)
            approve_v2 = w5.counsel_approve_rule_table(
                cur,
                company_code=COMPANY,
                rule_table_id=v2_id,
                actor_phone=APPROVER,
                reason=f"w5b_counsel_v2_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("counsel approve v2", approve_v2.get("ok") is True, approve_v2)

            asof_2029 = w5.resolve_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                employee_category="kuwaiti_national",
                as_of_date=date(2029, 6, 1),
                rule_code=rule_code_pifss,
            )
            check("as_of 2029 → v1", (asof_2029 or {}).get("version_label") == "v1", asof_2029)
            asof_2030 = w5.resolve_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="pifss",
                employee_category="kuwaiti_national",
                as_of_date=date(2030, 6, 1),
                rule_code=rule_code_pifss,
            )
            check("as_of 2030 → v2", (asof_2030 or {}).get("version_label") == "v2", asof_2030)

            # Recalculate after counsel rule
            recalc = w5.recalculate_pifss(
                cur,
                company_code=COMPANY,
                worksheet_id=kuwaiti_ws_id,
                contributory_salary=salary,
                actor_phone=CREATOR,
                reason=f"w5b_recalc_rule_{TAG}",
            )
            check("recalc after rule ok", recalc.get("ok") is True, recalc)
            draft_ws = recalc.get("worksheet") or {}
            check("recalc draft status", draft_ws.get("status") == "draft", draft_ws)
            check("recalc has rule", bool(draft_ws.get("rule_table_id")), draft_ws)
            draft_id = str(draft_ws.get("worksheet_id") or "")
            check("recalc new worksheet", bool(draft_id) and draft_id != kuwaiti_ws_id, draft_id)
            if draft_id:
                IDS["worksheet_ids"].append(draft_id)
            prior_kw = w5.get_worksheet(
                cur, company_code=COMPANY, kind="pifss", worksheet_id=kuwaiti_ws_id
            )
            check(
                "prior counsel superseded",
                (prior_kw or {}).get("status") == "superseded",
                prior_kw,
            )

            # submit → self approve forbidden → approve
            submitted = w5.submit_worksheet_for_review(
                cur,
                kind="pifss",
                company_code=COMPANY,
                worksheet_id=draft_id,
                actor_phone=CREATOR,
                reason=f"w5b_submit_{TAG}",
                expected_row_version=int(draft_ws.get("row_version") or 1),
            )
            check("submit ok", submitted.get("ok") is True, submitted)
            in_review = submitted.get("worksheet") or {}

            self_appr = w5.approve_worksheet(
                cur,
                kind="pifss",
                company_code=COMPANY,
                worksheet_id=draft_id,
                actor_phone=CREATOR,
                reason=f"w5b_self_appr_{TAG}",
                expected_row_version=int(in_review.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check(
                "self approve forbidden",
                self_appr.get("error") == "self_approval_forbidden",
                self_appr,
            )

            approved = w5.approve_worksheet(
                cur,
                kind="pifss",
                company_code=COMPANY,
                worksheet_id=draft_id,
                actor_phone=APPROVER,
                reason=f"w5b_approve_{TAG}",
                expected_row_version=int(in_review.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("approve ok", approved.get("ok") is True, approved)
            check(
                "approved status",
                (approved.get("worksheet") or {}).get("status") == "approved",
                approved,
            )

            immut = w5.mutate_approved_forbidden(
                cur, kind="pifss", company_code=COMPANY, worksheet_id=draft_id
            )
            check(
                "mutate_approved_forbidden",
                immut.get("error") == "approved_worksheet_immutable",
                immut,
            )

            # Recalculate after source change — history retained as superseded
            recalc2 = w5.recalculate_pifss(
                cur,
                company_code=COMPANY,
                worksheet_id=draft_id,
                contributory_salary=salary_new,
                actor_phone=CREATOR,
                reason=f"w5b_recalc_salary_{TAG}",
            )
            check("recalc new salary ok", recalc2.get("ok") is True, recalc2)
            new_draft = recalc2.get("worksheet") or {}
            check("new draft status", new_draft.get("status") == "draft", new_draft)
            new_draft_id = str(new_draft.get("worksheet_id") or "")
            check("new draft distinct", bool(new_draft_id) and new_draft_id != draft_id, new_draft_id)
            if new_draft_id:
                IDS["worksheet_ids"].append(new_draft_id)

            prior_approved = w5.get_worksheet(
                cur, company_code=COMPANY, kind="pifss", worksheet_id=draft_id
            )
            check(
                "prior approved superseded",
                (prior_approved or {}).get("status") == "superseded",
                prior_approved,
            )
            hist = w5.list_pifss_worksheets(cur, company_code=COMPANY, employee_key=EMP_KEY, limit=50)
            hist_ids = {str(r.get("worksheet_id")) for r in hist}
            hist_statuses = {str(r.get("worksheet_id")): str(r.get("status")) for r in hist}
            check("history includes superseded approved", draft_id in hist_ids, hist_statuses)
            check(
                "history superseded status",
                hist_statuses.get(draft_id) == "superseded",
                hist_statuses.get(draft_id),
            )
            check("history includes new draft", new_draft_id in hist_ids, hist_ids)

            # EOS blocked Art 51/53 + Law 17/2018
            eos_art = w5.generate_eos_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="expatriate",
                termination_date=term_date,
                termination_reason="employer_termination",
                service_start=date(2020, 1, 1),
                service_end=term_date,
                monthly_wage=800,
                art_51_53_status="unresolved_blocked",
                law_17_2018_status="not_applicable",
                actor_phone=CREATOR,
                reason=f"w5b_eos_art_{TAG}",
            )
            check("eos art blocked ok False", eos_art.get("ok") is False, eos_art)
            check(
                "eos art blocked error",
                eos_art.get("error") == "blocked_unresolved_eos_case",
                eos_art,
            )
            cur.execute(
                "UPDATE payroll_eos_worksheets SET status='superseded', updated_at=now() "
                "WHERE company_code=%s AND employee_key=%s AND status = ANY(%s)",
                (COMPANY, EMP_KEY, list(w5.ACTIVE_WS_STATUSES)),
            )

            eos_law17 = w5.generate_eos_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="kuwaiti_national",
                termination_date=term_date,
                termination_reason="employer_termination",
                service_start=date(2020, 1, 1),
                service_end=term_date,
                monthly_wage=800,
                art_51_53_status="resolved",
                law_17_2018_status="unresolved_blocked",
                actor_phone=CREATOR,
                reason=f"w5b_eos_law17_{TAG}",
            )
            check("eos law17 blocked ok False", eos_law17.get("ok") is False, eos_law17)
            check(
                "eos law17 blocked error",
                eos_law17.get("error") == "blocked_unresolved_eos_case",
                eos_law17,
            )
            cur.execute(
                "UPDATE payroll_eos_worksheets SET status='superseded', updated_at=now() "
                "WHERE company_code=%s AND employee_key=%s AND status = ANY(%s)",
                (COMPANY, EMP_KEY, list(w5.ACTIVE_WS_STATUSES)),
            )

            # EOS draft + dual override
            eos_rule = w5.upsert_rule_table(
                cur,
                company_code=COMPANY,
                rule_domain="eos",
                rule_code=rule_code_eos,
                employee_category="expatriate",
                version_label="v1",
                effective_from=date(2026, 1, 1),
                counsel_status="pending",
                source_citation="w5b counsel EOS Art51 monthly",
                rule_payload=dict(w5.SMOKE_EOS_MONTHLY_ART51_PAYLOAD),
                actor_phone=CREATOR,
                reason=f"w5b_upsert_eos_{TAG}",
            )
            check("upsert eos rule", eos_rule.get("ok") is True, eos_rule)
            eos_rule_id = str((eos_rule.get("rule_table") or {}).get("rule_table_id") or "")
            if eos_rule_id:
                IDS["rule_table_ids"].append(eos_rule_id)
            eos_rule_appr = w5.counsel_approve_rule_table(
                cur,
                company_code=COMPANY,
                rule_table_id=eos_rule_id,
                actor_phone=APPROVER,
                reason=f"w5b_counsel_eos_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("counsel approve eos", eos_rule_appr.get("ok") is True, eos_rule_appr)

            eos_ok = w5.generate_eos_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="expatriate",
                termination_date=term_date,
                termination_reason="employer_termination",
                service_start=date(2020, 1, 1),
                service_end=term_date,
                monthly_wage=800,
                art_51_53_status="resolved",
                law_17_2018_status="not_applicable",
                actor_phone=CREATOR,
                reason=f"w5b_eos_draft_{TAG}",
                rule_code=rule_code_eos,
            )
            check("eos generate ok", eos_ok.get("ok") is True, eos_ok)
            eos_ws = eos_ok.get("worksheet") or {}
            check("eos draft status", eos_ws.get("status") == "draft", eos_ws)
            check(
                "eos review worksheet",
                eos_ws.get("authoritative_label") == "review_worksheet_only",
                eos_ws,
            )
            check("eos automatic_payable false", eos_ok.get("eos_auto_payable") is False, eos_ok)
            eos_payload = eos_ws.get("worksheet_payload") or {}
            if isinstance(eos_payload, str):
                eos_payload = json.loads(eos_payload)
            check(
                "eos not payable instruction",
                eos_payload.get("automatic_payable_instruction") is False
                or eos_payload.get("not_payable_instruction") is True,
                eos_payload,
            )
            eos_ws_id = str(eos_ws.get("worksheet_id") or "")
            if eos_ws_id:
                IDS["worksheet_ids"].append(eos_ws_id)

            # Evidence preserved
            check(
                "eos termination reason preserved",
                eos_ws.get("termination_reason") == "employer_termination"
                or (eos_payload.get("termination_reason") == "employer_termination"),
                eos_ws,
            )

            init_ov = w5.initiate_manual_override(
                cur,
                kind="eos",
                company_code=COMPANY,
                worksheet_id=eos_ws_id,
                actor_phone=APPROVER,
                reason=f"w5b_override_init_{TAG}",
                exception_code="w5b_manual_exception",
                exception_evidence={"note": TAG, "canary": "wave5b"},
                actor_permissions=PERMS_APPROVE,
            )
            check("override initiate", init_ov.get("ok") is True, init_ov)
            dual_id = str((init_ov.get("dual_control") or {}).get("action_id") or "")
            check("dual action id", bool(dual_id), init_ov)

            same_actor = w5.confirm_manual_override(
                cur,
                kind="eos",
                company_code=COMPANY,
                worksheet_id=eos_ws_id,
                actor_phone=APPROVER,
                reason=f"w5b_override_same_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check(
                "override same actor deny",
                same_actor.get("error") == "dual_control_same_actor",
                same_actor,
            )

            confirmed = w5.confirm_manual_override(
                cur,
                kind="eos",
                company_code=COMPANY,
                worksheet_id=eos_ws_id,
                actor_phone=OVERRIDE2,
                reason=f"w5b_override_confirm_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("override confirm ok", confirmed.get("ok") is True, confirmed)
            check(
                "override exception status",
                (confirmed.get("worksheet") or {}).get("status") == "exception",
                confirmed,
            )
            check("override no remittance", confirmed.get("remittance") is False, confirmed)

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
        "wave": "5-B",
        "payment_processing": "disabled",
        "posts_payment": False,
        "remittance": False,
        "statutory_filing": False,
        "automatic_legal_compliance_claim": False,
        "pifss_worksheets": True,
        "pifss_remittance": False,
        "eos_worksheets": True,
        "eos_auto_payable": False,
        "bank_files": False,
        "wps": False,
        "ashal": False,
        "ai_calculations": False,
        "native_results_authoritative": False,
        "external_payroll_authority": "external",
        "synthetic_only": True,
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("QUALIFICATION_JSON", EVID / "qualification.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
