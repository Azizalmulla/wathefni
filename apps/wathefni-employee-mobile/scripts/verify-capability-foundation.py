#!/usr/bin/env python3
"""Static, dependency-free verification of Phase 9A1 mobile authority wiring."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> None:
    auth = read("src/auth/AuthProvider.tsx")
    tabs = read("app/(tabs)/_layout.tsx")
    home = read("app/(tabs)/index.tsx")
    home_view = read("src/features/home/HomeView.tsx")
    preview = read("src/designPreview.ts")
    premium = read("src/components/premium.tsx")
    motion = read("src/motion.ts")
    leave_request = read("app/leave/request.tsx")
    documents = read("app/documents.tsx")
    settings = read("app/settings.tsx")

    check("AuthProvider stores typed /app/me", "MeResponse" in auth and "setMe(next)" in auth)
    check("AuthProvider revalidates on foreground", "AppState.addEventListener" in auth and "refreshMe()" in auth)
    check("document download refreshes on 401", "result.status === 401" in auth and "rotateSessionAndLoadMe" in auth)
    check("optional tabs are capability-driven", "hasFeature('shifts')" in tabs and "hasFeature('leave')" in tabs)
    check(
        "home queries are capability-driven",
        "enabled: features.shifts" in home
        and "enabled: features.attendance" in home
        and "enabled: features.leave" in home
        and "enabled: features.onboarding" in home,
    )
    check(
        "home actions are capability-driven",
        "features.documents" in home_view
        and "features.attendance" in home_view
        and "can('leave', 'request')" in home,
    )
    check(
        "unsupported employee surfaces remain absent",
        "payslip" not in home_view.lower() and "compliance" not in home_view.lower(),
    )
    check(
        "design fixtures require explicit build flag",
        "EXPO_PUBLIC_DESIGN_PREVIEW" in preview and "design-preview-only" in preview,
    )
    check(
        "Wathefni branding is typography only",
        "function Wordmark" in premium
        and "Newsreader_600SemiBold" in premium
        and "NotoKufiArabic_600SemiBold" in premium
        and "brandMark" not in premium,
    )
    check(
        "motion respects reduced-motion preference",
        "isReduceMotionEnabled" in motion and "reduceMotionChanged" in motion,
    )
    check("leave types come from backend", "me?.leave.types" in leave_request and "LEAVE_TYPES" not in leave_request)
    check("documents do not read secure-store tokens directly", "loadSession" not in documents and "download" in documents)
    check("privacy URL is centralized", "@/config" in settings and "https://wathefni.ai/employee-app/privacy" not in settings)
    check("localized not-found route exists", (ROOT / "app/+not-found.tsx").is_file())

    optional_routes = {
        "app/(tabs)/shifts.tsx": "shifts",
        "app/(tabs)/leave.tsx": "leave",
        "app/onboarding.tsx": "onboarding",
        "app/documents.tsx": "documents",
        "app/attendance.tsx": "attendance",
        "app/leave/request.tsx": "leave",
    }
    for path, feature in optional_routes.items():
        source = read(path)
        check(
            f"{path} blocks direct access without {feature}",
            f"hasFeature('{feature}')" in source and "FeatureUnavailableState" in source,
        )

    required_i18n = {
        "access.offline.title",
        "access.app_disabled.title",
        "access.company_disabled.title",
        "access.company_archived.title",
        "access.company_app_disabled.title",
        "access.employee_inactive.title",
        "access.session_expired.title",
        "feature.unavailable.title",
        "notFound.title",
        "status.unknown",
    }
    en = json.loads(read("src/i18n/en.json"))
    ar = json.loads(read("src/i18n/ar.json"))
    check("English account/capability copy complete", required_i18n <= set(en))
    check("Arabic account/capability copy complete", required_i18n <= set(ar))
    check("English/Arabic keysets match", set(en) == set(ar))
    prefixes = {
        key
        for key in en
        if any(other.startswith(f"{key}.") for other in en if other != key)
    }
    check("translation keys have no scalar/object collisions", not prefixes)

    print("employee mobile capability foundation: GREEN")


if __name__ == "__main__":
    main()
