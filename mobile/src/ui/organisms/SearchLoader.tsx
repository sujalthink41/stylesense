import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeOut,
  ReduceMotion,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { Text } from '@/ui/atoms/Text';

export const SEARCH_STEPS = [
  'Reading your request…',
  'Searching Amazon, Flipkart & Myntra…',
  'Comparing prices…',
  'Picking the best for you…',
];

/**
 * The "we're working on it" screen: a status line that moves through what's actually
 * happening, a sliding progress bar, and two shimmering cards shaped like what's coming.
 */
export function SearchLoader({ steps = SEARCH_STEPS, cards = 2 }: { steps?: string[]; cards?: number }) {
  const { colors } = useTheme();
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 1_600);
    return () => clearInterval(timer);
  }, [steps.length]);

  return (
    <View style={styles.wrap} accessibilityRole="progressbar" accessibilityLabel={steps[step]} accessibilityLiveRegion="polite">
      <View style={styles.head}>
        <Spinner />
        <Animated.View
          key={step}
          entering={reduced ? undefined : FadeIn.duration(220).reduceMotion(ReduceMotion.System)}
          exiting={reduced ? undefined : FadeOut.duration(160).reduceMotion(ReduceMotion.System)}
          style={{ flex: 1 }}
        >
          <Text variant="headline" numberOfLines={2}>
            {steps[step]}
          </Text>
        </Animated.View>
      </View>
      <ProgressBar />
      <View style={styles.cards}>
        {Array.from({ length: cards }, (_, i) => (
          <View key={i} style={[styles.card, { backgroundColor: colors.raised }]}>
            <Shimmer style={styles.photo} />
            <View style={styles.lines}>
              <Shimmer style={{ height: 12, width: '45%', borderRadius: 6 }} />
              <Shimmer style={{ height: 16, width: '85%', borderRadius: 8 }} />
              <Shimmer style={{ height: 22, width: '35%', borderRadius: 8 }} />
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

/** The buti turning: our spinner. */
export function Spinner({ size = 36, color = palette.turmeric }: { size?: number; color?: string }) {
  const turn = useSharedValue(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!reduced) turn.set(withRepeat(withTiming(1, { duration: 1_400, easing: Easing.linear }), -1));
  }, [turn, reduced]);
  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${turn.value * 360}deg` }] }));
  return (
    <Animated.View style={style}>
      <Buti size={size} petals={8} color={color} />
    </Animated.View>
  );
}

function ProgressBar() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const x = useSharedValue(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!reduced) x.set(withRepeat(withTiming(1, { duration: 1_300, easing: Easing.inOut(Easing.cubic) }), -1));
  }, [x, reduced]);
  const bar = useAnimatedStyle(() => ({ transform: [{ translateX: -width * 0.4 + x.value * width * 1.2 }] }));
  return (
    <View style={[styles.track, { backgroundColor: colors.tonal }]}>
      <Animated.View style={[styles.bar, { width: width * 0.4, backgroundColor: palette.turmeric }, reduced ? { width: '60%' } : bar]} />
    </View>
  );
}

function Shimmer({ style }: { style: object }) {
  const { colors } = useTheme();
  const x = useSharedValue(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!reduced) x.set(withRepeat(withTiming(1, { duration: 1_200, easing: Easing.inOut(Easing.quad) }), -1));
  }, [x, reduced]);
  const sweep = useAnimatedStyle(() => ({ transform: [{ translateX: `${-100 + x.value * 200}%` }] }));
  return (
    <View style={[{ backgroundColor: colors.tonal, overflow: 'hidden' }, style]}>
      {reduced ? null : (
        <Animated.View style={[StyleSheet.absoluteFill, sweep]}>
          <LinearGradient
            colors={['transparent', 'rgba(255,255,255,0.55)', 'transparent']}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 16 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 56 },
  track: { height: 6, borderRadius: 3, overflow: 'hidden' },
  bar: { height: '100%', borderRadius: 3 },
  cards: { flexDirection: 'row', gap: 12 },
  card: { flex: 1, borderRadius: radius.lg, overflow: 'hidden' },
  photo: { aspectRatio: 0.8 },
  lines: { padding: 12, gap: 8 },
});
