"""Setup Console Phase 3A — complete company-facing payroll setup gaps.

Composes Phase 2A + P6 variance/allowlist + public_holidays + employee_identity.
Does not change calculation, sealing, or Wathefni-owned statutory rates.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import payroll_authority_production_p6 as p6
import payroll_authority_wave1 as pyw1

PHASE = "setup_console_phase3a"
DEFAULT_WEEKEND_DAYS = ["fri", "sat"]
WEEKDAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
STATUTORY_CATEGORIES = ("kuwaiti_national", "gcc_national", "expatriate")

FIELD_DEEP_LINKS_3A = {
    "working_calendar": "/setup-console#classic-payroll-setup-calendar",
    "employee_statutory_classifications": "/setup-console#classic-payroll-setup-statutory-inputs",
    "pifss_wage_bases": "/setup-console#classic-payroll-setup-statutory-inputs",
    "variance_thresholds": "/setup-console#classic-payroll-setup-variance",
    "employee_allowlist": "/setup-console#classic-payroll-setup-allowlist",
    "mode_a_entitlement": "/setup-console#classic-payroll-setup-authority",
}


def ensure_phase3a_schema(cur: Any) -> None:
    """Additive statutory input store + setup extras (via Phase 2A column)."""
    pyw1.ensure_payroll_wave1_schema(cur)
    cur.execute(
        """
        ALTER TABLE payroll_company_settings
          ADD COLUMN IF NOT EXISTS setup_extras jsonb NOT NULL DEFAULT '{}'::jsonb
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_employee_statutory_inputs (
          company_code text NOT NULL,
          employee_key text NOT NULL,
          employee_category text,
          pifss_wage_by_fund jsonb NOT NULL DEFAULT '{}'::jsonb,
          notes text,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payroll_employee_statutory_inputs_cat
          ON payroll_employee_statutory_inputs (company_code, employee_category)
        """
    )


def normalize_weekend_days(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    out: list[str] = []
    for item in value or []:
        key = str(item or "").strip().lower()[:3]
        # accept fri / friday
        mapping = {
            "sun": "sun",
            "mon": "mon",
            "tue": "tue",
            "wed": "wed",
            "thu": "thu",
            "fri": "fri",
            "sat": "sat",
        }
        for full, short in (
            ("sunday", "sun"),
            ("monday", "mon"),
            ("tuesday", "tue"),
            ("wednesday", "wed"),
            ("thursday", "thu"),
            ("friday", "fri"),
            ("saturday", "sat"),
        ):
            if key.startswith(full[:3]) or key == short:
                key = short
                break
        if key in mapping and key not in out:
            out.append(key)
    return out


def working_days_from_weekend(weekend_days: list[str]) -> list[str]:
    rest = set(weekend_days)
    return [d for d in WEEKDAY_KEYS if d not in rest]


def parse_setup_extras(settings: dict[str, Any]) -> dict[str, Any]:
    raw = settings.get("setup_extras") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    weekend = normalize_weekend_days(raw.get("weekend_days"))
    configured = bool(raw.get("calendar_configured")) or bool(weekend)
    return {
        "payroll_frequency": str(raw.get("payroll_frequency") or "monthly"),
        "cutoff_day": raw.get("cutoff_day"),
        "period_end_rule": str(raw.get("period_end_rule") or "calendar_month"),
        "working_calendar_note": str(raw.get("working_calendar_note") or ""),
        "weekend_days": weekend,
        "working_days": working_days_from_weekend(weekend) if weekend else [],
        "calendar_configured": configured,
        "holiday_calendar_source": str(raw.get("holiday_calendar_source") or "company_public_holidays"),
        "use_wathefni_public_holiday_pack": bool(raw.get("use_wathefni_public_holiday_pack", True)),
    }


def list_company_holidays(cur: Any, *, company_code: str, year: int | None = None) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    year_n = int(year or date.today().year)
    cur.execute(
        """
        SELECT holiday_id::text AS holiday_id, holiday_date::text AS holiday_date,
               name, year, COALESCE(review_status, 'company') AS review_status,
               COALESCE(source_provenance, 'company') AS source_provenance
        FROM public_holidays
        WHERE company_code=%s AND year=%s
        ORDER BY holiday_date
        """,
        (company, year_n),
    )
    rows = cur.fetchall() or []
    out = []
    for r in rows:
        out.append(dict(r) if isinstance(r, dict) else {
            "holiday_id": r[0],
            "holiday_date": r[1],
            "name": r[2],
            "year": r[3],
            "review_status": r[4],
            "source_provenance": r[5],
        })
    return out


def upsert_company_holiday(
    cur: Any,
    *,
    company_code: str,
    holiday_date: str,
    name: str,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    d = date.fromisoformat(str(holiday_date)[:10])
    cur.execute(
        """
        INSERT INTO public_holidays (company_code, holiday_date, name, year)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (company_code, holiday_date) DO UPDATE SET name=EXCLUDED.name
        RETURNING holiday_id::text AS holiday_id, holiday_date::text AS holiday_date, name, year
        """,
        (company, d, str(name or "").strip() or "Company holiday", d.year),
    )
    row = cur.fetchone()
    _ = actor_phone
    return {"ok": True, "holiday": dict(row) if isinstance(row, dict) else None}


def delete_company_holiday(cur: Any, *, company_code: str, holiday_date: str) -> dict[str, Any]:
    company = (company_code or "").upper()
    d = date.fromisoformat(str(holiday_date)[:10])
    cur.execute(
        "DELETE FROM public_holidays WHERE company_code=%s AND holiday_date=%s RETURNING holiday_date::text",
        (company, d),
    )
    return {"ok": True, "deleted": cur.fetchone() is not None}


def seed_kuwait_fixed_holidays(cur: Any, *, company_code: str, year: int | None = None) -> dict[str, Any]:
    """Reuse leave_policy_wave2 pack for fixed Gregorian KW holidays (Wathefni interpretation)."""
    year_n = int(year or date.today().year)
    try:
        import leave_policy_wave2 as leave_w2

        n = leave_w2.seed_fixed_kuwait_holidays(cur, company_code, year=year_n)
        return {
            "ok": True,
            "seeded": n,
            "year": year_n,
            "ownership": {
                "statutory_public_holidays": "wathefni",
                "company_operational_overrides": "company",
            },
        }
    except Exception as exc:
        return {"ok": False, "error": "holiday_seed_failed", "message": str(exc)[:200]}


def statutory_gap_summary(cur: Any, *, company_code: str, limit: int = 25) -> dict[str, Any]:
    """Count active employees with approved contracts missing category / PIFSS wage base."""
    ensure_phase3a_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT e.employee_key, e.name,
               COALESCE(ei.employee_category, si.employee_category) AS category,
               si.pifss_wage_by_fund
        FROM payroll_compensation_contracts c
        JOIN employees e
          ON e.company_code=c.company_code AND e.employee_key=c.employee_key
        LEFT JOIN employee_identity ei
          ON ei.company_code=c.company_code AND ei.employee_key=c.employee_key
        LEFT JOIN payroll_employee_statutory_inputs si
          ON si.company_code=c.company_code AND si.employee_key=c.employee_key
        WHERE c.company_code=%s
          AND c.status='approved'
          AND COALESCE(NULLIF(lower(e.employment_status), ''), 'active') = 'active'
        ORDER BY e.name NULLS LAST, e.employee_key
        """,
        (company,),
    )
    rows = [dict(r) if isinstance(r, dict) else {
        "employee_key": r[0],
        "name": r[1],
        "category": r[2],
        "pifss_wage_by_fund": r[3],
    } for r in (cur.fetchall() or [])]

    missing_category: list[dict[str, Any]] = []
    missing_wage: list[dict[str, Any]] = []
    complete = 0
    for row in rows:
        cat = str(row.get("category") or "").strip().lower()
        wage = row.get("pifss_wage_by_fund") or {}
        if isinstance(wage, str):
            try:
                wage = json.loads(wage)
            except Exception:
                wage = {}
        if not isinstance(wage, dict):
            wage = {}
        if not cat or cat not in STATUTORY_CATEGORIES:
            missing_category.append(
                {
                    "employee_key": row.get("employee_key"),
                    "name": row.get("name"),
                    "reason": "category_required",
                }
            )
            continue
        if cat in ("kuwaiti_national", "gcc_national") and not wage:
            missing_wage.append(
                {
                    "employee_key": row.get("employee_key"),
                    "name": row.get("name"),
                    "category": cat,
                    "reason": "pifss_wage_base_required",
                }
            )
            continue
        complete += 1

    incomplete = len(missing_category) + len(missing_wage)
    return {
        "ok": True,
        "total_with_approved_contracts": len(rows),
        "complete": complete,
        "incomplete": incomplete,
        "missing_category_count": len(missing_category),
        "missing_pifss_wage_count": len(missing_wage),
        "sample_missing_category": missing_category[:limit],
        "sample_missing_pifss_wage": missing_wage[:limit],
        "samples_truncated": incomplete > limit,
        "ops_deep_link": "/dashboard?page=employees",
        "wathefni_owned_rates": True,
        "message_en": (
            f"{incomplete} employee(s) still need statutory classification or PIFSS wage-base facts."
            if incomplete
            else "Statutory input facts are complete for contracted active employees."
        ),
        "message_ar": (
            f"{incomplete} موظفاً ما زالوا بحاجة لتصنيف قانوني أو أساس أجر التأمينات."
            if incomplete
            else "مدخلات التصنيف القانوني مكتملة للموظفين المتعاقدين النشطين."
        ),
    }


def upsert_employee_statutory_inputs(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str | None,
    employee_category: str | None = None,
    pifss_wage_by_fund: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Company-owned classification/wage facts only — never rates."""
    ensure_phase3a_schema(cur)
    company = (company_code or "").upper()
    key = str(employee_key or "").strip()
    if not key:
        return {"ok": False, "error": "employee_key_required"}
    cat = str(employee_category or "").strip().lower() or None
    if cat and cat not in STATUTORY_CATEGORIES:
        return {"ok": False, "error": "invalid_employee_category", "allowed": list(STATUTORY_CATEGORIES)}
    wage = pifss_wage_by_fund if isinstance(pifss_wage_by_fund, dict) else None
    # Reject accidental rate fields
    if wage:
        banned = {"employee_rate", "employer_rate", "percentage", "pct", "rate"}
        if any(str(k).lower() in banned for k in wage.keys()):
            return {
                "ok": False,
                "error": "wathefni_owned_rate_rejected",
                "message_en": "Do not enter PIFSS percentages — OctoHR owns statutory rates. Provide wage amounts by fund only.",
            }

    if cat:
        # Keep employee_identity in sync when the table exists.
        try:
            cur.execute(
                """
                INSERT INTO employee_identity (company_code, employee_key, employee_category, identity_profile, requiredness_policy)
                VALUES (%s,%s,%s,'kuwait_first','{}'::jsonb)
                ON CONFLICT (company_code, employee_key) DO UPDATE
                  SET employee_category=EXCLUDED.employee_category, updated_at=now()
                """,
                (company, key, cat),
            )
        except Exception:
            try:
                cur.execute(
                    """
                    INSERT INTO employee_identity (company_code, employee_key, employee_category)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (company_code, employee_key) DO UPDATE
                      SET employee_category=EXCLUDED.employee_category, updated_at=now()
                    """,
                    (company, key, cat),
                )
            except Exception:
                pass


    cur.execute(
        """
        INSERT INTO payroll_employee_statutory_inputs (
          company_code, employee_key, employee_category, pifss_wage_by_fund, updated_by_phone, updated_at
        ) VALUES (%s,%s,%s,%s::jsonb,%s, now())
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          employee_category=COALESCE(EXCLUDED.employee_category, payroll_employee_statutory_inputs.employee_category),
          pifss_wage_by_fund=CASE
            WHEN EXCLUDED.pifss_wage_by_fund IS NULL OR EXCLUDED.pifss_wage_by_fund = '{}'::jsonb
              THEN payroll_employee_statutory_inputs.pifss_wage_by_fund
            ELSE EXCLUDED.pifss_wage_by_fund
          END,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            key,
            cat,
            json.dumps(wage or {}),
            pyw1.digits_phone(actor_phone) if hasattr(pyw1, "digits_phone") else actor_phone,
        ),
    )
    row = cur.fetchone()
    return {"ok": True, "input": dict(row) if isinstance(row, dict) else None, "reason": reason}


def revoke_employee_allowlist(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    p6.ensure_payroll_production_p6_schema(cur)
    company = (company_code or "").upper()
    key = str(employee_key or "").strip()
    cur.execute(
        """
        UPDATE payroll_mode_a_employee_allowlist
        SET status='revoked', revoked_at=now(), revoked_by_phone=%s, reason=%s
        WHERE company_code=%s AND employee_key=%s AND status='active'
        RETURNING *
        """,
        (pyw1.digits_phone(actor_phone) if hasattr(pyw1, "digits_phone") else actor_phone, str(reason).strip(), company, key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "allowlist_entry_not_found"}
    try:
        p6._record_event(
            cur,
            company_code=company,
            event_type="employee_allowlist_revoke",
            payload={"employee_key": key, "reason": str(reason).strip()},
            actor_phone=actor_phone,
        )
    except Exception:
        pass
    return {"ok": True, "allowlist": dict(row) if isinstance(row, dict) else None}


def search_allowlist_candidates(
    cur: Any,
    *,
    company_code: str,
    q: str = "",
    limit: int = 40,
    offset: int = 0,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    limit_n = max(1, min(int(limit or 40), 100))
    offset_n = max(0, int(offset or 0))
    query = str(q or "").strip()
    like = f"%{query}%"
    cur.execute(
        """
        SELECT e.employee_key, e.name, e.phone,
               EXISTS (
                 SELECT 1 FROM payroll_mode_a_employee_allowlist a
                 WHERE a.company_code=e.company_code AND a.employee_key=e.employee_key AND a.status='active'
               ) AS on_allowlist,
               COUNT(*) OVER() AS total_count
        FROM employees e
        WHERE e.company_code=%s
          AND COALESCE(NULLIF(lower(e.employment_status), ''), 'active') = 'active'
          AND (%s = '' OR e.name ILIKE %s OR e.employee_key ILIKE %s OR COALESCE(e.phone,'') ILIKE %s)
        ORDER BY e.name NULLS LAST, e.employee_key
        LIMIT %s OFFSET %s
        """,
        (company, query, like, like, like, limit_n, offset_n),
    )
    rows = [dict(r) if isinstance(r, dict) else {
        "employee_key": r[0],
        "name": r[1],
        "phone": r[2],
        "on_allowlist": r[3],
        "total_count": r[4],
    } for r in (cur.fetchall() or [])]
    total = int(rows[0].get("total_count") or 0) if rows else 0
    return {
        "ok": True,
        "employees": [
            {
                "employee_key": r.get("employee_key"),
                "name": r.get("name"),
                "phone": r.get("phone"),
                "on_allowlist": bool(r.get("on_allowlist")),
            }
            for r in rows
        ],
        "total_count": total,
        "has_more": offset_n + len(rows) < total,
        "limit": limit_n,
        "offset": offset_n,
    }


def readiness_issues_phase3a(
    cur: Any,
    *,
    company_code: str,
    payroll_mode: str,
    extras: dict[str, Any],
) -> list[dict[str, Any]]:
    """Additive readiness issues for native Mode A. Mode B external skips these."""
    mode = str(payroll_mode or "").lower()
    if mode == "external":
        return []
    issues: list[dict[str, Any]] = []
    if not extras.get("calendar_configured") or not extras.get("weekend_days"):
        issues.append(
            {
                "code": "working_calendar_missing",
                "severity": "blocked",
                "field": "working_calendar",
                "message_en": "Set the company working calendar (working days and weekly rest).",
                "message_ar": "اضبط تقويم العمل للشركة (أيام العمل والراحة الأسبوعية).",
                "how_to_fix": "Choose weekly rest days and optionally seed Kuwait public holidays.",
                "fix_href": FIELD_DEEP_LINKS_3A["working_calendar"],
            }
        )

    gaps = statutory_gap_summary(cur, company_code=company_code, limit=5)
    if gaps.get("incomplete"):
        issues.append(
            {
                "code": "statutory_employee_inputs_incomplete",
                "severity": "attention",
                "field": "employee_statutory_classifications",
                "message_en": gaps.get("message_en"),
                "message_ar": gaps.get("message_ar"),
                "how_to_fix": "Classify employees and provide PIFSS wage bases where required — never type OctoHR rates.",
                "fix_href": FIELD_DEEP_LINKS_3A["employee_statutory_classifications"],
                "count": gaps.get("incomplete"),
                "missing_category_count": gaps.get("missing_category_count"),
                "missing_pifss_wage_count": gaps.get("missing_pifss_wage_count"),
            }
        )
    return issues


def enrich_payroll_setup_phase3a(cur: Any, *, company_code: str, base: dict[str, Any]) -> dict[str, Any]:
    """Merge Phase 3A surfaces onto Phase 2A GET payload."""
    ensure_phase3a_schema(cur)
    company = (company_code or "").upper()
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    extras = parse_setup_extras(settings)
    year = date.today().year
    holidays = list_company_holidays(cur, company_code=company, year=year)
    gaps = statutory_gap_summary(cur, company_code=company)
    variance = p6.get_variance_policy(cur, company_code=company)
    allowlist = p6.list_active_allowlist(cur, company_code=company)

    # Re-merge readiness with Phase 3A issues (Mode B unaffected).
    mode = str(base.get("payroll_mode") or settings.get("payroll_mode") or "")
    extra_issues = readiness_issues_phase3a(cur, company_code=company, payroll_mode=mode, extras=extras)
    readiness = dict(base.get("readiness") or {})
    issues = list(readiness.get("issues") or [])
    # Drop prior 3A codes then re-add
    issues = [i for i in issues if str(i.get("code") or "") not in {
        "working_calendar_missing",
        "statutory_employee_inputs_incomplete",
    }]
    issues.extend(extra_issues)
    if mode == "external":
        issues = [i for i in issues if str(i.get("code") or "") not in {
            "working_calendar_missing",
            "statutory_employee_inputs_incomplete",
        }]
    blockers = [i for i in issues if str(i.get("severity") or "") == "blocked"]
    attention = [i for i in issues if str(i.get("severity") or "") == "attention"]

    # Authoritative entitlement: statutory gaps become blockers.
    ent_state = str((base.get("entitlement") or {}).get("state") or "")
    if mode != "external" and ent_state in getattr(p6, "AUTHORITATIVE_STATES", {"authoritative", "authoritative_allowlisted"}):
        for issue in issues:
            if issue.get("code") == "statutory_employee_inputs_incomplete":
                issue["severity"] = "blocked"
        blockers = [i for i in issues if str(i.get("severity") or "") == "blocked"]

    calendar_ok = mode == "external" or bool(extras.get("calendar_configured") and extras.get("weekend_days"))
    # For display: ok means no blocked issues (authoritative includes statutory).
    display_ok = len(blockers) == 0 and (mode == "external" or calendar_ok)

    readiness["issues"] = issues
    readiness["blockers"] = blockers
    readiness["attention"] = attention
    readiness["ok"] = display_ok
    readiness["phase3a"] = {
        "calendar_ok": calendar_ok,
        "statutory_incomplete": int(gaps.get("incomplete") or 0),
        "authoritative_requires_statutory": True,
    }

    base = dict(base)
    base["phase"] = PHASE
    base["setup_extras"] = extras
    base["working_calendar"] = {
        "weekend_days": extras.get("weekend_days") or [],
        "working_days": extras.get("working_days") or [],
        "configured": bool(extras.get("calendar_configured")),
        "note": extras.get("working_calendar_note") or "",
        "holiday_year": year,
        "holidays": holidays,
        "holiday_count": len(holidays),
        "use_wathefni_public_holiday_pack": extras.get("use_wathefni_public_holiday_pack", True),
        "ownership": {
            "operational_working_calendar": "company",
            "statutory_public_holiday_interpretation": "wathefni",
        },
    }
    base["statutory_inputs"] = gaps
    base["variance_policy"] = {
        "gross_delta_abs": float(variance.get("gross_delta_abs") or 50),
        "net_delta_abs": float(variance.get("net_delta_abs") or 50),
        "gross_delta_pct": float(variance.get("gross_delta_pct") or 0.10),
        "net_delta_pct": float(variance.get("net_delta_pct") or 0.10),
        "flag_component_add_remove": bool(variance.get("flag_component_add_remove", True)),
        "flag_zero_or_negative_net": bool(variance.get("flag_zero_or_negative_net", True)),
        "advisory_only": True,
        "never_rewrites_money": True,
    }
    base["allowlist"] = {
        "active_count": len(allowlist),
        "employees": [
            {
                "employee_key": a.get("employee_key"),
                "reason": a.get("reason"),
                "added_at": str(a.get("added_at") or ""),
            }
            for a in allowlist[:100]
        ],
        "truncated": len(allowlist) > 100,
    }
    base["readiness"] = readiness
    base["ownership"] = {
        **(base.get("ownership") or {}),
        "working_calendar": "setup_console",
        "statutory_classifications": "setup_console_counts_employees_facts",
        "authority_rollout": "setup_console",
        "variance_review": "setup_console",
        "payroll_runs": "operational_payroll",
        "statutory_rates": "wathefni",
    }
    return base


def apply_working_calendar(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None,
    weekend_days: list[str] | None,
    working_calendar_note: str | None = None,
    seed_kuwait_holidays: bool = False,
    holiday_year: int | None = None,
) -> dict[str, Any]:
    ensure_phase3a_schema(cur)
    company = (company_code or "").upper()
    settings = pyw1.ensure_company_settings(cur, company_code=company)
    current = parse_setup_extras(settings)
    weekend = normalize_weekend_days(weekend_days if weekend_days is not None else current.get("weekend_days"))
    if weekend_days is not None and not weekend:
        return {"ok": False, "error": "weekend_days_required", "message_en": "Select at least one weekly rest day."}
    if not weekend:
        weekend = list(DEFAULT_WEEKEND_DAYS)
    current["weekend_days"] = weekend
    current["working_days"] = working_days_from_weekend(weekend)
    current["calendar_configured"] = True
    if working_calendar_note is not None:
        current["working_calendar_note"] = str(working_calendar_note)[:500]
    cur.execute(
        """
        UPDATE payroll_company_settings
        SET setup_extras=%s::jsonb, updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s
        """,
        (
            json.dumps(current),
            pyw1.digits_phone(actor_phone) if hasattr(pyw1, "digits_phone") else actor_phone,
            company,
        ),
    )
    seed_result = None
    if seed_kuwait_holidays:
        seed_result = seed_kuwait_fixed_holidays(cur, company_code=company, year=holiday_year)
        current["use_wathefni_public_holiday_pack"] = True
        cur.execute(
            "UPDATE payroll_company_settings SET setup_extras=%s::jsonb WHERE company_code=%s",
            (json.dumps(current), company),
        )
    # Phase 3B: push rest days into Leave policies + Shifts authority (no second calendar).
    consumer_sync = None
    try:
        import setup_console_modules_phase3b as p3b

        consumer_sync = p3b.sync_calendar_consumers(cur, company, weekend)
    except Exception:
        consumer_sync = {"ok": False, "skipped": True}
    return {"ok": True, "setup_extras": current, "holiday_seed": seed_result, "consumer_sync": consumer_sync}
