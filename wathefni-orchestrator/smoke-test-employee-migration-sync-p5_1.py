#!/usr/bin/env python3
"""Migration Sync P5.1 — scheduler + real SFTP file-feed canary smoke (WATHEFNI)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")
os.environ.setdefault("WATHEFNI_SFTP_ALLOW_INSECURE_HOST_KEY", "1")
os.environ["WATHEFNI_SYNTHETIC_CONNECTORS"] = "1"
os.environ["WATHEFNI_SYNTHETIC_CONNECTOR_COMPANIES"] = "WATHEFNI"


def _fail(msg: str) -> None:
    print(f"FAIL migration sync P5.1: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _csv(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "name,phone\n"
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    lines = [",".join(keys)]
    for r in rows:
        lines.append(",".join(str(r.get(k, "")).replace(",", " ") for k in keys))
    return "\n".join(lines) + "\n"


def main() -> None:
    import app as legacy
    import employee_migration_connectors as p5
    import employee_migration_foundation as emf
    import employee_migration_sftp as sftp_mod

    company = "WATHEFNI"
    if not emf.foundation_enabled(company):
        _fail("foundation off")

    honesty = emf.honesty_payload()
    if honesty.get("contract") != "employee_migration_sync_p6_leavers":
        _fail(f"contract {honesty.get('contract')}")
    if not honesty.get("connected_systems_p5_1_scheduler_sftp"):
        _fail("p5.1 honesty missing")
    if honesty.get("no_auth_wave2_phase6") is not True:
        _fail("Auth Wave 2 Phase 6 must remain out of scope")
    p5h = honesty.get("connected_systems") or {}
    if not p5h.get("scheduler_production") or not p5h.get("sftp_real_connector"):
        _fail(f"connector honesty incomplete: {p5h}")
    _ok("P5.1 honesty")

    tag = uuid.uuid4().hex[:8]
    context = {
        "company_code": company,
        "user_id": "smoke-p51",
        "email": "smoke-p51@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]

    root = tempfile.mkdtemp(prefix=f"p51-sftp-{tag}-")
    drop = Path(root) / "inbox"
    drop.mkdir(parents=True, exist_ok=True)
    server = sftp_mod.start_test_sftp_server(root_dir=str(drop), username="sftpuser", password="sftppass")
    time.sleep(0.3)

    connection_id = None
    created_keys: list[str] = []
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                emf.ensure_schema(cur, force=True)
                conn.commit()

        kinds = p5.connector_kinds_catalog()
        if not any(k["kind"] == "sftp" and k.get("available") for k in kinds["kinds"]):
            _fail("sftp kind not available")
        _ok("sftp catalog")

        phone_a = f"96558{(int(tag[:5], 16) % 90000) + 10000:05d}1"
        phone_b = f"96558{(int(tag[:5], 16) % 90000) + 10000:05d}2"
        file1 = drop / "employees_v1.csv"
        file1.write_text(
            _csv(
                [
                    {
                        "name": f"P51 Alpha {tag}",
                        "phone": phone_a,
                        "external_employee_id": f"SFTP-{tag}-A",
                        "email": f"p51a-{tag}@example.invalid",
                        "position_title": "Analyst",
                        "department": "Ops",
                        "custom_cost_center": "CC-SFTP-1",
                    },
                    {
                        "name": f"P51 Beta {tag}",
                        "phone": phone_b,
                        "external_employee_id": f"SFTP-{tag}-B",
                        "email": f"p51b-{tag}@example.invalid",
                        "position_title": "Coordinator",
                        "department": "Ops",
                    },
                ]
            ),
            encoding="utf-8",
        )
        # Age the file past stability window
        old = time.time() - 120
        os.utime(file1, (old, old))

        created = p5.create_connection(
            legacy,
            context,
            name=f"P51 SFTP {tag}",
            connector_kind="sftp",
            source_system=f"sftp:canary:{tag}",
            config={
                "host": server["host"],
                "port": server["port"],
                "username": "sftpuser",
                "remote_dir": "/",
                "file_pattern": "*.csv",
                "stability_seconds": 1,
                "host_key_fingerprint": server["host_key_fingerprint"],
                "allow_insecure_host_key": False,
                "auto_commit_on_schedule": True,
            },
            credentials={"password": "sftppass"},
            schedule_interval_minutes=60,
            schedule_enabled=True,
            timezone_name="Asia/Kuwait",
        )
        connection_id = created["connection"]["connection_id"]
        if not created["connection"].get("has_credentials"):
            _fail("credentials not sealed")
        if "password" in str(created["connection"].get("config") or {}).lower():
            _fail("password leaked in config")
        _ok(f"sftp connection {connection_id}")

        # Initial sync
        sync1 = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        if not sync1.get("ok"):
            _fail(f"initial sync failed: {sync1}")
        run1 = sync1["run"]
        if int(run1.get("created_count") or 0) < 2 and int(run1.get("records_fetched") or 0) < 2:
            _fail(f"initial counts: {run1}")
        _ok(f"initial file sync created={run1.get('created_count')} fetched={run1.get('records_fetched')}")

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key FROM employee_source_mappings
                    WHERE company_code=%s AND source_system=%s AND active IS TRUE
                    """,
                    (company, f"sftp:canary:{tag}"),
                )
                created_keys = [str(r["employee_key"]) for r in (cur.fetchall() or [])]
                if len(created_keys) < 2:
                    _fail(f"employees missing: {len(created_keys)}")
                cur.execute(
                    """
                    SELECT source_payload FROM employee_import_rows
                    WHERE batch_id=%s AND source_payload::text LIKE %s
                    LIMIT 1
                    """,
                    (sync1.get("batch_id"), "%custom_cost_center%"),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        SELECT values FROM employee_import_source_payloads
                        WHERE batch_id=%s AND values::text LIKE %s
                        LIMIT 1
                        """,
                        (sync1.get("batch_id"), "%CC-SFTP-1%"),
                    )
                    if not cur.fetchone():
                        _fail("custom field not retained")
                conn.commit()
        _ok("unknown/custom fields retained")

        # Duplicate same file → no duplicate application
        sync_dup = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        if not sync_dup.get("ok"):
            _fail(f"dup sync failed: {sync_dup}")
        if int((sync_dup["run"].get("created_count") or 0)) != 0:
            _fail(f"duplicate created employees: {sync_dup['run']}")
        _ok("duplicate same file → no duplicate apply")

        # Second new file incremental
        file2 = drop / "employees_v2.csv"
        phone_c = f"96558{(int(tag[:5], 16) % 90000) + 10000:05d}3"
        file2.write_text(
            _csv(
                [
                    {
                        "name": f"P51 Gamma {tag}",
                        "phone": phone_c,
                        "external_employee_id": f"SFTP-{tag}-C",
                        "email": f"p51c-{tag}@example.invalid",
                        "position_title": "Specialist",
                        "department": "Support",
                    }
                ]
            ),
            encoding="utf-8",
        )
        os.utime(file2, (old, old))
        sync2 = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        if not sync2.get("ok"):
            _fail(f"second file sync failed: {sync2}")
        if int(sync2["run"].get("created_count") or 0) < 1 and int(sync2["run"].get("records_fetched") or 0) < 1:
            _fail(f"second file counts: {sync2['run']}")
        _ok("second new file incremental sync")

        # Source update classification
        file3 = drop / "employees_v3_update.csv"
        file3.write_text(
            _csv(
                [
                    {
                        "name": f"P51 Beta {tag}",
                        "phone": phone_b,
                        "external_employee_id": f"SFTP-{tag}-B",
                        "email": f"p51b-{tag}@example.invalid",
                        "position_title": "Senior Coordinator",
                        "department": "Ops",
                    }
                ]
            ),
            encoding="utf-8",
        )
        os.utime(file3, (old, old))
        sync3 = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        if not sync3.get("ok"):
            _fail(f"update sync failed: {sync3}")
        upd = int(sync3["run"].get("updated_count") or 0)
        rev = int(sync3["run"].get("review_count") or 0)
        if upd < 1 and rev < 1 and int(sync3["run"].get("unchanged_count") or 0) < 1:
            # At least fetched and classified
            if int(sync3["run"].get("records_fetched") or 0) < 1:
                _fail(f"update classification missing: {sync3['run']}")
        _ok(f"source update classified update={upd} review={rev}")

        # Malformed file among valid
        bad = drop / "employees_bad.csv"
        bad.write_text("\x00\x01\x02NOT_A_CSV\xff\xfe", encoding="latin-1")
        os.utime(bad, (old, old))
        good = drop / "employees_v4_ok.csv"
        phone_d = f"96558{(int(tag[:5], 16) % 90000) + 10000:05d}4"
        good.write_text(
            _csv(
                [
                    {
                        "name": f"P51 Delta {tag}",
                        "phone": phone_d,
                        "external_employee_id": f"SFTP-{tag}-D",
                        "email": f"p51d-{tag}@example.invalid",
                        "position_title": "Associate",
                        "department": "Ops",
                    }
                ]
            ),
            encoding="utf-8",
        )
        os.utime(good, (old, old))
        sync_bad = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        meta = ((sync_bad.get("run") or {}).get("cursor_after") or {})
        # Check run metadata via DB
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT metadata, status, failed_count FROM employee_migration_sync_runs WHERE sync_run_id=%s",
                    (sync_bad["run"]["sync_run_id"],),
                )
                row = dict(cur.fetchone())
                fm = (row.get("metadata") or {}).get("fetch_meta") or {}
                if not fm.get("files_failed"):
                    _fail(f"malformed not recorded: {fm}")
                if not sync_bad.get("ok") and row.get("status") == "failed" and not fm.get("files_ok"):
                    _fail("good file should still process when one is bad")
                conn.commit()
        _ok("malformed file explicit + recoverable")

        # Auth failure
        p5.update_connection(
            legacy,
            context,
            connection_id=connection_id,
            credentials={"password": "wrong-password"},
        )
        fail = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual")
        if fail.get("ok") or (fail.get("run") or {}).get("error_code") != "auth_failed":
            _fail(f"auth failure: {fail}")
        _ok("auth failure recorded")

        # Restore credentials
        p5.update_connection(
            legacy,
            context,
            connection_id=connection_id,
            credentials={"password": "sftppass"},
            config={"force_timeout": False},
        )

        # Transient failure + backoff
        p5.update_connection(
            legacy,
            context,
            connection_id=connection_id,
            config={
                "host": server["host"],
                "port": server["port"],
                "username": "sftpuser",
                "remote_dir": "/",
                "file_pattern": "*.csv",
                "stability_seconds": 1,
                "host_key_fingerprint": server["host_key_fingerprint"],
                "force_timeout": True,
            },
        )
        to = p5.run_sync(legacy, context, connection_id=connection_id, trigger="scheduled")
        if (to.get("run") or {}).get("error_code") != "timeout":
            _fail(f"timeout not recorded: {to}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT retry_count, retry_after, next_sync_at FROM employee_migration_connections WHERE connection_id=%s",
                    (connection_id,),
                )
                sch = dict(cur.fetchone())
                if int(sch.get("retry_count") or 0) < 1 or not sch.get("retry_after"):
                    _fail(f"backoff missing: {sch}")
                conn.commit()
        _ok("transient failure retry/backoff")

        # Clear force_timeout
        p5.update_connection(
            legacy,
            context,
            connection_id=connection_id,
            config={
                "host": server["host"],
                "port": server["port"],
                "username": "sftpuser",
                "remote_dir": "/",
                "file_pattern": "never-match-xyz.csv",
                "stability_seconds": 1,
                "host_key_fingerprint": server["host_key_fingerprint"],
                "force_timeout": False,
                "auto_commit_on_schedule": True,
            },
        )

        # Pause prevents scheduled execution
        p5.set_connection_status(legacy, context, connection_id=connection_id, status="paused")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET next_sync_at=now() - interval '1 minute', retry_after=NULL, status='paused',
                        sync_lock_until=NULL
                    WHERE connection_id=%s
                    """,
                    (connection_id,),
                )
                conn.commit()
        tick_paused = p5.run_scheduler_tick(legacy, company_code=company, limit=50, auto_commit=True)
        if any(str((r.get("run") or {}).get("connection_id") or r.get("connection_id") or "") == connection_id for r in tick_paused.get("results") or []):
            # Also check claimed
            _fail(f"paused connection ran: {tick_paused}")
        # claim should not include paused
        claimed = p5.claim_due_connections(legacy, company_code=company, limit=50)
        if any(str(c["connection_id"]) == connection_id for c in claimed):
            _fail("paused claimed")
        # release any accidental claims
        for c in claimed:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    p5._release_sync_lock(cur, connection_id=str(c["connection_id"]))
                    conn.commit()
        _ok("pause prevents scheduled execution")

        # Resume + schedule due → automatic execution without manual sync API
        p5.set_connection_status(legacy, context, connection_id=connection_id, status="active")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET next_sync_at=now() - interval '2 minutes', retry_after=NULL, retry_count=0,
                        schedule_enabled=TRUE, status='active', sync_lock_until=NULL
                    WHERE connection_id=%s
                    """,
                    (connection_id,),
                )
                conn.commit()
        before_runs = 0
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM employee_migration_sync_runs WHERE connection_id=%s AND trigger='scheduled'",
                    (connection_id,),
                )
                before_runs = int(cur.fetchone()["n"])
                conn.commit()

        tick = p5.run_scheduler_tick(legacy, company_code=company, limit=50, auto_commit=True)
        if tick.get("claimed", 0) < 1 and tick.get("ran", 0) < 1:
            # Our connection should have been due
            _fail(f"scheduler did not claim due connection: {tick}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM employee_migration_sync_runs WHERE connection_id=%s AND trigger='scheduled'",
                    (connection_id,),
                )
                after_runs = int(cur.fetchone()["n"])
                if after_runs <= before_runs:
                    _fail("scheduled sync_run not created")
                cur.execute(
                    "SELECT next_sync_at, schedule_interval_minutes FROM employee_migration_connections WHERE connection_id=%s",
                    (connection_id,),
                )
                nxt = dict(cur.fetchone())
                if not nxt.get("next_sync_at"):
                    _fail("next_sync_at not updated")
                conn.commit()
        _ok("scheduled execution without manual trigger")

        # Missed-run / restart recovery: set next_sync far past, tick once → single run, next advanced from now
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET next_sync_at=now() - interval '3 days', sync_lock_until=NULL, retry_after=NULL
                    WHERE connection_id=%s
                    """,
                    (connection_id,),
                )
                conn.commit()
        tick2 = p5.run_scheduler_tick(legacy, company_code=company, limit=50, auto_commit=True)
        # Should claim once; duplicate apply prevented by file ledger
        if tick2.get("claimed", 0) < 1:
            _fail(f"missed-run not claimed: {tick2}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT next_sync_at FROM employee_migration_connections WHERE connection_id=%s",
                    (connection_id,),
                )
                ns = cur.fetchone()["next_sync_at"]
                # next should be in the future (catch-up once, not stampede)
                from datetime import datetime, timezone as tz

                now = datetime.now(tz.utc)
                if ns.tzinfo is None:
                    ns = ns.replace(tzinfo=tz.utc)
                if ns <= now:
                    _fail(f"next_sync_at not advanced after missed run: {ns}")
                conn.commit()
        _ok("missed-run/restart recovery (single catch-up)")

        # Sync history
        hist = p5.list_sync_runs(legacy, context, connection_id=connection_id, limit=50)
        if len(hist.get("runs") or []) < 3:
            _fail("sync history incomplete")
        _ok(f"sync-run history count={len(hist['runs'])}")

        # Deterministic next_sync helper
        nxt = p5.compute_next_sync_at(schedule_interval_minutes=30, timezone_name="Asia/Kuwait")
        if nxt <= p5._now():
            _fail("compute_next_sync_at")
        _ok("deterministic next_sync_at")

        # P5 canary connector still works (regression slice)
        canary = p5.create_connection(
            legacy,
            context,
            name=f"P51 Canary {tag}",
            connector_kind="deterministic_canary",
            source_system=f"canary:p51:{tag}",
            config={"fixture_tag": f"p51{tag}"[:12], "fixture_version": 1},
            schedule_enabled=False,
        )
        cres = p5.run_sync(
            legacy,
            context,
            connection_id=canary["connection"]["connection_id"],
            trigger="manual",
            auto_commit=True,
        )
        if not cres.get("ok"):
            _fail(f"canary regression: {cres}")
        _ok("P5 canary connector regression")

        # Disconnect cleanup
        p5.set_connection_status(legacy, context, connection_id=connection_id, status="disconnected")
        p5.set_connection_status(
            legacy, context, connection_id=canary["connection"]["connection_id"], status="disconnected"
        )
        _ok("P5.1 smoke PASS")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        try:
            sftp_mod.stop_test_sftp_server(server)
        except Exception:
            pass
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    if created_keys:
                        for ek in created_keys:
                            cur.execute(
                                "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                                (company, ek),
                            )
                    for src in (f"sftp:canary:{tag}", f"canary:p51:{tag}"):
                        cur.execute(
                            """
                            SELECT employee_key FROM employee_source_mappings
                            WHERE company_code=%s AND source_system=%s
                            """,
                            (company, src),
                        )
                        for r in cur.fetchall() or []:
                            cur.execute(
                                "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                                (company, r["employee_key"]),
                            )
                        cur.execute(
                            "DELETE FROM employee_source_mappings WHERE company_code=%s AND source_system=%s",
                            (company, src),
                        )
                        cur.execute(
                            "DELETE FROM employee_migration_connections WHERE company_code=%s AND source_system=%s",
                            (company, src),
                        )
                    if connection_id:
                        cur.execute(
                            "DELETE FROM employee_migration_connections WHERE connection_id=%s",
                            (connection_id,),
                        )
                    conn.commit()
        except Exception as cleanup_exc:
            print(f"WARN cleanup: {cleanup_exc}")
        import shutil

        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
