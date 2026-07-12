#!/usr/bin/env python3
"""Phase 7C.4 staging throwaway apply verifier — P7C4STG01 only.

Applies W1–W4 one-by-one under 7C.3 gates + canary caps.
Refuses staging WATHEFNI and production DSN apply.
Cleans up only P7C4STG01 fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

COMPANY = "P7C4STG01"
OPS = Path(__file__).resolve().parent
CLI = OPS / "staging-phase7c4-reconcile-docs.py"
POSTGRES_ENV = os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def sample_id(employee_key: str) -> str:
    return "emp_" + hashlib.sha256(str(employee_key).encode()).hexdigest()[:12]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect_rw():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    load_env(Path(POSTGRES_ENV))
    dsn = os.environ["WATHEFNI_DATABASE_URL"]
    if "staging" not in dsn.lower():
        raise SystemExit("refusing verifier against non-staging DSN")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def cleanup(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT employee_key FROM employees WHERE company_code=%s", (COMPANY,))
        keys = [str(r["employee_key"]) for r in cur.fetchall()]
        if keys:
            cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (keys,))
            cur.execute("DELETE FROM employee_documents WHERE employee_key = ANY(%s)", (keys,))
            cur.execute("DELETE FROM compliance_documents WHERE employee_key = ANY(%s)", (keys,))
            cur.execute(
                "DELETE FROM file_registry WHERE company_code=%s OR subject_key = ANY(%s)",
                (COMPANY, keys),
            )
            cur.execute("DELETE FROM employees WHERE company_code=%s", (COMPANY,))
        cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
        cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
    conn.commit()


def ensure_company(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO companies (company_code, name, country, metadata, raw_json, status)
            VALUES (%s, %s, 'KW', '{}'::jsonb, '{}'::jsonb, 'active')
            ON CONFLICT (company_code) DO UPDATE SET name=EXCLUDED.name, status='active', updated_at=now()
            """,
            (COMPANY, "Phase 7C.4 Throwaway"),
        )
    conn.commit()


def insert_employee(cur, key: str, phone: str) -> None:
    cur.execute(
        """
        INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status)
        VALUES (%s,%s,%s,%s,'in_progress')
        ON CONFLICT (employee_key) DO UPDATE SET phone=EXCLUDED.phone, company_code=EXCLUDED.company_code
        """,
        (key, phone, COMPANY, f"P7C4 {phone[-4:]}"),
    )


def insert_oi(cur, key: str, item_id: str, status: str) -> None:
    cur.execute(
        """
        INSERT INTO onboarding_items (
            employee_key, item_id, label, item_type, required, document_type, status, raw_json
        ) VALUES (%s,%s,%s,'document',true,%s,%s,'{}'::jsonb)
        ON CONFLICT (employee_key, item_id) DO UPDATE SET status=EXCLUDED.status
        """,
        (key, item_id, item_id, item_id, status),
    )


def insert_ed(cur, key: str, phone: str, *, item_id: str, document_type: str, expiry=None, sha=None) -> None:
    cur.execute(
        """
        INSERT INTO employee_documents (
            employee_key, phone, company_code, item_id, document_type, status,
            expiry_date, content_sha256, storage_status, metadata, raw_json
        ) VALUES (%s,%s,%s,%s,%s,'received',%s,%s,'stored','{}'::jsonb,'{}'::jsonb)
        """,
        (key, phone, COMPANY, item_id, document_type, expiry, sha),
    )


def insert_cd(cur, key: str, *, document_type: str, status: str, expiry=None) -> None:
    days = (expiry - date.today()).days if expiry else None
    cur.execute(
        """
        INSERT INTO compliance_documents (
            employee_key, document_type, label, status, expiry_date, days_until_expiry,
            company_code, raw_json
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)
        ON CONFLICT (employee_key, document_type) DO UPDATE
          SET status=EXCLUDED.status, expiry_date=EXCLUDED.expiry_date,
              days_until_expiry=EXCLUDED.days_until_expiry, company_code=EXCLUDED.company_code
        """,
        (key, document_type, document_type, status, expiry, days, COMPANY),
    )


def insert_file(cur, key: str, *, document_type: str, sha: str) -> None:
    cur.execute(
        """
        INSERT INTO file_registry (
            company_code, subject_type, subject_key, file_kind, document_type,
            storage_provider, content_sha256, storage_status, metadata, raw_json
        ) VALUES (%s,'employee',%s,'employee_document',%s,'local',%s,'stored',%s::jsonb,'{}'::jsonb)
        """,
        (COMPANY, key, document_type, sha, json.dumps({"item_id": document_type})),
    )


def company_counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        out = {}
        for name, sql in [
            ("employees", "SELECT count(*) n FROM employees WHERE company_code=%s"),
            ("employee_documents", "SELECT count(*) n FROM employee_documents WHERE company_code=%s"),
            ("compliance_documents", "SELECT count(*) n FROM compliance_documents WHERE company_code=%s"),
            ("file_registry", "SELECT count(*) n FROM file_registry WHERE company_code=%s"),
            (
                "onboarding_items",
                "SELECT count(*) n FROM onboarding_items oi JOIN employees e ON e.employee_key=oi.employee_key WHERE e.company_code=%s",
            ),
        ]:
            cur.execute(sql, (COMPANY,))
            out[name] = int((cur.fetchone() or {}).get("n") or 0)
    return out


def other_company_doc_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM employee_documents WHERE company_code<>%s)
            + (SELECT count(*) FROM compliance_documents WHERE company_code<>%s AND company_code IS NOT NULL)
            AS n
            """,
            (COMPANY, COMPANY),
        )
        return int((cur.fetchone() or {}).get("n") or 0)


def run_cli(args: list[str], *, env_extra: dict[str, str] | None = None, apply_env: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["WATHEFNI_POSTGRES_ENV"] = POSTGRES_ENV
    env.pop("WATHEFNI_RECONCILE_APPLY", None)
    if apply_env:
        env["WATHEFNI_RECONCILE_APPLY"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(CLI), "--postgres-env", POSTGRES_ENV, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def dry_run(sid: str, doc_type: str) -> tuple[dict, list[dict], str, str, str]:
    plan_path = Path(f"/tmp/p7c4-plan-{uuid.uuid4().hex}.jsonl")
    sum_path = Path(f"/tmp/p7c4-sum-{uuid.uuid4().hex}.json")
    proc = run_cli(
        [
            "--company", COMPANY,
            "--mode", "dry-run",
            "--employee-sample-id", sid,
            "--document-type", doc_type,
            "--jsonl-out", str(plan_path),
            "--summary-out", str(sum_path),
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr + proc.stdout)
    summary = json.loads(sum_path.read_text())
    events = []
    if plan_path.exists() and plan_path.read_text().strip():
        events = [json.loads(l) for l in plan_path.read_text().splitlines() if l.strip()]
    return summary, events, summary["apply_token"], summary["plan_hash"], summary["apply_token_expires_at"]


def apply_canary(
    sid: str,
    doc_type: str,
    token: str,
    plan_hash: str,
    expires_at: str,
    *,
    max_writes: int = 1,
    env_extra=None,
    apply_env=True,
    extra_args=None,
) -> tuple[subprocess.CompletedProcess, dict, list[dict]]:
    apply_path = Path(f"/tmp/p7c4-apply-{uuid.uuid4().hex}.jsonl")
    sum_path = Path(f"/tmp/p7c4-apply-sum-{uuid.uuid4().hex}.json")
    args = [
        "--company", COMPANY,
        "--mode", "apply",
        "--confirm-company", COMPANY,
        "--i-understand-writes",
        "--confirm-apply-token", token,
        "--apply-token-expires-at", expires_at,
        "--expect-plan-hash", plan_hash,
        "--employee-sample-id", sid,
        "--document-type", doc_type,
        "--max-writes", str(max_writes),
        "--apply-jsonl-out", str(apply_path),
        "--summary-out", str(sum_path),
    ]
    if extra_args:
        args.extend(extra_args)
    proc = run_cli(args, env_extra=env_extra, apply_env=apply_env)
    summary = json.loads(sum_path.read_text()) if sum_path.exists() else {}
    events = []
    if apply_path.exists() and apply_path.read_text().strip():
        events = [json.loads(l) for l in apply_path.read_text().splitlines() if l.strip()]
    if proc.returncode != 0 and not summary:
        summary = {"_stderr": (proc.stderr or "")[-500:], "_stdout": (proc.stdout or "")[-500:]}
    return proc, summary, events


def snapshot_oi(conn, key: str, item_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
            (key, item_id),
        )
        row = cur.fetchone() or {}
        return {"status": row.get("status")}


def snapshot_ed(conn, key: str, dt: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, expiry_date::text AS expiry_date FROM employee_documents WHERE employee_key=%s AND document_type=%s ORDER BY updated_at DESC LIMIT 1",
            (key, dt),
        )
        return dict(cur.fetchone() or {})


def snapshot_cd(conn, key: str, dt: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, expiry_date::text AS expiry_date FROM compliance_documents WHERE employee_key=%s AND document_type=%s",
            (key, dt),
        )
        return dict(cur.fetchone() or {})


def flag_off() -> tuple[bool, str]:
    details = []
    ok = True
    for flag in ("WATHEFNI_EMPLOYEE_APP", "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"):
        val = os.environ.get(flag, "off").strip().lower()
        details.append(f"{flag}={val or 'unset'}")
        if val in {"on", "1", "true", "yes"}:
            ok = False
    drop = Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d")
    if drop.exists():
        text = "\n".join(p.read_text() for p in drop.glob("*.conf"))
        for flag in ("WATHEFNI_EMPLOYEE_APP", "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"):
            if f"{flag}=on" in text.replace(" ", ""):
                ok = False
                details.append(f"dropin:{flag}=on")
    return ok, "; ".join(details)


def seed_all(conn) -> dict[str, dict[str, str]]:
    suffix = uuid.uuid4().hex[:6]
    older = date.today() + timedelta(days=30)
    newer = date.today() + timedelta(days=400)
    phones = {
        "w1": f"9657101{suffix[:4]}",
        "w2": f"9657102{suffix[:4]}",
        "w3": f"9657103{suffix[:4]}",
        "w4": f"9657104{suffix[:4]}",
        "max": f"9657105{suffix[:4]}",
        "alias": f"9657106{suffix[:4]}",
        "older": f"9657107{suffix[:4]}",
        "nullow": f"9657108{suffix[:4]}",
    }
    keys = {n: f"{COMPANY}-{p}" for n, p in phones.items()}
    with conn.cursor() as cur:
        for n, p in phones.items():
            insert_employee(cur, keys[n], p)

        # W1
        insert_oi(cur, keys["w1"], "civil_id", "pending")
        insert_ed(cur, keys["w1"], phones["w1"], item_id="civil_id", document_type="civil_id", sha="1" * 64)
        insert_file(cur, keys["w1"], document_type="civil_id", sha="1" * 64)

        # W2
        insert_cd(cur, keys["w2"], document_type="medical", status="received")
        insert_file(cur, keys["w2"], document_type="medical", sha="2" * 64)

        # W3
        insert_oi(cur, keys["w3"], "passport", "received")
        insert_ed(cur, keys["w3"], phones["w3"], item_id="passport", document_type="passport", expiry=older, sha="3" * 64)
        insert_file(cur, keys["w3"], document_type="passport", sha="3" * 64)
        insert_cd(cur, keys["w3"], document_type="passport", status="valid", expiry=newer)

        # W4
        insert_oi(cur, keys["w4"], "education_cert", "received")
        insert_ed(cur, keys["w4"], phones["w4"], item_id="education_cert", document_type="education_cert", expiry=newer, sha="4" * 64)
        insert_file(cur, keys["w4"], document_type="education_cert", sha="4" * 64)
        insert_cd(cur, keys["w4"], document_type="education_cert", status="received", expiry=None)

        # max-writes: pending OI + expiry mismatch → 2 plans
        insert_oi(cur, keys["max"], "civil_id", "pending")
        insert_ed(cur, keys["max"], phones["max"], item_id="civil_id", document_type="civil_id", expiry=older, sha="5" * 64)
        insert_file(cur, keys["max"], document_type="civil_id", sha="5" * 64)
        insert_cd(cur, keys["max"], document_type="civil_id", status="valid", expiry=newer)

        # alias
        insert_oi(cur, keys["alias"], "residency_iqama", "pending")
        insert_ed(cur, keys["alias"], phones["alias"], item_id="residency_iqama", document_type="residency_iqama", sha="6" * 64)
        insert_file(cur, keys["alias"], document_type="residency_iqama", sha="6" * 64)
        insert_cd(cur, keys["alias"], document_type="residency", status="missing")

        # older overwrite target (ED already newer)
        insert_oi(cur, keys["older"], "passport", "received")
        insert_ed(cur, keys["older"], phones["older"], item_id="passport", document_type="passport", expiry=newer, sha="7" * 64)
        insert_file(cur, keys["older"], document_type="passport", sha="7" * 64)
        insert_cd(cur, keys["older"], document_type="passport", status="valid", expiry=older)

        # null overwrite target (compliance already has expiry)
        insert_oi(cur, keys["nullow"], "medical", "received")
        insert_ed(cur, keys["nullow"], phones["nullow"], item_id="medical", document_type="medical", expiry=newer, sha="8" * 64)
        insert_file(cur, keys["nullow"], document_type="medical", sha="8" * 64)
        insert_cd(cur, keys["nullow"], document_type="medical", status="valid", expiry=newer)

    conn.commit()
    return {n: {"key": keys[n], "phone": phones[n], "sid": sample_id(keys[n])} for n in keys}


def main() -> int:
    if not CLI.exists():
        raise SystemExit(f"missing CLI {CLI}")
    load_env(Path(POSTGRES_ENV))
    conn = connect_rw()
    reports = OPS / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    sample_audit = None

    try:
        cleanup(conn)
        ensure_company(conn)
        fixtures = seed_all(conn)
        other_baseline = other_company_doc_count(conn)

        # ---- W1 ----
        before = snapshot_oi(conn, fixtures["w1"]["key"], "civil_id")
        record("w1_before_pending", before.get("status") == "pending", str(before))
        sid, key = fixtures["w1"]["sid"], fixtures["w1"]["key"]
        summary, events, token, plan_hash, expires = dry_run(sid, "civil_id")
        plans = [e for e in events if e.get("decision") == "plan"]
        record("A1_w1_dryrun", summary.get("planned_writes") == 1 and plans[0]["action"] == "mark_onboarding_received", str(summary.get("planned_writes")))
        proc, apply_sum, apply_events = apply_canary(sid, "civil_id", token, plan_hash, expires)
        after = snapshot_oi(conn, key, "civil_id")
        sample_audit = apply_events[0] if apply_events else None
        record("A1_w1_apply", proc.returncode == 0 and apply_sum.get("applied") == 1 and after.get("status") == "received", json.dumps({"sum": apply_sum, "after": after})[:240])
        record("A1_w1_audit", bool(sample_audit) and sample_audit.get("decision") == "applied" and sample_audit.get("plan_hash") == plan_hash and sample_audit.get("rowcount") == 1, json.dumps(sample_audit or {}, sort_keys=True)[:260])
        record("A1_w1_before_after", before.get("status") == "pending" and after.get("status") == "received", f"{before}->{after}")
        re_sum, _, _, _, _ = dry_run(sid, "civil_id")
        record("A1_w1_redryrun", re_sum.get("planned_writes") == 0, str(re_sum.get("planned_writes")))

        # ---- W2 ----
        before_ed = snapshot_ed(conn, fixtures["w2"]["key"], "medical")
        record("w2_before_no_ed", not before_ed, str(before_ed))
        sid, key = fixtures["w2"]["sid"], fixtures["w2"]["key"]
        summary, events, token, plan_hash, expires = dry_run(sid, "medical")
        record("A2_w2_dryrun", summary.get("planned_writes") == 1, str(summary.get("planned_writes")))
        counts_before = company_counts(conn)
        proc, apply_sum, apply_events = apply_canary(sid, "medical", token, plan_hash, expires)
        after_ed = snapshot_ed(conn, key, "medical")
        counts_after = company_counts(conn)
        record("A2_w2_apply", proc.returncode == 0 and apply_sum.get("applied") == 1 and after_ed.get("status") == "received", json.dumps(apply_sum)[:200])
        record("A2_w2_audit", bool(apply_events) and apply_events[0].get("decision") == "applied" and apply_events[0].get("action") == "insert_employee_document_from_file", json.dumps(apply_events[0] if apply_events else {}, sort_keys=True)[:260])
        record("A2_w2_counts", counts_after["employee_documents"] == counts_before["employee_documents"] + 1, f"{counts_before}->{counts_after}")
        re_sum, _, _, _, _ = dry_run(sid, "medical")
        record("A2_w2_redryrun", re_sum.get("planned_writes") == 0, str(re_sum.get("planned_writes")))

        # ---- W3 ----
        sid, key = fixtures["w3"]["sid"], fixtures["w3"]["key"]
        before_ed = snapshot_ed(conn, key, "passport")
        summary, events, token, plan_hash, expires = dry_run(sid, "passport")
        plans = [e for e in events if e.get("decision") == "plan" and e.get("action") == "sync_expiry"]
        record("A3_w3_dryrun", len(plans) == 1 and plans[0].get("table") == "employee_documents", str(summary.get("planned_writes")))
        proc, apply_sum, apply_events = apply_canary(sid, "passport", token, plan_hash, expires)
        after_ed = snapshot_ed(conn, key, "passport")
        newer = (date.today() + timedelta(days=400)).isoformat()
        record("A3_w3_apply", proc.returncode == 0 and apply_sum.get("applied") == 1 and after_ed.get("expiry_date") == newer, f"{before_ed}->{after_ed} sum={apply_sum}")
        record("A3_w3_audit", bool(apply_events) and apply_events[0].get("decision") == "applied", json.dumps(apply_events[0] if apply_events else {}, sort_keys=True)[:260])
        re_sum, re_events, _, _, _ = dry_run(sid, "passport")
        re_sync = [e for e in re_events if e.get("decision") == "plan" and e.get("action") == "sync_expiry"]
        record("A3_w3_redryrun", len(re_sync) == 0, f"planned={re_sum.get('planned_writes')} sync_left={len(re_sync)}")

        # ---- W4 ----
        sid, key = fixtures["w4"]["sid"], fixtures["w4"]["key"]
        before_cd = snapshot_cd(conn, key, "education_cert")
        summary, events, token, plan_hash, expires = dry_run(sid, "education_cert")
        record("A4_w4_dryrun", summary.get("planned_writes") == 1, str(summary.get("planned_writes")))
        proc, apply_sum, apply_events = apply_canary(sid, "education_cert", token, plan_hash, expires)
        after_cd = snapshot_cd(conn, key, "education_cert")
        record("A4_w4_apply", proc.returncode == 0 and apply_sum.get("applied") == 1 and after_cd.get("expiry_date") == newer, f"{before_cd}->{after_cd}")
        record("A4_w4_audit", bool(apply_events) and apply_events[0].get("action") == "fill_compliance_expiry_from_ed", json.dumps(apply_events[0] if apply_events else {}, sort_keys=True)[:260])
        re_sum, _, _, _, _ = dry_run(sid, "education_cert")
        record("A4_w4_redryrun", re_sum.get("planned_writes") == 0, str(re_sum.get("planned_writes")))

        # Idempotent re-apply W1 scope (already fixed)
        sid = fixtures["w1"]["sid"]
        summary, _, token, plan_hash, expires = dry_run(sid, "civil_id")
        record("A5_idempotent_dryrun_empty", summary.get("planned_writes") == 0, str(summary.get("planned_writes")))
        if summary.get("planned_writes") == 0:
            # apply with empty plan should apply 0 — still need token/hash from empty plan
            proc, apply_sum, _ = apply_canary(sid, "civil_id", token, plan_hash, expires)
            record("A5_idempotent_apply_zero", proc.returncode == 0 and apply_sum.get("applied") == 0, json.dumps(apply_sum)[:200])

        # ---- Blocked cases ----
        sid = fixtures["max"]["sid"]
        summary, events, token, plan_hash, expires = dry_run(sid, "civil_id")
        record("B5_setup_two_plans", summary.get("planned_writes", 0) >= 2, str(summary.get("planned_writes")))
        before_oi = snapshot_oi(conn, fixtures["max"]["key"], "civil_id")
        proc, _, _ = apply_canary(sid, "civil_id", token, plan_hash, expires, max_writes=1)
        after_oi = snapshot_oi(conn, fixtures["max"]["key"], "civil_id")
        record("B5_max_writes_exceeded", proc.returncode != 0 and before_oi == after_oi and "max-writes exceeded" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-200:])

        # missing env
        sid = fixtures["alias"]["sid"]
        summary, _, token, plan_hash, expires = dry_run(sid, "residency_iqama")
        proc, _, _ = apply_canary(sid, "residency_iqama", token, plan_hash, expires, apply_env=False)
        record("B1_missing_env_gate", proc.returncode != 0 and "WATHEFNI_RECONCILE_APPLY" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-180:])

        # wrong token (fresh dry-run so hash/token pair is valid except token)
        summary, _, token, plan_hash, expires = dry_run(sid, "residency_iqama")
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "apply",
                "--confirm-company", COMPANY, "--i-understand-writes",
                "--confirm-apply-token", "deadbeef",
                "--apply-token-expires-at", expires,
                "--expect-plan-hash", plan_hash,
                "--employee-sample-id", sid, "--document-type", "residency_iqama",
                "--max-writes", "1",
            ],
            apply_env=True,
        )
        record("B2_wrong_token", proc.returncode != 0 and "wrong apply token" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-160:])

        # wrong plan hash
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "apply",
                "--confirm-company", COMPANY, "--i-understand-writes",
                "--confirm-apply-token", token,
                "--apply-token-expires-at", expires,
                "--expect-plan-hash", "0" * 64,
                "--employee-sample-id", sid, "--document-type", "residency_iqama",
                "--max-writes", "1",
            ],
            apply_env=True,
        )
        record("B3_wrong_plan_hash", proc.returncode != 0 and "wrong plan hash" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-160:])

        # missing confirm flags
        proc = run_cli(
            [
                "--company", COMPANY, "--mode", "apply",
                "--confirm-apply-token", token,
                "--expect-plan-hash", plan_hash,
                "--employee-sample-id", sid, "--document-type", "residency_iqama",
                "--max-writes", "1",
            ],
            apply_env=True,
        )
        record("B4_missing_confirm_flags", proc.returncode != 0, (proc.stderr + proc.stdout)[-160:])

        # ALL
        proc = run_cli(["--company", "ALL", "--mode", "dry-run"])
        record("B4b_refuse_ALL", proc.returncode != 0 and "ALL" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-120:])

        # alias merge — dry-run should be manual_only needs_operator_map; no merge plan
        sid = fixtures["alias"]["sid"]
        summary, events, _, _, _ = dry_run(sid, "residency_iqama")
        merge_plans = [e for e in events if e.get("decision") == "plan" and (e.get("guards") or {}).get("alias_merge")]
        map_ev = [e for e in events if e.get("skip_reason") == "needs_operator_map"]
        # company-wide dry-run for alias family
        plan_path = Path(f"/tmp/p7c4-alias-{uuid.uuid4().hex}.jsonl")
        sum_path = Path(f"/tmp/p7c4-alias-{uuid.uuid4().hex}.json")
        proc = run_cli(["--company", COMPANY, "--jsonl-out", str(plan_path), "--summary-out", str(sum_path)])
        all_events = [json.loads(l) for l in plan_path.read_text().splitlines() if l.strip()] if plan_path.exists() else []
        map_ev = [e for e in all_events if e.get("sample_id") == sid and e.get("skip_reason") == "needs_operator_map"]
        merge_plans = [e for e in all_events if e.get("sample_id") == sid and (e.get("guards") or {}).get("alias_merge") is True]
        record("B6_alias_no_merge", len(map_ev) >= 1 and len(merge_plans) == 0, f"map={len(map_ev)} merge={len(merge_plans)}")

        # older expiry overwrite via direct executor
        import importlib.util
        spec = importlib.util.spec_from_file_location("p7c4cli", CLI)
        cli = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cli)
        key = fixtures["older"]["key"]
        before_ed = snapshot_ed(conn, key, "passport")
        with conn.cursor() as cur:
            fake = {
                "action": "sync_expiry",
                "table": "employee_documents",
                "natural_key": {"document_type": "passport"},
                "before": {"expiry_date": before_ed.get("expiry_date")},
                "after": {"expiry_date": (date.today() + timedelta(days=30)).isoformat()},
            }
            try:
                cli.execute_plan_event(cur, COMPANY, key, fake)
                conn.rollback()
                older_blocked = False
                err = "no-raise"
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                older_blocked = "expiry_older_than_existing" in str(exc)
                err = str(exc)
        after_ed = snapshot_ed(conn, key, "passport")
        record("B7_older_expiry_overwrite_blocked", older_blocked and before_ed == after_ed, err)

        # null overwrite
        key = fixtures["nullow"]["key"]
        before_cd = snapshot_cd(conn, key, "medical")
        with conn.cursor() as cur:
            fake = {
                "action": "sync_expiry",
                "table": "compliance_documents",
                "natural_key": {"document_type": "medical"},
                "before": {"expiry_date": before_cd.get("expiry_date")},
                "after": {"expiry_date": None},
            }
            try:
                cli.execute_plan_event(cur, COMPANY, key, fake)
                conn.rollback()
                null_blocked = False
                err = "no-raise"
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                null_blocked = "expiry_candidate_null" in str(exc)
                err = str(exc)
        after_cd = snapshot_cd(conn, key, "medical")
        record("B8_null_overwrite_blocked", null_blocked and before_cd == after_cd, err)

        # staging WATHEFNI refused
        proc = run_cli(
            [
                "--company", "WATHEFNI", "--mode", "apply",
                "--confirm-company", "WATHEFNI", "--i-understand-writes",
                "--confirm-apply-token", "x", "--expect-plan-hash", "y",
                "--employee-sample-id", "emp_test", "--document-type", "civil_id",
                "--max-writes", "1",
            ],
            apply_env=True,
        )
        record("B9_refuse_staging_WATHEFNI", proc.returncode != 0 and "WATHEFNI" in (proc.stderr + proc.stdout), (proc.stderr + proc.stdout)[-180:])

        # production DSN refused
        prod_env = "/root/.openclaw/secrets/postgres.env"
        if Path(prod_env).exists():
            proc = subprocess.run(
                [
                    sys.executable, str(CLI),
                    "--postgres-env", prod_env,
                    "--company", COMPANY, "--mode", "apply",
                    "--confirm-company", COMPANY, "--i-understand-writes",
                    "--confirm-apply-token", "x", "--expect-plan-hash", "y",
                    "--employee-sample-id", "emp_test", "--document-type", "civil_id",
                    "--max-writes", "1",
                ],
                capture_output=True, text=True,
                env={
                    **{k: v for k, v in os.environ.items() if k != "WATHEFNI_DATABASE_URL"},
                    "WATHEFNI_RECONCILE_APPLY": "1",
                },
            )
            out = (proc.stderr + proc.stdout).lower()
            record(
                "B10_refuse_production_dsn",
                proc.returncode != 0 and ("production" in out or "non-staging" in out or "refusing" in out),
                (proc.stderr + proc.stdout)[-180:],
            )
        else:
            record("B10_refuse_production_dsn", True, "postgres.env missing; skipped live probe")

        other_final = other_company_doc_count(conn)
        record("scope_only_P7C4STG01", other_baseline == other_final, f"other_baseline={other_baseline} other_final={other_final} local={company_counts(conn)}")

        flags_ok, flags_detail = flag_off()
        record("F1_protected_flags_off", flags_ok, flags_detail)

        if sample_audit:
            (reports / "phase7c4-apply-audit-sample.json").write_text(json.dumps(sample_audit, indent=2, sort_keys=True) + "\n")
        (reports / "phase7c4-verifier-summary.json").write_text(
            json.dumps({"results": [{"label": l, "ok": ok, "detail": d} for l, ok, d in RESULTS]}, indent=2) + "\n"
        )

    finally:
        try:
            cleanup(conn)
        finally:
            conn.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\nRESULT {passed}/{len(RESULTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
