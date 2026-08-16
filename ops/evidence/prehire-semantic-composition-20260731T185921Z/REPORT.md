# Pre-hire semantic composition correction (local)

**Stamp:** `20260731T185921Z`  
**Deploy:** **NO** — hold until explicit approval  
**Build:** PASS (`dashboard-CgDXvZTr.js`)  
**Map:** `ops/evidence/prehire-semantic-color-20260731T133500Z/COLOR_MAP.md` (composition rewrite)

## Correction vs prior chip pass

Prior live deploy treated color as badges/chips. This pass restores **Overview / mobile / Intelly composition**: larger pastel surfaces. Cream canvas + dark shell + black CTAs unchanged. Assistant suggestion chips stay **neutral**.

## What changed (local)

| Page | Composition surface |
|---|---|
| Tokens | Soft washes saturated toward Overview; mobile plum/pink tokens added (sparing) |
| Jobs | Open/Draft/Paused/Closed **status tiles** (click filters) |
| Candidates | Soft **people band** around views/filters; identity-review rows yellow wash |
| Interviews | Upcoming / Needs feedback / Completed **summary tiles** |
| Calendar | Event cards use **base** accent fills (Intelly-style) |
| Assessments | Send header **assess pink** panel; Needs review **yellow** header |
| Ranking | Top-3 **full-card** washes (priority / follow / assess) |
| Reports | Metric tiles as filled pastel surfaces |
| Assistant | Suggestion chips **neutral cream** (reverted from live colored chips) |

## Verification

| Gate | Result |
|---|---|
| `npm run build` | **PASS** |
| Before shots (prior chip pass) | `screenshots/before/` |
| After shots (this composition) | `screenshots/after/` EN+AR desktop; mobile jobs/candidates/calendar/ai |
| Probes | `verify/after-probes.json` |

## Deploy

**Blocked** until you approve. Redeploy would ship composition + Assistant chip revert together.

## Deployed

**LIVE** via `prehire-semantic-composition-deploy-20260731T190529Z` (`20260731T190529Z`).
