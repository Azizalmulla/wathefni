# HR OCR / validation summary UI — evidence stamp

**Stamp:** `20260806T035255Z`  
**Scope:** Shared HR extraction summary for every employee-upload document type · close document qualification wave (backend/HR-path) · Bank ESS next · Auth Wave 2 still blocked.

## What shipped

Shared component `apps/wathefni-dashboard/src/posthire/DocumentExtractionSummary.tsx` (+ loader) wired into:

1. **Compliance Findings** — expanded detail
2. **Compliance Register** — Summary row expand
3. **Onboarding checklist** — document rows with stored uploads

Uses existing journey API `ocr_proposal` (+ new `verified_fields`, `extraction_vs_verified`). No raw OCR/JSON dump. Document numbers masked by default; reveal gated by `compliance.manage` / `onboarding.manage` / `employees.ess.unmask`.

Backend enrichments:

- Persist `identity_check` + `hr_warnings` on `ocr_proposal`
- Dual-side promote merges name/nationality/DOB + per-side `parts` for Civil ID Front/Back + pair status
- Journey marks extracted values as proposals that never auto-overwrite employee profile (`confirm_ocr` still off by default on approve)

## Qualification (live HTTP · six types)

| Type | Verdict |
|---|---|
| Civil ID F+B canary | **fully proven** |
| Passport | **fully proven** |
| Residence | **fully proven** |
| Work permit | **fully proven** |
| Employment contract | **fully proven** |
| Personal photo | **fully proven** |

Includes: `hr_ocr_summary_ui`, `hr_ocr_no_raw_dump`, HR approve/reject/replace, civil SHA unchanged, canary leftovers 0.

Dashboard bundle contains “never overwrite canonical employee data”. Dual-side unit smoke OK.

## Residual (accepted)

- Real-world OCR accuracy still needs continued production sampling (synthetic fixtures prove pipeline/UI, not field accuracy at scale).
- Document-number reveal is permission-gated session reveal (ESS-style audited unmask API for document numbers not added in this slice).
- Bank ESS still required before claiming mobile onboarding complete.
- Authentication Wave 2 must not start until Bank ESS + onboarding completion are resolved.

## Live inspection (optional)

Dashboard already deployed to `/var/www/wathefni-dashboard`. After a disposable canary upload (or any pending HR review):

1. Post-hire → **Compliance** → Needs review → **Details** → Extraction & validation summary  
2. Or **All documents** → **Summary**  
3. Or **Onboarding** → open Aziz → document row shows the same shared summary  
4. Toggle EN/AR · confirm number masked · Reveal only if authorized · Civil ID shows Front/Back + pair status  
5. Confirm “Extracted (proposal)” vs “Verified / HR-saved” sections · approve does **not** write OCR into employee profile unless explicit `confirm_ocr` (UI does not send it)

## Rollback

1. Restore dashboard from `/opt/wathefni/dashboard-dist-bak/hr-ocr-summary-<stamp>/` → `/var/www/wathefni-dashboard/`  
2. Restore orchestrator from `/opt/wathefni/backups/hr-ocr-summary-<stamp>/` and `systemctl restart wathefni-orchestrator`
