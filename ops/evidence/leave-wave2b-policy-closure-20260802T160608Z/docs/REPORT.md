# Leave Wave 2B — Kuwait public-policy closure & production-canary preparation

**Stamp:** `20260802T160608Z`  
**Scope:** local + staging only. **No production deploy. No `enforced=true`. No real balance mutation.**  
**Pack:** `kw_private_sector_v2` **v2.1.0** · module `leave_policy_wave2.py`

Evidence root: `ops/evidence/leave-wave2b-policy-closure-20260802T160608Z/`

---

## Separate verdicts

| Gate | Verdict |
|------|---------|
| **Wave 2 synthetic production canary** | **CONDITIONAL GO** — policy questions for normal use are publicly closed; canary may proceed **synthetic-only**, observe-only balances, `enforced=false`, `legal_reviewed=false`, after a dedicated Wave 2B→prod canary plan (not executed here). |
| **Controlled real HR leave decisions** | **NO-GO** for expanding beyond Wave 1B synthetic authority gates; real HR decision rollout remains separate. |
| **Real balance enforcement** | **NO-GO** — Islamic yearly calendar not approved; carryover writers off; `legal_reviewed=false`; no enforcement flip. |
| **Payroll monetary calculations** | **NO-GO / out of Leave** — Leave stores sick tiers + paid/unpaid classification inputs only; money stays Payroll-owned. |

Staging re-qualify: Wave 1 **51/51**, Wave 2 **41/41**, freezes E360/Onboarding/Attendance green.

---

## Resolved eligibility rule (6 vs 9 months)

| Item | Finding |
|------|---------|
| Exact article | Law No. 6/2010 **Art. 70**, as **replaced** by Law No. **85/2017** Art. 1 |
| Current Arabic wording | «على أن يستحق العامل إجازة عن السنة الأولى بعد قضائه **ستة أشهر** على الأقل في خدمة صاحب العمل» |
| Obsolete figure | **تسعة أشهر (9 months)** in original Law 6/2010 Art.70 |
| Why obsolete | Not a mistranslation of a different entitlement — the **original article text** was superseded by Official Gazette amendment |
| Final product rule | **`eligibility_months = 6`** |
| Confidence | **high** (public-source verified) |
| Source hash | Law 85/2017 Kuwait Today PDF `sha256:f6f6cb68e4210649b89036786e0017b40737943dd66eb4f7c5e78b9f9df72448` |
| Counsel | `legal_reviewed` remains **false** until product counsel sign-off for enforcement |

Gazette: الكويت اليوم العدد 1348، الأحد 15 شوال 1438 هـ / 2017-07-09 — archived under `sources/official/kuwait-today-law-85-2017.pdf` (+ OCR pages).

MOJ original Law 6/2010 PDF (pre-amendment, shows 9 months in encoded extract): `sha256:20eac58834489098d86271cfc6df9926adfe3fcc9607c47531247e6a56d3f326`.

ILO NATLEX used **only as secondary indexing** (KWT-2010-L-83616 notes Law 85/2017).

---

## Article-level verification matrix

| Field | Value | Classification | Article | Confidence |
|-------|-------|----------------|---------|------------|
| Annual days | ≥30 **working days** | statutory | Art.70 as amended Law 85/2017 | high |
| First-year eligibility | **6 months** | statutory | Art.70 as amended | high |
| Exclude weekly rest + public holidays + sick days inside leave | yes | statutory | Art.70 as amended | high |
| Weekend pair (Fri/Sat default) | fri,sat | **configurable company policy** | Art.70 names العطل الأسبوعية only | medium |
| Sick tiers | 15 / 10 / 10 / 10 / 30 @ 1 / ¾ / ½ / ¼ / 0 | statutory structure; **pay fractions payroll_owned** | Art.69 | high |
| Leave wage before taking leave | — | **payroll_owned** | Art.71 | high |
| Cash settlement of accumulated annual leave on contract end | — | **payroll_owned** | Art.73 | high |
| Carryover / accumulation | ≤2 years; more with mutual consent; **no invented expiry** | statutory boundary; **writers disabled** | Art.72 | high |
| Special unpaid leave | employer may grant on request | **configurable / discretionary** | Art.79 | high |
| Unpaid sick band / childcare unpaid | separate statutory bands | statutory / exceptional | Art.69 / Art.24 | high |
| Islamic / decree holidays | load yearly from official announcements | **manual** | decrees | high |
| Fixed Gregorian holidays | 1 Jan, 25 Feb, 26 Feb versioned | statutory observances | national | high |
| Timezone | Asia/Kuwait | configurable | product | high |

Machine-readable: `OFFICIAL_SOURCE_MATRIX` in `leave_policy_wave2.py` + pack `source_matrix` jsonb. Full hashes: `sources/SOURCE_HASHES.txt`.

---

## Final `kw_private_sector_v2` values (v2.1.0)

```
jurisdiction=KW  worker_category=private_sector
timezone=Asia/Kuwait  weekend_days=[fri,sat]  exclude_public_holidays=true
annual: days_per_year=30 (working_days), eligibility_months=6, monthly_accrual
sick: Art.69 tiers (structure only; pay_fraction payroll_owned)
unpaid: catalogue / Art.79 discretionary; payroll_boundary=true
carryover_enabled=false  (Art.72 boundary recorded; writers off)
public_source_verified=true  legal_reviewed=false  enforced=false
```

---

## Yearly holiday operating contract

1. **Fixed Gregorian** may be seeded with `review_status=seeded_fixed` + provenance.  
2. **Islamic / decree-dependent** holidays: load only from Official Gazette / PAM / Council of Ministers yearly announcements — never invent dates.  
3. Each year gets a `leave_holiday_year_versions` row (`draft` → `pending_review` → `approved` / `rejected` / `superseded`) with source ref + optional sha256.  
4. `leave_holiday_audit` records seed / approve / reject actions.  
5. **Observe:** only `seeded_fixed` / `approved` holidays reduce chargeable days.  
6. **Enforced (future):** `ensure_holiday_calendar_for_enforced` **fail-closed** if year status ≠ `approved` or any in-range holiday is unreviewed.  
7. Staging proved fail-closed while 2026 year remains `pending_review`.

---

## Carryover decision

- **Public law (Art.72):** worker may accumulate up to **two years** of annual leave; with employer consent take at once; **mutual consent** may allow more than two years.  
- **No invented expiry-day limit** beyond that boundary.  
- **Product:** keep **`carryover_enabled=false` / writers disabled** until consent-aware ledger writers exist and counsel sets `legal_reviewed` for enforcement. Architecture is ready; not activated.

---

## Approved product copy & disclaimers

From `PRODUCT_COPY` in module (EN/AR disclaimers + eligibility + payroll boundary + holiday contract). Key lines:

- Wathefni does **not** provide legal advice and does **not** claim automatic legal compliance.  
- Balance enforcement remains off until counsel review and an explicit flip.  
- Leave records day bands and paid/unpaid **classification inputs**; Payroll owns monetary values and salary fractions.

---

## Migration impact (staging)

| Change | Impact |
|--------|--------|
| Pack row `kw_private_sector_v2` **2.1.0** | Additive; 2.0.0 row may remain; binding points to 2.1.0 |
| `leave_holiday_year_versions` / `leave_holiday_audit` | New tables |
| `public_holidays` provenance cols | Already from Wave 2 |
| Company policy notes / eligibility | Still 6 months; notes updated — **no real balance rewrite** |
| Observe holiday exclusion | Now ignores unreviewed rows (safer) |
| Production | **Not migrated** |

---

## Remaining exceptional / manual cases

- Maternity / childcare unpaid (Art.24) — later leave types  
- Study leave (Art.75), conference leave (Art.78-area), hajj (Art.76), bereavement (Art.77) — exceptional catalogues  
- Incurable-disease sick exceptions (Art.69 minister decision) — manual  
- Exact weekend pair per employer — configurable  
- Islamic holiday civil dates each year — manual yearly load + approval  
- Cash settlement amounts / Art.71 pre-leave pay — Payroll  
- Domestic workers / oil sector — out of private-sector pack  

---

## Tests & evidence

| Suite | Result |
|-------|--------|
| Wave 1 staging smoke | 51 passed |
| Wave 2 staging smoke (incl. eligibility + fail-closed) | 41 passed |
| Employees 360 / Onboarding / Attendance freezes | green |

Artifacts: Official Gazette PDF + OCR, MOJ PDF, PAM/Arab Times HTML, mesferlaw/lawskw HTML, SOURCE_HASHES, this REPORT.

---

## What was not done (by design)

No production deploy · no `enforced=true` · no real balance changes · no partial-day/attachments · no UI redesign · no frozen-module edits · no Payroll money engine.
