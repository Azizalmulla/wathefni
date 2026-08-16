# Onboarding Page Refinement Wave 1

**Stamp:** `20260804T063521Z`  
**Evidence:** `ops/evidence/onboarding-page-refinement-wave1-20260804T063521Z/`  
**Production dashboard:** `/var/www/wathefni-dashboard` (UI-only; orchestrator unchanged)  
**Backup:** `/opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-20260804T063521Z/`

## Implementation-truth findings (pre-change)

| Finding | Truth |
|---|---|
| Purpose drift | Page mixed oversized “still onboarding” / `NextAction` banners with the hire queue |
| Action clutter | Remind / Checklist / Reschedule / Cancel competed as equal row buttons |
| Delivery duplication | Host `DeliveryStatusStrip` could appear on Onboarding; Alerts owns failures |
| Profile ownership leak | Profile onboarding section could mark/waive/remind — same mutations as Onboarding |
| Deep-link | `?employee=` partially honored; expand/scroll/pin incomplete |
| Needs Attention leftover | Inner page heading duplicated shell title; delivery strip still mounted on inbox |
| Mutation integrity | Prior fix (`web_dashboard` exempt from assistant kill + confirm handshake) must stay |

## Exact change ledger

### Removed
- Oversized Onboarding `NextAction` / “still onboarding” banner
- `BlockedReason` banners on Onboarding (quiet permission/read-only hints only)
- Equal-weight Reschedule / Cancel / Checklist row buttons
- Profile checklist mutates (`onboarding_mark_item`, remind) — replaced with read-only list + **Open in Onboarding**
- Profile next-action executables for `module === 'onboarding'` (`canRunNextAction` → false)
- Needs Attention duplicated inner heading (eyebrow / h2 / detail block)
- Employee delivery-failure strip on Needs Attention **and** Onboarding mounts (`DeliveryStatusStrip` excluded for `employees` \| `inbox` \| `onboarding`)

### Moved / demoted
- Reschedule, Cancel, Checklist, Profile → **More** menu (or expand for checklist)
- Communication-failure honesty copy on Needs Attention → points to **Alerts & Delivery**

### Combined
- Progress + next/blocker on the same meta line (owner group · next item / overdue count)
- Urgency badge + status pill as compact row header

### Retained (frozen)
- Backend onboarding authority, permissions (`onboarding.manage` / `hr_mutate_enabled`)
- Confirm dialogs for mark / waive / remind / reschedule / cancel
- Audit history + tenant isolation contracts
- Mutation-integrity: `usePosthireAction` Promise + confirm; assistant kill still skipped for `web_dashboard`
- Needs Attention ranking/grouping workflow (no reopen beyond polish)

## Final queue & row structure

```
[compact purpose hint]                         [Refresh]
┌ Onboarding queue · N active · M completed ─────────┐
│ filters: Needs attention | In progress | Not started | Completed | All
│ ┌ row ───────────────────────────────────────────┐ │
│ │ urgency · status                               │ │
│ │ name · role/dept                               │ │
│ │ Start · Progress received/required · Next/blocker │
│ │ [Remind]  [⋯ More → Checklist|Reschedule|Cancel|Profile]
│ │ (expand) checklist panel + optional reschedule strip │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

Deep-link: `?page=onboarding&employee=<key>` → expand, sync URL, scrollIntoView, pin synthetic row via detail fetch if not on loaded page.

## Action ownership

| Action | Owner |
|---|---|
| Checklist mark / waive / upload | **Onboarding** |
| Remind / Reschedule / Cancel | **Onboarding** |
| Profile onboarding section | Context + deep-link only |
| Document verification findings | **Compliance** |
| Communication / delivery failures | **Alerts & Delivery** |
| Prioritize + route | **Needs Attention** |

## Mutation success/failure proof

- Client contracts: `PosthireMutationIntegrityContract` + Onboarding confirm paths — **PASS**
- Orchestrator smoke `smoke-test-posthire-mutation-integrity.py` — **PASS** (assistant denied; `web_dashboard` not kill-blocked)
- Production: prior stamp `20260804T062017Z` remains live; this wave is UI-only and does not reopen the kill exemption

## Needs Attention polish (same change)

1. **Removed** duplicated inner Needs Attention heading — refresh toolbar only above the board  
2. **Removed** delivery-failure strip from inbox mount — honesty line routes failures to Alerts & Delivery  

## Screenshots

| File | View |
|---|---|
| `screenshots/onboarding-desktop-en.png` | Queue + expanded hire |
| `screenshots/onboarding-mobile-en.png` | Mobile card density |
| `screenshots/onboarding-desktop-ar.png` | Arabic / RTL |
| `screenshots/onboarding-mobile-ar.png` | Arabic mobile |
| `screenshots/needs-attention-polish-desktop-en.png` | No inner h2 / no delivery strip |
| `screenshots/needs-attention-polish-mobile-ar.png` | AR mobile polish |

Visuals are cream/black queue-first fixtures seeded from live Talal Needs Attention subject (`WATHEFNI-96550252254`).

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-20260804T063521Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-20260804T063521Z
```

## Verdict

| Decision | Result |
|---|---|
| Ship Onboarding Wave 1 refinement to production | **GO** (deployed) |
| Freeze Onboarding surface for this wave | **GO** — ready to freeze after owner visual review |
| Begin Attendance | **NO-GO** until owner reviews this result |
| Reopen Needs Attention workflow | **NO-GO** (polish only) |
| Change mutation kill / backend contracts | **NO-GO** (preserved) |
