#!/usr/bin/env bash
# Point OpenClaw at staging orchestrator (:8011) for Stage B owner WhatsApp canary.
# Production orchestrator (:8010) stays running and unchanged.
set -euo pipefail

DROPIN_DIR=/root/.config/systemd/user/openclaw-gateway.service.d
DROPIN="$DROPIN_DIR/stage-b-staging-orchestrator.conf"
ACTION="${1:-status}"

case "$ACTION" in
  enable)
    mkdir -p "$DROPIN_DIR"
    cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_HR_ORCHESTRATOR_URL=http://127.0.0.1:8011/orchestrator/whatsapp-turn
EOF
    systemctl --user daemon-reload
    systemctl --user restart openclaw-gateway.service
    sleep 2
    systemctl --user is-active openclaw-gateway.service
    echo "OpenClaw now routes HR turns to staging :8011"
    ;;
  disable)
    rm -f "$DROPIN"
    systemctl --user daemon-reload
    systemctl --user restart openclaw-gateway.service
    sleep 2
    systemctl --user is-active openclaw-gateway.service
    echo "OpenClaw restored to default orchestrator URL (production :8010)"
    ;;
  status)
    if [ -f "$DROPIN" ]; then
      echo "ACTIVE drop-in:"
      cat "$DROPIN"
    else
      echo "No Stage B drop-in (default HR_ORCHESTRATOR_URL → :8010)"
    fi
    systemctl --user is-active openclaw-gateway.service || true
    ;;
  *)
    echo "usage: $0 enable|disable|status" >&2
    exit 2
    ;;
esac
