# HR-2 Preview Verification Matrix

Automated in `scripts/verify-preview.mjs` against Chromium and WebKit. Every case
is loaded, asserted, refreshed, and asserted again with URL state preserved.

- HR Home: English and Arabic RTL; HR-only, restricted manager and
  multi-workspace; ready, empty, revoked and company-disabled states.
- Leave Approval: English and Arabic RTL; HR-only and restricted manager;
  ready, loading, stale and successful-decision states.
- Candidate Review: English and Arabic RTL; recruiter-only and multi-workspace;
  ready, error and revoked states.

Additional manual controls expose every operator/scenario combination from the
stable preview URL. Inaccessible sections are removed rather than rendered as
empty gaps. HR-only users receive no recruiting actions; recruiter-only users
receive no HR decisions; restricted managers retain restricted scope metadata.

Captured WebKit screenshots:

- `docs/screenshots/home-en.png`
- `docs/screenshots/home-ar.png`
- `docs/screenshots/leave-en.png`
- `docs/screenshots/leave-ar.png`
- `docs/screenshots/candidate-en.png`
- `docs/screenshots/candidate-ar.png`

The preview is fixture-only and disconnected from every API environment.
