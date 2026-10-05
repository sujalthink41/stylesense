import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  interpolate,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

import { useTheme } from '@/design/theme';
import { motion } from '@/design/tokens';
import { Stamp } from '@/ui/atoms/Buti';
import { IconButton } from '@/ui/atoms/IconButton';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';

import { ProductSwipeCard, type ProductCardData } from './ProductSwipeCard';

export type SwipeDirection = 'left' | 'right' | 'super';

export interface SwipeDeckProps {
  cards: ProductCardData[];
  onSwipe(card: ProductCardData, direction: SwipeDirection): void;
  onOpen(card: ProductCardData): void;
  /** Called when two cards remain, so the next page can be fetched before the deck empties. */
  onRunningLow?: () => void;
  emptyLabel?: string;
}

const THRESHOLD = 110;

/**
 * Cards may grow (refills append) but never reorder; a new deck from the server must remount
 * this component (give it a fresh key) so it starts again at the top.
 *
 * Swipe right to like (the block stamp lands), left to skip; the buttons below do the same, so
 * nobody has to swipe. Tapping the card opens it.
 */
export function SwipeDeck({ cards, onSwipe, onOpen, onRunningLow, emptyLabel = "That's every pick for now." }: SwipeDeckProps) {
  const { colors } = useTheme();
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);
  const x = useSharedValue(0);
  const stamp = useSharedValue(0);
  // A shared value (not a ref) so the gesture callbacks may hold it; true while a card is leaving.
  const busy = useSharedValue(false);

  const remaining = cards.length - index;
  useEffect(() => {
    if (remaining === 2) onRunningLow?.();
  }, [remaining, onRunningLow]);

  const current = cards[index];
  const next = cards[index + 1];

  const advance = (direction: SwipeDirection) => {
    const card = cards[index];
    busy.value = false;
    x.value = 0;
    stamp.value = 0;
    setIndex((i) => i + 1);
    if (card) onSwipe(card, direction);
  };

  const fling = (direction: SwipeDirection) => {
    if (busy.value || !current) return;
    busy.value = true;
    const exit = direction === 'left' ? -520 : 520;
    if (direction === 'left') {
      void Haptics.selectionAsync();
      x.value = withTiming(exit, { duration: reduced ? 0 : 220 }, () => scheduleOnRN(advance, direction));
      return;
    }
    // Like: the block presses in (90 ms), the ink spreads (300 ms), then the card leaves.
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    stamp.value = withSequence(
      withTiming(1.18, { duration: reduced ? 0 : motion.stampPress }),
      withTiming(1, { duration: reduced ? 0 : motion.stampSpread }),
    );
    x.value = withSequence(
      withTiming(x.value, { duration: reduced ? 0 : 420 }),
      withTiming(exit, { duration: reduced ? 0 : 240 }, () => scheduleOnRN(advance, direction)),
    );
  };

  const pan = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .onUpdate((e) => {
      x.value = e.translationX;
    })
    .onEnd((e) => {
      if (e.translationX > THRESHOLD) scheduleOnRN(fling, 'right');
      else if (e.translationX < -THRESHOLD) scheduleOnRN(fling, 'left');
      else x.value = withSpring(0, { damping: 18, stiffness: 220 });
    });

  const cardStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: x.value }, { rotate: `${interpolate(x.value, [-300, 0, 300], [-9, 0, 9])}deg` }],
  }));
  const stampStyle = useAnimatedStyle(() => ({
    opacity: stamp.value > 0 ? 1 : interpolate(x.value, [40, THRESHOLD], [0, 0.85], 'clamp'),
    transform: [{ scale: stamp.value > 0 ? stamp.value : 1 }, { rotate: '-12deg' }],
  }));
  const nextStyle = useAnimatedStyle(() => ({
    transform: [{ scale: interpolate(Math.abs(x.value), [0, 300], [0.95, 1], 'clamp') }],
  }));

  if (!current) {
    return (
      <View style={styles.empty}>
        <Text variant="headline" align="center">
          {emptyLabel}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.stack}>
        {next ? (
          <Animated.View style={[styles.layer, nextStyle]} pointerEvents="none">
            <ProductSwipeCard card={next} imageHeight={360} />
          </Animated.View>
        ) : null}
        <GestureDetector gesture={pan}>
          <Animated.View style={[styles.layer, cardStyle]}>
            <PressableScale
              scaleTo={0.99}
              onPress={() => onOpen(current)}
              accessibilityLabel={`${current.title}. Opens details`}
              accessibilityActions={[{ name: 'like', label: 'Like' }, { name: 'skip', label: 'Skip' }]}
              onAccessibilityAction={(e) => fling(e.nativeEvent.actionName === 'like' ? 'right' : 'left')}
            >
              <ProductSwipeCard card={current} imageHeight={360} />
            </PressableScale>
            <Animated.View style={[styles.stamp, stampStyle]} pointerEvents="none">
              <Stamp size={124} color={colors.onShell} ground="transparent" />
            </Animated.View>
          </Animated.View>
        </GestureDetector>
      </View>
      <View style={styles.controls}>
        <IconButton icon="close" label="Skip" size={64} onPress={() => fling('left')} testID="deck-skip" />
        <IconButton icon="arrowRight" label="Open details" size={52} variant="shell" onPress={() => onOpen(current)} />
        <IconButton icon="heart" label="Like" size={72} variant="action" onPress={() => fling('right')} testID="deck-like" />
      </View>
      <Text variant="caption" tone="secondary" align="center">
        {remaining} {remaining === 1 ? 'pick' : 'picks'} left
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 18 },
  stack: { minHeight: 520 },
  layer: { position: 'absolute', left: 0, right: 0, top: 0 },
  stamp: { position: 'absolute', right: 18, top: 220 },
  controls: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 24 },
  empty: { paddingVertical: 80, paddingHorizontal: 24 },
});
