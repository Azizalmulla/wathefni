#!/usr/bin/env bash
# Physical RP matrix. Never invents PASS. Device evidence is required.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$REPO_ROOT/ops/evidence/store-release-physical-$STAMP"
mkdir -p "$EVID"

export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export PATH="$HOME/.maestro/bin:/opt/homebrew/bin:$PATH"

ios_usb=0
android_usb=0
ios_names=""
android_names=""

if command -v xcrun >/dev/null 2>&1 && [[ -d "$DEVELOPER_DIR" ]]; then
  ios_names="$(xcrun xctrace list devices 2>/dev/null | awk '/== Devices ==/{p=1;next} /== Simulators ==/{p=0} p && NF' || true)"
  if echo "$ios_names" | grep -Eqi 'iPhone|iPad'; then
    ios_usb=1
  fi
fi
if command -v adb >/dev/null 2>&1; then
  android_names="$(adb devices -l 2>/dev/null | awk 'NR>1 && $2=="device"{print}' || true)"
  if [[ -n "$android_names" ]]; then
    android_usb=1
  fi
fi

{
  echo "# Physical RP matrix — $STAMP"
  echo
  echo "Physical claims require physical evidence. This host check does not substitute a device run."
  echo
  echo "| Probe | Result |"
  echo "|---|---|"
  echo "| iOS USB device | $([[ $ios_usb -eq 1 ]] && echo PRESENT || echo ABSENT) |"
  echo "| Android USB device | $([[ $android_usb -eq 1 ]] && echo PRESENT || echo ABSENT) |"
  echo
  echo "## Devices seen"
  echo
  echo "### iOS"
  echo '```'
  echo "${ios_names:-none}"
  echo '```'
  echo
  echo "### Android"
  echo '```'
  echo "${android_names:-none}"
  echo '```'
  echo
  echo "## RP items"
  echo
  echo "| ID | Item | Result |"
  echo "|---|---|---|"
  for id in PH-1-keyboard-visible PH-2-keyboard-actions PH-3-android-keyboard PH-4-offsets PH-5-biometrics PH-6-pin-lock PH-7-camera-files PH-8-push PH-9-deep-links PH-10-offline-privacy PH-11-rtl; do
    echo "| $id | required on real iOS + Android | UNPROVEN |"
  done
  echo
  if [[ $ios_usb -eq 0 && $android_usb -eq 0 ]]; then
    echo "**PHYSICAL_MATRIX=UNPROVEN** — no USB iOS/Android device on this host."
  else
    echo "**PHYSICAL_MATRIX=DEVICE_PRESENT_BUT_UNRUN** — hardware is attached; the RP journey script was not executed in this pass."
  fi
} | tee "$EVID/PHYSICAL_MATRIX.md"

bash "$REPO_ROOT/ops/mobile-e2e/host-readiness.sh" "$EVID/host-readiness.json" >"$EVID/host-readiness.out" || true

if [[ $ios_usb -eq 0 && $android_usb -eq 0 ]]; then
  echo PHYSICAL_UNPROVEN
  echo "EVIDENCE=$EVID"
  exit 2
fi
echo PHYSICAL_DEVICE_PRESENT_UNRUN
echo "EVIDENCE=$EVID"
exit 2
