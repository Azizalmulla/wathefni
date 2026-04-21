// Shared dependency shape for extracted tool registration modules.
//
// During Wave 1a of the plugin split, the `api.registerTool(...)` blocks
// moved out of `plugins/riders-tools/index.ts` keep using helpers and
// mutable state that still live inside that file. Rather than creating
// cross-file imports that would force index.ts to expose internals, each
// extracted module receives the helpers it needs via a typed `deps`
// object constructed inside `register(api)`.
//
// Each tool group (pricing, booking, admin-*, support, guards) accesses
// only the subset it needs. The interface grows exactly as new extractions
// surface new dependencies; nothing speculative is added here.

export interface ToolDeps {
  // ---- rendering helpers ----
  createTextResult: (
    payload: unknown,
    details?: unknown,
  ) => {
    content: Array<{ type: string; text: string }>;
    details?: unknown;
  };
    errorPayload: (err: unknown) => {
      status: string;
      message: string;
      http_status?: number;
      details?: unknown;
    };

  // ---- admin authorization ----
  assertAdminAuthorized: (ctx: {
    requesterSenderId?: string;
    senderIsOwner?: boolean;
  }) => void;
  assertPricingAdminAuthorized: (ctx: {
    requesterSenderId?: string;
    senderIsOwner?: boolean;
  }) => void;
  isAdminSender: (senderId: string | null | undefined) => boolean;

  // ---- generic helpers shared across admin tool groups ----
  isRecord: (value: unknown) => value is Record<string, unknown>;
  runGogJsonCommand: (args: string[], commandLabel: string) => Promise<unknown>;

  // ---- live pricing-sheet identity (mutable, refreshed by applyPluginConfig) ----
  getPricingGoogleSheetSpreadsheetId: () => string;
  getPricingGoogleSheetName: () => string;

  // ---- intent-gate helpers ----
  // Shared closures built inside register() that classify the customer
  // context. Used by get_price, the booking tools, and the customer
  // support tools. Closures over the main register()-scope conversation
  // controller / session state; do not re-implement in callers.
  intentGates: {
    isCustomerOctopusContext: (ctx: any) => boolean;
    getVisibleCustomerText: (ctx: any) => string;
    getCustomerTurnActionHint: (ctx: any) => string;
    getNormalizedBookingAuthority: (ctx: any) => {
      stage: string;
      bookingStep: string;
      controller: any;
    };
    isActiveBookingFlow: (stage: string, bookingStep: string) => boolean;
    customerExplicitlyRequestsHuman: (text: string) => boolean;
    assignAgentReasonLooksLegitimate: (reason: string) => boolean;
    hasStrictTrackingOrderId: (text: string) => boolean;
    hasFreshLastQuotedRoute: (route: any) => boolean;
    getSessionFromCtx: (ctx: any) => {
      key: string;
      aliases: string[];
      session: any;
    };
  };

  // ---- pricing admin helpers ----
  // Loosely typed to match the current public surface in index.ts; wave
  // 1b will tighten these once the helpers move into lib/pricing-*.
  pricing: {
    getPricingSourceStatus: () => Promise<{
      active_source: string;
      published_path: string | null;
      last_updated: string | null;
      [key: string]: unknown;
    }>;
    loadPricingBaseDataForStatus: () => Promise<any>;
      inspectPricingResolverOverlay: (baseData: any) => Promise<{
      status: any;
      mergedResolver?: any;
    }>;
    summarizePricingResolver: (resolver: any) => any;
    clearPricingCache: () => void;
    loadPricing: (options?: { skipAutoSync?: boolean }) => Promise<any>;
    loadPricingFallbackData: () => Promise<any>;
    writePublishedPricing: (data: any) => Promise<void>;
    buildPublishedPricingData: (params: any, fallback: any) => any;
    resolvePublishedAreasInput: (params: any) => unknown[];
      resolvePublishedColumnsInput: (params: any) => any;
    resolvePublishedResolverInput: (params: any) => Record<string, unknown> | null;
    resolveSheetRowsInput: (params: any) => unknown[];
    resolveSheetHeaderMapInput: (params: any) => Record<string, string> | null;
      normalizeSheetRowsToPublishedAreas: (
      rows: unknown[],
      headerMap: any,
    ) => { areas: any[]; skipped_row_count: number };
    resolveAdminPricingArea: (params: any, areas: any[]) => any;
    normalizePricingNumber: (value: number) => number;
    isPricingGoogleSheetConfigured: () => boolean;
    executeAdminAddPricingAreaToGoogleSheet: (
      ctx: any,
      params: any,
    ) => Promise<unknown>;
    executeAdminGoogleSheetPriceUpdate: (
      ctx: any,
      params: any,
    ) => Promise<unknown>;
  };

  // ---- quote / route-pricing helpers ----
  // Used by get_price (and later the booking tools) to resolve areas and
  // build the customer-facing quote payload. All loosely typed; wave 1b
  // will tighten these once the helpers move into lib/pricing-resolver.ts
  // and lib/area-matching.ts.
  quoting: {
    extractAreaTokensFromText: (text: string) => {
      pickup: string | null;
      dropoff: string | null;
    };
    collectAreaEvidenceFromText: (text: string, data: any) => Set<number>;
    verifyAreaEvidence: (params: any) => any;
    createAreaSuggestionResult: (params: any) => any;
    createAreaNotFoundResult: (params: any) => any;
    createAreaNeedsClarificationResult: (params: any) => any;
    createAreaClarificationResult: (params: any) => any;
    collectAreaCandidates: (
      query: string,
      areas: any[],
      options?: { topK?: number; minSimilarity?: number },
    ) => Array<{ area: any; similarity: number }>;
    resolvePricingAreaQuery: (query: string, data: any) => Promise<any>;
    getBidirectionalRoutePrices: (pickup: any, dropoff: any) => any;
    getSpecialDeliveryCapabilities: () => Promise<any>;
    resolveAreaForOrdering: (query: string) => Promise<any>;
    getCommonShippingMethods: (pickup: any[], dropoff: any[]) => any[];
      selectShippingMethod: (methods: any[], deliveryType: any) => any;
      summarizeLiveDeliveryOption: (
      deliveryType: any,
      method: any,
      currency: string,
      bookable?: boolean,
    ) => any;
    parseNumericPrice: (value: any) => number | null;
    formatPrice: (value: number | null, currency: string) => string;
      buildServiceCatalogEntry: (
      deliveryType: any,
      price: number | null,
      currency: string,
      extras?: any,
    ) => any;
      getQuotedPriceForDeliveryType: (routePrices: any, deliveryType: any) => number | null;
  };

  // ---- booking / order helpers ----
  // Bundles the module-scope API clients, validators, and the handful of
  // register()-scope closures the booking tools use. All typed as `any`
  // for wave 1a — wave 1b will tighten these once the helpers move into
  // lib/grid-orders.ts and lib/booking-controller.ts.
  booking: {
    // module-scope helpers
    resolveToolConversationId: (ctx: any) => string;
    resolveToolConversationAliases: (ctx: any) => string[];
    resolveToolTurnId: (ctx: any) => string;
    asOptionalTrimmedString: (value: unknown) => string | null;
    splitFullName: (fullName: string) => { first: string; last: string };
    buildAddressPayload: (
      resolvedArea: any,
      fields: {
        block?: string | null;
        street?: string | null;
        house?: string | null;
        avenue?: string | null;
        extra?: string | null;
        notes?: string | null;
        latitude?: number | null;
        longitude?: number | null;
      },
    ) => any;
    pricesMatch: (a: number | null | undefined, b: number | null | undefined) => boolean;
    getRouteSheetPrice: (
      pickup: any,
      dropoff: any,
      deliveryType: any,
    ) => number | null;
    isOrderCreationBlockedByLiveMaintenance: (settings: any) => boolean;
    buildCreateOrderMaintenanceResult: (settings: any) => any;
    loadRidersGridLiveSettingsSummary: () => Promise<any>;
    assertWriteActionsEnabled: () => void;
    assertValidFleetrunnrOrderId: (orderId: string) => void;
    fleetrunnrRequest: (method: string, endpoint: string) => Promise<any>;
    normalizeFleetrunnrTracking: (payload: unknown, requestedOrderId: string) => any;
    ridersRequest: (method: string, endpoint: string, body?: any) => Promise<any>;
    ridersFormDataRequest: (method: string, endpoint: string, body?: any) => Promise<any>;
    normalizeOrder: (order: any) => any;
    validateCreateSimpleOrderPreflight: (params: any, ctxArgs: any) => void;

    // register()-scope closures
    getDirectChatBookingBlockReason: (controller: any) => string | null;
    buildCanonicalCreateOrderParamsFromController: (
      controller: any,
      params: Record<string, unknown>,
    ) => Record<string, unknown> | null;
    buildPendingOrderFingerprint: (params: Record<string, unknown>) => string;
    isExplicitSummaryConfirmation: (text: string) => boolean;

    // Live getters for mutable register()-scope state.
    getTrackingProvider: () => string;
    getActiveOffers: () => any[];
    isRidersOneBrainEnabled: () => boolean;

    // The module-scope RidersApiError class used by catch-narrowing checks.
    // Typed as a constructor with an instance shape so `err instanceof
    // RidersApiError` narrows into `{ status: number; message: string }`.
    RidersApiError: new (...args: any[]) => { status: number; message: string };
  };

  // ---- guard-state recorder ----
  // Single closure from register()-scope that persists per-session
  // guard metadata for tool replay. Passed through deps so get_price and
  // the booking tools can record without importing session internals.
  recordGuardState: (
    toolName: string,
    result: any,
    ctx: any,
  ) => Promise<void>;

  // ---- behavior policy admin helpers ----
  // Typed loosely as `any` to avoid leaking BehaviorPolicy internals across
  // the wave-1a surface; the behavior admin tools treat these as opaque
  // references and hand policy objects through unchanged.
  behavior: {
    assertBehaviorAdminAuthorized: (ctx: {
      requesterSenderId?: string;
      senderIsOwner?: boolean;
    }) => void;
    loadBehaviorPolicy: () => Promise<any>;
    getBehaviorPolicyStatus: () => Promise<{
      published_path: string;
      published_exists: boolean;
      [key: string]: unknown;
    }>;
    clearBehaviorPolicyCache: () => void;
    writePublishedBehaviorPolicy: (data: any) => Promise<void>;
    normalizeAdminSenderId: (value: string | null | undefined) => string;
    normalizeBehaviorPolicyDocument: (raw: unknown, basePolicy?: any) => any;
    buildNextBehaviorPolicy: (
      policy: any,
      currentPolicy: any,
      senderId?: string | null,
    ) => any;
    resolveBehaviorPolicyInput: (params: {
      policy?: unknown;
      policy_json?: string | null;
    }) => unknown;
    resolveBehaviorRequiredStepsInput: (params: {
      required_steps?: string[] | null;
      required_steps_json?: string | null;
    }) => string[];
    resolveBehaviorLiveInstructionsInput: (params: {
      live_instructions?: string[] | null;
      live_instructions_json?: string | null;
      clear?: boolean | null;
    }) => string[];
    normalizeBehaviorReplyCorrection: (value: unknown, seed: unknown) => any;
    normalizeBehaviorFlowRule: (value: unknown, seed: unknown) => any;
    normalizeBehaviorPhraseGuard: (value: unknown, seed: unknown) => any;
    getNextBehaviorPriority: <T extends { priority: number }>(rules: T[]) => number;
    findBehaviorRuleLocation: (
      policy: any,
      ruleId: string,
    ) => { collection: "reply_corrections" | "flow_rules" | "phrase_guards"; index: number } | null;
  };
}
