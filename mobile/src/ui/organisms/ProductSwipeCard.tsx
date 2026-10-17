import { Image } from 'expo-image';
import { memo } from 'react';
import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Badge } from '@/ui/atoms/Badge';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';

export interface ProductCardData {
  product_id: string;
  title: string;
  brand: string;
  image_url?: string | null;
  price_paise: number | null;
  best_store?: string | null;
  rating?: number | null;
  rating_count?: number;
  reasons?: string[];
}

const STORE_NAMES: Record<string, string> = { amazon: 'Amazon', flipkart: 'Flipkart', myntra: 'Myntra' };

export function storeName(code: string | null | undefined): string | null {
  if (!code) return null;
  return STORE_NAMES[code] ?? code.charAt(0).toUpperCase() + code.slice(1);
}

/** Taste reasons ("Your style: …") are dyed turmeric so you can tell what came from you. */
export function ReasonChips({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return (
    <View style={styles.reasons}>
      {reasons.slice(0, 3).map((r) => (
        <Badge key={r} kind={r.startsWith('Your style') ? 'taste' : 'neutral'} label={r} />
      ))}
    </View>
  );
}

/** Photo first, price at display scale, three reasons. */
// Memoised: while one card is dragged, the card underneath must not re-render.
export const ProductSwipeCard = memo(function ProductSwipeCard({ card, imageHeight = 400 }: { card: ProductCardData; imageHeight?: number }) {
  const { colors, elevation } = useTheme();
  const best = storeName(card.best_store);
  return (
    <View style={[styles.card, { backgroundColor: colors.raised }, elevation(3)]}>
      <View style={[styles.photo, { height: imageHeight, backgroundColor: palette.indigo700 }]}>
        {card.image_url ? (
          <Image
            source={{ uri: card.image_url }}
            recyclingKey={card.product_id}
            cachePolicy="memory-disk"
            style={StyleSheet.absoluteFill}
            contentFit="cover"
            transition={120}
            accessibilityLabel={card.title}
          />
        ) : null}
        {best ? (
          <View style={styles.bestTag}>
            <Badge kind="bestPrice" label={`Best on ${best}`} />
          </View>
        ) : null}
      </View>
      <View style={styles.body}>
        <View style={styles.titleRow}>
          <View style={styles.titles}>
            <Text variant="bodySmall" tone="secondary" numberOfLines={1}>
              {card.brand}
            </Text>
            <Text variant="title" numberOfLines={2}>
              {card.title}
            </Text>
          </View>
          <Price paise={card.price_paise} size="lg" store={storeName(card.best_store)} />
        </View>
        <ReasonChips reasons={card.reasons ?? []} />
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  card: { borderRadius: radius.xl, overflow: 'hidden' },
  photo: { overflow: 'hidden' },
  bestTag: { position: 'absolute', left: 14, top: 14 },
  body: { padding: 18, paddingTop: 16, gap: 12 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  titles: { flex: 1, gap: 2 },
  reasons: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
});
