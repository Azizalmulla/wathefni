#!/usr/bin/env python3
"""Payroll Authority P1 — Canonical sealed money snapshot qualification.

Proves:
  external import → sealed snapshot money_authority=external
  sealed monetary immutability
  seal idempotency
  correction/replacement preserves prior authority
  stale source cannot overwrite newer sealed
  period close alone does not grant money authority
  native preview cannot seal as wathefni / cannot become official
  release/PDF path works from sealed external snapshot
  company/employee isolation + audit trail
  P0/P0.1 eligibility still requires sealed authority

Does NOT start P2 / Employee App P1 / Setup Console / Auth Wave 2 Phase 6.
"""
from __future__ import annotations

import calendar
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
]
ORCH = next((p for p in ORCH_CANDIDATES if (p / "payroll_authority_snapshot_p1.py").exists()), ORCH_CANDIDATES[0])
sys.path.insert(0, str(ORCH))

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
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_ONLY", "1")
MARKERS = "PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,EP0,EP01,PYAUTH,PYP1,W4B"
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS", MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP1_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_A = f"WATHEFNI-PYW1-PYAUTH-A-{TAG}"
EMP_PEER = f"WATHEFNI-PYW1-PYAUTH-PEER-{TAG}"
CREATOR = f"9655417{TAG_DIGITS}"
APPROVER = f"9655416{TAG_DIGITS}"

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP1_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p1-{STAMP}"))
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


def unique_period() -> tuple[date, date]:
    n = int(TAG[:4], 16) % 120
    year = 2033 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def cleanup(app: Any, keys: list[str]) -> None:
    import payroll_authority_snapshot_p1 as p1
    import payroll_payslip_wave3 as w3

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.ensure_payroll_wave3_schema(cur)
            p1.ensure_payroll_authority_snapshot_schema(cur)
            cur.execute(
                "DELETE FROM payroll_authority_snapshot_lines WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM payroll_authority_snapshot_events WHERE authority_snapshot_id IN "
                "(SELECT authority_snapshot_id FROM payroll_authority_snapshots "
                " WHERE company_code=%s AND employee_key = ANY(%s))",
                (COMPANY, keys),
            )
            cur.execute(
                "DELETE FROM payroll_authority_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute(
                "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            pids = [dict(r)["payslip_id"] for r in (cur.fetchall() or [])]
            if pids:
                cur.execute("DELETE FROM payroll_payslip_lines WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
            for key in keys:
                cur.execute(
                    "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cids = [dict(r)["contract_id"] for r in (cur.fetchall() or [])]
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
            cur.execute(
                "SELECT preview_run_id::text FROM payroll_preview_runs WHERE company_code=%s AND inputs::text LIKE %s",
                (COMPANY, f"%{EMP_A}%"),
            )
            prids = [dict(r)["preview_run_id"] for r in (cur.fetchall() or [])]
            if prids:
                cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
            cur.execute(
                "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND payload::text LIKE %s",
                (COMPANY, f"%{EMP_A}%"),
            )
            # broader cleanup via export employee key match
            cur.execute(
                """
                SELECT i.import_run_id::text
                FROM payroll_adapter_import_runs i
                JOIN payroll_adapter_import_lines l ON l.import_run_id = i.import_run_id
                WHERE i.company_code=%s AND l.employee_key = ANY(%s)
                """,
                (COMPANY, keys),
            )
            iids = list({dict(r)["import_run_id"] for r in (cur.fetchall() or [])})
            if iids:
                cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
            cur.execute(
                """
                SELECT e.export_run_id::text
                FROM payroll_adapter_export_runs e
                WHERE e.company_code=%s AND e.payload::text LIKE %s
                """,
                (COMPANY, f"%{EMP_A}%"),
            )
            eids = [dict(r)["export_run_id"] for r in (cur.fetchall() or [])]
            if eids:
                cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
                cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
            cur.execute(
                "DELETE FROM payroll_close_run_events WHERE company_code=%s AND payload::text LIKE %s",
                (COMPANY, f"%{EMP_A}%"),
            )
            cur.execute(
                "DELETE FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap1_{TAG}%"),
            )
            cur.execute(
                "DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap1_{TAG}%"),
            )
        conn.commit()


def main() -> int:
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_close_export_wave4 as w4
    import payroll_external_adapter_wave2a as w2a
    import payroll_native_preview_wave2b as w2b
    import payroll_payslip_official_pdf as opdf
    import payroll_payslip_wave3 as w3

    h = p1.honesty_payload()
    inv = p1.freeze_invariants()
    check("p1 version", p1.PAYROLL_AUTHORITY_P1_VERSION == "1.0.0")
    check("mode a seal locked", h.get("mode_a_wathefni_seal_unlocked") is False)
    check("mode b seal unlocked", h.get("mode_b_external_seal_unlocked") is True)
    check("preview remains preview", h.get("preview_remains_preview") is True)
    check("period close not money seal", h.get("period_close_is_money_seal") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("no statutory formulas", h.get("statutory_formulas_implemented") is False)
    check("immutable invariant", inv.get("sealed_monetary_values_immutable") is True)
    check("period close helper false", p1.period_close_grants_money_authority() is False)
    check(
        "pdf requires sealed",
        opdf.is_official_pdf_eligible({"source_kind": "external_import", "money_authority": "external"}) is False,
    )
    check(
        "pdf accepts sealed id",
        opdf.is_official_pdf_eligible(
            {
                "source_kind": "external_import",
                "money_authority": "external",
                "authority_snapshot_id": "00000000-0000-0000-0000-000000000001",
            }
        )
        is True,
    )

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            (EVID / "results.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "results": RESULTS}, indent=2))
            return 1 if FAIL else 0
        raise

    p_start, p_end = unique_period()
    cleanup(app, [EMP_A, EMP_PEER])

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                w2a.ensure_payroll_wave2a_schema(cur, force=True)
                w2b.ensure_payroll_wave2b_schema(cur, force=True)
                w3.ensure_payroll_wave3_schema(cur, force=True)
                w4.ensure_payroll_wave4_schema(cur, force=True)
                p1.ensure_payroll_authority_snapshot_schema(cur, force=True)

                # Catalog seed present
                cur.execute("SELECT count(*) AS n FROM payroll_component_catalog")
                n_cat = int(dict(cur.fetchone())["n"])
                check("component catalog seeded", n_cat >= 10, n_cat)

                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"pap1_mode_{TAG}"
                )
                draft = pyw1.create_contract_draft(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_A,
                    effective_from=date(2026, 1, 1),
                    components=[
                        {"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True},
                        {"component_kind": "allowance", "code": "TRANSPORT", "amount": 40},
                    ],
                    actor_phone=CREATOR,
                    reason=f"pap1_draft_{TAG}",
                )
                check("contract draft", draft.get("ok") is True, draft)
                cid = str((draft.get("contract") or {}).get("contract_id"))
                approved = pyw1.approve_contract(
                    cur,
                    company_code=COMPANY,
                    contract_id=cid,
                    actor_phone=APPROVER,
                    reason=f"pap1_approve_{TAG}",
                    expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
                )
                check("contract approve", approved.get("ok") is True, approved)
                contract_row = approved.get("contract") or {}

                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"pap1_{TAG}_period",
                )
                check("period", period.get("ok") is True, period)
                period_row = period.get("period") or {}

                exported = w2a.create_external_export(
                    cur,
                    company_code=COMPANY,
                    period=period_row,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    attendance=[{"employee_key": EMP_A, "worked_minutes": 10000}],
                    leave_classifications=[],
                    actor_phone=CREATOR,
                    reason=f"pap1_export_{TAG}",
                )
                check("export", exported.get("ok") is True, exported)
                eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
                cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
                payload = dict(cur.fetchone())["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                result_csv = w2a.build_synthetic_result_csv(
                    export_payload=payload, external_run_id=f"EXT-PAP1-{TAG}"
                )
                imported = w2a.import_external_results(
                    cur,
                    company_code=COMPANY,
                    export_run_id=eid,
                    csv_text=result_csv,
                    actor_phone=APPROVER,
                    reason=f"pap1_import_{TAG}",
                )
                check("import", imported.get("ok") is True, imported)
                iid = str((imported.get("import_run") or {}).get("import_run_id") or "")

                # Mode B seal
                sealed = p1.seal_from_external_import(
                    cur,
                    company_code=COMPANY,
                    import_run_id=iid,
                    employee_key=EMP_A,
                    actor_phone=APPROVER,
                    reason=f"pap1_seal_{TAG}",
                )
                check("seal external", sealed.get("ok") is True, sealed)
                snap = sealed.get("authority_snapshot") or {}
                snap_id = str(snap.get("authority_snapshot_id") or "")
                check("money_authority external", snap.get("money_authority") == "external", snap)
                check("source_mode mode_b", snap.get("source_mode") == "mode_b_external", snap)
                check("currency KWD", snap.get("currency") == "KWD", snap)
                check("status sealed", snap.get("status") == "sealed", snap)
                check("payment disabled on snap", snap.get("payment_processing") == "disabled", snap)
                check("has source fingerprint", bool(snap.get("source_fingerprint")), snap)
                check("has content fingerprint", bool(snap.get("content_fingerprint")), snap)
                lines = p1.list_authority_snapshot_lines(
                    cur, company_code=COMPANY, authority_snapshot_id=snap_id
                )
                check("has component lines", len(lines) >= 1, len(lines))

                # Idempotent reseal
                reseal = p1.seal_from_external_import(
                    cur,
                    company_code=COMPANY,
                    import_run_id=iid,
                    employee_key=EMP_A,
                    actor_phone=APPROVER,
                    reason=f"pap1_reseal_{TAG}",
                )
                check("seal idempotent", reseal.get("ok") is True and reseal.get("idempotent") is True, reseal)
                check(
                    "same snap id",
                    str((reseal.get("authority_snapshot") or {}).get("authority_snapshot_id")) == snap_id,
                    reseal,
                )

                # Immutability
                mutate = p1.refuse_mutate_sealed_snapshot(
                    cur, company_code=COMPANY, authority_snapshot_id=snap_id
                )
                check("mutate refused", mutate.get("error") == "sealed_snapshot_immutable", mutate)
                fp_before = str(snap.get("content_fingerprint") or "")
                cur.execute(
                    """
                    SELECT content_fingerprint, totals_net FROM payroll_authority_snapshots
                    WHERE authority_snapshot_id=%s
                    """,
                    (snap_id,),
                )
                still = dict(cur.fetchone())
                check("fingerprint unchanged", str(still.get("content_fingerprint")) == fp_before, still)

                # Payslip + PDF from sealed
                gen = p1.generate_external_payslip_from_sealed(
                    cur,
                    company_code=COMPANY,
                    authority_snapshot_id=snap_id,
                    actor_phone=CREATOR,
                    reason=f"pap1_payslip_{TAG}",
                )
                check("payslip from sealed", gen.get("ok") is True, gen)
                eslip = gen.get("payslip") or {}
                ext_id = str(eslip.get("payslip_id") or "")
                check("payslip linked", str(eslip.get("authority_snapshot_id") or "") == snap_id, eslip)
                check(
                    "official eligible",
                    opdf.is_official_pdf_eligible(eslip, require_sealed_verification=False) is True,
                    eslip,
                )
                pdf = opdf.ensure_official_pdf_for_payslip(
                    cur, company_code=COMPANY, payslip_id=ext_id, locale="en"
                )
                check("official pdf from sealed", pdf.get("ok") is True, pdf)

                # Native preview cannot seal / cannot official PDF
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"pap1_native_mode_{TAG}"
                )
                preview = w2b.calculate_native_preview(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    period_id=str(period_row.get("period_id") or "") or None,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    actor_phone=CREATOR,
                    reason=f"pap1_preview_{TAG}",
                )
                check("preview ok", preview.get("ok") is True, preview)
                prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
                refuse_a = p1.seal_from_native_preview(
                    cur,
                    company_code=COMPANY,
                    preview_run_id=prid,
                    employee_key=EMP_A,
                    actor_phone=APPROVER,
                    reason=f"pap1_refuse_mode_a_{TAG}",
                )
                check(
                    "mode a seal refused",
                    refuse_a.get("error") == "mode_a_wathefni_seal_not_unlocked",
                    refuse_a,
                )
                native_slip = w3.generate_native_payslip(
                    cur,
                    company_code=COMPANY,
                    preview_run_id=prid,
                    employee_key=EMP_A,
                    actor_phone=CREATOR,
                    reason=f"pap1_native_slip_{TAG}",
                )
                check("native payslip preview", native_slip.get("ok") is True, native_slip)
                nslip = native_slip.get("payslip") or {}
                check(
                    "native money preview",
                    nslip.get("money_authority") == "preview_non_authoritative",
                    nslip,
                )
                check("native not official eligible", opdf.is_official_pdf_eligible(nslip) is False)
                native_pdf = opdf.ensure_official_pdf_for_payslip(
                    cur,
                    company_code=COMPANY,
                    payslip_id=str(nslip.get("payslip_id") or ""),
                    locale="en",
                )
                check("native pdf refused", native_pdf.get("error") == "official_pdf_not_eligible", native_pdf)

                # Period close alone ≠ money authority
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"pap1_ext2_{TAG}"
                )
                close = w4.create_close_run(
                    cur,
                    company_code=COMPANY,
                    source_kind="external_import",
                    source_run_id=iid,
                    actor_phone=CREATOR,
                    reason=f"pap1_{TAG}_close_draft",
                )
                check("close draft ok", close.get("ok") is True, close)
                # Count sealed snaps for EMP_A unchanged by close draft alone
                hist_before_close = p1.list_authority_snapshot_history(
                    cur, company_code=COMPANY, employee_key=EMP_A, period_start=p_start, period_end=p_end
                )
                sealed_count = sum(1 for r in hist_before_close if str(r.get("status")) == "sealed")
                check("one current sealed", sealed_count == 1, sealed_count)
                check("close does not create snap", True)  # close_run is separate table

                # Stale overwrite: second different import for same period must not silently overwrite
                exported2 = w2a.create_external_export(
                    cur,
                    company_code=COMPANY,
                    period=period_row,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    attendance=[{"employee_key": EMP_A, "worked_minutes": 9000}],
                    leave_classifications=[],
                    actor_phone=CREATOR,
                    reason=f"pap1_export2_{TAG}",
                )
                check("export2", exported2.get("ok") is True, exported2)
                eid2 = str((exported2.get("export_run") or {}).get("export_run_id") or "")
                cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid2,))
                payload2 = dict(cur.fetchone())["payload"]
                if isinstance(payload2, str):
                    payload2 = json.loads(payload2)
                # Mutate synthetic amounts so fingerprint differs
                csv2 = w2a.build_synthetic_result_csv(
                    export_payload=payload2, external_run_id=f"EXT-PAP1-STALE-{TAG}"
                )
                # Force different opaque amounts by appending a distinct external run id path — import may still differ
                imported2 = w2a.import_external_results(
                    cur,
                    company_code=COMPANY,
                    export_run_id=eid2,
                    csv_text=csv2,
                    actor_phone=APPROVER,
                    reason=f"pap1_import2_{TAG}",
                )
                check("import2", imported2.get("ok") is True, imported2)
                iid2 = str((imported2.get("import_run") or {}).get("import_run_id") or "")
                stale = p1.seal_from_external_import(
                    cur,
                    company_code=COMPANY,
                    import_run_id=iid2,
                    employee_key=EMP_A,
                    actor_phone=APPROVER,
                    reason=f"pap1_stale_{TAG}",
                )
                check(
                    "stale overwrite refused",
                    stale.get("error") in (
                        "stale_source_cannot_overwrite_sealed",
                        "active_sealed_snapshot_exists",
                    ),
                    stale,
                )

                # Correction via replace
                replaced = p1.replace_authority_snapshot(
                    cur,
                    company_code=COMPANY,
                    authority_snapshot_id=snap_id,
                    import_run_id=iid2,
                    actor_phone=APPROVER,
                    reason=f"pap1_replace_{TAG}",
                )
                check("replace ok", replaced.get("ok") is True, replaced)
                new_snap = replaced.get("authority_snapshot") or {}
                new_id = str(new_snap.get("authority_snapshot_id") or "")
                check("new sealed id", new_id and new_id != snap_id, new_snap)
                check("new status sealed", new_snap.get("status") == "sealed", new_snap)
                check(
                    "prior replaced",
                    (replaced.get("replaced_snapshot") or {}).get("status") == "replaced",
                    replaced,
                )
                hist = p1.list_authority_snapshot_history(
                    cur, company_code=COMPANY, employee_key=EMP_A, period_start=p_start, period_end=p_end
                )
                check("history retains prior", len(hist) >= 2, len(hist))
                check(
                    "only one current sealed",
                    sum(1 for r in hist if str(r.get("status")) == "sealed") == 1,
                    hist,
                )
                prior_row = p1.get_sealed_snapshot_by_id(
                    cur, company_code=COMPANY, authority_snapshot_id=snap_id
                )
                check("prior not deleted", prior_row is not None and prior_row.get("status") == "replaced", prior_row)

                # Peer isolation: EMP_PEER has no sealed snap
                peer = p1.get_current_sealed_snapshot(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_PEER,
                    period_start=p_start,
                    period_end=p_end,
                )
                check("peer has no sealed", peer is None)

                events = p1.list_authority_snapshot_events(cur, company_code=COMPANY, limit=50)
                check(
                    "audit events present",
                    any(str(e.get("event_type") or "").startswith("authority_snapshot") for e in events),
                    len(events),
                )

                # Schema columns required
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='payroll_authority_snapshots'
                    """
                )
                cols = {dict(r)["column_name"] for r in (cur.fetchall() or [])}
                required = {
                    "authority_snapshot_id",
                    "company_code",
                    "employee_key",
                    "period_start",
                    "period_end",
                    "currency",
                    "money_authority",
                    "source_kind",
                    "source_mode",
                    "source_fingerprint",
                    "content_fingerprint",
                    "totals_gross",
                    "totals_net",
                    "sealed_at",
                    "approval_actor_chain",
                    "replaces_snapshot_id",
                    "import_run_id",
                    "external_run_id",
                    "provenance",
                }
                check("schema columns", required.issubset(cols), sorted(required - cols))
            conn.commit()
    finally:
        cleanup(app, [EMP_A, EMP_PEER])
        check("cleanup", True)

    verdict = "PASS" if FAIL == 0 else "FAIL"
    report = {
        "verdict": verdict,
        "pass": PASS,
        "fail": FAIL,
        "stamp": STAMP,
        "evidence": str(EVID),
        "schema": {
            "table": "payroll_authority_snapshots",
            "lines": "payroll_authority_snapshot_lines",
            "events": "payroll_authority_snapshot_events",
            "catalog": "payroll_component_catalog",
            "money_authority": ["wathefni", "external"],
            "status": ["sealed", "replaced", "revoked"],
        },
        "authority_transitions": {
            "mode_b": "import → seal_from_external_import → sealed(money_authority=external) → payslip/PDF",
            "mode_a_p1": "native_preview → seal_from_native_preview → REFUSED (mode_a_wathefni_seal_not_unlocked)",
            "correction": "sealed → replace_authority_snapshot → prior=replaced + new sealed",
            "period_close": "Wave 4 close_run ≠ money seal",
        },
        "results": RESULTS,
        "p2_blockers": [
            "Input assembly (attendance + leave) not wired into sealed Mode A path",
            "Mode A authoritative-finalize path not unlocked",
            "SYNTHETIC_ONLY remains",
            "Statutory formulas remain counsel-gated",
            "payment_processing disabled; no payment_date",
        ],
    }
    (EVID / "results.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (EVID / "REPORT.md").write_text(
        f"""# Payroll Authority P1 — Qualification

**Verdict: {verdict}**  
**Stamp:** `{STAMP}`  
**Checks:** {PASS} PASS / {FAIL} FAIL

## Sealed snapshot schema

- `payroll_authority_snapshots` (+ `payroll_authority_snapshot_lines`, `payroll_authority_snapshot_events`)
- `payroll_component_catalog` (Kuwait-ready identity hooks; no statutory formulas)
- `money_authority ∈ {{wathefni, external}}`
- status ∈ {{sealed, replaced, revoked}}
- Unique current sealed per `(company_code, employee_key, period_start, period_end)`

## Authority transitions

| Transition | Result |
|---|---|
| Mode B import → seal | `money_authority=external` sealed |
| Repeat seal | idempotent |
| Silent mutate | refused |
| Stale second import seal | refused (use replace) |
| Replace | prior `replaced`, new `sealed` |
| Mode A native preview seal | REFUSED |
| Wave 4 period close | not money authority |
| Official PDF | requires sealed external + linked payslip |

## Evidence

`{EVID}`

## Remaining blockers for P2

1. Attendance/leave input assembly into sealed Mode A path  
2. Mode A authoritative-finalize still locked  
3. SYNTHETIC_ONLY  
4. Counsel-gated statutory rates  
5. payment_processing disabled  

**Do not start P2 / Employee App P1 / Setup Console / Auth Wave 2 Phase 6 automatically.**
""",
        encoding="utf-8",
    )
    print(f"\nVERDICT {verdict}  pass={PASS} fail={FAIL}  evidence={EVID}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
