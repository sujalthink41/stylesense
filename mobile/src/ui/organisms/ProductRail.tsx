import { useQuery } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';

import type { ProductSummary } from '@/api/types';
import { api } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { Icon } from '@/ui/atoms/Icon';
import { Price } from '@/ui/atoms/Price';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { enter } from '@/ui/motion';

import { storeName } from './ProductSwipeCard';

export interface RailQuery {
  category?: string;
  gender?: 'men' | 'women';
  maxPricePaise?: number;
}

/** A shelf of real, priced products from the stores; tap one to open it. */
export function ProductRail({
  title,
  kicker,
  query,
  onSeeAll,
}: {
  title: string;
  kicker?: string;
  query: RailQuery;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  const params = new URLSearchParams({ limit: '12', min_price_paise: '1' }); // real prices only
  if (query.category) params.set('category', query.category);
  if (query.gender) params.set('gender', query.gender);
  if (query.maxPricePaise) params.set('max_price_paise', String(query.maxPricePaise));
  const products = useQuery({
    queryKey: ['rail', params.toString()],
    queryFn: () => api.get<{ items: ProductSummary[] }>(`/v1/products?${params.toString()}`),
    staleTime: 5 * 60_000,
  });
  const items = (products.data?.items ?? []).filter((p) => p.primary_image_url);
  if (products.isSuccess && items.length === 0) return null;

  return (
    <View style={styles.wrap}>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          {kicker ? (
            <Text variant="caption" tone="secondary">
              {kicker}
            </Text>
          ) : null}
          <Text variant="headline" accessibilityRole="header">
            {title}
          </Text>
        </View>
        {onSeeAll ? (
          <PressableScale onPress={onSeeAll} accessibilityLabel={`See all: ${title}`} style={styles.seeAll}>
            <Text variant="label" tone="onTonal">
              See all
            </Text>
            <Icon name="chevronRight" size={16} color={colors.onTonal} strokeWidth={2.4} />
          </PressableScale>
        ) : null}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rail} decelerationRate="fast" snapToInterval={TILE + GAP}>
        {products.isLoading
          ? [0, 1, 2].map((i) => <View key={i} style={[styles.tile, styles.ghost, { backgroundColor: colors.tonal }]} />)
          : items.map((p, i) => <Tile key={p.id} product={p} index={i} />)}
      </ScrollView>
    </View>
  );
}

const TILE = 156;
const GAP = 12;

function Tile({ product, index }: { product: ProductSummary; index: number }) {
  const { colors, elevation } = useTheme();
  const store = storeName(product.best_store);
  return (
    <Animated.View entering={enter.slide(index)}>
      <PressableScale
        onPress={() => router.push(`/product/${product.id}`)}
        scaleTo={0.96}
        accessibilityLabel={`${product.title}, ${store ?? ''}`}
        style={[styles.tile, { backgroundColor: colors.raised }, elevation(2)]}
      >
        <View style={[styles.photo, { backgroundColor: palette.indigo700 }]}>
          <Image source={{ uri: product.primary_image_url! }} style={StyleSheet.absoluteFill} contentFit="cover" transition={180} recyclingKey={product.id} />
          <LinearGradient colors={['transparent', 'rgba(15,22,51,0.65)']} style={styles.scrim} pointerEvents="none" />
          {store ? (
            <View style={styles.store}>
              <Text variant="caption" style={styles.storeText}>
                {store}
              </Text>
            </View>
          ) : null}
          {product.rating ? (
            <View style={styles.rating}>
              <Icon name="star" size={11} color={palette.turmeric} />
              <Text variant="caption" tone="onShell" style={{ fontFamily: 'AnekLatin-SemiBold' }}>
                {product.rating.toFixed(1)}
              </Text>
            </View>
          ) : null}
        </View>
        <View style={styles.meta}>
          <Text variant="caption" tone="secondary" numberOfLines={1}>
            {product.brand}
          </Text>
          <Text variant="bodySmall" numberOfLines={2} style={{ minHeight: 36 }}>
            {product.title}
          </Text>
          <Price paise={product.min_price_paise} size="sm" showDiscount={false} store={store} />
        </View>
      </PressableScale>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  head: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: space.screen },
  seeAll: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 6, paddingHorizontal: 10, borderRadius: radius.pill },
  rail: { gap: GAP, paddingHorizontal: space.screen, paddingBottom: 6 },
  tile: { width: TILE, borderRadius: radius.lg, overflow: 'hidden' },
  ghost: { height: 300 },
  photo: { aspectRatio: 0.78, justifyContent: 'flex-end' },
  scrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 60 },
  store: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(255,255,255,0.92)', borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  storeText: { color: palette.ink, fontFamily: 'AnekLatin-SemiBold' },
  rating: { flexDirection: 'row', alignItems: 'center', gap: 3, margin: 8 },
  meta: { padding: 10, gap: 3 },
});
