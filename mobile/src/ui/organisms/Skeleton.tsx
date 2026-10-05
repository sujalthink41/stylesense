import { useEffect, type ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { PrintRepeat } from '@/ui/molecules/PrintRepeat';

export type SkeletonShape = 'cards' | 'question' | 'comparison';

const LABELS: Record<SkeletonShape, string> = {
  cards: 'Printing your picks…',
  question: 'Thinking…',
  comparison: 'Checking prices in every store…',
};

/**
 * What the screen will look like, before it arrives: the server names the shape (ui.loading),
 * so the layout doesn't jump when the real screen lands. Card searches get the print loader.
 */
export function Skeleton({ shape, count = 3 }: { shape: SkeletonShape; count?: number }) {
  if (shape === 'cards') return <PrintRepeat label={LABELS.cards} />;
  return (
    <Pulse label={LABELS[shape]}>
      {shape === 'question' ? <QuestionBones options={count} /> : <ComparisonBones offers={count} />}
    </Pulse>
  );
}

function Pulse({ label, children }: { label: string; children: ReactNode }) {
  const reduced = useReducedMotion();
  const glow = useSharedValue(0);
  useEffect(() => {
    if (!reduced) glow.value = withRepeat(withTiming(1, { duration: 900 }), -1, true);
  }, [glow, reduced]);
  const style = useAnimatedStyle(() => ({ opacity: 0.55 + glow.value * 0.45 }));
  return (
    <Animated.View style={[styles.stack, style]} accessibilityRole="progressbar" accessibilityLabel={label}>
      {children}
    </Animated.View>
  );
}

function Bone({ style }: { style: ViewStyle }) {
  const { colors } = useTheme();
  return <View style={[{ backgroundColor: colors.tonal, borderRadius: radius.sm }, style]} />;
}

function QuestionBones({ options }: { options: number }) {
  return (
    <>
      <Bone style={{ height: 30, width: '85%' }} />
      <Bone style={{ height: 30, width: '55%' }} />
      <View style={styles.row}>
        {Array.from({ length: Math.max(2, options) }, (_, i) => (
          <Bone key={i} style={{ height: 48, width: 96 + (i % 3) * 18, borderRadius: radius.pill }} />
        ))}
      </View>
    </>
  );
}

function ComparisonBones({ offers }: { offers: number }) {
  return (
    <>
      <Bone style={{ height: 360, borderRadius: radius.xl }} />
      <Bone style={{ height: 16, width: '30%' }} />
      <Bone style={{ height: 26, width: '75%' }} />
      <Bone style={{ height: 40, width: '40%' }} />
      {Array.from({ length: offers }, (_, i) => (
        <Bone key={i} style={{ height: 64, borderRadius: radius.md }} />
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 14 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
});
