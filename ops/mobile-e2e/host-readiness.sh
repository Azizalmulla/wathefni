#!/usr/bin/env bash
# Host readiness for Wathefni mobile UI E2E.
# Never invents MOBILE_PASS — exits 2 when no real UI target can run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_ID="${MOBILE_E2E_APP_ID:-ai.wathefni.employee}"
OUT_JSON="${1:-}"

export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export PATH="$HOME/.maestro/bin:/opt/homebrew/opt/openjdk@17/bin:/opt/homebrew/opt/openjdk/bin:/opt/homebrew/bin:$PATH"
# Prefer Homebrew OpenJDK when the system java stub is present but empty
if [[ -d /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ]]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
elif [[ -d /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home ]]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home"
fi

have() { command -v "$1" >/dev/null 2>&1; }

maestro_ok=0
java_ok=0
simctl_ok=0
runtime_ok=0
booted_ok=0
app_installed=0
adb_ok=0
device_usb=0
disk_free_gb="0"
blockers_file="$(mktemp)"

add_blocker() {
  printf '%s\n' "$1" >>"$blockers_file"
}

if have maestro; then
  maestro_ok=1
else
  add_blocker "maestro_cli_missing"
fi

# Maestro is JVM-based (ignore macOS java stub that prints "Unable to locate")
if [[ -n "${JAVA_HOME:-}" && -x "${JAVA_HOME}/bin/java" ]]; then
  java_ok=1
elif /usr/libexec/java_home >/dev/null 2>&1; then
  java_ok=1
elif command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
  java_ok=1
else
  add_blocker "java_runtime_missing_for_maestro"
fi

if [[ -d "$DEVELOPER_DIR" ]] && have xcrun; then
  if xcrun simctl help >/dev/null 2>&1; then
    simctl_ok=1
  else
    add_blocker "simctl_unavailable_fix_xcode_select_or_DEVELOPER_DIR"
  fi
else
  add_blocker "xcode_developer_dir_missing"
fi

if [[ "$simctl_ok" -eq 1 ]]; then
  runtimes="$(xcrun simctl list runtimes 2>/dev/null || true)"
  if echo "$runtimes" | grep -q "iOS"; then
    runtime_ok=1
  else
    add_blocker "ios_simulator_runtime_missing"
  fi
  booted="$(xcrun simctl list devices booted 2>/dev/null || true)"
  if echo "$booted" | grep -q "Booted"; then
    booted_ok=1
  fi
  if xcrun simctl get_app_container booted "$APP_ID" data >/dev/null 2>&1; then
    app_installed=1
  fi
fi

if have adb; then
  adb_ok=1
  if adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{found=1} END{exit !found}'; then
    device_usb=1
  fi
else
  add_blocker "adb_missing"
fi

if df -g /System/Volumes/Data >/dev/null 2>&1; then
  disk_free_gb="$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')"
else
  disk_free_gb="$(df -g / | awk 'NR==2{print $4}')"
fi

if [[ "$runtime_ok" -eq 0 ]]; then
  free_int="${disk_free_gb%%.*}"
  if [[ "$free_int" -lt 9 ]]; then
    add_blocker "disk_free_lt_9gb_for_ios_runtime"
  fi
fi

ui_ready=0
if [[ "$maestro_ok" -eq 1 && "$java_ok" -eq 1 ]]; then
  if [[ "$runtime_ok" -eq 1 && "$app_installed" -eq 1 ]]; then
    ui_ready=1
  elif [[ "$device_usb" -eq 1 ]]; then
    ui_ready=1
  fi
fi

if [[ "$ui_ready" -eq 0 ]]; then
  add_blocker "no_executable_ui_target"
fi

export ROOT APP_ID OUT_JSON
export maestro_ok java_ok simctl_ok runtime_ok booted_ok app_installed adb_ok device_usb disk_free_gb ui_ready
export blockers_file

python3 <<'PY'
import json
import os
import sys

blockers = []
seen = set()
with open(os.environ["blockers_file"]) as fh:
    for line in fh:
        b = line.strip()
        if b and b not in seen:
            seen.add(b)
            blockers.append(b)

payload = {
    "app_id": os.environ["APP_ID"],
    "repo_root": os.environ["ROOT"],
    "maestro_ok": bool(int(os.environ["maestro_ok"])),
    "java_ok": bool(int(os.environ["java_ok"])),
    "simctl_ok": bool(int(os.environ["simctl_ok"])),
    "ios_runtime_ok": bool(int(os.environ["runtime_ok"])),
    "ios_booted": bool(int(os.environ["booted_ok"])),
    "app_installed_booted": bool(int(os.environ["app_installed"])),
    "adb_ok": bool(int(os.environ["adb_ok"])),
    "usb_android_device": bool(int(os.environ["device_usb"])),
    "disk_free_gb": os.environ["disk_free_gb"],
    "ui_runtime_ready": bool(int(os.environ["ui_ready"])),
    "blockers": blockers,
    "rule": "API PASS ≠ MOBILE PASS — ui_runtime_ready=false means MOBILE_PASS stays 0",
}
text = json.dumps(payload, indent=2) + "\n"
sys.stdout.write(text)
out = os.environ.get("OUT_JSON") or ""
if out:
    with open(out, "w") as fh:
        fh.write(text)
sys.exit(0 if payload["ui_runtime_ready"] else 2)
PY

status=$?
rm -f "$blockers_file"
exit "$status"
