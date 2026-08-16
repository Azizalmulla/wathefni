#!/usr/bin/env python3
"""Surgical held-communication authority patch for staging offer_service.py."""
from __future__ import annotations

import pathlib
import sys

MARKER = "HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH"

GATE = f'''
    # Fail-closed: held/restricted Talent Pool records cannot receive offer delivery.
    application = None
    if hasattr(legacy, "find_application_by_key"):
        application = legacy.find_application_by_key(str(offer.get("app_key") or ""), company_code=company)
    if hasattr(legacy, "assert_application_communication_allowed"):
        try:
            legacy.assert_application_communication_allowed(
                application,
                kind="offer",
                expected_company_code=company,
            )  # {MARKER}
        except Exception as exc:
            code = getattr(exc, "code", None) or "held_record_communication_forbidden"
            message = getattr(exc, "message", None) or str(exc) or "Offer cannot be sent for this application."
            status_code = int(getattr(exc, "status_code", 409) or 409)
            raise offers.OfferAuthorityError(code, message, status_code=status_code) from exc
    elif application is None:
        raise offers.OfferAuthorityError(
            "candidate_communication_requires_live_application",
            "A live Job application is required before sending an offer.",
            status_code=409,
        )
'''


def patch(src: str) -> str:
    if MARKER in src and "assert_application_communication_allowed" in src:
        return src

    # Staging send_offer claims a delivery operation early. Gate before claim using offer lookup.
    # Insert after company = _company(...) and before operation claim, loading the offer first.
    old = '''    offers.require_human_actor(actor_type)
    company = _company(company_code)
    operation_kind = "resend" if resend else "send"
'''
    new = f'''    offers.require_human_actor(actor_type)
    company = _company(company_code)
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
{GATE}
    operation_kind = "resend" if resend else "send"
'''
    if old not in src:
        raise RuntimeError("send_offer anchor missing")
    src = src.replace(old, new, 1)
    if MARKER not in src:
        raise RuntimeError("offer held authority patch failed")
    return src


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch-staging-offer-held-notify-authority.py <in> <out>", file=sys.stderr)
        return 2
    inp, outp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    patched = patch(inp.read_text(encoding="utf-8"))
    import ast

    ast.parse(patched)
    outp.write_text(patched, encoding="utf-8")
    print(f"patched {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
