/**
 * Wire an Apple Icon Composer `.icon` package into the iOS target.
 *
 * Expo SDK 51 stock icons only understand PNGs. This plugin copies a Liquid Glass
 * `.icon` and sets ASSETCATALOG_COMPILER_APPICON_NAME — but only when explicitly
 * enabled, because compiling `.icon` requires Xcode 26+ and Expo SDK 51 currently
 * fails to build against Xcode 26 (Swift exhaustiveness / RN toolchain mismatch).
 *
 * Enable with env:
 *   WATHEFNI_IOS_ICON_COMPOSER=1
 *
 * Options:
 *   { icon: "./assets/WathefniAppIcon.icon" }
 */
const fs = require('fs')
const path = require('path')
const {
  IOSConfig,
  withDangerousMod,
  withXcodeProject,
  createRunOncePlugin,
} = require('@expo/config-plugins')

const DEFAULT_ICON = './assets/WathefniAppIcon.icon'

function enabled() {
  return process.env.WATHEFNI_IOS_ICON_COMPOSER === '1'
}

function assertIconPackage(absPath) {
  if (!fs.existsSync(absPath) || !fs.statSync(absPath).isDirectory()) {
    throw new Error(`Liquid Glass icon package missing: ${absPath}`)
  }
  const manifest = path.join(absPath, 'icon.json')
  if (!fs.existsSync(manifest)) {
    throw new Error(`Liquid Glass icon package missing icon.json: ${absPath}`)
  }
}

function withLiquidGlassIcon(config, props = {}) {
  if (!enabled()) {
    return config
  }

  const iconRel = props.icon || DEFAULT_ICON
  const iconName = path.basename(iconRel, '.icon')

  config = withDangerousMod(config, [
    'ios',
    async (cfg) => {
      const projectRoot = cfg.modRequest.projectRoot
      const projectName = cfg.modRequest.projectName || IOSConfig.XcodeUtils.getProjectName(projectRoot)
      const source = path.join(projectRoot, iconRel)
      assertIconPackage(source)
      const targetDir = path.join(projectRoot, 'ios', projectName, `${iconName}.icon`)
      fs.rmSync(targetDir, { recursive: true, force: true })
      fs.cpSync(source, targetDir, { recursive: true })
      return cfg
    },
  ])

  config = withXcodeProject(config, (cfg) => {
    const project = cfg.modResults
    const projectName = cfg.modRequest.projectName
    if (!projectName) return cfg

    const configurations = project.pbxXCBuildConfigurationSection()
    for (const value of Object.values(configurations)) {
      if (value && typeof value === 'object' && value.buildSettings) {
        value.buildSettings.ASSETCATALOG_COMPILER_APPICON_NAME = iconName
      }
    }

    const iconPath = `${projectName}/${iconName}.icon`
    IOSConfig.XcodeUtils.addResourceFileToGroup({
      filepath: iconPath,
      groupName: projectName,
      project,
      isBuildFile: true,
      verbose: false,
    })
    return cfg
  })

  return config
}

module.exports = createRunOncePlugin(withLiquidGlassIcon, 'with-wathefni-liquid-glass-icon', '1.0.0')
