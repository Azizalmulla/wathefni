"""Smoke test: Payroll standalone readiness — period picker + export download/detail.

Standalone-readiness for the Payroll module beyond the auto-derived single period:
HR must be able to pick which pay period they review/preview/export, and retrieve a
finalized export (detail view + CSV download) from the dashboard.

This pins the NEW dashboard surface for the batch:
  - period picker: dashboard_posthire_payroll(start_date,end_date) honours an explicit
    period, and the payload exposes a `periods` list (selected period always included).
  - export detail: GET /payroll/exports/{id} returns the export's rows/totals/period,
    is company-scoped (404 cross-company / unknown), gated on payroll.export, audited.
  - CSV download: build_payroll_export_csv has a stable header; the download endpoint
    returns text/csv + an attachment filename and records a 'payroll_export_downloaded'
    audit. A role without payroll.export is denied on both.

External side-effects are not triggered (we seed payroll_exports directly). All writes
use a synthetic export_id removed in a finally block, so this is safe to re-run.

Run against a DB (staging): python3 smoke-test-payroll-standalone.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    payroll standalone — period picker + export detail/CSV, RBAC + scope + audit")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    today = app.kuwait_today()

    # --- CSV builder column contract (no DB) -----------------------------
    sample_export = {
        "preview_snapshot": [
            {"employee_name": "Pay Tester", "employee_pay_type": "monthly", "payable_minutes": 9000,
             "deduction_minutes": 120, "overtime_review_minutes": 60, "estimated_amount_kwd": 250.5, "amount_status": "estimated"},
        ],
        "policy_snapshot": {"currency": "kwd"},
    }
    csv_text = app.build_payroll_export_csv(sample_export)
    header = csv_text.splitlines()[0]
    check("CSV header has the agreed columns",
          header == "Employee,Pay type,Payable hours,Deduction hours,Overtime (review) hours,Estimated amount (KWD),Status")
    check("CSV includes the row data", "Pay Tester" in csv_text and "250.500" in csv_text and "Estimated" in csv_text)
    check("CSV humanizes pay type", "Monthly" in csv_text)

    # --- locate a company with the payroll module enabled ----------------
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "payroll")), None)
    if not company:
        print("    (no company has the payroll module enabled — skipping live checks)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    print(f"    using company {company}")

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-payroll",
            "actor_role": role,
            "hr_phone": "99900000077",
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    owner = ctx(["payroll.read", "payroll.export"])

    # --- available periods helper ---------------------------------------
    sel = ((today - timedelta(days=400)).replace(day=1).isoformat(), (today - timedelta(days=400)).replace(day=15).isoformat())
    periods = app.available_payroll_periods(company, sel)
    check("available periods returns a non-empty list", isinstance(periods, list) and len(periods) >= 1)
    check("available periods includes the selected period", any(p["start_date"] == sel[0] and p["end_date"] == sel[1] for p in periods))
    starts = [p["start_date"] for p in periods]
    check("available periods sort most-recent first", starts == sorted(starts, reverse=True))

    # --- dashboard endpoint honours an explicit period ------------------
    mstart = today.replace(day=1)
    mend = (mstart.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    payload = app.dashboard_posthire_payroll(start_date=mstart.isoformat(), end_date=mend.isoformat(), context=owner)
    check("payroll payload echoes the picked period", payload.get("period", {}).get("start_date") == mstart.isoformat())
    check("payroll payload exposes periods for the picker", isinstance(payload.get("periods"), list) and len(payload.get("periods")) >= 1)
    check("payroll payload reports can_export for an exporter", payload.get("can_export") is True)
    viewer_payload = app.dashboard_posthire_payroll(start_date=None, end_date=None, context=ctx(["payroll.read"], role="viewer"))
    check("can_export is false without payroll.export", viewer_payload.get("can_export") is False)

    # Capture audit calls without coupling to the audit store internals.
    audits: list[dict] = []
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k})

    export_id = str(uuid.uuid4())

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM payroll_export_events WHERE export_id=%s", (export_id,))
                cur.execute("DELETE FROM payroll_exports WHERE export_id=%s", (export_id,))
            conn.commit()

    def seed_export():
        rows = [
            {"employee_name": "Alpha Worker", "employee_pay_type": "monthly", "payable_minutes": 9600,
             "deduction_minutes": 0, "overtime_review_minutes": 0, "estimated_amount_kwd": 300.0, "amount_status": "estimated"},
            {"employee_name": "Beta Worker", "employee_pay_type": "hourly", "payable_minutes": 7200,
             "deduction_minutes": 60, "overtime_review_minutes": 30, "estimated_amount_kwd": 180.250, "amount_status": "estimated"},
        ]
        totals = app.payroll_preview_totals(rows)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payroll_exports
                      (export_id, company_code, period_start, period_end, status, export_kind, row_count,
                       totals, policy_snapshot, preview_snapshot, source_payload, sheet_sync)
                    VALUES (%s,%s,%s,%s,'exported','payroll_preview',%s,%s,%s,%s,%s,%s)
                    """,
                    (export_id, company, mstart, mend, len(rows), app.Json(app.json_safe(totals)),
                     app.Json({"currency": "KWD"}), app.Json(app.json_safe(rows)), app.Json({}),
                     app.Json({"spreadsheet_url": "https://docs.google.com/spreadsheets/d/smoke"})),
                )
            conn.commit()

    cleanup()
    try:
        seed_export()

        # --- export detail (company-scoped, audited) ---------------------
        audits.clear()
        detail = app.dashboard_posthire_payroll_export_detail(export_id=export_id, context=owner)
        check("detail returns the export's period", detail.get("period", {}).get("start_date") == mstart.isoformat())
        check("detail returns the per-employee rows", len(detail.get("preview_rows") or []) == 2)
        check("detail returns totals", isinstance(detail.get("totals"), dict) and detail["totals"].get("row_count") == 2)
        check("detail surfaces the sheet destination", "smoke" in str(detail.get("sheet_url") or ""))
        check("detail recorded a 'payroll_export_viewed' audit", any(a["action_type"] == "payroll_export_viewed" for a in audits))

        # unknown / cross-company id => 404
        try:
            app.dashboard_posthire_payroll_export_detail(export_id=str(uuid.uuid4()), context=owner)
            check("unknown export id returns 404", False)
        except app.HTTPException as exc:
            check("unknown export id returns 404", exc.status_code == 404)
        try:
            app.dashboard_posthire_payroll_export_detail(export_id="not-a-uuid", context=owner)
            check("malformed export id returns 404", False)
        except app.HTTPException as exc:
            check("malformed export id returns 404", exc.status_code == 404)

        # --- CSV download (audited, text/csv, attachment) ----------------
        audits.clear()
        resp = app.dashboard_posthire_payroll_export_download(export_id=export_id, context=owner)
        check("download returns a text/csv response", getattr(resp, "media_type", "") == "text/csv")
        check("download sets an attachment filename", "attachment" in str(resp.headers.get("content-disposition", "")).lower())
        check("download recorded a 'payroll_export_downloaded' audit", any(a["action_type"] == "payroll_export_downloaded" for a in audits))

        # --- RBAC: payroll.export required for detail + download ----------
        viewer = ctx(["payroll.read"], role="viewer")
        try:
            app.dashboard_posthire_payroll_export_detail(export_id=export_id, context=viewer)
            check("role without payroll.export is denied (detail)", False)
        except app.HTTPException as exc:
            check("role without payroll.export is denied (detail)", exc.status_code in (401, 403))
        try:
            app.dashboard_posthire_payroll_export_download(export_id=export_id, context=viewer)
            check("role without payroll.export is denied (download)", False)
        except app.HTTPException as exc:
            check("role without payroll.export is denied (download)", exc.status_code in (401, 403))
    finally:
        app.record_admin_audit = real_audit
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    PAYROLL STANDALONE: FAILURES")
        return 1
    print("    PAYROLL STANDALONE: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
