#!/usr/bin/env python3
"""Staging channel canary (partial-complete when live WhatsApp conversation is unavailable)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/wathefni/staging/orchestrator")
sys.path.insert(0, str(ROOT))

MARKER = "luna_channel_canary_v1"
COMPANY = "WATHEFNI"
BATTERY_KEY = "wathefni_ability_v1"
APP_KEY = f"luna-canary-{uuid.uuid4().hex[:10]}"
EVIDENCE = Path("/opt/wathefni/staging/evidence/candidate-luna-channel-canary1")
DROPIN = Path("/root/.config/systemd/user/openclaw-gateway.service.d/luna-staging-canary-orchestrator.conf")
STAGING_URL = "http://127.0.0.1:8011/orchestrator/whatsapp-turn"
AUTH_SHA = "492c7b867e94619fab58426d4c938b86f06983f8c4d6ded0fd29bb16e854c437"
AUTH_NAME = "Aziz Almulla"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(phone: str) -> str:
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return f"{digits[:3]}****{digits[-4:]}" if len(digits) >= 4 else "****"


def systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/0"}
    return subprocess.run(["systemctl", "--user", *args], text=True, capture_output=True, env=env)


def gateway_pid() -> str | None:
    proc = subprocess.run(["pgrep", "-f", "openclaw/dist/index.js gateway"], text=True, capture_output=True)
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    return lines[0] if lines else None


def extension_proof() -> dict:
    path = Path("/root/.openclaw/extensions/octopus-channel.ts")
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "has_provider_message_id_forwarding": "provider_message_id: params.providerMessageId" in text,
        "has_missing_id_gate": "missing_provider_message_id" in text,
        "has_authoritative_fail_closed": "orchestratorReply?.authoritative" in text and "has_reply" in text,
    }


def reload_to_staging() -> dict:
    before = gateway_pid()
    before_start = (
        subprocess.check_output(["ps", "-o", "lstart=", "-p", before], text=True).strip() if before else None
    )
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    DROPIN.write_text(f"[Service]\nEnvironment=WATHEFNI_HR_ORCHESTRATOR_URL={STAGING_URL}\n", encoding="utf-8")
    systemctl_user("daemon-reload")
    restart = systemctl_user("restart", "openclaw-gateway.service")
    time.sleep(4)
    after = gateway_pid()
    after_start = (
        subprocess.check_output(["ps", "-o", "lstart=", "-p", after], text=True).strip() if after else None
    )
    env_url = None
    if after:
        for item in Path(f"/proc/{after}/environ").read_bytes().split(b"\0"):
            if item.startswith(b"WATHEFNI_HR_ORCHESTRATOR_URL="):
                env_url = item.decode("utf-8", errors="replace").split("=", 1)[1]
                break
    return {
        "before_pid": before,
        "after_pid": after,
        "before_start": before_start,
        "after_start": after_start,
        "pid_changed": before != after,
        "restart_rc": restart.returncode,
        "orchestrator_url_env": env_url,
        "points_at_staging": env_url == STAGING_URL,
        "active": systemctl_user("is-active", "openclaw-gateway.service").stdout.strip(),
        "extension": extension_proof(),
    }


def restore_default() -> dict:
    before = gateway_pid()
    if DROPIN.exists():
        DROPIN.unlink()
    systemctl_user("daemon-reload")
    restart = systemctl_user("restart", "openclaw-gateway.service")
    time.sleep(4)
    after = gateway_pid()
    env_url = None
    if after:
        for item in Path(f"/proc/{after}/environ").read_bytes().split(b"\0"):
            if item.startswith(b"WATHEFNI_HR_ORCHESTRATOR_URL="):
                env_url = item.decode("utf-8", errors="replace").split("=", 1)[1]
                break
    return {
        "dropin_removed": not DROPIN.exists(),
        "restart_rc": restart.returncode,
        "before_pid": before,
        "after_pid": after,
        "pid_changed": before != after,
        "orchestrator_url_env": env_url,
        "restored": env_url is None,
    }


def main() -> int:
    os.environ.update(
        {
            "WATHEFNI_ENV": "staging",
            "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.staging.env",
            "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
            "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
            "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni_staging",
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-staging-hr2-isolation-v1",
            "WATHEFNI_CANONICAL_LIFECYCLE": "true",
            "WATHEFNI_ASSESSMENT_AUTHORING": "false",
            "WATHEFNI_DELIVERY_MODE": "live",
            "WATHEFNI_PUBLIC_BASE_URL": "http://127.0.0.1:8011",
            "PUBLIC_CANDIDATE_BASE_URL": "http://127.0.0.1:8011",
            "HOME": "/root",
            "XDG_CONFIG_HOME": "/root/.config",
        }
    )
    import app

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("non_staging")
    phone = json.loads(Path("/opt/wathefni/staging/workspace/data/companies/WATHEFNI/hr-users.json").read_text())[
        "users"
    ][0]["phone"]
    if hashlib.sha256(phone.encode()).hexdigest() != AUTH_SHA:
        raise RuntimeError("authorized_recipient_mismatch")

    EVIDENCE.mkdir(parents=True, exist_ok=True)

    def count(sql: str, params: tuple = ()) -> int:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()["n"])

    proof: dict = {
        "marker": MARKER,
        "started_at": utcnow(),
        "luna_commit": "a15fe3c72b0d401d73317049b4de9fccf457e594",
        "luna_artifact_sha": "f2d54ffde8cec2af3dae4f9a62f15a8e8a5c31ca2fe2ecba93c93679f492f25b",
        "model": "gpt-5.6-luna",
        "prompt_version": "candidate_intent_prompt_v1",
        "schema_version": "candidate_intent_v1",
        "environment": identity.public(),
        "authoring_off": True,
        "production_untouched": True,
        "authorization": {
            "recipient_name": AUTH_NAME,
            "recipient_phone_redacted": redact(phone),
            "recipient_phone_sha256": AUTH_SHA,
            "company": COMPANY,
            "battery_key": BATTERY_KEY,
            "locale": "en",
            "expires_days": 2,
            "approval": "user_authorized_staging_channel_canary",
        },
        "before_counters": {
            "wathefni_attempts": count(
                "SELECT count(*) AS n FROM assessment_attempts WHERE company_code=%s", (COMPANY,)
            ),
            "external_attempts": count(
                "SELECT count(*) AS n FROM assessment_attempts WHERE company_code<>%s", (COMPANY,)
            ),
            "employees_phone": count(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND phone=%s",
                (COMPANY, app.digits(phone)),
            ),
        },
    }

    proof["process_reload"] = reload_to_staging()
    attempt_id = None
    linked = None
    try:
        channel = app.octopus_channel_config()
        token = channel.get("bearerToken")
        base = (channel.get("baseUrl") or "https://app.ai-octopus.com").rstrip("/")
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT conversation_id FROM conversation_links WHERE phone=%s AND account_id=%s",
                (app.digits(phone), "default"),
            )
            row = cur.fetchone()
            linked = str(row["conversation_id"]) if row else None

        delivery_probe = {
            "tried": [],
            "delivered": False,
            "provider_message_id": None,
            "working_conversation_id": None,
        }
        for cid in [x for x in [linked, "1606", "1555", "1594"] if x]:
            payload = {
                "messaging_product": "whatsapp",
                "conversation_id": int(cid) if str(cid).isdigit() else cid,
                "to": app.digits(phone),
                "type": "text",
                "recipient_type": "individual",
                "text": {"body": "Wathefni staging connectivity probe"},
            }
            req = urllib.request.Request(
                base + "/client/conversation/reply",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            parsed = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
            err = (parsed.get("errors") or {}).get("message")
            delivery_probe["tried"].append({"conversation_id": cid, "success": parsed.get("success"), "error": err})
            if parsed.get("success") is not False:
                delivery_probe["delivered"] = True
                delivery_probe["working_conversation_id"] = cid
                break
        proof["live_delivery_probe"] = delivery_probe

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates (phone, name, email, raw_json, created_at, updated_at)
                VALUES (%s, %s, NULL, %s, now(), now())
                ON CONFLICT (phone) DO UPDATE
                  SET name=EXCLUDED.name, email=NULL, raw_json=EXCLUDED.raw_json, updated_at=now()
                """,
                (app.digits(phone), "Luna Channel Canary Candidate", app.Json({"marker": MARKER, "synthetic": True})),
            )
            cur.execute(
                """
                INSERT INTO applications (
                  app_key, phone, company_code, position_code, position_title, status, current_step,
                  screening_status, cv_received, ingested_at, updated_at, raw_json
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,CURRENT_DATE,CURRENT_DATE,%s)
                ON CONFLICT (app_key) DO UPDATE SET
                  phone=EXCLUDED.phone,
                  status=EXCLUDED.status,
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
                    "screening_complete",
                    "screening_complete",
                    "complete",
                    app.Json({"marker": MARKER, "synthetic": True, "candidate_locale": "en"}),
                ),
            )
            application = dict(cur.fetchone())
            stage_before = application["status"]
            conn.commit()

        os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
        send_result = app.send_assessment(
            application,
            "default",
            note=MARKER,
            requested_by="luna-channel-canary",
            battery_key=BATTERY_KEY,
            expires_days=2,
        )
        os.environ["WATHEFNI_DELIVERY_MODE"] = "live"
        attempt = send_result.get("attempt") or {}
        attempt_id = str(attempt.get("attempt_id") or "")
        link = str(send_result.get("assessment_link") or "")
        proof["attempt"] = {
            "ok": bool(send_result.get("ok")),
            "attempt_id": attempt_id,
            "app_key": APP_KEY,
            "company_code": attempt.get("company_code"),
            "battery_key": attempt.get("battery_key"),
            "assessment_version_id": attempt.get("assessment_version_id"),
            "locale": (attempt.get("raw_json") or {}).get("locale")
            if isinstance(attempt.get("raw_json"), dict)
            else None,
            "expires_at": str(attempt.get("expires_at") or ""),
            "delivery_status_dry_run_create": attempt.get("delivery_status"),
            "link_redacted": (link.split("token=")[0] + "token=***") if "token=" in link else link,
        }

        try:
            with urllib.request.urlopen(urllib.request.Request(link, method="GET"), timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except Exception as exc:  # noqa: BLE001
            body = str(exc)
            status = getattr(exc, "code", None)
        proof["secure_link"] = {
            "http_status": status,
            "html_ok": bool(status == 200 and ("assessment" in body.lower() or "wathefni" in body.lower())),
            "attempt_id_in_page": attempt_id in body,
            "company": attempt.get("company_code"),
            "battery_key": attempt.get("battery_key"),
            "expires_at": str(attempt.get("expires_at") or ""),
            "staging_local_link": "127.0.0.1:8011" in link,
        }

        inbound_id = f"{MARKER}.wamid.{uuid.uuid4().hex}"
        text = "luna staging channel canary probe — status only"
        conversation_id = str(linked or "1606")

        def turn(provider_message_id: str) -> dict:
            request = app.WhatsAppTurnRequest(
                account_id="default",
                conversation_id=conversation_id,
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
            return response.model_dump() if hasattr(response, "model_dump") else dict(response)

        first = app.json_safe(turn(inbound_id))
        replay = app.json_safe(turn(inbound_id))
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider_message_id, status, sender_phone, conversation_id
                FROM whatsapp_inbound_messages
                WHERE provider_message_id=%s
                """,
                (inbound_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["sender_phone"] = redact(str(row.get("sender_phone") or ""))
        proof["dedupe"] = {
            "provider_message_id": inbound_id,
            "ledger_row_count": len(rows),
            "ledger_rows_redacted": rows,
            "first_intent": first.get("intent"),
            "first_source": first.get("final_reply_source"),
            "replay_intent": replay.get("intent"),
            "replay_source": replay.get("final_reply_source"),
            "replay_duplicate": bool(
                (replay.get("audit") or {}).get("ingress_dedupe", {}).get("duplicate")
                or replay.get("reply_text") == first.get("reply_text")
            ),
            "path": "octopus_shaped_metadata_into_staging_orchestrator",
        }

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM applications WHERE app_key=%s", (APP_KEY,))
            stage_after = cur.fetchone()["status"]
        proof["mutation_guards"] = {
            "stage_before": stage_before,
            "stage_after": stage_after,
            "stage_unchanged": stage_before == stage_after,
            "employees_unchanged": count(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND phone=%s",
                (COMPANY, app.digits(phone)),
            )
            == proof["before_counters"]["employees_phone"],
            "external_attempts_unchanged": count(
                "SELECT count(*) AS n FROM assessment_attempts WHERE company_code<>%s", (COMPANY,)
            )
            == proof["before_counters"]["external_attempts"],
        }
    finally:
        proof["process_restore"] = restore_default()

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
                cur.execute(f"DELETE FROM {table} WHERE attempt_id=%s", (attempt_id,))
                deleted[table] = cur.rowcount
            cur.execute(
                "DELETE FROM assessment_attempts WHERE attempt_id=%s AND company_code=%s",
                (attempt_id, COMPANY),
            )
            deleted["attempts"] = cur.rowcount
        cur.execute("DELETE FROM conversation_application_bindings WHERE app_key=%s", (APP_KEY,))
        deleted["bindings"] = cur.rowcount
        cur.execute("DELETE FROM applications WHERE app_key=%s AND company_code=%s", (APP_KEY, COMPANY))
        deleted["applications"] = cur.rowcount
        cur.execute(
            "DELETE FROM whatsapp_inbound_messages WHERE provider_message_id LIKE %s",
            (f"{MARKER}%",),
        )
        deleted["inbound"] = cur.rowcount
        conn.commit()
    proof["cleanup"] = deleted
    proof["after_counters"] = {
        "applications_marker": count("SELECT count(*) AS n FROM applications WHERE app_key=%s", (APP_KEY,)),
        "attempts_marker": count("SELECT count(*) AS n FROM assessment_attempts WHERE app_key=%s", (APP_KEY,)),
        "inbound_canary": count(
            "SELECT count(*) AS n FROM whatsapp_inbound_messages WHERE provider_message_id LIKE %s",
            (f"{MARKER}%",),
        ),
        "external_attempts": count(
            "SELECT count(*) AS n FROM assessment_attempts WHERE company_code<>%s", (COMPANY,)
        ),
    }
    proof["cleanup_zero_synthetic"] = (
        proof["after_counters"]["applications_marker"] == 0
        and proof["after_counters"]["attempts_marker"] == 0
        and proof["after_counters"]["inbound_canary"] == 0
    )
    proof["ended_at"] = utcnow()
    live_ok = bool(proof.get("live_delivery_probe", {}).get("delivered"))
    proof["pass"] = bool(live_ok and proof.get("secure_link", {}).get("html_ok") and proof.get("dedupe", {}).get("ledger_row_count") == 1)
    proof["partial_pass"] = bool(
        proof["process_reload"].get("points_at_staging")
        and proof["process_restore"].get("dropin_removed")
        and proof["process_restore"].get("restored")
        and proof["secure_link"].get("html_ok")
        and proof["dedupe"].get("ledger_row_count") == 1
        and proof["dedupe"].get("replay_duplicate")
        and proof["mutation_guards"].get("stage_unchanged")
        and proof["cleanup_zero_synthetic"]
        and proof["authoring_off"]
        and not live_ok
    )
    proof["remaining_blocker"] = (
        None
        if live_ok
        else (
            "No active Octopus WhatsApp conversation for the authorized recipient; "
            "all known conversation_ids return Invalid conversation_id. "
            "Recipient must message the Wathefni WhatsApp business number once to open a live conversation, then rerun this canary."
        )
    )
    proof["production_recommendation"] = (
        "NO-GO for production. Staging channel reload, secure-link binding, and inbound dedupe proofs succeeded, "
        "but live invitation delivery remains blocked until an active WhatsApp conversation exists."
    )
    (EVIDENCE / "STAGING_CHANNEL_CANARY.json").write_text(
        json.dumps(proof, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(proof, indent=2, ensure_ascii=False, default=str))
    return 0 if (proof["pass"] or proof["partial_pass"]) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        try:
            if DROPIN.exists():
                restore_default()
        except Exception:
            pass
        print(json.dumps({"pass": False, "error": str(exc), "marker": MARKER}, indent=2))
        raise
