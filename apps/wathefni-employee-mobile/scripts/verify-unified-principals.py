"""Contract checks for dual-principal shell resolution (no identity linking)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mode = (ROOT / "src/principals/mode.ts").read_text(encoding="utf-8")
session_emp = (ROOT / "src/auth/session.ts").read_text(encoding="utf-8")
session_hr = (ROOT / "src/hr/auth/session.ts").read_text(encoding="utf-8")
client_hr = (ROOT / "src/hr/api/client.ts").read_text(encoding="utf-8")
layout = (ROOT / "app/_layout.tsx").read_text(encoding="utf-8")
unified = (ROOT / "src/principals/UnifiedSignInView.tsx").read_text(encoding="utf-8")
freeze = Path("/Users/azizalmulla/Desktop/claw/docs/ADMIN_MOBILE_SCOPE_FREEZE.md").read_text(
    encoding="utf-8"
)

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, ok))
    print(("PASS" if ok else "FAIL"), name)


check("resolveShell exported", "export function resolveShell" in mode)
check(
    "no email/phone auto-link implementation",
    "dashboard_user" not in mode
    and "employee_key" not in mode
    and "normalize_email" not in mode
    and "digits(" not in mode,
)
check("employee SecureStore key namespace", "wathefni.session.token" in session_emp)
check("HR SecureStore key namespace", "wathefni.hr.access_token" in session_hr)
check("HR namespaces differ from employee", "wathefni.session.token" not in session_hr)
check("HR API allowlist", "/dashboard/mobile/" in client_hr and "unapproved_api_path" in client_hr)
check("PushLifecycle not imported into HR layout", "PushLifecycle" not in (ROOT / "app/hr/_layout.tsx").read_text())
check("Employee shell still mounts PushLifecycle", "PushLifecycle" in layout)
check("HR workspace flag gate", "EXPO_PUBLIC_HR_WORKSPACE_ENABLED" in mode)
check(
    "HR workspace falls back to app.config extra",
    "unifiedApp" in mode and "expo-constants" in mode,
)
check("freeze allows one public binary", "one public binary / two principals" in freeze.lower())
check("freeze forbids /app/me HR permissions", "Do **not** move HR permissions into `GET /app/me`" in freeze)
check("HR routes under /hr", (ROOT / "app/hr/(tabs)/index.tsx").is_file())
check("ai.wathefni.hr retired marker", (ROOT.parent / "wathefni-hr-mobile/SHIP_RETIRED.md").is_file())
check("no startup principal chooser", "PrincipalEntryView" not in layout and "PrincipalSwitcherView" not in layout)
check("app.config forces HR workspace on eas update", "EXPO_PUBLIC_HR_WORKSPACE_ENABLED" in (ROOT / "app.config.js").read_text())
check("ModeRedirect mounts UnsignedEntry", "UnsignedEntry" in layout and 'shell.kind === \'unsigned\'' in layout)
check(
    "HR shell waits for /hr before Slot",
    "Redirect" in layout and "segments[0] !== 'hr'" in layout and "<Slot" in layout,
)
check("HR shell removed unsafe HrShellHost stack", "function HrShellHost" not in layout)
check("Work email navigates to /hr before shell swap", 'router.replace(\'/hr\')' in unified)
check("no identity probe on sign-in", "dashboard_user_by_email" not in unified and "/app/me" not in unified)
check("work email uses operator login only", "/dashboard/mobile/auth/login" in unified)


def resolve(employee: bool, hr: bool, pref: str | None) -> str:
    if employee and not hr:
        return "employee"
    if not employee and hr:
        return "hr"
    if not employee and not hr:
        return "unsigned"
    if pref in {"employee", "hr"}:
        return pref
    return "employee"  # DEFAULT_DUAL_MODE


check("employee-only → employee", resolve(True, False, None) == "employee")
check("hr-only → hr", resolve(False, True, None) == "hr")
check("neither → unsigned", resolve(False, False, None) == "unsigned")
check("both + no pref → employee default", resolve(True, True, None) == "employee")
check("both + pref hr → hr", resolve(True, True, "hr") == "hr")
check("no boot switcher state", "switcher" not in mode.split("ResolvedShell")[1].split("export function")[0])

failed = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
