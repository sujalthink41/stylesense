import { router } from 'expo-router';
import { useEffect } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { SessionEntry } from '@/api/types';
import { useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { Chip } from '@/ui/atoms/Chip';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { AskField } from '@/ui/molecules/AskField';
import { Banner } from '@/ui/molecules/Banner';
import { OccasionTile } from '@/ui/molecules/OccasionTile';
import { useStylist } from '@/stylist';
import { enter, Rise } from '@/ui/motion';

const MORE_OCCASIONS = ['Office', 'College', 'Date night', 'Travel', 'Summer', 'Sports'];

function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function HomeScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const user = useSession((s) => s.user);
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);
  const error = useStylist((s) => s.error);
  const firstName = user?.display_name?.split(' ')[0];

  const go = async (entry: SessionEntry, value?: string) => {
    const id = await start(entry, value);
    if (id) router.push(`/session/${id}`);
  };

  return (
    <ScrollView style={{ backgroundColor: colors.ground }} contentContainerStyle={{ paddingBottom: space.xl }}>
      <View style={[styles.band, { backgroundColor: colors.shell, paddingTop: insets.top + space.md }]}>
        <TurningMotif />
        <Text variant="bodySmall" tone="onShellMuted">
          {greeting()}
          {firstName ? `, ${firstName}` : ''}
        </Text>
        <Animated.View entering={enter.rise(0)}>
        <Text variant="display" tone="onShell" accessibilityRole="header" style={{ fontSize: 40, lineHeight: 40 }}>
          What are we{'\n'}dressing for?
        </Text>
        </Animated.View>
        <AskField
          placeholder="a kurta for a sangeet under ₹2,000"
          disabled={phase !== 'idle'}
          onSubmit={(text) => void go('search', text)}
          testID="home-ask"
        />
      </View>

      <View style={styles.body}>
        {error ? <Banner tone="warning" text={friendlyMessage(error)} /> : null}
        <Rise index={1}>
          <Text variant="headline" accessibilityRole="header">
            Pick an occasion
          </Text>
        </Rise>
        <Rise index={2} style={styles.tiles}>
          <OccasionTile hero dye="madder" title={'Wedding\nseason'} subtitle="Sangeet to reception" onPress={() => void go('occasion_tile', 'wedding')} style={styles.heroTile} testID="tile-wedding" />
          <View style={styles.tileColumn}>
            <OccasionTile dye="turmeric" title="Festive" subtitle="Diwali, Eid" onPress={() => void go('occasion_tile', 'festive')} style={styles.smallTile} />
            <OccasionTile dye="cotton" title="Party" subtitle="Friday night" onPress={() => void go('occasion_tile', 'party')} style={styles.smallTile} />
          </View>
        </Rise>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          {MORE_OCCASIONS.map((o, i) => (
            <Animated.View key={o} entering={enter.slide(i + 3)}>
              <Chip label={o} onPress={() => void go('occasion_tile', o.toLowerCase())} />
            </Animated.View>
          ))}
        </ScrollView>

        <Rise index={4}>
          <PressableScale
            onPress={() => router.push('/photo')}
            accessibilityLabel="Shop from a photo. Snap a look, find it in every store."
            style={[styles.photo, { backgroundColor: colors.shell }]}
          >
            <View style={styles.photoMotif} pointerEvents="none">
              <Buti size={120} color={palette.indigo700} />
            </View>
            <View style={[styles.dnaMark, { backgroundColor: palette.turmeric }]}>
              <Icon name="camera" size={26} color={palette.ink} strokeWidth={2} />
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text variant="bodyStrong" tone="onShell">
                Shop from a photo
              </Text>
              <Text variant="bodySmall" tone="onShellMuted">
                Snap a look. We find it in every store.
              </Text>
            </View>
            <Icon name="chevronRight" size={22} color={colors.onShell} strokeWidth={2} />
          </PressableScale>
        </Rise>

        <Rise index={5}>
        <PressableScale
          onPress={() => void go('onboarding')}
          accessibilityLabel="Find your Style DNA. 30 seconds, taps only."
          style={[styles.dna, { backgroundColor: colors.tonal }]}
        >
          <View style={[styles.dnaMark, { backgroundColor: colors.shell }]}>
            <Buti size={34} petals={6} color={palette.turmeric} />
          </View>
          <View style={{ flex: 1, gap: 2 }}>
            <Text variant="bodyStrong" tone="onTonal">
              Find your Style DNA
            </Text>
            <Text variant="bodySmall" tone="secondary">
              30 seconds, taps only. Your picks get sharper.
            </Text>
          </View>
          <Icon name="chevronRight" size={22} color={colors.onTonal} strokeWidth={2} />
        </PressableScale>
        </Rise>
      </View>
    </ScrollView>
  );
}

/** The band's buti turns, very slowly: alive, never distracting. */
function TurningMotif() {
  const turn = useSharedValue(0);
  useEffect(() => {
    turn.set(withRepeat(withTiming(1, { duration: 60_000, easing: Easing.linear }), -1));
  }, [turn]);
  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${turn.value * 360}deg` }] }));
  return (
    <Animated.View style={[styles.motif, style]} pointerEvents="none">
      <Buti size={170} color={palette.indigo700} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  photo: { borderRadius: radius.lg, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14, overflow: 'hidden' },
  photoMotif: { position: 'absolute', right: -24, top: -30 },
  band: { paddingHorizontal: space.screen, paddingBottom: space.lg, gap: 16, borderBottomLeftRadius: radius.sheet, borderBottomRightRadius: radius.sheet, overflow: 'hidden' },
  motif: { position: 'absolute', right: -50, top: 30 },
  body: { padding: space.screen, gap: 14 },
  tiles: { flexDirection: 'row', gap: 12, height: 236 },
  heroTile: { flex: 1 },
  tileColumn: { flex: 1, gap: 12 },
  smallTile: { flex: 1 },
  chips: { gap: 8, paddingRight: space.screen },
  dna: { borderRadius: radius.lg, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14 },
  dnaMark: { width: 52, height: 52, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
});
