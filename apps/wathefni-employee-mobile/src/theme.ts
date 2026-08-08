// Phase A+B: warm editorial foundation with disciplined colour roles.
/**
 * Colour has three roles and they must not be mixed.
 *
 *  ground   cream + ink. The dominant surface of every screen.
 *  ambient  brand pastels. Module identity and warmth only — never a status.
 *  semantic success / warning / danger / accent. Status and interaction only,
 *           drawn as bordered chips on `surface` so a status can never be
 *           mistaken for an ambient fill (and an ambient fill can never be
 *           misread as a status).
 *
 * Ambient and semantic previously shared near-identical values (sage vs
 * successSoft measured dE 1.7, blush vs dangerSoft dE 2.1), which is why colour
 * could not carry meaning. Every ambient tone is now at least dE 12 from every
 * semantic colour, and every pairing below passes WCAG AA for the sizes in use.
 */
export const colors = {
  // — ground —
  bg: '#F9F3E5',
  surface: '#FFFCF4',
  surfaceMuted: '#F0E8D8',
  border: '#E5DAC6',
  ink: '#1B1A17',
  text: '#1B1A17',
  subtle: '#5E5850',
  primary: '#1B1A17',
  primaryText: '#FFFFFF',

  // — ambient (module identity; cream still dominates every screen) —
  butter: '#F6DA92',
  pink: '#F7CFE3',
  olive: '#DCE2BB',
  sky: '#C7D9EF',
  lilac: '#D6C9F0',

  // — semantic (status + interaction only) —
  success: '#2A6241',
  warning: '#8A4A15',
  danger: '#9B3239',
  accent: '#93356B',
}

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 40,
}

/**
 * One page geometry for every employee screen. Screens previously drifted
 * between 12 / 16 / 24pt horizontal margins and 24 / 40 / 120pt bottom padding,
 * which was visible as sideways shift while navigating. Anything that needs to
 * differ should differ for a stated product reason, not by accident.
 */
export const layout = {
  /** Horizontal margin for all page content. */
  pageMargin: spacing.lg,
  /**
   * Wider margin, used only by full-screen single-task surfaces that sit outside
   * the tab shell — activation, PIN, biometric opt-in. These have one job and no
   * lists, so the extra breathing room is deliberate rather than drift.
   */
  focusMargin: spacing.xl,
  /** Space above the first element after the nav row. */
  pageTop: spacing.md,
  /** Space between top-level page sections. */
  sectionGap: spacing.lg,
  /** Space between sibling cards/rows inside one section. */
  cardGap: spacing.sm,
  /** Tab bar content height; the bottom safe-area inset is added on top. */
  tabBarBase: 60,
  /** Clearance under the last element, above the tab bar / home indicator. */
  scrollBottom: spacing.xxl,
  /** Minimum interactive size. */
  touchTarget: 44,
}

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
}

export const font = {
  display: 30,
  h1: 26,
  h2: 20,
  h3: 17,
  body: 15,
  small: 13,
  tiny: 11.5,
}

/**
 * Dynamic Type ceilings. Scaling stays on everywhere; these only stop a title
 * from consuming an entire small screen before the body copy is reachable.
 * Body and action text scale further than display text on purpose.
 */
export const typeScaling = {
  display: 1.6,
  heading: 1.8,
  body: 2,
  chip: 1.6,
}

export const shadows = {
  card: {
    shadowColor: '#5D5144',
    shadowOpacity: 0.07,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 5 },
    elevation: 2,
  },
}
