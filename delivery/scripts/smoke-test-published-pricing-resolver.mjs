#!/usr/bin/env node
/**
 * Evaluates get_price against the real pricing.published.json plus pricing.resolver.overlay.json.
 * Run from repo: node delivery/scripts/smoke-test-published-pricing-resolver.mjs
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  parseToolText,
  resolveRegisteredTool,
} from "./_helpers/riders-plugin-loader.mjs";

const PUBLISHED_PATH = defaultPublishedPricingPath;
const OVERLAY_PATH = defaultResolverOverlayPath;
const OVERLAY = JSON.parse(fs.readFileSync(OVERLAY_PATH, "utf8"));

async function loadGetPriceTool() {
  return await resolveRegisteredTool(
    import.meta.url,
    "get_price",
    {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: PUBLISHED_PATH,
        resolverOverlayPath: OVERLAY_PATH,
        adminAllowlist: [],
      },
    },
  );
}

async function runCase(getPriceTool, testCase) {
  const result = await getPriceTool.execute(`published-resolver-${testCase.id}`, {
    pickup_area: testCase.pickup_area,
    dropoff_area: testCase.dropoff_area,
  });
  const text = result?.content?.find?.((item) => item?.type === "text")?.text || "";
  return parseToolText(text);
}

function assertClarificationHasExpectedOptions(payload, group, query) {
  assert(payload, `Expected JSON payload for ambiguity group ${group.id}`);
  assert.equal(
    payload.status,
    "clarification_required",
    `Expected ${group.id} to require clarification for query ${JSON.stringify(query)}`,
  );
  assert.equal(
    payload.field,
    "dropoff_area",
    `Expected ${group.id} to clarify the dropoff side for query ${JSON.stringify(query)}`,
  );
  assert(Array.isArray(payload.options), `Expected ${group.id} to return options[]`);
  assert(
    payload.options.length > 0,
    `Expected ${group.id} to return a non-empty options[] for query ${JSON.stringify(query)}`,
  );

  const expectedIds = new Set((group.options || []).map((entry) => entry.area_id));
  const actualIds = new Set((payload.options || []).map((entry) => entry.area_id));
  assert.deepEqual(
    [...actualIds].sort((a, b) => a - b),
    [...expectedIds].sort((a, b) => a - b),
    `Expected ${group.id} option ids to match overlay members for query ${JSON.stringify(query)}`,
  );
  assert(
    String(payload.prompt_en || payload.prompt_ar || "").trim().length > 0,
    `Expected ${group.id} to still return a non-empty clarification prompt for query ${JSON.stringify(query)}`,
  );
}

async function main() {
  const getPriceTool = await loadGetPriceTool();

  const grouped = await runCase(getPriceTool, {
    id: "south-saad-group",
    pickup_area: "المطلاع",
    dropoff_area: "جنوب سعد العبدالله",
  });
  assert(grouped.json, "Expected JSON for south Saad group");
  assert.equal(grouped.json.route.dropoff.name_ar, "جنوب سعد العبدالله");
  assert.equal(grouped.json.default_quote.price, 5);
  console.log("ok - south Saad group alias (published ids 75–86)");

  const direct = await runCase(getPriceTool, {
    id: "ali-sabah-alias",
    pickup_area: "علي صباح",
    dropoff_area: "حولي",
  });
  assert(direct.json, "Expected JSON for علي صباح alias");
  assert.equal(direct.json.route.pickup.name_ar, "علي صباح السالم");
  assert.equal(direct.json.default_quote.price, 1.75);
  console.log("ok - علي صباح alias → area 180 (published)");

  const ambiguity = await runCase(getPriceTool, {
    id: "khairan-ambiguity",
    pickup_area: "المطلاع",
    dropoff_area: "الخيران",
  });
  assert(ambiguity.json, "Expected JSON for Khairan ambiguity");
  assert.equal(ambiguity.json.status, "clarification_required");
  assert.equal(ambiguity.json.field, "dropoff_area");
  assert.match(ambiguity.json.prompt_ar, /الخيران السكنية|شاليهات الخيران/);
  console.log("ok - الخيران ambiguity (overlay)");

  const wafraAmbiguity = await runCase(getPriceTool, {
    id: "wafra-ambiguity",
    pickup_area: "المطلاع",
    dropoff_area: "الوفرة",
  });
  assert(wafraAmbiguity.json, "Expected JSON for Wafra ambiguity");
  assert.equal(wafraAmbiguity.json.status, "clarification_required");
  assert.equal(wafraAmbiguity.json.field, "dropoff_area");
  assert.match(wafraAmbiguity.json.prompt_ar, /الوفرة السكنية|مزارع الوفرة/);
  console.log("ok - الوفرة ambiguity (overlay)");

  const saadAmbiguity = await runCase(getPriceTool, {
    id: "saad-abdullah-ambiguity",
    pickup_area: "المطلاع",
    dropoff_area: "سعد العبدالله",
  });
  assert(saadAmbiguity.json, "Expected JSON for Saad ambiguity");
  assert.equal(saadAmbiguity.json.status, "clarification_required");
  assert.equal(saadAmbiguity.json.field, "dropoff_area");
  assert.match(saadAmbiguity.json.prompt_ar, /سعد العبدالله|جنوب سعد العبدالله/);
  console.log("ok - سعد العبدالله ambiguity stays safe");

  const mutlaaResidential = await runCase(getPriceTool, {
    id: "mutlaa-residential-group",
    pickup_area: "حولي",
    dropoff_area: "المطلاع السكنية",
  });
  assert(mutlaaResidential.json, "Expected JSON for Mutlaa Residential alias");
  assert.equal(mutlaaResidential.json.route.dropoff.name_ar, "المطلاع");
  assert.equal(mutlaaResidential.json.default_quote.price, 2.5);
  console.log("ok - المطلاع السكنية resolves through canonical overlay alias");

  const southSabah = await runCase(getPriceTool, {
    id: "south-sabah-group",
    pickup_area: "المطلاع",
    dropoff_area: "جنوب صباح الأحمد",
  });
  assert(southSabah.json, "Expected JSON for South Sabah Al-Ahmad group");
  assert.equal(southSabah.json.route.dropoff.name_ar, "جنوب صباح الأحمد");
  assert.equal(southSabah.json.default_quote.price, 2.75);
  console.log("ok - جنوب صباح الأحمد resolves through grouped sector metadata");

  const marineAlias = await runCase(getPriceTool, {
    id: "sabah-marine-alias",
    pickup_area: "المطلاع",
    dropoff_area: "ضاحية صباح الأحمد البحرية",
  });
  assert(marineAlias.json, "Expected JSON for Sabah Al-Ahmad Marine alias");
  assert.equal(marineAlias.json.route.dropoff.name_ar, "صباح الاحمد البحرية");
  assert.equal(marineAlias.json.default_quote.price, 6);
  console.log("ok - ضاحية صباح الأحمد البحرية resolves through direct overlay alias");

  const hawallyTypo = await runCase(getPriceTool, {
    id: "hawally-typo",
    pickup_area: "Hawally",
    dropoff_area: "Airport",
  });
  assert(hawallyTypo.json, "Expected JSON for Hawally typo recovery");
  assert.equal(hawallyTypo.json.route.pickup.name_en, "Hawalli");
  assert.equal(hawallyTypo.json.default_quote.price, 2.5);
  console.log("ok - Hawally typo resolves through deterministic Latin normalization");

  const arabiziHawalli = await runCase(getPriceTool, {
    id: "arabizi-hawalli",
    pickup_area: "7walli",
    dropoff_area: "Airport",
  });
  assert(arabiziHawalli.json, "Expected JSON for 7walli Arabizi recovery");
  assert.equal(arabiziHawalli.json.route.pickup.name_en, "Hawalli");
  assert.equal(arabiziHawalli.json.default_quote.price, 2.5);
  console.log("ok - 7walli resolves through Arabizi normalization");

  const salmyaTypo = await runCase(getPriceTool, {
    id: "salmya-typo",
    pickup_area: "Farwaniya",
    dropoff_area: "Salmya",
  });
  assert(salmyaTypo.json, "Expected JSON for Salmya typo recovery");
  assert.equal(salmyaTypo.json.route.dropoff.name_en, "Salmiya");
  assert.equal(salmyaTypo.json.default_quote.price, 1.25);
  console.log("ok - Salmya resolves to Salmiya without collapsing to Salmy");

  const saadTypo = await runCase(getPriceTool, {
    id: "saad-abdula-ambiguity",
    pickup_area: "Khaitan",
    dropoff_area: "Saad Abdula",
  });
  assert(saadTypo.json, "Expected JSON for Saad Abdula ambiguity");
  assert.equal(saadTypo.json.status, "clarification_required");
  assert.equal(saadTypo.json.field, "dropoff_area");
  assert.match(saadTypo.json.prompt_en, /Saad Al-Abdulla|South Saad Al-Abdulla/);
  console.log("ok - Saad Abdula routes into the ambiguity family prompt");

  const sabahAmbiguity = await runCase(getPriceTool, {
    id: "sabah-ambiguity",
    pickup_area: "المطلاع",
    dropoff_area: "صباح الأحمد",
  });
  assert(sabahAmbiguity.json, "Expected JSON for Sabah Al-Ahmad ambiguity");
  assert.equal(sabahAmbiguity.json.status, "clarification_required");
  assert.equal(sabahAmbiguity.json.field, "dropoff_area");
  assert.match(sabahAmbiguity.json.prompt_ar, /مدينة صباح الأحمد|جنوب صباح الأحمد|البحرية/);
  console.log("ok - صباح الأحمد ambiguity prompts for the right branch");

  const kuwaitCityAmbiguity = await runCase(getPriceTool, {
    id: "kuwait-city-downtown-ambiguity",
    pickup_area: "Shamiya",
    dropoff_area: "Kuwait City",
  });
  assert(kuwaitCityAmbiguity.json, "Expected JSON for Kuwait City ambiguity");
  assert.equal(kuwaitCityAmbiguity.json.status, "clarification_required");
  assert.equal(kuwaitCityAmbiguity.json.field, "dropoff_area");
  assert.match(kuwaitCityAmbiguity.json.prompt_en, /Sharq|Mirqab|Qibla|Bnaid Al-Qar/);
  console.log("ok - Kuwait City routes into downtown ambiguity instead of generic not-found");

  const shadadiyaAmbiguity = await runCase(getPriceTool, {
    id: "shadadiya-ambiguity",
    pickup_area: "Farwaniya",
    dropoff_area: "Shadadiya",
  });
  assert(shadadiyaAmbiguity.json, "Expected JSON for Shadadiya ambiguity");
  assert.equal(shadadiyaAmbiguity.json.status, "clarification_required");
  assert.equal(shadadiyaAmbiguity.json.field, "dropoff_area");
  assert.match(shadadiyaAmbiguity.json.prompt_en, /Shadadiya|Industrial/);
  console.log("ok - Shadadiya routes into residential vs industrial clarification");

  const seaFrontAmbiguity = await runCase(getPriceTool, {
    id: "sea-front-ambiguity",
    pickup_area: "Salmiya",
    dropoff_area: "The Sea Front",
  });
  assert(seaFrontAmbiguity.json, "Expected JSON for Sea Front ambiguity");
  assert.equal(seaFrontAmbiguity.json.status, "clarification_required");
  assert.equal(seaFrontAmbiguity.json.field, "dropoff_area");
  assert.match(seaFrontAmbiguity.json.prompt_en, /The Sea Front|Hawalli/);
  console.log("ok - Sea Front routes into Hawalli clarification instead of silently picking one");

  const minaAbdullahAmbiguity = await runCase(getPriceTool, {
    id: "mina-abdullah-ambiguity",
    pickup_area: "Hawalli",
    dropoff_area: "ميناء عبدالله",
  });
  assert(minaAbdullahAmbiguity.json, "Expected JSON for Mina Abdullah ambiguity");
  assert.equal(minaAbdullahAmbiguity.json.status, "clarification_required");
  assert.equal(minaAbdullahAmbiguity.json.field, "dropoff_area");
  assert.match(
    minaAbdullahAmbiguity.json.prompt_en,
    /Mina Abdulla|Mina Abdullah Refinery|Shalehat Mina Abdullah/,
  );
  console.log("ok - Mina Abdullah routes into its own safe ambiguity family");

  const minaAbdullahTypoAmbiguity = await runCase(getPriceTool, {
    id: "mina-abdullah-typo-ambiguity",
    pickup_area: "Hawalli",
    dropoff_area: "مينا عبدالله",
  });
  assert(minaAbdullahTypoAmbiguity.json, "Expected JSON for Mina Abdullah typo ambiguity");
  assert.equal(minaAbdullahTypoAmbiguity.json.status, "clarification_required");
  assert.equal(minaAbdullahTypoAmbiguity.json.field, "dropoff_area");
  assert.match(
    minaAbdullahTypoAmbiguity.json.prompt_en,
    /Mina Abdulla|Mina Abdullah Refinery|Shalehat Mina Abdullah/,
  );
  console.log("ok - Mina Abdullah typo routes into the ambiguity family");

  const shuwaikhIndustrialAmbiguity = await runCase(getPriceTool, {
    id: "shuwaikh-industrial-family",
    pickup_area: "Hawalli",
    dropoff_area: "Shuwaikh Industrial",
  });
  assert(shuwaikhIndustrialAmbiguity.json, "Expected JSON for Shuwaikh Industrial family ambiguity");
  assert.equal(shuwaikhIndustrialAmbiguity.json.status, "clarification_required");
  assert.equal(shuwaikhIndustrialAmbiguity.json.field, "dropoff_area");
  assert.match(
    shuwaikhIndustrialAmbiguity.json.prompt_en,
    /Shuwaikh Industrial-1|Shuwaikh Industrial-2|Shuwaikh Industrial-3/,
  );
  console.log("ok - Shuwaikh Industrial stays a numbered-family clarification");

  const shuwaikhIndustrialArabicAmbiguity = await runCase(getPriceTool, {
    id: "shuwaikh-industrial-family-ar",
    pickup_area: "Hawalli",
    dropoff_area: "الشويخ الصناعية",
  });
  assert(shuwaikhIndustrialArabicAmbiguity.json, "Expected JSON for Arabic Shuwaikh Industrial family ambiguity");
  assert.equal(shuwaikhIndustrialArabicAmbiguity.json.status, "clarification_required");
  assert.equal(shuwaikhIndustrialArabicAmbiguity.json.field, "dropoff_area");
  assert.match(
    shuwaikhIndustrialArabicAmbiguity.json.prompt_ar,
    /الشويخ الصناعية 1|الشويخ الصناعية 2|الشويخ الصناعية 3/,
  );
  console.log("ok - Arabic Shuwaikh Industrial now clarifies instead of collapsing to one zone");

  const shuwaikhArabiziAmbiguity = await runCase(getPriceTool, {
    id: "shuwaikh-arabizi-broad-ambiguity",
    pickup_area: "Hawalli",
    dropoff_area: "shwuai5",
  });
  assert(shuwaikhArabiziAmbiguity.json, "Expected JSON for broad shwuai5 ambiguity");
  assert.equal(shuwaikhArabiziAmbiguity.json.status, "clarification_required");
  assert.equal(shuwaikhArabiziAmbiguity.json.field, "dropoff_area");
  assert.match(
    shuwaikhArabiziAmbiguity.json.prompt_en,
    /Shuwaikh|Shuwaikh Industrial|Shuwaikh Educational|Shuwaikh Sanitary/,
  );
  console.log("ok - shwuai5 stays broad Shuwaikh ambiguity instead of route-locking");

  const sulaibiyaIndustrialAmbiguity = await runCase(getPriceTool, {
    id: "sulaibiya-industrial-family",
    pickup_area: "Hawalli",
    dropoff_area: "Sulaibiya Industrial",
  });
  assert(sulaibiyaIndustrialAmbiguity.json, "Expected JSON for Sulaibiya Industrial family ambiguity");
  assert.equal(sulaibiyaIndustrialAmbiguity.json.status, "clarification_required");
  assert.equal(sulaibiyaIndustrialAmbiguity.json.field, "dropoff_area");
  assert.match(
    sulaibiyaIndustrialAmbiguity.json.prompt_en,
    /Sulaibiya Industrial 1|Sulaibiya Industrial 2|Sulaibyia Industrial 3/,
  );
  console.log("ok - Sulaibiya Industrial no longer collapses to Industrial 1");

  const sulaibiyaIndustrialArabicAmbiguity = await runCase(getPriceTool, {
    id: "sulaibiya-industrial-family-ar",
    pickup_area: "Hawalli",
    dropoff_area: "الصليبية الصناعية",
  });
  assert(sulaibiyaIndustrialArabicAmbiguity.json, "Expected JSON for Arabic Sulaibiya Industrial family ambiguity");
  assert.equal(sulaibiyaIndustrialArabicAmbiguity.json.status, "clarification_required");
  assert.equal(sulaibiyaIndustrialArabicAmbiguity.json.field, "dropoff_area");
  assert.match(
    sulaibiyaIndustrialArabicAmbiguity.json.prompt_ar,
    /الصليبية الصناعية 1|الصليبية الصناعية 2|الصليبية الصناعية 3/,
  );
  console.log("ok - Arabic Sulaibiya Industrial no longer collapses to Industrial 1");

  const sabahAhmadAmbiguity = await runCase(getPriceTool, {
    id: "sabah-ahmad-ambiguity",
    pickup_area: "Hawalli",
    dropoff_area: "صباح احمد",
  });
  assert(sabahAhmadAmbiguity.json, "Expected JSON for Sabah Ahmad ambiguity");
  assert.equal(sabahAhmadAmbiguity.json.status, "clarification_required");
  assert.equal(sabahAhmadAmbiguity.json.field, "dropoff_area");
  assert.match(
    sabahAhmadAmbiguity.json.prompt_en,
    /Sabah Al-Ahmad City|South Sabah Al-Ahmad|Sabah Al-Ahmad Marine/,
  );
  console.log("ok - Sabah Ahmad typo now routes into the curated Sabah Al-Ahmad family prompt");

  const southSabahAhmadGroup = await runCase(getPriceTool, {
    id: "south-sabah-ahmad-group",
    pickup_area: "Hawalli",
    dropoff_area: "جنوب صباح احمد",
  });
  assert(southSabahAhmadGroup.json, "Expected JSON for South Sabah Ahmad grouped alias");
  assert.equal(southSabahAhmadGroup.json.route.dropoff.name_ar, "جنوب صباح الأحمد");
  assert.equal(southSabahAhmadGroup.json.route.dropoff.name_en, "South Sabah Al-Ahmad");
  console.log("ok - South Sabah Ahmad typo now resolves through the curated group alias");

  const sabihAhmadAmbiguity = await runCase(getPriceTool, {
    id: "sabih-ahmad-ambiguity",
    pickup_area: "Hawalli",
    dropoff_area: "سابح الاحمد",
  });
  assert(sabihAhmadAmbiguity.json, "Expected JSON for Sabih Ahmad ambiguity");
  assert.equal(sabihAhmadAmbiguity.json.status, "clarification_required");
  assert.equal(sabihAhmadAmbiguity.json.field, "dropoff_area");
  assert.match(
    sabihAhmadAmbiguity.json.prompt_en,
    /Sabah Al-Ahmad City|South Sabah Al-Ahmad|Sabah Al-Ahmad Marine/,
  );
  console.log("ok - Sabih Ahmad typo no longer misfires to Jaber Al-Ahmad");

  const ambiguityQueries = {
    khairan: "الخيران",
    wafra: "الوفرة",
    saad_abdullah: "سعد العبدالله",
    sabah_al_ahmad: "صباح الأحمد",
    shuwaikh: "الشويخ",
    ardhiya: "العارضية",
    ahmadi: "الأحمدي",
    sulaibiya: "الصليبية",
    doha: "الدوحة",
    sulaibikhat: "الصليبيخات",
    sabah_al_salem: "صباح السالم",
    kabd: "كبد",
    jahra_area: "الجهراء",
    shuaiba: "الشعيبة",
    mina: "ميناء",
    mina_abdullah: "ميناء عبدالله",
    kuwait_city_downtown: "Kuwait City",
    shadadiya: "Shadadiya",
    sea_front: "The Sea Front",
  };

  const allAmbiguityGroups = OVERLAY?.resolver?.ambiguity_groups || [];
  assert.equal(allAmbiguityGroups.length, 19, "Expected 19 ambiguity groups in live resolver overlay");
  for (const group of allAmbiguityGroups) {
    const query = ambiguityQueries[group.id];
    assert(query, `Missing smoke query seed for ambiguity group ${group.id}`);
    const response = await runCase(getPriceTool, {
      id: `ambiguity-members-${group.id}`,
      pickup_area: "Hawalli",
      dropoff_area: query,
    });
    assertClarificationHasExpectedOptions(response.json, group, query);
    console.log(
      `ok - ${group.id} returns ${group.options.length} concrete member options for ${JSON.stringify(query)}`,
    );
  }

  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
