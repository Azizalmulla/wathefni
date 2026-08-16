#!/usr/bin/env python3
"""Attendance final — production synthetic canary (UX + ops + capture health).

Synthetic-only. CAPTURE_INGEST must remain off. No real employees / payroll impact.
Cleans up all ATTW4B / canary tags. Asserts 42 demo attendance rows unchanged.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

import app  # noqa: E402
import attendance_authority_wave1 as core  # noqa: E402

KUWAIT = ZoneInfo("Asia/Kuwait")
RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
EVID = Path(os.environ.get("ATTW_FINAL_EVID") or f"/tmp/attw-final-{uuid.uuid4().hex[:8]}")
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def fingerprint_attendance(cur) -> tuple[int, int, str]:
    cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
    n = int(cur.fetchone()["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI' AND metadata->>'demo_seed'='wathefni_v1'"
    )
    demo = int(cur.fetchone()["n"])
    cur.execute(
        """
        SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|'
               ORDER BY attendance_id)) AS fp
        FROM attendance_records WHERE company_code='WATHEFNI'
        """
    )
    fp = str(cur.fetchone()["fp"] or "")
    return n, demo, fp


def cleanup_tag(tag: str, capture_prefix: str | None = None) -> dict[str, int]:
    deleted: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            def allow() -> None:
                cur.execute("SELECT set_config('wathefni.allow_authority_cleanup', '1', true)")

            allow()
            like = f"%ATTW4B-{tag}%"
            w3like = f"W3-SYNTH|ATTW4B-{tag}-%"
            for table, col in (
                ("attendance_ops_disputes", "employee_key"),
                ("attendance_ops_cases", "employee_key"),
                ("attendance_ops_exceptions", "employee_key"),
                ("attendance_punches", "employee_key"),
                ("attendance_day_projections", "employee_key"),
                ("attendance_payroll_snapshots", "employee_key"),
                ("attendance_corrections", "employee_key"),
            ):
                try:
                    cur.execute("SAVEPOINT attw_cleanup")
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s AND ({col} LIKE %s OR {col} LIKE %s)",
                        ("WATHEFNI", like, w3like),
                    )
                    deleted[table] = cur.rowcount
                    cur.execute("RELEASE SAVEPOINT attw_cleanup")
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                    deleted[table] = -1
                    deleted[f"{table}_err"] = str(exc)[:120]
            # idempotency keys
            try:
                cur.execute("SAVEPOINT attw_cleanup")
                cur.execute(
                    "DELETE FROM attendance_ops_idempotency WHERE company_code=%s AND idempotency_key LIKE %s",
                    ("WATHEFNI", f"%attw4b%{tag}%"),
                )
                deleted["attendance_ops_idempotency"] = cur.rowcount
                cur.execute("RELEASE SAVEPOINT attw_cleanup")
            except Exception as exc:  # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                deleted["attendance_ops_idempotency"] = -1
                deleted["attendance_ops_idempotency_err"] = str(exc)[:120]
            if capture_prefix:
                pref = capture_prefix
                try:
                    cur.execute("SAVEPOINT attw_cleanup")
                    cur.execute(
                        """
                        DELETE FROM attendance_capture_remediation
                        WHERE company_code=%s AND (
                          coalesce(device_user_id,'') LIKE %s
                          OR coalesce(source_event_id,'') LIKE %s
                          OR coalesce(device_id,'') LIKE %s
                          OR coalesce(connector_id,'') LIKE %s
                          OR payload::text LIKE %s
                        )
                        """,
                        ("WATHEFNI", f"%{pref}%", f"%{pref}%", f"%{pref}%", f"%{pref}%", f"%{pref}%"),
                    )
                    deleted["capture_remediation"] = cur.rowcount
                    cur.execute("RELEASE SAVEPOINT attw_cleanup")
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                    deleted["capture_remediation"] = -1
                    deleted["capture_remediation_err"] = str(exc)[:120]

                # Collect connector ids tied to this synthetic tag
                try:
                    cur.execute("SAVEPOINT attw_cleanup")
                    cur.execute(
                        """
                        SELECT connector_id FROM attendance_capture_connectors
                        WHERE company_code=%s AND (
                          connector_id LIKE %s OR coalesce(metadata->>'tag','')=%s
                          OR device_id IN (
                            SELECT device_id FROM attendance_capture_devices
                            WHERE company_code=%s AND (terminal_sn LIKE %s OR coalesce(metadata->>'tag','')=%s)
                          )
                          OR site_id IN (
                            SELECT site_id FROM attendance_capture_sites
                            WHERE company_code=%s AND (name LIKE %s OR coalesce(metadata->>'tag','')=%s)
                          )
                        )
                        """,
                        ("WATHEFNI", f"%{pref}%", pref, "WATHEFNI", f"%{pref}%", pref, "WATHEFNI", f"%{pref}%", pref),
                    )
                    connector_ids = [r["connector_id"] for r in cur.fetchall()]
                    cur.execute("RELEASE SAVEPOINT attw_cleanup")
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                    connector_ids = []
                    deleted["capture_connectors_lookup_err"] = str(exc)[:120]

                if connector_ids:
                    for tbl in (
                        "attendance_capture_health_events",
                        "attendance_capture_health",
                        "attendance_capture_checkpoints",
                        "attendance_capture_idempotency",
                        "attendance_capture_audit_events",
                        "attendance_capture_replay_ledger",
                        "attendance_capture_quarantine",
                        "attendance_capture_mappings",
                    ):
                        try:
                            cur.execute("SAVEPOINT attw_cleanup")
                            cur.execute(
                                f"DELETE FROM {tbl} WHERE company_code=%s AND connector_id = ANY(%s)",
                                ("WATHEFNI", connector_ids),
                            )
                            deleted[tbl] = cur.rowcount
                            cur.execute("RELEASE SAVEPOINT attw_cleanup")
                        except Exception as exc:  # noqa: BLE001
                            cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                            deleted[tbl] = -1
                            deleted[f"{tbl}_err"] = str(exc)[:120]
                    try:
                        cur.execute("SAVEPOINT attw_cleanup")
                        cur.execute(
                            "UPDATE attendance_capture_connectors SET credential_id=NULL, device_id=NULL WHERE company_code=%s AND connector_id = ANY(%s)",
                            ("WATHEFNI", connector_ids),
                        )
                        cur.execute(
                            "DELETE FROM attendance_capture_credentials WHERE company_code=%s AND connector_id = ANY(%s)",
                            ("WATHEFNI", connector_ids),
                        )
                        deleted["attendance_capture_credentials"] = cur.rowcount
                        cur.execute(
                            "DELETE FROM attendance_capture_connectors WHERE company_code=%s AND connector_id = ANY(%s)",
                            ("WATHEFNI", connector_ids),
                        )
                        deleted["attendance_capture_connectors"] = cur.rowcount
                        cur.execute("RELEASE SAVEPOINT attw_cleanup")
                    except Exception as exc:  # noqa: BLE001
                        cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                        deleted["attendance_capture_connectors"] = -1
                        deleted["attendance_capture_connectors_err"] = str(exc)[:120]

                try:
                    cur.execute("SAVEPOINT attw_cleanup")
                    cur.execute(
                        """
                        DELETE FROM attendance_capture_devices
                        WHERE company_code=%s AND (terminal_sn LIKE %s OR coalesce(metadata->>'tag','')=%s)
                        """,
                        ("WATHEFNI", f"%{pref}%", pref),
                    )
                    deleted["attendance_capture_devices"] = cur.rowcount
                    cur.execute("RELEASE SAVEPOINT attw_cleanup")
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                    deleted["attendance_capture_devices"] = -1
                    deleted["attendance_capture_devices_err"] = str(exc)[:120]
                try:
                    cur.execute("SAVEPOINT attw_cleanup")
                    cur.execute(
                        """
                        DELETE FROM attendance_capture_sites
                        WHERE company_code=%s AND (name LIKE %s OR coalesce(metadata->>'tag','')=%s)
                        """,
                        ("WATHEFNI", f"%{pref}%", pref),
                    )
                    deleted["attendance_capture_sites"] = cur.rowcount
                    cur.execute("RELEASE SAVEPOINT attw_cleanup")
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                    deleted["attendance_capture_sites"] = -1
                    deleted["attendance_capture_sites_err"] = str(exc)[:120]
            # Never touch demo / real attendance_records
            try:
                cur.execute("SAVEPOINT attw_cleanup")
                cur.execute(
                    """
                    DELETE FROM attendance_records
                    WHERE company_code='WATHEFNI'
                      AND (employee_key LIKE %s OR employee_key LIKE %s)
                      AND coalesce(metadata->>'demo_seed','') <> 'wathefni_v1'
                    """,
                    (like, w3like),
                )
                deleted["attendance_records_non_demo"] = cur.rowcount
                cur.execute("RELEASE SAVEPOINT attw_cleanup")
            except Exception as exc:  # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT attw_cleanup")
                deleted["attendance_records_non_demo"] = -1
                deleted["attendance_records_non_demo_err"] = str(exc)[:120]
        conn.commit()
    return deleted


def main() -> int:
    check("production env", (os.environ.get("WATHEFNI_ENV") or "").lower() == "production")
    check(
        "capture ingest off",
        (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "off").lower() in {"", "0", "false", "no", "off"},
    )
    check("ops synthetic only", (os.environ.get("WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY") or "").lower() in {"1", "true", "yes", "on"})
    check(
        "authority synthetic only",
        (os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY") or "").lower() in {"1", "true", "yes", "on"},
    )
    check("import off", (os.environ.get("WATHEFNI_ATTENDANCE_IMPORT") or "off").lower() in {"", "0", "false", "no", "off"})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            check("db is wathefni", cur.fetchone()["db"] == "wathefni")
            before_n, before_demo, before_fp = fingerprint_attendance(cur)
            check("42 attendance rows before", before_n == 42, before_n)
            check("42 demo_seed before", before_demo == 42, before_demo)
            cur.execute(
                "SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)",
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            check("four reals present", int(cur.fetchone()["n"]) == 4)
            cur.execute(
                """
                SELECT md5(string_agg(employee_key || ':' || coalesce(phone,''), '|' ORDER BY employee_key)) AS fp
                FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                """,
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            four_fp_before = str(cur.fetchone()["fp"] or "")
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM payroll_timesheets WHERE company_code='WATHEFNI'
                """
            )
            ts_before = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(timesheet_id::text || ':' || status, '|' ORDER BY timesheet_id)) AS fp
                FROM payroll_timesheets WHERE company_code='WATHEFNI'
                """
            )
            row = cur.fetchone()
            ts_fp_before = str((row or {}).get("fp") or "")

    # --- Wave 4B seed + click-through prove ---
    seed_evid = EVID / "wave4b"
    seed_evid.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["ATTW4B_EVID"] = str(seed_evid)
    env["ATTW4B_USE_APP"] = "1"
    env["ATTW4B_COMPANY"] = "WATHEFNI"
    env["WATHEFNI_ENV"] = "production"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "seed-and-prove-attendance-wave4b.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    (EVID / "wave4b-stdout.txt").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    summary_path = seed_evid / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        failed_n = int(summary["failed"]) if "failed" in summary else 1
        passed_n = int(summary["passed"]) if "passed" in summary else 0
        check("wave4b prove failed=0", failed_n == 0, summary)
        check("wave4b prove passed>=35", passed_n >= 35, summary)
        tag = str(summary.get("tag") or "")
        work_date = str(summary.get("work_date") or "")
    else:
        check("wave4b summary present", False, proc.stdout[-500:])
        tag = ""
        work_date = datetime.now(KUWAIT).date().isoformat()

    # --- Capture ops connector remediation (ingest stays off) ---
    capture_prefix = "ATTWFIN" + uuid.uuid4().hex[:6].upper()
    # Mint owner session for HTTP
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code='WATHEFNI' AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """
            )
            user = cur.fetchone()
    token, _ = app.create_dashboard_session(dict(user))

    def http(method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        import urllib.request

        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:8010{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Wathefni-Company": "WATHEFNI",
                "X-Company-Code": "WATHEFNI",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except Exception as exc:  # noqa: BLE001
            if hasattr(exc, "code"):
                raw = exc.read().decode() if hasattr(exc, "read") else ""
                try:
                    return int(exc.code), json.loads(raw) if raw else {"raw": raw}
                except Exception:
                    return int(exc.code), {"raw": raw[:400]}
            raise

    st, ov = http("GET", "/dashboard/posthire/attendance/capture-ops")
    check("capture ops overview ok", st == 200 and bool((ov or {}).get("ok")), {"status": st, "err": (ov or {}).get("error")})
    check("capture ingest disabled in overview", (ov or {}).get("ingest_enabled") in {False, None, 0, "off"} or not (ov or {}).get("ingest_enabled"))

    st, seed = http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", {"tag": capture_prefix})
    check("capture synthetic seed ok", st == 200 and bool((seed or {}).get("ok")), seed)

    st, ov2 = http("GET", "/dashboard/posthire/attendance/capture-ops")
    connectors = (ov2 or {}).get("connectors") or []
    check("capture connectors present", len(connectors) >= 1, len(connectors))
    if connectors:
        cid = connectors[0]["connector_id"]
        st_off, _ = http(
            "POST",
            f"/dashboard/posthire/attendance/capture-ops/connectors/{cid}/health",
            {"status": "offline", "lag_seconds": 0, "error_count": 1, "last_error": "final_canary_offline"},
        )
        check("connector simulate offline", st_off == 200, st_off)
        st_lag, _ = http(
            "POST",
            f"/dashboard/posthire/attendance/capture-ops/connectors/{cid}/health",
            {"status": "ok", "lag_seconds": 2400, "error_count": 0, "last_sync_at": datetime.now(KUWAIT).isoformat()},
        )
        check("connector simulate lag", st_lag == 200, st_lag)
        st_ok, _ = http(
            "POST",
            f"/dashboard/posthire/attendance/capture-ops/connectors/{cid}/health",
            {"status": "ok", "lag_seconds": 5, "error_count": 0, "last_sync_at": datetime.now(KUWAIT).isoformat()},
        )
        check("connector mark recovered", st_ok == 200, st_ok)

    remediation = (ov2 or {}).get("remediation_open") or []
    mapping = [r for r in remediation if r.get("kind") in {"unknown_employee", "unknown_device"}]
    check("unknown mapping remediation present", len(mapping) >= 1, len(mapping))
    if mapping:
        item = mapping[0]
        # Reject mapping (no real employee bind) — proves remediation UX path without ingest replay
        st_rj, rj = http(
            "POST",
            f"/dashboard/posthire/attendance/capture-ops/remediation/{item['item_id']}/reject",
            {"expected_row_version": int(item.get("row_version") or 1), "reason": "final_canary_reject"},
        )
        check("mapping remediation reject", st_rj == 200 and bool((rj or {}).get("ok") or rj.get("item") or st_rj == 200), {"status": st_rj, "body": rj})

    # --- HTTP attendance reconcile for ATTW4B rows ---
    if tag:
        st, att = http("GET", f"/dashboard/posthire/attendance?start_date={work_date}&end_date={work_date}&limit=500")
        rows = [r for r in ((att or {}).get("attendance") or []) if f"ATTW4B-{tag}-" in str(r.get("employee_key") or "")]
        check("http daily board rows >= 8", len(rows) >= 8, len(rows))
        seed_index = json.loads((seed_evid / "seed-index.json").read_text()) if (seed_evid / "seed-index.json").exists() else {}
        counts = {"approved": 0, "incomplete": 0, "absent": 0, "disputed": 0, "locked": 0, "needs_review": 0, "captured": 0}
        for row in rows:
            meta = row.get("metadata") or {}
            approval = str(meta.get("approval_status") or "").lower()
            status = str(row.get("status") or "").lower()
            if meta.get("payroll_locked"):
                stt = "locked"
            elif approval == "disputed" or status == "disputed":
                stt = "disputed"
            elif approval == "approved":
                stt = "approved"
            elif status == "absent":
                stt = "absent"
            elif str(meta.get("exception_state") or "none") not in {"", "none"}:
                stt = "incomplete"
            elif int(row.get("late_minutes") or 0) > 0 or int(row.get("early_leave_minutes") or meta.get("early_leave_minutes") or 0) > 0:
                stt = "needs_review"
            else:
                stt = "captured"
            counts[stt] = counts.get(stt, 0) + 1
        seed_counts = seed_index.get("counts") or {}
        check("api/ui life-state counts match seed", counts == seed_counts, {"http": counts, "seed": seed_counts})
        (EVID / "http-reconcile.json").write_text(json.dumps({"rows": len(rows), "counts": counts, "seed_counts": seed_counts}, indent=2), encoding="utf-8")

        # Ops queue has cases key
        st, opsq = http("GET", "/dashboard/attendance/ops/exceptions")
        check("ops list has cases key", st == 200 and isinstance(opsq, dict) and "cases" in opsq, opsq if st != 200 else list((opsq or {}).keys()))

    # Real employee must not be mutated by synthetic allowlist
    real_key = next(iter(core.FOUR_REAL_ATTENDANCE_KEYS))
    check(
        "real employee not synthetic-allowed",
        core.attendance_authority_allowed_for("WATHEFNI", {"employee_key": real_key, "phone": real_key.split("-")[-1]}) is False,
    )

    # --- Cleanup ---
    deleted = cleanup_tag(tag or "NONE", capture_prefix=capture_prefix)
    (EVID / "cleanup.json").write_text(json.dumps(deleted, indent=2, default=str), encoding="utf-8")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after_n, after_demo, after_fp = fingerprint_attendance(cur)
            check("42 attendance rows after cleanup", after_n == 42, after_n)
            check("42 demo_seed after cleanup", after_demo == 42, after_demo)
            check("attendance fingerprint unchanged", after_fp == before_fp, {"before": before_fp, "after": after_fp})
            cur.execute(
                """
                SELECT md5(string_agg(employee_key || ':' || coalesce(phone,''), '|' ORDER BY employee_key)) AS fp
                FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                """,
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            four_fp_after = str(cur.fetchone()["fp"] or "")
            check("four reals fingerprint unchanged", four_fp_after == four_fp_before)
            cur.execute("SELECT COUNT(*) AS n FROM payroll_timesheets WHERE company_code='WATHEFNI'")
            ts_after = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(timesheet_id::text || ':' || status, '|' ORDER BY timesheet_id)) AS fp
                FROM payroll_timesheets WHERE company_code='WATHEFNI'
                """
            )
            ts_fp_after = str((cur.fetchone() or {}).get("fp") or "")
            check("payroll timesheets unchanged", ts_after == ts_before and ts_fp_after == ts_fp_before, {"before": ts_before, "after": ts_after})
            if tag:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM attendance_day_projections WHERE company_code='WATHEFNI' AND employee_key LIKE %s",
                    (f"%ATTW4B-{tag}%",),
                )
                check("no leftover ATTW4B projections", int(cur.fetchone()["n"]) == 0)
                cur.execute(
                    "SELECT COUNT(*) AS n FROM attendance_ops_exceptions WHERE company_code='WATHEFNI' AND employee_key LIKE %s",
                    (f"%ATTW4B-{tag}%",),
                )
                check("no leftover ATTW4B exceptions", int(cur.fetchone()["n"]) == 0)

    # Freezes
    for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
        p = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT), capture_output=True, text=True)
        ok = p.returncode == 0 and "failed" in p.stdout and not any(
            line.strip().endswith("failed") and not line.strip().startswith("0 ") and "0 failed" not in line
            for line in p.stdout.splitlines()
            if "failed" in line and "passed" in line
        )
        # Prefer explicit "N passed, 0 failed"
        ok = p.returncode == 0 and ("0 failed" in p.stdout or "passed, 0 failed" in p.stdout)
        check(f"freeze {script}", ok, p.stdout[-400:])
        (EVID / f"{script}.out").write_text(p.stdout + p.stderr, encoding="utf-8")

    out = {
        "wave": "attendance-final-prod",
        "passed": PASS,
        "failed": FAIL,
        "total": PASS + FAIL,
        "tag": tag,
        "capture_prefix": capture_prefix,
        "work_date": work_date,
        "evid": str(EVID),
    }
    (EVID / "qualification.json").write_text(json.dumps({"results": RESULTS, "summary": out}, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
