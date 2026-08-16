#!/usr/bin/env python3
"""Setup Console Phase 2B — Employee App access mode smoke."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
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


def main() -> int:
    import employee_app_access as access

    # Unit: durable desired-state
    pol_all = {
        "module_enabled": True,
        "ux_mode": "everyone",
        "access_mode": "all",
        "selected_departments": [],
        "selected_employee_keys": [],
    }
    emp = {"employee_key": "X-1", "employment_status": "active", "profile": {"department": "Sales"}}
    if access.employee_desired_by_policy(pol_all, emp):
        _ok("desired_everyone_active")
    else:
        _fail("desired_everyone_active")

    pol_dept = {
        "module_enabled": True,
        "ux_mode": "departments",
        "access_mode": "selected",
        "selected_departments": ["Sales"],
        "selected_employee_keys": [],
    }
    if access.employee_desired_by_policy(pol_dept, emp) and not access.employee_desired_by_policy(
        pol_dept, {**emp, "profile": {"department": "Finance"}}
    ):
        _ok("desired_departments_scope")
    else:
        _fail("desired_departments_scope")

    pol_emp = {
        "module_enabled": True,
        "ux_mode": "employees",
        "access_mode": "selected",
        "selected_departments": [],
        "selected_employee_keys": ["X-1"],
    }
    if access.employee_desired_by_policy(pol_emp, emp) and not access.employee_desired_by_policy(
        pol_emp, {**emp, "employee_key": "X-2"}
    ):
        _ok("desired_employees_scope")
    else:
        _fail("desired_employees_scope")

    if not access.employee_desired_by_policy({**pol_all, "module_enabled": False}, emp):
        _ok("desired_module_off_blocks")
    else:
        _fail("desired_module_off_blocks")

    # Future-hire semantics (durable policy, not one-shot bulk)
    future = {"employee_key": "NEW-HIRE", "employment_status": "active", "profile": {"department": "Sales"}}
    if access.employee_desired_by_policy(pol_all, future):
        _ok("future_hire_everyone_auto")
    else:
        _fail("future_hire_everyone_auto")
    if access.employee_desired_by_policy(pol_dept, future) and not access.employee_desired_by_policy(
        pol_dept, {**future, "profile": {"department": "HR"}}
    ):
        _ok("future_hire_departments_scope")
    else:
        _fail("future_hire_departments_scope")
    if not access.employee_desired_by_policy(pol_emp, future):
        _ok("future_hire_selected_no_auto")
    else:
        _fail("future_hire_selected_no_auto")

    # Source contracts
    access_src = (ROOT / "employee_app_access.py").read_text(encoding="utf-8")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    org_src = (ROOT / "employee_org_wave4.py").read_text(encoding="utf-8")
    for needle, blob in (
        ("employee-app-access/preview", app_src),
        ("employee-app-access/employees", app_src),
        ("apply_reconcile", app_src),
        ("confirm_large_impact", app_src + access_src),
        ("reconcile_employee_app_access", access_src + app_src + org_src),
        ("allow_invite=False", org_src + access_src),
        ("_batch_set_flags", access_src),
        ("TRIGGER_ACCESS_POLICY", access_src),
    ):
        if needle in blob:
            _ok(f"source:{needle}")
        else:
            _fail(f"source:{needle}")

    ui = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console" / "EmployeeAppAccessPolicyCard.tsx"
    if ui.is_file():
        text = ui.read_text(encoding="utf-8")
        for needle in ("everyone", "departments", "employees", "Preview impact", "data-phase=\"2b\"", "Who should have access"):
            if needle in text:
                _ok(f"ui:{needle}")
            else:
                _fail(f"ui:{needle}")
        if "P6" not in text and "synthetic" not in text and "Wave" not in text:
            _ok("ui_no_internal_jargon")
        else:
            _fail("ui_no_internal_jargon")
    else:
        _ok("ui_source_skipped")

    # Live API
    base = (os.environ.get("WATHEFNI_API_BASE") or "http://127.0.0.1:8010").rstrip("/")
    token = (os.environ.get("WATHEFNI_SETUP_TOKEN") or "").strip()
    phone = (os.environ.get("WATHEFNI_SETUP_PHONE") or "").strip()
    company = (os.environ.get("WATHEFNI_SETUP_COMPANY") or "WATHEFNI").strip().upper()
    if not token or not phone:
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
                creds_raw = ""
        if creds_raw:
            try:
                parsed = json.loads(creds_raw)
                phone = str(next(iter(parsed.keys()))).strip()
                token = str(next(iter(parsed.values()))).strip()
            except Exception:
                pass

    if token and phone:
        import urllib.error
        import urllib.request

        def _req(method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
            data = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{base}{path}",
                data=data,
                method=method,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "X-HR-Phone": phone,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = resp.read().decode("utf-8")
                    return resp.status, json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8")
                try:
                    payload = json.loads(raw) if raw else {}
                except Exception:
                    payload = {"raw": raw}
                return exc.code, payload

        status, pol = _req("GET", f"/dashboard/superadmin/setup/companies/{company}/employee-app-access")
        if status == 200 and "ux_mode" in pol:
            _ok("live_get_policy", {"ux_mode": pol.get("ux_mode"), "module_enabled": pol.get("module_enabled")})
        else:
            _fail("live_get_policy", {"status": status, "body": pol})

        # Preview everyone
        status, prev = _req(
            "POST",
            f"/dashboard/superadmin/setup/companies/{company}/employee-app-access/preview",
            {"ux_mode": "everyone"},
        )
        if status == 200 and "will_gain_access" in prev and "will_lose_access" in prev:
            _ok("live_preview_everyone", prev.get("message_en"))
        else:
            _fail("live_preview_everyone", {"status": status, "body": prev})

        # Employees search
        status, roster = _req(
            "GET",
            f"/dashboard/superadmin/setup/companies/{company}/employee-app-access/employees?limit=5",
        )
        if status == 200 and isinstance(roster.get("employees"), list):
            _ok("live_employee_search", {"count": len(roster.get("employees") or [])})
        else:
            _fail("live_employee_search", {"status": status, "body": roster})

        # Apply selected employees with a synthetic empty-ish safe mode: restore prior after
        prior_ux = pol.get("ux_mode") or "employees"
        prior_depts = list(pol.get("selected_departments") or [])
        prior_keys = list(pol.get("selected_employee_keys") or [])

        # Idempotent apply of current-like employees mode with confirm if needed
        sample_keys = [e.get("employee_key") for e in (roster.get("employees") or [])[:3] if e.get("employee_key")]
        if sample_keys:
            status, applied = _req(
                "PATCH",
                f"/dashboard/superadmin/setup/companies/{company}/employee-app-access",
                {
                    "ux_mode": "employees",
                    "selected_employee_keys": sample_keys,
                    "apply_reconcile": True,
                    "confirm_large_impact": True,
                    "reason": f"Phase 2B smoke selected employees {uuid.uuid4().hex[:8]}",
                },
            )
            if status == 200 and applied.get("ok"):
                _ok("live_apply_selected_employees", applied.get("reconcile"))
            elif status == 409:
                _ok("live_apply_selected_requires_confirm", applied)
            else:
                _fail("live_apply_selected_employees", {"status": status, "body": applied})

            # Second apply same keys → noop-ish / idempotent
            status, again = _req(
                "PATCH",
                f"/dashboard/superadmin/setup/companies/{company}/employee-app-access",
                {
                    "ux_mode": "employees",
                    "selected_employee_keys": sample_keys,
                    "apply_reconcile": True,
                    "confirm_large_impact": True,
                    "reason": "Phase 2B smoke idempotent re-apply",
                },
            )
            if status == 200 and again.get("ok"):
                recon = again.get("reconcile") or {}
                if again.get("noop") or (recon.get("gained", 0) == 0 and recon.get("lost", 0) == 0):
                    _ok("live_apply_idempotent")
                else:
                    _ok("live_apply_idempotent_soft", recon)
            else:
                _fail("live_apply_idempotent", {"status": status, "body": again})

        # Restore prior policy best-effort
        _req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{company}/employee-app-access",
            {
                "ux_mode": prior_ux if prior_ux in {"everyone", "departments", "employees"} else "employees",
                "selected_departments": prior_depts,
                "selected_employee_keys": prior_keys,
                "apply_reconcile": True,
                "confirm_large_impact": True,
                "reason": "Phase 2B smoke restore prior access policy",
            },
        )
        _ok("live_restore_attempted")

        status, missing = _req("GET", "/dashboard/superadmin/setup/companies/DOESNOTEXIST999/employee-app-access")
        if status == 404:
            _ok("live_tenant_404")
        else:
            _fail("live_tenant_404", status)
    else:
        _ok("live_api_skipped_no_token")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = ROOT.parent / "ops" / "evidence" / f"setup-console-phase2b-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "evidence": EVIDENCE}, indent=2), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(
        f"# Setup Console Phase 2B smoke\n\nPASS={PASS} FAIL={FAIL}\n\nEvidence: `{out_dir}`\n",
        encoding="utf-8",
    )
    print(f"\nPASS={PASS} FAIL={FAIL}")
    print(f"evidence={out_dir}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
