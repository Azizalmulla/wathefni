#!/usr/bin/env python3
"""Production proof for Wathefni Assistant grounded HR operating copilot."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ORCH = Path(os.environ.get("WATHEFNI_ORCH", "/opt/wathefni/orchestrator"))
sys.path.insert(0, str(ORCH))
os.chdir(ORCH)

checks: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(json.dumps({"check": name, "ok": bool(ok), "detail": detail}, ensure_ascii=False))


def main() -> int:
    import action_registry as registry
    import assistant_capability_catalog as caps
    import assistant_policy as policy
    import tool_call_orchestrator as orch

    names = set(registry.REGISTRY.keys())
    for required in (
        "execute_candidate_workflow",
        "schedule_interview",
        "reschedule_interview",
        "cancel_interview",
        "send_email",
        "notify_candidate",
        "send_assessment",
        "get_reports_metrics",
        "rank_candidates",
        "list_job_openings",
    ):
        check(f"tool_registered:{required}", required in names)

    src = Path(orch.__file__).read_text(encoding="utf-8")
    check("copilot_prompt", "grounded HR operating copilot" in src)
    check("no_whatsapp_identity", "speaking to a company HR admin on WhatsApp" not in src)
    check("no_raw_cv_text_in_prompt", "cv_text, ranking_score" not in src)
    check("policy_wired", "_policy_short_circuit" in src and "capability_catalog" in src)
    check("progress_emit", "_emit_progress" in src and "_cancel_requested" in src)

    app_src = (ORCH / "app.py").read_text(encoding="utf-8")
    check("no_wording_nav", 'if "ranking" in text or "rank" in text' not in app_src)
    check("grounded_nav_comment", "Navigation must come from grounded tool/policy results only" in app_src)
    check("workflow_card_artifacts", "workflow_card" in app_src)
    check("progress_stream", '"type": "progress"' in app_src or "on_progress" in app_src)
    check("no_fake_token_sleep", "time_module.sleep(0.012)" not in app_src)

    # Live capability matrix for WATHEFNI if DB available
    try:
        import app as legacy

        company = "WATHEFNI"
        tools = registry.build_tool_schemas(legacy, type("R", (), {"metadata": {"company_code": company, "permissions": ["prehire.read", "candidate.manage", "interview.manage", "jobs.read", "assessment.manage"]}})())
        # Filter visible roughly
        catalog = caps.build_assistant_capability_catalog(
            legacy=legacy,
            company_code=company,
            permissions=["prehire.read", "candidate.manage", "interview.manage", "jobs.read", "assessment.manage", "jobs.read"],
            visible_tools=tools,
        )
        check("live_catalog_built", isinstance(catalog.get("capabilities"), dict), detail=str(catalog.get("offerable", [])[:12]))
        check("reports_offerable_or_denied", catalog["capabilities"]["reports"]["status"] in {caps.STATUS_AVAILABLE, caps.STATUS_DENIED})
        check("teams_not_invented_as_available_without_provider", catalog["capabilities"]["teams_meet"]["status"] != caps.STATUS_AVAILABLE or catalog["providers"].get("microsoft_calendar"))
    except Exception as exc:
        check("live_catalog_built", False, detail=str(exc)[:200])

    check("reports_policy_classifier", policy.is_reports_metric_question("time to hire this month"))
    check("overview_policy_classifier", policy.is_overview_operational_question("what should I work on today"))

    # Workflow card fields present on plan helper
    check("workflow_plan_has_card_fn", hasattr(registry, "_candidate_workflow_plan"))
    check("workflow_executor_partial_message", "not claiming the whole workflow succeeded" in Path(registry.__file__).read_text(encoding="utf-8"))

    dash = Path("/var/www/wathefni-dashboard/assets")
    admin_js = list(dash.glob("AdminAIPage-*.js"))
    check("dashboard_admin_ai_asset", bool(admin_js), detail=admin_js[0].name if admin_js else "")
    if admin_js:
        text = admin_js[0].read_text(errors="ignore")
        check("asset_rtl", "rtl" in text)
        check("asset_profiler", "assistant:" in text or "Profiler" in text)
        check("asset_workflow", "workflow" in text.lower())

    passed = sum(1 for c in checks if c["ok"])
    failed = [c for c in checks if not c["ok"]]
    summary = {
        "verdict": "PASS" if not failed else "FAIL",
        "passed": passed,
        "failed": len(failed),
        "failures": failed,
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
