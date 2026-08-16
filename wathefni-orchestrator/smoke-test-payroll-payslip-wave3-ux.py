#!/usr/bin/env python3
"""Payroll Wave 3 — EN/AR + mobile UX smoke (static)."""
from __future__ import annotations

from pathlib import Path

PASS = FAIL = 0


def check(label: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label} :: {detail}")


def main() -> int:
    print("    payroll payslip wave3 UX EN/AR/mobile")
    root = Path(__file__).resolve().parents[1]
    # when run from orchestrator cwd on remote, also look relative to repo apps
    candidates = [
        root / "apps" / "wathefni-dashboard" / "src" / "posthire",
        root.parent / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    posthire = next((p for p in candidates if p.exists()), None)
    check("posthire dir", posthire is not None, candidates)
    if not posthire:
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1
    ux = (posthire / "payrollPayslipUx.ts").read_text(encoding="utf-8")
    ws = (posthire / "PayslipWorkspace.tsx").read_text(encoding="utf-8")
    ph = (posthire / "PostHire.tsx").read_text(encoding="utf-8")
    check("EN title", "Payslips" in ux)
    check("AR title", "قسائم الراتب" in ux)
    check("honesty EN", "non-authoritative" in ux.lower())
    check("honesty AR", "غير ملزمة" in ux or "سلطة المال" in ux)
    check("payment disabled EN", "Payment processing: disabled" in ux)
    check("payment disabled AR", "معالجة الدفع: معطّلة" in ux)
    check("history retained", "never deletes" in ux.lower() or "لا يحذف" in ux)
    check("workspace rtl", "rtl" in ws)
    check("mobile hint", "md:hidden" in ws and "mobileHint" in ux)
    check("testid", 'data-testid="payslip-workspace"' in ws)
    check("posthire tab", "payslips" in ph and "PayslipWorkspace" in ph)
    check("tabPayslips copy", "tabPayslips" in ph or "tabPayslips" in (posthire / "payrollExternalUx.ts").read_text())
    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
