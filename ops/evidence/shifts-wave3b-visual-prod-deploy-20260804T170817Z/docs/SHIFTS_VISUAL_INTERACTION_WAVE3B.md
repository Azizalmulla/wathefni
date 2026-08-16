# Shifts Visual & Interaction Redesign Wave 3B

**Status:** PRODUCTION GREEN — stamp `20260804T170817Z`  
**Supersedes visually:** rejected Wave 3 (`20260804T162104Z`)  
**Preserves:** Wave 1 authority and Wave 2 IQ-12 (`20260804T155956Z`)  
**Production bundle:** `PostHire-Cehe0aMR.js`  
**Evidence:** `ops/evidence/shifts-wave3b-visual-prod-deploy-20260804T170817Z/`

## Why Wave 3 failed

Wave 3 changed tokens and surface colors without redesigning the schedule's
geometry. The week remained a bordered HTML table containing full product cards
inside narrow cells. Employee identity repeated inside every shift even though
the row already anchored the person. Name and status competed with time, real
data produced cramped stacks, overnight work appeared as a second full card,
and overlap was explained with text rather than composition.

The drawer remained a long, placeholder-led form that changed board width on
large screens and stacked below the board on smaller screens. Whole-board
opacity changes, visually blank history refreshes, filter wrapping, and an
unnecessary status refetch produced visible churn. Wave 3 evidence used empty
boards, so none of those populated-schedule failures were qualified.

Wave 3 therefore is not a post-hiring baseline.

## Wave 3B composition

### Weekly roster board

- CSS-grid roster lanes, not a table: one sticky identity rail plus seven open
  day lanes with no boxed cells.
- Employee identity appears once per row with initials, name, team/site, and a
  quiet weekly-hours summary.
- Shift tiles lead with tabular time, then role and location/team.
- Healthy work uses a restrained neutral/olive treatment. Yellow is conflict,
  pink is reconciliation, taupe is cancelled, and blue is reserved for
  overnight continuation or information.
- Multiple shifts become compact stacked windows. Overlaps use two lanes and a
  conflict cue. Overnight work uses linked start/continuation fragments while
  retaining one governed shift ID.
- Today has an ink date marker and a continuous quiet day-lane wash.
- Empty schedules retain the board scaffold and expose an inline first action
  instead of a generic oversized card.

### Create, detail, and edit

- Fixed end sheet: 420px desktop, full-screen mobile, no board resize.
- Sticky title/action regions; grouped Shift, Organization, and Controls
  sections; compact labeled fields; progressive disclosure for secondary
  detail and history.
- Local pending states stay on the initiating action. Existing content remains
  visible during reload and history refresh.
- Governed org selectors, unmapped-value preservation, concurrency fields,
  confirmations, and mutation payloads do not change.

### Filters, loading, Requests, and Planning

- Compact search and scope controls; advanced filters move behind one control;
  active filters appear only when applied.
- Employee search remains debounced. Client-only status filtering must not
  trigger a server refetch.
- No whole-board opacity flash. `data-shifts-updating` remains a non-reflow
  progress cue while prior content stays rendered.
- Requests and Planning reuse the typography and sheet language with quieter
  neutral surfaces and less color density than Schedule.

### Mobile and RTL

- Mobile uses a seven-day strip plus a selected-day agenda grouped once by
  employee.
- Filters and create/edit use end/full-screen sheets.
- Logical inline positioning, mirrored continuation caps, and Arabic-specific
  spacing are qualified with populated long-label fixtures.

## Review gate

The first deliverable is an isolated coded preview with deterministic data:

- dense multi-employee schedule
- multiple shifts in one day
- overlap/conflict
- overnight start and continuation
- cancelled and reconciliation states
- empty lanes
- open create/edit drawer
- desktop/mobile and English/Arabic

No production implementation, deploy, freeze, or cross-product propagation may
occur until those preview screenshots are explicitly approved.

### Preview artifact

- Interactive coded preview: `ops/previews/shifts-wave3b/index.html`
- Usage notes: `ops/previews/shifts-wave3b/README.md`
- Desktop/mobile EN/AR schedule screenshots:
  `ops/previews/shifts-wave3b/screenshots/schedule-*.png`
- Desktop/mobile drawer screenshots:
  `ops/previews/shifts-wave3b/screenshots/drawer-*.png`
- Quieter peer-surface screenshots:
  `ops/previews/shifts-wave3b/screenshots/requests-desktop-en.png` and
  `ops/previews/shifts-wave3b/screenshots/planning-desktop-ar.png`

**Review verdict:** APPROVED before implementation and deployment.

## Production qualification

- Dashboard TypeScript + Vite build: PASS
- Wave 1, Wave 2 IQ-12, semantic color, and Wave 3B contracts: 23/23 PASS
- Wave 3B read-only production smoke: PASS
- Wave 2 IQ-12 production recheck: PASS
- EN/AR desktop/mobile Schedule, Requests, and create-drawer captures: PASS
- Production database identity: `wathefni`
- Production behavior/mutation/API contracts: unchanged

The repository-wide dashboard suite remains 358/372 green. Its 14 failures are
pre-existing and outside Shifts (candidate presentation, Interviews, Employee
Profile, Calendar, Settings, App bootstrap, and Setup Console); all Shifts
targeted contracts are green.

### Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave3b-visual-20260804T170817Z/ROLLBACK.sh
```

### Baseline decision

**GO** for the Wave 3B composition and interaction primitives to become the
post-hiring visual baseline: roster lanes, time-first tiles, semantic rails,
compact control decks, fixed end sheets, retained-content loading, and
intentional mobile/RTL composition.

Adoption remains page-by-page. Wave 3's table/card composition stays rejected,
and no page inherits Shifts-specific scheduling semantics merely for decoration.

## Frozen contracts

- Schedule / Requests / Planning IA and one primary Schedule action
- organization-governed create/edit selectors and unmapped preservation
- `createShift`, `cancelShift`, `rescheduleShift`, swap and reconciliation APIs
- `expected_updated_at` and duplicate-submission guards
- soft-keep board loading and preserved filters/date range
- sticky selected snapshot and drawer continuity
- confirmation stays open until success
- clear success, error, and cancellation feedback
- no browser-native prompt, confirm, or alert

