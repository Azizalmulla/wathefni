# Employees 360 Wave 3F — Kuwait public-law policy closure

**Stamp:** `20260801T214550Z`  
**Evidence:** `ops/evidence/employees360-wave3f-public-law-closure-20260801T214550Z/`  
**Schema:** `employees360-wave3f-public-law-closure-v1`  
**Production deploy:** **NOT DONE** (staging code sync only)  
**Wave 4 / pre-hiring / Wave D:** **UNTOUCHED**

**Disclaimer:** Not legal advice. Wathefni records, validates and orchestrates HR decisions. It does **not** determine whether a specific termination is legally justified, and Employees 360 never calculates EOSB, notice pay, garden leave, damages or leave encashment.

---

## Separate GO / NO-GO verdicts

| Track | Verdict | Exact unresolved blocker (if any) | Blocker type |
|---|---|---|---|
| **Normal real-employee lifecycle operations** | **GO** (public-law product contract closed) | No remaining *legal-policy* blocker for normal Kuwait private-sector cases. Ops still requires explicit Wave 3F prod deploy + turning off synthetic-only when authorized — that is an intentional safety gate, not missing public authority. | — (legal-policy closed); ops gate = intentional safety |
| **Exceptional / high-risk termination cases** | **NO-GO for software decision** | Fit of Art. 41/42/48/49/50 grounds and lawfulness | **Intentionally manual legal judgment** |
| **Payroll settlement calculations** | **NO-GO in Employees 360** | EOSB (Arts. 51–53 + Law 17/2018), notice compensation, garden-leave pay, damages, leave encashment | **Intentionally Payroll ownership** (not a product defect; not missing public authority for *ownership*) |
| **Synthetic production lifecycle operations** | **GO (staging technical)** / **NO-GO (prod Wave 3F canary until deploy)** | Prod orchestrator still on Wave 3D schema; Wave 3F staging-only this wave | **Missing deploy authorization** (ops) |

**Target outcome achieved:** Wathefni is complete enough for **normal Kuwait private-sector lifecycle operations** using authoritative public-law defaults, while exceptional legal cases remain manual and outside the software’s decision authority.

---

## Authority sources archived

| Source | Role | Hash / note |
|---|---|---|
| e.gov.kw / MOJ Law No. 6/2010 Arabic PDF | **Primary** | SHA256 `20eac58834489098d86271cfc6df9926adfe3fcc9607c47531247e6a56d3f326` (byte-identical) |
| Official Gazette Issue 963 English extract | Secondary reading aid | SHA256 `aaed5c6e02a03df4bfdcf035ba1befb9ece3c96d635c5a947f0c5ae929a70fe0` |
| Arabic page PNGs (visual verification) | Manual Arabic verify | `sources/arabic-page-*.png` |
| PAM homepage | Index only | `sources/pam-home.html` |
| NATLEX Law 6/2010 + Law 17/2018 | Secondary index | Live fetch **403**; citation note archived |

**Not used as authority:** law-firm blogs, commercial summaries, AI paraphrases, automated OCR alone.

---

## Deliverables

| Artifact | Path |
|---|---|
| Article-level matrix | `matrix/ARTICLE-LEVEL-MATRIX.md` |
| Arabic/English comparison | `verify/ARABIC-ENGLISH-COMPARISON.md` |
| Approved UI copy | `copy/APPROVED-UI-COPY.md` |
| Normal + exceptional workflows | `copy/WORKFLOWS.md` |
| Production policy + schema/migration | `schema/PRODUCTION-POLICY-AND-SCHEMA.md` |
| Default policy JSON | `schema/DEFAULT_POLICY.json` |
| Source hashes | `sources/SHA256SUMS.txt` |

---

## Product contract implemented

In `employee_lifecycle_wave3c.py` (`SCHEMA_VERSION=employees360-wave3f-public-law-closure-v1`):

- Required: `contract_type`, `pay_frequency`, `probation_status` (+ dates if active), `termination_case_class`, effective date, last working day
- Notice hints fail closed unless unlimited + non-probation + known pay frequency + non-exceptional + `show_notice_hints`
- Exceptional classes require escalation note; software never decides lawfulness
- Settlement packet inputs-only → Payroll; service-certificate pending row (Art. 54)
- Retention: retain, floor 365 days (Art. 144); no auto-purge
- Cancel-before-effective preserved; post-effective reinstate default **false**; true rehire
- `require_counsel_gate` default **false** for normal public-law ops (PL1–PL10 checklist still recordable)
- Missing fields → `manual_review_missing_classification` (never inferred)

---

## Staging qualification

| Suite | Result | Log |
|---|---|---|
| Wave 3C/3F unit | **42/42 PASS** | `verify/w3f-unit3c.txt` |
| Wave 3 unit | **22/22 PASS** | `verify/w3f-unit3.txt` |
| Wave 3C/3F staging smoke | **56/56 PASS** | `verify/w3f-smoke3c.txt` |
| Wave 3 staging smoke | **51/51 PASS** | `verify/w3f-smoke3.txt` |

Staging module: Wave 3F. Production module: still Wave 3D (not updated this wave).

---

## Migration impact

Existing employments with NULL classification cannot complete termination until HR fills authoritative fields. Prior Wave 3D policy rows migrate to `wave=wave3f` with counsel gate off for normal ops on read/upsert. No inference from missing fields.

---

## Remaining ambiguities (exceptional / Payroll only)

1. Official Gazette Arabic for Law 17/2018 Art. 51 — Payroll owns EOSB regardless  
2. Fit of specific summary-dismissal / abandonment / worker-exit grounds — human judgment  
3. Legal continuity of post-effective reinstate — product keeps disabled  
4. Retention years beyond one-year lawsuit horizon — retain indefinitely with 365-day floor  
5. Probation “100 working days” calendar ops — HR dates only  

---

## Non-goals honored

- No production Wave 3F deploy  
- No real-employee flag enablement beyond synthetic gate  
- No Wave 5 / UI redesign  
- No pre-hiring / Wave D changes  
- No Employees 360 monetary calculators  
