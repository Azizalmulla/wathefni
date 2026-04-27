#!/usr/bin/env node
/**
 * Validates that every priced published area can be converted into the same
 * Grid ordering address payload used by create_simple_order.
 *
 * Requires RIDERS_GRID_API_KEY or RIDERS_API_KEY.
 */
import { loadRidersToolsModule } from "./_helpers/riders-plugin-loader.mjs";

const mod = await loadRidersToolsModule(import.meta.url);
const hooks = mod.__resolverTestHooks;
if (!hooks?.validatePublishedPricingOrderingMappings) {
  throw new Error("Ordering mapping validation hook is not exported");
}

const result = await hooks.validatePublishedPricingOrderingMappings();
if (!result.ok) {
  console.error(
    `FAIL - ${result.issue_count}/${result.checked_area_count} published pricing areas cannot map to Grid ordering payloads`,
  );
  for (const issue of result.issues.slice(0, 50)) {
    console.error(
      [
        `area=${issue.area_name_en || issue.area_name_ar}`,
        `id=${issue.area_id ?? "n/a"}`,
        `stage=${issue.stage}`,
        `pricing_governorate=${issue.pricing_governorate}`,
        `grid_governorate=${issue.grid_governorate ?? "n/a"}`,
        `message=${issue.message}`,
      ].join(" | "),
    );
  }
  if (result.issues.length > 50) {
    console.error(`... ${result.issues.length - 50} more issues`);
  }
  process.exit(1);
}

console.log(
  `ok - ${result.checked_area_count} published pricing areas map to Grid ordering payloads`,
);
