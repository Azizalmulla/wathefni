from __future__ import annotations

import argparse
import json

import app
from psycopg2.extras import Json


SMOKE_CONVERSATION_SQL = r"(smoke|cleanup|live-verify|ownership-final|fixture|test)"


def quarantine_smoke_rows(*, dry_run: bool) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT a.app_key, a.phone, a.company_code, pcs.conversation_id
                FROM applications a
                JOIN public_candidate_sessions pcs
                  ON pcs.phone=a.phone
                 AND pcs.company_code=a.company_code
                 AND pcs.selected_position_code=a.position_code
                WHERE a.company_code='WATHEFNI'
                  AND (
                    COALESCE(pcs.data_source, pcs.metadata->>'data_source', '') IN ('smoke_test','test','demo')
                    OR pcs.conversation_id ~* %s
                    OR a.phone LIKE '965555501%%'
                  )
                ORDER BY a.app_key
                """,
                (SMOKE_CONVERSATION_SQL,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            if not dry_run and rows:
                app_keys = [row["app_key"] for row in rows]
                cur.execute(
                    """
                    UPDATE applications
                    SET data_source='smoke_test',
                        data_source_detail=COALESCE(data_source_detail, 'quarantined_by_cleanup_script'),
                        raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                    WHERE app_key = ANY(%s)
                    """,
                    (
                        Json(
                            {
                                "data_source": "smoke_test",
                                "data_source_detail": "quarantined_by_cleanup_script",
                                "quarantined": True,
                            }
                        ),
                        app_keys,
                    ),
                )
                cur.execute(
                    """
                    UPDATE public_candidate_sessions
                    SET data_source='smoke_test',
                        metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                    WHERE phone = ANY(%s)
                      AND company_code='WATHEFNI'
                    """,
                    (Json({"data_source": "smoke_test", "quarantined": True}), [row["phone"] for row in rows]),
                )
                cur.execute(
                    """
                    UPDATE candidates c
                    SET data_source='smoke_test',
                        data_source_detail=COALESCE(data_source_detail, 'quarantined_by_cleanup_script')
                    WHERE phone = ANY(%s)
                      AND NOT EXISTS (
                        SELECT 1
                        FROM applications a
                        WHERE a.phone=c.phone
                          AND COALESCE(a.data_source, a.raw_json->>'data_source', 'production')='production'
                      )
                    """,
                    ([row["phone"] for row in rows],),
                )
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    return {"candidate_applications": rows, "count": len(rows)}


def clean_dirty_emails(*, dry_run: bool) -> dict:
    updates = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone, email FROM candidates WHERE email IS NOT NULL AND email <> '' ORDER BY phone")
            for row in cur.fetchall():
                current = str(row.get("email") or "")
                cleaned = app.clean_extracted_email(current)
                if cleaned and cleaned != current.strip().lower():
                    updates.append({"phone": row.get("phone"), "before": current, "after": cleaned})
                    if not dry_run:
                        cur.execute("UPDATE candidates SET email=%s WHERE phone=%s", (cleaned, row.get("phone")))
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    return {"emails": updates, "count": len(updates)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarantine Wathefni smoke/test data from production dashboard views.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry run.")
    args = parser.parse_args()
    dry_run = not args.apply
    app.ensure_schema()
    result = {
        "dry_run": dry_run,
        "quarantine": quarantine_smoke_rows(dry_run=dry_run),
        "email_cleanup": clean_dirty_emails(dry_run=dry_run),
    }
    print(json.dumps(app.json_safe(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
