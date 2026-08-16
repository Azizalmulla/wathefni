# Employee App Push UX Wave — Evidence

**Stamp:** `20260809T075811Z`  
**Scope:** Push on-by-default after OS permission; conservative event map; short tray copy; badge sync; activation Inbox-only; payslip/bank/docs push wiring.  
**Verdict:** **PASS (automated / contract)** · **Physical device: PENDING** (canary Aziz/Talal)

---

## PASS / FAIL

| Gate | Result |
|------|--------|
| Mobile opt-in removed (opt-out only) | **PASS** |
| Auto-register after OS permission | **PASS** (code) |
| Settings = manage/disable | **PASS** |
| Activation never Expo push | **PASS** (`employee_push_tray.push_allowed`) |
| Tray copy short EN/AR | **PASS** |
| Collapse id + time-sensitive shift | **PASS** |
| Badge sync from Inbox unread | **PASS** (code) |
| Sound `wathefni_default` + channel `v2` | **PASS** (`verify-push-sound.py`) |
| Capability foundation | **PASS** |
| Push follow-through | **PASS** (14 checks) |
| Push tray smoke | **PASS** |
| Physical FG/BG/killed / tap / sound / dupe | **PENDING** — needs canary device after OTA + orchestrator deploy |

---

## Event map actually wired

| Event | Channel | Notes |
|-------|---------|-------|
| Leave approved/rejected | Push + Inbox | Ladder; short tray; dedupe `leave_decision:{id}:{decision}` |
| Shift assigned / cancelled / reminder | Push + Inbox | When outbound `shift` on; reminder + same-day cancel → `timeSensitive` |
| Onboarding welcome / reminder | Push + Inbox | When outbound `onboarding` on |
| Document required / expiring | Push + Inbox | `send_compliance_reminder` picks expiring vs required template |
| Payslip ready | Push + Inbox | Inbox insert + `send_outbound_push` |
| Bank correction | Push + Inbox | On ESS reject / return_for_information |
| App activation | **Inbox + WA/email only** | Push skipped by policy |

---

## Payload example (Expo)

```json
{
  "to": "ExponentPushToken[…]",
  "title": "Leave approved",
  "body": "Your leave for 1 Aug to 3 Aug was approved.",
  "sound": "wathefni_default.wav",
  "channelId": "wathefni_default_v2",
  "collapseId": "WATHEFNI:leave_decision:…:approved",
  "data": {
    "flow": "leave_decision",
    "path": "/(tabs)/leave",
    "deep_link": { "path": "/(tabs)/leave" }
  }
}
```

Time-sensitive shift reminder also sets `"interruptionLevel": "timeSensitive"` and `"priority": "high"`.

---

## Backend / mobile changes

**Mobile**
- `preferences.ts` — opt-out model (default on)
- `PushLifecycle.tsx` — auto-register; badge refresh on foreground
- `syncInboxBadge.ts` — iOS badge ↔ unread
- `settings.tsx` — no consent wall; toggle manages enable/disable
- `AuthProvider` — logout clears badge, does not invent opt-out
- Home + Inbox sync badge
- EN/AR Settings subtitle

**Orchestrator**
- `employee_push_tray.py` — tray copy, skip list, collapse, interruption
- `outbound_delivery.py` — tray titles; skip activation push; `bank_correction_required` catalog
- `app.py` — Expo collapse/badge/interruption; payslip push; bank notify; compliance expiring template; `_APP_INBOX_FLOWS` + `bank`; `leave_decision` path
- `employee_selfservice_wave5.py` — notify after bank reject/return

---

## OTA / native

| Change | Channel |
|--------|---------|
| JS preference / lifecycle / badge / Settings | **OTA** (runtime 0.2.0) |
| Sound / channel / Icon Composer | Already in native SDK 54 build — **no new native required** for this wave |
| Orchestrator push policy | **Canary API deploy** required for server-side events |

---

## Rollback

1. OTA previous employee-mobile update (or disable `EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED`).
2. Orchestrator: set `WATHEFNI_PUSH_NOTIFICATIONS=off` (ladder skips Expo; Inbox/WA/email unchanged).
3. Code rollback: restore prior `preferences` opt-in + remove `employee_push_tray` skip if needed.

---

## Physical qualification checklist (canary)

- [ ] Grant permission → token registers without Settings opt-in
- [ ] Deny → app usable; Settings can open OS settings
- [ ] Foreground banner + sound
- [ ] Background / killed tray + tap deep-link
- [ ] Badge matches Inbox unread after mark-read
- [ ] Duplicate leave decision suppressed
- [ ] Activation code does **not** appear as push
