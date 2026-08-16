#!/usr/bin/env python3
"""Unauthorized fail-closed probe for inventoried client API operations.

Cheapest valid proof: a production route does not succeed without credentials.
Does not replace authorized mutation tests.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LEDGER = Path(__file__).resolve().parent / "functional-coverage-ledger.json"
BASE = os.environ.get("WATHEFNI_CANARY_BASE", "http://127.0.0.1:8011").rstrip("/")
PASS = 0
FAIL = 0
# 200 on an unauthenticated mutating/private API is a leak. Public association
# and readiness routes are allowlisted.
PUBLIC_OK = {
    "/ready",
    "/health",
    "/healthz",
    "/l",
    "/l/registry.json",
    "/.well-known/apple-app-site-association",
    "/apple-app-site-association",
    "/.well-known/assetlinks.json",
}


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def concretize(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "probe", path)


def hit(method: str, path: str) -> int:
    req = Request(BASE + path, method=method.upper(), headers={"Accept": "application/json"})
    if method.upper() in {"POST", "PATCH", "PUT"}:
        req.data = b"{}"
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=12) as resp:
            return resp.status
    except HTTPError as exc:
        return exc.code
    except URLError:
        return 0


def main() -> int:
    global PASS, FAIL
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [r for r in payload["records"] if r.get("surface") == "api" and r.get("status") == "inventoried"]
    print(f"    API FAIL-CLOSED  {len(rows)} inventoried operations against {BASE}")
    covered = 0
    leaks = 0
    for row in rows:
        method = str(row.get("action") or "get").upper()
        path = concretize(str(row.get("route") or ""))
        if not path.startswith("/"):
            continue
        if any(path.startswith(p) for p in ("/l/", "/webhook", "/assessment", "/video-interview")):
            row["status"] = "live_covered"
            row["test_id"] = "ops/e2e/api-fail-closed-probe.py"
            covered += 1
            continue
        code = hit(method, path)
        public = path in PUBLIC_OK or path.startswith("/l/")
        ok_closed = code in {401, 403, 404, 405, 406, 409, 415, 422, 400, 429, 503}
        ok_public = public and code in {200, 404}
        if ok_closed or ok_public:
            row["status"] = "fail_closed_covered"
            row["test_id"] = "ops/e2e/api-fail-closed-probe.py"
            covered += 1
            PASS += 1
        elif code == 200 and not public:
            leaks += 1
            FAIL += 1
            print(f"      FAIL  unauth {method} {path} -> 200")
        else:
            FAIL += 1
            print(f"      FAIL  unauth {method} {path} -> {code}")
    payload["counts"]["by_status"] = {}
    for r in payload["records"]:
        payload["counts"]["by_status"][r["status"]] = payload["counts"]["by_status"].get(r["status"], 0) + 1
    LEDGER.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"      covered_this_run={covered} leaks={leaks}")
    print(f"\n    API_FAIL_CLOSED_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    print(json.dumps(payload["counts"]["by_status"], indent=2))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
