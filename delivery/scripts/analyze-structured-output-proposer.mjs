#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Phase 1 / Milestone 2 (2026-04-22): structured-output/proposer conformance
// analyzer for the `turn_intent` shadow layer (and, as a free side-signal,
// `awaiting_confirmation`).
//
// Reads `[structured-output/proposer]` log lines from stdin or a file,
// groups by conformance bucket / kind / stage, and prints a human-readable
// report. Used to read the v1.2 shadow signal before any Phase 2 behavior
// wiring — if numbers aren't good enough here, we don't wire them into
// live policy.
//
// Usage:
//   # direct file
//   node scripts/analyze-structured-output-proposer.mjs path/to/log.txt
//
//   # streaming from journalctl
//   journalctl -u riders-delivery --since "1 hour ago" --no-pager \
//     | node scripts/analyze-structured-output-proposer.mjs
//
//   # JSON for tooling / CI
//   node scripts/analyze-structured-output-proposer.mjs --json log.txt
//
//   # internal self-test (synthetic corpus + asserted metrics)
//   node scripts/analyze-structured-output-proposer.mjs --selftest
//
// Flags:
//   --json          emit a single JSON object instead of the text report
//   --top=N         sample rows per suspicious-pattern bucket (default 3)
//   --conv=ID       restrict to a single conversation id
//   --selftest      run the bundled self-test and exit (non-zero on fail)
//   --min-samples=N suppress noisy per-cell rates when n < N (default 0)
//
// This is a pure offline tool. No network, no deploy impact.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import readline from "node:readline";

const PROPOSER_PREFIX = "[structured-output/proposer]";
const EMIT_FAILED_HINT = "[structured-output/proposer] emit failed";

// ---------------------------------------------------------------------
// Canonical closed sets. Must stay in sync with proposer-schema.ts; we
// do not import the TS file to keep this tool runnable standalone on a
// bare Node install. The v1.2 smoke test anchors the source list; any
// addition there should also land here.
// ---------------------------------------------------------------------
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
const TURN_INTENT_CONFIDENCES = ["high", "medium", "low"];
const TURN_INTENT_ADDRESSED_FIELDS = [
  "sender_name",
  "sender_phone",
  "recipient_name",
  "recipient_phone",
  "pickup_area",
  "dropoff_area",
  "pickup_address",
  "delivery_address",
  "route",
  "option",
];
const AWAITING_CONFIRMATION_KINDS = [
  "confirm_order",
  "cancel_order",
  "edit_order",
  "informational_question",
  "coherence_pleasantry",
  "unclear",
];
const EXPECTED_TI_STAGES = [
  "collecting_booking_details",
  "summary_shown",
  "awaiting_confirmation",
];
const CLASSIFICATION_BUCKETS = ["present", "missing", "unexpected", "n/a"];

// ---------------------------------------------------------------------
// Line parser. Matches `k=v` pairs where `v` is either a compact-list
// `[a|b|c]` or a non-whitespace token. Robust to journalctl prefix lines
// (timestamp / host / unit) — we only consume tokens that appear after
// the `[structured-output/proposer]` marker itself.
// ---------------------------------------------------------------------
const KV_RE = /(\w+)=(\[[^\]]*\]|[^\s]+)/g;

function parseLine(rawLine) {
  const line = rawLine.replace(/\r$/, "");
  const markerIdx = line.indexOf(PROPOSER_PREFIX);
  if (markerIdx < 0) return null;
  if (line.includes(EMIT_FAILED_HINT)) {
    return { kind: "emit_failed", raw: line };
  }
  const body = line.slice(markerIdx + PROPOSER_PREFIX.length);
  const tokens = {};
  let m;
  KV_RE.lastIndex = 0;
  while ((m = KV_RE.exec(body)) !== null) {
    const key = m[1];
    let value = m[2];
    if (value.startsWith("[") && value.endsWith("]")) {
      const inner = value.slice(1, -1);
      value = inner === "" ? [] : inner.split("|");
    }
    tokens[key] = value;
  }
  if (!tokens.conversation) return null; // not a conformance emit
  return { kind: "emit", raw: line, tokens };
}

// ---------------------------------------------------------------------
// Collectors.
// ---------------------------------------------------------------------
function makeAccumulator() {
  return {
    totalLines: 0,
    emitFailed: 0,
    emits: [],
    byConversation: new Map(),
    schemaVersions: new Map(),
    payloadValidity: {
      present_valid: 0,
      present_invalid: 0,
      absent: 0,
    },
    tiClassification: new Map(),
    acClassification: new Map(),
    tiKind: new Map(),
    tiConfidence: new Map(),
    acKind: new Map(),
    fieldCoverage: new Map(), // stage → { totalWithTi, perField:Map<field, count> }
    fieldCoverageByRequestedSlot: new Map(),
    kindByStage: new Map(), // stage → Map<kind, count>
    kindByRequestedSlot: new Map(),
    errorsObserved: new Map(),
    suspicious: {
      answered_but_empty_fields: { count: 0, samples: [] },
      ack_or_refused_but_fields: { count: 0, samples: [] },
      clarifying_question_but_fields: { count: 0, samples: [] },
      corrected_prior_but_empty_fields: { count: 0, samples: [] },
      ti_missing_on_expected_stage: { count: 0, samples: [] },
      ti_unexpected: { count: 0, samples: [] },
      invalid_payload_v12: { count: 0, samples: [] },
      unknown_token_in_addressed_fields: { count: 0, samples: [] },
      ac_vs_ti_contradiction: { count: 0, samples: [] },
    },
  };
}

function inc(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function incNested(outer, outerKey, innerKey) {
  let inner = outer.get(outerKey);
  if (!inner) {
    inner = new Map();
    outer.set(outerKey, inner);
  }
  inner.set(innerKey, (inner.get(innerKey) || 0) + 1);
}

function record(acc, parsed) {
  acc.totalLines += 1;
  if (parsed.kind === "emit_failed") {
    acc.emitFailed += 1;
    return;
  }
  const t = parsed.tokens;
  acc.emits.push(t);
  inc(acc.byConversation, t.conversation);

  const version = t.schema_version || "-";
  inc(acc.schemaVersions, version);

  const present = t.present === "true";
  const valid = t.schema_valid === "true";
  if (!present) acc.payloadValidity.absent += 1;
  else if (valid) acc.payloadValidity.present_valid += 1;
  else acc.payloadValidity.present_invalid += 1;

  const stage = t.stage || "-";
  const requestedSlot = t.requested_slot || "-";

  // ti_classification bucket rate
  const tiClass = t.ti_classification || "n/a";
  inc(acc.tiClassification, tiClass);

  // ac_classification bucket rate (free side-signal)
  const acClass = t.ac_classification || "n/a";
  inc(acc.acClassification, acClass);

  // Distributions — only over rows where the LLM actually provided the
  // field (classification=present). Unexpected rows are NOT counted in the
  // kind/confidence distribution because by definition they happen outside
  // the intended window and would bias the "what does the classifier think
  // of a typical collection turn" signal.
  const tiKind = t.ti_kind || "-";
  if (tiClass === "present" && tiKind !== "-") inc(acc.tiKind, tiKind);

  const tiConfidence = t.ti_confidence || "-";
  if (tiClass === "present" && tiConfidence !== "-")
    inc(acc.tiConfidence, tiConfidence);

  const acKind = t.ac_kind || "-";
  if (acClass === "present" && acKind !== "-") inc(acc.acKind, acKind);

  // addressed_fields coverage by stage / requested_slot — only counts rows
  // that actually carried turn_intent (classification=present). "absent"
  // rows don't contribute — they're tracked separately via tiClassification.
  const addressedFields = Array.isArray(t.ti_addressed_fields)
    ? t.ti_addressed_fields
    : [];
  if (tiClass === "present") {
    let stageBucket = acc.fieldCoverage.get(stage);
    if (!stageBucket) {
      stageBucket = { totalWithTi: 0, perField: new Map(), empty: 0 };
      acc.fieldCoverage.set(stage, stageBucket);
    }
    stageBucket.totalWithTi += 1;
    if (addressedFields.length === 0) stageBucket.empty += 1;
    for (const f of addressedFields) {
      stageBucket.perField.set(f, (stageBucket.perField.get(f) || 0) + 1);
    }

    let rsBucket = acc.fieldCoverageByRequestedSlot.get(requestedSlot);
    if (!rsBucket) {
      rsBucket = { totalWithTi: 0, perField: new Map(), empty: 0 };
      acc.fieldCoverageByRequestedSlot.set(requestedSlot, rsBucket);
    }
    rsBucket.totalWithTi += 1;
    if (addressedFields.length === 0) rsBucket.empty += 1;
    for (const f of addressedFields) {
      rsBucket.perField.set(f, (rsBucket.perField.get(f) || 0) + 1);
    }

    incNested(acc.kindByStage, stage, tiKind);
    incNested(acc.kindByRequestedSlot, requestedSlot, tiKind);
  }

  // Errors surface.
  if (t.errors && t.errors !== "-") {
    const errList = String(t.errors).split(",").filter(Boolean);
    for (const e of errList) inc(acc.errorsObserved, e);
  }

  // Unknown-token surface: the emit may carry tokens the analyzer doesn't
  // know about (e.g. a future token added to the schema but not to this
  // tool yet). Flag them rather than silently absorbing them.
  for (const f of addressedFields) {
    if (!TURN_INTENT_ADDRESSED_FIELDS.includes(f)) {
      pushCapped(acc.suspicious.unknown_token_in_addressed_fields, t);
    }
  }

  // Suspicious-pattern detectors. Each bucket caps at 32 samples to keep
  // output and JSON reasonable; counts go beyond the sample cap.
  const hasFields = addressedFields.length > 0;
  if (
    tiClass === "present" &&
    (tiKind === "answered_full" || tiKind === "answered_partial") &&
    !hasFields
  ) {
    pushCapped(acc.suspicious.answered_but_empty_fields, t);
  }
  if (
    tiClass === "present" &&
    (tiKind === "acknowledgement" || tiKind === "refused_or_stuck") &&
    hasFields
  ) {
    pushCapped(acc.suspicious.ack_or_refused_but_fields, t);
  }
  if (tiClass === "present" && tiKind === "clarifying_question" && hasFields) {
    pushCapped(acc.suspicious.clarifying_question_but_fields, t);
  }
  if (tiClass === "present" && tiKind === "corrected_prior" && !hasFields) {
    pushCapped(acc.suspicious.corrected_prior_but_empty_fields, t);
  }
  if (tiClass === "missing") {
    pushCapped(acc.suspicious.ti_missing_on_expected_stage, t);
  }
  if (tiClass === "unexpected") {
    pushCapped(acc.suspicious.ti_unexpected, t);
  }
  if (version === "1.2" && !valid && present) {
    pushCapped(acc.suspicious.invalid_payload_v12, t);
  }
  // Cross-signal sanity: ac thinks the customer confirmed/cancelled but ti
  // labels the turn as refused/unclear, or vice versa. Only meaningful on
  // summary stages.
  if (
    (acKind === "confirm_order" || acKind === "cancel_order") &&
    (tiKind === "refused_or_stuck" || tiKind === "unclear")
  ) {
    pushCapped(acc.suspicious.ac_vs_ti_contradiction, t);
  }
}

function pushCapped(bucket, t, cap = 32) {
  bucket.count += 1;
  if (bucket.samples.length < cap) bucket.samples.push(t);
}

// ---------------------------------------------------------------------
// Reporting helpers.
// ---------------------------------------------------------------------
function pct(num, den) {
  if (!den) return "  —  ";
  return ((num / den) * 100).toFixed(1).padStart(5, " ") + "%";
}

function padRight(s, n) {
  const str = String(s);
  return str.length >= n ? str.slice(0, n) : str + " ".repeat(n - str.length);
}

function padLeft(s, n) {
  const str = String(s);
  return str.length >= n ? str : " ".repeat(n - str.length) + str;
}

function sortedCounts(map) {
  return [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function renderTable({ title, rows, columns, indent = "  " }) {
  const colWidths = columns.map((c, i) =>
    Math.max(
      c.label.length,
      ...rows.map((r) => String(r[i] ?? "").length),
    ),
  );
  const out = [];
  out.push(`${title}`);
  out.push("─".repeat(Math.min(80, title.length)));
  const header = columns
    .map((c, i) => (c.align === "right" ? padLeft(c.label, colWidths[i]) : padRight(c.label, colWidths[i])))
    .join("  ");
  out.push(indent + header);
  for (const row of rows) {
    const rendered = columns
      .map((c, i) => {
        const v = row[i] ?? "";
        return c.align === "right"
          ? padLeft(v, colWidths[i])
          : padRight(v, colWidths[i]);
      })
      .join("  ");
    out.push(indent + rendered);
  }
  return out.join("\n");
}

function renderReport(acc, { top = 3, minSamples = 0 } = {}) {
  const convCount = acc.byConversation.size;
  const emitCount = acc.emits.length;
  const out = [];

  out.push("[structured-output/proposer] analyzer report");
  out.push("=".repeat(60));
  out.push("");
  out.push(`  lines scanned:     ${acc.totalLines}`);
  out.push(`  emits parsed:      ${emitCount}`);
  out.push(`  conversations:     ${convCount}`);
  out.push(`  emit-failed lines: ${acc.emitFailed}`);
  out.push("");

  if (emitCount === 0) {
    out.push("No `[structured-output/proposer]` emits found in input.");
    return out.join("\n");
  }

  out.push(
    renderTable({
      title: "Schema versions",
      columns: [
        { label: "version", align: "left" },
        { label: "count", align: "right" },
        { label: "share", align: "right" },
      ],
      rows: sortedCounts(acc.schemaVersions).map(([k, v]) => [
        k,
        String(v),
        pct(v, emitCount),
      ]),
    }),
  );
  out.push("");

  out.push(
    renderTable({
      title: "Payload validity",
      columns: [
        { label: "bucket", align: "left" },
        { label: "count", align: "right" },
        { label: "share", align: "right" },
      ],
      rows: [
        ["present + valid", String(acc.payloadValidity.present_valid), pct(acc.payloadValidity.present_valid, emitCount)],
        ["present + invalid", String(acc.payloadValidity.present_invalid), pct(acc.payloadValidity.present_invalid, emitCount)],
        ["absent (no propose_turn_decision)", String(acc.payloadValidity.absent), pct(acc.payloadValidity.absent, emitCount)],
      ],
    }),
  );
  out.push("");

  // ti_classification + conformance.
  const tiRows = CLASSIFICATION_BUCKETS.map((b) => [
    b,
    String(acc.tiClassification.get(b) || 0),
    pct(acc.tiClassification.get(b) || 0, emitCount),
  ]);
  out.push(
    renderTable({
      title: "ti_classification  (turn_intent shadow, v1.2)",
      columns: [
        { label: "bucket", align: "left" },
        { label: "count", align: "right" },
        { label: "share", align: "right" },
      ],
      rows: tiRows,
    }),
  );
  const tiPresent = acc.tiClassification.get("present") || 0;
  const tiMissing = acc.tiClassification.get("missing") || 0;
  const tiDen = tiPresent + tiMissing;
  out.push("");
  out.push(
    `  conformance (present / (present + missing)): ${
      tiDen ? ((tiPresent / tiDen) * 100).toFixed(1) + "%" : "—"
    } (n=${tiDen})`,
  );
  out.push("");

  // ac_classification (same shape, free side-signal)
  const acRows = CLASSIFICATION_BUCKETS.map((b) => [
    b,
    String(acc.acClassification.get(b) || 0),
    pct(acc.acClassification.get(b) || 0, emitCount),
  ]);
  out.push(
    renderTable({
      title: "ac_classification  (awaiting_confirmation shadow, v1.1 — side-signal)",
      columns: [
        { label: "bucket", align: "left" },
        { label: "count", align: "right" },
        { label: "share", align: "right" },
      ],
      rows: acRows,
    }),
  );
  out.push("");

  // ti_kind distribution (over present rows).
  if (tiPresent > 0) {
    const tiKindRows = TURN_INTENT_KINDS.map((k) => [
      k,
      String(acc.tiKind.get(k) || 0),
      pct(acc.tiKind.get(k) || 0, tiPresent),
    ]);
    out.push(
      renderTable({
        title: `ti_kind distribution  (n=${tiPresent} rows with ti_classification=present)`,
        columns: [
          { label: "kind", align: "left" },
          { label: "count", align: "right" },
          { label: "share", align: "right" },
        ],
        rows: tiKindRows,
      }),
    );
    out.push("");

    const tiConfRows = TURN_INTENT_CONFIDENCES.map((c) => [
      c,
      String(acc.tiConfidence.get(c) || 0),
      pct(acc.tiConfidence.get(c) || 0, tiPresent),
    ]);
    out.push(
      renderTable({
        title: `ti_confidence distribution  (n=${tiPresent})`,
        columns: [
          { label: "confidence", align: "left" },
          { label: "count", align: "right" },
          { label: "share", align: "right" },
        ],
        rows: tiConfRows,
      }),
    );
    out.push("");
  }

  // addressed_fields coverage by stage.
  const stagesSeen = [...acc.fieldCoverage.keys()].filter(
    (s) => (acc.fieldCoverage.get(s)?.totalWithTi || 0) >= minSamples,
  );
  // Put the three expected stages first, then anything else.
  stagesSeen.sort((a, b) => {
    const ai = EXPECTED_TI_STAGES.indexOf(a);
    const bi = EXPECTED_TI_STAGES.indexOf(b);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return a.localeCompare(b);
  });
  if (stagesSeen.length > 0) {
    const header = ["field", ...stagesSeen.map((s) => shortenStage(s))];
    const rows = [];
    for (const field of TURN_INTENT_ADDRESSED_FIELDS) {
      const row = [field];
      for (const stage of stagesSeen) {
        const bucket = acc.fieldCoverage.get(stage);
        const hit = bucket.perField.get(field) || 0;
        const tot = bucket.totalWithTi;
        row.push(tot ? `${hit}/${tot} (${((hit / tot) * 100).toFixed(0)}%)` : "—");
      }
      rows.push(row);
    }
    const emptyRow = ["(empty)"];
    for (const stage of stagesSeen) {
      const bucket = acc.fieldCoverage.get(stage);
      const hit = bucket.empty;
      const tot = bucket.totalWithTi;
      emptyRow.push(tot ? `${hit}/${tot} (${((hit / tot) * 100).toFixed(0)}%)` : "—");
    }
    rows.push(emptyRow);
    out.push(
      renderTable({
        title: "addressed_fields coverage by stage (rows with ti_classification=present)",
        columns: header.map((h, i) => ({ label: h, align: i === 0 ? "left" : "right" })),
        rows,
      }),
    );
    out.push("");
  }

  // addressed_fields coverage by requested_slot (collection turns only).
  const rsSlots = [...acc.fieldCoverageByRequestedSlot.keys()]
    .filter((s) => s !== "-" && (acc.fieldCoverageByRequestedSlot.get(s)?.totalWithTi || 0) >= minSamples)
    .sort();
  if (rsSlots.length > 0) {
    const rsRows = rsSlots.map((rs) => {
      const bucket = acc.fieldCoverageByRequestedSlot.get(rs);
      const perFieldSorted = sortedCounts(bucket.perField).slice(0, 3);
      const topStr =
        perFieldSorted.length === 0
          ? "(empty)"
          : perFieldSorted.map(([f, c]) => `${f}:${c}`).join(" | ");
      return [
        rs,
        String(bucket.totalWithTi),
        String(bucket.empty),
        topStr,
      ];
    });
    out.push(
      renderTable({
        title: "addressed_fields coverage by requested_slot",
        columns: [
          { label: "requested_slot", align: "left" },
          { label: "n_ti", align: "right" },
          { label: "empty", align: "right" },
          { label: "top fields", align: "left" },
        ],
        rows: rsRows,
      }),
    );
    out.push("");
  }

  // kind × stage cross-tab (counts only, not rates, to keep signal honest).
  if (stagesSeen.length > 0) {
    const header = ["kind", ...stagesSeen.map((s) => shortenStage(s))];
    const rows = [];
    for (const kind of TURN_INTENT_KINDS) {
      const row = [kind];
      for (const stage of stagesSeen) {
        const inner = acc.kindByStage.get(stage);
        const hit = inner ? inner.get(kind) || 0 : 0;
        row.push(String(hit));
      }
      rows.push(row);
    }
    out.push(
      renderTable({
        title: "ti_kind × stage  (counts only)",
        columns: header.map((h, i) => ({ label: h, align: i === 0 ? "left" : "right" })),
        rows,
      }),
    );
    out.push("");
  }

  // Suspicious patterns.
  out.push("Suspicious patterns");
  out.push("=".repeat(60));
  out.push("");
  appendSuspiciousBucket(out, "A", "answered_full/answered_partial with empty addressed_fields", acc.suspicious.answered_but_empty_fields, top);
  appendSuspiciousBucket(out, "B", "acknowledgement/refused_or_stuck with non-empty addressed_fields", acc.suspicious.ack_or_refused_but_fields, top);
  appendSuspiciousBucket(out, "C", "clarifying_question with non-empty addressed_fields", acc.suspicious.clarifying_question_but_fields, top);
  appendSuspiciousBucket(out, "D", "corrected_prior with empty addressed_fields", acc.suspicious.corrected_prior_but_empty_fields, top);
  appendSuspiciousBucket(out, "E", "ti_classification=missing (expected stage, LLM omitted)", acc.suspicious.ti_missing_on_expected_stage, top);
  appendSuspiciousBucket(out, "F", "ti_classification=unexpected (non-expected stage, LLM volunteered)", acc.suspicious.ti_unexpected, top);
  appendSuspiciousBucket(out, "G", "v1.2 payload present but invalid", acc.suspicious.invalid_payload_v12, top);
  appendSuspiciousBucket(out, "H", "unknown token in ti_addressed_fields", acc.suspicious.unknown_token_in_addressed_fields, top);
  appendSuspiciousBucket(out, "I", "ac/ti cross-signal contradiction (confirm/cancel vs refused/unclear)", acc.suspicious.ac_vs_ti_contradiction, top);
  out.push("");

  // ac_kind distribution (summary-stage side-signal).
  const acPresent = acc.acClassification.get("present") || 0;
  if (acPresent > 0) {
    const rows = AWAITING_CONFIRMATION_KINDS.map((k) => [
      k,
      String(acc.acKind.get(k) || 0),
      pct(acc.acKind.get(k) || 0, acPresent),
    ]);
    out.push(
      renderTable({
        title: `ac_kind distribution  (n=${acPresent} rows with ac_classification=present)`,
        columns: [
          { label: "kind", align: "left" },
          { label: "count", align: "right" },
          { label: "share", align: "right" },
        ],
        rows,
      }),
    );
    out.push("");
  }

  // Validator errors (any bucket).
  if (acc.errorsObserved.size > 0) {
    const rows = sortedCounts(acc.errorsObserved)
      .slice(0, 20)
      .map(([e, c]) => [e, String(c)]);
    out.push(
      renderTable({
        title: "Validator errors observed (top 20)",
        columns: [
          { label: "error", align: "left" },
          { label: "count", align: "right" },
        ],
        rows,
      }),
    );
    out.push("");
  }

  return out.join("\n");
}

function shortenStage(stage) {
  if (stage === "collecting_booking_details") return "collect";
  if (stage === "summary_shown") return "summary";
  if (stage === "awaiting_confirmation") return "awaiting";
  if (stage === "-" || !stage) return "(none)";
  return stage;
}

function appendSuspiciousBucket(out, letter, label, bucket, top) {
  const count = bucket.count;
  out.push(`${letter}. ${label}: ${count} rows`);
  if (count === 0) return;
  const show = Math.min(top, bucket.samples.length);
  for (let i = 0; i < show; i += 1) {
    out.push("   " + compactEmitSample(bucket.samples[i]));
  }
  if (count > show) {
    out.push(`   … (+${count - show} more)`);
  }
}

function compactEmitSample(t) {
  const keepKeys = [
    "conversation",
    "turn_id",
    "stage",
    "requested_slot",
    "schema_version",
    "ti_kind",
    "ti_confidence",
    "ti_classification",
    "ti_addressed_fields",
    "ac_kind",
    "ac_classification",
    "errors",
  ];
  const parts = [];
  for (const k of keepKeys) {
    if (t[k] === undefined) continue;
    const v = Array.isArray(t[k]) ? `[${t[k].join("|")}]` : t[k];
    parts.push(`${k}=${v}`);
  }
  return parts.join(" ");
}

// ---------------------------------------------------------------------
// JSON shape.
// ---------------------------------------------------------------------
function toJson(acc) {
  const mapToObj = (m) => Object.fromEntries([...m.entries()]);
  const nestedToObj = (m) =>
    Object.fromEntries([...m.entries()].map(([k, v]) => [k, mapToObj(v)]));
  const coverageToObj = (m) =>
    Object.fromEntries(
      [...m.entries()].map(([k, v]) => [
        k,
        {
          totalWithTi: v.totalWithTi,
          empty: v.empty,
          perField: mapToObj(v.perField),
        },
      ]),
    );
  return {
    totals: {
      lines_scanned: acc.totalLines,
      emits_parsed: acc.emits.length,
      conversations: acc.byConversation.size,
      emit_failed_lines: acc.emitFailed,
    },
    schema_versions: mapToObj(acc.schemaVersions),
    payload_validity: { ...acc.payloadValidity },
    ti_classification: Object.fromEntries(
      CLASSIFICATION_BUCKETS.map((b) => [b, acc.tiClassification.get(b) || 0]),
    ),
    ac_classification: Object.fromEntries(
      CLASSIFICATION_BUCKETS.map((b) => [b, acc.acClassification.get(b) || 0]),
    ),
    ti_kind: Object.fromEntries(
      TURN_INTENT_KINDS.map((k) => [k, acc.tiKind.get(k) || 0]),
    ),
    ti_confidence: Object.fromEntries(
      TURN_INTENT_CONFIDENCES.map((c) => [c, acc.tiConfidence.get(c) || 0]),
    ),
    ac_kind: Object.fromEntries(
      AWAITING_CONFIRMATION_KINDS.map((k) => [k, acc.acKind.get(k) || 0]),
    ),
    field_coverage_by_stage: coverageToObj(acc.fieldCoverage),
    field_coverage_by_requested_slot: coverageToObj(acc.fieldCoverageByRequestedSlot),
    kind_by_stage: nestedToObj(acc.kindByStage),
    kind_by_requested_slot: nestedToObj(acc.kindByRequestedSlot),
    errors_observed: mapToObj(acc.errorsObserved),
    suspicious: Object.fromEntries(
      Object.entries(acc.suspicious).map(([name, bucket]) => [
        name,
        {
          count: bucket.count,
          samples: bucket.samples.map(compactEmitSampleObj),
        },
      ]),
    ),
  };
}

function compactEmitSampleObj(t) {
  return {
    conversation: t.conversation,
    turn_id: t.turn_id,
    stage: t.stage,
    requested_slot: t.requested_slot,
    schema_version: t.schema_version,
    ti_kind: t.ti_kind,
    ti_confidence: t.ti_confidence,
    ti_classification: t.ti_classification,
    ti_addressed_fields: t.ti_addressed_fields,
    ac_kind: t.ac_kind,
    ac_classification: t.ac_classification,
    errors: t.errors,
  };
}

// ---------------------------------------------------------------------
// CLI driver.
// ---------------------------------------------------------------------
async function readLines(file) {
  const input = file ? fs.createReadStream(file) : process.stdin;
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  const lines = [];
  for await (const raw of rl) {
    lines.push(raw);
  }
  return lines;
}

function parseArgs(argv) {
  const args = {
    file: null,
    json: false,
    top: 3,
    minSamples: 0,
    conv: null,
    selftest: false,
  };
  for (const a of argv) {
    if (a === "--json") args.json = true;
    else if (a === "--selftest") args.selftest = true;
    else if (a.startsWith("--top=")) args.top = Math.max(0, parseInt(a.slice(6), 10) || 0);
    else if (a.startsWith("--min-samples=")) args.minSamples = Math.max(0, parseInt(a.slice(14), 10) || 0);
    else if (a.startsWith("--conv=")) args.conv = a.slice(7);
    else if (!a.startsWith("--")) args.file = a;
  }
  return args;
}

function analyze(lines, { conv = null } = {}) {
  const acc = makeAccumulator();
  for (const raw of lines) {
    const parsed = parseLine(raw);
    if (!parsed) continue;
    if (parsed.kind === "emit" && conv && parsed.tokens.conversation !== conv) {
      continue;
    }
    record(acc, parsed);
  }
  return acc;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selftest) {
    runSelfTest();
    return;
  }
  const lines = await readLines(args.file);
  const acc = analyze(lines, { conv: args.conv });
  if (args.json) {
    process.stdout.write(JSON.stringify(toJson(acc), null, 2) + "\n");
    return;
  }
  process.stdout.write(
    renderReport(acc, { top: args.top, minSamples: args.minSamples }) + "\n",
  );
}

// ---------------------------------------------------------------------
// Self-test. Runs a small synthetic corpus through the analyzer and
// checks expected counts. Used by
// smoke-test-analyze-structured-output-proposer.mjs so the analyzer
// stays in sync with the emit shape.
// ---------------------------------------------------------------------
function buildSyntheticCorpus() {
  const base = (over = {}) => ({
    conversation: over.conversation || "C1",
    stage: over.stage || "collecting_booking_details",
    requested_slot: over.requested_slot || "-",
    present: over.present ?? "true",
    schema_valid: over.schema_valid ?? "true",
    schema_version: over.schema_version || "1.2",
    turn_kind: over.turn_kind || "booking_detail_collection",
    pricing_action: over.pricing_action || "none",
    planned_tool_calls: over.planned_tool_calls || [],
    fired_tool_ops: over.fired_tool_ops || [],
    get_price_fired: over.get_price_fired || "false",
    plan_vs_fire: over.plan_vs_fire || "aligned",
    ac_stage: over.ac_stage || "false",
    ac_kind: over.ac_kind || "-",
    ac_classification: over.ac_classification || "n/a",
    ti_stage: over.ti_stage || "true",
    ti_kind: over.ti_kind || "answered_full",
    ti_confidence: over.ti_confidence || "high",
    ti_addressed_fields_count:
      over.ti_addressed_fields_count !== undefined
        ? over.ti_addressed_fields_count
        : (over.ti_addressed_fields?.length ?? 1),
    ti_addressed_fields: over.ti_addressed_fields || ["sender_name"],
    ti_classification: over.ti_classification || "present",
    duplicate_count: over.duplicate_count || "1",
    turn_id: over.turn_id || "T1",
    errors: over.errors || "-",
  });
  const serialize = (t) => {
    const parts = [];
    for (const [k, v] of Object.entries(t)) {
      if (Array.isArray(v)) parts.push(`${k}=[${v.join("|")}]`);
      else parts.push(`${k}=${v}`);
    }
    return `2026-04-22T10:00:00Z riders-delivery: [structured-output/proposer] ${parts.join(" ")}`;
  };
  const rows = [
    // collection — answered_full with sender_name
    base({ conversation: "C1", turn_id: "T1", requested_slot: "sender_name" }),
    // collection — answered_partial, gave phone only on combined ask
    base({
      conversation: "C1",
      turn_id: "T2",
      requested_slot: "sender_name",
      ti_kind: "answered_partial",
      ti_addressed_fields: ["sender_phone"],
    }),
    // collection — acknowledgement (lol / thanks), no fields — healthy
    base({
      conversation: "C1",
      turn_id: "T3",
      ti_kind: "acknowledgement",
      ti_addressed_fields: [],
    }),
    // SUSPICIOUS A: answered_full but empty fields
    base({
      conversation: "C1",
      turn_id: "T4",
      ti_kind: "answered_full",
      ti_addressed_fields: [],
    }),
    // SUSPICIOUS B: acknowledgement with fields
    base({
      conversation: "C1",
      turn_id: "T5",
      ti_kind: "acknowledgement",
      ti_addressed_fields: ["sender_phone"],
    }),
    // summary — confirm_order + answered_full (healthy)
    base({
      conversation: "C2",
      turn_id: "T1",
      stage: "summary_shown",
      ac_stage: "true",
      ac_kind: "confirm_order",
      ac_classification: "present",
      ti_kind: "answered_full",
      ti_addressed_fields: [],
    }),
    // SUSPICIOUS I: ac says confirm, ti says refused
    base({
      conversation: "C2",
      turn_id: "T2",
      stage: "awaiting_confirmation",
      ac_stage: "true",
      ac_kind: "confirm_order",
      ac_classification: "present",
      ti_kind: "refused_or_stuck",
      ti_addressed_fields: [],
    }),
    // ti missing on expected stage
    base({
      conversation: "C3",
      turn_id: "T1",
      stage: "collecting_booking_details",
      ti_stage: "true",
      ti_kind: "-",
      ti_confidence: "-",
      ti_addressed_fields: [],
      ti_addressed_fields_count: 0,
      ti_classification: "missing",
    }),
    // ti unexpected on non-expected stage
    base({
      conversation: "C3",
      turn_id: "T2",
      stage: "quoted",
      ti_stage: "false",
      ti_kind: "clarifying_question",
      ti_classification: "unexpected",
      ti_addressed_fields: [],
    }),
    // legacy v1.1 row — no ti_* at all (emulate by writing minimal line)
    "2026-04-22T10:00:00Z riders-delivery: [structured-output/proposer] " +
      "conversation=C4 stage=collecting_booking_details requested_slot=- present=true schema_valid=true schema_version=1.1 turn_kind=booking_detail_collection pricing_action=none planned_tool_calls=[] fired_tool_ops=[] get_price_fired=false plan_vs_fire=aligned ac_stage=false ac_kind=- ac_classification=n/a duplicate_count=1 turn_id=T1 errors=-",
    // emit_failed line (should be counted but not contribute to emits)
    "2026-04-22T10:00:00Z riders-delivery: [structured-output/proposer] emit failed conversation=C5 error=RangeError",
    // v1.2 payload invalid
    base({
      conversation: "C6",
      turn_id: "T1",
      stage: "collecting_booking_details",
      schema_valid: "false",
      errors: "turn_intent.kind_invalid:answered_sideways",
      ti_kind: "-",
      ti_confidence: "-",
      ti_classification: "missing",
      ti_addressed_fields: [],
    }),
  ];
  return rows.map((r) => (typeof r === "string" ? r : serialize(r)));
}

function runSelfTest() {
  const assert = (cond, msg) => {
    if (!cond) {
      process.stderr.write(`SELFTEST FAIL: ${msg}\n`);
      process.exit(1);
    }
  };
  const lines = buildSyntheticCorpus();
  const acc = analyze(lines);

  // Totals: 12 input lines — 11 structured emits + 1 emit_failed.
  assert(acc.totalLines === 12, `expected totalLines=12, got ${acc.totalLines}`);
  assert(acc.emits.length === 11, `expected 11 emits, got ${acc.emits.length}`);
  assert(acc.emitFailed === 1, `expected 1 emit-failed line, got ${acc.emitFailed}`);
  assert(acc.byConversation.size === 5, `expected 5 conversations, got ${acc.byConversation.size}`);

  // Schema versions: 10 × 1.2, 1 × 1.1.
  assert(acc.schemaVersions.get("1.2") === 10, `expected 10 v1.2 rows, got ${acc.schemaVersions.get("1.2")}`);
  assert(acc.schemaVersions.get("1.1") === 1, `expected 1 v1.1 row, got ${acc.schemaVersions.get("1.1")}`);

  // Payload validity.
  assert(acc.payloadValidity.present_valid === 10, `expected 10 valid, got ${acc.payloadValidity.present_valid}`);
  assert(acc.payloadValidity.present_invalid === 1, `expected 1 invalid, got ${acc.payloadValidity.present_invalid}`);
  assert(acc.payloadValidity.absent === 0, `expected 0 absent, got ${acc.payloadValidity.absent}`);

  // ti_classification bucket rates.
  //   present: 7 (C1T1..T5, C2T1, C2T2)
  //   missing: 2 (C3T1, C6T1)
  //   unexpected: 1 (C3T2)
  //   n/a: 1 (C4 v1.1 — ti_classification absent, treated as n/a)
  assert(acc.tiClassification.get("present") === 7, `expected ti present=7, got ${acc.tiClassification.get("present")}`);
  assert(acc.tiClassification.get("missing") === 2, `expected ti missing=2, got ${acc.tiClassification.get("missing")}`);
  assert(acc.tiClassification.get("unexpected") === 1, `expected ti unexpected=1, got ${acc.tiClassification.get("unexpected")}`);
  assert((acc.tiClassification.get("n/a") || 0) === 1, `expected ti n/a=1, got ${acc.tiClassification.get("n/a")}`);

  // ac_classification: 2 present (C2T1, C2T2), rest n/a.
  assert(acc.acClassification.get("present") === 2, `expected ac present=2, got ${acc.acClassification.get("present")}`);

  // ti_kind distribution (over 7 present rows):
  //   answered_full: 3 (C1T1, C1T4, C2T1)
  //   answered_partial: 1 (C1T2)
  //   acknowledgement: 2 (C1T3, C1T5)
  //   refused_or_stuck: 1 (C2T2)
  assert(acc.tiKind.get("answered_full") === 3, `expected answered_full=3, got ${acc.tiKind.get("answered_full")}`);
  assert(acc.tiKind.get("answered_partial") === 1, `got ${acc.tiKind.get("answered_partial")}`);
  assert(acc.tiKind.get("acknowledgement") === 2, `got ${acc.tiKind.get("acknowledgement")}`);
  assert(acc.tiKind.get("refused_or_stuck") === 1, `got ${acc.tiKind.get("refused_or_stuck")}`);

  // Field coverage by stage: collecting_booking_details has 5 present rows.
  const collBucket = acc.fieldCoverage.get("collecting_booking_details");
  assert(collBucket, "expected collecting_booking_details bucket");
  assert(collBucket.totalWithTi === 5, `expected 5 ti-present rows in collecting, got ${collBucket.totalWithTi}`);
  assert(collBucket.perField.get("sender_name") === 1, `expected sender_name=1 in collecting, got ${collBucket.perField.get("sender_name")}`);
  assert(collBucket.perField.get("sender_phone") === 2, `expected sender_phone=2 in collecting (partial + suspB), got ${collBucket.perField.get("sender_phone")}`);
  assert(collBucket.empty === 2, `expected 2 empty-fields rows in collecting (ack + suspA), got ${collBucket.empty}`);

  // Suspicious patterns.
  //   suspA fires on every answered_full/answered_partial row with
  //   addressed_fields=[]. In the synthetic corpus that's C1T4 (collecting)
  //   and C2T1 (summary stage confirm-turn with no fields named), so 2.
  assert(acc.suspicious.answered_but_empty_fields.count === 2, `expected 2 suspA, got ${acc.suspicious.answered_but_empty_fields.count}`);
  assert(acc.suspicious.ack_or_refused_but_fields.count === 1, `expected 1 suspB, got ${acc.suspicious.ack_or_refused_but_fields.count}`);
  assert(acc.suspicious.clarifying_question_but_fields.count === 0, `expected 0 suspC, got ${acc.suspicious.clarifying_question_but_fields.count}`);
  assert(acc.suspicious.corrected_prior_but_empty_fields.count === 0, `expected 0 suspD, got ${acc.suspicious.corrected_prior_but_empty_fields.count}`);
  assert(acc.suspicious.ti_missing_on_expected_stage.count === 2, `expected 2 missE, got ${acc.suspicious.ti_missing_on_expected_stage.count}`);
  assert(acc.suspicious.ti_unexpected.count === 1, `expected 1 suspF, got ${acc.suspicious.ti_unexpected.count}`);
  assert(acc.suspicious.invalid_payload_v12.count === 1, `expected 1 suspG, got ${acc.suspicious.invalid_payload_v12.count}`);
  assert(acc.suspicious.ac_vs_ti_contradiction.count === 1, `expected 1 suspI, got ${acc.suspicious.ac_vs_ti_contradiction.count}`);
  assert(acc.suspicious.unknown_token_in_addressed_fields.count === 0, `expected 0 suspH, got ${acc.suspicious.unknown_token_in_addressed_fields.count}`);

  // Errors observed contains validator errors.
  assert(
    [...acc.errorsObserved.keys()].some((k) => k.startsWith("turn_intent.kind_invalid")),
    "expected to see turn_intent.kind_invalid in errors",
  );

  // Report rendering should not crash and should include key section headings.
  const report = renderReport(acc, { top: 2 });
  for (const needle of [
    "ti_classification",
    "ti_kind distribution",
    "addressed_fields coverage by stage",
    "Suspicious patterns",
  ]) {
    assert(report.includes(needle), `report missing heading: ${needle}`);
  }

  // JSON roundtrip should include all top-level keys and be JSON-parseable.
  const jsonStr = JSON.stringify(toJson(acc));
  const parsed = JSON.parse(jsonStr);
  for (const needle of [
    "totals",
    "schema_versions",
    "payload_validity",
    "ti_classification",
    "ac_classification",
    "ti_kind",
    "ti_confidence",
    "field_coverage_by_stage",
    "field_coverage_by_requested_slot",
    "kind_by_stage",
    "errors_observed",
    "suspicious",
  ]) {
    assert(needle in parsed, `JSON missing key: ${needle}`);
  }
  // Conv filter — only C1 should survive.
  const filtered = analyze(lines, { conv: "C1" });
  assert(filtered.byConversation.size === 1, `conv filter expected 1 conv, got ${filtered.byConversation.size}`);
  assert(filtered.emits.length === 5, `conv filter expected 5 emits, got ${filtered.emits.length}`);

  process.stdout.write("selftest OK\n");
}

// ---------------------------------------------------------------------
// Export for the smoke test.
// ---------------------------------------------------------------------
export {
  parseLine,
  analyze,
  renderReport,
  toJson,
  buildSyntheticCorpus,
  TURN_INTENT_KINDS,
  TURN_INTENT_ADDRESSED_FIELDS,
  CLASSIFICATION_BUCKETS,
};

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    process.stderr.write(`analyze-structured-output-proposer: ${err && err.stack ? err.stack : String(err)}\n`);
    process.exit(1);
  });
}
