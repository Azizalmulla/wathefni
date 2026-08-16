# Android local release manifest audit

**UTC date:** 2026-08-16

**Artifact SHA-256:** `0c6acd53407d68ec7adcef897e7884ee19f78063f1213d02d2e5ab624d9c591f`

**Artifact size:** 95 MiB

**Result:** `ANDROID_RELEASE_MANIFEST_PASS`

The artifact was produced from a disposable clean Expo prebuild with the repository release configuration. The binary itself is intentionally not committed.

`apkanalyzer` verified:

- application ID `ai.wathefni.employee`;
- release artifact is not debuggable;
- `android:allowBackup="false"`;
- `android:usesCleartextTraffic="false"`;
- HTTPS App Link host `api.wathefni.ai` with `android:autoVerify="true"` and `/l` prefix;
- custom scheme is only `wathefni`;
- no `SYSTEM_ALERT_WINDOW`, `RECORD_AUDIO`, `READ_EXTERNAL_STORAGE`, or `WRITE_EXTERNAL_STORAGE` permission;
- camera, notifications, current media-image access, biometrics, network, and dependency-required notification/badge permissions remain.

This is native manifest proof, not Google Play signing or physical-device proof.
