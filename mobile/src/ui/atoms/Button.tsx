import * as Haptics from 'expo-haptics';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';

import { Icon, type IconName } from './Icon';
import { PressableScale } from './PressableScale';
import { PrintDots } from './PrintDots';
import { Text, type TextTone } from './Text';

export type ButtonVariant = 'action' | 'primary' | 'tonal' | 'ghost' | 'inverse';

export interface ButtonProps {
  label: string;
  onPress?: () => void;
  /** action = madder (spends or commits) · primary = indigo (move forward) · tonal · ghost · inverse (on indigo). */
  variant?: ButtonVariant;
  size?: 'lg' | 'md';
  icon?: IconName;
  iconPosition?: 'start' | 'end';
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'lg',
  icon,
  iconPosition = 'start',
  loading = false,
  disabled = false,
  fullWidth = false,
  accessibilityHint,
  style,
  testID,
}: ButtonProps) {
  const { colors, elevation } = useTheme();
  const inactive = disabled || loading;
  const look: Record<ButtonVariant, { bg: string; fg: string; tone: TextTone; shadow: object }> = {
    action: { bg: colors.action, fg: colors.onAction, tone: 'onAction', shadow: elevation(2) },
    primary: { bg: colors.shell, fg: colors.onShell, tone: 'onShell', shadow: {} },
    tonal: { bg: colors.tonal, fg: colors.onTonal, tone: 'onTonal', shadow: {} },
    ghost: { bg: 'transparent', fg: colors.onTonal, tone: 'onTonal', shadow: {} },
    inverse: { bg: colors.ground, fg: colors.shell, tone: 'onTonal', shadow: {} },
  };
  const v = look[variant];
  const height = size === 'lg' ? 56 : 48;
  return (
    <PressableScale
      testID={testID}
      onPress={() => {
        if (variant === 'action') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress?.();
      }}
      disabled={inactive}
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      style={[
        styles.base,
        { height, backgroundColor: disabled ? colors.tonal : v.bg },
        !disabled && v.shadow,
        fullWidth && styles.full,
        style,
      ]}
    >
      {loading ? (
        <PrintDots color={variant === 'action' || variant === 'primary' ? colors.bestPrice : colors.onTonal} />
      ) : (
        <View style={[styles.row, iconPosition === 'end' && styles.reverse]}>
          {icon ? <Icon name={icon} size={20} color={disabled ? colors.textDisabled : v.fg} strokeWidth={2} /> : null}
          <Text variant="label" tone={disabled ? 'disabled' : v.tone} style={{ fontSize: size === 'lg' ? 17 : 16 }}>
            {label}
          </Text>
        </View>
      )}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 48,
  },
  full: { alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  reverse: { flexDirection: 'row-reverse' },
});
