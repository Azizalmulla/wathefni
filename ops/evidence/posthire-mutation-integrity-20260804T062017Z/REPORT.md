# Post-hire mutation integrity — production deploy

**Stamp:** `20260804T062017Z`  
**Audit:** `ops/POSTHIRE_MUTATION_INTEGRITY_AUDIT.md`  
**Evidence:** `ops/evidence/posthire-mutation-integrity-20260804T062017Z/`

## Verdict

| Item | Result |
|---|---|
| Root cause | Assistant mutation kill leaked into `/dashboard/posthire/action` |
| Owner clicks (~05:56 UTC) changed production onboarding data? | **No** (all `failed` / `mutation_blocked`) |
| Fix deployed | **GO** |
| `WATHEFNI_ASSISTANT_MUTATIONS` | still **0** (assistant remains read-only) |
| Needs Attention UX follow-on | **HOLD** |

## Deployed

- `tool_call_orchestrator.py` — web_dashboard exempt from assistant mutation kill
- `app.py` — explicit `mutations_disabled` harness mapping
- Dashboard dist — confirm handshake / dismiss toast / Promise `run`

## Live probe

- WhatsApp channel `cancel_onboarding` → `mutations_disabled` (assistant kill intact)
- Dashboard channel `cancel_onboarding` → **not** `mutations_disabled` (`permission_denied` with probe scope only — kill no longer fires)
- Prod smoke: harness mapping OK

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-posthire-mutation-integrity-20260804T062017Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-posthire-mutation-integrity-20260804T062017Z
```
