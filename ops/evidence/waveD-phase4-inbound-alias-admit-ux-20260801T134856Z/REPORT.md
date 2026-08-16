# Wave D Phase 4 — Inbound CV alias and admit UX

**Stamp:** `20260801T134856Z`  
**Mode:** Local implementation only. **No deploy. No Wave D5.**  
**External tenants:** remain disabled (D2/D3 allowlist unchanged).

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Settings: general intake address create | **PASS** |
| Settings: job-specific alias create (`position_code` / title) | **PASS** |
| Clear labels: needs_role, role_bound, identity review, quarantined, ready | **PASS** |
| Lightweight held review inside Candidates (not Intake Operations) | **PASS** |
| Assign held candidate to job + explicit admit | **PASS** (Assign & admit / safe bulk confirm) |
| Bulk admit only where safe (group has role_code) | **PASS** |
| Duplicate/identity warnings before admission | **PASS** (confirm dialog + identity badges) |
| Quarantined/blocked reason + recovery copy | **PASS** |
| EN/AR + RTL, desktop/mobile screenshots | **PASS** |
| Permissions / tenant isolation preserved | **PASS** (existing dashboard entitlement + company-scoped APIs) |
| Durable backend / safety controls unchanged | **PASS** (no orchestrator behavior changes) |
| Intake Operations console not restored | **PASS** |
| Vitest | **PASS** (9/9) |

---

## UX architecture

```
Settings → Communications → Email & document intake
  ├─ General address  → hold_policy needs_role
  └─ Job-specific alias → position_code/title → role_bound
        ↓ forward from company mailbox
        ↓ Postmark → durable ingress (unchanged D2/D3)
Candidates
  ├─ Held CVs waiting for a job  (HeldIntakeReviewCard)
  │    ├─ status legend + quarantine recovery
  │    ├─ assign job → bulk assign&admit
  │    └─ safe bulk admit when role already clear
  └─ Profile → Add to job (existing AddToJobDialog)
```

**Not restored:** Intake Operations page, nav, attention banner, ops quarantine buckets.

**Backend reused (unchanged):**  
`createIntakeAddress` with `position_*`, `GET …/import/intake`, `POST …/import/items/bulk` (`confirm`|`assign`), person-profile add-to-job.

---

## Files changed

| File | Role |
|---|---|
| `src/lib/inboundIntakePresentation.ts` | EN/AR labels + recovery + safe-bulk helper |
| `src/components/candidates/HeldIntakeReviewCard.tsx` | Held review / admit surface |
| `src/pages/SettingsPage.tsx` | General vs job alias create + hold badges |
| `src/pages/CandidatesPage.tsx` | Mount held card |
| `src/App.tsx` | Pass `access` / `positions` / reload hooks |

---

## Screenshots

`ops/evidence/waveD-phase4-inbound-alias-admit-ux-20260801T134856Z/screenshots/`

| File | View |
|---|---|
| `settings-held-en-desktop.png` | EN desktop Settings + held legend |
| `settings-held-ar-desktop.png` | AR desktop RTL |
| `settings-held-en-mobile.png` | EN mobile |
| `settings-held-ar-mobile.png` | AR mobile |

---

## Tests & local evidence

| Artifact | Path |
|---|---|
| Vitest log (9/9) | `verify/vitest.log` |
| Capture log | `verify/capture.log` |
| Key SHAs | `verify/key-files.sha256` |
| This report | `REPORT.md` |

Suites: `inboundIntakePresentation.test.ts`, `SettingsEmailSending.test.tsx` (incl. alias controls), `HeldIntakeReviewCard.test.tsx`.

---

## Preserve checklist

- Recipient-only tenant resolution — unchanged  
- Quarantine / malware / OCR / identity / dedupe / quotas / replay / audit — unchanged  
- External tenants disabled — unchanged  
- D5 not started  

---

## Final

**PASS** — Wave D Phase 4 local UX complete. Ready for a separate deploy approval when requested.
