#!/usr/bin/env python3
"""HTTP qualify every registered HTTPS app-link destination. No screenshots."""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PASS = 0
FAIL = 0
BASE = os.environ.get("WATHEFNI_APP_LINK_BASE", "http://127.0.0.1:8011").rstrip("/")


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def http(path: str) -> tuple[int, str, str]:
    req = Request(BASE + path, headers={"Accept": "text/html, application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, body, ctype
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, exc.headers.get("Content-Type", "") if exc.headers else ""
    except URLError as exc:
        return 0, str(exc.reason or exc), ""


def main() -> int:
    owner_blockers: list[str] = []
    print(f"    HTTPS APP LINKS — live {BASE}")
    code, body, _ = http("/l/registry.json")
    check("registry is reachable", code == 200, code)
    try:
        registry = json.loads(body) if code == 200 else {}
    except json.JSONDecodeError:
        registry = {}
        check("registry is JSON", False, body[:180])
    dests = registry.get("destinations") or []
    check("registry lists destinations", len(dests) >= 20, len(dests))
    for row in dests:
        https = str(row.get("https") or "")
        path = https.split("api.wathefni.ai", 1)[-1] if "api.wathefni.ai" in https else ""
        if not path:
            check(f"destination has path {row.get('slug')}", False, https)
            continue
        status, html, _ = http(path)
        check(
            f"{path} serves fallback HTML",
            status == 200 and "wathefni://" in html and "Open in Wathefni" in html,
            status,
        )
        check(f"{path} preserves custom scheme", f"wathefni://{str(row.get('app_path') or '/').lstrip('/')}" in html, html[:120])
    missing_status, missing_html, _ = http("/l/definitely-not-a-registered-slug")
    check("unknown slug fails closed 404", missing_status == 404, missing_status)
    check("unknown slug still offers store fallback", "App Store" in missing_html and "Google Play" in missing_html)
    aasa_status, aasa_body, aasa_type = http("/.well-known/apple-app-site-association")
    check("AASA is served", aasa_status == 200, (aasa_status, aasa_type))
    try:
        aasa = json.loads(aasa_body) if aasa_status == 200 else {}
    except json.JSONDecodeError:
        aasa = {}
    check("AASA has applinks", isinstance(aasa.get("applinks"), dict), aasa_body[:160])
    aasa_details = (aasa.get("applinks") or {}).get("details") or []
    if not aasa_details:
        owner_blockers.append("WATHEFNI_IOS_APP_ID")
    else:
        app_ids = [str(row.get("appID") or "") for row in aasa_details if isinstance(row, dict)]
        check(
            "AASA has a production Wathefni application identifier",
            any(re.fullmatch(r"[A-Z0-9]{10}\.ai\.wathefni\.employee", app_id) for app_id in app_ids),
            app_ids,
        )
    asset_status, asset_body, _ = http("/.well-known/assetlinks.json")
    check("assetlinks is served", asset_status == 200, asset_status)
    try:
        assets = json.loads(asset_body) if asset_status == 200 else None
    except json.JSONDecodeError:
        assets = None
    check("assetlinks is a JSON list", isinstance(assets, list), asset_body[:160])
    if not assets:
        owner_blockers.append("WATHEFNI_ANDROID_SHA256_CERTS")
    else:
        android_targets = [
            row.get("target") or {}
            for row in assets
            if isinstance(row, dict) and "delegate_permission/common.handle_all_urls" in (row.get("relation") or [])
        ]
        fingerprints = [
            str(value)
            for target in android_targets
            if target.get("namespace") == "android_app" and target.get("package_name") == "ai.wathefni.employee"
            for value in (target.get("sha256_cert_fingerprints") or [])
        ]
        check(
            "assetlinks has the production package and SHA-256 certificate",
            any(re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}", value.upper()) for value in fingerprints),
            "malformed or wrong-package association",
        )
    print(f"\n    HTTPS_APP_LINKS_LIVE_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    if owner_blockers:
        print(f"      OWNER_BLOCKED  provision {', '.join(owner_blockers)}; installed-app intercept cannot verify yet")
    if FAIL:
        return 1
    return 2 if owner_blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
