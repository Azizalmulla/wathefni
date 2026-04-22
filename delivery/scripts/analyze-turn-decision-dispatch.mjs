#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Relocation 2 (A4 → layer) dispatch-divergence analyzer (2026-04-22).
//
// Parses the `[turn-decision/trace]` log stream emitted by the unified
// turn-decision layer and — optionally — joins it with the pre-existing
// `[structured-output/proposer]` stream on `turn_id`. Produces a
// human-readable report the user can review during the Reloc 2 bake
// window without having to eyeball raw JSON payloads.
//
// What the report answers
//
//   * AGREEMENT DISTRIBUTION — how often the layer's fresh dispatch
//     decision matches legacy A4, bucketed across the four
//     dispatch_agreement values. A stable `agree` rate is what we want
//     before considering an A4 flip.
//
//   * POLICY RULE FREQUENCY — which `layer.*` rule ids actually fire
//     on live traffic. Rules that never fire are either unreachable
//     or gated behind rare input shapes; rules that dominate are the
//     ones whose correctness matters most.
//
//   * OBSERVED × DERIVED MATRIX — the full cross-tab of observed
//     reply_source and layer derived_source. Off-diagonal cells are
//     divergences; the report flags the top-N cells.
//
//   * DIVERGENCE × TI_KIND — for each turn_intent kind, how often the
//     layer disagrees with legacy and in which direction. Lets us see
//     whether the ack/clarifying passthrough rules are the sole
//     disagreement sources or whether other ti_kinds are divergent too.
//
//   * DIVERGENCE × A1 INTENT — same slice by observed.reason. Helps
//     separate "A4 itself is disagreeing on healthy `allow` turns"
//     from "A4 disagreeing inside a specific A1 substitution branch".
//
//   * CLASSIFIER-NOISE HEURISTICS — when joined with the proposer
//     stream, the report flags turns whose `ti_kind` looks
//     inconsistent with the proposer's structural signals
//     (`turn_kind`, `pricing_action`, `ti_addressed_fields`). These
//     are the divergences we should DISCOUNT from policy evaluation
//     because they are classifier errors, not A4 policy errors.
//
// Usage
//
//   node scripts/analyze-turn-decision-dispatch.mjs path/to/log.txt
//
//   # streaming from journalctl
//   journalctl -u riders-delivery --since "2 hours ago" --no-pager \
//     | node scripts/analyze-turn-decision-dispatch.mjs
//
//   # JSON for tooling / CI
//   node scripts/analyze-turn-decision-dispatch.mjs --json log.txt
//
//   # restrict to a single conversation
//   node scripts/analyze-turn-decision-dispatch.mjs --conv=19534 log.txt
//
//   # cap per-bucket samples in the divergence detail list
//   node scripts/analyze-turn-decision-dispatch.mjs --top=10 log.txt
//
//   # internal self-test (synthetic corpus + asserted metrics)
//   node scripts/analyze-turn-decision-dispatch.mjs --selftest
//
// Pure offline tool. No network, no deploy impact, no runtime behaviour
// change. Safe to run against any journal dump.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import readline from "node:readline";

const TD_PREFIX = "[turn-decision/trace]";
const TD_EMIT_FAILED = "[turn-decision/trace] emit_failed";
const PROPOSER_PREFIX = "[structured-output/proposer]";

const REPLY_SOURCES = [
  "server_rendered_directive",
  "server_ack_plus_directive",
  "server_substitute_text",
  "server_recovery_template",
  "deferred_confirm_prompt",
  "llm_authored",
];

const DISPATCH_AGREEMENT_BUCKETS = [
  "agree",
  "disagree_layer_passthrough",
  "disagree_layer_substitute",
  "disagree_other",
];

const TURN_INTENT_KINDS = [
  "answered_full",
  "answered_partial",
  "answered_unasked",
  "corrected_prior",
  "clarifying_question",
  "acknowledgement",
  "refused_or_stuck",
  "unclear",
];

// ---------------------------------------------------------------------------
// Argv parsing.
// ---------------------------------------------------------------------------

const argv = process.argv.slice(2);
let asJson = false;
let selftest = false;
let topN = 5;
let convFilter = null;
const filePaths = [];
for (const a of argv) {
  if (a === "--json") asJson = true;
  else if (a === "--selftest") selftest = true;
  else if (a.startsWith("--top=")) topN = Number.parseInt(a.slice(6), 10) || 5;
  else if (a.startsWith("--conv=")) convFilter = a.slice(7);
  else if (a.startsWith("-")) {
    console.error(`unknown flag: ${a}`);
    process.exit(2);
  } else filePaths.push(a);
}

// ---------------------------------------------------------------------------
// Line parsers.
// ---------------------------------------------------------------------------

function parseKvTokens(line) {
  const out = {};
  const eq = line.indexOf("=");
  if (eq === -1) return out;
  let cursor = line.lastIndexOf(" ", eq);
  if (cursor < 0) cursor = 0;
  for (let i = cursor; i < line.length; ) {
    while (i < line.length && line[i] === " ") i++;
    const keyStart = i;
    while (i < line.length && line[i] !== "=" && line[i] !== " ") i++;
    if (i >= line.length || line[i] !== "=") break;
    const key = line.slice(keyStart, i);
    i++;
    let valEnd;
    if (line[i] === "[") {
      const close = line.indexOf("]", i);
      valEnd = close === -1 ? line.length : close + 1;
    } else if (line[i] === "{") {
      let depth = 0;
      let j = i;
      while (j < line.length) {
        if (line[j] === "{") depth++;
        else if (line[j] === "}") {
          depth--;
          if (depth === 0) {
            j++;
            break;
          }
        }
        j++;
      }
      valEnd = j;
    } else if (key === "payload") {
      // payload value is JSON that runs to end-of-line.
      valEnd = line.length;
    } else {
      valEnd = line.indexOf(" ", i);
      if (valEnd === -1) valEnd = line.length;
    }
    const val = line.slice(i, valEnd);
    out[key] = val;
    i = valEnd;
  }
  return out;
}

function parseTurnDecisionTrace(line) {
  if (!line.includes(TD_PREFIX)) return null;
  if (line.includes(TD_EMIT_FAILED)) return { emit_failed: true };
  const kv = parseKvTokens(line);
  const payloadIdx = line.indexOf("payload=");
  let payload = null;
  if (payloadIdx !== -1) {
    const raw = line.slice(payloadIdx + "payload=".length).trim();
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = null;
    }
  }
  if (!payload) return null;
  return {
    conversation: kv.conversation || payload.decision_id?.split(":")[0] || "-",
    turn_id: kv.turn_id || "-",
    language: kv.lang || "-",
    reply_source: payload.reply_source || "-",
    layer_source: payload.layer?.derived_source || null,
    dispatch_agreement: payload.layer?.dispatch_agreement || null,
    derived_reason: payload.layer?.derived_reason || null,
    derived_policy_rule: payload.layer?.derived_policy_rule || null,
    observed_reason: payload.observed?.reason || "-",
    observed_decision: payload.observed?.decision || "-",
    observed_reply_author: payload.observed?.reply_author || "-",
    directive: payload.directive || null,
    ti_kind: payload.semantic_signals?.ti_kind || null,
    ac_kind: payload.semantic_signals?.ac_kind || null,
    po_kind: payload.semantic_signals?.po_kind || null,
    stage_start: payload.input?.stage_at_turn_start || null,
    stage_end: payload.input?.stage_at_turn_end || null,
    has_active_quoted_route: !!payload.input?.has_active_quoted_route,
    drained_op_count: payload.input?.drained_op_count ?? 0,
    reply_text_chars: payload.input?.reply_text_chars ?? 0,
    schema_version: payload.input?.schema_version || "-",
    proposer_present: !!payload.input?.proposer_present,
    proposer_valid: !!payload.input?.proposer_valid,
    policy_hits: payload.policy_hits || [],
  };
}

function parseProposerEmit(line) {
  if (!line.includes(PROPOSER_PREFIX)) return null;
  const kv = parseKvTokens(line);
  if (!kv.turn_id) return null;
  return {
    conversation: kv.conversation || "-",
    turn_id: kv.turn_id,
    stage: kv.stage || null,
    requested_slot: kv.requested_slot || null,
    schema_valid: kv.schema_valid === "true",
    schema_version: kv.schema_version || null,
    turn_kind: kv.turn_kind || null,
    pricing_action: kv.pricing_action || null,
    ti_kind: kv.ti_kind === "-" ? null : kv.ti_kind || null,
    ti_confidence: kv.ti_confidence === "-" ? null : kv.ti_confidence || null,
    ti_addressed_fields_count:
      Number.parseInt(kv.ti_addressed_fields_count || "0", 10) || 0,
    ti_addressed_fields:
      kv.ti_addressed_fields && kv.ti_addressed_fields.startsWith("[")
        ? kv.ti_addressed_fields
            .slice(1, -1)
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
    ti_classification: kv.ti_classification || null,
    ac_kind: kv.ac_kind === "-" ? null : kv.ac_kind || null,
    po_kind: kv.po_kind === "-" ? null : kv.po_kind || null,
    duplicate_count: Number.parseInt(kv.duplicate_count || "1", 10) || 1,
  };
}

// ---------------------------------------------------------------------------
// Classifier-noise heuristics. Each heuristic flags a turn whose
// proposer-side signals look internally inconsistent. A flagged turn's
// layer divergence is likely driven by classifier error, not policy
// error — we DISCOUNT those from A4 flip readiness, not dismiss them.
//
// Heuristic ids are stable strings so follow-on analysis and design
// discussion can refer to a specific rule by name.
// ---------------------------------------------------------------------------

function classifierNoiseFlags(trace, proposer) {
  if (!proposer) return [];
  const flags = [];

  // F1. ti=clarifying_question but the turn is clearly a fresh route
  //     request — pricing_action=call_get_price or
  //     turn_kind=initial_route. The 2026-04-22 Surra→Salwa turn from
  //     the baseline sample hit this.
  if (
    trace.ti_kind === "clarifying_question" &&
    (proposer.pricing_action === "call_get_price" ||
      proposer.turn_kind === "initial_route")
  ) {
    flags.push("noise.clarifying_on_fresh_route_shape");
  }

  // F2. ti=clarifying_question with the informational combo that
  //     suggests a route-switch-mistaken-for-informational. Fires
  //     when stage_at_turn_start is quoted AND ti_addressed_fields
  //     contains "option" but pricing_action=informational_only
  //     AND the reply's substitute directive is a sender/address
  //     ask — the classic "customer asked for a new route price,
  //     bot pushed to collection phase" shape.
  if (
    trace.ti_kind === "clarifying_question" &&
    proposer.pricing_action === "informational_only" &&
    trace.stage_start === "quoted" &&
    proposer.ti_addressed_fields.includes("option") &&
    trace.directive &&
    /^(ASK_SENDER|ASK_RECIPIENT|ASK_PICKUP|ASK_DELIVERY)/.test(
      trace.directive,
    )
  ) {
    flags.push("noise.clarifying_option_but_collection_directive");
  }

  // F3. ti=acknowledgement but the patch addressed ≥2 fields — a
  //     real acknowledgement doesn't carry data. Large
  //     ti_addressed_fields on an ack classification is suspect.
  if (
    trace.ti_kind === "acknowledgement" &&
    proposer.ti_addressed_fields_count >= 2
  ) {
    flags.push("noise.acknowledgement_with_multi_field_patch");
  }

  // F4. ti_confidence=low — the layer's ack/clarifying passthrough
  //     rules already guard against low-confidence classifications,
  //     but older trace lines may still carry low-conf signals if a
  //     rule was loosened. Flag explicitly so it's not double-
  //     counted as policy divergence.
  if (proposer.ti_confidence === "low") {
    flags.push("noise.low_confidence_ti");
  }

  // F5. proposer classified the turn but the turn's apparent shape
  //     (inferred from stage + drained ops + directive) implies a
  //     different kind. Conservative: only flag when the proposer
  //     emit says `ti_classification=missing` yet the trace has a
  //     non-null ti_kind (cache/shadow mismatch). Rare but worth
  //     knowing.
  if (
    proposer.ti_classification === "missing" &&
    trace.ti_kind &&
    trace.ti_kind !== "-"
  ) {
    flags.push("noise.ti_missing_classification_with_kind");
  }

  return flags;
}

// ---------------------------------------------------------------------------
// Aggregator.
// ---------------------------------------------------------------------------

function emptyReport() {
  return {
    totals: {
      traces_parsed: 0,
      emit_failed: 0,
      payload_parse_failed: 0,
      with_layer_decision: 0,
      without_layer_decision: 0,
      matched_with_proposer: 0,
    },
    agreement: Object.fromEntries(
      DISPATCH_AGREEMENT_BUCKETS.map((k) => [k, 0]),
    ),
    policy_rules: new Map(),
    observed_vs_derived: new Map(),
    divergence_by_ti_kind: new Map(),
    divergence_by_observed_reason: new Map(),
    noise_flag_counts: new Map(),
    noise_flagged_divergences: 0,
    clean_divergences: 0,
    divergence_detail: [],
    conversations: new Set(),
    turn_ids: new Set(),
  };
}

function incMap(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function incMapOfMap(map, key1, key2) {
  if (!map.has(key1)) map.set(key1, new Map());
  incMap(map.get(key1), key2);
}

function aggregate(traces, proposersByTurn, report) {
  for (const trace of traces) {
    if (trace.emit_failed) {
      report.totals.emit_failed++;
      continue;
    }
    if (convFilter && trace.conversation !== convFilter) continue;
    report.totals.traces_parsed++;
    report.conversations.add(trace.conversation);
    report.turn_ids.add(trace.turn_id);

    if (!trace.layer_source || !trace.dispatch_agreement) {
      report.totals.without_layer_decision++;
      continue;
    }
    report.totals.with_layer_decision++;

    const proposer = proposersByTurn.get(trace.turn_id) || null;
    if (proposer) report.totals.matched_with_proposer++;

    report.agreement[trace.dispatch_agreement] =
      (report.agreement[trace.dispatch_agreement] || 0) + 1;

    if (trace.derived_policy_rule) {
      incMap(report.policy_rules, trace.derived_policy_rule);
    }

    incMapOfMap(report.observed_vs_derived, trace.reply_source, trace.layer_source);

    const tiBucket = trace.ti_kind || "-";
    incMapOfMap(report.divergence_by_ti_kind, tiBucket, trace.dispatch_agreement);
    incMapOfMap(
      report.divergence_by_observed_reason,
      trace.observed_reason,
      trace.dispatch_agreement,
    );

    if (trace.dispatch_agreement !== "agree") {
      const flags = classifierNoiseFlags(trace, proposer);
      for (const f of flags) incMap(report.noise_flag_counts, f);
      const hasNoise = flags.length > 0;
      if (hasNoise) report.noise_flagged_divergences++;
      else report.clean_divergences++;
      report.divergence_detail.push({
        conversation: trace.conversation,
        turn_id: trace.turn_id,
        dispatch_agreement: trace.dispatch_agreement,
        observed_reply_source: trace.reply_source,
        layer_source: trace.layer_source,
        observed_reason: trace.observed_reason,
        derived_policy_rule: trace.derived_policy_rule,
        directive: trace.directive,
        ti_kind: trace.ti_kind,
        ac_kind: trace.ac_kind,
        stage_start: trace.stage_start,
        stage_end: trace.stage_end,
        reply_text_chars: trace.reply_text_chars,
        noise_flags: flags,
        proposer_turn_kind: proposer?.turn_kind || null,
        proposer_pricing_action: proposer?.pricing_action || null,
        proposer_ti_confidence: proposer?.ti_confidence || null,
        proposer_ti_addressed_fields: proposer?.ti_addressed_fields || [],
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Rendering.
// ---------------------------------------------------------------------------

function pct(n, total) {
  if (!total) return "  0.0%";
  return `${((100 * n) / total).toFixed(1).padStart(5, " ")}%`;
}

function sortedEntries(map, limit = Infinity) {
  const arr = [...map.entries()].sort((a, b) => b[1] - a[1]);
  return limit === Infinity ? arr : arr.slice(0, limit);
}

function renderReport(report) {
  const out = [];
  const totalDecisions = report.totals.with_layer_decision;

  out.push("=".repeat(72));
  out.push(" Turn-decision dispatch divergence report (Relocation 2 bake)");
  out.push("=".repeat(72));
  out.push("");
  out.push(
    ` Conversations ......... ${report.conversations.size}`,
  );
  out.push(
    ` Turns (traces) ........ ${report.totals.traces_parsed} ` +
      `(${report.totals.emit_failed} emit_failed, ` +
      `${report.totals.without_layer_decision} without layer decision)`,
  );
  out.push(
    ` With layer decision ... ${report.totals.with_layer_decision} ` +
      `(${report.totals.matched_with_proposer} joined with proposer emit)`,
  );
  out.push("");

  out.push("-- Agreement distribution ".padEnd(72, "-"));
  for (const k of DISPATCH_AGREEMENT_BUCKETS) {
    const n = report.agreement[k] || 0;
    out.push(`   ${k.padEnd(30)} ${String(n).padStart(5)}  ${pct(n, totalDecisions)}`);
  }
  out.push("");

  out.push("-- Policy rule frequency ".padEnd(72, "-"));
  for (const [rule, n] of sortedEntries(report.policy_rules)) {
    out.push(`   ${rule.padEnd(55)} ${String(n).padStart(5)}  ${pct(n, totalDecisions)}`);
  }
  out.push("");

  out.push("-- Observed × derived reply_source ".padEnd(72, "-"));
  const obsKeys = [...report.observed_vs_derived.keys()].sort();
  for (const obs of obsKeys) {
    const cell = report.observed_vs_derived.get(obs);
    const parts = [...cell.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([d, n]) => `${d}=${n}`)
      .join(", ");
    out.push(`   ${obs.padEnd(32)} → ${parts}`);
  }
  out.push("");

  out.push("-- Divergence by ti_kind ".padEnd(72, "-"));
  const tiKeys = [...report.divergence_by_ti_kind.keys()].sort();
  for (const ti of tiKeys) {
    const cell = report.divergence_by_ti_kind.get(ti);
    const total = [...cell.values()].reduce((a, b) => a + b, 0);
    const diverge = total - (cell.get("agree") || 0);
    const parts = [...cell.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => `${k}=${n}`)
      .join(", ");
    out.push(
      `   ti=${(ti || "-").padEnd(22)} total=${String(total).padStart(3)} ` +
        `diverge=${String(diverge).padStart(3)}  ${parts}`,
    );
  }
  out.push("");

  out.push("-- Divergence by observed reason (A1 intent when replace_*) ".padEnd(72, "-"));
  const reasonKeys = [...report.divergence_by_observed_reason.keys()].sort();
  for (const r of reasonKeys) {
    const cell = report.divergence_by_observed_reason.get(r);
    const total = [...cell.values()].reduce((a, b) => a + b, 0);
    const diverge = total - (cell.get("agree") || 0);
    const parts = [...cell.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => `${k}=${n}`)
      .join(", ");
    out.push(
      `   ${r.padEnd(44)} total=${String(total).padStart(3)} ` +
        `diverge=${String(diverge).padStart(3)}  ${parts}`,
    );
  }
  out.push("");

  out.push("-- Classifier-noise heuristics ".padEnd(72, "-"));
  const totalDiv = report.noise_flagged_divergences + report.clean_divergences;
  out.push(
    `   noise-flagged divergences ........ ${String(
      report.noise_flagged_divergences,
    ).padStart(3)}  ${pct(report.noise_flagged_divergences, totalDiv)}`,
  );
  out.push(
    `   clean (policy-only) divergences .. ${String(
      report.clean_divergences,
    ).padStart(3)}  ${pct(report.clean_divergences, totalDiv)}`,
  );
  if (report.noise_flag_counts.size > 0) {
    out.push("");
    out.push("   flag frequency:");
    for (const [flag, n] of sortedEntries(report.noise_flag_counts)) {
      out.push(`     ${flag.padEnd(55)} ${String(n).padStart(3)}`);
    }
  }
  out.push("");

  out.push("-- Divergence detail (top " + topN + " per bucket) ".padEnd(72, "-"));
  const byAgreement = new Map();
  for (const d of report.divergence_detail) {
    if (!byAgreement.has(d.dispatch_agreement))
      byAgreement.set(d.dispatch_agreement, []);
    byAgreement.get(d.dispatch_agreement).push(d);
  }
  for (const bucket of [
    "disagree_layer_passthrough",
    "disagree_layer_substitute",
    "disagree_other",
  ]) {
    const arr = byAgreement.get(bucket) || [];
    out.push(`   [${bucket}] ${arr.length} total`);
    for (const d of arr.slice(0, topN)) {
      const noise = d.noise_flags.length
        ? ` NOISE=[${d.noise_flags.join(",")}]`
        : "";
      out.push(
        `     · conv=${d.conversation} turn=${d.turn_id} ` +
          `observed=${d.observed_reply_source}/${d.observed_reason} → layer=${d.layer_source} ` +
          `(rule=${d.derived_policy_rule}) ti=${d.ti_kind || "-"} ` +
          `stage=${d.stage_start || "-"}→${d.stage_end || "-"} ` +
          `dir=${d.directive || "-"}${noise}`,
      );
    }
  }
  out.push("");

  out.push("=".repeat(72));
  out.push(
    ` Readiness heuristic — NOT a flip signal on its own`,
  );
  out.push("=".repeat(72));
  const agreeRate = totalDecisions
    ? (report.agreement.agree || 0) / totalDecisions
    : 0;
  const cleanDivRate = totalDiv ? report.clean_divergences / totalDiv : 0;
  out.push(
    `   agreement rate ...................... ${(agreeRate * 100).toFixed(1)}%`,
  );
  out.push(
    `   clean divergence share .............. ${(cleanDivRate * 100).toFixed(1)}%`,
  );
  out.push(
    `   noise-flagged divergence share ...... ${(100 - cleanDivRate * 100).toFixed(1)}%`,
  );
  out.push("");
  out.push(
    `   A4 flip should only be considered when BOTH:`,
  );
  out.push(
    `     (a) clean divergences are dominated by intentional policy rules`,
  );
  out.push(
    `         (ack_passthrough, clarifying_passthrough, etc.) — not by`,
  );
  out.push(
    `         new unexpected combinations, AND`,
  );
  out.push(
    `     (b) noise-flagged share is low enough that classifier error`,
  );
  out.push(
    `         isn't driving most of the disagreements.`,
  );
  out.push("");

  return out.join("\n");
}

// ---------------------------------------------------------------------------
// IO — read from files or stdin, parse, aggregate, render.
// ---------------------------------------------------------------------------

async function ingest(stream, traces, proposerEmits) {
  const rl = readline.createInterface({ input: stream });
  for await (const line of rl) {
    if (!line) continue;
    if (line.includes(TD_PREFIX)) {
      const parsed = parseTurnDecisionTrace(line);
      if (parsed) traces.push(parsed);
      else {
        // keep the count of raw trace lines we failed to parse
        // separately from emit_failed
      }
    } else if (line.includes(PROPOSER_PREFIX)) {
      const parsed = parseProposerEmit(line);
      if (parsed) proposerEmits.push(parsed);
    }
  }
}

async function ingestAll() {
  const traces = [];
  const proposerEmits = [];
  if (filePaths.length === 0) {
    await ingest(process.stdin, traces, proposerEmits);
  } else {
    for (const p of filePaths) {
      const stream = fs.createReadStream(p, { encoding: "utf8" });
      await ingest(stream, traces, proposerEmits);
    }
  }
  return { traces, proposerEmits };
}

function indexProposersByTurn(proposerEmits) {
  const map = new Map();
  for (const p of proposerEmits) {
    if (!p.turn_id) continue;
    if (!map.has(p.turn_id)) map.set(p.turn_id, p);
  }
  return map;
}

function reportToJson(report) {
  return {
    totals: report.totals,
    conversations: report.conversations.size,
    turns: report.turn_ids.size,
    agreement: report.agreement,
    policy_rules: Object.fromEntries(sortedEntries(report.policy_rules)),
    observed_vs_derived: Object.fromEntries(
      [...report.observed_vs_derived.entries()].map(([k, m]) => [
        k,
        Object.fromEntries(sortedEntries(m)),
      ]),
    ),
    divergence_by_ti_kind: Object.fromEntries(
      [...report.divergence_by_ti_kind.entries()].map(([k, m]) => [
        k,
        Object.fromEntries(sortedEntries(m)),
      ]),
    ),
    divergence_by_observed_reason: Object.fromEntries(
      [...report.divergence_by_observed_reason.entries()].map(([k, m]) => [
        k,
        Object.fromEntries(sortedEntries(m)),
      ]),
    ),
    noise_flag_counts: Object.fromEntries(sortedEntries(report.noise_flag_counts)),
    noise_flagged_divergences: report.noise_flagged_divergences,
    clean_divergences: report.clean_divergences,
    divergence_detail: report.divergence_detail,
  };
}

// ---------------------------------------------------------------------------
// Self-test.
//
// Runs a synthetic corpus through the full pipeline and asserts the
// aggregated report shape. Non-zero exit on any assertion failure.
// ---------------------------------------------------------------------------

function selfTest() {
  const fails = [];
  const assert = (cond, msg) => {
    if (!cond) fails.push(msg);
  };

  // Construct a synthetic set of trace lines covering the cases we
  // care about during the bake window.
  function mkTrace(overrides) {
    const base = {
      conversation: "conv-1",
      turn_id: `turn-${overrides.seq}`,
      language: "en",
      reply_source: "llm_authored",
      layer: {
        derived_source: "llm_authored",
        derived_reason: "authority_allow",
        derived_policy_rule: "layer.authority_allow",
        dispatch_agreement: "agree",
      },
      directive: null,
      ac_kind: null,
      po_kind: null,
      ti_kind: null,
      observed: {
        reason: "allow",
        decision: "allow",
        reply_author: "llm",
      },
      input: {
        stage_at_turn_start: "idle",
        stage_at_turn_end: "quoted",
        has_active_quoted_route: true,
        drained_op_count: 2,
        reply_text_chars: 60,
        schema_version: "1.2",
        proposer_present: true,
        proposer_valid: true,
      },
      op_plan: [],
      transitions: { marked_summary_shown: false },
      semantic_signals: { ti_kind: null, ac_kind: null, po_kind: null },
      policy_hits: [],
      ...overrides.payload,
    };
    base.semantic_signals = {
      ti_kind: overrides.ti_kind ?? null,
      ac_kind: null,
      po_kind: null,
    };
    base.observed.reason = overrides.observed_reason || "allow";
    base.reply_source = overrides.reply_source || "llm_authored";
    base.directive = overrides.directive ?? null;
    base.layer = overrides.layer || base.layer;
    base.input.stage_at_turn_start = overrides.stage_start || "idle";
    return (
      `Apr 22 21:00:${String(overrides.seq).padStart(2, "0")} host openclaw[1]: ` +
      `[plugins] [turn-decision/trace] conversation=${base.conversation} ` +
      `turn_id=${base.turn_id} lang=en ` +
      `reply_source=${base.reply_source} ` +
      `layer_source=${base.layer.derived_source} ` +
      `dispatch_agreement=${base.layer.dispatch_agreement} ` +
      `observed_reason=${base.observed.reason} ` +
      `ti=${base.semantic_signals.ti_kind || "-"} ` +
      `ac=- po=- payload=${JSON.stringify(base)}`
    );
  }

  function mkProposer(turn_id, fields = {}) {
    const f = {
      conversation: "conv-1",
      stage: "quoted",
      requested_slot: "-",
      present: "true",
      schema_valid: "true",
      schema_version: "1.2",
      turn_kind: fields.turn_kind || "booking_detail_collection",
      pricing_action: fields.pricing_action || "continue_existing_quote",
      planned_tool_calls: "[]",
      fired_tool_ops: "[]",
      get_price_fired: "false",
      plan_vs_fire: "n/a",
      ac_stage: "false",
      ac_kind: "-",
      ac_classification: "n/a",
      ti_stage: "true",
      ti_kind: fields.ti_kind || "-",
      ti_confidence: fields.ti_confidence || "-",
      ti_addressed_fields_count: String(fields.ti_addressed_fields_count ?? 0),
      ti_addressed_fields: `[${(fields.ti_addressed_fields || []).join(",")}]`,
      ti_classification: fields.ti_classification || "n/a",
      po_stage: "false",
      po_kind: "-",
      po_classification: "n/a",
      duplicate_count: "1",
      turn_id,
      errors: "-",
    };
    return (
      `Apr 22 21:00:00 host openclaw[1]: [plugins] [structured-output/proposer] ` +
      Object.entries(f)
        .map(([k, v]) => `${k}=${v}`)
        .join(" ")
    );
  }

  const lines = [
    // Case A: clean agree.
    mkTrace({
      seq: 1,
      observed_reason: "allow",
      reply_source: "llm_authored",
      ti_kind: null,
      layer: {
        derived_source: "llm_authored",
        derived_reason: "authority_allow",
        derived_policy_rule: "layer.authority_allow",
        dispatch_agreement: "agree",
      },
    }),
    // Case B: A1 clarify substitute, agree.
    mkTrace({
      seq: 2,
      observed_reason: "replace_clarify_option_before_proceed",
      reply_source: "server_substitute_text",
      ti_kind: "clarifying_question",
      layer: {
        derived_source: "server_substitute_text",
        derived_reason: "replace_clarify_option_before_proceed",
        derived_policy_rule:
          "layer.a1_substitute.replace_clarify_option_before_proceed",
        dispatch_agreement: "agree",
      },
    }),
    // Case C: ack passthrough divergence.
    mkTrace({
      seq: 3,
      observed_reason: "replace_directive_ask",
      reply_source: "server_rendered_directive",
      ti_kind: "acknowledgement",
      directive: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      stage_start: "quoted",
      layer: {
        derived_source: "llm_authored",
        derived_reason: "a1_directive_ask_ack_passthrough",
        derived_policy_rule: "layer.a1_directive_ask.ack_passthrough",
        dispatch_agreement: "disagree_layer_passthrough",
      },
    }),
    // Case D: clarifying passthrough divergence, classifier noise
    //         (fresh route shape — pricing_action=call_get_price).
    mkTrace({
      seq: 4,
      observed_reason: "replace_directive_ask",
      reply_source: "server_rendered_directive",
      ti_kind: "clarifying_question",
      directive: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      stage_start: "quoted",
      layer: {
        derived_source: "llm_authored",
        derived_reason: "a1_directive_ask_clarifying_passthrough",
        derived_policy_rule:
          "layer.a1_directive_ask.clarifying_passthrough",
        dispatch_agreement: "disagree_layer_passthrough",
      },
    }),
    mkProposer("turn-4", {
      turn_kind: "informational",
      pricing_action: "call_get_price",
      ti_kind: "clarifying_question",
      ti_confidence: "high",
      ti_classification: "present",
      ti_addressed_fields: ["option"],
      ti_addressed_fields_count: 1,
    }),
    // Case E: clarifying passthrough divergence, clean (no noise signal).
    mkTrace({
      seq: 5,
      observed_reason: "replace_directive_ask",
      reply_source: "server_rendered_directive",
      ti_kind: "clarifying_question",
      directive: "ASK_PICKUP_AREA",
      stage_start: "collecting_booking_details",
      layer: {
        derived_source: "llm_authored",
        derived_reason: "a1_directive_ask_clarifying_passthrough",
        derived_policy_rule:
          "layer.a1_directive_ask.clarifying_passthrough",
        dispatch_agreement: "disagree_layer_passthrough",
      },
    }),
    mkProposer("turn-5", {
      turn_kind: "informational",
      pricing_action: "informational_only",
      ti_kind: "clarifying_question",
      ti_confidence: "high",
      ti_classification: "present",
      ti_addressed_fields: [],
      ti_addressed_fields_count: 0,
    }),
  ];

  const traces = [];
  const proposerEmits = [];
  for (const line of lines) {
    if (line.includes(TD_PREFIX)) {
      const t = parseTurnDecisionTrace(line);
      if (t) traces.push(t);
    } else if (line.includes(PROPOSER_PREFIX)) {
      const p = parseProposerEmit(line);
      if (p) proposerEmits.push(p);
    }
  }

  assert(
    traces.length === 5,
    `selftest: expected 5 parsed traces, got ${traces.length}`,
  );
  assert(
    proposerEmits.length === 2,
    `selftest: expected 2 parsed proposer emits, got ${proposerEmits.length}`,
  );

  const proposersByTurn = indexProposersByTurn(proposerEmits);
  const report = emptyReport();
  aggregate(traces, proposersByTurn, report);

  assert(
    report.totals.with_layer_decision === 5,
    `selftest: with_layer_decision=${report.totals.with_layer_decision}, want 5`,
  );
  assert(
    report.agreement.agree === 2,
    `selftest: agree bucket=${report.agreement.agree}, want 2`,
  );
  assert(
    report.agreement.disagree_layer_passthrough === 3,
    `selftest: disagree_layer_passthrough=${report.agreement.disagree_layer_passthrough}, want 3`,
  );
  assert(
    (report.policy_rules.get("layer.a1_directive_ask.ack_passthrough") || 0) ===
      1,
    `selftest: ack_passthrough rule count mismatch`,
  );
  assert(
    (report.policy_rules.get("layer.a1_directive_ask.clarifying_passthrough") ||
      0) === 2,
    `selftest: clarifying_passthrough rule count mismatch (got ${report.policy_rules.get("layer.a1_directive_ask.clarifying_passthrough")})`,
  );
  assert(
    report.noise_flagged_divergences === 1,
    `selftest: noise_flagged_divergences=${report.noise_flagged_divergences}, want 1 (case D only)`,
  );
  assert(
    report.clean_divergences === 2,
    `selftest: clean_divergences=${report.clean_divergences}, want 2 (cases C and E)`,
  );
  assert(
    (report.noise_flag_counts.get("noise.clarifying_on_fresh_route_shape") ||
      0) === 1,
    `selftest: fresh_route_shape flag not observed`,
  );

  if (fails.length > 0) {
    console.error(
      `[analyze-turn-decision-dispatch] selftest FAIL:\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }
  console.log(
    `[analyze-turn-decision-dispatch] selftest OK — ${traces.length} traces, ` +
      `${proposerEmits.length} proposer emits, ` +
      `${report.noise_flagged_divergences} noise-flagged, ` +
      `${report.clean_divergences} clean divergences.`,
  );
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

async function main() {
  if (selftest) {
    selfTest();
    return;
  }

  const { traces, proposerEmits } = await ingestAll();
  const proposersByTurn = indexProposersByTurn(proposerEmits);
  const report = emptyReport();
  aggregate(traces, proposersByTurn, report);

  if (asJson) {
    console.log(JSON.stringify(reportToJson(report), null, 2));
  } else {
    console.log(renderReport(report));
  }
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
