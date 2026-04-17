#!/usr/bin/env node
/**
 * Quick test: fetch rows from the Riders pricing Google Sheet
 * using the configured gog account.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const GOG_BIN = process.env.GOG_BIN || "gog";
const SPREADSHEET_ID = process.env.RIDERS_PRICING_SHEET_ID || "";
const SHEET_NAME = process.env.RIDERS_PRICING_SHEET_NAME || "";
const HEADER_ROW = parseInt(process.env.RIDERS_PRICING_SHEET_HEADER_ROW || "1", 10);

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

async function fetchValues() {
  const { stdout } = await execFileAsync(
    GOG_BIN,
    ["sheets", "get", SPREADSHEET_ID, SHEET_NAME, "--json"],
    {
      env: buildCommandEnv(),
      maxBuffer: 20 * 1024 * 1024,
    },
  );
  const payload = JSON.parse(stdout || "{}");
  return Array.isArray(payload.values) ? payload.values : [];
}

async function run() {
  if (!SPREADSHEET_ID || !SHEET_NAME) {
    throw new Error("RIDERS_PRICING_SHEET_ID and RIDERS_PRICING_SHEET_NAME are required.");
  }

  const values = await fetchValues();

  if (values.length === 0) {
    console.log("Sheet returned 0 rows.");
    return;
  }

  const headerIdx = HEADER_ROW - 1;
  const headers = values[headerIdx] || [];
  const dataRows = values.slice(headerIdx + 1);

  console.log(`Fetching: ${SHEET_NAME} from spreadsheet ${SPREADSHEET_ID.slice(0, 12)}...`);
  console.log(`\nHeaders (row ${HEADER_ROW}): ${JSON.stringify(headers)}`);
  console.log(`Data rows: ${dataRows.length}`);
  console.log(`\nFirst 3 rows:`);

  for (let i = 0; i < Math.min(3, dataRows.length); i++) {
    const row = {};
    headers.forEach((h, j) => {
      row[h] = dataRows[i][j] || "";
    });
    console.log(JSON.stringify(row, null, 2));
  }
}

run().catch((err) => {
  console.error(`Failed: ${err.message}`);
  process.exit(1);
});
