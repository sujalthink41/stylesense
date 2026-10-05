import * as Haptics from 'expo-haptics';
import type { StyleProp, ViewStyle } from 'react-native';

import { useTheme } from '@/design/theme';

import { Icon, type IconName } from './Icon';
import { PressableScale } from './PressableScale';

export interface IconButtonProps {
  icon: IconName;
  /** Required: icon-only buttons must say what they do. */
  label: string;
  onPress?: () => void;
  variant?: 'surface' | 'shell' | 'action' | 'tonal' | 'glass';
  size?: 44 | 48 | 52 | 64 | 72;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export function IconButton({
  icon,
  label,
  onPress,
  variant = 'surface',
  size = 48,
  disabled,
  style,
  testID,
}: IconButtonProps) {
  const { colors, elevation } = useTheme();
  const look = {
    surface: { bg: colors.raised, fg: colors.text, shadow: elevation(2) },
    shell: { bg: colors.shell, fg: colors.bestPrice, shadow: elevation(2) },
    action: { bg: colors.action, fg: colors.onAction, shadow: elevation(3) },
    tonal: { bg: colors.tonal, fg: colors.onTonal, shadow: {} },
    glass: { bg: colors.shellRaised, fg: colors.onShell, shadow: {} },
  }[variant];
  const glyph = Math.round(size * (size >= 64 ? 0.42 : 0.46));
  return (
    <PressableScale
      testID={testID}
      accessibilityLabel={label}
      disabled={disabled}
      hitSlop={size < 48 ? (48 - size) / 2 : 0}
      onPress={() => {
        if (variant === 'action') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        onPress?.();
      }}
      scaleTo={0.92}
      style={[
        { width: size, height: size, borderRadius: size, alignItems: 'center', justifyContent: 'center', backgroundColor: look.bg },
        look.shadow,
        disabled && { opacity: 0.4 },
        style,
      ]}
    >
      <Icon name={icon} size={glyph} color={look.fg} strokeWidth={size >= 64 ? 2.2 : 2} />
    </PressableScale>
  );
}
