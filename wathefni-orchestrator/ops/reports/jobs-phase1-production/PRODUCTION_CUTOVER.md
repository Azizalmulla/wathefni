# Jobs Phase 1 — Production Cutover Closure

**Status:** PRODUCTION VERIFIED  
**Promoted artifact:** `0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1`  
**Commits through:** `b35e9a1`  
**Deploy time (UTC):** 2026-07-20T22:45:06Z  

## Production commit and artifact SHA

- Artifact SHA shipped: `0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1`
- Public dashboard asset: `https://api.wathefni.ai/dashboard/assets/dashboard-DplcPCrM.js`
- Runtime `app.py` / `prehire_jobs.py` match staging green
- Gate: local artifact == staging-green before sync

## Backup and rollback reference

- Daily backup stamp: `20260720T224434Z`
- Pre-deploy snapshot: `/opt/wathefni/backups/predeploy-20260720T224440Z`
  - `orchestrator.tgz`, `dashboard-public.tgz`
- Rollback pointer: `/opt/wathefni/backups/.last-predeploy`
- Rollback: `ops/deploy.sh rollback`

## Effective APPLY environment value

Drop-in `/etc/systemd/system/wathefni-orchestrator.service.d/jobs-apply-whatsapp.conf`:

```
WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566
WATHEFNI_FILE_POSITIONS_ENABLED=false
```

Live process environ confirmed: `WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566`.

Preserved: Terra (`WATHEFNI_TOOL_AGENT_MODEL=gpt-5.6-terra`), Voyage embeddings, toolcall orchestrator, canonical lifecycle, assessment-authoring=false.

## Hard-coded path cleanup proof

- `ai-recruiter/app/routers/internal.py` — APPLY via env-owned helper; HTTP 503 if missing
- `ai-recruiter/app/services/qr_generator.py` — no hardcoded number; fail closed
- Scan of `ai-recruiter/app`: **clean** (no `wa.me/96599338566` / hardcoded `WHATSAPP_NUMBER`)
- Live Wathefni authority: `prehire_jobs.apply_whatsapp_number` / `apply_link`

## Lifecycle verification totals

Synthetic dry-run (`ops/jobs-phase1-production-verify.py`): **23 passed, 0 failed**

Covered: inventory intact, applications attached, draft create/edit, publish, open edit without status change, pause/resume/close/reopen, create-cannot-reopen-closed, duplicate code 409, stale edit/transition 409, vacancy/remaining, salary visibility, APPLY/QR/Assistant parity, file positions off, dry_run only, synthetic cleanup close.

## EN/AR proof

```json
{
  "en": { "locale": "en", "title": true, "create": true, "apply": true, "rtl": true },
  "ar": { "locale": "ar", "title": true, "create": true, "apply": true, "rtl": true }
}
```

Screenshots: `jobs-inventory-en.png`, `jobs-inventory-ar.png`

## APPLY / QR / Assistant parity proof

Verified production links of the form:

`https://wa.me/96599338566?text=APPLY-WATHEFNI-PRODJP1_…`

for `application_link`, `qr_value`, and `prehire_jobs.apply_link` (Assistant share path).

## Counters before and after

| Moment | Positions | Applications |
|---|---:|---:|
| Pre-deploy baseline | 10 | 17 |
| After deploy | 10 | 17 |
| After synthetic cleanup | 10 | 17 |
| Leftover `PRODJP1_%` | 0 | — |

## Synthetic cleanup proof

Deleted verification position(s) `PRODJP1_*`. Leftover count **0**. Applications unchanged at **17**.

## Outbound delivery

- Verification process: `WATHEFNI_DELIVERY_MODE=dry_run`
- Production service delivery mode: unchanged (unset → live default)
- No candidate WhatsApp/email sends invoked by verification

## Remaining non-blocking issues

1. Owner soak UX polish (Done label, ownership collapse, localized status badges, sticky actions) is **not** in artifact `0c0ac7a…` — promote in a follow-up if desired.
2. `ai-recruiter` is env-wired in repo but not a live service on this VPS (orchestrator is the live APPLY path).
3. Pre-deploy offsite backup push was skipped (local encrypted daily backup succeeded).

## Stop

Production verification complete. No further promotion steps in this cutover.
