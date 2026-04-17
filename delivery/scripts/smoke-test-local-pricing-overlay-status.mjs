#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { loadPluginRegistrations } from "./_helpers/riders-plugin-loader.mjs";

const FIXTURE_PATH =
  "/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.resolver-fixture.json";

async function loadPluginTools(resolverOverlayPath) {
  return await loadPluginRegistrations(import.meta.url, {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: FIXTURE_PATH,
        resolverOverlayPath,
        adminAllowlist: [],
      },
    });
}

async function resolveTool(registrations, name, ctx = {}) {
  for (const registration of registrations) {
    const tool = typeof registration === "function" ? registration(ctx) : registration;
    if (tool?.name === name) return tool;
  }
  throw new Error(`Tool ${name} not found`);
}

async function executeTool(name, resolverOverlayPath) {
  const registrations = await loadPluginTools(resolverOverlayPath);
  const tool = await resolveTool(registrations, name, {
    senderIsOwner: true,
    requesterSenderId: "96500000000",
  });
  const result = await tool.execute(`${name}-smoke`, {});
  return {
    payload: JSON.parse(result.content.find((item) => item.type === "text").text),
    details: result.details,
  };
}

async function main() {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "pricing-overlay-status-"));
  const validOverlayPath = path.join(tempDir, "valid-overlay.json");
  const invalidOverlayPath = path.join(tempDir, "invalid-overlay.json");
  const missingOverlayPath = path.join(tempDir, "missing-overlay.json");

  await fs.writeFile(
    validOverlayPath,
    `${JSON.stringify(
      {
        resolver: {
          aliases: [{ alias: "المطلاع الجديدة", area_id: 1 }],
          pricing_groups: [
            {
              id: "mutlaa_custom_group",
              name_ar: "المطلاع الخاصة",
              name_en: "Mutlaa Custom Group",
              area_ids: [1],
              aliases: ["المطلاع الخاصة"],
            },
          ],
          ambiguity_groups: [
            {
              id: "daiya_example",
              prompt_ar: "هل تقصد الدعية أو كيفان؟",
              prompt_en: "Do you mean Daiya or Kaifan?",
              aliases: ["الدعية"],
            },
          ],
        },
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );

  await fs.writeFile(
    invalidOverlayPath,
    `${JSON.stringify(
      {
        resolver: {
          aliases: [{ alias: "bad overlay alias", area_id: 999 }],
        },
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );

  const validStatus = await executeTool("admin_pricing_source_status", validOverlayPath);
  assert.equal(validStatus.payload.status, "ok");
  assert.equal(validStatus.payload.pricing_resolver_overlay.state, "active");
  assert.equal(validStatus.payload.pricing_resolver_overlay.aliases_count, 1);
  assert.equal(validStatus.payload.pricing_resolver_overlay.merged_aliases_count, 2);
  assert.deepEqual(validStatus.payload.pricing_resolver_overlay.pricing_group_ids, ["mutlaa_custom_group"]);
  assert.equal(validStatus.payload.resolver.aliases_count, 2);
  assert.equal(validStatus.payload.resolver_source, "base_plus_overlay");
  console.log("ok - pricing source status reports active resolver overlay details");

  const validValidation = await executeTool("admin_validate_pricing_resolver_overlay", validOverlayPath);
  assert.equal(validValidation.payload.status, "ok");
  assert.equal(validValidation.payload.pricing_resolver_overlay.state, "active");
  assert.equal(validValidation.payload.resolver.ambiguity_group_count, 2);
  console.log("ok - overlay validator accepts a valid overlay");

  const missingStatus = await executeTool("admin_pricing_source_status", missingOverlayPath);
  assert.equal(missingStatus.payload.status, "ok");
  assert.equal(missingStatus.payload.pricing_resolver_overlay.state, "missing");
  assert.match(missingStatus.payload.pricing_resolver_overlay.error, /not found/i);
  console.log("ok - pricing source status reports missing overlay without crashing");

  const invalidStatus = await executeTool("admin_pricing_source_status", invalidOverlayPath);
  assert.equal(invalidStatus.payload.status, "ok");
  assert.equal(invalidStatus.payload.pricing_resolver_overlay.state, "invalid");
  assert.match(invalidStatus.payload.pricing_resolver_overlay.error, /unknown area id 999/i);
  console.log("ok - pricing source status reports invalid overlay validation errors");

  const invalidValidation = await executeTool("admin_validate_pricing_resolver_overlay", invalidOverlayPath);
  assert.equal(invalidValidation.payload.status, "error");
  assert.match(invalidValidation.payload.message, /unknown area id 999/i);
  console.log("ok - overlay validator rejects invalid overlay references");

  await fs.rm(tempDir, { recursive: true, force: true });
  process.exit(0);
}

main().catch(async (err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
