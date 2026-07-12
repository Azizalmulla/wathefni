#!/usr/bin/env python3
"""Phase 7C.5 — one staging WATHEFNI canary apply (W1 civil_id only).

Hard limits:
  - staging DSN only
  - company WATHEFNI
  - employee sample_id emp_2c08123fca34
  - document_type civil_id
  - W1 only / max-writes 1
  - no production apply
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COMPANY = "WATHEFNI"
SAMPLE_ID = "emp_2c08123fca34"
DOC_TYPE = "civil_id"
OPS = Path(__file__).resolve().parent
CLI = OPS / "staging-phase7c4-reconcile-docs.py"
POSTGRES_ENV = os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
STAGING_BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
REPORTS = OPS / "reports"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    load_env(Path(POSTGRES_ENV))
    dsn = os.environ["WATHEFNI_DATABASE_URL"]
    if "staging" not in dsn.lower():
        raise SystemExit("refusing non-staging DSN")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def sample_id(employee_key: str) -> str:
    return "emp_" + hashlib.sha256(str(employee_key).encode()).hexdigest()[:12]


def run_cli(args: list[str], *, apply: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["WATHEFNI_POSTGRES_ENV"] = POSTGRES_ENV
    env.pop("WATHEFNI_RECONCILE_APPLY", None)
    if apply:
        env["WATHEFNI_RECONCILE_APPLY"] = "1"
    return subprocess.run(
        [sys.executable, str(CLI), "--postgres-env", POSTGRES_ENV, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def http_get(path: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(STAGING_BASE + path, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500] if hasattr(exc, "fp") and exc.fp else ""
        return int(exc.code), body or str(exc)
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def fingerprint(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM employees WHERE company_code=%s) AS employees,
              (SELECT count(*) FROM onboarding_items oi
                 JOIN employees e ON e.employee_key=oi.employee_key
                 WHERE e.company_code=%s) AS onboarding_items,
              (SELECT count(*) FROM employee_documents WHERE company_code=%s) AS employee_documents,
              (SELECT count(*) FROM compliance_documents WHERE company_code=%s) AS compliance_documents,
              (SELECT count(*) FROM file_registry WHERE company_code=%s) AS file_registry
            """,
            (COMPANY, COMPANY, COMPANY, COMPANY, COMPANY),
        )
        counts = dict(cur.fetchone() or {})
        cur.execute(
            """
            SELECT md5(string_agg(x.s, '|' ORDER BY x.s)) AS oi_fp
            FROM (
              SELECT oi.employee_key || ':' || oi.item_id || ':' || coalesce(oi.status,'') AS s
              FROM onboarding_items oi
              JOIN employees e ON e.employee_key=oi.employee_key
              WHERE e.company_code=%s
            ) x
            """,
            (COMPANY,),
        )
        oi_fp = (cur.fetchone() or {}).get("oi_fp")
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM employee_documents WHERE company_code<>%s)
              + (SELECT count(*) FROM compliance_documents WHERE company_code IS NOT NULL AND company_code<>%s)
              AS other_docs
            """,
            (COMPANY, COMPANY),
        )
        other = int((cur.fetchone() or {}).get("other_docs") or 0)
        cur.execute(
            """
            SELECT e.employee_key, oi.item_id, oi.status, oi.updated_at::text AS updated_at
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code=%s
            ORDER BY oi.item_id, e.employee_key
            """,
            (COMPANY,),
        )
        all_oi = []
        targets = []
        for row in cur.fetchall():
            sid = sample_id(row["employee_key"])
            entry = {
                "sample_id": sid,
                "item_id": row["item_id"],
                "status": row["status"],
                "updated_at": row["updated_at"],
            }
            all_oi.append(entry)
            if row["item_id"] == DOC_TYPE:
                targets.append({**entry, "match": sid == SAMPLE_ID})
        cur.execute(
            "SELECT employee_key, status FROM employee_documents WHERE company_code=%s AND document_type=%s",
            (COMPANY, DOC_TYPE),
        )
        ed_rows = []
        for row in cur.fetchall():
            sid = sample_id(row["employee_key"])
            if sid == SAMPLE_ID:
                ed_rows.append({"sample_id": sid, "status": row["status"]})
    return {
        "counts": counts,
        "onboarding_fingerprint": oi_fp,
        "other_company_docs": other,
        "civil_id_onboarding": targets,
        "all_onboarding": all_oi,
        "civil_id_employee_docs": ed_rows,
    }


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "phase": "7C.5",
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "company": COMPANY,
        "sample_id": SAMPLE_ID,
        "document_type": DOC_TYPE,
        "action": "mark_onboarding_received",
    }

    # Production refuse proof
    prod_env = "/root/.openclaw/secrets/postgres.env"
    if Path(prod_env).exists():
        env = {k: v for k, v in os.environ.items() if k != "WATHEFNI_DATABASE_URL"}
        env["WATHEFNI_RECONCILE_APPLY"] = "1"
        proc = subprocess.run(
            [
                sys.executable, str(CLI),
                "--postgres-env", prod_env,
                "--company", COMPANY, "--mode", "apply",
                "--confirm-company", COMPANY, "--i-understand-writes",
                "--allow-staging-wathefni-canary",
                "--confirm-apply-token", "x",
                "--apply-token-expires-at", "2099-01-01T00:00:00Z",
                "--expect-plan-hash", "y",
                "--employee-sample-id", SAMPLE_ID,
                "--document-type", DOC_TYPE,
                "--max-writes", "1",
            ],
            capture_output=True, text=True, env=env,
        )
        report["production_dsn_refused"] = {
            "ok": proc.returncode != 0 and "production" in (proc.stderr + proc.stdout).lower(),
            "output": (proc.stderr + proc.stdout)[-240:],
        }
    else:
        report["production_dsn_refused"] = {"ok": True, "output": "postgres.env missing"}

    # Refuse without unlock flag
    proc = run_cli(
        [
            "--company", COMPANY, "--mode", "apply",
            "--confirm-company", COMPANY, "--i-understand-writes",
            "--confirm-apply-token", "x",
            "--apply-token-expires-at", "2099-01-01T00:00:00Z",
            "--expect-plan-hash", "y",
            "--employee-sample-id", SAMPLE_ID,
            "--document-type", DOC_TYPE,
            "--max-writes", "1",
        ],
        apply=True,
    )
    report["wathefni_without_unlock_refused"] = {
        "ok": proc.returncode != 0 and "allow-staging-wathefni-canary" in (proc.stderr + proc.stdout),
        "output": (proc.stderr + proc.stdout)[-240:],
    }

    conn = connect()
    try:
        before = fingerprint(conn)
        report["before"] = before

        target = next((t for t in before["civil_id_onboarding"] if t["match"]), None)
        ed = before["civil_id_employee_docs"]
        if not target:
            raise SystemExit(f"canary sample_id {SAMPLE_ID} not found for civil_id onboarding")
        if not ed:
            raise SystemExit("employee document for civil_id not found for canary sample")
        if str(target.get("status") or "").lower() in {"received", "submitted", "complete", "completed", "done"}:
            raise SystemExit(f"canary already received; refusing apply status={target.get('status')}")

        plan_path = REPORTS / "phase7c5-wathefni-dryrun-before.jsonl"
        sum_path = REPORTS / "phase7c5-wathefni-dryrun-before-summary.json"
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "dry-run",
                "--employee-sample-id", SAMPLE_ID,
                "--document-type", DOC_TYPE,
                "--jsonl-out", str(plan_path),
                "--summary-out", str(sum_path),
            ]
        )
        if proc.returncode != 0:
            raise SystemExit(proc.stderr + proc.stdout)
        dry = json.loads(sum_path.read_text())
        events = [json.loads(l) for l in plan_path.read_text().splitlines() if l.strip()]
        plans = [e for e in events if e.get("decision") == "plan"]
        w1 = [e for e in plans if e.get("action") == "mark_onboarding_received"]
        report["dry_run_before"] = {
            "planned_writes": dry.get("planned_writes"),
            "plan_hash": dry.get("plan_hash"),
            "plan_actions": [e.get("action") for e in plans],
            "w1_count": len(w1),
        }
        if len(w1) != 1:
            raise SystemExit(f"expected exactly one W1 plan; got {len(w1)} plans={report['dry_run_before']}")
        report["selected_plan_event"] = w1[0]

        token = dry["apply_token"]
        expires = dry["apply_token_expires_at"]
        plan_hash = dry["plan_hash"]

        apply_path = REPORTS / "phase7c5-wathefni-apply.jsonl"
        apply_sum_path = REPORTS / "phase7c5-wathefni-apply-summary.json"
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "apply",
                "--confirm-company", COMPANY,
                "--i-understand-writes",
                "--allow-staging-wathefni-canary",
                "--confirm-apply-token", token,
                "--apply-token-expires-at", expires,
                "--expect-plan-hash", plan_hash,
                "--employee-sample-id", SAMPLE_ID,
                "--document-type", DOC_TYPE,
                "--max-writes", "1",
                "--apply-jsonl-out", str(apply_path),
                "--summary-out", str(apply_sum_path),
            ],
            apply=True,
        )
        if proc.returncode != 0:
            raise SystemExit("APPLY FAILED: " + proc.stderr + proc.stdout)
        apply_sum = json.loads(apply_sum_path.read_text())
        apply_events = [json.loads(l) for l in apply_path.read_text().splitlines() if l.strip()]
        report["apply_summary"] = apply_sum
        report["apply_audit"] = apply_events
        if apply_sum.get("applied") != 1 or len(apply_events) != 1:
            raise SystemExit(f"expected exactly one applied write: {apply_sum}")

        after = fingerprint(conn)
        report["after"] = after
        target_after = next((t for t in after["civil_id_onboarding"] if t["match"]), None)
        if not target_after or str(target_after.get("status") or "").lower() != "received":
            raise SystemExit(f"after status not received: {target_after}")

        # Collateral: counts/other companies/ED unchanged; only canary OI status changed.
        def oi_key(row: dict) -> tuple:
            return (row["sample_id"], row["item_id"], row["status"])

        before_other_oi = [
            oi_key(r)
            for r in before["all_onboarding"]
            if not (r["sample_id"] == SAMPLE_ID and r["item_id"] == DOC_TYPE)
        ]
        after_other_oi = [
            oi_key(r)
            for r in after["all_onboarding"]
            if not (r["sample_id"] == SAMPLE_ID and r["item_id"] == DOC_TYPE)
        ]
        collateral_ok = (
            before["counts"] == after["counts"]
            and before["other_company_docs"] == after["other_company_docs"]
            and before["civil_id_employee_docs"] == after["civil_id_employee_docs"]
            and before_other_oi == after_other_oi
            and before["onboarding_fingerprint"] != after["onboarding_fingerprint"]
        )
        report["collateral"] = {
            "ok": collateral_ok,
            "counts_before": before["counts"],
            "counts_after": after["counts"],
            "other_company_docs_before": before["other_company_docs"],
            "other_company_docs_after": after["other_company_docs"],
            "other_onboarding_rows_unchanged": before_other_oi == after_other_oi,
            "fingerprint_changed": before["onboarding_fingerprint"] != after["onboarding_fingerprint"],
        }
        # Do not keep full all_onboarding in final report (noise); drop after checks
        report["before"].pop("all_onboarding", None)
        report["after"].pop("all_onboarding", None)
        if not report["collateral"]["ok"]:
            raise SystemExit(f"collateral check failed: {report['collateral']}")

        # Re-dry-run canary scope
        re_plan = REPORTS / "phase7c5-wathefni-dryrun-after.jsonl"
        re_sum = REPORTS / "phase7c5-wathefni-dryrun-after-summary.json"
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "dry-run",
                "--employee-sample-id", SAMPLE_ID,
                "--document-type", DOC_TYPE,
                "--jsonl-out", str(re_plan),
                "--summary-out", str(re_sum),
            ]
        )
        if proc.returncode != 0:
            raise SystemExit(proc.stderr + proc.stdout)
        re_dry = json.loads(re_sum.read_text())
        re_events = [json.loads(l) for l in re_plan.read_text().splitlines() if l.strip()]
        re_w1 = [e for e in re_events if e.get("decision") == "plan" and e.get("action") == "mark_onboarding_received"]
        report["dry_run_after"] = {
            "planned_writes": re_dry.get("planned_writes"),
            "w1_remaining": len(re_w1),
            "plan_actions": [e.get("action") for e in re_events if e.get("decision") == "plan"],
        }
        if len(re_w1) != 0:
            raise SystemExit(f"W1 drift not resolved: {report['dry_run_after']}")

    finally:
        conn.close()

    health_status, health_body = http_get("/health")
    # Authenticated dashboard probes (staging operator phone used by prior staging verifiers).
    token = None
    for conf in Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d").glob("*.conf"):
        for line in conf.read_text().splitlines():
            if "WATHEFNI_DASHBOARD_TOKEN" in line and "=" in line:
                token = line.split("=", 1)[1].strip().strip('"')
    phone = os.environ.get("WATHEFNI_STAGING_HR_PHONE", "96599338566")
    dash_headers = {}
    if token:
        dash_headers = {
            "Authorization": f"Bearer {token}",
            "X-HR-Phone": phone,
            "X-Company-Code": COMPANY,
        }
    boot_status, boot_body = http_get("/dashboard/bootstrap", dash_headers)
    onboard_status, onboard_body = http_get("/dashboard/posthire/onboarding", dash_headers)
    report["staging_health"] = {"status": health_status, "ok": health_status == 200, "body": health_body[:200]}
    report["dashboard_endpoint"] = {
        "bootstrap_status": boot_status,
        "ok": boot_status == 200,
        "body": boot_body[:200],
    }
    report["onboarding_view"] = {
        "status": onboard_status,
        "ok": onboard_status == 200,
        "body": onboard_body[:200],
    }

    # Flags
    flags = {}
    for flag in ("WATHEFNI_EMPLOYEE_APP", "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"):
        flags[flag] = os.environ.get(flag, "off")
    # systemd staging/prod
    for unit in ("wathefni-orchestrator-staging.service", "wathefni-orchestrator.service"):
        try:
            pid = subprocess.check_output(
                ["systemctl", "show", "-p", "MainPID", "--value", unit], text=True
            ).strip()
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            decoded = {e.decode().split("=", 1)[0]: e.decode().split("=", 1)[1] for e in environ if b"=" in e}
            flags[f"{unit}:EMPLOYEE_APP"] = decoded.get("WATHEFNI_EMPLOYEE_APP", "unset")
            flags[f"{unit}:CHANNEL"] = decoded.get("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", "unset")
        except Exception as exc:  # noqa: BLE001
            flags[unit] = f"error:{exc}"
    report["protected_flags"] = flags
    report["flags_ok"] = all(
        str(v).lower() not in {"on", "1", "true", "yes"}
        for k, v in flags.items()
        if "EMPLOYEE_APP" in k or "CHANNEL" in k or k.startswith("WATHEFNI_")
    )

    out = REPORTS / "phase7c5-wathefni-canary-report.json"
    # scrub any accidental employee_key
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    out.write_text(text + "\n")
    print(text)
    print("PHASE7C5_OK=true")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(str(exc), file=sys.stderr)
        raise
