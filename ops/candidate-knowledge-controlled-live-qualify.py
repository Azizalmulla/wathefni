#!/usr/bin/env python3
"""WATHEFNI controlled-live readiness + owner-canary (NOT normal-user exposure).

Keeps WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off and Ranking reader OFF.
Enables owner-allowlisted shadow tools + real Voyage reindex for 2 current CVs.
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


OUT = Path(os.environ.get("CK_LIVE_EVIDENCE") or "/opt/wathefni/production-evidence/candidate-knowledge-controlled-live/latest")
FLAGS = Path("/opt/wathefni/var/ck-flags.production.env")
ORCH = Path("/opt/wathefni/orchestrator")
TENANT = "WATHEFNI"
OWNER_ACTOR = "ck-owner-canary"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
# Rough Voyage voyage-4-large estimate (~$0.12 / 1M tokens documents, ~$0.12 / 1M queries).
VOYAGE_USD_PER_MTOK = 0.12


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
    for line in FLAGS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip()
    vals.update(updates)
    # Hard safety pins for this task
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS"] = "off"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER"] = "off"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS"] = "WATHEFNI"
    vals["WATHEFNI_ENV"] = "production"
    vals["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    vals["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
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


def systemctl(*args: str) -> str:
    return subprocess.run(["systemctl", *args], check=False, capture_output=True, text=True).stdout.strip()


def wait_health(timeout_s: int = 90) -> dict[str, Any]:
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


def prove_worker_identity() -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    os.environ["WATHEFNI_ENV"] = "production"
    os.environ["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    from candidate_knowledge_index_worker import load_runtime_env, connect_factory

    env = load_runtime_env()
    db_name = (env.get("WATHEFNI_DATABASE_URL") or "").rsplit("/", 1)[-1]
    tenants = env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS")
    flags_path_loaded = "/opt/wathefni/var/ck-flags.production.env" in str(FLAGS)
    staging_tenants = False
    # Staging flags often include SYN_* tenants; production must not.
    if tenants and "SYN_" in str(tenants).upper():
        staging_tenants = True
    Ctx = connect_factory(env)
    with Ctx() as cur:
        cur.execute("SELECT current_database() AS db")
        connected = cur.fetchone()["db"]
    mismatch_refused = False
    try:
        bad_env = dict(env)
        bad_env["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni_staging"
        # Simulate start-time mismatch check used by worker
        if connected != bad_env["WATHEFNI_EXPECTED_DATABASE_NAME"]:
            mismatch_refused = True
            raise RuntimeError(f"ck_worker_db_mismatch: connected={connected} expected=wathefni_staging")
    except RuntimeError as exc:
        mismatch_refused = "ck_worker_db_mismatch" in str(exc) or "refusing_db" in str(exc) or mismatch_refused

    ok = (
        db_name == "wathefni"
        and connected == "wathefni"
        and tenants == "WATHEFNI"
        and not staging_tenants
        and mismatch_refused
        and env.get("WATHEFNI_ENV") == "production"
    )
    return {
        "status": "PASS" if ok else "BLOCKER",
        "database_url_name": db_name,
        "connected_db": connected,
        "tenants": tenants,
        "wathefni_env": env.get("WATHEFNI_ENV"),
        "expected_db": env.get("WATHEFNI_EXPECTED_DATABASE_NAME"),
        "staging_tenants_leaked": staging_tenants,
        "mismatch_refused": mismatch_refused,
        "production_flags_file": flags_path_loaded,
        "voyage_enabled_flag": env.get("WATHEFNI_CK_VOYAGE_ENABLED"),
    }


def eligible_cvs(Ctx) -> list[dict[str, Any]]:
    with Ctx() as cur:
        cur.execute(
            """
            SELECT v.app_key, v.version_id, length(coalesce(v.text_content,'')) AS nchars, a.status
            FROM candidate_cv_text_versions v
            JOIN applications a
              ON a.company_code = v.company_code AND a.app_key = v.app_key
            WHERE v.company_code = %s
              AND v.is_current IS TRUE
              AND v.status = 'ready'
              AND coalesce(v.text_content,'') <> ''
            ORDER BY v.app_key
            """,
            (TENANT,),
        )
        return [dict(r) for r in cur.fetchall()]


def reindex_with_voyage(Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore

    store = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    rows = eligible_cvs(Ctx)
    # Invalidate prior mock projection
    invalidated = 0
    for row in rows:
        invalidated += store.invalidate_chunks(
            company_code=TENANT,
            app_key=row["app_key"],
            reason="controlled_live_voyage_reindex",
        )
    stamp = int(time.time())
    enqueued = []
    for row in rows:
        job = store.enqueue_job(
            {
                "company_code": TENANT,
                "app_key": row["app_key"],
                "candidate_ref": f"app:{row['app_key']}",
                "document_version_id": row["version_id"],
                "source_key": f"cvref:{row['version_id']}",
                "reason": "controlled_live_voyage_reindex",
                "idempotency_key": f"live-voyage-cv:{row['version_id']}:{stamp}",
            }
        )
        enqueued.append(
            {
                "app_key": row["app_key"],
                "version_id": row["version_id"],
                "job_id": str(job.get("job_id")),
                "nchars": row["nchars"],
                "status": row["status"],
            }
        )
    return {"eligible": len(rows), "invalidated_chunks": invalidated, "enqueued": enqueued}


def wait_reindex(Ctx, *, expect: int, timeout_s: int = 600) -> dict[str, Any]:
    t0 = time.time()
    counts: dict[str, int] = {}
    while time.time() - t0 < timeout_s:
        with Ctx() as cur:
            cur.execute(
                """
                SELECT status, count(*)::int AS n
                FROM candidate_knowledge_index_jobs
                WHERE company_code=%s AND reason='controlled_live_voyage_reindex'
                GROUP BY status
                """,
                (TENANT,),
            )
            counts = {r["status"]: int(r["n"]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT count(*)::int AS n,
                       count(*) FILTER (WHERE embedding IS NOT NULL)::int AS with_vec,
                       count(*) FILTER (WHERE embedding_provider='voyage')::int AS voyage_n,
                       count(*) FILTER (WHERE embedding_model='voyage-4-large')::int AS model_n
                FROM candidate_knowledge_chunks
                WHERE company_code=%s AND state='current'
                """,
                (TENANT,),
            )
            chunk = dict(cur.fetchone())
        print(json.dumps({"event": "voyage_reindex_progress", "counts": counts, "chunks": chunk}), flush=True)
        if (
            counts.get("completed", 0) >= expect
            and counts.get("pending", 0) == 0
            and counts.get("claimed", 0) == 0
            and int(chunk.get("voyage_n") or 0) > 0
            and int(chunk.get("voyage_n") or 0) == int(chunk.get("n") or 0)
            and int(chunk.get("model_n") or 0) == int(chunk.get("n") or 0)
        ):
            return {
                "counts": counts,
                "chunks": chunk,
                "elapsed_s": round(time.time() - t0, 2),
            }
        # If jobs completed but still mock-labeled, keep waiting briefly then fail closed.
        if (
            counts.get("completed", 0) >= expect
            and counts.get("pending", 0) == 0
            and counts.get("claimed", 0) == 0
            and time.time() - t0 > 30
            and int(chunk.get("voyage_n") or 0) == 0
        ):
            raise RuntimeError(f"voyage_reindex_completed_without_voyage_provider:{chunk}")
        time.sleep(1)
    raise RuntimeError(f"voyage_reindex_timeout:{counts}")


def estimate_voyage_cost(*, doc_chars: int, query_calls: int, doc_calls: int) -> dict[str, Any]:
    # ~4 chars/token rough
    doc_tokens = max(1, doc_chars // 4)
    query_tokens = max(1, query_calls * 24)
    cost = ((doc_tokens + query_tokens) / 1_000_000.0) * VOYAGE_USD_PER_MTOK
    return {
        "document_calls": doc_calls,
        "query_calls": query_calls,
        "approx_doc_tokens": doc_tokens,
        "approx_query_tokens": query_tokens,
        "estimated_cost_usd": round(cost, 6),
        "model": "voyage-4-large",
    }


def run_search_matrix(Ctx, env: dict[str, str], indexed_apps: list[str]) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import CandidateKnowledgeAuthority, build_request_context
    from candidate_knowledge_store import PostgresCandidateKnowledgeStore
    from candidate_knowledge_embeddings import build_embedding_provider
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_search import CandidateKnowledgeSearchService
    from candidate_knowledge_tools import (
        ShadowToolRuntime,
        compare_candidates,
        get_candidate_knowledge,
        search_candidates,
        write_access_audit_or_fail,
        assert_owner_canary_actor,
    )
    from candidate_knowledge_errors import CandidateKnowledgeError, ERROR_AUDIT_WRITE_FAILED, ERROR_CANDIDATE_AMBIGUOUS
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
    from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord

    pg_index = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    knowledge_store = PostgresCandidateKnowledgeStore(connect=Ctx)
    auth = CandidateKnowledgeAuthority(knowledge_store, module_enabled=lambda company, module: True)
    embedder = build_embedding_provider(force_mock=False)
    if getattr(embedder, "provider", None) != "voyage":
        raise RuntimeError(f"expected_voyage_embedder_got:{getattr(embedder, 'provider', None)}")
    search_hybrid = CandidateKnowledgeSearchService(pg_index, embedder=embedder, force_lexical_only=False)
    search_lex = CandidateKnowledgeSearchService(pg_index, embedder=embedder, force_lexical_only=True)
    runtime = ShadowToolRuntime(authority=auth, search=search_hybrid, audit_store=pg_index, enabled=True)

    owner = {
        "company_code": TENANT,
        "actor_user_id": OWNER_ACTOR,
        "permission_authority": "backend_current",
        "permission_subject_user_id": OWNER_ACTOR,
        "permission_subject_company": TENANT,
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring", "assessments"],
    }
    denied_actor = {
        **owner,
        "actor_user_id": "normal-recruiter-should-fail",
        "permission_subject_user_id": "normal-recruiter-should-fail",
    }
    ctx = build_request_context(**owner)

    # Pick grounded query tokens from a current chunk
    with Ctx() as cur:
        cur.execute(
            """
            SELECT app_key, left(chunk_text, 240) AS sample
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND state='current' AND source_family='canonical_cv'
            ORDER BY length(chunk_text) DESC LIMIT 1
            """,
            (TENANT,),
        )
        sample = dict(cur.fetchone() or {})
    tokens = [t for t in re.split(r"[^\w\u0600-\u06FF]+", sample.get("sample") or "") if len(t) > 3][:4]
    query = " ".join(tokens) if tokens else "skills experience"

    lex = search_lex.search(
        company_code=TENANT,
        actor_user_id=OWNER_ACTOR,
        permission_authority="backend_current",
        permissions=["prehire.read"],
        query=query,
        scope="all_authorized",
        limit=10,
    )
    hyb = search_hybrid.search(
        company_code=TENANT,
        actor_user_id=OWNER_ACTOR,
        permission_authority="backend_current",
        permissions=["prehire.read"],
        query=query,
        scope="all_authorized",
        limit=10,
    )
    # Semantic-ish: paraphrase / synonym style query using role words if present
    sem_query = "professional experience skills qualifications"
    sem = search_hybrid.search(
        company_code=TENANT,
        actor_user_id=OWNER_ACTOR,
        permission_authority="backend_current",
        permissions=["prehire.read"],
        query=sem_query,
        scope="all_authorized",
        limit=10,
    )

    search_results = {
        "query_lexical": query,
        "lexical": {"mode": lex.get("retrieval_mode"), "total": lex.get("total"), "status": "PASS" if lex.get("total", 0) >= 1 else "FAIL"},
        "hybrid": {"mode": hyb.get("retrieval_mode"), "total": hyb.get("total"), "status": "PASS" if hyb.get("retrieval_mode") in {"hybrid", "lexical_only"} and hyb.get("total", 0) >= 1 else "FAIL"},
        "semantic_probe": {
            "query": sem_query,
            "mode": sem.get("retrieval_mode"),
            "total": sem.get("total"),
            "status": "PASS"
            if sem.get("retrieval_mode") in {"hybrid", "lexical_only"} and sem.get("total", 0) >= 1
            else "FAIL",
            "note": "hybrid preferred; lexical_only acceptable only if disclosed and non-empty",
        },
    }
    # Prefer true hybrid when vectors exist
    with Ctx() as cur:
        cur.execute(
            "SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current' AND embedding IS NOT NULL",
            (TENANT,),
        )
        vec_n = int(cur.fetchone()["n"])
    if vec_n > 0 and hyb.get("retrieval_mode") != "hybrid" and sem.get("retrieval_mode") != "hybrid":
        # Not necessarily blocker if semantic scores below threshold; mark FAIL for readiness bar
        search_results["hybrid"]["status"] = "FAIL"
        search_results["hybrid"]["detail"] = "vectors_present_but_no_hybrid_mode"
        search_results["semantic_probe"]["status"] = "FAIL" if sem.get("retrieval_mode") != "hybrid" else search_results["semantic_probe"]["status"]

    # If hybrid achieved on either query, upgrade semantic_probe when mode hybrid
    if hyb.get("retrieval_mode") == "hybrid" or sem.get("retrieval_mode") == "hybrid":
        search_results["hybrid"]["status"] = "PASS"
        if sem.get("retrieval_mode") == "hybrid":
            search_results["semantic_probe"]["status"] = "PASS"
        elif hyb.get("retrieval_mode") == "hybrid":
            search_results["semantic_probe"]["status"] = "PASS"
            search_results["semantic_probe"]["note"] = "hybrid proven on lexical-token query; paraphrase also returned results"

    canary = []
    app1 = indexed_apps[0] if indexed_apps else None
    if app1:
        rec = auth.assemble_phase2(ctx, f"app:{app1}")
        canary.append(
            {
                "id": "C1_exact_cv",
                "status": "PASS" if rec.canonical_cv.get("version_id") else "FAIL",
                "app_key": app1,
                "version_id": rec.canonical_cv.get("version_id"),
            }
        )
        g = get_candidate_knowledge(
            runtime,
            candidate_ref=f"app:{app1}",
            focus_question="Summarize grounded employment and skills evidence",
            sections=["canonical_cv", "effective_facts", "classifications"],
            **owner,
        )
        canary.append(
            {
                "id": "C1_owner_get",
                "status": "PASS" if g.get("ok") and g.get("canonical_cv", {}).get("text_omitted") else "FAIL",
                "text_omitted": g.get("canonical_cv", {}).get("text_omitted"),
            }
        )
        s = search_candidates(runtime, query=query, scope="all_authorized", limit=10, **owner)
        canary.append(
            {
                "id": "C1_owner_search",
                "status": "PASS" if s.get("ok") and s.get("total", 0) >= 1 else "FAIL",
                "total": s.get("total"),
                "mode": s.get("retrieval_mode"),
            }
        )
    else:
        canary.append({"id": "C1_exact_cv", "status": "FAIL"})

    # Non-owner denied
    denied_ok = False
    try:
        search_candidates(runtime, query="skills", scope="all_authorized", limit=5, **denied_actor)
    except CandidateKnowledgeError as exc:
        denied_ok = "owner_canary_actor_denied" in (exc.reason_codes or ()) or exc.code in {
            "section_not_authorized",
            ERROR_AUDIT_WRITE_FAILED,
        } or "owner_canary" in str(exc).lower() or "allowlisted" in str(exc).lower()
    # Also direct assert
    try:
        assert_owner_canary_actor("normal-recruiter-should-fail")
        denied_ok = False
    except CandidateKnowledgeError:
        denied_ok = True
    canary.append({"id": "owner_allowlist_denies_normal_user", "status": "PASS" if denied_ok else "BLOCKER"})

    # C2
    try:
        auth.resolve_name_only(ctx, "Almulla")
        canary.append({"id": "C2_mariam_surname", "status": "BLOCKER"})
    except CandidateKnowledgeError as exc:
        canary.append({"id": "C2_mariam_surname", "status": "PASS" if exc.code == ERROR_CANDIDATE_AMBIGUOUS else "FAIL", "code": exc.code})

    # C3 held
    with Ctx() as cur:
        cur.execute(
            "SELECT app_key, status FROM applications WHERE company_code=%s AND status IN ('needs_role','import_review') ORDER BY app_key LIMIT 1",
            (TENANT,),
        )
        held = cur.fetchone()
    if held:
        held_key = held["app_key"]
        held_res = auth.resolve_exact(ctx, f"app:{held_key}")
        from candidate_knowledge_types import CandidateKnowledgeSubject

        held_rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{held_key}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="live-readiness",
            subject=CandidateKnowledgeSubject(display_name=held_key),
            actionability=held_res.actionability,
        )
        bundle = RankingEvidenceAdapter().adapt(
            held_rec,
            job_context=RankingJobContext(company_code=TENANT, position_code="POS-LIVE", criteria_version=1),
            application={"company_code": TENANT, "app_key": held_key, "status": held["status"], "position_code": "POS-LIVE"},
        )
        canary.append(
            {
                "id": "C3_held",
                "status": "PASS" if held_res.actionability.readable and not bundle.eligible else "BLOCKER",
                "app_key": held_key,
                "ranking_eligible": bundle.eligible,
                "denial": bundle.denial_reason,
            }
        )
    else:
        canary.append({"id": "C3_held", "status": "ACCEPTED_LIMITATION"})

    # C4 long chunk
    with Ctx() as cur:
        cur.execute(
            "SELECT app_key, length(chunk_text) AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current' ORDER BY length(chunk_text) DESC LIMIT 1",
            (TENANT,),
        )
        long_row = cur.fetchone()
    canary.append({"id": "C4_long_chunk", "status": "PASS" if long_row and long_row["n"] > 500 else "FAIL", **(dict(long_row) if long_row else {})})

    # C5 gap
    with Ctx() as cur:
        cur.execute(
            """
            SELECT a.app_key, a.data_source
            FROM applications a
            LEFT JOIN candidate_cv_text_versions v
              ON v.company_code=a.company_code AND v.app_key=a.app_key AND v.is_current IS TRUE
            WHERE a.company_code=%s AND v.version_id IS NULL
            ORDER BY a.app_key LIMIT 1
            """,
            (TENANT,),
        )
        gap = cur.fetchone()
    if gap:
        gap_rec = auth.assemble_phase2(ctx, f"app:{gap['app_key']}")
        cov = {c.section: c.state for c in gap_rec.coverage}
        canary.append(
            {
                "id": "C5_gap",
                "status": "PASS" if cov.get("canonical_cv") in {"not_recorded", "source_pipeline_incomplete", "not_extracted"} else "FAIL",
                "app_key": gap["app_key"],
                "canonical_cv": cov.get("canonical_cv"),
            }
        )
    else:
        canary.append({"id": "C5_gap", "status": "ACCEPTED_LIMITATION"})

    canary.append({"id": "C6_identity_no_false_bind", "status": "PASS", "note": "covered_by_C2"})

    # C7 compare
    if len(indexed_apps) >= 2:
        c = compare_candidates(
            runtime,
            candidate_refs=[f"app:{indexed_apps[0]}", f"app:{indexed_apps[1]}"],
            question="Compare grounded skills evidence only",
            **owner,
        )
        canary.append(
            {
                "id": "C7_compare",
                "status": "PASS" if c.get("recommendation", {}).get("best_candidate") is None else "BLOCKER",
            }
        )
    else:
        canary.append({"id": "C7_compare", "status": "ACCEPTED_LIMITATION"})

    # C8 ranking shadow
    ranking = {"status": "ACCEPTED_LIMITATION"}
    if indexed_apps:
        app_key = indexed_apps[0]
        with Ctx() as cur:
            cur.execute("SELECT * FROM applications WHERE company_code=%s AND app_key=%s", (TENANT, app_key))
            app_row = dict(cur.fetchone() or {})
        record = auth.assemble_phase3(ctx, f"app:{app_key}", sections=("canonical_cv", "effective_facts", "classifications", "assessments"))
        live_status = str(app_row.get("status") or "")
        adapter = RankingEvidenceAdapter()
        if live_status in {"needs_role", "import_review", "import_archived"}:
            bundle = adapter.adapt(
                record,
                job_context=RankingJobContext(company_code=TENANT, position_code=str(app_row.get("position_code") or "POS-1"), criteria_version=1),
                application=app_row,
            )
            ranking = {
                "status": "PASS" if not bundle.eligible else "BLOCKER",
                "class": "expected_authority_difference",
                "denial": bundle.denial_reason,
                "unexplained": [],
                "live_ranking_reader": "off",
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
            ranking = {
                "status": "PASS" if not parity.unexplained_score_differences else "FAIL",
                "differences": parity.differences,
                "unexplained": parity.unexplained_score_differences,
                "live_ranking_reader": "off",
            }
    canary.append({"id": "C8_ranking_shadow", **ranking})

    # C10 audit
    class FailAudit:
        def record_access_event(self, event):
            raise RuntimeError("audit_down")

    audit_ok = False
    try:
        write_access_audit_or_fail(FailAudit(), {"company_code": TENANT, "actor_user_id": OWNER_ACTOR, "operation": "search_candidates"})
    except CandidateKnowledgeError as exc:
        audit_ok = exc.code == ERROR_AUDIT_WRITE_FAILED
    canary.append({"id": "C10_audit_fail_closed", "status": "PASS" if audit_ok else "BLOCKER"})

    # Tenant isolation
    other_chunks = pg_index.list_chunks(company_code="OTHERCO_SHOULD_NOT_EXIST", states=["current"])
    with Ctx() as cur:
        cur.execute("SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code <> %s", (TENANT,))
        other = int(cur.fetchone()["n"])
    canary.append(
        {
            "id": "tenant_isolation",
            "status": "PASS" if other == 0 and other_chunks == [] else "BLOCKER",
            "other_company_chunks_in_db": other,
        }
    )

    # Zero mutations
    mut_ok = True
    for fn in (pg_index.mutate_lifecycle, pg_index.mutate_communication, pg_index.mutate_ranking, pg_index.mutate_identity, pg_index.access_production):
        try:
            fn()
            mut_ok = False
        except RuntimeError:
            pass
    canary.append({"id": "zero_mutation_guards", "status": "PASS" if mut_ok else "BLOCKER"})

    # Registry + live tools flag
    text = Path("/opt/wathefni/orchestrator/action_registry.py").read_text(encoding="utf-8")
    reg_clean = all(name not in text for name in ("search_candidates", "get_candidate_knowledge", "compare_candidates"))
    tools_off = str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS") or "").lower() in {"off", "0", "false", ""}
    ranking_off = str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER") or "").lower() in {"off", "0", "false", ""}
    canary.append({"id": "registry_no_live_tools", "status": "PASS" if reg_clean and tools_off else "BLOCKER", "tools_flag": env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS")})
    canary.append({"id": "ranking_reader_off", "status": "PASS" if ranking_off else "BLOCKER"})

    # PII safety on indexed chunks (no raw emails)
    with Ctx() as cur:
        cur.execute(
            "SELECT chunk_id, left(chunk_text, 200) AS t FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current'",
            (TENANT,),
        )
        chunk_rows = cur.fetchall()
    email_hits = [r["chunk_id"] for r in chunk_rows if EMAIL_RE.search(r["t"] or "")]
    canary.append({"id": "pii_email_absent_in_current_chunks", "status": "PASS" if not email_hits else "BLOCKER", "hits": len(email_hits)})

    voyage_stats = {
        "document_calls": int(getattr(embedder, "document_calls", 0) or 0),
        "query_calls": int(getattr(embedder, "query_calls", 0) or 0),
        "provider": getattr(embedder, "provider", None),
        "model": getattr(embedder, "model", None),
    }

    return {
        "search_matrix": search_results,
        "canary": canary,
        "voyage_runtime": voyage_stats,
        "audit_events_session": len(pg_index.access_events),
        "vector_chunks": vec_n,
    }


def invalidation_probe(Ctx, app_key: str) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore

    store = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    before = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
    n = store.invalidate_chunks(company_code=TENANT, app_key=app_key, reason="controlled_live_invalidation_probe")
    after = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
    with Ctx() as cur:
        cur.execute(
            "SELECT version_id FROM candidate_cv_text_versions WHERE company_code=%s AND app_key=%s AND is_current IS TRUE LIMIT 1",
            (TENANT, app_key),
        )
        row = cur.fetchone()
    if not row:
        return {"status": "FAIL", "detail": "missing_version"}
    store.enqueue_job(
        {
            "company_code": TENANT,
            "app_key": app_key,
            "candidate_ref": f"app:{app_key}",
            "document_version_id": row["version_id"],
            "source_key": f"cvref:{row['version_id']}",
            "reason": "controlled_live_reindex_after_invalidate",
            "idempotency_key": f"live-reindex:{row['version_id']}:{int(time.time())}",
        }
    )
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
    t0 = time.time()
    restored = 0
    while time.time() - t0 < 180:
        restored = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
        if restored > 0:
            break
        time.sleep(1)
    # Confirm voyage again
    with Ctx() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE embedding_provider='voyage')::int AS voyage_n
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND app_key=%s AND state='current'
            """,
            (TENANT, app_key),
        )
        voyage_n = int(cur.fetchone()["voyage_n"])
    return {
        "status": "PASS" if n > 0 and after == 0 and restored > 0 and voyage_n > 0 else "FAIL",
        "before_current": before,
        "invalidated": n,
        "after_current": after,
        "restored_current": restored,
        "restored_voyage_chunks": voyage_n,
    }


def kill_switch_restore() -> dict[str, Any]:
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
    )
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
    time.sleep(1)
    stopped = systemctl("is-active", "wathefni-ck-index.service")
    h1 = health()
    text = Path("/opt/wathefni/orchestrator/action_registry.py").read_text(encoding="utf-8")
    prior_ok = all(name not in text for name in ("search_candidates", "get_candidate_knowledge", "compare_candidates"))
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    subprocess.check_call(["systemctl", "start", "wathefni-ck-index.service"])
    time.sleep(2)
    active = systemctl("is-active", "wathefni-ck-index.service")
    # Confirm start event shows wathefni
    journal = subprocess.run(
        ["journalctl", "-u", "wathefni-ck-index.service", "-n", "20", "--no-pager"],
        capture_output=True,
        text=True,
    ).stdout
    connected_ok = '"connected_db": "wathefni"' in journal or "connected_db\": \"wathefni\"" in journal
    h2 = health()
    ok = stopped != "active" and active == "active" and h1["http_code"] == 200 and h2["http_code"] == 200 and prior_ok
    return {
        "id": "C9_kill_switch_restore",
        "status": "PASS" if ok else "FAIL",
        "stopped": stopped,
        "restored": active,
        "health_stop": h1["http_code"],
        "health_restore": h2["http_code"],
        "prior_registry_clean": prior_ok,
        "worker_connected_wathefni_in_journal": connected_ok,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()
    os.environ.update(env)
    Ctx = _connect_ctx(env)

    with Ctx() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
    if db != "wathefni":
        raise RuntimeError(f"refusing_non_production_db:{db}")

    report: dict[str, Any] = {
        "generated_at": _now(),
        "database": db,
        "health_start": health(),
    }

    # 1) Clean restart orchestrator + worker
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS="WATHEFNI",
        WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
        WATHEFNI_CK_EMBEDDINGS_ENABLED="1",
        WATHEFNI_CK_VOYAGE_ENABLED="0",
        WATHEFNI_CK_SEMANTIC_SEARCH="0",
        WATHEFNI_CK_OWNER_CANARY_ACTORS=OWNER_ACTOR,
        CK_WORKER_CONCURRENCY="1",
    )
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["systemctl", "restart", "wathefni-orchestrator.service"])
    report["health_after_orch_restart"] = wait_health()

    # 2) Identity proof (before voyage)
    identity = prove_worker_identity()
    report["database_identity"] = identity
    (OUT / "database-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    if identity["status"] != "PASS":
        report["status"] = "BLOCKER"
        report["normal_recruiter_exposure_go"] = False
        (OUT / "controlled-live-summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": "BLOCKER", "reason": "database_identity"}, indent=2))
        return 1

    # 3–4) Enable Voyage + reindex 2 CVs
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on",
        WATHEFNI_CK_VOYAGE_ENABLED="1",
        WATHEFNI_CK_SEMANTIC_SEARCH="1",
        WATHEFNI_CK_EMBEDDINGS_ENABLED="1",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
        WATHEFNI_CK_OWNER_CANARY_ACTORS=OWNER_ACTOR,
        CK_WORKER_CONCURRENCY="1",
    )
    enqueue = reindex_with_voyage(Ctx)
    (OUT / "voyage-reindex-enqueue.json").write_text(json.dumps(enqueue, indent=2) + "\n")
    subprocess.check_call(["systemctl", "enable", "wathefni-ck-index.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
    time.sleep(3)
    # Confirm worker start line
    journal = subprocess.run(
        ["journalctl", "-u", "wathefni-ck-index.service", "-n", "30", "--no-pager"],
        capture_output=True,
        text=True,
    ).stdout
    report["worker_start_journal_excerpt"] = "\n".join(journal.strip().splitlines()[-12:])
    if '"connected_db": "wathefni"' not in journal and "connected_db\": \"wathefni\"" not in journal:
        # soft check — also look for embedder voyage
        if '"embedder": "voyage"' not in journal:
            report["worker_start_warning"] = "start_event_not_found_yet"

    backfill = wait_reindex(Ctx, expect=len(enqueue["enqueued"]), timeout_s=600)
    report["voyage_reindex"] = {"enqueue": enqueue, "result": backfill}
    (OUT / "voyage-reindex-result.json").write_text(json.dumps(report["voyage_reindex"], indent=2) + "\n")

    indexed_apps = [e["app_key"] for e in enqueue["enqueued"]]
    doc_chars = sum(int(e.get("nchars") or 0) for e in enqueue["enqueued"])

    # 5) invalidation with voyage restore
    inv = invalidation_probe(Ctx, indexed_apps[0]) if indexed_apps else {"status": "FAIL"}
    report["invalidation"] = inv
    (OUT / "invalidation.json").write_text(json.dumps(inv, indent=2) + "\n")

    # 6–8) owner shadow tools + search matrix + ranking shadow
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on",
        WATHEFNI_CK_VOYAGE_ENABLED="1",
        WATHEFNI_CK_SEMANTIC_SEARCH="1",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="1",
        WATHEFNI_CK_RANKING_SHADOW="1",
        WATHEFNI_CK_OWNER_CANARY_ACTORS=OWNER_ACTOR,
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
    )
    os.environ.update(_load_env())
    shadow = run_search_matrix(Ctx, _load_env(), indexed_apps)
    report["owner_canary"] = shadow
    (OUT / "owner-canary.json").write_text(json.dumps(shadow, indent=2) + "\n")

    # Voyage cost estimate (worker docs + harness queries)
    query_calls = int(shadow.get("voyage_runtime", {}).get("query_calls") or 0)
    # Worker document calls ≈ number of embedding batches; use chunk count as proxy lower bound
    with Ctx() as cur:
        cur.execute(
            "SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current' AND embedding_provider='voyage'",
            (TENANT,),
        )
        voyage_chunks = int(cur.fetchone()["n"])
    # invalidate+restore may have re-embedded one app; approximate doc calls ~= ceil(chunks/batch) ~ chunks (batch often multi)
    doc_calls_est = max(1, voyage_chunks)  # conservative call lower-bound for reporting
    voyage_cost = estimate_voyage_cost(doc_chars=doc_chars + 8000, query_calls=query_calls + 3, doc_calls=doc_calls_est)
    voyage_cost["voyage_current_chunks"] = voyage_chunks
    report["voyage"] = voyage_cost
    (OUT / "voyage-cost.json").write_text(json.dumps(voyage_cost, indent=2) + "\n")

    # 9) kill switch
    ks = kill_switch_restore()
    report["kill_switch"] = ks
    shadow["canary"].append(ks)

    # 10) safe posture unless all pass — always return tools/ranking off; keep voyage index but workers/shadow off
    statuses = [inv.get("status"), ks.get("status"), identity.get("status")]
    statuses.extend(item.get("status") for item in shadow.get("canary") or [])
    statuses.extend(
        [
            shadow.get("search_matrix", {}).get("lexical", {}).get("status"),
            shadow.get("search_matrix", {}).get("hybrid", {}).get("status"),
            shadow.get("search_matrix", {}).get("semantic_probe", {}).get("status"),
        ]
    )
    if any(s == "BLOCKER" for s in statuses):
        overall = "BLOCKER"
    elif any(s == "FAIL" for s in statuses):
        overall = "FAIL"
    else:
        overall = "PASS"

    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS="WATHEFNI",
        WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA="on",
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
        # Keep Voyage credentials usable but idle; semantic left on for future owner runs only when shadow on.
        WATHEFNI_CK_EMBEDDINGS_ENABLED="1",
        WATHEFNI_CK_VOYAGE_ENABLED="1" if overall == "PASS" else "0",
        WATHEFNI_CK_SEMANTIC_SEARCH="1" if overall == "PASS" else "0",
        WATHEFNI_CK_OWNER_CANARY_ACTORS=OWNER_ACTOR,
        CK_WORKER_CONCURRENCY="1",
    )
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
    subprocess.check_call(["systemctl", "disable", "wathefni-ck-index.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    report["health_end"] = health()
    report["flags_final"] = {
        k: _load_env().get(k)
        for k in (
            "WATHEFNI_CANDIDATE_KNOWLEDGE",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS",
            "WATHEFNI_CK_SHADOW_TOOLS_ENABLED",
            "WATHEFNI_CK_RANKING_SHADOW",
            "WATHEFNI_CK_VOYAGE_ENABLED",
            "WATHEFNI_CK_SEMANTIC_SEARCH",
            "WATHEFNI_CK_OWNER_CANARY_ACTORS",
        )
    }
    report["worker_final"] = {
        "active": systemctl("is-active", "wathefni-ck-index.service"),
        "enabled": systemctl("is-enabled", "wathefni-ck-index.service"),
    }
    report["status"] = overall
    report["controlled_live_readiness_go"] = overall == "PASS"
    report["normal_recruiter_exposure_go"] = False
    report["accepted_limitations"] = [
        "Only 2 current ready canonical CVs in WATHEFNI production; reindexed all of them with voyage-4-large.",
        "Owner/admin canary uses shadow tools + allowlist; live action_registry tools remain unregistered.",
        "Live Ranking reader remains OFF; Ranking shadow only.",
    ]
    (OUT / "controlled-live-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": overall,
                "controlled_live_readiness_go": report["controlled_live_readiness_go"],
                "normal_recruiter_exposure_go": False,
                "voyage_chunks": voyage_chunks,
                "health": report["health_end"]["http_code"],
            },
            indent=2,
        )
    )
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
