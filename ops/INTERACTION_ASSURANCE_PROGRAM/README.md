# Interaction Assurance Program

Tracked residual work from the Full Interaction & Dead-Control Audit
(`ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/`).

## Release policy

| Finding class | Blocks release? |
|---|---|
| Confirmed **P0/P1** broken, dead, or permission-mismatched controls | **Yes** |
| Static dead-control inventory failures (dashboard `prebuild`) | **Yes** |
| P1 **unproven** destructive/idempotency/audit properties (495 register) | **No** — progressive synthetic program |
| P2 raw/unclear mutation error contracts | **No** — gradual module waves |
| Dashboard Vitest regressions already explained/fixed | Suite must stay green |

Product development continues while the residual register shrinks. Do not treat the full 495 as a launch latch.

## Program pieces

| Path | Role |
|---|---|
| `RESIDUAL_REGISTER.md` | Closed P0/P1 + open residual inventory |
| `NAMING.md` | IAX markers, phone block, disposable tenant rules |
| `CLEANUP_CONTRACT.md` | Marker-scoped cleanup + audit retention |
| `RELEASE_GATE.md` | What fails a release vs what is tracked |
| `qualify-interaction-assurance-prod-synthetic.sh` | Stamped qualify → canary → evidence |
| `../full-web-e2e/run-interaction-assurance-release-gate.py` | Gate: fail only on confirmed P0/P1 |
| `../../wathefni-orchestrator/interaction_assurance_fixtures.py` | Disposable fixture create/cleanup |
| `../../wathefni-orchestrator/canary-prod-interaction-assurance.py` | Progressive destructive property probes |

## Cadence

1. Keep confirmed P0/P1 closed (this register + matrix).
2. Prove batches of unproven destructive properties on **disposable, marker-scoped fixtures** only — never real customer rows.
3. Improve raw mutation error contracts **by module** (calendar → employee-ess → …).
4. Stamp evidence under `ops/evidence/interaction-assurance-{stamp}/`.
5. Fail releases only via the release gate / dead-control prebuild when confirmed P0/P1 reappear.
