#!/usr/bin/env python3
"""Hire-override audit hardening — fail closed, UUID + non-UUID actors, idempotency."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def check(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(label)
    print(f"  ok: {label}")


class FakeCursor:
    def __init__(self, *, fail_insert: bool = False, apps: dict[tuple[str, str], dict] | None = None):
        self.fail_insert = fail_insert
        self.apps = apps or {}
        self.audits: list[dict[str, Any]] = []
        self._last_sql = ""
        self._fetch: Any = None
        self.statements: list[str] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self._last_sql = sql
        self.statements.append(sql)
        params = params or ()
        sql_l = " ".join(sql.lower().split())

        if self.fail_insert and "insert into employment_offer_hire_override_audits" in sql_l:
            raise RuntimeError("simulated_audit_insert_failure")

        if "from applications" in sql_l and "where company_code=%s and app_key=%s" in sql_l:
            row = self.apps.get((str(params[0]).upper(), str(params[1])))
            self._fetch = row
            return

        if "from applications" in sql_l and "where app_key=%s" in sql_l:
            for (company, app_key), row in self.apps.items():
                if app_key == params[0]:
                    self._fetch = {"company_code": company}
                    return
            self._fetch = None
            return

        if "from employment_offers" in sql_l and "status='accepted'" in sql_l:
            self._fetch = None
            return

        if "from employment_offers" in sql_l and "status = any" in sql_l:
            self._fetch = None
            return

        if "from employment_offer_hire_override_audits" in sql_l and "select" in sql_l:
            company, idem, app_key, confirm = params[0], params[1], params[2], params[3]
            for row in self.audits:
                if row["company_code"] == company and (
                    row.get("idempotency_key") == idem
                    or (row.get("app_key") == app_key and row.get("confirmation_ref") == confirm)
                ):
                    self._fetch = row
                    return
            self._fetch = None
            return

        if "insert into employment_offer_hire_override_audits" in sql_l:
            row = {
                "audit_id": str(uuid.uuid4()),
                "company_code": params[0],
                "app_key": params[1],
                "actor_type": params[2],
                "actor_subject": params[3],
                "actor_user_id": params[4],
                "reason": params[5],
                "from_stage": params[6],
                "to_stage": params[7],
                "confirmation_ref": params[8],
                "no_accepted_offer": params[9],
                "idempotency_key": params[10],
                "metadata": {},
            }
            self.audits.append(row)
            self._fetch = row
            return

        self._fetch = None

    def fetchone(self) -> Any:
        return self._fetch

    def fetchall(self) -> list[Any]:
        return []


class FakeConn:
    def __init__(self, cur: FakeCursor):
        self.cur = cur
        self.committed = False

    def cursor(self):
        return _Ctx(self.cur)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Ctx:
    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self.cur

    def __exit__(self, *args):
        return False


def make_legacy(cur: FakeCursor) -> MagicMock:
    legacy = MagicMock()
    legacy.db_connect.return_value = FakeConn(cur)
    legacy.company_has_module.side_effect = lambda company, module: module == "employment_offers"
    return legacy


def main() -> None:
    import offer_lifecycle as offers
    import offer_service

    print("Offer hire-override audit hardening")

    company = "WATHEFNI"
    app_key = "APP-OVERRIDE-1"
    apps = {(company, app_key): {"app_key": app_key, "company_code": company, "status": "shortlisted"}}
    perms = {"offer.hire_override", "candidate.decide"}

    # --- UUID actor success ---
    cur = FakeCursor(apps=apps)
    legacy = make_legacy(cur)
    actor_uuid = str(uuid.uuid4())
    result = offer_service.enforce_hire_gate(
        legacy,
        company_code=company,
        app_key=app_key,
        permissions=perms,
        hire_override=True,
        override_reason="Must hire for critical coverage",
        actor_user_id=actor_uuid,
        actor_subject=actor_uuid,
        actor_type="human",
        confirmation_token="confirm-uuid-1",
        confirmed=True,
        expected_from_stage="shortlisted",
        idempotency_key="idem-uuid-1",
    )
    check(result.get("override") is True, "UUID actor override allowed")
    check(bool(result.get("audit_id")), "UUID actor audit_id returned")
    check(len(cur.audits) == 1, "UUID actor creates exactly one audit")
    check(cur.audits[0]["actor_subject"] == actor_uuid, "UUID actor subject preserved")
    check(cur.audits[0]["actor_user_id"] == actor_uuid, "UUID actor_user_id stored")
    check(cur.audits[0]["no_accepted_offer"] is True, "no_accepted_offer recorded true")
    check(cur.audits[0]["from_stage"] == "shortlisted", "previous stage recorded")
    check(cur.audits[0]["to_stage"] == "hired", "next stage recorded")
    check(cur.audits[0]["confirmation_ref"] == "confirm-uuid-1", "confirmation reference recorded")
    check(cur.audits[0]["reason"] == "Must hire for critical coverage", "reason recorded")

    # --- Non-UUID actor subject ---
    cur2 = FakeCursor(apps=apps)
    legacy2 = make_legacy(cur2)
    result2 = offer_service.enforce_hire_gate(
        legacy2,
        company_code=company,
        app_key=app_key,
        permissions=perms,
        hire_override=True,
        override_reason="Non UUID subject path",
        actor_user_id=None,
        actor_subject="dashboard:owner@wathefni.test",
        actor_type="human",
        confirmation_token="confirm-nonuuid-1",
        confirmed=True,
    )
    check(result2.get("override") is True, "non-UUID actor override allowed")
    check(cur2.audits[0]["actor_subject"] == "dashboard:owner@wathefni.test", "non-UUID subject preserved")
    check(cur2.audits[0]["actor_user_id"] is None, "non-UUID leaves actor_user_id null when not provided")
    check(cur2.audits[0]["actor_type"] == "human", "actor type human preserved")

    # --- Missing reason ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps)),
            company_code=company,
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="   ",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-reason",
            confirmed=True,
        )
        raise AssertionError("missing reason should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "override_reason_required", "missing reason rejected")

    # --- Missing permission ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps)),
            company_code=company,
            app_key=app_key,
            permissions={"candidate.decide"},
            hire_override=True,
            override_reason="Has reason but no grant",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-perm",
            confirmed=True,
        )
        raise AssertionError("missing permission should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "permission_denied", "missing permission rejected")

    # --- Missing confirmation ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps)),
            company_code=company,
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="Confirmed? No",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-noconfirm",
            confirmed=False,
        )
        raise AssertionError("missing confirm should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "override_confirm_required", "missing confirmation rejected")

    # --- AI forbidden ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps)),
            company_code=company,
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="AI must not override",
            actor_subject="assistant",
            actor_type="ai",
            confirmation_token="c-ai",
            confirmed=True,
        )
        raise AssertionError("AI should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "ai_forbidden", "AI override rejected")

    # --- Audit insert failure → fail closed, no successful override ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps, fail_insert=True)),
            company_code=company,
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="Audit will fail",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-fail",
            confirmed=True,
        )
        raise AssertionError("audit failure should fail closed")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "override_audit_failed", "audit insert failure fail-closed")

    # --- Stale application state ---
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=apps)),
            company_code=company,
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="Stale expected stage",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-stale",
            confirmed=True,
            expected_from_stage="interview",
        )
        raise AssertionError("stale should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "stale_application", "stale application state rejected")

    # --- Invalid hire stage ---
    bad_apps = {(company, "APP-BAD"): {"app_key": "APP-BAD", "company_code": company, "status": "ready_for_review"}}
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=bad_apps)),
            company_code=company,
            app_key="APP-BAD",
            permissions=perms,
            hire_override=True,
            override_reason="Wrong stage",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-stage",
            confirmed=True,
        )
        raise AssertionError("invalid stage should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "invalid_hire_stage", "invalid application stage rejected")

    # --- Tenant mismatch ---
    other = {(company, app_key): {"app_key": app_key, "company_code": company, "status": "shortlisted"}}
    # app exists only under WATHEFNI; querying OTHERCO triggers mismatch via app_key lookup
    try:
        offer_service.enforce_hire_gate(
            make_legacy(FakeCursor(apps=other)),
            company_code="OTHERCO",
            app_key=app_key,
            permissions=perms,
            hire_override=True,
            override_reason="Wrong tenant",
            actor_subject="user-1",
            actor_type="human",
            confirmation_token="c-tenant",
            confirmed=True,
        )
        raise AssertionError("tenant mismatch should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "tenant_mismatch", "tenant mismatch rejected")

    # --- Idempotent retry creates exactly one audit ---
    cur_idem = FakeCursor(apps=apps)
    legacy_idem = make_legacy(cur_idem)
    first = offer_service.enforce_hire_gate(
        legacy_idem,
        company_code=company,
        app_key=app_key,
        permissions=perms,
        hire_override=True,
        override_reason="Idempotent override",
        actor_subject="user-retry",
        actor_type="human",
        confirmation_token="confirm-retry-1",
        confirmed=True,
        idempotency_key="idem-retry-1",
    )
    second = offer_service.enforce_hire_gate(
        legacy_idem,
        company_code=company,
        app_key=app_key,
        permissions=perms,
        hire_override=True,
        override_reason="Idempotent override",
        actor_subject="user-retry",
        actor_type="human",
        confirmation_token="confirm-retry-1",
        confirmed=True,
        idempotency_key="idem-retry-1",
    )
    check(len(cur_idem.audits) == 1, "retry/idempotency creates exactly one audit")
    check(first.get("audit_id") == second.get("audit_id"), "retry returns same audit_id")
    check(second.get("idempotent_replay") is True, "retry marked idempotent_replay")

    # --- Accepted offer path does not require override audit ---
    cur_acc = FakeCursor(apps=apps)

    def _accepted_execute(sql, params=None):
        FakeCursor.execute(cur_acc, sql, params)
        sql_l = " ".join(sql.lower().split())
        if "from employment_offers" in sql_l and "status='accepted'" in sql_l:
            cur_acc._fetch = {
                "offer_id": str(uuid.uuid4()),
                "accepted_version": 2,
                "current_version": 2,
            }

    cur_acc.execute = _accepted_execute  # type: ignore[method-assign]
    gate_acc = offer_service.enforce_hire_gate(
        make_legacy(cur_acc),
        company_code=company,
        app_key=app_key,
        permissions={"candidate.decide"},
        hire_override=False,
        actor_subject="user-1",
        actor_type="human",
    )
    check(gate_acc.get("override") is False, "accepted-offer path does not use override")
    check(gate_acc.get("offer_id"), "accepted-offer path returns offer_id")
    check(len(cur_acc.audits) == 0, "accepted-offer path writes no override audit")

    # Schema includes durable audit table
    schema_cur = FakeCursor()
    offers.ensure_offer_schema(schema_cur)
    joined = "\n".join(schema_cur.statements)
    check("employment_offer_hire_override_audits" in joined, "schema creates hire_override audit table")

    print("Offer hire-override audit hardening passed")


if __name__ == "__main__":
    main()
