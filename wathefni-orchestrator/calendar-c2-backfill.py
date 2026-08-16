#!/usr/bin/env python3
"""Calendar C2 — idempotent backfill of live interviews into native Calendar.

Modes:
  --dry-run     Print planned actions without writing
  --company X   Tenant scope (required for non-dry production safety unless --all-tenants)
  --limit N     Batch size
  --cursor ISO  Resume after scheduled_start
  --process     Also drain outbox after enqueue (module must be enabled for apply)

Does not enable the calendar module. Does not invent async deadlines.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill live interviews into Wathefni Calendar.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--company", default=None)
    parser.add_argument("--all-tenants", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--cursor", default=None, help="Resume: only interviews with scheduled_start > cursor ISO")
    parser.add_argument("--process", action="store_true", help="Run outbox worker after enqueue")
    parser.add_argument("--enable-module", action="store_true", help="Enable calendar module for --company (evidence only)")
    args = parser.parse_args()

    import app
    import calendar_outbox
    import calendar_interview_link as cil
    import interview_lifecycle as life

    app.assert_runtime_environment_binding()

    if not args.company and not args.all_tenants and not args.dry_run:
        print(json.dumps({"ok": False, "error": "company_or_all_tenants_required"}))
        return 2

    company = (args.company or "").strip().upper() or None
    planned = 0
    enqueued = 0
    skipped = 0
    errors: list[dict] = []
    next_cursor = None

    if args.enable_module and company and not args.dry_run:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                    VALUES (%s,'calendar',true,now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET enabled=true, updated_at=now()
                    """,
                    (company,),
                )
            conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            params: list = []
            where = [
                "lower(COALESCE(interview_type,'live')) <> 'async_video'",
                "scheduled_start IS NOT NULL",
                "scheduled_end IS NOT NULL",
                "lower(COALESCE(status,'')) IN ('scheduled','rescheduled','completed','cancelled','no_show')",
            ]
            if company:
                where.append("company_code=%s")
                params.append(company)
            if args.cursor:
                where.append("scheduled_start > %s::timestamptz")
                params.append(args.cursor)
            params.append(max(1, min(int(args.limit), 500)))
            cur.execute(
                f"""
                SELECT *
                FROM candidate_interviews
                WHERE {' AND '.join(where)}
                ORDER BY scheduled_start ASC, interview_id ASC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall() or []]

            for row in rows:
                next_cursor = str(row.get("scheduled_start"))
                if not cil.is_live_timed_interview(row):
                    skipped += 1
                    continue
                planned += 1
                assignments = life.list_assignments(cur, str(row["interview_id"]))
                status = str(row.get("status") or "").lower()
                if status in {"cancelled", "no_show"}:
                    op = "cancel"
                elif status == "completed":
                    op = "ensure"  # ensure then complete via second intent if needed
                else:
                    op = "ensure"
                token = f"backfill:{row['interview_id']}:{row.get('schedule_operation_id') or row.get('updated_at') or 'v1'}"
                if args.dry_run:
                    continue
                try:
                    result = calendar_outbox.enqueue_from_interview(
                        cur,
                        app,
                        interview=row,
                        assignments=assignments,
                        operation=op,
                        operation_token=token,
                    )
                    if result.get("ok"):
                        enqueued += 1
                        if status == "completed":
                            calendar_outbox.enqueue_from_interview(
                                cur,
                                app,
                                interview=row,
                                assignments=assignments,
                                operation="complete",
                                operation_token=f"{token}:complete",
                            )
                    else:
                        errors.append({"interview_id": str(row["interview_id"]), "error": result})
                except Exception as exc:
                    errors.append({"interview_id": str(row["interview_id"]), "error": str(exc)[:300]})
        if not args.dry_run:
            conn.commit()
        else:
            conn.rollback()

    process_result = None
    if args.process and not args.dry_run:
        process_result = calendar_outbox.run_outbox_once(app, limit=max(enqueued, 1) * 2, company_code=company)

    out = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "company": company,
        "planned": planned,
        "enqueued": enqueued if not args.dry_run else 0,
        "would_enqueue": planned if args.dry_run else None,
        "skipped": skipped,
        "errors": errors,
        "next_cursor": next_cursor,
        "process": process_result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
