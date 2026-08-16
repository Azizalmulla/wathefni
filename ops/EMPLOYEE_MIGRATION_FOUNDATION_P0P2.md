# Employee Migration Foundation — P0–P3 + Sync P1

Pointer doc. Expansion plan: `ops/EMPLOYEE_MIGRATION_SYNC_EXPANSION.md`

Evidence stamps:

| Phase | Stamp | Evidence |
|---|---|---|
| **Sync P5 Connected Systems** | `20260807T102912Z` | `ops/evidence/employee-migration-sync-p5-20260807T102912Z/` |
| **Sync P4 opening balances + cutover** | `20260807T101417Z` | `ops/evidence/employee-migration-sync-p4-20260807T101417Z/` |
| **Sync P3 onboarding migration** | `20260807T095819Z` | `ops/evidence/employee-migration-sync-p3-20260807T095819Z/` |
| **Sync P2 field model + deep records** | `20260807T093314Z` | `ops/evidence/employee-migration-sync-p2-20260807T093314Z/` |
| **Sync P1 foundation-only production path** | `20260807T085406Z` | `ops/evidence/employee-migration-sync-p1-20260807T085406Z/` |
| P0–P2 create-only foundation | `20260805T144609Z` | `ops/evidence/employee-migration-foundation-p0p2-20260805T144609Z/` |
| Manager phone resolution | `20260805T150828Z` | `ops/evidence/employee-migration-foundation-manager-20260805T150828Z/` |
| Assignment history + compliance seed off | `20260805T152228Z` | `ops/evidence/employee-migration-foundation-assignment-compliance-20260805T152228Z/` |
| **P3 safe updates + Migration & Sync shell** | `20260805T154331Z` | `ops/evidence/employee-migration-foundation-p3-20260805T154331Z/` |
| **P3 Needs review queue semantics** | `20260805T180801Z` | `ops/evidence/employee-migration-foundation-p3-review-queue-20260805T180801Z/` |
| **P3 review application (approve → apply)** | `20260805T184419Z` | `ops/evidence/employee-migration-foundation-p3-apply-flow-20260805T184419Z/` |
| **P3 canonical review Apply** | `20260805T194534Z` | `ops/evidence/employee-migration-foundation-p3-canonical-apply-20260805T194534Z/` |
| **P3 Migration & Sync flow clarity** | `20260805T161521Z` | `ops/evidence/employee-migration-foundation-p3-flow-clarity-20260805T161521Z/` |
| **P3 material name identity guard** | `20260805T160200Z` | `ops/evidence/employee-migration-foundation-p3-name-guard-20260805T160200Z/` |

## Sync P1 invariants

- Foundation path is the **only** production migration import path
- Legacy import that could seed compliance is **disabled** (503, no fallback)
- `start_onboarding=true` on import is **rejected** (422)
- Preview before/after · explicit confirm · Needs review · provenance · history · exception CSV · concurrency-safe undo
- No invites · no onboarding · no compliance seed · no leave/docs/shifts/payroll · no deactivation · no ERP/SFTP yet

## P3 invariants

- Match: external ID mapping → else phone → ambiguous Needs review → never name alone
- Auto-update fields only: name, email, job title, department, start date, manager (assignment history)
- **Materially different name → Needs review** (approve explicitly before name updates)
- Preview before/after · explicit confirm · field audit · concurrency-safe undo
- No invites · no onboarding · no compliance seed · no leave/docs/shifts/payroll · no deactivation
