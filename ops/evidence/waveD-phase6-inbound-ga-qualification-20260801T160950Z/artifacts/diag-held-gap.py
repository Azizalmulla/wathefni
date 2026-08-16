#!/usr/bin/env python3
import os, subprocess, json
from pathlib import Path

unit = subprocess.check_output(["systemctl", "cat", "wathefni-orchestrator"], text=True)
for line in unit.splitlines():
    s = line.strip()
    if s.startswith("EnvironmentFile="):
        p = Path(s.split("=", 1)[1].strip().lstrip("-"))
        if p.exists():
            for raw in p.read_text().splitlines():
                if raw and not raw.lstrip().startswith("#") and "=" in raw:
                    k, v = raw.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if s.startswith("Environment=") and "=" in s.split("=", 1)[1]:
        k, v = s.split("=", 1)[1].split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
for drop in Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
    for line in drop.read_text().splitlines():
        s = line.strip()
        if s.startswith("Environment=") and "=" in s.split("=", 1)[1]:
            k, v = s.split("=", 1)[1].split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

import sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")
import app

out = {}
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT inbound_id::text, status, provider_message_id, from_email, subject, created_at::text
            FROM inbound_email_messages
            WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours'
            ORDER BY created_at DESC LIMIT 12
            """
        )
        out["messages"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT job_id::text, job_type, status, last_error_code,
                   left(coalesce(last_error_detail,''),180) AS detail, created_at::text
            FROM intake_processing_jobs
            WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours'
            ORDER BY created_at DESC LIMIT 25
            """
        )
        out["jobs"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT app_key, status, ingested_at::text, coalesce(raw_json->>'email','') AS email
            FROM applications
            WHERE company_code='WATHEFNI' AND ingested_at > now() - interval '2 hours'
            ORDER BY ingested_at DESC LIMIT 10
            """
        )
        out["apps"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT document_id::text, inbound_id::text, malware_status, extraction_status, identity_status
            FROM intake_documents
            WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours'
            ORDER BY created_at DESC LIMIT 12
            """
        )
        try:
            out["docs"] = [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            out["docs_error"] = str(exc)
            conn.rollback()
            with conn.cursor() as cur2:
                cur2.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='intake_documents' ORDER BY 1
                    """
                )
                out["doc_columns"] = [r["column_name"] for r in cur2.fetchall()]

print(json.dumps(out, indent=2, default=str))
