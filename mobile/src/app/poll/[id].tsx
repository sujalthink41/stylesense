import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';
import { ScrollView, Share, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withDelay, withSpring } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { ProductSummary } from '@/api/types';
import { api } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { storeName } from '@/ui/organisms/ProductSwipeCard';
import { Badge } from '@/ui/atoms/Badge';
import { Button } from '@/ui/atoms/Button';
import { IconButton } from '@/ui/atoms/IconButton';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { enter, Rise } from '@/ui/motion';
import { Skeleton } from '@/ui/organisms/Skeleton';

interface Poll {
  id: string;
  url: string;
  question: string;
  status: 'open' | 'closed';
  closes_at: string;
  total_votes: number;
  options: { option_id: string; product: ProductSummary; votes: number | null }[];
}

function timeLeft(iso: string, now = Date.now()): string {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - now) / 3_600_000));
  return h >= 24 ? `${Math.round(h / 24)} days left` : h >= 1 ? `${h} h left` : 'closing soon';
}

/** Your poll's live results: friends vote on the web, no app or sign-in needed. */
export default function PollScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const client = useQueryClient();
  const poll = useQuery({
    queryKey: ['poll', id],
    queryFn: () => api.get<Poll>(`/v1/polls/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'open' ? 10_000 : false),
  });
  const p = poll.data;
  const max = Math.max(1, ...(p?.options.map((o) => o.votes ?? 0) ?? [0]));
  const leader = p && p.total_votes > 0 ? p.options.reduce((a, b) => ((b.votes ?? 0) > (a.votes ?? 0) ? b : a)) : null;

  const close = async () => {
    await api.post(`/v1/polls/${id}/close`).catch(() => undefined);
    void client.invalidateQueries({ queryKey: ['poll', id] });
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <IconButton icon="arrowLeft" label="Back" size={44} onPress={() => router.back()} />
      </View>
      {!p ? (
        <View style={styles.pad}>{poll.error ? <Banner tone="warning" text={friendlyMessage(poll.error)} /> : <Skeleton shape="question" />}</View>
      ) : (
        <ScrollView contentContainerStyle={styles.body}>
          <Rise index={0} style={{ gap: 8 }}>
            <View style={styles.row}>
              <Badge kind={p.status === 'open' ? 'inStock' : 'neutral'} label={p.status === 'open' ? `Live · ${timeLeft(p.closes_at)}` : 'Closed'} />
              <Text variant="bodySmall" tone="secondary">
                {p.total_votes} {p.total_votes === 1 ? 'vote' : 'votes'}
              </Text>
            </View>
            <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 38, lineHeight: 40 }}>
              {p.question}
            </Text>
          </Rise>
          {p.options.map((o, i) => (
            <Rise key={o.option_id} index={i + 1}>
              <PressableScale
                scaleTo={0.98}
                onPress={() => router.push(`/product/${o.product.id}`)}
                accessibilityLabel={`${o.product.title}: ${o.votes ?? 0} votes`}
                style={[styles.option, { backgroundColor: colors.raised }]}
              >
                <View style={[styles.thumb, { backgroundColor: palette.indigo700 }]}>
                  {o.product.primary_image_url ? <Image source={{ uri: o.product.primary_image_url }} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
                </View>
                <View style={{ flex: 1, gap: 6 }}>
                  <Text variant="bodyStrong" numberOfLines={1}>
                    {o.product.title}
                  </Text>
                  <Text variant="caption" tone="secondary">
                    {o.product.min_price_paise != null ? formatRupees(o.product.min_price_paise) : o.product.best_store ? `See price on ${storeName(o.product.best_store)}` : 'Out of stock'}
                  </Text>
                  <VoteBar share={(o.votes ?? 0) / max} lead={leader?.option_id === o.option_id} delay={i * 90} />
                </View>
                <Text variant="headline" style={{ minWidth: 28, textAlign: 'right' }}>
                  {o.votes ?? 0}
                </Text>
              </PressableScale>
            </Rise>
          ))}
          <Animated.View entering={enter.rise(p.options.length + 1)} style={{ gap: 8 }}>
            {p.status === 'open' ? (
              <>
                <Button
                  label="Send to friends"
                  variant="action"
                  icon="send"
                  fullWidth
                  onPress={() => void Share.share({ message: `${p.question} Help me pick:\n${p.url}`, url: p.url })}
                />
                <Button label="Close voting" variant="ghost" fullWidth onPress={() => void close()} />
              </>
            ) : leader ? (
              <Button label="Open the winner" variant="primary" fullWidth onPress={() => router.push(`/product/${leader.product.id}`)} />
            ) : null}
          </Animated.View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function VoteBar({ share, lead, delay }: { share: number; lead: boolean; delay: number }) {
  const { colors } = useTheme();
  const w = useSharedValue(0);
  useEffect(() => {
    w.set(withDelay(delay, withSpring(share, { damping: 16 })));
  }, [share, delay, w]);
  const fill = useAnimatedStyle(() => ({ width: `${Math.max(0.04, w.value) * 100}%` }));
  return (
    <View style={[styles.track, { backgroundColor: colors.tonal }]}>
      <Animated.View style={[styles.fill, { backgroundColor: lead ? colors.bestPrice : colors.shell }, fill]} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { paddingHorizontal: space.screen, paddingVertical: space.xs },
  pad: { padding: space.screen },
  body: { padding: space.screen, gap: space.md, paddingBottom: space.xl },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  option: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 12, borderRadius: radius.lg },
  thumb: { width: 64, height: 80, borderRadius: radius.md, overflow: 'hidden' },
  track: { height: 10, borderRadius: 5, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 5 },
});
