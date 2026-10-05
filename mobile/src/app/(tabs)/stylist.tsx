import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useStylist } from '@/stylist';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';
import { AskField } from '@/ui/molecules/AskField';

/** The stylist tab: pick up where you left off, or start fresh. */
export default function StylistTab() {
  const { colors } = useTheme();
  const session = useStylist((s) => s.session);
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);

  const go = async (text: string) => {
    const id = await start('search', text);
    if (id) router.push(`/session/${id}`);
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <View style={styles.body}>
        <Text variant="display" accessibilityRole="header">
          Your stylist
        </Text>
        <Text variant="body" tone="secondary">
          Say what you need in your own words, or tap your way there from Home.
        </Text>
        <AskField surface="ground" placeholder="black jeans for college under ₹1,500" disabled={phase !== 'idle'} onSubmit={(t) => void go(t)} />
        {session && session.status !== 'ended' ? (
          <Button label="Continue your last session" variant="tonal" icon="arrowRight" iconPosition="end" onPress={() => router.push(`/session/${session.session_id}`)} />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  body: { padding: space.screen, gap: space.md },
});
