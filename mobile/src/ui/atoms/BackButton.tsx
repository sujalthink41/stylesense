import { BlurView } from 'expo-blur';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';

import { Icon } from './Icon';
import { PressableScale } from './PressableScale';

export interface BackButtonProps {
  /** Defaults to going back, or Home when there's nothing to go back to. */
  onPress?: () => void;
  /** "glass" floats over photos and the indigo shell; "solid" sits on the ground. */
  variant?: 'solid' | 'glass';
  /** Close (×) instead of back (‹), for screens that slide up. */
  close?: boolean;
  label?: string;
}

/** One back control everywhere: a 44 pt circle with a hairline ring and a soft shadow. */
export function BackButton({ onPress, variant = 'solid', close = false, label }: BackButtonProps) {
  const { colors, elevation, scheme } = useTheme();
  const glass = variant === 'glass';
  return (
    <PressableScale
      accessibilityRole="button"
      accessibilityLabel={label ?? (close ? 'Close' : 'Back')}
      hitSlop={8}
      scaleTo={0.9}
      onPress={() => {
        void Haptics.selectionAsync();
        if (onPress) onPress();
        else if (router.canGoBack()) router.back();
        else router.replace('/');
      }}
      style={[
        styles.circle,
        glass
          ? { borderColor: 'rgba(255,255,255,0.35)' }
          : { backgroundColor: colors.raised, borderColor: colors.hairline },
        !glass && elevation(2),
      ]}
    >
      {glass ? <BlurView intensity={40} tint={scheme === 'dark' ? 'dark' : 'light'} style={StyleSheet.absoluteFill} /> : null}
      <View style={close ? undefined : styles.nudge}>
        <Icon name={close ? 'close' : 'chevronLeft'} size={22} color={glass ? '#FFFFFF' : colors.text} strokeWidth={2.4} />
      </View>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  circle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth * 2,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  nudge: { marginLeft: -2 }, // optical centre of a chevron sits left of its box
});
