/** Smaller organisms the stylist sends: questions, comparisons, looks, carousels, notices. */
import { Image } from 'expo-image';
import { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { Button } from '@/ui/atoms/Button';
import { Chip } from '@/ui/atoms/Chip';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';
import { StoreOfferRow } from '@/ui/molecules/StoreOfferRow';

import type { ProductCardData } from './ProductSwipeCard';

// ---------- question card ----------

export interface QuestionOption {
  id: string;
  label: string;
}

export function QuestionCard({
  question,
  options,
  multi = false,
  maxSelect = 1,
  disabled,
  onSubmit,
}: {
  question: string;
  options: QuestionOption[];
  multi?: boolean;
  maxSelect?: number;
  disabled?: boolean;
  onSubmit(ids: string[]): void;
}) {
  const { colors, elevation } = useTheme();
  const [picked, setPicked] = useState<string[]>([]);
  // The stylist leads with what it understood ("Got it: summer t-shirts.") then asks.
  const split = question.match(/^(Got it:[^.]*\.)\s*(.*)$/);
  const lead = split?.[1];
  const ask = split?.[2] ?? question;
  const toggle = (id: string) => {
    if (!multi) {
      onSubmit([id]);
      return;
    }
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < maxSelect ? [...p, id] : p));
  };
  return (
    <View style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]}>
      <View style={styles.cardHead}>
        {lead ? (
          <Text variant="bodySmall" tone="secondary">
            {lead}
          </Text>
        ) : null}
        <Text variant="display" style={{ fontSize: 30, lineHeight: 32 }} accessibilityRole="header">
          {ask}
        </Text>
      </View>
      <View style={styles.options}>
        {options.map((o) => (
          <Chip
            key={o.id}
            shape="tile"
            label={o.label}
            selected={picked.includes(o.id)}
            disabled={disabled}
            onPress={() => toggle(o.id)}
            testID={`option-${o.id}`}
          />
        ))}
      </View>
      {multi ? (
        <Button label={picked.length ? 'Continue' : 'Pick at least one'} disabled={!picked.length || disabled} onPress={() => onSubmit(picked)} />
      ) : null}
    </View>
  );
}

// ---------- image choice grid (Style DNA) ----------

export function ImageChoiceGrid({
  question,
  options,
  maxSelect,
  disabled,
  onSubmit,
}: {
  question: string;
  options: { id: string; label: string; image_url: string }[];
  maxSelect: number;
  disabled?: boolean;
  onSubmit(ids: string[]): void;
}) {
  const { colors } = useTheme();
  const [picked, setPicked] = useState<string[]>([]);
  return (
    <View style={styles.gridWrap}>
      <Text variant="display" style={{ fontSize: 30, lineHeight: 32 }} accessibilityRole="header">
        {question}
      </Text>
      <View style={styles.grid}>
        {options.map((o) => {
          const on = picked.includes(o.id);
          return (
            <PressableScale
              key={o.id}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
              accessibilityLabel={o.label}
              onPress={() => setPicked((p) => (on ? p.filter((x) => x !== o.id) : p.length < maxSelect ? [...p, o.id] : p))}
              style={[styles.gridItem, { borderColor: on ? colors.bestPrice : 'transparent' }]}
            >
              <Image source={{ uri: o.image_url }} style={styles.gridImage} contentFit="cover" />
              <View style={[styles.gridLabel, { backgroundColor: on ? colors.bestPrice : colors.raised }]}>
                <Text variant="label" tone={on ? 'onBestPrice' : 'default'} numberOfLines={1}>
                  {o.label}
                </Text>
              </View>
            </PressableScale>
          );
        })}
      </View>
      <Button
        label={picked.length ? `Continue with ${picked.length}` : `Pick up to ${maxSelect}`}
        disabled={!picked.length || disabled}
        onPress={() => onSubmit(picked)}
      />
    </View>
  );
}

// ---------- store comparison ----------

export interface OfferData {
  offer_id: string;
  store_name: string;
  price_paise: number;
  in_stock: boolean;
  is_best: boolean;
  buy_path: string;
}

export function StoreComparison({ offers, onBuy }: { offers: OfferData[]; onBuy(offer: OfferData): void }) {
  const { colors, elevation } = useTheme();
  return (
    <View style={styles.section}>
      <Text variant="headline" accessibilityRole="header">
        Prices across stores
      </Text>
      <View style={[styles.offers, { backgroundColor: colors.raised }, elevation(2)]}>
        {offers.map((o, i) => (
          <StoreOfferRow
            key={o.offer_id}
            first={i === 0}
            storeName={o.store_name}
            pricePaise={o.price_paise}
            inStock={o.in_stock}
            isBest={o.is_best}
            onBuy={() => onBuy(o)}
          />
        ))}
      </View>
    </View>
  );
}

// ---------- complete the look ----------

export function LookPanel({
  title,
  items,
  remainingPaise,
  onOpen,
}: {
  title: string;
  items: ProductCardData[];
  remainingPaise?: number | null;
  onOpen(item: ProductCardData): void;
}) {
  return (
    <View style={[styles.look, { backgroundColor: palette.indigo }]}>
      <Text variant="headline" tone="onShell" accessibilityRole="header">
        {title}
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rail}>
        {items.map((item) => (
          <MiniCard key={item.product_id} item={item} onPress={() => onOpen(item)} onShell />
        ))}
      </ScrollView>
      {remainingPaise != null ? (
        <Text variant="bodySmall" tone="onShellMuted">
          {formatRupees(remainingPaise)} left in your look budget
        </Text>
      ) : null}
    </View>
  );
}

export function ProductCarousel({ title, items, onOpen }: { title: string; items: ProductCardData[]; onOpen(item: ProductCardData): void }) {
  return (
    <View style={styles.section}>
      <Text variant="headline" accessibilityRole="header">
        {title}
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rail}>
        {items.map((item) => (
          <MiniCard key={item.product_id} item={item} onPress={() => onOpen(item)} />
        ))}
      </ScrollView>
    </View>
  );
}

function MiniCard({ item, onPress, onShell }: { item: ProductCardData; onPress(): void; onShell?: boolean }) {
  const { colors, elevation } = useTheme();
  return (
    <PressableScale
      onPress={onPress}
      accessibilityLabel={`${item.title}, ${item.price_paise != null ? formatRupees(item.price_paise) : 'out of stock'}`}
      style={[styles.mini, { backgroundColor: onShell ? palette.indigo700 : colors.raised }, !onShell && elevation(1)]}
    >
      <View style={[styles.miniPhoto, { backgroundColor: onShell ? '#3D4F8F' : colors.tonal }]}>
        {item.image_url ? <Image source={{ uri: item.image_url }} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
      </View>
      <View style={styles.miniBody}>
        <Text variant="caption" tone={onShell ? 'onShellMuted' : 'secondary'} numberOfLines={1}>
          {item.title}
        </Text>
        <Price paise={item.price_paise} size="sm" tone={onShell ? 'onShell' : 'default'} showDiscount={false} />
      </View>
    </PressableScale>
  );
}

// ---------- empty state ----------

export function EmptyState({ title, body, children }: { title: string; body?: string | null; children?: React.ReactNode }) {
  return (
    <View style={styles.emptyState}>
      <Text variant="display" align="center" style={{ fontSize: 30, lineHeight: 32 }}>
        {title}
      </Text>
      {body ? (
        <Text variant="body" tone="secondary" align="center">
          {body}
        </Text>
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.xl, padding: 22, gap: 18 },
  cardHead: { gap: 6 },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  gridWrap: { gap: 18 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  gridItem: { width: '47%', borderRadius: radius.lg, overflow: 'hidden', borderWidth: 3 },
  gridImage: { width: '100%', aspectRatio: 0.8 },
  gridLabel: { paddingVertical: 10, paddingHorizontal: 12 },
  section: { gap: 12 },
  offers: { borderRadius: radius.lg, overflow: 'hidden' },
  look: { borderRadius: radius.xl, padding: 20, gap: 16 },
  rail: { gap: 12, paddingRight: space.screen },
  mini: { width: 150, borderRadius: radius.lg - 4, overflow: 'hidden' },
  miniPhoto: { height: 120, overflow: 'hidden' },
  miniBody: { padding: 10, gap: 2 },
  emptyState: { paddingVertical: 48, paddingHorizontal: 12, gap: 12, alignItems: 'center' },
});
