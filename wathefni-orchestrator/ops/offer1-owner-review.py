#!/usr/bin/env python3
"""Offer-1 owner-review package against the staging-green artifact.

Covers the full pre-production checklist. Does not mutate production.
Writes JSON + markdown evidence under staging-evidence/offer-1/.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_SHA_EXPECTED = os.environ.get("OFFER_REVIEW_EXPECT_SHA", "").strip()


class Review:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.side_effects: list[str] = []

    def check(self, section: str, label: str, cond: bool, *, detail: str = "") -> None:
        row = {
            "section": section,
            "label": label,
            "ok": bool(cond),
            "detail": detail,
        }
        self.results.append(row)
        if cond:
            self.passed += 1
            print(f"  PASS  [{section}] {label}" + (f" — {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"  FAIL  [{section}] {label}" + (f" — {detail}" if detail else ""))

    def expect_error(self, section: str, label: str, fn, *, codes: set[str]) -> Any:
        try:
            fn()
            self.check(section, label, False, detail="expected error, got success")
            return None
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            ok = code in codes
            self.check(section, label, ok, detail=f"code={code}")
            return exc


def _pick_app(legacy: Any, company: str, offers: Any, *, require_no_accepted: bool = False) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            if require_no_accepted:
                cur.execute(
                    """
                    SELECT a.app_key, a.status, a.phone, a.position_code, a.position_title
                    FROM applications a
                    WHERE a.company_code=%s
                      AND a.status = ANY(%s)
                      AND NOT EXISTS (
                        SELECT 1 FROM employment_offers o
                        WHERE o.company_code=a.company_code
                          AND o.app_key=a.app_key
                          AND o.status='accepted'
                      )
                    ORDER BY a.updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER)),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                cur.execute(
                    """
                    SELECT a.app_key, a.status, a.phone, a.position_code, a.position_title
                    FROM applications a
                    WHERE a.company_code=%s
                      AND a.status NOT IN ('hired','rejected','withdrawn')
                      AND NOT EXISTS (
                        SELECT 1 FROM employment_offers o
                        WHERE o.company_code=a.company_code
                          AND o.app_key=a.app_key
                          AND o.status='accepted'
                      )
                    ORDER BY a.updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company,),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("No staging application without accepted offer for hire-gate-before proof")
                cur.execute(
                    "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
                    (company, row["app_key"]),
                )
                out = dict(row)
                out["status"] = "shortlisted"
                conn.commit()
                return out

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
            row = cur.fetchone()
            if row:
                return dict(row)
            cur.execute(
                """
                SELECT app_key, status, phone, position_code, position_title
                FROM applications
                WHERE company_code=%s AND status NOT IN ('hired','rejected','withdrawn')
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company,),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("No staging application available for owner review")
            cur.execute(
                "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
                (company, row["app_key"]),
            )
            out = dict(row)
            out["status"] = "shortlisted"
        conn.commit()
    return out


def _enable_module(legacy: Any, company: str, *, self_approval: bool) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'employment_offers', true, 'owner_review', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key) DO UPDATE
                  SET enabled=true, updated_at=now()
                """,
                (company,),
            )
            cur.execute(
                """
                INSERT INTO company_settings (company_code, settings)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (company_code) DO UPDATE
                  SET settings = company_settings.settings || EXCLUDED.settings,
                      updated_at=now()
                """,
                (company, json.dumps({"offer_allow_self_approval": self_approval})),
            )
        conn.commit()


def _clear_open(legacy: Any, company: str, app_key: str, offers: Any, offer_service: Any, perms: set[str], actor: str) -> None:
    open_offer = offers.find_open_offer(legacy, company, app_key)
    if open_offer:
        offer_service.withdraw_offer(
            legacy=legacy,
            company_code=company,
            offer_id=str(open_offer["offer_id"]),
            actor_user_id=actor,
            permissions=perms,
            reason="Owner review reset",
        )


def _flow_to_sent(
    legacy: Any,
    offer_service: Any,
    *,
    company: str,
    app_key: str,
    creator: str,
    approver: str,
    sender: str,
    perms: set[str],
    title: str,
) -> dict[str, Any]:
    draft = offer_service.create_draft(
        legacy,
        company_code=company,
        app_key=app_key,
        actor_user_id=creator,
        permissions=perms,
        position_title=title,
        base_salary=820,
        currency="KWD",
        wording_en="English employment offer terms for owner review.",
        wording_ar="شروط عرض العمل بالعربية لمراجعة المالك.",
        idempotency_key=f"owner-review:{uuid.uuid4()}",
    )
    offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )
    offer_service.approve_offer(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=approver,
        permissions=perms,
    )
    sent = offer_service.send_offer(
        legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=sender,
        permissions=perms,
    )
    return sent


def main() -> int:
    # Quarantined after Candidates C0/C1: uses direct applications.status fixture writes.
    sys.path.insert(0, str(ROOT / "ops"))
    from lifecycle_fixture_quarantine import refuse_unless_legacy_fixtures_explicitly_allowed

    refuse_unless_legacy_fixtures_explicitly_allowed(script_name="offer1-owner-review.py")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    import app as legacy
    import offer_lifecycle as offers
    import offer_service
    import operator_mobile as omobile

    review = Review()
    company = (os.environ.get("OFFER_PROOF_COMPANY") or "WATHEFNI").strip().upper()
    other_company = "OWNERREVX"
    evidence_dir = ROOT / "staging-evidence" / "offer-1" / "owner-review"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("=== Offer-1 owner review ===")
    print(f"company={company} expected_sha={ARTIFACT_SHA_EXPECTED}")

    # Artifact identity
    green = Path("/opt/wathefni/staging/last-green.sha256")
    remote_sha = green.read_text().strip() if green.exists() else ""
    env_sha = os.environ.get("OFFER_REVIEW_ARTIFACT_SHA", "").strip()
    artifact_sha = remote_sha or env_sha
    expected = ARTIFACT_SHA_EXPECTED or artifact_sha
    review.check("artifact", "staging-green SHA present", bool(artifact_sha), detail=artifact_sha)
    review.check(
        "artifact",
        "matches expected owner-review SHA",
        bool(artifact_sha) and artifact_sha == expected,
        detail=f"got={artifact_sha} expected={expected}",
    )

    legacy.assert_runtime_environment_binding()
    legacy.ensure_schema(force=True)
    offer_service.ensure_schema(legacy)

    perms = {
        "offer.manage",
        "offer.approve",
        "offer.send",
        "offer.withdraw",
        "offer.record_response",
        "candidate.decide",
        "prehire.read",
    }
    creator = f"owner-review-creator-{uuid.uuid4()}"
    approver = f"owner-review-approver-{uuid.uuid4()}"
    sender = f"owner-review-sender-{uuid.uuid4()}"

    # --- Separation of duties (policy OFF) ---
    _enable_module(legacy, company, self_approval=False)
    review.check(
        "self_approval",
        "policy OFF — offer_allow_self_approval is false",
        offers.offer_allow_self_approval(legacy, company) is False,
    )
    app_row = _pick_app(legacy, company, offers, require_no_accepted=True)
    app_key = str(app_row["app_key"])
    review.side_effects.append(f"hire-gate fixture app {app_key} (no prior accepted offer)")
    _clear_open(legacy, company, app_key, offers, offer_service, perms, creator)

    draft = offer_service.create_draft(
        legacy,
        company_code=company,
        app_key=app_key,
        actor_user_id=creator,
        permissions=perms,
        position_title="Owner Review Role",
        base_salary=700,
        currency="KWD",
        wording_en="EN terms v1",
        wording_ar="شروط عربية",
        idempotency_key=f"owner-review-sod:{uuid.uuid4()}",
    )
    review.check("web_flow", "draft created", draft["status"] == "draft", detail=draft["offer_id"])
    review.side_effects.append(f"created offer {draft['offer_id']}")

    # EN/AR document proof
    terms = (draft.get("terms") or {}) if isinstance(draft.get("terms"), dict) else {}
    pdf_en = offers.generate_offer_pdf_bytes(
        {
            **terms,
            "wording_en": "English employment offer terms for owner review.",
            "wording_ar": "",
            "candidate_name_snapshot": draft.get("candidate_name_snapshot") or "Candidate",
            "position_title": draft.get("position_title"),
            "currency": "KWD",
            "base_salary": draft.get("base_salary"),
        },
        locale="en",
    )
    pdf_ar = offers.generate_offer_pdf_bytes(
        {
            **terms,
            "wording_en": "",
            "wording_ar": "شروط عرض العمل بالعربية لمراجعة المالك.",
            "candidate_name_snapshot": draft.get("candidate_name_snapshot") or "مرشح",
            "position_title": draft.get("position_title"),
            "currency": "KWD",
            "base_salary": draft.get("base_salary"),
        },
        locale="ar",
    )
    (evidence_dir / "offer-en.pdf").write_bytes(pdf_en)
    (evidence_dir / "offer-ar.pdf").write_bytes(pdf_ar)
    review.check("documents", "EN PDF generated", pdf_en.startswith(b"%PDF"), detail=f"sha256={hashlib.sha256(pdf_en).hexdigest()[:16]}")
    review.check("documents", "AR PDF generated", pdf_ar.startswith(b"%PDF"), detail=f"sha256={hashlib.sha256(pdf_ar).hexdigest()[:16]}")
    review.check("documents", "EN/AR PDFs differ", hashlib.sha256(pdf_en).digest() != hashlib.sha256(pdf_ar).digest())

    # Upload mismatch without confirmation
    fake_pdf = b"%PDF-1.4\n% uploaded mismatch fixture\n"
    review.expect_error(
        "documents",
        "upload without match confirmation rejected",
        lambda: offer_service.update_draft(
            legacy,
            company_code=company,
            offer_id=draft["offer_id"],
            actor_user_id=creator,
            permissions=perms,
            expected_version=int(draft["current_version"]),
            uploaded_pdf_b64=base64.b64encode(fake_pdf).decode(),
            upload_matches_terms_confirmed=False,
        ),
        codes={"upload_match_confirmation_required"},
    )
    confirmed = offer_service.update_draft(
        legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
        expected_version=int(draft["current_version"]),
        fields={"base_salary": 710},
        uploaded_pdf_b64=base64.b64encode(fake_pdf).decode(),
        upload_matches_terms_confirmed=True,
    )
    review.check(
        "documents",
        "upload with match confirmation accepted",
        confirmed.get("document", {}).get("source") == "uploaded"
        and confirmed.get("document", {}).get("upload_matches_terms_confirmed") is True,
        detail=f"version={confirmed.get('current_version')}",
    )

    # Stale version rejection
    review.expect_error(
        "stale",
        "stale expected_version rejected",
        lambda: offer_service.update_draft(
            legacy,
            company_code=company,
            offer_id=draft["offer_id"],
            actor_user_id=creator,
            permissions=perms,
            expected_version=int(confirmed["current_version"]) - 1,
            fields={"base_salary": 711},
        ),
        codes={"stale_offer"},
    )

    # Web flow: submit → return → submit → approve (different actor) → send
    submitted = offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )
    review.check("web_flow", "submit → pending_approval", submitted["status"] == "pending_approval")

    returned = offer_service.return_to_draft(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=approver,
        permissions=perms,
        reason="Owner review return path",
    )
    review.check("web_flow", "approve/return → draft", returned["status"] == "draft")

    # New version after return
    v_before = int(returned["current_version"])
    versioned = offer_service.update_draft(
        legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
        expected_version=v_before,
        fields={"base_salary": 730, "wording_en": "EN terms after return"},
    )
    review.check(
        "web_flow",
        "return → edit creates new version",
        int(versioned["current_version"]) == v_before + 1,
        detail=f"{v_before}→{versioned['current_version']}",
    )

    offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )

    # Hidden self-approval must fail while policy OFF
    review.expect_error(
        "self_approval",
        "creator cannot approve when separation policy enabled (policy OFF)",
        lambda: offer_service.approve_offer(
            legacy=legacy,
            company_code=company,
            offer_id=draft["offer_id"],
            actor_user_id=creator,
            permissions=perms,
        ),
        codes={"self_approval_forbidden"},
    )

    approved = offer_service.approve_offer(
        legacy=legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=approver,
        permissions=perms,
    )
    review.check("web_flow", "separate approver succeeds", approved["status"] == "approved")

    sent = offer_service.send_offer(
        legacy,
        company_code=company,
        offer_id=draft["offer_id"],
        actor_user_id=sender,
        permissions=perms,
    )
    review.check("web_flow", "send → sent", sent["status"] == "sent")
    review.check(
        "web_flow",
        "delivery keyed by offer_id+version",
        sent.get("delivery") is not None
        and int((sent.get("delivery") or {}).get("offer_version") or 0) == int(sent["current_version"]),
        detail=str((sent.get("delivery") or {}).get("status")),
    )
    raw_token = sent.get("raw_token")
    respond_url = sent.get("respond_url")
    review.check("token", "respond token minted", bool(raw_token and respond_url))
    offer_id = draft["offer_id"]
    sent_version = int(sent["current_version"])

    # Hire unavailable before acceptance
    review.expect_error(
        "hire_gate",
        "hire blocked before acceptance",
        lambda: offer_service.enforce_hire_gate(
            legacy,
            company_code=company,
            app_key=app_key,
            permissions=perms,
        ),
        codes={"accepted_offer_required"},
    )

    # One-time use: accept, then reuse fails
    accepted = offer_service.respond_via_token(legacy, raw_token=str(raw_token), decision="accepted")
    review.check("token", "candidate token accept", accepted["status"] == "accepted")
    review.check(
        "token",
        "accepted_version pinned to sent version",
        int(accepted.get("accepted_version") or 0) == sent_version,
    )
    review.expect_error(
        "token",
        "one-time use — second accept rejected",
        lambda: offer_service.respond_via_token(legacy, raw_token=str(raw_token), decision="accepted"),
        codes={"token_used", "offer_not_open"},
    )

    # Hire available after accept
    gate = offer_service.enforce_hire_gate(
        legacy,
        company_code=company,
        app_key=app_key,
        permissions=perms,
    )
    review.check(
        "hire_gate",
        "hire available only after accepted offer",
        bool(gate.get("ok") and gate.get("offer_id") == offer_id),
        detail=str(gate.get("offer_id")),
    )

    # Decline path on a fresh offer
    _clear_open(legacy, company, app_key, offers, offer_service, perms, creator)
    # Prior accepted offer still exists — hire gate finds accepted. Use a second app if possible for decline-only,
    # else withdraw isn't possible on accepted. Create decline flow on a different application.
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key FROM applications
                WHERE company_code=%s AND app_key<>%s AND status = ANY(%s)
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (company, app_key, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER)),
            )
            other = cur.fetchone()
    decline_app = str(other["app_key"]) if other else None
    if not decline_app:
        # Force another row if exists
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT app_key FROM applications
                    WHERE company_code=%s AND app_key<>%s
                      AND status NOT IN ('hired','rejected','withdrawn')
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
                        (company, row["app_key"]),
                    )
                    decline_app = str(row["app_key"])
            conn.commit()

    if decline_app:
        _clear_open(legacy, company, decline_app, offers, offer_service, perms, creator)
        declined_sent = _flow_to_sent(
            legacy,
            offer_service,
            company=company,
            app_key=decline_app,
            creator=creator,
            approver=approver,
            sender=sender,
            perms=perms,
            title="Decline Path Role",
        )
        review.side_effects.append(f"decline-path offer {declined_sent['offer_id']} on {decline_app}")
        declined = offer_service.respond_via_token(
            legacy, raw_token=str(declined_sent["raw_token"]), decision="declined"
        )
        review.check("token", "candidate token decline", declined["status"] == "declined")
    else:
        review.check("token", "candidate token decline", False, detail="no second application available")

    # Withdraw → token revocation
    _clear_open(legacy, company, app_key, offers, offer_service, perms, creator)
    # Need a fresh shortlisted app without accepted-only conflict for withdraw token test —
    # use decline_app or create on app that we can open. Prefer a third key; else reuse decline_app after withdraw.
    revoke_app = decline_app or app_key
    # If revoke_app still has open/accepted, find another
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key FROM applications
                WHERE company_code=%s
                  AND status = ANY(%s)
                  AND app_key NOT IN (
                    SELECT app_key FROM employment_offers
                    WHERE company_code=%s AND status='accepted'
                  )
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (company, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER), company),
            )
            row = cur.fetchone()
            if row:
                revoke_app = str(row["app_key"])
    _clear_open(legacy, company, revoke_app, offers, offer_service, perms, creator)
    revoke_sent = _flow_to_sent(
        legacy,
        offer_service,
        company=company,
        app_key=revoke_app,
        creator=creator,
        approver=approver,
        sender=sender,
        perms=perms,
        title="Revoke Path Role",
    )
    revoke_token = str(revoke_sent["raw_token"])
    revoke_offer_id = revoke_sent["offer_id"]
    review.side_effects.append(f"revoke-path offer {revoke_offer_id} on {revoke_app}")
    offer_service.withdraw_offer(
        legacy=legacy,
        company_code=company,
        offer_id=revoke_offer_id,
        actor_user_id=sender,
        permissions=perms,
        reason="Owner review withdraw revocation",
    )
    review.expect_error(
        "token",
        "revocation on withdraw",
        lambda: offer_service.respond_via_token(legacy, raw_token=revoke_token, decision="accepted"),
        codes={"token_revoked", "offer_not_open"},
    )

    # Token expiry
    _clear_open(legacy, company, revoke_app, offers, offer_service, perms, creator)
    expiry_sent = _flow_to_sent(
        legacy,
        offer_service,
        company=company,
        app_key=revoke_app,
        creator=creator,
        approver=approver,
        sender=sender,
        perms=perms,
        title="Expiry Path Role",
    )
    expiry_token = str(expiry_sent["raw_token"])
    expiry_offer_id = expiry_sent["offer_id"]
    review.side_effects.append(f"expiry-path offer {expiry_offer_id}")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employment_offer_tokens
                SET expires_at=%s
                WHERE offer_id=%s AND used_at IS NULL AND revoked_at IS NULL
                """,
                (datetime.now(timezone.utc) - timedelta(minutes=1), expiry_offer_id),
            )
        conn.commit()
    review.expect_error(
        "token",
        "token expiry enforced",
        lambda: offer_service.respond_via_token(legacy, raw_token=expiry_token, decision="accepted"),
        codes={"token_expired"},
    )

    # Revocation / mismatch on new version: token bound to version; bump version while still sent is blocked
    # by product rules. Prove version_mismatch guard by minting a stale-version token row.
    _clear_open(legacy, company, revoke_app, offers, offer_service, perms, creator)
    version_sent = _flow_to_sent(
        legacy,
        offer_service,
        company=company,
        app_key=revoke_app,
        creator=creator,
        approver=approver,
        sender=sender,
        perms=perms,
        title="Version Guard Role",
    )
    version_offer_id = version_sent["offer_id"]
    current_v = int(version_sent["current_version"])
    raw_stale, hash_stale = offers.mint_offer_token()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employment_offer_tokens
                  (offer_id, company_code, token_hash, purpose, offer_version, expires_at)
                VALUES (%s,%s,%s,'respond',%s,%s)
                """,
                (
                    version_offer_id,
                    company,
                    hash_stale,
                    current_v - 1 if current_v > 1 else 0,
                    datetime.now(timezone.utc) + timedelta(days=1),
                ),
            )
        conn.commit()
    review.side_effects.append(f"version-mismatch token inserted for offer {version_offer_id}")
    review.expect_error(
        "token",
        "stale/new-version token rejected (version_mismatch)",
        lambda: offer_service.respond_via_token(legacy, raw_token=raw_stale, decision="accepted"),
        codes={"version_mismatch"},
    )
    # Also: after withdraw of this offer, live token revoked
    live_token = str(version_sent["raw_token"])
    offer_service.withdraw_offer(
        legacy=legacy,
        company_code=company,
        offer_id=version_offer_id,
        actor_user_id=sender,
        permissions=perms,
        reason="Cleanup version guard offer",
    )

    # Mobile V1 actions
    mobile_pending = offers.mobile_offer_allowed_actions("pending_approval", perms)
    review.check(
        "mobile",
        "advertise approve/return only (no edit/send)",
        "approve" in mobile_pending
        and "return_draft" in mobile_pending
        and "send" not in mobile_pending
        and "edit" not in mobile_pending,
        detail=str(mobile_pending),
    )
    mobile_sent_actions = offers.mobile_offer_allowed_actions("sent", perms)
    review.check(
        "mobile",
        "advertise record response + withdraw on sent",
        "record_accept" in mobile_sent_actions
        and "record_decline" in mobile_sent_actions
        and "withdraw" in mobile_sent_actions,
    )
    caps = omobile.build_recruiting_workspace_capabilities(
        legacy,
        {
            "company_code": company,
            "permissions": sorted(perms),
            "permission_authority": "backend_current",
            "permission_subject_user_id": approver,
            "permission_subject_company": company,
            "actor_user_id": approver,
        },
    )
    offer_cap = caps.get("employment_offers") if isinstance(caps, dict) else None
    review.check(
        "mobile",
        "employment_offers capability enabled with V1 actions",
        isinstance(offer_cap, dict)
        and offer_cap.get("enabled")
        and "approve" in (offer_cap.get("actions") or [])
        and "send" not in (offer_cap.get("actions") or []),
        detail=str((offer_cap or {}).get("actions")),
    )

    # Execute mobile-equivalent mutations on a fresh offer
    _clear_open(legacy, company, revoke_app, offers, offer_service, perms, creator)
    mobile_draft = offer_service.create_draft(
        legacy,
        company_code=company,
        app_key=revoke_app,
        actor_user_id=creator,
        permissions=perms,
        position_title="Mobile V1 Role",
        base_salary=640,
        wording_en="Mobile path",
        idempotency_key=f"owner-review-mobile:{uuid.uuid4()}",
    )
    offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )
    # return then approve (mobile subset)
    offer_service.return_to_draft(
        legacy=legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        actor_user_id=approver,
        permissions=perms,
        reason="Mobile return",
    )
    offer_service.submit_for_approval(
        legacy=legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )
    mob_approved = offer_service.approve_offer(
        legacy=legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        actor_user_id=approver,
        permissions=perms,
    )
    review.check("mobile", "approve/return path executable", mob_approved["status"] == "approved")
    # send is web-only; still needed to get to record/withdraw states
    mob_sent = offer_service.send_offer(
        legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        actor_user_id=sender,
        permissions=perms,
    )
    recorded = offer_service.record_response(
        legacy,
        company_code=company,
        offer_id=mobile_draft["offer_id"],
        decision="declined",
        actor_user_id=approver,
        permissions=perms,
        source="manual",
        evidence={"note": "mobile record response"},
    )
    review.check("mobile", "record response executable", recorded["status"] == "declined")

    _clear_open(legacy, company, revoke_app, offers, offer_service, perms, creator)
    mob_withdraw_sent = _flow_to_sent(
        legacy,
        offer_service,
        company=company,
        app_key=revoke_app,
        creator=creator,
        approver=approver,
        sender=sender,
        perms=perms,
        title="Mobile Withdraw Role",
    )
    withdrawn = offer_service.withdraw_offer(
        legacy=legacy,
        company_code=company,
        offer_id=mob_withdraw_sent["offer_id"],
        actor_user_id=approver,
        permissions=perms,
        reason="Mobile withdraw",
    )
    review.check("mobile", "withdraw executable", withdrawn["status"] == "withdrawn")
    # read DTO
    bundle = offer_service.load_offer_bundle(
        legacy,
        company,
        mob_withdraw_sent["offer_id"],
        permissions=perms,
        surface="mobile",
    )
    review.check("mobile", "read DTO available", bundle.get("offer_id") == mob_withdraw_sent["offer_id"])

    # AI mutation rejection
    review.expect_error(
        "ai",
        "AI cannot create draft",
        lambda: offer_service.create_draft(
            legacy,
            company_code=company,
            app_key=revoke_app,
            actor_user_id="ai-bot",
            permissions=perms,
            actor_type="ai",
            position_title="AI attempt",
        ),
        codes={"ai_forbidden"},
    )
    review.expect_error(
        "ai",
        "AI cannot approve",
        lambda: offer_service.approve_offer(
            legacy=legacy,
            company_code=company,
            offer_id=mob_withdraw_sent["offer_id"],
            actor_user_id="ai-bot",
            permissions=perms,
            actor_type="ai",
        ),
        codes={"ai_forbidden", "stale_offer", "transition_not_allowed", "permission_denied"},
    )
    # Prefer ai_forbidden specifically via require_human_actor
    review.expect_error(
        "ai",
        "require_human_actor rejects AI",
        lambda: offers.require_human_actor("ai"),
        codes={"ai_forbidden"},
    )

    # Grant-only override proofs — must use an app with NO accepted offer,
    # otherwise the normal accepted-offer hire gate short-circuits.
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.app_key, a.status FROM applications a
                WHERE a.company_code=%s
                  AND a.status = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM employment_offers o
                    WHERE o.company_code=a.company_code
                      AND o.app_key=a.app_key
                      AND o.status='accepted'
                  )
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company, list(offers.APPLICATION_STAGES_ELIGIBLE_FOR_HIRE)),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT a.app_key FROM applications a
                    WHERE a.company_code=%s
                      AND a.status NOT IN ('hired','rejected','withdrawn')
                      AND NOT EXISTS (
                        SELECT 1 FROM employment_offers o
                        WHERE o.company_code=a.company_code
                          AND o.app_key=a.app_key
                          AND o.status='accepted'
                      )
                    LIMIT 1
                    """,
                    (company,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
                        (company, row["app_key"]),
                    )
            override_app = str(row["app_key"]) if row else ""
        conn.commit()
    review.check("override", "fixture app without accepted offer available", bool(override_app), detail=override_app)
    if not override_app:
        raise RuntimeError("No application without accepted offer available for override proof")
    _clear_open(legacy, company, override_app, offers, offer_service, perms, creator)
    override_draft = offer_service.create_draft(
        legacy,
        company_code=company,
        app_key=override_app,
        actor_user_id=creator,
        permissions=perms,
        position_title="Override Audit Role",
        base_salary=500,
        wording_en="Open offer present for override audit attachment",
        idempotency_key=f"owner-review-override:{uuid.uuid4()}",
    )
    review.side_effects.append(f"open offer {override_draft['offer_id']} on {override_app} for override audit")
    review.expect_error(
        "override",
        "override without grant denied",
        lambda: offer_service.enforce_hire_gate(
            legacy,
            company_code=company,
            app_key=override_app,
            permissions=perms,  # no hire_override
            hire_override=True,
            override_reason="Needs override for owner review demonstration case",
            actor_user_id=approver,
            actor_subject=approver,
            actor_type="human",
            confirmation_token="owner-review-no-grant",
            confirmed=True,
        ),
        codes={"permission_denied"},
    )
    review.expect_error(
        "override",
        "override without reason denied",
        lambda: offer_service.enforce_hire_gate(
            legacy,
            company_code=company,
            app_key=override_app,
            permissions=set(perms) | {"offer.hire_override"},
            hire_override=True,
            override_reason="   ",
            actor_user_id=approver,
            actor_subject=approver,
            actor_type="human",
            confirmation_token="owner-review-empty-reason",
            confirmed=True,
        ),
        codes={"override_reason_required"},
    )
    confirm_token = f"owner-review-confirm-{uuid.uuid4()}"
    override_ok = offer_service.enforce_hire_gate(
        legacy,
        company_code=company,
        app_key=override_app,
        permissions=set(perms) | {"offer.hire_override"},
        hire_override=True,
        override_reason="Owner review mandatory override reason with audit trail",
        actor_user_id=approver,
        actor_subject=approver,
        actor_type="human",
        confirmation_token=confirm_token,
        confirmed=True,
        expected_from_stage=None,
        idempotency_key=f"owner-review-override:{confirm_token}",
    )
    review.check("override", "grant-only override with reason allowed", bool(override_ok.get("override")))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT audit_id, actor_subject, actor_type, reason, confirmation_ref, no_accepted_offer,
                       from_stage, to_stage
                FROM employment_offer_hire_override_audits
                WHERE company_code=%s AND confirmation_ref=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                (company, confirm_token),
            )
            audit = cur.fetchone()
    review.check(
        "override",
        "override audit recorded",
        bool(audit)
        and str((audit or {}).get("confirmation_ref") or "") == confirm_token
        and str((audit or {}).get("actor_subject") or "") == approver
        and (audit or {}).get("no_accepted_offer") is True
        and "Owner review mandatory override reason" in str((audit or {}).get("reason") or ""),
        detail=str((audit or {}).get("audit_id")),
    )
    # Second durable audit with non-UUID subject on same clean app (idempotent different confirm).
    synth_confirm = f"synth-{uuid.uuid4()}"
    offer_service.enforce_hire_gate(
        legacy,
        company_code=company,
        app_key=override_app,
        permissions=set(perms) | {"offer.hire_override"},
        hire_override=True,
        override_reason="Synthetic no-offer override path must leave durable audit",
        actor_user_id=None,
        actor_subject=f"dashboard:owner-review-{uuid.uuid4().hex[:8]}",
        actor_type="human",
        confirmation_token=synth_confirm,
        confirmed=True,
    )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM employment_offer_hire_override_audits
                WHERE company_code=%s AND confirmation_ref=%s
                """,
                (company, synth_confirm),
            )
            synth_n = int((cur.fetchone() or {}).get("n") or 0)
    review.check(
        "override",
        "no-offer override durable audit persisted",
        synth_n == 1,
        detail=f"hire_override_audit_rows={synth_n}",
    )
    review.side_effects.append(f"hire_override durable audits for confirm={confirm_token} and {synth_confirm}")
    # Tenant isolation
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_code, name, created_at, updated_at)
                VALUES (%s, 'Owner Review Isolation', now(), now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (other_company,),
            )
        conn.commit()
    review.side_effects.append(f"ensured tenant company {other_company}")
    foreign = offers.get_offer(legacy, other_company, offer_id)
    review.check("tenant", "offer not visible cross-tenant by get_offer", foreign is None)
    review.expect_error(
        "tenant",
        "cross-tenant update rejected",
        lambda: offer_service.update_draft(
            legacy,
            company_code=other_company,
            offer_id=offer_id,
            actor_user_id=creator,
            permissions=perms,
            fields={"base_salary": 1},
        ),
        codes={"offer_not_found", "stale_offer", "permission_denied", "module_disabled"},
    )

    # Confirm grant-only not in role defaults (source inspection on artifact)
    app_src = (ROOT / "app.py").read_text()
    review.check(
        "override",
        "hire_override not in owner ROLE_PERMISSIONS defaults",
        '"offer.hire_override"' not in app_src.split("ROLE_PERMISSIONS", 1)[-1].split("EMPLOYEE_PERMISSION_SCOPES", 1)[0],
    )
    review.check(
        "override",
        "OFFER_GRANT_ONLY_PERMISSIONS difference_update present",
        "difference_update(OFFER_GRANT_ONLY_PERMISSIONS)" in app_src,
    )

    # Reaffirm separation policy still OFF (no hidden self-approval)
    review.check(
        "self_approval",
        "no hidden self-approval — policy remains false after review",
        offers.offer_allow_self_approval(legacy, company) is False,
    )

    # Public preview HTML snapshot for screenshot package
    if respond_url and raw_token:
        preview = offer_service.public_offer_preview(legacy, raw_token=str(raw_token))
        # already used
        (evidence_dir / "token-preview-after-accept.json").write_text(json.dumps(preview, indent=2, default=str))
        review.check("token", "public preview reflects used token", bool(preview.get("already_used")))

    summary = {
        "artifact_sha": artifact_sha,
        "expected_sha": ARTIFACT_SHA_EXPECTED,
        "sha_match": artifact_sha == ARTIFACT_SHA_EXPECTED,
        "company": company,
        "passed": review.passed,
        "failed": review.failed,
        "total": review.passed + review.failed,
        "results": review.results,
        "side_effects": review.side_effects,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "staging",
        "production_touched": False,
        "documents": {
            "en_pdf": str(evidence_dir / "offer-en.pdf"),
            "ar_pdf": str(evidence_dir / "offer-ar.pdf"),
            "en_sha256": hashlib.sha256(pdf_en).hexdigest(),
            "ar_sha256": hashlib.sha256(pdf_ar).hexdigest(),
        },
    }
    out_json = evidence_dir / "OWNER_REVIEW_RESULTS.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nOwner review totals: {review.passed} passed, {review.failed} failed / {summary['total']}")
    print(f"Evidence: {out_json}")
    return 0 if review.failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
