#!/usr/bin/env python3
"""Staging smoke: Pre-Hiring Overview remediation invariants.

Proves card counts == destination filter totals, Reports alignment,
next_action authority, and work-queue contract — without touching production.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011").rstrip("/")
TOKEN = os.environ.get("WATHEFNI_STAGING_TOKEN", "")
COMPANY = os.environ.get("WATHEFNI_STAGING_COMPANY", "WATHEFNI")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"PASS: {msg}")


def request(path: str, *, params: dict | None = None) -> dict:
    if not TOKEN:
        fail("WATHEFNI_STAGING_TOKEN is required")
    qs = urllib.parse.urlencode(params or {})
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Company-Code": COMPANY,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"{path} -> HTTP {exc.code}: {detail[:400]}")
    except Exception as exc:  # noqa: BLE001
        fail(f"{path} -> {exc}")


def main() -> None:
    summary = request("/dashboard/prehire/summary")
    counts = summary.get("action_counts") or {}
    next_action = summary.get("next_action") or {}
    role = summary.get("role_priority")
    reports = request("/dashboard/prehire/reports")
    report_summary = reports.get("summary") or {}

    ready = int(counts.get("ready_for_review") or 0)
    assess = int(counts.get("assessment_pending") or 0)
    follow = int(counts.get("follow_up_needed") or 0)

    ready_dest = request(
        "/dashboard/prehire/applications",
        params={"review_status": "ready", "sort": "ready_for_review", "limit": 1, "offset": 0},
    )
    assess_dest = request(
        "/dashboard/prehire/applications",
        params={"assessment_status": "awaiting", "limit": 1, "offset": 0},
    )
    follow_dest = request(
        "/dashboard/prehire/applications",
        params={"follow_up": "needed", "limit": 1, "offset": 0},
    )

    if int(ready_dest.get("total") or 0) != ready:
        fail(f"ready parity: action_counts={ready} destination={ready_dest.get('total')}")
    ok(f"ready_for_review card==destination ({ready})")

    if int(assess_dest.get("total") or 0) != assess:
        fail(f"assessment parity: action_counts={assess} destination={assess_dest.get('total')}")
    ok(f"assessment_pending card==destination ({assess})")

    if int(follow_dest.get("total") or 0) != follow:
        fail(f"follow-up parity: action_counts={follow} destination={follow_dest.get('total')}")
    ok(f"follow_up_needed card==destination ({follow})")

    if int(report_summary.get("ready_for_review") or -1) != ready:
        fail("Reports ready_for_review != Overview")
    if int(report_summary.get("assessment_pending") or -1) != assess:
        fail("Reports assessment_pending != Overview")
    if int(report_summary.get("followups") or -1) != follow:
        fail("Reports followups != Overview follow_up_needed")
    ok("Reports headlines match Overview action_counts")

    if not next_action or "action" not in next_action:
        fail("next_action missing from summary")
    if str(next_action.get("label") or "") == "next_best_action":
        fail("misleading next_best_action label still present")
    if "priority" not in next_action or "reason" not in next_action:
        fail("next_action missing priority/reason")
    ok(f"next_action={next_action.get('action')} priority={next_action.get('priority')}")

    queue = request("/dashboard/prehire/overview/work-queue", params={"limit": 5})
    if "items" not in queue or "total" not in queue:
        fail("work-queue contract incomplete")
    if int(queue.get("limit") or 0) != 5:
        fail("work-queue limit not honored")
    for item in queue.get("items") or []:
        for key in ("action_type", "priority", "reason", "destination", "authority_source", "as_of"):
            if key not in item:
                fail(f"work-queue item missing {key}")
    ok(f"work-queue total={queue.get('total')} page={len(queue.get('items') or [])}")

    if role:
        if not role.get("position_code") or not role.get("reason"):
            fail("role_priority incomplete")
        ok(f"role_priority={role.get('position_code')}")
    else:
        ok("role_priority=null (no pressure)")

    print(
        json.dumps(
            {
                "company": COMPANY,
                "action_counts": counts,
                "next_action": {
                    "action": next_action.get("action"),
                    "priority": next_action.get("priority"),
                    "reason": next_action.get("reason"),
                },
                "work_queue_total": queue.get("total"),
                "role_priority": (role or {}).get("position_code"),
            },
            indent=2,
        )
    )
    print("ALL OVERVIEW REMEDIATION INVARIANTS GREEN")


if __name__ == "__main__":
    main()
