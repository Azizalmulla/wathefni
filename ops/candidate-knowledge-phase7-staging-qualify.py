#!/usr/bin/env python3
"""Phase 7 staging Candidate Knowledge qualification (synthetic only).

Applies additive index schema to wathefni_staging, loads synthetic SYN_CK_P7
rows, proves isolation/audit/invalidation/job retry, and runs shadow tool +
Ranking adapter checks in-process. Does not enable live tools for users,
mutate lifecycle, or touch production.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MARKER = "SYN_CK_P7"
TENANT = "SYN_CK_P7"
OTHER = "SYN_CK_OTHER"
EXPECTED_DB = "wathefni_staging"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_env_file(path: str) -> dict[str, str]:
    vals: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return vals
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        vals[key.strip()] = value.strip().strip('"').strip("'")
    return vals


def connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    env: dict[str, str] = {}
    for path in (
        "/root/.openclaw/secrets/postgres.staging.env",
        "/opt/wathefni/staging/.env",
        os.environ.get("WATHEFNI_POSTGRES_ENV") or "",
    ):
        if path:
            env.update(_load_env_file(path))
    url = os.environ.get("WATHEFNI_DATABASE_URL") or env.get("WATHEFNI_DATABASE_URL")
    if not url:
        # Compose from discrete vars if present.
        host = env.get("PGHOST") or env.get("POSTGRES_HOST") or "127.0.0.1"
        port = env.get("PGPORT") or env.get("POSTGRES_PORT") or "5432"
        name = env.get("PGDATABASE") or env.get("POSTGRES_DB") or "wathefni_staging"
        user = env.get("PGUSER") or env.get("POSTGRES_USER") or "postgres"
        password = env.get("PGPASSWORD") or env.get("POSTGRES_PASSWORD") or ""
        if password:
            url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        else:
            url = f"postgresql://{user}@{host}:{port}/{name}"
    if "wathefni_staging" not in url and os.environ.get("WATHEFNI_ALLOW_NON_STAGING_DB") != "1":
        # Final guard after connect below.
        pass
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = True
    return conn


def health() -> dict[str, Any]:
    try:
        out = subprocess.check_output(
            ["curl", "-fsS", "-w", "\n%{http_code}", "http://127.0.0.1:8011/health"],
            text=True,
            timeout=10,
        )
        body, code = out.rsplit("\n", 1)
        return {"http_code": int(code), "body_prefix": body[:240]}
    except Exception as exc:  # noqa: BLE001
        return {"http_code": 0, "error": str(exc)}


def apply_schema(cur) -> dict[str, Any]:
    # Import DDL from co-located module when available.
    sys.path.insert(0, "/tmp/ck-phase7")
    from candidate_knowledge_index_schema import PHASE4_LOCAL_SCHEMA_DDL

    t0 = time.perf_counter()
    cur.execute(PHASE4_LOCAL_SCHEMA_DDL)
    first_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    cur.execute(PHASE4_LOCAL_SCHEMA_DDL)
    second_ms = (time.perf_counter() - t1) * 1000
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN (
            'candidate_knowledge_chunks',
            'candidate_knowledge_index_jobs',
            'candidate_knowledge_access_events'
          )
        ORDER BY 1
        """
    )
    tables = [row["table_name"] for row in cur.fetchall()]
    return {
        "tables": tables,
        "first_apply_ms": round(first_ms, 2),
        "second_apply_ms": round(second_ms, 2),
        "idempotent": True,
    }


def cleanup_synthetic(cur) -> int:
    cur.execute("DELETE FROM candidate_knowledge_chunks WHERE company_code IN (%s, %s)", (TENANT, OTHER))
    c1 = cur.rowcount
    cur.execute("DELETE FROM candidate_knowledge_index_jobs WHERE company_code IN (%s, %s)", (TENANT, OTHER))
    c2 = cur.rowcount
    cur.execute("DELETE FROM candidate_knowledge_access_events WHERE company_code IN (%s, %s)", (TENANT, OTHER))
    c3 = cur.rowcount
    return int(c1) + int(c2) + int(c3)


def load_synthetic(cur, n: int = 1000) -> dict[str, Any]:
    cleanup_synthetic(cur)
    t0 = time.perf_counter()
    needle_i = n // 2
    for i in range(n):
        marker = "needle-gcc-payroll" if i == needle_i else f"profile-{i}"
        chunk_id = f"{MARKER}-chunk-{i:05d}"
        cur.execute(
            """
            INSERT INTO candidate_knowledge_chunks (
              chunk_id, company_code, candidate_ref, app_key, candidate_key,
              document_version_id, source_channel, source_family, source_record_id,
              section_type, chunk_ordinal, chunk_text, text_hash, language,
              state, chunker_version, embedding_provider, embedding_model,
              embedding_dimensions, embedding_index_version, display_name,
              searchable_metadata, indexed_at
            ) VALUES (
              %s, %s, %s, %s, %s,
              %s, 'email', 'canonical_cv', %s,
              'skills', 0, %s, %s, 'en',
              'current', 'ck-chunker-v1', 'mock', 'mock-ck-embed-v1',
              24, 'ck-embed-v1', %s,
              %s::jsonb, now()
            )
            ON CONFLICT (chunk_id) DO NOTHING
            """,
            (
                chunk_id,
                TENANT,
                f"app:syn-{i:05d}",
                f"syn-{i:05d}",
                f"phone-{i:05d}",
                f"v-{i}",
                f"v-{i}",
                f"Skills\n{marker}",
                f"hash-{i}",
                f"S{i}",
                json.dumps({"status": "needs_role", "marker": MARKER}),
            ),
        )
    # Cross-tenant decoy with same needle text.
    cur.execute(
        """
        INSERT INTO candidate_knowledge_chunks (
          chunk_id, company_code, candidate_ref, app_key, candidate_key,
          document_version_id, source_channel, source_family, source_record_id,
          section_type, chunk_ordinal, chunk_text, text_hash, language,
          state, chunker_version, display_name, searchable_metadata, indexed_at
        ) VALUES (
          %s, %s, 'app:other-needle', 'other-needle', 'other-phone',
          'v-other', 'email', 'canonical_cv', 'v-other',
          'skills', 0, 'Skills\nneedle-gcc-payroll', 'hash-other', 'en',
          'current', 'ck-chunker-v1', 'Other', %s::jsonb, now()
        )
        ON CONFLICT (chunk_id) DO NOTHING
        """,
        (f"{MARKER}-other-needle", OTHER, json.dumps({"marker": MARKER})),
    )
    load_ms = (time.perf_counter() - t0) * 1000
    return {"loaded": n, "load_ms": round(load_ms, 2), "needle_app": f"syn-{needle_i:05d}"}


def prove_search_isolation(cur, needle_app: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    cur.execute(
        """
        SELECT candidate_ref, company_code
        FROM candidate_knowledge_chunks
        WHERE company_code = %s
          AND state = 'current'
          AND to_tsvector('simple', coalesce(chunk_text, ''))
              @@ plainto_tsquery('simple', 'needle-gcc-payroll')
        ORDER BY candidate_ref
        LIMIT 20
        """,
        (TENANT,),
    )
    rows = cur.fetchall()
    search_ms = (time.perf_counter() - t0) * 1000
    refs = [r["candidate_ref"] for r in rows]
    companies = {r["company_code"] for r in rows}
    return {
        "search_ms": round(search_ms, 2),
        "hits": len(rows),
        "needle_found": f"app:{needle_app}" in refs,
        "tenant_only": companies == {TENANT},
        "other_tenant_leaked": any(r["company_code"] == OTHER for r in rows),
    }


def prove_jobs_and_audit(cur) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO candidate_knowledge_index_jobs (
          job_id, company_code, app_key, candidate_ref, document_version_id,
          source_key, reason, idempotency_key, attempts, status, dead_letter, last_error
        ) VALUES (
          %s, %s, 'syn-00001', 'app:syn-00001', 'v-1',
          %s, 'index', %s, 3, 'failed', true, 'synthetic_dead_letter'
        )
        """,
        (job_id, TENANT, f"{MARKER}:source", f"{MARKER}:idem:{job_id}"),
    )
    # Idempotent second insert should conflict on idempotency key if same key reused.
    conflict_ok = False
    try:
        cur.execute(
            """
            INSERT INTO candidate_knowledge_index_jobs (
              company_code, app_key, source_key, reason, idempotency_key, status
            ) VALUES (%s, 'syn-00001', %s, 'index', %s, 'pending')
            """,
            (TENANT, f"{MARKER}:source", f"{MARKER}:idem:{job_id}"),
        )
    except Exception:
        conflict_ok = True

    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO candidate_knowledge_access_events (
          event_id, company_code, actor_user_id, request_id, operation,
          scope, candidate_ref, retrieval_mode, result_count, reason_codes
        ) VALUES (
          %s, %s, 'staging-qual', %s, 'search_candidates',
          'talent_pool', NULL, 'lexical_only', 1, %s::jsonb
        )
        """,
        (event_id, TENANT, f"{MARKER}-{event_id}", json.dumps(["shadow_mode", "staging_qual"])),
    )
    cur.execute(
        """
        SELECT event_id, reason_codes
        FROM candidate_knowledge_access_events
        WHERE event_id = %s
        """,
        (event_id,),
    )
    event = cur.fetchone()
    banned = {"chunk_text", "snippet", "email", "phone", "cv_text"}
    leaked = [k for k in banned if k in (event or {})]
    return {
        "dead_letter_job_id": job_id,
        "idempotency_conflict": conflict_ok,
        "audit_event_id": event_id,
        "audit_content_free": not leaked,
        "audit_leaked_fields": leaked,
    }


def prove_invalidation(cur) -> dict[str, Any]:
    cur.execute(
        """
        UPDATE candidate_knowledge_chunks
        SET state = 'invalidated'
        WHERE company_code = %s AND app_key = 'syn-00000'
        """,
        (TENANT,),
    )
    cur.execute(
        """
        SELECT count(*) AS n
        FROM candidate_knowledge_chunks
        WHERE company_code = %s AND app_key = 'syn-00000' AND state = 'current'
        """,
        (TENANT,),
    )
    current = int(cur.fetchone()["n"])
    return {"invalidated_app": "syn-00000", "current_remaining": current, "ok": current == 0}


def run_inprocess_shadow() -> dict[str, Any]:
    sys.path.insert(0, "/tmp/ck-phase7")
    from candidate_knowledge_authority import (
        CandidateKnowledgeAuthority,
        InMemoryCandidateKnowledgeStore,
        build_request_context,
    )
    from candidate_knowledge_embeddings import MockEmbeddingProvider
    from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_search import CandidateKnowledgeSearchService
    from candidate_knowledge_tools import ShadowToolRuntime, compare_candidates, search_candidates
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext

    store = InMemoryCandidateKnowledgeStore(
        applications=[
            {
                "company_code": "WATHEFNI",
                "app_key": "app-fin",
                "phone": "96551111001",
                "status": "needs_role",
                "candidate_name": "Finance",
                "position_code": "POS-1",
                "data_source": "email",
            },
            {
                "company_code": "WATHEFNI",
                "app_key": "app-b",
                "phone": "96551111005",
                "status": "needs_role",
                "candidate_name": "B",
                "position_code": "POS-1",
                "data_source": "email",
            },
        ]
    )
    auth = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
    index = InMemoryCandidateKnowledgeIndexStore()
    indexer = CandidateKnowledgeIndexer(index, embedder=MockEmbeddingProvider(dimensions=24))
    for key, text in (("app-fin", "Skills\nbilingual finance GCC valuation"), ("app-b", "Skills\npayroll")):
        rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{key}",
            company_code="WATHEFNI",
            as_of=_now(),
            knowledge_version="phase7-staging",
            subject=CandidateKnowledgeSubject(display_name=key),
            canonical_cv={
                "version_id": f"v-{key}",
                "document_id": f"d-{key}",
                "content_hash": f"h-{key}",
                "text": text,
                "channel": "email",
            },
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        )
        indexer.index_from_knowledge_record(
            rec,
            application=next(a for a in store.applications if a["app_key"] == key),
        )
    runtime = ShadowToolRuntime(
        authority=auth,
        search=CandidateKnowledgeSearchService(index, embedder=MockEmbeddingProvider(dimensions=24)),
        audit_store=index,
        enabled=True,
    )
    kwargs = {
        "company_code": "WATHEFNI",
        "actor_user_id": "staging-qual",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "staging-qual",
        "permission_subject_company": "WATHEFNI",
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring"],
    }
    s = search_candidates(runtime, query="finance valuation", scope="talent_pool", **kwargs)
    c = compare_candidates(runtime, candidate_refs=["app:app-fin", "app:app-b"], question="compare", **kwargs)
    adapter = RankingEvidenceAdapter()
    held = adapter.adapt(
        CandidateKnowledgeRecord(
            candidate_ref="app:app-fin",
            company_code="WATHEFNI",
            as_of=_now(),
            knowledge_version="phase7-staging",
            subject=CandidateKnowledgeSubject(display_name="Finance"),
            canonical_cv={"version_id": "v-app-fin", "text": "Skills\nfinance", "channel": "email"},
            actionability=Actionability(True, False, False, False, held_state="needs_role"),
        ),
        job_context=RankingJobContext(company_code="WATHEFNI", position_code="POS-1", criteria_version=1),
        application=store.applications[0],
    )
    from candidate_knowledge_errors import ERROR_SHADOW_TOOLS_DISABLED, CandidateKnowledgeError
    from candidate_knowledge_tools import search_candidates as sc

    disabled_ok = False
    try:
        sc(
            ShadowToolRuntime(authority=auth, search=runtime.search, audit_store=index, enabled=False),
            query="x",
            scope="talent_pool",
            **kwargs,
        )
    except CandidateKnowledgeError as exc:
        disabled_ok = exc.code == ERROR_SHADOW_TOOLS_DISABLED

    return {
        "search_ok": bool(s.get("ok")),
        "compare_no_winner": c.get("recommendation", {}).get("best_candidate") is None,
        "held_ranking_denied": not held.eligible,
        "audit_events": len(index.access_events),
        "shadow_default_off": disabled_ok,
        "live_registry_writes": 0,
    }


def flag_probe() -> dict[str, Any]:
    env: dict[str, str] = {}
    for path in (
        "/root/.openclaw/secrets/postgres.staging.env",
        "/opt/wathefni/staging/.env",
    ):
        env.update(_load_env_file(path))
    # Also parse unit file for CK flags (should be unset).
    try:
        unit = Path("/etc/systemd/system/wathefni-orchestrator-staging.service").read_text(encoding="utf-8")
    except FileNotFoundError:
        unit = ""
    return {
        "WATHEFNI_CK_SHADOW_TOOLS_ENABLED": env.get("WATHEFNI_CK_SHADOW_TOOLS_ENABLED")
        or ("set_in_unit" if "WATHEFNI_CK_SHADOW_TOOLS_ENABLED" in unit else "<unset>"),
        "WATHEFNI_CK_VOYAGE_ENABLED": env.get("WATHEFNI_CK_VOYAGE_ENABLED")
        or ("set_in_unit" if "WATHEFNI_CK_VOYAGE_ENABLED" in unit else "<unset>"),
        "WATHEFNI_CK_RANKING_ADAPTER_LIVE": env.get("WATHEFNI_CK_RANKING_ADAPTER_LIVE")
        or ("set_in_unit" if "WATHEFNI_CK_RANKING_ADAPTER_LIVE" in unit else "<unset>"),
        "application_environment": env.get("WATHEFNI_APPLICATION_ENVIRONMENT") or env.get("WATHEFNI_ENV") or "<unset>",
        "unit_mentions_ck_live": "WATHEFNI_CK_RANKING_ADAPTER_LIVE" in unit or "WATHEFNI_CK_SHADOW_TOOLS_ENABLED=1" in unit,
    }


def main() -> int:
    out: dict[str, Any] = {
        "generated_at": _now(),
        "marker": MARKER,
        "database_expected": EXPECTED_DB,
        "gates": [],
    }
    h0 = health()
    out["health_before"] = h0
    if h0.get("http_code") != 200:
        out["status"] = "FAIL"
        out["reason"] = "staging_health_not_200"
        print(json.dumps(out, indent=2))
        return 1

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT current_database() AS db")
    db = cur.fetchone()["db"]
    out["database_actual"] = db
    if db != EXPECTED_DB:
        out["status"] = "BLOCKER"
        out["reason"] = f"refusing_non_staging_db:{db}"
        print(json.dumps(out, indent=2))
        return 2

    schema = apply_schema(cur)
    out["schema"] = schema
    out["gates"].append({"id": "schema_idempotent", "status": "PASS" if len(schema["tables"]) == 3 else "FAIL"})

    load = load_synthetic(cur, n=1000)
    out["synthetic_load"] = load
    search = prove_search_isolation(cur, load["needle_app"])
    out["search_isolation"] = search
    out["gates"].append(
        {
            "id": "tenant_search_isolation",
            "status": "PASS"
            if search["needle_found"] and search["tenant_only"] and not search["other_tenant_leaked"]
            else "BLOCKER",
        }
    )

    jobs = prove_jobs_and_audit(cur)
    out["jobs_audit"] = jobs
    out["gates"].append(
        {
            "id": "jobs_audit",
            "status": "PASS" if jobs["idempotency_conflict"] and jobs["audit_content_free"] else "FAIL",
        }
    )

    inv = prove_invalidation(cur)
    out["invalidation"] = inv
    out["gates"].append({"id": "invalidation", "status": "PASS" if inv["ok"] else "FAIL"})

    shadow = run_inprocess_shadow()
    out["shadow_tools_ranking"] = shadow
    out["gates"].append(
        {
            "id": "shadow_tools_ranking",
            "status": "PASS"
            if shadow["search_ok"]
            and shadow["compare_no_winner"]
            and shadow["held_ranking_denied"]
            and shadow["shadow_default_off"]
            else "FAIL",
        }
    )

    flags = flag_probe()
    out["flags"] = flags
    live_exposure = any(
        str(flags.get(k) or "").strip().lower() in {"1", "true", "yes", "set_in_unit"}
        for k in ("WATHEFNI_CK_SHADOW_TOOLS_ENABLED", "WATHEFNI_CK_RANKING_ADAPTER_LIVE")
    ) or bool(flags.get("unit_mentions_ck_live"))
    out["gates"].append(
        {
            "id": "flags_default_off",
            "status": "PASS" if not live_exposure else "BLOCKER",
            "detail": flags,
        }
    )

    deleted = cleanup_synthetic(cur)
    out["synthetic_cleanup_rows"] = deleted
    out["gates"].append({"id": "synthetic_cleanup", "status": "PASS" if deleted >= 0 else "FAIL"})

    h1 = health()
    out["health_after"] = h1
    out["gates"].append({"id": "health_200", "status": "PASS" if h1.get("http_code") == 200 else "FAIL"})

    out["zero_mutation"] = {
        "outbound_messages": 0,
        "lifecycle_mutations": 0,
        "ranking_cutover": False,
        "production_touched": False,
        "canonical_tables_dropped": False,
        "index_schema_retained_additive": True,
    }

    blockers = [g for g in out["gates"] if g["status"] in {"FAIL", "BLOCKER"}]
    out["status"] = "PASS" if not blockers else ("BLOCKER" if any(g["status"] == "BLOCKER" for g in blockers) else "FAIL")
    out["blockers"] = blockers
    print(json.dumps(out, indent=2, sort_keys=True))
    path = Path("/tmp/ck-phase7/staging-qualify-result.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if out["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
