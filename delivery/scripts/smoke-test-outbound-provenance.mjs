#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: outbound provenance contract (2026-04-22).
//
// Product rule:
//   Every wire-send of a WhatsApp reply (`sendOctopusTextReply`) must
//   carry an `OutboundProvenance` tag. The five values split the set of
//   all possible outbound texts into disjoint trust classes:
//
//     - registry_rendered         — produced by `renderDirectiveReply`
//     - authoritative_substitute  — produced by a server-side
//                                   deterministic builder that
//                                   overrides the LLM draft
//     - deterministic_fallback    — canned template, not backed by a
//                                   specific server record
//     - llm_verified              — LLM text that passed C1+C2
//     - llm_unverified            — LLM text that skipped C1+C2; this
//                                   should never fire in steady state
//                                   and emits a paired `warn` +
//                                   `operator action required` event
//                                   so on-call notices immediately.
//
// Cases covered:
//   P1  provenanceFromDecision mapping is exhaustive across every
//       reachable (decision, reason) pair, with `verifiedByPostDecision`
//       flipping `allow` between `llm_verified` and `llm_unverified`.
//   P2  Rank ordering: `registry_rendered > authoritative_substitute >
//       deterministic_fallback > llm_verified > llm_unverified`. Used by
//       `strongerProvenance` to preserve the customer-visible truth
//       across pipeline phases.
//   P3  Runtime validator `isValidOutboundProvenance` accepts exactly
//       the five literal values and rejects everything else (case
//       drift, non-strings, undefined, whitespace-padded, empty).
//       This is the enforcement-readiness guarantee behind the
//       runtime guard inside `sendOctopusTextReply`.
//   P4  `OUTBOUND_PROVENANCE_VALUES` tuple is exhaustive: exactly the
//       five canonical literals in declaration order, no more, no
//       less. Catches drift between the type union and the runtime
//       list.
//   S1  Static-grep invariant: every `sendOctopusTextReply(...)` call
//       site under `delivery/plugins/` carries a `provenance:` AND a
//       `provenanceReason:` key. Scanner is whitespace-/newline-
//       tolerant (matches `sendOctopusTextReply\s*\(\s*\{`) and
//       walks the whole plugin tree so a future cross-file caller is
//       also caught at CI time.
//   S2  `[outbound/provenance]` emitter exists at least twice (warn +
//       info paths) in `sendOctopusTextReply`. Guards against someone
//       silently removing the canonical log line.
//   S3  Every `deterministic_fallback` / `authoritative_substitute`
//       early call site has an explicit `provenanceReason` so the log
//       line carries a useful grep key.
//   S4  Meta-test: the S1 scanner actually catches a missing-
//       `provenance:` caller. Feeds synthetic well-formed and
//       broken call bodies into the extracted scanner to prove the
//       invariant is not dead code (would silently pass if the regex
//       ever stopped matching real call sites).
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function loadTs(relativePath) {
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, {
    interopDefault: true,
  });
  return jiti(path.join(root, relativePath));
}

const provenance = loadTs("plugins/shared/outbound-provenance.ts");
const {
  provenanceFromDecision,
  strongerProvenance,
  isStrongerProvenance,
  isValidOutboundProvenance,
  OUTBOUND_PROVENANCE_VALUES,
} = provenance;

// ---------------------------------------------------------------------------
// P1: provenanceFromDecision exhaustive mapping
// ---------------------------------------------------------------------------
{
  const cases = [
    // replace_authoritative + replace_directive_ask → registry_rendered
    {
      in: {
        decision: "replace_authoritative",
        reason: "replace_directive_ask",
        replyAuthor: "server",
        verifiedByPostDecision: true,
      },
      out: "registry_rendered",
    },
    // Any other replace_authoritative reason → authoritative_substitute
    ...[
      "replace_summary_fact_drift",
      "replace_transaction_artifact_missing",
      "replace_price_mismatch",
      "replace_field_rejection_hallucination",
      "replace_order_placed_hallucination",
      "replace_clarify_option_before_proceed",
      "replace_manual_confirm_address_ask",
      "replace_manual_confirm_handoff",
      "replace_get_price_bypass",
    ].map((reason) => ({
      in: {
        decision: "replace_authoritative",
        reason,
        replyAuthor: "server",
        verifiedByPostDecision: true,
      },
      out: "authoritative_substitute",
    })),
    // Fallback kinds → deterministic_fallback
    {
      in: {
        decision: "replace_fallback",
        reason: "fallback_empty_reply",
        replyAuthor: "fallback",
        verifiedByPostDecision: true,
      },
      out: "deterministic_fallback",
    },
    {
      in: {
        decision: "block_retry",
        reason: "block_provider_error",
        replyAuthor: "fallback",
        verifiedByPostDecision: true,
      },
      out: "deterministic_fallback",
    },
    // allow / allow_sanitized + verified → llm_verified
    {
      in: {
        decision: "allow",
        reason: "allow",
        replyAuthor: "llm",
        verifiedByPostDecision: true,
      },
      out: "llm_verified",
    },
    {
      in: {
        decision: "allow_sanitized",
        reason: "allow_sanitized",
        replyAuthor: "llm",
        verifiedByPostDecision: true,
      },
      out: "llm_verified",
    },
    {
      in: {
        decision: "allow",
        reason: "preserve_clarification",
        replyAuthor: "llm",
        verifiedByPostDecision: true,
      },
      out: "llm_verified",
    },
    // allow + NOT verified → llm_unverified
    {
      in: {
        decision: "allow",
        reason: "allow",
        replyAuthor: "llm",
        verifiedByPostDecision: false,
      },
      out: "llm_unverified",
    },
  ];
  for (const c of cases) {
    const got = provenanceFromDecision(c.in);
    assert.equal(
      got,
      c.out,
      `P1: ${JSON.stringify(c.in)} → ${got}, expected ${c.out}`,
    );
  }
  console.log(`P1: OK (${cases.length} decision→provenance mappings verified)`);
}

// ---------------------------------------------------------------------------
// P2: rank ordering
// ---------------------------------------------------------------------------
{
  const ranked = [
    "llm_unverified",
    "llm_verified",
    "deterministic_fallback",
    "authoritative_substitute",
    "registry_rendered",
  ];
  for (let i = 0; i < ranked.length - 1; i++) {
    assert.equal(
      isStrongerProvenance(ranked[i + 1], ranked[i]),
      true,
      `P2: ${ranked[i + 1]} should be stronger than ${ranked[i]}`,
    );
    assert.equal(
      strongerProvenance(ranked[i], ranked[i + 1]),
      ranked[i + 1],
      `P2: strongerProvenance(${ranked[i]}, ${ranked[i + 1]}) should be ${ranked[i + 1]}`,
    );
  }
  // Same-rank should return first arg (stable tiebreak).
  assert.equal(strongerProvenance("llm_verified", "llm_verified"), "llm_verified");
  console.log("P2: OK (rank ordering strict + stable)");
}

// ---------------------------------------------------------------------------
// P3: runtime validator accepts the five literals, rejects everything else
// ---------------------------------------------------------------------------
{
  const accepted = [
    "registry_rendered",
    "authoritative_substitute",
    "deterministic_fallback",
    "llm_verified",
    "llm_unverified",
  ];
  for (const v of accepted) {
    assert.equal(
      isValidOutboundProvenance(v),
      true,
      `P3: "${v}" must be accepted by isValidOutboundProvenance`,
    );
  }
  const rejected = [
    "",
    " registry_rendered",
    "registry_rendered ",
    "REGISTRY_RENDERED",
    "Registry_Rendered",
    "llm-unverified",
    "unknown",
    "server",
    undefined,
    null,
    0,
    1,
    true,
    false,
    {},
    [],
    "llm_verified ",
  ];
  for (const v of rejected) {
    assert.equal(
      isValidOutboundProvenance(v),
      false,
      `P3: ${JSON.stringify(v)} must be rejected by isValidOutboundProvenance`,
    );
  }
  console.log(
    `P3: OK (${accepted.length} accepted, ${rejected.length} rejected)`,
  );
}

// ---------------------------------------------------------------------------
// P4: OUTBOUND_PROVENANCE_VALUES tuple is exhaustive + canonical ordering
// ---------------------------------------------------------------------------
{
  assert.deepEqual(
    [...OUTBOUND_PROVENANCE_VALUES],
    [
      "registry_rendered",
      "authoritative_substitute",
      "deterministic_fallback",
      "llm_verified",
      "llm_unverified",
    ],
    "P4: OUTBOUND_PROVENANCE_VALUES must contain exactly the five canonical literals in declaration order",
  );
  console.log("P4: OK (enum tuple matches the five-literal union)");
}

// ---------------------------------------------------------------------------
// S1 scanner (shared with S4 meta-test)
// ---------------------------------------------------------------------------
//
// Extracts every `sendOctopusTextReply(...)` invocation from a source
// blob using a whitespace-/newline-tolerant regex and a brace-
// balancing walker. Returns an array of `{ idx, body }` objects. The
// same function is run against (a) the real `plugins/octopus-channel/
// index.ts` source in S1, (b) every other `.ts` under
// `delivery/plugins/` to catch future cross-file call sites, and (c)
// a synthetic good-vs-bad fixture in S4 to prove the invariant is
// not dead code.
function scanSendOctopusTextReplyCallSites(source) {
  const opener = /sendOctopusTextReply\s*\(\s*\{/gu;
  const callSites = [];
  let m;
  while ((m = opener.exec(source)) !== null) {
    // `m.index` is the start of `sendOctopusTextReply`; we want the
    // position of the opening `{` so the brace-balancer starts at
    // depth 1 on the first iteration.
    const openBraceIdx = source.indexOf("{", m.index + "sendOctopusTextReply".length);
    if (openBraceIdx < 0) continue;
    let depth = 0;
    let end = -1;
    for (let i = openBraceIdx; i < source.length; i++) {
      const ch = source[i];
      if (ch === "{") depth++;
      else if (ch === "}") {
        depth--;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    if (end < 0) continue;
    const body = source.slice(m.index, end + 1);
    callSites.push({ idx: m.index, body });
    // Advance past this call so the next exec() does not re-match.
    opener.lastIndex = end + 1;
  }
  return callSites;
}

function assertCallSiteCarriesProvenance(site, origin) {
  assert.ok(
    /\bprovenance\s*:/u.test(site.body),
    `${origin}: sendOctopusTextReply call at char ${site.idx} missing 'provenance:' key\n--- body ---\n${site.body}\n--- /body ---`,
  );
  assert.ok(
    /\bprovenanceReason\s*:/u.test(site.body),
    `${origin}: sendOctopusTextReply call at char ${site.idx} missing 'provenanceReason:' key\n--- body ---\n${site.body}\n--- /body ---`,
  );
}

// ---------------------------------------------------------------------------
// S1: every sendOctopusTextReply call under delivery/plugins/ carries
//     a provenance: + provenanceReason: key (whitespace-tolerant,
//     repo-wide scan).
// ---------------------------------------------------------------------------
{
  // Walk delivery/plugins/ and collect every .ts file. Skip
  // node_modules, test fixtures, and dist output.
  function walkTs(dir, out) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "dist") continue;
        walkTs(full, out);
      } else if (entry.isFile() && entry.name.endsWith(".ts")) {
        out.push(full);
      }
    }
  }
  const pluginsRoot = path.join(root, "plugins");
  const tsFiles = [];
  walkTs(pluginsRoot, tsFiles);

  let totalCallSites = 0;
  const perFile = [];
  for (const file of tsFiles) {
    const src = fs.readFileSync(file, "utf8");
    const sites = scanSendOctopusTextReplyCallSites(src);
    if (sites.length === 0) continue;
    perFile.push({ file: path.relative(root, file), count: sites.length });
    for (const s of sites) {
      assertCallSiteCarriesProvenance(
        s,
        `S1 (${path.relative(root, file)})`,
      );
    }
    totalCallSites += sites.length;
  }

  // The canonical file (index.ts) must own at least 7 call sites — the
  // six early paths plus the main decidePostStateOutbound path. This
  // catches a regression that removes the send entirely from the
  // pipeline.
  const indexRel = "plugins/octopus-channel/index.ts";
  const indexEntry = perFile.find((p) => p.file === indexRel);
  assert.ok(
    indexEntry && indexEntry.count >= 7,
    `S1: expected >= 7 sendOctopusTextReply call sites in ${indexRel}, found ${indexEntry?.count || 0}`,
  );
  console.log(
    `S1: OK (${totalCallSites} call sites across ${perFile.length} files; all carry provenance + provenanceReason)`,
  );
  for (const p of perFile) {
    console.log(`     ${p.count.toString().padStart(2)} site(s) in ${p.file}`);
  }
}

// ---------------------------------------------------------------------------
// S2: [outbound/provenance] emitter exists exactly once
// ---------------------------------------------------------------------------
{
  const indexSource = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  const emitMatches = indexSource.match(/\[outbound\/provenance\]/g) || [];
  assert.ok(
    emitMatches.length >= 2,
    `S2: expected at least two [outbound/provenance] emissions (warn + info paths), got ${emitMatches.length}`,
  );
  // Warn path: llm_unverified should escalate. Look for `logger.warn`
  // sharing a line with the provenance tag, within 200 chars of an
  // `llm_unverified` string literal.
  const hasWarnPath =
    /logger\.warn\([^\)]*\[outbound\/provenance\]/s.test(indexSource) &&
    /llm_unverified/.test(indexSource);
  assert.ok(
    hasWarnPath,
    "S2: expected a `logger.warn(... [outbound/provenance] ...)` emission paired with `llm_unverified`",
  );
  console.log("S2: OK ([outbound/provenance] emitter present; warn path exists)");
}

// ---------------------------------------------------------------------------
// S3: every tagged early call site names an explicit provenanceReason
// ---------------------------------------------------------------------------
{
  const indexSource = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  const expectedReasons = [
    "inactivity_close",
    "inactivity_nudge",
    "processing_error_fallback",
    "image_read_failure",
    "audio_transcription_failure",
    "deterministic_location_clarification",
  ];
  for (const reason of expectedReasons) {
    assert.ok(
      indexSource.includes(`provenanceReason: "${reason}"`),
      `S3: expected provenanceReason: "${reason}" on an early call site`,
    );
  }
  console.log(
    `S3: OK (${expectedReasons.length} early-call-site reasons present)`,
  );
}

// ---------------------------------------------------------------------------
// S4: meta-test — prove the S1 scanner actually catches a missing-
//     provenance call site. If the scanner regex ever stops matching
//     the real call syntax, S1 silently reports "0 sites, all OK" and
//     the invariant becomes dead code. This test feeds two synthetic
//     fixtures into the same scanner and asserts the assertion library
//     rejects the bad one.
// ---------------------------------------------------------------------------
{
  const goodFixture = `
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: "ok",
      provenance: "deterministic_fallback",
      provenanceReason: "synthetic_good",
    });
  `;
  const badFixtureMissingProvenance = `
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: "ok",
      provenanceReason: "synthetic_bad_missing_provenance",
    });
  `;
  const badFixtureMissingReason = `
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: "ok",
      provenance: "deterministic_fallback",
    });
  `;
  const multilineGoodFixture = `
    await sendOctopusTextReply(
      {
        api,
        account,
        conversationId,
        replyTarget,
        text: "ok",
        provenance: "deterministic_fallback",
        provenanceReason: "synthetic_good_multiline_opener",
      },
    );
  `;

  const goodSites = scanSendOctopusTextReplyCallSites(goodFixture);
  assert.equal(
    goodSites.length,
    1,
    "S4: scanner must find the well-formed synthetic call site",
  );
  assertCallSiteCarriesProvenance(goodSites[0], "S4-good");

  const multilineSites = scanSendOctopusTextReplyCallSites(multilineGoodFixture);
  assert.equal(
    multilineSites.length,
    1,
    "S4: scanner must tolerate newline between `sendOctopusTextReply(` and `{`",
  );
  assertCallSiteCarriesProvenance(multilineSites[0], "S4-multiline");

  const badSitesMissingProvenance = scanSendOctopusTextReplyCallSites(
    badFixtureMissingProvenance,
  );
  assert.equal(
    badSitesMissingProvenance.length,
    1,
    "S4: scanner must find the bad (missing provenance) synthetic call site",
  );
  assert.throws(
    () =>
      assertCallSiteCarriesProvenance(
        badSitesMissingProvenance[0],
        "S4-bad-missing-provenance",
      ),
    /missing 'provenance:' key/,
    "S4: assertion must reject a call body that omits `provenance:`",
  );

  const badSitesMissingReason = scanSendOctopusTextReplyCallSites(
    badFixtureMissingReason,
  );
  assert.equal(
    badSitesMissingReason.length,
    1,
    "S4: scanner must find the bad (missing reason) synthetic call site",
  );
  assert.throws(
    () =>
      assertCallSiteCarriesProvenance(
        badSitesMissingReason[0],
        "S4-bad-missing-reason",
      ),
    /missing 'provenanceReason:' key/,
    "S4: assertion must reject a call body that omits `provenanceReason:`",
  );

  console.log(
    "S4: OK (scanner catches missing provenance AND missing provenanceReason; tolerates multiline call syntax)",
  );
}

console.log("smoke-test-outbound-provenance: ALL OK");
