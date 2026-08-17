#!/usr/bin/env python3
"""Static and configuration contracts for isolated store-review access."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import store_review_access as review


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def _credential_matrix() -> dict[str, object]:
    identities = []
    for store in ("apple", "google"):
        for principal in ("employee", "hr"):
            identities.append(
                {
                    "store": store,
                    "principal": principal,
                    "username": f"{store}.{principal}@review.octo-hr.com",
                    "subject_id": f"review-{store}-{principal}",
                    "password_hash": "pbkdf2_sha256$180000$00$00",
                }
            )
    return {"company_code": review.REVIEW_COMPANY_CODE, "identities": identities}


def main() -> None:
    old_enabled = os.environ.get("OCTOHR_STORE_REVIEW_ACCESS_ENABLED")
    old_path = os.environ.get("OCTOHR_STORE_REVIEW_CREDENTIALS_FILE")
    try:
        os.environ.pop("OCTOHR_STORE_REVIEW_ACCESS_ENABLED", None)
        check("kill switch defaults off", review.enabled() is False)
        os.environ["OCTOHR_STORE_REVIEW_ACCESS_ENABLED"] = "true"
        check("kill switch enables explicitly", review.enabled() is True)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review-identities.json"
            path.write_text(json.dumps(_credential_matrix()), encoding="utf-8")
            path.chmod(0o600)
            os.environ["OCTOHR_STORE_REVIEW_CREDENTIALS_FILE"] = str(path)
            rows = review._load_credentials()
            check("exactly four fixed identities", len(rows) == 4)
            check(
                "Apple and Google HR/Employee matrix is complete",
                {(row["store"], row["principal"]) for row in rows}
                == {(store, principal) for store in ("apple", "google") for principal in ("employee", "hr")},
            )
            check("all identities pin to review tenant configuration", review.REVIEW_COMPANY_CODE == "OCTOHR-STORE-REVIEW")

            unsafe = path.with_name("unsafe.json")
            unsafe.write_text(json.dumps(_credential_matrix()), encoding="utf-8")
            unsafe.chmod(0o644)
            os.environ["OCTOHR_STORE_REVIEW_CREDENTIALS_FILE"] = str(unsafe)
            try:
                review._load_credentials()
            except RuntimeError as exc:
                check("group/world-readable credential file is rejected", str(exc) == "review_credentials_file_permissions")
            else:
                raise AssertionError("unsafe credentials file accepted")

            wrong = _credential_matrix()
            wrong["company_code"] = "OTHER"
            path.write_text(json.dumps(wrong), encoding="utf-8")
            path.chmod(0o600)
            os.environ["OCTOHR_STORE_REVIEW_CREDENTIALS_FILE"] = str(path)
            try:
                review._load_credentials()
            except RuntimeError as exc:
                check("wrong tenant configuration is rejected", str(exc) == "review_credentials_wrong_tenant")
            else:
                raise AssertionError("wrong-tenant credentials accepted")

        root = Path(__file__).resolve().parents[1]
        server = (root / "wathefni-orchestrator" / "store_review_access.py").read_text(encoding="utf-8")
        mobile = (root / "apps" / "wathefni-employee-mobile" / "src" / "principals" / "UnifiedSignInView.tsx").read_text(encoding="utf-8")
        migration = (root / "wathefni-orchestrator" / "migrations" / "0002_octohr_store_review_access.sql").read_text(encoding="utf-8")
        check("normal Employee activation endpoint is untouched", "/app/auth/activate" not in server)
        check("normal HR login endpoint is untouched", "/dashboard/mobile/auth/login" not in server)
        check("Employee delegates to standard session creation", "create_employee_session(" in server)
        check("HR delegates to standard operator session creation", "create_operator_mobile_session(" in server)
        check("review identities are never read from request tenant fields", "company_code: str" not in server)
        check("review access writes a durable audit trail", "store_review_access_audit" in server and "store_review_access_audit" in migration)
        check("mobile review entry is server availability controlled", "/auth/store-review-availability" in mobile)
        check("no reviewer password is embedded in mobile source", "review.octo-hr.com" not in mobile and "pbkdf2_sha256" not in mobile)
    finally:
        if old_enabled is None:
            os.environ.pop("OCTOHR_STORE_REVIEW_ACCESS_ENABLED", None)
        else:
            os.environ["OCTOHR_STORE_REVIEW_ACCESS_ENABLED"] = old_enabled
        if old_path is None:
            os.environ.pop("OCTOHR_STORE_REVIEW_CREDENTIALS_FILE", None)
        else:
            os.environ["OCTOHR_STORE_REVIEW_CREDENTIALS_FILE"] = old_path

    print("OCTOHR_STORE_REVIEW_ACCESS_PASS")


if __name__ == "__main__":
    main()
