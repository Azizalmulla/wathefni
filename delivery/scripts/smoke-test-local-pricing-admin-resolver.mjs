#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { loadPluginRegistrations } from "./_helpers/riders-plugin-loader.mjs";

const FIXTURE_PATH =
  "/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.resolver-fixture.json";

async function loadPluginTools() {
  return await loadPluginRegistrations(import.meta.url, {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: FIXTURE_PATH,
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

async function main() {
  const fixture = JSON.parse(await fs.readFile(FIXTURE_PATH, "utf-8"));
  const registrations = await loadPluginTools();

  const adminPublishTool = await resolveTool(registrations, "admin_publish_pricing_snapshot", {
    senderIsOwner: true,
    requesterSenderId: "96500000000",
  });

  const dryRun = await adminPublishTool.execute("admin-dry-run", {
    areas: fixture.areas,
    columns: fixture.columns,
    currency: fixture.currency,
    last_updated: fixture.last_updated,
    resolver: fixture.resolver,
    dry_run: true,
  });
  const dryRunPayload = JSON.parse(dryRun.content.find((item) => item.type === "text").text);
  assert.equal(dryRunPayload.status, "ok");
  assert.equal(dryRunPayload.published, false);
  assert.equal(dryRunPayload.area_count, fixture.areas.length);
  assert.equal(dryRun.details.pricing_data.resolver.pricing_groups[0].id, "south_saad");
  console.log("ok - admin snapshot dry run accepts resolver metadata");

  const brokenRun = await adminPublishTool.execute("admin-broken-run", {
    areas: fixture.areas,
    columns: fixture.columns,
    currency: fixture.currency,
    last_updated: fixture.last_updated,
    resolver: {
      aliases: [{ alias: "bad alias", pricing_group_id: "missing_group" }],
    },
    dry_run: true,
  });
  const brokenPayload = JSON.parse(brokenRun.content.find((item) => item.type === "text").text);
  assert.equal(brokenPayload.status, "error");
  assert.match(brokenPayload.message, /unknown pricing group id missing_group/i);
  console.log("ok - admin snapshot dry run rejects broken resolver references");

  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
