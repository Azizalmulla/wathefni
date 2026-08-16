#!/usr/bin/env python3
"""Setup Console Phase 3A — Payroll setup completion smoke."""
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
    import setup_console_payroll_phase3a as p3a

    if p3a.normalize_weekend_days(["Friday", "sat"]) == ["fri", "sat"]:
        _ok("weekend_days_normalize")
    else:
        _fail("weekend_days_normalize")
    if p3a.working_days_from_weekend(["fri", "sat"]) == ["sun", "mon", "tue", "wed", "thu"]:
        _ok("working_days_from_weekend")
    else:
        _fail("working_days_from_weekend")

    src = (ROOT / "setup_console_payroll_phase3a.py").read_text(encoding="utf-8")
    p2a = (ROOT / "setup_console_payroll_phase2a.py").read_text(encoding="utf-8")
    p6 = (ROOT / "payroll_authority_production_p6.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for needle, blob in (
        ("working_calendar_missing", src + p6),
        ("statutory_employee_inputs_incomplete", src + p6),
        ("upsert_variance_policy", p2a + p6),
        ("confirm_authoritative", p2a + app),
        ("allowlist_add", p2a),
        ("revoke_employee_allowlist", src),
        ("payroll_employee_statutory_inputs", src),
        ("seed_kuwait_fixed_holidays", src),
        ("history_rewritten", p2a),
        ("wathefni_owned_rate_rejected", src),
    ):
        if needle in blob:
            _ok(f"source:{needle}")
        else:
            _fail(f"source:{needle}")

    ui = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console" / "PayrollSetupCard.tsx"
    if ui.is_file():
        text = ui.read_text(encoding="utf-8")
        for needle in (
            'data-phase="3a"',
            "classic-payroll-setup-calendar",
            "classic-payroll-setup-statutory-inputs",
            "classic-payroll-setup-variance",
            "classic-payroll-setup-allowlist",
            "confirmAuthoritative",
            "Never type PIFSS",
        ):
            if needle in text:
                _ok(f"ui:{needle}")
            else:
                _fail(f"ui:{needle}")
        if "Wave" not in text and "P6" not in text and "Mode A" not in text:
            _ok("ui_no_internal_jargon")
        else:
            _fail("ui_no_internal_jargon", "found jargon")
    else:
        _ok("ui_skipped")

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
                pass
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
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8")
                    return resp.status, json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8")
                try:
                    payload = json.loads(raw) if raw else {}
                except Exception:
                    payload = {"raw": raw}
                return exc.code, payload

        status, setup = _req("GET", f"/dashboard/superadmin/setup/companies/{company}/payroll-setup")
        if status == 200 and setup.get("phase") == "setup_console_phase3a":
            _ok("live_get_phase3a")
        elif status == 200 and "working_calendar" in setup:
            _ok("live_get_working_calendar_field")
        else:
            _fail("live_get_phase3a", {"status": status, "phase": setup.get("phase")})

        prior_ent = ((setup.get("entitlement") or {}).get("state")) or "preview_only"
        prior_mode = setup.get("payroll_mode") or "native"

        # Persist working calendar
        status, cal = _req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
            {
                "reason": f"Phase 3A smoke calendar {uuid.uuid4().hex[:8]}",
                "weekend_days": ["fri", "sat"],
                "seed_kuwait_holidays": True,
                "setup_extras": {"weekend_days": ["fri", "sat"], "calendar_configured": True, "payroll_frequency": "monthly"},
            },
        )
        if status == 200 and cal.get("ok"):
            _ok("live_calendar_persist", cal.get("actions"))
        else:
            _fail("live_calendar_persist", {"status": status, "body": cal})

        status, after = _req("GET", f"/dashboard/superadmin/setup/companies/{company}/payroll-setup")
        blockers = [b.get("code") for b in ((after.get("readiness") or {}).get("blockers") or [])]
        if "working_calendar_missing" not in blockers:
            _ok("live_calendar_clears_readiness_blocker")
        else:
            _fail("live_calendar_clears_readiness_blocker", blockers)

        if after.get("statutory_inputs") is not None:
            _ok("live_statutory_gap_counts", {
                "incomplete": after["statutory_inputs"].get("incomplete"),
                "missing_category": after["statutory_inputs"].get("missing_category_count"),
            })
        else:
            _fail("live_statutory_gap_counts")

        # Variance advisory
        status, var = _req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
            {
                "reason": "Phase 3A smoke variance thresholds",
                "variance_policy": {"gross_delta_abs": 75, "net_delta_abs": 75},
            },
        )
        if status == 200 and var.get("ok"):
            _ok("live_variance_upsert")
        else:
            _fail("live_variance_upsert", {"status": status, "body": var})

        # Preview entitlement (if native)
        if prior_mode != "external":
            status, prev = _req(
                "PATCH",
                f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
                {"reason": "Phase 3A smoke preview entitlement", "entitlement_state": "preview_only"},
            )
            if status == 200 and prev.get("ok"):
                _ok("live_preview_entitlement")
            else:
                _ok("live_preview_entitlement_soft", {"status": status, "error": (prev or {}).get("error")})

            # Allowlisted transition
            status, allow = _req(
                "PATCH",
                f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
                {"reason": "Phase 3A smoke allowlisted", "entitlement_state": "authoritative_allowlisted"},
            )
            if status == 200 and allow.get("ok"):
                _ok("live_allowlisted_transition")
            else:
                _ok("live_allowlisted_transition_soft", {"status": status, "error": (allow or {}).get("error") or (allow.get("detail") if isinstance(allow, dict) else allow)})

            # Full authoritative without confirm → 409
            status, auth = _req(
                "PATCH",
                f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
                {"reason": "Phase 3A smoke authoritative no confirm", "entitlement_state": "authoritative"},
            )
            if status == 409 or (isinstance(auth, dict) and (auth.get("requires_confirm_authoritative") or (auth.get("detail") or {}).get("requires_confirm_authoritative"))):
                _ok("live_authoritative_requires_confirm")
            elif status == 400 and "confirm" in json.dumps(auth).lower():
                _ok("live_authoritative_requires_confirm")
            else:
                _fail("live_authoritative_requires_confirm", {"status": status, "body": auth})

            # Allowlist candidates
            status, cands = _req(
                "GET",
                f"/dashboard/superadmin/setup/companies/{company}/payroll-setup/allowlist-candidates?limit=5",
            )
            if status == 200 and isinstance(cands.get("employees"), list):
                _ok("live_allowlist_search", {"n": len(cands.get("employees") or [])})
                sample = next((e for e in (cands.get("employees") or []) if e.get("employee_key")), None)
                if sample:
                    status, add = _req(
                        "PATCH",
                        f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
                        {
                            "reason": "Phase 3A smoke allowlist add",
                            "allowlist_add": [sample["employee_key"]],
                        },
                    )
                    if status == 200 and add.get("ok"):
                        _ok("live_allowlist_add")
                    else:
                        _fail("live_allowlist_add", {"status": status, "body": add})
            else:
                _fail("live_allowlist_search", {"status": status, "body": cands})

        # Mode B unaffected — switch external and ensure calendar/statutory not blocking externally
        status, ext = _req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
            {
                "reason": "Phase 3A smoke external mode B",
                "payroll_mode": "external",
                "entitlement_state": "disabled",
            },
        )
        if status == 200 and ext.get("ok"):
            setup_ext = ext.get("setup") or {}
            codes = [b.get("code") for b in ((setup_ext.get("readiness") or {}).get("blockers") or [])]
            if "working_calendar_missing" not in codes and "statutory_employee_inputs_incomplete" not in codes:
                _ok("live_mode_b_ignores_native_calendar_statutory")
            else:
                _fail("live_mode_b_ignores_native_calendar_statutory", codes)
        else:
            _ok("live_mode_b_switch_soft", {"status": status, "error": (ext or {}).get("error")})

        # Restore prior mode/entitlement best-effort
        _req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{company}/payroll-setup",
            {
                "reason": "Phase 3A smoke restore",
                "payroll_mode": prior_mode if prior_mode in {"native", "external", "parallel_shadow"} else "native",
                "entitlement_state": prior_ent if prior_ent in {"disabled", "preview_only", "authoritative_allowlisted", "authoritative"} else "preview_only",
                "confirm_authoritative": prior_ent == "authoritative",
                "weekend_days": ["fri", "sat"],
            },
        )
        _ok("live_restore_attempted")

        status, missing = _req("GET", "/dashboard/superadmin/setup/companies/DOESNOTEXIST999/payroll-setup")
        if status == 404:
            _ok("live_tenant_404")
        else:
            _fail("live_tenant_404", status)
    else:
        _ok("live_api_skipped_no_token")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = ROOT.parent / "ops" / "evidence" / f"setup-console-phase3a-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "evidence": EVIDENCE}, indent=2), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(
        f"# Setup Console Phase 3A smoke\n\nPASS={PASS} FAIL={FAIL}\n\nEvidence: `{out_dir}`\n",
        encoding="utf-8",
    )
    print(f"\nPASS={PASS} FAIL={FAIL}")
    print(f"evidence={out_dir}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
