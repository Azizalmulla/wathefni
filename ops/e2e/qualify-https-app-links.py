#!/usr/bin/env python3
"""HTTP qualify every registered HTTPS app-link destination. No screenshots."""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

PASS = 0
FAIL = 0
BASE = os.environ.get("WATHEFNI_APP_LINK_BASE", "http://127.0.0.1:8011").rstrip("/")
EXPECTED_IOS_APP_ID = os.environ.get("WATHEFNI_EXPECTED_IOS_APP_ID", "").strip()
EXPECTED_ANDROID_CERTS = {
    part.strip().upper()
    for part in os.environ.get("WATHEFNI_EXPECTED_ANDROID_SHA256_CERTS", "").split(",")
    if part.strip()
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect())


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
        with OPENER.open(req, timeout=20) as resp:
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
        parsed = urlsplit(https)
        path = parsed.path if parsed.scheme == "https" and parsed.hostname == "api.octo-hr.com" else ""
        if not path:
            check(f"destination has path {row.get('slug')}", False, https)
            continue
        status, html, _ = http(path)
        check(
            f"{path} serves fallback HTML",
            status == 200 and "wathefni://" in html and "Open in OctoHR" in html,
            status,
        )
        check(f"{path} preserves custom scheme", f"wathefni://{str(row.get('app_path') or '/').lstrip('/')}" in html, html[:120])
    missing_status, missing_html, _ = http("/l/definitely-not-a-registered-slug")
    check("unknown slug fails closed 404", missing_status == 404, missing_status)
    check("unknown slug still offers store fallback", "App Store" in missing_html and "Google Play" in missing_html)
    aasa_status, aasa_body, aasa_type = http("/.well-known/apple-app-site-association")
    check("AASA is served directly without a redirect", aasa_status == 200, (aasa_status, aasa_type))
    check("AASA content type is application/json", "application/json" in aasa_type.lower(), aasa_type)
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
        if EXPECTED_IOS_APP_ID:
            check("AASA has exactly the expected production application identifier", app_ids == [EXPECTED_IOS_APP_ID], app_ids)
        else:
            check(
                "AASA has the stable production application identifier",
                any(re.fullmatch(r"[A-Z0-9]{10}\.ai\.wathefni\.employee", app_id) for app_id in app_ids),
                app_ids,
            )
        paths = [row.get("paths") for row in aasa_details if isinstance(row, dict)]
        check("AASA covers only the registered OctoHR link paths", paths == [["/l", "/l/*"]], paths)
    asset_status, asset_body, asset_type = http("/.well-known/assetlinks.json")
    check("assetlinks is served directly without a redirect", asset_status == 200, asset_status)
    check("assetlinks content type is application/json", "application/json" in asset_type.lower(), asset_type)
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
            str(value).upper()
            for target in android_targets
            if target.get("namespace") == "android_app" and target.get("package_name") == "ai.wathefni.employee"
            for value in (target.get("sha256_cert_fingerprints") or [])
        ]
        check(
            "assetlinks has the production package, relation, and valid SHA-256 certificates",
            bool(fingerprints) and all(re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}", value) for value in fingerprints),
            "malformed or wrong-package association",
        )
        if EXPECTED_ANDROID_CERTS:
            check(
                "assetlinks has exactly every expected production app-signing certificate",
                set(fingerprints) == EXPECTED_ANDROID_CERTS,
                {"expected": sorted(EXPECTED_ANDROID_CERTS), "actual": sorted(fingerprints)},
            )
    print(f"\n    HTTPS_APP_LINKS_LIVE_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    if owner_blockers:
        print(f"      OWNER_BLOCKED  provision {', '.join(owner_blockers)}; installed-app intercept cannot verify yet")
    if FAIL:
        return 1
    return 2 if owner_blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
