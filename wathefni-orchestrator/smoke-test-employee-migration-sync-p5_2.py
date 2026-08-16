#!/usr/bin/env python3
"""Migration Sync P5.2 — connector secret hardening canary smoke (WATHEFNI)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")
os.environ.setdefault("WATHEFNI_SFTP_ALLOW_INSECURE_HOST_KEY", "1")


def _fail(msg: str) -> None:
    print(f"FAIL migration sync P5.2: {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"OK {msg}")


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
    if not honesty.get("connected_systems_p5_2_secret_hardening"):
        _fail("p5.2 honesty missing")
    p5h = honesty.get("connected_systems") or {}
    if not p5h.get("secrets_fail_closed") or not p5h.get("plainhex_fallback_removed"):
        _fail(f"secret hardening honesty incomplete: {p5h}")
    if honesty.get("no_auth_wave2_phase6") is not True:
        _fail("Auth Wave 2 Phase 6 must remain out of scope")
    _ok("P5.2 honesty")

    if not legacy.sensitive_encryption_available():
        _fail("WATHEFNI_MAILBOX_SECRET_KEY must be set for P5.2 qualification")
    _ok("encryption key available")

    tag = uuid.uuid4().hex[:8]
    context = {
        "company_code": company,
        "user_id": "smoke-p52",
        "email": "smoke-p52@wathefni.ai",
        "permissions": ["employees.manage"],
    }
    original_require = legacy.require_employee_roster_admin

    def _require(ctx: dict[str, Any], permission: str = "employees.manage") -> str:
        del permission
        return str(ctx.get("company_code") or company).upper()

    legacy.require_employee_roster_admin = _require  # type: ignore[assignment]

    # --- Remediate any leftover insecure canary secrets first ---
    rem = p5.audit_and_remediate_insecure_secrets(legacy, company_code=company)
    _ok(
        f"remediation scanned={rem.get('scanned_insecure')} resealed={rem.get('resealed')} "
        f"reentry={rem.get('require_reentry')}"
    )

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            emf.ensure_schema(cur, force=True)
            cur.execute(
                """
                SELECT count(*) AS n FROM employee_migration_connection_secrets s
                JOIN employee_migration_connections c ON c.connection_id=s.connection_id
                WHERE c.company_code=%s
                  AND (s.alg IN ('plainhex','plaintext') OR s.ciphertext LIKE 'plainhex:%%')
                """,
                (company,),
            )
            left = int(cur.fetchone()["n"])
            if left:
                _fail(f"insecure secrets remain after remediation: {left}")
            conn.commit()
    _ok("no insecure connector secrets remain")

    # --- Missing key → create with credentials fails closed ---
    original_avail = legacy.sensitive_encryption_available

    def _no_enc() -> bool:
        return False

    legacy.sensitive_encryption_available = _no_enc  # type: ignore[assignment]
    try:
        p5.create_connection(
            legacy,
            context,
            name=f"P52 noenc {tag}",
            connector_kind="sftp",
            source_system=f"sftp:p52-noenc:{tag}",
            config={"host": "127.0.0.1", "username": "x"},
            credentials={"password": "should-not-persist"},
        )
        _fail("create should fail closed without encryption key")
    except Exception as exc:
        detail = getattr(exc, "detail", {}) or {}
        if not (isinstance(detail, dict) and detail.get("error") == "connector_encryption_unavailable"):
            if "connector_encryption_unavailable" not in str(exc):
                _fail(f"wrong missing-key error: {exc}")
    finally:
        legacy.sensitive_encryption_available = original_avail  # type: ignore[assignment]

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n FROM employee_migration_connections
                WHERE company_code=%s AND source_system=%s
                """,
                (company, f"sftp:p52-noenc:{tag}"),
            )
            if int(cur.fetchone()["n"]) != 0:
                _fail("connection persisted despite encryption failure")
            cur.execute(
                """
                SELECT count(*) AS n FROM employee_migration_connection_secrets s
                JOIN employee_migration_connections c ON c.connection_id=s.connection_id
                WHERE c.company_code=%s AND c.source_system=%s
                """,
                (company, f"sftp:p52-noenc:{tag}"),
            )
            if int(cur.fetchone()["n"]) != 0:
                _fail("secret persisted despite encryption failure")
            conn.commit()
    _ok("missing key → create fails closed, nothing persisted")

    # --- Invalid key → fails closed ---
    original_encrypt = legacy.encrypt_sensitive_text

    def _bad_encrypt(plaintext: str) -> dict[str, str]:
        del plaintext
        raise RuntimeError("invalid_fernet_key")

    legacy.encrypt_sensitive_text = _bad_encrypt  # type: ignore[assignment]
    try:
        p5.create_connection(
            legacy,
            context,
            name=f"P52 badkey {tag}",
            connector_kind="sftp",
            source_system=f"sftp:p52-badkey:{tag}",
            config={"host": "127.0.0.1"},
            credentials={"password": "nope"},
        )
        _fail("create should fail on invalid key")
    except Exception as exc:
        detail = getattr(exc, "detail", {}) or {}
        err = detail.get("error") if isinstance(detail, dict) else None
        if err not in {"connector_encryption_failed", "connector_encryption_unavailable"}:
            if "connector_encryption" not in str(exc):
                _fail(f"wrong invalid-key error: {exc}")
    finally:
        legacy.encrypt_sensitive_text = original_encrypt  # type: ignore[assignment]
    _ok("invalid key → fails closed")

    # Reject plainhex if somehow returned by encrypt
    def _plainhex_encrypt(plaintext: str) -> dict[str, str]:
        return {
            "ciphertext": "plainhex:" + plaintext.encode().hex(),
            "key_version": "dev_plainhex",
            "alg": "plainhex",
        }

    legacy.encrypt_sensitive_text = _plainhex_encrypt  # type: ignore[assignment]
    try:
        p5.create_connection(
            legacy,
            context,
            name=f"P52 reject-plain {tag}",
            connector_kind="sftp",
            source_system=f"sftp:p52-reject:{tag}",
            config={"host": "127.0.0.1"},
            credentials={"password": "nope"},
        )
        _fail("plainhex encrypt result must be rejected")
    except Exception as exc:
        detail = getattr(exc, "detail", {}) or {}
        if not (isinstance(detail, dict) and detail.get("error") == "connector_encryption_rejected"):
            if "connector_encryption_rejected" not in str(exc):
                _fail(f"plainhex not rejected: {exc}")
    finally:
        legacy.encrypt_sensitive_text = original_encrypt  # type: ignore[assignment]
    _ok("plainhex encrypt result rejected")

    # --- Valid key → Fernet seal + SFTP works ---
    root = tempfile.mkdtemp(prefix=f"p52-sftp-{tag}-")
    drop = Path(root) / "inbox"
    drop.mkdir(parents=True, exist_ok=True)
    server = sftp_mod.start_test_sftp_server(root_dir=str(drop), username="sftpuser", password="sftppass")
    time.sleep(0.3)
    phone = f"96559{(int(tag[:5], 16) % 90000) + 10000:05d}1"
    f1 = drop / "roster.csv"
    f1.write_text(
        f"name,phone,external_employee_id,email\nP52 Alpha {tag},{phone},SFTP-P52-{tag}-A,p52-{tag}@example.invalid\n",
        encoding="utf-8",
    )
    os.utime(f1, (time.time() - 120, time.time() - 120))

    connection_id = None
    created_keys: list[str] = []
    try:
        created = p5.create_connection(
            legacy,
            context,
            name=f"P52 SFTP {tag}",
            connector_kind="sftp",
            source_system=f"sftp:p52:{tag}",
            config={
                "host": server["host"],
                "port": server["port"],
                "username": "sftpuser",
                "remote_dir": "/",
                "file_pattern": "*.csv",
                "stability_seconds": 1,
                "host_key_fingerprint": server["host_key_fingerprint"],
            },
            credentials={"password": "sftppass"},
            schedule_enabled=False,
        )
        connection_id = created["connection"]["connection_id"]
        pub = str(created)
        if "sftppass" in pub or "password" in str(created.get("connection", {}).get("config") or {}).lower():
            # config should not contain password; public dump must not include secret value
            if "sftppass" in pub:
                _fail("password leaked in create response")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT alg, key_version, left(ciphertext, 12) AS prefix
                    FROM employee_migration_connection_secrets WHERE connection_id=%s
                    """,
                    (connection_id,),
                )
                srow = dict(cur.fetchone())
                if srow.get("alg") != "fernet" or str(srow.get("prefix") or "").startswith("plainhex"):
                    _fail(f"secret not fernet: {srow}")
                if "sftppass" in str(srow):
                    _fail("password visible in secret row metadata")
                conn.commit()
        _ok("valid key → secret stored as fernet")

        sync = p5.run_sync(legacy, context, connection_id=connection_id, trigger="manual", auto_commit=True)
        if not sync.get("ok"):
            _fail(f"encrypted connector sync failed: {sync}")
        _ok("fernet-sealed connector sync works")

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key FROM employee_source_mappings
                    WHERE company_code=%s AND source_system=%s AND active IS TRUE
                    """,
                    (company, f"sftp:p52:{tag}"),
                )
                created_keys = [str(r["employee_key"]) for r in (cur.fetchall() or [])]
                conn.commit()

        # --- Inject insecure secret; scheduler/sync must not apply ---
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                # Simulate legacy plainhex row without printing secret
                insecure_ct = "plainhex:" + b'{"password":"x"}'.hex()
                cur.execute(
                    """
                    UPDATE employee_migration_connection_secrets
                    SET ciphertext=%s, alg='plainhex', key_version='dev_plainhex', updated_at=now()
                    WHERE connection_id=%s
                    """,
                    (insecure_ct, connection_id),
                )
                cur.execute(
                    """
                    UPDATE employee_migration_connections
                    SET status='active', schedule_enabled=TRUE,
                        next_sync_at=now() - interval '1 minute',
                        sync_lock_until=NULL, last_error_summary=NULL
                    WHERE connection_id=%s
                    """,
                    (connection_id,),
                )
                conn.commit()

        before_batches = 0
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM employee_import_batches WHERE company_code=%s AND source_system=%s",
                    (company, f"sftp:p52:{tag}"),
                )
                before_batches = int(cur.fetchone()["n"])
                conn.commit()

        bad = p5.run_sync(legacy, context, connection_id=connection_id, trigger="scheduled", auto_commit=True)
        if bad.get("ok"):
            _fail("sync must fail on insecure secret")
        if (bad.get("run") or {}).get("error_code") != "insecure_secret_storage_rejected":
            _fail(f"wrong insecure sync error: {bad}")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM employee_import_batches WHERE company_code=%s AND source_system=%s",
                    (company, f"sftp:p52:{tag}"),
                )
                after_batches = int(cur.fetchone()["n"])
                if after_batches != before_batches:
                    _fail("insecure secret sync applied data")
                cur.execute(
                    "SELECT status, last_error_summary, schedule_enabled, has_sec FROM employee_migration_connections c LEFT JOIN (SELECT connection_id, true AS has_sec FROM employee_migration_connection_secrets) s ON s.connection_id=c.connection_id WHERE c.connection_id=%s",
                    (connection_id,),
                )
                # simpler query
                cur.execute(
                    """
                    SELECT c.status, c.last_error_summary, c.schedule_enabled,
                           (SELECT count(*) FROM employee_migration_connection_secrets s WHERE s.connection_id=c.connection_id) AS secret_n
                    FROM employee_migration_connections c WHERE c.connection_id=%s
                    """,
                    (connection_id,),
                )
                st = dict(cur.fetchone())
                if st.get("status") != "error" or not str(st.get("last_error_summary") or "").startswith(
                    "credentials_require_reentry"
                ):
                    _fail(f"connection not flagged for re-entry: {st}")
                if int(st.get("secret_n") or 0) != 0:
                    _fail("insecure secret not deleted")
                if st.get("schedule_enabled"):
                    _fail("schedule should be disabled after insecure secret")
                conn.commit()
        _ok("scheduler/sync rejects insecure secret without apply")

        # Re-enter credentials under fernet and confirm recovery
        p5.update_connection(
            legacy,
            context,
            connection_id=connection_id,
            credentials={"password": "sftppass"},
        )
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT alg FROM employee_migration_connection_secrets WHERE connection_id=%s",
                    (connection_id,),
                )
                alg = cur.fetchone()["alg"]
                if alg != "fernet":
                    _fail(f"re-entered secret not fernet: {alg}")
                conn.commit()
        _ok("credential re-entry reseals with fernet")

        listed = p5.list_connections(legacy, context)
        for c in listed.get("connections") or []:
            blob = str(c)
            if "sftppass" in blob or "plainhex:" in blob:
                _fail("secret leaked in list_connections")
        _ok("API list redacts credentials")

        p5.set_connection_status(legacy, context, connection_id=connection_id, status="disconnected")
        _ok("P5.2 smoke PASS")
    finally:
        legacy.require_employee_roster_admin = original_require  # type: ignore[assignment]
        try:
            sftp_mod.stop_test_sftp_server(server)
        except Exception:
            pass
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    for ek in created_keys:
                        cur.execute(
                            "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                            (company, ek),
                        )
                    cur.execute(
                        "DELETE FROM employee_source_mappings WHERE company_code=%s AND source_system=%s",
                        (company, f"sftp:p52:{tag}"),
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
