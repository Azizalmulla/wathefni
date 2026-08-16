#!/usr/bin/env python3
"""Wave 1 — Probation DB integration prove (staging/canary).

Process-scoped flags only. No UI. Proves:
  schema, gates, 30/60/90 seed, case SM active→under_review→confirmed|extended|failed,
  overdue mark, extend writes new end, module-off, idempotency, tenant isolation.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
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

        return app.db_connect(), True, RealDictCursor
    conn = psycopg2.connect(url)
    return conn, False, RealDictCursor


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'probation_canary', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='probation_canary'
        """,
        (company, module_key, enabled),
    )


def _ensure_employee(cur, company: str, key: str, start: date, phone_suffix: str = "0") -> None:
    digits = "".join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, "8")
    phone = f"965{phone_suffix}{digits}"
    cur.execute(
        """
        INSERT INTO employees (
          employee_key, company_code, name, phone, employment_status, start_date, updated_at
        ) VALUES (%s,%s,%s,%s,'active',%s,now())
        ON CONFLICT (employee_key) DO UPDATE SET
          employment_status='active', start_date=EXCLUDED.start_date, updated_at=now()
        """,
        (key, company, f"Probationer {SUFFIX}", phone, start),
    )


def main() -> int:
    print("    probation wave1 — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import probation as pr

    company = f"PRB{SUFFIX}".upper()
    other = f"PRX{SUFFIX}".upper()
    start = date.today() - timedelta(days=5)
    emp = f"{company}-PROB-{SUFFIX}"

    os.environ["WATHEFNI_PROBATION"] = "on"
    os.environ["WATHEFNI_PROBATION_COMPANIES"] = company

    try:
        conn, _via_app, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pr.ensure_probation_schema(cur)
            conn.commit()
            pr.ensure_probation_schema(cur)
            conn.commit()

            cur.execute(
                """
                SELECT count(*) AS c FROM information_schema.tables
                 WHERE table_schema='public'
                   AND table_name IN (
                     'probation_settings',
                     'probation_plan_templates',
                     'probation_plan_template_milestones',
                     'probation_cases',
                     'probation_milestones',
                     'probation_events'
                   )
                """
            )
            check("migration tables present", int(dict(cur.fetchone())["c"]) == 6)

            settings = pr.get_settings(cur, company)
            check("settings default disabled", settings.get("enabled") is False, settings)
            gate0 = pr.probation_enabled_for_company(cur, company)
            check("gate off before enable", gate0.get("ok") is False, gate0)

            pr.set_settings(cur, company, enabled=True, auto_plan_on_hire=True)
            _upsert_module(cur, company, "probation", True)
            conn.commit()
            gate1 = pr.probation_enabled_for_company(cur, company)
            check("gate on after enable", gate1.get("ok") is True, gate1)

            # Module-off other company
            os.environ["WATHEFNI_PROBATION_COMPANIES"] = f"{company},{other}"
            gate_other = pr.probation_enabled_for_company(cur, other)
            check("other company disabled without enable", gate_other.get("ok") is False, gate_other)
            os.environ["WATHEFNI_PROBATION_COMPANIES"] = company

            _ensure_employee(cur, company, emp, start, phone_suffix="1")
            conn.commit()

            created = pr.create_case(
                cur,
                company_code=company,
                employee_key=emp,
                probation_start=start,
                probation_days=90,
                actor_user_id="hr1",
                idempotency_key=f"case:{SUFFIX}",
            )
            conn.commit()
            check("create case ok", created.get("ok") is True, created)
            check("case status active", (created.get("case") or {}).get("status") == "active", created.get("case"))
            ms = created.get("milestones") or []
            check("seeded 3 milestones", len(ms) == 3, [m.get("milestone_key") for m in ms])
            check(
                "milestone keys 30/60/90",
                {m.get("milestone_key") for m in ms} == {"day_30", "day_60", "day_90"},
                ms,
            )
            case_id = (created.get("case") or {}).get("case_id")

            replay = pr.create_case(
                cur,
                company_code=company,
                employee_key=emp,
                probation_start=start,
                idempotency_key=f"case:{SUFFIX}",
            )
            check("idempotent replay", replay.get("replayed") is True and replay.get("ok") is True, replay)

            # Complete day_30
            u30 = pr.update_milestone(
                cur,
                company_code=company,
                case_id=case_id,
                milestone_key="day_30",
                to_status="completed",
                actor_user_id="mgr1",
                notes="good progress",
            )
            check("complete day_30", u30.get("ok") is True, u30)

            # Mark overdue artificially
            cur.execute(
                """
                UPDATE probation_milestones
                   SET due_on=%s
                 WHERE case_id=%s AND milestone_key='day_60'
                """,
                (date.today() - timedelta(days=1), case_id),
            )
            overdue = pr.mark_overdue_milestones(cur, company_code=company)
            check("overdue marked", overdue.get("ok") is True and overdue.get("marked", 0) >= 1, overdue)

            # SM: active → under_review → confirmed
            rev = pr.transition_case(
                cur, company_code=company, case_id=case_id, to_status="under_review", actor_user_id="hr1"
            )
            check("active→under_review", rev.get("ok") is True, rev)
            conf = pr.transition_case(
                cur,
                company_code=company,
                case_id=case_id,
                to_status="confirmed",
                actor_user_id="hr1",
                decision_reason="passed probation",
            )
            check("under_review→confirmed", conf.get("ok") is True, conf)
            check("confirmed terminal", (conf.get("case") or {}).get("status") == "confirmed", conf.get("case"))

            # Extended path on second employee
            emp2 = f"{company}-EXT-{SUFFIX}"
            _ensure_employee(cur, company, emp2, start, phone_suffix="2")
            c2 = pr.create_case(
                cur,
                company_code=company,
                employee_key=emp2,
                probation_start=start,
                probation_days=90,
                idempotency_key=f"ext:{SUFFIX}",
            )
            cid2 = (c2.get("case") or {}).get("case_id")
            pr.transition_case(
                cur, company_code=company, case_id=cid2, to_status="under_review", actor_user_id="hr1"
            )
            old_end = (c2.get("case") or {}).get("probation_end")
            ext = pr.extend_case(
                cur,
                company_code=company,
                case_id=cid2,
                extend_days=30,
                actor_user_id="hr1",
                decision_reason="need more time",
            )
            conn.commit()
            check("extend ok", ext.get("ok") is True, ext)
            check("status extended", (ext.get("case") or {}).get("status") == "extended", ext.get("case"))
            new_end = (ext.get("case") or {}).get("probation_end")
            check("probation_end advanced", str(new_end)[:10] > str(old_end)[:10], {"old": old_end, "new": new_end})

            # Failed path
            emp3 = f"{company}-FAIL-{SUFFIX}"
            _ensure_employee(cur, company, emp3, start, phone_suffix="3")
            c3 = pr.create_case(
                cur,
                company_code=company,
                employee_key=emp3,
                probation_start=start,
                idempotency_key=f"fail:{SUFFIX}",
            )
            cid3 = (c3.get("case") or {}).get("case_id")
            pr.transition_case(
                cur, company_code=company, case_id=cid3, to_status="under_review", actor_user_id="hr1"
            )
            failed = pr.transition_case(
                cur,
                company_code=company,
                case_id=cid3,
                to_status="failed",
                actor_user_id="hr1",
                decision_reason="did not meet standards",
            )
            check("under_review→failed", failed.get("ok") is True, failed)

            # Decision reason required
            emp4 = f"{company}-NOR-{SUFFIX}"
            _ensure_employee(cur, company, emp4, start, phone_suffix="4")
            c4 = pr.create_case(
                cur, company_code=company, employee_key=emp4, probation_start=start, idempotency_key=f"nor:{SUFFIX}"
            )
            cid4 = (c4.get("case") or {}).get("case_id")
            pr.transition_case(
                cur, company_code=company, case_id=cid4, to_status="under_review", actor_user_id="hr1"
            )
            no_reason = pr.transition_case(
                cur, company_code=company, case_id=cid4, to_status="confirmed", actor_user_id="hr1"
            )
            check("decision reason required", no_reason.get("error") == "decision_reason_required", no_reason)

            # Tenant isolation — other company cannot see case
            stolen = pr.get_case(cur, company_code=other, case_id=case_id)
            check("tenant isolation get_case", stolen is None)

            # Runtime off
            os.environ["WATHEFNI_PROBATION"] = "off"
            gate_off = pr.probation_enabled_for_company(cur, company)
            check("runtime flag kill-switch", gate_off.get("ok") is False, gate_off)
            os.environ["WATHEFNI_PROBATION"] = "on"

            conn.commit()

    except Exception as exc:
        print(f"FAIL exception: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        try:
            conn.rollback()
        except Exception:
            pass
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass
        os.environ["WATHEFNI_PROBATION"] = "off"

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PROBATION_WAVE1_DB_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
