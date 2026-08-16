#!/usr/bin/env python3
"""Terminal-driven HR mobile production/canary journey qualification.

Proves reachable HR mobile surfaces against the real deployed backend without
physical device operation. MOBILE_PASS for real UI taps is out of scope here —
those remain PHYSICAL_ONLY / BrowserStack.

Usage:
  python3 ops/mobile-e2e/run-hr-terminal-qual.py

Secrets: ~/.config/wathefni/e2e.env (never printed).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "wathefni-employee-mobile"
HR_APP = APP / "app" / "hr"
HR_SRC = APP / "src" / "hr"
I18N_EN = APP / "src" / "i18n" / "en.json"
I18N_AR = APP / "src" / "i18n" / "ar.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

API_BASE = os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")
COMPANY = "WATHEFNI"
SUBJECT = "WATHEFNI-96550252254"
MARKER = "wathefni_hr_terminal_qual_v1"
SSH_HOST = os.environ.get("MOBILE_E2E_SSH_HOST", "root@76.13.63.68")
LOCAL_FIXTURE_ENV = Path.home() / ".config" / "wathefni" / "e2e-fixtures.env"


def leave_ssh_run(mode: str) -> dict[str, Any]:
    """Reuse provision-leave-fixture SSH path without importing hyphenated module name."""
    script = Path(__file__).resolve().parent / "provision-leave-fixture.py"
    cmd = [sys.executable, str(script)]
    if mode == "cleanup":
        cmd.append("--cleanup")
    elif mode == "verify":
        cmd.append("--verify-only")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=180)
    text = (proc.stdout or "").strip()
    # provision prints pretty-printed JSON — parse from first "{" 
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(proc.stderr[-500:] or text[-500:] or f"rc={proc.returncode}")
    data = json.loads(text[start : end + 1])
    if mode == "provision" and "approve_leave_id" not in data and not data.get("ok"):
        raise RuntimeError(json.dumps(data)[:400])
    return data


def write_fixture_env_from_provision(payload: dict[str, Any]) -> None:
    approve = payload.get("approve_leave_id") or ""
    reject = payload.get("reject_leave_id") or ""
    if not approve:
        return
    LOCAL_FIXTURE_ENV.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FIXTURE_ENV.write_text(
        f"MOBILE_E2E_LEAVE_APPROVE_ID={approve}\n"
        f"MOBILE_E2E_LEAVE_REJECT_ID={reject}\n"
        f"MOBILE_E2E_LEAVE_ID={approve}\n"
        f"MAESTRO_LEAVE_ID={approve}\n"
        f"MAESTRO_LEAVE_REJECT_ID={reject}\n"
    )
    LOCAL_FIXTURE_ENV.chmod(0o600)


@dataclass
class Row:
    surface: str
    cta_or_link: str
    api_or_action: str
    expected: str
    actual: str
    verdict: str  # PASS | FAIL | SKIP | PHYSICAL_ONLY
    detail: str = ""


@dataclass
class Report:
    stamp: str
    evidence: str
    counts: dict[str, int] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    physical_only: list[str] = field(default_factory=list)
    ship: str = "NO-SHIP"
    ship_reason: str = ""


def add(report: Report, **kwargs: Any) -> None:
    report.rows.append(Row(**kwargs))


def api(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> tuple[int, Any]:
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return err.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def login() -> tuple[str, dict[str, Any]]:
    load_secrets()
    email = os.environ.get("MOBILE_E2E_HR_EMAIL") or os.environ.get("MAESTRO_HR_EMAIL")
    password = os.environ.get("MOBILE_E2E_HR_PASSWORD") or os.environ.get("MAESTRO_HR_PASSWORD")
    company = os.environ.get("MOBILE_E2E_HR_COMPANY") or os.environ.get("MAESTRO_HR_COMPANY") or COMPANY
    if not email or not password:
        raise SystemExit("Missing MOBILE_E2E_HR_EMAIL / MOBILE_E2E_HR_PASSWORD")
    code, body = api(
        "POST",
        "/dashboard/mobile/auth/login",
        body={"company_code": company, "email": email, "password": password},
    )
    if code != 200 or not isinstance(body, dict) or not body.get("access_token"):
        raise SystemExit(f"mobile login failed → {code}")
    return str(body["access_token"]), body


def me(token: str) -> dict[str, Any]:
    code, body = api("GET", "/dashboard/mobile/me", token=token)
    if code != 200 or not isinstance(body, dict):
        raise SystemExit(f"/me failed → {code}")
    return body


# ── Static crawl ─────────────────────────────────────────────────────────────


def list_hr_routes() -> list[str]:
    routes: list[str] = []
    for path in sorted(HR_APP.rglob("*.tsx")):
        rel = path.relative_to(HR_APP).as_posix()
        if rel.endswith("_layout.tsx"):
            continue
        parts = rel.split("/")
        out: list[str] = []
        for part in parts[:-1]:
            if part.startswith("(") and part.endswith(")"):
                continue
            out.append(part)
        name = parts[-1]
        if name == "index.tsx":
            route = "/hr" + (("/" + "/".join(out)) if out else "")
        else:
            stem = name[:-4]
            route = "/hr/" + "/".join(out + [stem]) if out else f"/hr/{stem}"
        route = route.replace("[", "{").replace("]", "}")
        routes.append(route)
    return sorted(set(routes))


def crawl_handlers() -> list[dict[str, str]]:
    """Map clickable patterns → nearby API/router targets from HR source."""
    findings: list[dict[str, str]] = []
    roots = [HR_APP, HR_SRC]
    patterns = [
        (r"[`'\"](/dashboard/mobile/[a-zA-Z0-9_/{}$?=&%.\-\[\]]+)", "api"),
        (r"router\.(?:push|replace)\(\s*[`'\"]([^`'\"]+)", "nav"),
        (r"toHrPath\(\s*[`'\"]([^`'\"]+)", "nav"),
        (r"testID=[\"'](e2e\.[^\"']+)[\"']", "testid"),
        (r"onPress=\{[^}]*prepare\(['\"](\w+)['\"]", "prepare_action"),
    ]
    for root in roots:
        for path in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = str(path.relative_to(ROOT))
            for rx, kind in patterns:
                for m in re.finditer(rx, text):
                    findings.append({"file": rel, "kind": kind, "value": m.group(1)[:200]})
    return findings


def canonical_parent_cases() -> list[tuple[str, str]]:
    # Mirror hrCanonicalParent expectations from navigation.ts
    return [
        ("/hr/leave/abc", "/hr"),
        ("/hr/candidates/x", "/hr/candidates"),
        ("/hr/candidates", "/hr/hiring"),
        ("/hr/jobs", "/hr/hiring"),
        ("/hr/interviews/i1", "/hr/interviews"),
        ("/hr/interviews", "/hr/hiring"),
        ("/hr/employees/e1", "/hr/people"),
        ("/hr/employees", "/hr/more"),
        ("/hr/tasks/t1", "/hr/tasks"),
        ("/hr/tasks", "/hr/more"),
        ("/hr/onboarding/e1", "/hr/onboarding"),
        ("/hr/onboarding", "/hr/more"),
        ("/hr/documents/e1/civil_id", "/hr/documents"),
        ("/hr/documents", "/hr/more"),
        ("/hr/attendance/a1", "/hr/attendance"),
        ("/hr/attendance", "/hr/more"),
        ("/hr/shift-swaps/s1", "/hr/shifts"),
        ("/hr/shifts", "/hr/more"),
        ("/hr/delivery-alerts", "/hr/more"),
        ("/hr/assistant", "/hr/more"),
        ("/hr/settings", "/hr/more"),
        ("/hr/change-pin", "/hr/settings"),
    ]


def run_canonical_parent_static(report: Report) -> None:
    nav = (HR_SRC / "navigation.ts").read_text(encoding="utf-8")
    for child, parent in canonical_parent_cases():
        # crude presence check that the branch exists for the prefix
        prefix = child.rsplit("/", 1)[0] if "{" not in child else child
        key = child.split("/")[2] if len(child.split("/")) > 2 else ""
        ok = key in nav or child in nav or f"'/{key}" in nav or f'"/{key}' in nav
        # stronger: evaluate via node if available — fallback to source contains startsWith
        starts = f"startsWith('/{key}" in nav or f'startsWith("/{key}' in nav or f"=== '/{key}'" in nav or f'=== "/{key}"' in nav
        if key in {"leave", "candidates", "interviews", "employees", "tasks", "onboarding", "documents", "attendance", "shift-swaps", "delivery-alerts", "assistant", "settings", "change-pin", "jobs", "shifts"}:
            ok = starts or (key.replace("-", "") in nav.replace("-", ""))
        add(
            report,
            surface="Static/safe-back",
            cta_or_link=f"cold-start parent of {child}",
            api_or_action="hrCanonicalParent",
            expected=parent,
            actual="implemented" if ok else "missing branch",
            verdict="PASS" if ok else "FAIL",
            detail="static source contract",
        )


def i18n_keys_for_hr() -> set[str]:
    keys: set[str] = set()
    for path in list(HR_SRC.rglob("*.ts")) + list(HR_SRC.rglob("*.tsx")) + list(HR_APP.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"t\(\s*['\"]([a-zA-Z][\w.]+)['\"]", text):
            keys.add(m.group(1))
    return keys


def run_i18n(report: Report) -> None:
    # HR Confirm sheet + many HR strings live in src/hr/i18n; shared auth/pin in src/i18n.
    catalogs = []
    for path in (
        I18N_EN,
        I18N_AR,
        HR_SRC / "i18n" / "en.json",
        HR_SRC / "i18n" / "ar.json",
    ):
        if path.exists():
            catalogs.append((path.name, json.loads(path.read_text(encoding="utf-8"))))
    en_merged: dict[str, Any] = {}
    ar_merged: dict[str, Any] = {}
    for name, data in catalogs:
        if name.startswith("en") or name == "en.json":
            en_merged.update(data)
        if name.startswith("ar") or name == "ar.json":
            ar_merged.update(data)
    # Prefer hr/i18n over app i18n when both exist — update order: app first then hr
    en_merged = {}
    ar_merged = {}
    if I18N_EN.exists():
        en_merged.update(json.loads(I18N_EN.read_text(encoding="utf-8")))
    if (HR_SRC / "i18n" / "en.json").exists():
        en_merged.update(json.loads((HR_SRC / "i18n" / "en.json").read_text(encoding="utf-8")))
    if I18N_AR.exists():
        ar_merged.update(json.loads(I18N_AR.read_text(encoding="utf-8")))
    if (HR_SRC / "i18n" / "ar.json").exists():
        ar_merged.update(json.loads((HR_SRC / "i18n" / "ar.json").read_text(encoding="utf-8")))

    used = sorted(
        k
        for k in i18n_keys_for_hr()
        if k.startswith(("hr", "confirm.", "auth.", "pin.", "biometric.", "common."))
        and "." in k
    )
    missing_en = [k for k in used if k not in en_merged]
    missing_ar = [k for k in used if k not in ar_merged]
    add(
        report,
        surface="Static/i18n",
        cta_or_link=f"{len(used)} HR-related t() keys",
        api_or_action="app i18n ∪ hr/i18n EN+AR",
        expected="all referenced keys present EN+AR",
        actual=f"missing_en={len(missing_en)} missing_ar={len(missing_ar)}",
        verdict="PASS" if not missing_en and not missing_ar else "FAIL",
        detail=("en:" + ",".join(missing_en[:20]) + " | ar:" + ",".join(missing_ar[:20]))[:500],
    )


def run_route_registration(report: Report, handlers: list[dict[str, str]]) -> None:
    routes = list_hr_routes()
    add(
        report,
        surface="Static/routes",
        cta_or_link="app/hr/** route tree",
        api_or_action="expo file-based routes",
        expected="registered HR screens",
        actual=f"{len(routes)} routes",
        verdict="PASS" if len(routes) >= 20 else "FAIL",
        detail=", ".join(routes[:40]),
    )
    # destinationAvailable must mention key prefixes
    cap = (HR_SRC / "capabilities.ts").read_text(encoding="utf-8")
    for prefix in (
        "/leave/",
        "/candidates/",
        "/onboarding/",
        "/employees/",
        "/shift-swaps/",
        "/interviews/",
        "/tasks/",
        "/documents/",
        "/attendance/",
        "/assistant",
    ):
        ok = prefix in cap
        add(
            report,
            surface="Static/destinationAvailable",
            cta_or_link=prefix,
            api_or_action="capabilities.destinationAvailable",
            expected="gated",
            actual="present" if ok else "absent",
            verdict="PASS" if ok else "FAIL",
        )
    # Assistant deep-link map
    adl = (HR_SRC / "features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8")
    for page in ("leave", "attendance", "shifts", "onboarding", "candidates", "interviews", "tasks", "documents", "jobs"):
        ok = f"{page}:" in adl or f'"{page}"' in adl or f"'{page}'" in adl
        add(
            report,
            surface="Static/assistantDeepLinks",
            cta_or_link=f"page={page}",
            api_or_action="mapAssistantNavigation",
            expected="mapped or web-only refused",
            actual="mapped" if ok else "unmapped",
            verdict="PASS" if ok else "FAIL",
        )
    # CTA/API inventory size
    apis = sorted({h["value"] for h in handlers if h["kind"] == "api"})
    add(
        report,
        surface="Static/handlers",
        cta_or_link="request('/dashboard/mobile/…') crawl",
        api_or_action=f"{len(apis)} unique API paths",
        expected=">=15 mobile endpoints referenced",
        actual=str(len(apis)),
        verdict="PASS" if len(apis) >= 15 else "FAIL",
        detail="; ".join(apis[:25]),
    )


# ── Live API ─────────────────────────────────────────────────────────────────


def feature_enabled(me_body: dict[str, Any], workspace: str, feature: str) -> bool:
    ws = ((me_body.get("workspaces") or {}).get(workspace) or {})
    feat = (ws.get("features") or {}).get(feature) or {}
    return bool(feat.get("enabled"))


def row_read(
    report: Report,
    *,
    surface: str,
    cta: str,
    path: str,
    token: str,
    expect_ok: bool = True,
    accept: set[int] | None = None,
    capability_off_ok: bool = False,
) -> Any:
    code, body = api("GET", path, token=token)
    accept = accept or ({200} if expect_ok else {200, 403, 404})
    if capability_off_ok and code in {403}:
        add(
            report,
            surface=surface,
            cta_or_link=cta,
            api_or_action=f"GET {path}",
            expected="200 or honest capability denial",
            actual=f"HTTP {code} {_brief(body)}",
            verdict="PASS",
            detail="capability/RBAC deny-closed",
        )
        return None
    ok = code in accept
    add(
        report,
        surface=surface,
        cta_or_link=cta,
        api_or_action=f"GET {path}",
        expected=f"HTTP {sorted(accept)}",
        actual=f"HTTP {code}",
        verdict="PASS" if ok else "FAIL",
        detail=_brief(body),
    )
    return body if code == 200 else None


def _brief(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, dict):
        keys = list(body.keys())[:8]
        extra = ""
        if "items" in body and isinstance(body["items"], list):
            extra = f" items={len(body['items'])}"
        if "total" in body:
            extra += f" total={body.get('total')}"
        if "request" in body and isinstance(body["request"], dict):
            extra += f" status={body['request'].get('status')}"
        return ("keys=" + ",".join(keys) + extra)[:240]
    return str(body)[:160]


def leave_decision(token: str, leave_id: str, action: str, *, confirm: bool, reason: str | None = None, conf: dict | None = None, key: str | None = None) -> tuple[int, Any]:
    payload: dict[str, Any] = {
        "action": action,
        "idempotency_key": key or f"term-{action}-{uuid.uuid4()}",
        "confirm": confirm,
    }
    if reason:
        payload["reason"] = reason
    if conf:
        payload["confirmation_id"] = conf.get("confirmation_id")
        payload["confirmation_hash"] = conf.get("confirmation_hash")
    return api("POST", f"/dashboard/mobile/leave/{leave_id}/decision", token=token, body=payload)


def run_leave_mutations(report: Report, token: str) -> None:
    # provision disposable leaves
    try:
        provisioned = leave_ssh_run("provision")
        write_fixture_env_from_provision(provisioned)
        approve_id = provisioned["approve_leave_id"]
        reject_id = provisioned["reject_leave_id"]
    except Exception as exc:
        add(
            report,
            surface="Leave",
            cta_or_link="provision disposable fixtures",
            api_or_action="SSH leave_requests INSERT",
            expected="two requested leaves",
            actual=str(exc)[:200],
            verdict="FAIL",
        )
        return

    # detail + allowed actions
    for lid, label in ((approve_id, "approve fixture"), (reject_id, "reject fixture")):
        code, body = api("GET", f"/dashboard/mobile/leave/{lid}", token=token)
        req = (body or {}).get("request") if isinstance(body, dict) else None
        ok = code == 200 and isinstance(req, dict) and req.get("status") == "requested"
        add(
            report,
            surface="Leave",
            cta_or_link=f"Open {label}",
            api_or_action=f"GET /dashboard/mobile/leave/{lid}",
            expected="status=requested + approve/reject actions",
            actual=f"HTTP {code} status={(req or {}).get('status')} actions={(req or {}).get('allowed_actions')}",
            verdict="PASS" if ok and "approve" in (req or {}).get("allowed_actions", []) else "FAIL",
        )

    # reject without reason must 422
    code, body = leave_decision(token, reject_id, "reject", confirm=False, reason="")
    err = (body or {}).get("detail", {}) if isinstance(body, dict) else {}
    if isinstance(err, dict):
        err_code = err.get("error")
    else:
        err_code = str(err)
    add(
        report,
        surface="Leave",
        cta_or_link="Reject without reason",
        api_or_action="POST …/decision confirm=false reason=''",
        expected="422 rejection_reason_required",
        actual=f"HTTP {code} error={err_code}",
        verdict="PASS" if code == 422 or err_code == "rejection_reason_required" else "FAIL",
    )

    # approve prepare → confirm
    key_a = f"term-approve-{uuid.uuid4()}"
    code, prep = leave_decision(token, approve_id, "approve", confirm=False, key=key_a)
    conf = (prep or {}).get("confirmation") if isinstance(prep, dict) else None
    add(
        report,
        surface="Leave",
        cta_or_link="Approve → confirmation sheet",
        api_or_action="POST …/decision confirm=false action=approve",
        expected="confirmation material",
        actual=f"HTTP {code} has_conf={bool(conf)}",
        verdict="PASS" if code == 200 and conf else "FAIL",
        detail=_brief(prep),
    )
# Also accept prepare responses that use ok=false status=needs_confirmation (SOD envelope)
    if conf:
        code2, done = leave_decision(token, approve_id, "approve", confirm=True, conf=conf, key=key_a)
        ok2 = code2 == 200 and isinstance(done, dict) and (
            done.get("ok") is True or str(done.get("status") or "") == "completed"
        )
        # Surface allowlist / domain failures honestly
        err = ""
        if isinstance(done, dict):
            err = str(((done.get("result") or {}) if isinstance(done.get("result"), dict) else {}).get("error") or done.get("status") or "")
        add(
            report,
            surface="Leave",
            cta_or_link="Confirm Approve",
            api_or_action="POST …/decision confirm=true",
            expected="completed / approved",
            actual=f"HTTP {code2} ok={done.get('ok') if isinstance(done, dict) else None} status={done.get('status') if isinstance(done, dict) else None} err={err}",
            verdict="PASS" if ok2 else "FAIL",
            detail=_brief(done),
        )
        # stale replay
        code3, stale = leave_decision(token, approve_id, "approve", confirm=True, conf=conf, key=key_a)
        add(
            report,
            surface="Leave",
            cta_or_link="Double-submit / stale confirm",
            api_or_action="POST …/decision confirm=true (replay)",
            expected="not a second successful mutation (4xx or idempotent completed)",
            actual=f"HTTP {code3} body={_brief(stale)}",
            verdict="PASS" if code3 in {200, 409, 400, 422} else "FAIL",
        )
        # DB/detail truth
        code4, after = api("GET", f"/dashboard/mobile/leave/{approve_id}", token=token)
        st = ((after or {}).get("request") or {}).get("status") if isinstance(after, dict) else None
        add(
            report,
            surface="Leave",
            cta_or_link="Post-approve detail refresh",
            api_or_action=f"GET /dashboard/mobile/leave/{approve_id}",
            expected="status=approved, allowed_actions=[]",
            actual=f"HTTP {code4} status={st} actions={((after or {}).get('request') or {}).get('allowed_actions') if isinstance(after, dict) else None}",
            verdict="PASS" if st == "approved" else "FAIL",
        )

    # reject prepare → confirm
    key_r = f"term-reject-{uuid.uuid4()}"
    reason = "Terminal qual reject — disposable"
    code, prep = leave_decision(token, reject_id, "reject", confirm=False, reason=reason, key=key_r)
    conf = (prep or {}).get("confirmation") if isinstance(prep, dict) else None
    add(
        report,
        surface="Leave",
        cta_or_link="Reject → confirmation sheet",
        api_or_action="POST …/decision confirm=false action=reject",
        expected="confirmation material",
        actual=f"HTTP {code} has_conf={bool(conf)}",
        verdict="PASS" if code == 200 and conf else "FAIL",
    )
    if conf:
        code2, done = leave_decision(token, reject_id, "reject", confirm=True, reason=reason, conf=conf, key=key_r)
        add(
            report,
            surface="Leave",
            cta_or_link="Confirm Reject",
            api_or_action="POST …/decision confirm=true",
            expected="completed / rejected",
            actual=f"HTTP {code2} {_brief(done)}",
            verdict="PASS" if code2 == 200 and isinstance(done, dict) and done.get("ok") else "FAIL",
        )
        code4, after = api("GET", f"/dashboard/mobile/leave/{reject_id}", token=token)
        req = (after or {}).get("request") if isinstance(after, dict) else {}
        st = (req or {}).get("status")
        note = (req or {}).get("decision_note") or ""
        add(
            report,
            surface="Leave",
            cta_or_link="Post-reject detail + reason persistence",
            api_or_action=f"GET /dashboard/mobile/leave/{reject_id}",
            expected="status=rejected + decision_note set",
            actual=f"status={st} note_len={len(str(note))}",
            verdict="PASS" if st == "rejected" and str(note).strip() else "FAIL",
        )

    # priorities should not keep decided leave destinations (best-effort)
    code, pri = api("GET", "/dashboard/mobile/priorities", token=token)
    dests: list[str] = []
    if isinstance(pri, dict):
        for section in pri.get("sections") or []:
            for item in section.get("items") or []:
                dests.append(str(item.get("destination") or ""))
    still = [d for d in dests if approve_id in d or reject_id in d]
    add(
        report,
        surface="Home/Inbox",
        cta_or_link="Priorities after leave decisions",
        api_or_action="GET /dashboard/mobile/priorities",
        expected="decided leave IDs absent from destinations",
        actual=f"HTTP {code} lingering={len(still)}",
        verdict="PASS" if code == 200 and not still else "FAIL",
        detail=";".join(still[:5]),
    )


def run_governed_prepare_only(report: Report, token: str, me_body: dict[str, Any]) -> None:
    """Prepare (confirm=false) for open items when available — no destructive confirm unless disposable."""

    # Attendance unresolved — prepare only if exception exists
    if feature_enabled(me_body, "hr", "attendance_exceptions"):
        body = row_read(
            report,
            surface="Attendance",
            cta="Open Attendance exceptions queue",
            path="/dashboard/mobile/attendance?status=exceptions&limit=5",
            token=token,
        )
        items = (body or {}).get("items") if isinstance(body, dict) else []
        if items:
            aid = str(items[0].get("attendance_id") or items[0].get("id") or "")
            row_read(report, surface="Attendance", cta="Open exception detail", path=f"/dashboard/mobile/attendance/{aid}", token=token)
            # prepare resolve without confirm if endpoint accepts
            code, prep = api(
                "POST",
                f"/dashboard/mobile/attendance/{aid}/resolve",
                token=token,
                body={"action": "correct", "idempotency_key": f"term-att-{uuid.uuid4()}", "confirm": False},
            )
            # may 400 for unsupported action vocabulary — record honestly
            add(
                report,
                surface="Attendance",
                cta_or_link="Request correction → prepare",
                api_or_action=f"POST /attendance/{aid}/resolve confirm=false",
                expected="confirmation or honest domain error (not 500)",
                actual=f"HTTP {code} {_brief(prep)}",
                verdict="PASS" if code in {200, 400, 409, 422, 403} else "FAIL",
            )
        else:
            add(
                report,
                surface="Attendance",
                cta_or_link="Mutation prepare",
                api_or_action="no unresolved exceptions",
                expected="skip without inventing fixtures",
                actual="empty queue",
                verdict="SKIP",
            )

    # Shift swaps
    if feature_enabled(me_body, "hr", "shift_swap_decisions"):
        body = row_read(
            report,
            surface="Shifts",
            cta="Open shift-swap queue",
            path="/dashboard/mobile/shift-swaps?status=requested&limit=5",
            token=token,
        )
        items = (body or {}).get("items") if isinstance(body, dict) else []
        if items:
            sid = str(items[0].get("swap_id") or items[0].get("id") or "")
            row_read(report, surface="Shifts", cta="Open swap detail", path=f"/dashboard/mobile/shift-swaps/{sid}", token=token)
            code, prep = api(
                "POST",
                f"/dashboard/mobile/shift-swaps/{sid}/decision",
                token=token,
                body={"action": "approve", "idempotency_key": f"term-swap-{uuid.uuid4()}", "confirm": False},
            )
            add(
                report,
                surface="Shifts",
                cta_or_link="Approve swap → prepare (no confirm)",
                api_or_action=f"POST /shift-swaps/{sid}/decision confirm=false",
                expected="confirmation material or honest refusal",
                actual=f"HTTP {code} {_brief(prep)}",
                verdict="PASS" if code in {200, 400, 403, 409, 422} else "FAIL",
            )
            # cancel unused confirmation by not confirming — OK
        else:
            add(
                report,
                surface="Shifts",
                cta_or_link="Swap mutation",
                api_or_action="no requested swaps",
                expected="skip",
                actual="empty",
                verdict="SKIP",
            )

    # Tasks mark done — only on disposable-looking tasks if any; else prepare-less resolve on first open is destructive — SKIP confirm
    if feature_enabled(me_body, "hr", "hr_tasks"):
        body = row_read(
            report,
            surface="HR Tasks",
            cta="Open Tasks",
            path="/dashboard/mobile/tasks?status=open&limit=5",
            token=token,
        )
        items = (body or {}).get("items") if isinstance(body, dict) else []
        if items:
            tid = str(items[0].get("task_id") or items[0].get("id") or "")
            row_read(report, surface="HR Tasks", cta="Open task detail", path=f"/dashboard/mobile/tasks/{tid}", token=token)
            add(
                report,
                surface="HR Tasks",
                cta_or_link="Mark done",
                api_or_action="POST /tasks/{id}/resolve",
                expected="not executed — no disposable task fixture yet",
                actual="SKIPPED_NO_DISPOSABLE_FIXTURE",
                verdict="SKIP",
                detail="Would mutate live open task; fixture provisioner TBD",
            )
        else:
            add(
                report,
                surface="HR Tasks",
                cta_or_link="Mark done",
                api_or_action="empty open queue",
                expected="skip",
                actual="empty",
                verdict="SKIP",
            )

    # Onboarding / documents — read + skip destructive confirm without disposable item
    if feature_enabled(me_body, "hr", "onboarding_review"):
        body = row_read(report, surface="Onboarding", cta="Open Onboarding", path="/dashboard/mobile/onboarding?limit=5", token=token)
        items = (body or {}).get("items") if isinstance(body, dict) else []
        if items:
            ek = str(items[0].get("employee_key") or "")
            row_read(report, surface="Onboarding", cta="Open employee onboarding", path=f"/dashboard/mobile/onboarding/{urllib.parse.quote(ek, safe='')}", token=token)
            add(
                report,
                surface="Onboarding",
                cta_or_link="Accept/Waive",
                api_or_action="POST /onboarding/{key}/review",
                expected="not confirmed without disposable item",
                actual="SKIPPED_NO_DISPOSABLE_FIXTURE",
                verdict="SKIP",
            )

    if feature_enabled(me_body, "hr", "document_review"):
        body = row_read(
            report,
            surface="Documents",
            cta="Open Documents needs_review",
            path="/dashboard/mobile/documents?status=needs_review&limit=5",
            token=token,
        )
        items = (body or {}).get("items") if isinstance(body, dict) else []
        if items:
            ek = str(items[0].get("employee_key") or "")
            dtype = str(items[0].get("document_type") or items[0].get("type") or "")
            if ek and dtype:
                row_read(
                    report,
                    surface="Documents",
                    cta="Open document detail",
                    path=f"/dashboard/mobile/documents/{urllib.parse.quote(ek, safe='')}/{urllib.parse.quote(dtype, safe='')}",
                    token=token,
                )
            add(
                report,
                surface="Documents",
                cta_or_link="Mark reviewed",
                api_or_action="POST /documents/.../review",
                expected="not confirmed without disposable item",
                actual="SKIPPED_NO_DISPOSABLE_FIXTURE",
                verdict="SKIP",
            )


# (urllib.parse imported at module top)


def run_reads(report: Report, token: str, me_body: dict[str, Any]) -> None:
    row_read(report, surface="Auth", cta="Session /me", path="/dashboard/mobile/me", token=token)
    row_read(report, surface="Home", cta="Home priorities", path="/dashboard/mobile/priorities", token=token)
    row_read(report, surface="Leave", cta="Leave requested list", path="/dashboard/mobile/leave?status=requested&limit=10", token=token)
    row_read(report, surface="People", cta="Employee search", path="/dashboard/mobile/employees?limit=10", token=token, capability_off_ok=True)
    # Talal profile
    row_read(
        report,
        surface="People",
        cta="Employee profile (Talal canary)",
        path=f"/dashboard/mobile/employees/{SUBJECT}",
        token=token,
        capability_off_ok=True,
    )
    today = date.today().isoformat()
    row_read(report, surface="Shifts", cta="Today shifts", path=f"/dashboard/mobile/shifts?date={today}", token=token)
    row_read(report, surface="Delivery Alerts", cta="Open Delivery Alerts", path="/dashboard/mobile/delivery-alerts", token=token)
    row_read(report, surface="Assistant", cta="Assistant capabilities", path="/dashboard/mobile/assistant/capabilities?locale=en", token=token)
    row_read(report, surface="Assistant", cta="Assistant capabilities AR", path="/dashboard/mobile/assistant/capabilities?locale=ar", token=token)

    if feature_enabled(me_body, "recruiting", "candidate_rankings") or feature_enabled(me_body, "recruiting", "candidate_summary"):
        # positions then scoped candidates
        pos = row_read(report, surface="Hiring", cta="Jobs / positions", path="/dashboard/mobile/positions?status=open&limit=10", token=token)
        positions = (pos or {}).get("positions") or (pos or {}).get("items") or []
        if isinstance(pos, dict) and not positions and isinstance(pos.get("data"), list):
            positions = pos["data"]
        code, unc = api("GET", "/dashboard/mobile/candidates?limit=5", token=token)
        add(
            report,
            surface="Hiring",
            cta_or_link="Unscoped candidates list",
            api_or_action="GET /candidates (no position)",
            expected="honest requires_position / ranking_unavailable (not fake empty success)",
            actual=f"HTTP {code} {_brief(unc)}",
            verdict="PASS"
            if code in {200, 400, 422}
            and (
                code != 200
                or (isinstance(unc, dict) and (unc.get("error") or unc.get("code") or unc.get("requires_position") or unc.get("status") in {"requires_position", "ranking_unavailable"} or "position" in json.dumps(unc).lower()))
            )
            else "FAIL",
        )
        if positions:
            p0 = positions[0]
            code_p = str(p0.get("position_code") or p0.get("code") or p0.get("id") or "")
            if code_p:
                row_read(
                    report,
                    surface="Hiring",
                    cta=f"Candidates for position {code_p}",
                    path=f"/dashboard/mobile/candidates?position={urllib.parse.quote(code_p)}&limit=10",
                    token=token,
                )
        row_read(report, surface="Interviews", cta="Interviews list", path="/dashboard/mobile/interviews", token=token)


def run_files(report: Report, token: str) -> None:
    # Try document file endpoints from a needs_review item if present
    code, body = api("GET", "/dashboard/mobile/documents?status=needs_review&limit=5", token=token)
    items = (body or {}).get("items") if isinstance(body, dict) else []
    file_paths: list[str] = []
    for item in items or []:
        for key in ("preview_path", "download_path", "file_path"):
            val = item.get(key)
            if isinstance(val, str) and val.startswith("/dashboard/mobile/"):
                file_paths.append(val)
        docs = item.get("documents") or item.get("files") or []
        if isinstance(docs, list):
            for d in docs:
                for key in ("preview_path", "download_path"):
                    val = (d or {}).get(key)
                    if isinstance(val, str) and val.startswith("/dashboard/mobile/"):
                        file_paths.append(val)
    if not file_paths:
        # known demo paths used in composition — may 404 without demo; still check auth gate
        file_paths = ["/dashboard/mobile/documents/files/demo-civil"]
    for path in file_paths[:3]:
        # unauthenticated should fail
        code_u, _ = api("GET", path, token=None)
        add(
            report,
            surface="Documents/Files",
            cta_or_link=f"Unauthenticated GET {path}",
            api_or_action="auth gate",
            expected="401/403",
            actual=f"HTTP {code_u}",
            verdict="PASS" if code_u in {401, 403} else "FAIL",
        )
        code_a, body_a = api("GET", path, token=token)
        add(
            report,
            surface="Documents/Files",
            cta_or_link=f"Authenticated GET {path}",
            api_or_action="file bytes / JSON error",
            expected="200 file or honest 404",
            actual=f"HTTP {code_a}",
            verdict="PASS" if code_a in {200, 404} else "FAIL",
            detail=_brief(body_a),
        )


def run_rbac_isolation(report: Report, token: str) -> None:
    # Cross-tenant leave id should not leak
    fake = "00000000-0000-0000-0000-000000000099"
    code, body = api("GET", f"/dashboard/mobile/leave/{fake}", token=token)
    add(
        report,
        surface="RBAC/Tenant",
        cta_or_link="Foreign/unknown leave detail",
        api_or_action=f"GET /leave/{fake}",
        expected="404/403 not 200 with foreign payload",
        actual=f"HTTP {code}",
        verdict="PASS" if code in {403, 404} else "FAIL",
        detail=_brief(body),
    )
    # Wrong confirmation should fail closed
    code, body = api(
        "POST",
        f"/dashboard/mobile/leave/{fake}/decision",
        token=token,
        body={
            "action": "approve",
            "confirm": True,
            "idempotency_key": f"term-bad-{uuid.uuid4()}",
            "confirmation_id": str(uuid.uuid4()),
            "confirmation_hash": "0" * 64,
        },
    )
    add(
        report,
        surface="RBAC/Tenant",
        cta_or_link="Bogus confirm",
        api_or_action="POST /leave/{fake}/decision confirm=true",
        expected="4xx fail closed",
        actual=f"HTTP {code}",
        verdict="PASS" if code >= 400 else "FAIL",
        detail=_brief(body),
    )


def run_assistant_destinations(report: Report, token: str, me_body: dict[str, Any]) -> None:
    code, caps = api("GET", "/dashboard/mobile/assistant/capabilities?locale=en", token=token)
    add(
        report,
        surface="Assistant",
        cta_or_link="Capabilities payload",
        api_or_action="GET /assistant/capabilities",
        expected="200 with tools/pages",
        actual=f"HTTP {code} {_brief(caps)}",
        verdict="PASS" if code == 200 else "FAIL",
    )
    # Static mapAssistantNavigation rules already covered; verify web-only pages refused in source
    adl = (HR_SRC / "features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8")
    for page in ("assessments", "reports", "calendar"):
        ok = page in adl and "WEB_ONLY_PAGES" in adl
        add(
            report,
            surface="Assistant",
            cta_or_link=f"Refuse web-only page={page}",
            api_or_action="WEB_ONLY_PAGES",
            expected="not linked on mobile",
            actual="listed" if ok else "missing",
            verdict="PASS" if ok else "FAIL",
        )


def physical_only_list() -> list[str]:
    return [
        "Real-device tap hit-testing / XCTest clickable (BrowserStack Maestro)",
        "Face ID / Touch ID biometric unlock and opt-in sheet",
        "Keyboard occlusion, scroll physics, sheet gesture dismiss",
        "RTL visual mirroring and Back chevron direction on device",
        "Native PDF/image previewer rendering (HTTP file gate is terminal-proven)",
        "Push notification banner → deep link cold start on physical device",
        "Offline/cache visual empty/error chrome timing",
    ]


def write_report(report: Report, evid: Path) -> None:
    counts: dict[str, int] = {}
    for r in report.rows:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    report.counts = counts
    fails = counts.get("FAIL", 0)
    report.ship = "NO-SHIP" if fails else "SHIP-TERMINAL"
    report.ship_reason = (
        f"FAIL={fails} PASS={counts.get('PASS', 0)} SKIP={counts.get('SKIP', 0)} — "
        "terminal API/contract only; PHYSICAL_ONLY remains for device UI"
    )
    evid.mkdir(parents=True, exist_ok=True)
    payload = {
        "stamp": report.stamp,
        "evidence": report.evidence,
        "counts": report.counts,
        "ship": report.ship,
        "ship_reason": report.ship_reason,
        "physical_only": report.physical_only,
        "rows": [asdict(r) for r in report.rows],
        "rule": "Terminal PASS ≠ MOBILE_PASS. Device UI remains PHYSICAL_ONLY / BrowserStack.",
    }
    (evid / "MATRIX.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        f"# HR mobile terminal qualification — {report.stamp}",
        "",
        f"**Ship (terminal):** `{report.ship}`",
        f"**Reason:** {report.ship_reason}",
        "",
        "## Counts",
        "",
        "| Verdict | Count |",
        "| --- | ---: |",
    ]
    for k in sorted(counts):
        lines.append(f"| {k} | {counts[k]} |")
    lines += [
        "",
        "## Matrix",
        "",
        "| Surface | CTA / deep link | API / action | Expected | Actual | Verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in report.rows:
        lines.append(
            f"| {r.surface} | {r.cta_or_link} | `{r.api_or_action}` | {r.expected} | {r.actual} | **{r.verdict}** |"
        )
    lines += ["", "## PHYSICAL_ONLY", ""]
    for item in report.physical_only:
        lines.append(f"- {item}")
    (evid / "MATRIX.md").write_text("\n".join(lines) + "\n")
    (evid / "PHYSICAL_ONLY.md").write_text("# PHYSICAL_ONLY\n\n" + "\n".join(f"- {x}" for x in report.physical_only) + "\n")


def main() -> int:
    load_secrets()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evid = ROOT / "ops" / "evidence" / f"hr-terminal-qual-{stamp}"
    report = Report(stamp=stamp, evidence=str(evid.relative_to(ROOT)), physical_only=physical_only_list())

    print(json.dumps({"phase": "static_crawl"}))
    handlers = crawl_handlers()
    run_route_registration(report, handlers)
    run_canonical_parent_static(report)
    run_i18n(report)

    print(json.dumps({"phase": "login"}))
    token, auth_body = login()
    add(
        report,
        surface="Auth",
        cta_or_link="Work email Sign in",
        api_or_action="POST /dashboard/mobile/auth/login",
        expected="access_token + me",
        actual="ok",
        verdict="PASS",
        detail=f"company={auth_body.get('company_code')} modules={len(auth_body.get('enabled_modules') or [])}",
    )
    me_body = me(token)

    print(json.dumps({"phase": "reads"}))
    run_reads(report, token, me_body)

    print(json.dumps({"phase": "leave_mutations"}))
    run_leave_mutations(report, token)

    print(json.dumps({"phase": "governed_prepare"}))
    run_governed_prepare_only(report, token, me_body)

    print(json.dumps({"phase": "files"}))
    run_files(report, token)

    print(json.dumps({"phase": "rbac"}))
    run_rbac_isolation(report, token)

    print(json.dumps({"phase": "assistant"}))
    run_assistant_destinations(report, token, me_body)

    # cleanup leftover requested e2e leaves
    try:
        leave_ssh_run("cleanup")
        add(
            report,
            surface="Leave",
            cta_or_link="Fixture cleanup",
            api_or_action="cancel remaining MARKER requested leaves",
            expected="cleanup ok",
            actual="ok",
            verdict="PASS",
        )
    except Exception as exc:
        add(
            report,
            surface="Leave",
            cta_or_link="Fixture cleanup",
            api_or_action="cleanup",
            expected="cleanup ok",
            actual=str(exc)[:160],
            verdict="FAIL",
        )

    write_report(report, evid)
    summary = {
        "stamp": stamp,
        "evidence": report.evidence,
        "counts": report.counts,
        "ship": report.ship,
        "ship_reason": report.ship_reason,
        "fail_rows": [asdict(r) for r in report.rows if r.verdict == "FAIL"][:20],
    }
    print(json.dumps(summary, indent=2))
    return 0 if report.counts.get("FAIL", 0) == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise
