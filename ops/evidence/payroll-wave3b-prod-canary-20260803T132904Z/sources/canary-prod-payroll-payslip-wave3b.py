#!/usr/bin/env python3
"""Payroll Wave 3-B — production synthetic payslip canary.

Synthetic subjects only (PYW1/PYW3/W3B · 965541*).
Proves: native preview payslips, external imported payslips,
permissions/scope, EN/AR download, replace/revoke/history,
idempotency, residual cleanup.

Does NOT: bank/WPS, PIFSS, EOS, journals, payments, AI.
Native payslips non-authoritative; external remains money authority.
payment_processing=disabled.
"""
from __future__ import annotations

import calendar
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
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY", "1")
os.environ.setdefault(
    "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS",
    "PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402
import payroll_native_preview_wave2b as w2b  # noqa: E402
import payroll_payslip_wave3 as w3  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW3B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-PYW3-W3B-{TAG}"
REAL_KEY = "WATHEFNI-96566363363"
CREATOR = f"9655417{TAG_DIGITS}"
APPROVER = f"9655418{TAG_DIGITS}"

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW3B_EVID") or f"/tmp/payroll-w3b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER},
    "payslip_ids": [],
    "preview_run_ids": [],
    "import_run_ids": [],
    "export_run_ids": [],
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
    year = 2030 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def cleanup(cur) -> dict[str, int]:
    deleted: dict[str, int] = {}
    cur.execute(
        "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    pids = [dict(r)["payslip_id"] for r in cur.fetchall()]
    if pids:
        cur.execute("DELETE FROM payroll_payslip_lines WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslip_lines"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslip_events"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslips"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_payslip_events WHERE company_code=%s AND payload::text LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    deleted["orphan_events"] = cur.rowcount or 0

    cur.execute(
        "SELECT preview_run_id::text FROM payroll_preview_runs WHERE company_code=%s AND (decision_note LIKE %s OR inputs::text LIKE %s)",
        (COMPANY, f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    prids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
    if prids:
        cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
        cur.execute("DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)", (prids,))
        cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
        cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_runs"] = cur.rowcount or 0

    cur.execute(
        "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
    if iids:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
        cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
        cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
        cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["imports"] = cur.rowcount or 0
    cur.execute(
        "SELECT export_run_id::text FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
    if eids:
        cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
        cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["exports"] = cur.rowcount or 0

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
    period_ids = [dict(r)["period_id"] for r in cur.fetchall()]
    if period_ids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        cur.execute(
            "DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        deleted["periods"] = cur.rowcount or 0
    return deleted


def residual(cur) -> int:
    n = 0
    for sql, args in (
        ("SELECT COUNT(*) AS n FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_KEY)),
        ("SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_KEY)),
        (
            "SELECT COUNT(*) AS n FROM payroll_preview_runs WHERE company_code=%s AND (decision_note LIKE %s OR inputs::text LIKE %s)",
            (COMPANY, f"%{TAG}%", f"%{EMP_KEY}%"),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, f"%{TAG}%"),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, f"%{TAG}%"),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, f"%{TAG}%"),
        ),
    ):
        cur.execute(sql, args)
        n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave3b prod synthetic canary tag={TAG}")
    h = w3.honesty_payload()
    check("wave3 enabled", w3.payroll_wave3_enabled())
    check("synthetic only", w3.payroll_wave3_synthetic_only())
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("not money", h.get("payslips_as_money") is False)
    check("native non-auth", h.get("native_payslips_authoritative") is False)
    check("external authority", h.get("external_payslips_authority") == "external")
    check("no AI", h.get("ai_calculations") is False)
    check("no bank", h.get("bank_files") is False)
    check("wave1 enabled", pyw1.payroll_wave1_enabled())
    check("wave2a enabled synthetic", w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only())
    check("wave2b enabled synthetic", w2b.payroll_wave2b_enabled() and w2b.payroll_wave2b_synthetic_only())
    check("history never deleted", w3.freeze_invariants().get("history_never_deleted") is True)

    # EN/AR + mobile UX static
    ux_paths = [
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
        ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "posthire",
    ]
    posthire = next((p for p in ux_paths if (p / "payrollPayslipUx.ts").exists()), None)
    check("ux sources present", posthire is not None, ux_paths)
    if posthire:
        ux = (posthire / "payrollPayslipUx.ts").read_text(encoding="utf-8")
        ws = (posthire / "PayslipWorkspace.tsx").read_text(encoding="utf-8")
        ph = (posthire / "PostHire.tsx").read_text(encoding="utf-8")
        check("ux EN title", "Payslips" in ux)
        check("ux AR title", "قسائم الراتب" in ux)
        check("ux honesty", "non-authoritative" in ux.lower())
        check("ux payment disabled", "Payment processing: disabled" in ux)
        check("ux mobile", "md:hidden" in ws and "mobileHint" in ux)
        check("ux rtl", "rtl" in ws)
        check("ux posthire tab", "payslips" in ph and "PayslipWorkspace" in ph)

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
            check("settings payment disabled", settings.get("payment_processing") == "disabled")

            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"w3b_native_{TAG}"
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50},
                ],
                actor_phone=CREATOR,
                reason=f"w3b_draft_{TAG}",
            )
            check("draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id") or "")
            IDS["contract_ids"].append(cid)
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w3b_approve_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

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
                period = {"ok": True, "period": dict(existing)}
            else:
                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"w3b_period_{TAG}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")
            if pid:
                IDS["period_ids"].append(pid)

            preview = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                period_id=pid or None,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w3b_preview_{TAG}",
            )
            check("preview ok", preview.get("ok") is True, preview)
            prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
            IDS["preview_run_ids"].append(prid)

            gen = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_native_slip_{TAG}",
            )
            check("native payslip ok", gen.get("ok") is True, gen)
            slip = gen.get("payslip") or {}
            check("native money authority preview", slip.get("money_authority") == "preview_non_authoritative", slip)
            check("native payment disabled", slip.get("payment_processing") == "disabled", slip)
            sid = str(slip.get("payslip_id") or "")
            IDS["payslip_ids"].append(sid)

            replay = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_native_idem_{TAG}",
            )
            check("native idempotent", replay.get("idempotent") is True, replay)

            scope_denied = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_scope_{TAG}",
                allowed_employee_keys={"OTHER-KEY"},
            )
            check("scope denied", scope_denied.get("error") == "employee_outside_manager_scope", scope_denied)

            real_denied = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=REAL_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_real_{TAG}",
            )
            check("real refused", real_denied.get("error") == "payroll_wave3_synthetic_only", real_denied)

            replaced = w3.replace_payslip(
                cur,
                company_code=COMPANY,
                payslip_id=sid,
                actor_phone=APPROVER,
                reason=f"w3b_replace_{TAG}",
            )
            check("replace ok", replaced.get("ok") is True, replaced)
            new_id = str((replaced.get("payslip") or {}).get("payslip_id") or "")
            IDS["payslip_ids"].append(new_id)
            check("replace version 2", int((replaced.get("payslip") or {}).get("version_number") or 0) == 2, replaced)
            check("prior replaced", (replaced.get("replaced_payslip") or {}).get("status") == "replaced", replaced)
            hist = w3.list_payslip_history(cur, company_code=COMPANY, employee_key=EMP_KEY)
            check("history after replace", len(hist) >= 2, len(hist))

            dl_en = w3.download_payslip_document(cur, company_code=COMPANY, payslip_id=new_id, locale="en")
            check("download EN", dl_en.get("ok") is True and "Preview only" in str(dl_en.get("body") or ""), dl_en)
            dl_ar = w3.download_payslip_document(cur, company_code=COMPANY, payslip_id=new_id, locale="ar")
            check("download AR", dl_ar.get("ok") is True and "معاينة" in str(dl_ar.get("body") or ""), dl_ar)

            # External path
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w3b_ext_mode_{TAG}"
            )
            exported = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=period_row,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                attendance=[{"employee_key": EMP_KEY, "worked_minutes": 10000}],
                leave_classifications=[],
                actor_phone=CREATOR,
                reason=f"w3b_export_{TAG}",
            )
            check("external export", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
            IDS["export_run_ids"].append(eid)
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload = dict(cur.fetchone())["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=f"EXT-W3B-{TAG}")
            imported = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w3b_import_{TAG}",
            )
            check("external import", imported.get("ok") is True, imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id") or "")
            IDS["import_run_ids"].append(iid)

            ext = w3.generate_external_payslip(
                cur,
                company_code=COMPANY,
                import_run_id=iid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_ext_slip_{TAG}",
            )
            check("external payslip ok", ext.get("ok") is True, ext)
            eslip = ext.get("payslip") or {}
            check("external money authority", eslip.get("money_authority") == "external", eslip)
            check("external authoritative label", eslip.get("authoritative_label") == "external", eslip)
            eid_slip = str(eslip.get("payslip_id") or "")
            IDS["payslip_ids"].append(eid_slip)

            ext_replay = w3.generate_external_payslip(
                cur,
                company_code=COMPANY,
                import_run_id=iid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"w3b_ext_idem_{TAG}",
            )
            check("external idempotent", ext_replay.get("idempotent") is True, ext_replay)

            revoked = w3.revoke_payslip(
                cur,
                company_code=COMPANY,
                payslip_id=new_id,
                actor_phone=APPROVER,
                reason=f"w3b_revoke_{TAG}",
            )
            check("revoke ok", revoked.get("ok") is True, revoked)
            check("revoke status", (revoked.get("payslip") or {}).get("status") == "revoked", revoked)
            hist2 = w3.list_payslip_history(cur, company_code=COMPANY, employee_key=EMP_KEY)
            check("history after revoke", any(str(r.get("status")) == "revoked" for r in hist2), hist2)
            check("no hard delete", all(str(r.get("payslip_id") or "") for r in hist2))

            events = w3.list_payslip_events(cur, company_code=COMPANY, limit=30)
            check("audit events", len(events) >= 1, len(events))

            restore = IDS["prior_mode"] if IDS["prior_mode"] in ("native", "external", "parallel_shadow") else "external"
            restored = pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode=restore, actor_phone=APPROVER, reason=f"w3b_restore_{TAG}"
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
        "wave": "3-B",
        "payslips_as_money": False,
        "native_payslips_authoritative": False,
        "external_payslips_authority": "external",
        "payment_processing": "disabled",
        "ai_calculations": False,
        "bank_files": False,
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("QUALIFICATION_JSON", EVID / "qualification.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
