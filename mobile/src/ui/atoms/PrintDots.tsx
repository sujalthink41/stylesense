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

/** Three dye dots printing in sequence: the loading state that never moves the label. */
export function PrintDots({ color, size = 10 }: { color: string; size?: number }) {
  return (
    <View style={styles.row} accessibilityRole="progressbar" accessibilityLabel="Loading">
      {[0, 1, 2].map((i) => (
        <Dot key={i} index={i} color={color} size={size} />
      ))}
    </View>
  );
}

function Dot({ index, color, size }: { index: number; color: string; size: number }) {
  const reduced = useReducedMotion();
  const opacity = useSharedValue(reduced ? 0.7 : 0.25);
  useEffect(() => {
    if (reduced) return;
    opacity.value = withDelay(
      index * 160,
      withRepeat(withSequence(withTiming(1, { duration: 280 }), withTiming(0.25, { duration: 480 })), -1),
    );
  }, [index, opacity, reduced]);
  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <Animated.View style={[{ width: size, height: size, borderRadius: size, backgroundColor: color }, style]} />;
}

const styles = StyleSheet.create({ row: { flexDirection: 'row', gap: 8, alignItems: 'center' } });
