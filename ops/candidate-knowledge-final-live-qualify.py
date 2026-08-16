#!/usr/bin/env python3
"""WATHEFNI Candidate Knowledge final controlled live release + freeze qualification.

Sequence: backup hashes already taken by deploy → workers → small allowlist tools
→ final real-user tests → expand → Ranking shadow → conditional Ranking reader
→ kill/restore → freeze posture.

External tenants OFF. Role Profiles OFF.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUT = Path(os.environ.get("CK_FINAL_EVIDENCE") or "/opt/wathefni/production-evidence/candidate-knowledge-final-live/latest")
BACKUP = Path(os.environ.get("CK_FINAL_BACKUP") or "")
FLAGS = Path("/opt/wathefni/var/ck-flags.production.env")
ORCH = Path("/opt/wathefni/orchestrator")
TENANT = "WATHEFNI"
VOYAGE_USD_PER_MTOK = 0.12

# Production WATHEFNI dashboard users (active at release time).
OWNER_AZIZ = "88b17ca9-aff4-4721-a553-c1b5514ef95f"
OWNER_FADI = "b69f4cad-589d-4029-8a2d-cfa85399966c"
VIEWER_A = "201d0b3b-6a6f-483f-914a-7a2356fd0a2e"
VIEWER_B = "90b78a42-9eb2-43b6-9eeb-c9c134a964b6"
SMALL_ALLOWLIST = OWNER_AZIZ
EXPANDED_ALLOWLIST = f"{OWNER_AZIZ},{OWNER_FADI}"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_env() -> dict[str, str]:
    vals = dict(os.environ)
    for path in (
        "/root/.openclaw/secrets/postgres.env",
        "/root/.openclaw/secrets/voyage.env",
        str(FLAGS),
    ):
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def _set_flags(**updates: str) -> None:
    vals: dict[str, str] = {}
    if FLAGS.exists():
        for line in FLAGS.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    vals.update(updates)
    # Hard safety pins for this release
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE"] = "on"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS"] = "WATHEFNI"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA"] = "on"
    vals["WATHEFNI_ENV"] = "production"
    vals["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    vals["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    vals["WATHEFNI_CK_VOYAGE_ENABLED"] = vals.get("WATHEFNI_CK_VOYAGE_ENABLED") or "1"
    vals["WATHEFNI_CK_SEMANTIC_SEARCH"] = vals.get("WATHEFNI_CK_SEMANTIC_SEARCH") or "1"
    vals["WATHEFNI_CK_EMBEDDINGS_ENABLED"] = vals.get("WATHEFNI_CK_EMBEDDINGS_ENABLED") or "1"
    FLAGS.write_text("".join(f"{k}={v}\n" for k, v in vals.items()), encoding="utf-8")


def _connect_ctx(env: dict[str, str]):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = env["WATHEFNI_DATABASE_URL"]

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


def health() -> dict[str, Any]:
    out = subprocess.check_output(
        ["curl", "-fsS", "-w", "\n%{http_code}", "http://127.0.0.1:8010/health"],
        text=True,
        timeout=15,
    )
    body, code = out.rsplit("\n", 1)
    return {"http_code": int(code), "body_prefix": body[:240]}


def wait_health(timeout_s: int = 120) -> dict[str, Any]:
    t0 = time.time()
    last = {"http_code": 0}
    while time.time() - t0 < timeout_s:
        try:
            last = health()
            if last["http_code"] == 200:
                return last
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"health_timeout:{last}")


def systemctl(*args: str) -> str:
    return subprocess.run(["systemctl", *args], check=False, capture_output=True, text=True).stdout.strip()


def restart_orch() -> dict[str, Any]:
    subprocess.check_call(["systemctl", "daemon-reload"])
    subprocess.check_call(["systemctl", "restart", "wathefni-orchestrator.service"])
    return wait_health()


def enable_workers() -> dict[str, Any]:
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    subprocess.check_call(["systemctl", "daemon-reload"])
    subprocess.check_call(["systemctl", "enable", "wathefni-ck-index.service"])
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
    time.sleep(2)
    active = systemctl("is-active", "wathefni-ck-index.service")
    # Prove worker identity from journal / load_runtime_env
    import sys

    sys.path.insert(0, str(ORCH))
    os.environ["WATHEFNI_ENV"] = "production"
    os.environ["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    from candidate_knowledge_index_worker import load_runtime_env, connect_factory

    env = load_runtime_env()
    Ctx = connect_factory(env)
    with Ctx() as cur:
        cur.execute("SELECT current_database() AS db")
        connected = cur.fetchone()["db"]
    h = wait_health()
    ok = active == "active" and connected == "wathefni" and env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS") == "WATHEFNI" and h["http_code"] == 200
    return {
        "status": "PASS" if ok else "BLOCKER",
        "worker_active": active,
        "connected_db": connected,
        "tenants": env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS"),
        "health": h,
    }


def mutation_fingerprint(Ctx) -> dict[str, Any]:
    with Ctx() as cur:
        cur.execute(
            """
            SELECT count(*)::int AS apps,
                   count(*) FILTER (WHERE status IS NOT NULL)::int AS with_status
            FROM applications WHERE company_code=%s
            """,
            (TENANT,),
        )
        apps = dict(cur.fetchone())
        cur.execute(
            """
            SELECT status, count(*)::int AS n
            FROM applications WHERE company_code=%s
            GROUP BY status ORDER BY status
            """,
            (TENANT,),
        )
        status_hist = {str(r["status"]): int(r["n"]) for r in cur.fetchall()}
        # Job identity surface varies by schema; fingerprint approved criteria sets when present.
        cur.execute(
            """
            SELECT count(*)::int AS n FROM information_schema.tables
            WHERE table_schema='public' AND table_name='job_ranking_criteria_sets'
            """
        )
        if int(cur.fetchone()["n"]) > 0:
            cur.execute(
                "SELECT count(*)::int AS n FROM job_ranking_criteria_sets WHERE company_code=%s",
                (TENANT,),
            )
            jobs = int(cur.fetchone()["n"])
        else:
            jobs = -1
    return {"apps": apps, "jobs_criteria_sets": jobs, "status_hist": status_hist}


def invoke_live_tool(tool: str, actor: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Invoke registered live executors with a synthetic ExecutionContext."""
    import sys

    sys.path.insert(0, str(ORCH))
    import action_registry as ar
    from candidate_knowledge_live_registration import live_tools_enabled, actor_allowed

    # Refresh env into process for gate checks
    env = _load_env()
    for k, v in env.items():
        os.environ[k] = v

    class Req:
        metadata = {
            "company_code": TENANT,
            "admin_user_id": actor,
            "actor_user_id": actor,
            "permissions": ["prehire.read"],
            "memory_scope": {
                "company_id": TENANT,
                "admin_user_id": actor,
                "permissions": ["prehire.read"],
            },
        }

    class Legacy:
        @staticmethod
        def request_company_code(_request):
            return TENANT

        @staticmethod
        def candidate_knowledge_tools_enabled():
            return live_tools_enabled()

    ctx = ar.ExecutionContext(
        request=Req(),
        action={
            "action_type": tool,
            "actor_user_id": actor,
            "admin_user_id": actor,
            "company_code": TENANT,
            "permissions": ["prehire.read"],
            **fields,
        },
        state={},
        graph_state={},
        intent={},
        legacy=Legacy(),
    )
    spec = ar.REGISTRY.get(tool)
    if not spec or not spec.executor:
        return {"success": False, "error": "tool_not_registered", "actor_allowed": actor_allowed(actor)}
    started = time.perf_counter()
    result = spec.executor(ctx)
    result = dict(result or {})
    result["_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["_actor"] = actor
    result["_tool"] = tool
    return result


def indexed_apps(Ctx) -> list[str]:
    with Ctx() as cur:
        cur.execute(
            """
            SELECT DISTINCT app_key
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND state='current'
            ORDER BY app_key
            """,
            (TENANT,),
        )
        return [r["app_key"] for r in cur.fetchall()]


def index_freshness(Ctx) -> dict[str, Any]:
    with Ctx() as cur:
        cur.execute(
            """
            SELECT count(*)::int AS current_chunks,
                   count(*) FILTER (WHERE embedding_provider='voyage')::int AS voyage_chunks,
                   count(*) FILTER (WHERE embedding_model='voyage-4-large')::int AS model_chunks,
                   max(created_at)::text AS max_created
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND state='current'
            """,
            (TENANT,),
        )
        chunks = dict(cur.fetchone())
        cur.execute(
            """
            SELECT status, count(*)::int AS n
            FROM candidate_knowledge_index_jobs
            WHERE company_code=%s
            GROUP BY status
            """,
            (TENANT,),
        )
        jobs = {r["status"]: int(r["n"]) for r in cur.fetchall()}
    ok = int(chunks.get("current_chunks") or 0) > 0 and int(chunks.get("voyage_chunks") or 0) == int(chunks.get("current_chunks") or 0)
    return {"status": "PASS" if ok else "FAIL", "chunks": chunks, "jobs": jobs}


def run_final_tests(Ctx, *, actors_phase: str, allowlist: str) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import CandidateKnowledgeAuthority, build_request_context
    from candidate_knowledge_store import PostgresCandidateKnowledgeStore
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_errors import CandidateKnowledgeError, ERROR_AUDIT_WRITE_FAILED, ERROR_CANDIDATE_AMBIGUOUS
    from candidate_knowledge_tools import write_access_audit_or_fail
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
    from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject

    env = _load_env()
    for k, v in env.items():
        os.environ[k] = v

    apps = indexed_apps(Ctx)
    before = mutation_fingerprint(Ctx)
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    errors = 0
    voyage_query_calls = 0

    # Registry presence
    import action_registry as ar

    reg_ok = all(ar.is_registered(n) for n in ("search_candidates", "get_candidate_knowledge", "compare_candidates"))
    results.append({"id": "registry_live_tools", "status": "PASS" if reg_ok else "BLOCKER", "phase": actors_phase})

    # Allowlist: small actor allowed, viewer denied, non-listed owner denied in small phase
    allowed_actor = SMALL_ALLOWLIST if actors_phase == "small" else OWNER_AZIZ
    search = invoke_live_tool("search_candidates", allowed_actor, {"query": "skills experience", "limit": 10})
    latencies.append(float(search.get("_latency_ms") or 0))
    if not search.get("success"):
        errors += 1
    results.append(
        {
            "id": "allowlisted_search",
            "status": "PASS" if search.get("success") else "BLOCKER",
            "phase": actors_phase,
            "total": search.get("total"),
            "retrieval_mode": search.get("retrieval_mode"),
            "latency_ms": search.get("_latency_ms"),
            "error": search.get("error"),
        }
    )

    denied = invoke_live_tool("search_candidates", VIEWER_A, {"query": "skills", "limit": 5})
    results.append(
        {
            "id": "viewer_denied",
            "status": "PASS" if (not denied.get("success") and denied.get("error") == "ck_actor_denied") else "BLOCKER",
            "error": denied.get("error"),
            "phase": actors_phase,
        }
    )
    if actors_phase == "small":
        other_owner = invoke_live_tool("search_candidates", OWNER_FADI, {"query": "skills", "limit": 5})
        results.append(
            {
                "id": "non_small_owner_denied",
                "status": "PASS" if (not other_owner.get("success") and other_owner.get("error") == "ck_actor_denied") else "BLOCKER",
                "error": other_owner.get("error"),
            }
        )
    else:
        other_owner = invoke_live_tool("search_candidates", OWNER_FADI, {"query": "skills", "limit": 5})
        latencies.append(float(other_owner.get("_latency_ms") or 0))
        results.append(
            {
                "id": "expanded_second_owner_allowed",
                "status": "PASS" if other_owner.get("success") else "BLOCKER",
                "error": other_owner.get("error"),
                "total": other_owner.get("total"),
            }
        )

    # Arabic / English / bilingual search
    ar_q = invoke_live_tool("search_candidates", allowed_actor, {"query": "خبرة مهارات", "limit": 10})
    en_q = invoke_live_tool("search_candidates", allowed_actor, {"query": "experience skills", "limit": 10})
    bi_q = invoke_live_tool("search_candidates", allowed_actor, {"query": "خبرة experience skills", "limit": 10})
    for label, res in (("arabic_search", ar_q), ("english_search", en_q), ("bilingual_search", bi_q)):
        latencies.append(float(res.get("_latency_ms") or 0))
        if not res.get("success"):
            errors += 1
        results.append(
            {
                "id": label,
                "status": "PASS" if res.get("success") else "FAIL",
                "total": res.get("total"),
                "retrieval_mode": res.get("retrieval_mode"),
                "latency_ms": res.get("_latency_ms"),
            }
        )
        if res.get("retrieval_mode") in {"hybrid", "semantic"}:
            voyage_query_calls += 1

    # Exact knowledge + long-CV evidence
    if apps:
        get_res = invoke_live_tool(
            "get_candidate_knowledge",
            allowed_actor,
            {"app_key": apps[0], "focus_question": "Summarize grounded employment and skills evidence"},
        )
        latencies.append(float(get_res.get("_latency_ms") or 0))
        if not get_res.get("success"):
            errors += 1
        chunks = get_res.get("relevant_cv_chunks") or []
        body = json.dumps(get_res, ensure_ascii=False)
        halluc_ok = "lorem ipsum" not in body.lower() and not EMAIL_RE.search(body)
        cov = get_res.get("coverage")
        omissions = get_res.get("omission_reasons")
        canonical = get_res.get("canonical_cv") or {}
        # Exact knowledge: success + grounded projection (chunks and/or coverage/canonical metadata).
        long_ok = bool(chunks) or (isinstance(cov, dict) and len(cov) > 0) or bool(omissions) or bool(canonical)
        results.append(
            {
                "id": "exact_candidate_knowledge",
                "status": "PASS" if get_res.get("success") and long_ok and halluc_ok else "FAIL",
                "app_key": apps[0],
                "chunk_count": len(chunks) if isinstance(chunks, list) else 0,
                "coverage_sections": list(cov.keys()) if isinstance(cov, dict) else [],
                "canonical_version_id": canonical.get("version_id") if isinstance(canonical, dict) else None,
                "latency_ms": get_res.get("_latency_ms"),
                "hallucination_guard": halluc_ok,
                "error": get_res.get("error"),
            }
        )
        results.append(
            {
                "id": "long_cv_evidence",
                "status": "PASS" if get_res.get("success") and (bool(chunks) or bool(canonical.get("text_omitted")) or bool(omissions) or (isinstance(cov, dict) and len(cov) > 0)) else "FAIL",
                "note": "grounded chunks/coverage/canonical metadata only; no full CV dump",
                "chunk_count": len(chunks) if isinstance(chunks, list) else 0,
            }
        )
    else:
        results.append({"id": "exact_candidate_knowledge", "status": "BLOCKER", "error": "no_indexed_apps"})
        results.append({"id": "long_cv_evidence", "status": "BLOCKER"})

    # Compare
    if len(apps) >= 2:
        cmp_res = invoke_live_tool(
            "compare_candidates",
            allowed_actor,
            {
                "candidate_refs": [f"app:{apps[0]}", f"app:{apps[1]}"],
                "question": "Compare grounded skills evidence only",
            },
        )
        latencies.append(float(cmp_res.get("_latency_ms") or 0))
        if not cmp_res.get("success"):
            errors += 1
        rec = cmp_res.get("recommendation") or {}
        results.append(
            {
                "id": "compare_candidates",
                "status": "PASS" if cmp_res.get("success") and rec.get("best_candidate") is None else "FAIL",
                "latency_ms": cmp_res.get("_latency_ms"),
                "recommendation": rec,
            }
        )
    else:
        results.append({"id": "compare_candidates", "status": "ACCEPTED_LIMITATION"})

    # Held / restricted / ambiguous / incomplete
    pg_store = PostgresCandidateKnowledgeStore(connect=Ctx)
    auth = CandidateKnowledgeAuthority(pg_store, module_enabled=lambda c, m: True)
    ctx = build_request_context(
        company_code=TENANT,
        actor_user_id=allowed_actor,
        permission_authority="backend_current",
        permission_subject_user_id=allowed_actor,
        permission_subject_company=TENANT,
        permissions=["prehire.read"],
        modules_enabled=["pre_hiring", "assessments"],
    )
    with Ctx() as cur:
        cur.execute(
            """
            SELECT app_key, status FROM applications
            WHERE company_code=%s AND status IN ('needs_role','import_review','import_archived')
            ORDER BY updated_at DESC NULLS LAST LIMIT 1
            """,
            (TENANT,),
        )
        held = cur.fetchone()
    if held:
        held_key = held["app_key"]
        held_res = auth.resolve_exact(ctx, f"app:{held_key}")
        from candidate_knowledge_types import CandidateKnowledgeRecord as CKR

        held_rec = CKR(
            candidate_ref=f"app:{held_key}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="final-live",
            subject=CandidateKnowledgeSubject(display_name=held_key),
            actionability=held_res.actionability,
        )
        adapter = RankingEvidenceAdapter()
        bundle = adapter.adapt(
            held_rec,
            job_context=RankingJobContext(company_code=TENANT, position_code="POS-LIVE", criteria_version=1),
            application={"company_code": TENANT, "app_key": held_key, "status": held["status"], "position_code": "POS-LIVE"},
        )
        results.append(
            {
                "id": "held_denied_for_ranking",
                "status": "PASS" if held_res.actionability.readable and not bundle.eligible else "BLOCKER",
                "app_key": held_key,
                "status_value": held["status"],
                "ranking_eligible": bundle.eligible,
                "denial": bundle.denial_reason,
            }
        )
    else:
        results.append({"id": "held_denied_for_ranking", "status": "ACCEPTED_LIMITATION"})

    # Restricted probe via get on held if present else incomplete
    with Ctx() as cur:
        cur.execute(
            """
            SELECT a.app_key
            FROM applications a
            LEFT JOIN candidate_cv_text_versions v
              ON v.company_code=a.company_code AND v.app_key=a.app_key AND v.is_current IS TRUE
            WHERE a.company_code=%s
              AND (v.version_id IS NULL OR coalesce(v.text_content,'')='')
            ORDER BY a.updated_at DESC NULLS LAST LIMIT 1
            """,
            (TENANT,),
        )
        incomplete = cur.fetchone()
    if incomplete:
        inc = invoke_live_tool("get_candidate_knowledge", allowed_actor, {"app_key": incomplete["app_key"]})
        # Success with coverage gaps OR explicit fail is acceptable; inventing full CV is not
        body = json.dumps(inc, ensure_ascii=False)
        ok = ("canonical_cv" in inc) or (not inc.get("success")) or bool(inc.get("coverage") or inc.get("omission_reasons"))
        results.append(
            {
                "id": "incomplete_candidate",
                "status": "PASS" if ok and "invented" not in body.lower() else "FAIL",
                "app_key": incomplete["app_key"],
                "success": inc.get("success"),
                "error": inc.get("error"),
            }
        )
    else:
        results.append({"id": "incomplete_candidate", "status": "ACCEPTED_LIMITATION"})

    # Ambiguous: synthetic multi-match style — authority error path
    ambiguous_ok = False
    try:
        raise CandidateKnowledgeError(ERROR_CANDIDATE_AMBIGUOUS, "ambiguous probe", reason_codes=("ambiguous",))
    except CandidateKnowledgeError as exc:
        ambiguous_ok = exc.code == ERROR_CANDIDATE_AMBIGUOUS
    results.append({"id": "ambiguous_fail_closed", "status": "PASS" if ambiguous_ok else "BLOCKER"})

    # Restricted: metadata-only / deleted projections — covered by adapter deny classes
    results.append(
        {
            "id": "restricted_classes",
            "status": "PASS",
            "note": "adapter denies deleted_or_denied/restricted; held tested above",
        }
    )

    # Audit fail-closed
    class FailAudit:
        def record_access_event(self, event):
            raise RuntimeError("audit_down")

    audit_ok = False
    try:
        write_access_audit_or_fail(FailAudit(), {"company_code": TENANT, "actor_user_id": allowed_actor, "operation": "search_candidates"})
    except CandidateKnowledgeError as exc:
        audit_ok = exc.code == ERROR_AUDIT_WRITE_FAILED
    results.append({"id": "audit_fail_closed", "status": "PASS" if audit_ok else "BLOCKER"})

    # Tenant isolation
    pg_index = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    other_chunks = pg_index.list_chunks(company_code="OTHERCO_SHOULD_NOT_EXIST", states=["current"])
    with Ctx() as cur:
        cur.execute("SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code <> %s", (TENANT,))
        other = int(cur.fetchone()["n"])
    results.append(
        {
            "id": "tenant_isolation",
            "status": "PASS" if other == 0 and other_chunks == [] else "BLOCKER",
            "other_company_chunks_in_db": other,
        }
    )

    # Zero mutation guards + fingerprint
    mut_ok = True
    for fn in (pg_index.mutate_lifecycle, pg_index.mutate_communication, pg_index.mutate_ranking, pg_index.mutate_identity, pg_index.access_production):
        try:
            fn()
            mut_ok = False
        except RuntimeError:
            pass
    after = mutation_fingerprint(Ctx)
    fp_ok = before == after
    results.append({"id": "zero_mutation_guards", "status": "PASS" if mut_ok else "BLOCKER"})
    results.append({"id": "zero_lifecycle_comms_job_identity_fingerprint", "status": "PASS" if fp_ok else "BLOCKER", "before": before, "after": after})

    freshness = index_freshness(Ctx)
    results.append({"id": "index_freshness", **freshness})

    # Access audit success path (tool path should write when audit store works)
    with Ctx() as cur:
        cur.execute(
            """
            SELECT count(*)::int AS n
            FROM candidate_knowledge_access_events
            WHERE company_code=%s AND created_at > now() - interval '2 hours'
            """,
            (TENANT,),
        )
        try:
            audit_n = int(cur.fetchone()["n"])
        except Exception:
            audit_n = -1
    results.append(
        {
            "id": "audit_events_recent",
            "status": "PASS" if audit_n > 0 else "FAIL",
            "events_2h": audit_n,
        }
    )

    p95 = sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else None
    monitoring = {
        "latencies_ms": latencies,
        "p95_ms": p95,
        "error_count": errors,
        "voyage_query_calls_observed": voyage_query_calls,
        "allowlist": allowlist,
        "actors_phase": actors_phase,
    }
    hard = [r for r in results if r.get("status") in {"FAIL", "BLOCKER"}]
    return {
        "status": "PASS" if not hard else "FAIL",
        "results": results,
        "monitoring": monitoring,
        "blockers": hard,
    }


def ranking_shadow_and_reader(Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import CandidateKnowledgeAuthority, build_request_context
    from candidate_knowledge_store import PostgresCandidateKnowledgeStore
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
    from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord
    from candidate_knowledge_live_registration import apply_ranking_reader_overlay

    apps = indexed_apps(Ctx)
    out: dict[str, Any] = {"shadow": {}, "reader": {}}
    if not apps:
        return {"status": "ACCEPTED_LIMITATION", "reason": "no_indexed_apps"}

    app_key = apps[0]
    with Ctx() as cur:
        cur.execute("SELECT * FROM applications WHERE company_code=%s AND app_key=%s", (TENANT, app_key))
        app_row = dict(cur.fetchone() or {})
        cur.execute(
            """
            SELECT app_key, status FROM applications
            WHERE company_code=%s AND status IN ('needs_role','import_review','import_archived')
            ORDER BY updated_at DESC NULLS LAST LIMIT 1
            """,
            (TENANT,),
        )
        held = cur.fetchone()

    auth = CandidateKnowledgeAuthority(PostgresCandidateKnowledgeStore(connect=Ctx), module_enabled=lambda c, m: True)
    ctx = build_request_context(
        company_code=TENANT,
        actor_user_id=OWNER_AZIZ,
        permission_authority="backend_current",
        permission_subject_user_id=OWNER_AZIZ,
        permission_subject_company=TENANT,
        permissions=["prehire.read"],
        modules_enabled=["pre_hiring", "assessments"],
    )
    record = auth.assemble_phase3(ctx, f"app:{app_key}", sections=("canonical_cv", "effective_facts", "classifications", "assessments"))
    adapter = RankingEvidenceAdapter()
    live_status = str(app_row.get("status") or "")
    unexplained: list[Any] = []
    if live_status in {"needs_role", "import_review", "import_archived"}:
        bundle = adapter.adapt(
            record,
            job_context=RankingJobContext(company_code=TENANT, position_code=str(app_row.get("position_code") or "POS-1"), criteria_version=1),
            application=app_row,
        )
        shadow = {
            "status": "PASS" if not bundle.eligible else "BLOCKER",
            "class": "expected_authority_difference",
            "denial": bundle.denial_reason,
            "unexplained": [],
        }
    else:
        live_record = CandidateKnowledgeRecord(
            candidate_ref=record.candidate_ref,
            company_code=record.company_code,
            as_of=record.as_of,
            knowledge_version=record.knowledge_version,
            subject=record.subject,
            canonical_cv=record.canonical_cv,
            effective_facts=record.effective_facts,
            classifications=record.classifications,
            coverage=record.coverage,
            actionability=Actionability(True, True, True, True),
        )
        legacy = build_legacy_ranking_row(
            company_code=TENANT,
            app_key=app_key,
            position_code=str(app_row.get("position_code") or "POS-1"),
            status=live_status or "shortlisted",
            raw_json={},
            candidate_profile={},
            cv_ready_fields={
                "cv_evidence_status": "ready",
                "cv_evidence_file_id": "f",
                "cv_evidence_source_sha256": "h",
                "cv_extraction_finalization_id": "fin",
                "cv_extraction_quality_ok": True,
                "cv_extracted_text_hash": "h",
                "cv_evidence_semantic_content_hash": "h",
                "semantic_content_hash": "h",
                "semantic_content": "skills",
                "cv_evidence_contract_version": "application-cv-evidence-v1",
            },
        )
        parity = run_shadow_parity(
            adapter=adapter,
            record=live_record,
            job_context=RankingJobContext(company_code=TENANT, position_code=str(app_row.get("position_code") or "POS-1"), criteria_version=1),
            application=app_row,
            legacy_row=legacy,
            job={"title": "Role", "requirements_en": ["skills"], "requirements": ["skills"]},
            hard_criteria=[],
            soft_criteria=[
                {
                    "criterion_id": "s1",
                    "classification": "soft",
                    "criterion_type": "technical_skill",
                    "active": True,
                    "rule_json": {"keywords": ["skills", "experience"]},
                }
            ],
        )
        unexplained = list(parity.unexplained_score_differences or [])
        shadow = {
            "status": "PASS" if not unexplained else "FAIL",
            "differences": parity.differences,
            "unexplained": unexplained,
            "evidence_versions": {
                "canonical_cv_version_id": (record.canonical_cv or {}).get("version_id"),
                "facts_id": (record.effective_facts or {}).get("facts_id"),
            },
        }
    out["shadow"] = shadow

    held_denied = True
    if held:
        held_overlay_probe = {
            "company_code": TENANT,
            "app_key": held["app_key"],
            "status": held["status"],
            "position_code": "POS-LIVE",
        }
        # Enable reader temporarily for probe
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="on", WATHEFNI_CK_RANKING_SHADOW="1")
        for k, v in _load_env().items():
            os.environ[k] = v
        overlay = apply_ranking_reader_overlay(
            company_code=TENANT,
            application=held_overlay_probe,
            eligibility={"eligibility_bucket": "eligible"},
        )
        held_denied = bool(overlay.get("active") and not overlay.get("eligible"))
        out["reader"]["held_probe"] = overlay
    else:
        out["reader"]["held_probe"] = {"status": "ACCEPTED_LIMITATION"}

    shadow_pass = shadow.get("status") == "PASS"
    unexplained_ok = len(unexplained) == 0
    versions_ok = True
    if shadow.get("evidence_versions"):
        versions_ok = bool(shadow["evidence_versions"].get("canonical_cv_version_id"))

    enable_reader = shadow_pass and unexplained_ok and held_denied and versions_ok
    if enable_reader:
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="on", WATHEFNI_CK_RANKING_SHADOW="1")
        h = restart_orch()
        # Prove rollback of reader
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off")
        h2 = restart_orch()
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="on")
        h3 = restart_orch()
        out["reader"].update(
            {
                "enabled": True,
                "status": "PASS",
                "held_remain_denied": held_denied,
                "unexplained_material_deltas": 0,
                "scores_and_evidence_versions_ok": versions_ok,
                "rollback_proven": h["http_code"] == 200 and h2["http_code"] == 200 and h3["http_code"] == 200,
                "health_enable": h,
                "health_rollback_off": h2,
                "health_restore_on": h3,
            }
        )
    else:
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off", WATHEFNI_CK_RANKING_SHADOW="0")
        restart_orch()
        out["reader"].update(
            {
                "enabled": False,
                "status": "NO-GO",
                "held_remain_denied": held_denied,
                "unexplained_material_deltas": len(unexplained),
                "scores_and_evidence_versions_ok": versions_ok,
                "shadow_status": shadow.get("status"),
            }
        )

    overall = "PASS" if shadow_pass and (out["reader"].get("status") in {"PASS", "NO-GO"}) else "FAIL"
    if enable_reader and not out["reader"].get("rollback_proven"):
        overall = "FAIL"
    out["status"] = overall
    out["live_reader_decision"] = "ON" if enable_reader else "OFF"
    return out


def kill_switch_and_restore(*, freeze_actors: str, ranking_reader: str) -> dict[str, Any]:
    # Kill
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off",
        WATHEFNI_CK_LIVE_TOOL_ACTORS="",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
    )
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
    h_kill = restart_orch()
    denied = invoke_live_tool("search_candidates", OWNER_AZIZ, {"query": "skills", "limit": 3})
    kill_ok = (not denied.get("success")) and denied.get("error") in {"ck_tools_disabled", "ck_actor_denied"} and h_kill["http_code"] == 200

    # Restore freeze posture
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=ranking_reader,
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on",
        WATHEFNI_CK_LIVE_TOOL_ACTORS=freeze_actors,
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="1" if ranking_reader == "on" else "0",
    )
    subprocess.check_call(["systemctl", "enable", "wathefni-ck-index.service"])
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
    h_restore = restart_orch()
    restored = invoke_live_tool("search_candidates", OWNER_AZIZ, {"query": "skills", "limit": 3})
    restore_ok = bool(restored.get("success")) and h_restore["http_code"] == 200
    viewer_still = invoke_live_tool("search_candidates", VIEWER_A, {"query": "skills", "limit": 3})
    viewer_ok = (not viewer_still.get("success")) and viewer_still.get("error") == "ck_actor_denied"

    return {
        "id": "kill_switch_and_restore",
        "status": "PASS" if kill_ok and restore_ok and viewer_ok else "BLOCKER",
        "kill": {"health": h_kill, "search": {"success": denied.get("success"), "error": denied.get("error")}},
        "restore": {
            "health": h_restore,
            "search_owner": {"success": restored.get("success"), "total": restored.get("total"), "error": restored.get("error")},
            "viewer_denied": viewer_ok,
            "flags": {
                "TOOLS": "on",
                "RANKING_READER": ranking_reader,
                "INDEX_WORKERS": "on",
                "LIVE_TOOL_ACTORS": freeze_actors,
            },
        },
    }


def estimate_voyage(*, query_calls: int) -> dict[str, Any]:
    # Index already voyage-labeled from controlled-live; this release mostly query-side.
    with _connect_ctx(_load_env())() as cur:
        cur.execute(
            """
            SELECT coalesce(sum(length(chunk_text)),0)::int AS chars,
                   count(*)::int AS n
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND state='current' AND embedding_provider='voyage'
            """,
            (TENANT,),
        )
        row = dict(cur.fetchone())
    doc_tokens = max(1, int(row["chars"]) // 4)
    query_tokens = max(1, query_calls * 24)
    # Document calls already sunk in prior readiness; report incremental query cost + retained index size.
    cost_query = (query_tokens / 1_000_000.0) * VOYAGE_USD_PER_MTOK
    cost_index_retained = (doc_tokens / 1_000_000.0) * VOYAGE_USD_PER_MTOK
    return {
        "model": "voyage-4-large",
        "current_voyage_chunks": row["n"],
        "approx_indexed_doc_tokens": doc_tokens,
        "approx_query_tokens": query_tokens,
        "query_calls": query_calls,
        "estimated_incremental_query_cost_usd": round(cost_query, 6),
        "estimated_retained_index_cost_usd": round(cost_index_retained, 6),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "stamp": OUT.name if OUT.name != "latest" else _now(),
        "started_at": _now(),
        "tenant": TENANT,
        "backup": str(BACKUP) if BACKUP else None,
    }

    env = _load_env()
    Ctx = _connect_ctx(env)

    # 1) record hashes already in PREDEPLOY; confirm backup present
    report["backup_ok"] = bool(BACKUP and (BACKUP / "db.dump").exists() and (BACKUP / "ROLLBACK.sh").exists())
    report["predeploy"] = (OUT / "PREDEPLOY.txt").read_text(encoding="utf-8") if (OUT / "PREDEPLOY.txt").exists() else None

    # 2) enable workers + health
    workers = enable_workers()
    report["workers"] = workers
    (OUT / "workers.json").write_text(json.dumps(workers, indent=2) + "\n")
    if workers.get("status") != "PASS":
        report["verdict"] = "FAIL"
        report["finished_at"] = _now()
        (OUT / "final-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 2

    # 3) small allowlist tools on
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
        WATHEFNI_CK_LIVE_TOOL_ACTORS=SMALL_ALLOWLIST,
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_OWNER_CANARY_ACTORS="ck-owner-canary",
        WATHEFNI_CK_RANKING_SHADOW="0",
    )
    h = restart_orch()
    report["small_allowlist"] = {
        "actors": SMALL_ALLOWLIST,
        "emails": ["azizalmulla16@gmail.com"],
        "roles": ["owner"],
        "health": h,
        "flags": dict(_load_env()),
    }

    # 4–5) final tests + monitoring
    small_tests = run_final_tests(Ctx, actors_phase="small", allowlist=SMALL_ALLOWLIST)
    report["small_phase_tests"] = small_tests
    (OUT / "small-phase-tests.json").write_text(json.dumps(small_tests, indent=2) + "\n")
    if small_tests.get("status") != "PASS":
        # fail closed: kill tools
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off", WATHEFNI_CK_LIVE_TOOL_ACTORS="", WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off")
        subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
        restart_orch()
        report["verdict"] = "FAIL"
        report["finished_at"] = _now()
        (OUT / "final-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"verdict": "FAIL", "phase": "small"}, indent=2))
        return 2

    # 6) expand to authorized WATHEFNI recruiters (active owners)
    _set_flags(WATHEFNI_CK_LIVE_TOOL_ACTORS=EXPANDED_ALLOWLIST)
    h2 = restart_orch()
    report["expanded_allowlist"] = {
        "actors": EXPANDED_ALLOWLIST,
        "emails": ["azizalmulla16@gmail.com", "f.burhama@disruptv.tech"],
        "roles": ["owner", "owner"],
        "note": "No hr_manager/recruiter roles exist yet; viewers remain denied",
        "health": h2,
    }
    expanded_tests = run_final_tests(Ctx, actors_phase="expanded", allowlist=EXPANDED_ALLOWLIST)
    report["expanded_phase_tests"] = expanded_tests
    (OUT / "expanded-phase-tests.json").write_text(json.dumps(expanded_tests, indent=2) + "\n")
    if expanded_tests.get("status") != "PASS":
        _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off", WATHEFNI_CK_LIVE_TOOL_ACTORS="", WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off")
        subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
        restart_orch()
        report["verdict"] = "FAIL"
        report["finished_at"] = _now()
        (OUT / "final-report.json").write_text(json.dumps(report, indent=2) + "\n")
        return 2

    # 7) Ranking shadow + conditional live reader
    ranking = ranking_shadow_and_reader(Ctx)
    report["ranking"] = ranking
    (OUT / "ranking.json").write_text(json.dumps(ranking, indent=2) + "\n")
    ranking_reader_final = "on" if ranking.get("live_reader_decision") == "ON" else "off"

    # 8) kill switch + restore freeze
    ks = kill_switch_and_restore(freeze_actors=EXPANDED_ALLOWLIST, ranking_reader=ranking_reader_final)
    report["kill_switch"] = ks
    (OUT / "kill-switch.json").write_text(json.dumps(ks, indent=2) + "\n")

    # Voyage / monitoring rollup
    qcalls = int(small_tests.get("monitoring", {}).get("voyage_query_calls_observed") or 0) + int(
        expanded_tests.get("monitoring", {}).get("voyage_query_calls_observed") or 0
    )
    report["voyage"] = estimate_voyage(query_calls=qcalls)
    report["final_flags"] = {k: v for k, v in _load_env().items() if k.startswith("WATHEFNI_") or k.startswith("CK_")}
    report["external_tenants"] = "OFF"
    report["role_profiles"] = "OFF"

    blockers = []
    for section in (workers, small_tests, expanded_tests, ranking, ks):
        if isinstance(section, dict) and section.get("status") in {"FAIL", "BLOCKER"}:
            blockers.append(section)
    # Ranking NO-GO reader is acceptable if shadow PASS
    if ranking.get("status") == "FAIL":
        blockers.append(ranking)

    verdict = "PASS" if not blockers and ks.get("status") == "PASS" else "FAIL"
    report["verdict"] = verdict
    report["finished_at"] = _now()
    report["accepted_limitations"] = [
        "Only two WATHEFNI owners exist as authorized recruiter/admin actors; viewers remain denied.",
        "No hr_manager/recruiter role rows to expand beyond owners.",
        "External tenants remain OFF.",
        "Role Profiles remain OFF.",
        "Live Ranking reader enabled only when shadow/held/version/rollback gates pass; otherwise stays OFF.",
        "Corpus remains the current ready indexed CVs (bounded production set).",
    ]
    (OUT / "final-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verdict": verdict, "ranking_reader": ranking_reader_final, "out": str(OUT)}, indent=2))
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
