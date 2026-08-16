#!/usr/bin/env python3
"""Offer-1 controlled production proof + cleanup (WATHEFNI tenant only).

Enables employment_offers for WATHEFNI only, runs synthetic proofs with
intentionally_skipped delivery, then deletes every synthetic fixture.
Never sends real WhatsApp/email. Leaves real WATHEFNI counters unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MARKER = "temporary_offer1_prod_proof_v1"
COMPANY = "WATHEFNI"
OTHER = "OFFER1XO"  # isolation probe tenant (created + deleted)
PHONE_A = "965500481001"
PHONE_B = "965500481002"
PHONE_C = "965500481003"
REPORT: dict[str, Any] = {"checks": [], "migration": {}, "tenant": {}, "cleanup": {}, "hashes": {}}
PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL
    ok = bool(cond)
    if ok:
        PASS += 1
        print(f"  PASS  {label}" + (f" — {detail}" if detail not in (None, "") and ok else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))
    REPORT["checks"].append({"label": label, "ok": ok, "detail": detail if not ok or detail else None})


def main() -> int:
    # Quarantined after Candidates C0/C1: uses direct applications.status fixture writes.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lifecycle_fixture_quarantine import refuse_unless_legacy_fixtures_explicitly_allowed

    refuse_unless_legacy_fixtures_explicitly_allowed(script_name="offer1-production-cutover-proof.py")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")

    prod_orch = os.environ.get("WATHEFNI_PROD_ORCH", "/opt/wathefni/orchestrator")
    sys.path = [p for p in sys.path if p not in {prod_orch, "/opt/wathefni/staging/orchestrator"}]
    sys.path.insert(0, prod_orch)

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    import app as legacy
    import offer_lifecycle as offers
    import offer_service
    import operator_mobile as omobile

    if not str(getattr(legacy, "__file__", "")).startswith(prod_orch):
        raise RuntimeError(f"must import production app.py, got {legacy.__file__}")

    print("Offer-1 PRODUCTION controlled proof — WATHEFNI only")
    legacy.assert_runtime_environment_binding()
    legacy.ensure_schema(force=True)
    offer_service.ensure_schema(legacy)

    # Migration presence
    with legacy.db_connect() as conn, conn.cursor() as cur:
        for table in (
            "employment_offers",
            "employment_offer_versions",
            "employment_offer_events",
            "employment_offer_tokens",
            "employment_offer_deliveries",
            "employment_offer_hire_override_audits",
        ):
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name=%s LIMIT 1",
                (table,),
            )
            check(f"schema has {table}", cur.fetchone() is not None)
            REPORT["migration"][table] = True
    REPORT["migration"]["ensure_schema"] = "ok"

    def snapshot() -> dict[str, int]:
        with legacy.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM applications WHERE company_code=%s", (COMPANY,))
            apps = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM candidate_interviews WHERE company_code=%s", (COMPANY,))
            interviews = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employees WHERE company_code=%s", (COMPANY,))
            employees = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM outbound_delivery_events WHERE account_id=%s",
                (COMPANY,),
            )
            outbound = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM employment_offers WHERE company_code=%s AND COALESCE(metadata->>'marker','')<>%s",
                (COMPANY, MARKER),
            )
            real_offers = int((cur.fetchone() or {}).get("n") or 0)
        return {
            "applications": apps,
            "interviews": interviews,
            "employees": employees,
            "outbound": outbound,
            "non_marker_offers": real_offers,
        }

    before = snapshot()
    REPORT["wathefni_before"] = before

    # Tenant/module state: enable WATHEFNI only; force self-approval false; disable others if present.
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
            VALUES (%s, 'employment_offers', true, %s, '{}'::jsonb, now())
            ON CONFLICT (company_code, module_key) DO UPDATE
              SET enabled=true, source=EXCLUDED.source, updated_at=now()
            """,
            (COMPANY, MARKER),
        )
        cur.execute(
            """
            INSERT INTO company_settings (company_code, settings)
            VALUES (%s, '{"offer_allow_self_approval": false}'::jsonb)
            ON CONFLICT (company_code) DO UPDATE
              SET settings = company_settings.settings || '{"offer_allow_self_approval": false}'::jsonb,
                  updated_at=now()
            """,
            (COMPANY,),
        )
        cur.execute(
            """
            UPDATE company_modules
            SET enabled=false, updated_at=now()
            WHERE module_key='employment_offers' AND company_code<>%s AND enabled=true
            RETURNING company_code
            """,
            (COMPANY,),
        )
        disabled_others = [r["company_code"] for r in cur.fetchall()]
        # Isolation probe company — module OFF
        cur.execute(
            """
            INSERT INTO companies (company_code, name, created_at, updated_at)
            VALUES (%s, 'Offer1 Isolation Probe', now(), now())
            ON CONFLICT (company_code) DO NOTHING
            """,
            (OTHER,),
        )
        cur.execute(
            """
            INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
            VALUES (%s, 'employment_offers', false, %s, '{}'::jsonb, now())
            ON CONFLICT (company_code, module_key) DO UPDATE
              SET enabled=false, updated_at=now()
            """,
            (OTHER, MARKER),
        )
        conn.commit()
    REPORT["tenant"] = {
        "wathefni_employment_offers": True,
        "offer_allow_self_approval": False,
        "disabled_other_tenants": disabled_others,
        "probe_company": OTHER,
        "probe_module_enabled": False,
    }
    check("WATHEFNI employment_offers enabled", offers.employment_offers_enabled(legacy, COMPANY))
    check("self-approval disabled", offers.offer_allow_self_approval(legacy, COMPANY) is False)
    check("probe tenant module disabled", offers.employment_offers_enabled(legacy, OTHER) is False)

    app_a = f"OFFER1PROD-A-{uuid.uuid4().hex[:8]}"
    app_b = f"OFFER1PROD-B-{uuid.uuid4().hex[:8]}"
    app_c = f"OFFER1PROD-C-{uuid.uuid4().hex[:8]}"
    created_offer_ids: list[str] = []
    created_app_keys = [app_a, app_b, app_c]
    creator = f"offer1-prod-creator-{uuid.uuid4()}"
    approver = f"offer1-prod-approver-{uuid.uuid4()}"
    sender = f"offer1-prod-sender-{uuid.uuid4()}"
    perms = {
        "offer.manage",
        "offer.approve",
        "offer.send",
        "offer.withdraw",
        "offer.record_response",
        "candidate.decide",
        "prehire.read",
    }

    def insert_app(app_key: str, phone: str) -> None:
        with legacy.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates (phone, name, current_status, active_company_code, data_source)
                VALUES (%s, %s, 'ready_for_review', %s, 'production')
                ON CONFLICT (phone) DO UPDATE SET
                  name=EXCLUDED.name,
                  active_company_code=EXCLUDED.active_company_code
                """,
                (phone, f"Offer1 Prod {app_key[-8:]}", COMPANY),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, company_code, phone, position_code, position_title,
                   status, data_source, cv_received, raw_json, updated_at)
                VALUES (%s,%s,%s,'OFFER1-PROD','Offer1 Prod Role','shortlisted','production',true,%s,now())
                """,
                (
                    app_key,
                    COMPANY,
                    phone,
                    legacy.Json({"marker": MARKER, "source": MARKER, "candidate_name": f"Offer1 Prod {app_key[-8:]}"}),
                ),
            )
            conn.commit()

    try:
        insert_app(app_a, PHONE_A)
        insert_app(app_b, PHONE_B)
        insert_app(app_c, PHONE_C)
    except Exception as exc:
        # Fallback if unique constraint shape differs
        check("insert synthetic applications", False, str(exc))
        raise

    check("synthetic applications inserted", True, ",".join(created_app_keys))

    def flow_to_sent(app_key: str, *, title: str, salary: float = 700) -> dict[str, Any]:
        draft = offer_service.create_draft(
            legacy,
            company_code=COMPANY,
            app_key=app_key,
            actor_user_id=creator,
            permissions=perms,
            position_title=title,
            base_salary=salary,
            currency="KWD",
            wording_en="Production Offer-1 English terms.",
            wording_ar="شروط عرض العمل بالعربية للتحقق الإنتاجي.",
            idempotency_key=f"{MARKER}:{uuid.uuid4()}",
        )
        # stamp marker on offer metadata
        with legacy.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employment_offers
                SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                WHERE offer_id=%s
                """,
                (json.dumps({"marker": MARKER}), draft["offer_id"]),
            )
            conn.commit()
        created_offer_ids.append(draft["offer_id"])
        offer_service.submit_for_approval(
            legacy=legacy,
            company_code=COMPANY,
            offer_id=draft["offer_id"],
            actor_user_id=creator,
            permissions=perms,
        )
        offer_service.approve_offer(
            legacy=legacy,
            company_code=COMPANY,
            offer_id=draft["offer_id"],
            actor_user_id=approver,
            permissions=perms,
        )
        # Force intentionally_skipped — never call production WhatsApp transport.
        had = hasattr(legacy, "send_company_whatsapp_message")
        original = getattr(legacy, "send_company_whatsapp_message", None)
        if had:
            delattr(legacy, "send_company_whatsapp_message")
        try:
            sent = offer_service.send_offer(
                legacy,
                company_code=COMPANY,
                offer_id=draft["offer_id"],
                actor_user_id=sender,
                permissions=perms,
            )
        finally:
            if had and original is not None:
                setattr(legacy, "send_company_whatsapp_message", original)
        return sent

    # --- Web flow ---
    sent = flow_to_sent(app_a, title="Prod Proof Role A")
    check("draft→submit→approve→send", sent["status"] == "sent")
    check(
        "delivery intentionally_skipped",
        (sent.get("delivery") or {}).get("status") == "intentionally_skipped",
        (sent.get("delivery") or {}).get("status"),
    )
    raw_token = str(sent.get("raw_token") or "")
    sent_version = int(sent["current_version"])
    offer_a = sent["offer_id"]

    # Immutable sent version
    try:
        offer_service.update_draft(
            legacy,
            company_code=COMPANY,
            offer_id=offer_a,
            actor_user_id=creator,
            permissions=perms,
            expected_status="draft",
            fields={"base_salary": 999},
        )
        check("immutable sent version", False, "edit succeeded")
    except offers.OfferAuthorityError as exc:
        check("immutable sent version", exc.code in {"stale_offer", "permission_denied"}, exc.code)

    # Hire blocked before acceptance
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=COMPANY,
            app_key=app_a,
            permissions=perms,
            actor_subject=approver,
            actor_type="human",
        )
        check("hire blocked before acceptance", False)
    except offers.OfferAuthorityError as exc:
        check("hire blocked before acceptance", exc.code == "accepted_offer_required", exc.code)

    # Token accept
    accepted = offer_service.respond_via_token(legacy, raw_token=raw_token, decision="accepted")
    check("token accept", accepted["status"] == "accepted")
    try:
        offer_service.respond_via_token(legacy, raw_token=raw_token, decision="accepted")
        check("one-time token", False)
    except offers.OfferAuthorityError as exc:
        check("one-time token", exc.code in {"token_used", "offer_not_open"}, exc.code)

    gate = offer_service.enforce_hire_gate(
        legacy,
        company_code=COMPANY,
        app_key=app_a,
        permissions=perms,
        actor_subject=approver,
        actor_type="human",
    )
    check("hire allowed after acceptance", bool(gate.get("ok") and gate.get("offer_id") == offer_a))

    # Decline path
    declined_sent = flow_to_sent(app_b, title="Prod Proof Role B", salary=710)
    declined = offer_service.respond_via_token(
        legacy, raw_token=str(declined_sent["raw_token"]), decision="declined"
    )
    check("token decline", declined["status"] == "declined")

    # Withdraw / revoke
    revoke_sent = flow_to_sent(app_c, title="Prod Proof Role C", salary=720)
    revoke_token = str(revoke_sent["raw_token"])
    offer_service.withdraw_offer(
        legacy=legacy,
        company_code=COMPANY,
        offer_id=revoke_sent["offer_id"],
        actor_user_id=sender,
        permissions=perms,
        reason="Prod proof withdraw",
    )
    try:
        offer_service.respond_via_token(legacy, raw_token=revoke_token, decision="accepted")
        check("withdrawal/token revocation", False)
    except offers.OfferAuthorityError as exc:
        check("withdrawal/token revocation", exc.code in {"token_revoked", "offer_not_open"}, exc.code)

    # Expiry — reuse app_c after withdraw (terminal) need new app — recreate shortlisted on app_c
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
            (COMPANY, app_c),
        )
        conn.commit()
    expiry_sent = flow_to_sent(app_c, title="Prod Proof Expiry", salary=730)
    expiry_token = str(expiry_sent["raw_token"])
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE employment_offer_tokens
            SET expires_at=%s
            WHERE offer_id=%s AND used_at IS NULL
            """,
            (datetime.now(timezone.utc) - timedelta(minutes=1), expiry_sent["offer_id"]),
        )
        conn.commit()
    try:
        offer_service.respond_via_token(legacy, raw_token=expiry_token, decision="accepted")
        check("token expiry", False)
    except offers.OfferAuthorityError as exc:
        check("token expiry", exc.code == "token_expired", exc.code)

    # Self-approval denied
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
            (COMPANY, app_b),
        )
        conn.commit()
    # clear open on B if any
    open_b = offers.find_open_offer(legacy, COMPANY, app_b)
    if open_b:
        try:
            offer_service.withdraw_offer(
                legacy=legacy,
                company_code=COMPANY,
                offer_id=str(open_b["offer_id"]),
                actor_user_id=creator,
                permissions=perms,
                reason="clear for self-approval test",
            )
        except Exception:
            pass
    draft_sa = offer_service.create_draft(
        legacy,
        company_code=COMPANY,
        app_key=app_b,
        actor_user_id=creator,
        permissions=perms,
        position_title="Self Approval Test",
        base_salary=500,
        wording_en="sa",
        idempotency_key=f"{MARKER}:sa:{uuid.uuid4()}",
    )
    created_offer_ids.append(draft_sa["offer_id"])
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE employment_offers SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE offer_id=%s",
            (json.dumps({"marker": MARKER}), draft_sa["offer_id"]),
        )
        conn.commit()
    offer_service.submit_for_approval(
        legacy=legacy,
        company_code=COMPANY,
        offer_id=draft_sa["offer_id"],
        actor_user_id=creator,
        permissions=perms,
    )
    try:
        offer_service.approve_offer(
            legacy=legacy,
            company_code=COMPANY,
            offer_id=draft_sa["offer_id"],
            actor_user_id=creator,
            permissions=perms,
        )
        check("self-approval denied", False)
    except offers.OfferAuthorityError as exc:
        check("self-approval denied", exc.code == "self_approval_forbidden", exc.code)

    # Override proofs on app without accepted — use app_c after ensuring no accepted
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE employment_offers SET status='withdrawn', updated_at=now()
            WHERE company_code=%s AND app_key=%s AND status='accepted'
            """,
            (COMPANY, app_c),
        )
        cur.execute(
            "UPDATE applications SET status='shortlisted', updated_at=now() WHERE company_code=%s AND app_key=%s",
            (COMPANY, app_c),
        )
        conn.commit()
    open_c = offers.find_open_offer(legacy, COMPANY, app_c)
    if open_c:
        try:
            offer_service.withdraw_offer(
                legacy=legacy,
                company_code=COMPANY,
                offer_id=str(open_c["offer_id"]),
                actor_user_id=creator,
                permissions=perms,
                reason="clear for override",
            )
        except Exception:
            pass

    override_perms = set(perms) | {"offer.hire_override"}
    # missing permission
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=COMPANY,
            app_key=app_c,
            permissions=perms,
            hire_override=True,
            override_reason="needs grant",
            actor_subject=approver,
            actor_type="human",
            confirmation_token="prod-no-grant",
            confirmed=True,
        )
        check("override requires permission", False)
    except offers.OfferAuthorityError as exc:
        check("override requires permission", exc.code == "permission_denied", exc.code)

    # missing confirmation
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=COMPANY,
            app_key=app_c,
            permissions=override_perms,
            hire_override=True,
            override_reason="needs confirm",
            actor_subject=approver,
            actor_type="human",
            confirmation_token="prod-noconfirm",
            confirmed=False,
        )
        check("override requires confirmation", False)
    except offers.OfferAuthorityError as exc:
        check("override requires confirmation", exc.code == "override_confirm_required", exc.code)

    # missing reason
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=COMPANY,
            app_key=app_c,
            permissions=override_perms,
            hire_override=True,
            override_reason="  ",
            actor_subject=approver,
            actor_type="human",
            confirmation_token="prod-noreason",
            confirmed=True,
        )
        check("override requires reason", False)
    except offers.OfferAuthorityError as exc:
        check("override requires reason", exc.code == "override_reason_required", exc.code)

    # UUID actor success
    uuid_actor = str(uuid.uuid4())
    uuid_confirm = f"prod-uuid-{uuid.uuid4()}"
    uuid_gate = offer_service.enforce_hire_gate(
        legacy,
        company_code=COMPANY,
        app_key=app_c,
        permissions=override_perms,
        hire_override=True,
        override_reason="Prod UUID override proof",
        actor_user_id=uuid_actor,
        actor_subject=uuid_actor,
        actor_type="human",
        confirmation_token=uuid_confirm,
        confirmed=True,
    )
    check("no-offer override with UUID actor", bool(uuid_gate.get("override") and uuid_gate.get("audit_id")))

    # non-UUID actor
    nonuuid_confirm = f"prod-nonuuid-{uuid.uuid4()}"
    nonuuid_gate = offer_service.enforce_hire_gate(
        legacy,
        company_code=COMPANY,
        app_key=app_c,
        permissions=override_perms,
        hire_override=True,
        override_reason="Prod non-UUID override proof",
        actor_user_id=None,
        actor_subject="dashboard:offer1-prod-owner",
        actor_type="human",
        confirmation_token=nonuuid_confirm,
        confirmed=True,
    )
    check(
        "no-offer override with non-UUID actor",
        bool(nonuuid_gate.get("override") and nonuuid_gate.get("audit_id")),
    )

    # failed audit prevents hire — force insert failure via broken table name monkeypatch is hard;
    # use unit-level equivalent: call _persist with failing connection mock is local-only.
    # In production, simulate by confirming require path: audit must exist after successful override.
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM employment_offer_hire_override_audits WHERE confirmation_ref=%s",
            (uuid_confirm,),
        )
        n_uuid = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM employment_offer_hire_override_audits WHERE confirmation_ref=%s",
            (nonuuid_confirm,),
        )
        n_non = int((cur.fetchone() or {}).get("n") or 0)
    check("UUID override audit durable", n_uuid == 1)
    check("non-UUID override audit durable", n_non == 1)

    # AI denied
    try:
        offer_service.enforce_hire_gate(
            legacy,
            company_code=COMPANY,
            app_key=app_c,
            permissions=override_perms,
            hire_override=True,
            override_reason="AI attempt",
            actor_subject="assistant",
            actor_type="ai",
            confirmation_token="prod-ai",
            confirmed=True,
        )
        check("AI/Assistant override denied", False)
    except offers.OfferAuthorityError as exc:
        check("AI/Assistant override denied", exc.code == "ai_forbidden", exc.code)

    # Tenant isolation — offer from WATHEFNI not visible under OTHER
    foreign = offers.get_offer(legacy, OTHER, offer_a)
    check("tenant isolation", foreign is None)

    # Mobile allowed actions match executable authority
    mobile_pending = offers.mobile_offer_allowed_actions("pending_approval", perms)
    check(
        "mobile allowed actions match execution",
        "approve" in mobile_pending
        and "return_draft" in mobile_pending
        and "send" not in mobile_pending
        and "edit" not in mobile_pending,
        mobile_pending,
    )
    caps = omobile.build_recruiting_workspace_capabilities(
        legacy,
        {
            "company_code": COMPANY,
            "permissions": sorted(perms),
            "permission_authority": "backend_current",
            "permission_subject_user_id": approver,
            "permission_subject_company": COMPANY,
            "actor_user_id": approver,
        },
    )
    offer_cap = caps.get("employment_offers") or {}
    check(
        "mobile employment_offers capability",
        bool(offer_cap.get("enabled")) and "approve" in (offer_cap.get("actions") or []),
        offer_cap.get("actions"),
    )

    # EN/AR documents
    terms = {
        "candidate_name_snapshot": "Offer1 Prod",
        "position_title": "Prod Role",
        "currency": "KWD",
        "base_salary": "700",
        "wording_en": "English production proof letter",
        "wording_ar": "خطاب إثبات إنتاجي بالعربية",
        "allowances": [],
        "department": None,
        "proposed_start_date": None,
        "probation_days": 90,
        "expires_at": None,
        "position_code": "OFFER1-PROD",
    }
    pdf_en = offers.generate_offer_pdf_bytes(terms, locale="en")
    pdf_ar = offers.generate_offer_pdf_bytes(terms, locale="ar")
    en_sha = hashlib.sha256(pdf_en).hexdigest()
    ar_sha = hashlib.sha256(pdf_ar).hexdigest()
    REPORT["hashes"]["offer_en_sha256"] = en_sha
    REPORT["hashes"]["offer_ar_sha256"] = ar_sha
    check("English offer document", pdf_en.startswith(b"%PDF"))
    check("Arabic offer document", pdf_ar.startswith(b"%PDF") and en_sha != ar_sha)

    # failed audit prevents hire — invoke persist with a cursor that fails
    class Boom:
        def db_connect(self):
            raise RuntimeError("forced_audit_failure")

    try:
        offer_service._persist_hire_override_audit(
            Boom(),
            company_code=COMPANY,
            app_key=app_c,
            actor_type="human",
            actor_subject="x",
            actor_user_id=None,
            reason="fail",
            from_stage="shortlisted",
            to_stage="hired",
            confirmation_ref="boom",
            no_accepted_offer=True,
            idempotency_key="boom",
        )
        check("failed audit prevents hire", False)
    except offers.OfferAuthorityError as exc:
        check("failed audit prevents hire", exc.code == "override_audit_failed", exc.code)

    # Cleanup
    def cleanup() -> dict[str, Any]:
        deleted: dict[str, int] = {}
        with legacy.db_connect() as conn, conn.cursor() as cur:
            # Collect marker offer ids
            cur.execute(
                """
                SELECT offer_id FROM employment_offers
                WHERE company_code=%s AND (
                  metadata->>'marker'=%s OR app_key = ANY(%s)
                )
                """,
                (COMPANY, MARKER, created_app_keys),
            )
            oids = [str(r["offer_id"]) for r in cur.fetchall()] + list(created_offer_ids)
            oids = list(dict.fromkeys(oids))

            def _del(sql: str, params: tuple[Any, ...], key: str) -> None:
                cur.execute(sql, params)
                deleted[key] = deleted.get(key, 0) + cur.rowcount

            if oids:
                _del(
                    "DELETE FROM employment_offer_tokens WHERE offer_id = ANY(%s::uuid[])",
                    (oids,),
                    "tokens",
                )
                _del(
                    "DELETE FROM employment_offer_deliveries WHERE offer_id = ANY(%s::uuid[])",
                    (oids,),
                    "deliveries",
                )
                _del(
                    "DELETE FROM employment_offer_events WHERE offer_id = ANY(%s::uuid[])",
                    (oids,),
                    "events",
                )
                _del(
                    "DELETE FROM employment_offer_versions WHERE offer_id = ANY(%s::uuid[])",
                    (oids,),
                    "versions",
                )
                _del(
                    "DELETE FROM employment_offers WHERE offer_id = ANY(%s::uuid[])",
                    (oids,),
                    "offers",
                )
            _del(
                "DELETE FROM employment_offer_hire_override_audits WHERE company_code=%s AND app_key = ANY(%s)",
                (COMPANY, created_app_keys),
                "override_audits",
            )
            _del(
                "DELETE FROM application_lifecycle_events WHERE company_code=%s AND app_key = ANY(%s)",
                (COMPANY, created_app_keys),
                "lifecycle_events",
            )
            _del(
                "DELETE FROM applications WHERE company_code=%s AND app_key = ANY(%s)",
                (COMPANY, created_app_keys),
                "applications",
            )
            _del(
                "DELETE FROM candidates WHERE phone = ANY(%s)",
                ([PHONE_A, PHONE_B, PHONE_C],),
                "candidates",
            )
            _del(
                "DELETE FROM company_modules WHERE company_code=%s AND source=%s",
                (OTHER, MARKER),
                "probe_modules",
            )
            _del("DELETE FROM companies WHERE company_code=%s", (OTHER,), "probe_company")
            # Keep WATHEFNI employment_offers enabled (controlled cutover state) but clear marker source noise
            cur.execute(
                """
                UPDATE company_modules SET source='production_controlled_enablement'
                WHERE company_code=%s AND module_key='employment_offers'
                """,
                (COMPANY,),
            )
            conn.commit()
        return deleted

    deleted = cleanup()
    REPORT["cleanup"] = deleted

    # Residual marker rows must be zero
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM employment_offers WHERE company_code=%s AND app_key = ANY(%s)",
            (COMPANY, created_app_keys),
        )
        left_offers = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM applications WHERE company_code=%s AND app_key = ANY(%s)",
            (COMPANY, created_app_keys),
        )
        left_apps = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM employment_offer_hire_override_audits WHERE company_code=%s AND app_key = ANY(%s)",
            (COMPANY, created_app_keys),
        )
        left_audits = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM candidates WHERE phone = ANY(%s)",
            ([PHONE_A, PHONE_B, PHONE_C],),
        )
        left_cands = int((cur.fetchone() or {}).get("n") or 0)
    check("synthetic cleanup offers gone", left_offers == 0, left_offers)
    check("synthetic cleanup applications gone", left_apps == 0, left_apps)
    check("synthetic cleanup audits gone", left_audits == 0, left_audits)
    check("synthetic cleanup candidates gone", left_cands == 0, left_cands)

    after = snapshot()
    REPORT["wathefni_after"] = after
    check("real applications unchanged", after["applications"] == before["applications"], f"{before['applications']}→{after['applications']}")
    check("real interviews unchanged", after["interviews"] == before["interviews"], f"{before['interviews']}→{after['interviews']}")
    check("real employees unchanged", after["employees"] == before["employees"], f"{before['employees']}→{after['employees']}")
    check("outbound counters unchanged", after["outbound"] == before["outbound"], f"{before['outbound']}→{after['outbound']}")

    # Module remains on for WATHEFNI only
    check("WATHEFNI module still enabled after proof", offers.employment_offers_enabled(legacy, COMPANY))
    with legacy.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n FROM company_modules
            WHERE module_key='employment_offers' AND enabled=true AND company_code<>%s
            """,
            (COMPANY,),
        )
        others_on = int((cur.fetchone() or {}).get("n") or 0)
    check("no external tenants have employment_offers enabled", others_on == 0, others_on)

    REPORT["passed"] = PASS
    REPORT["failed"] = FAIL
    REPORT["total"] = PASS + FAIL
    out = Path("/tmp/offer1-production-proof.json")
    out.write_text(json.dumps(REPORT, indent=2, default=str))
    print(f"\nOffer-1 prod proof: {PASS} passed, {FAIL} failed / {PASS+FAIL}")
    print(f"Evidence: {out}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
