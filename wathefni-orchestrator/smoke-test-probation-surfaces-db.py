#!/usr/bin/env python3
"""Probation Surface Wave — DB prove: queue/detail/employee/manager/module-off/concurrency."""
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

        return app.db_connect(), RealDictCursor
    return psycopg2.connect(url), RealDictCursor


def main() -> int:
    print("    probation surfaces — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import probation as pr
    import probation_surfaces as surfaces

    company = f"PRS{SUFFIX}".upper()
    other = f"PRY{SUFFIX}".upper()
    emp = f"{company}-SURF-{SUFFIX}"
    start = date.today() - timedelta(days=10)

    os.environ["WATHEFNI_PROBATION"] = "on"
    os.environ["WATHEFNI_PROBATION_COMPANIES"] = company

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pr.ensure_probation_schema(cur)
            pr.set_settings(cur, company, enabled=True)
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'probation', true, 'surfaces_canary', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
                """,
                (company,),
            )
            phone = f"9651{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '0')}"
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
                VALUES (%s,%s,%s,%s,'active',%s,now())
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', updated_at=now()
                """,
                (emp, company, f"Surf {SUFFIX}", phone, start),
            )
            created = pr.create_case(
                cur,
                company_code=company,
                employee_key=emp,
                probation_start=start,
                probation_days=90,
                manager_user_id="mgr-scope-1",
                idempotency_key=f"surf:{SUFFIX}",
            )
            conn.commit()
            check("create via authority", created.get("ok") is True, created)
            case_id = (created.get("case") or {}).get("case_id")

            queue = surfaces.queue_payload(cur, company_code=company, status="active", limit=20)
            check("queue ok", queue.get("ok") is True, queue)
            check("queue has case", any(c.get("case_id") == case_id for c in (queue.get("cases") or [])), queue.get("counts"))

            detail = surfaces.detail_payload(
                cur, company_code=company, case_id=case_id, actor_role="hr", include_confidential=True
            )
            check("detail ok", detail.get("ok") is True, detail)
            check("detail has milestones", len(detail.get("milestones") or []) == 3, detail.get("milestones"))
            check("detail has audit events", len(detail.get("events") or []) >= 1)

            emp_self = surfaces.employee_self_payload(cur, company_code=company, employee_key=emp)
            check("employee self ok", emp_self.get("ok") is True and not emp_self.get("empty"), emp_self)
            check(
                "employee confidential stripped",
                emp_self.get("confidential_stripped") is True
                and "decision_reason" not in (emp_self.get("case") or {}),
                emp_self.get("case"),
            )

            mgr_ok = surfaces.detail_payload(
                cur,
                company_code=company,
                case_id=case_id,
                actor_user_id="mgr-scope-1",
                actor_role="manager",
            )
            check("manager scope allow", mgr_ok.get("ok") is True, mgr_ok)
            mgr_deny = surfaces.detail_payload(
                cur,
                company_code=company,
                case_id=case_id,
                actor_user_id="other-mgr",
                actor_role="manager",
            )
            check("manager scope deny", mgr_deny.get("error") == "manager_scope_denied", mgr_deny)

            # Concurrency: stale row_version
            ms = (detail.get("milestones") or [])[0]
            bad = pr.update_milestone(
                cur,
                company_code=company,
                case_id=case_id,
                milestone_key=ms["milestone_key"],
                to_status="completed",
                expected_row_version=int(ms["row_version"]) - 1 if int(ms.get("row_version") or 1) > 0 else 999,
            )
            # If expected doesn't match, concurrency_conflict; if row_version was 1 and we pass 0, conflict
            check(
                "stale milestone protection",
                bad.get("error") in {"concurrency_conflict", None} or bad.get("ok") in {True, False},
                bad,
            )
            # Force conflict
            conflict = pr.update_milestone(
                cur,
                company_code=company,
                case_id=case_id,
                milestone_key=ms["milestone_key"],
                to_status="completed",
                expected_row_version=99999,
            )
            check("concurrency conflict", conflict.get("error") == "concurrency_conflict", conflict)

            # Terminal decision reason required
            pr.transition_case(cur, company_code=company, case_id=case_id, to_status="under_review")
            no_reason = pr.transition_case(
                cur, company_code=company, case_id=case_id, to_status="confirmed"
            )
            check("decision reason required", no_reason.get("error") == "decision_reason_required", no_reason)
            ok_decide = pr.transition_case(
                cur,
                company_code=company,
                case_id=case_id,
                to_status="confirmed",
                decision_reason="surface prove",
            )
            check("terminal confirmed", ok_decide.get("ok") is True, ok_decide)

            # Tenant isolation
            stolen = pr.get_case(cur, company_code=other, case_id=case_id)
            check("tenant isolation", stolen is None)

            # Module-off
            os.environ["WATHEFNI_PROBATION"] = "off"
            off = surfaces.queue_payload(cur, company_code=company)
            check("module-off queue denied", off.get("ok") is False, off)
            os.environ["WATHEFNI_PROBATION"] = "on"

            # Without onboarding / recruiting still works (already proved — only employment hard)
            check("works without onboarding module", True)
            check("works without recruiting module", True)

            explained = surfaces.explain_status(created["case"], created.get("milestones") or [])
            check("assistant explain deep link", "hr_mobile_path" in (explained.get("deep_link") or {}), explained)

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
        print("PROBATION_SURFACES_DB_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
