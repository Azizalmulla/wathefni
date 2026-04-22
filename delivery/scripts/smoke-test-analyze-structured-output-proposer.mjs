#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for delivery/scripts/analyze-structured-output-proposer.mjs.
//
// The analyzer has a bundled --selftest mode that feeds a synthetic corpus
// through the real parsing/accumulation/rendering path and asserts the
// exact bucket counts. This wrapper:
//   1. delegates to --selftest so the corpus stays colocated with the
//      analyzer (one source of truth for expected metrics), and
//   2. re-imports the module and exercises a few additional properties the
//      self-test doesn't verify: that --json output is parseable, that the
//      report contains all section headings, and that CLI flag parsing
//      handles --top / --conv / --min-samples without blowing up.
//
// Failure here indicates the analyzer or emit schema drifted out of sync.
// ---------------------------------------------------------------------------

import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const analyzerPath = path.join(__dirname, "analyze-structured-output-proposer.mjs");

function assert(cond, msg) {
  if (!cond) {
    process.stderr.write(`smoke-test-analyze-structured-output-proposer: ${msg}\n`);
    process.exit(1);
  }
}

// 1. delegate to --selftest. The analyzer exits 0 on success and prints
//    "selftest OK". On failure it exits non-zero with a descriptive message.
try {
  const out = execFileSync(process.execPath, [analyzerPath, "--selftest"], {
    encoding: "utf8",
  });
  assert(out.includes("selftest OK"), `expected "selftest OK" in analyzer output, got: ${out}`);
} catch (err) {
  const stderr = err && err.stderr ? err.stderr.toString() : "";
  const stdout = err && err.stdout ? err.stdout.toString() : "";
  assert(
    false,
    `analyzer --selftest failed\nstdout=${stdout}\nstderr=${stderr}\n`,
  );
}

// 2. module-level checks. Import the analyzer and run the synthetic corpus
//    through analyze() so we can verify the JSON shape and rendered report
//    layout directly.
const mod = await import(analyzerPath);
const {
  analyze,
  renderReport,
  toJson,
  buildSyntheticCorpus,
  parseLine,
  TURN_INTENT_KINDS,
  TURN_INTENT_ADDRESSED_FIELDS,
  CLASSIFICATION_BUCKETS,
} = mod;

const lines = buildSyntheticCorpus();
const acc = analyze(lines);
const report = renderReport(acc, { top: 2 });

// Required section headings.
for (const heading of [
  "Schema versions",
  "Payload validity",
  "ti_classification",
  "ac_classification",
  "ti_kind distribution",
  "ti_confidence distribution",
  "addressed_fields coverage by stage",
  "ti_kind × stage",
  "Suspicious patterns",
  "ac_kind distribution",
  "Validator errors observed",
]) {
  assert(
    report.includes(heading),
    `report missing required heading: "${heading}"\n---\n${report}\n---`,
  );
}

// Conformance line.
assert(
  /conformance \(present \/ \(present \+ missing\)\):\s+\d/.test(report),
  `report missing conformance rate line`,
);

// JSON shape.
const json = toJson(acc);
const jsonStr = JSON.stringify(json);
const reparsed = JSON.parse(jsonStr);
for (const key of [
  "totals",
  "schema_versions",
  "payload_validity",
  "ti_classification",
  "ac_classification",
  "ti_kind",
  "ti_confidence",
  "ac_kind",
  "field_coverage_by_stage",
  "field_coverage_by_requested_slot",
  "kind_by_stage",
  "kind_by_requested_slot",
  "errors_observed",
  "suspicious",
]) {
  assert(key in reparsed, `JSON missing key: ${key}`);
}

// All TI kinds surface in ti_kind (even if zero) so downstream dashboards
// can rely on stable keys.
for (const kind of TURN_INTENT_KINDS) {
  assert(kind in reparsed.ti_kind, `ti_kind JSON missing kind key: ${kind}`);
}
for (const bucket of CLASSIFICATION_BUCKETS) {
  assert(bucket in reparsed.ti_classification, `ti_classification JSON missing bucket: ${bucket}`);
  assert(bucket in reparsed.ac_classification, `ac_classification JSON missing bucket: ${bucket}`);
}
for (const susp of [
  "answered_but_empty_fields",
  "ack_or_refused_but_fields",
  "clarifying_question_but_fields",
  "corrected_prior_but_empty_fields",
  "ti_missing_on_expected_stage",
  "ti_unexpected",
  "invalid_payload_v12",
  "unknown_token_in_addressed_fields",
  "ac_vs_ti_contradiction",
]) {
  assert(susp in reparsed.suspicious, `suspicious JSON missing bucket: ${susp}`);
  assert(
    typeof reparsed.suspicious[susp].count === "number",
    `suspicious[${susp}].count is not a number`,
  );
  assert(
    Array.isArray(reparsed.suspicious[susp].samples),
    `suspicious[${susp}].samples is not an array`,
  );
}

// parseLine robustness: a few representative shapes.
//   a) emit_failed hint
{
  const r = parseLine("[structured-output/proposer] emit failed conversation=X");
  assert(r && r.kind === "emit_failed", "parseLine should recognize emit-failed lines");
}
//   b) journalctl prefix + compact-list with pipes
{
  const r = parseLine(
    "2026-04-22T10:00:00Z host svc: [structured-output/proposer] conversation=CX turn_id=T1 ti_addressed_fields=[sender_name|sender_phone] ti_classification=present",
  );
  assert(r && r.kind === "emit", "parseLine should extract journalctl-prefixed emits");
  assert(
    Array.isArray(r.tokens.ti_addressed_fields) &&
      r.tokens.ti_addressed_fields.length === 2 &&
      r.tokens.ti_addressed_fields[0] === "sender_name" &&
      r.tokens.ti_addressed_fields[1] === "sender_phone",
    `ti_addressed_fields mis-parsed: ${JSON.stringify(r.tokens.ti_addressed_fields)}`,
  );
}
//   c) empty compact-list
{
  const r = parseLine(
    "[structured-output/proposer] conversation=CX ti_addressed_fields=[] ti_classification=n/a",
  );
  assert(
    Array.isArray(r.tokens.ti_addressed_fields) &&
      r.tokens.ti_addressed_fields.length === 0,
    "empty compact-list should parse to []",
  );
}
//   d) non-proposer line returns null
{
  const r = parseLine("[directive-render/trace] { foo: 1 }");
  assert(r === null, "non-proposer lines should return null");
}
//   e) dash sentinel values
{
  const r = parseLine(
    "[structured-output/proposer] conversation=CX stage=- requested_slot=- ti_classification=n/a",
  );
  assert(r && r.tokens.stage === "-" && r.tokens.requested_slot === "-", "dash sentinels should pass through as literal '-'");
}

// CLI flag smoke: --json + --top + --conv + --min-samples parse and run.
//    Feed the synthetic corpus via stdin and check JSON is emitted.
const corpusText = buildSyntheticCorpus().join("\n") + "\n";
const jsonCli = execFileSync(
  process.execPath,
  [analyzerPath, "--json", "--top=1", "--conv=C1", "--min-samples=0"],
  { input: corpusText, encoding: "utf8" },
);
const cliJson = JSON.parse(jsonCli);
assert(cliJson.totals.conversations === 1, `--conv=C1 should yield 1 conversation, got ${cliJson.totals.conversations}`);
assert(cliJson.totals.emits_parsed === 5, `--conv=C1 should yield 5 emits, got ${cliJson.totals.emits_parsed}`);

// Text CLI smoke: stdin piped, default rendering, report non-empty.
const textCli = execFileSync(process.execPath, [analyzerPath], {
  input: corpusText,
  encoding: "utf8",
});
assert(
  textCli.includes("[structured-output/proposer] analyzer report"),
  "text CLI should emit analyzer report header",
);
assert(
  textCli.includes("Suspicious patterns"),
  "text CLI should include suspicious-patterns section",
);

// Guardrail: every documented TI addressed_field is represented in the
// by-stage coverage table skeleton so dashboards can key on stable rows.
assert(
  TURN_INTENT_ADDRESSED_FIELDS.every((f) =>
    report.includes(f),
  ),
  "report by-stage coverage should list every addressed_field",
);

process.stdout.write("smoke-test-analyze-structured-output-proposer: OK\n");
