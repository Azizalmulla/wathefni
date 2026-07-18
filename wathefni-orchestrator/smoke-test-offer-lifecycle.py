#!/usr/bin/env python3
"""Offer-1 smoke: schema, authority, versioning, hire gate, AI forbidden."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def check(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(label)
    print(f"  ok: {label}")


def main() -> None:
    import offer_lifecycle as offers
    import offer_service
    import module_catalog

    print("Offer-1 authority + schema contract")

    check("employment_offers" in module_catalog.MODULE_KEYS, "employment_offers module catalogued")
    check(
        module_catalog.MODULE_BY_KEY["employment_offers"].depends_on == ("pre_hiring",),
        "employment_offers depends on pre_hiring",
    )

    # Permissions matrix
    perms_owner = {"offer.manage", "offer.approve", "offer.send", "offer.withdraw", "offer.record_response"}
    check(offers.authorize_offer_action("create", None, perms_owner), "owner can create")
    check(offers.authorize_offer_action("approve", "pending_approval", perms_owner), "owner can approve")
    check(not offers.authorize_offer_action("approve", "draft", perms_owner), "cannot approve from draft")
    check(offers.authorize_offer_action("send", "approved", perms_owner), "can send approved")
    check(not offers.authorize_offer_action("send", "draft", perms_owner), "cannot send draft")
    check(offers.authorize_offer_action("edit", "draft", {"offer.manage"}), "can edit draft")
    check(not offers.authorize_offer_action("edit", "sent", {"offer.manage"}), "cannot edit sent")

    recruiter = {"offer.manage", "offer.send", "offer.withdraw"}
    check(not offers.authorize_offer_action("approve", "pending_approval", recruiter), "recruiter cannot approve")
    hm = {"offer.approve"}
    check(offers.authorize_offer_action("approve", "pending_approval", hm), "hiring manager can approve")
    check(not offers.authorize_offer_action("send", "approved", hm), "hiring manager cannot send")

    check("offer.hire_override" in offers.OFFER_GRANT_ONLY_PERMISSIONS, "hire_override is grant-only")
    check(
        offers.permission_for_offer_action("hire_override") == "offer.hire_override",
        "hire_override permission mapped",
    )

    # AI forbidden
    try:
        offers.require_human_actor("ai")
        raise AssertionError("ai should be rejected")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "ai_forbidden", "AI mutation rejected")

    offers.require_human_actor("human")
    offers.require_human_actor("candidate")
    check(True, "human and candidate actors allowed")

    # Mobile V1 subset
    mobile = offers.mobile_offer_allowed_actions("pending_approval", perms_owner)
    check("approve" in mobile and "return_draft" in mobile, "mobile advertise approve/return")
    check("send" not in mobile and "edit" not in mobile, "mobile V1 excludes edit/send")
    mobile_sent = offers.mobile_offer_allowed_actions("sent", perms_owner)
    check("record_accept" in mobile_sent and "withdraw" in mobile_sent, "mobile record/withdraw on sent")

    # PDF generation + fingerprint
    terms = offers.build_terms_payload(
        position_code="ENG",
        position_title="Engineer",
        department="Tech",
        currency="KWD",
        base_salary="900",
        allowances=[{"label": "Transport", "amount": "50"}],
        proposed_start_date="2026-08-01",
        probation_days=90,
        expires_at=None,
        wording_en="Welcome aboard",
        wording_ar="",
        candidate_name_snapshot="Ali Test",
    )
    pdf = offers.generate_offer_pdf_bytes(terms)
    check(pdf.startswith(b"%PDF"), "generated PDF header")
    check(len(offers.terms_fingerprint(terms)) == 64, "terms fingerprint sha256")

    # Transitions
    check("pending_approval" in offers.allowed_offer_targets("draft"), "draft -> pending_approval")
    check("approved" in offers.allowed_offer_targets("pending_approval"), "pending -> approved")
    check("sent" in offers.allowed_offer_targets("approved"), "approved -> sent")
    check("accepted" in offers.allowed_offer_targets("sent"), "sent -> accepted")
    check(not offers.allowed_offer_targets("accepted"), "accepted is terminal")

    # Role permission wiring — parse app source without importing heavy deps.
    app_src = (ROOT / "app.py").read_text()
    check('"offer.manage"' in app_src and "ROLE_PERMISSIONS" in app_src, "app defines offer permissions")
    check("OFFER_GRANT_ONLY_PERMISSIONS" in app_src, "app defines offer grant-only set")
    check("offer.hire_override" in app_src, "hire_override referenced in app")
    check("difference_update(OFFER_GRANT_ONLY_PERMISSIONS)" in app_src, "grant-only stripped from role defaults")
    check("_offer_routes.register_offer_routes" in app_src, "offer routes registered")
    check("enforce_hire_gate" in (ROOT / "action_registry.py").read_text(), "hire executor gated")
    check("DashboardHireRequest" in app_src, "hire override request model present")
    check("ensure_offer_schema" in app_src, "schema ensure wired")

    # Schema SQL callable
    class FakeCur:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(sql)

    cur = FakeCur()
    offers.ensure_offer_schema(cur)
    joined = "\n".join(cur.statements)
    for table in (
        "employment_offers",
        "employment_offer_versions",
        "employment_offer_events",
        "employment_offer_tokens",
        "employment_offer_deliveries",
        "employment_offer_hire_override_audits",
    ):
        check(table in joined, f"schema creates {table}")
    check("employment_offers_open_app_uq" in joined, "open offer uniqueness index")

    # Deploy includes offer modules
    deploy = (ROOT / "ops" / "deploy.sh").read_text()
    check("offer_lifecycle.py" in deploy, "deploy ships offer_lifecycle.py")
    check("offer_service.py" in deploy, "deploy ships offer_service.py")
    check("offer_routes.py" in deploy, "deploy ships offer_routes.py")

    # Service helpers exist
    check(callable(offer_service.create_draft), "create_draft service")
    check(callable(offer_service.send_offer), "send_offer service")
    check(callable(offer_service.respond_via_token), "token respond service")
    check(callable(offer_service.enforce_hire_gate), "hire gate service")

    print("Offer-1 smoke passed")


if __name__ == "__main__":
    main()
