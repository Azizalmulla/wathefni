// Customer support tools.
//
// Extracted from plugins/riders-tools/index.ts as part of Wave 1a of the
// surgical plugin split. Tool bodies are unchanged. Helpers come from
// deps.intentGates and deps.createTextResult / deps.errorPayload; the
// shared conversation-policy helpers are imported directly because they
// already live as a sibling module.
//
// Tools registered:
//   - complains
//   - assign_agent

import {
  extractTrackingOrderId,
  isBookingStartIntent,
  normalizeIntentText,
} from "../../shared/conversation-policy";

import type { ToolDeps } from "./deps";

export function registerCustomerSupportTools(api: any, deps: ToolDeps): void {
  const { intentGates } = deps;
  const {
    isCustomerOctopusContext,
    getVisibleCustomerText,
    getCustomerTurnActionHint,
    getNormalizedBookingAuthority,
    isActiveBookingFlow,
    customerExplicitlyRequestsHuman,
    assignAgentReasonLooksLegitimate,
    hasStrictTrackingOrderId,
  } = intentGates;

  // =========================================================================
  // TOOL: complains — STUB (records complaint, AI Octopus integration pending)
  // =========================================================================
  api.registerTool({
    name: "complains",
    label: "Record Complaint",
    description:
      "Record a customer complaint and forward it to management for review. The complaint is logged and the customer is informed that it has been escalated.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        complaint_text: {
          type: "string",
          description: "The customer's complaint details as described by them",
        },
        order_id: {
          type: "string",
          description: "Related order ID if applicable",
        },
      },
      required: ["complaint_text"],
    },

    async execute(
      _toolCallId: string,
      params: { complaint_text: string; order_id?: string },
    ) {
      // STUB: AI Octopus escalation integration pending.
      // When live, this will:
      //   1. Log the complaint locally
      //   2. Call POST /client/conversation/toagent on AI Octopus
      //      to move the conversation to a human agent queue
      //
      // For now, acknowledge receipt so the bot can confirm to the customer.
      const timestamp = new Date().toISOString();
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              status: "recorded",
              complaint_text: params.complaint_text,
              order_id: params.order_id || null,
              recorded_at: timestamp,
              message: "تم تسجيل الشكوى وتحويلها للإدارة للمراجعة.",
              escalation_status: "pending_integration",
            }),
          },
        ],
      };
    },
  });

  // =========================================================================
  // TOOL: assign_agent — STUB (AI Octopus escalation pending)
  // =========================================================================
  api.registerTool({
    name: "assign_agent",
    label: "Assign to Human Agent",
    description:
      "Transfer the current conversation to a human support agent. Use this for refunds, data modifications, system errors, job applications, or any case requiring human intervention.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        reason: {
          type: "string",
          description:
            "Brief reason for the handover (e.g. refund request, system error, job application)",
        },
      },
      required: ["reason"],
    },

    async execute(_toolCallId: string, params: { reason: string }, ctx?: any) {
      if (ctx && isCustomerOctopusContext(ctx)) {
        const visibleText = getVisibleCustomerText(ctx);
        const actionHint = getCustomerTurnActionHint(ctx);
        const bookingAuthority = getNormalizedBookingAuthority(ctx);
        const stageHint = bookingAuthority.stage;
        const bookingStepHint = bookingAuthority.bookingStep;
        const reason = String(params.reason || "");
        const explicitHumanRequest = customerExplicitlyRequestsHuman(visibleText);
        const interpreterWantsHandoff = actionHint === "handoff";
        const quotedBookingFollowup =
          stageHint === "quoted" &&
          (actionHint === "start booking" || isBookingStartIntent(visibleText));
        const activeBookingCollection = isActiveBookingFlow(stageHint, bookingStepHint);
        const trackingFallbackReason =
          normalizeIntentText(reason).includes("tracking") ||
          normalizeIntentText(reason).includes("order id") ||
          normalizeIntentText(reason).includes("order number");
        const hasVisibleTrackingId = hasStrictTrackingOrderId(
          extractTrackingOrderId(visibleText) || "",
        );
        if (
          (activeBookingCollection && !explicitHumanRequest && !interpreterWantsHandoff) ||
          (quotedBookingFollowup &&
            !explicitHumanRequest &&
            !assignAgentReasonLooksLegitimate(reason) &&
            !interpreterWantsHandoff) ||
          (actionHint === "tracking missing id" && !explicitHumanRequest) ||
          (actionHint === "booking step input" && !explicitHumanRequest) ||
          (trackingFallbackReason && !hasVisibleTrackingId && !explicitHumanRequest)
        ) {
          console.log(
            `[intent-gate-exec] blocked assign_agent intent=${actionHint} stage=${stageHint || "unknown"} bookingStep=${bookingStepHint || "unknown"}`,
          );
          throw new Error(
            "Do not escalate to a human here. Continue the current booking flow unless the customer explicitly asked for human support or there is a real unsupported/manual-confirmation/system-error case.",
          );
        }
      }

      const timestamp = new Date().toISOString();
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              status: "escalated",
              reason: params.reason,
              escalated_at: timestamp,
              message:
                "تم تحويل المحادثة لموظف الدعم المختص. يرجى الانتظار قليلاً.",
              escalation_status: "pending_integration",
            }),
          },
        ],
      };
    },
  });
}
