// Coverage lookup tool.
//
// The customer asks: "do you deliver to X?" / "توصلون X؟" about ONE area.
// Before this tool existed, the LLM was either (a) answering from its
// general Kuwait knowledge (dangerous — our coverage is defined by the
// internal pricing sheet of ~222 areas, not all of Kuwait, so the LLM was
// confidently claiming coverage for Messilah/Bnaider which are not in the
// sheet), or (b) being told by the prompt to ask the customer for the
// OTHER leg first and then call `get_price` (annoying — extra round trip,
// and the LLM was still orchestrating the tool routing through prompt
// rules instead of server-grounded facts).
//
// The clean architectural split for coverage-of-a-single-area questions:
//
//   * LLM owns meaning and wording:
//       "the customer is asking whether we serve X → call check_area_coverage
//        with X → author a reply from the tool result."
//   * Tool owns grounded business truth:
//       runs the same resolver `get_price` uses against the live pricing
//       sheet and returns covered / suggested / ambiguous / not_covered.
//       Known landmarks are resolved to their underlying covered area;
//       unknown place-like queries return `needs_area_for_place` instead
//       of a false "not covered" denial.
//   * Server owns context preservation: the tool stores a tiny
//       coveragePending object in the existing per-conversation guard
//       session. It does not mutate booking/controller state, does not
//       set requested slots, and does not author customer-facing text.
//   * Guards can still block a false positive: if the LLM ever ignores
//       this tool and writes "we deliver to X" for an uncovered X, a
//       separate outbound coverage-claim guard (Phase B, landed later)
//       refuses the turn and lets the LLM retry.
//
// Reply-authoring trade-off:
//
//   We deliberately keep the tool's output minimal (status + canonical
//   name + nearby covered areas) rather than returning a prebuilt
//   customer-facing sentence. The LLM is better at adapting tone,
//   language (EN / AR / Kuwaiti dialect), and contextual follow-ups than
//   a server template would be. The tool's job is truth; the LLM's job
//   is wording.

import type { ToolDeps } from "./deps";

type CoverageStatus =
  | "covered"
  | "landmark_mapped"
  | "place_area_resolved"
  | "suggested"
  | "ambiguous"
  | "needs_area_for_place"
  | "nearby_suggestions"
  | "nearby_unavailable"
  | "not_covered";

interface CoverageResultCovered {
  status: "covered";
  query: string;
  area_id: number;
  canonical_en: string;
  canonical_ar: string;
  resolved_from_pending?: {
    kind: "ambiguous_area";
    original_query: string;
  };
}

interface CoverageResultLandmarkMapped {
  status: "landmark_mapped";
  query: string;
  landmark: {
    canonical_en: string;
  };
  area: {
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
  };
}

interface CoverageResultPlaceAreaResolved {
  status: "place_area_resolved";
  query: string;
  place: {
    query: string;
    canonical_en: string | null;
  };
  area: {
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
  };
}

interface CoverageResultSuggested {
  status: "suggested";
  query: string;
  suggested_area: {
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
  };
  alternative_areas: Array<{
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
  }>;
}

interface CoverageResultAmbiguous {
  status: "ambiguous";
  query: string;
  options: Array<{
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
  }>;
}

interface CoverageResultNeedsArea {
  status: "needs_area_for_place";
  query: string;
  place: {
    query: string;
    canonical_en: string | null;
  };
  reason: "landmark_or_place_not_area";
  ask_for: "area_name";
}

interface CoverageResultNearbySuggestions {
  status: "nearby_suggestions";
  query: string;
  unsupported_query: string;
  nearby_covered: Array<{
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
    similarity: number;
  }>;
}

interface CoverageResultNearbyUnavailable {
  status: "nearby_unavailable";
  query: string;
  unsupported_query: string;
  nearby_covered: [];
}

interface CoverageResultNotCovered {
  status: "not_covered";
  query: string;
  can_suggest_nearby: boolean;
  nearby_covered: Array<{
    area_id: number;
    canonical_en: string;
    canonical_ar: string;
    similarity: number;
  }>;
}

type CoverageResult =
  | CoverageResultCovered
  | CoverageResultLandmarkMapped
  | CoverageResultPlaceAreaResolved
  | CoverageResultSuggested
  | CoverageResultAmbiguous
  | CoverageResultNeedsArea
  | CoverageResultNearbySuggestions
  | CoverageResultNearbyUnavailable
  | CoverageResultNotCovered;

type CoverageAreaOption = {
  area_id: number;
  canonical_en: string;
  canonical_ar: string;
};

type CoverageNearbyOption = CoverageResultNotCovered["nearby_covered"][number];

type CoveragePending =
  | {
      kind: "covered_area_candidate";
      original_query: string;
      area: CoverageAreaOption;
      source_status:
        | "covered"
        | "suggested"
        | "landmark_mapped"
        | "place_area_resolved";
      created_at: number;
    }
  | {
      kind: "needs_area_for_place";
      place_query: string;
      place_canonical_en: string | null;
      created_at: number;
    }
  | {
      kind: "ambiguous_area";
      original_query: string;
      options: CoverageAreaOption[];
      created_at: number;
    }
  | {
      kind: "unsupported_area";
      original_query: string;
      nearby_covered: CoverageNearbyOption[];
      created_at: number;
    };

const COVERAGE_PENDING_TTL_MS = 10 * 60_000;

const KNOWN_LANDMARKS: Array<{
  canonical_en: string;
  area_query: string;
  aliases: string[];
}> = [
  {
    canonical_en: "The Avenues Mall",
    area_query: "Rai",
    aliases: [
      "avenues",
      "the avenues",
      "avenues mall",
      "the avenues mall",
      "aveneus",
      "aveneus mall",
      "avenus",
      "avenus mall",
      "المجمع الافنيوز",
      "الافنيوز",
      "الأفنيوز",
      "افنيوز",
      "أفنيوز",
      "مجمع الافنيوز",
      "مجمع الأفنيوز",
    ],
  },
  {
    canonical_en: "360 Mall",
    area_query: "Zahra",
    aliases: [
      "360",
      "360 mall",
      "mall 360",
      "360mall",
      "مول 360",
      "مجمع 360",
      "٣٦٠",
      "مول ٣٦٠",
      "مجمع ٣٦٠",
    ],
  },
];

const PLACE_HINT_WORDS = [
  "mall",
  "complex",
  "tower",
  "hospital",
  "clinic",
  "airport",
  "university",
  "school",
  "restaurant",
  "cafe",
  "hotel",
  "store",
  "shop",
  "avenues",
  "360",
  "مول",
  "مجمع",
  "مستشفى",
  "مطار",
  "جامعة",
  "مدرسة",
  "مطعم",
  "كافيه",
  "فندق",
  "الافنيوز",
  "افنيوز",
];

function normalizeLandmarkQuery(raw: string): string {
  return String(raw || "")
    .toLowerCase()
    .replace(/[أإآٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)))
    .replace(/[’']/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function findKnownLandmark(query: string):
  | { canonical_en: string; area_query: string }
  | null {
  const normalized = normalizeLandmarkQuery(query);
  if (!normalized) return null;
  for (const landmark of KNOWN_LANDMARKS) {
    if (
      landmark.aliases.some(
        (alias) => normalizeLandmarkQuery(alias) === normalized,
      )
    ) {
      return {
        canonical_en: landmark.canonical_en,
        area_query: landmark.area_query,
      };
    }
  }
  return null;
}

function looksLikePlaceOrLandmark(query: string): boolean {
  const normalized = normalizeLandmarkQuery(query);
  if (!normalized) return false;
  return PLACE_HINT_WORDS.some((word) =>
    normalized.includes(normalizeLandmarkQuery(word)),
  );
}

function normalizeCoverageToken(raw: string): string {
  return normalizeLandmarkQuery(raw);
}

function areaToOption(area: any): CoverageAreaOption | null {
  const areaId =
    typeof area?.area_id === "number"
      ? area.area_id
      : typeof area?.id === "number"
        ? area.id
        : null;
  const canonicalEn =
    typeof area?.canonical_en === "string"
      ? area.canonical_en
      : typeof area?.name_en === "string"
        ? area.name_en
        : null;
  const canonicalAr =
    typeof area?.canonical_ar === "string"
      ? area.canonical_ar
      : typeof area?.name_ar === "string"
        ? area.name_ar
        : null;
  if (typeof areaId !== "number" || !canonicalEn || !canonicalAr) return null;
  return {
    area_id: areaId,
    canonical_en: canonicalEn,
    canonical_ar: canonicalAr,
  };
}

function isFreshCoveragePending(value: unknown): value is CoveragePending {
  if (!value || typeof value !== "object") return false;
  const createdAt = Number((value as { created_at?: unknown }).created_at || 0);
  return Number.isFinite(createdAt) && Date.now() - createdAt <= COVERAGE_PENDING_TTL_MS;
}

function getCoverageSession(ctx: any, deps: ToolDeps): any | null {
  try {
    return deps.intentGates.getSessionFromCtx(ctx).session || null;
  } catch {
    return null;
  }
}

function setCoveragePending(session: any | null, pending: CoveragePending | null): void {
  if (!session) return;
  if (pending) {
    session.coveragePending = pending;
  } else {
    delete session.coveragePending;
  }
}

function selectPendingAreaOption(
  pending: Extract<CoveragePending, { kind: "ambiguous_area" }>,
  query: string,
): CoverageAreaOption | null {
  const q = normalizeCoverageToken(query);
  if (!q) return null;
  const numeric = Number.parseInt(q, 10);
  if (Number.isFinite(numeric) && numeric >= 1 && numeric <= pending.options.length) {
    return pending.options[numeric - 1] || null;
  }

  const matches = pending.options.filter((option) => {
    const en = normalizeCoverageToken(option.canonical_en);
    const ar = normalizeCoverageToken(option.canonical_ar);
    const tokens = `${en} ${ar}`.split(/\s+/).filter(Boolean);
    return (
      en === q ||
      ar === q ||
      en.includes(q) ||
      ar.includes(q) ||
      tokens.some((token) => token.startsWith(q))
    );
  });
  return matches.length === 1 ? matches[0] : null;
}

function isCoverageCandidateFollowup(query: string): boolean {
  const q = normalizeCoverageToken(query);
  return /^(?:yes|yes pls|yes please|yep|sure|ok|okay|thats it|that's it|that is it|اي|نعم|تمام)$/.test(q) ||
    /\b(?:thats|that's|that is|this is)\s+(?:the\s+)?(?:delivery|dropoff|drop\s*off|area)\b/i.test(query);
}

function isNearbyFollowup(query: string): boolean {
  const q = normalizeCoverageToken(query);
  return /^(?:yes|yes pls|yes please|sure|ok|okay|اي|نعم|تمام)$/.test(q) ||
    /\bnearby\b/i.test(query) ||
    /قريب|قريبه|قريبة|اقرب|أقرب/.test(query);
}

async function resolvePendingCoverageFollowup(params: {
  query: string;
  pending: CoveragePending;
  data: any;
  resolvePricingAreaQuery: (query: string, data: any) => Promise<any>;
}): Promise<CoverageResult | null> {
  const { query, pending, data, resolvePricingAreaQuery } = params;
  if (pending.kind === "covered_area_candidate") {
    if (!isCoverageCandidateFollowup(query)) return null;
    return {
      status: "covered",
      query,
      area_id: pending.area.area_id,
      canonical_en: pending.area.canonical_en,
      canonical_ar: pending.area.canonical_ar,
    };
  }

  if (pending.kind === "ambiguous_area") {
    const selected = selectPendingAreaOption(pending, query);
    if (!selected) return null;
    return {
      status: "covered",
      query,
      area_id: selected.area_id,
      canonical_en: selected.canonical_en,
      canonical_ar: selected.canonical_ar,
      resolved_from_pending: {
        kind: "ambiguous_area",
        original_query: pending.original_query,
      },
    };
  }

  if (pending.kind === "needs_area_for_place") {
    const resolution: any = await resolvePricingAreaQuery(query, data);
    if (resolution && resolution.status === "resolved" && resolution.area) {
      const area = areaToOption(resolution.area);
      if (!area) return null;
      return {
        status: "place_area_resolved",
        query,
        place: {
          query: pending.place_query,
          canonical_en: pending.place_canonical_en,
        },
        area,
      };
    }
    return null;
  }

  if (pending.kind === "unsupported_area" && isNearbyFollowup(query)) {
    if (pending.nearby_covered.length > 0) {
      return {
        status: "nearby_suggestions",
        query,
        unsupported_query: pending.original_query,
        nearby_covered: pending.nearby_covered,
      };
    }
    return {
      status: "nearby_unavailable",
      query,
      unsupported_query: pending.original_query,
      nearby_covered: [],
    };
  }

  return null;
}

export function registerCoverageTools(api: any, deps: ToolDeps): void {
  const { createTextResult, quoting, pricing } = deps;
  const { resolvePricingAreaQuery, collectAreaCandidates } = quoting;
  const { loadPricing } = pricing;

  api.registerTool({
    name: "check_area_coverage",
    label: "Check area coverage",
    description:
      "Check whether Riders delivers to a specific area or known landmark/place. Use this BEFORE answering a single-area coverage question like \"do you deliver to X?\" / \"توصلون X؟\" / \"توصلين لي X؟\". Also use it for short coverage follow-ups that answer the previous coverage clarification (for example `res` after Wafra options, or an area after an unknown mall/place). Returns grounded coverage truth from the live pricing sheet. Accepts English, Arabic, Arabizi, typos, common aliases, and known landmarks such as The Avenues Mall and 360 Mall. Does NOT advance booking state or set requested slots. Use it freely whenever the customer asks about one specific area/place. Do NOT answer coverage from memory: the pricing sheet has ~222 areas and is the ONLY source of truth; your general Kuwait knowledge includes many areas we do NOT serve. After the tool returns, author the reply yourself — short and natural, in the customer's language (Kuwaiti dialect if they wrote Arabic). For `covered`: confirm by the canonical area name and optionally invite them to send the other leg for a quote. For `landmark_mapped`: say the landmark is in the returned area and that we cover that area. For `place_area_resolved`: answer that the place is in the returned area and that the area is covered. For `needs_area_for_place`: do not say we don't cover it; ask which area the place is in. For `suggested`: confirm which area they meant. For `ambiguous`: present the options. For `not_covered`: be honest that we don't currently serve that area. Only mention nearby covered areas if `nearby_covered` is non-empty; otherwise do not offer nearby areas. For `nearby_suggestions`, list the provided covered nearby options. For `nearby_unavailable`, say you do not have nearby covered suggestions for that area.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        area: {
          type: "string",
          description:
            "The area name the customer mentioned, verbatim (Arabic, English, Arabizi, or colloquial). Do NOT translate or normalize — the resolver handles fuzzy matching.",
        },
      },
      required: ["area"],
    },

    async execute(
      _toolCallId: string,
      params: { area: string },
      ctx?: any,
    ) {
      const query = (params?.area || "").trim();
      if (!query) {
        return createTextResult({
          status: "not_covered",
          query: "",
          can_suggest_nearby: false,
          nearby_covered: [],
          error: "empty_area",
        } satisfies CoverageResultNotCovered & { error: string });
      }

      try {
        const data = await loadPricing();
        const areas: any[] = Array.isArray((data as any)?.areas)
          ? (data as any).areas
          : [];
        const session = getCoverageSession(ctx, deps);
        const pending = isFreshCoveragePending(session?.coveragePending)
          ? session.coveragePending
          : null;
        if (session && !pending && session.coveragePending) {
          setCoveragePending(session, null);
        }

        const pendingResult = pending
          ? await resolvePendingCoverageFollowup({
              query,
              pending,
              data,
              resolvePricingAreaQuery,
            })
          : null;
        if (pendingResult) {
          if (pendingResult.status === "covered") {
            setCoveragePending(session, {
              kind: "covered_area_candidate",
              original_query: pendingResult.query,
              area: {
                area_id: pendingResult.area_id,
                canonical_en: pendingResult.canonical_en,
                canonical_ar: pendingResult.canonical_ar,
              },
              source_status: "covered",
              created_at: Date.now(),
            });
          } else if (pendingResult.status === "place_area_resolved") {
            setCoveragePending(session, {
              kind: "covered_area_candidate",
              original_query: pendingResult.query,
              area: pendingResult.area,
              source_status: "place_area_resolved",
              created_at: Date.now(),
            });
          } else if (
            pendingResult.status === "nearby_suggestions" ||
            pendingResult.status === "nearby_unavailable"
          ) {
            setCoveragePending(session, {
              ...pending,
              created_at: Date.now(),
            } as CoveragePending);
          } else {
            setCoveragePending(session, null);
          }
          try {
            console.log(
              `[metric] check_area_coverage.pending_resolved` +
                ` query=${JSON.stringify(query)}` +
                ` status=${pendingResult.status satisfies CoverageStatus}` +
                ` pending_kind=${pending.kind}`,
            );
          } catch {}
          return createTextResult(pendingResult);
        }

        const knownLandmark = findKnownLandmark(query);
        const resolution: any = await resolvePricingAreaQuery(
          knownLandmark?.area_query || query,
          data,
        );

        let result: CoverageResult;

        if (
          knownLandmark &&
          resolution &&
          resolution.status === "resolved" &&
          resolution.area
        ) {
          result = {
            status: "landmark_mapped",
            query,
            landmark: {
              canonical_en: knownLandmark.canonical_en,
            },
            area: {
              area_id: resolution.area.id,
              canonical_en: resolution.area.name_en,
              canonical_ar: resolution.area.name_ar,
            },
          };
        } else if (
          resolution &&
          resolution.status === "resolved" &&
          resolution.area
        ) {
          result = {
            status: "covered",
            query,
            area_id: resolution.area.id,
            canonical_en: resolution.area.name_en,
            canonical_ar: resolution.area.name_ar,
          };
        } else if (
          resolution &&
          resolution.status === "suggested" &&
          resolution.area
        ) {
          const alts = Array.isArray(resolution.alternative_areas)
            ? resolution.alternative_areas
                .filter(
                  (a: any) =>
                    a && typeof a === "object" && typeof a.id === "number",
                )
                .slice(0, 3)
                .map((a: any) => ({
                  area_id: a.id,
                  canonical_en: a.name_en,
                  canonical_ar: a.name_ar,
                }))
            : [];
          result = {
            status: "suggested",
            query,
            suggested_area: {
              area_id: resolution.area.id,
              canonical_en: resolution.area.name_en,
              canonical_ar: resolution.area.name_ar,
            },
            alternative_areas: alts,
          };
        } else if (
          resolution &&
          resolution.status === "ambiguous" &&
          Array.isArray(resolution.options)
        ) {
          const options = resolution.options
            .filter(
              (o: any) =>
                o && typeof o === "object" && typeof o.area_id === "number",
            )
            .slice(0, 6)
            .map((o: any) => ({
              area_id: o.area_id,
              canonical_en: o.name_en,
              canonical_ar: o.name_ar,
            }));
          result = {
            status: "ambiguous",
            query,
            options,
          };
        } else if (looksLikePlaceOrLandmark(query)) {
          result = {
            status: "needs_area_for_place",
            query,
            place: {
              query,
              canonical_en: knownLandmark?.canonical_en || null,
            },
            reason: "landmark_or_place_not_area",
            ask_for: "area_name",
          };
        } else {
          const candidates = collectAreaCandidates(query, areas, { topK: 3 });
          const nearby = candidates
            .filter(
              (c: any) =>
                c &&
                c.area &&
                typeof c.area.id === "number" &&
                typeof c.similarity === "number",
            )
            .map((c: any) => ({
              area_id: c.area.id,
              canonical_en: c.area.name_en,
              canonical_ar: c.area.name_ar,
              similarity: Number(c.similarity.toFixed(3)),
            }));
          result = {
            status: "not_covered",
            query,
            can_suggest_nearby: nearby.length > 0,
            nearby_covered: nearby,
          };
        }

        if (result.status === "covered") {
          setCoveragePending(session, {
            kind: "covered_area_candidate",
            original_query: result.query,
            area: {
              area_id: result.area_id,
              canonical_en: result.canonical_en,
              canonical_ar: result.canonical_ar,
            },
            source_status: result.resolved_from_pending
              ? "suggested"
              : "covered",
            created_at: Date.now(),
          });
        } else if (result.status === "suggested") {
          setCoveragePending(session, {
            kind: "covered_area_candidate",
            original_query: result.query,
            area: result.suggested_area,
            source_status: "suggested",
            created_at: Date.now(),
          });
        } else if (result.status === "landmark_mapped") {
          setCoveragePending(session, {
            kind: "covered_area_candidate",
            original_query: result.query,
            area: result.area,
            source_status: "landmark_mapped",
            created_at: Date.now(),
          });
        } else if (result.status === "needs_area_for_place") {
          setCoveragePending(session, {
            kind: "needs_area_for_place",
            place_query: result.query,
            place_canonical_en: result.place.canonical_en,
            created_at: Date.now(),
          });
        } else if (result.status === "ambiguous" && result.options.length > 0) {
          setCoveragePending(session, {
            kind: "ambiguous_area",
            original_query: result.query,
            options: result.options,
            created_at: Date.now(),
          });
        } else if (result.status === "not_covered") {
          setCoveragePending(session, {
            kind: "unsupported_area",
            original_query: result.query,
            nearby_covered: result.nearby_covered,
            created_at: Date.now(),
          });
        } else {
          setCoveragePending(session, null);
        }

        try {
          console.log(
            `[metric] check_area_coverage` +
              ` query=${JSON.stringify(query)}` +
              ` status=${result.status satisfies CoverageStatus}` +
              ` canonical_en=${JSON.stringify(
                result.status === "covered"
                  ? result.canonical_en
                  : result.status === "landmark_mapped"
                    ? result.area.canonical_en
                  : result.status === "suggested"
                    ? result.suggested_area.canonical_en
                    : null,
              )}`,
          );
        } catch {}

        return createTextResult(result);
      } catch (err) {
        try {
          console.log(
            `[metric] check_area_coverage.error` +
              ` query=${JSON.stringify(query)}` +
              ` error=${JSON.stringify(
                err instanceof Error ? err.message : String(err),
              )}`,
          );
        } catch {}
        return createTextResult({
          status: "not_covered",
          query,
          can_suggest_nearby: false,
          nearby_covered: [],
          error: "coverage_lookup_failed",
        } satisfies CoverageResultNotCovered & { error: string });
      }
    },
  });
}
