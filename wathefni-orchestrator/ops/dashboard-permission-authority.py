#!/usr/bin/env python3
"""Audited dashboard permission-authority cutover operations.

This tool never infers employee permissions from a role. Production operators
must review the inventory, record explicit grants, run preflight, revoke
recovery sessions, and then require normal reauthentication.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def inventory(company_code: str) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    app.ensure_schema()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id, u.email, u.name, u.role, u.status,
                       COALESCE(u.metadata->>'source','workspace') AS auth_source,
                       count(DISTINCT s.session_id) FILTER (
                         WHERE s.status='active' AND s.expires_at > now()
                       ) AS active_sessions,
                       COALESCE(
                         array_agg(DISTINCT g.permission ORDER BY g.permission)
                           FILTER (WHERE g.status='active'),
                         ARRAY[]::text[]
                       ) AS explicit_permissions
                FROM dashboard_users u
                LEFT JOIN dashboard_user_sessions s ON s.user_id=u.user_id
                LEFT JOIN dashboard_user_permission_grants g
                  ON g.company_code=u.company_code AND g.user_id=u.user_id
                WHERE u.company_code=%s
                GROUP BY u.user_id, u.email, u.name, u.role, u.status, u.metadata
                ORDER BY u.role, u.email
                """,
                (company,),
            )
            users = [dict(row) for row in cur.fetchall()]
    return {
        "ok": True,
        "company_code": company,
        "users": app.json_safe(users),
        "employee_permission_scopes": sorted(app.EMPLOYEE_PERMISSION_SCOPES),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inventory", help="List current users, sessions, and explicit grants")
    inspect_cmd.add_argument("--company", required=True)

    for name in ("grant", "revoke"):
        cmd = sub.add_parser(name, help=f"{name.title()} one reviewed permission")
        cmd.add_argument("--company", required=True)
        cmd.add_argument("--user-id", required=True)
        cmd.add_argument("--permission", required=True, choices=sorted(app.KNOWN_DASHBOARD_PERMISSIONS))
        cmd.add_argument("--actor-user-id", required=True)
        cmd.add_argument("--reason", required=True)
        cmd.add_argument("--review-reference", required=True)

    preflight_cmd = sub.add_parser("preflight", help="Refuse cutover without a reviewed normal owner")
    preflight_cmd.add_argument("--company", required=True)
    preflight_cmd.add_argument("--require-no-recovery-sessions", action="store_true")

    revoke_sessions = sub.add_parser("revoke-recovery-sessions", help="Revoke active legacy/recovery sessions")
    revoke_sessions.add_argument("--company", required=True)
    revoke_sessions.add_argument("--actor-user-id", required=True)
    revoke_sessions.add_argument("--reason", required=True)
    revoke_sessions.add_argument("--review-reference", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "inventory":
        result = inventory(args.company)
    elif args.command in {"grant", "revoke"}:
        result = app.set_dashboard_user_permission_grant(
            args.company,
            args.user_id,
            args.permission,
            active=args.command == "grant",
            actor_user_id=args.actor_user_id,
            reason=args.reason,
            review_reference=args.review_reference,
        )
    elif args.command == "preflight":
        result = app.permission_authority_preflight(args.company)
        if args.require_no_recovery_sessions and result.get("active_recovery_sessions"):
            result = {
                **result,
                "ok": False,
                "error": "active_recovery_sessions_remain",
            }
    else:
        result = app.revoke_dashboard_recovery_sessions(
            args.company,
            actor_user_id=args.actor_user_id,
            reason=args.reason,
            review_reference=args.review_reference,
        )
    print(json.dumps(app.json_safe(result), indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
