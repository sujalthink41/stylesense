import * as Haptics from 'expo-haptics';
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withSpring, withTiming } from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';

export interface SaveHeartProps {
  saved: boolean;
  onToggle(): void;
  disabled?: boolean;
  size?: number;
}

/** Save to the wishlist: madder when saved, with a small pop and a tap of haptics. */
export function SaveHeart({ saved, onToggle, disabled, size = 48 }: SaveHeartProps) {
  const { colors, elevation } = useTheme();
  const reduced = useReducedMotion();
  const pop = useSharedValue(1);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: pop.value }] }));
  return (
    <PressableScale
      testID="save-heart"
      accessibilityRole="button"
      accessibilityLabel={saved ? 'Remove from wishlist' : 'Save to wishlist'}
      accessibilityState={{ selected: saved, disabled }}
      disabled={disabled}
      scaleTo={0.9}
      onPress={() => {
        if (!saved) {
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          if (!reduced) pop.set(withSequence(withTiming(1.25, { duration: 90 }), withSpring(1, { damping: 9 })));
        } else void Haptics.selectionAsync();
        onToggle();
      }}
      style={[
        { width: size, height: size, borderRadius: size, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.raised },
        elevation(2),
        disabled && { opacity: 0.5 },
      ]}
    >
      <Animated.View style={style}>
        <Icon name={saved ? 'heart' : 'heartOutline'} size={Math.round(size * 0.48)} color={saved ? colors.action : colors.text} strokeWidth={2} />
      </Animated.View>
    </PressableScale>
  );
}
