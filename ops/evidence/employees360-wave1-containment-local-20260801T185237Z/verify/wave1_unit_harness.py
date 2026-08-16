"""Wave 1 containment unit harness (no production DB).

Exercises phone alias matching, duplicate prevention, canary allowlists,
manager-scope denial, and optimistic concurrency with an in-memory fake DB.
"""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}")


class FakeCursor:
    def __init__(self, store: dict[str, list[dict[str, Any]]]):
        self.store = store
        self._result: list[dict[str, Any]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> None:
        q = " ".join(str(sql).lower().split())
        params = tuple(params or ())
        self._result = []
        self.rowcount = 0
        if "from employees" in q and "phone = any" in q:
            company, aliases, keys = params[0], list(params[1]), list(params[2])
            exclude = params[3] if len(params) > 3 and "employee_key <>" in q else None
            rows = []
            for row in self.store.get("employees", []):
                if row.get("company_code") != company:
                    continue
                if exclude and row.get("employee_key") == exclude:
                    continue
                if row.get("phone") in aliases or row.get("employee_key") in keys:
                    rows.append(row)
            rows.sort(key=lambda r: r.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            self._result = rows[:1]
            return
        if "from employees" in q and "employee_key" in q and "company_code" in q and "phone = any" not in q and not q.startswith("update"):
            # SELECT * FROM employees WHERE company_code=%s AND employee_key=%s
            # or WHERE employee_key=%s AND company_code=%s
            a, b = params[0], params[1]
            rows = [
                r
                for r in self.store.get("employees", [])
                if (r.get("company_code") == a and r.get("employee_key") == b)
                or (r.get("employee_key") == a and r.get("company_code") == b)
            ]
            self._result = rows[:1]
            return
        if q.startswith("insert into employees") and "on conflict" in q:
            # create_company_employee insert
            (
                employee_key,
                phone,
                company,
                name,
                email,
                title,
                start_date,
                _profile,
                _raw,
            ) = params
            existing = next((r for r in self.store["employees"] if r["employee_key"] == employee_key), None)
            if existing:
                self._result = []
                self.rowcount = 0
                return
            row = {
                "employee_key": employee_key,
                "phone": phone,
                "company_code": company,
                "name": name,
                "email": email,
                "position_title": title,
                "start_date": start_date,
                "profile": {},
                "raw_json": {"source": "dashboard_roster"},
                "employment_status": "active",
                "onboarding_status": "not_started",
                "updated_at": datetime.now(timezone.utc),
            }
            self.store["employees"].append(row)
            self._result = [row]
            self.rowcount = 1
            return
        if q.startswith("update employees set") and "where employee_key=%s and company_code=%s" in q:
            # parse set columns from sql roughly via params ending
            # params = values... + employee_key + company [+ expected_updated_at]
            if "and updated_at=%s" in q:
                expected = params[-1]
                employee_key, company = params[-3], params[-2]
                values = params[:-3]
            else:
                expected = None
                employee_key, company = params[-2], params[-1]
                values = params[:-2]
            cols = []
            # Extract "col=%s" tokens between SET and WHERE
            set_part = q.split("set", 1)[1].split("where", 1)[0]
            for token in set_part.split(","):
                token = token.strip()
                if token.endswith("=%s"):
                    cols.append(token.split("=", 1)[0].strip())
                elif token.startswith("updated_at"):
                    cols.append("updated_at")
            row = next(
                (
                    r
                    for r in self.store["employees"]
                    if r.get("employee_key") == employee_key and r.get("company_code") == company
                ),
                None,
            )
            if not row:
                self._result = []
                return
            if expected is not None and row.get("updated_at") != expected:
                self._result = []
                return
            value_idx = 0
            for col in cols:
                if col == "updated_at":
                    row["updated_at"] = datetime.now(timezone.utc)
                    continue
                row[col] = values[value_idx]
                value_idx += 1
            self._result = [deepcopy(row)]
            self.rowcount = 1
            return
        if "to_regclass" in q:
            self._result = [{"reg": "public.x"}]
            return
        if "count(*)" in q:
            self._result = [{"orphans": 0}]
            return
        # default no-op
        self._result = []

    def fetchone(self) -> dict[str, Any] | None:
        return deepcopy(self._result[0]) if self._result else None

    def fetchall(self) -> list[dict[str, Any]]:
        return deepcopy(self._result)


class FakeConn:
    def __init__(self, store: dict[str, list[dict[str, Any]]]):
        self.store = store

    def cursor(self):
        @contextmanager
        def _cm():
            yield FakeCursor(self.store)

        return _cm()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "test")
    root = Path(__file__).resolve().parents[3] / "wathefni-orchestrator"
    # When placed under ops/evidence/.../verify, parents[3] is repo root.
    if not (root / "app.py").exists():
        root = Path(__file__).resolve().parents[1]
        if not (root / "app.py").exists():
            # evidence/verify → repo/wathefni-orchestrator
            root = Path("/Users/azizalmulla/Desktop/claw/wathefni-orchestrator")
    sys.path.insert(0, str(root))
    import app

    store: dict[str, list[dict[str, Any]]] = {"employees": []}

    @contextmanager
    def fake_db_connect():
        yield FakeConn(store)

    app.db_connect = fake_db_connect  # type: ignore[assignment]
    app.company_has_module = lambda company, module: True  # type: ignore[assignment]
    app.onboarding_seed_enabled = lambda: False  # type: ignore[assignment]
    app.dashboard_context_has_permission = lambda context, perm: perm in (context.get("permissions") or [])  # type: ignore[assignment]

    # --- canary pure ---
    prev = {k: os.environ.get(k) for k in (
        "WATHEFNI_ENV",
        "WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES",
        "WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS",
    )}
    try:
        os.environ["WATHEFNI_ENV"] = "staging"
        os.environ.pop("WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES", None)
        os.environ.pop("WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS", None)
        check("canary WATHEFNI+staging allowed", app.employee_status_canary_allowed("WATHEFNI") is True)
        os.environ["WATHEFNI_ENV"] = "production"
        check("canary WATHEFNI+production denied default", app.employee_status_canary_allowed("WATHEFNI") is False)
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS"] = "production"
        check("canary production allowed when listed", app.employee_status_canary_allowed("WATHEFNI") is True)
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = ""
        check("empty company allowlist fails closed", app.employee_status_canary_allowed("WATHEFNI") is False)
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = "WATHEFNI"
        os.environ["WATHEFNI_ENV"] = "test"
        check("external company denied", app.employee_status_canary_allowed("ACMECO") is False)
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.setdefault("WATHEFNI_ENV", "test")

    # --- phone aliases ---
    check("canonical 8→965", app.canonical_employee_phone("51234567") == "96551234567")
    check(
        "alias bidirectional",
        set(app.employee_phone_alias_list("96551234567")) == {"51234567", "96551234567"},
    )

    company = "WATHEFNI"
    created = app.create_company_employee(company, name="Alias Person", phone="51234567")
    check("create canonicalizes phone", created.get("status") == "created" and created.get("employee_key") == f"{company}-96551234567")
    found_local = app.find_employee_by_phone("51234567", company_code=company)
    found_965 = app.find_employee_by_phone("96551234567", company_code=company)
    check("lookup local alias", bool(found_local) and found_local["employee_key"] == created["employee_key"])
    check("lookup 965 alias", bool(found_965) and found_965["employee_key"] == created["employee_key"])

    dup = app.create_company_employee(company, name="Dup Person", phone="96551234567")
    check("duplicate create blocked", dup.get("status") == "exists")

    # legacy local-key row collision
    store["employees"] = [{
        "employee_key": f"{company}-51239999",
        "phone": "51239999",
        "company_code": company,
        "name": "Legacy Local",
        "profile": {},
        "raw_json": {},
        "updated_at": datetime.now(timezone.utc),
        "employment_status": "active",
        "onboarding_status": "not_started",
    }]
    blocked = app.create_company_employee(company, name="Should Block", phone="96551239999")
    check("alias collision blocks create", blocked.get("status") == "exists" and blocked.get("identity_collision") is True)

    # --- concurrency ---
    now = datetime.now(timezone.utc)
    key = f"{company}-96551112222"
    store["employees"] = [{
        "employee_key": key,
        "phone": "96551112222",
        "company_code": company,
        "name": "Concurrency",
        "position_title": "A",
        "profile": {},
        "raw_json": {},
        "updated_at": now,
        "employment_status": "active",
        "onboarding_status": "not_started",
    }]
    stale = app.update_company_employee(company, key, fields={"position_title": "B"}, expected_updated_at=now - timedelta(seconds=5))
    check("stale edit conflicts", stale.get("status") == "conflict")
    fresh = app.update_company_employee(company, key, fields={"position_title": "B"}, expected_updated_at=now)
    check("fresh edit updates", fresh.get("status") == "updated" and (fresh.get("employee") or {}).get("position_title") == "B")

    # phone alias duplicate on edit
    store["employees"].append({
        "employee_key": f"{company}-96553334444",
        "phone": "96553334444",
        "company_code": company,
        "name": "Other",
        "profile": {},
        "raw_json": {},
        "updated_at": datetime.now(timezone.utc),
        "employment_status": "active",
        "onboarding_status": "not_started",
    })
    phone_dup = app.update_company_employee(company, key, fields={"phone": "53334444"})
    check("phone alias edit duplicate", phone_dup.get("status") == "duplicate")

    # --- manager scope denial ---
    audits: list[dict[str, Any]] = []
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k})  # type: ignore[assignment]
    app.manager_scope_context = lambda *a, **k: {  # type: ignore[assignment]
        "restricted": True,
        "branch_keys": [],
        "team_keys": [],
        "direct_employee_keys": [f"{company}-other"],
    }
    store["employees"] = [{
        "employee_key": key,
        "phone": "96551112222",
        "company_code": company,
        "name": "Scoped",
        "profile": {},
        "raw_json": {},
        "updated_at": now,
        "employment_status": "active",
        "onboarding_status": "not_started",
    }]
    ctx = {
        "company_code": company,
        "permissions": ["employees.manage"],
        "actor_user_id": "u1",
        "actor_role": "manager",
        "hr_phone": "999",
        "hr_user": {"role": "manager", "status": "active", "company_code": company},
        "permission_authority": "backend_current",
        "permission_subject_user_id": "u1",
        "permission_subject_company": company,
        "access": {"role": "manager", "permissions": ["employees.manage"]},
    }
    try:
        app.dashboard_posthire_update_employee(
            employee_key=key,
            request=app.DashboardEmployeeUpdate(position_title="Nope", expected_updated_at=now),
            context=ctx,
        )
        check("scoped PATCH denied", False)
    except app.HTTPException as exc:
        check("scoped PATCH denied 404", exc.status_code == 404)
    check(
        "scoped PATCH denial audited",
        any(a["action_type"] == "employee_mutation_denied" for a in audits),
    )

    # integrity table expansion (static)
    names = {spec["table"] for spec in app.INTEGRITY_SCAN_SPECS}
    needed = {
        "employee_messages",
        "employee_sessions",
        "file_registry",
        "onboarding_items",
        "employee_status_changes",
        "employee_org_assignments",
    }
    check("integrity specs expanded", needed.issubset(names))

    # source markers
    source = (root / "app.py").read_text(encoding="utf-8")
    hire = (root / "hire_operations.py").read_text(encoding="utf-8")
    check("hire uses canonical_employee_phone", "canonical_employee_phone" in hire)
    check("hire uses phone_identity_candidates", "phone_identity_candidates" in hire)
    check("canary gate present", "employee_status_canary_allowed" in source)
    check("mutation scope helper present", "require_employee_mutation_scope" in source)
    check("orphan doc restricted path present", "manager_scope_or_orphan" in source)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
