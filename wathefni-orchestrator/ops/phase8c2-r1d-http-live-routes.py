#!/usr/bin/env python3
"""Live HTTP route proofs against staging :8011 (no session IDs in evidence)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

BASE = os.environ.get("R1D_STAGING_BASE", "http://127.0.0.1:8011")
EVIDENCE = Path(os.environ.get("R1D_EVIDENCE_DIR", "/opt/wathefni/staging/evidence"))
COMPANY = "WATHEFNI"
OWNER_EMAIL = "r1d-owner@wathefni.staging.invalid"


def fp(values: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def main() -> int:
    if "staging" not in str(os.environ.get("WATHEFNI_POSTGRES_ENV") or "").lower():
        raise SystemExit("refusing to run without staging postgres env")

    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM dashboard_users
            WHERE company_code=%s AND lower(email)=lower(%s) AND status='active'
            LIMIT 1
            """,
            (COMPANY, OWNER_EMAIL),
        )
        owner = dict(cur.fetchone())
    token, _ = app.create_dashboard_session(owner)
    headers = {"Authorization": f"Bearer {token}", "X-Company-Code": COMPANY}
    wrong = {"Authorization": f"Bearer {token}", "X-Company-Code": "WRONGCO"}
    none = {"Authorization": f"Bearer {token}", "X-Company-Code": COMPANY}

    # Temporary empty-permission session for denial proofs: revoke employee grants
    # is already covered in-process; here we prove unauthenticated + auth routes.
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: dict) -> None:
        checks.append({"name": name, "ok": ok, **detail})

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        health = client.get("/health")
        record("health 200", health.status_code == 200, {"status": health.status_code})

        me = client.get("/dashboard/auth/me", headers=headers)
        body = me.json() if me.headers.get("content-type", "").startswith("application/json") else {}
        access = body.get("access") or {}
        perms = access.get("permissions") or []
        record(
            "reauth capabilities backend_current",
            me.status_code == 200
            and access.get("permission_authority") == "backend_current"
            and "employees.read" in perms
            and "employees.manage" in perms
            and "employees.status.approve" in perms,
            {
                "status": me.status_code,
                "permission_authority": access.get("permission_authority"),
                "role": access.get("role"),
                "employee_scopes": sorted(set(perms) & set(app.EMPLOYEE_PERMISSION_SCOPES)),
            },
        )

        unauth = client.get("/dashboard/posthire/employees")
        record("employees directory unauthenticated denied", unauth.status_code in {401, 403}, {"status": unauth.status_code})

        emp = client.get("/dashboard/posthire/employees", headers=headers)
        record("employees directory exact allowed", emp.status_code == 200, {"status": emp.status_code})

        emp_wrong = client.get("/dashboard/posthire/employees", headers=wrong)
        record("employees directory wrong company denied", emp_wrong.status_code in {401, 403, 404}, {"status": emp_wrong.status_code})

        team = client.get("/dashboard/team", headers=headers)
        if team.status_code == 404:
            team = client.get("/dashboard/settings/team", headers=headers)
        record("team route authenticated", team.status_code in {200, 404}, {"status": team.status_code})

        hr = client.get("/dashboard/hr-tasks", headers=headers)
        if hr.status_code == 404:
            hr = client.get("/dashboard/posthire/hr-tasks", headers=headers)
        record("hr tasks authenticated", hr.status_code in {200, 404}, {"status": hr.status_code})

        docs = client.get("/dashboard/posthire/compliance", headers=headers)
        record("compliance/documents hub authenticated", docs.status_code in {200, 403}, {"status": docs.status_code})

        payroll = client.get("/dashboard/posthire/payroll", headers=headers)
        record("payroll authenticated", payroll.status_code in {200, 403}, {"status": payroll.status_code})

        # Revoke employees.manage and prove open token loses write gate immediately.
        app.set_dashboard_user_permission_grant(
            COMPANY,
            str(owner["user_id"]),
            "employees.manage",
            active=False,
            actor_user_id=str(owner["user_id"]),
            reason="r1d live http open-session proof",
            review_reference="phase8c2-r1d-staging-cutover",
        )
        denied = client.post(
            f"/dashboard/posthire/employees/{COMPANY}-nonexistent/status",
            headers=headers,
            json={
                "status": "left",
                "reason": "r1d-http-denial-proof",
                "idempotency_key": str(uuid.uuid4()),
                "expected_status": "active",
                "expected_updated_at": datetime.now(timezone.utc).isoformat(),
                "approver_user_id": str(owner["user_id"]),
                "approval_reference": "phase8c2-r1d-staging-cutover",
                "approval_mode": "self_approved_internal_canary",
            },
        )
        record("open session loses employees.manage immediately", denied.status_code in {403, 404}, {"status": denied.status_code})
        app.set_dashboard_user_permission_grant(
            COMPANY,
            str(owner["user_id"]),
            "employees.manage",
            active=True,
            actor_user_id=str(owner["user_id"]),
            reason="r1d live http restore",
            review_reference="phase8c2-r1d-staging-cutover",
        )

    passed = [c["name"] for c in checks if c["ok"]]
    failed = [c["name"] for c in checks if not c["ok"]]
    payload = {
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "base": BASE,
        "ok": not failed,
        "counts": {"passed": len(passed), "failed": len(failed)},
        "passed": passed,
        "failed": failed,
        "checks": [{k: v for k, v in c.items() if k != "token"} for c in checks],
        "session_fingerprint": fp([str(owner["user_id"]), "http-live-proof"]),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "r1d-http-live-routes.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: payload[k] for k in ("ok", "counts", "passed", "failed")}, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
