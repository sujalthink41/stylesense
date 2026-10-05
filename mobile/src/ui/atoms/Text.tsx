import { Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { useTheme } from '@/design/theme';
import { typeScale, type TextVariant } from '@/design/typography';
import type { Colors } from '@/design/tokens';

export type TextTone =
  | 'default'
  | 'secondary'
  | 'disabled'
  | 'onShell'
  | 'onShellMuted'
  | 'onAction'
  | 'onTonal'
  | 'action'
  | 'saving'
  | 'onBestPrice'
  | 'onBestPriceWash';

const toneColor: Record<TextTone, keyof Colors> = {
  default: 'text',
  secondary: 'textSecondary',
  disabled: 'textDisabled',
  onShell: 'onShell',
  onShellMuted: 'onShellMuted',
  onAction: 'onAction',
  onTonal: 'onTonal',
  action: 'action',
  saving: 'saving',
  onBestPrice: 'onBestPrice',
  onBestPriceWash: 'onBestPriceWash',
};

export interface TextProps extends RNTextProps {
  variant?: TextVariant;
  tone?: TextTone;
  align?: 'left' | 'center' | 'right';
}

/** The only way the app sets type: a variant from the scale plus a tone from the theme. */
export function Text({ variant = 'body', tone = 'default', align, style, ...rest }: TextProps) {
  const { colors } = useTheme();
  const { maxScale, ...spec } = typeScale[variant];
  return (
    <RNText
      maxFontSizeMultiplier={maxScale}
      {...rest}
      style={[spec, { color: colors[toneColor[tone]] }, align ? { textAlign: align } : null, style]}
    />
  );
}
