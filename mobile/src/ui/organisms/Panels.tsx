/** Smaller organisms the stylist sends: questions, comparisons, looks, carousels, notices. */
import * as Haptics from 'expo-haptics';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';

import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { formatRupees } from '@/lib/money';
import { Button } from '@/ui/atoms/Button';
import { Chip } from '@/ui/atoms/Chip';
import { Icon } from '@/ui/atoms/Icon';
import { PressableScale } from '@/ui/atoms/PressableScale';
import { Price } from '@/ui/atoms/Price';
import { Text } from '@/ui/atoms/Text';
import { OptionTile } from '@/ui/molecules/OptionTile';
import { StoreOfferRow } from '@/ui/molecules/StoreOfferRow';
import { enter } from '@/ui/motion';

import type { ProductCardData } from './ProductSwipeCard';

// ---------- question card ----------

const SELECT_BEAT_MS = 220;

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
    if (disabled) return;
    if (!multi) {
      setPicked([id]);
      setTimeout(() => onSubmit([id]), SELECT_BEAT_MS); // let the tile dye before moving on
      return;
    }
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < maxSelect ? [...p, id] : p));
  };
  const tiles = options.length <= 8;
  return (
    <View style={[styles.card, { backgroundColor: colors.raised }, elevation(2)]}>
      <Animated.View entering={enter.rise(0)} style={styles.cardHead}>
        {lead ? (
          <View style={[styles.lead, { backgroundColor: colors.tonal }]}>
            <Icon name="check" size={14} color={colors.onTonal} strokeWidth={2.6} />
            <Text variant="caption" tone="onTonal" numberOfLines={2} style={{ flexShrink: 1 }}>
              {lead.replace(/^Got it:\s*/, '').replace(/\.$/, '')}
            </Text>
          </View>
        ) : null}
        <Text variant="display" style={{ fontSize: 30, lineHeight: 33 }} accessibilityRole="header">
          {ask}
        </Text>
        {multi ? (
          <Text variant="bodySmall" tone="secondary">
            Pick up to {maxSelect}
          </Text>
        ) : null}
      </Animated.View>
      {tiles ? (
        <View style={styles.tileGrid}>
          {options.map((o, i) => (
            <OptionTile
              key={o.id}
              index={i + 1}
              label={o.label}
              selected={picked.includes(o.id)}
              disabled={disabled || (!multi && picked.length > 0 && !picked.includes(o.id))}
              onPress={() => toggle(o.id)}
              testID={`option-${o.id}`}
            />
          ))}
        </View>
      ) : (
        <View style={styles.options}>
          {options.map((o, i) => (
            <Animated.View key={o.id} entering={enter.rise(i + 1)}>
              <Chip label={o.label} selected={picked.includes(o.id)} disabled={disabled} onPress={() => toggle(o.id)} testID={`option-${o.id}`} />
            </Animated.View>
          ))}
        </View>
      )}
      {multi ? (
        <Button
          label={picked.length ? `Continue with ${picked.length}` : 'Pick at least one'}
          disabled={!picked.length || disabled}
          onPress={() => onSubmit(picked)}
        />
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
      <Animated.View entering={enter.rise(0)} style={{ gap: 6 }}>
        <Text variant="display" style={{ fontSize: 30, lineHeight: 33 }} accessibilityRole="header">
          {question}
        </Text>
        <Text variant="bodySmall" tone="secondary">
          {picked.length}/{maxSelect} picked
        </Text>
      </Animated.View>
      <View style={styles.grid}>
        {options.map((o, i) => {
          const on = picked.includes(o.id);
          const order = picked.indexOf(o.id) + 1;
          return (
            <Animated.View key={o.id} entering={enter.rise(i + 1)} style={styles.gridCell}>
              <PressableScale
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={o.label}
                scaleTo={0.96}
                onPress={() => {
                  void Haptics.selectionAsync();
                  setPicked((p) => (on ? p.filter((x) => x !== o.id) : p.length < maxSelect ? [...p, o.id] : p));
                }}
                style={[styles.gridItem, { borderColor: on ? colors.bestPrice : 'transparent' }]}
              >
                <Image source={{ uri: o.image_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={160} />
                <LinearGradient colors={['transparent', 'rgba(15,22,51,0.85)']} style={styles.gridScrim} pointerEvents="none" />
                {on ? <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(31,43,92,0.25)' }]} pointerEvents="none" /> : null}
                <Text variant="label" tone="onShell" numberOfLines={1} style={styles.gridLabel}>
                  {o.label}
                </Text>
                {on ? (
                  <Animated.View entering={enter.pop()} style={[styles.gridCheck, { backgroundColor: colors.bestPrice }]}>
                    <Text variant="label" style={{ color: palette.ink, fontFamily: 'AnekLatin-Bold' }}>
                      {order}
                    </Text>
                  </Animated.View>
                ) : null}
              </PressableScale>
            </Animated.View>
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
        {items.map((item, i) => (
          <MiniCard key={item.product_id} index={i} item={item} onPress={() => onOpen(item)} onShell />
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
        {items.map((item, i) => (
          <MiniCard key={item.product_id} index={i} item={item} onPress={() => onOpen(item)} />
        ))}
      </ScrollView>
    </View>
  );
}

function MiniCard({ item, onPress, onShell, index = 0 }: { item: ProductCardData; onPress(): void; onShell?: boolean; index?: number }) {
  const { colors, elevation } = useTheme();
  return (
    <Animated.View entering={enter.slide(index)}>
      <PressableScale
        onPress={onPress}
        scaleTo={0.96}
        accessibilityLabel={`${item.title}, ${item.price_paise != null ? formatRupees(item.price_paise) : 'out of stock'}`}
        style={[styles.mini, { backgroundColor: onShell ? palette.indigo700 : colors.raised }, elevation(onShell ? 0 : 2)]}
      >
        <View style={[styles.miniPhoto, { backgroundColor: onShell ? palette.indigo500 : colors.tonal }]}>
          {item.image_url ? <Image source={{ uri: item.image_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={160} /> : null}
          <LinearGradient colors={['transparent', 'rgba(15,22,51,0.7)']} style={styles.miniScrim} pointerEvents="none" />
          {item.brand ? (
            <Text variant="caption" tone="onShell" numberOfLines={1} style={styles.miniBrand}>
              {item.brand}
            </Text>
          ) : null}
        </View>
        <View style={styles.miniBody}>
          <Text variant="bodySmall" tone={onShell ? 'onShell' : 'default'} numberOfLines={2}>
            {item.title}
          </Text>
          <Price paise={item.price_paise} size="sm" tone={onShell ? 'onShell' : 'default'} showDiscount={false} />
        </View>
      </PressableScale>
    </Animated.View>
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
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 },
  gridCell: { width: '48.5%' },
  gridItem: { aspectRatio: 0.78, borderRadius: radius.lg, overflow: 'hidden', borderWidth: 3, justifyContent: 'flex-end' },
  gridScrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '45%' },
  gridLabel: { paddingVertical: 12, paddingHorizontal: 12 },
  gridCheck: { position: 'absolute', top: 10, right: 10, width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  tileGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 },
  lead: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 10, borderRadius: radius.pill, maxWidth: '100%' },
  section: { gap: 12 },
  offers: { borderRadius: radius.lg, overflow: 'hidden' },
  look: { borderRadius: radius.xl, padding: 20, gap: 16 },
  rail: { gap: 12, paddingRight: space.screen },
  mini: { width: 168, borderRadius: radius.lg, overflow: 'hidden' },
  miniPhoto: { height: 196, overflow: 'hidden', justifyContent: 'flex-end' },
  miniScrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 70 },
  miniBrand: { paddingHorizontal: 10, paddingBottom: 8 },
  miniBody: { padding: 12, gap: 4 },
  emptyState: { paddingVertical: 48, paddingHorizontal: 12, gap: 12, alignItems: 'center' },
});
