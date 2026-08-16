# Employees 360 Wave 3D — Official public-law verification & conservative production policy

**Stamp:** `20260801T205907Z`  
**Evidence:** `ops/evidence/employees360-wave3d-public-law-policy-20260801T205907Z/`  
**Schema:** `employees360-wave3d-public-law-policy-v1`  
**Production deploy:** **NOT DONE** (staging code sync only)  
**Wave 4 / pre-hiring / Wave D:** **UNTOUCHED**

**Disclaimer:** This pack cites official public sources and records product-policy choices. It is **not legal advice**. Employees 360 does **not** determine lawfulness, compute EOSB/notice pay/garden leave/leave encashment, or approve irreversible offboarding without a human second approver.

---

## Verdict

| Gate | Result |
|---|---|
| Official-source research (gov.kw / MOJ PDF + NATLEX metadata) | **DONE** |
| Conservative Wave 3D policy defaults coded | **DONE** |
| Staging Wave 3 unit + smoke | **22/22 + 51/51 PASS** |
| Staging Wave 3C/3D unit + smoke | **23/23 + 50/50 PASS** |
| Prod deploy | **NOT DONE** |
| WATHEFNI-only production **synthetic canary** | **NO-GO** (do not deploy yet; remaining Arabic-text / amendment gaps + counsel re-sign required) |

### Final GO / NO-GO

**NO-GO** for WATHEFNI-only production synthetic canary **now**.

Staging requalification passed after conservative policy changes. Canary remains blocked until (1) explicit deploy authorization, (2) counsel re-signs the Wave 3D checklist version, and (3) counsel confirms Art. 44 / Art. 51 Arabic wording against the official PDF (automated Arabic extraction from the published PDF is font-encoded and unreadable).

---

## 1. Authority sources used

| Source | Role | Path / URL | Notes |
|---|---|---|---|
| Kuwait Government Online — Labour Law PDF | **Primary** Arabic official text | https://e.gov.kw/sites/kgoEnglish/Forms/KuwaitLaborLaw.pdf | SHA256 `20eac588…d326`; archived in `sources/` |
| Ministry of Justice — same Law 6/2010 PDF | **Primary** Arabic official text | https://www.moj.gov.kw/AR/Documents/MojDocs/…قانون رقم 6 لسنة 2010….pdf | Byte-identical to e.gov PDF |
| e.gov Human Resources page | Official index | https://e.gov.kw/sites/kgoEnglish/Pages/Business/InfoSubPages/HumanResources.aspx | Links Labour Law PDF |
| ILO NATLEX record Law No. 6/2010 | Official legal repository metadata | https://natlex.ilo.org/…/details?p3_isn=83616 | Live fetch returned 403; citation retained from NATLEX catalog |
| ILO NATLEX Law No. 17/2018 | Amendment metadata (Art. 51 EOSB for Kuwaiti nationals) | https://natlex.ilo.org/…/details?p3_isn=108307 | Abstract only; full Arabic amendment text **not** retrieved this wave |
| CAWTAR English PDF (kuwaitlaborlaw.com watermark) | **Non-authority** reading aid only | archived as `Law6-2010-english-secondary-cawtar.pdf` | Used only to locate article numbers; **not** cited as binding English |

**Not used as authority:** law-firm blogs, commercial digests, AI paraphrases.

**Extraction caveat:** `pdftotext` on the official Arabic PDF yields corrupted presentation-form glyphs (custom font encoding). Product policy therefore **hides** numeric notice hints by default rather than asserting unverified OCR.

---

## 2. Public-source legal verification matrix

| Topic | Official finding (public sources) | Product implication | Confidence | Classification |
|---|---|---|---|---|
| **Scope / Kuwait-only** | Law 6/2010 Arts. 2–5: applies to private-sector workers; oil/marine residual; excludes workers under other laws and domestic workers (Art. 5). | `jurisdiction_mode=kuwait_private_sector_only`; reject explicit non-KW `work_country`. | **High** (structure confirmed via Official Gazette English reading + gov PDF presence) | **Statutory** scope; product excludes non-KW |
| **Notice — unlimited / monthly** | Art. 44(a): three months’ notice for monthly-paid workers (unlimited term). | Optional labeled guidance only: 90 calendar days when `show_notice_hints=true`. **Hidden by default.** | **Medium** — English Gazette reading clear; Arabic PDF not machine-verified | **Statutory** floor for unlimited monthly; product treats UI as **configurable policy guidance** |
| **Notice — unlimited / other pay** | Art. 44(b): one month for other workers. | Optional 30-day labeled guidance when hints enabled. Hidden by default. | **Medium** (same caveat) | Statutory / configurable guidance |
| **Pay-in-lieu of notice** | Art. 44: party failing notice pays compensation equal to remuneration for the notice period. | Employees 360 **never** calculates amount; Payroll owns. Dates entered by HR. | **High** (rule existence); amount math **out of scope** | Statutory entitlement; product **manual / Payroll** |
| **Garden leave / exempt from work during notice** | Art. 44(d): employer may exempt worker during notice; period counts as service; entitlements/remuneration paid. | No garden-leave calculator; LWD + effective date are operator inputs. | **Medium–High** | Statutory; product **manual** |
| **Job-search day** | Art. 44(c): during employer notice, worker may be absent 1 day or 8h/week paid. | Not auto-scheduled; no entitlement engine. | **Medium** | Statutory; product **manual / ambiguous ops tracking** |
| **Fixed-term vs unlimited** | Art. 44 notice applies when term **not** specified. Art. 47: wrongful early end of fixed-term → damages capped at remaining-term remuneration. | Do **not** apply 90/30 hints to fixed-term. No damages calculator. | **Medium–High** | Statutory; product **ambiguous** without contract-type field enforcement |
| **Probation** | Art. 32: ≤100 working days; either party may terminate **without notice**; employer-initiated still pays EOSB for period worked; probation once per employer. | No numeric notice hint on probation cases; no EOSB math. | **Medium–High** | Statutory; product **manual** |
| **Summary dismissal** | Art. 41: limited grounds; some without notice/compensation/benefit; others keep EOSB; Ministry notification; arbitrary dismissal → EOSB + damages after final verdict. | Case type may exist; **no** auto-lawfulness; evidence/counsel required; no indemnity math. | **Medium** (grounds list from English reading) | Statutory; product **manual + counsel** |
| **EOSB / indemnity ownership** | Arts. 51–53 formulas; Art. 52 full benefit cases; Art. 53 partial on worker resignation (unlimited). Law 17/2018 (NATLEX) amends Art. 51 for Kuwaiti nationals / PIFSS interaction. | **Payroll owns all EOSB math.** Settlement packet inputs-only. | **High** that formulas exist & belong outside E360; **Low** on 2018 Arabic amendment details (not retrieved) | Statutory; product **Payroll-only** |
| **Leave encashment** | Art. 73: cash consideration for accumulated annual leave on contract expiry; Art. 74: cannot waive annual leave. | No encashment calculator in E360; balances are settlement **inputs**. | **Medium–High** | Statutory; product **Payroll-only** |
| **Reinstatement vs rehire** | Law text addresses termination/EOSB/certificate (Art. 54); **no** clear public statutory “click reinstate = continuous service” rule found. | **`allow_reinstate_after_effective=false` by default**; use **true rehire**. Opt-in reinstate only if explicitly enabled. | **High** for product conservatism; legal continuity **ambiguous** | **Configurable policy** (safe default); legal effect **ambiguous** |
| **Document retention** | Art. (personnel file): employer must maintain worker file incl. contract, leaves, EOS date/reasons, return receipts. Art. 144-ish limitation: worker suits generally not heard after **one year** from end of contract (English reading). | `document_retention_mode=retain` by default; no auto-purge. Exact retention years beyond litigation horizon **not** fully specified in retrieved public text. | **Medium** (file duty clear; retention duration partially ambiguous) | Statutory duty to keep file; product **retain**; duration **ambiguous** |
| **Auto shift cancel / leave reject** | Not a statutory auto-action found. | `downstream_mode=warn_first`; `auto_cancel_shifts=false`; `auto_decline_leave=false`; explicit dual-approved downstream actions only. | **High** (absence of mandate → safest disabled) | **Configurable policy** |
| **Two-person / no self-approval** | Not a statutory PAM UI rule; product control. | Hard-coded `allow_self_approval=false`. | **High** (product) | **Configurable policy** (mandatory in Wathefni) |
| **Cross-border** | Law is Kuwait private-sector. No public rule found authorizing E360 to apply KW notice abroad. | Exclude non-KW cases. | **High** for exclusion; foreign regimes **out of scope** | Product exclusion |

---

## 3. Final production policy values (Wave 3D defaults)

```json
{
  "tier": "small",
  "timezone": "Asia/Kuwait",
  "show_notice_hints": false,
  "notice_hint_monthly_days": 90,
  "notice_hint_other_days": 30,
  "require_last_working_day": true,
  "allow_reinstate_after_effective": false,
  "jurisdiction_mode": "kuwait_private_sector_only",
  "document_retention_mode": "retain",
  "auto_cancel_shifts": false,
  "auto_decline_leave": false,
  "monetary_calculations_owner": "payroll",
  "settlement_packet_mode": "inputs_only",
  "revoke_mode": "end_of_last_working_day",
  "effective_time_mode": "start_of_effective_date",
  "downstream_mode": "warn_first",
  "require_impact_ack": true,
  "require_counsel_gate": true,
  "allow_self_approval": false,
  "rehire_same_employee_key": true,
  "scheduler_cadence": "hourly",
  "lag_alert_seconds": 7200
}
```

**Enforcement added in Wave 3D**

- Numeric notice hints **hidden** unless `show_notice_hints` explicitly enabled (then labeled configurable guidance only).
- Termination requires **effective date + last working day**.
- Post-effective **reinstate rejected** unless policy opt-in.
- Explicit non-Kuwait `work_country` / `jurisdiction` → `jurisdiction_excluded`.
- Settlement packet states Payroll ownership + document retain mode; still **no amounts**.

---

## 4. Remaining unresolved ambiguities

1. **Arabic Art. 44/32/51 exact wording** — official PDF archived, but font encoding blocks reliable automated text extraction; counsel must read Arabic PDF.
2. **Law 17/2018 Art. 51 amendment** — NATLEX abstract only; full Official Gazette Arabic not retrieved; EOSB stays in Payroll regardless.
3. **Fixed-term + probation product detection** — law differs; employment records may lack reliable contract/pay-type fields for enforcement beyond hiding hints.
4. **Reinstatement legal continuity** (visa / indemnity / continuous service) — no clear public statute located; default remains rehire.
5. **Document retention duration** after end of service — file-keeping duty clear; multi-year retention schedule not fully resolved from public text → retain indefinitely in product.
6. **Amendments 90/2013, 108/2013, 32/2016, 85/2017** — catalogued by secondary indexes; full official texts not pulled this wave; no product math depends on them.

---

## 5. Staging evidence

| Suite | Result | Log |
|---|---|---|
| Wave 3C/3D unit | **23/23 PASS** | `verify/w3d-unit3c.txt` |
| Wave 3 unit | **22/22 PASS** | `verify/w3d-unit3.txt` |
| Wave 3C/3D staging smoke | **50/50 PASS** | `verify/w3d-smoke3c.txt` |
| Wave 3 staging smoke | **51/51 PASS** | `verify/w3d-smoke3.txt` |

Staging path updated: `/opt/wathefni/staging/orchestrator/employee_lifecycle_wave3c.py`  
Production orchestrator **not** updated this wave.

---

## 6. Non-goals confirmed

- No production Wave 3 feature deploy
- No Wave 4 start
- No pre-hiring / Wave D behavior changes
- No Employees 360 monetary calculators

---

## 7. Pre-canary checklist (when deploy is later authorized)

1. Counsel re-sign checklist version `employees360-wave3d-public-law-policy-v1`
2. Confirm Arabic Arts. 32, 41, 44, 47, 51–54, 70–74 against official PDF
3. Deploy Wave 3D module to prod with flags **WATHEFNI-only**
4. Synthetic employees only; no live workforce cases
5. Keep `show_notice_hints=false`, `allow_reinstate_after_effective=false`
6. Verify settlement packets still contain **no amounts**


---

## Readiness reclassification (20260801T210838Z)

- **Technical synthetic canary:** **GO** — see `ops/evidence/employees360-wave3d-synthetic-canary-20260801T210838Z/REPORT.md`
- **Real-employee production use:** **NO-GO** (unchanged)
