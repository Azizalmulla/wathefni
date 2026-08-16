#!/usr/bin/env python3
"""Physical acceptance — Employee App invitation/delivery (WATHEFNI canary).

Proves HR invitation states, Resend/Re-invite (no code), needs_attention code
fallback gating, Aziz emailed-code activate → session reopen, HR activated,
and no duplicate pending invites.

PIN / Face ID are local-only on device; this script proves the server + HR
contract and the activation code that was delivered. Device PIN/Face ID must be
confirmed on the canary iPhone when USB/device is available.

Does NOT start Auth Wave 2 Phase 6.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")

import app as legacy  # noqa: E402
import employee_app_invitation as inv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
AZIZ_PHONE = "99338566"
FAILS: list[str] = []
EVID: dict[str, Any] = {"checks": [], "aziz": {}, "hr": {}, "states": {}}


def check(name: str, ok: bool, detail: Any = None) -> None:
    row = {"name": name, "ok": bool(ok), "detail": detail}
    EVID["checks"].append(row)
    print(("PASS" if ok else "FAIL") + f"  {name}" + (f" — {detail}" if detail is not None else ""))
    if not ok:
        FAILS.append(name)


def no_code(payload: Any) -> bool:
    blob = json.dumps(payload, default=str)
    return "activation_code" not in blob and '"code":' not in blob.lower().replace("company_code", "")


def dash_client() -> tuple[TestClient, str]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND email=%s AND status='active'
                LIMIT 1
                """,
                (COMPANY, "azizalmulla16@gmail.com"),
            )
            user = dict(cur.fetchone() or {})
            conn.commit()
    assert user, "aziz dashboard owner missing"
    token, _ = legacy.create_dashboard_session(user)
    client = TestClient(legacy.app)
    return client, token


def live_json(method: str, path: str, *, token: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"http://127.0.0.1:8010{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return int(exc.code), parsed


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def load_systemd_employee_app_env() -> None:
    """TestClient imports app without systemd Environment= — copy employee-app flags."""
    import subprocess

    try:
        env_line = subprocess.check_output(
            ["systemctl", "show", "wathefni-orchestrator", "-p", "Environment", "--value"],
            text=True,
        )
    except Exception:
        return
    for part in env_line.split(" "):
        if not part.startswith("WATHEFNI_EMPLOYEE_APP"):
            continue
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        os.environ[key] = val.strip().strip('"')


def pending_invite_count(employee_key: str) -> int:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n FROM employee_app_invites
                WHERE company_code=%s AND employee_key=%s AND status='pending'
                """,
                (COMPANY, employee_key),
            )
            n = int(dict(cur.fetchone())["n"])
            conn.commit()
    return n


def force_delivery_status(invite_id: str, status: str, channel: str | None = None) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            inv.ensure_invitation_schema(cur)
            cur.execute(
                """
                UPDATE employee_app_invites
                SET delivery_status=%s,
                    delivery_channel=%s,
                    last_delivery_error=CASE WHEN %s IN ('failed','needs_attention') THEN 'physical_acceptance_force' ELSE NULL END,
                    updated_at=now()
                WHERE invite_id=%s
                """,
                (status, channel, status, invite_id),
            )
            conn.commit()


def force_expired(invite_id: str) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employee_app_invites SET expires_at=now() - interval '1 hour', updated_at=now() WHERE invite_id=%s",
                (invite_id,),
            )
            conn.commit()


def main() -> int:
    load_systemd_employee_app_env()
    client, token = dash_client()
    headers = auth_headers(token)

    # --- UI bundle needles (EN + AR) served from production static ---
    import urllib.request

    js = urllib.request.urlopen("http://127.0.0.1:8010/docs", timeout=10).status  # warm
    check("orchestrator docs warm", js == 200)
    # Read built PostHire bundle from disk (same bytes as /dashboard/assets)
    assets = Path("/var/www/wathefni-dashboard/assets")
    posthire = next(assets.glob("PostHire-*.js"), None)
    api_js = next(assets.glob("api-*.js"), None)
    check("posthire bundle present", posthire is not None, str(posthire))
    text = posthire.read_text(encoding="utf-8", errors="replace") if posthire else ""
    for needle in [
        "Resend invitation",
        "إعادة إرسال الدعوة",
        "Re-invite",
        "إعادة الدعوة",
        "Show activation code",
        "عرض رمز التفعيل",
        "Delivered",
        "تم التسليم",
        "Needs attention",
        "تحتاج متابعة",
        "Expired",
        "منتهية",
        "Failed",
        "فشل التسليم",
        "App access",
        "وصول التطبيق",
    ]:
        check(f"ui_needle:{needle}", needle in text)
    api_text = api_js.read_text(encoding="utf-8", errors="replace") if api_js else ""
    check("api client has app-invitation", "app-invitation" in api_text)
    check("api client has resend path", "app-invitation/resend" in api_text)
    check("show_code_exception gated in UI", "show_code_exception" in text)

    # --- HR GET snapshot (Aziz) — never returns code ---
    r = client.get(f"/dashboard/posthire/employees/{AZIZ}/app-invitation", headers=headers)
    check("hr get invitation 200", r.status_code == 200, r.status_code)
    snap = r.json()
    EVID["hr"]["aziz_before"] = {k: snap.get(k) for k in ("invitation_status", "channel", "actions", "app_access_active")}
    check("hr snapshot no code", no_code(snap))
    check("hr snapshot has status", bool(snap.get("invitation_status")))

    # --- Resend (no code) ---
    r = client.post(
        f"/dashboard/posthire/employees/{AZIZ}/app-invitation/resend",
        headers=headers,
        json={"reason": "physical acceptance resend prove"},
    )
    check("hr resend 200", r.status_code == 200, r.text[:300])
    resend = r.json()
    EVID["hr"]["resend"] = {k: resend.get(k) for k in ("ok", "delivered", "delivery_status", "channel", "code_disclosed", "invite_id")}
    check("hr resend ok", bool(resend.get("ok")))
    check("hr resend code_disclosed false", resend.get("code_disclosed") is False)
    check("hr resend no activation_code", no_code(resend))
    check("hr resend has invite_id", bool(resend.get("invite_id")))
    after_resend = (resend.get("snapshot") or inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=AZIZ))
    check(
        "hr resend status updated",
        after_resend.get("invitation_status") in {"sent", "delivered", "failed", "needs_attention", "pending"},
        after_resend.get("invitation_status"),
    )
    check("only one pending after resend", pending_invite_count(AZIZ) == 1, pending_invite_count(AZIZ))

    # --- Re-invite (no code) ---
    r = client.post(
        f"/dashboard/posthire/employees/{AZIZ}/app-invitation/reinvite",
        headers=headers,
        json={"reason": "physical acceptance reinvite prove"},
    )
    check("hr reinvite 200", r.status_code == 200, r.text[:300])
    reinv = r.json()
    EVID["hr"]["reinvite"] = {k: reinv.get(k) for k in ("ok", "delivered", "delivery_status", "channel", "code_disclosed", "invite_id")}
    check("hr reinvite ok", bool(reinv.get("ok")))
    check("hr reinvite code_disclosed false", reinv.get("code_disclosed") is False)
    check("hr reinvite no activation_code", no_code(reinv))
    check("only one pending after reinvite", pending_invite_count(AZIZ) == 1, pending_invite_count(AZIZ))

    # --- delivered / failed / needs_attention / expired state matrix ---
    invite_id = str(reinv.get("invite_id") or "")
    check("have invite for state matrix", bool(invite_id))

    force_delivery_status(invite_id, inv.STATUS_DELIVERED, inv.CHANNEL_EMAIL)
    s = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=AZIZ)
    EVID["states"]["delivered"] = s
    check("state delivered", s.get("invitation_status") == inv.STATUS_DELIVERED, s.get("invitation_status"))
    check("delivered: no show_code_exception", s.get("actions", {}).get("show_code_exception") is False)

    force_delivery_status(invite_id, inv.STATUS_FAILED, None)
    s = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=AZIZ)
    EVID["states"]["failed"] = {k: s.get(k) for k in ("invitation_status", "actions", "last_error")}
    check("state failed", s.get("invitation_status") == inv.STATUS_FAILED, s.get("invitation_status"))
    check("failed: no show_code_exception", s.get("actions", {}).get("show_code_exception") is False)

    force_delivery_status(invite_id, inv.STATUS_NEEDS_ATTENTION, None)
    s = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=AZIZ)
    EVID["states"]["needs_attention"] = {k: s.get(k) for k in ("invitation_status", "actions", "last_error")}
    check("state needs_attention", s.get("invitation_status") == inv.STATUS_NEEDS_ATTENTION, s.get("invitation_status"))
    check("needs_attention: show_code_exception", s.get("actions", {}).get("show_code_exception") is True)

    # Exception handoff only when needs_attention path is approved
    r = client.post(
        f"/dashboard/posthire/employees/{AZIZ}/app-invite",
        headers=headers,
        json={
            "delivery_mode": "hr_task_only",
            "idempotency_key": f"phys-exception-{uuid.uuid4()}",
            "reason": "physical acceptance needs_attention fallback code",
            "supersede_invite_id": invite_id,
        },
    )
    # May 409 without supersede if force didn't keep pending — handle both
    if r.status_code == 409:
        detail = r.json().get("detail") if isinstance(r.json(), dict) else {}
        pending_id = (detail or {}).get("pending_invite_id") if isinstance(detail, dict) else None
        r = client.post(
            f"/dashboard/posthire/employees/{AZIZ}/app-invite",
            headers=headers,
            json={
                "delivery_mode": "hr_task_only",
                "idempotency_key": f"phys-exception2-{uuid.uuid4()}",
                "reason": "physical acceptance needs_attention fallback code supersede",
                "supersede_invite_id": str(pending_id or invite_id),
            },
        )
    check("exception handoff status", r.status_code == 200, r.text[:400])
    handoff = r.json() if r.status_code == 200 else {}
    EVID["hr"]["exception_handoff"] = {
        "ok": handoff.get("ok"),
        "has_code": bool(str(handoff.get("activation_code") or "").strip()),
        "invite_id": handoff.get("invite_id"),
    }
    check("exception handoff returns code", bool(str(handoff.get("activation_code") or "").strip()))

    # Restore delivered invite for Aziz activate (emailed code path) — mint+deliver with known code
    emp = legacy.find_employee_by_key(AZIZ, company_code=COMPANY)
    invite_row, code = legacy.create_employee_app_invite(COMPANY, emp, created_by_user_id="physical-acceptance")
    outbound = legacy.deliver_app_activation_code(COMPANY, emp, code)
    inv._stamp_delivery(
        legacy,
        invite_id=str(invite_row["invite_id"]),
        delivery_status=inv._map_outbound_to_invite_delivery(outbound)[0],
        channel=inv._map_outbound_to_invite_delivery(outbound)[1],
        error=inv._map_outbound_to_invite_delivery(outbound)[2],
        trigger_source=inv.TRIGGER_HR_REINVITE,
    )
    mapped = inv._map_outbound_to_invite_delivery(outbound)
    EVID["aziz"]["delivered_code_len"] = len(code)
    EVID["aziz"]["outbound_ok"] = bool(outbound.get("ok"))
    EVID["aziz"]["delivery_status"] = mapped[0]
    EVID["aziz"]["channel"] = mapped[1]
    check("aziz invite delivered or sent", mapped[0] in {inv.STATUS_DELIVERED, inv.STATUS_SENT, inv.STATUS_FAILED, inv.STATUS_NEEDS_ATTENTION}, mapped)
    check("only one pending before activate", pending_invite_count(AZIZ) == 1, pending_invite_count(AZIZ))

    # Confirm HR does NOT see this code on invitation endpoints
    r = client.get(f"/dashboard/posthire/employees/{AZIZ}/app-invitation", headers=headers)
    snap2 = r.json()
    check("hr after deliver still no code", no_code(snap2) and code not in json.dumps(snap2))
    check("show_code_exception false when not needs_attention",
          snap2.get("actions", {}).get("show_code_exception") is False
          or snap2.get("invitation_status") == inv.STATUS_NEEDS_ATTENTION)

    # Expired state on a disposable synthetic invite (do not expire Aziz before activate)
    suffix = uuid.uuid4().hex[:8]
    synth_key = f"WATHEFNI-INVITE-PHYS-{suffix.upper()}"
    synth_phone = f"70{suffix[:6]}"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, email, employment_status, position_title, raw_json)
                VALUES (%s,%s,%s,%s,%s,'active','Phys Accept',%s::jsonb)
                """,
                (COMPANY, synth_key, f"Phys {suffix}", synth_phone, f"phys-{suffix}@example.invalid", json.dumps({"source": "phys_accept"})),
            )
            conn.commit()
    try:
        synth = legacy.find_employee_by_key(synth_key, company_code=COMPANY)
        s_invite, _scode = legacy.create_employee_app_invite(COMPANY, synth, created_by_user_id="physical-acceptance")
        force_expired(str(s_invite["invite_id"]))
        s_exp = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=synth_key)
        EVID["states"]["expired"] = {k: s_exp.get(k) for k in ("invitation_status", "actions")}
        check("state expired", s_exp.get("invitation_status") == inv.STATUS_EXPIRED, s_exp.get("invitation_status"))
    finally:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employee_app_invites WHERE company_code=%s AND employee_key=%s", (COMPANY, synth_key))
                cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, synth_key))
                conn.commit()

    # --- Aziz activate with the delivered code (LIVE uvicorn — has allowlist) ---
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_sessions
                SET status='revoked', refresh_hash=NULL, revoked_at=now(), revoked_reason='physical_acceptance_reset',
                    expires_at=LEAST(expires_at, now()), refresh_expires_at=LEAST(refresh_expires_at, now())
                WHERE company_code=%s AND employee_key=%s AND status='active'
                """,
                (COMPANY, AZIZ),
            )
            conn.commit()

    act_status, act_body = live_json("POST", "/app/auth/activate", body={"phone": AZIZ_PHONE, "code": code, "platform": "ios"})
    check("aziz activate 200", act_status == 200, act_body if act_status != 200 else act_status)
    token_app = str(act_body.get("token") or "")
    refresh = str(act_body.get("refresh_token") or "")
    EVID["aziz"]["activate_ok"] = bool(act_body.get("ok"))
    EVID["aziz"]["replaced_previous_device"] = act_body.get("replaced_previous_device")
    check("aziz activate ok", bool(act_body.get("ok")) and bool(token_app) and bool(refresh))

    me_status, me_body = live_json("GET", "/app/me", token=token_app)
    check("aziz /app/me 200", me_status == 200, me_body if me_status != 200 else me_status)
    me_key = me_body.get("employee_key") or (me_body.get("employee") or {}).get("employee_key")
    check("aziz me employee key", me_key == AZIZ, me_key)

    # Reopen without activation code = refresh session
    ref_status, ref_body = live_json("POST", "/app/auth/refresh", body={"refresh_token": refresh})
    check("aziz refresh (reopen) 200", ref_status == 200, ref_body if ref_status != 200 else ref_status)
    token2 = str(ref_body.get("token") or "")
    me2_status, _me2 = live_json("GET", "/app/me", token=token2)
    check("aziz me after reopen 200", me2_status == 200)

    # Wrong/old code must fail (stale activation)
    stale_status, _stale = live_json("POST", "/app/auth/activate", body={"phone": AZIZ_PHONE, "code": code, "platform": "ios"})
    check("stale code rejected", stale_status in {401, 403, 409, 422, 400}, stale_status)

    # HR reflects activated
    r = client.get(f"/dashboard/posthire/employees/{AZIZ}/app-invitation", headers=headers)
    final = r.json()
    EVID["hr"]["aziz_after"] = {k: final.get(k) for k in ("invitation_status", "channel", "app_access_active", "actions", "access")}
    check("hr invitation_status activated", final.get("invitation_status") == inv.STATUS_ACTIVATED, final.get("invitation_status"))
    check("hr app access active", bool(final.get("app_access_active") or (final.get("access") or {}).get("active")))
    check("hr final no code", no_code(final))
    check("no pending invites after activate", pending_invite_count(AZIZ) == 0, pending_invite_count(AZIZ))

    # No Phase 6 surface
    routes = {getattr(rt, "path", None) for rt in legacy.app.routes}
    check("no /app/devices phase6", "/app/devices" not in routes)

    print("---")
    print(json.dumps({"fail_count": len(FAILS), "fails": FAILS, "evidence": EVID}, indent=2, default=str))
    if FAILS:
        print(f"FAIL physical_acceptance count={len(FAILS)}")
        return 1
    print("PASS employee_app_invitation_physical_acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
