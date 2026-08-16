#!/usr/bin/env python3
"""Wave 1 tenant ownership migration for outbound_delivery_events.

Classifies null company_code rows, backfills only when applications.app_key maps
to exactly one company_code, and quarantines ambiguous/orphaned rows (payload
stamp only — company_code stays NULL so they never match a strict tenant
predicate).

Default is dry-run (audit only). Apply with --apply against an explicit DB.
NEVER point --apply at production unless an operator deliberately does so.

Authoritative ownership source: applications (company_code) via subject_key=app_key.
Heuristics (subject_key embeds WATHEFNI, account_id==company) are reported as
signals only and never silently assigned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLASS_BACKFILL = "backfill_unambiguous_application"
CLASS_AMBIGUOUS = "quarantine_ambiguous_multi_tenant"
CLASS_ORPHAN = "quarantine_orphan_no_application"

QUARANTINE_PAYLOAD_KEY = "tenant_ownership"


def classify_null_company_event(
    *,
    delivery_id: str,
    subject_key: str | None,
    app_companies: list[str],
) -> dict[str, Any]:
    """Classify one null-company delivery event.

    app_companies: distinct applications.company_code values for subject_key.
    """
    companies = sorted({str(c).strip().upper() for c in app_companies if str(c or "").strip()})
    if len(companies) == 1:
        return {
            "delivery_id": delivery_id,
            "subject_key": subject_key,
            "class": CLASS_BACKFILL,
            "owner_company_code": companies[0],
            "app_companies": companies,
        }
    if len(companies) > 1:
        return {
            "delivery_id": delivery_id,
            "subject_key": subject_key,
            "class": CLASS_AMBIGUOUS,
            "owner_company_code": None,
            "app_companies": companies,
            "reason": "subject_key_maps_to_multiple_companies",
        }
    return {
        "delivery_id": delivery_id,
        "subject_key": subject_key,
        "class": CLASS_ORPHAN,
        "owner_company_code": None,
        "app_companies": [],
        "reason": "no_application_for_subject_key",
    }


def quarantine_payload_patch(*, reason: str, signals: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        QUARANTINE_PAYLOAD_KEY: {
            "status": "quarantined",
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
            "wave": "follow_up_tenant_strict_wave1",
            "signals": signals or {},
        }
    }


def backfill_payload_patch(*, owner: str) -> dict[str, Any]:
    return {
        QUARANTINE_PAYLOAD_KEY: {
            "status": "backfilled",
            "owner_company_code": owner,
            "authority": "applications.app_key_unique_company",
            "at": datetime.now(timezone.utc).isoformat(),
            "wave": "follow_up_tenant_strict_wave1",
        }
    }


def audit_null_company_events(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          ode.delivery_id,
          ode.subject_key,
          ode.subject_type,
          ode.status,
          ode.last_error,
          ode.recovered_at,
          ode.account_id,
          ode.channel,
          ode.created_at,
          ode.payload,
          COALESCE(
            (
              SELECT array_agg(DISTINCT a.company_code ORDER BY a.company_code)
              FROM applications a
              WHERE a.app_key = ode.subject_key
            ),
            ARRAY[]::text[]
          ) AS app_companies,
          EXISTS (
            SELECT 1 FROM companies c WHERE c.company_code = ode.account_id
          ) AS account_id_is_company,
          NULLIF(ode.payload->>'company_code', '') AS payload_company_code
        FROM outbound_delivery_events ode
        WHERE ode.company_code IS NULL
        ORDER BY ode.created_at ASC, ode.delivery_id ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    classified: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    followup_counts: Counter[str] = Counter()

    for row in rows:
        companies = list(row.get("app_companies") or [])
        item = classify_null_company_event(
            delivery_id=row["delivery_id"],
            subject_key=row.get("subject_key"),
            app_companies=companies,
        )
        item.update(
            {
                "status": row.get("status"),
                "last_error": row.get("last_error"),
                "account_id": row.get("account_id"),
                "channel": row.get("channel"),
                "created_at": row.get("created_at"),
                "signals": {
                    "account_id_is_company": bool(row.get("account_id_is_company")),
                    "payload_company_code": row.get("payload_company_code"),
                },
            }
        )
        # Heuristic signals only — never used for ownership assignment.
        sk = str(row.get("subject_key") or "")
        if "WATHEFNI" in sk.upper():
            item["signals"]["subject_key_embeds_wathefni"] = True
        counts[item["class"]] += 1
        is_followup = (
            str(row.get("status") or "") not in {"sent", "recovered"}
            and row.get("recovered_at") is None
            and (row.get("status") == "failed" or row.get("last_error") is not None)
        )
        item["follow_up_relevant"] = is_followup
        if is_followup:
            followup_counts[item["class"]] += 1
        classified.append(item)

    return {
        "null_total": len(rows),
        "class_counts": dict(counts),
        "follow_up_class_counts": dict(followup_counts),
        "rows": classified,
        "backfill_ids": [r["delivery_id"] for r in classified if r["class"] == CLASS_BACKFILL],
        "ambiguous_ids": [r["delivery_id"] for r in classified if r["class"] == CLASS_AMBIGUOUS],
        "orphan_ids": [r["delivery_id"] for r in classified if r["class"] == CLASS_ORPHAN],
    }


def apply_migration(cur: Any, audit: dict[str, Any]) -> dict[str, Any]:
    """Apply backfill + quarantine stamps. Caller owns the transaction."""
    applied = {"backfilled": 0, "quarantined": 0}
    by_id = {r["delivery_id"]: r for r in audit["rows"]}

    for delivery_id in audit["backfill_ids"]:
        row = by_id[delivery_id]
        owner = row["owner_company_code"]
        patch = backfill_payload_patch(owner=owner)
        cur.execute(
            """
            UPDATE outbound_delivery_events
               SET company_code = %s,
                   payload = COALESCE(payload, '{}'::jsonb) || %s::jsonb,
                   updated_at = now()
             WHERE delivery_id = %s
               AND company_code IS NULL
            """,
            (owner, json.dumps(patch), delivery_id),
        )
        applied["backfilled"] += cur.rowcount

    for delivery_id in audit["ambiguous_ids"] + audit["orphan_ids"]:
        row = by_id[delivery_id]
        patch = quarantine_payload_patch(
            reason=row.get("reason") or row["class"],
            signals=row.get("signals") or {},
        )
        cur.execute(
            """
            UPDATE outbound_delivery_events
               SET payload = COALESCE(payload, '{}'::jsonb) || %s::jsonb,
                   updated_at = now()
             WHERE delivery_id = %s
               AND company_code IS NULL
            """,
            (json.dumps(patch), delivery_id),
        )
        applied["quarantined"] += cur.rowcount

    return applied


def prove_strict_wathefni(cur: Any) -> dict[str, Any]:
    """After migration (or simulated), strict follow-up counts for WATHEFNI."""
    # Import locally so unit/sqlite callers can skip.
    import prehire_overview as po  # noqa: WPS433

    reviewable = po.reviewable_predicate("a")
    person = po.person_identity_sql("a", "c")
    strict = """
        EXISTS (
          SELECT 1
          FROM outbound_delivery_events ode
          WHERE ode.subject_key=a.app_key
            AND ode.company_code=a.company_code
            AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
            AND ode.recovered_at IS NULL
            AND (ode.status='failed' OR ode.last_error IS NOT NULL)
        )
    """
    cur.execute(
        f"""
        SELECT
          COUNT(*) FILTER (WHERE {strict}) AS apps,
          COUNT(DISTINCT CASE WHEN {strict} THEN {person} END) AS people,
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM outbound_delivery_events ode
              WHERE ode.subject_key=a.app_key
                AND ode.company_code IS NULL
                AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
                AND ode.recovered_at IS NULL
                AND (ode.status='failed' OR ode.last_error IS NOT NULL)
            )
          ) AS apps_with_null_followup_events
        FROM applications a
        LEFT JOIN candidates c ON c.phone=a.phone
        WHERE a.company_code='WATHEFNI' AND {reviewable}
        """
    )
    return dict(cur.fetchone() or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write backfill/quarantine (default: dry-run)")
    parser.add_argument("--out", type=Path, help="Write audit JSON to this path")
    parser.add_argument("--ack-db", default="", help="Must match WATHEFNI_EXPECTED_DATABASE_NAME when --apply")
    args = parser.parse_args(argv)

    # Late import so classify helpers can be unit-tested without app/DB.
    import app  # noqa: WPS433

    expected = str(os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "").strip()
    if args.apply:
        if not expected or args.ack_db != expected:
            print(
                f"REFUSING --apply: pass --ack-db={expected or '<WATHEFNI_EXPECTED_DATABASE_NAME>'} "
                "matching the bound database name",
                file=sys.stderr,
            )
            return 2

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            audit = audit_null_company_events(cur)
            result = {
                "mode": "apply" if args.apply else "dry_run",
                "database": expected or "unknown",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "null_total": audit["null_total"],
                "class_counts": audit["class_counts"],
                "follow_up_class_counts": audit["follow_up_class_counts"],
                "backfill_count": len(audit["backfill_ids"]),
                "ambiguous_count": len(audit["ambiguous_ids"]),
                "orphan_count": len(audit["orphan_ids"]),
                "backfill_sample": [
                    {k: r[k] for k in ("delivery_id", "subject_key", "owner_company_code", "follow_up_relevant")}
                    for r in audit["rows"]
                    if r["class"] == CLASS_BACKFILL
                ][:40],
                "ambiguous_rows": [r for r in audit["rows"] if r["class"] == CLASS_AMBIGUOUS],
                "orphan_follow_up_sample": [
                    {k: r[k] for k in ("delivery_id", "subject_key", "status", "last_error", "signals")}
                    for r in audit["rows"]
                    if r["class"] == CLASS_ORPHAN and r.get("follow_up_relevant")
                ][:40],
            }

            if args.apply:
                applied = apply_migration(cur, audit)
                conn.commit()
                result["applied"] = applied
                result["wathefni_strict_after"] = prove_strict_wathefni(cur)
            else:
                # Simulate backfill in a CTE for WATHEFNI proof without writing.
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM outbound_delivery_events
                    WHERE company_code IS NULL
                      AND subject_key IN (
                        SELECT app_key FROM applications
                        GROUP BY app_key HAVING COUNT(DISTINCT company_code)=1
                      )
                    """
                )
                result["simulated_backfill_eligible"] = int((cur.fetchone() or {}).get("n") or 0)
                # Simulated strict counts
                import prehire_overview as po

                reviewable = po.reviewable_predicate("a")
                person = po.person_identity_sql("a", "c")
                cur.execute(
                    f"""
                    WITH owners AS (
                      SELECT ode.delivery_id, MIN(a.company_code) AS company_code
                      FROM outbound_delivery_events ode
                      JOIN applications a ON a.app_key = ode.subject_key
                      WHERE ode.company_code IS NULL
                      GROUP BY ode.delivery_id
                      HAVING COUNT(DISTINCT a.company_code) = 1
                    ),
                    simulated AS (
                      SELECT ode.subject_key,
                             COALESCE(ode.company_code, o.company_code) AS company_code,
                             ode.status, ode.last_error, ode.recovered_at
                      FROM outbound_delivery_events ode
                      LEFT JOIN owners o ON o.delivery_id = ode.delivery_id
                    )
                    SELECT
                      COUNT(*) FILTER (
                        WHERE EXISTS (
                          SELECT 1 FROM simulated ode
                          WHERE ode.subject_key=a.app_key
                            AND ode.company_code=a.company_code
                            AND COALESCE(ode.status,'') NOT IN ('sent','recovered')
                            AND ode.recovered_at IS NULL
                            AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                        )
                      ) AS apps,
                      COUNT(DISTINCT CASE WHEN EXISTS (
                          SELECT 1 FROM simulated ode
                          WHERE ode.subject_key=a.app_key
                            AND ode.company_code=a.company_code
                            AND COALESCE(ode.status,'') NOT IN ('sent','recovered')
                            AND ode.recovered_at IS NULL
                            AND (ode.status='failed' OR ode.last_error IS NOT NULL)
                        ) THEN {person} END) AS people
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    WHERE a.company_code='WATHEFNI' AND {reviewable}
                    """
                )
                result["wathefni_strict_after_simulated_backfill"] = dict(cur.fetchone() or {})

    text = json.dumps(result, default=str, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
