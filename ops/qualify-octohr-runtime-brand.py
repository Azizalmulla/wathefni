#!/usr/bin/env python3
"""Deterministic OctoHR runtime-brand qualification for shipping surfaces.

The source gate is necessary but insufficient: this also renders the canonical
server communication catalogs and disassembles compiled Hermes bundles. Signed
IPA/APK/AAB archives may be supplied to audit their native display strings.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "wathefni-employee-mobile"
ORCHESTRATOR = ROOT / "wathefni-orchestrator"
HERMESC = MOBILE / "node_modules" / "react-native" / "sdks" / "hermesc" / "osx-bin" / "hermesc"

OLD_BRAND = re.compile(r"(?<![A-Za-z0-9_])wathefni(?![A-Za-z0-9_])|وظفني|وظّفني|وثفني|وثّفني|وطّفني", re.IGNORECASE)
COMPILED_TECHNICAL_MARKERS = (
    "ai.wathefni.employee",
    "api.wathefni.ai",
    "wathefni.ai/employee-app/privacy",
    "wathefni://",
    "wathefni:",
    "wathefni.",
    "wathefni_",
    "wathefni-",
    "__wathefni",
    "WATHEFNI_",
    "WathefniBloom",
    "WathefniMark",
    "apps/wathefni-employee-mobile",
    "Payload/Wathefni.app",
)


class Qualification:
    def __init__(self) -> None:
        self.checks = 0
        self.defects: list[str] = []

    def check(self, condition: bool, label: str, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            suffix = f": {detail}" if detail else ""
            self.defects.append(f"{label}{suffix}")

    def customer_copy(self, value: Any, label: str) -> None:
        text = str(value or "")
        matches = sorted({m.group(0) for m in OLD_BRAND.finditer(text)})
        self.check(not matches, label, ", ".join(matches))


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk_strings(nested)


def _compiled_old_brand_is_technical(value: str) -> bool:
    if not OLD_BRAND.search(value):
        return True
    if value == "wathefni":  # Stable custom URL scheme; not customer copy.
        return True
    if any(marker in value for marker in COMPILED_TECHNICAL_MARKERS):
        return True
    # This defensive regex is deliberately shipped so stale tenant records can
    # never restore the retired customer brand.
    if "وظفني" in value and "وثفني" in value and "wathefni" in value.lower():
        return True
    return False


def _hermes_strings(bundle: Path) -> list[str]:
    if not HERMESC.is_file():
        raise RuntimeError(f"Hermes compiler missing: {HERMESC}")
    result = subprocess.run(
        [str(HERMESC), "-b", "-dump-bytecode", str(bundle)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    values: list[str] = []
    in_table = False
    for line in result.stdout.splitlines():
        if line == "Global String Table:":
            in_table = True
            continue
        if in_table and line.startswith("Function<"):
            break
        if not in_table:
            continue
        match = re.match(r"^[si]\d+\[[^]]*\](?: [^:]+)?: (.*)$", line)
        if match:
            values.append(match.group(1))
    return values


def _audit_hermes(q: Qualification, bundle: Path, platform: str) -> None:
    q.check(bundle.is_file(), f"{platform} compiled Hermes bundle exists", str(bundle))
    if not bundle.is_file():
        return
    values = _hermes_strings(bundle)
    q.check(bool(values), f"{platform} Hermes string table decoded")
    defects = sorted({value for value in values if OLD_BRAND.search(value) and not _compiled_old_brand_is_technical(value)})
    q.check(not defects, f"{platform} compiled customer-visible old brand", " | ".join(defects[:30]))


def _audit_app_config(q: Qualification) -> None:
    config = json.loads((MOBILE / "app.json").read_text(encoding="utf-8"))["expo"]
    q.check(config.get("name") == "OctoHR", "Expo display name is OctoHR", str(config.get("name")))
    q.check(config.get("runtimeVersion", {}).get("policy") == "appVersion", "OTA runtime is appVersion-isolated")
    for index, value in enumerate(_walk_strings(config)):
        if OLD_BRAND.search(value) and not _compiled_old_brand_is_technical(value):
            q.check(False, f"app.json customer string {index}", value)


def _audit_tenant_brand_contract(q: Qualification) -> None:
    resolver = (MOBILE / "src" / "branding" / "CompanyBrand.tsx").read_text(encoding="utf-8")
    wordmark = (MOBILE / "src" / "components" / "premium.tsx").read_text(encoding="utf-8")
    employee_layout = (MOBILE / "app" / "_layout.tsx").read_text(encoding="utf-8")
    hr_layout = (MOBILE / "app" / "hr" / "_layout.tsx").read_text(encoding="utf-8")
    app_backend = (ORCHESTRATOR / "app.py").read_text(encoding="utf-8")
    hr_backend = (ORCHESTRATOR / "operator_mobile.py").read_text(encoding="utf-8")

    q.check("[identity.display_name_ar, identity.display_name_en, identity.display_name]" in resolver, "Arabic tenant-name priority")
    q.check("[identity.display_name_en, identity.display_name, identity.display_name_ar]" in resolver, "English tenant-name priority")
    q.check("name: PLATFORM_BRAND, logoUrl: null, isTenantBrand: false" in resolver, "unresolved tenant falls back to OctoHR")
    q.check("parsed.protocol !== 'https:'" in resolver and "parsed.username || parsed.password" in resolver, "tenant logo URL is HTTPS and credential-free")
    q.check("{brand.name}" in wordmark and "source={{ uri: brand.logoUrl }}" in wordmark, "shared authenticated wordmark renders tenant name/logo")
    q.check("showPlatformAttribution && brand.isTenantBrand" in wordmark, "Powered by OctoHR is subtle tenant-only attribution")
    q.check("identity={me?.company_identity}" in employee_layout, "Employee shell binds canonical tenant identity")
    q.check("identity={me?.company_identity}" in hr_layout, "HR shell binds canonical tenant identity")
    q.check('"company_identity": mobile_company_identity' in app_backend, "Employee /app/me returns tenant identity")
    q.check('"company_identity": app_mod.mobile_company_identity' in hr_backend, "HR /mobile/me returns tenant identity")
    q.check('email_subject="Your OctoHR app activation code"' in app_backend, "activation email subject uses OctoHR")
    q.check(
        'text=f"Your {company_display_name(company)} app activation code is {code}.' in app_backend,
        "activation body uses the resolved safe company display name",
    )

    runtime = subprocess.run(
        ["node", str(MOBILE / "scripts" / "verify-company-brand-runtime.js")],
        cwd=MOBILE,
        text=True,
        capture_output=True,
    )
    if runtime.stdout:
        print(runtime.stdout.rstrip())
    q.check(runtime.returncode == 0, "tenant brand resolver runtime contract", runtime.stderr.strip())


def _sample_variables() -> dict[str, str]:
    return {
        "employee_name": "Sample Employee",
        "company_name": "Acme Company",
        "date_text": "2026-08-23 to 2026-08-25",
        "start_date": "2026-08-23",
        "end_date": "2026-08-25",
        "shift_date": "2026-08-23",
        "shift_time": "09:00-17:00",
        "document_type": "civil ID",
        "expiry_date": "2026-09-01",
        "period": "2026-08",
        "code": "123456",
        "expiry_hours": "24",
    }


def _audit_server_communications(q: Qualification) -> None:
    sys.path.insert(0, str(ORCHESTRATOR))
    import employee_push_tray as push_tray  # type: ignore
    import outbound_delivery as outbound  # type: ignore
    import tenant_email_authority as tenant_email  # type: ignore

    variables = _sample_variables()
    rendered = 0
    for template_key in sorted(outbound.TEMPLATE_CATALOG):
        for locale in ("en", "ar"):
            q.customer_copy(outbound.catalog_label(template_key, locale), f"email/in-app label {template_key}/{locale}")
            q.customer_copy(outbound.render_body(template_key, variables, locale), f"email/in-app body {template_key}/{locale}")
            rendered += 2
    for template_key in sorted(push_tray.PUSH_TRAY):
        for locale in ("en", "ar"):
            title, body = push_tray.tray_copy(template_key, locale=locale, variables=variables)
            q.customer_copy(title, f"push title {template_key}/{locale}")
            q.customer_copy(body, f"push body {template_key}/{locale}")
            rendered += 2

    q.check(tenant_email._customer_brand_text("Wathefni") is None, "legacy English tenant sender is rejected")
    q.check(tenant_email._customer_brand_text("وظفني") is None, "legacy Arabic tenant sender is rejected")
    q.check(
        tenant_email.format_from_header("Wathefni", "notifications@example.com") == "notifications@example.com",
        "legacy shared-sender display name cannot escape",
    )
    print(f"RUNTIME_BRAND_RENDERED_COMMUNICATIONS={rendered}")


def _archive_member(archive: zipfile.ZipFile, suffix: str) -> str | None:
    return next((name for name in archive.namelist() if name.endswith(suffix)), None)


def _audit_ipa(q: Qualification, ipa: Path) -> None:
    q.check(ipa.is_file(), "signed IPA exists", str(ipa))
    if not ipa.is_file():
        return
    with zipfile.ZipFile(ipa) as archive:
        info_member = _archive_member(archive, ".app/Info.plist")
        bundle_member = _archive_member(archive, ".app/main.jsbundle")
        q.check(bool(info_member), "IPA Info.plist exists")
        q.check(bool(bundle_member), "IPA embedded Hermes bundle exists")
        if info_member:
            info = plistlib.loads(archive.read(info_member))
            q.check(info.get("CFBundleDisplayName") == "OctoHR", "IPA display name is OctoHR", str(info.get("CFBundleDisplayName")))
            for key in ("NSCameraUsageDescription", "NSPhotoLibraryUsageDescription", "NSMicrophoneUsageDescription", "NSFaceIDUsageDescription"):
                if info.get(key):
                    q.customer_copy(info[key], f"IPA {key}")
        if bundle_member:
            with tempfile.NamedTemporaryFile(suffix=".hbc") as handle:
                handle.write(archive.read(bundle_member))
                handle.flush()
                _audit_hermes(q, Path(handle.name), "signed iOS")


def _audit_android_archive(q: Qualification, archive_path: Path, archive_kind: str) -> None:
    q.check(archive_path.is_file(), f"signed {archive_kind} exists", str(archive_path))
    if not archive_path.is_file():
        return
    with zipfile.ZipFile(archive_path) as archive:
        bundle_member = _archive_member(archive, "assets/index.android.bundle")
        resources_member = _archive_member(archive, "resources.arsc") or _archive_member(archive, "resources.pb")
        q.check(bool(bundle_member), f"{archive_kind} embedded Hermes bundle exists")
        q.check(bool(resources_member), f"{archive_kind} resource table exists")
        if bundle_member:
            with tempfile.NamedTemporaryFile(suffix=".hbc") as handle:
                handle.write(archive.read(bundle_member))
                handle.flush()
                _audit_hermes(q, Path(handle.name), "signed Android")
        if resources_member:
            with tempfile.NamedTemporaryFile(suffix=Path(resources_member).suffix) as handle:
                handle.write(archive.read(resources_member))
                handle.flush()
                strings = subprocess.run(["strings", "-a", handle.name], check=True, text=True, capture_output=True).stdout.splitlines()
            q.check(any("OctoHR" in value for value in strings), f"{archive_kind} native resource identifies OctoHR")
            defects = sorted({value for value in strings if OLD_BRAND.search(value) and not _compiled_old_brand_is_technical(value)})
            q.check(not defects, f"{archive_kind} native resource customer-visible old brand", " | ".join(defects[:30]))


def _source_gate(q: Qualification) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "ops" / "qualify-octohr-public-brand.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    q.check(result.returncode == 0, "customer-visible source brand gate", result.stderr.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ios-bundle", type=Path)
    parser.add_argument("--android-bundle", type=Path)
    parser.add_argument("--ios-ipa", type=Path)
    parser.add_argument("--android-apk", type=Path)
    parser.add_argument("--android-aab", type=Path)
    args = parser.parse_args()

    q = Qualification()
    _source_gate(q)
    _audit_app_config(q)
    _audit_tenant_brand_contract(q)
    _audit_server_communications(q)
    if args.ios_bundle:
        _audit_hermes(q, args.ios_bundle, "iOS")
    if args.android_bundle:
        _audit_hermes(q, args.android_bundle, "Android")
    if args.ios_ipa:
        _audit_ipa(q, args.ios_ipa)
    if args.android_apk:
        _audit_android_archive(q, args.android_apk, "APK")
    if args.android_aab:
        _audit_android_archive(q, args.android_aab, "AAB")

    print(f"RUNTIME_BRAND_CHECKS={q.checks}")
    print(f"RUNTIME_BRAND_DEFECTS={len(q.defects)}")
    if q.defects:
        print("RUNTIME_BRAND_DEFECT_LIST:")
        for defect in q.defects:
            print(f"- {defect}")
        print("OCTOHR_RUNTIME_BRAND_FAILED")
        return 1
    print("OCTOHR_RUNTIME_BRAND_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
