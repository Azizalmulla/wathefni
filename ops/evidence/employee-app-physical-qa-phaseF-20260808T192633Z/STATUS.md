# Employee App Final Phase — Physical Visual QA

**Status: BLOCKED — not started.**
**EMPLOYEE_APP_READY_FOR_OWNER_FREEZE = NO (cannot be assessed).**

No physical device QA was performed. No visual, RTL, Dynamic Type, VoiceOver or
responsiveness verdict is claimed for any screen. This file exists so that no
later reader mistakes the absence of a report for a passing one.

---

## Why it could not start

### 1. The build the device would be running does not contain Phases A–E

All of Visual A+B, C+D and E exists only in the local working tree: 96
uncommitted files in `apps/wathefni-employee-mobile`, plus `app.py`. Nothing has
been committed, built, or published to the `canary` channel.

The phase brief says *"Do not qualify a stale build."* Whatever is on the canary
device today predates this work.

### 2. The Phase E backend reads are not in production

Probed directly against `https://api.wathefni.ai`:

| Route | Result | Meaning |
|---|---|---|
| `/app/me` | 401 | route exists, auth required |
| `/app/leave` | 401 | route exists, auth required |
| `/app/home` | 401 | route exists, auth required |
| `/app/leave/duration` | **404** | **route absent** |

The deployed backend predates Phase E. Even with a mobile OTA published, the
Request Leave duration line would never appear and the Home expiry task would
fall back to its generic label — so two of Phase E's six additions could not be
qualified at all.

### 3. This machine cannot perform the QA

- `eas-cli` is not installed and not authenticated: cannot publish an OTA, and
  cannot query which update the canary device is running.
- No Xcode and zero iOS simulators: no way to render the app for inspection,
  so even the simulator fallback the brief permits for extra widths is closed.
- No physical device, and no ability to see a screen, run VoiceOver, use Face ID,
  or tap a push notification.

Every deliverable the brief asks for — EN visual verdict, AR/RTL verdict,
responsive verdict, Dynamic Type verdict, VoiceOver verdict, per screen — is
obtainable only by a person holding the device.

---

## What was not done, explicitly

Not attempted, not simulated, not inferred from source: any visual verdict, any
RTL rendering check, any Dynamic Type check, any VoiceOver check, any composition
shape A–F check, any interaction test, any responsiveness measurement.

Producing that matrix from code inspection would have been fabrication. It would
also have been self-defeating: Phase E's headline finding was a screen printing a
confident "0 days available" that no system asserted, and inventing a QA result
is the same failure at a larger scale — with the owner freezing the app on the
strength of it.

---

## Required sequence before this phase can run

1. ~~**Commit** the Employee App work.~~ **Done** — 11 commits, `cf26d59..1e77bf6`.
   See "Commits" below. Working tree for the Employee App is clean; the rest of
   the repo's backlog was deliberately left untouched.
2. **Deploy the backend** so `/app/leave/duration` returns 401 rather than 404,
   and `/app/home` tasks carry `detail`. The delta against the running production
   file is 128 lines in 5 hunks, all Phase E — verified by pulling
   `/opt/wathefni/orchestrator/app.py` off the VPS and diffing.
3. **Publish the mobile OTA** to `canary`. The mobile changes across A–E are
   JS-only — no native module was added in these phases — so an OTA is sufficient
   provided the installed native build's runtime version still matches `0.1.0`.
   Record the update ID and the rollback ID.
4. **Install and force-quit/relaunch** on the canary device.
5. Confirm the build-verification block in `PHYSICAL_QA_CHECKLIST.md`.
6. Then run the checklist.

Steps 2–3 need credentials and authority this environment does not have.

---

## Commits

Backend:

| SHA | Subject |
|---|---|
| `c80900c` | expose leave duration and document expiry as read-only projections |

Mobile, split by subsystem. Phase-based commits were not reconstructible —
Visual A–E and Functional Phases 0–4 modified the same files with no intermediate
commit to diff against, so the boundary exists only in the chat transcripts:

| SHA | Subject |
|---|---|
| `6cada55` | refine the colour system and brand primitives |
| `5b0ed35` | shared page geometry, compact list and honest state primitives |
| `390edc4` | composition as the single navigation contract; tab bar settled |
| `b33bea9` | local device lock — PIN, biometrics and auto-lock |
| `a17bd3b` | correct the API contract and centralise formatting |
| `5cfc4b9` | rebuild the employee screens |
| `28432be` | EN/AR parity and RTL layout sync |
| `7cfae0d` | qualification gates |
| `a19140a` | screen-detector native module and OTA configuration |
| `1e77bf6` | capabilities doc and per-wave evidence |

Auth was split out of the feature-screen commit rather than folded into it: it is
the security surface and is worth reviewing alone.

**Bisectability caveat:** these are archival commits of a month of work that was
developed as a whole. Each is coherent to *review*, but intermediate commits will
not typecheck in isolation, because feature screens and primitives were written
against each other. Only the tip represents a building tree — verified: typecheck
clean and all gates green at `1e77bf6`.

---

## Artifacts here

- `build-state.txt` — the probes above, captured verbatim.
- `PHYSICAL_QA_CHECKLIST.md` — the full A–E device script, ready to run. Not run.
