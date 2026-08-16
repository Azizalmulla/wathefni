# HR Leave detail — cream + honesty ship

Stamp: `20260810T170800Z`  
Surface: `/hr/leave/[id]` · cream `LeaveApprovalView` + localized route  
Ship: canary OTA **`21e2ccc7-eb8e-414b-9b0e-ab1161699aef`** · runtime 0.3.0 · iOS `019feca4-d4a8-7a5e-a48c-642b66a38943`

## Verdict: **PASS**

Honesty gaps from `hr-leave-detail-qual-20260810T165300Z` are closed. Decision spine unchanged. Leave mobile detail is frozen for this workflow pass.

### Lock checklist

| Criterion | Result |
| --- | --- |
| Real balance numbers + observe-only caption | **PASS** |
| Conflict + confirm action copy EN+AR | **PASS** (`physical-hr-leave-en-ar.py`) |
| Consequence localization (known EN templates → i18n; unknown passthrough) | **PASS** |
| `already_decided` / success / stale / revoked reachable | **PASS** |
| Status badge tone from real status | **PASS** |
| Cream `PageScreen` + `HrPushedNav`; no plum/amber/sky stack | **PASS** |
| Reject reason cream input; no `#xxxxxxxx` chrome | **PASS** |
| Backend prepare→confirm SOD + priorities drop | **PASS** (`spine-reenforcement.txt`) |
| EN+AR physical copy matrix | **PASS** |
| Safe-back / RBAC / invalidate preserved | **PASS** (verify + route) |

### Evidence

- `verify.txt` · `tsc.txt` · `ota-publish.log`
- `en-ar-physical.txt`
- `spine-reenforcement.txt` (Fouad balance 17.5 observe-only; disposable Talal approve)
- Prior audit: `../hr-leave-detail-qual-20260810T165300Z/`

### Not expanded

- No leave list route, enforcement, Payroll money, or workflow redesign
- Existing Leave product freeze (`leave-freeze.mdc`) unchanged
