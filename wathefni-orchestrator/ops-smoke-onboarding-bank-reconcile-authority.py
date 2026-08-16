#!/usr/bin/env python3
"""Regression smoke: the Bank ESS → onboarding reconciliation authority order.

The live failure this guards against: an employee had an old `rejected` bank
request and a newer `applied` one. The reconciler ranked request states by a
hand-written CASE list where `applied` fell into `ELSE 9`, below `rejected` (6).
Every HR drawer read therefore re-selected the stale rejection, reverted
`bank_details` from accepted to replacement_required, and dropped the canonical
completion back to 3/4 with a wrong "Payroll" owner.

Cases proven here:
  1. applied + older rejected      → accepted, completion completed
  2. open needs_information        → replacement_required with THAT request's reason
  3. open review + older rejected  → processing (Needs HR), reason cleared
  4. reconcile is idempotent       → a read never rewrites an already-correct row
  5. live effective bank, no open  → accepted even with no applied request row
  6. canonical next owner          → employee when bank needs correction, not payroll

Run on the orchestrator host with the service environment loaded.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

COMPANY = "WATHEFNI"
SYNTH_PHONE_PREFIX = "9999"
RESULTS: dict[str, Any] = {"cases": [], "failed": 0, "created": []}


def check(case: str, ok: bool, detail: Any = None) -> bool:
    RESULTS["cases"].append({"case": case, "status": "proven" if ok else "FAILED", "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(f"{'PASS' if ok else 'FAIL'} {case}" + (f" :: {json.dumps(detail, default=str)}" if detail else ""))
    return ok


def make_employee(app: Any, suffix: str) -> str:
    phone = f"{SYNTH_PHONE_PREFIX}{suffix}"
    key = f"{COMPANY}-{phone}"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name,
                                       onboarding_status, employment_status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,now(),now())
                ON CONFLICT (employee_key) DO UPDATE SET updated_at=now()
                """,
                (COMPANY, key, phone, f"SYNTH-RECONCILE-{suffix}", "in_progress", "active"),
            )
            # One required employee doc plus the ESS-owned bank row: enough to make
            # completion meaningful without touching real templates.
            for item_id, required, owner, authority, mode in (
                ("recon_doc", True, "employee", "onboarding", "document"),
                ("bank_details", True, "employee", "ess", "ess_encrypted"),
            ):
                cur.execute(
                    """
                    INSERT INTO onboarding_items (
                      employee_key, item_id, label, status, required, owner,
                      item_type, collection_mode, authority, depends_on, created_at, updated_at
                    ) VALUES (%s,%s,%s,'pending',%s,%s,%s,%s,%s,'[]'::jsonb,now(),now())
                    ON CONFLICT (employee_key, item_id) DO UPDATE
                    SET status='pending', rejection_reason=NULL, required=EXCLUDED.required,
                        authority=EXCLUDED.authority, collection_mode=EXCLUDED.collection_mode,
                        updated_at=now()
                    """,
                    (key, item_id, f"Recon {item_id}", required, owner, "document", mode, authority),
                )
        conn.commit()
    RESULTS["created"].append(key)
    return key


def add_request(app: Any, key: str, *, state: str, minutes_ago: int, reason: str | None = None) -> str:
    """Insert one bank request row directly: this smoke tests selection, not the
    state machine, so history is seeded rather than replayed."""
    request_id = str(uuid.uuid4())
    comments = (
        [{"at": "2026-01-01T00:00:00+00:00", "by": "smoke", "text": reason, "action": "reject"}]
        if reason
        else []
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee_ess_requests (
                  request_id, company_code, employee_key, request_type, state, requester_kind,
                  proposed_values, comments, idempotency_key, request_hash, created_at, updated_at
                ) VALUES (%s,%s,%s,'bank_detail_change',%s,'employee','{}'::jsonb,%s::jsonb,%s,%s,
                          now() - (%s || ' minutes')::interval, now() - (%s || ' minutes')::interval)
                """,
                (
                    request_id, COMPANY, key, state,
                    json.dumps(comments), f"smoke-{request_id}", f"hash-{request_id}",
                    str(minutes_ago), str(minutes_ago),
                ),
            )
        conn.commit()
    return request_id


def add_effective(app: Any, key: str, request_id: str) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee_bank_effective (
                  company_code, employee_key, request_id, fingerprint, display,
                  bank_profile_version, effective_from, created_at
                ) VALUES (%s,%s,%s,%s,%s::jsonb,1,current_date,now())
                """,
                (COMPANY, key, request_id, "smokefingerprint01", json.dumps({"iban_last4": "0000"})),
            )
        conn.commit()


def bank_item(app: Any, key: str) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, rejection_reason, updated_at FROM onboarding_items"
                " WHERE employee_key=%s AND item_id='bank_details'",
                (key,),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def reconcile(app: Any, bank: Any, key: str) -> dict[str, Any] | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            out = bank.reconcile_onboarding_bank_item(cur, company_code=COMPANY, employee_key=key)
        conn.commit()
    return out


def cleanup(app: Any) -> None:
    if not RESULTS["created"]:
        return
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table, col in (
                ("employee_bank_effective", "employee_key"),
                ("employee_ess_requests", "employee_key"),
                ("onboarding_items", "employee_key"),
                ("employee_onboarding_completion", "employee_key"),
                ("employees", "employee_key"),
            ):
                cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (RESULTS["created"],))
        conn.commit()


def main() -> int:
    import app as A
    import employee_bank_ess as bank
    import onboarding_completion_contract as C

    try:
        # --- 1 + 4: applied outranks older rejected, and reconcile is idempotent
        key = make_employee(A, "01")
        add_request(A, key, state="rejected", minutes_ago=60, reason="Old rejection that must not win.")
        applied_id = add_request(A, key, state="applied", minutes_ago=10)
        add_effective(A, key, applied_id)
        # Start from the wrong state the live bug produced.
        with A.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE onboarding_items SET status='replacement_required',"
                    " rejection_reason='Old rejection that must not win.'"
                    " WHERE employee_key=%s AND item_id='bank_details'",
                    (key,),
                )
            conn.commit()
        first = reconcile(A, bank, key)
        item = bank_item(A, key)
        check(
            "applied outranks an older rejected request",
            item.get("status") == "accepted" and not item.get("rejection_reason"),
            item,
        )
        check("reconcile reports the applied request", (first or {}).get("state") == "applied", first)
        stamp = item.get("updated_at")
        second = reconcile(A, bank, key)
        check(
            "a second reconcile does not rewrite an already-correct row",
            (second or {}).get("changed") is False and bank_item(A, key).get("updated_at") == stamp,
            second,
        )
        # Bank satisfied + the other required doc still open → waiting on employee.
        emp = A.find_employee_by_key(key, company_code=COMPANY)
        summary = A.employee_onboarding_summary(emp, company_code=COMPANY)
        check(
            "bank counts as satisfied in canonical completion",
            summary["completion"]["satisfied_count"] == 1
            and summary["completion"]["required_total"] == 2
            and "bank_details" in summary["completion"]["satisfied_items"],
            {k: summary["completion"][k] for k in ("state", "satisfied_count", "required_total")},
        )

        # Everything satisfied → completed. Go through the lifecycle writer so the
        # persisted contract is refreshed the way real transitions refresh it.
        import onboarding_lifecycle_wave2a as _lc

        with A.db_connect() as conn:
            with conn.cursor() as cur:
                _lc.set_item_lifecycle(
                    cur, employee_key=key, item_id="recon_doc",
                    new_status=_lc.STATE_ACCEPTED, clear_rejection=True,
                )
                _lc.sync_completion_contract(cur, employee_key=key, actor="smoke")
            conn.commit()
        summary = A.employee_onboarding_summary(A.find_employee_by_key(key, company_code=COMPANY), company_code=COMPANY)
        check(
            "one Apply completes onboarding with no second action",
            summary["completion"]["state"] == "completed" and summary["next_owner"] is None,
            {"state": summary["completion"]["state"], "next_owner": summary["next_owner"]},
        )

        # --- 2 + 6: an open correction owns the item, and the employee owns it
        key2 = make_employee(A, "02")
        add_request(A, key2, state="rejected", minutes_ago=90, reason="Stale reason from a dead request.")
        add_request(A, key2, state="needs_information", minutes_ago=5, reason="Fix the account holder name.")
        reconcile(A, bank, key2)
        item2 = bank_item(A, key2)
        check(
            "an open correction request owns the item and its reason",
            item2.get("status") == "replacement_required"
            and item2.get("rejection_reason") == "Fix the account holder name.",
            item2,
        )
        enrich = A.onboarding_queue_enrichment(COMPANY, [key2]).get(key2) or {}
        check(
            "queue next owner is the employee, not the payroll rail",
            enrich.get("next_owner") == "employee" and enrich.get("next_owner_group") == "employee",
            {k: enrich.get(k) for k in ("next_owner", "next_owner_group", "completion_state", "next_item_label")},
        )
        check(
            "queue completion state matches the contract",
            enrich.get("completion_state") == "waiting_on_employee",
            enrich.get("completion_state"),
        )

        # --- 3: an open review outranks older terminal history. The other required
        # doc is closed first so bank is the only open item and therefore the one
        # the queue must name.
        key3 = make_employee(A, "03")
        with A.db_connect() as conn:
            with conn.cursor() as cur:
                _lc.set_item_lifecycle(
                    cur, employee_key=key3, item_id="recon_doc",
                    new_status=_lc.STATE_ACCEPTED, clear_rejection=True,
                )
            conn.commit()
        add_request(A, key3, state="rejected", minutes_ago=120, reason="Older rejection.")
        add_request(A, key3, state="pending_hr", minutes_ago=2)
        reconcile(A, bank, key3)
        item3 = bank_item(A, key3)
        check(
            "an open review request shows Needs HR with no stale reason",
            item3.get("status") == "processing" and not item3.get("rejection_reason"),
            item3,
        )
        enrich3 = A.onboarding_queue_enrichment(COMPANY, [key3]).get(key3) or {}
        check(
            "queue owner for a bank request under review is HR",
            enrich3.get("next_owner") == "hr" and enrich3.get("completion_state") == "waiting_on_hr",
            {k: enrich3.get(k) for k in ("next_owner", "next_owner_group", "completion_state")},
        )

        # --- 5: the bank of record alone satisfies the item
        key4 = make_employee(A, "04")
        withdrawn = add_request(A, key4, state="withdrawn", minutes_ago=30)
        add_effective(A, key4, withdrawn)
        reconcile(A, bank, key4)
        check(
            "a live effective bank record satisfies the item without an applied row",
            bank_item(A, key4).get("status") == "accepted",
            bank_item(A, key4),
        )

        # --- no request at all must not invent a state
        key5 = make_employee(A, "05")
        out5 = reconcile(A, bank, key5)
        check(
            "no bank request leaves the checklist untouched",
            out5 is None and bank_item(A, key5).get("status") == "pending",
            {"reconcile": out5, "item": bank_item(A, key5)},
        )

        with A.db_connect() as conn:
            with conn.cursor() as cur:
                row = C.load_completion_row(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        check(
            "persisted completion agrees with the computed snapshot",
            (row or {}).get("state") == "completed",
            (row or {}).get("state"),
        )

        # --- one owner per snapshot, whatever the state.
        # `reopened` used to hardcode "employee", so a bank change under review
        # made the queue say HR while the drawer and the app said employee.
        owner_cases = []
        for label, items in (
            (
                "reopened while HR reviews",
                [
                    {"item_id": "a", "required": True, "status": "accepted"},
                    {"item_id": "b", "required": True, "status": "processing", "owner": "payroll"},
                ],
            ),
            (
                "reopened while the employee corrects",
                [
                    {"item_id": "a", "required": True, "status": "accepted"},
                    {
                        "item_id": "b",
                        "required": True,
                        "status": "replacement_required",
                        "owner": "employee",
                    },
                ],
            ),
        ):
            snap = C.compute_completion(items, previously_completed=True)
            action = C.next_action(snap)
            chosen = C.select_next_item(items) or {}
            expected = A._RESPONSIBLE_TO_OWNER_GROUP.get(
                str(chosen.get("responsible_party") or "")
            ) or str(chosen.get("responsible_party") or "")
            owner_cases.append(
                {
                    "case": label,
                    "state": snap["state"],
                    "next_action_owner": action["owner"],
                    "next_item": chosen.get("item_id"),
                    "next_item_owner": expected,
                    "agrees": action["owner"] == expected,
                }
            )
        check(
            "next action owner and next item owner agree on every state",
            all(c["agrees"] for c in owner_cases),
            owner_cases,
        )
        check(
            "the named next item is required and open, never an optional one",
            (
                C.select_next_item(
                    [
                        {"item_id": "req", "required": True, "status": "processing"},
                        {"item_id": "opt", "required": False, "status": "pending", "owner": "employee"},
                    ]
                )
                or {}
            ).get("item_id")
            == "req",
        )
    finally:
        cleanup(A)

    print(json.dumps(RESULTS, indent=2, default=str))
    verdict = "RECONCILE_AUTHORITY_OK" if RESULTS["failed"] == 0 else "RECONCILE_AUTHORITY_FAILED"
    print(verdict)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
