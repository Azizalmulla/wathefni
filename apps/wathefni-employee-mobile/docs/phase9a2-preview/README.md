# Phase 9A2 first-slice previews

These screenshots are rendered from the real Expo screen components through the
development-only `/design-preview` route at an iPhone-sized viewport. Preview
fixtures are synthetic, visibly isolated from authentication, and excluded
unless the explicit `EXPO_PUBLIC_DESIGN_PREVIEW=1` build-time flag is present.
No normal EAS profile sets that flag.

The first slice covers Activation, Home, and Onboarding in English and Arabic,
plus capability and loading/empty/error/review/rejected states.

## Real-device preview

The repository is still on Expo SDK 51, which is not supported by the current
App Store version of Expo Go. Until the approved SDK upgrade or an EAS
development build is created, use the equivalent real-device web preview:

```sh
cd apps/wathefni-employee-mobile
EXPO_PUBLIC_DESIGN_PREVIEW=1 npx expo export --platform web --output-dir /tmp/wathefni-preview
npx serve -s /tmp/wathefni-preview -l 8091
```

On an iPhone connected to the same Wi-Fi, open:

```text
http://<mac-lan-ip>:8091/design-preview?screen=activation&locale=en&scenario=default
```

For an app-like launch during review, use Safari's Share menu and choose
**Add to Home Screen**.

Preview URL query params are the source of truth:

- `screen`: `activation` | `home` | `onboarding`
- `locale`: `en` | `ar`
- `scenario`: screen-specific; invalid values fall back safely
- `capture=1`: hides the review controls

Supported scenarios:

- Activation: `default`, `loading`, `error`
- Home: `multi`, `minimal`, `loading`, `empty`, `error`
- Onboarding: `multi`, `loading`, `empty`, `error`, `review`, `rejected`, `completed`

Changing language, screen, or scenario updates the URL immediately and preserves
the other selected controls. Refresh restores the same combination. The selected
control shows an active state (`… selected` accessibility label + butter highlight).

## Screenshot set

Regenerate and verify:

```sh
npm run preview:verify
```

Results are written to `verification-matrix.json`.

## Typography-only wordmark

- English artwork: `Wathefni` in bundled Newsreader SemiBold, 22/30 at full size
  and 17/24 in authenticated headers, with -0.55 optical tracking.
- Arabic artwork: `وظفني` in bundled Noto Kufi Arabic SemiBold, matched to the
  English wordmark's weight and visual height, with -0.1 optical tracking.
- Minimum digital size is 15 px. Preserve clear space of at least 0.6 times the
  wordmark text height on every side.
- Keep both wordmarks on one line, never stretch or outline them, and never pair
  them with a heart, W, abstract mark, app icon, or other logo symbol.
- Hero headings continue to use Georgia/Geeza Pro/system editorial typography;
  the dedicated wordmark faces must not be reused for screen headings.

## Motion rules

- Input focus and button feedback: 120–180 ms.
- Fade-and-lift entry: 280 ms with an 8 px maximum lift.
- Progress transitions: 420 ms.
- Springs use low bounciness and settle quickly; no repeated or decorative
  looping motion.
- All first-slice motion reads the operating system reduced-motion setting and
  resolves immediately when reduction is enabled.

Reusable components: `Wordmark`, `WathefniBloom`, `EditorialHeading`, `PastelCard`,
`PremiumButton`, `MotionProgressBar`, `IconBadge`, `DirectionalIcon`, `FadeIn`,
and `PreviewSkeleton`. Feature views: `ActivationView`, `HomeView`, and
`OnboardingView`.

The concept's employee photo, payslip card, compliance actions, and example
employment data were deliberately not copied. The real app uses authenticated
profile and module data, and Home still renders only `/app/me`-authorized
capabilities. Preview-only data is generic and cannot enter authentication or
production API traffic.
