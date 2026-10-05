import { fireEvent, render, screen } from '@testing-library/react-native';

import { ThemeProvider } from '@/design/theme';
import { snap } from '@/ui/molecules/BudgetSlider';
import { ImageChoiceGrid, StoreComparison, type OfferData } from '@/ui/organisms/Panels';
import { ProductDetailView } from '@/ui/organisms/ProductDetailView';
import { StyleDnaCard } from '@/ui/organisms/StyleDnaCard';

const inTheme = (node: React.ReactElement) => render(<ThemeProvider scheme="light">{node}</ThemeProvider>);

describe('budget snapping', () => {
  it.each([
    [123_456, 120_000],
    [125_000, 130_000], // halfway rounds up
    [-5, 0],
    [9_999_999, 500_000],
  ])('%d → %d', (raw, expected) => {
    expect(snap(raw, 0, 500_000, 10_000)).toBe(expected);
  });

  it('never steps past the top when the range is not a multiple of the step', () => {
    expect(snap(495_000, 0, 495_000, 10_000)).toBe(495_000);
  });
});

const offer = (o: Partial<OfferData>): OfferData => ({
  offer_id: 'o',
  store_name: 'Myntra',
  price_paise: 79_900,
  in_stock: true,
  is_best: false,
  buy_path: '/v1/out/o',
  ...o,
});

describe('store comparison', () => {
  it('names the best price for screen readers and buys from the tapped store', async () => {
    const onBuy = jest.fn();
    await inTheme(
      <StoreComparison
        offers={[
          offer({ offer_id: 'a', store_name: 'Amazon', price_paise: 74_900, is_best: true }),
          offer({ offer_id: 'f', store_name: 'Flipkart', price_paise: 82_900 }),
        ]}
        onBuy={onBuy}
      />,
    );

    expect(screen.getByLabelText('Amazon, ₹749, best price')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Flipkart, ₹829'));

    expect(onBuy).toHaveBeenCalledWith(expect.objectContaining({ offer_id: 'f' }));
  });

  it('cannot buy a sold-out offer', async () => {
    const onBuy = jest.fn();
    await inTheme(<StoreComparison offers={[offer({ in_stock: false })]} onBuy={onBuy} />);

    await fireEvent.press(screen.getByLabelText('Myntra, sold out'));

    expect(onBuy).not.toHaveBeenCalled();
  });
});

describe('style DNA grid', () => {
  const options = ['minimal', 'street', 'ethnic'].map((id) => ({ id, label: id, image_url: `https://img/${id}.png` }));

  it('caps the picks and submits them in order', async () => {
    const onSubmit = jest.fn();
    await inTheme(<ImageChoiceGrid question="Pick looks you love" options={options} maxSelect={2} onSubmit={onSubmit} />);

    expect(screen.getByText('Pick up to 2')).toBeTruthy();
    for (const id of ['street', 'minimal', 'ethnic']) await fireEvent.press(screen.getByLabelText(id));
    await fireEvent.press(screen.getByText('Continue with 2'));

    expect(onSubmit).toHaveBeenCalledWith(['street', 'minimal']);
  });

  it('a second tap removes a pick', async () => {
    const onSubmit = jest.fn();
    await inTheme(<ImageChoiceGrid question="Q" options={options} maxSelect={2} onSubmit={onSubmit} />);

    await fireEvent.press(screen.getByLabelText('street'));
    await fireEvent.press(screen.getByLabelText('street'));

    expect(screen.getByText('Pick up to 2')).toBeTruthy();
  });
});

describe('product detail', () => {
  it('shows price, rating, facts and sizes, and survives missing photos', async () => {
    await inTheme(
      <ProductDetailView
        detail={{
          title: 'Linen shirt',
          brand: 'Kalaa',
          price_paise: 129_900,
          mrp_paise: 199_900,
          rating: 4.26,
          rating_count: 812,
          facts: ['Linen', 'Relaxed fit'],
          sizes: ['S', 'M', 'L'],
        }}
      />,
    );

    expect(screen.getByText('Linen shirt')).toBeTruthy();
    expect(screen.getByText('4.3 · 812')).toBeTruthy();
    expect(screen.getByText('Relaxed fit')).toBeTruthy();
    expect(screen.getByText('M')).toBeTruthy();
  });

  it('labels each photo with its position', async () => {
    await inTheme(<ProductDetailView detail={{ title: 'Tee', brand: 'B', price_paise: 50_000, images: ['https://a', 'https://b'] }} />);

    expect(screen.getByLabelText('Tee, photo 2 of 2')).toBeTruthy();
  });
});

describe('style DNA card', () => {
  const options = {
    styles: [{ id: 'minimal', label: 'Clean minimal', image_url: 'https://img/minimal.png' }],
    max_styles: 3,
    top_sizes: [],
    bottom_sizes: [],
    shoe_sizes: [],
  };
  const profile = (o: object) => ({
    fit_preference: null,
    styles: [],
    sizes: { top: null, bottom: null, shoe: null },
    onboarding_done: false,
    swipe_count: 0,
    top_tags: [],
    ...o,
  });

  it('invites someone without a Style DNA to start', async () => {
    const onStart = jest.fn();
    await inTheme(<StyleDnaCard profile={profile({})} options={options} onStart={onStart} />);

    await fireEvent.press(screen.getByText('Find my Style DNA'));

    expect(onStart).toHaveBeenCalled();
  });

  it('shows chosen looks by name, sizes, and what swipes taught it', async () => {
    await inTheme(
      <StyleDnaCard
        profile={profile({
          onboarding_done: true,
          styles: ['minimal', 'retired-style'],
          fit_preference: 'women',
          sizes: { top: 'M', bottom: '30', shoe: null },
          swipe_count: 1,
          top_tags: ['linen'],
        })}
        options={options}
        onStart={jest.fn()}
      />,
    );

    expect(screen.getByLabelText('Look you love: Clean minimal')).toBeTruthy();
    expect(screen.getByLabelText('Look you love: retired-style')).toBeTruthy(); // unknown id still shown
    expect(screen.getByText('1 swipe has taught your stylist so far')).toBeTruthy();
    expect(screen.getByText('For Women')).toBeTruthy();
    expect(screen.getByText('Top M')).toBeTruthy();
    expect(screen.queryByText(/^Shoe/)).toBeNull();
    expect(screen.getByText('linen')).toBeTruthy();
    expect(screen.getByText('Retake Style DNA')).toBeTruthy();
  });
});
