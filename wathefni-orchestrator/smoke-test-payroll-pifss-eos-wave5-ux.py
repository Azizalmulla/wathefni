#!/usr/bin/env python3
"""Payroll Wave 5 — static UX smoke (EN/AR/mobile)."""
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
    print("    payroll pifss eos wave5 UX EN/AR/mobile")
    roots = [
        Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    dash = next((p for p in roots if (p / "payrollStatutoryUx.ts").exists()), None)
    check("posthire dir", dash is not None, roots)
    if not dash:
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1

    ux_path = dash / "payrollStatutoryUx.ts"
    ws_path = dash / "StatutoryWorksheetWorkspace.tsx"
    post_path = dash / "PostHire.tsx"

    check("ux file", ux_path.exists(), ux_path)
    check("workspace file", ws_path.exists(), ws_path)
    check("posthire file", post_path.exists(), post_path)
    if not ux_path.exists() or not ws_path.exists():
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1

    ux = ux_path.read_text(encoding="utf-8")
    ws = ws_path.read_text(encoding="utf-8")
    post = post_path.read_text(encoding="utf-8") if post_path.exists() else ""

    check("EN title", "PIFSS & EOS review worksheets" in ux)
    check("AR title", "أوراق مراجعة التأمينات ومكافأة نهاية الخدمة" in ux)
    check(
        "honesty EN",
        "non-authoritative" in ux.lower() or "review worksheet" in ux.lower() or "review documents" in ux.lower(),
    )
    check("honesty AR", "غير ملزمة" in ux or "مراجعة" in ux)
    check("payment disabled EN", "Payment processing: disabled" in ux)
    check("payment disabled AR", "معالجة الدفع: معطّلة" in ux)
    check("no remittance EN", "No remittance" in ux or "remittance" in ux.lower())
    check("no remittance AR", "بلا تحويل" in ux or "تحويل" in ux)
    check("counsel EN", "counsel" in ux.lower())
    check("counsel AR", "مستشار" in ux)
    check("workspace rtl", "dir={isAr" in ws or 'dir={isAr ? "rtl"' in ws or "rtl" in ws)
    check("mobile hint", "mobileHint" in ux and "md:hidden" in ws)
    check("testid", 'data-testid="statutory-worksheet-workspace"' in ws)
    tab_wired = (
        "StatutoryWorksheetWorkspace" in post
        or ("CloseExportWorkspace" in post and "payroll-tab-close-export" in post)
    )
    check("posthire tab", tab_wired, "StatutoryWorksheetWorkspace or CloseExportWorkspace")
    check("review only", "Review only" in ux or "مراجعة فقط" in ux)

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
