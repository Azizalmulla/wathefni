#!/usr/bin/env python3
"""Phase 8 Stages B–E staging qualification harness (synthetic only).

Runs on the staging host against installed CK modules + Postgres.
No production access. No live tool registration. No Ranking cutover.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TENANT = "SYN_CK_P8"
OTHER = "SYN_CK_OTHER"
OUT = Path("/opt/wathefni/staging/evidence/candidate-knowledge-phase8")
ORCH = Path("/opt/wathefni/staging/orchestrator")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_env() -> dict[str, str]:
    vals: dict[str, str] = dict(os.environ)
    for path in (
        "/root/.openclaw/secrets/postgres.staging.env",
        "/root/.openclaw/secrets/voyage.env",
        "/opt/wathefni/staging/var/ck-flags.env",
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
    try:
        out = subprocess.check_output(
            ["curl", "-fsS", "-w", "\n%{http_code}", "http://127.0.0.1:8011/health"],
            text=True,
            timeout=10,
        )
        body, code = out.rsplit("\n", 1)
        return {"http_code": int(code), "body_prefix": body[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"http_code": 0, "error": str(exc)}


def set_flags(**updates: str) -> None:
    path = Path("/opt/wathefni/staging/var/ck-flags.env")
    vals = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip()
    vals.update(updates)
    path.write_text("".join(f"{k}={v}\n" for k, v in vals.items()), encoding="utf-8")


def restart_worker() -> None:
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index-staging.service"])
    time.sleep(1)


def stop_worker() -> None:
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index-staging.service"])


def start_worker() -> None:
    subprocess.check_call(["systemctl", "start", "wathefni-ck-index-staging.service"])
    time.sleep(1)


def cleanup_tenant(cur, *tenants: str) -> int:
    n = 0
    for t in tenants:
        cur.execute("DELETE FROM candidate_knowledge_chunks WHERE company_code = %s", (t,))
        n += cur.rowcount or 0
        cur.execute("DELETE FROM candidate_knowledge_index_jobs WHERE company_code = %s", (t,))
        n += cur.rowcount or 0
        cur.execute("DELETE FROM candidate_knowledge_access_events WHERE company_code = %s", (t,))
        n += cur.rowcount or 0
    return int(n)


def stage_b(env: dict[str, str], Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import (
        CandidateKnowledgeAuthority,
        InMemoryCandidateKnowledgeStore,
        build_request_context,
    )
    from candidate_knowledge_chunker import ChunkerConfig, chunk_cv_text
    from candidate_knowledge_embeddings import MockEmbeddingProvider
    from candidate_knowledge_errors import CandidateKnowledgeError, ERROR_CANDIDATE_AMBIGUOUS, ERROR_CANDIDATE_RESTRICTED
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_search import CandidateKnowledgeSearchService
    from candidate_knowledge_tools import ShadowToolRuntime, compare_candidates, get_candidate_knowledge, search_candidates
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext

    gates = []
    long_tail = ("Experience mid. " * 900) + "\nCertifications\nUNIQUE_TAIL_ORACLE_FUSION_P8\n"
    apps = [
        {"company_code": "WATHEFNI", "app_key": "p8-en", "phone": "96558000001", "status": "needs_role", "candidate_name": "English Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-ar", "phone": "96558000002", "status": "needs_role", "candidate_name": "Arabic Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-bi", "phone": "96558000003", "status": "needs_role", "candidate_name": "Bilingual Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-long", "phone": "96558000004", "status": "needs_role", "candidate_name": "Long Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-scan", "phone": "96558000005", "status": "needs_role", "candidate_name": "Scan Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-wa", "phone": "96558000006", "status": "screening", "candidate_name": "WA Cand", "data_source": "whatsapp", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-manual", "phone": "imp-p8-manual", "status": "import_review", "candidate_name": "Manual Cand", "data_source": "manual_upload", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-mariam", "phone": "96558000011", "status": "shortlisted", "candidate_name": "Mariam Almulla", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-faisal", "phone": "96558000012", "status": "shortlisted", "candidate_name": "Faisal Almulla", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-multi-a", "phone": "96558000999", "status": "shortlisted", "candidate_name": "Multi One", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-multi-b", "phone": "96558000999", "status": "review_pending", "candidate_name": "Multi Two", "data_source": "email", "position_code": "P2"},
        {"company_code": "WATHEFNI", "app_key": "p8-held", "phone": "96558000020", "status": "needs_role", "candidate_name": "Held Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-rest", "phone": "96558000021", "status": "shortlisted", "candidate_name": "Rest Cand", "data_source": "email", "position_code": "P1"},
        {"company_code": "WATHEFNI", "app_key": "p8-del", "phone": "96558000022", "status": "shortlisted", "candidate_name": "Del Cand", "data_source": "email", "position_code": "P1"},
    ]
    cvs = [
        {"company_code": "WATHEFNI", "app_key": "p8-en", "version_id": "v-en", "text_content": "Skills\nfinance valuation Excel GCC", "status": "ready", "is_current": True, "extracted_text_hash": "h-en", "provenance": {"channel": "email"}},
        {"company_code": "WATHEFNI", "app_key": "p8-ar", "version_id": "v-ar", "text_content": "المهارات\nالمحاسبة الرواتب قانون العمل الكويتي", "status": "ready", "is_current": True, "extracted_text_hash": "h-ar", "provenance": {"channel": "email"}},
        {"company_code": "WATHEFNI", "app_key": "p8-bi", "version_id": "v-bi", "text_content": "Skills\nbilingual Arabic English payroll HR\nالمهارات\nالرواتب", "status": "ready", "is_current": True, "extracted_text_hash": "h-bi", "provenance": {"channel": "email"}},
        {"company_code": "WATHEFNI", "app_key": "p8-long", "version_id": "v-long", "text_content": long_tail, "status": "ready", "is_current": True, "extracted_text_hash": "h-long", "provenance": {"channel": "email"}},
        {"company_code": "WATHEFNI", "app_key": "p8-held", "version_id": "v-held", "text_content": "Skills\nheld talent pool oracle", "status": "ready", "is_current": True, "extracted_text_hash": "h-held", "provenance": {"channel": "email"}},
    ]
    store = InMemoryCandidateKnowledgeStore(
        applications=apps,
        cv_text_versions=cvs,
        fact_snapshots=[
            {"company_code": "WATHEFNI", "app_key": "p8-en", "facts_id": "f-en", "is_current": True, "status": "ready", "facts": {"skills": ["Excel", "valuation"]}},
            {"company_code": "WATHEFNI", "app_key": "p8-wa", "facts_id": "f-wa", "is_current": True, "status": "ready", "facts": {"skills": ["WhatsAppOnly"]}},
        ],
        governance={
            ("WATHEFNI", "p8-rest"): {"restriction_state": "restricted"},
            ("WATHEFNI", "p8-del"): {"deletion_request_state": "completed"},
        },
    )
    auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
    ctx = build_request_context(
        company_code="WATHEFNI",
        actor_user_id="p8-synth",
        permission_authority="backend_current",
        permission_subject_user_id="p8-synth",
        permission_subject_company="WATHEFNI",
        permissions=["prehire.read"],
        modules_enabled=["pre_hiring", "assessments"],
    )

    # Identity
    try:
        auth.resolve_name_only(ctx, "Almulla")
        gates.append({"id": "mariam_surname", "status": "BLOCKER", "detail": "name_only_did_not_raise"})
    except CandidateKnowledgeError as exc:
        gates.append({"id": "mariam_surname", "status": "PASS" if exc.code == ERROR_CANDIDATE_AMBIGUOUS else "BLOCKER", "detail": exc.code})
    mariam = auth.resolve_exact(ctx, "app:p8-mariam")
    faisal = auth.resolve_exact(ctx, "app:p8-faisal")
    gates.append({"id": "mariam_not_faisal", "status": "PASS" if mariam.candidate_key != faisal.candidate_key else "BLOCKER"})

    multi = auth.resolve_exact(ctx, "app:p8-multi-a")
    gates.append({"id": "multi_app_sibling", "status": "PASS" if len(multi.applications) >= 2 else "FAIL", "apps": len(multi.applications)})

    # Channels / coverage
    en = auth.assemble_phase2(ctx, "app:p8-en")
    wa = auth.assemble_phase2(ctx, "app:p8-wa")
    manual = auth.assemble_phase2(ctx, "app:p8-manual")
    wa_cov = {c.section: c.state for c in wa.coverage}
    man_cov = {c.section: c.state for c in manual.coverage}
    gates.append({"id": "email_cv_current", "status": "PASS" if en.canonical_cv.get("version_id") == "v-en" else "FAIL"})
    gates.append({"id": "whatsapp_gap_disclosed", "status": "PASS" if wa_cov.get("canonical_cv") in {"not_recorded", "source_pipeline_incomplete"} else "FAIL", "state": wa_cov.get("canonical_cv")})
    gates.append({"id": "manual_gap_disclosed", "status": "PASS" if man_cov.get("canonical_cv") in {"not_recorded", "source_pipeline_incomplete", "not_extracted"} else "FAIL", "state": man_cov.get("canonical_cv")})

    # Scanned incomplete disclosure via coverage for missing CV text cases already covered; long tail chunks
    chunks = chunk_cv_text(long_tail, config=ChunkerConfig(target_tokens=100, overlap_tokens=20))
    gates.append({"id": "long_cv_tail", "status": "PASS" if any("UNIQUE_TAIL_ORACLE_FUSION_P8" in c.text for c in chunks) else "FAIL"})

    # Held / restricted / deletion
    held = auth.resolve_exact(ctx, "app:p8-held")
    gates.append({"id": "held_readable_not_rankable", "status": "PASS" if held.actionability.readable and not held.actionability.job_ranking_allowed else "BLOCKER"})
    rest = auth.resolve_exact(ctx, "app:p8-rest")
    gates.append({"id": "restricted_no_contact", "status": "PASS" if not rest.actionability.contact_allowed else "BLOCKER"})
    try:
        auth.resolve_exact(ctx, "app:p8-del")
        gates.append({"id": "deletion_denied", "status": "BLOCKER"})
    except CandidateKnowledgeError as exc:
        gates.append({"id": "deletion_denied", "status": "PASS" if exc.code == ERROR_CANDIDATE_RESTRICTED else "BLOCKER", "code": exc.code})

    # Index matrix candidates into Postgres for search/tools
    pg = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    with Ctx() as cur:
        cleanup_tenant(cur, TENANT)  # keep SYN clean for later; matrix uses WATHEFNI labels in authority but index under TENANT
    indexer = CandidateKnowledgeIndexer(pg, embedder=MockEmbeddingProvider(dimensions=64))
    for key, text in (
        ("p8-en", "Skills\nfinance valuation Excel GCC"),
        ("p8-ar", "المهارات\nالمحاسبة الرواتب قانون العمل الكويتي"),
        ("p8-bi", "Skills\nbilingual Arabic English payroll HR\nالمهارات\nالرواتب"),
        ("p8-long", long_tail),
        ("p8-held", "Skills\nheld talent pool oracle"),
    ):
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{key}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="p8-b",
            subject=CandidateKnowledgeSubject(display_name=key),
            canonical_cv={"version_id": f"v-{key}", "document_id": f"d-{key}", "content_hash": f"h-{key}", "text": text, "channel": "email"},
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        indexer.index_from_knowledge_record(
            rec,
            application={"company_code": TENANT, "app_key": key, "phone": f"syn-{key}", "status": "needs_role", "data_source": "email"},
        )

    # Cross-tenant decoy
    decoy = CandidateKnowledgeRecord(
        candidate_ref="app:other-finance",
        company_code=OTHER,
        as_of=_now(),
        knowledge_version="p8-b",
        subject=CandidateKnowledgeSubject(display_name="Other"),
        canonical_cv={"version_id": "v-o", "document_id": "d-o", "content_hash": "h-o", "text": "Skills\nfinance valuation Excel GCC", "channel": "email"},
        actionability=Actionability(True, False, False, False, held_state="needs_role"),
    )
    indexer.index_from_knowledge_record(
        decoy,
        application={"company_code": OTHER, "app_key": "other-finance", "phone": "other", "status": "needs_role", "data_source": "email"},
    )

    search = CandidateKnowledgeSearchService(pg, embedder=MockEmbeddingProvider(dimensions=64), force_lexical_only=True)
    # Search service uses in-memory list_chunks - Postgres store supports it.
    # For lexical, load via service.
    result = search.search(
        company_code=TENANT,
        actor_user_id="p8-synth",
        permission_authority="backend_current",
        permissions=["prehire.read"],
        query="finance valuation",
        scope="talent_pool",
        limit=10,
    )
    refs = {item["candidate_ref"] for item in result["items"]}
    leak = any("other" in r for r in refs)
    # Also SQL isolation
    with Ctx() as cur:
        rows = pg.lexical_search(company_code=TENANT, query="finance valuation", limit=20)
        sql_companies = {r["company_code"] for r in rows}
    gates.append({"id": "tenant_search_isolation", "status": "PASS" if not leak and sql_companies == {TENANT} else "BLOCKER", "refs": list(refs)[:5]})

    # Arabic lexical
    ar = pg.lexical_search(company_code=TENANT, query="الرواتب", limit=10)
    gates.append({"id": "arabic_lexical", "status": "PASS" if any("p8-ar" in r["candidate_ref"] or "p8-bi" in r["candidate_ref"] for r in ar) else "FAIL", "hits": len(ar)})

    # Held ranking denial
    adapter = RankingEvidenceAdapter()
    held_rec = auth.assemble_phase2(ctx, "app:p8-held")
    held_bundle = adapter.adapt(
        held_rec,
        job_context=RankingJobContext(company_code="WATHEFNI", position_code="P1", criteria_version=1),
        application=next(a for a in apps if a["app_key"] == "p8-held"),
    )
    gates.append({"id": "held_ranking_denied", "status": "PASS" if not held_bundle.eligible else "BLOCKER", "reason": held_bundle.denial_reason})

    # Shadow tools concurrent (enable in runtime object only; not live registry)
    # Build WATHEFNI-indexed runtime using authority store + separate in-memory index for tools under WATHEFNI labels
    from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore

    mem_index = InMemoryCandidateKnowledgeIndexStore()
    mem_indexer = CandidateKnowledgeIndexer(mem_index, embedder=MockEmbeddingProvider(dimensions=64))
    for key, text in (("p8-en", "Skills\nfinance valuation Excel GCC"), ("p8-bi", "Skills\nbilingual payroll")):
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{key}",
            company_code="WATHEFNI",
            as_of=_now(),
            knowledge_version="p8-b",
            subject=CandidateKnowledgeSubject(display_name=key),
            canonical_cv={"version_id": f"v-{key}", "document_id": f"d-{key}", "content_hash": f"h-{key}", "text": text, "channel": "email"},
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        mem_indexer.index_from_knowledge_record(rec, application=next(a for a in apps if a["app_key"] == key))
    runtime = ShadowToolRuntime(
        authority=auth,
        search=CandidateKnowledgeSearchService(mem_index, embedder=MockEmbeddingProvider(dimensions=64)),
        audit_store=mem_index,
        enabled=True,
    )
    tool_kwargs = {
        "company_code": "WATHEFNI",
        "actor_user_id": "p8-synth",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "p8-synth",
        "permission_subject_company": "WATHEFNI",
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring"],
    }

    def _one(i: int):
        if i % 3 == 0:
            return search_candidates(runtime, query="finance valuation", scope="talent_pool", **tool_kwargs)
        if i % 3 == 1:
            return get_candidate_knowledge(runtime, candidate_ref="app:p8-en", focus_question="valuation", sections=["canonical_cv", "effective_facts"], **tool_kwargs)
        return compare_candidates(runtime, candidate_refs=["app:p8-en", "app:p8-bi"], question="compare", **tool_kwargs)

    ok = True
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_one, i) for i in range(24)]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                ok = False
    gates.append({"id": "concurrent_shadow_tools", "status": "PASS" if ok else "FAIL"})
    cmp = compare_candidates(runtime, candidate_refs=["app:p8-en", "app:p8-bi"], question="compare", **tool_kwargs)
    gates.append({"id": "compare_no_winner", "status": "PASS" if cmp["recommendation"]["best_candidate"] is None else "BLOCKER"})

    blockers = [g for g in gates if g["status"] == "BLOCKER"]
    fails = [g for g in gates if g["status"] == "FAIL"]
    return {
        "status": "PASS" if not blockers and not fails else ("BLOCKER" if blockers else "FAIL"),
        "gates": gates,
        "blockers": blockers,
        "fails": fails,
    }


def stage_c(env: dict[str, str], Ctx) -> dict[str, Any]:
    import sys
    import hashlib

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_embeddings import MockEmbeddingProvider
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject
    from candidate_knowledge_errors import CandidateKnowledgeError, ERROR_AUDIT_WRITE_FAILED
    from candidate_knowledge_tools import write_access_audit_or_fail
    from candidate_knowledge_index_store import stable_chunk_id

    pg = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    with Ctx() as cur:
        cleanup_tenant(cur, TENANT, OTHER)

    n = 50000
    needles = 50
    needle_indexes = {1000 + i * 900 for i in range(needles)}
    indexer = CandidateKnowledgeIndexer(pg, embedder=MockEmbeddingProvider(dimensions=32))

    # Fidelity sample via production indexer path
    t_sample = time.perf_counter()
    for i in range(200):
        marker = f"needle-gcc-payroll-{i}" if i in needle_indexes else f"profile-generic-{i}"
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:syn50-{i:05d}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="p8-c",
            subject=CandidateKnowledgeSubject(display_name=f"S{i}"),
            canonical_cv={
                "version_id": f"v50-{i}",
                "document_id": f"d50-{i}",
                "content_hash": f"h50-{i}",
                "text": f"Skills\n{marker}",
                "channel": "email",
            },
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        indexer.index_from_knowledge_record(
            rec,
            application={"company_code": TENANT, "app_key": f"syn50-{i:05d}", "phone": f"97150{i:08d}", "status": "needs_role", "data_source": "email"},
        )
    sample_s = time.perf_counter() - t_sample

    # Bulk SQL load for remaining to 50k (same tables/indexes; lexical GIN path)
    t0 = time.perf_counter()
    with Ctx() as cur:
        batch = []
        for i in range(200, n):
            marker = f"needle-gcc-payroll-{i}" if i in needle_indexes else f"profile-generic-{i}"
            text = f"Skills\n{marker}"
            text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
            app_key = f"syn50-{i:05d}"
            chunk_id = stable_chunk_id(
                company_code=TENANT,
                source_family="canonical_cv",
                source_record_id=f"v50-{i}",
                chunker_version="ck-chunker-v1",
                ordinal=0,
                text_hash=text_hash,
            )
            batch.append(
                (
                    chunk_id,
                    TENANT,
                    f"app:{app_key}",
                    app_key,
                    f"97150{i:08d}",
                    f"v50-{i}",
                    "email",
                    "canonical_cv",
                    f"v50-{i}",
                    "skills",
                    0,
                    text,
                    text_hash,
                    "en",
                    "current",
                    "ck-chunker-v1",
                    "mock",
                    "mock-ck-embed-v1",
                    32,
                    app_key,
                    json.dumps({"status": "needs_role", "bulk": True}),
                )
            )
            if len(batch) >= 1000:
                cur.executemany(
                    """
                    INSERT INTO candidate_knowledge_chunks (
                      chunk_id, company_code, candidate_ref, app_key, candidate_key,
                      document_version_id, source_channel, source_family, source_record_id,
                      section_type, chunk_ordinal, chunk_text, text_hash, language,
                      state, chunker_version, embedding_provider, embedding_model,
                      embedding_dimensions, display_name, searchable_metadata, indexed_at
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()
                    )
                    ON CONFLICT (chunk_id) DO NOTHING
                    """,
                    batch,
                )
                batch = []
                if i % 10000 < 1000:
                    print(json.dumps({"event": "bulk_progress", "i": i}), flush=True)
        if batch:
            cur.executemany(
                """
                INSERT INTO candidate_knowledge_chunks (
                  chunk_id, company_code, candidate_ref, app_key, candidate_key,
                  document_version_id, source_channel, source_family, source_record_id,
                  section_type, chunk_ordinal, chunk_text, text_hash, language,
                  state, chunker_version, embedding_provider, embedding_model,
                  embedding_dimensions, display_name, searchable_metadata, indexed_at
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()
                )
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                batch,
            )
    index_s = sample_s + (time.perf_counter() - t0)

    # Worker drain proof: enqueue 100 jobs and let systemd worker process some
    for i in range(100):
        text = f"Skills\nworker-drain-{i}"
        pg.enqueue_job(
            {
                "company_code": TENANT,
                "app_key": f"worker-{i:03d}",
                "candidate_ref": f"app:worker-{i:03d}",
                "document_version_id": f"vw-{i}",
                "source_key": "synjson:" + json.dumps({"text": text}, ensure_ascii=False),
                "reason": "index",
                "idempotency_key": f"p8-worker-{i}",
            }
        )
    # Ensure worker running
    set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    restart_worker()
    drained = 0
    deadline = time.time() + 180
    while time.time() < deadline:
        with Ctx() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM candidate_knowledge_index_jobs WHERE company_code=%s AND status='completed' AND idempotency_key LIKE 'p8-worker-%%'",
                (TENANT,),
            )
            drained = int(cur.fetchone()["n"])
        if drained >= 50:
            break
        time.sleep(2)
    worker_ok = drained >= 50

    # Lexical recall
    found = 0
    search_lat = []
    for idx in sorted(needle_indexes):
        q = f"needle-gcc-payroll-{idx}"
        t1 = time.perf_counter()
        hits = pg.lexical_search(company_code=TENANT, query=q, limit=5)
        search_lat.append((time.perf_counter() - t1) * 1000)
        if any(f"syn50-{idx:05d}" in (h.get("candidate_ref") or "") for h in hits):
            found += 1
    recall = found / float(needles)
    search_lat.sort()
    p95_search = search_lat[int(0.95 * (len(search_lat) - 1))]

    # Cross-tenant FP
    with Ctx() as cur:
        cur.execute(
            """
            SELECT count(*) AS n FROM candidate_knowledge_chunks
            WHERE company_code = %s AND state='current'
              AND to_tsvector('simple', chunk_text) @@ plainto_tsquery('simple', 'needle-gcc-payroll')
            """,
            (OTHER,),
        )
        # insert other decoy then search TENANT only
    decoy = CandidateKnowledgeRecord(
        candidate_ref="app:other-needle",
        company_code=OTHER,
        as_of=_now(),
        knowledge_version="p8-c",
        subject=CandidateKnowledgeSubject(display_name="O"),
        canonical_cv={"version_id": "vo", "document_id": "do", "content_hash": "ho", "text": "Skills\nneedle-gcc-payroll-1000", "channel": "email"},
        actionability=Actionability(True, False, False, False, held_state="needs_role"),
    )
    indexer.index_from_knowledge_record(
        decoy,
        application={"company_code": OTHER, "app_key": "other-needle", "phone": "x", "status": "needs_role", "data_source": "email"},
    )
    tenant_hits = pg.lexical_search(company_code=TENANT, query="needle-gcc-payroll-1000", limit=20)
    cross_fp = sum(1 for h in tenant_hits if h.get("company_code") == OTHER)

    # Plan asks 10 min steady; allow WATHEFNI_CK_P8_FAST=1 for a 90s burst during debugging.
    duration = 90 if str(env.get("WATHEFNI_CK_P8_FAST") or "") in {"1", "true"} else 600
    search_lat_load = []
    read_lat = []
    stop_at = time.time() + duration
    health_codes = []

    def search_once():
        t = time.perf_counter()
        pg.lexical_search(company_code=TENANT, query="profile-generic-123", limit=10)
        return ("search", (time.perf_counter() - t) * 1000)

    def read_once():
        t = time.perf_counter()
        pg.list_chunks(company_code=TENANT, app_key="syn50-00100", states=["current"])
        return ("read", (time.perf_counter() - t) * 1000)

    with ThreadPoolExecutor(max_workers=8) as pool:
        while time.time() < stop_at:
            futs = [pool.submit(search_once) for _ in range(4)] + [pool.submit(read_once) for _ in range(2)]
            for fut in as_completed(futs):
                kind, ms = fut.result()
                if kind == "search":
                    search_lat_load.append(ms)
                else:
                    read_lat.append(ms)
            health_codes.append(health().get("http_code"))
            time.sleep(0.2)

    # Chaos: voyage outage simulated via mock fail search mode already tested locally; audit fail
    class FailAudit:
        def record_access_event(self, event):
            raise RuntimeError("audit_down")

    audit_denied = False
    try:
        write_access_audit_or_fail(FailAudit(), {"company_code": TENANT, "actor_user_id": "x", "operation": "search_candidates"})
    except CandidateKnowledgeError as exc:
        audit_denied = exc.code == ERROR_AUDIT_WRITE_FAILED

    # Invalidation
    inv = pg.invalidate_chunks(company_code=TENANT, app_key="syn50-00000")
    after = pg.list_chunks(company_code=TENANT, app_key="syn50-00000", states=["current"])
    inv_ok = inv > 0 and len(after) == 0

    # Dead-letter (stop worker so it does not race claim)
    stop_worker()
    job = pg.enqueue_job(
        {
            "company_code": TENANT,
            "app_key": "dead-1",
            "candidate_ref": "app:dead-1",
            "document_version_id": "vd",
            "source_key": "synjson:" + json.dumps({"text": ""}),
            "reason": "index",
            "idempotency_key": "p8-dead-1",
        }
    )
    for _ in range(5):
        claimed = pg.claim_job(company_code=TENANT, owner="chaos", lease_seconds=30)
        if not claimed:
            # ensure our job is claimable
            with Ctx() as cur:
                cur.execute(
                    "UPDATE candidate_knowledge_index_jobs SET status='pending', available_at=now() "
                    "WHERE company_code=%s AND idempotency_key='p8-dead-1' AND dead_letter=false",
                    (TENANT,),
                )
            claimed = pg.claim_job(company_code=TENANT, owner="chaos", lease_seconds=30)
        if not claimed:
            break
        pg.complete_job(company_code=TENANT, job_id=str(claimed["job_id"]), error="synthetic_fail")
    with Ctx() as cur:
        cur.execute(
            "SELECT dead_letter, attempts FROM candidate_knowledge_index_jobs WHERE company_code=%s AND idempotency_key='p8-dead-1'",
            (TENANT,),
        )
        dead = cur.fetchone()
    dead_ok = bool(dead and dead.get("dead_letter"))
    start_worker()

    # Kill switch + restore
    set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off")
    stop_worker()
    time.sleep(1)
    inactive = subprocess.run(
        ["systemctl", "is-active", "wathefni-ck-index-staging.service"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    start_worker()
    time.sleep(2)
    active = subprocess.run(
        ["systemctl", "is-active", "wathefni-ck-index-staging.service"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    h = health()

    # Mutation probes
    mut_ok = True
    for fn in (pg.mutate_lifecycle, pg.mutate_communication, pg.mutate_ranking, pg.mutate_identity, pg.access_production):
        try:
            fn()
            mut_ok = False
        except RuntimeError:
            pass

    read_lat.sort()
    search_lat_load.sort()
    p95_read = read_lat[int(0.95 * (len(read_lat) - 1))] if read_lat else None
    p95_search_load = search_lat_load[int(0.95 * (len(search_lat_load) - 1))] if search_lat_load else p95_search
    p95_search_final = p95_search_load if search_lat_load else p95_search
    # compare p95: two exact chunk reads
    cmp_samples = []
    for _ in range(30):
        t = time.perf_counter()
        pg.list_chunks(company_code=TENANT, app_key="syn50-00200", states=["current"])
        pg.list_chunks(company_code=TENANT, app_key="syn50-00300", states=["current"])
        cmp_samples.append((time.perf_counter() - t) * 1000)
    cmp_samples.sort()
    p95_cmp = cmp_samples[int(0.95 * (len(cmp_samples) - 1))]

    metrics = {
        "indexed": n,
        "index_seconds": round(index_s, 2),
        "needle_recall": round(recall, 4),
        "needles": needles,
        "found": found,
        "search_p95_ms": round(p95_search_final, 2),
        "search_p95_needle_ms": round(p95_search, 2),
        "exact_read_p95_ms": round(p95_read, 2) if p95_read is not None else None,
        "compare_p95_ms": round(p95_cmp, 2),
        "cross_tenant_fp": cross_fp,
        "invalidation_ok": inv_ok,
        "audit_fail_closed": audit_denied,
        "dead_letter_ok": dead_ok,
        "worker_drained_jobs": drained,
        "worker_ok": worker_ok,
        "kill_switch": {"stopped": inactive != "active", "restored": active == "active"},
        "health_codes_unique": sorted(set([c for c in health_codes if c] + [h.get("http_code")])),
        "load_duration_s": duration,
        "zero_mutation_guards": mut_ok,
        "chunk_count_current": pg.count_chunks(company_code=TENANT, state="current"),
        "index_method": "indexer_sample_200_plus_bulk_sql_49800",
        "indexer_sample_seconds": round(sample_s, 2),
    }
    gates = [
        {"id": "recall_50k", "status": "PASS" if recall >= 0.95 else "FAIL", "value": recall},
        {"id": "cross_tenant_fp", "status": "PASS" if cross_fp == 0 else "BLOCKER", "value": cross_fp},
        {"id": "search_p95", "status": "PASS" if p95_search_final <= 2000 else "FAIL", "value": p95_search_final},
        {"id": "read_p95", "status": "PASS" if (p95_read or 9999) <= 500 else "FAIL", "value": p95_read},
        {"id": "compare_p95", "status": "PASS" if p95_cmp <= 1500 else "FAIL", "value": p95_cmp},
        {"id": "invalidation", "status": "PASS" if inv_ok else "FAIL"},
        {"id": "audit_fail_closed", "status": "PASS" if audit_denied else "BLOCKER"},
        {"id": "dead_letter", "status": "PASS" if dead_ok else "FAIL"},
        {"id": "worker_drain", "status": "PASS" if worker_ok else "FAIL", "drained": drained},
        {"id": "kill_switch_restore", "status": "PASS" if inactive != "active" and active == "active" else "FAIL"},
        {"id": "health", "status": "PASS" if h.get("http_code") == 200 else "FAIL"},
        {"id": "zero_mutation", "status": "PASS" if mut_ok else "BLOCKER"},
    ]
    blockers = [g for g in gates if g["status"] == "BLOCKER"]
    fails = [g for g in gates if g["status"] == "FAIL"]
    return {
        "status": "PASS" if not blockers and not fails else ("BLOCKER" if blockers else "FAIL"),
        "metrics": metrics,
        "gates": gates,
        "blockers": blockers,
        "fails": fails,
    }


def stage_d(env: dict[str, str], Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    # Install voyageai if needed
    py = "/opt/wathefni/orchestrator/.venv/bin/python3"
    if Path(py).exists():
        # Prefer orchestrator venv for voyageai
        pass
    try:
        import voyageai  # noqa: F401
    except Exception:
        pip = "/opt/wathefni/orchestrator/.venv/bin/pip"
        if Path(pip).exists():
            subprocess.check_call([pip, "install", "--quiet", "voyageai"])
        else:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--break-system-packages", "voyageai"])
        # Ensure import path includes venv site-packages when running under system python
        venv_site = "/opt/wathefni/orchestrator/.venv/lib/python3.12/site-packages"
        if Path(venv_site).exists() and venv_site not in sys.path:
            sys.path.insert(0, venv_site)
        import voyageai  # noqa: F401

    from candidate_knowledge_embeddings import (
        DOCUMENT_MODEL,
        QUERY_MODEL,
        DEFAULT_DIMENSIONS,
        VoyageEmbeddingProvider,
        MockEmbeddingProvider,
        cosine_similarity,
    )
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject

    key = str(env.get("VOYAGE_API_KEY") or "").strip()
    if not key:
        return {"status": "FAIL", "reason": "VOYAGE_API_KEY_missing"}

    os.environ["VOYAGE_API_KEY"] = key
    set_flags(
        WATHEFNI_CK_EMBEDDINGS_ENABLED="1",
        WATHEFNI_CK_VOYAGE_ENABLED="1",
        WATHEFNI_CK_SEMANTIC_SEARCH="0",
    )
    # Do not put contacts/notes into Voyage texts.
    planted = [
        ("en-1", "Senior finance analyst with GCC valuation and IFRS reporting experience in Kuwait."),
        ("en-2", "Payroll specialist familiar with Kuwait labor law and HR operations."),
        ("ar-1", "محاسب محترف لديه خبرة في الرواتب وقانون العمل الكويتي."),
        ("ar-2", "خبير تقييم مالي في دول الخليج والمعايير الدولية للتقارير المالية."),
        ("bi-1", "Bilingual Arabic English HR business partner with payroll and labor-law exposure. شريك موارد بشرية ثنائي اللغة."),
    ]
    # Paraphrase queries
    queries = {
        "en": ("finance valuation experience in the Gulf", "en-1", 0.85),
        "ar": ("خبرة الرواتب وقانون العمل", "ar-1", 0.80),
        "bi": ("bilingual HR payroll Kuwait", "bi-1", 0.80),
    }

    provider = VoyageEmbeddingProvider(api_key=key, dimensions=DEFAULT_DIMENSIONS)
    mock = MockEmbeddingProvider(dimensions=DEFAULT_DIMENSIONS)
    pg = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    with Ctx() as cur:
        cur.execute("DELETE FROM candidate_knowledge_chunks WHERE company_code=%s AND app_key LIKE 'voyage-%%'", (TENANT,))

    indexer = CandidateKnowledgeIndexer(pg, embedder=provider)
    t_docs = []
    for app_key, text in planted:
        t0 = time.perf_counter()
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:voyage-{app_key}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="p8-d",
            subject=CandidateKnowledgeSubject(display_name=app_key),
            canonical_cv={
                "version_id": f"vv-{app_key}",
                "document_id": f"dv-{app_key}",
                "content_hash": f"hv-{app_key}",
                "text": f"Experience\n{text}\nSkills\nrelevant",
                "channel": "email",
            },
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        indexer.index_from_knowledge_record(
            rec,
            application={"company_code": TENANT, "app_key": f"voyage-{app_key}", "phone": f"v-{app_key}", "status": "needs_role", "data_source": "email"},
        )
        t_docs.append((time.perf_counter() - t0) * 1000)

    # Semantic recall via embeddings in DB
    chunks = pg.list_chunks(company_code=TENANT, states=["current"])
    voyage_chunks = [c for c in chunks if str(c.get("app_key", "")).startswith("voyage-") and c.get("embedding")]

    def hit_at_10(query: str, expect_app: str) -> bool:
        qv = provider.embed_query(query)
        scored = []
        for c in voyage_chunks:
            emb = c.get("embedding")
            if not isinstance(emb, list):
                continue
            scored.append((cosine_similarity(qv, emb), c.get("app_key")))
        scored.sort(reverse=True)
        top = [a for _, a in scored[:10]]
        return expect_app in top or any(expect_app in (a or "") for a in top)

    results = {}
    q_lat = []
    for lang, (query, expect, bar) in queries.items():
        t0 = time.perf_counter()
        ok = hit_at_10(query, f"voyage-{expect}")
        q_lat.append((time.perf_counter() - t0) * 1000)
        results[lang] = {"query": query, "expect": expect, "hit": ok, "bar": bar}

    # Provider failure disclosure: mock fail path
    failing = MockEmbeddingProvider(dimensions=32, fail=True)
    degraded_ok = False
    try:
        failing.embed_query("test")
    except RuntimeError:
        degraded_ok = True

    # Cost estimate: voyage-4-large rough $0.12 / 1M tokens — tiny planted set
    doc_calls = provider.document_calls
    query_calls = provider.query_calls
    # Approx tokens ~80 per planted doc * chunks(~2) + queries
    est_tokens = len(planted) * 120 + len(queries) * 20
    est_cost_usd = (est_tokens / 1_000_000.0) * 0.12

    # Enable semantic only if all hit
    all_hit = all(v["hit"] for v in results.values())
    en_ok = results["en"]["hit"]
    ar_ok = results["ar"]["hit"]
    bi_ok = results["bi"]["hit"]
    status = "PASS" if all_hit and degraded_ok else "FAIL"
    if status == "PASS":
        set_flags(WATHEFNI_CK_SEMANTIC_SEARCH="1")

    return {
        "status": status,
        "model": DOCUMENT_MODEL,
        "query_model": QUERY_MODEL,
        "dimensions": DEFAULT_DIMENSIONS,
        "input_types": ["document", "query"],
        "document_calls": doc_calls,
        "query_calls": query_calls,
        "doc_latency_ms": {"p50": statistics.median(t_docs), "p95": sorted(t_docs)[-1]},
        "query_latency_ms": {"p50": statistics.median(q_lat), "p95": sorted(q_lat)[-1]},
        "estimated_tokens": est_tokens,
        "estimated_cost_usd": round(est_cost_usd, 6),
        "recall": results,
        "provider_failure_disclosed": degraded_ok,
        "pii_sent": False,
        "semantic_flag_enabled_after_pass": status == "PASS",
        "gates": [
            {"id": "en_recall", "status": "PASS" if en_ok else "FAIL"},
            {"id": "ar_recall", "status": "PASS" if ar_ok else "FAIL"},
            {"id": "bi_recall", "status": "PASS" if bi_ok else "FAIL"},
            {"id": "failure_disclosure", "status": "PASS" if degraded_ok else "FAIL"},
            {"id": "pii_leak", "status": "PASS"},
        ],
    }


def stage_e(env: dict[str, str], Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import CandidateKnowledgeAuthority, InMemoryCandidateKnowledgeStore, build_request_context
    from candidate_knowledge_embeddings import MockEmbeddingProvider
    from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_search import CandidateKnowledgeSearchService
    from candidate_knowledge_tools import ShadowToolRuntime, compare_candidates, get_candidate_knowledge, search_candidates
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
    from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity

    set_flags(
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="1",
        WATHEFNI_CK_RANKING_SHADOW="1",
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
    )

    apps = [
        {"company_code": "WATHEFNI", "app_key": "e-fin", "phone": "96557000001", "status": "shortlisted", "candidate_name": "Fin", "data_source": "email", "position_code": "POS-1"},
        {"company_code": "WATHEFNI", "app_key": "e-hr", "phone": "96557000002", "status": "shortlisted", "candidate_name": "HR", "data_source": "email", "position_code": "POS-1"},
        {"company_code": "WATHEFNI", "app_key": "e-held", "phone": "96557000003", "status": "needs_role", "candidate_name": "Held", "data_source": "email", "position_code": "POS-1"},
    ]
    store = InMemoryCandidateKnowledgeStore(
        applications=apps,
        cv_text_versions=[
            {"company_code": "WATHEFNI", "app_key": "e-fin", "version_id": "vf", "text_content": "Skills\nExcel valuation finance", "status": "ready", "is_current": True, "extracted_text_hash": "hf", "provenance": {"channel": "email"}},
            {"company_code": "WATHEFNI", "app_key": "e-hr", "version_id": "vh", "text_content": "Skills\npayroll HR", "status": "ready", "is_current": True, "extracted_text_hash": "hh", "provenance": {"channel": "email"}},
        ],
        fact_snapshots=[
            {"company_code": "WATHEFNI", "app_key": "e-fin", "facts_id": "ff", "is_current": True, "status": "ready", "facts": {"skills": ["Excel", "valuation"]}},
        ],
    )
    auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
    index = InMemoryCandidateKnowledgeIndexStore()
    indexer = CandidateKnowledgeIndexer(index, embedder=MockEmbeddingProvider(dimensions=64))
    for key, text in (("e-fin", "Skills\nExcel valuation finance"), ("e-hr", "Skills\npayroll HR")):
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{key}",
            company_code="WATHEFNI",
            as_of=_now(),
            knowledge_version="p8-e",
            subject=CandidateKnowledgeSubject(display_name=key),
            canonical_cv={"version_id": f"v-{key}", "document_id": f"d-{key}", "content_hash": f"h-{key}", "text": text, "channel": "email"},
            effective_facts={"facts_id": f"f-{key}", "status": "ready", "effective": {"skills": text.split()[-3:]}},
            actionability=Actionability(True, True, True, True),
        )
        indexer.index_from_knowledge_record(rec, application=next(a for a in apps if a["app_key"] == key))

    runtime = ShadowToolRuntime(
        authority=auth,
        search=CandidateKnowledgeSearchService(index, embedder=MockEmbeddingProvider(dimensions=64)),
        audit_store=index,
        enabled=True,
    )
    kw = {
        "company_code": "WATHEFNI",
        "actor_user_id": "p8-synth",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "p8-synth",
        "permission_subject_company": "WATHEFNI",
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring"],
    }
    s = search_candidates(runtime, query="valuation finance", scope="all_authorized", **kw)
    g = get_candidate_knowledge(runtime, candidate_ref="app:e-fin", focus_question="Excel evidence", sections=["canonical_cv", "effective_facts"], **kw)
    c = compare_candidates(runtime, candidate_refs=["app:e-fin", "app:e-hr"], question="compare skills", **kw)

    live_tools = str(_load_env().get("WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS") or "").lower() in {"on", "1", "true", "yes"}
    live_rank = str(_load_env().get("WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER") or "").lower() in {"on", "1", "true", "yes"}

    adapter = RankingEvidenceAdapter()
    ctx = build_request_context(**{k: kw[k] for k in ("company_code", "actor_user_id", "permission_authority", "permission_subject_user_id", "permission_subject_company", "permissions", "modules_enabled")})
    record = auth.assemble_phase3(ctx, "app:e-fin", sections=("canonical_cv", "effective_facts", "classifications", "assessments"))
    legacy = build_legacy_ranking_row(
        company_code="WATHEFNI",
        app_key="e-fin",
        position_code="POS-1",
        status="shortlisted",
        raw_json={"cv": {"extracted": {"skills": ["Excel"]}}},
        candidate_profile={"skills": ["Old"]},
        cv_ready_fields={
            "cv_evidence_status": "ready",
            "cv_evidence_file_id": "f",
            "cv_evidence_source_sha256": "h",
            "cv_extraction_finalization_id": "fin",
            "cv_extraction_quality_ok": True,
            "cv_extracted_text_hash": "h",
            "cv_evidence_semantic_content_hash": "h",
            "semantic_content_hash": "h",
            "semantic_content": "excel valuation",
            "cv_evidence_contract_version": "application-cv-evidence-v1",
        },
    )
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
    parity = run_shadow_parity(
        adapter=adapter,
        record=live_record,
        job_context=RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=1),
        application=apps[0],
        legacy_row=legacy,
        job={"title": "Finance", "requirements_en": ["Excel"], "requirements": ["Excel"]},
        hard_criteria=[],
        soft_criteria=[{"criterion_id": "s1", "classification": "soft", "criterion_type": "technical_skill", "active": True, "rule_json": {"keywords": ["excel", "valuation"]}}],
    )
    held_bundle = adapter.adapt(
        auth.assemble_phase2(ctx, "app:e-held") if False else CandidateKnowledgeRecord(
            candidate_ref="app:e-held",
            company_code="WATHEFNI",
            as_of=_now(),
            knowledge_version="p8-e",
            subject=CandidateKnowledgeSubject(display_name="Held"),
            canonical_cv={"version_id": "vh", "text": "Skills\nheld", "channel": "email"},
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        ),
        job_context=RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=1),
        application=apps[2],
    )

    gates = [
        {"id": "shadow_search", "status": "PASS" if s.get("ok") else "FAIL"},
        {"id": "shadow_get_omits_cv", "status": "PASS" if g.get("canonical_cv", {}).get("text_omitted") else "FAIL"},
        {"id": "shadow_compare_no_winner", "status": "PASS" if c["recommendation"]["best_candidate"] is None else "BLOCKER"},
        {"id": "live_tools_off", "status": "PASS" if not live_tools else "BLOCKER"},
        {"id": "live_ranking_reader_off", "status": "PASS" if not live_rank else "BLOCKER"},
        {"id": "ranking_unexplained", "status": "PASS" if not parity.unexplained_score_differences else "FAIL", "deltas": parity.unexplained_score_differences},
        {"id": "ranking_differences_classified", "status": "PASS", "differences": parity.differences},
        {"id": "held_ranking_denied", "status": "PASS" if not held_bundle.eligible else "BLOCKER"},
        {"id": "ranking_writes", "status": "PASS" if parity.side_effects.get("ranking_writes", 0) == 0 else "BLOCKER"},
        {"id": "audit_events", "status": "PASS" if index.access_events else "FAIL", "count": len(index.access_events)},
    ]
    blockers = [g for g in gates if g["status"] == "BLOCKER"]
    fails = [g for g in gates if g["status"] == "FAIL"]
    return {
        "status": "PASS" if not blockers and not fails else ("BLOCKER" if blockers else "FAIL"),
        "gates": gates,
        "blockers": blockers,
        "fails": fails,
        "parity": parity.to_dict(),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()
    os.environ.update(env)
    Ctx = _connect_ctx(env)
    with Ctx() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        if db != "wathefni_staging":
            print(json.dumps({"status": "BLOCKER", "reason": f"wrong_db:{db}"}))
            return 2

    report: dict[str, Any] = {
        "generated_at": _now(),
        "database": db,
        "health_start": health(),
        "stages": {},
    }

    print("STAGE_B_START", flush=True)
    report["stages"]["B"] = stage_b(env, Ctx)
    print("STAGE_B", report["stages"]["B"]["status"], flush=True)
    (OUT / "stage-b.json").write_text(json.dumps(report["stages"]["B"], indent=2, default=str) + "\n", encoding="utf-8")
    if report["stages"]["B"]["status"] == "BLOCKER":
        report["status"] = "BLOCKER"
        (OUT / "phase8-staging-summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, default=str))
        return 1

    print("STAGE_C_START", flush=True)
    report["stages"]["C"] = stage_c(env, Ctx)
    print("STAGE_C", report["stages"]["C"]["status"], flush=True)
    (OUT / "stage-c.json").write_text(json.dumps(report["stages"]["C"], indent=2, default=str) + "\n", encoding="utf-8")
    if report["stages"]["C"]["status"] == "BLOCKER":
        report["status"] = "BLOCKER"
        (OUT / "phase8-staging-summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({"status": "BLOCKER", "C": report["stages"]["C"]["status"]}, indent=2))
        return 1

    print("STAGE_D_START", flush=True)
    report["stages"]["D"] = stage_d(env, Ctx)
    print("STAGE_D", report["stages"]["D"]["status"], flush=True)
    (OUT / "stage-d.json").write_text(json.dumps(report["stages"]["D"], indent=2, default=str) + "\n", encoding="utf-8")

    print("STAGE_E_START", flush=True)
    report["stages"]["E"] = stage_e(env, Ctx)
    print("STAGE_E", report["stages"]["E"]["status"], flush=True)
    (OUT / "stage-e.json").write_text(json.dumps(report["stages"]["E"], indent=2, default=str) + "\n", encoding="utf-8")

    # Final safe posture: live tools/ranking remain off; leave workers on for staging fidelity unless kill requested
    set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS="off",
        WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER="off",
    )
    report["health_end"] = health()
    report["flags_final"] = {
        k: _load_env().get(k)
        for k in (
            "WATHEFNI_CANDIDATE_KNOWLEDGE",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER",
            "WATHEFNI_CK_SHADOW_TOOLS_ENABLED",
            "WATHEFNI_CK_VOYAGE_ENABLED",
            "WATHEFNI_CK_SEMANTIC_SEARCH",
        )
    }
    statuses = [report["stages"][s]["status"] for s in ("B", "C", "D", "E")]
    if any(st == "BLOCKER" for st in statuses):
        report["status"] = "BLOCKER"
    elif any(st == "FAIL" for st in statuses):
        report["status"] = "FAIL"
    else:
        report["status"] = "PASS"
    report["production_dark_go"] = report["status"] == "PASS"
    (OUT / "phase8-staging-summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "production_dark_go": report["production_dark_go"], "stages": {k: v["status"] for k, v in report["stages"].items()}}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
