# Jobs Phase 2 Closure Contract

Status: **PRODUCTION GREEN / CLOSED / FROZEN**  
Closed: 2026-07-21  
Production code commit: `6e844a48140b6dc86410e877688b959b0c3bcc1d`  
Production artifact SHA-256: `c7305cfce6ff3db08cf30ce6e8e6d0e881293b48cbd088e80a455bbb2bc5064f`

## Frozen authority

Jobs Phase 2 is closed. The following behavior is production authority and must
not be changed without a new, explicitly approved Jobs change contract:

- exact APPLY-code resolution; no fuzzy substitution;
- Stage A context creation with zero applications before valid intent;
- delivered/accepted preview as the `preview_sent_at` boundary;
- transactional Stage B conversion after explicit confirmation or a qualifying CV;
- one active canonical application per candidate/company/position;
- separate applications for different positions;
- backend-owned eligibility, visibility, vacancy and deadline checks;
- source attribution, conversation binding, lifecycle events and webhook idempotency;
- fail-closed tenant and production database identity binding.

## Production evidence

- Clean release passed the complete staging gate.
- Stage A: 22/22 staging checks.
- Stage B: 6/6 staging checks.
- Guarded production matrix: 9/9 checks.
- Dashboard: 44/44 tests in the clean release worktree; production edge routes passed.
- Production backend: local health 200 with matching production runtime/database identity.
- OpenClaw: staging route drop-in removed; production default `:8010` active.
- WhatsApp/AI Octopus: gateway active; default account enabled and configured.
- Production worker timers active; video interview worker repaired and running.
- Synthetic production rows cleaned: zero applications, contexts and temporary positions.

## Production test job

- Position: `J2P2_PROD_TEST`
- APPLY code: `APPLY-WATHEFNI-J2P2_PROD_TEST`
- WhatsApp: `96597453460`
- Link: `https://wa.me/96597453460?text=APPLY-WATHEFNI-J2P2_PROD_TEST`
- State: open, public, shareable, accepts applications, 25 vacancies.

## Backup and rollback

- Validated backup: `/opt/wathefni/backups/daily/20260721T025912Z`
- Pre-deploy application snapshot: `/opt/wathefni/backups/predeploy-20260721T030238Z`
- Database dump, file archive and encrypted secrets checksums passed.
- `pg_restore --list` and both pre-deploy tar archives passed integrity checks.

Operator rollback:

```bash
cd /path/to/claw
bash wathefni-orchestrator/ops/deploy.sh rollback
```

Immediate Stage B kill switch:

```bash
ssh root@76.13.63.68 \
  "systemctl edit wathefni-orchestrator.service"
# Set WATHEFNI_STAGE_B_ENABLED=0, then:
ssh root@76.13.63.68 \
  "systemctl daemon-reload && systemctl restart wathefni-orchestrator.service"
```

The Stage B schema migration is additive and is intentionally left in place
during an application rollback.

## Defects found during rollout

1. Production proof fixture initially violated the candidate/application foreign
   key. Fixed in `6e844a4`; the corrected matrix passed 9/9.
2. The video interview worker had a pre-existing restart loop because its systemd
   unit lacked production runtime identity variables. Repaired with
   `wathefni-video-interview-worker-production.conf`; post-fix state is active,
   running, zero restarts and zero new binding errors.
3. Backup encryption and local retention are healthy, but no offsite push target
   is configured. The encrypted offsite bundle is created locally; remote
   redundancy remains an operations follow-up outside Jobs Phase 2.
4. `npm audit` reports one low and three high dependency advisories. Build and
   tests pass; dependency remediation is a separate platform maintenance task.

No unresolved Jobs Phase 2 correctness or isolation defect remains.
