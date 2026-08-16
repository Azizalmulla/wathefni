"""Candidate Knowledge index worker (staging/production-shaped).

Claims jobs from candidate_knowledge_index_jobs and indexes synthetic or
authority-backed payloads. Never mutates lifecycle/communication/ranking/identity.
"""

from __future__ import annotations

import json
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any

from candidate_knowledge_embeddings import MockEmbeddingProvider, build_embedding_provider
from candidate_knowledge_indexer import CandidateKnowledgeIndexer
from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CandidateKnowledgeSubject


STOP = False


def _handle_stop(*_args: Any) -> None:
    global STOP
    STOP = True


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


def load_runtime_env() -> dict[str, str]:
    """Load runtime env without cross-contaminating production and staging.

    Production workers must never inherit staging DATABASE_URL / CK flags.
    Staging workers keep their dedicated postgres + flags files.
    """

    env = dict(os.environ)
    is_production = str(env.get("WATHEFNI_ENV") or "").strip().lower() == "production"
    paths: list[str] = []
    postgres_env = str(env.get("WATHEFNI_POSTGRES_ENV") or "").strip()
    if postgres_env:
        paths.append(postgres_env)
    elif is_production:
        paths.append("/root/.openclaw/secrets/postgres.env")
    else:
        paths.append("/root/.openclaw/secrets/postgres.staging.env")
    paths.append("/root/.openclaw/secrets/voyage.env")
    if is_production:
        paths.append("/opt/wathefni/var/ck-flags.production.env")
    else:
        paths.append("/opt/wathefni/staging/var/ck-flags.env")
    for path in paths:
        if path:
            env.update(_load_env_file(path))
    return env


def connect_factory(env: dict[str, str]):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = env.get("WATHEFNI_DATABASE_URL")
    if not url:
        raise RuntimeError("WATHEFNI_DATABASE_URL missing")

    def _connect():
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn.cursor()

    class _Ctx:
        def __enter__(self):
            self.cur = _connect()
            self.conn = self.cur.connection
            return self.cur

        def __exit__(self, *exc):
            try:
                self.cur.close()
            finally:
                self.conn.close()

    return _Ctx


def workers_enabled(env: dict[str, str]) -> bool:
    return str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def tenant_allowed(env: dict[str, str], company_code: str) -> bool:
    master = str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE") or "").strip().lower()
    if master not in {"1", "true", "yes", "on"}:
        return False
    raw = str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS") or "").strip()
    if not raw:
        return False
    allowed = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return company_code.upper() in allowed


def _payload_from_job(job: dict[str, Any]) -> dict[str, Any]:
    # Jobs may carry JSON in last_error temporarily for synthetic staging payloads via source_key marker.
    # Preferred: payload table is not required; synthetic loader stores text in searchable path via enqueue metadata.
    return {}


def _load_cv_text_from_db(store: PostgresCandidateKnowledgeIndexStore, *, company: str, app_key: str, version_id: str) -> tuple[str, dict[str, Any]]:
    """Load current/version-pinned CV text and application row for production backfill."""

    with store.connect() as cur:
        cur.execute(
            """
            SELECT version_id, document_id, text_content, status, is_current,
                   extracted_text_hash, provenance
            FROM candidate_cv_text_versions
            WHERE company_code = %s AND app_key = %s AND version_id = %s
            LIMIT 1
            """,
            (company, app_key, version_id),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"cv_version_not_found:{company}:{app_key}:{version_id}")
        cur.execute(
            """
            SELECT company_code, app_key, phone, status, position_code, position_title, data_source
            FROM applications
            WHERE company_code = %s AND app_key = %s
            LIMIT 1
            """,
            (company, app_key),
        )
        app = cur.fetchone() or {}
    text = str(row.get("text_content") or "")
    meta = {
        "version_id": str(row.get("version_id") or version_id),
        "document_id": str(row.get("document_id") or ""),
        "content_hash": str(row.get("extracted_text_hash") or version_id)[:64],
        "channel": "email",
        "application": dict(app) if app else {},
    }
    prov = row.get("provenance")
    if isinstance(prov, dict) and prov.get("channel"):
        meta["channel"] = str(prov.get("channel"))
    elif isinstance(prov, str) and prov:
        try:
            parsed = json.loads(prov)
            if isinstance(parsed, dict) and parsed.get("channel"):
                meta["channel"] = str(parsed.get("channel"))
        except Exception:
            pass
    return text, meta


def process_job(
    *,
    store: PostgresCandidateKnowledgeIndexStore,
    indexer: CandidateKnowledgeIndexer,
    job: dict[str, Any],
    payload_text: str | None = None,
) -> None:
    company = str(job.get("company_code") or "").upper()
    app_key = str(job.get("app_key") or "")
    candidate_ref = str(job.get("candidate_ref") or f"app:{app_key}")
    text = payload_text or ""
    meta: dict[str, Any] = {}
    if not text:
        source_key = str(job.get("source_key") or "")
        if source_key.startswith("synjson:"):
            try:
                data = json.loads(source_key[len("synjson:") :])
                text = str(data.get("text") or "")
            except Exception:
                text = ""
        elif source_key.startswith("cvref:"):
            # cvref:<version_id>
            version_id = source_key.split(":", 1)[1].strip() or str(job.get("document_version_id") or "")
            text, meta = _load_cv_text_from_db(
                store,
                company=company,
                app_key=app_key,
                version_id=version_id or str(job.get("document_version_id") or ""),
            )
        elif source_key.startswith("src_") and str(job.get("document_version_id") or "").strip():
            # Versioned source keys from CandidateKnowledgeIndexer.enqueue — load CV by document_version_id.
            text, meta = _load_cv_text_from_db(
                store,
                company=company,
                app_key=app_key,
                version_id=str(job.get("document_version_id") or "").strip(),
            )
    if not text:
        raise RuntimeError("missing_index_payload_text")

    app = meta.get("application") if isinstance(meta.get("application"), dict) else {}
    status = str(app.get("status") or "needs_role")
    held = status if status in {"needs_role", "import_review", "import_archived"} else None
    record = CandidateKnowledgeRecord(
        candidate_ref=candidate_ref,
        company_code=company,
        as_of=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        knowledge_version="ck-index-worker-v1",
        subject=CandidateKnowledgeSubject(display_name=str(app_key)),
        canonical_cv={
            "version_id": str(meta.get("version_id") or job.get("document_version_id") or f"v-{app_key}"),
            "document_id": str(meta.get("document_id") or f"d-{app_key}"),
            "content_hash": str(meta.get("content_hash") or job.get("idempotency_key") or app_key)[:64],
            "text": text,
            "channel": str(meta.get("channel") or app.get("data_source") or "email"),
        },
        actionability=Actionability(
            True,
            False if held else True,
            False if held else True,
            False if held else True,
            held_state=held,
        ),
    )
    application = {
        "company_code": company,
        "app_key": app_key,
        "phone": str(app.get("phone") or f"ck-{app_key}")[:64],
        "status": status,
        "data_source": str(app.get("data_source") or "email"),
        "position_code": str(app.get("position_code") or ""),
        "position_title": str(app.get("position_title") or ""),
    }
    indexer.index_from_knowledge_record(record, application=application)


def run_loop() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    env = load_runtime_env()
    # Pin process env from the resolved runtime map, but never let a later
    # staging overlay win over an explicit production WATHEFNI_ENV.
    for key, value in env.items():
        if key == "WATHEFNI_ENV" and str(os.environ.get("WATHEFNI_ENV") or "").lower() == "production":
            continue
        if key not in os.environ or key.startswith("WATHEFNI_") or key in {"VOYAGE_API_KEY", "CK_WORKER_CONCURRENCY"}:
            os.environ[key] = value
    env = load_runtime_env()

    if not workers_enabled(env):
        print("ck-index-worker: workers disabled; idle exit 0", flush=True)
        return 0

    expected_db = env.get("WATHEFNI_EXPECTED_DATABASE_NAME") or (
        "wathefni" if str(env.get("WATHEFNI_ENV") or "").lower() == "production" else "wathefni_staging"
    )
    connect = connect_factory(env)
    store = PostgresCandidateKnowledgeIndexStore(connect=connect)
    if str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA") or "").lower() in {"1", "true", "yes", "on"}:
        store.ensure_schema()

    use_voyage = str(env.get("WATHEFNI_CK_VOYAGE_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
    # Prefer explicit mock unless Voyage is enabled AND SDK importable.
    if use_voyage:
        try:
            import voyageai  # noqa: F401
        except Exception:
            print(json.dumps({"event": "ck_worker_voyage_sdk_missing_fallback_mock"}), flush=True)
            use_voyage = False
    embedder = build_embedding_provider(force_mock=not use_voyage)
    indexer = CandidateKnowledgeIndexer(store, embedder=embedder)
    owner = f"ck-worker-{uuid.uuid4().hex[:8]}"
    concurrency = max(1, int(env.get("CK_WORKER_CONCURRENCY") or "2"))
    tenants = [
        part.strip().upper()
        for part in str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS") or "").split(",")
        if part.strip()
    ]
    # One-shot DB identity proof for operators.
    with connect() as cur:
        cur.execute("SELECT current_database() AS db")
        connected_db = cur.fetchone()["db"]
    if connected_db != expected_db:
        raise RuntimeError(f"ck_worker_db_mismatch: connected={connected_db} expected={expected_db}")
    print(
        json.dumps(
            {
                "event": "ck_worker_start",
                "owner": owner,
                "tenants": tenants,
                "concurrency": concurrency,
                "embedder": getattr(embedder, "provider", "unknown"),
                "expected_db": expected_db,
                "connected_db": connected_db,
                "wathefni_env": env.get("WATHEFNI_ENV"),
            }
        ),
        flush=True,
    )

    idle_loops = 0
    while not STOP:
        env = load_runtime_env()
        if not workers_enabled(env):
            print("ck-index-worker: kill switch workers=off; exiting", flush=True)
            return 0
        claimed = 0
        for company in tenants:
            if not tenant_allowed(env, company):
                continue
            for _ in range(concurrency):
                job = store.claim_job(company_code=company, owner=owner, lease_seconds=120)
                if not job:
                    break
                claimed += 1
                try:
                    with connect() as cur:
                        cur.execute("SELECT current_database() AS db")
                        db = cur.fetchone()["db"]
                        if db != expected_db:
                            raise RuntimeError(f"refusing_db:{db}:expected:{expected_db}")
                        # Wave 3 epoch/lifecycle gate before side effects.
                        try:
                            import tenant_control_queue_gate as _tc_qg

                            queued_epoch = None
                            if isinstance(job.get("metadata"), dict):
                                queued_epoch = job["metadata"].get("activation_epoch")
                            if queued_epoch is None:
                                queued_epoch = _tc_qg.persist_work_epoch(
                                    cur,
                                    company_code=company,
                                    work_kind="candidate_knowledge_index",
                                    work_ref=str(job.get("job_id")),
                                    module_key="pre_hiring",
                                )
                            allowed, decision = _tc_qg.gate_or_skip(
                                cur,
                                company_code=company,
                                module_key="pre_hiring",
                                work_kind="candidate_knowledge_index",
                                work_ref=str(job.get("job_id")),
                                queued_epoch=int(queued_epoch),
                            )
                            if not allowed:
                                print(
                                    json.dumps(
                                        {
                                            "event": "ck_job_held_tenant_control",
                                            "job_id": str(job.get("job_id")),
                                            "reason": decision.reason_code,
                                            "correlation_id": decision.audit_correlation_id,
                                        }
                                    ),
                                    flush=True,
                                )
                                continue
                        except Exception:
                            pass
                    process_job(store=store, indexer=indexer, job=job)
                    store.complete_job(company_code=company, job_id=str(job["job_id"]))
                except Exception as exc:  # noqa: BLE001
                    store.complete_job(company_code=company, job_id=str(job["job_id"]), error=str(exc))
                    print(json.dumps({"event": "ck_job_failed", "job_id": str(job.get("job_id")), "error": str(exc)[:300]}), flush=True)
        if claimed == 0:
            idle_loops += 1
            time.sleep(1.0 if idle_loops < 30 else 2.0)
        else:
            idle_loops = 0
    print(json.dumps({"event": "ck_worker_stop", "owner": owner}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_loop())
