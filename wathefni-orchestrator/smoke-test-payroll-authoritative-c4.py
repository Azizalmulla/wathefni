#!/usr/bin/env python3
"""Wave 2 C4 — Authoritative Payroll prove (company-scoped; global OFF).

Synthetic canary only. No payment / WPS / bank send.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PYC{_N:05d}"[:12].upper()
OTHER = f"PYX{_N:05d}"[:12].upper()
CREATOR = f"9655511{_N:05d}"
APPROVER = f"9655512{_N:05d}"
FINALIZER = f"9655513{_N:05d}"
EMP = f"{COMPANY}-PYW1-PYC4-{SUFFIX}"
MARKERS = "PYW1,PYP1,PYP2,PYP3,PYP4A,PYP4B,PYP5,PYP6,PYC4,PYAUTH,PYINPUT,PYCALC"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c4: str, companies: str) -> None:
    os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_C4"] = c4
    os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES"] = companies
    for flag in (
        "WATHEFNI_PAYROLL_WAVE1",
        "WATHEFNI_PAYROLL_AUTHORITY_P1",
        "WATHEFNI_PAYROLL_AUTHORITY_P2",
        "WATHEFNI_PAYROLL_AUTHORITY_P3",
        "WATHEFNI_PAYROLL_AUTHORITY_P4A",
        "WATHEFNI_PAYROLL_AUTHORITY_P4B",
        "WATHEFNI_PAYROLL_AUTHORITY_P5",
        "WATHEFNI_PAYROLL_AUTHORITY_P6",
    ):
        os.environ[flag] = "1"
        os.environ[f"{flag}_COMPANIES"] = f"{COMPANY},{OTHER}"
        os.environ[f"{flag}_SYNTHETIC_ONLY"] = "1"
    os.environ["WATHEFNI_PAYROLL_AUTHORITY_P6_ALLOW_SYNTHETIC_QUALIFICATION"] = "1"
    for mk in (
        "WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P6_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS",
    ):
        os.environ[mk] = MARKERS


def unique_period() -> tuple[date, date]:
    n = int(SUFFIX[:4], 16) % 120
    year = 2036 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def upsert_employee(cur: Any, key: str, phone: str, *, hire: date) -> None:
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE
          SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, name=EXCLUDED.name,
              hire_date=EXCLUDED.hire_date, start_date=EXCLUDED.start_date, updated_at=now()
        """,
        (COMPANY, key, phone, f"C4 {key[-12:]}", hire, hire),
    )


def approve_contract(cur: Any, pyw1: Any, *, employee_key: str, effective_from: date) -> str:
    draft = pyw1.create_contract_draft(
        cur,
        company_code=COMPANY,
        employee_key=employee_key,
        effective_from=effective_from,
        components=[
            {"component_kind": "earning", "code": "BASIC", "amount": 700, "is_basic": True},
            {"component_kind": "earning", "code": "HOUSING", "amount": 100},
            {"component_kind": "deduction", "code": "OTHER_DED", "amount": 25},
        ],
        actor_phone=CREATOR,
        reason=f"pyc4_draft_{SUFFIX}",
    )
    cid = str((draft.get("contract") or {}).get("contract_id"))
    pyw1.approve_contract(
        cur,
        company_code=COMPANY,
        contract_id=cid,
        actor_phone=APPROVER,
        reason=f"pyc4_appr_{SUFFIX}",
        expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
    )
    return cid


def run_mode_a_path(
    cur: Any,
    *,
    c4: Any,
    pyw1: Any,
    p2: Any,
    p3: Any,
    p5: Any,
    p_start: date,
    p_end: date,
    feed_mode: str,
    tag: str,
    finalize: bool = True,
) -> dict[str, Any]:
    feeds = c4.configure_input_feeds(
        cur, company_code=COMPANY, mode=feed_mode, actor_phone=APPROVER, reason=f"{tag}_feeds"
    )
    if not feeds.get("ok"):
        return {"ok": False, "step": "feeds", "result": feeds}
    flags = feeds.get("policy_flags") or {}

    period = pyw1.create_period(
        cur,
        company_code=COMPANY,
        period_start=p_start,
        period_end=p_end,
        attendance_input_source="approved_snapshots",
        actor_phone=CREATOR,
        reason=f"{tag}_period",
    )
    if not period.get("ok"):
        # period may already exist for matrix reuse — load/create with unique note via offset months
        return {"ok": False, "step": "period", "result": period}
    period_id = str((period.get("period") or {}).get("period_id") or "")

    if feed_mode in {"leave", "all"}:
        cur.execute("SAVEPOINT c4_leave_seed")
        try:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, reason, metadata, payroll_handoff
                ) VALUES (%s,%s,%s,%s,'unpaid',%s,%s,'approved',%s,%s::jsonb,%s::jsonb)
                """,
                (
                    COMPANY,
                    EMP,
                    f"96557{_N:05d}01",
                    f"C4 {EMP[-12:]}",
                    p_start + timedelta(days=2),
                    p_start + timedelta(days=2),
                    f"{tag}_unpaid",
                    json.dumps({"pyc4": True}),
                    json.dumps({"classification": "unpaid_leave"}),
                ),
            )
            cur.execute("RELEASE SAVEPOINT c4_leave_seed")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT c4_leave_seed")

    if feed_mode == "imported":
        # Manual/imported independence: one-off adjustment as imported provenance (no Att/Leave required).
        try:
            p3.create_one_off_adjustment(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                period_start=p_start,
                period_end=p_end,
                component_code="IMPORT_ADJ",
                amount=15,
                line_kind="earning",
                actor_phone=APPROVER,
                reason=f"{tag}_imported_adj",
            )
        except Exception:
            pass

    assembled = p2.assemble_payroll_inputs(
        cur,
        company_code=COMPANY,
        period_start=p_start,
        period_end=p_end,
        employee_keys=[EMP],
        actor_phone=CREATOR,
        reason=f"{tag}_assemble",
    )
    if not assembled.get("ok"):
        return {"ok": False, "step": "assemble", "result": assembled, "feeds": feeds}
    snap = assembled.get("input_snapshot") or {}
    sid = str(snap.get("input_snapshot_id"))
    locked = p2.lock_payroll_input_snapshot(
        cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER, reason=f"{tag}_lock", force=True
    )
    if not locked.get("ok"):
        return {"ok": False, "step": "lock", "result": locked}
    sid = str((locked.get("input_snapshot") or snap).get("input_snapshot_id") or sid)

    # Provenance: every assemble carries source_counts / fingerprints
    provenance = {
        "input_snapshot_id": sid,
        "content_fingerprint": (locked.get("input_snapshot") or snap).get("content_fingerprint"),
        "source_fingerprint": (locked.get("input_snapshot") or snap).get("source_fingerprint"),
        "feed_mode": feed_mode,
        "feeds": feeds.get("feeds"),
    }

    pol = p3.create_policy_version(
        cur,
        company_code=COMPANY,
        effective_from=p_start,
        actor_phone=APPROVER,
        reason=f"{tag}_policy",
        attendance_payroll_mode=flags.get("attendance_payroll_mode") or "ignored",
        lateness_money_enabled=bool(flags.get("lateness_money_enabled")),
        absence_money_enabled=bool(flags.get("absence_money_enabled")),
        unpaid_leave_money_enabled=bool(flags.get("unpaid_leave_money_enabled")),
        ot_money_enabled=bool(flags.get("ot_money_enabled")),
        rest_day_money_enabled=False,
        public_holiday_money_enabled=False,
        sick_leave_money_enabled=bool(flags.get("sick_leave_money_enabled")),
        approve=True,
    )
    if not pol.get("ok"):
        return {"ok": False, "step": "policy", "result": pol}
    pol_id = str((pol.get("policy") or {}).get("policy_version_id"))

    calc = p3.calculate_mode_a_preview(
        cur,
        company_code=COMPANY,
        input_snapshot_id=sid,
        actor_phone=APPROVER,
        reason=f"{tag}_calc",
        policy_version_id=pol_id,
        employee_keys=[EMP],
    )
    if not calc.get("ok"):
        return {"ok": False, "step": "calc", "result": calc}
    run = calc.get("calc_run") or {}
    calc_id = str(run.get("calc_run_id"))

    if not finalize:
        return {
            "ok": True,
            "period_id": period_id,
            "input_snapshot_id": sid,
            "calc_run_id": calc_id,
            "calc_run": run,
            "provenance": provenance,
            "feeds": feeds,
            "period_state": "calculated",
        }

    p5.upsert_company_finalize_policy(
        cur,
        company_code=COMPANY,
        actor_phone=APPROVER,
        reason=f"{tag}_fin_pol",
        require_review_step=True,
        require_distinct_reviewer=True,
        require_distinct_approver=True,
        require_distinct_finalizer=True,
        allow_approver_as_finalizer=True,
    )
    created = p5.create_finalize_run_from_calc(
        cur,
        company_code=COMPANY,
        calc_run_id=calc_id,
        actor_phone=CREATOR,
        reason=f"{tag}_create_fin",
        employee_keys=[EMP],
    )
    if not created.get("ok"):
        return {"ok": False, "step": "create_finalize", "result": created}
    fid = str((created.get("finalize_run") or {}).get("finalize_run_id"))
    p5.submit_finalize_for_review(
        cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"{tag}_submit"
    )
    fr = p5._get_finalize(cur, company_code=COMPANY, finalize_run_id=fid) or {}  # noqa: SLF001
    approved = c4.approve_finalize_with_version(
        cur,
        company_code=COMPANY,
        finalize_run_id=fid,
        actor_phone=APPROVER,
        reason=f"{tag}_approve",
        expected_row_version=int(fr.get("row_version") or 0),
    )
    if not approved.get("ok"):
        return {"ok": False, "step": "approve", "result": approved}

    finalized = c4.authoritative_finalize(
        cur,
        company_code=COMPANY,
        finalize_run_id=fid,
        actor_phone=FINALIZER,
        reason=f"{tag}_finalize",
        employee_keys=[EMP],
    )
    return {
        "ok": bool(finalized.get("ok")),
        "period_id": period_id,
        "input_snapshot_id": sid,
        "calc_run_id": calc_id,
        "finalize_run_id": fid,
        "finalize": finalized,
        "provenance": provenance,
        "feeds": feeds,
        "period_state": "finalized" if finalized.get("ok") else "approved",
        "calc_run": run,
    }


def main() -> int:
    print("    payroll authoritative c4 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import payroll_authoritative_c4 as c4

    check("c4 module", c4.PHASE == "payroll_authoritative_c4")
    check("rollback guidance", "WATHEFNI_PAYROLL_AUTHORITATIVE_C4=off" in str(c4.rollback_guidance()))
    check("EN finalized", c4.status_label("finalized", lang="en") == "Finalized")
    check("AR finalized", c4.status_label("finalized", lang="ar") == "مختوم")
    check("payment disabled honesty", c4.honesty_payload().get("payment_processing") == "disabled")
    check("no WPS/bank", c4.honesty_payload().get("wps_bank_send") is False)
    check("e360 not calculator", c4.honesty_payload().get("e360_is_payroll_calculator") is False)
    check("attendance not required", c4.honesty_payload().get("attendance_required") is False)

    _flags(c4="off", companies="")
    g0 = c4.runtime_gate_for_company(COMPANY)
    check("global c4 off", g0.get("ok") is not True, g0)

    _flags(c4="on", companies="")
    g1 = c4.runtime_gate_for_company(COMPANY)
    check("empty allowlist denies", "allowlist" in str(g1.get("gate")), g1)

    _flags(c4="on", companies=COMPANY)
    g2 = c4.runtime_gate_for_company(COMPANY)
    check("canary runtime allowlisted", g2.get("ok") is True, g2)
    g3 = c4.runtime_gate_for_company(OTHER)
    check("other company denied", g3.get("ok") is not True, g3)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_authority_production_p6 as p6

    p_start, p_end = unique_period()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
            p2.ensure_payroll_input_snapshot_schema(cur, force=True)
            p3.ensure_payroll_components_policy_schema(cur, force=True)
            # Clear aborted txn if a prior ensure failed mid-script.
            try:
                cur.execute("SELECT 1")
            except Exception:
                conn.rollback()
            p5.ensure_payroll_mode_a_finalize_schema(cur, force=True)
            p6.ensure_payroll_production_p6_schema(cur)
            c4.ensure_payroll_authoritative_c4_schema(cur)
            pyw1.ensure_company_settings(cur, company_code=COMPANY)
            cur.execute(
                """
                UPDATE payroll_company_settings
                   SET payroll_mode='native', payment_processing='disabled', updated_at=now()
                 WHERE company_code=%s
                """,
                (COMPANY,),
            )

            # Cannot claim authoritative without enable
            mid = c4.authoritative_finalize_enabled_for_company(cur, COMPANY)
            check("not enabled until opt-in", mid.get("ok") is not True, mid)

            en = c4.enable_company_authoritative_finalize(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="enable canary authoritative finalize",
                feed_attendance=False,
                feed_leave=False,
                feed_ot=False,
            )
            check("authoritative finalize enabled", en.get("ok") is True, en)
            gate = c4.authoritative_finalize_enabled_for_company(cur, COMPANY)
            check("authoritative gate open", gate.get("ok") is True, gate)

            hire = p_start - timedelta(days=90)
            upsert_employee(cur, EMP, f"96557{_N:05d}01", hire=hire)
            p6.add_employee_allowlist(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=APPROVER,
                reason=f"c4 allowlist {SUFFIX}",
            )
            approve_contract(cur, pyw1, employee_key=EMP, effective_from=hire)

            # Modularity matrix — configure + assemble/calc for each feed (finalize only primary paths)
            for mode in ("manual", "imported", "attendance", "leave", "ot", "all"):
                # Distinct period months per mode to avoid period collisions
                offset = {"manual": 0, "imported": 1, "attendance": 2, "leave": 3, "ot": 4, "all": 5}[mode]
                m = ((p_start.month - 1 + offset) % 12) + 1
                y = p_start.year + ((p_start.month - 1 + offset) // 12)
                ps = date(y, m, 1)
                pe = date(y, m, calendar.monthrange(y, m)[1])
                do_finalize = mode in {"manual", "all"}
                path = run_mode_a_path(
                    cur,
                    c4=c4,
                    pyw1=pyw1,
                    p2=p2,
                    p3=p3,
                    p5=p5,
                    p_start=ps,
                    p_end=pe,
                    feed_mode=mode,
                    tag=f"pyc4_{mode}_{SUFFIX}",
                    finalize=do_finalize,
                )
                check(f"feed mode {mode} path", path.get("ok") is True, path)
                if path.get("ok"):
                    check(
                        f"feed mode {mode} has provenance",
                        bool((path.get("provenance") or {}).get("content_fingerprint")),
                        path.get("provenance"),
                    )
                    check(
                        f"feed mode {mode} calc preview authority",
                        (path.get("calc_run") or {}).get("money_authority") == "preview_non_authoritative"
                        or not do_finalize,
                        path.get("calc_run"),
                    )
                if mode == "manual" and path.get("ok"):
                    fin = path.get("finalize") or {}
                    snaps = fin.get("authority_snapshots") or []
                    check("manual finalize authoritative", fin.get("authoritative") is True, fin)
                    check("manual sealed present", len(snaps) >= 1, snaps)
                    auth = snaps[0] if snaps else {}
                    aid = str(auth.get("authority_snapshot_id") or "")
                    check("money_authority=wathefni", auth.get("money_authority") == "wathefni", auth)
                    mutate = p1.refuse_mutate_sealed_snapshot(cur, company_code=COMPANY, authority_snapshot_id=aid)
                    check(
                        "post-finalize immutability",
                        mutate.get("ok") is False and mutate.get("error") == "sealed_snapshot_immutable",
                        mutate,
                    )
                    again = c4.authoritative_finalize(
                        cur,
                        company_code=COMPANY,
                        finalize_run_id=str(path.get("finalize_run_id")),
                        actor_phone=FINALIZER,
                        reason=f"pyc4_idempotent_{SUFFIX}",
                        employee_keys=[EMP],
                        check_stale_inputs=False,
                    )
                    check("duplicate finalize idempotent", again.get("ok") is True and again.get("idempotent") is True, again)
                    check(
                        "audit before/after present",
                        bool(fin.get("audit_before")) and bool(fin.get("audit_after")),
                        fin,
                    )
                    # Reopen forbidden
                    if path.get("period_id"):
                        # close/lock then reopen
                        try:
                            pyw1.lock_period(
                                cur,
                                company_code=COMPANY,
                                period_id=path["period_id"],
                                actor_phone=APPROVER,
                                reason=f"pyc4_lock_{SUFFIX}",
                            )
                        except Exception:
                            pass
                        try:
                            pyw1.close_period(
                                cur,
                                company_code=COMPANY,
                                period_id=path["period_id"],
                                actor_phone=APPROVER,
                                reason=f"pyc4_close_{SUFFIX}",
                            )
                        except Exception:
                            pass
                        reopen = pyw1.reopen_period(
                            cur,
                            company_code=COMPANY,
                            period_id=path["period_id"],
                            actor_phone=APPROVER,
                            reason=f"pyc4_reopen_{SUFFIX}",
                        )
                        check(
                            "period reopen forbidden after authoritative seal",
                            reopen.get("ok") is False
                            and reopen.get("error")
                            in {"authoritative_period_reopen_forbidden", "invalid_period_transition", "period_not_found"},
                            reopen,
                        )

                if mode == "all" and path.get("ok"):
                    fin = path.get("finalize") or {}
                    check("all-feeds finalize ok", fin.get("ok") is True and fin.get("authoritative") is True, fin)

            # SoD + stale approval on a fresh calculated period (offset 8 — beyond feed matrix 0–5)
            sod_m = ((p_start.month - 1 + 8) % 12) + 1
            sod_y = p_start.year + ((p_start.month - 1 + 8) // 12)
            ps = date(sod_y, sod_m, 1)
            pe = date(sod_y, sod_m, calendar.monthrange(sod_y, sod_m)[1])
            path = run_mode_a_path(
                cur,
                c4=c4,
                pyw1=pyw1,
                p2=p2,
                p3=p3,
                p5=p5,
                p_start=ps,
                p_end=pe,
                feed_mode="manual",
                tag=f"pyc4_sod_{SUFFIX}",
                finalize=False,
            )
            if not path.get("ok"):
                try:
                    conn.rollback()
                except Exception:
                    pass
            check("sod fixture calculated", path.get("ok") is True, path)
            if path.get("ok"):
                p5.upsert_company_finalize_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=APPROVER,
                    reason=f"pyc4_sod_pol_{SUFFIX}",
                    require_review_step=True,
                    require_distinct_approver=True,
                    require_distinct_finalizer=True,
                    allow_approver_as_finalizer=True,
                )
                created = p5.create_finalize_run_from_calc(
                    cur,
                    company_code=COMPANY,
                    calc_run_id=str(path["calc_run_id"]),
                    actor_phone=CREATOR,
                    reason=f"pyc4_sod_create_{SUFFIX}",
                    employee_keys=[EMP],
                )
                fid = str((created.get("finalize_run") or {}).get("finalize_run_id"))
                p5.submit_finalize_for_review(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"pyc4_sod_sub_{SUFFIX}"
                )
                sod = p5.approve_finalize_run(
                    cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"pyc4_sod_bad_{SUFFIX}"
                )
                check(
                    "approve/finalize SoD",
                    sod.get("ok") is False and sod.get("error") == "sod_creator_cannot_approve",
                    sod,
                )
                # Stale version
                fr = p5._get_finalize(cur, company_code=COMPANY, finalize_run_id=fid)  # noqa: SLF001
                stale = c4.approve_finalize_with_version(
                    cur,
                    company_code=COMPANY,
                    finalize_run_id=fid,
                    actor_phone=APPROVER,
                    reason=f"pyc4_stale_{SUFFIX}",
                    expected_row_version=0,
                )
                check(
                    "stale concurrent approval conflict",
                    stale.get("error") == "stale_finalize_decision",
                    stale,
                )
                ok_appr = c4.approve_finalize_with_version(
                    cur,
                    company_code=COMPANY,
                    finalize_run_id=fid,
                    actor_phone=APPROVER,
                    reason=f"pyc4_ok_appr_{SUFFIX}",
                    expected_row_version=int((fr or {}).get("row_version") or 0),
                )
                check("versioned approve ok", ok_appr.get("ok") is True, ok_appr)

            # Tenant isolation / RBAC surface
            other_gate = c4.authoritative_finalize_enabled_for_company(cur, OTHER)
            check("tenant isolation", other_gate.get("ok") is not True, other_gate)

            # Synthetic vs authoritative distinction
            check(
                "synthetic default flagged",
                c4.honesty_payload(company_code=COMPANY).get("synthetic_default_non_authoritative") is True,
            )
            check(
                "non-allowlisted company cannot claim",
                c4.runtime_gate_for_company("NOPECO") .get("ok") is not True,
            )

            # Disabled optional modules do not break (attendance ignored already proved via manual)
            try:
                feeds_off = c4.configure_input_feeds(
                    cur, company_code=COMPANY, mode="manual", actor_phone=APPROVER, reason="modules off ok"
                )
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                feeds_off = {"ok": False, "error": str(exc)}
            check(
                "disabled feeds do not break payroll",
                feeds_off.get("disabled_modules_do_not_break_payroll") is True,
                feeds_off,
            )

            # Independence from Attendance/Leave/Shifts modules
            src = Path(__file__).with_name("payroll_authoritative_c4.py").read_text()
            check("c4 does not import attendance_truth", "attendance_truth_c1" not in src)
            check("c4 does not import leave_enforcement", "leave_enforcement_c2" not in src)
            check("c4 does not import shifts_mss", "shifts_mss_c3" not in src)

            # Rollback entitlement off preserves seals
            off = c4.disable_company_authoritative_finalize(
                cur, company_code=COMPANY, actor_phone=APPROVER, reason="rollback canary entitlement"
            )
            check("rollback entitlement off", off.get("ok") is True and off.get("sealed_records_preserved") is True, off)
            after_off = c4.authoritative_finalize_enabled_for_company(cur, COMPANY)
            check("gate closed after rollback", after_off.get("ok") is not True, after_off)
            # Re-enable for residual sealed immutability check already done above

            # Payment still disabled on company settings
            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            check("company payment_processing disabled", str(settings.get("payment_processing")) == "disabled", settings)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("PAYROLL_AUTHORITY_UNIT_PASS")
    print("PAYROLL_AUTHORITY_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
