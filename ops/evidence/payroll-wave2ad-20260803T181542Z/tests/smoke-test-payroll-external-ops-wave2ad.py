#!/usr/bin/env python3
"""Payroll Wave 2A-D — External Run Operability smoke (adapter + routes).

Proves setup payload, package contents honesty, quarantine acknowledge,
rollback concurrency requirement. Does NOT enable money rails.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = FAIL = 0
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    import payroll_external_adapter_wave2a as w2a
    import payroll_authority_wave1 as w1

    h = w2a.honesty_payload()
    check("payment_processing disabled", h.get("payment_processing") == "disabled")
    check("money_authority external", h.get("money_authority") == "external")
    check("vendor unclaimed", h.get("vendor_claimed") is False)
    check("no AI", h.get("ai") is False)
    check("wave2a contracts unchanged flag", h.get("wave2a_adapter_contracts_unchanged") is True)
    check("operability version", bool(h.get("payroll_wave2ad_operability_version")))
    pkg = h.get("package_contents") or {}
    check("package includes contracts", "approved_compensation_components" in (pkg.get("included") or []))
    check("package excludes attendance live", "attendance_minutes_live" in (pkg.get("not_included_yet") or []))
    check("attendance not packaged flag", pkg.get("attendance_leave_shifts_packaged") is False)
    check("export csv headers present", "employee_key" in (pkg.get("export_csv_headers") or []))
    check("import csv headers present", "opaque_amount" in (pkg.get("import_csv_headers") or []))

    # Concurrency still required for rollback
    denied = w1.require_concurrency(expected_row_version=None, actual_row_version=1)
    check("rollback concurrency required", isinstance(denied, dict) and denied.get("error") == "concurrency_token_required")

    # Source wiring
    app_src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    check("rollback passes expected_row_version", "expected_row_version=request.expected_row_version" in app_src)
    check("quarantine acknowledge route", "/quarantine/{quarantine_id}/acknowledge" in app_src)
    check("acknowledge does not admit money", "money_authority_unchanged" in (ROOT / "payroll_external_adapter_wave2a.py").read_text(encoding="utf-8"))

    # Optional DB path when postgres env present
    pg = os.environ.get("WATHEFNI_POSTGRES_ENV") or os.environ.get("POSTGRES_ENV")
    if pg and Path(pg).is_file() and os.environ.get("WATHEFNI_SKIP_DB") != "1":
        try:
            import app  # noqa: WPS433

            company = "WATHEFNI"
            tag = uuid.uuid4().hex[:8]
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    w2a.ensure_payroll_wave2a_schema(cur, force=True)
                    boot = w2a.workspace_bootstrap(cur, company_code=company)
                    check("workspace has setup", isinstance(boot.get("setup"), dict))
                    check("workspace has package_contents", isinstance(boot.get("package_contents"), dict))
                    # Soft quarantine insert then acknowledge
                    q = w2a._quarantine(
                        cur,
                        company_code=company,
                        source_kind="other",
                        reason=f"wave2ad-ack-{tag}",
                        artifact_excerpt="operability smoke",
                        payload={"tag": tag},
                        actor_phone="96554000001",
                    )
                    qid = str(q.get("quarantine_id"))
                    ack = w2a.acknowledge_quarantine(
                        cur,
                        company_code=company,
                        quarantine_id=qid,
                        actor_phone="96554000001",
                        reason="reviewed exception for smoke",
                    )
                    check("quarantine ack ok", ack.get("ok") is True, ack)
                    check("ack money unchanged", ack.get("money_authority_unchanged") is True)
                    check("ack not authoritative", ack.get("authoritative_in_wathefni") is False)
                    # Idempotent replay
                    ack2 = w2a.acknowledge_quarantine(
                        cur,
                        company_code=company,
                        quarantine_id=qid,
                        actor_phone="96554000001",
                        reason="reviewed exception for smoke again",
                    )
                    check("quarantine ack idempotent", ack2.get("idempotent") is True)
                    # Missing reason denied
                    bad = w2a.acknowledge_quarantine(
                        cur,
                        company_code=company,
                        quarantine_id=qid,
                        actor_phone="96554000001",
                        reason="x",
                    )
                    check("ack reason enforced", bad.get("ok") is False or bad.get("error"), bad)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            check("db operability path", False, str(exc)[:240])
    else:
        check("db path skipped (no postgres env)", True)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
