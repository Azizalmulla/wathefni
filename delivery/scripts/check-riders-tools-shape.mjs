#!/usr/bin/env node
// Lightweight shape check: loads the riders-tools plugin via jiti, calls
// `register(api)` with a stub API, and verifies that the expected set of tool
// names is registered. Used as a gate between surgical extractions in the
// Wave 1a tool split.

import assert from "node:assert/strict";
import { loadPluginRegistrations } from "./_helpers/riders-plugin-loader.mjs";

const EXPECTED_TOOLS = [
  "get_price",
  "track_order",
  "create_simple_order",
  "create_order",
  "pay_order",
  "cancel_order",
  "shadow_extract_booking_fields",
  "apply_booking_field",
  "start_booking",
  "confirm_summary",
  "cancel_booking",
  "request_handoff",
  "offers",
  "admin_pricing_source_status",
  "admin_validate_pricing_resolver_overlay",
  "admin_refresh_pricing_cache",
  "admin_behavior_policy_status",
  "admin_refresh_behavior_policy_cache",
  "admin_view_behavior_policy",
  "admin_publish_behavior_policy",
  "admin_set_behavior_live_instructions",
  "admin_add_behavior_reply_correction",
  "admin_add_behavior_flow_rule",
  "admin_add_behavior_phrase_guard",
  "admin_disable_behavior_rule",
  "admin_delete_behavior_rule",
  "admin_publish_pricing_snapshot",
  "admin_publish_pricing_sheet_rows",
  "admin_add_pricing_area_to_google_sheet",
  "admin_update_area_price_in_google_sheet",
  "admin_update_area_price",
  "admin_fetch_google_sheet_rows",
  "admin_fetch_google_sheet_metadata",
  "admin_update_google_sheet_values",
  "admin_batch_update_google_sheet",
  "admin_clear_google_sheet_values",
  "admin_append_google_sheet_rows",
  "admin_delete_google_sheet_rows",
  "complains",
  "assign_agent",
  "admin_list_workspace_files",
  "admin_read_workspace_file",
  "admin_write_workspace_file",
];

const stubCtx = {
  requesterSenderId: "shape-check",
  senderIsOwner: true,
};

async function main() {
  const registrations = await loadPluginRegistrations(import.meta.url, {});
  const names = new Set();
  for (const registration of registrations) {
    const tool =
      typeof registration === "function" ? registration(stubCtx) : registration;
    if (tool && typeof tool.name === "string") {
      names.add(tool.name);
    }
  }

  const missing = EXPECTED_TOOLS.filter((name) => !names.has(name));
  const unexpected = [...names].filter((name) => !EXPECTED_TOOLS.includes(name));

  if (missing.length > 0 || unexpected.length > 0) {
    if (missing.length > 0) {
      console.error(`Missing tools: ${missing.join(", ")}`);
    }
    if (unexpected.length > 0) {
      console.error(`Unexpected tools: ${unexpected.join(", ")}`);
    }
    process.exit(1);
  }

  assert.equal(names.size, EXPECTED_TOOLS.length);
  console.log(
    `Riders-tools plugin shape OK: ${names.size} tools registered as expected.`,
  );
}

main()
  .then(() => {
    // The plugin's guard hook installs a setInterval keep-alive that would
    // otherwise prevent this script from terminating. Force-exit on success.
    process.exit(0);
  })
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
