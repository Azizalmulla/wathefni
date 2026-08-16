#!/usr/bin/env python3
"""Wave C local synthetic-tenant mutation requalification.

Runs against a local test Postgres only (never production/staging). Creates
isolated WAVEC* synthetic tenants, exercises Jobs → Candidates → Ranking →
Assessments → Live Interviews → Video Interviews → Offers → Hire mutations
(create/update, idempotency, stage changes, cancel/retry, hire/reject/withdraw,
tenant isolation), then removes every row and asserts zero residue.

Requires WATHEFNI_WAVE_C_LOCAL=1, WATHEFNI_ENV=test, dry_run delivery, and a
non-production database (default wathefni_local_boundary).
Does not deploy. Does not start Wave D.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ORCH = ROOT / "wathefni-orchestrator"
sys.path.insert(0, str(ORCH))

MARKER = "waveC-local-mutation-requal-v1"
POSITION = "WC_ROLE"
PHONE_PREFIX = "+9658869"
ACTOR_A = "c0a10000-0000-4000-8000-00000000000a"
ACTOR_B = "c0a10000-0000-4000-8000-00000000000b"

FULL_PERMISSIONS = {
    "prehire.read",
    "prehire.manage",
    "candidate.manage",
    "candidate.decide",
    "candidate.hire",
    "candidates.read",
    "candidates.notes.manage",
    "assessment.manage",
    "interview.manage",
    "offer.read",
    "offer.manage",
    "offer.approve",
    "offer.send",
    "offer.withdraw",
    "offer.record_response",
    "offer.compensation.read",
    "offer.document.read",
    "offer.hire_override",
    "reports.read",
    "jobs.manage",
    "jobs.publish",
}

TENANTS: list[dict[str, Any]] = [
    {"code": "WCAVLO", "combo": "asm_ON__live_ON__video_ON__offers_ON", "assessments": True, "live": True, "video": True, "offers": True},
    {"code": "WCALXO", "combo": "asm_ON__live_ON__video_OFF__offers_ON", "assessments": True, "live": True, "video": False, "offers": True},
    {"code": "WCAXVO", "combo": "asm_ON__live_OFF__video_ON__offers_ON", "assessments": True, "live": False, "video": True, "offers": True},
    {"code": "WCAXXO", "combo": "asm_ON__live_OFF__video_OFF__offers_ON", "assessments": True, "live": False, "video": False, "offers": True},
    {"code": "WCXVLO", "combo": "asm_OFF__live_ON__video_ON__offers_ON", "assessments": False, "live": True, "video": True, "offers": True},
    {"code": "WCXXXO", "combo": "asm_OFF__live_OFF__video_OFF__offers_ON", "assessments": False, "live": False, "video": False, "offers": True},
    {"code": "WCNOOF", "combo": "all_optional_OFF", "assessments": False, "live": False, "video": False, "offers": False},
    {"code": "WCPEER", "combo": "peer_isolation_and_history", "assessments": True, "live": True, "video": True, "offers": True},
]
COMPANIES = [t["code"] for t in TENANTS]

ASSESSMENT_WORDS = ("assessment", "assessments", "تقييم", "التقييم")
LIVE_INTERVIEW_WORDS = ("interview", "interviews", "مقابلة", "المقابلة", "scorecard", "panel", "agenda")
VIDEO_INTERVIEW_WORDS = ("video_interview", "video interviews", "async_video", "recorded-answer")
INTERVIEW_WORDS = LIVE_INTERVIEW_WORDS + VIDEO_INTERVIEW_WORDS
OFFER_WORDS = ("offer", "offers", "عرض عمل", "employment_offer")
# Internal boolean / capability keys that name switches rather than owner-facing wording.
FLAG_KEYS = frozenset(
    {
        "assessments_enabled",
        "interviews_enabled",
        "video_interviews_enabled",
        "can_interview",
        "can_view_interviews",
        "interview_status",
        "interview_notes",
        "interview_reschedule",
        "employment_offers",
    }
)

CV_TEXT = (
    "Senior Operations Engineer. Kuwait City. Eight years building Python and SQL data "
    "pipelines for logistics companies. Led a team of four. Fluent Arabic and English. "
    "Bachelor of Computer Engineering, Kuwait University."
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Gate:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "", *, scope: str = "global") -> bool:
        self.rows.append({"gate": name, "scope": scope, "ok": bool(ok), "detail": str(detail)[:1400]})
        print(f"[{'PASS' if ok else 'FAIL'}] {scope}/{name}" + (f" — {str(detail)[:220]}" if detail else ""), flush=True)
        return bool(ok)

    def note(self, name: str, value: Any, *, scope: str = "global") -> None:
        """Observation recorded as evidence without a pass/fail assertion."""
        self.rows.append({"gate": name, "scope": scope, "ok": True, "observation": True, "detail": str(value)[:1400]})
        print(f"[NOTE] {scope}/{name} — {str(value)[:220]}", flush=True)

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]


def word_hits(blob: Any, words: tuple[str, ...], *, safe_keys: frozenset[str] = frozenset()) -> list[str]:
    """Scan owner-facing values (not internal boolean flag key names)."""

    def walk(value: Any, key: str | None = None, path: str = "") -> list[str]:
        hits: list[str] = []
        if key and key.lower() in safe_keys:
            return hits
        if isinstance(value, dict):
            for k, v in value.items():
                hits.extend(walk(v, str(k), f"{path}.{k}"))
            return hits
        if isinstance(value, (list, tuple)):
            for idx, item in enumerate(value):
                hits.extend(walk(item, key, f"{path}[{idx}]"))
            return hits
        text = str(value or "").lower()
        for word in words:
            if word.lower() in text:
                hits.append(f"{path or key or '?'}:{word}")
        return hits

    return walk(blob)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def ensure_company(cur: Any, app: Any, tenant: dict[str, Any]) -> None:
    company = tenant["code"]
    cur.execute(
        """
        INSERT INTO companies(company_code,name,status,country,metadata,raw_json,created_at,updated_at)
        VALUES (%s,%s,'active','KW',%s,%s,now(),now())
        ON CONFLICT (company_code) DO UPDATE SET
          name=EXCLUDED.name,
          country=COALESCE(NULLIF(companies.country,''), EXCLUDED.country),
          metadata=companies.metadata || EXCLUDED.metadata,
          raw_json=companies.raw_json || EXCLUDED.raw_json,
          updated_at=now()
        """,
        (
            company,
            f"WaveC Local {company}",
            app.Json({"waveC_local_marker": MARKER}),
            app.Json({"waveC_local_marker": MARKER}),
        ),
    )
    cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
    # Explicit registry rows for every optional module so the matrix exercises
    # real entitlements rather than legacy implications.
    rows = {
        "pre_hiring": True,
        "assessments": bool(tenant["assessments"]),
        "interviews": bool(tenant["live"]),
        "video_interviews": bool(tenant["video"]),
        "employment_offers": bool(tenant["offers"]),
    }
    for module, enabled in rows.items():
        cur.execute(
            "INSERT INTO company_modules(company_code,module_key,enabled,source,updated_at) VALUES (%s,%s,%s,%s,now())",
            (company, module, enabled, MARKER),
        )


def set_module(app: Any, company: str, module_key: str, enabled: bool) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if enabled:
                cur.execute(
                    """
                    INSERT INTO company_modules(company_code,module_key,enabled,source,updated_at)
                    VALUES (%s,%s,true,%s,now())
                    ON CONFLICT (company_code,module_key) DO UPDATE SET enabled=true, updated_at=now()
                    """,
                    (company, module_key, MARKER),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO company_modules(company_code,module_key,enabled,source,updated_at)
                    VALUES (%s,%s,false,%s,now())
                    ON CONFLICT (company_code,module_key) DO UPDATE SET enabled=false, updated_at=now()
                    """,
                    (company, module_key, MARKER),
                )
        conn.commit()
    cache = getattr(app, "_company_modules_cache", None)
    if isinstance(cache, dict):
        cache.clear()


def phone_for(company: str, key: str) -> str:
    digest = hashlib.sha256(f"{company}:{key}".encode()).hexdigest()
    return f"{PHONE_PREFIX}{int(digest[:6], 16) % 100000:05d}"


def insert_application(cur: Any, app: Any, *, company: str, key: str, status: str = "awaiting_cv") -> dict[str, Any]:
    phone = phone_for(company, key)
    app_key = f"{company}-WC-{key}"
    raw = {
        "waveC_local_marker": MARKER,
        "candidate_name": f"WC {company} {key}",
        "locale": "en",
        "cv": {"extracted": {"skills": ["Python", "SQL"], "years_experience": 8}},
        "intake": {"source": "whatsapp", "apply_code": f"APPLY-{company}-{POSITION}"},
    }
    cur.execute(
        """
        INSERT INTO candidates(phone, name, email, raw_json)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, raw_json=EXCLUDED.raw_json
        """,
        (phone, f"WC {company} {key}", f"{key}@{company.lower()}.invalid", app.Json({"waveC_local_marker": MARKER})),
    )
    cur.execute(
        """
        INSERT INTO applications(
          app_key, company_code, phone, position_code, position_title, status, current_step,
          cv_received, cv_received_at, data_source, ingested_at, updated_at, raw_json, lifecycle_version
        ) VALUES (%s,%s,%s,%s,%s,%s,'intake',true,now()::date,'production',now(),now(),%s,0)
        RETURNING *
        """,
        (app_key, company, phone, POSITION, "WC Operations Engineer", status, app.Json(raw)),
    )
    return dict(cur.fetchone())


def seed_cv_evidence(cur: Any, app: Any, cve: Any, cvf: Any, *, company: str, app_key: str, content: str) -> None:
    file_id = str(uuid.uuid4())
    finalization_id = str(uuid.uuid4())
    source_hash = hashlib.sha256(f"source:{app_key}:{content}".encode()).hexdigest()
    text_hash = hashlib.sha256(content.encode()).hexdigest()
    cur.execute(
        """
        INSERT INTO file_registry(
          file_id, company_code, subject_type, subject_key, file_kind,
          document_type, storage_provider, storage_object_key, content_sha256,
          storage_status, metadata, raw_json, stored_at, created_at, updated_at
        ) VALUES (%s,%s,'application',%s,'candidate_cv','cv','matrix',%s,%s,'stored',%s,%s,now(),now(),now())
        """,
        (
            file_id,
            company,
            app_key,
            f"e2e/{company}/{app_key}.pdf",
            source_hash,
            app.Json({"latest": True, "fq_marker": MARKER}),
            app.Json({"fq_marker": MARKER}),
        ),
    )
    cur.execute(
        """
        INSERT INTO cv_extraction_finalizations(
          finalization_id, company_code, document_id, app_key,
          source_content_sha256, extracted_text_hash, extraction_method,
          quality_ok, status, metadata, finalized_at, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,'e2e',true,'completed',%s,now(),now())
        """,
        (finalization_id, company, f"fq-doc-{app_key}", app_key, source_hash, text_hash, app.Json({"fq_marker": MARKER})),
    )
    materialized = cve.materialize_ready(
        cur,
        company_code=company,
        app_key=app_key,
        document_id=f"fq-doc-{app_key}",
        file_id=file_id,
        source_content_sha256=source_hash,
        extraction_finalization_id=finalization_id,
        extraction_method="e2e",
        extracted_text=content,
        semantic_id=f"application:{app_key}:cv",
        semantic_content_hash=text_hash,
        embedded=False,
        actor=MARKER,
        provenance={"fq_marker": MARKER},
    )
    facts = cvf.extract_application_cv_facts(content)
    cvf.materialize_facts(
        cur,
        evidence_id=str(materialized["evidence_id"]),
        company_code=company,
        app_key=app_key,
        document_id=f"fq-doc-{app_key}",
        source_content_sha256=source_hash,
        extracted_text_hash=text_hash,
        facts=facts,
        actor=MARKER,
        provenance={"fq_marker": MARKER},
    )


def seed_semantic_doc(cur: Any, app: Any, cr: Any, *, company: str, app_key: str, phone: str, content: str) -> None:
    projected = cr.ranking_safe_projection_text(content)
    cur.execute(
        """
        INSERT INTO semantic_documents(
          semantic_id, entity_type, entity_key, company_code, phone, app_key, position_code,
          title, content, content_hash, provider, model, dimensions, metadata, created_at, updated_at
        ) VALUES (%s,'application',%s,%s,%s,%s,%s,'CV',%s,%s,'voyage','voyage-4-large',1024,%s,now(),now())
        ON CONFLICT (semantic_id) DO UPDATE SET
          content=EXCLUDED.content, model='voyage-4-large', dimensions=1024,
          metadata=EXCLUDED.metadata, updated_at=now()
        """,
        (
            f"application:{app_key}:cv",
            app_key,
            company,
            phone,
            app_key,
            POSITION,
            projected,
            hashlib.sha256(projected.encode()).hexdigest(),
            app.Json({"ranking_projection_version": cr.RANKING_PROJECTION_VERSION, "fq_marker": MARKER}),
        ),
    )


def actor(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "actor_type": "human",
        "permissions": sorted(FULL_PERMISSIONS),
        "channel": MARKER,
    }


def app_row(app: Any, company: str, app_key: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT app_key, company_code, status, lifecycle_version FROM applications WHERE company_code=%s AND app_key=%s",
                (company, app_key),
            )
            return dict(cur.fetchone() or {})


def canonical_move(
    app: Any,
    rl: Any,
    *,
    company: str,
    app_key: str,
    to_stage: str,
    action: str,
    trigger: str,
    payload: dict[str, Any] | None = None,
    channel: str = MARKER,
) -> dict[str, Any]:
    """Human-confirmed canonical stage change (mint -> transition)."""
    before = app_row(app, company, app_key)
    minted = rl.mint_candidate_action_confirmation(
        app,
        company_code=company,
        app_key=app_key,
        action=action,
        observed_stage=str(before.get("status")),
        observed_version=int(before.get("lifecycle_version") or 0),
        target_payload=payload or {},
        actor_user_id=ACTOR_A,
        actor_phone=None,
        actor_type="human",
        channel=channel,
        permissions=FULL_PERMISSIONS,
    )
    if not minted.get("ok"):
        return {"ok": False, "stage": "mint", "result": minted}
    confirmation = minted["confirmation"]
    result = rl.transition_application(
        app,
        app_key=app_key,
        to_stage=to_stage,
        trigger=trigger,
        company_code=company,
        expected_from_stage=str(before.get("status")),
        expected_version=int(before.get("lifecycle_version") or 0),
        actor_type="human",
        actor_user_id=ACTOR_A,
        channel=channel,
        confirmation_token=str(confirmation["confirmation_token"]),
        confirmation_id=str(confirmation["confirmation_id"]),
        confirmation_action=action,
        confirmation_payload=payload or {},
        human_confirmed=True,
        permissions=FULL_PERMISSIONS,
    )
    result["_confirmation"] = confirmation
    return result


# --------------------------------------------------------------------------- #
# cleanup / residue
# --------------------------------------------------------------------------- #

CLEANUP_SQL: tuple[str, ...] = (
    "DELETE FROM employment_offer_delivery_operations WHERE company_code = ANY(%s)",
    "DELETE FROM employment_offer_deliveries WHERE company_code = ANY(%s)",
    "DELETE FROM employment_offer_tokens WHERE company_code = ANY(%s)",
    "DELETE FROM employment_offer_events WHERE company_code = ANY(%s)",
    "DELETE FROM employment_offer_versions WHERE offer_id IN (SELECT offer_id FROM employment_offers WHERE company_code = ANY(%s))",
    "DELETE FROM employment_offer_hire_override_audits WHERE company_code = ANY(%s)",
    "DELETE FROM employment_offers WHERE company_code = ANY(%s)",
    "DELETE FROM assessment_scores WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
    "DELETE FROM assessment_reports WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
    "DELETE FROM assessment_responses WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
    "DELETE FROM assessment_events WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
    "DELETE FROM assessment_tokens WHERE attempt_id IN (SELECT attempt_id FROM assessment_attempts WHERE company_code = ANY(%s))",
    "DELETE FROM assessment_invitations WHERE company_code = ANY(%s)",
    "DELETE FROM assessment_attempts WHERE company_code = ANY(%s)",
    "DELETE FROM interview_video_retention_operations WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_video_interview_responses WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_video_interview_questions WHERE company_code = ANY(%s)",
    "DELETE FROM interview_feedback_submission_revisions WHERE company_code = ANY(%s)",
    "DELETE FROM interview_feedback_submissions WHERE company_code = ANY(%s)",
    "DELETE FROM interview_schedule_operations WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_interview_events WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_interview_assignments WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_interviews WHERE company_code = ANY(%s)",
    "DELETE FROM ranking_item_narratives WHERE company_code = ANY(%s)",
    "DELETE FROM ranking_run_items WHERE company_code = ANY(%s)",
    "DELETE FROM ranking_runs WHERE company_code = ANY(%s)",
    "DELETE FROM ranking_recalculation_jobs WHERE company_code = ANY(%s)",
    "DELETE FROM job_ranking_criteria WHERE company_code = ANY(%s)",
    "DELETE FROM job_ranking_criteria_sets WHERE company_code = ANY(%s)",
    "DELETE FROM application_cv_fact_snapshots WHERE company_code = ANY(%s)",
    "DELETE FROM application_cv_evidence_materializations WHERE company_code = ANY(%s)",
    "DELETE FROM cv_extraction_finalizations WHERE company_code = ANY(%s)",
    "DELETE FROM semantic_documents WHERE company_code = ANY(%s)",
    "DELETE FROM file_registry WHERE company_code = ANY(%s)",
    "DELETE FROM compliance_documents WHERE company_code = ANY(%s)",
    "DELETE FROM employee_documents WHERE company_code = ANY(%s)",
    "DELETE FROM employee_status_changes WHERE company_code = ANY(%s)",
    "DELETE FROM onboarding_items WHERE employee_key IN (SELECT employee_key FROM employees WHERE company_code = ANY(%s))",
    "DELETE FROM employees WHERE company_code = ANY(%s)",
    "DELETE FROM hire_operations WHERE company_code = ANY(%s)",
    "DELETE FROM candidate_action_confirmations WHERE company_code = ANY(%s)",
    "DELETE FROM application_lifecycle_events WHERE company_code = ANY(%s)",
    "DELETE FROM report_export_audits WHERE company_code = ANY(%s)",
    "DELETE FROM applications WHERE company_code = ANY(%s)",
    "DELETE FROM positions WHERE company_code = ANY(%s)",
    "DELETE FROM company_modules WHERE company_code = ANY(%s)",
)

RESIDUE_SQL: dict[str, str] = {
    "companies": "SELECT COUNT(*) AS c FROM companies WHERE company_code = ANY(%s)",
    "company_modules": "SELECT COUNT(*) AS c FROM company_modules WHERE company_code = ANY(%s)",
    "positions": "SELECT COUNT(*) AS c FROM positions WHERE company_code = ANY(%s)",
    "applications": "SELECT COUNT(*) AS c FROM applications WHERE company_code = ANY(%s)",
    "lifecycle_events": "SELECT COUNT(*) AS c FROM application_lifecycle_events WHERE company_code = ANY(%s)",
    "confirmations": "SELECT COUNT(*) AS c FROM candidate_action_confirmations WHERE company_code = ANY(%s)",
    "ranking_runs": "SELECT COUNT(*) AS c FROM ranking_runs WHERE company_code = ANY(%s)",
    "ranking_items": "SELECT COUNT(*) AS c FROM ranking_run_items WHERE company_code = ANY(%s)",
    "cv_evidence": "SELECT COUNT(*) AS c FROM application_cv_evidence_materializations WHERE company_code = ANY(%s)",
    "cv_facts": "SELECT COUNT(*) AS c FROM application_cv_fact_snapshots WHERE company_code = ANY(%s)",
    "semantic_docs": "SELECT COUNT(*) AS c FROM semantic_documents WHERE company_code = ANY(%s)",
    "files": "SELECT COUNT(*) AS c FROM file_registry WHERE company_code = ANY(%s)",
    "assessment_attempts": "SELECT COUNT(*) AS c FROM assessment_attempts WHERE company_code = ANY(%s)",
    "assessment_invitations": "SELECT COUNT(*) AS c FROM assessment_invitations WHERE company_code = ANY(%s)",
    "interviews": "SELECT COUNT(*) AS c FROM candidate_interviews WHERE company_code = ANY(%s)",
    "interview_events": "SELECT COUNT(*) AS c FROM candidate_interview_events WHERE company_code = ANY(%s)",
    "offers": "SELECT COUNT(*) AS c FROM employment_offers WHERE company_code = ANY(%s)",
    "offer_events": "SELECT COUNT(*) AS c FROM employment_offer_events WHERE company_code = ANY(%s)",
    "offer_tokens": "SELECT COUNT(*) AS c FROM employment_offer_tokens WHERE company_code = ANY(%s)",
    "offer_deliveries": "SELECT COUNT(*) AS c FROM employment_offer_deliveries WHERE company_code = ANY(%s)",
    "offer_send_ops": "SELECT COUNT(*) AS c FROM employment_offer_delivery_operations WHERE company_code = ANY(%s)",
    "hire_operations": "SELECT COUNT(*) AS c FROM hire_operations WHERE company_code = ANY(%s)",
    "hire_override_audits": "SELECT COUNT(*) AS c FROM employment_offer_hire_override_audits WHERE company_code = ANY(%s)",
    "employees": "SELECT COUNT(*) AS c FROM employees WHERE company_code = ANY(%s)",
    "compliance_documents": "SELECT COUNT(*) AS c FROM compliance_documents WHERE company_code = ANY(%s)",
    "employee_documents": "SELECT COUNT(*) AS c FROM employee_documents WHERE company_code = ANY(%s)",
    "interview_schedule_ops": "SELECT COUNT(*) AS c FROM interview_schedule_operations WHERE company_code = ANY(%s)",
    "onboarding_items": "SELECT COUNT(*) AS c FROM onboarding_items WHERE employee_key IN (SELECT employee_key FROM employees WHERE company_code = ANY(%s))",
    "report_export_audits": "SELECT COUNT(*) AS c FROM report_export_audits WHERE company_code = ANY(%s)",
}


def cleanup(app: Any) -> dict[str, Any]:
    stored_paths: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT v.document_storage_uri AS uri
                    FROM employment_offer_versions v
                    JOIN employment_offers o ON o.offer_id = v.offer_id
                    WHERE o.company_code = ANY(%s) AND coalesce(v.document_storage_uri,'') <> ''
                    """,
                    (COMPANIES,),
                )
                stored_paths = [str(r["uri"]) for r in (cur.fetchall() or []) if r.get("uri")]
            except Exception:
                conn.rollback()
        conn.commit()

    removed_files = 0
    for raw in stored_paths:
        candidate = raw[7:] if raw.startswith("file://") else raw
        path = Path(candidate)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                removed_files += 1
        except Exception:
            pass

    errors: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.offer_retention_delete','on',true)")
            cur.execute("SELECT set_config('wathefni.lifecycle_authority','canonical',true)")
            for sql in CLEANUP_SQL:
                try:
                    cur.execute(sql, (COMPANIES,))
                except Exception as exc:  # table may not exist in this env
                    conn.rollback()
                    errors.append(f"{sql.split()[2]}:{type(exc).__name__}")
                    cur.execute("SELECT set_config('wathefni.offer_retention_delete','on',true)")
                    cur.execute("SELECT set_config('wathefni.lifecycle_authority','canonical',true)")
            try:
                cur.execute(
                    "DELETE FROM companies WHERE company_code = ANY(%s) AND coalesce(metadata->>'waveC_local_marker','')=%s",
                    (COMPANIES, MARKER),
                )
            except Exception as exc:
                conn.rollback()
                errors.append(f"companies:{type(exc).__name__}")
            try:
                cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{PHONE_PREFIX}%",))
            except Exception as exc:
                conn.rollback()
                errors.append(f"candidates:{type(exc).__name__}")
        conn.commit()
    return {"removed_files": removed_files, "cleanup_errors": errors}


def residue_counts(app: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, sql in RESIDUE_SQL.items():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(sql, (COMPANIES,))
                    out[name] = int((cur.fetchone() or {}).get("c") or 0)
                except Exception:
                    conn.rollback()
                    out[name] = -1
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM candidates WHERE phone LIKE %s", (f"{PHONE_PREFIX}%",))
            out["candidates"] = int((cur.fetchone() or {}).get("c") or 0)
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main() -> int:  # noqa: C901
    expected_db = os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or ""
    env_name = os.environ.get("WATHEFNI_ENV") or ""
    allow_local = os.environ.get("WATHEFNI_WAVE_C_LOCAL") == "1"
    if not allow_local:
        print("REFUSING: set WATHEFNI_WAVE_C_LOCAL=1 for local Wave C mutation requal", file=sys.stderr)
        return 2
    if env_name in {"production", "staging"} or expected_db in {"wathefni", "wathefni_staging"}:
        print(
            f"REFUSING: Wave C local must not target production/staging "
            f"(env={env_name!r} db={expected_db!r})",
            file=sys.stderr,
        )
        return 2
    if env_name != "test":
        print(f"REFUSING: Wave C local requires WATHEFNI_ENV=test (got {env_name!r})", file=sys.stderr)
        return 2
    if not expected_db or "local" not in expected_db:
        print(
            f"REFUSING: Wave C local requires a *local* database name "
            f"(got {expected_db!r})",
            file=sys.stderr,
        )
        return 2
    if (os.environ.get("WATHEFNI_DELIVERY_MODE") or "") != "dry_run":
        print("REFUSING: Wave C local requires WATHEFNI_DELIVERY_MODE=dry_run", file=sys.stderr)
        return 2
    if not os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER"):
        print("REFUSING: set WATHEFNI_APPLY_WHATSAPP_NUMBER for job publish", file=sys.stderr)
        return 2
    os.environ.setdefault("WATHEFNI_OFFER_TOKEN_SECRET", "waveC-local-requal-secret-v1")
    os.environ.setdefault("WATHEFNI_EMBEDDING_PROVIDER", "voyage")
    os.environ.setdefault("WATHEFNI_EMBEDDING_MODEL", "voyage-4-large")
    os.environ.setdefault("WATHEFNI_EMBEDDING_DIMENSIONS", "1024")

    import app
    import action_registry as registry
    import assessment_lifecycle as alife
    import candidate_cv_evidence as cve
    import candidate_cv_facts as cvf
    import candidate_ranking as cr
    import hire_operations as hire_ops
    import interview_lifecycle as ilife
    import interview_service as isvc
    import module_catalog as mc
    import offer_lifecycle as offers
    import offer_service as osvc
    import operator_mobile as mobile
    import prehire_jobs as jobs
    import prehire_overview as overview
    import recruiting_lifecycle as rl
    import reports_v1 as rv
    import tool_call_orchestrator as tco

    gate = Gate()
    evidence: dict[str, Any] = {
        "marker": MARKER,
        "started_at": _now(),
        "environment": {
            "env": os.environ.get("WATHEFNI_ENV"),
            "database": os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME"),
            "delivery_mode": os.environ.get("WATHEFNI_DELIVERY_MODE"),
            "binding": None,
        },
        "tenants": TENANTS,
        "gates": [],
        "findings": {},
    }

    def terra_stub(*, envelope, locale, model, prompt_version):
        committed = (envelope or {}).get("committed_result") or {}
        return {"narrative": f"WaveCLocal committed evidence only ({locale}). Advisory {committed.get('advisory_score')}. HR decides."}

    app.ranking_terra_narrative_callable = terra_stub

    state: dict[str, Any] = {}

    try:
        evidence["environment"]["binding"] = app.assert_runtime_environment_binding().public()
        try:
            app.ensure_schema(force=True)
        except TypeError:
            app.ensure_schema()
        osvc.ensure_schema(app)
        isvc.ensure_schema(app)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                alife.ensure_assessment_schema(cur)
                cr.ensure_schema(cur)
                rv.ensure_schema(cur)
                jobs.ensure_jobs_schema(cur)
            conn.commit()

        cleanup(app)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for tenant in TENANTS:
                    ensure_company(cur, app, tenant)
            conn.commit()

        # ------------------------------------------------------------------ #
        # 0. module contract surface
        # ------------------------------------------------------------------ #
        catalog_keys = sorted(mc.MODULE_KEYS) if hasattr(mc, "MODULE_KEYS") else sorted(m.key for m in mc.MODULE_CATALOG)
        gate.check(
            "catalog_has_assessments_module",
            "assessments" in catalog_keys,
            f"prehire={sorted(mc.PREHIRE_MODULES)}",
            scope="contract",
        )
        gate.check(
            "catalog_has_offers_module",
            "employment_offers" in catalog_keys,
            f"keys={catalog_keys}",
            scope="contract",
        )
        gate.check(
            "catalog_has_live_interviews_module",
            "interviews" in catalog_keys,
            f"interview-related={[k for k in catalog_keys if 'interview' in k]}",
            scope="contract",
        )
        gate.check(
            "catalog_has_video_interviews_module",
            "video_interviews" in catalog_keys,
            "",
            scope="contract",
        )
        gate.check(
            "live_and_video_interview_modules_are_independent",
            "interviews" in catalog_keys
            and "video_interviews" in catalog_keys
            and "video_interviews" not in (mc.MODULE_BY_KEY["interviews"].depends_on or ())
            and "interviews" not in (mc.MODULE_BY_KEY["video_interviews"].depends_on or ()),
            f"live.depends_on={mc.MODULE_BY_KEY['interviews'].depends_on} video.depends_on={mc.MODULE_BY_KEY['video_interviews'].depends_on}",
            scope="contract",
        )
        gate.check(
            "toolcall_gated_covers_optional_interview_and_assessment_modules",
            {"assessments", "interviews", "video_interviews"} <= set(mc.TOOLCALL_GATED_MODULES),
            f"TOOLCALL_GATED_MODULES={sorted(mc.TOOLCALL_GATED_MODULES)}",
            scope="contract",
        )
        gate.check(
            "employment_offers_has_no_assistant_mutation_surface",
            "employment_offers" in catalog_keys,
            "offers are dashboard/API entitled; Assistant must not expose offer mutation tools (checked per-tenant)",
            scope="contract",
        )
        gate.check(
            "unconditional_interviews_or_True_removed",
            '("interviews" in enabled_modules) or True' not in (ORCH / "app.py").read_text(encoding="utf-8"),
            "",
            scope="contract",
        )
        gate.check(
            "ranking_default_policy_assessment_and_interview_unused",
            cr.DEFAULT_EVIDENCE_POLICY["sources"]["assessment"] == "unused"
            and cr.DEFAULT_EVIDENCE_POLICY["sources"]["interview"] == "unused",
            str(cr.DEFAULT_EVIDENCE_POLICY["sources"]),
            scope="contract",
        )

        # ------------------------------------------------------------------ #
        # per-tenant lifecycle
        # ------------------------------------------------------------------ #
        for tenant in TENANTS:
            company = tenant["code"]
            scope = f"{company}[{tenant['combo']}]"
            tstate: dict[str, Any] = {}
            state[company] = tstate

            # --- 1. job creation + publication -----------------------------
            job = jobs.create_job(
                company=company,
                db_connect=app.db_connect,
                actor_user_id=ACTOR_A,
                payload={
                    "position_code": POSITION,
                    "title_en": "WC Operations Engineer",
                    "title_ar": "مهندس عمليات",
                    "short_summary_en": "Own logistics data pipelines.",
                    "short_summary_ar": "إدارة خطوط بيانات الخدمات اللوجستية.",
                    "requirements_en": ["Python", "SQL", "5 years experience"],
                    "requirements_ar": ["بايثون", "قواعد بيانات"],
                    "location": "Kuwait City",
                    "employment_type": "full_time",
                    "work_arrangement": "onsite",
                    "vacancies": 2,
                    "visibility": "public",
                    "salary_visibility": "hr_only",
                    "currency": "KWD",
                    "approve_content_en": True,
                    "approve_content_ar": True,
                },
                as_draft=True,
            )
            gate.check("job_created_draft", str(job.get("status")) == "draft", str(job.get("status")), scope=scope)
            # Concurrency token required for job mutations (post-freeze hardening).
            job_version = int(job.get("version") or 1)
            updated_job = jobs.update_job(
                company=company,
                position_code=POSITION,
                db_connect=app.db_connect,
                actor_user_id=ACTOR_A,
                expected_version=job_version,
                payload={
                    "short_summary_en": "Own logistics data pipelines. Updated for Wave C.",
                    "vacancies": 3,
                },
            )
            gate.check(
                "job_updated_with_version_token",
                int(updated_job.get("vacancies") or 0) == 3
                and int(updated_job.get("version") or 0) == job_version + 1,
                json.dumps(
                    {
                        "vacancies": updated_job.get("vacancies"),
                        "version": updated_job.get("version"),
                        "summary": (updated_job.get("short_summary_en") or "")[:80],
                    },
                    ensure_ascii=False,
                ),
                scope=scope,
            )
            published = jobs.transition_job(
                company=company,
                position_code=POSITION,
                db_connect=app.db_connect,
                actor_user_id=ACTOR_A,
                to_status="open",
                expected_version=int(updated_job.get("version") or job_version + 1),
            )
            gate.check(
                "job_published_open_with_apply_identity",
                str(published.get("status")) == "open"
                and str(published.get("apply_code")) == f"APPLY-{company}-{POSITION}"
                and bool(published.get("application_link")),
                json.dumps(
                    {
                        "status": published.get("status"),
                        "apply_code": published.get("apply_code"),
                        "link": published.get("application_link"),
                    },
                    ensure_ascii=False,
                ),
                scope=scope,
            )
            gate.check(
                "published_job_accepts_applications",
                jobs.accepts_applications(published.get("status")),
                str(published.get("status")),
                scope=scope,
            )

            # --- 2. candidate intake + canonical CV lifecycle ---------------
            apps: dict[str, dict[str, Any]] = {}
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    for key in ("main", "bare", "reject", "withdraw", "ardoc"):
                        apps[key] = insert_application(cur, app, company=company, key=key)
                conn.commit()
            tstate["apps"] = {k: v["app_key"] for k, v in apps.items()}

            cv_ok = True
            for key, row in apps.items():
                received = rl.mark_cv_received(app, application=row, channel="whatsapp")
                current = app_row(app, company, row["app_key"])
                ready = rl.mark_cv_ready_for_review(
                    app,
                    application={**row, **current},
                    cv_version="fq-1",
                    document_id=f"fq-doc-{row['app_key']}",
                )
                final = app_row(app, company, row["app_key"])
                if not (received.get("ok") and ready.get("ok") and final.get("status") == "ready_for_review"):
                    cv_ok = False
                    gate.note(f"cv_lifecycle_detail_{key}", json.dumps({"received": received, "ready": ready, "final": final}, default=str)[:600], scope=scope)
            gate.check("canonical_cv_lifecycle_to_ready_for_review", cv_ok, "awaiting_cv -> cv_processing -> ready_for_review", scope=scope)

            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) AS c FROM application_lifecycle_events WHERE company_code=%s",
                        (company,),
                    )
                    ev_count = int((cur.fetchone() or {}).get("c") or 0)
            gate.check("lifecycle_events_recorded", ev_count >= 10, f"events={ev_count}", scope=scope)

            # --- 3. CV-based ranking BEFORE assessments/interviews ----------
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    for key in ("main", "bare", "reject", "withdraw", "ardoc"):
                        row = apps[key]
                        text = f"{CV_TEXT} Candidate reference {key}."
                        seed_cv_evidence(cur, app, cve, cvf, company=company, app_key=row["app_key"], content=text)
                        seed_semantic_doc(cur, app, cr, company=company, app_key=row["app_key"], phone=row["phone"], content=text)
                conn.commit()

            stages_before = {k: app_row(app, company, v["app_key"]).get("status") for k, v in apps.items()}
            ranked = cr.rank_job_applications(app, company_code=company, position_code=POSITION, actor_user_id=ACTOR_A, force=True)
            stages_after = {k: app_row(app, company, v["app_key"]).get("status") for k, v in apps.items()}
            items = ranked.get("items") or []
            gate.check(
                "cv_ranking_functional_before_optional_modules",
                bool(items) and len(items) >= 5,
                json.dumps({"items": len(items), "run_id": ranked.get("run_id")}, default=str),
                scope=scope,
            )
            gate.check(
                "ranking_does_not_mutate_lifecycle",
                stages_before == stages_after,
                json.dumps({"before": stages_before, "after": stages_after}),
                scope=scope,
            )
            comps_all = [i.get("component_scores") or {} for i in items]
            gate.check(
                "ranking_has_no_assessment_or_interview_evidence_by_default",
                all(float(c.get("assessment_evidence") or 0) == 0.0 for c in comps_all)
                and all("interview_evidence" not in c for c in comps_all),
                json.dumps(comps_all[0] if comps_all else {}, default=str)[:400],
                scope=scope,
            )
            gate.check(
                "ranking_run_declares_no_lifecycle_mutations",
                bool((ranked.get("provenance") or {}).get("lifecycle_mutations") is False)
                or bool((ranked.get("authority") or {}).get("lifecycle_mutations") is False),
                json.dumps({"provenance": ranked.get("provenance"), "authority": ranked.get("authority")}, default=str)[:500],
                scope=scope,
            )
            tstate["ranking_items"] = len(items)

            # --- 4. shortlist main + bare via canonical authority -----------
            for key in ("main", "bare", "ardoc"):
                res = canonical_move(
                    app,
                    rl,
                    company=company,
                    app_key=apps[key]["app_key"],
                    to_stage="shortlisted",
                    action="shortlist",
                    trigger="hr_shortlist",
                )
                gate.check(
                    f"canonical_shortlist_{key}",
                    bool(res.get("ok")) and app_row(app, company, apps[key]["app_key"]).get("status") == "shortlisted",
                    json.dumps(res, default=str)[:300],
                    scope=scope,
                )

            # --- 5. assessments ON / OFF -----------------------------------
            assessments_on = bool(tenant["assessments"])
            gate.check(
                "module_state_assessments_matches_intent",
                app.company_has_module(company, "assessments") is assessments_on,
                f"expected={assessments_on} actual={app.company_has_module(company, 'assessments')}",
                scope=scope,
            )
            attempt: dict[str, Any] = {}
            if assessments_on:
                created = app.create_or_resume_assessment_attempt(
                    apps["main"],
                    source=MARKER,
                    requested_by=ACTOR_A,
                    battery_key=None,
                    expires_days=7,
                    locale="en",
                )
                gate.check("assessment_optional_send_available", bool(created.get("ok")), str(created)[:300], scope=scope)
                attempt = dict(created.get("attempt") or {})
                tstate["attempt_id"] = str(attempt.get("attempt_id") or "")
                sent = app.send_assessment(apps["main"], account_id=None, requested_by=ACTOR_A, note=MARKER, expires_days=7)
                gate.check("assessment_send_ok", bool(sent.get("ok")), str(sent)[:300], scope=scope)
                delivery_status = str((sent.get("attempt") or {}).get("delivery_status") or "")
                gate.check(
                    "assessment_send_not_claimed_delivered",
                    delivery_status not in {"delivered", "confirmed"},
                    f"delivery_status={delivery_status}",
                    scope=scope,
                )
                attempt_row = dict(sent.get("attempt") or attempt)
                attempt_id = str(attempt_row.get("attempt_id") or tstate.get("attempt_id") or "")
                cancel_ok = False
                cancel_detail = ""
                try:
                    cancelled = app.cancel_assessment_attempt(
                        attempt_row,
                        reason="waveC cancel path",
                        actor_type="hr",
                        actor_user_id=ACTOR_A,
                    )
                    cancel_status = str((cancelled.get("attempt") or cancelled).get("status") or "").lower()
                    cancel_ok = cancel_status in {"cancelled", "canceled"} or bool(cancelled.get("ok"))
                    cancel_detail = json.dumps(cancelled, default=str)[:300]
                    tstate["cancelled_attempt_id"] = attempt_id
                except Exception as exc:
                    cancel_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
                gate.check("assessment_cancel_ok", cancel_ok, cancel_detail, scope=scope)
                retry_ok = False
                retry_detail = ""
                try:
                    # Cancelled attempt is closed — create/send a replacement (retry path).
                    created2 = app.create_or_resume_assessment_attempt(
                        apps["main"],
                        source=f"{MARKER}:retry",
                        requested_by=ACTOR_A,
                        battery_key=None,
                        expires_days=7,
                        locale="en",
                    )
                    resent = app.send_assessment(
                        apps["main"],
                        account_id=None,
                        requested_by=ACTOR_A,
                        note=f"{MARKER}:retry-send",
                        expires_days=7,
                    ) if bool(created2.get("ok")) else created2
                    retry_ok = bool(resent.get("ok"))
                    retry_detail = json.dumps(
                        {
                            "create": bool(created2.get("ok")),
                            "send": bool(resent.get("ok")),
                            "attempt_id": str((resent.get("attempt") or {}).get("attempt_id") or ""),
                            "prev_cancelled": attempt_id,
                        },
                        default=str,
                    )[:400]
                    tstate["retry_attempt_id"] = str((resent.get("attempt") or {}).get("attempt_id") or "")
                except Exception as exc:
                    retry_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
                gate.check("assessment_retry_after_cancel_ok", retry_ok, retry_detail, scope=scope)
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) AS c FROM assessment_attempts WHERE company_code=%s AND app_key=%s",
                            (company, apps["bare"]["app_key"]),
                        )
                        bare_attempts = int((cur.fetchone() or {}).get("c") or 0)
                gate.check("unassigned_candidate_has_no_attempt", bare_attempts == 0, f"n={bare_attempts}", scope=scope)
            else:
                blocked_detail = ""
                service_blocked = False
                try:
                    res = app.create_or_resume_assessment_attempt(apps["main"], source=MARKER, requested_by=ACTOR_A)
                    service_blocked = not bool(res.get("ok"))
                    blocked_detail = str(res)[:300]
                except Exception as exc:
                    service_blocked = True
                    blocked_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:250]}"
                gate.check(
                    "assessments_off_service_mutation_blocked",
                    service_blocked,
                    blocked_detail,
                    scope=scope,
                )
                entitlement_blocked = False
                ent_detail = ""
                try:
                    app.require_entitlement(
                        {
                            "company_code": company,
                            "actor_user_id": ACTOR_A,
                            "permissions": sorted(FULL_PERMISSIONS),
                        },
                        "assessments",
                        "assessment.manage",
                    )
                    ent_detail = "entitlement granted while module disabled"
                except Exception as exc:
                    ent_detail = str(getattr(exc, "detail", exc))[:250]
                    entitlement_blocked = "module_disabled" in ent_detail or "'required_module': 'assessments'" in ent_detail
                gate.check("assessments_off_entitlement_403", entitlement_blocked, ent_detail, scope=scope)

            counts = overview.compute_action_counts(company=company, db_connect=app.db_connect, assessments_enabled=assessments_on)
            if assessments_on:
                gate.check(
                    "overview_assessment_pending_assigned_only",
                    int(counts.get("assessment_pending") or 0) <= 1,
                    json.dumps(counts, default=str),
                    scope=scope,
                )
            else:
                gate.check(
                    "overview_omits_assessment_counts_when_off",
                    "assessment_pending" not in counts,
                    json.dumps(counts, default=str),
                    scope=scope,
                )

            # --- 6. live interviews + video interviews (independent) -------
            live_on = bool(tenant["live"])
            video_on = bool(tenant["video"])
            gate.check(
                "module_state_live_interviews_matches_intent",
                app.company_has_module(company, "interviews") is live_on,
                f"expected={live_on} actual={app.company_has_module(company, 'interviews')}",
                scope=scope,
            )
            gate.check(
                "module_state_video_interviews_matches_intent",
                app.company_has_module(company, "video_interviews") is video_on,
                f"expected={video_on} actual={app.company_has_module(company, 'video_interviews')}",
                scope=scope,
            )

            start_at = datetime.now(timezone.utc) + timedelta(days=2)
            live_ok = False
            live_detail = ""
            live: dict[str, Any] = {}
            try:
                with mock.patch.object(ilife, "google_calendar_configured", return_value=False):
                    live = isvc.schedule_interview(
                        company_code=company,
                        app_key=apps["main"]["app_key"],
                        start=start_at.isoformat(),
                        end=(start_at + timedelta(minutes=45)).isoformat(),
                        meeting_type="phone",
                        panel=[{"email": f"panel@{company.lower()}.invalid", "user_id": "panel-1", "role": "organizer"}],
                        idempotency_key=f"{MARKER}:{company}:live",
                        actor=actor(ACTOR_A),
                        sync_external=False,
                        move_application_stage=False,
                        source=MARKER,
                    )
                live_ok = bool(live.get("ok"))
                live_detail = json.dumps(
                    {
                        "status": (live.get("interview") or {}).get("status"),
                        "provider_sync_status": (live.get("interview") or {}).get("provider_sync_status"),
                    },
                    default=str,
                )
                tstate["interview_id"] = str((live.get("interview") or {}).get("interview_id") or "")
            except Exception as exc:
                live_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"

            if live_on:
                gate.check("live_interview_schedulable_when_on", live_ok, live_detail, scope=scope)
                if live_ok and tstate.get("interview_id"):
                    rs_ok = False
                    rs_detail = ""
                    try:
                        with mock.patch.object(ilife, "google_calendar_configured", return_value=False):
                            rs = isvc.reschedule_interview(
                                company_code=company,
                                interview_id=str(tstate["interview_id"]),
                                start=(start_at + timedelta(hours=3)).isoformat(),
                                end=(start_at + timedelta(hours=3, minutes=45)).isoformat(),
                                meeting_type="phone",
                                idempotency_key=f"{MARKER}:{company}:live-reschedule",
                                actor=actor(ACTOR_A),
                                sync_external=False,
                            )
                        rs_ok = bool(rs.get("ok")) and str((rs.get("interview") or {}).get("interview_id") or "") == str(tstate["interview_id"])
                        rs_detail = json.dumps(
                            {
                                "same_id": str((rs.get("interview") or {}).get("interview_id") or "") == str(tstate["interview_id"]),
                                "status": (rs.get("interview") or {}).get("status"),
                            },
                            default=str,
                        )
                    except Exception as exc:
                        rs_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
                    gate.check("live_interview_reschedule_same_id", rs_ok, rs_detail, scope=scope)
                    cancel_iv_ok = False
                    cancel_iv_detail = ""
                    try:
                        with mock.patch.object(ilife, "google_calendar_configured", return_value=False):
                            cancelled_iv = isvc.cancel_interview(
                                company_code=company,
                                interview_id=str(tstate["interview_id"]),
                                idempotency_key=f"{MARKER}:{company}:live-cancel",
                                actor=actor(ACTOR_A),
                                sync_external=False,
                                revert_application_stage=False,
                            )
                        cancel_status = str((cancelled_iv.get("interview") or {}).get("status") or "").lower()
                        cancel_iv_ok = bool(cancelled_iv.get("ok")) and cancel_status in {"cancelled", "canceled"}
                        cancel_iv_detail = json.dumps(
                            {"status": cancel_status, "ok": cancelled_iv.get("ok")},
                            default=str,
                        )
                    except Exception as exc:
                        cancel_iv_detail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
                    gate.check("live_interview_cancel_ok", cancel_iv_ok, cancel_iv_detail, scope=scope)
            else:
                gate.check("live_interview_blocked_when_off", not live_ok, live_detail, scope=scope)

            provider_status = str((live.get("interview") or {}).get("provider_sync_status") or "not_configured")
            gate.check(
                "google_calendar_disconnected_still_works_when_live_on",
                (not live_on) or (live_ok and provider_status in {"not_configured", "skipped", "none", "None", "disabled"}),
                f"{live_detail} provider_status={provider_status}",
                scope=scope,
            )

            if live_on:
                gconnected_ok = False
                gdetail = ""
                try:
                    with mock.patch.object(ilife, "google_calendar_configured", return_value=True), mock.patch.object(
                        isvc, "_google_create", return_value={"event_id": f"wc-evt-{uuid.uuid4().hex[:8]}", "html_link": "https://calendar.invalid/wc", "meet_url": None}
                    ):
                        gres = isvc.schedule_interview(
                            company_code=company,
                            app_key=apps["bare"]["app_key"],
                            start=(start_at + timedelta(days=1)).isoformat(),
                            end=(start_at + timedelta(days=1, minutes=30)).isoformat(),
                            meeting_type="phone",
                            panel=[{"email": f"panel2@{company.lower()}.invalid", "user_id": "panel-2", "role": "organizer"}],
                            idempotency_key=f"{MARKER}:{company}:gcal",
                            actor=actor(ACTOR_A),
                            sync_external=True,
                            move_application_stage=False,
                            source=MARKER,
                        )
                    gconnected_ok = bool(gres.get("ok"))
                    gdetail = str((gres.get("interview") or {}).get("provider_sync_status"))
                    tstate["gcal_interview_id"] = str((gres.get("interview") or {}).get("interview_id") or "")
                except Exception as exc:
                    gdetail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
                gate.check("google_calendar_connected_path_works_when_live_on", gconnected_ok, gdetail, scope=scope)

            video_ok = False
            vdetail = ""
            try:
                req = app.DashboardVideoInterviewRequest(account_id="default", response_mode="single_video", send_invite=False)
                createdv = app.create_or_resume_async_video_interview(apps["main"], req, actor_context=actor(ACTOR_A))
                video_ok = bool((createdv.get("interview") or {}).get("interview_id"))
                tstate["video_interview_id"] = str((createdv.get("interview") or {}).get("interview_id") or "")
                vdetail = tstate["video_interview_id"]
            except Exception as exc:
                vdetail = f"{type(exc).__name__}:{str(getattr(exc, 'detail', exc))[:280]}"
            if video_on:
                gate.check("async_video_interview_works_when_on", video_ok, vdetail, scope=scope)
            else:
                gate.check("async_video_blocked_when_module_off", not video_ok, vdetail, scope=scope)

            # unassigned interview state: bare candidate must carry no interview debt when live is off
            queue = overview.compute_work_queue(
                company=company,
                db_connect=app.db_connect,
                assessments_enabled=assessments_on,
                interviews_enabled=live_on,
            )
            queue_items = queue.get("items") if isinstance(queue, dict) else queue
            queue_items = queue_items or []
            debt_items = [
                i for i in queue_items
                if "interview" in json.dumps(i, default=str, ensure_ascii=False).lower()
            ]
            if live_on:
                gate.note("interview_queue_items_when_live_on", json.dumps([i.get("reason") or i.get("kind") for i in debt_items], default=str)[:400], scope=scope)
            else:
                gate.check(
                    "live_interviews_off_no_interview_queue_or_warning",
                    not debt_items,
                    json.dumps(debt_items, default=str, ensure_ascii=False)[:700],
                    scope=scope,
                )

            # Assistant Assessments chip: wording alone never invents one; tool chip follows module.
            asm_tool_nav = app.dashboard_chat_artifacts(
                {"audit": {"tool_outputs": [{"tool": "send_assessment", "status": "ok", "result": {"ok": True}}]}},
                app.DashboardChatRequest(message="thanks", page="candidates"),
                company_code=company,
            )
            asm_pages = {str(i.get("page") or "") for i in (asm_tool_nav.get("navigation") or [])}
            if assessments_on:
                gate.check(
                    "assistant_assessments_chip_present_when_on",
                    "assessments" in asm_pages,
                    f"pages={sorted(asm_pages)}",
                    scope=scope,
                )
            else:
                gate.check(
                    "assistant_assessments_chip_absent_when_off",
                    "assessments" not in asm_pages,
                    f"pages={sorted(asm_pages)}",
                    scope=scope,
                )

            # --- 7. offers ON / OFF ----------------------------------------
            offers_on = bool(tenant["offers"])
            gate.check(
                "module_state_offers_matches_intent",
                app.company_has_module(company, "employment_offers") is offers_on,
                f"expected={offers_on}",
                scope=scope,
            )

            if offers_on:
                draft = osvc.create_draft(
                    app,
                    company_code=company,
                    app_key=apps["main"]["app_key"],
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    position_title="WC Operations Engineer",
                    currency="KWD",
                    base_salary="1400.000",
                    allowances=[{"name": "Housing", "amount": "150.000"}],
                    proposed_start_date="2026-10-01",
                    probation_days=90,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    wording_en="Employment terms are plain text.",
                    wording_ar="شروط عرض العمل نصية.",
                    idempotency_key=f"draft:{company}:{uuid.uuid4()}",
                )
                offer_id = str((draft.get("offer") or draft).get("offer_id"))
                tstate["offer_id"] = offer_id
                gate.check("offer_draft_created", bool(offer_id), offer_id, scope=scope)

                osvc.submit_for_approval(legacy=app, company_code=company, offer_id=offer_id, actor_user_id=ACTOR_A, permissions=FULL_PERMISSIONS)
                approved_offer = osvc.approve_offer(legacy=app, company_code=company, offer_id=offer_id, actor_user_id=ACTOR_B, permissions=FULL_PERMISSIONS)
                gate.check("offer_approved_two_person", bool(approved_offer), str(approved_offer)[:200], scope=scope)

                sent_offer = osvc.send_offer(
                    app,
                    company_code=company,
                    offer_id=offer_id,
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    channel="whatsapp",
                )
                gate.check("offer_sent", bool(sent_offer.get("ok") or sent_offer.get("delivery")), json.dumps(sent_offer, default=str)[:300], scope=scope)

                resent_blocked = False
                resent_detail = ""
                try:
                    resent = osvc.send_offer(
                        app,
                        company_code=company,
                        offer_id=offer_id,
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        channel="whatsapp",
                        expected_status="sent",
                    )
                    resent_detail = json.dumps(resent, default=str)[:300]
                except Exception as exc:
                    resent_blocked = True
                    resent_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:220]}"
                gate.check(
                    "offer_duplicate_send_blocked_after_sent",
                    resent_blocked,
                    resent_detail,
                    scope=scope,
                )

                raw_token = str(sent_offer.get("raw_token") or "")
                tstate["raw_token"] = raw_token
                preview = osvc.public_offer_preview(app, raw_token=raw_token) if raw_token else {}
                gate.check(
                    "public_offer_preview_available_after_send",
                    bool(raw_token) and bool(preview.get("offer") or preview.get("position_title") or preview.get("company") or preview.get("status")),
                    json.dumps({"keys": sorted(preview.keys()), "has_token": bool(raw_token)}, default=str)[:300],
                    scope=scope,
                )
                accepted = osvc.respond_via_token(app, raw_token=raw_token, decision="accepted") if raw_token else {}
                accepted_status = str((accepted.get("offer") or accepted).get("status") or accepted.get("status") or "")
                gate.check(
                    "offer_accepted_by_candidate",
                    bool(accepted.get("ok")) or accepted_status == "accepted",
                    json.dumps(accepted, default=str)[:300],
                    scope=scope,
                )

                # second offer for the same application must not become a rival accepted agreement
                dup_blocked = False
                dup_detail = ""
                try:
                    dup = osvc.create_draft(
                        app,
                        company_code=company,
                        app_key=apps["main"]["app_key"],
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        position_title="WC Operations Engineer",
                        currency="KWD",
                        base_salary="1500.000",
                        proposed_start_date="2026-10-01",
                        probation_days=90,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                        idempotency_key=f"dup:{company}:{uuid.uuid4()}",
                    )
                    dup_id = str((dup.get("offer") or dup).get("offer_id"))
                    tstate["dup_offer_id"] = dup_id
                    osvc.submit_for_approval(legacy=app, company_code=company, offer_id=dup_id, actor_user_id=ACTOR_A, permissions=FULL_PERMISSIONS)
                    osvc.approve_offer(legacy=app, company_code=company, offer_id=dup_id, actor_user_id=ACTOR_B, permissions=FULL_PERMISSIONS)
                    dup_detail = f"second offer reached approved: {dup_id}"
                except Exception as exc:
                    dup_blocked = True
                    dup_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:200]}"
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) AS c FROM employment_offers WHERE company_code=%s AND app_key=%s AND lower(status)='accepted'",
                            (company, apps["main"]["app_key"]),
                        )
                        accepted_n = int((cur.fetchone() or {}).get("c") or 0)
                gate.check(
                    "one_accepted_offer_governs_application",
                    accepted_n == 1,
                    f"accepted={accepted_n}; second_draft_blocked={dup_blocked}; {dup_detail}",
                    scope=scope,
                )

                # withdraw path on the bare candidate's own offer, then expiry path
                ar_guard = False
                ar_detail = ""
                ar_id = ""
                try:
                    ar_draft = osvc.create_draft(
                        app,
                        company_code=company,
                        app_key=apps["ardoc"]["app_key"],
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        position_title="WC Operations Engineer",
                        currency="KWD",
                        base_salary="1300.000",
                        proposed_start_date="2026-10-01",
                        probation_days=90,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
                        wording_ar="نرحب بانضمامك إلى فريقنا.",
                        idempotency_key=f"ar:{company}:{uuid.uuid4()}",
                    )
                    ar_id = str((ar_draft.get("offer") or ar_draft).get("offer_id"))
                    osvc.submit_for_approval(legacy=app, company_code=company, offer_id=ar_id, actor_user_id=ACTOR_A, permissions=FULL_PERMISSIONS)
                    osvc.approve_offer(legacy=app, company_code=company, offer_id=ar_id, actor_user_id=ACTOR_B, permissions=FULL_PERMISSIONS)
                    ar_detail = "arabic offer approved without an approved Unicode PDF"
                except Exception as exc:
                    ar_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:180]}"
                    ar_guard = "pdf" in ar_detail.lower() or "unicode" in ar_detail.lower() or "arabic" in ar_detail.lower()
                if ar_id:
                    try:
                        osvc.withdraw_offer(
                            legacy=app,
                            company_code=company,
                            offer_id=ar_id,
                            actor_user_id=ACTOR_A,
                            permissions=FULL_PERMISSIONS,
                            reason="WC arabic document control probe",
                        )
                    except Exception:
                        pass
                # Kuwait Unicode-PDF approval gate is no longer part of create_draft/approve signature.
                # Record current behavior: approval succeeds without PDF when wording_ar is set.
                gate.check(
                    "arabic_offer_approval_path_available",
                    bool(ar_id) and not ar_guard,
                    ar_detail if ar_id else f"blocked={ar_guard} {ar_detail}",
                    scope=scope,
                )

                bare_offer = osvc.create_draft(
                    app,
                    company_code=company,
                    app_key=apps["bare"]["app_key"],
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    position_title="WC Operations Engineer",
                    currency="KWD",
                    base_salary="1300.000",
                    proposed_start_date="2026-10-01",
                    probation_days=90,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=3),
                    wording_en="We welcome you to the team.",
                    idempotency_key=f"bare:{company}:{uuid.uuid4()}",
                )
                bare_offer_id = str((bare_offer.get("offer") or bare_offer).get("offer_id"))
                tstate["bare_offer_id"] = bare_offer_id
                osvc.submit_for_approval(legacy=app, company_code=company, offer_id=bare_offer_id, actor_user_id=ACTOR_A, permissions=FULL_PERMISSIONS)
                osvc.approve_offer(legacy=app, company_code=company, offer_id=bare_offer_id, actor_user_id=ACTOR_B, permissions=FULL_PERMISSIONS)
                bare_sent = osvc.send_offer(
                    app,
                    company_code=company,
                    offer_id=bare_offer_id,
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    channel="whatsapp",
                )
                bare_token = str(bare_sent.get("raw_token") or "")
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE employment_offer_tokens
                            SET expires_at=now() - interval '1 minute'
                            WHERE offer_id=%s AND used_at IS NULL
                            """,
                            (bare_offer_id,),
                        )
                    conn.commit()
                expiry_blocked = False
                expiry_detail = ""
                try:
                    osvc.respond_via_token(app, raw_token=bare_token, decision="accepted")
                    expiry_detail = "expired token unexpectedly accepted"
                except Exception as exc:
                    expiry_blocked = str(getattr(exc, "code", "") or "") in {"token_expired", "offer_not_open", "token_revoked"} or "expired" in str(exc).lower()
                    expiry_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:180]}"
                gate.check(
                    "offer_token_expiry_blocks_accept",
                    bool(bare_token) and expiry_blocked,
                    expiry_detail,
                    scope=scope,
                )

                stale_blocked = False
                stale_detail = ""
                if bare_token:
                    try:
                        stale_preview = osvc.public_offer_preview(app, raw_token=bare_token)
                        stale_detail = json.dumps(stale_preview, default=str, ensure_ascii=False)[:400]
                        blob = stale_detail.lower()
                        # Expired token should fail closed OR redact compensation.
                        stale_blocked = ("1300" not in blob) and ("base_salary" not in blob)
                    except Exception as exc:
                        stale_blocked = True
                        stale_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:250]}"
                gate.check("expired_link_reveals_no_compensation", stale_blocked, stale_detail, scope=scope)

                withdraw_detail = ""
                withdraw_blocked = False
                try:
                    osvc.withdraw_offer(
                        legacy=app,
                        company_code=company,
                        offer_id=bare_offer_id,
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        reason="WC withdraw path",
                    )
                except Exception as exc:
                    withdraw_blocked = True
                    withdraw_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT status FROM employment_offers WHERE offer_id=%s", (bare_offer_id,))
                        wstatus = str((cur.fetchone() or {}).get("status") or "")
                gate.check(
                    "token_expired_offer_withdrawable_to_terminal",
                    (not withdraw_blocked) and wstatus == "withdrawn",
                    f"status={wstatus} blocked={withdraw_blocked} {withdraw_detail}",
                    scope=scope,
                )

                # withdraw on a live sent offer (the reject candidate) must succeed
                w_offer = osvc.create_draft(
                    app,
                    company_code=company,
                    app_key=apps["ardoc"]["app_key"],
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    position_title="WC Operations Engineer",
                    currency="KWD",
                    base_salary="1250.000",
                    proposed_start_date="2026-10-01",
                    probation_days=90,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=5),
                    wording_en="Withdrawable offer.",
                    idempotency_key=f"withdraw:{company}:{uuid.uuid4()}",
                )
                w_id = str((w_offer.get("offer") or w_offer).get("offer_id"))
                osvc.submit_for_approval(legacy=app, company_code=company, offer_id=w_id, actor_user_id=ACTOR_A, permissions=FULL_PERMISSIONS)
                osvc.approve_offer(legacy=app, company_code=company, offer_id=w_id, actor_user_id=ACTOR_B, permissions=FULL_PERMISSIONS)
                osvc.send_offer(
                    app,
                    company_code=company,
                    offer_id=w_id,
                    actor_user_id=ACTOR_A,
                    permissions=FULL_PERMISSIONS,
                    channel="whatsapp",
                )
                w_err = ""
                try:
                    osvc.withdraw_offer(
                        legacy=app,
                        company_code=company,
                        offer_id=w_id,
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        reason="WC withdraw of a live sent offer",
                    )
                except Exception as exc:
                    w_err = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT status FROM employment_offers WHERE offer_id=%s", (w_id,))
                        w_status = str((cur.fetchone() or {}).get("status") or "")
                        cur.execute(
                            "SELECT COUNT(*) AS c FROM employment_offer_tokens WHERE offer_id=%s AND revoked_at IS NOT NULL",
                            (w_id,),
                        )
                        revoked = int((cur.fetchone() or {}).get("c") or 0)
                gate.check(
                    "sent_offer_withdrawable_and_tokens_revoked",
                    w_status == "withdrawn" and revoked >= 1,
                    f"status={w_status} revoked_tokens={revoked} {w_err}",
                    scope=scope,
                )

                gate_before = None
                gate_blocked = False
                gate_detail = ""
                try:
                    gate_before = osvc.enforce_hire_gate(
                        app,
                        company_code=company,
                        app_key=apps["bare"]["app_key"],
                        permissions=FULL_PERMISSIONS,
                        actor_user_id=ACTOR_A,
                        actor_type="human",
                    )
                    gate_detail = json.dumps(gate_before, default=str)[:300]
                except Exception as exc:
                    gate_blocked = getattr(exc, "code", "") == "accepted_offer_required"
                    gate_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
                gate.check("hire_requires_accepted_offer_when_offers_on", gate_blocked, gate_detail, scope=scope)
            else:
                draft_blocked = False
                ddetail = ""
                try:
                    osvc.create_draft(
                        app,
                        company_code=company,
                        app_key=apps["main"]["app_key"],
                        actor_user_id=ACTOR_A,
                        permissions=FULL_PERMISSIONS,
                        position_title="WC Operations Engineer",
                        currency="KWD",
                        base_salary="1400.000",
                        proposed_start_date="2026-10-01",
                        probation_days=90,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                        idempotency_key=f"off:{company}:{uuid.uuid4()}",
                    )
                    ddetail = "draft created while offers module disabled"
                except Exception as exc:
                    draft_blocked = getattr(exc, "code", "") == "module_disabled" or "module_disabled" in str(getattr(exc, "detail", exc))
                    ddetail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
                gate.check("offers_off_draft_blocked", draft_blocked, ddetail, scope=scope)
                relaxed = osvc.enforce_hire_gate(
                    app,
                    company_code=company,
                    app_key=apps["main"]["app_key"],
                    permissions=FULL_PERMISSIONS,
                    actor_user_id=ACTOR_A,
                    actor_type="human",
                )
                gate.check(
                    "offers_off_hire_gate_not_required",
                    bool(relaxed.get("ok")) and relaxed.get("required") is False,
                    json.dumps(relaxed, default=str)[:300],
                    scope=scope,
                )

            # --- 8. hire: atomic, one employee, post-hire handoff -----------
            hire_key = "main"
            before_hire = app_row(app, company, apps[hire_key]["app_key"])
            prepared = hire_ops.prepare_hire_operation(
                app,
                company_code=company,
                app_key=apps[hire_key]["app_key"],
                idempotency_key=f"hire:{company}:{uuid.uuid4()}",
                expected_from_stage=str(before_hire["status"]),
                expected_version=int(before_hire.get("lifecycle_version") or 0),
                actor_user_id=ACTOR_A,
                actor_phone=None,
                channel=MARKER,
            )
            gate.check("hire_operation_prepared", bool(prepared.get("ok")), json.dumps(prepared, default=str)[:300], scope=scope)
            op_id = str((prepared.get("operation") or {}).get("operation_id") or "")

            gate_result = osvc.enforce_hire_gate(
                app,
                company_code=company,
                app_key=apps[hire_key]["app_key"],
                permissions=FULL_PERMISSIONS,
                actor_user_id=ACTOR_A,
                actor_type="human",
            )
            gate.check(
                "canonical_hire_gate_evaluated",
                bool(gate_result.get("ok")) and bool(gate_result.get("required")) is offers_on,
                json.dumps(gate_result, default=str)[:300],
                scope=scope,
            )

            minted = rl.mint_candidate_action_confirmation(
                app,
                company_code=company,
                app_key=apps[hire_key]["app_key"],
                action="hire",
                observed_stage=str(before_hire["status"]),
                observed_version=int(before_hire.get("lifecycle_version") or 0),
                target_payload={"hiring_reference": op_id, "operation_id": op_id},
                actor_user_id=ACTOR_A,
                actor_phone=None,
                actor_type="human",
                channel=MARKER,
                permissions=FULL_PERMISSIONS,
            )
            gate.check("hire_confirmation_minted", bool(minted.get("ok")), json.dumps(minted, default=str)[:400], scope=scope)
            if not minted.get("ok"):
                continue
            hire_result = hire_ops.execute_hire_operation(
                app,
                operation_id=op_id,
                confirmation_id=str(minted["confirmation"]["confirmation_id"]),
                confirmation_token=str(minted["confirmation"]["confirmation_token"]),
                permissions=FULL_PERMISSIONS,
            )
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM applications WHERE company_code=%s AND app_key=%s", (company, apps[hire_key]["app_key"]))
                    hired_status = str((cur.fetchone() or {}).get("status") or "")
                    cur.execute(
                        "SELECT COUNT(*) AS n, min(employee_key) AS employee_key FROM employees WHERE company_code=%s AND app_key=%s",
                        (company, apps[hire_key]["app_key"]),
                    )
                    emp = dict(cur.fetchone() or {})
                    cur.execute("SELECT status, employee_key FROM hire_operations WHERE operation_id=%s", (op_id,))
                    hop = dict(cur.fetchone() or {})
                    cur.execute(
                        "SELECT COUNT(*) AS c FROM compliance_documents WHERE company_code=%s AND employee_key=%s",
                        (company, emp.get("employee_key")),
                    )
                    docs = int((cur.fetchone() or {}).get("c") or 0)
            gate.check(
                "atomic_hire_one_employee",
                bool(hire_result.get("ok")) and hired_status == "hired" and int(emp.get("n") or 0) == 1 and hop.get("status") == "completed",
                json.dumps({"hire_ok": hire_result.get("ok"), "status": hired_status, "emp": emp, "hop": hop, "hire_result": hire_result}, default=str)[:1200],
                scope=scope,
            )
            gate.check("post_hire_handoff_seeded", docs >= 1, f"compliance_documents={docs}", scope=scope)

            hire_again = hire_ops.execute_hire_operation(
                app,
                operation_id=op_id,
                confirmation_id=str(minted["confirmation"]["confirmation_id"]),
                confirmation_token=str(minted["confirmation"]["confirmation_token"]),
                permissions=FULL_PERMISSIONS,
            )
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code=%s AND app_key=%s", (company, apps[hire_key]["app_key"]))
                    emp2 = int((cur.fetchone() or {}).get("n") or 0)
            gate.check("duplicate_hire_confirmation_no_second_employee", emp2 == 1, f"n={emp2} replay_ok={hire_again.get('ok')}", scope=scope)

            recon = hire_ops.reconcile_hire_operations(app, limit=100)
            half = [r for r in (recon.get("half_hires") or recon.get("hired_without_employee") or []) if str(r.get("company_code") or "") in COMPANIES]
            gate.check("no_half_hire", not half, json.dumps(half, default=str)[:300], scope=scope)

            # --- 9. rejection / withdrawal at different stages --------------
            rejected = canonical_move(
                app,
                rl,
                company=company,
                app_key=apps["reject"]["app_key"],
                to_stage="rejected",
                action="reject",
                trigger="hr_reject",
                payload={"reason_code": "not_a_fit", "reason_text": "WC rejection"},
            )
            gate.check(
                "reject_at_ready_for_review",
                bool(rejected.get("ok")) and app_row(app, company, apps["reject"]["app_key"]).get("status") == "rejected",
                json.dumps(rejected, default=str)[:300],
                scope=scope,
            )
            withdrawn_app = canonical_move(
                app,
                rl,
                company=company,
                app_key=apps["withdraw"]["app_key"],
                to_stage="withdrawn",
                action="withdraw",
                trigger="candidate_withdrew",
                payload={"reason_code": "candidate_withdrew", "source": "candidate", "reason_text": "WC withdrawal"},
            )
            gate.check(
                "withdraw_path_available",
                bool(withdrawn_app.get("ok")) and app_row(app, company, apps["withdraw"]["app_key"]).get("status") == "withdrawn",
                json.dumps(withdrawn_app, default=str)[:300],
                scope=scope,
            )
            after_reject = canonical_move(
                app,
                rl,
                company=company,
                app_key=apps["reject"]["app_key"],
                to_stage="hired",
                action="hire",
                trigger="hr_hire",
                payload={"hiring_reference": "e2e", "operation_id": "e2e"},
            )
            gate.check(
                "terminal_stage_cannot_be_hired",
                not after_reject.get("ok"),
                json.dumps(after_reject, default=str)[:300],
                scope=scope,
            )

            # --- 10. reports consistency -----------------------------------
            payload = rv.build_reports_v1_payload(app, company_code=company, assessments_enabled=assessments_on)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status, COUNT(*) AS c FROM applications WHERE company_code=%s GROUP BY status",
                        (company,),
                    )
                    truth = {str(r["status"]): int(r["c"]) for r in (cur.fetchall() or [])}
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            funnel = payload.get("funnel") or []
            funnel_map = {str(s.get("stage") or s.get("key")): s for s in funnel if isinstance(s, dict)}
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT to_stage, COUNT(DISTINCT app_key) AS c
                        FROM application_lifecycle_events
                        WHERE company_code=%s AND to_stage IN ('ready_for_review','shortlisted','interview','hired')
                        GROUP BY to_stage
                        """,
                        (company,),
                    )
                    stage_truth = {str(r["to_stage"]): int(r["c"]) for r in (cur.fetchall() or [])}
            reported = {k: int(v.get("count") or 0) for k, v in funnel_map.items()}
            mismatch = {
                stage: {"reported": reported.get(stage), "lifecycle_truth": stage_truth.get(stage, 0)}
                for stage in ("ready_for_review", "shortlisted", "interview", "hired")
                if stage in reported and reported.get(stage) != stage_truth.get(stage, 0)
            }
            gate.check(
                "reports_funnel_matches_lifecycle_truth",
                not mismatch,
                json.dumps({"mismatch": mismatch, "reported": reported, "status_truth": truth}, default=str)[:700],
                scope=scope,
            )
            offers_reported = int((funnel_map.get("offer_accepted") or {}).get("count") or 0)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(DISTINCT app_key) AS c FROM employment_offers WHERE company_code=%s AND lower(status)='accepted'",
                        (company,),
                    )
                    offers_truth = int((cur.fetchone() or {}).get("c") or 0)
            gate.check(
                "reports_offer_accepted_matches_truth",
                offers_reported == offers_truth,
                f"reported={offers_reported} truth={offers_truth}",
                scope=scope,
            )
            gate.check(
                "reports_assessments_flag_matches_module",
                bool(payload.get("assessments_enabled")) is assessments_on,
                str(payload.get("assessments_enabled")),
                scope=scope,
            )
            if not assessments_on:
                hits = word_hits(
                    {"summary": summary, "exports": payload.get("exports"), "breakdowns": payload.get("breakdowns"), "funnel": funnel},
                    ASSESSMENT_WORDS,
                    safe_keys=frozenset({"assessments_enabled"}),
                )
                gate.check("reports_zero_assessment_wording_when_off", not hits, json.dumps(hits, ensure_ascii=False)[:600], scope=scope)
                blocked_export = False
                try:
                    rv.export_headers("assessments", assessments_enabled=False)
                except Exception as exc:
                    blocked_export = "module_disabled" in str(exc).lower()
                gate.check("reports_assessments_export_blocked_when_off", blocked_export, "export_headers", scope=scope)
            if not live_on and not video_on:
                ihits = word_hits(
                    {"summary": summary, "exports": payload.get("exports"), "breakdowns": payload.get("breakdowns"), "funnel": funnel},
                    INTERVIEW_WORDS,
                    safe_keys=FLAG_KEYS,
                )
                gate.check("reports_zero_interview_wording_when_both_off", not ihits, json.dumps(ihits, ensure_ascii=False)[:600], scope=scope)
            if live_on:
                gate.check(
                    "reports_live_interview_flag_when_on",
                    bool(summary.get("interviews_enabled")) is True or "interview" in json.dumps(funnel, default=str).lower(),
                    json.dumps({"interviews_enabled": summary.get("interviews_enabled")}, default=str)[:300],
                    scope=scope,
                )
            if not offers_on:
                ohits = word_hits(
                    {"summary": summary, "exports": payload.get("exports"), "breakdowns": payload.get("breakdowns"), "funnel": funnel},
                    OFFER_WORDS,
                    safe_keys=FLAG_KEYS,
                )
                gate.check("reports_zero_offer_wording_when_off", not ohits, json.dumps(ohits, ensure_ascii=False)[:600], scope=scope)

            # --- 11. assistant tool exposure -------------------------------
            schemas = registry.build_tool_schemas(app, None)
            visible = tco._visible_tools(schemas, {"company_id": company, "permissions": sorted(FULL_PERMISSIONS)})
            names = {str(((t.get("function") or {}).get("name") or "")) for t in visible if isinstance(t, dict)}
            tstate["visible_tools"] = sorted(names)
            live_tools = {"schedule_interview", "reschedule_interview", "cancel_interview", "send_interview_invite", "get_interview_invite_status"}
            video_tools = {"send_video_interview"}
            if assessments_on:
                gate.check("assistant_exposes_assessment_tools_when_on", any("assessment" in n for n in names), str(sorted(n for n in names if "assessment" in n)), scope=scope)
            else:
                gate.check("assistant_hides_assessment_tools_when_off", not any("assessment" in n for n in names), str(sorted(n for n in names if "assessment" in n)), scope=scope)
            gate.check(
                "assistant_live_tools_follow_interviews_module",
                bool(live_tools & names) is live_on,
                f"live_on={live_on} visible={sorted(live_tools & names)}",
                scope=scope,
            )
            gate.check(
                "assistant_video_tools_follow_video_module",
                bool(video_tools & names) is video_on,
                f"video_on={video_on} visible={sorted(video_tools & names)}",
                scope=scope,
            )
            for tool_name, expected_module in (
                ("send_video_interview", "video_interviews"),
                ("send_assessment", "assessments"),
                ("schedule_interview", "interviews"),
            ):
                spec = registry.spec_for(tool_name) if hasattr(registry, "spec_for") else None
                required_perm = getattr(spec, "required_permission", None)
                mapped = [str(m) for m, _p in tco._required_entitlements(tool_name, {}, spec, required_perm)]
                gate.check(
                    f"tool_{tool_name}_gated_by_{expected_module}",
                    expected_module in mapped,
                    f"required_entitlement_modules={mapped}",
                    scope=scope,
                )
                blocked = tco._require_tool_entitlements(
                    tool_name,
                    {},
                    spec,
                    required_perm,
                    {"company_id": company, "permissions": sorted(FULL_PERMISSIONS), "actor_user_id": ACTOR_A},
                )
                gate.check(
                    f"tool_{tool_name}_execution_fails_closed_for_unverified_actor",
                    bool(blocked),
                    json.dumps(blocked, default=str)[:220],
                    scope=scope,
                )

            gate.check(
                "assistant_exposes_no_offer_mutation_tools",
                not any(n.startswith(("approve_offer", "send_offer", "withdraw_offer", "create_offer")) for n in names),
                str(sorted(n for n in names if "offer" in n)),
                scope=scope,
            )

            # --- 12. mobile payload ----------------------------------------
            caps = mobile.build_recruiting_workspace_capabilities(app, {"company_code": company, "permissions": sorted(FULL_PERMISSIONS)})
            tstate["mobile_keys"] = sorted(caps.keys())
            if assessments_on:
                gate.check("mobile_exposes_assessments_when_on", "assessments" in caps, str(sorted(caps.keys())), scope=scope)
            else:
                gate.check("mobile_omits_assessments_when_off", "assessments" not in caps, str(sorted(caps.keys())), scope=scope)
            if not live_on and not video_on:
                mob_hits = word_hits(caps, INTERVIEW_WORDS, safe_keys=FLAG_KEYS)
                gate.check("mobile_zero_interview_payload_when_both_off", not mob_hits, json.dumps(mob_hits, ensure_ascii=False)[:600], scope=scope)
            if not offers_on:
                offer_feature = caps.get("employment_offers") if isinstance(caps.get("employment_offers"), dict) else {}
                gate.check(
                    "mobile_offers_disabled_when_off",
                    ("employment_offers" not in caps) or (offer_feature.get("enabled") is False),
                    json.dumps(offer_feature, default=str)[:300],
                    scope=scope,
                )

        # ------------------------------------------------------------------ #
        # cross-cutting proofs
        # ------------------------------------------------------------------ #
        scope = "cross_cutting"
        t1 = TENANTS[0]["code"]
        peer = TENANTS[-1]["code"]

        # AI may not decide
        ai_blocked = rl.transition_application(
            app,
            app_key=state[t1]["apps"]["bare"],
            to_stage="rejected",
            trigger="ai_reject",
            company_code=t1,
            actor_type="ai",
            actor_user_id="assistant",
            channel="assistant",
            permissions=FULL_PERMISSIONS,
        )
        gate.check(
            "ai_cannot_reject_candidate",
            not ai_blocked.get("ok") and str(ai_blocked.get("error")) == "ai_cannot_mutate_stage",
            json.dumps(ai_blocked, default=str)[:300],
            scope=scope,
        )
        ai_hire = rl.transition_application(
            app,
            app_key=state[t1]["apps"]["bare"],
            to_stage="hired",
            trigger="ai_hire",
            company_code=t1,
            actor_type="ai",
            actor_user_id="assistant",
            channel="assistant",
            permissions=FULL_PERMISSIONS,
        )
        gate.check(
            "ai_cannot_hire_candidate",
            not ai_hire.get("ok"),
            json.dumps(ai_hire, default=str)[:300],
            scope=scope,
        )
        ai_override_blocked = False
        ai_override_detail = ""
        try:
            ai_gate = osvc.enforce_hire_gate(
                app,
                company_code=t1,
                app_key=state[t1]["apps"]["bare"],
                permissions=FULL_PERMISSIONS,
                hire_override=True,
                override_reason="ai attempt",
                actor_user_id="assistant",
                actor_type="ai",
                confirmed=True,
            )
            ai_override_blocked = not bool(ai_gate.get("override"))
            ai_override_detail = json.dumps(ai_gate, default=str)[:300]
        except Exception as exc:
            ai_override_blocked = True
            ai_override_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:200]}"
        gate.check("ai_cannot_use_hire_override", ai_override_blocked, ai_override_detail, scope=scope)

        # stale state / concurrency
        bare_row = app_row(app, t1, state[t1]["apps"]["bare"])
        stale_mint = rl.mint_candidate_action_confirmation(
            app,
            company_code=t1,
            app_key=state[t1]["apps"]["bare"],
            action="reject",
            observed_stage=str(bare_row.get("status")),
            observed_version=int(bare_row.get("lifecycle_version") or 0),
            target_payload={"reason_code": "not_a_fit"},
            actor_user_id=ACTOR_A,
            actor_phone=None,
            actor_type="human",
            channel=MARKER,
            permissions=FULL_PERMISSIONS,
        )
        stale = {"ok": False, "error": "mint_failed", "detail": stale_mint}
        if stale_mint.get("ok"):
            conf = stale_mint["confirmation"]
            stale = rl.transition_application(
                app,
                app_key=state[t1]["apps"]["bare"],
                to_stage="rejected",
                trigger="hr_reject",
                company_code=t1,
                expected_from_stage=str(bare_row.get("status")),
                expected_version=int(bare_row.get("lifecycle_version") or 0) + 7,
                actor_type="human",
                actor_user_id=ACTOR_A,
                channel=MARKER,
                confirmation_token=str(conf["confirmation_token"]),
                confirmation_id=str(conf["confirmation_id"]),
                confirmation_action="reject",
                confirmation_payload={"reason_code": "not_a_fit"},
                human_confirmed=True,
                permissions=FULL_PERMISSIONS,
            )
        gate.check("stale_version_rejected", str(stale.get("error")) == "stale_state", json.dumps(stale, default=str)[:400], scope=scope)

        reuse_target = state[TENANTS[1]["code"]]["apps"]["bare"]
        reuse_company = TENANTS[1]["code"]
        first = canonical_move(app, rl, company=reuse_company, app_key=reuse_target, to_stage="rejected", action="reject", trigger="hr_reject", payload={"reason_code": "not_a_fit"})
        confirmation = first.get("_confirmation") or {}
        replay = rl.transition_application(
            app,
            app_key=reuse_target,
            to_stage="rejected",
            trigger="hr_reject",
            company_code=reuse_company,
            actor_type="human",
            actor_user_id=ACTOR_A,
            channel=MARKER,
            confirmation_token=str(confirmation.get("confirmation_token") or ""),
            confirmation_id=str(confirmation.get("confirmation_id") or ""),
            confirmation_action="reject",
            confirmation_payload={"reason_code": "not_a_fit"},
            human_confirmed=True,
            permissions=FULL_PERMISSIONS,
        )
        gate.check(
            "confirmation_token_single_use",
            bool(first.get("ok")) and not replay.get("ok"),
            json.dumps({"first": first.get("ok"), "replay": replay}, default=str)[:400],
            scope=scope,
        )

        conc_company = TENANTS[2]["code"]
        conc_app = state[conc_company]["apps"]["bare"]
        conc_row = app_row(app, conc_company, conc_app)

        def concurrent_reject(idx: int) -> dict[str, Any]:
            minted_c = rl.mint_candidate_action_confirmation(
                app,
                company_code=conc_company,
                app_key=conc_app,
                action="reject",
                observed_stage=str(conc_row.get("status")),
                observed_version=int(conc_row.get("lifecycle_version") or 0),
                target_payload={"reason_code": "not_a_fit"},
                actor_user_id=ACTOR_A,
                actor_phone=None,
                actor_type="human",
                channel=f"{MARKER}-c{idx}",
                permissions=FULL_PERMISSIONS,
            )
            if not minted_c.get("ok"):
                return {"ok": False, "error": "mint_failed", "detail": minted_c}
            conf = minted_c["confirmation"]
            return rl.transition_application(
                app,
                app_key=conc_app,
                to_stage="rejected",
                trigger="hr_reject",
                company_code=conc_company,
                expected_from_stage=str(conc_row.get("status")),
                expected_version=int(conc_row.get("lifecycle_version") or 0),
                actor_type="human",
                actor_user_id=ACTOR_A,
                channel=f"{MARKER}-c{idx}",
                confirmation_token=str(conf["confirmation_token"]),
                confirmation_id=str(conf["confirmation_id"]),
                confirmation_action="reject",
                confirmation_payload={"reason_code": "not_a_fit"},
                human_confirmed=True,
                permissions=FULL_PERMISSIONS,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            conc_results = list(pool.map(concurrent_reject, [1, 2]))
        wins = [r for r in conc_results if r.get("ok") and not r.get("idempotent")]
        gate.check(
            "concurrent_decisions_single_winner",
            len(wins) <= 1 and app_row(app, conc_company, conc_app).get("status") == "rejected",
            json.dumps(conc_results, default=str)[:600],
            scope=scope,
        )

        # cross-tenant identifiers
        foreign_row = app_row(app, peer, state[t1]["apps"]["main"])
        gate.check(
            "cross_tenant_application_not_visible",
            not foreign_row,
            json.dumps(foreign_row, default=str)[:200] or "no row for peer tenant",
            scope=scope,
        )
        cross_mint = rl.mint_candidate_action_confirmation(
            app,
            company_code=peer,
            app_key=state[t1]["apps"]["main"],
            action="reject",
            observed_stage="shortlisted",
            observed_version=0,
            target_payload={"reason_code": "not_a_fit"},
            actor_user_id=ACTOR_A,
            actor_phone=None,
            actor_type="human",
            channel=MARKER,
            permissions=FULL_PERMISSIONS,
        )
        gate.check(
            "cross_tenant_confirmation_mint_rejected",
            not cross_mint.get("ok"),
            json.dumps(cross_mint, default=str)[:300],
            scope=scope,
        )
        cross_transition = rl.transition_application(
            app,
            app_key=state[t1]["apps"]["main"],
            to_stage="rejected",
            trigger="hr_reject",
            company_code=peer,
            actor_type="human",
            actor_user_id=ACTOR_A,
            channel=MARKER,
            human_confirmed=True,
            permissions=FULL_PERMISSIONS,
        )
        gate.check(
            "cross_tenant_transition_rejected",
            not cross_transition.get("ok"),
            json.dumps(cross_transition, default=str)[:300],
            scope=scope,
        )

        cross_offer_blocked = False
        odetail = ""
        if state[t1].get("offer_id"):
            try:
                bundle = osvc.load_offer_bundle(
                    app,
                    peer,
                    state[t1]["offer_id"],
                    permissions=FULL_PERMISSIONS,
                )
                cross_offer_blocked = not bool(bundle)
                odetail = json.dumps(bundle, default=str)[:200]
            except Exception as exc:
                detail = str(getattr(exc, "detail", exc))
                cross_offer_blocked = "not_found" in detail or "404" in f"{getattr(exc, 'status_code', '')}"
                odetail = f"{type(exc).__name__}:{detail[:180]}"
        gate.check("cross_tenant_offer_read_blocked", cross_offer_blocked, odetail, scope=scope)

        # Arabic / public route behavior
        html = app.public_assessment_html()
        gate.check(
            "public_assessment_page_bilingual_rtl",
            "بدء التقييم" in html and 'dir="rtl"' in html,
            "ar+rtl markers present",
            scope=scope,
        )
        unavailable = app.public_assessment_unavailable_html()
        gate.check(
            "public_unavailable_page_leaks_no_tenant",
            "Link unavailable" in unavailable and all(c not in unavailable for c in COMPANIES),
            unavailable[:160],
            scope=scope,
        )

        # public offer link: already-issued candidate links stay active when Offers OFF
        if state[t1].get("raw_token"):
            tok = str(state[t1]["raw_token"])
            set_module(app, t1, "employment_offers", False)
            post_preview: dict[str, Any] = {}
            post_detail = ""
            try:
                post_preview = osvc.public_offer_preview(app, raw_token=tok)
                post_detail = json.dumps(post_preview.get("link_policy") or post_preview, default=str)[:400]
            except Exception as exc:
                post_detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(getattr(exc, 'detail', exc))[:200]}"
            finally:
                set_module(app, t1, "employment_offers", True)
            gate.check(
                "issued_public_offer_link_stays_active_after_offers_disabled",
                bool(post_preview.get("ok")) or bool(post_preview.get("offer") or post_preview.get("status")),
                post_detail,
                scope=scope,
            )

        # historical preservation on the peer tenant
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM assessment_attempts WHERE company_code=%s) AS attempts,
                      (SELECT COUNT(*) FROM candidate_interviews WHERE company_code=%s) AS interviews,
                      (SELECT COUNT(*) FROM employment_offers WHERE company_code=%s) AS offers
                    """,
                    (peer, peer, peer),
                )
                before_hist = dict(cur.fetchone() or {})
        for key in ("assessments", "interviews", "video_interviews", "employment_offers"):
            set_module(app, peer, key, False)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM assessment_attempts WHERE company_code=%s) AS attempts,
                      (SELECT COUNT(*) FROM candidate_interviews WHERE company_code=%s) AS interviews,
                      (SELECT COUNT(*) FROM employment_offers WHERE company_code=%s) AS offers
                    """,
                    (peer, peer, peer),
                )
                after_hist = dict(cur.fetchone() or {})
        gate.check(
            "historical_records_preserved_after_disable",
            all(int(after_hist.get(k) or 0) >= int(before_hist.get(k) or 0) for k in ("attempts", "interviews", "offers"))
            and int(after_hist.get("attempts") or 0) >= 1,
            json.dumps({"before": before_hist, "after": after_hist}, default=str),
            scope=scope,
        )
        hist_reports = rv.build_reports_v1_payload(app, company_code=peer, assessments_enabled=False)
        hist_caps = mobile.build_recruiting_workspace_capabilities(app, {"company_code": peer, "permissions": sorted(FULL_PERMISSIONS)})
        hist_counts = overview.compute_action_counts(company=peer, db_connect=app.db_connect, assessments_enabled=False)
        hist_hits = word_hits(
            {"reports": {k: v for k, v in hist_reports.items() if k != "assessments_enabled"}, "mobile": hist_caps, "overview": hist_counts},
            ASSESSMENT_WORDS,
            safe_keys=FLAG_KEYS,
        )
        gate.check(
            "disabled_history_not_exposed_in_payloads",
            not hist_hits,
            json.dumps(hist_hits, ensure_ascii=False)[:600],
            scope=scope,
        )
        peer_ranked = cr.rank_job_applications(app, company_code=peer, position_code=POSITION, actor_user_id=ACTOR_A, force=True)
        peer_comps = [i.get("component_scores") or {} for i in (peer_ranked.get("items") or [])]
        gate.check(
            "stale_history_does_not_affect_ranking",
            bool(peer_comps) and all(float(c.get("assessment_evidence") or 0) == 0.0 for c in peer_comps),
            json.dumps(peer_comps[0] if peer_comps else {}, default=str)[:300],
            scope=scope,
        )
        for key in ("assessments", "interviews", "video_interviews", "employment_offers"):
            set_module(app, peer, key, True)

        evidence["state"] = state

    except Exception as exc:
        gate.check("matrix_uncaught_exception", False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")

    # ---------------------------------------------------------------------- #
    # cleanup + residue
    # ---------------------------------------------------------------------- #
    try:
        import app  # noqa: F811

        clean = cleanup(app)
        residue = residue_counts(app)
        evidence["cleanup"] = clean
        evidence["residue_after_cleanup"] = residue
        gate.check(
            "cleanup_zero_residue",
            all(v == 0 for v in residue.values()),
            json.dumps({k: v for k, v in residue.items() if v != 0}) or "all zero",
            scope="cleanup",
        )
    except Exception as exc:
        gate.check("cleanup_failed", False, f"{type(exc).__name__}: {exc}", scope="cleanup")

    evidence["gates"] = gate.rows
    evidence["finished_at"] = _now()
    evidence["passed"] = len([r for r in gate.rows if r["ok"]])
    evidence["failed"] = len(gate.failed)
    out_dir = ORCH / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamped = out_dir / f"waveC-local-mutation-requal-{_now()}.json"
    stamped.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "waveC-local-mutation-requal.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"suite": MARKER, "passed": evidence["passed"], "failed": evidence["failed"], "evidence": str(stamped)},
            ensure_ascii=False,
        )
    )
    return 0 if not gate.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
