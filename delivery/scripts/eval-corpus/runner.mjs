#!/usr/bin/env node
// Phase C eval corpus runner (2026-04-21).
//
// Hybrid harness:
//   - "live" cases run against the real prod webhook via
//     live-riders-harness.mjs. Between turns, the runner scrapes the
//     gateway journal for `[drift/get-price-bypass]` +
//     `[structured-output/proposer]` + `[proposer/tool-call]` emits that
//     landed after the turn's `acceptedAtMs`, records them per-turn, and
//     emits a per-turn verdict.
//   - "unit" cases run in-process (schema-validator round-trips today).
//
// Output:
//   reports/eval-corpus/<run_id>/raw.jsonl      — one event per run/turn
//   reports/eval-corpus/<run_id>/report.json    — structured rollup
//   reports/eval-corpus/<run_id>/report.md      — human-readable rollup
//
// CLI:
//   node scripts/eval-corpus/runner.mjs --n 5
//   node scripts/eval-corpus/runner.mjs --n 3 --cases C16-paired-doha-mina-doha
//   node scripts/eval-corpus/runner.mjs --unit-only
//
// Observation-only: the runner NEVER modifies live state beyond the same
// `resetLiveConversationState` the existing canaries call. Assertions in
// cases are ADVISORY — a failed assert is recorded in the report as a
// warning, not an abort. Only unit schema-validator failures are
// hard-fail (they indicate the phase A contract is broken in-repo).

import { mkdir, writeFile, appendFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";
import url from "node:url";

// Timeout contract for the reply-log wait. The default harness value is 45s,
// which turned out to be tight enough that a full corpus sweep would time
// out on ~half the turns purely because the LLM step ran long, not because
// the pipeline was broken. The runner then moved to the next run, which
// called `resetLiveConversationState` → `systemctl restart riders-delivery`
// → KILLED the LLM call that was still in flight → the ingress got stuck
// in the replay store → every subsequent boot replayed-and-killed it
// again. 120s matches `live-class16-canary.mjs` and gives the LLM enough
// headroom to complete even under stacked context.
if (!process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS) {
  process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS = "120000";
}

import {
  compactWhitespace,
  createRunContext,
  ensureLiveGatewayReady,
  fetchGatewayLogs,
  getLiveSmokeConfig,
  postTextTurn,
  resetLiveConversationState,
  sleep,
  waitForGatewayReplyLog,
} from "../live-riders-harness.mjs";

import { CASES, LIVE_CASES, UNIT_CASES } from "./cases.mjs";
import { runSchemaContractTests } from "./unit-schema-contract.mjs";

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { n: 5, cases: null, unitOnly: false, liveOnly: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--n") {
      args.n = Math.max(1, Number.parseInt(argv[++i] || "5", 10) || 5);
    } else if (a === "--cases") {
      args.cases = String(argv[++i] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else if (a === "--unit-only") {
      args.unitOnly = true;
    } else if (a === "--live-only") {
      args.liveOnly = true;
    } else if (a === "--help" || a === "-h") {
      console.log(
        "Usage: runner.mjs [--n 5] [--cases id1,id2] [--unit-only] [--live-only]",
      );
      process.exit(0);
    }
  }
  return args;
}

// ---------------------------------------------------------------------------
// Log-scrape helpers (scoped per-turn window)
// ---------------------------------------------------------------------------

// `fetchGatewayLogs` tails up to 20 matching lines per needle. Because the
// three signals we care about each land at most ~2-3 times per turn, a
// 20-line tail is enough headroom when we scope the journal window to a
// single turn's `acceptedAtMs - 5s`.
const DRIFT_NEEDLE = "[drift/get-price-bypass]";
const PROPOSER_EMIT_NEEDLE = "[structured-output/proposer]";
const PROPOSER_TOOL_NEEDLE = "[proposer/tool-call]";
const CLASS15_BYPASS_NEEDLE = "[class-15/bypass]";

function parseEmitFields(line, prefixMarker) {
  // Emits use `key=value` pairs separated by spaces, with quoted strings for
  // free-form text. We only need a tolerant kv-reader here.
  const idx = line.indexOf(prefixMarker);
  if (idx < 0) return null;
  const tail = line.slice(idx + prefixMarker.length).trim();
  const fields = {};
  const re = /([a-zA-Z0-9_.]+)=(\[[^\]]*\]|"[^"]*"|[^\s]+)/g;
  let m;
  while ((m = re.exec(tail)) !== null) {
    let val = m[2];
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
    fields[m[1]] = val;
  }
  return fields;
}

async function scrapeTurnEmits(config, run, acceptedAtMs) {
  // Small fetch window — 5s of slack before the accept + we'll sleep ~1.5s
  // after the outbound log arrives so the late `[drift/…]` + `[proposer/…]`
  // lines land in the journal.
  const since = acceptedAtMs - 5_000;
  const [driftLines, proposerEmitLines, proposerToolLines, class15Lines] =
    await Promise.all([
      fetchGatewayLogs(config, run, since, DRIFT_NEEDLE),
      fetchGatewayLogs(config, run, since, PROPOSER_EMIT_NEEDLE),
      fetchGatewayLogs(config, run, since, PROPOSER_TOOL_NEEDLE),
      fetchGatewayLogs(config, run, since, CLASS15_BYPASS_NEEDLE),
    ]);

  return {
    drift: (driftLines || [])
      .filter((l) => l.includes(DRIFT_NEEDLE))
      .map((l) => parseEmitFields(l, DRIFT_NEEDLE))
      .filter(Boolean),
    proposer_emit: (proposerEmitLines || [])
      .filter((l) => l.includes(PROPOSER_EMIT_NEEDLE))
      .map((l) => parseEmitFields(l, PROPOSER_EMIT_NEEDLE))
      .filter(Boolean),
    proposer_tool: (proposerToolLines || [])
      .filter((l) => l.includes(PROPOSER_TOOL_NEEDLE))
      .map((l) => parseEmitFields(l, PROPOSER_TOOL_NEEDLE))
      .filter(Boolean),
    class15_bypass: (class15Lines || []).filter((l) =>
      l.includes(CLASS15_BYPASS_NEEDLE),
    ).length,
  };
}

// ---------------------------------------------------------------------------
// Assertion evaluation (advisory — never throws)
// ---------------------------------------------------------------------------

function evaluateTurnAssertions(turnAssert, emits) {
  if (!turnAssert) return { warnings: [], passed: true };
  const warnings = [];

  const driftEmit = emits.drift[emits.drift.length - 1] || null;
  const proposerEmit = emits.proposer_emit[emits.proposer_emit.length - 1] || null;

  if (turnAssert.drift) {
    if (!driftEmit) {
      warnings.push("missing_drift_emit");
    } else {
      const d = turnAssert.drift;
      if (d.turn_kind && driftEmit.turn_kind !== d.turn_kind) {
        warnings.push(
          `drift.turn_kind_mismatch:expected=${d.turn_kind}:actual=${driftEmit.turn_kind}`,
        );
      }
      if (
        Array.isArray(d.turn_kind_expected) &&
        !d.turn_kind_expected.includes(driftEmit.turn_kind)
      ) {
        warnings.push(
          `drift.turn_kind_not_in_expected:expected=[${d.turn_kind_expected.join(",")}]:actual=${driftEmit.turn_kind}`,
        );
      }
      if (
        Array.isArray(d.outcome_expected) &&
        !d.outcome_expected.includes(driftEmit.outcome)
      ) {
        warnings.push(
          `drift.outcome_not_in_expected:expected=[${d.outcome_expected.join(",")}]:actual=${driftEmit.outcome}`,
        );
      }
    }
  }

  if (turnAssert.proposer) {
    if (!proposerEmit) {
      warnings.push("missing_proposer_emit");
    } else {
      const p = turnAssert.proposer;
      if (p.present === true && proposerEmit.present !== "true") {
        warnings.push(`proposer.not_present:actual=${proposerEmit.present}`);
      }
      if (p.schema_valid === true && proposerEmit.schema_valid !== "true") {
        warnings.push(
          `proposer.schema_invalid:actual=${proposerEmit.schema_valid}:errors=${proposerEmit.errors || "-"}`,
        );
      }
      if (
        Array.isArray(p.plan_vs_fire) &&
        !p.plan_vs_fire.includes(proposerEmit.plan_vs_fire)
      ) {
        warnings.push(
          `proposer.plan_vs_fire_unexpected:expected=[${p.plan_vs_fire.join(",")}]:actual=${proposerEmit.plan_vs_fire}`,
        );
      }
    }
  }

  return { warnings, passed: warnings.length === 0 };
}

// ---------------------------------------------------------------------------
// Per-case config resolution
// ---------------------------------------------------------------------------

// Build a per-case config by re-invoking `getLiveSmokeConfig` under a
// scoped env-var override for `RIDERS_LIVE_SMOKE_REPLY_TARGET`. The
// harness validates the target via `assertReplyTargetLooksLikeTestNumber`
// inside `getLiveSmokeConfig`, so if a case declares a bad number we
// fail fast with a clear error instead of silently writing to the
// corpus-level shared phone.
function resolveCaseConfig(baseConfig, replyTarget) {
  const prev = process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET;
  process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET = String(replyTarget);
  try {
    const scoped = getLiveSmokeConfig();
    // We keep the rest of `baseConfig` (host, tokens, timeouts, etc.)
    // and only swap in the per-case reply target + its derived sender
    // defaults. The harness today reads `replyTarget` off the config
    // and derives sender/recipient phones from env; since we're not
    // overriding those envs here, the shared defaults still apply,
    // which is fine for the corpus (we only need the reply target to
    // differ so Octopus opens a new conversation).
    return { ...baseConfig, replyTarget: scoped.replyTarget };
  } finally {
    if (prev === undefined) {
      delete process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET;
    } else {
      process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET = prev;
    }
  }
}

// ---------------------------------------------------------------------------
// Live-case runner
// ---------------------------------------------------------------------------

async function runLiveCase(baseConfig, caseDef, runIdx, log) {
  // Per-case conversation isolation — see `cases.mjs` comment. If the
  // case declares its own reply_target we resolve a config keyed to
  // that phone. Otherwise we inherit the corpus-level `baseConfig`,
  // which matches the env-var-driven default.
  const config = caseDef.reply_target
    ? resolveCaseConfig(baseConfig, caseDef.reply_target)
    : baseConfig;
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);

  const turnResults = [];
  for (let t = 0; t < caseDef.turns.length; t += 1) {
    const turn = caseDef.turns[t];
    const turnLabel = `${caseDef.id}/run${runIdx + 1}/turn${t + 1}`;
    log(`  [${turnLabel}] customer: ${turn.customer_text}`);

    let reply = null;
    let emits = null;
    let turnError = null;
    let acceptedAtMs = 0;
    try {
      const ack = await postTextTurn(config, run, turn.customer_text);
      acceptedAtMs = ack.acceptedAtMs;
      const outbound = await waitForGatewayReplyLog(
        config,
        run,
        acceptedAtMs,
        "outbound reply sent",
        turnLabel,
      );
      reply = outbound.reply || null;
      // Give journald a moment to flush the post-decision emits.
      await sleep(1_500);
      emits = await scrapeTurnEmits(config, run, acceptedAtMs);
    } catch (err) {
      turnError = err?.message || String(err);
      log(`  [${turnLabel}] ERROR ${turnError}`);
    }

    const assertionResult = emits
      ? evaluateTurnAssertions(turn.assert, emits)
      : { warnings: ["scrape_failed_or_no_emits"], passed: false };

    const replyText = compactWhitespace(reply?.text || "");
    if (replyText) log(`  [${turnLabel}] assistant: ${replyText.slice(0, 160)}`);
    if (emits) {
      const d = emits.drift[emits.drift.length - 1];
      const p = emits.proposer_emit[emits.proposer_emit.length - 1];
      log(
        `  [${turnLabel}] drift=${d ? `${d.turn_kind}/${d.outcome}` : "-"} ` +
          `proposer=${p ? `${p.present}/${p.schema_valid}/${p.plan_vs_fire}` : "-"} ` +
          `warnings=${assertionResult.warnings.length}`,
      );
    }

    turnResults.push({
      turn_idx: t,
      customer_text: turn.customer_text,
      reply_text: replyText,
      reply_author: reply?.author || null,
      accepted_at_ms: acceptedAtMs,
      emits: emits || {
        drift: [],
        proposer_emit: [],
        proposer_tool: [],
        class15_bypass: 0,
      },
      assertions: assertionResult,
      error: turnError,
    });

    if (turnError) break;
  }

  return {
    case_id: caseDef.id,
    kind: "live",
    class_ref: caseDef.class_ref,
    run_idx: runIdx,
    conversation_id: run.conversationId,
    run_id: run.runId,
    reply_target: run.replyTarget,
    turns: turnResults,
    case_pass: turnResults.every(
      (t) => !t.error && t.assertions.warnings.length === 0,
    ),
  };
}

// ---------------------------------------------------------------------------
// Unit case runner
// ---------------------------------------------------------------------------

async function runUnitCase(caseDef, runIdx, log) {
  if (caseDef.unit_run !== "schema_contract") {
    return {
      case_id: caseDef.id,
      kind: "unit",
      class_ref: caseDef.class_ref,
      run_idx: runIdx,
      error: `unknown unit_run:${caseDef.unit_run}`,
      case_pass: false,
    };
  }
  const contractResult = await runSchemaContractTests();
  log(
    `  [${caseDef.id}/run${runIdx + 1}] unit=${contractResult.passed ? "PASS" : "FAIL"} ` +
      `checks=${contractResult.checks.length} failures=${contractResult.failures.length}`,
  );
  return {
    case_id: caseDef.id,
    kind: "unit",
    class_ref: caseDef.class_ref,
    run_idx: runIdx,
    contract: contractResult,
    case_pass: contractResult.passed,
  };
}

// ---------------------------------------------------------------------------
// Aggregation
// ---------------------------------------------------------------------------

function aggregateLive(caseRuns) {
  const turns = caseRuns.flatMap((r) => r.turns || []);
  const driftEmits = turns
    .map((t) => t.emits.drift[t.emits.drift.length - 1])
    .filter(Boolean);
  const proposerEmits = turns
    .map((t) => t.emits.proposer_emit[t.emits.proposer_emit.length - 1])
    .filter(Boolean);

  const turnKindXOutcome = {};
  for (const d of driftEmits) {
    const k = `${d.turn_kind}/${d.outcome}`;
    turnKindXOutcome[k] = (turnKindXOutcome[k] || 0) + 1;
  }
  const planVsFire = {};
  for (const p of proposerEmits) {
    const k = p.plan_vs_fire || "-";
    planVsFire[k] = (planVsFire[k] || 0) + 1;
  }
  const presentCount = proposerEmits.filter((p) => p.present === "true").length;
  const schemaValidCount = proposerEmits.filter(
    (p) => p.schema_valid === "true",
  ).length;
  const getPriceFiredCount = driftEmits.filter(
    (d) => d.get_price_fired === "true",
  ).length;
  const bypassCount = driftEmits.filter(
    (d) => d.outcome === "turn1_bypass" || d.outcome === "post_clarify_bypass",
  ).length;

  return {
    total_turns: turns.length,
    total_drift_emits: driftEmits.length,
    total_proposer_emits: proposerEmits.length,
    turn_kind_x_outcome: turnKindXOutcome,
    plan_vs_fire: planVsFire,
    proposer_present_rate: proposerEmits.length
      ? presentCount / proposerEmits.length
      : 0,
    proposer_schema_valid_rate: presentCount
      ? schemaValidCount / presentCount
      : 0,
    get_price_fired_rate: driftEmits.length
      ? getPriceFiredCount / driftEmits.length
      : 0,
    bypass_rate: driftEmits.length ? bypassCount / driftEmits.length : 0,
    case_pass_rate: caseRuns.length
      ? caseRuns.filter((r) => r.case_pass).length / caseRuns.length
      : 0,
  };
}

function aggregateUnit(caseRuns) {
  const total = caseRuns.length;
  const passed = caseRuns.filter((r) => r.case_pass).length;
  return {
    total_runs: total,
    passed,
    failed: total - passed,
    pass_rate: total ? passed / total : 0,
  };
}

function buildReport(corpusRunId, allResults, selectedCases, args) {
  const caseGroups = {};
  for (const r of allResults) {
    if (!caseGroups[r.case_id])
      caseGroups[r.case_id] = {
        case_id: r.case_id,
        kind: r.kind,
        class_ref: r.class_ref,
        runs: [],
      };
    caseGroups[r.case_id].runs.push(r);
  }
  const perCase = Object.values(caseGroups).map((g) => ({
    ...g,
    aggregate:
      g.kind === "live" ? aggregateLive(g.runs) : aggregateUnit(g.runs),
  }));
  const corpusAggregate = {
    live: aggregateLive(
      perCase.filter((c) => c.kind === "live").flatMap((c) => c.runs),
    ),
    unit: aggregateUnit(
      perCase.filter((c) => c.kind === "unit").flatMap((c) => c.runs),
    ),
  };
  return {
    corpus_run_id: corpusRunId,
    generated_at: new Date().toISOString(),
    args,
    selected_case_ids: selectedCases.map((c) => c.id),
    cases: perCase,
    corpus_aggregate: corpusAggregate,
  };
}

function renderMarkdown(report) {
  const lines = [];
  lines.push(`# Eval corpus report — ${report.corpus_run_id}`);
  lines.push("");
  lines.push(`Generated: ${report.generated_at}`);
  lines.push(
    `Args: n=${report.args.n} cases=${report.args.cases?.join(",") || "(all)"} unit_only=${report.args.unitOnly} live_only=${report.args.liveOnly}`,
  );
  lines.push("");
  lines.push("## Corpus-level");
  const ca = report.corpus_aggregate;
  lines.push("");
  lines.push("### Live");
  lines.push(`- Total turns: ${ca.live.total_turns}`);
  lines.push(`- Drift emits: ${ca.live.total_drift_emits}`);
  lines.push(`- Proposer emits: ${ca.live.total_proposer_emits}`);
  lines.push(
    `- Proposer present rate: ${(ca.live.proposer_present_rate * 100).toFixed(1)}%`,
  );
  lines.push(
    `- Proposer schema-valid rate (of present): ${(ca.live.proposer_schema_valid_rate * 100).toFixed(1)}%`,
  );
  lines.push(
    `- get_price fired rate: ${(ca.live.get_price_fired_rate * 100).toFixed(1)}%`,
  );
  lines.push(`- Bypass rate: ${(ca.live.bypass_rate * 100).toFixed(1)}%`);
  lines.push(
    `- Case pass-rate (advisory): ${(ca.live.case_pass_rate * 100).toFixed(1)}%`,
  );
  lines.push("");
  lines.push("#### turn_kind × outcome");
  for (const [k, v] of Object.entries(ca.live.turn_kind_x_outcome).sort()) {
    lines.push(`- \`${k}\`: ${v}`);
  }
  lines.push("");
  lines.push("#### plan_vs_fire");
  for (const [k, v] of Object.entries(ca.live.plan_vs_fire).sort()) {
    lines.push(`- \`${k}\`: ${v}`);
  }
  lines.push("");
  lines.push("### Unit");
  lines.push(`- Runs: ${ca.unit.total_runs}`);
  lines.push(`- Passed: ${ca.unit.passed}`);
  lines.push(`- Failed: ${ca.unit.failed}`);
  lines.push(`- Pass rate: ${(ca.unit.pass_rate * 100).toFixed(1)}%`);
  lines.push("");

  lines.push("## Per-case");
  for (const c of report.cases) {
    lines.push("");
    lines.push(`### ${c.case_id} (${c.kind}, ${c.class_ref})`);
    if (c.kind === "live") {
      const ag = c.aggregate;
      lines.push(
        `- Runs: ${c.runs.length} | case pass-rate: ${(ag.case_pass_rate * 100).toFixed(1)}%`,
      );
      lines.push(
        `- proposer present/schema-valid: ${(ag.proposer_present_rate * 100).toFixed(1)}% / ${(ag.proposer_schema_valid_rate * 100).toFixed(1)}%`,
      );
      lines.push(
        `- get_price fired rate: ${(ag.get_price_fired_rate * 100).toFixed(1)}% | bypass rate: ${(ag.bypass_rate * 100).toFixed(1)}%`,
      );
      const outcomes = Object.entries(ag.turn_kind_x_outcome)
        .map(([k, v]) => `${k}=${v}`)
        .join(", ");
      lines.push(`- turn_kind × outcome: ${outcomes || "(none)"}`);
    } else {
      const ag = c.aggregate;
      lines.push(
        `- Runs: ${ag.total_runs} | passed: ${ag.passed} | failed: ${ag.failed}`,
      );
    }
  }
  return lines.join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let selected = CASES;
  if (args.cases && args.cases.length > 0) {
    selected = CASES.filter((c) => args.cases.includes(c.id));
  }
  if (args.unitOnly) selected = selected.filter((c) => c.kind === "unit");
  if (args.liveOnly) selected = selected.filter((c) => c.kind === "live");

  if (selected.length === 0) {
    console.error("[corpus] No cases selected. Check --cases filter.");
    process.exit(2);
  }

  const corpusRunId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`;
  const here = path.dirname(url.fileURLToPath(import.meta.url));
  const outDir = path.resolve(here, "../../reports/eval-corpus", corpusRunId);
  await mkdir(outDir, { recursive: true });
  const rawPath = path.join(outDir, "raw.jsonl");
  const reportJsonPath = path.join(outDir, "report.json");
  const reportMdPath = path.join(outDir, "report.md");

  const log = (msg) => console.log(msg);
  log(
    `[corpus] run_id=${corpusRunId} n=${args.n} cases=[${selected.map((c) => c.id).join(", ")}]`,
  );
  log(`[corpus] out=${outDir}`);

  let config = null;
  if (selected.some((c) => c.kind === "live")) {
    config = getLiveSmokeConfig();
    await ensureLiveGatewayReady(config);
  }

  const results = [];
  for (const caseDef of selected) {
    log(`\n[corpus] case=${caseDef.id} kind=${caseDef.kind}`);
    for (let i = 0; i < args.n; i += 1) {
      let res;
      try {
        if (caseDef.kind === "live") {
          res = await runLiveCase(config, caseDef, i, log);
        } else {
          res = await runUnitCase(caseDef, i, log);
        }
      } catch (err) {
        res = {
          case_id: caseDef.id,
          kind: caseDef.kind,
          class_ref: caseDef.class_ref,
          run_idx: i,
          error: err?.message || String(err),
          case_pass: false,
        };
        log(`  [${caseDef.id}/run${i + 1}] RUNNER ERROR: ${res.error}`);
      }
      results.push(res);
      try {
        await appendFile(rawPath, JSON.stringify(res) + "\n");
      } catch {}
    }
  }

  const report = buildReport(corpusRunId, results, selected, args);
  await writeFile(reportJsonPath, JSON.stringify(report, null, 2));
  await writeFile(reportMdPath, renderMarkdown(report));

  log(`\n[corpus] DONE`);
  log(`[corpus] raw:      ${rawPath}`);
  log(`[corpus] json:     ${reportJsonPath}`);
  log(`[corpus] markdown: ${reportMdPath}`);

  // Exit code policy:
  //   - 0 if every unit case passed (live cases are advisory).
  //   - 1 if any unit case failed (indicates broken in-repo contract).
  const unitFailed = results.some(
    (r) => r.kind === "unit" && r.case_pass === false,
  );
  if (unitFailed) {
    log(`[corpus] UNIT FAILURE — exit 1`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(`[corpus] FATAL: ${err?.message || err}`);
  if (err?.stack) console.error(err.stack);
  process.exit(2);
});
