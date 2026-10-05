import { TabList, TabSlot, TabTrigger, Tabs, type TabTriggerSlotProps } from 'expo-router/ui';
import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { Icon, type IconName } from '@/ui/atoms/Icon';
import { Text } from '@/ui/atoms/Text';

/** Four destinations, Material 3 navigation bar in our colours (indicator pill when active). */
export default function TabsLayout() {
  const { colors, elevation } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Tabs>
      <TabSlot />
      <TabList
        style={[
          styles.bar,
          { backgroundColor: colors.raised, paddingBottom: Math.max(insets.bottom, 10) },
          elevation(2),
        ]}
      >
        <TabTrigger name="home" href="/" asChild>
          <TabButton icon="home" label="Home" />
        </TabTrigger>
        <TabTrigger name="stylist" href="/stylist" asChild>
          <TabButton icon="stylist" label="Stylist" />
        </TabTrigger>
        <TabTrigger name="saved" href="/saved" asChild>
          <TabButton icon="saved" label="Saved" />
        </TabTrigger>
        <TabTrigger name="me" href="/me" asChild>
          <TabButton icon="me" label="Me" />
        </TabTrigger>
      </TabList>
    </Tabs>
  );
}

type TabButtonProps = TabTriggerSlotProps & { icon: IconName; label: string };

function TabButton({ icon, label, isFocused, ...props }: TabButtonProps) {
  const { colors } = useTheme();
  const focus = useSharedValue(isFocused ? 1 : 0);
  useEffect(() => {
    focus.set(withSpring(isFocused ? 1 : 0, { damping: 15, stiffness: 220 }));
  }, [isFocused, focus]);
  // The indicator pill grows out from the icon (Material 3), the icon lifts a touch.
  const pill = useAnimatedStyle(() => ({ opacity: focus.value, transform: [{ scaleX: 0.4 + focus.value * 0.6 }] }));
  const glyph = useAnimatedStyle(() => ({ transform: [{ translateY: -focus.value * 1.5 }, { scale: 1 + focus.value * 0.06 }] }));
  return (
    <Pressable
      {...props}
      accessibilityRole="tab"
      accessibilityState={{ selected: !!isFocused }}
      accessibilityLabel={label}
      style={styles.tab}
    >
      <View style={styles.indicator}>
        <Animated.View style={[StyleSheet.absoluteFill, styles.pill, { backgroundColor: colors.tonal }, pill]} />
        <Animated.View style={glyph}>
          <Icon name={icon} size={22} color={isFocused ? colors.onTonal : colors.textSecondary} strokeWidth={isFocused ? 2 : 1.75} />
        </Animated.View>
      </View>
      <Text variant="caption" tone={isFocused ? 'onTonal' : 'secondary'} style={isFocused ? { fontFamily: 'AnekLatin-Bold' } : undefined}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', paddingTop: 10, paddingHorizontal: 8 },
  tab: { flex: 1, alignItems: 'center', gap: 4, minHeight: 56 },
  indicator: { width: 64, height: 32, alignItems: 'center', justifyContent: 'center' },
  pill: { borderRadius: radius.pill },
});
