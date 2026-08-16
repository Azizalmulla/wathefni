# Employee App Visual Refinement Phase A+B — Trust, Terminology, Layout & Colour-System Foundation

Result: **PASS** (static + gate level). Physical iPhone review is still outstanding and is
listed at the bottom; no accessibility or device claim is made here.

Scope guard held: Home navigation, Documents IA, Bank lifecycle presentation, Inbox
density/history, Onboarding progress hierarchy and the bottom-tab product decision were
not restructured. No backend, entitlement, payroll, OCR, migration or onboarding
authority was touched. No new features were started.

---

## 1. Trust + terminology fixes

Every string below changed in both `en.json` and `ar.json`. Key parity is enforced by a
gate, and a new gate fails the build if `canary`, `wave 2a`, `authoritative`,
`payroll-effective`, `released payroll`, `internal build`, `not enforced` or `paci`
reappears in either locale.

| Key | Before | After |
| --- | --- | --- |
| `onboarding.item.civil_id_dual_side_canary` | CANARY — Civil ID front & back | Civil ID — front & back |
| `onboarding.contractErrorTitle` | Checklist update required | Checklist unavailable |
| `onboarding.contractErrorMessage` | This app build expects Wave 2A onboarding (got {{version}} / {{reason}}). Pull to refresh or install the latest internal build. | We could not load your checklist. Pull down to refresh, or update Wathefni to the latest version. |
| `autoLock.diagnosticsTitle` | Auto-lock canary | Auto-lock diagnostics |
| `leave.notEnforced` | Balances are shown for reference and are not enforced. | Your HR team confirms your final balance when they review a request. |
| `remaining.leaveAuthorityNote` | …The status shown in Wathefni is authoritative. | …This is the latest status they have shared. |
| `documents.legitimacyNote` | Statuses show HR review of your upload only. Government verification (PACI / MOI / PAM) is not available. | These statuses show your HR team's review of what you uploaded. |
| `payslips.officialPdfNote` | This PDF is generated from the authoritative released payroll record for this version. | Official payslip issued by your company. |
| `payslips.released` | Released | Issued |
| `payslips.releasedList` | Released payslips | Your payslips |
| `payslips.emptyHint` | When HR releases a payslip to you… | When your company issues a payslip, it will appear here. |
| `bank.subtitle` | Your salary is paid to the account that is payroll-effective. | Your salary is paid into the account shown here. |
| `bank.payrollEffectiveTitle` | Used by payroll | Where your salary is paid |
| `bank.payrollEffectiveChip` / `bank.state.applied` | Payroll-effective | Receiving your salary |
| `bank.payrollEffectiveFrom` | Used by payroll from {{date}} | Receiving your salary since {{date}} |
| `bank.payrollEffectiveUnchangedNote` | Payroll keeps using this account until payroll applies an approved change. | Your salary keeps going to this account until an approved change is applied. |
| `bank.verifiedUnchangedNote` | Your payroll account stays the same until payroll applies an approved change. | Your salary account stays the same until an approved change is applied. |
| `bank.state.pending_payroll` | HR verified · awaiting payroll | Confirmed by HR · being finalised |
| `bank.next.pending_payroll` | HR verified your details. Payroll is reviewing them before they become effective. | Your HR team confirmed these details. Your company is finalising the change. |
| `bank.next.approved` | Payroll approved the change. It is not used for payroll until payroll applies it. | Your change is approved. Your salary moves to this account once your company applies it. |
| `bank.next.applied` | Your approved bank details are now used for payroll. | Your salary is now paid into this account. |
| `bank.formHint` | …HR verifies every change; payroll applies it before it is used. | …Your company checks every change before your salary moves. |
| `onboarding.handledByOthers` | Handled by HR / payroll | Handled by your company |
| `onboarding.handledByOthersNote` | {{count}} items are handled by HR or payroll… | Your company is handling {{count}} items… |
| `remaining.featureEyebrow` | Capability update | Not available |

Removed keys (and their call sites): `payslips.paymentDateUnknown`,
`deviceSecurity.statusActive`. Added: `documents.item.other`.

### Raw backend values no longer shown as display text

- **Onboarding contract error** no longer interpolates the lifecycle version or the machine
  `reason`. Both still reach telemetry through `projectOnboardingLifecycle`.
- **Documents review status**: `statusLabel()` returns the translated status, or
  "Status unavailable" — it can no longer fall through to `pending_hr_review`.
- **Documents names**: `documentsHierarchy` now carries `documentType` and a nullable human
  `label` separately. The registry branch dropped its `filename || fileId` fallback, so a
  storage key can never appear where a document name belongs. The view resolves i18n name →
  API label (rejected if it matches a `snake_case` key shape) → "Document".
- **Documents rejection reason** is suppressed when the stored value is a machine code
  rather than something a human wrote.
- **Profile** no longer renders the Company and Employee ID rows. `/app/profile` only
  exposes `company_code` and `employee_key`, and the employee key is a company prefix plus a
  phone number. Showing part of it would have meant inventing a staff number. *This is the
  one judgement call in the phase and is easy to reverse* — see "Owner decisions".
- **Settings** dropped the hardcoded `Status: Active` row; the panel only ever describes the
  device in the employee's hand, so the value could never say anything else.

The auto-lock diagnostics panel (raw build marker, update id, flag values, employee key)
remains behind `EXPO_PUBLIC_LOCAL_AUTO_LOCK_DIAGNOSTICS === '1'`, which is set in no build
profile in `eas.json`. It is not employee-reachable; only its title string changed.

## 2. Payslip payment-date defect

`app/payslips.tsx` never read `payslip.payment_date`; it printed
`Payment date: Not available` unconditionally. It now reads the field, renders the row with
the real formatted date when payroll has recorded one, and omits the row entirely otherwise.
No date is ever synthesised and payroll authority is unchanged. The gate that previously
asserted the presence of `paymentDateUnknown` — encoding the bug — was replaced with one
asserting the corrected behaviour.

## 3. Layout token system

```
layout.pageMargin   16   horizontal margin for all page content
layout.pageTop      12   space above the first element after the nav row
layout.sectionGap   16   between top-level sections
layout.cardGap       8   between sibling cards/rows in one section
layout.tabBarBase   60   tab bar content height; bottom inset added on top
layout.scrollBottom 32   clearance under the last element
layout.touchTarget  44   minimum interactive size
layout.focusMargin  24   full-screen single-task surfaces outside the tab shell
```

Screens previously drifted across 12 / 16 / 24pt margins and 24 / 40 / 120pt bottom padding.
`focusMargin` is the one deliberate exception: activation, PIN and biometric opt-in are
single-task, list-free screens with no tab bar, so the wider margin is now a named role
rather than drift.

`src/components/layout.tsx` provides the shared chrome: `PageScreen` (cream ground + top
safe area, RTL direction) and `PageScrollView` (one margin, one rhythm, correct bottom
clearance, `keyboardShouldPersistTaps="handled"`, interactive dismiss, and
`automaticallyAdjustKeyboardInsets` on iOS so the leave-request form no longer needs its own
keyboard handling).

## 4. Bottom-tab / safe-area correctness

The tab bar was a flat `height: 72` with no bottom inset, so on devices with a home
indicator the labels sat inside the inset and page content ran underneath the bar.

- `app/(tabs)/_layout.tsx` now sizes the bar as `layout.tabBarBase + insets.bottom` with
  `paddingBottom: insets.bottom`.
- `useScrollBottomPadding()` reads the tab bar's own measured height back out of
  `BottomTabBarHeightContext` (which already includes the inset) and falls back to
  `insets.bottom` on screens pushed above the tabs, where there is no bar but the home
  indicator still has to be cleared.

No screen carries a hand-tuned bottom number. `@react-navigation/bottom-tabs` was promoted
from a hoisted transitive of `expo-router` to an explicit `~6.5.7` dependency;
`expo install --check` reports dependencies up to date and the lockfile changed by 2 lines.

## 5. Responsive text foundation

- **Profile rows** no longer pin the label to a fixed 96pt column with the value floated to
  the opposite edge. Label sits above value, both starting at the same edge, so long emails,
  long Arabic department names and large type wrap down the card instead of competing for
  horizontal space. The same layout is correct LTR and RTL.
- **Bank** IBAN / account-holder values wrap rather than truncate and are `selectable`, so
  the full value is always copyable.
- **Payslip line rows**: the amount keeps its width (`flexShrink: 0`) and the label wraps —
  previously the amount could be squeezed by a long label.
- **Home module tiles** moved from `width: '47%'` to `flexBasis`, so a single tile fills the
  row rather than sitting orphaned.
- `numberOfLines` added where truncation is safe (module titles, button labels, status
  chips, metric labels); omitted everywhere a value carries meaning.

## 6. Dynamic Type foundation

Scaling stays enabled everywhere. `theme.typeScaling` sets ceilings by role — display 1.6,
heading 1.8, body 2.0, chip 1.6 — so a title cannot consume a small screen before the body
copy is reachable, while body and action text keep scaling further. Display size dropped
from 34 to 30 with line height corrected 43 → 36; the leave balance figure moved off a
hardcoded 38px onto the display token. Fixed-height boxes that would clip became
`minHeight` + padding: the primary button, the onboarding progress counter, and the inbox
unread badge. The serif brand language is unchanged.

## 7. Colour token system

```
ground    bg #F9F3E5 · surface #FFFCF4 · surfaceMuted #F0E8D8 · border #E5DAC6
          ink #1B1A17 · subtle #5E5850 · primary #1B1A17 · primaryText #FFFFFF
ambient   butter #F6DA92 · pink #F7CFE3 · olive #DCE2BB · sky #C7D9EF · lilac #D6C9F0
semantic  success #2A6241 · warning #8A4A15 · danger #9B3239 · accent #93356B
```

Retired: `chip`, `skeleton`, `accentSoft`, `successSoft`, `warningSoft`, `dangerSoft`, and
the `pastel*` prefixes. 22 tokens → 18. The soft-status tokens were the core defect: `sage`
and `successSoft` measured dE 1.7 apart, so a decorative card and an "approved" status were
literally the same colour. `blush` → `pink` and `sage` → `olive` were renamed rather than
re-valued in place, because the hues genuinely changed and a stale name would have been
worse than the churn.

Verified by `scripts/verify-color-system.py` (32 checks) against the tokens as written in
`theme.ts`:

- ink on every ground and ambient fill: **11.2:1 – 17.0:1** (AA body, not just large).
- muted text on every ground and ambient fill: **4.5:1 – 6.9:1** (AA body).
- every semantic colour on `surface`: **6.7:1 – 7.0:1** (AA body and AA UI).
- closest ambient-to-semantic pair: butter/warning **dE 54.6** (threshold 10).
- closest ambient pair: sky/lilac **dE 14.5** (threshold 8).
- closest semantic pair: warning/danger **dE 29.4** (threshold 10).

## 8. Colour assignment: identity, never list position

All `index % 2 ? … : …` tone selection is gone and the gate fails if it returns.

| Surface | Ambient tone | Reasoning |
| --- | --- | --- |
| Schedule | sky | module identity; today's card and upcoming cards share it |
| Leave | olive | on the balance cards only — request rows stay cream so a long list never becomes a monochrome screen |
| Documents | lilac | attention + current cards; history is cream, which demotes it without moving it |
| Payslips | butter | list rows and the detail hero |
| Onboarding | lilac (your actions), pink (completion) | colour sits on the employee's own work, not on the summary card |
| Profile / identity | pink | the identity hero and the Home avatar |
| Bank | butter on "Where your salary is paid" only | everything else cream; the chip carries state |
| Home | sky today, butter tasks, module tones on tiles | caught-up and the inbox strip are cream — Inbox is platform, not a module, so it takes no identity |

## 9. Semantic status treatment

`StatusChip` is now outline + semantic text + icon on `surface`, never a pastel fill. The
label always states the condition in words, so nothing depends on colour alone. Converted
away from pastel-as-status: Schedule's Present/Late/Absent metrics (neutral tiles, semantic
figure), Bank's state-driven card fills, Onboarding's section-driven card fills, Documents
status (plain text → semantic chip), Inbox unread (pink wash → accent edge + dot), and every
error card (Home, Profile, Schedule, States, Activation feedback) which now uses a neutral
surface with a danger edge.

## 10. Colour usage discipline

Cream and ink dominate; each screen now carries one or two deliberate tones instead of four
or five decorative ones. Home went from six pastel surfaces to module-meaningful tones plus
cream; Bank from four state-coloured cards to one; Onboarding from four to two. No
pastel-on-pastel chips remain. Six untokenised `rgba()`/hex literals were replaced with
`surfaceMuted` or `border`; the translucent whites had to go anyway, because they became
invisible on the cream cards this phase introduced. The gate fails on any new colour literal
in a screen.

## 11. Accessibility baseline

`SectionTitle` and the shared `SectionLabel` gained `accessibilityRole="header"` (editorial
headings already had it). Text labels are preserved alongside every status. Reduced-motion
handling in `FadeIn`/`MotionProgressBar` is untouched. Touch targets moved onto
`layout.touchTarget` (44) rather than scattered literals — the a11y scan was taught to count
the token as well as the literal, since tokenising it had otherwise hidden compliant targets
from the heuristic. No contrast was reduced anywhere; several pairings improved.

**No physical accessibility pass is claimed.**

---

## Files migrated

Shared: `src/theme.ts`, `src/components/layout.tsx` (new), `src/components/premium.tsx`,
`src/components/ui.tsx`, `src/components/States.tsx`, `src/components/AccessStates.tsx`,
`app/(tabs)/_layout.tsx`.

Screens: `HomeView`, `ScheduleView`, `ProfileView`, `DocumentsView` (+ `documentsHierarchy`),
`RemainingViews` (Leave, Inbox, Settings, Privacy & Support, shared `Page`), `BankView`,
`OnboardingView`, `app/payslips.tsx`, `ActivationView`, `PinView`, `BiometricOptInView`.

Copy: `src/i18n/en.json`, `src/i18n/ar.json` (580 keys each, parity enforced).

Gates: `scripts/verify-color-system.py` (new), `scripts/verify-capability-foundation.py`,
`scripts/a11y-i18n-static-scan.py`.

## Regressions

None found. Three gates needed updating because they asserted the old behaviour, and each
was replaced with a stricter check rather than relaxed:

1. `verify-capability-foundation.py` required `paymentDateUnknown` to be present in the
   payslips screen — it asserted the bug. Replaced with a check that `payment_date` is read
   and the row is conditional, plus that the removed key is gone from both locales.
2. The same script required the literal phrase "authoritative released payroll record".
   Replaced with an exact-match assertion on the new copy, keeping the original
   source-neutrality intent, plus a new sweep that fails on eight internal terms across both
   locales.
3. `a11y-i18n-static-scan.py` counted the literal `minHeight: 44` and dropped below its
   threshold once targets moved onto the token. Taught to count both spellings.

`documents-hierarchy-test.js` still passes unchanged despite the `DocumentHistoryEntry`
shape change, which confirms the dedupe behaviour was preserved.

## Evidence

- `local-gates.txt` — full output of typecheck and all nine gates.
- `source-stamp.txt` — branch, HEAD, changed files. Note the diffstat spans all uncommitted
  work on `authority-cutover`, including Phases 0–4, not only this phase.
- `PHYSICAL_QA_CHECKLIST.md` — what still needs a device.

## Owner decisions (not objective fixes)

1. **Profile Company + Employee ID rows removed.** The API exposes only backend keys. The
   alternative was to print a partial key as a staff number. If you want an ID visible, the
   correct fix is a real `staff_number` / `company_name` in `/app/profile`, and the rows come
   straight back.
2. **Butter carries two meanings** — Payslips identity, and "needs you" emphasis on Home and
   Documents attention. They never co-occur on one screen, but it is a shared tone.
3. **Bank uses cream almost throughout**, with butter only on the salary-destination card.
   Calm and disciplined; you may want more warmth there.

## Remaining for the next Density / Hierarchy phase

- Home hierarchy: the destination grid duplicates the bottom tabs, and the bottom-tab
  product decision is still open.
- Documents IA: history is uncapped and renders every entry.
- Bank lifecycle presentation: four stacked cards still restate one another.
- Inbox density and history policy.
- Onboarding progress hierarchy: "Where you stand" and "Overall progress" still duplicate.
- `EXPECTED` / `RECORDED` all-caps block labels on Schedule read as shouting.
- Empty states still look unfinished (audit item, deliberately untouched here).
- Manager row on Profile is not actionable.
- Physical AX3 / AX5 Dynamic Type qualification and VoiceOver order.
