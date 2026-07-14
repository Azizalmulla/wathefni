# HR-2 Staging Runtime Proof

Status: staging green; production unchanged.

Backend artifact:

`d96b7843e05cd322886e6befb7e7847833d23abb49d27fedcea67f8a84b8eef3`

The local and `/opt/wathefni/staging/orchestrator` hashes matched exactly.

## Verification

- Existing complete staging smoke suite: passed.
- HR-1 operator-mobile staging regression: 70 passed, 0 failed.
- HR-2 DB-backed staging verifier: 36 passed, 0 failed.
- Local HR-2A contract smoke: 33 passed, 0 failed.

The HR-2 verifier proved:

- real operator-mobile login and `/dashboard/mobile/me`;
- backend-current capability response, including shortlist confirmation;
- mobile priorities, leave list/detail and candidate detail;
- tenant isolation and cross-tenant 404 behavior;
- dashboard-user-ID manager scope and out-of-scope detail denial;
- leave prepare, explicit confirmation, successful decision and replay idempotency;
- stale leave conflict rejection;
- candidate CV access audit on a safe unavailable-file result;
- candidate shortlist prepare/confirm through the existing action registry;
- backend-authoritative candidate status;
- grant-only employee search and next-request grant revocation;
- next-request module removal;
- next-request company disable;
- refresh rotation, logout and revoked access.

## Isolation remediation found during proof

The existing candidate mutation wrapper called workspace tools whose `--env`
default pointed at production. HR-2 now passes the backend-current env path and
overrides the child process environment from that file, covering candidate
shortlist/reject and the hire/post-hire transition. The verifier then completed
the candidate mutation against staging.

No production candidate mutation occurred during the failed staging attempts;
the updater returned `application not found` before any write.

## Runtime boundaries

- staging delivery mode remained `dry_run`;
- no production deploy or production configuration change;
- no Employee App contract change;
- no Setup Console or legacy AI Recruiter exposure;
- no push delivery, EAS credentials or store submission.
