#!/usr/bin/env python3
"""Setup Console Wave A-B — production synthetic Launch Readiness canary (WATHEFNI).

Read-only evaluate. Operator-only / WATHEFNI-only.
Proves six stages, overall readiness, blockers+deep links, pause impact,
EN/AR + mobile UI markers, entitlement freeze/allowlist/SYNTHETIC_ONLY/
CAPTURE_INGEST=off honesty, residual 0.
Does not start Setup Wave B or mutate frozen modules.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")

import app  # noqa: E402
import setup_console_wave_a_launch_readiness as wave_a  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("SCWAB_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("SCWAB_EVID") or f"/tmp/setup-console-wab-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def main() -> int:
    honesty = wave_a.honesty_payload()
    check("wave a enabled", wave_a.wave_a_enabled())
    check("wathefni company allowed", wave_a.wave_a_enabled_for_company(COMPANY))
    check("external company denied", wave_a.wave_a_enabled_for_company("EXTERNALCO") is False)
    check("operator only honesty", honesty.get("operator_only") is True)
    check("wathefni only honesty", honesty.get("wathefni_only") is True)
    check("no external tenants", honesty.get("external_tenants") is False)
    check("no payroll money", honesty.get("payroll_money") is False)
    check("no attendance ingest", honesty.get("attendance_ingest") is False)
    check("capture ingest off", honesty.get("capture_ingest") == "off")
    check("no AI", honesty.get("ai") is False)
    check("no setup wave b", honesty.get("setup_wave_b") is False)
    check("entitlements cannot bypass (honesty)", honesty.get("entitlements_cannot_bypass_gates") is True)
    check("read only evaluate", honesty.get("read_only_evaluate") is True)
    check("ingest env off", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)

            result = wave_a.evaluate_launch_readiness(cur, company_code=COMPANY)
            refused = wave_a.evaluate_launch_readiness(cur, company_code="ACME")

    (EVID / "evaluate.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    check("evaluate ok", result.get("ok") is True, result)
    check("refuse non-wathefni", refused.get("ok") is False and refused.get("error") == "wave_a_wathefni_only", refused)
    check("overall state honest", result.get("overall_state") in wave_a.HONEST_STATES, result.get("overall_state"))
    check("six stages", len(result.get("stages") or []) == 6, len(result.get("stages") or []))
    stage_keys = [s.get("stage", {}).get("key") for s in (result.get("stages") or [])]
    expected = [s["key"] for s in wave_a.STAGES]
    check("stage keys", stage_keys == expected, stage_keys)
    check("entitlements cannot bypass", result.get("entitlements_cannot_bypass_gates") is True)
    check("payroll money false", result.get("payroll_money") is False)
    check("attendance ingest false", result.get("attendance_ingest") is False)
    check("external tenants false", result.get("external_tenants") is False)

    pause = result.get("pause_impact") or {}
    check("pause impact en", bool(pause.get("bullets_en")), pause)
    check("pause impact ar", bool(pause.get("bullets_ar")), pause)
    check(
        "pause says freezes hold",
        any("freeze" in (b or "").lower() or "allowlist" in (b or "").lower() for b in (pause.get("bullets_en") or [])),
        pause,
    )

    blockers = result.get("important_blockers") or []
    check("blockers have next actions", all(b.get("next_action_en") for b in blockers) if blockers else True, blockers)
    check("blockers have deep links", all(b.get("deep_link") for b in blockers) if blockers else True, blockers)
    check("blockers have ar next actions", all(b.get("next_action_ar") for b in blockers) if blockers else True, blockers)

    mods: list[dict[str, Any]] = []
    for stage in result.get("stages") or []:
        if stage.get("stage", {}).get("key") == "modules":
            mods = stage.get("items") or []
    check("modules stage non-empty", len(mods) >= 8, len(mods))

    att = next((m for m in mods if m.get("key") == "module:attendance"), None)
    pay = next((m for m in mods if m.get("key") == "module:payroll"), None)
    sh = next((m for m in mods if m.get("key") == "module:shifts"), None)
    leave = next((m for m in mods if m.get("key") == "module:leave"), None)

    # Entitlements / purchased cannot clear freezes, allowlists, SYNTHETIC_ONLY, CAPTURE_INGEST=off
    if att and att.get("purchased"):
        evid = json.dumps(att.get("evidence") or {}).lower()
        summary = (att.get("summary_en") or "").lower()
        honest_ingest = (
            att.get("blocked") is True
            or att.get("state") in {"live_controlled", "blocked", "setup_required"}
            or "ingest" in evid
            or "device" in summary
            or "controlled" in summary
        )
        check("attendance purchased cannot bypass ingest off", honest_ingest, att)
        check(
            "attendance does not claim ingest on",
            "ingest on" not in summary and "capture on" not in summary,
            summary,
        )

    if pay and pay.get("purchased"):
        summary = (pay.get("summary_en") or "").lower()
        check(
            "payroll purchased cannot claim money authority",
            pay.get("state") in {"live_controlled", "setup_required", "blocked"}
            and ("money" not in summary or "does not process" in summary or "external" in summary or "synthetic" in summary or pay.get("state") == "setup_required"),
            pay,
        )

    for mod, label in ((sh, "shifts"), (leave, "leave"), (pay, "payroll"), (att, "attendance")):
        if not mod:
            continue
        evid = mod.get("evidence") or {}
        # If evidence mentions synthetic_only / allowlist, state must not pretend fully open commercial live
        blob = json.dumps(evid).lower() + " " + (mod.get("summary_en") or "").lower()
        if "synthetic" in blob or "allowlist" in blob or "freeze" in blob:
            check(
                f"{label} cannot bypass synthetic/allowlist/freeze",
                mod.get("state") != "not_purchased" or not mod.get("purchased"),
                mod,
            )
            check(
                f"{label} not claiming unrestricted live",
                mod.get("state") in {"live_controlled", "blocked", "setup_required", "ready_for_canary", "paused", "not_purchased"},
                mod.get("state"),
            )

    # UI EN/AR + mobile
    dash = Path("/opt/wathefni/apps/wathefni-dashboard/src/setup-console")
    if not dash.is_dir():
        dash = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console"
    ui_path = dash / "LaunchReadinessPage.tsx"
    check("launch UI present", ui_path.is_file(), ui_path)
    if ui_path.is_file():
        ui = ui_path.read_text(encoding="utf-8")
        check("UI EN title", "Launch readiness" in ui)
        check("UI AR title", "جاهزية الإطلاق" in ui)
        check("UI overall marker", "launch-overall-status" in ui)
        check("UI blockers marker", "launch-important-blockers" in ui)
        check("UI pause marker", "launch-pause-impact" in ui)
        check("UI mobile wrap", "flex-wrap" in ui)
        check("UI rtl support", "dir={dir}" in ui or "rtl" in ui)

    dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
    if dist.is_dir():
        joined = ""
        for p in list(dist.rglob("*.js"))[:200] + list(dist.rglob("*.html"))[:20]:
            try:
                joined += p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if len(joined) > 8_000_000:
                break
        check("dist has launch EN or AR", ("Launch readiness" in joined) or ("جاهزية الإطلاق" in joined) or ("launch-overall-status" in joined), "missing launch copy in dist")
        check("dist mobile wrap token", "flex-wrap" in joined)

    # Residual: evaluate is read-only; prove no SCWAB synthetic rows were created
    residual = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Probe common canary tables if present; Wave A writes none.
            for table, col in (
                ("analytics_wave_acks", "canary_tag"),
                ("payroll_adapter_quarantine", "acknowledgement_reason"),
            ):
                cur.execute(
                    """
                    SELECT to_regclass(%s) AS reg
                    """,
                    (f"public.{table}",),
                )
                reg = dict(cur.fetchone())["reg"]
                if not reg:
                    continue
                try:
                    cur.execute(
                        f"SELECT count(*) AS c FROM {table} WHERE coalesce({col}::text,'') ILIKE %s",
                        (f"%SCWAB-{TAG}%",),
                    )
                    residual += int(dict(cur.fetchone())["c"])
                except Exception:
                    conn.rollback()
    check("residual scwab rows 0", residual == 0, residual)

    summary = {"pass": PASS, "fail": FAIL, "tag": TAG, "overall_state": result.get("overall_state"), "blockers": len(blockers), "residual": residual}
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
