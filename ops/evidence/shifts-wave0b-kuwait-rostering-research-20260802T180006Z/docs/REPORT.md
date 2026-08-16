# Shifts Wave 0B — Kuwait workforce scheduling & rostering research

**Stamp:** `20260802T180006Z`  
**Evidence:** `ops/evidence/shifts-wave0b-kuwait-rostering-research-20260802T180006Z/`  
**Mode:** research only — **no** Shifts code, deploy, UI redesign, or frozen-module changes  
**Prior:** Wave 0 prod truth `ops/evidence/shifts-wave0-prod-truth-20260802T174657Z/` (PARTIAL)  
**Canvas:** [shifts-wave0b-kuwait-rostering](/Users/azizalmulla/.cursor/projects/Users-azizalmulla-Desktop-claw/canvases/shifts-wave0b-kuwait-rostering.canvas.tsx)

---

## Objective

Design a **sector-agnostic** Shifts foundation that supports Kuwait offices through industrial/oil operations, without baking Wathefni-only office assumptions into the core. Separate **statutory**, **common practice**, **company policy**, and **manual exception** layers.

**Interview gap (explicit):** No live interviews with Kuwait HR/ops owners were completed in this wave. Findings below combine official/legal sources, published studies, job ads, vendor claims, and GCC operational patterns. Customer interviews remain required before locking enterprise rotation UX.

---

## Official-source legal matrix

Sources: Law No. 6 of 2010 (Private Sector); Law No. 28 of 1969 (Oil Sector); PAM Ministerial Resolution No. 15 of 2025 (working-hours declaration); WageIndicator / Kuwait HR Worker’s Guide summaries; PAM press on midday outdoor ban.

| Topic | Statutory baseline | Notes for Shifts |
|---|---|---|
| Daily / weekly hours | Max **8h/day**, **48h/week** (Art. 64) | Soft policy limits + Payroll OT boundary; not hard-block create by default |
| Ramadan | **36h/week** private sector | Seasonal schedule version / policy profile required |
| Breaks | ≥ **1 unpaid hour** after **5 consecutive** worked hours (Art. 65); finance/commercial/investment may run 8 consecutive; ministerial exceptions | Breaks as schedule metadata + compliance checks, not always punch events |
| Weekly rest | ≥ **24 continuous paid hours** after 6 workdays (Art. 67). Friday is traditional, **not** the only legal rest day | Rest-day is **configurable**; Friday is default policy not hardcode |
| Rest-day work | Premium ≥ **50%** + substitute rest day | Schedule change + Payroll handoff; not money in Shifts |
| Public holiday work | Premium ≥ **100%** + substitute day (per Worker’s Guide / Art. 68 family) | Holiday calendar already exists for Leave; Shifts must reference it |
| Overtime | Written order; caps commonly cited **2h/day**, **180h/year** (and day/week limits in secondary guides); ≥ **25%** premium ordinary OT | Shifts records planned OT windows; Payroll calculates |
| Women night work | Generally restricted **22:00–07:00** with listed exemptions (hospitals, hotels, pharmacies, etc.); Ramadan carve-outs exist | Policy/compliance warning, not universal ban |
| Juveniles | Max 6h/day; no OT/rest-day/holiday; no night **19:00–06:00** | Role/age gates later |
| Oil sector (Law 28/1969) | Rotation-cycle average often **40h/week**; remote-site **travel time paid**; free **accommodation + transport** (or allowance); employer sets rest day by ops need | Need rotation cycles + site/remote flags |
| Remote / gov projects (Art. 34 family) | Accommodation + transport obligations for remote areas | Site + logistics dependencies on assignment |
| PAM schedule declaration (Res. 15/2025) | Employers must enter daily hours, rest periods, weekly rest, holidays into PAM e-system; display printed schedule; update on change; non-compliance → file suspension risk | Future **compliance export**; not Wave 1 product |
| Midday outdoor ban | Summer outdoor work ban commonly **11:00–16:00**, ~1 Jun–30 Sep (PAM) | Seasonal construction/site schedule constraint |

**Classification keys used below**

- **S** = statutory  
- **P** = common industry practice  
- **C** = configurable company policy  
- **M** = exceptional/manual workflow  

---

## Kuwait sector-by-sector scheduling matrix

| Sector | Pattern (P) | Length (P) | Split / overnight | Rest (P/C) | Coverage / site | Tools (P) | Att / Leave / Payroll link |
|---|---|---|---|---|---|---|---|
| Offices / professional | Fixed Sun–Thu or Sun–Fri | 7–8h days | Rare overnight; rare split | Fri+Sat or Fri | Branch/HQ teams | Excel, Outlook, HRIS | Hours → payroll; leave blocks day |
| Government contractors | Fixed + site visits | 8h + OT | Occasional field overnight | Fri | Multi-site / client sites | Excel + WhatsApp | Timesheets + biometric |
| Restaurants / cafés / hospitality | Peak-driven; **split shifts** common | 4–10h fragments | Split lunch/dinner; late nights | Rotating offs | Role (FOH/BOH) + outlet | WhatsApp + POS + Excel | POS labour vs punches |
| Retail / malls | Fixed + weekend peaks | 8–9h; evenings | Late closes; rare overnight stock | Staggered Fri/Sat | Store/branch staffing minima | Excel, vendor TA | Biometric + sales peaks |
| Hospitals / clinics / pharmacies | **Rotating** 3-shift (documented MOH nursing) or 12h private | 7/8/9h bands or 12h | **Cross-midnight nights** required | 6-on/1-off common in gov nursing literature | Unit coverage minima | Paper/Excel/roster apps | Critical leave coverage |
| Construction / site | Day shifts + summer midday ban | 8h with seasonal cut | Rare night pours | Fri | **Site** + transport | WhatsApp, biometric gates | Manhours + safety |
| Logistics / delivery / warehouse | Fixed + peak waves | 8–12h | Overnight sort/delivery | Rotating | Hub/route teams | Excel, GPS apps | Route + punch |
| Factories / manufacturing | Rotating crews | 8 or 12h | Overnight lines | 4-on/4-off / continental (P) | Line/crew | Biometric + Excel | OT heavy |
| Security / cleaning | **12h** ads common; 6-on/1-off | 8 or 12h | Heavy overnight | Fri off often advertised | Post/site + transport/accommodation | WhatsApp + muster | Post coverage critical |
| Schools / education | Fixed term timetable | 6–8h | Rare | Fri–Sat | Class/role | Timetable software | Term calendars |
| Oil / gas / industrial | **Rotation cycles**; remote camps | Cycle avg ~40h (oil law); 8/12h | Night + remote | Employer-set rest in cycle | Plant/site + camp logistics | Enterprise roster + TA | Travel time, camp, OT |
| Telecom / field service | Appointment + standby | Variable | On-call overnight | Rotating | Territory/crew | FSM + WhatsApp | Job tickets ≠ punches |
| Automotive workshops / dealers | Fixed workshop + Saturday retail | 8–9h | Rare | Fri or Fri+Sat | Workshop bay / showroom | Excel + DMS | Job cards |
| Salons / appointment businesses | Booking-driven flexible | 6–10h | Split possible | Midweek offs | Chair/station | Booking apps | Appointments ≈ schedule |

---

## Current market / workflow findings

1. **Most Kuwait SMEs still schedule in Excel + WhatsApp**, then reconcile punches from biometric devices (ZKTeco / FingerTec / Hikvision class) into payroll — vendors (ZenHR, Bayanat, AiTIME, Odoo partners, FingerTec) sell the integrated gap Wathefni must eventually fill.
2. **PAM Res. 15/2025** raises the bar: declared working hours / rest / holidays become the **official inspection reference**. Wathefni schedules should eventually be exportable to that declaration shape.
3. **Hospitality and retail** need **split shifts** and late closes more than office 09:00–17:00.
4. **Healthcare, security, oil, factories** need **overnight / cross-midnight** and often **rotations** — Wave 0’s “same-day only create” is a **sector blocker**, not a niche gap.
5. **Construction** needs **seasonal midday constraints** and site transport — schedule is not only clock times.
6. **Oil Law 28/1969** introduces **rotation-cycle averaging** and **remote travel/accommodation** obligations that pure daily assignments cannot express alone.
7. **Open shifts / call-outs / last-minute coverage** are operationally common; full software support is rare outside larger HR suites — WhatsApp remains the replacement channel.
8. **Schedule publishing lead time** varies: offices ~1 week; retail/hospitality often mid-week for next week; security/healthcare continuous rolling rosters.

---

## Common roster patterns (canonical library)

| Pattern ID | Shape | Typical sectors |
|---|---|---|
| `fixed_week` | Same days/hours each week | Office, school, salon |
| `six_on_one_off` | 6 work + 1 rest | Security, cleaning, some nursing |
| `five_two` | Sun–Thu work | Professional services |
| `split_peak` | Two windows same calendar day | Restaurants, some retail |
| `three_band_rotate` | Morning / evening / night rotation | Government hospitals (documented) |
| `twelve_two_crew` | 12h day/night dual crew | Private hospitals, security, industry |
| `four_on_four_off` | 4×12h + 4 off | Industry, some 24/7 ops |
| `panama_223` | 2-2-3 style | Continuous ops (less Kuwait-documented; keep as library option) |
| `remote_rotation` | On-site hitch + off-site rest (cycle-average hours) | Oil/gas, remote construction |
| `seasonal_ramadan` | Shortened daily windows | All private sector during Ramadan |
| `seasonal_midday_ban` | Outdoor window constraints | Construction / outdoor labour |

---

## Recommended canonical data model

Layered so small companies never touch enterprise objects.

### L0 — Assignment authority (must exist for everyone)

`shift_assignments` remains **canonical published work intervals**, with:

| Field / concept | Why |
|---|---|
| `shift_date` + `start_time` + `end_time` | Keep |
| **`ends_next_day` / overnight span** (or `end_at` timestamptz) | Cross-midnight for healthcare/security/oil |
| `timezone` (Asia/Kuwait default) | Keep |
| `status`: `draft` \| `scheduled` \| `cancelled` (+ later `published` alias) | Soft lifecycle |
| `employee_key` **required & must exist** | Wave 0 orphan P0 |
| Optional `team_key` / `branch_key` / `site_key` / `role` / `position_key` | Org + coverage without forcing use |
| `break_minutes` / `break_policy_id` | Art. 65 compliance metadata |
| `source`: manual \| template_instance \| rotation_instance \| swap \| open_claim | Provenance |
| `schedule_version_id` nullable | Publish lineage |
| `row_version` / `updated_at` concurrency | Already partially required |
| `shift_events` append-only | Keep |

**Split shifts** = **multiple L0 assignments** same employee/date (already conflict-safe if non-overlapping). Do **not** invent a special split row type.

### L1 — Templates & recurring (medium)

| Object | Role |
|---|---|
| `shift_templates` | Named window (e.g. Morning 07–14, Night 22–07) |
| `recurring_schedules` | RRULE / weekday mask + template + assignee set + effective dates |
| Materializer | Expands to L0 assignments in a date window |

### L2 — Enterprise rostering

| Object | Role |
|---|---|
| `roster_patterns` | 4-on/4-off, 6-on/1-off, remote hitch definitions |
| `schedule_periods` | Draft → review → **publish** with effective dating |
| `coverage_rules` | Min staff by site/role/band |
| `open_shifts` | Unassigned published need |
| `availability_requests` + **decide** | Preferred / unavailable (schema exists; decide missing) |
| `shift_swap_requests` | Keep; add self-decision ban |
| `seasonal_profiles` | Ramadan / midday-ban overlays |
| `site_logistics` | Transport pickup, camp, gate access flags |

### Derived boundaries (never money in Shifts)

- **Attendance:** attribute punches/projections to L0 assignment intervals (overnight-aware).  
- **Leave:** conflict against L0; cancel/acknowledge on approve.  
- **Payroll:** scheduled-hours + planned OT flags handoff only.  
- **PAM:** export declared hours/rest from published L0 + policy.

---

## Configurable policy model

| Policy | Default (Kuwait-aware) | Tier |
|---|---|---|
| `weekly_hours_cap` | 48 (36 in Ramadan profile) | All |
| `daily_hours_cap` | 8 (6 Ramadan) | All |
| `rest_after_consecutive_hours` | 5h → 60m break | All |
| `weekly_rest_rule` | 24h after 6 days; preferred weekday=Fri | All |
| `allow_overnight` | **true** (foundation); company may disable | All |
| `allow_split_day` | true | All |
| `require_publish` | false (simple direct assign) | Medium+ |
| `publish_lead_days` | 0 / 3 / 7 | Medium+ |
| `min_staffing_enforced` | false | Enterprise |
| `self_swap_forbidden` | **true** | All |
| `leave_conflict_mode` | `block` \| `require_ack` \| `auto_cancel_future` | All |
| `lifecycle_future_shift_mode` | cancel on terminate/suspend | All |
| `women_night_warning` | on | All |
| `seasonal_profile_id` | null / ramadan / midday_ban | Medium+ |
| `pam_declaration_sync` | off until compliance wave | Enterprise |

---

## Simple / medium / enterprise product tiers

| Capability | Simple | Medium | Enterprise |
|---|---|---|---|
| Direct assign / cancel / reschedule | ✓ | ✓ | ✓ |
| Overnight + split | ✓ | ✓ | ✓ |
| Manager scope + self-swap ban | ✓ | ✓ | ✓ |
| Templates + recurring expand | — | ✓ | ✓ |
| Availability decide | — | ✓ | ✓ |
| Swaps + open shifts | basic swaps | ✓ | ✓ |
| Draft → publish + versions | — | optional | ✓ |
| Rotations / coverage minima | — | — | ✓ |
| Multi-site logistics / remote hitch | — | — | ✓ |
| PAM export / seasonal overlays | — | seasonal flags | ✓ |
| Complexity visible to user | Direct board only | Templates tab | Roster studio |

**Rule:** Enterprise objects never block Simple path. Unpublished drafts never affect Attendance/Payroll.

---

## Exact changes needed to proposed Wave 1 foundation

Wave 0 proposed Wave 1 as authority/safety. Wave 0B **amends** that foundation:

| # | Change vs Wave 0 Wave-1 plan | Why |
|---|---|---|
| 1 | **Decide overnight = allow** (Attendance-compatible encoding) as Wave 1 deliverable, not optional doc-only | Healthcare/security/oil are mainstream Kuwait sectors |
| 2 | Add **`ends_next_day` (or timestamptz end)** + conflict math across midnight | Unblocks L0 for night work |
| 3 | Treat **split** as multi-assignment (document + smoke); no new type | Already near-ready |
| 4 | Keep orphan cleanup, reschedule concurrency, self-swap ban, employee existence + lifecycle gates | Still P0 |
| 5 | Leave×shift policy remains | Still P1 integrity |
| 6 | Add **break_minutes optional** on create (default null; policy warn later) | Art. 65 without forcing punches |
| 7 | Add optional structured **`site_key`/`branch_key`** passthrough if org keys exist; else keep free-text `location` | Multi-site without enterprise UI |
| 8 | **Do not** build templates/publish/rotations/open shifts/PAM export in Wave 1 | Still Wave 2–4 |
| 9 | Schema comments / honesty flags: `allow_overnight`, rest-day not hardcoded Friday | Avoid office-only assumptions |
| 10 | Synthetic markers distinct from Leave/Attendance | Unchanged |

**Wave 1 renamed scope:** *Shifts Authority, Safety & Overnight Foundation*  
Still: no UI redesign, no templates, no broad employee app, no Payroll money, no frozen-module changes.

---

## Recommended phased implementation plan

| Wave | Goal |
|---|---|
| **0** | Prod truth — done (PARTIAL) |
| **0B** | Kuwait sector + legal research — **this document** |
| **1** | Authority/safety + **overnight L0** + concurrency + self-swap + orphan/lifecycle/leave gates |
| **2** | Schedule integrity: effective history, availability decide, swap prove-out, attendance link, reminder reliability, seasonal policy flags |
| **3** | Controlled HR/manager UX (week board) using L0 only — EN/AR |
| **4** | Templates + recurring materializer (Medium tier) |
| **5** | Publish versions, open shifts, coverage rules (Enterprise start) |
| **6** | Rotations (incl. remote hitch), PAM export, logistics flags |

---

## Unresolved questions requiring customer interviews

1. Which rest-day pattern do target customers actually use (Fri only vs Fri+Sat vs rotating)?  
2. For hospitality: are split shifts unpaid gap legally treated as two work periods only, and do managers expect one “shift card” or two rows?  
3. Private hospital preference: 3-band rotation vs 12h dual crew?  
4. Security contractors: is 12h×6 days still common after PAM enforcement, or shifting to 8h?  
5. Oil/industrial: which hitch lengths (14/14, 28/28, etc.) and is travel time paid into Attendance or Payroll only?  
6. Retail: how many days ahead is roster published, and who owns last-minute call-outs?  
7. Should Wathefni warn vs block on women-night and juvenile rules at schedule time?  
8. Do customers need PAM declaration export in year-1, or is biometric+payroll enough?  
9. Appointment businesses: schedule from bookings, or bookings independent of Shifts?  
10. Minimum staffing: soft warn or hard publish block?

---

## Source notes (non-exhaustive)

- Law No. 6 of 2010 Arts. 64–68 (hours, breaks, OT, weekly rest) — WageIndicator / Kuwait HR Worker’s Guide / secondary legal commentaries  
- Law No. 28 of 1969 (oil) — rotation average hours, remote travel pay, rest-day by employer  
- PAM Resolution No. 15 of 2025 — electronic working-hours declaration  
- MOH nursing shift study (morning/evening/night bands, 6-on/1-off)  
- Job-ad patterns for security/cleaning (12h, transport, Friday off)  
- Vendor landscape: ZenHR, Bayanat, AiTIME, FingerTec, Odoo Kuwait partners  
- Hospitality split-shift operational norms (GCC/global practice applied to Kuwait F&B)

**Confidence:** Legal matrix = **high** (statute + PAM). Sector matrix = **medium** (studies + ads + vendor claims; **interviews pending**). Architecture = **design recommendation**, not implementation.

---

## What Wave 0B did not do

- No code, deploy, UI, dark features  
- No customer interviews executed  
- No changes to frozen Employees 360, Onboarding, Attendance, Leave, pre-hiring, or Wave D  
- No orphan mutation from Wave 0
