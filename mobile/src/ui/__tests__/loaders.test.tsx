import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ThemeProvider } from '@/design/theme';
import { BackButton } from '@/ui/atoms/BackButton';
import { PrintDots } from '@/ui/atoms/PrintDots';
import { OccasionTile } from '@/ui/molecules/OccasionTile';
import { PrintRepeat } from '@/ui/molecules/PrintRepeat';
import { LoadingOverlay } from '@/ui/organisms/LoadingOverlay';
import { ProductRail } from '@/ui/organisms/ProductRail';
import { SEARCH_STEPS, SearchLoader, Spinner } from '@/ui/organisms/SearchLoader';
import { Skeleton } from '@/ui/organisms/Skeleton';

const mockGet = jest.fn();
jest.mock('@/auth/session', () => ({ api: { get: (...args: unknown[]) => mockGet(...args) } }));

const inTheme = (node: React.ReactElement) => render(<ThemeProvider scheme="light">{node}</ThemeProvider>);

describe('loading states', () => {
  it('the search loader says what it is doing', async () => {
    await inTheme(<SearchLoader />);
    expect(screen.getByText(SEARCH_STEPS[0] ?? '')).toBeTruthy();
  });

  it('skeletons render for every shape as progress bars', async () => {
    for (const shape of ['cards', 'comparison', 'question'] as const) {
      await inTheme(<Skeleton shape={shape} count={2} />);
      expect(screen.toJSON()).toBeTruthy();
    }
  });

  it('the overlay shows only while visible', async () => {
    const insets = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
    const overlay = (visible: boolean) => (
      <SafeAreaProvider initialMetrics={insets}>
        <LoadingOverlay visible={visible} steps={['Reading your photo']} />
      </SafeAreaProvider>
    );
    await inTheme(overlay(false));
    expect(screen.queryByText('Reading your photo')).toBeNull();
    await inTheme(overlay(true));
    expect(screen.getByText('Reading your photo')).toBeTruthy();
  });

  it('print motifs render', async () => {
    await inTheme(
      <>
        <PrintRepeat label="Block printing" rows={2} />
        <PrintDots color="#000" />
        <Spinner />
      </>,
    );
    expect(screen.getByText('Block printing')).toBeTruthy();
  });
});

describe('controls', () => {
  it('the back button is a labelled round button', async () => {
    const onPress = jest.fn();
    await inTheme(<BackButton onPress={onPress} variant="glass" label="Close try-on" close />);
    await fireEvent.press(screen.getByLabelText('Close try-on'));
    expect(onPress).toHaveBeenCalled();
  });

  it('an occasion tile opens its occasion', async () => {
    const onPress = jest.fn();
    await inTheme(<OccasionTile title="Wedding" subtitle="Guest looks" dye="madder" hero onPress={onPress} />);
    await fireEvent.press(screen.getByText('Wedding'));
    expect(onPress).toHaveBeenCalled();
  });
});

describe('product rail', () => {
  it('asks only for priced items and shows them', async () => {
    mockGet.mockResolvedValue({
      items: [
        { id: 'p1', title: 'Linen shirt', brand: 'Roadster', primary_image_url: 'https://img/1.jpg', min_price_paise: 79_900, best_store: 'myntra' },
        { id: 'p2', title: 'No photo', brand: 'X', primary_image_url: null, min_price_paise: 10_000, best_store: 'amazon' },
      ],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await inTheme(
      <QueryClientProvider client={client}>
        <ProductRail title="Shirts for men" query={{ category: 'shirt', gender: 'men', maxPricePaise: 200_000 }} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Linen shirt')).toBeTruthy();
    expect(screen.queryByText('No photo')).toBeNull();
    const path = String(mockGet.mock.calls[0][0]);
    expect(path).toContain('min_price_paise=1');
    expect(path).toContain('category=shirt');
  });
});
