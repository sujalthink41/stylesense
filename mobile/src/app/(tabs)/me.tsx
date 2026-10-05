import { useQuery } from '@tanstack/react-query';
import { router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_URL, APP_VERSION } from '@/api/config';
import type { StyleOptions, StyleProfileView } from '@/api/types';
import { api, useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { GENUI_CATALOG_VERSION } from '@/genui/types.gen';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';
import { StyleDnaCard } from '@/ui/organisms/StyleDnaCard';
import { useStylist } from '@/stylist';

export default function MeTab() {
  const { colors } = useTheme();
  const user = useSession((s) => s.user);
  const signOut = useSession((s) => s.signOut);
  const profile = useQuery({ queryKey: ['style-profile'], queryFn: () => api.get<StyleProfileView>('/v1/me/style-profile') });
  const options = useQuery({
    queryKey: ['style-options'],
    queryFn: () => api.get<StyleOptions>('/v1/me/style-profile/options'),
    staleTime: 24 * 60 * 60 * 1000, // the catalogue of looks rarely changes
  });
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);
  // Back from a Style DNA session or a swipe spree: show what changed.
  const { refetch } = profile;
  useFocusEffect(
    useCallback(() => {
      void refetch();
    }, [refetch]),
  );
  const retake = async () => {
    const id = await start('onboarding');
    if (id) router.push(`/session/${id}`);
  };
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

        <StyleDnaCard profile={profile.data} options={options.data} busy={phase === 'starting'} onStart={() => void retake()} />

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
});
