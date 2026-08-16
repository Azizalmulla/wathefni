#!/usr/bin/env python3
import os, sys, re
from pathlib import Path

envp = Path("/tmp/orch-environ.env")
if not envp.exists():
    import subprocess
    pid = subprocess.check_output(
        ["systemctl", "show", "-p", "MainPID", "--value", "wathefni-orchestrator"], text=True
    ).strip()
    envp.write_bytes(b"\n".join(Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")))
for line in envp.read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k, v)

sys.path.insert(0, "/opt/wathefni/orchestrator")
import app as A

with A.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT employee_key, phone, name FROM employees WHERE company_code=%s AND employee_key LIKE %s ORDER BY employee_key LIMIT 20",
            ("WATHEFNI", "WATHEFNI-965549%"),
        )
        print("allowlist-ish", cur.fetchall())
        cur.execute(
            "SELECT employee_key, phone, name FROM employees WHERE company_code=%s AND (name ILIKE %s OR phone LIKE %s) ORDER BY updated_at DESC LIMIT 15",
            ("WATHEFNI", "%Aziz%", "965549%"),
        )
        print("aziz-ish", cur.fetchall())
        cur.execute(
            "SELECT employee_key, phone, name FROM employees WHERE company_code=%s ORDER BY updated_at DESC LIMIT 10",
            ("WATHEFNI",),
        )
        print("recent", cur.fetchall())

t = Path("/opt/wathefni/orchestrator/app.py").read_text(errors="ignore")
for pat in [
    r'["\']/dashboard/posthire/employees/\{[^}]+\}/bank[^"\']*["\']',
    r'["\']/dashboard/posthire/employees/\{[^}]+\}/onboarding-completion[^"\']*["\']',
]:
    for m in re.finditer(pat, t):
        print("route", m.group(0))
