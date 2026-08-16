#!/usr/bin/env python3
"""Phase A slice 2 — task ontology + SLA DB prove (synthetic canary)."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        import app

        return app.db_connect(), RealDictCursor
    return psycopg2.connect(url), RealDictCursor


def main() -> int:
    print("    workflow_task_sla phase A slice 2 — DB prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    import workflow_task_sla as wts

    company = f"WFT{SUFFIX}".upper()
    other = f"WFX{SUFFIX}".upper()
    os.environ["WATHEFNI_WORKFLOW_TASKS"] = "on"
    os.environ["WATHEFNI_WORKFLOW_SLA"] = "on"
    os.environ["WATHEFNI_WORKFLOW_TASKS_COMPANIES"] = company
    os.environ["WATHEFNI_WORKFLOW_SLA_COMPANIES"] = company

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            wts.ensure_workflow_task_sla_schema(cur)
            conn.commit()
            wts.ensure_workflow_task_sla_schema(cur)
            conn.commit()
            check("migration idempotent", True)

            types = wts.list_task_types(cur)
            type_keys = {t["task_type"] for t in types}
            check(
                "catalogue seeded",
                set(wts.CANONICAL_TASK_TYPES).issubset(type_keys),
                type_keys,
            )

            # defaults disabled
            tg = wts.tasks_enabled_for_company(cur, company)
            sg = wts.sla_enabled_for_company(cur, company)
            check("tasks default disabled", tg.get("gate") == "company_setting", tg)
            check("sla default disabled", sg.get("gate") == "company_setting", sg)

            # fail-closed flags
            os.environ["WATHEFNI_WORKFLOW_TASKS"] = "off"
            check(
                "tasks runtime gate",
                wts.tasks_enabled_for_company(cur, company).get("gate") == "runtime_flag",
            )
            os.environ["WATHEFNI_WORKFLOW_TASKS"] = "on"
            os.environ["WATHEFNI_WORKFLOW_TASKS_COMPANIES"] = "NOPE"
            check(
                "tasks allowlist gate",
                wts.tasks_enabled_for_company(cur, company).get("gate") == "company_allowlist",
            )
            os.environ["WATHEFNI_WORKFLOW_TASKS_COMPANIES"] = company
            os.environ["WATHEFNI_WORKFLOW_SLA"] = "off"
            check(
                "sla runtime gate",
                wts.sla_enabled_for_company(cur, company).get("gate") == "runtime_flag",
            )
            os.environ["WATHEFNI_WORKFLOW_SLA"] = "on"

            wts.set_task_enabled(cur, company, enabled=True)
            wts.set_sla_enabled(cur, company, enabled=True, reminders_enabled=True)
            check("tasks gate open", wts.tasks_enabled_for_company(cur, company).get("ok") is True)
            check("sla gate open", wts.sla_enabled_for_company(cur, company).get("ok") is True)
            conn.commit()

            # task create + resolve + idempotency + concurrency
            created = wts.create_workflow_task(
                cur,
                company_code=company,
                task_type="preboard_item",
                title="Canary preboard item",
                subject_id=f"WFT-SYNTH|{SUFFIX}|item",
                actor_user_id="u-hr",
                idempotency_key=f"WFT-SYNTH|{SUFFIX}|t1",
            )
            check("task create", created.get("ok") is True, created)
            replay = wts.create_workflow_task(
                cur,
                company_code=company,
                task_type="preboard_item",
                title="Canary preboard item",
                subject_id=f"WFT-SYNTH|{SUFFIX}|item-other",
                idempotency_key=f"WFT-SYNTH|{SUFFIX}|t1",
            )
            check("task idempotent replay", replay.get("replayed") is True, replay)
            task = created["task"]
            check("task on hr_tasks SoT", task["task_type"] == "preboard_item" and task["status"] == "open")
            check("subject_type from catalogue", task.get("subject_type") == "preboard_item", task)

            stale = wts.resolve_workflow_task(
                cur,
                company_code=company,
                task_id=task["task_id"],
                expected_row_version=int(task["row_version"]) + 9,
            )
            check("task stale row_version", stale.get("error") == "concurrency_conflict", stale)

            resolved = wts.resolve_workflow_task(
                cur,
                company_code=company,
                task_id=task["task_id"],
                status="done",
                actor_phone="96577000002",
                expected_row_version=task["row_version"],
            )
            check("task resolve", resolved.get("ok") is True and resolved["task"]["status"] == "done", resolved)

            # cross-tenant
            cross = wts.get_task_for_company(cur, company_code=other, task_id=task["task_id"])
            check("cross-tenant task read denial", cross is None)

            bad_type = wts.create_workflow_task(
                cur,
                company_code=company,
                task_type="not_a_real_type",
                title="x",
            )
            check("unknown task_type denied", bad_type.get("error") == "task_type_unknown", bad_type)

            # SLA policy + clock + reminder + breach → sla_breach task
            pol = wts.upsert_sla_policy(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                name="Canary SLA",
                due_in_seconds=3600,
                remind_before_seconds=1800,
                escalate_to_user_id="u-escalation",
                actor_user_id="u-admin",
            )
            check("sla policy upsert", pol.get("ok") is True, pol)

            t0 = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
            started = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id=f"WFT-SYNTH|{SUFFIX}|subj",
                idempotency_key=f"WFT-SYNTH|{SUFFIX}|clock",
                now=t0,
            )
            check("sla clock start", started.get("ok") is True, started)
            clock = started["clock"]
            replay_c = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id=f"WFT-SYNTH|{SUFFIX}|subj2",
                idempotency_key=f"WFT-SYNTH|{SUFFIX}|clock",
                now=t0,
            )
            check("sla clock idempotent", replay_c.get("replayed") is True, replay_c)

            # reminder tick
            mid = t0 + timedelta(seconds=1800)
            tick_r = wts.tick_sla_clock(
                cur, company_code=company, clock_id=clock["clock_id"], now=mid
            )
            check(
                "sla reminder audit",
                tick_r.get("ok") is True and "reminded" in (tick_r.get("actions") or []),
                tick_r,
            )

            # breach tick
            past = t0 + timedelta(seconds=3601)
            # reload clock for current row_version after reminder
            clock2 = wts._load_clock(cur, company_code=company, clock_id=clock["clock_id"])
            tick_b = wts.tick_sla_clock(
                cur, company_code=company, clock_id=clock["clock_id"], now=past
            )
            check(
                "sla breach",
                tick_b.get("ok") is True
                and tick_b["clock"]["status"] == "breached"
                and tick_b["clock"].get("breach_task_id"),
                tick_b,
            )
            breach_task = wts.get_task_for_company(
                cur, company_code=company, task_id=tick_b["clock"]["breach_task_id"]
            )
            check(
                "breach creates sla_breach hr_task",
                breach_task is not None and breach_task["task_type"] == "sla_breach",
                breach_task,
            )

            # satisfy path on a fresh clock
            started2 = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id=f"WFT-SYNTH|{SUFFIX}|subj-sat",
                now=t0,
            )
            sat = wts.satisfy_sla_clock(
                cur,
                company_code=company,
                clock_id=started2["clock"]["clock_id"],
                expected_row_version=started2["clock"]["row_version"],
            )
            check("sla satisfy", sat.get("ok") is True and sat["clock"]["status"] == "satisfied", sat)

            # cancel path
            started3 = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id=f"WFT-SYNTH|{SUFFIX}|subj-can",
                now=t0,
            )
            can = wts.cancel_sla_clock(
                cur,
                company_code=company,
                clock_id=started3["clock"]["clock_id"],
                expected_row_version=started3["clock"]["row_version"],
            )
            check("sla cancel", can.get("ok") is True and can["clock"]["status"] == "cancelled", can)

            # modularity: SLA clock still works if tasks disabled (no breach task)
            wts.set_task_enabled(cur, company, enabled=False)
            started4 = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id=f"WFT-SYNTH|{SUFFIX}|subj-notask",
                now=t0,
            )
            tick_nt = wts.tick_sla_clock(
                cur,
                company_code=company,
                clock_id=started4["clock"]["clock_id"],
                now=past,
            )
            check(
                "SLA without tasks still breaches clock",
                tick_nt.get("ok") is True
                and tick_nt["clock"]["status"] == "breached"
                and not tick_nt["clock"].get("breach_task_id"),
                tick_nt,
            )
            wts.set_task_enabled(cur, company, enabled=True)

            # cross-tenant clock
            xclock = wts._load_clock(cur, company_code=other, clock_id=clock["clock_id"])
            check("cross-tenant clock read denial", xclock is None)

            # disable returns safely
            wts.set_task_enabled(cur, company, enabled=False)
            wts.set_sla_enabled(cur, company, enabled=False)
            blocked_t = wts.create_workflow_task(
                cur, company_code=company, task_type="sla_breach", title="blocked"
            )
            blocked_s = wts.start_sla_clock(
                cur,
                company_code=company,
                subject_type="phase_a_canary_subject",
                subject_id="blocked",
            )
            check("disable tasks blocks create", blocked_t.get("gate") == "company_setting", blocked_t)
            check("disable sla blocks clock", blocked_s.get("gate") == "company_setting", blocked_s)

            cur.execute(
                """
                SELECT event_type, count(*) AS c FROM workflow_task_sla_events
                 WHERE company_code=%s GROUP BY event_type
                """,
                (company,),
            )
            ev = {r["event_type"]: int(r["c"]) for r in cur.fetchall()}
            need = {
                "task_created",
                "task_resolved",
                "sla_policy_upserted",
                "sla_clock_started",
                "sla_reminder_due",
                "sla_breached",
                "sla_satisfied",
                "sla_cancelled",
            }
            missing = sorted(need - set(ev))
            check("audit events present", not missing, {"missing": missing, "seen": ev})

            # legacy hr_tasks path untouched: delivery_failed still not blocked by catalogue
            cur.execute(
                """
                INSERT INTO hr_tasks (task_id, company_code, task_type, source, title, status, priority, metadata)
                VALUES (%s,%s,'delivery_failed','legacy_probe','legacy', 'open','normal','{}'::jsonb)
                """,
                (str(uuid.uuid4()), company),
            )
            check("legacy hr_task type still insertable", True)
            conn.commit()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "DELETE FROM workflow_task_sla_events WHERE company_code=%s", (company,)
            )
            cur.execute("DELETE FROM workflow_sla_clocks WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM workflow_sla_policies WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM workflow_sla_settings WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM workflow_task_settings WHERE company_code=%s", (company,))
            cur.execute(
                "DELETE FROM hr_tasks WHERE company_code=%s AND (source=%s OR metadata->>'ontology'=%s OR title=%s)",
                (company, "workflow_task_sla", "workflow_task_sla_v1", "legacy"),
            )
            conn.commit()
            check("synthetic cleanup", True)
    finally:
        conn.close()
        for k in (
            "WATHEFNI_WORKFLOW_TASKS",
            "WATHEFNI_WORKFLOW_SLA",
            "WATHEFNI_WORKFLOW_TASKS_COMPANIES",
            "WATHEFNI_WORKFLOW_SLA_COMPANIES",
        ):
            os.environ.pop(k, None)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("    PHASE_A_SLICE2_DB_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
