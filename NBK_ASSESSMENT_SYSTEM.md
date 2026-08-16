# NBK Assessment System

## Goal

Build an SHL-aligned assessment and evaluation platform inside Wathefni for NBK.

The system should closely follow SHL-style methodology, scoring structure, competency grouping, and report format, while using only original Wathefni-generated content.

## Compliance Guardrails

- Do not copy SHL proprietary questions, OPQ items, item wording, charts, or report text.
- Use original AI-generated business and professional scenarios.
- Keep scoring deterministic, auditable, and separate from AI interpretation.
- AI may summarize official outputs, but must never change scores, bands, or job-match logic.

## Ability Assessments

The system must assess:

- Numerical Reasoning
- Verbal Reasoning
- Inductive or Logical Reasoning

Ability assessments should follow SHL Verify-style logic and reporting.

Questions must:

- Be original and AI-generated.
- Match SHL-style difficulty and structure.
- Use business or professional scenarios.
- Support randomized item banks.
- Produce raw score, percentile, T-score, Sten score, and interpretation band.

## Personality and Competency Assessment

The system should follow an OPQ-style Universal Competency framework:

- 20 competencies.
- 8 competency groups.
- 1 to 5 competency score.
- Color band per competency.
- Strength and development interpretation.
- Grouped display similar to SHL-style competency reports.

## Job Match System

Initial NBK job profiles:

- Teller
- Customer Service
- Sales Officer
- Operations Officer

Each role must support:

- Competency weighting.
- Ability weighting.
- Job match percentage.
- Low, Medium, or High fit.
- Strengths.
- Development areas.

Job match must come from the deterministic scoring engine, not AI.

## Reports

The system must generate:

- Verify Ability-style report.
- OPQ Competency-style report.
- Mass Assessment-style report.

Reports must include:

- Ability scores.
- Competency profile.
- Strengths.
- Development areas.
- Job suitability.
- Clear HR-friendly interpretation.

Report numbers must always come from the official score JSON.

## AI Layer

AI is an HR-assistant layer on top of official scoring outputs.

AI can generate:

- Report summaries.
- Hiring recommendations.
- STAR interview questions.
- Follow-up interview probes.
- HR insights.

AI must always use the exact same scoring data shown in the assessment report.

## Proposed Wathefni Architecture

Build this as a deterministic assessment module in the live Wathefni workspace.

Primary targets:

- `/root/.openclaw/workspaces/company-wathefni/tools/assessments/`
- `/root/.openclaw/workspaces/company-wathefni/tools/db/schema.sql`
- `/root/.openclaw/workspaces/company-wathefni/tools/db/update_state.py`
- `/root/.openclaw/workspaces/company-wathefni/tools/google/sync_candidate_sheet.py`
- `/root/.openclaw/workspaces/company-wathefni/SKILL.md`
- `/root/.openclaw/workspaces/company-wathefni/TOOLS.md`

Use `/root/.openclaw/extensions/octopus-channel.ts` only for routing and context, not scoring logic.

## Data Model

Add durable assessment records:

- `assessment_batteries`: battery versions, sections, timing, active flag.
- `assessment_items`: original item text, section, difficulty, answer key, scoring metadata, version.
- `assessment_attempts`: candidate, app key, battery, random seed, status, timestamps.
- `assessment_responses`: item id, response, correctness or keyed value, response time, raw response.
- `assessment_scores`: ability scores, competency scores, job match, bands, norm version.
- `assessment_reports`: structured report JSON and generated artifact paths.

Mirror final output for compatibility:

- `data/candidates/{PHONE}/applications/assessments/{APP_KEY}.json`

## Deterministic Scoring

Ability scoring:

- Raw correct count.
- Percentile.
- T-score.
- Sten.
- Interpretation band.

Competency scoring:

- Item-to-competency mapping.
- Reverse-key support.
- 1 to 5 competency scores.
- Color bands.
- Strength and development interpretation.

Job match scoring:

- Role-specific ability weights.
- Role-specific competency weights.
- Weighted fit percentage.
- Low, Medium, or High fit.
- Strengths and development areas.

Initial norming can use an internal synthetic norm table until NBK provides official benchmark data. Every report must show the norm version.

## Candidate and HR Flow

HR-triggered commands:

- `send assessment to Fouad for Teller`
- `send NBK assessment to candidate`
- `show Fouad assessment report`
- `compare assessment fit for Teller vs Customer Service`
- `generate interview probes from his report`

Candidate flow:

- Send short assessment intro and instructions.
- Ask assessment questions one at a time or by compact section batches.
- Save each answer immediately.
- Score only after completion.
- Notify HR when complete.
- Generate report artifacts from official score JSON.

## Verification

Required tests:

- Item bank validation, no missing keys, invalid mappings, or duplicate item IDs.
- Scoring determinism, same responses always produce same score JSON.
- Role-match determinism for Teller, Customer Service, Sales Officer, and Operations Officer.
- Report consistency across JSON, report artifacts, Google Sheet sync, and AI summaries.
- WhatsApp regression, AI must not invent scores before completion.

## Rollout

1. Build the schema, item bank format, and validation tools.
2. Implement deterministic scoring for abilities, competencies, and role match.
3. Generate structured Verify, OPQ, and Mass Assessment-style reports.
4. Wire official scores into Google Sheet columns.
5. Add HR tools for start, answer, score, report, and compare.
6. Update AI tool contracts so AI only summarizes official outputs.
7. Wire candidate and HR WhatsApp flow.
8. Add smoke tests and run against fixed fixtures.

