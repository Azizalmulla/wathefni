#!/usr/bin/env python3
"""Restore the Candidate profile redesign canary to general-candidate state.

Target: imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT
- Was promoted to J2P2_PROD_TEST / ready_for_review during profile redesign proof.
- Restore to needs_role with cleared position while preserving CV/identity/audit.

Safe: only mutates the single app_key when it still carries J2P2_PROD_TEST
position and/or a stale intake-admit lifecycle event for that job.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from datetime import datetime, timezone


def main() -> int:
    pid = os.environ.get("PROOF_PID") or ""
    if not pid:
        print("PROOF_PID required", file=sys.stderr)
        return 2
    for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ[k.decode()] = v.decode(errors="replace")

    import app

    evidence = os.environ.get("PROOF_EVID") or "/tmp/candidate-profile-canary-cleanup"
    pathlib.Path(evidence).mkdir(parents=True, exist_ok=True)
    app_key = "imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT"
    company = "WATHEFNI"
    test_job = "J2P2_PROD_TEST"
    now = datetime.now(timezone.utc).isoformat()
    stale_idem = f"intake-admit:{company}:{app_key}:{test_job}"

    before = {}
    after = {}
    unrelated_before = {}
    unrelated_after = {}
    events_superseded = 0
    bindings_updated = 0

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key, status, position_code, position_title, phone, person_id, membership_id,
                       raw_json, updated_at
                FROM applications
                WHERE company_code=%s AND app_key=%s
                FOR UPDATE
                """,
                (company, app_key),
            )
            row = cur.fetchone()
            if not row:
                print(json.dumps({"ok": False, "error": "application_not_found"}))
                return 1
            before = dict(row)

            cur.execute(
                """
                SELECT event_id, from_stage, to_stage, trigger, idempotency_key, created_at
                FROM application_lifecycle_events
                WHERE company_code=%s AND app_key=%s
                  AND (
                    idempotency_key=%s
                    OR (trigger='intake_admit' AND coalesce(metadata->>'position_code','')=%s)
                  )
                ORDER BY created_at DESC
                """,
                (company, app_key, stale_idem, test_job),
            )
            stale_events = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT app_key, status, position_code
                FROM applications
                WHERE company_code=%s AND app_key <> %s
                  AND (
                    position_code=%s
                    OR app_key LIKE 'imp-wathefni-%%'
                  )
                ORDER BY app_key
                """,
                (company, app_key, test_job),
            )
            unrelated_before = [dict(r) for r in cur.fetchall()]

            status = str(before.get("status") or "")
            position = str(before.get("position_code") or "").strip()
            needs_restore = (
                position == test_job
                or status == "ready_for_review"
                or bool(stale_events)
            )
            if not needs_restore:
                payload = {
                    "ok": True,
                    "skipped": True,
                    "reason": "already_general_candidate",
                    "before": {
                        "app_key": app_key,
                        "status": status,
                        "position_code": position,
                    },
                }
                pathlib.Path(f"{evidence}/canary-cleanup.json").write_text(
                    json.dumps(payload, default=str, indent=2)
                )
                print(json.dumps(payload, default=str, indent=2))
                return 0

            raw = before.get("raw_json") if isinstance(before.get("raw_json"), dict) else {}
            raw = dict(raw)
            import_meta = raw.get("import") if isinstance(raw.get("import"), dict) else {}
            import_meta = dict(import_meta)
            import_meta.update(
                {
                    "needs_role": True,
                    "promoted": False,
                    "unpromoted_at": now,
                    "unpromoted_reason": "candidate_profile_redesign_canary_cleanup",
                    "previous_position_code": position or test_job,
                    "previous_status": status,
                }
            )
            raw["import"] = import_meta

            # Status/current_step writes require the canonical lifecycle session flag.
            cur.execute("SELECT set_config('wathefni.lifecycle_authority', 'canonical', true)")
            cur.execute(
                """
                UPDATE applications
                SET status=%s,
                    position_code=%s,
                    position_title=%s,
                    raw_json=%s::jsonb,
                    updated_at=CURRENT_DATE
                WHERE company_code=%s AND app_key=%s
                """,
                (
                    "needs_role",
                    "",
                    None,
                    json.dumps(raw),
                    company,
                    app_key,
                ),
            )

            # Soft-invalidate verified bindings for this app/job if present.
            try:
                cur.execute(
                    """
                    UPDATE application_job_bindings
                    SET verified=false,
                        provenance = coalesce(provenance,'{}'::jsonb) || jsonb_build_object(
                          'unbound_at', %s,
                          'unbound_reason', 'candidate_profile_redesign_canary_cleanup'
                        )
                    WHERE company_code=%s AND app_key=%s AND position_code=%s
                    """,
                    (now, company, app_key, test_job),
                )
                bindings_updated = cur.rowcount
            except Exception:
                conn.rollback()
                cur.execute("SELECT 1")
                bindings_updated = 0
                cur.execute("SELECT set_config('wathefni.lifecycle_authority', 'canonical', true)")
                cur.execute(
                    """
                    UPDATE applications
                    SET status=%s, position_code=%s, position_title=%s, raw_json=%s::jsonb, updated_at=CURRENT_DATE
                    WHERE company_code=%s AND app_key=%s
                    """,
                    ("needs_role", "", None, json.dumps(raw), company, app_key),
                )

            # Preserve audit rows but retire colliding idempotency keys so future
            # admit proofs are not blocked by the prior canary promote.
            for ev in stale_events:
                old_key = str(ev.get("idempotency_key") or stale_idem)
                if ":superseded:" in old_key:
                    continue
                new_key = f"{old_key}:superseded:{ev.get('event_id')}"
                cur.execute(
                    """
                    UPDATE application_lifecycle_events
                    SET idempotency_key=%s,
                        metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
                          'superseded', true,
                          'superseded_at', %s,
                          'superseded_reason', 'candidate_profile_redesign_canary_cleanup',
                          'original_idempotency_key', %s
                        )
                    WHERE event_id=%s::uuid
                    """,
                    (new_key, now, old_key, ev.get("event_id")),
                )
                events_superseded += cur.rowcount

            phone = before.get("phone")
            if phone:
                cur.execute(
                    """
                    UPDATE candidates
                    SET active_position_code=NULL, updated_at=now()
                    WHERE phone=%s AND active_position_code=%s
                    """,
                    (phone, test_job),
                )

            cur.execute(
                """
                SELECT app_key, status, position_code, position_title, phone, person_id, membership_id, raw_json
                FROM applications WHERE company_code=%s AND app_key=%s
                """,
                (company, app_key),
            )
            after = dict(cur.fetchone())

            cur.execute(
                """
                SELECT app_key, status, position_code
                FROM applications
                WHERE company_code=%s AND app_key <> %s
                  AND (
                    position_code=%s
                    OR app_key LIKE 'imp-wathefni-%%'
                  )
                ORDER BY app_key
                """,
                (company, app_key, test_job),
            )
            unrelated_after = [dict(r) for r in cur.fetchall()]
            conn.commit()

    audit_error = None
    try:
        ctx = {
            "company_code": company,
            "actor_user_id": "platform-ops",
            "actor_email": "ops@wathefni.local",
        }
        app.record_admin_audit(
            ctx,
            "candidate_profile_canary_cleanup",
            summary=f"Restored {app_key} from {test_job}/{status} to needs_role general candidate.",
            target_type="application",
            target=app_key,
            details={
                "previous_status": before.get("status"),
                "previous_position_code": before.get("position_code"),
                "bindings_updated": bindings_updated,
                "events_superseded": events_superseded,
                "reason": "candidate_profile_redesign_canary_cleanup",
            },
        )
    except Exception as exc:
        audit_error = str(exc)

    unchanged_unrelated = unrelated_before == unrelated_after
    payload = {
        "ok": True,
        "skipped": False,
        "app_key": app_key,
        "before": {
            "status": before.get("status"),
            "position_code": before.get("position_code"),
            "phone": before.get("phone"),
            "person_id": before.get("person_id"),
        },
        "after": {
            "status": after.get("status"),
            "position_code": after.get("position_code") or "",
            "phone": after.get("phone"),
            "person_id": after.get("person_id"),
            "import_meta": (after.get("raw_json") or {}).get("import")
            if isinstance(after.get("raw_json"), dict)
            else None,
        },
        "bindings_updated": bindings_updated,
        "events_superseded": events_superseded,
        "stale_events_seen": [
            {
                "event_id": e.get("event_id"),
                "idempotency_key": e.get("idempotency_key"),
                "to_stage": e.get("to_stage"),
            }
            for e in stale_events
        ],
        "unrelated_before": unrelated_before,
        "unrelated_after": unrelated_after,
        "zero_unrelated_mutations": unchanged_unrelated,
        "audit_error": audit_error,
        "cv_identity_preserved": {
            "phone_unchanged": before.get("phone") == after.get("phone"),
            "person_id_unchanged": before.get("person_id") == after.get("person_id"),
        },
    }
    pathlib.Path(f"{evidence}/canary-cleanup.json").write_text(json.dumps(payload, default=str, indent=2))
    print(json.dumps(payload, default=str, indent=2))
    restored = (
        payload["ok"]
        and unchanged_unrelated
        and str(after.get("status") or "") == "needs_role"
        and not str(after.get("position_code") or "").strip()
    )
    return 0 if restored else 1


if __name__ == "__main__":
    raise SystemExit(main())
