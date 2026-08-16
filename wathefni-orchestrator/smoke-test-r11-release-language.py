#!/usr/bin/env python3
"""Production Readiness R11 — critical EN/AR/RTL release-language contracts.

Store/canary scope: Employee App + HR co-bundle + standalone HR Mobile catalogs,
RTL wiring, and critical journey keys. Does not start the HR Web UX redesign.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0
REPO = Path(__file__).resolve().parents[1]
EMP = REPO / "apps" / "wathefni-employee-mobile"
HR = REPO / "apps" / "wathefni-hr-mobile"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = str(value or "")
    return out


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parity(label: str, en: dict, ar: dict) -> None:
    en_f = flatten(en)
    ar_f = flatten(ar)
    missing_ar = sorted(set(en_f) - set(ar_f))
    missing_en = sorted(set(ar_f) - set(en_f))
    empty_ar = sorted(k for k, v in ar_f.items() if not str(v or "").strip())
    check(f"{label} EN/AR key parity", not missing_ar and not missing_en, {"en-only": missing_ar[:8], "ar-only": missing_en[:8]})
    check(f"{label} AR values not empty", not empty_ar, empty_ar[:8])


def prefixes(label: str, en: dict, required: list[str]) -> None:
    flat = flatten(en)
    for prefix in required:
        stem = prefix.rstrip(".")
        ok = stem in en or any(k == stem or k.startswith(stem + ".") for k in flat)
        check(f"{label} has {stem}", ok)


def main() -> int:
    print("    PRODUCTION READINESS R11 — release language")
    emp_en = load(EMP / "src" / "i18n" / "en.json")
    emp_ar = load(EMP / "src" / "i18n" / "ar.json")
    hr_en = load(EMP / "src" / "hr" / "i18n" / "en.json")
    hr_ar = load(EMP / "src" / "hr" / "i18n" / "ar.json")
    standalone_en = load(HR / "src" / "i18n" / "en.json")
    standalone_ar = load(HR / "src" / "i18n" / "ar.json")

    parity("employee app", emp_en, emp_ar)
    parity("HR co-bundle", hr_en, hr_ar)
    parity("HR mobile standalone", standalone_en, standalone_ar)

    prefixes(
        "employee app",
        emp_en,
        [
            "auth", "home", "leave", "schedule", "onboarding", "documents",
            "payslips", "notifications", "pin", "biometric", "feature.unavailable",
            "performance", "talent", "learning", "benefits", "engagement",
        ],
    )
    prefixes("HR co-bundle", hr_en, ["auth", "home", "common"])
    prefixes("HR mobile standalone", standalone_en, ["auth", "home", "common"])

    for catalog, name in ((emp_en, "employee"), (hr_en, "hr-cobundle"), (standalone_en, "hr-standalone")):
        for key in ("auth.genericError", "common.retry"):
            if key in catalog:
                check(f"{name} {key} present", True)
            else:
                # HR catalogs use auth.genericError; employee may use a different error key.
                alts = [k for k in catalog if "error" in k.lower() or k.endswith(".retry")]
                check(f"{name} has error/retry copy", bool(alts), alts[:6])

    emp_i18n = (EMP / "src" / "i18n" / "index.tsx").read_text(encoding="utf-8")
    hr_i18n = (EMP / "src" / "hr" / "i18n" / "index.tsx").read_text(encoding="utf-8")
    check("employee forceRTL wiring", "I18nManager.forceRTL" in emp_i18n)
    check("HR co-bundle forceRTL wiring", "I18nManager.forceRTL" in hr_i18n)

    app_json = (EMP / "app.json").read_text(encoding="utf-8")
    check("iOS Face ID usage string exists", "NSFaceIDUsageDescription" in app_json)
    check("camera usage string exists", "NSCameraUsageDescription" in app_json)
    # Expo locale files place Apple permission strings under `ios`; keeping them
    # at the shared root is interpreted as invalid Android ExtraTranslation data.
    check("Face ID usage is truthful about PIN fallback", "PIN still works" in app_json)
    locales = EMP / "locales" / "ar.json"
    check("Arabic OS permission strings exist", locales.is_file())
    if locales.is_file():
        locale_payload = json.loads(locales.read_text(encoding="utf-8"))
        ar_perm = locale_payload.get("ios") or {}
        check("Arabic Face ID string is non-English", any(ord(ch) > 127 for ch in str(ar_perm.get("NSFaceIDUsageDescription") or "")))

    dash = REPO / "apps" / "wathefni-dashboard" / "src"
    web_surfaces = {
        "leave": dash / "posthire" / "leaveUx.ts",
        "payroll": dash / "posthire" / "ExternalPayrollWorkspace.tsx",
        "talent": dash / "posthire" / "TalentWorkspace.tsx",
        "auth": dash / "App.tsx",
    }
    for name, path in web_surfaces.items():
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        check(f"HR Web {name} exists", path.is_file(), str(path))
        if path.is_file():
            bilingual = "isAr ?" in text or "locale === 'ar'" in text or 'locale === "ar"' in text or "recruitingLocale === 'ar'" in text
            check(f"HR Web {name} has EN/AR branch", bilingual)
            check(f"HR Web {name} contains Arabic copy", any(ord(ch) > 127 for ch in text), "no Arabic glyphs")

    print("\n    R11_RELEASE_LANGUAGE_UNIT_PASS" if not FAIL else "\n    R11_RELEASE_LANGUAGE_UNIT_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
