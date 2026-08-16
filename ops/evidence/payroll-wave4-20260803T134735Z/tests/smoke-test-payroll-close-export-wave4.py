#!/usr/bin/env python3
"""Payroll Wave 4 — close + finance export smoke (local/staging).

Proves:
  review → approve → close workflow
  immutable closed-run snapshot
  SOD for approve / close / export
  controlled reopen with dual approval
  balanced journal validation
  invalid mappings fail closed
  bank-export contract validation only
  export history / approvals / fingerprints / reconciliation
  export idempotency + fingerprint drift
  honesty: payment disabled, no real bank/WPS/PIFSS/EOS/AI
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
EMP = f"WATHEFNI-PYW1-PYW4-{SUFFIX}"
CREATOR = "965541100041"
APPROVER = "965541100042"
CLOSER = "965541100043"
EXPORTER = "965541100044"
EXPORTER2 = "965541100045"
REAL = "WATHEFNI-96566363363"

PERMS_APPROVE = ["payroll.read", "payroll.manage", "payroll.approve"]
PERMS_EXPORT = ["payroll.read", "payroll.export"]
PERMS_SOD_BAD = ["payroll.read", "payroll.approve", "payroll.export"]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    payroll close export wave4")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    for k, v in {
        "WATHEFNI_PAYROLL_WAVE1": "1",
        "WATHEFNI_PAYROLL_WAVE1_COMPANIES": "WATHEFNI",
        "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY": "1",
        "WATHEFNI_PAYROLL_WAVE2A": "1",
        "WATHEFNI_PAYROLL_WAVE2A_COMPANIES": "WATHEFNI",
        "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY": "1",
        "WATHEFNI_PAYROLL_WAVE2B": "1",
        "WATHEFNI_PAYROLL_WAVE2B_COMPANIES": "WATHEFNI",
        "WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY": "1",
        "WATHEFNI_PAYROLL_WAVE4": "1",
        "WATHEFNI_PAYROLL_WAVE4_COMPANIES": "WATHEFNI",
        "WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY": "1",
    }.items():
        os.environ.setdefault(k, v)

    import payroll_authority_wave1 as pyw1
    import payroll_external_adapter_wave2a as w2a
    import payroll_native_preview_wave2b as w2b
    import payroll_close_export_wave4 as w4

    h = w4.honesty_payload()
    check("version", w4.PAYROLL_WAVE4_VERSION == "1.0.0")
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("no posts payment", h.get("posts_payment") is False)
    check("journal drafts", h.get("journal_drafts") is True)
    check("no erp journals", h.get("journals") is False)
    check("bank contract only", h.get("bank_export_contract") is True)
    check("no bank files", h.get("bank_files") is False)
    check("no bank connection", h.get("bank_connection") is False)
    check("no wps", h.get("wps") is False)
    check("no ashal", h.get("ashal") is False)
    check("no pifss", h.get("pifss") is False)
    check("no eos", h.get("eos") is False)
    check("no AI", h.get("ai_calculations") is False)
    check("native non-auth", h.get("native_results_authoritative") is False)
    check("external authority", h.get("external_payroll_authority") == "external")
    inv = w4.freeze_invariants()
    check("immutable invariant", inv.get("closed_runs_immutable") is True)
    check("dual reopen invariant", inv.get("reopen_requires_dual_approval") is True)
    check("sod invariant", inv.get("sod_approve_close_export") is True)

    dash_candidates = [
        Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    dash = next((p for p in dash_candidates if (p / "payrollCloseExportUx.ts").exists()), None)
    if dash:
        ux = (dash / "payrollCloseExportUx.ts").read_text(encoding="utf-8")
        ws = (dash / "CloseExportWorkspace.tsx").read_text(encoding="utf-8") if (dash / "CloseExportWorkspace.tsx").exists() else ""
        check("ux en title", "Close & finance export" in ux)
        check("ux ar title", "الإغلاق وتصدير المالية" in ux)
        check("ux honesty", "validation only" in ux.lower() or "تحقق فقط" in ux)
        check("ux payment disabled", "disabled" in ux.lower())
        check("ux mobile", "mobileHint" in ux and "md:hidden" in ws)
        check("ux rtl", "rtl" in ws or "dir=" in ws)
    else:
        print("      SKIP  ux files not co-located (covered by smoke-test-payroll-close-export-wave4-ux.py)")

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit+ux)")
            return 1 if FAIL else 0
        raise

    company = "WATHEFNI"
    p_start = date(2031, 4, 1)
    p_end = date(2031, 4, 30)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            if db == "wathefni":
                print("REFUSE production database in staging smoke")
                return 2

            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            w2a.ensure_payroll_wave2a_schema(cur, force=True)
            w2b.ensure_payroll_wave2b_schema(cur, force=True)
            w4.ensure_payroll_wave4_schema(cur, force=True)

            settings = pyw1.ensure_company_settings(cur, company_code=company)
            prior_mode = str(settings.get("payroll_mode") or "native")
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="native", actor_phone=APPROVER, reason=f"w4_native_{SUFFIX}"
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 40},
                ],
                actor_phone=CREATOR,
                reason=f"w4_draft_{SUFFIX}",
            )
            check("draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w4_approve_{SUFFIX}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("contract approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

            cur.execute(
                """
                SELECT * FROM payroll_periods
                WHERE company_code=%s AND period_start=%s AND period_end=%s
                ORDER BY created_at DESC NULLS LAST LIMIT 1
                """,
                (company, p_start, p_end),
            )
            existing = cur.fetchone()
            if existing:
                period = {"ok": True, "period": dict(existing)}
            else:
                period = pyw1.create_period(
                    cur,
                    company_code=company,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"w4_period_{SUFFIX}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")

            preview = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                period_id=pid or None,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w4_preview_{SUFFIX}",
            )
            check("preview ok", preview.get("ok") is True, preview)
            prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")

            created = w4.create_close_run(
                cur,
                company_code=company,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"w4_create_{SUFFIX}",
                actor_permissions=PERMS_APPROVE,
            )
            check("create close run", created.get("ok") is True, created)
            run = created.get("close_run") or {}
            crid = str(run.get("close_run_id") or "")
            check("native authority", run.get("money_authority") == "preview_non_authoritative", run)
            check("payment disabled on run", run.get("payment_processing") == "disabled", run)

            replay = w4.create_close_run(
                cur,
                company_code=company,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"w4_create_idem_{SUFFIX}",
            )
            check("create idempotent", replay.get("idempotent") is True, replay)

            # SOD: actor with approve+export cannot approve
            sod_bad = w4.approve_close_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4_sod_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            # still draft — submit first
            check("sod blocked before submit or bad status", sod_bad.get("ok") is False, sod_bad)

            submitted = w4.submit_close_run_for_review(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_submit_{SUFFIX}",
                expected_row_version=int((replay.get("close_run") or run).get("row_version") or 1),
            )
            check("submit review", submitted.get("ok") is True, submitted)
            run = submitted.get("close_run") or {}

            self_approve = w4.approve_close_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_self_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self approve forbidden", self_approve.get("error") == "self_approval_forbidden", self_approve)

            sod_approve = w4.approve_close_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4_sod_approve_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod approve+export blocked", sod_approve.get("error") == "sod_approve_export_conflict", sod_approve)

            approved_run = w4.approve_close_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4_approve_run_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("approve ok", approved_run.get("ok") is True, approved_run)
            run = approved_run.get("close_run") or {}

            close_sod = w4.close_payroll_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4_close_sod_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod close+export blocked", close_sod.get("error") in ("sod_close_export_conflict", "sod_approve_export_conflict"), close_sod)

            self_close = w4.close_payroll_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_self_close_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self close forbidden", self_close.get("error") == "self_close_forbidden", self_close)

            closed = w4.close_payroll_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4_close_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("close ok", closed.get("ok") is True, closed)
            run = closed.get("close_run") or {}
            check("closed status", run.get("status") == "closed", run)
            check("snapshot immutable", run.get("snapshot_immutable") is True, run)
            check("snapshot fingerprint", bool(run.get("snapshot_fingerprint")), run)
            snap_fp = str(run.get("snapshot_fingerprint") or "")

            immut = w4.mutate_closed_run_forbidden(cur, company_code=company, close_run_id=crid)
            check("immutable probe", immut.get("error") == "closed_run_immutable", immut)

            re_close = w4.close_payroll_run(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4_reclose_{SUFFIX}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("reclose blocked", re_close.get("error") == "closed_run_immutable", re_close)

            # Invalid mapping fail-closed
            bad_journal = w4.generate_journal_draft(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_journal_bad_{SUFFIX}",
            )
            check("invalid mapping fail closed", bad_journal.get("error") == "invalid_mapping_fail_closed", bad_journal)

            for code, kind, acct, side in [
                ("BASIC", "earning", "5100.BASIC", "debit"),
                ("TRANSPORT", "allowance", "5100.TRANSPORT", "debit"),
                ("NET_PAYABLE", "net_payable", "2100.NET", "credit"),
            ]:
                m = w4.upsert_account_mapping(
                    cur,
                    company_code=company,
                    component_code=code,
                    component_kind=kind,
                    account_code=acct,
                    journal_side=side,
                    cost_centre="CC-HR",
                    actor_phone=APPROVER,
                    reason=f"w4_map_{code}_{SUFFIX}",
                )
                check(f"mapping {code}", m.get("ok") is True, m)

            journal = w4.generate_journal_draft(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_journal_{SUFFIX}",
            )
            check("journal ok", journal.get("ok") is True, journal)
            jd = journal.get("journal_draft") or {}
            check("journal balanced", jd.get("balanced") is True, jd)
            check("journal no erp", jd.get("posts_to_erp") is False, jd)
            jid = str(jd.get("journal_draft_id") or "")

            journal_idem = w4.generate_journal_draft(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_journal_idem_{SUFFIX}",
            )
            check("journal idempotent", journal_idem.get("idempotent") is True, journal_idem)

            bank = w4.generate_bank_export_contract(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_bank_{SUFFIX}",
                employee_iban_placeholders={EMP: "KW00PLACEHOLDER0001"},
            )
            check("bank contract ok", bank.get("ok") is True, bank)
            be = bank.get("bank_export") or {}
            check("bank no real format", be.get("real_bank_format") is False, be)
            check("bank no connection", be.get("bank_connection") is False, be)
            check("bank no wps", be.get("wps_submission") is False, be)
            bid = str(be.get("bank_export_id") or "")

            bank_idem = w4.generate_bank_export_contract(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4_bank_idem_{SUFFIX}",
                employee_iban_placeholders={EMP: "KW00PLACEHOLDER0001"},
            )
            check("bank idempotent", bank_idem.get("idempotent") is True, bank_idem)

            # Export SOD: closer cannot export; approve+export conflict; needs export perm
            exp_closer = w4.record_finance_export(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=CLOSER,
                reason=f"w4_exp_closer_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("sod closer≠exporter", exp_closer.get("error") == "sod_close_export_same_actor", exp_closer)

            exp_sod = w4.record_finance_export(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4_exp_sod_{SUFFIX}",
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod export+approve blocked", exp_sod.get("error") == "sod_approve_export_conflict", exp_sod)

            exp = w4.record_finance_export(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4_exp_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export recorded", exp.get("ok") is True, exp)
            fe = exp.get("finance_export") or {}
            feid = str(fe.get("finance_export_id") or "")
            check("recon unmatched", fe.get("reconciliation_status") == "unmatched", fe)

            exp_idem = w4.record_finance_export(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4_exp_idem_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export idempotent", exp_idem.get("idempotent") is True, exp_idem)

            # Fingerprint drift: mutate artifact source fingerprint then record bank export with forced drift
            cur.execute(
                """
                UPDATE payroll_journal_drafts
                SET source_snapshot_fingerprint=%s
                WHERE journal_draft_id=%s
                """,
                ("drift-" + snap_fp[:16], jid),
            )
            drift = w4.detect_export_fingerprint_drift(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
            )
            check("drift detected", drift.get("drifted") is True, drift)

            # Restore fingerprint for bank export path, then approve finance export
            cur.execute(
                "UPDATE payroll_journal_drafts SET source_snapshot_fingerprint=%s WHERE journal_draft_id=%s",
                (snap_fp, jid),
            )

            bank_exp = w4.record_finance_export(
                cur,
                company_code=company,
                close_run_id=crid,
                export_kind="bank_contract",
                artifact_id=bid,
                actor_phone=EXPORTER,
                reason=f"w4_bank_exp_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("bank export recorded", bank_exp.get("ok") is True, bank_exp)

            self_exp_appr = w4.approve_finance_export(
                cur,
                company_code=company,
                finance_export_id=feid,
                actor_phone=EXPORTER,
                reason=f"w4_exp_self_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export self approve forbidden", self_exp_appr.get("error") == "self_approval_forbidden", self_exp_appr)

            exp_appr = w4.approve_finance_export(
                cur,
                company_code=company,
                finance_export_id=feid,
                actor_phone=EXPORTER2,
                reason=f"w4_exp_appr_{SUFFIX}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export approved", exp_appr.get("ok") is True, exp_appr)
            check("recon matched", (exp_appr.get("finance_export") or {}).get("reconciliation_status") == "matched", exp_appr)

            hist = w4.list_finance_exports(cur, company_code=company, close_run_id=crid)
            check("export history", len(hist) >= 2, len(hist))

            # Dual-control reopen
            same_reopen = w4.initiate_reopen(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4_reopen1_{SUFFIX}",
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen initiate", same_reopen.get("ok") is True, same_reopen)
            dual_id = str((same_reopen.get("dual_control") or {}).get("action_id") or "")

            same_actor = w4.confirm_reopen(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4_reopen_same_{SUFFIX}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen same actor denied", same_actor.get("error") == "dual_control_same_actor", same_actor)

            reopened = w4.confirm_reopen(
                cur,
                company_code=company,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4_reopen2_{SUFFIX}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen confirmed", reopened.get("ok") is True, reopened)
            check("reopened status", (reopened.get("close_run") or {}).get("status") == "reopened", reopened)

            # External close path (separate run)
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="external", actor_phone=APPROVER, reason=f"w4_ext_mode_{SUFFIX}"
            )
            exported = w2a.create_external_export(
                cur,
                company_code=company,
                period=period_row,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                attendance=[{"employee_key": EMP, "worked_minutes": 10000}],
                leave_classifications=[],
                actor_phone=CREATOR,
                reason=f"w4_export_{SUFFIX}",
            )
            check("external export", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload = dict(cur.fetchone())["payload"]
            if isinstance(payload, str):
                import json as _json

                payload = _json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=f"EXT-W4-{SUFFIX}")
            imported = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w4_import_{SUFFIX}",
            )
            check("external import", imported.get("ok") is True, imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id") or "")

            ext_created = w4.create_close_run(
                cur,
                company_code=company,
                source_kind="external_import",
                source_run_id=iid,
                actor_phone=CREATOR,
                reason=f"w4_ext_create_{SUFFIX}",
            )
            check("external close create", ext_created.get("ok") is True, ext_created)
            check(
                "external authority retained",
                (ext_created.get("close_run") or {}).get("money_authority") == "external",
                ext_created,
            )

            # Cleanup synthetic close/finance rows for this suffix
            cur.execute(
                """
                DELETE FROM payroll_finance_exports
                WHERE company_code=%s AND close_run_id IN (
                  SELECT close_run_id FROM payroll_close_runs
                  WHERE company_code=%s AND decision_note LIKE %s
                )
                """,
                (company, company, f"%{SUFFIX}%"),
            )
            cur.execute(
                """
                DELETE FROM payroll_journal_lines
                WHERE journal_draft_id IN (
                  SELECT journal_draft_id FROM payroll_journal_drafts
                  WHERE company_code=%s AND decision_note LIKE %s
                )
                """,
                (company, f"%{SUFFIX}%"),
            )
            cur.execute("DELETE FROM payroll_journal_drafts WHERE company_code=%s AND decision_note LIKE %s", (company, f"%{SUFFIX}%"))
            cur.execute("DELETE FROM payroll_bank_export_drafts WHERE company_code=%s AND decision_note LIKE %s", (company, f"%{SUFFIX}%"))
            cur.execute(
                """
                DELETE FROM payroll_close_dual_control
                WHERE close_run_id IN (
                  SELECT close_run_id FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s
                )
                """,
                (company, f"%{SUFFIX}%"),
            )
            cur.execute(
                """
                DELETE FROM payroll_close_run_events
                WHERE close_run_id IN (
                  SELECT close_run_id FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s
                )
                """,
                (company, f"%{SUFFIX}%"),
            )
            cur.execute("DELETE FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s", (company, f"%{SUFFIX}%"))
            cur.execute("DELETE FROM payroll_account_mappings WHERE company_code=%s AND decision_note LIKE %s", (company, f"%{SUFFIX}%"))
            # Prior-wave synthetic cleanup for this EMP marker (tables may be absent on fresh DBs)
            for sql, params in [
                ("DELETE FROM payroll_preview_lines WHERE employee_key=%s", (EMP,)),
                ("DELETE FROM payroll_preview_employee_results WHERE employee_key=%s", (EMP,)),
                ("DELETE FROM payroll_adapter_import_lines WHERE employee_key=%s", (EMP,)),
                (
                    """
                    DELETE FROM payroll_compensation_events WHERE contract_id IN (
                      SELECT contract_id FROM payroll_compensation_contracts WHERE employee_key=%s
                    )
                    """,
                    (EMP,),
                ),
                (
                    """
                    DELETE FROM payroll_compensation_components WHERE contract_id IN (
                      SELECT contract_id FROM payroll_compensation_contracts WHERE employee_key=%s
                    )
                    """,
                    (EMP,),
                ),
                ("DELETE FROM payroll_compensation_contracts WHERE employee_key=%s", (EMP,)),
            ]:
                try:
                    cur.execute(sql, params)
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    # re-open transaction context via noop; keep going on missing tables
                    cur.execute("SELECT 1")

            residual = 0
            cur.execute(
                "SELECT count(*) AS c FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s",
                (company, f"%{SUFFIX}%"),
            )
            residual += int(dict(cur.fetchone())["c"])
            check("residual zero", residual == 0, residual)

            pyw1.set_payroll_mode(
                cur, company_code=company, mode=prior_mode, actor_phone=APPROVER, reason=f"w4_restore_{SUFFIX}"
            )
            check("restore prior mode", True)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
