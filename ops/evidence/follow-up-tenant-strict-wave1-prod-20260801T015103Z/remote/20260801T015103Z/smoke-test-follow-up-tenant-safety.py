#!/usr/bin/env python3
"""Wave 1 strict tenant safety: predicate + migration classification proofs.

Proves:
  - Predicate is strict ode.company_code = a.company_code (no COALESCE)
  - Null-company events cannot qualify any application
  - Explicit Tenant A events cannot qualify Tenant B (same app_key)
  - Same-tenant failed still qualify; sent/recovered excluded
  - Ambiguous multi-tenant app_keys are classified quarantine, not backfilled
  - Unambiguous application ownership is backfill-eligible
  - Orphans are reported/quarantined, never silently assigned
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prehire_overview as po

_MIG_PATH = ROOT / "ops" / "migrate-outbound-delivery-company-ownership.py"
_spec = importlib.util.spec_from_file_location("ode_company_mig", _MIG_PATH)
assert _spec and _spec.loader
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def prove_predicate_strict() -> None:
    sql = " ".join(po.follow_up_needed_exists("a").split())
    compact = sql.replace(" ", "")
    assert_true("ode.subject_key=a.app_key" in compact, "matches subject_key")
    assert_true("ode.company_code=a.company_code" in compact, "strict company_code equality")
    assert_true("COALESCE(ode.company_code" not in sql, "no COALESCE on company_code")
    assert_true("NOT IN ('sent','recovered')" in sql, "excludes sent/recovered")
    print("PASS: strict predicate shape")


def _qualifies(conn: sqlite3.Connection, app_key: str, company: str) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1 FROM outbound_delivery_events ode
          WHERE ode.subject_key = ?
            AND ode.company_code = ?
            AND COALESCE(ode.status, '') NOT IN ('sent','recovered')
            AND ode.recovered_at IS NULL
            AND (ode.status='failed' OR ode.last_error IS NOT NULL)
        )
        """,
        (app_key, company),
    ).fetchone()
    return bool(row[0])


def prove_runtime_isolation() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE applications (app_key TEXT, company_code TEXT);
        CREATE TABLE outbound_delivery_events (
          delivery_id TEXT PRIMARY KEY,
          subject_key TEXT,
          company_code TEXT,
          status TEXT,
          last_error TEXT,
          recovered_at TEXT
        );
        """
    )
    shared = "SHARED-KEY"
    conn.execute("INSERT INTO applications VALUES (?,?)", (shared, "TENANT_A"))
    conn.execute("INSERT INTO applications VALUES (?,?)", (shared, "TENANT_B"))
    conn.execute("INSERT INTO applications VALUES (?,?)", ("A-ONLY", "TENANT_A"))
    conn.execute("INSERT INTO applications VALUES (?,?)", ("SENT", "TENANT_A"))
    conn.execute("INSERT INTO applications VALUES (?,?)", ("REC", "TENANT_A"))
    conn.execute("INSERT INTO applications VALUES (?,?)", ("NULL-APP", "TENANT_A"))

    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e1", shared, "TENANT_A", "failed", "x", None),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e2", "A-ONLY", "TENANT_A", "failed", "x", None),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e3", "SENT", "TENANT_A", "sent", None, None),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e4", "REC", "TENANT_A", "failed", "x", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e5", "NULL-APP", None, "failed", "legacy", None),
    )
    # Orphan null event with colliding subject_key should not qualify either tenant
    # via null company_code.
    conn.execute(
        "INSERT INTO outbound_delivery_events VALUES (?,?,?,?,?,?)",
        ("e6", shared, None, "failed", "null_cc", None),
    )

    assert_true(_qualifies(conn, shared, "TENANT_A"), "same-tenant failed qualifies")
    assert_true(not _qualifies(conn, shared, "TENANT_B"), "cross-tenant explicit blocked")
    assert_true(_qualifies(conn, "A-ONLY", "TENANT_A"), "same-tenant only app qualifies")
    assert_true(not _qualifies(conn, "SENT", "TENANT_A"), "sent excluded")
    assert_true(not _qualifies(conn, "REC", "TENANT_A"), "recovered excluded")
    assert_true(not _qualifies(conn, "NULL-APP", "TENANT_A"), "null company_code cannot qualify")
    assert_true(not _qualifies(conn, shared, "TENANT_B"), "null shared-key event cannot qualify Tenant B")
    print("PASS: runtime isolation (null + cross-tenant + sent/recovered)")


def prove_classification() -> None:
    backfill = _mig.classify_null_company_event(
        delivery_id="d1",
        subject_key="APP-1",
        app_companies=["WATHEFNI"],
    )
    assert_true(backfill["class"] == _mig.CLASS_BACKFILL, "unambiguous backfill")
    assert_true(backfill["owner_company_code"] == "WATHEFNI", "owner set")

    ambiguous = _mig.classify_null_company_event(
        delivery_id="d2",
        subject_key="SHARED",
        app_companies=["TENANT_A", "TENANT_B"],
    )
    assert_true(ambiguous["class"] == _mig.CLASS_AMBIGUOUS, "multi-tenant quarantined")
    assert_true(ambiguous["owner_company_code"] is None, "ambiguous not assigned")

    orphan = _mig.classify_null_company_event(
        delivery_id="d3",
        subject_key="WATHEFNI-NO-APP",
        app_companies=[],
    )
    assert_true(orphan["class"] == _mig.CLASS_ORPHAN, "orphan quarantined")
    assert_true(orphan["owner_company_code"] is None, "orphan not assigned")

    # Heuristic-looking orphan must still not be assigned by classifier
    assert_true(orphan.get("owner_company_code") is None, "no silent WATHEFNI embed assignment")
    print("PASS: classification (backfill / ambiguous / orphan)")


def prove_sqlite_migration_apply() -> None:
    """Apply classification rules in sqlite: backfill unambiguous, leave others null."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE applications (app_key TEXT, company_code TEXT);
        CREATE TABLE outbound_delivery_events (
          delivery_id TEXT PRIMARY KEY,
          subject_key TEXT,
          company_code TEXT,
          status TEXT,
          last_error TEXT,
          recovered_at TEXT,
          payload TEXT DEFAULT '{}'
        );
        """
    )
    # Unambiguous WATHEFNI app
    conn.execute("INSERT INTO applications VALUES ('APP-W','WATHEFNI')")
    # Ambiguous collision
    conn.execute("INSERT INTO applications VALUES ('SHARED','TENANT_A')")
    conn.execute("INSERT INTO applications VALUES ('SHARED','TENANT_B')")
    conn.execute(
        "INSERT INTO outbound_delivery_events(delivery_id,subject_key,company_code,status,last_error) VALUES (?,?,?,?,?)",
        ("bf1", "APP-W", None, "failed", "no_usable_conversation_id"),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events(delivery_id,subject_key,company_code,status,last_error) VALUES (?,?,?,?,?)",
        ("amb1", "SHARED", None, "failed", "x"),
    )
    conn.execute(
        "INSERT INTO outbound_delivery_events(delivery_id,subject_key,company_code,status,last_error) VALUES (?,?,?,?,?)",
        ("orp1", "NO-APP", None, "failed", "x"),
    )

    rows = conn.execute("SELECT * FROM outbound_delivery_events WHERE company_code IS NULL").fetchall()
    reported_ambiguous = []
    reported_orphan = []
    for r in rows:
        companies = [
            row["company_code"]
            for row in conn.execute(
                "SELECT DISTINCT company_code FROM applications WHERE app_key=?",
                (r["subject_key"],),
            )
        ]
        cls = _mig.classify_null_company_event(
            delivery_id=r["delivery_id"],
            subject_key=r["subject_key"],
            app_companies=companies,
        )
        if cls["class"] == _mig.CLASS_BACKFILL:
            conn.execute(
                "UPDATE outbound_delivery_events SET company_code=? WHERE delivery_id=?",
                (cls["owner_company_code"], r["delivery_id"]),
            )
        elif cls["class"] == _mig.CLASS_AMBIGUOUS:
            reported_ambiguous.append(cls)
        else:
            reported_orphan.append(cls)

    assert_true(
        conn.execute(
            "SELECT company_code FROM outbound_delivery_events WHERE delivery_id='bf1'"
        ).fetchone()[0]
        == "WATHEFNI",
        "unambiguous backfilled",
    )
    assert_true(
        conn.execute(
            "SELECT company_code FROM outbound_delivery_events WHERE delivery_id='amb1'"
        ).fetchone()[0]
        is None,
        "ambiguous left null (not silently assigned)",
    )
    assert_true(
        conn.execute(
            "SELECT company_code FROM outbound_delivery_events WHERE delivery_id='orp1'"
        ).fetchone()[0]
        is None,
        "orphan left null (not silently assigned)",
    )
    assert_true(len(reported_ambiguous) == 1, "ambiguous reported")
    assert_true(len(reported_orphan) == 1, "orphan reported")
    assert_true(_qualifies(conn, "APP-W", "WATHEFNI"), "backfilled event qualifies WATHEFNI")
    assert_true(not _qualifies(conn, "SHARED", "TENANT_A"), "ambiguous null cannot qualify A")
    assert_true(not _qualifies(conn, "SHARED", "TENANT_B"), "ambiguous null cannot qualify B")
    print("PASS: sqlite migration apply + report ambiguous/orphan")


def prove_call_sites() -> None:
    text = (ROOT / "prehire_overview.py").read_text(encoding="utf-8")
    assert_true("ode.company_code={alias}.company_code" in text, "helper template strict")
    assert_true(text.count("ode.company_code=a.company_code") >= 2, "companion JOINs strict")
    assert_true("COALESCE(ode.company_code" not in text, "no COALESCE company in overview")
    for name in ("app.py", "reports_metrics.py", "reports_v1.py"):
        body = (ROOT / name).read_text(encoding="utf-8")
        assert_true("follow_up_needed_exists" in body, f"{name} uses helper")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert_true("_resolve_outbound_delivery_company_code" in app_src, "write-path resolver present")
    assert_true("company_code_required" in app_src, "write-path requires company_code")
    print("PASS: call sites + write-path require company_code")


def main() -> None:
    prove_predicate_strict()
    prove_runtime_isolation()
    prove_classification()
    prove_sqlite_migration_apply()
    prove_call_sites()
    print("PASS: follow_up_needed Wave 1 STRICT tenant safety")


if __name__ == "__main__":
    main()
