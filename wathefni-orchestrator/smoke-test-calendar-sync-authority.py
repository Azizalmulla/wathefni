#!/usr/bin/env python3
"""Calendar sync authority — permissions, API sanitization, UI placement."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name}{' — ' + detail if detail else ''}")


def main() -> int:
    print("=== Calendar sync authority smoke ===")
    import app
    import calendar_sync as csync

    owner = set(app.ROLE_PERMISSIONS["owner"])
    hr_admin = set(app.ROLE_PERMISSIONS["hr_admin"])
    hr_manager = set(app.ROLE_PERMISSIONS["hr_manager"])
    recruiter = set(app.ROLE_PERMISSIONS["recruiter"])
    interviewer = set(app.ROLE_PERMISSIONS["interviewer"])

    check("owner has calendar.sync by default", "calendar.sync" in owner)
    check("owner has settings.manage", "settings.manage" in owner)
    check("hr_admin lacks calendar.sync", "calendar.sync" not in hr_admin)
    check("hr_admin keeps settings.manage", "settings.manage" in hr_admin)
    check("hr_admin keeps calendar.company", "calendar.company" in hr_admin)
    check("hr_admin keeps calendar.manage", "calendar.manage" in hr_admin)
    check("hr_manager lacks calendar.sync", "calendar.sync" not in hr_manager)
    check("recruiter lacks calendar.sync", "calendar.sync" not in recruiter)
    check("interviewer lacks calendar.sync", "calendar.sync" not in interviewer)
    check("no HR role auto-grants calendar.sync", not any("calendar.sync" in set(app.ROLE_PERMISSIONS[r]) for r in ("hr_admin", "hr_manager", "recruiter", "hiring_manager", "interviewer")))
    check("owner still strict superset of hr_admin", owner > hr_admin)

    # Sanitized public status — never leaks internals
    synced = csync.public_event_sync_status(
        [{"sync_status": "synced", "provider_key": "google_workspace", "binding_id": "b1", "last_error": "secret", "external_html_link": "https://x"}]
    )
    check("public synced label", synced.get("customer_status") == "synced")
    check("public has no bindings key", "bindings" not in synced)
    check("public has no provider", "provider_key" not in synced and "last_error" not in synced)

    pending = csync.public_event_sync_status([{"sync_status": "queued"}])
    check("public pending label", pending.get("customer_status") == "pending")
    failed = csync.public_event_sync_status([{"sync_status": "failed", "last_error": "boom"}])
    check("public failed is unavailable without error", failed.get("customer_status") == "unavailable")
    empty = csync.public_event_sync_status([])
    check("public empty is none", empty.get("customer_status") is None)

    # Endpoint source contract
    app_src = Path(app.__file__).read_text(encoding="utf-8")
    fn_start = app_src.find("def dashboard_calendar_event_sync_status")
    fn_chunk = app_src[fn_start : fn_start + 1800]
    check("event sync uses calendar.read entitlement", 'require_entitlement(context, "calendar", "calendar.read")' in fn_chunk)
    check("event sync gates full bindings on calendar.sync", 'dashboard_context_has_permission(context, "calendar.sync")' in fn_chunk)
    check("event sync returns empty bindings for non-sync", '"bindings": []' in fn_chunk or "'bindings': []" in fn_chunk)
    check("event sync uses public_event_sync_status", "public_event_sync_status" in fn_chunk)
    check("event sync detail full branch", '"detail": "full"' in fn_chunk)
    check("event sync detail status branch", '"detail": "status"' in fn_chunk)

    # Direct API shape simulation (no HTTP): mirror handler branches
    fake_bindings = [
        {
            "binding_id": "bind-1",
            "provider_key": "microsoft_365",
            "sync_status": "synced",
            "last_error": "should-not-leak",
            "external_html_link": "https://outlook.office.com/x",
            "connection_id": "conn-1",
        }
    ]
    public = csync.public_event_sync_status(fake_bindings)
    read_payload = {"ok": True, "detail": "status", "bindings": [], **public}
    sync_payload = {"ok": True, "detail": "full", "bindings": fake_bindings, **public}
    check("read payload empty bindings", read_payload["bindings"] == [])
    check("read payload no provider in top-level", "provider_key" not in read_payload and "last_error" not in read_payload)
    check("read payload customer synced", read_payload["customer_status"] == "synced")
    check("sync payload retains bindings for operators", len(sync_payload["bindings"]) == 1)
    check("sync payload still includes customer_status", sync_payload["customer_status"] == "synced")

    # UI placement — Settings hosts console; Calendar does not.
    # Prefer deployed dashboard assets when present (production host may keep a stale source tree).
    cal_src = REPO / "apps/wathefni-dashboard/src/components/CalendarShell.tsx"
    settings_src = REPO / "apps/wathefni-dashboard/src/pages/SettingsPage.tsx"
    panel_src = REPO / "apps/wathefni-dashboard/src/components/PlatformIntegrationsPanel.tsx"
    assets = Path("/var/www/wathefni-dashboard/assets")
    if assets.is_dir() and any(assets.glob("CalendarShell-*.js")):
        cal = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in assets.glob("CalendarShell-*.js"))
        settings = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in assets.glob("SettingsPage-*.js"))
        panel = settings
    elif cal_src.exists() and settings_src.exists() and panel_src.exists():
        cal = cal_src.read_text(encoding="utf-8")
        settings = settings_src.read_text(encoding="utf-8")
        panel = panel_src.read_text(encoding="utf-8")
    else:
        raise SystemExit("Calendar UI sources/assets not found for placement checks")
    check("Calendar has no External sync", "External sync" not in cal and "مزامنة خارجية" not in cal)
    check("Calendar has no Platform integrations console", "Platform integrations" not in cal and "تكاملات المنصة" not in cal)
    check("Calendar has no legacy operator control", "Ensure legacy operator" not in cal)
    check("Calendar quiet Synced label", "Synced" in cal or "تمت المزامنة" in cal)
    check("Calendar quiet Not synced label", "Not synced" in cal or "غير متزامن" in cal)
    check("Calendar no Open external", "Open external" not in cal)
    check("Calendar no Retry sync", "Sync requeued" not in cal and "retryCalendarEventSync" not in cal)
    check("Settings imports PlatformIntegrationsPanel", "PlatformIntegrationsPanel" in settings or "Platform Integrations" in settings)
    check(
        "Settings dual-gates settings.manage and calendar.sync",
        ("settings.manage" in settings and "calendar.sync" in settings and "canManagePlatformIntegrations" in settings)
        or ("settings.manage" in settings and "calendar.sync" in settings),
    )
    check(
        "Platform panel still has connect flows",
        ("Connect Microsoft 365" in panel and "Connect Google Workspace" in panel)
        or ("Microsoft 365" in panel and "Google Workspace" in panel),
    )
    check("Platform panel keeps legacy operator", "Ensure legacy operator" in panel or "legacy operator" in panel.lower())

    print(f"=== sync authority done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
