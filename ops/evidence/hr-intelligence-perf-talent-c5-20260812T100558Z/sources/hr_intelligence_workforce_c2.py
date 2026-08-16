#!/usr/bin/env python3
"""Wave 5 C2 — Workforce + Employee Lifecycle Intelligence (company-scoped).

Builds on frozen C1 Registry/evaluator. Commercial key remains `analytics`.
Internal namespace: hr_intelligence_* .

Authority:
  - Canonical workforce population resolver (effective employment truth)
  - Headcount + future starters
  - Hires / exits / turnover / retention / tenure / org-span facts
  - Formula kinds registered into C1 shared evaluator

Does NOT:
  - Publish FTE (remains blocked)
  - Infer exit reasons from free text
  - Mix contingent into employee headcount
  - Second analytics math engine outside C1
  - UI KPI cards (optional thin validation only)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_workforce_c2"
CONTRACT_VERSION = "hr_intelligence_workforce_c2_v1"
PASS_STAMP = "HR_INTELLIGENCE_WORKFORCE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
_ON = {"1", "true", "yes", "on"}

DEFAULT_TENURE_BANDS = [
    {"key": "0_6m", "label_en": "0–6 months", "label_ar": "٠–٦ أشهر", "min_days": 0, "max_days": 182},
    {"key": "6_12m", "label_en": "6–12 months", "label_ar": "٦–١٢ شهراً", "min_days": 183, "max_days": 365},
    {"key": "1_3y", "label_en": "1–3 years", "label_ar": "١–٣ سنوات", "min_days": 366, "max_days": 1095},
    {"key": "3y_plus", "label_en": "3+ years", "label_ar": "٣+ سنوات", "min_days": 1096, "max_days": None},
]

HEADCOUNT_KEY = c1.HEADCOUNT_KEY
FUTURE_STARTERS_KEY = c1.FUTURE_STARTERS_KEY
FTE_KEY = c1.FTE_KEY
HIRES_KEY = "workforce.hires.count"
EXITS_KEY = "workforce.exits.count"
TURNOVER_KEY = "workforce.turnover.rate"
RETENTION_KEY = "workforce.retention.rate"
TENURE_KEY = "workforce.tenure.distribution"
SPAN_KEY = "workforce.span_of_control"

STATUS_LABELS = {
    "active": {"en": "Active", "ar": "نشط"},
    "pending_start": {"en": "Pending start", "ar": "قيد الالتحاق"},
    "notice": {"en": "Notice period", "ar": "فترة إشعار"},
    "on_leave": {"en": "On leave", "ar": "في إجازة"},
    "suspended": {"en": "Suspended", "ar": "موقوف"},
    "left": {"en": "Left", "ar": "غادر"},
    "contingent": {"en": "Contingent", "ar": "متعاقد مؤقت"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "uses_c1_registry_evaluator": True,
        "no_second_analytics_math_engine": True,
        "fte_remains_blocked": True,
        "pending_start_excluded_from_headcount": True,
        "future_starters_separate": True,
        "contingent_not_mixed": True,
        "turnover_not_exits_over_current_hc": True,
        "retention_cohort_aware": True,
        "no_exit_reason_from_freetext": True,
        "demographics_off_by_default": True,
        "ordinary_headcount_not_suppressed_by_min_cohort": True,
        "sensitive_aggregates_use_min_cohort_n": True,
        "complementary_suppression": True,
        "assistant_mutations": False,
        "company_code": company_code_norm(company_code) if company_code else None,
        "headcount_policy": dict(c1.HEADCOUNT_POLICY),
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2=off",
            "Clear WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES",
            "WATHEFNI_ANALYTICS_KILL=on (optional)",
            "C1 Registry history retained",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_ANALYTICS_KILL", "off"):
        return {"ok": False, "enabled": False, "error": "analytics_kill_switch", "gate": "kill", "phase": PHASE}
    # C2 requires C1 spine
    c1_gate = c1.runtime_gate_for_company(company)
    if not c1_gate.get("ok"):
        return {**c1_gate, "error": "c1_registry_required", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_workforce_c2_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    raw = str(os.environ.get("WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES") or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_workforce_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_workforce_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_workforce_c2_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c2_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          tenure_bands jsonb NOT NULL DEFAULT '[]'::jsonb,
          turnover_qualifying_exit_types jsonb NOT NULL DEFAULT '["voluntary","involuntary","other"]'::jsonb,
          nationality_dimension_enabled boolean NOT NULL DEFAULT false,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Effective employment projection (materialized from domain / explicit upserts) — not alternate SoT
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_employment_periods (
          period_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          employment_period_key text NOT NULL,
          person_key text,
          worker_class text NOT NULL DEFAULT 'employee',
          status text NOT NULL,
          effective_start date NOT NULL,
          effective_end date,
          last_working_day date,
          notice_started_on date,
          on_leave boolean NOT NULL DEFAULT false,
          suspended boolean NOT NULL DEFAULT false,
          hire_event_date date,
          exit_event_date date,
          exit_type text,
          department text,
          location text,
          manager_employee_key text,
          job_role text,
          grade text,
          source_authority text NOT NULL,
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, employment_period_key)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hr_intel_emp_periods_asof
          ON hr_intelligence_employment_periods (company_code, effective_start, effective_end)
          WHERE superseded_by IS NULL
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_org_assignment_history (
          assignment_hist_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          employment_period_key text NOT NULL,
          department text,
          location text,
          manager_employee_key text,
          job_role text,
          grade text,
          effective_from date NOT NULL,
          effective_to date,
          source_authority text NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c2_audit (
          audit_id bigserial PRIMARY KEY,
          company_code text,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _audit(cur, *, company_code, action, actor_phone, reason=None, subject_type=None, subject_id=None, payload=None):
    cur.execute(
        """
        INSERT INTO hr_intelligence_c2_audit
          (company_code, action, actor_phone, reason, subject_type, subject_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code) if company_code else None,
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_hr_intelligence_workforce_c2_schema(cur)
    # C1 company entitlement required
    c1_ent = c1._entitled(cur, company)
    if not c1_ent.get("ok"):
        return {"ok": False, "error": "c1_company_intelligence_disabled", "detail": c1_ent}
    cur.execute("SELECT * FROM hr_intelligence_c2_company_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {"ok": False, "error": "company_workforce_intelligence_disabled", "company_code": company}
    return {"ok": True, "company_code": company, "settings": dict(row), "c1_settings": c1_ent["settings"]}


def enable_company_workforce_intelligence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    tenure_bands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    # ensure C1 enabled
    c1.enable_company_hr_intelligence(cur, company_code=company, actor_phone=actor_phone, reason="c2 requires c1")
    ensure_hr_intelligence_workforce_c2_schema(cur)
    bands = tenure_bands or DEFAULT_TENURE_BANDS
    cur.execute(
        """
        INSERT INTO hr_intelligence_c2_company_settings (
          company_code, enabled, tenure_bands, enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s::jsonb,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          tenure_bands=EXCLUDED.tenure_bands,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (company, json.dumps(bands, default=str), _digits(actor_phone), str(reason).strip()[:500]),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="company_enabled", actor_phone=actor_phone, reason=reason, subject_type="company", subject_id=company)
    seed_workforce_definitions(cur, actor_phone=actor_phone)
    _register_handlers()
    return {"ok": True, "settings": row, **honesty_payload(company_code=company)}


def disable_company_workforce_intelligence(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_hr_intelligence_workforce_c2_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c2_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="company_disabled", actor_phone=actor_phone, reason=reason, payload={"preserves_history": True})
    return {"ok": True, "settings": dict(row) if row else None, "preserves_history": True}


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def upsert_employment_period(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    employment_period_key: str,
    status: str,
    effective_start: date | str,
    reason: str,
    effective_end: date | str | None = None,
    last_working_day: date | str | None = None,
    notice_started_on: date | str | None = None,
    on_leave: bool = False,
    suspended: bool = False,
    worker_class: str = "employee",
    person_key: str | None = None,
    hire_event_date: date | str | None = None,
    exit_event_date: date | str | None = None,
    exit_type: str | None = None,
    department: str | None = None,
    location: str | None = None,
    manager_employee_key: str | None = None,
    job_role: str | None = None,
    grade: str | None = None,
    source_authority: str = "domain_employment",
    source_version: str | None = None,
    emit_facts: bool = True,
) -> dict[str, Any]:
    """Write effective employment projection + optional C1 facts (idempotent)."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    st = str(status).strip().lower()
    wc = str(worker_class or "employee").strip().lower()
    if wc not in ("employee", "contingent"):
        return {"ok": False, "error": "invalid_worker_class"}
    if exit_type and str(exit_type).strip().lower() not in ("voluntary", "involuntary", "other", "unknown"):
        return {"ok": False, "error": "invalid_exit_type", "message": "Canonical exit types only — no free-text inference"}
    es = _as_date(effective_start)
    if not es:
        return {"ok": False, "error": "effective_start_required"}
    ee = _as_date(effective_end)
    lwd = _as_date(last_working_day)
    ns = _as_date(notice_started_on)
    hd = _as_date(hire_event_date) or es
    xd = _as_date(exit_event_date)
    pid = str(uuid.uuid4())
    ver = source_version or f"v:{es}:{ee}:{st}:{lwd}"
    cur.execute(
        """
        INSERT INTO hr_intelligence_employment_periods (
          period_id, company_code, employee_key, employment_period_key, person_key, worker_class,
          status, effective_start, effective_end, last_working_day, notice_started_on,
          on_leave, suspended, hire_event_date, exit_event_date, exit_type,
          department, location, manager_employee_key, job_role, grade,
          source_authority, source_version, event_time
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
        )
        ON CONFLICT (company_code, employment_period_key) DO UPDATE SET
          status=EXCLUDED.status,
          effective_start=EXCLUDED.effective_start,
          effective_end=EXCLUDED.effective_end,
          last_working_day=EXCLUDED.last_working_day,
          notice_started_on=EXCLUDED.notice_started_on,
          on_leave=EXCLUDED.on_leave,
          suspended=EXCLUDED.suspended,
          hire_event_date=EXCLUDED.hire_event_date,
          exit_event_date=EXCLUDED.exit_event_date,
          exit_type=EXCLUDED.exit_type,
          department=EXCLUDED.department,
          location=EXCLUDED.location,
          manager_employee_key=EXCLUDED.manager_employee_key,
          job_role=EXCLUDED.job_role,
          grade=EXCLUDED.grade,
          source_version=EXCLUDED.source_version,
          worker_class=EXCLUDED.worker_class,
          person_key=COALESCE(EXCLUDED.person_key, hr_intelligence_employment_periods.person_key),
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            pid, company, employee_key, employment_period_key, person_key, wc,
            st, es, ee, lwd, ns, bool(on_leave), bool(suspended), hd, xd, exit_type,
            department, location, manager_employee_key, job_role, grade,
            source_authority, ver,
        ),
    )
    row = dict(cur.fetchone())
    # org history row (idempotent by period+from)
    if department or manager_employee_key or location or job_role or grade:
        cur.execute(
            """
            INSERT INTO hr_intelligence_org_assignment_history (
              assignment_hist_id, company_code, employee_key, employment_period_key,
              department, location, manager_employee_key, job_role, grade,
              effective_from, effective_to, source_authority
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(uuid.uuid4()), company, employee_key, employment_period_key,
                department, location, manager_employee_key, job_role, grade,
                es, ee, source_authority,
            ),
        )
    if emit_facts:
        _emit_period_facts(cur, company=company, actor_phone=actor_phone, row=row, reason=reason)
    _audit(cur, company_code=company, action="employment_period_upserted", actor_phone=actor_phone, reason=reason, subject_type="employment_period", subject_id=employment_period_key)
    return {"ok": True, "period": row}


def _emit_period_facts(cur, *, company: str, actor_phone: str, row: dict[str, Any], reason: str) -> None:
    dims = {
        "department": row.get("department"),
        "location": row.get("location"),
        "manager_employee_key": row.get("manager_employee_key"),
        "job_role": row.get("job_role"),
        "grade": row.get("grade"),
        "worker_class": row.get("worker_class"),
        "status": row.get("status"),
        "employment_period_key": row.get("employment_period_key"),
    }
    measures = {
        "on_leave": bool(row.get("on_leave")),
        "suspended": bool(row.get("suspended")),
        "last_working_day": str(row["last_working_day"]) if row.get("last_working_day") else None,
        "exit_type": row.get("exit_type"),
    }
    ef = row["effective_start"]
    et = row.get("effective_end")
    c1.ingest_fact(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        fact_type="workforce_employment_period",
        entity_type="employment_period",
        entity_id=str(row["employment_period_key"]),
        source_authority=str(row.get("source_authority") or "domain_employment"),
        measures=measures,
        dimensions=dims,
        effective_from=datetime.combine(_as_date(ef), datetime.min.time(), tzinfo=timezone.utc) if ef else None,
        effective_to=datetime.combine(_as_date(et), datetime.min.time(), tzinfo=timezone.utc) if et else None,
        source_version=str(row.get("source_version") or ""),
        ingest_key=f"emp_period:{row['employment_period_key']}:{row.get('source_version')}",
        reason=reason,
    )
    if row.get("hire_event_date"):
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="workforce_hire_event",
            entity_type="employment_period",
            entity_id=str(row["employment_period_key"]),
            source_authority=str(row.get("source_authority") or "domain_employment"),
            measures={"employee_key": row["employee_key"]},
            dimensions=dims,
            event_time=datetime.combine(_as_date(row["hire_event_date"]), datetime.min.time(), tzinfo=timezone.utc),
            source_version=str(row.get("source_version") or ""),
            ingest_key=f"hire:{row['employment_period_key']}",
            reason=reason,
        )
    if row.get("exit_event_date"):
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="workforce_exit_event",
            entity_type="employment_period",
            entity_id=str(row["employment_period_key"]),
            source_authority=str(row.get("source_authority") or "domain_employment"),
            measures={"employee_key": row["employee_key"], "exit_type": row.get("exit_type")},
            dimensions=dims,
            event_time=datetime.combine(_as_date(row["exit_event_date"]), datetime.min.time(), tzinfo=timezone.utc),
            source_version=str(row.get("source_version") or ""),
            ingest_key=f"exit:{row['employment_period_key']}",
            reason=reason,
        )


def correct_employment_period(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employment_period_key: str,
    reason: str,
    **updates: Any,
) -> dict[str, Any]:
    """Governed correction via new source_version; prior C1 facts superseded through ingest keys."""
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        SELECT * FROM hr_intelligence_employment_periods
         WHERE company_code=%s AND employment_period_key=%s AND superseded_by IS NULL
        """,
        (company, employment_period_key),
    )
    prior = cur.fetchone()
    if not prior:
        return {"ok": False, "error": "period_not_found"}
    prior = dict(prior)
    payload = {k: prior.get(k) for k in (
        "employee_key", "status", "effective_start", "effective_end", "last_working_day",
        "notice_started_on", "on_leave", "suspended", "worker_class", "person_key",
        "hire_event_date", "exit_event_date", "exit_type", "department", "location",
        "manager_employee_key", "job_role", "grade", "source_authority",
    )}
    payload.update(updates)
    payload["source_version"] = f"corr:{uuid.uuid4().hex[:8]}"
    return upsert_employment_period(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employment_period_key=employment_period_key,
        reason=reason,
        **payload,
    )


def _active_periods(cur, *, company: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM hr_intelligence_employment_periods
         WHERE company_code=%s AND superseded_by IS NULL
        """,
        (company,),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def classify_as_of(period: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Apply binding headcount inclusion rules for a single employment period at as_of."""
    wc = str(period.get("worker_class") or "employee").lower()
    if wc == "contingent":
        return {
            "include_in_headcount": False,
            "include_in_future_starters": False,
            "bucket": "contingent_excluded",
            "reason_en": "Contingent/non-employee workers are never mixed into employee headcount",
            "reason_ar": "المتعاقدون المؤقتون لا يُخلطون مع عدد رؤوس الموظفين",
        }
    es = _as_date(period.get("effective_start"))
    ee = _as_date(period.get("effective_end"))
    lwd = _as_date(period.get("last_working_day")) or ee
    st = str(period.get("status") or "").lower()

    # Not yet started period
    if es and as_of < es:
        if st in ("pending_start", "joining", "future_start") or True:
            return {
                "include_in_headcount": False,
                "include_in_future_starters": st in ("pending_start", "joining", "future_start") or (es > as_of),
                "bucket": "not_yet_started",
                "reason_en": "Employment has not started as-of date",
                "reason_ar": "لم يبدأ التوظيف في تاريخ القطع",
            }

    # Ended: after effective end or after LWD
    end_boundary = lwd or ee
    if end_boundary and as_of > end_boundary:
        return {
            "include_in_headcount": False,
            "include_in_future_starters": False,
            "bucket": "left_after_end",
            "reason_en": "Past effective last working day / end date",
            "reason_ar": "بعد آخر يوم عمل / تاريخ الانتهاء الفعلي",
        }

    # pending_start on/after start? If status still pending_start and as_of < start handled above.
    # If as_of >= start but status pending_start, treat as future starter still excluded from HC
    if st in ("pending_start", "joining", "future_start"):
        return {
            "include_in_headcount": False,
            "include_in_future_starters": True,
            "bucket": "pending_start",
            "reason_en": "pending_start excluded from actual headcount",
            "reason_ar": "قيد الالتحاق مستبعد من عدد الرؤوس الفعلي",
        }

    # notice: included until LWD/end
    if st == "notice" or period.get("notice_started_on"):
        if end_boundary and as_of <= end_boundary:
            return {
                "include_in_headcount": True,
                "include_in_future_starters": False,
                "bucket": "notice_included",
                "reason_en": "Notice-period employee included until effective LWD/end",
                "reason_ar": "موظف فترة الإشعار مشمول حتى آخر يوم عمل/الانتهاء",
            }

    if st == "left":
        return {
            "include_in_headcount": False,
            "include_in_future_starters": False,
            "bucket": "left",
            "reason_en": "Employment left/terminated",
            "reason_ar": "انتهى التوظيف",
        }

    # active / on_leave / suspended while employment active
    if st in ("active", "on_leave", "suspended") or period.get("on_leave") or period.get("suspended"):
        return {
            "include_in_headcount": True,
            "include_in_future_starters": False,
            "bucket": "active_included",
            "reason_en": "Active employment (leave/suspension still included)",
            "reason_ar": "توظيف نشط (الإجازة/الوقف ما زالا مشمولين)",
        }

    # default: if within [start, end] include
    if es and as_of >= es and (end_boundary is None or as_of <= end_boundary):
        return {
            "include_in_headcount": True,
            "include_in_future_starters": False,
            "bucket": "active_included",
            "reason_en": "Within effective employment range",
            "reason_ar": "ضمن فترة التوظيف الفعلية",
        }
    return {
        "include_in_headcount": False,
        "include_in_future_starters": False,
        "bucket": "excluded",
        "reason_en": "Not in employee headcount population",
        "reason_ar": "خارج مجتمع عدد رؤوس الموظفين",
    }


def resolve_workforce_population(
    cur: Any,
    *,
    company_code: str,
    as_of: date | str | None = None,
    manager_scope_employee_keys: list[str] | None = None,
    actor_role: str = "hr",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    as_of_d = _as_date(as_of) or date.today()
    periods = _active_periods(cur, company=company)
    headcount: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for p in periods:
        cls = classify_as_of(p, as_of_d)
        item = {
            "employee_key": p["employee_key"],
            "employment_period_key": p["employment_period_key"],
            "person_key": p.get("person_key"),
            "department": p.get("department"),
            "location": p.get("location"),
            "manager_employee_key": p.get("manager_employee_key"),
            "job_role": p.get("job_role"),
            "grade": p.get("grade"),
            "status": p.get("status"),
            "worker_class": p.get("worker_class"),
            **cls,
        }
        if manager_scope_employee_keys is not None and actor_role == "manager":
            if p["employee_key"] not in set(manager_scope_employee_keys):
                continue
        if cls["include_in_headcount"]:
            headcount.append(item)
        elif cls["include_in_future_starters"]:
            future.append(item)
        else:
            excluded.append(item)
    return {
        "ok": True,
        "company_code": company,
        "as_of": str(as_of_d),
        "time_semantics": {
            "event_time": "hire/exit event dates on period",
            "effective_time": "effective_start/effective_end/LWD",
            "recorded_time": "recorded_at on projection/facts",
        },
        "headcount_population": headcount,
        "future_starters_population": future,
        "excluded_population": excluded,
        "headcount": len(headcount),
        "future_starters": len(future),
        "policy": dict(c1.HEADCOUNT_POLICY),
    }


def org_dims_as_of(cur, *, company: str, employee_key: str, employment_period_key: str, as_of: date) -> dict[str, Any]:
    """Historical org segment from assignment history — later transfers do not rewrite as-of."""
    cur.execute(
        """
        SELECT * FROM hr_intelligence_org_assignment_history
         WHERE company_code=%s AND employment_period_key=%s AND superseded_by IS NULL
           AND effective_from <= %s
           AND (effective_to IS NULL OR effective_to >= %s)
         ORDER BY effective_from DESC
         LIMIT 1
        """,
        (company, employment_period_key, as_of, as_of),
    )
    row = cur.fetchone()
    if row:
        d = dict(row)
        return {
            "department": d.get("department"),
            "location": d.get("location"),
            "manager_employee_key": d.get("manager_employee_key"),
            "job_role": d.get("job_role"),
            "grade": d.get("grade"),
            "historical": True,
        }
    # fallback to period snapshot
    cur.execute(
        """
        SELECT department, location, manager_employee_key, job_role, grade
          FROM hr_intelligence_employment_periods
         WHERE company_code=%s AND employment_period_key=%s AND superseded_by IS NULL
        """,
        (company, employment_period_key),
    )
    r = cur.fetchone()
    return dict(r) if r else {}


def apply_complementary_suppression(
    *,
    segment_count: int,
    complement_count: int,
    min_cohort_n: int,
    sensitive: bool,
) -> dict[str, Any]:
    if not sensitive:
        return {"suppressed": False}
    if segment_count < min_cohort_n or complement_count < min_cohort_n:
        return {
            "suppressed": True,
            "reason_en": "Sensitive cohort or complement below min_cohort_n",
            "reason_ar": "المجموعة الحساسة أو مكملها دون الحد الأدنى",
            "segment_count": segment_count,
            "complement_count": complement_count,
            "min_cohort_n": min_cohort_n,
        }
    return {"suppressed": False}


def _parse_window(time_window: dict[str, Any]) -> tuple[date, date]:
    start = _as_date(time_window.get("period_start") or time_window.get("start"))
    end = _as_date(time_window.get("period_end") or time_window.get("end"))
    if not start or not end:
        # default last 30 days
        end = date.today()
        start = end - timedelta(days=30)
    return start, end


def _handler_headcount(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    as_of = _as_date(time_window.get("as_of") or filters.get("as_of")) or date.today()
    scope = filters.get("manager_scope_employee_keys")
    pop = resolve_workforce_population(
        cur,
        company_code=company_code,
        as_of=as_of,
        manager_scope_employee_keys=scope,
        actor_role=actor_role,
    )
    if not pop.get("ok"):
        return pop
    members = pop["headcount_population"]
    # optional dimension filter (non-demographic by default)
    dim = filters.get("dimension")
    dim_val = filters.get("dimension_value")
    if dim and dim_val:
        if dim in ("nationality", "gender"):
            cur.execute(
                "SELECT nationality_dimension_enabled FROM hr_intelligence_c2_company_settings WHERE company_code=%s",
                (company_code,),
            )
            srow = cur.fetchone()
            nat_on = bool(dict(srow).get("nationality_dimension_enabled")) if srow else False
            if dim == "gender" or (dim == "nationality" and not nat_on):
                return {"status": "forbidden", "error": "demographic_dimension_disabled", "value": None, "population_ids": []}
        members = [m for m in members if str(m.get(dim) or "") == str(dim_val)]
        # complementary suppression only for sensitive demographic dims
        if dim in ("nationality", "gender"):
            complement = pop["headcount"] - len(members)
            min_n = int(settings.get("min_cohort_n") or 5)
            comp = apply_complementary_suppression(
                segment_count=len(members), complement_count=complement, min_cohort_n=min_n, sensitive=True
            )
            if comp["suppressed"]:
                return {
                    "status": "suppressed",
                    "value": None,
                    "population_ids": [],
                    "explain": {"complementary_suppression": comp, "as_of": str(as_of)},
                }
    ids = [m["employee_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "unit": "heads",
        "numerator_value": float(len(ids)),
        "population_ids": ids,
        "explain": {
            "as_of": str(as_of),
            "inclusion_policy": dict(c1.HEADCOUNT_POLICY),
            "members": members,
            "name_en": publication.get("name_en"),
            "name_ar": publication.get("name_ar"),
        },
    }


def _handler_future_starters(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    as_of = _as_date(time_window.get("as_of") or filters.get("as_of")) or date.today()
    scope = filters.get("manager_scope_employee_keys")
    pop = resolve_workforce_population(
        cur, company_code=company_code, as_of=as_of, manager_scope_employee_keys=scope, actor_role=actor_role
    )
    if not pop.get("ok"):
        return pop
    members = pop["future_starters_population"]
    ids = [m["employee_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "unit": "count",
        "population_ids": ids,
        "explain": {"as_of": str(as_of), "members": members, "separate_from_headcount": True},
    }


def _handler_hires(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    start, end = _parse_window(time_window)
    periods = _active_periods(cur, company=company_code)
    scope = set(filters.get("manager_scope_employee_keys") or []) if actor_role == "manager" else None
    members = []
    for p in periods:
        if str(p.get("worker_class") or "employee") != "employee":
            continue
        hd = _as_date(p.get("hire_event_date"))
        if not hd or hd < start or hd > end:
            continue
        if scope is not None and p["employee_key"] not in scope:
            continue
        members.append({
            "employee_key": p["employee_key"],
            "employment_period_key": p["employment_period_key"],
            "hire_event_date": str(hd),
            "department": p.get("department"),
        })
    ids = [m["employment_period_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "unit": "count",
        "population_ids": ids,
        "explain": {"period_start": str(start), "period_end": str(end), "members": members, "rehire_distinct_periods": True},
    }


def _handler_exits(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    start, end = _parse_window(time_window)
    periods = _active_periods(cur, company=company_code)
    scope = set(filters.get("manager_scope_employee_keys") or []) if actor_role == "manager" else None
    members = []
    for p in periods:
        if str(p.get("worker_class") or "employee") != "employee":
            continue
        xd = _as_date(p.get("exit_event_date"))
        if not xd or xd < start or xd > end:
            continue
        if scope is not None and p["employee_key"] not in scope:
            continue
        members.append({
            "employee_key": p["employee_key"],
            "employment_period_key": p["employment_period_key"],
            "exit_event_date": str(xd),
            "exit_type": p.get("exit_type"),
        })
    ids = [m["employment_period_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "unit": "count",
        "population_ids": ids,
        "explain": {"period_start": str(start), "period_end": str(end), "members": members},
    }


def _handler_turnover(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    """Turnover = exits_in_period / average_headcount * 100; average = (HC_start + HC_end)/2."""
    start, end = _parse_window(time_window)
    scope = filters.get("manager_scope_employee_keys")
    exits = _handler_exits(
        cur, company_code=company_code, settings=settings, formula_contract=formula_contract,
        publication=publication, filters=filters, time_window={"period_start": start, "period_end": end},
        actor_phone=actor_phone, actor_role=actor_role,
    )
    # qualify exit types
    cur.execute("SELECT turnover_qualifying_exit_types FROM hr_intelligence_c2_company_settings WHERE company_code=%s", (company_code,))
    srow = cur.fetchone()
    allowed = set(dict(srow).get("turnover_qualifying_exit_types") or ["voluntary", "involuntary", "other"]) if srow else {"voluntary", "involuntary", "other"}
    if isinstance(next(iter(allowed), None), str) is False and allowed:
        pass
    # filter members by exit_type when present
    members = []
    for m in exits.get("explain", {}).get("members") or []:
        et = m.get("exit_type") or "other"
        if et in allowed or et == "unknown":
            # unknown only if formula allows
            if et == "unknown" and not formula_contract.get("allow_unknown_exit_type"):
                continue
            members.append(m)
    num = float(len(members))
    hc_start = resolve_workforce_population(cur, company_code=company_code, as_of=start, manager_scope_employee_keys=scope, actor_role=actor_role)
    hc_end = resolve_workforce_population(cur, company_code=company_code, as_of=end, manager_scope_employee_keys=scope, actor_role=actor_role)
    den = (float(hc_start["headcount"]) + float(hc_end["headcount"])) / 2.0
    if den == 0:
        return {
            "status": "not_applicable",
            "value": None,
            "numerator_value": num,
            "denominator_value": 0.0,
            "population_ids": [m["employment_period_key"] for m in members],
            "explain": {
                "method": "exits / average_headcount",
                "average_headcount": den,
                "hc_start": hc_start["headcount"],
                "hc_end": hc_end["headcount"],
                "period_start": str(start),
                "period_end": str(end),
                "zero_denominator": "not_applicable",
            },
        }
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [m["employment_period_key"] for m in members],
        "explain": {
            "method": "exits_in_period / ((HC_start + HC_end)/2) * 100",
            "numerator_exits": members,
            "hc_start": hc_start["headcount"],
            "hc_end": hc_end["headcount"],
            "average_headcount": den,
            "period_start": str(start),
            "period_end": str(end),
        },
    }


def _handler_retention(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    """Cohort retention: hires in cohort_window who remain in headcount at retention_as_of."""
    cohort_start = _as_date(time_window.get("cohort_start") or time_window.get("period_start"))
    cohort_end = _as_date(time_window.get("cohort_end") or time_window.get("period_end"))
    retain_as_of = _as_date(time_window.get("retention_as_of") or time_window.get("as_of"))
    if not cohort_start or not cohort_end or not retain_as_of:
        return {"status": "insufficient_data", "error": "cohort_window_and_retention_as_of_required", "value": None, "population_ids": []}
    scope = filters.get("manager_scope_employee_keys")
    hires = _handler_hires(
        cur, company_code=company_code, settings=settings, formula_contract=formula_contract,
        publication=publication, filters=filters,
        time_window={"period_start": cohort_start, "period_end": cohort_end},
        actor_phone=actor_phone, actor_role=actor_role,
    )
    cohort = hires.get("explain", {}).get("members") or []
    if not cohort:
        return {
            "status": "not_applicable",
            "value": None,
            "numerator_value": 0.0,
            "denominator_value": 0.0,
            "population_ids": [],
            "explain": {"reason": "empty_cohort", "cohort_start": str(cohort_start), "cohort_end": str(cohort_end)},
        }
    pop = resolve_workforce_population(cur, company_code=company_code, as_of=retain_as_of, manager_scope_employee_keys=scope, actor_role=actor_role)
    active_keys = {m["employment_period_key"] for m in pop.get("headcount_population") or []}
    # also match by employee_key+period
    retained = []
    for m in cohort:
        # retained if that employment period still in headcount OR employee still active on same period
        if m["employment_period_key"] in active_keys:
            retained.append(m)
        else:
            # check employee still headcount on a later period? Retention is period-cohort: must remain on SAME employment period
            pass
    den = float(len(cohort))
    num = float(len(retained))
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [m["employment_period_key"] for m in retained],
        "explain": {
            "cohort": cohort,
            "retained": retained,
            "exclusions": [m for m in cohort if m not in retained],
            "cohort_start": str(cohort_start),
            "cohort_end": str(cohort_end),
            "retention_as_of": str(retain_as_of),
            "not_inverse_of_turnover": True,
        },
    }


def _handler_tenure(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    as_of = _as_date(time_window.get("as_of") or filters.get("as_of")) or date.today()
    scope = filters.get("manager_scope_employee_keys")
    pop = resolve_workforce_population(cur, company_code=company_code, as_of=as_of, manager_scope_employee_keys=scope, actor_role=actor_role)
    cur.execute("SELECT tenure_bands FROM hr_intelligence_c2_company_settings WHERE company_code=%s", (company_code,))
    srow = cur.fetchone()
    bands = dict(srow).get("tenure_bands") if srow else DEFAULT_TENURE_BANDS
    if isinstance(bands, str):
        bands = json.loads(bands)
    # map employee -> current employment period tenure (not merged rehire history)
    periods = {p["employment_period_key"]: p for p in _active_periods(cur, company=company_code)}
    dist = {b["key"]: [] for b in bands}
    for m in pop.get("headcount_population") or []:
        p = periods.get(m["employment_period_key"])
        if not p:
            continue
        start = _as_date(p.get("hire_event_date") or p.get("effective_start"))
        if not start:
            continue
        days = (as_of - start).days
        for b in bands:
            mx = b.get("max_days")
            mn = int(b.get("min_days") or 0)
            if days >= mn and (mx is None or days <= int(mx)):
                dist[b["key"]].append({
                    "employee_key": m["employee_key"],
                    "employment_period_key": m["employment_period_key"],
                    "tenure_days": days,
                    "tenure_basis": "current_employment_period",
                })
                break
    # value = count in requested band or total distribution object via explain
    band_key = filters.get("tenure_band")
    if band_key:
        ids = [x["employee_key"] for x in dist.get(band_key) or []]
        return {"status": "ok", "value": float(len(ids)), "population_ids": ids, "explain": {"distribution": dist, "as_of": str(as_of), "bands": bands}}
    # default: return total headcount with distribution in explain
    all_ids = [m["employee_key"] for m in pop.get("headcount_population") or []]
    return {
        "status": "ok",
        "value": float(len(all_ids)),
        "population_ids": all_ids,
        "explain": {"distribution": {k: len(v) for k, v in dist.items()}, "members_by_band": dist, "as_of": str(as_of), "bands": bands},
    }


def _handler_span(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    as_of = _as_date(time_window.get("as_of") or filters.get("as_of")) or date.today()
    manager_key = filters.get("manager_employee_key")
    pop = resolve_workforce_population(cur, company_code=company_code, as_of=as_of, actor_role="hr")
    reports = []
    for m in pop.get("headcount_population") or []:
        dims = org_dims_as_of(cur, company=company_code, employee_key=m["employee_key"], employment_period_key=m["employment_period_key"], as_of=as_of)
        mgr = dims.get("manager_employee_key") or m.get("manager_employee_key")
        if manager_key and mgr != manager_key:
            continue
        if not manager_key:
            # aggregate span facts: count per manager in explain; value = managers counted
            pass
        reports.append({**m, "manager_employee_key": mgr, "department_as_of": dims.get("department")})
    if manager_key:
        ids = [r["employee_key"] for r in reports]
        return {
            "status": "ok",
            "value": float(len(ids)),
            "unit": "count",
            "population_ids": ids,
            "explain": {"manager_employee_key": manager_key, "direct_reports": reports, "as_of": str(as_of)},
        }
    # company-wide: number of managers with >=1 report
    by_mgr: dict[str, list] = {}
    for r in reports:
        mk = r.get("manager_employee_key") or ""
        if not mk:
            continue
        by_mgr.setdefault(mk, []).append(r["employee_key"])
    return {
        "status": "ok",
        "value": float(len(by_mgr)),
        "unit": "count",
        "population_ids": list(by_mgr.keys()),
        "explain": {"spans": {k: len(v) for k, v in by_mgr.items()}, "as_of": str(as_of)},
    }


def _register_handlers() -> None:
    c1.register_formula_handler("workforce_headcount", _handler_headcount)
    c1.register_formula_handler("workforce_future_starters", _handler_future_starters)
    c1.register_formula_handler("workforce_hires", _handler_hires)
    c1.register_formula_handler("workforce_exits", _handler_exits)
    c1.register_formula_handler("workforce_turnover", _handler_turnover)
    c1.register_formula_handler("workforce_retention", _handler_retention)
    c1.register_formula_handler("workforce_tenure", _handler_tenure)
    c1.register_formula_handler("workforce_span", _handler_span)


def seed_workforce_definitions(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    created = []

    def _ensure(key: str, **kwargs):
        want_kind = (kwargs.get("formula_contract") or {}).get("kind")
        cur.execute(
            """
            SELECT kpi_definition_id, status, effective_version, formula_contract
              FROM hr_kpi_definitions WHERE semantic_key=%s
             ORDER BY effective_version DESC LIMIT 1
            """,
            (key,),
        )
        ex = cur.fetchone()
        if ex:
            ex = dict(ex)
            fc = ex.get("formula_contract")
            if isinstance(fc, str):
                fc = json.loads(fc)
            if want_kind and (not fc or fc.get("kind") != want_kind):
                ver = c1.version_kpi_definition(
                    cur,
                    actor_phone=actor_phone,
                    semantic_key=key,
                    reason=f"c2 activate {key}",
                    updates={**kwargs, "status": kwargs.get("status") or "published"},
                )
                if ver.get("ok"):
                    created.append(key)
                    if (kwargs.get("status") or "published") == "published":
                        c1.publish_kpi_definition(
                            cur,
                            actor_phone=actor_phone,
                            kpi_definition_id=str(ver["definition"]["kpi_definition_id"]),
                            reason="c2 publish",
                        )
                return
            if kwargs.get("status") == "published" and ex["status"] != "published" and ex["status"] != "blocked":
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone, kpi_definition_id=str(ex["kpi_definition_id"]), reason="c2 seed publish"
                )
            return
        out = c1.create_kpi_definition(cur, actor_phone=actor_phone, semantic_key=key, **kwargs)
        if out.get("ok"):
            created.append(key)
            if kwargs.get("status") == "published":
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone, kpi_definition_id=str(out["definition"]["kpi_definition_id"]), reason="c2 seed publish"
                )

    _ensure(
        HEADCOUNT_KEY,
        name_en="Active headcount (heads)", name_ar="عدد الرؤوس النشط",
        description_en="Point-in-time employee heads per binding inclusion policy.",
        description_ar="عدد الموظفين النشطين حسب سياسة الإدراج الملزمة.",
        business_meaning="Workforce size as-of date; pending_start excluded; notice included until LWD.",
        formula_contract={"kind": "workforce_headcount", "sensitive_aggregate": False},
        unit="heads", time_semantics="point_in_time", permission_class="workforce_general", status="published",
        inclusion_rules=dict(c1.HEADCOUNT_POLICY), numerator={"description": "included employees"},
        supported_dimensions=["department", "location", "manager", "job_role", "grade"],
        canonical_source_facts=["workforce_employment_period"], owner="wave5_c2", reason="c2 headcount",
    )
    _ensure(
        FUTURE_STARTERS_KEY,
        name_en="Future starters", name_ar="الملتحقون المستقبليون",
        description_en="pending_start / future starters — separate from headcount.",
        description_ar="قيد الالتحاق / الملتحقون المستقبليون — منفصل عن عدد الرؤوس.",
        business_meaning="Separate population for pending_start.",
        formula_contract={"kind": "workforce_future_starters", "sensitive_aggregate": False},
        unit="count", time_semantics="point_in_time", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 future starters",
    )
    # Keep FTE blocked — do not publish
    _ensure(
        HIRES_KEY,
        name_en="Hires", name_ar="التعيينات",
        description_en="Employment hire events in period (distinct employment periods).",
        description_ar="أحداث التعيين خلال الفترة (فترات توظيف متميزة).",
        business_meaning="Count of hire events; rehire = new employment period.",
        formula_contract={"kind": "workforce_hires", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 hires",
    )
    _ensure(
        EXITS_KEY,
        name_en="Exits", name_ar="المغادرات",
        description_en="Employment exit events in period.",
        description_ar="أحداث المغادرة خلال الفترة.",
        business_meaning="Count of exit events with canonical exit_type when present.",
        formula_contract={"kind": "workforce_exits", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 exits",
    )
    _ensure(
        TURNOVER_KEY,
        name_en="Turnover rate", name_ar="معدل الدوران",
        description_en="Exits in period ÷ average headcount ((HC_start+HC_end)/2) × 100.",
        description_ar="المغادرات ÷ متوسط عدد الرؤوس ((البداية+النهاية)/٢) × ١٠٠.",
        business_meaning="Period turnover with honest average-headcount denominator.",
        formula_contract={"kind": "workforce_turnover", "sensitive_aggregate": False, "denominator_method": "average_headcount_start_end"},
        unit="percent", time_semantics="rate_over_window", permission_class="workforce_general", status="published",
        numerator={"description": "qualifying exits"}, denominator={"description": "(HC_start+HC_end)/2"},
        owner="wave5_c2", reason="c2 turnover",
    )
    _ensure(
        RETENTION_KEY,
        name_en="Cohort retention rate", name_ar="معدل الاحتفاظ بالدفعة",
        description_en="Share of hire cohort still in headcount at retention as-of (same employment period).",
        description_ar="حصة دفعة التعيين التي ما زالت في عدد الرؤوس بتاريخ الاحتفاظ.",
        business_meaning="Cohort-aware retention; not assumed inverse of turnover.",
        formula_contract={"kind": "workforce_retention", "sensitive_aggregate": False},
        unit="percent", time_semantics="cohort", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 retention",
    )
    _ensure(
        TENURE_KEY,
        name_en="Tenure distribution", name_ar="توزيع مدة الخدمة",
        description_en="Current-employment tenure bands from Setup/Registry.",
        description_ar="شرائح مدة الخدمة للتوظيف الحالي من الإعداد/السجل.",
        business_meaning="Does not silently merge separate employments.",
        formula_contract={"kind": "workforce_tenure", "sensitive_aggregate": False},
        unit="count", time_semantics="point_in_time", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 tenure",
    )
    _ensure(
        SPAN_KEY,
        name_en="Span of control", name_ar="نطاق الإشراف",
        description_en="Direct-report counts from historical org assignments.",
        description_ar="عدد المرؤوسين المباشرين من تعيينات التنظيم التاريخية.",
        business_meaning="Uses effective-time org history.",
        formula_contract={"kind": "workforce_span", "sensitive_aggregate": False},
        unit="count", time_semantics="point_in_time", permission_class="workforce_general", status="published",
        owner="wave5_c2", reason="c2 span",
    )
    _register_handlers()
    return {"ok": True, "created_or_activated": created}


def publish_workforce_kpis_for_company(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    pubs = []
    for key in (HEADCOUNT_KEY, FUTURE_STARTERS_KEY, HIRES_KEY, EXITS_KEY, TURNOVER_KEY, RETENTION_KEY, TENURE_KEY, SPAN_KEY):
        p = c1.publish_kpi_for_company(cur, company_code=company_code, actor_phone=actor_phone, semantic_key=key, reason=reason)
        pubs.append({"semantic_key": key, "ok": p.get("ok"), "error": p.get("error")})
    # FTE must fail
    fte = c1.publish_kpi_for_company(cur, company_code=company_code, actor_phone=actor_phone, semantic_key=FTE_KEY, reason=reason)
    return {"ok": True, "publications": pubs, "fte_blocked": fte.get("ok") is not True, "fte_error": fte.get("error")}


def rebuild_workforce_facts(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    """Idempotent rebuild: re-emit C1 facts from employment period projection."""
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    periods = _active_periods(cur, company=company)
    n = 0
    for row in periods:
        _emit_period_facts(cur, company=company, actor_phone=actor_phone, row=row, reason=reason)
        n += 1
    _audit(cur, company_code=company, action="workforce_facts_rebuilt", actor_phone=actor_phone, reason=reason, payload={"periods": n})
    return {"ok": True, "periods_emitted": n, "idempotent": True}


# register on import when env allows (safe no-op for handlers)
_register_handlers()
