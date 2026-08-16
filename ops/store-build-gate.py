#!/usr/bin/env python3
"""Store build gate — production iOS/Android configuration for App Store / Play.

Does not claim a completed store submission. Fails closed on demo flags,
staging API URLs in the production profile, or missing identifiers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0
REPO = Path(__file__).resolve().parents[1]
APP = REPO / "apps" / "wathefni-employee-mobile"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    STORE BUILD GATE")
    app_json = json.loads((APP / "app.json").read_text(encoding="utf-8"))
    eas = json.loads((APP / "eas.json").read_text(encoding="utf-8"))
    expo = app_json["expo"]
    ios = expo.get("ios") or {}
    android = expo.get("android") or {}
    plugins = expo.get("plugins") or []
    production = (eas.get("build") or {}).get("production") or {}
    store = (eas.get("build") or {}).get("store") or {}
    prod_env = store.get("env") or production.get("env") or {}

    hr_settings = (APP / "src/hr/features/settings/SettingsView.tsx").read_text(encoding="utf-8")
    employee_settings = (APP / "src/features/remaining/RemainingViews.tsx").read_text(encoding="utf-8")
    en = json.loads((APP / "src/i18n/en.json").read_text(encoding="utf-8"))
    ar = json.loads((APP / "src/i18n/ar.json").read_text(encoding="utf-8"))

    check("iOS bundleIdentifier is ai.wathefni.employee", ios.get("bundleIdentifier") == "ai.wathefni.employee")
    check("Android package is ai.wathefni.employee", android.get("package") == "ai.wathefni.employee")
    check("customer-visible app name is OctoHR", expo.get("name") == "OctoHR")
    check("production API is api.octo-hr.com", prod_env.get("EXPO_PUBLIC_API_BASE_URL") == "https://api.octo-hr.com")
    check("production privacy URL is canonical", prod_env.get("EXPO_PUBLIC_PRIVACY_URL") == "https://octo-hr.com/privacy")
    check("production support URL is canonical", prod_env.get("EXPO_PUBLIC_SUPPORT_URL") == "https://octo-hr.com/support")
    check("production API is not staging", "staging" not in str(prod_env.get("EXPO_PUBLIC_API_BASE_URL") or ""))
    check("production release flag is on", prod_env.get("EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE") == "1")
    check("production does not set HR demo flags", not any("DEMO" in k for k in prod_env))
    check("Face ID usage description present", bool((ios.get("infoPlist") or {}).get("NSFaceIDUsageDescription")))
    check("camera usage description present", bool((ios.get("infoPlist") or {}).get("NSCameraUsageDescription")))
    check("photo library usage description present", bool((ios.get("infoPlist") or {}).get("NSPhotoLibraryUsageDescription")))
    check("Android camera permission declared", "android.permission.CAMERA" in (android.get("permissions") or []))
    check("Android biometric permission declared", "android.permission.USE_BIOMETRIC" in (android.get("permissions") or []))
    blocked_permissions = set(android.get("blockedPermissions") or [])
    check(
        "Android store blocks unused/restricted permissions",
        {
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.RECORD_AUDIO",
            "android.permission.SYSTEM_ALERT_WINDOW",
            "android.permission.WRITE_EXTERNAL_STORAGE",
        }.issubset(blocked_permissions),
        sorted(blocked_permissions),
    )
    check("Android store does not request microphone", "android.permission.RECORD_AUDIO" not in (android.get("permissions") or []))
    check("push plugin present", any("expo-notifications" in str(p) for p in expo.get("plugins") or []))
    check("updates URL is Expo", str((expo.get("updates") or {}).get("url") or "").startswith("https://u.expo.dev/"))
    associated_domains = set(ios.get("associatedDomains") or [])
    check("associatedDomains includes canonical host", "applinks:api.octo-hr.com" in associated_domains)
    check("associatedDomains preserves legacy host", "applinks:api.wathefni.ai" in associated_domains)
    app_link_hosts = {
        str(data.get("host") or "")
        for item in (android.get("intentFilters") or [])
        if isinstance(item, dict) and item.get("autoVerify") is True
        for data in (item.get("data") or [])
        if isinstance(data, dict) and data.get("scheme") == "https" and data.get("pathPrefix") == "/l"
    }
    check("Android App Links includes canonical host", "api.octo-hr.com" in app_link_hosts)
    check("Android App Links preserves legacy host", "api.wathefni.ai" in app_link_hosts)
    # Store distribution is required before Apple/Google submission. Internal
    # canary APK/IPA is not a store build.
    dist = store.get("distribution")
    android_type = (store.get("android") or {}).get("buildType")
    check("store EAS profile exists", bool(store), "missing build.store")
    check("store EAS profile is not a development client", store.get("developmentClient") is not True)
    check("store EAS update channel is production", store.get("channel") == "production", store.get("channel"))
    check(
        "store EAS profile is store distribution (not internal canary)",
        dist == "store",
        f"distribution={dist} android.buildType={android_type}",
    )
    check(
        "Android production buildType is app-bundle",
        android_type == "app-bundle",
        android_type,
    )
    cfg = (APP / "app.config.js").read_text(encoding="utf-8")
    check("app.config.js refuses demo flags on production release", "production release cannot bake demo flags" in cfg)
    check(
        "HR Settings excludes engineering diagnostics",
        not (APP / "src/hr/features/settings/HrSessionQueueProbe.tsx").exists()
        and all(
            token not in hr_settings
            for token in ("HrSessionQueueProbe", "sectionProbe", "probeHint", "sectionAccess", "accessHint")
        ),
    )
    check(
        "Employee Settings excludes auto-lock diagnostics panel",
        "autoLockDiagnostics" not in employee_settings and "diagnosticsTitle" not in employee_settings,
    )
    translations = json.dumps({"en": en, "ar": ar}, ensure_ascii=False)
    check(
        "customer translations use OctoHR branding",
        all(token not in translations for token in ("Wathefni", "WATHEFNI", "وظفني", "وثفني")),
    )
    check("Arabic OS permission locale file present", (APP / "locales" / "ar.json").is_file())
    dev_client_plugin = next(
        (item for item in plugins if isinstance(item, list) and item and item[0] == "expo-dev-client"),
        None,
    )
    check(
        "development client generated scheme disabled",
        bool(dev_client_plugin)
        and isinstance(dev_client_plugin[1] if len(dev_client_plugin) > 1 else None, dict)
        and dev_client_plugin[1].get("addGeneratedScheme") is False,
    )
    check(
        "Android backup and cleartext security plugin present",
        "./plugins/withAndroidStoreSecurity" in plugins
        and (APP / "plugins" / "withAndroidStoreSecurity.js").is_file(),
    )

    print("\n    STORE_BUILD_GATE_PASS" if not FAIL else "\n    STORE_BUILD_GATE_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
