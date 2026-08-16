#!/usr/bin/env python3
"""Wave 1 — Preboarding authority unit smoke (no DB required).

Pins SM, readiness derivation, Kuwait template, flags, wiring, no UI.
Run: python3 smoke-test-preboarding-wave1.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    preboarding wave1 — SM + readiness + template + flags")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import preboarding as pb

    check("schema version pinned", pb.PREBOARDING_SCHEMA_VERSION == "1.0.0")
    check("sql pack exists", pb._SCHEMA.is_file())

    check("asn not_started→in_progress", pb.can_transition_assignment("not_started", "in_progress"))
    check("asn in_progress→ready", pb.can_transition_assignment("in_progress", "ready"))
    check("asn in_progress→blocked", pb.can_transition_assignment("in_progress", "blocked"))
    check("asn ready→converted", pb.can_transition_assignment("ready", "converted"))
    check("asn →cancelled", pb.can_transition_assignment("in_progress", "cancelled"))
    check("asn converted terminal", not pb.can_transition_assignment("converted", "ready"))
    check("item pending→done", pb.can_transition_item("pending", "done"))
    check("item done terminal", not pb.can_transition_item("done", "pending"))

    items = [
        {"item_key": "a", "required": True, "status": "done", "depends_on": []},
        {"item_key": "b", "required": True, "status": "pending", "depends_on": ["a"]},
        {"item_key": "c", "required": False, "status": "pending", "depends_on": []},
    ]
    r = pb.compute_readiness(items)
    check("readiness incomplete when required pending", r["ready"] is False, r)
    check("percent partial", r["percent"] == 50, r)

    items[1]["status"] = "done"
    r2 = pb.compute_readiness(items)
    check("readiness derived when required done", r2["ready"] is True, r2)
    check("blockers empty when ready", r2["blockers"] == [], r2)

    blocked = [
        {"item_key": "a", "required": True, "status": "blocked", "blocker_reason": "missing", "depends_on": []},
        {"item_key": "b", "required": True, "status": "done", "depends_on": []},
    ]
    rb = pb.compute_readiness(blocked)
    check("blocked when required item blocked", rb["blocked"] is True and rb["ready"] is False, rb)

    tmpl = pb.default_kuwait_preboard_items()
    keys = {i["item_key"] for i in tmpl}
    for need in (
        "civil_id",
        "passport",
        "residence",
        "work_permit",
        "employment_contract",
        "company_policy_ack",
        "bank_details",
        "equipment",
        "it_system_access",
        "workspace_site_ready",
        "manager_preparation",
        "employee_prejoin_actions",
        "welcome_reminder_comms",
    ):
        check(f"kuwait template has {need}", need in keys)
    bank = next(i for i in tmpl if i["item_key"] == "bank_details")
    check("bank is ESS-safe (no plaintext)", bool((bank.get("metadata") or {}).get("no_plaintext_iban")))

    prev = os.environ.pop("WATHEFNI_PREBOARDING", None)
    prev_c = os.environ.pop("WATHEFNI_PREBOARDING_COMPANIES", None)
    try:
        check("runtime flag default off", pb.preboarding_runtime_flag_on() is False)
        os.environ["WATHEFNI_PREBOARDING"] = "on"
        check("runtime flag on", pb.preboarding_runtime_flag_on() is True)
        os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = "Acme, beta"
        check("allowlist normalizes", pb.preboarding_company_allowlist() == {"ACME", "BETA"})
    finally:
        if prev is None:
            os.environ.pop("WATHEFNI_PREBOARDING", None)
        else:
            os.environ["WATHEFNI_PREBOARDING"] = prev
        if prev_c is None:
            os.environ.pop("WATHEFNI_PREBOARDING_COMPANIES", None)
        else:
            os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = prev_c

    rb_guide = pb.rollback_guidance()
    check("rollback guidance", "WATHEFNI_PREBOARDING=off" in str(rb_guide.get("runtime")))

    scope_ok = pb.assert_actor_scope(
        assignment={"manager_user_id": "mgr-1"},
        actor_user_id="mgr-1",
        actor_role="manager",
        permission="preboarding.manage",
    )
    check("manager in scope", scope_ok.get("ok") is True)
    scope_bad = pb.assert_actor_scope(
        assignment={"manager_user_id": "mgr-1"},
        actor_user_id="mgr-2",
        actor_role="manager",
        permission="preboarding.manage",
    )
    check("manager out of scope denied", scope_bad.get("ok") is False)

    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check("app.ensure_schema wires preboarding", "ensure_preboarding_schema" in app_src)

    freeze = orch.parent / "ops" / "REQUISITIONS_WAVE1_BACKEND_FREEZE.md"
    check("requisitions freeze doc present", freeze.is_file())

    dash = orch.parent / "apps" / "wathefni-dashboard" / "src"
    ui_hits = []
    if dash.is_dir():
        for p in dash.rglob("*Preboard*.tsx"):
            ui_hits.append(str(p))
    check("no Preboarding UI page this slice", ui_hits == [], ui_hits)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("PREBOARDING_WAVE1_UNIT_FAIL")
        return 1
    print("PREBOARDING_WAVE1_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
