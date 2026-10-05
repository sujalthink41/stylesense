import * as Haptics from 'expo-haptics';
import * as Linking from 'expo-linking';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { API_URL } from '@/api/config';
import { api } from '@/auth/session';
import { useWishlist } from '@/boards/wishlist';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { timers } from '@/lib/perf';
import { Badge } from '@/ui/atoms/Badge';
import { Button } from '@/ui/atoms/Button';
import { Chip } from '@/ui/atoms/Chip';
import { Text } from '@/ui/atoms/Text';
import { AskField } from '@/ui/molecules/AskField';
import { Banner } from '@/ui/molecules/Banner';
import { BudgetSlider } from '@/ui/molecules/BudgetSlider';
import { BuyBar } from '@/ui/molecules/BuyBar';
import { SaveHeart } from '@/ui/molecules/SaveHeart';
import {
  EmptyState,
  ImageChoiceGrid,
  LookPanel,
  ProductCarousel,
  QuestionCard,
  StoreComparison,
} from '@/ui/organisms/Panels';
import { ProductDetailView } from '@/ui/organisms/ProductDetailView';
import { ProductSwipeCard, type ProductCardData } from '@/ui/organisms/ProductSwipeCard';
import { Skeleton } from '@/ui/organisms/Skeleton';
import { SwipeDeck, type SwipeDirection } from '@/ui/organisms/SwipeDeck';

import type { Action, GenUIComponent, GenUIContext, UiEnvelope } from './types';

const UPDATE_PROMPT = 'Update StyleSense to see this.';

/**
 * Draws one server-sent screen. The server decides WHAT to show (ADR 0011); this decides HOW.
 * Text inputs dock at the bottom; everything else stacks in order.
 */
export function GenUIScreen({ envelope, ctx, header }: { envelope: UiEnvelope; ctx: GenUIContext; header?: ReactNode }) {
  const body = envelope.components.filter((c) => c.type !== 'text_input_bar');
  const composer = envelope.components.find((c) => c.type === 'text_input_bar');
  const buy = bestOffer(envelope.components);
  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {header}
        {body.map((c) => (
          <View key={`${envelope.turn_id}:${c.id}`}>{renderComponent(c, ctx)}</View>
        ))}
      </ScrollView>
      {composer ? <View style={styles.composer}>{renderComponent(composer, ctx)}</View> : null}
      {buy ? (
        <BuyBar storeName={buy.offer.store_name} pricePaise={buy.offer.price_paise} isBest={buy.compared} onBuy={() => openOffer(buy.offer.buy_path, 'detail')} />
      ) : null}
    </View>
  );
}

export function renderComponent(c: GenUIComponent, ctx: GenUIContext): ReactNode {
  switch (c.type) {
    case 'chip_question':
      return (
        <QuestionCard
          question={c.props.question}
          options={c.props.options.map((o) => ({ id: o.id, label: o.label }))}
          multi={c.props.multi ?? false}
          maxSelect={c.props.max_select ?? 1}
          disabled={ctx.busy}
          onSubmit={(ids) => ctx.dispatch({ type: 'chip_select', component_id: c.id, option_ids: ids })}
        />
      );
    case 'image_choice_grid':
      return (
        <ImageChoiceGrid
          question={c.props.question}
          options={c.props.options}
          maxSelect={c.props.max_select ?? 1}
          disabled={ctx.busy}
          onSubmit={(ids) => ctx.dispatch({ type: 'chip_select', component_id: c.id, option_ids: ids })}
        />
      );
    case 'budget_slider':
      return <BudgetQuestion component={c} ctx={ctx} />;
    case 'product_card':
      return (
        <ProductSwipeCard card={c.props as ProductCardData} imageHeight={300} />
      );
    case 'product_swipe_deck':
      // Keyed by turn: a new deck from the server starts fresh, a refill only extends it.
      return <DeckAdapter key={`${c.id}:${ctx.turnId}`} component={c} ctx={ctx} />;
    case 'store_comparison':
      return (
        <StoreComparison
          offers={c.props.offers}
          onBuy={(o) => openOffer(o.buy_path, 'stylist')}
        />
      );
    case 'complete_the_look':
      return (
        <LookPanel
          title={c.props.title}
          items={c.props.items as ProductCardData[]}
          remainingPaise={c.props.remaining_budget_paise}
          onOpen={(item) => ctx.dispatch({ type: 'card_open', component_id: c.id, product_id: item.product_id })}
        />
      );
    case 'product_detail':
      return <ProductDetailView detail={c.props} accessory={<WishlistHeart productId={c.props.product_id} />} />;
    case 'product_carousel':
      return (
        <ProductCarousel
          title={c.props.title}
          items={c.props.items as ProductCardData[]}
          onOpen={(item) => ctx.dispatch({ type: 'card_open', component_id: c.id, product_id: item.product_id })}
        />
      );
    case 'suggestion_bar':
      return (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestions}>
          {c.props.suggestions.map((s) => (
            <Chip key={s.id} label={s.label} disabled={ctx.busy} onPress={() => ctx.dispatch(s.action as Action)} />
          ))}
        </ScrollView>
      );
    case 'info_banner':
      return <Banner text={c.props.text} tone={c.props.tone ?? 'info'} />;
    case 'empty_state':
      return (
        <EmptyState title={c.props.title} body={c.props.body}>
          <View style={styles.suggestions}>
            {(c.props.recovery ?? []).map((s) => (
              <Chip key={s.id} label={s.label} disabled={ctx.busy} onPress={() => ctx.dispatch(s.action as Action)} />
            ))}
          </View>
        </EmptyState>
      );
    case 'text_input_bar':
      return (
        <AskField
          surface="ground"
          placeholder={c.props.placeholder ?? 'Tell the stylist more'}
          disabled={ctx.busy}
          onSubmit={(text) => ctx.dispatch({ type: 'text_input', text })}
        />
      );
    case 'loading_skeleton':
      return <Skeleton shape={c.props.shape} count={c.props.count} />;
    default:
      return <Banner text={UPDATE_PROMPT} />; // a newer component than this app knows
  }
}

/** The lowest in-stock offer on a detail screen, for the docked buy bar. */
function bestOffer(components: GenUIComponent[]) {
  const comparison = components.find((c) => c.type === 'store_comparison');
  if (comparison?.type !== 'store_comparison') return null;
  const inStock = comparison.props.offers.filter((o) => o.in_stock);
  const offer = inStock.find((o) => o.is_best) ?? [...inStock].sort((a, b) => a.price_paise - b.price_paise)[0];
  return offer ? { offer, compared: inStock.length > 1 } : null;
}

function openOffer(buyPath: string, src: string) {
  // The redirect endpoint records the click and only goes to allow-listed store hosts.
  void Linking.openURL(`${API_URL}${buyPath}?src=${src}`);
}

function WishlistHeart({ productId }: { productId: string }) {
  const { ready, isSaved, toggle } = useWishlist();
  const onToggle = async () => {
    // The heart already flipped back; a buzz says the save didn't stick.
    if (!(await toggle(productId))) void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
  };
  return <SaveHeart saved={isSaved(productId)} disabled={!ready} onToggle={() => void onToggle()} />;
}

function BudgetQuestion({ component, ctx }: { component: Extract<GenUIComponent, { type?: 'budget_slider' }>; ctx: GenUIContext }) {
  const p = component.props;
  const [value, setValue] = useState(p.default_max_paise);
  return (
    <View style={styles.stack}>
      <BudgetSlider label={p.label} minPaise={p.min_paise} maxPaise={p.max_paise} stepPaise={p.step_paise} value={value} onChange={setValue} />
      <Button
        label="Show my picks"
        loading={ctx.busy}
        onPress={() =>
          ctx.dispatch({ type: 'slider_set', component_id: component.id, min_paise: p.default_min_paise, max_paise: value })
        }
      />
    </View>
  );
}

/** The deck lives on the phone: swipes are recorded straight away (ADR 0013), not as turns. */
function DeckAdapter({ component, ctx }: { component: Extract<GenUIComponent, { type?: 'product_swipe_deck' }>; ctx: GenUIContext }) {
  const { colors } = useTheme();
  const [cards, setCards] = useState<ProductCardData[]>(component.props.cards as ProductCardData[]);
  const [hasMore, setHasMore] = useState(component.props.has_more ?? false);
  useEffect(() => void timers.end('first_products'), []);

  const onSwipe = useCallback(
    (card: ProductCardData, direction: SwipeDirection) => {
      void api
        .post('/v1/me/swipes', { product_id: card.product_id, direction, session_id: ctx.sessionId })
        .catch(() => undefined); // taste learning is best effort; the deck never waits on it
    },
    [ctx.sessionId],
  );

  const onRunningLow = useCallback(() => {
    if (!hasMore) return;
    const exclude = cards.map((c) => `exclude=${c.product_id}`).slice(-50).join('&');
    void api
      .get<{ cards: ProductCardData[]; has_more: boolean }>(`/v1/stylist/sessions/${ctx.sessionId}/deck?limit=10&${exclude}`)
      .then((page) => {
        setCards((prev) => [...prev, ...page.cards.filter((n) => !prev.some((p) => p.product_id === n.product_id))]);
        setHasMore(page.has_more);
      })
      .catch(() => setHasMore(false));
  }, [cards, hasMore, ctx.sessionId]);

  return (
    <View style={styles.stack}>
      {component.props.title ? (
        <View style={styles.deckHead}>
          <Text variant="headline" accessibilityRole="header" style={{ flex: 1 }}>
            {component.props.title}
          </Text>
          <Badge kind="neutral" label={`${cards.length} picks`} />
        </View>
      ) : null}
      <SwipeDeck
        cards={cards}
        onSwipe={onSwipe}
        onRunningLow={onRunningLow}
        onOpen={(card) => ctx.dispatch({ type: 'card_open', component_id: component.id, product_id: card.product_id })}
      />
      <View style={{ height: 1, backgroundColor: colors.hairline }} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: space.screen, gap: space.lg, paddingBottom: 120 },
  composer: { paddingHorizontal: space.screen, paddingBottom: space.md, paddingTop: space.xs },
  suggestions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  stack: { gap: space.md },
  deckHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
});
