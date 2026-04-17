import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

export const deliveryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const ridersPluginPath = path.join(deliveryRoot, "plugins/riders-tools/index.ts");
export const defaultPublishedPricingPath = path.join(
  deliveryRoot,
  "workspaces/riders/data/pricing.published.json",
);
export const defaultResolverOverlayPath = path.join(
  deliveryRoot,
  "workspaces/riders/data/pricing.resolver.overlay.json",
);

function resolveJitiPath() {
  const candidates = [
    path.join(deliveryRoot, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
    process.env.OPENCLAW_JITI_PATH?.trim() || "",
    process.env.OPENCLAW_GLOBAL_JITI_PATH?.trim() || "",
    path.join(process.env.HOME || "", ".npm-global/lib/node_modules/openclaw/node_modules/jiti/lib/jiti.cjs"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    "Unable to locate jiti. Run `npm install` in delivery/plugins/riders-tools or set OPENCLAW_JITI_PATH.",
  );
}

export function createJiti(importMetaUrl) {
  const jitiFactory = require(resolveJitiPath());
  return jitiFactory(importMetaUrl, { interopDefault: true });
}

export async function loadRidersToolsModule(importMetaUrl) {
  const jiti = createJiti(importMetaUrl);
  return await jiti(ridersPluginPath);
}

export async function loadPluginRegistrations(importMetaUrl, pluginConfig) {
  const registrations = [];
  const api = {
    pluginConfig,
    registerTool(definition) {
      registrations.push(definition);
    },
    on() {},
  };

  const mod = await loadRidersToolsModule(importMetaUrl);
  const register = mod.default || mod;
  register(api);
  return registrations;
}

export async function resolveRegisteredTool(importMetaUrl, name, pluginConfig, ctx = {}) {
  const registrations = await loadPluginRegistrations(importMetaUrl, pluginConfig);
  for (const registration of registrations) {
    const tool = typeof registration === "function" ? registration(ctx) : registration;
    if (tool?.name === name) {
      return tool;
    }
  }
  throw new Error(`Tool ${name} not found`);
}

export function parseToolText(text) {
  try {
    return { json: JSON.parse(text), raw: text };
  } catch {
    return { json: null, raw: text };
  }
}
