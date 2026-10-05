import { useQuery } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as Linking from 'expo-linking';
import { router, useLocalSearchParams } from 'expo-router';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_URL } from '@/api/config';
import { friendlyMessage } from '@/api/errors';
import type { ProductSummary } from '@/api/types';
import { api } from '@/auth/session';
import { useWishlist } from '@/boards/wishlist';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { shareLink } from '@/lib/share';
import { BackButton } from '@/ui/atoms/BackButton';
import { Button } from '@/ui/atoms/Button';
import { IconButton } from '@/ui/atoms/IconButton';
import { Banner } from '@/ui/molecules/Banner';
import { BuyBar } from '@/ui/molecules/BuyBar';
import { SaveHeart } from '@/ui/molecules/SaveHeart';
import { enter, Rise } from '@/ui/motion';
import { ProductCarousel, StoreComparison, type OfferData } from '@/ui/organisms/Panels';
import { ProductDetailView } from '@/ui/organisms/ProductDetailView';
import { Skeleton } from '@/ui/organisms/Skeleton';

interface Offer {
  id: string;
  store_name: string;
  price_paise: number | null;
  in_stock: boolean;
  is_best: boolean;
  buy_path: string;
}
interface Product extends ProductSummary {
  images: string[];
  colors: string[];
  sizes_available: string[];
  attributes: Record<string, string>;
  offers: Offer[];
}

/** A product outside a stylist session: from a board, a share, or "similar". */
export default function ProductScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const product = useQuery({ queryKey: ['product', id], queryFn: () => api.get<Product>(`/v1/products/${id}`) });
  const similar = useQuery({
    queryKey: ['similar', id],
    queryFn: () => api.get<ProductSummary[]>(`/v1/products/${id}/similar?limit=10`),
    enabled: product.isSuccess,
  });
  const { ready, isSaved, toggle } = useWishlist();
  const p = product.data;
  const offers: OfferData[] = (p?.offers ?? []).map((o) => ({ ...o, offer_id: o.id }));
  const inStock = offers.filter((o) => o.in_stock);
  const priced = inStock.filter((o) => o.price_paise != null);
  const best =
    priced.find((o) => o.is_best) ?? [...priced].sort((a, b) => (a.price_paise ?? 0) - (b.price_paise ?? 0))[0] ?? inStock[0];
  const open = (path: string) => void Linking.openURL(`${API_URL}${path}?src=product`);

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <BackButton />
        <View style={{ flex: 1 }} />
        {p ? (
          <IconButton
            icon="share"
            label="Share this product"
            size={44}
            onPress={() => void shareLink({ kind: 'product', productId: p.id }, `${p.title} on StyleSense`).catch(() => undefined)}
          />
        ) : null}
      </View>
      {product.error ? (
        <View style={styles.pad}>
          <Banner tone="warning" text={friendlyMessage(product.error)} />
        </View>
      ) : !p ? (
        <View style={styles.pad}>
          <Skeleton shape="comparison" />
        </View>
      ) : (
        <>
          <ScrollView contentContainerStyle={styles.content}>
            <Animated.View entering={enter.rise(0)}>
              <ProductDetailView
                detail={{
                  title: p.title,
                  brand: p.brand,
                  images: p.images.length ? p.images : p.primary_image_url ? [p.primary_image_url] : [],
                  price_paise: p.min_price_paise,
                  rating: p.rating,
                  rating_count: p.rating_count,
                  colors: p.colors,
                  sizes: p.sizes_available,
                  facts: Object.values(p.attributes).slice(0, 6),
                }}
                accessory={
                  <SaveHeart
                    saved={isSaved(p.id)}
                    disabled={!ready}
                    onToggle={() =>
                      void toggle(p.id).then((ok) => {
                        if (!ok) void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
                      })
                    }
                  />
                }
              />
            </Animated.View>
            <Rise index={1}>
              <Button
                label="Try it on"
                variant="tonal"
                icon="camera"
                fullWidth
                onPress={() => router.push({ pathname: '/tryon/[productId]', params: { productId: p.id, title: p.title } })}
              />
            </Rise>
            {offers.length ? (
              <Rise index={2}>
                <StoreComparison offers={offers} onBuy={(o) => open(o.buy_path)} />
              </Rise>
            ) : null}
            {similar.data?.length ? (
              <Rise index={3}>
                <ProductCarousel
                  title="You might also like"
                  items={similar.data.map((s) => ({
                    product_id: s.id,
                    title: s.title,
                    brand: s.brand,
                    image_url: s.primary_image_url,
                    price_paise: s.min_price_paise,
                    best_store: s.best_store,
                  }))}
                  onOpen={(item) => router.push(`/product/${item.product_id}`)}
                />
              </Rise>
            ) : null}
          </ScrollView>
          {best ? (
            <BuyBar storeName={best.store_name} pricePaise={best.price_paise} isBest={priced.length > 1} onBuy={() => open(best.buy_path)} />
          ) : null}
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: space.screen, paddingVertical: space.xs },
  pad: { padding: space.screen },
  content: { padding: space.screen, gap: space.lg, paddingBottom: space.xl },
});
