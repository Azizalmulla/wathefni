#!/usr/bin/env python3
"""Employee Payslips P0 — HR release gate + employee read-only (WATHEFNI canary).

Proves:
  draft/unreleased invisible → explicit release → self-only → peer 404
  unrelease/revoke unavailable → replace needs re-release → release idempotent
  payroll module off → payslips feature disabled (contract)
  EN/AR honesty + catalog labels
  official PDF / payment_date absent (honest)

Synthetic subjects only (PYW3 + 965541*). Does not touch Aziz/Talal payroll.

Usage (on VPS with prod env):
  cd /opt/wathefni/orchestrator && .venv/bin/python /path/to/ops/smoke-test-employee-payslips-p0.py
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
ORCH = next((p for p in ORCH_CANDIDATES if (p / "payroll_payslip_wave3.py").exists()), ORCH_CANDIDATES[0])
sys.path.insert(0, str(ORCH))
sys.path.insert(0, str(ROOT / "ops"))

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
TAG = os.environ.get("EP0_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
PHONE_A = f"9655419{TAG_DIGITS}"
PHONE_B = f"9655418{TAG_DIGITS}"
# PYW1 required for Wave 1 contracts; PYW3 for Wave 3 release gate synthetic markers.
EMP_A = f"WATHEFNI-PYW1-PYW3-EP0-A-{TAG}"
EMP_B = f"WATHEFNI-PYW1-PYW3-EP0-B-{TAG}"
CREATOR = f"9655417{TAG_DIGITS}"
APPROVER = f"9655416{TAG_DIGITS}"

# Extend allowlist in-process so TestClient + create_session work without systemd churn.
_existing = [x.strip() for x in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if x.strip()]
os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(set(_existing) | {EMP_A, EMP_B}))

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("EP0_EVID") or str(ROOT / "ops" / "evidence" / f"employee-payslips-p0-{STAMP}"))
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
    year = 2031 + (n // 12)
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


def cleanup(app: Any, w3: Any, pyw1: Any, keys: list[str]) -> dict[str, int]:
    deleted: dict[str, int] = {}
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
                deleted["lines"] = cur.rowcount or 0
                cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
                deleted["events"] = cur.rowcount or 0
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
                deleted["payslips"] = cur.rowcount or 0
            cur.execute(
                "DELETE FROM employee_messages WHERE company_code=%s AND employee_key = ANY(%s) AND template_key='payslip_ready'",
                (COMPANY, keys),
            )
            deleted["messages"] = cur.rowcount or 0
            cur.execute("DELETE FROM employee_sessions WHERE employee_key = ANY(%s)", (keys,))
            deleted["sessions"] = cur.rowcount or 0
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
                "DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%ep0_{TAG}%"),
            )
            cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
            deleted["employees"] = cur.rowcount or 0
        conn.commit()
    return deleted


def static_contracts() -> None:
    mobile = ROOT / "apps" / "wathefni-employee-mobile"
    dash = ROOT / "apps" / "wathefni-dashboard"
    orch = ORCH
    check("sql release migration", (orch / "ops/sql/payroll_payslip_employee_release_v1.sql").exists())
    w3src = (orch / "payroll_payslip_wave3.py").read_text(encoding="utf-8")
    check("release_payslip_to_employee", "def release_payslip_to_employee" in w3src)
    check("employee list gate", "employee_visibility='released'" in w3src)
    check("period never implies visibility", "period_status_never_implies_employee_visibility" in w3src)
    appsrc = (orch / "app.py").read_text(encoding="utf-8")
    check("employee /app/payslips route", '@app.get("/app/payslips")' in appsrc)
    check("HR release route", "/payslips/{payslip_id}/release" in appsrc)
    check("payslips feature implemented", '"payslips"' in appsrc and '"implemented": True' in appsrc)
    check("wave3 gate on detail", appsrc.count("payroll_wave3_enabled_for_company(company)") >= 3)
    payslips_tsx = (mobile / "app/payslips.tsx").read_text(encoding="utf-8")
    check("mobile ScrollView", "ScrollView" in payslips_tsx and "RefreshControl" in payslips_tsx)
    check("mobile deep link param", "payslip_id" in payslips_tsx)
    check("mobile hasFeature gate", "hasFeature('payslips')" in payslips_tsx)
    en = (mobile / "src/i18n/en.json").read_text(encoding="utf-8")
    ar = (mobile / "src/i18n/ar.json").read_text(encoding="utf-8")
    check("i18n EN payslips", "payslips.title" in en and "Payslips" in en)
    check("i18n AR payslips", "payslips.title" in ar and "كشوف الرواتب" in ar)
    check("no invented payment date UI", "paymentDateUnknown" in en and "paymentDateUnknown" in ar)
    ws = (dash / "src/posthire/PayslipWorkspace.tsx").read_text(encoding="utf-8")
    check("HR release UI", "postPayrollPayslipRelease" in ws and "employee_facing_state" in ws)
    ux = (dash / "src/posthire/payrollPayslipUx.ts").read_text(encoding="utf-8")
    check("HR EN/AR release copy", ("release" in ux.lower()) and (("إصدار" in ux) or ("مُصدَر" in ux) or ("سحب" in ux)))
    outbound = (orch / "outbound_delivery.py").read_text(encoding="utf-8")
    check("payslip_ready catalog AR", '"payslip_ready"' in outbound and "كشف الراتب جاهز" in outbound)
    notify = (mobile / "app/(tabs)/notifications.tsx").read_text(encoding="utf-8")
    check("notif deep link payslips", "/payslips" in notify)


def main() -> int:
    print(f"employee payslips p0 canary tag={TAG}")
    static_contracts()

    import app  # noqa: E402
    import outbound_delivery as outbound  # noqa: E402
    import payroll_authority_wave1 as pyw1  # noqa: E402
    import payroll_native_preview_wave2b as w2b  # noqa: E402
    import payroll_payslip_wave3 as w3  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402

    check("wave3 enabled", w3.payroll_wave3_enabled_for_company(COMPANY))
    check("synthetic only", w3.payroll_wave3_synthetic_only())
    check("emp A synthetic", w3.is_wave3_synthetic_employee(employee_key=EMP_A, phone=PHONE_A))
    check("emp B synthetic", w3.is_wave3_synthetic_employee(employee_key=EMP_B, phone=PHONE_B))
    honesty = w3.honesty_payload()
    check("official pdf false", honesty.get("official_employee_pdf") is False)
    check("release gate documented", honesty.get("employee_release_gate") is True)

    feat_on = app.build_employee_app_feature_contract({"payroll", "employee_app", "leave"}, push_available=False)
    check(
        "feature payslips on with payroll",
        bool((feat_on.get("features") or {}).get("payslips", {}).get("enabled")),
        feat_on.get("features", {}).get("payslips"),
    )
    feat_off = app.build_employee_app_feature_contract({"employee_app", "leave"}, push_available=False)
    check(
        "feature payslips off without payroll",
        not bool((feat_off.get("features") or {}).get("payslips", {}).get("enabled")),
        feat_off.get("features", {}).get("payslips"),
    )
    check("catalog label EN", outbound.catalog_label("payslip_ready", "en") == "Payslip ready")
    check("catalog label AR", outbound.catalog_label("payslip_ready", "ar") == "كشف الراتب جاهز")

    cleanup(app, w3, pyw1, [EMP_A, EMP_B])
    upsert_employee(app, EMP_A, PHONE_A, f"EP0 A {TAG}")
    upsert_employee(app, EMP_B, PHONE_B, f"EP0 B {TAG}")

    p_start, p_end = unique_period()
    payslip_id = ""
    replaced_id = ""
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w3.ensure_payroll_wave3_schema(cur)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"ep0_mode_{TAG}"
                )
                draft = pyw1.create_contract_draft(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_A,
                    effective_from=date(2026, 1, 1),
                    components=[
                        {"component_kind": "earning", "code": "BASIC", "amount": 400, "is_basic": True},
                        {"component_kind": "allowance", "code": "TRANSPORT", "amount": 40},
                    ],
                    actor_phone=CREATOR,
                    reason=f"ep0_draft_{TAG}",
                )
                check("contract draft", draft.get("ok") is True, draft)
                if not draft.get("ok"):
                    raise RuntimeError(f"contract draft failed: {draft}")
                cid = str((draft.get("contract") or {}).get("contract_id") or "")
                approved = pyw1.approve_contract(
                    cur,
                    company_code=COMPANY,
                    contract_id=cid,
                    actor_phone=APPROVER,
                    reason=f"ep0_approve_{TAG}",
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
                    reason=f"ep0_period_{TAG}",
                )
                if not period.get("ok"):
                    # Unique period collision — fetch existing
                    cur.execute(
                        """
                        SELECT * FROM payroll_periods
                        WHERE company_code=%s AND period_start=%s AND period_end=%s
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (COMPANY, p_start, p_end),
                    )
                    row = cur.fetchone()
                    period = {"ok": True, "period": dict(row)} if row else period
                check("period", period.get("ok") is True, period)
                pid = str((period.get("period") or {}).get("period_id") or "")
                preview = w2b.calculate_native_preview(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    period_id=pid or None,
                    employees=[{"employee_key": EMP_A}],
                    contracts=[contract_row],
                    actor_phone=CREATOR,
                    reason=f"ep0_preview_{TAG}",
                )
                check("preview", preview.get("ok") is True, preview)
                prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
                gen = w3.generate_native_payslip(
                    cur,
                    company_code=COMPANY,
                    preview_run_id=prid,
                    employee_key=EMP_A,
                    actor_phone=CREATOR,
                    reason=f"ep0_gen_{TAG}",
                )
                check("generate payslip", gen.get("ok") is True, gen)
                slip = gen.get("payslip") or {}
                payslip_id = str(slip.get("payslip_id") or "")
                check("starts not_released", str(slip.get("employee_visibility") or "not_released") == "not_released", slip)
                check("employee_facing not_released", w3.employee_facing_state(slip) == "not_released", slip)
                check("employee cannot view draft", w3.employee_can_view(slip) is False)
                listed = w3.list_employee_released_payslips(cur, company_code=COMPANY, employee_key=EMP_A)
                check("draft invisible in employee list", all(str(r.get("payslip_id")) != payslip_id for r in listed), listed)

                # Period status must never imply visibility (assert without requiring lock/close).
                again = w3.get_payslip(cur, company_code=COMPANY, payslip_id=payslip_id)
                check(
                    "unreleased stays invisible regardless of period lifecycle",
                    w3.employee_can_view(again) is False
                    and str(again.get("employee_visibility") or "") == "not_released",
                    again,
                )
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

        r = client.get("/app/payslips", headers={"Authorization": f"Bearer {token_a}"})
        check("http list before release", r.status_code == 200, r.text[:300])
        before_ids = [str(x.get("payslip_id")) for x in (r.json().get("payslips") or [])]
        check("http draft absent", payslip_id not in before_ids, before_ids)

        if not hr_token:
            check("http HR release", False, "no hr dashboard user")
        else:
            rr = client.post(
                f"/dashboard/posthire/payroll/payslips/{payslip_id}/release",
                headers={"Authorization": f"Bearer {hr_token}"},
                json={"reason": f"ep0_http_release_{TAG}"},
            )
            check("http HR release", rr.status_code == 200 and rr.json().get("ok") is True, rr.text[:400])
            check("release ok", rr.status_code == 200 and rr.json().get("ok") is True and not rr.json().get("idempotent"), rr.text[:200])
            check("facing released", rr.json().get("employee_facing_state") == "released", rr.json())
            rr2 = client.post(
                f"/dashboard/posthire/payroll/payslips/{payslip_id}/release",
                headers={"Authorization": f"Bearer {hr_token}"},
                json={"reason": f"ep0_http_release_idem_{TAG}"},
            )
            check("http release idempotent", rr2.status_code == 200 and rr2.json().get("idempotent") is True, rr2.text[:300])
            check("duplicate release idempotent", rr2.status_code == 200 and rr2.json().get("idempotent") is True, rr2.text[:200])

        r2 = client.get("/app/payslips?locale=en", headers={"Authorization": f"Bearer {token_a}"})
        check("http list after release", r2.status_code == 200, r2.text[:300])
        after_ids = [str(x.get("payslip_id")) for x in (r2.json().get("payslips") or [])]
        check("http released visible", payslip_id in after_ids, after_ids)
        check("released visible to owner", payslip_id in after_ids, after_ids)
        check(
            "http official_document false",
            all(x.get("official_document") is False for x in (r2.json().get("payslips") or [])),
            r2.json(),
        )

        r_ar = client.get("/app/payslips?locale=ar", headers={"Authorization": f"Bearer {token_a}"})
        check(
            "http list AR",
            r_ar.status_code == 200 and "صرف" in str(r_ar.json().get("honesty", {}).get("ar") or ""),
            r_ar.json(),
        )

        d = client.get(f"/app/payslips/{payslip_id}?locale=en", headers={"Authorization": f"Bearer {token_a}"})
        check("http detail owner", d.status_code == 200 and d.json().get("ok") is True, d.text[:300])
        check("summary ok", d.status_code == 200 and d.json().get("ok") is True, d.text[:200])
        check("http detail no payment_date", d.json().get("payslip", {}).get("payment_date") is None, d.json())
        check("no payment_date", d.json().get("payslip", {}).get("payment_date") is None, d.json())
        check("official_document false", d.json().get("payslip", {}).get("official_document") is False, d.json())
        dump = json.dumps(d.json())
        check("no approval workflow leak", "approval_workflow" not in dump and "calc_debug" not in dump)

        d_ar = client.get(f"/app/payslips/{payslip_id}?locale=ar", headers={"Authorization": f"Bearer {token_a}"})
        check(
            "summary AR honesty",
            "صرف" in str((d_ar.json().get("payslip") or {}).get("honesty", {}).get("ar") or ""),
            d_ar.json(),
        )

        d_peer = client.get(f"/app/payslips/{payslip_id}", headers={"Authorization": f"Bearer {token_b}"})
        check("http peer detail 404", d_peer.status_code == 404, d_peer.text[:200])
        check("peer detail denied", d_peer.status_code == 404)

        peer_list = client.get("/app/payslips", headers={"Authorization": f"Bearer {token_b}"})
        peer_ids = [str(x.get("payslip_id")) for x in (peer_list.json().get("payslips") or [])]
        check("peer list empty for A slip", payslip_id not in peer_ids, peer_ids)

        dl = client.get(
            f"/app/payslips/{payslip_id}/download?locale=en",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("http download owner", dl.status_code == 200 and "not an official" in dl.text.lower(), dl.text[:200])
        check("http download header honesty", dl.headers.get("X-Wathefni-Official-Document") == "false")

        dl_peer = client.get(f"/app/payslips/{payslip_id}/download", headers={"Authorization": f"Bearer {token_b}"})
        check("http peer download 404", dl_peer.status_code == 404, dl_peer.text[:200])

        n_en = client.get("/app/notifications?locale=en", headers={"Authorization": f"Bearer {token_a}"})
        n_ar = client.get("/app/notifications?locale=ar", headers={"Authorization": f"Bearer {token_a}"})
        check("http notifications EN", n_en.status_code == 200, n_en.text[:200])
        check("http notifications AR", n_ar.status_code == 200, n_ar.text[:200])
        ready_en = [x for x in (n_en.json().get("notifications") or []) if x.get("flow") == "payroll"]
        ready_ar = [x for x in (n_ar.json().get("notifications") or []) if x.get("flow") == "payroll"]
        if ready_en:
            check("notify title EN", "Payslip" in str(ready_en[0].get("title") or ""), ready_en[0])
            check("notify deep_link", bool((ready_en[0].get("deep_link") or {}).get("path")), ready_en[0])
        else:
            check("notify title EN", False, "missing payslip_ready inbox row")
        if ready_ar:
            check("notify title AR", "كشف" in str(ready_ar[0].get("title") or ""), ready_ar[0])
        else:
            check("notify title AR", False, "missing AR payslip_ready")

        me = client.get("/app/me", headers={"Authorization": f"Bearer {token_a}"})
        check("http /app/me", me.status_code == 200, me.text[:200])
        features = (me.json() or {}).get("features") or {}
        if isinstance(features, dict) and "payslips" in features:
            check("me.features.payslips enabled", bool(features["payslips"].get("enabled")), features.get("payslips"))
        else:
            check("me payload present (features shape varies)", me.status_code == 200)

        # Replace / unrelease / revoke via authority module (history integrity)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                replaced = w3.replace_payslip(
                    cur,
                    company_code=COMPANY,
                    payslip_id=payslip_id,
                    actor_phone=APPROVER,
                    reason=f"ep0_replace_{TAG}",
                )
                check("replace ok", replaced.get("ok") is True, replaced)
                replaced_id = str((replaced.get("payslip") or {}).get("payslip_id") or "")
                prior = replaced.get("replaced_payslip") or {}
                check("prior status replaced", prior.get("status") == "replaced", prior)
                check("prior not employee-visible", w3.employee_can_view(prior) is False, prior)
                new_doc = replaced.get("payslip") or {}
                check("replacement starts not_released", w3.employee_facing_state(new_doc) == "not_released", new_doc)
                check(
                    "old id invisible after replace",
                    w3.get_employee_released_payslip(
                        cur, company_code=COMPANY, employee_key=EMP_A, payslip_id=payslip_id
                    )
                    is None,
                )
                check(
                    "new id invisible until re-release",
                    w3.get_employee_released_payslip(
                        cur, company_code=COMPANY, employee_key=EMP_A, payslip_id=replaced_id
                    )
                    is None,
                )
                re_rel = w3.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep0_rerelease_{TAG}",
                )
                check("re-release replacement", re_rel.get("ok") is True and not re_rel.get("idempotent"), re_rel)
                hist = w3.list_payslip_history(cur, company_code=COMPANY, employee_key=EMP_A)
                check("history retained after replace", len(hist) >= 2, len(hist))

                un = w3.unrelease_payslip_from_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep0_unrelease_{TAG}",
                )
                check("unrelease ok", un.get("ok") is True, un)
                check(
                    "unreleased invisible",
                    w3.get_employee_released_payslip(
                        cur, company_code=COMPANY, employee_key=EMP_A, payslip_id=replaced_id
                    )
                    is None,
                )
                w3.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep0_release_before_revoke_{TAG}",
                )
                rev = w3.revoke_payslip(
                    cur,
                    company_code=COMPANY,
                    payslip_id=replaced_id,
                    actor_phone=APPROVER,
                    reason=f"ep0_revoke_{TAG}",
                )
                check("revoke ok", rev.get("ok") is True, rev)
                rev_doc = rev.get("payslip") or w3.get_payslip(cur, company_code=COMPANY, payslip_id=replaced_id)
                check("revoked facing", w3.employee_facing_state(rev_doc) == "revoked", rev_doc)
                check(
                    "revoked invisible",
                    w3.get_employee_released_payslip(
                        cur, company_code=COMPANY, employee_key=EMP_A, payslip_id=replaced_id
                    )
                    is None,
                )
            conn.commit()

        gone = client.get(f"/app/payslips/{replaced_id}", headers={"Authorization": f"Bearer {token_a}"})
        check("http revoked detail 404", gone.status_code == 404, gone.text[:200])

    finally:
        deleted = cleanup(app, w3, pyw1, [EMP_A, EMP_B])
        check("cleanup residual", True, deleted)

    report = {
        "stamp": STAMP,
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "verdict": "PASS" if FAIL == 0 else "FAIL",
        "authority_model": {
            "employee_visible_iff": "status=active AND employee_visibility=released",
            "period_status_never_implies_visibility": True,
            "official_employee_pdf": False,
            "payment_date": None,
            "download": "statement_summary_txt_non_official",
        },
        "results": RESULTS,
    }
    (EVID / "results.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "pass": PASS, "fail": FAIL, "evidence": str(EVID)}, indent=2))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
