#!/usr/bin/env python3
"""PT7 — read/explain Assistant tools over deterministic PT services.

No mutation tools. AI explanation is grounded in the same WHY graph the UI uses.
"""
from __future__ import annotations

from typing import Any

import talent_models_pt2 as pt2
import talent_profile_c5 as c5
import talent_role_fit_pt3 as pt3
import talent_succession_c6 as c6
import talent_succession_intel_pt5 as pt5
import talent_trajectory_pt6 as pt6

PHASE = "talent_assistant_pt7"
CONTRACT_VERSION = "talent_assistant_pt7_v1"
PASS_STAMP = "PT7_ASSISTANT_TALENT_INTELLIGENCE_FULL_PASS"

READ_TOOLS = (
    "list_role_fit_candidates",
    "list_uncovered_critical_roles",
    "list_model_classifications",
    "explain_talent_classification",
    "list_capability_gaps",
    "list_succession_replacements",
    "get_okr_alignment",
)
FORBIDDEN_MUTATIONS = (
    "designate_hipo",
    "set_potential",
    "set_readiness",
    "create_successor",
    "promote",
    "create_mobility_application",
)


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "calls_deterministic_services": True,
        "no_prompt_recreated_talent_math": True,
        "no_mutation_tools": True,
        "same_why_as_ui": True,
        "insufficient_evidence_is_said": True,
        "company_code": c5.company_code_norm(company_code) if company_code else None,
    }


def _company(ctx: Any) -> str:
    action = getattr(ctx, "action", None) or {}
    if isinstance(action, dict) and action.get("company_code"):
        return c5.company_code_norm(action.get("company_code"))
    legacy = getattr(ctx, "legacy", None)
    request = getattr(ctx, "request", None)
    if legacy and hasattr(legacy, "request_company_code") and request is not None:
        try:
            return c5.company_code_norm(legacy.request_company_code(request))
        except Exception:
            pass
    return c5.company_code_norm(getattr(request, "company_code", None) if request is not None else None)


def _db(ctx: Any):
    legacy = getattr(ctx, "legacy", None)
    if legacy and hasattr(legacy, "db_connect"):
        return legacy.db_connect()
    import app

    return app.db_connect()


def _action(ctx: Any) -> dict[str, Any]:
    raw = getattr(ctx, "action", None)
    if isinstance(raw, dict):
        return raw
    return {}


def _gate(cur: Any, company: str) -> dict[str, Any] | None:
    gate = c5.runtime_gate_for_company(company)
    if not gate.get("ok"):
        return {"ok": False, "error": gate.get("error") or "talent_unavailable", "insufficient_evidence": True, **honesty_payload(company_code=company)}
    return None


def _reply(result: dict[str, Any], *, action_type: str, text: str) -> dict[str, Any]:
    out = {
        "ok": bool(result.get("ok", True)),
        "action_type": action_type,
        "success": bool(result.get("ok", True)),
        "status": "ok" if result.get("ok", True) else "error",
        "message": text,
        "safe_user_message": text,
        "why": result.get("why"),
        **honesty_payload(company_code=result.get("company_code")),
    }
    out.update({k: v for k, v in result.items() if k not in out})
    return out


def list_role_fit_candidates_tool(ctx: Any) -> dict[str, Any]:
    action = _action(ctx)
    company = _company(ctx)
    set_id = str(action.get("set_id") or action.get("requirement_set_id") or "")
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="list_role_fit_candidates", text="Talent is not available.")
            if not set_id:
                sets = pt3.list_sets(cur, company_code=company)
                published = next((s for s in (sets.get("sets") or []) if s.get("status") == "published"), None)
                set_id = str((published or {}).get("set_id") or "")
            if not set_id:
                return _reply({"ok": True, "candidates": [], "insufficient_evidence": True}, action_type="list_role_fit_candidates", text="No published role-fit requirement set is available.")
            result = pt3.list_role_fit_candidates(cur, company_code=company, set_id=set_id)
    text = f"{len(result.get('candidates') or [])} candidates with explainable fit — not an opaque rank."
    return _reply(result, action_type="list_role_fit_candidates", text=text)


def list_uncovered_critical_roles_tool(ctx: Any) -> dict[str, Any]:
    company = _company(ctx)
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="list_uncovered_critical_roles", text="Talent is not available.")
            intel = pt5.succession_intelligence(cur, company_code=company)
            c6_uncovered = c6.list_uncovered_critical_roles(cur, company_code=company)
    roles = intel.get("uncovered_critical_roles") or []
    zero_ready = intel.get("zero_ready_now") or []
    text = f"{len(roles)} critical roles have no successor. {len(zero_ready)} have successors but none ready now."
    return _reply({**intel, "c6_uncovered": c6_uncovered}, action_type="list_uncovered_critical_roles", text=text)


def list_model_classifications_tool(ctx: Any) -> dict[str, Any]:
    action = _action(ctx)
    company = _company(ctx)
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="list_model_classifications", text="Talent is not available.")
            result = pt2.list_classifications(
                cur,
                company_code=company,
                model_id=action.get("model_id"),
                classification=action.get("classification") or "derived_high_potential",
            )
    text = f"{len(result.get('classifications') or [])} people meet the configured derived signal. This is not designated HiPo."
    return _reply(result, action_type="list_model_classifications", text=text)


def explain_talent_classification_tool(ctx: Any) -> dict[str, Any]:
    action = _action(ctx)
    company = _company(ctx)
    employee_key = str(action.get("employee_key") or action.get("employee_name") or "")
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="explain_talent_classification", text="Talent is not available.")
            if not employee_key:
                return _reply({"ok": False, "insufficient_evidence": True}, action_type="explain_talent_classification", text="I need the employee before I can explain the classification.")
            why = pt2.get_why(cur, company_code=company, employee_key=employee_key)
            listed = pt2.list_classifications(cur, company_code=company)
            mine = next((c for c in (listed.get("classifications") or []) if str(c.get("employee_key")) == employee_key), None)
            hipo = c6.get_hipo_for_viewer(cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True)
    graph = (why.get("why") or {}).get("graph") if why.get("ok") else None
    designated = False
    for d in (hipo.get("designations") or []):
        if not d.get("superseded_by_designation_id") and d.get("status") in {"designated", "nominated"}:
            designated = True
    if not graph:
        text = "There is insufficient evidence to explain this classification."
        return _reply({"ok": True, "insufficient_evidence": True, "designated_hipo": designated}, action_type="explain_talent_classification", text=text)
    derived = (mine or {}).get("classification")
    text = (
        f"Derived classification is {derived or 'none'} under model {graph.get('model_id')} v{graph.get('version')}. "
        f"Designated HiPo is {'yes' if designated else 'no'}. "
        f"Missing evidence: {len(graph.get('missing_evidence') or [])}."
    )
    return _reply(
        {"ok": True, "why": graph, "classification": mine, "designated_hipo": designated, "same_why_as_ui": True},
        action_type="explain_talent_classification",
        text=text,
    )


def list_capability_gaps_tool(ctx: Any) -> dict[str, Any]:
    company = _company(ctx)
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="list_capability_gaps", text="Talent is not available.")
            facts = pt6.capability_facts(cur, company_code=company)
    singles = facts.get("single_person_capability") or {}
    text = f"{len(singles)} capabilities have a single verified holder." if singles else "Capability coverage facts are available; no single-holder gaps were found."
    return _reply(facts, action_type="list_capability_gaps", text=text)


def list_succession_replacements_tool(ctx: Any) -> dict[str, Any]:
    action = _action(ctx)
    company = _company(ctx)
    employee_key = str(action.get("employee_key") or "")
    role_id = str(action.get("critical_role_id") or "")
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            denied = _gate(cur, company)
            if denied:
                return _reply(denied, action_type="list_succession_replacements", text="Talent is not available.")
            intel = pt5.succession_intelligence(cur, company_code=company)
            if role_id:
                compared = pt5.compare_successors(cur, company_code=company, critical_role_id=role_id)
            else:
                compared = {"comparisons": []}
            mobility = None
            if employee_key:
                mobility = pt5.discover_mobility(cur, company_code=company, actor_phone="assistant", employee_key=employee_key, reason="assistant mobility read")
    text = "Successor slates are listed with WHY graphs. No invented candidates."
    return _reply({**intel, "comparisons": compared.get("comparisons"), "mobility": mobility}, action_type="list_succession_replacements", text=text)


def get_okr_alignment_tool(ctx: Any) -> dict[str, Any]:
    action = _action(ctx)
    company = _company(ctx)
    employee_key = str(action.get("employee_key") or "")
    try:
        import okr_operating_pt1 as pt1
    except Exception:
        return _reply({"ok": False, "insufficient_evidence": True}, action_type="get_okr_alignment", text="OKR alignment is not available.")
    with _db(ctx) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM perf_okr_cycles
                 WHERE company_code=%s AND status IN ('active','closed')
                 ORDER BY period_end DESC LIMIT 1
                """,
                (c5.company_code_norm(company),),
            )
            cycle = cur.fetchone()
            if not cycle:
                return _reply({"ok": True, "insufficient_evidence": True}, action_type="get_okr_alignment", text="There is no active or closed OKR cycle to explain alignment.")
            cycle = dict(cycle)
            tree = None
            if hasattr(pt1, "alignment_tree"):
                tree = pt1.alignment_tree(cur, company_code=company, cycle_id=str(cycle.get("cycle_id")))
            elif hasattr(pt1, "get_alignment_tree"):
                tree = pt1.get_alignment_tree(cur, company_code=company, cycle_id=str(cycle.get("cycle_id")))
    text = f"OKR cycle {cycle.get('name_en') or cycle.get('cycle_id')} alignment is shown without score inheritance."
    return _reply({"ok": True, "cycle": cycle, "alignment": tree, "employee_key": employee_key, "score_inherited": False}, action_type="get_okr_alignment", text=text)


EXECUTORS = {
    "list_role_fit_candidates": list_role_fit_candidates_tool,
    "list_uncovered_critical_roles": list_uncovered_critical_roles_tool,
    "list_model_classifications": list_model_classifications_tool,
    "explain_talent_classification": explain_talent_classification_tool,
    "list_capability_gaps": list_capability_gaps_tool,
    "list_succession_replacements": list_succession_replacements_tool,
    "get_okr_alignment": get_okr_alignment_tool,
}


def register_assistant_tools() -> None:
    import action_registry as registry

    for name, executor in EXECUTORS.items():
        if name in registry.REGISTRY:
            continue
        registry.register(
            registry.ActionSpec(
                name=name,
                description=f"Read-only Talent intelligence tool. Calls deterministic PT services. Never mutates HiPo, potential, readiness, succession, or employment.",
                required_fields=(),
                optional_fields=("employee_key", "employee_name", "set_id", "model_id", "classification", "critical_role_id"),
                module="talent",
                requires_confirmation=False,
                executor=executor,
                result_keys=("action_type", "success", "status", "message", "safe_user_message", "why"),
                sensitive=True,
                notes="PT7 read/explain tool. Same WHY graph as Talent UI.",
            )
        )
