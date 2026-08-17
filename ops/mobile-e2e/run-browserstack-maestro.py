#!/usr/bin/env python3
"""BrowserStack App Automate + Maestro runner for Wathefni.

Credentials (never commit):
  BROWSERSTACK_USERNAME
  BROWSERSTACK_ACCESS_KEY

Optional:
  BROWSERSTACK_APP_URL          bs://… (skip IPA upload)
  BROWSERSTACK_IPA_PATH         local .ipa path
  BROWSERSTACK_CUSTOM_APP_ID    custom_id for app upload (default wathefni-employee-canary)
  BROWSERSTACK_DEVICES          comma list, default iPhone 15-17.0
  BROWSERSTACK_PROJECT          default WathefniMobileE2E
  MOBILE_E2E_SUITE              smoke | bs-smoke | full
  MAESTRO_HR_* / MOBILE_E2E_HR_* for setEnvVariables

Rule: MOBILE_PASS only when BrowserStack reports passed sessions for executed flows.
"""

from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import base64

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets, _parse_env_file  # noqa: E402

APP = ROOT / "apps" / "wathefni-employee-mobile"
MAESTRO_DIR = APP / ".maestro"
API = "https://api-cloud.browserstack.com/app-automate"
FIXTURE_ENV = Path.home() / ".config" / "wathefni" / "e2e-fixtures.env"


def auth_header() -> str:
    user = os.environ.get("BROWSERSTACK_USERNAME", "").strip()
    key = os.environ.get("BROWSERSTACK_ACCESS_KEY", "").strip()
    if not user or not key:
        raise SystemExit("Set BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY (do not commit).")
    token = base64.b64encode(f"{user}:{key}".encode()).decode()
    return f"Basic {token}"


def api(method: str, path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 120.0) -> Any:
    hdrs = {"Authorization": auth_header(), "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = Request(f"{API}{path}", data=data, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {"error": str(err)}
        except json.JSONDecodeError:
            body = {"error": raw or str(err)}
        raise RuntimeError(f"BrowserStack {method} {path} → {err.code}: {body}") from err
    except URLError as err:
        raise RuntimeError(f"BrowserStack network error: {err}") from err


def multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"----WathefniBS{int(time.time())}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, path in files.items():
        filename = path.name
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload_app(ipa: Path, custom_id: str) -> str:
    body, ctype = multipart({"custom_id": custom_id}, {"file": ipa})
    result = api("POST", "/maestro/v2/app", data=body, headers={"Content-Type": ctype}, timeout=600.0)
    url = result.get("app_url")
    if not url:
        raise RuntimeError(f"App upload missing app_url: {result}")
    return url


def zip_flows(suite_dir: Path, out_zip: Path, include: list[str] | None = None) -> Path:
    """Zip flows under a single parent folder (BrowserStack requirement)."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    parent = "wathefni-maestro"
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        cfg = MAESTRO_DIR / "config.yaml"
        if cfg.exists():
            zf.write(cfg, f"{parent}/config.yaml")
        for path in sorted(suite_dir.rglob("*.yaml")):
            rel = path.relative_to(suite_dir).as_posix()
            # Always ship shared helpers (_*.yaml) when filtering execute list
            helper = path.name.startswith("_")
            if include is not None and not helper and path.name not in include and rel not in include:
                continue
            # Keep suite subfolder so execute paths stay stable
            zf.write(path, f"{parent}/{suite_dir.name}/{rel}")
    return out_zip


def upload_test_suite(zip_path: Path, custom_id: str) -> str:
    body, ctype = multipart({"custom_id": custom_id}, {"file": zip_path})
    result = api("POST", "/maestro/v2/test-suite", data=body, headers={"Content-Type": ctype}, timeout=300.0)
    url = result.get("test_suite_url") or result.get("test_url")
    if not url:
        raise RuntimeError(f"Test-suite upload missing url: {result}")
    return url


def env_for_maestro() -> dict[str, str]:
    mapping = {
        "MOBILE_E2E_HR_COMPANY": "MAESTRO_HR_COMPANY",
        "MOBILE_E2E_COMPANY_CODE": "MAESTRO_HR_COMPANY",
        "MOBILE_E2E_HR_EMAIL": "MAESTRO_HR_EMAIL",
        "MOBILE_E2E_HR_PASSWORD": "MAESTRO_HR_PASSWORD",
        "MOBILE_E2E_EMPLOYEE_PHONE": "MAESTRO_EMPLOYEE_PHONE",
        "MOBILE_E2E_EMPLOYEE_CODE": "MAESTRO_EMPLOYEE_CODE",
        "MOBILE_E2E_EMPLOYEE_PIN": "MAESTRO_EMPLOYEE_PIN",
        "MOBILE_E2E_HR_PIN": "MAESTRO_HR_PIN",
        "MOBILE_E2E_LEAVE_ID": "MAESTRO_LEAVE_ID",
        "MOBILE_E2E_LEAVE_APPROVE_ID": "MAESTRO_LEAVE_ID",
        "MOBILE_E2E_LEAVE_REJECT_ID": "MAESTRO_LEAVE_REJECT_ID",
        "MOBILE_E2E_PIN": "MAESTRO_PIN",
    }
    out: dict[str, str] = {}
    for src, dst in mapping.items():
        if os.environ.get(src) and not os.environ.get(dst):
            out[dst] = os.environ[src]
    for key in (
        "MAESTRO_HR_COMPANY",
        "MAESTRO_HR_EMAIL",
        "MAESTRO_HR_PASSWORD",
        "MAESTRO_EMPLOYEE_PHONE",
        "MAESTRO_EMPLOYEE_CODE",
        "MAESTRO_LEAVE_ID",
        "MAESTRO_LEAVE_REJECT_ID",
        "MAESTRO_PIN",
        "MAESTRO_EMPLOYEE_PIN",
        "MAESTRO_HR_PIN",
        "MAESTRO_HR_EMAIL_LOCAL",
        "MAESTRO_HR_EMAIL_DOMAIN",
    ):
        if os.environ.get(key):
            out[key] = os.environ[key]
    out.setdefault("MAESTRO_HR_COMPANY", "WATHEFNI")
    out.setdefault("MAESTRO_PIN", "246810")
    out.setdefault("MAESTRO_EMPLOYEE_PIN", out["MAESTRO_PIN"])
    out.setdefault("MAESTRO_HR_PIN", "864209")
    if out["MAESTRO_HR_PIN"] == out["MAESTRO_EMPLOYEE_PIN"]:
        out["MAESTRO_HR_PIN"] = "975310"
    # Split email for reliable iOS Maestro input (avoids domain corruption)
    email = out.get("MAESTRO_HR_EMAIL") or ""
    if email and "@" in email:
        local, _, domain = email.partition("@")
        out.setdefault("MAESTRO_HR_EMAIL_LOCAL", local)
        out.setdefault("MAESTRO_HR_EMAIL_DOMAIN", domain)
    return out


def start_ios_build(*, app_url: str, suite_url: str, execute: list[str], devices: list[str], project: str) -> str:
    payload: dict[str, Any] = {
        "app": app_url,
        "testSuite": suite_url,
        "devices": devices,
        "project": project,
        "deviceLogs": True,
        "networkLogs": True,
        "debugscreenshots": True,
        "video": True,
        "execute": execute,
        "customBuildName": f"wathefni-{int(time.time())}",
    }
    env = env_for_maestro()
    if env:
        payload["setEnvVariables"] = env
    raw = json.dumps(payload).encode()
    result = api(
        "POST",
        "/maestro/v2/ios/build",
        data=raw,
        headers={"Content-Type": "application/json"},
        timeout=120.0,
    )
    build_id = result.get("build_id")
    if not build_id:
        raise RuntimeError(f"Build start failed: {result}")
    return build_id


def poll_build(build_id: str, *, timeout_s: int = 2400) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    terminal = {"passed", "failed", "error", "timeout", "skipped"}
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = api("GET", f"/maestro/v2/builds/{build_id}", timeout=60.0)
        status = (last.get("status") or "").lower()
        if status in terminal or status in {"done", "completed"}:
            return last
        # Some payloads nest status under devices; keep polling while running/queued
        if status in {"running", "queued", "started", "pending", ""}:
            time.sleep(20)
            continue
        # Unknown but maybe finished with device sessions
        devices = last.get("devices") or []
        if devices and all(
            ((s.get("status") or "").lower() in terminal | {"passed", "failed"})
            for d in devices
            for s in (d.get("sessions") or [{"status": "running"}])
        ):
            return last
        time.sleep(20)
    last["poll_timeout"] = True
    return last


def summarize(build: dict[str, Any]) -> dict[str, Any]:
    status = (build.get("status") or "unknown").lower()
    sessions = []
    passed = failed = error = 0
    per_flow: list[dict[str, Any]] = []
    for device in build.get("devices") or []:
        for session in device.get("sessions") or []:
            st = (session.get("status") or "").lower()
            sessions.append(
                {
                    "device": device.get("device"),
                    "os_version": device.get("os_version"),
                    "session_id": session.get("id"),
                    "status": st,
                    "duration": session.get("duration"),
                    "testcases": session.get("testcases"),
                }
            )
            if st == "passed":
                passed += 1
            elif st == "failed":
                failed += 1
            elif st in {"error", "timeout"}:
                error += 1
            # Per-flow honesty: session can fail while some flows MOBILE_PASS
            tc = session.get("testcases") or {}
            for group in tc.get("data") or []:
                for case in group.get("testcases") or []:
                    name = str(case.get("name") or group.get("class") or "")
                    cst = (case.get("status") or "").lower()
                    per_flow.append(
                        {
                            "flow": name,
                            "status": cst,
                            "duration": case.get("duration"),
                            "id": case.get("id"),
                            "device": device.get("device"),
                            "os_version": device.get("os_version"),
                            "session_id": session.get("id"),
                            "video": case.get("video"),
                        }
                    )
    dashboard = f"https://app-automate.browserstack.com/dashboard/v2/builds/{build.get('id')}"
    # Never persist credentials / tokens into evidence
    caps = dict(build.get("input_capabilities") or {})
    env = dict(caps.get("setEnvVariables") or {})
    for key in list(env):
        upper = key.upper()
        if any(s in upper for s in ("PASSWORD", "TOKEN", "SECRET", "ACCESS_KEY", "API_KEY")):
            env[key] = "***REDACTED***"
    if env:
        caps["setEnvVariables"] = env
    flow_pass = sum(1 for f in per_flow if f["status"] == "passed")
    return {
        "build_id": build.get("id"),
        "status": status,
        "passed_sessions": passed,
        "failed_sessions": failed,
        "error_sessions": error,
        "passed_flows": flow_pass,
        "failed_flows": sum(1 for f in per_flow if f["status"] == "failed"),
        "flows": per_flow,
        "sessions": sessions,
        "dashboard_url": dashboard,
        "app_details": build.get("app_details"),
        "input_capabilities": caps,
        "poll_timeout": bool(build.get("poll_timeout")),
        "raw_status": build.get("status"),
    }


def selected_bs_flows() -> tuple[Path, list[str]]:
    """Return suite directory and execute paths relative to zip root."""
    suite = os.environ.get("MOBILE_E2E_SUITE", "bs-smoke").strip()
    directory = MAESTRO_DIR / "bs-smoke"
    if suite in {"smoke", "bs-smoke"}:
        names = ["00-launch-unsigned.yaml"]
        if os.environ.get("MAESTRO_HR_EMAIL") or os.environ.get("MOBILE_E2E_HR_EMAIL"):
            names.extend(["01-hr-login.yaml", "02-hr-tabs.yaml"])
            if os.environ.get("MOBILE_E2E_LEAVE_ID") or os.environ.get("MAESTRO_LEAVE_ID") or os.environ.get(
                "MOBILE_E2E_LEAVE_APPROVE_ID"
            ):
                names.append("03-hr-leave-approve.yaml")
            if os.environ.get("MOBILE_E2E_LEAVE_REJECT_ID") or os.environ.get("MAESTRO_LEAVE_REJECT_ID"):
                names.append("04-hr-leave-reject.yaml")
        execute = [f"bs-smoke/{n}" for n in names]
        return directory, execute
    directory = MAESTRO_DIR / "flows"
    execute = [f"flows/{p.name}" for p in sorted(directory.glob("*.yaml")) if not p.name.startswith("_")]
    flow_filter = os.environ.get("MOBILE_E2E_FLOW_FILTER", "").strip()
    if flow_filter:
        execute = [path for path in execute if flow_filter in Path(path).name]
    return directory, execute


def main() -> int:
    load_secrets()
    if FIXTURE_ENV.exists():
        for key, value in _parse_env_file(FIXTURE_ENV).items():
            os.environ.setdefault(key, value)
        # Re-apply Maestro mirrors after fixture load
        load_secrets()

    evid = Path(os.environ.get("MOBILE_E2E_EVID") or (ROOT / "ops" / "evidence" / f"mobile-e2e-bs-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"))
    evid.mkdir(parents=True, exist_ok=True)
    bs_dir = evid / "browserstack"
    bs_dir.mkdir(exist_ok=True)

    devices = [d.strip() for d in os.environ.get("BROWSERSTACK_DEVICES", "iPhone 15-17.0").split(",") if d.strip()]
    project = os.environ.get("BROWSERSTACK_PROJECT", "WathefniMobileE2E")
    custom_app = os.environ.get("BROWSERSTACK_CUSTOM_APP_ID", "wathefni-employee-canary-0.3.0-23")

    app_url = os.environ.get("BROWSERSTACK_APP_URL", "").strip()
    if not app_url:
        ipa = Path(os.environ.get("BROWSERSTACK_IPA_PATH", "/tmp/wathefni-rc/wathefni-employee-0.3.0-23.ipa"))
        if not ipa.exists():
            raise SystemExit(f"IPA missing: {ipa}. Set BROWSERSTACK_APP_URL or BROWSERSTACK_IPA_PATH.")
        print(json.dumps({"phase": "upload_app", "ipa": str(ipa)}))
        app_url = upload_app(ipa, custom_app)
        (bs_dir / "app_upload.json").write_text(json.dumps({"app_url": app_url, "custom_id": custom_app}, indent=2) + "\n")
    else:
        (bs_dir / "app_upload.json").write_text(json.dumps({"app_url": app_url, "reused": True}, indent=2) + "\n")

    suite_dir, execute = selected_bs_flows()
    if not suite_dir.exists():
        raise SystemExit(f"Missing suite dir {suite_dir}")
    include = [Path(p).name for p in execute]
    zip_path = bs_dir / "maestro-suite.zip"
    zip_flows(suite_dir, zip_path, include=include)
    print(json.dumps({"phase": "upload_suite", "zip": str(zip_path), "execute": execute}))
    suite_url = upload_test_suite(zip_path, custom_id=f"wathefni-{suite_dir.name}-{int(time.time())}")
    (bs_dir / "suite_upload.json").write_text(json.dumps({"test_suite_url": suite_url, "execute": execute}, indent=2) + "\n")

    print(json.dumps({"phase": "start_build", "app": app_url, "suite": suite_url, "devices": devices}))
    build_id = start_ios_build(app_url=app_url, suite_url=suite_url, execute=execute, devices=devices, project=project)
    (bs_dir / "build_started.json").write_text(json.dumps({"build_id": build_id}, indent=2) + "\n")

    print(json.dumps({"phase": "poll", "build_id": build_id}))
    build = poll_build(build_id)
    # Enrich sessions with per-testcase detail (build poll often omits testcases.data)
    for device in build.get("devices") or []:
        for session in device.get("sessions") or []:
            sid = session.get("id")
            if not sid:
                continue
            try:
                detail = api("GET", f"/maestro/v2/builds/{build_id}/sessions/{sid}", timeout=60.0)
                if isinstance(detail, dict) and detail.get("testcases"):
                    session["testcases"] = detail["testcases"]
            except Exception as exc:
                session["detail_error"] = str(exc)[:200]
    # Redact secrets before writing raw build evidence
    raw_for_disk = json.loads(json.dumps(build))
    caps = raw_for_disk.get("input_capabilities") or {}
    env = caps.get("setEnvVariables") if isinstance(caps, dict) else None
    if isinstance(env, dict):
        for key in list(env):
            upper = key.upper()
            if any(s in upper for s in ("PASSWORD", "TOKEN", "SECRET", "ACCESS_KEY", "API_KEY")):
                env[key] = "***REDACTED***"
    (bs_dir / "build_final.json").write_text(json.dumps(raw_for_disk, indent=2) + "\n")
    summary = summarize(build)
    summary["execute"] = execute
    summary["app_url"] = app_url
    summary["test_suite_url"] = suite_url
    summary["evidence"] = str(evid.relative_to(ROOT)) if evid.is_relative_to(ROOT) else str(evid)
    # MOBILE_PASS = count of real-device flows that passed (not API)
    summary["MOBILE_PASS"] = int(summary.get("passed_flows") or 0) or int(summary.get("passed_sessions") or 0)
    summary["ui_runtime"] = "browserstack_real_device"
    if summary["poll_timeout"]:
        ship = "NO-SHIP"
        reason = "BrowserStack poll timeout — incomplete real-device evidence"
    elif summary["failed_flows"] == 0 and summary["error_sessions"] == 0 and summary["MOBILE_PASS"] > 0:
        ship = "SHIP"
        reason = "All executed BrowserStack flows passed (smoke scope only — expand matrix before broad release)"
    elif summary["passed_sessions"] > 0 and summary["failed_sessions"] == 0 and summary["error_sessions"] == 0:
        ship = "SHIP"
        reason = "All BrowserStack sessions passed (smoke scope only — expand matrix before broad release)"
    else:
        ship = "NO-SHIP"
        reason = (
            f"flows_pass={summary.get('passed_flows')} flows_fail={summary.get('failed_flows')} "
            f"sessions_pass={summary['passed_sessions']} sessions_fail={summary['failed_sessions']} "
            f"status={summary['status']}"
        )
    summary["hr_mobile"] = ship
    summary["employee_mobile"] = ship
    summary["ship_reason"] = reason
    summary["rule"] = "API PASS ≠ MOBILE PASS — BrowserStack real-device execution required"
    (bs_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    # Avoid dumping secrets if any slipped into print
    printable = dict(summary)
    caps = printable.get("input_capabilities") or {}
    if isinstance(caps, dict) and isinstance(caps.get("setEnvVariables"), dict):
        for key in list(caps["setEnvVariables"]):
            if "PASSWORD" in key.upper():
                caps["setEnvVariables"][key] = "***REDACTED***"
    print(json.dumps(printable, indent=2))
    return 0 if ship == "SHIP" and summary["MOBILE_PASS"] > 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise
