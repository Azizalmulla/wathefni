#!/usr/bin/env python3
"""Staging-only Setup Console V2 enablement dry-run. Never prints secrets."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8011"
PHONE = "96599338566"
COMPANY = "V2STAGEDRY01"


def load_operator_token() -> str:
    raw = Path("/root/.openclaw/secrets/wathefni-setup-operator.env").read_text()
    match = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", raw)
    if not match:
        raise SystemExit("operator credentials missing")
    value = match.group(1).strip()
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        value = value[1:-1]
    creds = json.loads(value)
    if PHONE not in creds:
        raise SystemExit("operator phone missing from credentials")
    return str(creds[PHONE])


def load_dashboard_token() -> str | None:
    candidates = [
        Path("/root/.openclaw/secrets/wathefni-dashboard.env"),
        Path("/etc/systemd/system/wathefni-orchestrator.service.d/dashboard-auth.conf"),
        Path("/etc/systemd/system/wathefni-orchestrator.service.d/runtime-env.conf"),
        Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/dashboard-auth.conf"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", path.read_text())
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return None


def record(results: list, label: str, ok: bool, detail: str = "") -> None:
    results.append((label, bool(ok), detail))
    suffix = f" — {detail}" if detail else ""
    print(("PASS" if ok else "FAIL"), f"{label}{suffix}")


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None, expect_json: bool = True):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw_body = resp.read()
            content_type = resp.headers.get("content-type", "")
            if expect_json and "json" in content_type:
                payload = json.loads(raw_body.decode())
            else:
                payload = raw_body.decode("utf-8", "replace")
            return resp.status, payload, content_type
    except urllib.error.HTTPError as exc:
        raw_body = exc.read()
        try:
            payload = json.loads(raw_body.decode())
        except Exception:
            payload = raw_body.decode("utf-8", "replace")
        return exc.code, payload, exc.headers.get("content-type", "")


def main() -> int:
    op_token = load_operator_token()
    dash_token = load_dashboard_token()
    op_headers = {"Authorization": f"Bearer {op_token}", "X-HR-Phone": PHONE}
    results: list[tuple[str, bool, str]] = []

    status, body, content_type = req("GET", "/setup-console", expect_json=False)
    is_v2 = status == 200 and (
        "setup-console-root" in body
        or "setupConsole" in body
        or "/assets/setupConsole-" in body
    )
    record(results, "1. /setup-console serves React V2", is_v2, f"status={status} ct={content_type} len={len(body)}")
    print("V2_HTML_FINGERPRINT:")
    for line in body.splitlines():
        if "setupConsole" in line or "setup-console-root" in line or ('id="root"' in line) or ("id='root'" in line):
            print(" ", line.strip()[:180])

    status, payload, _ = req("GET", "/dashboard/superadmin/setup/companies?q=&limit=5&offset=0", headers=op_headers)
    record(
        results,
        "2. Authorized operator can connect",
        status == 200 and isinstance(payload, dict) and "companies" in payload,
        f"status={status}",
    )

    if dash_token:
        status, _, _ = req(
            "GET",
            "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
            headers={"Authorization": f"Bearer {dash_token}", "X-HR-Phone": PHONE},
        )
        record(results, "3. Shared dashboard token returns 401", status == 401, f"status={status}")
    else:
        status, _, _ = req(
            "GET",
            "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
            headers={"Authorization": "Bearer not-an-operator-token", "X-HR-Phone": PHONE},
        )
        record(
            results,
            "3. Shared dashboard token returns 401",
            status == 401,
            f"dashboard token unavailable locally; generic wrong token status={status}",
        )

    wrong_phone, _, _ = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": f"Bearer {op_token}", "X-HR-Phone": "96500000000"},
    )
    wrong_token, _, _ = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": "Bearer wrong-operator-token", "X-HR-Phone": PHONE},
    )
    record(
        results,
        "4. Wrong phone/token still return 401",
        wrong_phone == 401 and wrong_token == 401,
        f"wrong_phone={wrong_phone} wrong_token={wrong_token}",
    )

    status, _, _ = req("GET", "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0")
    record(results, "5. Unauthenticated / normal client blocked", status in (401, 403, 404), f"status={status}")

    status, payload, _ = req("GET", "/dashboard/superadmin/setup/companies?q=&limit=20&offset=0", headers=op_headers)
    record(
        results,
        "6. React V2 can list companies (API)",
        status == 200 and isinstance(payload.get("companies"), list),
        f"status={status} count={payload.get('total_count') if isinstance(payload, dict) else None}",
    )

    status, created, _ = req(
        "POST",
        "/dashboard/superadmin/setup/companies",
        headers=op_headers,
        body={
            "company_code": COMPANY,
            "name": "V2 Staging Dry Run",
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
        },
    )
    record(
        results,
        "8. Create staging throwaway company",
        status in (200, 201) and isinstance(created, dict),
        f"status={status} created={created.get('created') if isinstance(created, dict) else None}",
    )

    status, profile, _ = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/profile",
        headers=op_headers,
        body={
            "name": "V2 Staging Dry Run Co",
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
        },
    )
    record(
        results,
        "9. Save profile",
        status == 200 and isinstance(profile, dict) and profile.get("ok") is True,
        f"status={status} name={(profile.get('profile') or {}).get('name') if isinstance(profile, dict) else None}",
    )

    status, detail, _ = req("GET", f"/dashboard/superadmin/setup/companies/{COMPANY}", headers=op_headers)
    bundles = detail.get("module_bundles") or [] if isinstance(detail, dict) else []
    available = detail.get("available_modules") or [] if isinstance(detail, dict) else []
    assessments = next((item for item in available if item.get("key") == "assessments"), {})
    payroll = next((item for item in available if item.get("key") == "payroll"), {})
    record(
        results,
        "7. Module guidance payload present",
        status == 200
        and len(bundles) >= 6
        and assessments.get("depends_on") == ["pre_hiring"]
        and set(payroll.get("recommended_with") or []) == {"attendance", "leave"},
        f"bundles={len(bundles)} assess_deps={assessments.get('depends_on')} payroll_rec={payroll.get('recommended_with')}",
    )

    workforce = ["shifts", "attendance", "leave", "payroll"]
    status_apply, applied, _ = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers,
        body={"modules": workforce},
    )
    status_remove, removed, _ = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers,
        body={"modules": ["attendance", "leave", "payroll"]},
    )
    record(
        results,
        "10. Apply bundle modules + remove soft rec without blocking",
        status_apply == 200
        and set(applied.get("modules") or []) == set(workforce)
        and status_remove == 200
        and "shifts" not in (removed.get("modules") or [])
        and {"attendance", "leave", "payroll"}.issubset(set(removed.get("modules") or [])),
        f"apply={status_apply} remove={status_remove} modules={removed.get('modules') if isinstance(removed, dict) else None}",
    )

    status, with_deps, _ = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers,
        body={
            "modules": [
                "pre_hiring",
                "assessments",
                "video_interviews",
                "attendance",
                "leave",
                "payroll",
                "employee_app",
            ]
        },
    )
    record(
        results,
        "11. Assessments/Video with Pre-Hiring save OK",
        status == 200
        and {"pre_hiring", "assessments", "video_interviews"}.issubset(set((with_deps or {}).get("modules") or [])),
        f"status={status} modules={(with_deps or {}).get('modules')}",
    )

    status, err, _ = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers,
        body={"modules": ["assessments"]},
    )
    detail_err = err.get("detail") if isinstance(err, dict) else None
    err_code = detail_err.get("error") if isinstance(detail_err, dict) else None
    record(
        results,
        "12. Direct API save without Pre-Hiring returns 422",
        status == 422 and err_code == "missing_module_dependency",
        f"status={status} error={err_code}",
    )

    req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers,
        body={
            "modules": [
                "pre_hiring",
                "assessments",
                "video_interviews",
                "attendance",
                "leave",
                "payroll",
                "employee_app",
            ]
        },
    )
    status, detail2, _ = req("GET", f"/dashboard/superadmin/setup/companies/{COMPANY}", headers=op_headers)
    employee = next(
        (item for item in (detail2.get("available_modules") or []) if item.get("key") == "employee_app"),
        {},
    ) if isinstance(detail2, dict) else {}
    surfaces = ((detail2.get("module_guidance") or {}).get("app_surfaces") or []) if isinstance(detail2, dict) else []
    record(
        results,
        "13. employee_app configured awaiting activation not live",
        employee.get("configured") is True
        and employee.get("platform_available") is False
        and employee.get("effective") is False,
        f"configured={employee.get('configured')} platform={employee.get('platform_available')} "
        f"effective={employee.get('effective')} surfaces={len(surfaces)}",
    )

    policy = detail2.get("channel_policy") or {} if isinstance(detail2, dict) else {}
    account = detail2.get("channel_account") if isinstance(detail2, dict) else None
    channel_flag = policy.get("company_channel_accounts_enabled")
    put_status, _, _ = req(
        "PUT",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/channel-account",
        headers=op_headers,
        body={
            "provider": "octopus",
            "provider_account_id": "SHOULD-NOT-WORK",
            "sender_phone": "96550000000",
            "audiences": ["candidate"],
            "status": "active",
            "verification_reference": "x",
        },
    )
    record(
        results,
        "14. Channel accounts remain inactive",
        channel_flag in (False, None) and put_status in (404, 403, 422) and not account,
        f"flag={channel_flag} put_status={put_status} account={account}",
    )

    req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/settings",
        headers=op_headers,
        body={"channel_policy_reviewed": True},
    )

    status, owner, _ = req(
        "POST",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/owner",
        headers=op_headers,
        body={
            "name": "Staging Dry Owner",
            "email": "v2dryowner@example.test",
            "phone": "96551112233",
        },
    )
    invite_token = owner.get("invite_token") if isinstance(owner, dict) else None
    invite_link = (owner.get("invite_link") or owner.get("invite_url")) if isinstance(owner, dict) else None
    sent_claim = any(key in (owner or {}) for key in ("sent", "email_sent", "delivered", "whatsapp_sent")) if isinstance(owner, dict) else False
    record(
        results,
        "15. Owner invite copy-only",
        status == 200 and bool(invite_token or invite_link) and not sent_claim,
        f"status={status} has_token={bool(invite_token)} has_link={bool(invite_link)} sent_claim={sent_claim}",
    )

    status, detail3, _ = req("GET", f"/dashboard/superadmin/setup/companies/{COMPANY}", headers=op_headers)
    readiness = detail3.get("readiness") or {} if isinstance(detail3, dict) else {}
    ready = readiness.get("ready")
    steps = [{"key": step.get("key"), "done": step.get("done")} for step in (readiness.get("steps") or [])]
    record(results, "16. Readiness becomes ready", ready is True, f"ready={ready} steps={steps}")

    status, body2, _ = req("GET", "/setup-console", expect_json=False)
    record(
        results,
        "V2 page still served after dry-run",
        status == 200 and ("setupConsole" in body2 or "setup-console-root" in body2),
        f"status={status}",
    )

    print("\nSUMMARY")
    failed = [item for item in results if not item[1]]
    print(f"{sum(1 for item in results if item[1])} passed, {len(failed)} failed")
    print(f"DRY_RUN_COMPANY={COMPANY}")
    print(f"INVITE_TOKEN_PRESENT={bool(invite_token)}")
    print(f"INVITE_LINK_PRESENT={bool(invite_link)}")
    print(f"DASHBOARD_TOKEN_FOUND={bool(dash_token)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
