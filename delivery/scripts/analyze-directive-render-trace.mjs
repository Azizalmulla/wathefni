#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Phase B measure-first (2026-04-21): directive-render trace analyzer.
//
// Reads `[directive-render/trace] { ... }` log lines from stdin or a file,
// groups by directive action, and prints a human-readable breakdown of
// rendered-chars distribution vs a minimal facts-only projection for each
// action. The verbs-to-facts ratio surfaces which renderers carry the most
// prose overhead on top of their raw inputs.
//
// Usage:
//   cat journal-excerpt.log | node scripts/analyze-directive-render-trace.mjs
//   node scripts/analyze-directive-render-trace.mjs path/to/log.txt
//
// Output:
//   - Per action: count, rendered_chars min/max/mean, facts_only_chars_est,
//     verbs_chars_est (rendered − facts_only), verbs_ratio.
//   - Up to 3 sample renderings per action for manual inspection.
//
// This is a pure offline tool — no network, no deploy impact.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import readline from "node:readline";

const TRACE_PREFIX = "[directive-render/trace] ";

function extractJsonAfterPrefix(line) {
  const idx = line.indexOf(TRACE_PREFIX);
  if (idx < 0) return null;
  const jsonStart = idx + TRACE_PREFIX.length;
  const candidate = line.slice(jsonStart).trim();
  if (!candidate.startsWith("{")) return null;
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

// Minimal facts-only projection per directive action. Returns the shortest
// reasonable facts-only phrasing the renderer COULD emit given the same
// context. Keeps one short verb ("?" or "please") — facts-only does not
// mean zero prose, it means "facts + one token of framing".
function factsOnlyBaseline(action, facts) {
  const lang = facts?.language || "en";
  const ar = lang === "ar";
  const asList = (arr, sep) => (arr.length ? arr.join(sep) : "");
  switch (action) {
    case "ASK_MISSING_AREAS":
      return ar ? "الاستلام والتوصيل؟" : "Pickup and delivery areas?";
    case "ASK_PICKUP_AREA": {
      const delivery =
        facts?.quoteDropoffAreaNameEn || facts?.pendingDropoffAreaNameEn || "";
      // Option names are FACTS (they're the disambiguation candidates
      // the customer needs to pick from), so the facts-only baseline
      // includes them verbatim. We don't get the actual strings in the
      // trace payload, only the count; approximate the baseline length
      // as "(N×avg_area_name_chars + separators)".
      const opts = facts?.requested_slot_options_count || 0;
      const optsLen = opts > 0 ? opts * 10 + (opts - 1) * 2 : 0; // rough
      if (delivery && opts > 0) {
        // Template: "Delivery X. Pickup? [opts]"
        return ar
          ? `التوصيل ${delivery}. الاستلام؟ (${"x".repeat(optsLen)})`
          : `Delivery ${delivery}. Pickup? [${"x".repeat(optsLen)}]`;
      }
      if (delivery) {
        return ar
          ? `التوصيل ${delivery}. الاستلام؟`
          : `Delivery ${delivery}. Pickup?`;
      }
      return ar ? "الاستلام؟" : "Pickup area?";
    }
    case "ASK_DELIVERY_AREA": {
      const pickup =
        facts?.quotePickupAreaNameEn || facts?.pendingPickupAreaNameEn || "";
      const opts = facts?.requested_slot_options_count || 0;
      const optsLen = opts > 0 ? opts * 10 + (opts - 1) * 2 : 0;
      if (pickup && opts > 0) {
        return ar
          ? `الاستلام ${pickup}. التوصيل؟ (${"x".repeat(optsLen)})`
          : `Pickup ${pickup}. Delivery? [${"x".repeat(optsLen)}]`;
      }
      if (pickup) {
        return ar
          ? `الاستلام ${pickup}. التوصيل؟`
          : `Pickup ${pickup}. Delivery?`;
      }
      return ar ? "التوصيل؟" : "Delivery area?";
    }
    case "ASK_SENDER_NAME_AND_PHONE_DECISION":
      return ar
        ? "اسم المرسل؟ رقم واتساب أو رقم آخر؟"
        : "Sender name? This WhatsApp or another number?";
    case "ASK_SENDER_PHONE": {
      const name = facts?.senderName || "";
      if (name) {
        return ar ? `${name}. رقم المرسل؟` : `${name}. Sender phone?`;
      }
      return ar ? "رقم المرسل؟" : "Sender phone?";
    }
    case "ASK_RECIPIENT_NAME_AND_PHONE":
      return ar ? "اسم ورقم المستلم؟" : "Recipient name and phone?";
    case "ASK_PICKUP_ADDRESS": {
      const area =
        facts?.quotePickupAreaNameEn || facts?.pendingPickupAreaNameEn || "";
      if (area) {
        return ar
          ? `عنوان الاستلام في ${area} (قطعة، شارع، مبنى)؟`
          : `Pickup address in ${area} (block, street, building)?`;
      }
      return ar
        ? "عنوان الاستلام (قطعة، شارع، مبنى)؟"
        : "Pickup address (block, street, building)?";
    }
    case "ASK_DELIVERY_ADDRESS": {
      const area =
        facts?.quoteDropoffAreaNameEn || facts?.pendingDropoffAreaNameEn || "";
      if (area) {
        return ar
          ? `عنوان التوصيل في ${area} (قطعة، شارع، مبنى)؟`
          : `Delivery address in ${area} (block, street, building)?`;
      }
      return ar
        ? "عنوان التوصيل (قطعة، شارع، مبنى)؟"
        : "Delivery address (block, street, building)?";
    }
    case "CONFIRM_SLOT_CONFLICT": {
      const slot = facts?.conflictingSlot || "field";
      const inc = facts?.conflictValues?.incoming || "";
      const exist = facts?.conflictValues?.existing || "";
      if (inc && exist) {
        return ar
          ? `${slot}: "${exist}" أو "${inc}"؟`
          : `${slot}: "${exist}" or "${inc}"?`;
      }
      return ar ? `${slot}؟` : `${slot}?`;
    }
    case "COLLECT_NEXT_MISSING_FIELD":
      return ar ? "البيانات الناقصة؟" : "Remaining details?";
    case "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED":
      // The summary is deterministic state dump; facts-only baseline is
      // already the current rendering. Report as zero verb overhead.
      return null;
    default:
      return null;
  }
}

function stats(nums) {
  if (!nums.length) return { count: 0, min: 0, max: 0, mean: 0 };
  const sorted = [...nums].sort((a, b) => a - b);
  const sum = sorted.reduce((a, b) => a + b, 0);
  return {
    count: sorted.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    mean: Math.round((sum / sorted.length) * 10) / 10,
    p50: sorted[Math.floor(sorted.length / 2)],
  };
}

async function main() {
  const input =
    process.argv[2] && process.argv[2] !== "-"
      ? fs.createReadStream(process.argv[2], { encoding: "utf8" })
      : process.stdin;
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  /** @type {Map<string, { traces: any[] }>} */
  const byAction = new Map();
  let totalLines = 0;
  let matchedLines = 0;
  for await (const line of rl) {
    totalLines++;
    const trace = extractJsonAfterPrefix(line);
    if (!trace || typeof trace.action !== "string") continue;
    matchedLines++;
    if (!byAction.has(trace.action)) {
      byAction.set(trace.action, { traces: [] });
    }
    byAction.get(trace.action).traces.push(trace);
  }
  console.log(
    `[analyze-directive-render-trace] scanned=${totalLines} matched=${matchedLines} actions=${byAction.size}`,
  );
  console.log("");
  const actions = [...byAction.keys()].sort();
  for (const action of actions) {
    const bucket = byAction.get(action);
    const traces = bucket.traces;
    const renderedStats = stats(traces.map((t) => t.rendered_chars || 0));
    const factsOnlyLengths = traces
      .map((t) => {
        const base = factsOnlyBaseline(action, t.facts || {});
        return base == null ? null : base.length;
      })
      .filter((v) => v != null);
    const factsOnlyAvg = factsOnlyLengths.length
      ? Math.round(
          factsOnlyLengths.reduce((a, b) => a + b, 0) / factsOnlyLengths.length,
        )
      : null;
    const verbsEst =
      factsOnlyAvg != null
        ? Math.max(0, Math.round(renderedStats.mean - factsOnlyAvg))
        : null;
    const ratio =
      factsOnlyAvg != null && renderedStats.mean > 0
        ? Math.round(((verbsEst || 0) / renderedStats.mean) * 100)
        : null;
    console.log(`── ${action} ──────────────`);
    console.log(
      `   count=${renderedStats.count} rendered_chars min=${renderedStats.min} p50=${renderedStats.p50} mean=${renderedStats.mean} max=${renderedStats.max}`,
    );
    if (factsOnlyAvg != null) {
      console.log(
        `   facts_only_chars_est≈${factsOnlyAvg}   verbs_chars_est≈${verbsEst}   verbs_ratio≈${ratio}%`,
      );
    } else {
      console.log(`   facts_only_baseline: n/a (deterministic summary)`);
    }
    const samples = traces.slice(0, 3);
    for (const s of samples) {
      const baseline = factsOnlyBaseline(action, s.facts || {});
      console.log(`   ─ rendered  : ${JSON.stringify(s.rendered)}`);
      if (baseline != null) {
        console.log(`     facts_only: ${JSON.stringify(baseline)}`);
      }
    }
    console.log("");
  }
}

main().catch((err) => {
  console.error("analyze-directive-render-trace failed:", err);
  process.exit(1);
});
