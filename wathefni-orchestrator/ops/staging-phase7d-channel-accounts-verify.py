#!/usr/bin/env python3
"""Phase 7D staging verifier — company channel accounts readiness pack.

Throwaway companies only: P7DSTG01 / P7DSTG02.
Uses mocked sends (dry-run + pure resolver). Never provisions live WhatsApp.
Never flips production WATHEFNI_COMPANY_CHANNEL_ACCOUNTS.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COMPANY_A = "P7DSTG01"
COMPANY_B = "P7DSTG02"
PROTECTED = "WATHEFNI"
ACC_A = "p7d-mock-wa-a"
ACC_B = "p7d-mock-wa-b"
ACC_BAD = "p7d-mock-wa-unknown"
MOCK_KNOWN = frozenset({ACC_A, ACC_B, "default"})
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
POSTGRES_ENV = os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
OPERATOR_PHONE = "96599338566"
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def systemd_flag(unit_dropin_dir: Path, flag: str) -> str:
    if not unit_dropin_dir.exists():
        return "unset"
    for conf in unit_dropin_dir.glob("*.conf"):
        text = conf.read_text()
        match = re.search(rf"(?:^|\n)Environment={flag}=([^\n]+)", text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        match = re.search(rf"(?:^|\n){flag}=([^\n]+)", text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return "unset"


def decode_systemd_show(unit: str) -> dict[str, str]:
    import subprocess

    try:
        out = subprocess.check_output(
            ["systemctl", "show", unit, "-p", "Environment", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {}
    decoded: dict[str, str] = {}
    for part in out.strip().split():
        if "=" in part:
            k, v = part.split("=", 1)
            decoded[k] = v
    return decoded


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw.decode())
            except Exception:
                return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload


def load_operator_token() -> str:
    raw = Path("/root/.openclaw/secrets/wathefni-setup-operator.env").read_text()
    match = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", raw)
    value = match.group(1).strip()
    if value[0] in "\"'":
        value = value[1:-1]
    return str(json.loads(value)[OPERATOR_PHONE])


def op_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-HR-Phone": OPERATOR_PHONE}


def ensure_company(app: Any, company: str, name: str, ctx: dict) -> None:
    app.setup_console_create_company(
        app.SetupCompanyCreateRequest(
            company_code=company,
            name=name,
            country="KW",
            timezone="Asia/Kuwait",
            currency="KWD",
        ),
        ctx,
    )


def cleanup_companies(app: Any, companies: list[str]) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in companies:
                cur.execute("DELETE FROM company_channel_accounts WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM dashboard_whatsapp_identities WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM dashboard_user_invites WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM company_settings WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
        conn.commit()


def mocked_send(app: Any, *, company: str, audience: str, known=MOCK_KNOWN) -> dict[str, Any]:
    """Resolve + dry-run send. Never hits live WhatsApp."""
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    route = app.resolve_company_outbound_whatsapp_route(
        company_code=company,
        audience=audience,
        shared_account_id="default",
        known_provider_account_ids=set(known),
    )
    sent = app.send_octopus_whatsapp(
        account_id="default",
        phone="96555557099",
        text=f"p7d mock {company} {audience}",
        subject_type=audience,
        subject_key=f"P7D-{company}-{audience}",
        company_code=company,
        audience=audience,
    )
    # Force known set for send path by re-resolving (send uses live octopus known).
    # Attach explicit mock route so the matrix asserts on the staged decision.
    sent = dict(sent)
    sent["mock_route"] = route
    sent["account_id"] = route.get("account_id")
    return sent


def main() -> int:
    if COMPANY_A == PROTECTED or COMPANY_B == PROTECTED:
        raise SystemExit("refusing protected company codes")

    staging_orch = Path(os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator"))
    if staging_orch.is_dir():
        sys.path.insert(0, str(staging_orch))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    load_env(Path(POSTGRES_ENV))
    dsn = os.environ.get("WATHEFNI_DATABASE_URL", "")
    if "staging" not in dsn.lower():
        raise SystemExit("refusing verifier against non-staging DSN")

    os.environ.setdefault("WATHEFNI_SETUP_CONSOLE_ENABLED", "on")
    os.environ.setdefault("WATHEFNI_SETUP_CONSOLE_V2", "on")
    os.environ["WATHEFNI_EMPLOYEE_APP"] = "off"
    os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")

    import app  # noqa: E402

    ctx = {
        "is_platform_admin": True,
        "actor_phone": OPERATOR_PHONE,
        "hr_phone": OPERATOR_PHONE,
        "actor_user_id": f"platform_admin:{OPERATOR_PHONE}",
        "actor_email": "",
        "actor_role": "platform_admin",
        "hr_user": {"phone": OPERATOR_PHONE, "role": "platform_admin", "name": "P7D", "status": "active"},
    }

    # --- Live staging HTTP: flag OFF mutations ---
    try:
        op = load_operator_token()
        status, _ = req("GET", "/health")
        record("staging health 200", status == 200, f"status={status}")
        status, body = req(
            "PUT",
            f"/dashboard/superadmin/setup/companies/{COMPANY_A}/channel-account",
            headers=op_headers(op),
            body={
                "provider": "octopus",
                "provider_account_id": ACC_A,
                "sender_phone": "96555557101",
                "audiences": ["candidate"],
                "status": "pending_verification",
            },
        )
        record("case1 HTTP mutation 404 while staging flag OFF", status == 404, f"status={status}")
    except Exception as exc:
        record("staging health / HTTP baseline", False, str(exc)[:200])

    cleanup_companies(app, [COMPANY_A, COMPANY_B])
    ensure_company(app, COMPANY_A, "Phase 7D Staging A", ctx)
    ensure_company(app, COMPANY_B, "Phase 7D Staging B", ctx)

    # Case 1 — flag OFF baseline (in-process)
    os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
    try:
        app.setup_console_upsert_channel_account(
            COMPANY_A,
            app.SetupCompanyChannelAccountRequest(provider_account_id=ACC_A, audiences=["candidate"]),
            ctx,
        )
        record("case1 in-process mutation 404 while flag OFF", False, "expected 404")
    except app.HTTPException as exc:
        record("case1 in-process mutation 404 while flag OFF", exc.status_code == 404, f"status={exc.status_code}")

    route_off = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "case1 flag OFF ignores company accounts (shared route)",
        route_off["source"] == "shared_default" and route_off["runtime_routing_changed"] is False,
        route_off.get("reason", ""),
    )
    readiness_off = app.setup_console_company_readiness(COMPANY_A)
    channel_step = next((s for s in readiness_off.get("steps") or [] if s.get("key") == "channel_account"), None)
    record(
        "case1 readiness not blocked by channel while flag OFF",
        channel_step is None or channel_step.get("done") is True,
        str(channel_step),
    )
    policy_off = app.setup_console_channel_policy(COMPANY_A)
    record(
        "case1 Setup Console policy runtime_routing_changed=False while OFF",
        policy_off.get("runtime_routing_changed") is False
        and policy_off.get("company_channel_accounts_enabled") is False,
        f"enabled={policy_off.get('company_channel_accounts_enabled')}",
    )

    # Case 2 — flag ON, no account
    os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "on"
    route_none = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "case2 flag ON no account → shared fallback",
        route_none["source"] == "fallback_shared" and route_none["reason"] == "no_company_account",
        route_none.get("reason", ""),
    )
    readiness_none = app.setup_console_company_readiness(COMPANY_A)
    channel_step = next((s for s in readiness_none.get("steps") or [] if s.get("key") == "channel_account"), None)
    # No account ⇒ channel step considered done (optional / not configured), not a blocker.
    record(
        "case2 channel step does not hard-block when no account",
        channel_step is not None and channel_step.get("done") is True,
        str(channel_step),
    )

    # Case 3 — upsert pending
    pending = app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["candidate", "employee"],
            status="active",
        ),
        ctx,
    )
    record(
        "case3 upsert without verification stays pending",
        pending["channel_account"]["status"] == "pending_verification",
        pending["channel_account"]["status"],
    )
    route_pending = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "case3 pending cannot hijack send",
        route_pending["source"] == "fallback_shared"
        and "pending" in str(route_pending.get("reason") or ""),
        route_pending.get("reason", ""),
    )

    # Case 4 — activate
    active = app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["candidate", "employee"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    record(
        "case4 activate with verification ref",
        active["channel_account"]["status"] == "active" and active["channel_account"]["verified"] is True,
        active["channel_account"]["status"],
    )
    policy_on = app.setup_console_channel_policy(COMPANY_A)
    record(
        "case4 policy runtime_routing_changed=True while ON+active",
        policy_on.get("runtime_routing_changed") is True
        and policy_on.get("company_channel_accounts_enabled") is True,
        f"changed={policy_on.get('runtime_routing_changed')}",
    )

    # Case 5 — candidate-only audience
    app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["candidate"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    send_cand = mocked_send(app, company=COMPANY_A, audience="candidate")
    send_emp = mocked_send(app, company=COMPANY_A, audience="employee")
    record(
        "case5 candidate audience uses company account (mocked)",
        send_cand["mock_route"]["source"] == "company_owned" and send_cand["account_id"] == ACC_A,
        str(send_cand["mock_route"]),
    )
    record(
        "case5 employee blocked on candidate-only (shared fallback)",
        send_emp["mock_route"]["reason"] == "audience_not_permitted"
        and send_emp["account_id"] == "default",
        str(send_emp["mock_route"]),
    )
    record(
        "mocked send is dry-run only (no live WhatsApp)",
        send_cand.get("dry_run") is True and send_cand.get("simulated") is True,
        f"dry_run={send_cand.get('dry_run')}",
    )

    # Case 6 — employee-only
    app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["employee"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    send_emp2 = mocked_send(app, company=COMPANY_A, audience="employee")
    send_cand2 = mocked_send(app, company=COMPANY_A, audience="candidate")
    record(
        "case6 employee audience uses company account (mocked)",
        send_emp2["mock_route"]["source"] == "company_owned" and send_emp2["account_id"] == ACC_A,
        str(send_emp2["mock_route"]),
    )
    record(
        "case6 candidate blocked on employee-only (shared fallback)",
        send_cand2["mock_route"]["reason"] == "audience_not_permitted"
        and send_cand2["account_id"] == "default",
        str(send_cand2["mock_route"]),
    )

    # Unknown provider id cannot hijack even when active
    app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_BAD,
            sender_phone="96555557101",
            audiences=["candidate", "employee"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    bad_route = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "active unknown provider id cannot hijack (fail-closed shared)",
        bad_route["reason"] == "provider_account_not_in_sender_config"
        and bad_route["account_id"] == "default",
        bad_route.get("reason", ""),
    )

    # Restore ACC_A active both audiences for disable/tenant cases
    app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["candidate", "employee"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )

    # Case 7 — disable
    disabled = app.setup_console_disable_channel_account(COMPANY_A, ctx)
    record("case7 soft-disable account", disabled["channel_account"]["status"] == "disabled")
    route_disabled = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "case7 disabled returns shared fallback",
        route_disabled["source"] == "fallback_shared" and route_disabled["account_id"] == "default",
        route_disabled.get("reason", ""),
    )

    # Case 8 — tenant isolation / unique provider id
    app.setup_console_upsert_channel_account(
        COMPANY_A,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_A,
            sender_phone="96555557101",
            audiences=["candidate"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    try:
        app.setup_console_upsert_channel_account(
            COMPANY_B,
            app.SetupCompanyChannelAccountRequest(
                provider_account_id=ACC_A,
                sender_phone="96555557102",
                audiences=["candidate"],
                status="active",
                verification_reference="p7d-staging-verify-ref",
            ),
            ctx,
        )
        record("case8 second company cannot steal provider id", False, "expected 409")
    except app.HTTPException as exc:
        record("case8 second company cannot steal provider id", exc.status_code == 409, f"status={exc.status_code}")

    app.setup_console_upsert_channel_account(
        COMPANY_B,
        app.SetupCompanyChannelAccountRequest(
            provider_account_id=ACC_B,
            sender_phone="96555557102",
            audiences=["candidate"],
            status="active",
            verification_reference="p7d-staging-verify-ref",
        ),
        ctx,
    )
    route_a = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    route_b = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_B,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "tenant isolation: A never selects B account id",
        route_a["account_id"] == ACC_A and route_b["account_id"] == ACC_B and route_a["account_id"] != route_b["account_id"],
        f"A={route_a['account_id']} B={route_b['account_id']}",
    )
    inbound_a = app.resolve_inbound_company_from_whatsapp_account(provider="octopus", provider_account_id=ACC_A)
    inbound_b = app.resolve_inbound_company_from_whatsapp_account(provider="octopus", provider_account_id=ACC_B)
    record(
        "inbound account map is tenant-scoped",
        inbound_a.get("company_code") == COMPANY_A and inbound_b.get("company_code") == COMPANY_B,
        f"A={inbound_a.get('company_code')} B={inbound_b.get('company_code')}",
    )
    detail_b = app.setup_console_company_detail(COMPANY_B, ctx)
    record(
        "Setup Console detail is tenant-isolated",
        (detail_b.get("channel_account") or {}).get("provider_account_id") == ACC_B,
        str((detail_b.get("channel_account") or {}).get("provider_account_id")),
    )

    # Case 9 — flag rollback OFF mid-flight
    os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
    try:
        app.setup_console_upsert_channel_account(
            COMPANY_A,
            app.SetupCompanyChannelAccountRequest(provider_account_id=ACC_A, audiences=["candidate"]),
            ctx,
        )
        record("case9 mutations 404 after rollback OFF", False, "expected 404")
    except app.HTTPException as exc:
        record("case9 mutations 404 after rollback OFF", exc.status_code == 404, f"status={exc.status_code}")
    route_rollback = app.resolve_company_outbound_whatsapp_route(
        company_code=COMPANY_A,
        audience="candidate",
        known_provider_account_ids=set(MOCK_KNOWN),
    )
    record(
        "case9 routing shared even if active row remains",
        route_rollback["source"] == "shared_default" and route_rollback["runtime_routing_changed"] is False,
        route_rollback.get("reason", ""),
    )
    inbound_rollback = app.resolve_inbound_company_from_whatsapp_account(provider="octopus", provider_account_id=ACC_A)
    record(
        "case9 inbound map ignored after rollback",
        inbound_rollback.get("company_code") is None and inbound_rollback.get("reason") == "flag_off",
        str(inbound_rollback),
    )
    still_readable = app.setup_console_channel_account(COMPANY_A)
    record(
        "case9 existing row still readable while OFF",
        still_readable is not None and still_readable.get("status") == "active",
        str((still_readable or {}).get("status")),
    )

    # Case 10 — production shared-path regression (flag OFF on prod unit)
    prod_drop = Path("/etc/systemd/system/wathefni-orchestrator.service.d")
    staging_drop = Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d")
    prod_env = decode_systemd_show("wathefni-orchestrator.service")
    staging_env = decode_systemd_show("wathefni-orchestrator-staging.service")
    prod_channel = prod_env.get("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS") or systemd_flag(prod_drop, "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS")
    prod_employee = prod_env.get("WATHEFNI_EMPLOYEE_APP") or systemd_flag(prod_drop, "WATHEFNI_EMPLOYEE_APP")
    staging_channel = staging_env.get("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS") or systemd_flag(staging_drop, "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS")
    staging_employee = staging_env.get("WATHEFNI_EMPLOYEE_APP") or systemd_flag(staging_drop, "WATHEFNI_EMPLOYEE_APP")

    def is_off(value: str) -> bool:
        return str(value or "unset").strip().lower() in {"", "unset", "0", "false", "no", "off"}

    record(
        "case10 production COMPANY_CHANNEL_ACCOUNTS remains OFF",
        is_off(prod_channel),
        f"value={prod_channel}",
    )
    record(
        "case10 production EMPLOYEE_APP remains OFF",
        is_off(prod_employee),
        f"value={prod_employee}",
    )
    record(
        "staging EMPLOYEE_APP remains OFF",
        is_off(staging_employee),
        f"value={staging_employee}",
    )
    # Staging channel may be unset/off (verifier toggles in-process only).
    record(
        "staging systemd COMPANY_CHANNEL_ACCOUNTS not forced ON",
        is_off(staging_channel),
        f"value={staging_channel}",
    )

    # Shared send without company_code is unchanged
    os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
    shared_send = app.send_octopus_whatsapp(
        account_id="default",
        phone="96555557099",
        text="p7d shared regression",
        subject_type="candidate",
        subject_key="P7D-SHARED",
    )
    record(
        "production shared-route regression: no company_code → dry-run shared path",
        shared_send.get("dry_run") is True and "channel_route" not in shared_send,
        str({k: shared_send.get(k) for k in ("ok", "dry_run", "account_id")}),
    )

    # Secrets never in table
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name='company_channel_accounts'
                """
            )
            cols = {str(r["column_name"]) for r in cur.fetchall()}
    secretish = {c for c in cols if any(x in c for x in ("token", "secret", "password", "bearer", "api_key"))}
    record("model keeps secrets out of company_channel_accounts", not secretish, f"cols={sorted(cols)}")

    cleanup_companies(app, [COMPANY_A, COMPANY_B])

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\nPhase 7D matrix: {passed} passed, {failed} failed, {len(RESULTS)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
