# Employee App — Physical Visual QA checklist (Phases A–E consolidated)

**Status: NOT RUN.** Nothing in this file has been executed. It is the script for
the device pass, not a record of one.

This consolidates the Phase C+D checklist and adds Phase E. Items are grouped by
what they prove, not by screen, so the pass can be done in a few sittings without
re-navigating the same flows.

Classification for anything found: **A** objective defect (clipping, overlap,
wrong RTL, unreachable action, false state, broken accessibility) → fix
immediately · **B** clear inconsistency with the established system → fix when
low-risk · **C** subjective design preference → record, do not change.

---

## 0. Build confirmation — do this first, and stop if it fails

- [ ] Installed update ID recorded, and it is the update containing Visual A–E.
- [ ] Runtime version matches the installed native build (`appVersion` policy, `0.1.0`).
- [ ] Source/commit stamp recorded.
- [ ] Rollback update ID recorded and known-good.
- [ ] Device model and iOS version recorded.
- [ ] `GET /app/leave/duration` returns 401 (not 404) against the API the device is
      pointed at — otherwise Phase E's duration line cannot appear and Leave cannot
      be qualified.
- [ ] Force-quit and relaunch before judging anything.

**A stale build invalidates every row below.**

---

## 1. Phase E additions — the newest and least proven

### Request Leave — balance

- [ ] Balance appears for the **selected** leave type, and changes when the type changes.
- [ ] Switching type does not briefly show the previous type's number.
- [ ] A company with balances disabled shows **no** balance block at all — not a zero.
- [ ] A leave type with no balance row shows nothing for that type.
- [ ] **Regression watch:** no leave type anywhere reads "0 days available" unless the
      balance is genuinely zero. This was live before Phase E and is the single most
      important thing to confirm on device.
- [ ] The non-enforcement note reads as reassurance, not as a disclaimer wall.
- [ ] `can_take_from` line appears only when the balance is not yet takeable.

### Request Leave — duration

- [ ] Selecting Thu→Mon over a Fri/Sat weekend reads **3 working days**, not 5.
- [ ] A single working day reads "1 working day", not "1 working days".
- [ ] A Fri–Sat-only range says there are no working days rather than showing 0.
- [ ] With the device offline, the duration line is **absent** — no zero, no spinner stuck.
- [ ] The line does not reflow or jump as the picker closes.
- [ ] The summary block fits without clipping at AX3 and in Arabic.

### Profile — manager contact

- [ ] Manager name shows; number beneath it is grouped and readable.
- [ ] Call button opens the iOS dialler with the correct number, including the +965.
- [ ] Cancelling the call sheet returns cleanly with no state change.
- [ ] A manager record without a usable phone shows **no** call button.
- [ ] The call button is comfortably tappable and not hit accidentally while scrolling.
- [ ] Only one contact action exists. **No WhatsApp in this phase.**

### Inbox — relative time

- [ ] A message from seconds ago reads "Just now".
- [ ] Minutes, hours and "Yesterday" read naturally in EN and AR.
- [ ] Older messages fall back to a localized date rather than a large day count.
- [ ] VoiceOver announces the exact timestamp alongside the relative one.
- [ ] Arabic numerals render in the Arabic locale without Latin/Arabic mixing.

### Home — document expiry task

- [ ] An employee with an expiring document sees the document named and the days stated.
- [ ] The day count matches the expiry date in Documents — no off-by-one across midnight.
- [ ] An already-expired document says expired, not "-3 days".
- [ ] A renewal with no expiry date falls back to the generic label.
- [ ] The task still opens Documents.

### Payslips — year grouping

- [ ] A company with one year of payslips shows the year heading with **no** collapse control.
- [ ] Multi-year: most recent open, older collapsed, expanding is smooth.
- [ ] Same single-year behaviour in Documents history.

---

## 2. Navigation (Phase C+D, must not have regressed)

- [ ] Five tabs render; labels do not truncate in EN or AR.
- [ ] A company without Payslips shows four tabs with no gap or dead slot.
- [ ] A company with neither Shifts nor Attendance shows no Schedule tab.
- [ ] Bell opens the Inbox; back returns to Home.
- [ ] Cold-start deep link to the old `/(tabs)/notifications` path opens the Inbox.
- [ ] Push tap with `flow: payroll` opens Payslips as a tab, not a pushed screen.
- [ ] Push tap for an unentitled module lands on the Inbox, not a dead screen.
- [ ] No two elements on Home route to the same place.

---

## 3. Density and hierarchy (Phase C+D)

- [ ] Home: the shift time reads as the headline; "Today at work" does not compete.
- [ ] Documents: attention / current / history distinguishable at arm's length.
- [ ] Documents: opening a collapsed year and "Show more" grows without a jump.
- [ ] Inbox: unread obvious without reading; activity group stays collapsed.
- [ ] Leave: a one-day request shows one date.
- [ ] Payslips: net pay is the first thing seen on a detail; PDF is one tap.
- [ ] Bank: the same masked IBAN does not appear twice on one screen.
- [ ] Onboarding: exactly one progress indicator; HR-owned items are named.
- [ ] Profile: name and job title appear once.

---

## 4. Composition shapes — each needs a real tenant or seeded canary

| | Configuration | Home intentional? | Tabs correct? | No filler? |
|---|---|---|---|---|
| A | Documents only | [ ] | [ ] | [ ] |
| B | Leave + Documents | [ ] | [ ] | [ ] |
| C | Leave + Documents + Schedule + Payslips | [ ] | [ ] | [ ] |
| D | Full suite | [ ] | [ ] | [ ] |
| E | Onboarding active | [ ] | [ ] | [ ] |
| F | Onboarding complete | [ ] | [ ] | [ ] |

- [ ] No blank tab slots in any configuration.
- [ ] Sparse companies look deliberately designed, not stripped.

---

## 5. Long content — no horizontal overflow, no clipped essential value

Seed or find a record for each, then check every screen it appears on:

- [ ] Long employee name (35+ chars) — header, hero, Profile.
- [ ] Long job title.
- [ ] Long Arabic department name.
- [ ] Long email.
- [ ] Full IBAN, EN and AR.
- [ ] Large KWD amount with 3 decimals.
- [ ] Long document label.
- [ ] Long notification title and body.
- [ ] Long leave reason.

---

## 6. Arabic / RTL — full critical path, not a spot check

- [ ] Tab order mirrors correctly.
- [ ] Chevrons and back arrows point the right way on every pushed screen.
- [ ] Status chips sit on the correct side.
- [ ] **Double-flip watch:** no screen where native RTL and a manual directional
      style cancel out, leaving LTR layout inside an RTL page.
- [ ] Mixed Arabic/Latin (email, IBAN, phone) does not reorder mid-string.
- [ ] Schedule time ranges read in the correct order.
- [ ] Dates and currency localize correctly.
- [ ] EN → AR → EN keeps the session and does not corrupt navigation.

---

## 7. Dynamic Type — normal, AX3, AX5

- [ ] Nothing critical clipped or overlapping at AX5.
- [ ] Primary actions still reachable by scrolling at AX5.
- [ ] Text reflows vertically rather than shrinking.
- [ ] Bottom content still clears the tab bar and home indicator at AX5.
- [ ] Request Leave summary block and Payslip net pay survive AX5.

---

## 8. VoiceOver

- [ ] Focus order is sensible on Home, Documents, Payslips, Profile.
- [ ] Section headings navigate by heading rotor.
- [ ] Icon-only buttons (bell, call, download, back) have useful labels.
- [ ] Unread state is announced, not implied by colour.
- [ ] Onboarding progress is understandable without seeing the bar.
- [ ] No status conveyed by colour alone anywhere.
- [ ] Reduced Motion is respected.

---

## 9. Real-device interactions

- [ ] Pull-to-refresh on every list screen.
- [ ] Background → foreground refresh.
- [ ] PIN unlock.
- [ ] Face ID; Face ID cancel → PIN fallback.
- [ ] Airplane mode → stale/offline state is honest → reconnect recovers.
- [ ] Push tap: foreground, background, killed.
- [ ] Document upload / renew / re-upload.
- [ ] PDF open and share; **no temp file retained after share**.
- [ ] Native date picker.
- [ ] Keyboard never hides the leave notes field or submit button.
- [ ] Manager Call action.
- [ ] App-access removal while backgrounded → clean lockout, no crash.

**Do not start Auth Wave 2 Phase 6.**

---

## 10. Screens to judge, not just render

For each: hierarchy · typography · spacing · density · card/list treatment ·
colour · alignment · tap targets · safe areas · scroll reachability · keyboard ·
sheets · loading · empty · error · offline.

Activation · Home · Schedule · Leave · Request Leave · Documents · document
detail · upload/renew · Payslips list · Payslip detail · PDF/share · Inbox ·
Profile · Bank · Settings/security · Onboarding.

Judge against: simple, premium, calm, modern, useful, trustworthy. Less is more.
Keep the warm cream foundation, ink anchors, serif character and restrained
pastels. Flag generic-HR density, decorative card spam, oversized empty
surfaces, repeated information, unnecessary explanatory copy, excess colour.
