"""Canonical action registry for the Wathefni HR orchestrator.

Single source of truth for:
- Which HR actions GPT is allowed to choose (SUPPORTED_INTENTS).
- Which fields each action requires before execution.
- Which actions need explicit user confirmation before mutating state.
- Which executor function actually runs the action against the backend.
- The shape of the ActionResult produced for renderer consumption.

Design rules:
- Adding a capability anywhere in the system (intent list, prompt docs, executor switch, OpenAI tool schema, confirmation policy) must come through this registry.
- If an action is registered but has no executor, startup must fail loudly, not at the moment a user hits it from WhatsApp.
- If an action is registered but its required fields are not present at execution time, the registry returns a needs_clarification result instead of running the executor.
- All live HR-admin tools must be registered here; no parallel intent/executor switch should expose a capability outside this registry.
"""

from __future__ import annotations

import logging
import os
import re
import json
from urllib.parse import quote_plus
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Callable, Optional, Union

logger = logging.getLogger("wathefni.action_registry")


ExecutorCallable = Callable[["ExecutionContext"], dict[str, Any]]
ConfirmationRule = Union[bool, Callable[[dict[str, Any]], bool]]
ParametersCatalogLoader = Callable[[Any, Any], dict[str, Any]]


@dataclass
class ExecutionContext:
    """Container passed to executors. Keeps executors decoupled from FastAPI internals."""

    request: Any
    action: dict[str, Any]
    state: dict[str, Any]
    graph_state: dict[str, Any]
    intent: dict[str, Any]
    legacy: Any


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    entity_type: Optional[str] = None
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    module: Optional[str] = None
    requires_confirmation: ConfirmationRule = False
    executor: Optional[ExecutorCallable] = None
    preflight: Optional[ExecutorCallable] = None
    result_keys: tuple[str, ...] = ("action_type", "success", "status", "message")
    sensitive: bool = False
    notes: str = ""
    # Loader returning the live vocabulary for this action's parameters (positions,
    # statuses, modules, etc.). The intent interpreter sees this so GPT picks a real
    # value from your DB rather than inventing one.
    parameters_catalog_loader: Optional[ParametersCatalogLoader] = None


REGISTRY: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> ActionSpec:
    if spec.name in REGISTRY:
        raise ValueError(f"Duplicate action registration: {spec.name}")
    REGISTRY[spec.name] = spec
    return spec


def registered_intents() -> list[str]:
    return sorted(REGISTRY.keys())


def is_registered(name: str | None) -> bool:
    return bool(name) and str(name) in REGISTRY


def spec_for(name: str | None) -> ActionSpec | None:
    return REGISTRY.get(str(name or ""))


def requires_confirmation(name: str | None, action: dict[str, Any]) -> bool:
    spec = spec_for(name)
    if not spec:
        return False
    rule = spec.requires_confirmation
    if callable(rule):
        try:
            return bool(rule(action))
        except Exception:
            logger.warning("requires_confirmation callable for %s raised; defaulting to True", name)
            return True
    return bool(rule)


def missing_required_fields(name: str | None, action: dict[str, Any]) -> list[str]:
    spec = spec_for(name)
    if not spec:
        return []
    out: list[str] = []
    for field_name in spec.required_fields:
        value = action.get(field_name)
        if value in (None, "", [], {}):
            out.append(field_name)
    return out


def _candidate_reference_properties() -> dict[str, Any]:
    """Reusable JSON-Schema properties GPT uses to point at a candidate.

    The orchestrator resolves these to a concrete app_key before invoking the
    executor. GPT can supply any combination; resolution prefers app_key, then
    email, then name + phone.
    """

    return {
        "candidate_app_key": {
            "type": "string",
            "description": "Resolved application key like '96597485758-WATHEFNI-HR'. Use when you know it from prior state. Otherwise use candidate_name.",
        },
        "candidate_name": {
            "type": "string",
            "description": "Candidate name as the user referenced (first name, full name, or 'him'/'her' resolved from conversation_history).",
        },
        "candidate_email": {
            "type": "string",
            "description": "Candidate email if the user provided one.",
        },
        "candidate_phone": {
            "type": "string",
            "description": "Candidate phone digits if the user provided one.",
        },
    }


def _properties_for_field(name: str, catalog: dict[str, Any] | None) -> dict[str, Any]:
    if catalog and isinstance(catalog.get(name), list):
        return {
            "type": "string",
            "enum": list(catalog[name]),
            "description": f"Must be one of the catalog values for {name}. If the user's wording does not match any value, omit this and put their wording in query.",
        }
    descriptions = {
        "query": {"type": "string", "description": "Free-text query for semantic ranking (skills, traits, role keywords). Used when the user's wording does not match the position/status catalog."},
        "top_n": {"type": "integer", "minimum": 1, "maximum": 10, "description": "How many results to return."},
        "reason": {"type": "string", "description": "Optional short reason for the action."},
        "email_subject": {"type": "string", "description": "Email subject line."},
        "message_text": {"type": "string", "description": "Message body or freeform message text."},
        "purpose": {"type": "string", "description": "Email purpose (e.g. 'shortlisted', 'interview_invite')."},
        "interview_id": {"type": "string", "description": "Canonical interview_id when referring to a specific scheduled interview."},
        "preferred_channel": {"type": "string", "enum": ["email", "whatsapp"], "description": "Preferred delivery channel for an invite or reminder."},
        "batch_action_type": {"type": "string", "enum": ["send_video_interview", "send_assessment", "send_screening_questions", "send_interview_invite", "notify_candidate", "send_email", "shortlist_candidate"], "description": "Atomic candidate action to run once per selected candidate in a batch."},
        "candidate_app_keys": {"type": "array", "items": {"type": "string"}, "description": "Resolved application keys for every candidate in the batch."},
        "candidate_names": {"type": "array", "items": {"type": "string"}, "description": "Candidate names mentioned by HR when multiple named candidates are requested."},
        "mixed_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "enum": ["send_video_interview", "send_assessment", "send_screening_questions", "send_interview_invite", "notify_candidate", "send_email", "shortlist_candidate"]},
                    "candidate_app_key": {"type": "string"},
                    "candidate_name": {"type": "string"},
                    "candidate_email": {"type": "string"},
                    "candidate_phone": {"type": "string"},
                    "message_text": {"type": "string"},
                    "preferred_channel": {"type": "string", "enum": ["email", "whatsapp"]},
                },
                "additionalProperties": True,
            },
            "description": "Per-candidate mixed batch items. Use one object per requested candidate/action pair.",
        },
        "interview_time": {"type": "string", "description": "Natural-language or ISO datetime ('tomorrow at 4pm' or '2026-05-15T16:00')."},
        "when": {"type": "string", "description": "Alias for interview_time."},
        "datetime": {"type": "string", "description": "Alias for interview_time."},
        "question": {"type": "string", "description": "Specific question the user asked about the candidate."},
        "based_on_cv": {"type": "boolean", "description": "Set true if the user explicitly asked you to judge from the CV."},
        "workflow_goal": {"type": "string", "description": "The user's business goal in plain language, e.g. 'shortlist and invite to online interview'."},
        "steps": {
            "type": "array",
            "items": {"type": "string", "enum": ["shortlist_candidate", "hire_candidate", "reject_candidate", "send_email", "notify_candidate", "send_interview_invite", "send_video_interview", "send_assessment", "send_screening_questions", "schedule_interview"]},
            "description": "Ordered atomic registry actions to compose into one workflow. Use this for multi-step candidate requests instead of calling sensitive tools separately.",
        },
        "invite_channel": {"type": "string", "enum": ["email", "whatsapp"], "description": "Preferred candidate invite channel. Use whatsapp when email is missing or the user asks for WhatsApp."},
        "fallback_channel": {"type": "string", "enum": ["whatsapp", "none"], "description": "Fallback channel if invite_channel cannot be used."},
        "allow_fallback": {"type": "boolean", "description": "True only when the user explicitly allowed fallback behavior, e.g. WhatsApp instead of email."},
        "meeting_type": {"type": "string", "enum": ["google_meet", "none"], "description": "Use google_meet when the user asks for online/Google Meet interview."},
        "datetime_text": {"type": "string", "description": "Natural-language meeting time if provided, e.g. 'tomorrow at 9pm'."},
        "title": {"type": "string", "description": "Job opening title, e.g. 'Computer Science' or 'IT Maintenance'."},
        "position_code": {"type": "string", "description": "Canonical uppercase job code. If omitted, backend derives it from title."},
        "salary_min": {"type": "number", "description": "Minimum monthly salary in KD."},
        "salary_max": {"type": "number", "description": "Maximum monthly salary in KD."},
        "salary": {"type": "number", "description": "Monthly salary in KD when only one salary number is provided."},
        "currency": {"type": "string", "description": "Salary currency, default KD."},
        "employment_type": {"type": "string", "description": "Full-time, part-time, internship, contract, etc."},
        "description": {"type": "string", "description": "Short job description if provided."},
        "requirements": {"type": "array", "items": {"type": "string"}, "description": "Job requirements or qualifications."},
        "employee_name": {"type": "string", "description": "Employee name as the user referenced them."},
        "employee_phone": {"type": "string", "description": "Employee phone digits if the user provided one."},
        "leave_id": {"type": "string", "description": "Canonical leave_id when the user refers to a specific leave request you already saw."},
        "leave_type": {"type": "string", "description": "Leave type if stated: sick, vacation, or time_off. Omit if unstated."},
        "decision_note": {"type": "string", "description": "Optional short note explaining the approval/rejection decision."},
        "status": {"type": "string", "description": "Status filter or target value when stated (e.g. leave: requested/approved/rejected/cancelled; attendance: present/late/absent/completed; timesheet: pending/approved/rejected). Omit to list all."},
        "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD) or natural-language day. Omit if not stated; the backend infers the period."},
        "end_date": {"type": "string", "description": "End date (YYYY-MM-DD) or natural-language day. Omit for a single day."},
        "date": {"type": "string", "description": "A single day (YYYY-MM-DD) or natural-language day the action applies to. Omit to default to today."},
        "time": {"type": "string", "description": "A clock time (e.g. '09:15') if the user stated one for a check-in/out or correction. Omit otherwise."},
        "notes": {"type": "string", "description": "Optional short free-text note/reason the user provided for this action."},
        "shift_id": {"type": "string", "description": "Canonical shift_id when the user refers to a specific shift you already saw. Omit otherwise."},
        "shift_date": {"type": "string", "description": "Shift date (YYYY-MM-DD) or natural-language day for a scheduling action."},
        "start_time": {"type": "string", "description": "Shift start time (e.g. '09:00') when scheduling."},
        "end_time": {"type": "string", "description": "Shift end time (e.g. '17:00') when scheduling."},
        "swap_id": {"type": "string", "description": "Canonical swap_id when the user refers to a specific shift swap request you already saw."},
        "timesheet_id": {"type": "string", "description": "Canonical timesheet_id when the user refers to a specific timesheet you already saw."},
        "metric": {"type": "string", "description": "The workforce metric the user asked about (e.g. headcount, attendance rate, overtime, turnover). Omit if unclear."},
        "document_type": {"type": "string", "description": "Compliance document type when the user named one: civil_id, passport, residency, work_permit, medical, education_cert. Omit to cover all of the employee's outstanding documents."},
    }
    return descriptions.get(name, {"type": "string", "description": f"{name} value"})


# Tools that are only exposed to the LLM when their dark-launch flag (a no-arg
# predicate on the app/legacy module) returns True. Default behaviour without a
# flag entry is "always exposed".
_FLAG_GATED_TOOLS: dict[str, str] = {
    "list_onboarding_status": "assistant_hr_reads_enabled",
    "list_compliance_documents": "assistant_hr_reads_enabled",
}


def build_tool_schemas(legacy: Any, request: Any) -> list[dict[str, Any]]:
    """Generate OpenAI-style tool schemas from the registry.

    Tool schemas are the single source of truth that GPT sees: descriptions,
    required fields, enums from live parameters_catalog. If you add a tool to
    the registry, GPT can use it on the next request. If you delete it, GPT
    loses access. There is no parallel intent list to maintain.
    """

    tools: list[dict[str, Any]] = []
    for name, spec in REGISTRY.items():
        if not spec.executor:
            continue
        # Dark-launch gate: some tools are only offered to the LLM when their
        # feature flag is on (default OFF). Keeps the catalog inert in production
        # until the flag is enabled, so tool-selection behaviour is unchanged.
        gate = _FLAG_GATED_TOOLS.get(name)
        if gate is not None:
            checker = getattr(legacy, gate, None)
            if not (callable(checker) and checker()):
                continue
        catalog: dict[str, Any] | None = None
        if spec.parameters_catalog_loader is not None:
            try:
                catalog = spec.parameters_catalog_loader(legacy, request)
            except Exception:
                catalog = None
        properties: dict[str, Any] = {}
        required_input: list[str] = []
        if spec.entity_type == "candidate":
            properties.update(_candidate_reference_properties())
        for field_name in spec.required_fields:
            if field_name == "app_key":
                # Already represented via the candidate_* reference fields.
                continue
            properties[field_name] = _properties_for_field(field_name, catalog)
            required_input.append(field_name)
        for field_name in spec.optional_fields:
            if field_name == "app_key" or field_name in properties:
                continue
            properties[field_name] = _properties_for_field(field_name, catalog)
        # Inventory tools must not expose free-text query (prevents accidental filters).
        if (
            "query" not in properties
            and spec.entity_type is None
            and name not in {"list_job_openings"}
        ):
            properties["query"] = _properties_for_field("query", catalog)
        confirmation_hint = ""
        if (isinstance(spec.requires_confirmation, bool) and spec.requires_confirmation) or callable(spec.requires_confirmation):
            if spec.preflight is not None:
                confirmation_hint = (
                    " PREFLIGHT-THEN-CONFIRM: call this tool before confirmation so the backend can validate the plan, "
                    "detect missing fields, and find blocked steps. The backend will not execute mutations until a later explicit user confirmation."
                )
            else:
                confirmation_hint = " SENSITIVE: ask the user to confirm in your own words before calling this. Do not call it unprompted; only call after the user has explicitly agreed."
        description = spec.description + confirmation_hint
        if catalog and isinstance(catalog.get("policy"), str):
            description = description + " " + catalog["policy"]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_input,
                        "additionalProperties": True,
                    },
                },
            }
        )
    return tools


def resolve_candidate_reference(legacy: Any, args: dict[str, Any]) -> dict[str, Any] | None:
    """Back-compat shim: returns the application row when a single confident match exists, else None.

    New callers should use resolve_candidate_typed(legacy, args) to get the full typed result
    (resolved | ambiguous | not_found | no_input) so they can give GPT a clear instruction.
    """

    result = resolve_candidate_typed(legacy, args)
    if result["status"] == "resolved" and result.get("matches"):
        return result["matches"][0]
    return None


def resolve_candidate_typed(legacy: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Translate GPT's candidate_* tool args into a typed resolver result.

    Returns:
      {
        "status": "resolved" | "ambiguous" | "not_found" | "no_input",
        "matches": [application rows],
        "alternates": [other plausible matches],
        "searched": {what we searched on},
      }

    Uses app.resolve_candidate() when available (canonical, fuzzy, never silently 'latest').
    Falls back to legacy.resolve_application_for_action with allow_latest=False otherwise.
    """

    app_key = args.get("candidate_app_key") or args.get("app_key") or args.get("subject_key")
    name = args.get("candidate_name") or args.get("subject_name") or args.get("name")
    email = args.get("candidate_email")
    phone = args.get("candidate_phone") or args.get("subject_phone") or args.get("phone")
    company_code = args.get("company_code")

    if hasattr(legacy, "resolve_candidate"):
        try:
            return legacy.resolve_candidate(
                app_key=app_key,
                phone=phone,
                email=email,
                name=name,
                company_code=company_code,
            )
        except Exception:
            pass
    if not (app_key or name or email or phone):
        return {"status": "no_input", "matches": [], "searched": {}}
    searched = {k: v for k, v in {"app_key": app_key, "name": name, "email": email, "phone": phone}.items() if v}
    if app_key and hasattr(legacy, "find_application_by_key"):
        try:
            row = legacy.find_application_by_key(str(app_key), company_code=company_code)
            if row:
                return {"status": "resolved", "matches": [row], "searched": searched}
            if company_code:
                return {"status": "not_found", "matches": [], "searched": searched}
        except Exception:
            pass
    lookup = {
        "app_key": app_key,
        "subject_key": app_key,
        "subject_name": name,
        "subject_phone": phone,
        "email": email,
        "company_code": company_code,
    }
    try:
        row = legacy.resolve_application_for_action(lookup, allow_latest=False)
    except Exception:
        row = None
    if row:
        return {"status": "resolved", "matches": [row], "searched": searched}
    return {"status": "not_found", "matches": [], "searched": searched}


def validate_registry(strict: bool = True) -> list[str]:
    """Validate that every registered action has the metadata required for safe execution.

    When strict=True (the default), the function raises RuntimeError. This is intended to
    run at process startup so a misconfigured registry blocks the server from accepting traffic.
    """

    errors: list[str] = []
    for name, spec in REGISTRY.items():
        if not spec.executor:
            errors.append(f"Action '{name}' has no executor")
        if not spec.description:
            errors.append(f"Action '{name}' has no description")
        for fld in spec.required_fields:
            if not isinstance(fld, str) or not fld:
                errors.append(f"Action '{name}' has invalid required_fields entry: {fld!r}")
        rule = spec.requires_confirmation
        if not isinstance(rule, bool) and not callable(rule):
            errors.append(f"Action '{name}' has invalid requires_confirmation rule: {rule!r}")
    if errors:
        message = "Action registry validation failed:\n  - " + "\n  - ".join(errors)
        logger.critical(message)
        if strict:
            raise RuntimeError(message)
    return errors


def validate_result(name: str, result: dict[str, Any]) -> dict[str, Any]:
    spec = spec_for(name)
    out = dict(result or {})
    out.setdefault("action_type", name)
    if "success" not in out:
        out["success"] = out.get("status") == "completed"
    out.setdefault("status", "completed" if out.get("success") else "failed")
    out.setdefault("message", "")
    if spec:
        for key in spec.result_keys:
            out.setdefault(key, None)
    return out


def execute(name: str, ctx: ExecutionContext) -> dict[str, Any]:
    spec = spec_for(name)
    if not spec or not spec.executor:
        return {
            "action_type": name,
            "success": False,
            "status": "failed",
            "message": f"No executor registered for {name}.",
            "error": "missing_registered_executor",
        }
    missing = missing_required_fields(name, ctx.action)
    if missing:
        nice_fields = ", ".join(missing)
        return {
            "action_type": name,
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_required_fields": missing,
            "message": f"I need {nice_fields} before I can run {name.replace('_', ' ')}.",
        }
    try:
        raw_result = spec.executor(ctx)
    except Exception as exc:
        logger.exception("Executor for %s raised", name)
        return {
            "action_type": name,
            "success": False,
            "status": "failed",
            "message": "The action did not complete. Please try again.",
            "error": str(exc)[:500],
        }
    return validate_result(name, raw_result)


def _legacy_execute(ctx: ExecutionContext) -> dict[str, Any]:
    """Run an action through the legacy app.execute_direct_action helper.

    We use this for actions whose backend implementation already lives in app.py
    and which legacy does NOT gate behind its own confirmation prompt — otherwise
    v2 (which has already gathered confirmation) and legacy would double-prompt.

    The registry still owns the contract (required fields, confirmation policy,
    intent name, description) so GPT and the executor stay in sync.
    """

    legacy = ctx.legacy
    graph_state = {
        **ctx.graph_state,
        "direct_action": ctx.action,
        "intent": ctx.action.get("action_type"),
        "turn_focus": "registry_action_execution",
    }
    result_state = legacy.execute_direct_action(graph_state)
    return {
        "action_type": str(ctx.action.get("action_type") or ""),
        "success": bool(result_state.get("authoritative")),
        "status": "completed" if result_state.get("authoritative") else "failed",
        "message": result_state.get("reply_text"),
        "final_reply_source": result_state.get("final_reply_source"),
        "legacy_state": legacy.json_safe(
            {
                "authoritative": result_state.get("authoritative"),
                "reply_text": result_state.get("reply_text"),
                "final_reply_source": result_state.get("final_reply_source"),
                "pending_action": result_state.get("pending_action"),
                "persistent_context": result_state.get("persistent_context"),
            }
        ),
    }


def _resolve_app(ctx: ExecutionContext) -> dict[str, Any] | None:
    return ctx.legacy.resolve_application_for_action(ctx.action, allow_latest=False)


CV_TEXT_MAX_CHARS = 6000


def _load_candidate_cv_text(legacy: Any, app_key: str) -> str | None:
    """Return the latest indexed CV / application text for a candidate.

    Bounded to CV_TEXT_MAX_CHARS so the renderer prompt stays inside the token
    budget. Returns None on any failure so callers degrade gracefully — the
    renderer can still reason from the structured fields.
    """

    if not app_key:
        return None
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content FROM semantic_documents WHERE entity_type='application' AND entity_key=%s ORDER BY updated_at DESC NULLS LAST LIMIT 1",
                    (str(app_key),),
                )
                row = cur.fetchone()
    except Exception:
        return None
    if not row:
        return None
    content = row.get("content") if isinstance(row, dict) else (row[0] if isinstance(row, (list, tuple)) and row else None)
    text = str(content or "").strip()
    return text[:CV_TEXT_MAX_CHARS] if text else None


def _prior_ranking_for(state: dict[str, Any], app_key: str) -> dict[str, Any]:
    """Look up this candidate in the previous rank_candidates result, if any.

    Lets single-candidate questions ("is he good?") inherit the ranking score and
    reasons we already computed during the last rank_candidates turn, instead of
    starting from zero.
    """

    if not isinstance(state, dict) or not app_key:
        return {}
    last = state.get("last_action_result") if isinstance(state.get("last_action_result"), dict) else {}
    candidates_pool: list[Any] = []
    candidates = last.get("candidates") if isinstance(last.get("candidates"), list) else None
    if candidates:
        candidates_pool.extend(candidates)
    result_payload = last.get("result") if isinstance(last.get("result"), dict) else {}
    nested = result_payload.get("candidates") if isinstance(result_payload.get("candidates"), list) else None
    if nested:
        candidates_pool.extend(nested)
    for candidate in candidates_pool:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("app_key") or "") != str(app_key):
            continue
        return {
            "ranking_score": candidate.get("score") or candidate.get("ranking_score"),
            "ranking_reasons": candidate.get("reasons") or candidate.get("evidence"),
            "ranking_confidence": candidate.get("confidence"),
            "matched_terms": candidate.get("matched_terms"),
        }
    return {}


def _resolve_company_code(legacy: Any, request: Any) -> str | None:
    if hasattr(legacy, "request_company_code"):
        try:
            return legacy.request_company_code(request)
        except Exception:
            return None
    return None


def _load_candidate_context(
    legacy: Any,
    app: dict[str, Any] | None,
    action: dict[str, Any],
    state: dict[str, Any],
    request: Any,
) -> dict[str, Any]:
    """Single source of truth for candidate context across registry executors.

    Returns a structured dict that the GPT renderer treats as if it just read the
    CV itself. Never include this dict verbatim in user-facing replies — the
    renderer prompt explicitly forbids dumping the CV body.
    """

    if not isinstance(app, dict) or not app.get("app_key"):
        return {}
    app_key = str(app.get("app_key"))
    company_code = _resolve_company_code(legacy, request)
    item: dict[str, Any] = {}
    strengths: list[str] = []
    gaps: list[str] = []
    try:
        item = legacy.compare_candidate_item({"app_key": app_key}, company_code=company_code) or {}
    except Exception:
        item = {}
    try:
        strengths, gaps = legacy.candidate_strengths_and_gaps(item) if item else ([], [])
    except Exception:
        strengths, gaps = [], []
    cv_text = _load_candidate_cv_text(legacy, app_key)
    prior = _prior_ranking_for(state, app_key)
    return {
        "app_key": app_key,
        "name": item.get("name") or app.get("candidate_name") or action.get("subject_name"),
        "job": item.get("job") or app.get("position_title") or app.get("position_code"),
        "stage": item.get("stage") or app.get("status"),
        "current_step": item.get("current_step"),
        "cv_status": item.get("cv_status") or ("received" if app.get("cv_received") else "unknown"),
        "cv_text": cv_text,
        "ranking_score_current": item.get("ranking_score"),
        "assessment_status": item.get("assessment_status"),
        "assessment_score": item.get("assessment_score"),
        "notes": item.get("notes"),
        "last_activity": item.get("last_activity"),
        "strengths": strengths,
        "gaps": gaps,
        "prior_turn_ranking": prior,
    }


def _candidate_name(app: dict[str, Any] | None, action: dict[str, Any]) -> str:
    if isinstance(app, dict) and app.get("candidate_name"):
        return str(app.get("candidate_name"))
    return str(action.get("subject_name") or "the candidate")


def _candidate_not_found_result(name: str, label: str) -> dict[str, Any]:
    return {
        "action_type": name,
        "success": False,
        "status": "failed",
        "message": f"I could not find the candidate to {label}.",
        "error": "candidate_not_found",
    }


def _status_mutation_executor(target_status: str, success_label: str, failure_label: str) -> ExecutorCallable:
    """Build an executor that moves a candidate to a new application status.

    Used for shortlist/reject. Bypasses legacy's own confirmation gate because
    v2 has already gathered explicit user confirmation via the action-plan flow.
    (Hire has its own executor — see _hire_candidate_executor — because hiring
    must also run the post-hire transition that creates the employee record.)
    """

    def executor(ctx: ExecutionContext) -> dict[str, Any]:
        legacy = ctx.legacy
        app = _resolve_app(ctx)
        action_type = str(ctx.action.get("action_type") or "")
        if not app:
            return _candidate_not_found_result(action_type, success_label.lower())
        # AI never executes autonomously: confirmation was already collected by the
        # orchestrator before this executor runs. Still refuse if actor is marked AI
        # without human_confirmed on the action payload.
        actor_type = str(ctx.action.get("actor_type") or "human")
        human_confirmed = bool(ctx.action.get("human_confirmed", False))
        meta = getattr(ctx.request, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        permissions = meta.get("permissions") or []
        if isinstance(permissions, dict):
            permissions = list(permissions.keys())
        company = str(app.get("company_code") or "").strip().upper()
        if not company:
            return {
                "action_type": action_type,
                "success": False,
                "status": "failed",
                "error": "tenant_scope_required",
                "message": "The candidate company scope is missing.",
            }
        action_name = "shortlist" if target_status == "shortlisted" else "reject"
        confirmation_payload = ctx.action.get("confirmation_payload")
        if not isinstance(confirmation_payload, dict):
            confirmation_payload = {}
        update = legacy.update_application_status(
            app,
            target_status,
            trigger=action_type or f"registry_{target_status}",
            human_confirmed=human_confirmed,
            actor_type="ai" if actor_type == "ai" else "human",
            actor_user_id=str(ctx.action.get("actor_user_id") or meta.get("actor_user_id") or "") or None,
            actor_phone=getattr(ctx.request, "sender_phone", None),
            channel="whatsapp" if not meta.get("dashboard") else "web",
            permissions=set(permissions),
            expected_from_stage=str(ctx.action.get("expected_from_stage") or "") or None,
            expected_version=ctx.action.get("expected_version"),
            confirmation_id=str(ctx.action.get("confirmation_id") or "") or None,
            confirmation_token=str(ctx.action.get("confirmation_token") or "") or None,
            confirmation_action=str(ctx.action.get("confirmation_action") or action_name),
            confirmation_payload=confirmation_payload,
            idempotency_key=str(ctx.action.get("idempotency_key") or "") or None,
            metadata=confirmation_payload,
        )
        ok = bool(update.get("ok") if isinstance(update, dict) else False)
        name = _candidate_name(app, ctx.action)
        return {
            "action_type": action_type,
            "success": ok,
            "status": "completed" if ok else "failed",
            "message": f"{name} {success_label}." if ok else f"I could not {failure_label} {name}.",
            "application": legacy.json_safe(app),
            "update": legacy.json_safe(update),
            "candidate_status": target_status if ok else app.get("status"),
            "error": update.get("error") if isinstance(update, dict) and not ok else None,
        }

    return executor


def _hire_candidate_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Hire a candidate: mark the application hired AND run the post-hire
    transition that creates/links the employee record and starts the post-hire
    chain.

    This is the single shared hire path for BOTH the Wathefni Assistant and the
    dashboard Hire button, so hiring is always consistent: status -> hired,
    transition_hire -> employee created, post-hire setup begun. (Previously the
    registry hire only updated status, which would have left the Assistant and
    the dashboard inconsistent.)
    """
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    action_type = str(ctx.action.get("action_type") or "hire_candidate")
    if not app:
        return _candidate_not_found_result(action_type, "hire")
    meta = getattr(ctx.request, "metadata", {}) or {}
    if not isinstance(meta, dict):
        meta = {}
    permissions = list(meta.get("permissions") or [])
    # Offer-1 hire gate: when employment_offers is enabled, accepted offer is required.
    # AI must never pass hire_override (never available to AI).
    try:
        import offer_service as _offer_service
        import offer_lifecycle as _offers

        actor_type = "human"
        if str((meta.get("actor_type") if isinstance(meta, dict) else "") or "").lower() == "ai" or (
            isinstance(meta, dict) and meta.get("ai_actor")
        ):
            actor_type = "ai"
        hire_override = bool(ctx.action.get("hire_override") or (isinstance(meta, dict) and meta.get("hire_override")))
        if actor_type == "ai":
            hire_override = False
        # Assistant/tool paths must never pass override: strip unless explicit human dashboard confirm.
        if hire_override and not (
            isinstance(meta, dict)
            and (meta.get("dashboard") or meta.get("hire_override_confirmed"))
            and (ctx.action.get("confirm") or meta.get("confirm") or meta.get("hire_override_confirmed"))
        ):
            hire_override = False
        company_code = str(app.get("company_code") or (meta.get("company_code") if isinstance(meta, dict) else "") or "")
        if not company_code:
            return {
                "action_type": action_type,
                "success": False,
                "status": "failed",
                "error": "tenant_scope_required",
                "message": "The candidate company scope is missing.",
            }
        actor_user_id = str((meta.get("actor_user_id") if isinstance(meta, dict) else "") or "") or None
        actor_subject = str(
            (meta.get("actor_subject") if isinstance(meta, dict) else "")
            or (meta.get("permission_subject_user_id") if isinstance(meta, dict) else "")
            or actor_user_id
            or ""
        ) or None
        _offer_service.enforce_hire_gate(
            legacy,
            company_code=company_code,
            app_key=str(app.get("app_key") or ""),
            permissions=set(permissions),
            hire_override=hire_override and actor_type == "human",
            override_reason=str(ctx.action.get("override_reason") or (meta.get("override_reason") if isinstance(meta, dict) else "") or "")
            or None,
            actor_user_id=actor_user_id,
            actor_subject=actor_subject,
            actor_type=actor_type,
            confirmation_token=str(
                ctx.action.get("confirmation_id")
                or (meta.get("confirmation_id") if isinstance(meta, dict) else "")
                or ""
            )
            or None,
            confirmed=bool(
                ctx.action.get("confirm")
                or (meta.get("confirm") if isinstance(meta, dict) else False)
                or (meta.get("hire_override_confirmed") if isinstance(meta, dict) else False)
            ),
            expected_from_stage=str(app.get("status") or "") or None,
            idempotency_key=str(
                ctx.action.get("idempotency_key")
                or (meta.get("idempotency_key") if isinstance(meta, dict) else "")
                or ""
            )
            or None,
        )
    except Exception as gate_exc:
        import offer_lifecycle as _offers

        if isinstance(gate_exc, _offers.OfferAuthorityError):
            return {
                "action_type": action_type,
                "success": False,
                "status": "failed",
                "message": gate_exc.message,
                "error": gate_exc.code,
                "detail": gate_exc.as_detail(),
            }
        raise

    human_confirmed = bool(ctx.action.get("human_confirmed", False))
    hire_operation = ctx.action.get("hire_operation") if isinstance(ctx.action.get("hire_operation"), dict) else {}
    confirmation_payload = ctx.action.get("confirmation_payload")
    if not isinstance(confirmation_payload, dict):
        confirmation_payload = {}
    operation_id = str(hire_operation.get("operation_id") or confirmation_payload.get("operation_id") or "").strip()
    if not human_confirmed or not operation_id:
        update = {"ok": False, "error": "confirmation_required"}
        posthire = {"ok": False, "skipped": "confirmation_required"}
        ok = False
    else:
        import hire_operations as _hire_operations

        hire_result = _hire_operations.execute_hire_operation(
            legacy,
            operation_id=operation_id,
            confirmation_id=str(ctx.action.get("confirmation_id") or ""),
            confirmation_token=str(ctx.action.get("confirmation_token") or ""),
            permissions=set(permissions),
        )
        update = hire_result.get("transition") if isinstance(hire_result.get("transition"), dict) else hire_result
        posthire = update.get("side_effect") if isinstance(update, dict) else None
        ok = bool(hire_result.get("ok"))
    update_ok = bool(ok)
    name = _candidate_name(app, ctx.action)
    if ok:
        message = f"{name} is hired and employee setup is done."
    else:
        message = f"I could not complete hiring for {name}."
    return {
        "action_type": action_type,
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": message,
        "application": legacy.json_safe(app),
        "update": legacy.json_safe(update),
        "posthire": legacy.json_safe(posthire),
        "candidate_status": "hired" if ok else app.get("status"),
        "error": update.get("error") if isinstance(update, dict) and not update_ok else None,
    }


def _normalized_invite_fields(invite_result: dict[str, Any] | None) -> dict[str, Any]:
    result = invite_result if isinstance(invite_result, dict) else {}
    interview = result.get("interview") if isinstance(result.get("interview"), dict) else {}
    delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else {}
    successful_channels = delivery.get("successful_channels") if isinstance(delivery.get("successful_channels"), list) else []
    status_channels = result.get("notification_channels") if isinstance(result.get("notification_channels"), list) else []
    calendar_invite_sent = bool(result.get("calendar_invite_sent") or interview.get("calendar_invite_sent"))
    candidate_invited = bool(result.get("candidate_invited") or interview.get("candidate_invited") or calendar_invite_sent)
    candidate_notified = bool(result.get("candidate_notified") or successful_channels or interview.get("candidate_notified") or calendar_invite_sent)
    return {
        "interview_created": bool(interview.get("interview_id")),
        "calendar_event_created": bool(interview.get("calendar_event_id")),
        "google_meet_link": result.get("google_meet_link") or interview.get("meet_link"),
        "calendar_invite_sent": calendar_invite_sent,
        "candidate_invited": candidate_invited,
        "candidate_notified": candidate_notified,
        "notification_channel": result.get("notification_channel") or interview.get("notification_channel") or (successful_channels[-1] if successful_channels else (status_channels[-1] if status_channels else None)),
        "sent_subject": result.get("sent_subject") or interview.get("sent_subject"),
        "sent_body": result.get("sent_body") or interview.get("sent_body"),
        "interview": result.get("interview"),
    }


def _should_use_interview_invite(ctx: ExecutionContext, app: dict[str, Any], text: str) -> bool:
    normalized = str(text or "").lower()
    if any(token in normalized for token in ("assessment", "screening", "shortlist", "reject", "rejected", "hire", "hired", "cv")):
        return False
    if any(token in normalized for token in ("video interview", "ai interview", "ai video", "recorded interview", "asynchronous interview", "async interview")):
        return False
    explicit_interview = any(token in normalized for token in ("interview", "meeting", "google meet", "meet link"))
    generic_followup = bool(re.search(r"\b(notify|whatsapp|email|send|invite|link)\b", normalized))
    if not (explicit_interview or generic_followup):
        return False
    if explicit_interview:
        return True
    if not hasattr(ctx.legacy, "latest_candidate_interview_for_app"):
        return False
    try:
        company = str(app.get("company_code") or "").strip().upper()
        if not company:
            return False
        return bool(ctx.legacy.latest_candidate_interview_for_app(str(app.get("app_key") or ""), company))
    except Exception:
        return False


def _is_ambiguous_interview_link_request(text: str) -> bool:
    normalized = str(text or "").lower()
    if any(token in normalized for token in ("video interview", "ai interview", "ai video", "recorded interview", "asynchronous interview", "async interview")):
        return False
    if any(token in normalized for token in ("google meet", "meet link", "meeting link", "scheduled interview", "interview invite")):
        return False
    return bool(re.search(r"\binterview\s+link\b|\blink\s+.*\binterview\b", normalized))


def _send_email_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("send_email", "email")
    account_id = getattr(ctx.request, "account_id", None)
    email_text = " ".join(str(ctx.action.get(key) or "") for key in ("purpose", "message_text", "workflow_goal", "prompt_text")).lower()
    if hasattr(legacy, "send_interview_invite") and _should_use_interview_invite(ctx, app, email_text):
        invite_result = legacy.send_interview_invite(
            app,
            account_id=account_id,
            interview_id=ctx.action.get("interview_id"),
            preferred_channel="email",
        )
        ok = bool(invite_result.get("ok") if isinstance(invite_result, dict) else False)
        name = _candidate_name(app, ctx.action)
        return {
            "action_type": "send_interview_invite",
            "success": ok,
            "status": "completed" if ok else "failed",
            "message": f"Scheduled interview invite sent to {name}." if ok else invite_result.get("safe_user_message") or f"I could not send the scheduled interview invite to {name}.",
            "safe_user_message": invite_result.get("safe_user_message"),
            **_normalized_invite_fields(invite_result),
            "result": legacy.json_safe(invite_result),
            "application": legacy.json_safe(app),
        }
    result = legacy.candidate_communication_router(
        app,
        account_id=account_id,
        kind=str(ctx.action.get("purpose") or "general"),
        message=ctx.action.get("message_text") or ctx.action.get("email_body"),
        action={**ctx.action, "preferred_channel": "email"},
    )
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    name = _candidate_name(app, ctx.action)
    channels = result.get("successful_channels") if isinstance(result.get("successful_channels"), list) else []
    channel_text = " and ".join(str(channel) for channel in channels) or "email"
    safe_message = None
    if not ok and hasattr(legacy, "communication_delivery_failure_message"):
        safe_message = legacy.communication_delivery_failure_message(result, subject_label=f"the message to {name}")
    return {
        "action_type": "send_email",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"Message sent to {name} by {channel_text}." if ok else safe_message or f"I could not send the message to {name}.",
        "safe_user_message": safe_message,
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _notify_candidate_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("notify_candidate", "notify")
    account_id = getattr(ctx.request, "account_id", None)
    message = ctx.action.get("message_text") or ctx.action.get("message")
    notify_text = " ".join(str(ctx.action.get(key) or "") for key in ("purpose", "message_text", "workflow_goal", "prompt_text")).lower()
    if hasattr(legacy, "send_interview_invite") and _should_use_interview_invite(ctx, app, notify_text):
        invite_result = legacy.send_interview_invite(
            app,
            account_id=account_id,
            interview_id=ctx.action.get("interview_id"),
            preferred_channel="whatsapp",
        )
        ok = bool(invite_result.get("ok") if isinstance(invite_result, dict) else False)
        name = _candidate_name(app, ctx.action)
        channels = (invite_result.get("delivery") or {}).get("successful_channels") if isinstance(invite_result.get("delivery"), dict) else []
        channel_text = " and ".join(str(channel) for channel in channels) or "candidate channels"
        return {
            "action_type": "send_interview_invite",
            "success": ok,
            "status": "completed" if ok else "failed",
            "message": f"Scheduled interview invite sent to {name} by {channel_text}." if ok else invite_result.get("safe_user_message") or f"I could not send the scheduled interview invite to {name}.",
            "safe_user_message": invite_result.get("safe_user_message"),
            **_normalized_invite_fields(invite_result),
            "result": legacy.json_safe(invite_result),
            "application": legacy.json_safe(app),
        }
    result = legacy.candidate_communication_router(
        app,
        account_id=account_id,
        kind=str(ctx.action.get("purpose") or "notification"),
        message=message,
        action={**ctx.action, "preferred_channel": "whatsapp"},
    )
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    name = _candidate_name(app, ctx.action)
    channels = result.get("successful_channels") if isinstance(result.get("successful_channels"), list) else []
    channel_text = " and ".join(str(channel) for channel in channels) or "WhatsApp/email"
    safe_message = None
    if not ok and hasattr(legacy, "communication_delivery_failure_message"):
        safe_message = legacy.communication_delivery_failure_message(result, subject_label=f"{name}")
    return {
        "action_type": "notify_candidate",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"{name} was notified by {channel_text}." if ok else safe_message or f"I could not notify {name}.",
        "safe_user_message": safe_message,
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _send_assessment_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("send_assessment", "send an assessment to")
    account_id = getattr(ctx.request, "account_id", None)
    note_text = str(ctx.action.get("message_text") or "").strip() or None
    result = legacy.send_assessment(app, account_id, note=note_text)
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    name = _candidate_name(app, ctx.action)
    delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else result.get("send") if isinstance(result.get("send"), dict) else {}
    channels = delivery.get("successful_channels") if isinstance(delivery.get("successful_channels"), list) else []
    channel_text = " and ".join(str(channel) for channel in channels) or "candidate channels"
    safe_message = None
    if not ok and hasattr(legacy, "communication_delivery_failure_message"):
        safe_message = legacy.communication_delivery_failure_message(delivery, subject_label=f"the assessment to {name}")
    return {
        "action_type": "send_assessment",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"Assessment sent to {name} by {channel_text}." if ok else safe_message or f"I could not send the assessment to {name}.",
        "safe_user_message": safe_message,
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _screening_questions_for_app(legacy: Any, app: dict[str, Any]) -> list[dict[str, Any]]:
    company_code = str(app.get("company_code") or "").strip().upper()
    if not company_code:
        return []
    position_code = str(app.get("position_code") or "")
    questions: list[dict[str, Any]] = []
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT metadata, raw_json FROM positions WHERE company_code=%s AND position_code=%s LIMIT 1",
                    (company_code, position_code),
                )
                row = cur.fetchone()
        metadata = row.get("metadata") if row and isinstance(row.get("metadata"), dict) else {}
        raw_json = row.get("raw_json") if row and isinstance(row.get("raw_json"), dict) else {}
        for source in (metadata, raw_json):
            raw_questions = source.get("screening_questions") if isinstance(source, dict) else None
            if isinstance(raw_questions, list) and raw_questions:
                questions = [item for item in raw_questions if isinstance(item, dict)]
                break
    except Exception:
        questions = []
    if questions:
        return questions
    role = str(app.get("position_title") or app.get("position_code") or "this role")
    return [
        {"key": "visa_status", "question": "What is your current visa or residency status in Kuwait?", "required": True},
        {"key": "salary_expectation", "question": "What is your expected monthly salary in KD?", "required": True},
        {"key": "availability", "question": "When can you start?", "required": True},
        {"key": "relevant_experience", "question": f"Briefly describe your relevant experience for {role}.", "required": True},
        {"key": "tools", "question": "Which tools, software, or systems are you strongest with?", "required": False},
    ]


def _send_screening_questions_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("send_screening_questions", "send screening questions to")
    company = str(app.get("company_code") or "").strip().upper()
    if not company:
        return {
            "action_type": "send_screening_questions",
            "success": False,
            "status": "failed",
            "error": "tenant_scope_required",
            "message": "The candidate company scope is missing.",
        }
    all_questions = _screening_questions_for_app(legacy, app)
    raw_json = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
    screening = raw_json.get("screening") if isinstance(raw_json.get("screening"), dict) else {}
    answers = screening.get("answers") if isinstance(screening.get("answers"), dict) else {}
    questions = [
        question for question in all_questions
        if not str(answers.get(str(question.get("key") or "")) or "").strip()
    ]
    name = _candidate_name(app, ctx.action)
    role = app.get("position_title") or app.get("position_code") or "the role"
    if not questions:
        return {
            "action_type": "send_screening_questions",
            "success": True,
            "status": "completed",
            "message": f"{name} has already answered the required screening questions.",
            "questions": [],
            "result": {"ok": True, "skipped": True, "reason": "no_missing_questions"},
            "application": legacy.json_safe(app),
        }
    lines = [
        f"Hi {name},",
        "",
        f"Thanks for applying for {role}. Please answer these quick application questions:",
        "",
    ]
    for idx, question in enumerate(questions, 1):
        lines.append(f"{idx}. {question.get('question') or question.get('text') or question.get('key')}")
    message = "\n".join(lines)
    account_id = getattr(ctx.request, "account_id", None)
    result = legacy.candidate_communication_router(
        app,
        account_id=account_id,
        kind="screening_questions",
        message=message,
        action={"purpose": "screening_questions", "message_text": message, "preferred_channel": "whatsapp"},
    )
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    safe_message = None
    if not ok and hasattr(legacy, "communication_delivery_failure_message"):
        safe_message = legacy.communication_delivery_failure_message(result, subject_label=f"quick application questions to {name}")
    try:
        raw_json = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
        screening = raw_json.get("screening") if isinstance(raw_json.get("screening"), dict) else {}
        screening = {
            **screening,
            "status": "pending",
            "pending_keys": [str(q.get("key") or f"q{idx}") for idx, q in enumerate(questions, 1)],
            "questions": all_questions,
            "last_sent_at": getattr(legacy, "now_iso", lambda: None)() if hasattr(legacy, "now_iso") else None,
        }
        raw_json = {**raw_json, "screening": screening}
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE applications
                    SET raw_json=%s,
                        screening_status='pending',
                        updated_at=now()
                    WHERE app_key=%s AND company_code=%s
                    """,
                    (legacy.Json(legacy.json_safe(raw_json)), app.get("app_key"), company),
                )
            conn.commit()
    except Exception:
        pass
    return {
        "action_type": "send_screening_questions",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"Quick application questions sent to {name}." if ok else safe_message or f"I could not send quick application questions to {name}.",
        "safe_user_message": safe_message,
        "questions": legacy.json_safe(questions),
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _scheduled_interview_for_current_app(legacy: Any, app: dict[str, Any]) -> dict[str, Any] | None:
    if not hasattr(legacy, "latest_candidate_interview_for_app"):
        return None
    try:
        company = str(app.get("company_code") or "").strip().upper()
        if not company:
            return None
        interview = legacy.latest_candidate_interview_for_app(str(app.get("app_key") or ""), company)
        if isinstance(interview, dict) and str(interview.get("status") or "").lower() in {"scheduled", "rescheduled"}:
            return interview
        return None
    except Exception:
        return None


OUTBOUND_PREVIEW_ACTIONS = {
    "send_video_interview",
    "send_assessment",
    "send_interview_invite",
    "notify_candidate",
    "send_email",
    "send_screening_questions",
}


def _preview_role(app: dict[str, Any]) -> str:
    return str(app.get("position_title") or app.get("position_code") or "Role")


def _preview_candidate_name(legacy: Any, app: dict[str, Any], action: dict[str, Any]) -> str:
    try:
        contact = legacy.candidate_contact(app) if hasattr(legacy, "candidate_contact") else {}
    except Exception:
        contact = {}
    return str((contact or {}).get("name") or app.get("candidate_name") or action.get("candidate_name") or app.get("phone") or "Candidate")


def _preview_channels(action_type: str, action: dict[str, Any], app: dict[str, Any]) -> str:
    preferred = str(action.get("preferred_channel") or action.get("invite_channel") or "").strip().lower()
    has_email = bool(app.get("candidate_email"))
    has_phone = bool(app.get("phone"))
    if action_type in {"send_video_interview", "send_assessment", "send_interview_invite"}:
        if preferred == "whatsapp":
            return "WhatsApp + Email where available"
        if preferred == "email":
            return "Email + WhatsApp where available"
        return "WhatsApp + Email where available"
    if action_type == "send_email":
        return "Email" if has_email else "Email (candidate has no email address)"
    if action_type in {"notify_candidate", "send_screening_questions"}:
        return "WhatsApp" if has_phone else "WhatsApp (candidate has no phone number)"
    return "Candidate channel"


def _preview_link_type(action_type: str) -> str | None:
    return {
        "send_video_interview": "video interview link",
        "send_assessment": "assessment link",
        "send_interview_invite": "scheduled interview invite",
    }.get(action_type)


def _preview_action_title(action_type: str) -> str:
    return {
        "send_video_interview": "Send video interview",
        "send_assessment": "Send application assessment",
        "send_interview_invite": "Send interview invite",
        "notify_candidate": "Notify candidate",
        "send_email": "Send email",
        "send_screening_questions": "Send quick application questions",
    }.get(action_type, _action_preview_label(action_type).capitalize())


def _preview_expected_result(action_type: str, name: str) -> str:
    return {
        "send_video_interview": f"{name} will receive a secure video interview link.",
        "send_assessment": f"{name} will receive an application assessment link.",
        "send_interview_invite": f"{name} will receive the scheduled interview invite.",
        "notify_candidate": f"{name} will receive the message.",
        "send_email": f"{name} will receive the email.",
        "send_screening_questions": f"{name} will receive quick application questions.",
    }.get(action_type, f"{name} will receive the message.")


def _preview_body_for_action(legacy: Any, action_type: str, action: dict[str, Any], app: dict[str, Any]) -> str:
    name = _preview_candidate_name(legacy, app, action)
    role = _preview_role(app)
    if action_type == "send_video_interview":
        return "\n".join([
            f"Hi {name},",
            "",
            "You have been invited to complete a short video interview for your application.",
            "Please open the link below when you are ready. You will be asked to review the instructions, give consent, and answer a few questions by video.",
            "",
            "[secure video interview link]",
        ])
    if action_type == "send_assessment":
        return "\n".join([
            f"Hi {name},",
            "",
            f"You have been invited to complete an application assessment for {role}.",
            "",
            "Open your assessment here:",
            "[secure assessment link]",
        ])
    if action_type == "send_interview_invite":
        interview = _scheduled_interview_for_current_app(legacy, app)
        if interview and hasattr(legacy, "compose_interview_invite_message"):
            try:
                return str(legacy.compose_interview_invite_message(app, interview))
            except Exception:
                pass
        return "\n".join([
            f"Hi {name},",
            "",
            f"Your interview for {role} is scheduled.",
            "The joining details will be included in the invite.",
        ])
    if action_type == "send_email":
        if hasattr(legacy, "compose_email_content"):
            try:
                return str((legacy.compose_email_content(app, action) or {}).get("body") or "").strip()
            except Exception:
                pass
        return str(action.get("message_text") or action.get("email_body") or f"Hi {name},\n\nWathefni HR is following up regarding your application.").strip()
    if action_type == "send_screening_questions":
        questions = _screening_questions_for_app(legacy, app)
        lines = [f"Hi {name},", "", f"Thanks for applying for {role}. Please answer these quick application questions:", ""]
        for idx, question in enumerate(questions[:5], 1):
            lines.append(f"{idx}. {question.get('question') or question.get('text') or 'Application question'}")
        return "\n".join(lines).strip()
    return str(action.get("message_text") or action.get("message") or f"Hi {name},\n\nWathefni HR is following up regarding your application.").strip()


def _truncate_preview_body(body: str, *, limit: int = 700) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", str(body or "").strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _format_confirmation_text(preview: dict[str, Any]) -> str:
    candidate = preview.get("candidate") or "Candidate"
    delivery = preview.get("delivery_channels") or "Candidate channel"
    body = preview.get("message_preview") or "Message will be generated from the selected action."
    expected = preview.get("expected_result") or "Candidate will receive the message."
    lines = [
        str(preview.get("title") or "Confirm candidate message"),
        "",
        "Candidate:",
        str(candidate),
        "",
        "Delivery:",
        str(delivery),
        "",
        "Candidate message:",
        f"“{body}”",
        "",
        "Expected result:",
        str(expected),
        "",
        "Confirm to send?",
    ]
    return "\n".join(lines)


def outbound_confirmation_preview(ctx: ExecutionContext, action_type: str | None = None, app: dict[str, Any] | None = None) -> dict[str, Any] | None:
    legacy = ctx.legacy
    selected_action = str(action_type or ctx.action.get("action_type") or "").strip()
    if selected_action not in OUTBOUND_PREVIEW_ACTIONS:
        return None
    target = app or _resolve_app(ctx)
    if not target:
        return None
    name = _preview_candidate_name(legacy, target, ctx.action)
    if selected_action == "send_interview_invite" and not _scheduled_interview_for_current_app(legacy, target):
        return {
            "status": "needs_clarification",
            "message": f"No scheduled interview exists for {name}'s current application yet. You can schedule one first, or send a video interview link instead.",
        }
    role = _preview_role(target)
    body = _truncate_preview_body(_preview_body_for_action(legacy, selected_action, ctx.action, target))
    title = f"{_preview_action_title(selected_action)} to {name}"
    preview = {
        "title": title,
        "candidate_name": name,
        "role": role,
        "candidate": f"{name} — {role}",
        "action": _preview_action_title(selected_action),
        "delivery_channels": _preview_channels(selected_action, ctx.action, target),
        "message_preview": body,
        "link_type": _preview_link_type(selected_action),
        "expected_result": _preview_expected_result(selected_action, name),
    }
    return {**preview, "confirmation_text": _format_confirmation_text(preview)}


def _send_video_interview_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("send_video_interview", "send an AI video interview to")
    if not all(hasattr(legacy, name) for name in ("DashboardVideoInterviewRequest", "create_or_resume_async_video_interview", "send_async_video_interview_invite")):
        return {
            "action_type": "send_video_interview",
            "success": False,
            "status": "failed",
            "message": "AI video interview sending is not available in this runtime.",
            "application": legacy.json_safe(app),
        }
    company = _resolve_company_code(legacy, ctx.request) or str(app.get("company_code") or "").upper()
    metadata = getattr(ctx.request, "metadata", None)
    hr_user = metadata.get("admin_user") if isinstance(metadata, dict) and isinstance(metadata.get("admin_user"), dict) else None
    access = metadata.get("access") if isinstance(metadata, dict) and isinstance(metadata.get("access"), dict) else {}
    actor = legacy.actor_context_for_hr_user(
        hr_user or {"phone": legacy.digits(getattr(ctx.request, "sender_phone", None)), "role": access.get("role") or getattr(ctx.request, "sender_role", None) or "hr_admin", "company_code": company},
        company_code=company,
        hr_phone=getattr(ctx.request, "sender_phone", None),
    )
    contact = legacy.candidate_contact(app) if hasattr(legacy, "candidate_contact") else {}
    preferred = str(ctx.action.get("preferred_channel") or ctx.action.get("invite_channel") or "").strip().lower()
    text = " ".join(str(ctx.action.get(key) or "") for key in ("workflow_goal", "prompt_text", "message_text", "purpose")).lower()
    if preferred not in {"email", "whatsapp"}:
        preferred = "whatsapp" if "whatsapp" in text or not (contact or {}).get("email") else "email"
    note_text = str(ctx.action.get("message_text") or "").strip() or None
    request = legacy.DashboardVideoInterviewRequest(
        account_id=getattr(ctx.request, "account_id", None) or "default",
        response_mode="single_video",
        send_invite=True,
        preferred_channel=preferred,
        message=note_text,
    )
    created = legacy.create_or_resume_async_video_interview(app, request, actor_context=actor)
    result = legacy.send_async_video_interview_invite(
        app,
        created["interview"],
        created["public_link"],
        account_id=request.account_id,
        preferred_channel=preferred,
        actor_context=actor,
        note=note_text,
    )
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    name = _candidate_name(app, ctx.action)
    channels = (result.get("delivery") or {}).get("successful_channels") if isinstance(result.get("delivery"), dict) else []
    channel_text = " and ".join(str(channel) for channel in channels) or preferred
    delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else {}
    safe_message = None
    if not ok and hasattr(legacy, "communication_delivery_failure_message"):
        safe_message = legacy.communication_delivery_failure_message(delivery, subject_label=f"the video interview link to {name}")
    return {
        "action_type": "send_video_interview",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"Video interview link sent to {name} by {channel_text}." if ok else safe_message or f"I prepared the video interview, but could not send the link to {name}.",
        "safe_user_message": safe_message,
        "interview": result.get("interview"),
        "public_link": result.get("public_link"),
        "candidate_notified": ((result.get("interview") or {}).get("candidate_notified") if isinstance(result.get("interview"), dict) else None),
        "notification_channel": ((result.get("interview") or {}).get("notification_channel") if isinstance(result.get("interview"), dict) else None),
        "sent_subject": result.get("sent_subject"),
        "sent_body": result.get("sent_body"),
        "delivery": legacy.json_safe(result.get("delivery") or {}),
        "application": legacy.json_safe(app),
    }


BATCH_ALLOWED_ACTIONS = {
    "send_video_interview",
    "send_assessment",
    "send_screening_questions",
    "send_interview_invite",
    "notify_candidate",
    "send_email",
    "shortlist_candidate",
}
BATCH_MAX_ITEMS = 20


def _batch_action_type(action: dict[str, Any]) -> str:
    explicit = str(action.get("batch_action_type") or action.get("target_action_type") or action.get("item_action_type") or "").strip()
    if explicit in BATCH_ALLOWED_ACTIONS:
        return explicit
    text = " ".join(str(action.get(key) or "") for key in ("workflow_goal", "prompt_text", "message_text", "purpose", "query")).lower()
    if "video" in text and "interview" in text:
        return "send_video_interview"
    if "assessment" in text:
        return "send_assessment"
    if "screening" in text and "question" in text:
        return "send_screening_questions"
    if "shortlist" in text:
        return "shortlist_candidate"
    if "interview" in text and any(token in text for token in ("invite", "link", "send")):
        return "send_interview_invite"
    if "email" in text:
        return "send_email"
    if "notify" in text or "whatsapp" in text:
        return "notify_candidate"
    return ""


def _candidate_name_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*(?:,| and | و )\s*", raw, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def _candidate_summary_for_batch(legacy: Any, app: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_key": app.get("app_key"),
        "candidate_name": app.get("candidate_name") or app.get("name") or app.get("phone"),
        "candidate_email": app.get("candidate_email"),
        "phone": app.get("phone"),
        "position_code": app.get("position_code"),
        "position_title": app.get("position_title"),
        "status": app.get("status"),
    }


def _dedupe_batch_candidates(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for app in apps:
        key = str(app.get("app_key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(app)
    return out


def _batch_candidates_from_recent_state(state: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if not isinstance(state, dict):
        return []
    last = state.get("last_action_result") if isinstance(state.get("last_action_result"), dict) else {}
    pools: list[Any] = []
    if isinstance(last.get("candidates"), list):
        pools.extend(last.get("candidates") or [])
    result = last.get("result") if isinstance(last.get("result"), dict) else {}
    if isinstance(result.get("candidates"), list):
        pools.extend(result.get("candidates") or [])
    apps: list[dict[str, Any]] = []
    for item in pools:
        if not isinstance(item, dict):
            continue
        app = item.get("application") if isinstance(item.get("application"), dict) else item
        if isinstance(app, dict) and app.get("app_key"):
            apps.append(app)
    return _dedupe_batch_candidates(apps)[:limit]


def _resolve_batch_candidates(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = ctx.action
    company_code = _resolve_company_code(legacy, ctx.request) or str(action.get("company_code") or "").upper()
    limit = max(1, min(int(action.get("top_n") or action.get("limit") or 5), BATCH_MAX_ITEMS))
    apps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for app_key in action.get("candidate_app_keys") or action.get("app_keys") or []:
        app = legacy.find_application_by_key(str(app_key), company_code=company_code) if hasattr(legacy, "find_application_by_key") else None
        if app:
            apps.append(app)
        else:
            errors.append({"candidate_app_key": app_key, "error": "not_found"})
    for name in _candidate_name_list(action.get("candidate_names") or action.get("candidate_name")):
        result = resolve_candidate_typed(legacy, {**action, "candidate_name": name, "company_code": company_code})
        if result.get("status") == "resolved" and result.get("matches"):
            apps.append(result["matches"][0])
        elif result.get("status") == "ambiguous":
            errors.append({"candidate_name": name, "error": "ambiguous", "matches": [_candidate_summary_for_batch(legacy, row) for row in (result.get("matches") or [])[:5]]})
        else:
            errors.append({"candidate_name": name, "error": result.get("status") or "not_found"})
    if not apps:
        apps = _batch_candidates_from_recent_state(ctx.state, limit)
    if not apps and (action.get("query") or action.get("position") or action.get("status") or action.get("top_n")):
        rank_action = {
            **action,
            "action_type": "rank_candidates",
            "top_n": limit,
            "query": action.get("query") or action.get("prompt_text") or action.get("workflow_goal") or "",
        }
        rank_ctx = ExecutionContext(ctx.request, rank_action, ctx.state, ctx.graph_state, {**ctx.intent, "batch_source": "rank_candidates"}, legacy)
        ranked = _rank_candidates_executor(rank_ctx)
        for item in ranked.get("candidates") or []:
            if isinstance(item, dict):
                app = item.get("application") if isinstance(item.get("application"), dict) else None
                if app and app.get("app_key"):
                    apps.append(app)
    apps = _dedupe_batch_candidates(apps)[:limit]
    return {"company_code": company_code, "candidates": apps, "errors": errors, "limit": limit}


ACTION_PREVIEW_LABELS = {
    "send_video_interview": "send a video interview link",
    "send_assessment": "send an application assessment",
    "send_screening_questions": "send quick application questions",
    "send_interview_invite": "send a scheduled interview invite",
    "notify_candidate": "notify the candidate",
    "send_email": "send an email",
    "shortlist_candidate": "shortlist",
    "hire_candidate": "mark as hired",
    "reject_candidate": "mark as rejected",
}


def _action_preview_label(action_type: str | None) -> str:
    return ACTION_PREVIEW_LABELS.get(str(action_type or ""), "run this action")


def _candidate_preview_name(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_name") or candidate.get("name") or candidate.get("phone") or "candidate")


def _candidate_preview_lines(candidates: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    lines = []
    for candidate in candidates[:limit]:
        role = candidate.get("position_title") or candidate.get("position_code")
        lines.append(f"{_candidate_preview_name(candidate)}{f' — {role}' if role else ''}")
    extra = len(candidates) - len(lines)
    if extra > 0:
        lines.append(f"and {extra} more")
    return lines


def _delivery_preview_for_action(action_type: str | None) -> str | None:
    if action_type in {"send_video_interview", "send_assessment", "send_interview_invite"}:
        return "WhatsApp and email where available"
    if action_type == "send_email":
        return "email"
    if action_type in {"notify_candidate", "send_screening_questions"}:
        return "WhatsApp"
    return None


def _execute_candidate_batch_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    batch_action = _batch_action_type(ctx.action)
    if not batch_action:
        return {
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["batch_action_type"],
            "message": "Which action should I run for the selected candidates?",
        }
    if batch_action not in BATCH_ALLOWED_ACTIONS:
        return {
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "message": f"{batch_action} is not supported for batch execution yet.",
        }
    resolved = _resolve_batch_candidates(ctx)
    candidates = resolved["candidates"]
    if not candidates:
        return {
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["candidate_selection"],
            "message": "I could not resolve candidates for this batch. Ask for exact names, app keys, or run a candidate ranking first.",
            "resolution_errors": resolved["errors"],
        }
    labels = [_candidate_summary_for_batch(ctx.legacy, app) for app in candidates]
    candidate_lines = _candidate_preview_lines(labels)
    action_label = _action_preview_label(batch_action)
    channel = _delivery_preview_for_action(batch_action)
    channel_text = f" by {channel}" if channel else ""
    sample_body = _truncate_preview_body(_preview_body_for_action(ctx.legacy, batch_action, ctx.action, candidates[0])) if candidates else ""
    preview = {
        "title": f"{_preview_action_title(batch_action)} to {len(labels)} candidate{'s' if len(labels) != 1 else ''}",
        "candidate_count": len(labels),
        "candidates": candidate_lines,
        "action": _preview_action_title(batch_action),
        "delivery_channels": channel or "Candidate channel",
        "message_preview": sample_body,
        "link_type": _preview_link_type(batch_action),
        "expected_result": f"{len(labels)} candidate{'s' if len(labels) != 1 else ''} will receive {_preview_link_type(batch_action) or 'the message'}.",
    }
    preview["confirmation_text"] = "\n".join([
        str(preview["title"]),
        "",
        "Candidates:",
        *[f"- {line}" for line in candidate_lines],
        "",
        "Delivery:",
        str(preview["delivery_channels"]),
        "",
        "Candidate message:",
        f"“{sample_body}”",
        "",
        "Expected result:",
        str(preview["expected_result"]),
        "",
        "Confirm to send?",
    ])
    return {
        "action_type": "execute_candidate_batch",
        "success": True,
        "status": "ready",
        "batch_action_type": batch_action,
        "company_code": resolved["company_code"],
        "candidate_count": len(labels),
        "candidates": labels,
        "resolution_errors": resolved["errors"],
        "message": (
            f"I found {len(labels)} candidate{'s' if len(labels) != 1 else ''}. "
            f"I can {action_label} for: {', '.join(candidate_lines)}{channel_text}. Confirm to continue?"
        ),
        "instruction": "Ask HR to confirm this exact candidate list before executing. Do not mention internal action names.",
        "human_action": action_label,
        "delivery_channel": channel,
        "confirmation_preview": preview,
        "confirmation_text": preview["confirmation_text"],
    }


def _insert_batch_action(ctx: ExecutionContext, preflight: dict[str, Any]) -> str:
    legacy = ctx.legacy
    company = str(preflight.get("company_code") or ctx.action.get("company_code") or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO batch_actions (
                  company_code, company_id, action_type, status, total_count,
                  requested_by_phone, actor_user_id, actor_phone, actor_role, source_turn_id,
                  request_payload, preflight_payload, started_at, updated_at
                )
                VALUES (%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
                RETURNING batch_id
                """,
                (
                    company,
                    company,
                    preflight.get("batch_action_type"),
                    int(preflight.get("candidate_count") or 0),
                    str(getattr(ctx.request, "sender_phone", "") or ""),
                    ctx.action.get("actor_user_id"),
                    ctx.action.get("actor_phone"),
                    ctx.action.get("actor_role"),
                    ctx.action.get("turn_id"),
                    legacy.Json(legacy.json_safe(ctx.action)),
                    legacy.Json(legacy.json_safe(preflight)),
                ),
            )
            batch_id = str(cur.fetchone()["batch_id"])
        conn.commit()
    return batch_id


def _update_batch_item(legacy: Any, batch_id: str, app: dict[str, Any], action_type: str, status: str, result: dict[str, Any]) -> None:
    error = str(result.get("error") or result.get("error_code") or "") or None
    message = None if status == "completed" else str(result.get("message") or result.get("safe_user_message") or "")[:500]
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO batch_action_items (
                  batch_id, company_code, company_id, action_type, app_key, candidate_name, candidate_phone,
                  candidate_email, position_code, position_title, status, result, error_code, error_message,
                  started_at, completed_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now(),now())
                """,
                (
                    batch_id,
                    str(app.get("company_code") or "").upper(),
                    str(app.get("company_code") or "").upper(),
                    action_type,
                    str(app.get("app_key") or ""),
                    app.get("candidate_name"),
                    app.get("phone"),
                    app.get("candidate_email"),
                    app.get("position_code"),
                    app.get("position_title"),
                    status,
                    legacy.Json(legacy.json_safe(result)),
                    error,
                    message,
                ),
            )
        conn.commit()


def _execute_candidate_batch_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    preflight = _execute_candidate_batch_preflight(ctx)
    if preflight.get("status") != "ready":
        return preflight
    batch_action = str(preflight.get("batch_action_type") or "")
    resolved = _resolve_batch_candidates(ctx)
    apps = resolved["candidates"]
    batch_id = _insert_batch_action(ctx, {**preflight, "candidate_count": len(apps)})
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    for app in apps:
        action = {
            **ctx.action,
            "action_type": batch_action,
            "app_key": app.get("app_key"),
            "subject_key": app.get("app_key"),
            "subject_type": "candidate",
            "subject_name": app.get("candidate_name"),
            "candidate_app_key": app.get("app_key"),
            "candidate_name": app.get("candidate_name"),
            "batch_id": batch_id,
        }
        atomic_ctx = ExecutionContext(ctx.request, action, ctx.state, ctx.graph_state, {**ctx.intent, "batch_id": batch_id, "batch_item_action": batch_action}, legacy)
        result = execute(batch_action, atomic_ctx)
        item_status = "completed" if result.get("status") == "completed" and result.get("success") is not False else "failed"
        if item_status == "completed":
            success_count += 1
        else:
            failed_count += 1
        _update_batch_item(legacy, batch_id, app, batch_action, item_status, result)
        results.append({"app_key": app.get("app_key"), "candidate_name": app.get("candidate_name"), "status": item_status, "result": legacy.json_safe(result)})
    batch_status = "completed" if failed_count == 0 else "partial" if success_count else "failed"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_actions
                SET status=%s, success_count=%s, failed_count=%s, result_payload=%s,
                    completed_at=now(), updated_at=now()
                WHERE batch_id=%s
                """,
                (batch_status, success_count, failed_count, legacy.Json(legacy.json_safe({"items": results})), batch_id),
            )
        conn.commit()
    return {
        "action_type": "execute_candidate_batch",
        "success": failed_count == 0,
        "status": batch_status,
        "message": f"{_action_preview_label(batch_action).capitalize()} finished for {success_count} candidate{'s' if success_count != 1 else ''}. {failed_count} candidate{'s' if failed_count != 1 else ''} need attention.",
        "batch_id": batch_id,
        "batch_action_type": batch_action,
        "success_count": success_count,
        "failed_count": failed_count,
        "total_count": len(apps),
        "items": results,
    }


def _mixed_batch_raw_items(action: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = action.get("mixed_items") or action.get("items") or action.get("batch_items")
    if isinstance(raw_items, list):
        return [dict(item) for item in raw_items if isinstance(item, dict)]
    return []


def _resolve_mixed_batch_items(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    company_code = _resolve_company_code(legacy, ctx.request) or str(ctx.action.get("company_code") or "").upper()
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(_mixed_batch_raw_items(ctx.action)):
        action_type = _batch_action_type(item)
        if not action_type or action_type not in BATCH_ALLOWED_ACTIONS:
            errors.append({"index": index, "error": "unsupported_action", "action_type": item.get("action_type")})
            continue
        resolution = resolve_candidate_typed(
            legacy,
            {
                **ctx.action,
                **item,
                "candidate_app_key": item.get("candidate_app_key") or item.get("app_key") or item.get("subject_key"),
                "candidate_name": item.get("candidate_name") or item.get("subject_name") or item.get("name"),
                "company_code": company_code,
            },
        )
        matches = resolution.get("matches") or []
        if resolution.get("status") == "resolved" and matches:
            app = matches[0]
            items.append(
                {
                    "index": index,
                    "action_type": action_type,
                    "app": app,
                    "candidate": _candidate_summary_for_batch(legacy, app),
                    "item_args": {key: value for key, value in item.items() if value not in (None, "", [], {})},
                }
            )
        elif resolution.get("status") == "ambiguous":
            errors.append({"index": index, "error": "ambiguous", "action_type": action_type, "matches": [_candidate_summary_for_batch(legacy, row) for row in matches[:5]]})
        else:
            errors.append({"index": index, "error": resolution.get("status") or "not_found", "action_type": action_type, "item": item})
    return {"company_code": company_code, "items": items[:BATCH_MAX_ITEMS], "errors": errors}


def _execute_mixed_candidate_batch_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    raw_items = _mixed_batch_raw_items(ctx.action)
    if not raw_items:
        return {
            "action_type": "execute_mixed_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["mixed_items"],
            "message": "I need the candidate/action pairs before I can prepare a mixed batch.",
        }
    resolved = _resolve_mixed_batch_items(ctx)
    if not resolved["items"]:
        return {
            "action_type": "execute_mixed_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["resolvable_mixed_items"],
            "message": "I could not resolve any candidate/action pairs for this mixed batch.",
            "resolution_errors": resolved["errors"],
        }
    preview_items = [
        {
            "index": item["index"],
            "action_type": item["action_type"],
            "human_action": _action_preview_label(item["action_type"]),
            **item["candidate"],
        }
        for item in resolved["items"]
    ]
    pair_lines = [
        f"{_candidate_preview_name(item)} — {item.get('human_action')}"
        for item in preview_items[:5]
    ]
    extra = len(preview_items) - len(pair_lines)
    if extra > 0:
        pair_lines.append(f"and {extra} more")
    first = resolved["items"][0]
    sample_body = _truncate_preview_body(_preview_body_for_action(ctx.legacy, first["action_type"], {**ctx.action, **first.get("item_args", {})}, first["app"]))
    preview = {
        "title": f"Confirm {len(preview_items)} candidate action{'s' if len(preview_items) != 1 else ''}",
        "candidate_count": len(preview_items),
        "candidates": pair_lines,
        "action": "Mixed candidate actions",
        "delivery_channels": "Candidate channels by action",
        "message_preview": sample_body,
        "expected_result": f"{len(preview_items)} candidate action{'s' if len(preview_items) != 1 else ''} will run after confirmation.",
    }
    preview["confirmation_text"] = "\n".join([
        str(preview["title"]),
        "",
        "Candidates and actions:",
        *[f"- {line}" for line in pair_lines],
        "",
        "Delivery:",
        str(preview["delivery_channels"]),
        "",
        "Candidate message preview:",
        f"“{sample_body}”",
        "",
        "Expected result:",
        str(preview["expected_result"]),
        "",
        "Confirm to send?",
    ])
    return {
        "action_type": "execute_mixed_candidate_batch",
        "success": True,
        "status": "ready",
        "batch_action_type": "mixed_candidate_batch",
        "company_code": resolved["company_code"],
        "candidate_count": len(preview_items),
        "items": preview_items,
        "resolution_errors": resolved["errors"],
        "message": f"I prepared these candidate actions: {', '.join(pair_lines)}. Confirm to continue?",
        "instruction": "Ask HR to confirm this exact candidate/action list before executing. Do not mention internal action names.",
        "confirmation_preview": preview,
        "confirmation_text": preview["confirmation_text"],
    }


def _execute_mixed_candidate_batch_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    preflight = _execute_mixed_candidate_batch_preflight(ctx)
    if preflight.get("status") != "ready":
        return preflight
    resolved = _resolve_mixed_batch_items(ctx)
    items = resolved["items"]
    batch_id = _insert_batch_action(ctx, {**preflight, "batch_action_type": "mixed_candidate_batch", "candidate_count": len(items)})
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    for item in items:
        app = item["app"]
        action_type = item["action_type"]
        action = {
            **ctx.action,
            **item.get("item_args", {}),
            "action_type": action_type,
            "app_key": app.get("app_key"),
            "subject_key": app.get("app_key"),
            "subject_type": "candidate",
            "subject_name": app.get("candidate_name"),
            "candidate_app_key": app.get("app_key"),
            "candidate_name": app.get("candidate_name"),
            "batch_id": batch_id,
            "mixed_batch_item_index": item["index"],
        }
        atomic_ctx = ExecutionContext(ctx.request, action, ctx.state, ctx.graph_state, {**ctx.intent, "batch_id": batch_id, "mixed_batch_item_action": action_type}, legacy)
        result = execute(action_type, atomic_ctx)
        item_status = "completed" if result.get("status") == "completed" and result.get("success") is not False else "failed"
        if item_status == "completed":
            success_count += 1
        else:
            failed_count += 1
        _update_batch_item(legacy, batch_id, app, action_type, item_status, result)
        results.append({"index": item["index"], "app_key": app.get("app_key"), "candidate_name": app.get("candidate_name"), "action_type": action_type, "status": item_status, "result": legacy.json_safe(result)})
    batch_status = "completed" if failed_count == 0 else "partial" if success_count else "failed"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_actions
                SET status=%s, success_count=%s, failed_count=%s, result_payload=%s,
                    completed_at=now(), updated_at=now()
                WHERE batch_id=%s
                """,
                (batch_status, success_count, failed_count, legacy.Json(legacy.json_safe({"items": results})), batch_id),
            )
        conn.commit()
    return {
        "action_type": "execute_mixed_candidate_batch",
        "success": failed_count == 0,
        "status": batch_status,
        "message": f"Candidate actions finished for {success_count} candidate{'s' if success_count != 1 else ''}. {failed_count} candidate{'s' if failed_count != 1 else ''} need attention.",
        "batch_id": batch_id,
        "success_count": success_count,
        "failed_count": failed_count,
        "total_count": len(items),
        "items": results,
    }


def _schedule_interview_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Schedule via canonical interview_service (Google Meet or Microsoft Teams).

    Replaces the legacy direct gog calendar path. Wathefni interview record is
    source of truth; provider sync is optional and never invents success.
    """

    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("schedule_interview", "schedule")
    text = " ".join(
        str(value or "")
        for value in (
            ctx.action.get("prompt_text"),
            ctx.action.get("interview_time"),
            ctx.action.get("when"),
            ctx.action.get("datetime"),
            ctx.action.get("datetime_text"),
            ctx.action.get("message"),
            ctx.action.get("message_text"),
        )
    ).strip()
    start, end = legacy.parse_meeting_time(text)
    if not start or not end:
        return {
            "action_type": "schedule_interview",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_required_fields": ["interview_time"],
            "message": "I need a specific date and time for the interview — for example, 'tomorrow at 4pm' or '2026-05-15T16:00'.",
        }
    contact = legacy.candidate_contact(app) or {}
    email = contact.get("email")
    name = contact.get("name") or _candidate_name(app, ctx.action)
    meeting_type = str(ctx.action.get("meeting_type") or "").strip() or "google_meet"
    try:
        import interview_microsoft_calendar as mcal
        import interview_lifecycle as life

        if life.normalize_meeting_type(meeting_type) == "microsoft_teams" and not mcal.microsoft_env_configured():
            return {
                "action_type": "schedule_interview",
                "success": False,
                "status": "failed",
                "error": "microsoft_not_configured",
                "message": "Microsoft Teams is not configured for this company yet.",
                "application": legacy.json_safe(app),
            }
    except Exception:
        pass
    if meeting_type in {"google_meet", "google", "meet"} and not email:
        return {
            "action_type": "schedule_interview",
            "success": False,
            "status": "failed",
            "message": f"I do not have an email address for {name}, so I can't send the calendar invite.",
            "error": "missing_candidate_email",
            "application": legacy.json_safe(app),
        }
    meta = getattr(ctx.request, "metadata", {}) or {}
    if not isinstance(meta, dict):
        meta = {}
    import interview_service as _interview_service
    import interview_lifecycle as _il

    try:
        scheduled = _interview_service.schedule_interview(
            company_code=str(app.get("company_code") or ""),
            app_key=str(app.get("app_key") or ""),
            start=start,
            end=end,
            meeting_type=meeting_type,
            location=ctx.action.get("location"),
            meet_link=ctx.action.get("meet_link") or ctx.action.get("meeting_link"),
            idempotency_key=str(ctx.action.get("idempotency_key") or "") or None,
            actor={
                "actor_user_id": str(ctx.action.get("actor_user_id") or meta.get("actor_user_id") or "") or None,
                "actor_phone": getattr(ctx.request, "sender_phone", None),
                "actor_role": str(meta.get("actor_role") or "") or None,
                "actor_type": "human",
            },
            source="assistant_schedule",
            sync_external=True,
            move_application_stage=True,
            confirmation={
                "human_confirmed": bool(ctx.action.get("human_confirmed", False)),
                "channel": "web" if meta.get("dashboard") else "whatsapp",
                "permissions": meta.get("permissions") or [],
                "confirmation_id": ctx.action.get("confirmation_id"),
                "confirmation_token": ctx.action.get("confirmation_token"),
                "confirmation_payload": ctx.action.get("confirmation_payload")
                if isinstance(ctx.action.get("confirmation_payload"), dict)
                else {},
                "idempotency_key": ctx.action.get("idempotency_key"),
                "expected_version": ctx.action.get("expected_version"),
            },
            permissions=meta.get("permissions") or [],
        )
    except _il.InterviewAuthorityError as exc:
        return {
            "action_type": "schedule_interview",
            "success": False,
            "status": "failed" if getattr(exc, "error", "") != "confirmation_required" else "failed",
            "error": getattr(exc, "error", None) or "schedule_failed",
            "message": getattr(exc, "message", None) or str(exc),
            "application": legacy.json_safe(app),
        }
    interview = scheduled.get("interview") if isinstance(scheduled, dict) else None
    meet_link = None
    if isinstance(interview, dict):
        meet_link = interview.get("meet_link")
    provider_sync = scheduled.get("provider_sync") if isinstance(scheduled, dict) else {}
    sync_ok = bool((provider_sync or {}).get("ok")) if isinstance(provider_sync, dict) else bool(provider_sync)
    return {
        "action_type": "schedule_interview",
        "success": True,
        "status": "completed",
        "message": f"Interview with {name} scheduled for {start}.",
        "interview": legacy.json_safe(interview),
        "interview_created": bool(interview),
        "calendar_event_created": sync_ok or bool(isinstance(interview, dict) and interview.get("calendar_event_id")),
        "google_meet_link": meet_link if meeting_type in {"google_meet", "google", "meet"} else None,
        "teams_meet_link": meet_link if "team" in meeting_type.lower() or meeting_type == "microsoft_teams" else None,
        "meet_link": meet_link,
        "calendar_invite_sent": bool(isinstance(interview, dict) and interview.get("calendar_invite_sent")),
        "candidate_invited": bool(isinstance(interview, dict) and interview.get("candidate_invited")),
        "candidate_notified": bool(isinstance(interview, dict) and (interview.get("candidate_invited") or interview.get("candidate_notified"))),
        "notification_channel": (interview or {}).get("notification_channel") if isinstance(interview, dict) else None,
        "provider_sync": legacy.json_safe(provider_sync),
        "idempotent_replay": bool(scheduled.get("idempotent_replay")),
        "application": legacy.json_safe(app),
        "start": start,
        "end": end,
    }


def _send_interview_invite_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("send_interview_invite", "send an interview invite to")
    if not hasattr(legacy, "send_interview_invite"):
        return {
            "action_type": "send_interview_invite",
            "success": False,
            "status": "failed",
            "message": "Interview invite delivery is not available in this runtime.",
        }
    preferred = str(ctx.action.get("preferred_channel") or ctx.action.get("invite_channel") or "").strip().lower() or None
    result = legacy.send_interview_invite(
        app,
        account_id=getattr(ctx.request, "account_id", None),
        interview_id=ctx.action.get("interview_id"),
        preferred_channel=preferred,
        explicit=True,
    )
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    name = _candidate_name(app, ctx.action)
    channels = (result.get("delivery") or {}).get("successful_channels") if isinstance(result.get("delivery"), dict) else []
    channel_text = " and ".join(str(channel) for channel in channels) or "candidate channels"
    return {
        "action_type": "send_interview_invite",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": f"Scheduled interview invite sent to {name} by {channel_text}." if ok else result.get("safe_user_message") or f"I could not send the scheduled interview invite to {name}.",
        "safe_user_message": result.get("safe_user_message"),
        **_normalized_invite_fields(result),
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _get_interview_invite_status_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("get_interview_invite_status", "check interview invite status for")
    if not hasattr(legacy, "interview_invite_status"):
        return {
            "action_type": "get_interview_invite_status",
            "success": False,
            "status": "failed",
            "message": "Interview invite status is not available in this runtime.",
        }
    result = legacy.interview_invite_status(app)
    ok = bool(result.get("ok") if isinstance(result, dict) else False)
    return {
        "action_type": "get_interview_invite_status",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": str(result.get("message") or "I could not find an interview invite record for this candidate."),
        **_normalized_invite_fields(result),
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app),
    }


def _candidate_cv_evaluation_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Read-only evaluation that always includes candidate_context (CV text +
    structured fields + prior ranking) so the renderer can answer naturally
    grounded in the candidate's real data, without the user having to ask.
    """

    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("candidate_cv_evaluation", "evaluate")
    context = _load_candidate_context(legacy, app, ctx.action, ctx.state, ctx.request)
    name = context.get("name") or _candidate_name(app, ctx.action)
    return {
        "action_type": "candidate_cv_evaluation",
        "success": True,
        "status": "completed",
        "message": f"Evaluation context loaded for {name}.",
        "candidate_context": legacy.json_safe(context),
        "application": legacy.json_safe(app),
        "selected_application": legacy.json_safe(
            legacy.candidate_lookup_match_payload(app)
            if hasattr(legacy, "candidate_lookup_match_payload")
            else app
        ),
    }


CANDIDATE_STATUSES = (
    "awaiting_cv",
    "cv_processing",
    "ready_for_review",
    "shortlisted",
    "interview",
    "hired",
    "rejected",
    "withdrawn",
    # Legacy aliases kept for ranker filter compatibility (mapped by lifecycle).
    "review_pending",
    "screening",
    "screening_complete",
)


RANK_SCORE_SCALE = "0_100"
RANK_SCORE_MAX = 100.0
DIRECT_POSITION_MATCH_BOOST = 25.0
STATUS_MATCH_BOOST = 10.0


def _candidate_dedupe_key(candidate: dict[str, Any]) -> str:
    name = str(candidate.get("name") or "").strip().lower()
    if name:
        return f"name:{name}"
    phone = str(candidate.get("phone") or "").strip()
    if phone:
        return f"phone:{phone}"
    return f"app:{candidate.get('app_key')}"


def _dedupe_ranked_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest application per person unless the user asks for all apps.

    The HR user usually asks "who are the candidates?", not "show every
    application row". Without this, one person with three applications can crowd
    out direct matches from other people.
    """

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _candidate_dedupe_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _rank_candidates_parameters_catalog(legacy: Any, request: Any) -> dict[str, Any]:
    """Return the live position vocabulary for this company so GPT picks from
    real values instead of inventing strings like 'instagram marketing'."""

    company_code = _resolve_company_code(legacy, request) or ""
    positions: list[dict[str, Any]] = []
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT DISTINCT position_code, position_title FROM applications WHERE company_code=%s AND position_code IS NOT NULL AND {legacy.production_application_predicate('applications')} ORDER BY position_code",
                    (company_code,),
                )
                rows = cur.fetchall()
        for row in rows:
            if isinstance(row, dict):
                positions.append({"code": row.get("position_code"), "title": row.get("position_title")})
            elif isinstance(row, (list, tuple)) and row:
                positions.append({"code": row[0], "title": row[1] if len(row) > 1 else None})
    except Exception:
        positions = []
    return {
        "company_code": company_code,
        "position": [p["code"] for p in positions if p.get("code")],
        "position_titles": {p["code"]: p.get("title") for p in positions if p.get("code")},
        "status": list(CANDIDATE_STATUSES),
        "policy": "When the user names a position or status, pick the closest matching code from the lists above. If you can't match confidently, leave the parameter null — the executor will rank semantically using the user's words. Never invent values not in these lists.",
    }


def _rank_candidates_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Semantic-first ranker.

    Voyage embedding is the primary ranking signal. Position and status from
    GPT are *boosts*, never WHERE-clause filters. This means a query like
    'instagram marketing' will reach Marketing Specialist and Social Media
    Manager candidates via CV similarity, even if the position string GPT
    chose has zero literal matches in applications.position_code.
    """

    legacy = ctx.legacy
    action = ctx.action
    company_code = _resolve_company_code(legacy, ctx.request) or ""
    default_top_n = getattr(legacy, "RANK_CANDIDATES_DEFAULT_TOP_N", 5)
    max_top_n = getattr(legacy, "RANK_CANDIDATES_MAX_TOP_N", 10)
    pool_limit = getattr(legacy, "RANK_CANDIDATES_POOL_LIMIT", 200)

    requested_top_n = int(action.get("top_n") or 0)
    desired_top_n = requested_top_n if requested_top_n > 0 else default_top_n
    capped = desired_top_n > max_top_n
    top_n = max(1, min(desired_top_n, max_top_n))

    try:
        include_assessment = bool(legacy.company_has_module(company_code, "assessments"))
    except Exception:
        include_assessment = False

    query = str(action.get("query") or action.get("prompt_text") or "").strip()
    position_hint_raw = str(action.get("position") or "").strip()
    position_hint = position_hint_raw.upper() if position_hint_raw else None
    status_hint = str(action.get("status") or "").strip().lower() or None

    catalog = _rank_candidates_parameters_catalog(legacy, ctx.request)
    valid_positions = {str(code).upper(): code for code in (catalog.get("position") or [])}
    titles_by_code = {str(code).upper(): title for code, title in (catalog.get("position_titles") or {}).items()}
    valid_position_titles_upper = {str(t or "").upper(): code for code, t in titles_by_code.items() if t}
    matched_position_code: str | None = None
    if position_hint:
        if position_hint in valid_positions:
            matched_position_code = valid_positions[position_hint]
        elif position_hint in valid_position_titles_upper:
            matched_position_code = valid_position_titles_upper[position_hint]
    if status_hint and status_hint not in {s.lower() for s in CANDIDATE_STATUSES}:
        status_hint = None

    ranking_prompt = query
    if position_hint and titles_by_code.get(position_hint):
        ranking_prompt = (ranking_prompt + " " + titles_by_code[position_hint]).strip()
    elif position_hint_raw and not matched_position_code:
        ranking_prompt = (ranking_prompt + " " + position_hint_raw).strip()
    if not ranking_prompt:
        ranking_prompt = position_hint_raw or ""

    try:
        terms = legacy.normalized_search_terms(ranking_prompt, matched_position_code or "")
    except Exception:
        terms = []
    try:
        query_vector = legacy.embed_rank_query(ranking_prompt) if ranking_prompt else None
    except Exception:
        query_vector = None
    query_vector_literal = legacy.pgvector_literal(query_vector) if query_vector else None

    where = ["a.company_code=%s"]
    if hasattr(legacy, "production_application_predicate"):
        where.append(legacy.production_application_predicate("a"))
    params: list[Any] = [company_code]
    finalized = {"hired", "rejected", "withdrawn"}
    if status_hint in finalized:
        pass
    else:
        where.append("a.status NOT IN ('hired','rejected','withdrawn')")
    if status_hint == "screening_complete":
        where.append(
            "("
            "a.status=%s "
            "OR a.screening_status='complete' "
            "OR a.raw_json->'screening'->>'status'='complete'"
            ")"
        )
        params.append(status_hint)
    where_sql = " AND ".join(where)

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS count FROM applications a WHERE {where_sql}", params)
            count_row = cur.fetchone()
            total = int((count_row.get("count") if isinstance(count_row, dict) else (count_row[0] if count_row else 0)) or 0)
            if query_vector_literal:
                select_params = [query_vector_literal, *params, query_vector_literal, pool_limit]
                cur.execute(
                    f"""
                    SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                           c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                           sd.content AS semantic_content,
                           1 - (sd.embedding <=> %s::vector) AS semantic_similarity
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    LEFT JOIN semantic_documents sd ON sd.entity_type='application' AND sd.entity_key=a.app_key
                    WHERE {where_sql}
                    ORDER BY (sd.embedding <=> %s::vector) ASC NULLS LAST,
                             CASE a.status
                               WHEN 'screening_complete' THEN 0
                               WHEN 'review_pending' THEN 1
                               WHEN 'shortlisted' THEN 2
                               WHEN 'screening' THEN 3
                               ELSE 4
                             END,
                             a.ingested_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    select_params,
                )
            else:
                select_params = [*params, pool_limit]
                cur.execute(
                    f"""
                    SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                           c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                           NULL AS semantic_content,
                           NULL::double precision AS semantic_similarity
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    WHERE {where_sql}
                    ORDER BY CASE a.status
                               WHEN 'screening_complete' THEN 0
                               WHEN 'review_pending' THEN 1
                               WHEN 'shortlisted' THEN 2
                               WHEN 'screening' THEN 3
                               ELSE 4
                             END,
                             a.ingested_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    select_params,
                )
            rows = [dict(row) for row in cur.fetchall()]

    scored: list[dict[str, Any]] = []
    for row in rows:
        try:
            score, breakdown, evidence, confidence, matched_terms = legacy.rank_candidate_row(
                row,
                query=query,
                position=matched_position_code or "",
                terms=terms,
            )
        except Exception:
            score, breakdown, evidence, confidence, matched_terms = 0.0, {}, [], "low", []
        position_code_value = str(row.get("position_code") or "").upper()
        position_title_value = str(row.get("position_title") or "").upper()
        direct_position_match = bool(
            matched_position_code
            and (position_code_value == matched_position_code.upper() or matched_position_code.upper() in position_title_value)
        )
        if direct_position_match:
            score = min(RANK_SCORE_MAX, float(score or 0) + DIRECT_POSITION_MATCH_BOOST)
            breakdown = {**(breakdown or {}), "registry_position_boost": DIRECT_POSITION_MATCH_BOOST}
            evidence = list(evidence or []) + [f"matches requested position {matched_position_code}"]
        row_screening_status = str(row.get("screening_status") or screening.get("status") or "").lower()
        status_matches = str(row.get("status") or "").lower() == status_hint or (
            status_hint == "screening_complete" and row_screening_status == "complete"
        )
        if status_hint and status_matches:
            score = min(RANK_SCORE_MAX, float(score or 0) + STATUS_MATCH_BOOST)
            breakdown = {**(breakdown or {}), "registry_status_boost": STATUS_MATCH_BOOST}
            evidence = list(evidence or []) + [f"matches requested status {status_hint}"]
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        screening = raw_json.get("screening") if isinstance(raw_json.get("screening"), dict) else {}
        scored.append(
            {
                "score": round(float(score or 0), 2),
                "score_breakdown": breakdown,
                "ranking_contract": {
                    "score_scale": RANK_SCORE_SCALE,
                    "score_max": RANK_SCORE_MAX,
                    "direct_position_match": direct_position_match,
                    "matched_position_code": matched_position_code,
                    "dedupe_key": _candidate_dedupe_key({
                        "phone": row.get("phone"),
                        "name": legacy.candidate_name_from_row(row) if hasattr(legacy, "candidate_name_from_row") else (row.get("candidate_name") or row.get("phone")),
                        "app_key": row.get("app_key"),
                    }),
                },
                "confidence": confidence,
                "evidence": evidence,
                "app_key": row.get("app_key"),
                "phone": row.get("phone"),
                "name": legacy.candidate_name_from_row(row) if hasattr(legacy, "candidate_name_from_row") else (row.get("candidate_name") or row.get("phone")),
                "position_code": row.get("position_code"),
                "position_title": row.get("position_title"),
                "status": row.get("status"),
                "screening_status": row.get("screening_status") or screening.get("status"),
                "semantic_similarity": row.get("semantic_similarity"),
                "matched_terms": matched_terms,
                "reasons": list(evidence or [])[:4],
                "application": legacy.prehire_application_summary(row, include_raw=True, include_assessment=include_assessment) if hasattr(legacy, "prehire_application_summary") else None,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    deduped = _dedupe_ranked_candidates(scored)
    top = deduped[:top_n]

    if top:
        message = f"Top {len(top)} candidate{'s' if len(top) != 1 else ''} ranked semantically."
    else:
        message = "I scanned the whole pool semantically and didn't find a match for that."

    return {
        "action_type": "rank_candidates",
        "success": True,
        "status": "completed",
        "message": message,
        "query": query,
        "filters": {
            "company_code": company_code,
            "position": matched_position_code,
            "position_raw": position_hint_raw or None,
            "status": status_hint,
            "literal_position_filter": False,
            "ranking_mode": "semantic_first_with_boosts",
        },
        "requested_top_n": requested_top_n or None,
        "shown_top_n": top_n,
        "capped": capped,
        "embedding": {"provider": "voyage", "model": "voyage-4", "used": bool(query_vector_literal)},
        "total_matching": total,
        "pool_scanned": len(rows),
        "ranked_count": len(scored),
        "deduped_count": len(deduped),
        "ranking_contract": {
            "score_scale": RANK_SCORE_SCALE,
            "score_max": RANK_SCORE_MAX,
            "direct_position_match_boost": DIRECT_POSITION_MATCH_BOOST,
            "status_match_boost": STATUS_MATCH_BOOST,
            "dedupe": "one_result_per_phone_or_name",
        },
        "candidates": top,
    }


def _get_candidate_status_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Read-only: return the candidate's current application status, enriched
    with full candidate_context so even a 'is he shortlisted?' question gets
    answered alongside relevant CV signal when the user follows up.
    """

    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("get_candidate_status", "look up")
    context = _load_candidate_context(legacy, app, ctx.action, ctx.state, ctx.request)
    name = context.get("name") or _candidate_name(app, ctx.action)
    raw_status = str(app.get("status") or "unknown")
    phrased = {
        "review_pending": f"{name}'s application is still under review.",
        "shortlisted": f"{name} is shortlisted.",
        "hired": f"{name} is hired.",
        "rejected": f"{name} was rejected.",
        "withdrawn": f"{name} withdrew the application.",
    }.get(raw_status, f"{name}'s application status is {raw_status}.")
    return {
        "action_type": "get_candidate_status",
        "success": True,
        "status": "completed",
        "message": phrased,
        "candidate_status": raw_status,
        "candidate_context": legacy.json_safe(context),
        "application": legacy.json_safe(app),
    }


def _slug_position_code(title: str | None) -> str:
    raw = str(title or "").strip()
    tokens = re.findall(r"[A-Za-z0-9]+", raw.upper())
    return "_".join(tokens[:6]) or "JOB"


def _as_salary(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(str(value).replace(",", "").replace("KD", "").replace("kd", "").strip())
    except Exception:
        return None


def _fallback_screening_questions_for_role(title: str, requirements: list[str] | None = None) -> list[dict[str, Any]]:
    normalized = str(title or "").lower()
    role_label = str(title or "this role").strip() or "this role"
    questions: list[dict[str, Any]] = [
        {
            "key": "visa_status",
            "question": "What is your current visa or residency status in Kuwait?",
            "required": True,
            "allow_cv_prefill": False,
            "requires_candidate_confirmation": True,
            "answer_type": "text",
            "source_policy": "candidate_only",
        },
        {
            "key": "salary_expectation",
            "question": "What is your expected monthly salary in KD?",
            "required": True,
            "allow_cv_prefill": False,
            "requires_candidate_confirmation": True,
            "answer_type": "text",
            "source_policy": "candidate_only",
        },
        {
            "key": "availability",
            "question": "When can you start?",
            "required": True,
            "allow_cv_prefill": False,
            "requires_candidate_confirmation": True,
            "answer_type": "text",
            "source_policy": "candidate_only",
        },
    ]
    if "account" in normalized or "finance" in normalized or "excel" in normalized:
        questions.extend(
            [
                {
                    "key": "accounting_experience",
                    "question": "How many years of accounting, bookkeeping, or finance experience do you have?",
                    "required": True,
                    "allow_cv_prefill": True,
                    "requires_candidate_confirmation": False,
                    "answer_type": "text",
                    "source_policy": "cv_or_candidate",
                },
                {
                    "key": "excel_level",
                    "question": "Which Excel functions or reporting tasks can you do confidently?",
                    "required": True,
                    "allow_cv_prefill": True,
                    "requires_candidate_confirmation": False,
                    "answer_type": "text",
                    "source_policy": "cv_or_candidate",
                },
                {
                    "key": "accounting_tools",
                    "question": "Which accounting software, ERP, or finance tools have you used?",
                    "required": False,
                    "allow_cv_prefill": True,
                    "requires_candidate_confirmation": False,
                    "answer_type": "text",
                    "source_policy": "cv_or_candidate",
                },
            ]
        )
    else:
        questions.extend(
            [
                {
                    "key": "relevant_experience",
                    "question": f"Briefly describe your relevant experience for {role_label}.",
                    "required": True,
                    "allow_cv_prefill": True,
                    "requires_candidate_confirmation": False,
                    "answer_type": "text",
                    "source_policy": "cv_or_candidate",
                },
                {
                    "key": "tools",
                    "question": "Which tools, software, or systems are you strongest with?",
                    "required": False,
                    "allow_cv_prefill": True,
                    "requires_candidate_confirmation": False,
                    "answer_type": "text",
                    "source_policy": "cv_or_candidate",
                },
            ]
        )
    return questions


def _generate_screening_questions_for_role(ctx: ExecutionContext, *, title: str, requirements: list[str] | None = None) -> list[dict[str, Any]]:
    legacy = ctx.legacy
    fallback = _fallback_screening_questions_for_role(title, requirements)
    provider = legacy.planner_provider_config() if hasattr(legacy, "planner_provider_config") else None
    if not provider:
        return fallback
    payload = {
        "role_title": title,
        "salary_min": ctx.action.get("salary_min") or ctx.action.get("salary"),
        "salary_max": ctx.action.get("salary_max") or ctx.action.get("salary"),
        "employment_type": ctx.action.get("employment_type"),
        "requirements": requirements or [],
        "defaults_required": ["visa_status", "salary_expectation", "availability"],
        "rules": [
            "Return JSON only with screening_questions array.",
            "Always include visa_status, salary_expectation, availability as candidate-only confirmation questions.",
            "Add 2-4 role-specific questions.",
            "Set allow_cv_prefill true only for experience/skills/tools/project evidence visible in a CV.",
            "Do not ask illegal or highly sensitive questions.",
        ],
    }
    system = "You design concise candidate screening questions for a Kuwait HR application flow. Return JSON only."
    if provider.get("api") == "openai-responses":
        body = {"model": provider["model"], "temperature": 0, "input": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    else:
        body = {"model": provider["model"], "temperature": 0, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    try:
        req = urllib.request.Request(
            provider["url"],
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=18) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
        raw_text = legacy.extract_model_text(parsed) if hasattr(legacy, "extract_model_text") else ""
        data = legacy.extract_json_object(raw_text) if hasattr(legacy, "extract_json_object") else None
        raw_questions = data.get("screening_questions") if isinstance(data, dict) else None
        if not isinstance(raw_questions, list):
            return fallback
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_questions:
            if not isinstance(item, dict):
                continue
            key = re.sub(r"[^a-z0-9_]+", "_", str(item.get("key") or "").lower()).strip("_")
            question = str(item.get("question") or "").strip()
            if not key or not question or key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "key": key,
                    "question": question,
                    "required": bool(item.get("required", True)),
                    "allow_cv_prefill": bool(item.get("allow_cv_prefill", False)),
                    "requires_candidate_confirmation": bool(item.get("requires_candidate_confirmation", not item.get("allow_cv_prefill", False))),
                    "answer_type": str(item.get("answer_type") or "text"),
                    "source_policy": str(item.get("source_policy") or ("cv_or_candidate" if item.get("allow_cv_prefill") else "candidate_only")),
                }
            )
        required_defaults = {"visa_status", "salary_expectation", "availability"}
        present = {item["key"] for item in out}
        if not required_defaults.issubset(present):
            return fallback
        return out[:8]
    except Exception:
        return fallback


def _create_job_opening_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    title = str(ctx.action.get("title") or ctx.action.get("position_title") or "").strip()
    salary = _as_salary(ctx.action.get("salary"))
    salary_min = _as_salary(ctx.action.get("salary_min")) or salary
    salary_max = _as_salary(ctx.action.get("salary_max")) or salary_min
    missing: list[str] = []
    if not title:
        missing.append("title")
    if missing:
        return {
            "action_type": "create_job_opening",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": missing,
            "message": "I need the job title before I can save the draft.",
        }
    company_code = _resolve_company_code(ctx.legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "create_job_opening",
            "success": False,
            "status": "failed",
            "error": "company_context_required",
            "message": "I could not verify the company context, so I did not create the job.",
        }
    position_code = str(ctx.action.get("position_code") or "").strip().upper() or _slug_position_code(title)
    apply_code = f"APPLY-{company_code}-{position_code}"
    requirements = ctx.action.get("requirements") if isinstance(ctx.action.get("requirements"), list) else []
    screening_questions = _generate_screening_questions_for_role(ctx, title=title, requirements=requirements)
    return {
        "action_type": "create_job_opening",
        "success": True,
        "status": "ready",
        "message": f"Ready to save {title} as a draft for HR review.",
        "company_code": company_code,
        "title": title,
        "position_code": position_code,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": str(ctx.action.get("currency") or "KD").upper(),
        "employment_type": ctx.action.get("employment_type") or ("Full-time" if "full" in str(ctx.action.get("prompt_text") or "").lower() else None),
        "description": ctx.action.get("description"),
        "requirements": requirements,
        "screening_questions": screening_questions,
        "apply_code": apply_code,
        "apply_link": None,
        "qr_image_url": None,
        "whatsapp_number": None,
    }


def _create_job_opening_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    plan = _create_job_opening_preflight(ctx)
    if plan.get("status") != "ready":
        return plan
    import prehire_jobs as jobs

    # Never silently reopen an existing role via upsert.
    try:
        created = jobs.create_job(
            company=str(plan["company_code"]),
            db_connect=legacy.db_connect,
            actor_user_id=str(getattr(ctx.request, "actor_user_id", None) or "") or None,
            payload={
                "title": plan["title"],
                "position_code": plan["position_code"],
                "salary_min": plan["salary_min"],
                "salary_max": plan["salary_max"],
                "currency": plan.get("currency") or "KD",
                "employment_type": plan.get("employment_type"),
                "description": plan.get("description") or "",
                "requirements": plan.get("requirements") or [],
                "requirements_en": plan.get("requirements") or [],
            },
            as_draft=True,
        )
    except jobs.JobsError as exc:
        if exc.code == "position_code_conflict":
            return {
                "action_type": "create_job_opening",
                "success": False,
                "status": "needs_clarification",
                "needs_clarification": True,
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        return {
            "action_type": "create_job_opening",
            "success": False,
            "status": "failed",
            "error": exc.code,
            "message": exc.message,
        }
    share = jobs.assistant_external_share_fields(created)
    return {
        "action_type": "create_job_opening",
        "success": True,
        "status": "completed",
        "message": f"Saved {plan['title']} as a draft. HR must complete and approve the candidate-facing content before publishing.",
        "position": legacy.json_safe(created),
        "apply_code": share.get("apply_code") or plan["apply_code"],
        "apply_link": share.get("apply_link"),
        "qr_image_url": share.get("qr_image_url"),
        "qr_send_result": None,
        "shareable": share.get("shareable"),
        "accepts_applications": share.get("accepts_applications"),
        "eligibility_reason": share.get("eligibility_reason"),
        "authority_source": "positions",
    }


def _find_job_opening_matches(legacy: Any, company: str, *, position_code: str | None, title: str | None) -> list[dict[str, Any]]:
    """Resolve a job opening by exact APPLY/position code or fuzzy title match
    against the canonical `positions` table only. Applications never synthesize jobs."""
    code = str(position_code or "").strip().upper()
    term = str(title or "").strip()
    if not code and not term:
        return []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            if code:
                cur.execute(
                    """
                    SELECT position_code, COALESCE(title, position_code) AS position_title
                    FROM positions
                    WHERE company_code=%s
                      AND NULLIF(TRIM(COALESCE(position_code, '')), '') IS NOT NULL
                      AND (upper(position_code)=%s OR upper(COALESCE(apply_code, ''))=%s)
                    """,
                    (company, code, code),
                )
            else:
                like = f"%{legacy._ilike_escape(term)}%"
                cur.execute(
                    """
                    SELECT position_code, COALESCE(title, position_code) AS position_title
                    FROM positions
                    WHERE company_code=%s
                      AND NULLIF(TRIM(COALESCE(position_code, '')), '') IS NOT NULL
                      AND COALESCE(title, position_code) ILIKE %s
                    """,
                    (company, like),
                )
            rows = [dict(row) for row in cur.fetchall()]
    return rows


def _job_opening_status_preflight(ctx: ExecutionContext, *, target_status: str) -> dict[str, Any]:
    legacy = ctx.legacy
    action_name = {
        "closed": "close_job_opening",
        "paused": "pause_job_opening",
        "open": "reopen_job_opening",
    }.get(target_status, "close_job_opening")
    verb = {
        "closed": "close",
        "paused": "pause",
        "open": "reopen or resume",
    }.get(target_status, "update")
    company_code = _resolve_company_code(legacy, ctx.request) or ""
    position_code = str(ctx.action.get("position_code") or "").strip()
    title = str(ctx.action.get("title") or ctx.action.get("position_title") or "").strip()
    if not position_code and not title:
        return {
            "action_type": action_name,
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["title"],
            "message": f"Which job opening should I {verb}? Tell me the job title or its APPLY code.",
        }
    matches = _find_job_opening_matches(legacy, company_code, position_code=position_code, title=title)
    if not matches:
        return {
            "action_type": action_name,
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "message": f"I couldn't find a job opening matching \"{position_code or title}\".",
        }
    if len(matches) > 1:
        options = "; ".join(f"{m['position_title']} ({m['position_code']})" for m in matches[:8])
        return {
            "action_type": action_name,
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "message": f"I found more than one match — which one? {options}",
        }
    match = matches[0]
    return {
        "action_type": action_name,
        "success": True,
        "status": "ready",
        "message": f"{verb.capitalize()} {match['position_title']} ({match['position_code']})?",
        "company_code": company_code,
        "position_code": match["position_code"],
        "position_title": match["position_title"],
        "target_status": target_status,
    }


def _job_opening_status_executor(ctx: ExecutionContext, *, target_status: str) -> dict[str, Any]:
    legacy = ctx.legacy
    plan = _job_opening_status_preflight(ctx, target_status=target_status)
    if plan.get("status") != "ready":
        return plan
    row = legacy.dashboard_set_position_status(plan["company_code"], plan["position_code"], target_status)
    verb = {
        "closed": "closed to new applicants",
        "paused": "paused (not accepting new applicants)",
        "open": "open to new applicants",
    }.get(target_status, f"set to {target_status}")
    import prehire_jobs as jobs

    share = jobs.assistant_external_share_fields(row if isinstance(row, dict) else {})
    return {
        **plan,
        "status": "completed",
        "message": f"{row.get('title') or plan['position_code']} is now {verb}.",
        "position": legacy.json_safe(row),
        "apply_code": share.get("apply_code"),
        "apply_link": share.get("apply_link"),
        "qr_image_url": share.get("qr_image_url"),
        "shareable": share.get("shareable"),
        "accepts_applications": share.get("accepts_applications"),
        "eligibility_reason": share.get("eligibility_reason"),
    }


def _close_job_opening_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_preflight(ctx, target_status="closed")


def _close_job_opening_executor(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_executor(ctx, target_status="closed")


def _pause_job_opening_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_preflight(ctx, target_status="paused")


def _pause_job_opening_executor(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_executor(ctx, target_status="paused")


def _reopen_job_opening_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_preflight(ctx, target_status="open")


def _reopen_job_opening_executor(ctx: ExecutionContext) -> dict[str, Any]:
    return _job_opening_status_executor(ctx, target_status="open")


CANDIDATE_WORKFLOW_ALLOWED_STEPS = {
    "shortlist_candidate",
    "hire_candidate",
    "reject_candidate",
    "send_email",
    "notify_candidate",
    "send_interview_invite",
    "send_video_interview",
    "send_assessment",
    "send_screening_questions",
    "schedule_interview",
}


def _workflow_steps_from_action(action: dict[str, Any]) -> list[str]:
    raw_steps = action.get("steps")
    steps: list[str] = []
    if isinstance(raw_steps, list):
        steps = [str(step).strip() for step in raw_steps if str(step or "").strip()]
    elif isinstance(raw_steps, str) and raw_steps.strip():
        steps = [part.strip() for part in raw_steps.split(",") if part.strip()]
    text = " ".join(
        str(action.get(key) or "")
        for key in ("workflow_goal", "prompt_text", "message_text", "purpose")
    ).lower()
    if not steps:
        wants_video_interview = any(token in text for token in ("video interview", "ai interview", "ai video", "recorded interview", "asynchronous interview", "async interview"))
        if "shortlist" in text:
            steps.append("shortlist_candidate")
        if "hire" in text:
            steps.append("hire_candidate")
        if "reject" in text:
            steps.append("reject_candidate")
        if "assessment" in text:
            steps.append("send_assessment")
        if wants_video_interview:
            steps.append("send_video_interview")
        if "screening" in text and "question" in text:
            steps.append("send_screening_questions")
        interviewish = any(token in text for token in ("interview", "meeting", "meet", "calendar"))
        scheduleish = any(token in text for token in ("schedule", "book", "set up", "calendar"))
        notifyish = any(token in text for token in ("notify", "whatsapp", "email", "send", "invite", "link"))
        if interviewish and scheduleish:
            steps.append("schedule_interview")
        if interviewish and notifyish and "send_video_interview" not in steps:
            steps.append("send_interview_invite")
        elif "email" in text:
            steps.append("send_email")
        if ("whatsapp" in text or "notify" in text) and "send_interview_invite" not in steps:
            steps.append("notify_candidate")
    deduped: list[str] = []
    for step in steps:
        normalized = step.strip()
        if normalized in CANDIDATE_WORKFLOW_ALLOWED_STEPS and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _workflow_message_text(action: dict[str, Any], app: dict[str, Any], *, default: str) -> str:
    return str(action.get("message_text") or action.get("message") or default).strip()


def _workflow_order_steps(steps: list[str]) -> list[str]:
    priority = {
        "shortlist_candidate": 10,
        "hire_candidate": 10,
        "reject_candidate": 10,
        "send_assessment": 20,
        "send_screening_questions": 20,
        "schedule_interview": 30,
        "send_video_interview": 35,
        "send_interview_invite": 40,
        "send_email": 40,
        "notify_candidate": 40,
    }
    return sorted(steps, key=lambda step: priority.get(step, 50))


def _workflow_meet_link(schedule_result: dict[str, Any] | None) -> str | None:
    if not isinstance(schedule_result, dict):
        return None
    for key in ("hangoutLink", "meet_link", "google_meet_link"):
        if schedule_result.get(key):
            return str(schedule_result[key])
    result = schedule_result.get("result") if isinstance(schedule_result.get("result"), dict) else {}
    event = result.get("event") if isinstance(result.get("event"), dict) else {}
    if not event and isinstance(result.get("json"), dict):
        result_json = result.get("json") or {}
        event = result_json.get("event") if isinstance(result_json.get("event"), dict) else {}
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])
    conference = event.get("conferenceData") if isinstance(event.get("conferenceData"), dict) else {}
    entry_points = conference.get("entryPoints") if isinstance(conference.get("entryPoints"), list) else []
    for entry in entry_points:
        if isinstance(entry, dict) and entry.get("entryPointType") == "video" and entry.get("uri"):
            return str(entry["uri"])
    return None


def _workflow_time_label(schedule_result: dict[str, Any] | None, fallback: str | None = None) -> str:
    raw_time = None
    if isinstance(schedule_result, dict):
        raw_time = schedule_result.get("start")
        result = schedule_result.get("result") if isinstance(schedule_result.get("result"), dict) else {}
        event = result.get("event") if isinstance(result.get("event"), dict) else {}
        if not event and isinstance(result.get("json"), dict):
            result_json = result.get("json") or {}
            event = result_json.get("event") if isinstance(result_json.get("event"), dict) else {}
        start = event.get("start") if isinstance(event.get("start"), dict) else {}
        raw_time = raw_time or start.get("dateTime")
    if raw_time:
        try:
            parsed = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            kuwait = parsed.astimezone(ZoneInfo("Asia/Kuwait"))
            day = kuwait.strftime("%A")
            month = kuwait.strftime("%B")
            hour = kuwait.strftime("%I").lstrip("0") or "0"
            return f"{day}, {month} {kuwait.day} at {hour}:{kuwait.strftime('%M %p')} Kuwait time"
        except Exception:
            return str(raw_time)
    return str(fallback or "").strip()


def _schedule_artifact_from_workflow_result(result: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    schedule = artifacts.get("schedule_interview") if isinstance(artifacts.get("schedule_interview"), dict) else None
    if schedule:
        return schedule
    step_results = result.get("step_results") if isinstance(result.get("step_results"), list) else []
    for item in step_results:
        if not isinstance(item, dict) or item.get("step") != "schedule_interview":
            continue
        step_result = item.get("result") if isinstance(item.get("result"), dict) else None
        if step_result:
            return step_result
    return None


def _prior_workflow_artifacts(ctx: ExecutionContext, app_key: str | None) -> dict[str, Any]:
    """Load reusable truth from the previous scoped workflow turn.

    Follow-up requests like "send him the link on WhatsApp" should use the
    actual interview_event artifact created by the prior schedule step instead
    of relying on GPT to remember or recreate the Meet URL.
    """

    if not isinstance(ctx.state, dict):
        return {}
    outputs = ctx.state.get("last_tool_outputs") if isinstance(ctx.state.get("last_tool_outputs"), list) else []
    for output in reversed(outputs):
        if not isinstance(output, dict):
            continue
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        if result.get("action_type") != "execute_candidate_workflow":
            continue
        candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
        application = result.get("application") if isinstance(result.get("application"), dict) else {}
        candidate_app_key = candidate.get("app_key") or application.get("app_key")
        if app_key and candidate_app_key and str(candidate_app_key) != str(app_key):
            continue
        schedule = _schedule_artifact_from_workflow_result(result)
        if schedule:
            artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
            return {
                **artifacts,
                "schedule_interview": schedule,
                "candidate": candidate or artifacts.get("candidate") or {},
                "application": application or artifacts.get("application") or {},
                "artifact_source": "previous_execute_candidate_workflow",
            }
    return {}


def _workflow_communication_message(
    action: dict[str, Any],
    app: dict[str, Any],
    artifacts: dict[str, Any],
    *,
    default: str,
) -> str:
    explicit = str(action.get("message_text") or action.get("message") or "").strip()
    schedule_result = artifacts.get("schedule_interview") if isinstance(artifacts.get("schedule_interview"), dict) else None
    meet_link = _workflow_meet_link(schedule_result)
    time_label = _workflow_time_label(schedule_result, str(action.get("datetime_text") or action.get("interview_time") or "").strip())
    candidate_name = (artifacts.get("candidate") or {}).get("candidate_name") if isinstance(artifacts.get("candidate"), dict) else None
    name = candidate_name or _candidate_name(app, action)
    role = app.get("position_title") or app.get("position_code") or "the role"
    completed_steps = set(artifacts.get("completed_steps") if isinstance(artifacts.get("completed_steps"), list) else [])
    status_changed_to_shortlisted = "shortlist_candidate" in completed_steps
    if schedule_result and (meet_link or time_label):
        lines = [
            f"Hi {name},",
            "",
        ]
        if status_changed_to_shortlisted:
            lines.append(f"You've been shortlisted for {role}.")
        if explicit and meet_link and meet_link not in explicit:
            lines = [explicit.rstrip(".")]
            if time_label and time_label not in explicit:
                lines.append(f"Time: {time_label}")
            lines.append(f"Google Meet: {meet_link}")
            return "\n".join(lines)
        if time_label and meet_link:
            lines.append(f"We'd like to invite you to an online interview at {time_label} via Google Meet: {meet_link}")
        elif time_label:
            lines.append(f"We'd like to invite you to an online interview at {time_label}.")
        elif meet_link:
            lines.append(f"We'd like to invite you to an online interview via Google Meet: {meet_link}")
        lines.extend(["", "Best,", "Wathefni HR"])
        return "\n".join(lines)
    if explicit:
        return explicit
    return default


def _workflow_invite_channel(action: dict[str, Any], contact: dict[str, Any]) -> str:
    channel = str(action.get("invite_channel") or "").strip().lower()
    if channel in {"email", "whatsapp"}:
        return channel
    text = " ".join(str(action.get(key) or "") for key in ("workflow_goal", "prompt_text", "message_text")).lower()
    if "whatsapp" in text:
        return "whatsapp"
    if "email" in text:
        return "email"
    return "email" if contact.get("email") else "whatsapp"


def _dedupe_workflow_steps(steps: list[str]) -> list[str]:
    out: list[str] = []
    for step in steps:
        if step not in out:
            out.append(step)
    return out


INTERVIEW_ACTION_RESULT_KEYS = (
    "interview_created",
    "calendar_event_created",
    "google_meet_link",
    "calendar_invite_sent",
    "candidate_invited",
    "candidate_notified",
    "notification_channel",
    "sent_subject",
    "sent_body",
    "public_link",
    "interview",
)


def _workflow_interview_fields(artifacts: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for artifact_name in ("schedule_interview", "send_video_interview", "send_interview_invite", "send_email", "notify_candidate"):
        artifact = artifacts.get(artifact_name) if isinstance(artifacts.get(artifact_name), dict) else {}
        for key in INTERVIEW_ACTION_RESULT_KEYS:
            value = artifact.get(key)
            if value not in (None, "", [], {}) or key not in fields:
                fields[key] = value
    return {key: value for key, value in fields.items() if value not in (None, "", [], {})}


def _candidate_workflow_plan(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("execute_candidate_workflow", "plan workflow for")
    contact = legacy.candidate_contact(app) if hasattr(legacy, "candidate_contact") else {}
    name = (contact or {}).get("name") or _candidate_name(app, ctx.action)
    steps = _workflow_steps_from_action(ctx.action)
    if not steps:
        return {
            "action_type": "execute_candidate_workflow",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_required_fields": ["steps"],
            "message": f"What should I do with {name}? For example: shortlist, send assessment, schedule interview, email, or WhatsApp.",
            "application": legacy.json_safe(app),
        }
    missing_fields: list[str] = []
    blocked_steps: list[dict[str, Any]] = []
    invite_channel = _workflow_invite_channel(ctx.action, contact or {})
    wants_schedule = "schedule_interview" in steps
    wants_video_interview = "send_video_interview" in steps
    wants_scheduled_invite = "send_interview_invite" in steps
    wants_email = "send_email" in steps or (invite_channel == "email" and not wants_video_interview)
    datetime_text = str(ctx.action.get("datetime_text") or ctx.action.get("interview_time") or ctx.action.get("when") or ctx.action.get("datetime") or "").strip()
    allow_fallback = str(ctx.action.get("allow_fallback")).lower() in {"true", "1", "yes"}
    exact_interview = _scheduled_interview_for_current_app(legacy, app) if wants_scheduled_invite else None
    if wants_scheduled_invite and not exact_interview:
        missing_fields.append("interview_type_choice")
        blocked_steps.append(
            {
                "step": "send_interview_invite",
                "reason": "no_scheduled_interview_for_current_application",
                "fallback": "send_video_interview",
                "safe_user_message": f"No scheduled interview exists for {name}'s current application yet. You can schedule one first, or send an AI video interview link instead.",
            }
        )
    if wants_schedule and not (contact or {}).get("email"):
        blocked_steps.append(
            {
                "step": "schedule_interview",
                "reason": "candidate_email_missing_for_calendar_invite",
                "fallback": "notify_candidate",
            }
        )
    if wants_email and not (contact or {}).get("email"):
        blocked_steps.append(
            {
                "step": "send_email",
                "reason": "candidate_email_missing",
                "fallback": "notify_candidate",
            }
        )
    if not (contact or {}).get("email") and allow_fallback:
        steps = [
            "notify_candidate" if step in {"send_email", "schedule_interview"} else step
            for step in steps
        ]
        steps = _dedupe_workflow_steps(steps)
        blocked_steps = []
        invite_channel = "whatsapp"
        wants_schedule = False
    if wants_schedule and not datetime_text:
        missing_fields.append("datetime_text")
    if not missing_fields and not blocked_steps and steps == ["send_interview_invite"]:
        ready_message = f"Scheduled interview invite is ready for {name}."
    elif not missing_fields and not blocked_steps and steps == ["send_video_interview"]:
        ready_message = f"Video interview link is ready for {name}."
    else:
        ready_message = f"Workflow is ready for {name}."
    outbound_steps = [step for step in steps if step in OUTBOUND_PREVIEW_ACTIONS]
    preview = None
    if not missing_fields and not blocked_steps and outbound_steps:
        preview_ctx = ExecutionContext(
            request=ctx.request,
            action={**ctx.action, "action_type": outbound_steps[0], "preferred_channel": invite_channel},
            state=ctx.state,
            graph_state=ctx.graph_state,
            intent={**ctx.intent, "phase": "workflow_preview"},
            legacy=legacy,
        )
        preview = outbound_confirmation_preview(preview_ctx, outbound_steps[0], app)
        if preview and len(steps) > 1:
            preview = {
                **preview,
                "title": f"Confirm workflow for {name}",
                "action": " + ".join(_preview_action_title(step) for step in steps),
                "expected_result": f"{name} will receive the candidate-facing message after the workflow steps are ready.",
            }
            preview["confirmation_text"] = _format_confirmation_text(preview)
    workflow_card = {
        "kind": "workflow_preview",
        "title": f"Workflow for {name}",
        "status": "ready" if not missing_fields and not blocked_steps else "needs_clarification",
        "steps": [{"step": step, "status": "planned"} for step in steps],
        "channels": {
            "invite_channel": invite_channel,
            "meeting_type": ctx.action.get("meeting_type") or ("google_meet" if wants_schedule else None),
            "fallback_channel": ctx.action.get("fallback_channel") or ("whatsapp" if blocked_steps else None),
        },
        "people": [{"name": name, "app_key": app.get("app_key")}],
        "missing_fields": missing_fields,
        "blocked_steps": blocked_steps,
        "datetime_text": datetime_text or None,
    }
    return {
        "action_type": "execute_candidate_workflow",
        "success": not missing_fields and not blocked_steps,
        "status": "ready" if not missing_fields and not blocked_steps else "needs_clarification",
        "needs_clarification": bool(missing_fields or blocked_steps),
        "message": (
            ready_message
            if not missing_fields and not blocked_steps
            else next((str(item.get("safe_user_message")) for item in blocked_steps if isinstance(item, dict) and item.get("safe_user_message")), f"I need one detail before I can run this workflow for {name}.")
        ),
        "candidate": legacy.json_safe(legacy.candidate_lookup_match_payload(app) if hasattr(legacy, "candidate_lookup_match_payload") else app),
        "application": legacy.json_safe(app),
        "steps": steps,
        "invite_channel": invite_channel,
        "meeting_type": ctx.action.get("meeting_type") or ("google_meet" if wants_schedule else None),
        "datetime_text": datetime_text or None,
        "missing_fields": missing_fields,
        "blocked_steps": blocked_steps,
        "fallback_channel": ctx.action.get("fallback_channel") or ("whatsapp" if blocked_steps else None),
        "workflow_card": workflow_card,
        "instruction": (
            "Ask one targeted question. If datetime_text is missing, ask for the meeting time. "
            "If candidate_email_missing, tell the user the candidate has no email and ask whether to WhatsApp instead. "
            "Do not ask for generic confirmation yet."
        ),
        **({"confirmation_preview": preview, "confirmation_text": preview.get("confirmation_text")} if preview else {}),
    }


def _candidate_workflow_preflight(ctx: ExecutionContext) -> dict[str, Any]:
    return _candidate_workflow_plan(ctx)


def _execute_candidate_workflow_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    plan = _candidate_workflow_plan(ctx)
    if plan.get("status") != "ready":
        return plan
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("execute_candidate_workflow", "execute workflow for")
    steps = _workflow_order_steps(plan.get("steps") if isinstance(plan.get("steps"), list) else [])
    name = ((plan.get("candidate") or {}).get("candidate_name") if isinstance(plan.get("candidate"), dict) else None) or _candidate_name(app, ctx.action)
    results: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {
        **_prior_workflow_artifacts(ctx, app.get("app_key")),
        "candidate": plan.get("candidate") if isinstance(plan.get("candidate"), dict) else {},
        "application": legacy.json_safe(app),
    }
    success = True

    def run_atomic(step: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        step_key = str(ctx.action.get("idempotency_key") or "").strip() or f"workflow:{app.get('app_key')}:{step}"
        action = {
            **ctx.action,
            **(overrides or {}),
            "action_type": step,
            "app_key": app.get("app_key"),
            "subject_key": app.get("app_key"),
            "subject_type": "candidate",
            "subject_name": name,
            "idempotency_key": f"{step_key}:{step}",
        }
        atomic_ctx = ExecutionContext(
            request=ctx.request,
            action=action,
            state=ctx.state,
            graph_state=ctx.graph_state,
            intent={**ctx.intent, "workflow_step": step},
            legacy=legacy,
        )
        return execute(step, atomic_ctx)

    for step in steps:
        overrides: dict[str, Any] = {}
        if step == "send_email":
            overrides = {
                "purpose": ctx.action.get("purpose") or "interview_invite",
                "message_text": _workflow_communication_message(
                    ctx.action,
                    app,
                    {**artifacts, "completed_steps": [item["step"] for item in results if (item.get("result") or {}).get("status") == "completed"]},
                    default="We would like to invite you to an online interview. Please reply with your availability.",
                ),
            }
        elif step == "send_interview_invite":
            overrides = {
                "purpose": "interview_invite",
                "preferred_channel": plan.get("invite_channel") or ctx.action.get("preferred_channel") or ctx.action.get("invite_channel"),
                "interview_id": ctx.action.get("interview_id"),
            }
        elif step == "send_video_interview":
            overrides = {
                "purpose": "video_interview_invite",
                "preferred_channel": plan.get("invite_channel") or ctx.action.get("preferred_channel") or ctx.action.get("invite_channel"),
            }
        elif step == "notify_candidate":
            overrides = {
                "message_text": _workflow_communication_message(
                    ctx.action,
                    app,
                    {**artifacts, "completed_steps": [item["step"] for item in results if (item.get("result") or {}).get("status") == "completed"]},
                    default="We would like to invite you to an online interview. Please reply with your availability.",
                ),
            }
        elif step == "schedule_interview":
            overrides = {
                "interview_time": plan.get("datetime_text"),
                "message_text": ctx.action.get("message_text") or ctx.action.get("workflow_goal"),
            }
        result = run_atomic(step, overrides)
        results.append({"step": step, "result": legacy.json_safe(result)})
        if result.get("status") == "completed":
            artifacts[step] = legacy.json_safe(result)
        if result.get("status") not in {"completed", "ready"} or result.get("success") is False:
            success = False
            break

    completed_steps = [item["step"] for item in results if (item.get("result") or {}).get("status") == "completed"]
    failed_steps = [item for item in results if (item.get("result") or {}).get("status") != "completed"]
    idempotency_key = str(ctx.action.get("idempotency_key") or "").strip() or f"workflow:{app.get('app_key')}:{'-'.join(steps)}:{plan.get('datetime_text') or ''}"
    compensation_state = {
        "strategy": "stop_on_failure_no_auto_rollback",
        "note": "Completed steps remain; failed step can be safely retried with the same idempotency key after fixing the cause.",
        "retry_step": (failed_steps[0].get("step") if failed_steps else None),
        "completed_steps": completed_steps,
    }
    workflow_card = {
        "kind": "workflow_result" if success or failed_steps else "workflow_preview",
        "title": f"Workflow for {name}",
        "status": "completed" if success else "partial",
        "steps": [
            {
                "step": item.get("step"),
                "status": (item.get("result") or {}).get("status"),
                "success": (item.get("result") or {}).get("success"),
                "message": (item.get("result") or {}).get("message") or (item.get("result") or {}).get("error"),
            }
            for item in results
        ],
        "channels": {
            "invite_channel": plan.get("invite_channel"),
            "meeting_type": plan.get("meeting_type"),
        },
        "people": [{"name": name, "app_key": app.get("app_key")}],
        "idempotency_key": idempotency_key,
        "compensation_state": compensation_state,
        "retry_prompt": (
            f"Retry the failed step ({compensation_state['retry_step']}) for {name}"
            if compensation_state.get("retry_step")
            else None
        ),
    }
    return {
        "action_type": "execute_candidate_workflow",
        "success": success,
        "status": "completed" if success else "partial",
        "message": (
            f"Workflow completed for {name}."
            if success
            else f"I completed {len(completed_steps)} step(s) for {name}, but one step needs attention. I am not claiming the whole workflow succeeded."
        ),
        "candidate": plan.get("candidate"),
        "application": legacy.json_safe(app),
        "plan": legacy.json_safe(plan),
        "artifacts": legacy.json_safe(artifacts),
        "step_results": results,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "idempotency_key": idempotency_key,
        "compensation_state": compensation_state,
        "workflow_card": workflow_card,
        **_workflow_interview_fields(artifacts),
    }


register(
    ActionSpec(
        name="rank_candidates",
        description="Rank or list HR candidates from stored CV/application records. Voyage embedding is the ranker; position and status are boosts, never hard filters. Free-text queries (skills, tools, traits) are encouraged.",
        entity_type=None,
        required_fields=(),
        optional_fields=("position", "status", "top_n", "query"),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_rank_candidates_executor,
        result_keys=("action_type", "success", "status", "message", "candidates", "total_matching", "pool_scanned"),
        sensitive=False,
        notes="Semantic-first. Position/status only boost scores; no row is excluded by a literal SQL position match. Parameters catalog publishes the live position+status vocabulary so GPT picks real values.",
        parameters_catalog_loader=_rank_candidates_parameters_catalog,
    )
)


register(
    ActionSpec(
        name="candidate_cv_evaluation",
        description="Evaluate or comment on a candidate based on their CV, application, assessment, and any prior ranking. Always loads CV text + structured fields so the renderer can answer real questions like 'is he good?' without the user having to ask the system to read the CV.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("question", "based_on_cv"),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_candidate_cv_evaluation_executor,
        result_keys=("action_type", "success", "status", "message", "candidate_context", "selected_application"),
        sensitive=False,
        notes="Dedicated executor loads cv_text from semantic_documents and inherits ranking score from the prior rank_candidates turn.",
    )
)


def _positions_authority_payload(
    legacy: Any,
    *,
    company_code: str,
    status_filter: str,
    search: str | None,
    limit: int,
    offset: int = 0,
    operation: str,
) -> dict[str, Any]:
    """Shared positions authority: one tenant-scoped query for items + SQL total."""
    status_arg = None if status_filter == "all" else status_filter
    rows, total_count = legacy._dashboard_prehire_positions_query(
        company_code,
        limit=limit,
        offset=offset,
        search=search,
        status=status_arg,
    )
    # Reject synthesized/blank parents if any slip through.
    clean_rows = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("position_code") or "").strip()
    ]
    if len(clean_rows) != len(rows):
        return {
            "action_type": operation,
            "success": False,
            "status": "failed",
            "error": "positions_authority_invariant_failed",
            "message": "Job inventory rejected a synthesized or blank position row.",
            "safe_user_message": "I could not load job openings safely. Please try again.",
        }
    if offset == 0 and len(clean_rows) > total_count:
        return {
            "action_type": operation,
            "success": False,
            "status": "failed",
            "error": "positions_authority_count_mismatch",
            "message": "Job inventory page metadata contradicted the SQL total.",
            "safe_user_message": "I could not load job openings safely. Please try again.",
        }
    if offset == 0 and limit >= total_count and len(clean_rows) != total_count:
        return {
            "action_type": operation,
            "success": False,
            "status": "failed",
            "error": "positions_authority_unpaginated_mismatch",
            "message": "Unpaginated job inventory count did not match returned items.",
            "safe_user_message": "I could not load job openings safely. Please try again.",
        }
    summary = {}
    if hasattr(legacy, "dashboard_prehire_positions_summary"):
        try:
            summary = legacy.dashboard_prehire_positions_summary(company_code) or {}
        except Exception:
            summary = {}
    # Inventory summary must agree with open filter when status=open and no search.
    if operation == "list_job_openings" and status_filter == "open" and not search and offset == 0:
        open_summary = int((summary or {}).get("open_positions") or -1)
        if open_summary >= 0 and open_summary != total_count:
            return {
                "action_type": operation,
                "success": False,
                "status": "failed",
                "error": "positions_authority_summary_mismatch",
                "message": "Job inventory total contradicted the open-positions summary.",
                "safe_user_message": "I could not load job openings safely. Please try again.",
                "summary": legacy.json_safe(summary),
                "total_matching": total_count,
            }
    provenance = {
        "canonical_table": "positions",
        "company_code": company_code,
        "filters": {"status": status_filter, "search": search},
        "pagination": {"limit": limit, "offset": offset, "total_count": total_count},
        "as_of": legacy.now_iso() if hasattr(legacy, "now_iso") else None,
        "operation": operation,
    }
    result = {
        "action_type": operation,
        "success": True,
        "status": "completed",
        "company_code": company_code,
        "status_filter": status_filter,
        "positions": legacy.json_safe(clean_rows),
        "total_matching": int(total_count),
        "summary": legacy.json_safe(summary),
        "provenance": provenance,
        "authority": "positions",
    }
    if hasattr(legacy, "format_list_job_openings_reply"):
        result["message"] = legacy.format_list_job_openings_reply(result)
    else:
        result["message"] = f"Found {total_count} job opening(s)."
    result["safe_user_message"] = result["message"]
    return result


def _list_job_openings_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Inventory-only job openings from canonical `positions` (no free-text filter)."""
    legacy = ctx.legacy
    action = ctx.action if isinstance(ctx.action, dict) else {}
    company_code = _resolve_company_code(legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "list_job_openings",
            "success": False,
            "status": "failed",
            "error": "company_required",
            "message": "I need a company context before listing job openings.",
            "safe_user_message": "I need a company context before listing job openings.",
        }
    status_raw = str(action.get("status") or action.get("status_filter") or "open").strip().lower()
    if status_raw in {"", "all", "*"}:
        status_filter = "all"
    elif status_raw in {"open", "closed"}:
        status_filter = status_raw
    else:
        status_filter = "open"
    try:
        limit = max(1, min(int(action.get("top_n") or action.get("limit") or 100), 100))
    except Exception:
        limit = 100
    # Inventory must ignore free-text query/search — those belong to search_job_openings.
    return _positions_authority_payload(
        legacy,
        company_code=str(company_code).upper(),
        status_filter=status_filter,
        search=None,
        limit=limit,
        offset=0,
        operation="list_job_openings",
    )


def _search_job_openings_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Explicit role/title search over canonical `positions`."""
    legacy = ctx.legacy
    action = ctx.action if isinstance(ctx.action, dict) else {}
    company_code = _resolve_company_code(legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "search_job_openings",
            "success": False,
            "status": "failed",
            "error": "company_required",
            "message": "I need a company context before searching job openings.",
            "safe_user_message": "I need a company context before searching job openings.",
        }
    search = str(action.get("search") or action.get("query") or action.get("title") or "").strip()
    # Reject whole-utterance inventory questions masquerading as search.
    lowered = search.lower()
    inventory_like = bool(
        re.search(
            r"\b(how many|what|which|list|show|any|do we have|we have)\b.*\b(job|jobs|opening|openings|position|positions|role|roles)\b",
            lowered,
        )
        or re.search(r"\bopen\s+(jobs?|openings?|positions?|roles?)\b", lowered)
    )
    if not search or inventory_like or len(search.split()) > 6:
        return {
            "action_type": "search_job_openings",
            "success": False,
            "status": "needs_clarification",
            "error": "search_term_required",
            "message": "Tell me which role or title to search for (for example Finance or IT Manager).",
            "safe_user_message": "Tell me which role or title to search for (for example Finance or IT Manager).",
        }
    status_raw = str(action.get("status") or action.get("status_filter") or "all").strip().lower()
    if status_raw in {"", "all", "*"}:
        status_filter = "all"
    elif status_raw in {"open", "closed"}:
        status_filter = status_raw
    else:
        status_filter = "all"
    try:
        limit = max(1, min(int(action.get("top_n") or action.get("limit") or 50), 100))
    except Exception:
        limit = 50
    return _positions_authority_payload(
        legacy,
        company_code=str(company_code).upper(),
        status_filter=status_filter,
        search=search,
        limit=limit,
        offset=0,
        operation="search_job_openings",
    )


register(
    ActionSpec(
        name="list_job_openings",
        description=(
            "List Pre-Hiring job openings from the canonical positions table only. "
            "Use for inventory/count questions like what jobs are open or how many openings. "
            "Do NOT pass search/query text. For role/title lookup use search_job_openings. "
            "Do NOT use rank_candidates for job inventory."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("status", "top_n", "limit"),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_list_job_openings_executor,
        result_keys=("action_type", "success", "status", "message", "positions", "total_matching", "summary", "status_filter", "provenance", "safe_user_message"),
        sensitive=False,
        notes="Positions-only authority via dashboard_prehire_positions query. No free-text filter.",
    )
)


register(
    ActionSpec(
        name="search_job_openings",
        description=(
            "Search Pre-Hiring job openings by role title or position code (for example Finance, IT Manager). "
            "Use only when HR names a specific role/title to find. "
            "For 'how many openings' or 'list open jobs' use list_job_openings instead."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("search", "query", "title", "status", "top_n", "limit"),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_search_job_openings_executor,
        result_keys=("action_type", "success", "status", "message", "positions", "total_matching", "summary", "status_filter", "provenance", "safe_user_message"),
        sensitive=False,
        notes="Positions-only search; rejects inventory-like free-text.",
    )
)

register(
    ActionSpec(
        name="create_job_opening",
        description=(
            "Create a pre-hiring job draft in Postgres for HR to complete and approve. "
            "Use when HR asks to create or add a position. This action never publishes the job or shares a QR code. "
            "Publishing is a separate confirmed action after the backend validates all candidate-facing requirements."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=(
            "title",
            "position_code",
            "salary",
            "salary_min",
            "salary_max",
            "currency",
            "employment_type",
            "description",
            "requirements",
        ),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_create_job_opening_preflight,
        executor=_create_job_opening_executor,
        result_keys=("action_type", "success", "status", "message", "position", "apply_code", "apply_link", "qr_image_url"),
        sensitive=True,
        notes="Writes a draft position only. It does not publish, reopen, or share candidate APPLY links.",
    )
)

register(
    ActionSpec(
        name="close_job_opening",
        description=(
            "Close a job opening so its APPLY code / QR / link stop accepting NEW applicants. "
            "Does NOT touch candidates already in that job's pipeline — they stay fully manageable (review, interview, decide). "
            "Use when HR asks to close, stop hiring, or take down a role/posting. "
            "Do NOT use this for temporary pause — use pause_job_opening instead. "
            "This is a PREFLIGHT-THEN-CONFIRM workflow: call it to resolve the exact job by title or APPLY code before confirmation; it executes only after explicit approval."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("title", "position_code"),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_close_job_opening_preflight,
        executor=_close_job_opening_executor,
        result_keys=("action_type", "success", "status", "message", "position", "position_code", "position_title"),
        sensitive=True,
        notes="Sets positions.status='closed'. public_role_by_apply_code already filters on status, so this takes effect immediately for new WhatsApp/QR applicants.",
    )
)

register(
    ActionSpec(
        name="pause_job_opening",
        description=(
            "Temporarily pause an open job opening so it stops accepting NEW applicants while preserving the existing pipeline. "
            "Use when HR asks to pause or temporarily stop intake (not permanent close). "
            "This is a PREFLIGHT-THEN-CONFIRM workflow."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("title", "position_code"),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_pause_job_opening_preflight,
        executor=_pause_job_opening_executor,
        result_keys=("action_type", "success", "status", "message", "position", "position_code", "position_title"),
        sensitive=True,
        notes="Sets positions.status='paused'. Resume with reopen_job_opening.",
    )
)

register(
    ActionSpec(
        name="reopen_job_opening",
        description=(
            "Reopen a closed job or resume a paused job — its existing APPLY code / QR / link start accepting new applicants again, unchanged. "
            "Use when HR asks to reopen, resume, or restart a closed/paused role/posting. Does NOT ask for title/salary again (unlike create_job_opening). "
            "This is a PREFLIGHT-THEN-CONFIRM workflow: call it to resolve the exact job by title or APPLY code before confirmation; it executes only after explicit approval."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("title", "position_code"),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_reopen_job_opening_preflight,
        executor=_reopen_job_opening_executor,
        result_keys=("action_type", "success", "status", "message", "position", "position_code", "position_title"),
        sensitive=True,
        notes="Sets positions.status='open' from closed (reopen) or paused (resume). apply_code/QR are unchanged.",
    )
)


register(
    ActionSpec(
        name="execute_candidate_workflow",
        description=(
            "Plan and execute a multi-step candidate workflow as one auditable unit using atomic registry actions. "
            "Use this instead of calling multiple sensitive tools separately when the user asks to combine actions, e.g. "
            "'shortlist him and email him', 'shortlist and schedule a Google Meet', 'send assessment then notify him'. "
            "Use send_video_interview in the workflow when HR asks for an AI/video/asynchronous interview link. "
            "Backend validates missing fields, email availability, fallback channel, permissions, and asks one confirmation for the whole plan."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(
            "workflow_goal",
            "steps",
            "invite_channel",
            "fallback_channel",
            "allow_fallback",
            "meeting_type",
            "datetime_text",
            "interview_time",
            "when",
            "datetime",
            "message_text",
            "purpose",
            "reason",
            "idempotency_key",
        ),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_candidate_workflow_preflight,
        executor=_execute_candidate_workflow_executor,
        result_keys=("action_type", "success", "status", "message", "plan", "step_results", "completed_steps", "failed_steps", "workflow_card", "idempotency_key", "compensation_state", "interview_created", "calendar_event_created", "google_meet_link", "public_link", "candidate_invited", "candidate_notified", "notification_channel"),
        sensitive=True,
        notes="Workflow-level sensitive tool. One confirmation covers the validated plan; executor composes atomic registry actions internally with per-step results and stop-on-failure compensation.",
    )
)


register(
    ActionSpec(
        name="execute_candidate_batch",
        description=(
            "Preview and execute one candidate mutation for multiple candidates as a DB-backed batch. "
            "Use when HR asks to send, notify, shortlist, or message multiple candidates, top N candidates, all candidates from a previous ranking, or a plural candidate group. "
            "This is PREFLIGHT-THEN-CONFIRM: first call previews the exact candidates, then after explicit confirmation it executes the atomic action once per candidate with per-item audit."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=(
            "batch_action_type",
            "candidate_app_keys",
            "candidate_names",
            "top_n",
            "position",
            "status",
            "query",
            "preferred_channel",
            "invite_channel",
            "message_text",
            "workflow_goal",
        ),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_execute_candidate_batch_preflight,
        executor=_execute_candidate_batch_executor,
        result_keys=("action_type", "success", "status", "message", "batch_id", "batch_action_type", "success_count", "failed_count", "total_count", "items"),
        sensitive=True,
        notes="Batch wrapper only. It never implements business mutations itself; it calls atomic single-candidate registry actions per app_key and stores batch_actions/batch_action_items.",
    )
)


register(
    ActionSpec(
        name="execute_mixed_candidate_batch",
        description=(
            "Preview and execute different candidate actions for different candidates as one DB-backed mixed batch. "
            "Use when HR asks for distinct candidate/action pairs, e.g. 'shortlist Foad, send assessment to Sara, and send video interview to Ali'. "
            "This is PREFLIGHT-THEN-CONFIRM: first call previews each exact candidate/action pair, then after explicit confirmation it executes atomic tools per item with per-item audit."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("mixed_items", "workflow_goal", "preferred_channel", "invite_channel", "message_text"),
        module="pre_hiring",
        requires_confirmation=True,
        preflight=_execute_mixed_candidate_batch_preflight,
        executor=_execute_mixed_candidate_batch_executor,
        result_keys=("action_type", "success", "status", "message", "batch_id", "success_count", "failed_count", "total_count", "items"),
        sensitive=True,
        notes="Mixed batch wrapper only. Every item runs an existing atomic single-candidate registry action and stores batch_action_items.",
    )
)


register(
    ActionSpec(
        name="shortlist_candidate",
        description="Move a candidate's application to the shortlisted stage. Sensitive mutation, requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("reason",),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_status_mutation_executor("shortlisted", "is shortlisted", "shortlist"),
        result_keys=("action_type", "success", "status", "message", "application", "update", "candidate_status"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="hire_candidate",
        description="Mark a candidate as hired. This also creates the employee record and starts the post-hire chain. Sensitive mutation, requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("reason",),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_hire_candidate_executor,
        result_keys=("action_type", "success", "status", "message", "application", "update", "posthire", "candidate_status"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="reject_candidate",
        description="Mark a candidate as rejected. Sensitive mutation, requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("reason",),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_status_mutation_executor("rejected", "was rejected", "reject"),
        result_keys=("action_type", "success", "status", "message", "application", "update", "candidate_status"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="send_email",
        description="Send an email to a candidate. Subject and body come from intent.parameters or sensible defaults per purpose (shortlisted, interview invite, generic follow-up). Sensitive: requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("email_subject", "message_text", "purpose"),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_send_email_executor,
        result_keys=("action_type", "success", "status", "message", "result", "application"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="notify_candidate",
        description="Send a WhatsApp notification to a candidate. If the message is about an interview, use the saved interview record/Meet link rather than a generic message. Sensitive: requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("message_text",),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_notify_candidate_executor,
        result_keys=("action_type", "success", "status", "message", "result", "application"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="send_interview_invite",
        description=(
            "Send or resend the canonical interview invite for a scheduled candidate interview. "
            "Always loads candidate_interviews from Postgres and includes the saved Google Meet link, or clearly says the Google Calendar invite contains joining details. Sensitive: requires confirmation."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("interview_id", "preferred_channel", "invite_channel"),
        module="interviews",
        requires_confirmation=True,
        executor=_send_interview_invite_executor,
        result_keys=("action_type", "success", "status", "message", "interview", "google_meet_link", "candidate_notified", "notification_channel", "sent_subject", "sent_body"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="send_assessment",
        description="Send the standard candidate assessment link by email and WhatsApp where available. Sensitive: requires confirmation.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("message_text",),
        module="assessments",
        requires_confirmation=True,
        executor=_send_assessment_executor,
        result_keys=("action_type", "success", "status", "message", "result", "application"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="send_video_interview",
        description=(
            "Create or resume an asynchronous AI video interview for a candidate and send the signed candidate link. "
            "Use when HR asks to send a video interview, AI video interview, async interview, recorded interview, or screening video link. "
            "V1 defaults to one candidate video covering the standard question list, not separate videos per question. "
            "When asking for confirmation, preview the standard questions: introduce yourself/background; why interested in the role; relevant experience/skills/strengths; availability and anything else the hiring team should know. "
            "This is an interview.manage mutation and HR remains the decision-maker."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("preferred_channel", "invite_channel", "message_text"),
        module="video_interviews",
        requires_confirmation=True,
        executor=_send_video_interview_executor,
        result_keys=("action_type", "success", "status", "message", "interview", "public_link", "candidate_notified", "notification_channel", "sent_subject", "sent_body"),
        sensitive=True,
        notes="Uses candidate_interviews as parent source of truth with interview_type=async_video and child video question/answer records.",
    )
)


register(
    ActionSpec(
        name="send_screening_questions",
        description="Send the actual position screening questions to a candidate on WhatsApp and mark their application as screening/pending. Use this for 'send screening questions' requests; do not use generic notify_candidate.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(),
        module="pre_hiring",
        requires_confirmation=True,
        executor=_send_screening_questions_executor,
        result_keys=("action_type", "success", "status", "message", "questions", "result", "application"),
        sensitive=True,
    )
)


register(
    ActionSpec(
        name="schedule_interview",
        description=(
            "Create the canonical Wathefni interview record and sync an external calendar event "
            "(Google Meet or Microsoft Teams when configured). "
            "Accepts natural-language times like 'tomorrow at 4pm'. Sensitive: requires confirmation. "
            "Uses interview_service — never a parallel gog-only path."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(
            "interview_time",
            "when",
            "datetime",
            "datetime_text",
            "message_text",
            "meeting_type",
            "location",
            "meet_link",
            "meeting_link",
            "idempotency_key",
        ),
        module="interviews",
        requires_confirmation=True,
        executor=_schedule_interview_executor,
        result_keys=(
            "action_type",
            "success",
            "status",
            "message",
            "application",
            "start",
            "end",
            "interview",
            "interview_created",
            "calendar_event_created",
            "google_meet_link",
            "teams_meet_link",
            "meet_link",
            "candidate_invited",
            "candidate_notified",
            "provider_sync",
            "idempotent_replay",
        ),
        sensitive=True,
        notes="Canonical interview_service authority for schedule/reschedule/cancel.",
    )
)


def _active_interview_id_for_app(legacy: Any, app: dict[str, Any], interview_id: str | None = None) -> str:
    if interview_id:
        return str(interview_id).strip()
    existing = _scheduled_interview_for_current_app(legacy, app)
    if existing and existing.get("interview_id"):
        return str(existing.get("interview_id"))
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT interview_id FROM candidate_interviews
                    WHERE company_code=%s AND app_key=%s
                      AND lower(COALESCE(status,'')) IN ('scheduled','rescheduled')
                      AND lower(COALESCE(interview_type,'live')) <> 'async_video'
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (str(app.get("company_code") or "").upper(), str(app.get("app_key") or "")),
                )
                row = cur.fetchone() or {}
                return str(row.get("interview_id") or "")
    except Exception:
        return ""


def _cancel_interview_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("cancel_interview", "cancel")
    interview_id = _active_interview_id_for_app(legacy, app, str(ctx.action.get("interview_id") or "") or None)
    if not interview_id:
        return {
            "action_type": "cancel_interview",
            "success": False,
            "status": "failed",
            "error": "interview_not_found",
            "message": "No active interview found to cancel.",
            "application": legacy.json_safe(app),
        }
    import interview_service as _interview_service
    import interview_lifecycle as _il

    meta = getattr(ctx.request, "metadata", {}) or {}
    if not isinstance(meta, dict):
        meta = {}
    try:
        result = _interview_service.cancel_interview(
            company_code=str(app.get("company_code") or ""),
            interview_id=interview_id,
            idempotency_key=str(ctx.action.get("idempotency_key") or "") or None,
            actor={
                "actor_user_id": str(ctx.action.get("actor_user_id") or meta.get("actor_user_id") or "") or None,
                "actor_phone": getattr(ctx.request, "sender_phone", None),
                "actor_role": str(meta.get("actor_role") or "") or None,
                "actor_type": "human",
            },
            sync_external=True,
            revert_application_stage=True,
            permissions=meta.get("permissions") or [],
        )
    except _il.InterviewAuthorityError as exc:
        return {
            "action_type": "cancel_interview",
            "success": False,
            "status": "failed",
            "error": getattr(exc, "error", None) or "cancel_failed",
            "message": getattr(exc, "message", None) or str(exc),
            "application": legacy.json_safe(app),
        }
    return {
        "action_type": "cancel_interview",
        "success": True,
        "status": "completed",
        "message": "Interview cancelled.",
        "interview": legacy.json_safe(result.get("interview")),
        "provider_sync": legacy.json_safe(result.get("provider_sync")),
        "idempotent_replay": bool(result.get("idempotent_replay")),
        "application": legacy.json_safe(app),
    }


def _reschedule_interview_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    app = _resolve_app(ctx)
    if not app:
        return _candidate_not_found_result("reschedule_interview", "reschedule")
    interview_id = _active_interview_id_for_app(legacy, app, str(ctx.action.get("interview_id") or "") or None)
    if not interview_id:
        return {
            "action_type": "reschedule_interview",
            "success": False,
            "status": "failed",
            "error": "interview_not_found",
            "message": "No active interview found to reschedule.",
            "application": legacy.json_safe(app),
        }
    text = " ".join(
        str(value or "")
        for value in (
            ctx.action.get("prompt_text"),
            ctx.action.get("interview_time"),
            ctx.action.get("when"),
            ctx.action.get("datetime"),
            ctx.action.get("datetime_text"),
            ctx.action.get("message_text"),
        )
    ).strip()
    start, end = legacy.parse_meeting_time(text)
    if not start or not end:
        return {
            "action_type": "reschedule_interview",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_required_fields": ["interview_time"],
            "message": "I need the new date and time — for example, 'Thursday at 3pm'.",
            "application": legacy.json_safe(app),
        }
    import interview_service as _interview_service
    import interview_lifecycle as _il

    meta = getattr(ctx.request, "metadata", {}) or {}
    if not isinstance(meta, dict):
        meta = {}
    try:
        result = _interview_service.reschedule_interview(
            company_code=str(app.get("company_code") or ""),
            interview_id=interview_id,
            start=start,
            end=end,
            meeting_type=ctx.action.get("meeting_type"),
            location=ctx.action.get("location"),
            meet_link=ctx.action.get("meet_link") or ctx.action.get("meeting_link"),
            idempotency_key=str(ctx.action.get("idempotency_key") or "") or None,
            actor={
                "actor_user_id": str(ctx.action.get("actor_user_id") or meta.get("actor_user_id") or "") or None,
                "actor_phone": getattr(ctx.request, "sender_phone", None),
                "actor_role": str(meta.get("actor_role") or "") or None,
                "actor_type": "human",
            },
            sync_external=True,
            permissions=meta.get("permissions") or [],
        )
    except _il.InterviewAuthorityError as exc:
        return {
            "action_type": "reschedule_interview",
            "success": False,
            "status": "failed",
            "error": getattr(exc, "error", None) or "reschedule_failed",
            "message": getattr(exc, "message", None) or str(exc),
            "application": legacy.json_safe(app),
        }
    return {
        "action_type": "reschedule_interview",
        "success": True,
        "status": "completed",
        "message": "Interview rescheduled.",
        "interview": legacy.json_safe(result.get("interview")),
        "provider_sync": legacy.json_safe(result.get("provider_sync")),
        "idempotent_replay": bool(result.get("idempotent_replay")),
        "application": legacy.json_safe(app),
        "start": start,
        "end": end,
    }


register(
    ActionSpec(
        name="cancel_interview",
        description=(
            "Cancel the active Wathefni interview for a candidate using the same cancel authority as the dashboard. "
            "Optionally syncs calendar cancellation when Google is connected. Requires interview.manage and confirmation. Idempotent."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("interview_id", "idempotency_key"),
        module="interviews",
        requires_confirmation=True,
        executor=_cancel_interview_executor,
        result_keys=("action_type", "success", "status", "message", "interview", "provider_sync", "idempotent_replay", "application"),
        sensitive=True,
        notes="Reuses interview_service.cancel_interview.",
    )
)


register(
    ActionSpec(
        name="reschedule_interview",
        description=(
            "Reschedule the active Wathefni interview for a candidate to a new date/time using the same authority as the dashboard. "
            "Updates the same external calendar event when connected. Requires interview.manage and confirmation."
        ),
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(
            "interview_id",
            "interview_time",
            "when",
            "datetime",
            "datetime_text",
            "message_text",
            "meeting_type",
            "location",
            "meet_link",
            "meeting_link",
            "idempotency_key",
        ),
        module="interviews",
        requires_confirmation=True,
        executor=_reschedule_interview_executor,
        result_keys=("action_type", "success", "status", "message", "interview", "provider_sync", "idempotent_replay", "application", "start", "end"),
        sensitive=True,
        notes="Reuses interview_service.reschedule_interview.",
    )
)


register(
    ActionSpec(
        name="get_interview_invite_status",
        description="Read-only check for whether a scheduled interview candidate was invited/notified. Uses candidate_interviews plus outbound_delivery_events, not memory guesses. Use for questions like 'did you notify him?' after scheduling.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(),
        module="interviews",
        requires_confirmation=False,
        executor=_get_interview_invite_status_executor,
        result_keys=("action_type", "success", "status", "message", "interview", "calendar_invite_sent", "candidate_invited", "candidate_notified", "notification_channel", "google_meet_link"),
        sensitive=False,
    )
)


register(
    ActionSpec(
        name="get_candidate_status",
        description="Look up a candidate's current application status (review_pending, shortlisted, hired, rejected, withdrawn). Read-only.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=(),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_get_candidate_status_executor,
        result_keys=("action_type", "success", "status", "message", "candidate_status", "application"),
        sensitive=False,
        notes="Closes the 'is he shortlisted?' clarification loop by giving GPT an explicit read intent.",
    )
)


def _get_reports_metrics_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Read-only Assistant Reports executor bound to reports-contract-v2 / reports_metrics."""

    import reports_metrics as _reports_metrics

    legacy = ctx.legacy
    action = ctx.action
    company_code = _resolve_company_code(legacy, ctx.request) or ""
    if not company_code:
        return {
            "action_type": "get_reports_metrics",
            "success": False,
            "status": "failed",
            "error": "tenant_scope_required",
            "message": "Reports requires an authenticated tenant.",
        }
    locale = str(action.get("locale") or "en").strip() or "en"
    try:
        assessments_enabled = bool(legacy.company_has_module(company_code, "assessments"))
        interviews_enabled = bool(
            legacy.company_has_module(company_code, "interviews")
            or legacy.company_has_module(company_code, "video_interviews")
        )
    except Exception:
        assessments_enabled = False
        interviews_enabled = False
    reviewable = getattr(legacy, "reviewable_application_predicate", None)
    if not callable(reviewable):
        return {
            "action_type": "get_reports_metrics",
            "success": False,
            "status": "failed",
            "error": "reports_authority_unavailable",
            "message": "Reports authority is unavailable right now. Open the Reports page.",
            "authority": "reports-contract-v2",
        }
    try:
        payload = _reports_metrics.build_canonical_reports_payload(
            company=company_code,
            db_connect=legacy.db_connect,
            reviewable_predicate=reviewable,
            assessments_enabled=assessments_enabled,
            interviews_enabled=interviews_enabled,
            locale=locale,
        )
    except Exception as exc:
        return {
            "action_type": "get_reports_metrics",
            "success": False,
            "status": "failed",
            "error": "reports_failed",
            "message": str(exc)[:300],
            "authority": "reports-contract-v2",
        }
    overview = payload.get("overview") if isinstance(payload.get("overview"), dict) else {}
    return {
        "action_type": "get_reports_metrics",
        "success": bool(payload.get("ok", True)),
        "status": "completed" if payload.get("ok", True) else "partial",
        "message": (
            "Canonical Reports metrics. Cite these values exactly. "
            "Do not invent additional analytics. Overview work-queue counts are not a substitute for Reports."
        ),
        "authority": "reports-contract-v2",
        "metric_version": payload.get("metric_version"),
        "overview": legacy.json_safe(overview),
        "summary": legacy.json_safe(payload.get("summary")),
        "breakdowns": legacy.json_safe(payload.get("breakdowns")),
        "exports": legacy.json_safe(payload.get("exports")),
        "payload": legacy.json_safe(payload),
        "overview_is_not_reports": True,
        "partial": bool(payload.get("partial")),
    }


# Keep get_prehire_* registrations that follow in file — reports tool registered here.

register(
    ActionSpec(
        name="get_reports_metrics",
        description=(
            "Return canonical hiring Reports metrics (reports-contract-v2): overview cards, breakdowns, "
            "export counts, and definitions for the authenticated tenant. "
            "Read-only. Never invent metrics. Never use Overview tools as a Reports substitute. "
            "Overview work-queue questions should use get_prehire_* tools instead."
        ),
        entity_type=None,
        required_fields=(),
        optional_fields=("locale",),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_get_reports_metrics_executor,
        result_keys=(
            "action_type",
            "success",
            "status",
            "message",
            "metric_version",
            "overview",
            "summary",
            "breakdowns",
            "exports",
        ),
        sensitive=False,
        notes="Bound only to reports_metrics.build_canonical_reports_payload.",
    )
)


def _get_prehire_action_counts_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    company_code = _resolve_company_code(legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "get_prehire_action_counts",
            "success": False,
            "status": "failed",
            "error": "company_required",
            "message": "I need a company context before reading Overview counts.",
        }
    counts = legacy.prehire_action_counts(company_code)
    return {
        "action_type": "get_prehire_action_counts",
        "success": True,
        "status": "ok",
        "message": (
            f"{counts.get('ready_for_review', 0)} ready for review, "
            f"{counts.get('assessment_pending', 0)} awaiting assessment, "
            f"{counts.get('follow_up_needed', 0)} need follow-up."
        ),
        "company_code": company_code,
        "action_counts": legacy.json_safe(counts),
        "authority_source": "prehire_overview.action_counts",
    }


def _get_prehire_priorities_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    company_code = _resolve_company_code(legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "get_prehire_priorities",
            "success": False,
            "status": "failed",
            "error": "company_required",
            "message": "I need a company context before reading Overview priorities.",
        }
    overview = legacy._prehire_overview.build_overview_authority(
        company=company_code,
        db_connect=legacy.db_connect,
        get_company_settings=legacy.get_company_settings,
        assessments_enabled=legacy.company_has_module(company_code, "assessments"),
        interviews_enabled=True,
    )
    return {
        "action_type": "get_prehire_priorities",
        "success": True,
        "status": "ok",
        "message": str((overview.get("next_action") or {}).get("reason") or "No urgent hiring priorities."),
        "company_code": company_code,
        "action_counts": legacy.json_safe(overview.get("action_counts")),
        "next_action": legacy.json_safe(overview.get("next_action")),
        "role_priority": legacy.json_safe(overview.get("role_priority")),
        "definitions": legacy.json_safe(overview.get("definitions")),
        "as_of": overview.get("as_of"),
        "authority_source": "prehire_overview",
    }


def _get_prehire_work_queue_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    company_code = _resolve_company_code(legacy, ctx.request)
    if not company_code:
        return {
            "action_type": "get_prehire_work_queue",
            "success": False,
            "status": "failed",
            "error": "company_required",
            "message": "I need a company context before reading the Overview work queue.",
        }
    limit = int(ctx.action.get("limit") or 25)
    cursor = str(ctx.action.get("cursor") or "").strip() or None
    payload = legacy._prehire_overview.compute_work_queue(
        company=company_code,
        db_connect=legacy.db_connect,
        assessments_enabled=legacy.company_has_module(company_code, "assessments"),
        interviews_enabled=True,
        settings=legacy.get_company_settings(company_code),
        limit=limit,
        cursor=cursor,
    )
    return {
        "action_type": "get_prehire_work_queue",
        "success": True,
        "status": "ok",
        "message": f"{payload.get('total', 0)} prioritized hiring actions.",
        "company_code": company_code,
        **legacy.json_safe(payload),
    }


register(
    ActionSpec(
        name="get_prehire_action_counts",
        description="Return canonical company-wide Overview action counts: ready_for_review, assessment_pending, follow_up_needed. Read-only backend facts — do not recalculate.",
        entity_type=None,
        required_fields=(),
        optional_fields=(),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_get_prehire_action_counts_executor,
        result_keys=("action_type", "success", "status", "message", "action_counts", "authority_source"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="get_prehire_priorities",
        description="Return canonical Overview priorities: action_counts, suggested next_action with reason, and role_priority. Read-only backend facts.",
        entity_type=None,
        required_fields=(),
        optional_fields=(),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_get_prehire_priorities_executor,
        result_keys=("action_type", "success", "status", "message", "action_counts", "next_action", "role_priority", "authority_source"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="get_prehire_work_queue",
        description="Return the company-wide prioritized pre-hiring work queue with cursor pagination. Read-only backend facts.",
        entity_type=None,
        required_fields=(),
        optional_fields=("limit", "cursor"),
        module="pre_hiring",
        requires_confirmation=False,
        executor=_get_prehire_work_queue_executor,
        result_keys=("action_type", "success", "status", "message", "total", "items", "next_cursor", "authority_source"),
        sensitive=False,
    )
)


# ---------------------------------------------------------------------------
# Leave management (post-hire pilot)
#
# These wrap the existing, battle-tested app.py leave executors as registry
# actions so leave runs on the same tool-call architecture as pre-hiring:
# typed tool schemas, central entitlement checks, pending_actions + action_hash
# confirmation, and audited execution. The backend functions remain the single
# source of truth; the adapters only translate the ExecutionContext into the
# legacy call signature and normalize the result shape. The legacy
# execute_direct_action / infer_leave_action / pending_operations paths are kept
# intact during the pilot; nothing here removes them.
# ---------------------------------------------------------------------------


def _leave_action(ctx: ExecutionContext) -> dict[str, Any]:
    """Build the action dict the legacy leave functions expect.

    Mirrors execute_direct_action: the actor's phone is injected as viewer_phone
    so manager-scope enforcement behaves identically to the legacy path. HR
    admins who are not scoped managers stay unrestricted (manager_scope_context
    returns restricted=False when no manager_scopes row exists for non-manager
    roles). Team managers without an explicit scope binding fail closed.
    """

    action = dict(ctx.action)
    actor_phone = getattr(ctx.request, "sender_phone", None) or action.get("actor_phone") or action.get("viewer_phone")
    if actor_phone and not action.get("viewer_phone"):
        action["viewer_phone"] = actor_phone
    return action


def _leave_actor_phone(ctx: ExecutionContext) -> Any:
    return getattr(ctx.request, "sender_phone", None) or ctx.action.get("actor_phone") or ctx.action.get("viewer_phone")


def _leave_account_id(ctx: ExecutionContext) -> Any:
    return getattr(ctx.request, "account_id", None)


def _leave_origin_surface(ctx: ExecutionContext) -> str:
    """Which surface drove this governed action.

    Callers (assistant turn, dashboards) stamp the action/state; anything that
    does not is attributed to the assistant rather than mislabelled whatsapp.
    """
    for candidate in (
        ctx.action.get("origin_surface"),
        ctx.action.get("surface"),
        (ctx.state or {}).get("origin_surface"),
        (ctx.state or {}).get("surface"),
        getattr(ctx.request, "surface", None),
        getattr(ctx.request, "channel", None),
    ):
        if str(candidate or "").strip():
            return str(candidate).strip()
    return "assistant"


def _list_leave_requests_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.list_leave_requests(action, company_code=action.get("company_code"))
    reply = legacy.format_list_leave_requests_reply(result)
    return legacy.normalize_posthire_result(result, action_type="list_leave_requests", reply=reply)


def _request_leave_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.request_leave(
        action,
        company_code=action.get("company_code"),
        created_by_phone=_leave_actor_phone(ctx),
        origin_surface=_leave_origin_surface(ctx),
    )
    reply = legacy.format_leave_mutation_reply(result, "request_leave")
    return legacy.normalize_posthire_result(result, action_type="request_leave", reply=reply)


def _approve_leave_request_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    # The registry confirmation gate has already required explicit user
    # confirmation, and the preflight surfaced any shift conflicts in the
    # confirmation text. Approving now intentionally covers those conflicts so
    # we do not bounce the user with a second legacy conflict prompt.
    action["allow_shift_conflicts"] = True
    result = legacy.approve_leave_request(
        action,
        company_code=action.get("company_code"),
        created_by_phone=_leave_actor_phone(ctx),
        account_id=_leave_account_id(ctx),
    )
    reply = legacy.format_leave_mutation_reply(result, "approve_leave_request")
    return legacy.normalize_posthire_result(result, action_type="approve_leave_request", reply=reply)


def _reject_leave_request_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.reject_leave_request(
        action,
        company_code=action.get("company_code"),
        created_by_phone=_leave_actor_phone(ctx),
        account_id=_leave_account_id(ctx),
    )
    reply = legacy.format_leave_mutation_reply(result, "reject_leave_request")
    return legacy.normalize_posthire_result(result, action_type="reject_leave_request", reply=reply)


def _cancel_leave_request_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.cancel_leave_request(
        action,
        company_code=action.get("company_code"),
        created_by_phone=_leave_actor_phone(ctx),
        account_id=_leave_account_id(ctx),
    )
    reply = legacy.format_leave_mutation_reply(result, "cancel_leave_request")
    return legacy.normalize_posthire_result(result, action_type="cancel_leave_request", reply=reply)


def _leave_decision_preflight(action_type: str, statuses: tuple[str, ...], verb: str, check_conflicts: bool = False) -> ExecutorCallable:
    """Resolve the target leave request before confirmation and build a
    deterministic confirmation_text. For approve, reuse the existing shift
    conflict detection so HR sees conflicts in the same confirmation prompt.
    """

    def preflight(ctx: ExecutionContext) -> dict[str, Any]:
        legacy = ctx.legacy
        action = _leave_action(ctx)
        company = action.get("company_code")
        leave = legacy.resolve_leave_request(action, company_code=company, statuses=statuses)
        if not leave:
            message = f"I could not find one exact leave request to {verb}. Ask which employee or which dates."
            return {
                "action_type": action_type,
                "status": "leave_request_not_found",
                "success": False,
                "message": message,
                "safe_user_message": message,
            }
        employee = legacy.find_employee_by_phone(leave.get("employee_phone"))
        viewer_phone = action.get("viewer_phone")
        if viewer_phone and not legacy.manager_scope_allows_employee(
            employee or {"employee_key": leave.get("employee_key"), "company_code": company},
            company_code=company,
            viewer_phone=viewer_phone,
        ):
            message = "That employee is outside your manager scope."
            return {
                "action_type": action_type,
                "status": "employee_outside_manager_scope",
                "success": False,
                "message": message,
                "safe_user_message": message,
            }
        name = leave.get("employee_name") or "that employee"
        date_text = legacy.format_shift_date_range(leave.get("start_date"), leave.get("end_date"))
        conflicts: list[dict[str, Any]] = []
        if check_conflicts:
            try:
                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        conflicts = legacy.leave_shift_conflicts(
                            cur,
                            company=company,
                            employee_key=str(leave.get("employee_key")),
                            start_date=leave.get("start_date"),
                            end_date=leave.get("end_date"),
                        )
            except Exception:
                conflicts = []
        if conflicts:
            plural = "s" if len(conflicts) != 1 else ""
            confirmation_text = f"{name} has {len(conflicts)} scheduled shift{plural} during {date_text}. {verb.capitalize()} the leave anyway?"
        else:
            confirmation_text = f"{verb.capitalize()} {name}'s leave for {date_text}?"
        return {
            "action_type": action_type,
            "status": "ready",
            "success": True,
            "message": confirmation_text,
            "confirmation_text": confirmation_text,
            "leave": legacy.json_safe(leave),
            "leave_id": leave.get("leave_id"),
            "shift_conflicts": legacy.json_safe(conflicts),
        }

    return preflight


_LEAVE_RESULT_KEYS = (
    "action_type",
    "success",
    "status",
    "message",
    "safe_user_message",
    "leave",
    "leave_requests",
    "shift_conflicts",
    "employee_notification",
)


register(
    ActionSpec(
        name="list_leave_requests",
        description=(
            "List leave requests for the company or one employee. Read-only. "
            "Use for questions like 'show pending leave', 'who is off next week', or 'has Sara requested leave'. "
            "Filter by status (requested/approved/rejected/cancelled) and date range when the user specifies them."
        ),
        required_fields=(),
        optional_fields=("employee_name", "employee_phone", "status", "start_date", "end_date"),
        module="leave",
        requires_confirmation=False,
        executor=_list_leave_requests_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=False,
        notes="Wraps app.list_leave_requests; company-scoped and manager-scope aware.",
    )
)


register(
    ActionSpec(
        name="request_leave",
        description=(
            "Create a leave request on behalf of an employee. Provide the employee (name or phone) and the dates. "
            "Leave starts in 'requested' status for HR to approve later; this does not approve it. "
            "If a scheduled shift overlaps the period, the backend records it so HR can review before approving."
        ),
        required_fields=(),
        optional_fields=(
            "employee_name",
            "employee_phone",
            "leave_type",
            "reason",
            "start_date",
            "end_date",
            "duration_unit",
            "half_portion",
            "start_time",
            "end_time",
            "hours",
            "shift_id",
            "sensitive_category",
        ),
        module="leave",
        requires_confirmation=False,
        executor=_request_leave_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=False,
        notes="Wraps app.request_leave; never auto-approves. Wave 3 duration/unpaid fields optional.",
    )
)


register(
    ActionSpec(
        name="approve_leave_request",
        description=(
            "Approve a pending leave request for an employee. SENSITIVE decision. "
            "Identify the request by employee + dates or by leave_id. "
            "Call this tool to preflight: the backend confirms which request and warns about any scheduled shift conflicts, "
            "then asks for one explicit confirmation before approving."
        ),
        required_fields=(),
        optional_fields=("leave_id", "employee_name", "employee_phone", "start_date", "end_date", "decision_note", "expected_row_version", "allow_shift_conflicts"),
        module="leave",
        requires_confirmation=True,
        executor=_approve_leave_request_executor,
        preflight=_leave_decision_preflight("approve_leave_request", ("requested", "needs_review"), "approve", check_conflicts=True),
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wraps app.approve_leave_request; reuses leave_shift_conflicts in preflight so conflicts are confirmed once.",
    )
)


register(
    ActionSpec(
        name="reject_leave_request",
        description=(
            "Reject a pending leave request for an employee. SENSITIVE decision. "
            "Identify the request by employee + dates or by leave_id. "
            "Call this tool to preflight: the backend confirms which request, then asks for one explicit confirmation before rejecting."
        ),
        required_fields=(),
        optional_fields=("leave_id", "employee_name", "employee_phone", "start_date", "end_date", "decision_note"),
        module="leave",
        requires_confirmation=True,
        executor=_reject_leave_request_executor,
        preflight=_leave_decision_preflight("reject_leave_request", ("requested", "needs_review", "needs_info"), "reject"),
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wraps app.reject_leave_request.",
    )
)


register(
    ActionSpec(
        name="cancel_leave_request",
        description=(
            "Cancel an existing leave request (requested or already approved) for an employee. SENSITIVE decision. "
            "Identify the request by employee + dates or by leave_id. "
            "Call this tool to preflight: the backend confirms which request, then asks for one explicit confirmation before cancelling."
        ),
        required_fields=(),
        optional_fields=("leave_id", "employee_name", "employee_phone", "start_date", "end_date", "expected_row_version", "allow_cancel_started"),
        module="leave",
        requires_confirmation=True,
        executor=_cancel_leave_request_executor,
        preflight=_leave_decision_preflight("cancel_leave_request", ("requested", "approved", "needs_review", "needs_info"), "cancel"),
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wraps app.cancel_leave_request.",
    )
)


def _return_leave_for_info_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.return_leave_for_info(action, company_code=action.get("company_code"), created_by_phone=_leave_actor_phone(ctx))
    reply = result.get("error") or "Returned leave for more information."
    if result.get("ok"):
        reply = "Leave returned for information — employee can resubmit."
    return legacy.normalize_posthire_result(result, action_type="return_leave_for_info", reply=reply)


def _withdraw_leave_request_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.withdraw_leave_request(action, company_code=action.get("company_code"), created_by_phone=_leave_actor_phone(ctx))
    reply = "Leave withdrawn." if result.get("ok") else (result.get("error") or "Could not withdraw leave.")
    return legacy.normalize_posthire_result(result, action_type="withdraw_leave_request", reply=reply)


def _resubmit_leave_request_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.resubmit_leave_request(action, company_code=action.get("company_code"), created_by_phone=_leave_actor_phone(ctx))
    reply = "Leave resubmitted." if result.get("ok") else (result.get("error") or "Could not resubmit leave.")
    return legacy.normalize_posthire_result(result, action_type="resubmit_leave_request", reply=reply)


def _initiate_leave_stale_dual_control_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.initiate_leave_stale_dual_control(
        action, company_code=action.get("company_code"), created_by_phone=_leave_actor_phone(ctx)
    )
    reply = "Dual-control initiated — awaiting second allowlisted confirmer." if result.get("ok") else (result.get("error") or "Dual-control failed.")
    return legacy.normalize_posthire_result(result, action_type="initiate_leave_stale_dual_control", reply=reply)


def _confirm_leave_stale_dual_control_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _leave_action(ctx)
    result = legacy.confirm_leave_stale_dual_control(
        action, company_code=action.get("company_code"), created_by_phone=_leave_actor_phone(ctx)
    )
    reply = "Stale leave resolved via dual control." if result.get("ok") else (result.get("error") or "Dual-control confirm failed.")
    return legacy.normalize_posthire_result(result, action_type="confirm_leave_stale_dual_control", reply=reply)


register(
    ActionSpec(
        name="return_leave_for_info",
        description="Return a pending leave request for more information (needs_info). Keeps reservation.",
        required_fields=(),
        optional_fields=("leave_id", "employee_name", "employee_phone", "decision_note", "info_request", "expected_row_version"),
        module="leave",
        requires_confirmation=True,
        executor=_return_leave_for_info_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wave 3/4 RFI path.",
    )
)

register(
    ActionSpec(
        name="withdraw_leave_request",
        description="Withdraw a leave request before decision.",
        required_fields=(),
        optional_fields=("leave_id", "employee_name", "employee_phone", "expected_row_version"),
        module="leave",
        requires_confirmation=True,
        executor=_withdraw_leave_request_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=False,
        notes="Wave 3 withdraw.",
    )
)

register(
    ActionSpec(
        name="resubmit_leave_request",
        description="Resubmit a leave request after needs_info.",
        required_fields=(),
        optional_fields=("leave_id", "reason", "expected_row_version"),
        module="leave",
        requires_confirmation=False,
        executor=_resubmit_leave_request_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=False,
        notes="Wave 3 resubmit.",
    )
)

register(
    ActionSpec(
        name="initiate_leave_stale_dual_control",
        description="Initiate audited dual-control to resolve a stale real pending leave (first allowlisted actor).",
        required_fields=("leave_id",),
        optional_fields=("action_kind", "decision_note"),
        module="leave",
        requires_confirmation=True,
        executor=_initiate_leave_stale_dual_control_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wave 4 dual-control first leg.",
    )
)

register(
    ActionSpec(
        name="confirm_leave_stale_dual_control",
        description="Confirm dual-control resolution of a stale real pending leave (second different allowlisted actor).",
        required_fields=("leave_id",),
        optional_fields=("dual_action_id", "decision_note"),
        module="leave",
        requires_confirmation=True,
        executor=_confirm_leave_stale_dual_control_executor,
        result_keys=_LEAVE_RESULT_KEYS,
        sensitive=True,
        notes="Wave 4 dual-control second leg.",
    )
)


# ---------------------------------------------------------------------------
# Post-hire operations (attendance, shifts, onboarding, payroll, analytics)
#
# Coordinated migration onto the same registry/tool-call architecture as Leave.
# A generic adapter factory wraps the existing app.py executors — none of the
# backend business logic is rewritten. Each adapter:
#   * injects the actor phone as viewer_phone (manager-scope parity with legacy)
#   * calls the legacy executor with its exact kwargs
#   * replays the legacy post-execute notifications (shift created/cancelled,
#     attendance exceptions) so behaviour is identical to execute_direct_action
#   * renders the user-facing reply via the existing format_*_reply helpers
#   * normalizes the result into the registry contract (normalize_posthire_result)
#
# Sensitive actions require confirmation (pending_actions + action_hash) with a
# lightweight confirm-preflight that produces a clean HR prompt. Attendance
# mark-absent/correct set allow_without_shift after confirmation (the human gate
# replaces the legacy second prompt), mirroring Leave's allow_shift_conflicts.
#
# Legacy execute_direct_action / infer_* / pending_operations paths are kept.
# ---------------------------------------------------------------------------


def _posthire_action(ctx: ExecutionContext) -> dict[str, Any]:
    action = dict(ctx.action)
    actor_phone = getattr(ctx.request, "sender_phone", None) or action.get("actor_phone") or action.get("viewer_phone")
    if actor_phone and not action.get("viewer_phone"):
        action["viewer_phone"] = actor_phone
    # The registry tool schema speaks "employee_name"/"employee_phone" (clean,
    # LLM- and dashboard-facing vocabulary), but the legacy attendance/shift/
    # onboarding/payroll resolvers read "subject_name"/"subject_phone". Bridge
    # the two so employee resolution behaves identically no matter which name
    # the caller used. We only fill the legacy keys when unset to avoid clobber.
    if action.get("employee_name") and not action.get("subject_name"):
        action["subject_name"] = action["employee_name"]
    if action.get("employee_phone") and not action.get("subject_phone"):
        action["subject_phone"] = action["employee_phone"]
    return action


def _posthire_actor_phone(ctx: ExecutionContext) -> Any:
    return getattr(ctx.request, "sender_phone", None) or ctx.action.get("actor_phone") or ctx.action.get("viewer_phone")


def _posthire_account_id(ctx: ExecutionContext) -> Any:
    return getattr(ctx.request, "account_id", None)


def _posthire_scope_block(
    ctx: ExecutionContext,
    action: dict[str, Any],
    employee: dict[str, Any],
    *,
    action_type: str,
) -> dict[str, Any] | None:
    """Manager-scope gate for post-hire employee-object executors.

    Mirrors the leave path: the actor's phone was injected as viewer_phone by
    _posthire_action, so a scoped manager can only act on employees inside their
    org scope. HR admins with no manager_scopes row stay unrestricted. Returns a
    normalized error result to short-circuit the executor, or None when allowed.
    """

    legacy = ctx.legacy
    viewer_phone = action.get("viewer_phone")
    if not viewer_phone or not employee:
        return None
    company = str(employee.get("company_code") or action.get("company_code") or "WATHEFNI").upper()
    if legacy.manager_scope_allows_employee(employee, company_code=company, viewer_phone=viewer_phone):
        return None
    msg = "That employee is outside your manager scope."
    return legacy.normalize_posthire_result(
        {"ok": False, "error": "employee_outside_manager_scope", "safe_user_message": msg},
        action_type=action_type,
        reply=msg,
    )


# --- post-execute notification hooks (parity with execute_direct_action) ----

def _hook_notify_shift_created(legacy: Any, ctx: ExecutionContext, result: dict[str, Any]) -> None:
    result["employee_notification"] = legacy.notify_employee_shift_created(
        result=result, account_id=_posthire_account_id(ctx), created_by_phone=_posthire_actor_phone(ctx)
    )


def _hook_notify_shift_cancelled(legacy: Any, ctx: ExecutionContext, result: dict[str, Any]) -> None:
    result["employee_notification"] = legacy.notify_employee_shift_cancelled(
        result=result, account_id=_posthire_account_id(ctx), created_by_phone=_posthire_actor_phone(ctx)
    )


def _hook_notify_late_checkin(legacy: Any, ctx: ExecutionContext, result: dict[str, Any]) -> None:
    attendance = result.get("attendance") if isinstance(result.get("attendance"), dict) else {}
    try:
        late = int(attendance.get("late_minutes") or 0)
    except Exception:
        late = 0
    if late > 0:
        result["hr_notification"] = legacy.notify_attendance_exception(
            result, account_id=_posthire_account_id(ctx), event_type="late_check_in"
        )


def _hook_notify_marked_absent(legacy: Any, ctx: ExecutionContext, result: dict[str, Any]) -> None:
    result["hr_notification"] = legacy.notify_attendance_exception(
        result, account_id=_posthire_account_id(ctx), event_type="marked_absent"
    )


def _posthire_confirm_preflight(action_type: str, phrase: str) -> ExecutorCallable:
    """Cheap, DB-free preflight that yields a clean HR confirmation prompt for a
    sensitive post-hire action. Always returns ready; the requires_confirmation
    gate + pending_actions/action_hash provide the actual safety.
    """

    def preflight(ctx: ExecutionContext) -> dict[str, Any]:
        action = _posthire_action(ctx)
        who = action.get("employee_name") or action.get("subject_name") or action.get("employee_phone") or action.get("subject_phone")
        suffix = f" for {who}" if who else ""
        text = f"{phrase}{suffix}?"
        return {"action_type": action_type, "status": "ready", "success": True, "message": text, "confirmation_text": text}

    return preflight


def _posthire_identity_confirm_preflight(action_type: str, phrase: str) -> ExecutorCallable:
    """Confirm-preflight that resolves employee identity before asking to confirm.

    Prevents the Assistant from confirming a bare duplicate name as if it were
    one person. Ambiguous / missing matches return clarification instead of ready.
    """

    def preflight(ctx: ExecutionContext) -> dict[str, Any]:
        action = _posthire_action(ctx)
        legacy = ctx.legacy
        company = str(action.get("company_code") or getattr(ctx.request, "account_id", None) or "").strip().upper()
        typed = None
        if hasattr(legacy, "resolve_employee_typed"):
            typed = legacy.resolve_employee_typed(
                employee_key=action.get("employee_key"),
                employee_phone=action.get("subject_phone") or action.get("employee_phone"),
                employee_name=action.get("subject_name") or action.get("employee_name"),
                company_code=company or None,
            )
        status = str((typed or {}).get("status") or "")
        if status == "ambiguous":
            choices = typed.get("choices") or typed.get("matches") or []
            lines = [
                f"I found {len(choices)} employees named "
                f"{action.get('employee_name') or action.get('subject_name') or 'that'}. "
                "Which one should I use?"
            ]
            for item in choices[:5]:
                if not isinstance(item, dict):
                    continue
                key = item.get("employee_key") or item.get("phone") or ""
                name = item.get("name") or "Employee"
                lines.append(f"- {name} (`{key}`)")
            message = "\n".join(lines)
            return {
                "action_type": action_type,
                "status": "needs_clarification",
                "success": False,
                "error": "ambiguous_employee",
                "choices": choices[:5],
                "message": message,
                "safe_user_message": message,
                "confirmation_text": message,
            }
        if status == "employee_not_found":
            message = "I could not find that employee. Please use the exact employee key, name, or phone."
            return {
                "action_type": action_type,
                "status": "needs_clarification",
                "success": False,
                "error": "employee_not_found",
                "message": message,
                "safe_user_message": message,
                "confirmation_text": message,
            }
        who = None
        if status == "resolved" and isinstance((typed or {}).get("employee"), dict):
            emp = typed["employee"]
            who = f"{emp.get('name') or 'Employee'} (`{emp.get('employee_key') or emp.get('phone') or ''}`)"
            action["employee_key"] = emp.get("employee_key") or action.get("employee_key")
        if not who:
            who = action.get("employee_name") or action.get("subject_name") or action.get("employee_phone") or action.get("subject_phone")
        suffix = f" for {who}" if who else ""
        text = f"{phrase}{suffix}?"
        return {"action_type": action_type, "status": "ready", "success": True, "message": text, "confirmation_text": text}

    return preflight


def _posthire_executor(
    action_type: str,
    fn_name: str,
    *,
    created_by: bool = False,
    account_id: bool = False,
    reply_fn: str | None = None,
    reply_args: tuple[Any, ...] = (),
    force_flags: dict[str, Any] | None = None,
    post_hooks: tuple[Any, ...] = (),
) -> ExecutorCallable:
    """Build a registry executor that wraps an existing app.py post-hire function.

    The legacy function keeps full authority over validation, DB writes, sheet
    sync, and audit events; this only translates ExecutionContext into the legacy
    call and normalizes the result.
    """

    def executor(ctx: ExecutionContext) -> dict[str, Any]:
        legacy = ctx.legacy
        action = _posthire_action(ctx)
        if force_flags:
            for key, value in force_flags.items():
                action[key] = value
        kwargs: dict[str, Any] = {"company_code": action.get("company_code")}
        if created_by:
            kwargs["created_by_phone"] = _posthire_actor_phone(ctx)
        if account_id:
            kwargs["account_id"] = _posthire_account_id(ctx)
        result = getattr(legacy, fn_name)(action, **kwargs)
        if isinstance(result, dict) and result.get("ok"):
            for hook in post_hooks:
                try:
                    hook(legacy, ctx, result)
                except Exception:
                    logger.warning("post-hire notification hook failed for %s", action_type, exc_info=True)
        reply = None
        if reply_fn:
            try:
                reply = getattr(legacy, reply_fn)(result, *reply_args)
            except Exception:
                reply = None
        return legacy.normalize_posthire_result(result, action_type=action_type, reply=reply)

    return executor


def _send_onboarding_reminder_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Onboarding reminder has a non-standard signature (employee object), so it
    gets a bespoke adapter that mirrors the execute_direct_action branch exactly.
    """

    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee name or phone before I send the onboarding reminder."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="send_onboarding_reminder",
            reply=msg,
        )
    blocked = _posthire_scope_block(ctx, action, employee, action_type="send_onboarding_reminder")
    if blocked is not None:
        return blocked
    result = legacy.send_onboarding_reminder(employee, _posthire_account_id(ctx))
    name = employee.get("name") or action.get("subject_name") or "the employee"
    if isinstance(result, dict) and result.get("ok"):
        try:
            result["reminder_update"] = legacy.mark_onboarding_reminder_sent(str(employee.get("employee_key")))
        except Exception:
            pass
        reply = f"Reminder sent to {name}."
    else:
        send_error = (result.get("send") or {}).get("error") if isinstance(result, dict) and isinstance(result.get("send"), dict) else None
        if send_error in ("conversation_closed", "conversation_inactive"):
            reply = f"I found {name}, but the WhatsApp conversation is not active. {name} needs to message us again before we can send the reminder."
        else:
            reply = f"I could not send the reminder to {name}."
    return legacy.normalize_posthire_result(result, action_type="send_onboarding_reminder", reply=reply)


def _compliance_send_reminder_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Compliance reminder mirrors the onboarding reminder: employee-object
    signature, so it gets a bespoke adapter rather than the generic wrapper."""

    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee name or phone before I send the compliance reminder."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="compliance_send_reminder",
            reply=msg,
        )
    document_type = (str(action.get("document_type") or "")).strip() or None
    result = legacy.send_compliance_reminder(employee, document_type, _posthire_account_id(ctx))
    name = employee.get("name") or action.get("subject_name") or "the employee"
    if isinstance(result, dict) and result.get("ok"):
        reply = f"Compliance reminder sent to {name}."
    elif isinstance(result, dict) and result.get("error") in ("nothing_outstanding", "document_not_found"):
        reply = result.get("safe_user_message") or f"There is nothing outstanding to remind {name} about."
    else:
        send_error = (result.get("send") or {}).get("error") if isinstance(result, dict) and isinstance(result.get("send"), dict) else None
        if send_error in ("conversation_closed", "conversation_inactive"):
            reply = f"I found {name}, but the WhatsApp conversation is not active. {name} needs to message us again before we can send the reminder."
        else:
            reply = f"I could not send the compliance reminder to {name}."
    return legacy.normalize_posthire_result(result, action_type="compliance_send_reminder", reply=reply)


def _compliance_mark_reviewed_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Mark a compliance document as reviewed by HR (clears 'needs review')."""

    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee name or phone before I can mark a document reviewed."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="compliance_mark_reviewed",
            reply=msg,
        )
    document_type = (str(action.get("document_type") or "")).strip() or None
    if not document_type:
        msg = "Which document should I mark as reviewed?"
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "needs_clarification", "safe_user_message": msg},
            action_type="compliance_mark_reviewed",
            reply=msg,
        )
    note = (str(action.get("notes") or "")).strip() or None
    result = legacy.mark_compliance_reviewed(employee, document_type, note)
    name = employee.get("name") or "the employee"
    if isinstance(result, dict) and result.get("ok"):
        label = result.get("document_label") or "document"
        reply = f"Marked {name}'s {label} as reviewed."
    else:
        reply = (result.get("safe_user_message") if isinstance(result, dict) else None) or f"I could not mark that document reviewed for {name}."
    return legacy.normalize_posthire_result(result, action_type="compliance_mark_reviewed", reply=reply)


def _onboarding_start_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Start (or restart) the onboarding flow for an employee from the dashboard.
    Dark-launched behind WATHEFNI_ONBOARDING_HR_MUTATE; Wave 2B also allows
    synthetic canary targets when global HR_MUTATE is off."""

    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee before I can start onboarding."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="start_onboarding",
            reply=msg,
        )
    gate = legacy.onboarding_mutation_gate_error(employee)
    if gate is not None:
        return legacy.normalize_posthire_result(
            gate,
            action_type="start_onboarding",
            reply=gate.get("safe_user_message") or "Onboarding changes are not enabled.",
        )
    blocked = _posthire_scope_block(ctx, action, employee, action_type="start_onboarding")
    if blocked is not None:
        return blocked
    name = employee.get("name") or action.get("subject_name") or "the employee"
    delayed = str(action.get("delayed") or "").lower() in {"1", "true", "yes", "on"}
    try:
        started = legacy.start_onboarding(
            employee,
            planned_start_date=action.get("planned_start_date") or action.get("start_date"),
            delayed=delayed,
            allow_restart=str(action.get("allow_restart") or "").lower() in {"1", "true", "yes"},
            actor_phone=action.get("viewer_phone"),
        )
        if isinstance(started, dict) and not started.get("ok"):
            err = started.get("error")
            if err == "onboarding_terminal":
                msg = f"Onboarding for {name} is already closed."
            elif err == "delayed_start_requires_future_date":
                msg = "A delayed start needs a future planned start date."
            else:
                msg = started.get("safe_user_message") or f"I could not start onboarding for {name}."
            return legacy.normalize_posthire_result(
                {**started, "safe_user_message": msg},
                action_type="start_onboarding",
                reply=msg,
            )
        status = (started or {}).get("status") if isinstance(started, dict) else "in_progress"
        result = {
            "ok": True,
            "employee": legacy.json_safe(legacy.posthire_employee_card(employee)),
            "onboarding_status": status or "in_progress",
            "idempotent": bool((started or {}).get("idempotent")) if isinstance(started, dict) else False,
            "start": legacy.json_safe(started) if isinstance(started, dict) else None,
        }
        if result["idempotent"]:
            reply = f"Onboarding for {name} is already in progress."
        elif status == "delayed":
            reply = f"Onboarding for {name} is scheduled (delayed start)."
        else:
            reply = f"Onboarding started for {name}."
    except Exception:
        logger.warning("start_onboarding failed", exc_info=True)
        result = {"ok": False, "error": "start_failed", "safe_user_message": f"I could not start onboarding for {name}."}
        reply = f"I could not start onboarding for {name}."
    return legacy.normalize_posthire_result(result, action_type="start_onboarding", reply=reply)


def _onboarding_mark_item_executor(ctx: ExecutionContext) -> dict[str, Any]:
    """Mark one onboarding checklist item accepted/waived from the dashboard.
    Dark-launched behind WATHEFNI_ONBOARDING_HR_MUTATE; Wave 2B also allows
    synthetic canary targets when global HR_MUTATE is off."""

    legacy = ctx.legacy
    action = _posthire_action(ctx)
    # Resolve early so synthetic canary gate can allow without global HR_MUTATE.
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if employee is not None:
        gate = legacy.onboarding_mutation_gate_error(employee)
        if gate is not None:
            return legacy.normalize_posthire_result(
                gate,
                action_type="onboarding_mark_item",
                reply=gate.get("safe_user_message") or "Onboarding changes are not enabled.",
            )
    elif not legacy.onboarding_hr_mutate_enabled() and not legacy.onboarding_synthetic_canary_enabled():
        msg = "Onboarding changes from the dashboard are not enabled yet."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "feature_disabled", "safe_user_message": msg},
            action_type="onboarding_mark_item",
            reply=msg,
        )
    result = legacy.mark_onboarding_item(
        action,
        company_code=action.get("company_code"),
        created_by_phone=_posthire_actor_phone(ctx),
    )
    if isinstance(result, dict) and result.get("ok"):
        label = result.get("item_label") or "checklist item"
        verb = "waived" if result.get("item_status") == "waived" else "accepted"
        reply = f"{label.capitalize()} {verb}."
    else:
        reply = (result.get("safe_user_message") if isinstance(result, dict) else None) or "I could not update that checklist item."
    return legacy.normalize_posthire_result(result, action_type="onboarding_mark_item", reply=reply)


_POSTHIRE_RESULT_KEYS = (
    "action_type", "success", "status", "message", "safe_user_message",
    "employee", "employee_notification", "hr_notification",
    "attendance", "shift", "created", "cancelled", "conflicts",
    "swap", "timesheet", "timesheets", "policy", "export", "summaries", "analytics",
)


# === Attendance =============================================================

register(ActionSpec(
    name="list_attendance",
    description="List attendance records for the company or one employee over a date range. Read-only. Use for 'who was late', 'show today's attendance', 'attendance for Sara this week'.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "status", "start_date", "end_date"),
    module="attendance", requires_confirmation=False,
    executor=_posthire_executor("list_attendance", "list_attendance", reply_fn="format_list_attendance_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_attendance.",
))

register(ActionSpec(
    name="check_in_employee",
    description="Record an employee check-in (clock-in) against their scheduled shift. Provide the employee; an optional time. Requires a scheduled shift for that day.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_id", "time"),
    module="attendance", requires_confirmation=False,
    executor=_posthire_executor("check_in_employee", "check_in_employee", created_by=True, reply_fn="format_attendance_mutation_reply", reply_args=("check_in_employee",), post_hooks=(_hook_notify_late_checkin,)),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.check_in_employee; late check-in notifies HR.",
))

register(ActionSpec(
    name="check_out_employee",
    description="Record an employee check-out (clock-out) for their shift that day. Provide the employee; an optional time.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_id", "time"),
    module="attendance", requires_confirmation=False,
    executor=_posthire_executor("check_out_employee", "check_out_employee", created_by=True, reply_fn="format_attendance_mutation_reply", reply_args=("check_out_employee",)),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.check_out_employee.",
))

register(ActionSpec(
    name="mark_attendance_absent",
    description="Mark an employee absent for a day. SENSITIVE: ask the user to confirm first. Blocked if the employee has approved leave that day.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "date", "notes"),
    module="attendance", requires_confirmation=True,
    executor=_posthire_executor("mark_attendance_absent", "mark_attendance_absent", created_by=True, reply_fn="format_attendance_mutation_reply", reply_args=("mark_attendance_absent",), force_flags={"allow_without_shift": True}, post_hooks=(_hook_notify_marked_absent,)),
    preflight=_posthire_confirm_preflight("mark_attendance_absent", "Mark absent"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.mark_attendance_absent; allow_without_shift set post-confirmation.",
))

register(ActionSpec(
    name="correct_attendance_record",
    description="Correct an existing attendance record (status/time) for an employee on a day. SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "date", "status", "time", "notes"),
    module="attendance", requires_confirmation=True,
    executor=_posthire_executor("correct_attendance_record", "correct_attendance_record", created_by=True, reply_fn="format_attendance_mutation_reply", reply_args=("correct_attendance_record",), force_flags={"allow_without_shift": True}),
    preflight=_posthire_confirm_preflight("correct_attendance_record", "Correct the attendance record"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.correct_attendance_record; allow_without_shift set post-confirmation.",
))


# === Shifts =================================================================

register(ActionSpec(
    name="list_shifts",
    description="List scheduled shifts for the company or one employee over a date range. Read-only.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "start_date", "end_date"),
    module="shifts", requires_confirmation=False,
    executor=_posthire_executor("list_shifts", "list_shifts", reply_fn="format_list_shifts_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_shifts.",
))

register(ActionSpec(
    name="list_availability",
    description="List employee availability submissions over a date range. Read-only.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "start_date", "end_date"),
    module="shifts", requires_confirmation=False,
    executor=_posthire_executor("list_availability", "list_availability", reply_fn="format_list_availability_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_availability.",
))

register(ActionSpec(
    name="list_shift_swaps",
    description="List shift swap requests and their status. Read-only.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "status"),
    module="shifts", requires_confirmation=False,
    executor=_posthire_executor("list_shift_swaps", "list_shift_swaps", reply_fn="format_list_shift_swaps_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_shift_swaps.",
))

register(ActionSpec(
    name="create_shift_assignment",
    description="Schedule a shift for one or more employees (date + start/end time). Notifies the employee(s). Use for 'schedule Sara 9-5 tomorrow', 'assign the morning shift'. SENSITIVE: confirm first.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_date", "start_time", "end_time"),
    module="shifts", requires_confirmation=True,
    executor=_posthire_executor("create_shift_assignment", "create_shift_assignment", created_by=True, reply_fn="format_create_shift_reply", post_hooks=(_hook_notify_shift_created,)),
    preflight=_posthire_identity_confirm_preflight("create_shift_assignment", "Schedule the shift"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.create_shift_assignment; notifies employees.",
))

register(ActionSpec(
    name="cancel_shift_assignment",
    description="Cancel scheduled shift(s) for an employee in a date range. SENSITIVE: ask the user to confirm first. Notifies the employee.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_date", "start_date", "end_date"),
    module="shifts", requires_confirmation=True,
    executor=_posthire_executor("cancel_shift_assignment", "cancel_shift_assignment", created_by=True, reply_fn="format_cancel_shift_reply", post_hooks=(_hook_notify_shift_cancelled,)),
    preflight=_posthire_confirm_preflight("cancel_shift_assignment", "Cancel the scheduled shift(s)"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.cancel_shift_assignment.",
))

register(ActionSpec(
    name="replace_conflicting_shift_assignment",
    description="Replace an existing conflicting shift with a new assignment. SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_date", "start_time", "end_time"),
    module="shifts", requires_confirmation=True,
    executor=_posthire_executor("replace_conflicting_shift_assignment", "replace_conflicting_shift_assignment", created_by=True, account_id=True, reply_fn="format_replace_shift_reply"),
    preflight=_posthire_confirm_preflight("replace_conflicting_shift_assignment", "Replace the conflicting shift"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.replace_conflicting_shift_assignment.",
))

register(ActionSpec(
    name="request_availability",
    description="Ask an employee to submit their availability for a period. Sends them a request. Use for 'ask Sara for her availability next week'.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "start_date", "end_date"),
    module="shifts", requires_confirmation=False,
    executor=_posthire_executor("request_availability", "request_availability", created_by=True, account_id=True, reply_fn="format_request_availability_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.request_availability.",
))

register(ActionSpec(
    name="request_shift_swap",
    description="Open a shift swap request for an employee/shift. Use for 'Sara wants to swap her Friday shift'.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "shift_id", "shift_date"),
    module="shifts", requires_confirmation=False,
    executor=_posthire_executor("request_shift_swap", "request_shift_swap", created_by=True, account_id=True, reply_fn="format_request_shift_swap_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.request_shift_swap.",
))

register(ActionSpec(
    name="approve_shift_swap",
    description="Approve a pending shift swap request. SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("swap_id", "employee_name", "employee_phone"),
    module="shifts", requires_confirmation=True,
    executor=_posthire_executor("approve_shift_swap", "approve_shift_swap", created_by=True, account_id=True, reply_fn="format_shift_swap_decision_reply", reply_args=("approved",)),
    preflight=_posthire_confirm_preflight("approve_shift_swap", "Approve the shift swap"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.approve_shift_swap.",
))

register(ActionSpec(
    name="reject_shift_swap",
    description="Reject a pending shift swap request. SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("swap_id", "employee_name", "employee_phone"),
    module="shifts", requires_confirmation=True,
    executor=_posthire_executor("reject_shift_swap", "reject_shift_swap", created_by=True, account_id=True, reply_fn="format_shift_swap_decision_reply", reply_args=("rejected",)),
    preflight=_posthire_confirm_preflight("reject_shift_swap", "Reject the shift swap"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.reject_shift_swap.",
))


# === Onboarding =============================================================

register(ActionSpec(
    name="list_onboarding_status",
    description=(
        "List onboarding status for the company. Read-only. Answers 'who hasn't completed onboarding', "
        "'which employees have pending onboarding items', and 'who is missing/has not uploaded a specific "
        "document' (e.g. Civil ID, passport). Optional filters: document_type (e.g. civil_id, passport), "
        "status (not_started|in_progress|complete), pending_only, employee_name/employee_phone. "
        "Same source of truth as the dashboard Onboarding page."
    ),
    required_fields=(), optional_fields=("document_type", "item", "status", "pending_only", "employee_name", "employee_phone"),
    module="onboarding", requires_confirmation=False,
    executor=_posthire_executor("list_onboarding_status", "list_onboarding_status", reply_fn="format_list_onboarding_status_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False,
    notes="Wraps app.list_onboarding_status (read-only, manager-scoped, metadata only). Dark-launched behind WATHEFNI_ASSISTANT_HR_READS.",
))

register(ActionSpec(
    name="send_onboarding_reminder",
    description="Send an onboarding reminder to a new hire over WhatsApp. Provide the employee name or phone. Use for 'remind the new hire about their documents'.",
    required_fields=(), optional_fields=("employee_name", "employee_phone"),
    module="onboarding", requires_confirmation=False,
    executor=_send_onboarding_reminder_executor,
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False,
    notes="Wraps app.send_onboarding_reminder (employee-object signature). answer_onboarding_status remains legacy-only.",
))

register(ActionSpec(
    name="start_onboarding",
    description="Start (or restart) the onboarding flow for an employee from the dashboard. Provide employee_key (preferred) or name/phone. SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("employee_key", "employee_name", "employee_phone"),
    module="onboarding", requires_confirmation=True,
    executor=_onboarding_start_executor,
    preflight=_posthire_confirm_preflight("start_onboarding", "Start onboarding"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True,
    notes="Wraps app.start_onboarding; HR-driven dashboard mutation, dark-launched behind WATHEFNI_ONBOARDING_HR_MUTATE. Seeds the onboarding checklist from the company template (WATHEFNI_ONBOARDING_SEED, idempotent).",
))

register(ActionSpec(
    name="onboarding_mark_item",
    description="Mark one onboarding checklist item as accepted or waived for an employee. Provide employee_key (or name/phone) and item_id; optional item_status ('accepted' or 'waived'; legacy 'received' maps to accepted under Wave 2A). SENSITIVE: ask the user to confirm first.",
    required_fields=(), optional_fields=("employee_key", "employee_name", "employee_phone", "item_id", "item_status", "notes", "expected_row_version"),
    module="onboarding", requires_confirmation=True,
    executor=_onboarding_mark_item_executor,
    preflight=_posthire_confirm_preflight("onboarding_mark_item", "Update the onboarding checklist item"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True,
    notes="Wave 2A: writes accepted/waived via shared lifecycle (never ambiguous received when flag on). Dark-launched behind WATHEFNI_ONBOARDING_HR_MUTATE.",
))


def _onboarding_cancel_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee before I can cancel onboarding."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="cancel_onboarding",
            reply=msg,
        )
    gate = legacy.onboarding_mutation_gate_error(employee)
    if gate is not None:
        return legacy.normalize_posthire_result(gate, action_type="cancel_onboarding", reply=gate.get("safe_user_message"))
    blocked = _posthire_scope_block(ctx, action, employee, action_type="cancel_onboarding")
    if blocked is not None:
        return blocked
    result = legacy.cancel_employee_onboarding(
        {**action, "viewer_phone": action.get("viewer_phone")},
        company_code=action.get("company_code") or employee.get("company_code"),
        created_by_phone=_posthire_actor_phone(ctx),
    )
    name = employee.get("name") or "the employee"
    if result.get("ok"):
        reply = f"Onboarding for {name} was cancelled. Checklist history was kept."
    else:
        reply = result.get("safe_user_message") or f"I could not cancel onboarding for {name}."
    return legacy.normalize_posthire_result(result, action_type="cancel_onboarding", reply=reply)


def _onboarding_reschedule_executor(ctx: ExecutionContext) -> dict[str, Any]:
    legacy = ctx.legacy
    action = _posthire_action(ctx)
    employee = legacy.resolve_employee_for_direct_action(action, allow_latest=False)
    if not employee:
        msg = "I need the employee before I can reschedule onboarding."
        return legacy.normalize_posthire_result(
            {"ok": False, "error": "employee_not_found", "safe_user_message": msg},
            action_type="reschedule_onboarding",
            reply=msg,
        )
    gate = legacy.onboarding_mutation_gate_error(employee)
    if gate is not None:
        return legacy.normalize_posthire_result(gate, action_type="reschedule_onboarding", reply=gate.get("safe_user_message"))
    blocked = _posthire_scope_block(ctx, action, employee, action_type="reschedule_onboarding")
    if blocked is not None:
        return blocked
    result = legacy.reschedule_employee_onboarding(
        {**action, "viewer_phone": action.get("viewer_phone")},
        company_code=action.get("company_code") or employee.get("company_code"),
        created_by_phone=_posthire_actor_phone(ctx),
    )
    name = employee.get("name") or "the employee"
    if result.get("ok"):
        reply = f"Onboarding start date for {name} was updated."
    else:
        reply = result.get("safe_user_message") or f"I could not reschedule onboarding for {name}."
    return legacy.normalize_posthire_result(result, action_type="reschedule_onboarding", reply=reply)


register(ActionSpec(
    name="cancel_onboarding",
    description="Cancel or withdraw onboarding for an employee without deleting checklist history. Provide employee_key. SENSITIVE: confirm first.",
    required_fields=(), optional_fields=("employee_key", "employee_name", "employee_phone", "reason"),
    module="onboarding", requires_confirmation=True,
    executor=_onboarding_cancel_executor,
    preflight=_posthire_confirm_preflight("cancel_onboarding", "Cancel onboarding"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True,
    notes="Wave 4: cancel preserves history; gated by HR_MUTATE + company allowlist.",
))

register(ActionSpec(
    name="reschedule_onboarding",
    description="Reschedule the planned onboarding start date and refresh open-item due dates. Provide employee_key and planned_start_date (YYYY-MM-DD). SENSITIVE: confirm first.",
    required_fields=(), optional_fields=("employee_key", "employee_name", "employee_phone", "planned_start_date", "start_date"),
    module="onboarding", requires_confirmation=True,
    executor=_onboarding_reschedule_executor,
    preflight=_posthire_confirm_preflight("reschedule_onboarding", "Reschedule onboarding start"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True,
    notes="Wave 4: reschedule with due-date recompute; gated by HR_MUTATE + company allowlist.",
))


# === Compliance =============================================================

register(ActionSpec(
    name="list_compliance_documents",
    description=(
        "List employee compliance documents by status. Read-only. Answers 'who has expired documents', "
        "'who has documents expiring this month', 'which documents need HR review', and 'who is missing a "
        "specific document'. Optional filters: status (expired|expiring_soon|missing|needs_review|valid), "
        "document_type (e.g. civil_id, passport), timeframe ('this_month'), employee_name/employee_phone. "
        "Same source of truth as the dashboard Compliance page."
    ),
    required_fields=(), optional_fields=("status", "document_type", "item", "timeframe", "employee_name", "employee_phone"),
    module="compliance", requires_confirmation=False,
    executor=_posthire_executor("list_compliance_documents", "list_compliance_documents", reply_fn="format_list_compliance_documents_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False,
    notes="Wraps app.list_compliance_documents (read-only, manager-scoped, metadata only). Dark-launched behind WATHEFNI_ASSISTANT_HR_READS.",
))

register(ActionSpec(
    name="compliance_send_reminder",
    description="Send a WhatsApp reminder to an employee about a missing, expiring, or expired compliance document. Identify the employee by name or phone. Optionally pass document_type to target one document; omit it to cover all of the employee's outstanding documents.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "document_type"),
    module="compliance", requires_confirmation=False,
    executor=_compliance_send_reminder_executor,
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False,
    notes="Wraps app.send_compliance_reminder (employee-object signature); bumps reminder_count/last_alerted_at on a successful send.",
))

register(ActionSpec(
    name="compliance_mark_reviewed",
    description="Mark an employee's compliance document as reviewed by HR, clearing the 'needs review' flag (used when a document was received but its expiry could not be read). Provide the employee (name or phone) and the document_type. Optional note.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "document_type", "notes"),
    module="compliance", requires_confirmation=False,
    executor=_compliance_mark_reviewed_executor,
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False,
    notes="Wraps app.mark_compliance_reviewed; expiry-bearing documents are still re-derived by the classifier so this cannot fake validity.",
))


# === Payroll (sensitive money domain) =======================================

register(ActionSpec(
    name="list_payroll_hours",
    description="Show computed payroll hours (worked/scheduled/overtime/late) for the company or one employee over a period. Read-only.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "start_date", "end_date"),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("list_payroll_hours", "list_payroll_hours", reply_fn="format_payroll_hours_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_payroll_hours.",
))

register(ActionSpec(
    name="list_timesheets",
    description="List payroll timesheets and their review status over a period. Read-only.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "status", "start_date", "end_date"),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("list_timesheets", "list_timesheets", reply_fn="format_list_timesheets_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_timesheets.",
))

register(ActionSpec(
    name="show_payroll_policy",
    description="Show the company's current payroll policy (overtime, late thresholds, rounding). Read-only.",
    required_fields=(), optional_fields=(),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("show_payroll_policy", "show_payroll_policy", reply_fn="format_show_payroll_policy_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.show_payroll_policy.",
))

register(ActionSpec(
    name="preview_payroll",
    description="Preview the payroll run for a period without exporting it. Read-only.",
    required_fields=(), optional_fields=("start_date", "end_date"),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("preview_payroll", "preview_payroll", reply_fn="format_preview_payroll_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.preview_payroll.",
))

register(ActionSpec(
    name="list_payroll_exports",
    description="List previous payroll exports. Read-only.",
    required_fields=(), optional_fields=("start_date", "end_date"),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("list_payroll_exports", "list_payroll_exports", reply_fn="format_list_payroll_exports_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.list_payroll_exports.",
))

register(ActionSpec(
    name="create_timesheet_review",
    description="Open a payroll timesheet review for an employee/period so it can be approved later.",
    required_fields=(), optional_fields=("employee_name", "employee_phone", "start_date", "end_date"),
    module="payroll", requires_confirmation=False,
    executor=_posthire_executor("create_timesheet_review", "create_timesheet_review", created_by=True, reply_fn="format_create_timesheet_review_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.create_timesheet_review.",
))

register(ActionSpec(
    name="approve_timesheet",
    description="Approve a payroll timesheet. SENSITIVE money action: ask the user to confirm first.",
    required_fields=(), optional_fields=("timesheet_id", "employee_name", "employee_phone"),
    module="payroll", requires_confirmation=True,
    executor=_posthire_executor("approve_timesheet", "approve_timesheet", created_by=True, reply_fn="format_timesheet_decision_reply", reply_args=("approved",)),
    preflight=_posthire_confirm_preflight("approve_timesheet", "Approve the timesheet"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.approve_timesheet.",
))

register(ActionSpec(
    name="reject_timesheet",
    description="Reject a payroll timesheet. SENSITIVE money action: ask the user to confirm first.",
    required_fields=(), optional_fields=("timesheet_id", "employee_name", "employee_phone", "notes"),
    module="payroll", requires_confirmation=True,
    executor=_posthire_executor("reject_timesheet", "reject_timesheet", created_by=True, reply_fn="format_timesheet_decision_reply", reply_args=("rejected",)),
    preflight=_posthire_confirm_preflight("reject_timesheet", "Reject the timesheet"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.reject_timesheet.",
))

register(ActionSpec(
    name="set_payroll_policy",
    description="Update the company's payroll policy (overtime/late/rounding). SENSITIVE money action: ask the user to confirm the exact change first.",
    required_fields=(),
    optional_fields=(
        "structured_policy", "employee_pay_type", "leave_policy", "overtime_policy",
        "overtime_cap_hours", "absence_deduction_enabled", "late_deduction_enabled",
        "early_leave_deduction_enabled", "default_hourly_rate_kwd", "currency",
    ),
    module="payroll", requires_confirmation=True,
    executor=_posthire_executor("set_payroll_policy", "set_payroll_policy", created_by=True, reply_fn="format_set_payroll_policy_reply"),
    preflight=_posthire_confirm_preflight("set_payroll_policy", "Update the payroll policy"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.set_payroll_policy.",
))

register(ActionSpec(
    name="export_payroll",
    description="Export the payroll run for a period (produces the payroll file). HIGHLY SENSITIVE money action gated by the payroll.export permission: always ask the user to confirm the exact period first.",
    required_fields=(), optional_fields=("start_date", "end_date"),
    module="payroll", requires_confirmation=True,
    executor=_posthire_executor("export_payroll", "export_payroll", created_by=True, reply_fn="format_export_payroll_reply"),
    preflight=_posthire_confirm_preflight("export_payroll", "Export payroll for the requested period"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=True, notes="Wraps app.export_payroll; separate payroll.export permission.",
))


# === Analytics ==============================================================

register(ActionSpec(
    name="workforce_analytics",
    description="Answer a workforce analytics attention question (lateness, absences, hours-above-schedule non-payroll signal, branch concentration, pending review) from operational data. Read-only; not money authority.",
    required_fields=(), optional_fields=("metric", "start_date", "end_date"),
    module="analytics", requires_confirmation=False,
    executor=_posthire_executor("workforce_analytics", "workforce_analytics", reply_fn="format_workforce_analytics_reply"),
    result_keys=_POSTHIRE_RESULT_KEYS, sensitive=False, notes="Wraps app.workforce_analytics.",
))


# === Platform Assistant Wave 1 — Spine read-only tools ========================
# Summarize / explain / investigate / prepare deep links only. No mutations.
# Gated by WATHEFNI_PLATFORM_ASSISTANT_WAVE1 + HR dashboard channel in schema build.


def _spine_wave1_tools_enabled(legacy: Any) -> bool:
    try:
        import platform_assistant_spine_wave1 as spine

        return bool(spine.platform_assistant_wave1_enabled()) and not spine.assistant_kill_engaged()
    except Exception:
        return False


def _spine_wave2_tools_enabled(legacy: Any) -> bool:
    try:
        import platform_assistant_wave2_safe_ops_reads as wave2

        return bool(wave2.platform_assistant_wave2_enabled()) and not __import__(
            "platform_assistant_spine_wave1", fromlist=["assistant_kill_engaged"]
        ).assistant_kill_engaged()
    except Exception:
        return False


_FLAG_GATED_TOOLS["summarize_action_inbox"] = "platform_assistant_wave1_tools_enabled"
_FLAG_GATED_TOOLS["summarize_employee_360"] = "platform_assistant_wave1_tools_enabled"
_FLAG_GATED_TOOLS["get_launch_readiness_summary"] = "platform_assistant_wave1_tools_enabled"
_FLAG_GATED_TOOLS["summarize_leave_queue"] = "platform_assistant_wave2_tools_enabled"
_FLAG_GATED_TOOLS["summarize_attendance_exceptions"] = "platform_assistant_wave2_tools_enabled"


def _bind_spine_flag(legacy: Any) -> None:
    """Ensure legacy exposes Wave 1/2 tool gate checkers used by build_tool_schemas."""
    if legacy is None:
        return
    if not hasattr(legacy, "platform_assistant_wave1_tools_enabled"):
        setattr(legacy, "platform_assistant_wave1_tools_enabled", lambda: _spine_wave1_tools_enabled(legacy))
    if not hasattr(legacy, "platform_assistant_wave2_tools_enabled"):
        setattr(legacy, "platform_assistant_wave2_tools_enabled", lambda: _spine_wave2_tools_enabled(legacy))


_orig_build_tool_schemas = build_tool_schemas


def build_tool_schemas(legacy: Any, request: Any) -> list[dict[str, Any]]:  # type: ignore[misc]
    _bind_spine_flag(legacy)
    tools = _orig_build_tool_schemas(legacy, request)
    try:
        import platform_assistant_spine_wave1 as spine
    except Exception:
        return tools

    metadata = getattr(request, "metadata", None) if isinstance(getattr(request, "metadata", None), dict) else {}
    channel = str(metadata.get("channel") or "").strip()
    dashboard = channel == "web_dashboard" or bool(metadata.get("dashboard"))
    company = str(metadata.get("company_code") or getattr(request, "company_code", "") or "").upper()

    filtered: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = str(fn.get("name") or tool.get("name") or "")
        if spine.is_spine_read_tool(name):
            if not dashboard or not spine.wave1_enabled_for_company(company or spine.ALLOWED_COMPANY):
                continue
            # Wave 2 tools need Wave 2 flag as well
            try:
                import platform_assistant_wave2_safe_ops_reads as wave2

                if wave2.is_wave2_read_tool(name) and not wave2.wave2_enabled_for_company(company or spine.ALLOWED_COMPANY):
                    continue
            except Exception:
                if name in {"summarize_leave_queue", "summarize_attendance_exceptions"}:
                    continue
        # Mutation kill: hide confirming/sensitive tools from the catalog when mutations denied.
        if not spine.assistant_mutations_allowed():
            spec = spec_for(name)
            if spine.tool_is_mutation(spec):
                continue
        filtered.append(tool)
    return filtered


register(ActionSpec(
    name="summarize_action_inbox",
    description=(
        "Default post-hire entry: summarize Unified Action Inbox attention items (read-only compose). "
        "Prepares deep links into systems of action. Never mutates. Never claims Payroll money or Attendance ingest."
    ),
    required_fields=(),
    optional_fields=("query",),
    module="action_inbox",
    requires_confirmation=False,
    executor=lambda ctx: __import__("platform_assistant_spine_wave1", fromlist=["execute_summarize_action_inbox"]).execute_summarize_action_inbox(ctx),
    result_keys=_POSTHIRE_RESULT_KEYS + ("grounding",),
    sensitive=False,
    notes="Platform Assistant Wave 1 spine — Action Inbox read/prepare only.",
))

register(ActionSpec(
    name="summarize_employee_360",
    description=(
        "Read-only Employees 360 summary for one employee (name or employee_key). "
        "Prepares next-action deep links only. Never mutates employee records."
    ),
    required_fields=(),
    optional_fields=("employee_key", "employee_name", "subject_key", "subject_name", "query"),
    module="employees",
    requires_confirmation=False,
    executor=lambda ctx: __import__("platform_assistant_spine_wave1", fromlist=["execute_summarize_employee_360"]).execute_summarize_employee_360(ctx),
    result_keys=_POSTHIRE_RESULT_KEYS + ("grounding",),
    sensitive=False,
    notes="Platform Assistant Wave 1 spine — Employees 360 read/prepare only.",
))

register(ActionSpec(
    name="get_launch_readiness_summary",
    description=(
        "Read-only Setup Console Launch Readiness summary for WATHEFNI. Explains blockers and prepares deep links. "
        "Never mutates Setup, never enables Attendance ingest or Payroll money, never claims legal/government authority."
    ),
    required_fields=(),
    optional_fields=("query",),
    module="setup_console",
    requires_confirmation=False,
    executor=lambda ctx: __import__("platform_assistant_spine_wave1", fromlist=["execute_get_launch_readiness_summary"]).execute_get_launch_readiness_summary(ctx),
    result_keys=_POSTHIRE_RESULT_KEYS + ("grounding",),
    sensitive=False,
    notes="Platform Assistant Wave 1 spine — Setup readiness read/prepare only.",
))


# === Platform Assistant Wave 2 — Safe Ops Queue Reads ========================

register(ActionSpec(
    name="summarize_leave_queue",
    description=(
        "Summarize the Leave request queue that needs HR attention (pending/needs_review/needs_info). "
        "Groups by employee, team, status, urgency. Prepares deep links into Leave. "
        "Read-only — never approve, reject, or mutate leave. Leave remains the system of action."
    ),
    required_fields=(),
    optional_fields=("query", "status", "employee_key", "employee_name", "start_date", "end_date"),
    module="leave",
    requires_confirmation=False,
    executor=lambda ctx: __import__(
        "platform_assistant_wave2_safe_ops_reads", fromlist=["execute_summarize_leave_queue"]
    ).execute_summarize_leave_queue(ctx),
    result_keys=_POSTHIRE_RESULT_KEYS + ("grounding",),
    sensitive=False,
    notes="Platform Assistant Wave 2 — Leave queue read/prepare only.",
))

register(ActionSpec(
    name="summarize_attendance_exceptions",
    description=(
        "Summarize Attendance exception records (late/absent/pending) from existing attendance records. "
        "Device ingest is OFF — do not claim live punches. Groups by employee, team, status. "
        "Prepares deep links into Attendance. Read-only — never correct or mark absence."
    ),
    required_fields=(),
    optional_fields=("query", "status", "employee_key", "employee_name", "start_date", "end_date"),
    module="attendance",
    requires_confirmation=False,
    executor=lambda ctx: __import__(
        "platform_assistant_wave2_safe_ops_reads", fromlist=["execute_summarize_attendance_exceptions"]
    ).execute_summarize_attendance_exceptions(ctx),
    result_keys=_POSTHIRE_RESULT_KEYS + ("grounding",),
    sensitive=False,
    notes="Platform Assistant Wave 2 — Attendance exceptions read/prepare only; ingest-off honesty.",
))


# === P1 — Assessment / Interview / Video reads + Employment Offers ============


def _assistant_actor_permissions(ctx: ExecutionContext) -> list[str]:
    meta = getattr(ctx.request, "metadata", None) or {}
    if not isinstance(meta, dict):
        return []
    raw = meta.get("permissions") or []
    if isinstance(raw, (list, set, tuple)):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def _assistant_actor_user_id(ctx: ExecutionContext) -> str:
    meta = getattr(ctx.request, "metadata", None) or {}
    if isinstance(meta, dict):
        admin = meta.get("admin_user") if isinstance(meta.get("admin_user"), dict) else {}
        for key in ("user_id", "id", "email", "phone"):
            val = admin.get(key) or meta.get(key)
            if val:
                return str(val)
    return str(getattr(ctx.request, "sender_phone", None) or "assistant")


def _list_assessment_attempts_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    result = p1.list_assessment_attempts(
        legacy,
        company_code=company,
        status=ctx.action.get("status"),
        position=ctx.action.get("position") or ctx.action.get("position_code"),
        limit=int(ctx.action.get("limit") or 25),
    )
    count = int(result.get("count") or 0)
    return {
        "action_type": "list_assessment_attempts",
        "success": bool(result.get("ok")),
        "status": "completed",
        "message": f"Found {count} assessment attempt(s)." if count else "No assessment attempts matched.",
        "safe_user_message": f"Found {count} assessment attempt(s)." if count else "No assessment attempts matched.",
        "result": legacy.json_safe(result),
    }


def _list_live_interviews_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    result = p1.list_live_interviews(
        legacy,
        company_code=company,
        status=ctx.action.get("status"),
        limit=int(ctx.action.get("limit") or 25),
    )
    count = int(result.get("count") or 0)
    return {
        "action_type": "list_live_interviews",
        "success": bool(result.get("ok")),
        "status": "completed",
        "message": f"Found {count} live interview(s)." if count else "No live interviews matched.",
        "safe_user_message": f"Found {count} live interview(s)." if count else "No live interviews matched.",
        "result": legacy.json_safe(result),
    }


def _list_video_interviews_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    result = p1.list_video_interviews(
        legacy,
        company_code=company,
        status=ctx.action.get("status"),
        limit=int(ctx.action.get("limit") or 25),
    )
    count = int(result.get("count") or 0)
    return {
        "action_type": "list_video_interviews",
        "success": bool(result.get("ok")),
        "status": "completed",
        "message": f"Found {count} video interview(s)." if count else "No video interviews matched.",
        "safe_user_message": f"Found {count} video interview(s)." if count else "No video interviews matched.",
        "result": legacy.json_safe(result),
    }


def _list_candidate_offers_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1

    legacy = ctx.legacy
    app = _resolve_app(ctx)
    company = _resolve_company_code(legacy, ctx.request) or str((app or {}).get("company_code") or "")
    app_key = str((app or {}).get("app_key") or ctx.action.get("app_key") or "").strip()
    result = p1.list_candidate_offers(
        legacy,
        company_code=company,
        app_key=app_key,
        permissions=_assistant_actor_permissions(ctx),
    )
    ok = bool(result.get("ok"))
    count = int(result.get("count") or 0)
    msg = result.get("message") or (f"Found {count} offer(s)." if count else "No offers for this candidate.")
    return {
        "action_type": "list_candidate_offers",
        "success": ok,
        "status": "completed" if ok else "failed",
        "message": msg,
        "safe_user_message": msg,
        "result": legacy.json_safe(result),
        "application": legacy.json_safe(app) if app else None,
    }


def _approve_employment_offer_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1
    import offer_lifecycle as offers

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    offer_id = str(ctx.action.get("offer_id") or "").strip()
    if not offer_id:
        return {
            "action_type": "approve_employment_offer",
            "success": False,
            "status": "failed",
            "message": "I need an offer_id to approve.",
            "safe_user_message": "I need an offer_id to approve.",
        }
    try:
        result = p1.approve_employment_offer(
            legacy,
            company_code=company,
            offer_id=offer_id,
            actor_user_id=_assistant_actor_user_id(ctx),
            permissions=_assistant_actor_permissions(ctx),
        )
        return {
            "action_type": "approve_employment_offer",
            "success": True,
            "status": "completed",
            "message": f"Offer {offer_id} approved.",
            "safe_user_message": f"Offer {offer_id} approved.",
            "result": legacy.json_safe(result),
        }
    except offers.OfferAuthorityError as exc:
        return {
            "action_type": "approve_employment_offer",
            "success": False,
            "status": "failed",
            "message": str(exc.message or exc),
            "safe_user_message": str(exc.message or exc),
            "error": getattr(exc, "code", None),
        }


def _send_employment_offer_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p1_tools as p1
    import offer_lifecycle as offers

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    offer_id = str(ctx.action.get("offer_id") or "").strip()
    channel = str(ctx.action.get("preferred_channel") or ctx.action.get("channel") or "whatsapp").strip().lower()
    if not offer_id:
        return {
            "action_type": "send_employment_offer",
            "success": False,
            "status": "failed",
            "message": "I need an offer_id to send.",
            "safe_user_message": "I need an offer_id to send.",
        }
    try:
        result = p1.send_employment_offer(
            legacy,
            company_code=company,
            offer_id=offer_id,
            actor_user_id=_assistant_actor_user_id(ctx),
            permissions=_assistant_actor_permissions(ctx),
            channel=channel,
        )
        ok = bool(result.get("ok"))
        msg = result.get("safe_user_message") or result.get("message") or (
            f"Offer {offer_id} sent via {channel}." if ok else f"Could not send offer {offer_id}."
        )
        return {
            "action_type": "send_employment_offer",
            "success": ok,
            "status": "completed" if ok else "failed",
            "message": msg,
            "safe_user_message": msg,
            "result": legacy.json_safe(result),
        }
    except offers.OfferAuthorityError as exc:
        return {
            "action_type": "send_employment_offer",
            "success": False,
            "status": "failed",
            "message": str(exc.message or exc),
            "safe_user_message": str(exc.message or exc),
            "error": getattr(exc, "code", None),
        }


register(
    ActionSpec(
        name="list_assessment_attempts",
        description="List recent assessment attempts for this company (status, score, needs review). Read-only. Same source of truth as the Assessments page.",
        required_fields=(),
        optional_fields=("status", "position", "position_code", "limit", "query"),
        module="assessments",
        requires_confirmation=False,
        executor=_list_assessment_attempts_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="list_live_interviews",
        description="List live (calendar) interviews for this company. Read-only. Prefer this before scheduling when HR asks what interviews are upcoming.",
        required_fields=(),
        optional_fields=("status", "limit", "query"),
        module="interviews",
        requires_confirmation=False,
        executor=_list_live_interviews_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="list_video_interviews",
        description="List asynchronous video interviews for this company (pending/completed). Read-only.",
        required_fields=(),
        optional_fields=("status", "limit", "query"),
        module="video_interviews",
        requires_confirmation=False,
        executor=_list_video_interviews_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="list_candidate_offers",
        description="List employment offers for a candidate application. Read-only. Requires employment_offers module.",
        entity_type="candidate",
        required_fields=("app_key",),
        optional_fields=("query",),
        module="employment_offers",
        requires_confirmation=False,
        executor=_list_candidate_offers_executor,
        result_keys=("action_type", "success", "status", "message", "result", "application"),
        sensitive=False,
    )
)

register(
    ActionSpec(
        name="approve_employment_offer",
        description="Approve a pending employment offer. Sensitive: requires confirmation. Uses the canonical offer lifecycle (SOD / self-approval rules).",
        required_fields=("offer_id",),
        optional_fields=("app_key",),
        module="employment_offers",
        requires_confirmation=True,
        executor=_approve_employment_offer_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=True,
    )
)

register(
    ActionSpec(
        name="send_employment_offer",
        description="Send an approved employment offer to the candidate via WhatsApp or email when configured. Sensitive: requires confirmation. Uses company channel accounts.",
        required_fields=("offer_id",),
        optional_fields=("app_key", "preferred_channel", "channel"),
        module="employment_offers",
        requires_confirmation=True,
        executor=_send_employment_offer_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=True,
    )
)

# === P2 — Calendar module read =================================================


def _list_calendar_events_executor(ctx: ExecutionContext) -> dict[str, Any]:
    import assistant_p2_tools as p2

    legacy = ctx.legacy
    company = _resolve_company_code(legacy, ctx.request) or ""
    meta = getattr(ctx.request, "metadata", None) or {}
    admin = meta.get("admin_user") if isinstance(meta, dict) and isinstance(meta.get("admin_user"), dict) else {}
    actor_user_id = str(admin.get("user_id") or admin.get("id") or getattr(ctx.request, "sender_phone", "") or "")
    actor_role = str(admin.get("role") or getattr(ctx.request, "sender_role", "") or "hr_admin")
    result = p2.list_calendar_events(
        legacy,
        company_code=company,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        permissions=_assistant_actor_permissions(ctx),
        scope=str(ctx.action.get("scope") or "mine"),
        days=int(ctx.action.get("days") or 14),
    )
    count = int(result.get("count") or 0)
    return {
        "action_type": "list_calendar_events",
        "success": bool(result.get("ok")),
        "status": "completed",
        "message": f"Found {count} calendar event(s)." if count else "No calendar events in this window.",
        "safe_user_message": f"Found {count} calendar event(s)." if count else "No calendar events in this window.",
        "result": legacy.json_safe(result),
    }


register(
    ActionSpec(
        name="list_calendar_events",
        description="List upcoming company calendar events for the actor (mine/team/company scope). Read-only. Requires calendar module. Does not create or cancel events.",
        required_fields=(),
        optional_fields=("scope", "days", "query"),
        module="calendar",
        requires_confirmation=False,
        executor=_list_calendar_events_executor,
        result_keys=("action_type", "success", "status", "message", "result"),
        sensitive=False,
    )
)
