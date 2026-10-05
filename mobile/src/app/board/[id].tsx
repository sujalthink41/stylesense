import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Crypto from 'expo-crypto';
import * as Haptics from 'expo-haptics';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, FlatList, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { ProductSummary } from '@/api/types';
import { api } from '@/auth/session';
import { WISHLIST_KEY } from '@/boards/wishlist';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { shareLink } from '@/lib/share';
import { Button } from '@/ui/atoms/Button';
import { Icon } from '@/ui/atoms/Icon';
import { IconButton } from '@/ui/atoms/IconButton';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { enter, layout } from '@/ui/motion';
import { EmptyState } from '@/ui/organisms/Panels';
import { Skeleton } from '@/ui/organisms/Skeleton';

interface Board {
  id: string;
  name: string;
  kind: 'wishlist' | 'outfit';
  item_count: number;
  items: { product: ProductSummary }[];
}

const POLL_MIN = 2;
const POLL_MAX = 4;

/** A board: tap to open, long-press to remove, "Ask friends" to turn picks into a poll. */
export default function BoardScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const client = useQueryClient();
  const board = useQuery({ queryKey: ['board', id], queryFn: () => api.get<Board>(`/v1/boards/${id}`) });
  const [polling, setPolling] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const b = board.data;

  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['board', id] });
    void client.invalidateQueries({ queryKey: ['boards'] });
    void client.invalidateQueries({ queryKey: WISHLIST_KEY });
  };

  const remove = (p: ProductSummary) =>
    Alert.alert('Remove from board?', p.title, [
      { text: 'Keep', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: () =>
          void api
            .delete(`/v1/boards/${id}/items/${p.id}`)
            .then(refresh)
            .catch((e: unknown) => setError(friendlyMessage(e))),
      },
    ]);

  const createPoll = async () => {
    setBusy(true);
    try {
      // Client id: a retried create returns the same poll instead of making two.
      const poll = await api.post<{ id: string }>('/v1/polls', { id: Crypto.randomUUID(), product_ids: picked });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setPolling(false);
      setPicked([]);
      router.push(`/poll/${poll.id}`);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (pid: string) => {
    void Haptics.selectionAsync();
    setPicked((p) => (p.includes(pid) ? p.filter((x) => x !== pid) : p.length < POLL_MAX ? [...p, pid] : p));
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <IconButton icon="arrowLeft" label="Back" size={44} onPress={() => router.back()} />
        <View style={{ flex: 1 }} />
        {b && b.items.length ? (
          <IconButton
            icon="share"
            label="Share this board"
            size={44}
            onPress={() => void shareLink({ kind: 'board', boardId: b.id }, `My ${b.name} on StyleSense`).catch((e: unknown) => setError(friendlyMessage(e)))}
          />
        ) : null}
      </View>
      {!b ? (
        <View style={styles.pad}>{board.error ? <Banner tone="warning" text={friendlyMessage(board.error)} /> : <Skeleton shape="question" count={4} />}</View>
      ) : (
        <FlatList
          data={b.items}
          keyExtractor={(i) => i.product.id}
          numColumns={2}
          columnWrapperStyle={styles.columns}
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <Animated.View entering={enter.rise(0)} style={styles.head}>
              <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 40, lineHeight: 42 }}>
                {b.name}
              </Text>
              <Text variant="bodySmall" tone="secondary">
                {b.item_count} {b.item_count === 1 ? 'item' : 'items'}
                {polling ? ` · pick ${POLL_MIN}–${POLL_MAX} to ask friends` : ' · long-press to remove'}
              </Text>
              {error ? <Banner tone="warning" text={error} /> : null}
              {b.items.length >= POLL_MIN && !polling ? (
                <Button label="Ask friends which to buy" variant="tonal" icon="send" onPress={() => setPolling(true)} />
              ) : null}
            </Animated.View>
          }
          ListEmptyComponent={<EmptyState title="Empty for now" body="Tap the heart on any product to save it here." />}
          renderItem={({ item, index }) => {
            const on = picked.includes(item.product.id);
            return (
              <Animated.View entering={enter.rise(index + 1)} layout={layout} style={styles.cell}>
                <PressableScale
                  scaleTo={0.96}
                  accessibilityLabel={`${item.product.title}${on ? ', picked' : ''}`}
                  onPress={() => (polling ? toggle(item.product.id) : router.push(`/product/${item.product.id}`))}
                  onLongPress={() => !polling && remove(item.product)}
                  style={[styles.card, { backgroundColor: colors.raised, borderColor: on ? colors.bestPrice : 'transparent' }]}
                >
                  <View style={[styles.photo, { backgroundColor: palette.indigo700 }]}>
                    {item.product.primary_image_url ? (
                      <Image source={{ uri: item.product.primary_image_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={160} />
                    ) : null}
                    <LinearGradient colors={['transparent', 'rgba(15,22,51,0.75)']} style={styles.scrim} pointerEvents="none" />
                    <Text variant="label" tone="onShell" style={styles.price}>
                      {item.product.min_price_paise != null ? formatRupees(item.product.min_price_paise) : 'Out of stock'}
                    </Text>
                    {polling ? (
                      <View style={[styles.pick, { backgroundColor: on ? colors.bestPrice : 'rgba(255,255,255,0.85)' }]}>
                        {on ? <Icon name="check" size={16} color={palette.ink} strokeWidth={3} /> : null}
                      </View>
                    ) : null}
                  </View>
                  <View style={styles.meta}>
                    <Text variant="caption" tone="secondary" numberOfLines={1}>
                      {item.product.brand}
                    </Text>
                    <Text variant="bodySmall" numberOfLines={2}>
                      {item.product.title}
                    </Text>
                  </View>
                </PressableScale>
              </Animated.View>
            );
          }}
        />
      )}
      {polling ? (
        <Animated.View entering={enter.rise(0)} style={[styles.dock, { backgroundColor: colors.raised, borderTopColor: colors.hairline }]}>
          <Button label="Cancel" variant="ghost" onPress={() => (setPolling(false), setPicked([]))} />
          <Button
            label={picked.length >= POLL_MIN ? `Create poll (${picked.length})` : `Pick ${POLL_MIN - picked.length} more`}
            variant="action"
            disabled={picked.length < POLL_MIN}
            loading={busy}
            onPress={() => void createPoll()}
            style={{ flex: 1 }}
          />
        </Animated.View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.screen, paddingVertical: space.xs },
  pad: { padding: space.screen },
  list: { padding: space.screen, gap: 12, paddingBottom: 120 },
  columns: { gap: 12 },
  head: { gap: 10, marginBottom: 8 },
  cell: { flex: 1 },
  card: { borderRadius: radius.lg, overflow: 'hidden', borderWidth: 3 },
  photo: { aspectRatio: 0.8, justifyContent: 'flex-end' },
  scrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '40%' },
  price: { padding: 10 },
  pick: { position: 'absolute', top: 10, right: 10, width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  meta: { padding: 10, gap: 2 },
  dock: { flexDirection: 'row', gap: 10, padding: space.screen, borderTopWidth: StyleSheet.hairlineWidth },
});
