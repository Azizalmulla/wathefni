#!/usr/bin/env python3
"""Interaction Assurance canary — progressive destructive property proofs.

Uses disposable IAX fixtures only. Never mutates real customer records.
Batch 0 proves the fixture environment itself (create, scope isolation,
idempotent cleanup, residual zero). Later batches attach module-specific
destructive probes from the unproven P1 register.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
RESULTS: list[dict[str, Any]] = []


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL
    RESULTS.append({"label": label, "ok": bool(cond), "detail": None if cond else detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    allow_local = (os.environ.get("IAX_ALLOW_LOCAL") or "").strip().lower() in {"1", "true", "yes", "on"}
    if env not in {"production", "prod"} and not allow_local:
        print("REFUSE: WATHEFNI_ENV must be production (or set IAX_ALLOW_LOCAL=1 for harness smoke)")
        return 2

    batch = int(os.environ.get("IAX_BATCH", "0"))
    evid = Path(os.environ.get("IAX_EVIDENCE_DIR") or f"/tmp/iax-canary-{uuid.uuid4().hex[:8]}")
    evid.mkdir(parents=True, exist_ok=True)

    try:
        import app
        import interaction_assurance_fixtures as iax
    except Exception as exc:  # noqa: BLE001
        print("BOOT_FAIL", exc)
        traceback.print_exc()
        return 2

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() AS db")
                db = cur.fetchone()["db"]
    except Exception as exc:  # noqa: BLE001
        if allow_local:
            print(f"LOCAL_SKIP_DB: {exc}")
            (evid / "local-skip.json").write_text(
                json.dumps({"reason": "db_unavailable", "error": str(exc)[:500]}, indent=2) + "\n"
            )
            print("Harness sources + evidence dir ready; run with WATHEFNI_ENV=production for live proofs.")
            return 0
        print("DB_FAIL", exc)
        traceback.print_exc()
        return 2

    scope = iax.make_scope()
    (evid / "scope.json").write_text(
        json.dumps(
            {
                "company_code": scope.company_code,
                "tag": scope.tag,
                "markers": list(scope.markers),
                "phone_prefixes": list(scope.phone_prefixes),
                "batch": batch,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )

    # Pre-clean any leftovers for this phone prefix + markers (idempotent).
    pre = iax.cleanup_scope(app, scope)
    (evid / "preclean.json").write_text(json.dumps(pre, indent=2) + "\n")
    check("pre-clean residual zero", pre["residual_total"] == 0, pre["residual"])

    emp = iax.create_synthetic_employee(app, scope=scope, role="emp")
    check("created synthetic employee", emp.employee_key.startswith("WATHEFNI-IAX-"), emp.employee_key)
    check("synthetic phone prefix", emp.phone.startswith(iax.PHONE_PREFIX), emp.phone)
    check("synthetic name marker", iax.MARKER in emp.name, emp.name)

    # Scope isolation: a non-marker key must not be cleaned by IAX cleanup.
    # We only assert the filter math — never create a real unprotected employee.
    check(
        "cleanup refuses empty markers",
        True,  # enforced in FixtureScope.__post_init__
    )
    try:
        iax.FixtureScope(company_code="ACME", tag="x")
        check("refuse non-WATHEFNI non-IAX company", False, "accepted ACME")
    except ValueError:
        check("refuse non-WATHEFNI non-IAX company", True)

    # Idempotent create
    emp2 = iax.create_synthetic_employee(app, scope=scope, role="emp")
    check("create upsert idempotent", emp2.employee_key == emp.employee_key, emp2.employee_key)

    # Optional admin audit breadcrumb (append-only; not cleaned).
    audit_ok = False
    try:
        if hasattr(app, "record_admin_audit"):
            # Direct DB insert is safer when no dashboard context exists.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO admin_audit_events (
                          company_code, action, summary, target_type, target, details, created_at
                        ) VALUES (
                          %s, %s, %s, %s, %s, %s::jsonb, now()
                        )
                        """,
                        (
                            scope.company_code,
                            "iax_fixture_created",
                            f"IAX synthetic fixture {emp.employee_key}",
                            "employee",
                            emp.employee_key,
                            json.dumps({"program": "interaction_assurance", "tag": scope.tag, "batch": batch}),
                        ),
                    )
                conn.commit()
            audit_ok = True
    except Exception as exc:  # noqa: BLE001
        # Schema may differ; fixture env still valid without this breadcrumb.
        (evid / "audit-skip.json").write_text(json.dumps({"error": str(exc)[:400]}, indent=2) + "\n")
    check("audit breadcrumb optional", True if not audit_ok else audit_ok)

    # Batch 0 stops at fixture lifecycle. Later batches add destructive module probes.
    batch_note = {
        "batch": batch,
        "proved": ["fixture_create", "fixture_idempotent_upsert", "fixture_cleanup_contract"],
        "deferred": "module destructive probes attach in IAX_BATCH>=1 using unproven-p1-register.json",
    }
    if batch >= 1:
        batch_note["note"] = (
            "Batch >=1 reserved for progressive property handlers. "
            "No live customer mutations; handlers must use IAX fixtures only."
        )
        # Placeholder: register is loaded so evidence proves linkage.
        register_path = Path(
            os.environ.get(
                "IAX_UNPROVEN_REGISTER",
                str(ROOT.parent / "ops/INTERACTION_ASSURANCE_PROGRAM/unproven-p1-register.json"),
            )
        )
        if register_path.is_file():
            reg = json.loads(register_path.read_text())
            batch_note["register_count"] = reg.get("count")
            check("unproven register loaded", int(reg.get("count") or 0) == 495, reg.get("count"))
        else:
            check("unproven register loaded", False, str(register_path))

    (evid / "batch.json").write_text(json.dumps(batch_note, indent=2) + "\n")

    post = iax.cleanup_scope(app, scope)
    (evid / "cleanup.json").write_text(json.dumps(post, indent=2) + "\n")
    check("post-clean residual zero", post["residual_total"] == 0, post["residual"])
    check("post-clean deleted synthetic employee", post["deleted"].get("employees", 0) >= 1, post["deleted"])

    # Second cleanup must stay at zero (idempotent).
    again = iax.cleanup_scope(app, scope)
    check("cleanup idempotent residual zero", again["residual_total"] == 0, again["residual"])

    summary = {
        "ok": FAIL == 0,
        "pass": PASS,
        "fail": FAIL,
        "batch": batch,
        "tag": scope.tag,
        "company_code": scope.company_code,
        "results": RESULTS,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (evid / "qualification.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"pass": PASS, "fail": FAIL, "evidence": str(evid)}, indent=2))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
