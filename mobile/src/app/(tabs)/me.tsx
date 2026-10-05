import { useQuery } from '@tanstack/react-query';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_URL, APP_VERSION } from '@/api/config';
import type { StyleProfileView } from '@/api/types';
import { api, useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { GENUI_CATALOG_VERSION } from '@/genui/types.gen';
import { Badge } from '@/ui/atoms/Badge';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';

export default function MeTab() {
  const { colors, elevation } = useTheme();
  const user = useSession((s) => s.user);
  const signOut = useSession((s) => s.signOut);
  const profile = useQuery({ queryKey: ['style-profile'], queryFn: () => api.get<StyleProfileView>('/v1/me/style-profile') });
  const initial = (user?.display_name ?? user?.email ?? '?').charAt(0).toUpperCase();
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.who}>
          <View style={[styles.avatar, { backgroundColor: colors.bestPrice }]}>
            <Text variant="headline" tone="onBestPrice">
              {initial}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text variant="title">{user?.display_name ?? 'You'}</Text>
            <Text variant="bodySmall" tone="secondary">
              {user?.email}
            </Text>
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]}>
          <Text variant="headline">Your Style DNA</Text>
          {profile.data?.onboarding_done ? (
            <>
              <Text variant="bodySmall" tone="secondary">
                {profile.data.swipe_count} swipes taught your stylist so far.
              </Text>
              <View style={styles.tags}>
                {[...profile.data.styles, ...profile.data.top_tags].slice(0, 6).map((t) => (
                  <Badge key={t} kind="taste" label={t} />
                ))}
              </View>
            </>
          ) : (
            <Text variant="bodySmall" tone="secondary">
              Not set yet. Start it from Home: 30 seconds, taps only.
            </Text>
          )}
        </View>

        <Button label="Sign out" variant="tonal" icon="logout" onPress={() => void signOut()} />
        <Text variant="caption" tone="secondary" align="center">
          StyleSense {APP_VERSION} · UI catalog v{GENUI_CATALOG_VERSION}
          {__DEV__ ? ` · ${API_URL}` : ''}
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  body: { padding: space.screen, gap: space.lg },
  who: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  avatar: { width: 56, height: 56, borderRadius: 56, alignItems: 'center', justifyContent: 'center' },
  card: { borderRadius: radius.lg, padding: 18, gap: 10 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
});
