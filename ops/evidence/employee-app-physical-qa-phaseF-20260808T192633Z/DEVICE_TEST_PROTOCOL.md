# Device test protocol — remaining technical QA

Device on OTA `019fe322-4cc3-7507-adfd-04f5ba4cc758` (commit `3415887`).
A1 (Arabic double-flip) is confirmed closed on device.

Each test is one action with one expected result. Report by number, e.g.
`T7 fail — gap above keyboard`. Silence on a number means it passed.

Tests are ordered by how likely they are to find something. T1–T5 target specific
suspects found in the code; T6 onward is systematic coverage.

---

## Targeted — specific suspects found in code

### T1. Keyboard on Request Leave

Two mechanisms compensate for the keyboard on this screen: a
`KeyboardAvoidingView` with `behavior="padding"`, and the shared scroller's
`automaticallyAdjustKeyboardInsets`. They may be harmless — the automatic inset
only applies to the keyboard's *overlap* with the scroller, which the avoiding
view may already have removed — or they may fight during the animation.

**Do:** Leave → Request Leave → tap the reason/notes field.

**Expect:** the field lifts to just above the keyboard in one smooth motion, with
no gap larger than normal padding between the content and the keyboard, and no
visible settle-then-jump.

**Finding if:** content is pushed roughly twice as far as needed, leaving a dead
band above the keyboard; or it jumps up then drops back.

### T2. Keyboard on Activation

Same doubled arrangement, on the login screen.

**Do:** sign out, or use a second device/simulator if you would rather not.
Tap the phone number field.

**Expect:** as T1.

*(If you would rather not sign out, skip this — the arrangement is identical to
T1, and T1's result predicts it.)*

### T3. App-switcher snapshot

The privacy cover is set when the app goes `inactive`, but iOS may take its
switcher snapshot before React commits that frame. This is a genuine race that
only the device settles.

**Do:** open Payslips (so real salary figures are on screen), then swipe up to the
app switcher.

**Expect:** the Wathefni card shows the privacy cover, not payslip content.

**Finding if:** amounts are readable in the switcher card. That is an A.

### T4. Dynamic Type AX5 — Activation `+965`

The country-code box is `height: 48` fixed while its text scales; the phone row
beside it uses `minHeight`.

**Do:** Settings → Accessibility → Display & Text Size → Larger Text → AX5. Open
Activation (or view it on the sign-in screen).

**Expect:** `+965` fully legible, box grows to fit.

**Finding if:** the text is clipped top/bottom or the box compresses it.

### T5. Dynamic Type AX5 — Home initials

38×38 circle, uncapped text inside.

**Do:** still at AX5, open Home.

**Expect:** initials fit inside the circle.

**Finding if:** letters overflow the circle, collide with the greeting, or are cut.

---

## Smoothness and responsiveness

For T6–T8, give each a verdict: **SMOOTH / ACCEPTABLE / LAGGY**.

### T6. Tab switching

**Do:** Home → Schedule → Leave → Payslips → Profile, then back across, at a
normal pace. Then a few rapid switches.

**Expect:** the active tab highlights on touch-up with no perceptible delay, and
content appears without a blank frame. Cached tabs should not re-show a skeleton.

**Finding if:** the highlight lags the tap, a tab blanks before rendering, or
rapid switching drops frames.

### T7. Push/pop transitions

**Do:** Home bell → Inbox → back · Home task → Documents → back · Profile → Bank →
back · Leave → Request Leave → back · a document detail open/close · a payslip
detail open/close.

**Expect:** native slide, no white or cream flash, no stutter, no old screen
briefly reappearing, no content shifting after the transition settles.

### T8. Scrolling

Long histories are paged inside a plain `ScrollView` rather than virtualized — a
deliberate choice, since nesting a virtualized list inside the page scroller
trades one problem for a worse one. It needs confirming under a real finger.

**Do:** Documents history, Inbox, Payslips across years, Leave requests. Scroll
slowly, then flick hard. Tap **Show more** and keep scrolling.

**Expect:** no hitching, no blank gaps during a fast flick, no jump in scroll
position after **Show more** or after a pull-to-refresh.

### T9. Tap responsiveness

**Do:** tap a list row, a Show more, a tab, and the Home bell — each once, normally.

**Expect:** every tap registers first time, with immediate pressed feedback.
Nothing needs a second tap, and nothing double-navigates.

---

## Loading, offline, forms

### T10. Refresh does not blank content

Code shows skeletons gate on `isLoading && !data`, so refresh should never clear a
screen. Confirming that holds on device.

**Do:** on Home, Documents and Payslips, pull to refresh.

**Expect:** existing content stays visible with a spinner at the top; no skeleton,
no empty state flash, no layout shift when fresh data lands.

### T11. Offline and reconnect

**Do:** with the app loaded, enable airplane mode. Navigate between already-loaded
tabs. Pull to refresh on one. Then disable airplane mode and refresh again.

**Expect:** loaded surfaces stay readable; refresh fails with a human error rather
than an endless spinner or a false "nothing here"; reconnect recovers on the next
refresh without a retry storm.

### T12. Submit states

Guards exist in code (`disabled={!valid || busy}`); this confirms they feel right.

**Do:** submit a leave request and watch the button.

**Expect:** immediate pressed feedback, the button disables while in flight, a
second tap does nothing, and success transitions cleanly.

---

## Accessibility

### T13. VoiceOver

**Do:** enable VoiceOver. Swipe through Home, switch a tab, open a list row, enter
Request Leave, open Inbox from the bell.

**Expect:** focus order follows the visual order; section headings are reachable as
headings; the bell announces its unread meaning as words, not just a dot; status
chips announce text; decorative dots are skipped.

### T14. Reduce Motion

**Do:** Settings → Accessibility → Motion → Reduce Motion on. Navigate a few
screens.

**Expect:** transitions simplify rather than break; nothing becomes unreachable.

---

## Auth and native handoffs

### T15. Auth transitions

**Do:** background the app past the auto-lock timeout and return · unlock with PIN ·
unlock with Face ID · cancel Face ID and fall back to PIN.

**Expect:** the unlock overlay is already present when the app becomes visible —
no frame of app content before it. After success it dismisses once, with no
double-navigation and no wrong screen in between.

### T16. Native handoffs

Temp files are deleted in a `finally` with `idempotent: true`, so cancelling a
share should not leak.

**Do:** open a payslip PDF, share it, then cancel a second share. Use the manager
Call action on Profile and come back. Open the date picker in Request Leave.
Upload or renew a document.

**Expect:** each hands off and returns to the right screen with navigation intact.

---

## Device sizes

### T17. Narrow and wide

**Do:** if you have access to an SE-sized and a Pro Max-sized device, repeat T6 and
a look at Home, Profile, Bank and a payslip detail.

**Expect:** no horizontal clipping of names, job titles, Arabic department names,
email, IBAN or KWD amounts.

*(I cannot cover this with a simulator — no Xcode on the build machine. If you have
no second device, say so and we record it as untested rather than passed.)*

---

## Already settled, no test needed

- **Loading pattern** — every one of the ten network screens gates on
  `isLoading && !data`, and nothing gates on `isFetching`. Refetch cannot blank a
  screen. (T10 spot-checks that this holds in practice.)
- **Duplicate submit** — guarded on leave submit, cancel, push, biometric,
  auto-lock and delete actions.
- **Temp files** — deleted in `finally`, idempotent, catch-guarded.
- **List keys** — the only index keys are fixed-length PIN dots and skeleton rows,
  which never reorder.
- **Query config** — 30s `staleTime`, no focus refetch, abort signals wired; the
  two `['leave']` call sites dedupe to one request.
- **Pull to refresh** — centralised in the shared scroller.
- **Paging** — all four growable histories bounded.
