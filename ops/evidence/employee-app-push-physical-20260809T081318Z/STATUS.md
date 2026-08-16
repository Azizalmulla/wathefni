# Physical push canary — status

**Stamp:** 20260809T081318Z
**Employee:** Aziz `WATHEFNI-96599338566` (primary)
**Backend:** employee_push_tray deployed · orchestrator restarted · `WATHEFNI_PUSH_NOTIFICATIONS=on`
**OTA:** group `36ab3079-0124-497e-b14a-ca097a03a4b1` · runtime **0.2.0** · canary branch

## Blocker

Aziz/Talal have **0** rows in `employee_push_tokens`. No Expo push can arrive until the canary iPhone:
1. Runs the SDK 54 / runtime 0.2.0 build
2. Pulls the OTA above
3. Grants OS notification permission (or Settings → Push on)
4. Registers a token via `POST /app/push/register`

## Event order (not started)

1. leave_approved — waiting on token
2. shift_assigned
3. shift_cancelled_same_day / shift_reminder
4. document_required / document_expiring
5. payslip_ready
6. onboarding_reminder
7. bank_correction
8. app_activation_should_not_push
9. App-state matrix (open / background / killed) interleaved per event where practical
