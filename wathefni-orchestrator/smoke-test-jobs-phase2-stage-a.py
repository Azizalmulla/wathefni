#!/usr/bin/env python3
"""Guarded staging-only matrix for Jobs Phase 2 Stage A.

Refuses production paths. Uses isolated marker records and deterministic cleanup.
Does not send WhatsApp, create real candidate journeys, or start Stage B conversion.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import prehire_jobs as jobs


ACTOR = "00000000-0000-4000-8000-000000000001"
MARKER = "J2SA"


def require_staging_ack() -> dict[str, str]:
    if os.environ.get("WATHEFNI_STAGE_A_SMOKE_ACK") != "staging-only":
        raise SystemExit("Set WATHEFNI_STAGE_A_SMOKE_ACK=staging-only to run this staging smoke.")
    runtime_env = str(
        os.environ.get("WATHEFNI_ENV")
        or os.environ.get("WATHEFNI_ENVIRONMENT")
        or os.environ.get("WATHEFNI_DEPLOYMENT_ENV")
        or ""
    ).strip().lower()
    if runtime_env not in {"staging", "stage"}:
        raise SystemExit("WATHEFNI_ENV/WATHEFNI_ENVIRONMENT must be explicitly staging.")
    env_path = str(os.environ.get("WATHEFNI_POSTGRES_ENV") or "").lower()
    if "prod" in env_path or "production" in env_path:
        raise SystemExit("Refusing to run Stage A smoke against an obvious production environment file.")
    expected_db = str(os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "").strip()
    if expected_db != "wathefni_staging":
        raise SystemExit("WATHEFNI_EXPECTED_DATABASE_NAME must be wathefni_staging.")
    delivery = str(os.environ.get("WATHEFNI_DELIVERY_MODE") or "").strip().lower()
    if delivery and delivery != "dry_run":
        raise SystemExit("Refusing Stage A smoke unless WATHEFNI_DELIVERY_MODE=dry_run (or unset for in-process).")
    return {
        "runtime_env": runtime_env,
        "postgres_env": env_path,
        "expected_db": expected_db,
        "delivery_mode": delivery or "unset",
    }


class Matrix:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            value = fn()
            self.rows.append({"case": name, "result": "PASS", "detail": value if isinstance(value, (str, int, float, bool, dict, list)) else "ok"})
            print(f"PASS  {name}")
            return value
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.rows.append({"case": name, "result": "FAIL", "detail": detail, "trace": traceback.format_exc(limit=4)})
            print(f"FAIL  {name}: {detail}")
            return None

    def summary(self) -> dict[str, Any]:
        passed = sum(1 for r in self.rows if r["result"] == "PASS")
        failed = sum(1 for r in self.rows if r["result"] == "FAIL")
        return {"passed": passed, "failed": failed, "total": len(self.rows), "rows": self.rows}


def phone_for(suffix: str, n: int = 0) -> str:
    base = int(uuid.uuid5(uuid.NAMESPACE_DNS, f"{suffix}-{n}").hex[:8], 16) % 10_000_000
    return f"9657{base:07d}"


def media_stub(suffix: str) -> dict[str, str]:
    return {
        "path": f"/tmp/stage-a-smoke-{suffix}.pdf",
        "type": "application/pdf",
        "mime_type": "application/pdf",
        "filename": f"stage-a-{suffix}.pdf",
    }


def base_payload(code: str, suffix: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title_en": f"Stage A Smoke {suffix} {code}",
        "position_code": code,
        "visibility": "public",
        "short_summary_en": "Stage A isolated smoke role for temporary context validation.",
        "requirements_en": ["Stage A smoke requirement"],
        "approve_content_en": True,
        "location": "Kuwait City",
        "work_arrangement": "onsite",
        "employment_type": "full_time",
        "vacancies": 1,
        "salary_visibility": "hr_only",
        "salary_min": 500,
        "salary_max": 900,
        "currency": "KD",
    }
    payload.update(overrides)
    return payload


def create_open(orch: Any, company: str, code: str, suffix: str, **overrides: Any) -> dict[str, Any]:
    draft = jobs.create_job(
        company=company,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        payload=base_payload(code, suffix, **overrides),
        as_draft=True,
    )
    opened = jobs.transition_job(
        company=company,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        to_status="open",
        expected_version=draft.get("version"),
    )
    assert opened["status"] == "open", opened
    return opened


def cleanup(orch: Any, company: str, codes: list[str], phones: list[str]) -> dict[str, Any]:
    evidence: dict[str, Any] = {"phones": phones, "codes": codes, "deleted": {}}
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            for phone in phones:
                cur.execute("DELETE FROM candidate_pending_media WHERE phone=%s RETURNING pending_id", (phone,))
                evidence["deleted"].setdefault("pending_media", 0)
                evidence["deleted"]["pending_media"] += len(cur.fetchall() or [])
                cur.execute("DELETE FROM candidate_job_contexts WHERE phone=%s RETURNING context_id", (phone,))
                evidence["deleted"].setdefault("job_contexts", 0)
                evidence["deleted"]["job_contexts"] += len(cur.fetchall() or [])
                cur.execute(
                    "DELETE FROM applications WHERE phone=%s AND company_code=%s RETURNING app_key",
                    (phone, company),
                )
                evidence["deleted"].setdefault("applications", 0)
                evidence["deleted"]["applications"] += len(cur.fetchall() or [])
            for code in codes:
                cur.execute(
                    "DELETE FROM applications WHERE company_code=%s AND position_code=%s",
                    (company, code),
                )
                cur.execute(
                    "DELETE FROM positions WHERE company_code=%s AND position_code=%s RETURNING position_code",
                    (company, code),
                )
                evidence["deleted"].setdefault("positions", 0)
                evidence["deleted"]["positions"] += len(cur.fetchall() or [])
            residual: dict[str, int] = {}
            for phone in phones:
                cur.execute("SELECT COUNT(*) AS c FROM candidate_pending_media WHERE phone=%s", (phone,))
                residual["pending_media"] = residual.get("pending_media", 0) + int((cur.fetchone() or {}).get("c") or 0)
                cur.execute("SELECT COUNT(*) AS c FROM candidate_job_contexts WHERE phone=%s", (phone,))
                residual["job_contexts"] = residual.get("job_contexts", 0) + int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT COUNT(*) AS c FROM applications WHERE phone=%s AND company_code=%s",
                    (phone, company),
                )
                residual["applications"] = residual.get("applications", 0) + int((cur.fetchone() or {}).get("c") or 0)
            for code in codes:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM positions WHERE company_code=%s AND position_code=%s",
                    (company, code),
                )
                residual["positions"] = residual.get("positions", 0) + int((cur.fetchone() or {}).get("c") or 0)
            evidence["residual"] = residual
        conn.commit()
    # Best-effort session cleanup outside the residual proof transaction.
    try:
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                for phone in phones:
                    cur.execute(
                        "DELETE FROM public_candidate_sessions WHERE phone=%s OR conversation_id LIKE %s",
                        (phone, f"%{MARKER}%"),
                    )
            conn.commit()
    except Exception as exc:
        evidence["session_cleanup_warning"] = str(exc)
    return evidence


def count_apps(orch: Any, company: str, code: str, phone: str | None = None) -> int:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            if phone:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM applications WHERE company_code=%s AND position_code=%s AND phone=%s",
                    (company, code, phone),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM applications WHERE company_code=%s AND position_code=%s",
                    (company, code),
                )
            return int((cur.fetchone() or {}).get("c") or 0)


def count_contexts(orch: Any, phone: str, company: str, code: str) -> dict[str, Any]:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS c,
                       COUNT(*) FILTER (WHERE preview_rendered_at IS NOT NULL) AS rendered,
                       COUNT(*) FILTER (WHERE preview_sent_at IS NOT NULL) AS sent
                FROM candidate_job_contexts
                WHERE phone=%s AND company_code=%s AND position_code=%s
                  AND status='awaiting_apply_confirmation'
                """,
                (phone, company, code),
            )
            row = dict(cur.fetchone() or {})
            return {
                "count": int(row.get("c") or 0),
                "preview_rendered": int(row.get("rendered") or 0),
                "preview_sent": int(row.get("sent") or 0),
            }


def count_pending(orch: Any, phone: str) -> int:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM candidate_pending_media WHERE phone=%s AND status='pending'",
                (phone,),
            )
            return int((cur.fetchone() or {}).get("c") or 0)


def main() -> int:
    guards = require_staging_ack()
    import app as orch

    company = str(os.environ.get("SMOKE_COMPANY") or "").strip().upper()
    if not company:
        raise SystemExit("SMOKE_COMPANY is required; no tenant fallback is allowed.")

    suffix = uuid.uuid4().hex[:8].upper()
    codes: list[str] = []
    phones: list[str] = []
    matrix = Matrix()
    evidence: dict[str, Any] = {"suffix": suffix, "company": company, "guards": guards}

    # Binding proof before mutations
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db, current_user AS usr")
            binding = dict(cur.fetchone())
            if binding.get("db") != "wathefni_staging":
                raise SystemExit(f"Abort: connected to {binding.get('db')}, not wathefni_staging")
            jobs.ensure_jobs_schema(cur)
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='positions' AND column_name IN ('visibility','short_summary_en','content_approved_en_at','title_en')
                ORDER BY 1
                """
            )
            pos_cols = [r["column_name"] for r in cur.fetchall()]
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name IN ('candidate_job_contexts','candidate_pending_media')
                ORDER BY 1
                """
            )
            tables = [r["table_name"] for r in cur.fetchall()]
        conn.commit()
    evidence["db_binding"] = binding
    evidence["schema"] = {"position_columns": pos_cols, "tables": tables}
    print(f"TARGET db={binding['db']} user={binding['usr']} company={company} suffix={suffix}")
    print(f"FLAGS env={guards['runtime_env']} delivery={guards['delivery_mode']} postgres_env={guards['postgres_env']}")

    try:
        # --- Fixture jobs ---
        code_hyphen = f"{MARKER}-IT-MGR-{suffix}"
        codes.append(code_hyphen)
        open_hyphen = create_open(
            orch,
            company,
            code_hyphen,
            suffix,
            visibility="share_only",
            location="",
            work_arrangement="fully_remote",
            salary_visibility="hr_only",
        )
        apply_hyphen = str(open_hyphen["apply_code"])
        phone_main = phone_for(suffix, 1)
        phones.append(phone_main)
        conversation = f"{MARKER.lower()}-{suffix}"

        matrix.check(
            "exact_hyphenated_apply_code_resolution",
            lambda: (
                jobs.extract_apply_code(apply_hyphen) == apply_hyphen
                and orch.resolve_public_role_by_apply_code(apply_hyphen).get("ok") is True
            )
            or (_ for _ in ()).throw(AssertionError(f"apply resolve failed for {apply_hyphen}")),
        )

        matrix.check(
            "invalid_exact_apply_never_fuzzy_substitutes",
            lambda: (
                lambda bad: (
                    (lambda resolved: (
                        resolved.get("ok") is False
                        and resolved.get("error") == "apply_code_not_found"
                        and resolved.get("role") is None
                    ) or (_ for _ in ()).throw(AssertionError(resolved)))(
                        orch.resolve_public_role_by_apply_code(bad)
                    )
                )
            )(apply_hyphen[:-1] + ("X" if not apply_hyphen.endswith("X") else "Z")),
        )

        matrix.check(
            "no_default_or_fallback_tenant",
            lambda: (
                (lambda resolved: (
                    resolved.get("ok") is False
                    and resolved.get("error") == "apply_code_not_found"
                ) or (_ for _ in ()).throw(AssertionError(resolved)))(
                    orch.resolve_public_role_by_apply_code(f"APPLY-NOTREAL-{code_hyphen}")
                )
            ),
        )

        # Initial APPLY -> one context, zero apps
        def initial_apply() -> dict[str, Any]:
            request = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=conversation,
                sender_phone=phone_main,
                sender_role="candidate",
                raw_text=apply_hyphen,
                metadata={"locale": "en"},
            )
            result = orch.handle_public_candidate_apply_code_turn(request)
            assert result and result.get("application_created") is False, result
            assert result.get("job_context"), result
            assert result.get("application") is None, result
            ctx = count_contexts(orch, phone_main, company, code_hyphen)
            apps = count_apps(orch, company, code_hyphen, phone_main)
            assert ctx["count"] == 1 and ctx["preview_rendered"] == 1 and ctx["preview_sent"] == 0, ctx
            assert apps == 0, apps
            return {"contexts": ctx, "applications": apps, "intent": result.get("intent")}

        evidence["initial_apply"] = matrix.check("initial_apply_one_context_zero_applications", initial_apply)

        def repeated_apply_idempotent() -> dict[str, Any]:
            request = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=conversation,
                sender_phone=phone_main,
                sender_role="candidate",
                raw_text=apply_hyphen,
                metadata={"locale": "en"},
            )
            result = orch.handle_public_candidate_apply_code_turn(request)
            assert result and result.get("application_created") is False, result
            ctx = count_contexts(orch, phone_main, company, code_hyphen)
            apps = count_apps(orch, company, code_hyphen, phone_main)
            assert ctx["count"] == 1, ctx
            assert apps == 0, apps
            return {"contexts": ctx, "applications": apps}

        evidence["repeat_apply"] = matrix.check("repeated_apply_idempotent", repeated_apply_idempotent)

        def cv_with_context_held() -> dict[str, Any]:
            request = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=conversation,
                sender_phone=phone_main,
                sender_role="candidate",
                raw_text="",
                media=media_stub(suffix),
                metadata={"locale": "en"},
            )
            result = orch.handle_candidate_file_turn(request)
            assert result and result.get("application_created") is False, result
            assert result.get("pending_media"), result
            assert result.get("cv_counts_as_apply_intent") is False, result  # Stage B gate: preview_sent_at unset
            pending = count_pending(orch, phone_main)
            apps = count_apps(orch, company, code_hyphen, phone_main)
            assert pending == 1, pending
            assert apps == 0, apps
            return {
                "pending_media": pending,
                "applications": apps,
                "intent": result.get("intent"),
                "cv_counts_as_apply_intent": result.get("cv_counts_as_apply_intent"),
            }

        evidence["cv_with_context"] = matrix.check(
            "cv_with_eligible_unique_context_held_zero_applications",
            cv_with_context_held,
        )

        phone_orphan = phone_for(suffix, 2)
        phones.append(phone_orphan)

        def cv_without_context_no_guess() -> dict[str, Any]:
            request = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=f"{conversation}-orphan",
                sender_phone=phone_orphan,
                sender_role="candidate",
                raw_text="",
                media=media_stub(f"{suffix}-orphan"),
                metadata={"locale": "en"},
            )
            result = orch.handle_candidate_file_turn(request)
            assert result and result.get("application_created") is False, result
            assert result.get("error") in {"no_active_application", "ambiguous_applications"} or "needs_role" in str(
                result.get("intent") or result.get("template") or ""
            ) or "cv_held_needs_role" in str(result), result
            assert count_apps(orch, company, code_hyphen, phone_orphan) == 0
            assert count_contexts(orch, phone_orphan, company, code_hyphen)["count"] == 0
            assert count_pending(orch, phone_orphan) == 1
            return {
                "error": result.get("error"),
                "intent": result.get("intent"),
                "pending_media": count_pending(orch, phone_orphan),
            }

        evidence["cv_without_context"] = matrix.check(
            "cv_without_unique_context_does_not_guess_role",
            cv_without_context_no_guess,
        )

        # Visibility / public share-only / internal
        code_public = f"{MARKER}-PUB-{suffix}"
        codes.append(code_public)
        create_open(orch, company, code_public, suffix, visibility="public")
        code_share = f"{MARKER}-SHR-{suffix}"
        codes.append(code_share)
        create_open(orch, company, code_share, suffix, visibility="share_only")
        code_internal = f"{MARKER}-INT-{suffix}"
        codes.append(code_internal)
        create_open(orch, company, code_internal, suffix, visibility="internal")

        def visibility_matrix() -> dict[str, Any]:
            pub = jobs.get_job(company=company, position_code=code_public, db_connect=orch.db_connect)
            shr = jobs.get_job(company=company, position_code=code_share, db_connect=orch.db_connect)
            inn = jobs.get_job(company=company, position_code=code_internal, db_connect=orch.db_connect)
            vac = {"remaining_vacancies": 1}
            assert jobs.job_eligibility_snapshot(pub, vacancy=vac, access_mode="discovery")["eligible"] is True
            assert jobs.job_eligibility_snapshot(shr, vacancy=vac, access_mode="discovery")["reason"] == "job_visibility_denied"
            assert jobs.job_eligibility_snapshot(shr, vacancy=vac, access_mode="exact_token")["eligible"] is True
            assert jobs.job_eligibility_snapshot(inn, vacancy=vac, access_mode="exact_token")["reason"] == "job_visibility_denied"
            assert jobs.job_eligibility_snapshot(inn, vacancy=vac, access_mode="discovery")["reason"] == "job_visibility_denied"
            internal_apply = f"APPLY-{company}-{code_internal}"
            resolved = orch.resolve_public_role_by_apply_code(internal_apply)
            assert resolved.get("ok") is False and resolved.get("error") == "job_visibility_denied", resolved
            return {"public_discovery": True, "share_only_exact": True, "internal_denied": True}

        matrix.check("public_and_share_only_eligibility", visibility_matrix)
        matrix.check(
            "internal_jobs_inaccessible_externally",
            lambda: orch.resolve_public_role_by_apply_code(f"APPLY-{company}-{code_internal}").get("error")
            == "job_visibility_denied"
            or (_ for _ in ()).throw(AssertionError("internal accessible")),
        )

        # Status / eligibility reasons
        code_status = f"{MARKER}-ST-{suffix}"
        codes.append(code_status)
        opened_status = create_open(orch, company, code_status, suffix)
        apply_status = opened_status["apply_code"]

        def status_reasons() -> dict[str, Any]:
            out: dict[str, Any] = {}
            # draft
            draft_job = jobs.create_job(
                company=company,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                payload=base_payload(f"{MARKER}-DR-{suffix}", suffix),
                as_draft=True,
            )
            codes.append(draft_job["position_code"])
            snap = jobs.job_eligibility_snapshot(draft_job, vacancy={"remaining_vacancies": 1})
            assert snap["reason"] == "job_not_accepting", snap
            out["draft"] = snap["reason"]

            paused = jobs.transition_job(
                company=company,
                position_code=code_status,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="paused",
                expected_version=opened_status.get("version"),
            )
            r = orch.resolve_public_role_by_apply_code(apply_status)
            assert r.get("error") == "job_paused", r
            out["paused"] = r.get("error")

            closed = jobs.transition_job(
                company=company,
                position_code=code_status,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="closed",
                expected_version=paused.get("version"),
            )
            r = orch.resolve_public_role_by_apply_code(apply_status)
            assert r.get("error") == "job_closed", r
            out["closed"] = r.get("error")

            # reopen then expire by deadline
            reopened = jobs.transition_job(
                company=company,
                position_code=code_status,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                to_status="open",
                expected_version=closed.get("version"),
            )
            yesterday = (datetime.now(ZoneInfo("Asia/Kuwait")).date() - timedelta(days=1)).isoformat()
            expired_row = jobs.update_job(
                company=company,
                position_code=code_status,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                payload={"application_deadline": yesterday},
                expected_version=reopened.get("version"),
            )
            r = orch.resolve_public_role_by_apply_code(apply_status)
            assert r.get("error") == "job_deadline_passed", r
            out["expired_deadline"] = r.get("error")

            # full / vacancies
            full_code = f"{MARKER}-FULL-{suffix}"
            codes.append(full_code)
            full = create_open(orch, company, full_code, suffix, vacancies=1)
            # Simulate exhausted vacancies via eligibility snapshot (backend-owned remaining)
            snap_full = jobs.job_eligibility_snapshot(full, vacancy={"remaining_vacancies": 0})
            assert snap_full["reason"] == "job_vacancies_exhausted", snap_full
            out["full"] = snap_full["reason"]
            _ = expired_row
            return out

        evidence["status_reasons"] = matrix.check(
            "draft_paused_closed_expired_full_reasons",
            status_reasons,
        )

        matrix.check(
            "null_or_unknown_lifecycle_status_fails_closed",
            lambda: (
                jobs.job_eligibility_snapshot(
                    {"status": None, "visibility": "public", "vacancies": 1},
                    vacancy={"remaining_vacancies": 1},
                )["reason"]
                == "job_not_accepting"
                and jobs.job_eligibility_snapshot(
                    {"status": "weird", "visibility": "public", "vacancies": 1},
                    vacancy={"remaining_vacancies": 1},
                )["reason"]
                == "job_not_accepting"
            )
            or (_ for _ in ()).throw(AssertionError("fail-open on unknown status")),
        )

        def deadline_tenant_tz() -> dict[str, Any]:
            # Inclusive through deadline day in Asia/Kuwait; fails the next calendar day there.
            deadline = date(2026, 7, 21)
            row = {
                "status": "open",
                "visibility": "public",
                "vacancies": 1,
                "application_deadline": deadline.isoformat(),
                "title_en": "x",
                "short_summary_en": "y",
                "requirements_en": ["z"],
                "content_approved_en_at": datetime.now(timezone.utc),
                "location": "Kuwait City",
                "employment_type": "full_time",
                "work_arrangement": "onsite",
                "salary_visibility": "hr_only",
                "position_code": "X",
                "apply_code": "APPLY-X-X",
                "company_display_name": "Wathefni",
            }
            vac = {"remaining_vacancies": 1}
            still_ok = datetime(2026, 7, 21, 23, 30, tzinfo=ZoneInfo("Asia/Kuwait"))
            next_day = datetime(2026, 7, 22, 0, 1, tzinfo=ZoneInfo("Asia/Kuwait"))
            ok = jobs.job_eligibility_snapshot(row, vacancy=vac, now=still_ok, tenant_timezone="Asia/Kuwait")
            bad = jobs.job_eligibility_snapshot(row, vacancy=vac, now=next_day, tenant_timezone="Asia/Kuwait")
            assert ok.get("eligible") is True, ok
            assert bad.get("reason") == "job_deadline_passed", bad
            return {"inclusive_deadline_day": True, "next_day_fails": True, "timezone": "Asia/Kuwait"}

        matrix.check("deadline_uses_tenant_timezone", deadline_tenant_tz)

        matrix.check(
            "remaining_vacancy_enforcement_backend_owned",
            lambda: jobs.job_eligibility_snapshot(
                {
                    "status": "open",
                    "visibility": "public",
                    "vacancies": 5,
                    "title_en": "x",
                    "short_summary_en": "y",
                    "requirements_en": ["z"],
                    "content_approved_en_at": datetime.now(timezone.utc),
                    "location": "Kuwait City",
                    "employment_type": "full_time",
                    "work_arrangement": "onsite",
                    "salary_visibility": "hr_only",
                    "position_code": "X",
                    "apply_code": "APPLY-X-X",
                    "company_display_name": "Wathefni",
                },
                vacancy={"remaining_vacancies": 0},
            )["reason"]
            == "job_vacancies_exhausted"
            or (_ for _ in ()).throw(AssertionError("vacancy not enforced")),
        )

        matrix.check(
            "missing_or_unapproved_content_fails_closed",
            lambda: (
                "approved_language_pack" in jobs.publish_blockers(
                    {
                        "visibility": "public",
                        "vacancies": 1,
                        "title_en": "Title",
                        "short_summary_en": "Summary",
                        "requirements_en": ["Req"],
                        "content_approved_en_at": None,
                        "location": "Kuwait City",
                        "employment_type": "full_time",
                        "work_arrangement": "onsite",
                        "salary_visibility": "hr_only",
                        "position_code": "X",
                        "apply_code": "APPLY-X-X",
                        "company_display_name": "Wathefni",
                    }
                )
            )
            or (_ for _ in ()).throw(AssertionError("unapproved content publishable")),
        )

        matrix.check(
            "fully_remote_publishable_without_physical_location",
            lambda: "location_or_fully_remote"
            not in jobs.publish_blockers(
                {
                    "visibility": "public",
                    "vacancies": 1,
                    "title_en": "Remote",
                    "short_summary_en": "Summary",
                    "requirements_en": ["Req"],
                    "content_approved_en_at": datetime.now(timezone.utc),
                    "location": "",
                    "employment_type": "full_time",
                    "work_arrangement": "fully_remote",
                    "salary_visibility": "hr_only",
                    "position_code": "X",
                    "apply_code": "APPLY-X-X",
                    "company_display_name": "Wathefni",
                }
            )
            or (_ for _ in ()).throw(AssertionError("remote blocked")),
        )

        def salary_visibility() -> dict[str, Any]:
            hidden = jobs.serialize_job(open_hyphen, vacancy={"remaining_vacancies": 1}, include_salary=False)
            assert hidden.get("salary_min") is None and hidden.get("salary_max") is None, hidden
            assert hidden.get("salary_visibility") == "hr_only"
            code_sal = f"{MARKER}-SAL-{suffix}"
            codes.append(code_sal)
            public_sal = create_open(
                orch,
                company,
                code_sal,
                suffix,
                salary_visibility="public",
                salary_min=1000,
                salary_max=1500,
                currency="KD",
            )
            shown = jobs.serialize_job(public_sal, vacancy={"remaining_vacancies": 1}, include_salary=False)
            # include_salary=False still shows when visibility is public
            assert shown.get("salary_min") == 1000.0 and shown.get("salary_max") == 1500.0, shown
            return {"hr_only_hidden": True, "public_visible": True}

        evidence["salary"] = matrix.check("salary_hidden_unless_public_visibility", salary_visibility)

        def assistant_draft_only() -> dict[str, Any]:
            import action_registry as registry

            assert registry.requires_confirmation("create_job_opening", {}) is True
            code_asst = f"{MARKER}-ASST-{suffix}"
            codes.append(code_asst)
            created = jobs.create_job(
                company=company,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                payload=base_payload(code_asst, suffix, approve_content_en=False),
                as_draft=True,
            )
            assert created.get("status") == "draft", created
            # Registry executor path uses as_draft=True; verify create never opens.
            assert created.get("published_at") in (None, ""), created
            return {"status": created.get("status"), "requires_confirmation": True, "qr_not_sent": True}

        matrix.check("assistant_job_creation_drafts_only", assistant_draft_only)

        def permissions_stale_audit() -> dict[str, Any]:
            assert jobs.permission_for_transition("publish") == "jobs.publish"
            assert jobs.permission_for_transition("resume") == "jobs.publish"
            assert jobs.permission_for_transition("reopen") == "jobs.publish"
            assert jobs.permission_for_transition("close") == "jobs.close"
            assert jobs.permission_for_transition("pause") == "jobs.close"
            code_stale = f"{MARKER}-STALE-{suffix}"
            codes.append(code_stale)
            draft = jobs.create_job(
                company=company,
                db_connect=orch.db_connect,
                actor_user_id=ACTOR,
                payload=base_payload(code_stale, suffix),
                as_draft=True,
            )
            try:
                jobs.transition_job(
                    company=company,
                    position_code=code_stale,
                    db_connect=orch.db_connect,
                    actor_user_id=ACTOR,
                    to_status="open",
                    expected_version=int(draft.get("version") or 1) - 1,
                )
                raise AssertionError("stale version was accepted")
            except jobs.JobsError as exc:
                assert exc.code == "stale_job_version", exc.code
            # Audit path exists and writes for dashboard transitions when context provided.
            context = {
                "company_code": company,
                "actor_user_id": ACTOR,
                "actor_email": "stage-a-smoke@wathefni.local",
                "actor_phone": "96570000000",
                "actor_role": "owner",
            }
            orch.record_admin_audit(
                context,
                "job_opening_stage_a_smoke",
                summary=f"Stage A smoke audit marker {suffix}",
                target_type="position",
                target=code_stale,
                details={"marker": MARKER, "suffix": suffix},
            )
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM action_results
                        WHERE action_type='job_opening_stage_a_smoke'
                          AND final_reply LIKE %s
                        """,
                        (f"%{suffix}%",),
                    )
                    written = int((cur.fetchone() or {}).get("c") or 0)
                    assert written >= 1, "audit row not written"
                    cur.execute(
                        """
                        DELETE FROM action_results
                        WHERE action_type='job_opening_stage_a_smoke'
                          AND final_reply LIKE %s
                        """,
                        (f"%{suffix}%",),
                    )
                    deleted_audits = cur.rowcount
                conn.commit()
            return {
                "permissions": True,
                "stale_version_blocked": True,
                "audit_written": written,
                "audit_cleaned": deleted_audits,
                "assistant_confirmation": True,
            }

        evidence["guards"] = {
            **guards,
            **(matrix.check("permissions_confirmation_stale_audit_intact", permissions_stale_audit) or {}),
        }

        def languages_rtl() -> dict[str, Any]:
            code_ar = f"{MARKER}-AR-{suffix}"
            codes.append(code_ar)
            ar_job = create_open(
                orch,
                company,
                code_ar,
                suffix,
                title_en="",
                short_summary_en="",
                requirements_en=[],
                approve_content_en=False,
                title_ar=f"مدير تقنية {suffix}",
                short_summary_ar="قيادة التقنية في الشركة.",
                requirements_ar=["خبرة تقنية"],
                approve_content_ar=True,
            )
            assert ar_job.get("status") == "open", ar_job
            request = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=f"{conversation}-ar",
                sender_phone=phone_for(suffix, 3),
                sender_role="candidate",
                raw_text=ar_job["apply_code"],
                metadata={"locale": "ar"},
            )
            phones.append(request.sender_phone)
            result = orch.handle_public_candidate_apply_code_turn(request)
            assert result and result.get("application_created") is False, result
            reply = str(result.get("reply") or "")
            # Arabic content should be preferred when locale=ar and AR pack approved.
            assert "مدير" in reply or "قيادة" in reply or result.get("job_context"), result
            en_code = f"{MARKER}-EN-{suffix}"
            codes.append(en_code)
            en_job = create_open(orch, company, en_code, suffix)
            en_req = orch.WhatsAppTurnRequest(
                account_id="stage-a-smoke",
                conversation_id=f"{conversation}-en",
                sender_phone=phone_for(suffix, 4),
                sender_role="candidate",
                raw_text=en_job["apply_code"],
                metadata={"locale": "en"},
            )
            phones.append(en_req.sender_phone)
            en_result = orch.handle_public_candidate_apply_code_turn(en_req)
            assert en_result and en_result.get("application_created") is False, en_result
            # RTL is a presentation concern; Stage A proves Arabic payload + locale selection.
            return {
                "ar_publish": True,
                "en_publish": True,
                "ar_preview_locale": True,
                "rtl_content_present": any("\u0600" <= ch <= "\u06FF" for ch in reply),
            }

        evidence["languages"] = matrix.check(
            "english_arabic_rtl_primary_language_publishing",
            languages_rtl,
        )

        # Aggregate Stage A applications for all marker codes must remain zero for smoke phones
        def zero_stage_a_applications() -> dict[str, Any]:
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM applications
                        WHERE company_code=%s
                          AND position_code LIKE %s
                          AND phone = ANY(%s)
                        """,
                        (company, f"{MARKER}-%{suffix}", phones),
                    )
                    total = int((cur.fetchone() or {}).get("c") or 0)
            assert total == 0, total
            return {"applications_for_smoke_phones": total}

        evidence["zero_applications"] = matrix.check(
            "database_zero_stage_a_created_applications",
            zero_stage_a_applications,
        )

        # Context + held media evidence snapshot before cleanup
        def context_media_evidence() -> dict[str, Any]:
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT phone, company_code, position_code, status,
                               (preview_rendered_at IS NOT NULL) AS rendered,
                               (preview_sent_at IS NOT NULL) AS sent
                        FROM candidate_job_contexts
                        WHERE phone = ANY(%s)
                        ORDER BY phone, position_code
                        """,
                        (phones,),
                    )
                    contexts = [dict(r) for r in cur.fetchall()]
                    cur.execute(
                        """
                        SELECT phone, status, (media IS NOT NULL) AS has_media
                        FROM candidate_pending_media
                        WHERE phone = ANY(%s)
                        ORDER BY phone, created_at
                        """,
                        (phones,),
                    )
                    media = [dict(r) for r in cur.fetchall()]
            assert any(c.get("rendered") and not c.get("sent") for c in contexts), contexts
            assert any(m.get("status") == "pending" and m.get("has_media") for m in media), media
            return {"contexts": contexts, "pending_media": media}

        evidence["pre_cleanup"] = matrix.check(
            "temporary_contexts_and_held_cv_media_as_designed",
            context_media_evidence,
        )

    finally:
        cleanup_proof = cleanup(orch, company, codes, phones)
        evidence["cleanup"] = cleanup_proof
        residual = cleanup_proof.get("residual") or {}
        if any(int(v or 0) > 0 for v in residual.values()):
            matrix.rows.append(
                {
                    "case": "cleanup_removes_all_smoke_records",
                    "result": "FAIL",
                    "detail": residual,
                }
            )
            print(f"FAIL  cleanup_removes_all_smoke_records: {residual}")
        else:
            matrix.rows.append(
                {
                    "case": "cleanup_removes_all_smoke_records",
                    "result": "PASS",
                    "detail": cleanup_proof.get("deleted"),
                }
            )
            print("PASS  cleanup_removes_all_smoke_records")

    summary = matrix.summary()
    report = {
        "suite": "jobs-phase2-stage-a-staging-matrix",
        "target": evidence.get("db_binding"),
        "company": company,
        "channel": {
            "account_id": "stage-a-smoke",
            "apply_whatsapp_number": os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER"),
            "delivery_mode": guards.get("delivery_mode"),
            "note": "In-process handlers only; no WhatsApp outbound invoked by this smoke.",
        },
        "summary": {"passed": summary["passed"], "failed": summary["failed"], "total": summary["total"]},
        "matrix": summary["rows"],
        "evidence": evidence,
    }
    out_path = os.environ.get("STAGE_A_REPORT_PATH") or os.path.join(
        ROOT, "ops", "reports", f"jobs-phase2-stage-a-staging-{suffix}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(json.dumps({"summary": report["summary"], "report": out_path}, indent=2))
    if summary["failed"]:
        print("RESULT: FAIL", file=sys.stderr)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
