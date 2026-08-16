#!/usr/bin/env python3
"""Setup Console Wave A — launch readiness smoke (static + optional staging DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = FAIL = 0
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import setup_console_wave_a_launch_readiness as wave_a

    check("wave a version", bool(wave_a.WAVE_A_VERSION))
    check("wathefni only constant", wave_a.ALLOWED_COMPANY == "WATHEFNI")
    check("honest states complete", set(wave_a.HONEST_STATES) == {
        "not_purchased",
        "setup_required",
        "blocked",
        "ready_for_canary",
        "live_controlled",
        "paused",
    })
    check("six stages", len(wave_a.STAGES) == 6)
    honesty = wave_a.honesty_payload()
    check("honesty operator only", honesty.get("operator_only") is True)
    check("honesty no payroll money", honesty.get("payroll_money") is False)
    check("honesty no attendance ingest", honesty.get("attendance_ingest") is False)
    check("honesty no wave b", honesty.get("setup_wave_b") is False)
    check("honesty entitlements cannot bypass", honesty.get("entitlements_cannot_bypass_gates") is True)
    check("external company helper denied", wave_a.wave_a_enabled_for_company("EXTERNALCO") is False)

    # External company refused without DB
    class _Cur:
        def execute(self, *a, **k):
            raise AssertionError("should not query for non-wathefni")

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    refused = wave_a.evaluate_launch_readiness(_Cur(), company_code="ACME")
    check("refuses non-wathefni", refused.get("ok") is False and refused.get("error") == "wave_a_wathefni_only", refused)

    # UI surface
    dash = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console"
    if not dash.is_dir():
        dash = Path("/opt/wathefni/apps/wathefni-dashboard/src/setup-console")
    check("launch readiness page present", (dash / "LaunchReadinessPage.tsx").is_file(), dash)
    if (dash / "LaunchReadinessPage.tsx").is_file():
        ui = (dash / "LaunchReadinessPage.tsx").read_text(encoding="utf-8")
        app = (dash / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
        check("UI overall status", "launch-overall-status" in ui)
        check("UI important blockers", "launch-important-blockers" in ui)
        check("UI pause impact", "launch-pause-impact" in ui)
        check("UI EN launch title", "Launch readiness" in ui)
        check("UI AR launch title", "جاهزية الإطلاق" in ui)
        check("UI rtl", "dir={dir}" in ui or "rtl" in ui)
        check("UI mobile wrap", "flex-wrap" in ui)
        check("app wires launch view", "LaunchReadinessPage" in app and "launch" in app)
        check("no giant form in launch page", "textarea" not in ui.lower())

    app_py = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    check("route registered", "/launch-readiness" in app_py)
    check("module imported in app", "setup_console_wave_a_launch_readiness" in app_py)

    # Optional DB path
    if os.environ.get("WATHEFNI_POSTGRES_ENV") and os.environ.get("WATHEFNI_ENV"):
        try:
            import app as orch

            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database() AS db")
                    db = dict(cur.fetchone())["db"]
                    result = wave_a.evaluate_launch_readiness(cur, company_code="WATHEFNI")
            check("db evaluate ok", result.get("ok") is True, result)
            check("overall state present", result.get("overall_state") in wave_a.HONEST_STATES, result.get("overall_state"))
            check("stages returned", len(result.get("stages") or []) == 6)
            check("entitlements cannot bypass", result.get("entitlements_cannot_bypass_gates") is True)
            check("payroll money false", result.get("payroll_money") is False)
            check("attendance ingest false", result.get("attendance_ingest") is False)
            mods = []
            for stage in result.get("stages") or []:
                if stage.get("stage", {}).get("key") == "modules":
                    mods = stage.get("items") or []
            check("modules stage non-empty", len(mods) >= 8, len(mods))
            att = next((m for m in mods if m.get("key") == "module:attendance"), None)
            pay = next((m for m in mods if m.get("key") == "module:payroll"), None)
            if att and att.get("purchased"):
                check("attendance honest ingest block", att.get("blocked") is True or att.get("state") == "live_controlled", att)
            if pay and pay.get("purchased"):
                check(
                    "payroll honest state",
                    pay.get("state") in {"live_controlled", "setup_required", "blocked"},
                    pay,
                )
                check("payroll not claiming money authority", "money" not in (pay.get("summary_en") or "").lower() or "does not process pay money" in (pay.get("summary_en") or "").lower() or pay.get("state") == "setup_required", pay)
            blockers = result.get("important_blockers") or []
            check("blockers have next actions", all(b.get("next_action_en") for b in blockers), blockers)
            check("blockers have deep links", all(b.get("deep_link") for b in blockers), blockers)
            print("db", db)
        except Exception as exc:
            check("db evaluate path", False, exc)
    else:
        print("db path skipped (no postgres env)")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
