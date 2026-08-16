"""Leave Wave 2 — policy & balance correctness (local/staging).

Does NOT enable enforcement (enforced/legal_reviewed remain false).
Does NOT deploy to production or mutate real production balances.
Payroll money calculations remain out of Leave (unpaid is a catalogue/boundary only).

Public-source classifications are recorded in OFFICIAL_SOURCE_MATRIX; unresolved
fields stay legal_reviewed=false and are not guessed.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

LEAVE_POLICY_WAVE2_VERSION = "2.0.0"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
_ON_VALUES = {"1", "true", "yes", "on"}

# --- Official-source verification matrix (do not invent unresolved fields) -----
# Classifications: statutory | configurable_company_policy | payroll_owned | manual | unresolved
OFFICIAL_SOURCE_MATRIX: list[dict[str, Any]] = [
    {
        "field": "annual_days_per_year",
        "value": 30,
        "classification": "statutory",
        "sources": [
            "Kuwait Labour Law No. 6/2010 Art. 70 (private sector)",
            "PAM Know Your Rights advisory (Arab Times 2026-07-28 summary of Art. 70)",
            "Law No. 85/2017 amendments notes (Ogletree / Al Tamimi commentary)",
        ],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "30 paid annual leave days; working-day treatment clarified by Law 85/2017 commentary.",
    },
    {
        "field": "annual_eligibility_months",
        "value": 6,
        "classification": "unresolved",
        "sources": [
            "PAM / Arab Times: Art. 70 — not entitled during first year until ≥6 months",
            "Ogletree 2018 on Law 85/2017: entitlement after six months",
            "HLB HAMT guide: older EN translation cites 9 months — CONFLICT",
            "ops/KUWAIT_PRIVATE_SECTOR_REQUIREMENTS_RESEARCH.md L2: UC",
        ],
        "confidence": "medium",
        "legal_reviewed": False,
        "pack_default": 6,
        "notes": "Pack seeds 6 months to match PAM/Ogletree; 9-month EN conflict remains unresolved — counsel must confirm Arabic Art. 70 before legal_reviewed=true.",
    },
    {
        "field": "annual_excludes_weekends_holidays_sick",
        "value": True,
        "classification": "statutory",
        "sources": [
            "Law No. 85/2017 amending Law 6/2010 (Ogletree 2018): weekends, public holidays, and sick leave days shall not count toward annual leave",
        ],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "Chargeable-day calc excludes configured weekend rest + public holidays. Sick overlap exclusion is policy-aware, not a payroll wage calc.",
    },
    {
        "field": "weekend_days_default",
        "value": ["fri", "sat"],
        "classification": "configurable_company_policy",
        "sources": [
            "Law provides weekly rest; exact weekend pair is employer calendar / sector practice",
            "ops/KUWAIT_PRIVATE_SECTOR_REQUIREMENTS_RESEARCH.md H2: employer calendar",
        ],
        "confidence": "medium",
        "legal_reviewed": False,
        "notes": "Default Fri+Sat for KW private pack; companies may override in leave_policies.weekend_days.",
    },
    {
        "field": "sick_tiers_art69",
        "value": [
            {"days": 15, "pay_fraction": 1.0},
            {"days": 10, "pay_fraction": 0.75},
            {"days": 10, "pay_fraction": 0.5},
            {"days": 10, "pay_fraction": 0.25},
            {"days": 30, "pay_fraction": 0.0},
        ],
        "classification": "statutory",
        "sources": [
            "Kuwait Labour Law No. 6/2010 Art. 69 (EN translations / HLB HAMT guide)",
            "ops/KUWAIT_PRIVATE_SECTOR_REQUIREMENTS_RESEARCH.md L3: Medium confidence pending counsel",
        ],
        "confidence": "medium",
        "legal_reviewed": False,
        "notes": "Tier structure stored for observe-only day banding. Pay fractions are NOT applied to Payroll money in Leave.",
    },
    {
        "field": "public_holidays_fixed_gregorian",
        "value": ["New Year (1 Jan)", "National Day (25 Feb)", "Liberation Day (26 Feb)"],
        "classification": "statutory",
        "sources": [
            "Kuwait national observances (National Day 25 Feb; Liberation Day 26 Feb widely observed)",
            "HLB HAMT holiday list (fixed Gregorian items)",
        ],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "Fixed Gregorian holidays seedable. Islamic movable holidays require yearly decree dates — not invented.",
    },
    {
        "field": "public_holidays_islamic_movable",
        "value": None,
        "classification": "manual",
        "sources": [
            "Annual government / PAM holiday decrees for Hijri observances",
            "HLB HAMT lists categories without fixed civil dates",
        ],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "Model supports yearly rows with provenance + review_status=pending_yearly_review. Wave 2 does not invent Eid/Arafa/etc. dates.",
    },
    {
        "field": "carryover_rules",
        "value": {"enabled": False, "max_years": 2, "requires_employer_consent": True},
        "classification": "unresolved",
        "sources": [
            "Secondary guides: accumulate up to 2 years with employer consent; more with mutual consent",
            "Not verified against current Arabic statute in this wave",
        ],
        "confidence": "low",
        "legal_reviewed": False,
        "notes": "Architecture only; carryover writers remain DISABLED until verified.",
    },
    {
        "field": "unpaid_leave",
        "value": "catalogue_boundary_only",
        "classification": "payroll_owned",
        "sources": [
            "Leave catalogue may label unpaid; wage impact is Payroll-owned",
        ],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "Leave never computes unpaid wage deductions or payroll money.",
    },
    {
        "field": "timezone",
        "value": "Asia/Kuwait",
        "classification": "configurable_company_policy",
        "sources": ["Wathefni operational standard for KW tenants"],
        "confidence": "high",
        "legal_reviewed": False,
        "notes": "All Wave 2 as-of / boundary dates use Asia/Kuwait.",
    },
]

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

KUWAIT_PRIVATE_PACK = {
    "pack_code": "kw_private_sector_v2",
    "jurisdiction_code": "KW",
    "worker_category": "private_sector",
    "version": "2.0.0",
    "timezone": "Asia/Kuwait",
    "weekend_days": ["fri", "sat"],
    "exclude_public_holidays": True,
    "carryover_enabled": False,
    "legal_reviewed": False,
    "enforced": False,
    "policies": {
        "annual": {
            "days_per_year": 30,
            "accrual_method": "monthly_accrual",
            "eligibility_months": 6,
            "allow_negative": False,
            "tiers": [],
        },
        "sick": {
            "days_per_year": 0,
            "accrual_method": "none",
            "eligibility_months": 0,
            "allow_negative": False,
            "tiers": [
                {"band": 1, "days": 15, "pay_fraction": 1.0, "label": "full_pay"},
                {"band": 2, "days": 10, "pay_fraction": 0.75, "label": "three_quarter_pay"},
                {"band": 3, "days": 10, "pay_fraction": 0.5, "label": "half_pay"},
                {"band": 4, "days": 10, "pay_fraction": 0.25, "label": "quarter_pay"},
                {"band": 5, "days": 30, "pay_fraction": 0.0, "label": "unpaid_sick_band"},
            ],
        },
        "unpaid": {
            "days_per_year": 0,
            "accrual_method": "none",
            "eligibility_months": 0,
            "allow_negative": False,
            "tiers": [],
            "payroll_boundary": True,
        },
    },
}

FIXED_KW_HOLIDAYS_TEMPLATE: list[dict[str, Any]] = [
    {"month": 1, "day": 1, "name_en": "Gregorian New Year", "name_ar": "رأس السنة الميلادية", "source": "kuwait_fixed_observance"},
    {"month": 2, "day": 25, "name_en": "National Day", "name_ar": "اليوم الوطني", "source": "kuwait_fixed_observance"},
    {"month": 2, "day": 26, "name_en": "Liberation Day", "name_ar": "يوم التحرير", "source": "kuwait_fixed_observance"},
]

SCHEMA_SQL = """
ALTER TABLE leave_balances
  ADD COLUMN IF NOT EXISTS reserved numeric(6,2) NOT NULL DEFAULT 0;

ALTER TABLE public_holidays
  ADD COLUMN IF NOT EXISTS source_provenance text,
  ADD COLUMN IF NOT EXISTS effective_from date,
  ADD COLUMN IF NOT EXISTS effective_to date,
  ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'unreviewed',
  ADD COLUMN IF NOT EXISTS calendar_code text;

CREATE TABLE IF NOT EXISTS leave_policy_packs (
  pack_code text NOT NULL,
  version text NOT NULL,
  jurisdiction_code text NOT NULL,
  worker_category text NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  weekend_days text[] NOT NULL DEFAULT ARRAY['fri','sat'],
  exclude_public_holidays boolean NOT NULL DEFAULT true,
  carryover_enabled boolean NOT NULL DEFAULT false,
  carryover_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  legal_reviewed boolean NOT NULL DEFAULT false,
  enforced boolean NOT NULL DEFAULT false,
  source_matrix jsonb NOT NULL DEFAULT '[]'::jsonb,
  policies jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (pack_code, version)
);

CREATE TABLE IF NOT EXISTS leave_company_policy_bindings (
  company_code text PRIMARY KEY,
  pack_code text NOT NULL,
  pack_version text NOT NULL,
  jurisdiction_code text NOT NULL DEFAULT 'KW',
  worker_category text NOT NULL DEFAULT 'private_sector',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leave_holiday_calendars (
  calendar_code text PRIMARY KEY,
  jurisdiction_code text NOT NULL,
  display_name text NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  yearly_review_status text NOT NULL DEFAULT 'pending_yearly_review',
  last_reviewed_year int,
  source_notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_ledger_reservation_idem
  ON leave_ledger (leave_id, entry_kind)
  WHERE leave_id IS NOT NULL AND entry_kind IN ('reservation','reservation_release');

CREATE TABLE IF NOT EXISTS leave_balance_reconcile_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  leave_type text,
  period_year int,
  ok boolean NOT NULL,
  drift jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def leave_policy_wave2_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_LEAVE_POLICY_WAVE2")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON_VALUES


def kuwait_today_wave2(*, now: datetime | None = None) -> date:
    dt = now or datetime.now(tz=KUWAIT_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KUWAIT_TZ)
    return dt.astimezone(KUWAIT_TZ).date()


def ensure_leave_policy_wave2_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def seed_kuwait_private_policy_pack(cur: Any) -> None:
    pack = KUWAIT_PRIVATE_PACK
    cur.execute(
        """
        INSERT INTO leave_policy_packs (
          pack_code, version, jurisdiction_code, worker_category, timezone,
          weekend_days, exclude_public_holidays, carryover_enabled, carryover_rules,
          legal_reviewed, enforced, source_matrix, policies
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,false,false,%s::jsonb,%s::jsonb)
        ON CONFLICT (pack_code, version) DO UPDATE SET
          source_matrix=EXCLUDED.source_matrix,
          policies=EXCLUDED.policies,
          carryover_enabled=false,
          legal_reviewed=false,
          enforced=false
        """,
        (
            pack["pack_code"],
            pack["version"],
            pack["jurisdiction_code"],
            pack["worker_category"],
            pack["timezone"],
            pack["weekend_days"],
            pack["exclude_public_holidays"],
            False,
            '{"enabled": false, "max_years": 2, "requires_employer_consent": true}',
            __import__("json").dumps(OFFICIAL_SOURCE_MATRIX),
            __import__("json").dumps(pack["policies"]),
        ),
    )
    cur.execute(
        """
        INSERT INTO leave_holiday_calendars (calendar_code, jurisdiction_code, display_name, timezone, yearly_review_status, source_notes)
        VALUES ('kw_public_v2', 'KW', 'Kuwait public holiday calendar', 'Asia/Kuwait', 'pending_yearly_review',
                'Fixed Gregorian observances seeded; Islamic movable dates require yearly decree — not invented')
        ON CONFLICT (calendar_code) DO NOTHING
        """
    )


def bind_company_policy_pack(cur: Any, company_code: str, *, pack_code: str = "kw_private_sector_v2", pack_version: str = "2.0.0") -> None:
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO leave_company_policy_bindings (company_code, pack_code, pack_version, jurisdiction_code, worker_category)
        VALUES (%s,%s,%s,'KW','private_sector')
        ON CONFLICT (company_code) DO UPDATE SET pack_code=EXCLUDED.pack_code, pack_version=EXCLUDED.pack_version, updated_at=now()
        """,
        (company, pack_code, pack_version),
    )


def seed_fixed_kuwait_holidays(cur: Any, company_code: str, *, year: int) -> int:
    """Seed fixed Gregorian KW holidays for a company/year. Islamic dates NOT invented."""
    company = (company_code or "").upper()
    inserted = 0
    for h in FIXED_KW_HOLIDAYS_TEMPLATE:
        d = date(year, h["month"], h["day"])
        cur.execute(
            """
            INSERT INTO public_holidays (
              company_code, holiday_date, name, year, source_provenance,
              effective_from, effective_to, review_status, calendar_code
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,'seeded_fixed', 'kw_public_v2')
            ON CONFLICT (company_code, holiday_date) DO UPDATE SET
              source_provenance=EXCLUDED.source_provenance,
              review_status=EXCLUDED.review_status,
              calendar_code=EXCLUDED.calendar_code
            """,
            (company, d, h["name_en"], year, h["source"], d, d),
        )
        inserted += cur.rowcount or 0
    # Marker rows for movable Islamic holidays awaiting yearly decree
    for name in (
        "Islamic New Year (pending decree)",
        "Isra and Mi'raj (pending decree)",
        "Eid al-Fitr (pending decree)",
        "Arafa Day (pending decree)",
        "Eid al-Adha (pending decree)",
        "Prophet's Birthday (pending decree)",
    ):
        # Store review placeholder without a concrete holiday_date collision:
        # use leave_holiday_calendars notes only — do not insert fake dates.
        pass
    cur.execute(
        """
        UPDATE leave_holiday_calendars
        SET yearly_review_status='pending_yearly_review', last_reviewed_year=NULL
        WHERE calendar_code='kw_public_v2'
        """
    )
    return inserted


def chargeable_leave_days_kuwait(
    start_date: Any,
    end_date: Any,
    *,
    weekend_days: Any,
    holiday_dates: Any,
) -> Decimal:
    """Deterministic inclusive chargeable days (no half-days)."""
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date[:10])
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date[:10])
    if not start_date or not end_date or end_date < start_date:
        return Decimal("0")
    weekend = {str(w).lower() for w in (weekend_days or [])}
    holidays = set(holiday_dates or set())
    total = Decimal("0")
    cur_d = start_date
    while cur_d <= end_date:
        if WEEKDAY_NAMES[cur_d.weekday()] not in weekend and cur_d not in holidays:
            total += Decimal("1")
        cur_d = cur_d + timedelta(days=1)
    return total


def sick_tier_breakdown(chargeable_days: Decimal, tiers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Allocate chargeable sick days across Art.69-style bands (observe-only; no pay calc)."""
    remaining = Decimal(str(chargeable_days or 0))
    out: list[dict[str, Any]] = []
    if remaining <= 0:
        return out
    for tier in tiers or []:
        band_days = Decimal(str(tier.get("days") or 0))
        if band_days <= 0:
            continue
        take = min(remaining, band_days)
        if take > 0:
            out.append(
                {
                    "band": tier.get("band"),
                    "label": tier.get("label"),
                    "days": float(take),
                    "pay_fraction": tier.get("pay_fraction"),
                    "payroll_owned": True,
                }
            )
            remaining -= take
        if remaining <= 0:
            break
    if remaining > 0:
        out.append({"band": "overflow", "label": "beyond_pack_tiers", "days": float(remaining), "pay_fraction": None, "payroll_owned": True})
    return out


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(KUWAIT_TZ).date() if value.tzinfo else value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def holiday_dates_for_range(cur: Any, company_code: str, start_date: Any, end_date: Any) -> set[date]:
    start = _as_date(start_date)
    end = _as_date(end_date)
    if not start or not end:
        return set()
    cur.execute(
        """
        SELECT holiday_date FROM public_holidays
        WHERE company_code=%s AND holiday_date BETWEEN %s AND %s
          AND coalesce(review_status,'') <> 'invalid'
        """,
        ((company_code or "").upper(), start, end),
    )
    return {r["holiday_date"] for r in cur.fetchall()}


def available_balance(cur: Any, *, company_code: str, employee_key: str, leave_type: str, period_year: int) -> dict[str, Decimal]:
    cur.execute(
        """
        SELECT current_balance, reserved FROM leave_balances
        WHERE company_code=%s AND employee_key=%s AND leave_type=%s AND period_year=%s
        """,
        (company_code, employee_key, leave_type, period_year),
    )
    row = cur.fetchone()
    if not row:
        return {"current_balance": Decimal("0"), "reserved": Decimal("0"), "available": Decimal("0")}
    bal = Decimal(str(row["current_balance"] or 0))
    reserved = Decimal(str(row["reserved"] or 0))
    return {"current_balance": bal, "reserved": reserved, "available": bal - reserved}


def recompute_balance_with_reservations(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    leave_type: str,
    period_year: int,
    entitlement_days: Decimal | None = None,
    can_take_from: Any = None,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          COALESCE(SUM(days) FILTER (WHERE entry_kind='accrual'),0) AS accrued,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='consume'),0) AS consumed,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='reversal'),0) AS reversed,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='adjustment'),0) AS adjusted,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='carryover'),0) AS carried_in,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='reservation'),0) AS reserved_sum,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='reservation_release'),0) AS released_sum
        FROM leave_ledger
        WHERE company_code=%s AND employee_key=%s AND leave_type=%s
          AND (period IS NULL OR left(period,4)=%s)
        """,
        (company_code, employee_key, leave_type, str(period_year)),
    )
    agg = dict(cur.fetchone() or {})
    accrued = Decimal(str(agg.get("accrued") or 0))
    consumed = Decimal(str(agg.get("consumed") or 0))
    reversed_ = Decimal(str(agg.get("reversed") or 0))
    adjusted = Decimal(str(agg.get("adjusted") or 0))
    carried_in = Decimal(str(agg.get("carried_in") or 0))
    reserved = Decimal(str(agg.get("reserved_sum") or 0)) - Decimal(str(agg.get("released_sum") or 0))
    if reserved < 0:
        reserved = Decimal("0")
    net_consumed = consumed - reversed_
    if entitlement_days is None:
        entitlement_days = Decimal("0")
    current_balance = carried_in + accrued + adjusted - net_consumed
    cur.execute(
        """
        INSERT INTO leave_balances
          (company_code, employee_key, leave_type, period_year, entitlement_days,
           accrued_to_date, consumed, adjusted, carried_in, current_balance, reserved, can_take_from, as_of)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (company_code, employee_key, leave_type, period_year) DO UPDATE SET
          entitlement_days=EXCLUDED.entitlement_days,
          accrued_to_date=EXCLUDED.accrued_to_date,
          consumed=EXCLUDED.consumed,
          adjusted=EXCLUDED.adjusted,
          carried_in=EXCLUDED.carried_in,
          current_balance=EXCLUDED.current_balance,
          reserved=EXCLUDED.reserved,
          can_take_from=COALESCE(EXCLUDED.can_take_from, leave_balances.can_take_from),
          as_of=now()
        """,
        (
            company_code,
            employee_key,
            leave_type,
            period_year,
            entitlement_days,
            accrued,
            net_consumed,
            adjusted,
            carried_in,
            current_balance,
            reserved,
            can_take_from,
        ),
    )
    return {
        "leave_type": leave_type,
        "period_year": period_year,
        "entitlement_days": float(entitlement_days),
        "accrued_to_date": float(accrued),
        "consumed": float(net_consumed),
        "reserved": float(reserved),
        "available": float(current_balance - reserved),
        "current_balance": float(current_balance),
    }


def reserve_leave_balance(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any],
    actor_phone: str | None = None,
    lock: bool = True,
) -> dict[str, Any]:
    """Pending reservation. Observe-only: never flips enforced. Prevents double-reserve of available."""
    leave_type = str(leave.get("leave_type") or "")
    if leave_type == "unpaid" or policy.get("payroll_boundary"):
        return {"ok": True, "skipped": True, "reason": "unpaid_payroll_boundary"}
    employee_key = str(leave.get("employee_key") or "")
    leave_id = leave.get("leave_id")
    start = _as_date(leave.get("start_date"))
    end = _as_date(leave.get("end_date"))
    if not employee_key or not leave_id or not start or not end:
        return {"ok": False, "error": "invalid_leave_for_reservation"}
    holidays = holiday_dates_for_range(cur, company_code, start, end) if policy.get("exclude_public_holidays") else set()
    days = chargeable_leave_days_kuwait(start, end, weekend_days=policy.get("weekend_days"), holiday_dates=holidays)
    if days <= 0:
        return {"ok": True, "skipped": True, "reason": "zero_chargeable_days", "days": 0}
    year = start.year
    if lock:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"leave-res:{company_code}:{employee_key}:{leave_type}:{year}",),
        )
    avail = available_balance(cur, company_code=company_code, employee_key=employee_key, leave_type=leave_type, period_year=year)
    # Sick (and other non-accruing tiered types) track chargeable bands observe-only;
    # they are not gated on an accrued pool. Annual/other accrued types cannot overspend reserved.
    accrual_method = str(policy.get("accrual_method") or "").strip().lower()
    balance_gated = accrual_method not in {"", "none"} and leave_type != "sick"
    insufficient = (
        balance_gated
        and days > avail["available"]
        and not bool(policy.get("allow_negative"))
    )
    if insufficient:
        # Observe-only: do not overspend reserved pool; leave request may still exist.
        return {
            "ok": True,
            "reserved": False,
            "insufficient_balance_observe": True,
            "days": float(days),
            "available_before": float(avail["available"]),
            "balances_enforced": False,
            "legal_reviewed": False,
        }
    period = f"{start.year}-{start.month:02d}"
    tiers = sick_tier_breakdown(days, policy.get("tiers") if leave_type == "sick" else None)
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period, leave_id,
          observe_only, tier_breakdown, actor_phone, reason
        ) VALUES (%s,%s,%s,'reservation',%s,%s,%s,true,%s::jsonb,%s,%s)
        ON CONFLICT (leave_id, entry_kind) WHERE leave_id IS NOT NULL AND entry_kind IN ('reservation','reservation_release') DO NOTHING
        """,
        (
            company_code,
            employee_key,
            leave_type,
            days,
            period,
            leave_id,
            __import__("json").dumps(tiers),
            actor_phone,
            "wave2 pending reservation",
        ),
    )
    posted = (cur.rowcount or 0) > 0
    ent = Decimal(str(policy.get("days_per_year") or 0))
    bal = recompute_balance_with_reservations(
        cur, company_code=company_code, employee_key=employee_key, leave_type=leave_type, period_year=year, entitlement_days=ent
    )
    return {
        "ok": True,
        "reserved": posted,
        "days": float(days),
        "insufficient_balance_observe": False,
        "balance": bal,
        "tier_breakdown": tiers,
        "balances_enforced": False,
        "legal_reviewed": False,
    }


def release_leave_reservation(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any] | None = None,
    actor_phone: str | None = None,
    reason: str = "reservation_release",
) -> dict[str, Any]:
    leave_id = leave.get("leave_id")
    employee_key = str(leave.get("employee_key") or "")
    leave_type = str(leave.get("leave_type") or "")
    start = _as_date(leave.get("start_date")) or kuwait_today_wave2()
    if not leave_id or not employee_key:
        return {"ok": False, "error": "invalid_leave"}
    # Find open reservation days
    cur.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days ELSE 0 END),0)
             - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days ELSE 0 END),0) AS open_days
        FROM leave_ledger WHERE leave_id=%s AND entry_kind IN ('reservation','reservation_release')
        """,
        (leave_id,),
    )
    open_days = Decimal(str(dict(cur.fetchone() or {}).get("open_days") or 0))
    if open_days <= 0:
        return {"ok": True, "released": False, "reason": "no_open_reservation"}
    period = f"{start.year}-{start.month:02d}"
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period, leave_id,
          observe_only, actor_phone, reason
        ) VALUES (%s,%s,%s,'reservation_release',%s,%s,%s,true,%s,%s)
        ON CONFLICT (leave_id, entry_kind) WHERE leave_id IS NOT NULL AND entry_kind IN ('reservation','reservation_release') DO NOTHING
        """,
        (company_code, employee_key, leave_type, open_days, period, leave_id, actor_phone, reason),
    )
    ent = Decimal(str((policy or {}).get("days_per_year") or 0))
    bal = recompute_balance_with_reservations(
        cur, company_code=company_code, employee_key=employee_key, leave_type=leave_type, period_year=start.year, entitlement_days=ent
    )
    return {"ok": True, "released": True, "days": float(open_days), "balance": bal}


def consume_from_reservation(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Approve path: release reservation then post consume exactly once (idempotent)."""
    leave_type = str(leave.get("leave_type") or "")
    if leave_type == "unpaid" or policy.get("payroll_boundary"):
        return {"ok": True, "skipped": True, "reason": "unpaid_payroll_boundary"}
    release_leave_reservation(
        cur, company_code=company_code, leave=leave, policy=policy, actor_phone=actor_phone, reason="converted_to_consume"
    )
    employee_key = str(leave.get("employee_key") or "")
    leave_id = leave.get("leave_id")
    start = _as_date(leave.get("start_date"))
    end = _as_date(leave.get("end_date"))
    if not start or not end or not leave_id:
        return {"ok": False, "error": "invalid_leave"}
    holidays = holiday_dates_for_range(cur, company_code, start, end) if policy.get("exclude_public_holidays") else set()
    days = chargeable_leave_days_kuwait(start, end, weekend_days=policy.get("weekend_days"), holiday_dates=holidays)
    if days <= 0:
        return {"ok": True, "skipped": True, "reason": "zero_chargeable_days"}
    tiers = sick_tier_breakdown(days, policy.get("tiers") if leave_type == "sick" else None)
    period = f"{start.year}-{start.month:02d}"
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period, leave_id,
          observe_only, tier_breakdown, actor_phone, reason
        ) VALUES (%s,%s,%s,'consume',%s,%s,%s,true,%s::jsonb,%s,%s)
        ON CONFLICT (leave_id, entry_kind) WHERE leave_id IS NOT NULL AND entry_kind IN ('consume','reversal') DO NOTHING
        """,
        (
            company_code,
            employee_key,
            leave_type,
            days,
            period,
            leave_id,
            __import__("json").dumps(tiers),
            actor_phone,
            "wave2 approve consumption",
        ),
    )
    posted = (cur.rowcount or 0) > 0
    bal = recompute_balance_with_reservations(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        leave_type=leave_type,
        period_year=start.year,
        entitlement_days=Decimal(str(policy.get("days_per_year") or 0)),
    )
    return {"ok": True, "consumed": posted, "days": float(days), "tier_breakdown": tiers, "balance": bal}


def reverse_consumption(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    leave_type = str(leave.get("leave_type") or "")
    employee_key = str(leave.get("employee_key") or "")
    leave_id = leave.get("leave_id")
    start = _as_date(leave.get("start_date"))
    end = _as_date(leave.get("end_date"))
    if not start or not end or not leave_id:
        return {"ok": False, "error": "invalid_leave"}
    holidays = holiday_dates_for_range(cur, company_code, start, end) if policy.get("exclude_public_holidays") else set()
    days = chargeable_leave_days_kuwait(start, end, weekend_days=policy.get("weekend_days"), holiday_dates=holidays)
    if days <= 0:
        return {"ok": True, "skipped": True}
    period = f"{start.year}-{start.month:02d}"
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period, leave_id,
          observe_only, actor_phone, reason
        ) VALUES (%s,%s,%s,'reversal',%s,%s,%s,true,%s,%s)
        ON CONFLICT (leave_id, entry_kind) WHERE leave_id IS NOT NULL AND entry_kind IN ('consume','reversal') DO NOTHING
        """,
        (company_code, employee_key, leave_type, days, period, leave_id, actor_phone, "wave2 cancel reversal"),
    )
    bal = recompute_balance_with_reservations(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        leave_type=leave_type,
        period_year=start.year,
        entitlement_days=Decimal(str(policy.get("days_per_year") or 0)),
    )
    return {"ok": True, "reversed": True, "days": float(days), "balance": bal}


def reconcile_ledger_to_balances(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    leave_type: str | None = None,
    period_year: int | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    year = period_year or kuwait_today_wave2().year
    params: list[Any] = [company, str(year)]
    where = ["company_code=%s", "(period IS NULL OR left(period,4)=%s)"]
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    if leave_type:
        where.append("leave_type=%s")
        params.append(leave_type)
    cur.execute(
        f"""
        SELECT employee_key, leave_type,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='accrual'),0) AS accrued,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='consume'),0)
            - COALESCE(SUM(days) FILTER (WHERE entry_kind='reversal'),0) AS consumed,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='adjustment'),0) AS adjusted,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='carryover'),0) AS carried_in,
          COALESCE(SUM(days) FILTER (WHERE entry_kind='reservation'),0)
            - COALESCE(SUM(days) FILTER (WHERE entry_kind='reservation_release'),0) AS reserved
        FROM leave_ledger
        WHERE {' AND '.join(where)}
        GROUP BY employee_key, leave_type
        """,
        params,
    )
    drifts: list[dict[str, Any]] = []
    for row in cur.fetchall():
        d = dict(row)
        expected_balance = (
            Decimal(str(d["carried_in"]))
            + Decimal(str(d["accrued"]))
            + Decimal(str(d["adjusted"]))
            - Decimal(str(d["consumed"]))
        )
        expected_reserved = max(Decimal(str(d["reserved"])), Decimal("0"))
        cur.execute(
            """
            SELECT current_balance, reserved FROM leave_balances
            WHERE company_code=%s AND employee_key=%s AND leave_type=%s AND period_year=%s
            """,
            (company, d["employee_key"], d["leave_type"], year),
        )
        bal = cur.fetchone()
        if not bal:
            drifts.append({"employee_key": d["employee_key"], "leave_type": d["leave_type"], "error": "missing_balance_row"})
            continue
        got_bal = Decimal(str(bal["current_balance"] or 0))
        got_res = Decimal(str(bal["reserved"] or 0))
        if got_bal != expected_balance or got_res != expected_reserved:
            drifts.append(
                {
                    "employee_key": d["employee_key"],
                    "leave_type": d["leave_type"],
                    "expected_balance": float(expected_balance),
                    "got_balance": float(got_bal),
                    "expected_reserved": float(expected_reserved),
                    "got_reserved": float(got_res),
                }
            )
    ok = len(drifts) == 0
    cur.execute(
        """
        INSERT INTO leave_balance_reconcile_runs (company_code, employee_key, leave_type, period_year, ok, drift)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (company, employee_key, leave_type, year, ok, __import__("json").dumps(drifts)),
    )
    return {"ok": ok, "drifts": drifts, "period_year": year}


def carryover_enabled(pack_or_policy: dict[str, Any] | None = None) -> bool:
    """Hard-disabled unless an explicitly verified pack flips the flag (Wave 2 keeps false)."""
    if not pack_or_policy:
        return False
    return bool(pack_or_policy.get("carryover_enabled")) and bool(pack_or_policy.get("legal_reviewed"))
