# Shifts UX Visual Direction — production report

**Stamp:** `20260804T175726Z`  
**Verdict:** GREEN  
**Bundle:** `PostHire-DEryqnEv.js`  
**Database:** `wathefni`

## Correction honored

No free-text role/label classification. Healthy tile color reads only governed
`shift_assignments.assignment_type`:

`guest` | `operations` | `night` | `event` | `general`

- EN/AR labels share the same keys
- Missing / custom / legacy → `general` (neutral frame cream)
- Invalid write values rejected (`invalid_assignment_type`)
- Conflict / Review / Cancelled override category fill **and** keep text labels
- Overnight span no longer invents a blue “category”

Model doc: `ops/SHIFTS_ASSIGNMENT_TYPE_GOVERNED_MODEL.md`

## Delivered

- Governed `assignment_type` column + CHECK + create path + composer select
- Category surfaces from governed field only (`visualBaseline.ts`)
- UX hierarchy trim: no Shifts-workspace subtitle band; quieter Requests chip
- Operational overnight copy: `Next day`
- Wider identity rail (220px); location only when it differs from row site
- Legend shows assignment categories + Conflict
- Wave 1 authority + IQ-12 markers preserved

## Verification

- Shifts contracts (Wave 1 + IQ-12 + visual + 3B): **23/23 PASS**
- Vite production build: PASS (`PostHire-DEryqnEv.js`)
- Production schema/smoke: PASS (`assignment_type` present; free-text normalize → general)
- IQ-12 production recheck: PASS
- Populated EN/AR × desktop/mobile Schedule: captured (week of 16–22 Aug 2026)
- Create drawer shows Assignment type select: captured

Evidence note: synthetic Wave-1 subjects in the dense week were given explicit
governed `assignment_type` values for visual proof only (not role-text matching).
Real/legacy rows remain `general` until set via composer.

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-ux-direction-20260804T175726Z/ROLLBACK.sh
```

## Evidence paths

- `ops/evidence/shifts-ux-direction-prod-deploy-20260804T175726Z/`
- Remote: `/opt/wathefni/production-evidence/shifts-ux-direction/20260804T175726Z/`
