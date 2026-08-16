#!/usr/bin/env python3
"""Wathefni mobile E2E release gate.

Pipeline:
  release candidate → fixtures/credentials → Maestro UI (if host ready) →
  API reconcile → SHIP / NO-SHIP

Critical rule: API PASS ≠ MOBILE PASS.
MOBILE_PASS is stamped only when Maestro (or another real UI driver) executed
a flow successfully on a simulator/device.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

APP = ROOT / "apps" / "wathefni-employee-mobile"
MAESTRO_DIR = APP / ".maestro"
HOST_READY = Path(__file__).resolve().parent / "host-readiness.sh"
API_RECONCILE = Path(__file__).resolve().parent / "run-api-reconcile.py"
BS_RUNNER = Path(__file__).resolve().parent / "run-browserstack-maestro.py"
LEAVE_PROVISION = Path(__file__).resolve().parent / "provision-leave-fixture.py"
LEAVE_RECONCILE = Path(__file__).resolve().parent / "reconcile-leave-decision.py"

SUITE = os.environ.get("MOBILE_E2E_SUITE", "smoke").strip()  # smoke | bs-smoke | full
EVID_OVERRIDE = os.environ.get("MOBILE_E2E_EVID", "").strip()
USE_BROWSERSTACK = os.environ.get("MOBILE_E2E_RUNTIME", "").strip().lower() in {"browserstack", "bs"} or (
    bool(os.environ.get("BROWSERSTACK_USERNAME")) and bool(os.environ.get("BROWSERSTACK_ACCESS_KEY"))
    and os.environ.get("MOBILE_E2E_RUNTIME", "auto").strip().lower() != "local"
)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer")
    path_prefix = f"{Path.home()}/.maestro/bin:/opt/homebrew/opt/openjdk@17/bin:/opt/homebrew/opt/openjdk/bin:/opt/homebrew/bin:"
    merged["PATH"] = path_prefix + merged.get("PATH", "")
    for candidate in (
        "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
        "/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home",
    ):
        if Path(candidate, "bin", "java").exists():
            merged["JAVA_HOME"] = candidate
            break
    else:
        # Avoid a stale invalid JAVA_HOME from the caller environment
        if merged.get("JAVA_HOME") and not Path(merged["JAVA_HOME"], "bin", "java").exists():
            merged.pop("JAVA_HOME", None)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=merged, text=True, capture_output=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def flow_files(suite: str) -> list[Path]:
    smoke = sorted((MAESTRO_DIR / "smoke").glob("*.yaml"))
    if suite == "smoke":
        # Unsigned-only by default; credential flows run when env present.
        selected: list[Path] = []
        for path in smoke:
            text = path.read_text()
            needs_creds = "requires_credentials" in text
            needs_session = "requires_session" in text
            if needs_creds:
                if path.name.startswith("01-") and os.environ.get("MAESTRO_HR_EMAIL"):
                    selected.append(path)
                elif path.name.startswith("03-") and os.environ.get("MAESTRO_EMPLOYEE_CODE"):
                    selected.append(path)
                continue
            if needs_session:
                # Tabs after login — only if matching login env present
                if path.name.startswith("02-") and os.environ.get("MAESTRO_HR_EMAIL"):
                    selected.append(path)
                elif path.name.startswith("04-") and os.environ.get("MAESTRO_EMPLOYEE_CODE"):
                    selected.append(path)
                continue
            selected.append(path)
        return selected
    return smoke


def main() -> int:
    load_secrets()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evid = Path(EVID_OVERRIDE) if EVID_OVERRIDE else ROOT / "ops" / "evidence" / f"mobile-e2e-gate-{stamp}"
    evid.mkdir(parents=True, exist_ok=True)
    ui_dir = evid / "ui"
    ui_dir.mkdir(exist_ok=True)

    # 0) Disposable leave fixtures when HR credentials present
    fixture_meta: dict[str, Any] = {"skipped": True}
    if os.environ.get("MOBILE_E2E_HR_EMAIL") or os.environ.get("MAESTRO_HR_EMAIL"):
        if os.environ.get("MOBILE_E2E_SKIP_FIXTURES", "").strip() not in {"1", "true", "yes"}:
            prov = run(
                [sys.executable, str(LEAVE_PROVISION), "--evidence", str(evid / "fixtures")],
                cwd=ROOT,
            )
            (evid / "fixtures.stdout.txt").write_text(prov.stdout)
            (evid / "fixtures.stderr.txt").write_text(prov.stderr)
            try:
                fixture_meta = json.loads(prov.stdout.strip().splitlines()[-1]) if prov.stdout.strip() else {"ok": False}
            except json.JSONDecodeError:
                fixture_meta = {"ok": False, "parse_error": True, "rc": prov.returncode}
            load_secrets()

    # 1) Host readiness
    ready_json = evid / "host-readiness.json"
    ready = run(["bash", str(HOST_READY), str(ready_json)])
    (evid / "host-readiness.stdout.txt").write_text(ready.stdout)
    (evid / "host-readiness.stderr.txt").write_text(ready.stderr)
    try:
        host = json.loads(ready_json.read_text()) if ready_json.exists() else {"ui_runtime_ready": False, "blockers": ["host_readiness_failed"]}
    except json.JSONDecodeError:
        host = {"ui_runtime_ready": False, "blockers": ["host_readiness_json_invalid"]}

    ui_ready = bool(host.get("ui_runtime_ready"))
    matrix: list[dict[str, Any]] = []
    bs_summary: dict[str, Any] = {}

    # 2) UI driver: BrowserStack real device preferred when credentials present
    flows = flow_files(SUITE) if not USE_BROWSERSTACK else []
    write_json(evid / "selected-flows.json", [str(p.relative_to(ROOT)) for p in flows] if flows else ["browserstack:" + SUITE])

    if USE_BROWSERSTACK:
        bs_env = os.environ.copy()
        bs_env["MOBILE_E2E_EVID"] = str(evid)
        if SUITE == "smoke":
            bs_env["MOBILE_E2E_SUITE"] = "bs-smoke"
        print(json.dumps({"phase": "browserstack", "suite": bs_env.get("MOBILE_E2E_SUITE")}))
        bs = run([sys.executable, str(BS_RUNNER)], env=bs_env)
        (evid / "browserstack.stdout.txt").write_text(bs.stdout)
        (evid / "browserstack.stderr.txt").write_text(bs.stderr)
        summary_path = evid / "browserstack" / "SUMMARY.json"
        if summary_path.exists():
            bs_summary = json.loads(summary_path.read_text())
            mobile_n = int(bs_summary.get("MOBILE_PASS") or 0)
            flows_detail = bs_summary.get("flows") or []
            if flows_detail:
                for flow in flows_detail:
                    name = str(flow.get("flow") or "")
                    stem = Path(name).stem if name else "unknown"
                    st = (flow.get("status") or "").lower()
                    matrix.append(
                        {
                            "id": f"UI.{stem}",
                            "flow": name,
                            "verdict": "MOBILE_PASS" if st == "passed" else "FAIL",
                            "detail": (
                                f"BrowserStack {flow.get('device')} iOS {flow.get('os_version')} "
                                f"status={st} duration={flow.get('duration')} "
                                f"dashboard={bs_summary.get('dashboard_url')}"
                            ),
                            "dashboard_url": bs_summary.get("dashboard_url"),
                            "video": flow.get("video"),
                            "session_id": flow.get("session_id"),
                        }
                    )
            elif mobile_n > 0 and bs_summary.get("failed_sessions", 0) == 0 and bs_summary.get("error_sessions", 0) == 0:
                matrix.append(
                    {
                        "id": "UI.browserstack.sessions",
                        "flow": "browserstack/" + ",".join(bs_summary.get("execute") or []),
                        "verdict": "MOBILE_PASS",
                        "detail": f"BrowserStack real-device sessions passed={mobile_n} dashboard={bs_summary.get('dashboard_url')}",
                        "dashboard_url": bs_summary.get("dashboard_url"),
                        "build_id": bs_summary.get("build_id"),
                    }
                )
                for exe in bs_summary.get("execute") or []:
                    matrix.append(
                        {
                            "id": f"UI.{Path(exe).stem}",
                            "flow": exe,
                            "verdict": "MOBILE_PASS",
                            "detail": f"Included in BrowserStack build {bs_summary.get('build_id')}",
                        }
                    )
            elif bs_summary.get("poll_timeout"):
                matrix.append(
                    {
                        "id": "UI.browserstack.sessions",
                        "flow": "browserstack",
                        "verdict": "BLOCKED",
                        "detail": "BrowserStack poll timeout",
                        "dashboard_url": bs_summary.get("dashboard_url"),
                    }
                )
            else:
                matrix.append(
                    {
                        "id": "UI.browserstack.sessions",
                        "flow": "browserstack/" + ",".join(bs_summary.get("execute") or []),
                        "verdict": "FAIL",
                        "detail": bs_summary.get("ship_reason") or f"status={bs_summary.get('status')}",
                        "dashboard_url": bs_summary.get("dashboard_url"),
                        "build_id": bs_summary.get("build_id"),
                    }
                )
        else:
            matrix.append(
                {
                    "id": "UI.browserstack.sessions",
                    "flow": "browserstack",
                    "verdict": "FAIL" if bs.returncode else "BLOCKED",
                    "detail": (bs.stderr or bs.stdout or "BrowserStack runner produced no SUMMARY")[:500],
                }
            )
    elif not ui_ready:
        for path in flows:
            matrix.append(
                {
                    "id": f"UI.{path.stem}",
                    "flow": str(path.relative_to(ROOT)),
                    "verdict": "BLOCKED",
                    "detail": "No simulator/device UI runtime ready: " + ", ".join(host.get("blockers") or []),
                }
            )
    else:
        maestro_bin = shutil.which("maestro", path=f"{Path.home()}/.maestro/bin:/opt/homebrew/bin:" + os.environ.get("PATH", ""))
        if not maestro_bin:
            for path in flows:
                matrix.append(
                    {
                        "id": f"UI.{path.stem}",
                        "flow": str(path.relative_to(ROOT)),
                        "verdict": "BLOCKED",
                        "detail": "maestro CLI not on PATH",
                    }
                )
        else:
            env = os.environ.copy()
            mapping = {
                "MOBILE_E2E_HR_COMPANY": "MAESTRO_HR_COMPANY",
                "MOBILE_E2E_HR_EMAIL": "MAESTRO_HR_EMAIL",
                "MOBILE_E2E_HR_PASSWORD": "MAESTRO_HR_PASSWORD",
                "MOBILE_E2E_EMPLOYEE_PHONE": "MAESTRO_EMPLOYEE_PHONE",
                "MOBILE_E2E_EMPLOYEE_CODE": "MAESTRO_EMPLOYEE_CODE",
            }
            for src, dst in mapping.items():
                if os.environ.get(src) and not env.get(dst):
                    env[dst] = os.environ[src]

            dest_dir = ui_dir / "flows-no-screenshot"
            dest_dir.mkdir(parents=True, exist_ok=True)
            for path in flows:
                text = path.read_text(encoding="utf-8")
                stripped = "\n".join(line for line in text.splitlines() if "takeScreenshot" not in line) + "\n"
                run_path = dest_dir / path.name
                run_path.write_text(stripped, encoding="utf-8")
                out_log = ui_dir / f"{path.stem}.log"
                proc = run(
                    [
                        maestro_bin,
                        "test",
                        str(run_path),
                        "--format",
                        "NOOP",
                    ],
                    cwd=APP,
                    env=env,
                )
                out_log.write_text(proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""))
                if proc.returncode == 0:
                    matrix.append(
                        {
                            "id": f"UI.{path.stem}",
                            "flow": str(path.relative_to(ROOT)),
                            "verdict": "MOBILE_PASS",
                            "detail": "Maestro flow passed on real UI runtime",
                        }
                    )
                else:
                    matrix.append(
                        {
                            "id": f"UI.{path.stem}",
                            "flow": str(path.relative_to(ROOT)),
                            "verdict": "FAIL",
                            "detail": f"Maestro exit {proc.returncode}",
                        }
                    )

    # 3) API reconcile
    api_env = os.environ.copy()
    api_env["MOBILE_E2E_EVID"] = str(evid)
    api = run([sys.executable, str(API_RECONCILE)], env=api_env)
    (evid / "api-reconcile.stdout.txt").write_text(api.stdout)
    (evid / "api-reconcile.stderr.txt").write_text(api.stderr)
    api_summary: dict[str, Any] = {}
    api_path = evid / "api-reconcile.json"
    if api_path.exists():
        api_summary = json.loads(api_path.read_text())
        for r in api_summary.get("rows") or []:
            matrix.append(r)

    # 4) Leave decision reconcile (only when leave fixtures were in play)
    leave_reconcile: dict[str, Any] = {}
    executed = [str(x) for x in (bs_summary.get("execute") or [])]
    leave_ui_ran = any("leave" in x for x in executed)
    if leave_ui_ran or os.environ.get("MAESTRO_LEAVE_ID") or os.environ.get("MAESTRO_LEAVE_REJECT_ID"):
        # After mutation flows, expect decided statuses; before UI, expect requested.
        expect_approve = "approved" if any("leave-approve" in x for x in executed) else "requested"
        expect_reject = "rejected" if any("leave-reject" in x for x in executed) else "requested"
        # If UI failed, still report actual status without forcing FAIL on expected mutation.
        lr = run(
            [
                sys.executable,
                str(LEAVE_RECONCILE),
                "--evidence",
                str(evid),
                "--expect-approve",
                expect_approve,
                "--expect-reject",
                expect_reject,
            ],
            env=os.environ.copy(),
        )
        (evid / "leave-reconcile.stdout.txt").write_text(lr.stdout)
        (evid / "leave-reconcile.stderr.txt").write_text(lr.stderr)
        lr_path = evid / "leave-reconcile.json"
        if lr_path.exists():
            leave_reconcile = json.loads(lr_path.read_text())
            matrix.append(
                {
                    "id": "API.leave.reconcile",
                    "flow": "reconcile-leave-decision",
                    "verdict": "PASS" if leave_reconcile.get("ok") else "FAIL",
                    "detail": json.dumps(
                        {k: (v.get("status") if isinstance(v, dict) else v) for k, v in (leave_reconcile.get("checks") or {}).items()},
                        default=str,
                    )[:400],
                }
            )

    counts: dict[str, int] = {}
    for r in matrix:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    mobile_pass = counts.get("MOBILE_PASS", 0)
    ui_fail = sum(1 for r in matrix if r["id"].startswith("UI.") and r["verdict"] == "FAIL")
    api_fail = counts.get("FAIL", 0) - ui_fail
    if api_fail < 0:
        api_fail = counts.get("FAIL", 0)

    # SHIP rule: need at least unsigned smoke MOBILE_PASS + no UI FAIL + no API FAIL on executed spines
    # Broad release still needs the full matrix; this gate never invents PASS.
    # Foundation stop-point: when leave mutation flows are executed, they must MOBILE_PASS + reconcile.
    ship = False
    ship_reason = ""
    if mobile_pass == 0:
        ship_reason = "MOBILE_PASS=0 (no real UI execution succeeded)"
    elif ui_fail:
        ship_reason = f"UI FAIL count={ui_fail}"
    elif any(r.get("verdict") == "FAIL" for r in matrix):
        ship_reason = "API or UI FAIL present"
    else:
        unsigned_ok = any(
            r["id"] in {"UI.00-unsigned-entry", "UI.00-launch-unsigned", "UI.browserstack.sessions"}
            and r["verdict"] == "MOBILE_PASS"
            for r in matrix
        )
        login_ok = any(r["id"] in {"UI.01-hr-login"} and r["verdict"] == "MOBILE_PASS" for r in matrix) or not (
            os.environ.get("MAESTRO_HR_EMAIL") or os.environ.get("MOBILE_E2E_HR_EMAIL")
        )
        leave_approve_executed = any("03-hr-leave-approve" in x for x in executed)
        leave_reject_executed = any("04-hr-leave-reject" in x for x in executed)
        leave_approve_ok = (not leave_approve_executed) or any(
            r["id"] == "UI.03-hr-leave-approve" and r["verdict"] == "MOBILE_PASS" for r in matrix
        )
        leave_reject_ok = (not leave_reject_executed) or any(
            r["id"] == "UI.04-hr-leave-reject" and r["verdict"] == "MOBILE_PASS" for r in matrix
        )
        if unsigned_ok and login_ok and leave_approve_ok and leave_reject_ok:
            ship = True
            if leave_approve_executed or leave_reject_executed:
                ship_reason = "Foundation gate green (unsigned + HR auth/tabs + Leave mutations) — expand matrix before broad release"
            else:
                ship_reason = "Smoke UI MOBILE_PASS with no FAIL — canary-only; broad release still needs full matrix"
            if bs_summary.get("dashboard_url"):
                ship_reason += f" · BS {bs_summary.get('dashboard_url')}"
        else:
            missing = []
            if not unsigned_ok:
                missing.append("unsigned")
            if not login_ok:
                missing.append("hr-login")
            if not leave_approve_ok:
                missing.append("leave-approve")
            if not leave_reject_ok:
                missing.append("leave-reject")
            ship_reason = "Missing MOBILE_PASS for: " + ", ".join(missing)

    verdict = {
        "stamp": stamp,
        "suite": SUITE,
        "runtime": "browserstack" if USE_BROWSERSTACK else "local",
        "evidence": str(evid.relative_to(ROOT)),
        "host": host,
        "fixtures": fixture_meta,
        "leave_reconcile": leave_reconcile or None,
        "browserstack": {
            "build_id": bs_summary.get("build_id"),
            "dashboard_url": bs_summary.get("dashboard_url"),
            "MOBILE_PASS": bs_summary.get("MOBILE_PASS"),
        }
        if bs_summary
        else None,
        "counts": counts,
        "MOBILE_PASS": mobile_pass,
        "hr_mobile": "SHIP" if ship else "NO-SHIP",
        "employee_mobile": "SHIP" if ship else "NO-SHIP",
        "ship_reason": ship_reason,
        "rule": "API PASS ≠ MOBILE PASS",
        "selected_flows": [str(p.relative_to(ROOT)) for p in flows] if flows else bs_summary.get("execute"),
        "matrix": matrix,
    }
    write_json(evid / "VERDICT.json", verdict)

    md = [
        f"# Mobile E2E release gate — {stamp}",
        "",
        f"**Suite:** `{SUITE}`",
        f"**Evidence:** `{evid.relative_to(ROOT)}`",
        "",
        "## Rule",
        "",
        "**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.",
        "",
        "## Counts",
        "",
        "| Verdict | Count |",
        "| --- | ---: |",
    ]
    for k in sorted(counts):
        md.append(f"| {k} | {counts[k]} |")
    md.extend(
        [
            "",
            "## SHIP / NO-SHIP",
            "",
            f"| Product | Verdict |",
            f"| --- | --- |",
            f"| HR (unified `/hr`) | **{verdict['hr_mobile']}** |",
            f"| Employee | **{verdict['employee_mobile']}** |",
            "",
            f"Reason: {ship_reason}",
            "",
            "## Host blockers",
            "",
        ]
    )
    for b in host.get("blockers") or ["(none)"]:
        md.append(f"- `{b}`")
    md.extend(["", "## Matrix", ""])
    for r in matrix:
        md.append(f"- `{r['id']}` · **{r['verdict']}** — {r.get('detail','')}")
    (evid / "VERDICT.md").write_text("\n".join(md) + "\n")

    print(json.dumps({k: verdict[k] for k in ("stamp", "counts", "MOBILE_PASS", "hr_mobile", "employee_mobile", "ship_reason", "evidence")}, indent=2))
    return 0 if ship else 2


if __name__ == "__main__":
    sys.exit(main())
