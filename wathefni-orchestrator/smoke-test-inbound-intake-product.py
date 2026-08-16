"""Wave D Phase 2 — productized forwarded inbound CV intake (local only).

Proves:
* tenant resolve only from recipient (active intake_addresses)
* create / rotate / disable / inspect APIs (soft-disable)
* allowlist + tenant flag fail-closed for external tenants
* optional job alias vs needs_role hold_policy
* EN/AR setup instructions present
* health + quotas surfaced without Intake Operations UI
* durable ingress still rejects unknown / disabled / non-allowlisted recipients
"""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi.testclient import TestClient

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-inbound-d2-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if database_url:
    parsed_database = urlparse(database_url)
    env_file = _QUARANTINE / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ["WATHEFNI_ENV"] = "test"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed_database.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed_database.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed_database.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-local-boundary-remediation-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated test database."
    )

os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ["WATHEFNI_INBOUND_ALLOWED_COMPANIES"] = "WATHEFNI,D2TESTA,D2TESTB"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"

import app  # noqa: E402
import inbound_intake_product as iip  # noqa: E402

COMPANY_A = "D2TESTA"
COMPANY_B = "D2TESTB"
EXTERNAL = "ACMECORP"
MARKER = "wave_d2_inbound_intake_product"


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
            print(f"PASS  {label}")
        for label in self.failed:
            print(f"FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 0 if not self.failed else 1


def _pdf(name: str, email: str) -> bytes:
    summary = "Senior analyst with bilingual client coordination and reporting."
    stream = (
        f"BT /F1 12 Tf 72 720 Td ({name}) Tj "
        f"0 -18 Td (Email {email}) Tj "
        f"0 -18 Td ({summary}) Tj ET"
    ).encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n"
        + f"4 0 obj<</Length {len(stream)}>>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
        + b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        + b"xref\n0 6\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n"
    )


def _att(name: str, data: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": "application/pdf",
        "ContentLength": len(encoded),
    }


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict]) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": "My CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _ctx(company: str) -> dict[str, Any]:
    user_id = f"d2-user-{company.lower()}"
    perms = sorted(app.ROLE_PERMISSIONS["owner"])
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_email": "hr@example.com",
        "actor_name": "D2 HR",
        "role": "owner",
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "modules": {"pre_hiring": {"enabled": True}},
        "hr_user": {
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "company_code": company,
            "permissions": perms,
        },
        "access": {
            "role": "owner",
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
    }


def setup() -> None:
    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B, EXTERNAL, "WATHEFNI"):
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (
                        company,
                        f"D2 {company}",
                        app.Json({"smoke": MARKER}),
                        app.Json({"smoke": MARKER}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, settings, source, updated_at)
                    VALUES (%s,'pre_hiring',true,'{}'::jsonb,'smoke',now())
                    ON CONFLICT (company_code, module_key) DO UPDATE
                      SET enabled=true, updated_at=now()
                    """,
                    (company,),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.authority_cleanup','synthetic',true)")
            companies = [COMPANY_A, COMPANY_B, EXTERNAL]
            cur.execute("DELETE FROM intake_processing_jobs WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_documents WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_submissions WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM inbound_messages WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_addresses WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM company_settings WHERE company_code = ANY(%s)", (companies,))
            cur.execute(
                "DELETE FROM intake_addresses WHERE local_part LIKE %s OR local_part LIKE %s",
                ("d2testa-%", "d2testb-%"),
            )
        conn.commit()
    shutil.rmtree(_QUARANTINE, ignore_errors=True)


def main() -> int:
    checks = Checks()
    setup()
    client = TestClient(app.app)
    app.app.dependency_overrides[app.prehire_dashboard_context] = lambda: _ctx(COMPANY_A)

    try:
        checks.check(
            "allowlist includes test tenants and WATHEFNI",
            lambda: iip.company_on_inbound_allowlist(COMPANY_A)
            and iip.company_on_inbound_allowlist("WATHEFNI")
            and not iip.company_on_inbound_allowlist(EXTERNAL),
        )
        checks.check(
            "setup instructions include EN/AR steps",
            lambda: len(iip.setup_instructions()["setup_steps_en"]) >= 5
            and len(iip.setup_instructions()["setup_steps_ar"]) >= 5,
        )

        created = client.post(
            "/dashboard/prehire/integrations/intake",
            json={"label": "General careers"},
        )
        checks.check("create intake address 200", lambda: created.status_code == 200)
        address = (created.json() or {}).get("address") or {}
        intake_id = str(address.get("intake_id") or "")
        local = str(address.get("local_part") or "")
        full_address = str(address.get("address") or "")
        checks.check(
            "create returns needs_role hold policy without position",
            lambda: address.get("hold_policy") == "needs_role" and address.get("status") == "active",
        )

        listed = client.get("/dashboard/prehire/integrations/intake")
        body = listed.json() if listed.status_code == 200 else {}
        checks.check(
            "list exposes feature health and quotas",
            lambda: listed.status_code == 200
            and body.get("feature", {}).get("enabled") is True
            and "quotas" in (body.get("feature") or {})
            and "health" in (body.get("feature") or {})
            and len(body.get("setup_steps_en") or []) >= 5
            and len(body.get("setup_steps_ar") or []) >= 5,
        )

        inspected = client.get(f"/dashboard/prehire/integrations/intake/{intake_id}")
        checks.check(
            "inspect returns address + setup copy",
            lambda: inspected.status_code == 200
            and (inspected.json() or {}).get("address", {}).get("intake_id") == intake_id
            and (inspected.json() or {}).get("forward_instructions_en"),
        )

        # Tenant isolation: company B cannot see/disable company A address
        app.app.dependency_overrides[app.prehire_dashboard_context] = lambda: _ctx(COMPANY_B)
        cross = client.get(f"/dashboard/prehire/integrations/intake/{intake_id}")
        checks.check("inspect is tenant-scoped 404", lambda: cross.status_code == 404)
        cross_disable = client.post(f"/dashboard/prehire/integrations/intake/{intake_id}/disable")
        checks.check("disable is tenant-scoped 404", lambda: cross_disable.status_code == 404)

        # External tenant cannot create even with global ON
        app.app.dependency_overrides[app.prehire_dashboard_context] = lambda: _ctx(EXTERNAL)
        blocked = client.post("/dashboard/prehire/integrations/intake", json={"label": "Nope"})
        checks.check(
            "external tenant create blocked",
            lambda: blocked.status_code in {403, 404},
        )

        app.app.dependency_overrides[app.prehire_dashboard_context] = lambda: _ctx(COMPANY_A)

        role_bound = client.post(
            "/dashboard/prehire/integrations/intake",
            json={
                "local_part": f"{local}-eng",
                "position_code": "ENG-1",
                "position_title": "Engineer",
                "label": "Engineer inbox",
            },
        )
        role_addr = (role_bound.json() or {}).get("address") or {}
        checks.check(
            "optional job-specific alias is role_bound",
            lambda: role_bound.status_code == 200 and role_addr.get("hold_policy") == "role_bound",
        )

        # Recipient-only resolve + durable path
        hit = None
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hit = app.resolve_intake_address(cur, full_address, None)
        checks.check(
            "resolve tenant only from recipient",
            lambda: hit is not None and hit.get("company_code") == COMPANY_A,
        )

        received = app.process_postmark_inbound(
            _payload(
                f"d2-{intake_id}-1",
                full_address,
                "Candidate <cand@example.com>",
                [_att("CV.pdf", _pdf("Cand", "cand@example.com"))],
            )
        )
        checks.check(
            "durable receive for allowlisted active address",
            lambda: received.get("durable") is True and received.get("company_code") == COMPANY_A,
        )

        # Rotate: old recipient unknown, new recipient active
        rotated = client.post(f"/dashboard/prehire/integrations/intake/{intake_id}/rotate")
        rot = rotated.json() if rotated.status_code == 200 else {}
        new_address = (rot.get("address") or {}).get("address")
        checks.check(
            "rotate disables previous and creates new",
            lambda: rotated.status_code == 200
            and (rot.get("previous") or {}).get("status") == "disabled"
            and (rot.get("address") or {}).get("status") == "active"
            and new_address
            and new_address != full_address,
        )

        old_msg = app.process_postmark_inbound(
            _payload(
                f"d2-{intake_id}-old",
                full_address,
                "Old <old@example.com>",
                [_att("Old.pdf", _pdf("Old", "old@example.com"))],
            )
        )
        checks.check(
            "disabled address rejects as unknown_recipient",
            lambda: old_msg.get("ignored") == "unknown_recipient",
        )

        # Soft-disable remaining role address
        role_id = str(role_addr.get("intake_id") or "")
        disabled = client.post(f"/dashboard/prehire/integrations/intake/{role_id}/disable")
        checks.check(
            "disable soft-sets status",
            lambda: disabled.status_code == 200
            and (disabled.json() or {}).get("address", {}).get("status") == "disabled",
        )

        # Tenant flag off → resolve fails closed
        app.set_company_setting(COMPANY_A, "inbound_forwarding_enabled", False)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                gated = app.resolve_intake_address(cur, new_address, None)
        checks.check("tenant flag off fails closed on resolve", lambda: gated is None)
        app.set_company_setting(COMPANY_A, "inbound_forwarding_enabled", True)

        # Quotas stored on allowlisted tenant
        put = client.put(
            "/dashboard/prehire/integrations/email",
            json={"inbound_quotas": {"daily_message_quota": 25}},
        )
        email_view = put.json() if put.status_code == 200 else {}
        checks.check(
            "tenant quotas stored and surfaced",
            lambda: put.status_code == 200
            and ((email_view.get("intake") or {}).get("feature") or {})
            .get("quotas", {})
            .get("tenant_overrides", {})
            .get("daily_message_quota")
            == 25,
        )

        # External company with forged address row must not resolve
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_addresses (company_code, local_part, domain, status)
                    VALUES (%s,'acmecorp-cv-forged','inbound.wathefni.ai','active')
                    """,
                    (EXTERNAL,),
                )
            conn.commit()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                forged = app.resolve_intake_address(
                    cur, "acmecorp-cv-forged@inbound.wathefni.ai", None
                )
        checks.check("non-allowlisted company never resolves", lambda: forged is None)

        # Email settings view keeps product language (no Intake Ops)
        view = client.get("/dashboard/prehire/integrations/email")
        view_body = view.json() if view.status_code == 200 else {}
        checks.check(
            "email settings intake productized without ops clutter keys",
            lambda: view.status_code == 200
            and "setup_steps_en" in (view_body.get("intake") or {})
            and "Intake Operations" not in str(view_body),
        )

    finally:
        app.app.dependency_overrides.pop(app.prehire_dashboard_context, None)
        teardown()

    return checks.report()


if __name__ == "__main__":
    raise SystemExit(main())
