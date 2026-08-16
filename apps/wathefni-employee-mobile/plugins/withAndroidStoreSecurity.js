const { withAndroidManifest } = require('@expo/config-plugins')

/** Store builds must not expose app data to Android backup or cleartext transport. */
module.exports = function withAndroidStoreSecurity(config) {
  return withAndroidManifest(config, (modConfig) => {
    const application = modConfig.modResults.manifest.application?.[0]
    if (!application?.$) {
      throw new Error('AndroidManifest application node is missing')
    }
    application.$['android:allowBackup'] = 'false'
    application.$['android:usesCleartextTraffic'] = 'false'
    return modConfig
  })
}
