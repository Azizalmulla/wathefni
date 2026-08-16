# HR mobile queue pagination — pre-customer blockers

**Status:** Logged 2026-08-11 · **do not fix during visual wave** · harden before first real customer onboarding.

These are must-fix before GA / first non-canary customer onboard. Safe to defer while Editorial Entity Detail visuals continue on canary (WATHEFNI · Aziz/Talal).

---

## Must-fix before first real customer onboarding

### 1. Home / Inbox priorities — silent 12-item cap per section
- Server `/dashboard/mobile/priorities` defaults to **limit=12** per section.
- Home further caps visible rows (`HOME_VISIBLE_ITEM_CAP = 6`) and has **no fetch-more**.
- Inbox “Show more” only expands already-fetched items.
- **Risk:** Leave / docs / onboarding / tasks / attendance / swaps look short or clear while `section.total` is higher. Actionable work disappears beyond the first page with no honest continuation path.

### 2. Actionable queues — default page 30, no load-more / search
- Documents, Tasks, Onboarding, Delivery Alerts omit client `limit`/`offset` → server default **30**.
- UI ignores `has_more` (Tasks expose `total` but not `has_more`).
- **Risk:** Open actionable items beyond page 1 never appear; queue can look complete or empty of remaining work.

### 3. Task priority ordering buries `urgent`
- Backend: `ORDER BY (t.priority = 'high') DESC, t.created_at DESC`.
- **`urgent` is not elevated** — sorts with normal/low.
- **Risk:** Urgent follow-ups buried under newer normal tasks within the first page.

---

## Related (safe debt — not GA blockers alone)
- Attendance Unresolved: `limit=100` over 92d lookback; `has_more` ignored; chip counts = page length.
- Shifts today / requested swaps hard-stop ~100 without continuation cue.
- Candidates 20 / interviews 50 / positions 50; Hiring home upcoming sliced to 8.
- People directory is the reference pattern (search + infinite load).

## Clarity that is already OK
- Attendance **Today vs Unresolved** tabs are explicit; bare `?status=exceptions` = today only by design.
