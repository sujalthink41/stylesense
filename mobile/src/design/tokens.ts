/**
 * Indigo & Block design tokens: the single source of every colour, size and timing in the
 * app. Screens never pick values; they pick tokens. Mirrors the design-system canvas.
 */

export const palette = {
  indigoNight: '#0F1633',
  indigo900: '#16204A',
  indigo: '#1F2B5C', // vat indigo: the brand shell
  indigo700: '#2C3B78',
  indigo500: '#4A5DB0',
  indigoMist: '#C9CFE8', // hairlines, text on indigo
  indigoWash: '#E4E7F3', // chips, tonal fills
  cotton: '#F2F3F7', // indigo-rinsed cotton: the ground
  white: '#FFFFFF',
  madder: '#B8322A', // actions only
  madderLight: '#E2574C', // madder on dark grounds
  madderTint: '#F7D9D6',
  turmeric: '#D9A21B', // the single best price on a screen
  turmericWash: '#FBF1D3',
  turmericInk: '#4A3708',
  neem: '#1E7A4F', // savings, in stock
  ink: '#14161B', // syahi: text
  ink600: '#4B5060', // secondary text (7.4:1 on cotton)
  ink400: '#8A8FA0', // disabled, struck prices (large text only)
} as const;

export type ColorScheme = 'light' | 'dark';

export interface Colors {
  ground: string;
  raised: string;
  shell: string; // the indigo band, sign-in, navigation accents
  shellRaised: string; // fields and chips on the shell
  onShell: string;
  onShellMuted: string;
  text: string;
  textSecondary: string;
  textDisabled: string;
  hairline: string;
  tonal: string;
  onTonal: string;
  action: string;
  onAction: string;
  bestPrice: string;
  onBestPrice: string;
  bestPriceWash: string;
  onBestPriceWash: string;
  saving: string;
  danger: string;
  focus: string;
  scrim: string;
  shadow: string;
}

export const colors: Record<ColorScheme, Colors> = {
  light: {
    ground: palette.cotton,
    raised: palette.white,
    shell: palette.indigo,
    shellRaised: palette.indigo700,
    onShell: palette.white,
    onShellMuted: palette.indigoMist,
    text: palette.ink,
    textSecondary: palette.ink600,
    textDisabled: palette.ink400,
    hairline: palette.indigoWash,
    tonal: palette.indigoWash,
    onTonal: palette.indigo,
    action: palette.madder,
    onAction: palette.white,
    bestPrice: palette.turmeric,
    onBestPrice: palette.ink,
    bestPriceWash: palette.turmericWash,
    onBestPriceWash: palette.turmericInk,
    saving: palette.neem,
    danger: palette.madder,
    focus: palette.turmeric,
    scrim: 'rgba(15,22,51,0.55)',
    shadow: '22,32,74',
  },
  dark: {
    ground: palette.indigoNight,
    raised: '#1A2450',
    shell: palette.indigo900,
    shellRaised: palette.indigo700,
    onShell: palette.white,
    onShellMuted: palette.indigoMist,
    text: '#F2F3F7',
    textSecondary: '#AEB5D4',
    textDisabled: '#6C7398',
    hairline: '#26306A',
    tonal: '#26306A',
    onTonal: '#E4E7F3',
    action: palette.madderLight,
    onAction: palette.white,
    bestPrice: palette.turmeric,
    onBestPrice: palette.ink,
    bestPriceWash: '#3A3214',
    onBestPriceWash: '#F5D98B',
    saving: '#4CC48C',
    danger: palette.madderLight,
    focus: palette.turmeric,
    scrim: 'rgba(0,0,0,0.6)',
    shadow: '0,0,0',
  },
};

/** 4-pt base, 8-pt rhythm. */
export const space = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
  screen: 20, // screen side margin
} as const;

export const radius = {
  sm: 8, // badges
  md: 14, // buttons, fields
  lg: 20, // cards
  xl: 24, // feature cards
  sheet: 28, // sheets, the indigo band
  pill: 999, // chips only
} as const;

/** One soft, tinted shadow per level; never a border plus a shadow. */
export function elevation(level: 0 | 1 | 2 | 3, scheme: ColorScheme = 'light'): { boxShadow?: string } {
  const rgb = colors[scheme].shadow;
  switch (level) {
    case 0:
      return {};
    case 1:
      return { boxShadow: `0px 2px 8px rgba(${rgb},0.08)` };
    case 2:
      return { boxShadow: `0px 6px 18px rgba(${rgb},0.10)` };
    case 3:
      return { boxShadow: `0px 18px 40px rgba(${rgb},0.16)` };
  }
}

export const touch = {
  min: 48, // Material minimum target (dp)
  gap: 8,
} as const;

export const motion = {
  press: 120,
  ui: 220,
  screen: 380,
  stampPress: 90,
  stampSpread: 300,
  pressedScale: 0.97,
} as const;
