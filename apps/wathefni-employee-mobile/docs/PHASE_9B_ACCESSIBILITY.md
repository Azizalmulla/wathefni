# Phase 9B Accessibility Report

## Verified in code

- Headerless Home, Activation, Onboarding, modal, and blocking-state surfaces use native safe-area insets.
- Native stack/tab headers own insets for headered routes, avoiding duplicate notch padding.
- Primary controls are at least 48 points high; icon/back controls are at least 44×44 points.
- Buttons, tabs, progress bars, selected segments, disabled/busy states, alerts, and decorative elements expose appropriate accessibility roles/state or are hidden.
- Wathefni Bloom decorations are excluded from the accessibility tree.
- Reduced Motion is read at startup and observed at runtime; entrance lift and press scaling are removed when enabled.
- Body copy uses React Native font scaling. Editorial headings allow 200%; the typography-only wordmark allows 125%.
- Leave form scrolling adjusts for the iOS keyboard and permits keyboard-controlled submission.
- English and Arabic labels, reading alignment, row order, directional icons, and date-entry direction are explicit.

## Contrast measurements

- Ink on canvas: 15.45:1.
- Ink on surface: 16.81:1.
- Ink on approved pastels: 13.15:1 or higher.
- Secondary text on canvas: 4.82:1.
- Accent on canvas: 4.81:1.
- Warning on canvas: 4.87:1.
- Danger on canvas: 5.45:1.

The accent and warning tokens were minimally darkened after the audit because their prior values were 4.37:1 and 4.23:1 on the cream canvas.

## Required physical-device verification

These checks cannot be certified from static inspection and remain TestFlight gates:

- VoiceOver rotor order and announcements across Activation, all tabs, Leave Request, Onboarding upload, Documents, Settings, and every access state.
- Dynamic Type at the largest accessibility sizes in English and Arabic, including truncation and overlap.
- Reduce Motion with system setting toggled while the app is open.
- Voice Control names for icon-only document cancel/view and navigation controls.
- Full Keyboard Access through activation and leave forms.
- Contrast and legibility under Increase Contrast, Reduce Transparency, and Smart Invert.

Acceptance requires no unreachable control, clipped required text, focus loss after navigation, or status conveyed only by color.
