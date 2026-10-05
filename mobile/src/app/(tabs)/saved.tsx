import { useQuery } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import type { BoardSummary } from '@/api/types';
import { api } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { Buti } from '@/ui/atoms/Buti';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { EmptyState } from '@/ui/organisms/Panels';

/** Your wishlist and outfit boards (full board editing arrives with CP17). */
export default function SavedTab() {
  const { colors, elevation } = useTheme();
  const boards = useQuery({ queryKey: ['boards'], queryFn: () => api.get<BoardSummary[]>('/v1/boards') });
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <FlatList
        data={boards.data ?? []}
        keyExtractor={(b) => b.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={boards.isRefetching} onRefresh={() => void boards.refetch()} tintColor={colors.shell} />}
        ListHeaderComponent={
          <View style={styles.head}>
            <Text variant="display" accessibilityRole="header">
              Saved
            </Text>
            {boards.error ? <Banner tone="warning" text={friendlyMessage(boards.error)} /> : null}
          </View>
        }
        ListEmptyComponent={
          boards.isLoading ? null : <EmptyState title="Nothing saved yet" body="Tap the heart on any pick to keep it here." />
        }
        renderItem={({ item }) => (
          <View style={[styles.board, { backgroundColor: colors.raised }, elevation(2)]}>
            <View style={[styles.cover, { backgroundColor: item.kind === 'wishlist' ? palette.madder : palette.indigo }]}>
              {item.cover_image_url ? (
                <Image source={{ uri: item.cover_image_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
              ) : (
                <Buti size={36} color={item.kind === 'wishlist' ? '#C9483F' : palette.indigo700} />
              )}
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text variant="bodyStrong">{item.name}</Text>
              <Text variant="bodySmall" tone="secondary">
                {item.item_count} {item.item_count === 1 ? 'item' : 'items'}
              </Text>
            </View>
          </View>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  list: { padding: space.screen, gap: space.sm },
  head: { gap: space.md, marginBottom: space.xs },
  board: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 12, borderRadius: radius.lg },
  cover: { width: 64, height: 64, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
