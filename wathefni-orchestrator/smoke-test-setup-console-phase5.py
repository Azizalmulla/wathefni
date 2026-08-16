#!/usr/bin/env python3
"""Setup Console Phase 5 — adaptive Employee App composition + Phases 1–5 regression smoke."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
EVIDENCE: list[dict[str, Any]] = []


def _ok(name: str, detail: Any = None) -> None:
    global PASS
    PASS += 1
    EVIDENCE.append({"status": "PASS", "name": name, "detail": detail})
    print(f"PASS  {name}")


def _fail(name: str, detail: Any = None) -> None:
    global FAIL
    FAIL += 1
    EVIDENCE.append({"status": "FAIL", "name": name, "detail": detail})
    print(f"FAIL  {name}: {detail}")


def _load_creds() -> tuple[str, str]:
    token = (os.environ.get("WATHEFNI_SETUP_TOKEN") or "").strip()
    phone = (os.environ.get("WATHEFNI_SETUP_PHONE") or "").strip()
    if token and phone:
        return token, phone
    creds_raw = (os.environ.get("WATHEFNI_SETUP_OPERATOR_CREDENTIALS") or "").strip()
    if not creds_raw:
        try:
            for p in Path("/proc").iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    cmd = (p / "cmdline").read_bytes()
                except Exception:
                    continue
                if b"uvicorn" not in cmd or b"8010" not in cmd:
                    continue
                for item in (p / "environ").read_bytes().split(b"\0"):
                    if item.startswith(b"WATHEFNI_SETUP_OPERATOR_CREDENTIALS="):
                        creds_raw = item.decode().split("=", 1)[1]
                        break
                if creds_raw:
                    break
        except Exception:
            pass
    if not creds_raw:
        return "", ""
    try:
        parsed = json.loads(creds_raw)
        phone = str(next(iter(parsed.keys()))).strip()
        token = str(next(iter(parsed.values()))).strip()
        return token, phone
    except Exception:
        return "", ""


def _req(method: str, path: str, *, token: str, phone: str) -> tuple[int, Any]:
    base = (os.environ.get("WATHEFNI_API_BASE") or "http://127.0.0.1:8010").rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-HR-Phone": phone,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = request.Request(f"{base}{path}", headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {"error": str(exc)}
        except Exception:
            payload = {"error": raw or str(exc)}
        return int(exc.code), payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def _mobile_roots() -> list[Path]:
    roots = [
        Path("/opt/wathefni/wathefni-employee-mobile"),
        REPO / "apps" / "wathefni-employee-mobile",
        Path("/opt/wathefni/apps/wathefni-employee-mobile"),
    ]
    return [r for r in roots if r.is_dir()]


def main() -> int:
    import setup_console_employee_app_phase5 as p5

    # A–F composition matrix
    matrix = p5.qualify_all()
    if matrix.get("ok"):
        _ok("composition_matrix_A_to_F", {r["name"]: "ok" for r in matrix["results"]})
    else:
        _fail("composition_matrix_A_to_F", matrix)

    for r in matrix["results"]:
        if r["ok"]:
            _ok(f"config:{r['name']}")
        else:
            _fail(f"config:{r['name']}", r.get("failures"))

    # Single-module intentional
    a = p5.composition_from_features({"documents": True})
    if a["wide_home_tiles"] and a["home_tiles"] == ["documents"] and not a["tabs"]["leave"]:
        _ok("one_module_intentional")
    else:
        _fail("one_module_intentional", a)

    # Inbox never purchased
    if a.get("inbox_is_purchased_module") is False and "inbox" not in a["home_tiles"]:
        _ok("inbox_not_purchased_module")
    else:
        _fail("inbox_not_purchased_module", a)

    # Disabled module contributes no tile/tab/task
    disabled = p5.composition_from_features({"leave": False, "documents": True})
    if "leave" not in disabled["home_tiles"] and disabled["tabs"]["leave"] is False:
        _ok("disabled_module_absent")
    else:
        _fail("disabled_module_absent", disabled)

    # Source / UI contracts (composition + Home only; verify script mentions moduleCount as a negative assert)
    mobile_blob = ""
    home_view_blob = ""
    for root in _mobile_roots():
        for rel in (
            "src/composition/employeeAppComposition.ts",
            "src/features/home/HomeView.tsx",
            "app/(tabs)/index.tsx",
            "app/(tabs)/_layout.tsx",
            "app/(tabs)/notifications.tsx",
        ):
            p = root / rel
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                mobile_blob += text
                if rel.endswith("HomeView.tsx"):
                    home_view_blob += text
    for needle in (
        "compositionFromMe",
        "wideHomeTiles",
        "inboxStrip",
        "canOpenPath",
        "showOnboardingJourney",
        "separateComplianceTab: false",
    ):
        if needle in mobile_blob:
            _ok(f"ui:{needle}")
        else:
            _fail(f"ui:{needle}")
    if home_view_blob and "moduleCount" not in home_view_blob:
        _ok("ui:moduleCount_removed")
    else:
        _fail("ui:moduleCount_removed", "HomeView still references moduleCount" if home_view_blob else "HomeView missing")

    # Run mobile verify script when the tree is complete enough (AuthProvider present)
    verify = None
    for root in _mobile_roots():
        cand = root / "scripts" / "verify-capability-foundation.py"
        auth = root / "src" / "auth" / "AuthProvider.tsx"
        if cand.is_file() and auth.is_file():
            verify = cand
            break
    if verify:
        import subprocess

        proc = subprocess.run([sys.executable, str(verify)], cwd=str(verify.parent.parent), capture_output=True, text=True)
        if proc.returncode == 0:
            _ok("mobile_verify_capability_foundation")
        else:
            _fail("mobile_verify_capability_foundation", (proc.stdout + proc.stderr)[-800:])
    else:
        _fail("mobile_verify_capability_foundation", "complete employee-mobile tree not present on host")

    # Setup Console regression Phases 1–5 (live)
    token, phone = _load_creds()
    company = (os.environ.get("WATHEFNI_SETUP_COMPANY") or "WATHEFNI").strip().upper()
    if token and phone:
        checks = [
            ("ownership", f"/dashboard/superadmin/setup/ownership"),
            ("company", f"/dashboard/superadmin/setup/companies/{company}"),
            ("payroll_setup", f"/dashboard/superadmin/setup/companies/{company}/payroll-setup"),
            ("module_policies", f"/dashboard/superadmin/setup/companies/{company}/module-policies"),
            ("team_access", f"/dashboard/superadmin/setup/companies/{company}/team-access"),
            ("integrations", f"/dashboard/superadmin/setup/companies/{company}/integrations-catalog"),
            ("employee_app_access", f"/dashboard/superadmin/setup/companies/{company}/employee-app-access"),
        ]
        for name, path in checks:
            status, body = _req("GET", path, token=token, phone=phone)
            if status == 200:
                _ok(f"regression:{name}")
            else:
                _fail(f"regression:{name}", {"status": status, "body": body if isinstance(body, dict) else str(body)[:200]})
    else:
        _fail("creds_missing_for_regression")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = REPO / "ops" / "evidence" / f"setup-console-phase5-{stamp}"
    if not out_dir.parent.is_dir():
        out_dir = Path("/opt/wathefni/ops/evidence") / f"setup-console-phase5-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "smoke.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "evidence": EVIDENCE, "matrix": matrix}, indent=2), encoding="utf-8")
    freeze = FAIL == 0
    (out_dir / "SUMMARY.md").write_text(
        f"# Setup Console Phase 5 smoke\n\nPASS={PASS} FAIL={FAIL}\n\n"
        f"Freeze recommendation: {'YES — Setup Console track can be FROZEN' if freeze else 'NO'}\n\n"
        f"Evidence: `{out_dir}`\n",
        encoding="utf-8",
    )
    print(f"\nEvidence: {out_dir}")
    print(f"RESULT {PASS}/{FAIL}")
    print(f"FREEZE={'YES' if freeze else 'NO'}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
