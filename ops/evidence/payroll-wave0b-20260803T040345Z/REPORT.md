# Payroll Wave 0B REPORT

**Gate:** `PROD_RESEARCH_PAYROLL_WAVE0B_ARCHITECTURE_GO`  
**Stamp:** `20260803T040345Z`  
**Mode:** research only  

Full research: `ops/PAYROLL_WAVE0B_KUWAIT_GCC_ARCHITECTURE_RESEARCH.md`  
Prior: Wave 0 `PROD_READONLY_PAYROLL_WAVE0_NO_GO`

## Verdict

| Question | Answer |
|---|---|
| Native gross-to-net + PIFSS + WPS + EOS in Wave 1? | **NO** |
| Mode-agnostic money-authority foundation in Wave 1? | **YES** |
| External Payroll as first-class mode? | **YES (default for customers with engines)** |
| Parallel migration mode? | **YES (Wave 2+)** |
| Enforce Art. 51/66/69 calculators now? | **NO — counsel-gated** |
| XBRL | **Out of scope** |

## Exact Wave 1

Money-authority foundation: salary contracts, pay periods, SOD/self-approve bans, attendance handoff truth, `native|external|parallel_shadow` mode flag, external input-export schema stub. **No payment processing.**

## Modes

- **Native** — Wathefni closed run is money authority (later waves)  
- **External** — external posted run is money authority; Wathefni owns inputs + mirrors results  
- **Parallel** — external pays; Wathefni shadow compares  

PROD_RESEARCH_PAYROLL_WAVE0B_ARCHITECTURE_GO
