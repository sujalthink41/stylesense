import type { TextStyle } from 'react-native';

/**
 * Anek Latin (Ek Type, India) cut into static instances: React Native can't drive the width
 * axis of a variable font, so condensed display widths ship as their own files.
 */
export const fontFiles = {
  'AnekLatin-Regular': require('../../assets/fonts/AnekLatin-Regular.ttf'),
  'AnekLatin-Medium': require('../../assets/fonts/AnekLatin-Medium.ttf'),
  'AnekLatin-SemiBold': require('../../assets/fonts/AnekLatin-SemiBold.ttf'),
  'AnekLatin-Bold': require('../../assets/fonts/AnekLatin-Bold.ttf'),
  'AnekLatinSemiCondensed-Bold': require('../../assets/fonts/AnekLatinSemiCondensed-Bold.ttf'),
  'AnekLatinCondensed-SemiBold': require('../../assets/fonts/AnekLatinCondensed-SemiBold.ttf'),
  'AnekLatinCondensed-Bold': require('../../assets/fonts/AnekLatinCondensed-Bold.ttf'),
  'AnekLatinCondensed-Heavy': require('../../assets/fonts/AnekLatinCondensed-Heavy.ttf'),
} as const;

export type FontName = keyof typeof fontFiles;

export type TextVariant =
  | 'displayXL'
  | 'display'
  | 'headline'
  | 'title'
  | 'body'
  | 'bodyStrong'
  | 'bodySmall'
  | 'label'
  | 'caption';

interface VariantSpec extends TextStyle {
  fontFamily: FontName;
  fontSize: number;
  lineHeight: number;
  /** Large-text cap so a 200% system font size doesn't explode a display headline. */
  maxScale: number;
}

export const typeScale: Record<TextVariant, VariantSpec> = {
  displayXL: { fontFamily: 'AnekLatinCondensed-Heavy', fontSize: 52, lineHeight: 52, letterSpacing: -1.3, maxScale: 1.2 },
  display: { fontFamily: 'AnekLatinCondensed-Heavy', fontSize: 36, lineHeight: 38, letterSpacing: -0.8, maxScale: 1.3 },
  headline: { fontFamily: 'AnekLatinSemiCondensed-Bold', fontSize: 24, lineHeight: 28, letterSpacing: -0.2, maxScale: 1.4 },
  title: { fontFamily: 'AnekLatin-SemiBold', fontSize: 19, lineHeight: 24, maxScale: 1.6 },
  body: { fontFamily: 'AnekLatin-Regular', fontSize: 16, lineHeight: 24, maxScale: 2 },
  bodyStrong: { fontFamily: 'AnekLatin-SemiBold', fontSize: 16, lineHeight: 22, maxScale: 2 },
  bodySmall: { fontFamily: 'AnekLatin-Medium', fontSize: 14, lineHeight: 20, maxScale: 2 },
  label: { fontFamily: 'AnekLatin-SemiBold', fontSize: 15, lineHeight: 18, letterSpacing: 0.15, maxScale: 1.6 },
  caption: { fontFamily: 'AnekLatin-Medium', fontSize: 12, lineHeight: 16, letterSpacing: 0.2, maxScale: 1.8 },
};

/** Prices and comparisons: condensed, tabular so columns of numbers line up. */
export const priceType = {
  xl: { fontFamily: 'AnekLatinCondensed-Heavy' as FontName, fontSize: 52, lineHeight: 54, symbol: 30 },
  lg: { fontFamily: 'AnekLatinCondensed-Heavy' as FontName, fontSize: 36, lineHeight: 38, symbol: 21 },
  md: { fontFamily: 'AnekLatinCondensed-Bold' as FontName, fontSize: 24, lineHeight: 28, symbol: 16 },
  sm: { fontFamily: 'AnekLatinCondensed-Bold' as FontName, fontSize: 18, lineHeight: 22, symbol: 13 },
} as const;

export type PriceSize = keyof typeof priceType;
