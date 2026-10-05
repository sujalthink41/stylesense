import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { Text } from '@/ui/atoms/Text';

/**
 * The signature loader: while the stylist searches, the block prints across the space one
 * impression at a time. Reduce Motion shows the finished print, still.
 */
export function PrintRepeat({ label = 'Printing your picks…', rows = 3 }: { label?: string; rows?: number }) {
  const { colors, elevation } = useTheme();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]}
      accessibilityRole="progressbar"
      accessibilityLabel={label}
    >
      <View style={styles.grid}>
        {Array.from({ length: rows * 4 }, (_, i) => (
          <Impression key={i} index={i} color={i % 7 === 5 ? colors.bestPrice : colors.shell} />
        ))}
      </View>
      <Text variant="bodySmall" tone="secondary" align="center">
        {label}
      </Text>
    </View>
  );
}

function Impression({ index, color }: { index: number; color: string }) {
  const reduced = useReducedMotion();
  const ink = useSharedValue(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) return;
    ink.value = withDelay(
      index * 110,
      withRepeat(withSequence(withTiming(1, { duration: 240 }), withDelay(1400, withTiming(0.12, { duration: 500 }))), -1),
    );
  }, [index, ink, reduced]);
  const style = useAnimatedStyle(() => ({ opacity: 0.12 + ink.value * 0.88, transform: [{ scale: 1.15 - ink.value * 0.15 }] }));
  return (
    <Animated.View style={style}>
      <Buti size={44} color={color} petals={6} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.xl, paddingVertical: 28, paddingHorizontal: 20, gap: 18 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-around', rowGap: 14 },
});
