#!/usr/bin/env node
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { deliveryRoot } from "./_helpers/riders-plugin-loader.mjs";

const execFileAsync = promisify(execFile);

function parseEnvFile(raw) {
  const result = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }
    const key = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1);
    result[key] = value;
  }
  return result;
}

async function copyFile(sourcePath, targetPath) {
  await fs.mkdir(path.dirname(targetPath), { recursive: true });
  await fs.copyFile(sourcePath, targetPath);
}

function buildBootstrapEnvFile(envExample) {
  const keys = [
    "OPENCLAW_PROFILE",
    "OPENCLAW_GATEWAY_TOKEN",
    "RIDERS_PRICING_SOURCE_MODE",
    "RIDERS_PRICING_PUBLISHED_PATH",
    "RIDERS_PRICING_RESOLVER_OVERLAY_PATH",
    "RIDERS_PRICING_SHEET_ID",
    "RIDERS_PRICING_SHEET_NAME",
    "RIDERS_PRICING_SHEET_HEADER_ROW",
    "RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH",
  ];
  const lines = [];
  for (const key of keys) {
    if (envExample[key] !== undefined) {
      lines.push(`${key}=${envExample[key]}`);
    }
  }
  if (!envExample.OPENCLAW_GATEWAY_TOKEN) {
    lines.push("OPENCLAW_GATEWAY_TOKEN=CHANGE_ME_DELIVERY_TOKEN");
  }
  return `${lines.join("\n")}\n`;
}

async function main() {
  const envExamplePath = path.join(deliveryRoot, ".env.example");
  const templatePath = path.join(deliveryRoot, "openclaw.template.json");
  const pluginSchemaPath = path.join(deliveryRoot, "plugins/riders-tools/openclaw.plugin.json");
  const bootstrapPath = path.join(deliveryRoot, "scripts/bootstrap-profile.sh");
  const deployPath = path.join(deliveryRoot, "scripts/deploy.sh");

  const envExample = parseEnvFile(await fs.readFile(envExamplePath, "utf-8"));
  assert.equal(envExample.RIDERS_PRICING_SOURCE_MODE, "published_preferred");
  assert.match(envExample.RIDERS_PRICING_PUBLISHED_PATH, /pricing\.published\.json$/);
  assert.match(envExample.RIDERS_PRICING_RESOLVER_OVERLAY_PATH, /pricing\.resolver\.overlay\.json$/);
  console.log("ok - .env.example defaults to published snapshot + resolver overlay");

  const pluginSchema = JSON.parse(await fs.readFile(pluginSchemaPath, "utf-8"));
  assert.equal(
    pluginSchema.configSchema.properties.pricing.properties.resolverOverlayPath.type,
    "string",
  );
  console.log("ok - plugin schema exposes resolverOverlayPath");

  const template = JSON.parse(await fs.readFile(templatePath, "utf-8"));
  const templatePricing = template.plugins.entries["riders-tools"].config.pricing;
  assert.equal(templatePricing.sourceMode, "published_preferred");
  assert.match(templatePricing.publishedPath, /pricing\.published\.json$/);
  assert.match(templatePricing.resolverOverlayPath, /pricing\.resolver\.overlay\.json$/);
  console.log("ok - openclaw template defaults to published snapshot + resolver overlay");

  const deployScript = await fs.readFile(deployPath, "utf-8");
  assert.match(deployScript, /pricing\.resolver\.overlay\.json/);
  assert.match(deployScript, /RIDERS_PRICING_RESOLVER_OVERLAY_PATH/);
  assert.match(deployScript, /published_preferred/);
  console.log("ok - deploy script persists overlay path and published_preferred defaults");

  const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "pricing-config-audit-"));
  const tempProjectDir = path.join(tempRoot, "delivery");
  const tempHomeDir = path.join(tempRoot, "home");
  await fs.mkdir(path.join(tempProjectDir, "scripts"), { recursive: true });
  await fs.mkdir(tempHomeDir, { recursive: true });
  await fs.writeFile(path.join(tempProjectDir, ".env"), buildBootstrapEnvFile(envExample), "utf-8");
  await copyFile(templatePath, path.join(tempProjectDir, "openclaw.template.json"));
  await copyFile(bootstrapPath, path.join(tempProjectDir, "scripts/bootstrap-profile.sh"));

  await execFileAsync("zsh", [path.join(tempProjectDir, "scripts/bootstrap-profile.sh"), "--force"], {
    cwd: tempProjectDir,
    env: {
      ...process.env,
      HOME: tempHomeDir,
    },
    maxBuffer: 10 * 1024 * 1024,
  });

  const generatedConfigPath = path.join(tempHomeDir, ".openclaw-delivery/openclaw.json");
  const generatedConfig = JSON.parse(await fs.readFile(generatedConfigPath, "utf-8"));
  const generatedPricing = generatedConfig.plugins.entries["riders-tools"].config.pricing;
  assert.equal(generatedPricing.sourceMode, "published_preferred");
  assert.match(generatedPricing.publishedPath, /pricing\.published\.json$/);
  assert.match(generatedPricing.resolverOverlayPath, /pricing\.resolver\.overlay\.json$/);
  console.log("ok - bootstrap profile generation preserves published snapshot + overlay config");

  await fs.rm(tempRoot, { recursive: true, force: true });
  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
