# HR Leave detail — physical-surface qualification

Stamp: `20260810T165300Z`  
Surface: `/hr/leave/[id]` · `LeaveApprovalView` + `app/hr/leave/[id].tsx`  
Actor: Aziz owner `96599338566` (real-decision allowlist)  
Subject for mutate: Talal `WATHEFNI-96550252254` disposable request  
Read fixture: Fouad `033e8a56-…` annual requested (conflict=1, balance present)

## Functional verdict: **CONDITIONAL — do not lock yet**

Backend mobile leave spine is sound for canary. The **shipped UI is not honesty-complete** for balance/conflict/confirmation copy, so Leave should not be marked frozen/locked until the listed functional fixes land (small, no redesign).

### Exercised (host, production helpers)

| Check | Result |
| --- | --- |
| Open queue for Aziz | 2 requested (Fouad annual, Mohammad sick); both conflict_count=1 |
| Fouad detail facts | type annual · 2026-08-16→18 · duration 3 · reason Family trip · actions approve/reject |
| Shift conflict vs DB | payload 1 = `shift_assignments` scheduled count 1 |
| Balance on detail | list with annual: entitlement 30 · accrued/current/available **17.5** · observe_only · enforced=false |
| Balance on list | not loaded (detail-only) — OK |
| Disposable create + prepare reject | needs_confirmation + reason in args |
| Prepare approve + confirm | completed → status `approved` · allowed_actions `[]` |
| Priorities sync | disposable gone; remaining `/leave/{open ids}` only |
| Already-decided historical | actions `[]` |
| Reject empty reason | route requires reason (422) |
| Manager scope gate in loader | out-of-scope → 404 same as missing |
| Safe-back parent | `hrCanonicalParent(/leave/x)` → `/hr` |
| Home/Inbox client invalidation | `mobile-priorities` + `refreshMe` after confirm |

### Client / honesty gaps (block lock)

1. **Fake balance card** — API returns real balance rows; UI shows only “Authoritative balance context is available for this request.” and never numbers/`observe_only`.
2. **Conflict copy EN-only** — hard-coded English string; not in i18n; AR UI still English.
3. **Confirmation action label** — route returns raw `action: 'approve'|'reject'` into sheet; shows English verb keys instead of `leave.approve` / `leave.reject`.
4. **Confirmation consequence EN-only** — server prepare consequence is English; AR session still English consequence (backend copy).
5. **`already_decided` UI dead** — view supports state; route never sets it when status≠requested (shows ready facts with no buttons instead of decided panel). Success/stale/revoked via ResourcePanel work after mutation.
6. **Status badge always `attention`** — even approved/cancelled when opened read-only.
7. **List duration_days null** — list rows stringify dates so `_leave_duration` fails; detail OK. Not detail-blocking but Home body may omit days if it relied on list.

### Not blocking (acceptable under leave freeze)

- Balances observe-only / `enforced=false` (freeze: no real enforcement).
- No leave list route (Home/Inbox only) — intentional.
- Legacy visual chrome — visual debt, not functional blocker if honesty fixed.
- Idempotent confirm replay of completed confirmation returns OK (not stale); true stale is status drift between prepare and confirm.

## Exact visual changes recommended (no redesign pass yet)

Map Leave onto cream HR system used by Attendance/Tasks (`@/theme` `#FCF4E9`), keep decision layout.

1. Replace `@hr/theme` Screen/Card/plum icons with cream `PageScreen` + `HrPushedNav` / shared decision chrome (same as Attendance detail).
2. Drop multi-tone plum/amber/sky cards → one cream surface + one attention callout for conflicts.
3. Show **real balance lines** (type · available/current · observe-only caption). Do not show a placeholder “context is available” card.
4. Localize conflict sentence (`hrAssistant`-style keys EN/AR); keep count from server.
5. Confirmation sheet: localized action labels; prefer server `summary` + localized wrapper for consequence if EN-only remains.
6. Read-only decided state: use existing `alreadyDecided` panel (or success-equivalent) instead of empty-action ready card; status chip tone from real status.
7. Remove decorative request-id `#xxxxxxxx` or demote to metadata (low priority).
8. Reject reason field: keep required gate; match cream input (hairline border, no plum).

## Lock criteria for Leave

- [ ] Balance numbers rendered from API (observe-only labeled)
- [ ] Conflict + confirm action copy EN+AR
- [ ] already_decided / success / stale / revoked states reachable from route
- [ ] One physical device pass: Home→approve · Home→reject+reason · safe-back · AR RTL
- [ ] Then stamp canary PASS and move to Candidate detail

Evidence: this folder (`qualify-run.txt`, scripts).
