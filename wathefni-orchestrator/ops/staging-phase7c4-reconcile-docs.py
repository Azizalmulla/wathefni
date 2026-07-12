#!/usr/bin/env python3
"""Phase 7C.4 — guarded dry-run + apply for document reconciliation.

Dry-run default. Apply requires all 7C.3 gates and canary caps.
Phase 7C.4 policy: refuse apply on WATHEFNI and on production DSNs.

Usage (dry-run):
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
    python3 ops/staging-phase7c4-reconcile-docs.py --company P7C4STG01 \\
      --employee-sample-id emp_… --document-type civil_id \\
      --jsonl-out /tmp/plan.jsonl --summary-out /tmp/sum.json

Usage (apply — throwaway only):
  WATHEFNI_RECONCILE_APPLY=1 WATHEFNI_POSTGRES_ENV=.../postgres.staging.env \\
    python3 ops/staging-phase7c4-reconcile-docs.py --company P7C4STG01 \\
      --mode apply --confirm-company P7C4STG01 --i-understand-writes \\
      --confirm-apply-token TOKEN --expect-plan-hash HASH \\
      --employee-sample-id emp_… --document-type civil_id --max-writes 1 \\
      --apply-jsonl-out /tmp/apply.jsonl --summary-out /tmp/apply-sum.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OPS_ROOT = Path(__file__).resolve().parent
if str(OPS_ROOT) not in sys.path:
    sys.path.insert(0, str(OPS_ROOT))

from lib import doc_type_map as tm  # noqa: E402

APPLY_ACTOR = "phase7c3-reconcile-apply"
TOKEN_TTL_MIN = 30
ALLOWED_ACTIONS = {
    "mark_onboarding_received",
    "insert_employee_document_from_file",
    "sync_expiry",
    "fill_compliance_expiry_from_ed",
}
FORBID_APPLY_COMPANIES = {"WATHEFNI"}


def _load_p7c2():
    path = OPS_ROOT / "staging-phase7c2-reconcile-docs-dryrun.py"
    spec = importlib.util.spec_from_file_location("p7c2_dryrun", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load planner: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


p7c2 = _load_p7c2()


def sample_id(employee_key: str) -> str:
    return p7c2.sample_id(employee_key)


def json_safe(value: Any) -> Any:
    return p7c2.json_safe(value)


def load_env(path: Path) -> None:
    p7c2.load_env(path)


def as_date(value: Any) -> date | None:
    return p7c2.as_date(value)


def dsn_is_staging(dsn: str) -> bool:
    d = dsn.lower()
    return "staging" in d or "wathefni_staging" in d


def dsn_is_production(dsn: str) -> bool:
    d = dsn.lower()
    if dsn_is_staging(d):
        return False
    return d.rstrip("/").endswith("/wathefni") or "/wathefni?" in d


def connect_readonly(*, allow_production_dsn: bool = False):
    return p7c2.connect_readonly(allow_production_dsn=allow_production_dsn)


def connect_readwrite():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = os.environ.get("WATHEFNI_DATABASE_URL")
    if not dsn:
        raise SystemExit("WATHEFNI_DATABASE_URL missing")
    if dsn_is_production(dsn):
        raise SystemExit("refusing production-looking DSN for apply (Phase 7C.4)")
    if not dsn_is_staging(dsn):
        raise SystemExit("refusing non-staging DSN for Phase 7C.4 apply")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def canonical_plan_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans = [e for e in events if e.get("decision") == "plan"]
    stable = []
    for e in plans:
        stable.append(
            {
                "action": e.get("action"),
                "after": e.get("after"),
                "before": e.get("before"),
                "company_code": e.get("company_code"),
                "decision": e.get("decision"),
                "drift_class": e.get("drift_class"),
                "natural_key": e.get("natural_key"),
                "op": e.get("op"),
                "sample_id": e.get("sample_id"),
                "table": e.get("table"),
            }
        )
    return sorted(stable, key=lambda row: json.dumps(row, sort_keys=True))


def plan_hash_for(events: list[dict[str, Any]]) -> str:
    plans = canonical_plan_events(events)
    blob = "\n".join(json.dumps(e, sort_keys=True, separators=(",", ":")) for e in plans)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def make_apply_token(company: str, plan_hash: str, expires_at: str) -> str:
    secret = os.environ.get("WATHEFNI_RECONCILE_TOKEN_SECRET", "phase7c4-local-token")
    payload = f"{company.upper()}|{plan_hash}|{expires_at}|{secret}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def verify_apply_token(company: str, plan_hash: str, token: str, expires_at: str) -> None:
    if not expires_at:
        raise SystemExit("apply token missing expiry")
    exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if exp < datetime.now(timezone.utc):
        raise SystemExit("apply token expired")
    expected = make_apply_token(company, plan_hash, expires_at)
    if not token or token != expected:
        raise SystemExit("wrong apply token")


def filter_events(
    events: list[dict[str, Any]],
    *,
    sample_id_filter: str | None,
    document_type: str | None,
) -> list[dict[str, Any]]:
    out = []
    for ev in events:
        if sample_id_filter and ev.get("sample_id") != sample_id_filter:
            continue
        if document_type:
            nk = ev.get("natural_key") or {}
            after = ev.get("after") or {}
            candidates = {
                str(nk.get("document_type") or ""),
                str(nk.get("item_id") or ""),
                str(after.get("document_type") or ""),
                str(after.get("item_id") or ""),
            }
            if document_type not in candidates:
                continue
        out.append(ev)
    return out


def resolve_employee_key(cur, company: str, sid: str) -> str | None:
    cur.execute("SELECT employee_key FROM employees WHERE company_code=%s", (company,))
    for row in cur.fetchall():
        key = str(row["employee_key"])
        if sample_id(key) == sid:
            return key
    return None


def execute_plan_event(cur, company: str, employee_key: str, event: dict[str, Any]) -> int:
    action = event["action"]
    table = event.get("table")
    before = event.get("before") or {}
    after = event.get("after") or {}
    nk = event.get("natural_key") or {}

    if action == "mark_onboarding_received":
        item_id = nk.get("item_id")
        cur.execute(
            "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
            (employee_key, item_id),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("stale_before_image")
        live = str(row.get("status") or "").lower()
        expected = str(before.get("status") or "").lower()
        if expected and expected not in {"empty", ""} and live != expected:
            raise RuntimeError("stale_before_image")
        if live in tm.RECEIVED_LIKE:
            raise RuntimeError("stale_before_image")
        cur.execute(
            """
            UPDATE onboarding_items
            SET status='received', updated_at=now()
            WHERE employee_key=%s AND item_id=%s
            """,
            (employee_key, item_id),
        )
        return int(cur.rowcount)

    if action == "insert_employee_document_from_file":
        dt = str(nk.get("document_type") or after.get("document_type") or "")
        cur.execute(
            "SELECT 1 FROM employee_documents WHERE employee_key=%s AND document_type=%s LIMIT 1",
            (employee_key, dt),
        )
        if cur.fetchone():
            raise RuntimeError("stale_before_image")
        cur.execute(
            """
            SELECT content_sha256, storage_status, storage_provider, storage_object_key,
                   external_file_id, mime_type
            FROM file_registry
            WHERE company_code=%s AND subject_type='employee' AND subject_key=%s
              AND document_type=%s AND file_kind = ANY(%s)
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
            """,
            (company, employee_key, dt, list(tm.EMPLOYEE_FILE_KINDS)),
        )
        fr = cur.fetchone()
        if not fr:
            raise RuntimeError("no_supported_file")
        cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (employee_key,))
        phone = str((cur.fetchone() or {}).get("phone") or "")
        expiry = as_date(after.get("expiry_date"))
        item_id = after.get("item_id") or (dt if dt in tm.ONBOARDING_DOCUMENT_ITEMS else dt)
        cur.execute(
            """
            INSERT INTO employee_documents (
                employee_key, phone, company_code, item_id, document_type, status,
                expiry_date, content_sha256, storage_status, storage_provider,
                storage_object_key, external_file_id, mime_type, metadata, raw_json
            ) VALUES (%s,%s,%s,%s,%s,'received',%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb,'{}'::jsonb)
            """,
            (
                employee_key,
                phone,
                company,
                item_id,
                dt,
                expiry,
                fr.get("content_sha256"),
                fr.get("storage_status") or "stored",
                fr.get("storage_provider"),
                fr.get("storage_object_key"),
                fr.get("external_file_id"),
                fr.get("mime_type"),
            ),
        )
        return int(cur.rowcount)

    if action == "sync_expiry":
        dt = str(nk.get("document_type") or "")
        new_exp = as_date(after.get("expiry_date"))
        if new_exp is None:
            raise RuntimeError("expiry_candidate_null")
        if table == "employee_documents":
            cur.execute(
                """
                SELECT document_id, expiry_date FROM employee_documents
                WHERE employee_key=%s AND document_type=%s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (employee_key, dt),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("stale_before_image")
            live_exp = as_date(row.get("expiry_date"))
            expected = as_date(before.get("expiry_date"))
            if expected is not None and live_exp != expected:
                raise RuntimeError("stale_before_image")
            if live_exp is not None and new_exp < live_exp:
                raise RuntimeError("expiry_older_than_existing")
            cur.execute(
                "UPDATE employee_documents SET expiry_date=%s, updated_at=now() WHERE document_id=%s",
                (new_exp, row["document_id"]),
            )
            return int(cur.rowcount)
        if table == "compliance_documents":
            cur.execute(
                "SELECT expiry_date FROM compliance_documents WHERE employee_key=%s AND document_type=%s",
                (employee_key, dt),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("stale_before_image")
            live_exp = as_date(row.get("expiry_date"))
            expected = as_date(before.get("expiry_date"))
            if expected is not None and live_exp != expected:
                raise RuntimeError("stale_before_image")
            if live_exp is not None and new_exp < live_exp:
                raise RuntimeError("expiry_older_than_existing")
            days = (new_exp - date.today()).days
            cur.execute(
                """
                UPDATE compliance_documents
                SET expiry_date=%s, days_until_expiry=%s, updated_at=now()
                WHERE employee_key=%s AND document_type=%s
                """,
                (new_exp, days, employee_key, dt),
            )
            return int(cur.rowcount)
        raise RuntimeError(f"unsupported sync_expiry table={table}")

    if action == "fill_compliance_expiry_from_ed":
        dt = str(nk.get("document_type") or "")
        new_exp = as_date(after.get("expiry_date"))
        if new_exp is None:
            raise RuntimeError("expiry_candidate_null")
        cur.execute(
            "SELECT expiry_date FROM compliance_documents WHERE employee_key=%s AND document_type=%s",
            (employee_key, dt),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("stale_before_image")
        live_exp = as_date(row.get("expiry_date"))
        if live_exp is not None:
            raise RuntimeError("expiry_candidate_null")
        days = (new_exp - date.today()).days
        cur.execute(
            """
            UPDATE compliance_documents
            SET expiry_date=%s, days_until_expiry=%s, updated_at=now()
            WHERE employee_key=%s AND document_type=%s AND expiry_date IS NULL
            """,
            (new_exp, days, employee_key, dt),
        )
        return int(cur.rowcount)

    raise RuntimeError(f"unsupported_action:{action}")


def build_apply_audit(
    plan_event: dict[str, Any],
    *,
    company: str,
    plan_hash: str,
    decision: str,
    rowcount: int | None = None,
    skip_reason: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    nk = dict(plan_event.get("natural_key") or {})
    return json_safe(
        {
            "event_id": str(uuid.uuid4()),
            "plan_event_id": plan_event.get("event_id"),
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "schema_version": 1,
            "mode": "apply",
            "actor": APPLY_ACTOR,
            "operator": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "host": socket.gethostname(),
            "company_code": company,
            "sample_id": plan_event.get("sample_id"),
            "drift_class": plan_event.get("drift_class"),
            "action": plan_event.get("action"),
            "decision": decision,
            "skip_reason": skip_reason,
            "error": error,
            "table": plan_event.get("table"),
            "op": plan_event.get("op"),
            "natural_key": nk,
            "document_type": nk.get("document_type") or nk.get("item_id"),
            "before": plan_event.get("before"),
            "after": plan_event.get("after"),
            "rowcount": rowcount,
            "plan_hash": plan_hash,
            "guards": plan_event.get("guards")
            or {"expiry_rule": None, "no_delete": True, "alias_merge": False},
        }
    )


def run_dry_run(args: argparse.Namespace, company: str) -> tuple[list[dict], dict]:
    conn = connect_readonly(allow_production_dsn=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok FROM companies WHERE company_code=%s LIMIT 1", (company,))
            if not cur.fetchone():
                raise SystemExit(f"company not found: {company}")
            events, summary = p7c2.plan_company(cur, company)
    finally:
        conn.close()

    if args.employee_sample_id or args.document_type:
        events = filter_events(
            events,
            sample_id_filter=args.employee_sample_id or None,
            document_type=args.document_type or None,
        )
        summary = p7c2.build_summary(company, events)

    ph = plan_hash_for(events)
    expires = (
        datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MIN)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    token = make_apply_token(company, ph, expires)
    summary.update(
        {
            "mode": "dry-run",
            "read_only": True,
            "no_writes": True,
            "apply_enabled": False,
            "plan_hash": ph,
            "apply_token": token,
            "apply_token_expires_at": expires,
            "production_apply_authorized": False,
            "canary": {
                "employee_sample_id": args.employee_sample_id or None,
                "document_type": args.document_type or None,
            },
            "planned_writes": sum(1 for e in events if e.get("decision") == "plan"),
        }
    )
    return events, summary


def run_apply(args: argparse.Namespace, company: str) -> tuple[list[dict], dict]:
    if os.environ.get("WATHEFNI_RECONCILE_APPLY", "").strip() != "1":
        raise SystemExit("missing env gate: WATHEFNI_RECONCILE_APPLY=1 required for apply")
    if not args.i_understand_writes:
        raise SystemExit("missing confirm flag: --i-understand-writes")
    if str(args.confirm_company or "").strip().upper() != company:
        raise SystemExit("company confirmation mismatch")
    if company in FORBID_APPLY_COMPANIES:
        raise SystemExit(f"refusing apply on forbidden company {company} (Phase 7C.4 throwaway only)")
    if not args.employee_sample_id or not args.document_type:
        raise SystemExit("canary caps required: --employee-sample-id and --document-type")
    max_writes = int(args.max_writes)
    if max_writes < 1:
        raise SystemExit("--max-writes must be >= 1")

    # Fresh dry-run for plan binding
    events, dry_summary = run_dry_run(args, company)
    plan_events = [e for e in events if e.get("decision") == "plan"]
    ph = dry_summary["plan_hash"]
    expires = dry_summary["apply_token_expires_at"]

    if args.expect_plan_hash and args.expect_plan_hash != ph:
        raise SystemExit("wrong plan hash")
    expires_for_token = str(args.apply_token_expires_at or "").strip()
    if not expires_for_token:
        raise SystemExit("missing --apply-token-expires-at from dry-run summary")
    verify_apply_token(company, ph, str(args.confirm_apply_token or ""), expires_for_token)

    for ev in plan_events:
        if ev.get("action") not in ALLOWED_ACTIONS:
            raise SystemExit(f"plan contains non-W1–W4 action: {ev.get('action')}")
        if (ev.get("guards") or {}).get("alias_merge") is True:
            raise SystemExit("refusing alias merge plan")

    if len(plan_events) > max_writes:
        raise SystemExit(
            f"max-writes exceeded: filtered plan has {len(plan_events)} events > max-writes={max_writes}"
        )

    audit: list[dict[str, Any]] = []
    applied = skipped = failed = 0

    conn = connect_readwrite()
    try:
        with conn.cursor() as cur:
            for ev in plan_events:
                sid = str(ev.get("sample_id") or "")
                emp = resolve_employee_key(cur, company, sid)
                if not emp:
                    audit.append(
                        build_apply_audit(
                            ev,
                            company=company,
                            plan_hash=ph,
                            decision="failed",
                            skip_reason="orphan_employee_key",
                            error="sample_id not resolved",
                        )
                    )
                    failed += 1
                    conn.rollback()
                    break
                try:
                    rowcount = execute_plan_event(cur, company, emp, ev)
                    if rowcount != 1:
                        raise RuntimeError(f"unexpected_rowcount:{rowcount}")
                    audit.append(
                        build_apply_audit(
                            ev,
                            company=company,
                            plan_hash=ph,
                            decision="applied",
                            rowcount=rowcount,
                        )
                    )
                    applied += 1
                    if applied >= max_writes:
                        break
                except Exception as exc:  # noqa: BLE001
                    reason = str(exc)
                    soft = {
                        "stale_before_image",
                        "expiry_older_than_existing",
                        "expiry_candidate_null",
                        "no_supported_file",
                    }
                    decision = (
                        "skipped"
                        if reason in soft or reason.startswith("stale_before_image")
                        else "failed"
                    )
                    audit.append(
                        build_apply_audit(
                            ev,
                            company=company,
                            plan_hash=ph,
                            decision=decision,
                            skip_reason=reason.split(":")[0],
                            error=reason,
                        )
                    )
                    if decision == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                    conn.rollback()
                    break
            if failed == 0 and skipped == 0:
                conn.commit()
            else:
                conn.rollback()
    finally:
        conn.close()

    summary = {
        "mode": "apply",
        "company_code": company,
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "max_writes": max_writes,
        "canary": {
            "employee_sample_id": args.employee_sample_id,
            "document_type": args.document_type,
        },
        "plan_hash": ph,
        "no_deletes": True,
        "production_apply_authorized": False,
        "dry_run_planned_writes": dry_summary.get("planned_writes"),
    }
    return audit, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7C.4 dry-run + guarded apply")
    parser.add_argument("--company", required=True)
    parser.add_argument("--mode", default="dry-run", choices=["dry-run", "apply"])
    parser.add_argument(
        "--postgres-env",
        default=os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"),
    )
    parser.add_argument("--jsonl-out", default="")
    parser.add_argument("--apply-jsonl-out", default="")
    parser.add_argument("--summary-out", default="")
    parser.add_argument("--confirm-company", default="")
    parser.add_argument("--i-understand-writes", action="store_true")
    parser.add_argument("--confirm-apply-token", default="")
    parser.add_argument("--apply-token-expires-at", default="", help="ISO expiry from dry-run summary")
    parser.add_argument("--expect-plan-hash", default="")
    parser.add_argument("--employee-sample-id", default="")
    parser.add_argument("--document-type", default="")
    parser.add_argument("--max-writes", type=int, default=1)
    parser.add_argument("--allow-production-dsn", action="store_true")
    args = parser.parse_args()

    company = str(args.company or "").strip().upper()
    if not company:
        raise SystemExit("--company is required")
    if company in {"ALL", "*", "ANY"}:
        raise SystemExit("refusing broad ALL-company run")

    load_env(Path(args.postgres_env))
    dsn = os.environ.get("WATHEFNI_DATABASE_URL", "")
    if args.mode == "apply":
        if args.allow_production_dsn:
            raise SystemExit("Phase 7C.4 refuses --allow-production-dsn for apply")
        if dsn_is_production(dsn):
            raise SystemExit("refusing production DSN for apply (Phase 7C.4)")
        events, summary = run_apply(args, company)
        out_path = args.apply_jsonl_out or args.jsonl_out
        text = "\n".join(json.dumps(e, sort_keys=True) for e in events)
        if events:
            text += "\n"
        if out_path:
            Path(out_path).write_text(text)
        if args.summary_out:
            Path(args.summary_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("APPLY_ENABLED=true")
        print(f"APPLIED={summary.get('applied')}")
        return 0 if summary.get("failed", 0) == 0 else 1

    # dry-run
    if args.allow_production_dsn and dsn_is_production(dsn):
        # still allow dry-run only with flag — but 7C.4 verifier won't use it
        pass
    elif dsn_is_production(dsn):
        raise SystemExit("refusing production-looking DSN without --allow-production-dsn")

    events, summary = run_dry_run(args, company)
    text = "\n".join(json.dumps(e, sort_keys=True) for e in events)
    if events:
        text += "\n"
    if args.jsonl_out:
        Path(args.jsonl_out).write_text(text)
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("NO_WRITES=true")
    print("APPLY_ENABLED=false")
    print(f"PLAN_HASH={summary.get('plan_hash')}")
    print(f"APPLY_TOKEN={summary.get('apply_token')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
