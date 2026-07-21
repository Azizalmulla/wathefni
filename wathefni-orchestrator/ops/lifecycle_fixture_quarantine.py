#!/usr/bin/env python3
"""Shared guard for historical scripts that used direct lifecycle SQL.

After Candidates C0/C1, applications.status/current_step updates outside the
canonical authority are blocked by applications_lifecycle_authority_guard.
Scripts must migrate to recruiting_lifecycle.transition_application (or intake
helpers) before they can run again.
"""

from __future__ import annotations

import os
import sys


QUARANTINE_REASON = (
    "quarantined_after_candidates_c0_c1: direct applications.status/current_step "
    "fixture writes are blocked by the lifecycle authority trigger. Migrate this "
    "script to recruiting_lifecycle.transition_application (or intake helpers) "
    "before re-enabling. Override only with WATHEFNI_ALLOW_LEGACY_LIFECYCLE_FIXTURES=1 "
    "for emergency forensics."
)


def refuse_unless_legacy_fixtures_explicitly_allowed(*, script_name: str) -> None:
    if (os.environ.get("WATHEFNI_ALLOW_LEGACY_LIFECYCLE_FIXTURES") or "").strip() == "1":
        print(f"WARNING: {script_name} running with legacy lifecycle fixture override enabled", file=sys.stderr)
        return
    raise SystemExit(f"{script_name}: {QUARANTINE_REASON}")
