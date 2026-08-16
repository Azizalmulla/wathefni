# Kuwait/GCC Contracts & Compliance Document Intelligence — Wave 1

**Stamp:** `20260804T040217Z`  
**Host:** staging qualify on `root@76.13.63.68` (`/opt/wathefni/staging/orchestrator`)  
**Production deploy this wave:** **NO-GO** (explicit)  
**Staging module authority (qualify ready / not wired to live routes):** **GO**

## Clarification honored

Wave 1 covers **both**:

1. **Onboarding document intake** (WhatsApp + ESS onboarding)
2. **Post-onboarding** HR Document Hub, ESS renewal, and compliance uploads

Civil ID, passport, residency, work permit, medical, education certificate, and employment contract processing reuse the **same** document-class schemas, authority rules, and Mistral extraction path across channels. **No separate onboarding-only vs compliance-only extractors.**

Required onboarding / shared flow (qualified, not yet wired into Hub/ESS):

```text
upload
  → classify / verify expected onboarding item
  → document_envelope@1
  → extract fields (shared path)
  → HR confirmation
  → employee / compliance record
  → expiry and renewal tracking (HR-confirmed dates only)
```

**Live identity Mistral authority is preserved.** Identity types **delegate** to `identity_document_extraction` — this wave does not duplicate or replace that module.

## Verdict

| Gate | Result |
|---|---|
| Staging qualify (shared module + identity delegate) | **GO** |
| Production deploy this wave | **NO-GO** |
| Hub / ESS / onboarding live cutover | **NO-GO** (Wave 2) |
| CV / identity authority / payroll / Migration Wave 1 / Ranking / CK / foundation ROUTE_MATRIX | **unchanged** |

Evidence:

- Corpus: `ops/evidence/kuwait-gcc-contracts-wave1-corpus-20260804/`
- Qualify: `ops/evidence/kuwait-gcc-contracts-wave1-qualify-20260804/summary.json`
- Module: `wathefni-orchestrator/kuwait_gcc_document_intelligence/`
- Scripts: `scripts/build-kuwait-gcc-contracts-wave1-corpus.py`, `scripts/wave1-kuwait-gcc-contracts-compliance-qualify.py`

## Kuwait-first implementation map

| Document class | Processor | Authority default | Channels (intended) |
|---|---|---|---|
| civil_id | **delegate → identity_document_extraction** | PACI | WhatsApp / ESS onboarding / Hub / ESS renew |
| passport | **delegate → identity** | MOI | same |
| residence (aliases: residency, residency_iqama) | **delegate → identity** | MOI | same |
| work_permit | **delegate → identity** | PAM | same |
| medical | **delegate → identity** | MOH | same |
| education_cert | Mistral Document AI (this module) | EMPLOYER / attested | same |
| employment_contract / contract_amendment | Mistral Document AI (this module) | EMPLOYER | same (+ Hub amendments) |
| commercial_licence | storage / text mirror | MOCI | employer setup |
| authorised_signature | storage / text mirror | EMPLOYER | offer snapshot |
| offer_letter | storage or generated | EMPLOYER | onboarding / Hub |
| PIFSS-related | external authority mirror / payroll worksheet | PIFSS | payroll import — not OCR in this wave |

Jurisdiction profile: `kuwait_gcc_document_intelligence/jurisdiction_kw.py` (`country_code=KW`, authorities PACI/PAM/MOI/PIFSS/MOCI/MOH/EMPLOYER, reminder windows). Profile is **not** hardcoded into the shared foundation.

Hard constraints honored:

- No CV Extraction V2 for these classes
- No GPT as OCR / extraction / fallback
- Fields non-authoritative until HR confirms
- No second identity extractor
- No production deploy

## Channel gaps & inconsistencies (audit)

Returned from `channel_gap_registry()` — **10** live inconsistencies. High-severity onboarding / post-onboarding gaps:

| Gap | Channel | Route / symptom |
|---|---|---|
| Hub skips extraction | HR Document Hub | `POST /dashboard/posthire/employees/{key}/documents` → `extraction={}` |
| ESS renew skips extraction | ESS renew | `POST /app/documents/renew` → `extraction={}` |
| ESS onboarding skips extraction | ESS onboarding | `POST /app/onboarding/documents` → `extraction={}` |
| WhatsApp identity-only structure | WhatsApp onboarding | Identity types use live Mistral; **contracts / education_cert not structured** |
| Backfill identity-only | compliance backfill | contracts / education not in backfill set |
| residence alias split | all | storage `residence` vs identity `residency` (+ `residency_iqama`) — normalized in shared module |
| medical vs medical_check | onboarding template | checklist task vs compliance dual-write type |
| education_cert obsolete checklist | WhatsApp onboarding | obsolete in wave2 template but still allowlisted |
| ROUTE_MATRIX stale identity label | foundation | still says GPT vision; live is Mistral — **not mutated this wave** |
| contract_compliance_processor label-only | foundation | ROUTE_MATRIX label with no prior live module — package qualifies; matrix unchanged |

**Onboarding flow gap vs required contract:** ESS onboarding and Hub do not run classify/verify → envelope → extract today. WhatsApp onboarding runs identity verify/extract for identity types only. Expiry/renewal tracking remains tied to HR-confirmed metadata where extraction was skipped.

**No duplicated onboarding-only / compliance-only extractors were created.** Wave 1 adds one shared package; identity remains the existing live authority.

## Qualify results (staging)

| Check | Result |
|---|---|
| Circuit open → durable `needs_review` (no GPT) | PASS |
| GPT-free | PASS (`gpt_calls=0`) |
| Invented scored fields | **0** |
| Wrong category (passport as contract) | PASS |
| Identity delegate (5 types) | PASS → `identity_document_extraction` |
| Structuring fixtures ≥50% field match | **5/5** |
| Sibling freezes (CV / identity / payroll / migration / Ranking / CK / ROUTE_MATRIX / no prod) | PASS |

### Benchmark by document class

| Class | n | Mean field accuracy |
|---|---|---|
| employment_contract | 3 | **0.833** |
| education_cert | 2 | **1.000** |

Identity refs (civil_id, passport, residence, work_permit, medical): delegated; not re-benchmarked as a second extractor.

Corpus: 6 structuring fixtures + 12 identity-corpus refs (synthetic / anonymized). Low-res Arabic contract remains the weakest case (doc number / name OCR noise) but stayed above the Wave 1 gate.

## Storage-only / generated-only / external mirrors

| Kind | Types |
|---|---|
| Storage-only (no OCR structuring in Wave 1) | offer_letter, personal_photo, police_certificate / clearance, blood_type / blood_test, lease / lease_contract, fingerprint_notice |
| Generated-only | generated_offer, payslip, payroll_mirror, pifss_worksheet |
| External authority mirrors | commercial_licence_text, pam_employer_file_no, authorised_signatory_name, pifss_payroll_worksheet |

## GCC extension design (not implemented)

Kuwait profile is the first jurisdiction pack. Extension hooks expect parallel profiles (`SA`, `AE`, `BH`, `QA`, `OM`) supplying authorities, reminder windows, and optional field validators — **same** schemas and shared extraction entrypoints. No other GCC profile is shipped in Wave 1.

## Smallest production cutover wave (Wave 2 — not this wave)

**Kuwait/GCC Contracts & Compliance Wave 2 — Shared Channel Wiring**

1. Staging: replace `extraction={}` on Hub / ESS renew / ESS onboarding with `kuwait_gcc_document_intelligence.process_document`
2. Identity channels keep `identity_document_extraction` delegate (no second extractor)
3. Wire `employment_contract` + `education_cert` structuring on WhatsApp + Hub + ESS
4. Write HR-confirmed expiry only into compliance reminders / renewal tracking
5. Production canary `WATHEFNI`, then expand

**Do not:** mutate CV; replace identity module; re-enable GPT fallback; silently rewrite foundation ROUTE_MATRIX without owner GO.

## Rollback / non-deploy note

This wave synced the qualify package to **staging orchestrator only** for bench. Live Hub/ESS/onboarding routes were **not** cut over. Production was **not** deployed. Instant “rollback” for Wave 1 is remove the unused staging package / evidence — no live traffic depends on it yet.
