#!/usr/bin/env python3
"""Prepare or clean isolated Candidates C0/C1 owner-review fixtures on staging."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMPANY = "WATHEFNI"
MARKER = "candidates_c01_owner_ux"
ACTOR = "00000000-0000-4000-8000-c01c01c01c01"
FIXTURES = (
    {
        "app_key": "c01ux-ready-20260721",
        "phone": "965580019901",
        "name": "C01 Review Candidate",
        "name_ar": "مرشح مراجعة C01",
        "position_code": "C01UX_READY",
        "position_title": "Owner UX — Ready for Review",
        "status": "ready_for_review",
    },
    {
        "app_key": "c01ux-shortlisted-20260721",
        "phone": "965580019902",
        "name": "C01 Shortlisted Candidate",
        "name_ar": "مرشح القائمة المختصرة C01",
        "position_code": "C01UX_SHORTLISTED",
        "position_title": "Owner UX — Shortlisted",
        "status": "shortlisted",
    },
    {
        "app_key": "c01ux-interview-20260721",
        "phone": "965580019903",
        "name": "C01 Interview Candidate",
        "name_ar": "مرشح المقابلة C01",
        "position_code": "C01UX_INTERVIEW",
        "position_title": "Owner UX — Interview",
        "status": "interview",
    },
)


def require_staging() -> None:
    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni_staging":
        raise SystemExit("refusing non-staging database")
    if (os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() not in {"dry_run", "dry-run", "dryrun"}:
        raise SystemExit("refusing non-dry-run delivery")


def cleanup(orch: Any) -> dict[str, int]:
    app_keys = [item["app_key"] for item in FIXTURES]
    phones = [item["phone"] for item in FIXTURES]
    positions = [item["position_code"] for item in FIXTURES]
    counts: dict[str, int] = {}
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            statements = (
                ("action_results", "DELETE FROM action_results WHERE company_code=%s AND result->'action'->>'target'=ANY(%s)", (COMPANY, app_keys)),
                ("pending_actions", "DELETE FROM pending_actions WHERE company_code=%s AND metadata->'tool_args'->>'app_key'=ANY(%s)", (COMPANY, app_keys)),
                ("hire_operations", "DELETE FROM hire_operations WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("confirmations", "DELETE FROM candidate_action_confirmations WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("interview_events", "DELETE FROM candidate_interview_events WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("interviews", "DELETE FROM candidate_interviews WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("lifecycle_events", "DELETE FROM application_lifecycle_events WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("hr_tasks", "DELETE FROM hr_tasks WHERE company_code=%s AND metadata->>'app_key'=ANY(%s)", (COMPANY, app_keys)),
                ("compliance", "DELETE FROM compliance_documents WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, "WATHEFNI-9655800199%")),
                ("onboarding", "DELETE FROM onboarding_items WHERE employee_key LIKE %s", ("WATHEFNI-9655800199%",)),
                ("employees", "DELETE FROM employees WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("applications", "DELETE FROM applications WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY, app_keys)),
                ("positions", "DELETE FROM positions WHERE company_code=%s AND position_code=ANY(%s)", (COMPANY, positions)),
                ("candidates", "DELETE FROM candidates WHERE phone=ANY(%s)", (phones,)),
            )
            for label, sql, params in statements:
                cur.execute(sql, params)
                counts[label] = cur.rowcount
        conn.commit()
    return counts


def prepare(orch: Any) -> dict[str, Any]:
    cleanup(orch)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            for item in FIXTURES:
                cur.execute(
                    """
                    INSERT INTO candidates
                      (phone, name, email, current_status, active_company_code,
                       active_position_code, data_source, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,'staging_owner_review',%s::jsonb,now())
                    """,
                    (
                        item["phone"],
                        item["name"],
                        f"{item['phone']}@example.test",
                        item["status"],
                        COMPANY,
                        item["position_code"],
                        json.dumps({"c01_marker": MARKER, "name_ar": item["name_ar"], "smoke": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO positions
                      (company_code, position_code, title, status, vacancies, raw_json)
                    VALUES (%s,%s,%s,'open',2,%s::jsonb)
                    """,
                    (
                        COMPANY,
                        item["position_code"],
                        item["position_title"],
                        json.dumps({"c01_marker": MARKER, "owner_review": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications
                      (app_key, phone, company_code, position_code, position_title,
                       status, current_step, lifecycle_version, cv_received,
                       screening_status, data_source, ingested_at, updated_at, raw_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,0,true,'complete',
                            'staging_owner_review',now(),now(),%s::jsonb)
                    """,
                    (
                        item["app_key"],
                        item["phone"],
                        COMPANY,
                        item["position_code"],
                        item["position_title"],
                        item["status"],
                        item["status"],
                        json.dumps(
                            {
                                "c01_marker": MARKER,
                                "owner_review": True,
                                "candidate_name_ar": item["name_ar"],
                                "cv": {"received": True, "quality_ok": True},
                            }
                        ),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO application_lifecycle_events
                      (company_code, app_key, from_stage, to_stage, trigger,
                       actor_type, actor_user_id, channel, idempotency_key, metadata)
                    VALUES (%s,%s,%s,%s,'fixture_preparation','system',%s,'system',%s,%s::jsonb)
                    """,
                    (
                        COMPANY,
                        item["app_key"],
                        item["status"],
                        item["status"],
                        ACTOR,
                        f"{MARKER}:{item['app_key']}",
                        json.dumps({"c01_marker": MARKER, "owner_review": True}),
                    ),
                )
        conn.commit()

    interview_fixture = next(item for item in FIXTURES if item["status"] == "interview")
    interview_app = orch.find_application_by_key(interview_fixture["app_key"], company_code=COMPANY)
    interview = orch.create_candidate_interview_from_schedule(
        interview_app,
        {
            "start": "2026-07-23T10:00:00+03:00",
            "end": "2026-07-23T10:30:00+03:00",
            "result": {
                "event": {
                    "id": f"{MARKER}-calendar",
                    "conferenceData": {
                        "entryPoints": [
                            {"entryPointType": "video", "uri": "https://meet.google.com/c01-owner-review"}
                        ]
                    },
                }
            },
        },
        created_by_phone="96599338566",
        source=MARKER,
    )
    return {
        "company_code": COMPANY,
        "marker": MARKER,
        "delivery_mode": os.environ.get("WATHEFNI_DELIVERY_MODE"),
        "fixtures": list(FIXTURES),
        "interview_id": str((interview or {}).get("interview_id") or ""),
        "cleanup_command": "python ops/candidates-c01-owner-ux.py cleanup",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "cleanup"))
    args = parser.parse_args()
    require_staging()
    import app as orch

    orch.assert_runtime_environment_binding()
    result = prepare(orch) if args.mode == "prepare" else {"cleanup": cleanup(orch)}
    print(json.dumps(result, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
