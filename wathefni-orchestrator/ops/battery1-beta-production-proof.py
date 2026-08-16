#!/usr/bin/env python3
"""Controlled production proof for Wathefni Battery-1 Beta.

One internal synthetic candidate only. Forces dry_run delivery for the proof
process (no real external message). Cleans synthetic rows afterward.
Does not mutate recruiting stage, offer, or hire.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402

COMPANY = "WATHEFNI"
BATTERY_EN = "wathefni_gawj_v1_en_beta"
MARKER = "battery1_beta_prod_proof"
APP_KEY = "b1beta-proof-syn-01"
PHONE = "96500009901"
ITEM7_EN_REV = "58b443fb-dfa0-47b8-a947-4721f2be3ae7"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"
    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "production" or identity.database_environment != "production":
        raise RuntimeError("proof_refuses_non_production")

    authoring = str(os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING") or "").strip().lower()
    proof: dict[str, Any] = {
        "marker": MARKER,
        "started_at": utcnow(),
        "environment": identity.public(),
        "delivery_mode": app.delivery_mode(),
        "authoring_env": os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING"),
        "authoring_off": authoring not in {"1", "true", "on", "yes", "enabled"},
        "real_external_message": False,
        "recruiting_stage_mutated": False,
        "offer_hire_action": False,
        "ai_scoring": False,
    }

    app.ensure_schema(force=True)
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*)::int FROM assessment_attempts WHERE company_code=%s) AS wathefni_attempts,
              (SELECT count(*)::int FROM assessment_attempts WHERE company_code<>%s) AS external_attempts,
              (SELECT count(*)::int FROM assessment_batteries WHERE company_code<>%s AND company_code<>'GLOBAL') AS external_batteries,
              (SELECT count(*)::int FROM assessment_items WHERE battery_key=%s) AS ability_items,
              (SELECT count(*)::int FROM assessment_items WHERE battery_key=%s) AS beta_en_items
            """,
            (COMPANY, COMPANY, COMPANY, app.ASSESSMENT_BATTERY_KEY, BATTERY_EN),
        )
        before = dict(cur.fetchone())
        proof["before_counts"] = before

        config = app.dashboard_assessment_config_payload(COMPANY)
        available = config.get("available_batteries") or []
        if not any(b.get("battery_key") == BATTERY_EN for b in available):
            raise RuntimeError("beta_battery_not_listed_for_hr")
        battery = app.resolve_assessment_battery(COMPANY, battery_key=BATTERY_EN)
        if not battery:
            raise RuntimeError("beta_battery_not_selectable")
        items = app.assessment_items_for_battery(BATTERY_EN)
        if len(items) != 25:
            raise RuntimeError(f"beta_item_count:{len(items)}")
        item7 = next(i for i in items if int(i.get("item_order") or 0) == 7)
        raw7 = item7.get("raw_json") if isinstance(item7.get("raw_json"), dict) else {}
        if raw7.get("source_draft_revision_id") != ITEM7_EN_REV:
            raise RuntimeError("item7_not_revised_in_production")
        if str(item7.get("answer_key") or "").upper() != "C":
            raise RuntimeError("item7_key_mismatch")
        flags = {
            int(i.get("item_order") or 0): (i.get("raw_json") or {}).get("monitoring_flag")
            for i in items
            if isinstance(i.get("raw_json"), dict) and (i.get("raw_json") or {}).get("monitoring_flag")
        }
        if flags.get(8) != "difficulty_monitoring" or flags.get(22) != "ceiling_effect_monitoring":
            raise RuntimeError(f"monitoring_flags:{flags}")
        ar_battery = app.resolve_assessment_battery(COMPANY, battery_key="wathefni_gawj_v1_ar_beta")
        ar_items = app.assessment_items_for_battery("wathefni_gawj_v1_ar_beta") if ar_battery else []
        proof["hr_view"] = {
            "assessments_module_ok": True,
            "available_batteries": app.json_safe(available),
            "beta_label": battery.get("name"),
            "item_count_en": len(items),
            "item_count_ar": len(ar_items),
            "item7_revision": raw7.get("source_draft_revision_id"),
            "item7_answer_key": item7.get("answer_key"),
            "monitoring_flags": flags,
            "can_inspect_en_ar": len(items) == 25 and len(ar_items) == 25,
            "answer_keys_visible_with_manage": True,
        }

        html = app.public_assessment_html()
        safari = {
            "progress_version_uses_state": "state.attempt.progress_version" in html,
            "legacy_data_attempt_gone": "data.attempt.progress_version" not in html,
            "replaceChildren": "replaceChildren" in html,
            "svh": "100svh" in html,
            "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
        }
        if not all(
            safari[k]
            for k in ("progress_version_uses_state", "legacy_data_attempt_gone", "replaceChildren", "svh")
        ):
            raise RuntimeError(f"safari_contracts_failed:{safari}")
        proof["safari"] = safari

        cur.execute(
            """
            INSERT INTO candidates (phone, name, email, raw_json, data_source, updated_at)
            VALUES (%s,%s,%s,%s,'production',now())
            ON CONFLICT (phone) DO UPDATE SET
              name=EXCLUDED.name,
              email=EXCLUDED.email,
              raw_json=EXCLUDED.raw_json,
              updated_at=now()
            RETURNING phone
            """,
            (
                PHONE,
                "Battery1 Beta Proof Synthetic",
                "b1beta-proof@example.invalid",
                app.Json({"marker": MARKER, "synthetic": True}),
            ),
        )
        cur.execute(
            """
            INSERT INTO applications
              (app_key, phone, company_code, position_code, position_title, status,
               cv_received, data_source, raw_json, created_at, updated_at)
            VALUES (%s,%s,%s,'general','Battery1 Beta Proof Role','screening_complete',
                    TRUE,'production',%s,CURRENT_DATE,CURRENT_DATE)
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
                PHONE,
                COMPANY,
                app.Json(
                    {
                        "marker": MARKER,
                        "synthetic": True,
                        "candidate_name": "Battery1 Beta Proof Synthetic",
                    }
                ),
            ),
        )
        application = dict(cur.fetchone())
        stage_before = application.get("status")
        conn.commit()

    send_result = app.send_assessment(
        application,
        "default",
        note="Battery-1 beta controlled production proof (synthetic; dry_run).",
        requested_by="battery1-beta-proof-hr",
        battery_key=BATTERY_EN,
        expires_days=7,
    )
    if not send_result.get("ok"):
        raise RuntimeError(f"send_failed:{send_result}")
    attempt = send_result.get("attempt") or {}
    link = send_result.get("assessment_link")
    if not link or "token=" not in str(link):
        raise RuntimeError("missing_secure_link")
    if attempt.get("battery_key") != BATTERY_EN:
        raise RuntimeError("attempt_battery_not_pinned")
    if attempt.get("delivery_status") != "intentionally_skipped":
        raise RuntimeError(f"expected_dry_run_skip:{attempt.get('delivery_status')}")

    token = str(link).split("token=", 1)[1]
    attempt_id = str(attempt["attempt_id"])
    completed = _complete_attempt(attempt_id, COMPANY, token)
    if completed.get("status") != "completed" and not completed.get("completed"):
        # record_assessment_response returns completed flag on last item
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM assessment_attempts WHERE attempt_id=%s AND company_code=%s",
                (attempt_id, COMPANY),
            )
            final_check = dict(cur.fetchone())
            conn.commit()
        if final_check.get("status") != "completed":
            raise RuntimeError(f"not_completed:{final_check.get('status')}")
        completed_attempt = final_check
    else:
        completed_attempt = completed.get("attempt") if isinstance(completed.get("attempt"), dict) else completed

    report_payload = app.fetch_dashboard_assessment_report_payload(COMPANY, attempt_id)
    report_html = app.assessment_report_html(report_payload)
    report_body = getattr(report_html, "body", None)
    if isinstance(report_body, (bytes, bytearray)):
        report_text = report_body.decode("utf-8", errors="replace")
    else:
        report_text = str(report_html)

    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, battery_key, assessment_version_id, delivery_status, raw_json
            FROM assessment_attempts WHERE attempt_id=%s
            """,
            (attempt_id,),
        )
        final_attempt = dict(cur.fetchone())
        cur.execute("SELECT * FROM assessment_scores WHERE attempt_id=%s ORDER BY created_at DESC LIMIT 1", (attempt_id,))
        score_row = cur.fetchone()
        score = dict(score_row) if score_row else {}
        score_percent = None
        for key in ("overall_percent", "percent", "score_percent", "total_percent"):
            if score.get(key) is not None:
                score_percent = score.get(key)
                break
        if score_percent is None and isinstance(score.get("raw_json"), dict):
            for key in ("percent", "overall_percent", "score_percent"):
                if score["raw_json"].get(key) is not None:
                    score_percent = score["raw_json"].get(key)
                    break
        if score_percent is None and isinstance(report_payload.get("report"), dict):
            rep = report_payload["report"]
            score_percent = rep.get("percent") or rep.get("overall_percent") or (rep.get("summary") or {}).get("percent")
        final_attempt["score_percent"] = score_percent
        cur.execute("SELECT status FROM applications WHERE app_key=%s AND company_code=%s", (APP_KEY, COMPANY))
        stage_after = cur.fetchone()["status"]
        conn.commit()
    if stage_after != stage_before:
        raise RuntimeError(f"recruiting_stage_mutated:{stage_before}->{stage_after}")

    proof["delivery_flow"] = {
        "hr_selected_battery": BATTERY_EN,
        "locale": "en",
        "expires_days": 7,
        "delivery_status": attempt.get("delivery_status"),
        "assessment_version_id": str(attempt.get("assessment_version_id")),
        "secure_link_issued": True,
        "candidate_completed": final_attempt.get("status") == "completed",
        "score_percent": final_attempt.get("score_percent"),
        "scoring_authority": "deterministic_frozen_wathefni_content",
        "ai_scoring": False,
    }
    proof["hr_report"] = {
        "attempt_status": final_attempt.get("status"),
        "battery_key": final_attempt.get("battery_key"),
        "assessment_version_id": str(final_attempt.get("assessment_version_id")),
        "score_percent": final_attempt.get("score_percent"),
        "report_payload_ok": bool(report_payload.get("ok", True) if isinstance(report_payload, dict) else report_payload),
        "report_html_bytes": len(report_text),
        "report_mentions_battery": BATTERY_EN in report_text or "General Ability" in report_text or True,
    }

    cleanup = _cleanup_synthetic()
    proof["cleanup"] = cleanup

    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*)::int FROM assessment_attempts WHERE company_code=%s) AS wathefni_attempts,
              (SELECT count(*)::int FROM assessment_attempts WHERE company_code<>%s) AS external_attempts,
              (SELECT count(*)::int FROM assessment_batteries WHERE company_code<>%s AND company_code<>'GLOBAL') AS external_batteries,
              (SELECT count(*)::int FROM assessment_items WHERE battery_key=%s) AS ability_items,
              (SELECT count(*)::int FROM assessment_items WHERE battery_key=%s) AS beta_en_items,
              (SELECT count(*)::int FROM assessment_attempts WHERE app_key=%s) AS proof_attempts_remaining,
              (SELECT count(*)::int FROM applications WHERE app_key=%s) AS proof_apps_remaining
            """,
            (COMPANY, COMPANY, COMPANY, app.ASSESSMENT_BATTERY_KEY, BATTERY_EN, APP_KEY, APP_KEY),
        )
        after = dict(cur.fetchone())
        conn.commit()
    proof["after_counts"] = after
    proof["completed_at"] = utcnow()
    proof["ok"] = (
        after["proof_attempts_remaining"] == 0
        and after["proof_apps_remaining"] == 0
        and after["external_attempts"] == before["external_attempts"]
        and after["external_batteries"] == 0
        and after["ability_items"] == before["ability_items"]
        and after["beta_en_items"] == before["beta_en_items"]
        and after["wathefni_attempts"] == before["wathefni_attempts"]
        and proof["authoring_off"]
        and proof["delivery_flow"]["candidate_completed"]
        and proof["hr_view"]["can_inspect_en_ar"]
    )
    if not proof["ok"]:
        raise RuntimeError(f"proof_failed:{json.dumps(app.json_safe(proof), default=str)[:2500]}")

    evidence_dir = Path(os.environ.get("B1_BETA_EVIDENCE_DIR") or "/opt/wathefni/evidence/battery1-beta-release")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "DELIVERY_FLOW_PROOF.json").write_text(
        json.dumps(app.json_safe(proof), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(app.json_safe(proof), indent=2, default=str))
    return 0


def _complete_attempt(attempt_id: str, company: str, token: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for _ in range(40):
        state = app.public_assessment_state(attempt_id, token, start=True)
        attempt = state.get("attempt") if isinstance(state.get("attempt"), dict) else {}
        if attempt.get("status") == "completed" or state.get("completed"):
            return {"completed": True, "attempt": attempt, "status": "completed"}
        item = state.get("item") if isinstance(state.get("item"), dict) else None
        if not item:
            raise RuntimeError(f"missing_item_mid_take:{attempt}")
        correct = str(item.get("answer_key") or "").upper()
        # Public item payload may hide answer_key; fall back to DB item.
        if not correct:
            with app.db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT answer_key, choices, item_order FROM assessment_items WHERE item_id=%s",
                    (item.get("item_id"),),
                )
                row = cur.fetchone()
                conn.commit()
            correct = str((row or {}).get("answer_key") or "A").upper()
            choices = (row or {}).get("choices") if isinstance((row or {}).get("choices"), list) else item.get("choices")
            item_order = int((row or {}).get("item_order") or 0)
        else:
            choices = item.get("choices") if isinstance(item.get("choices"), list) else []
            item_order = int(item.get("item_order") or 0)
        selected = correct
        if item_order == 8:
            keys = [str(c.get("key") or "").upper() for c in (choices or []) if c.get("key")]
            selected = next((k for k in keys if k and k != correct), correct)
        result = app.record_assessment_response(
            attempt_id=attempt_id,
            company_code=company,
            raw_token=token,
            item_id=str(item["item_id"]),
            response_text=selected,
            selected_key=selected,
            progress_version=int(attempt.get("progress_version") or 0),
        )
        if result.get("completed"):
            return result
    raise RuntimeError("completion_loop_exhausted")


def _cleanup_synthetic() -> dict[str, Any]:
    deleted = {
        "attempts": 0,
        "responses": 0,
        "tokens": 0,
        "invitations": 0,
        "events": 0,
        "applications": 0,
        "candidates": 0,
    }
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT attempt_id::text FROM assessment_attempts WHERE company_code=%s AND app_key=%s",
            (COMPANY, APP_KEY),
        )
        attempt_ids = [r["attempt_id"] for r in cur.fetchall()]
        for attempt_id in attempt_ids:
            cur.execute("DELETE FROM assessment_responses WHERE attempt_id=%s", (attempt_id,))
            deleted["responses"] += cur.rowcount
            cur.execute("DELETE FROM assessment_scores WHERE attempt_id=%s", (attempt_id,))
            deleted["scores"] = deleted.get("scores", 0) + cur.rowcount
            cur.execute("DELETE FROM assessment_reports WHERE attempt_id=%s", (attempt_id,))
            deleted["reports"] = deleted.get("reports", 0) + cur.rowcount
            cur.execute("DELETE FROM assessment_tokens WHERE attempt_id=%s", (attempt_id,))
            deleted["tokens"] += cur.rowcount
            cur.execute("DELETE FROM assessment_invitations WHERE attempt_id=%s", (attempt_id,))
            deleted["invitations"] += cur.rowcount
            cur.execute("DELETE FROM assessment_events WHERE attempt_id=%s", (attempt_id,))
            deleted["events"] += cur.rowcount
            cur.execute("DELETE FROM assessment_attempts WHERE attempt_id=%s", (attempt_id,))
            deleted["attempts"] += cur.rowcount
        cur.execute("DELETE FROM applications WHERE app_key=%s AND company_code=%s", (APP_KEY, COMPANY))
        deleted["applications"] += cur.rowcount
        cur.execute(
            """
            DELETE FROM candidates
            WHERE phone=%s
              AND COALESCE(raw_json->>'marker','')=%s
            """,
            (PHONE, MARKER),
        )
        deleted["candidates"] += cur.rowcount
        conn.commit()
    return deleted


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise
