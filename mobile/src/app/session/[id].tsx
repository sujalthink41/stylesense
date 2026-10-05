import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useMemo } from 'react';
import { BackHandler, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { useTheme } from '@/design/theme';
import { motion, space } from '@/design/tokens';
import { backAction } from '@/genui/navigation';
import { GenUIScreen, renderComponent } from '@/genui/Renderer';
import type { GenUIComponent, GenUIContext, UiEnvelope } from '@/genui/types';
import { useStylist } from '@/stylist';
import { Button } from '@/ui/atoms/Button';
import { IconButton } from '@/ui/atoms/IconButton';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { PrintRepeat } from '@/ui/molecules/PrintRepeat';

/** One stylist conversation, drawn entirely from server-sent components. */
export default function SessionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const session = useStylist((s) => s.session);
  const phase = useStylist((s) => s.phase);
  const error = useStylist((s) => s.error);
  const loading = useStylist((s) => s.loading);
  const open = useStylist((s) => s.open);
  const act = useStylist((s) => s.act);

  useEffect(() => {
    if (id) void open(id);
  }, [id, open]);

  const ui = session?.ui as UiEnvelope | undefined;
  const ctx = useMemo<GenUIContext | null>(
    () =>
      session
        ? { sessionId: session.session_id, turnId: session.turn_id, busy: phase !== 'idle', dispatch: (a) => void act(a) }
        : null,
    [session, phase, act],
  );

  // Android back steps back through the conversation while the server offers a way back.
  useFocusEffect(
    useCallback(() => {
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        const back = ui ? backAction(ui.components) : null;
        if (!back || phase !== 'idle') return phase !== 'idle'; // mid-turn: swallow, don't leave
        void act(back);
        return true;
      });
      return () => sub.remove();
    }, [ui, phase, act]),
  );

  const ended = session?.status === 'ended';
  const ready = session && ctx && ui && session.session_id === id;
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <IconButton icon="arrowLeft" label="Leave the stylist" size={44} onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} />
        <Text variant="bodySmall" tone="secondary" style={{ flex: 1 }} accessibilityLiveRegion="polite">
          {phase === 'acting' ? 'Thinking…' : ended ? 'All done' : 'Your stylist'}
        </Text>
      </View>
      {error ? (
        <View style={styles.notice}>
          <Banner tone="warning" text={friendlyMessage(error)} />
        </View>
      ) : null}
      {ready ? (
        loading ? (
          <Loading components={loading} ctx={ctx} />
        ) : (
          // Until the server says what's coming, the current screen stays, taps disabled (ctx.busy).
          <Animated.View key={ui.turn_id} entering={FadeIn.duration(motion.ui)} style={styles.screen}>
            <GenUIScreen
              envelope={ui}
              ctx={ctx}
              header={ended ? <Button label="Back to home" variant="primary" onPress={() => router.replace('/')} /> : undefined}
            />
          </Animated.View>
        )
      ) : (
        <View style={styles.pad}>
          <PrintRepeat label="Opening your stylist…" />
        </View>
      )}
    </SafeAreaView>
  );
}

function Loading({ components, ctx }: { components: GenUIComponent[]; ctx: GenUIContext }) {
  return (
    <Animated.View entering={FadeIn.duration(motion.press)} style={styles.screen}>
      <ScrollView contentContainerStyle={[styles.pad, { gap: space.lg }]} scrollEnabled={false}>
        {components.map((c) => (
          <View key={c.id}>{renderComponent(c, ctx)}</View>
        ))}
      </ScrollView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.screen, paddingVertical: space.xs },
  notice: { paddingHorizontal: space.screen },
  pad: { padding: space.screen },
});
