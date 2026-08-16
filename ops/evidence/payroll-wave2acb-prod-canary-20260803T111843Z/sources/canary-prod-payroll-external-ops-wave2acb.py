#!/usr/bin/env python3
"""Payroll Wave 2A-C-B — production synthetic external-ops canary.

Synthetic subjects only (PYW2ACB / 965540*).
Proves: readiness, assemble/export, upload/replace, quarantine, reconciliation,
fingerprint drift, history/events, manager-scope empty set, permissions surface,
imported results never authoritative, residual cleanup.

Does NOT: real vendor, bank files, native G2N, real employee compensation mutation
beyond temporary synthetic rows cleaned up.
money_authority=external; payment_processing=disabled; vendor_claimed=false.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
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
os.environ.setdefault(
    "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS",
    "PYW2ACB,PYW2ACB-SYNTH|,PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|",
)
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES", "965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW2ACB_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW2ACB-{TAG}"
REAL_KEY = "WATHEFNI-96566363363"
CREATOR = f"9655403{TAG_DIGITS}"
APPROVER = f"9655404{TAG_DIGITS}"

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW2ACB_EVID") or f"/tmp/payroll-w2acb-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER},
    "export_run_ids": [],
    "import_run_ids": [],
    "period_ids": [],
    "contract_ids": [],
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


def _payload(cur, export_run_id: str) -> dict[str, Any]:
    cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (export_run_id,))
    row = dict(cur.fetchone())
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload


def cleanup(cur) -> dict[str, Any]:
    deleted: dict[str, int] = {}
    cur.execute(
        """
        SELECT import_run_id::text FROM payroll_adapter_import_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR external_run_id LIKE %s OR artifact_csv LIKE %s)
        """,
        (COMPANY, f"%{TAG}%", f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
    if iids:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["import_lines"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["reconciliations"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["events_import"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["imports"] = cur.rowcount or 0
    cur.execute(
        """
        SELECT export_run_id::text FROM payroll_adapter_export_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR external_run_id LIKE %s OR artifact_csv LIKE %s)
        """,
        (COMPANY, f"%{TAG}%", f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
    if eids:
        cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["recon_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["events_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_quarantine WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["quarantine_by_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["exports"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_adapter_quarantine WHERE company_code=%s AND (reason LIKE %s OR artifact_excerpt LIKE %s)",
        (COMPANY, f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    deleted["quarantine"] = cur.rowcount or 0

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
    pids = [dict(r)["period_id"] for r in cur.fetchall()]
    if pids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, pids),
        )
        cur.execute("DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)", (COMPANY, pids))
        deleted["periods"] = cur.rowcount or 0
    return deleted


def residual(cur) -> int:
    n = 0
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_adapter_export_runs WHERE company_code=%s AND artifact_csv LIKE %s",
        (COMPANY, f"%{EMP_KEY}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM payroll_adapter_import_runs
        WHERE company_code=%s AND (artifact_csv LIKE %s OR external_run_id LIKE %s)
        """,
        (COMPANY, f"%{EMP_KEY}%", f"%{TAG}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave2acb prod synthetic canary tag={TAG}")
    check("wave2a enabled", w2a.payroll_wave2a_enabled())
    check("wave2a company", w2a.payroll_wave2a_enabled_for_company(COMPANY))
    check("synthetic_only on", w2a.payroll_wave2a_synthetic_only())
    honesty = w2a.honesty_payload()
    check("payment disabled", honesty.get("payment_processing") == "disabled")
    check("money authority external", honesty.get("money_authority") == "external")
    check("wathefni not money authority", honesty.get("wathefni_money_authority") is False)
    check("vendor unclaimed", honesty.get("vendor_claimed") is False)
    check("no bank files", honesty.get("bank_files") is False)
    check("no native g2n", honesty.get("native_gross_to_net") is False)
    check("wave1 contracts unchanged", honesty.get("wave1_contracts_unchanged") is True)
    check("wave1 still enabled", pyw1.payroll_wave1_enabled())

    # Permission / route surface
    paths = {getattr(r, "path", None) for r in app.app.routes}
    check("route external workspace", "/dashboard/posthire/payroll/external" in paths)
    check("route readiness", "/dashboard/posthire/payroll/external/readiness" in paths)
    check("route exports", "/dashboard/posthire/payroll/external/exports" in paths)
    check("route quarantine", "/dashboard/posthire/payroll/external/quarantine" in paths)
    check("route events", "/dashboard/posthire/payroll/external/events" in paths)
    check("helper _payroll_w2a_require", callable(getattr(app, "_payroll_w2a_require", None)))
    check("helper scope keys", callable(getattr(app, "_payroll_w2a_scope_keys", None)))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)

            pyw1.ensure_payroll_wave1_schema(cur)
            w2a.ensure_payroll_wave2a_schema(cur)
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w2acb_mode_{TAG}"
            )

            # Refuse real employee
            real_deny = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period={
                    "period_id": str(uuid.uuid4()),
                    "period_start": "2026-12-01",
                    "period_end": "2026-12-07",
                    "attendance_input_source": "legacy_records",
                    "status": "open",
                    "payroll_mode": "external",
                },
                employees=[{"employee_key": REAL_KEY}],
                contracts=[],
                actor_phone=CREATOR,
                reason=f"w2acb_real_deny_{TAG}",
            )
            check("real employee export refused", real_deny.get("error") == "payroll_wave2a_synthetic_only", real_deny)

            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 480, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"w2acb_draft_{TAG}",
            )
            check("synth contract draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            IDS["contract_ids"].append(cid)
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2acb_approve_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("synth contract approve", approved.get("ok") is True, approved)

            p_start = date(2027, 2, 1) + timedelta(days=(int(TAG[:2], 16) % 8))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"w2acb_period_{TAG}",
            )
            check("period create", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            IDS["period_ids"].append(str(period_row.get("period_id") or ""))

            ready = w2a.period_readiness(
                cur, company_code=COMPANY, period_start=str(p_start), period_end=str(p_end)
            )
            check("readiness ready", ready.get("ready") is True, ready)
            check("readiness not authoritative", ready.get("authoritative_in_wathefni") is False)

            boot = w2a.workspace_bootstrap(cur, company_code=COMPANY)
            check("bootstrap ok", boot.get("ok") is True, boot)
            check("bootstrap not authoritative", boot.get("authoritative_in_wathefni") is False)
            check("bootstrap payment disabled", (boot.get("settings") or {}).get("payment_processing") == "disabled")

            empty = w2a.assemble_period_export_inputs(
                cur,
                company_code=COMPANY,
                period_start=str(p_start),
                period_end=str(p_end),
                period_id=str(period_row.get("period_id") or "") or None,
                allowed_employee_keys=set(),
            )
            check("manager empty scope blocks export assembly", len(empty.get("employees") or []) == 0)

            assembled = w2a.assemble_period_export_inputs(
                cur,
                company_code=COMPANY,
                period_start=str(p_start),
                period_end=str(p_end),
                period_id=str(period_row.get("period_id") or "") or None,
            )
            check("assemble has synth employee", any(e.get("employee_key") == EMP_KEY for e in assembled.get("employees") or []))

            exported = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=assembled["period"],
                employees=assembled["employees"],
                contracts=assembled["contracts"],
                actor_phone=CREATOR,
                reason=f"w2acb_export_{TAG}",
            )
            check("export ok", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id"))
            IDS["export_run_ids"].append(eid)
            fp = str(exported.get("input_fingerprint") or (exported.get("export_run") or {}).get("input_fingerprint") or "")

            exports = w2a.list_export_runs(cur, company_code=COMPANY, limit=30)
            check("history list exports", any(str(r.get("export_run_id")) == eid for r in exports))

            payload = _payload(cur, eid)
            result_csv = w2a.build_synthetic_result_csv(
                export_payload=payload, external_run_id=f"EXT-W2ACB-{TAG}"
            )
            imported = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2acb_import_{TAG}",
                expected_input_fingerprint=fp,
            )
            check("upload import ok", imported.get("ok") is True, imported)
            check("import money external", imported.get("money_authority") == "external")
            iid = str((imported.get("import_run") or {}).get("import_run_id"))
            IDS["import_run_ids"].append(iid)

            replay = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2acb_import_replay_{TAG}",
                expected_input_fingerprint=fp,
            )
            check("duplicate upload idempotent", replay.get("idempotent") is True, replay)

            stale = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2acb_stale_{TAG}",
                expected_input_fingerprint="deadbeef" * 4,
            )
            check("fingerprint drift blocked", stale.get("error") == "input_fingerprint_changed", stale)
            check("fingerprint drift quarantined", bool(stale.get("quarantine")), stale)

            bad = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text="not,valid\n1,2",
                actor_phone=APPROVER,
                reason=f"w2acb_malformed_{TAG}",
            )
            check("malformed quarantined", bad.get("ok") is False and bool(bad.get("quarantine")), bad)

            q = w2a.list_quarantine(cur, company_code=COMPANY, limit=100)
            check("quarantine queue non-empty", len(q) >= 1)

            recon = w2a.reconcile_export_import(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                import_run_id=iid,
                actor_phone=APPROVER,
                reason=f"w2acb_recon_{TAG}",
            )
            check("reconcile ok", recon.get("ok") is True, recon)
            stored = w2a.get_reconciliation(cur, company_code=COMPANY, export_run_id=eid, import_run_id=iid)
            check("reconciliation stored", bool(stored), stored)
            lines = w2a.list_import_lines(cur, company_code=COMPANY, import_run_id=iid)
            check("employee-level lines", len(lines) >= 1, lines)

            replace_csv = w2a.build_synthetic_result_csv(
                export_payload=payload, external_run_id=f"EXT-W2ACB-RPL-{TAG}"
            )
            replaced = w2a.replace_import_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=replace_csv,
                actor_phone=APPROVER,
                reason=f"w2acb_replace_{TAG}",
                expected_input_fingerprint=fp,
            )
            check("replace import ok", replaced.get("ok") is True, replaced)
            check("replace flagged", replaced.get("replace") is True)
            check("replace not authoritative", replaced.get("authoritative_in_wathefni") is False)
            check("replace money external", replaced.get("money_authority") == "external")
            if replaced.get("ok"):
                IDS["import_run_ids"].append(str((replaced.get("import_run") or {}).get("import_run_id")))

            events = w2a.list_events(cur, company_code=COMPANY, export_run_id=eid, limit=80)
            check("audit history events", len(events) >= 2, len(events))
            check(
                "replace event in history",
                any(e.get("event_type") == "import_replace_initiated" for e in events),
                events,
            )

            # Native mode readiness blocker then restore
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"w2acb_native_{TAG}"
            )
            blocked = w2a.period_readiness(cur, company_code=COMPANY, period_start=str(p_start), period_end=str(p_end))
            check("native mode blocks readiness", blocked.get("ready") is False, blocked)
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w2acb_restore_{TAG}"
            )

            deleted = cleanup(cur)
            rem = residual(cur)
            check("residual synthetic zero", rem == 0, {"residual": rem, "deleted": deleted})
            conn.commit()

            (EVID / "ids.json").write_text(json.dumps(IDS, indent=2))
            (EVID / "cleanup.json").write_text(json.dumps(deleted, indent=2))
            qual = {
                "wave": "payroll_wave2acb_prod_synthetic",
                "tag": TAG,
                "passed": PASS,
                "failed": FAIL,
                "cleanup": {"deleted": deleted, "residual_total": rem},
                "honesty": {
                    "payment_processing": "disabled",
                    "money_authority": "external",
                    "vendor_claimed": False,
                    "authoritative_in_wathefni": False,
                },
                "results": RESULTS,
            }
            (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
            print(json.dumps({"passed": PASS, "failed": FAIL, "residual": rem}, indent=2))
            return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
