/* Generated from backend/contracts/genui.schema.json by scripts/gen-genui.mjs.
 * Do not edit by hand: run `npm run gen` (or `make contracts`). */
export const GENUI_CATALOG_VERSION = 2;

export type Action =
  ChipSelect | SliderSet | Swipe | CardOpen | TextInput | Shortcut | Back | Restart;
export type ComponentId = string;
/**
 * @minItems 1
 * @maxItems 12
 */
export type OptionIds = string[];
export type Type = 'chip_select';
export type ComponentId1 = string;
export type MaxPaise = number;
export type MinPaise = number;
export type Type1 = 'slider_set';
export type ComponentId2 = string;
export type Direction = 'left' | 'right' | 'super';
export type ProductId = string;
export type Type2 = 'swipe';
export type ComponentId3 = string;
export type ProductId1 = string;
export type Type3 = 'card_open';
export type Text = string;
export type Type4 = 'text_input';
export type Type5 = 'shortcut';
export type Value = string;
export type Type6 = 'back';
export type Type7 = 'restart';
export type TurnId = number;
export type Id = string;
export type AllowCustom = boolean;
export type MaxSelect = number;
export type Multi = boolean;
export type Icon = string | null;
export type Id1 = string;
export type Label = string;
/**
 * @minItems 2
 * @maxItems 12
 */
export type Options = ChipOption[];
export type Question = string;
export type Type8 = 'chip_question';
export type V = 1;
export type Id2 = string;
export type DefaultMaxPaise = number;
export type DefaultMinPaise = number;
export type Label1 = string;
export type MaxPaise1 = number;
export type MinPaise1 = number;
export type StepPaise = number;
export type Type9 = 'budget_slider';
export type V1 = 1;
export type Id3 = string;
export type MaxSelect1 = number;
export type Id4 = string;
export type ImageUrl = string;
export type Label2 = string;
/**
 * @minItems 2
 * @maxItems 12
 */
export type Options1 = ImageChoice[];
export type Question1 = string;
export type Type10 = 'image_choice_grid';
export type V2 = 1;
export type Id5 = string;
export type BestStore = string | null;
export type Brand = string;
export type ImageUrl1 = string | null;
export type PricePaise = number | null;
export type ProductId2 = string;
export type Rating = number | null;
export type RatingCount = number;
/**
 * @maxItems 3
 */
export type Reasons = string[];
export type Title = string;
export type Type11 = 'product_card';
export type V3 = 1;
export type Id6 = string;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Cards = ProductCardProps[];
export type HasMore = boolean;
export type Title1 = string | null;
export type Type12 = 'product_swipe_deck';
export type V4 = 1;
export type Id7 = string;
export type BuyPath = string;
export type DiscountPercent = number;
export type InStock = boolean;
export type IsBest = boolean;
export type MrpPaise = number | null;
export type OfferId = string;
export type PricePaise1 = number;
export type Store = string;
export type StoreName = string;
/**
 * @minItems 1
 * @maxItems 10
 */
export type Offers = ComparedOffer[];
export type ProductId3 = string;
export type Title2 = string;
export type Type13 = 'store_comparison';
export type V5 = 1;
export type Id8 = string;
export type AnchorProductId = string;
/**
 * @minItems 1
 * @maxItems 10
 */
export type Items = ProductCardProps[];
export type RemainingBudgetPaise = number | null;
export type Title3 = string;
export type Type14 = 'complete_the_look';
export type V6 = 1;
export type Id9 = string;
export type Brand1 = string;
/**
 * @maxItems 10
 */
export type Colors = string[];
/**
 * @maxItems 8
 */
export type Facts = string[];
/**
 * @maxItems 8
 */
export type Images = string[];
export type MrpPaise1 = number | null;
export type PricePaise2 = number | null;
export type ProductId4 = string;
export type Rating1 = number | null;
export type RatingCount1 = number;
/**
 * @maxItems 3
 */
export type Reasons1 = string[];
/**
 * @maxItems 20
 */
export type Sizes = string[];
export type Title4 = string;
export type Type15 = 'product_detail';
export type V7 = 1;
export type Id10 = string;
/**
 * @minItems 1
 * @maxItems 10
 */
export type Items1 = ProductCardProps[];
export type Title5 = string;
export type Type16 = 'product_carousel';
export type V8 = 1;
export type Id11 = string;
export type Action1 =
  ChipSelect | SliderSet | Swipe | CardOpen | TextInput | Shortcut | Back | Restart;
export type Id12 = string;
export type Label3 = string;
/**
 * @minItems 1
 * @maxItems 6
 */
export type Suggestions = Suggestion[];
export type Type17 = 'suggestion_bar';
export type V9 = 1;
export type Id13 = string;
export type Text1 = string;
export type Tone = 'info' | 'success' | 'warning';
export type Type18 = 'info_banner';
export type V10 = 1;
export type Id14 = string;
export type Body = string;
/**
 * @maxItems 4
 */
export type Recovery = Suggestion[];
export type Title6 = string;
export type Type19 = 'empty_state';
export type V11 = 1;
export type Id15 = string;
export type AllowPhoto = boolean;
export type Placeholder = string;
export type Type20 = 'text_input_bar';
export type V12 = 1;
export type Id16 = string;
export type Count = number;
export type Shape = 'cards' | 'question' | 'comparison';
export type Type21 = 'loading_skeleton';
export type V13 = 1;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Components = (
  | ChipQuestion
  | BudgetSlider
  | ImageChoiceGrid
  | ProductCard
  | ProductSwipeDeck
  | StoreComparison
  | CompleteTheLook
  | ProductDetail
  | ProductCarousel
  | SuggestionBar
  | InfoBanner
  | EmptyState
  | TextInputBar
  | LoadingSkeleton
)[];
export type Mode = 'replace' | 'append';
export type SessionId = string;
export type TurnId1 = number;
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "event".
 */
export type Event = RenderEvent | LoadingEvent | ErrorEvent | DoneEvent;
export type Event1 = 'ui.render';
/**
 * @minItems 1
 * @maxItems 5
 */
export type Components1 = (
  | ChipQuestion
  | BudgetSlider
  | ImageChoiceGrid
  | ProductCard
  | ProductSwipeDeck
  | StoreComparison
  | CompleteTheLook
  | ProductDetail
  | ProductCarousel
  | SuggestionBar
  | InfoBanner
  | EmptyState
  | TextInputBar
  | LoadingSkeleton
)[];
export type Event2 = 'ui.loading';
export type TurnId2 = number;
export type Event3 = 'error';
export type Event4 = 'done';
export type TurnId3 = number;

export interface GenUIContract {
  action_request: ActionRequest;
  envelope: UiEnvelope;
  event: Event;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ActionRequest".
 */
export interface ActionRequest {
  action: Action;
  turn_id: TurnId;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ChipSelect".
 */
export interface ChipSelect {
  component_id: ComponentId;
  option_ids: OptionIds;
  type?: Type;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "SliderSet".
 */
export interface SliderSet {
  component_id: ComponentId1;
  max_paise: MaxPaise;
  min_paise: MinPaise;
  type?: Type1;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "Swipe".
 */
export interface Swipe {
  component_id: ComponentId2;
  direction: Direction;
  product_id: ProductId;
  type?: Type2;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "CardOpen".
 */
export interface CardOpen {
  component_id: ComponentId3;
  product_id: ProductId1;
  type?: Type3;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "TextInput".
 */
export interface TextInput {
  text: Text;
  type?: Type4;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "Shortcut".
 */
export interface Shortcut {
  type?: Type5;
  value: Value;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "Back".
 */
export interface Back {
  type?: Type6;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "Restart".
 */
export interface Restart {
  type?: Type7;
}
/**
 * One turn's UI. `turn_id` is what the app must echo back with its next action.
 *
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "UiEnvelope".
 */
export interface UiEnvelope {
  components: Components;
  mode?: Mode;
  session_id: SessionId;
  turn_id: TurnId1;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ChipQuestion".
 */
export interface ChipQuestion {
  id: Id;
  props: ChipQuestionProps;
  type?: Type8;
  v?: V;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ChipQuestionProps".
 */
export interface ChipQuestionProps {
  allow_custom?: AllowCustom;
  max_select?: MaxSelect;
  multi?: Multi;
  options: Options;
  question: Question;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ChipOption".
 */
export interface ChipOption {
  icon?: Icon;
  id: Id1;
  label: Label;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "BudgetSlider".
 */
export interface BudgetSlider {
  id: Id2;
  props: BudgetSliderProps;
  type?: Type9;
  v?: V1;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "BudgetSliderProps".
 */
export interface BudgetSliderProps {
  default_max_paise: DefaultMaxPaise;
  default_min_paise: DefaultMinPaise;
  label: Label1;
  max_paise: MaxPaise1;
  min_paise: MinPaise1;
  step_paise: StepPaise;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ImageChoiceGrid".
 */
export interface ImageChoiceGrid {
  id: Id3;
  props: ImageChoiceGridProps;
  type?: Type10;
  v?: V2;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ImageChoiceGridProps".
 */
export interface ImageChoiceGridProps {
  max_select?: MaxSelect1;
  options: Options1;
  question: Question1;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ImageChoice".
 */
export interface ImageChoice {
  id: Id4;
  image_url: ImageUrl;
  label: Label2;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductCard".
 */
export interface ProductCard {
  id: Id5;
  props: ProductCardProps;
  type?: Type11;
  v?: V3;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductCardProps".
 */
export interface ProductCardProps {
  best_store?: BestStore;
  brand: Brand;
  image_url?: ImageUrl1;
  price_paise: PricePaise;
  product_id: ProductId2;
  rating?: Rating;
  rating_count?: RatingCount;
  reasons?: Reasons;
  title: Title;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductSwipeDeck".
 */
export interface ProductSwipeDeck {
  id: Id6;
  props: ProductSwipeDeckProps;
  type?: Type12;
  v?: V4;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductSwipeDeckProps".
 */
export interface ProductSwipeDeckProps {
  cards: Cards;
  has_more?: HasMore;
  title?: Title1;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "StoreComparison".
 */
export interface StoreComparison {
  id: Id7;
  props: StoreComparisonProps;
  type?: Type13;
  v?: V5;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "StoreComparisonProps".
 */
export interface StoreComparisonProps {
  offers: Offers;
  product_id: ProductId3;
  title: Title2;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ComparedOffer".
 */
export interface ComparedOffer {
  buy_path: BuyPath;
  discount_percent: DiscountPercent;
  in_stock: InStock;
  is_best: IsBest;
  mrp_paise: MrpPaise;
  offer_id: OfferId;
  price_paise: PricePaise1;
  store: Store;
  store_name: StoreName;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "CompleteTheLook".
 */
export interface CompleteTheLook {
  id: Id8;
  props: CompleteTheLookProps;
  type?: Type14;
  v?: V6;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "CompleteTheLookProps".
 */
export interface CompleteTheLookProps {
  anchor_product_id: AnchorProductId;
  items: Items;
  remaining_budget_paise?: RemainingBudgetPaise;
  title: Title3;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductDetail".
 */
export interface ProductDetail {
  id: Id9;
  props: ProductDetailProps;
  type?: Type15;
  v?: V7;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductDetailProps".
 */
export interface ProductDetailProps {
  brand: Brand1;
  colors?: Colors;
  facts?: Facts;
  images?: Images;
  mrp_paise?: MrpPaise1;
  price_paise: PricePaise2;
  product_id: ProductId4;
  rating?: Rating1;
  rating_count?: RatingCount1;
  reasons?: Reasons1;
  sizes?: Sizes;
  title: Title4;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductCarousel".
 */
export interface ProductCarousel {
  id: Id10;
  props: ProductCarouselProps;
  type?: Type16;
  v?: V8;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ProductCarouselProps".
 */
export interface ProductCarouselProps {
  items: Items1;
  title: Title5;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "SuggestionBar".
 */
export interface SuggestionBar {
  id: Id11;
  props: SuggestionBarProps;
  type?: Type17;
  v?: V9;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "SuggestionBarProps".
 */
export interface SuggestionBarProps {
  suggestions: Suggestions;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "Suggestion".
 */
export interface Suggestion {
  action: Action1;
  id: Id12;
  label: Label3;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "InfoBanner".
 */
export interface InfoBanner {
  id: Id13;
  props: InfoBannerProps;
  type?: Type18;
  v?: V10;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "InfoBannerProps".
 */
export interface InfoBannerProps {
  text: Text1;
  tone?: Tone;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "EmptyState".
 */
export interface EmptyState {
  id: Id14;
  props: EmptyStateProps;
  type?: Type19;
  v?: V11;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "EmptyStateProps".
 */
export interface EmptyStateProps {
  body?: Body;
  recovery?: Recovery;
  title: Title6;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "TextInputBar".
 */
export interface TextInputBar {
  id: Id15;
  props: TextInputBarProps;
  type?: Type20;
  v?: V12;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "TextInputBarProps".
 */
export interface TextInputBarProps {
  allow_photo?: AllowPhoto;
  placeholder?: Placeholder;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "LoadingSkeleton".
 */
export interface LoadingSkeleton {
  id: Id16;
  props: LoadingSkeletonProps;
  type?: Type21;
  v?: V13;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "LoadingSkeletonProps".
 */
export interface LoadingSkeletonProps {
  count?: Count;
  shape: Shape;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "RenderEvent".
 */
export interface RenderEvent {
  envelope: UiEnvelope;
  event?: Event1;
}
/**
 * Skeletons to show while the turn is being computed (e.g. waiting on AI).
 *
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "LoadingEvent".
 */
export interface LoadingEvent {
  components: Components1;
  event?: Event2;
  turn_id: TurnId2;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "ErrorEvent".
 */
export interface ErrorEvent {
  event?: Event3;
  problem: Problem;
}
export interface Problem {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `GenUIContract`'s JSON-Schema
 * via the `definition` "DoneEvent".
 */
export interface DoneEvent {
  event?: Event4;
  turn_id: TurnId3;
}
