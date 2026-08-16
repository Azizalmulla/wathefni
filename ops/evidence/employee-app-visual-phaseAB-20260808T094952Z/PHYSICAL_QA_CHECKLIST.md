# Physical iPhone review — Phase A+B

Static gates are green. Everything below needs a real device and is **not** claimed as passing.

## Devices
- iPhone SE (3rd gen) — smallest width, no home indicator
- iPhone 15 / 16 Pro — home indicator, Dynamic Island
- iPhone Pro Max — largest width

## Bottom-tab and safe area (the highest-confidence change)
- [ ] Home, Schedule, Profile, Leave, Inbox: scroll to the very bottom. The last element must
      sit fully above the tab bar with visible clearance, on both a home-indicator device and
      the SE.
- [ ] Tab labels are not clipped by the home indicator.
- [ ] Pushed screens (Documents, Payslips, Bank, Settings, Onboarding, Privacy & Support):
      last element clears the home indicator; there is no tab-bar-sized gap where no bar exists.
- [ ] Leave request form: focus each field, confirm the keyboard pushes content and the
      submit button stays reachable. Interactive dismiss works.
- [ ] Bank form: same, with the IBAN field focused.
- [ ] Rotate / reopen after backgrounding — no layout jump.

## Colour and status
- [ ] Cream and ink dominate. Count the ambient tones per screen: expect one or two.
- [ ] Status chips read as status against every card colour they appear on, including on
      butter (Payslips) and lilac (Documents).
- [ ] No pastel fill reads as a success/failure signal.
- [ ] Outdoors / low brightness: `surface` on `bg`, and `surfaceMuted` icon badges on cream
      cards, are still distinguishable. This is the pairing most at risk from the move off
      translucent white.

## Responsive text
- [ ] Profile with a long Arabic name, long job title, long department, and a long email.
- [ ] Bank with a full 30-character IBAN — wraps, does not truncate, and is selectable.
- [ ] Payslip line rows with a long deduction label — the amount is not squeezed.
- [ ] Home module tiles with a single entitled module — the tile fills the row.

## Dynamic Type
- [ ] Default, XXL, AX3, AX5 on Home, Schedule, Payslip detail, Profile, Onboarding.
- [ ] Titles do not consume the screen before body copy is reachable.
- [ ] Primary buttons grow rather than clip their label.
- [ ] Onboarding progress counter and inbox unread badge do not clip their number.

## EN / AR and RTL
- [ ] Every migrated screen in Arabic: margins mirror, chips and icons sit on the correct
      side, the Profile label-above-value rows read correctly.
- [ ] Switch language at runtime and confirm the silent reload leaves layout correct.

## Copy
- [ ] No CANARY, Wave, build/version/reason code, `snake_case` value, IBAN key, employee key
      or company code appears anywhere an employee can reach.
- [ ] Payslip detail: the payment-date row appears only for a payslip payroll has actually
      dated, and shows the right date. Confirm against a payslip with a null `payment_date`.

## VoiceOver
- [ ] Section headings announce as headings.
- [ ] Status is announced in words, not implied by colour.
- [ ] Reading order is logical on Home and Payslip detail.
