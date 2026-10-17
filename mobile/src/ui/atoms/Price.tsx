import { StyleSheet, Text as RNText, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { priceType, typeScale, type PriceSize } from '@/design/typography';
import { discountPercent, formatRupees, rupeeDigits } from '@/lib/money';

export interface PriceProps {
  paise: number | null | undefined;
  size?: PriceSize;
  mrpPaise?: number | null;
  /** Show "38% off" next to a struck MRP. */
  showDiscount?: boolean;
  tone?: 'default' | 'onShell';
  /** With no price: the store that lists it. We never estimate: "See price on Myntra". */
  store?: string | null;
}

/** Prices are display type: condensed, tabular, the ₹ set smaller and raised. */
export function Price({ paise, size = 'md', mrpPaise, showDiscount = true, tone = 'default', store }: PriceProps) {
  const { colors } = useTheme();
  const spec = priceType[size];
  const color = tone === 'onShell' ? colors.onShell : colors.text;
  if (paise == null && store) {
    return (
      <RNText
        style={[typeScale.bodyStrong, { color: tone === 'onShell' ? colors.onShell : colors.onTonal }]}
        accessibilityLabel={`Price on ${store}`}
      >
        See price on {store} →
      </RNText>
    );
  }
  if (paise == null) {
    return (
      <RNText style={[typeScale.bodySmall, { color: colors.textSecondary }]} accessibilityLabel="Price not available">
        Out of stock
      </RNText>
    );
  }
  const off = discountPercent(paise, mrpPaise);
  const spoken = `${formatRupees(paise)}${off ? `, was ${formatRupees(mrpPaise ?? 0)}, ${off}% off` : ''}`;
  return (
    <View style={styles.row} accessible accessibilityLabel={spoken}>
      <RNText
        maxFontSizeMultiplier={1.3}
        style={{ fontFamily: spec.fontFamily, fontSize: spec.fontSize, lineHeight: spec.lineHeight, color, fontVariant: ['tabular-nums'], letterSpacing: -0.4 }}
      >
        <RNText style={{ fontSize: spec.symbol, fontFamily: 'AnekLatin-SemiBold' }}>₹</RNText>
        {rupeeDigits(paise)}
      </RNText>
      {off > 0 && mrpPaise ? (
        <View style={styles.row}>
          <RNText maxFontSizeMultiplier={1.6} style={[typeScale.bodySmall, styles.struck, { color: colors.textDisabled }]}>
            {formatRupees(mrpPaise)}
          </RNText>
          {showDiscount ? (
            <RNText maxFontSizeMultiplier={1.6} style={[typeScale.bodyStrong, { color: colors.saving, fontSize: 15 }]}>
              {off}% off
            </RNText>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' },
  struck: { textDecorationLine: 'line-through' },
});
