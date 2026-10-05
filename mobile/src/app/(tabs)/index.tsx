import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  useAnimatedScrollHandler,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { SessionEntry, StyleProfileView } from '@/api/types';
import { api, useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { Chip } from '@/ui/atoms/Chip';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { AskField } from '@/ui/molecules/AskField';
import { Banner } from '@/ui/molecules/Banner';
import { OccasionTile } from '@/ui/molecules/OccasionTile';
import { enter, Rise } from '@/ui/motion';
import { ProductRail } from '@/ui/organisms/ProductRail';

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
  const client = useQueryClient();
  const user = useSession((s) => s.user);
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);
  const error = useStylist((s) => s.error);
  const firstName = user?.display_name?.split(' ')[0];
  const profile = useQuery({ queryKey: ['style-profile'], queryFn: () => api.get<StyleProfileView>('/v1/me/style-profile') });
  const fit = profile.data?.fit_preference;
  const gender = fit === 'men' || fit === 'women' ? fit : undefined;
  const who = gender === 'men' ? 'for him' : gender === 'women' ? 'for her' : 'for you';
  const [refreshing, setRefreshing] = useState(false);

  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });
  // The band drifts up at half speed and its words fade: depth without a heavy parallax.
  const bandContent = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(scrollY.value, [-100, 0, 220], [-30, 0, 70], 'clamp') }],
    opacity: interpolate(scrollY.value, [0, 200], [1, 0.25], 'clamp'),
  }));

  const go = async (entry: SessionEntry, value?: string) => {
    const id = await start(entry, value);
    if (id) router.push(`/session/${id}`);
  };
  const seeAll = (text: string) => () => void go('search', gender ? `${gender} ${text}` : text);

  const refresh = async () => {
    setRefreshing(true);
    await client.invalidateQueries({ queryKey: ['rail'] });
    setRefreshing(false);
  };

  return (
    <Animated.ScrollView
      onScroll={onScroll}
      scrollEventThrottle={16}
      style={{ backgroundColor: colors.ground }}
      contentContainerStyle={{ paddingBottom: space.xl }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} tintColor={colors.shell} />}
    >
      <View style={[styles.band, { backgroundColor: colors.shell, paddingTop: insets.top + space.md }]}>
        <TurningMotif scrollY={scrollY} />
        <Animated.View style={[{ gap: 16 }, bandContent]}>
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
          <LiveStrip />
        </Animated.View>
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
      </View>

      <View style={styles.rails}>
        <ProductRail kicker={`Live prices, ${who}`} title="Trending under ₹999" query={{ gender, maxPricePaise: 99_900 }} onSeeAll={seeAll('trending under 999')} />
        <Rise index={4} style={styles.pad}>
          <PhotoCard />
        </Rise>
        <ProductRail kicker="Kurtas, sets and more" title="The ethnic edit" query={{ gender, category: 'kurta' }} onSeeAll={seeAll('kurta')} />
        <ProductRail kicker="Fresh kicks" title="Sneaker drop" query={{ gender, category: 'sneakers' }} onSeeAll={seeAll('sneakers')} />
        <ProductRail kicker="Every fit, every wash" title="Denim days" query={{ gender, category: 'jeans' }} onSeeAll={seeAll('jeans')} />
        {!profile.data?.onboarding_done ? (
          <Rise index={6} style={styles.pad}>
            <DnaCard onPress={() => void go('onboarding')} />
          </Rise>
        ) : null}
      </View>
    </Animated.ScrollView>
  );
}

/** Proof the prices are live: a pulsing dot and the three stores we compare. */
function LiveStrip() {
  const pulse = useSharedValue(1);
  useEffect(() => {
    pulse.set(withRepeat(withSequence(withTiming(0.35, { duration: 700 }), withTiming(1, { duration: 700 })), -1));
  }, [pulse]);
  const dot = useAnimatedStyle(() => ({ opacity: pulse.value }));
  return (
    <View style={styles.live} accessible accessibilityLabel="Live prices from Amazon, Flipkart and Myntra">
      <Animated.View style={[styles.dot, dot]} />
      <Text variant="caption" tone="onShellMuted">
        Live prices
      </Text>
      {['Amazon', 'Flipkart', 'Myntra'].map((s) => (
        <View key={s} style={styles.storePill}>
          <Text variant="caption" tone="onShell" style={{ fontFamily: 'AnekLatin-SemiBold' }}>
            {s}
          </Text>
        </View>
      ))}
    </View>
  );
}

function PhotoCard() {
  const { colors } = useTheme();
  return (
    <PressableScale
      onPress={() => router.push('/photo')}
      accessibilityLabel="Shop from a photo. Snap a look, find it in every store."
      style={[styles.photo, { backgroundColor: colors.shell }]}
    >
      <View style={styles.photoMotif} pointerEvents="none">
        <Buti size={120} color={palette.indigo700} />
      </View>
      <View style={[styles.mark, { backgroundColor: palette.turmeric }]}>
        <Icon name="camera" size={26} color={palette.ink} strokeWidth={2} />
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text variant="bodyStrong" tone="onShell">
          Shop from a photo
        </Text>
        <Text variant="bodySmall" tone="onShellMuted">
          Snap a look or a screenshot. We find it in every store.
        </Text>
      </View>
      <Icon name="chevronRight" size={22} color={colors.onShell} strokeWidth={2} />
    </PressableScale>
  );
}

function DnaCard({ onPress }: { onPress(): void }) {
  const { colors } = useTheme();
  return (
    <PressableScale onPress={onPress} accessibilityLabel="Find your Style DNA. 30 seconds, taps only." style={[styles.dna, { backgroundColor: colors.tonal }]}>
      <View style={[styles.mark, { backgroundColor: colors.shell }]}>
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
  );
}

/** The band's buti turns slowly, and a little faster as you scroll. */
function TurningMotif({ scrollY }: { scrollY: SharedValue<number> }) {
  const turn = useSharedValue(0);
  useEffect(() => {
    turn.set(withRepeat(withTiming(1, { duration: 60_000, easing: Easing.linear }), -1));
  }, [turn]);
  const style = useAnimatedStyle(() => ({
    transform: [{ rotate: `${turn.value * 360 + scrollY.value * 0.4}deg` }, { scale: interpolate(scrollY.value, [-120, 0], [1.25, 1], 'clamp') }],
  }));
  return (
    <Animated.View style={[styles.motif, style]} pointerEvents="none">
      <Buti size={170} color={palette.indigo700} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  band: { paddingHorizontal: space.screen, paddingBottom: space.lg, borderBottomLeftRadius: radius.sheet, borderBottomRightRadius: radius.sheet, overflow: 'hidden' },
  motif: { position: 'absolute', right: -50, top: 30 },
  live: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#3DDC84' },
  storePill: { backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  body: { padding: space.screen, gap: 14 },
  rails: { gap: space.lg },
  pad: { paddingHorizontal: space.screen },
  tiles: { flexDirection: 'row', gap: 12, height: 236 },
  heroTile: { flex: 1 },
  tileColumn: { flex: 1, gap: 12 },
  smallTile: { flex: 1 },
  chips: { gap: 8, paddingRight: space.screen },
  photo: { borderRadius: radius.lg, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14, overflow: 'hidden' },
  photoMotif: { position: 'absolute', right: -24, top: -30 },
  dna: { borderRadius: radius.lg, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14 },
  mark: { width: 52, height: 52, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
});
