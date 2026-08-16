# STATUS — Page scroll bottom limit fix

| Field | Value |
| --- | --- |
| Stamp | `20260809T035953Z` |
| Verdict | **PASS** (canary OTA; confirm on device) |
| OTA | `4ab57e78-af3d-4f0b-8986-d7f9c0025361` |
| Rollback | `8851af5b-1fc1-4d24-b610-08631226f304` |
| Cause | `useScrollBottomPadding` added full tab-bar height even though tab scenes are already laid out above the bar → large empty cream scroll. Plus global `automaticallyAdjustKeyboardInsets` could leave a stale inset (intermittent). Home also overwrote bottom padding inconsistently. |
| Fix | Tabs: breathing room only. Stack: home-indicator + breathing. Keyboard insets opt-in (Bank). `contentInsetAdjustmentBehavior=never`. Home no longer overrides `paddingBottom`. |
