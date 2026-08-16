# Physical RP matrix — store release

Physical claims require one real iPhone and one real Android phone. Simulator/emulator/Maestro evidence does not substitute for this matrix.

**Build:** Play/App Store-distributed test build of `ai.wathefni.employee`, pointed at `https://api.wathefni.ai`

**Languages:** execute the core journey once in EN and once in AR/RTL on each phone

**Evidence rule:** record device model, OS version, build/version, UTC time, tester, and PASS/FAIL notes; do not record passwords, activation codes, tokens, or private document contents

## Preconditions

1. AASA contains the real `TEAMID.ai.wathefni.employee`; assetlinks contains the Google Play **app-signing** SHA-256; the live association qualifier exits 0.
2. Install the store-delivered build. Do not use Expo Go or a development client.
3. Prepare one HR test principal, one Employee test principal, a safe test document/image, and a push-capable test event.
4. Enable device PIN/passcode and biometrics. Keep Wi-Fi/mobile-data controls accessible.
5. Run `./ops/qualify-physical-device-matrix.sh` and confirm both devices are detected before recording results.

## Exact RP procedure — repeat on iPhone and Android

1. **Clean launch and keyboard**
   - Force-close, relaunch, choose Employee, and focus every activation field.
   - Confirm the focused field remains visible above the keyboard, Next/Done behaves correctly, bottom actions remain reachable, and dismiss/reopen does not shift content incorrectly.
   - Repeat on HR sign-in, assistant composer, and PIN entry. Android must also pass with gesture navigation and three-button navigation if supported.

2. **Employee activation and convergence**
   - Activate the prepared Employee principal using a live code; create the local PIN.
   - Open Home/Profile and confirm identity/company are the canonical test principal.
   - Submit one safe critical action, such as a leave request, then verify the resulting backend state through the HR surface/API and confirm the Employee surface shows the same state.

3. **PIN, local lock, and biometrics**
   - Background long enough to trigger the local lock, return, and unlock with the correct PIN.
   - Enter incorrect PINs and confirm bounded lockout/recovery behavior without exposing account data.
   - Enable Face ID/Touch ID or Android biometrics, lock, unlock successfully, cancel once, use PIN fallback, then revoke/alter biometric enrollment and verify fail-closed fallback.
   - Relaunch after device reboot and confirm protected content is not visible before unlock.

4. **Privacy cover and app switching**
   - From a sensitive screen, background the app and open the system app switcher.
   - Confirm the Wathefni task preview is covered and reveals no employee, payroll, document, or notification content.

5. **Push and foreground refresh**
   - With the app backgrounded, trigger the prepared push. Confirm one correctly scoped notification, tap it, and verify the intended authorized destination.
   - While the app is foregrounded, change the same record from another surface. Return/resume and confirm refresh converges without duplicate mutations or stale tenant data.

6. **HTTPS Universal/App Link**
   - Tap `https://api.wathefni.ai/l/leave` from Messages/Mail/Notes or Chrome on the installed phone. It must open Wathefni directly and land on the authorized Leave destination after sign-in/unlock.
   - Test an HR URL with an Employee principal and confirm it fails closed; test an unknown slug and confirm browser 404/store fallback.
   - Uninstall the app, tap the valid URL, and confirm the browser/store fallback. Reinstall the Play/App Store build before continuing.
   - iPhone evidence: use device diagnostics if needed. Android evidence: `adb shell pm get-app-links ai.wathefni.employee` must show the host verified.

7. **Camera, picker, and viewer**
   - From an authorized document/upload action, deny camera once and confirm a recoverable state; then allow it and capture the safe test image.
   - Pick the safe test PDF/image from the native picker, upload once, open it in the native/in-app viewer, return, and confirm no duplicate upload.
   - Confirm no microphone permission is requested and cross-tenant/private files cannot be opened.

8. **Offline/reconnect**
   - Open a previously loaded safe record, enable airplane mode, attempt a read and one mutation, and confirm truthful offline UI with no false success.
   - Restore network, foreground the app, retry once, and verify exactly one canonical mutation and current backend state.

9. **Arabic and RTL**
   - Change app/device language to Arabic and repeat sign-in/activation, Home, Leave, Documents, PIN/biometrics, push-open, and HTTPS-link paths.
   - Confirm true RTL direction, correct back/navigation direction, visible untruncated Arabic, correct numeric/date behavior, and no mixed LTR credentials-field regression.
   - Switch back to English and confirm layout/direction return cleanly without losing the session or tenant.

10. **Final isolation check**
    - Sign out, relaunch, and confirm prior private content is absent from UI, app switcher, notifications, and file previews.
    - Repeat the representative canonical-state read on the other relevant surface and record the matching result identifier/status.

## Result matrix

Mark every cell **PASS**, **FAIL**, or **UNPROVEN**. Any FAIL or UNPROVEN blocks the full-pass stamp.

| ID | Proof | iPhone EN | iPhone AR | Android EN | Android AR |
|---|---|---|---|---|---|
| PH-1 | Keyboard/input visibility and actions | | | | |
| PH-2 | Employee activation + canonical convergence | | | | |
| PH-3 | PIN, local lock, lockout/recovery | | | | |
| PH-4 | Biometrics, cancellation, fallback, revoke | | | | |
| PH-5 | Privacy cover/app switcher | | | | |
| PH-6 | Push background delivery and routing | | | | |
| PH-7 | HTTPS Universal/App Link + fallback | | | | |
| PH-8 | Camera permission/capture | | | | |
| PH-9 | File picker/upload/viewer | | | | |
| PH-10 | Offline, reconnect, exactly-once truth | | | | |
| PH-11 | Foreground refresh/cross-surface truth | | | | |
| PH-12 | RTL layout, navigation, copy, return to EN | | | | |
| PH-13 | Sign-out/private-state clearing | | | | |

Current status: **UNPROVEN**. Latest corrected host evidence: `ops/evidence/store-release-physical-20260816T142417Z/` (no connected iPhone or Android phone).
