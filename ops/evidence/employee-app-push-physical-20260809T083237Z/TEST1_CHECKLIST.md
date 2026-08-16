# Test 1 — Leave approved (foreground)

**Sent:** yes · Aziz · `delivered_push`  
**message_id:** `87733528-0d61-47ba-b27d-49c76b3761e3`  
**Dedupe:** `canary_push_phys:leave_approved:leave1-20260809T083237Z`  
**Inbox rows for dedupe:** 1 (intentional resend reused same message_id)

## Expected tray (EN)

| Field | Value |
| --- | --- |
| Title | Leave approved |
| Body | Your leave for 2026-08-23 to 2026-08-25 was approved. |
| Sound | wathefni_default |
| Tap | Leave tab `/(tabs)/leave` |

## Verify while app is foreground

1. Banner arrives
2. Title/body short and correct (above)
3. wathefni_default sound plays
4. Icon correct
5. Tap opens Leave
6. Matching Inbox row
7. Badge stays synced
8. Duplicate resend does not spam (second server call same dedupe → 1 inbox row)

Reply PASS/FAIL before next event.
