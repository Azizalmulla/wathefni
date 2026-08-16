#!/usr/bin/env python3
"""Smoke: assignment_type schema + UI markers. Prefer orchestrator venv python."""
from __future__ import annotations

import os
import pathlib
import sys

ORCH = os.environ.get("ORCH_PATH") or "/opt/wathefni/orchestrator"
DIST = pathlib.Path(os.environ.get("DASH_DIST") or "/opt/wathefni/dashboard-dist")


def main() -> int:
    sys.path.insert(0, ORCH)
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_explicit_environment()
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")

    import app
    import shifts_authority_wave1 as w1

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w1.ensure_shifts_authority_wave1_schema(cur)
            conn.commit()
            cur.execute(
                """
                SELECT column_name, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name='shift_assignments' AND column_name='assignment_type'
                """
            )
            col = cur.fetchone()
            assert col, "assignment_type column missing"
            cur.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE conname='shift_assignment_type_chk'
                """
            )
            assert cur.fetchone(), "assignment_type check missing"
            cur.execute(
                """
                SELECT COALESCE(assignment_type, 'general') AS assignment_type, count(*)
                FROM shift_assignments
                WHERE company_code='WATHEFNI' AND status='scheduled'
                GROUP BY 1 ORDER BY 1
                """
            )
            counts = {str(r["assignment_type"]): int(r["count"]) for r in cur.fetchall()}
            print("ASSIGNMENT_TYPE_COUNTS", counts)
            assert w1.normalize_assignment_type(None) == "general"
            assert w1.normalize_assignment_type("guest") == "guest"
            assert w1.normalize_assignment_type("Front desk") == "general"
            assert w1.normalize_assignment_type("bogus", reject_unknown=True) is None

    posthire = list(DIST.glob("assets/PostHire-*.js"))
    assert posthire, "PostHire bundle missing"
    text = posthire[0].read_text(encoding="utf-8", errors="ignore")
    for needle in (
        "data-shifts-visual-direction",
        "data-shifts-iq-wave2",
        "data-shifts-updating",
        "data-shifts-assignment-type",
        "assignment_type",
    ):
        assert needle in text, f"missing bundle marker {needle}"
    print("BUNDLE", posthire[0].name)
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
