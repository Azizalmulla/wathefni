// Smoke test for the check_area_coverage tool.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-coverage-tool.mjs
//
// The test compiles `plugins/riders-tools/tools/coverage.ts` on the fly
// via a one-shot tsc invocation so we can exercise the tool registration
// and execute() without touching the full plugin runtime.
//
// Coverage:
//   - resolver `resolved`       → tool returns `status: "covered"` with canonical names.
//   - known landmark            → tool returns `status: "landmark_mapped"` with area.
//   - resolver `suggested`      → tool returns `status: "suggested"` with alternatives.
//   - resolver `ambiguous`      → tool returns `status: "ambiguous"` with options.
//   - unknown place-like query  → tool returns `status: "needs_area_for_place"`, not not_covered.
//   - pending clarification     → short follow-ups resolve against prior coverage context.
//   - resolver `not_found`      → tool returns `status: "not_covered"` with nearby.
//   - empty input               → `status: "not_covered"` with `error: "empty_area"`.
//   - loadPricing throws        → graceful fallback (`error: "coverage_lookup_failed"`).
//   - tool definition shape     → strict, required params, correct name.

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");
const SOURCE_FILE = path.join(
  DELIVERY_ROOT,
  "plugins/riders-tools/tools/coverage.ts",
);

const tscBin = path.join(DELIVERY_ROOT, "node_modules/.bin/tsc");
const outDir = mkdtempSync(path.join(tmpdir(), "check-coverage-tool-"));

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
    path.join(outDir, "coverage.js"),
  ).href;
  const mod = await import(compiledUrl);
  const { registerCoverageTools } = mod;

  function makeApi() {
    const registered = [];
    return {
      registered,
      registerTool(def) {
        registered.push(def);
      },
    };
  }

  function makeDeps({ resolverResult, candidates = [], throwOnLoad = false }) {
    const session = {};
    return {
      _session: session,
      createTextResult(payload) {
        return {
          content: [{ type: "text", text: JSON.stringify(payload) }],
        };
      },
      quoting: {
        resolvePricingAreaQuery: async (query) =>
          typeof resolverResult === "function"
            ? resolverResult(query)
            : resolverResult,
        collectAreaCandidates: () => candidates,
      },
      pricing: {
        loadPricing: async () => {
          if (throwOnLoad) throw new Error("pricing load failed");
          return {
            areas: [
              { id: 1, name_en: "Khaldiya", name_ar: "الخالدية" },
              { id: 2, name_en: "Salwa", name_ar: "سلوى" },
              { id: 24, name_en: "Rai", name_ar: "الري" },
              { id: 44, name_en: "Zahra", name_ar: "الزهراء" },
            ],
          };
        },
      },
      intentGates: {
        getSessionFromCtx: () => ({ key: "test", aliases: ["test"], session }),
      },
    };
  }

  async function run(deps, params) {
    const api = makeApi();
    registerCoverageTools(api, deps);
    const tool = api.registered[0];
    if (!tool) throw new Error("no tool registered");
    const out = await tool.execute("call-1", params, {});
    const text = out?.content?.[0]?.text;
    return { def: tool, result: JSON.parse(text) };
  }

  // Case 1 — resolved → covered.
  {
    const deps = makeDeps({
        resolverResult: {
          status: "resolved",
          area: { id: 16, name_en: "Khaldiya", name_ar: "الخالدية" },
        },
      });
    const { result: r } = await run(deps, { area: "khaldiya" });
    assert("resolved→covered status", r.status === "covered", JSON.stringify(r));
    assert("covered canonical_en", r.canonical_en === "Khaldiya", JSON.stringify(r));
    assert("covered canonical_ar", r.canonical_ar === "الخالدية", JSON.stringify(r));
    assert("covered area_id", r.area_id === 16, JSON.stringify(r));
    assert("covered echoes query", r.query === "khaldiya", JSON.stringify(r));
    assert(
      "covered result leaves route candidate pending",
      deps._session.coveragePending?.kind === "covered_area_candidate" &&
        deps._session.coveragePending?.area?.canonical_en === "Khaldiya",
      JSON.stringify(deps._session.coveragePending),
    );
  }

  // Case 1b — known landmark typo → mapped to its covered area.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: (query) => {
          if (query !== "Rai") {
            return { status: "not_found" };
          }
          return {
            status: "resolved",
            area: { id: 24, name_en: "Rai", name_ar: "الري" },
          };
        },
      }),
      { area: "aveneus" },
    );
    assert("landmark mapped status", r.status === "landmark_mapped", JSON.stringify(r));
    assert(
      "landmark canonical",
      r.landmark?.canonical_en === "The Avenues Mall",
      JSON.stringify(r),
    );
    assert("landmark area canonical", r.area?.canonical_en === "Rai", JSON.stringify(r));
    assert("landmark area id", r.area?.area_id === 24, JSON.stringify(r));
  }

  // Case 1c — Arabic Avenues alias → mapped to Rai.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: (query) => {
          if (query !== "Rai") return { status: "not_found" };
          return {
            status: "resolved",
            area: { id: 24, name_en: "Rai", name_ar: "الري" },
          };
        },
      }),
      { area: "افنيوز" },
    );
    assert("Arabic Avenues mapped", r.status === "landmark_mapped", JSON.stringify(r));
    assert("Arabic Avenues area ar", r.area?.canonical_ar === "الري", JSON.stringify(r));
  }

  // Case 1d — 360 Mall → mapped to Zahra from pricing data.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: (query) => {
          if (query !== "Zahra") return { status: "not_found" };
          return {
            status: "resolved",
            area: { id: 44, name_en: "Zahra", name_ar: "الزهراء" },
          };
        },
      }),
      { area: "360" },
    );
    assert("360 mapped status", r.status === "landmark_mapped", JSON.stringify(r));
    assert("360 mapped landmark", r.landmark?.canonical_en === "360 Mall", JSON.stringify(r));
    assert("360 mapped area", r.area?.canonical_en === "Zahra", JSON.stringify(r));
  }

  // Case 2 — suggested → suggested with alternatives.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: {
          status: "suggested",
          area: { id: 57, name_en: "Mishrif", name_ar: "مشرف" },
          prompt_ar: "تقصد مشرف؟",
          prompt_en: "Do you mean Mishrif?",
          alternative_areas: [{ id: 58, name_en: "Salwa", name_ar: "سلوى" }],
        },
      }),
      { area: "messilah" },
    );
    assert("suggested status", r.status === "suggested", JSON.stringify(r));
    assert(
      "suggested canonical",
      r.suggested_area?.canonical_en === "Mishrif",
      JSON.stringify(r),
    );
    assert(
      "suggested has alternative",
      Array.isArray(r.alternative_areas) && r.alternative_areas.length === 1,
      JSON.stringify(r),
    );
    assert(
      "alternative canonical",
      r.alternative_areas[0]?.canonical_en === "Salwa",
      JSON.stringify(r),
    );
  }

  // Case 3 — ambiguous → ambiguous with options.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: {
          status: "ambiguous",
          options: [
            { area_id: 100, name_en: "Khiran City", name_ar: "مدينة الخيران" },
            {
              area_id: 101,
              name_en: "Shalehat Al-Khiran",
              name_ar: "شاليهات الخيران",
            },
          ],
        },
      }),
      { area: "khairan" },
    );
    assert("ambiguous status", r.status === "ambiguous", JSON.stringify(r));
    assert(
      "ambiguous options count",
      Array.isArray(r.options) && r.options.length === 2,
      JSON.stringify(r),
    );
    assert(
      "ambiguous option shape",
      r.options?.[0]?.canonical_en === "Khiran City" &&
        r.options?.[0]?.area_id === 100,
      JSON.stringify(r),
    );
  }

  // Case 3b — unknown place-like query should ask for area instead of
  // falsely saying the place is not covered.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: { status: "not_found" },
        candidates: [
          {
            area: { id: 2, name_en: "Salwa", name_ar: "سلوى" },
            similarity: 0.41,
          },
        ],
      }),
      { area: "Some Random Mall" },
    );
    assert("unknown landmark needs_area", r.status === "needs_area_for_place", JSON.stringify(r));
    assert(
      "unknown landmark ask_for area",
      r.ask_for === "area_name" &&
        r.reason === "landmark_or_place_not_area" &&
        r.place?.query === "Some Random Mall",
      JSON.stringify(r),
    );
  }

  // Case 3c — unknown place pending area follow-up resolves the place.
  {
    const deps = makeDeps({
      resolverResult: (query) => {
        if (query === "Some Random Mall") return { status: "not_found" };
        if (query === "zahra i think") {
          return {
            status: "resolved",
            area: { id: 44, name_en: "Zahra", name_ar: "الزهراء" },
          };
        }
        return { status: "not_found" };
      },
    });
    const first = await run(deps, { area: "Some Random Mall" });
    const second = await run(deps, { area: "zahra i think" });
    assert(
      "pending place first asks area",
      first.result.status === "needs_area_for_place",
      JSON.stringify(first.result),
    );
    assert(
      "pending place area resolved",
      second.result.status === "place_area_resolved" &&
        second.result.place?.query === "Some Random Mall" &&
        second.result.area?.canonical_en === "Zahra",
      JSON.stringify(second.result),
    );
  }

  // Case 3d — Wafra ambiguity pending lets `res` resolve to Wafra Residential.
  {
    const deps = makeDeps({
      resolverResult: {
        status: "ambiguous",
        options: [
          { area_id: 201, name_en: "Wafra", name_ar: "الوفرة" },
          {
            area_id: 202,
            name_en: "Wafra Residential",
            name_ar: "الوفرة السكنية",
          },
          { area_id: 203, name_en: "Wafra Farms", name_ar: "مزارع الوفرة" },
        ],
      },
    });
    const first = await run(deps, { area: "wafra" });
    const second = await run(deps, { area: "res" });
    assert("wafra ambiguous", first.result.status === "ambiguous", JSON.stringify(first.result));
    assert(
      "res resolves pending Wafra Residential",
      second.result.status === "covered" &&
        second.result.canonical_en === "Wafra Residential" &&
        second.result.resolved_from_pending?.original_query === "wafra",
      JSON.stringify(second.result),
    );
  }

  // Case 4 — not_found → not_covered with nearby.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: { status: "not_found" },
        candidates: [
          {
            area: { id: 2, name_en: "Salwa", name_ar: "سلوى" },
            similarity: 0.41,
          },
          {
            area: { id: 1, name_en: "Khaldiya", name_ar: "الخالدية" },
            similarity: 0.33,
          },
        ],
      }),
      { area: "messilah" },
    );
    assert("not_found→not_covered", r.status === "not_covered", JSON.stringify(r));
    assert("not_covered can suggest", r.can_suggest_nearby === true, JSON.stringify(r));
    assert(
      "not_covered has nearby",
      Array.isArray(r.nearby_covered) && r.nearby_covered.length === 2,
      JSON.stringify(r),
    );
    assert(
      "nearby shape",
      r.nearby_covered[0]?.canonical_en === "Salwa" &&
        r.nearby_covered[0]?.similarity === 0.41,
      JSON.stringify(r),
    );
  }

  // Case 4b — not_found with no candidates must not invite fake nearby areas.
  {
    const { result: r } = await run(
      makeDeps({
        resolverResult: { status: "not_found" },
        candidates: [],
      }),
      { area: "messila" },
    );
    assert("messila not covered", r.status === "not_covered", JSON.stringify(r));
    assert("messila no fake nearby", r.can_suggest_nearby === false, JSON.stringify(r));
    assert(
      "messila nearby empty",
      Array.isArray(r.nearby_covered) && r.nearby_covered.length === 0,
      JSON.stringify(r),
    );
  }

  // Case 5 — empty input → not_covered with error marker.
  {
    const { result: r } = await run(
      makeDeps({ resolverResult: { status: "not_found" } }),
      { area: "   " },
    );
    assert("empty status", r.status === "not_covered", JSON.stringify(r));
    assert("empty error marker", r.error === "empty_area", JSON.stringify(r));
  }

  // Case 6 — loadPricing throws → graceful fallback.
  {
    const { result: r } = await run(
      makeDeps({ throwOnLoad: true, resolverResult: { status: "not_found" } }),
      { area: "anywhere" },
    );
    assert("load-fails status", r.status === "not_covered", JSON.stringify(r));
    assert(
      "load-fails error marker",
      r.error === "coverage_lookup_failed",
      JSON.stringify(r),
    );
  }

  // Case 7 — tool definition well-formed.
  {
    const { def } = await run(
      makeDeps({ resolverResult: { status: "not_found" } }),
      { area: "x" },
    );
    assert("tool name", def?.name === "check_area_coverage", def?.name);
    assert(
      "tool requires area",
      Array.isArray(def?.parameters?.required) &&
        def.parameters.required.includes("area"),
      JSON.stringify(def?.parameters?.required),
    );
    assert("tool is strict", def?.strict === true, String(def?.strict));
    assert(
      "area param type string",
      def?.parameters?.properties?.area?.type === "string",
      JSON.stringify(def?.parameters?.properties?.area),
    );
  }

  // Case 8 — workspace prompt contract must not resurrect the old
  // "landmarks are not areas; ask which area first" authority.
  {
    const skill = readFileSync(
      path.join(DELIVERY_ROOT, "workspaces/riders/SKILL.md"),
      "utf8",
    );
    const tools = readFileSync(
      path.join(DELIVERY_ROOT, "workspaces/riders/TOOLS.md"),
      "utf8",
    );
    const reference = readFileSync(
      path.join(DELIVERY_ROOT, "workspaces/riders/REFERENCE.md"),
      "utf8",
    );
    const oneBrainContext = readFileSync(
      path.join(
        DELIVERY_ROOT,
        "plugins/octopus-channel/lib/one-brain-context.ts",
      ),
      "utf8",
    );
    assert(
      "workspace no old landmark no-tool rule",
      !/do NOT call `check_area_coverage` with the landmark name/i.test(
        skill + "\n" + tools,
      ) &&
        !/Do NOT call it for landmarks or malls/i.test(skill + "\n" + tools),
      "old landmark no-tool rule still present",
    );
    assert(
      "workspace delegates landmark handling to coverage tool",
      /landmark/i.test(tools) && /coverage truth/i.test(skill),
      "concise landmark coverage contract missing",
    );
    assert(
      "reference does not suspend Avenues",
      !/الأفنيوز[\s\S]{0,80}متوقفة/.test(reference) &&
        !/The Avenues[\s\S]{0,80}suspended/i.test(reference),
      "Avenues still appears as suspended",
    );
    assert(
      "hard rules require coverage tool for Avenues",
      /check_area_coverage/.test(oneBrainContext) &&
        /افنيوز/.test(oneBrainContext),
      "one-brain hard rule missing coverage tool obligation",
    );
  }

  console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
  if (failures.length > 0) process.exit(1);
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
