#!/usr/bin/env python3
"""Company-scoped operator inspection and safe retry for document storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1]
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import app  # noqa: E402


def rows_for_company(company: str, status: str | None, limit: int) -> list[dict]:
    params: list[object] = [company.upper()]
    status_sql = ""
    if status:
        status_sql = " AND status=%s"
        params.append(status)
    params.append(max(1, min(limit, 500)))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT operation_id, company_code, employee_key, item_id, provider,
                       status, failure_reason, attempt_count, next_attempt_at,
                       created_at, updated_at
                FROM document_storage_operations
                WHERE company_code=%s {status_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [dict(row) for row in cur.fetchall() or []]


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or safely retry document storage reconciliation.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--status")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--retry", metavar="OPERATION_ID", help="Run the normal ownership/reference-checked retry.")
    args = parser.parse_args()
    if args.retry:
        operation = app.document_storage_operation(args.retry)
        if not operation or str(operation.get("company_code") or "").upper() != args.company.upper():
            raise SystemExit("operation was not found in the requested company")
        result = app.reconcile_document_storage_operation(args.retry, lease_owner="operator-cli")
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
        raise SystemExit(0 if result.get("ok") else 1)
    print(json.dumps(rows_for_company(args.company, args.status, args.limit), ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
