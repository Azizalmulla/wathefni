#!/usr/bin/env bash
# Stage or apply the OctoHR production Caddy cutover.
# `stage` uploads and validates without reloading Caddy or requesting certificates.
# `apply` refuses until both new VPS hostnames resolve to the production IPv4.
set -euo pipefail

MODE="${1:-stage}"
case "$MODE" in
  stage|apply) ;;
  *) echo "usage: $0 {stage|apply}" >&2; exit 2 ;;
esac

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
EXPECTED_IPV4="${OCTOHR_PRODUCTION_IPV4:-76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="$SCRIPT_DIR/api.wathefni.ai.Caddyfile"
APP_LINKS_SRC="$REPO_ROOT/wathefni-orchestrator/app_links.py"
PUBLIC_LINKS_SRC="$SCRIPT_DIR/octohr-public-links.conf"
REMOTE_STAGE=/etc/caddy/Caddyfile.octohr-next
REMOTE_CUTOVER=/opt/wathefni/cutover/octohr
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$SRC" "$APP_LINKS_SRC" "$PUBLIC_LINKS_SRC" "$VPS_HOST:/tmp/"

"${SSH[@]}" "set -e; \
  caddy validate --adapter caddyfile --config /tmp/api.wathefni.ai.Caddyfile; \
  install -d -m 0755 '$REMOTE_CUTOVER'; \
  install -m 0644 /tmp/api.wathefni.ai.Caddyfile '$REMOTE_STAGE'; \
  install -m 0644 /tmp/app_links.py '$REMOTE_CUTOVER/app_links.py'; \
  install -m 0644 /tmp/octohr-public-links.conf '$REMOTE_CUTOVER/public-links.conf'; \
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile '$REMOTE_CUTOVER/app_links.py'; \
  echo OCTOHR_CUTOVER_STAGE_VALID"

if [ "$MODE" = stage ]; then
  echo "Cutover staged under $VPS_HOST:$REMOTE_CUTOVER and $REMOTE_STAGE; live services were not changed."
  exit 0
fi

for host in api.octo-hr.com app.octo-hr.com; do
  resolved="$("${SSH[@]}" "getent ahostsv4 '$host' | awk '{print \$1}' | sort -u" || true)"
  if ! grep -Fxq "$EXPECTED_IPV4" <<<"$resolved"; then
    echo "REFUSING APPLY: $host does not resolve to $EXPECTED_IPV4 (resolved: ${resolved:-none})" >&2
    exit 1
  fi
done

"${SSH[@]}" "set -Ee; \
  had_public_links=0; \
  cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-octohr-$STAMP; \
  cp -a /opt/wathefni/orchestrator/app_links.py /opt/wathefni/orchestrator/app_links.py.bak-octohr-$STAMP; \
  if [ -f /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf ]; then \
    had_public_links=1; \
    cp -a /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf.bak-octohr-$STAMP; \
  fi; \
  rollback_cutover() { \
    set +e; \
    cp -a /etc/caddy/Caddyfile.bak-octohr-$STAMP /etc/caddy/Caddyfile; \
    cp -a /opt/wathefni/orchestrator/app_links.py.bak-octohr-$STAMP /opt/wathefni/orchestrator/app_links.py; \
    if [ \"\$had_public_links\" = 1 ]; then \
      cp -a /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf.bak-octohr-$STAMP /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf; \
    else \
      rm -f /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf; \
    fi; \
    systemctl daemon-reload; \
    systemctl restart wathefni-orchestrator.service; \
    systemctl reload caddy; \
    echo OCTOHR_CUTOVER_ROLLED_BACK; \
  }; \
  trap 'rc=\$?; rollback_cutover; exit \$rc' ERR; \
  install -m 0644 '$REMOTE_CUTOVER/app_links.py' /opt/wathefni/orchestrator/app_links.py; \
  install -m 0644 '$REMOTE_CUTOVER/public-links.conf' /etc/systemd/system/wathefni-orchestrator.service.d/public-links.conf; \
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app_links.py; \
  systemctl daemon-reload; \
  systemctl restart wathefni-orchestrator.service; \
  for i in \$(seq 1 20); do \
    code=\$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health || true); \
    [ \"\$code\" = 200 ] && break; sleep 3; \
  done; \
  [ \"\$code\" = 200 ] || { echo ORCHESTRATOR_HEALTH_FAILED; exit 1; }; \
  cp -a '$REMOTE_STAGE' /etc/caddy/Caddyfile; \
  caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile; \
  systemctl reload caddy; \
  trap - ERR; \
  echo OCTOHR_CUTOVER_APPLIED"

for url in \
  https://api.octo-hr.com/ready \
  https://app.octo-hr.com/dashboard/ \
  https://api.wathefni.ai/ready \
  https://api.wathefni.ai/dashboard/; do
  curl -sS -o /dev/null -w "$url -> %{http_code}\n" --max-time 25 "$url"
done
