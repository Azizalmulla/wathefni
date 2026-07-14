# Wathefni Employee App Design System

Status: frozen for production after Phase 9A. Changes require a concrete usability, accessibility, platform, or product issue.

## Principles

- Warm cream canvas, editorial hierarchy, calm sans-serif utility copy.
- Typography-only Wathefni branding. Do not introduce an unapproved symbol or substitute wordmark.
- Rounded pastel cards communicate grouping, not capability or authority.
- Backend capabilities and access states determine what exists and what actions are available.
- English and Arabic are equal product surfaces. Mirroring must preserve meaning and reading order.

## Tokens

Source of truth: `src/theme.ts`.

### Color

- Canvas `#F8F2E8`; surface `#FFFCF6`; muted surface `#F1EADF`; border `#E8DED0`.
- Ink/text `#1C1B19`; secondary text `#656058`.
- Accent `#AA477F`; soft accent `#F2DDEC`.
- Success `#477052` / `#DFEAD9`; warning `#8E5B16` / `#F6E5B6`; danger `#A23A40` / `#F4D7D5`.
- Pastels: lilac `#EAE1F4`, butter `#F7DFA4`, blush `#F5DCD9`, sage `#DDE8D4`, sky `#D9E6F5`.
- Ink has at least 13.15:1 contrast on every approved pastel. Secondary text is 5.60:1 on canvas and at least 4.76:1 on every pastel. Semantic status text exceeds 4.5:1 on its paired soft surface.
- Status must always include text or an icon; color is never the only signal.

### Typography

- English wordmark: Newsreader SemiBold. Arabic wordmark: Noto Kufi Arabic SemiBold.
- Editorial headings: Georgia on iOS for English and Geeza Pro for Arabic; platform serif/sans fallbacks elsewhere.
- UI copy uses the platform sans-serif stack.
- Sizes: display 38, H1 28, H2 20, H3 17, body 15, small 13, tiny 11.5.
- Body text follows system font scaling. Editorial headings support up to 200%. The wordmark may cap at 125% to preserve brand form and is exposed as one accessibility header.
- Do not fake Arabic letter spacing or reuse English editorial metrics for Arabic.

### Layout

- Spacing scale: 4, 8, 12, 16, 24, 32, 40.
- Radius scale: 8, 12, 16, 22, and pill.
- Interactive targets are at least 44×44 points; primary buttons are 48 points high.
- Native safe-area insets own notch, Dynamic Island, and Home Indicator spacing. Do not add device-model-specific padding.
- Native stack/tab headers own their safe area. Headerless screens must use `SafeAreaView`.

### Elevation

- Card shadow: `#5D5144`, 7% opacity, radius 14, Y offset 5; Android elevation 2.
- Elevation communicates grouping only. Avoid nested shadows and modal-like cards inside cards.

### Motion and haptics

Source of truth: `src/motion.ts` and `src/native/haptics.ts`.

- Durations: 120 ms instant, 180 ms quick, 280 ms enter, 420 ms progress.
- Standard easing: cubic Bézier (0.2, 0.8, 0.2, 1). Springs use speed 28 and bounciness 3.
- Reduced Motion removes lift and press-scale animation while retaining state changes.
- Light impact is reserved for deliberate primary actions; success feedback follows completed native transfers.

## Components

- `Wordmark`: text only; minimum 15 points; clear space 0.6 em; never place inside a busy illustration.
- `EditorialHeading`: one primary thought per section.
- `PastelCard`: lilac, butter, blush, sage, sky, or cream variants.
- `PremiumButton`: default, disabled, busy, success, and directional variants.
- `StatusChip`: always uses a localized status label.
- `IconBadge`: supporting decoration; meaningful actions require a label on the containing control.
- `WathefniBloom`: decorative corner, ribbon, and watermark variants; hidden from accessibility APIs.
- `ContentSkeleton`, loading, empty, error, feature-unavailable, and access-state components are the permanent state patterns.

## English, Arabic, and RTL

- All user-facing strings live in `src/i18n/en.json` and `src/i18n/ar.json`.
- Rows reverse in RTL; text aligns right; directional arrows and chevrons mirror.
- Dates and machine-entry date fields remain LTR while their labels follow the active locale.
- Numeric data may use localized numerals through the shared formatters.
- Never derive authorization, feature visibility, or status meaning from translated copy.

## Iconography

- Ionicons is the only production icon family and is imported directly to avoid bundling unused font families.
- Use outline icons for navigation/supporting actions and filled/check icons for confirmed states.
- Icons do not replace labels for destructive, permission, upload, or account actions.

## Governance

- A visual change needs a reproducible issue and English/Arabic review.
- A new module must arrive through `/app/me` capability data and employee-scoped APIs.
- Payslips and compliance actions remain absent until their APIs and capabilities are available.
