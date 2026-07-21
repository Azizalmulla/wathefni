#!/usr/bin/env python3
"""Deterministic cleanup for Stage B canary applications/contexts on staging."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch


def main() -> None:
    assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni_staging"
    position_code = (os.environ.get("STAGE_B_CLEANUP_POSITION") or "").strip()
    phones = [
        p.strip()
        for p in (os.environ.get("STAGE_B_CLEANUP_PHONES") or os.environ.get("WATHEFNI_STAGE_B_CANDIDATE_ALLOWLIST") or "").split(",")
        if p.strip()
    ]
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute("select current_database() as d")
        assert cur.fetchone()["d"] == "wathefni_staging"
        deleted: dict[str, int] = {}
        if phones:
            cur.execute("DELETE FROM conversation_application_bindings WHERE phone = ANY(%s)", (phones,))
            deleted["bindings"] = cur.rowcount
            cur.execute("DELETE FROM candidate_pending_media WHERE phone = ANY(%s)", (phones,))
            deleted["pending_media"] = cur.rowcount
            cur.execute("DELETE FROM candidate_job_contexts WHERE phone = ANY(%s)", (phones,))
            deleted["contexts"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM applications
                WHERE phone = ANY(%s)
                  AND (
                    COALESCE(raw_json->>'stage_b_canary','')='true'
                    OR (%s <> '' AND position_code=%s)
                  )
                """,
                (phones, position_code, position_code),
            )
            deleted["applications"] = cur.rowcount
        if position_code:
            cur.execute(
                "DELETE FROM positions WHERE company_code='WATHEFNI' AND position_code=%s",
                (position_code,),
            )
            deleted["positions"] = cur.rowcount
    print(json.dumps({"ok": True, "deleted": deleted, "phones": phones, "position_code": position_code}))


if __name__ == "__main__":
    main()
