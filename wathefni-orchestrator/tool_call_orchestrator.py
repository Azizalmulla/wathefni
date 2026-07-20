"""Tool-using orchestrator for Wathefni HR/admin chat.

Uses the OpenAI Responses API (/v1/responses) with gpt-5.6-terra by default.
The model may plan and request tools; the backend remains authoritative for
tenant identity, permissions, confirmations, state transitions, payroll,
candidate lifecycle, shifts, delivery, and employee data.

Per turn the model receives:
- the user's message
- conversation history
- a structured state_summary (last action result, current focus, pending confirmations)
- the canonical action registry as strict Responses tool schemas

The model may:
- reply directly (when state has the answer)
- call tools (sequentially; parallel_tool_calls=false)
- ask a clarifying question
- ask the user to confirm a sensitive action (then re-call on the next turn)

Hidden reasoning content is never exposed in user replies or telemetry payloads.
"""

from __future__ import annotations

import importlib
import hashlib
import json
import os
import re
import sys
import time as time_module
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import action_registry as _registry
from module_catalog import TOOLCALL_GATED_MODULES


TOOLCALL_GRAPH_VERSION = "wathefni_hr_toolcall_v2_responses"
TOOLCALL_STATE_SCOPE = "toolcall_dialog_state"
MAX_TOOL_LOOPS = 4
MAX_HISTORY_MESSAGES = 10
CANDIDATE_SUMMARY_LIMIT = 5
ACTIVE_SESSION_TTL_MINUTES = int(os.environ.get("WATHEFNI_TOOLCALL_SESSION_TTL_MINUTES", "20") or "20")
DEFAULT_TOOLCALL_REASONING_EFFORT = "low"
ALLOWED_TOOLCALL_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
TOOLCALL_LLM_TIMEOUT_SEC = int(os.environ.get("WATHEFNI_TOOLCALL_LLM_TIMEOUT_SEC", "45") or "45")
TOOLCALL_LLM_RETRIES = max(0, int(os.environ.get("WATHEFNI_TOOLCALL_LLM_RETRIES", "1") or "1"))
TOOLCALL_TURN_BUDGET_SEC = int(os.environ.get("WATHEFNI_TOOLCALL_TURN_BUDGET_SEC", "90") or "90")
TOOLCALL_MODULE = "pre_hiring"
TOOLCALL_CHANNEL = "whatsapp"
WEB_DASHBOARD_CHANNEL = "web_dashboard"
TERMINAL_FAILURE_STATUSES = {"candidate_not_found", "failed", "error", "needs_clarification", "needs_candidate_reference"}
CASUAL_SESSION_RESET_RE = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|hala|salam|salaam|good\s+(morning|afternoon|evening)|"
    r"how\s+(are|r)\s+(you|u)|good\s*(wbu|and\s+you|\?)?|all\s+good|شلونك|هلا|مرحبا)\s*[!.?؟]*\s*$",
    re.IGNORECASE,
)
OPERATIONAL_HINT_RE = re.compile(
    r"\b(candidate|candidates|employee|payroll|shift|leave|attendance|hire|reject|shortlist|email|schedule|interview|cv|assessment|salary|timesheet)\b",
    re.IGNORECASE,
)
WORKFLOW_TRIGGER_RE = re.compile(
    r"\b(shortlist|hire|reject|email|notify|whatsapp|assessment|screening|questions|schedule|interview|meeting|meet|calendar|invite)\b",
    re.IGNORECASE,
)
BATCH_TRIGGER_RE = re.compile(
    r"\b(all|top\s+\d+|\d+\s+(candidates|applicants)|candidates|applicants|both|each|everyone|them)\b.*\b(send|notify|shortlist|email|assessment|screening|video|interview|invite|link)\b|"
    r"\b(send|notify|shortlist|email|assessment|screening|video|interview|invite|link)\b.*\b(all|top\s+\d+|\d+\s+(candidates|applicants)|candidates|applicants|both|each|everyone|them)\b",
    re.IGNORECASE,
)
MIXED_BATCH_TRIGGER_RE = re.compile(
    r"\b(shortlist|hire|reject|send|notify|email|assessment|screening|video|interview|invite|link)\b[\s\S]{0,80}\b(and|,|then|و)\b[\s\S]{0,80}\b(shortlist|hire|reject|send|notify|email|assessment|screening|video|interview|invite|link)\b",
    re.IGNORECASE,
)
INVITE_STATUS_RE = re.compile(
    r"\b(did|have|has|was|is)\b.*\b(notify|notified|invite|invited|email|emailed)\b|\b(did|have|has)\b.*\bsend\b.*\b(invite|email|link)\b|\b(did\s+u\s+notify|did\s+you\s+notify)\b",
    re.IGNORECASE,
)
JOB_OPENING_TRIGGER_RE = re.compile(
    r"\b(create|publish|add|new)\b.*\b(job|position|opening|role|vacancy|qr|qr code)\b|"
    r"\bopen\s+(a|an|the|new)\b.*\b(job|position|opening|role|vacancy)\b|"
    r"\b(qr|qr code)\b.*\b(job|position|opening|role|apply)\b",
    re.IGNORECASE,
)
LIST_JOB_OPENINGS_RE = re.compile(
    r"\b(what|which|show|list|any|have|do we|we have|available|current|how many|count|number of)\b.*\b(job|jobs|opening|openings|position|positions|role|roles|vacanc(?:y|ies))\b|"
    r"\b(job|jobs|opening|openings|position|positions)\b.*\b(open|available|active|current)\b|"
    r"\bopen\s+(jobs?|openings?|positions?|roles?)\b",
    re.IGNORECASE,
)
APPROVAL_RE = re.compile(r"^\s*(yes|yeah|yep|ok|okay|go ahead|confirm|approved|do it|sure|نعم|اي|إي|تمام)\b", re.IGNORECASE)
REJECTION_RE = re.compile(r"^\s*(no|nah|cancel|stop|don't|dont|لا|لأ)\b", re.IGNORECASE)

TOOL_PERMISSION_MAP = {
    "rank_candidates": "prehire.read",
    "candidate_cv_evaluation": "prehire.read",
    "compare_candidates": "prehire.read",
    "get_candidate_status": "prehire.read",
    "get_interview_invite_status": "prehire.read",
    "list_job_openings": "prehire.read",
    "search_job_openings": "prehire.read",
    "create_job_opening": "settings.manage",
    "close_job_opening": "settings.manage",
    "reopen_job_opening": "settings.manage",
    "execute_mixed_candidate_batch": "candidate.manage",
    "execute_candidate_batch": "candidate.manage",
    "execute_candidate_workflow": "candidate.manage",
    "shortlist_candidate": "candidate.manage",
    "reject_candidate": "candidate.decide",
    "send_email": "candidate.manage",
    "notify_candidate": "candidate.manage",
    "send_screening_questions": "candidate.manage",
    "hire_candidate": "candidate.decide",
    "schedule_interview": "interview.manage",
    "send_interview_invite": "interview.manage",
    "send_video_interview": "interview.manage",
    "send_assessment": "assessment.manage",
    "list_leave_requests": "leave.read",
    "request_leave": "leave.request",
    "approve_leave_request": "leave.decide",
    "reject_leave_request": "leave.decide",
    "cancel_leave_request": "leave.decide",
    # Attendance
    "list_attendance": "attendance.read",
    "check_in_employee": "attendance.manage",
    "check_out_employee": "attendance.manage",
    "mark_attendance_absent": "attendance.manage",
    "correct_attendance_record": "attendance.manage",
    # Shifts
    "list_shifts": "shifts.read",
    "list_availability": "shifts.read",
    "list_shift_swaps": "shifts.read",
    "create_shift_assignment": "shifts.manage",
    "cancel_shift_assignment": "shifts.manage",
    "replace_conflicting_shift_assignment": "shifts.manage",
    "request_availability": "shifts.manage",
    "request_shift_swap": "shifts.manage",
    "approve_shift_swap": "shifts.manage",
    "reject_shift_swap": "shifts.manage",
    # Onboarding
    "list_onboarding_status": "onboarding.read",
    "send_onboarding_reminder": "onboarding.manage",
    "start_onboarding": "onboarding.manage",
    "onboarding_mark_item": "onboarding.manage",
    # Compliance
    "list_compliance_documents": "compliance.read",
    "compliance_send_reminder": "compliance.manage",
    "compliance_mark_reviewed": "compliance.manage",
    # Payroll (sensitive money domain; export is separately gated)
    "list_payroll_hours": "payroll.read",
    "list_timesheets": "payroll.read",
    "show_payroll_policy": "payroll.read",
    "preview_payroll": "payroll.read",
    "list_payroll_exports": "payroll.read",
    "create_timesheet_review": "payroll.manage",
    "approve_timesheet": "payroll.manage",
    "reject_timesheet": "payroll.manage",
    "set_payroll_policy": "payroll.manage",
    "export_payroll": "payroll.export",
    # Analytics
    "workforce_analytics": "analytics.read",
}


# Modules exposed through the tool-call surface in addition to the core
# pre-hiring set. Tools in these modules are filtered out of the catalog the
# model sees unless the company has the module enabled AND the user holds the
# tool's permission. This is the "careful unlock": the registry is the single
# source of truth, but post-hire tools never reach a non-entitled company.
# Execution is still independently gated by _require_tool_entitlements.
TOOLCALL_SYSTEM = """
You are Wathefni HR, a smart, opinionated HR colleague speaking to a company HR admin on WhatsApp. You operate on real candidate and employee data through tools the orchestrator exposes to you.

On every turn you receive:
- the user's latest message
- the recent conversation_history
- a structured state_summary (last action result, candidates list, current focus, any pending confirmations)
- a tool catalog with descriptions, parameter schemas, and parameter enums

How to decide:
1. If the answer is already present in state_summary or conversation_history (for example: the user asked "who are they" right after a candidate ranking, or "is he shortlisted" about the candidate you just discussed), answer directly with no tool call.
2. If you need fresh data or to mutate state, call exactly one tool. Pick the smallest tool that solves the request.
3. If you genuinely do not have enough information, ask one short clarifying question. Do not loop on the same clarification.
4. For SENSITIVE atomic tools (descriptions say SENSITIVE), never call on the first mention. Ask the user to confirm naturally in your own words. On the next turn, when the user agrees, call the tool with the same arguments.
5. For PREFLIGHT-THEN-CONFIRM workflow/batch tools, call the tool immediately to preflight. The backend will not execute mutations during preflight; it will return missing fields, blocked steps, fallback options, candidate previews, or a single confirmation request.

Replying directly (no tool call):
- For candidate evaluations, ground every judgment in candidate_context fields: cv_text, ranking_score, strengths, gaps, prior_turn_ranking. Speak like a senior recruiter, do NOT paste or list the CV. At most 2-3 concrete facts.
- For follow-ups like "who are they", "show me", "list them", read state_summary.last_action_result.candidates and just answer.
- For status questions, lead with the status in one sentence.
- Language policy is based on the user's CURRENT message only:
  * If the current message is English or Arabizi written in Latin characters ("yo", "hi", "good wbu", "shlonk"), reply only in Latin characters. Do NOT switch into Arabic script.
  * If the current message is Arabic script, reply in Arabic script.
  * If the current message code-switches, you may code-switch at the same level.
  * Do not infer reply language from WhatsApp profile name, company locale, phone country, or older conversation history.
- Match the user's register, but keep the script/language stable.
- Keep replies WhatsApp-short. Evaluations 2-4 sentences max, status 1-2.
- Never repeat your last 2-3 phrasings.

Calling a tool:
- Use parameter values from the tool's catalog enums when the user's wording matches one. If it does not match confidently, omit the parameter and put the user's wording in `query`. Never invent values that are not in the enum.
- For candidate tools, pass candidate_name (and candidate_app_key if you already know it). The orchestrator resolves the rest.
- For mixed candidate/action requests ("shortlist Foad, send assessment to Sara, send video interview to Ali"), call execute_mixed_candidate_batch with one mixed_items object per candidate/action pair.
- For plural/batch candidate mutations where all candidates get the same action ("top 5", "all these candidates", "send to Foad and Sara"), call execute_candidate_batch, not atomic tools. The backend previews exact candidates and asks for confirmation.
- For multi-step candidate operations (shortlist + email, shortlist + schedule interview, schedule + notify, video interview link, assessment + notify), call execute_candidate_workflow once immediately. Do NOT ask a generic confirmation yourself first. Do NOT call multiple sensitive tools separately for one user request.
- For "did you notify/invite/email him?" after an interview, call get_interview_invite_status. Do not start a new notification unless the user explicitly asks you to send/resend.
- For listing/reading open jobs or positions ("what jobs are open", "how many openings", "list positions"), call list_job_openings. Do NOT pass search/query text. Do NOT use rank_candidates for job-opening inventory.
- For finding a named role/title ("Finance", "IT Manager"), call search_job_openings with that search term only.
- For job opening / position creation / QR-code requests, call create_job_opening immediately for backend preflight. Do NOT say job openings are unsupported.
- For closing/pausing/stopping a job posting, use close_job_opening. For reopening/resuming a closed one, use reopen_job_opening (do not use create_job_opening for this — it would ask for salary again unnecessarily). Both are PREFLIGHT-THEN-CONFIRM: identify the exact job by title or APPLY code, then confirm before executing.
- For employee leave requests (only when the leave tools are present in your catalog): use list_leave_requests to read leave ("show pending leave", "who is off next week"); request_leave to file a new request for an employee with their dates; approve_leave_request / reject_leave_request / cancel_leave_request for decisions. The decision tools are PREFLIGHT-THEN-CONFIRM: call the tool to let the backend identify the exact request and flag shift conflicts, then ask the user for one explicit confirmation before it executes. Identify a request by employee name/phone + dates, or by leave_id from prior state.
- For post-hire operations, only use a tool when it is present in your catalog (it is hidden if the company has not enabled that module or you lack permission):
  * Attendance: list_attendance to read ("who was late today"); check_in_employee / check_out_employee to clock an employee in/out. mark_attendance_absent and correct_attendance_record are SENSITIVE — confirm in your own words first.
  * Shifts: list_shifts / list_availability / list_shift_swaps to read; create_shift_assignment to schedule (SENSITIVE — confirm first); request_availability / request_shift_swap to ask employees. cancel_shift_assignment, replace_conflicting_shift_assignment, approve_shift_swap, reject_shift_swap are SENSITIVE — confirm first.
  * Onboarding: send_onboarding_reminder to nudge a new hire about onboarding.
  * Compliance: compliance_send_reminder to nudge an employee about a missing/expiring/expired document (name a document_type to target one, or omit it for all outstanding); compliance_mark_reviewed to clear the 'needs review' flag once HR has checked a document (needs the employee + document_type).
  * Payroll: list_payroll_hours / list_timesheets / show_payroll_policy / preview_payroll / list_payroll_exports to read; create_timesheet_review to open a review. approve_timesheet, reject_timesheet, set_payroll_policy are SENSITIVE money actions and export_payroll is the most sensitive — always confirm the exact target/period in your own words before calling, and never call export_payroll on first mention.
  * Analytics: workforce_analytics to answer headcount/attendance/overtime/turnover questions.
- Identify an employee by name or phone; identify a specific shift/swap/timesheet by its id from prior state when you have it.
- Do not call the same tool repeatedly in one turn.

When a tool returns one of these special statuses, respond like this:
- candidate_not_found: tell the user plainly that no candidate by that name/email exists in the database. Do NOT ask them to spell it differently or send more identifiers. If they insist, ask whether they want to add the candidate or whether the spelling is different — but only after acknowledging it isn't in our records.
- candidate_ambiguous: list the matches in plain language (name + position + status) and ask which one they mean. Do not pick.
- needs_candidate_reference: you have not been told which candidate. Ask once for a name.
- needs_confirmation: this is the only path for sensitive tools. Ask the user to confirm in your own words and wait for them to agree before re-calling the tool.
- needs_clarification: the user's request is incomplete; ask one targeted question.
- For execute_candidate_batch preflight: summarize the exact candidate list and action, then ask for one explicit confirmation. Do not execute until confirmed.
- For execute_mixed_candidate_batch preflight: summarize each candidate/action pair, then ask for one explicit confirmation. Do not execute until confirmed.
- For execute_candidate_workflow preflight failures: if missing_fields includes datetime_text, ask for the meeting date/time. If blocked_steps says candidate_email_missing, tell the user the candidate has no email and ask whether to use WhatsApp instead. Do not ask generic confirmation until the workflow is ready.

Never expose JSON, tool names, parameter names, or system internals to the user. Speak like a person.
""".strip()


def _legacy() -> Any:
    return sys.modules.get("app") or importlib.import_module("app")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    return _legacy().json_safe(value)


def _parse_iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _session_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=max(1, ACTIVE_SESSION_TTL_MINUTES))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _module_for_request(request: Any) -> str:
    # Tool-call orchestrator is currently enabled only for pre-hiring tools.
    # Future modules should be selected here before any context is loaded.
    return TOOLCALL_MODULE


def _channel_for_request(request: Any) -> str:
    metadata = getattr(request, "metadata", None)
    if isinstance(metadata, dict):
        channel = str(metadata.get("channel") or "").strip()
        if channel:
            return channel
    return TOOLCALL_CHANNEL


def _base_memory_scope(request: Any) -> dict[str, Any]:
    """Build toolcall memory scope with the same authority markers as dashboard chat.

    WhatsApp HR and dashboard Pre-Hiring Assistant share handle_toolcall_whatsapp_turn.
    Dashboard injects access/permissions/admin_user; WhatsApp must hydrate the same
    permission_authority=backend_current subject markers from the linked actor or the
    entitlement gate fail-closes even when permissions are listed.

    Critical invariant: admin_user_id must equal permission_subject_user_id whenever
    authority is backend_current. Dashboard sessions identify actors by user_id UUID;
    phone digits must never become admin_user_id in that path or require_entitlement
    sees an empty grant set and returns a false permission_denied.
    """
    legacy = _legacy()
    company_id = None
    if hasattr(legacy, "request_company_code"):
        try:
            company_id = legacy.request_company_code(request)
        except Exception:
            company_id = None
    metadata = getattr(request, "metadata", None) if isinstance(getattr(request, "metadata", None), dict) else {}
    access = metadata.get("access") if isinstance(metadata.get("access"), dict) else {}
    access_user = access.get("user") if isinstance(access.get("user"), dict) else {}
    channel = _channel_for_request(request)
    dashboard_channel = channel == WEB_DASHBOARD_CHANNEL or bool(metadata.get("dashboard"))
    permissions = (
        metadata.get("permissions")
        if isinstance(metadata.get("permissions"), list)
        else access.get("permissions") if isinstance(access.get("permissions"), list) else []
    )
    actor_context = None
    if hasattr(legacy, "whatsapp_actor_context_for_phone"):
        try:
            actor_context = legacy.whatsapp_actor_context_for_phone(getattr(request, "sender_phone", None), company_id)
        except Exception:
            actor_context = None
    # Dashboard metadata is the session authority. Do not let a WhatsApp phone link
    # overwrite dashboard permissions/role/user id (phone may be empty/"dashboard"
    # or resolve to a different linked actor than the signed-in user).
    if isinstance(actor_context, dict) and not dashboard_channel:
        if isinstance(actor_context.get("permissions"), list):
            permissions = actor_context.get("permissions") or []
        if actor_context.get("company_code") and not company_id:
            company_id = actor_context.get("company_code")
    permissions = sorted({str(item) for item in permissions if str(item).strip()})
    admin_meta = metadata.get("admin_user") if isinstance(metadata.get("admin_user"), dict) else {}
    hr_meta = metadata.get("hr_user") if isinstance(metadata.get("hr_user"), dict) else {}
    admin_user_from_dashboard = str(
        admin_meta.get("user_id")
        or hr_meta.get("user_id")
        or access.get("permission_subject_user_id")
        or access_user.get("user_id")
        or ""
    ).strip()
    phone_digits = legacy.digits(getattr(request, "sender_phone", None)) or ""
    if dashboard_channel:
        role_scope = str(
            access.get("role")
            or admin_meta.get("role")
            or hr_meta.get("role")
            or (actor_context or {}).get("actor_role")
            or getattr(request, "sender_role", None)
            or "hr_admin"
        )
        admin_user_id = str(
            admin_user_from_dashboard
            or (actor_context or {}).get("actor_user_id")
            or phone_digits
            or "unknown_admin"
        )
        authority = str(
            access.get("permission_authority")
            or metadata.get("permission_authority")
            or (actor_context or {}).get("permission_authority")
            or ""
        ).strip()
        subject_user_id = str(
            access.get("permission_subject_user_id")
            or admin_user_from_dashboard
            or (actor_context or {}).get("permission_subject_user_id")
            or (actor_context or {}).get("actor_user_id")
            or ""
        ).strip()
        subject_company = str(
            access.get("permission_subject_company")
            or (actor_context or {}).get("permission_subject_company")
            or (actor_context or {}).get("company_code")
            or company_id
            or ""
        ).strip().upper()
        actor_email = str(admin_meta.get("email") or access_user.get("email") or (actor_context or {}).get("actor_email") or "")
    else:
        role_scope = str(
            (actor_context or {}).get("actor_role")
            or access.get("role")
            or getattr(request, "sender_role", None)
            or "hr_admin"
        )
        admin_user_id = str(
            (actor_context or {}).get("actor_user_id")
            or phone_digits
            or "unknown_admin"
        )
        authority = str(
            (actor_context or {}).get("permission_authority")
            or access.get("permission_authority")
            or metadata.get("permission_authority")
            or ""
        ).strip()
        subject_user_id = str(
            (actor_context or {}).get("permission_subject_user_id")
            or access.get("permission_subject_user_id")
            or (actor_context or {}).get("actor_user_id")
            or ""
        ).strip()
        subject_company = str(
            (actor_context or {}).get("permission_subject_company")
            or access.get("permission_subject_company")
            or (actor_context or {}).get("company_code")
            or company_id
            or ""
        ).strip().upper()
        actor_email = str((actor_context or {}).get("actor_email") or "")
    company_key = str(company_id or getattr(request, "account_id", None) or "default").strip().upper() or "default"
    if not subject_company:
        subject_company = company_key
    # Only advertise backend_current when a trusted linked actor (or dashboard access) provided it.
    if authority != "backend_current":
        authority = ""
        subject_user_id = ""
        subject_company = ""
    elif not subject_user_id:
        subject_user_id = admin_user_id if admin_user_id != "unknown_admin" else ""
        if not subject_user_id:
            authority = ""
            subject_company = ""
    # Keep actor id aligned with subject when authority is trusted.
    if authority == "backend_current" and subject_user_id:
        admin_user_id = subject_user_id

    hr_user = None
    if isinstance(metadata.get("admin_user"), dict):
        hr_user = metadata.get("admin_user")
    elif isinstance(metadata.get("hr_user"), dict):
        hr_user = metadata.get("hr_user")
    elif isinstance(actor_context, dict) and actor_context.get("actor_user_id") and authority == "backend_current":
        hr_user = {
            "user_id": actor_context.get("actor_user_id"),
            "email": actor_context.get("actor_email") or "",
            "phone": actor_context.get("actor_phone") or legacy.digits(getattr(request, "sender_phone", None)) or "",
            "role": actor_context.get("actor_role") or role_scope,
            "company_code": subject_company or company_key,
            "status": actor_context.get("status") or "active",
            "permissions": permissions,
        }

    return {
        "company_id": company_key,
        "account_id": getattr(request, "account_id", None) or "default",
        "admin_user_id": admin_user_id,
        "actor_email": actor_email,
        "conversation_id": getattr(request, "conversation_id", None) or "no_conversation",
        "channel": channel,
        "module": _module_for_request(request),
        "role_scope": role_scope,
        "permissions": permissions,
        "permission_authority": authority,
        "permission_subject_user_id": subject_user_id,
        "permission_subject_company": subject_company,
        "hr_user": hr_user,
        "access": {
            "role": role_scope,
            "permissions": permissions,
            "permission_authority": authority,
            "permission_subject_user_id": subject_user_id,
            "permission_subject_company": subject_company,
        },
    }


def _permission_denied(tool_name: str, required_permission: str, scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "permission_denied",
        "tool": tool_name,
        "required_permission": required_permission,
        "message": "You do not have permission to do this action.",
        "company_id": scope.get("company_id"),
        "role_scope": scope.get("role_scope"),
    }


def _module_disabled(tool_name: str, module_key: str, scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "module_disabled",
        "tool": tool_name,
        "required_module": module_key,
        "message": "This module is not enabled for this company.",
        "company_id": scope.get("company_id"),
    }


def _entitlement_context(scope: dict[str, Any]) -> dict[str, Any]:
    """Map orchestrator scope into the same authority shape HTTP handlers use.

    Must preserve permission_authority / subject markers from
    posthire_dashboard_scope (and WhatsApp scopes). Dropping them makes
    require_entitlement see an empty grant set and fail closed even when the
    action was correctly advertised from backend-current permissions.
    """
    permissions = sorted({str(item) for item in scope.get("permissions") or [] if str(item).strip()})
    access = scope.get("access") if isinstance(scope.get("access"), dict) else {}
    authority = str(
        scope.get("permission_authority")
        or access.get("permission_authority")
        or ""
    ).strip()
    subject_user_id = str(
        scope.get("permission_subject_user_id")
        or access.get("permission_subject_user_id")
        or scope.get("admin_user_id")
        or ""
    ).strip()
    subject_company = str(
        scope.get("permission_subject_company")
        or access.get("permission_subject_company")
        or scope.get("company_id")
        or ""
    ).strip().upper()
    role = scope.get("role_scope") or access.get("role")
    hr_user = scope.get("hr_user") if isinstance(scope.get("hr_user"), dict) else None
    return {
        "company_code": scope.get("company_id"),
        "company_id": scope.get("company_id"),
        "actor_user_id": scope.get("admin_user_id"),
        "admin_user_id": scope.get("admin_user_id"),
        "actor_email": scope.get("actor_email"),
        "actor_role": role,
        "role_scope": role,
        "permissions": permissions,
        "permission_authority": authority,
        "permission_subject_user_id": subject_user_id,
        "permission_subject_company": subject_company,
        "hr_user": hr_user,
        "access": {
            "role": role,
            "permissions": permissions,
            "permission_authority": authority,
            "permission_subject_user_id": subject_user_id,
            "permission_subject_company": subject_company,
        },
    }


def _safe_detail(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None)
    return detail if isinstance(detail, dict) else {}


def _action_module(action_name: str | None) -> str | None:
    spec = _registry.spec_for(action_name)
    return str(spec.module) if spec and spec.module else None


def _batch_action_name(args: dict[str, Any]) -> str | None:
    action = str(args.get("batch_action_type") or args.get("target_action_type") or "").strip()
    if action:
        return action
    text = " ".join(str(args.get(key) or "") for key in ("workflow_goal", "prompt_text", "message_text", "purpose", "query")).lower()
    if "video" in text and "interview" in text:
        return "send_video_interview"
    if "assessment" in text:
        return "send_assessment"
    if "interview" in text:
        return "send_interview_invite"
    if "shortlist" in text:
        return "shortlist_candidate"
    return None


def _workflow_step_names(args: dict[str, Any]) -> list[str]:
    raw_steps = args.get("steps")
    steps: list[str] = []
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if isinstance(item, str):
                steps.append(item)
            elif isinstance(item, dict):
                name = str(item.get("action_type") or item.get("step") or item.get("tool_name") or "").strip()
                if name:
                    steps.append(name)
    if not steps and hasattr(_registry, "_workflow_steps_from_action"):
        try:
            inferred = _registry._workflow_steps_from_action(args)  # type: ignore[attr-defined]
            if isinstance(inferred, list):
                steps.extend(str(item) for item in inferred if str(item).strip())
        except Exception:
            pass
    return steps


def _mixed_item_action_names(args: dict[str, Any]) -> list[str]:
    raw_items = args.get("mixed_items") or args.get("items") or args.get("batch_items")
    actions: list[str] = []
    if not isinstance(raw_items, list):
        return actions
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action_type") or item.get("batch_action_type") or "").strip()
        if not action:
            action = _batch_action_name(item) or ""
        if action:
            actions.append(action)
    return actions


def _required_entitlements(tool_name: str, args: dict[str, Any], spec: Any, required_permission: str | None) -> list[tuple[str, str | None]]:
    entitlements: list[tuple[str, str | None]] = []

    def add(module: str | None, permission: str | None) -> None:
        if not module:
            return
        item = (str(module), permission)
        if item not in entitlements:
            entitlements.append(item)

    add(getattr(spec, "module", None), required_permission)
    if tool_name == "execute_candidate_batch":
        action = _batch_action_name(args)
        add(_action_module(action), TOOL_PERMISSION_MAP.get(action or "", required_permission or "candidate.manage"))
    elif tool_name == "execute_mixed_candidate_batch":
        for action in _mixed_item_action_names(args):
            add(_action_module(action), TOOL_PERMISSION_MAP.get(action, required_permission or "candidate.manage"))
    elif tool_name == "execute_candidate_workflow":
        for action in _workflow_step_names(args):
            add(_action_module(action), TOOL_PERMISSION_MAP.get(action, required_permission or "candidate.manage"))
    return entitlements


def _require_tool_entitlements(tool_name: str, args: dict[str, Any], spec: Any, required_permission: str | None, scope: dict[str, Any]) -> dict[str, Any] | None:
    legacy = _legacy()
    for module_key, permission in _required_entitlements(tool_name, args, spec, required_permission):
        if hasattr(legacy, "require_entitlement"):
            try:
                legacy.require_entitlement(_entitlement_context(scope), module_key, permission)
                continue
            except Exception as exc:
                detail = _safe_detail(exc)
                if detail.get("error") == "module_disabled":
                    return _module_disabled(tool_name, str(detail.get("required_module") or module_key), scope)
                if detail.get("error") == "permission_denied":
                    return _permission_denied(tool_name, str(detail.get("required_permission") or permission or required_permission or "prehire.read"), scope)
                return {
                    "status": str(detail.get("error") or "permission_denied"),
                    "tool": tool_name,
                    "message": str(detail.get("message") or "You do not have permission to do this action."),
                    "company_id": scope.get("company_id"),
                }
        if hasattr(legacy, "company_has_module"):
            try:
                if not legacy.company_has_module(scope.get("company_id"), module_key):
                    return _module_disabled(tool_name, module_key, scope)
            except Exception:
                return _module_disabled(tool_name, module_key, scope)
    return None


def _strict_whatsapp_perms() -> bool:
    """Item 4 hardening flag (WATHEFNI_STRICT_WHATSAPP_PERMS).

    When ON, a WhatsApp/HR turn that resolves to NO dashboard permissions
    (an unlinked WhatsApp number or a sender with no real role) can still read,
    but can no longer invoke mutating tools — they fail closed with a clear,
    HR-facing access message. Default OFF; rolled out on staging first.

    Linked dashboard users always carry their real (non-empty) permission set,
    so they are unaffected. Employee self-service uses a separate non-HR turn
    handler and never reaches this code path.
    """
    return os.environ.get("WATHEFNI_STRICT_WHATSAPP_PERMS", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_read_only_permission(permission: str | None) -> bool:
    return bool(permission) and str(permission).endswith(".read")


def _access_not_linked(tool_name: str, required_permission: str | None, scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "permission_denied",
        "tool": tool_name,
        "required_permission": required_permission,
        "message": (
            "This WhatsApp number isn’t linked to a Wathefni account with permission for that. "
            "Ask a workspace admin to link your number or grant the right role, then try again."
        ),
        "company_id": scope.get("company_id"),
        "role_scope": scope.get("role_scope"),
        "reason": "identity_not_linked",
    }


def _tool_allowed(tool_name: str, scope: dict[str, Any]) -> tuple[bool, str | None]:
    required = TOOL_PERMISSION_MAP.get(tool_name, "prehire.read")
    permissions = {str(item) for item in scope.get("permissions") or []}
    if not permissions:
        if _strict_whatsapp_perms() and not _is_read_only_permission(required):
            # Fail closed: an unlinked / no-role identity cannot run mutating tools.
            return False, required
        # Flag off, or a read-only tool: keep legacy admin-capable behaviour.
        return True, required
    return required in permissions, required


def _visible_tools(tools: list[dict[str, Any]], scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the registry tool catalog for this company + user.

    Core pre-hiring/assessments/video tools are unchanged (always offered;
    execution-time entitlement still applies). Tools whose module is in
    TOOLCALL_GATED_MODULES are only offered when the company has that module
    enabled and the user holds the tool's permission. Legacy WhatsApp admins
    with no explicit permission set keep admin-level visibility, matching
    _tool_allowed's existing behaviour.
    """

    legacy = _legacy()
    company = scope.get("company_id")
    permissions = {str(item) for item in scope.get("permissions") or [] if str(item).strip()}
    module_enabled_cache: dict[str, bool] = {}

    def module_enabled(module_key: str) -> bool:
        if module_key not in module_enabled_cache:
            enabled = False
            if hasattr(legacy, "company_has_module"):
                try:
                    enabled = bool(legacy.company_has_module(company, module_key))
                except Exception:
                    enabled = False
            module_enabled_cache[module_key] = enabled
        return module_enabled_cache[module_key]

    visible: list[dict[str, Any]] = []
    for tool in tools:
        name = str((tool.get("function") or {}).get("name") or "")
        spec = _registry.spec_for(name)
        module_key = str(getattr(spec, "module", None) or "") if spec else ""
        if module_key in TOOLCALL_GATED_MODULES:
            if not module_enabled(module_key):
                continue
            required = TOOL_PERMISSION_MAP.get(name)
            if permissions and required and required not in permissions:
                continue
            if not permissions and _strict_whatsapp_perms() and required and not _is_read_only_permission(required):
                # Strict mode: don't even offer mutating post-hire tools to an unlinked identity.
                continue
        visible.append(tool)
    return visible


def _batch_required_permission(args: dict[str, Any]) -> str:
    action = str(args.get("batch_action_type") or args.get("target_action_type") or "").strip()
    text = " ".join(str(args.get(key) or "") for key in ("workflow_goal", "prompt_text", "message_text", "purpose", "query")).lower()
    if not action:
        if "video" in text and "interview" in text:
            action = "send_video_interview"
        elif "assessment" in text:
            action = "send_assessment"
        elif "interview" in text:
            action = "send_interview_invite"
        elif "shortlist" in text:
            action = "shortlist_candidate"
    return TOOL_PERMISSION_MAP.get(action, TOOL_PERMISSION_MAP.get("execute_candidate_batch", "candidate.manage"))


def _mixed_batch_required_permissions(args: dict[str, Any]) -> list[str]:
    raw_items = args.get("mixed_items") or args.get("items") or args.get("batch_items")
    if not isinstance(raw_items, list):
        return [TOOL_PERMISSION_MAP.get("execute_mixed_candidate_batch", "candidate.manage")]
    permissions: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action_type") or item.get("batch_action_type") or "").strip()
        if not action:
            text = " ".join(str(item.get(key) or "") for key in ("workflow_goal", "message_text", "purpose", "query")).lower()
            if "video" in text and "interview" in text:
                action = "send_video_interview"
            elif "assessment" in text:
                action = "send_assessment"
            elif "interview" in text:
                action = "send_interview_invite"
            elif "shortlist" in text:
                action = "shortlist_candidate"
        permission = TOOL_PERMISSION_MAP.get(action) or TOOL_PERMISSION_MAP.get("execute_mixed_candidate_batch", "candidate.manage")
        if permission not in permissions:
            permissions.append(permission)
    return permissions or [TOOL_PERMISSION_MAP.get("execute_mixed_candidate_batch", "candidate.manage")]


def _is_fresh_session_opener(text: str | None) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if OPERATIONAL_HINT_RE.search(raw):
        return False
    return bool(CASUAL_SESSION_RESET_RE.match(raw))


def _scope_matches(scope: dict[str, Any], expected: dict[str, Any], *, include_session: bool = True) -> bool:
    keys = ("company_id", "account_id", "admin_user_id", "conversation_id", "channel", "module")
    if include_session:
        keys = (*keys, "session_id")
    return all(str(scope.get(key) or "") == str(expected.get(key) or "") for key in keys)


def _latest_active_session_state(request: Any, base_scope: dict[str, Any]) -> dict[str, Any]:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot.payload
                FROM memory_snapshots snapshot
                JOIN hr_turns turn ON turn.turn_id=snapshot.turn_id
                WHERE snapshot.scope=%s
                  AND turn.sender_phone=%s
                  AND (%s IS NULL OR turn.account_id=%s)
                  AND (%s IS NULL OR turn.conversation_id=%s)
                  AND snapshot.payload->'memory_scope'->>'company_id'=%s
                  AND snapshot.payload->'memory_scope'->>'admin_user_id'=%s
                  AND snapshot.payload->'memory_scope'->>'conversation_id'=%s
                  AND snapshot.payload->'memory_scope'->>'channel'=%s
                  AND snapshot.payload->'memory_scope'->>'module'=%s
                  AND COALESCE(snapshot.payload->>'expires_at', snapshot.payload->'memory_scope'->>'expires_at', '') > %s
                ORDER BY snapshot.created_at DESC
                LIMIT 1
                """,
                (
                    TOOLCALL_STATE_SCOPE,
                    legacy.digits(request.sender_phone),
                    request.account_id,
                    request.account_id,
                    request.conversation_id,
                    request.conversation_id,
                    str(base_scope["company_id"]),
                    str(base_scope["admin_user_id"]),
                    str(base_scope["conversation_id"]),
                    str(base_scope["channel"]),
                    str(base_scope["module"]),
                    _now_iso(),
                ),
            )
            row = cur.fetchone()
    return dict(row["payload"]) if row and isinstance(row.get("payload"), dict) else {}


def _resolve_memory_scope(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    base_scope = _base_memory_scope(request)
    if _is_fresh_session_opener(getattr(request, "raw_text", "")):
        session_id = f"toolcall-{uuid.uuid4().hex}"
        scope = {**base_scope, "session_id": session_id, "workflow_id": session_id, "expires_at": _session_expires_at()}
        return scope, {}
    active_state = _latest_active_session_state(request, base_scope)
    active_scope = active_state.get("memory_scope") if isinstance(active_state.get("memory_scope"), dict) else {}
    active_expires = _parse_iso(active_state.get("expires_at") or active_scope.get("expires_at"))
    if active_scope and active_expires and active_expires > datetime.now(timezone.utc) and _scope_matches(active_scope, base_scope, include_session=False):
        session_id = str(active_scope.get("session_id") or active_scope.get("workflow_id") or f"toolcall-{uuid.uuid4().hex}")
        scope = {**base_scope, "session_id": session_id, "workflow_id": session_id, "expires_at": _session_expires_at()}
        return scope, active_state
    session_id = f"toolcall-{uuid.uuid4().hex}"
    scope = {**base_scope, "session_id": session_id, "workflow_id": session_id, "expires_at": _session_expires_at()}
    return scope, {}


def _attach_scope_to_request(request: Any, scope: dict[str, Any]) -> None:
    metadata = getattr(request, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = {**metadata, "memory_scope": _json_safe(scope)}
    try:
        request.metadata = metadata
    except Exception:
        setattr(request, "metadata", metadata)


def _conversation_history(request: Any, scope: dict[str, Any], *, exclude_turn_id: str | None = None, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, Any]]:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT turn.turn_id::text, turn.raw_text, turn.created_at, result.final_reply
                FROM hr_turns turn
                LEFT JOIN action_results result ON result.turn_id=turn.turn_id
                WHERE turn.sender_phone=%s
                  AND (%s IS NULL OR turn.account_id=%s)
                  AND (%s IS NULL OR turn.conversation_id=%s)
                  AND (%s IS NULL OR turn.turn_id::text<>%s)
                  AND turn.metadata->'memory_scope'->>'company_id'=%s
                  AND turn.metadata->'memory_scope'->>'admin_user_id'=%s
                  AND turn.metadata->'memory_scope'->>'conversation_id'=%s
                  AND turn.metadata->'memory_scope'->>'channel'=%s
                  AND turn.metadata->'memory_scope'->>'module'=%s
                  AND turn.metadata->'memory_scope'->>'session_id'=%s
                ORDER BY turn.created_at DESC
                LIMIT %s
                """,
                (
                    legacy.digits(request.sender_phone),
                    request.account_id,
                    request.account_id,
                    request.conversation_id,
                    request.conversation_id,
                    exclude_turn_id,
                    exclude_turn_id,
                    str(scope["company_id"]),
                    str(scope["admin_user_id"]),
                    str(scope["conversation_id"]),
                    str(scope["channel"]),
                    str(scope["module"]),
                    str(scope["session_id"]),
                    max(1, min(limit, 20)),
                ),
            )
            rows = [dict(row) for row in cur.fetchall()]
    history: list[dict[str, Any]] = []
    for row in reversed(rows):
        if row.get("raw_text"):
            history.append({"role": "user", "content": str(row["raw_text"])})
        if row.get("final_reply"):
            history.append({"role": "assistant", "content": str(row["final_reply"])})
    return history[-limit * 2:]


def _latest_state(request: Any, scope: dict[str, Any], active_state: dict[str, Any] | None = None) -> dict[str, Any]:
    if active_state and isinstance(active_state, dict):
        active_scope = active_state.get("memory_scope") if isinstance(active_state.get("memory_scope"), dict) else {}
        if _scope_matches(active_scope, scope):
            return active_state
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot.payload
                FROM memory_snapshots snapshot
                JOIN hr_turns turn ON turn.turn_id=snapshot.turn_id
                WHERE snapshot.scope=%s
                  AND turn.sender_phone=%s
                  AND (%s IS NULL OR turn.account_id=%s)
                  AND (%s IS NULL OR turn.conversation_id=%s)
                  AND snapshot.payload->'memory_scope'->>'company_id'=%s
                  AND snapshot.payload->'memory_scope'->>'admin_user_id'=%s
                  AND snapshot.payload->'memory_scope'->>'conversation_id'=%s
                  AND snapshot.payload->'memory_scope'->>'channel'=%s
                  AND snapshot.payload->'memory_scope'->>'module'=%s
                  AND snapshot.payload->'memory_scope'->>'session_id'=%s
                ORDER BY snapshot.created_at DESC
                LIMIT 1
                """,
                (
                    TOOLCALL_STATE_SCOPE,
                    legacy.digits(request.sender_phone),
                    request.account_id,
                    request.account_id,
                    request.conversation_id,
                    request.conversation_id,
                    str(scope["company_id"]),
                    str(scope["admin_user_id"]),
                    str(scope["conversation_id"]),
                    str(scope["channel"]),
                    str(scope["module"]),
                    str(scope["session_id"]),
                ),
            )
            row = cur.fetchone()
    return dict(row["payload"]) if row and isinstance(row.get("payload"), dict) else {}


def _last_action_result(request: Any, scope: dict[str, Any]) -> dict[str, Any]:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT result.action_type, result.status, result.result, result.final_reply, result.created_at
                FROM action_results result
                JOIN hr_turns turn ON turn.turn_id=result.turn_id
                WHERE turn.sender_phone=%s
                  AND (%s IS NULL OR turn.account_id=%s)
                  AND (%s IS NULL OR turn.conversation_id=%s)
                  AND result.result->'memory_scope'->>'company_id'=%s
                  AND result.result->'memory_scope'->>'admin_user_id'=%s
                  AND result.result->'memory_scope'->>'conversation_id'=%s
                  AND result.result->'memory_scope'->>'channel'=%s
                  AND result.result->'memory_scope'->>'module'=%s
                  AND result.result->'memory_scope'->>'session_id'=%s
                  AND result.status NOT IN %s
                ORDER BY result.created_at DESC
                LIMIT 1
                """,
                (
                    legacy.digits(request.sender_phone),
                    request.account_id,
                    request.account_id,
                    request.conversation_id,
                    request.conversation_id,
                    str(scope["company_id"]),
                    str(scope["admin_user_id"]),
                    str(scope["conversation_id"]),
                    str(scope["channel"]),
                    str(scope["module"]),
                    str(scope["session_id"]),
                    tuple(sorted(TERMINAL_FAILURE_STATUSES)),
                ),
            )
            row = cur.fetchone()
    return _json_safe(dict(row)) if row else {}


def _summarize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    return {
        "app_key": candidate.get("app_key"),
        "name": candidate.get("name") or candidate.get("candidate_name"),
        "position": candidate.get("position_title") or candidate.get("position_code"),
        "status": candidate.get("status"),
        "score": candidate.get("score") or candidate.get("ranking_score"),
        "reasons": (candidate.get("reasons") or candidate.get("evidence") or [])[:3],
    }


def _summarize_last_result(last: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(last, dict) or not last:
        return {}
    result = last.get("result") if isinstance(last.get("result"), dict) else last
    summary: dict[str, Any] = {
        "action_type": last.get("action_type") or result.get("action_type"),
        "status": last.get("status") or result.get("status"),
        "created_at": _json_safe(last.get("created_at")),
    }
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else None
    if candidates:
        summary["candidates"] = [_summarize_candidate(c) for c in candidates[:CANDIDATE_SUMMARY_LIMIT]]
    context = result.get("candidate_context") if isinstance(result.get("candidate_context"), dict) else None
    if context:
        copy = dict(context)
        cv_text = copy.get("cv_text")
        if isinstance(cv_text, str) and len(cv_text) > 4000:
            copy["cv_text"] = cv_text[:4000]
        summary["candidate_context"] = copy
    return summary


def _module_focus(state: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    by_module = state.get("current_focus_by_module") if isinstance(state.get("current_focus_by_module"), dict) else {}
    module_focus = by_module.get(scope["module"]) if isinstance(by_module.get(scope["module"]), dict) else None
    if module_focus:
        return module_focus
    return state.get("current_focus") if isinstance(state.get("current_focus"), dict) else {}


def _build_state_summary(state: dict[str, Any], request: Any, scope: dict[str, Any]) -> dict[str, Any]:
    last = _last_action_result(request, scope)
    pending = _find_active_pending(request, scope)
    return {
        "now_iso": _now_iso(),
        "memory_scope": _json_safe(scope),
        "context_policy": "Only same company/admin/conversation/channel/module/session context is active. Older or cross-module history is audit-only unless the user explicitly bridges modules.",
        "current_focus": _module_focus(state, scope),
        "last_action_result": _summarize_last_result(last),
        "pending_confirmation": _summarize_pending(pending),
    }


def _summarize_pending(pending: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(pending, dict) or not pending:
        return {}
    metadata = pending.get("metadata") if isinstance(pending.get("metadata"), dict) else {}
    return {
        "action_id": str(pending.get("action_id") or ""),
        "tool": metadata.get("tool_name") or pending.get("action_type"),
        "args": metadata.get("tool_args") or {},
        "asked_at": _json_safe(pending.get("created_at")),
    }


def _find_active_pending(request: Any, scope: dict[str, Any]) -> dict[str, Any] | None:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM pending_actions
                WHERE admin_phone=%s
                  AND (%s IS NULL OR account_id=%s)
                  AND (%s IS NULL OR conversation_id=%s)
                  AND action_type=%s
                  AND status='pending'
                  AND (expires_at IS NULL OR expires_at > now())
                  AND metadata->'memory_scope'->>'company_id'=%s
                  AND metadata->'memory_scope'->>'admin_user_id'=%s
                  AND metadata->'memory_scope'->>'conversation_id'=%s
                  AND metadata->'memory_scope'->>'channel'=%s
                  AND metadata->'memory_scope'->>'module'=%s
                  AND metadata->'memory_scope'->>'session_id'=%s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    legacy.digits(request.sender_phone),
                    request.account_id,
                    request.account_id,
                    request.conversation_id,
                    request.conversation_id,
                    "toolcall_pending",
                    str(scope["company_id"]),
                    str(scope["admin_user_id"]),
                    str(scope["conversation_id"]),
                    str(scope["channel"]),
                    str(scope["module"]),
                    str(scope["session_id"]),
                ),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _action_hash(tool_name: str, tool_args: dict[str, Any], scope: dict[str, Any]) -> str:
    payload = {
        "tool_name": tool_name,
        "tool_args": tool_args,
        "company_id": scope.get("company_id"),
        "admin_user_id": scope.get("admin_user_id"),
        "module": scope.get("module"),
        "target": tool_args.get("candidate_app_key") or tool_args.get("candidate_name") or tool_args.get("candidate_email") or tool_args.get("candidate_phone"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _save_pending(
    request: Any,
    graph_state: dict[str, Any],
    tool_name: str,
    tool_args: dict[str, Any],
    summary: str,
    scope: dict[str, Any],
    preflight_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    pending_metadata = {
        "tool_name": tool_name,
        "tool_args": tool_args,
        "memory_scope": scope,
        "action_hash": _action_hash(tool_name, tool_args, scope),
        "preflight_plan": preflight_plan or {},
        "confirmation_contract": "same_admin_company_conversation_module_session_and_action_hash",
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_actions
                (account_id, conversation_id, admin_phone, action_type, subject_type, subject_key, subject_name, prompt_text,
                 metadata, company_code, actor_user_id, actor_phone, actor_role, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now() + interval '20 minutes')
                RETURNING *
                """,
                (
                    request.account_id,
                    request.conversation_id,
                    legacy.digits(request.sender_phone),
                    "toolcall_pending",
                    tool_args.get("subject_type") or "candidate",
                    tool_args.get("candidate_app_key") or tool_args.get("subject_key"),
                    tool_args.get("candidate_name") or tool_args.get("subject_name"),
                    summary,
                    legacy.Json(_json_safe(pending_metadata)),
                    str(scope.get("company_id") or ""),
                    str(scope.get("admin_user_id") or ""),
                    legacy.digits(request.sender_phone),
                    str(scope.get("role_scope") or ""),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def _resolve_pending_match(request: Any, tool_name: str, tool_args: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any] | None:
    pending = _find_active_pending(request, scope)
    if not pending:
        return None
    metadata = pending.get("metadata") if isinstance(pending.get("metadata"), dict) else {}
    if metadata.get("tool_name") != tool_name:
        return None
    pending_scope = metadata.get("memory_scope") if isinstance(metadata.get("memory_scope"), dict) else {}
    if not _scope_matches(pending_scope, scope):
        return None
    if metadata.get("action_hash") and metadata.get("action_hash") != _action_hash(tool_name, tool_args, scope):
        return None
    prev_args = metadata.get("tool_args") if isinstance(metadata.get("tool_args"), dict) else {}
    candidate_keys = ("candidate_app_key", "candidate_name", "candidate_email", "candidate_phone")
    for key in candidate_keys:
        if prev_args.get(key) and tool_args.get(key) and str(prev_args[key]).lower() != str(tool_args[key]).lower():
            return None
    return pending


def _mark_pending_resolved(action_id: Any, status: str) -> None:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_actions SET status=%s, resolved_at=now() WHERE action_id=%s",
                (status, action_id),
            )
        conn.commit()


def _approval_value(text: str | None) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if REJECTION_RE.match(raw):
        return "rejected"
    if APPROVAL_RE.match(raw):
        return "approved"
    return None


def _candidate_match_summary(match: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(match, dict):
        return {}
    return {
        "app_key": match.get("app_key"),
        "name": match.get("candidate_name"),
        "email": match.get("candidate_email"),
        "phone": match.get("phone"),
        "position": match.get("position_title") or match.get("position_code"),
        "status": match.get("status"),
        "similarity": match.get("match_similarity"),
        "match_source": match.get("match_source"),
    }


def _candidate_from_recent_rank_state(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a candidate reference from the latest ranked list before falling
    back to name-only database search.

    This prevents "send him screening questions" after an Accounting Excel list
    from resolving Hamad's older HR application just because the name matches.
    """

    if args.get("candidate_app_key") or args.get("app_key"):
        return None
    wanted = str(args.get("candidate_name") or args.get("subject_name") or args.get("name") or "").strip().lower()
    outputs = state.get("last_tool_outputs") if isinstance(state.get("last_tool_outputs"), list) else []
    candidates: list[dict[str, Any]] = []
    for output in reversed(outputs):
        if not isinstance(output, dict):
            continue
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        if result.get("action_type") != "rank_candidates":
            continue
        rows = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        candidates = [row for row in rows if isinstance(row, dict)]
        if candidates:
            break
    if not candidates:
        return None
    if wanted in {"", "him", "her", "them", "he", "she", "candidate", "the candidate"} and len(candidates) == 1:
        return candidates[0]
    if wanted:
        matches = [
            item for item in candidates
            if wanted in str(item.get("name") or item.get("candidate_name") or "").strip().lower()
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _tool_call_summary(tool_name: str, args: dict[str, Any]) -> str:
    fragments = [tool_name.replace("_", " ")]
    if args.get("batch_action_type"):
        fragments.append(str(args.get("batch_action_type")).replace("_", " "))
    if args.get("top_n"):
        fragments.append(f"top {args.get('top_n')}")
    if args.get("candidate_names"):
        fragments.append("for " + ", ".join(str(item) for item in args.get("candidate_names") or []))
    target = args.get("candidate_name") or args.get("candidate_app_key") or args.get("candidate_email")
    if target:
        fragments.append(f"for {target}")
    if args.get("position"):
        fragments.append(f"position={args['position']}")
    if args.get("status"):
        fragments.append(f"status={args['status']}")
    return " ".join(str(part) for part in fragments)


def _pending_args(pending: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    metadata = pending.get("metadata") if isinstance(pending.get("metadata"), dict) else {}
    tool_name = str(metadata.get("tool_name") or "")
    tool_args = metadata.get("tool_args") if isinstance(metadata.get("tool_args"), dict) else {}
    preflight_plan = metadata.get("preflight_plan") if isinstance(metadata.get("preflight_plan"), dict) else {}
    return tool_name, tool_args, preflight_plan


def _build_action_payload(tool_name: str, args: dict[str, Any], request: Any, resolved_app: dict[str, Any] | None, scope: dict[str, Any]) -> dict[str, Any]:
    action: dict[str, Any] = {
        "action_type": tool_name,
        "planned_by": TOOLCALL_GRAPH_VERSION,
        "memory_scope": scope,
        "company_code": scope.get("company_id"),
        "actor_user_id": scope.get("admin_user_id"),
        "actor_phone": scope.get("admin_user_id"),
        "actor_role": scope.get("role_scope"),
    }
    action.update({k: v for k, v in args.items() if v not in (None, "", [], {})})
    action["prompt_text"] = getattr(request, "raw_text", None)
    # Never inject the full user utterance as a hard inventory filter.
    if tool_name == "list_job_openings":
        action.pop("query", None)
        action.pop("search", None)
    else:
        action["query"] = args.get("query") or getattr(request, "raw_text", None)
    if resolved_app:
        action["app_key"] = resolved_app.get("app_key")
        action["subject_key"] = resolved_app.get("app_key")
        action["subject_type"] = "candidate"
        action["subject_name"] = resolved_app.get("candidate_name")
        action["subject_phone"] = resolved_app.get("phone")
        action["email"] = resolved_app.get("candidate_email")
        action["position_code"] = action.get("position_code") or resolved_app.get("position_code")
        action["position_title"] = action.get("position_title") or resolved_app.get("position_title")
        action["resolved_candidate"] = {
            "app_key": resolved_app.get("app_key"),
            "candidate_name": resolved_app.get("candidate_name"),
            "candidate_email": resolved_app.get("candidate_email"),
            "phone": resolved_app.get("phone"),
            "position_code": resolved_app.get("position_code"),
            "position_title": resolved_app.get("position_title"),
            "status": resolved_app.get("status"),
        }
    return {key: value for key, value in action.items() if value not in (None, "", [], {})}


def _execute_tool(tool_name: str, args: dict[str, Any], request: Any, state: dict[str, Any], graph_state: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    legacy = _legacy()
    args = {**args, "company_code": scope.get("company_id")}
    spec = _registry.spec_for(tool_name)
    if not spec or not spec.executor:
        return {"status": "error", "message": "That action is not available right now.", "tool": tool_name}
    allowed, required_permission = _tool_allowed(tool_name, scope)
    if tool_name == "execute_mixed_candidate_batch":
        permissions = {str(item) for item in scope.get("permissions") or []}
        required_permissions = _mixed_batch_required_permissions(args)
        if not permissions and _strict_whatsapp_perms():
            non_read = [perm for perm in required_permissions if not _is_read_only_permission(perm)]
            if non_read:
                denied = _access_not_linked(tool_name, non_read[0], scope)
                denied["required_permissions"] = required_permissions
                return denied
        missing_permissions = [permission for permission in required_permissions if permissions and permission not in permissions]
        if missing_permissions:
            denied = _permission_denied(tool_name, missing_permissions[0], scope)
            denied["required_permissions"] = required_permissions
            return denied
        allowed = True
        required_permission = required_permissions[0] if required_permissions else "candidate.manage"
    if tool_name == "execute_candidate_batch":
        required_permission = _batch_required_permission(args)
        permissions = {str(item) for item in scope.get("permissions") or []}
        if not permissions:
            allowed = not (_strict_whatsapp_perms() and not _is_read_only_permission(required_permission))
        else:
            allowed = required_permission in permissions
    if not allowed and required_permission:
        permissions = {str(item) for item in scope.get("permissions") or []}
        if not permissions and _strict_whatsapp_perms():
            return _access_not_linked(tool_name, required_permission, scope)
        return _permission_denied(tool_name, required_permission, scope)
    entitlement_denied = _require_tool_entitlements(tool_name, args, spec, required_permission, scope)
    if entitlement_denied:
        return entitlement_denied
    resolved_app = None
    if spec.entity_type == "candidate":
        if not any(args.get(key) for key in ("candidate_app_key", "app_key", "subject_key", "candidate_name", "subject_name", "candidate_email", "candidate_phone", "subject_phone")):
            focus = _module_focus(state, scope)
            if isinstance(focus, dict) and focus.get("app_key"):
                args = {**args, "candidate_app_key": focus.get("app_key"), "candidate_name": focus.get("candidate_name")}
        ranked_candidate = _candidate_from_recent_rank_state(state, args)
        if ranked_candidate and ranked_candidate.get("app_key"):
            args = {
                **args,
                "candidate_app_key": ranked_candidate.get("app_key"),
                "candidate_name": ranked_candidate.get("name") or ranked_candidate.get("candidate_name") or args.get("candidate_name"),
            }
        resolution = _registry.resolve_candidate_typed(legacy, args)
        status = resolution.get("status")
        matches = resolution.get("matches") or []
        if status == "resolved" and matches:
            resolved_app = matches[0]
        elif status == "no_input":
            return {
                "status": "needs_candidate_reference",
                "tool": tool_name,
                "message": "I don't know which candidate to act on. Ask the user to name the candidate.",
                "args": args,
            }
        elif status == "ambiguous":
            return {
                "status": "candidate_ambiguous",
                "tool": tool_name,
                "message": "Multiple candidates match. List the options to the user and ask which one — do NOT pick one yourself.",
                "matches": [_candidate_match_summary(m) for m in matches[:5]],
                "searched": resolution.get("searched"),
                "args": args,
            }
        else:
            return {
                "status": "candidate_not_found",
                "tool": tool_name,
                "message": "No candidate in our database matches this. Tell the user the candidate is not in our records (the name or email may be misspelled, or they were never onboarded). Do NOT keep asking the user for more identifiers — they already gave one.",
                "searched": resolution.get("searched"),
                "args": args,
            }
    action = _build_action_payload(tool_name, args, request, resolved_app, scope)
    if spec.preflight is not None:
        preflight_ctx = _registry.ExecutionContext(
            request=request,
            action=action,
            state=state,
            graph_state=graph_state,
            intent={"tool_name": tool_name, "raw_args": args, "phase": "preflight"},
            legacy=legacy,
        )
        preflight_result = spec.preflight(preflight_ctx)
        if str(preflight_result.get("status") or "") != "ready":
            return {"status": preflight_result.get("status") or "needs_clarification", "tool": tool_name, "result": _json_safe(preflight_result)}
    if _registry.requires_confirmation(tool_name, action):
        if "preflight_result" not in locals() and hasattr(_registry, "outbound_confirmation_preview"):
            preview_ctx = _registry.ExecutionContext(
                request=request,
                action=action,
                state=state,
                graph_state=graph_state,
                intent={"tool_name": tool_name, "raw_args": args, "phase": "confirmation_preview"},
                legacy=legacy,
            )
            preview = _registry.outbound_confirmation_preview(preview_ctx, tool_name, resolved_app)
            if preview:
                if str(preview.get("status") or "") == "needs_clarification":
                    return {"status": "needs_clarification", "tool": tool_name, "result": _json_safe(preview)}
                preflight_result = {
                    "action_type": tool_name,
                    "success": True,
                    "status": "ready",
                    "message": preview.get("confirmation_text") or preview.get("title") or "Confirm to continue?",
                    "confirmation_preview": preview,
                    "confirmation_text": preview.get("confirmation_text"),
                }
        match = _resolve_pending_match(request, tool_name, args, scope)
        if not match:
            saved = _save_pending(
                request,
                graph_state,
                tool_name,
                args,
                _tool_call_summary(tool_name, args),
                scope,
                preflight_plan=preflight_result if "preflight_result" in locals() else None,
            )
            return {
                "status": "needs_confirmation",
                "tool": tool_name,
                "args": args,
                "pending_action_id": str(saved.get("action_id") or ""),
                "memory_scope": _json_safe(scope),
                "action_hash": _action_hash(tool_name, args, scope),
                "preflight_plan": _json_safe(preflight_result if "preflight_result" in locals() else {}),
                "result": _json_safe(preflight_result if "preflight_result" in locals() else {"message": "Confirm to continue?"}),
                "instruction": "Ask the user for one explicit confirmation for this exact stored plan. The backend will execute the stored plan directly when the user says yes; do not ask for repeated confirmations.",
            }
        _mark_pending_resolved(match["action_id"], "approved")
    ctx = _registry.ExecutionContext(
        request=request,
        action=action,
        state=state,
        graph_state=graph_state,
        intent={"tool_name": tool_name, "raw_args": args},
        legacy=legacy,
    )
    result = _registry.execute(tool_name, ctx)
    return {"status": result.get("status") or "completed", "tool": tool_name, "result": _json_safe(result)}


def _looks_like_list_job_openings_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not normalized:
        return False
    # Create / lifecycle intents belong to create/close/reopen tools.
    if re.search(r"\b(create|publish|add|make|generate)\b.*\b(job|position|opening|role|vacancy|qr)\b", normalized):
        return False
    if re.search(r"\bopen\s+(a|an|the|new)\b.*\b(job|position|opening|role|vacancy)\b", normalized):
        return False
    if re.search(r"\b(close|reopen|pause|resume|take down)\b.*\b(job|position|opening|role)\b", normalized):
        return False
    return bool(LIST_JOB_OPENINGS_RE.search(normalized))


def _looks_like_search_job_openings_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not normalized or _looks_like_list_job_openings_request(normalized):
        return False
    # Explicit role/title search, e.g. "search Finance jobs", "find IT Manager opening".
    if re.search(r"\b(search|find|look\s+up|lookup)\b.*\b(job|jobs|opening|openings|position|positions|role|roles)\b", normalized):
        return True
    if re.search(r"\b(job|jobs|opening|openings|position|positions|role|roles)\b.*\b(named|called|titled|for)\b", normalized):
        return True
    return False


def _forced_tool_for_turn(request: Any, tools: list[dict[str, Any]]) -> str | None:
    text = str(getattr(request, "raw_text", "") or "")
    tool_names = {str((tool.get("function") or {}).get("name") or "") for tool in tools}
    if "list_job_openings" in tool_names and _looks_like_list_job_openings_request(text):
        return "list_job_openings"
    if "search_job_openings" in tool_names and _looks_like_search_job_openings_request(text):
        return "search_job_openings"
    if "create_job_opening" in tool_names and JOB_OPENING_TRIGGER_RE.search(text):
        return "create_job_opening"
    if "rank_candidates" in tool_names and _looks_like_candidate_list_request(text):
        return "rank_candidates"
    if "get_interview_invite_status" in tool_names and INVITE_STATUS_RE.search(text):
        return "get_interview_invite_status"
    if "execute_mixed_candidate_batch" in tool_names and _looks_like_mixed_candidate_batch_request(text):
        return "execute_mixed_candidate_batch"
    if "execute_candidate_batch" in tool_names and BATCH_TRIGGER_RE.search(text):
        return "execute_candidate_batch"
    if "execute_candidate_workflow" in tool_names and WORKFLOW_TRIGGER_RE.search(text):
        # Mutation/workflow-looking HR turns must go through backend preflight.
        # This prevents the model from asking generic confirmations before it
        # checks missing fields, email availability, fallback channels, and permissions.
        return "execute_candidate_workflow"
    return None


def _looks_like_mixed_candidate_batch_request(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or not MIXED_BATCH_TRIGGER_RE.search(raw):
        return False
    normalized = raw.lower()
    action_hits = re.findall(r"\b(shortlist|hire|reject|send|notify|email|assessment|screening|video|interview|invite|link)\b", normalized)
    if len(set(action_hits)) < 2:
        return False
    explicit_to_names = re.findall(r"\b(?:to|for)\s+([A-Z][A-Za-z][A-Za-z' -]{0,40})", raw)
    comma_name_hits = re.findall(r"\b([A-Z][A-Za-z][A-Za-z' -]{1,30})\s*,", raw)
    if len({name.strip().lower() for name in explicit_to_names + comma_name_hits if name.strip()}) >= 2:
        return True
    if re.search(r"\b(and|,|then)\s+(send|notify|shortlist|email|assessment|screening|video|interview|invite|link)\s+(?:to|for)\s+[A-Z]", raw):
        return bool(re.search(r"\b(shortlist|hire|reject)\s+[A-Z]", raw))
    return False


def _looks_like_candidate_list_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not normalized:
        return False
    has_read_verb = re.search(r"\b(show|list|find|who|which|any|give me|get|display)\b", normalized)
    has_candidate = re.search(r"\b(candidate|candidates|applicant|applicants|people)\b", normalized)
    has_status_filter = re.search(
        r"\b(screening complete|screening_complete|review pending|review_pending|shortlisted|hired|rejected|awaiting cv|awaiting_cv|interview)\b",
        normalized,
    )
    return bool(has_read_verb and has_candidate and has_status_filter)


def _normalize_reasoning_effort(raw: Any) -> str:
    effort = str(raw or "").strip().lower()
    if effort in ALLOWED_TOOLCALL_REASONING_EFFORTS:
        return effort
    return DEFAULT_TOOLCALL_REASONING_EFFORT


def _reasoning_effort_for_request(request: Any | None = None) -> str:
    """Resolve Responses reasoning.effort. Staging may override via request metadata for evals."""
    env_effort = _normalize_reasoning_effort(os.environ.get("WATHEFNI_TOOL_AGENT_REASONING_EFFORT") or DEFAULT_TOOLCALL_REASONING_EFFORT)
    metadata = getattr(request, "metadata", None) if request is not None else None
    if not isinstance(metadata, dict):
        return env_effort
    override = metadata.get("tool_agent_reasoning_effort")
    if override is None:
        return env_effort
    # Staging-only override so production never changes effort via client metadata.
    if str(os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "staging":
        return env_effort
    return _normalize_reasoning_effort(override)


def _toolcall_provider_config() -> dict[str, str] | None:
    """HR toolcall always uses OpenAI Responses (/v1/responses), never Chat Completions."""
    legacy = _legacy()
    provider = legacy.planner_provider_config()
    if not provider:
        return None
    url = str(provider.get("url") or "")
    if "/chat/completions" in url:
        url = url.replace("/chat/completions", "/responses")
    elif "/responses" not in url:
        base = url.rsplit("/", 1)[0] if url else "https://api.openai.com/v1"
        if base.endswith("/v1"):
            url = f"{base}/responses"
        else:
            url = "https://api.openai.com/v1/responses"
    return {
        **provider,
        "url": url,
        "api": "openai-responses",
    }


def _force_strict_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively make a JSON schema compatible with Responses strict function tools."""
    out = dict(schema)

    # Resolve anyOf/oneOf/allOf branches.
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(out.get(key), list):
            out[key] = [
                _force_strict_object_schema(item) if isinstance(item, dict) else item
                for item in out[key]
            ]

    raw_type = out.get("type")
    types = raw_type if isinstance(raw_type, list) else ([raw_type] if isinstance(raw_type, str) else [])

    if "object" in types or ("properties" in out and "type" not in out):
        props_in = out.get("properties") if isinstance(out.get("properties"), dict) else {}
        props: dict[str, Any] = {}
        for key, child in props_in.items():
            if isinstance(child, dict):
                props[str(key)] = _force_strict_object_schema(child)
            else:
                props[str(key)] = child
        out["properties"] = props
        out["required"] = list(props.keys())
        out["additionalProperties"] = False

    if "array" in types or "items" in out:
        items = out.get("items")
        if isinstance(items, dict):
            out["items"] = _force_strict_object_schema(items)
        elif isinstance(items, list):
            out["items"] = [
                _force_strict_object_schema(item) if isinstance(item, dict) else item
                for item in items
            ]

    if isinstance(out.get("additionalProperties"), dict):
        out["additionalProperties"] = _force_strict_object_schema(out["additionalProperties"])

    return out


def _nullable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    out = _force_strict_object_schema(schema)
    raw_type = out.get("type")
    if isinstance(raw_type, list):
        types = list(raw_type)
        if "null" not in types:
            types.append("null")
        out["type"] = types
    elif isinstance(raw_type, str) and raw_type:
        out["type"] = [raw_type, "null"]
    else:
        # Property without explicit type — treat as nullable string for strict mode.
        out["type"] = ["string", "null"]
    if "enum" in out and isinstance(out["enum"], list) and None not in out["enum"]:
        out["enum"] = list(out["enum"]) + [None]
    return out


def _strict_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Convert chat-style parameters into Responses strict-compatible JSON schema."""
    params = parameters if isinstance(parameters, dict) else {}
    properties_in = params.get("properties") if isinstance(params.get("properties"), dict) else {}
    required_orig = {str(x) for x in (params.get("required") or []) if str(x)}
    properties: dict[str, Any] = {}
    for key, schema in properties_in.items():
        name = str(key)
        base = dict(schema) if isinstance(schema, dict) else {"type": "string"}
        if name not in required_orig:
            base = _nullable_schema(base)
        else:
            base = _force_strict_object_schema(base)
        properties[name] = base
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _convert_tools_for_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": str(fn.get("description") or ""),
                "parameters": _strict_parameters(fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {}),
                "strict": True,
            }
        )
    return converted


def _split_system_and_input(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    instructions = TOOLCALL_SYSTEM
    input_items: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role == "system":
            instructions = str(content or instructions)
            continue
        if role in {"user", "assistant"} and content is not None:
            input_items.append({"role": role, "content": str(content)})
    return instructions, input_items


def _provider_responses_body(
    *,
    instructions: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    provider: dict[str, str],
    reasoning_effort: str,
    forced_tool_name: str | None = None,
    previous_response_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": provider["model"],
        "instructions": instructions,
        "input": input_items,
        "tools": tools,
        "parallel_tool_calls": False,
        "reasoning": {"effort": reasoning_effort},
        "store": False,
    }
    # No custom temperature — gpt-5.6-* rejects non-default values.
    if forced_tool_name:
        body["tool_choice"] = {"type": "function", "name": forced_tool_name}
    else:
        body["tool_choice"] = "auto"
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    return body


def _is_transient_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return True
    if "http error 429" in text or "http error 500" in text or "http error 502" in text or "http error 503" in text:
        return True
    return False


def _http_error_body(exc: BaseException) -> str:
    read = getattr(exc, "read", None)
    if not callable(read):
        return ""
    try:
        return read().decode("utf-8", errors="replace")[:800]
    except Exception:
        return ""


def _call_responses_with_tools(
    *,
    instructions: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    turn_id: str | None,
    step: int,
    reasoning_effort: str,
    forced_tool_name: str | None = None,
    previous_response_id: str | None = None,
    tool_sequence: list[str] | None = None,
) -> dict[str, Any] | None:
    legacy = _legacy()
    provider = _toolcall_provider_config()
    if not provider:
        return None
    body = _provider_responses_body(
        instructions=instructions,
        input_items=input_items,
        tools=tools,
        provider=provider,
        reasoning_effort=reasoning_effort,
        forced_tool_name=forced_tool_name,
        previous_response_id=previous_response_id,
    )
    url = provider["url"]
    prompt_hash = legacy.stable_text_hash(TOOLCALL_SYSTEM)
    estimated_tokens = legacy.estimate_tokens_from_payload(body)
    attempts = TOOLCALL_LLM_RETRIES + 1
    last_error = ""
    start = time_module.monotonic()
    for attempt in range(attempts):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TOOLCALL_LLM_TIMEOUT_SEC) as resp:
                parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last_error = str(exc)
            detail = _http_error_body(exc)
            if detail:
                last_error = f"{last_error} | {detail}"
            if attempt + 1 < attempts and _is_transient_llm_error(exc):
                continue
            legacy.record_llm_call(
                turn_id=turn_id,
                call_name=f"toolcall_step_{step}",
                provider={**provider, "url": url},
                prompt_mode=TOOLCALL_GRAPH_VERSION,
                prompt_docs_loaded=False,
                prompt_hash=prompt_hash,
                estimated_input_tokens=estimated_tokens,
                latency_ms=int((time_module.monotonic() - start) * 1000),
                status="error",
                error=last_error[:500],
                metadata={
                    "graph": TOOLCALL_GRAPH_VERSION,
                    "step": step,
                    "forced_tool": forced_tool_name,
                    "api": "openai-responses",
                    "reasoning_effort": reasoning_effort,
                    "attempt": attempt + 1,
                    "previous_response_id": previous_response_id,
                    "tool_sequence": list(tool_sequence or []),
                    # Never persist hidden reasoning content.
                    "reasoning_content_logged": False,
                },
            )
            return None
        usage = legacy.usage_from_llm_response(parsed) if hasattr(legacy, "usage_from_llm_response") else {}
        legacy.record_llm_call(
            turn_id=turn_id,
            call_name=f"toolcall_step_{step}",
            provider={**provider, "url": url},
            prompt_mode=TOOLCALL_GRAPH_VERSION,
            prompt_docs_loaded=False,
            prompt_hash=prompt_hash,
            estimated_input_tokens=estimated_tokens,
            latency_ms=int((time_module.monotonic() - start) * 1000),
            status="ok",
            parsed=parsed,
            metadata={
                "graph": TOOLCALL_GRAPH_VERSION,
                "step": step,
                "forced_tool": forced_tool_name,
                "api": "openai-responses",
                "reasoning_effort": reasoning_effort,
                "attempt": attempt + 1,
                "previous_response_id": previous_response_id,
                "response_id": usage.get("response_id") or parsed.get("id"),
                "tool_sequence": list(tool_sequence or []),
                "output_item_types": [
                    str(item.get("type") or "")
                    for item in (parsed.get("output") or [])
                    if isinstance(item, dict)
                ],
                "reasoning_content_logged": False,
            },
        )
        return parsed
    return None


def _extract_responses_tool_calls(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in parsed.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        call_id = str(item.get("call_id") or item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        args_raw = item.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw if isinstance(args_raw, dict) else {})
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            {
                "id": call_id or f"call_{len(calls)}",
                "name": name,
                "arguments": args,
                "arguments_raw": args_raw if isinstance(args_raw, str) else json.dumps(args, ensure_ascii=False),
            }
        )
    return calls


def _extract_responses_text(parsed: dict[str, Any]) -> str:
    direct = parsed.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in parsed.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                chunks.append(str(part.get("text")))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _continuation_items_from_response(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Pass model output items back (including reasoning) without logging their content."""
    items: list[dict[str, Any]] = []
    for item in parsed.get("output") or []:
        if isinstance(item, dict):
            items.append(item)
    return items


# Maps a dashboard page id to a short, HR-friendly description of what that page
# is about. Used only to bias the assistant toward the area the user is currently
# viewing — it never changes which tools are available (that stays entitlement- and
# permission-gated via _visible_tools).
_DASHBOARD_PAGE_FOCUS: dict[str, str] = {
    "jobs": "Jobs — open positions, application links, and applicants waiting",
    "candidates": "Candidates — reviewing applicants and choosing the next hiring step",
    "interviews": "Interviews — scheduling, candidate responses, and feedback",
    "assessments": "Assessments — who needs one sent, progress, and results",
    "ranking": "Ranking — who to prioritize for a role",
    "notifications": "Notifications — HR action alerts and exceptions",
    "reports": "Reports — hiring reports and exports",
    "employees": "Employees — the people directory, roles, and onboarding status",
    "onboarding": "Onboarding — new hires in progress, documents, and reminders",
    "attendance": "Attendance — check-ins, late or missing, and corrections",
    "leave": "Leave — pending requests, approvals, and who is away",
    "shifts": "Shifts — the schedule, open gaps, and swap requests",
    "payroll": "Payroll — timesheets, exceptions, and the audited export",
    "analytics": "Analytics — workforce, attendance, and post-hire trends",
    "compliance": "Compliance — missing, expiring, expired, and needs-review documents",
    "settings": "Settings — team, roles, and workspace configuration",
}


def _dashboard_page(request: Any) -> str:
    metadata = getattr(request, "metadata", None)
    if isinstance(metadata, dict):
        return str(metadata.get("page") or "").strip()
    return ""


def _surface_instruction(request: Any) -> str:
    if _channel_for_request(request) != WEB_DASHBOARD_CHANNEL:
        return ""
    base = (
        "\n\nYou are the Wathefni Assistant, the company's HR assistant, answering inside the Wathefni "
        "web dashboard (not WhatsApp). You help across every HR area the company has enabled — hiring AND "
        "post-hire (employees, onboarding, attendance, leave, shifts, payroll, compliance, analytics). "
        "Your tool catalog already reflects what this company has enabled and what this user is allowed to do; "
        "only offer to help with areas whose tools are actually in your catalog, and never claim a module that is not. "
        "Use the same backend tools, permissions, confirmation policy, and audit rules. Keep text concise. "
        "For navigation requests like 'open Hamad' or 'show Accounting ranking', say what should be opened; "
        "the dashboard UI will render buttons."
    )
    focus = _DASHBOARD_PAGE_FOCUS.get(_dashboard_page(request))
    if focus:
        base += (
            f"\n\nThe user is currently working in {focus}. When their request is ambiguous, prioritize that "
            "area first — but you may help with anything else they ask, as long as the tools are in your catalog."
        )
    return base


def _build_messages(request: Any, state: dict[str, Any], state_summary: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system_payload = TOOLCALL_SYSTEM + _surface_instruction(request) + "\n\nstate_summary (JSON):\n" + json.dumps(state_summary, ensure_ascii=False, default=str)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_payload}]
    for msg in history:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": getattr(request, "raw_text", "") or ""})
    return messages


def _record_turn_result(turn_id: str, action_type: str, status: str, payload: dict[str, Any], final_reply: str, scope: dict[str, Any]) -> None:
    legacy = _legacy()
    scoped_payload = {**payload, "memory_scope": _json_safe(scope)}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hr_turns SET intent=%s, turn_focus=%s, final_reply_source=%s WHERE turn_id=%s",
                (action_type, "toolcall_dialog", "toolcall_orchestrator", turn_id),
            )
            cur.execute(
                """
                INSERT INTO action_results
                (turn_id, action_id, action_type, status, result, final_reply,
                 company_code, actor_user_id, actor_phone, actor_role)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    turn_id,
                    None,
                    action_type,
                    status,
                    legacy.Json(_json_safe(scoped_payload)),
                    final_reply,
                    str(scope.get("company_id") or ""),
                    str(scope.get("admin_user_id") or ""),
                    str(scope.get("admin_user_id") or ""),
                    str(scope.get("role_scope") or ""),
                ),
            )
        conn.commit()


def _save_state(turn_id: str, payload: dict[str, Any], scope: dict[str, Any]) -> None:
    legacy = _legacy()
    scoped_payload = {**payload, "memory_scope": _json_safe(scope), "expires_at": scope.get("expires_at")}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_snapshots (turn_id, scope, payload) VALUES (%s,%s,%s)",
                (turn_id, TOOLCALL_STATE_SCOPE, legacy.Json(_json_safe(scoped_payload))),
            )
        conn.commit()


def _candidate_focus_from_tool_calls(tool_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    for output in reversed(tool_outputs):
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        context = result.get("candidate_context") if isinstance(result.get("candidate_context"), dict) else None
        if context and context.get("app_key"):
            return {
                "app_key": context.get("app_key"),
                "candidate_name": context.get("name"),
                "position_code": context.get("job"),
            }
        application = result.get("application") if isinstance(result.get("application"), dict) else None
        if application and application.get("app_key"):
            return {
                "app_key": application.get("app_key"),
                "candidate_name": application.get("candidate_name"),
                "position_code": application.get("position_code"),
            }
    return {}


WORKFLOW_STEP_FALLBACK_LABELS = {
    "shortlist_candidate": "{name} is shortlisted",
    "send_email": "{name} was emailed",
    "notify_candidate": "{name} was notified",
    "send_interview_invite": "interview invite sent to {name}",
    "send_video_interview": "AI video interview link sent to {name}",
    "send_assessment": "assessment sent to {name}",
    "schedule_interview": "{name} is scheduled for interview",
    "hire_candidate": "{name} is marked as hired",
    "reject_candidate": "{name} is marked as rejected",
}


def _clean_reply_fragment(value: Any) -> str:
    text = str(value or "").strip()
    return text.rstrip(".。").strip()


def _workflow_step_results(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = result.get("step_results") if isinstance(result.get("step_results"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "").strip()
        step_result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if step and isinstance(step_result, dict):
            out[step] = step_result
    return out


def _workflow_step_reply(step: str, step_result: dict[str, Any], name: str) -> str:
    for key in ("safe_user_message", "message"):
        message = _clean_reply_fragment(step_result.get(key))
        if message:
            return message
    if step == "send_interview_invite":
        channel = step_result.get("notification_channel")
        if not channel and isinstance(step_result.get("result"), dict):
            channel = step_result["result"].get("notification_channel")
        if channel:
            return f"interview invite sent to {name} by {channel}"
    fallback = WORKFLOW_STEP_FALLBACK_LABELS.get(step)
    return fallback.format(name=name) if fallback else "completed"


def _first_failed_workflow_message(failed_steps: list[Any]) -> str:
    for item in failed_steps:
        if not isinstance(item, dict):
            continue
        step_result = item.get("result") if isinstance(item.get("result"), dict) else {}
        nested = step_result.get("result") if isinstance(step_result.get("result"), dict) else {}
        for payload in (step_result, nested):
            for key in ("safe_user_message", "message"):
                value = payload.get(key) if isinstance(payload, dict) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _join_reply_fragments(fragments: list[str]) -> str:
    cleaned = [_clean_reply_fragment(item) for item in fragments if _clean_reply_fragment(item)]
    if not cleaned:
        return "Done."
    if len(cleaned) == 1:
        sentence = cleaned[0]
    else:
        sentence = ", ".join(cleaned[:-1]) + " and " + cleaned[-1]
    return f"Done — {sentence}."


def _reply_for_tool_result(tool_name: str, tool_result: dict[str, Any], pending: dict[str, Any] | None = None) -> str:
    if tool_result.get("status") == "permission_denied":
        return str(tool_result.get("message") or "You do not have permission to do this action.")
    if tool_result.get("status") == "needs_confirmation":
        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
        plan = tool_result.get("preflight_plan") if isinstance(tool_result.get("preflight_plan"), dict) else {}
        preview = result.get("confirmation_preview") if isinstance(result.get("confirmation_preview"), dict) else plan.get("confirmation_preview") if isinstance(plan.get("confirmation_preview"), dict) else {}
        return str(
            result.get("confirmation_text")
            or plan.get("confirmation_text")
            or preview.get("confirmation_text")
            or result.get("message")
            or plan.get("message")
            or "Confirm to send?"
        )
    if tool_result.get("status") in {"needs_clarification", "candidate_not_found", "candidate_ambiguous", "needs_candidate_reference"}:
        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else tool_result
        return str(result.get("message") or "I need one more detail before I can do that.")
    result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
    if tool_name == "execute_candidate_workflow":
        candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
        name = candidate.get("candidate_name") or candidate.get("name") or "the candidate"
        completed = result.get("completed_steps") if isinstance(result.get("completed_steps"), list) else []
        failed = result.get("failed_steps") if isinstance(result.get("failed_steps"), list) else []
        if result.get("status") == "completed":
            step_results = _workflow_step_results(result)
            done = [_workflow_step_reply(str(step), step_results.get(str(step), {}), str(name)) for step in completed]
            return _join_reply_fragments(done)
        if completed and failed:
            failure = _first_failed_workflow_message(failed)
            if failure:
                return f"Some actions for {name} were completed, but one item needs attention: {failure}"
            return f"Some actions for {name} were completed, but one item still needs attention."
        if failed:
            failure = _first_failed_workflow_message(failed)
            if failure:
                return failure
    if result.get("safe_user_message"):
        return str(result["safe_user_message"])
    if result.get("message"):
        return str(result["message"])
    return "Done."


def _handle_pending_confirmation_if_any(request: Any, scope: dict[str, Any], state: dict[str, Any], graph_state: dict[str, Any]) -> dict[str, Any] | None:
    decision = _approval_value(getattr(request, "raw_text", ""))
    if not decision:
        return None
    pending = _find_active_pending(request, scope)
    if not pending:
        return None
    tool_name, tool_args, _plan = _pending_args(pending)
    if not tool_name:
        return None
    if decision == "rejected":
        _mark_pending_resolved(pending["action_id"], "rejected")
        return {
            "tool_outputs": [{"tool": tool_name, "status": "cancelled", "pending_action_id": str(pending.get("action_id") or "")}],
            "action_type": tool_name,
            "status": "cancelled",
            "reply": "Okay, cancelled.",
        }
    tool_result = _execute_tool(tool_name, tool_args, request, state, graph_state, scope)
    return {
        "tool_outputs": [{"tool": tool_name, **tool_result}],
        "action_type": tool_name,
        "status": tool_result.get("status") or "completed",
        "reply": _reply_for_tool_result(tool_name, tool_result, pending),
    }


def handle_toolcall_whatsapp_turn(request: Any) -> dict[str, Any]:
    legacy = _legacy()
    # Pin the tenant for this turn so every AI/WhatsApp helper read (candidate, application,
    # position, employee, role focus) is company-scoped and fails closed if missing.
    try:
        company_scope = legacy.request_company_code(request)
    except Exception:
        company_scope = None
    token = legacy.set_active_company_code(company_scope)
    try:
        return _handle_toolcall_whatsapp_turn_impl(request)
    finally:
        legacy.reset_active_company_code(token)


def _handle_toolcall_whatsapp_turn_impl(request: Any) -> dict[str, Any]:
    legacy = _legacy()
    legacy.ensure_schema()
    scope, active_state = _resolve_memory_scope(request)
    _attach_scope_to_request(request, scope)
    graph_state = legacy.create_turn({"request": request})
    turn_id = str(graph_state["turn_id"])
    state = _latest_state(request, scope, active_state)
    history = _conversation_history(request, scope, exclude_turn_id=turn_id)
    state_summary = _build_state_summary(state, request, scope)
    tools = _visible_tools(_registry.build_tool_schemas(legacy, request), scope)

    _save_state(turn_id, {"scope_init": _now_iso(), "summary": state_summary}, scope)

    pending_resume = _handle_pending_confirmation_if_any(request, scope, state, graph_state)
    if pending_resume:
        tool_outputs = pending_resume["tool_outputs"]
        final_reply = pending_resume["reply"]
        last_action_type = pending_resume["action_type"]
        last_status = pending_resume["status"]
        audit_payload = {
            "graph": TOOLCALL_GRAPH_VERSION,
            "state_summary": state_summary,
            "tool_outputs": tool_outputs,
            "messages_count": 0,
            "context_assembly": {
                "history_messages": len(history),
                "scope_policy": "same_company_admin_conversation_channel_module_session_only",
                "pending_confirmation_resumed_by_backend": True,
            },
        }
        _record_turn_result(turn_id, last_action_type, last_status, audit_payload, final_reply, scope)
        focus = _candidate_focus_from_tool_calls(tool_outputs) or _module_focus(state, scope) or {}
        focus_by_module = state.get("current_focus_by_module") if isinstance(state.get("current_focus_by_module"), dict) else {}
        focus_by_module = {**focus_by_module, scope["module"]: focus}
        _save_state(
            turn_id,
            {
                "current_focus": focus,
                "current_focus_by_module": focus_by_module,
                "last_tool_outputs": _json_safe(tool_outputs[-3:]),
                "updated_at": _now_iso(),
                "graph": TOOLCALL_GRAPH_VERSION,
            },
            scope,
        )
        return {
            "authoritative": True,
            "reply_text": final_reply,
            "final_reply_source": "toolcall_orchestrator",
            "intent": last_action_type,
            "turn_focus": "toolcall_dialog",
            "pending_action": None,
            "audit": {
                "turn_id": turn_id,
                "graph": TOOLCALL_GRAPH_VERSION,
                "tool_outputs": _json_safe(tool_outputs),
                "state_summary": _json_safe(state_summary),
                "memory_scope": _json_safe(scope),
            },
        }

    messages = _build_messages(request, state, state_summary, history)
    instructions, input_items = _split_system_and_input(messages)
    responses_tools = _convert_tools_for_responses(tools)
    forced_tool_name = _forced_tool_for_turn(request, tools)
    reasoning_effort = _reasoning_effort_for_request(request)
    tool_outputs: list[dict[str, Any]] = []
    tool_sequence: list[str] = []
    executed_call_ids: set[str] = set()
    final_reply = ""
    last_action_type = "direct_reply"
    last_status = "completed"
    previous_response_id: str | None = None
    turn_started = time_module.monotonic()
    cancelled = False

    for step in range(MAX_TOOL_LOOPS):
        if (time_module.monotonic() - turn_started) >= TOOLCALL_TURN_BUDGET_SEC:
            final_reply = "That took too long to finish. Try again with a shorter request."
            last_status = "cancelled"
            cancelled = True
            break
        parsed = _call_responses_with_tools(
            instructions=instructions,
            input_items=input_items,
            tools=responses_tools,
            turn_id=turn_id,
            step=step,
            reasoning_effort=reasoning_effort,
            forced_tool_name=forced_tool_name if step == 0 else None,
            previous_response_id=None,
            tool_sequence=tool_sequence,
        )
        if not parsed:
            final_reply = "I had trouble reaching the model. Try again in a moment."
            last_status = "failed"
            break
        previous_response_id = str(parsed.get("id") or "") or previous_response_id
        tool_calls = _extract_responses_tool_calls(parsed)
        content = _extract_responses_text(parsed)
        if not tool_calls:
            final_reply = str(content).strip() or "I'm here. What would you like to check?"
            last_action_type = tool_outputs[-1].get("tool") if tool_outputs else "direct_reply"
            break

        # Continue the same Responses flow: feed model output items (incl. reasoning) + tool outputs.
        input_items.extend(_continuation_items_from_response(parsed))
        outputs_for_step: list[dict[str, Any]] = []
        for call in tool_calls:
            call_id = str(call.get("id") or "")
            tool_name = str(call.get("name") or "")
            tool_args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            if call_id and call_id in executed_call_ids:
                # Idempotent: never re-execute the same Responses tool call on retry/continuation.
                cached = next((o for o in tool_outputs if o.get("id") == call_id), None)
                output_payload = cached or {
                    "id": call_id,
                    "tool": tool_name,
                    "status": "duplicate_skipped",
                    "result": {"safe_user_message": "Already executed."},
                }
            else:
                tool_result = _execute_tool(tool_name, tool_args, request, state, graph_state, scope)
                output_payload = {"id": call_id, "tool": tool_name, **tool_result}
                if call_id:
                    executed_call_ids.add(call_id)
                tool_sequence.append(tool_name)
            outputs_for_step.append(output_payload)
            last_action_type = tool_name
            last_status = output_payload.get("status") or "completed"
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {k: v for k, v in output_payload.items() if k != "id"},
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )
        tool_outputs.extend(outputs_for_step)
        if step == MAX_TOOL_LOOPS - 1:
            final_reply = "I ran out of steps reasoning about that. Try rephrasing the request."
            last_status = "failed"

    if tool_outputs and not cancelled:
        last_output = tool_outputs[-1]
        status_for_reply = str(last_output.get("status") or "").lower()
        result_for_reply = last_output.get("result") if isinstance(last_output.get("result"), dict) else {}
        if (
            status_for_reply in {"needs_confirmation", "failed", "partial", "permission_denied"}
            or str(last_output.get("tool") or "").startswith("execute_candidate_")
            or result_for_reply.get("safe_user_message")
        ):
            final_reply = _reply_for_tool_result(str(last_output.get("tool") or ""), last_output)

    audit_payload = {
        "graph": TOOLCALL_GRAPH_VERSION,
        "state_summary": state_summary,
        "tool_outputs": tool_outputs,
        "messages_count": len(input_items),
        "api": "openai-responses",
        "model": (_toolcall_provider_config() or {}).get("model"),
        "reasoning_effort": reasoning_effort,
        "tool_sequence": tool_sequence,
        "previous_response_id": previous_response_id,
        "context_assembly": {
            "history_messages": len(history),
            "scope_policy": "same_company_admin_conversation_channel_module_session_only",
            "fresh_session_opener": _is_fresh_session_opener(getattr(request, "raw_text", "")),
            "cancelled": cancelled,
        },
    }
    _record_turn_result(turn_id, last_action_type, last_status, audit_payload, final_reply, scope)
    focus = _candidate_focus_from_tool_calls(tool_outputs) or _module_focus(state, scope) or {}
    focus_by_module = state.get("current_focus_by_module") if isinstance(state.get("current_focus_by_module"), dict) else {}
    focus_by_module = {**focus_by_module, scope["module"]: focus}
    saved_state = {
        "current_focus": focus,
        "current_focus_by_module": focus_by_module,
        "last_tool_outputs": _json_safe(tool_outputs[-3:]),
        "updated_at": _now_iso(),
        "graph": TOOLCALL_GRAPH_VERSION,
        "reasoning_effort": reasoning_effort,
        "tool_sequence": tool_sequence,
    }
    _save_state(turn_id, saved_state, scope)
    return {
        "authoritative": True,
        "reply_text": final_reply,
        "final_reply_source": "toolcall_orchestrator",
        "intent": last_action_type,
        "turn_focus": "toolcall_dialog",
        "pending_action": None,
        "audit": {
            "turn_id": turn_id,
            "graph": TOOLCALL_GRAPH_VERSION,
            "tool_outputs": _json_safe(tool_outputs),
            "state_summary": _json_safe(state_summary),
            "memory_scope": _json_safe(scope),
            "api": "openai-responses",
            "reasoning_effort": reasoning_effort,
            "tool_sequence": tool_sequence,
            "model": (_toolcall_provider_config() or {}).get("model"),
        },
    }
