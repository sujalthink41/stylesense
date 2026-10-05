import { router } from 'expo-router';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { AskField } from '@/ui/molecules/AskField';
import { Banner } from '@/ui/molecules/Banner';
import { enter, Rise } from '@/ui/motion';

const PROMPTS = [
  'Black jeans for college under ₹1,500',
  'A kurta for a sangeet',
  'Linen shirts for Goa',
  'Office wear for a first job',
  'Sneakers that go with everything',
  'A saree for Diwali under ₹4,000',
];

/** Ask in your own words, start from a photo, or pick up where you left off. */
export default function StylistTab() {
  const { colors, elevation } = useTheme();
  const session = useStylist((s) => s.session);
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);
  const error = useStylist((s) => s.error);

  const go = async (text: string) => {
    const id = await start('search', text);
    if (id) router.push(`/session/${id}`);
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Rise index={0} style={{ gap: 8 }}>
          <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 44, lineHeight: 44 }}>
            Ask your{'\n'}stylist.
          </Text>
          <Text variant="body" tone="secondary">
            Say it like you would to a friend: the occasion, the budget, the vibe.
          </Text>
        </Rise>
        <Rise index={1}>
          <AskField surface="ground" placeholder="black jeans for college under ₹1,500" disabled={phase !== 'idle'} onSubmit={(t) => void go(t)} />
        </Rise>
        {error ? <Banner tone="warning" text={friendlyMessage(error)} /> : null}

        {session && session.status !== 'ended' ? (
          <Rise index={2}>
            <PressableScale
              onPress={() => router.push(`/session/${session.session_id}`)}
              accessibilityLabel="Continue your last session"
              style={[styles.resume, { backgroundColor: colors.shell }, elevation(2)]}
            >
              <View style={styles.resumeMotif} pointerEvents="none">
                <Buti size={110} color={palette.indigo700} />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text variant="caption" tone="onShellMuted">
                  Pick up where you left off
                </Text>
                <Text variant="bodyStrong" tone="onShell">
                  Continue your last session
                </Text>
              </View>
              <Icon name="arrowRight" size={22} color={palette.turmeric} strokeWidth={2.2} />
            </PressableScale>
          </Rise>
        ) : null}

        <Rise index={3}>
          <PressableScale
            onPress={() => router.push('/photo')}
            accessibilityLabel="Shop from a photo"
            style={[styles.photo, { backgroundColor: colors.raised }, elevation(1)]}
          >
            <View style={[styles.iconBlock, { backgroundColor: palette.turmeric }]}>
              <Icon name="camera" size={24} color={palette.ink} strokeWidth={2} />
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text variant="bodyStrong">Shop from a photo</Text>
              <Text variant="bodySmall" tone="secondary">
                A screenshot, an outfit, a shop window
              </Text>
            </View>
            <Icon name="chevronRight" size={20} color={colors.textSecondary} />
          </PressableScale>
        </Rise>

        <Rise index={4}>
          <Text variant="label" tone="secondary">
            Try asking
          </Text>
        </Rise>
        <View style={styles.prompts}>
          {PROMPTS.map((p, i) => (
            <Animated.View key={p} entering={enter.rise(i + 5)}>
              <PressableScale
                disabled={phase !== 'idle'}
                onPress={() => void go(p)}
                accessibilityLabel={`Ask: ${p}`}
                style={[styles.prompt, { backgroundColor: colors.raised, borderColor: colors.hairline }]}
              >
                <Icon name="search" size={16} color={colors.textSecondary} />
                <Text variant="bodySmall" style={{ flexShrink: 1 }}>
                  {p}
                </Text>
              </PressableScale>
            </Animated.View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  body: { padding: space.screen, gap: space.md, paddingBottom: space.xl },
  resume: { borderRadius: radius.lg, padding: 18, flexDirection: 'row', alignItems: 'center', gap: 14, overflow: 'hidden' },
  resumeMotif: { position: 'absolute', right: -20, top: -24 },
  photo: { borderRadius: radius.lg, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 14 },
  iconBlock: { width: 48, height: 48, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  prompts: { gap: 8 },
  prompt: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 14, paddingHorizontal: 16, borderRadius: radius.md, borderWidth: 1 },
});
