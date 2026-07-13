module.exports = function (api) {
  api.cache(true)
  return {
    presets: ['babel-preset-expo'],
    // Strip console.* from production bundles (App Store / Play Store hygiene).
    env: {
      production: {
        plugins: ['transform-remove-console'],
      },
    },
  }
}
