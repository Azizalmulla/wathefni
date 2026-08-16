"""Leave Wave 2 / 2B — policy & balance correctness (local/staging).

Wave 2B closes normal-use Kuwait public-policy questions from Official Gazette /
MOJ Arabic text and prepares a synthetic production canary.

Does NOT enable enforcement (enforced/legal_reviewed remain false).
Does NOT deploy to production or mutate real production balances.
Payroll money calculations remain out of Leave.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

LEAVE_POLICY_WAVE2_VERSION = "2.1.0"
LEAVE_POLICY_WAVE2B_VERSION = "2.1.0"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
_ON_VALUES = {"1", "true", "yes", "on"}

# Archived Official Gazette Law 85/2017 (الكويت اليوم 1348) SHA-256
LAW_85_2017_GAZETTE_SHA256 = "f6f6cb68e4210649b89036786e0017b40737943dd66eb4f7c5e78b9f9df72448"
MOJ_LAW_6_2010_PDF_SHA256 = "20eac58834489098d86271cfc6df9926adfe3fcc9607c47531247e6a56d3f326"

# Statuses usable in observe chargeable-day exclusion
HOLIDAY_OBSERVE_OK = frozenset({"seeded_fixed", "approved"})
# Enforced path requires approved calendar year + approved/seeded_fixed holiday rows only
HOLIDAY_ENFORCED_OK = frozenset({"seeded_fixed", "approved"})

PRODUCT_COPY = {
    "disclaimer_en": (
        "Leave figures reflect Kuwait private-sector Labour Law research for software operation. "
        "Wathefni does not provide legal advice and does not claim automatic legal compliance. "
        "Balance enforcement is off until counsel review and an explicit product flip."
    ),
    "disclaimer_ar": (
        "أرقام الإجازات مبنية على بحث قانون العمل للقطاع الأهلي لتشغيل البرمجيات. "
        "وثفني لا تقدّم استشارة قانونية ولا تدّعي الامتثال التلقائي. "
        "إنفاذ الأرصدة متوقف حتى مراجعة قانونية وتفعيل صريح."
    ),
    "eligibility_rule_en": (
        "Annual leave: at least 30 paid working days per year; first-year leave may be taken "
        "after 6 months of service (Law 6/2010 Art. 70 as amended by Law 85/2017)."
    ),
    "payroll_boundary_en": (
        "Leave records day bands and paid/unpaid classification inputs only. "
        "Payroll owns monetary values and salary fractions."
    ),
    "holiday_contract_en": (
        "Fixed Gregorian holidays may be versioned with provenance. "
        "Islamic/decree holidays require official yearly announcement load, review, and approval. "
        "Unreviewed dates fail closed for enforced calculations."
    ),
}

# --- Official-source verification matrix (article-level; do not invent) --------
# Classifications: statutory | configurable_company_policy | payroll_owned | manual | unresolved
OFFICIAL_SOURCE_MATRIX: list[dict[str, Any]] = [
    {
        "field": "annual_days_per_year",
        "value": 30,
        "unit": "working_days",
        "classification": "statutory",
        "article": "Law 6/2010 Art. 70 as amended by Law 85/2017",
        "arabic_excerpt": "إجازة سنوية لا تقل عن ثلاثين يوم عمل مدفوعة الأجر",
        "sources": [
            f"Kuwait Today (الكويت اليوم) Issue 1348, 2017-07-09 — Law 85/2017 Art.1 replacing Art.70 (sha256:{LAW_85_2017_GAZETTE_SHA256})",
            f"MOJ Arabic PDF Law 6/2010 (original pre-amendment text; sha256:{MOJ_LAW_6_2010_PDF_SHA256})",
            "ILO NATLEX KWT-2010-L-83616 (secondary index; notes Law 85/2017 amendment)",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Amended text: no less than thirty paid working days (يوم عمل).",
    },
    {
        "field": "annual_eligibility_months",
        "value": 6,
        "classification": "statutory",
        "article": "Law 6/2010 Art. 70 as amended by Law 85/2017",
        "arabic_excerpt": "بعد قضائه ستة أشهر على الأقل في خدمة صاحب العمل",
        "resolution": {
            "final_product_rule_months": 6,
            "obsolete_figure_months": 9,
            "obsolete_source": "Original Law 6/2010 Art.70 Arabic (pre-amendment): تسعة أشهر",
            "why_obsolete": "Law 85/2017 Art.1 expressly replaces Art.70; gazette text uses ستة أشهر. Nine-month figure is the superseded original wording / unamended EN reprints — not a different entitlement.",
            "gazette": "Kuwait Today 1348 / 2017-07-09",
            "source_sha256": LAW_85_2017_GAZETTE_SHA256,
        },
        "sources": [
            f"Official Gazette Law 85/2017 replacing Art.70 (sha256:{LAW_85_2017_GAZETTE_SHA256})",
            "PAM Know Your Rights republished summary (Arab Times 2026-07-28) — aligns with 6 months",
            "Ogletree/Al Tamimi 2018 secondary commentary — aligns with 6 months",
            "HLB/older EN reprints citing 9 months — obsolete relative to Law 85/2017",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "pack_default": 6,
        "notes": "Conflict closed at public-source level. Product still legal_reviewed=false until counsel sign-off for enforcement.",
    },
    {
        "field": "annual_excludes_weekends_holidays_sick",
        "value": True,
        "classification": "statutory",
        "article": "Law 6/2010 Art. 70 as amended by Law 85/2017",
        "arabic_excerpt": "ولا تحسب ضمن الإجازة السنوية أيام العطل الأسبوعية والعطل الرسمية وأيام الإجازات المرضية الواقعة خلالها",
        "sources": [
            f"Official Gazette Law 85/2017 Art.70 (sha256:{LAW_85_2017_GAZETTE_SHA256})",
            "Explanatory memo to Law 85/2017 (same gazette) — weekly rest days during leave not counted",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Chargeable-day calc excludes configured weekly rest + public holidays. Sick-day overlap exclusion is day accounting, not a payroll wage calc.",
    },
    {
        "field": "weekend_days_default",
        "value": ["fri", "sat"],
        "classification": "configurable_company_policy",
        "article": "Art.70 references العطل الأسبوعية without naming Fri/Sat",
        "sources": [
            "Law 85/2017 Art.70 (weekly rest days excluded; pair not prescribed)",
            "Employer calendar / sector practice",
        ],
        "confidence": "medium",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Default Fri+Sat for KW private pack; companies may override leave_policies.weekend_days.",
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
        "article": "Law 6/2010 Art. 69",
        "arabic_excerpt": "خمسة عشر يوما بأجر كامل … ثلاثون يوما من دون أجر",
        "sources": [
            "Consolidated Arabic Art.69 (lawskw / mesferlaw republications of Law 6/2010)",
            f"MOJ Law 6/2010 PDF (sha256:{MOJ_LAW_6_2010_PDF_SHA256}) — original statute article present",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Tier day structure is statutory. Pay fractions are Payroll-owned monetary application — Leave stores classification inputs only.",
    },
    {
        "field": "annual_leave_cash_settlement",
        "value": "on_contract_end_for_accumulated_days",
        "classification": "payroll_owned",
        "article": "Law 6/2010 Art. 73",
        "arabic_excerpt": "مقابل نقدي لأيام إجازاته السنوية المجتمعة في حالة انتهاء عقده",
        "sources": ["Law 6/2010 Art.73 Arabic"],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Leave may flag settlement-due days; cash amount is Payroll-owned.",
    },
    {
        "field": "annual_leave_pay_before_taking",
        "value": "employer_pays_leave_wage_before_start",
        "classification": "payroll_owned",
        "article": "Law 6/2010 Art. 71",
        "sources": ["Law 6/2010 Art.71 Arabic"],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Timing of leave wage payment is Payroll/employer process — out of Leave money calc.",
    },
    {
        "field": "public_holidays_fixed_gregorian",
        "value": ["New Year (1 Jan)", "National Day (25 Feb)", "Liberation Day (26 Feb)"],
        "classification": "statutory",
        "sources": [
            "Kuwait national observances (National Day 25 Feb; Liberation Day 26 Feb)",
            "Versioned with source_provenance on public_holidays rows",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Fixed Gregorian holidays seedable with provenance. Still subject to yearly calendar approval under enforced mode.",
    },
    {
        "field": "public_holidays_islamic_movable",
        "value": None,
        "classification": "manual",
        "sources": [
            "Annual Official Gazette / PAM / Council of Ministers holiday decrees",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "Must be loaded from official yearly announcements. Never invent dates. Unreviewed → fail closed when enforced.",
    },
    {
        "field": "carryover_rules",
        "value": {
            "enabled": False,
            "max_years_without_extra_consent": 2,
            "more_than_two_years_requires_mutual_consent": True,
            "invented_expiry_days": None,
        },
        "classification": "statutory",
        "article": "Law 6/2010 Art. 72",
        "arabic_excerpt": "تجميع إجازاته بما لا يزيد على إجازة سنتين … ويجوز موافقة الطرفين تجميع … لأكثر من سنتين",
        "sources": ["Law 6/2010 Art.72 Arabic"],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": (
            "Public-law boundary verified: accumulate up to two years' leave; more only with mutual consent. "
            "No statutory invented day-expiry beyond that boundary. Product writers remain DISABLED "
            "(carryover_enabled=false) until an enforcement-ready implementation of consent rules."
        ),
    },
    {
        "field": "unpaid_leave",
        "value": "employer_may_grant_special_unpaid_on_request",
        "classification": "configurable_company_policy",
        "article": "Law 6/2010 Art. 79",
        "arabic_excerpt": "إجازة خاصة من دون أجر خلاف الإجازات المشار إليها",
        "sources": [
            "Law 6/2010 Art.79 — discretionary special unpaid leave on worker request",
            "Art.69 unpaid sick band and Art.24 unpaid childcare are separate statutory bands",
        ],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "No statutory universal unpaid-day bank. Catalogue type is company-configurable; wage impact Payroll-owned.",
    },
    {
        "field": "timezone",
        "value": "Asia/Kuwait",
        "classification": "configurable_company_policy",
        "sources": ["Wathefni operational standard for KW tenants"],
        "confidence": "high",
        "public_source_verified": True,
        "legal_reviewed": False,
        "notes": "All Wave 2/2B as-of / boundary dates use Asia/Kuwait.",
    },
]

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

KUWAIT_PRIVATE_PACK = {
    "pack_code": "kw_private_sector_v2",
    "jurisdiction_code": "KW",
    "worker_category": "private_sector",
    "version": "2.1.0",
    "timezone": "Asia/Kuwait",
    "weekend_days": ["fri", "sat"],
    "exclude_public_holidays": True,
    "carryover_enabled": False,
    "carryover_rules": {
        "max_years_without_extra_consent": 2,
        "more_than_two_years_requires_mutual_consent": True,
        "invented_expiry_days": None,
        "writers_enabled": False,
        "article": "Law 6/2010 Art.72",
    },
    "public_source_verified": True,
    "legal_reviewed": False,
    "enforced": False,
    "eligibility_resolution": "law_85_2017_art70_six_months",
    "policies": {
        "annual": {
            "days_per_year": 30,
            "day_basis": "working_days",
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
            "article": "Law 6/2010 Art.79 discretionary special unpaid",
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

CREATE TABLE IF NOT EXISTS leave_holiday_year_versions (
  calendar_code text NOT NULL,
  year int NOT NULL,
  version int NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'draft',
  source_announcement_ref text,
  source_url text,
  source_sha256 text,
  approved_by text,
  approved_at timestamptz,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (calendar_code, year, version),
  CONSTRAINT leave_holiday_year_status_chk
    CHECK (status IN ('draft','pending_review','approved','superseded','rejected'))
);

CREATE TABLE IF NOT EXISTS leave_holiday_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  calendar_code text,
  year int,
  holiday_date date,
  action text NOT NULL,
  actor text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
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
            '{"enabled": false, "max_years_without_extra_consent": 2, "more_than_two_years_requires_mutual_consent": true, "invented_expiry_days": null, "writers_enabled": false, "article": "Law 6/2010 Art.72"}',
            __import__("json").dumps(OFFICIAL_SOURCE_MATRIX),
            __import__("json").dumps(pack["policies"]),
        ),
    )
    cur.execute(
        """
        INSERT INTO leave_holiday_calendars (calendar_code, jurisdiction_code, display_name, timezone, yearly_review_status, source_notes)
        VALUES ('kw_public_v2', 'KW', 'Kuwait public holiday calendar', 'Asia/Kuwait', 'pending_yearly_review',
                'Fixed Gregorian observances seeded; Islamic movable dates require yearly Official Gazette/PAM decree — not invented. Wave2B fail-closed when enforced.')
        ON CONFLICT (calendar_code) DO UPDATE SET
          source_notes=EXCLUDED.source_notes,
          yearly_review_status=COALESCE(leave_holiday_calendars.yearly_review_status, 'pending_yearly_review')
        """
    )


def bind_company_policy_pack(cur: Any, company_code: str, *, pack_code: str = "kw_private_sector_v2", pack_version: str = "2.1.0") -> None:
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
    # Year version row for fixed Gregorian seed — Islamic still pending_review
    cur.execute(
        """
        INSERT INTO leave_holiday_year_versions (
          calendar_code, year, version, status, source_announcement_ref, notes
        ) VALUES (
          'kw_public_v2', %s, 1, 'pending_review',
          'fixed_gregorian_seed_only',
          'Fixed Gregorian seeded; Islamic/decree holidays must be loaded from Official Gazette/PAM yearly announcement before status=approved'
        )
        ON CONFLICT (calendar_code, year, version) DO NOTHING
        """,
        (year,),
    )
    cur.execute(
        """
        INSERT INTO leave_holiday_audit (calendar_code, year, action, actor, payload)
        VALUES ('kw_public_v2', %s, 'seed_fixed_gregorian', 'wave2b', %s::jsonb)
        """,
        (year, __import__("json").dumps({"inserted": inserted, "islamic": "not_invented"})),
    )
    cur.execute(
        """
        UPDATE leave_holiday_calendars
        SET yearly_review_status='pending_yearly_review', last_reviewed_year=NULL
        WHERE calendar_code='kw_public_v2'
        """
    )
    return inserted


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


def holiday_year_version_status(cur: Any, *, calendar_code: str, year: int) -> str | None:
    cur.execute(
        """
        SELECT status FROM leave_holiday_year_versions
        WHERE calendar_code=%s AND year=%s
        ORDER BY version DESC LIMIT 1
        """,
        (calendar_code, year),
    )
    row = cur.fetchone()
    return str(row["status"]) if row else None


def ensure_holiday_calendar_for_enforced(
    cur: Any,
    *,
    start_date: Any,
    end_date: Any,
    calendar_code: str = "kw_public_v2",
) -> dict[str, Any]:
    """Fail closed for enforced chargeable-day calculations.

    Observe-only callers must not require approved yearly Islamic calendars.
    Enforced callers fail if any spanned year lacks status=approved, or if the
    date range contains holiday rows that are not seeded_fixed/approved.
    """
    start = _as_date(start_date)
    end = _as_date(end_date)
    if not start or not end:
        return {"ok": False, "error": "invalid_date_range", "fail_closed": True}
    years = list(range(start.year, end.year + 1))
    for y in years:
        status = holiday_year_version_status(cur, calendar_code=calendar_code, year=y)
        if status != "approved":
            return {
                "ok": False,
                "error": "holiday_year_not_approved",
                "fail_closed": True,
                "year": y,
                "status": status or "missing",
                "message": PRODUCT_COPY["holiday_contract_en"],
            }
    cur.execute(
        """
        SELECT holiday_date, review_status FROM public_holidays
        WHERE calendar_code=%s AND holiday_date BETWEEN %s AND %s
        """,
        (calendar_code, start, end),
    )
    bad = []
    for r in cur.fetchall():
        st = str(dict(r).get("review_status") or "unreviewed")
        if st not in HOLIDAY_ENFORCED_OK:
            bad.append({"holiday_date": str(dict(r)["holiday_date"]), "review_status": st})
    if bad:
        return {
            "ok": False,
            "error": "unreviewed_holiday_dates",
            "fail_closed": True,
            "holidays": bad,
            "message": PRODUCT_COPY["holiday_contract_en"],
        }
    return {"ok": True, "fail_closed": False}


def holiday_dates_for_range(cur: Any, company_code: str, start_date: Any, end_date: Any) -> set[date]:
    start = _as_date(start_date)
    end = _as_date(end_date)
    if not start or not end:
        return set()
    cur.execute(
        """
        SELECT holiday_date, review_status FROM public_holidays
        WHERE company_code=%s AND holiday_date BETWEEN %s AND %s
          AND coalesce(review_status,'') <> 'invalid'
        """,
        ((company_code or "").upper(), start, end),
    )
    out: set[date] = set()
    for r in cur.fetchall():
        d = dict(r)
        status = str(d.get("review_status") or "unreviewed")
        # Observe path: only exclude holidays that are seeded_fixed or approved.
        # Unreviewed/pending never silently reduce chargeable days.
        if status in HOLIDAY_OBSERVE_OK:
            out.add(d["holiday_date"])
    return out


def chargeable_leave_days_kuwait_enforced(
    cur: Any,
    *,
    company_code: str,
    start_date: Any,
    end_date: Any,
    weekend_days: Any,
    enforced: bool,
) -> dict[str, Any]:
    """Chargeable days with optional enforced fail-closed holiday gate."""
    if enforced:
        gate = ensure_holiday_calendar_for_enforced(cur, start_date=start_date, end_date=end_date)
        if not gate.get("ok"):
            return {**gate, "days": None}
    holidays = holiday_dates_for_range(cur, company_code, start_date, end_date)
    days = chargeable_leave_days_kuwait(start_date, end_date, weekend_days=weekend_days, holiday_dates=holidays)
    return {"ok": True, "days": days, "fail_closed": False, "holiday_count": len(holidays)}


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


def chargeable_days_for_leave(
    cur: Any,
    *,
    company_code: str,
    leave: dict[str, Any],
    policy: dict[str, Any],
) -> Decimal:
    """Prefer Wave 3 stored fractional chargeable_days when present; else Kuwait day calc."""
    stored = leave.get("chargeable_days")
    if stored is not None and str(stored).strip() != "":
        try:
            return Decimal(str(stored))
        except Exception:
            pass
    start = _as_date(leave.get("start_date"))
    end = _as_date(leave.get("end_date"))
    if not start or not end:
        return Decimal("0")
    holidays = holiday_dates_for_range(cur, company_code, start, end) if policy.get("exclude_public_holidays") else set()
    return chargeable_leave_days_kuwait(start, end, weekend_days=policy.get("weekend_days"), holiday_dates=holidays)


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
    days = chargeable_days_for_leave(cur, company_code=company_code, leave=leave, policy=policy)
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
        # Observe-only by default. C2 enforcement fail-closed when company entitled.
        try:
            import leave_enforcement_c2 as _enf

            gate = _enf.leave_enforcement_enabled_for_company(cur, company_code)
            if gate.get("ok"):
                return {
                    "ok": False,
                    "error": "insufficient_balance",
                    "reserved": False,
                    "days": float(days),
                    "available_before": float(avail["available"]),
                    "balances_enforced": True,
                    "legal_reviewed": True,
                    "observe_only": False,
                    "phase": "leave_enforcement_c2",
                }
        except Exception:
            pass
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
    days = chargeable_days_for_leave(cur, company_code=company_code, leave=leave, policy=policy)
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
    days = chargeable_days_for_leave(cur, company_code=company_code, leave=leave, policy=policy)
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
    """Hard-disabled unless an explicitly verified pack flips the flag.

    Art.72 public-law boundary is recorded, but writers stay off until
    consent-aware carryover is implemented and legal_reviewed for enforcement.
    """
    if not pack_or_policy:
        return False
    if pack_or_policy.get("carryover_rules", {}).get("writers_enabled") is False:
        return False
    return bool(pack_or_policy.get("carryover_enabled")) and bool(pack_or_policy.get("legal_reviewed"))


def resolved_eligibility_months() -> dict[str, Any]:
    row = next(r for r in OFFICIAL_SOURCE_MATRIX if r["field"] == "annual_eligibility_months")
    return {
        "months": int(row["value"]),
        "confidence": row["confidence"],
        "public_source_verified": bool(row.get("public_source_verified")),
        "legal_reviewed": bool(row.get("legal_reviewed")),
        "resolution": row.get("resolution"),
        "source_sha256": LAW_85_2017_GAZETTE_SHA256,
    }
