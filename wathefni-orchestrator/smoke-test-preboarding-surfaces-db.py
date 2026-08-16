#!/usr/bin/env python3
"""Preboarding surfaces DB prove — queue/detail/employee/manager/module-off on staging."""
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
    print("    preboarding surfaces — DB queue/detail/employee/manager")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    import preboarding as pb
    import preboarding_surfaces as surfaces

    company = f"PBS{SUFFIX}".upper()
    emp = f"{company}-J-{SUFFIX}"
    joining = date.today() + timedelta(days=10)
    os.environ["WATHEFNI_PREBOARDING"] = "on"
    os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = company

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pb.ensure_preboarding_schema(cur)
            pb.set_settings(cur, company, enabled=True)
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s,'preboarding',true,'surface_canary','{}'::jsonb,now())
                ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                """,
                (company,),
            )
            pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp,
                name=f"Surface Joiner {SUFFIX}",
                joining_date=joining,
                phone=f"9655{SUFFIX[:7]}",
            )
            created = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp,
                joining_date=joining,
                manager_user_id="mgr-surface",
                created_by_user_id="u-hr",
                idempotency_key=f"surf-{SUFFIX}",
                seed_tasks=False,
                apply_handoff=False,
            )
            check("create for surface", created.get("ok") is True, created)
            aid = created["assignment"]["assignment_id"]
            conn.commit()

            queue = surfaces.queue_payload(cur, company_code=company, hub_lookup=None)
            check("queue ok", queue.get("ok") is True, queue)
            check("queue has assignment", any(a["assignment_id"] == aid for a in queue.get("assignments") or []))
            check("queue marks joining", any(a.get("is_joining") for a in queue.get("assignments") or []))

            mgr_q = surfaces.queue_payload(
                cur,
                company_code=company,
                manager_scope_only=True,
                actor_user_id="mgr-surface",
            )
            check("manager sees assigned", any(a["assignment_id"] == aid for a in mgr_q.get("assignments") or []))
            mgr_other = surfaces.queue_payload(
                cur,
                company_code=company,
                manager_scope_only=True,
                actor_user_id="mgr-other",
            )
            check(
                "other manager empty",
                not any(a["assignment_id"] == aid for a in mgr_other.get("assignments") or []),
            )

            detail = surfaces.detail_payload(
                cur,
                company_code=company,
                assignment_id=aid,
                actor_user_id="u-hr",
                actor_role="hr",
                hub_employee={"employment_status": "pending_start", "name": "Joiner"},
            )
            check("detail ok", detail.get("ok") is True, detail)
            check("detail items", len(detail.get("items") or []) >= 5)
            check("detail events", isinstance(detail.get("events"), list))
            explained = surfaces.explain_blockers(detail["assignment"], detail["items"])
            check("assistant explain", "deep_link" in explained and explained["deep_link"].get("web_page") == "preboarding")

            emp_payload = surfaces.employee_self_payload(
                cur,
                company_code=company,
                employee_key=emp,
                hub_employee={"employment_status": "pending_start", "name": "Joiner"},
            )
            check("employee payload", emp_payload.get("ok") is True and emp_payload.get("preboarding_only") is True)
            check(
                "employee only owns employee items",
                all(i.get("owner_role") == "employee" for i in emp_payload.get("items") or []),
            )

            pb.set_settings(cur, company, enabled=False)
            cur.execute(
                "UPDATE company_modules SET enabled=false WHERE company_code=%s AND module_key='preboarding'",
                (company,),
            )
            off = surfaces.queue_payload(cur, company_code=company)
            check(
                "module-off queue denied",
                off.get("ok") is False and off.get("error") == "preboarding_company_disabled",
                off,
            )
            conn.commit()

        print(f"\n{PASS} passed, {FAIL} failed")
        if FAIL:
            print("PREBOARDING_SURFACES_DB_FAIL")
            return 1
        print("PREBOARDING_SURFACES_DB_FULL_PASS")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
