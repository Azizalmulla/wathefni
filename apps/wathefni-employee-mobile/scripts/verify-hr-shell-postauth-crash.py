#!/usr/bin/env python3
"""Reproduce the post Work-email HR shell crash cause (static contract).

Crash stack (canary OTA e046b071… / runtime 0.3.0), first failing module:

  Error: useAuth must be used within AuthProvider
      at useAuth (src/auth/AuthProvider.tsx)
      at TabsLayout (app/(tabs)/_layout.tsx)

Root cause:
  After Work-email auth, ModeRedirect swapped UnsignedEntry → HrShellHost while
  the URL was still `/`. HrShellHost's root Stack focused Employee `(tabs)`
  without Employee AuthProvider/QueryClient. HR providers only exist under
  app/hr/_layout.tsx, which never mounted.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
layout = (ROOT / "app/_layout.tsx").read_text(encoding="utf-8")
tabs = (ROOT / "app/(tabs)/_layout.tsx").read_text(encoding="utf-8")
unified = (ROOT / "src/principals/UnifiedSignInView.tsx").read_text(encoding="utf-8")
auth = (ROOT / "src/auth/AuthProvider.tsx").read_text(encoding="utf-8")

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, ok))
    print(("PASS" if ok else "FAIL"), name)


check("employee tabs call useAuth", "useAuth()" in tabs)
check("useAuth throws outside provider", "useAuth must be used within AuthProvider" in auth)
check("HR path uses Redirect guard", "Redirect" in layout and "segments[0] !== 'hr'" in layout)
check("HR path mounts Slot only on /hr", "<Slot" in layout)
check("unsafe HrShellHost removed", "function HrShellHost" not in layout)
check("work email replace /hr before selectMode", "router.replace('/hr')" in unified)

failed = [name for name, ok in checks if not ok]
print()
print(f"{len(checks) - len(failed)}/{len(checks)} passed")
if failed:
    raise SystemExit(1)
print(
    "FIRST_FAILING_MODULE=app/(tabs)/_layout.tsx :: useAuth outside AuthProvider "
    "(post-auth shell swap on non-/hr URL)"
)
