# Compliance Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T084521Z`  
**Evidence:** `ops/evidence/compliance-page-refinement-wave1-prod-deploy-20260804T084521Z/`  
**Freeze:** `ops/COMPLIANCE_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle (live):** `/var/www/wathefni-dashboard/assets/PostHire-CTpKApnh.js`  
**Backup:** `/opt/wathefni/backups/production-pre-compliance-page-refinement-wave1-20260804T084521Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** (`COMPLIANCE_PAGE_WAVE1_SMOKE_OK`) |
| Mutation / permission proof | **GO** (`MUTATION_PERMISSION_PROOF_OK`) |
| Freeze Compliance Page Wave 1 | **GO / FROZEN** |
| Extraction / OCR / backend authority | **NO-GO** (not changed) |
| Employees native dialogs D1–D2 | **UNTOUCHED** |
| Analytics / Payroll / Shifts / Leave freezes | **UNTOUCHED** |

## Implementation-truth findings

| Finding | Truth |
|---|---|
| Mount | `CompliancePage` in `PostHire.tsx` only |
| Pre-wave IA | Banner + StatCards + chips + findings + full register all restated the same counts |
| Reminders | Lived on register rows, bulk “Remind all”, Employees 360, and findings |
| Delivery strip | Mounted on Compliance (Alerts & Delivery territory) |
| Native dialogs D3–D6 | `window.prompt` in shared `DocumentHrReviewButtons` |
| Default surface | Now **Findings**; register behind **All documents** |

## Duplication removed

- Hero / `NextAction` attention banner
- Five equal **StatCards** repeating summary buckets
- Bulk **Remind all**
- Reminder + HR review actions from Employees 360 (deep-link only)
- Reminder buttons on **All documents** register (routes to Findings)
- `DeliveryStatusStrip` on Compliance
- Always-on methodology / source authority on first paint
- Competing equal actions on findings (primary + More pattern)

## Final Findings / All documents structure

1. Compact Compliance header + purpose  
2. One-line attention summary (+ as-of)  
3. Surface tabs: **Findings** (default) · **All documents**  
4. Filters: Needs review · Missing · Expiring · Expired · All  
5. Findings list: employee, document type, issue, deadline, state, one primary action, Details expansion  
6. All documents: searchable register; review/Open in Findings; evidence/upload secondary  
7. Definitions & authority collapsed  

## Reminder and verification ownership

| Concern | Owner |
|---|---|
| Document review / confirm / reject / expiry correction / follow-up | **Compliance** |
| Send reminder (`compliance_send_reminder`) | **Findings only** (one path) |
| Required-document progress | Onboarding (deep-links here for verification) |
| Prioritize & route | Needs Attention |
| Failed communication delivery | Alerts & Delivery |
| Government verification | Never claimed — HR reviewed ≠ PACI/MOI/PAM |
| Extraction / OCR / identity authority | Unchanged (Mistral) |

## Native-dialog replacements (D3–D6)

| ID | Action | Replacement |
|---|---|---|
| D3 | Reject reason | `confirm.withReason` (min 3) |
| D4 | Expiry date | Governed dates modal |
| D5 | Issue date | Same modal |
| D6 | Correction reason | Optional field on same modal |

D1–D2 (Employees approver / activation handoff) **untouched**.

## Permission and mutation proof

- Gate: `compliance.manage`  
- Review POST: `/dashboard/posthire/employees/{key}/documents/{type}/review` (approve / reject / correct_metadata)  
- Reminder action: `compliance_send_reminder`  
- Live proof: `verify/mutation-permission-proof.out` → `MUTATION_PERMISSION_PROOF_OK`

## Smoke

`verify/smoke-prod.out` — `COMPLIANCE_PAGE_WAVE1_SMOKE_OK`  
(run via `/opt/wathefni/orchestrator/.venv/bin/python`)

## Screenshots

`ops/evidence/compliance-page-refinement-wave1-prod-deploy-20260804T084521Z/screenshots/`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-compliance-page-refinement-wave1-20260804T084521Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-compliance-page-refinement-wave1-20260804T084521Z
```
