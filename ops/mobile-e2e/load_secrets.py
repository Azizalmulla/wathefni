#!/usr/bin/env python3
"""Load Wathefni mobile E2E secrets from local-only paths into os.environ.

Never prints secret values. Safe to import from gate/fixture/BrowserStack runners.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CANDIDATES = (
    Path.home() / ".config" / "wathefni" / "e2e.env",
    Path.home() / ".config" / "wathefni" / "browserstack.env",
    ROOT / "ops" / "mobile-e2e" / ".env.local",
    ROOT / "apps" / "wathefni-employee-mobile" / ".env.local",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def load_secrets(*, override: bool = True) -> list[str]:
    """Load known secret files. Returns list of loaded path strings (no values).

    Default override=True so ~/.config/wathefni/*.env wins over stale exported shell vars.
    """
    loaded: list[str] = []
    for path in CANDIDATES:
        if not path.is_file():
            continue
        try:
            data = _parse_env_file(path)
        except OSError:
            continue
        for key, value in data.items():
            if not value:
                continue
            if override or key not in os.environ or not os.environ.get(key):
                os.environ[key] = value
        loaded.append(str(path))
    # Mirror MOBILE_E2E_* → MAESTRO_* after file load (always refresh aliases from current values)
    mirrors = {
        "MOBILE_E2E_HR_COMPANY": "MAESTRO_HR_COMPANY",
        "MOBILE_E2E_COMPANY_CODE": "MAESTRO_HR_COMPANY",
        "MOBILE_E2E_HR_EMAIL": "MAESTRO_HR_EMAIL",
        "MOBILE_E2E_HR_PASSWORD": "MAESTRO_HR_PASSWORD",
        "MOBILE_E2E_EMPLOYEE_PHONE": "MAESTRO_EMPLOYEE_PHONE",
        "MOBILE_E2E_EMPLOYEE_CODE": "MAESTRO_EMPLOYEE_CODE",
        "MOBILE_E2E_LEAVE_ID": "MAESTRO_LEAVE_ID",
        "MOBILE_E2E_LEAVE_APPROVE_ID": "MAESTRO_LEAVE_ID",
        "MOBILE_E2E_LEAVE_REJECT_ID": "MAESTRO_LEAVE_REJECT_ID",
        "MOBILE_E2E_PIN": "MAESTRO_PIN",
    }
    for src, dst in mirrors.items():
        if os.environ.get(src):
            os.environ[dst] = os.environ[src]
    if not os.environ.get("MAESTRO_HR_COMPANY"):
        os.environ.setdefault("MAESTRO_HR_COMPANY", os.environ.get("MOBILE_E2E_HR_COMPANY") or "WATHEFNI")
    if not os.environ.get("MAESTRO_PIN"):
        os.environ.setdefault("MAESTRO_PIN", "246810")
    return loaded


if __name__ == "__main__":
    paths = load_secrets()
    print(
        {
            "loaded_files": paths,
            "hr_email_set": bool(os.environ.get("MAESTRO_HR_EMAIL") or os.environ.get("MOBILE_E2E_HR_EMAIL")),
            "hr_password_set": bool(os.environ.get("MAESTRO_HR_PASSWORD") or os.environ.get("MOBILE_E2E_HR_PASSWORD")),
            "employee_phone_set": bool(os.environ.get("MAESTRO_EMPLOYEE_PHONE") or os.environ.get("MOBILE_E2E_EMPLOYEE_PHONE")),
            "employee_code_set": bool(os.environ.get("MAESTRO_EMPLOYEE_CODE") or os.environ.get("MOBILE_E2E_EMPLOYEE_CODE")),
            "bs_user_set": bool(os.environ.get("BROWSERSTACK_USERNAME")),
            "leave_id_set": bool(os.environ.get("MAESTRO_LEAVE_ID")),
            "leave_reject_id_set": bool(os.environ.get("MAESTRO_LEAVE_REJECT_ID")),
        }
    )
