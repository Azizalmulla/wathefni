# Canonical candidate and interview UX — staging review

Status: **Not approved for production promotion**

The updated admin dashboard is deployed to staging on port 8011 with
`WATHEFNI_CANONICAL_LIFECYCLE=true`. Production data and production services were
not touched.

## Implemented

- Candidate list and detail use the eight canonical application stages.
- CV processing, screening, intake source, communication, interview data, and
  Wathefni analysis remain separate facets.
- Candidate and interview actions are rendered from backend `allowed_actions`.
- Shortlist, reject, schedule interview, and hire retain explicit human
  confirmation.
- Communication is normalized to `pending`, `sent`, `failed`, or
  `intentionally_skipped`, including a prominent uninformed-candidate warning.
- Interview status is distinct from both application stage and invitation
  delivery status.
- Interview detail exposes schedule, channel/location, invitation,
  confirmation, notes, advisory analysis, and next human action without hiding
  them in accordions.
- English and Arabic lifecycle labels are shared and tested across admin web
  and Wathefni HR mobile.
- Legacy environment markers such as `production` no longer appear as intake
  methods; they render as “Source not recorded.”

## Screenshot evidence

Admin web screenshots use the deployed staging build and staging data:

- `web-en-candidate-list.png`
- `web-en-candidate-detail.png`
- `web-en-interview-list.png`
- `web-en-interview-detail.png`
- `web-ar-candidate-list.png`
- `web-ar-candidate-detail.png`
- `web-ar-interview-list.png`
- `web-ar-interview-detail.png`

Wathefni HR mobile screenshots use the fixture-only review build with the
production shared screen components. It performs no network request or
mutation:

- `mobile-en-candidate-list.png`
- `mobile-en-candidate-detail.png`
- `mobile-en-interview-list.png`
- `mobile-en-interview-detail.png`
- `mobile-ar-candidate-list.png`
- `mobile-ar-candidate-detail.png`
- `mobile-ar-interview-list.png`
- `mobile-ar-interview-detail.png`

## Verification results

- Admin web: 38 tests passed; production build passed.
- Wathefni HR mobile: 44 tests passed; TypeScript check and web preview export
  passed.
- Canonical lifecycle staging DB smoke: 77 passed, 0 failed.
- No sparkle, wand, magic, or starburst icon remains in the recruiting screens.
- HR mobile staging reads passed for candidate detail, advisory metadata,
  interview list, interview detail, and interview notes.

## Staging blockers

The repository-wide staging gate did not complete. It consistently stopped in
the unrelated leave standalone harness because an owner `request_leave` action
returned `permission_denied`.

The focused HR mobile verifiers exposed the same broader permission-authority
drift:

- HR-2: 30 passed, 16 failed.
- HR-3: 58 passed, 12 failed.
- Candidate and several post-hire write preparations were advertised by the
  capability payload but rejected by the action endpoint with
  `permission_denied`.

That mismatch means the staging API does not yet prove that advertised actions
and executable permissions are identical. Changing permission policy is outside
this UX scope, so production promotion must remain blocked.

## Exact production rollout recommendation

1. Do not run `ops/deploy.sh production` for this artifact.
2. Resolve the staging permission-authority mismatch without changing the
   intended permission policy: align the staging role/grant fixtures and
   authorization plumbing so an advertised action is executable and an
   unadvertised action remains denied.
3. Rerun `ops/hr2-staging-verify.py`, `ops/hr3-staging-verify.py`, and
   `ops/deploy.sh staging` from the exact release working tree.
4. Require all three to pass. Confirm that `deploy.sh staging` records the exact
   artifact hash in `/opt/wathefni/staging/last-green.sha256`.
5. Repeat the four English and four Arabic admin-web checks against staging.
   Produce an authenticated native/internal-distribution Wathefni HR build
   pointed at the staging API and repeat the same four screens before store
   promotion.
6. Promote the unchanged, staging-green artifact with
   `ops/deploy.sh production`. Do not rebuild between staging and production.
7. Run read-only production checks for `/health`, candidate list/detail, and
   interview list/detail. Verify stage, communication, and `allowed_actions`
   parity for one authorized and one restricted operator.
8. Monitor authorization errors and failed outbound delivery for 30 minutes.
   If lifecycle labels, action visibility, or authorization diverges, run
   `ops/deploy.sh rollback`.

Stop point: staging review complete; production promotion intentionally not
performed.
