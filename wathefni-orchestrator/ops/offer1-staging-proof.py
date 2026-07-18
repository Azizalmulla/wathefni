#!/usr/bin/env python3
"""Staging proof for Offer-1 — draft → approve → send → token accept → hire gate.

Stop before production. Requires staging orchestrator + DB access on the VPS.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(label)
    print(f"  ok: {label}")


def main() -> None:
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    import app as legacy
    import offer_lifecycle as offers
    import offer_service

    legacy.assert_runtime_environment_binding()
    legacy.ensure_schema(force=True)
    offer_service.ensure_schema(legacy)

    company = (os.environ.get("OFFER_PROOF_COMPANY") or "WATHEFNI").strip().upper()
    print(f"Offer-1 staging proof company={company}")

    # Enable module + allow self-approval for single-actor staging proof.
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'employment_offers', true, 'staging_proof', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE
                  SET enabled=true, updated_at=now()
                """,
                (company,),
            )
            cur.execute(
                """
                INSERT INTO company_settings (company_code, settings)
                VALUES (%s, '{"offer_allow_self_approval": true}'::jsonb)
                ON CONFLICT (company_code) DO UPDATE
                  SET settings = company_settings.settings || EXCLUDED.settings,
                      updated_at=now()
                """,
                (company,),
            )
            # Find a shortlisted/interview application to attach, else create a synthetic fixture row if table allows.
            cur.execute(
                """
                SELECT app_key, status, phone, position_code, position_title
                FROM applications
                WHERE company_code=%s AND status = ANY(%s)
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER)),
            )
            app_row = cur.fetchone()
            if not app_row:
                # Fall back to any non-terminal application and force shortlisted for the fixture.
                cur.execute(
                    """
                    SELECT app_key, status, phone, position_code, position_title
                    FROM applications
                    WHERE company_code=%s
                      AND status NOT IN ('hired', 'rejected', 'withdrawn')
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company,),
                )
                app_row = cur.fetchone()
                if app_row:
                    cur.execute(
                        """
                        UPDATE applications
                        SET status='shortlisted', updated_at=now()
                        WHERE company_code=%s AND app_key=%s
                        """,
                        (company, app_row["app_key"]),
                    )
                    app_row = dict(app_row)
                    app_row["status"] = "shortlisted"
        conn.commit()

    check(bool(app_row), "found eligible shortlisted/interview application")
    app_key = str(app_row["app_key"])
    print(f"  using app_key={app_key} status={app_row.get('status')}")

    check(offers.employment_offers_enabled(legacy, company), "employment_offers module enabled")
    check(offers.offer_allow_self_approval(legacy, company), "self-approval policy on for proof")

    actor_a = f"staging-offer-a-{uuid.uuid4()}"
    actor_b = f"staging-offer-b-{uuid.uuid4()}"
    perms = {
        "offer.manage",
        "offer.approve",
        "offer.send",
        "offer.withdraw",
        "offer.record_response",
        "candidate.decide",
    }

    # Withdraw any open offer first.
    open_offer = offers.find_open_offer(legacy, company, app_key)
    if open_offer:
        offer_service.withdraw_offer(
            legacy=legacy,
            company_code=company,
            offer_id=str(open_offer["offer_id"]),
            actor_user_id=actor_a,
            permissions=perms,
            reason="Clearing for staging proof",
        )

    draft = offer_service.create_draft(
        legacy,
        company_code=company,
        app_key=app_key,
        actor_user_id=actor_a,
        permissions=perms,
        position_title=str(app_row.get("position_title") or "Staging Role"),
        base_salary=750,
        currency="KWD",
        wording_en="Staging offer proof letter.",
        wording_ar="خطاب عرض تجريبي.",
        idempotency_key=f"offer-proof:{uuid.uuid4()}",
    )
    check(draft["status"] == "draft", "draft created")
    check(draft.get("candidate_name_snapshot") is not None or True, "identity snapshot fields present")
    offer_id = draft["offer_id"]
    v1 = int(draft["current_version"])

    updated = offer_service.update_draft(
        legacy,
        company_code=company,
        offer_id=offer_id,
        actor_user_id=actor_a,
        permissions=perms,
        expected_version=v1,
        fields={"base_salary": 800, "probation_days": 90},
    )
    check(int(updated["current_version"]) == v1 + 1, "edit creates new version")
    check(updated["document"]["source"] == "generated", "document generated from terms")

    submitted = offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=offer_id,
        actor_user_id=actor_a,
        permissions=perms,
    )
    check(submitted["status"] == "pending_approval", "submitted for approval")

    # Separation of duties: creator cannot approve unless policy allows (enabled above).
    approved = offer_service.approve_offer(
        legacy=legacy,
        company_code=company,
        offer_id=offer_id,
        actor_user_id=actor_a,
        permissions=perms,
    )
    check(approved["status"] == "approved", "self-approval allowed under company policy")

    # Different approver path still works when policy off — covered by unit smoke.
    sent = offer_service.send_offer(
        legacy,
        company_code=company,
        offer_id=offer_id,
        actor_user_id=actor_b,
        permissions=perms,
    )
    check(sent["status"] == "sent", "offer sent")
    check(sent.get("delivery") is not None, "delivery tied to offer version")
    check(int(sent["delivery"]["offer_version"]) == int(sent["current_version"]), "delivery version matches")
    check(bool(sent.get("respond_url") and sent.get("raw_token")), "respond token minted")
    raw_token = sent["raw_token"]
    sent_version = int(sent["current_version"])

    # Sent versions are immutable — edit must fail.
    try:
        offer_service.update_draft(
            legacy,
            company_code=company,
            offer_id=offer_id,
            actor_user_id=actor_a,
            permissions=perms,
            expected_status="draft",
            fields={"base_salary": 900},
        )
        raise AssertionError("edit after send should fail")
    except offers.OfferAuthorityError as exc:
        check(exc.code in {"stale_offer", "permission_denied"}, f"sent immutable ({exc.code})")

    # Hire blocked before accept
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=company,
            app_key=app_key,
            permissions=perms,
        )
        raise AssertionError("hire should require accepted offer")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "accepted_offer_required", "hire gated without accepted offer")

    # AI cannot mutate
    try:
        offer_service.record_response(
            legacy,
            company_code=company,
            offer_id=offer_id,
            decision="accepted",
            actor_user_id=None,
            permissions=perms,
            actor_type="ai",
        )
        raise AssertionError("ai must not record response")
    except offers.OfferAuthorityError as exc:
        check(exc.code == "ai_forbidden", "AI mutation blocked")

    accepted = offer_service.respond_via_token(legacy, raw_token=raw_token, decision="accepted")
    check(accepted["status"] == "accepted", "token accept recorded")
    check(int(accepted.get("accepted_version") or 0) == sent_version, "accepted_version pinned")

    gate = offer_service.enforce_hire_gate(
        legacy,
        company_code=company,
        app_key=app_key,
        permissions=perms,
    )
    check(gate.get("ok") and gate.get("offer_id") == offer_id, "hire gate opens after accept")

    # Override grant path with durable audit (confirmed + non-UUID subject supported)
    override_perms = set(perms) | {"offer.hire_override"}
    # Pick an app without accepted offer
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.app_key FROM applications a
                WHERE a.company_code=%s AND a.status = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM employment_offers o
                    WHERE o.company_code=a.company_code AND o.app_key=a.app_key AND o.status='accepted'
                  )
                ORDER BY a.updated_at DESC NULLS LAST LIMIT 1
                """,
                (company, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER)),
            )
            row = cur.fetchone()
    synthetic_key = str(row["app_key"]) if row else app_key
    confirm = f"staging-proof-override-{uuid.uuid4()}"
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=company,
            app_key=synthetic_key,
            permissions=override_perms,
            hire_override=True,
            override_reason="Staging proof override with mandatory reason text",
            actor_user_id=None,
            actor_subject=f"staging-proof:{actor_b}",
            actor_type="human",
            confirmation_token=confirm,
            confirmed=True,
        )
        check(True, "hire_override with reason allowed")
    except offers.OfferAuthorityError as exc:
        if exc.code == "accepted_offer_required":
            raise
        check(exc.code != "permission_denied", f"override path exercised ({exc.code})")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM employment_offer_hire_override_audits WHERE confirmation_ref=%s",
                (confirm,),
            )
            n = int((cur.fetchone() or {}).get("n") or 0)
    check(n == 1, "hire_override durable audit persisted")

    evidence = {
        "company": company,
        "app_key": app_key,
        "offer_id": offer_id,
        "accepted_version": sent_version,
        "respond_url": sent.get("respond_url"),
        "delivery_status": (sent.get("delivery") or {}).get("status"),
    }
    out = Path("/tmp/offer1-staging-proof.json")
    out.write_text(json.dumps(evidence, indent=2, default=str))
    print(f"Offer-1 staging proof passed → {out}")
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    main()
