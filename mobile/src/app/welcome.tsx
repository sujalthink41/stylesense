import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useOnboarding } from '@/onboarding';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { dyes, type Dye } from '@/ui/molecules/OccasionTile';

const BLOCKS: { dye: Dye; petals: 6 | 8 }[] = [
  { dye: 'indigo', petals: 8 },
  { dye: 'turmeric', petals: 6 },
  { dye: 'madder', petals: 6 },
  { dye: 'cotton', petals: 8 },
];

/** Shown once, right after the first sign-in: learn their style before the first search. */
export default function WelcomeScreen() {
  const { colors } = useTheme();
  const outline = { borderWidth: 1, borderColor: colors.hairline };
  const firstName = useSession((s) => s.user?.display_name?.split(' ')[0]);
  const dismiss = useOnboarding((s) => s.dismiss);
  const start = useStylist((s) => s.start);
  const error = useStylist((s) => s.error);
  const [busy, setBusy] = useState(false);

  const begin = async () => {
    setBusy(true);
    const id = await start('onboarding');
    setBusy(false);
    if (id) await dismiss(id); // else the banner says why; they can retry or skip
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]}>
      <View style={styles.mosaic} accessible={false}>
        {BLOCKS.map((b, i) => (
          <View key={i} style={[styles.block, { backgroundColor: dyes[b.dye].bg }, b.dye === 'cotton' && outline]}>
            <Buti size={88} color={dyes[b.dye].motif} petals={b.petals} />
          </View>
        ))}
      </View>
      <View style={styles.copy}>
        <Text variant="caption" tone="secondary">
          {firstName ? `Welcome, ${firstName}` : 'Welcome'}
        </Text>
        <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 46, lineHeight: 46 }}>
          First, your style.
        </Text>
        <Text variant="body" tone="secondary">
          Tap the looks you love. Ten seconds, one screen, and every pick after that gets sharper. Everything else, just tell the stylist.
        </Text>
      </View>
      <View style={styles.actions}>
        {error ? <Banner tone="warning" text={friendlyMessage(error)} /> : null}
        <Button label="Find my Style DNA" variant="primary" size="lg" fullWidth loading={busy} onPress={() => void begin()} testID="welcome-start" />
        <Button label="Maybe later" variant="ghost" fullWidth disabled={busy} onPress={() => void dismiss()} testID="welcome-skip" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: space.screen, justifyContent: 'space-between' },
  mosaic: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: space.md },
  block: { width: '48.5%', aspectRatio: 1.15, borderRadius: radius.xl, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  copy: { gap: 12 },
  actions: { gap: 6, paddingBottom: space.md },
});
