#!/usr/bin/env python3
"""Static proof: session / refresh / entitlement revoke paths stay wired.

Does not claim device behaviour — only that the Phase 4 refresh contract remains
implemented in source (foreground, post-unlock, PTR, soft refresh of /app/me).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    passed = 0

    def check(name: str, ok: bool) -> None:
        nonlocal passed
        if ok:
            passed += 1
            print(f"PASS  {name}")
        else:
            failures.append(name)
            print(f"FAIL  {name}")

    refresh = read("src/lib/refresh.tsx")
    soft = read("src/lib/employeeSoftRefresh.ts")
    unlock = read("src/features/pin/LocalUnlockShell.tsx")
    layout = read("app/_layout.tsx")
    auth = read("src/auth/AuthProvider.tsx")
    home = read("app/(tabs)/index.tsx")
    access = read("src/components/AccessStates.tsx")
    caps = read("src/capabilities.ts")

    check(
        "foreground resume soft-refreshes me + active queries",
        "ForegroundQueryRefresh" in refresh
        and "softRefreshEmployeeSurfaces" in refresh
        and "AppState.addEventListener" in refresh
        and "needsLocalUnlock" in refresh,
    )
    check(
        "soft refresh always refreshes /app/me before active queries",
        "await refreshMe()" in soft and "refetchQueries({ type: 'active' })" in soft,
    )
    check(
        "post-PIN / Face ID unlock triggers the same soft refresh",
        "softRefreshEmployeeSurfaces" in unlock and "refreshMeRef" in unlock,
    )
    check(
        "root layout mounts ForegroundQueryRefresh while signed in",
        "ForegroundQueryRefresh" in layout,
    )
    check(
        "Home pull-to-refresh refreshes me + home projection",
        "refreshMe()" in home and "home.refetch()" in home,
    )
    check(
        "app-access revoke / session errors map to AccessStateScreen",
        "app_access_revoked" in caps
        and "access_reset" in caps
        and "AccessStateScreen" in layout
        and ("accessStateForError" in auth or "blockForError" in auth),
    )
    check(
        "feature-disabled API responses trigger refreshMe",
        "employee_feature_disabled" in auth and "await refreshMe()" in auth,
    )
    feature_copy = read("src/lib/featureUnavailableCopy.ts")
    check(
        "FeatureUnavailable reads server features.reason (no client entitlement invention)",
        "featureUnavailableMessageKey" in access
        and "me?.features" in access
        and "featureUnavailableReasonKind" in feature_copy
        and "SOME_INTERNAL" not in feature_copy,
    )

    print("---")
    if failures:
        print(f"FAIL count={len(failures)}: {', '.join(failures)}")
        return 1
    print(f"PASS session/refresh static proof ({passed} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
