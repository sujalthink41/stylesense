import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { GenUIScreen } from '@/genui/Renderer';
import type { GenUIContext } from '@/genui/types';
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
  const open = useStylist((s) => s.open);
  const act = useStylist((s) => s.act);

  useEffect(() => {
    if (id) void open(id);
  }, [id, open]);

  const ctx = useMemo<GenUIContext | null>(
    () =>
      session
        ? { sessionId: session.session_id, turnId: session.turn_id, busy: phase !== 'idle', dispatch: (a) => void act(a) }
        : null,
    [session, phase, act],
  );

  const ended = session?.status === 'ended';
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <IconButton icon="arrowLeft" label="Back" size={44} onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} />
        <Text variant="bodySmall" tone="secondary" style={{ flex: 1 }}>
          {phase === 'acting' ? 'Thinking…' : ended ? 'All done' : 'Your stylist'}
        </Text>
      </View>
      {error ? (
        <View style={styles.notice}>
          <Banner tone="warning" text={friendlyMessage(error)} />
        </View>
      ) : null}
      {session && ctx && session.session_id === id ? (
        phase === 'acting' ? (
          <View style={styles.loading}>
            <PrintRepeat />
          </View>
        ) : (
          <GenUIScreen
            envelope={session.ui}
            ctx={ctx}
            header={
              ended ? (
                <Button label="Back to home" variant="primary" onPress={() => router.replace('/')} />
              ) : undefined
            }
          />
        )
      ) : (
        <View style={styles.loading}>
          <PrintRepeat label="Opening your stylist…" />
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.screen, paddingVertical: space.xs },
  notice: { paddingHorizontal: space.screen },
  loading: { padding: space.screen },
});
