#!/usr/bin/env node

const baseUrl = (process.env.RIDERS_API_BASE_URL || "https://order-riders.trywebsight.com/api").replace(/\/+$/, "");
const apiKey = (process.env.RIDERS_API_KEY || "").trim();
const bearer = (process.env.RIDERS_BEARER_TOKEN || apiKey || "").trim();

if (!apiKey) {
  console.error("RIDERS_API_KEY is not configured");
  process.exit(1);
}

async function ridersRequest(endpoint) {
  const headers = {
    Accept: "application/json",
    "x-api-key": apiKey,
  };
  if (bearer) headers.Authorization = `Bearer ${bearer}`;

  const res = await fetch(`${baseUrl}${endpoint}`, { headers });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${typeof data === "string" ? data : JSON.stringify(data)}`);
  }
  return data;
}

function normalizeName(value) {
  return String(value || "").toLowerCase();
}

async function run() {
  const govsPayload = await ridersRequest("/geo/govs");
  const govs = Array.isArray(govsPayload?.data) ? govsPayload.data : [];

  const allAreas = [];
  for (const gov of govs) {
    const areasPayload = await ridersRequest(`/geo/areas?governorate_id=${encodeURIComponent(String(gov.id))}`);
    const areas = Array.isArray(areasPayload?.data) ? areasPayload.data : [];
    for (const area of areas) {
      allAreas.push({
        governorate_id: gov.id,
        governorate_name: gov.name,
        area_id: area.id,
        area_name: area.name,
        shipping_methods: Array.isArray(area.shipping_methods) ? area.shipping_methods : [],
      });
    }
  }

  const methodMap = new Map();
  for (const area of allAreas) {
    for (const method of area.shipping_methods) {
      const key = `${method.id}|${method.name}|${method.type || ""}`;
      if (!methodMap.has(key)) {
        methodMap.set(key, {
          id: method.id,
          name: method.name,
          type: method.type || null,
          areas: 0,
          governorates: new Set(),
          sample_areas: [],
        });
      }
      const entry = methodMap.get(key);
      entry.areas += 1;
      entry.governorates.add(area.governorate_name);
      if (entry.sample_areas.length < 5) {
        entry.sample_areas.push(`${area.area_name} (${area.governorate_name})`);
      }
    }
  }

  const methods = Array.from(methodMap.values())
    .map((entry) => ({
      id: entry.id,
      name: entry.name,
      type: entry.type,
      area_count: entry.areas,
      governorate_count: entry.governorates.size,
      sample_areas: entry.sample_areas,
    }))
    .sort((a, b) => a.id - b.id || a.name.localeCompare(b.name));

  const keywordHits = methods.filter((method) => {
    const value = normalizeName(`${method.name} ${method.type || ""}`);
    return (
      value.includes("cool") ||
      value.includes("refrig") ||
      value.includes("cold") ||
      value.includes("helper") ||
      value.includes("assist") ||
      value.includes("car") ||
      value.includes("van")
    );
  });

  const areaSamples = ["Dasman", "Mansouriya", "Airport", "Northern Artificial island"]
    .map((name) => {
      const area = allAreas.find((item) => normalizeName(item.area_name) === normalizeName(name));
      return area
        ? {
            area_name: area.area_name,
            governorate_name: area.governorate_name,
            shipping_methods: area.shipping_methods.map((method) => ({
              id: method.id,
              name: method.name,
              type: method.type || null,
              default_price: method.default_price ?? null,
              price: method.price ?? null,
            })),
          }
        : { area_name: name, error: "not found" };
    });

  console.log(
    JSON.stringify(
      {
        governorate_count: govs.length,
        area_count: allAreas.length,
        distinct_shipping_methods: methods,
        keyword_method_hits: keywordHits,
        sample_area_methods: areaSamples,
      },
      null,
      2,
    ),
  );
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
