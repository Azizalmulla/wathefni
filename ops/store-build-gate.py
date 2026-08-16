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

    check("iOS bundleIdentifier is ai.wathefni.employee", ios.get("bundleIdentifier") == "ai.wathefni.employee")
    check("Android package is ai.wathefni.employee", android.get("package") == "ai.wathefni.employee")
    check("production API is api.wathefni.ai", prod_env.get("EXPO_PUBLIC_API_BASE_URL") == "https://api.wathefni.ai")
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
    check("associatedDomains includes api.wathefni.ai", any("applinks:api.wathefni.ai" in str(d) for d in (ios.get("associatedDomains") or [])))
    check("Android App Links intent filter present", any(
        (item.get("autoVerify") is True) and any(d.get("host") == "api.wathefni.ai" for d in (item.get("data") or []))
        for item in (android.get("intentFilters") or [])
        if isinstance(item, dict)
    ))
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
