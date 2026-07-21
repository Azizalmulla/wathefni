#!/usr/bin/env python3
"""Guarded staging-only matrix for Jobs Phase 2 Stage B conversion."""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from typing import Any, Callable

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch
import prehire_jobs as jobs

ACTOR = "00000000-0000-4000-8000-000000000001"
MARKER = f"J2B{uuid.uuid4().hex[:8].upper()}"
COMPANY = os.environ.get("SMOKE_COMPANY") or "WATHEFNI"
OWNER_PHONE = "96599338566"
OTHER_PHONE = "96550009999"
CV_PHONE = "96550118877"
ACCOUNT = "stage-b-smoke"


def require_staging() -> None:
    if os.environ.get("WATHEFNI_STAGE_B_SMOKE_ACK") != "staging-only":
        raise SystemExit("refusing: set WATHEFNI_STAGE_B_SMOKE_ACK=staging-only")
    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni_staging":
        raise SystemExit("refusing: expected wathefni_staging")
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute("select current_database() as d")
        db = cur.fetchone()["d"]
    if db != "wathefni_staging":
        raise SystemExit(f"refusing: connected to {db}")


def payload(code: str) -> dict[str, Any]:
    return {
        "position_code": code,
        "title": f"Stage B Canary {MARKER}",
        "title_en": f"Stage B Canary {MARKER}",
        "title_ar": f"تجربة مرحلة ب {MARKER}",
        "short_summary_en": f"{MARKER} Stage B canary summary.",
        "short_summary_ar": f"{MARKER} ملخص تجريبي.",
        "description": f"{MARKER} Stage B canary description with enough detail.",
        "requirements_en": ["Stage B smoke requirement"],
        "approve_content_en": True,
        "approve_content_ar": True,
        "location": "Kuwait City",
        "work_arrangement": "onsite",
        "employment_type": "full_time",
        "vacancies": 2,
        "visibility": "public",
        "salary_visibility": "hr_only",
        "salary_min": 500,
        "salary_max": 900,
        "currency": "KD",
    }


def create_open(code: str) -> dict[str, Any]:
    draft = jobs.create_job(
        company=COMPANY,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        payload=payload(code),
        as_draft=True,
    )
    opened = jobs.transition_job(
        company=COMPANY,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        to_status="open",
        expected_version=draft.get("version"),
    )
    assert opened.get("status") == "open", opened
    return opened


def cleanup(codes: list[str], phones: list[str]) -> None:
    with orch.db_connect() as conn, conn.cursor() as cur:
        for phone in phones:
            cur.execute("DELETE FROM conversation_application_bindings WHERE phone=%s", (phone,))
            cur.execute("DELETE FROM candidate_pending_media WHERE phone=%s", (phone,))
            cur.execute("DELETE FROM candidate_job_contexts WHERE phone=%s", (phone,))
            cur.execute(
                "DELETE FROM applications WHERE phone=%s AND company_code=%s",
                (phone, COMPANY),
            )
        for code in codes:
            cur.execute(
                "DELETE FROM applications WHERE company_code=%s AND position_code=%s",
                (COMPANY, code),
            )
            cur.execute(
                "DELETE FROM positions WHERE company_code=%s AND position_code=%s",
                (COMPANY, code),
            )


def turn(
    *,
    phone: str,
    text: str,
    conversation: str,
    message_id: str,
    media: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = orch.WhatsAppTurnRequest(
        account_id=ACCOUNT,
        conversation_id=conversation,
        sender_phone=phone,
        sender_role="candidate",
        raw_text=text,
        media=media,
        metadata={
            "provider": "stage-b-smoke",
            "provider_message_id": message_id,
            "message_id": message_id,
            "locale": "en",
            "smoke": True,
        },
    )
    raw = orch.handle_non_hr_conversational_turn(req) or {}
    nested = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    return {**raw, **nested}


def app_count(*, phone: str, position_code: str) -> int:
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n FROM applications
            WHERE phone=%s AND position_code=%s
              AND COALESCE(raw_json->>'stage_b_canary','')='true'
            """,
            (phone, position_code),
        )
        return int(cur.fetchone()["n"])


def main() -> int:
    require_staging()
    os.environ["WATHEFNI_STAGE_B_ENABLED"] = "1"
    os.environ["WATHEFNI_STAGE_B_CANARY_ONLY"] = "1"
    os.environ.pop("WATHEFNI_STAGE_B_CANDIDATE_ALLOWLIST", None)
    os.environ["WATHEFNI_STAGE_B_LIVE_WHATSAPP"] = "0"
    os.environ["WATHEFNI_STAGE_B_STAMP_DRY_RUN"] = "1"
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")

    orch.ensure_schema(force=True)
    results: list[dict[str, Any]] = []
    code = f"{MARKER}-ROLE"
    other_code = f"{MARKER}-OTHER"
    codes = [code, other_code]
    phones = [OWNER_PHONE, OTHER_PHONE, CV_PHONE]
    cleanup(codes, phones)
    job = create_open(code)
    apply_code = str(job.get("apply_code") or "")
    assert apply_code.upper().startswith("APPLY-"), apply_code
    # Scope Stage B convert to this smoke public canary job only.
    os.environ["WATHEFNI_STAGE_B_PUBLIC_POSITIONS"] = code
    os.environ["WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES"] = apply_code

    other_job = create_open(other_code)
    other_apply = str(other_job.get("apply_code") or "")

    conv_owner = f"{MARKER}-owner"
    conv_other = f"{MARKER}-other"
    conv_noncanary = f"{MARKER}-noncanary"

    def check(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            results.append({"name": name, "ok": True})
            print(f"PASS  {name}")
        except Exception as exc:
            results.append({"name": name, "ok": False, "error": str(exc), "trace": traceback.format_exc()})
            print(f"FAIL  {name}: {exc}")

    def case_preview_stamped_no_app() -> None:
        resp = turn(
            phone=OWNER_PHONE,
            text=apply_code,
            conversation=conv_owner,
            message_id=f"{MARKER}-apply-1",
        )
        assert resp.get("application_created") is False, resp
        ctx = resp.get("job_context") or {}
        assert ctx.get("preview_sent_at"), f"preview_sent_at missing: {json.dumps(ctx, default=str)[:500]}"
        with orch.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM applications WHERE phone=%s AND position_code=%s",
                (OWNER_PHONE, code),
            )
            assert int(cur.fetchone()["n"]) == 0

    def case_confirm_creates_one() -> None:
        resp = turn(
            phone=OWNER_PHONE,
            text="ready to apply",
            conversation=conv_owner,
            message_id=f"{MARKER}-confirm-1",
        )
        assert resp.get("application_created") is True, resp
        app = resp.get("application") or {}
        assert app.get("status") == "awaiting_cv", app
        assert (app.get("raw_json") or {}).get("stage_b_canary") is True
        assert (app.get("raw_json") or {}).get("stage_b_canary_position") == code
        assert app_count(phone=OWNER_PHONE, position_code=code) == 1

    def case_confirm_idempotent() -> None:
        again = turn(
            phone=OWNER_PHONE,
            text=apply_code,
            conversation=conv_owner,
            message_id=f"{MARKER}-reapply",
        )
        assert again.get("application_created") is False, again
        assert again.get("intent") == "public_candidate_existing_application", again
        assert app_count(phone=OWNER_PHONE, position_code=code) == 1

    def case_public_canary_open_to_any_phone() -> None:
        other_bind = turn(
            phone=OTHER_PHONE,
            text=apply_code,
            conversation=conv_other,
            message_id=f"{MARKER}-other-apply",
        )
        assert other_bind.get("job_context"), other_bind
        created = turn(
            phone=OTHER_PHONE,
            text="ready to apply",
            conversation=conv_other,
            message_id=f"{MARKER}-other-confirm",
        )
        assert created.get("application_created") is True, created
        assert app_count(phone=OTHER_PHONE, position_code=code) == 1

    def case_non_canary_job_no_convert() -> None:
        bind = turn(
            phone=OWNER_PHONE,
            text=other_apply,
            conversation=conv_noncanary,
            message_id=f"{MARKER}-noncanary-apply",
        )
        assert bind.get("job_context"), bind
        assert bind.get("application_created") is False
        confirm = turn(
            phone=OWNER_PHONE,
            text="ready to apply",
            conversation=conv_noncanary,
            message_id=f"{MARKER}-noncanary-confirm",
        )
        # Confirm handler returns None for non-canary → may fall through; must not create app.
        assert confirm.get("application_created") is not True
        with orch.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM applications WHERE phone=%s AND position_code=%s",
                (OWNER_PHONE, other_code),
            )
            assert int(cur.fetchone()["n"]) == 0

    def case_cv_before_preview_no_app() -> None:
        with orch.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidate_job_contexts
                  (phone,account_id,conversation_id,company_code,position_code,apply_code,
                   status,preview_rendered_at,preview_locale,preview_template_version,expires_at,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,'awaiting_apply_confirmation',now(),'en','v1',now()+interval '1 day',%s)
                """,
                (
                    CV_PHONE,
                    ACCOUNT,
                    f"{MARKER}-cv-before",
                    COMPANY,
                    code,
                    apply_code,
                    orch.Json({"marker": MARKER}),
                ),
            )
        media = {"path": "/tmp/does-not-exist-stage-b.pdf", "type": "application/pdf"}
        resp = turn(
            phone=CV_PHONE,
            text="",
            conversation=f"{MARKER}-cv-before",
            message_id=f"{MARKER}-cv-before-1",
            media=media,
        )
        assert resp.get("application_created") is False, resp
        with orch.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM applications WHERE phone=%s", (CV_PHONE,))
            assert int(cur.fetchone()["n"]) == 0
            cur.execute(
                """
                SELECT preview_sent_at IS NULL AS no_sent
                FROM candidate_job_contexts
                WHERE phone=%s AND conversation_id=%s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (CV_PHONE, f"{MARKER}-cv-before"),
            )
            row = cur.fetchone()
            assert row and row["no_sent"] is True

    check("preview_stamped_zero_apps", case_preview_stamped_no_app)
    check("confirm_creates_awaiting_cv", case_confirm_creates_one)
    check("confirm_idempotent", case_confirm_idempotent)
    check("public_canary_open_to_any_phone", case_public_canary_open_to_any_phone)
    check("non_canary_job_no_convert", case_non_canary_job_no_convert)
    check("cv_before_preview_no_app", case_cv_before_preview_no_app)

    cleanup(codes, phones)

    passed = sum(1 for r in results if r["ok"])
    report = {
        "marker": MARKER,
        "apply_code": apply_code,
        "database": "wathefni_staging",
        "passed": passed,
        "total": len(results),
        "results": results,
        "result": "PASS" if passed == len(results) else "FAIL",
    }
    path = os.environ.get("STAGE_B_REPORT_PATH") or os.path.join(
        ROOT, "ops/reports/jobs-phase2-stage-b-staging-latest.json"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(json.dumps({"RESULT": report["result"], "passed": passed, "total": len(results), "report": path}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
