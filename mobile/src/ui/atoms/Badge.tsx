import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';

import { Icon } from './Icon';
import { Text } from './Text';

export type BadgeKind = 'bestPrice' | 'inStock' | 'soldOut' | 'rating' | 'neutral' | 'taste';

export interface BadgeProps {
  kind: BadgeKind;
  label: string;
}

/** Small status marks. Sold out is stamped (rotated, outlined), never hidden. */
export function Badge({ kind, label }: BadgeProps) {
  const { colors, elevation } = useTheme();
  switch (kind) {
    case 'bestPrice':
      return (
        <View style={[styles.base, { backgroundColor: colors.bestPrice }]}>
          <Text variant="caption" tone="onBestPrice" style={styles.strong}>{label}</Text>
        </View>
      );
    case 'inStock':
      return (
        <View style={[styles.base, { backgroundColor: colors.tonal }]}>
          <View style={[styles.dot, { backgroundColor: colors.saving }]} />
          <Text variant="caption" tone="onTonal">{label}</Text>
        </View>
      );
    case 'soldOut':
      return (
        <View style={[styles.base, styles.stamped, { borderColor: colors.danger }]}>
          <Text variant="caption" tone="action" style={styles.stampText}>{label.toUpperCase()}</Text>
        </View>
      );
    case 'rating':
      return (
        <View style={[styles.base, { backgroundColor: colors.raised }, elevation(1)]}>
          <Icon name="star" size={13} color={colors.bestPrice} />
          <Text variant="caption" style={styles.strong}>{label}</Text>
        </View>
      );
    case 'taste':
      return (
        <View style={[styles.pill, { backgroundColor: colors.bestPriceWash }]}>
          <Text variant="caption" tone="onBestPriceWash" style={styles.strong}>{label}</Text>
        </View>
      );
    case 'neutral':
      return (
        <View style={[styles.pill, { backgroundColor: colors.tonal }]}>
          <Text variant="caption" tone="onTonal" style={styles.strong}>{label}</Text>
        </View>
      );
  }
}

const styles = StyleSheet.create({
  base: { height: 28, paddingHorizontal: 10, borderRadius: radius.sm, flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start' },
  pill: { height: 28, paddingHorizontal: 11, borderRadius: radius.pill, flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start' },
  dot: { width: 8, height: 8, borderRadius: 8 },
  stamped: { borderWidth: 1.5, transform: [{ rotate: '-4deg' }] },
  stampText: { fontFamily: 'AnekLatin-Bold', letterSpacing: 1 },
  strong: { fontFamily: 'AnekLatin-Bold', fontSize: 13 },
});
