"""Deterministic validation — safety only, no invented values."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _null_if_blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    return text


def _parse_iso(value: Any) -> date | None:
    raw = _null_if_blank(value)
    if not raw or not ISO_DATE_RE.match(raw):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def field_value(fields: dict[str, Any], key: str) -> Any:
    cell = fields.get(key)
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def validate_common_fields(
    fields: dict[str, Any],
    *,
    expected_type: str | None = None,
    document_number_re: re.Pattern[str] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    doc_type = _null_if_blank(field_value(fields, "document_type"))
    issue = _parse_iso(field_value(fields, "issue_date") or field_value(fields, "contract_start_date"))
    expiry = _parse_iso(field_value(fields, "expiry_date") or field_value(fields, "contract_end_date"))
    number = _null_if_blank(field_value(fields, "document_number"))

    for key in ("issue_date", "expiry_date", "contract_start_date", "contract_end_date"):
        raw = field_value(fields, key)
        if raw is not None and _parse_iso(raw) is None and _null_if_blank(raw):
            issues.append(f"invalid_date_format:{key}")

    if issue and expiry and expiry < issue:
        issues.append("expiry_or_end_before_issue_or_start")

    if expected_type and doc_type and doc_type not in {expected_type, "unknown", "residence" if expected_type == "residency" else expected_type}:
        if not (expected_type in {"residence", "residency"} and doc_type in {"residence", "residency"}):
            issues.append(f"type_mismatch:expected_{expected_type}_got_{doc_type}")

    if document_number_re and number and not document_number_re.match(number.replace(" ", "")):
        issues.append("document_number_format_unexpected")

    # Arabic/English kept separate — inventing a translation is forbidden; both may be null.
    name_ar = _null_if_blank(field_value(fields, "employee_name_ar") or field_value(fields, "employee_or_holder_ar"))
    name_en = _null_if_blank(field_value(fields, "employee_name_en") or field_value(fields, "employee_or_holder_en"))
    if name_ar and name_en:
        # Conflicting scripts only flagged when both non-empty and clearly swapped (heuristic).
        ar_chars = sum(1 for ch in name_ar if "\u0600" <= ch <= "\u06FF")
        en_chars = sum(1 for ch in name_en if "\u0600" <= ch <= "\u06FF")
        if ar_chars == 0 and en_chars > 0:
            issues.append("possible_ar_en_name_swap")

    currency = _null_if_blank(field_value(fields, "salary_currency"))
    salary = field_value(fields, "salary_amount")
    if salary is not None and currency is None:
        issues.append("salary_present_currency_missing")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "has_issue_date": issue is not None,
        "has_expiry_date": expiry is not None,
    }


def duplicate_keys(
    *,
    content_sha256: str | None,
    document_type: str | None,
    document_number: str | None,
    company_code: str | None,
) -> dict[str, str]:
    return {
        "content_sha256": str(content_sha256 or ""),
        "identifier_key": f"{(company_code or '').upper()}:{(document_type or 'unknown').lower()}:{(document_number or '').strip().lower()}",
    }
