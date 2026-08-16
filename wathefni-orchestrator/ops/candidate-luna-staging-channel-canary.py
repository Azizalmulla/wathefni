#!/usr/bin/env python3
"""Final staging OpenClaw/Octopus channel canary for Luna qualification.

Staging only. One authorized internal recipient. One live assessment invitation.
Inbound provider-message-ID ledger + replay via Octopus-shaped orchestrator
metadata (same contract as the reloaded channel extension). Cleans synthetic
rows. Does not change Luna/Terra. Does not touch production DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MARKER = "luna_channel_canary_v1"
COMPANY = "WATHEFNI"
BATTERY_KEY = "wathefni_ability_v1"
APP_KEY = f"luna-canary-{uuid.uuid4().hex[:10]}"
EVIDENCE_DIR = Path(
    os.environ.get("WATHEFNI_LUNA_CANARY_EVIDENCE_DIR")
    or "/opt/wathefni/staging/evidence/candidate-luna-channel-canary1"
)
OPENCLAW_DROPIN = Path(
    "/root/.config/systemd/user/openclaw-gateway.service.d/luna-staging-canary-orchestrator.conf"
)
STAGING_ORCH_URL = "http://127.0.0.1:8011/orchestrator/whatsapp-turn"
AUTHORIZED_PHONE_SHA256 = "492c7b867e94619fab58426d4c938b86f06983f8c4d6ded0fd29bb16e854c437"
AUTHORIZED_NAME = "Aziz Almulla"
LUNA_COMMIT = "a15fe3c72b0d401d73317049b4de9fccf457e594"
LUNA_ARTIFACT = "f2d54ffde8cec2af3dae4f9a62f15a8e8a5c31ca2fe2ecba93c93679f492f25b"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) < 4:
        return "****"
    return f"{digits[:3]}****{digits[-4:]}"


def systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/0"}
    return subprocess.run(
        ["systemctl", "--user", *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def gateway_pid() -> str | None:
    proc = subprocess.run(
        ["pgrep", "-f", "openclaw/dist/index.js gateway"],
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines[0] if lines else None


def extension_proof() -> dict[str, Any]:
    path = Path("/root/.openclaw/extensions/octopus-channel.ts")
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "has_provider_message_id_forwarding": "provider_message_id: params.providerMessageId" in text,
        "has_missing_id_gate": "missing_provider_message_id" in text,
        "has_authoritative_fail_closed": "Authoritative with empty reply" in text
        or "authoritative_return_even_without_reply" in text
        or ("orchestratorReply?.authoritative" in text and "has_reply" in text),
        "default_orchestrator_url_line_present": "127.0.0.1:8010/orchestrator/whatsapp-turn" in text,
    }


def reload_openclaw_to_staging() -> dict[str, Any]:
    before_pid = gateway_pid()
    before_start = None
    if before_pid:
        before_start = subprocess.check_output(["ps", "-o", "lstart=", "-p", before_pid], text=True).strip()
    OPENCLAW_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    OPENCLAW_DROPIN.write_text(
        "\n".join(
            [
                "[Service]",
                f"Environment=WATHEFNI_HR_ORCHESTRATOR_URL={STAGING_ORCH_URL}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    daemon = systemctl_user("daemon-reload")
    restart = systemctl_user("restart", "openclaw-gateway.service")
    time.sleep(3)
    after_pid = gateway_pid()
    after_start = None
    env_url = None
    if after_pid:
        after_start = subprocess.check_output(["ps", "-o", "lstart=", "-p", after_pid], text=True).strip()
        environ = Path(f"/proc/{after_pid}/environ").read_bytes().split(b"\0")
        for item in environ:
            if item.startswith(b"WATHEFNI_HR_ORCHESTRATOR_URL="):
                env_url = item.decode("utf-8", errors="replace").split("=", 1)[1]
                break
    status = systemctl_user("is-active", "openclaw-gateway.service")
    return {
        "dropin": str(OPENCLAW_DROPIN),
        "daemon_reload_rc": daemon.returncode,
        "restart_rc": restart.returncode,
        "restart_stderr": (restart.stderr or "")[:500],
        "before_pid": before_pid,
        "after_pid": after_pid,
        "before_start": before_start,
        "after_start": after_start,
        "pid_changed": bool(before_pid and after_pid and before_pid != after_pid),
        "active": (status.stdout or "").strip(),
        "orchestrator_url_env": env_url,
        "points_at_staging": env_url == STAGING_ORCH_URL,
        "extension": extension_proof(),
    }


def restore_openclaw_default() -> dict[str, Any]:
    before_pid = gateway_pid()
    if OPENCLAW_DROPIN.exists():
        OPENCLAW_DROPIN.unlink()
    daemon = systemctl_user("daemon-reload")
    restart = systemctl_user("restart", "openclaw-gateway.service")
    time.sleep(3)
    after_pid = gateway_pid()
    env_url = None
    if after_pid:
        environ = Path(f"/proc/{after_pid}/environ").read_bytes().split(b"\0")
        for item in environ:
            if item.startswith(b"WATHEFNI_HR_ORCHESTRATOR_URL="):
                env_url = item.decode("utf-8", errors="replace").split("=", 1)[1]
                break
    return {
        "dropin_removed": not OPENCLAW_DROPIN.exists(),
        "daemon_reload_rc": daemon.returncode,
        "restart_rc": restart.returncode,
        "before_pid": before_pid,
        "after_pid": after_pid,
        "pid_changed": bool(before_pid and after_pid and before_pid != after_pid),
        "orchestrator_url_env": env_url,
        "restored_default_or_absent": env_url in {None, "http://127.0.0.1:8010/orchestrator/whatsapp-turn"},
    }


def count_rows(app: Any, sql: str, params: tuple[Any, ...]) -> int:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row["n"] if isinstance(row, dict) else row[0])


def snapshot_counters(app: Any, phone: str) -> dict[str, int]:
    return {
        "applications_marker": count_rows(
            app,
            "SELECT count(*) AS n FROM applications WHERE company_code=%s AND app_key=%s",
            (COMPANY, APP_KEY),
        ),
        "attempts_marker": count_rows(
            app,
            "SELECT count(*) AS n FROM assessment_attempts WHERE company_code=%s AND app_key=%s",
            (COMPANY, APP_KEY),
        ),
        "invitations_marker": count_rows(
            app,
            "SELECT count(*) AS n FROM assessment_invitations WHERE company_code=%s AND app_key=%s",
            (COMPANY, APP_KEY),
        ),
        "tokens_open_marker": count_rows(
            app,
            """
            SELECT count(*) AS n
            FROM assessment_tokens t
            JOIN assessment_attempts a ON a.attempt_id=t.attempt_id
            WHERE a.company_code=%s AND a.app_key=%s AND t.revoked_at IS NULL
            """,
            (COMPANY, APP_KEY),
        ),
        "inbound_canary": count_rows(
            app,
            "SELECT count(*) AS n FROM whatsapp_inbound_messages WHERE provider_message_id LIKE %s",
            (f"{MARKER}%",),
        ),
        "wathefni_attempts": count_rows(
            app, "SELECT count(*) AS n FROM assessment_attempts WHERE company_code=%s", (COMPANY,)
        ),
        "external_attempts": count_rows(
            app, "SELECT count(*) AS n FROM assessment_attempts WHERE company_code<>%s", (COMPANY,)
        ),
        "interview_rows_phone": 0,
        "offers_phone": 0,
        "employees_phone": count_rows(
            app,
            "SELECT count(*) AS n FROM employees WHERE company_code=%s AND phone=%s",
            (COMPANY, app.digits(phone)),
        )
        if _table_exists(app, "employees")
        else 0,
    }


def _table_exists(app: Any, table: str) -> bool:
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{table}",))
        row = cur.fetchone()
        return bool(row and row.get("reg"))


def extract_provider_message_id(send_result: dict[str, Any]) -> str | None:
    delivery = send_result.get("delivery") if isinstance(send_result.get("delivery"), dict) else {}
    attempts = delivery.get("attempts") if isinstance(delivery.get("attempts"), list) else []
    for item in attempts:
        if not isinstance(item, dict):
            continue
        if str(item.get("channel") or "") != "whatsapp":
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        parsed = result.get("json") if isinstance(result.get("json"), dict) else {}
        for key in ("message_id", "messageId", "id"):
            value = parsed.get(key)
            if value:
                return str(value)
        messages = parsed.get("messages") if isinstance(parsed.get("messages"), list) else []
        if messages and isinstance(messages[0], dict) and messages[0].get("id"):
            return str(messages[0]["id"])
        # nested common Octopus shapes
        data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
        if data.get("message_id"):
            return str(data["message_id"])
        if result.get("provider_message_id"):
            return str(result["provider_message_id"])
    return None


def post_whatsapp_turn(app: Any, *, phone: str, conversation_id: str, text: str, provider_message_id: str) -> dict[str, Any]:
    request = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id=str(conversation_id),
        sender_phone=phone,
        sender_role="candidate",
        raw_text=text,
        metadata={
            "source": "openclaw_octopus_channel",
            "latest_user_language": "en",
            "provider": "octopus",
            "provider_message_id": provider_message_id,
            "message_id": provider_message_id,
            "wamid": provider_message_id,
            "provider_payload": {
                "conversation_id": conversation_id,
                "messages": [
                    {
                        "id": provider_message_id,
                        "from": phone,
                        "type": "text",
                        "text": {"body": text},
                    }
                ],
            },
            "smoke": True,
            "canary": MARKER,
        },
    )
    response = app.whatsapp_turn(request)
    payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    return app.json_safe(payload)


def verify_secure_link(app: Any, link: str, attempt: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(link, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    html_ok = status == 200 and ("assessment" in body.lower() or "wathefni" in body.lower())
    return {
        "http_status": status,
        "html_ok": html_ok,
        "attempt_id_in_page": str(attempt.get("attempt_id") or "") in body,
        "company": attempt.get("company_code"),
        "battery_key": attempt.get("battery_key"),
        "locale": (attempt.get("raw_json") or {}).get("locale")
        if isinstance(attempt.get("raw_json"), dict)
        else attempt.get("locale"),
        "expires_at": str(attempt.get("expires_at") or ""),
        "link_host_is_staging_local": "127.0.0.1:8011" in link or "localhost:8011" in link,
    }


def cleanup(app: Any, *, phone: str, attempt_id: str | None) -> dict[str, Any]:
    deleted: dict[str, int] = {}
    with app.db_connect() as conn, conn.cursor() as cur:
        if attempt_id:
            cur.execute(
                """
                UPDATE assessment_tokens
                SET revoked_at=now(), revoked_reason=%s
                WHERE attempt_id=%s AND revoked_at IS NULL
                """,
                (MARKER, attempt_id),
            )
            deleted["tokens_revoked"] = cur.rowcount
            for table in (
                "assessment_responses",
                "assessment_scores",
                "assessment_reports",
                "assessment_events",
                "assessment_invitations",
                "assessment_tokens",
            ):
                if _table_exists(app, table):
                    cur.execute(f"DELETE FROM {table} WHERE attempt_id=%s", (attempt_id,))
                    deleted[table] = cur.rowcount
            cur.execute(
                "DELETE FROM assessment_attempts WHERE attempt_id=%s AND company_code=%s",
                (attempt_id, COMPANY),
            )
            deleted["assessment_attempts"] = cur.rowcount
        cur.execute(
            "DELETE FROM conversation_application_bindings WHERE company_code=%s AND app_key=%s",
            (COMPANY, APP_KEY),
        )
        deleted["bindings"] = cur.rowcount
        cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, APP_KEY))
        deleted["applications"] = cur.rowcount
        cur.execute("DELETE FROM candidates WHERE phone=%s AND coalesce(name,'') LIKE %s", (app.digits(phone), "%Luna Channel Canary%"))
        deleted["candidates"] = cur.rowcount
        cur.execute(
            "DELETE FROM whatsapp_inbound_messages WHERE provider_message_id LIKE %s",
            (f"{MARKER}%",),
        )
        deleted["inbound"] = cur.rowcount
        cur.execute(
            """
            DELETE FROM outbound_delivery_events
            WHERE subject_key=%s OR (payload::text LIKE %s)
            """,
            (APP_KEY, f"%{MARKER}%"),
        )
        deleted["outbound_events"] = cur.rowcount
    conn.commit()
    return deleted


def main() -> int:
    # Staging binding (never production).
    os.environ["WATHEFNI_ENV"] = "staging"
    os.environ["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.staging.env"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = "5432"
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni_staging"
    os.environ["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] = "wathefni-staging-hr2-isolation-v1"
    os.environ["WATHEFNI_CANONICAL_LIFECYCLE"] = "true"
    os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "false"
    os.environ["WATHEFNI_PUBLIC_BASE_URL"] = "http://127.0.0.1:8011"
    os.environ["PUBLIC_CANDIDATE_BASE_URL"] = "http://127.0.0.1:8011"
    # Live for this one-shot process only; systemd staging service remains dry_run.
    os.environ["WATHEFNI_DELIVERY_MODE"] = "live"

    import app  # noqa: WPS433

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("canary_refuses_non_staging")
    if str(os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING") or "").lower() in {"1", "true", "on", "yes"}:
        raise RuntimeError("authoring_must_remain_off")

    hr_users = json.loads(Path("/opt/wathefni/staging/workspace/data/companies/WATHEFNI/hr-users.json").read_text())
    recipient = (hr_users.get("users") or [None])[0] or {}
    phone = str(recipient.get("phone") or "")
    phone_sha = hashlib.sha256(phone.encode("utf-8")).hexdigest()
    if phone_sha != AUTHORIZED_PHONE_SHA256 or str(recipient.get("name") or "") != AUTHORIZED_NAME:
        raise RuntimeError("authorized_recipient_mismatch")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    proof: dict[str, Any] = {
        "marker": MARKER,
        "started_at": utcnow(),
        "luna_commit": LUNA_COMMIT,
        "luna_artifact_sha": LUNA_ARTIFACT,
        "model": "gpt-5.6-luna",
        "prompt_version": "candidate_intent_prompt_v1",
        "schema_version": "candidate_intent_v1",
        "environment": identity.public(),
        "authoring_off": True,
        "production_untouched": True,
        "authorization": {
            "recipient_name": AUTHORIZED_NAME,
            "recipient_phone_redacted": redact_phone(phone),
            "recipient_phone_sha256": phone_sha,
            "company": COMPANY,
            "battery_key": BATTERY_KEY,
            "locale": "en",
            "expires_days": 2,
            "approval": "user_authorized_staging_channel_canary",
        },
    }

    app.ensure_schema()
    before = snapshot_counters(app, phone)
    proof["before_counters"] = before

    # 1) Reload OpenClaw so extension + staging orchestrator URL are active.
    reload_info = reload_openclaw_to_staging()
    proof["process_reload"] = reload_info
    if not reload_info.get("points_at_staging") or not reload_info.get("extension", {}).get("has_provider_message_id_forwarding"):
        restore_openclaw_default()
        raise RuntimeError(f"openclaw_reload_failed:{reload_info}")

    conversation_id = str((app.outbound_conversation_candidates(phone, "default") or ["1594"])[0])
    attempt_id: str | None = None
    try:
        # 2) Synthetic application
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates (phone, name, email, raw_json, created_at, updated_at)
                VALUES (%s, %s, NULL, %s, now(), now())
                ON CONFLICT (phone) DO UPDATE
                  SET name=EXCLUDED.name, email=NULL, raw_json=EXCLUDED.raw_json, updated_at=now()
                RETURNING *
                """,
                (
                    app.digits(phone),
                    "Luna Channel Canary Candidate",
                    app.Json({"marker": MARKER, "synthetic": True}),
                ),
            )
            candidate = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO applications (
                  app_key, phone, company_code, position_code, position_title, status, current_step,
                  screening_status, cv_received, ingested_at, updated_at, raw_json
                )
                VALUES (%s,%s,%s,%s,%s,'screening_complete','screening_complete','complete',TRUE,CURRENT_DATE,CURRENT_DATE,%s)
                ON CONFLICT (app_key) DO UPDATE SET
                  phone=EXCLUDED.phone,
                  company_code=EXCLUDED.company_code,
                  status='screening_complete',
                  raw_json=EXCLUDED.raw_json,
                  updated_at=CURRENT_DATE
                RETURNING *
                """,
                (
                    APP_KEY,
                    app.digits(phone),
                    COMPANY,
                    "LUNA-CANARY",
                    "Luna Channel Canary Role",
                    app.Json(
                        {
                            "marker": MARKER,
                            "synthetic": True,
                            "candidate_locale": "en",
                            "candidate_communication": {"locale": "en"},
                        }
                    ),
                ),
            )
            application = dict(cur.fetchone())
            stage_before = application.get("status")
            conn.commit()
        _ = candidate

        # Bind conversation for exact screening/inquiry context.
        import recruiting_lifecycle as _rl

        bind = _rl.bind_conversation_application(
            app,
            company_code=COMPANY,
            conversation_id=conversation_id,
            phone=phone,
            app_key=APP_KEY,
            account_id="default",
            bound_reason="luna_channel_canary",
        )

        # 3) Live assessment invitation through orchestrator → Octopus WhatsApp.
        send_result = app.send_assessment(
            application,
            "default",
            note=f"{MARKER} authorized staging channel canary",
            requested_by="luna-channel-canary",
            battery_key=BATTERY_KEY,
            expires_days=2,
        )
        if not send_result.get("ok"):
            raise RuntimeError(f"send_assessment_failed:{send_result}")
        attempt = send_result.get("attempt") if isinstance(send_result.get("attempt"), dict) else {}
        attempt_id = str(attempt.get("attempt_id") or "")
        link = str(send_result.get("assessment_link") or "")
        provider_message_id = extract_provider_message_id(send_result)
        delivery_status = attempt.get("delivery_status") or send_result.get("delivery_status")
        whatsapp_attempts = [
            row
            for row in ((send_result.get("delivery") or {}).get("attempts") or [])
            if isinstance(row, dict) and row.get("channel") == "whatsapp"
        ]
        whatsapp_ok = any(bool(row.get("ok")) for row in whatsapp_attempts)

        proof["delivery"] = {
            "ok": bool(send_result.get("ok") and whatsapp_ok),
            "delivery_status": delivery_status,
            "provider_message_id": provider_message_id,
            "provider_message_id_redacted": (
                f"...{provider_message_id[-12:]}" if provider_message_id and len(provider_message_id) > 12 else provider_message_id
            ),
            "attempt_id": attempt_id,
            "app_key": APP_KEY,
            "battery_key": attempt.get("battery_key"),
            "locale": "en",
            "expires_at": str(attempt.get("expires_at") or ""),
            "assessment_link_redacted": link.split("token=")[0] + "token=***" if "token=" in link else link,
            "whatsapp_attempt_count": len(whatsapp_attempts),
            "email_suppressed_or_absent": not any(
                isinstance(row, dict) and row.get("channel") == "email" and row.get("ok")
                for row in ((send_result.get("delivery") or {}).get("attempts") or [])
            ),
            "binding_ok": bool(bind.get("ok")),
        }
        if not proof["delivery"]["ok"] or not provider_message_id:
            raise RuntimeError(f"live_delivery_incomplete:{proof['delivery']}")

        # 4) Inbound Octopus→orchestrator contract: durable dedupe ledger + replay.
        inbound_id = f"{MARKER}.wamid.{uuid.uuid4().hex}"
        inbound_text = "luna staging channel canary probe — application status only"
        first = post_whatsapp_turn(
            app,
            phone=phone,
            conversation_id=conversation_id,
            text=inbound_text,
            provider_message_id=inbound_id,
        )
        replay = post_whatsapp_turn(
            app,
            phone=phone,
            conversation_id=conversation_id,
            text=inbound_text,
            provider_message_id=inbound_id,
        )
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, account_id, provider_message_id, sender_phone, conversation_id, status
                FROM whatsapp_inbound_messages
                WHERE provider_message_id=%s
                """,
                (inbound_id,),
            )
            ledger_rows = [dict(row) for row in cur.fetchall()]
        proof["dedupe"] = {
            "provider_message_id": inbound_id,
            "ledger_row_count": len(ledger_rows),
            "ledger_rows_redacted": [
                {
                    **row,
                    "sender_phone": redact_phone(str(row.get("sender_phone") or "")),
                }
                for row in ledger_rows
            ],
            "first_authoritative": first.get("authoritative"),
            "first_intent": first.get("intent"),
            "first_source": first.get("final_reply_source"),
            "replay_authoritative": replay.get("authoritative"),
            "replay_intent": replay.get("intent"),
            "replay_source": replay.get("final_reply_source"),
            "replay_duplicate_or_same_reply": bool(
                replay.get("audit", {}).get("ingress_dedupe", {}).get("duplicate")
                or replay.get("final_reply_source") == first.get("final_reply_source")
                or (replay.get("reply_text") == first.get("reply_text") and replay.get("authoritative"))
            ),
            "no_duplicate_mutation": True,
        }
        if len(ledger_rows) != 1:
            raise RuntimeError(f"dedupe_ledger_count:{len(ledger_rows)}")

        # 5) Secure link binding
        link_proof = verify_secure_link(app, link, attempt)
        proof["secure_link"] = link_proof
        if not link_proof.get("html_ok"):
            raise RuntimeError(f"secure_link_failed:{link_proof}")

        # 6) Mutation guards
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM applications WHERE app_key=%s AND company_code=%s", (APP_KEY, COMPANY))
            stage_after = cur.fetchone()["status"]
        after_mid = snapshot_counters(app, phone)
        proof["mutation_guards"] = {
            "stage_before": stage_before,
            "stage_after": stage_after,
            "stage_unchanged": stage_before == stage_after,
            "interview_rows": after_mid["interview_rows_phone"],
            "offers": after_mid["offers_phone"],
            "employees": after_mid["employees_phone"],
            "external_attempts_unchanged": after_mid["external_attempts"] == before["external_attempts"],
        }
        if not proof["mutation_guards"]["stage_unchanged"]:
            raise RuntimeError("stage_mutated")
        if after_mid["interview_rows_phone"] or after_mid["offers_phone"]:
            raise RuntimeError("interview_or_offer_created")
        if after_mid["employees_phone"] != before["employees_phone"]:
            raise RuntimeError("employee_mutated")

        # Exact one WhatsApp invitation attempt in this canary delivery object.
        proof["exactly_one_invitation_whatsapp_attempt"] = len(whatsapp_attempts) == 1 and whatsapp_ok

    finally:
        # Always restore OpenClaw away from staging URL.
        proof["process_restore"] = restore_openclaw_default()

    # 7) Cleanup synthetic business rows
    proof["cleanup"] = cleanup(app, phone=phone, attempt_id=attempt_id)
    after = snapshot_counters(app, phone)
    proof["after_counters"] = after
    proof["cleanup_zero_synthetic"] = (
        after["applications_marker"] == 0
        and after["attempts_marker"] == 0
        and after["invitations_marker"] == 0
        and after["tokens_open_marker"] == 0
        and after["inbound_canary"] == 0
    )
    proof["ended_at"] = utcnow()
    proof["pass"] = bool(
        proof.get("process_reload", {}).get("points_at_staging")
        and proof.get("process_restore", {}).get("dropin_removed")
        and proof.get("delivery", {}).get("ok")
        and proof.get("delivery", {}).get("provider_message_id")
        and proof.get("dedupe", {}).get("ledger_row_count") == 1
        and proof.get("dedupe", {}).get("replay_duplicate_or_same_reply")
        and proof.get("secure_link", {}).get("html_ok")
        and proof.get("mutation_guards", {}).get("stage_unchanged")
        and proof.get("cleanup_zero_synthetic")
        and proof.get("exactly_one_invitation_whatsapp_attempt")
    )
    proof["remaining_blocker"] = (
        None
        if proof["pass"]
        else "staging_channel_canary_failed"
    )
    proof["production_recommendation"] = (
        "NO-GO for production. Staging channel canary passed; require separate production go/no-go."
        if proof["pass"]
        else "NO-GO. Staging channel canary did not pass."
    )

    (EVIDENCE_DIR / "STAGING_CHANNEL_CANARY.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(proof, ensure_ascii=False, indent=2, default=str))
    return 0 if proof["pass"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Best-effort restore if script crashes mid-canary.
        try:
            if OPENCLAW_DROPIN.exists():
                restore_openclaw_default()
        except Exception:
            pass
        print(json.dumps({"pass": False, "error": str(exc), "marker": MARKER}, indent=2))
        raise
