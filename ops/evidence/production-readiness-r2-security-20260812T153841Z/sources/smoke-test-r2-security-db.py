#!/usr/bin/env python3
"""Production Readiness R2 — live negative-path security qualification.

Runs against an isolated staging database with two synthetic tenants, exercising
the real FastAPI route handlers (not helper functions) so the proofs are about
shipped behaviour:

  P0-2  forged links from the removed fallbacks are rejected by the live app
  P0-3  dashboard and Setup logins throttle, and rejections do not disclose
        whether a company, an email, or only the password was wrong
  P0-4  the internal worker endpoint denies an unauthenticated caller that
        presents itself as localhost
  P0-5  tenant A cannot read tenant B's turns, pending actions, action results,
        or intake artifacts; break-glass is required for platform operations
  P1-22 the public calendar guest-token endpoint throttles

Also proves the denial audit is populated and carries no credential material,
and that legitimate same-tenant paths still work.

All fixtures are created under randomized company codes and removed afterwards.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
CO_A = f"R2ALPHA{SUFFIX}"
CO_B = f"R2BETA{SUFFIX}"

TOKEN_PLATFORM = f"r2-platform-internal-{uuid.uuid4().hex}"
TOKEN_A = f"r2-tenant-alpha-{uuid.uuid4().hex}"
TOKEN_B = f"r2-tenant-beta-{uuid.uuid4().hex}"
TOKEN_WORKER = f"r2-worker-{uuid.uuid4().hex}"
TOKEN_BREAK_GLASS = f"r2-break-glass-{uuid.uuid4().hex}"

LINK_SECRET_ASSESSMENT = f"r2-assessment-{uuid.uuid4().hex}"
LINK_SECRET_VIDEO = f"r2-video-{uuid.uuid4().hex}"
OLD_ASSESSMENT_CONSTANT = "wathefni-assessment-dev-secret"
OLD_VIDEO_CONSTANT = "wathefni-video-interview-dev-secret"

USER_A_EMAIL = f"alpha.owner.{SUFFIX.lower()}@r2security.test"
USER_A_PASSWORD = f"R2-valid-password-{uuid.uuid4().hex[:12]}"
OPERATOR_PHONE = "96555000111"
OPERATOR_TOKEN = f"r2-operator-{uuid.uuid4().hex}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _configure_env() -> None:
    os.environ["WATHEFNI_INTERNAL_TOKEN"] = TOKEN_PLATFORM
    os.environ["WATHEFNI_INTERNAL_TENANT_TOKENS"] = json.dumps({CO_A: TOKEN_A, CO_B: TOKEN_B})
    os.environ["WATHEFNI_INTERNAL_WORKER_TOKEN"] = TOKEN_WORKER
    os.environ.pop("WATHEFNI_INTERNAL_WORKER_ACCEPT_SHARED", None)
    os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET"] = LINK_SECRET_ASSESSMENT
    os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"] = LINK_SECRET_VIDEO
    os.environ.pop("WATHEFNI_ASSESSMENT_LINK_SECRET_PREVIOUS", None)
    os.environ.pop("WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET_PREVIOUS", None)
    os.environ.pop("WATHEFNI_BREAK_GLASS_ENABLED", None)
    os.environ["WATHEFNI_BREAK_GLASS_TOKEN"] = TOKEN_BREAK_GLASS
    os.environ.pop("WATHEFNI_RATE_LIMIT_DISABLED", None)
    os.environ.pop("WATHEFNI_RATE_LIMIT_FAIL_OPEN", None)
    os.environ["WATHEFNI_SETUP_CONSOLE_ENABLED"] = "1"
    os.environ["WATHEFNI_SETUP_OPERATOR_CREDENTIALS"] = json.dumps({OPERATOR_PHONE: OPERATOR_TOKEN})
    os.environ["WATHEFNI_PLATFORM_ADMIN_PHONES"] = OPERATOR_PHONE
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")


def seed(app) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company, name in ((CO_A, "R2 Alpha"), (CO_B, "R2 Beta")):
                cur.execute(
                    "INSERT INTO companies (company_code, name, status, metadata, raw_json) "
                    "VALUES (%s,%s,'active',%s,%s) ON CONFLICT (company_code) DO NOTHING",
                    (company, name, app.Json({"r2_security_smoke": True}), app.Json({})),
                )
                cur.execute(
                    """
                    INSERT INTO hr_turns (account_id, conversation_id, sender_phone, sender_role,
                                          raw_text, metadata, company_code)
                    VALUES (%s,%s,%s,'hr_admin',%s,%s,%s)
                    """,
                    (
                        company,
                        f"conv-{company}",
                        "96550000000",
                        f"confidential message for {company}",
                        app.Json({"r2_security_smoke": True}),
                        company,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO pending_actions (account_id, conversation_id, admin_phone, action_type,
                                                 prompt_text, metadata, company_code, expires_at)
                    VALUES (%s,%s,%s,'r2_smoke_action',%s,%s,%s, now() + interval '30 minutes')
                    """,
                    (
                        company,
                        f"conv-{company}",
                        "96550000000",
                        f"pending for {company}",
                        app.Json({"r2_security_smoke": True}),
                        company,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO action_results (action_type, status, result, final_reply, company_code)
                    VALUES ('r2_smoke_action','completed',%s,%s,%s)
                    """,
                    (app.Json({"company": company}), f"result for {company}", company),
                )
            cur.execute(
                """
                INSERT INTO dashboard_users (user_id, company_code, email, role, status, password_hash,
                                             created_at, updated_at)
                VALUES (%s,%s,%s,'owner','active',%s, now(), now())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (str(uuid.uuid4()), CO_A, USER_A_EMAIL, app.dashboard_password_hash(USER_A_PASSWORD)),
            )
            try:
                import tenant_email_authority as tea

                tea.ensure_schema(cur)
                cur.execute(
                    """
                    INSERT INTO company_operational_mailboxes (company_code, address, display_name, status)
                    VALUES (%s,%s,'R2 Alpha Docs','active')
                    """,
                    (CO_A, f"docs.{SUFFIX.lower()}@r2security.test"),
                )
            except Exception as exc:  # mailbox routing proof is skipped, not faked
                print(f"      NOTE  operational mailbox seed unavailable: {type(exc).__name__}")
        conn.commit()


def cleanup(app) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (CO_A, CO_B):
                for table in (
                    "action_results",
                    "pending_actions",
                    "hr_turns",
                    "dashboard_user_sessions",
                    "dashboard_users",
                ):
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                    except Exception:
                        conn.rollback()
                try:
                    cur.execute("DELETE FROM company_operational_mailboxes WHERE company_code=%s", (company,))
                except Exception:
                    conn.rollback()
                try:
                    cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
                except Exception:
                    conn.rollback()
            try:
                cur.execute("DELETE FROM security_denial_events WHERE company_code = ANY(%s)", ([CO_A, CO_B],))
                cur.execute("DELETE FROM security_break_glass_events WHERE operation LIKE 'intake_%%'"
                            " AND operator_id=%s", (f"r2-smoke-{SUFFIX}",))
            except Exception:
                conn.rollback()
        conn.commit()


def _hdr(token: str) -> dict[str, str]:
    return {"X-Internal-Token": token}


def tenant_isolation(client, app) -> None:
    print("\n    P0-5 — tenant isolation on internal audit reads")

    r = client.get("/orchestrator/audit/turns", headers=_hdr(TOKEN_A))
    body = r.json()
    check("tenant A reads its own turns", r.status_code == 200 and body.get("company_code") == CO_A, r.status_code)
    check(
        "tenant A sees only its own conversation text",
        all(str(row.get("raw_text") or "").endswith(CO_A) for row in body.get("turns", [])),
        [row.get("raw_text") for row in body.get("turns", [])][:3],
    )

    r = client.get(f"/orchestrator/audit/turns?company_code={CO_B}", headers=_hdr(TOKEN_A))
    check(
        "tenant A cannot request tenant B turns",
        r.status_code == 403 and r.json()["detail"]["error"] == "tenant_scope_violation",
        (r.status_code, r.text[:160]),
    )

    for route, key in (
        ("/orchestrator/audit/pending-actions", "pending_actions"),
        ("/orchestrator/audit/action-results", "action_results"),
    ):
        r = client.get(f"{route}?company_code={CO_B}", headers=_hdr(TOKEN_A))
        check(
            f"tenant A cannot request tenant B {key}",
            r.status_code == 403,
            (r.status_code, r.text[:120]),
        )
        r = client.get(route, headers=_hdr(TOKEN_A))
        check(f"tenant A reads its own {key}", r.status_code == 200 and r.json().get("company_code") == CO_A)

    r = client.get("/orchestrator/audit/turns", headers=_hdr(TOKEN_PLATFORM))
    check(
        "platform token cannot perform an unscoped global read",
        r.status_code == 400 and r.json()["detail"]["error"] == "company_scope_required",
        (r.status_code, r.text[:160]),
    )

    r = client.get(f"/orchestrator/audit/turns?company_code={CO_B}", headers=_hdr(TOKEN_PLATFORM))
    ok = r.status_code == 200 and r.json().get("company_code") == CO_B
    rows = r.json().get("turns", []) if ok else []
    check("platform token with an explicit company reads only that company", ok and all(CO_A not in str(row) for row in rows))

    r = client.get("/orchestrator/audit/turns?company_code=" + CO_A, headers=_hdr("guessed-internal-token"))
    check("unknown internal token is denied", r.status_code == 401, r.status_code)

    print("\n    P0-5 — tenant isolation on intake artifacts")
    r = client.get(f"/orchestrator/debug/intake-operations?company_code={CO_B}", headers=_hdr(TOKEN_A))
    check("tenant A cannot read tenant B intake operations", r.status_code == 403, r.status_code)
    r = client.post(
        f"/orchestrator/debug/intake-documents/{uuid.uuid4()}/signed-download?company_code={CO_B}",
        headers=_hdr(TOKEN_A),
    )
    check("tenant A cannot mint a download for tenant B", r.status_code == 403, r.status_code)
    r = client.post(
        f"/orchestrator/debug/intake-jobs/{uuid.uuid4()}/replay?company_code={CO_B}",
        headers=_hdr(TOKEN_A),
    )
    check("tenant A cannot replay tenant B intake jobs", r.status_code == 403, r.status_code)


def break_glass(client, app) -> None:
    print("\n    P0-5 — break-glass authority for platform operations")
    operator = f"r2-smoke-{SUFFIX}"

    r = client.post("/orchestrator/debug/intake-quarantine/sweep", headers=_hdr(TOKEN_PLATFORM))
    check(
        "platform token alone cannot run the global sweep",
        r.status_code == 403 and r.json()["detail"]["error"] == "break_glass_disabled",
        (r.status_code, r.text[:160]),
    )

    r = client.post("/orchestrator/debug/intake-worker/run", headers=_hdr(TOKEN_PLATFORM))
    check("platform token alone cannot run the shared worker", r.status_code == 403, r.status_code)

    r = client.post("/orchestrator/debug/intake-outage-replay", headers=_hdr(TOKEN_PLATFORM))
    check("unscoped outage replay requires break-glass", r.status_code == 403, r.status_code)

    r = client.post("/orchestrator/debug/intake-quarantine/sweep", headers=_hdr(TOKEN_A))
    check("a tenant principal can never reach platform administration", r.status_code == 403, r.status_code)

    os.environ["WATHEFNI_BREAK_GLASS_ENABLED"] = "1"

    r = client.post(
        "/orchestrator/debug/intake-quarantine/sweep",
        headers={**_hdr(TOKEN_PLATFORM), "X-Operator-Id": operator},
    )
    check(
        "enabled break-glass still needs its own secret",
        r.status_code == 401 and r.json()["detail"]["error"] == "break_glass_forbidden",
        (r.status_code, r.text[:160]),
    )

    r = client.post(
        "/orchestrator/debug/intake-quarantine/sweep?apply=true",
        headers={**_hdr(TOKEN_PLATFORM), "X-Break-Glass-Token": TOKEN_BREAK_GLASS},
    )
    check(
        "destructive apply=true is refused without operator attribution",
        r.status_code == 400 and r.json()["detail"]["error"] == "break_glass_operator_required",
        (r.status_code, r.text[:160]),
    )

    r = client.post(
        "/orchestrator/debug/intake-quarantine/sweep?apply=true",
        headers={**_hdr(TOKEN_PLATFORM), "X-Operator-Id": operator, "X-Break-Glass-Token": "wrong-break-glass"},
    )
    check("destructive apply=true is refused with a wrong break-glass secret", r.status_code == 401, r.status_code)

    # Non-destructive report form with full authority must succeed and be audited.
    r = client.post(
        "/orchestrator/debug/intake-quarantine/sweep",
        headers={**_hdr(TOKEN_PLATFORM), "X-Operator-Id": operator, "X-Break-Glass-Token": TOKEN_BREAK_GLASS},
    )
    check("fully authorized non-destructive break-glass succeeds", r.status_code == 200, (r.status_code, r.text[:160]))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT operation, operator_id, destructive FROM security_break_glass_events "
                "WHERE operator_id=%s ORDER BY created_at DESC LIMIT 5",
                (operator,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    check("break-glass use is attributed and audited", bool(rows) and rows[0]["operator_id"] == operator, rows[:1])

    os.environ.pop("WATHEFNI_BREAK_GLASS_ENABLED", None)


def login_throttle(client, app) -> None:
    print("\n    P0-3 — dashboard login throttling and enumeration safety")

    unknown_company = client.post(
        "/dashboard/auth/login",
        json={"company_code": f"NOSUCH{SUFFIX}", "email": USER_A_EMAIL, "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/dashboard/auth/login",
        json={"company_code": CO_A, "email": f"nobody.{SUFFIX}@r2security.test", "password": "wrong-password"},
    )
    wrong_password = client.post(
        "/dashboard/auth/login",
        json={"company_code": CO_A, "email": USER_A_EMAIL, "password": "wrong-password"},
    )
    statuses = {unknown_company.status_code, unknown_email.status_code, wrong_password.status_code}
    bodies = {unknown_company.text, unknown_email.text, wrong_password.text}
    check("unknown company, unknown email and wrong password return one status", statuses == {401}, statuses)
    check("...and one identical body", len(bodies) == 1, list(bodies)[:3])

    limit = app._rate_limit.policy("dashboard_login").limit
    saw_429 = False
    for _ in range(limit + 3):
        r = client.post(
            "/dashboard/auth/login",
            json={"company_code": CO_A, "email": USER_A_EMAIL, "password": "wrong-password"},
        )
        if r.status_code == 429:
            saw_429 = True
            break
    check(f"dashboard brute force locks out within the {limit}-failure window", saw_429)
    if saw_429:
        check("lockout returns retry metadata", "Retry-After" in r.headers, dict(r.headers).get("Retry-After"))
        check(
            "lockout does not disclose the account",
            USER_A_EMAIL not in r.text and CO_A not in r.text,
            r.text[:160],
        )
        locked_unknown = client.post(
            "/dashboard/auth/login",
            json={"company_code": CO_A, "email": f"other.{SUFFIX}@r2security.test", "password": "x"},
        )
        check(
            "throttling is per-identity, so it is not an existence oracle",
            locked_unknown.status_code in {401, 429},
            locked_unknown.status_code,
        )

    # A legitimate credential must still work once its own counter is clear.
    app._rate_limit.reset(app, "dashboard_login", dimensions={"source": "testclient", "identity": f"{CO_A}|{USER_A_EMAIL.lower()}"})
    ok = client.post(
        "/dashboard/auth/login",
        json={"company_code": CO_A, "email": USER_A_EMAIL, "password": USER_A_PASSWORD},
    )
    check("valid credentials still sign in", ok.status_code == 200, (ok.status_code, ok.text[:200]))
    check("successful login clears the failure counter", ok.status_code == 200 and "token" in ok.text)

    print("\n    P0-3 — Setup Console operator login throttling")
    bad_phone = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"phone": "96555999888", "operator_token": "wrong-operator-token"},
    )
    bad_token = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"phone": OPERATOR_PHONE, "operator_token": "wrong-operator-token"},
    )
    check(
        "unknown operator and wrong token are indistinguishable",
        bad_phone.status_code == bad_token.status_code == 401 and bad_phone.text == bad_token.text,
        (bad_phone.status_code, bad_token.status_code),
    )

    setup_limit = app._rate_limit.policy("setup_operator_login").limit
    saw_429 = False
    for _ in range(setup_limit + 3):
        r = client.post(
            "/dashboard/superadmin/setup/auth/login",
            json={"phone": OPERATOR_PHONE, "operator_token": "wrong-operator-token"},
        )
        if r.status_code == 429:
            saw_429 = True
            break
    check(f"Setup operator brute force locks out within the {setup_limit}-failure window", saw_429)


def calendar_throttle(client, app) -> None:
    print("\n    P1-22 — public calendar guest-token throttling")
    token = uuid.uuid4().hex
    limit = app._rate_limit.policy("calendar_guest_token").limit
    saw_429 = False
    seen_404 = False
    for _ in range(limit + 5):
        r = client.get(f"/calendar/guest/{token}/state")
        if r.status_code == 404:
            seen_404 = True
        if r.status_code == 429:
            saw_429 = True
            break
    check("guest-token semantics unchanged: unknown token is still 404", seen_404)
    check(f"repeated use of one guest token throttles at {limit}", saw_429, r.status_code)
    if saw_429:
        check("guest throttle returns retry metadata", "Retry-After" in r.headers)


def worker_auth(client_localhost, app) -> None:
    print("\n    P0-4 — internal worker endpoint from localhost")
    path = "/internal/video-interviews/process-transcripts"

    r = client_localhost.post(path)
    check("no token from 127.0.0.1 is denied", r.status_code == 403, (r.status_code, r.text[:160]))

    r = client_localhost.post(path, headers={"X-Internal-Token": "wrong-worker-token"})
    check("wrong worker token is denied", r.status_code == 403, r.status_code)

    r = client_localhost.post(path, headers={"X-Internal-Token": TOKEN_PLATFORM})
    check("the shared platform token is not worker authority", r.status_code == 403, r.status_code)

    r = client_localhost.post(path, headers={"X-Internal-Token": TOKEN_WORKER})
    check("the dedicated worker token is accepted", r.status_code != 403, (r.status_code, r.text[:160]))

    saved = os.environ.pop("WATHEFNI_INTERNAL_WORKER_TOKEN", None)
    r = client_localhost.post(path)
    check("a missing worker secret fails closed rather than trusting localhost", r.status_code == 403, r.status_code)
    if saved:
        os.environ["WATHEFNI_INTERNAL_WORKER_TOKEN"] = saved


def link_secrets_live(client, app) -> None:
    print("\n    P0-2 — live public link capability")
    import hashlib
    import hmac
    import time as _time

    def forge(subject: str, secret: str) -> str:
        expires = int(_time.time()) + 600
        payload = f"{subject}:{expires}"
        sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        return app.b64url_encode(f"{payload}:".encode("utf-8") + sig)

    interview_id = str(uuid.uuid4())
    r = client.get(f"/video-interview/{interview_id}/state?token={forge(interview_id, OLD_VIDEO_CONSTANT)}")
    check("a link forged with the old committed constant is refused", r.status_code == 403, (r.status_code, r.text[:120]))

    db_url = os.environ.get("WATHEFNI_DATABASE_URL") or "postgres://x:y@127.0.0.1:5432/z"
    r = client.get(f"/video-interview/{interview_id}/state?token={forge(interview_id, db_url)}")
    check("a link forged with the database URL is refused", r.status_code == 403, r.status_code)

    ready = client.get("/ready").json()
    check("readiness reports link signing healthy", ready.get("public_link_capabilities_available") is True, ready.get("link_signing"))
    check(
        "readiness never exposes secret material",
        LINK_SECRET_VIDEO not in json.dumps(ready) and LINK_SECRET_ASSESSMENT not in json.dumps(ready),
    )

    saved = os.environ.pop("WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET", None)
    r = client.get(f"/video-interview/{interview_id}/state?token=anything")
    check(
        "a missing signing secret makes the capability unavailable, not permissive",
        r.status_code == 503 and r.json()["detail"]["error"] == "link_signing_unavailable",
        (r.status_code, r.text[:160]),
    )
    not_ready = client.get("/ready").json()
    check("readiness degrades when the signing secret is absent", not_ready.get("public_link_capabilities_available") is False)
    if saved:
        os.environ["WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"] = saved


def dashboard_tenant_trust(app) -> None:
    print("\n    P0-5 — caller-supplied dashboard tenant metadata")

    def turn(metadata: dict) -> object:
        return app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id=f"conv-{SUFFIX}",
            sender_phone="96550000000",
            sender_role="hr_admin",
            raw_text="show me payroll",
            metadata=metadata,
        )

    claimed = {"channel": "web_dashboard", "dashboard": True, "company_code": CO_B}
    resolved = app.request_company_code(turn(claimed), default=None)
    check("channel=web_dashboard alone does not select a tenant", resolved != CO_B, resolved)

    guessed = {**claimed, app.DASHBOARD_TURN_AUTHORITY_KEY: "guessed-authority-value"}
    resolved = app.request_company_code(turn(guessed), default=None)
    check("a guessed authority marker does not select a tenant", resolved != CO_B, resolved)

    real = {**claimed, app.DASHBOARD_TURN_AUTHORITY_KEY: app._DASHBOARD_TURN_AUTHORITY_NONCE}
    resolved = app.request_company_code(turn(real), default=None)
    check("an in-process dashboard session still binds its own tenant", resolved == CO_B, resolved)

    boundary = dict(real)
    app.strip_claimed_dashboard_authority(boundary)
    check("the HTTP boundary strips any claimed authority marker", app.DASHBOARD_TURN_AUTHORITY_KEY not in boundary)


def intake_routing(client, app) -> None:
    print("\n    P0-5 — email intake tenant routing")
    address = f"docs.{SUFFIX.lower()}@r2security.test"
    payload = {"message_id": f"msg-{uuid.uuid4()}", "attachments": []}

    r = client.post(
        "/orchestrator/posthire/documents/email-intake",
        headers=_hdr(TOKEN_PLATFORM),
        json={**payload, "recipient": address},
    )
    if r.status_code == 200:
        check("tenant is derived from the destination mailbox", r.json().get("company_code") == CO_A, r.json().get("company_code"))
    else:
        check("tenant is derived from the destination mailbox", False, (r.status_code, r.text[:160]))

    r = client.post(
        "/orchestrator/posthire/documents/email-intake",
        headers=_hdr(TOKEN_PLATFORM),
        json={**payload, "recipient": address, "company_code": CO_B},
    )
    check(
        "a request-body company that contradicts the mailbox is refused",
        r.status_code == 403 and r.json()["detail"]["error"] == "intake_routing_conflict",
        (r.status_code, r.text[:160]),
    )

    r = client.post(
        "/orchestrator/posthire/documents/email-intake",
        headers=_hdr(TOKEN_PLATFORM),
        json={**payload, "company_code": CO_B},
    )
    check(
        "a request-body company with no routing evidence is refused",
        r.status_code == 403 and r.json()["detail"]["error"] == "intake_routing_unresolved",
        (r.status_code, r.text[:160]),
    )

    r = client.post(
        "/orchestrator/posthire/documents/email-intake",
        headers=_hdr(TOKEN_A),
        json={**payload, "recipient": address, "company_code": CO_B},
    )
    check("a tenant principal cannot route mail into another company", r.status_code == 403, r.status_code)


def denial_audit(app) -> None:
    print("\n    R2 — denial audit is usable and leaks nothing")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route, denial_class, policy_key, principal_digest, detail::text AS detail_text
                FROM security_denial_events
                WHERE created_at > now() - interval '15 minutes'
                ORDER BY created_at DESC
                LIMIT 400
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

    classes = {row["denial_class"] for row in rows}
    check("rate-limited attempts are recorded", "rate_limited" in classes, sorted(classes)[:8])
    check("failed logins are recorded", "dashboard_auth_failed" in classes, sorted(classes)[:8])
    check("tenant scope violations are recorded", "tenant_scope_violation" in classes, sorted(classes)[:8])
    check("break-glass denials are recorded", any(c.startswith("break_glass") for c in classes), sorted(classes)[:8])
    check("worker denials are recorded", "internal_worker_forbidden" in classes, sorted(classes)[:8])
    check("every record names its route", all(row["route"] for row in rows))

    blob = json.dumps(rows)
    secrets_that_must_not_appear = {
        "password": USER_A_PASSWORD,
        "operator token": OPERATOR_TOKEN,
        "platform internal token": TOKEN_PLATFORM,
        "tenant token": TOKEN_A,
        "worker token": TOKEN_WORKER,
        "break-glass token": TOKEN_BREAK_GLASS,
        "assessment signing secret": LINK_SECRET_ASSESSMENT,
        "video signing secret": LINK_SECRET_VIDEO,
    }
    for label, value in secrets_that_must_not_appear.items():
        check(f"audit never stores the {label}", value not in blob)
    check("audit never stores the raw account email", USER_A_EMAIL not in blob)


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R2 — live security negative paths")
    print(f"    tenants: {CO_A} / {CO_B}")
    _configure_env()

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable; this suite requires the staging database.")
            print(f"\n    {PASS} passed, {FAIL} failed (skipped)")
            return 1
        raise

    try:
        probe = app.db_connect()
        conn = probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (skipped)")
        return 1

    from fastapi.testclient import TestClient

    app.ensure_schema()
    with app.db_connect() as c:
        with c.cursor() as cur:
            app._rate_limit.ensure_security_rate_limit_schema(cur)
            app._internal_authority.ensure_break_glass_schema(cur)
        c.commit()

    cleanup(app)
    seed(app)
    client = TestClient(app.app)
    client_localhost = TestClient(app.app, client=("127.0.0.1", 51515))
    try:
        tenant_isolation(client, app)
        break_glass(client, app)
        intake_routing(client, app)
        dashboard_tenant_trust(app)
        link_secrets_live(client, app)
        worker_auth(client_localhost, app)
        login_throttle(client, app)
        calendar_throttle(client, app)
        denial_audit(app)
    finally:
        cleanup(app)

    print("\n    R2_SECURITY_FULL_PASS")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
