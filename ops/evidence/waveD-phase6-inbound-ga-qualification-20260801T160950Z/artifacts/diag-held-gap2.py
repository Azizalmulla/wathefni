#!/usr/bin/env python3
import os, subprocess, sys, json
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
for drop in Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
    for line in drop.read_text().splitlines():
        s = line.strip()
        if s.startswith("Environment=") and "=" in s.split("=", 1)[1]:
            k, v = s.split("=", 1)[1].split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")
import app

out = {}
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT inbound_id::text, status, provider, provider_message_id,
                   coalesce(from_email, '') AS from_email,
                   coalesce(subject,'') AS subject, created_at::text
            FROM inbound_messages
            WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours'
            ORDER BY created_at DESC LIMIT 15
            """
        )
        out["messages"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT job_id::text, job_type, status, last_error_code,
                   left(coalesce(last_error_detail,''),200) AS detail, created_at::text
            FROM intake_processing_jobs
            WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours'
            ORDER BY created_at DESC LIMIT 30
            """
        )
        out["jobs"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT app_key, status, ingested_at::text, coalesce(raw_json->>'email','') AS email
            FROM applications
            WHERE company_code='WATHEFNI' AND ingested_at > now() - interval '6 hours'
            ORDER BY ingested_at DESC LIMIT 15
            """
        )
        out["apps"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='intake_documents' ORDER BY 1
            """
        )
        cols = [r["column_name"] for r in cur.fetchall()]
        out["doc_columns"] = cols
        # pick safe columns
        want = [c for c in ["document_id", "inbound_id", "malware_status", "scan_state", "extraction_status", "identity_status", "status", "created_at"] if c in cols]
        if want:
            cur.execute(
                f"SELECT {', '.join(want)} FROM intake_documents WHERE company_code='WATHEFNI' AND created_at > now() - interval '2 hours' ORDER BY created_at DESC LIMIT 12"
            )
            out["docs"] = [dict(r) for r in cur.fetchall()]

Path("/opt/wathefni/production-evidence/waveD-phase6-ga/20260801T160950Z/verify/diag-held-gap.json").write_text(
    json.dumps(out, indent=2, default=str) + "\n"
)
print(json.dumps({"msg": len(out["messages"]), "jobs": len(out["jobs"]), "apps": len(out["apps"])}, indent=2))
for m in out["messages"][:8]:
    print("M", m.get("status"), m.get("from_email"), m.get("subject")[:40] if m.get("subject") else "", m.get("provider_message_id"))
from collections import Counter
print("job_counter", Counter((j["job_type"], j["status"], j.get("last_error_code")) for j in out["jobs"]))
print("apps", out["apps"][:5])
print("docs", out.get("docs", [])[:5])
