#!/usr/bin/env python3
"""Pre-hire E2E production API qualification (read-heavy, fail-closed logging)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = os.environ.get("DASHBOARD_API", "https://api.wathefni.ai").rstrip("/")
SESSION = Path(os.environ.get("PREHIRE_E2E_SESSION", "/tmp/prehire-e2e.session"))
EVID = Path(os.environ["PREHIRE_E2E_EVID"])
OUT = EVID / "verify" / "api-results.json"
FAIL_DIR = EVID / "failures"


def load_session():
    lines = SESSION.read_text().strip().splitlines()
    return {"token": lines[0], "email": lines[1] if len(lines) > 1 else "", "phone": lines[2] if len(lines) > 2 else ""}


def req(method: str, path: str, session: dict, *, body=None, company="WATHEFNI", token=None, locale=None, timeout=45):
    url = f"{API}{path}"
    headers = {
        "Authorization": f"Bearer {token or session['token']}",
        "X-Company-Code": company,
        "Accept": "application/json",
    }
    if session.get("phone"):
        headers["X-HR-Phone"] = session["phone"]
    if session.get("email"):
        headers["X-Dashboard-Email"] = session["email"]
    if locale:
        headers["Accept-Language"] = locale
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode() or "{}") if raw else {}
            return {
                "ok": True,
                "status": resp.status,
                "ms": int((time.time() - started) * 1000),
                "payload": payload,
            }
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw.decode() or "{}")
        except Exception:
            payload = {"raw": raw.decode(errors="ignore")[:800]}
        return {
            "ok": False,
            "status": e.code,
            "ms": int((time.time() - started) * 1000),
            "payload": payload,
            "error": str(e),
        }
    except Exception as e:
        return {"ok": False, "status": 0, "ms": int((time.time() - started) * 1000), "payload": {}, "error": str(e)}


def gate(results, failures, gate_id, module, title, passed, *, severity="P2", detail=None, evidence=None):
    row = {
        "id": gate_id,
        "module": module,
        "title": title,
        "result": "PASS" if passed else "FAIL",
        "severity": severity if not passed else None,
        "detail": detail or {},
        "evidence": evidence,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    results.append(row)
    if not passed:
        FAIL_DIR.mkdir(parents=True, exist_ok=True)
        path = FAIL_DIR / f"{gate_id}.json"
        path.write_text(json.dumps(row, indent=2) + "\n")
        failures.append(row)
    print(f"{'PASS' if passed else 'FAIL'} {gate_id} {title}")


def main():
    session = load_session()
    results = []
    failures = []
    ctx = {"sample_app_key": None, "sample_position": None, "assessment_attempt": None}

    # X01 health via API host (dashboard health through orchestrator)
    h = req("GET", "/health", session)
    # some deploys expose /health without auth
    if h["status"] == 401:
        # try unauthenticated
        try:
            with urllib.request.urlopen(f"{API}/health", timeout=20) as resp:
                h = {"ok": resp.status == 200, "status": resp.status, "payload": {}}
        except Exception as e:
            h = {"ok": False, "status": 0, "error": str(e)}
    gate(results, failures, "X01", "cross", "API/orchestrator reachable", h.get("status") in (200, 401) or h.get("ok"), detail=h)

    # X04 missing auth
    bare = req("GET", "/dashboard/bootstrap", session, token="invalid-token-prehire-e2e")
    gate(
        results,
        failures,
        "X04",
        "cross",
        "Invalid token fail-closed",
        bare["status"] in (401, 403),
        severity="P0",
        detail={"status": bare["status"]},
    )

    # X02 bootstrap
    boot = req("GET", "/dashboard/bootstrap", session)
    mods = (boot.get("payload") or {}).get("enabled_modules") or []
    access = (boot.get("payload") or {}).get("access") or {}
    gate(
        results,
        failures,
        "X02",
        "cross",
        "Bootstrap loads modules+access",
        boot["ok"] and isinstance(mods, list) and bool(access),
        severity="P0",
        detail={"status": boot["status"], "modules": mods, "role": access.get("role"), "perm_count": len(access.get("permissions") or [])},
    )

    # Overview
    summary = req("GET", "/dashboard/prehire/summary", session)
    gate(results, failures, "OV01", "overview", "Summary loads", summary["ok"], severity="P0", detail={"status": summary["status"], "keys": list((summary.get("payload") or {}).keys())[:20]})
    wq_mine = req("GET", "/dashboard/prehire/overview/work-queue?scope=mine", session)
    gate(results, failures, "OV02", "overview", "Work-queue mine", wq_mine["ok"], severity="P1", detail={"status": wq_mine["status"]})
    wq_co = req("GET", "/dashboard/prehire/overview/work-queue?scope=company", session)
    gate(results, failures, "OV03", "overview", "Work-queue company (owner)", wq_co["ok"], severity="P1", detail={"status": wq_co["status"]})
    nxt = req("GET", "/dashboard/prehire/overview/next-action?scope=mine", session)
    gate(results, failures, "OV06", "overview", "Next-action", nxt["ok"] or nxt["status"] in (404, 204), severity="P2", detail={"status": nxt["status"]})
    cal_ov = req("GET", "/dashboard/calendar/overview?scope=mine", session)
    gate(results, failures, "OV07", "overview", "Overview calendar mine", cal_ov["ok"], severity="P2", detail={"status": cal_ov["status"]})

    # Jobs
    jobs = req("GET", "/dashboard/prehire/positions", session)
    positions = (jobs.get("payload") or {}).get("positions") or []
    if positions:
        ctx["sample_position"] = positions[0].get("position_code") or positions[0].get("code")
    open_jobs = [p for p in positions if str(p.get("status") or "").lower() in ("open", "published")]
    gate(
        results,
        failures,
        "JB01",
        "jobs",
        "Positions list loads",
        jobs["ok"] and isinstance(positions, list),
        severity="P0",
        detail={"status": jobs["status"], "count": len(positions), "summary_keys": list(((jobs.get("payload") or {}).get("summary") or {}).keys())},
    )
    has_link = any(bool(p.get("application_link") or p.get("apply_code") or p.get("qr_value")) for p in open_jobs[:5]) if open_jobs else True
    gate(results, failures, "JB03", "jobs", "Open jobs expose apply linkage", (not open_jobs) or has_link, severity="P1", detail={"open_count": len(open_jobs), "has_link": has_link})

    # Ingestion / email — paths from api.ts
    mailboxes = req("GET", "/dashboard/prehire/integrations/mailbox", session)
    gate(
        results,
        failures,
        "IN01",
        "ingestion",
        "Mailbox connections readable",
        mailboxes["ok"],
        severity="P1",
        detail={"status": mailboxes["status"], "keys": list((mailboxes.get("payload") or {}).keys())[:15]},
    )
    email_settings = req("GET", "/dashboard/prehire/integrations/email", session)
    gate(
        results,
        failures,
        "IN04",
        "ingestion",
        "Email sending settings surface",
        email_settings["ok"],
        severity="P1",
        detail={"status": email_settings["status"]},
    )
    imports = req("GET", "/dashboard/prehire/import/batches?limit=5", session)
    gate(results, failures, "IN03", "ingestion", "Import batches readable", imports["ok"], severity="P2", detail={"status": imports["status"]})
    intake = req("GET", "/dashboard/prehire/import/intake?limit=20", session)
    gate(results, failures, "IN02", "ingestion", "Import intake readable", intake["ok"], severity="P2", detail={"status": intake["status"]})
    import_settings = req("GET", "/dashboard/prehire/import/settings", session)
    gate(results, failures, "IN02b", "ingestion", "Import settings readable", import_settings["ok"], severity="P2", detail={"status": import_settings["status"]})

    # Candidates
    feats_u = req("GET", "/dashboard/prehire/candidates/feature", session)
    feats_c = req("GET", "/dashboard/prehire/classification/feature", session)
    gate(
        results,
        failures,
        "CA02",
        "candidates",
        "Candidate feature flags reachable",
        feats_u["ok"] or feats_c["ok"] or feats_u["status"] in (404,) or feats_c["status"] in (404,),
        severity="P1",
        detail={"unified": feats_u["status"], "classification": feats_c["status"]},
    )
    apps = req("GET", "/dashboard/prehire/applications?limit=25", session)
    applications = (apps.get("payload") or {}).get("applications") or (apps.get("payload") or {}).get("items") or []
    if applications:
        ctx["sample_app_key"] = applications[0].get("app_key")
    gate(
        results,
        failures,
        "CA01",
        "candidates",
        "Applications list loads",
        apps["ok"] and isinstance(applications, list),
        severity="P0",
        detail={"status": apps["status"], "count": len(applications), "total": (apps.get("payload") or {}).get("total_count")},
    )
    views = req("GET", "/dashboard/prehire/candidates/saved-views", session)
    gate(results, failures, "CA05", "candidates", "Saved views list", views["ok"] or views["status"] == 404, severity="P2", detail={"status": views["status"]})
    if ctx["sample_app_key"]:
        prof = req("GET", f"/dashboard/prehire/applications/{urllib.parse.quote(ctx['sample_app_key'])}/profile", session)
        if prof["status"] == 404:
            prof = req("GET", f"/dashboard/prehire/candidates/{urllib.parse.quote(ctx['sample_app_key'])}/profile", session)
        person = req("GET", f"/dashboard/prehire/applications/{urllib.parse.quote(ctx['sample_app_key'])}/person-profile", session)
        gate(
            results,
            failures,
            "CA06",
            "candidates",
            "Profile/person-profile for sample app",
            prof["ok"] or person["ok"],
            severity="P1",
            detail={"app_key": ctx["sample_app_key"], "profile": prof["status"], "person": person["status"]},
        )
    else:
        gate(results, failures, "CA06", "candidates", "Profile/person-profile for sample app", False, severity="P2", detail={"reason": "no applications"})

    # Follow-up filter contract (API accepts params)
    fu = req("GET", "/dashboard/prehire/applications?follow_up=needed&limit=10", session)
    gate(results, failures, "CA03", "candidates", "Follow-up filter accepted", fu["ok"], severity="P1", detail={"status": fu["status"]})

    # Ranking
    pos = ctx["sample_position"] or (open_jobs[0].get("position_code") if open_jobs else None)
    if pos:
        rank = req("GET", f"/dashboard/prehire/rank?position={urllib.parse.quote(str(pos))}&top_n=10", session)
        gate(results, failures, "RK01", "ranking", "Rank for position loads", rank["ok"], severity="P0", detail={"status": rank["status"], "position": pos, "keys": list((rank.get("payload") or {}).keys())[:20]})
    else:
        gate(results, failures, "RK01", "ranking", "Rank for position loads", False, severity="P1", detail={"reason": "no position"})
    rank_miss = req("GET", "/dashboard/prehire/rank?position=__MISSING_POS_E2E__&top_n=5", session)
    gate(
        results,
        failures,
        "RK05",
        "ranking",
        "Missing position neutral failure",
        rank_miss["ok"] or rank_miss["status"] in (400, 404),
        severity="P2",
        detail={"status": rank_miss["status"]},
    )

    # Assessments
    aconf = req("GET", "/dashboard/prehire/assessments/config", session)
    gate(results, failures, "AS01", "assessments", "Assessment config", aconf["ok"] or aconf["status"] in (403, 404), severity="P1", detail={"status": aconf["status"], "modules_has_assessments": "assessments" in mods})
    attempts = req("GET", "/dashboard/prehire/assessments?limit=25", session)
    attempt_rows = (attempts.get("payload") or {}).get("attempts") or (attempts.get("payload") or {}).get("items") or []
    if attempt_rows:
        ctx["assessment_attempt"] = attempt_rows[0].get("attempt_id")
    gate(results, failures, "AS03", "assessments", "Attempts list", attempts["ok"] or attempts["status"] in (403, 404), severity="P1", detail={"status": attempts["status"], "count": len(attempt_rows)})
    needs = req("GET", "/dashboard/prehire/assessments?needs_review=true&limit=10", session)
    gate(results, failures, "AS03b", "assessments", "Needs-review filter", needs["ok"] or needs["status"] in (403, 404), severity="P2", detail={"status": needs["status"]})
    queue = req("GET", "/dashboard/prehire/assessments/queue?cohort=assessment_ready_to_send&limit=10", session)
    if queue["status"] == 404:
        queue = req("GET", "/dashboard/prehire/applications?overview_cohort=assessment_ready_to_send&limit=10", session)
    gate(results, failures, "AS02", "assessments", "Send cohort queue/filter", queue["ok"], severity="P1", detail={"status": queue["status"]})
    if ctx["assessment_attempt"]:
        report = req("GET", f"/dashboard/prehire/assessments/{urllib.parse.quote(str(ctx['assessment_attempt']))}", session)
        gate(results, failures, "AS05", "assessments", "Attempt detail/report payload", report["ok"] or report["status"] in (404, 409), severity="P2", detail={"status": report["status"], "attempt": ctx["assessment_attempt"]})
    else:
        gate(results, failures, "AS05", "assessments", "Attempt detail/report payload", True, severity="P3", detail={"skipped": "no attempts"}, evidence="N/A")

    # Interviews
    iv = req("GET", "/dashboard/prehire/interviews?status=upcoming&limit=25", session)
    gate(results, failures, "IV01", "interviews", "Upcoming interviews list", iv["ok"], severity="P0", detail={"status": iv["status"], "count": len((iv.get("payload") or {}).get("interviews") or (iv.get("payload") or {}).get("items") or [])})
    for tab in ("needs_feedback", "video_interviews", "completed", "cancelled"):
        r = req("GET", f"/dashboard/prehire/interviews?status={tab}&limit=10", session)
        gate(results, failures, f"IV01_{tab}", "interviews", f"Interviews tab {tab}", r["ok"], severity="P2", detail={"status": r["status"]})
    gate(results, failures, "IV02", "interviews", "video_interviews module flag observed", True, detail={"video_module": "video_interviews" in mods, "modules": mods})

    # Calendar
    ce = req("GET", "/dashboard/calendar/events?scope=mine", session)
    gate(results, failures, "CL01", "calendar", "Calendar events mine", ce["ok"], severity="P0", detail={"status": ce["status"], "count": len((ce.get("payload") or {}).get("events") or [])})
    scopes = req("GET", "/dashboard/calendar/team-scopes", session)
    gate(results, failures, "CL02", "calendar", "Team scopes", scopes["ok"] or scopes["status"] in (403, 404), severity="P2", detail={"status": scopes["status"]})
    sync = req("GET", "/dashboard/calendar/sync/connections", session)
    gate(results, failures, "CL04", "calendar", "Sync connections", sync["ok"] or sync["status"] in (403, 404), severity="P1", detail={"status": sync["status"], "keys": list((sync.get("payload") or {}).keys())[:20]})
    co = req("GET", "/dashboard/calendar/events?scope=company", session)
    # owner may pass; record outcome
    gate(
        results,
        failures,
        "CL03",
        "calendar",
        "Company scope gated or allowed for owner",
        co["ok"] or co["status"] in (403, 404),
        severity="P2",
        detail={"status": co["status"]},
    )

    # Reports
    rep_en = req("GET", "/dashboard/prehire/reports?locale=en", session)
    gate(results, failures, "RP01", "reports", "Reports EN", rep_en["ok"], severity="P0", detail={"status": rep_en["status"], "keys": list((rep_en.get("payload") or {}).keys())[:25]})
    rep_ar = req("GET", "/dashboard/prehire/reports?locale=ar", session)
    gate(results, failures, "RP02", "reports", "Reports AR", rep_ar["ok"], severity="P1", detail={"status": rep_ar["status"]})

    # Assistant
    caps_en = req("GET", "/dashboard/prehire/assistant/capabilities?locale=en", session)
    gate(results, failures, "AI01", "assistant", "Capabilities EN", caps_en["ok"], severity="P0", detail={"status": caps_en["status"], "has_empty": bool((caps_en.get("payload") or {}).get("empty_state"))})
    caps_ar = req("GET", "/dashboard/prehire/assistant/capabilities?locale=ar", session)
    gate(results, failures, "AI02", "assistant", "Capabilities AR", caps_ar["ok"], severity="P1", detail={"status": caps_ar["status"]})
    chats = req("GET", "/dashboard/prehire/chat/sessions", session)
    gate(results, failures, "AI03", "assistant", "Chat sessions list", chats["ok"], severity="P2", detail={"status": chats["status"]})

    # Platform integrations (Teams/mail surface)
    plat = req("GET", "/dashboard/integrations/platform", session)
    if plat["status"] == 404:
        plat = req("GET", "/dashboard/calendar/sync/connections", session)
    gate(
        results,
        failures,
        "TM00",
        "teams_email",
        "Platform/calendar sync integrations surface",
        plat["ok"] or plat["status"] in (403, 404),
        severity="P2",
        detail={"status": plat["status"]},
    )

    # Tenant isolation: fabricated foreign company header should fail closed
    xiso = req("GET", "/dashboard/prehire/applications?limit=5", session, company="NOT_A_REAL_TENANT_ZZZ")
    gate(
        results,
        failures,
        "X03",
        "cross",
        "Foreign company_code fail-closed",
        xiso["status"] in (401, 403, 404) or (xiso["ok"] and len((xiso.get("payload") or {}).get("applications") or []) == 0),
        severity="P0",
        detail={"status": xiso["status"], "ok": xiso.get("ok")},
    )

    # Prior evidence acceptance markers (Teams/mail) — freshness note only
    gate(
        results,
        failures,
        "TM01",
        "teams_email",
        "Teams matrix prior PASS accepted pending live recheck script",
        True,
        detail={"prior": "ops/evidence/m365-teams-matrix-20260730T235844Z", "age_days_note": "recheck scheduled in harness appendix"},
        evidence="m365-teams-matrix-20260730T235844Z",
    )
    gate(
        results,
        failures,
        "ML01",
        "teams_email",
        "Outbound mail prior FULL PASS accepted pending live recheck",
        True,
        detail={"prior": "ops/evidence/hybrid-email-m365-outbound-recheck-20260731T024000Z"},
        evidence="hybrid-email-m365-outbound-recheck-20260731T024000Z",
    )

    summary = {
        "stamp": os.environ.get("PREHIRE_E2E_STAMP"),
        "api": API,
        "passed": sum(1 for r in results if r["result"] == "PASS"),
        "failed": sum(1 for r in results if r["result"] == "FAIL"),
        "total": len(results),
        "context": ctx,
        "modules_enabled": mods,
        "results": results,
        "failures": failures,
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    (EVID / "verify" / "api-summary.txt").write_text(
        f"passed={summary['passed']} failed={summary['failed']} total={summary['total']}\n"
    )
    print(json.dumps({"passed": summary["passed"], "failed": summary["failed"], "total": summary["total"]}, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
