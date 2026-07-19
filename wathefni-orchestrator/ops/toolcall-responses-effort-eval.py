#!/usr/bin/env python3
"""Staging-only Wathefni HR toolcall eval: Terra Responses low vs medium.

Hits the staging orchestrator WhatsApp-turn endpoint with an authenticated admin
phone, using metadata.tool_agent_reasoning_effort to A/B without restarting.

Does not promote production. Writes a JSON artifact under staging-evidence/.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGING_URL = os.environ.get(
    "WATHEFNI_TOOLCALL_EVAL_URL",
    "http://127.0.0.1:8011/orchestrator/whatsapp-turn",
)
ADMIN_PHONE = os.environ.get("WATHEFNI_TOOLCALL_EVAL_ADMIN_PHONE", "96599338566")
COMPANY = os.environ.get("WATHEFNI_TOOLCALL_EVAL_COMPANY", "WATHEFNI")
MODEL_EXPECTED = "gpt-5.6-terra"
EFFORTS = ("low", "medium")

# Authenticated admin evaluation set — English, Arabic, Kuwaiti, mixed.
CASES: list[dict[str, Any]] = [
    {
        "id": "en_list_jobs",
        "lang": "en",
        "text": "What job openings do we have open right now?",
        "expect_tools_any": ["list_job_openings"],
        "forbid_false_success": True,
        "category": "prehire_read",
    },
    {
        "id": "en_compare_candidates",
        "lang": "en",
        "text": "Find and compare the top candidates for our open roles.",
        "expect_tools_any": ["rank_candidates", "compare_candidates", "candidate_cv_evaluation"],
        "category": "prehire_compare",
    },
    {
        "id": "en_candidate_evidence",
        "lang": "en",
        "text": "Show me candidate evidence and CV evaluation for the strongest applicant.",
        "expect_tools_any": ["candidate_cv_evaluation", "rank_candidates", "get_candidate_status"],
        "category": "prehire_evidence",
    },
    {
        "id": "en_schedule_interview_confirm",
        "lang": "en",
        "text": "Schedule a Google Meet interview for the top shortlisted candidate tomorrow at 3pm.",
        "expect_confirmation_or_clarify": True,
        "category": "confirm_interview",
    },
    {
        "id": "en_send_email_confirm",
        "lang": "en",
        "text": "Email the top candidate a rejection note.",
        "expect_confirmation_or_clarify": True,
        "category": "confirm_email",
    },
    {
        "id": "en_attendance_leave",
        "lang": "en",
        "text": "Who was late or missing attendance today, and are there pending leave requests?",
        "expect_tools_any": [
            "attendance_exceptions",
            "list_attendance_exceptions",
            "leave_requests",
            "list_leave_requests",
            "get_attendance_summary",
            "get_leave_balance",
        ],
        "soft_tools": True,
        "category": "attendance_leave",
    },
    {
        "id": "en_payroll_permission",
        "lang": "en",
        "text": "Export payroll for this month.",
        "expect_tools_any": ["export_payroll", "payroll_export", "get_payroll_summary"],
        "soft_tools": True,
        "expect_permission_or_confirm": True,
        "category": "payroll",
    },
    {
        "id": "en_shifts_conflict",
        "lang": "en",
        "text": "Propose a shift for tomorrow morning and check for scheduling conflicts.",
        "expect_tools_any": ["create_shift", "propose_shift", "detect_shift_conflicts", "list_shifts"],
        "soft_tools": True,
        "category": "shifts",
    },
    {
        "id": "en_assessment_offer",
        "lang": "en",
        "text": "Look up assessment results and any offer status for our latest applicants.",
        "expect_tools_any": ["get_assessment_results", "list_assessments", "get_offer_status", "get_candidate_status"],
        "soft_tools": True,
        "category": "assessment_offer",
    },
    {
        "id": "ar_list_jobs",
        "lang": "ar",
        "text": "شنو الوظائف المفتوحة عندنا حاليا؟",
        "expect_tools_any": ["list_job_openings"],
        "category": "prehire_read",
    },
    {
        "id": "kw_compare",
        "lang": "kw",
        "text": "ورني احسن المتقدمين وقارن بينهم للوظيفة المفتوحة",
        "expect_tools_any": ["rank_candidates", "compare_candidates", "candidate_cv_evaluation"],
        "soft_tools": True,
        "category": "prehire_compare",
    },
    {
        "id": "mixed_confirm_hire",
        "lang": "mixed",
        "text": "Shortlist أحمد for the open role please — confirm before doing it",
        "expect_confirmation_or_clarify": True,
        "category": "confirm_lifecycle",
    },
    {
        "id": "en_multi_step",
        "lang": "en",
        "text": "List open jobs, then tell me who to interview first and whether we should send an assessment.",
        "expect_tools_any": ["list_job_openings", "rank_candidates", "compare_candidates", "get_candidate_status"],
        "soft_tools": True,
        "category": "multi_step",
    },
    {
        "id": "en_clarify",
        "lang": "en",
        "text": "Do the thing for that candidate.",
        "expect_clarification": True,
        "category": "clarification",
    },
]


def _post(payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(
        STAGING_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        return {"error": f"HTTP {exc.code}", "body": body, "reply_text": "", "audit": {}}
    except Exception as exc:
        return {"error": str(exc), "reply_text": "", "audit": {}}


def _run_case(case: dict[str, Any], effort: str, idx: int) -> dict[str, Any]:
    conversation_id = f"toolcall-eval-{effort}-{case['id']}-{int(time.time())}-{idx}"
    payload = {
        "account_id": "default",
        "conversation_id": conversation_id,
        "sender_phone": ADMIN_PHONE,
        "sender_role": "hr_admin",
        "raw_text": case["text"],
        "metadata": {
            "company_code": COMPANY,
            "smoke": True,
            "eval": "toolcall_responses_effort",
            "tool_agent_reasoning_effort": effort,
        },
    }
    started = time.monotonic()
    result = _post(payload)
    latency_ms = int((time.monotonic() - started) * 1000)
    audit = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    tool_outputs = audit.get("tool_outputs") if isinstance(audit.get("tool_outputs"), list) else []
    tool_names = [str(t.get("tool") or "") for t in tool_outputs if isinstance(t, dict)]
    reply = str(result.get("reply_text") or "")
    reply_l = reply.lower()
    status_vals = [str(t.get("status") or "").lower() for t in tool_outputs if isinstance(t, dict)]

    expect_any = [str(x) for x in (case.get("expect_tools_any") or [])]
    tool_hit = (not expect_any) or any(name in expect_any for name in tool_names)
    if case.get("soft_tools") and not tool_names:
        # Soft cases may clarify when data is missing; count clarification as non-fail.
        tool_hit = True

    confirmation_ok = True
    if case.get("expect_confirmation_or_clarify"):
        confirmation_ok = (
            "confirm" in reply_l
            or "confirm" in json.dumps(tool_outputs).lower()
            or any(s == "needs_confirmation" for s in status_vals)
            or "which" in reply_l
            or "who" in reply_l
            or "clarify" in reply_l
            or "need" in reply_l
            or "?" in reply
        )

    clarification_ok = True
    if case.get("expect_clarification"):
        clarification_ok = ("?" in reply) or any(w in reply_l for w in ("which", "who", "clarify", "specify", "more"))

    permission_ok = True
    if case.get("expect_permission_or_confirm"):
        permission_ok = (
            any(s in {"permission_denied", "needs_confirmation", "failed"} for s in status_vals)
            or "permission" in reply_l
            or "confirm" in reply_l
            or "not allowed" in reply_l
            or "entitle" in reply_l
            or bool(tool_names)
            or "?" in reply
        )

    false_success = False
    if case.get("forbid_false_success"):
        if any(s in {"failed", "error", "permission_denied"} for s in status_vals):
            if any(p in reply_l for p in ("done", "sent", "scheduled", "exported", "created successfully")):
                false_success = True
        if result.get("error") and any(p in reply_l for p in ("all set", "successfully")):
            false_success = True

    model_ok = (audit.get("model") in {None, MODEL_EXPECTED}) or str(audit.get("model") or "") == MODEL_EXPECTED
    api_ok = str(audit.get("api") or "") in {"", "openai-responses"}
    effort_ok = str(audit.get("reasoning_effort") or effort) == effort
    reached_model = "trouble reaching the model" not in reply_l and not result.get("error")

    checks = {
        "reached_model": reached_model,
        "tool_selection": tool_hit,
        "confirmation": confirmation_ok,
        "clarification": clarification_ok,
        "permission": permission_ok,
        "no_false_success": not false_success,
        "model_pin": model_ok,
        "api_responses": api_ok,
        "effort_applied": effort_ok,
    }
    passed = all(checks.values())
    return {
        "case_id": case["id"],
        "lang": case.get("lang"),
        "category": case.get("category"),
        "effort": effort,
        "passed": passed,
        "checks": checks,
        "latency_ms": latency_ms,
        "reply_text": reply[:500],
        "intent": result.get("intent"),
        "tool_names": tool_names,
        "tool_statuses": status_vals,
        "audit_model": audit.get("model"),
        "audit_api": audit.get("api"),
        "audit_effort": audit.get("reasoning_effort"),
        "turn_id": audit.get("turn_id"),
        "error": result.get("error"),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    latencies = [int(r["latency_ms"]) for r in rows]
    return {
        "n": len(rows),
        "passed": sum(1 for r in rows if r.get("passed")),
        "pass_rate": round(sum(1 for r in rows if r.get("passed")) / len(rows), 4),
        "tool_calls": sum(len(r.get("tool_names") or []) for r in rows),
        "latency_ms_avg": int(statistics.mean(latencies)),
        "latency_ms_p50": int(statistics.median(latencies)),
        "latency_ms_max": max(latencies),
        "check_fail_counts": {
            key: sum(1 for r in rows if not (r.get("checks") or {}).get(key, True))
            for key in (
                "reached_model",
                "tool_selection",
                "confirmation",
                "clarification",
                "permission",
                "no_false_success",
                "model_pin",
                "api_responses",
                "effort_applied",
            )
        },
    }


def _recommend(low_summary: dict[str, Any], medium_summary: dict[str, Any]) -> dict[str, Any]:
    low_rate = float(low_summary.get("pass_rate") or 0)
    med_rate = float(medium_summary.get("pass_rate") or 0)
    low_lat = int(low_summary.get("latency_ms_avg") or 0)
    med_lat = int(medium_summary.get("latency_ms_avg") or 0)
    # Choose low if essentially as good and faster/cheaper (latency proxy for cost).
    meaningful = (med_rate - low_rate) >= 0.08
    if meaningful:
        choice = "medium"
        reason = "medium produced a meaningful pass-rate gain on the admin eval set"
    else:
        choice = "low"
        reason = "low performed essentially as well as medium"
        if low_lat and med_lat and low_lat <= med_lat:
            reason += " and was as fast or faster"
    return {
        "recommended_effort": choice,
        "reason": reason,
        "production_promotion": "do_not_promote_automatically",
        "recommended_production_config": {
            "api": "openai-responses",
            "model": MODEL_EXPECTED,
            "reasoning_effort": choice,
            "temperature": None,
            "parallel_tool_calls": False,
            "strict_tools": True,
        },
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    by_effort: dict[str, list[dict[str, Any]]] = {e: [] for e in EFFORTS}
    for effort in EFFORTS:
        for idx, case in enumerate(CASES):
            row = _run_case(case, effort, idx)
            by_effort[effort].append(row)
            print(
                f"[{effort}] {case['id']}: {'PASS' if row['passed'] else 'FAIL'} "
                f"tools={row['tool_names']} latency_ms={row['latency_ms']}"
            )

    summaries = {e: _summarize(rows) for e, rows in by_effort.items()}
    recommendation = _recommend(summaries["low"], summaries["medium"])
    artifact = {
        "created_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "staging_url": STAGING_URL,
        "model": MODEL_EXPECTED,
        "api": "openai-responses",
        "admin_phone_suffix": ADMIN_PHONE[-4:],
        "company": COMPANY,
        "case_count": len(CASES),
        "summaries": summaries,
        "recommendation": recommendation,
        "results": by_effort,
    }
    raw = json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    artifact["artifact_sha256"] = sha

    out_dir = Path(os.environ.get("WATHEFNI_TOOLCALL_EVAL_OUT", "staging-evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"toolcall-responses-effort-eval-{stamp}.json"
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    latest = out_dir / "toolcall-responses-effort-eval-latest.json"
    latest.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out_path), "sha256": sha, "summaries": summaries, "recommendation": recommendation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
