"""Setup Console settings durability — operator keys survive the registry sync.

Bug this guards: sync_company_module_registry() refreshes company_settings.settings
from the workspace company.json profile on every startup/deploy. It used to do a
wholesale `settings = EXCLUDED.settings`, which silently reverted operator changes
made through the Setup Console (notification_preset, timezone) and the import
settings (intake_auto_admit_explicit).

Contract proven here (DB-backed, uses a throwaway company):
  1. Operator-managed keys are written through the real API handlers / shared
     set_company_setting writer.
  2. Running sync_company_module_registry() (the exact code path that runs on
     startup/deploy) PRESERVES every operator-managed key.
  3. The sync still refreshes non-operator profile fields from company.json (so the
     preservation isn't just a no-op — the upsert genuinely ran).
  4. DB operator value wins over a conflicting company.json value (precedence).
  5. OPERATOR_MANAGED_SETTING_KEYS covers exactly the keys set_company_setting writes.

Run with the orchestrator venv + prod/staging postgres env, e.g.:
  WATHEFNI_POSTGRES_ENV=... WATHEFNI_WORKSPACE=... \
    /opt/wathefni/orchestrator/.venv/bin/python smoke-test-settings-durability.py
"""

from __future__ import annotations

import json
import shutil
import sys
from typing import Any, Callable

import app

TEST_CO = "DURABILITYSMOKE"
FAKE_SUPERADMIN = {
    "actor_phone": "96599338566",
    "actor_role": "platform_admin",
    "actor_user_id": "settings-durability-smoke",
    "permission_authority": "backend_current",
    "permission_subject_user_id": "settings-durability-smoke",
    "permission_subject_company": TEST_CO,
    "actor_email": "smoke@wathefni.ai",
    "hr_user": "settings-durability-smoke",
}


def _write_company_json(profile: dict[str, Any]) -> None:
    root = app.company_root(TEST_CO)
    root.mkdir(parents=True, exist_ok=True)
    (root / "company.json").write_text(json.dumps(profile, indent=2))


def _purge() -> None:
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM company_settings WHERE company_code=%s", (TEST_CO,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (TEST_CO,))
                cur.execute("DELETE FROM company_channel_accounts WHERE company_code=%s", (TEST_CO,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (TEST_CO,))
                try:
                    cur.execute("DELETE FROM action_results WHERE company_code=%s", (TEST_CO,))
                except Exception:
                    conn.rollback()
            conn.commit()
    except Exception as exc:
        print(f"  WARN purge db: {exc}")
    try:
        root = app.company_root(TEST_CO)
        if root.exists():
            shutil.rmtree(root)
    except Exception as exc:
        print(f"  WARN purge fs: {exc}")


def _settings() -> dict[str, Any]:
    return app.get_company_settings(TEST_CO)


def _company_country() -> str | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT country FROM companies WHERE company_code=%s", (TEST_CO,))
            row = cur.fetchone()
    return (str((row or {}).get("country") or "").strip().upper() or None)


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def run_checks(checks: Checks) -> None:
    # --- 5. The allowlist matches the keys operators actually write ----------
    checks.check(
        "OPERATOR_MANAGED_SETTING_KEYS covers all operator-owned setup fields",
        lambda: set(app.OPERATOR_MANAGED_SETTING_KEYS) == {
            "timezone", "currency", "notification_preset",
            "channel_policy_reviewed", "intake_auto_admit_explicit",
        },
    )

    # --- Arrange: create company + seed a profile WITHOUT operator keys ------
    app.setup_console_create_company(
        app.SetupCompanyCreateRequest(company_code=TEST_CO, name="Durability Smoke"),
        superadmin=FAKE_SUPERADMIN,
    )
    _write_company_json({"code": TEST_CO, "name": "Durability Smoke", "sector": "SmokeV1", "country": "KW", "modules": ["shifts"]})

    # Initial sync seeds settings from company.json (no operator keys yet).
    app.sync_company_module_registry()
    seeded = _settings()
    checks.check("initial sync seeds profile (country=KW)", lambda: seeded.get("country") == "KW")
    checks.check("new company keeps GCC timezone/currency defaults", lambda: seeded.get("timezone") == "Asia/Kuwait" and seeded.get("currency") == "KWD")
    checks.check("initial sync has no notification/channel review yet", lambda: "notification_preset" not in seeded and "channel_policy_reviewed" not in seeded)

    # --- Act: set operator keys through the real API handlers / writer -------
    app.setup_console_set_settings(
        TEST_CO,
        app.SetupSettingsRequest(
            timezone="Asia/Riyadh",
            currency="SAR",
            notification_preset="office",
            channel_policy_reviewed=True,
        ),
        superadmin=FAKE_SUPERADMIN,
    )
    # intake_auto_admit_explicit goes through PUT /dashboard/prehire/import/settings,
    # which funnels through the same set_company_setting writer.
    app.set_company_setting(TEST_CO, "intake_auto_admit_explicit", False)

    after_set = _settings()
    checks.check("API set: timezone persisted", lambda: after_set.get("timezone") == "Asia/Riyadh")
    checks.check("API set: notification_preset persisted", lambda: after_set.get("notification_preset") == "office")
    checks.check("API set: currency persisted", lambda: after_set.get("currency") == "SAR")
    checks.check("API set: channel review persisted", lambda: after_set.get("channel_policy_reviewed") is True)
    checks.check("API set: intake_auto_admit_explicit persisted", lambda: after_set.get("intake_auto_admit_explicit") is False)

    # --- Assert: a restart/deploy-style re-sync does NOT clobber them --------
    # Also mutate a NON-operator profile field so we can prove the upsert genuinely
    # ran (preservation must not be a silent no-op).
    _write_company_json({"code": TEST_CO, "name": "Durability Smoke", "sector": "SmokeV2", "country": "BH", "modules": ["shifts"]})
    app.sync_company_module_registry()
    after_sync = _settings()
    checks.check("after re-sync: timezone preserved", lambda: after_sync.get("timezone") == "Asia/Riyadh")
    checks.check("after re-sync: notification_preset preserved", lambda: after_sync.get("notification_preset") == "office")
    checks.check("after re-sync: currency preserved", lambda: after_sync.get("currency") == "SAR")
    checks.check("after re-sync: channel review preserved", lambda: after_sync.get("channel_policy_reviewed") is True)
    checks.check("after re-sync: intake_auto_admit_explicit preserved", lambda: after_sync.get("intake_auto_admit_explicit") is False)
    checks.check("after re-sync: profile field refreshed (sector=SmokeV2 — proves upsert ran)", lambda: after_sync.get("sector") == "SmokeV2")
    checks.check("after re-sync: profile field refreshed (country=BH)", lambda: after_sync.get("country") == "BH")

    # --- Precedence: DB operator value wins over a conflicting company.json --
    _write_company_json({
        "code": TEST_CO,
        "name": "Durability Smoke",
        "sector": "SmokeV3",
        "country": "BH",
        "modules": ["shifts"],
        "timezone": "UTC",
        "currency": "BHD",
        "notification_preset": "conservative",
        "channel_policy_reviewed": False,
    })
    app.sync_company_module_registry()
    after_conflict = _settings()
    checks.check("precedence: operator timezone wins over company.json", lambda: after_conflict.get("timezone") == "Asia/Riyadh")
    checks.check("precedence: operator notification_preset wins over company.json", lambda: after_conflict.get("notification_preset") == "office")
    checks.check("precedence: operator currency wins over company.json", lambda: after_conflict.get("currency") == "SAR")
    checks.check("precedence: operator channel review wins over company.json", lambda: after_conflict.get("channel_policy_reviewed") is True)

    # The Setup Console readiness snapshot reflects the durable explicit value.
    r = app.setup_console_company_readiness(TEST_CO)
    checks.check("readiness shows explicit notification_preset after re-sync", lambda: r.get("notification_preset") == "office" and r.get("notification_preset_explicit") is True)

    # --- Country lives on companies.country (column), NOT company_settings -----
    # company.json profile currently says country=BH (from SmokeV3 above). The
    # operator sets a DIFFERENT country through Setup Console; it must land on the
    # `companies.country` column, drive readiness, survive a restart-style sync,
    # and must NOT be shoved into company_settings.settings.
    app.setup_console_set_settings(
        TEST_CO,
        app.SetupSettingsRequest(country="sa"),  # lowercase in -> normalized to SA
        superadmin=FAKE_SUPERADMIN,
    )
    checks.check("country: written to companies.country column (SA)", lambda: _company_country() == "SA")
    r_country = app.setup_console_company_readiness(TEST_CO)
    checks.check("country: readiness reflects companies.country (SA)", lambda: r_country.get("country") == "SA")
    checks.check("country: NOT shoved into company_settings.settings (profile stays BH)", lambda: _settings().get("country") == "BH")

    # Restart/deploy-style re-sync must not clobber the column-backed country.
    app.sync_company_module_registry()
    checks.check("country: companies.country survives re-sync (SA)", lambda: _company_country() == "SA")
    checks.check("country: readiness still SA after re-sync", lambda: app.setup_console_company_readiness(TEST_CO).get("country") == "SA")

    # Invalid country is rejected (defensive — operators can't write junk).
    def _bad_country() -> bool:
        try:
            app.setup_console_set_settings(TEST_CO, app.SetupSettingsRequest(country="Kuwait"), superadmin=FAKE_SUPERADMIN)
            return False
        except app.HTTPException as exc:
            return exc.status_code == 422
    checks.check("country: non-ISO value rejected with 422", _bad_country)


def main() -> None:
    print("setup console settings durability — operator keys survive registry sync")
    _purge()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        _purge()
    code = checks.report()
    if code:
        print("\nSETTINGS DURABILITY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nSETTINGS DURABILITY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
