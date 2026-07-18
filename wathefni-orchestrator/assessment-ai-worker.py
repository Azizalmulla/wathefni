#!/usr/bin/env python3
"""Process queued Assessment Product-2 AI runs outside candidate runtime.

The worker refuses production unconditionally, even if its feature flag is
misconfigured.  Run it manually or from a future staging-only service.
"""

from __future__ import annotations

import argparse
import json
import os

# The worker must not inherit the broad web-app credential.  The dedicated
# env file points at the same staging database with a column/table-restricted
# login provisioned by ops/provision-assessment-ai-db-role.py.
AI_DB_ENV = str(os.environ.get("WATHEFNI_ASSESSMENT_AI_POSTGRES_ENV") or "").strip()
if AI_DB_ENV:
    os.environ["WATHEFNI_POSTGRES_ENV"] = AI_DB_ENV

import app
import assessment_ai_service as service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not AI_DB_ENV:
        raise RuntimeError("assessment_ai_worker_requires_dedicated_database_credential")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment == "production" or identity.database_environment == "production":
        raise RuntimeError("assessment_ai_worker_refuses_production")
    service.assert_authoring_enabled(
        environment=identity.application_environment,
        flag_value=os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING"),
    )
    expected_role = str(
        os.environ.get("WATHEFNI_ASSESSMENT_AI_DB_ROLE")
        or "wathefni_assessment_ai_runner"
    ).strip()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user AS current_user")
            actual_role = str(cur.fetchone()["current_user"])
    if actual_role != expected_role:
        raise RuntimeError(
            f"assessment_ai_worker_database_role_mismatch:{actual_role}:{expected_role}"
        )

    run_ids: list[str] = []
    if args.run_id:
        run_ids = [args.run_id]
    else:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text AS run_id
                    FROM assessment_ai_runs
                    WHERE status='queued'
                    ORDER BY queued_at
                    LIMIT %s
                    """,
                    (max(1, min(args.limit, 100)),),
                )
                run_ids = [str(row["run_id"]) for row in cur.fetchall()]

    results = []
    for run_id in run_ids:
        try:
            run = service.process_queued_run(app, run_id)
            results.append({"run_id": run_id, "status": run.get("status")})
        except Exception as exc:
            results.append({"run_id": run_id, "status": "worker_error", "error": f"{type(exc).__name__}: {exc}"})

    payload = {
        "environment": identity.public(),
        "processed": len(results),
        "results": results,
        "production_touched": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 1 if any(row["status"] == "worker_error" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
