#!/usr/bin/env python3
"""Static safety checks for the Google Play closed-test provisioner."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "ops" / "provision-octohr-closed-test.py").read_text(encoding="utf-8")


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS: {label}")


def main() -> int:
    check('COMPANY = "OCTOHR-CLOSED-TEST"' in SOURCE, "tenant is hard-pinned")
    check("ACCOUNT_COUNT = 15" in SOURCE, "fifteen distinct tester identities")
    check("/auth/store-review" not in SOURCE, "no store-review authentication adapter")
    check("/app/auth/" not in SOURCE, "no employee authentication adapter")
    check("'hr_manager','active'" in SOURCE, "ordinary HR manager accounts")
    check("legacy.dashboard_password_hash" in SOURCE, "normal dashboard password authority")
    check("settings_manage\": False" in SOURCE, "report declares no Setup authority")
    check("users_manage\": False" in SOURCE, "report declares no user administration")
    check("dashboard_user_permission_grants" in SOURCE and "'employees.read'" in SOURCE, "grant-only employee directory read")
    check("'employees.manage'" not in SOURCE, "no employee management grant")
    check("synthetic_only" in SOURCE, "tenant and records marked synthetic")
    check("0o600" in SOURCE, "credential files owner-only")
    check("passwords_in_report\": False" in SOURCE, "report excludes passwords")
    check("credentials_expire_after_14_days\": False" in SOURCE, "credentials persist beyond day fourteen")
    check("prehire_jobs.create_job" in SOURCE, "hiring data uses canonical job authority")
    check("performance.create_objective" in SOURCE, "performance data uses frozen authority")
    check("performance_reviews.launch_cycle" in SOURCE, "performance review uses frozen authority")
    print("CLOSED_TEST_PROVISIONER_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
