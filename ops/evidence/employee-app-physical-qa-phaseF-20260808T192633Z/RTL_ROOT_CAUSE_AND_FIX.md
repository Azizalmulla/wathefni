# A1 — Arabic was mirrored twice. Root cause, proof, fix.

Settled without a device. The question "does `row-reverse` under RTL flip a row
back to Latin order?" is not a matter of visual opinion — it is decided by the
layout engine, and that engine's source ships in `node_modules`.

## Proof 1 — Yoga reverses `row` on its own

`react-native/ReactCommon/yoga/yoga/algorithm/FlexDirection.h`, RN 0.74.5:

```cpp
inline FlexDirection resolveDirection(
    const FlexDirection flexDirection,
    const Direction direction) {
  if (direction == Direction::RTL) {
    if (flexDirection == FlexDirection::Row) {
      return FlexDirection::RowReverse;
    } else if (flexDirection == FlexDirection::RowReverse) {
      return FlexDirection::Row;
    }
  }
  return flexDirection;
}
```

Under RTL, `Row` becomes `RowReverse` — and `RowReverse` becomes **`Row`**. A
hand-written `row-reverse` for Arabic therefore resolves to a plain left-to-right
row.

## Proof 2 — Arabic really does reach Yoga as RTL

Two independent paths, either of which is sufficient:

- `src/i18n/index.tsx:196` renders everything inside
  `<View style={[styles.root, { direction: isRTL ? 'rtl' : 'ltr' }]}>`, and
  `direction` is a real RN layout prop (`'inherit' | 'ltr' | 'rtl'` in
  `StyleSheetTypes.d.ts:117`) that sets the Yoga node direction. Yoga direction
  inherits, so every descendant is RTL.
- `syncNativeLayoutDirection()` calls `I18nManager.forceRTL(true)` and the app
  reloads so it takes effect.

So the double flip was unconditional in Arabic, not dependent on the reload.

## Proof 3 — iOS swaps text alignment too

`react-native/Libraries/Text/RCTTextAttributes.mm`:

```objc
if (_layoutDirection == UIUserInterfaceLayoutDirectionRightToLeft) {
  if (alignment == NSTextAlignmentRight) {
    alignment = NSTextAlignmentLeft;
  } else if (alignment == NSTextAlignmentLeft) {
    alignment = NSTextAlignmentRight;
  }
}
```

`textAlign: isRTL ? 'right' : 'left'` therefore asked for right, was swapped to
left, and pinned Arabic against the wrong edge.

## Scale

96 sites in 14 files: 42 manual row flips (37 `isRTL && styles.rowReverse`, 5
ternaries) and 54 manual alignments, plus 11 now-dead `rowReverse` style
definitions.

## Why it was written this way

`reloadForLayoutDirection()` notes that "Dev client / Expo Go may not support
`Updates.reloadAsync`". In a dev client the RTL restart never happens, native
direction stays LTR, and manual flipping genuinely does look correct. The bug only
appears once a production build reloads properly — which is exactly the build the
canary now runs.

## Fix

Manual row flipping is removed outright; Yoga does it. Alignment goes through two
shared helpers in `src/i18n/index.tsx`:

```ts
export function readingEdgeAlign(isRTL: boolean) {
  return isRTL && !I18nManager.isRTL ? ALIGN_LITERAL_RIGHT : ALIGN_LEADING
}
```

They key off `I18nManager.isRTL` — the direction actually in force — rather than
the selected locale, because those differ in the degraded case where the RTL
reload did not happen. In that state the literal value is the correct one.

Chevrons and arrows still branch on the locale. They are glyphs, not layout, and
Yoga does not mirror them: all 11 are preserved and asserted by the gate.

Native RTL was **not** disabled. The engine's mirroring is the correct authority;
the app's job was to stop competing with it.

## English is unaffected by construction

Every removed branch was already `false` in LTR, and `readingEdgeAlign(false)`
returns the same `{ textAlign: 'left' }` the ternary produced. The remaining diff
is style arrays collapsing from `[styles.x]` to `styles.x`. Only Arabic rendering
changes.

## Verification

- TypeScript clean.
- 14 gates, 609 checks, all green — including the 13 that passed before the change.
- New gate `verify-rtl-single-source.py` (260 checks) forbids `row-reverse`,
  literal `textAlign: isRTL ? …`, and `forceRTL(false)`, requires both helpers to
  read `I18nManager.isRTL`, and requires direction-aware icons to survive. It was
  proven to fail when a single `row-reverse` is reintroduced, then pass again.

## Shipped

| | |
| --- | --- |
| Commit | `3415887` |
| iOS update | `019fe322-4cc3-7507-adfd-04f5ba4cc758` |
| Android update | `019fe322-4cc3-75e3-95b0-7df9af333633` |
| Group | `9b4d8a79-a9d9-4fa5-9f5b-6471685a4219` |
| Runtime | `0.1.0` |
| Rollback group | `c997eac8-8b33-4b55-9a8e-a1860d0420fe` |

## Still required

A device look confirming Arabic rows now read right-to-left with the chevron on
the left. The reasoning above is engine-level and I consider it settled, but the
rendered result has not been seen by anyone yet.
