#!/usr/bin/env python3
"""Production-canary employee app API/control qualification for Talal."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

EVID = Path(os.environ["INTERACTION_AUDIT_EVID"])
SESSION_FILE = Path(os.environ["INTERACTION_AUDIT_EMPLOYEE_SESSION"])
API = os.environ.get("EMPLOYEE_APP_API", "https://api.wathefni.ai").rstrip("/")


def http(
    method: str,
    route: str,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + route, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode(errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except Exception:
                return resp.status, {"binary_or_text": True, "bytes": len(raw)}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except Exception:
            return int(exc.code), {"raw": raw[:300]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": "network_error", "message": str(exc)}


def calm_error(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    detail = payload.get("detail", payload)
    if not isinstance(detail, dict):
        return False
    code = str(detail.get("error") or "")
    message = str(detail.get("message") or "")
    return bool(message) and message != code and "_" not in message


rows: list[dict] = []


def add(
    screen: str,
    control: str,
    expected: str,
    actual: str,
    status: str,
    severity: str | None,
    fix: str,
    evidence: object | None = None,
) -> None:
    rows.append(
        {
            "app": "employee_mobile",
            "screen": screen,
            "role": "employee",
            "control": control,
            "expected_behavior": expected,
            "actual_result": actual,
            "status": status,
            "severity": severity,
            "exact_fix_location": fix,
            "evidence": evidence,
        }
    )
    print(status.upper(), screen, control, actual)


session = json.loads(SESSION_FILE.read_text())
token = session["token"]
refresh_token = session["refresh_token"]
employee_key = session["employee_key"]

# Session refresh is a primary interaction and must rotate safely.
st, refreshed = http("POST", "/app/auth/refresh", body={"refresh_token": refresh_token})
refresh_ok = st == 200 and isinstance(refreshed, dict) and refreshed.get("token") and refreshed.get("refresh_token")
add(
    "activation/session",
    "Automatic session refresh",
    "Rotate access+refresh tokens, keep same employee, return calm auth errors.",
    f"status={st}; rotated={bool(refresh_ok)}",
    "pass" if refresh_ok else "broken",
    None if refresh_ok else "P0",
    "wathefni-orchestrator/app.py:65975",
)
if not refresh_ok:
    raise SystemExit(1)
token = str(refreshed["token"])
refresh_token = str(refreshed["refresh_token"])

read_routes = [
    ("home", "Load employee identity and capability gates", "/app/me", "wathefni-orchestrator/app.py:66002"),
    ("profile", "Open profile", "/app/profile", "wathefni-orchestrator/app.py:66018"),
    ("onboarding", "Open onboarding", "/app/onboarding", "wathefni-orchestrator/app.py:66038"),
    ("leave", "Open leave", "/app/leave", "wathefni-orchestrator/app.py:66154"),
    ("shifts", "Open today's shifts", "/app/shifts/today", "wathefni-orchestrator/app.py:66187"),
    ("shifts", "Open upcoming shifts", "/app/shifts/upcoming", "wathefni-orchestrator/app.py:66209"),
    ("attendance", "Open attendance", "/app/attendance", "wathefni-orchestrator/app.py:66233"),
    ("documents", "Open documents", "/app/documents", "wathefni-orchestrator/app.py:66261"),
    ("notifications", "Open notifications", "/app/notifications", "wathefni-orchestrator/app.py:66578"),
]

payloads: dict[str, object] = {}
for screen, control, route, fix in read_routes:
    st, payload = http("GET", route, token)
    ok = st == 200 or (
        st == 403
        and isinstance(payload, dict)
        and isinstance(payload.get("detail", payload), dict)
        and payload.get("detail", payload).get("error") == "employee_feature_disabled"
        and calm_error(payload)
    )
    payloads[route] = payload
    add(
        screen,
        control,
        "Return self-scoped data, or a calm explained feature-disabled state.",
        f"status={st}",
        "pass" if ok else "broken",
        None if ok else "P1",
        fix,
        {"status": st},
    )

me = payloads.get("/app/me")
if isinstance(me, dict):
    actual_key = str((me.get("employee") or {}).get("employee_key") or me.get("employee_key") or "")
    scoped = actual_key == employee_key
    add(
        "home",
        "Self-scope identity",
        "The employee can only see their own canonical employee key.",
        f"employee_key={actual_key}",
        "pass" if scoped else "permission mismatch",
        None if scoped else "P0",
        "wathefni-orchestrator/app.py:66002",
    )

# Onboarding version/history drill-in if an item exists.
onboarding = payloads.get("/app/onboarding")
items = []
if isinstance(onboarding, dict):
    items = onboarding.get("items") or onboarding.get("checklist") or []
if isinstance(items, list) and items:
    item_id = str((items[0] or {}).get("item_id") or (items[0] or {}).get("id") or "")
    if item_id:
        st, _ = http("GET", f"/app/onboarding/items/{item_id}/versions", token)
        add(
            "onboarding",
            "Open item history",
            "Open version history for a self-scoped onboarding item.",
            f"status={st}",
            "pass" if st == 200 else "broken",
            None if st == 200 else "P2",
            "wathefni-orchestrator/app.py:66101",
        )

# Notification read is an idempotent visible mutation; the read receipt row is
# the durable mutation ledger. Repeat it to prove safe repeated clicks.
notifications = payloads.get("/app/notifications")
notification_items = notifications.get("notifications", []) if isinstance(notifications, dict) else []
if notification_items:
    message_id = str((notification_items[0] or {}).get("id") or "")
    st1, body1 = http("POST", f"/app/notifications/{message_id}/read", token, {})
    st2, body2 = http("POST", f"/app/notifications/{message_id}/read", token, {})
    st3, after_notifications = http("GET", "/app/notifications", token)
    marked = False
    if st3 == 200 and isinstance(after_notifications, dict):
        marked = any(
            str(item.get("id")) == message_id and bool(item.get("read"))
            for item in after_notifications.get("notifications", [])
            if isinstance(item, dict)
        )
    ok = st1 == 200 and st2 == 200 and marked
    add(
        "notifications",
        "Mark notification read",
        "Persist read receipt; update state; repeated taps are idempotent.",
        f"first={st1}; repeat={st2}; persisted={marked}",
        "pass" if ok else "broken",
        None if ok else "P1",
        "wathefni-orchestrator/app.py:66618",
        {"first": body1, "repeat": body2},
    )
else:
    add(
        "notifications",
        "Mark notification read",
        "Persist read receipt; repeated taps are idempotent.",
        "No canary notification exists to mutate.",
        "unproven",
        "P3",
        "wathefni-orchestrator/app.py:66618",
    )

# Invalid/stale IDs must fail calmly, not leak raw codes.
st, payload = http("POST", "/app/leave/00000000-0000-0000-0000-000000000000/cancel", token, {})
safe_stale = st in {400, 403, 404, 409} and calm_error(payload)
add(
    "leave",
    "Cancel stale/nonexistent request",
    "Do not mutate; return calm copy and allow refresh.",
    f"status={st}; calm={calm_error(payload)}",
    "pass" if safe_stale else "broken",
    None if safe_stale else "P2",
    "wathefni-orchestrator/app.py:66687",
)

# Push registration preference is low-risk and reversible. Use a unique audit
# token then unregister twice to prove lock/idempotency.
push_token = f"ExponentPushToken[interaction-audit-{os.environ.get('AUDIT_STAMP', 'run')}]"
st1, _ = http("POST", "/app/push/register", token, {"push_token": push_token, "platform": "audit", "device_id": "interaction-audit"})
st2, _ = http("POST", "/app/push/unregister", token, {"push_token": push_token})
st3, _ = http("POST", "/app/push/unregister", token, {"push_token": push_token})
push_ok = st1 in {200, 403} and st2 == 200 and st3 == 200
add(
    "settings",
    "Push preference register/unregister",
    "Register only when capability allows; unregister is reversible and idempotent.",
    f"register={st1}; unregister={st2}; repeat={st3}",
    "pass" if push_ok else "broken",
    None if push_ok else "P1",
    "wathefni-orchestrator/app.py:67297",
)

# Invalid auth error must be calm.
st, payload = http("GET", "/app/me", "invalid-interaction-audit-token")
invalid_ok = st in {401, 403} and calm_error(payload)
add(
    "activation/session",
    "Expired/invalid session",
    "Fail closed with calm sign-in copy; no raw error code.",
    f"status={st}; calm={calm_error(payload)}",
    "pass" if invalid_ok else "broken",
    None if invalid_ok else "P1",
    "wathefni-orchestrator/app.py:employee_app_context",
)

# Sign out on this dedicated session and prove repeat-safe revocation.
st1, _ = http("POST", "/app/auth/logout", token, {})
st2, _ = http("POST", "/app/auth/logout", token, {})
st3, payload = http("GET", "/app/me", token)
logout_ok = st1 == 200 and st2 == 200 and st3 in {401, 403} and calm_error(payload)
add(
    "settings",
    "Sign out",
    "Revoke server session; clear local state; repeated taps safe.",
    f"first={st1}; repeat={st2}; revoked_probe={st3}",
    "pass" if logout_ok else "broken",
    None if logout_ok else "P0",
    "wathefni-orchestrator/app.py:65993",
)

summary = {
    "employee_key": employee_key,
    "controls": len(rows),
    "status_counts": {
        status: sum(row["status"] == status for row in rows)
        for status in sorted({row["status"] for row in rows})
    },
}
(EVID / "inventory").mkdir(parents=True, exist_ok=True)
(EVID / "verify").mkdir(parents=True, exist_ok=True)
(EVID / "inventory" / "employee-app-controls.json").write_text(json.dumps(rows, indent=2) + "\n")
(EVID / "verify" / "employee-app-control-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("EMPLOYEE_APP_CONTROL_AUDIT", json.dumps(summary))
if any(row["status"] in {"broken", "permission mismatch", "dead"} for row in rows):
    raise SystemExit(1)
