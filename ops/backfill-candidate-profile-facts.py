#!/usr/bin/env python3
"""Idempotent backfill of candidate-profile-facts-v1 from existing CV fact snapshots.

Does not re-extract CVs, create duplicate snapshots, or invent new documents.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys


def main() -> int:
    pid = os.environ.get("PROOF_PID") or ""
    company = (os.environ.get("COMPANY_CODE") or "").strip().upper() or None
    limit = int(os.environ["LIMIT"]) if os.environ.get("LIMIT") else None
    if pid:
        for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
            if not item or b"=" not in item:
                continue
            k, v = item.split(b"=", 1)
            os.environ[k.decode()] = v.decode(errors="replace")

    import app
    import candidate_profile_facts as cpf

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            before = 0
            try:
                cur.execute("SELECT count(*) AS n FROM application_cv_fact_snapshots WHERE is_current=true")
                before = int((cur.fetchone() or {}).get("n") or 0)
            except Exception:
                before = 0
            result = cpf.backfill_current_snapshots(cur, company_code=company, limit=limit)
            cur.execute("SELECT count(*) AS n FROM candidate_profile_facts WHERE is_current=true")
            after_profiles = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM application_cv_fact_snapshots WHERE is_current=true")
            after_facts = int((cur.fetchone() or {}).get("n") or 0)
            conn.commit()

    payload = {
        **result,
        "current_fact_snapshots_before": before,
        "current_fact_snapshots_after": after_facts,
        "current_profile_facts": after_profiles,
        "no_duplicate_fact_snapshots": before == after_facts,
        "company_code": company,
    }
    print(json.dumps(payload, default=str, indent=2))
    return 0 if payload.get("ok") and payload.get("no_duplicate_fact_snapshots") else 1


if __name__ == "__main__":
    raise SystemExit(main())
