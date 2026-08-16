#!/usr/bin/env python3
"""Read-only audit: WATHEFNI applications missing application_job_bindings.

Never INSERT/UPDATE/DELETE. Never enables enforce or cutover.
"""

from __future__ import annotations

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


HELD = {"needs_role", "import_review", "import_archived"}
LIVEISH = {
    "review_pending",
    "awaiting_cv",
    "screening",
    "screening_complete",
    "shortlisted",
    "interview",
    "offer",
    "hired",
    "rejected",
    "withdrawn",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def infer_source_channel(app: dict[str, Any], lifecycle: list[dict[str, Any]]) -> str:
    ds = str(app.get("data_source") or "").strip().lower()
    detail = str(app.get("data_source_detail") or "").strip().lower()
    source_ref = str(app.get("source_ref") or "").strip().lower()
    raw = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
    raw_source = str(raw.get("source") or raw.get("channel") or "").strip().lower()
    channels = [
        str(e.get("channel") or "").strip().lower()
        for e in lifecycle
        if str(e.get("channel") or "").strip()
    ]
    blob = " ".join([ds, detail, source_ref, raw_source, " ".join(channels), str(app.get("app_key") or "")])
    if "whatsapp" in blob or "wa_" in blob:
        return "whatsapp"
    if "email" in blob or "postmark" in blob or "inbound" in blob:
        return "email"
    if "import" in blob or "manual" in blob or "batch" in blob or str(app.get("import_batch_id") or ""):
        return "manual_import"
    if "job" in blob and "apply" in blob:
        return "job_apply"
    if ds in {"whatsapp", "email", "manual_import", "import", "job_apply"}:
        return ds
    if channels:
        return channels[0]
    if ds in {"production", "smoke_test"}:
        # data_source here is environment/label, not intake channel.
        return "legacy_unspecified_channel"
    if ds:
        return f"other:{ds}"
    return "unknown"


def classify(
    *,
    app: dict[str, Any],
    position: dict[str, Any] | None,
    lifecycle: list[dict[str, Any]],
    source_channel: str,
    trust: str,
) -> dict[str, Any]:
    status = str(app.get("status") or "").strip().lower()
    position_code = str(app.get("position_code") or "").strip()
    phone = str(app.get("phone") or "").strip()
    app_key = str(app.get("app_key") or "").strip()

    why = (
        "Application predates Wave 4 application_job_bindings dual-write; "
        "no verified binding row was ever written because the authority did not exist yet "
        "and production-dark has not backfilled."
    )

    if not app_key or not phone:
        return {
            "bucket": "orphaned",
            "safe_to_backfill": False,
            "why_no_binding": why + " Additionally missing app_key/phone identifiers.",
            "notes": "Malformed identity keys.",
        }

    if status in HELD or not position_code:
        return {
            "bucket": "held",
            "safe_to_backfill": False,
            "why_no_binding": why
            + " Record is held/unassigned Talent Pool style and must not receive a Job binding without exact Job confirmation.",
            "notes": f"status={status or 'missing'}; position_code={position_code or 'empty'}",
        }

    if position is None:
        return {
            "bucket": "malformed",
            "safe_to_backfill": False,
            "why_no_binding": why
            + f" position_code={position_code!r} has no matching positions row for WATHEFNI.",
            "notes": "Canonical Job missing.",
        }

    if trust == "untrustworthy":
        return {
            "bucket": "ambiguous",
            "safe_to_backfill": False,
            "why_no_binding": why
            + " Current Job link evidence is inconsistent or weak.",
            "notes": "Requires human review before any backfill.",
        }

    if trust == "ambiguous":
        return {
            "bucket": "ambiguous",
            "safe_to_backfill": False,
            "why_no_binding": why
            + " Job exists but provenance/lifecycle evidence is incomplete.",
            "notes": "Audited backfill only after owner confirmation.",
        }

    ds = str(app.get("data_source") or "").strip().lower()
    detail = str(app.get("data_source_detail") or "").strip().lower()
    if ds == "smoke_test" or "quarantined" in detail:
        return {
            "bucket": "ambiguous",
            "safe_to_backfill": False,
            "why_no_binding": why
            + " Row is smoke_test / quarantine residue, not a production hiring authority record.",
            "notes": "Do not backfill as a real verified Job binding without explicit cleanup/owner decision.",
        }

    # Trustworthy live Job app predating bindings.
    return {
        "bucket": "safe_to_backfill_after_owner_approval",
        "safe_to_backfill": True,
        "why_no_binding": why,
        "notes": (
            f"Legacy live application with canonical Job {position_code}; "
            f"source_channel={source_channel}; lifecycle_events={len(lifecycle)}. "
            "Backfill only with audited consent/provenance — not in this task."
        ),
    }


def assess_job_trust(
    *,
    app: dict[str, Any],
    position: dict[str, Any] | None,
    lifecycle: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(app.get("status") or "").strip().lower()
    position_code = str(app.get("position_code") or "").strip()
    apply_code = str(app.get("apply_code") or "").strip()
    reasons: list[str] = []

    if not position_code:
        return {
            "job_exists_canonically": False,
            "current_job_link_trustworthy": False,
            "trust": "untrustworthy",
            "trust_reasons": ["empty_position_code"],
        }

    if position is None:
        return {
            "job_exists_canonically": False,
            "current_job_link_trustworthy": False,
            "trust": "untrustworthy",
            "trust_reasons": ["position_row_missing"],
        }

    pos_status = str(position.get("status") or "").strip().lower()
    pos_apply = str(position.get("apply_code") or "").strip()
    reasons.append(f"position_status={pos_status or 'unknown'}")

    if apply_code and pos_apply and apply_code != pos_apply:
        reasons.append("apply_code_mismatch_vs_position")
        trust = "ambiguous"
    elif status in HELD:
        reasons.append("held_status")
        trust = "untrustworthy"
    elif any(str(e.get("trigger") or "") in {"explicit_apply", "intake_admit", "convert_job_context"} for e in lifecycle):
        reasons.append("lifecycle_has_job_trigger")
        trust = "trustworthy"
    elif status in LIVEISH and position_code:
        reasons.append("live_status_with_position")
        trust = "trustworthy"
    else:
        reasons.append("limited_provenance")
        trust = "ambiguous"

    title_match = True
    app_title = str(app.get("position_title") or "").strip().lower()
    pos_title = str(position.get("title") or position.get("title_en") or "").strip().lower()
    if app_title and pos_title and app_title not in pos_title and pos_title not in app_title:
        reasons.append("position_title_divergence")
        if trust == "trustworthy":
            trust = "ambiguous"
        title_match = False

    return {
        "job_exists_canonically": True,
        "position_status": pos_status,
        "position_apply_code": pos_apply or None,
        "job_id": str(position.get("job_id") or "") or None,
        "title_match": title_match,
        "current_job_link_trustworthy": trust == "trustworthy",
        "trust": trust,
        "trust_reasons": reasons,
    }


def main() -> int:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(
        os.environ.get(
            "LEGACY_BINDING_AUDIT_OUT",
            f"/opt/wathefni/production-evidence/unified-inbound-cv-legacy-binding-audit/{stamp}",
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    from psycopg2.extras import RealDictCursor
    import psycopg2

    env_path = Path(os.environ["WATHEFNI_POSTGRES_ENV"])
    cfg: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    dsn = cfg.get("WATHEFNI_DATABASE_URL") or ""
    if "wathefni_staging" in dsn or not dsn:
        raise SystemExit("refusing_non_production_dsn")

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db")
            db = (cur.fetchone() or {}).get("db")
            if db != "wathefni":
                raise SystemExit(f"refusing_db:{db}")

            # Ensure we do not create schema; only read if table exists.
            cur.execute(
                "SELECT to_regclass('public.application_job_bindings') IS NOT NULL AS ok"
            )
            if not (cur.fetchone() or {}).get("ok"):
                raise SystemExit("application_job_bindings_missing")

            cur.execute(
                """
                SELECT a.*
                FROM applications a
                WHERE a.company_code = 'WATHEFNI'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM application_job_bindings b
                    WHERE b.company_code = a.company_code
                      AND b.app_key = a.app_key
                      AND COALESCE(b.verified, false) = true
                  )
                ORDER BY a.created_at NULLS LAST, a.app_key
                """
            )
            apps = [dict(r) for r in (cur.fetchall() or [])]

            cur.execute(
                """
                SELECT company_code, position_code, title, title_en, status, apply_code,
                       job_id::text AS job_id, published_at, closed_at, visibility
                FROM positions
                WHERE company_code = 'WATHEFNI'
                """
            )
            positions = {
                str(r["position_code"]): dict(r) for r in (cur.fetchall() or []) if r.get("position_code")
            }

            cur.execute(
                """
                SELECT phone, name, person_id::text AS person_id, active_company_code
                FROM candidates
                WHERE active_company_code = 'WATHEFNI' OR active_company_code IS NULL
                """
            )
            candidates_by_phone = {
                str(r.get("phone") or ""): dict(r) for r in (cur.fetchall() or []) if r.get("phone")
            }

            rows_out: list[dict[str, Any]] = []
            buckets: dict[str, int] = {}
            for app in apps:
                app_key = str(app.get("app_key") or "")
                cur.execute(
                    """
                    SELECT event_id::text, from_stage, to_stage, trigger, actor_type,
                           channel, created_at, metadata
                    FROM application_lifecycle_events
                    WHERE company_code = 'WATHEFNI' AND app_key = %s
                    ORDER BY created_at ASC NULLS LAST
                    """,
                    (app_key,),
                )
                lifecycle = [dict(r) for r in (cur.fetchall() or [])]
                position = positions.get(str(app.get("position_code") or "").strip())
                source_channel = infer_source_channel(app, lifecycle)
                trust = assess_job_trust(app=app, position=position, lifecycle=lifecycle)
                decision = classify(
                    app=app,
                    position=position,
                    lifecycle=lifecycle,
                    source_channel=source_channel,
                    trust=str(trust.get("trust") or "ambiguous"),
                )
                buckets[decision["bucket"]] = buckets.get(decision["bucket"], 0) + 1

                cand = candidates_by_phone.get(str(app.get("phone") or ""))
                first_event = lifecycle[0] if lifecycle else None
                last_event = lifecycle[-1] if lifecycle else None
                created_how = None
                if first_event:
                    created_how = {
                        "from_lifecycle_trigger": first_event.get("trigger"),
                        "from_stage": first_event.get("from_stage"),
                        "to_stage": first_event.get("to_stage"),
                        "channel": first_event.get("channel"),
                        "at": _jsonable(first_event.get("created_at")),
                    }
                elif app.get("import_batch_id"):
                    created_how = {
                        "inferred": "manual_or_bulk_import",
                        "import_batch_id": str(app.get("import_batch_id")),
                        "data_source": app.get("data_source"),
                    }
                else:
                    created_how = {
                        "inferred": "legacy_row_without_lifecycle_event",
                        "data_source": app.get("data_source"),
                        "data_source_detail": app.get("data_source_detail"),
                        "source_ref": app.get("source_ref"),
                    }

                raw = app.get("raw_json") if isinstance(app.get("raw_json"), dict) else {}
                rows_out.append(
                    {
                        "app_key": app_key,
                        "status": app.get("status"),
                        "candidate": {
                            "phone": app.get("phone"),
                            "name": (cand or {}).get("name")
                            or raw.get("candidate_name")
                            or raw.get("name"),
                            "person_id": str(app.get("person_id") or (cand or {}).get("person_id") or "")
                            or None,
                        },
                        "position_code": app.get("position_code"),
                        "position_title": app.get("position_title"),
                        "apply_code": app.get("apply_code"),
                        "job": {
                            "exists_canonically": trust["job_exists_canonically"],
                            "position_row": {
                                "title": (position or {}).get("title") or (position or {}).get("title_en"),
                                "status": (position or {}).get("status"),
                                "apply_code": (position or {}).get("apply_code"),
                                "job_id": (position or {}).get("job_id"),
                            }
                            if position
                            else None,
                            "trust": trust,
                        },
                        "originally_created": {
                            "created_at": _jsonable(app.get("created_at")),
                            "ingested_at": _jsonable(app.get("ingested_at")),
                            "updated_at": _jsonable(app.get("updated_at")),
                            "how": created_how,
                        },
                        "source_channel": source_channel,
                        "data_source": app.get("data_source"),
                        "data_source_detail": app.get("data_source_detail"),
                        "source_ref": app.get("source_ref"),
                        "import_batch_id": str(app.get("import_batch_id") or "") or None,
                        "lifecycle_history": [
                            {
                                "at": _jsonable(e.get("created_at")),
                                "from_stage": e.get("from_stage"),
                                "to_stage": e.get("to_stage"),
                                "trigger": e.get("trigger"),
                                "actor_type": e.get("actor_type"),
                                "channel": e.get("channel"),
                            }
                            for e in lifecycle
                        ],
                        "lifecycle_summary": {
                            "event_count": len(lifecycle),
                            "first": _jsonable(first_event),
                            "last": _jsonable(last_event),
                        },
                        "why_no_verified_binding": decision["why_no_binding"],
                        "classification": decision["bucket"],
                        "safe_to_backfill": decision["safe_to_backfill"],
                        "notes": decision["notes"],
                        "has_application_job_binding": False,
                    }
                )

            cur.execute("SELECT count(*)::int AS n FROM applications WHERE company_code='WATHEFNI'")
            total_apps = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*)::int AS n FROM application_job_bindings
                WHERE company_code='WATHEFNI' AND verified=true
                """
            )
            verified_bindings = int((cur.fetchone() or {}).get("n") or 0)

        payload = {
            "stamp": stamp,
            "database": db,
            "company_code": "WATHEFNI",
            "read_only": True,
            "mutations": 0,
            "total_applications": total_apps,
            "verified_bindings": verified_bindings,
            "missing_verified_bindings": len(rows_out),
            "bucket_counts": buckets,
            "applications": rows_out,
            "conclusion_seed": {
                "all_missing_are_pre_wave4": verified_bindings == 0,
                "real_data_problems": [
                    b
                    for b in ("malformed", "orphaned")
                    if buckets.get(b)
                ],
            },
        }
        (out_dir / "audit.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"ok": True, "out": str(out_dir), "missing": len(rows_out), "buckets": buckets}, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
