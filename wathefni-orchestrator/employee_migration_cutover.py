"""Migration & Sync P4 — opening balances + current-state cutover.

Authoritative opening/current values with provenance. Never fabricates historical
leave requests, attendance, or payroll-effective money. Reuses batch/row model.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import schema_contract

CONTRACT = "employee_migration_sync_p4_cutover"
CONTRACT_VERSION = "4.0.0"

AUTHORITY_IMPORTED = "imported"
AUTHORITY_VERIFIED = "verified"
AUTHORITY_WATHEFNI = "wathefni_authoritative"

DISP_WILL_APPLY = "will_apply"
DISP_UNCHANGED = "unchanged"
DISP_NEEDS_REVIEW = "needs_review"
DISP_NOT_SUPPLIED = "not_supplied"

CUTOVER_CANONICAL_FIELDS: dict[str, dict[str, Any]] = {
    "cutover_date": {
        "domain": "cutover",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["opening_balance_as_of", "as_of_date", "balance_as_of", "cutover_as_of"],
    },
    "leave_type": {
        "domain": "leave",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["leave_balance_type", "leave_category"],
    },
    "leave_opening_balance": {
        "domain": "leave",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["leave_balance", "current_leave_balance", "annual_leave_balance"],
    },
    "leave_entitlement_days": {
        "domain": "leave",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["leave_entitlement", "annual_leave_entitlement"],
    },
    "salary_basic_monthly": {
        "domain": "payroll",
        "authority": "payroll_draft_only",
        "sensitivity": "bank",
        "aliases": ["basic_salary", "salary", "monthly_salary", "basic_pay"],
    },
    "salary_currency": {
        "domain": "payroll",
        "authority": "payroll_draft_only",
        "sensitivity": "public",
        "aliases": ["pay_currency", "currency"],
    },
    "current_assignment_title": {
        "domain": "assignment",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["current_job_title", "assignment_title"],
    },
    "current_assignment_department": {
        "domain": "assignment",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["current_department", "assignment_department"],
    },
    "shift_template_code": {
        "domain": "shifts",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["current_shift_template", "shift_code", "work_pattern"],
    },
    "compliance_current_state": {
        "domain": "compliance",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["compliance_state", "current_compliance_status"],
    },
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_migration_opening_balances (
  balance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  domain text NOT NULL,
  field_key text NOT NULL,
  value_text text,
  value_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  display_masked text,
  cutover_date date,
  authority text NOT NULL DEFAULT 'imported',
  source_system text,
  external_employee_id text,
  batch_id uuid NOT NULL,
  row_id uuid,
  native_superseded boolean NOT NULL DEFAULT false,
  applied_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, employee_key, domain, field_key, batch_id),
  CHECK (authority = ANY (ARRAY['imported','verified','wathefni_authoritative'])),
  CHECK (domain = ANY (ARRAY['leave','payroll','assignment','shifts','compliance','cutover','other']))
);
CREATE INDEX IF NOT EXISTS idx_emp_mig_opening_emp
  ON employee_migration_opening_balances(company_code, employee_key);
CREATE INDEX IF NOT EXISTS idx_emp_mig_opening_batch
  ON employee_migration_opening_balances(batch_id);
"""

_SCHEMA_READY = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "no_fake_historical_transactions": True,
        "no_leave_request_fabrication": True,
        "no_attendance_fabrication": True,
        "payroll_draft_only": True,
        "never_payroll_effective_on_import": True,
        "compliance_imported_unverified": True,
        "missing_means_not_supplied": True,
        "native_wathefni_wins": True,
        "canonical_fields": sorted(CUTOVER_CANONICAL_FIELDS.keys()),
    }


def ensure_cutover_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=["employee_migration_opening_balances"],
        module="employee_migration_cutover",
        lock_id=None,
    )
    _SCHEMA_READY = True


def _parse_decimal(raw: Any) -> Decimal | None:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def mask_salary(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return "••••"


def resolve_cutover_preview(
    canonical: dict[str, str],
    *,
    existing: dict[str, Any] | None = None,
    source_system: str | None = None,
) -> list[dict[str, Any]]:
    """Build preview lines for opening/current-state fields. Missing → not_supplied."""
    existing = existing or {}
    cutover = _parse_date(canonical.get("cutover_date"))
    cutover_s = cutover.isoformat() if cutover else None
    lines: list[dict[str, Any]] = []

    def add(
        *,
        domain: str,
        field_key: str,
        label: str,
        import_value: Any,
        existing_value: Any,
        masked: bool = False,
        disposition: str | None = None,
        note: str | None = None,
        force_include: bool = False,
    ) -> None:
        supplied = import_value is not None and str(import_value).strip() != ""
        if not supplied and not force_include:
            return
        if not supplied:
            disp = DISP_NOT_SUPPLIED
            show_import = "Not supplied"
        else:
            if disposition:
                disp = disposition
            elif existing_value is not None and str(existing_value).strip() != "" and str(existing_value) != str(import_value):
                disp = DISP_NEEDS_REVIEW
            elif existing_value is not None and str(existing_value).strip() != "" and str(existing_value) == str(import_value):
                disp = DISP_UNCHANGED
            else:
                disp = DISP_WILL_APPLY
            show_import = mask_salary(import_value) if masked else str(import_value)
        show_existing = (
            "Not supplied"
            if existing_value is None or str(existing_value).strip() == ""
            else (mask_salary(existing_value) if masked else str(existing_value))
        )
        lines.append(
            {
                "domain": domain,
                "field_key": field_key,
                "preview_label": label,
                "import_value": show_import,
                "existing_value": show_existing,
                "cutover_date": cutover_s,
                "source": source_system,
                "disposition": disp,
                "masked": masked,
                "note": note,
            }
        )

    leave_type = str(canonical.get("leave_type") or "annual").strip() or "annual"
    if "leave_opening_balance" in canonical:
        add(
            domain="leave",
            field_key="leave_opening_balance",
            label=f"Leave opening balance ({leave_type})",
            import_value=canonical.get("leave_opening_balance"),
            existing_value=existing.get("leave_opening_balance"),
            note="Imported as opening adjustment — no leave requests fabricated",
            force_include=True,
        )
    if str(canonical.get("leave_entitlement_days") or "").strip():
        add(
            domain="leave",
            field_key="leave_entitlement_days",
            label=f"Leave entitlement ({leave_type})",
            import_value=canonical.get("leave_entitlement_days"),
            existing_value=existing.get("leave_entitlement_days"),
        )

    if "salary_basic_monthly" in canonical:
        add(
            domain="payroll",
            field_key="salary_basic_monthly",
            label="Basic salary (monthly)",
            import_value=canonical.get("salary_basic_monthly"),
            existing_value=existing.get("salary_basic_monthly"),
            masked=True,
            note="Draft/imported only — never payroll-effective on import",
            force_include=True,
        )

    if "current_assignment_title" in canonical:
        add(
            domain="assignment",
            field_key="current_assignment_title",
            label="Current assignment title",
            import_value=canonical.get("current_assignment_title"),
            existing_value=existing.get("current_assignment_title"),
            note="Current org slice only — no attendance fabricated",
            force_include=True,
        )
    if "current_assignment_department" in canonical:
        add(
            domain="assignment",
            field_key="current_assignment_department",
            label="Current assignment department",
            import_value=canonical.get("current_assignment_department"),
            existing_value=existing.get("current_assignment_department"),
            force_include=True,
        )

    if "shift_template_code" in canonical:
        add(
            domain="shifts",
            field_key="shift_template_code",
            label="Shift template (planning)",
            import_value=canonical.get("shift_template_code"),
            existing_value=existing.get("shift_template_code"),
            note="Planning metadata only — no shift events created",
            force_include=True,
        )

    if any(
        k in canonical
        for k in ("compliance_current_state", "compliance_expiry", "compliance_status", "compliance_doc_type")
    ):
        state = canonical.get("compliance_current_state") or canonical.get("compliance_status")
        expiry = canonical.get("compliance_expiry")
        parts = []
        if canonical.get("compliance_doc_type"):
            parts.append(str(canonical["compliance_doc_type"]))
        if state:
            parts.append(str(state))
        if expiry:
            parts.append(f"exp {expiry}")
        import_blob = " · ".join(parts) if parts else None
        add(
            domain="compliance",
            field_key="compliance_current_state",
            label="Compliance current state",
            import_value=import_blob,
            existing_value=existing.get("compliance_current_state"),
            note="Imported/unverified — no campaign auto-seed",
            force_include=True,
        )

    return lines


def load_existing_cutover_snapshot(cur: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        cur.execute("SAVEPOINT p4_leave_snap")
        cur.execute(
            """
            SELECT leave_type, current_balance, entitlement_days
            FROM leave_balances
            WHERE company_code=%s AND employee_key=%s
            ORDER BY as_of DESC NULLS LAST
            LIMIT 1
            """,
            (company, employee_key),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT p4_leave_snap")
        if row:
            out["leave_opening_balance"] = str(row.get("current_balance"))
            out["leave_entitlement_days"] = str(row.get("entitlement_days"))
            out["leave_type"] = row.get("leave_type")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_leave_snap")
        except Exception:
            pass
    try:
        cur.execute("SAVEPOINT p4_pay_snap")
        cur.execute(
            """
            SELECT c.status, comp.amount
            FROM payroll_compensation_contracts c
            LEFT JOIN payroll_compensation_components comp
              ON comp.contract_id=c.contract_id AND comp.is_basic IS TRUE
            WHERE c.company_code=%s AND c.employee_key=%s
            ORDER BY CASE c.status WHEN 'approved' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                     c.created_at DESC NULLS LAST
            LIMIT 1
            """,
            (company, employee_key),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT p4_pay_snap")
        if row and row.get("amount") is not None:
            out["salary_basic_monthly"] = str(row.get("amount"))
            out["salary_contract_status"] = row.get("status")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_pay_snap")
        except Exception:
            pass
    try:
        cur.execute("SAVEPOINT p4_asg_snap")
        cur.execute(
            """
            SELECT position_title, change_type
            FROM employee_org_assignment_history
            WHERE company_code=%s AND employee_key=%s AND effective_to IS NULL
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (company, employee_key),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT p4_asg_snap")
        if row:
            out["current_assignment_title"] = row.get("position_title")
            out["assignment_change_type"] = row.get("change_type")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_asg_snap")
        except Exception:
            pass
    try:
        cur.execute(
            "SELECT position_title, raw_json FROM employees WHERE company_code=%s AND employee_key=%s",
            (company, employee_key),
        )
        row = cur.fetchone() or {}
        if row.get("position_title") and "current_assignment_title" not in out:
            out["current_assignment_title"] = row.get("position_title")
        raw = row.get("raw_json") or {}
        if isinstance(raw, str):
            import json as _json
            raw = _json.loads(raw)
        dept = (raw or {}).get("department") or (raw or {}).get("assignment_department")
        if dept:
            out["current_assignment_department"] = dept
    except Exception:
        pass
    return out


def _upsert_opening_row(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    domain: str,
    field_key: str,
    value_text: str | None,
    value_json: dict[str, Any],
    display_masked: str | None,
    cutover_date: date | None,
    source_system: str | None,
    external_employee_id: str | None,
    batch_id: str,
    row_id: str | None,
    applied_ref: dict[str, Any],
    actor: str | None,
) -> dict[str, Any]:
    ensure_cutover_schema(cur)
    cur.execute(
        """
        SELECT balance_id, authority, native_superseded, batch_id
        FROM employee_migration_opening_balances
        WHERE company_code=%s AND employee_key=%s AND domain=%s AND field_key=%s
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (company, employee_key, domain, field_key),
    )
    prior = cur.fetchone()
    if prior and (
        prior.get("native_superseded")
        or str(prior.get("authority") or "") == AUTHORITY_WATHEFNI
    ):
        if str(prior.get("batch_id")) != str(batch_id):
            return {
                "ok": False,
                "skipped": True,
                "reason": "native_or_authoritative_wins",
                "prior": _jsonable(dict(prior)),
            }

    provenance = {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "imported_at": _now().isoformat(),
        "actor": actor,
        "batch_id": batch_id,
        "row_id": row_id,
    }
    cur.execute(
        """
        INSERT INTO employee_migration_opening_balances (
          company_code, employee_key, domain, field_key, value_text, value_json,
          display_masked, cutover_date, authority, source_system, external_employee_id,
          batch_id, row_id, native_superseded, applied_ref, provenance, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s::jsonb,%s,%s,'imported',%s,%s,%s,%s,false,%s::jsonb,%s::jsonb,now()
        )
        ON CONFLICT (company_code, employee_key, domain, field_key, batch_id) DO UPDATE SET
          value_text=EXCLUDED.value_text,
          value_json=EXCLUDED.value_json,
          display_masked=EXCLUDED.display_masked,
          cutover_date=EXCLUDED.cutover_date,
          authority='imported',
          source_system=EXCLUDED.source_system,
          external_employee_id=EXCLUDED.external_employee_id,
          row_id=EXCLUDED.row_id,
          applied_ref=EXCLUDED.applied_ref,
          provenance=EXCLUDED.provenance,
          updated_at=now()
        WHERE employee_migration_opening_balances.native_superseded IS NOT TRUE
        RETURNING *
        """,
        (
            company,
            employee_key,
            domain,
            field_key,
            value_text,
            json.dumps(value_json),
            display_masked,
            cutover_date,
            source_system,
            external_employee_id,
            batch_id,
            row_id,
            json.dumps(applied_ref),
            json.dumps(provenance),
        ),
    )
    row = cur.fetchone()
    return {"ok": True, "row": _jsonable(dict(row) if row else {})}


def _apply_leave_opening(
    legacy: Any,
    cur: Any,
    *,
    company: str,
    employee_key: str,
    leave_type: str,
    days: Decimal,
    entitlement: Decimal | None,
    cutover_date: date | None,
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    reason_tag = f"migration_opening:{batch_id}:{leave_type}"
    try:
        cur.execute("SAVEPOINT p4_leave_native")
        cur.execute(
            """
            SELECT count(*) AS c FROM leave_ledger
            WHERE company_code=%s AND employee_key=%s AND leave_type=%s
              AND coalesce(reason,'') NOT LIKE 'migration_opening:%%'
              AND entry_kind IN ('consume','accrual','reversal')
            """,
            (company, employee_key, leave_type),
        )
        native_n = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("RELEASE SAVEPOINT p4_leave_native")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_leave_native")
        except Exception:
            pass
        native_n = 0

    if native_n > 0:
        cur.execute(
            """
            UPDATE employee_migration_opening_balances
            SET native_superseded=true, updated_at=now(),
                provenance = provenance || %s::jsonb
            WHERE company_code=%s AND employee_key=%s AND domain='leave'
              AND field_key='leave_opening_balance'
            """,
            (json.dumps({"superseded_at": _now().isoformat(), "by": "native_leave_activity"}), company, employee_key),
        )
        return {"ok": False, "skipped": True, "reason": "native_leave_activity_present", "needs_review": True}

    cur.execute(
        "DELETE FROM leave_ledger WHERE company_code=%s AND employee_key=%s AND reason=%s",
        (company, employee_key, reason_tag),
    )
    year = (cutover_date or date.today()).year
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period,
          leave_id, observe_only, actor_phone, reason, tier_breakdown
        ) VALUES (%s,%s,%s,'adjustment',%s,%s,NULL,true,%s,%s,%s::jsonb)
        RETURNING entry_id
        """,
        (
            company,
            employee_key,
            leave_type,
            str(days),
            str(year),
            actor,
            reason_tag,
            json.dumps(
                {
                    "source": "migration_import",
                    "batch_id": batch_id,
                    "row_id": row_id,
                    "cutover_date": cutover_date.isoformat() if cutover_date else None,
                    "fabricated_requests": False,
                }
            ),
        ),
    )
    entry = cur.fetchone() or {}
    entry_id = str(entry.get("entry_id") or "")
    try:
        legacy.recompute_leave_balance(
            cur,
            company_code=company,
            employee_key=employee_key,
            leave_type=leave_type,
            period_year=year,
            entitlement_days=entitlement,
        )
    except Exception as exc:
        return {"ok": False, "error": f"leave_recompute_failed:{exc}"[:200], "entry_id": entry_id}

    return _upsert_opening_row(
        cur,
        company=company,
        employee_key=employee_key,
        domain="leave",
        field_key="leave_opening_balance",
        value_text=str(days),
        value_json={
            "leave_type": leave_type,
            "days": str(days),
            "entitlement": str(entitlement) if entitlement is not None else None,
        },
        display_masked=str(days),
        cutover_date=cutover_date,
        source_system=source_system,
        external_employee_id=external_employee_id,
        batch_id=batch_id,
        row_id=row_id,
        applied_ref={"leave_ledger_entry_id": entry_id, "period_year": year},
        actor=actor,
    )


def _apply_payroll_opening(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    amount: Decimal,
    currency: str,
    cutover_date: date | None,
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    try:
        cur.execute("SAVEPOINT p4_pay_guard")
        cur.execute(
            """
            SELECT contract_id, status FROM payroll_compensation_contracts
            WHERE company_code=%s AND employee_key=%s AND status='approved'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, employee_key),
        )
        approved = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT p4_pay_guard")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_pay_guard")
        except Exception:
            pass
        approved = None
    if approved:
        return {
            "ok": False,
            "skipped": True,
            "reason": "approved_payroll_contract_present",
            "needs_review": True,
        }

    contract_id = None
    draft_error = None
    try:
        import payroll_authority_wave1 as paw

        result = paw.create_contract_draft(
            cur,
            company_code=company,
            employee_key=employee_key,
            effective_from=cutover_date or date.today(),
            currency=currency or "KWD",
            components=[
                {
                    "component_kind": "earning",
                    "code": "basic",
                    "label_en": "Basic salary",
                    "amount": float(amount),
                    "amount_unit": "monthly",
                    "is_basic": True,
                    "sort_order": 0,
                    "metadata": {"source": "migration_import", "batch_id": batch_id},
                }
            ],
            source_kind="import",
            actor_phone=None,
            reason=f"Migration opening balance batch {batch_id}",
            metadata={
                "source": "migration_import",
                "batch_id": batch_id,
                "row_id": row_id,
                "authority": AUTHORITY_IMPORTED,
                "payroll_effective": False,
            },
        )
        if result.get("ok"):
            contract_id = str((result.get("contract") or {}).get("contract_id") or "")
        else:
            draft_error = str(result.get("error") or "draft_refused")
    except Exception as exc:
        draft_error = str(exc)[:160]

    staged = _upsert_opening_row(
        cur,
        company=company,
        employee_key=employee_key,
        domain="payroll",
        field_key="salary_basic_monthly",
        value_text=str(amount),
        value_json={
            "amount": str(amount),
            "currency": currency or "KWD",
            "payroll_effective": False,
            "draft_contract_id": contract_id,
            "draft_error": draft_error,
        },
        display_masked=mask_salary(amount),
        cutover_date=cutover_date,
        source_system=source_system,
        external_employee_id=external_employee_id,
        batch_id=batch_id,
        row_id=row_id,
        applied_ref={"draft_contract_id": contract_id, "draft_error": draft_error},
        actor=actor,
    )
    staged["draft_contract_id"] = contract_id
    staged["draft_error"] = draft_error
    staged["payroll_effective"] = False
    return staged


def _apply_assignment_opening(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    title: str | None,
    department: str | None,
    cutover_date: date | None,
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    if not (title or department):
        return {"ok": True, "skipped": True, "reason": "not_supplied"}

    history_id = None
    org_error = None
    try:
        cur.execute("SAVEPOINT p4_asg_apply")
        cur.execute(
            """
            SELECT history_id, position_title, change_type, batch_id
            FROM employee_org_assignment_history
            WHERE company_code=%s AND employee_key=%s AND effective_to IS NULL
            ORDER BY effective_from DESC LIMIT 1
            """,
            (company, employee_key),
        )
        open_row = cur.fetchone()
        if open_row and str(open_row.get("change_type") or "") not in {"migration", "initial", ""}:
            existing_title = str(open_row.get("position_title") or "").strip()
            if title and existing_title and existing_title != title:
                cur.execute("RELEASE SAVEPOINT p4_asg_apply")
                return {"ok": False, "skipped": True, "reason": "native_assignment_conflict", "needs_review": True}
        effective = cutover_date or date.today()
        cur.execute(
            """
            UPDATE employee_org_assignment_history
            SET effective_to=%s
            WHERE company_code=%s AND employee_key=%s AND batch_id=%s AND effective_to IS NULL
            """,
            (effective, company, employee_key, batch_id),
        )
        cur.execute(
            """
            INSERT INTO employee_org_assignment_history (
              company_code, employee_key, position_title,
              effective_from, change_type, reason, actor_user_id, batch_id, provenance
            ) VALUES (%s,%s,%s,%s,'migration',%s,%s,%s,%s::jsonb)
            RETURNING history_id
            """,
            (
                company,
                employee_key,
                title,
                effective,
                f"Migration current assignment batch {batch_id}",
                actor,
                batch_id,
                json.dumps(
                    {
                        "source": "migration_import",
                        "department": department,
                        "no_attendance": True,
                        "row_id": row_id,
                    }
                ),
            ),
        )
        history_id = str((cur.fetchone() or {}).get("history_id") or "")
        cur.execute("RELEASE SAVEPOINT p4_asg_apply")
    except Exception as exc:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p4_asg_apply")
        except Exception:
            pass
        org_error = str(exc)[:160]

    if title:
        cur.execute(
            """
            UPDATE employees SET position_title=%s, updated_at=now()
            WHERE company_code=%s AND employee_key=%s
              AND coalesce(nullif(trim(position_title),''),'') = ''
            """,
            (title, company, employee_key),
        )
    if department:
        cur.execute(
            """
            UPDATE employees
            SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb, updated_at=now()
            WHERE company_code=%s AND employee_key=%s
              AND coalesce(raw_json->>'department','') = ''
            """,
            (json.dumps({"department": department, "assignment_department_imported": True}), company, employee_key),
        )

    return _upsert_opening_row(
        cur,
        company=company,
        employee_key=employee_key,
        domain="assignment",
        field_key="current_assignment_title" if title else "current_assignment_department",
        value_text=title or department,
        value_json={"title": title, "department": department, "org_error": org_error},
        display_masked=title or department,
        cutover_date=cutover_date,
        source_system=source_system,
        external_employee_id=external_employee_id,
        batch_id=batch_id,
        row_id=row_id,
        applied_ref={"history_id": history_id},
        actor=actor,
    )


def _apply_shift_planning(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    template_code: str,
    cutover_date: date | None,
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    return _upsert_opening_row(
        cur,
        company=company,
        employee_key=employee_key,
        domain="shifts",
        field_key="shift_template_code",
        value_text=template_code,
        value_json={"template_code": template_code, "shift_assignments_created": False},
        display_masked=template_code,
        cutover_date=cutover_date,
        source_system=source_system,
        external_employee_id=external_employee_id,
        batch_id=batch_id,
        row_id=row_id,
        applied_ref={},
        actor=actor,
    )


def _apply_compliance_cutover(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    canonical: dict[str, str],
    cutover_date: date | None,
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    doc_type = str(canonical.get("compliance_doc_type") or "other").strip() or "other"
    status = str(canonical.get("compliance_current_state") or canonical.get("compliance_status") or "").strip() or None
    expiry = str(canonical.get("compliance_expiry") or "").strip() or None
    if not status and not expiry and not canonical.get("compliance_doc_type"):
        return {"ok": True, "skipped": True, "reason": "not_supplied"}

    # Staging evidence row is written by P2 apply_deep; P4 only records opening provenance.
    blob = " · ".join(p for p in [doc_type, status, f"exp {expiry}" if expiry else None] if p)
    return _upsert_opening_row(
        cur,
        company=company,
        employee_key=employee_key,
        domain="compliance",
        field_key="compliance_current_state",
        value_text=blob,
        value_json={
            "doc_type": doc_type,
            "status": status,
            "expiry": expiry,
            "verification_status": "unverified",
        },
        display_masked=blob,
        cutover_date=cutover_date,
        source_system=source_system,
        external_employee_id=external_employee_id,
        batch_id=batch_id,
        row_id=row_id,
        applied_ref={},
        actor=actor,
    )


def apply_cutover_from_canonical(
    legacy: Any,
    cur: Any,
    *,
    company: str,
    employee_key: str,
    canonical: dict[str, str],
    batch_id: str,
    row_id: str | None,
    source_system: str | None,
    external_employee_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    ensure_cutover_schema(cur)
    notes: dict[str, Any] = {"applied": [], "skipped": [], "review": []}
    cutover = _parse_date(canonical.get("cutover_date"))

    leave_raw = canonical.get("leave_opening_balance")
    if str(leave_raw or "").strip():
        days = _parse_decimal(leave_raw)
        if days is None:
            notes["review"].append({"field": "leave_opening_balance", "reason": "Invalid leave balance number"})
        else:
            ent = _parse_decimal(canonical.get("leave_entitlement_days"))
            leave_type = str(canonical.get("leave_type") or "annual").strip() or "annual"
            result = _apply_leave_opening(
                legacy,
                cur,
                company=company,
                employee_key=employee_key,
                leave_type=leave_type,
                days=days,
                entitlement=ent,
                cutover_date=cutover,
                batch_id=batch_id,
                row_id=row_id,
                source_system=source_system,
                external_employee_id=external_employee_id,
                actor=actor,
            )
            if result.get("ok"):
                notes["applied"].append("leave_opening_balance")
            elif result.get("needs_review") or result.get("skipped"):
                notes["skipped"].append(result)
                if result.get("needs_review"):
                    notes["review"].append({"field": "leave_opening_balance", "reason": result.get("reason")})
            else:
                notes["review"].append(
                    {"field": "leave_opening_balance", "reason": result.get("error") or result.get("reason")}
                )
    elif "leave_opening_balance" in canonical:
        notes["skipped"].append({"field": "leave_opening_balance", "reason": "not_supplied"})

    salary_raw = canonical.get("salary_basic_monthly")
    if str(salary_raw or "").strip():
        amount = _parse_decimal(salary_raw)
        if amount is None:
            notes["review"].append({"field": "salary_basic_monthly", "reason": "Invalid salary amount"})
        else:
            result = _apply_payroll_opening(
                cur,
                company=company,
                employee_key=employee_key,
                amount=amount,
                currency=str(canonical.get("salary_currency") or "KWD").strip() or "KWD",
                cutover_date=cutover,
                batch_id=batch_id,
                row_id=row_id,
                source_system=source_system,
                external_employee_id=external_employee_id,
                actor=actor,
            )
            if result.get("ok"):
                notes["applied"].append("salary_basic_monthly")
                if result.get("draft_error"):
                    notes["skipped"].append({"field": "salary_draft", "reason": result.get("draft_error")})
            elif result.get("needs_review") or result.get("skipped"):
                notes["skipped"].append(result)
                if result.get("needs_review"):
                    notes["review"].append({"field": "salary_basic_monthly", "reason": result.get("reason")})
    elif "salary_basic_monthly" in canonical:
        notes["skipped"].append({"field": "salary_basic_monthly", "reason": "not_supplied"})

    title = str(canonical.get("current_assignment_title") or "").strip() or None
    dept = str(canonical.get("current_assignment_department") or "").strip() or None
    if title or dept or "current_assignment_title" in canonical or "current_assignment_department" in canonical:
        if title or dept:
            result = _apply_assignment_opening(
                cur,
                company=company,
                employee_key=employee_key,
                title=title,
                department=dept,
                cutover_date=cutover,
                batch_id=batch_id,
                row_id=row_id,
                source_system=source_system,
                external_employee_id=external_employee_id,
                actor=actor,
            )
            if result.get("ok"):
                notes["applied"].append("current_assignment")
            elif result.get("needs_review"):
                notes["review"].append({"field": "current_assignment", "reason": result.get("reason")})
            else:
                notes["skipped"].append(result)
        else:
            notes["skipped"].append({"field": "current_assignment", "reason": "not_supplied"})

    shift = str(canonical.get("shift_template_code") or "").strip()
    if shift:
        result = _apply_shift_planning(
            cur,
            company=company,
            employee_key=employee_key,
            template_code=shift,
            cutover_date=cutover,
            batch_id=batch_id,
            row_id=row_id,
            source_system=source_system,
            external_employee_id=external_employee_id,
            actor=actor,
        )
        if result.get("ok"):
            notes["applied"].append("shift_template_code")
    elif "shift_template_code" in canonical:
        notes["skipped"].append({"field": "shift_template_code", "reason": "not_supplied"})

    if any(
        k in canonical
        for k in ("compliance_current_state", "compliance_expiry", "compliance_status", "compliance_doc_type")
    ):
        result = _apply_compliance_cutover(
            cur,
            company=company,
            employee_key=employee_key,
            canonical=canonical,
            cutover_date=cutover,
            batch_id=batch_id,
            row_id=row_id,
            source_system=source_system,
            external_employee_id=external_employee_id,
            actor=actor,
        )
        if result.get("ok") and not result.get("skipped"):
            notes["applied"].append("compliance_current_state")
        elif result.get("skipped"):
            notes["skipped"].append(result)

    return notes


def mark_native_superseded(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    domain: str,
    field_key: str,
    reason: str,
) -> None:
    ensure_cutover_schema(cur)
    cur.execute(
        """
        UPDATE employee_migration_opening_balances
        SET native_superseded=true, authority='wathefni_authoritative', updated_at=now(),
            provenance = provenance || %s::jsonb
        WHERE company_code=%s AND employee_key=%s AND domain=%s AND field_key=%s
        """,
        (
            json.dumps({"superseded_at": _now().isoformat(), "by": reason}),
            company,
            employee_key,
            domain,
            field_key,
        ),
    )


def rollback_cutover_for_batch(cur: Any, *, company: str, batch_id: str) -> dict[str, Any]:
    ensure_cutover_schema(cur)
    cur.execute(
        """
        SELECT balance_id, employee_key, domain, field_key, applied_ref, native_superseded, value_json
        FROM employee_migration_opening_balances
        WHERE company_code=%s AND batch_id=%s
        """,
        (company, batch_id),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    leave_deleted = 0
    contracts_deleted = 0
    history_deleted = 0
    preserved = 0
    for row in rows:
        if row.get("native_superseded"):
            preserved += 1
            continue
        ref = row.get("applied_ref") or {}
        if isinstance(ref, str):
            ref = json.loads(ref)
        vj = row.get("value_json") or {}
        if isinstance(vj, str):
            vj = json.loads(vj)
        if row.get("domain") == "leave":
            leave_type = str((vj or {}).get("leave_type") or "annual")
            reason_tag = f"migration_opening:{batch_id}:{leave_type}"
            cur.execute(
                "DELETE FROM leave_ledger WHERE company_code=%s AND employee_key=%s AND reason=%s",
                (company, row["employee_key"], reason_tag),
            )
            leave_deleted += cur.rowcount or 0
            entry_id = ref.get("leave_ledger_entry_id")
            if entry_id:
                cur.execute("DELETE FROM leave_ledger WHERE entry_id=%s", (entry_id,))
                leave_deleted += cur.rowcount or 0
        if row.get("domain") == "payroll":
            cid = ref.get("draft_contract_id")
            if cid:
                cur.execute(
                    """
                    DELETE FROM payroll_compensation_components
                    WHERE contract_id=%s
                      AND EXISTS (
                        SELECT 1 FROM payroll_compensation_contracts
                        WHERE contract_id=%s AND status='draft' AND source_kind='import'
                          AND metadata::text LIKE %s
                      )
                    """,
                    (cid, cid, f"%{batch_id}%"),
                )
                cur.execute(
                    """
                    DELETE FROM payroll_compensation_events
                    WHERE contract_id=%s
                      AND EXISTS (
                        SELECT 1 FROM payroll_compensation_contracts
                        WHERE contract_id=%s AND status='draft' AND source_kind='import'
                          AND metadata::text LIKE %s
                      )
                    """,
                    (cid, cid, f"%{batch_id}%"),
                )
                cur.execute(
                    """
                    DELETE FROM payroll_compensation_contracts
                    WHERE contract_id=%s AND status='draft' AND source_kind='import'
                      AND metadata::text LIKE %s
                    """,
                    (cid, f"%{batch_id}%"),
                )
                contracts_deleted += cur.rowcount or 0
        if row.get("domain") == "assignment":
            hid = ref.get("history_id")
            if hid:
                cur.execute(
                    """
                    DELETE FROM employee_org_assignment_history
                    WHERE history_id=%s AND change_type='migration' AND batch_id=%s
                    """,
                    (hid, batch_id),
                )
                history_deleted += cur.rowcount or 0

    cur.execute(
        """
        DELETE FROM employee_migration_opening_balances
        WHERE company_code=%s AND batch_id=%s AND native_superseded IS NOT TRUE
        """,
        (company, batch_id),
    )
    opening_deleted = cur.rowcount or 0
    return {
        "opening_rows": opening_deleted,
        "leave_ledger": leave_deleted,
        "draft_contracts": contracts_deleted,
        "assignment_history": history_deleted,
        "preserved_superseded": preserved,
    }
