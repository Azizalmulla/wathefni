# Schedule capsule — in-cell stadium (fix left clip)

**Stamp:** `20260809T022428Z`  
**Verdict: PASS**

## Why it looked flat

Selected fill was an absolute `translateX` overlay inside the week `ScrollView`. On Sunday (index 0) the capsule often sat flush-left; ScrollView clipped the left round → flat left edge, text shoved right.

## Fix

Capsule is drawn **inside** the selected day cell (centered absolute child). No overlay, no `translateX`. Empties use `CalmNote` (cream text, no white card).

| Field | Value |
| --- | --- |
| OTA | `7356b390-d966-45d2-a24b-272bdb5cdc17` |
| Rollback | `dff580af-bca4-44dd-94b8-97c5282b9968` |
