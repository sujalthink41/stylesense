import { BlurView } from 'expo-blur';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeOut, ReduceMotion } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';

import { SearchLoader } from './SearchLoader';

/** Covers the screen the moment a search starts, so a tap always visibly does something. */
export function LoadingOverlay({ visible, steps }: { visible: boolean; steps?: string[] }) {
  const { colors, scheme, elevation } = useTheme();
  const insets = useSafeAreaInsets();
  if (!visible) return null;
  return (
    <Animated.View
      entering={FadeIn.duration(160).reduceMotion(ReduceMotion.System)}
      exiting={FadeOut.duration(160).reduceMotion(ReduceMotion.System)}
      style={[StyleSheet.absoluteFill, styles.root]}
      pointerEvents="auto"
      accessibilityViewIsModal
    >
      <BlurView intensity={30} tint={scheme === 'dark' ? 'dark' : 'light'} style={StyleSheet.absoluteFill} />
      <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.ground, opacity: 0.6 }]} />
      <View style={[styles.sheet, { backgroundColor: colors.ground, marginTop: insets.top + space.xl }, elevation(3)]}>
        <SearchLoader steps={steps} />
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: { zIndex: 50, paddingHorizontal: space.screen },
  sheet: { borderRadius: radius.xl, padding: 20 },
});
