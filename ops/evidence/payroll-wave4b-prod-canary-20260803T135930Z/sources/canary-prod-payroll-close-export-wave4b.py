#!/usr/bin/env python3
"""Payroll Wave 4-B — production synthetic close + finance export canary.

Synthetic subjects only (PYW4/PYW1/W4B · 965541*).
Proves: honesty flags, review→approve→close, immutable snapshot, SOD,
dual reopen, balanced journal, fail-closed mappings, bank contract validation
only, export idempotency, fingerprint drift, export history/approvals/recon,
external close create with external authority, residual cleanup = 0.

Does NOT: real bank formats/connections, WPS/AS'HAL, PIFSS, EOS, ERP posts,
payments, or AI. Native results non-authoritative; external remains money
authority. payment_processing=disabled.
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
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY", "1")
os.environ.setdefault(
    "WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS",
    "PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,"
    "PYW1,PYW1-SYNTH|,W2BB,W3B,W4,W4B",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402
import payroll_native_preview_wave2b as w2b  # noqa: E402
import payroll_close_export_wave4 as w4  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW4B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-PYW4-W4B-{TAG}"
CREATOR = f"9655411{TAG_DIGITS}"
APPROVER = f"9655412{TAG_DIGITS}"
CLOSER = f"9655413{TAG_DIGITS}"
EXPORTER = f"9655414{TAG_DIGITS}"
EXPORTER2 = f"9655415{TAG_DIGITS}"
ACTOR_PHONES = [CREATOR, APPROVER, CLOSER, EXPORTER, EXPORTER2]

PERMS_APPROVE = ["payroll.read", "payroll.manage", "payroll.approve"]
PERMS_EXPORT = ["payroll.read", "payroll.export"]
PERMS_SOD_BAD = ["payroll.read", "payroll.approve", "payroll.export"]

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW4B_EVID") or f"/tmp/payroll-w4b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {
        "creator": CREATOR,
        "approver": APPROVER,
        "closer": CLOSER,
        "exporter": EXPORTER,
        "exporter2": EXPORTER2,
    },
    "close_run_ids": [],
    "journal_draft_ids": [],
    "bank_export_ids": [],
    "finance_export_ids": [],
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
    """Unique period in 2032+ to avoid collisions with wave3/wave4 staging periods."""
    n = int(TAG[:4], 16) % 120
    year = 2032 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def cleanup(cur) -> dict[str, int]:
    deleted: dict[str, int] = {}
    tag_like = f"%{TAG}%"

    # 1) Finance exports tied to this TAG's close runs
    cur.execute(
        """
        DELETE FROM payroll_finance_exports
        WHERE company_code=%s AND close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, COMPANY, tag_like),
    )
    deleted["finance_exports"] = cur.rowcount or 0

    # 2) Journal lines then drafts
    cur.execute(
        """
        DELETE FROM payroll_journal_lines
        WHERE journal_draft_id IN (
          SELECT journal_draft_id FROM payroll_journal_drafts
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["journal_lines"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_journal_drafts WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["journal_drafts"] = cur.rowcount or 0

    # 3) Bank export drafts
    cur.execute(
        "DELETE FROM payroll_bank_export_drafts WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["bank_drafts"] = cur.rowcount or 0

    # 4) Dual control
    cur.execute(
        """
        DELETE FROM payroll_close_dual_control
        WHERE close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["dual_control"] = cur.rowcount or 0

    # 5) Close events then runs
    cur.execute(
        """
        DELETE FROM payroll_close_run_events
        WHERE close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["close_events"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["close_runs"] = cur.rowcount or 0

    # 6) Mappings by decision_note LIKE %TAG%
    cur.execute(
        "DELETE FROM payroll_account_mappings WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["mappings"] = cur.rowcount or 0

    # 7) Preview / import / adapter export / contract / period for EMP+TAG
    cur.execute(
        """
        SELECT preview_run_id::text FROM payroll_preview_runs
        WHERE company_code=%s AND (
          decision_note LIKE %s OR inputs::text LIKE %s OR created_by_phone = ANY(%s)
        )
        """,
        (COMPANY, tag_like, f"%{EMP_KEY}%", ACTOR_PHONES),
    )
    prids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
    if prids:
        cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_lines"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)",
            (prids,),
        )
        deleted["preview_employees"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_events"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_runs"] = cur.rowcount or 0
    else:
        cur.execute("DELETE FROM payroll_preview_lines WHERE employee_key=%s", (EMP_KEY,))
        deleted["preview_lines"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_employee_results WHERE employee_key=%s", (EMP_KEY,))
        deleted["preview_employees"] = cur.rowcount or 0

    cur.execute(
        "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
    if iids:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["import_lines"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)",
            (iids,),
        )
        deleted["import_recons"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
        cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["imports"] = cur.rowcount or 0
    else:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE employee_key=%s", (EMP_KEY,))
        deleted["import_lines"] = cur.rowcount or 0

    cur.execute(
        "SELECT export_run_id::text FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
    if eids:
        cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
        cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["adapter_exports"] = cur.rowcount or 0

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
        deleted["contract_events"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contract_components"] = cur.rowcount or 0
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
        (COMPANY, tag_like, ACTOR_PHONES),
    )
    period_ids = [dict(r)["period_id"] for r in cur.fetchall()]
    if period_ids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        deleted["period_events"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        deleted["periods"] = cur.rowcount or 0

    return deleted


def residual(cur) -> int:
    n = 0
    tag_like = f"%{TAG}%"
    for sql, args in (
        (
            "SELECT COUNT(*) AS n FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_finance_exports WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_journal_drafts WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_bank_export_drafts WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_account_mappings WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
            (COMPANY, EMP_KEY),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_preview_runs WHERE company_code=%s AND (decision_note LIKE %s OR inputs::text LIKE %s)",
            (COMPANY, tag_like, f"%{EMP_KEY}%"),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
        (
            "SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
            (COMPANY, tag_like),
        ),
    ):
        cur.execute(sql, args)
        n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave4b prod synthetic canary tag={TAG}")
    h = w4.honesty_payload()
    check("wave4 enabled", w4.payroll_wave4_enabled())
    check("synthetic only", w4.payroll_wave4_synthetic_only())
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
    check("wave1 enabled", pyw1.payroll_wave1_enabled())
    check("wave2a enabled synthetic", w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only())
    check("wave2b enabled synthetic", w2b.payroll_wave2b_enabled() and w2b.payroll_wave2b_synthetic_only())
    check("markers include PYW4", "PYW4" in w4.synthetic_key_markers())
    check("markers include PYW1", "PYW1" in w4.synthetic_key_markers())
    check("markers include W4B", "W4B" in w4.synthetic_key_markers() or w4.is_wave4_synthetic_employee(employee_key=EMP_KEY))
    check("emp synthetic", w4.is_wave4_synthetic_employee(employee_key=EMP_KEY))
    check("phones synthetic", all(w4.is_wave4_synthetic_employee(phone=p) for p in ACTOR_PHONES))

    dash_candidates = [
        ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    dash = next((p for p in dash_candidates if (p / "payrollCloseExportUx.ts").exists()), None)
    if dash:
        ux = (dash / "payrollCloseExportUx.ts").read_text(encoding="utf-8")
        ws_path = dash / "CloseExportWorkspace.tsx"
        ws = ws_path.read_text(encoding="utf-8") if ws_path.exists() else ""
        check("ux en title", "Close & finance export" in ux)
        check("ux ar title", "الإغلاق وتصدير المالية" in ux)
        check("ux honesty", "validation only" in ux.lower() or "تحقق فقط" in ux)
        check("ux payment disabled", "disabled" in ux.lower())
        check("ux mobile", "mobileHint" in ux and "md:hidden" in ws)
        check("ux rtl", "rtl" in ws or "dir=" in ws)

    p_start, p_end = unique_period()
    IDS["period"] = {"start": str(p_start), "end": str(p_end)}
    check("period year >= 2032", p_start.year >= 2032, p_start.year)

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
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"w4b_native_{TAG}"
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 40},
                ],
                actor_phone=CREATOR,
                reason=f"w4b_draft_{TAG}",
            )
            check("draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id") or "")
            IDS["contract_ids"].append(cid)
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w4b_approve_{TAG}",
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
                    reason=f"w4b_period_{TAG}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")
            if pid:
                IDS["period_ids"].append(pid)

            # --- Native preview first (full SOD / journal path) ---
            preview = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                period_id=pid or None,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w4b_preview_{TAG}",
            )
            check("preview ok", preview.get("ok") is True, preview)
            prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
            IDS["preview_run_ids"].append(prid)

            created = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"w4b_create_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("create close run", created.get("ok") is True, created)
            run = created.get("close_run") or {}
            crid = str(run.get("close_run_id") or "")
            IDS["close_run_ids"].append(crid)
            check("native authority", run.get("money_authority") == "preview_non_authoritative", run)
            check("payment disabled on run", run.get("payment_processing") == "disabled", run)

            replay = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"w4b_create_idem_{TAG}",
            )
            check("create idempotent", replay.get("idempotent") is True, replay)

            sod_bad = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4b_sod_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod blocked before submit or bad status", sod_bad.get("ok") is False, sod_bad)

            submitted = w4.submit_close_run_for_review(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_submit_{TAG}",
                expected_row_version=int((replay.get("close_run") or run).get("row_version") or 1),
            )
            check("submit review", submitted.get("ok") is True, submitted)
            run = submitted.get("close_run") or {}

            self_approve = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_self_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self approve forbidden", self_approve.get("error") == "self_approval_forbidden", self_approve)

            sod_approve = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4b_sod_approve_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod approve+export blocked", sod_approve.get("error") == "sod_approve_export_conflict", sod_approve)

            approved_run = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4b_approve_run_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("approve ok", approved_run.get("ok") is True, approved_run)
            run = approved_run.get("close_run") or {}

            close_sod = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4b_close_sod_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check(
                "sod close+export blocked",
                close_sod.get("error") in ("sod_close_export_conflict", "sod_approve_export_conflict"),
                close_sod,
            )

            self_close = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_self_close_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self close forbidden", self_close.get("error") == "self_close_forbidden", self_close)

            closed = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4b_close_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("close ok", closed.get("ok") is True, closed)
            run = closed.get("close_run") or {}
            check("closed status", run.get("status") == "closed", run)
            check("snapshot immutable", run.get("snapshot_immutable") is True, run)
            check("snapshot fingerprint", bool(run.get("snapshot_fingerprint")), run)
            snap_fp = str(run.get("snapshot_fingerprint") or "")

            immut = w4.mutate_closed_run_forbidden(cur, company_code=COMPANY, close_run_id=crid)
            check("immutable probe", immut.get("error") == "closed_run_immutable", immut)

            re_close = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4b_reclose_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("reclose blocked", re_close.get("error") == "closed_run_immutable", re_close)

            bad_journal = w4.generate_journal_draft(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_journal_bad_{TAG}",
            )
            check("invalid mapping fail closed", bad_journal.get("error") == "invalid_mapping_fail_closed", bad_journal)

            for code, kind, acct, side in [
                ("BASIC", "earning", "5100.BASIC", "debit"),
                ("TRANSPORT", "allowance", "5100.TRANSPORT", "debit"),
                ("NET_PAYABLE", "net_payable", "2100.NET", "credit"),
            ]:
                m = w4.upsert_account_mapping(
                    cur,
                    company_code=COMPANY,
                    component_code=code,
                    component_kind=kind,
                    account_code=acct,
                    journal_side=side,
                    cost_centre="CC-HR",
                    actor_phone=APPROVER,
                    reason=f"w4b_map_{code}_{TAG}",
                )
                check(f"mapping {code}", m.get("ok") is True, m)

            journal = w4.generate_journal_draft(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_journal_{TAG}",
            )
            check("journal ok", journal.get("ok") is True, journal)
            jd = journal.get("journal_draft") or {}
            check("journal balanced", jd.get("balanced") is True, jd)
            check("journal no erp", jd.get("posts_to_erp") is False, jd)
            jid = str(jd.get("journal_draft_id") or "")
            IDS["journal_draft_ids"].append(jid)

            journal_idem = w4.generate_journal_draft(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_journal_idem_{TAG}",
            )
            check("journal idempotent", journal_idem.get("idempotent") is True, journal_idem)

            bank = w4.generate_bank_export_contract(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_bank_{TAG}",
                employee_iban_placeholders={EMP_KEY: "KW00PLACEHOLDER0001"},
            )
            check("bank contract ok", bank.get("ok") is True, bank)
            be = bank.get("bank_export") or {}
            check("bank no real format", be.get("real_bank_format") is False, be)
            check("bank no connection", be.get("bank_connection") is False, be)
            check("bank no wps", be.get("wps_submission") is False, be)
            bid = str(be.get("bank_export_id") or "")
            IDS["bank_export_ids"].append(bid)

            bank_idem = w4.generate_bank_export_contract(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"w4b_bank_idem_{TAG}",
                employee_iban_placeholders={EMP_KEY: "KW00PLACEHOLDER0001"},
            )
            check("bank idempotent", bank_idem.get("idempotent") is True, bank_idem)

            exp_closer = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=CLOSER,
                reason=f"w4b_exp_closer_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("sod closer≠exporter", exp_closer.get("error") == "sod_close_export_same_actor", exp_closer)

            exp_sod = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4b_exp_sod_{TAG}",
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod export+approve blocked", exp_sod.get("error") == "sod_approve_export_conflict", exp_sod)

            exp = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4b_exp_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export recorded", exp.get("ok") is True, exp)
            fe = exp.get("finance_export") or {}
            feid = str(fe.get("finance_export_id") or "")
            IDS["finance_export_ids"].append(feid)
            check("recon unmatched", fe.get("reconciliation_status") == "unmatched", fe)

            exp_idem = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"w4b_exp_idem_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export idempotent", exp_idem.get("idempotent") is True, exp_idem)

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
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
            )
            check("drift detected", drift.get("drifted") is True, drift)

            cur.execute(
                "UPDATE payroll_journal_drafts SET source_snapshot_fingerprint=%s WHERE journal_draft_id=%s",
                (snap_fp, jid),
            )

            bank_exp = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="bank_contract",
                artifact_id=bid,
                actor_phone=EXPORTER,
                reason=f"w4b_bank_exp_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("bank export recorded", bank_exp.get("ok") is True, bank_exp)
            beid = str((bank_exp.get("finance_export") or {}).get("finance_export_id") or "")
            if beid:
                IDS["finance_export_ids"].append(beid)

            self_exp_appr = w4.approve_finance_export(
                cur,
                company_code=COMPANY,
                finance_export_id=feid,
                actor_phone=EXPORTER,
                reason=f"w4b_exp_self_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export self approve forbidden", self_exp_appr.get("error") == "self_approval_forbidden", self_exp_appr)

            exp_appr = w4.approve_finance_export(
                cur,
                company_code=COMPANY,
                finance_export_id=feid,
                actor_phone=EXPORTER2,
                reason=f"w4b_exp_appr_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("export approved", exp_appr.get("ok") is True, exp_appr)
            check(
                "recon matched",
                (exp_appr.get("finance_export") or {}).get("reconciliation_status") == "matched",
                exp_appr,
            )

            hist = w4.list_finance_exports(cur, company_code=COMPANY, close_run_id=crid)
            check("export history", len(hist) >= 2, len(hist))

            same_reopen = w4.initiate_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4b_reopen1_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen initiate", same_reopen.get("ok") is True, same_reopen)
            dual_id = str((same_reopen.get("dual_control") or {}).get("action_id") or "")

            same_actor = w4.confirm_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"w4b_reopen_same_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen same actor denied", same_actor.get("error") == "dual_control_same_actor", same_actor)

            reopened = w4.confirm_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"w4b_reopen2_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen confirmed", reopened.get("ok") is True, reopened)
            check("reopened status", (reopened.get("close_run") or {}).get("status") == "reopened", reopened)

            # --- External path for authority check ---
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w4b_ext_mode_{TAG}"
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
                reason=f"w4b_export_{TAG}",
            )
            check("external export", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
            IDS["export_run_ids"].append(eid)
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload = dict(cur.fetchone())["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=f"EXT-W4B-{TAG}")
            imported = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w4b_import_{TAG}",
            )
            check("external import", imported.get("ok") is True, imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id") or "")
            IDS["import_run_ids"].append(iid)

            ext_created = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="external_import",
                source_run_id=iid,
                actor_phone=CREATOR,
                reason=f"w4b_ext_create_{TAG}",
            )
            check("external close create", ext_created.get("ok") is True, ext_created)
            ext_run = ext_created.get("close_run") or {}
            ext_crid = str(ext_run.get("close_run_id") or "")
            if ext_crid:
                IDS["close_run_ids"].append(ext_crid)
            check("external authority retained", ext_run.get("money_authority") == "external", ext_created)

            restore = IDS["prior_mode"] if IDS["prior_mode"] in ("native", "external", "parallel_shadow") else "external"
            restored = pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode=restore, actor_phone=APPROVER, reason=f"w4b_restore_{TAG}"
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
        "wave": "4-B",
        "payment_processing": "disabled",
        "posts_payment": False,
        "journal_drafts": True,
        "journals": False,
        "bank_export_contract": True,
        "bank_files": False,
        "bank_connection": False,
        "wps": False,
        "ashal": False,
        "pifss": False,
        "eos": False,
        "ai_calculations": False,
        "native_results_authoritative": False,
        "external_payroll_authority": "external",
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("QUALIFICATION_JSON", EVID / "qualification.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
