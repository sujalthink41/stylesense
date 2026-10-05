import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { Button } from '@/ui/atoms/Button';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';

export interface BuyBarProps {
  storeName: string;
  pricePaise: number;
  /** Several stores compared: say this is the lowest. */
  isBest: boolean;
  onBuy(): void;
}

/** Docked under a product: the one action that matters, at the best price we found. */
export function BuyBar({ storeName, pricePaise, isBest, onBuy }: BuyBarProps) {
  const { colors, elevation } = useTheme();
  return (
    <View style={[styles.bar, { backgroundColor: colors.raised, borderTopColor: colors.hairline }, elevation(3)]}>
      <View style={styles.price}>
        <Text variant="caption" tone="secondary">
          {isBest ? 'Best price' : 'Price'} · {storeName}
        </Text>
        <Price paise={pricePaise} size="md" showDiscount={false} />
      </View>
      <Button
        label={`Buy on ${storeName}`}
        variant="action"
        icon="arrowUpRight"
        iconPosition="end"
        onPress={onBuy}
        testID="buy-best"
        accessibilityHint={`Opens ${storeName} to buy`}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: space.screen,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  price: { flex: 1, gap: 2 },
});
