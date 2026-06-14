"""Team WhatsApp-linked visibility — GET /dashboard/team exposes a correct,
company-scoped whatsapp_linked flag per user.

Contract proven here (DB-backed, throwaway companies):
  1. A user with an ACTIVE dashboard_whatsapp_identities row shows whatsapp_linked=True.
  2. A user with NO identity row shows whatsapp_linked=False.
  3. A user whose only identity row is status<>'active' (disabled) shows False
     (inactive/deactivated identities never count).
  4. No cross-company leakage: an identity that lives in another company does not
     mark the same user as linked in this company, and the other company's users
     never appear in this company's team list.

Run with the orchestrator venv + prod/staging postgres env, e.g.:
  WATHEFNI_POSTGRES_ENV=... WATHEFNI_WORKSPACE=... \
    /opt/wathefni/orchestrator/.venv/bin/python smoke-test-team-whatsapp-visibility.py
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app

TEST_CO = "TEAMWALINKSMOKE"
OTHER_CO = "TEAMWALINKOTHER"


def _purge() -> None:
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # identities cascade on user delete, but be explicit/idempotent.
                cur.execute("DELETE FROM dashboard_whatsapp_identities WHERE company_code = ANY(%s)", ([TEST_CO, OTHER_CO],))
                cur.execute("DELETE FROM dashboard_users WHERE company_code = ANY(%s)", ([TEST_CO, OTHER_CO],))
            conn.commit()
    except Exception as exc:
        print(f"  WARN purge: {exc}")


def _add_user(company: str, email: str, name: str, role: str = "hr_manager") -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_users (company_code, email, name, role, status, accepted_at, updated_at)
                VALUES (%s,%s,%s,%s,'active',now(),now())
                RETURNING user_id
                """,
                (company, email, name, role),
            )
            user_id = str(cur.fetchone()["user_id"])
        conn.commit()
    return user_id


def _add_identity(company: str, user_id: str, phone: str, status: str = "active") -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_whatsapp_identities (company_code, user_id, phone, status, updated_at)
                VALUES (%s,%s,%s,%s,now())
                ON CONFLICT (company_code, phone)
                DO UPDATE SET user_id=EXCLUDED.user_id, status=EXCLUDED.status, updated_at=now()
                """,
                (company, user_id, phone, status),
            )
        conn.commit()


def _team(company: str) -> dict[str, Any]:
    # Call the real handler directly; prehire.read is enforced by the Depends in
    # production, so a minimal company-scoped context is all the body needs.
    return app.dashboard_team_list(context={"company_code": company, "actor_role": "owner", "actor_user_id": "smoke"})


def _linked_map(company: str) -> dict[str, bool]:
    data = _team(company)
    return {str(u.get("user_id")): bool(u.get("whatsapp_linked")) for u in data.get("users", [])}


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def run_checks(checks: Checks) -> None:
    # Arrange: four users in TEST_CO with different identity states + one in OTHER_CO.
    u_linked = _add_user(TEST_CO, "linked@smoke.local", "Linked User")
    u_unlinked = _add_user(TEST_CO, "unlinked@smoke.local", "Unlinked User")
    u_disabled = _add_user(TEST_CO, "disabled-id@smoke.local", "Disabled Identity User")
    u_cross = _add_user(TEST_CO, "cross@smoke.local", "Cross Company User")
    u_other = _add_user(OTHER_CO, "other@smoke.local", "Other Company User")

    _add_identity(TEST_CO, u_linked, "96599000001", status="active")
    _add_identity(TEST_CO, u_disabled, "96599000002", status="disabled")
    # Cross-company: this user's only active identity lives in OTHER_CO.
    _add_identity(OTHER_CO, u_cross, "96599000003", status="active")
    _add_identity(OTHER_CO, u_other, "96599000004", status="active")

    linked = _linked_map(TEST_CO)

    checks.check("1. active identity -> whatsapp_linked True", lambda: linked.get(u_linked) is True)
    checks.check("2. no identity -> whatsapp_linked False", lambda: linked.get(u_unlinked) is False)
    checks.check("3. disabled identity does NOT count (False)", lambda: linked.get(u_disabled) is False)
    checks.check("4a. identity in another company does NOT mark linked here (False)", lambda: linked.get(u_cross) is False)
    checks.check("4b. other company's user is NOT in this company's team list", lambda: u_other not in linked)

    # The other company sees its own user as linked, and none of TEST_CO's users.
    other_linked = _linked_map(OTHER_CO)
    checks.check("4c. other company sees its own active-identity user as linked", lambda: other_linked.get(u_other) is True)
    checks.check("4d. other company does NOT see this company's users", lambda: u_linked not in other_linked and u_unlinked not in other_linked)

    # Flag is a real boolean on every row (no missing/None).
    checks.check("every team row has a boolean whatsapp_linked", lambda: all(isinstance(u.get("whatsapp_linked"), bool) for u in _team(TEST_CO)["users"]))


def main() -> None:
    print("team whatsapp-linked visibility — company-scoped, active-only")
    _purge()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        _purge()
    code = checks.report()
    if code:
        print("\nTEAM WHATSAPP VISIBILITY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nTEAM WHATSAPP VISIBILITY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
