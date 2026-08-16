# Employee App invitation/delivery — physical acceptance

**Stamp:** `20260807T063432Z`  
**Evidence:** `ops/evidence/employee-app-invitation-physical-20260807T063432Z/`  
**Verdict:** **PASS** (with residuals)  
**Auth Wave 2 Phase 6:** not started  

## Scope exercised

| Check | Result |
|---|---|
| HR invitation GET never returns code | PASS |
| Resend → delivered/email, `code_disclosed=false`, one pending | PASS |
| Re-invite → delivered/email, no code, one pending | PASS |
| States: delivered / failed / needs_attention / expired | PASS |
| `show_code_exception` only on `needs_attention` | PASS |
| Exception `hr_task_only` returns code when approved | PASS |
| Production UI needles EN + AR (App access, Resend, Re-invite, statuses, Show code) | PASS |
| Copy contract vitest EN+AR / RTL dir helper | PASS (4/4) |
| Aziz emailed activation code → live activate → `/app/me` → refresh reopen → `/app/me` | PASS |
| Stale code rejected after redeem | PASS |
| HR snapshot after: `invitation_status=activated`, access active, **0 pending** | PASS |
| No `/app/devices` (Phase 6) | PASS |
| PIN crypto selftest | PASS |

## Final Aziz HR state

```json
{
  "invitation_status": "activated",
  "channel": "email",
  "app_access_active": true,
  "actions": {
    "resend": false,
    "reinvite": true,
    "revoke_access": true,
    "show_code_exception": false
  }
}
```

## Residuals (do not block invitation/delivery PASS)

1. **On-device PIN create + Face ID + cold app reopen UI** — no USB/canary iPhone attached to the agent. Local PIN/Face ID remain Auth Wave 2 Phase 2 partial; server session reopen without activation code is proven via refresh.
2. **Interactive HR profile App access card screenshot** — SPA navigation did not stably open the real Aziz profile card in headless Chromium (directory/shell screenshots + production bundle needles + API walk cover EN/AR copy). Owner glance on `https://api.wathefni.ai/dashboard/` → Employees → Aziz → App access (switch AR) recommended.
3. **Multiple emails during acceptance** — Resend/Re-invite/state matrix intentionally delivered several codes; prior invites were superseded; final pending count = 0; latest redeemed invite is the activated one.

## Defects

None blocking. No duplicate **pending** invites; no code leakage on normal HR paths; Phase 6 not started.

## Artifacts

- `prove/physical-canary-final.txt` — full PASS run  
- `aziz/live-activate-reopen.txt` — live uvicorn activate path  
- `hr/final-snapshot.json` — activated + invite status counts  
- `ui/copy-vitest.txt` · production PostHire/api needles  
- `ui/screenshots/*` — dashboard EN/AR shells + directory  
- `mobile/pin-crypto.txt`  

## Non-actions

- Do **not** start Auth Wave 2 Phase 6.
