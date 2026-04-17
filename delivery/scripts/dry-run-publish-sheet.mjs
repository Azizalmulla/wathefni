#!/usr/bin/env node
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  loadPluginRegistrations,
} from "./_helpers/riders-plugin-loader.mjs";

const execFileAsync = promisify(execFile);
const GOG_BIN = process.env.GOG_BIN || "gog";
const SPREADSHEET_ID = process.env.RIDERS_PRICING_SHEET_ID || "";
const SHEET_NAME = process.env.RIDERS_PRICING_SHEET_NAME || "";
const HEADER_ROW = parseInt(process.env.RIDERS_PRICING_SHEET_HEADER_ROW || "1", 10);
const PUBLISHED_PATH =
  process.env.RIDERS_PRICING_PUBLISHED_PATH || defaultPublishedPricingPath;
const OVERLAY_PATH =
  process.env.RIDERS_PRICING_RESOLVER_OVERLAY_PATH || defaultResolverOverlayPath;
const LIVE_PUBLISH = /^(1|true|yes|on)$/i.test(process.env.PUBLISH_LIVE || "");

function buildCommandEnv() {
  const nextEnv = { ...process.env };
  if (process.env.GOG_ACCOUNT) {
    nextEnv.GOG_ACCOUNT = process.env.GOG_ACCOUNT;
  }
  if (process.env.GOG_KEYRING_PASSWORD) {
    nextEnv.GOG_KEYRING_PASSWORD = process.env.GOG_KEYRING_PASSWORD;
  }
  if (process.env.GOG_CLIENT) {
    nextEnv.GOG_CLIENT = process.env.GOG_CLIENT;
  }
  return nextEnv;
}

async function fetchRows() {
  const { stdout } = await execFileAsync(
    GOG_BIN,
    ["sheets", "get", SPREADSHEET_ID, SHEET_NAME, "--json"],
    {
      env: buildCommandEnv(),
      maxBuffer: 20 * 1024 * 1024,
    },
  );
  const payload = JSON.parse(stdout || "{}");
  const values = Array.isArray(payload.values) ? payload.values : [];
  if (!values.length) {
    return [];
  }
  const headers = values[Math.max(0, HEADER_ROW - 1)] || [];
  return values.slice(HEADER_ROW).map((cells) => {
    const row = {};
    headers.forEach((header, index) => {
      row[String(header)] = cells[index] ?? "";
    });
    return row;
  });
}

async function run() {
  if (!SPREADSHEET_ID || !SHEET_NAME) {
    throw new Error("RIDERS_PRICING_SHEET_ID and RIDERS_PRICING_SHEET_NAME are required.");
  }

  const rows = await fetchRows();
  console.log(`Fetched ${rows.length} raw rows from Google Sheets.`);

  const tools = await loadPluginRegistrations(import.meta.url, {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: PUBLISHED_PATH,
        resolverOverlayPath: OVERLAY_PATH,
        adminAllowlist: [],
        googleSheet: {
          spreadsheetId: SPREADSHEET_ID,
          sheetName: SHEET_NAME,
          headerRow: HEADER_ROW,
        },
      },
    });

  const ctx = {
    senderIsOwner: true,
    requesterSenderId: "admin:test",
  };

  const publishFactory = tools.find((tool) => {
    if (typeof tool === "function") {
      const built = tool(ctx);
      return built?.name === "admin_publish_pricing_sheet_rows";
    }
    return tool?.name === "admin_publish_pricing_sheet_rows";
  });

  if (!publishFactory) {
    throw new Error("admin_publish_pricing_sheet_rows tool not found after plugin registration");
  }

  const publishTool = typeof publishFactory === "function" ? publishFactory(ctx) : publishFactory;
  const result = await publishTool.execute(LIVE_PUBLISH ? "publish" : "dry-run", {
    rows,
    dry_run: !LIVE_PUBLISH,
    currency: "KWD",
    last_updated: new Date().toISOString(),
  });

  const text = result?.content?.find?.((item) => item?.type === "text")?.text || "";
  console.log("\n=== Tool Result ===\n");
  console.log(text);
}

run().catch((err) => {
  console.error(`Failed: ${err.message}`);
  process.exit(1);
});
