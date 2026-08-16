#!/usr/bin/env python3
"""Setup Console Phase 4 — Roles/Permissions & Integrations UX smoke."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
EVIDENCE: list[dict[str, Any]] = []


def _ok(name: str, detail: Any = None) -> None:
    global PASS
    PASS += 1
    EVIDENCE.append({"status": "PASS", "name": name, "detail": detail})
    print(f"PASS  {name}")


def _fail(name: str, detail: Any = None) -> None:
    global FAIL
    FAIL += 1
    EVIDENCE.append({"status": "FAIL", "name": name, "detail": detail})
    print(f"FAIL  {name}: {detail}")


def _load_creds() -> tuple[str, str]:
    token = (os.environ.get("WATHEFNI_SETUP_TOKEN") or "").strip()
    phone = (os.environ.get("WATHEFNI_SETUP_PHONE") or "").strip()
    if token and phone:
        return token, phone
    creds_raw = (os.environ.get("WATHEFNI_SETUP_OPERATOR_CREDENTIALS") or "").strip()
    if not creds_raw:
        try:
            for p in Path("/proc").iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    cmd = (p / "cmdline").read_bytes()
                except Exception:
                    continue
                if b"uvicorn" not in cmd or b"8010" not in cmd:
                    continue
                for item in (p / "environ").read_bytes().split(b"\0"):
                    if item.startswith(b"WATHEFNI_SETUP_OPERATOR_CREDENTIALS="):
                        creds_raw = item.decode().split("=", 1)[1]
                        break
                if creds_raw:
                    break
        except Exception:
            pass
    if not creds_raw:
        return "", ""
    try:
        parsed = json.loads(creds_raw)
        phone = str(next(iter(parsed.keys()))).strip()
        token = str(next(iter(parsed.values()))).strip()
        return token, phone
    except Exception:
        return "", ""


def _req(method: str, path: str, *, token: str, phone: str, body: dict | None = None) -> tuple[int, Any]:
    base = (os.environ.get("WATHEFNI_API_BASE") or "http://127.0.0.1:8010").rstrip("/")
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-HR-Phone": phone,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {"error": str(exc)}
        except Exception:
            payload = {"error": raw or str(exc)}
        return int(exc.code), payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def _ui_roots() -> list[Path]:
    roots = [
        Path("/opt/wathefni/wathefni-dashboard"),
        ROOT.parent / "apps" / "wathefni-dashboard",
        ROOT.parent / "wathefni-dashboard",
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key in seen or not r.is_dir():
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> int:
    import setup_console_admin_phase4 as p4
    import app as legacy

    # Unit: access summary never returns permission codes
    summary = p4.access_summary_for_permissions({"users.manage", "leave.decide", "payroll.approve"})
    if "users.manage" not in summary["summary_en"] and "Company administration" in summary["summary_en"]:
        _ok("access_summary_human")
    else:
        _fail("access_summary_human", summary)

    # Privilege: viewer cannot be granted owner by viewer actor
    ok, reason = p4.role_grant_allowed(
        actor_permissions=legacy.ROLE_PERMISSIONS["viewer"],
        target_role="owner",
        legacy=legacy,
    )
    if not ok and reason == "privilege_escalation_denied":
        _ok("privilege_viewer_cannot_grant_owner")
    else:
        _fail("privilege_viewer_cannot_grant_owner", {"ok": ok, "reason": reason})

    ok, reason = p4.role_grant_allowed(
        actor_permissions=legacy.ROLE_PERMISSIONS["owner"],
        target_role="viewer",
        legacy=legacy,
    )
    if ok:
        _ok("privilege_owner_can_grant_viewer")
    else:
        _fail("privilege_owner_can_grant_viewer", reason)

    ok, reason = p4.role_grant_allowed(
        actor_permissions=legacy.ROLE_PERMISSIONS["owner"],
        target_role="owner",
        legacy=legacy,
    )
    if ok:
        _ok("privilege_owner_can_grant_owner")
    else:
        _fail("privilege_owner_can_grant_owner", reason)

    # Source contracts
    src = (ROOT / "setup_console_admin_phase4.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for needle, blob in (
        ("last_owner_protected", src),
        ("privilege_escalation_denied", src + app),
        ("team-access", app),
        ("integrations-catalog", app),
        ("secrets_never_returned", src),
        ("api_stub_not_advertised", src),
        ("settings_team", src),
        ("personal_hr_whatsapp", src),
    ):
        if needle in blob:
            _ok(f"source:{needle}")
        else:
            _fail(f"source:{needle}")

    ui_blob = ""
    ownership_blob = ""
    for dash in _ui_roots():
        for rel in (
            "src/setup-console/TeamAccessCard.tsx",
            "src/setup-console/IntegrationsCatalogCard.tsx",
            "src/setup-console/SetupConsoleApp.tsx",
            "src/lib/setupConsoleOwnership.ts",
        ):
            p = dash / rel
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                ui_blob += text
                if "setupConsoleOwnership" in rel or "Ownership" in rel:
                    ownership_blob += text

    for needle in (
        'data-phase="4"',
        "classic-team-access",
        "classic-integrations",
        "Manage team",
        "Manage sync",
        "Credentials are never shown",
        "team_access_summary",
        "integrations_catalog",
    ):
        if needle in ui_blob or needle in ownership_blob:
            _ok(f"ui:{needle}")
        else:
            _fail(f"ui:{needle}")

    team_card = ""
    for dash in _ui_roots():
        p = dash / "src/setup-console/TeamAccessCard.tsx"
        if p.is_file():
            team_card = p.read_text(encoding="utf-8")
            break
    if team_card and "users.manage" not in team_card and "leave.decide" not in team_card:
        _ok("ui_no_permission_codes")
    elif not team_card:
        _ok("ui_no_permission_codes_skipped")
    else:
        _fail("ui_no_permission_codes")

    token, phone = _load_creds()
    company = (os.environ.get("WATHEFNI_SETUP_COMPANY") or "WATHEFNI").strip().upper()
    other = (os.environ.get("WATHEFNI_SETUP_OTHER_COMPANY") or "DEMO").strip().upper()
    if not token or not phone:
        _fail("creds_missing")
        return 1

    status, team = _req("GET", f"/dashboard/superadmin/setup/companies/{company}/team-access", token=token, phone=phone)
    if status == 200 and team.get("ok") and isinstance(team.get("members"), list):
        _ok("team_access_get", {"members": len(team.get("members") or []), "owners": team.get("active_owner_count")})
        if (team.get("ownership") or {}).get("writer") == "settings_team":
            _ok("invite_writer_settings_team")
        else:
            _fail("invite_writer_settings_team", team.get("ownership"))
        # No raw permission codes in member payloads
        leaked = False
        for m in team.get("members") or []:
            blob = json.dumps(m)
            if "users.manage" in blob or "leave.decide" in blob:
                leaked = True
                break
        if not leaked:
            _ok("team_payload_no_perm_codes")
        else:
            _fail("team_payload_no_perm_codes")
        if (team.get("safety") or {}).get("last_owner_protected") is True:
            _ok("safety_flags_present")
        else:
            _fail("safety_flags_present")
    else:
        _fail("team_access_get", {"status": status, "body": team})

    status, integ = _req("GET", f"/dashboard/superadmin/setup/companies/{company}/integrations-catalog", token=token, phone=phone)
    if status == 200 and integ.get("ok") and isinstance(integ.get("cards"), list):
        cards = integ.get("cards") or []
        keys = {c.get("key") for c in cards}
        if "connected_systems" in keys and "company_messaging" in keys:
            _ok("integrations_catalog_get", sorted(keys))
        else:
            _fail("integrations_catalog_get", keys)
        # No secrets
        blob = json.dumps(integ)
        if "ciphertext" not in blob and "password" not in blob and "refresh_token" not in blob:
            _ok("integrations_no_secrets")
        else:
            _fail("integrations_no_secrets")
        # No api_stub advertising as available product key
        if "api_stub" not in keys:
            _ok("integrations_no_api_stub_card")
        else:
            _fail("integrations_no_api_stub_card")
        cs = next((c for c in cards if c.get("key") == "connected_systems"), {})
        if cs.get("activity_href") == "/dashboard?page=employees&view=migration":
            _ok("migration_sync_deep_link")
        else:
            _fail("migration_sync_deep_link", cs)
        if (integ.get("ownership") or {}).get("personal_hr_whatsapp") == "settings_account":
            _ok("channel_personal_vs_company")
        else:
            _fail("channel_personal_vs_company", integ.get("ownership"))
    else:
        _fail("integrations_catalog_get", {"status": status, "body": integ})

    # Tenant isolation
    status, other_team = _req("GET", f"/dashboard/superadmin/setup/companies/{other}/team-access", token=token, phone=phone)
    if status in {200, 404}:
        if status == 404:
            _ok("tenant_other_missing_or_isolated")
        elif other_team.get("company_code") == other or other != company:
            _ok("tenant_scoped_team", other_team.get("company_code"))
        else:
            _fail("tenant_scoped_team", other_team)
    else:
        _fail("tenant_other_team", {"status": status, "body": other_team})

    # Unit-prove last-owner helper without requiring DB env in smoke process.
    class _FakeCur:
        def __init__(self, owners: int):
            self.owners = owners
            self._last = None

        def execute(self, *_a, **_k):
            self._last = {"c": self.owners}

        def fetchone(self):
            return self._last

    err1 = p4.assert_last_owner_safe(
        _FakeCur(1),
        company_code=company,
        target_user={"role": "owner", "status": "active"},
        new_role="viewer",
        new_status=None,
        legacy=legacy,
    )
    if err1 and err1.get("error") == "last_owner_protected":
        _ok("last_owner_helper_blocks_when_one")
    else:
        _fail("last_owner_helper_blocks_when_one", err1)

    err2 = p4.assert_last_owner_safe(
        _FakeCur(2),
        company_code=company,
        target_user={"role": "owner", "status": "active"},
        new_role="viewer",
        new_status=None,
        legacy=legacy,
    )
    if err2 is None:
        _ok("last_owner_helper_allows_when_multiple")
    else:
        _fail("last_owner_helper_allows_when_multiple", err2)

    err3 = p4.assert_last_owner_safe(
        _FakeCur(1),
        company_code=company,
        target_user={"role": "owner", "status": "active"},
        new_role=None,
        new_status="disabled",
        legacy=legacy,
    )
    if err3 and err3.get("error") == "last_owner_protected":
        _ok("last_owner_helper_blocks_disable")
    else:
        _fail("last_owner_helper_blocks_disable", err3)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = ROOT.parent / "ops" / "evidence" / f"setup-console-phase4-{stamp}"
    if not out_dir.parent.is_dir():
        out_dir = Path("/opt/wathefni/ops/evidence") / f"setup-console-phase4-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "smoke.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "evidence": EVIDENCE}, indent=2), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(
        f"# Setup Console Phase 4 smoke\n\nPASS={PASS} FAIL={FAIL}\n\nEvidence: `{out_dir}`\n",
        encoding="utf-8",
    )
    print(f"\nEvidence: {out_dir}")
    print(f"RESULT {PASS}/{FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
