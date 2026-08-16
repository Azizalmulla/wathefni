#!/usr/bin/env python3
"""Employee Payslips P0.1 — Official PDF from immutable external-authority snapshot.

Keeps P0 release gate frozen. Proves:
  - official PDF only for external_import + money_authority=external
  - native_preview never becomes official PDF
  - unreleased PDF inaccessible; release → employee PDF download
  - peer isolation; replace needs re-release; revoke/unrelease remove access
  - EN/AR PDF; amounts match API; no invented payment_date

Usage (VPS):
  cd /opt/wathefni/ops && /opt/wathefni/orchestrator/.venv/bin/python smoke-test-employee-payslips-p0_1.py
"""
from __future__ import annotations

import calendar
import hashlib
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
ORCH = next((p for p in ORCH_CANDIDATES if (p / "payroll_payslip_wave3.py").exists()), ORCH_CANDIDATES[0])
sys.path.insert(0, str(ORCH))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
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
    "PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,EP0",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

COMPANY = "WATHEFNI"
TAG = os.environ.get("EP01_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
PHONE_A = f"9655415{TAG_DIGITS}"
PHONE_B = f"9655414{TAG_DIGITS}"
EMP_A = f"WATHEFNI-PYW1-PYW3-EP01-A-{TAG}"
EMP_B = f"WATHEFNI-PYW1-PYW3-EP01-B-{TAG}"
CREATOR = f"9655413{TAG_DIGITS}"
APPROVER = f"9655412{TAG_DIGITS}"

_existing = [x.strip() for x in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if x.strip()]
os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(set(_existing) | {EMP_A, EMP_B}))

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("EP01_EVID") or str(ROOT / "ops" / "evidence" / f"employee-payslips-p0_1-{STAMP}"))
EVID.mkdir(parents=True, exist_ok=True)
(EVID / "pdf").mkdir(parents=True, exist_ok=True)


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
    year = 2032 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def upsert_employee(app: Any, key: str, phone: str, name: str) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name,
                                       onboarding_status, employment_status, app_access_enabled,
                                       created_at, updated_at)
                VALUES (%s,%s,%s,%s,'not_started','active',true,now(),now())
                ON CONFLICT (employee_key) DO UPDATE
                SET phone=EXCLUDED.phone, name=EXCLUDED.name, employment_status='active',
                    app_access_enabled=true, updated_at=now()
                """,
                (COMPANY, key, phone, name),
            )
        conn.commit()


def cleanup(app: Any, w3: Any, keys: list[str]) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.ensure_payroll_wave3_schema(cur)
            cur.execute(
                "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            pids = [dict(r)["payslip_id"] for r in cur.fetchall()]
            if pids:
                cur.execute("DELETE FROM payroll_payslip_lines WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
            cur.execute("DELETE FROM employee_messages WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            cur.execute("DELETE FROM employee_sessions WHERE employee_key = ANY(%s)", (keys,))
            for key in keys:
                cur.execute(
                    "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
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
            cur.execute(
                "SELECT preview_run_id::text FROM payroll_preview_runs WHERE company_code=%s AND inputs::text LIKE %s",
                (COMPANY, f"%{EMP_A}%"),
            )
            prids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
            if prids:
                cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
            cur.execute(
                "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%ep01_{TAG}%"),
            )
            iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
            if iids:
                cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
            cur.execute(
                "SELECT export_run_id::text FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%ep01_{TAG}%"),
            )
            eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
            if eids:
                cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
                cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
            cur.execute(
                "DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%ep01_{TAG}%"),
            )
            cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
        conn.commit()


def main() -> int:
    print(f"employee payslips p0.1 official pdf tag={TAG}")
    import app  # noqa: E402
    import payroll_authority_wave1 as pyw1  # noqa: E402
    import payroll_external_adapter_wave2a as w2a  # noqa: E402
    import payroll_native_preview_wave2b as w2b  # noqa: E402
    import payroll_payslip_official_pdf as opdf  # noqa: E402
    import payroll_payslip_wave3 as w3  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402

    try:
        import reportlab  # noqa: F401
        check("reportlab installed", True)
    except ImportError as exc:
        check("reportlab installed", False, str(exc))
        return 1

    blockers = opdf.production_authority_blockers()
    check("native never official documented", blockers.get("native_preview_never_official") is True)
    check("external mirror not wathefni money authority", blockers.get("external_is_mirror_not_wathefni_money_authority") is True)
    check("remaining gate present", bool(blockers.get("remaining_production_authority_gate")))

    # Unit: refuse native eligibility
    check(
        "native ineligible",
        opdf.is_official_pdf_eligible({"source_kind": "native_preview", "money_authority": "preview_non_authoritative"})
        is False,
    )
    check(
        "external eligible",
        opdf.is_official_pdf_eligible({"source_kind": "external_import", "money_authority": "external"}) is True,
    )

    # Deterministic PDF render unit (no payment_date)
    sample = opdf.render_official_payslip_pdf_bytes(
        company_name="Wathefni Canary",
        employee_name="EP01 Employee",
        employee_id=EMP_A,
        payslip={
            "payslip_id": "00000000-0000-0000-0000-000000000001",
            "period_start": "2032-01-01",
            "period_end": "2032-01-31",
            "version_number": 1,
            "currency": "KWD",
            "totals_earnings": 550,
            "totals_deductions": 50,
            "totals_net": 500,
            "money_authority": "external",
            "content_fingerprint": "abc123fingerprint",
        },
        lines=[
            {"line_kind": "earning", "code": "BASIC", "label_en": "Basic", "label_ar": "أساسي", "amount": 500},
            {"line_kind": "allowance", "code": "TRANSPORT", "label_en": "Transport", "label_ar": "مواصلات", "amount": 50},
            {"line_kind": "deduction", "code": "DED", "label_en": "Deduction", "label_ar": "خصم", "amount": 50},
        ],
        locale="en",
        payment_date=None,
    )
    check("unit pdf magic", sample.startswith(b"%PDF"))
    check("unit pdf no invented payment date string", b"Payment date" not in sample)
    (EVID / "pdf" / "unit-sample-en.pdf").write_bytes(sample)
    sample_ar = opdf.render_official_payslip_pdf_bytes(
        company_name="وظفني",
        employee_name="موظف تجريبي",
        employee_id=EMP_A,
        payslip={
            "payslip_id": "00000000-0000-0000-0000-000000000001",
            "period_start": "2032-01-01",
            "period_end": "2032-01-31",
            "version_number": 1,
            "currency": "KWD",
            "totals_net": 500,
            "money_authority": "external",
            "content_fingerprint": "abc123fingerprint",
        },
        lines=[{"line_kind": "earning", "code": "BASIC", "label_ar": "أساسي", "label_en": "Basic", "amount": 500}],
        locale="ar",
    )
    check("unit pdf AR magic", sample_ar.startswith(b"%PDF"))
    (EVID / "pdf" / "unit-sample-ar.pdf").write_bytes(sample_ar)

    cleanup(app, w3, [EMP_A, EMP_B])
    upsert_employee(app, EMP_A, PHONE_A, f"EP01 A {TAG}")
    upsert_employee(app, EMP_B, PHONE_B, f"EP01 B {TAG}")
    p_start, p_end = unique_period()
    ext_id = ""
    native_id = ""
    replaced_id = ""

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.ensure_payroll_wave3_schema(cur)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"ep01_mode_{TAG}"
                )
                draft = pyw1.create_contract_draft(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_A,
                    effective_from=date(2026, 1, 1),
                    components=[
                        {"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True},
                        {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50},
                    ],
                    actor_phone=CREATOR,
                    reason=f"ep01_draft_{TAG}",
                )
                check("contract draft", draft.get("ok") is True, draft)
                if not draft.get("ok"):
                    raise RuntimeError(draft)
                cid = str((draft.get("contract") or {}).get("contract_id") or "")
                approved = pyw1.approve_contract(
                    cur,
                    company_code=COMPANY,
                    contract_id=cid,
                    actor_phone=APPROVER,
                    reason=f"ep01_approve_{TAG}",
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
                    reason=f"ep01_period_{TAG}",
                )
                if not period.get("ok"):
                    cur.execute(
                        "SELECT * FROM payroll_periods WHERE company_code=%s AND period_start=%s AND period_end=%s ORDER BY created_at DESC LIMIT 1",
                        (COMPANY, p_start, p_end),
                    )
                    row = cur.fetchone()
                    period = {"ok": True, "period": dict(row)} if row else period
                check("period", period.get("ok") is True, period)
                period_row = period.get("period") or {}
                pid = str(period_row.get("period_id") or "")

                # Native preview slip (must NEVER be official)
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"ep01_native_mode_{TAG}"
                )
                preview = w2b.calculate_native_preview(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    period_id=pid or None,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    actor_phone=CREATOR,
                    reason=f"ep01_preview_{TAG}",
                )
                check("native preview", preview.get("ok") is True, preview)
                prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
                gen_n = w3.generate_native_payslip(
                    cur,
                    company_code=COMPANY,
                    preview_run_id=prid,
                    employee_key=EMP_A,
                    actor_phone=CREATOR,
                    reason=f"ep01_native_{TAG}",
                )
                check("native payslip", gen_n.get("ok") is True, gen_n)
                native_id = str((gen_n.get("payslip") or {}).get("payslip_id") or "")
                check(
                    "native money authority preview",
                    (gen_n.get("payslip") or {}).get("money_authority") == "preview_non_authoritative",
                    gen_n,
                )
                check("native official ineligible", opdf.is_official_pdf_eligible(gen_n.get("payslip") or {}) is False)

                # External path — official-eligible
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"ep01_ext_mode_{TAG}"
                )
                exported = w2a.create_external_export(
                    cur,
                    company_code=COMPANY,
                    period=period_row,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    attendance=[{"employee_key": EMP_A, "worked_minutes": 10000}],
                    leave_classifications=[],
                    actor_phone=CREATOR,
                    reason=f"ep01_export_{TAG}",
                )
                check("external export", exported.get("ok") is True, exported)
                eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
                cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
                payload = dict(cur.fetchone())["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=f"EXT-EP01-{TAG}")
                imported = w2a.import_external_results(
                    cur,
                    company_code=COMPANY,
                    export_run_id=eid,
                    csv_text=result_csv,
                    actor_phone=APPROVER,
                    reason=f"ep01_import_{TAG}",
                )
                check("external import", imported.get("ok") is True, imported)
                iid = str((imported.get("import_run") or {}).get("import_run_id") or "")
                ext = w3.generate_external_payslip(
                    cur,
                    company_code=COMPANY,
                    import_run_id=iid,
                    employee_key=EMP_A,
                    actor_phone=CREATOR,
                    reason=f"ep01_ext_slip_{TAG}",
                )
                check("external payslip", ext.get("ok") is True, ext)
                eslip = ext.get("payslip") or {}
                ext_id = str(eslip.get("payslip_id") or "")
                check("external money authority", eslip.get("money_authority") == "external", eslip)
                check("external official eligible", opdf.is_official_pdf_eligible(eslip) is True)
                check("starts not_released", str(eslip.get("employee_visibility") or "not_released") == "not_released")

                # Unreleased: employee cannot view; PDF ensure allowed for HR staging but employee API blocked
                check("employee cannot view unreleased", w3.employee_can_view(eslip) is False)
                gen_pdf = opdf.ensure_official_pdf_for_payslip(
                    cur, company_code=COMPANY, payslip_id=ext_id, locale="en"
                )
                check("pdf generate before release ok (immutable snapshot)", gen_pdf.get("ok") is True, gen_pdf)
            conn.commit()

        token_a = str(app.create_employee_session(COMPANY, EMP_A, PHONE_A)["token"])
        token_b = str(app.create_employee_session(COMPANY, EMP_B, PHONE_B)["token"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM dashboard_users
                    WHERE company_code=%s AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr')
                    ORDER BY created_at LIMIT 1
                    """,
                    (COMPANY,),
                )
                hr_user = dict(cur.fetchone() or {})
            conn.commit()
        hr_token = str(app.create_dashboard_session(hr_user)[0]) if hr_user else ""
        client = TestClient(app.app)

        # Unreleased inaccessible
        d0 = client.get(f"/app/payslips/{ext_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("unreleased detail 404", d0.status_code == 404, d0.text[:200])
        dl0 = client.get(f"/app/payslips/{ext_id}/download", headers={"Authorization": f"Bearer {token_a}"})
        check("unreleased download 404", dl0.status_code == 404, dl0.text[:200])

        # Release via HR
        rr = client.post(
            f"/dashboard/posthire/payroll/payslips/{ext_id}/release",
            headers={"Authorization": f"Bearer {hr_token}"},
            json={"reason": f"ep01_release_{TAG}"},
        )
        check("HR release", rr.status_code == 200 and rr.json().get("ok") is True, rr.text[:400])

        d1 = client.get(f"/app/payslips/{ext_id}?locale=en", headers={"Authorization": f"Bearer {token_a}"})
        check("released detail", d1.status_code == 200 and d1.json().get("ok") is True, d1.text[:300])
        body = d1.json()
        check("official_document true", (body.get("payslip") or {}).get("official_document") is True, body)
        check("payment_date null", (body.get("payslip") or {}).get("payment_date") is None, body)
        api_net = (body.get("payslip") or {}).get("totals", {}).get("net")

        dl = client.get(
            f"/app/payslips/{ext_id}/download?locale=en",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("download PDF 200", dl.status_code == 200 and dl.content.startswith(b"%PDF"), dl.headers)
        check("official header true", dl.headers.get("X-Wathefni-Official-Document") == "true")
        check("content-type pdf", "pdf" in (dl.headers.get("content-type") or ""))
        (EVID / "pdf" / f"employee-{ext_id}-en.pdf").write_bytes(dl.content)
        # Amounts: compare API totals to PDF text extract (streams may be compressed).
        pdf_text = _pdf_text(dl.content)
        check(
            "pdf contains net amount",
            _net_in_text(pdf_text, api_net),
            {"api_net": api_net, "pdf_excerpt": pdf_text[-400:]},
        )
        check("pdf omits payment date label when unknown", "Payment date" not in pdf_text)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                stored = opdf.read_official_pdf(cur, company_code=COMPANY, payslip_id=ext_id, locale="en")
            conn.commit()
        check(
            "stored totals_net matches API",
            float(stored.get("totals_net") or -1) == float(api_net),
            {"stored": stored.get("totals_net"), "api": api_net},
        )

        dl_ar = client.get(
            f"/app/payslips/{ext_id}/download?locale=ar",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("download PDF AR", dl_ar.status_code == 200 and dl_ar.content.startswith(b"%PDF"), dl_ar.headers)
        (EVID / "pdf" / f"employee-{ext_id}-ar.pdf").write_bytes(dl_ar.content)

        # Peer isolation
        d_peer = client.get(f"/app/payslips/{ext_id}", headers={"Authorization": f"Bearer {token_b}"})
        check("peer detail 404", d_peer.status_code == 404)
        dl_peer = client.get(f"/app/payslips/{ext_id}/download", headers={"Authorization": f"Bearer {token_b}"})
        check("peer download 404", dl_peer.status_code == 404)

        # Native released still cannot be official PDF
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=native_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_release_native_{TAG}",
                )
            conn.commit()
        dn = client.get(f"/app/payslips/{native_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("native released viewable", dn.status_code == 200, dn.text[:200])
        check(
            "native official_document false",
            (dn.json().get("payslip") or {}).get("official_document") is False,
            dn.json(),
        )
        dln = client.get(f"/app/payslips/{native_id}/download", headers={"Authorization": f"Bearer {token_a}"})
        check("native official download refused", dln.status_code == 422, dln.text[:300])

        # Replace → new version not visible until re-release
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                replaced = w3.replace_payslip(
                    cur,
                    company_code=COMPANY,
                    payslip_id=ext_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_replace_{TAG}",
                )
                check("replace ok", replaced.get("ok") is True, replaced)
                replaced_id = str((replaced.get("payslip") or {}).get("payslip_id") or "")
                check("replacement not released", w3.employee_facing_state(replaced.get("payslip") or {}) == "not_released")
            conn.commit()
        d_old = client.get(f"/app/payslips/{ext_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("old version unavailable after replace", d_old.status_code == 404)
        d_new = client.get(f"/app/payslips/{replaced_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("new version invisible until re-release", d_new.status_code == 404)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_rerelease_{TAG}",
                )
            conn.commit()
        d_new2 = client.get(f"/app/payslips/{replaced_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("re-released new version visible", d_new2.status_code == 200)
        dl_new = client.get(
            f"/app/payslips/{replaced_id}/download?locale=en",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("new version PDF", dl_new.status_code == 200 and dl_new.content.startswith(b"%PDF"))
        (EVID / "pdf" / f"employee-{replaced_id}-en.pdf").write_bytes(dl_new.content)

        # Unrelease / revoke
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.unrelease_payslip_from_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_unrelease_{TAG}",
                )
            conn.commit()
        check(
            "unrelease removes access",
            client.get(f"/app/payslips/{replaced_id}/download", headers={"Authorization": f"Bearer {token_a}"}).status_code
            == 404,
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_rerelease2_{TAG}",
                )
                w3.revoke_payslip(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep01_revoke_{TAG}",
                )
            conn.commit()
        check(
            "revoke removes access",
            client.get(f"/app/payslips/{replaced_id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404,
        )

        # Immutable: same fingerprint regenerate is idempotent
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # Re-create a fresh external for immutability proof on a known released slip is heavy;
                # prove idempotent ensure on already-generated first ext (still on disk even if replaced).
                again = opdf.ensure_official_pdf_for_payslip(
                    cur, company_code=COMPANY, payslip_id=ext_id, locale="en"
                )
                check("pdf ensure idempotent for same fingerprint", again.get("ok") is True and again.get("idempotent") is True, again)
            conn.commit()

    finally:
        cleanup(app, w3, [EMP_A, EMP_B])
        check("cleanup", True)

    report = {
        "stamp": STAMP,
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "verdict": "PASS" if FAIL == 0 else "FAIL",
        "authority_model": {
            "employee_visible_iff": "status=active AND employee_visibility=released",
            "official_pdf_requires": "source_kind=external_import AND money_authority=external",
            "native_preview_never_official": True,
            "payment_date": None,
        },
        "production_authority_blockers": blockers,
        "sample_pdfs": [str(p.relative_to(EVID)) for p in sorted((EVID / "pdf").glob("*.pdf"))],
        "results": RESULTS,
    }
    (EVID / "results.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "pass": PASS, "fail": FAIL, "evidence": str(EVID)}, indent=2))
    return 0 if FAIL == 0 else 1


def _pdf_text(pdf: bytes) -> str:
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf)
        tmp.flush()
        try:
            out = subprocess.check_output(["pdftotext", tmp.name, "-"], stderr=subprocess.DEVNULL, timeout=10)
            return out.decode("utf-8", "replace")
        except Exception:
            # Fallback: inflate content streams
            import re
            import zlib

            parts: list[str] = []
            for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
                chunk = m.group(1).lstrip(b"\r\n")
                try:
                    parts.append(zlib.decompress(chunk).decode("latin1", "replace"))
                except Exception:
                    continue
            return "\n".join(parts)


def _net_in_text(text: str, net: Any) -> bool:
    from decimal import Decimal

    try:
        d = Decimal(str(net))
    except Exception:
        return str(net) in text
    candidates = {str(net), f"{d:.3f}", f"{d:.2f}", f"{d:f}", str(float(d))}
    return any(c in text for c in candidates if c)


if __name__ == "__main__":
    raise SystemExit(main())
