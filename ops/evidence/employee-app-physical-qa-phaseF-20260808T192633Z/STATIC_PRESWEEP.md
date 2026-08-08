# Physical QA — static pre-sweep against the shipped bundle

Run against commit `1e77bf6`, the exact source of canary OTA
`019fe2f8-0363-7f93-8095-2abeb8647013`. Working tree was clean, so what was
analysed is what the phone is running.

This is not a physical pass. It exists to shorten the owner's device session by
settling everything code can settle first.

## Automated gates — all green

TypeScript `--noEmit` clean. All 13 qualification gates pass, 349 checks:

| Gate | Result |
| --- | --- |
| `composition-shapes-test.js` | PASS (61 checks) |
| `density-hierarchy-test.js` | PASS (24) |
| `documents-hierarchy-test.js` | PASS (7) |
| `feature-unavailable-copy-test.js` | PASS (9) |
| `high-value-additions-test.js` | PASS (23) |
| `pin-crypto-selftest.js` | PASS |
| `push-follow-through-test.js` | PASS (14) |
| `a11y-i18n-static-scan.py` | PASS (21) |
| `session-refresh-static-proof.py` | PASS (8) |
| `verify-capability-foundation.py` | GREEN |
| `verify-color-system.py` | PASS (32) |
| `verify-density-hierarchy.py` | PASS (71) |
| `verify-high-value-additions.py` | PASS (79) |

## Confirmed good (no device time needed)

**List scalability.** Every history that grows over an employee's tenure is paged
through `usePagedList` + `ShowMoreButton`: payslips (`payslips.tsx:303`), inbox
earlier and system activity (`RemainingViews.tsx:181-182`), leave requests
(`:296`), documents history (`DocumentsView.tsx:444`). No unbounded `.map()` over
growable data survives. The remaining `.map()` calls are over onboarding task
groups, which are bounded by the journey definition.

**Dynamic Type is not suppressed.** `allowFontScaling={false}` appears nowhere, so
text scales. 38 of 236 `<Text>` elements carry `maxFontSizeMultiplier`, which caps
scaling only where a bound was deliberate.

**Spacing is direction-agnostic.** Zero physical `marginLeft/Right`,
`paddingLeft/Right` or `borderLeft/RightWidth` in the whole app. Only logical
`start`/`end` properties are used. Spacing will mirror correctly in Arabic on its
own.

## A — objective defect candidate (needs one device observation)

### A1. Rows may be double-flipped in Arabic

`src/i18n/index.tsx:48-58` forces native RTL for Arabic (`I18nManager.forceRTL(true)`
plus `swapLeftAndRightInRTL(true)`) and reloads the process so it takes effect. Under
forced RTL, Yoga already lays `flexDirection: 'row'` out right-to-left.

On top of that, 42 sites across 11 files add `flexDirection: 'row-reverse'`
conditionally when `isRTL`. The shared compact row is the clearest case:

```207:208:apps/wathefni-employee-mobile/src/components/lists.tsx
  rowMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rowReverse: { flexDirection: 'row-reverse' },
```

applied at `lists.tsx:63` as `isRTL && styles.rowReverse`. Reversing an already-RTL
row returns it to left-to-right, so in Arabic the icon would sit on the left and the
chevron on the right — Latin order inside an Arabic screen.

Two things make this look like a real defect rather than a deliberate choice. The
codebase uses only logical `start`/`end` spacing properties and `borderEndWidth`,
which auto-flip and therefore only make sense if native RTL is expected to be doing
the work. And no gate asserts the `row-reverse` pattern and no document explains it.

Counting against it: Arabic has been looked at in earlier phases and nobody reported
mirrored rows, and mirrored-but-plausible layouts are easy to miss.

Because it is a 42-site change and I cannot see the screen, this needs one look
before anything is touched. It is the first item on the checklist and takes five
seconds to settle.

Affected: `lists.tsx`, `HomeView`, `ScheduleView` (11 sites), `RemainingViews` (10),
`ProfileView` (4), `ActivationView` (4), `OnboardingView` (3), `DocumentsView` (3),
`payslips.tsx` (2), `BankView`, `premium.tsx`.

## B — clear inconsistencies (low-risk, fix after confirmation)

### B1. `countryCode` is rigid where its own sibling is flexible

```296:302:apps/wathefni-employee-mobile/src/features/activation/ActivationView.tsx
  phoneRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center' },
  rowReverse: { flexDirection: 'row-reverse' },
  countryCode: {
    height: 48,
```

`phoneRow` uses `minHeight` so it can grow; the `countryCode` box beside it is
pinned to `height: 48` while `countryText` scales freely. At AX5 the `+965` can clip.
Same component, two different rules — the fix is `minHeight`.

### B2. Home avatar initials can outgrow their circle

`HomeView.tsx:410-418` — a 38×38 pill containing `avatarText` with no
`maxFontSizeMultiplier`. At AX5 the initials scale but the circle does not. Either
cap the text or let the circle grow.

## C — subjective, owner decision only

Nothing was changed and nothing is recommended unilaterally here. The density,
colour-restraint and card-versus-row judgements from Phases C+D are exactly the
kind of thing that should be judged on glass, not asserted from source. They are
listed as prompts in the checklist rather than as findings.

## Carried over from deploy

Neither canary employee has a document with a dated expiry, so the "expires in N
days" Home copy cannot render on this device as data stands. Aziz's only renewal is
a rejected re-upload with a null expiry, which correctly falls back to the generic
label. Verifying that copy needs a seeded fixture — an owner decision before QA.
