import { ApiClient } from '../client';
import { ApiError, friendlyMessage, problemFrom } from '../errors';

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

function client(handler: Handler, tokens?: { token?: string | null; refresh?: () => Promise<boolean> }) {
  const calls: { url: string; init: RequestInit }[] = [];
  let token = tokens?.token ?? 'old';
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return handler(url, init);
  }) as unknown as typeof fetch;
  const refresh = jest.fn(
    tokens?.refresh ??
      (async () => {
        token = 'new';
        return true;
      }),
  );
  const api = new ApiClient({
    baseUrl: 'https://api.test',
    genuiVersion: 2,
    appVersion: '0.1.0',
    fetchImpl,
    defaultTimeoutMs: 50,
    tokens: { accessToken: () => token, refresh },
  });
  return { api, calls, refresh };
}

const headersOf = (init: RequestInit) => init.headers as Record<string, string>;

describe('ApiClient', () => {
  it('sends the token, GenUI version, app version and a JSON body', async () => {
    const { api, calls } = client(() => json(200, { ok: true }));

    const result = await api.post<{ ok: boolean }>('/v1/x', { a: 1 });

    expect(result).toEqual({ ok: true });
    const h = headersOf(calls[0]!.init);
    expect(calls[0]!.url).toBe('https://api.test/v1/x');
    expect(h.Authorization).toBe('Bearer old');
    expect(h['X-GenUI-Version']).toBe('2');
    expect(h['X-App-Version']).toBe('0.1.0');
    expect(h['Content-Type']).toBe('application/json');
    expect(calls[0]!.init.body).toBe('{"a":1}');
  });

  it('omits the token on unauthenticated calls', async () => {
    const { api, calls } = client(() => json(200, {}));

    await api.post('/v1/auth/refresh', {}, { auth: false });

    expect(headersOf(calls[0]!.init).Authorization).toBeUndefined();
  });

  it('turns problem+json into an ApiError with code, extras and Retry-After', async () => {
    const { api } = client(() =>
      json(409, { type: '/problems/stale_turn', title: 'Stale', status: 409, code: 'stale_turn', current_turn: 4 }, { 'Retry-After': '2' }),
    );

    const error = await api.get('/v1/s').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: 'stale_turn', extra: { current_turn: 4 }, retryAfterS: 2 });
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    const { api, calls, refresh } = client((_, init) =>
      headersOf(init).Authorization === 'Bearer new' ? json(200, { ok: 1 }) : json(401, { code: 'token_expired' }),
    );

    await expect(api.get('/v1/me')).resolves.toEqual({ ok: 1 });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(calls).toHaveLength(2);
  });

  it('shares one refresh between concurrent 401s', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => (release = r));
    let token = 'old';
    const { api, refresh } = client(
      (_, init) => (headersOf(init).Authorization === `Bearer new` ? json(200, {}) : json(401, {})),
      {
        refresh: async () => {
          await gate;
          token = 'new';
          return true;
        },
      },
    );
    // Make the shared token visible to the client for the retries.
    (api as unknown as { config: { tokens: { accessToken: () => string } } }).config.tokens.accessToken = () => token;

    const pending = Promise.all([api.get('/a'), api.get('/b'), api.get('/c')]);
    await new Promise((r) => setTimeout(r, 0));
    release();
    await pending;

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('gives up when the refresh fails, surfacing the 401', async () => {
    const { api } = client(() => json(401, { code: 'token_expired', title: 'Expired' }), { refresh: async () => false });

    await expect(api.get('/v1/me')).rejects.toMatchObject({ status: 401, code: 'token_expired' });
  });

  it('maps a network failure to an offline error and a hang to a timeout', async () => {
    const offline = client(() => {
      throw new TypeError('Network request failed');
    });
    await expect(offline.api.get('/x')).rejects.toMatchObject({ status: 0, code: 'offline' });

    const slow = client(
      (_, init) =>
        new Promise<Response>((_, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    );
    await expect(slow.api.get('/x')).rejects.toMatchObject({ status: 0, code: 'timeout' });
  });

  it('handles 204 and non-JSON error bodies', async () => {
    const empty = client(() => new Response(null, { status: 204 }));
    await expect(empty.api.delete('/x')).resolves.toBeUndefined();

    const html = client(() => new Response('<html>bad gateway</html>', { status: 502 }));
    await expect(html.api.get('/x')).rejects.toMatchObject({ status: 502, code: 'http_502' });
  });
});

describe('error messages', () => {
  it('speaks plainly for codes the user can act on', () => {
    expect(friendlyMessage(problemFrom(429, { code: 'daily_limit' }, null))).toMatch(/today's limit/);
    expect(friendlyMessage(problemFrom(500, { title: 'Boom', detail: 'Database down' }, null))).toBe('Database down');
    expect(friendlyMessage(new Error('x'))).toMatch(/Something went wrong/);
  });
});
