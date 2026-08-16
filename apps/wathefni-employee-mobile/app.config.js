/**
 * Expo config for Wathefni Employee App.
 *
 * Auth Wave 2 master flags are forced here so `eas update` / Metro always bake
 * them even when the shell forgot to export them. EAS production env vars are
 * the remote source of truth; this is the local fail-safe.
 */
const appJson = require('./app.json')

const AUTH_WAVE2_DEFAULTS = {
  EXPO_PUBLIC_LOCAL_PIN_UNLOCK: '1',
  EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK: '1',
  EXPO_PUBLIC_LOCAL_AUTO_LOCK: '1',
  EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC: '1',
}

/** Unified-app HR workspace — must bake on eas update, not only EAS build env. */
const UNIFIED_APP_DEFAULTS = {
  EXPO_PUBLIC_HR_WORKSPACE_ENABLED: '1',
}

for (const [key, value] of Object.entries({ ...AUTH_WAVE2_DEFAULTS, ...UNIFIED_APP_DEFAULTS })) {
  if (!String(process.env[key] || '').trim()) {
    process.env[key] = value
  }
}

/** Hard stop if someone explicitly disables the foundation without intending to. */
function assertAuthWave2Flags() {
  for (const key of Object.keys(AUTH_WAVE2_DEFAULTS)) {
    const raw = String(process.env[key] || '').trim()
    if (raw !== '1' && raw !== '0') {
      throw new Error(`${key} must be 1 or 0 after Auth Wave 2 defaults (got ${JSON.stringify(raw)})`)
    }
  }
  const hr = String(process.env.EXPO_PUBLIC_HR_WORKSPACE_ENABLED || '').trim()
  if (hr !== '1' && hr !== '0') {
    throw new Error(
      `EXPO_PUBLIC_HR_WORKSPACE_ENABLED must be 1 or 0 after unified-app defaults (got ${JSON.stringify(hr)})`,
    )
  }
}

assertAuthWave2Flags()

const DEMO_FLAG_KEYS = [
  'EXPO_PUBLIC_HR_HIRING_DEMO',
  'EXPO_PUBLIC_HR_ATTENDANCE_DEMO',
  'EXPO_PUBLIC_HR_SHIFTS_DEMO',
  'EXPO_PUBLIC_HR_ONBOARDING_DEMO',
  'EXPO_PUBLIC_HR_DOCUMENTS_DEMO',
  'EXPO_PUBLIC_HR_TASKS_DEMO',
  'EXPO_PUBLIC_HR_DELIVERY_ALERTS_DEMO',
]

function isProductionReleaseConfig() {
  const marker = String(process.env.EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE || '').trim()
  if (marker === '1') return true
  const profile = String(process.env.EAS_BUILD_PROFILE || '').trim().toLowerCase()
  if (profile === 'production' || profile === 'store') return true
  const channel = String(
    process.env.EXPO_PUBLIC_EAS_CHANNEL || process.env.EAS_UPDATE_CHANNEL || process.env.EAS_CHANNEL || '',
  )
    .trim()
    .toLowerCase()
  return channel === 'production' || channel === 'canary'
}

function assertDemoFlagsSafe() {
  const productionRelease = isProductionReleaseConfig()
  const enabled = DEMO_FLAG_KEYS.filter((key) => String(process.env[key] || '').trim() === '1')
  if (productionRelease && enabled.length) {
    throw new Error(
      `R3 data safety: production release cannot bake demo flags (${enabled.join(', ')}). Unset them or use a development/preview profile.`,
    )
  }
}

assertDemoFlagsSafe()

module.exports = () => ({
  ...appJson.expo,
  extra: {
    ...(appJson.expo.extra || {}),
    authWave2: {
      pin: process.env.EXPO_PUBLIC_LOCAL_PIN_UNLOCK,
      biometric: process.env.EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK,
      autoLock: process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK,
      autoLockBiometric: process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC,
    },
    unifiedApp: {
      hrWorkspace: process.env.EXPO_PUBLIC_HR_WORKSPACE_ENABLED,
      /** Presentation-only Hiring demo. Never default on — must be explicit for canary design passes. */
      hiringDemo: process.env.EXPO_PUBLIC_HR_HIRING_DEMO || '0',
      /** Presentation-only Attendance exception demo. */
      attendanceDemo: process.env.EXPO_PUBLIC_HR_ATTENDANCE_DEMO || '0',
      /** Presentation-only Shifts decision demo. */
      shiftsDemo: process.env.EXPO_PUBLIC_HR_SHIFTS_DEMO || '0',
      /** Presentation-only Onboarding HR-actionable demo. */
      onboardingDemo: process.env.EXPO_PUBLIC_HR_ONBOARDING_DEMO || '0',
      /** Presentation-only Document Reviews needs_review demo. */
      documentsDemo: process.env.EXPO_PUBLIC_HR_DOCUMENTS_DEMO || '0',
      /** Presentation-only HR Tasks open-queue demo. */
      tasksDemo: process.env.EXPO_PUBLIC_HR_TASKS_DEMO || '0',
      /** Presentation-only Delivery Alerts monitor demo. */
      deliveryAlertsDemo: process.env.EXPO_PUBLIC_HR_DELIVERY_ALERTS_DEMO || '0',
    },
    dataSafety: {
      productionRelease: isProductionReleaseConfig() ? '1' : '0',
      allowDemo: isProductionReleaseConfig() ? '0' : '1',
    },
  },
})
