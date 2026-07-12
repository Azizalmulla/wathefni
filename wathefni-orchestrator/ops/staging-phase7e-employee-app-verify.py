#!/usr/bin/env python3
"""Phase 7E E2 verifier-first staging matrix.

Writes only isolated P7ESTG01/P7ESTG02 fixtures to the staging database.
Uses synthetic employees/files and mocked activation delivery. It never enables
production flags, sends live messages, or patches application behavior.

Application failures are evidence: the verifier records the endpoint, expected
and observed behavior, and smallest durable remediation scope, then continues
only with independent test paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from psycopg2.extras import Json

COMPANY = "P7ESTG01"
OTHER_COMPANY = "P7ESTG02"
PROTECTED_COMPANY = "WATHEFNI"
MARKER = "phase7e_e2_verifier"
POSTGRES_ENV = Path(os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"))
PRODUCTION_POSTGRES_ENV = Path(os.environ.get("WATHEFNI_PRODUCTION_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env"))
REPORT_DIR = Path(os.environ.get("WATHEFNI_PHASE7E_REPORT_DIR", "/opt/wathefni/orchestrator/ops/reports"))
STAGING_ORCH = Path(os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator"))

EMP_A = "p7e-app-a"
EMP_B = "p7e-app-b"
EMP_D = "p7e-app-d"
EMP_E = "p7e-app-e"
EMP_F = "p7e-app-f"
EMP_CROSS = "p7e-app-cross"
PHONE_A = "96555557801"
PHONE_B = "96555557802"
PHONE_D = "96555557804"
PHONE_E = "96555557805"
PHONE_F = "96555557806"
PHONE_CROSS = "96555557901"
ITEMS = ("civil_id", "personal_photo", "employment_contract", "bank_details")
LABELS = {
    "civil_id": "Civil ID",
    "personal_photo": "Personal Photo",
    "employment_contract": "Employment Contract",
    "bank_details": "Bank Details",
}
PROTECTED_FLAGS = (
    "WATHEFNI_EMPLOYEE_APP",
    "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS",
    "WATHEFNI_ONBOARDING_SEED",
)


def load_env(path: Path, *, overwrite: bool = False) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
        if overwrite or key.strip() not in os.environ:
            os.environ[key.strip()] = values[key.strip()]
    return values


load_env(POSTGRES_ENV)
if STAGING_ORCH.is_dir():
    sys.path.insert(0, str(STAGING_ORCH))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): ("[redacted]" if str(k).lower() in {"code", "token", "refresh_token", "code_hash", "token_hash", "refresh_hash"} else json_safe(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def compact(value: Any, limit: int = 700) -> str:
    text = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


class Evidence:
    def __init__(self) -> None:
        self.cases: list[dict[str, Any]] = []
        self.blockers: list[dict[str, Any]] = []
        self.rollback: list[dict[str, Any]] = []
        self.meta: dict[str, Any] = {
            "phase": "7E-E2",
            "company": COMPANY,
            "other_company": OTHER_COMPANY,
            "synthetic_only": True,
            "mocked_outbound_only": True,
            "application_code_patched": False,
        }

    def record(
        self,
        case_id: str,
        label: str,
        passed: bool,
        *,
        endpoint: str,
        expected: Any,
        observed: Any,
        category: str,
        remediation: str | None = None,
        rollback: bool = False,
    ) -> bool:
        item = {
            "case_id": case_id,
            "label": label,
            "status": "PASS" if passed else "FAIL",
            "category": category,
            "endpoint": endpoint,
            "expected": json_safe(expected),
            "observed": json_safe(observed),
        }
        self.cases.append(item)
        print(f"{item['status']} {case_id} {label} — {compact(observed)}")
        if not passed:
            blocker = {
                **item,
                "smallest_durable_remediation_scope": remediation or "Investigate the endpoint gate without changing unrelated behavior.",
            }
            self.blockers.append(blocker)
        if rollback:
            self.rollback.append(item)
        return passed

    def write(self, extra: dict[str, Any]) -> tuple[Path, Path]:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        passed = sum(1 for item in self.cases if item["status"] == "PASS")
        failed = len(self.cases) - passed
        payload = {
            "meta": self.meta,
            "summary": {
                "total": len(self.cases),
                "passed": passed,
                "failed": failed,
                "blockers": len(self.blockers),
                "recommendation": "staging-green" if failed == 0 else "not-staging-green",
            },
            "cases": self.cases,
            "blockers": self.blockers,
            "rollback_evidence": self.rollback,
            **json_safe(extra),
        }
        json_path = REPORT_DIR / "phase7e-e2-verifier-report.json"
        md_path = REPORT_DIR / "phase7e-e2-verifier-report.md"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")

        lines = [
            "# Phase 7E E2 staging verifier report",
            "",
            f"- Result: **{passed}/{len(self.cases)} passed; {failed} failed**",
            f"- Recommendation: **{payload['summary']['recommendation']}**",
            f"- Fixture: `{COMPANY}` (+ `{OTHER_COMPANY}` for isolation)",
            "- Outbound: mocked only; synthetic documents only",
            "- Application remediation: none performed",
            "",
            "## Exact case evidence",
            "",
        ]
        for item in self.cases:
            lines.extend(
                [
                    f"### {item['status']} — {item['case_id']} {item['label']}",
                    f"- Endpoint: `{item['endpoint']}`",
                    f"- Expected: `{compact(item['expected'])}`",
                    f"- Observed: `{compact(item['observed'])}`",
                    "",
                ]
            )
        lines.extend(["## Blockers", ""])
        if self.blockers:
            for blocker in self.blockers:
                lines.extend(
                    [
                        f"### {blocker['case_id']} — {blocker['label']}",
                        f"- Endpoint: `{blocker['endpoint']}`",
                        f"- Observed: `{compact(blocker['observed'])}`",
                        f"- Expected: `{compact(blocker['expected'])}`",
                        f"- Smallest durable remediation: {blocker['smallest_durable_remediation_scope']}",
                        "",
                    ]
                )
        else:
            lines.extend(["No blockers.", ""])
        lines.extend(
            [
                "## Rollback evidence",
                "",
                *[
                    f"- **{item['status']}** {item['case_id']} — {item['label']}: `{compact(item['observed'])}`"
                    for item in self.rollback
                ],
                "",
                "## Production protection",
                "",
                f"- Flags before: `{compact(extra.get('production_flags_before'))}`",
                f"- Flags after: `{compact(extra.get('production_flags_after'))}`",
                f"- Production snapshot unchanged: `{extra.get('production_snapshot_unchanged')}`",
                f"- Staging protected-company snapshot unchanged: `{extra.get('staging_protected_snapshot_unchanged')}`",
                "",
            ]
        )
        md_path.write_text("\n".join(lines) + "\n")
        return json_path, md_path


E = Evidence()


def invoke(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        # Keep raw values in memory so later steps can use opaque tokens/codes.
        # Evidence.record/json_safe redacts them before printing or persistence.
        return {"returned": True, "status_code": 200, "body": fn()}
    except app.HTTPException as exc:
        return {"returned": False, "status_code": exc.status_code, "body": exc.detail}
    except Exception as exc:
        return {"returned": False, "status_code": 500, "exception": type(exc).__name__, "body": str(exc)[:500]}


def denied(result: dict[str, Any], codes: set[int] | tuple[int, ...]) -> bool:
    return not result.get("returned") and int(result.get("status_code") or 0) in set(codes)


def exec_sql(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()] if cur.description else []
        conn.commit()
    return rows


def scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
    rows = exec_sql(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))


def table_columns(table: str) -> set[str]:
    return {
        str(row["column_name"])
        for row in exec_sql("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    }


def set_flag(name: str, on: bool) -> None:
    os.environ[name] = "on" if on else "off"


def set_company_status(company: str, status: str) -> None:
    exec_sql(
        "UPDATE companies SET status=%s, updated_at=now(), "
        "disabled_at=CASE WHEN %s='disabled' THEN now() ELSE NULL END, "
        "archived_at=CASE WHEN %s='archived' THEN now() ELSE NULL END "
        "WHERE company_code=%s",
        (status, status, status, company),
    )


def set_module(company: str, module: str, enabled: bool) -> None:
    exec_sql(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source=EXCLUDED.source, updated_at=now()
        """,
        (company, module, enabled, MARKER),
    )


def insert_employee(company: str, key: str, phone: str, name: str) -> None:
    columns = table_columns("employees")
    desired: dict[str, Any] = {
        "company_code": company,
        "employee_key": key,
        "phone": phone,
        "name": name,
        "email": f"{key}@synthetic.invalid",
        "onboarding_status": "in_progress",
        "employment_status": "active",
        "raw_json": Json({"marker": MARKER, "synthetic": True}),
        "profile": Json({"marker": MARKER, "synthetic": True}),
    }
    cols = [col for col in desired if col in columns]
    placeholders = ",".join(["%s"] * len(cols))
    exec_sql(
        f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})",
        tuple(desired[col] for col in cols),
    )


def insert_item(company: str, employee_key: str, item_id: str, *, required: bool = True) -> None:
    columns = table_columns("onboarding_items")
    desired: dict[str, Any] = {
        "company_code": company,
        "employee_key": employee_key,
        "item_id": item_id,
        "label": LABELS.get(item_id, item_id.replace("_", " ").title()),
        "item_type": "document",
        "document_type": item_id,
        "required": required,
        "status": "pending",
        "raw_json": Json({"marker": MARKER, "synthetic": True}),
    }
    cols = [col for col in desired if col in columns]
    exec_sql(
        f"INSERT INTO onboarding_items ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})",
        tuple(desired[col] for col in cols),
    )


def insert_invite(
    company: str,
    employee_key: str,
    phone: str,
    code: str,
    *,
    expires_delta: timedelta = timedelta(hours=24),
    status: str = "pending",
) -> str:
    rows = exec_sql(
        """
        INSERT INTO employee_app_invites
          (company_code, employee_key, phone, code_hash, status, expires_at, last_sent_at, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,now(),%s)
        RETURNING invite_id
        """,
        (
            company,
            employee_key,
            phone,
            app._app_code_hash(company, phone, code),
            status,
            app.now_utc() + expires_delta,
            Json({"marker": MARKER, "synthetic": True}),
        ),
    )
    return str(rows[0]["invite_id"])


def app_context(token: str) -> dict[str, Any]:
    return app.employee_app_context(authorization=f"Bearer {token}")


def hr_context(company: str = COMPANY) -> dict[str, Any]:
    return {
        "company_code": company,
        "actor_user_id": f"{MARKER}:owner",
        "actor_role": "owner",
        "actor_phone": "96555557000",
        "hr_phone": "",
        "permissions": [],
        "hr_user": {
            "status": "active",
            "role": "owner",
            "company_code": company,
            "phone": "96555557000",
            "name": "Synthetic E2 Owner",
        },
    }


def cleanup() -> None:
    keys = [EMP_A, EMP_B, EMP_D, EMP_E, EMP_F, EMP_CROSS]
    companies = [COMPANY, OTHER_COMPANY]
    statements = [
        ("DELETE FROM employee_notification_reads WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_push_tokens WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_sessions WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_app_invites WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM whatsapp_suppressions WHERE phone = ANY(%s)", ([PHONE_A, PHONE_B, PHONE_D, PHONE_E, PHONE_F, PHONE_CROSS],)),
        ("DELETE FROM outbound_delivery_events WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM hr_tasks WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_messages WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM action_results WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM leave_events WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM leave_requests WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_documents WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM compliance_documents WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM file_registry WHERE company_code = ANY(%s) OR subject_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM onboarding_items WHERE company_code = ANY(%s) OR employee_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM company_settings WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employees WHERE company_code = ANY(%s) OR employee_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM companies WHERE company_code = ANY(%s)", (companies,)),
    ]
    for sql, params in statements:
        try:
            exec_sql(sql, params)
        except Exception:
            # Schema varies slightly across deploys; each delete is isolated.
            continue
    workspace = Path(os.environ.get("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace"))
    for company in companies:
        shutil.rmtree(workspace / "data" / "companies" / company, ignore_errors=True)


def setup() -> None:
    cleanup()
    for company, name in ((COMPANY, "Phase 7E E2 Synthetic Tenant"), (OTHER_COMPANY, "Phase 7E E2 Isolation Tenant")):
        exec_sql(
            """
            INSERT INTO companies
              (company_code, name, country, status, metadata, raw_json, created_at, updated_at)
            VALUES (%s,%s,'KW','active',%s,%s,now(),now())
            """,
            (company, name, Json({"marker": MARKER, "synthetic": True}), Json({"marker": MARKER, "synthetic": True})),
        )
        for module in ("onboarding", "leave"):
            set_module(company, module, True)
    insert_employee(COMPANY, EMP_A, PHONE_A, "Synthetic Employee A")
    insert_employee(COMPANY, EMP_B, PHONE_B, "Synthetic Employee B")
    insert_employee(COMPANY, EMP_D, PHONE_D, "Synthetic Employee D")
    insert_employee(COMPANY, EMP_E, PHONE_E, "Synthetic Employee E")
    insert_employee(COMPANY, EMP_F, PHONE_F, "Synthetic Employee F")
    insert_employee(OTHER_COMPANY, EMP_CROSS, PHONE_CROSS, "Synthetic Cross Tenant Employee")
    insert_item(COMPANY, EMP_B, "other_employee_only")
    insert_item(OTHER_COMPANY, EMP_CROSS, "cross_tenant_only")


def systemd_flags(unit: str) -> dict[str, str]:
    try:
        raw = subprocess.check_output(
            ["systemctl", "show", unit, "-p", "Environment", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"_error": str(exc)}
    values: dict[str, str] = {}
    for match in re.finditer(r"(WATHEFNI_[A-Z0-9_]+)=([^\s\"]+)", raw):
        values[match.group(1)] = match.group(2)
    return {flag: values.get(flag, "unset") for flag in PROTECTED_FLAGS}


def flag_is_off(value: str) -> bool:
    return str(value or "unset").strip().lower() in {"", "unset", "0", "off", "false", "no"}


def database_snapshot(dsn: str, company: str) -> dict[str, Any]:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code, name, status, updated_at FROM companies WHERE company_code=%s", (company,))
            company_row = dict(cur.fetchone() or {})
            cur.execute("SELECT module_key, enabled FROM company_modules WHERE company_code=%s ORDER BY module_key", (company,))
            modules = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT count(*) AS n FROM employees WHERE company_code=%s", (company,))
            employees = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employee_app_invites WHERE company_code=%s", (company,))
            invites = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employee_sessions WHERE company_code=%s", (company,))
            sessions = int((cur.fetchone() or {}).get("n") or 0)
        payload = json_safe(
            {
                "company": company_row,
                "modules": modules,
                "employees": employees,
                "employee_app_invites": invites,
                "employee_sessions": sessions,
            }
        )
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return {"sha256": digest, "payload": payload}
    finally:
        conn.close()


def production_snapshot() -> dict[str, Any]:
    values = load_env(PRODUCTION_POSTGRES_ENV)
    dsn = values.get("WATHEFNI_DATABASE_URL", "")
    if not dsn:
        return {"error": "production_dsn_unavailable"}
    if dsn == os.environ.get("WATHEFNI_DATABASE_URL"):
        raise SystemExit("refusing: production and staging DSNs are identical")
    return database_snapshot(dsn, PROTECTED_COMPANY)


def staging_protected_snapshot() -> dict[str, Any]:
    return database_snapshot(os.environ["WATHEFNI_DATABASE_URL"], PROTECTED_COMPANY)


def create_mocked_invite(status: str, channel: str | None, *, employee_key: str = EMP_A) -> tuple[dict[str, Any], dict[str, Any]]:
    employee = app.find_employee_by_key(employee_key, company_code=COMPANY)
    called: list[dict[str, Any]] = []
    original = app.deliver_app_activation_code

    def mocked(company_code: str, emp: dict[str, Any], code: str) -> dict[str, Any]:
        called.append({"company_code": company_code, "employee_key": emp.get("employee_key")})
        return {
            "ok": status.startswith("delivered_") or status == "sent_email_fallback",
            "delivery_status": status,
            "channel": channel,
        }

    app.deliver_app_activation_code = mocked
    try:
        response = app.dashboard_posthire_app_invite(employee_key, hr_context())
    finally:
        app.deliver_app_activation_code = original
    return response, {"mock_calls": called}


def synthetic_upload(filename: str, content_type: str, data: bytes, item_id: str, context: dict[str, Any]) -> dict[str, Any]:
    from starlette.datastructures import Headers, UploadFile

    upload = UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )
    return asyncio.run(app.app_onboarding_document_upload(file=upload, item_id=item_id, context=context))


def insert_owned_file(company: str, employee_key: str, item_id: str) -> str:
    file_id = str(uuid.uuid4())
    exec_sql(
        """
        INSERT INTO file_registry
          (file_id, company_code, subject_type, subject_key, file_kind, document_type,
           original_filename, mime_type, storage_provider, storage_status, storage_url, metadata, raw_json)
        VALUES (%s,%s,'employee',%s,'onboarding_document',%s,%s,'application/pdf',
                'local','stored','local://synthetic-missing',%s,%s)
        """,
        (
            file_id,
            company,
            employee_key,
            item_id,
            f"{item_id}.pdf",
            Json({"item_id": item_id, "label": LABELS.get(item_id, item_id), "marker": MARKER}),
            Json({"marker": MARKER, "synthetic": True}),
        ),
    )
    return file_id


def run_matrix() -> dict[str, Any]:
    # C01 — global flag OFF.
    set_flag("WATHEFNI_EMPLOYEE_APP", False)
    set_flag("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", False)
    set_flag("WATHEFNI_ONBOARDING_SEED", False)
    set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
    result = invoke(lambda: app.employee_app_context(authorization="Bearer invalid"))
    E.record(
        "C01a",
        "global flag OFF blocks authenticated app context",
        denied(result, {503}),
        endpoint="GET /app/me (employee_app_context)",
        expected={"status_code": 503, "error": "employee_app_disabled"},
        observed=result,
        category="authorization",
        rollback=True,
    )
    result = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code="000000")))
    E.record(
        "C01b",
        "global flag OFF blocks activation",
        denied(result, {503}),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 503},
        observed=result,
        category="invite",
        rollback=True,
    )

    # C02 — flag ON only, module remains OFF.
    set_flag("WATHEFNI_EMPLOYEE_APP", True)
    pre_session = app.create_employee_session(COMPANY, EMP_A, PHONE_A)
    result = invoke(lambda: app_context(pre_session["token"]))
    E.record(
        "C02a",
        "module OFF blocks an existing session",
        denied(result, {403}),
        endpoint="GET /app/me (employee_app_context)",
        expected={"status_code": 403, "error": "employee_app_not_enabled_for_company"},
        observed=result,
        category="authorization",
        rollback=True,
    )
    result = invoke(lambda: app.dashboard_posthire_app_invite(EMP_A, hr_context()))
    E.record(
        "C02b",
        "module OFF blocks HR invite",
        denied(result, {403}),
        endpoint="POST /dashboard/posthire/employees/{employee_key}/app-invite",
        expected={"status_code": 403},
        observed=result,
        category="invite",
    )
    app.revoke_employee_session_token(pre_session["token"])

    for module in ("employee_app",):
        set_module(COMPANY, module, True)
        set_module(OTHER_COMPANY, module, True)

    # C03 — backend-owned delivery outcomes, all mocked.
    delivery_contract = [
        ("delivered_whatsapp", "whatsapp_session", "delivered"),
        ("failed", None, "failed"),
        ("suppressed", None, "suppressed"),
        ("sent_email_fallback", "email", "fallback"),
    ]
    for index, (status, channel, semantic) in enumerate(delivery_contract, start=1):
        before = int(scalar("SELECT count(*) FROM employee_app_invites WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_A)) or 0)
        response, mock = create_mocked_invite(status, channel)
        after = int(scalar("SELECT count(*) FROM employee_app_invites WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_A)) or 0)
        observed = {
            "created": after == before + 1,
            "attempted": len(mock["mock_calls"]) == 1,
            "server_status": (response.get("delivery") or {}).get("status"),
            "server_channel": (response.get("delivery") or {}).get("channel"),
            "semantic": semantic,
        }
        E.record(
            f"C03{chr(96 + index)}",
            f"mocked activation delivery exposes backend-owned {semantic} outcome",
            observed["created"] and observed["attempted"] and observed["server_status"] == status and observed["server_channel"] == channel,
            endpoint="POST /dashboard/posthire/employees/{employee_key}/app-invite",
            expected={"created": True, "attempted": True, "status": status, "channel": channel},
            observed=observed,
            category="delivery",
        )

    # Exercise the real outbound ladder with only the provider primitives stubbed.
    # This proves durable message status, attempt_log, fallback trail, HR task, and
    # terminal outbound event without any network traffic.
    delivery_originals = {
        "session": app.send_octopus_whatsapp,
        "template": app.octopus_send_template,
        "email": app.send_outbound_email,
        "email_enabled": app.outbound_email_fallback_enabled,
    }
    delivery_stubs: dict[str, Any] = {
        "session": {"ok": False, "error": "conversation_closed"},
        "template": {"ok": False, "error": "template_unmapped"},
        "email": {"ok": True, "channel": "email"},
    }
    delivery_calls = {"session": 0, "template": 0, "email": 0}

    def session_stub(**_kwargs: Any) -> dict[str, Any]:
        delivery_calls["session"] += 1
        return dict(delivery_stubs["session"])

    def template_stub(**_kwargs: Any) -> dict[str, Any]:
        delivery_calls["template"] += 1
        return dict(delivery_stubs["template"])

    def email_stub(**_kwargs: Any) -> dict[str, Any]:
        delivery_calls["email"] += 1
        return dict(delivery_stubs["email"])

    app.send_octopus_whatsapp = session_stub
    app.octopus_send_template = template_stub
    app.send_outbound_email = email_stub
    app.outbound_email_fallback_enabled = lambda: True
    employee_a = app.find_employee_by_key(EMP_A, company_code=COMPANY)
    try:
        delivery_stubs["session"] = {"ok": True, "status": 200}
        delivery_calls.update(session=0, template=0, email=0)
        ladder_delivered = app.deliver_app_activation_code(COMPANY, employee_a, "830001")
        delivered_row = exec_sql(
            "SELECT message_id, status, channel_used, attempts, attempt_log FROM employee_messages "
            "WHERE company_code=%s AND employee_key=%s AND flow='app_activation' ORDER BY created_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        delivered_events = exec_sql(
            "SELECT status, channel, payload FROM outbound_delivery_events WHERE company_code=%s "
            "AND subject_key=%s AND channel='outbound_layer' ORDER BY created_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        E.record(
            "C03e",
            "real ladder persists created/attempted/delivered state",
            ladder_delivered.get("delivery_status") == "delivered_whatsapp"
            and bool(delivered_row)
            and delivered_row[0].get("status") == "delivered_whatsapp"
            and int(delivered_row[0].get("attempts") or 0) == 1
            and len(delivered_row[0].get("attempt_log") or []) == 1
            and delivery_calls["session"] == 1
            and bool(delivered_events),
            endpoint="deliver_app_activation_code → outbound_delivery",
            expected={"created_row": True, "attempts": 1, "status": "delivered_whatsapp", "terminal_event": True},
            observed={
                "result": {key: ladder_delivered.get(key) for key in ("ok", "delivery_status", "channel", "hr_task_id")},
                "message": delivered_row,
                "event": delivered_events,
                "provider_calls": dict(delivery_calls),
            },
            category="delivery",
        )

        delivery_stubs["session"] = {"ok": False, "error": "conversation_closed"}
        delivery_stubs["template"] = {"ok": False, "error": "template_unmapped"}
        delivery_stubs["email"] = {"ok": True, "channel": "email"}
        delivery_calls.update(session=0, template=0, email=0)
        ladder_fallback = app.deliver_app_activation_code(COMPANY, employee_a, "830002")
        fallback_row = exec_sql(
            "SELECT status, channel_used, attempts, attempt_log FROM employee_messages "
            "WHERE company_code=%s AND employee_key=%s AND flow='app_activation' ORDER BY created_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        fallback_log = (fallback_row[0].get("attempt_log") or []) if fallback_row else []
        fallback_reasons = (fallback_log[-1].get("reasons") or []) if fallback_log else []
        E.record(
            "C03f",
            "real ladder records fallback as later-rung success plus reason trail",
            ladder_fallback.get("delivery_status") == "sent_email_fallback"
            and ladder_fallback.get("channel") == "email"
            and bool(fallback_row)
            and fallback_row[0].get("status") == "sent_email_fallback"
            and fallback_row[0].get("channel_used") == "email"
            and any(str(reason).startswith("session:") for reason in fallback_reasons)
            and delivery_calls["session"] == 1
            and delivery_calls["email"] == 1,
            endpoint="deliver_app_activation_code → outbound_delivery",
            expected={"status": "sent_email_fallback", "channel": "email", "prior_rung_reason": True},
            observed={
                "result": {key: ladder_fallback.get(key) for key in ("ok", "delivery_status", "channel", "hr_task_id")},
                "message": fallback_row,
                "provider_calls": dict(delivery_calls),
            },
            category="delivery",
        )

        delivery_stubs["email"] = {"ok": False, "error": "synthetic_email_failure"}
        delivery_calls.update(session=0, template=0, email=0)
        ladder_failed = app.deliver_app_activation_code(COMPANY, employee_a, "830003")
        failed_row = exec_sql(
            "SELECT status, channel_used, attempts, attempt_log, hr_task_id FROM employee_messages "
            "WHERE company_code=%s AND employee_key=%s AND flow='app_activation' ORDER BY created_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        hr_task_id = failed_row[0].get("hr_task_id") if failed_row else None
        hr_task_count = int(
            scalar("SELECT count(*) FROM hr_tasks WHERE task_id=%s AND company_code=%s AND status='open'", (hr_task_id, COMPANY))
            or 0
        ) if hr_task_id else 0
        E.record(
            "C03g",
            "real ladder all-failed activation creates visible HR task",
            ladder_failed.get("delivery_status") == "needs_hr_action"
            and bool(failed_row)
            and failed_row[0].get("status") == "needs_hr_action"
            and bool(hr_task_id)
            and hr_task_count == 1,
            endpoint="deliver_app_activation_code → outbound_delivery",
            expected={"status": "needs_hr_action", "hr_task": "open"},
            observed={
                "result": {key: ladder_failed.get(key) for key in ("ok", "delivery_status", "channel", "hr_task_id")},
                "message": failed_row,
                "hr_task_count": hr_task_count,
            },
            category="delivery",
        )

        app.suppress_whatsapp(PHONE_A, scope="all", reason=MARKER, source=MARKER, context_company_code=COMPANY)
        delivery_calls.update(session=0, template=0, email=0)
        ladder_suppressed = app.deliver_app_activation_code(COMPANY, employee_a, "830004")
        suppressed_row = exec_sql(
            "SELECT status, channel_used, attempts, attempt_log, hr_task_id FROM employee_messages "
            "WHERE company_code=%s AND employee_key=%s AND flow='app_activation' ORDER BY created_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        E.record(
            "C03h",
            "real ladder persists suppressed without provider calls or HR task",
            ladder_suppressed.get("delivery_status") == "suppressed"
            and bool(suppressed_row)
            and suppressed_row[0].get("status") == "suppressed"
            and not suppressed_row[0].get("hr_task_id")
            and sum(delivery_calls.values()) == 0,
            endpoint="deliver_app_activation_code → outbound_delivery",
            expected={"status": "suppressed", "provider_calls": 0, "hr_task": None},
            observed={
                "result": {key: ladder_suppressed.get(key) for key in ("ok", "delivery_status", "channel", "hr_task_id")},
                "message": suppressed_row,
                "provider_calls": dict(delivery_calls),
            },
            category="delivery",
        )
        app.unsuppress_whatsapp(PHONE_A, by=MARKER)
    finally:
        app.send_octopus_whatsapp = delivery_originals["session"]
        app.octopus_send_template = delivery_originals["template"]
        app.send_outbound_email = delivery_originals["email"]
        app.outbound_email_fallback_enabled = delivery_originals["email_enabled"]

    # C04 — happy activation.
    invite_response, _ = create_mocked_invite("delivered_whatsapp", "whatsapp_session")
    activation = invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=PHONE_A, code=invite_response["code"])
        )
    )
    activation_ok = activation.get("returned") and (activation.get("body") or {}).get("employee", {}).get("employee_key") == EMP_A
    E.record(
        "C04a",
        "valid single-use invite activates the intended employee",
        bool(activation_ok),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 200, "employee_key": EMP_A, "session": True},
        observed=activation,
        category="invite",
    )
    token_a = activation["body"]["token"] if activation_ok else app.create_employee_session(COMPANY, EMP_A, PHONE_A)["token"]
    refresh_a = activation["body"].get("refresh_token") if activation_ok else None
    me = invoke(lambda: app.app_me(app_context(token_a)))
    E.record(
        "C04b",
        "authenticated identity is self-scoped",
        me.get("returned") and (me.get("body") or {}).get("employee_key") == EMP_A and (me.get("body") or {}).get("company_code") == COMPANY,
        endpoint="GET /app/me",
        expected={"employee_key": EMP_A, "company_code": COMPANY},
        observed=me,
        category="tenant_isolation",
    )

    # C05 — invite safety and abuse protection.
    employee_b = app.find_employee_by_key(EMP_B, company_code=COMPANY)
    _, old_code = app.create_employee_app_invite(COMPANY, employee_b)
    _, new_code = app.create_employee_app_invite(COMPANY, employee_b)
    result = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code=old_code)))
    E.record(
        "C05a",
        "superseded invite is rejected",
        denied(result, {401}),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 401},
        observed=result,
        category="invite",
    )
    # Fresh invite after old-code attempt so lockout count starts at zero.
    _, rate_code = app.create_employee_app_invite(COMPANY, employee_b)
    invalid_results = [
        invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code="111111")))
        for _ in range(app._EMPLOYEE_APP_MAX_CODE_ATTEMPTS)
    ]
    locked = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code=rate_code)))
    E.record(
        "C05b",
        "repeated invalid activation attempts trigger abuse protection",
        all(denied(item, {401}) for item in invalid_results) and denied(locked, {429}),
        endpoint="POST /app/auth/activate",
        expected={"first_invalid": 401, "after_limit": 429, "max_attempts": app._EMPLOYEE_APP_MAX_CODE_ATTEMPTS},
        observed={"invalid_statuses": [item["status_code"] for item in invalid_results], "locked": locked},
        category="abuse_protection",
    )
    _, reusable_code = app.create_employee_app_invite(COMPANY, employee_b)
    first_b = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code=reusable_code)))
    second_b = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code=reusable_code)))
    E.record(
        "C05c",
        "redeemed invite cannot be reused",
        first_b.get("returned") and denied(second_b, {401}),
        endpoint="POST /app/auth/activate",
        expected={"first": 200, "second": 401},
        observed={"first": first_b, "second": second_b},
        category="invite",
    )
    token_b = first_b["body"]["token"] if first_b.get("returned") else app.create_employee_session(COMPANY, EMP_B, PHONE_B)["token"]

    expired_code = "730001"
    insert_invite(COMPANY, EMP_E, PHONE_E, expired_code, expires_delta=timedelta(seconds=-1))
    result = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_E, code=expired_code)))
    E.record(
        "C05d",
        "expired invite is rejected",
        denied(result, {401}),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 401},
        observed=result,
        category="invite",
    )
    revoked_code = "730009"
    insert_invite(COMPANY, EMP_E, PHONE_E, revoked_code, status="revoked")
    revoked_invite = invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=PHONE_E, code=revoked_code)
        )
    )
    E.record(
        "C05d2",
        "explicitly revoked invite is rejected",
        denied(revoked_invite, {401}),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 401},
        observed=revoked_invite,
        category="invite",
    )

    wrong_employee_code = "730002"
    insert_invite(COMPANY, EMP_A, PHONE_D, wrong_employee_code)
    before_d = int(scalar("SELECT count(*) FROM employee_sessions WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_D)) or 0)
    wrong_employee = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_D, code=wrong_employee_code)))
    after_d = int(scalar("SELECT count(*) FROM employee_sessions WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_D)) or 0)
    E.record(
        "C05e",
        "invite employee_key/phone mismatch cannot activate the wrong employee",
        denied(wrong_employee, {401}) and after_d == before_d,
        endpoint="POST /app/auth/activate",
        expected={"status_code": 401, "new_sessions_for_wrong_employee": 0},
        observed={"response": wrong_employee, "sessions_before": before_d, "sessions_after": after_d},
        category="invite_security",
        remediation="Bind activation lookup to invite.employee_key and verify it equals the resolved employee before redeeming or creating a session.",
    )
    app.revoke_employee_app_access(COMPANY, EMP_D, reason=MARKER)

    wrong_company_code = "730003"
    insert_invite(COMPANY, EMP_CROSS, PHONE_CROSS, wrong_company_code)
    wrong_company = invoke(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_CROSS, code=wrong_company_code)))
    E.record(
        "C05f",
        "cross-company invite cannot activate an employee",
        denied(wrong_company, {401}),
        endpoint="POST /app/auth/activate",
        expected={"status_code": 401},
        observed=wrong_company,
        category="tenant_isolation",
    )

    # Disabled/archived invite + activation checks. Safe delivery mock prevents sends.
    for case_id, status, employee_key, phone in (
        ("C05g", "disabled", EMP_E, PHONE_E),
        ("C05h", "archived", EMP_F, PHONE_F),
    ):
        set_company_status(COMPANY, status)
        invite = invoke(lambda employee_key=employee_key: create_mocked_invite("failed", None, employee_key=employee_key)[0])
        invite_denied = denied(invite, {401, 403, 404})
        if invite.get("returned"):
            activation_result = invoke(
                lambda phone=phone, code=invite["body"]["code"]: app.app_auth_activate(
                    app.EmployeeAppActivateRequest(phone=phone, code=code)
                )
            )
        else:
            activation_result = {"skipped": True, "reason": "invite correctly denied"}
        activation_denied = activation_result.get("skipped") or denied(activation_result, {401, 403, 404})
        E.record(
            case_id,
            f"{status} company blocks invite and activation",
            invite_denied and bool(activation_denied),
            endpoint="POST /dashboard/.../app-invite + POST /app/auth/activate",
            expected={"invite_denied": True, "activation_denied": True},
            observed={"invite": invite, "activation": activation_result},
            category="company_lifecycle",
            remediation="Enforce active company lifecycle in the HR invite route and activation path before issuing/redeeming an invite.",
        )
        app.revoke_employee_app_access(COMPANY, employee_key, reason=MARKER)
        set_company_status(COMPANY, "active")

    # Already activated: no privileged second identity/session.
    sessions_before = int(scalar("SELECT count(*) FROM employee_sessions WHERE company_code=%s AND employee_key=%s AND status='active'", (COMPANY, EMP_A)) or 0)
    second_invite, _ = create_mocked_invite("failed", None)
    second_activation = invoke(
        lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code=second_invite["code"]))
    )
    sessions_after = int(scalar("SELECT count(*) FROM employee_sessions WHERE company_code=%s AND employee_key=%s AND status='active'", (COMPANY, EMP_A)) or 0)
    second_safe = denied(second_activation, {401, 409}) or (
        second_activation.get("returned") and sessions_after <= sessions_before
    )
    E.record(
        "C05i",
        "already-activated employee does not receive an additional privileged session",
        bool(second_safe),
        endpoint="POST /app/auth/activate",
        expected={"rejected_or_idempotent": True, "active_session_count_growth": 0},
        observed={"response": second_activation, "sessions_before": sessions_before, "sessions_after": sessions_after},
        category="invite_security",
        remediation="Define activation idempotency and reject or atomically replace existing active sessions instead of accumulating privileged sessions.",
    )
    if second_activation.get("returned"):
        token_a = second_activation["body"]["token"]
        refresh_a = second_activation["body"].get("refresh_token")

    # C06 — unseeded honesty + manual Option A.
    empty_ctx = app_context(app.create_employee_session(COMPANY, EMP_D, PHONE_D)["token"])
    empty = invoke(lambda: app.app_onboarding(empty_ctx))
    empty_body = empty.get("body") or {}
    empty_honest = (
        empty.get("returned")
        and empty_body.get("required_total") == 0
        and empty_body.get("received_count") == 0
        and empty_body.get("pending_count") == 0
        and empty_body.get("pending") == []
        and empty_body.get("received") == []
        and str(empty_body.get("status") or "").lower() not in {"complete", "completed", "ready"}
    )
    E.record(
        "C06a",
        "unseeded employee does not crash, invent items, or appear completed",
        bool(empty_honest),
        endpoint="GET /app/onboarding",
        expected={"required_total": 0, "items": [], "status_not_complete": True},
        observed=empty,
        category="onboarding",
        remediation="Return an explicit not_assigned state when no checklist exists; never derive completed from zero rows.",
    )
    for item_id in ITEMS:
        insert_item(COMPANY, EMP_A, item_id)
    ctx_a = app_context(token_a)
    manual = invoke(lambda: app.app_onboarding(ctx_a))
    manual_ids = {
        str(item.get("item_id"))
        for item in ((manual.get("body") or {}).get("pending") or [])
    }
    E.record(
        "C06b",
        "Option A exposes exactly four manually provisioned canonical items",
        manual.get("returned") and manual_ids == set(ITEMS) and not app.onboarding_seed_enabled(),
        endpoint="GET /app/onboarding",
        expected={"pending_item_ids": sorted(ITEMS), "onboarding_seed": False},
        observed={"response": manual, "seed_enabled": app.onboarding_seed_enabled()},
        category="onboarding",
    )

    # C07 — uploads.
    pdf_bytes = b"%PDF-1.4\n% synthetic phase7e\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    valid = invoke(lambda: synthetic_upload("civil-id.pdf", "application/pdf", pdf_bytes, "civil_id", ctx_a))
    file_id = (valid.get("body") or {}).get("file_id")
    canonical = {}
    if file_id:
        canonical["file_registry"] = exec_sql(
            "SELECT company_code, subject_key, document_type, storage_status, mime_type, metadata "
            "FROM file_registry WHERE file_id=%s",
            (file_id,),
        )
        canonical["employee_documents"] = exec_sql(
            "SELECT company_code, employee_key, item_id, document_type, status, storage_status, metadata "
            "FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id='civil_id' ORDER BY updated_at DESC LIMIT 1",
            (COMPANY, EMP_A),
        )
        canonical["onboarding_item"] = exec_sql(
            "SELECT status, document_type, storage_status, mime_type FROM onboarding_items WHERE employee_key=%s AND item_id='civil_id'",
            (EMP_A,),
        )
    canonical_ok = (
        valid.get("returned")
        and bool(file_id)
        and bool(canonical.get("file_registry"))
        and canonical["file_registry"][0].get("company_code") == COMPANY
        and canonical["file_registry"][0].get("subject_key") == EMP_A
        and canonical["file_registry"][0].get("document_type") == "civil_id"
        and bool(canonical.get("employee_documents"))
        and canonical["employee_documents"][0].get("status") == "received"
        and bool(canonical.get("onboarding_item"))
        and canonical["onboarding_item"][0].get("status") == "received"
    )
    E.record(
        "C07a",
        "valid synthetic upload creates canonical Document Hub linkage",
        bool(canonical_ok),
        endpoint="POST /app/onboarding/documents",
        expected={"file_registry": True, "employee_documents": True, "onboarding_item": "received"},
        observed={"response": valid, "canonical": canonical},
        category="document_upload",
    )

    action_audit = exec_sql(
        "SELECT action_type, status, company_code, actor_user_id FROM action_results "
        "WHERE company_code=%s AND action_type='employee_document_uploaded' ORDER BY created_at DESC LIMIT 1",
        (COMPANY,),
    )
    E.record(
        "C07b",
        "successful upload is auditable",
        bool(action_audit) and action_audit[0].get("status") == "completed",
        endpoint="POST /app/onboarding/documents",
        expected={"action_type": "employee_document_uploaded", "status": "completed"},
        observed=action_audit,
        category="audit",
    )

    cross_employee = invoke(
        lambda: synthetic_upload("other.pdf", "application/pdf", pdf_bytes, "other_employee_only", ctx_a)
    )
    E.record(
        "C07c",
        "cross-employee item upload is denied",
        denied(cross_employee, {404}),
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": 404},
        observed=cross_employee,
        category="employee_isolation",
    )
    cross_tenant_upload = invoke(
        lambda: synthetic_upload("cross.pdf", "application/pdf", pdf_bytes, "cross_tenant_only", ctx_a)
    )
    E.record(
        "C07d",
        "cross-tenant item upload is denied",
        denied(cross_tenant_upload, {404}),
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": 404},
        observed=cross_tenant_upload,
        category="tenant_isolation",
    )
    foreign_file = insert_owned_file(OTHER_COMPANY, EMP_CROSS, "cross_tenant_only")
    cross_tenant_read = invoke(lambda: app.app_document_file(foreign_file, context=ctx_a))
    E.record(
        "C07e",
        "cross-tenant document read is denied",
        denied(cross_tenant_read, {404}),
        endpoint="GET /app/documents/{file_id}",
        expected={"status_code": 404},
        observed=cross_tenant_read,
        category="tenant_isolation",
    )
    same_tenant_foreign = insert_owned_file(COMPANY, EMP_B, "other_employee_only")
    cross_employee_read = invoke(lambda: app.app_document_file(same_tenant_foreign, context=ctx_a))
    E.record(
        "C07f",
        "cross-employee document read is denied",
        denied(cross_employee_read, {404}),
        endpoint="GET /app/documents/{file_id}",
        expected={"status_code": 404},
        observed=cross_employee_read,
        category="employee_isolation",
    )

    bad_extension = invoke(
        lambda: synthetic_upload("bank-details.exe", "application/octet-stream", b"MZ synthetic", "bank_details", ctx_a)
    )
    E.record(
        "C07g",
        "server rejects disallowed extension",
        denied(bad_extension, {400}) and (bad_extension.get("body") or {}).get("error") == "unsupported_file_type",
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": 400, "error": "unsupported_file_type"},
        observed=bad_extension,
        category="document_validation",
    )
    oversized = invoke(
        lambda: synthetic_upload(
            "employment-contract.pdf",
            "application/pdf",
            b"%PDF-" + (b"x" * (app._APP_DOC_MAX_BYTES + 1)),
            "employment_contract",
            ctx_a,
        )
    )
    E.record(
        "C07h",
        "server rejects file over 15 MiB cap",
        denied(oversized, {400}) and (oversized.get("body") or {}).get("error") == "file_too_large",
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": 400, "error": "file_too_large"},
        observed=oversized,
        category="document_validation",
    )
    mime_mismatch = invoke(
        lambda: synthetic_upload(
            "personal-photo.pdf",
            "image/png",
            b"\x89PNG\r\n\x1a\nsynthetic",
            "personal_photo",
            ctx_a,
        )
    )
    E.record(
        "C07i",
        "server rejects extension/MIME mismatch",
        denied(mime_mismatch, {400, 415}),
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": "400/415", "error": "mime_mismatch_or_invalid_content"},
        observed=mime_mismatch,
        category="document_validation",
        remediation="Add server-side MIME allowlist and extension-to-MIME/content-signature consistency validation before storage.",
    )

    rows_before = {
        "files": int(scalar("SELECT count(*) FROM file_registry WHERE company_code=%s AND subject_key=%s AND document_type='bank_details'", (COMPANY, EMP_A)) or 0),
        "docs": int(scalar("SELECT count(*) FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id='bank_details'", (COMPANY, EMP_A)) or 0),
        "status": scalar("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='bank_details'", (EMP_A,)),
    }
    original_store = app.store_onboarding_document
    app.store_onboarding_document = lambda **_kwargs: {
        "ok": False,
        "provider": "mock",
        "storage_status": "failed",
        "storage_error": "synthetic_failure",
    }
    try:
        failed_write = invoke(
            lambda: synthetic_upload("bank-details.pdf", "application/pdf", pdf_bytes, "bank_details", ctx_a)
        )
    finally:
        app.store_onboarding_document = original_store
    rows_after = {
        "files": int(scalar("SELECT count(*) FROM file_registry WHERE company_code=%s AND subject_key=%s AND document_type='bank_details'", (COMPANY, EMP_A)) or 0),
        "docs": int(scalar("SELECT count(*) FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id='bank_details'", (COMPANY, EMP_A)) or 0),
        "status": scalar("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='bank_details'", (EMP_A,)),
    }
    E.record(
        "C07j",
        "failed storage does not create canonical rows or mark item received",
        denied(failed_write, {502}) and rows_before == rows_after,
        endpoint="POST /app/onboarding/documents",
        expected={"status_code": 502, "database_state_unchanged": True},
        observed={"response": failed_write, "before": rows_before, "after": rows_after},
        category="orphan_safety",
    )
    # Stronger orphan test: storage succeeds, then the DB receipt write fails.
    # A durable implementation must compensate by deleting the permanent object.
    workspace = Path(os.environ.get("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace"))
    company_files = workspace / "data" / "companies" / COMPANY
    permanent_before = {
        str(path)
        for path in company_files.rglob("*")
        if path.is_file()
    } if company_files.exists() else set()
    contract_before = {
        "files": int(scalar("SELECT count(*) FROM file_registry WHERE company_code=%s AND subject_key=%s AND document_type='employment_contract'", (COMPANY, EMP_A)) or 0),
        "docs": int(scalar("SELECT count(*) FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id='employment_contract'", (COMPANY, EMP_A)) or 0),
        "status": scalar("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='employment_contract'", (EMP_A,)),
    }
    original_receipt = app.record_employee_document_receipt

    def fail_after_storage(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic_db_failure_after_storage")

    app.record_employee_document_receipt = fail_after_storage
    try:
        post_storage_failure = invoke(
            lambda: synthetic_upload(
                "employment-contract.pdf",
                "application/pdf",
                pdf_bytes + b"post-storage-failure",
                "employment_contract",
                ctx_a,
            )
        )
    finally:
        app.record_employee_document_receipt = original_receipt
    permanent_after = {
        str(path)
        for path in company_files.rglob("*")
        if path.is_file()
    } if company_files.exists() else set()
    orphan_paths = sorted(permanent_after - permanent_before)
    contract_after = {
        "files": int(scalar("SELECT count(*) FROM file_registry WHERE company_code=%s AND subject_key=%s AND document_type='employment_contract'", (COMPANY, EMP_A)) or 0),
        "docs": int(scalar("SELECT count(*) FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id='employment_contract'", (COMPANY, EMP_A)) or 0),
        "status": scalar("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='employment_contract'", (EMP_A,)),
    }
    E.record(
        "C07k",
        "DB failure after successful storage leaves no permanent orphan",
        not post_storage_failure.get("returned")
        and contract_before == contract_after
        and orphan_paths == [],
        endpoint="POST /app/onboarding/documents",
        expected={"request_failed": True, "database_state_unchanged": True, "permanent_orphans": []},
        observed={
            "response": post_storage_failure,
            "database_before": contract_before,
            "database_after": contract_after,
            "permanent_orphans": orphan_paths,
        },
        category="orphan_safety",
        remediation="Add compensating deletion for the stored local/Drive object when the post-storage database transaction fails, or make storage finalization transactional.",
    )
    # Remove synthetic orphan(s) so verifier cleanup remains deterministic.
    for orphan in orphan_paths:
        try:
            Path(orphan).unlink(missing_ok=True)
        except Exception:
            pass

    rejection_audits_before = int(
        scalar(
            "SELECT count(*) FROM action_results WHERE company_code=%s AND action_type='employee_document_upload_rejected'",
            (COMPANY,),
        )
        or 0
    )
    rejected_for_audit = invoke(
        lambda: synthetic_upload(
            "audit-reject.exe",
            "application/octet-stream",
            b"MZ synthetic rejection",
            "bank_details",
            ctx_a,
        )
    )
    rejection_audits_after = int(
        scalar(
            "SELECT count(*) FROM action_results WHERE company_code=%s AND action_type='employee_document_upload_rejected'",
            (COMPANY,),
        )
        or 0
    )
    E.record(
        "C07l",
        "rejected employee upload is auditable",
        denied(rejected_for_audit, {400})
        and rejection_audits_after == rejection_audits_before + 1,
        endpoint="POST /app/onboarding/documents",
        expected={"request_denied": True, "rejection_audit_growth": 1},
        observed={
            "response": rejected_for_audit,
            "audit_before": rejection_audits_before,
            "audit_after": rejection_audits_after,
        },
        category="audit",
        remediation="Write an HR-safe, company/employee-scoped audit event for rejected upload attempts without recording document bytes or secrets.",
    )

    # C08 — leave self-scope.
    ctx_b = app_context(token_b)
    leave_create = invoke(
        lambda: app.app_leave_request(
            app.EmployeeLeaveRequestBody(start_date="2099-01-10", end_date="2099-01-12", leave_type="annual"),
            context=ctx_a,
        )
    )
    leave_id = ((leave_create.get("body") or {}).get("leave") or {}).get("leave_id")
    leave_cross = invoke(lambda: app.app_leave_cancel(str(leave_id), context=ctx_b)) if leave_id else {"skipped": True}
    leave_own = invoke(lambda: app.app_leave_cancel(str(leave_id), context=ctx_a)) if leave_id else {"skipped": True}
    E.record(
        "C08",
        "leave request/cancel remains employee-owned",
        leave_create.get("returned") and denied(leave_cross, {404}) and leave_own.get("returned"),
        endpoint="POST /app/leave/request + POST /app/leave/{id}/cancel",
        expected={"create": 200, "cross_employee_cancel": 404, "own_cancel": 200},
        observed={"create": leave_create, "cross": leave_cross, "own": leave_own},
        category="employee_isolation",
    )

    # C09 — inbox-only, server-owned state.
    message_id = str(uuid.uuid4())
    exec_sql(
        """
        INSERT INTO employee_messages
          (message_id, company_code, employee_key, flow, template_key, sensitivity,
           body_preview, status, attempts, metadata)
        VALUES (%s,%s,%s,'onboarding','onboarding_reminder','preview',%s,'pending',1,%s)
        """,
        (message_id, COMPANY, EMP_A, "Synthetic onboarding reminder", Json({"marker": MARKER, "outbound_mode": "inbox_only"})),
    )
    inbox = invoke(lambda: app.app_notifications(ctx_a))
    inbox_item = next(
        (item for item in ((inbox.get("body") or {}).get("notifications") or []) if item.get("id") == message_id),
        None,
    )
    mark = invoke(lambda: app.app_notification_mark_read(message_id, context=ctx_a))
    E.record(
        "C09",
        "inbox exposes backend-owned status without push",
        inbox.get("returned")
        and inbox_item is not None
        and inbox_item.get("status") == "pending"
        and mark.get("returned")
        and not app.push_notifications_enabled(),
        endpoint="GET /app/notifications + POST /app/notifications/{id}/read",
        expected={"server_status": "pending", "push_enabled": False, "read_marked": True},
        observed={"item": inbox_item, "mark": mark, "push_enabled": app.push_notifications_enabled()},
        category="delivery",
    )

    # C10 — API-level rollback/kill switches. Navigation is not involved.
    set_flag("WATHEFNI_EMPLOYEE_APP", False)
    global_off = invoke(lambda: app_context(token_a))
    E.record(
        "C10a",
        "global flag OFF blocks a previously valid bearer",
        denied(global_off, {503}),
        endpoint="GET /app/me (employee_app_context)",
        expected={"status_code": 503},
        observed=global_off,
        category="rollback",
        rollback=True,
    )
    if refresh_a:
        global_refresh = invoke(
            lambda: app.app_auth_refresh(
                app.EmployeeAppRefreshRequest(refresh_token=refresh_a)
            )
        )
        E.record(
            "C10a2",
            "global flag OFF blocks refresh",
            denied(global_refresh, {503}),
            endpoint="POST /app/auth/refresh",
            expected={"status_code": 503},
            observed=global_refresh,
            category="rollback",
            rollback=True,
        )
    set_flag("WATHEFNI_EMPLOYEE_APP", True)

    set_module(COMPANY, "employee_app", False)
    module_off = invoke(lambda: app_context(token_a))
    E.record(
        "C10b",
        "company module removal blocks a previously valid bearer",
        denied(module_off, {403}),
        endpoint="GET /app/me (employee_app_context)",
        expected={"status_code": 403},
        observed=module_off,
        category="rollback",
        rollback=True,
    )
    if refresh_a:
        module_refresh = invoke(lambda: app.app_auth_refresh(app.EmployeeAppRefreshRequest(refresh_token=refresh_a)))
        E.record(
            "C10c",
            "company module removal blocks refresh",
            denied(module_refresh, {401, 403}),
            endpoint="POST /app/auth/refresh",
            expected={"status_code": "401/403"},
            observed=module_refresh,
            category="rollback",
            remediation="Apply company lifecycle/module/employee eligibility gates before rotating a refresh token; revoke the session when a gate fails.",
            rollback=True,
        )
        if module_refresh.get("returned"):
            token_a = module_refresh["body"]["token"]
            refresh_a = module_refresh["body"]["refresh_token"]
    set_module(COMPANY, "employee_app", True)

    for case_id, status in (("C10d", "disabled"), ("C10e", "archived")):
        set_company_status(COMPANY, status)
        lifecycle_access = invoke(lambda: app_context(token_a))
        E.record(
            case_id,
            f"company {status} blocks subsequent authenticated API access",
            denied(lifecycle_access, {401, 403}),
            endpoint="GET /app/me (employee_app_context)",
            expected={"status_code": "401/403", "company_status": status},
            observed=lifecycle_access,
            category="rollback",
            remediation="Add an active-company lifecycle check to employee_app_context and all unauthenticated auth/invite paths.",
            rollback=True,
        )
        if refresh_a:
            lifecycle_refresh = invoke(
                lambda: app.app_auth_refresh(
                    app.EmployeeAppRefreshRequest(refresh_token=refresh_a)
                )
            )
            E.record(
                f"{case_id}2",
                f"company {status} blocks refresh",
                denied(lifecycle_refresh, {401, 403}),
                endpoint="POST /app/auth/refresh",
                expected={"status_code": "401/403", "company_status": status},
                observed=lifecycle_refresh,
                category="rollback",
                remediation="Check active company lifecycle and effective employee_app module before rotating refresh credentials.",
                rollback=True,
            )
            if lifecycle_refresh.get("returned"):
                token_a = lifecycle_refresh["body"]["token"]
                refresh_a = lifecycle_refresh["body"]["refresh_token"]
        set_company_status(COMPANY, "active")

    app.revoke_employee_app_access(COMPANY, EMP_A, reason=MARKER)
    employee_revoked = invoke(lambda: app_context(token_a))
    E.record(
        "C10f",
        "per-employee revoke blocks subsequent authenticated API access",
        denied(employee_revoked, {401, 403}),
        endpoint="GET /app/me (employee_app_context)",
        expected={"status_code": "401/403"},
        observed=employee_revoked,
        category="rollback",
        rollback=True,
    )
    if refresh_a:
        revoked_refresh = invoke(
            lambda: app.app_auth_refresh(
                app.EmployeeAppRefreshRequest(refresh_token=refresh_a)
            )
        )
        E.record(
            "C10f2",
            "per-employee revoke blocks refresh",
            denied(revoked_refresh, {401, 403}),
            endpoint="POST /app/auth/refresh",
            expected={"status_code": "401/403"},
            observed=revoked_refresh,
            category="rollback",
            rollback=True,
        )
    doc_after_revoke = invoke(
        lambda: app.app_document_file(str(file_id), context=app_context(token_a))
    ) if file_id else {"skipped": True}
    E.record(
        "C10g",
        "revoked employee cannot download a previously owned document",
        denied(doc_after_revoke, {401, 403}),
        endpoint="GET /app/documents/{file_id}",
        expected={"status_code": "401/403"},
        observed=doc_after_revoke,
        category="rollback",
        rollback=True,
    )

    # Existing shared/dash surfaces remain available in-process.
    shared = app.send_octopus_whatsapp(
        account_id="default",
        phone=PHONE_A,
        text="phase7e synthetic rollback proof",
        subject_type="employee",
        subject_key=EMP_A,
    )
    E.record(
        "C10h",
        "rollback does not require company channel routing or live delivery",
        shared.get("dry_run") is True and "channel_route" not in shared,
        endpoint="shared send helper (dry-run)",
        expected={"dry_run": True, "shared_account": "default", "company_route": False},
        observed=shared,
        category="rollback",
        rollback=True,
    )

    return {"last_token_hash": hashlib.sha256(str(token_a).encode()).hexdigest()[:12]}


def main() -> int:
    dsn = os.environ.get("WATHEFNI_DATABASE_URL", "")
    if "staging" not in dsn.lower():
        raise SystemExit("refusing Phase 7E verifier against non-staging DSN")
    if COMPANY == PROTECTED_COMPANY or OTHER_COMPANY == PROTECTED_COMPANY:
        raise SystemExit("refusing protected company fixture")

    production_flags_before = systemd_flags("wathefni-orchestrator.service")
    staging_flags_before = systemd_flags("wathefni-orchestrator-staging.service")
    if not all(flag_is_off(production_flags_before.get(flag, "unset")) for flag in PROTECTED_FLAGS):
        raise SystemExit(f"refusing: protected production flag is not OFF: {production_flags_before}")

    production_before = production_snapshot()
    staging_protected_before = staging_protected_snapshot()
    extra: dict[str, Any] = {
        "production_flags_before": production_flags_before,
        "staging_flags_before": staging_flags_before,
        "production_snapshot_before": production_before,
        "staging_protected_snapshot_before": staging_protected_before,
    }

    setup()
    matrix_extra: dict[str, Any] = {}
    try:
        matrix_extra = run_matrix()
    finally:
        # The verifier's process-local flag is always restored OFF; systemd was
        # never changed. Fixtures and synthetic files are removed.
        for flag in PROTECTED_FLAGS:
            set_flag(flag, False)
        set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
        cleanup()

    production_after = production_snapshot()
    staging_protected_after = staging_protected_snapshot()
    production_flags_after = systemd_flags("wathefni-orchestrator.service")
    staging_flags_after = systemd_flags("wathefni-orchestrator-staging.service")
    production_unchanged = production_before.get("sha256") == production_after.get("sha256")
    staging_protected_unchanged = staging_protected_before.get("sha256") == staging_protected_after.get("sha256")

    E.record(
        "C11a",
        "production protected flags remained OFF",
        all(flag_is_off(production_flags_after.get(flag, "unset")) for flag in PROTECTED_FLAGS),
        endpoint="systemd wathefni-orchestrator.service",
        expected={flag: "off/unset" for flag in PROTECTED_FLAGS},
        observed=production_flags_after,
        category="production_protection",
        rollback=True,
    )
    E.record(
        "C11b",
        "staging systemd protected flags remained OFF",
        all(flag_is_off(staging_flags_after.get(flag, "unset")) for flag in PROTECTED_FLAGS),
        endpoint="systemd wathefni-orchestrator-staging.service",
        expected={flag: "off/unset" for flag in PROTECTED_FLAGS},
        observed=staging_flags_after,
        category="production_protection",
        rollback=True,
    )
    E.record(
        "C11c",
        "production WATHEFNI data snapshot remained unchanged",
        production_unchanged,
        endpoint="production DB read-only fingerprint",
        expected={"unchanged": True, "before": production_before.get("sha256")},
        observed={"unchanged": production_unchanged, "after": production_after.get("sha256")},
        category="production_protection",
    )
    E.record(
        "C11d",
        "staging WATHEFNI protected tenant remained unchanged",
        staging_protected_unchanged,
        endpoint="staging DB protected-tenant fingerprint",
        expected={"unchanged": True, "before": staging_protected_before.get("sha256")},
        observed={"unchanged": staging_protected_unchanged, "after": staging_protected_after.get("sha256")},
        category="tenant_isolation",
    )
    remaining = int(
        scalar("SELECT count(*) FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER_COMPANY],))
        or 0
    )
    E.record(
        "C11e",
        "throwaway staging fixtures were removed after evidence capture",
        remaining == 0,
        endpoint="staging DB cleanup",
        expected={"remaining_fixture_companies": 0},
        observed={"remaining_fixture_companies": remaining},
        category="rollback",
        rollback=True,
    )

    extra.update(
        {
            **matrix_extra,
            "production_flags_after": production_flags_after,
            "staging_flags_after": staging_flags_after,
            "production_snapshot_after": production_after,
            "staging_protected_snapshot_after": staging_protected_after,
            "production_snapshot_unchanged": production_unchanged,
            "staging_protected_snapshot_unchanged": staging_protected_unchanged,
            "fixture_cleanup_remaining": remaining,
        }
    )
    json_path, md_path = E.write(extra)
    passed = sum(1 for item in E.cases if item["status"] == "PASS")
    failed = len(E.cases) - passed
    print(f"\nPHASE 7E E2: {passed}/{len(E.cases)} passed, {failed} failed")
    print(f"machine_report={json_path}")
    print(f"human_report={md_path}")
    print("recommendation=" + ("staging-green" if failed == 0 else "not-staging-green"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
