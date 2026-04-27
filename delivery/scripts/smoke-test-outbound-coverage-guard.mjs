// Smoke test for the outbound coverage-claim guard (Phase B, log-only).
//
// Run from `delivery/` with:
//   node scripts/smoke-test-outbound-coverage-guard.mjs
//
// Compiles `plugins/shared/outbound-coverage-guard.ts` on the fly via a
// one-shot tsc invocation, then exercises:
//
//   1. Detector
//      - EN positive: "we deliver to Khaldiya"         → detected
//      - EN positive: "yes we cover Salwa"             → detected
//      - EN positive: "Messilah is covered"            → detected
//      - EN negative: "we don't deliver to Messilah"   → NOT detected
//      - EN generic:  "we cover most areas"            → NOT detected (stopword)
//      - EN unrelated: "what's the pickup area?"       → NOT detected
//      - AR positive: "نوصل لسلوى"                       → detected
//      - AR positive: "اي نوصل الخالدية"                 → detected
//      - AR negative: "للأسف ما نوصل لهناك"              → NOT detected
//
//   2. Evaluator
//      - flag unset         → disabled_by_flag
//      - flag "off"         → disabled_by_flag
//      - flag "log"  + grounded area   → grounded
//      - flag "log"  + ungrounded area → ungrounded_log_only
//      - flag "on"   + ungrounded area → ungrounded_would_block
//      - flag "log"  + no claim        → no_claim_detected
//      - loader throws                 → evaluator_error
//
//   3. Metric formatter
//      - produces a [metric] line with expected fields.

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");
const SOURCE_FILE = path.join(
  DELIVERY_ROOT,
  "plugins/shared/outbound-coverage-guard.ts",
);
const SHIM_FILE = path.join(
  DELIVERY_ROOT,
  "plugins/shared/node-shims.d.ts",
);

const tscBin = path.join(DELIVERY_ROOT, "node_modules/.bin/tsc");
const outDir = mkdtempSync(path.join(tmpdir(), "outbound-coverage-guard-"));

const failures = [];
function assert(name, cond, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    console.log(`FAIL  ${name} -- ${detail || ""}`);
    failures.push(name);
  }
}

try {
  const tsc = spawnSync(
    tscBin,
    [
      SOURCE_FILE,
      SHIM_FILE,
      "--target",
      "ES2020",
      "--module",
      "ES2022",
      "--moduleResolution",
      "bundler",
      "--esModuleInterop",
      "--skipLibCheck",
      "--ignoreConfig",
      "--outDir",
      outDir,
    ],
    { stdio: "pipe", encoding: "utf-8" },
  );
  if (tsc.status !== 0) {
    console.error("tsc failed:\n" + (tsc.stdout || "") + (tsc.stderr || ""));
    process.exit(1);
  }

  const compiledUrl = url.pathToFileURL(
    path.join(outDir, "outbound-coverage-guard.js"),
  ).href;
  const mod = await import(compiledUrl);
  const {
    detectCoverageClaim,
    evaluateOutboundCoverageGuard,
    formatCoverageGuardMetric,
    __normalizeEnForTests,
    __normalizeArForTests,
  } = mod;

  // --------------------------------------------------------------------
  // (1) Detector tests
  // --------------------------------------------------------------------

  {
    const c = detectCoverageClaim("Yes, we deliver to Khaldiya. Send me the other area.");
    assert(
      "en.positive.we_deliver_to.khaldiya",
      c && c.polarity === "positive" && /khaldiya/i.test(c.areaToken) && c.language === "en",
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("Yes we cover Salwa. Want a quote?");
    assert(
      "en.positive.we_cover.salwa",
      c && /salwa/i.test(c.areaToken) && c.language === "en",
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("Messilah is covered.");
    assert(
      "en.positive.area_is_covered.messilah",
      c && /messilah/i.test(c.areaToken) && c.language === "en",
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("We don't deliver to Messilah.");
    assert("en.negative.dont_deliver", c === null, JSON.stringify(c));
  }
  {
    const c = detectCoverageClaim("We cover most areas in Kuwait.");
    assert("en.generic.most_areas_stopword", c === null, JSON.stringify(c));
  }
  {
    const c = detectCoverageClaim("What's the pickup area?");
    assert("en.unrelated.pickup_question", c === null, JSON.stringify(c));
  }
  {
    const c = detectCoverageClaim("Yes, avenues are fine. Send the avenue number if you have it.");
    // "avenues" is not a stopword but the regex captures "avenues";
    // this is an INTENDED positive detection since the LLM is claiming
    // coverage of "avenues" — which is exactly the case we want to flag.
    assert(
      "en.positive.avenues_match",
      c && /avenues/i.test(c.areaToken),
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("نوصل لسلوى. تبي السعر؟");
    assert(
      "ar.positive.nuwassil_salwa",
      c && c.language === "ar" && /سلو/.test(c.areaToken),
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("اي نوصل الخالدية");
    assert(
      "ar.positive.naam_nuwassil_khaldiya",
      c && c.language === "ar" && /خالدي/.test(c.areaToken),
      JSON.stringify(c),
    );
  }
  {
    const c = detectCoverageClaim("للأسف ما نوصل لهناك حاليا.");
    assert("ar.negative.lil_asaf", c === null, JSON.stringify(c));
  }

  // --------------------------------------------------------------------
  // (2) Evaluator tests
  // --------------------------------------------------------------------

  function makeIndex({ en = [], ar = [], areas = [] } = {}) {
    const norm_en = new Set(en.map((s) => __normalizeEnForTests(s)));
    const norm_ar = new Set(ar.map((s) => __normalizeArForTests(s)));
    return async () => ({
      en: norm_en,
      ar: norm_ar,
      areas: areas.length
        ? areas
        : [
            ...en.map((n) => ({ nameEn: n, nameAr: "" })),
            ...ar.map((n) => ({ nameEn: "", nameAr: n })),
          ],
      source: "test",
    });
  }

  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Khaldiya",
      envValue: undefined,
      loadIndex: makeIndex({ en: ["Khaldiya"] }),
    });
    assert("eval.flag_unset.disabled", d.action === "disabled_by_flag", JSON.stringify(d));
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Khaldiya",
      envValue: "off",
      loadIndex: makeIndex({ en: ["Khaldiya"] }),
    });
    assert("eval.flag_off.disabled", d.action === "disabled_by_flag", JSON.stringify(d));
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Khaldiya",
      envValue: "log",
      loadIndex: makeIndex({ en: ["Khaldiya"] }),
    });
    assert("eval.log_grounded", d.action === "grounded", JSON.stringify(d));
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Messilah",
      envValue: "log",
      loadIndex: makeIndex({ en: ["Khaldiya", "Salwa", "Mishrif"] }),
    });
    assert(
      "eval.log_ungrounded",
      d.action === "ungrounded_log_only",
      JSON.stringify(d),
    );
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Messilah",
      envValue: "on",
      loadIndex: makeIndex({ en: ["Khaldiya", "Salwa", "Mishrif"] }),
    });
    assert(
      "eval.on_ungrounded_would_block",
      d.action === "ungrounded_would_block",
      JSON.stringify(d),
    );
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "What's the pickup area?",
      envValue: "log",
      loadIndex: makeIndex({ en: ["Khaldiya"] }),
    });
    assert("eval.no_claim", d.action === "no_claim_detected", JSON.stringify(d));
  }
  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Khaldiya",
      envValue: "log",
      loadIndex: async () => {
        throw new Error("disk unavailable");
      },
    });
    assert("eval.loader_throws.graceful", d.action === "evaluator_error", JSON.stringify(d));
  }
  {
    // Arabic grounded case: "نوصل للخالدية" where Khaldiya canonical is
    // normalized (ال prefix stripped).
    const d = await evaluateOutboundCoverageGuard({
      replyText: "اي نوصل للخالدية",
      envValue: "log",
      loadIndex: makeIndex({ ar: ["الخالدية"] }),
    });
    assert(
      "eval.ar_grounded_khaldiya",
      d.action === "grounded",
      JSON.stringify(d),
    );
  }

  // --------------------------------------------------------------------
  // (3) Metric formatter
  // --------------------------------------------------------------------

  {
    const d = await evaluateOutboundCoverageGuard({
      replyText: "Yes we deliver to Messilah",
      envValue: "log",
      loadIndex: makeIndex({ en: ["Mishrif", "Salwa"] }),
    });
    const line = formatCoverageGuardMetric(d, {
      conversationId: "default::12345",
      replyLength: 28,
    });
    assert(
      "metric.contains_ungrounded_log_only",
      /action=ungrounded_log_only/.test(line),
      line,
    );
    assert("metric.contains_language", /language=en/.test(line), line);
    assert(
      "metric.contains_area_token_json",
      /area_token="Messilah"/.test(line),
      line,
    );
    assert(
      "metric.contains_conversation_id",
      /conversation=default::12345/.test(line),
      line,
    );
    assert(
      "metric.contains_reply_length",
      /reply_length=28/.test(line),
      line,
    );
  }

  console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
  if (failures.length > 0) process.exit(1);
} finally {
  try {
    rmSync(outDir, { recursive: true, force: true });
  } catch {}
}
