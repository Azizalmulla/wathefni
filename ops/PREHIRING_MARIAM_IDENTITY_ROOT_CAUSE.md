# Mariam CV Identity Root Cause

Date: 2026-07-26  
Environment: production, read-only investigation  
Resolution: `e4817b46-d840-4317-8d96-9bf3c9755f13`

## Conclusion

Mariam's CV was held because the matcher applies Python
`SequenceMatcher` to the entire normalized name and treats any score `>= 0.72`
as a weak match. Four unrelated WATHEFNI candidates share the surname
`almulla`; the shared `" almulla"` suffix pushed all four above the threshold
despite different first names and no matching email or phone.

The **fail-closed action was correct**: the system did not merge, create,
extract, or classify without confirmed ownership. The **weak-match detector is
overly sensitive for this case** and produced a false-positive review.

No data was modified or cleaned.

## Exact CV values used

Durable `pdftotext` extraction:

- name: `Mariam Almulla`
- email: `mariam.almulla@example.com`
- phone: `96555629147`

Normalized values compared:

- name: `mariam almulla`
- email: `mariam.almulla@example.com`
- phone: `96555629147`

The durable extractor returned the phone without `+`; no existing candidate
matched either the exact normalized phone or the digit-equivalent
`+965 5562 9147`.

## Exact rule

Deployed policy: `inbound-cv-identity-v1`.

1. Candidates are loaded only through applications where
   `applications.company_code='WATHEFNI'`.
2. Email and phone exact matches are strong identity keys.
3. Name similarity is:

   `SequenceMatcher(None, normalized_cv_name, normalized_candidate_name).ratio()`

4. A score `>= 0.72` adds a weak candidate.
5. If there is no strong candidate but at least one weak candidate, the result
   is:
   - `possible_match`
   - `weak_name_match_requires_hr_review`
6. `new_candidate` is reached only when both strong and weak candidate sets are
   empty.

Ignored name tokens are only:
`cv`, `resume`, `curriculum`, `vitae`, `updated`, `update`, `new`, `v2`,
`السيرة`, and `الذاتية`.

The matcher does not distinguish first name from surname.

## Every candidate considered

The production query returned 19 application rows grouped into 14 candidates.
All were tenant-scoped to `WATHEFNI`.

| Candidate key | Source name → normalized | Compared email(s) | Compared phone(s) | Similarity | Applications |
|---|---|---|---|---:|---|
| `96599652277` | Faisal Almulla → `faisal almulla` | `fslalmulla@gmail.com`; malformed parsed value `fslalmulla@gmail.comlocation` | `96599652277` | **0.78571429** | `SOCIAL_MEDIA_MANAGER` (shortlisted) |
| `96598900677` | AZIZ ALMULLA → `aziz almulla` | `azizalmulla16@gmail.com` | `96598900677` | **0.76923077** | `HR` (shortlisted); `ACCOUNTING` (review_pending); `FINANCE` (screening) |
| `96599338566` | Aziz Almulla → `aziz almulla` | `azizalmulla16@gmail.com` | `96599338566` | **0.76923077** | `FULLSTACK_DEVELOPER` (screening_complete) |
| `96597485758` | Hamad Almulla → `hamad almulla` | `h.almulla@almulla-media.com` | `96597485758`; `97485758` | **0.74074074** | `ACCOUNTING_EXCEL` (screening_complete); `HR` (shortlisted) |
| `imp-wathefni-837eb9b1bf14506b` | yasser al dossary → `yasser al dossary` | `yasser.aldossary@example.com` | `96555501842` | 0.38709677 | held import (`needs_role`) |
| `imp-wathefni-06ffffc36d7fd375` | Esraa Aziz → `esraa aziz` | `azizalmulla16@gmail.com` | none | 0.33333333 | held import (`needs_role`) |
| `96550252254` | Talal Fadhli → `talal fadhli` | `talalabdalla89@gmail.com`; malformed parsed value with `location` suffix | `96550252254` | 0.30769231 | `SOCIAL_MEDIA_MANAGER` (hired) |
| `96597727743` | MOHAMMAD QATTAN → `mohammad qattan` | `mohammad.qattan@gmail.com` | `96597727743` | 0.27586207 | `MARKETING_SPECIALIST` (hired); `FULLSTACK_DEVELOPER` (awaiting_cv) |
| `96555550133` | Test Candidate → `test candidate` | `test@example.com` | `96555550133` | 0.21428571 | `ACCOUNTING` (screening) |
| `96566363363` | Fouad Burhamad → `fouad burhamad` | `fb-urhama@gmail.com` | `96566363363` | 0.14285714 | `IT_MAINTENANCE` (hired) |
| `96555550132` | no name | none | `96555550132` | 0 | `ACCOUNTING` (awaiting_cv) |
| `96555550134` | no name | none | `96555550134` | 0 | `ACCOUNTING_EXCEL` (awaiting_cv) |
| `96555550135` | no name | none | `96555550135` | 0 | `ACCOUNTING_EXCEL` (awaiting_cv) |
| `96555550136` | no name | none | `96555550136` | 0 | `ACCOUNTING_EXCEL` (awaiting_cv) |

Only the first four crossed `0.72`. None had an exact email or phone match.

## Why the surname caused the collision

Matching blocks against Mariam:

- `faisal almulla`: shared suffix `" almulla"` (8 characters); first-name
  similarity `0.50`; full-name score `0.78571429`
- `aziz almulla`: shared suffix `" almulla"`; first-name similarity `0.40`;
  full-name score `0.76923077`
- `hamad almulla`: shared suffix `" almulla"`; first-name similarity
  `0.36363636`; full-name score `0.74074074`

Therefore this was effectively **surname-only matching**, even though the code
technically scores the complete string. No partial/surname-specific rule exists;
the whole-string metric allowed the common suffix to dominate.

## Why novel email and phone did not create Mariam

Production checks found:

- exact email candidate rows: `0`
- exact phone candidate rows, including digit-equivalent comparison: `0`
- exact email identity keys: `0`
- exact phone identity keys, including digit-equivalent comparison: `0`
- persisted `strong_keys`: empty

Novel email/phone values do not override a weak name candidate. The decision
order returns `possible_match` whenever `weak_candidates` is non-empty; only the
next fallback creates a new candidate.

## Stale or test records

No stale or test record caused the collision.

- The four colliding candidates all have `data_source='production'`.
- Their applications have active workflow states, not archived/deleted states.
- The explicit `Test Candidate` smoke record was considered, but scored only
  `0.21428571` and did not match.
- Two separate production Aziz records each contributed a weak match, but the
  highest score came from Faisal.
- The malformed `fslalmulla@gmail.comlocation` parsed email did not contribute;
  all four matches had `email_exact=false` and `phone_exact=false`.

## Narrowest safe fix

Keep the current fail-closed review behavior, but prevent a common surname from
creating a weak match by itself:

> For a name-only weak match, require corroboration outside the surname—for
> example, at least one additional name token match or a sufficiently similar
> first/given-name token. Do not accept whole-string `SequenceMatcher >= 0.72`
> when the only shared token is the final surname.

Exact email and phone matching should remain unchanged and authoritative. Add
focused cases for Mariam/Faisal/Aziz/Hamad, exact full-name duplicates,
multi-part Arabic/GCC names, and transliteration differences before promotion.

Under that narrow rule, this CV has no tenant-scoped identity match and should
resolve as `new_candidate`.

## Evidence

Full read-only production replay:

`/opt/wathefni/production-evidence/continuous-wathefni-release/20260726T161509Z/mariam-identity-root-cause.json`
