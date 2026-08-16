#!/usr/bin/env python3
"""Requisitions Surface Wave — DB prove: queue/detail/SoD/module-off/concurrency."""
from __future__ import annotations

import os
import sys
import uuid
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
    print("    requisitions surfaces — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import requisitions as rq
    import requisitions_surfaces as surfaces

    company = f"RQS{SUFFIX}".upper()
    other = f"RQY{SUFFIX}".upper()
    creator = f"creator-{SUFFIX}"
    approver = f"approver-{SUFFIX}"

    os.environ["WATHEFNI_REQUISITIONS"] = "on"
    os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = company

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rq.ensure_requisitions_schema(cur)
            rq.set_settings(cur, company, enabled=True)
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'requisitions', true, 'surfaces_canary', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
                """,
                (company,),
            )
            created = rq.create_requisition(
                cur,
                company_code=company,
                title_en=f"Surface Req {SUFFIX}",
                title_ar=f"طلب سطحي {SUFFIX}",
                headcount=2,
                department="Ops",
                created_by_user_id=creator,
                submit=True,
                idempotency_key=f"surf-req:{SUFFIX}",
            )
            conn.commit()
            check("create+submit via authority", created.get("ok") is True, created)
            req_id = (created.get("requisition") or {}).get("requisition_id")
            row_version = (created.get("requisition") or {}).get("row_version")

            queue = surfaces.queue_payload(cur, company_code=company, status="attention", limit=20)
            check("queue ok", queue.get("ok") is True, queue)
            check("queue has attention", any(r.get("requisition_id") == req_id for r in (queue.get("requisitions") or [])))
            check("counts.attention", int((queue.get("counts") or {}).get("attention") or 0) >= 1)

            detail = surfaces.detail_payload(
                cur, company_code=company, requisition_id=str(req_id), actor_user_id=approver, actor_role="hr"
            )
            check("detail ok", detail.get("ok") is True, detail)
            check("detail events", len(detail.get("events") or []) >= 1)
            check("explain", "Approval" in (surfaces.explain_status(detail["requisition"]).get("summary_en") or ""))

            # SoD: creator cannot approve
            sod = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=str(req_id),
                to_status="approved",
                actor_user_id=creator,
                expected_row_version=row_version,
            )
            check("SoD blocks creator", sod.get("error") == "self_approval_forbidden", sod)

            approved = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=str(req_id),
                to_status="approved",
                actor_user_id=approver,
                expected_row_version=row_version,
            )
            conn.commit()
            check("approver succeeds", approved.get("ok") is True, approved)
            new_ver = (approved.get("requisition") or {}).get("row_version")

            stale = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=str(req_id),
                to_status="open",
                actor_user_id=approver,
                expected_row_version=row_version,
            )
            check("stale concurrency conflict", stale.get("error") == "concurrency_conflict", stale)

            opened = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=str(req_id),
                to_status="open",
                actor_user_id=approver,
                expected_row_version=new_ver,
            )
            conn.commit()
            check("open succeeds", opened.get("ok") is True, opened)

            # Tenant isolation
            rq.set_settings(cur, other, enabled=True)
            os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = f"{company},{other}"
            leaked = surfaces.queue_payload(cur, company_code=other, status="attention", limit=20)
            check(
                "tenant isolation",
                not any(r.get("requisition_id") == req_id for r in (leaked.get("requisitions") or [])),
            )

            # Module-off
            os.environ["WATHEFNI_REQUISITIONS"] = "off"
            denied = surfaces.queue_payload(cur, company_code=company, status="attention", limit=5)
            check("module-off denied", denied.get("ok") is not True, denied)
            os.environ["WATHEFNI_REQUISITIONS"] = "on"

            # Without pre_hiring — surfaces still work
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'pre_hiring', false, 'surfaces_canary', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=false, updated_at=now()
                """,
                (company,),
            )
            alone = surfaces.queue_payload(cur, company_code=company, status="open", limit=5)
            conn.commit()
            check("works without pre_hiring", alone.get("ok") is True, alone)

        print(f"\n    {PASS} passed, {FAIL} failed")
        if FAIL == 0:
            print("REQUISITIONS_SURFACES_DB_FULL_PASS")
        return 1 if FAIL else 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
