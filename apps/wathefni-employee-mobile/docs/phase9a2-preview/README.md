# Phase 9A2 first-slice previews

These screenshots are rendered from the real Expo screen components through the
development-only `/design-preview` route at an iPhone-sized viewport. Preview
fixtures are synthetic, visibly isolated from authentication, and excluded
unless the explicit `EXPO_PUBLIC_DESIGN_PREVIEW=1` build-time flag is present.
No normal EAS profile sets that flag.

The first slice covers Activation, Home, and Onboarding in English and Arabic,
plus capability and loading/empty/error states.

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
http://<mac-lan-ip>:8091/design-preview
```

For an app-like launch during review, use Safari's Share menu and choose
**Add to Home Screen**.

The floating review controls switch between Activation, Home, Onboarding,
English, Arabic, multi-capability, minimal-capability, loading, empty, and error
states. Activation continues to Home; the authorized onboarding entry continues
to the checklist. The controls are hidden in captured screenshots.

## Screenshot set

- `activation-en.png`, `home-en-multi.png`, `onboarding-en.png`
- `activation-ar.png`, `home-ar-multi.png`, `onboarding-ar.png`
- `home-en-minimal.png`
- `onboarding-en-loading.png`, `onboarding-en-empty.png`
- `activation-en-error.png`

Regenerate the set after serving the exported preview:

```sh
npm run preview:capture
```

## First-slice tokens and components

- Warm cream canvas, near-black ink, white-cream surfaces, subtle warm borders.
- Lilac, butter, blush, sage, and sky capability cards.
- 24–28 px rounded cards, pill controls, and low warm shadows.
- Georgia editorial moments in English, Geeza Pro/system Arabic for RTL hero
  moments, and native system sans-serif for operational UI.
- `BrandLockup`, `EditorialHeading`, `PastelCard`, `IconBadge`, `DirectionalIcon`,
  `FadeIn`, and `PreviewSkeleton`.
- Feature views: `ActivationView`, `HomeView`, and `OnboardingView`.

The concept's employee photo, payslip card, compliance actions, and example
employment data were deliberately not copied. The real app uses authenticated
profile and module data, and Home still renders only `/app/me`-authorized
capabilities. Preview-only data is generic and cannot enter authentication or
production API traffic.
