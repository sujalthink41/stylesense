import { ApiClient } from '@/api/client';
import { timers } from '@/lib/perf';

import { createStylistStore } from '../store';

const UI = (turn: number) => ({ session_id: 's1', turn_id: turn, components: [{ id: 'notice', type: 'info_banner', props: { text: `turn ${turn}` } }] });
const VIEW = (turn: number) => ({ session_id: 's1', turn_id: turn, status: 'active', ui: UI(turn) });

function respond(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

function setup(handler: (method: string, path: string, body: unknown) => Response) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const api = new ApiClient({
    baseUrl: 'https://api.test',
    genuiVersion: 2,
    appVersion: '0.1.0',
    tokens: { accessToken: () => 't', refresh: async () => false },
    fetchImpl: (async (url: string, init: RequestInit) => {
      const path = url.replace('https://api.test', '');
      const body = init.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method: String(init.method), path, body });
      return handler(String(init.method), path, body);
    }) as unknown as typeof fetch,
  });
  const store = createStylistStore(api, async () => undefined);
  return { store, calls };
}

const tap = { type: 'chip_select' as const, component_id: 'q_gender', option_ids: ['men'] };

describe('stylist store', () => {
  it('starts a session and trims the request', async () => {
    const { store, calls } = setup(() => respond(201, VIEW(1)));

    const id = await store.getState().start('search', '  linen shirt  ');

    expect(id).toBe('s1');
    expect(calls[0]!.body).toEqual({ entry: 'search', value: 'linen shirt' });
    expect(store.getState().session?.turn_id).toBe(1);
  });

  it('acts on the current turn and adopts the next screen', async () => {
    const { store, calls } = setup((m) => (m === 'POST' && calls.length === 1 ? respond(201, VIEW(1)) : respond(200, { turn_id: 2, ui: UI(2), error: null })));
    await store.getState().start('search', 'tee');

    await store.getState().act(tap);

    expect(calls[1]!.body).toEqual({ turn_id: 1, action: tap });
    expect(store.getState().session?.turn_id).toBe(2);
    expect(store.getState().phase).toBe('idle');
  });

  it('a stale turn catches up from the snapshot instead of showing an error', async () => {
    const { store } = setup((m, path) => {
      if (m === 'GET') return respond(200, VIEW(5));
      if (path.endsWith('/actions')) return respond(409, { code: 'stale_turn', current_turn: 5 });
      return respond(201, VIEW(1));
    });
    await store.getState().start('search', 'tee');

    await store.getState().act(tap);

    expect(store.getState().session?.turn_id).toBe(5);
    expect(store.getState().error).toBeNull();
  });

  it('restarts the products timer on every tap, so reading time never counts', async () => {
    const started = jest.spyOn(timers, 'start');
    const { store } = setup((m) => (m === 'POST' ? respond(200, { turn_id: 2, ui: UI(2) }) : respond(200, VIEW(1))));
    await store.getState().start('search', 'tee');
    await store.getState().act(tap);

    expect(started.mock.calls).toEqual([['tap_to_products'], ['tap_to_products']]);
    started.mockRestore();
  });

  it('retries once when the session is busy', async () => {
    let attempts = 0;
    const { store } = setup((_, path) => {
      if (!path.endsWith('/actions')) return respond(201, VIEW(1));
      attempts++;
      return attempts === 1 ? respond(409, { code: 'session_busy' }) : respond(200, { turn_id: 2, ui: UI(2) });
    });
    await store.getState().start('search', 'tee');

    await store.getState().act(tap);

    expect(attempts).toBe(2);
    expect(store.getState().session?.turn_id).toBe(2);
  });

  it('ignores a second tap while a turn is in flight', async () => {
    let release: (r: Response) => void = () => undefined;
    let posts = 0;
    const { store } = setup((_, path) => {
      if (!path.endsWith('/actions')) return respond(201, VIEW(1));
      posts++;
      return new Promise<Response>((r) => (release = r)) as unknown as Response;
    });
    await store.getState().start('search', 'tee');

    const first = store.getState().act(tap);
    await store.getState().act(tap);
    release(respond(200, { turn_id: 2, ui: UI(2) }));
    await first;

    expect(posts).toBe(1);
  });

  it('surfaces a failed turn as an error but keeps the screen', async () => {
    const { store } = setup((_, path) =>
      path.endsWith('/actions')
        ? respond(200, { turn_id: 2, ui: UI(2), error: { code: 'turn_failed', title: 'Something went wrong on our side', status: 500 } })
        : respond(201, VIEW(1)),
    );
    await store.getState().start('search', 'tee');

    await store.getState().act(tap);

    expect(store.getState().error?.code).toBe('turn_failed');
    expect(store.getState().session?.turn_id).toBe(2);
  });

  describe('streamed turns', () => {
    const frames = (...events: [string, unknown][]) =>
      new Response(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(''), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    const skeleton = { id: 'loading', type: 'loading_skeleton', props: { shape: 'cards', count: 3 } };

    it('shows the server skeleton while working, then the new screen', async () => {
      const loadingSeen: unknown[] = [];
      const { store } = setup((_, path) =>
        path.endsWith('/actions')
          ? frames(['ui.loading', { turn_id: 2, components: [skeleton] }], ['ui.render', { envelope: UI(2) }], ['done', { turn_id: 2 }])
          : respond(201, VIEW(1)),
      );
      await store.getState().start('search', 'tee');
      const unsubscribe = store.subscribe((s) => s.loading && loadingSeen.push(s.loading));

      await store.getState().act(tap);
      unsubscribe();

      expect(loadingSeen).toEqual([[skeleton]]);
      expect(store.getState()).toMatchObject({ loading: null, phase: 'idle', error: null });
      expect(store.getState().session?.turn_id).toBe(2);
    });

    it('keeps the screen and shows the problem from an error event', async () => {
      const { store } = setup((_, path) =>
        path.endsWith('/actions')
          ? frames(['ui.render', { envelope: UI(2) }], ['error', { problem: { status: 503, code: 'ai_unavailable', title: 'Busy' } }])
          : respond(201, VIEW(1)),
      );
      await store.getState().start('search', 'tee');

      await store.getState().act(tap);

      expect(store.getState().session?.turn_id).toBe(2);
      expect(store.getState().error?.code).toBe('ai_unavailable');
    });

    it('a dropped stream resumes from the snapshot, waiting while the turn finishes', async () => {
      let snapshots = 0;
      const { store, calls } = setup((m, path) => {
        if (path.endsWith('/actions')) {
          const body = new ReadableStream({
            start(c) {
              c.error(new TypeError('Network request failed'));
            },
          });
          return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
        }
        if (m === 'GET') return respond(200, ++snapshots < 3 ? { ...VIEW(1), status: 'busy' } : VIEW(2));
        return respond(201, VIEW(1));
      });
      await store.getState().start('search', 'tee');

      await store.getState().act(tap);

      expect(calls.filter((c) => c.path.endsWith('/actions'))).toHaveLength(1); // never resent
      expect(snapshots).toBe(3);
      expect(store.getState().session?.turn_id).toBe(2);
      expect(store.getState().error).toBeNull();
    });
  });

  it('reports a failed start without a session', async () => {
    const { store } = setup(() => respond(422, { code: 'validation_error', title: 'Bad request' }));

    expect(await store.getState().start('search', 'x')).toBeNull();
    expect(store.getState().error?.code).toBe('validation_error');
  });
});
