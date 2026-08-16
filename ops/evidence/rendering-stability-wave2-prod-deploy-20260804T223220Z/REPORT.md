# Rendering Stability Wave 2 — production deploy

**Stamp:** `20260804T223220Z`  
**PostHire bundle:** `PostHire-DajvJ0vm.js`  
**Dashboard chunk:** `dashboard-pnt48cji.js`  
**Spec:** `ops/RENDERING_STABILITY_WAVE2.md`

## Proof

| Check | Result |
| --- | --- |
| Unit / contract | 50 passed (Wave2 + IQ1 + Calendar + Shifts) |
| Bundle markers | `RENDERING_W2_BUNDLE_SMOKE_OK` |
| Prod opacity-95 absent | `OPACITY95_ABSENT_OK` |
| Health `:8010/health` | 200 |

## Rollback

```bash
/opt/wathefni/backups/production-pre-rendering-stability-wave2-20260804T223220Z/ROLLBACK.sh
```

## Calendar Wave 2

**GO** for UX soft-keep follow-ons (scroll/selection).  
**NO-GO** for new post-hire event sources until Wave 1 preview review.
