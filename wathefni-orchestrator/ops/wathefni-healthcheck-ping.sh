#!/usr/bin/env bash
# Wathefni uptime dead-man's switch.
#
# Runs every 5 minutes (wathefni-uptime.timer). It pings the Healthchecks.io URL
# ONLY when the local app /health returns healthy. If /health fails — or the whole
# VPS is down so this never runs — no ping is sent, and Healthchecks raises the
# alert after its grace period (check is configured 5 min period / 10 min grace).
#
# The ping URL is a capability secret: it lives ONLY in the env file below
# (chmod 600), never in git.
#
#   WATHEFNI_HEALTHCHECK_URL   the hc-ping.com URL (from the env file)
#   WATHEFNI_HEALTH_URL        health endpoint to probe (default: local app port)
#   WATHEFNI_HEALTHCHECK_ENV   override the env file path (for testing)
set -uo pipefail

ENV_FILE="${WATHEFNI_HEALTHCHECK_ENV:-/root/.openclaw/secrets/healthcheck.env}"
HEALTH_URL="${WATHEFNI_HEALTH_URL:-http://127.0.0.1:8010/health}"
LOG="${WATHEFNI_UPTIME_LOG:-/var/log/wathefni-uptime.log}"
OUT="$(mktemp /tmp/wathefni-health-XXXXXX)"
trap 'rm -f "$OUT"' EXIT
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

[ -r "$ENV_FILE" ] && . "$ENV_FILE"
PING_URL="${WATHEFNI_HEALTHCHECK_URL:-}"
if [ -z "$PING_URL" ]; then
  printf '%s [uptime] no WATHEFNI_HEALTHCHECK_URL configured; skipping\n' "$(ts)" >>"$LOG" 2>/dev/null || true
  exit 0
fi

code="$(curl -sS -m 8 -o "$OUT" -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
if [ "$code" = "200" ] && grep -q '"status":"ok"' "$OUT" 2>/dev/null; then
  if curl -fsS -m 10 --retry 2 "$PING_URL" >/dev/null 2>&1; then
    printf '%s [uptime] health=200 ping=OK\n' "$(ts)" >>"$LOG" 2>/dev/null || true
  else
    # Healthy app but the ping itself failed (network/Healthchecks blip). No alert
    # is forced; the next run will re-ping. A sustained ping outage trips the deadman.
    printf '%s [uptime] health=200 ping=FAILED\n' "$(ts)" >>"$LOG" 2>/dev/null || true
  fi
else
  # Unhealthy: deliberately do NOT ping, so Healthchecks trips after the grace window.
  printf '%s [uptime] health=%s UNHEALTHY -> no ping (deadman trips)\n' "$(ts)" "$code" >>"$LOG" 2>/dev/null || true
fi
# Always succeed: the alert signal is the ABSENCE of a ping, not a failed unit.
exit 0
