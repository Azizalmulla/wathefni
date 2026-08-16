# Payroll Authority P4B Preparation — Kuwait Statutory Source Pack (not activated)

**Status:** superseded by public baseline activation — see `ops/PAYROLL_AUTHORITY_P4B.md`  
**Pack ID:** `KW_STATUTORY_SOURCE_PACK_P4B_PREP_v1.0.0` (research pack retained)  
**Activation pack:** `KW_STATUTORY_PUBLIC_BASELINE_P4B_v1.0.0` / policy `KW_PUBLIC_BASELINE_v1.0.0`

## Deliverables

| Artifact | Path |
|---|---|
| Versioned source pack + counsel matrix | `ops/PAYROLL_AUTHORITY_P4B_KUWAIT_STATUTORY_SOURCE_PACK.md` |
| Machine-ready candidate records | `ops/payroll_authority_p4b_candidate_records_v1.json` |
| Seed loader (awaiting_legal_validation only) | `ops/seed-payroll-authority-p4b-candidates.py` |

## Candidate invariants (enforced)

- `approval_status=awaiting_legal_validation`
- `legal_claim=false`
- `counsel_signed=false`
- `is_architecture_fixture=false`
- PIFSS numeric rows use `rate_awaiting_legal_validation=true` (never architecture fixture as a legal stand-in)
- Candidates **must not** resolve on the legal money path (`require_legal_claim=true`)

## Seed usage

```bash
# Validate payload only
python3 ops/seed-payroll-authority-p4b-candidates.py

# Insert country-level candidates (canary/ops; still not approved)
python3 ops/seed-payroll-authority-p4b-candidates.py --apply --company WATHEFNI
```

## Next gate (human)

Counsel sign-off on unresolved questions in the source pack, then a separate P4B activation change control to flip `approved` + `legal_claim=true` + `counsel_signed=true`.
