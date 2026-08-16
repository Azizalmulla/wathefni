#!/usr/bin/env python3
"""Idempotent production backfill for Assessments Cleanup-1.

Requires explicit --confirm. Refuses staging and any non-production binding.
Does not alter live item prompts, answer keys, scoring rule payloads, or norms;
it only pins attempts to a frozen content snapshot and expires stale opens.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import assessment_lifecycle as lifecycle  # noqa: E402
import assessment_service as service  # noqa: E402


MIGRATION_KEY = "assessments_cleanup1_production_v1"
CONFIRM = "production:wathefni:assessments_cleanup1_v1"


def _json(value: Any) -> Any:
    return app.json_safe(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Must equal {CONFIRM!r}",
    )
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise RuntimeError(f"confirm_mismatch: expected {CONFIRM!r}")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "production" or identity.database_environment != "production":
        raise RuntimeError("assessments_cleanup1_production_migration_refuses_non_production")

    report: dict[str, Any] = {
        "migration": MIGRATION_KEY,
        "confirm": CONFIRM,
        "environment": identity.public(),
        "attempts_seen": 0,
        "attempts_pinned": 0,
        "attempts_expired": 0,
        "responses_backfilled": 0,
        "scores_frozen": 0,
        "reports_frozen": 0,
        "events_added": 0,
        "historical_screening_json_changed": False,
        "item_bank_content_modified": False,
        "scoring_rules_modified": False,
        "norms_modified": False,
    }

    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            lifecycle.ensure_assessment_schema(cur)
            cur.execute(
                """
                SELECT DISTINCT battery_key
                FROM assessment_attempts
                WHERE assessment_version_id IS NULL
                ORDER BY battery_key
                """
            )
            battery_keys = [str(row["battery_key"]) for row in cur.fetchall()]
            versions_by_battery: dict[str, dict[str, Any]] = {}
            for battery_key in battery_keys or [app.ASSESSMENT_BATTERY_KEY]:
                cur.execute(
                    """
                    SELECT * FROM assessment_content_versions
                    WHERE battery_key=%s AND company_code='GLOBAL'
                    ORDER BY content_version DESC, created_at DESC
                    LIMIT 1
                    """,
                    (battery_key,),
                )
                row = cur.fetchone()
                if row:
                    versions_by_battery[battery_key] = dict(row)
                    continue
                cur.execute(
                    "SELECT 1 FROM assessment_batteries WHERE battery_key=%s LIMIT 1",
                    (battery_key,),
                )
                if not cur.fetchone():
                    raise RuntimeError(f"missing_battery_for_historical_attempt:{battery_key}")
                # Snapshot-only freeze: INSERT content version; COALESCE metadata timestamps only.
                versions_by_battery[battery_key] = service.freeze_current_content_version(
                    cur,
                    company_code="GLOBAL",
                    battery_key=battery_key,
                    created_by_user_id=MIGRATION_KEY,
                )

            cur.execute("SELECT * FROM assessment_attempts ORDER BY created_at, attempt_id FOR UPDATE")
            attempts = [dict(row) for row in cur.fetchall()]
            report["attempts_seen"] = len(attempts)
            now = datetime.now(timezone.utc)

            for attempt in attempts:
                attempt_id = str(attempt["attempt_id"])
                company = str(attempt["company_code"]).upper()
                battery_key = str(attempt["battery_key"])
                version = versions_by_battery.get(battery_key)
                if not version:
                    cur.execute(
                        """
                        SELECT * FROM assessment_content_versions
                        WHERE assessment_version_id=%s
                        """,
                        (attempt.get("assessment_version_id"),),
                    )
                    version_row = cur.fetchone()
                    version = dict(version_row) if version_row else None
                if not version:
                    raise RuntimeError(f"missing_content_version_for_attempt:{attempt_id}")

                expires_at = attempt.get("expires_at") or (
                    (attempt.get("created_at") or now) + timedelta(days=lifecycle.DEFAULT_ATTEMPT_TTL_DAYS)
                )
                cur.execute(
                    """
                    UPDATE assessment_attempts
                    SET assessment_version_id=COALESCE(assessment_version_id,%s),
                        expires_at=COALESCE(expires_at,%s),
                        delivery_status=COALESCE(NULLIF(delivery_status,''),'pending'),
                        review_status=COALESCE(NULLIF(review_status,''),'unreviewed')
                    WHERE attempt_id=%s
                    RETURNING *
                    """,
                    (version["assessment_version_id"], expires_at, attempt_id),
                )
                migrated_attempt = dict(cur.fetchone())
                if not attempt.get("assessment_version_id"):
                    report["attempts_pinned"] += 1

                if migrated_attempt.get("status") in lifecycle.OPEN_ATTEMPT_STATUSES and expires_at <= now:
                    cur.execute(
                        """
                        UPDATE assessment_attempts
                        SET status='expired', expired_at=COALESCE(expired_at,now()), updated_at=now()
                        WHERE attempt_id=%s AND status IN ('pending','in_progress')
                        RETURNING *
                        """,
                        (attempt_id,),
                    )
                    if cur.fetchone():
                        report["attempts_expired"] += 1
                        lifecycle.revoke_active_tokens(
                            cur,
                            attempt_id=attempt_id,
                            company_code=company,
                            reason="historical_attempt_expired",
                        )
                        lifecycle.record_event(
                            cur,
                            attempt_id=attempt_id,
                            company_code=company,
                            event_type="expired",
                            actor_type="migration",
                            from_status=str(migrated_attempt.get("status")),
                            to_status="expired",
                            payload={"migration": MIGRATION_KEY},
                        )
                        report["events_added"] += 1

                item_map = {
                    str(item.get("item_id")): item
                    for item in service.version_items(version)
                }
                cur.execute(
                    "SELECT * FROM assessment_responses WHERE attempt_id=%s ORDER BY item_order",
                    (attempt_id,),
                )
                for response in cur.fetchall():
                    item = item_map.get(str(response.get("item_id"))) or {}
                    scoring_snapshot = response.get("scoring_snapshot")
                    needs_backfill = (
                        not response.get("company_code")
                        or not response.get("assessment_version_id")
                        or response.get("item_content_version") is None
                        or (
                            item.get("answer_key") is not None
                            and response.get("answer_key_snapshot") is None
                        )
                        or not isinstance(scoring_snapshot, dict)
                        or not scoring_snapshot
                    )
                    if not needs_backfill:
                        continue
                    cur.execute(
                        """
                        UPDATE assessment_responses
                        SET company_code=COALESCE(company_code,%s),
                            assessment_version_id=COALESCE(assessment_version_id,%s),
                            item_content_version=COALESCE(item_content_version,%s),
                            answer_key_snapshot=COALESCE(answer_key_snapshot,%s),
                            scoring_snapshot=CASE
                              WHEN scoring_snapshot='{}'::jsonb THEN %s
                              ELSE scoring_snapshot
                            END
                        WHERE response_id=%s
                        """,
                        (
                            company,
                            version["assessment_version_id"],
                            int(item.get("content_version") or version.get("content_version") or 1),
                            item.get("answer_key"),
                            app.Json(_json(item.get("scoring") or {})),
                            response["response_id"],
                        ),
                    )
                    report["responses_backfilled"] += cur.rowcount

                cur.execute(
                    """
                    UPDATE assessment_scores
                    SET assessment_version_id=COALESCE(assessment_version_id,%s), immutable=TRUE
                    WHERE attempt_id=%s AND immutable IS NOT TRUE
                    """,
                    (version["assessment_version_id"], attempt_id),
                )
                report["scores_frozen"] += cur.rowcount
                cur.execute(
                    """
                    UPDATE assessment_reports
                    SET assessment_version_id=COALESCE(assessment_version_id,%s), immutable=TRUE
                    WHERE attempt_id=%s AND immutable IS NOT TRUE
                    """,
                    (version["assessment_version_id"], attempt_id),
                )
                report["reports_frozen"] += cur.rowcount

                cur.execute(
                    """
                    SELECT 1 FROM assessment_events
                    WHERE attempt_id=%s AND event_type='snapshot_updated'
                      AND payload_json->>'migration'=%s
                    LIMIT 1
                    """,
                    (attempt_id, MIGRATION_KEY),
                )
                if not cur.fetchone():
                    lifecycle.record_event(
                        cur,
                        attempt_id=attempt_id,
                        company_code=company,
                        event_type="snapshot_updated",
                        actor_type="migration",
                        payload={
                            "migration": MIGRATION_KEY,
                            "assessment_version_id": str(version["assessment_version_id"]),
                            "historical_screening_json_changed": False,
                        },
                    )
                    report["events_added"] += 1

            cur.execute("ALTER TABLE assessment_attempts VALIDATE CONSTRAINT assessment_attempts_status_check")
            cur.execute("ALTER TABLE assessment_attempts VALIDATE CONSTRAINT assessment_attempts_delivery_status_check")
            cur.execute("ALTER TABLE assessment_attempts VALIDATE CONSTRAINT assessment_attempts_review_status_check")
        conn.commit()

    print(json.dumps(_json(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
