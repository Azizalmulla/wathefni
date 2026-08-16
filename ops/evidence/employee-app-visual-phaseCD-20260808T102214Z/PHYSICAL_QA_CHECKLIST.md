# Phase C+D — physical-device checklist (not yet run)

Everything below is a claim the static and behavioural gates **cannot** make. No
part of this has been executed; Phase C+D is locally qualified only.

## Navigation

- [ ] Five tabs render and the labels do not truncate in EN or AR.
- [ ] A company without Payslips shows four tabs with no gap or dead slot.
- [ ] A company with neither Shifts nor Attendance shows no Schedule tab.
- [ ] Bell opens the Inbox; back returns to Home.
- [ ] Cold-start deep link to `/(tabs)/notifications` (the old path) opens the Inbox.
- [ ] Push tap with `flow: payroll` opens Payslips as a tab, not a pushed screen.
- [ ] Push tap for an unentitled module lands on the Inbox, not a dead screen.

## Density and hierarchy

- [ ] Home: the shift time reads as the headline; the "Today at work" label does not compete with it.
- [ ] Home: no two elements route to the same place.
- [ ] Documents: attention, current and history are distinguishable at a glance from arm's length.
- [ ] Documents: open a collapsed year; "Show more" grows it without a jump.
- [ ] Inbox: unread is obvious without reading; activity group stays collapsed.
- [ ] Leave: a one-day request shows one date.
- [ ] Payslips: net pay is the first thing seen on a detail; the PDF is one tap.
- [ ] Bank: the same masked IBAN does not appear twice on one screen.
- [ ] Onboarding: exactly one progress indicator; HR-owned items are named.
- [ ] Profile: name and job title appear once.

## Arabic and RTL

- [ ] Every new row mirrors: icon tile, unread dot, chevron, trailing chip.
- [ ] Section headers with counts read correctly in Arabic numerals.
- [ ] Relative time ("قبل 3 س") reads naturally, not as a literal English calque.
- [ ] Year headings render as Arabic-Indic numerals without thousands separators.
- [ ] Collapse chevrons point correctly in RTL.

## Dynamic Type

- [ ] AX3: rows grow vertically; titles do not clip; chips do not overlap.
- [ ] AX5: the bell badge numeral remains legible and does not escape the bell.
- [ ] AX5: section headers with counts wrap rather than truncate the count.
- [ ] Large text does not push the tab bar content under the home indicator.

## Screen sizes

- [ ] iPhone SE: Home fits its four sections without a cramped tab bar.
- [ ] iPhone SE: a long Arabic department name in Profile wraps rather than clips.
- [ ] Pro Max: rows do not look stretched or empty.

## VoiceOver

- [ ] Bell announces the unread count.
- [ ] An unread inbox row announces its unread state, not just the dot.
- [ ] A collapsible section header announces expanded/collapsed and toggles.
- [ ] "Show more" announces how many more.
- [ ] Every row with an action reaches 44×44.

## Scale

- [ ] A long-tenure QA employee (5+ years of documents and payslips) opens Documents and Payslips without a visible stall.
- [ ] An inbox with 200+ messages scrolls smoothly.

## Regression

- [ ] Pull-to-refresh on every touched screen.
- [ ] Background/foreground: entitlements soft-refresh; nothing flickers.
- [ ] Upload, renew and re-upload still work from Documents and Onboarding.
- [ ] Bank submission and evidence upload unchanged.
- [ ] Leave request and cancel unchanged.
