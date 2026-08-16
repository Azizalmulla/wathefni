#!/usr/bin/env python3
"""Smoke: Calendar populated preview — WATHEFNI-only, no DB writes, kill-switch."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/wathefni-orchestrator")
# When run from repo root:
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ORCH = os.path.join(ROOT, "wathefni-orchestrator")
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import calendar_populated_preview as cpp  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"PASS  {msg}")


def main() -> None:
    os.environ.pop(cpp.FLAG, None)
    check(not cpp.preview_enabled_for_company("WATHEFNI"), "flag off → disabled")

    os.environ[cpp.FLAG] = "on"
    os.environ[cpp.COMPANIES_FLAG] = "WATHEFNI"
    check(cpp.preview_enabled_for_company("WATHEFNI"), "flag on + WATHEFNI → enabled")
    check(not cpp.preview_enabled_for_company("OTHERCO"), "other tenant denied")

    events = cpp.build_preview_events()
    check(len(events) >= 10, f"dense synthetic set ({len(events)})")
    check(all(e["preview_only"] is True for e in events), "all preview_only")
    check(all(str(e["event_id"]).startswith(cpp.PREVIEW_ID_PREFIX) for e in events), "calprev- ids")
    check(all("Preview" in e["title"] or "معاينة" in e["title"] for e in events), "Preview in titles")
    check(any(e["metadata"]["preview_category"] == "approved_leave" for e in events), "leave preview category")
    check(any(e["status"] == "cancelled" for e in events), "cancelled status sample")

    # Overlap Monday interview + meeting
    mon = [e for e in events if "interview-sara" in e["event_id"] or "hiring-sync" in e["event_id"]]
    check(len(mon) == 2, "overlap pair present")

    tz = ZoneInfo("Asia/Kuwait")
    now = datetime.now(tz)
    start = (now - timedelta(days=1)).isoformat()
    end = (now + timedelta(days=14)).isoformat()
    window = cpp.events_overlapping_range(start=start, end=end)
    check(len(window) >= 5, f"range overlap injects events ({len(window)})")

    merged = cpp.merge_into_list_result(
        {"events": [{"event_id": "real-1", "title": "Real"}], "count": 1},
        company_code="WATHEFNI",
        start=start,
        end=end,
    )
    check(merged["populated_preview"]["enabled"] is True, "list merge marks preview")
    check(merged["count"] > 1, "list merge adds events")
    check(any(e["event_id"] == "real-1" for e in merged["events"]), "real events preserved")

    denied = cpp.merge_into_list_result(
        {"events": [], "count": 0},
        company_code="ACME",
        start=start,
        end=end,
    )
    check("populated_preview" not in denied or denied.get("count") == 0, "non-WATHEFNI unchanged")
    # When flag on but wrong company, merge returns result unchanged without preview key
    check(denied.get("count") == 0 and "populated_preview" not in denied, "ACME gets no inject")

    check(cpp.is_preview_event_id("calprev-x"), "preview id detect")
    check(cpp.get_preview_event(events[0]["event_id"]) is not None, "detail lookup")

    os.environ[cpp.FLAG] = "off"
    check(not cpp.preview_enabled_for_company("WATHEFNI"), "instant kill switch")
    print("CALENDAR_POPULATED_PREVIEW_SMOKE_OK")


if __name__ == "__main__":
    main()
