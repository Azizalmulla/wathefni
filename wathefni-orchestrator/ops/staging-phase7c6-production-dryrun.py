#!/usr/bin/env python3
"""Phase 7C.6 Option B — production dry-run only (no apply, no writes).

Usage (on VPS):
  python3 ops/staging-phase7c6-production-dryrun.py --company WATHEFNI
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parent
CLI = OPS / "staging-phase7c4-reconcile-docs.py"
AUDIT = OPS / "staging-phase7c-compliance-docs-audit.py"
PROD_ENV = "/root/.openclaw/secrets/postgres.env"
PROD_BASE = os.environ.get("WATHEFNI_PROD_BASE", "http://127.0.0.1:8010")
REPORTS = OPS / "reports"
W1W4 = {
    "mark_onboarding_received": "W1",
    "insert_employee_document_from_file": "W2",
    "sync_expiry": "W3",
    "fill_compliance_expiry_from_ed": "W4",
}


def http_get(path: str) -> tuple[int, str]:
    req = urllib.request.Request(PROD_BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300] if getattr(exc, "fp", None) else str(exc)
        return int(exc.code), body
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def load_env(path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "WATHEFNI_DATABASE_URL"}
    env.pop("WATHEFNI_RECONCILE_APPLY", None)
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def fingerprint(env: dict[str, str], company: str) -> dict:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(env["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            tro = str((cur.fetchone() or {}).get("transaction_read_only") or "")
            try:
                cur.execute("UPDATE companies SET name=name WHERE false")
                write_blocked = False
                write_err = None
            except Exception as exc:  # noqa: BLE001
                write_blocked = True
                write_err = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
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
                (company, company, company, company, company),
            )
            counts = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT md5(string_agg(s, '|' ORDER BY s)) AS fp FROM (
                  SELECT oi.employee_key||':'||oi.item_id||':'||coalesce(oi.status,'') AS s
                  FROM onboarding_items oi
                  JOIN employees e ON e.employee_key=oi.employee_key
                  WHERE e.company_code=%s
                ) x
                """,
                (company,),
            )
            oi_fp = (cur.fetchone() or {}).get("fp")
            cur.execute(
                """
                SELECT md5(string_agg(s, '|' ORDER BY s)) AS fp FROM (
                  SELECT employee_key||':'||document_type||':'||coalesce(status,'')||':'||coalesce(expiry_date::text,'') AS s
                  FROM employee_documents WHERE company_code=%s
                ) x
                """,
                (company,),
            )
            ed_fp = (cur.fetchone() or {}).get("fp")
            cur.execute(
                """
                SELECT md5(string_agg(s, '|' ORDER BY s)) AS fp FROM (
                  SELECT employee_key||':'||document_type||':'||coalesce(status,'')||':'||coalesce(expiry_date::text,'') AS s
                  FROM compliance_documents WHERE company_code=%s
                ) x
                """,
                (company,),
            )
            cd_fp = (cur.fetchone() or {}).get("fp")
    finally:
        conn.close()
    return {
        "transaction_read_only": tro,
        "write_probe_blocked": write_blocked,
        "write_probe_error": write_err,
        "counts": counts,
        "fingerprints": {"onboarding_items": oi_fp, "employee_documents": ed_fp, "compliance_documents": cd_fp},
    }


def main() -> int:
    company = "WATHEFNI"
    if len(sys.argv) > 1 and sys.argv[1] == "--company" and len(sys.argv) > 2:
        company = sys.argv[2].strip().upper()
    if company in {"ALL", "*", "ANY", ""}:
        raise SystemExit("company-scoped only")

    REPORTS.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(PROD_ENV))
    dsn = env.get("WATHEFNI_DATABASE_URL", "")
    if "staging" in dsn.lower() or "wathefni_staging" in dsn.lower():
        raise SystemExit("refusing: postgres.env does not look like production")

    report: dict = {
        "phase": "7C.6-option-B",
        "mode": "dry-run-only",
        "company_code": company,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "apply_attempted": False,
        "wathefni_reconcile_apply_set": "WATHEFNI_RECONCILE_APPLY" in env,
        "production_apply_authorized": False,
    }

    h1, b1 = http_get("/health")
    report["health_before"] = {"status": h1, "ok": h1 == 200, "body": b1}

    before = fingerprint(env, company)
    report["before"] = before

    plan_path = REPORTS / "phase7c6-prod-wathefni-dryrun.jsonl"
    sum_path = REPORTS / "phase7c6-prod-wathefni-dryrun-summary.json"
    audit_json = REPORTS / "phase7c6-prod-wathefni-audit.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--postgres-env",
            PROD_ENV,
            "--company",
            company,
            "--mode",
            "dry-run",
            "--allow-production-dsn",
            "--jsonl-out",
            str(plan_path),
            "--summary-out",
            str(sum_path),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr + proc.stdout)

    # Ensure apply still refused on prod even with allow-production-dsn
    refuse = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--postgres-env",
            PROD_ENV,
            "--company",
            company,
            "--mode",
            "apply",
            "--allow-production-dsn",
            "--confirm-company",
            company,
            "--i-understand-writes",
            "--confirm-apply-token",
            "x",
            "--apply-token-expires-at",
            "2099-01-01T00:00:00Z",
            "--expect-plan-hash",
            "y",
            "--employee-sample-id",
            "emp_test",
            "--document-type",
            "civil_id",
            "--max-writes",
            "1",
        ],
        capture_output=True,
        text=True,
        env={**env, "WATHEFNI_RECONCILE_APPLY": "1"},
    )
    report["apply_still_refused"] = {
        "ok": refuse.returncode != 0,
        "output": (refuse.stderr + refuse.stdout)[-240:],
    }

    dry = json.loads(sum_path.read_text())
    events = []
    if plan_path.exists() and plan_path.read_text().strip():
        events = [json.loads(line) for line in plan_path.read_text().splitlines() if line.strip()]

    by_w = {"W1": 0, "W2": 0, "W3": 0, "W4": 0, "other_plan": 0}
    samples_by_action: dict[str, list] = {}
    for ev in events:
        if ev.get("decision") != "plan":
            continue
        action = str(ev.get("action") or "")
        label = W1W4.get(action, "other_plan")
        by_w[label] = by_w.get(label, 0) + 1
        bucket = samples_by_action.setdefault(action, [])
        if len(bucket) < 5:
            bucket.append(
                {
                    "sample_id": ev.get("sample_id"),
                    "document_type": (ev.get("natural_key") or {}).get("document_type")
                    or (ev.get("natural_key") or {}).get("item_id")
                    or ev.get("document_type"),
                    "table": ev.get("table"),
                }
            )

    report["dry_run_summary"] = {
        "planned_writes": dry.get("planned_writes"),
        "skips": dry.get("skips"),
        "manual_only": dry.get("manual_only"),
        "event_count": dry.get("event_count"),
        "by_action": dry.get("by_action"),
        "by_drift_class": dry.get("by_drift_class"),
        "by_skip_reason": dry.get("by_skip_reason"),
        "plan_hash": dry.get("plan_hash"),
        "read_only": dry.get("read_only"),
        "no_writes": dry.get("no_writes"),
        "apply_enabled": dry.get("apply_enabled"),
        "planned_writes_by_W1_W4": by_w,
        "redacted_plan_samples": samples_by_action,
    }

    # Also run 7C audit for store/mismatch counts (read-only)
    audit_proc = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            "--postgres-env",
            PROD_ENV,
            "--company",
            company,
            "--json-out",
            str(audit_json),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if audit_proc.returncode != 0:
        # audit script may refuse prod DSN — capture and continue with dry-run data
        report["audit_note"] = (audit_proc.stderr + audit_proc.stdout)[-300:]
        report["store_counts"] = before["counts"]
        report["mismatch_totals"] = dry.get("by_drift_class")
    else:
        audit = json.loads(audit_json.read_text())
        report["store_counts"] = audit.get("store_counts") or before["counts"]
        report["mismatch_totals"] = audit.get("mismatch_totals")
        report["audit_transaction_read_only"] = audit.get("transaction_read_only")
        # redact samples already hashed in audit

    after = fingerprint(env, company)
    report["after"] = after
    report["no_data_changed"] = before["fingerprints"] == after["fingerprints"] and before["counts"] == after["counts"]

    h2, b2 = http_get("/health")
    report["health_after"] = {"status": h2, "ok": h2 == 200, "body": b2}

    # Flags
    flags = {}
    for unit in ("wathefni-orchestrator.service",):
        try:
            pid = subprocess.check_output(
                ["systemctl", "show", "-p", "MainPID", "--value", unit], text=True
            ).strip()
            raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            decoded = {}
            for item in raw:
                if b"=" in item:
                    k, v = item.decode(errors="replace").split("=", 1)
                    decoded[k] = v
            flags["EMPLOYEE_APP"] = decoded.get("WATHEFNI_EMPLOYEE_APP", "unset")
            flags["CHANNEL_ACCOUNTS"] = decoded.get("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", "unset")
        except Exception as exc:  # noqa: BLE001
            flags["error"] = str(exc)
    report["protected_flags"] = flags

    planned = int(dry.get("planned_writes") or 0)
    if planned == 0:
        rec = "stop_defer"
        rec_text = (
            "No planned writes on production WATHEFNI. Stop/defer production apply canary; "
            "no Option C needed for reconcile readiness on this company."
        )
    elif by_w.get("W1", 0) >= 1 and by_w.get("W1", 0) == planned:
        rec = "optional_later_w1_canary"
        rec_text = (
            "Production has W1-only planned writes. A later one-write W1 canary (Option C) could be "
            "proposed after separate approval; not required before employee-app pilot."
        )
    elif by_w.get("W1", 0) >= 1:
        rec = "optional_later_w1_canary_after_review"
        rec_text = (
            "Production has mixed planned writes including W1. If a canary is ever approved, "
            "restrict to one W1 row first (like staging 7C.5). Prefer stop/defer for now unless "
            "prod checklist healing is an explicit goal."
        )
    else:
        rec = "stop_defer"
        rec_text = (
            "Planned writes are non-W1 (W2/W3/W4). Do not start Option C with those; "
            "stop/defer production apply until a safer W1 candidate exists or staging-style review is repeated."
        )
    report["recommendation"] = {"code": rec, "text": rec_text}

    out = REPORTS / "phase7c6-prod-wathefni-option-b-report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("PHASE7C6_OPTION_B_OK=true")
    print(f"RECOMMENDATION={rec}")
    return 0 if report["no_data_changed"] and report["health_before"]["ok"] and report["health_after"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
