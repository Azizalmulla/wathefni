"""Smoke: Phase 7D company channel account routing (pure, no DB/network)."""

from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"      FAIL  {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("    channel account routing — flag/audience/fallback")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import channel_account_routing as routing

    shared = routing.resolve_outbound_whatsapp_route(
        flag_enabled=False,
        company_code="P7DSTG01",
        audience="candidate",
        account={"status": "active", "provider_account_id": "wa-co-a", "audiences": ["candidate"]},
        known_provider_account_ids={"wa-co-a", "default"},
    )
    check("flag OFF always shared", shared["source"] == "shared_default" and shared["runtime_routing_changed"] is False)

    pending = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="candidate",
        account={"status": "pending_verification", "provider_account_id": "wa-co-a", "audiences": ["candidate"]},
        known_provider_account_ids={"wa-co-a", "default"},
    )
    check("pending cannot hijack", pending["source"] == "fallback_shared" and pending["reason"] == "account_status_pending_verification")

    disabled = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="candidate",
        account={"status": "disabled", "provider_account_id": "wa-co-a", "audiences": ["candidate"]},
        known_provider_account_ids={"wa-co-a", "default"},
    )
    check("disabled falls back shared", disabled["source"] == "fallback_shared")

    cand_only = {
        "status": "active",
        "provider_account_id": "wa-co-a",
        "audiences": ["candidate"],
    }
    ok_cand = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="candidate",
        account=cand_only,
        known_provider_account_ids={"wa-co-a", "default"},
    )
    bad_emp = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="employee",
        account=cand_only,
        known_provider_account_ids={"wa-co-a", "default"},
    )
    check("candidate audience permitted", ok_cand["source"] == "company_owned" and ok_cand["account_id"] == "wa-co-a")
    check("employee blocked on candidate-only", bad_emp["reason"] == "audience_not_permitted" and bad_emp["account_id"] == "default")

    unknown = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="candidate",
        account=cand_only,
        known_provider_account_ids={"default"},
    )
    check("unknown provider id fail-closed", unknown["reason"] == "provider_account_not_in_sender_config")

    other = routing.resolve_outbound_whatsapp_route(
        flag_enabled=True,
        company_code="P7DSTG01",
        audience="candidate",
        account={"status": "active", "provider_account_id": "wa-co-b", "audiences": ["candidate"]},
        known_provider_account_ids={"wa-co-a", "wa-co-b", "default"},
    )
    check("company A never selects B's id from its own row", other["account_id"] == "wa-co-b")

    inbound_off = routing.resolve_inbound_company_from_account(
        flag_enabled=False,
        provider="octopus",
        provider_account_id="wa-co-a",
        lookup=lambda _p, _a: {"company_code": "P7DSTG01", "status": "active"},
    )
    check("inbound flag OFF ignores map", inbound_off["company_code"] is None and inbound_off["reason"] == "flag_off")

    inbound_on = routing.resolve_inbound_company_from_account(
        flag_enabled=True,
        provider="octopus",
        provider_account_id="wa-co-a",
        lookup=lambda _p, _a: {"company_code": "P7DSTG01", "status": "active"},
    )
    check("inbound flag ON maps company", inbound_on["company_code"] == "P7DSTG01" and inbound_on["runtime_routing_changed"] is True)

    inbound_pending = routing.resolve_inbound_company_from_account(
        flag_enabled=True,
        provider="octopus",
        provider_account_id="wa-co-a",
        lookup=lambda _p, _a: {"company_code": "P7DSTG01", "status": "pending_verification"},
    )
    check("inbound pending does not map", inbound_pending["company_code"] is None)

    print(f"    channel routing smoke: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
