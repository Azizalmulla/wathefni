"""Production-safe synthetic smoke for Canonical Recruiting Lifecycle.

Creates ONLY synthetic candidate/application rows with a clear marker, exercises
lifecycle authority checks, then deletes every synthetic row. Never sends WhatsApp
or email, never mutates real applications, never creates interviews/employees for
real people.

Required env (production binding):
  WATHEFNI_CANONICAL_LIFECYCLE=1
  WATHEFNI_DELIVERY_MODE=dry_run   # or live env with dry_run override for this process
  production postgres binding

Run on the VPS against production only after code deploy + flag enable.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

PASS = 0
FAIL = 0
MARKER = "canonical_lifecycle_prod_smoke_v1"


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("    canonical lifecycle — production-safe synthetic smoke")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))

    import recruiting_lifecycle as rl
    import app

    if not rl.canonical_lifecycle_enabled():
        print("FAIL: WATHEFNI_CANONICAL_LIFECYCLE must be enabled for this proof")
        return 1

    # --- read mapping (no writes) -------------------------------------------
    for raw, want in {
        "screening_complete": "ready_for_review",
        "review_pending": "ready_for_review",
        "cv_received": "cv_processing",
        "screening": "cv_processing",
        "offered": "shortlisted",
        "scheduled": "interview",
    }.items():
        check(f"legacy read map {raw}", rl.normalize_stage(raw) == want)

    # Existing production candidates remain readable (sample, no mutation).
    readable = 0
    sample_statuses: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key, status, company_code
                FROM applications
                WHERE COALESCE(data_source, raw_json->>'data_source', 'production')='production'
                  AND company_code='WATHEFNI'
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 25
                """
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
    for row in rows:
        status = row.get("status")
        # Intake facets normalize to None; others must map or already be canonical.
        stage = rl.normalize_stage(status)
        intake = str(status or "").lower() in rl.INTAKE_STATUSES
        if stage is not None or intake:
            readable += 1
            sample_statuses.append(f"{status}->{stage}")
    check("existing production candidates remain readable", readable == len(rows) and len(rows) > 0, f"readable={readable}/{len(rows)}")

    # Snapshot counters for side-effect proof.
    company = "WATHEFNI"
    phone = f"9650{int(uuid.uuid4().hex[:8], 16) % 10_000_000:07d}"
    app_key_a = f"SMOKE-LIFE-A-{uuid.uuid4().hex[:8]}"
    app_key_b = f"SMOKE-LIFE-B-{uuid.uuid4().hex[:8]}"
    conv = f"smoke-life-{uuid.uuid4().hex[:10]}"

    def count_side_effects() -> dict[str, int]:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM candidate_interviews WHERE app_key IN (%s,%s)",
                    (app_key_a, app_key_b),
                )
                interviews = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT count(*) AS c FROM employees WHERE phone=%s",
                    (phone,),
                )
                employees = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    """
                    SELECT count(*) AS c FROM outbound_delivery_events
                    WHERE subject_key IN (%s,%s)
                    """,
                    (app_key_a, app_key_b),
                )
                outbound = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    """
                    SELECT count(*) AS c FROM action_results
                    WHERE COALESCE(result::text, '') LIKE %s
                       OR COALESCE(final_reply, '') LIKE %s
                    """,
                    (f"%{MARKER}%", f"%{MARKER}%"),
                )
                actions = int((cur.fetchone() or {}).get("c") or 0)
        return {
            "interviews": interviews,
            "employees": employees,
            "outbound": outbound,
            "action_results": actions,
        }

    before = count_side_effects()

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO candidates (phone, name, current_status, active_company_code, data_source, raw_json)
                    VALUES (%s,%s,'ready_for_review',%s,'production',%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET
                      name=EXCLUDED.name,
                      raw_json=COALESCE(candidates.raw_json,'{}'::jsonb) || EXCLUDED.raw_json,
                      updated_at=now()
                    """,
                    (phone, "Lifecycle Prod Smoke", company, app.Json({"smoke_marker": MARKER})),
                )
                for key, position in ((app_key_a, "SMOKE_ROLE_A"), (app_key_b, "SMOKE_ROLE_B")):
                    cur.execute(
                        """
                        INSERT INTO applications
                          (app_key, phone, company_code, position_code, position_title, status, current_step,
                           cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,'ready_for_review','ready_for_review',true,'pending',%s::jsonb,'production',now(),now(),now())
                        ON CONFLICT (app_key) DO UPDATE SET
                          phone=EXCLUDED.phone, status='ready_for_review', current_step='ready_for_review',
                          raw_json=EXCLUDED.raw_json, updated_at=now()
                        """,
                        (key, phone, company, position, position, app.Json({"smoke_marker": MARKER})),
                    )
            conn.commit()

        # Ambiguous WhatsApp mutation rejection
        ambiguous = rl.resolve_conversation_application(
            app, phone=phone, conversation_id=conv, company_code=company, allow_single_eligible=True
        )
        check("ambiguous WhatsApp mutation rejection", ambiguous.get("error") == "ambiguous_applications", str(ambiguous.get("error")))

        # Conversation-bound app_key
        bind = rl.bind_conversation_application(
            app,
            company_code=company,
            conversation_id=conv,
            phone=phone,
            app_key=app_key_a,
            bound_reason="smoke_explicit",
            metadata={"smoke_marker": MARKER},
        )
        check("conversation bind ok", bool(bind.get("ok")))
        resolved = rl.resolve_conversation_application(
            app, phone=phone, conversation_id=conv, company_code=company
        )
        check(
            "conversation-bound app_key",
            bool(resolved.get("ok")) and (resolved.get("application") or {}).get("app_key") == app_key_a,
            str((resolved.get("application") or {}).get("app_key")),
        )

        # Valid shortlist
        shortlist = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code=company,
            to_stage="shortlisted",
            trigger="prod_smoke_shortlist",
            human_confirmed=True,
            actor_type="human",
            channel="system",
            permissions={"candidate.manage"},
            expected_from_stage="ready_for_review",
            idempotency_key=f"prod-smoke-shortlist-{app_key_a}",
            metadata={"smoke_marker": MARKER},
        )
        check("valid shortlist", bool(shortlist.get("ok")) and shortlist.get("to_stage") == "shortlisted", str(shortlist.get("error")))

        # Stale transition rejection
        stale = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code=company,
            to_stage="rejected",
            trigger="prod_smoke_stale",
            human_confirmed=True,
            actor_type="human",
            channel="system",
            permissions={"candidate.decide"},
            expected_from_stage="ready_for_review",
            idempotency_key=f"prod-smoke-stale-{app_key_a}",
            metadata={"smoke_marker": MARKER},
        )
        check("stale transition rejection", stale.get("error") == "stale_state", str(stale.get("error")))

        # Hire blocked from ready_for_review
        bad_hire = rl.transition_application(
            app,
            app_key=app_key_b,
            company_code=company,
            to_stage="hired",
            trigger="prod_smoke_hire",
            human_confirmed=True,
            actor_type="human",
            channel="system",
            permissions={"candidate.decide"},
            expected_from_stage="ready_for_review",
            run_hire_side_effects=False,
            metadata={"smoke_marker": MARKER},
        )
        check("hire blocked from ready_for_review", bad_hire.get("error") == "transition_not_allowed", str(bad_hire.get("error")))

        # Ready-for-review task created once
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM applications WHERE app_key=%s", (app_key_b,))
                app_b = dict(cur.fetchone())
        task1 = rl.ensure_ready_for_review_task(app, company_code=company, application=app_b, cv_version="prod-smoke-cv-1")
        task2 = rl.ensure_ready_for_review_task(app, company_code=company, application=app_b, cv_version="prod-smoke-cv-1")
        check("ready-for-review task created", bool(task1.get("ok")) and bool(task1.get("task_id")), str(task1))
        check(
            "ready-for-review task created once",
            bool(task2.get("ok")) and bool(task2.get("idempotent")) and task2.get("task_id") == task1.get("task_id"),
            f"{task1.get('task_id')} vs {task2.get('task_id')}",
        )

        # Tenant isolation
        tenant = rl.transition_application(
            app,
            app_key=app_key_a,
            company_code="OTHERCO",
            to_stage="rejected",
            trigger="prod_smoke_tenant",
            human_confirmed=True,
            actor_type="human",
            permissions={"candidate.decide"},
            metadata={"smoke_marker": MARKER},
        )
        check("tenant isolation", tenant.get("error") in {"application_not_found", "tenant_mismatch"}, str(tenant.get("error")))

    finally:
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

    after = count_side_effects()
    check("no interviews created by smoke", after["interviews"] == before["interviews"] == 0)
    check("no employees created by smoke", after["employees"] == before["employees"] == 0)
    check("no outbound messages created by smoke", after["outbound"] == before["outbound"] == 0)
    check(
        "no durable decision audits left for smoke marker",
        after["action_results"] == before["action_results"],
        f"before={before['action_results']} after={after['action_results']}",
    )

    # Synthetic rows gone
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key IN (%s,%s)", (app_key_a, app_key_b))
            left = int((cur.fetchone() or {}).get("c") or 0)
    check("synthetic applications cleaned up", left == 0)

    print(f"\n    result: {PASS} passed, {FAIL} failed")
    print(f"    sample_status_maps: {', '.join(sample_statuses[:8])}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
