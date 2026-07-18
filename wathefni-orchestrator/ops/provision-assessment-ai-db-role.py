#!/usr/bin/env python3
"""Provision the least-privilege Assessment Product-2 worker login.

Staging-only.  This does not enable authoring, start a worker, call a model, or
write an env file.  The generated login cannot update/delete live assessment
or recruiting data.
"""

from __future__ import annotations

import argparse
import os
import re

from psycopg2 import sql

import app


CONFIRM = "staging-assessment-ai-least-privilege-role"
DEFAULT_ROLE = "wathefni_assessment_ai_runner"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--role", default=DEFAULT_ROLE)
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise RuntimeError("assessment_ai_db_role_confirmation_mismatch")
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", args.role):
        raise RuntimeError("assessment_ai_db_role_invalid")
    password = str(os.environ.get("WATHEFNI_ASSESSMENT_AI_DB_PASSWORD") or "")
    if len(password) < 24:
        raise RuntimeError("assessment_ai_db_role_strong_password_required")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("assessment_ai_db_role_provision_refuses_non_staging")
    app.ensure_schema(force=True)

    live_and_recruiting_tables = (
        "assessment_batteries",
        "assessment_content_versions",
        "assessment_attempts",
        "assessment_responses",
        "assessment_scores",
        "assessment_reports",
        "assessment_norms",
        "applications",
        "candidates",
        "interviews",
        "offers",
        "employees",
        "recruiting_stage_events",
        "outbound_delivery_events",
    )
    read_tables = (
        "assessment_ai_model_registry_versions",
        "assessment_prompt_versions",
        "assessment_blueprint_versions",
        "assessment_ai_runs",
        "assessment_item_drafts",
        "assessment_item_draft_revisions",
        "assessment_item_reviews",
        "assessment_translation_pairs",
        "assessment_authoring_events",
        "wathefni_environment_identity",
    )
    insert_tables = (
        "assessment_item_drafts",
        "assessment_item_draft_revisions",
        "assessment_item_reviews",
        "assessment_translation_pairs",
        "assessment_authoring_events",
        "llm_call_logs",
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS database_name")
            database_name = str(cur.fetchone()["database_name"])
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (args.role,))
            exists = bool(cur.fetchone())
            if exists:
                cur.execute(
                    sql.SQL(
                        "ALTER ROLE {} WITH LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOREPLICATION NOINHERIT"
                    ).format(sql.Identifier(args.role)),
                    (password,),
                )
            else:
                cur.execute(
                    sql.SQL(
                        "CREATE ROLE {} WITH LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOREPLICATION NOINHERIT"
                    ).format(sql.Identifier(args.role)),
                    (password,),
                )
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier(args.role),
                )
            )
            cur.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(args.role))
            )
            for table in live_and_recruiting_tables:
                cur.execute("SELECT to_regclass(%s) AS relation", (f"public.{table}",))
                if cur.fetchone().get("relation"):
                    cur.execute(
                        sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(
                            sql.Identifier(table),
                            sql.Identifier(args.role),
                        )
                    )
            for table in read_tables:
                cur.execute(
                    sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
                        sql.Identifier(table),
                        sql.Identifier(args.role),
                    )
                )
            for table in insert_tables:
                cur.execute(
                    sql.SQL("GRANT INSERT ON TABLE {} TO {}").format(
                        sql.Identifier(table),
                        sql.Identifier(args.role),
                    )
                )
            cur.execute(
                sql.SQL(
                    "GRANT SELECT (item_id,battery_key,prompt_text,answer_key) "
                    "ON assessment_items TO {}"
                ).format(sql.Identifier(args.role))
            )
            cur.execute(
                sql.SQL(
                    "GRANT UPDATE (status,output_json,output_sha256,provider_response_model,"
                    "provider_request_id,input_tokens,output_tokens,cached_tokens,"
                    "estimated_cost_usd,latency_ms,attempt_count,refusal_reason,error_code,"
                    "error_message,started_at,completed_at,draft_revision_id,draft_id) "
                    "ON assessment_ai_runs TO {}"
                ).format(sql.Identifier(args.role))
            )
            cur.execute(
                sql.SQL(
                    "GRANT UPDATE (current_revision_id,lifecycle_status,prompt_text,choices,"
                    "proposed_answer_key,proposed_scoring,rationale,explanation,updated_at) "
                    "ON assessment_item_drafts TO {}"
                ).format(sql.Identifier(args.role))
            )
            cur.execute(
                sql.SQL(
                    "GRANT UPDATE (review_run_id,findings_json,status) "
                    "ON assessment_translation_pairs TO {}"
                ).format(sql.Identifier(args.role))
            )
        conn.commit()

    print(
        {
            "environment": identity.public(),
            "role": args.role,
            "authoring_enabled": False,
            "live_table_update_delete": False,
            "recruiting_table_update_delete": False,
            "password_printed": False,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
