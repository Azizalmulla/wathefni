# Technical physical QA — result

Device on OTA `019fe322-4cc3-7507-adfd-04f5ba4cc758`, commit `3415887`,
runtime `0.1.0`, channel `canary`. Owner-executed on the physical iPhone.

## Verdicts

| | |
| --- | --- |
| `RTL_PHYSICAL` | **PASS** |
| `RESPONSIVENESS` | **PASS** |
| `SMOOTHNESS` | **PASS** |
| `TRANSITIONS` | **PASS** |
| `DYNAMIC_TYPE` | **PASS** |
| `ACCESSIBILITY_PHYSICAL` | **NOT ESTABLISHED** — T13/T14 not run |
| `TECHNICAL_PHYSICAL_QA` | **NOT CLOSED** — five tests unreported |
| `EMPLOYEE_APP_READY_FOR_OWNER_FREEZE` | **NO** |

Freeze is No on visual grounds regardless of technical result: the owner has
rejected the current visual direction and a dedicated redesign phase follows.

## Owner-reported results

| Test | Area | Result |
| --- | --- | --- |
| T1 | Keyboard on Request Leave | PASS |
| T2 | Keyboard on Activation | skipped — identical arrangement to T1, which passed |
| T3 | App-switcher privacy cover | PASS |
| T4 | Dynamic Type AX5 — Activation `+965` | PASS |
| T5 | Dynamic Type AX5 — Home initials | PASS |
| T6 | Tab switching | **SMOOTH** |
| T7 | Push/pop transitions | **SMOOTH** |
| T8 | Scrolling, long histories | **SMOOTH** |
| T9 | Tap responsiveness | PASS |
| T10 | Refresh does not blank content | **not reported** |
| T11 | Offline and reconnect | **not reported** |
| T12 | Submit states | **not reported** |
| T13 | VoiceOver | **not reported** |
| T14 | Reduce Motion | **not reported** |
| T15 | Auth transitions | PASS |
| T16 | Native handoffs | PASS |
| T17 | Narrow / wide device sizes | **untested** — no second device available |

## What the passes actually establish

**T1 resolved an open question rather than confirming a guess.** Request Leave
stacks a `KeyboardAvoidingView` on the shared scroller's
`automaticallyAdjustKeyboardInsets`. Statically that could either compose
harmlessly — the automatic inset only compensates for the keyboard's overlap with
the scroller, which the avoiding view may already have removed — or fight during
the animation. The device says they compose. No change needed, and the redundancy
is left alone rather than "cleaned up" on taste.

**T3 closed a real race.** The privacy cover is set on `inactive`, and whether iOS
snapshots for the app switcher before React commits that frame is not decidable
from source. It commits in time.

**T4 and T5 cleared the two Dynamic Type suspects.** Both are fixed-height
containers holding scalable text — the `height: 48` country-code box next to a
`minHeight` sibling, and the 38×38 initials circle. Both hold at AX5. They remain
inconsistent in code with the flexible pattern used around them, which is recorded
as B1/B2 in `STATIC_PRESWEEP.md` and deliberately not changed, since the defect
they could have caused does not occur.

**T8 validated the paging decision.** Long histories are paged inside a plain
`ScrollView` rather than virtualized, because nesting a virtualized list inside the
page scroller trades one problem for a worse one. That trade-off is now confirmed
under a real finger rather than assumed.

## A findings

One, found and closed this phase.

**A1 — Arabic was mirrored twice.** Root-caused from the layout engine's own
source rather than by inspection: Yoga's `resolveDirection()` turns `Row` into
`RowReverse` under RTL *and `RowReverse` back into `Row`*, so 42 manual
`row-reverse` overrides were laying Arabic rows out in Latin order; iOS
`RCTTextAttributes` swaps `NSTextAlignmentLeft`/`Right` under RTL, so 54
`textAlign: isRTL ? 'right' : 'left'` sites pinned Arabic to the wrong edge.
96 sites, 14 files.

Fixed by mirroring once: manual row flips removed, alignment routed through
`readingEdgeAlign()`/`trailingEdgeAlign()`, which key off `I18nManager.isRTL`
rather than the locale so the degraded no-reload state stays correct. Native RTL
was not disabled. The 11 direction-aware chevrons and arrows are preserved —
glyphs are content, and Yoga does not mirror them.

Shipped in `3415887`, confirmed on device: Arabic content starts from the right,
chevrons and actions sit on the left.

Full detail in `RTL_ROOT_CAUSE_AND_FIX.md`.

## B findings

Both recorded, neither changed, because the device proved the defect they could
have caused does not occur.

- **B1** — `ActivationView.countryCode` uses `height: 48` while its sibling
  `phoneRow` uses `minHeight: 48`. Inconsistent, but legible at AX5 (T4).
- **B2** — `HomeView.avatar` is a fixed 38×38 with uncapped text. Same shape of
  inconsistency, holds at AX5 (T5).

## C findings

None recorded, and nothing aesthetic was touched. Density, colour, card treatment
and hierarchy are the subject of the separate redesign phase and were deliberately
left alone.

## Settled in code, no device time spent

- Loading gates on `isLoading && !data` across all ten network screens; nothing
  gates on `isFetching`, so a refetch structurally cannot blank a screen.
- Duplicate submits guarded on leave submit, cancel, push, biometric, auto-lock
  and delete.
- PDF temp files deleted in a `finally`, idempotent and catch-guarded.
- List keys stable — index keys only on fixed-length PIN dots and skeleton rows.
- Query config: 30s `staleTime`, focus refetch off, abort signals wired; the two
  `['leave']` call sites dedupe to one request.
- Pull-to-refresh centralised in the shared scroller.
- Paging bounds all four growable histories.
- Auth state transitions batch into a single commit, so the cover cannot vanish
  before the overlay arrives.

## Regressions

None. TypeScript clean; 14 gates, 609 checks green, including
`verify-rtl-single-source.py` which was proven to fail on a reintroduced flip and
pass once reverted.

## Gaps

Five tests unreported (T10–T14) and one untestable here (T17). Of these, T13 and
T14 are the material ones: they carry the `ACCESSIBILITY_PHYSICAL` verdict, which
is an exit criterion, and VoiceOver behaviour cannot be inferred from static
scans. T17 needs a second device size; the build machine has no Xcode or
simulator, so it cannot be covered as a secondary.

## Build state

| | |
| --- | --- |
| Backend | `c80900c`, deployed `20260808T195345Z`, sha `144a608f…` |
| Mobile tip | `3415887` |
| iOS OTA | `019fe322-4cc3-7507-adfd-04f5ba4cc758` |
| Android OTA | `019fe322-4cc3-75e3-95b0-7df9af333633` |
| Rollback group | `c997eac8-8b33-4b55-9a8e-a1860d0420fe` |
| Runtime | `0.1.0` |
