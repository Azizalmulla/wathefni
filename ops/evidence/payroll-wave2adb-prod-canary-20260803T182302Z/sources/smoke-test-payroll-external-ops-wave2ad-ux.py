#!/usr/bin/env python3
"""Payroll Wave 2A-D — EN/AR + mobile operability UX smoke (static)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = FAIL = 0


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    orch = Path(__file__).resolve().parent
    repo = orch.parent
    candidates = [
        repo / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
        Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/posthire"),
    ]
    posthire = next((p for p in candidates if p.is_dir()), None)
    check("posthire src present", posthire is not None, candidates)
    if not posthire:
        print(f"\n{PASS} passed, {FAIL} failed")
        return 1

    ws = (posthire / "ExternalPayrollWorkspace.tsx").read_text(encoding="utf-8")
    ux = (posthire / "payrollExternalUx.ts").read_text(encoding="utf-8")
    post = (posthire / "PostHire.tsx").read_text(encoding="utf-8")
    payslip = (posthire / "PayslipWorkspace.tsx").read_text(encoding="utf-8")
    close = (posthire / "CloseExportWorkspace.tsx").read_text(encoding="utf-8")
    api = (posthire.parent / "lib" / "api.ts").read_text(encoding="utf-8")

    check("setup panel", "external-payroll-setup" in ws)
    check("checklist panel", "external-payroll-checklist" in ws)
    check("package honesty panel", "external-payroll-package" in ws)
    check("csv help tab", "external-payroll-csv-help" in ws)
    check("rollback sends expected_row_version", "expected_row_version" in ws)
    check("quarantine acknowledge wired", "onAcknowledge" in ws or "acknowledge" in ws.lower())
    check("rtl support", "dir={isAr" in ws)
    check("mobile flex wrap", "flex-wrap" in ws)

    check("EN operator title", "External payroll run" in ux)
    check("AR operator title", "تشغيل الرواتب الخارجية" in ux)
    check("EN who pays copy", "Who pays: external payroll system" in ux)
    check("EN input snapshot", "Input snapshot" in ux)
    check("no primary Fingerprint jargon", "Fingerprint drift" not in ux)
    check("Hours review tab label", "Hours review" in ux)
    check("AR hours review", "مراجعة الساعات" in ux)

    check("PostHire external tab hint", "tabExternalHint" in post)
    check("PostHire hours tab", "payroll-tab-hours-review" in post or "tabTimesheetsHint" in post)
    check("payslip import picker", "payslip-import-run-picker" in payslip)
    check("close import picker", "close-import-run-picker" in close)
    check("no pasted import_run_id placeholder", 'placeholder="import_run_id"' not in close)
    check("api quarantine acknowledge", "postExternalPayrollQuarantineAcknowledge" in api)
    check("api rollback requires row version", "expected_row_version: number" in api)

    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
    app_src = (orch / "app.py").read_text(encoding="utf-8", errors="ignore")
    check("acknowledge route in app", "quarantine/{quarantine_id}/acknowledge" in app_src)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
