#!/usr/bin/env python3
"""Live Candidate Knowledge tool registration (thin action_registry adapters).

Gated by:
  WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=on|off
  WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS (must include company)
  WATHEFNI_CK_LIVE_TOOL_ACTORS (comma user ids; empty => nobody)

Does not enable Ranking reader. Does not mutate lifecycle/communication/identity.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from candidate_knowledge_authority import CandidateKnowledgeAuthority
from candidate_knowledge_embeddings import build_embedding_provider
from candidate_knowledge_errors import CandidateKnowledgeError
from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
from candidate_knowledge_search import CandidateKnowledgeSearchService
from candidate_knowledge_store import PostgresCandidateKnowledgeStore
from candidate_knowledge_tools import (
    ShadowToolRuntime,
    compare_candidates as ck_compare_candidates,
    get_candidate_knowledge as ck_get_candidate_knowledge,
    search_candidates as ck_search_candidates,
)


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def live_tools_enabled() -> bool:
    return _env_flag("WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS") and _env_flag("WATHEFNI_CANDIDATE_KNOWLEDGE")


def ranking_reader_enabled() -> bool:
    return _env_flag("WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER") and _env_flag("WATHEFNI_CANDIDATE_KNOWLEDGE")


def tenant_allowed(company_code: str) -> bool:
    raw = str(os.environ.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS") or "").strip()
    if not raw:
        return False
    allowed = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return str(company_code or "").strip().upper() in allowed


def live_tool_actors() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_CK_LIVE_TOOL_ACTORS") or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def actor_allowed(actor_user_id: str) -> bool:
    allowed = live_tool_actors()
    if not allowed:
        return False
    return str(actor_user_id or "").strip() in allowed


def _deny(action_type: str, error: str, message: str) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "success": False,
        "status": "failed",
        "error": error,
        "message": message,
        "safe_user_message": message,
    }


def _connect_factory():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = str(os.environ.get("WATHEFNI_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("WATHEFNI_DATABASE_URL missing")

    class Ctx:
        def __enter__(self):
            self.conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
            self.conn.autocommit = True
            self.cur = self.conn.cursor()
            return self.cur

        def __exit__(self, *a):
            self.cur.close()
            self.conn.close()

    return Ctx


def _runtime():
    Ctx = _connect_factory()
    store = PostgresCandidateKnowledgeStore(connect=Ctx)
    index = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    auth = CandidateKnowledgeAuthority(store, module_enabled=lambda company, module: True)
    use_voyage = _env_flag("WATHEFNI_CK_VOYAGE_ENABLED")
    use_semantic = _env_flag("WATHEFNI_CK_SEMANTIC_SEARCH")
    embedder = build_embedding_provider(force_mock=not use_voyage)
    search = CandidateKnowledgeSearchService(
        index,
        embedder=embedder,
        force_lexical_only=not use_semantic,
    )
    # Live path reuses the same tool functions; enable runtime without shadow env flag.
    return ShadowToolRuntime(authority=auth, search=search, audit_store=index, enabled=True), index


def _actor_and_company(ctx: Any, resolve_company: Callable[[Any, Any], str | None]) -> tuple[str, str, list[str]]:
    action = getattr(ctx, "action", {}) or {}
    meta = {}
    req = getattr(ctx, "request", None)
    if req is not None and isinstance(getattr(req, "metadata", None), dict):
        meta = dict(req.metadata or {})
    memory = meta.get("memory_scope") if isinstance(meta.get("memory_scope"), dict) else {}
    company = resolve_company(getattr(ctx, "legacy", None), req) or str(
        action.get("company_code") or meta.get("company_code") or memory.get("company_id") or ""
    )
    actor = str(
        action.get("actor_user_id")
        or action.get("admin_user_id")
        or meta.get("actor_user_id")
        or meta.get("admin_user_id")
        or memory.get("admin_user_id")
        or (meta.get("admin_user") or {}).get("user_id")
        or ""
    ).strip()
    perms = action.get("permissions") or meta.get("permissions") or memory.get("permissions") or ["prehire.read"]
    if isinstance(perms, dict):
        perms = list(perms.keys())
    perms = [str(p) for p in perms if str(p).strip()]
    if "prehire.read" not in perms:
        perms.append("prehire.read")
    return actor, str(company or "").strip().upper(), perms


def _gate(ctx: Any, action_type: str, resolve_company: Callable[[Any, Any], str | None]) -> tuple[dict[str, Any] | None, str, str, list[str]]:
    if not live_tools_enabled():
        return _deny(action_type, "ck_tools_disabled", "Candidate Knowledge tools are disabled."), "", "", []
    actor, company, perms = _actor_and_company(ctx, resolve_company)
    if not company or not tenant_allowed(company):
        return _deny(action_type, "ck_tenant_denied", "Candidate Knowledge is not enabled for this tenant."), actor, company, perms
    if not actor_allowed(actor):
        return _deny(action_type, "ck_actor_denied", "Candidate Knowledge tools are not enabled for this user."), actor, company, perms
    return None, actor, company, perms


def make_search_executor(resolve_company: Callable[[Any, Any], str | None]):
    def _exec(ctx: Any) -> dict[str, Any]:
        started = time.perf_counter()
        denied, actor, company, perms = _gate(ctx, "search_candidates", resolve_company)
        if denied:
            return denied
        action = getattr(ctx, "action", {}) or {}
        query = str(action.get("query") or action.get("prompt_text") or "").strip()
        scope = str(action.get("scope") or "all_authorized").strip() or "all_authorized"
        limit = int(action.get("limit") or 20)
        try:
            runtime, _index = _runtime()
            result = ck_search_candidates(
                runtime,
                company_code=company,
                actor_user_id=actor,
                permission_authority="backend_current",
                permission_subject_user_id=actor,
                permission_subject_company=company,
                permissions=perms,
                modules_enabled=["pre_hiring", "assessments"],
                query=query,
                scope=scope,
                limit=min(max(limit, 1), 50),
                filters=action.get("filters") if isinstance(action.get("filters"), dict) else None,
            )
        except CandidateKnowledgeError as exc:
            return _deny("search_candidates", exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _deny("search_candidates", "ck_search_failed", f"Candidate Knowledge search failed: {exc}")
        return {
            "action_type": "search_candidates",
            "success": True,
            "status": "completed",
            "message": f"Found {result.get('total', 0)} candidate(s).",
            "retrieval_mode": result.get("retrieval_mode"),
            "total": result.get("total"),
            "candidates": result.get("candidates") or result.get("results") or [],
            "coverage": result.get("coverage"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "mode": "live_allowlisted",
        }

    return _exec


def make_get_executor(resolve_company: Callable[[Any, Any], str | None]):
    def _exec(ctx: Any) -> dict[str, Any]:
        started = time.perf_counter()
        denied, actor, company, perms = _gate(ctx, "get_candidate_knowledge", resolve_company)
        if denied:
            return denied
        action = getattr(ctx, "action", {}) or {}
        app_key = str(action.get("app_key") or "").strip()
        candidate_ref = str(action.get("candidate_ref") or "").strip()
        if not candidate_ref and app_key:
            candidate_ref = f"app:{app_key}"
        if not candidate_ref:
            return _deny("get_candidate_knowledge", "candidate_ref_required", "Exact app: candidate_ref or app_key is required.")
        try:
            runtime, _index = _runtime()
            result = ck_get_candidate_knowledge(
                runtime,
                company_code=company,
                actor_user_id=actor,
                permission_authority="backend_current",
                permission_subject_user_id=actor,
                permission_subject_company=company,
                permissions=perms,
                modules_enabled=["pre_hiring", "assessments"],
                candidate_ref=candidate_ref,
                focus_question=str(action.get("focus_question") or action.get("question") or "") or None,
                sections=action.get("sections") if isinstance(action.get("sections"), (list, tuple)) else None,
            )
        except CandidateKnowledgeError as exc:
            return _deny("get_candidate_knowledge", exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _deny("get_candidate_knowledge", "ck_get_failed", f"Candidate Knowledge read failed: {exc}")
        return {
            "action_type": "get_candidate_knowledge",
            "success": True,
            "status": "completed",
            "message": "Candidate knowledge assembled.",
            "candidate_ref": result.get("candidate_ref"),
            "canonical_cv": result.get("canonical_cv"),
            "effective_facts": result.get("effective_facts"),
            "classifications": result.get("classifications"),
            "coverage": result.get("coverage"),
            "relevant_cv_chunks": result.get("relevant_cv_chunks"),
            "omission_reasons": result.get("omission_reasons"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "mode": "live_allowlisted",
        }

    return _exec


def make_compare_executor(resolve_company: Callable[[Any, Any], str | None]):
    def _exec(ctx: Any) -> dict[str, Any]:
        started = time.perf_counter()
        denied, actor, company, perms = _gate(ctx, "compare_candidates", resolve_company)
        if denied:
            return denied
        action = getattr(ctx, "action", {}) or {}
        refs = action.get("candidate_refs") or action.get("app_keys") or []
        if isinstance(refs, str):
            refs = [part.strip() for part in refs.split(",") if part.strip()]
        normalized = []
        for item in refs:
            text = str(item or "").strip()
            if not text:
                continue
            if text.startswith("app:"):
                normalized.append(text)
            else:
                normalized.append(f"app:{text}")
        try:
            runtime, _index = _runtime()
            result = ck_compare_candidates(
                runtime,
                company_code=company,
                actor_user_id=actor,
                permission_authority="backend_current",
                permission_subject_user_id=actor,
                permission_subject_company=company,
                permissions=perms,
                modules_enabled=["pre_hiring", "assessments"],
                candidate_refs=normalized,
                question=str(action.get("question") or "") or None,
                job_context=action.get("job_context") if isinstance(action.get("job_context"), dict) else None,
            )
        except CandidateKnowledgeError as exc:
            return _deny("compare_candidates", exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _deny("compare_candidates", "ck_compare_failed", f"Candidate Knowledge compare failed: {exc}")
        return {
            "action_type": "compare_candidates",
            "success": True,
            "status": "completed",
            "message": "Candidate comparison completed.",
            "candidates": result.get("candidates"),
            "recommendation": result.get("recommendation"),
            "dimensions": result.get("dimensions"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "mode": "live_allowlisted",
        }

    return _exec


def apply_ranking_reader_overlay(
    *,
    company_code: str,
    application: dict[str, Any],
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    """Live Ranking reader overlay: deny held/restricted via CK authority.

    Returns overlay metadata. Callers must force non-eligible buckets when
    eligible is False for *governance* denials. Infrastructure failures must
    not silently void an otherwise usable advisory score — they degrade to
    inactive overlay and leave soft scoring intact.
    """

    if not ranking_reader_enabled() or not tenant_allowed(company_code):
        return {"active": False}
    app_key = str(application.get("app_key") or "").strip()
    if not app_key:
        return {"active": True, "eligible": False, "denial_reason": "missing_app_key"}
    try:
        from candidate_knowledge_authority import build_request_context
        from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext

        runtime, _index = _runtime()
        auth = runtime.authority
        ctx = build_request_context(
            company_code=company_code,
            actor_user_id="ck-ranking-reader",
            permission_authority="backend_current",
            permission_subject_user_id="ck-ranking-reader",
            permission_subject_company=company_code,
            permissions=["prehire.read"],
            modules_enabled=["pre_hiring", "assessments"],
        )
        record = auth.assemble_phase3(
            ctx,
            f"app:{app_key}",
            sections=("canonical_cv", "effective_facts", "classifications", "assessments"),
        )
        adapter = RankingEvidenceAdapter()
        bundle = adapter.adapt(
            record,
            job_context=RankingJobContext(
                company_code=company_code,
                position_code=str(application.get("position_code") or "POS"),
                criteria_version=1,
            ),
            application=application,
        )
        versions = {
            "canonical_cv_version_id": (record.canonical_cv or {}).get("version_id"),
            "facts_id": (record.effective_facts or {}).get("facts_id"),
            "knowledge_version": getattr(record, "knowledge_version", None),
        }
        return {
            "active": True,
            "eligible": bool(bundle.eligible),
            "denial_reason": bundle.denial_reason,
            "evidence_versions": versions,
            "prior_eligibility_bucket": eligibility.get("eligibility_bucket"),
        }
    except CandidateKnowledgeError as exc:
        # Governance / authority denials stay fail-closed.
        return {
            "active": True,
            "eligible": False,
            "denial_reason": f"ck_error:{exc.code}",
            "evidence_versions": {},
            "prior_eligibility_bucket": eligibility.get("eligibility_bucket"),
        }
    except Exception as exc:  # noqa: BLE001
        # Infrastructure failures (e.g. SQL UndefinedFunction) must not void
        # soft scores. Degrade overlay to inactive and keep soft scoring.
        try:
            import logging

            logging.getLogger("wathefni.ranking").exception(
                "ck_ranking_reader_infra_failed company=%s app_key=%s error=%s",
                company_code,
                app_key,
                f"{type(exc).__name__}:{exc}",
            )
        except Exception:
            pass
        return {
            "active": False,
            "eligible": True,
            "infra_error": True,
            "denial_reason": None,
            "platform_error": f"ck_ranking_reader_failed:{type(exc).__name__}",
            "evidence_versions": {},
            "prior_eligibility_bucket": eligibility.get("eligibility_bucket"),
        }


def register_live_tools(*, registry_module: Any, resolve_company: Callable[[Any, Any], str | None]) -> list[str]:
    """Idempotently register CK live tools into action_registry.REGISTRY."""

    ActionSpec = registry_module.ActionSpec
    register = registry_module.register
    REGISTRY = registry_module.REGISTRY
    registered: list[str] = []

    specs = [
        (
            "search_candidates",
            "Search governed Candidate Knowledge for authorized candidates (lexical/hybrid). Exact tenant scope. Does not mutate lifecycle.",
            (),
            ("query", "scope", "limit", "filters"),
            ("action_type", "success", "status", "message", "candidates", "total", "retrieval_mode"),
            make_search_executor(resolve_company),
        ),
        (
            "get_candidate_knowledge",
            "Exact Candidate Knowledge read for one app: candidate_ref. Returns grounded sections with CV text omitted (chunks only).",
            (),
            ("candidate_ref", "app_key", "focus_question", "question", "sections"),
            ("action_type", "success", "status", "message", "candidate_ref", "canonical_cv", "coverage"),
            make_get_executor(resolve_company),
        ),
        (
            "compare_candidates",
            "Compare 2–5 exact Candidate Knowledge refs on grounded evidence. Does not auto-pick a winner without job context.",
            (),
            ("candidate_refs", "app_keys", "question", "job_context"),
            ("action_type", "success", "status", "message", "candidates", "recommendation"),
            make_compare_executor(resolve_company),
        ),
    ]
    for name, description, required, optional, result_keys, executor in specs:
        if name in REGISTRY:
            existing = REGISTRY[name]
            if getattr(existing, "notes", "").startswith("candidate-knowledge-live"):
                registered.append(name)
                continue
            # Prefer CK live tool over any legacy collision (compare_candidates).
            if name == "compare_candidates":
                REGISTRY.pop(name, None)
            else:
                continue
        register(
            ActionSpec(
                name=name,
                description=description,
                entity_type="candidate" if name != "search_candidates" else None,
                required_fields=required,
                optional_fields=optional,
                module="pre_hiring",
                requires_confirmation=False,
                executor=executor,
                result_keys=result_keys,
                sensitive=False,
                notes="candidate-knowledge-live-v1 allowlisted actors only",
            )
        )
        registered.append(name)
    return registered


__all__ = [
    "live_tools_enabled",
    "ranking_reader_enabled",
    "tenant_allowed",
    "live_tool_actors",
    "actor_allowed",
    "apply_ranking_reader_overlay",
    "register_live_tools",
]
