#!/usr/bin/env python3
"""Prove HR Intelligence automatic freshness: outbox, idempotency, retry, data_as_of."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"HIF{_N:05d}"[:12].upper()
OTHER = f"HIO{_N:05d}"[:12].upper()
HR = f"9656711{_N:05d}"
EMP = f"EMP-{SUFFIX}"
EMP_NODATE = f"EMP-ND-{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags() -> None:
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    os.environ["WATHEFNI_HR_INTELLIGENCE_STALE_AFTER_SECONDS"] = "180"
    os.environ["WATHEFNI_HR_INTELLIGENCE_PROJECTION_MAX_ATTEMPTS"] = "3"
    os.environ["WATHEFNI_HR_INTELLIGENCE_PROJECTION_ACTOR"] = HR


def main() -> int:
    print("    hr intelligence projection freshness — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_projection as proj
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_workforce_c2 as c2

    _flags()
    check("phase", proj.PHASE == "hr_intelligence_projection_freshness")
    check("no payroll family in incremental sources", "payroll" not in proj.SOURCE_FAMILIES)
    check("semantic workforce", proj.family_for_semantic_key("workforce.headcount.active_heads") == "workforce")
    check("semantic leave", proj.family_for_semantic_key("leave.utilization") == "leave")
    check("semantic payroll", proj.family_for_semantic_key("payroll.workforce_cost") == "payroll")
    check("incremental families exclude payroll", "payroll" not in proj.SOURCE_FAMILIES)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise
    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c1.ensure_hr_intelligence_registry_c1_schema(cur)
            c2.ensure_hr_intelligence_workforce_c2_schema(cur)
            proj.ensure_hr_intelligence_projection_schema(cur)
            for code, name in ((COMPANY, f"HIF {COMPANY}"), (OTHER, f"HIO {OTHER}")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, name),
                )
            en = c2.enable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="enable freshness")
            check("enable c2", en.get("ok") is True, en)
            c2.publish_workforce_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="publish freshness")
            c2.enable_company_workforce_intelligence(cur, company_code=OTHER, actor_phone=HR, reason="enable other")

            missing = proj.project_workforce_row(
                cur,
                company=COMPANY,
                emp={"employee_key": EMP_NODATE, "employment_status": "active"},
                actor=HR,
            )
            check("skip missing employment date", missing.get("skipped") is True and missing.get("reason") == "missing_employment_date", missing)

            first = proj.enqueue(
                cur,
                company_code=COMPANY,
                source_family="workforce",
                entity_type="employee",
                entity_id=EMP,
                event_ref="test:1",
                payload={
                    "employee_key": EMP,
                    "employment_status": "active",
                    "start_date": str(date.today() - timedelta(days=30)),
                    "hire_date": str(date.today() - timedelta(days=30)),
                    "profile": {"department": "Ops"},
                    "raw_json": {},
                },
            )
            second = proj.enqueue(
                cur,
                company_code=COMPANY,
                source_family="workforce",
                entity_type="employee",
                entity_id=EMP,
                event_ref="test:1",
                payload={"employee_key": EMP},
            )
            check("enqueue ok", first.get("ok") is True and first.get("enqueued") is True, first)
            check("enqueue idempotent", second.get("ok") is True and second.get("enqueued") is False, second)

            other_q = proj.enqueue(
                cur,
                company_code=OTHER,
                source_family="workforce",
                entity_type="employee",
                entity_id=f"{EMP}-X",
                event_ref="test:other",
                payload={
                    "employee_key": f"{EMP}-X",
                    "employment_status": "active",
                    "start_date": str(date.today() - timedelta(days=10)),
                },
            )
            check("other tenant enqueue isolated key", other_q.get("company_code") == OTHER, other_q)

            drained = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            check("drain processed", drained.get("processed") >= 1 and drained.get("failed") == 0, drained)
            cur.execute(
                "SELECT status FROM hr_intelligence_employment_periods WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            row = cur.fetchone()
            check("projected employment period", bool(row) and dict(row).get("status") == "active", row)

            hc = c1.evaluate_kpi(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window={"as_of": str(date.today())},
            )
            check("headcount after projection", hc.get("status") in {"ok", "stale"} and float(hc.get("value") or 0) >= 1, hc)
            check("freshness data_as_of present", bool((hc.get("freshness") or {}).get("data_as_of")), hc.get("freshness"))
            check("freshness guaranteed after drain", (hc.get("freshness") or {}).get("guaranteed_current") is True, hc.get("freshness"))
            check("freshness not labelled current when payroll", proj.freshness_for_semantic_key(cur, company_code=COMPANY, semantic_key="payroll.workforce_cost").get("guaranteed_current") is False)

            drained_again = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            check("second drain idle", drained_again.get("processed") == 0, drained_again)

            os.environ["WATHEFNI_HR_INTELLIGENCE_STALE_AFTER_SECONDS"] = "1"
            proj.enqueue(
                cur,
                company_code=COMPANY,
                source_family="workforce",
                entity_type="employee",
                entity_id=f"{EMP}-stale",
                event_ref="test:stale",
                payload={"employee_key": f"{EMP}-stale", "employment_status": "active", "start_date": str(date.today())},
            )
            cur.execute(
                "UPDATE hr_intelligence_projection_outbox SET created_at=now() - interval '2 seconds', next_attempt_at=now() + interval '1 hour' WHERE company_code=%s AND entity_id=%s",
                (COMPANY, f"{EMP}-stale"),
            )
            stale = proj.refresh_family_freshness(cur, COMPANY, "workforce")
            check("pending lag marked stale", stale.get("status") == "stale" and stale.get("guaranteed_current") is False, stale)
            os.environ["WATHEFNI_HR_INTELLIGENCE_STALE_AFTER_SECONDS"] = "180"
            cur.execute(
                "UPDATE hr_intelligence_projection_outbox SET status='done', processed_at=now() WHERE company_code=%s AND entity_id=%s",
                (COMPANY, f"{EMP}-stale"),
            )
            proj.refresh_family_freshness(cur, COMPANY, "workforce")

            fail_item = proj.enqueue(
                cur,
                company_code=COMPANY,
                source_family="workforce",
                entity_type="employee",
                entity_id="missing-retry",
                event_ref="test:retry",
                payload={"employee_key": ""},
            )
            check("retry enqueue", fail_item.get("ok") is True, fail_item)
            # Force a failure by pointing at unsupported family via SQL, then drain retry path.
            cur.execute(
                """
                UPDATE hr_intelligence_projection_outbox
                   SET source_family='workforce', entity_id='retry-missing', payload='{}'::jsonb
                 WHERE company_code=%s AND idempotency_key=%s
                """,
                (COMPANY, fail_item["idempotency_key"]),
            )
            # Simulate apply failure by marking next_attempt and using a monkeypatch.
            original = proj.apply_outbox_item

            def _boom(cur_inner, item):
                if str(item.get("entity_id")) == "retry-missing":
                    return {"ok": False, "error": "injected_failure"}
                return original(cur_inner, item)

            proj.apply_outbox_item = _boom
            retry1 = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            check("retry records failure", retry1.get("failed") >= 1, retry1)
            cur.execute(
                "SELECT status, attempts FROM hr_intelligence_projection_outbox WHERE company_code=%s AND entity_id=%s",
                (COMPANY, "retry-missing"),
            )
            fail_row = dict(cur.fetchone() or {})
            check("retry not dead yet", fail_row.get("status") == "failed" and int(fail_row.get("attempts") or 0) >= 1, fail_row)
            cur.execute(
                "UPDATE hr_intelligence_projection_outbox SET next_attempt_at=now() - interval '1 second' WHERE company_code=%s AND entity_id=%s",
                (COMPANY, "retry-missing"),
            )
            retry2 = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            cur.execute(
                "UPDATE hr_intelligence_projection_outbox SET next_attempt_at=now() - interval '1 second' WHERE company_code=%s AND entity_id=%s",
                (COMPANY, "retry-missing"),
            )
            retry3 = proj.drain_outbox(cur, company_code=COMPANY, limit=50)
            proj.apply_outbox_item = original
            cur.execute(
                "SELECT status, attempts FROM hr_intelligence_projection_outbox WHERE company_code=%s AND entity_id=%s",
                (COMPANY, "retry-missing"),
            )
            dead_row = dict(cur.fetchone() or {})
            check("dead-letter after max attempts", dead_row.get("status") == "dead", dead_row)
            fresh_err = proj.freshness_row(cur, COMPANY, "workforce")
            check("error freshness not guaranteed current", fresh_err.get("guaranteed_current") is not True, fresh_err)

            rebuilt = proj.rebuild_company(cur, COMPANY, family="workforce", reason="test rebuild")
            check("rebuild path ok", rebuilt.get("ok") is True, rebuilt)
            cur.execute(
                "SELECT last_rebuild_at FROM hr_intelligence_source_freshness WHERE company_code=%s AND source_family='workforce'",
                (COMPANY,),
            )
            check("rebuild stamp", bool(dict(cur.fetchone() or {}).get("last_rebuild_at")))

            payload = proj.freshness_payload(cur, COMPANY)
            check("payload no frontend rebuild", payload.get("no_frontend_rebuild") is True, payload)
            check("payroll family unavailable", (payload.get("families") or {}).get("payroll", {}).get("status") == "unavailable", payload)
            check("tenant cursor isolation", proj.freshness_payload(cur, OTHER)["company_code"] == OTHER)

        conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
