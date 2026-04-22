#!/usr/bin/env node
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const DEFAULT_TIMEOUT_MS = Number.parseInt(process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS || "45000", 10);
const DEFAULT_POLL_MS = Number.parseInt(process.env.RIDERS_LIVE_SMOKE_POLL_MS || "2000", 10);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function envNumber(name, fallback) {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\"'\"'`)}'`;
}

function buildRemotePythonInvocation(base64Payload) {
  return `python3 -c ${shellQuote(
    [
      "import base64",
      "import json",
      "import sys",
      "code = base64.b64decode(sys.argv[1]).decode('utf-8')",
      "exec(compile(code, '<remote-smoke>', 'exec'))",
    ].join("; "),
  )} ${shellQuote(base64Payload)}`;
}

function spawnAndCapture(command, args, options = {}) {
  const { input, cwd } = options;
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr, code });
        return;
      }
      reject(
        new Error(
          `${command} ${args.join(" ")} failed with exit code ${code}\n${stderr || stdout}`.trim(),
        ),
      );
    });
    if (input) {
      child.stdin.write(input);
    }
    child.stdin.end();
  });
}

function buildRemotePythonScript(payload) {
  const encoded = Buffer.from(payload, "utf-8").toString("base64");
  return buildRemotePythonInvocation(encoded);
}

async function runRemoteScript(host, scriptSource) {
  const remoteCommand = buildRemotePythonScript(scriptSource);
  const { stdout } = await spawnAndCapture("ssh", [host, remoteCommand]);
  return stdout.trim();
}

// Numbers we know are live production support lines. The destructive live
// smoke must never, ever fire at them — even as a typo. If you're adding a
// new test number, set RIDERS_LIVE_SMOKE_REPLY_TARGET_ALLOW=1 in your
// environment to acknowledge the risk explicitly.
const PROTECTED_LIVE_NUMBERS = new Set([
  "1880999", // RIDERS_SUPPORT_NUMBER
  "9651880999",
  "+9651880999",
  "69039993", // RIDERS_B2B_CONTACT_PHONE
  "96569039993",
  "+96569039993",
  "90010001", // RIDERS_EXECUTIVE_PHONE
  "96590010001",
  "+96590010001",
]);

function digitsOnly(value) {
  return String(value || "").replace(/[^0-9]/g, "");
}

function assertReplyTargetLooksLikeTestNumber(rawReplyTarget) {
  const replyTarget = String(rawReplyTarget || "").trim();
  assert(
    replyTarget,
    "RIDERS_LIVE_SMOKE_REPLY_TARGET is required. Use a dedicated test WhatsApp number before running destructive live smoke tests.",
  );

  if (String(process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET_ALLOW || "").trim() === "1") {
    return replyTarget;
  }

  const digits = digitsOnly(replyTarget);
  assert(
    digits.length >= 7,
    `RIDERS_LIVE_SMOKE_REPLY_TARGET '${replyTarget}' does not look like a phone number. Refusing to run destructive live smoke.`,
  );

  const protectedHit =
    PROTECTED_LIVE_NUMBERS.has(replyTarget) ||
    PROTECTED_LIVE_NUMBERS.has(digits) ||
    Array.from(PROTECTED_LIVE_NUMBERS).some((protectedNumber) => {
      const pd = digitsOnly(protectedNumber);
      return pd && digits.endsWith(pd);
    });
  assert(
    !protectedHit,
    `RIDERS_LIVE_SMOKE_REPLY_TARGET '${replyTarget}' matches a known Riders production support/contact number. Refusing to run destructive live smoke. Set RIDERS_LIVE_SMOKE_REPLY_TARGET_ALLOW=1 to override.`,
  );

  return replyTarget;
}

export function getLiveSmokeConfig() {
  const replyTarget = assertReplyTargetLooksLikeTestNumber(
    process.env.RIDERS_LIVE_SMOKE_REPLY_TARGET,
  );

  return {
    host: String(process.env.RIDERS_LIVE_SMOKE_VPS_HOST || process.env.RIDERS_VPS_HOST || "root@72.61.106.61").trim(),
    profile: String(process.env.RIDERS_LIVE_SMOKE_PROFILE || process.env.OPENCLAW_PROFILE || "delivery").trim(),
    agentId: String(process.env.RIDERS_LIVE_SMOKE_AGENT_ID || "riders").trim(),
    replyTarget,
    remoteEnvPath: String(process.env.RIDERS_LIVE_SMOKE_REMOTE_ENV_PATH || "/opt/riders-delivery/.env").trim(),
    gatewayHost: String(process.env.RIDERS_LIVE_SMOKE_GATEWAY_HOST || "127.0.0.1").trim(),
    gatewayPort: envNumber("RIDERS_LIVE_SMOKE_GATEWAY_PORT", envNumber("OPENCLAW_GATEWAY_PORT", 18790)),
    webhookPath: String(process.env.RIDERS_LIVE_SMOKE_WEBHOOK_PATH || "/webhook").trim(),
    webhookToken: String(process.env.RIDERS_LIVE_SMOKE_WEBHOOK_TOKEN || process.env.AI_OCTOPUS_WEBHOOK_TOKEN || "").trim(),
    timeoutMs: envNumber("RIDERS_LIVE_SMOKE_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
    pollMs: envNumber("RIDERS_LIVE_SMOKE_POLL_MS", DEFAULT_POLL_MS),
    senderNamePrefix: String(process.env.RIDERS_LIVE_SMOKE_SENDER_NAME_PREFIX || "Smoke Sender").trim(),
    recipientNamePrefix: String(process.env.RIDERS_LIVE_SMOKE_RECIPIENT_NAME_PREFIX || "Smoke Recipient").trim(),
    senderPhone: String(process.env.RIDERS_LIVE_SMOKE_SENDER_PHONE || "66565430").trim(),
    recipientPhone: String(process.env.RIDERS_LIVE_SMOKE_RECIPIENT_PHONE || "66565431").trim(),
    pickupInput: String(process.env.RIDERS_LIVE_SMOKE_PICKUP_INPUT || "Farwaniya").trim(),
    dropoffInput: String(process.env.RIDERS_LIVE_SMOKE_DROPOFF_INPUT || "Hawalli").trim(),
    pickupExpected: String(process.env.RIDERS_LIVE_SMOKE_PICKUP_EXPECTED || "Farwaniya").trim(),
    dropoffExpected: String(process.env.RIDERS_LIVE_SMOKE_DROPOFF_EXPECTED || "Hawalli").trim(),
    pickupAddressStep: String(process.env.RIDERS_LIVE_SMOKE_PICKUP_ADDRESS || "Block 1, Street 1, House 1").trim(),
    dropoffAddressStep: String(process.env.RIDERS_LIVE_SMOKE_DROPOFF_ADDRESS || "Block 2, Street 2, House 2").trim(),
    transportConversationId: String(process.env.RIDERS_LIVE_SMOKE_CONVERSATION_ID || "").trim(),
    voiceNoteAudioUrl: String(process.env.RIDERS_LIVE_SMOKE_AUDIO_URL || "").trim(),
    voiceNoteVoice: String(process.env.RIDERS_LIVE_SMOKE_AUDIO_VOICE || "Samantha").trim(),
  };
}

function buildResolveConversationIdRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import re
import subprocess

params = json.loads(${JSON.stringify(encoded)})
reply_target = str(params["replyTarget"]).strip()
service_name = params.get("serviceName") or "riders-delivery"
log_tail = int(params.get("logTail") or 4000)

try:
    out = subprocess.check_output(
        ["journalctl", "-u", service_name, "-n", str(log_tail), "--no-pager"],
        text=True,
        errors="replace",
    )
except Exception:
    out = ""

lines = out.splitlines()
conversation_pattern = re.compile(r"conversation=([^\\s]+)")
active_conversation_pattern = re.compile(r"activeConversation=([^\\s]+)")
debounce_pattern = re.compile(r"key=[^:]+:([^\\s]+)")

known_conversations = set()
for line in lines:
    if f"replyTarget={reply_target}" not in line:
        continue
    candidates = []
    match = conversation_pattern.search(line)
    if match:
        candidates.append(match.group(1).strip())
    active_match = active_conversation_pattern.search(line)
    if active_match:
        candidates.append(active_match.group(1).strip())
    for candidate in candidates:
        if candidate and not candidate.startswith("smoke-"):
            known_conversations.add(candidate)

states = {
    conversation_id: {
        "latestInboundIdx": -1,
        "latestInboundLine": "",
        "latestOutboundIdx": -1,
        "latestOutboundLine": "",
        "latestClosedIdx": -1,
        "latestClosedLine": "",
    }
    for conversation_id in known_conversations
}

for idx, line in enumerate(lines):
    match = conversation_pattern.search(line)
    active_match = active_conversation_pattern.search(line)
    debounce_match = debounce_pattern.search(line) if "[octopus] debounce " in line else None
    conversation_id = ""
    if match:
        conversation_id = match.group(1).strip()
    elif active_match:
        conversation_id = active_match.group(1).strip()
    elif debounce_match:
        conversation_id = debounce_match.group(1).strip()
    if not conversation_id:
        continue
    if conversation_id not in states:
        continue
    state = states[conversation_id]
    if "[octopus] inbound routed" in line and f"replyTarget={reply_target}" in line:
        state["latestInboundIdx"] = idx
        state["latestInboundLine"] = line
    if "[turn-interpreter]" in line and idx > state["latestInboundIdx"]:
        state["latestInboundIdx"] = idx
        state["latestInboundLine"] = line
    if "[octopus] debounce " in line and idx > state["latestInboundIdx"]:
        state["latestInboundIdx"] = idx
        state["latestInboundLine"] = line
    if "[octopus] outbound reply sent" in line:
        state["latestOutboundIdx"] = idx
        state["latestOutboundLine"] = line
    if "Conversation is closed" in line:
        state["latestClosedIdx"] = idx
        state["latestClosedLine"] = line

active_candidates = []
for conversation_id, state in states.items():
    if (
        state["latestOutboundIdx"] >= 0 and
        state["latestInboundIdx"] >= 0 and
        state["latestOutboundIdx"] > state["latestInboundIdx"] and
        state["latestOutboundIdx"] > state["latestClosedIdx"]
    ):
        active_candidates.append((state["latestOutboundIdx"], conversation_id, state))

if active_candidates:
    _, conversation_id, state = max(active_candidates)
    print(json.dumps({
        "status": "active",
        "conversationId": conversation_id,
        "detail": state["latestOutboundLine"],
    }))
else:
    newest = None
    for conversation_id, state in states.items():
        candidate = (state["latestInboundIdx"], conversation_id, state)
        if newest is None or candidate[0] > newest[0]:
            newest = candidate
    if newest and newest[0] >= 0:
        _, conversation_id, state = newest
        status = "awaiting_sendable_reply"
        detail = state["latestInboundLine"]
        if state["latestClosedIdx"] > state["latestInboundIdx"]:
            status = "closed_after_latest_inbound"
            detail = state["latestClosedLine"] or detail
        print(json.dumps({
            "status": status,
            "conversationId": conversation_id,
            "detail": detail,
        }))
    else:
        print(json.dumps({
            "status": "missing",
            "conversationId": "",
            "detail": "",
        }))
`;
}

export async function resolveTransportConversationId(config) {
  if (config.transportConversationId) {
    return config.transportConversationId;
  }
  const stdout = await runRemoteScript(
    config.host,
    buildResolveConversationIdRemoteScript({
      replyTarget: config.replyTarget,
      serviceName: "riders-delivery",
      logTail: 4000,
    }),
  );
  let parsed = null;
  try {
    parsed = JSON.parse(stdout || "{}");
  } catch {
    parsed = null;
  }
  const status = String(parsed?.status || "").trim();
  const conversationId = String(parsed?.conversationId || stdout || "").trim();
  assert(
    status === "active" && conversationId,
    status === "closed_after_latest_inbound"
      ? `The latest inbound for ${config.replyTarget} is still attached to a closed AI Octopus conversation (${conversationId}). Wait for the bot to successfully reply on a fresh/reopened thread before running live smoke tests. Detail: ${String(parsed?.detail || "")}`
      : status === "awaiting_sendable_reply"
        ? `Found a recent inbound for ${config.replyTarget} on conversation ${conversationId}, but no successful outbound reply was observed yet. Wait for the bot to answer your real message before running live smoke tests. Detail: ${String(parsed?.detail || "")}`
        : `Could not resolve an active live conversation_id for ${config.replyTarget}. Set RIDERS_LIVE_SMOKE_CONVERSATION_ID or send one real message and wait for a successful bot reply first.`,
  );
  config.transportConversationId = conversationId;
  return conversationId;
}

export async function createRunContext(config) {
  const transportConversationId = await resolveTransportConversationId(config);
  const runId = `${Date.now().toString(36)}-${randomUUID().slice(0, 8)}`;
  const markerCore = randomUUID().replace(/[^a-z]/g, "").slice(0, 6) || "smoketest";
  const marker = markerCore;
  return {
    runId,
    marker,
    startedAtMs: Date.now(),
    conversationId: transportConversationId,
    logicalConversationId: `smoke-${runId}`,
    replyTarget: config.replyTarget,
    senderName: `${config.senderNamePrefix} ${marker}`,
    recipientName: `${config.recipientNamePrefix} ${marker}`,
    recipientPhone: config.recipientPhone,
    messageCounter: 0,
  };
}

function buildResetConversationStateRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import socket
import subprocess
import time
from pathlib import Path

params = json.loads(${JSON.stringify(encoded)})
profile = str(params.get("profile") or "delivery").strip()
conversation_id = str(params.get("conversationId") or "").strip()
reply_target = str(params.get("replyTarget") or "").strip()
service_name = str(params.get("serviceName") or "riders-delivery").strip()
gateway_host = str(params.get("gatewayHost") or "127.0.0.1").strip()
gateway_port = int(params.get("gatewayPort") or 18790)

base = Path.home() / f".openclaw-{profile}"
controller_path = base / "conversation-controller-state.json"
inactivity_path = base / "inactivity-state.json"
guard_path = base / "riders-guard-state.json"

for path in [controller_path, inactivity_path, guard_path]:
    if path.exists():
        try:
            state = json.loads(path.read_text())
        except Exception:
            state = {}
        if isinstance(state, dict):
            next_state = {}
            for key, value in state.items():
                key_str = str(key or "")
                if path == guard_path:
                    if (
                        key_str == "__global__" or
                        key_str == conversation_id or
                        key_str == reply_target or
                        key_str == f"default::{conversation_id}" or
                        (conversation_id and key_str.endswith(f"::{conversation_id}")) or
                        (conversation_id and f":octopus:direct:{conversation_id}" in key_str)
                    ):
                        continue
                    if isinstance(value, dict):
                        last_quote = value.get("lastQuotedRoute") or {}
                        route_key = str(last_quote.get("routeKey") or "").strip()
                        if route_key and reply_target and reply_target in route_key:
                            continue
                        if str(value.get("replyTarget") or value.get("reply_target") or "") == reply_target:
                            continue
                else:
                    if key_str == conversation_id or key_str == f"default::{conversation_id}":
                        continue
                    if isinstance(value, dict):
                        if str(value.get("conversationId") or value.get("conversation_id") or "") == conversation_id:
                            continue
                        if str(value.get("replyTarget") or value.get("reply_target") or "") == reply_target and conversation_id:
                            continue
                next_state[key] = value
            path.write_text(json.dumps(next_state))

subprocess.check_call(["systemctl", "restart", service_name])
status = subprocess.check_output(["systemctl", "is-active", service_name], text=True, errors="replace").strip()
deadline = time.time() + 30
last_error = ""
while time.time() < deadline:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((gateway_host, gateway_port))
        sock.close()
        print(status)
        break
    except Exception as exc:
        last_error = str(exc)
        time.sleep(0.5)
    finally:
        try:
            sock.close()
        except Exception:
            pass
else:
    raise SystemExit(f"gateway_not_ready:{last_error}")
`;
}

export async function resetLiveConversationState(config, run) {
  const stdout = await runRemoteScript(
    config.host,
    buildResetConversationStateRemoteScript({
      profile: config.profile,
      conversationId: run.conversationId,
      replyTarget: run.replyTarget,
      serviceName: "riders-delivery",
      gatewayHost: config.gatewayHost,
      gatewayPort: config.gatewayPort,
    }),
  );
  assert(stdout === "active", `Expected riders-delivery to be active after reset, got: ${stdout || "empty"}`);
}

function buildAgeQuoteStateRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import socket
import subprocess
import time
from pathlib import Path

params = json.loads(${JSON.stringify(encoded)})
profile = str(params.get("profile") or "delivery").strip()
conversation_id = str(params.get("conversationId") or "").strip()
reply_target = str(params.get("replyTarget") or "").strip()
age_ms = int(params.get("ageMs") or 0)
service_name = str(params.get("serviceName") or "riders-delivery").strip()
gateway_host = str(params.get("gatewayHost") or "127.0.0.1").strip()
gateway_port = int(params.get("gatewayPort") or 18790)
now_ms = int(time.time() * 1000)
target_ts = max(0, now_ms - age_ms)

base = Path.home() / f".openclaw-{profile}"
controller_path = base / "conversation-controller-state.json"
guard_path = base / "riders-guard-state.json"

updated = {"controller": 0, "guard": 0}

def controller_matches(key, value):
    if key == conversation_id or key.endswith(f"::{conversation_id}"):
        return True
    if isinstance(value, dict):
        if str(value.get("conversationId") or value.get("conversation_id") or "").strip() == conversation_id:
            return True
        if reply_target and str(value.get("replyTarget") or value.get("reply_target") or "").strip() == reply_target:
            return True
    return False

def guard_matches(key, value):
    if key == conversation_id or key.endswith(f"::{conversation_id}"):
        return True
    if reply_target and key == reply_target:
        return True
    if conversation_id and (f":octopus:direct:{conversation_id}::prompt=" in key or key.endswith(f":octopus:direct:{conversation_id}")):
        return True
    if isinstance(value, dict):
        last_quote = value.get("lastQuotedRoute") or {}
        if str(last_quote.get("routeKey") or "").strip():
            if reply_target and key == reply_target:
                return True
    return False

if controller_path.exists():
    try:
        state = json.loads(controller_path.read_text())
    except Exception:
        state = {}
    if isinstance(state, dict):
        for key, value in state.items():
            if not controller_matches(key, value) or not isinstance(value, dict):
                continue
            if value.get("stage") == "quoted" or value.get("quoteTs") is not None:
                value["quoteTs"] = target_ts
                value["lastActivityTs"] = now_ms
                updated["controller"] += 1
        controller_path.write_text(json.dumps(state))

if guard_path.exists():
    try:
        state = json.loads(guard_path.read_text())
    except Exception:
        state = {}
    if isinstance(state, dict):
        for key, value in state.items():
            if not guard_matches(key, value) or not isinstance(value, dict):
                continue
            last_quote = value.get("lastQuotedRoute")
            if not isinstance(last_quote, dict):
                continue
            value["lastToolTs"] = target_ts
            last_quote["quotedAt"] = target_ts
            updated["guard"] += 1
        guard_path.write_text(json.dumps(state))

subprocess.check_call(["systemctl", "restart", service_name])
deadline = time.time() + 30
last_error = ""
while time.time() < deadline:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((gateway_host, gateway_port))
        sock.close()
        print(json.dumps(updated))
        break
    except Exception as exc:
        last_error = str(exc)
        time.sleep(0.5)
    finally:
        try:
            sock.close()
        except Exception:
            pass
else:
    raise SystemExit(f"gateway_not_ready:{last_error}")
`;
}

export async function ageLiveQuoteState(config, run, ageMs) {
  const stdout = await runRemoteScript(
    config.host,
    buildAgeQuoteStateRemoteScript({
      profile: config.profile,
      conversationId: run.conversationId,
      replyTarget: run.replyTarget,
      ageMs,
      serviceName: "riders-delivery",
      gatewayHost: config.gatewayHost,
      gatewayPort: config.gatewayPort,
    }),
  );
  const parsed = JSON.parse(stdout || "{}");
  return {
    controllerUpdated: Number(parsed?.controller || 0),
    guardUpdated: Number(parsed?.guard || 0),
  };
}

function buildWaitForGatewayReadyRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import socket
import time

params = json.loads(${JSON.stringify(encoded)})
gateway_host = str(params.get("gatewayHost") or "127.0.0.1").strip()
gateway_port = int(params.get("gatewayPort") or 18790)
timeout_s = float(params.get("timeoutSeconds") or 30)

deadline = time.time() + timeout_s
last_error = ""
while time.time() < deadline:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((gateway_host, gateway_port))
        print("ready")
        break
    except Exception as exc:
        last_error = str(exc)
        time.sleep(0.5)
    finally:
        try:
            sock.close()
        except Exception:
            pass
else:
    raise SystemExit(f"gateway_not_ready:{last_error}")
`;
}

export async function ensureLiveGatewayReady(config) {
  const stdout = await runRemoteScript(
    config.host,
    buildWaitForGatewayReadyRemoteScript({
      gatewayHost: config.gatewayHost,
      gatewayPort: config.gatewayPort,
      timeoutSeconds: 30,
    }),
  );
  assert(stdout === "ready", `Expected gateway to be ready, got: ${stdout || "empty"}`);
}

function buildPostWebhookRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import os
import urllib.request
import urllib.error

def load_env(path):
    env = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env

params = json.loads(${JSON.stringify(encoded)})
env = load_env(params["remoteEnvPath"])
gateway_host = params.get("gatewayHost") or "127.0.0.1"
gateway_port = int(params.get("gatewayPort") or env.get("OPENCLAW_GATEWAY_PORT") or 18790)
webhook_path = params.get("webhookPath") or "/webhook"
webhook_token = params.get("webhookToken") or env.get("AI_OCTOPUS_WEBHOOK_TOKEN") or ""
payload = params.get("payload")
raw_body = params.get("rawBody")
method = str(params.get("method") or "POST").upper()
headers = params.get("headers") or {}
request_id = params.get("requestId") or ""
url = f"http://{gateway_host}:{gateway_port}{webhook_path}"
if raw_body is not None:
    data = str(raw_body).encode("utf-8")
elif payload is not None:
    data = json.dumps(payload).encode("utf-8")
else:
    data = None
request = urllib.request.Request(url, data=data, method=method)
normalized_header_names = {str(key).lower() for key in headers.keys()}
if "content-type" not in normalized_header_names and (payload is not None or raw_body is not None):
    request.add_header("Content-Type", "application/json")
if webhook_token and "x-ai-octopus-token" not in normalized_header_names:
    request.add_header("x-ai-octopus-token", webhook_token)
if request_id and "x-request-id" not in normalized_header_names:
    request.add_header("X-Request-Id", request_id)
for key, value in headers.items():
    request.add_header(str(key), str(value))
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        print(json.dumps({"statusCode": int(getattr(response, "status", 200)), "body": body}))
except urllib.error.HTTPError as error:
    detail = error.read().decode("utf-8", errors="replace")
    print(json.dumps({"statusCode": int(error.code), "body": detail}))
`;
}

function buildBaseInboundPayload(run) {
  return {
    conversation_id: run.conversationId,
    phone: run.replyTarget,
    from: run.replyTarget,
    sender_id: run.replyTarget,
    message_id: `${run.runId}-${run.messageCounter}`,
  };
}

export async function postWebhookPayload(config, run, payload) {
  run.messageCounter += 1;
  const mergedPayload = {
    ...buildBaseInboundPayload(run),
    ...(payload || {}),
  };
  const response = await postRawWebhookRequest(config, {
    payload: mergedPayload,
  });
  return {
    payload: mergedPayload,
    response: response.parsedBody || {},
    statusCode: response.statusCode,
    acceptedAtMs: Date.parse(response.parsedBody?.received_at || "") || Date.now(),
  };
}

export async function postRawWebhookRequest(config, params = {}) {
  const requestId = String(params.requestId || `riders-webhook-${randomUUID().slice(0, 8)}`).trim();
  const stdout = await runRemoteScript(
    config.host,
    buildPostWebhookRemoteScript({
      remoteEnvPath: config.remoteEnvPath,
      gatewayHost: config.gatewayHost,
      gatewayPort: config.gatewayPort,
      webhookPath: params.webhookPath || config.webhookPath,
      webhookToken:
        Object.prototype.hasOwnProperty.call(params, "webhookToken")
          ? params.webhookToken
          : config.webhookToken,
      payload: Object.prototype.hasOwnProperty.call(params, "payload") ? params.payload : undefined,
      rawBody: Object.prototype.hasOwnProperty.call(params, "rawBody") ? params.rawBody : undefined,
      method: params.method || "POST",
      headers: params.headers || {},
      requestId,
    }),
  );
  const response = JSON.parse(stdout || "{}");
  let parsedBody = null;
  try {
    parsedBody = response?.body ? JSON.parse(response.body) : null;
  } catch {
    parsedBody = null;
  }
  return {
    requestId,
    statusCode: Number(response?.statusCode || 0),
    body: String(response?.body || ""),
    parsedBody,
  };
}

export async function postTextTurn(config, run, text) {
  return postWebhookPayload(config, run, { message: text });
}

async function generateLocalVoiceNoteDataUrl(text, voice = "Samantha") {
  const tempId = randomUUID().slice(0, 8);
  const aiffPath = path.join(os.tmpdir(), `riders-smoke-${tempId}.aiff`);
  const wavPath = path.join(os.tmpdir(), `riders-smoke-${tempId}.wav`);
  try {
    const sayArgs = [];
    if (voice) {
      sayArgs.push("-v", voice);
    }
    sayArgs.push("-o", aiffPath, text);
    await spawnAndCapture("say", sayArgs);
    await spawnAndCapture("afconvert", ["-f", "WAVE", "-d", "LEI16@22050", aiffPath, wavPath]);
    const wavBuffer = await readFile(wavPath);
    return `data:audio/wav;base64,${wavBuffer.toString("base64")}`;
  } finally {
    await Promise.allSettled([rm(aiffPath, { force: true }), rm(wavPath, { force: true })]);
  }
}

export async function postAudioTurn(config, run, params) {
  const audioUrl =
    params?.audioUrl ||
    config.voiceNoteAudioUrl ||
    (params?.textToSpeech
      ? await generateLocalVoiceNoteDataUrl(params.textToSpeech, params.voice || config.voiceNoteVoice)
      : "");
  assert(audioUrl, "Audio turn requires either audioUrl, RIDERS_LIVE_SMOKE_AUDIO_URL, or textToSpeech.");
  const audioMessage = {
    id: `${run.runId}-audio-${run.messageCounter + 1}`,
    from: run.replyTarget,
    type: "audio",
    audio: {
      id: `${run.runId}-audio-media-${run.messageCounter + 1}`,
      mime_type: params?.mimeType || "audio/wav",
      url: audioUrl,
      voice: params?.voiceMessage !== false,
    },
  };
  return postWebhookPayload(config, run, {
    ...(params?.text ? { message: params.text } : {}),
    messages: [audioMessage],
  });
}

export async function postImageTurn(config, run, params) {
  const imageMessage = {
    id: `${run.runId}-image-${run.messageCounter + 1}`,
    from: run.replyTarget,
    type: "image",
    image: {
      id: `${run.runId}-image-media-${run.messageCounter + 1}`,
      mime_type: params?.mimeType || "image/png",
      url: params?.imageUrl,
      caption: params?.caption || undefined,
    },
  };
  return postWebhookPayload(config, run, {
    ...(params?.caption ? { message: params.caption } : {}),
    messages: [imageMessage],
  });
}

export async function postLocationTurn(config, run, params) {
  const locationMessage = {
    id: `${run.runId}-location-${run.messageCounter + 1}`,
    from: run.replyTarget,
    type: "location",
    location: {
      latitude: params.latitude,
      longitude: params.longitude,
      name: params.name || undefined,
      address: params.address || undefined,
    },
  };
  return postWebhookPayload(config, run, {
    ...(params?.text ? { message: params.text } : {}),
    location: locationMessage.location,
    messages: [locationMessage],
  });
}

function buildFetchGatewayLogsRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import subprocess

params = json.loads(${JSON.stringify(encoded)})
service_name = params.get("serviceName") or "riders-delivery"
conversation_id = str(params.get("conversationId") or "").strip()
since = str(params.get("since") or "").strip()
needle = str(params.get("needle") or "").strip()

cmd = ["journalctl", "-u", service_name, "--no-pager"]
if since:
    cmd.extend(["--since", since])

try:
    out = subprocess.check_output(cmd, text=True, errors="replace")
except Exception:
    out = ""

lines = []
for line in out.splitlines():
    if conversation_id and f"conversation={conversation_id}" not in line:
        continue
    if needle and needle not in line:
        continue
    lines.append(line)

print(json.dumps({"lines": lines[-20:]}, ensure_ascii=False))
`;
}

export async function fetchGatewayLogs(config, run, afterMs, needle = "") {
  const since = new Date(Math.max(0, afterMs)).toISOString().replace("T", " ").replace("Z", " UTC");
  const stdout = await runRemoteScript(
    config.host,
    buildFetchGatewayLogsRemoteScript({
      serviceName: "riders-delivery",
      conversationId: run.conversationId,
      since,
      needle,
    }),
  );
  const parsed = JSON.parse(stdout || '{"lines": []}');
  return Array.isArray(parsed.lines) ? parsed.lines : [];
}

export async function fetchGatewayLogsByNeedle(config, afterMs, needle = "", conversationId = "") {
  const since = new Date(Math.max(0, afterMs)).toISOString().replace("T", " ").replace("Z", " UTC");
  const stdout = await runRemoteScript(
    config.host,
    buildFetchGatewayLogsRemoteScript({
      serviceName: "riders-delivery",
      conversationId,
      since,
      needle,
    }),
  );
  const parsed = JSON.parse(stdout || '{"lines": []}');
  return Array.isArray(parsed.lines) ? parsed.lines : [];
}

export async function waitForGatewayReplyLog(config, run, afterMs, needle, label) {
  const deadline = Date.now() + config.timeoutMs;
  let lastLines = [];
  let lastAllLines = [];
  while (Date.now() <= deadline) {
    lastLines = await fetchGatewayLogs(config, run, afterMs, needle);
    const matched = [...lastLines].reverse().find((line) => line.includes(needle));
    if (matched) {
      const textMatch = matched.match(/text=(.+)$/);
      let text = matched;
      if (textMatch?.[1]) {
        try {
          text = JSON.parse(textMatch[1]);
        } catch {
          text = textMatch[1];
        }
      }
      return {
        reply: {
          text: String(text || ""),
        },
        snapshot: {
          found: false,
          sessionFile: null,
          events: [],
          gatewayLogLines: lastLines,
        },
      };
    }
    lastAllLines = await fetchGatewayLogs(config, run, afterMs, "");
    const deliveryFailure = [...lastAllLines].reverse().find(
      (line) => line.includes("Conversation is closed"),
    );
    if (deliveryFailure) {
      throw new Error(`Live delivery failed after ${label}: conversation is closed. Last log: ${deliveryFailure}`);
    }
    await sleep(config.pollMs);
  }
  const lastVisibleLines = lastLines.length > 0 ? lastLines : lastAllLines;
  throw new Error(`Timed out waiting for gateway reply log after ${label}. Last log lines: ${lastVisibleLines.slice(-3).join(" | ")}`);
}

function buildFetchSessionRemoteScript(params) {
  const encoded = JSON.stringify(params);
  return `
import json
import os
from pathlib import Path

params = json.loads(${JSON.stringify(encoded)})
base = Path.home() / f".openclaw-{params['profile']}" / "agents" / params["agentId"] / "sessions"
reply_target = params["replyTarget"]
marker = params.get("marker") or ""
since_ts = int(params["sinceTs"])
max_files = int(params.get("maxFiles") or 40)

def safe_json(value):
    try:
        return json.loads(value)
    except Exception:
        return None

def get_timestamp_ms(record):
    candidate = record.get("timestamp")
    if isinstance(candidate, (int, float)):
        return int(candidate)
    message = record.get("message")
    if isinstance(message, dict):
        candidate = message.get("timestamp")
        if isinstance(candidate, (int, float)):
            return int(candidate)
    return 0

def extract_text_items(content):
    texts = []
    if not isinstance(content, list):
        return texts
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts

def simplify_user_text(raw):
    if not isinstance(raw, str):
        return ""
    if "\\n\\nUntrusted context" in raw:
        raw = raw.split("\\n\\nUntrusted context", 1)[0]
    parts = raw.split("\\n\`\`\`\\n\\n")
    if len(parts) >= 3:
        return parts[2].strip()
    return raw.strip()

def message_contains_reply_target(record):
    message = record.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    markers = [
        f'"sender_id": "{reply_target}"',
        f'"sender": "{reply_target}"',
        f"current_customer_whatsapp: {reply_target}",
        f'"id": "{reply_target}"',
    ]
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and any(marker in text for marker in markers):
            return True
    return False

def flatten_records(records):
    events = []
    for record in records:
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        timestamp_ms = get_timestamp_ms(record)
        if role == "user":
            joined = "\\n".join(extract_text_items(message.get("content")))
            events.append({
                "kind": "text",
                "role": "user",
                "timestampMs": timestamp_ms,
                "text": simplify_user_text(joined),
                "rawText": joined,
            })
            continue
        if role == "assistant":
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "toolCall":
                    events.append({
                        "kind": "toolCall",
                        "role": "assistant",
                        "timestampMs": timestamp_ms,
                        "toolName": item.get("name"),
                        "arguments": item.get("arguments"),
                    })
                elif item.get("type") == "text" and isinstance(item.get("text"), str):
                    events.append({
                        "kind": "text",
                        "role": "assistant",
                        "timestampMs": timestamp_ms,
                        "text": item.get("text"),
                    })
            continue
        if role == "toolResult":
            text_items = extract_text_items(message.get("content"))
            text = "\\n".join(text_items)
            events.append({
                "kind": "toolResult",
                "role": "toolResult",
                "timestampMs": timestamp_ms,
                "toolName": message.get("toolName"),
                "text": text,
                "json": safe_json(text),
            })
    return events

if not base.is_dir():
    print(json.dumps({"found": False, "sessionFile": None, "events": []}))
    raise SystemExit(0)

files = sorted(
    [path for path in base.iterdir() if path.is_file() and path.suffix == ".jsonl"],
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)[:max_files]

best = None
for file_path in files:
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            records = [safe_json(line) for line in handle if line.strip()]
    except Exception:
        continue
    records = [record for record in records if isinstance(record, dict)]
    if not records:
        continue
    latest_ts = max(get_timestamp_ms(record) for record in records)
    earliest_ts = min(get_timestamp_ms(record) for record in records)
    if latest_ts and latest_ts < since_ts - 30_000:
        continue
    sender_match = any(message_contains_reply_target(record) for record in records)
    if not sender_match:
        continue
    serialized = json.dumps(records, ensure_ascii=False)
    marker_match = bool(marker) and marker in serialized
    score = 10 if marker_match else 1
    candidate = {
        "score": score,
        "latestTs": latest_ts,
        "earliestTs": earliest_ts,
        "filePath": str(file_path),
        "events": flatten_records(records),
    }
    if best is None or (candidate["score"], candidate["latestTs"]) > (best["score"], best["latestTs"]):
        best = candidate

if best is None:
    print(json.dumps({"found": False, "sessionFile": None, "events": []}))
    raise SystemExit(0)

assistant_events = [event for event in best["events"] if event.get("role") == "assistant" and event.get("kind") == "text"]
tool_results = [event for event in best["events"] if event.get("kind") == "toolResult"]
print(json.dumps({
    "found": True,
    "sessionFile": best["filePath"],
    "score": best["score"],
    "latestTs": best["latestTs"],
    "earliestTs": best["earliestTs"],
    "assistantTexts": assistant_events,
    "toolResults": tool_results,
    "events": best["events"],
}, ensure_ascii=False))
`;
}

export async function fetchSessionSnapshot(config, run) {
  const stdout = await runRemoteScript(
    config.host,
    buildFetchSessionRemoteScript({
      profile: config.profile,
      agentId: config.agentId,
      replyTarget: run.replyTarget,
      marker: run.marker,
      sinceTs: run.startedAtMs,
      maxFiles: 40,
    }),
  );
  const snapshot = JSON.parse(stdout || '{"found": false, "events": []}');
  snapshot.events = Array.isArray(snapshot.events) ? snapshot.events : [];
  return snapshot;
}

export function findLatestAssistantTextAfter(snapshot, timestampMs) {
  return [...snapshot.events]
    .filter((event) => event.role === "assistant" && event.kind === "text" && event.timestampMs > timestampMs)
    .sort((a, b) => a.timestampMs - b.timestampMs)
    .at(-1) || null;
}

export function findToolResultsAfter(snapshot, timestampMs, toolName = null) {
  return snapshot.events.filter(
    (event) =>
      event.kind === "toolResult" &&
      event.timestampMs > timestampMs &&
      (!toolName || event.toolName === toolName),
  );
}

export function findToolCallsAfter(snapshot, timestampMs, toolName = null) {
  return snapshot.events.filter(
    (event) =>
      event.kind === "toolCall" &&
      event.timestampMs > timestampMs &&
      (!toolName || event.toolName === toolName),
  );
}

export async function waitForAssistantReply(config, run, afterMs, label) {
  const deadline = Date.now() + config.timeoutMs;
  let lastSnapshot = null;
  while (Date.now() <= deadline) {
    lastSnapshot = await fetchSessionSnapshot(config, run);
    const reply = findLatestAssistantTextAfter(lastSnapshot, afterMs);
    if (reply) {
      return { snapshot: lastSnapshot, reply };
    }
    await sleep(config.pollMs);
  }
  const context = lastSnapshot?.sessionFile ? ` Last session file: ${lastSnapshot.sessionFile}` : "";
  throw new Error(`Timed out waiting for assistant reply after ${label}.${context}`);
}

export async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export function containsArabic(text) {
  return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/u.test(text || "");
}

export function containsEmoji(text) {
  return /[\p{Extended_Pictographic}\p{Emoji_Presentation}]/u.test(text || "");
}

export function containsUrl(text) {
  return /https?:\/\/\S+/i.test(text || "");
}

export function compactWhitespace(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

export function printTranscriptTail(snapshot, count = 8) {
  const tail = snapshot.events.slice(-count);
  for (const event of tail) {
    if (event.kind === "toolCall") {
      console.log(`  [${event.timestampMs}] assistant -> tool:${event.toolName} ${JSON.stringify(event.arguments)}`);
      continue;
    }
    if (event.kind === "toolResult") {
      console.log(`  [${event.timestampMs}] tool:${event.toolName} -> ${compactWhitespace(event.text).slice(0, 220)}`);
      continue;
    }
    console.log(`  [${event.timestampMs}] ${event.role}: ${compactWhitespace(event.text).slice(0, 220)}`);
  }
}
