# Orphan final disposition — Shifts Wave 1C

**Stamp:** recorded with Wave 1C evidence  
**Authority:** change-controlled classification; **no restoration performed**

## Classification rule

Restore only with a **verified canonical employee match** (exact `employees.employee_key` for WATHEFNI, or unambiguous phone/person identity with documented evidence). Absent that match → permanently invalid; retain cancelled audit history.

## Research summary

For each orphan:

- Exact `employees` match: **none**
- Phone-digit / key-suffix fuzzy hits: **none**
- Assignment fields `employee_phone` / `employee_name`: **null**
- Keys appear malformed / non-roster (`WATHEFNI-96596552203`, `WATHEFNI-96552202357`, `WATHEFNI-96552263564`)
- Quarantine snapshots + `orphan_quarantined` events present; status **cancelled**

## Final disposition

| shift_id | employee_key | Disposition |
|---|---|---|
| `0a6e73dd-9c6d-49a0-b253-39a9922ebd70` | `WATHEFNI-96596552203` | **Permanently invalid** — retain as cancelled audit history |
| `6a84a671-eb7f-43ea-870e-af859a440467` | `WATHEFNI-96552202357` | **Permanently invalid** — retain as cancelled audit history |
| `f9ebecf3-8838-456a-8124-c34c3c7600ca` | `WATHEFNI-96552263564` | **Permanently invalid** — retain as cancelled audit history |

**Restoration eligibility:** **NO** for all three (no verified canonical employee match).

**Actions taken this wave:** classification only. Rows remain soft-cancelled; quarantine metadata retained for audit; **not deleted**; **not restored**.
