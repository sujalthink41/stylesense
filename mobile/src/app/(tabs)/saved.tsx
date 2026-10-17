import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Crypto from 'expo-crypto';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { BoardSummary } from '@/api/types';
import { api } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { typeScale } from '@/design/typography';
import { Badge } from '@/ui/atoms/Badge';
import { Buti } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { enter, Rise } from '@/ui/motion';

interface PollSummary {
  id: string;
  question: string;
  status: 'open' | 'closed';
  total_votes: number;
}

/** Wishlist first, then outfit boards; your polls underneath. */
export default function SavedTab() {
  const { colors, elevation } = useTheme();
  const client = useQueryClient();
  const boards = useQuery({ queryKey: ['boards'], queryFn: () => api.get<BoardSummary[]>('/v1/boards') });
  const polls = useQuery({ queryKey: ['polls'], queryFn: () => api.get<PollSummary[]>('/v1/polls') });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { refetch: refetchBoards } = boards;
  const { refetch: refetchPolls } = polls;
  useFocusEffect(
    useCallback(() => {
      void refetchBoards();
      void refetchPolls();
    }, [refetchBoards, refetchPolls]),
  );

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const board = await api.post<BoardSummary>('/v1/boards', { id: Crypto.randomUUID(), name: trimmed });
      setCreating(false);
      setName('');
      void client.invalidateQueries({ queryKey: ['boards'] });
      router.push(`/board/${board.id}`);
    } catch (e) {
      setError(friendlyMessage(e));
    }
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={boards.isRefetching} onRefresh={() => void refetchBoards()} tintColor={colors.shell} />}
      >
        <Rise index={0} style={styles.head}>
          <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 44, lineHeight: 44 }}>
            Saved
          </Text>
          <PressableScale
            accessibilityLabel="New board"
            onPress={() => setCreating((c) => !c)}
            style={[styles.newBtn, { backgroundColor: colors.shell }]}
          >
            <Icon name={creating ? 'close' : 'plus'} size={20} color={colors.onShell} strokeWidth={2.4} />
          </PressableScale>
        </Rise>
        {error || boards.error ? <Banner tone="warning" text={error ?? friendlyMessage(boards.error)} /> : null}
        {creating ? (
          <Animated.View entering={enter.rise(0)} style={[styles.sheet, { backgroundColor: colors.raised }, elevation(2)]}>
            <Text variant="label">Name your board</Text>
            <TextInput
              autoFocus
              value={name}
              onChangeText={setName}
              maxLength={60}
              placeholder="Goa trip, Office week, Sangeet…"
              placeholderTextColor={colors.textSecondary}
              onSubmitEditing={() => void create()}
              style={[typeScale.body, styles.input, { backgroundColor: colors.ground, color: colors.text }]}
              accessibilityLabel="Board name"
            />
            <Button label="Create board" variant="primary" disabled={!name.trim()} onPress={() => void create()} />
          </Animated.View>
        ) : null}

        <View style={styles.grid}>
          {(boards.data ?? []).map((b, i) => (
            <Animated.View key={b.id} entering={enter.rise(i + 1)} style={i === 0 ? styles.wide : styles.half}>
              <PressableScale
                onPress={() => router.push(`/board/${b.id}`)}
                accessibilityLabel={`${b.name}, ${b.item_count} items`}
                style={[styles.board, { backgroundColor: b.kind === 'wishlist' ? palette.madder : palette.indigo }, elevation(2)]}
              >
                {b.cover_image_url ? (
                  <Image source={{ uri: b.cover_image_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={160} />
                ) : (
                  <View style={styles.motif}>
                    <Buti size={i === 0 ? 170 : 110} color={b.kind === 'wishlist' ? '#C9483F' : palette.indigo700} />
                  </View>
                )}
                <LinearGradient colors={['transparent', 'rgba(15,22,51,0.85)']} style={styles.scrim} pointerEvents="none" />
                <View style={styles.boardText}>
                  {b.kind === 'wishlist' ? <Icon name="heart" size={18} color={palette.white} /> : null}
                  <Text variant={i === 0 ? 'headline' : 'bodyStrong'} tone="onShell" numberOfLines={1}>
                    {b.name}
                  </Text>
                  <Text variant="caption" tone="onShellMuted">
                    {b.item_count} {b.item_count === 1 ? 'item' : 'items'}
                  </Text>
                </View>
              </PressableScale>
            </Animated.View>
          ))}
        </View>

        {polls.data?.length ? (
          <Rise index={(boards.data?.length ?? 0) + 1} style={{ gap: 10 }}>
            <Text variant="headline" accessibilityRole="header">
              Your polls
            </Text>
            {polls.data.map((p) => (
              <PressableScale key={p.id} onPress={() => router.push(`/poll/${p.id}`)} style={[styles.poll, { backgroundColor: colors.raised }]}>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text variant="bodyStrong" numberOfLines={1}>
                    {p.question}
                  </Text>
                  <Text variant="caption" tone="secondary">
                    {p.total_votes} {p.total_votes === 1 ? 'vote' : 'votes'}
                  </Text>
                </View>
                <Badge kind={p.status === 'open' ? 'inStock' : 'neutral'} label={p.status === 'open' ? 'Live' : 'Closed'} />
                <Icon name="chevronRight" size={20} color={colors.textSecondary} />
              </PressableScale>
            ))}
          </Rise>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  body: { padding: space.screen, gap: space.md, paddingBottom: space.xl },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  newBtn: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  sheet: { borderRadius: radius.lg, padding: 16, gap: 12 },
  input: { height: 52, borderRadius: radius.md, paddingHorizontal: 14 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 },
  wide: { width: '100%' },
  half: { width: '48.5%' },
  board: { height: 190, borderRadius: radius.xl, overflow: 'hidden', justifyContent: 'flex-end' },
  motif: { position: 'absolute', right: -30, top: -20 },
  scrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '60%' },
  boardText: { padding: 16, gap: 2 },
  poll: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: radius.lg },
});
