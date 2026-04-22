#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Phase B measure-first static audit (2026-04-21).
//
// Complements `analyze-directive-render-trace.mjs` (which reads live traces)
// by walking the phrasing pools in `directive-reply-registry.ts` directly
// and computing char counts / verbs-vs-facts split without needing live
// traffic. Useful for the directives the eval corpus doesn't exercise
// (booking-collection flow, slot conflicts, etc.).
//
// Methodology:
//   - For each pool phrasing, compute total char length.
//   - Substitute synthetic fact tokens to estimate facts-only baseline:
//     area names, option counts, sender names, slot labels.
//   - Verbs ≈ rendered_len − facts_len (clamped at 0).
//
// This is heuristic — it will mis-categorise tokens that straddle
// fact/verb (e.g. "Before we continue, which value..." is pure verb).
// Use it as a directional scan, then cross-check live traces.
// ---------------------------------------------------------------------------

// Post-trim pools (2026-04-22, Phase B): each renderer now emits a single
// facts-only phrasing. `ASK_PICKUP_AREA` / `ASK_DELIVERY_AREA` are kept
// intact per the Phase B scope (already optimal at 24–27%). The summary
// directive stays a note (deterministic builder).
const EN_POOLS = {
  ASK_MISSING_AREAS: {
    pool: ["Pickup area and delivery area?"],
    facts_tokens: [],
    facts_only: "Pickup and delivery areas?",
  },
  ASK_PICKUP_AREA: {
    // Preferred shape: has delivery + options. Unchanged by Phase B trim.
    pool: [
      "Delivery to Hawalli. What's the pickup area (Doha Residential, Shalehat Doha, Mina Doha)?",
    ],
    facts_tokens: ["Hawalli", "Doha Residential, Shalehat Doha, Mina Doha"],
    facts_only: "Delivery Hawalli. Pickup? [Doha Residential/Shalehat Doha/Mina Doha]",
  },
  ASK_DELIVERY_AREA: {
    // Unchanged by Phase B trim.
    pool: [
      "Pickup from Salmiya. What's the delivery area (Sharq, Mirqab, Qibla, Bnaid Al-Qar, Dasman)?",
    ],
    facts_tokens: ["Salmiya", "Sharq, Mirqab, Qibla, Bnaid Al-Qar, Dasman"],
    facts_only: "Pickup Salmiya. Delivery? [Sharq/Mirqab/Qibla/Bnaid Al-Qar/Dasman]",
  },
  ASK_SENDER_NAME_AND_PHONE_DECISION: {
    pool: ["Sender's full name? Use this WhatsApp number, or a different one?"],
    facts_tokens: [],
    facts_only: "Sender name? This WhatsApp or another number?",
  },
  ASK_SENDER_PHONE: {
    // With-name shape is the common one (we've just captured the name
    // from the previous turn); no-name shape is the fallback.
    pool: [
      "Thanks Ahmed. Sender's phone number?",
      "Sender's phone number?",
    ],
    facts_tokens: ["Ahmed"],
    facts_only: "Sender phone? (Ahmed)",
  },
  ASK_RECIPIENT_NAME_AND_PHONE: {
    pool: ["Recipient's full name and phone number?"],
    facts_tokens: [],
    facts_only: "Recipient name and phone?",
  },
  ASK_PICKUP_ADDRESS: {
    pool: ["Pickup address in Salmiya — block, street, building/apartment?"],
    facts_tokens: ["Salmiya"],
    facts_only: "Pickup address in Salmiya (block, street, building)?",
  },
  ASK_DELIVERY_ADDRESS: {
    pool: ["Delivery address in Dasman — block, street, building/apartment?"],
    facts_tokens: ["Dasman"],
    facts_only: "Delivery address in Dasman (block, street, building)?",
  },
  CONFIRM_SLOT_CONFLICT: {
    pool: [
      'pickup block: "3" or "4"?',
      "Correct value for pickup block?",
    ],
    facts_tokens: ["pickup block", "3", "4"],
    facts_only: 'pickup block: "3" or "4"?',
  },
  COLLECT_NEXT_MISSING_FIELD: {
    pool: ["Remaining booking details?"],
    facts_tokens: [],
    facts_only: "Remaining details?",
  },
  WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED: {
    pool: [],
    facts_tokens: [],
    facts_only: null,
    note: "Deterministic summary (buildDeterministicOrderSummary); already facts-only",
  },
};

function computeFactsLen(factsTokens) {
  if (!factsTokens.length) return 0;
  // Sum of fact token lengths + 2 chars per token for light separators.
  return factsTokens.reduce((sum, t) => sum + t.length, 0) + factsTokens.length * 2;
}

console.log("Phase B static audit — en phrasing pools");
console.log("========================================");
console.log("");
const rows = [];
for (const [action, def] of Object.entries(EN_POOLS)) {
  if (def.pool.length === 0) {
    console.log(`── ${action}`);
    console.log(`   note: ${def.note}`);
    console.log("");
    continue;
  }
  const lens = def.pool.map((p) => p.length);
  const mean = Math.round(lens.reduce((a, b) => a + b, 0) / lens.length);
  const min = Math.min(...lens);
  const max = Math.max(...lens);
  const factsLen = computeFactsLen(def.facts_tokens);
  const factsOnlyLen = def.facts_only ? def.facts_only.length : null;
  const verbsEst = factsOnlyLen != null ? Math.max(0, mean - factsOnlyLen) : null;
  const verbsRatio =
    factsOnlyLen != null && mean > 0 ? Math.round((verbsEst / mean) * 100) : null;
  rows.push({ action, mean, min, max, factsLen, factsOnlyLen, verbsEst, verbsRatio, poolSize: def.pool.length });
  console.log(`── ${action}`);
  console.log(`   pool_size=${def.pool.length}  mean=${mean}  min=${min}  max=${max}`);
  console.log(`   state_facts_chars≈${factsLen}   facts_only_baseline≈${factsOnlyLen}   verbs_chars_est≈${verbsEst}   verbs_ratio≈${verbsRatio}%`);
  console.log(`   sample    : ${JSON.stringify(def.pool[0])}`);
  if (def.facts_only) {
    console.log(`   facts_only: ${JSON.stringify(def.facts_only)}`);
  }
  console.log("");
}

console.log("");
console.log("── Ranked by verbs_ratio (highest overhead first) ──");
rows
  .filter((r) => r.verbsRatio != null)
  .sort((a, b) => b.verbsRatio - a.verbsRatio)
  .forEach((r) => {
    console.log(
      `   ${String(r.verbsRatio).padStart(3)}%   mean=${String(r.mean).padStart(3)}   pool=${r.poolSize}   ${r.action}`,
    );
  });
