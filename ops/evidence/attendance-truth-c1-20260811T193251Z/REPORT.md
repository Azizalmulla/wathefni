# Attendance Truth C1 — Staging Prove

- Stamp: 20260811T193251Z
- Unit: YES
- Staging: YES
- Freeze regression: YES
- Global CAPTURE_INGEST: remains **off** (company allowlist fail-closed when temporarily process-scoped on)
- Canary: ATTTRUTH synthetic in smoke; entitlement pattern for WATHEFNI / dedicated truth tenant
- Verdict: **ATTENDANCE_TRUTH_FULL_PASS**

## Proven
1. Global ingest off / empty allowlist deny
2. Company-entitled ingest → punches → day projection
3. Correction approve ≠ apply; apply mutates projection
4. Reject does not apply

## Stop
Do **not** start C2 Leave Enforcement until owner reviews this stamp.

Evidence: `/Users/azizalmulla/Desktop/claw/ops/evidence/attendance-truth-c1-20260811T193251Z`
