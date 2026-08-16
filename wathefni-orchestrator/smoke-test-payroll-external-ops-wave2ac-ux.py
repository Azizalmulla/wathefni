#!/usr/bin/env python3
"""Payroll Wave 2A-C — EN/AR + mobile UX smoke (static + route surface).

Does not hit production money paths. Safe to run locally or on prod host.
"""
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

    check("workspace file present", "ExternalPayrollWorkspace" in ws)
    check("honesty strip", "moneyAuthority" in ws or "honesty" in ws.lower())
    check("not authoritative banner", "notAuthoritative" in ws or "authoritative" in ws.lower())
    check("quarantine tab", "quarantine" in ws.lower())
    check("replace import", "replaceImport" in ws or "replace" in ws.lower())
    check("rtl dir support", 'dir={isAr ? "rtl"' in ws or "dir={isAr" in ws)
    check("mobile flex wrap", "flex-wrap" in ws)
    check("sm grid breakpoint", "sm:grid-cols" in ws or "lg:grid-cols" in ws)
    check("loading state", "loading" in ws.lower())
    check("error retry", "retry" in ws.lower())
    check("WorkflowEmpty usage", "WorkflowEmpty" in ws)

    check("EN copy title", "External payroll" in ux)
    check("AR copy title", "الرواتب الخارجية" in ux)
    check("EN honesty money authority", "Money authority: external" in ux)
    check("AR honesty money authority", "سلطة المال: خارجي" in ux)
    check("EN not authoritative", "not authoritative" in ux.lower())
    check("AR not authoritative", "ليست مرجعًا" in ux or "مرجع" in ux)
    check("EN fingerprint drift", "Fingerprint drift" in ux)
    check("AR fingerprint drift", "انحراف البصمة" in ux)

    check("PostHire wires workspace", "ExternalPayrollWorkspace" in post)
    check("Payroll tabs external/timesheets", "tabExternal" in post or "surface === 'external'" in post)

    # Route presence when app importable
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
    try:
        import app  # noqa: WPS433

        paths = {getattr(r, "path", None) for r in app.app.routes}
        check("API external workspace route", "/dashboard/posthire/payroll/external" in paths)
        check("API import route pattern", any(
            isinstance(p, str) and p.endswith("/import") and "payroll/external/exports" in p for p in paths
        ))
    except ModuleNotFoundError as exc:
        if exc.name in {"psycopg2", "fastapi"}:
            # Local laptop without orch deps — assert routes in source instead
            app_src = (orch / "app.py").read_text(encoding="utf-8", errors="ignore")
            check("API routes in app.py source", "/dashboard/posthire/payroll/external" in app_src)
            check("API import route in app.py source", "payroll/external/exports/{export_run_id}/import" in app_src)
        else:
            check("API routes importable", False, str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        check("API routes importable", False, str(exc)[:200])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
