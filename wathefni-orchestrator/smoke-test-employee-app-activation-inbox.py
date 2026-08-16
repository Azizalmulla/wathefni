#!/usr/bin/env python3
"""Employee App Inbox — activation supersede / projection contract.

Proves:
  1. Source contract: deliver hides priors; inbox projection filters hidden + keeps
     only the newest app_activation.
  2. Pure projection behaviour for mixed flows (activation flood vs payroll).
  3. Optional live canary remediate + unread honesty when WATHEFNI_LIVE_INBOX=1.

No new Inbox tabs. Does not redesign the FE list.
"""
from __future__ import annotations

import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any


def check(label: str, ok: bool, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    if ok:
        print(f"PASS  {label}{suffix}")
    else:
        print(f"FAIL  {label}{suffix}")
        raise SystemExit(1)


def _project_inbox(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror `_employee_inbox_rows` visibility rules for unit proof without DB."""
    visible: list[dict[str, Any]] = []
    for row in rows:
        meta = row.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("inbox_hidden") is True:
            continue
        visible.append(row)
    latest_activation = None
    for row in sorted(visible, key=lambda r: r.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        if row.get("flow") == "app_activation":
            latest_activation = row.get("message_id")
            break
    out: list[dict[str, Any]] = []
    for row in visible:
        if row.get("flow") == "app_activation" and row.get("message_id") != latest_activation:
            continue
        out.append(row)
    out.sort(key=lambda r: r.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def main() -> None:
    import app as orch
    import employee_app_invitation as inv

    deliver_src = inspect.getsource(orch.deliver_app_activation_code)
    supersede_src = inspect.getsource(orch._supersede_prior_app_activation_inbox)
    inbox_src = inspect.getsource(orch._employee_inbox_rows)
    deliver_code_src = inspect.getsource(inv._deliver_code)

    check(
        "new activation delivery supersedes prior Inbox rows after send",
        "_supersede_prior_app_activation_inbox" in deliver_src
        and "keep_message_id" in deliver_src
        and "inbox_hidden" in supersede_src
        and "superseded_by_newer_activation" in supersede_src,
    )
    check(
        "activation delivery uses invite-scoped dedupe without blocking new codes",
        "dedupe_key=" in deliver_src and "app_activation:" in deliver_src and "invite_id" in deliver_src,
    )
    check(
        "invitation deliver passes invite_id into activation delivery",
        "invite_id=invite_id" in deliver_code_src,
    )
    check(
        "Inbox projection omits inbox_hidden rows",
        "inbox_hidden" in inbox_src and "IS NOT TRUE" in inbox_src,
    )
    check(
        "Inbox projection keeps only the newest visible app_activation",
        "flow IS DISTINCT FROM 'app_activation'" in inbox_src
        and "ORDER BY m2.created_at DESC" in inbox_src
        and "LIMIT 1" in inbox_src,
    )

    now = datetime.now(timezone.utc)
    rows = [
        {
            "message_id": "a1",
            "flow": "app_activation",
            "created_at": now - timedelta(days=3),
            "metadata": {},
            "read": False,
        },
        {
            "message_id": "a2",
            "flow": "app_activation",
            "created_at": now - timedelta(days=2),
            "metadata": {},
            "read": False,
        },
        {
            "message_id": "a3",
            "flow": "app_activation",
            "created_at": now - timedelta(hours=1),
            "metadata": {},
            "read": False,
        },
        {
            "message_id": "p1",
            "flow": "payroll",
            "created_at": now - timedelta(hours=2),
            "metadata": {},
            "read": False,
        },
        {
            "message_id": "a0",
            "flow": "app_activation",
            "created_at": now - timedelta(days=10),
            "metadata": {"inbox_hidden": True},
            "read": False,
        },
    ]
    projected = _project_inbox(rows)
    ids = [r["message_id"] for r in projected]
    check("activation flood collapses to newest only", ids.count("a3") == 1 and "a1" not in ids and "a2" not in ids, str(ids))
    check("hidden activation stays out of projection", "a0" not in ids)
    check("non-activation flows are unaffected", "p1" in ids)
    unread = sum(1 for r in projected if not r.get("read"))
    check("unread counts only projected rows", unread == 2, f"unread={unread}")

    if os.environ.get("WATHEFNI_LIVE_INBOX") == "1":
        company = (os.environ.get("WATHEFNI_COMPANY") or "WATHEFNI").upper()
        keys = [
            k.strip()
            for k in (
                os.environ.get("WATHEFNI_CANARY_KEYS")
                or "WATHEFNI-96599338566,WATHEFNI-96550252254"
            ).split(",")
            if k.strip()
        ]
        for key in keys:
            before = None
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT count(*) AS c FROM employee_messages
                        WHERE company_code=%s AND employee_key=%s AND flow='app_activation'
                          AND COALESCE((metadata->>'inbox_hidden')::boolean, false) IS NOT TRUE
                        """,
                        (company, key),
                    )
                    before = int(cur.fetchone()["c"])
            result = orch._remediate_app_activation_inbox_projection(company_code=company, employee_key=key)
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    projected_live = orch._employee_inbox_rows(cur, company_code=company, employee_key=key)
            activation_live = [r for r in projected_live if r.get("flow") == "app_activation"]
            check(
                f"live {key}: at most one visible app_activation after remediate",
                len(activation_live) <= 1,
                f"before_visible={before} remediate={result} projected_activation={len(activation_live)}",
            )
            print(
                f"INFO  live {key}: activation_before_visible={before} "
                f"hidden={result.get('hidden')} kept={result.get('kept')} "
                f"inbox_total={len(projected_live)} unread="
                f"{sum(1 for r in projected_live if not r.get('read'))}"
            )

    print("PASS employee app activation inbox projection")


if __name__ == "__main__":
    main()
