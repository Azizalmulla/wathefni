"""Smoke test: Canonical Recruiting Lifecycle (staging-first).

Covers:
  - vocabulary + legacy status mapping
  - strict transition matrix
  - human confirmation / AI cannot mutate stages
  - WhatsApp conversation binding fail-closed on ambiguity
  - idempotent candidate_ready_for_review HR task
  - communication status normalization
  - web/mobile stage label consistency
  - permissions (reject = candidate.decide)

Flag: WATHEFNI_CANONICAL_LIFECYCLE (default OFF). This test enables it for the
behaviour section and restores the previous value afterwards.

Run: WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-canonical-recruiting-lifecycle.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" — {detail}" if detail else ""
        print(f"      FAIL  {label}{suffix}")


def main() -> int:
    print("    canonical recruiting lifecycle — matrix + binding + task + labels")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))

    import recruiting_lifecycle as rl

    # --- 1) vocabulary -------------------------------------------------------
    expected = {
        "awaiting_cv",
        "cv_processing",
        "ready_for_review",
        "shortlisted",
        "interview",
        "hired",
        "rejected",
        "withdrawn",
    }
    check("exactly eight application stages", set(rl.APPLICATION_STAGES) == expected)
    check("offer is not a canonical stage", "offered" not in rl.APPLICATION_STAGES and "offer_sent" not in rl.APPLICATION_STAGES)
    check("communication states are four values", set(rl.COMMUNICATION_STATES) == {"pending", "sent", "failed", "intentionally_skipped"})

    # --- 2) legacy mapping ---------------------------------------------------
    mapping = {
        "cv_received": "cv_processing",
        "screening": "cv_processing",
        "screening_complete": "ready_for_review",
        "review_pending": "ready_for_review",
        "offered": "shortlisted",
        "offer_sent": "shortlisted",
        "scheduled": "interview",
        "needs_role": None,
        "import_review": None,
    }
    for raw, want in mapping.items():
        got = rl.normalize_stage(raw)
        check(f"legacy map {raw} -> {want}", got == want, f"got {got}")

    # --- 3) transition matrix ------------------------------------------------
    allowed = {
        ("awaiting_cv", "cv_processing"),
        ("cv_processing", "ready_for_review"),
        ("ready_for_review", "shortlisted"),
        ("ready_for_review", "interview"),
        ("ready_for_review", "rejected"),
        ("shortlisted", "interview"),
        ("shortlisted", "hired"),
        ("shortlisted", "rejected"),
        ("interview", "hired"),
        ("interview", "rejected"),
        ("interview", "shortlisted"),
    }
    for src, dst in allowed:
        check(f"allows {src} -> {dst}", rl.transition_is_allowed(src, dst))
    forbidden = [
        ("awaiting_cv", "hired"),
        ("cv_processing", "hired"),
        ("ready_for_review", "hired"),
        ("hired", "shortlisted"),
        ("rejected", "shortlisted"),
        ("awaiting_cv", "interview"),
    ]
    for src, dst in forbidden:
        check(f"blocks {src} -> {dst}", not rl.transition_is_allowed(src, dst))

    # --- 4) confirmation + AI hard boundary ---------------------------------
    check("shortlist requires human confirmation", rl.human_confirmation_required("shortlisted", trigger="dashboard_shortlist"))
    check("reject requires human confirmation", rl.human_confirmation_required("rejected", trigger="dashboard_reject"))
    check("hire requires human confirmation", rl.human_confirmation_required("hired", trigger="dashboard_hire"))
    check("schedule requires human confirmation", rl.human_confirmation_required("interview", trigger="schedule_interview"))
    check("cv success does not require confirmation", not rl.human_confirmation_required("ready_for_review", trigger="cv_processing_success"))
    check("reject permission is candidate.decide", rl.permission_for_target("rejected") == "candidate.decide")
    check("hire permission is candidate.decide", rl.permission_for_target("hired") == "candidate.decide")
    check("shortlist permission is candidate.manage", rl.permission_for_target("shortlisted") == "candidate.manage")

    # Pure unit call without DB for AI block / confirmation block.
    class _FakeLegacy:
        @staticmethod
        def digits(value):
            return "".join(ch for ch in str(value or "") if ch.isdigit()) or None

        @staticmethod
        def json_safe(value):
            return value

        class Json:
            def __init__(self, value):
                self.value = value

        def db_connect(self):
            raise RuntimeError("db_should_not_be_reached_for_precheck")

    fake = _FakeLegacy()
    ai_block = rl.transition_application(
        fake,
        app_key="x",
        to_stage="shortlisted",
        trigger="ai_proposal",
        actor_type="ai",
        human_confirmed=False,
    )
    check("AI cannot shortlist without confirmation", ai_block.get("error") == "ai_cannot_mutate_stage")
    no_confirm = rl.transition_application(
        fake,
        app_key="x",
        to_stage="rejected",
        trigger="dashboard_reject",
        actor_type="human",
        human_confirmed=False,
        permissions={"candidate.decide"},
    )
    check("reject without confirmation fails closed", no_confirm.get("error") == "confirmation_required")

    # --- 5) labels consistency (web/mobile shared) ---------------------------
    for stage, label in {
        "ready_for_review": "Ready for review",
        "screening_complete": "Ready for review",
        "review_pending": "Ready for review",
        "cv_processing": "Processing CV",
        "cv_received": "Processing CV",
        "shortlisted": "Shortlisted",
        "interview": "Interview",
        "hired": "Hired",
        "rejected": "Rejected",
        "withdrawn": "Withdrawn",
    }.items():
        check(f"label {stage}", rl.stage_label(stage) == label, f"got {rl.stage_label(stage)}")

    # --- 6) communication normalization --------------------------------------
    for raw, want in {
        "delivered_whatsapp": "sent",
        "sent_email_fallback": "sent",
        "needs_hr_action": "failed",
        "suppressed": "intentionally_skipped",
        "dashboard_only": "intentionally_skipped",
        "pending": "pending",
        "throttled": "pending",
    }.items():
        check(f"comm {raw} -> {want}", rl.normalize_communication_status(raw) == want)

    # --- 7) allowed actions parity -------------------------------------------
    manage_decide = {"candidate.manage", "candidate.decide", "interview.manage"}
    actions_ready = rl.allowed_actions_for_stage("ready_for_review", manage_decide)
    check("ready_for_review actions include shortlist+reject+schedule", set(actions_ready) >= {"shortlist", "reject", "schedule_interview"})
    check("ready_for_review cannot hire directly", "hire" not in actions_ready)
    actions_short = rl.allowed_actions_for_stage("shortlisted", manage_decide)
    check("shortlisted can hire/reject/schedule", set(actions_short) >= {"hire", "reject", "schedule_interview"})
    check("terminal hired has no actions", rl.allowed_actions_for_stage("hired", manage_decide) == [])

    # --- 8) tool permission map ----------------------------------------------
    try:
        import tool_call_orchestrator as tco

        check("tool reject uses candidate.decide", tco.TOOL_PERMISSION_MAP.get("reject_candidate") == "candidate.decide")
        check("tool hire uses candidate.decide", tco.TOOL_PERMISSION_MAP.get("hire_candidate") == "candidate.decide")
        check("tool shortlist uses candidate.manage", tco.TOOL_PERMISSION_MAP.get("shortlist_candidate") == "candidate.manage")
    except Exception as exc:  # noqa: BLE001
        check("tool permission map importable", False, str(exc))

    # --- 9) behaviour against staging DB (optional) --------------------------
    orig_flag = os.environ.get("WATHEFNI_CANONICAL_LIFECYCLE")
    try:
        os.environ["WATHEFNI_CANONICAL_LIFECYCLE"] = "1"
        try:
            import app
        except ModuleNotFoundError as exc:
            if exc.name == "psycopg2":
                print("SKIP DB: psycopg2 not available locally; full DB proof runs on staging.")
                return 0 if FAIL == 0 else 1
            raise

        check("flag enabled", app.canonical_lifecycle_enabled())
        # Schema ensure
        try:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    rl.ensure_lifecycle_schema(cur)
                conn.commit()
            check("lifecycle schema ensure", True)
        except Exception as exc:  # noqa: BLE001
            check("lifecycle schema ensure", False, str(exc))
            return 1 if FAIL else 0

        company = "WATHEFNI"
        phone = f"9655{int(uuid.uuid4().hex[:7], 16) % 10_000_000:07d}"
        app_key_a = f"LIFECYCLE-A-{uuid.uuid4().hex[:8]}"
        app_key_b = f"LIFECYCLE-B-{uuid.uuid4().hex[:8]}"
        conv = f"wa-lifecycle-{uuid.uuid4().hex[:10]}"

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, current_status, active_company_code, data_source)
                    VALUES (%s,%s,'ready_for_review',%s,'production')
                    ON CONFLICT (phone) DO UPDATE SET
                      name=EXCLUDED.name,
                      active_company_code=EXCLUDED.active_company_code,
                      updated_at=now()
                    """,
                    (phone, "Lifecycle Smoke", company),
                )
                for key, position in ((app_key_a, "ROLE_A"), (app_key_b, "ROLE_B")):
                    cur.execute(
                        """
                        INSERT INTO applications
                          (app_key, phone, company_code, position_code, position_title, status, current_step,
                           cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,'ready_for_review','ready_for_review',true,'pending','{}'::jsonb,'production',now(),now(),now())
                        ON CONFLICT (app_key) DO UPDATE SET
                          phone=EXCLUDED.phone,
                          status='ready_for_review',
                          current_step='ready_for_review',
                          company_code=EXCLUDED.company_code,
                          updated_at=now()
                        """,
                        (key, phone, company, position, position),
                    )
            conn.commit()

        # Ambiguity: two open apps, no binding → fail closed
        ambiguous = rl.resolve_conversation_application(
            app,
            phone=phone,
            conversation_id=conv,
            company_code=company,
            allow_single_eligible=True,
        )
        check("WhatsApp ambiguity fails closed", ambiguous.get("error") == "ambiguous_applications", str(ambiguous.get("error")))

        # Bind then resolve
        bind = rl.bind_conversation_application(
            app,
            company_code=company,
            conversation_id=conv,
            phone=phone,
            app_key=app_key_a,
            bound_reason="explicit_apply",
        )
        check("conversation bind ok", bool(bind.get("ok")))
        resolved = rl.resolve_conversation_application(
            app,
            phone=phone,
            conversation_id=conv,
            company_code=company,
        )
        check(
            "bound conversation resolves to app A",
            bool(resolved.get("ok")) and (resolved.get("application") or {}).get("app_key") == app_key_a,
            str((resolved.get("application") or {}).get("app_key")),
        )

        # Transition shortlist with confirmation + stale check
        shortlist = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code=company,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            human_confirmed=True,
            actor_type="human",
            channel="web",
            permissions={"candidate.manage"},
            expected_from_stage="ready_for_review",
            idempotency_key=f"test-shortlist-{app_key_a}",
        )
        check("shortlist transition ok", bool(shortlist.get("ok")), str(shortlist.get("error")))
        check("shortlist to_stage", shortlist.get("to_stage") == "shortlisted")

        # Idempotent replay
        replay = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code=company,
            to_stage="shortlisted",
            trigger="dashboard_shortlist",
            human_confirmed=True,
            actor_type="human",
            channel="web",
            permissions={"candidate.manage"},
            expected_from_stage="ready_for_review",
            idempotency_key=f"test-shortlist-{app_key_a}",
        )
        check("shortlist idempotent replay", bool(replay.get("ok")) and bool(replay.get("idempotent")))

        # Stale expected stage fails
        stale = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code=company,
            to_stage="rejected",
            trigger="dashboard_reject",
            human_confirmed=True,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
            expected_from_stage="ready_for_review",
            idempotency_key=f"test-stale-{app_key_a}",
        )
        check("stale expected_from_stage fails closed", stale.get("error") == "stale_state", str(stale.get("error")))

        # Forbidden hire from ready_for_review on the unbound app
        bad_hire = rl.transition_application(
            app,
            app_key=app_key_b,
            company_code=company,
            to_stage="hired",
            trigger="dashboard_hire",
            human_confirmed=True,
            actor_type="human",
            channel="web",
            permissions={"candidate.decide"},
            expected_from_stage="ready_for_review",
        )
        check("hire from ready_for_review blocked", bad_hire.get("error") == "transition_not_allowed", str(bad_hire.get("error")))

        # Ready-for-review HR task idempotency
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM applications WHERE app_key=%s", (app_key_b,))
                app_b = dict(cur.fetchone())
        task1 = rl.ensure_ready_for_review_task(
            app,
            company_code=company,
            application=app_b,
            cv_version="cv-v1",
        )
        task2 = rl.ensure_ready_for_review_task(
            app,
            company_code=company,
            application=app_b,
            cv_version="cv-v1",
        )
        check("HR task created", bool(task1.get("ok")) and bool(task1.get("task_id")), str(task1))
        check(
            "HR task idempotent for same cv_version",
            bool(task2.get("ok")) and bool(task2.get("idempotent")) and task2.get("task_id") == task1.get("task_id"),
            f"{task1.get('task_id')} vs {task2.get('task_id')}",
        )
        task3 = rl.ensure_ready_for_review_task(
            app,
            company_code=company,
            application=app_b,
            cv_version="cv-v2",
        )
        check(
            "new CV version creates distinct ready task",
            bool(task3.get("ok")) and task3.get("task_id") != task1.get("task_id"),
            f"{task3.get('task_id')} vs {task1.get('task_id')}",
        )

        # Tenant isolation: wrong company cannot transition
        tenant = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code="OTHERCO",
            to_stage="rejected",
            trigger="dashboard_reject",
            human_confirmed=True,
            actor_type="human",
            permissions={"candidate.decide"},
        )
        check("tenant mismatch fails closed", tenant.get("error") in {"application_not_found", "tenant_mismatch"}, str(tenant.get("error")))

        # Cleanup test rows (best effort)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM application_lifecycle_events WHERE app_key IN (%s,%s)", (app_key_a, app_key_b))
                cur.execute("DELETE FROM conversation_application_bindings WHERE conversation_id=%s", (conv,))
                cur.execute(
                    "DELETE FROM hr_tasks WHERE company_code=%s AND metadata->>'app_key' IN (%s,%s)",
                    (company, app_key_a, app_key_b),
                )
                cur.execute("DELETE FROM applications WHERE app_key IN (%s,%s)", (app_key_a, app_key_b))
                cur.execute("DELETE FROM candidates WHERE phone=%s", (phone,))
            conn.commit()

    finally:
        if orig_flag is None:
            os.environ.pop("WATHEFNI_CANONICAL_LIFECYCLE", None)
        else:
            os.environ["WATHEFNI_CANONICAL_LIFECYCLE"] = orig_flag

    print(f"\n    result: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
