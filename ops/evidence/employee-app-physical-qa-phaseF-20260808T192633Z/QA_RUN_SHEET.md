# Physical QA run sheet — owner session

Device on canary OTA `019fe2f8-0363-7f93-8095-2abeb8647013` (runtime 0.1.0,
source `1e77bf6`), confirmed by the five-tab bar with Inbox in the Home header.

Ordered so that anything which would invalidate later observations is settled
first. Report findings as `screen — what you saw`; classification into A/B/C is
mine, and nothing subjective gets changed without your call.

---

## Step 0 — the one check that gates the Arabic half of this session

Switch the app to Arabic and let it reload. Open **Inbox** (bell on Home), or any
list: Leave history, Documents history, Payslips.

Look at a single row and answer one question:

> Is the chevron on the **left** edge of the row, with the icon and text starting
> from the **right**?

- **Chevron left, content right → correct.** Arabic is fine, continue to Step 1.
- **Chevron right, content starting from the left → A1 is confirmed.** Stop the
  Arabic pass and tell me. Rows are double-flipped across 42 sites in 11 files and
  every later Arabic observation would be polluted. It is one systemic fix, not
  eleven screen fixes.

Switch back to English before Step 1 either way.

---

## Step 1 — English critical path

For each screen: hierarchy, spacing, density, alignment, whether the bottom content
clears the tab bar, and whether anything is clipped, overlapping or repeated.

| # | Screen | Look specifically at |
| --- | --- | --- |
| 1.1 | Home | Is today's work the focal point, above the decorative label? Bell obvious without shouting? Any duplicate route to Leave or Schedule? Does the last card clear the tab bar? |
| 1.2 | Schedule | Expected vs Recorded instantly readable? Times legible, status chips not overpowering? Overnight shift renders sensibly? |
| 1.3 | Leave | History compact? A single-day request showing **one** date, not the same date twice? Balance present but not shouting? |
| 1.4 | Request Leave | Balance for the **selected** leave type. Pick Thu 13 → Mon 17 Aug: it must say **3 days**, not 5. Keyboard must not hide the notes field or Submit. |
| 1.5 | Payslips | Year grouping; net pay prominent; payment date row **absent** rather than "Not available"; amounts not clipped. |
| 1.6 | Payslip detail → PDF | Opens, shares, and the share sheet dismisses cleanly. |
| 1.7 | Documents | Needs attention clearly above Current, History compact and grouped. Long document labels wrap rather than clip. No internal wording. |
| 1.8 | Inbox | Compact rows; unread obvious without relying on colour alone; relative time reads naturally; activation history demoted rather than dominant. |
| 1.9 | Profile | No hero value repeated in the details below. Manager row shows the name, and Call appears **only** if a number exists. Phone/email formatting clean. |
| 1.10 | Bank | Answers "where does my salary go, and is it confirmed?" in one surface. The masked IBAN must not repeat across several cards. |
| 1.11 | Onboarding | One progress indicator, one next action, employee-owned vs HR-owned legible. |
| 1.12 | Settings | No internal build or status strings; nothing hardcoded as "Active". |

Known and expected: the Home document task shows the **generic** label rather than
"expires in N days", because neither canary employee has a document with a dated
expiry. Not a defect. Tell me if you want a fixture seeded to see that copy.

---

## Step 2 — Arabic repeat

Only if Step 0 came out correct. Same twelve screens, plus: tab order, chevron
direction, status chips, and mixed Arabic/Latin content — email, phone, IBAN, KWD
amounts, dates and Schedule time ranges. Then switch EN → AR → EN and confirm the
session survives and navigation is not corrupted.

---

## Step 3 — Dynamic Type

Settings → Accessibility → Display & Text Size → Larger Text. Test **AX3** and
**AX5** on Home, Request Leave, Payslip detail, Documents and Profile.

Critical information and actions must stay readable, reachable and unclipped, and
should reflow vertically rather than shrink. Two known suspects from the static
sweep, worth looking at directly: the **`+965` box on Activation** (B1) and the
**initials circle on Home** (B2) — both are pinned to a fixed height while their
text scales.

---

## Step 4 — VoiceOver

Focus order, section headings, icon-button labels, unread announced as text, status
not colour-only, and reduced motion respected.

---

## Step 5 — Real-device interactions

Pull to refresh · background and foreground · PIN unlock · Face ID · Face ID cancel
falling back to PIN · airplane mode then reconnect · push tap from foreground,
background and killed · document upload and renew · PDF open and share · native date
picker · manager Call action.

Note: `expo-screen-detector` is absent from the installed binary, so screen-lock
detection falls back to timeout-based auto-lock. Pre-existing, unchanged by this
release, and not a QA finding.

---

## Reporting

Send them as they come, in the form `Documents — long Arabic label clipped at the
second line`. I will classify each as:

- **A** objective defect — clipping, overlap, wrong RTL, unreachable action, false
  state, broken accessibility. Fixed immediately.
- **B** clear inconsistency with the established system. Fixed when low-risk.
- **C** subjective design decision. Recorded and brought to you before any change.
