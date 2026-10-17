import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as Linking from 'expo-linking';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import Animated from 'react-native-reanimated';
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
import { formatRupees } from '@/lib/money';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Chip } from '@/ui/atoms/Chip';
import { Icon, type IconName } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { BudgetSlider } from '@/ui/molecules/BudgetSlider';
import { enter, Rise } from '@/ui/motion';
import { StyleDnaCard } from '@/ui/organisms/StyleDnaCard';

// Brands people shop for most on the three stores; any of them can be a favourite.
const POPULAR_BRANDS = [
  'Nike', 'Adidas', 'Puma', 'ASICS', 'Skechers', 'Red Tape', 'Campus', "Levi's", 'Roadster', 'HRX',
  'U.S. Polo Assn.', 'Allen Solly', 'Van Heusen', 'Peter England', 'Jack & Jones', 'H&M', 'Zara',
  'Biba', 'Libas', 'W', 'Aurelia', 'Fabindia', 'Manyavar', 'Snitch', 'Bewakoof', 'The Souled Store',
  'Highlander', 'Mast & Harbour', 'Tommy Hilfiger', 'Calvin Klein', 'Crocs', 'Woodland',
];
const SHOPPING_FOR: { id: 'men' | 'women' | 'any'; label: string }[] = [
  { id: 'men', label: 'Men' },
  { id: 'women', label: 'Women' },
  { id: 'any', label: 'Everyone' },
];
const MAX_BRANDS = 8;

type Draft = {
  fit: StyleProfileView['fit_preference'];
  sizes: StyleProfileView['sizes'];
  brands: string[];
  budget: number | null;
};

function draftOf(p: StyleProfileView | undefined): Draft {
  return {
    fit: p?.fit_preference ?? null,
    sizes: { ...(p?.sizes ?? {}) },
    brands: [...(p?.favorite_brands ?? [])],
    budget: p?.usual_budget_paise ?? null,
  };
}

/** You, your style, and your data: everything here is yours to change or delete. */
export default function MeTab() {
  const { colors } = useTheme();
  const client = useQueryClient();
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

  // Only what the person changed is state; everything shown is the saved profile plus edits.
  const [edits, setEdits] = useState<Partial<Draft>>({});
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ tone: 'info' | 'warning'; text: string } | null>(null);
  const draft = useMemo<Draft>(() => ({ ...draftOf(profile.data), ...edits }), [profile.data, edits]);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(draftOf(profile.data)), [draft, profile.data]);
  const setDraft = (change: (d: Draft) => Draft) => setEdits(change(draft));

  const save = async () => {
    if (!profile.data) return;
    setSaving(true);
    setNote(null);
    try {
      // Saved whole; the Style DNA looks are sent back unchanged.
      await api.put('/v1/me/style-profile', {
        styles: profile.data.styles,
        fit_preference: draft.fit,
        sizes: draft.sizes,
        favorite_brands: draft.brands,
        usual_budget_paise: draft.budget,
      });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setNote({ tone: 'info', text: 'Saved. Your picks will use this from now on.' });
      await client.invalidateQueries({ queryKey: ['style-profile'] });
      setEdits({});
    } catch (e) {
      setNote({ tone: 'warning', text: friendlyMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  const retake = async () => {
    const id = await start('onboarding');
    if (id) router.push(`/session/${id}`);
  };

  const saved = boards.data?.reduce((n, b) => n + b.item_count, 0) ?? 0;
  const setSize = (kind: 'top' | 'bottom' | 'shoe') => (v: string | null) =>
    setDraft((d) => ({ ...d, sizes: { ...d.sizes, [kind]: v } as Draft['sizes'] }));

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
          <Section title="Your details" hint="Used to prefill sizes and lift the brands you love.">
            <Field label="Shopping for">
              <View style={styles.chips}>
                {SHOPPING_FOR.map((o) => (
                  <Chip key={o.id} label={o.label} selected={draft.fit === o.id} onPress={() => setDraft((d) => ({ ...d, fit: o.id }))} />
                ))}
              </View>
            </Field>
            <SizeRow label="Top size" values={options.data?.top_sizes ?? []} selected={draft.sizes.top} onPick={setSize('top')} />
            <SizeRow label="Waist" values={options.data?.bottom_sizes ?? []} selected={draft.sizes.bottom} onPick={setSize('bottom')} />
            <SizeRow label="Shoe size" values={options.data?.shoe_sizes ?? []} selected={draft.sizes.shoe} onPick={setSize('shoe')} />
            <BrandPicker selected={draft.brands} onChange={(brands) => setDraft((d) => ({ ...d, brands }))} />
            <Field label={draft.budget ? `Usual budget: up to ${formatRupees(draft.budget)}` : 'Usual budget'}>
              <BudgetSlider
                label="Usual budget for one item"
                minPaise={50_000}
                maxPaise={1_000_000}
                stepPaise={50_000}
                value={draft.budget ?? 200_000}
                onChange={(v) => setDraft((d) => ({ ...d, budget: v }))}
              />
            </Field>
            {note ? <Banner tone={note.tone} text={note.text} /> : null}
            {dirty ? (
              <Animated.View entering={enter.pop()}>
                <Button label="Save my details" variant="primary" fullWidth loading={saving} onPress={() => void save()} />
              </Animated.View>
            ) : null}
          </Section>
        </Rise>

        <Rise index={4}>
          <Section title="Privacy & account">
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <Text variant="label">{label}</Text>
      {children}
    </View>
  );
}

function SizeRow({ label, values, selected, onPick }: { label: string; values: string[]; selected?: string | null; onPick(v: string | null): void }) {
  if (!values.length) return null;
  return (
    <Field label={label}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        {values.map((v) => (
          <Chip key={v} label={v} selected={selected === v} onPress={() => onPick(selected === v ? null : v)} />
        ))}
      </ScrollView>
    </Field>
  );
}

function BrandPicker({ selected, onChange }: { selected: string[]; onChange(brands: string[]): void }) {
  const [open, setOpen] = useState(false);
  const toggle = (b: string) =>
    onChange(selected.includes(b) ? selected.filter((x) => x !== b) : selected.length < MAX_BRANDS ? [...selected, b] : selected);
  const rest = POPULAR_BRANDS.filter((b) => !selected.includes(b));
  const shown = open ? [...selected, ...rest] : [...selected, ...rest].slice(0, Math.max(8, selected.length));
  return (
    <Field label={`Favourite brands${selected.length ? ` (${selected.length}/${MAX_BRANDS})` : ''}`}>
      <View style={styles.chips}>
        {shown.map((b) => (
          <Chip key={b} label={b} selected={selected.includes(b)} onPress={() => toggle(b)} />
        ))}
        <Chip label={open ? 'Fewer' : 'More brands'} onPress={() => setOpen((o) => !o)} />
      </View>
    </Field>
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
