#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Phase 2 Milestones 1 + 2 combined shadow-signal analyzer (2026-04-22).
//
// Parses three log streams that M1 + M2 emit per turn and produces a
// human-readable report you can review before the coordinated flip-to-live.
//
//   [structured-output/proposer]   — Phase 1 shadow (ti_kind, ti_addressed_*,
//                                    ti_classification, ti_stage). Pre-existing;
//                                    we piggyback for joins.
//   [reply-compose/shadow]         — M1 (2026-04-22). What ack prefix the
//                                    server would prepend to the directive ask.
//   [slot-apply-gate/shadow]       — M2 (2026-04-22). What the apply gate
//                                    would do with this LLM-drained patch.
//
// Key questions the report answers:
//
//   * M1 COVERAGE — on directive-eligible turns, how often does the server
//     actually get a turn_intent (choice_reason != turn_intent_missing)? Low
//     coverage means the Phase-1 classifier isn't firing reliably on the
//     stages M1 depends on — fix that before flipping M1 live.
//
//   * M1 CHOICE DISTRIBUTION — per directive × ti_kind, which ack prefix
//     the server chose. Flags cells that look wrong (e.g. a directive
//     rarely getting a prefix because the draft has a built-in ack).
//
//   * M2 BLOCK RATE — per ti_kind, how often the gate would block_all vs
//     allow vs block_partial. The unclear / acknowledgement / refused /
//     clarifying_question rows tell us how much actual write-corruption
//     M2 will prevent at flip time.
//
//   * M2 FIELD-LEVEL — which patch fields get block_partial the most.
//     High-frequency entries here signal fields the LLM commonly drains
//     but doesn't name in addressed_fields — could be a real bug (LLM
//     over-drains) or a conformance bug (LLM under-names).
//
//   * ORDERING SIGNAL — what % of M2 emits had `ti_kind=-` at the callsite
//     (i.e. `apply_booking_field` arrived before `proposed_turn_decision`
//     in the drain). High numbers here mean the LLM is emitting tool calls
//     in the wrong order and M2's shadow is blind on those turns.
//
//   * PASTE-CLASS DETECTION — counts + samples of turns M2 would have
//     block_all'd with reason=ti_kind_unclear, which is exactly the
//     2026-04-22 pasted-operational-text regression target.
//
// Usage:
//   # direct file
//   node scripts/analyze-m1-m2-shadow.mjs path/to/log.txt
//
//   # streaming from journalctl
//   journalctl -u riders-delivery --since "2 hours ago" --no-pager \
//     | node scripts/analyze-m1-m2-shadow.mjs
//
//   # JSON for tooling / CI
//   node scripts/analyze-m1-m2-shadow.mjs --json log.txt
//
//   # internal self-test (synthetic corpus + asserted metrics)
//   node scripts/analyze-m1-m2-shadow.mjs --selftest
//
//   # restrict to a single conversation for deep-dive
//   node scripts/analyze-m1-m2-shadow.mjs --conv=19400 log.txt
//
// Flags:
//   --json              emit a single JSON object instead of the text report
//   --top=N             sample rows per suspicious-pattern bucket (default 5)
//   --conv=ID           restrict to a single conversation id
//   --min-samples=N     suppress noisy per-cell rates when n < N (default 0)
//   --selftest          run the bundled self-test and exit (non-zero on fail)
//
// Pure offline tool. No network, no deploy impact. Kept runnable on a bare
// Node install — no TS imports, closed-set literals duplicated and anchored
// by the accompanying smoke tests.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import readline from "node:readline";

const M1_PREFIX = "[reply-compose/shadow]";
const M1_EMIT_FAILED = "[reply-compose/shadow] emit_failed";
const M2_PREFIX = "[slot-apply-gate/shadow]";
const M2_EMIT_FAILED = "[slot-apply-gate/shadow] emit_failed";
const PROPOSER_PREFIX = "[structured-output/proposer]";
const PROPOSER_EMIT_FAILED = "[structured-output/proposer] emit failed";

// Closed-set literals — MUST mirror proposer-schema.ts and
// slot-apply-gate.ts / reply-compose.ts. The accompanying smoke tests
// anchor these, so drift here causes a test failure.
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

const M1_CHOICE_REASONS = [
  "selected",
  "turn_intent_missing",
  "low_confidence",
  "directive_has_builtin_ack",
  "summary_directive_self_ack",
  "customer_asked_question",
  "ack_of_ack",
  "unmapped_kind",
];

const M2_DECISION_KINDS = ["allow", "block_all", "block_partial"];
const M2_BLOCK_REASONS = [
  "ti_kind_unclear",
  "ti_kind_acknowledgement",
  "ti_kind_refused_or_stuck",
  "ti_kind_clarifying_question",
  "field_not_in_addressed",
];
const M2_ALLOW_REASONS = [
  "source_carryover_exempt",
  "turn_intent_missing",
  "low_confidence",
  "all_fields_addressed",
  "addressed_fields_empty_permissive",
  "empty_patch_after_meta_filter",
];

const ACK_ELIGIBLE_DIRECTIVES = [
  "ASK_MISSING_AREAS",
  "ASK_PICKUP_AREA",
  "ASK_DELIVERY_AREA",
  "COLLECT_NEXT_MISSING_FIELD",
  "ASK_SENDER_NAME_AND_PHONE_DECISION",
  "ASK_SENDER_NAME",
  "ASK_SENDER_PHONE",
  "ASK_RECIPIENT_NAME_AND_PHONE",
  "ASK_PICKUP_ADDRESS",
  "ASK_DELIVERY_ADDRESS",
  "CONFIRM_SLOT_CONFLICT",
  "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
];

// ---------------------------------------------------------------------------
// Argv parsing.
// ---------------------------------------------------------------------------

const argv = process.argv.slice(2);
let asJson = false;
let selftest = false;
let topN = 5;
let minSamples = 0;
let convFilter = null;
const filePaths = [];
for (const a of argv) {
  if (a === "--json") asJson = true;
  else if (a === "--selftest") selftest = true;
  else if (a.startsWith("--top=")) topN = Number.parseInt(a.slice(6), 10) || 5;
  else if (a.startsWith("--min-samples=")) {
    minSamples = Number.parseInt(a.slice(14), 10) || 0;
  } else if (a.startsWith("--conv=")) convFilter = a.slice(7);
  else if (a.startsWith("-")) {
    console.error(`unknown flag: ${a}`);
    process.exit(2);
  } else filePaths.push(a);
}

// ---------------------------------------------------------------------------
// Line parsers — extract the key=value token pairs from each emit shape.
//
// The emits are all single-line and token-space-separated:
//   [reply-compose/shadow] conversation=... sessionKey=... directive=...
//       lang=... ti_kind=... ti_confidence=... choice=... reason=...
//       prefix_chars=...
//   [slot-apply-gate/shadow] conversation=... turn_id=... source=...
//       ti_kind=... ti_confidence=... ti_addressed_count=...
//       patch_fields_count=... ungateable_count=... decision=...
//       reason=... blocked=[...] allowed=[...]
//
// The proposer emit is richer and already parseable — we only lift
// conversation + turn_id + ti_kind + ti_addressed_fields here.
// ---------------------------------------------------------------------------

function parseKvTokens(line) {
  // Start from the first `key=` token (skip the preamble like "2026-04-22
  // INFO [tag] ..."). This tolerates journalctl timestamps, plugin tags,
  // and any other prefix noise.
  const out = {};
  // Regex: match tokens of form `key=value` where value is either
  // [...] bracket list OR a non-whitespace run.
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)=(\[[^\]]*\]|"[^"]*"|\S+)/g;
  let m;
  while ((m = re.exec(line)) !== null) {
    let v = m[2];
    if (v.startsWith("[") && v.endsWith("]")) {
      v = v.slice(1, -1);
    } else if (v.startsWith('"') && v.endsWith('"')) {
      v = v.slice(1, -1);
    }
    out[m[1]] = v;
  }
  return out;
}

function parsePipeList(token) {
  if (!token || token === "-") return [];
  return token.split("|").filter(Boolean);
}

// ---------------------------------------------------------------------------
// Accumulator.
// ---------------------------------------------------------------------------

function makeState() {
  return {
    totalLines: 0,
    m1: {
      total: 0,
      emitFailures: 0,
      byChoiceKind: Object.create(null), // { prefix: n, skip: n }
      byChoiceReason: Object.create(null),
      byDirectiveKind: Object.create(null), // key=`${directive}|${ti_kind}` → {prefix, skip, total}
      byLanguage: Object.create(null),
      byTiKind: Object.create(null),
      missingTiCount: 0,
      lowConfidenceCount: 0,
      samples: [],
    },
    m2: {
      total: 0,
      emitFailures: 0,
      byDecisionKind: Object.create(null), // {allow, block_all, block_partial}
      byDecisionReason: Object.create(null),
      byTiKind: Object.create(null), // ti_kind → {allow, block_all, block_partial, total}
      bySource: Object.create(null),
      orderingMissingTi: 0,
      blockedFieldCounts: Object.create(null),
      pasteClassSamples: [], // block_all + ti_kind_unclear
      partialBlockSamples: [],
    },
    proposer: {
      total: 0,
      byTiKind: Object.create(null),
      byTurnId: Object.create(null), // turn_id → {ti_kind, ti_addressed, conversation}
    },
  };
}

function bump(obj, key) {
  obj[key] = (obj[key] || 0) + 1;
}

// ---------------------------------------------------------------------------
// Ingest one line.
// ---------------------------------------------------------------------------

function ingest(state, line) {
  state.totalLines += 1;

  // Fast filter — our three prefixes anywhere in the line.
  const hasM1 = line.includes(M1_PREFIX);
  const hasM2 = line.includes(M2_PREFIX);
  const hasProp = line.includes(PROPOSER_PREFIX);
  if (!hasM1 && !hasM2 && !hasProp) return;

  // Emit-failure lines — count separately, do NOT parse kvs from them.
  if (hasM1 && line.includes(M1_EMIT_FAILED)) {
    state.m1.emitFailures += 1;
    return;
  }
  if (hasM2 && line.includes(M2_EMIT_FAILED)) {
    state.m2.emitFailures += 1;
    return;
  }
  if (hasProp && line.includes(PROPOSER_EMIT_FAILED)) {
    return;
  }

  const tok = parseKvTokens(line);
  if (convFilter) {
    const conv = tok.conversation || tok.conv;
    if (conv !== convFilter) return;
  }

  // Proposer — lift ti_kind + ti_addressed for cross-signal joins.
  if (hasProp) {
    if (!tok.ti_kind) return;
    state.proposer.total += 1;
    bump(state.proposer.byTiKind, tok.ti_kind);
    const turnId = tok.turn_id || tok.turnId;
    if (turnId) {
      state.proposer.byTurnId[turnId] = {
        ti_kind: tok.ti_kind,
        ti_addressed: parsePipeList(tok.ti_addressed_fields),
        conversation: tok.conversation || null,
      };
    }
    return;
  }

  if (hasM1) {
    const directive = tok.directive || "-";
    const tiKind = tok.ti_kind || "-";
    const tiConfidence = tok.ti_confidence || "-";
    const language = tok.lang || "-";
    const choice = tok.choice || "-";
    const reason = tok.reason || "-";

    state.m1.total += 1;
    bump(state.m1.byChoiceKind, choice);
    bump(state.m1.byChoiceReason, reason);
    bump(state.m1.byLanguage, language);
    bump(state.m1.byTiKind, tiKind);
    const cell = `${directive}|${tiKind}`;
    if (!state.m1.byDirectiveKind[cell]) {
      state.m1.byDirectiveKind[cell] = { prefix: 0, skip: 0, total: 0 };
    }
    state.m1.byDirectiveKind[cell].total += 1;
    if (choice === "prefix") state.m1.byDirectiveKind[cell].prefix += 1;
    else state.m1.byDirectiveKind[cell].skip += 1;

    if (reason === "turn_intent_missing") state.m1.missingTiCount += 1;
    if (reason === "low_confidence") state.m1.lowConfidenceCount += 1;

    if (state.m1.samples.length < topN) {
      state.m1.samples.push({
        directive,
        tiKind,
        tiConfidence,
        language,
        choice,
        reason,
        prefix_chars: tok.prefix_chars ? Number(tok.prefix_chars) : 0,
        conversation: tok.conversation || null,
      });
    }
    return;
  }

  if (hasM2) {
    const tiKind = tok.ti_kind || "-";
    const source = tok.source || "-";
    const decision = tok.decision || "-";
    const reason = tok.reason || "-";
    const blocked = parsePipeList(tok.blocked);
    const allowed = parsePipeList(tok.allowed);

    state.m2.total += 1;
    bump(state.m2.byDecisionKind, decision);
    bump(state.m2.byDecisionReason, reason);
    bump(state.m2.bySource, source);

    if (!state.m2.byTiKind[tiKind]) {
      state.m2.byTiKind[tiKind] = {
        allow: 0,
        block_all: 0,
        block_partial: 0,
        total: 0,
      };
    }
    state.m2.byTiKind[tiKind].total += 1;
    if (decision === "allow") state.m2.byTiKind[tiKind].allow += 1;
    else if (decision === "block_all") state.m2.byTiKind[tiKind].block_all += 1;
    else if (decision === "block_partial") {
      state.m2.byTiKind[tiKind].block_partial += 1;
    }

    if (tiKind === "-") state.m2.orderingMissingTi += 1;

    for (const f of blocked) bump(state.m2.blockedFieldCounts, f);

    if (
      decision === "block_all" &&
      reason === "ti_kind_unclear" &&
      state.m2.pasteClassSamples.length < topN
    ) {
      state.m2.pasteClassSamples.push({
        conversation: tok.conversation || null,
        turn_id: tok.turn_id || null,
        source,
        patch_fields_count: tok.patch_fields_count || "0",
      });
    }

    if (
      decision === "block_partial" &&
      state.m2.partialBlockSamples.length < topN
    ) {
      state.m2.partialBlockSamples.push({
        conversation: tok.conversation || null,
        turn_id: tok.turn_id || null,
        tiKind,
        source,
        blocked,
        allowed,
      });
    }
    return;
  }
}

// ---------------------------------------------------------------------------
// Report writers.
// ---------------------------------------------------------------------------

function pct(num, den) {
  if (!den) return "0.0%";
  return ((num / den) * 100).toFixed(1) + "%";
}

function renderTextReport(state) {
  const lines = [];
  lines.push(
    `# Phase 2 M1 + M2 shadow-signal report`,
    `Total input lines scanned: ${state.totalLines}`,
    ``,
  );
  if (convFilter) {
    lines.push(`Filter: conversation=${convFilter}`, ``);
  }

  // --- proposer cross-signal ------------------------------------------------
  lines.push(
    `## Proposer join (observed ti_kind distribution)`,
    `Total [structured-output/proposer] emits with ti_kind: ${state.proposer.total}`,
  );
  if (state.proposer.total > 0) {
    for (const k of TURN_INTENT_KINDS) {
      const n = state.proposer.byTiKind[k] || 0;
      if (n === 0 && minSamples > 0) continue;
      lines.push(`  ${k.padEnd(22)} ${String(n).padStart(6)}  ${pct(n, state.proposer.total)}`);
    }
    const missing = state.proposer.byTiKind["-"] || 0;
    if (missing) {
      lines.push(`  (missing)              ${String(missing).padStart(6)}  ${pct(missing, state.proposer.total)}`);
    }
  }
  lines.push(``);

  // --- M1 -------------------------------------------------------------------
  lines.push(`## M1 — reply-compose shadow`);
  lines.push(`Total emits: ${state.m1.total} (failures: ${state.m1.emitFailures})`);
  if (state.m1.total === 0) {
    lines.push(`  (no M1 emits seen)`, ``);
  } else {
    lines.push(``, `### Choice kind`);
    for (const [k, n] of sortedEntries(state.m1.byChoiceKind)) {
      lines.push(`  ${k.padEnd(12)} ${String(n).padStart(6)}  ${pct(n, state.m1.total)}`);
    }

    lines.push(``, `### Choice reason`);
    for (const r of M1_CHOICE_REASONS) {
      const n = state.m1.byChoiceReason[r] || 0;
      if (n === 0 && minSamples > 0) continue;
      lines.push(`  ${r.padEnd(32)} ${String(n).padStart(6)}  ${pct(n, state.m1.total)}`);
    }
    const otherReasons = Object.keys(state.m1.byChoiceReason)
      .filter((r) => !M1_CHOICE_REASONS.includes(r))
      .sort();
    for (const r of otherReasons) {
      lines.push(`  ${r.padEnd(32)} ${String(state.m1.byChoiceReason[r]).padStart(6)}  ${pct(state.m1.byChoiceReason[r], state.m1.total)}`);
    }

    lines.push(``, `### Turn-intent coverage at M1`);
    lines.push(
      `  missing_turn_intent: ${state.m1.missingTiCount} (${pct(state.m1.missingTiCount, state.m1.total)})`,
    );
    lines.push(
      `  low_confidence:      ${state.m1.lowConfidenceCount} (${pct(state.m1.lowConfidenceCount, state.m1.total)})`,
    );
    const effective = state.m1.total - state.m1.missingTiCount - state.m1.lowConfidenceCount;
    lines.push(
      `  effective_coverage:  ${effective} (${pct(effective, state.m1.total)})`,
    );

    lines.push(``, `### Directive × ti_kind cells (sorted by volume, min=${minSamples})`);
    const cellEntries = Object.entries(state.m1.byDirectiveKind)
      .filter(([_, v]) => v.total >= minSamples)
      .sort((a, b) => b[1].total - a[1].total);
    lines.push(
      `  ${"directive".padEnd(42)} ${"ti_kind".padEnd(22)} ${"prefix".padStart(7)} ${"skip".padStart(7)} ${"total".padStart(7)}`,
    );
    for (const [cell, v] of cellEntries.slice(0, 30)) {
      const [directive, tiKind] = cell.split("|");
      lines.push(
        `  ${directive.padEnd(42)} ${tiKind.padEnd(22)} ${String(v.prefix).padStart(7)} ${String(v.skip).padStart(7)} ${String(v.total).padStart(7)}`,
      );
    }
    if (cellEntries.length > 30) {
      lines.push(`  ... (${cellEntries.length - 30} more cells)`);
    }

    lines.push(``, `### M1 samples (first ${state.m1.samples.length})`);
    for (const s of state.m1.samples) {
      lines.push(
        `  conv=${s.conversation || "-"} dir=${s.directive} ti=${s.tiKind}/${s.tiConfidence} lang=${s.language} choice=${s.choice} reason=${s.reason} prefix_chars=${s.prefix_chars}`,
      );
    }
  }
  lines.push(``);

  // --- M2 -------------------------------------------------------------------
  lines.push(`## M2 — slot-apply-gate shadow`);
  lines.push(`Total emits: ${state.m2.total} (failures: ${state.m2.emitFailures})`);
  if (state.m2.total === 0) {
    lines.push(`  (no M2 emits seen)`, ``);
  } else {
    lines.push(``, `### Decision kind`);
    for (const k of M2_DECISION_KINDS) {
      const n = state.m2.byDecisionKind[k] || 0;
      lines.push(`  ${k.padEnd(14)} ${String(n).padStart(6)}  ${pct(n, state.m2.total)}`);
    }

    lines.push(``, `### Decision reason (block reasons)`);
    for (const r of M2_BLOCK_REASONS) {
      const n = state.m2.byDecisionReason[r] || 0;
      if (n === 0 && minSamples > 0) continue;
      lines.push(`  ${r.padEnd(32)} ${String(n).padStart(6)}  ${pct(n, state.m2.total)}`);
    }

    lines.push(``, `### Decision reason (allow reasons)`);
    for (const r of M2_ALLOW_REASONS) {
      const n = state.m2.byDecisionReason[r] || 0;
      if (n === 0 && minSamples > 0) continue;
      lines.push(`  ${r.padEnd(32)} ${String(n).padStart(6)}  ${pct(n, state.m2.total)}`);
    }

    lines.push(``, `### By ti_kind`);
    const tiEntries = Object.entries(state.m2.byTiKind).sort(
      (a, b) => b[1].total - a[1].total,
    );
    lines.push(
      `  ${"ti_kind".padEnd(22)} ${"allow".padStart(7)} ${"block_all".padStart(10)} ${"block_part".padStart(11)} ${"total".padStart(7)}`,
    );
    for (const [k, v] of tiEntries) {
      if (v.total < minSamples) continue;
      lines.push(
        `  ${k.padEnd(22)} ${String(v.allow).padStart(7)} ${String(v.block_all).padStart(10)} ${String(v.block_partial).padStart(11)} ${String(v.total).padStart(7)}`,
      );
    }

    lines.push(``, `### By proposal source`);
    for (const [k, n] of sortedEntries(state.m2.bySource)) {
      lines.push(`  ${k.padEnd(12)} ${String(n).padStart(6)}  ${pct(n, state.m2.total)}`);
    }

    lines.push(``, `### Ordering signal`);
    lines.push(
      `  apply_before_proposer (ti_kind=-): ${state.m2.orderingMissingTi} (${pct(state.m2.orderingMissingTi, state.m2.total)})`,
    );
    lines.push(
      `  if this is high (>~10%), the LLM is emitting apply_booking_field before`,
      `  propose_turn_decision; M2 shadow is blind on those turns.`,
    );

    lines.push(``, `### Blocked-field counts (partial blocks)`);
    const fieldEntries = sortedEntries(state.m2.blockedFieldCounts).slice(0, 15);
    for (const [f, n] of fieldEntries) {
      lines.push(`  ${f.padEnd(24)} ${String(n).padStart(6)}`);
    }

    lines.push(``, `### Paste-class samples (block_all + ti_kind_unclear)`);
    if (state.m2.pasteClassSamples.length === 0) {
      lines.push(`  (none observed yet)`);
    } else {
      for (const s of state.m2.pasteClassSamples) {
        lines.push(
          `  conv=${s.conversation || "-"} turn=${s.turn_id || "-"} source=${s.source} patch_fields=${s.patch_fields_count}`,
        );
      }
    }

    lines.push(``, `### Partial-block samples (first ${state.m2.partialBlockSamples.length})`);
    for (const s of state.m2.partialBlockSamples) {
      lines.push(
        `  conv=${s.conversation || "-"} turn=${s.turn_id || "-"} ti=${s.tiKind} source=${s.source} blocked=[${s.blocked.join("|")}] allowed=[${s.allowed.join("|")}]`,
      );
    }
  }
  lines.push(``);

  // --- Flip readiness summary -----------------------------------------------
  lines.push(`## Flip readiness summary`);
  const m1Miss = state.m1.total > 0 ? state.m1.missingTiCount / state.m1.total : 0;
  const m2MissOrder =
    state.m2.total > 0 ? state.m2.orderingMissingTi / state.m2.total : 0;
  const pasteBlocks = state.m2.byDecisionReason["ti_kind_unclear"] || 0;

  lines.push(
    `  M1 turn_intent_missing rate: ${pct(state.m1.missingTiCount, state.m1.total)}`,
  );
  lines.push(
    `  M2 apply_before_proposer rate: ${pct(state.m2.orderingMissingTi, state.m2.total)}`,
  );
  lines.push(`  M2 paste-class blocks observed: ${pasteBlocks}`);
  lines.push(``);
  lines.push(`Heuristic guidance (NOT a hard gate — review the full tables):`);
  lines.push(`  * M1.5 flip: prefer M1 turn_intent_missing < ~15%.`);
  lines.push(`  * M2 flip:   prefer M2 apply_before_proposer < ~10%.`);
  lines.push(`  * Fire drill: if paste-class blocks > 0 AND those conversations`);
  lines.push(`                appear to be legitimate booking turns — DO NOT FLIP.`);
  lines.push(`                Investigate the transcripts before flipping.`);

  if (m1Miss > 0.15 && state.m1.total >= 20) {
    lines.push(``, `⚠ M1 turn_intent_missing rate above 15% — classifier coverage gap.`);
  }
  if (m2MissOrder > 0.1 && state.m2.total >= 20) {
    lines.push(
      ``,
      `⚠ M2 apply_before_proposer rate above 10% — tool-call ordering issue.`,
    );
  }

  return lines.join("\n");
}

function sortedEntries(obj) {
  return Object.entries(obj).sort((a, b) => b[1] - a[1]);
}

function renderJson(state) {
  // Flatten for JSON consumers. Avoid Object.create(null) nuances by
  // copying via spread.
  return {
    total_lines: state.totalLines,
    proposer: {
      total: state.proposer.total,
      by_ti_kind: { ...state.proposer.byTiKind },
    },
    m1: {
      total: state.m1.total,
      emit_failures: state.m1.emitFailures,
      by_choice_kind: { ...state.m1.byChoiceKind },
      by_choice_reason: { ...state.m1.byChoiceReason },
      by_language: { ...state.m1.byLanguage },
      by_ti_kind: { ...state.m1.byTiKind },
      by_directive_kind: { ...state.m1.byDirectiveKind },
      missing_ti_count: state.m1.missingTiCount,
      low_confidence_count: state.m1.lowConfidenceCount,
      samples: state.m1.samples,
    },
    m2: {
      total: state.m2.total,
      emit_failures: state.m2.emitFailures,
      by_decision_kind: { ...state.m2.byDecisionKind },
      by_decision_reason: { ...state.m2.byDecisionReason },
      by_ti_kind: { ...state.m2.byTiKind },
      by_source: { ...state.m2.bySource },
      apply_before_proposer: state.m2.orderingMissingTi,
      blocked_field_counts: { ...state.m2.blockedFieldCounts },
      paste_class_samples: state.m2.pasteClassSamples,
      partial_block_samples: state.m2.partialBlockSamples,
    },
  };
}

// ---------------------------------------------------------------------------
// Self-test — synthetic corpus with asserted metrics.
// ---------------------------------------------------------------------------

function runSelftest() {
  const fixture = [
    // M1 cases
    `2026-04-22 INFO [reply-compose/shadow] conversation=c1 sessionKey=s1 directive=ASK_SENDER_PHONE lang=en ti_kind=answered_partial ti_confidence=high choice=prefix reason=selected prefix_chars=7`,
    `2026-04-22 INFO [reply-compose/shadow] conversation=c1 sessionKey=s1 directive=ASK_SENDER_PHONE lang=en ti_kind=answered_partial ti_confidence=high choice=skip reason=directive_has_builtin_ack prefix_chars=0`,
    `2026-04-22 INFO [reply-compose/shadow] conversation=c2 sessionKey=s2 directive=ASK_RECIPIENT_NAME_AND_PHONE lang=ar ti_kind=- ti_confidence=- choice=skip reason=turn_intent_missing prefix_chars=0`,
    `2026-04-22 INFO [reply-compose/shadow] conversation=c3 sessionKey=s3 directive=ASK_SENDER_NAME_AND_PHONE_DECISION lang=en ti_kind=unclear ti_confidence=high choice=prefix reason=selected prefix_chars=38`,
    `2026-04-22 WARN [reply-compose/shadow] emit_failed conversation=c4 error=boom`,
    // M2 cases
    `2026-04-22 INFO [slot-apply-gate/shadow] conversation=c1 turn_id=t1 source=llm ti_kind=answered_partial ti_confidence=high ti_addressed_count=2 patch_fields_count=2 ungateable_count=0 decision=allow reason=all_fields_addressed blocked=[-] allowed=[-]`,
    `2026-04-22 INFO [slot-apply-gate/shadow] conversation=c2 turn_id=t2 source=llm ti_kind=unclear ti_confidence=high ti_addressed_count=0 patch_fields_count=1 ungateable_count=0 decision=block_all reason=ti_kind_unclear blocked=[-] allowed=[-]`,
    `2026-04-22 INFO [slot-apply-gate/shadow] conversation=c3 turn_id=t3 source=llm ti_kind=answered_partial ti_confidence=high ti_addressed_count=1 patch_fields_count=2 ungateable_count=0 decision=block_partial reason=field_not_in_addressed blocked=[recipient_phone] allowed=[sender_name]`,
    `2026-04-22 INFO [slot-apply-gate/shadow] conversation=c4 turn_id=t4 source=llm ti_kind=- ti_confidence=- ti_addressed_count=0 patch_fields_count=1 ungateable_count=0 decision=allow reason=turn_intent_missing blocked=[-] allowed=[-]`,
    `2026-04-22 INFO [slot-apply-gate/shadow] conversation=c5 turn_id=t5 source=carryover ti_kind=answered_full ti_confidence=high ti_addressed_count=0 patch_fields_count=3 ungateable_count=0 decision=allow reason=source_carryover_exempt blocked=[-] allowed=[-]`,
    // Proposer
    `2026-04-22 INFO [structured-output/proposer] conversation=c1 turn_id=t1 ti_stage=true ti_kind=answered_partial ti_confidence=high ti_addressed_fields=[sender_name|sender_phone] ti_classification=present`,
    `2026-04-22 INFO [structured-output/proposer] conversation=c2 turn_id=t2 ti_stage=true ti_kind=unclear ti_confidence=high ti_addressed_fields=[] ti_classification=present`,
  ];
  const state = makeState();
  for (const l of fixture) ingest(state, l);

  const assert = (cond, msg) => {
    if (!cond) {
      console.error(`SELFTEST FAIL: ${msg}`);
      process.exit(1);
    }
  };

  assert(state.m1.total === 4, `m1.total expected 4, got ${state.m1.total}`);
  assert(state.m1.emitFailures === 1, `m1.emitFailures expected 1`);
  assert(
    state.m1.byChoiceKind.prefix === 2,
    `m1 prefix expected 2 got ${state.m1.byChoiceKind.prefix}`,
  );
  assert(
    state.m1.byChoiceKind.skip === 2,
    `m1 skip expected 2 got ${state.m1.byChoiceKind.skip}`,
  );
  assert(
    state.m1.byChoiceReason.selected === 2,
    `m1 selected reason expected 2`,
  );
  assert(
    state.m1.byChoiceReason.turn_intent_missing === 1,
    `m1 missing reason expected 1`,
  );
  assert(state.m1.missingTiCount === 1, `m1 missingTi expected 1`);
  assert(
    state.m1.byDirectiveKind["ASK_SENDER_PHONE|answered_partial"].total === 2,
    `m1 ASK_SENDER_PHONE|answered_partial total expected 2`,
  );

  assert(state.m2.total === 5, `m2.total expected 5 got ${state.m2.total}`);
  assert(
    state.m2.byDecisionKind.allow === 3,
    `m2 allow expected 3 got ${state.m2.byDecisionKind.allow}`,
  );
  assert(state.m2.byDecisionKind.block_all === 1, `m2 block_all expected 1`);
  assert(
    state.m2.byDecisionKind.block_partial === 1,
    `m2 block_partial expected 1`,
  );
  assert(
    state.m2.byDecisionReason.ti_kind_unclear === 1,
    `m2 ti_kind_unclear expected 1`,
  );
  assert(state.m2.orderingMissingTi === 1, `m2 missing_ti at gate expected 1`);
  assert(
    state.m2.blockedFieldCounts.recipient_phone === 1,
    `m2 blocked recipient_phone expected 1`,
  );
  assert(state.m2.pasteClassSamples.length === 1, `m2 paste-class samples expected 1`);
  assert(state.m2.partialBlockSamples.length === 1, `m2 partial-block samples expected 1`);
  assert(state.m2.bySource.llm === 4, `m2 llm source expected 4`);
  assert(state.m2.bySource.carryover === 1, `m2 carryover source expected 1`);

  assert(state.proposer.total === 2, `proposer total expected 2`);
  assert(
    state.proposer.byTurnId.t2.ti_kind === "unclear",
    `proposer t2 ti_kind expected unclear`,
  );

  // Smoke the report writers too.
  const txt = renderTextReport(state);
  assert(txt.includes("M1 — reply-compose shadow"), `text report missing M1 header`);
  assert(txt.includes("M2 — slot-apply-gate shadow"), `text report missing M2 header`);
  assert(txt.includes("Paste-class samples"), `text report missing paste-class section`);
  const json = renderJson(state);
  assert(json.m1.total === 4, `json m1.total`);
  assert(json.m2.total === 5, `json m2.total`);

  console.log("[analyze-m1-m2-shadow] SELFTEST OK");
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

async function main() {
  if (selftest) {
    runSelftest();
    return;
  }

  const state = makeState();

  async function readFromStream(stream) {
    const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });
    for await (const line of rl) ingest(state, line);
  }

  if (filePaths.length === 0) {
    if (process.stdin.isTTY) {
      console.error(
        `usage: analyze-m1-m2-shadow.mjs [--json] [--top=N] [--conv=ID] [--min-samples=N] [--selftest] <file>`,
      );
      console.error(`       pipe logs via stdin, e.g.:`);
      console.error(
        `       journalctl -u riders-delivery --since "2 hours ago" --no-pager \\`,
      );
      console.error(`         | node scripts/analyze-m1-m2-shadow.mjs`);
      process.exit(2);
    }
    await readFromStream(process.stdin);
  } else {
    for (const p of filePaths) {
      const stream = fs.createReadStream(p, { encoding: "utf8" });
      await readFromStream(stream);
    }
  }

  if (asJson) {
    process.stdout.write(JSON.stringify(renderJson(state), null, 2) + "\n");
  } else {
    process.stdout.write(renderTextReport(state) + "\n");
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
