#!/bin/zsh
set -euo pipefail

# ---------------------------------------------------------------------------
# Safer OpenClaw update on Riders VPS
# - Uses the official `openclaw update` flow
# - Creates a validated OpenClaw state backup
# - Creates a separate tarball backup of /opt/riders-delivery
# - Records a project-tree content manifest before and after update
# - Runs doctor + gateway health checks before declaring success
# ---------------------------------------------------------------------------

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

VPS_HOST="${RIDERS_VPS_HOST:-root@72.61.106.61}"
PROFILE_NAME="${RIDERS_OPENCLAW_PROFILE:-delivery}"
SERVICE_NAME="${RIDERS_VPS_SERVICE:-riders-delivery}"
PROJECT_ROOT="${RIDERS_VPS_PROJECT_ROOT:-/opt/riders-delivery}"
BACKUP_ROOT="${RIDERS_VPS_BACKUP_ROOT:-/opt/riders-delivery/backups}"
BACKUP_TAG="$(date +%Y%m%d-%H%M%S)"

DRY_RUN=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage: update-openclaw.sh [--dry-run] [--yes]

  --dry-run   Preview the OpenClaw updater plan only. Makes no remote changes.
  --yes       Skip the interactive confirmation prompt.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --yes)
      ASSUME_YES=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

CURRENT_VERSION_NUMBER=""
BACKUP_DIR="$BACKUP_ROOT/pre-update-$BACKUP_TAG"

print_rollback_instructions() {
  if [[ -z "$CURRENT_VERSION_NUMBER" ]]; then
    return
  fi
  echo ""
  echo "==> Rollback instructions:"
  echo "    ssh $VPS_HOST 'systemctl stop $SERVICE_NAME'"
  echo "    ssh $VPS_HOST 'npm install -g openclaw@${CURRENT_VERSION_NUMBER}'"
  echo "    ssh $VPS_HOST 'tar -xzf $BACKUP_DIR/riders-delivery-project.tgz -C /opt'"
  echo "    ssh $VPS_HOST 'cp $BACKUP_DIR/openclaw.json.before /root/.openclaw-${PROFILE_NAME}/openclaw.json'"
  echo "    ssh $VPS_HOST 'systemctl start $SERVICE_NAME'"
}

echo "==> OpenClaw VPS update"
echo "    VPS: $VPS_HOST"
echo "    Service: $SERVICE_NAME"
echo "    Profile: $PROFILE_NAME"
echo "    Project root: $PROJECT_ROOT"
echo "    Backup dir: $BACKUP_DIR"
echo ""

echo "==> Step 1: Remote preflight"
CURRENT_VERSION=$(ssh "$VPS_HOST" 'openclaw --version 2>/dev/null' | head -1)
CURRENT_VERSION_NUMBER=$(echo "$CURRENT_VERSION" | sed -E 's/^OpenClaw ([0-9.]+).*/\1/')
LATEST_VERSION=$(ssh "$VPS_HOST" 'npm info openclaw version 2>/dev/null' | head -1)
SERVICE_STATUS=$(ssh "$VPS_HOST" "systemctl is-active $SERVICE_NAME 2>/dev/null" || true)
WORKSPACE_PATH=$(ssh "$VPS_HOST" "python3 - <<'PY'
import json
from pathlib import Path
p = Path('/root/.openclaw-${PROFILE_NAME}/openclaw.json')
if not p.exists():
    print('')
    raise SystemExit(0)
obj = json.loads(p.read_text())
print((((obj.get('agents') or {}).get('defaults') or {}).get('workspace')) or '')
PY")
echo "    Current: $CURRENT_VERSION"
echo "    Latest:  OpenClaw $LATEST_VERSION"
echo "    Service status: ${SERVICE_STATUS:-unknown}"
echo "    Workspace: ${WORKSPACE_PATH:-<not set>}"

if [[ -n "$WORKSPACE_PATH" && "$WORKSPACE_PATH" != "$PROJECT_ROOT"/workspaces/* ]]; then
  echo ""
  echo "Workspace path looks unexpected for Riders delivery. Aborting for safety." >&2
  exit 1
fi

if [[ "$CURRENT_VERSION_NUMBER" == "$LATEST_VERSION" ]]; then
  echo ""
  echo "Already on latest version. Nothing to do."
  exit 0
fi

echo ""
echo "==> Step 2: Preview updater plan"
ssh "$VPS_HOST" "OPENCLAW_PROFILE=$PROFILE_NAME openclaw update --dry-run --json"

if (( DRY_RUN )); then
  echo ""
  echo "Dry run complete. No remote changes were made."
  exit 0
fi

if (( ! ASSUME_YES )); then
  read -q "REPLY?    Proceed with update $CURRENT_VERSION_NUMBER -> $LATEST_VERSION? [y/N] " || true
  echo ""
  if [[ "$REPLY" != "y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

echo ""
echo "==> Step 3: Backing up OpenClaw state and deployed project"
if ! ssh "$VPS_HOST" bash -s -- "$BACKUP_TAG" "$PROFILE_NAME" "$PROJECT_ROOT" "$BACKUP_ROOT" <<'REMOTE_BACKUP'
set -euo pipefail
BACKUP_TAG="$1"
PROFILE_NAME="$2"
PROJECT_ROOT="$3"
BACKUP_ROOT="$4"
BACKUP_DIR="$BACKUP_ROOT/pre-update-$BACKUP_TAG"
STATE_DIR="$HOME/.openclaw-$PROFILE_NAME"
PROJECT_PARENT="$(dirname "$PROJECT_ROOT")"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$STATE_DIR/openclaw.json" ]]; then
  echo "Missing profile config at $STATE_DIR/openclaw.json" >&2
  exit 1
fi

cp -a "$STATE_DIR/openclaw.json" "$BACKUP_DIR/openclaw.json.before"
openclaw --version > "$BACKUP_DIR/version-before.txt"
openclaw --profile "$PROFILE_NAME" backup create --verify --no-include-workspace --output "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/riders-delivery-project.tgz" --exclude="${PROJECT_NAME}/backups" -C "$PROJECT_PARENT" "$PROJECT_NAME"

python3 - "$PROJECT_ROOT" "$BACKUP_DIR/project-tree.before.tsv" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])

def should_skip(path: Path) -> bool:
    rel = path.relative_to(root)
    return rel.parts[:1] == ("backups",)

with out.open("w", encoding="utf-8") as fh:
    for path in sorted(root.rglob("*")):
      if not path.is_file() or should_skip(path):
        continue
      digest = hashlib.sha256(path.read_bytes()).hexdigest()
      rel = path.relative_to(root).as_posix()
      fh.write(f"{rel}\t{digest}\t{path.stat().st_size}\n")
PY
REMOTE_BACKUP
then
  echo "Backup failed." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 4: Stopping $SERVICE_NAME"
if ! ssh "$VPS_HOST" "systemctl stop $SERVICE_NAME"; then
  echo "Failed to stop $SERVICE_NAME." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 5: Updating OpenClaw"
if ! ssh "$VPS_HOST" "OPENCLAW_PROFILE=$PROFILE_NAME openclaw update --yes --no-restart"; then
  echo "OpenClaw update failed." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 6: Verifying updated version"
NEW_VERSION=$(ssh "$VPS_HOST" 'openclaw --version 2>/dev/null' | head -1)
echo "    New version: $NEW_VERSION"

echo ""
echo "==> Step 6b: Re-applying narration-suppression patches"
# OpenClaw updates replace the gateway bundle files in dist/, which wipes
# the three narration-suppression monkey-patches (handleMessageEnd,
# onPartialReply, fallbackAnswerText). Without this step, internal
# framework narration (e.g. "Now uploading CV to Drive") can leak to
# WhatsApp customers on the very next turn after an update. The patch
# script is idempotent — running it on an already-patched bundle is a
# no-op. Source-of-truth lives in repo-root `scripts/patch-openclaw.py`;
# we scp it to /tmp on the VPS (not under $PROJECT_ROOT) so step 10's
# project-tree content manifest keeps clean — the patch only mutates
# files inside the npm module tree, which is outside the verified set.
REPO_ROOT="${PROJECT_DIR:h}"
LOCAL_PATCH_SCRIPT="$REPO_ROOT/scripts/patch-openclaw.py"
if [[ ! -f "$LOCAL_PATCH_SCRIPT" ]]; then
  echo "Missing narration-suppression patch script at $LOCAL_PATCH_SCRIPT" >&2
  print_rollback_instructions
  exit 1
fi
REMOTE_PATCH_SCRIPT="/tmp/patch-openclaw-$BACKUP_TAG.py"
scp "$LOCAL_PATCH_SCRIPT" "$VPS_HOST:$REMOTE_PATCH_SCRIPT"
if ! ssh "$VPS_HOST" "python3 $REMOTE_PATCH_SCRIPT && rm -f $REMOTE_PATCH_SCRIPT"; then
  echo "patch-openclaw.py failed; gateway bundle may still carry framework narration." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 7: Running OpenClaw doctor"
if ! ssh "$VPS_HOST" "OPENCLAW_PROFILE=$PROFILE_NAME openclaw doctor"; then
  echo "openclaw doctor failed." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 8: Starting $SERVICE_NAME"
if ! ssh "$VPS_HOST" "systemctl start $SERVICE_NAME"; then
  echo "Failed to start $SERVICE_NAME." >&2
  print_rollback_instructions
  exit 1
fi
sleep 5

echo ""
echo "==> Step 9: Service + health checks"
SERVICE_STATUS=$(ssh "$VPS_HOST" "systemctl is-active $SERVICE_NAME 2>/dev/null" || true)
echo "    Service status: ${SERVICE_STATUS:-unknown}"
if [[ "$SERVICE_STATUS" != "active" ]]; then
  echo "$SERVICE_NAME did not return to active state." >&2
  print_rollback_instructions
  exit 1
fi

if ! ssh "$VPS_HOST" "OPENCLAW_PROFILE=$PROFILE_NAME openclaw gateway health"; then
  echo "Gateway health check failed." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 10: Verifying project tree remained unchanged"
if ! ssh "$VPS_HOST" bash -s -- "$BACKUP_TAG" "$PROJECT_ROOT" "$BACKUP_ROOT" <<'REMOTE_VERIFY'
set -euo pipefail
BACKUP_TAG="$1"
PROJECT_ROOT="$2"
BACKUP_ROOT="$3"
BACKUP_DIR="$BACKUP_ROOT/pre-update-$BACKUP_TAG"

python3 - "$PROJECT_ROOT" "$BACKUP_DIR/project-tree.after.tsv" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])

def should_skip(path: Path) -> bool:
    rel = path.relative_to(root)
    return rel.parts[:1] == ("backups",)

with out.open("w", encoding="utf-8") as fh:
    for path in sorted(root.rglob("*")):
      if not path.is_file() or should_skip(path):
        continue
      digest = hashlib.sha256(path.read_bytes()).hexdigest()
      rel = path.relative_to(root).as_posix()
      fh.write(f"{rel}\t{digest}\t{path.stat().st_size}\n")
PY

if diff -u "$BACKUP_DIR/project-tree.before.tsv" "$BACKUP_DIR/project-tree.after.tsv" > "$BACKUP_DIR/project-tree.diff"; then
  echo "project_tree_changed: no"
else
  echo "project_tree_changed: yes"
  cat "$BACKUP_DIR/project-tree.diff"
  exit 1
fi
REMOTE_VERIFY
then
  echo "Project tree changed during update. Inspect $BACKUP_DIR/project-tree.diff before proceeding." >&2
  print_rollback_instructions
  exit 1
fi

echo ""
echo "==> Step 11: Recent logs"
ssh "$VPS_HOST" "journalctl -u $SERVICE_NAME --since '2 min ago' --no-pager | tail -50"

echo ""
echo "==> Update complete: $CURRENT_VERSION -> $NEW_VERSION"
echo "    Backups: $BACKUP_DIR"
