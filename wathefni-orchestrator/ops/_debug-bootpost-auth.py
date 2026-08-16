#!/usr/bin/env python3
import json, re, urllib.request, urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8011"
raw = Path("/root/.openclaw/secrets/wathefni-setup-operator.env").read_text()
val = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", raw).group(1).strip()
if val[0] in "\"'":
    val = val[1:-1]
op = json.loads(val)["96599338566"]
dash = re.search(
    r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)",
    Path("/root/.openclaw/secrets/postgres.staging.env").read_text(),
).group(1).strip().strip('"').strip("'")


def req(method, path, headers=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


st, detail = req("GET", "/dashboard/superadmin/setup/companies/BOOTPOST01", {"Authorization": f"Bearer {op}", "X-HR-Phone": "96599338566"})
print("users", json.dumps(detail.get("users"), indent=2)[:1200])

st, body = req(
    "GET",
    "/dashboard/bootstrap",
    {"Authorization": f"Bearer {dash}", "X-HR-Phone": "96551110002", "X-Company-Code": "BOOTPOST01"},
)
print("bootstrap_before", st, body)

# Try setup console HR whatsapp link endpoint variants
for path in (
    "/dashboard/superadmin/setup/companies/BOOTPOST01/hr-whatsapp",
    "/dashboard/superadmin/setup/companies/BOOTPOST01/whatsapp",
    "/dashboard/superadmin/setup/companies/BOOTPOST01/link-whatsapp",
):
    st, body = req("POST", path, {"Authorization": f"Bearer {op}", "X-HR-Phone": "96599338566"}, {"phone": "96551110002"})
    print("try", path, st, body)

st, body = req(
    "GET",
    "/dashboard/bootstrap",
    {"Authorization": f"Bearer {dash}", "X-HR-Phone": "96551110002", "X-Company-Code": "BOOTPOST01"},
)
print("bootstrap_after", st, body if st != 200 else {k: body.get(k) for k in ("company_code", "enabled_modules", "access")})

# Accept invite if token available
st, owner = req(
    "POST",
    "/dashboard/superadmin/setup/companies/BOOTPOST01/owner",
    {"Authorization": f"Bearer {op}", "X-HR-Phone": "96599338566"},
    {"name": "Boot Posthire Only Owner", "email": "bootpost01-owner@example.test", "phone": "96551110002"},
)
print("owner_keys", st, list(owner.keys()) if isinstance(owner, dict) else owner)
invite = (owner or {}).get("invite_token") if isinstance(owner, dict) else None
if invite:
    st, body = req(
        "POST",
        "/dashboard/auth/accept-invite",
        body={"token": invite, "password": "BootPost01!pass", "name": "Boot Posthire Only Owner"},
    )
    print("accept", st, body)
    # login with email/password
    st, body = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": "BOOTPOST01", "email": "bootpost01-owner@example.test", "password": "BootPost01!pass"},
    )
    print("login", st, {k: body.get(k) for k in ("token", "access", "user", "detail") if isinstance(body, dict)})
    sess = body.get("token") if isinstance(body, dict) else None
    if sess:
        st, boot = req("GET", "/dashboard/bootstrap", {"Authorization": f"Bearer {sess}", "X-Company-Code": "BOOTPOST01"})
        print("bootstrap_session", st, {k: boot.get(k) for k in ("company_code", "enabled_modules") } if isinstance(boot, dict) else boot)
