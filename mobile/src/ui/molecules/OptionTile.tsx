import * as Haptics from 'expo-haptics';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { interpolateColor, useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { enter } from '@/ui/motion';

// Colour answers show the colour itself, not just its name.
const SWATCHES: Record<string, string> = {
  black: '#14161B', white: '#FFFFFF', navy: '#1F2B5C', blue: '#2F5DA8', 'sky blue': '#8EC1E6', red: '#B8322A',
  maroon: '#6E1F24', pink: '#E79AB0', green: '#2E7D4F', olive: '#6B7A3A', yellow: '#E8C547', mustard: '#D9A21B',
  beige: '#E3D3B5', cream: '#F4EBDC', brown: '#7A5235', grey: '#8A8FA0', gray: '#8A8FA0', orange: '#E07B39',
  purple: '#6C4AA0', lavender: '#B9A7DD', gold: '#C9A13B', silver: '#C4C7CF', khaki: '#BDAE82', teal: '#2A7F7F',
};

const MOTIFS = [palette.indigo, palette.turmeric, palette.madder, palette.neem] as const;

export function swatchFor(label: string): string | null {
  return SWATCHES[label.trim().toLowerCase()] ?? null;
}

export interface OptionTileProps {
  label: string;
  index: number;
  selected: boolean;
  disabled?: boolean;
  onPress(): void;
  testID?: string;
}

/**
 * One answer to a stylist question: a tile printed with a small buti in its corner. Selected,
 * it dyes indigo and a turmeric check stamps in.
 */
export function OptionTile({ label, index, selected, disabled, onPress, testID }: OptionTileProps) {
  const { colors, elevation } = useTheme();
  const on = useSharedValue(selected ? 1 : 0);
  useEffect(() => {
    on.set(withTiming(selected ? 1 : 0, { duration: 180 }));
  }, [selected, on]);
  const fill = useAnimatedStyle(() => ({
    backgroundColor: interpolateColor(on.value, [0, 1], [colors.raised, colors.shell]),
    transform: [{ scale: withSpring(selected ? 1.02 : 1, { damping: 14 }) }],
  }));
  const swatch = swatchFor(label);
  const motif = MOTIFS[index % MOTIFS.length]!;
  return (
    <Animated.View entering={enter.rise(index)} style={styles.cell}>
      <PressableScale
        testID={testID}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: selected, disabled: !!disabled }}
        accessibilityLabel={label}
        disabled={disabled}
        scaleTo={0.95}
        onPress={() => {
          void Haptics.selectionAsync();
          onPress();
        }}
      >
        <Animated.View style={[styles.tile, elevation(selected ? 3 : 1), fill, disabled && !selected && { opacity: 0.55 }]}>
          <View style={styles.motif} pointerEvents="none">
            <Buti size={58} petals={index % 2 ? 6 : 8} color={selected ? palette.indigo700 : motif} />
          </View>
          {swatch ? <View style={[styles.swatch, { backgroundColor: swatch, borderColor: colors.hairline }]} /> : null}
          <Text variant="bodyStrong" tone={selected ? 'onShell' : 'default'} numberOfLines={2} style={styles.label}>
            {label}
          </Text>
          {selected ? (
            <Animated.View entering={enter.pop()} style={[styles.check, { backgroundColor: colors.bestPrice }]}>
              <Icon name="check" size={14} color={palette.ink} strokeWidth={3} />
            </Animated.View>
          ) : null}
        </Animated.View>
      </PressableScale>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  cell: { width: '48%' },
  tile: { minHeight: 84, borderRadius: radius.lg, padding: 16, justifyContent: 'flex-end', overflow: 'hidden', gap: 8 },
  motif: { position: 'absolute', right: -14, top: -14, opacity: 0.16 },
  swatch: { width: 26, height: 26, borderRadius: 13, borderWidth: 1 },
  label: { fontSize: 17 },
  check: { position: 'absolute', top: 10, right: 10, width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
});
