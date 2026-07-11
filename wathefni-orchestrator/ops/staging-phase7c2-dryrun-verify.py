#!/usr/bin/env python3
"""Phase 7C.2 staging throwaway verifier — dry-run planner only.

Seeds company P7C2STG01, runs the dry-run planner, asserts plan shapes.
Does NOT enable apply mode. Cleans up only P7C2STG01 fixtures it creates.

Keep OFF: WATHEFNI_EMPLOYEE_APP, WATHEFNI_COMPANY_CHANNEL_ACCOUNTS.
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

COMPANY = "P7C2STG01"
OPS = Path(__file__).resolve().parent
PLANNER = OPS / "staging-phase7c2-reconcile-docs-dryrun.py"
AUDIT = OPS / "staging-phase7c-compliance-docs-audit.py"
POSTGRES_ENV = os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def sample_id(employee_key: str) -> str:
    digest = hashlib.sha256(str(employee_key).encode("utf-8")).hexdigest()[:12]
    return f"emp_{digest}"


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


def emp_key(suffix: str, phone: str) -> str:
    return f"{COMPANY}-{phone}"


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
            (COMPANY, "Phase 7C.2 Throwaway"),
        )
    conn.commit()


def insert_employee(cur, key: str, phone: str) -> None:
    cur.execute(
        """
        INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status)
        VALUES (%s, %s, %s, %s, 'in_progress')
        ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone
        """,
        (key, phone, COMPANY, f"P7C2 {phone[-4:]}"),
    )


def insert_oi(cur, key: str, item_id: str, status: str, document_type: str | None = None) -> None:
    cur.execute(
        """
        INSERT INTO onboarding_items (
            employee_key, item_id, label, item_type, required, document_type, status, raw_json
        ) VALUES (%s,%s,%s,'document',true,%s,%s,'{}'::jsonb)
        ON CONFLICT (employee_key, item_id) DO UPDATE SET status=EXCLUDED.status, document_type=EXCLUDED.document_type
        """,
        (key, item_id, item_id, document_type or item_id, status),
    )


def insert_ed(
    cur,
    key: str,
    phone: str,
    *,
    item_id: str,
    document_type: str,
    status: str = "received",
    expiry: date | None = None,
    sha: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO employee_documents (
            employee_key, phone, company_code, item_id, document_type, status,
            expiry_date, content_sha256, storage_status, metadata, raw_json
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'stored','{}'::jsonb,'{}'::jsonb)
        """,
        (key, phone, COMPANY, item_id, document_type, status, expiry, sha),
    )


def insert_cd(
    cur,
    key: str,
    *,
    document_type: str,
    status: str,
    expiry: date | None = None,
) -> None:
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


def seed_fixtures(conn) -> dict[str, str]:
    """Create one employee per scenario. Returns map scenario -> employee_key."""
    suffix = uuid.uuid4().hex[:6]
    phones = {
        "w1": f"9657001{suffix[:4]}",
        "w2_file": f"9657002{suffix[:4]}",
        "w2_nofile": f"9657003{suffix[:4]}",
        "w3_newer": f"9657004{suffix[:4]}",
        "w3_older": f"9657005{suffix[:4]}",
        "w4_fill": f"9657006{suffix[:4]}",
        "w4_nosrc": f"9657007{suffix[:4]}",
        "alias": f"9657008{suffix[:4]}",
        "consistent": f"9657009{suffix[:4]}",
    }
    keys = {name: emp_key(name, phone) for name, phone in phones.items()}
    older = date.today() + timedelta(days=30)
    newer = date.today() + timedelta(days=400)

    with conn.cursor() as cur:
        for name, phone in phones.items():
            insert_employee(cur, keys[name], phone)

        # Case 3 / W1: ED received, OI pending
        insert_oi(cur, keys["w1"], "civil_id", "pending")
        insert_ed(
            cur, keys["w1"], phones["w1"],
            item_id="civil_id", document_type="civil_id", sha="b" * 64,
        )
        insert_file(cur, keys["w1"], document_type="civil_id", sha="b" * 64)

        # Case 4: compliance orphan + file (intentional orphan file until apply)
        insert_cd(cur, keys["w2_file"], document_type="medical", status="received", expiry=None)
        insert_file(cur, keys["w2_file"], document_type="medical", sha="a" * 64)

        # Case 5: compliance orphan, no file
        insert_cd(cur, keys["w2_nofile"], document_type="passport", status="valid", expiry=newer)

        # Case 6: ED older, compliance newer → plan sync ED + skip older
        insert_oi(cur, keys["w3_newer"], "civil_id", "received")
        insert_ed(
            cur, keys["w3_newer"], phones["w3_newer"],
            item_id="civil_id", document_type="civil_id", expiry=older, sha="c" * 64,
        )
        insert_file(cur, keys["w3_newer"], document_type="civil_id", sha="c" * 64)
        insert_cd(cur, keys["w3_newer"], document_type="civil_id", status="valid", expiry=newer)

        # Case 7: ED newer, compliance older → plan sync CD + skip older
        insert_oi(cur, keys["w3_older"], "passport", "received")
        insert_ed(
            cur, keys["w3_older"], phones["w3_older"],
            item_id="passport", document_type="passport", expiry=newer, sha="d" * 64,
        )
        insert_file(cur, keys["w3_older"], document_type="passport", sha="d" * 64)
        insert_cd(cur, keys["w3_older"], document_type="passport", status="valid", expiry=older)

        # Case 8: null compliance expiry, ED has date
        insert_oi(cur, keys["w4_fill"], "education_cert", "received")
        insert_ed(
            cur, keys["w4_fill"], phones["w4_fill"],
            item_id="education_cert", document_type="education_cert", expiry=newer, sha="e" * 64,
        )
        insert_file(cur, keys["w4_fill"], document_type="education_cert", sha="e" * 64)
        insert_cd(cur, keys["w4_fill"], document_type="education_cert", status="received", expiry=None)

        # Case 9: both null expiry
        insert_oi(cur, keys["w4_nosrc"], "medical", "received")
        insert_ed(
            cur, keys["w4_nosrc"], phones["w4_nosrc"],
            item_id="medical", document_type="medical", expiry=None, sha="f" * 64,
        )
        insert_file(cur, keys["w4_nosrc"], document_type="medical", sha="f" * 64)
        insert_cd(cur, keys["w4_nosrc"], document_type="medical", status="received", expiry=None)

        # Case 10: alias coexistence
        insert_oi(cur, keys["alias"], "residency_iqama", "pending")
        insert_cd(cur, keys["alias"], document_type="residency", status="missing", expiry=None)
        insert_ed(
            cur, keys["alias"], phones["alias"],
            item_id="residency_iqama", document_type="residency_iqama", sha="g" * 64,
        )
        insert_file(cur, keys["alias"], document_type="residency_iqama", sha="g" * 64)

        # Case 11: already consistent
        insert_oi(cur, keys["consistent"], "civil_id", "received")
        insert_ed(
            cur, keys["consistent"], phones["consistent"],
            item_id="civil_id", document_type="civil_id", expiry=newer, sha="h" * 64,
        )
        insert_file(cur, keys["consistent"], document_type="civil_id", sha="h" * 64)
        insert_cd(cur, keys["consistent"], document_type="civil_id", status="valid", expiry=newer)

    conn.commit()
    return keys


def counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        out = {}
        for table, sql in [
            ("employees", "SELECT count(*) AS n FROM employees WHERE company_code=%s"),
            ("onboarding_items", "SELECT count(*) AS n FROM onboarding_items oi JOIN employees e ON e.employee_key=oi.employee_key WHERE e.company_code=%s"),
            ("employee_documents", "SELECT count(*) AS n FROM employee_documents WHERE company_code=%s"),
            ("compliance_documents", "SELECT count(*) AS n FROM compliance_documents WHERE company_code=%s"),
            ("file_registry", "SELECT count(*) AS n FROM file_registry WHERE company_code=%s"),
        ]:
            cur.execute(sql, (COMPANY,))
            out[table] = int((cur.fetchone() or {}).get("n") or 0)
    return out


def run_planner(*, company: str = COMPANY, extra: list[str] | None = None) -> tuple[int, list[dict], dict, str]:
    jsonl_path = Path(f"/tmp/p7c2-{uuid.uuid4().hex}.jsonl")
    summary_path = Path(f"/tmp/p7c2-{uuid.uuid4().hex}.summary.json")
    cmd = [
        sys.executable,
        str(PLANNER),
        "--company",
        company,
        "--mode",
        "dry-run",
        "--postgres-env",
        POSTGRES_ENV,
        "--jsonl-out",
        str(jsonl_path),
        "--summary-out",
        str(summary_path),
        "--prove-write-probe",
    ]
    if extra:
        cmd.extend(extra)
    env = os.environ.copy()
    env["WATHEFNI_POSTGRES_ENV"] = POSTGRES_ENV
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    events: list[dict] = []
    summary: dict = {}
    if jsonl_path.exists() and jsonl_path.read_text().strip():
        events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
    stderr = (proc.stderr or "") + ("\n" + proc.stdout if proc.returncode else "")
    return proc.returncode, events, summary, stderr


def events_for(events: list[dict], key: str) -> list[dict]:
    sid = sample_id(key)
    return [e for e in events if e.get("sample_id") == sid]


def plans(events: list[dict], *, action: str | None = None) -> list[dict]:
    out = [e for e in events if e.get("decision") == "plan"]
    if action:
        out = [e for e in out if e.get("action") == action]
    return out


def flag_off_on_host() -> tuple[bool, str]:
    """Best-effort: staging unit drop-ins / environ should keep protected flags off."""
    details = []
    ok = True
    for flag in ("WATHEFNI_EMPLOYEE_APP", "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"):
        val = os.environ.get(flag, "off").strip().lower()
        details.append(f"{flag}={val or 'unset'}")
        if val in {"on", "1", "true", "yes"}:
            ok = False
    # Staging systemd drop-ins if present
    drop_in_dir = Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d")
    if drop_in_dir.exists():
        text = "\n".join(p.read_text() for p in drop_in_dir.glob("*.conf"))
        for flag in ("WATHEFNI_EMPLOYEE_APP", "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"):
            if f"{flag}=on" in text.replace(" ", ""):
                ok = False
                details.append(f"staging_dropin:{flag}=on")
            else:
                details.append(f"staging_dropin:{flag}!=on")
    return ok, "; ".join(details)


def main() -> int:
    if not PLANNER.exists():
        raise SystemExit(f"missing planner: {PLANNER}")

    load_env(Path(POSTGRES_ENV))
    conn = connect_rw()
    keys: dict[str, str] = {}
    try:
        cleanup(conn)
        ensure_company(conn)
        keys = seed_fixtures(conn)
        before = counts(conn)

        # Case 2: refuse unscoped / ALL
        env = os.environ.copy()
        env["WATHEFNI_POSTGRES_ENV"] = POSTGRES_ENV
        r_missing = subprocess.run(
            [sys.executable, str(PLANNER), "--postgres-env", POSTGRES_ENV],
            capture_output=True, text=True, env=env,
        )
        record("case02_refuse_missing_company", r_missing.returncode != 0, r_missing.stderr[-200:] or r_missing.stdout[-200:])
        r_all = subprocess.run(
            [sys.executable, str(PLANNER), "--company", "ALL", "--postgres-env", POSTGRES_ENV],
            capture_output=True, text=True, env=env,
        )
        record("case02_refuse_ALL", r_all.returncode != 0 and "refusing" in (r_all.stderr + r_all.stdout).lower(), (r_all.stderr or r_all.stdout)[-200:])

        # Apply disabled even with confirm flags
        r_apply = subprocess.run(
            [
                sys.executable, str(PLANNER),
                "--company", COMPANY,
                "--mode", "apply",
                "--confirm-company", COMPANY,
                "--i-understand-writes",
                "--postgres-env", POSTGRES_ENV,
            ],
            capture_output=True, text=True, env=env,
        )
        apply_out = (r_apply.stderr or "") + (r_apply.stdout or "")
        record(
            "apply_hard_disabled",
            r_apply.returncode != 0 and "disabled until Phase 7C.3" in apply_out,
            apply_out[-240:],
        )

        code, events, summary, err = run_planner()
        record("planner_exit_0", code == 0, err[-300:] if code else f"events={len(events)}")
        record("case01_planned_writes_ge_1", summary.get("planned_writes", 0) >= 1, json.dumps(summary.get("planned_writes")))
        record("case01_read_only", summary.get("transaction_read_only") == "on" and summary.get("read_only") is True, str(summary.get("transaction_read_only")))
        record("case01_write_probe_blocked", bool((summary.get("write_probe") or {}).get("blocked")), json.dumps(summary.get("write_probe")))
        after = counts(conn)
        record("case01_no_db_mutation", before == after, f"before={before} after={after}")
        record("apply_enabled_false", summary.get("apply_enabled") is False, str(summary.get("apply_enabled")))
        record("no_writes_flag", summary.get("no_writes") is True, str(summary.get("no_writes")))

        # Case 3 W1
        e3 = events_for(events, keys["w1"])
        p3 = plans(e3, action="mark_onboarding_received")
        record(
            "case03_w1_mark_onboarding_received",
            len(p3) == 1 and p3[0].get("table") == "onboarding_items" and p3[0].get("op") == "UPDATE"
            and (p3[0].get("after") or {}).get("status") == "received",
            json.dumps(p3[0] if p3 else e3[:2], sort_keys=True)[:300],
        )

        # Case 4 W2 with file
        e4 = events_for(events, keys["w2_file"])
        p4 = plans(e4, action="insert_employee_document_from_file")
        record(
            "case04_w2_insert_ed_from_file",
            len(p4) == 1 and p4[0].get("op") == "INSERT" and p4[0].get("table") == "employee_documents",
            json.dumps(p4[0] if p4 else e4[:2], sort_keys=True)[:300],
        )

        # Case 5 skip no file
        e5 = events_for(events, keys["w2_nofile"])
        s5 = [e for e in e5 if e.get("skip_reason") == "skip_compliance_orphan_no_file"]
        record(
            "case05_skip_orphan_no_file",
            len(s5) >= 1 and len(plans(e5, action="insert_employee_document_from_file")) == 0,
            json.dumps(s5[0] if s5 else e5[:2], sort_keys=True)[:300],
        )

        # Case 6 newer wins (update ED)
        e6 = events_for(events, keys["w3_newer"])
        p6 = [e for e in plans(e6, action="sync_expiry") if e.get("table") == "employee_documents"]
        record(
            "case06_sync_expiry_ed_to_newer",
            len(p6) == 1 and (p6[0].get("guards") or {}).get("expiry_rule") == "newer_non_null_wins",
            json.dumps(p6[0] if p6 else e6[:3], sort_keys=True)[:300],
        )

        # Case 7 older rejected
        e7 = events_for(events, keys["w3_older"])
        s7 = [e for e in e7 if e.get("skip_reason") == "expiry_older_than_existing"]
        p7 = [e for e in plans(e7, action="sync_expiry") if e.get("table") == "compliance_documents"]
        record(
            "case07_expiry_older_rejected",
            len(s7) >= 1 and len(p7) == 1,
            json.dumps({"skip": s7[:1], "plan": p7[:1]}, sort_keys=True)[:300],
        )

        # Case 8 fill null from ED
        e8 = events_for(events, keys["w4_fill"])
        p8 = plans(e8, action="fill_compliance_expiry_from_ed")
        record(
            "case08_fill_compliance_expiry_from_ed",
            len(p8) == 1 and p8[0].get("table") == "compliance_documents"
            and (p8[0].get("after") or {}).get("expiry_date"),
            json.dumps(p8[0] if p8 else e8[:2], sort_keys=True)[:300],
        )

        # Case 9 null no source
        e9 = events_for(events, keys["w4_nosrc"])
        s9 = [e for e in e9 if e.get("skip_reason") == "null_expiry_no_source"]
        record(
            "case09_null_expiry_no_source",
            len(s9) >= 1 and len(plans(e9, action="fill_compliance_expiry_from_ed")) == 0,
            json.dumps(s9[0] if s9 else e9[:2], sort_keys=True)[:300],
        )

        # Case 10 alias no merge
        e10 = events_for(events, keys["alias"])
        m10 = [e for e in e10 if e.get("skip_reason") == "needs_operator_map"]
        merge_plans = [e for e in plans(e10) if "residency" in json.dumps(e).lower() and e.get("action") not in {"mark_onboarding_received"}]
        # W1 may still plan mark_onboarding for residency_iqama ED — that's OK; forbid merge plans
        alias_merge = [e for e in e10 if (e.get("guards") or {}).get("alias_merge") is True]
        record(
            "case10_needs_operator_map_no_merge",
            len(m10) >= 1 and len(alias_merge) == 0,
            json.dumps({"map": m10[:1], "plans": plans(e10)[:2]}, sort_keys=True)[:300],
        )

        # Case 11 idempotent consistent → no plans for that employee
        e11 = events_for(events, keys["consistent"])
        record(
            "case11_already_consistent_no_plans",
            len(plans(e11)) == 0,
            json.dumps(e11[:3], sort_keys=True)[:300],
        )

        # Case 12 re-audit alignment
        audit_json = Path(f"/tmp/p7c2-audit-{uuid.uuid4().hex}.json")
        audit = subprocess.run(
            [
                sys.executable, str(AUDIT),
                "--company", COMPANY,
                "--postgres-env", POSTGRES_ENV,
                "--json-out", str(audit_json),
            ],
            capture_output=True, text=True, env=env,
        )
        audit_ok = audit.returncode == 0 and audit_json.exists()
        totals = {}
        if audit_ok:
            totals = json.loads(audit_json.read_text()).get("mismatch_totals") or {}
        drift = summary.get("by_drift_class") or {}
        covers = all(
            drift.get(k, 0) >= 0  # present keys checked below
            for k in ()
        )
        # Require planner saw the A–D classes we seeded
        needed = [
            "employee_doc_without_received_item",
            "compliance_without_employee_doc",
            "expiry_status_conflicts",
            "null_expiry_on_received_compliance",
        ]
        covers = all(drift.get(k, 0) >= 1 for k in needed)
        # Dry-run fixtures: all EDs have files; exactly one intentional orphan file (W2 case4).
        storage_ok = (
            totals.get("employee_doc_without_file", 1) == 0
            and totals.get("orphan_employee_files", 0) == 1
            and totals.get("company_mismatch", 1) == 0
            and totals.get("orphan_employee_keys", 1) == 0
        )
        record(
            "case12_reaudit_alignment",
            audit_ok and covers and storage_ok,
            json.dumps({"drift": {k: drift.get(k) for k in needed}, "audit_storage": {
                "employee_doc_without_file": totals.get("employee_doc_without_file"),
                "orphan_employee_files": totals.get("orphan_employee_files"),
                "company_mismatch": totals.get("company_mismatch"),
                "orphan_employee_keys": totals.get("orphan_employee_keys"),
            }}, sort_keys=True),
        )

        # Case 13 flags
        flags_ok, flags_detail = flag_off_on_host()
        record("case13_protected_flags_off", flags_ok, flags_detail)

        # Save sample artifacts
        reports = OPS / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "phase7c2-p7c2stg01-plan.jsonl").write_text(
            "\n".join(json.dumps(e, sort_keys=True) for e in events[:12]) + ("\n" if events else "")
        )
        (reports / "phase7c2-p7c2stg01-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

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
