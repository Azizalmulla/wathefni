#!/usr/bin/env python3
"""Wave 4C remediation hygiene — classify Wave 3 jurisdiction queue.

- Do NOT classify the four real employees (leave policy_pack_status=remediation).
- Quarantine only confirmed synthetic/test leftovers with evidence stamps.
- Preserve genuine historical employments (reals + any non-synth historical).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REAL_KEYS = {
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
}

QUARANTINE_STATUS = "quarantined_synthetic_test"


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import app

    company = "WATHEFNI"
    dry_run = str(os.environ.get("WAVE4C_REMEDIATION_DRY_RUN") or "0") in {"1", "true", "yes"}
    stamp = datetime.now(timezone.utc).isoformat()
    report: dict = {
        "stamp": stamp,
        "dry_run": dry_run,
        "categories": {
            "real_active_unclassified": [],
            "synthetic_test_leftover_quarantined": [],
            "preserved_historical_non_synth": [],
            "unknown_skipped": [],
        },
        "actions": [],
    }

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.employment_id::text AS employment_id,
                       e.legacy_employee_key,
                       e.employment_status,
                       e.lifecycle_state,
                       e.hire_source,
                       e.policy_pack_status,
                       e.jurisdiction_code,
                       e.worker_category,
                       e.provenance,
                       p.display_name,
                       p.primary_phone,
                       m.employee_key AS map_key
                FROM employee_employments e
                LEFT JOIN employee_persons p ON p.person_id=e.person_id
                LEFT JOIN employee_key_authority_map m ON m.employment_id=e.employment_id
                WHERE e.company_code=%s AND e.policy_pack_status='remediation'
                ORDER BY e.legacy_employee_key NULLS LAST, e.created_at
                """,
                (company,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]

            for row in rows:
                key = str(row.get("legacy_employee_key") or row.get("map_key") or "")
                name = str(row.get("display_name") or "")
                phone = str(row.get("primary_phone") or "")
                prov = row.get("provenance") or {}
                if isinstance(prov, str):
                    try:
                        prov = json.loads(prov)
                    except Exception:
                        prov = {"raw": prov}
                source = str(prov.get("source") or row.get("hire_source") or "")

                is_real = key in REAL_KEYS
                is_synth = (
                    name.startswith("W3D-SYNTH|")
                    or phone.startswith("965522")
                    or "wave3d_synthetic" in source
                    or "wave3c_same_key_rehire" in source
                    or (source == "rehire" and ("965522" in phone or "965522" in key or "W3D-SYNTH" in name))
                    or (not key and "wave3d_synthetic" in json.dumps(prov))
                )

                item = {
                    "employment_id": row["employment_id"],
                    "employee_key": key or None,
                    "name": name,
                    "phone": phone,
                    "employment_status": row.get("employment_status"),
                    "lifecycle_state": row.get("lifecycle_state"),
                    "source": source,
                    "reason": None,
                }

                if is_real:
                    item["reason"] = "real_employee_active_employment_left_unclassified"
                    report["categories"]["real_active_unclassified"].append(item)
                    continue

                if is_synth:
                    item["reason"] = "confirmed_synthetic_canary_leftover"
                    report["categories"]["synthetic_test_leftover_quarantined"].append(item)
                    if not dry_run:
                        new_prov = dict(prov) if isinstance(prov, dict) else {"prior": prov}
                        new_prov["wave4c_quarantine"] = {
                            "at": stamp,
                            "status": QUARANTINE_STATUS,
                            "reason": item["reason"],
                        }
                        cur.execute(
                            """
                            UPDATE employee_employments
                            SET policy_pack_status=%s,
                                provenance=%s::jsonb,
                                updated_at=now()
                            WHERE employment_id=%s AND company_code=%s
                              AND policy_pack_status='remediation'
                            """,
                            (QUARANTINE_STATUS, json.dumps(new_prov), row["employment_id"], company),
                        )
                        report["actions"].append(
                            {"employment_id": row["employment_id"], "action": "quarantine", "new_status": QUARANTINE_STATUS}
                        )
                    continue

                # Non-synth historical leftovers — preserve (do not quarantine)
                item["reason"] = "not_confirmed_synthetic_preserved"
                report["categories"]["preserved_historical_non_synth"].append(item)

            if not dry_run:
                conn.commit()
            else:
                conn.rollback()

            # Final counts by category (post-action remediation queue)
            cur.execute(
                """
                SELECT policy_pack_status, count(*)::int AS n
                FROM employee_employments
                WHERE company_code=%s
                  AND (
                    policy_pack_status='remediation'
                    OR policy_pack_status=%s
                    OR legacy_employee_key = ANY(%s)
                  )
                GROUP BY policy_pack_status
                ORDER BY 1
                """,
                (company, QUARANTINE_STATUS, list(REAL_KEYS)),
            )
            report["final_status_counts"] = {dict(r)["policy_pack_status"]: int(dict(r)["n"]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT count(*)::int AS n FROM employee_employments
                WHERE company_code=%s AND policy_pack_status='remediation'
                """,
                (company,),
            )
            report["final_remediation_queue_count"] = int(dict(cur.fetchone())["n"])
            # Confirm reals still remediation + unclassified
            cur.execute(
                """
                SELECT legacy_employee_key, policy_pack_status, jurisdiction_code, worker_category
                FROM employee_employments
                WHERE company_code=%s AND legacy_employee_key = ANY(%s)
                """,
                (company, list(REAL_KEYS)),
            )
            report["reals_after"] = [dict(r) for r in cur.fetchall()]

    report["category_counts"] = {k: len(v) for k, v in report["categories"].items()}
    out = os.environ.get("WAVE4C_REMEDIATION_JSON")
    text = json.dumps(report, default=str, indent=2)
    if out:
        Path(out).write_text(text)
        print(f"wrote {out}")
    print(text)
    # Sanity: must keep exactly 4 reals unclassified; never act on them
    if report["category_counts"]["real_active_unclassified"] != 4:
        print("ERROR: expected 4 reals", file=sys.stderr)
        return 1
    if any(a.get("employment_id") in {x["employment_id"] for x in report["categories"]["real_active_unclassified"]} for a in report["actions"]):
        print("ERROR: acted on real", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
