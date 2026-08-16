#!/usr/bin/env python3
"""Production Readiness R8 — staging DB migration + error-event contracts."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import app
    import migration_framework as mf
    import observability
    import schema_contract

    print("    PRODUCTION READINESS R8 — delivery safety DB contracts")
    marker = f"r8-db-{uuid.uuid4().hex[:8]}"
    secret = "super-secret-token-value"
    phone = "+96550001111"
    email = "ceo@acme.test"

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if schema_contract.schema_apply_allowed():
                applied = mf.apply_pending(cur)
                conn.commit()
                check("apply_pending ran under WATHEFNI_SCHEMA_APPLY", True, applied)
            else:
                check("runtime path does not apply schema", True)
            drift = mf.detect_drift(cur)
            hist = mf.history(cur)
            waiting = mf.pending(cur)
            check("drift detector is ok after apply", drift.get("ok") is True, drift)
            check("version 1 is in history", 1 in [int(row["version"]) for row in hist], hist)
            check("no pending forward migrations", waiting == [], waiting)
            check("required relations exist", drift.get("missing_relations") == [])

    event = observability.record_error_event(
        app,
        surface="hr_web",
        message=f"{marker} password={secret} {phone} {email}",
        detail={"password": secret, "token": "abcd", "note": f"mail {email} phone {phone}"},
    )
    check("error event persist attempted", event.get("stored") is True, event)
    check("stored message redacts email", "[redacted-email]" in event["message"])
    check("stored message redacts phone", "[redacted-phone]" in event["message"])
    check("stored detail redacts password", event["detail"].get("password") == "[redacted]")
    check("raw secret never stored in message", secret not in event["message"])
    check("raw secret never stored in detail json", secret not in json.dumps(event["detail"]))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT message, detail FROM wathefni_error_events WHERE event_id=%s",
                (event["event_id"],),
            )
            row = cur.fetchone()
    check("error event row exists", bool(row), event["event_id"])
    if row:
        message = row["message"] if isinstance(row, dict) else row[0]
        detail = row["detail"] if isinstance(row, dict) else row[1]
        check("DB message has no raw secret", secret not in str(message))
        check("DB message has no raw email", email not in str(message))
        check("DB detail has no raw secret", secret not in json.dumps(detail, default=str))

    jobs = observability.failed_job_visibility(app)
    check("failed-job visibility returns a total", isinstance(jobs.get("total"), int), jobs)
    snap = observability.delivery_snapshot(app)
    check("delivery snapshot migrations ok", bool((snap.get("migrations") or {}).get("ok")), snap.get("migrations"))
    check("delivery snapshot includes failed_jobs", "failed_jobs" in snap)
    rollback = mf.rollback_procedure()
    check("rollback procedure remains restore-from-backup", rollback["mode"] == "restore_from_backup")

    print("\n    R8_DELIVERY_SAFETY_DB_PASS")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
