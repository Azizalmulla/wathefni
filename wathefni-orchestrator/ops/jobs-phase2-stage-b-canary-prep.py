#!/usr/bin/env python3
"""Prepare dedicated Stage B WhatsApp canary fixtures on staging only.

Creates one open public test job with a clearly marked APPLY code, prints the
owner allowlist, and leaves deterministic cleanup instructions.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as orch
import prehire_jobs as jobs

COMPANY = "WATHEFNI"
ACTOR = "00000000-0000-4000-8000-000000000001"


def main() -> None:
    os.environ.setdefault("WATHEFNI_APPLY_WHATSAPP_NUMBER", "96599338566")
    assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni_staging"
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute("select current_database() as d")
        assert cur.fetchone()["d"] == "wathefni_staging"
        jobs.ensure_jobs_schema(cur)

    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M")
    marker = f"STAGEB-{suffix}"
    code = f"STAGEB_{suffix}"
    draft = jobs.create_job(
        company=COMPANY,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        payload={
            "position_code": code,
            "title": f"Stage B Owner Canary {marker}",
            "title_en": f"Stage B Owner Canary {marker}",
            "title_ar": f"تجربة مرحلة ب {marker}",
            "short_summary_en": f"{marker} Dedicated Stage B WhatsApp canary role. Test only.",
            "short_summary_ar": f"{marker} وظيفة تجريبية لمرحلة ب على واتساب فقط.",
            "description": (
                f"{marker} This is a staging-only Stage B canary job for owner WhatsApp testing. "
                "Applications created from this role are marked stage_b_canary=true."
            ),
            "requirements_en": ["Owner/girlfriend allowlisted WhatsApp test only"],
            "approve_content_en": True,
            "approve_content_ar": True,
            "location": "Kuwait City",
            "work_arrangement": "onsite",
            "employment_type": "full_time",
            "vacancies": 5,
            "visibility": "public",
            "salary_visibility": "hr_only",
            "salary_min": 400,
            "salary_max": 600,
            "currency": "KD",
        },
        as_draft=True,
    )
    # Ensure bilingual approval timestamps are present before publish.
    with orch.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE positions
            SET content_approved_en_at=COALESCE(content_approved_en_at, now()),
                content_approved_en_by=COALESCE(content_approved_en_by, %s::uuid),
                content_approved_ar_at=COALESCE(content_approved_ar_at, now()),
                content_approved_ar_by=COALESCE(content_approved_ar_by, %s::uuid),
                short_summary_en=COALESCE(NULLIF(TRIM(short_summary_en), ''), %s),
                short_summary_ar=COALESCE(NULLIF(TRIM(short_summary_ar), ''), %s),
                updated_at=now()
            WHERE company_code=%s AND position_code=%s
            RETURNING version
            """,
            (
                ACTOR,
                ACTOR,
                f"{marker} Dedicated Stage B WhatsApp canary role. Test only.",
                f"{marker} وظيفة تجريبية لمرحلة ب على واتساب فقط.",
                COMPANY,
                code,
            ),
        )
        version = int((cur.fetchone() or {}).get("version") or draft.get("version") or 1)
    opened = jobs.transition_job(
        company=COMPANY,
        position_code=code,
        db_connect=orch.db_connect,
        actor_user_id=ACTOR,
        to_status="open",
        expected_version=version,
    )
    allowlist = sorted(
        {
            *(os.environ.get("WATHEFNI_STAGE_B_PUBLIC_POSITIONS") or "STAGEB_07210227").split(","),
            *(os.environ.get("WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES") or "APPLY-WATHEFNI-STAGEB_07210227").split(","),
        }
    )
    report = {
        "marker": marker,
        "position_code": code,
        "apply_code": opened.get("apply_code"),
        "application_link": opened.get("application_link"),
        "status": opened.get("status"),
        "accepts_applications": opened.get("accepts_applications"),
        "public_canary_scope": allowlist,
        "database": "wathefni_staging",
        "cleanup": {
            "positions": code,
            "applications_filter": "raw_json.stage_b_canary=true OR position_code=code",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": uuid.uuid4().hex[:10],
    }
    path = os.environ.get("STAGE_B_CANARY_REPORT") or os.path.join(
        ROOT, "ops/reports/jobs-phase2-stage-b-canary-fixture.json"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
