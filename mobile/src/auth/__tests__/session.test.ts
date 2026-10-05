import { createSession } from '../session';
import type { SecretStore } from '../tokenStore';

function memory(initial: Record<string, string> = {}): SecretStore & { data: Map<string, string> } {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get: async (k) => data.get(k) ?? null,
    set: async (k, v) => {
      data.set(k, v);
    },
    remove: async (k) => {
      data.delete(k);
    },
  };
}

const USER = { id: 'u1', email: 'asha@example.com', display_name: 'Asha Rao' };
const PAIR = { access_token: 'a2', access_token_expires_in: 900, refresh_token: 'r2', refresh_token_expires_in: 1, token_type: 'Bearer' };

function respond(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

function setup(store: SecretStore, routes: Record<string, () => Response>) {
  const seen: string[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    const path = url.replace('https://api.test', '');
    seen.push(`${init.method} ${path}`);
    const route = routes[`${init.method} ${path}`];
    return route ? route() : respond(404, { code: 'not_found' });
  }) as unknown as typeof fetch;
  const { useStore } = createSession({ store, baseUrl: 'https://api.test', fetchImpl });
  return { useStore, seen };
}

describe('session', () => {
  it('developer sign-in stores the refresh token, never the access token, and sends the install id', async () => {
    const store = memory();
    let body = '';
    const { useStore } = createSession({
      store,
      baseUrl: 'https://api.test',
      fetchImpl: (async (_url: string, init: RequestInit) => {
        body = String(init.body);
        return respond(200, { tokens: { ...PAIR, access_token: 'a1', refresh_token: 'r1' }, user: USER, is_new_user: true });
      }) as unknown as typeof fetch,
    });

    await useStore.getState().signInWithDev('asha@example.com');

    expect(useStore.getState()).toMatchObject({ status: 'signedIn', accessToken: 'a1', user: USER });
    expect(store.data.get('stylesense.refresh_token')).toBe('r1');
    expect([...store.data.values()]).not.toContain('a1');
    expect(JSON.parse(body)).toMatchObject({ email: 'asha@example.com', installation_id: expect.any(String) });
  });

  it('boots straight into the app from a stored session, rotating the refresh token', async () => {
    const store = memory({ 'stylesense.refresh_token': 'r1' });
    const { useStore } = setup(store, {
      'POST /v1/auth/refresh': () => respond(200, PAIR),
      'GET /v1/me': () => respond(200, USER),
    });

    await useStore.getState().boot();

    expect(useStore.getState()).toMatchObject({ status: 'signedIn', accessToken: 'a2', user: USER });
    expect(store.data.get('stylesense.refresh_token')).toBe('r2');
  });

  it('boots to sign-in when there is no session', async () => {
    const { useStore, seen } = setup(memory(), {});

    await useStore.getState().boot();

    expect(useStore.getState().status).toBe('signedOut');
    expect(seen).toEqual([]);
  });

  it('a rejected refresh ends the session and forgets the token', async () => {
    const store = memory({ 'stylesense.refresh_token': 'stolen' });
    const { useStore } = setup(store, { 'POST /v1/auth/refresh': () => respond(401, { code: 'refresh_reused' }) });

    await useStore.getState().boot();

    expect(useStore.getState().status).toBe('signedOut');
    expect(store.data.has('stylesense.refresh_token')).toBe(false);
  });

  it('sign-out clears locally even when the server is unreachable', async () => {
    const store = memory({ 'stylesense.refresh_token': 'r1' });
    const { useStore } = createSession({
      store,
      baseUrl: 'https://api.test',
      fetchImpl: (async () => {
        throw new TypeError('offline');
      }) as unknown as typeof fetch,
    });

    await useStore.getState().signOut();

    expect(useStore.getState().status).toBe('signedOut');
    expect(store.data.has('stylesense.refresh_token')).toBe(false);
  });

  it('stays signed in when launched offline with a session', async () => {
    const store = memory({ 'stylesense.refresh_token': 'r1' });
    let calls = 0;
    const { useStore } = createSession({
      store,
      baseUrl: 'https://api.test',
      fetchImpl: (async () => {
        calls++;
        if (calls === 1) return respond(200, PAIR);
        throw new TypeError('offline');
      }) as unknown as typeof fetch,
    });

    await useStore.getState().boot();

    expect(useStore.getState().status).toBe('signedIn');
  });
});
