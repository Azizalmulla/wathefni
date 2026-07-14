"""HR-0: manager scope must fail closed for the manager role.

Pins source + runtime (when psycopg2 is available):
  - manager without phone/user binding -> restricted empty + configuration_error
  - manager with phone but no assignments -> restricted empty + configuration_error
  - explicit team assignment still restricts
  - removed assignments fail closed
  - owners/HR without scopes remain unrestricted
  - operator identity (dashboard_user_id) is preferred when present

Run: python3 smoke-test-hr0-manager-scope-fail-closed.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    HR-0 manager scope fail-closed")
    root = Path(__file__).resolve().parent
    source = (root / "app.py").read_text(encoding="utf-8")

    check("MANAGER_SCOPE_REQUIRED_ROLES includes manager", 'MANAGER_SCOPE_REQUIRED_ROLES = frozenset({"manager"})' in source)
    check("fail-closed helper exists", "def _fail_closed_manager_scope" in source)
    check("binding conflict error exists", "manager_scope_binding_conflict" in source)
    check("user-id resolution does not merge phone sets", "Exclusive user-ID resolution" in source or "never union phone-only rows" in source)
    check("phone fallback only when user id absent", "Transitional phone fallback" in source)
    check("unconfigured error exists", "manager_scope_unconfigured" in source)
    check("dashboard_user_id column migration present", "ADD COLUMN IF NOT EXISTS dashboard_user_id" in source)
    check("operator_manager_scope helper exists", "def operator_manager_scope" in source)
    check("dashboard_context uses operator_manager_scope", "operator_manager_scope(" in source)
    check("context_manager_allows_employee exists", "def context_manager_allows_employee" in source)
    # Ensure the old fail-open empty-phone return is gone for the role-aware path.
    check(
        "no unconditional unrestricted empty-phone return remains alone",
        'if not phone:\n        return {"restricted": False' not in source,
    )

    sys.path.insert(0, str(root))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2" or (exc.name or "").startswith("psycopg2"):
            print("NOTE: runtime checks skipped (psycopg2 unavailable locally).")
            print(f"\n{PASS} passed, {FAIL} failed")
            return 1 if FAIL else 0
        raise

    company = "HR0MGRSCOPE"
    other = "OTHERCO"

    empty = app.manager_scope_context(None, company, actor_role="manager")
    check("manager without phone fails closed", empty.get("restricted") is True)
    check(
        "manager without phone has configuration_error",
        empty.get("configuration_error") == "manager_scope_binding_missing",
    )
    check("manager without phone has empty keys", empty.get("branch_keys") == [] and empty.get("team_keys") == [])

    owner_empty = app.manager_scope_context(None, company, actor_role="owner")
    check("owner without phone stays unrestricted", owner_empty.get("restricted") is False)

    hr_empty = app.manager_scope_context(None, company, actor_role="hr_manager")
    check("hr_manager without phone stays unrestricted", hr_empty.get("restricted") is False)

    class _Cur:
        def __init__(self, rows):
            self._rows = rows
            self._params = None

        def execute(self, *a, **k):
            if len(a) > 1:
                self._params = a[1]
            elif "params" in k:
                self._params = k["params"]
            return None

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def __init__(self, rows):
            self._rows = rows
            self.last_cur = None

        def cursor(self):
            self.last_cur = _Cur(self._rows)
            return self.last_cur

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch.object(app, "db_connect", return_value=_Conn([])):
        missing = app.manager_scope_context("96550001111", company, actor_role="manager")
    check("manager with phone but no assignments fails closed", missing.get("restricted") is True)
    check(
        "unconfigured manager error is deterministic",
        missing.get("configuration_error") == "manager_scope_unconfigured",
    )

    with patch.object(app, "db_connect", return_value=_Conn([])):
        hr_no_scope = app.manager_scope_context("96550002222", company, actor_role="hr_manager")
    check("HR with phone and no rows remains unrestricted", hr_no_scope.get("restricted") is False)

    team_key = app.org_key(company, "team", "Team A")
    scoped_rows = [
        {
            "scope_id": "11111111-1111-1111-1111-111111111111",
            "company_code": company,
            "manager_phone": "96550003333",
            "dashboard_user_id": "user-mgr-1",
            "scope_type": "team",
            "branch_key": None,
            "team_key": team_key,
            "role": "manager",
            "is_active": True,
        }
    ]
    with patch.object(app, "db_connect", return_value=_Conn(scoped_rows)):
        with patch.object(app, "org_hierarchy_enabled", return_value=True):
            scoped = app.manager_scope_context(
                "96550003333",
                company,
                dashboard_user_id="user-mgr-1",
                actor_role="manager",
            )
    check("explicit team assignment is restricted", scoped.get("restricted") is True)
    check("explicit team assignment exposes team_key", scoped.get("team_keys") == [team_key])

    conn = _Conn([])
    with patch.object(app, "db_connect", return_value=conn):
        app.manager_scope_context("96550004444", other, actor_role="manager")
    check(
        "cross-company lookup binds requested company only",
        bool(conn.last_cur and conn.last_cur._params and conn.last_cur._params[0] == other),
    )

    with patch.object(app, "db_connect", return_value=_Conn([])):
        removed = app.manager_scope_context(
            "96550003333",
            company,
            dashboard_user_id="user-mgr-1",
            actor_role="manager",
        )
    check("removed assignments fail closed", removed.get("configuration_error") == "manager_scope_unconfigured")

    clause, _ = app.employee_scope_sql("e", empty)
    check("fail-closed scope SQL is AND FALSE", clause == "AND FALSE")

    with patch.object(app, "db_connect", return_value=_Conn([])):
        allowed = app.manager_scope_allows_employee(
            {"employee_key": "emp-a", "company_code": company},
            company_code=company,
            viewer_phone=None,
            actor_role="manager",
        )
    check("manager without binding cannot see employees", allowed is False)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
