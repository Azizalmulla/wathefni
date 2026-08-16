#!/usr/bin/env python3
"""Attendance Wave 2D — read-only customer BioTime compatibility probe.

Connects to a BioTime URL, authenticates, samples transaction field shapes,
and reports readiness. NEVER ingests punches into Wathefni authority.
"""

from __future__ import annotations

from typing import Any

from attendance_capture_biotime import BioTimeAuthError, BioTimeClient, extract_transaction_rows, transaction_to_canonical
from attendance_capture_secrets import REDACTED, redact_mapping, safe_error

REQUIRED_FIELDS = ("id", "emp_code", "punch_time", "punch_state")
OPTIONAL_FIELDS = ("verify_type", "terminal_sn", "terminal_alias", "work_code")


def run_readonly_compat(
    *,
    company_code: str,
    base_url: str,
    username: str | None = None,
    password: str | None = None,
    token: str | None = None,
    sample_limit: int = 5,
    connector_id: str = "compat-readonly",
) -> dict[str, Any]:
    """Read-only probe. Returns field coverage + sanitize results. No authority writes."""
    client = BioTimeClient(base_url=base_url, username=username, password=password, token=token)
    report: dict[str, Any] = {
        "ok": False,
        "company_code": company_code.upper(),
        "base_url": base_url,
        "ingest": False,
        "auth_ok": False,
        "sample_count": 0,
        "fields_present": {},
        "privacy_failures": 0,
        "canonical_ok": 0,
        "warnings": [],
        "secrets": REDACTED,
    }
    try:
        if not token and username and password is not None:
            try:
                client.obtain_token()
            except BioTimeAuthError:
                # Basic auth may still work for list
                pass
        payload = client.list_transactions(page=1, limit=sample_limit)
        report["auth_ok"] = True
    except BioTimeAuthError as exc:
        report["error"] = "auth_failed"
        report["detail"] = safe_error(exc)
        return report
    except Exception as exc:  # noqa: BLE001
        report["error"] = "unreachable_or_error"
        report["detail"] = safe_error(exc)
        return report

    rows = extract_transaction_rows(payload)[:sample_limit]
    report["sample_count"] = len(rows)
    if not rows:
        report["warnings"].append("no_transactions_in_sample")
        report["ok"] = True  # auth worked; empty site is still compatible at API level
        return report

    field_hits = {f: 0 for f in REQUIRED_FIELDS + OPTIONAL_FIELDS}
    for row in rows:
        for f in field_hits:
            if row.get(f) not in (None, ""):
                field_hits[f] += 1
        mapped = transaction_to_canonical(row, company_code=company_code, connector_id=connector_id)
        if mapped.get("privacy_hard_fail"):
            report["privacy_failures"] += 1
            report["warnings"].append("privacy_hard_fail_in_sample")
        elif mapped.get("ok"):
            report["canonical_ok"] += 1
        else:
            report["warnings"].append(str(mapped.get("error") or "map_failed"))

    report["fields_present"] = field_hits
    missing_required = [f for f in REQUIRED_FIELDS if field_hits[f] == 0]
    if missing_required:
        report["error"] = "missing_required_fields"
        report["missing_required"] = missing_required
        return report
    if report["privacy_failures"] > 0:
        report["error"] = "privacy_unsafe_fields_in_feed"
        return report
    report["ok"] = True
    report["sample_preview"] = [redact_mapping({k: r.get(k) for k in list(REQUIRED_FIELDS) + list(OPTIONAL_FIELDS)}) for r in rows[:2]]
    return report
