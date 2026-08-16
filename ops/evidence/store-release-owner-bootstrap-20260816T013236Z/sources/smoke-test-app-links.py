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
    os.environ["WATHEFNI_IOS_APP_ID"] = "TEAMID.ai.wathefni.employee"
    check("AASA includes appID when configured", app_links.aasa_document()["applinks"]["details"][0]["appID"].endswith("ai.wathefni.employee"))
    app_json = (ROOT.parent / "apps" / "wathefni-employee-mobile" / "app.json").read_text(encoding="utf-8")
    check("iOS associatedDomains lists api.wathefni.ai", "applinks:api.wathefni.ai" in app_json)
    check("Android intentFilters host api.wathefni.ai", "api.wathefni.ai" in app_json and "pathPrefix" in app_json)
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("orchestrator mounts app_links router", "app_links" in src and "include_router" in src)

    print(f"\n    APP_LINKS_UNIT_{'PASS' if not FAIL else 'FAIL'}")
    print(f"    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
