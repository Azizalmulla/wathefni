# Kuwait/GCC Contracts & Compliance Document Intelligence — Wave 2

**Stamp:** staging `20260804T042149Z` · production `20260804T042508Z`  
**Host:** `root@76.13.63.68`  
**Scope freeze:** Kuwait/GCC Contracts & Compliance Document Intelligence (omnichannel)

## Final gates

| Gate | Result |
|---|---|
| Staging omnichannel wiring | **GO** |
| Production authority (global) | **GO** |
| Freeze Kuwait/GCC Contracts & Compliance Document Intelligence | **GO** |

Evidence:

- Staging: `ops/evidence/kuwait-gcc-contracts-wave2-omnichannel-20260804/summary.json`
- Production: `ops/evidence/kuwait-gcc-contracts-wave2-omnichannel-prod-20260804/summary.json`
- Isolation / residual: `ops/evidence/kuwait-gcc-contracts-wave2-omnichannel-prod-20260804/isolation_residual.json`

Sibling freezes honored: CV extraction, identity schemas, payroll, Migration Wave 1, Ranking, Candidate Knowledge, `document_envelope@1` contract.

## What shipped

One shared processor path across all intake channels — **no** WhatsApp/email/ESS/Hub-specific extractors.

| Channel | Route / entry | Shared path |
|---|---|---|
| WhatsApp onboarding | verify / classify / `validate_onboarding_document_identity` → receipt | `shared_channel_extraction` |
| ESS onboarding | `POST /app/onboarding/documents` | same |
| ESS renew | `POST /app/documents/renew` | same |
| HR Document Hub | `POST /dashboard/posthire/employees/{key}/documents` | same |
| Compliance backfill | `POST /orchestrator/posthire/documents/extract` | allowlist + shared extract |
| Inbound email | `POST /orchestrator/posthire/documents/email-intake` | `email_intake.process_email_attachment` → shared processor |

Required flow live:

```text
upload/attachment
  → tenant + employee matching (email: strong match only)
  → classify/verify expected document
  → document_envelope@1
  → shared document processor
  → non-authoritative proposal
  → HR confirmation/correction
  → employee/compliance record
  → expiry/renewal tracking (HR-confirmed only)
```

Uncertain email tenant/employee/type → durable `employee_document_email_intake` review queue; **never** weak auto-attach. Duplicate message+hash suppressed.

## Processor routing

| Classes | Processor |
|---|---|
| Civil ID, passport, residency/residence, work permit, medical | **delegate → `identity_document_extraction`** (unchanged live Mistral authority) |
| Employment contract, contract amendment, education certificate | **Kuwait/GCC Mistral** (`kuwait_gcc_document_intelligence`) |

No CV V2. No GPT for classify / verify / extract / fallback / shadow.

## Audited gaps closed (12)

| Gap | Status |
|---|---|
| Hub / ESS renew / ESS onboarding `extraction={}` | **closed** |
| WhatsApp contracts/education unstructured | **closed** |
| Backfill identity-only | **closed** (contracts + education + residence) |
| residence / residency / residency_iqama drift | **closed** (canonical `residence`, aliases preserved) |
| medical / medical_check drift | **closed** (canonical `medical`, aliases preserved) |
| education_cert checklist naming | **closed_compat** (canonical `education_cert`) |
| Stale ROUTE_MATRIX GPT identity / label-only contract processor | **closed** |
| Email employee-doc intake missing | **closed** (shared processor + review queue) |
| OCR expiry drove reminders pre-HR | **closed** (proposal-only until `renewal_status=reviewed`) |

## Canonical document-type mapping

| Canonical | Preserved aliases |
|---|---|
| `residence` | `residency`, `residency_iqama` |
| `medical` | `medical_check`, `medical_fitness` |
| `education_cert` | `education_certificate`, `education`, `edu_cert` |
| `employment_contract` | `employment_agreement`, `contract` |
| `contract_amendment` | `amendment` |

Historical stored rows were **not** destructively rewritten.

## ROUTE_MATRIX labels (updated)

- Identity → `identity_document_extraction_mistral` · no GPT auto OCR
- Contract / compliance → `kuwait_gcc_document_intelligence` · shared hybrid / native DOCX · no GPT

## Production flags / kill switch / rollback

Live process env:

```text
WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY=on
WATHEFNI_KUWAIT_GCC_MISTRAL_DISABLE_COMPANIES=
WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=on
WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
WATHEFNI_CV_GPT_VISION_RESCUE=off
```

| Control | Behavior |
|---|---|
| Global default | `AUTHORITY=on` for current and future tenants |
| Kill switch | `WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY=off\|kill\|disabled` |
| Per-tenant pause | `WATHEFNI_KUWAIT_GCC_MISTRAL_DISABLE_COMPANIES=A,B` |
| Rollback | `/opt/wathefni/backups/production-pre-kuwait-gcc-wave2-20260804T042303Z/ROLLBACK.sh` |

## Route-by-route results

### Staging

| Channel | Result |
|---|---|
| WhatsApp / ESS onboarding / Hub / ESS renew / backfill (contract + education) | **PASS** (10/10) |
| Identity delegate (5 types) | **PASS** |
| Wrong category | **PASS** |
| Email unmatched → review + duplicate suppress | **PASS** |
| Reminder gate (unconfirmed OCR) | **PASS** |
| Circuit → `needs_review` / GPT-free / kill switch | **PASS** |

### Production

Same omnichannel suite **PASS**. Isolation:

| Tenant | Global ON | On disable list ISOID1,ISOID2 |
|---|---|---|
| WATHEFNI | enabled | still enabled |
| ISOID1 | enabled | disabled |
| ISOID2 | enabled | disabled |

Residual zero: no `extraction={}` on wired receipts; Hub/ESS/email/backfill call shared path; verify/classify/extract wrappers have no planner/GPT; route matrix GPT-free.

## Remaining non-OCR classes

| Kind | Types |
|---|---|
| Storage-only | offer_letter, personal_photo, police_certificate/clearance, blood_type/test, lease, fingerprint_notice |
| Generated-only | generated_offer, payslip, payroll_mirror, pifss_worksheet |
| External mirrors | commercial_licence_text, pam_employer_file_no, authorised_signatory_name, pifss_payroll_worksheet |

## Freeze declaration

**Kuwait/GCC Contracts & Compliance Document Intelligence is frozen** at Wave 2 omnichannel production authority:

- Shared schemas + Mistral path across all channels
- Identity Mistral authority preserved via delegation
- HR confirmation required; reminders only after HR-confirmed expiry
- Kill switch + rollback retained

Further work in this scope requires an explicit unfreeze / new wave owner GO.
