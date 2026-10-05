import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { Badge } from '@/ui/atoms/Badge';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';

export interface StoreOfferRowProps {
  storeName: string;
  pricePaise: number;
  inStock: boolean;
  isBest: boolean;
  onBuy(): void;
  first?: boolean;
}

/** One store's price for the exact item. Best price sits on turmeric; sold out is stamped. */
export function StoreOfferRow({ storeName, pricePaise, inStock, isBest, onBuy, first }: StoreOfferRowProps) {
  const { colors } = useTheme();
  const initials = storeName.slice(0, 2);
  return (
    <PressableScale
      onPress={onBuy}
      disabled={!inStock}
      scaleTo={0.99}
      accessibilityLabel={`${storeName}, ${inStock ? formatRupees(pricePaise) : 'sold out'}${isBest ? ', best price' : ''}`}
      accessibilityHint={inStock ? `Opens ${storeName} to buy` : undefined}
      style={[
        styles.row,
        { backgroundColor: isBest ? colors.bestPriceWash : colors.raised },
        !first && { borderTopWidth: 1, borderTopColor: colors.hairline },
      ]}
    >
      <View style={[styles.logo, { backgroundColor: isBest ? colors.raised : colors.ground }]}>
        <Text variant="label" tone={inStock ? 'onTonal' : 'disabled'} style={{ fontFamily: 'AnekLatin-Bold' }}>
          {initials}
        </Text>
      </View>
      <View style={styles.middle}>
        <Text variant="bodyStrong" tone={inStock ? 'default' : 'secondary'}>
          {storeName}
        </Text>
        <Text variant="bodySmall" tone="secondary">
          {inStock ? 'In stock' : `Last seen at ${formatRupees(pricePaise)}`}
        </Text>
      </View>
      {inStock ? (
        <View style={styles.end}>
          <Price paise={pricePaise} size={isBest ? 'md' : 'sm'} showDiscount={false} />
          {isBest ? <Badge kind="bestPrice" label="Best price" /> : null}
        </View>
      ) : (
        <Badge kind="soldOut" label="Sold out" />
      )}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, minHeight: 76 },
  logo: { width: 44, height: 44, borderRadius: radius.md - 2, alignItems: 'center', justifyContent: 'center' },
  middle: { flex: 1, gap: 2 },
  end: { alignItems: 'flex-end', gap: 4 },
});
