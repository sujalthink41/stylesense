import { Image } from 'expo-image';
import { StyleSheet, View } from 'react-native';

import type { StyleOptions, StyleProfileView } from '@/api/types';
import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Badge } from '@/ui/atoms/Badge';
import { Buti } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';

const SHOPPING_FOR: Record<string, string> = { men: 'Men', women: 'Women', unisex: 'Unisex', any: 'Everyone' };

export interface StyleDnaCardProps {
  profile: StyleProfileView | undefined;
  options: StyleOptions | undefined;
  busy?: boolean;
  onStart(): void;
}

/** What the stylist knows about you: chosen looks, sizes, and what your swipes taught it. */
export function StyleDnaCard({ profile, options, busy, onStart }: StyleDnaCardProps) {
  const { colors, elevation } = useTheme();
  const done = profile?.onboarding_done ?? false;
  const looks = (profile?.styles ?? []).map((id) => options?.styles.find((s) => s.id === id) ?? { id, label: id, image_url: '' });
  const sizes = profile
    ? [
        ['Top', profile.sizes.top],
        ['Bottom', profile.sizes.bottom],
        ['Shoe', profile.sizes.shoe],
      ].filter((p): p is [string, string] => !!p[1])
    : [];

  return (
    <View style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]} testID="style-dna">
      <View style={styles.head}>
        <View style={[styles.mark, { backgroundColor: colors.shell }]}>
          <Buti size={30} petals={6} color={palette.turmeric} />
        </View>
        <View style={{ flex: 1 }}>
          <Text variant="headline" accessibilityRole="header">
            Your Style DNA
          </Text>
          <Text variant="bodySmall" tone="secondary">
            {done
              ? `${profile?.swipe_count ?? 0} ${profile?.swipe_count === 1 ? 'swipe has' : 'swipes have'} taught your stylist so far`
              : 'One screen of looks to tap. Every pick after gets sharper.'}
          </Text>
        </View>
      </View>

      {looks.length ? (
        <View style={styles.looks}>
          {looks.map((l) => (
            <View key={l.id} style={styles.look} accessible accessibilityLabel={`Look you love: ${l.label}`}>
              <View style={[styles.lookImage, { backgroundColor: palette.indigo700 }]}>
                {l.image_url ? <Image source={{ uri: l.image_url }} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
              </View>
              <Text variant="caption" numberOfLines={1}>
                {l.label}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {done && (sizes.length || profile?.fit_preference) ? (
        <View style={styles.facts}>
          {profile?.fit_preference ? <Badge kind="neutral" label={`For ${SHOPPING_FOR[profile.fit_preference] ?? profile.fit_preference}`} /> : null}
          {sizes.map(([k, v]) => (
            <Badge key={k} kind="neutral" label={`${k} ${v}`} />
          ))}
        </View>
      ) : null}

      {profile?.top_tags.length ? (
        <View style={{ gap: 8 }}>
          <Text variant="label" tone="secondary">
            Learned from your swipes
          </Text>
          <View style={styles.facts}>
            {profile.top_tags.slice(0, 6).map((t) => (
              <Badge key={t} kind="taste" label={t} />
            ))}
          </View>
        </View>
      ) : null}

      <Button
        label={done ? 'Retake Style DNA' : 'Find my Style DNA'}
        variant={done ? 'tonal' : 'primary'}
        loading={busy}
        onPress={onStart}
        testID="style-dna-start"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, padding: 18, gap: 16 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  mark: { width: 48, height: 48, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  looks: { flexDirection: 'row', gap: 10 },
  look: { flex: 1, gap: 6, maxWidth: '32%' },
  lookImage: { aspectRatio: 0.8, borderRadius: radius.md, overflow: 'hidden' },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
});
