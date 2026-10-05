import { fireEvent, render, screen } from '@testing-library/react-native';

import { ThemeProvider } from '@/design/theme';

import { GenUIScreen } from '../Renderer';
import type { GenUIContext, UiEnvelope } from '../types';

jest.mock('@/auth/session', () => ({ api: { post: jest.fn(async () => ({ recorded: true })), get: jest.fn() } }));

async function draw(components: unknown[], overrides: Partial<GenUIContext> = {}) {
  const dispatch = jest.fn();
  const envelope = { session_id: 's1', turn_id: 3, components } as unknown as UiEnvelope;
  const ctx: GenUIContext = { sessionId: 's1', turnId: 3, busy: false, dispatch, ...overrides };
  await render(
    <ThemeProvider scheme="light">
      <GenUIScreen envelope={envelope} ctx={ctx} />
    </ThemeProvider>,
  );
  return dispatch;
}

const question = {
  id: 'q_gender',
  type: 'chip_question',
  props: {
    question: 'Got it: summer t-shirts. Who is it for?',
    options: [
      { id: 'men', label: 'Men' },
      { id: 'women', label: 'Women' },
    ],
  },
};

describe('GenUI renderer', () => {
  it('splits the stylist lead from its question and sends the tapped option', async () => {
    const dispatch = await draw([question]);

    expect(screen.getByText('Got it: summer t-shirts.')).toBeTruthy();
    expect(screen.getByText('Who is it for?')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('option-women'));

    expect(dispatch).toHaveBeenCalledWith({ type: 'chip_select', component_id: 'q_gender', option_ids: ['women'] });
  });

  it('replaces a component it does not know with an update prompt', async () => {
    await draw([{ id: 'tryon', type: 'tryon_result', props: {} }]);

    expect(screen.getByText('Update StyleSense to see this.')).toBeTruthy();
  });

  it('sends the slider value with its id', async () => {
    const dispatch = await draw([
      {
        id: 'q_budget',
        type: 'budget_slider',
        props: { label: "What's your budget?", min_paise: 0, max_paise: 500_000, step_paise: 10_000, default_min_paise: 0, default_max_paise: 150_000 },
      },
    ]);

    await fireEvent.press(screen.getByText('Show my picks'));

    expect(dispatch).toHaveBeenCalledWith({ type: 'slider_set', component_id: 'q_budget', min_paise: 0, max_paise: 150_000 });
  });

  it('sends typed text from the composer', async () => {
    const dispatch = await draw([{ id: 'ask', type: 'text_input_bar', props: { placeholder: 'Refine' } }]);

    await fireEvent.changeText(screen.getByLabelText('Ask the stylist'), 'only cotton');
    await fireEvent(screen.getByLabelText('Ask the stylist'), 'submitEditing');

    expect(dispatch).toHaveBeenCalledWith({ type: 'text_input', text: 'only cotton' });
  });

  it('runs suggestion actions verbatim', async () => {
    const dispatch = await draw([
      { id: 'next', type: 'suggestion_bar', props: { suggestions: [{ id: 'restart', label: 'Start over', action: { type: 'restart' } }] } },
    ]);

    await fireEvent.press(screen.getByText('Start over'));

    expect(dispatch).toHaveBeenCalledWith({ type: 'restart' });
  });

  it('opens a card from the deck and records swipes without a turn', async () => {
    const { api } = jest.requireMock('@/auth/session') as { api: { post: jest.Mock } };
    const dispatch = await draw([
      {
        id: 'deck',
        type: 'product_swipe_deck',
        props: {
          title: 'Summer t-shirts',
          has_more: false,
          cards: [
            { product_id: 'p1', title: 'Striped tee', brand: 'Street Theory', price_paise: 64_900, reasons: ['Within ₹800'] },
            { product_id: 'p2', title: 'Linen tee', brand: 'Kalaa', price_paise: 79_900 },
          ],
        },
      },
    ]);

    await fireEvent.press(screen.getByLabelText('Striped tee. Opens details'));
    expect(dispatch).toHaveBeenCalledWith({ type: 'card_open', component_id: 'deck', product_id: 'p1' });

    await fireEvent.press(screen.getByTestId('deck-skip'));
    expect(api.post).toHaveBeenCalledWith('/v1/me/swipes', { product_id: 'p1', direction: 'left', session_id: 's1' });
    expect(dispatch).toHaveBeenCalledTimes(1); // the swipe never became a turn
  });

  it('a refill extends the deck without replaying cards already swiped', async () => {
    const { api } = jest.requireMock('@/auth/session') as { api: { get: jest.Mock } };
    api.get.mockResolvedValueOnce({ cards: [{ product_id: 'p4', title: 'Kurta', brand: 'Kalaa', price_paise: 99_900 }], has_more: false });
    await draw([
      {
        id: 'deck',
        type: 'product_swipe_deck',
        props: {
          title: 'Tees',
          has_more: true,
          cards: ['p1', 'p2', 'p3'].map((id) => ({ product_id: id, title: `Tee ${id}`, brand: 'B', price_paise: 50_000 })),
        },
      },
    ]);

    await fireEvent.press(screen.getByTestId('deck-skip'));

    expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/v1/stylist/sessions/s1/deck?limit=10&exclude=p1'));
    expect(await screen.findByText('3 picks left')).toBeTruthy();
    expect(screen.getByLabelText('Tee p2. Opens details')).toBeTruthy();
  });

  it('disables taps while a turn is in flight', async () => {
    const dispatch = await draw([question], { busy: true });

    await fireEvent.press(screen.getByTestId('option-men'));

    expect(dispatch).not.toHaveBeenCalled();
  });
});
