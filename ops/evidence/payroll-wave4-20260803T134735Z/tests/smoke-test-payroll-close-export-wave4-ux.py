#!/usr/bin/env python3
"""Payroll Wave 4 — static UX smoke (EN/AR/mobile)."""
from __future__ import annotations

from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    payroll close export wave4 UX EN/AR/mobile")
    roots = [
        Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    dash = next((p for p in roots if (p / "payrollCloseExportUx.ts").exists()), None)
    check("posthire dir", dash is not None, roots)
    if not dash:
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1

    ux = (dash / "payrollCloseExportUx.ts").read_text(encoding="utf-8")
    ws = (dash / "CloseExportWorkspace.tsx").read_text(encoding="utf-8")
    post = (dash / "PostHire.tsx").read_text(encoding="utf-8") if (dash / "PostHire.tsx").exists() else ""

    check("EN title", "Close & finance export" in ux)
    check("AR title", "الإغلاق وتصدير المالية" in ux)
    check("honesty EN", "validation only" in ux.lower())
    check("honesty AR", "تحقق فقط" in ux)
    check("payment disabled EN", "Payment processing: disabled" in ux)
    check("payment disabled AR", "معالجة الدفع: معطّلة" in ux)
    check("immutable", "immutable" in ux.lower() or "غير قابلة" in ux)
    check("sod", "SOD" in ux or "فصل الصلاحيات" in ux)
    check("workspace rtl", "dir={isAr" in ws or 'dir={isAr ? "rtl"' in ws or "rtl" in ws)
    check("mobile hint", "mobileHint" in ux and "md:hidden" in ws)
    check("testid", 'data-testid="close-export-workspace"' in ws)
    check("posthire tab", "CloseExportWorkspace" in post and "payroll-tab-close-export" in post)
    check("no real bank claim", "no real bank" in ux.lower() or "بلا صيغة بنك" in ux)

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
