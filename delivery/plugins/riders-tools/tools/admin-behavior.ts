// Admin behavior-policy tools.
//
// Extracted from plugins/riders-tools/index.ts (originally lines 8526-9136)
// as part of Wave 1a of the surgical plugin split. Tool bodies are
// unchanged. All behavior-policy helpers live in `deps.behavior` so this
// file does not import from index.ts.
//
// Tools registered:
//   - admin_behavior_policy_status
//   - admin_refresh_behavior_policy_cache
//   - admin_view_behavior_policy
//   - admin_publish_behavior_policy
//   - admin_set_behavior_live_instructions
//   - admin_add_behavior_reply_correction
//   - admin_add_behavior_flow_rule
//   - admin_add_behavior_phrase_guard
//   - admin_disable_behavior_rule
//   - admin_delete_behavior_rule

import type { ToolDeps } from "./deps";

type BehaviorLanguageScope = "any" | "arabic" | "english";
type BehaviorPhraseGuardKind = "blocked" | "required";

export function registerAdminBehaviorTools(api: any, deps: ToolDeps): void {
  const { createTextResult, errorPayload, behavior } = deps;
  const {
    assertBehaviorAdminAuthorized,
    loadBehaviorPolicy,
    getBehaviorPolicyStatus,
    clearBehaviorPolicyCache,
    writePublishedBehaviorPolicy,
    normalizeAdminSenderId,
    normalizeBehaviorPolicyDocument,
    buildNextBehaviorPolicy,
    resolveBehaviorPolicyInput,
    resolveBehaviorRequiredStepsInput,
    resolveBehaviorLiveInstructionsInput,
    normalizeBehaviorReplyCorrection,
    normalizeBehaviorFlowRule,
    normalizeBehaviorPhraseGuard,
    getNextBehaviorPriority,
    findBehaviorRuleLocation,
  } = behavior;

  api.registerTool((ctx: any) => ({
    name: "admin_behavior_policy_status",
    label: "Admin Behavior Policy Status",
    description:
      "Return the active Riders live behavior policy snapshot path, version, and enabled rule counts. Only for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const status = await getBehaviorPolicyStatus();
        return createTextResult(
          {
            status: "ok",
            ...status,
          },
          status,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_refresh_behavior_policy_cache",
    label: "Admin Refresh Behavior Policy Cache",
    description:
      "Clear the in-memory Riders behavior policy cache and report the currently published status. Only for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertBehaviorAdminAuthorized(ctx);
        clearBehaviorPolicyCache();
        const status = await getBehaviorPolicyStatus();
        return createTextResult(
          {
            status: "ok",
            message: "Behavior policy cache refreshed.",
            ...status,
          },
          status,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_view_behavior_policy",
    label: "Admin View Behavior Policy",
    description:
      "Return the currently published Riders live behavior policy for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const policy = await loadBehaviorPolicy();
        const status = await getBehaviorPolicyStatus();
        return createTextResult(
          {
            status: "ok",
            policy,
            published_path: status.published_path,
            published_exists: status.published_exists,
          },
          {
            policy,
            status,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_publish_behavior_policy",
    label: "Admin Publish Behavior Policy",
    description:
      "Validate and publish the Riders live behavior policy snapshot for allowlisted behavior admins. Accepts either a structured policy object or policy_json.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        policy: {
          type: ["object", "null"],
          additionalProperties: true,
        },
        policy_json: {
          type: ["string", "null"],
        },
        dry_run: {
          type: ["boolean", "null"],
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: {
        policy?: Record<string, unknown> | null;
        policy_json?: string | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const rawPolicy = resolveBehaviorPolicyInput(params);
        const normalizedPolicy = normalizeBehaviorPolicyDocument(
          rawPolicy,
          currentPolicy,
        );
        const nextPolicy = buildNextBehaviorPolicy(
          normalizedPolicy,
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        const status = await getBehaviorPolicyStatus();
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Behavior policy validated successfully."
              : "Behavior policy published successfully.",
            published: !params.dry_run,
            updated_by_sender:
              normalizeAdminSenderId(ctx.requesterSenderId) || null,
            version: nextPolicy.version,
            live_instruction_count: nextPolicy.live_instructions.length,
            reply_correction_count: nextPolicy.reply_corrections.filter(
              (rule: any) => rule.enabled,
            ).length,
            flow_rule_count: nextPolicy.flow_rules.filter(
              (rule: any) => rule.enabled,
            ).length,
            phrase_guard_count: nextPolicy.phrase_guards.filter(
              (rule: any) => rule.enabled,
            ).length,
            published_path: status.published_path,
          },
          {
            status,
            policy: nextPolicy,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_set_behavior_live_instructions",
    label: "Admin Set Behavior Live Instructions",
    description:
      "Replace or clear the free-form live instruction block in the Riders behavior policy for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        live_instructions: {
          type: ["array", "null"],
          items: { type: "string" },
        },
        live_instructions_json: {
          type: ["string", "null"],
        },
        summary: {
          type: ["string", "null"],
        },
        clear: {
          type: ["boolean", "null"],
        },
        dry_run: {
          type: ["boolean", "null"],
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: {
        live_instructions?: string[] | null;
        live_instructions_json?: string | null;
        summary?: string | null;
        clear?: boolean | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const nextInstructions = resolveBehaviorLiveInstructionsInput(params);
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            summary:
              typeof params.summary === "string"
                ? params.summary.trim()
                : currentPolicy.summary,
            live_instructions: nextInstructions,
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Live instructions validated successfully."
              : "Live instructions published successfully.",
            published: !params.dry_run,
            version: nextPolicy.version,
            live_instruction_count: nextPolicy.live_instructions.length,
            summary: nextPolicy.summary || null,
          },
          {
            policy: nextPolicy,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_add_behavior_reply_correction",
    label: "Admin Add Behavior Reply Correction",
    description:
      "Add one live reply-correction rule to the Riders behavior policy for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        title: { type: "string" },
        situation: { type: "string" },
        preferred_reply: { type: "string" },
        wrong_reply: { type: ["string", "null"] },
        guidance: { type: ["string", "null"] },
        language_scope: {
          type: ["string", "null"],
          enum: ["any", "arabic", "english", null],
        },
        priority: { type: ["integer", "null"] },
        enabled: { type: ["boolean", "null"] },
        dry_run: { type: ["boolean", "null"] },
      },
      required: ["title", "situation", "preferred_reply"],
    },

    async execute(
      _toolCallId: string,
      params: {
        title: string;
        situation: string;
        preferred_reply: string;
        wrong_reply?: string | null;
        guidance?: string | null;
        language_scope?: BehaviorLanguageScope | null;
        priority?: number | null;
        enabled?: boolean | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const nextRule = normalizeBehaviorReplyCorrection(
          {
            ...params,
            priority:
              params.priority ??
              getNextBehaviorPriority(currentPolicy.reply_corrections),
          },
          [ctx.requesterSenderId, currentPolicy.version, params.title],
        );
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            reply_corrections: [...currentPolicy.reply_corrections, nextRule],
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Reply correction validated successfully."
              : "Reply correction published successfully.",
            published: !params.dry_run,
            rule_id: nextRule.id,
            version: nextPolicy.version,
          },
          {
            rule: nextRule,
            policy: nextPolicy,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_add_behavior_flow_rule",
    label: "Admin Add Behavior Flow Rule",
    description:
      "Add one live flow-control rule to the Riders behavior policy for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        title: { type: "string" },
        situation: { type: "string" },
        required_steps: {
          type: ["array", "null"],
          items: { type: "string" },
        },
        required_steps_json: { type: ["string", "null"] },
        guidance: { type: ["string", "null"] },
        priority: { type: ["integer", "null"] },
        enabled: { type: ["boolean", "null"] },
        dry_run: { type: ["boolean", "null"] },
      },
      required: ["title", "situation"],
    },

    async execute(
      _toolCallId: string,
      params: {
        title: string;
        situation: string;
        required_steps?: string[] | null;
        required_steps_json?: string | null;
        guidance?: string | null;
        priority?: number | null;
        enabled?: boolean | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const nextRule = normalizeBehaviorFlowRule(
          {
            ...params,
            priority:
              params.priority ??
              getNextBehaviorPriority(currentPolicy.flow_rules),
            required_steps: resolveBehaviorRequiredStepsInput(params),
          },
          [ctx.requesterSenderId, currentPolicy.version, params.title],
        );
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            flow_rules: [...currentPolicy.flow_rules, nextRule],
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Flow rule validated successfully."
              : "Flow rule published successfully.",
            published: !params.dry_run,
            rule_id: nextRule.id,
            version: nextPolicy.version,
          },
          {
            rule: nextRule,
            policy: nextPolicy,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_add_behavior_phrase_guard",
    label: "Admin Add Behavior Phrase Guard",
    description:
      "Add one required or blocked phrase guard to the Riders live behavior policy for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        kind: {
          type: "string",
          enum: ["blocked", "required"],
        },
        phrase: { type: "string" },
        applies_when: { type: ["string", "null"] },
        guidance: { type: ["string", "null"] },
        priority: { type: ["integer", "null"] },
        enabled: { type: ["boolean", "null"] },
        dry_run: { type: ["boolean", "null"] },
      },
      required: ["kind", "phrase"],
    },

    async execute(
      _toolCallId: string,
      params: {
        kind: BehaviorPhraseGuardKind;
        phrase: string;
        applies_when?: string | null;
        guidance?: string | null;
        priority?: number | null;
        enabled?: boolean | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const nextRule = normalizeBehaviorPhraseGuard(
          {
            ...params,
            priority:
              params.priority ??
              getNextBehaviorPriority(currentPolicy.phrase_guards),
          },
          [
            ctx.requesterSenderId,
            currentPolicy.version,
            params.kind,
            params.phrase,
          ],
        );
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            phrase_guards: [...currentPolicy.phrase_guards, nextRule],
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Phrase guard validated successfully."
              : "Phrase guard published successfully.",
            published: !params.dry_run,
            rule_id: nextRule.id,
            version: nextPolicy.version,
          },
          {
            rule: nextRule,
            policy: nextPolicy,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_disable_behavior_rule",
    label: "Admin Disable Behavior Rule",
    description:
      "Disable one existing live behavior rule by id for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        rule_id: { type: "string" },
        dry_run: { type: ["boolean", "null"] },
      },
      required: ["rule_id"],
    },

    async execute(
      _toolCallId: string,
      params: {
        rule_id: string;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const location = findBehaviorRuleLocation(currentPolicy, params.rule_id);
        if (!location) {
          throw new Error(`Behavior rule not found: ${params.rule_id}`);
        }
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            reply_corrections:
              location.collection === "reply_corrections"
                ? currentPolicy.reply_corrections.map((rule: any, index: number) =>
                    index === location.index ? { ...rule, enabled: false } : rule,
                  )
                : currentPolicy.reply_corrections,
            flow_rules:
              location.collection === "flow_rules"
                ? currentPolicy.flow_rules.map((rule: any, index: number) =>
                    index === location.index ? { ...rule, enabled: false } : rule,
                  )
                : currentPolicy.flow_rules,
            phrase_guards:
              location.collection === "phrase_guards"
                ? currentPolicy.phrase_guards.map((rule: any, index: number) =>
                    index === location.index ? { ...rule, enabled: false } : rule,
                  )
                : currentPolicy.phrase_guards,
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Behavior rule disable validated successfully."
              : "Behavior rule disabled successfully.",
            published: !params.dry_run,
            rule_id: params.rule_id,
            version: nextPolicy.version,
          },
          {
            policy: nextPolicy,
            location,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_delete_behavior_rule",
    label: "Admin Delete Behavior Rule",
    description:
      "Delete one existing live behavior rule by id for allowlisted behavior admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        rule_id: { type: "string" },
        dry_run: { type: ["boolean", "null"] },
      },
      required: ["rule_id"],
    },

    async execute(
      _toolCallId: string,
      params: {
        rule_id: string;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertBehaviorAdminAuthorized(ctx);
        const currentPolicy = await loadBehaviorPolicy();
        const location = findBehaviorRuleLocation(currentPolicy, params.rule_id);
        if (!location) {
          throw new Error(`Behavior rule not found: ${params.rule_id}`);
        }
        const nextPolicy = buildNextBehaviorPolicy(
          {
            ...currentPolicy,
            reply_corrections: currentPolicy.reply_corrections.filter(
              (rule: any) => rule.id !== params.rule_id,
            ),
            flow_rules: currentPolicy.flow_rules.filter(
              (rule: any) => rule.id !== params.rule_id,
            ),
            phrase_guards: currentPolicy.phrase_guards.filter(
              (rule: any) => rule.id !== params.rule_id,
            ),
          },
          currentPolicy,
          ctx.requesterSenderId,
        );
        if (!params.dry_run) {
          await writePublishedBehaviorPolicy(nextPolicy);
        }
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Behavior rule delete validated successfully."
              : "Behavior rule deleted successfully.",
            published: !params.dry_run,
            rule_id: params.rule_id,
            version: nextPolicy.version,
          },
          {
            policy: nextPolicy,
            location,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
