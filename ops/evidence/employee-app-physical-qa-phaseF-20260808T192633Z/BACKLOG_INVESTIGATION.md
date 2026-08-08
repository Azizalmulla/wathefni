# Uncommitted backlog — what is actually in it, and what is actually live

Investigation before committing anything. Read-only throughout.

---

## Headline

**Git is not the source of truth for this system. Production is.**

Production is deployed by copying files from this working tree to a VPS. Git has
been used as a lagging archive, and it lags badly: the last commit touching the
Employee App is **2026-07-14**, nearly a month ago.

The consequence is the opposite of what the file counts suggest. The 2452
uncommitted files are not unreviewed work waiting to ship — most of it is
**already running in production**. Committing is an archival exercise, not a
release.

---

## How deployment actually works

From `ops/deploy-*.sh`: the orchestrator is a systemd service
(`wathefni-orchestrator.service`) at `/opt/wathefni/orchestrator` on
`root@76.13.63.68`. Deploys `scp` `app.py` and named sibling modules from the
local working tree, back up the previous file, verify the AST parses, restart the
service, then health-check. The dashboard is `rsync`'d to `/var/www`.

No build from a git ref is involved at any point.

---

## Backend: exactly one delta between local and production

Compared the local `app.py` against the file actually running in production:

| | Lines |
|---|---|
| Deployed `/opt/wathefni/orchestrator/app.py` | 80,793 |
| Local `wathefni-orchestrator/app.py` | 80,917 |
| **Differing lines** | **128, in 5 hunks** |

All five hunks are Phase E:

```
67993a67994,68025    _home_document_renewal_detail helper
68125c68157          home task wiring
68130c68162,68171    home task wiring
69303a69345,69366    /app/leave/duration
69304a69368,69372    /app/leave/duration
69305a69374,69429    /app/leave/duration
```

Nothing else differs. Verified independently by route probe: 272 routes added in
the "uncommitted" git diff, and the ones sampled
(`/dashboard/superadmin/setup/auth/session`,
`/dashboard/prehire/assessments/queue`) already return 401 in production —
i.e. they exist there. Only `/app/leave/duration` returns 404.

**Meaning: deploying the backend ships my 128 lines and nothing else.** The
18,498-line git diff is archival lag, already live. This is a low-risk deploy.

---

## Mobile: three visual phases genuinely unpublished

Different situation. The mobile app cannot be file-copied; it ships via EAS
Update to the `canary` channel.

- Last commit touching `apps/wathefni-employee-mobile`: **2026-07-14** (`d251580`).
- Uncommitted since: 44 modified files (+5,966 / −1,415) and 52 untracked.
- That backlog contains Functional Phases 0–4, Auth Wave 2 (PIN, biometrics, the
  local `expo-screen-detector` native module), **and** Visual A+B, C+D, E.
- Phases 0–4 and Auth Wave 2 were published as OTAs (update IDs are in the canary
  log). **Visual A+B, C+D and E were not** — no update ID was ever recorded for
  them, because they were never published.

So the canary device is on the 2026-08-07 OTA, which predates all three visual
phases.

### This breaks the requested commit plan

"Commit A–E in reviewable chunks" cannot be done as stated. A–E and Phases 0–4
modified **the same files** — `HomeView.tsx`, `RemainingViews.tsx`,
`employeeAppComposition.ts` and others were each touched by both — and there is
no intermediate commit to diff against. The phase boundary exists only in the
chat transcripts, not in the filesystem, so git cannot reconstruct it.

What is achievable is a clean split **by subsystem**, which is reviewable even
though each commit spans phases:

1. Design tokens and premium primitives (`theme.ts`, `components/premium.tsx`, `ui.tsx`)
2. Layout and list primitives (`components/layout.tsx`, `lists.tsx`)
3. Composition contract and navigation (`employeeAppComposition.ts`, `app/_layout.tsx`, tabs, route moves)
4. Feature screens (`features/**`, `app/**` screens)
5. Localization (`i18n/**`)
6. Qualification gates (`scripts/**`)
7. Native module and build config (`modules/`, `app.json`, `eas.json`, `package.json`)
8. Docs and ops (`docs/**`, `ops/**`)

Plus one clean backend commit for Phase E (the 5 hunks above).

---

## Bearing on Physical QA

Unchanged, and now better quantified:

- **Backend** is a 128-line, five-hunk deploy away from being Phase E ready.
- **Mobile** needs a `canary` OTA publish; the changes across A–E are JS-only, so
  no native rebuild is required provided the installed build's runtime version is
  still `0.1.0`.
- Neither can be done from this environment (no `eas-cli`, not authenticated).
