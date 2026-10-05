import { Image } from 'expo-image';
import { useState } from 'react';
import { ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';

import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Badge } from '@/ui/atoms/Badge';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';

export interface DetailData {
  title: string;
  brand: string;
  images?: string[];
  price_paise: number | null;
  mrp_paise?: number | null;
  rating?: number | null;
  rating_count?: number;
  colors?: string[];
  sizes?: string[];
  facts?: string[];
}

/** The full product: swipeable photos, the price at its largest, facts as chips. */
export function ProductDetailView({ detail }: { detail: DetailData }) {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const [page, setPage] = useState(0);
  const photoWidth = width - 40;
  const images = detail.images?.length ? detail.images : [];
  return (
    <View style={styles.wrap}>
      <View style={[styles.photos, { backgroundColor: palette.indigo700 }]}>
        <ScrollView
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          onMomentumScrollEnd={(e) => setPage(Math.round(e.nativeEvent.contentOffset.x / photoWidth))}
        >
          {images.map((uri, i) => (
            <Image
              key={uri}
              source={{ uri }}
              style={{ width: photoWidth, height: photoWidth * 1.2 }}
              contentFit="cover"
              accessibilityLabel={`${detail.title}, photo ${i + 1} of ${images.length}`}
            />
          ))}
        </ScrollView>
        {images.length > 1 ? (
          <View style={styles.dots}>
            {images.map((uri, i) => (
              <View key={uri} style={[styles.dot, { width: i === page ? 18 : 8, opacity: i === page ? 1 : 0.5 }]} />
            ))}
          </View>
        ) : null}
      </View>
      <View style={styles.head}>
        <Text variant="bodySmall" tone="secondary">
          {detail.brand}
        </Text>
        <Text variant="headline" accessibilityRole="header">
          {detail.title}
        </Text>
      </View>
      <Price paise={detail.price_paise} size="xl" mrpPaise={detail.mrp_paise} />
      <View style={styles.chips}>
        {detail.rating != null ? <Badge kind="rating" label={`${detail.rating.toFixed(1)} · ${detail.rating_count ?? 0}`} /> : null}
        {(detail.facts ?? []).slice(0, 6).map((f) => (
          <Badge key={f} kind="neutral" label={f} />
        ))}
      </View>
      {detail.sizes?.length ? (
        <View style={styles.sizes}>
          <Text variant="label">Sizes</Text>
          <View style={styles.chips}>
            {detail.sizes.map((s) => (
              <View key={s} style={[styles.size, { backgroundColor: colors.raised, borderColor: colors.hairline }]}>
                <Text variant="label">{s}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 14 },
  photos: { borderRadius: radius.xl, overflow: 'hidden' },
  dots: { position: 'absolute', bottom: 14, right: 14, flexDirection: 'row', gap: 6 },
  dot: { height: 4, borderRadius: 4, backgroundColor: palette.white },
  head: { gap: 2 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  sizes: { gap: 8 },
  size: { minWidth: 48, height: 40, paddingHorizontal: 12, borderRadius: radius.md - 4, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
});
