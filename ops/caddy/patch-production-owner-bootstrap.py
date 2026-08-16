#!/usr/bin/env python3
"""Surgical production patch: Setup owner bootstrap grants. Does not replace app.py."""
from __future__ import annotations

from pathlib import Path

APP = Path("/opt/wathefni/orchestrator/app.py")
SEED_OLD = '''            invite = dict(cur.fetchone() or {})
        conn.commit()
    record_admin_audit(
        _setup_audit_context(superadmin, company),
        "setup_owner_seeded",
'''
SEED_NEW = '''            invite = dict(cur.fetchone() or {})
            import setup_owner_bootstrap as _owner_boot
            bootstrap = _owner_boot.apply_owner_bootstrap_grants(
                cur,
                company_code=company,
                user_id=str(user.get("user_id") or ""),
                granted_by_user_id=str(user.get("user_id") or ""),
            )
            write_admin_audit(
                cur,
                _setup_audit_context(superadmin, company),
                "setup_owner_bootstrap_grants",
                summary=f"Applied {_owner_boot.BUNDLE_VERSION} grants for owner {email}.",
                target_type="team_member",
                target=email,
                details={
                    "company_code": company,
                    "email": email,
                    "user_id": str(user.get("user_id") or ""),
                    "bundle_version": _owner_boot.BUNDLE_VERSION,
                    "granted": bootstrap.get("granted"),
                    "already_present": bootstrap.get("already_present"),
                    "source": "setup_console_seed",
                },
            )
        conn.commit()
    record_admin_audit(
        _setup_audit_context(superadmin, company),
        "setup_owner_seeded",
'''
ACCEPT_OLD = '''                    (company, user.get("user_id"), digits(user.get("phone"))),
                )
        conn.commit()
    token, expires_at = create_dashboard_session(user)
    return dashboard_auth_response(user, token, expires_at)
'''
ACCEPT_NEW = '''                    (company, user.get("user_id"), digits(user.get("phone"))),
                )
            if dashboard_role_key(user.get("role")) == "owner":
                import setup_owner_bootstrap as _owner_boot
                bootstrap = _owner_boot.apply_owner_bootstrap_grants(
                    cur,
                    company_code=company,
                    user_id=str(user.get("user_id") or ""),
                    granted_by_user_id=str(user.get("user_id") or ""),
                )
                write_admin_audit(
                    cur,
                    {
                        "company_code": company,
                        "actor_user_id": user.get("user_id"),
                        "actor_email": user.get("email"),
                        "actor_role": user.get("role"),
                        "hr_user": user,
                    },
                    "setup_owner_bootstrap_grants",
                    summary=f"Applied {_owner_boot.BUNDLE_VERSION} grants on owner invite accept.",
                    target_type="team_member",
                    target=str(user.get("email") or user.get("user_id") or ""),
                    details={
                        "company_code": company,
                        "user_id": str(user.get("user_id") or ""),
                        "bundle_version": _owner_boot.BUNDLE_VERSION,
                        "granted": bootstrap.get("granted"),
                        "already_present": bootstrap.get("already_present"),
                        "source": "invite_accept",
                    },
                )
        conn.commit()
    token, expires_at = create_dashboard_session(user)
    return dashboard_auth_response(user, token, expires_at)
'''
INVITE_OLD = '''            invite = dict(cur.fetchone() or {})
        conn.commit()
    record_admin_audit(
        context,
        "team_member_invited",
'''
INVITE_NEW = '''            invite = dict(cur.fetchone() or {})
            if dashboard_role_key(role) == "owner":
                import setup_owner_bootstrap as _owner_boot
                bootstrap = _owner_boot.apply_owner_bootstrap_grants(
                    cur,
                    company_code=company,
                    user_id=str(user.get("user_id") or ""),
                    granted_by_user_id=str(context.get("actor_user_id") or user.get("user_id") or ""),
                )
                write_admin_audit(
                    cur,
                    context,
                    "setup_owner_bootstrap_grants",
                    summary=f"Applied {_owner_boot.BUNDLE_VERSION} grants for invited owner {email}.",
                    target_type="team_member",
                    target=email,
                    details={
                        "company_code": company,
                        "email": email,
                        "user_id": str(user.get("user_id") or ""),
                        "bundle_version": _owner_boot.BUNDLE_VERSION,
                        "granted": bootstrap.get("granted"),
                        "already_present": bootstrap.get("already_present"),
                        "source": "team_invite",
                    },
                )
        conn.commit()
    record_admin_audit(
        context,
        "team_member_invited",
'''


def main() -> int:
    text = APP.read_text(encoding="utf-8")
    if "apply_owner_bootstrap_grants" in text:
        print("ALREADY_PATCHED")
        return 0
    for old, new, label in (
        (SEED_OLD, SEED_NEW, "seed"),
        (ACCEPT_OLD, ACCEPT_NEW, "accept"),
        (INVITE_OLD, INVITE_NEW, "invite"),
    ):
        if old not in text:
            print(f"MISSING_ANCHOR_{label}")
            return 1
        text = text.replace(old, new, 1)
    APP.write_text(text, encoding="utf-8")
    print("PATCHED_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
