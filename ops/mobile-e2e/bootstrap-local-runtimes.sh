#!/usr/bin/env bash
# Best-effort local Maestro environment: Java (done via brew), iOS runtime, Android SDK.
# Never claims MOBILE_PASS. Does not take screenshots or record video.
set -euo pipefail
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
export PATH="$JAVA_HOME/bin:$HOME/.maestro/bin:/opt/homebrew/bin:$PATH"
export HOMEBREW_NO_AUTO_UPDATE=1

echo "java=$("$JAVA_HOME/bin/java" -version 2>&1 | head -1 || echo missing)"
echo "maestro=$("$HOME/.maestro/bin/maestro" --version 2>/dev/null | head -1 || echo missing)"

if ! "$DEVELOPER_DIR/usr/bin/simctl" list runtimes 2>/dev/null | grep -q iOS; then
  echo "ios_runtime=missing (download may already be running)"
else
  echo "ios_runtime=present"
fi

if ! command -v adb >/dev/null 2>&1; then
  echo "android_sdk=missing — installing commandlinetools if Homebrew can"
  if brew list --cask android-commandlinetools >/dev/null 2>&1; then
    echo "android-commandlinetools already installed"
  else
    brew install --cask android-commandlinetools || echo "ANDROID_CASK_FAIL"
  fi
fi

if command -v sdkmanager >/dev/null 2>&1; then
  yes | sdkmanager --licenses >/dev/null || true
  sdkmanager "platform-tools" "emulator" "platforms;android-35" "system-images;android-35;google_apis;arm64-v8a" || echo "SDKMANAGER_FAIL"
elif [[ -x /opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/sdkmanager ]]; then
  SM=/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/sdkmanager
  yes | "$SM" --licenses >/dev/null || true
  "$SM" "platform-tools" "emulator" "platforms;android-35" "system-images;android-35;google_apis;arm64-v8a" || echo "SDKMANAGER_FAIL"
else
  echo "sdkmanager_not_on_path"
fi

command -v adb && adb version | head -1 || echo "adb_still_missing"
echo BOOTSTRAP_ENV_DONE
