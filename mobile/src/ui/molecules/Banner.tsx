import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { Icon } from '@/ui/atoms/Icon';
import { Text } from '@/ui/atoms/Text';

export type BannerTone = 'info' | 'success' | 'warning';

/** A one-line notice from the stylist ("Photo search is unavailable right now…"). */
export function Banner({ text, tone = 'info' }: { text: string; tone?: BannerTone }) {
  const { colors } = useTheme();
  const look = {
    info: { bg: colors.tonal, fg: colors.onTonal, tone: 'onTonal' as const },
    success: { bg: colors.bestPriceWash, fg: colors.onBestPriceWash, tone: 'onBestPriceWash' as const },
    warning: { bg: colors.raised, fg: colors.danger, tone: 'default' as const },
  }[tone];
  return (
    <View
      accessibilityRole="alert"
      style={[styles.banner, { backgroundColor: look.bg }, tone === 'warning' && { borderWidth: 1, borderColor: colors.danger }]}
    >
      <Icon name="info" size={20} color={look.fg} />
      <Text variant="bodySmall" tone={look.tone} style={styles.text}>
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: 14 },
  text: { flex: 1 },
});
