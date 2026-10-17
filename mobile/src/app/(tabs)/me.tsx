import { useQuery } from '@tanstack/react-query';
import * as Linking from 'expo-linking';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_URL, APP_VERSION } from '@/api/config';
import { friendlyMessage } from '@/api/errors';
import type { BoardSummary, StyleOptions, StyleProfileView, TryOnQuota, UserProfile } from '@/api/types';
import { googleSignOut } from '@/auth/google';
import { api, useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { typeScale } from '@/design/typography';
import { GENUI_CATALOG_VERSION } from '@/genui/types.gen';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Icon, type IconName } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { Rise } from '@/ui/motion';
import { StyleDnaCard } from '@/ui/organisms/StyleDnaCard';

/** You, your style, and your data: everything here is yours to change or delete. */
export default function MeTab() {
  const { colors } = useTheme();
  const user = useSession((s) => s.user);
  const signOut = useSession((s) => s.signOut);
  const start = useStylist((s) => s.start);
  const phase = useStylist((s) => s.phase);

  const profile = useQuery({ queryKey: ['style-profile'], queryFn: () => api.get<StyleProfileView>('/v1/me/style-profile') });
  const options = useQuery({
    queryKey: ['style-options'],
    queryFn: () => api.get<StyleOptions>('/v1/me/style-profile/options'),
    staleTime: 24 * 60 * 60 * 1000,
  });
  const boards = useQuery({ queryKey: ['boards'], queryFn: () => api.get<BoardSummary[]>('/v1/boards') });
  const polls = useQuery({ queryKey: ['polls'], queryFn: () => api.get<unknown[]>('/v1/polls') });
  const quota = useQuery({ queryKey: ['tryon-quota'], queryFn: () => api.get<TryOnQuota>('/v1/tryon/quota') });

  // Back from Style DNA, a swipe spree or a try-on: show what changed.
  const refresh = [profile.refetch, boards.refetch, polls.refetch, quota.refetch];
  useFocusEffect(
    useCallback(() => {
      for (const r of refresh) void r();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []),
  );

  const retake = async () => {
    const id = await start('onboarding');
    if (id) router.push(`/session/${id}`);
  };

  const saved = boards.data?.reduce((n, b) => n + b.item_count, 0) ?? 0;

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Rise index={0}>
          <Header user={user} />
        </Rise>

        <Rise index={1} style={styles.stats}>
          <Stat value={profile.data?.swipe_count ?? 0} label="Swipes" icon="heart" />
          <Stat value={saved} label="Saved" icon="saved" />
          <Stat value={polls.data?.length ?? 0} label="Polls" icon="send" />
          <Stat value={quota.data?.remaining ?? '–'} label="Try-ons left" icon="camera" />
        </Rise>

        <Rise index={2}>
          <StyleDnaCard profile={profile.data} options={options.data} busy={phase === 'starting'} onStart={() => void retake()} />
        </Rise>

        <Rise index={3}>
          <Section title="Privacy & account" hint="Sizes, budget and who you shop for? Just tell the stylist in the chat.">
            <Row icon="info" label="Privacy policy" onPress={() => void Linking.openURL(`${API_URL}/privacy`)} />
            <Row icon="info" label="Terms of use" onPress={() => void Linking.openURL(`${API_URL}/terms`)} />
            <Row icon="logout" label="Sign out" onPress={() => void Promise.all([signOut(), googleSignOut()])} />
            <DeleteAccountRow onDeleted={() => void Promise.all([signOut(), googleSignOut()])} />
          </Section>
        </Rise>

        <Text variant="caption" tone="secondary" align="center">
          StyleSense {APP_VERSION} · UI catalog v{GENUI_CATALOG_VERSION}
          {__DEV__ ? ` · ${API_URL}` : ''}
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

/** Avatar, name (tap to change it) and since when. */
function Header({ user }: { user: UserProfile | null }) {
  const { colors, elevation } = useTheme();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.display_name ?? '');
  const [error, setError] = useState<string | null>(null);
  const initial = (user?.display_name ?? user?.email ?? '?').trim().charAt(0).toUpperCase();
  const since = user?.created_at ? new Date(user.created_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : null;

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === user?.display_name) {
      setEditing(false);
      return;
    }
    try {
      const updated = await api.patch<UserProfile>('/v1/me', { display_name: trimmed });
      useSession.setState({ user: updated });
      setEditing(false);
      setError(null);
    } catch (e) {
      setError(friendlyMessage(e));
    }
  };

  return (
    <View style={[styles.header, { backgroundColor: colors.shell }, elevation(2)]}>
      <View style={styles.headerMotif} pointerEvents="none">
        <Buti size={150} color={palette.indigo700} />
      </View>
      <View style={[styles.avatar, { backgroundColor: palette.turmeric }]}>
        <Text variant="displayXL" style={{ color: palette.ink, fontSize: 34, lineHeight: 38 }}>
          {initial}
        </Text>
      </View>
      {editing ? (
        <View style={styles.editor}>
          <TextInput
            autoFocus
            value={name}
            onChangeText={setName}
            maxLength={60}
            onSubmitEditing={() => void save()}
            placeholder="Your name"
            placeholderTextColor="#AEB5D4"
            accessibilityLabel="Your name"
            style={[typeScale.body, styles.nameInput, { backgroundColor: colors.shellRaised, color: colors.onShell }]}
          />
          <View style={styles.editorButtons}>
            <Button label="Save" variant="inverse" style={{ flex: 1 }} onPress={() => void save()} />
            <Button label="Cancel" variant="ghost" onPress={() => setEditing(false)} />
          </View>
          {error ? (
            <Text variant="bodySmall" style={{ color: palette.madderTint }}>
              {error}
            </Text>
          ) : null}
        </View>
      ) : (
        <PressableScale
          accessibilityLabel="Change your name"
          onPress={() => {
            setName(user?.display_name ?? '');
            setEditing(true);
          }}
          style={styles.nameRow}
        >
          <Text variant="title" tone="onShell" numberOfLines={1}>
            {user?.display_name ?? 'Add your name'}
          </Text>
          <Icon name="chevronRight" size={18} color={colors.onShell} />
        </PressableScale>
      )}
      <Text variant="bodySmall" tone="onShellMuted">
        {user?.email}
        {since ? ` · with StyleSense since ${since}` : ''}
      </Text>
    </View>
  );
}

function Stat({ value, label, icon }: { value: number | string; label: string; icon: IconName }) {
  const { colors, elevation } = useTheme();
  return (
    <View style={[styles.stat, { backgroundColor: colors.raised }, elevation(1)]} accessible accessibilityLabel={`${value} ${label}`}>
      <Icon name={icon} size={18} color={colors.textSecondary} />
      <Text variant="headline">{value}</Text>
      <Text variant="caption" tone="secondary" numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  const { colors, elevation } = useTheme();
  return (
    <View style={[styles.section, { backgroundColor: colors.raised }, elevation(2)]}>
      <View style={{ gap: 2 }}>
        <Text variant="headline" accessibilityRole="header">
          {title}
        </Text>
        {hint ? (
          <Text variant="bodySmall" tone="secondary">
            {hint}
          </Text>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function Row({ icon, label, onPress, danger }: { icon: IconName; label: string; onPress(): void; danger?: boolean }) {
  const { colors } = useTheme();
  return (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={label} style={[styles.row, { borderTopColor: colors.hairline }]}>
      <Icon name={icon} size={20} color={danger ? colors.action : colors.textSecondary} />
      <Text variant="bodyStrong" style={{ flex: 1, color: danger ? colors.action : colors.text }}>
        {label}
      </Text>
      <Icon name="chevronRight" size={18} color={colors.textSecondary} />
    </PressableScale>
  );
}

/** In-app deletion (a Play Store requirement): closed at once, data erased within 30 days. */
function DeleteAccountRow({ onDeleted }: { onDeleted(): void }) {
  const confirm = () =>
    Alert.alert(
      'Delete your account?',
      "You'll be signed out on every device. Your profile, saves, boards, polls and history are erased within 30 days. This can't be undone.",
      [
        { text: 'Keep my account', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () =>
            void api
              .delete('/v1/me')
              .then(onDeleted)
              .catch((e: unknown) => Alert.alert('Could not delete', friendlyMessage(e))),
        },
      ],
    );
  return <Row icon="close" label="Delete account" onPress={confirm} danger />;
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  body: { padding: space.screen, gap: space.lg, paddingBottom: space.xl },
  header: { borderRadius: radius.xl, padding: 20, alignItems: 'flex-start', gap: 10, overflow: 'hidden' },
  headerMotif: { position: 'absolute', right: -30, top: -30 },
  avatar: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  editor: { gap: 8, alignSelf: 'stretch' },
  editorButtons: { flexDirection: 'row', gap: 8 },
  nameInput: { height: 50, borderRadius: radius.md, paddingHorizontal: 14 },
  stats: { flexDirection: 'row', gap: 8 },
  stat: { flex: 1, borderRadius: radius.lg, paddingVertical: 12, alignItems: 'center', gap: 2 },
  section: { borderRadius: radius.lg, padding: 18, gap: 16 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, borderTopWidth: StyleSheet.hairlineWidth },
});
