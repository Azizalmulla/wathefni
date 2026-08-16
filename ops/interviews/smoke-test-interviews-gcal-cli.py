#!/usr/bin/env python3
"""Focused argv construction tests for Google Calendar update/delete CLI fixes.

No DB. No live gog. Asserts command shapes against gog v0.12.0 constraints:
- update must NOT include --with-meet
- delete must include --force for non-interactive confirmation
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

ORCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ORCH))

import interview_service as svc  # noqa: E402


def main() -> int:
    calls: list[list[str]] = []

    class Legacy:
        def openclaw_env(self) -> dict[str, str]:
            return {"GOG_ACCOUNT": "soak@example.com"}

        def run_gog(self, args: list[str], timeout: int = 60) -> dict[str, Any]:
            calls.append(list(args))
            # First update attempt succeeds; first delete attempt succeeds.
            return {"ok": True, "args": list(args)}

    legacy = Legacy()
    start = datetime.now(timezone.utc).replace(microsecond=0)
    end = start + timedelta(minutes=30)

    calls.clear()
    upd = svc._google_update(
        legacy,
        "evt-same-1",
        summary="Wathefni interview",
        start=start,
        end=end,
        attendees=["cand@intv.invalid", "panel@intv.invalid"],
        with_meet=True,
    )
    assert upd.get("ok") is True, upd
    assert len(calls) == 1, calls
    args = calls[0]
    assert args[:4] == ["calendar", "update", "primary", "evt-same-1"], args
    assert "--with-meet" not in args, args
    assert "--from" in args and "--to" in args, args
    assert "--attendees" in args, args
    assert "--account" in args and "soak@example.com" in args, args
    print("PASS: update_omits_with_meet_preserves_same_event_id")

    # Fallback path: primary update fails, events update must also omit --with-meet
    calls.clear()

    class LegacyFailThenOk:
        def openclaw_env(self) -> dict[str, str]:
            return {"GOG_ACCOUNT": "soak@example.com"}

        def run_gog(self, args: list[str], timeout: int = 60) -> dict[str, Any]:
            calls.append(list(args))
            if args[:2] == ["calendar", "update"]:
                return {"ok": False, "stderr": "unknown flag --with-meet"}
            return {"ok": True, "args": list(args)}

    upd2 = svc._google_update(
        LegacyFailThenOk(),
        "evt-same-2",
        summary="Wathefni interview",
        start=start,
        end=end,
        attendees=["cand@intv.invalid"],
        with_meet=True,
    )
    assert upd2.get("ok") is True, upd2
    assert len(calls) == 2, calls
    assert "--with-meet" not in calls[0] and "--with-meet" not in calls[1], calls
    assert calls[1][:5] == ["calendar", "events", "update", "primary", "evt-same-2"], calls[1]
    print("PASS: update_fallback_also_omits_with_meet")

    calls.clear()
    deleted = svc._google_delete(legacy, "evt-same-1")
    assert deleted.get("ok") is True, deleted
    assert len(calls) == 1, calls
    dargs = calls[0]
    assert dargs[:4] == ["calendar", "delete", "primary", "evt-same-1"], dargs
    assert "--force" in dargs, dargs
    assert "--no-input" in dargs, dargs
    assert "--account" in dargs and "soak@example.com" in dargs, dargs
    print("PASS: delete_includes_force_noninteractive")

    # Fallback delete also includes --force
    calls.clear()

    class LegacyDeleteFallback:
        def openclaw_env(self) -> dict[str, str]:
            return {}

        def run_gog(self, args: list[str], timeout: int = 60) -> dict[str, Any]:
            calls.append(list(args))
            if args[:2] == ["calendar", "delete"]:
                return {"ok": False, "stderr": "unexpected"}
            return {"ok": True, "args": list(args)}

    deleted2 = svc._google_delete(LegacyDeleteFallback(), "evt-x")
    assert deleted2.get("ok") is True, deleted2
    assert len(calls) == 2, calls
    assert "--force" in calls[0] and "--force" in calls[1], calls
    assert calls[1][:5] == ["calendar", "events", "delete", "primary", "evt-x"], calls[1]
    print("PASS: delete_fallback_includes_force")

    # Create still may use --with-meet (unchanged contract)
    calls.clear()
    created = svc._google_create(
        legacy,
        summary="Wathefni interview",
        start=start,
        end=end,
        attendees=["cand@intv.invalid"],
        with_meet=True,
    )
    assert created.get("ok") is True, created
    assert "--with-meet" in calls[0], calls[0]
    print("PASS: create_still_supports_with_meet")

    print("ALL FOCUSED GOOGLE CLI CONSTRUCTION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
