"""Payroll External Adapter Wave 2A — synthetic CSV/SFTP foundation (staging).

Uses frozen Wave 1 contracts:
  PayrollInputExport@1.0.0
  PayrollResultImport@1.0.0

Builds one complete external flow:
  export → import → quarantine → reconcile
  with fingerprints, external_run_id idempotency, and rollback.

Does NOT: enable payment_processing, native G2N, PIFSS, WPS/bank files,
EOS, journals, XBRL, or Wathefni money authority.
Does NOT alter Wave 1 contract/period DDL.
Does NOT claim support for a real vendor schema.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import payroll_authority_wave1 as pyw1

PAYROLL_WAVE2A_VERSION = "1.0.0"
ADAPTER_KIND = "synthetic_csv_sftp"
ADAPTER_LABEL = "Synthetic generic CSV/SFTP (not a real vendor)"

_ON = {"1", "true", "yes", "on"}

DEFAULT_SYNTHETIC_KEY_MARKERS = ("PYW2A", "PYW2A-SYNTH|", "PYW1", "PYW1-SYNTH|")
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539", "965540")

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_external_adapter_wave2a_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""

_SCHEMA_READY = False

# CSV columns for the synthetic generic adapter (input export artifact)
EXPORT_CSV_HEADERS = (
    "employee_key",
    "component_code",
    "component_kind",
    "amount_unit",
    "contract_amount",
    "attendance_minutes",
    "leave_classification",
    "period_start",
    "period_end",
)

# CSV columns for synthetic result import (opaque mirror amounts — external authority)
IMPORT_CSV_HEADERS = (
    "employee_key",
    "component_code",
    "opaque_amount",
    "currency",
    "external_run_id",
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave2a_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE2A", default=False)


def payroll_wave2a_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave2a_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE2A_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave2a_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def is_wave2a_synthetic_employee(*, employee_key: str | None = None, phone: str | None = None) -> bool:
    key = str(employee_key or "")
    phone_d = digits_phone(phone)
    for marker in synthetic_key_markers():
        if marker and marker in key:
            return True
    for prefix in DEFAULT_SYNTHETIC_PHONE_PREFIXES:
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_wave2a_version": PAYROLL_WAVE2A_VERSION,
        "adapter_kind": ADAPTER_KIND,
        "adapter_label": ADAPTER_LABEL,
        "vendor_claimed": False,
        "payment_processing": "disabled",
        "money_authority": "external",
        "wathefni_money_authority": False,
        "posts_payment": False,
        "bank_files": False,
        "native_gross_to_net": False,
        "pifss": False,
        "wps": False,
        "eos": False,
        "journals": False,
        "xbrl": False,
        "input_export_schema": pyw1.PAYROLL_INPUT_EXPORT_SCHEMA,
        "result_import_schema": pyw1.PAYROLL_RESULT_IMPORT_SCHEMA,
        "wave1_contracts_unchanged": True,
        "synthetic_only": payroll_wave2a_synthetic_only(),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "money_authority_external": True,
        "no_bank_files": True,
        "no_native_g2n": True,
        "mirror_only_imports": True,
        "wave1_ddl_untouched": True,
        "vendor_schema_unclaimed": True,
    }


# --------------------------------------------------------------------------- schema


def ensure_payroll_wave2a_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_002
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        # Wave 1 schema is a dependency for periods/settings honesty — never alter its DDL here.
        pyw1.ensure_payroll_wave1_schema(cur)
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    fetched = cur.fetchall() or []
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in fetched]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    # psycopg Decimal / numeric
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    return value


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_payload(payload: dict[str, Any]) -> str:
    """Stable fingerprint over canonical JSON (sorted keys)."""
    canonical = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(canonical)


def require_audit_reason(reason: Any) -> dict[str, Any] | None:
    return pyw1.require_audit_reason(reason)


# --------------------------------------------------------------------------- CSV codec (synthetic generic)


def encode_export_csv(export_payload: dict[str, Any]) -> str:
    """Flatten PayrollInputExport into synthetic generic CSV rows."""
    period = export_payload.get("period") or {}
    p_start = str(period.get("period_start") or "")[:10]
    p_end = str(period.get("period_end") or "")[:10]
    attendance_by_emp: dict[str, int] = {}
    for row in export_payload.get("attendance") or []:
        key = str(row.get("employee_key") or "")
        attendance_by_emp[key] = attendance_by_emp.get(key, 0) + int(row.get("worked_minutes") or row.get("minutes") or 0)
    leave_by_emp: dict[str, str] = {}
    for row in export_payload.get("leave_classifications") or []:
        key = str(row.get("employee_key") or "")
        leave_by_emp[key] = str(row.get("classification") or row.get("leave_type") or "")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(EXPORT_CSV_HEADERS), lineterminator="\n")
    writer.writeheader()
    contracts = export_payload.get("compensation_contracts") or []
    if not contracts:
        for emp in export_payload.get("employees") or []:
            key = str(emp.get("employee_key") or "")
            writer.writerow(
                {
                    "employee_key": key,
                    "component_code": "",
                    "component_kind": "",
                    "amount_unit": "",
                    "contract_amount": "",
                    "attendance_minutes": str(attendance_by_emp.get(key, 0)),
                    "leave_classification": leave_by_emp.get(key, ""),
                    "period_start": p_start,
                    "period_end": p_end,
                }
            )
    for contract in contracts:
        key = str(contract.get("employee_key") or "")
        components = contract.get("components") or [{"code": "BASIC", "component_kind": "earning", "amount_unit": "monthly", "amount": 0}]
        for comp in components:
            writer.writerow(
                {
                    "employee_key": key,
                    "component_code": str(comp.get("code") or ""),
                    "component_kind": str(comp.get("component_kind") or ""),
                    "amount_unit": str(comp.get("amount_unit") or ""),
                    "contract_amount": str(comp.get("amount") if comp.get("amount") is not None else ""),
                    "attendance_minutes": str(attendance_by_emp.get(key, 0)),
                    "leave_classification": leave_by_emp.get(key, ""),
                    "period_start": p_start,
                    "period_end": p_end,
                }
            )
    return buf.getvalue()


def decode_import_csv(csv_text: str) -> dict[str, Any]:
    """Parse synthetic result CSV into PayrollResultImport@1.0.0 payload (mirror-only)."""
    text = str(csv_text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_import_csv"}
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "malformed_csv", "detail": str(exc)[:200]}
    if not reader.fieldnames:
        return {"ok": False, "error": "malformed_csv", "detail": "missing_header"}
    missing = [h for h in IMPORT_CSV_HEADERS if h not in set(reader.fieldnames)]
    if missing:
        return {"ok": False, "error": "malformed_csv", "detail": f"missing_columns:{missing}"}

    lines: list[dict[str, Any]] = []
    external_run_id = ""
    for i, row in enumerate(reader):
        try:
            amount_raw = str(row.get("opaque_amount") or "").strip()
            amount = float(amount_raw) if amount_raw != "" else None
        except ValueError:
            return {"ok": False, "error": "malformed_csv", "detail": f"bad_amount_row_{i}"}
        ext = str(row.get("external_run_id") or "").strip()
        if not external_run_id and ext:
            external_run_id = ext
        if ext and external_run_id and ext != external_run_id:
            return {"ok": False, "error": "malformed_csv", "detail": "mixed_external_run_id"}
        lines.append(
            {
                "employee_key": str(row.get("employee_key") or "").strip(),
                "component_code": str(row.get("component_code") or "").strip(),
                "opaque_amount": amount,
                "currency": str(row.get("currency") or "KWD").strip() or "KWD",
                "raw": dict(row),
            }
        )
    if not external_run_id:
        return {"ok": False, "error": "malformed_csv", "detail": "missing_external_run_id"}
    payload = {
        "schema": pyw1.PAYROLL_RESULT_IMPORT_SCHEMA,
        "payment_processing": "disabled",
        "posts_payment": False,
        "money_authority": "external",  # string authority label — not boolean True
        "mirror_only": True,
        "external_run_id": external_run_id,
        "adapter_kind": ADAPTER_KIND,
        "lines": lines,
    }
    # Wave 1 validator forbids money_authority=True (bool). String "external" is OK.
    valid = pyw1.validate_result_import_schema(
        {
            **payload,
            "money_authority": False,  # Wathefni does not hold money authority
        }
    )
    if not valid.get("ok"):
        return valid
    return {"ok": True, "payload": payload}


def build_synthetic_result_csv(
    *,
    export_payload: dict[str, Any],
    external_run_id: str,
    amount_fn: Any | None = None,
) -> str:
    """Generate a matching synthetic result CSV from an export (for clean-import proofs)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(IMPORT_CSV_HEADERS), lineterminator="\n")
    writer.writeheader()
    for contract in export_payload.get("compensation_contracts") or []:
        key = str(contract.get("employee_key") or "")
        for comp in contract.get("components") or []:
            code = str(comp.get("code") or "BASIC")
            base = float(comp.get("amount") or 0)
            opaque = float(amount_fn(key, code, base)) if amount_fn else base
            writer.writerow(
                {
                    "employee_key": key,
                    "component_code": code,
                    "opaque_amount": f"{opaque:.3f}",
                    "currency": str(contract.get("currency") or "KWD"),
                    "external_run_id": external_run_id,
                }
            )
    return buf.getvalue()


# --------------------------------------------------------------------------- quarantine helper


def _quarantine(
    cur: Any,
    *,
    company_code: str,
    source_kind: str,
    reason: str,
    export_run_id: str | None = None,
    import_run_id: str | None = None,
    artifact_excerpt: str | None = None,
    payload: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO payroll_adapter_quarantine (
          company_code, source_kind, export_run_id, import_run_id, reason,
          artifact_excerpt, payload, hard_deleted, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,false,%s)
        RETURNING *
        """,
        (
            company,
            source_kind,
            export_run_id,
            import_run_id,
            reason,
            (artifact_excerpt or "")[:2000],
            json.dumps(_json_safe(payload or {})),
            digits_phone(actor_phone),
        ),
    )
    return _row(cur) or {}


def _event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    export_run_id: str | None = None,
    import_run_id: str | None = None,
    payload: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_adapter_events (company_code, export_run_id, import_run_id, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            export_run_id,
            import_run_id,
            event_type,
            json.dumps(_json_safe(payload or {})),
            digits_phone(actor_phone),
        ),
    )


# --------------------------------------------------------------------------- export


def create_external_export(
    cur: Any,
    *,
    company_code: str,
    period: dict[str, Any],
    employees: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    shifts: list[dict[str, Any]] | None = None,
    attendance: list[dict[str, Any]] | None = None,
    leave_classifications: list[dict[str, Any]] | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    external_run_id: str | None = None,
) -> dict[str, Any]:
    """Build + persist a PayrollInputExport and synthetic CSV artifact."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2a_schema(cur)
    company = (company_code or "").upper()

    if payroll_wave2a_synthetic_only():
        for emp in employees:
            key = str(emp.get("employee_key") or "")
            if not is_wave2a_synthetic_employee(employee_key=key, phone=emp.get("phone") or emp.get("employee_phone")):
                return {"ok": False, "error": "payroll_wave2a_synthetic_only", "employee_key": key}

    built = pyw1.build_input_export(
        company_code=company,
        period=period,
        employees=employees,
        contracts=contracts,
        shifts=shifts or [],
        attendance=attendance or [],
        leave_classifications=leave_classifications or [],
    )
    if not built.get("ok"):
        return built
    export_payload = built["export"]
    # Authority honesty on export envelope
    export_payload["money_authority"] = "external"
    export_payload["adapter_kind"] = ADAPTER_KIND
    export_payload["vendor_claimed"] = False
    export_payload["posts_payment"] = False

    fp = fingerprint_payload(
        {
            "employees": export_payload.get("employees"),
            "compensation_contracts": export_payload.get("compensation_contracts"),
            "shifts": export_payload.get("shifts"),
            "attendance": export_payload.get("attendance"),
            "leave_classifications": export_payload.get("leave_classifications"),
            "period": export_payload.get("period"),
        }
    )
    # Detect changed input vs latest exported fingerprint for same period
    period_id = str((period or {}).get("period_id") or "") or None
    cur.execute(
        """
        SELECT export_run_id::text, input_fingerprint, status
        FROM payroll_adapter_export_runs
        WHERE company_code=%s AND status='exported'
          AND (
            (%s::uuid IS NOT NULL AND period_id=%s::uuid)
            OR (period_start=%s::date AND period_end=%s::date)
          )
        ORDER BY created_at DESC LIMIT 1
        """,
        (
            company,
            period_id,
            period_id,
            str((period or {}).get("period_start") or "")[:10] or None,
            str((period or {}).get("period_end") or "")[:10] or None,
        ),
    )
    prior = _row(cur)
    prior_fp = str((prior or {}).get("input_fingerprint") or "")
    fingerprint_changed = bool(prior_fp and prior_fp != fp)

    csv_text = encode_export_csv(export_payload)
    artifact_sha = _sha256_text(csv_text)
    ext_id = str(external_run_id or f"EXT-EXP-{uuid.uuid4().hex[:12]}").strip()

    # Idempotent clean re-export of identical fingerprint
    if prior and prior_fp == fp:
        cur.execute(
            "SELECT * FROM payroll_adapter_export_runs WHERE export_run_id=%s",
            (prior["export_run_id"],),
        )
        existing = _row(cur) or {}
        return {
            "ok": True,
            "idempotent": True,
            "export_run": _json_safe(existing),
            "input_fingerprint": fp,
            "fingerprint_changed": False,
            "artifact_csv": existing.get("artifact_csv") or csv_text,
            **honesty_payload(),
        }

    if fingerprint_changed and prior:
        cur.execute(
            """
            UPDATE payroll_adapter_export_runs
            SET status='superseded', updated_at=now(), row_version=row_version+1
            WHERE export_run_id=%s AND status='exported'
            """,
            (prior["export_run_id"],),
        )

    cur.execute(
        """
        INSERT INTO payroll_adapter_export_runs (
          company_code, period_id, period_start, period_end, adapter_kind, schema_version,
          status, input_fingerprint, payload, artifact_csv, artifact_sha256, external_run_id,
          money_authority, payment_processing, posts_payment, created_by_phone, decision_note, metadata
        ) VALUES (
          %s,%s,%s,%s,%s,%s,'exported',%s,%s::jsonb,%s,%s,%s,
          'external','disabled',false,%s,%s,%s::jsonb
        )
        RETURNING *
        """,
        (
            company,
            period_id,
            str((period or {}).get("period_start") or "")[:10] or None,
            str((period or {}).get("period_end") or "")[:10] or None,
            ADAPTER_KIND,
            pyw1.PAYROLL_INPUT_EXPORT_SCHEMA,
            fp,
            json.dumps(_json_safe(export_payload)),
            csv_text,
            artifact_sha,
            ext_id,
            digits_phone(actor_phone),
            str(reason).strip(),
            json.dumps(_json_safe({"fingerprint_changed_from": prior_fp or None})),
        ),
    )
    run = _row(cur) or {}
    _event(
        cur,
        company_code=company,
        event_type="export_created",
        export_run_id=str(run.get("export_run_id")),
        payload={"fingerprint": fp, "fingerprint_changed": fingerprint_changed, "external_run_id": ext_id},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "idempotent": False,
        "export_run": _json_safe(run),
        "input_fingerprint": fp,
        "fingerprint_changed": fingerprint_changed,
        "prior_fingerprint": prior_fp or None,
        "artifact_csv": csv_text,
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- import


def import_external_results(
    cur: Any,
    *,
    company_code: str,
    export_run_id: str,
    csv_text: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    expected_input_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Import synthetic CSV results against an export run; quarantine malformed/unmatched."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2a_schema(cur)
    company = (company_code or "").upper()

    cur.execute(
        "SELECT * FROM payroll_adapter_export_runs WHERE company_code=%s AND export_run_id=%s",
        (company, export_run_id),
    )
    export_run = _row(cur)
    if not export_run:
        return {"ok": False, "error": "export_run_not_found"}
    if str(export_run.get("status")) == "rolled_back":
        return {"ok": False, "error": "export_run_rolled_back"}

    # Changed input fingerprint detection (caller may pass current fingerprint)
    if expected_input_fingerprint and expected_input_fingerprint != str(export_run.get("input_fingerprint") or ""):
        q = _quarantine(
            cur,
            company_code=company,
            source_kind="fingerprint_mismatch",
            reason="import_blocked_input_fingerprint_changed",
            export_run_id=export_run_id,
            artifact_excerpt=str(csv_text)[:500],
            payload={
                "export_fingerprint": export_run.get("input_fingerprint"),
                "expected_input_fingerprint": expected_input_fingerprint,
            },
            actor_phone=actor_phone,
        )
        return {
            "ok": False,
            "error": "input_fingerprint_changed",
            "quarantine": _json_safe(q),
            **honesty_payload(),
        }

    decoded = decode_import_csv(csv_text)
    if not decoded.get("ok"):
        q = _quarantine(
            cur,
            company_code=company,
            source_kind="malformed_import" if decoded.get("error") == "malformed_csv" else "schema_reject",
            reason=str(decoded.get("error") or "import_reject"),
            export_run_id=export_run_id,
            artifact_excerpt=str(csv_text)[:500],
            payload=decoded,
            actor_phone=actor_phone,
        )
        return {
            "ok": False,
            "error": decoded.get("error") or "import_reject",
            "detail": decoded.get("detail"),
            "quarantine": _json_safe(q),
            **honesty_payload(),
        }

    result_payload = decoded["payload"]
    external_run_id = str(result_payload.get("external_run_id") or "")
    result_fp = fingerprint_payload(result_payload)

    # Idempotent replay by external_run_id
    cur.execute(
        """
        SELECT * FROM payroll_adapter_import_runs
        WHERE company_code=%s AND external_run_id=%s
          AND status IN ('imported','idempotent_replay','partial')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, external_run_id),
    )
    prior_import = _row(cur)
    if prior_import and str(prior_import.get("result_fingerprint")) == result_fp:
        return {
            "ok": True,
            "idempotent": True,
            "import_run": _json_safe(prior_import),
            "message": "duplicate_external_run_replayed",
            **honesty_payload(),
        }

    export_payload = export_run.get("payload") or {}
    if isinstance(export_payload, str):
        export_payload = json.loads(export_payload)
    expected_employees = {
        str(e.get("employee_key") or "")
        for e in (export_payload.get("employees") or [])
        if e.get("employee_key")
    }
    if not expected_employees:
        expected_employees = {
            str(c.get("employee_key") or "")
            for c in (export_payload.get("compensation_contracts") or [])
            if c.get("employee_key")
        }
    expected_components: set[tuple[str, str]] = set()
    for c in export_payload.get("compensation_contracts") or []:
        ek = str(c.get("employee_key") or "")
        for comp in c.get("components") or []:
            expected_components.add((ek, str(comp.get("code") or "")))

    matched = 0
    unmatched = 0
    quarantined = 0
    line_rows: list[dict[str, Any]] = []
    for line in result_payload.get("lines") or []:
        ek = str(line.get("employee_key") or "")
        code = str(line.get("component_code") or "")
        if not ek or ek not in expected_employees:
            status = "unmatched_employee"
            unmatched += 1
            quarantined += 1
        elif expected_components and (ek, code) not in expected_components and code:
            status = "unmatched_component"
            unmatched += 1
        else:
            status = "matched"
            matched += 1
        line_rows.append({**line, "line_status": status})

    status = "imported"
    if quarantined and matched:
        status = "partial"
    elif quarantined and not matched:
        status = "quarantined"

    cur.execute(
        """
        INSERT INTO payroll_adapter_import_runs (
          company_code, export_run_id, adapter_kind, schema_version, status, external_run_id,
          result_fingerprint, payload, artifact_csv, artifact_sha256,
          money_authority, payment_processing, posts_payment, mirror_only,
          matched_count, unmatched_count, quarantined_count,
          created_by_phone, decision_note, metadata
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          %s,%s::jsonb,%s,%s,
          'external','disabled',false,true,
          %s,%s,%s,
          %s,%s,%s::jsonb
        )
        RETURNING *
        """,
        (
            company,
            export_run_id,
            ADAPTER_KIND,
            pyw1.PAYROLL_RESULT_IMPORT_SCHEMA,
            status,
            external_run_id,
            result_fp,
            json.dumps(_json_safe(result_payload)),
            csv_text,
            _sha256_text(csv_text),
            matched,
            unmatched,
            quarantined,
            digits_phone(actor_phone),
            str(reason).strip(),
            json.dumps(_json_safe({"prior_import_id": (prior_import or {}).get("import_run_id")})),
        ),
    )
    import_run = _row(cur) or {}
    iid = str(import_run.get("import_run_id"))

    for line in line_rows:
        cur.execute(
            """
            INSERT INTO payroll_adapter_import_lines (
              import_run_id, company_code, employee_key, component_code, line_status,
              opaque_amount, currency, match_notes, raw_row
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                iid,
                company,
                line.get("employee_key"),
                line.get("component_code"),
                line.get("line_status"),
                line.get("opaque_amount"),
                line.get("currency") or "KWD",
                line.get("line_status"),
                json.dumps(_json_safe(line.get("raw") or line)),
            ),
        )
        if line.get("line_status") == "unmatched_employee":
            _quarantine(
                cur,
                company_code=company,
                source_kind="unmatched_employee",
                reason=f"unmatched_employee:{line.get('employee_key')}",
                export_run_id=export_run_id,
                import_run_id=iid,
                payload=line,
                actor_phone=actor_phone,
            )

    _event(
        cur,
        company_code=company,
        event_type="import_created",
        export_run_id=export_run_id,
        import_run_id=iid,
        payload={"status": status, "matched": matched, "unmatched": unmatched, "external_run_id": external_run_id},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "idempotent": False,
        "import_run": _json_safe(import_run),
        "matched_count": matched,
        "unmatched_count": unmatched,
        "quarantined_count": quarantined,
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- reconcile


def reconcile_export_import(
    cur: Any,
    *,
    company_code: str,
    export_run_id: str,
    import_run_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2a_schema(cur)
    company = (company_code or "").upper()

    cur.execute(
        "SELECT * FROM payroll_adapter_export_runs WHERE company_code=%s AND export_run_id=%s",
        (company, export_run_id),
    )
    export_run = _row(cur)
    cur.execute(
        "SELECT * FROM payroll_adapter_import_runs WHERE company_code=%s AND import_run_id=%s",
        (company, import_run_id),
    )
    import_run = _row(cur)
    if not export_run or not import_run:
        return {"ok": False, "error": "export_or_import_not_found"}
    if str(import_run.get("export_run_id")) != str(export_run_id):
        return {"ok": False, "error": "import_export_mismatch"}

    export_payload = export_run.get("payload") or {}
    if isinstance(export_payload, str):
        export_payload = json.loads(export_payload)

    expected_emps = {
        str(e.get("employee_key") or "")
        for e in (export_payload.get("employees") or [])
        if e.get("employee_key")
    }
    if not expected_emps:
        expected_emps = {
            str(c.get("employee_key") or "")
            for c in (export_payload.get("compensation_contracts") or [])
            if c.get("employee_key")
        }
    expected_comp_amounts: dict[tuple[str, str], float] = {}
    for c in export_payload.get("compensation_contracts") or []:
        ek = str(c.get("employee_key") or "")
        for comp in c.get("components") or []:
            expected_comp_amounts[(ek, str(comp.get("code") or ""))] = float(comp.get("amount") or 0)

    cur.execute(
        "SELECT * FROM payroll_adapter_import_lines WHERE import_run_id=%s",
        (import_run_id,),
    )
    lines = _rows(cur)
    imported_emps = {str(l.get("employee_key") or "") for l in lines if l.get("employee_key")}
    matched_emps = expected_emps & imported_emps
    missing = sorted(expected_emps - imported_emps)
    extra = sorted(imported_emps - expected_emps)

    component_diffs: list[dict[str, Any]] = []
    totals_export = sum(expected_comp_amounts.values())
    totals_import = 0.0
    for line in lines:
        if str(line.get("line_status")) != "matched":
            continue
        ek = str(line.get("employee_key") or "")
        code = str(line.get("component_code") or "")
        amt = float(line.get("opaque_amount") or 0)
        totals_import += amt
        exp = expected_comp_amounts.get((ek, code))
        if exp is not None and abs(exp - amt) > 0.0005:
            component_diffs.append(
                {
                    "employee_key": ek,
                    "component_code": code,
                    "export_amount": exp,
                    "import_opaque_amount": amt,
                    "delta": round(amt - exp, 3),
                }
            )

    differences: list[dict[str, Any]] = []
    if missing:
        differences.append({"kind": "employees_missing", "employees": missing})
    if extra:
        differences.append({"kind": "employees_extra", "employees": extra})
    if component_diffs:
        differences.append({"kind": "component_amount_diffs", "items": component_diffs})

    status = "ok" if not differences else "differences"
    totals_delta = round(totals_import - totals_export, 3)

    cur.execute(
        """
        INSERT INTO payroll_adapter_reconciliations (
          company_code, export_run_id, import_run_id, status,
          employees_expected, employees_matched, employees_missing, employees_extra,
          components_diff, totals_export, totals_import, totals_delta, differences,
          money_authority, payment_processing, created_by_phone, decision_note
        ) VALUES (
          %s,%s,%s,%s,
          %s,%s,%s,%s,
          %s::jsonb,%s,%s,%s,%s::jsonb,
          'external','disabled',%s,%s
        )
        ON CONFLICT (export_run_id, import_run_id) DO UPDATE SET
          status=EXCLUDED.status,
          employees_expected=EXCLUDED.employees_expected,
          employees_matched=EXCLUDED.employees_matched,
          employees_missing=EXCLUDED.employees_missing,
          employees_extra=EXCLUDED.employees_extra,
          components_diff=EXCLUDED.components_diff,
          totals_export=EXCLUDED.totals_export,
          totals_import=EXCLUDED.totals_import,
          totals_delta=EXCLUDED.totals_delta,
          differences=EXCLUDED.differences,
          decision_note=EXCLUDED.decision_note
        RETURNING *
        """,
        (
            company,
            export_run_id,
            import_run_id,
            status,
            len(expected_emps),
            len(matched_emps),
            len(missing),
            len(extra),
            json.dumps(_json_safe(component_diffs)),
            totals_export,
            totals_import,
            totals_delta,
            json.dumps(_json_safe(differences)),
            digits_phone(actor_phone),
            str(reason).strip(),
        ),
    )
    recon = _row(cur) or {}
    _event(
        cur,
        company_code=company,
        event_type="reconciled",
        export_run_id=export_run_id,
        import_run_id=import_run_id,
        payload={"status": status, "differences": differences},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "reconciliation": _json_safe(recon),
        "has_differences": status != "ok",
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- rollback


def rollback_export_run(
    cur: Any,
    *,
    company_code: str,
    export_run_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    expected_row_version: Any = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2a_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        "SELECT * FROM payroll_adapter_export_runs WHERE company_code=%s AND export_run_id=%s",
        (company, export_run_id),
    )
    run = _row(cur)
    if not run:
        return {"ok": False, "error": "export_run_not_found"}
    conc = pyw1.require_concurrency(expected_row_version=expected_row_version, actual_row_version=run.get("row_version"))
    if conc:
        return conc
    cur.execute(
        """
        UPDATE payroll_adapter_export_runs
        SET status='rolled_back', decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND export_run_id=%s AND status IN ('exported','superseded') AND row_version=%s
        RETURNING *
        """,
        (str(reason).strip(), company, export_run_id, int(expected_row_version)),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    # Soft-roll back linked imports (do not hard-delete quarantine rows)
    cur.execute(
        """
        UPDATE payroll_adapter_import_runs
        SET status='rolled_back', updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND export_run_id=%s AND status <> 'rolled_back'
        """,
        (company, export_run_id),
    )
    _event(
        cur,
        company_code=company,
        event_type="export_rolled_back",
        export_run_id=export_run_id,
        payload={"reason": reason},
        actor_phone=actor_phone,
    )
    return {"ok": True, "export_run": _json_safe(updated), **honesty_payload()}


def get_export_run(cur: Any, *, company_code: str, export_run_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave2a_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_adapter_export_runs WHERE company_code=%s AND export_run_id=%s",
        ((company_code or "").upper(), export_run_id),
    )
    return _row(cur)


def get_import_run(cur: Any, *, company_code: str, import_run_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave2a_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_adapter_import_runs WHERE company_code=%s AND import_run_id=%s",
        ((company_code or "").upper(), import_run_id),
    )
    return _row(cur)
