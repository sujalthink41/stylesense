import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '@/design/theme';
import { palette, radius } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';

/** Each occasion owns one dye, so the home screen reads as printed cloth, not icon tiles. */
export type Dye = 'madder' | 'turmeric' | 'indigo' | 'cotton';

const dyes: Record<Dye, { bg: string; title: string; sub: string; motif?: string }> = {
  madder: { bg: palette.madder, title: palette.white, sub: palette.madderTint, motif: '#C9483F' },
  turmeric: { bg: palette.turmeric, title: palette.ink, sub: palette.turmericInk },
  indigo: { bg: palette.indigo, title: palette.white, sub: palette.indigoMist, motif: palette.indigo700 },
  cotton: { bg: palette.white, title: palette.ink, sub: palette.ink600 },
};

export interface OccasionTileProps {
  title: string;
  subtitle: string;
  dye: Dye;
  onPress(): void;
  hero?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export function OccasionTile({ title, subtitle, dye, onPress, hero = false, style, testID }: OccasionTileProps) {
  const { elevation } = useTheme();
  const d = dyes[dye];
  return (
    <PressableScale
      testID={testID}
      onPress={onPress}
      accessibilityLabel={`${title}. ${subtitle}`}
      style={[styles.tile, { backgroundColor: d.bg }, dye === 'cotton' && elevation(2), style]}
    >
      {hero && d.motif ? (
        <View style={styles.motif} pointerEvents="none">
          <Buti size={150} color={d.motif} />
        </View>
      ) : null}
      <Text variant="caption" style={{ color: d.sub, fontSize: 13 }}>
        {subtitle}
      </Text>
      <Text variant="display" style={{ color: d.title, fontSize: hero ? 32 : 25, lineHeight: hero ? 32 : 26 }}>
        {title}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  tile: {
    borderRadius: radius.lg,
    padding: 16,
    justifyContent: 'space-between',
    overflow: 'hidden',
    minHeight: 112,
  },
  motif: { position: 'absolute', right: -40, bottom: -40 },
});
