#!/usr/bin/env python3
"""HTTPS App Link registry + association documents."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0
ROOT = Path(__file__).resolve().parent


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
    sys.path.insert(0, str(ROOT))
    import app_links

    print("    APP LINKS — unit")
    dests = app_links.registered_destinations()
    check("employee leave HTTPS destination exists", any(d["slug"] == "leave" for d in dests))
    check("HR people HTTPS destination exists", any(d["slug"] == "hr/people" for d in dests))
    check("unknown slug fails closed", app_links.resolve_slug(["nope-not-a-surface"]) is None)
    check("leave slug resolves to /leave", (app_links.resolve_slug(["leave"]) or {}).get("app_path") == "/leave")
    check("custom scheme preserved in fallback HTML", "wathefni://" in app_links._fallback_html(app_links.EMPLOYEE_DESTINATIONS["leave"], missing=False))
    aasa = app_links.aasa_document()
    check("AASA has applinks key", "applinks" in aasa)
    os.environ.pop("WATHEFNI_IOS_APP_ID", None)
    os.environ.pop("WATHEFNI_ANDROID_SHA256_CERTS", None)
    check("AASA details empty until team id is provisioned", app_links.aasa_document()["applinks"]["details"] == [])
    check("assetlinks empty until cert fingerprints are provisioned", app_links.assetlinks_document() == [])
    os.environ["WATHEFNI_IOS_APP_ID"] = "A1B2C3D4E5.ai.wathefni.employee"
    check(
        "AASA includes the exact appID when configured",
        app_links.aasa_document()["applinks"]["details"][0]["appID"] == "A1B2C3D4E5.ai.wathefni.employee",
    )
    fp1 = ":".join(["AA"] * 32)
    fp2 = ":".join(["BB"] * 32)
    os.environ["WATHEFNI_ANDROID_SHA256_CERTS"] = f"{fp1}, {fp2.lower()}"
    assetlinks = app_links.assetlinks_document()
    check(
        "assetlinks preserves every comma-separated certificate",
        assetlinks[0]["target"]["sha256_cert_fingerprints"] == [fp1, fp2],
    )
    check(
        "assetlinks uses the canonical Android package and relation",
        assetlinks[0]["target"]["package_name"] == "ai.wathefni.employee"
        and assetlinks[0]["relation"] == ["delegate_permission/common.handle_all_urls"],
    )
    app_json = (ROOT.parent / "apps" / "wathefni-employee-mobile" / "app.json").read_text(encoding="utf-8")
    check("iOS associatedDomains lists canonical api.octo-hr.com", "applinks:api.octo-hr.com" in app_json)
    check("iOS associatedDomains preserves api.wathefni.ai", "applinks:api.wathefni.ai" in app_json)
    check("Android intentFilters include canonical and legacy hosts", all(host in app_json for host in ("api.octo-hr.com", "api.wathefni.ai")) and "pathPrefix" in app_json)
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    emp_layout = (ROOT.parent / "apps" / "wathefni-employee-mobile" / "app" / "_layout.tsx").read_text(encoding="utf-8")
    hr_layout = (ROOT.parent / "apps" / "wathefni-employee-mobile" / "app" / "hr" / "_layout.tsx").read_text(encoding="utf-8")
    check("employee layout stashes HTTPS links until signed in", "pendingHttpsHref" in emp_layout and "signedIn" in emp_layout)
    check("HR layout stashes HTTPS links until signed in", "pendingHttpsHref" in hr_layout)
    check("employee layout never routes HTTPS /hr destinations", "href.startsWith('/hr')" in emp_layout)
    check("HR layout only routes HTTPS /hr destinations", "href.startsWith('/hr')" in hr_layout)
    access = (ROOT.parent / "apps" / "wathefni-employee-mobile" / "src" / "capabilities.ts").read_text(encoding="utf-8")
    check("module/app disabled is a first-class access state", "app_disabled" in access and "company_app_disabled" in access)
    check("allowlist/permission denial is a first-class access state", "not_allowlisted" in access)

    print(f"\n    APP_LINKS_UNIT_{'PASS' if not FAIL else 'FAIL'}")
    print(f"    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
