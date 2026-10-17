import type { ReactNode } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import Animated, { FadeInDown, FadeInRight, LinearTransition, ReduceMotion, ZoomIn } from 'react-native-reanimated';

/**
 * Entrance choreography: things rise into place one after another (70 ms apart), on a soft
 * spring. Every preset follows the system Reduce Motion setting.
 */
export const enter = {
  rise: (index = 0) =>
    FadeInDown.delay(Math.min(index, 8) * 70)
      .springify()
      .damping(18)
      .stiffness(160)
      .reduceMotion(ReduceMotion.System),
  slide: (index = 0) =>
    FadeInRight.delay(Math.min(index, 8) * 60)
      .springify()
      .damping(18)
      .reduceMotion(ReduceMotion.System),
  pop: () => ZoomIn.springify().damping(12).stiffness(260).reduceMotion(ReduceMotion.System),
};

export const layout = LinearTransition.springify().damping(20).reduceMotion(ReduceMotion.System);

export function Rise({ index = 0, children, style }: { index?: number; children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return (
    <Animated.View entering={enter.rise(index)} style={style}>
      {children}
    </Animated.View>
  );
}
