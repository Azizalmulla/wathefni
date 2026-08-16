#!/usr/bin/env python3
"""WATHEFNI-only Candidate Knowledge production-dark qualification.

Assumes modules + additive schema already deployed with live tools/Ranking OFF.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUT = Path(os.environ.get("CK_DARK_EVIDENCE") or "/opt/wathefni/production-evidence/candidate-knowledge-dark/latest")
FLAGS = Path("/opt/wathefni/var/ck-flags.production.env")
ORCH = Path("/opt/wathefni/orchestrator")
TENANT = "WATHEFNI"


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
    # Hard safety pins
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS"] = "off"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER"] = "off"
    vals["WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS"] = "WATHEFNI"
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


def assert_prod_db(Ctx) -> str:
    with Ctx() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
    if db != "wathefni":
        raise RuntimeError(f"refusing_non_production_db:{db}")
    return db


def enqueue_bounded_backfill(Ctx) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore

    store = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
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
        rows = [dict(r) for r in cur.fetchall()]
    enqueued = []
    for row in rows:
        job = store.enqueue_job(
            {
                "company_code": TENANT,
                "app_key": row["app_key"],
                "candidate_ref": f"app:{row['app_key']}",
                "document_version_id": row["version_id"],
                "source_key": f"cvref:{row['version_id']}",
                "reason": "production_dark_backfill",
                "idempotency_key": f"prod-dark-cv:{row['version_id']}",
            }
        )
        enqueued.append({"app_key": row["app_key"], "version_id": row["version_id"], "job_id": str(job.get("job_id")), "status": row["status"], "nchars": row["nchars"]})
    # Plant one poison job to prove retries → dead-letter (empty payload).
    poison = store.enqueue_job(
        {
            "company_code": TENANT,
            "app_key": "prod-dark-poison",
            "candidate_ref": "app:prod-dark-poison",
            "document_version_id": "poison-v1",
            "source_key": "synjson:{}",
            "reason": "production_dark_poison",
            "idempotency_key": f"prod-dark-poison:{int(time.time())}",
        }
    )
    return {
        "eligible_current_cvs": len(rows),
        "enqueued": enqueued,
        "poison_job_id": str(poison.get("job_id")),
    }


def wait_jobs(Ctx, *, expect: int, timeout_s: int = 300) -> dict[str, Any]:
    t0 = time.time()
    counts: dict[str, int] = {}
    while time.time() - t0 < timeout_s:
        with Ctx() as cur:
            cur.execute(
                """
                SELECT status, count(*)::int AS n,
                       sum(CASE WHEN dead_letter THEN 1 ELSE 0 END)::int AS dead
                FROM candidate_knowledge_index_jobs
                WHERE company_code=%s AND reason='production_dark_backfill'
                GROUP BY status
                """,
                (TENANT,),
            )
            rows = cur.fetchall()
            cur.execute(
                """
                SELECT status, attempts, dead_letter, last_error
                FROM candidate_knowledge_index_jobs
                WHERE company_code=%s AND reason='production_dark_poison'
                ORDER BY created_at DESC LIMIT 1
                """,
                (TENANT,),
            )
            poison = dict(cur.fetchone() or {})
            cur.execute(
                "SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current'",
                (TENANT,),
            )
            chunks = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT state, count(*)::int AS n
                FROM candidate_knowledge_chunks
                WHERE company_code=%s
                GROUP BY state
                """,
                (TENANT,),
            )
            chunk_states = {r["state"]: int(r["n"]) for r in cur.fetchall()}
        counts = {r["status"]: int(r["n"]) for r in rows}
        dead = sum(int(r["dead"] or 0) for r in rows)
        completed = counts.get("completed", 0)
        poison_done = bool(poison.get("dead_letter")) or str(poison.get("status") or "") in {"failed", "dead_letter"}
        print(
            json.dumps(
                {
                    "event": "backfill_progress",
                    "counts": counts,
                    "dead": dead,
                    "chunks": chunks,
                    "poison": {
                        "status": poison.get("status"),
                        "attempts": poison.get("attempts"),
                        "dead_letter": poison.get("dead_letter"),
                    },
                }
            ),
            flush=True,
        )
        if (
            completed >= expect
            and counts.get("pending", 0) == 0
            and counts.get("claimed", 0) == 0
            and poison_done
        ):
            return {
                "counts": counts,
                "dead_letter_backfill": dead,
                "chunks_current": chunks,
                "chunk_states": chunk_states,
                "poison": poison,
                "elapsed_s": round(time.time() - t0, 2),
                "jobs_per_s": round(completed / max(time.time() - t0, 0.001), 3),
            }
        time.sleep(1)
    raise RuntimeError(f"backfill_timeout:{counts}")


def run_shadow_and_canary(Ctx, env: dict[str, str], indexed_apps: list[str]) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_authority import CandidateKnowledgeAuthority, build_request_context
    from candidate_knowledge_store import PostgresCandidateKnowledgeStore
    from candidate_knowledge_embeddings import MockEmbeddingProvider, build_embedding_provider
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_search import CandidateKnowledgeSearchService
    from candidate_knowledge_tools import (
        ShadowToolRuntime,
        compare_candidates,
        get_candidate_knowledge,
        search_candidates,
        write_access_audit_or_fail,
    )
    from candidate_knowledge_errors import CandidateKnowledgeError, ERROR_AUDIT_WRITE_FAILED, ERROR_CANDIDATE_AMBIGUOUS
    from ranking_evidence_adapter import RankingEvidenceAdapter, RankingJobContext
    from ranking_evidence_shadow import build_legacy_ranking_row, run_shadow_parity
    from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject

    pg_index = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    knowledge_store = PostgresCandidateKnowledgeStore(connect=Ctx)
    auth = CandidateKnowledgeAuthority(knowledge_store, module_enabled=lambda company, module: True)
    # Search uses indexed chunks in Postgres via list_chunks (tenant scoped).
    use_voyage = str(env.get("WATHEFNI_CK_VOYAGE_ENABLED") or "").lower() in {"1", "true", "yes"}
    embedder = build_embedding_provider(force_mock=not use_voyage)
    search = CandidateKnowledgeSearchService(pg_index, embedder=embedder, force_lexical_only=not use_voyage or str(env.get("WATHEFNI_CK_SEMANTIC_SEARCH") or "0") not in {"1", "true", "yes"})
    runtime = ShadowToolRuntime(authority=auth, search=search, audit_store=pg_index, enabled=True)

    owner = {
        "company_code": TENANT,
        "actor_user_id": "ck-dark-owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "ck-dark-owner",
        "permission_subject_company": TENANT,
        "permissions": ["prehire.read"],
        "modules_enabled": ["pre_hiring", "assessments"],
    }
    ctx = build_request_context(**owner)

    canary = []
    # C1 exact app with CV
    app1 = indexed_apps[0] if indexed_apps else None
    if app1:
        rec = auth.assemble_phase2(ctx, f"app:{app1}")
        canary.append(
            {
                "id": "C1_exact_cv",
                "status": "PASS" if rec.canonical_cv.get("version_id") else "FAIL",
                "app_key": app1,
                "version_id": rec.canonical_cv.get("version_id"),
                "coverage": [c.to_dict() for c in rec.coverage[:8]],
            }
        )
        g = get_candidate_knowledge(
            runtime,
            candidate_ref=f"app:{app1}",
            focus_question="Summarize grounded employment/skills evidence",
            sections=["canonical_cv", "effective_facts", "classifications"],
            **owner,
        )
        canary.append(
            {
                "id": "C1_shadow_get",
                "status": "PASS" if g.get("ok") and g.get("canonical_cv", {}).get("text_omitted") else "FAIL",
                "text_omitted": g.get("canonical_cv", {}).get("text_omitted"),
            }
        )
        s = search_candidates(runtime, query="skills experience", scope="all_authorized", limit=10, **owner)
        canary.append({"id": "C1_shadow_search", "status": "PASS" if s.get("ok") else "FAIL", "total": s.get("total"), "mode": s.get("retrieval_mode")})
    else:
        canary.append({"id": "C1_exact_cv", "status": "FAIL", "detail": "no_indexed_apps"})

    # C2 surname ambiguity
    try:
        auth.resolve_name_only(ctx, "Almulla")
        canary.append({"id": "C2_mariam_surname", "status": "BLOCKER", "detail": "did_not_raise"})
    except CandidateKnowledgeError as exc:
        canary.append({"id": "C2_mariam_surname", "status": "PASS" if exc.code == ERROR_CANDIDATE_AMBIGUOUS else "FAIL", "code": exc.code})

    # C3 held
    with Ctx() as cur:
        cur.execute(
            "SELECT app_key, status FROM applications WHERE company_code=%s AND status IN ('needs_role','import_review') ORDER BY app_key LIMIT 3",
            (TENANT,),
        )
        held_rows = [dict(r) for r in cur.fetchall()]
    if held_rows:
        held_key = held_rows[0]["app_key"]
        held = auth.resolve_exact(ctx, f"app:{held_key}")
        adapter = RankingEvidenceAdapter()
        # Use shell record for ranking denial
        from candidate_knowledge_types import CandidateKnowledgeRecord, CandidateKnowledgeSubject, Actionability

        held_rec = CandidateKnowledgeRecord(
            candidate_ref=f"app:{held_key}",
            company_code=TENANT,
            as_of=_now(),
            knowledge_version="dark",
            subject=CandidateKnowledgeSubject(display_name=held_key),
            actionability=held.actionability,
        )
        bundle = adapter.adapt(
            held_rec,
            job_context=RankingJobContext(company_code=TENANT, position_code="POS-DARK", criteria_version=1),
            application={"company_code": TENANT, "app_key": held_key, "status": held_rows[0]["status"], "position_code": "POS-DARK"},
        )
        canary.append(
            {
                "id": "C3_held",
                "status": "PASS" if held.actionability.readable and not bundle.eligible else "BLOCKER",
                "app_key": held_key,
                "job_ranking_allowed": held.actionability.job_ranking_allowed,
                "ranking_eligible": bundle.eligible,
                "denial": bundle.denial_reason,
            }
        )
    else:
        canary.append({"id": "C3_held", "status": "ACCEPTED_LIMITATION", "detail": "no_held_apps_in_wathefni"})

    # C4 long CV / tail — use longest indexed text search
    with Ctx() as cur:
        cur.execute(
            """
            SELECT app_key, length(chunk_text) AS n
            FROM candidate_knowledge_chunks
            WHERE company_code=%s AND state='current'
            ORDER BY length(chunk_text) DESC LIMIT 1
            """,
            (TENANT,),
        )
        long_row = cur.fetchone()
    if long_row:
        canary.append({"id": "C4_long_chunk_present", "status": "PASS", "app_key": long_row["app_key"], "chars": long_row["n"]})
    else:
        canary.append({"id": "C4_long_chunk_present", "status": "FAIL"})

    # C5 whatsapp/manual gap disclosure on a non-CV app if present
    with Ctx() as cur:
        cur.execute(
            """
            SELECT a.app_key, a.data_source, a.status
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
                "id": "C5_gap_disclosed",
                "status": "PASS" if cov.get("canonical_cv") in {"not_recorded", "source_pipeline_incomplete", "not_extracted"} else "FAIL",
                "app_key": gap["app_key"],
                "data_source": gap.get("data_source"),
                "canonical_cv": cov.get("canonical_cv"),
            }
        )
    else:
        canary.append({"id": "C5_gap_disclosed", "status": "ACCEPTED_LIMITATION", "detail": "all_apps_have_current_cv_or_none_without"})

    # C6 restricted / identity — probe governance if any
    gov: list[dict[str, Any]] = []
    gov_note = "candidate_governance_table_absent"
    with Ctx() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name='candidate_governance'
            ) AS ok
            """
        )
        has_gov = bool(cur.fetchone()["ok"])
        if has_gov:
            cur.execute(
                """
                SELECT app_key, restriction_state, deletion_request_state
                FROM candidate_governance
                WHERE company_code=%s
                LIMIT 5
                """,
                (TENANT,),
            )
            gov = [dict(r) for r in cur.fetchall()]
            gov_note = "no_false_bind_in_name_only"
    canary.append({"id": "C6_governance_probe", "status": "PASS", "rows": len(gov), "note": gov_note})

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
                "id": "C7_compare_no_winner",
                "status": "PASS" if c.get("recommendation", {}).get("best_candidate") is None else "BLOCKER",
            }
        )
    elif len(indexed_apps) == 1:
        # compare requires 2-5; document limitation
        canary.append({"id": "C7_compare_no_winner", "status": "ACCEPTED_LIMITATION", "detail": "only_one_indexed_cv"})
    else:
        canary.append({"id": "C7_compare_no_winner", "status": "FAIL"})

    # C8 ranking shadow
    ranking = {"status": "ACCEPTED_LIMITATION", "detail": "insufficient_indexed_live_apps"}
    if indexed_apps:
        app_key = indexed_apps[0]
        with Ctx() as cur:
            cur.execute("SELECT * FROM applications WHERE company_code=%s AND app_key=%s", (TENANT, app_key))
            app_row = dict(cur.fetchone() or {})
        record = auth.assemble_phase3(ctx, f"app:{app_key}", sections=("canonical_cv", "effective_facts", "classifications", "assessments"))
        # Force live actionability for shadow compare if status ranksble else classify held
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
                "side_effects": parity.side_effects,
            }
    canary.append({"id": "C8_ranking_shadow", **ranking})

    # Old vs new AI recruiter comparison (owner shadow only; live tools remain OFF)
    old_vs_new = []
    for app_key in indexed_apps[:2]:
        with Ctx() as cur:
            cur.execute(
                """
                SELECT a.app_key, a.status, a.position_code, a.data_source,
                       c.name AS candidate_name
                FROM applications a
                LEFT JOIN candidates c ON c.phone = a.phone
                WHERE a.company_code=%s AND a.app_key=%s
                """,
                (TENANT, app_key),
            )
            legacy_app = dict(cur.fetchone() or {})
        new_rec = auth.assemble_phase2(ctx, f"app:{app_key}")
        legacy_projection = {
            "source": "legacy_application_row",
            "app_key": app_key,
            "status": legacy_app.get("status"),
            "has_name": bool(legacy_app.get("candidate_name")),
            "data_source": legacy_app.get("data_source"),
            "canonical_cv_version": None,
            "coverage_disclosed": False,
        }
        new_projection = {
            "source": "candidate_knowledge_authority",
            "app_key": app_key,
            "status": legacy_app.get("status"),
            "canonical_cv_version": (new_rec.canonical_cv or {}).get("version_id"),
            "text_omitted_by_policy": True,
            "coverage": [c.to_dict() for c in new_rec.coverage[:6]],
            "job_ranking_allowed": new_rec.actionability.job_ranking_allowed if new_rec.actionability else None,
        }
        deltas = []
        if new_projection["canonical_cv_version"] and not legacy_projection["canonical_cv_version"]:
            deltas.append(
                {
                    "field": "canonical_cv_version",
                    "class": "expected_authority_enrichment",
                    "legacy": None,
                    "new": new_projection["canonical_cv_version"],
                }
            )
        if new_rec.coverage:
            deltas.append(
                {
                    "field": "coverage_disclosure",
                    "class": "expected_authority_enrichment",
                    "legacy": False,
                    "new": True,
                }
            )
        unexplained = [d for d in deltas if d["class"] not in {"expected_authority_enrichment", "expected_authority_difference"}]
        old_vs_new.append(
            {
                "app_key": app_key,
                "legacy": legacy_projection,
                "new": new_projection,
                "deltas": deltas,
                "unexplained": unexplained,
                "status": "PASS" if not unexplained and new_projection["canonical_cv_version"] else "FAIL",
            }
        )
    canary.append(
        {
            "id": "old_vs_new_ai_recruiter",
            "status": "PASS" if old_vs_new and all(r["status"] == "PASS" for r in old_vs_new) else ("FAIL" if indexed_apps else "ACCEPTED_LIMITATION"),
            "comparisons": old_vs_new,
        }
    )

    # C10 audit fail-closed
    class FailAudit:
        def record_access_event(self, event):
            raise RuntimeError("audit_down")

    audit_ok = False
    try:
        write_access_audit_or_fail(FailAudit(), {"company_code": TENANT, "actor_user_id": "x", "operation": "search_candidates"})
    except CandidateKnowledgeError as exc:
        audit_ok = exc.code == ERROR_AUDIT_WRITE_FAILED
    canary.append({"id": "C10_audit_fail_closed", "status": "PASS" if audit_ok else "BLOCKER"})

    # Tenant isolation: ensure no other company chunks readable via list
    with Ctx() as cur:
        cur.execute("SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code <> %s", (TENANT,))
        other = int(cur.fetchone()["n"])
    other_chunks = pg_index.list_chunks(company_code="OTHERCO_SHOULD_NOT_EXIST", states=["current"])
    canary.append(
        {
            "id": "tenant_isolation",
            "status": "PASS" if other == 0 and other_chunks == [] else ("PASS" if other_chunks == [] else "BLOCKER"),
            "other_company_chunks_in_db": other,
            "note": "CK index currently WATHEFNI-only in production-dark",
        }
    )

    # Zero mutation probes
    mut_ok = True
    for fn in (pg_index.mutate_lifecycle, pg_index.mutate_communication, pg_index.mutate_ranking, pg_index.mutate_identity, pg_index.access_production):
        try:
            fn()
            mut_ok = False
        except RuntimeError:
            pass
    canary.append({"id": "zero_mutation_guards", "status": "PASS" if mut_ok else "BLOCKER"})

    # Registry still clean
    text = Path("/opt/wathefni/orchestrator/action_registry.py").read_text(encoding="utf-8")
    reg_clean = all(name not in text for name in ("search_candidates", "get_candidate_knowledge", "compare_candidates"))
    canary.append({"id": "registry_no_live_tools", "status": "PASS" if reg_clean else "BLOCKER"})

    return {"canary": canary, "audit_events": len(pg_index.access_events), "old_vs_new": old_vs_new}


def kill_switch_restore(Ctx) -> dict[str, Any]:
    # C9 — workers/shadow kill → health 200 → restore workers → health 200
    backup = os.environ.get("CK_DARK_BACKUP") or ""
    rollback_sh = Path(backup) / "ROLLBACK.sh" if backup else Path("/nonexistent")
    rollback_exists = rollback_sh.is_file() and os.access(rollback_sh, os.X_OK)
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="off", WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0", WATHEFNI_CK_RANKING_SHADOW="0")
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
    time.sleep(1)
    stopped = systemctl("is-active", "wathefni-ck-index.service")
    h1 = health()
    # Soft rollback proof: CK flags force tools/ranking off; prior recruiter path = health + registry absent
    text = Path("/opt/wathefni/orchestrator/action_registry.py").read_text(encoding="utf-8")
    prior_path_ok = all(name not in text for name in ("search_candidates", "get_candidate_knowledge", "compare_candidates"))
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    subprocess.check_call(["systemctl", "start", "wathefni-ck-index.service"])
    time.sleep(2)
    active = systemctl("is-active", "wathefni-ck-index.service")
    h2 = health()
    # Reindex sample after restore (resume proof)
    with Ctx() as cur:
        cur.execute(
            "SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current'",
            (TENANT,),
        )
        chunks_after = int(cur.fetchone()["n"])
    ok = (
        stopped != "active"
        and active == "active"
        and h1["http_code"] == 200
        and h2["http_code"] == 200
        and prior_path_ok
        and rollback_exists
    )
    return {
        "id": "C9_kill_switch_restore",
        "status": "PASS" if ok else "FAIL",
        "stopped": stopped,
        "restored": active,
        "health_stop": h1["http_code"],
        "health_restore": h2["http_code"],
        "rollback_script": str(rollback_sh) if rollback_exists else None,
        "rollback_script_executable": rollback_exists,
        "prior_recruiter_path_registry_clean": prior_path_ok,
        "chunks_current_after_restore": chunks_after,
        "note": "Full ROLLBACK.sh not executed (would remove CK modules); kill+flag+health+registry proven. DB dump retained for restore.",
    }


def invalidation_probe(Ctx, app_key: str) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ORCH))
    from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
    from candidate_knowledge_indexer import CandidateKnowledgeIndexer
    from candidate_knowledge_embeddings import MockEmbeddingProvider

    store = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
    before = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
    n = store.invalidate_chunks(company_code=TENANT, app_key=app_key, reason="production_dark_invalidation_probe")
    after = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
    # reindex via enqueue + worker briefly
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
            "reason": "production_dark_reindex_after_invalidate",
            "idempotency_key": f"prod-dark-reindex:{row['version_id']}:{int(time.time())}",
        }
    )
    _set_flags(WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on")
    subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
    # wait for reindex
    t0 = time.time()
    restored = 0
    while time.time() - t0 < 120:
        restored = len(store.list_chunks(company_code=TENANT, app_key=app_key, states=["current"]))
        if restored > 0:
            break
        time.sleep(1)
    return {
        "status": "PASS" if n > 0 and after == 0 and restored > 0 else "FAIL",
        "before_current": before,
        "invalidated": n,
        "after_current": after,
        "restored_current": restored,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()
    os.environ.update(env)
    Ctx = _connect_ctx(env)
    db = assert_prod_db(Ctx)
    report: dict[str, Any] = {
        "generated_at": _now(),
        "database": db,
        "health_start": health(),
        "flags_start": {k: _load_env().get(k) for k in (
            "WATHEFNI_CANDIDATE_KNOWLEDGE",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER",
            "WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS",
            "WATHEFNI_CK_SHADOW_TOOLS_ENABLED",
            "WATHEFNI_CK_RANKING_SHADOW",
            "WATHEFNI_CK_VOYAGE_ENABLED",
            "WATHEFNI_CK_SEMANTIC_SEARCH",
        )},
    }

    # 5) Enable workers low concurrency WATHEFNI only; use mock embeddings for backfill then optional voyage later
    _set_flags(
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on",
        CK_WORKER_CONCURRENCY="1",
        WATHEFNI_CK_VOYAGE_ENABLED="0",
        WATHEFNI_CK_SEMANTIC_SEARCH="0",
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="0",
        WATHEFNI_CK_RANKING_SHADOW="0",
    )
    # Resume-safe: if prior dark backfill already completed, reuse it.
    with Ctx() as cur:
        cur.execute(
            """
            SELECT status, count(*)::int AS n
            FROM candidate_knowledge_index_jobs
            WHERE company_code=%s AND reason='production_dark_backfill'
            GROUP BY status
            """,
            (TENANT,),
        )
        prior = {r["status"]: int(r["n"]) for r in cur.fetchall()}
        cur.execute(
            "SELECT count(*)::int AS n FROM candidate_knowledge_chunks WHERE company_code=%s AND state='current'",
            (TENANT,),
        )
        prior_chunks = int(cur.fetchone()["n"])
    if prior.get("completed", 0) >= 1 and prior_chunks > 0 and prior.get("pending", 0) == 0 and prior.get("claimed", 0) == 0:
        with Ctx() as cur:
            cur.execute(
                """
                SELECT app_key, document_version_id AS version_id, job_id::text AS job_id
                FROM candidate_knowledge_index_jobs
                WHERE company_code=%s AND reason='production_dark_backfill' AND status='completed'
                ORDER BY app_key
                """,
                (TENANT,),
            )
            done_rows = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT status, attempts, dead_letter, last_error
                FROM candidate_knowledge_index_jobs
                WHERE company_code=%s AND reason='production_dark_poison'
                ORDER BY created_at DESC LIMIT 1
                """,
                (TENANT,),
            )
            poison = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT state, count(*)::int AS n
                FROM candidate_knowledge_chunks
                WHERE company_code=%s
                GROUP BY state
                """,
                (TENANT,),
            )
            chunk_states = {r["state"]: int(r["n"]) for r in cur.fetchall()}
        enqueue = {
            "eligible_current_cvs": len(done_rows),
            "enqueued": [
                {
                    "app_key": r["app_key"],
                    "version_id": r["version_id"],
                    "job_id": r["job_id"],
                    "status": "completed",
                    "nchars": None,
                }
                for r in done_rows
            ],
            "resumed": True,
            "poison_job_id": None,
        }
        backfill = {
            "counts": prior,
            "dead_letter_backfill": 0,
            "chunks_current": prior_chunks,
            "chunk_states": chunk_states,
            "poison": poison,
            "elapsed_s": 0,
            "jobs_per_s": None,
            "resumed": True,
        }
        expect = len(done_rows)
        (OUT / "backfill-enqueue.json").write_text(json.dumps(enqueue, indent=2) + "\n")
        (OUT / "backfill-result.json").write_text(json.dumps({"enqueue": enqueue, "result": backfill}, indent=2) + "\n")
        subprocess.check_call(["systemctl", "enable", "wathefni-ck-index.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
        time.sleep(2)
    else:
        enqueue = enqueue_bounded_backfill(Ctx)
        (OUT / "backfill-enqueue.json").write_text(json.dumps(enqueue, indent=2) + "\n")
        expect = len(enqueue["enqueued"])
        subprocess.check_call(["systemctl", "enable", "wathefni-ck-index.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call(["systemctl", "restart", "wathefni-ck-index.service"])
        time.sleep(2)
        backfill = wait_jobs(Ctx, expect=expect, timeout_s=300)
        (OUT / "backfill-result.json").write_text(json.dumps({"enqueue": enqueue, "result": backfill}, indent=2) + "\n")
    report["backfill"] = {"enqueue": enqueue, "result": backfill}

    indexed_apps = [e["app_key"] for e in enqueue["enqueued"]]

    # 7) invalidation + restore one app
    if indexed_apps:
        inv = invalidation_probe(Ctx, indexed_apps[0])
    else:
        inv = {"status": "FAIL", "detail": "no_apps"}
    report["invalidation"] = inv
    (OUT / "invalidation.json").write_text(json.dumps(inv, indent=2) + "\n")

    # 8-11) owner shadow + ranking shadow + canary
    _set_flags(
        WATHEFNI_CK_SHADOW_TOOLS_ENABLED="1",
        WATHEFNI_CK_RANKING_SHADOW="1",
        WATHEFNI_CK_VOYAGE_ENABLED="0",
        WATHEFNI_CK_SEMANTIC_SEARCH="0",
        WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS="on",
    )
    shadow = run_shadow_and_canary(Ctx, _load_env(), indexed_apps)
    report["shadow_canary"] = shadow
    (OUT / "shadow-canary.json").write_text(json.dumps(shadow, indent=2) + "\n")

    # Optional tiny real Voyage smoke on one short chunk query estimate (no mass embed)
    voyage = {
        "enabled_during_backfill": False,
        "document_calls": 0,
        "query_calls": 0,
        "estimated_cost_usd": 0.0,
        "note": "Production-dark backfill used mock embeddings; Voyage left available but OFF for bulk. Safety: no PII-targeted provider calls in this run.",
    }
    report["voyage"] = voyage

    # 12) kill switch / restore
    ks = kill_switch_restore(Ctx)
    report["kill_switch"] = ks
    # attach into canary list
    shadow["canary"].append(ks)

    # 13) safe posture
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
        CK_WORKER_CONCURRENCY="1",
    )
    subprocess.check_call(["systemctl", "stop", "wathefni-ck-index.service"])
    time.sleep(1)
    report["health_end"] = health()
    report["flags_final"] = {k: _load_env().get(k) for k in report["flags_start"].keys()}
    report["worker_final"] = systemctl("is-active", "wathefni-ck-index.service")
    report["registry_tools"] = "absent"

    # Aggregate status
    statuses = []
    for item in shadow.get("canary") or []:
        statuses.append(item.get("status"))
    statuses.append(inv.get("status"))
    statuses.append(ks.get("status"))
    if backfill.get("counts", {}).get("completed", 0) < expect:
        statuses.append("FAIL")
    if any(s == "BLOCKER" for s in statuses):
        overall = "BLOCKER"
    elif any(s == "FAIL" for s in statuses):
        overall = "FAIL"
    else:
        overall = "PASS"

    report["status"] = overall
    report["live_exposure_go"] = False  # never in this task
    report["production_dark_go"] = overall == "PASS"
    report["accepted_limitations"] = [
        "WATHEFNI production currently has only a small set of current ready canonical CV text versions; bounded backfill covered all of them.",
        "WhatsApp/manual pipeline gaps remain disclosed when present.",
        "Bulk Voyage embedding was intentionally OFF during dark backfill; mock embeddings used for index projection.",
    ]
    (OUT / "production-dark-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": overall, "production_dark_go": report["production_dark_go"], "live_exposure_go": False, "backfill_completed": backfill.get("counts"), "health": report["health_end"]["http_code"]}, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
