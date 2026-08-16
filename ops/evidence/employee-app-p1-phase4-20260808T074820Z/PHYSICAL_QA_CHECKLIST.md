# Employee App — Physical Visual QA & Responsiveness checklist

Stamp: Phase 4 `20260808T074820Z` · OTA group `f9fc3c25-f535-40e0-b273-ef3214da93c2` · canary Aziz/Talal only.

**Do not claim visual quality from static tests.** This checklist is for the owner/device pass.

Install: force-quit → reopen Employee App on canary build (runtime `0.1.0`) until Settings/diagnostics (if visible) or behaviour confirms Phase 4 OTA.

## Languages / layout
- [ ] EN LTR — full walk
- [ ] AR RTL — full walk (mirroring, chevrons, reading order)
- [ ] Language switch + restart path stays signed in

## Compositions (entitlement matrix)
- [ ] 1-module Home
- [ ] 2-module Home
- [ ] 4-module Home
- [ ] Full-suite Home
- [ ] Zero / sparse Home does not look “broken empty”

## Per screen — states
For each screen below, check **loading · refreshing (PTR) · ready · genuine empty · partial authority · error · offline/stale**. A network failure must never read as a business fact.

### Home
- [ ] Destinations only (no duplicate quick actions)
- [ ] Tasks open entitled routes; unavailable link is calm
- [ ] Onboarding journey appears only when incomplete
- [ ] Inbox unread badge honesty

### Schedule
- [ ] Opens when shifts **or** attendance entitled
- [ ] Today expected vs recorded
- [ ] Authority unavailable is informational, not empty
- [ ] Read-only (no clocking UI)

### Leave
- [ ] List / balances / cancel (when allowed)
- [ ] Request form
- [ ] FeatureUnavailable copy when module off

### Documents
- [ ] Attention / Current / History hierarchy
- [ ] No duplicate current files in History
- [ ] Detail open / cancel mid-download
- [ ] Renew upload + legitimacy note
- [ ] Partial compliance never looks like “no documents”

### Payslips
- [ ] List period labeling + net prominence
- [ ] Detail earnings / deductions
- [ ] PDF download + share
- [ ] Deep link `payslip_id` opens detail when entitled
- [ ] Source-neutral honesty copy

### Profile
- [ ] Personal → Employment → Bank → Account
- [ ] No Docs/Payslips shortcuts
- [ ] Bank only here

### Bank
- [ ] Verified / submitted / rejected states
- [ ] Evidence open via authorized stream
- [ ] Controlled-rollout explained state (not error loop)

### Inbox
- [ ] Unread / earlier sections
- [ ] Tap → entitled deep link; unentitled calm alert
- [ ] Push tap (when a push arrives) follows through or falls back to Inbox
- [ ] HR title/body shown as entered (no fake translation)

### Settings / security
- [ ] Push preference (when registration enabled on build)
- [ ] PIN change / biometric / auto-lock
- [ ] Device-security retry
- [ ] No Bank entry here
- [ ] Diagnostics remain build-gated in production

### Onboarding
- [ ] Checklist / upload / preview
- [ ] Demotes when complete
- [ ] Bank CTA only when backend grants `open_bank`

### Auth / session (device)
- [ ] Foreground resume soft refresh (no nav corruption)
- [ ] Post-PIN unlock refresh
- [ ] Post-Face ID unlock refresh
- [ ] Pull-to-refresh on major surfaces
- [ ] Background → revoke module entitlement → resume removes privileged surface
- [ ] Background → revoke app access → AccessState (no stale privileged UI)
- [ ] Airplane / offline → reconnect recovers without false empty facts
- [ ] Unlock overlay never bypassed by push follow-through

## Accessibility (device judgment)
- [ ] VoiceOver labels / hints / reading order
- [ ] 44pt+ targets
- [ ] Dynamic Type — no clipped primary actions
- [ ] Reduced motion — animations calm
- [ ] Status not color-only

## Responsiveness / visual (owner)
- [ ] First viewport hierarchy per screen
- [ ] Safe areas / notches / home indicator
- [ ] Keyboard avoiding on forms
- [ ] No overlapping chrome under unlock overlay

## Sign-off
- [ ] Aziz canary OK
- [ ] Talal canary OK
- [ ] Defects filed (if any) with screen + state + locale
- [ ] Ready to freeze Employee App **only after** this pass + explicit freeze decision
