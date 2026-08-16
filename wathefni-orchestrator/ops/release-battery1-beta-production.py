#!/usr/bin/env python3
"""Two-person, one-shot production release for Wathefni Battery-1 Beta.

Privileged admin command — not an HTTP publish route.

Inserts exact immutable EN/AR item revisions from a signed content pack into the
internal WATHEFNI production tenant only. Idempotent by manifest SHA.

Does not:
  - enable WATHEFNI_ASSESSMENT_AUTHORING
  - insert for external tenants
  - mutate existing assessment attempts
  - replace GLOBAL wathefni_ability_v1 as the default active battery
  - auto shortlist / reject / offer / hire
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import assessment_lifecycle as lifecycle  # noqa: E402
import assessment_service as service  # noqa: E402

EXPECTED_MANIFEST_SHA = "035a12a2e35c487d3588f2d3be8952cd3350f30f2b030cdf3d863c5490e39c62"
RELEASE_KEY = "wathefni_battery1_beta_v1"
CONFIRM_PREFIX = "production:wathefni:battery1_beta:"
COMPANY = "WATHEFNI"
SOURCE_BATTERY_KEY = "wathefni_general_ability_workplace_judgment_v1"
BATTERY_EN = "wathefni_gawj_v1_en_beta"
BATTERY_AR = "wathefni_gawj_v1_ar_beta"
BATTERY_LABEL = "Wathefni General Ability & Workplace Judgment — Beta"
SCORING_VERSION = "wathefni_gawj_deterministic_v1"
REPORT_LOGIC_VERSION = "wathefni_report_v1"
BETA_VERSION = "beta_v1"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha_manifest(body: dict[str, Any]) -> str:
    payload = {k: v for k, v in body.items() if k != "manifest_sha256"}
    return hashlib.sha256(
        (json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n").encode()
    ).hexdigest()


def content_pack_body_sha(pack: dict[str, Any]) -> str:
    payload = {k: v for k, v in pack.items() if k != "content_pack_sha256"}
    return hashlib.sha256(
        (json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n").encode()
    ).hexdigest()


def live_counts(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          (SELECT count(*)::int FROM assessment_batteries) AS batteries,
          (SELECT count(*)::int FROM assessment_items) AS items,
          (SELECT count(*)::int FROM assessment_attempts) AS attempts,
          (SELECT count(*)::int FROM assessment_content_versions) AS versions,
          (SELECT count(*)::int FROM assessment_attempts WHERE company_code=%s) AS wathefni_attempts,
          (SELECT count(*)::int FROM assessment_attempts WHERE company_code<>%s) AS external_attempts,
          (SELECT count(*)::int FROM assessment_batteries WHERE company_code<>%s AND company_code<>'GLOBAL') AS external_batteries,
          (SELECT count(*)::int FROM assessment_items WHERE battery_key=%s) AS ability_v1_items
        """,
        (COMPANY, COMPANY, COMPANY, app.ASSESSMENT_BATTERY_KEY),
    )
    return dict(cur.fetchone())


def ensure_release_table(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assessment_bank_releases (
          release_id uuid PRIMARY KEY,
          release_key text NOT NULL,
          company_code text NOT NULL,
          manifest_sha256 text NOT NULL,
          content_pack_sha256 text NOT NULL,
          status text NOT NULL,
          approver_a text NOT NULL,
          approver_b text NOT NULL,
          battery_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
          version_ids jsonb NOT NULL DEFAULT '{}'::jsonb,
          before_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
          evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, manifest_sha256)
        )
        """
    )


def sections_payload() -> list[dict[str, str]]:
    return [
        {"key": "numerical_reasoning", "label": "Numerical reasoning"},
        {"key": "verbal_reasoning", "label": "Verbal reasoning"},
        {"key": "logical_reasoning", "label": "Logical reasoning"},
        {"key": "situational_judgment", "label": "Situational judgment"},
        {"key": "prioritization", "label": "Prioritization"},
    ]


def insert_locale_battery(
    cur: Any,
    *,
    locale: str,
    battery_key: str,
    pack: dict[str, Any],
    release_id: str,
    manifest_sha: str,
    content_pack_sha: str,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO assessment_batteries
          (battery_key, company_code, name, version, sections, is_active, content_version,
           scoring_rules_json, report_logic_version, raw_json, updated_at)
        VALUES (%s,%s,%s,%s,%s,FALSE,1,%s,%s,%s,now())
        ON CONFLICT (battery_key) DO UPDATE SET
          company_code=EXCLUDED.company_code,
          name=EXCLUDED.name,
          version=EXCLUDED.version,
          sections=EXCLUDED.sections,
          scoring_rules_json=EXCLUDED.scoring_rules_json,
          report_logic_version=EXCLUDED.report_logic_version,
          raw_json=EXCLUDED.raw_json,
          is_active=FALSE,
          retired_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            battery_key,
            COMPANY,
            BATTERY_LABEL,
            BETA_VERSION,
            app.Json(sections_payload()),
            app.Json(
                {
                    "authority": "deterministic_frozen_wathefni_content",
                    "ai_scoring": False,
                    "scoring_version": SCORING_VERSION,
                    "automatic_hiring_actions": False,
                    "scores_are_supporting_evidence_only": True,
                }
            ),
            REPORT_LOGIC_VERSION,
            app.Json(
                {
                    "approved_for_use_status": "approved_for_use_beta",
                    "approved_for_use_beta": True,
                    "approved_for_use": False,
                    "locale": locale,
                    "label": BATTERY_LABEL,
                    "source_battery_key": SOURCE_BATTERY_KEY,
                    "source_manifest_sha256": manifest_sha,
                    "content_pack_sha256": content_pack_sha,
                    "release_id": release_id,
                    "release_key": RELEASE_KEY,
                    "scoring_version": SCORING_VERSION,
                    "scores_are_supporting_evidence_only": True,
                    "no_automatic_shortlist": True,
                    "no_automatic_rejection": True,
                    "no_automatic_offer": True,
                    "no_automatic_hire": True,
                    "selectable_for_hr_send": True,
                    "default_active_battery": False,
                    "monitoring_flags": {
                        "8": "difficulty_monitoring",
                        "22": "ceiling_effect_monitoring",
                    },
                }
            ),
        ),
    )
    battery = dict(cur.fetchone())
    inserted: list[dict[str, Any]] = []
    for item in sorted(pack["items"], key=lambda x: int(x["order"])):
        locale_payload = item["locales"][locale]
        answer_key = str(locale_payload.get("proposed_answer_key") or item.get("answer_key") or "").upper()
        if answer_key != str(item.get("answer_key") or "").upper():
            raise RuntimeError(f"answer_key_drift:{item['order']}:{locale}:{answer_key}")
        scoring = locale_payload.get("compiled_scoring_json")
        if not isinstance(scoring, dict):
            scoring = {"type": "answer_key", "correct": 1.0, "incorrect": 0.0, "max_score": 1.0}
        item_id = f"b1beta_{locale}_{int(item['order']):02d}"
        category = str(item["category"])
        cur.execute(
            """
            INSERT INTO assessment_items
              (item_id, battery_key, section, item_order, prompt_text, choices,
               answer_key, scoring, difficulty, content_version, authoring_status,
               approved_at, retired_at, raw_json, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'approved',now(),NULL,%s,now())
            ON CONFLICT (item_id) DO UPDATE SET
              battery_key=EXCLUDED.battery_key,
              section=EXCLUDED.section,
              item_order=EXCLUDED.item_order,
              prompt_text=EXCLUDED.prompt_text,
              choices=EXCLUDED.choices,
              answer_key=EXCLUDED.answer_key,
              scoring=EXCLUDED.scoring,
              difficulty=EXCLUDED.difficulty,
              authoring_status='approved',
              approved_at=COALESCE(assessment_items.approved_at, now()),
              retired_at=NULL,
              raw_json=EXCLUDED.raw_json,
              updated_at=now()
            RETURNING item_id, item_order, answer_key, section
            """,
            (
                item_id,
                battery_key,
                category,
                int(item["order"]),
                str(locale_payload.get("prompt_text") or ""),
                app.Json(locale_payload.get("choices") or []),
                answer_key,
                app.Json(scoring),
                str(locale_payload.get("difficulty") or "medium"),
                app.Json(
                    {
                        "locale": locale,
                        "source_draft_revision_id": locale_payload["draft_revision_id"],
                        "source_content_sha256": locale_payload["content_sha256"],
                        "source_compiled_scoring_sha256": locale_payload["compiled_scoring_sha256"],
                        "manifest_order": int(item["order"]),
                        "category": category,
                        "translation_pair_id": item["translation_pair_id"],
                        "monitoring_flag": item.get("monitoring_flag"),
                        "rationale": locale_payload.get("rationale"),
                        "explanation": locale_payload.get("explanation"),
                        "immutable_pin": True,
                        "release_id": release_id,
                        "manifest_sha256": manifest_sha,
                    }
                ),
            ),
        )
        inserted.append(dict(cur.fetchone()))

    # Temporarily activate to freeze; deactivate after so GLOBAL ability remains default.
    cur.execute(
        "UPDATE assessment_batteries SET is_active=FALSE, updated_at=now() WHERE company_code=%s AND battery_key IN (%s,%s)",
        (COMPANY, BATTERY_EN, BATTERY_AR),
    )
    cur.execute(
        "UPDATE assessment_batteries SET is_active=TRUE, retired_at=NULL, updated_at=now() WHERE battery_key=%s AND company_code=%s",
        (battery_key, COMPANY),
    )
    version = service.freeze_current_content_version(
        cur,
        company_code=COMPANY,
        battery_key=battery_key,
        created_by_user_id=f"bank_release:{RELEASE_KEY}",
    )
    cur.execute(
        """
        UPDATE assessment_batteries
        SET is_active=FALSE, updated_at=now(),
            raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
        WHERE battery_key=%s AND company_code=%s
        RETURNING *
        """,
        (
            json.dumps(
                {
                    "approved_for_use_status": "approved_for_use_beta",
                    "approved_for_use_beta": True,
                    "frozen_assessment_version_id": str(version["assessment_version_id"]),
                    "frozen_content_sha256": version.get("content_sha256"),
                    "selectable_for_hr_send": True,
                    "default_active_battery": False,
                }
            ),
            battery_key,
            COMPANY,
        ),
    )
    battery = dict(cur.fetchone())
    return {
        "battery_key": battery_key,
        "locale": locale,
        "item_count": len(inserted),
        "items": inserted,
        "assessment_version_id": str(version["assessment_version_id"]),
        "content_sha256": version.get("content_sha256"),
        "content_version": version.get("content_version"),
        "battery": app.json_safe(battery),
    }


def verify_item7(cur: Any, pack: dict[str, Any]) -> dict[str, Any]:
    expected_en = pack["items"][6]["locales"]["en"]
    cur.execute(
        """
        SELECT item_id, answer_key, prompt_text, raw_json
        FROM assessment_items
        WHERE item_id='b1beta_en_07'
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("item7_missing_after_insert")
    item = dict(row)
    raw = item.get("raw_json") if isinstance(item.get("raw_json"), dict) else {}
    if raw.get("source_draft_revision_id") != expected_en["draft_revision_id"]:
        raise RuntimeError("item7_revision_mismatch")
    if str(item.get("answer_key") or "").upper() != "C":
        raise RuntimeError("item7_answer_key_mismatch")
    if "Exclusive" not in str(expected_en.get("prompt_text") or "") and "supervisor" not in str(item.get("prompt_text") or "").lower():
        # Content must match exported pack text exactly.
        pass
    if str(item.get("prompt_text") or "") != str(expected_en.get("prompt_text") or ""):
        raise RuntimeError("item7_prompt_text_mismatch")
    return {
        "item_id": item["item_id"],
        "answer_key": item["answer_key"],
        "source_draft_revision_id": raw.get("source_draft_revision_id"),
        "prompt_prefix": str(item.get("prompt_text") or "")[:96],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to BATTERY_MANIFEST_V2.json")
    parser.add_argument("--content-pack", required=True, help="Path to BATTERY1_BETA_CONTENT_PACK.json")
    parser.add_argument("--approver-a", required=True, help="Assessment owner identity")
    parser.add_argument("--approver-b", required=True, help="Bank release operator identity")
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Must equal {CONFIRM_PREFIX}<manifest_sha256>",
    )
    parser.add_argument("--evidence-dir", default="", help="Optional evidence output directory")
    args = parser.parse_args()

    if args.approver_a.strip() == args.approver_b.strip():
        raise RuntimeError("two_person_control_requires_distinct_approvers")
    if not args.approver_a.strip() or not args.approver_b.strip():
        raise RuntimeError("approver_identity_required")

    expected_confirm = f"{CONFIRM_PREFIX}{EXPECTED_MANIFEST_SHA}"
    if args.confirm != expected_confirm:
        raise RuntimeError(f"confirm_mismatch: expected {expected_confirm!r}")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "production" or identity.database_environment != "production":
        raise RuntimeError("battery1_beta_release_refuses_non_production")

    authoring = str(os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING") or "").strip().lower()
    if authoring in {"1", "true", "on", "yes", "enabled"}:
        raise RuntimeError("refusing_release_while_assessment_authoring_enabled")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    pack = json.loads(Path(args.content_pack).read_text(encoding="utf-8"))
    manifest_sha = sha_manifest(manifest)
    if manifest_sha != EXPECTED_MANIFEST_SHA:
        raise RuntimeError(f"manifest_sha_mismatch:{manifest_sha}")
    if str(manifest.get("manifest_sha256") or "") != EXPECTED_MANIFEST_SHA:
        raise RuntimeError("manifest_embedded_sha_mismatch")
    if str(pack.get("manifest_sha256") or "") != EXPECTED_MANIFEST_SHA:
        raise RuntimeError("content_pack_manifest_pin_mismatch")
    pack_sha = content_pack_body_sha(pack)
    if str(pack.get("content_pack_sha256") or "") != pack_sha:
        raise RuntimeError(f"content_pack_sha_mismatch:{pack_sha}")
    if int(pack.get("item_count") or 0) != 25 or len(pack.get("items") or []) != 25:
        raise RuntimeError("content_pack_item_count_invalid")

    # Pin revised item #7 + monitoring flags.
    item7 = next(i for i in pack["items"] if int(i["order"]) == 7)
    if item7["locales"]["en"]["draft_revision_id"] != "58b443fb-dfa0-47b8-a947-4721f2be3ae7":
        raise RuntimeError("item7_en_revision_not_revised")
    if item7["locales"]["ar"]["draft_revision_id"] != "5b9ac5f5-2f98-4cda-af2a-79f21719ca6d":
        raise RuntimeError("item7_ar_revision_not_revised")
    flags = {int(i["order"]): i.get("monitoring_flag") for i in pack["items"]}
    if flags.get(8) != "difficulty_monitoring" or flags.get(22) != "ceiling_effect_monitoring":
        raise RuntimeError("monitoring_flags_missing")

    release_id = str(uuid.uuid4())
    report: dict[str, Any] = {
        "release_key": RELEASE_KEY,
        "release_id": release_id,
        "started_at": utcnow(),
        "environment": identity.public(),
        "company_code": COMPANY,
        "manifest_sha256": manifest_sha,
        "content_pack_sha256": pack_sha,
        "approver_a": args.approver_a.strip(),
        "approver_b": args.approver_b.strip(),
        "confirm": args.confirm,
        "authoring_env": os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING"),
        "idempotent_replay": False,
        "existing_attempts_untouched": True,
        "external_tenants_inserted": False,
        "http_publish_route_used": False,
        "ai_scoring": False,
    }

    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            lifecycle.ensure_assessment_schema(cur)
            ensure_release_table(cur)
            before = live_counts(cur)
            report["before_counts"] = before

            cur.execute(
                """
                SELECT *
                FROM assessment_bank_releases
                WHERE company_code=%s AND manifest_sha256=%s
                FOR UPDATE
                """,
                (COMPANY, manifest_sha),
            )
            existing = cur.fetchone()
            if existing:
                report["idempotent_replay"] = True
                report["release_id"] = str(existing["release_id"])
                report["status"] = "already_released"
                report["existing_release"] = app.json_safe(dict(existing))
                report["after_counts"] = live_counts(cur)
                conn.commit()
                _write_evidence(args.evidence_dir, report)
                print(json.dumps(app.json_safe(report), indent=2, default=str))
                return 0

            # Capture GLOBAL ability fingerprint before insert.
            cur.execute(
                """
                SELECT battery_key, company_code, is_active, content_version,
                       md5(coalesce(name,'') || coalesce(version,'')) AS fingerprint
                FROM assessment_batteries
                WHERE battery_key=%s
                """,
                (app.ASSESSMENT_BATTERY_KEY,),
            )
            ability = dict(cur.fetchone() or {})
            report["global_ability_before"] = app.json_safe(ability)

            insertion = {
                "en": insert_locale_battery(
                    cur,
                    locale="en",
                    battery_key=BATTERY_EN,
                    pack=pack,
                    release_id=release_id,
                    manifest_sha=manifest_sha,
                    content_pack_sha=pack_sha,
                ),
                "ar": insert_locale_battery(
                    cur,
                    locale="ar",
                    battery_key=BATTERY_AR,
                    pack=pack,
                    release_id=release_id,
                    manifest_sha=manifest_sha,
                    content_pack_sha=pack_sha,
                ),
            }
            item7_proof = verify_item7(cur, pack)

            # Ensure GLOBAL ability remains the only default active battery.
            cur.execute(
                """
                UPDATE assessment_batteries
                SET is_active=FALSE, updated_at=now()
                WHERE company_code=%s AND battery_key IN (%s,%s)
                """,
                (COMPANY, BATTERY_EN, BATTERY_AR),
            )
            cur.execute(
                """
                SELECT battery_key, company_code, is_active
                FROM assessment_batteries
                WHERE is_active IS TRUE
                ORDER BY company_code, battery_key
                """
            )
            active = [dict(r) for r in cur.fetchall()]
            if not any(r["battery_key"] == app.ASSESSMENT_BATTERY_KEY and r["is_active"] for r in active):
                raise RuntimeError("global_ability_not_active_after_release")
            if any(r["battery_key"] in {BATTERY_EN, BATTERY_AR} and r["is_active"] for r in active):
                raise RuntimeError("beta_batteries_must_not_be_default_active")

            after = live_counts(cur)
            if after["wathefni_attempts"] != before["wathefni_attempts"]:
                raise RuntimeError("attempt_count_changed_during_release")
            if after["external_attempts"] != before["external_attempts"]:
                raise RuntimeError("external_attempts_changed")
            if after["external_batteries"] != 0:
                raise RuntimeError("external_tenant_batteries_present")
            if after["ability_v1_items"] != before["ability_v1_items"]:
                raise RuntimeError("ability_v1_items_mutated")

            evidence = {
                "batteries": {
                    "en": {
                        "battery_key": insertion["en"]["battery_key"],
                        "assessment_version_id": insertion["en"]["assessment_version_id"],
                        "content_sha256": insertion["en"]["content_sha256"],
                        "item_count": insertion["en"]["item_count"],
                    },
                    "ar": {
                        "battery_key": insertion["ar"]["battery_key"],
                        "assessment_version_id": insertion["ar"]["assessment_version_id"],
                        "content_sha256": insertion["ar"]["content_sha256"],
                        "item_count": insertion["ar"]["item_count"],
                    },
                },
                "item7": item7_proof,
                "monitoring_flags": {"8": flags.get(8), "22": flags.get(22)},
                "active_batteries": app.json_safe(active),
                "label": BATTERY_LABEL,
                "scoring_version": SCORING_VERSION,
            }
            cur.execute(
                """
                INSERT INTO assessment_bank_releases
                  (release_id, release_key, company_code, manifest_sha256, content_pack_sha256,
                   status, approver_a, approver_b, battery_keys, version_ids,
                   before_counts, after_counts, evidence_json)
                VALUES (%s,%s,%s,%s,%s,'released',%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    release_id,
                    RELEASE_KEY,
                    COMPANY,
                    manifest_sha,
                    pack_sha,
                    args.approver_a.strip(),
                    args.approver_b.strip(),
                    app.Json([BATTERY_EN, BATTERY_AR]),
                    app.Json(
                        {
                            "en": insertion["en"]["assessment_version_id"],
                            "ar": insertion["ar"]["assessment_version_id"],
                        }
                    ),
                    app.Json(before),
                    app.Json(after),
                    app.Json(evidence),
                ),
            )
            release_row = dict(cur.fetchone())
            report.update(
                {
                    "status": "released",
                    "completed_at": utcnow(),
                    "after_counts": after,
                    "insertion": {
                        "en": {k: insertion["en"][k] for k in ("battery_key", "assessment_version_id", "content_sha256", "item_count")},
                        "ar": {k: insertion["ar"][k] for k in ("battery_key", "assessment_version_id", "content_sha256", "item_count")},
                    },
                    "item7": item7_proof,
                    "release_row": app.json_safe(release_row),
                    "rollback": {
                        "method": "retire_beta_batteries_restore_global_default",
                        "commands": [
                            f"UPDATE assessment_batteries SET is_active=FALSE, retired_at=now() WHERE battery_key IN ('{BATTERY_EN}','{BATTERY_AR}') AND company_code='{COMPANY}'",
                            f"UPDATE assessment_batteries SET is_active=TRUE, retired_at=NULL WHERE battery_key='{app.ASSESSMENT_BATTERY_KEY}'",
                            "Existing attempts remain pinned to their original assessment_version_id and are never rewritten.",
                        ],
                    },
                }
            )
        conn.commit()

    _write_evidence(args.evidence_dir, report)
    print(json.dumps(app.json_safe(report), indent=2, default=str))
    return 0


def _write_evidence(evidence_dir: str, report: dict[str, Any]) -> None:
    if not evidence_dir:
        return
    path = Path(evidence_dir)
    path.mkdir(parents=True, exist_ok=True)
    out = path / "RELEASE_PROOF.json"
    out.write_text(json.dumps(app.json_safe(report), indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise
