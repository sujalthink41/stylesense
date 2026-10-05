import * as Haptics from 'expo-haptics';
import { useCallback, useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';

export interface BudgetSliderProps {
  label: string;
  minPaise: number;
  maxPaise: number;
  stepPaise: number;
  value: number;
  onChange(paise: number): void;
}

const THUMB = 32;

export function snap(raw: number, min: number, max: number, step: number): number {
  const clamped = Math.min(max, Math.max(min, raw));
  return Math.min(max, Math.round((clamped - min) / step) * step + min);
}

/**
 * A budget "up to" slider: drag the block, or use the adjustable accessibility actions
 * (swipe up/down with TalkBack). The value is shown at display scale.
 */
export function BudgetSlider({ label, minPaise, maxPaise, stepPaise, value, onChange }: BudgetSliderProps) {
  const { colors, elevation } = useTheme();
  const [width, setWidth] = useState(0);
  const range = Math.max(1, maxPaise - minPaise);
  const fraction = (value - minPaise) / range;

  const setFromX = useCallback(
    (x: number) => {
      if (width <= 0) return;
      const next = snap(minPaise + (x / width) * range, minPaise, maxPaise, stepPaise);
      if (next !== value) {
        void Haptics.selectionAsync();
        onChange(next);
      }
    },
    [width, minPaise, maxPaise, stepPaise, range, value, onChange],
  );

  // JS-thread callbacks: the value is React state anyway, and snapping steps are coarse.
  const pan = Gesture.Pan()
    .runOnJS(true)
    .minDistance(0)
    .onBegin((e) => setFromX(e.x))
    .onUpdate((e) => setFromX(e.x));

  return (
    <View style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]}>
      <Text variant="bodySmall" tone="secondary">
        {label}
      </Text>
      <View style={styles.valueRow}>
        <Text variant="body" tone="secondary">
          Up to
        </Text>
        <Price paise={value} size="lg" />
      </View>
      <GestureDetector gesture={pan}>
        <View
          style={styles.track}
          onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}
          accessible
          accessibilityRole="adjustable"
          accessibilityLabel="Budget"
          accessibilityValue={{ text: `Up to ${formatRupees(value)}` }}
          accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
          onAccessibilityAction={(e) => {
            const delta = e.nativeEvent.actionName === 'increment' ? stepPaise : -stepPaise;
            onChange(snap(value + delta, minPaise, maxPaise, stepPaise));
          }}
        >
          <View style={[styles.rail, { backgroundColor: colors.tonal }]} />
          <View style={[styles.rail, { backgroundColor: colors.shell, width: `${fraction * 100}%` }]} />
          <View
            style={[
              styles.thumb,
              { left: Math.max(0, fraction * width - THUMB / 2), backgroundColor: colors.shell },
              elevation(2),
            ]}
          >
            <View style={[styles.eye, { backgroundColor: colors.bestPrice }]} />
          </View>
        </View>
      </GestureDetector>
      <View style={styles.ends}>
        <Text variant="caption" tone="secondary">
          {formatRupees(minPaise)}
        </Text>
        <Text variant="caption" tone="secondary">
          {formatRupees(maxPaise)}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, padding: 20, gap: 12 },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  track: { height: 44, justifyContent: 'center' },
  rail: { position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 4 },
  thumb: { position: 'absolute', width: THUMB, height: THUMB, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  eye: { width: 10, height: 10, borderRadius: 3 },
  ends: { flexDirection: 'row', justifyContent: 'space-between' },
});
